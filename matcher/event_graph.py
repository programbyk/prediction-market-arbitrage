"""V7.1 graph matcher built on Entity, Intent and Event engines."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Sequence, Set, Tuple

from core.event_engine import EventEngine, EventObject
from models import MatchResult, ParsedMarket
from legacy.scanner_v6_1 import is_review_candidate
from matcher.confidence_engine import semantic_confidence


_EVENT_ENGINE = EventEngine()


def build_event_object(market: ParsedMarket) -> EventObject | None:
    return _EVENT_ENGINE.build(market)


def annotate_event_objects(markets: Sequence[ParsedMarket]) -> int:
    count = 0
    for market in markets:
        if build_event_object(market):
            count += 1
    return count



def resolution_compatible(left: EventObject, right: EventObject) -> bool:
    """Hard equivalence checks before a pair reaches the score matcher."""
    if left.category != right.category:
        return False
    if left.entity.key != right.entity.key:
        return False
    if left.intent != right.intent:
        return False

    if (
        left.resolution_type
        and right.resolution_type
        and left.resolution_type != right.resolution_type
    ):
        return False

    if left.year and right.year and left.year != right.year:
        return False

    if left.threshold is not None and right.threshold is not None:
        tolerance = max(0.001, 0.0001 * max(abs(left.threshold), abs(right.threshold), 1))
        if abs(left.threshold - right.threshold) > tolerance:
            return False

    if left.direction and right.direction and left.direction != right.direction:
        return False

    if left.resolution_time and right.resolution_time:
        if left.resolution_time != right.resolution_time:
            return False

    if left.deadline and right.deadline and left.deadline != right.deadline:
        return False

    if left.lower_bound is not None and right.lower_bound is not None:
        if abs(left.lower_bound - right.lower_bound) > 0.001:
            return False

    if left.upper_bound is not None and right.upper_bound is not None:
        if abs(left.upper_bound - right.upper_bound) > 0.001:
            return False

    return True


def _graph_keys(event: EventObject) -> Set[str]:
    """Strict and relaxed keys that always preserve entity + intent."""
    keys = {
        f"strict|{event.key}",
        f"entity_intent_resolution|{event.category}|{event.entity.key}|"
        f"{event.intent}|{event.resolution_type or ''}",
    }

    if event.year:
        keys.add(
            f"entity_intent_year|{event.category}|"
            f"{event.entity.key}|{event.intent}|{event.year}"
        )

    if event.category == "sports" and event.league:
        keys.add(
            f"sports_scope|{event.entity.key}|{event.intent}|"
            f"{event.league}|{event.year or ''}"
        )

    if event.category == "crypto" and event.threshold is not None:
        keys.add(
            f"crypto_threshold|{event.entity.key}|{event.intent}|"
            f"{round(event.threshold, 3)}|{event.direction or ''}"
        )

    if event.category == "economy" and event.period:
        keys.add(
            f"economy_period|{event.entity.key}|{event.intent}|{event.period}"
        )

    return keys


def build_event_graph(
    markets: Sequence[ParsedMarket],
) -> Dict[str, List[ParsedMarket]]:
    graph: Dict[str, List[ParsedMarket]] = defaultdict(list)
    for market in markets:
        event = build_event_object(market)
        if not event:
            continue
        for key in _graph_keys(event):
            graph[key].append(market)
    return graph


def event_graph_candidate_pairs(
    kalshi: Sequence[ParsedMarket],
    polymarket: Sequence[ParsedMarket],
) -> List[Tuple[ParsedMarket, ParsedMarket, int]]:
    """Return every pair inside compatible entity+intent nodes."""
    poly_graph = build_event_graph(polymarket)
    pair_hits: Counter[Tuple[str, str]] = Counter()
    pair_objects: Dict[Tuple[str, str], Tuple[ParsedMarket, ParsedMarket]] = {}

    for kalshi_market in kalshi:
        event = build_event_object(kalshi_market)
        if not event:
            continue
        for key in _graph_keys(event):
            for poly_market in poly_graph.get(key, []):
                poly_event = build_event_object(poly_market)
                if not poly_event or not resolution_compatible(event, poly_event):
                    continue
                pair_id = (kalshi_market.source_id, poly_market.source_id)
                pair_hits[pair_id] += 1
                pair_objects[pair_id] = (kalshi_market, poly_market)

    output = [
        (
            pair_objects[pair_id][0],
            pair_objects[pair_id][1],
            hits,
        )
        for pair_id, hits in pair_hits.items()
    ]
    output.sort(key=lambda item: item[2], reverse=True)
    return output


def find_event_graph_matches(
    kalshi: Sequence[ParsedMarket],
    polymarket: Sequence[ParsedMarket],
) -> Tuple[List[MatchResult], List[MatchResult], List[MatchResult]]:
    annotated_k = annotate_event_objects(kalshi)
    annotated_p = annotate_event_objects(polymarket)
    print(
        f"[SemanticEngine] EventObjects: "
        f"Kalshi={annotated_k}, Polymarket={annotated_p}"
    )

    pairs = event_graph_candidate_pairs(kalshi, polymarket)
    print(f"[EventGraph] Candidate pairs generated: {len(pairs)}")

    accepted: List[MatchResult] = []
    review: List[MatchResult] = []
    all_scored: List[MatchResult] = []

    for kalshi_market, poly_market, hits in pairs:
        kalshi_event = build_event_object(kalshi_market)
        poly_event = build_event_object(poly_market)
        if not kalshi_event or not poly_event:
            continue
        result = semantic_confidence(
            kalshi_market,
            poly_market,
            kalshi_event,
            poly_event,
            hits,
        )
        all_scored.append(result)
        if result.accepted:
            accepted.append(result)
        elif is_review_candidate(result):
            review.append(result)

    sort_key = lambda result: (result.confidence, result.bucket_hits)
    accepted.sort(key=sort_key, reverse=True)
    review.sort(key=sort_key, reverse=True)
    all_scored.sort(key=sort_key, reverse=True)

    print(f"[EventGraph] Candidate comparisons: {len(all_scored)}")
    print(f"[EventGraph] Accepted matches: {len(accepted)}")
    print(f"[EventGraph] Review matches: {len(review)}")
    return accepted, review, all_scored


def export_event_graph(
    kalshi: Sequence[ParsedMarket],
    polymarket: Sequence[ParsedMarket],
    export_dir: str = "exports",
) -> Path:
    annotate_event_objects(kalshi)
    annotate_event_objects(polymarket)

    export_root = Path(export_dir)
    export_root.mkdir(parents=True, exist_ok=True)
    csv_path = export_root / "event_graph_nodes.csv"

    rows = []
    for market in [*kalshi, *polymarket]:
        if not market.event_object_key:
            continue
        rows.append({
            "platform": market.platform,
            "source_id": market.source_id,
            "category": market.category,
            "entity_key": market.entity_key,
            "market_intent": market.market_intent,
            "year": market.year or "",
            "event_object_key": market.event_object_key,
            "resolution_type": market.resolution_type or "",
            "resolution_time": market.resolution_time or "",
            "deadline": market.deadline or "",
            "lower_bound": market.lower_bound if market.lower_bound is not None else "",
            "upper_bound": market.upper_bound if market.upper_bound is not None else "",
            "threshold": market.threshold if market.threshold is not None else "",
            "direction": market.direction or "",
            "title": market.title,
        })

    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "platform",
                "source_id",
                "category",
                "entity_key",
                "market_intent",
                "year",
                "event_object_key",
                "resolution_type",
                "resolution_time",
                "deadline",
                "lower_bound",
                "upper_bound",
                "threshold",
                "direction",
                "title",
            ),
        )
        writer.writeheader()
        writer.writerows(rows)

    return csv_path
