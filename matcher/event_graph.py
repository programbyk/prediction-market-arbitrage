"""V7 Event Graph Engine.

Markets are no longer grouped only by team/player/asset. Each market is
converted into an EventObject containing:

    category + entity + market_intent + time scope

Only EventObjects with compatible identities are compared. Every Kalshi
contract is compared against all Polymarket contracts in its event node, so
one Kalshi market can produce several relevant Polymarket options.
"""

from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from models import MatchResult, ParsedMarket
from legacy.scanner_v6_1 import (
    compare_markets,
    is_review_candidate,
    normalize_text,
)


@dataclass(frozen=True)
class EventObject:
    category: str
    entity: str
    intent: str
    year: Optional[int]
    scope: str
    key: str


SPORTS_INTENT_PATTERNS: Tuple[Tuple[str, str], ...] = (
    # Match/game propositions
    (r"\bwhat will (?:the )?announcers? say\b|\bannouncers? mention\b", "broadcast_mention"),
    (r"\bclin(?:ch|ches)\b.*\bpostseason\b|\bmake (?:the )?postseason\b", "postseason_qualification"),
    (r"\bhost (?:a |the )?playoff game\b", "playoff_host"),
    (r"\bplayoff seed\b|\bnumber [1-8] seed\b|\b#\s?[1-8] seed\b", "playoff_seed"),
    (r"\bdivision winner\b|\bwin (?:the )?division\b", "division_winner"),
    (r"\bconference winner\b|\bwin (?:the )?conference\b", "conference_winner"),
    (r"\bsuper bowl\b.*\bwin\b|\bwin (?:the )?super bowl\b", "super_bowl_winner"),
    (r"\bworld series\b.*\bwin\b|\bwin (?:the )?world series\b", "world_series_winner"),
    (r"\brelegat(?:e|ed|ion)\b", "relegation"),
    (r"\bpromot(?:e|ed|ion)\b", "promotion"),
    (r"\bfinish (?:in )?top 4\b|\btop four\b", "top_four_finish"),
    (r"\bfinish (?:in )?top 6\b|\btop six\b", "top_six_finish"),
    (r"\bqualif(?:y|ies|ied|ication)\b.*\bchampions league\b", "champions_league_qualification"),
    (r"\bteam of the year\b", "team_of_the_year"),
    (r"\bgolden boot\b|\btop scorer\b", "top_scorer"),
    (r"\bmost sacks\b|\bsack leader\b", "most_sacks"),
    (r"\bmost touchdowns\b|\btouchdown leader\b", "most_touchdowns"),
    (r"\bmost passing yards\b|\bpassing yards leader\b", "most_passing_yards"),
    (r"\bmost rushing yards\b|\brushing yards leader\b", "most_rushing_yards"),
    (r"\bmost receiving yards\b|\breceiving yards leader\b", "most_receiving_yards"),
    (r"\bmvp\b|\bmost valuable player\b", "mvp"),
    (r"\bcy young\b", "cy_young"),
    (r"\bhank aaron award\b", "hank_aaron_award"),
    (r"\bhome run derby\b|\bhr derby\b", "home_run_derby"),
    (r"\bretire(?:s|d|ment|ing)?\b", "retirement"),
    (r"\bjoin(?:s|ed|ing)?\b.*\bteam\b|\bsign(?:s|ed|ing)?\b.*\bteam\b", "team_move"),
    (r"\btrad(?:e|es|ed|ing)\b", "trade"),
    (r"\bcoach\b.*\b(?:fired|sacked|dismissed)\b", "coach_fired"),
    (r"\bboth teams (?:to )?score\b.*\b1st half\b", "first_half_btts"),
    (r"\bboth teams (?:to )?score\b|\bbtts\b", "both_teams_to_score"),
    (r"\bover \d+(?:\.\d+)? maps?\b|\btotal maps?\b", "total_maps"),
    (r"\bmap\s*\d+\b.*\bwin\b|\bwin\b.*\bmap\s*\d+\b", "map_winner"),
    (r"\bseries winner\b|\bwin (?:the )?series\b", "series_winner"),
    (r"\bmatch winner\b|\bwin (?:the )?match\b|\bbeat\b|\bdefeat\b", "match_winner"),
    (r"\bteam total\b", "team_total"),
    (r"\bplayer total\b", "player_total"),
    (r"\bfirst inning\b", "first_inning"),
    (r"\bno hitter\b", "no_hitter"),
    (r"\bgrand slam\b", "grand_slam"),
)

POLITICS_INTENT_PATTERNS: Tuple[Tuple[str, str], ...] = (
    (r"\bprimary\b", "primary_winner"),
    (r"\bnominee\b|\bnomination\b", "nomination"),
    (r"\bapproval rating\b", "approval_rating"),
    (r"\bmargin\b|\bpercentage points?\b", "election_margin"),
    (r"\bcontrol (?:of )?(?:the )?(?:senate|house|congress)\b", "chamber_control"),
    (r"\bwin\b|\belected\b|\belection winner\b", "election_winner"),
)

CRYPTO_INTENT_PATTERNS: Tuple[Tuple[str, str], ...] = (
    (r"\bmarket cap\b", "market_cap_threshold"),
    (r"\betf\b.*\bapprov", "etf_approval"),
    (r"\ball time high\b|\bath\b", "all_time_high"),
    (r"\babove\b|\bover\b|\bexceed\b|\bbelow\b|\bunder\b", "price_threshold"),
)

ECONOMY_INTENT_PATTERNS: Tuple[Tuple[str, str], ...] = (
    (r"\brate cut\b", "rate_cut"),
    (r"\brate hike\b", "rate_hike"),
    (r"\brecession\b", "recession"),
    (r"\bunemployment\b", "unemployment_threshold"),
    (r"\binflation\b|\bcpi\b", "inflation_threshold"),
    (r"\bgdp\b", "gdp_threshold"),
    (r"\bjobs\b|\bpayrolls\b", "payrolls_threshold"),
)


def _first_pattern(text: str, patterns: Sequence[Tuple[str, str]]) -> Optional[str]:
    normalized = normalize_text(text)
    for pattern, canonical in patterns:
        if re.search(pattern, normalized):
            return canonical
    return None


def infer_market_intent(market: ParsedMarket) -> Optional[str]:
    """Infer the exact proposition type represented by the market."""
    title = market.title.split("|", 1)[0].strip()

    if market.category == "sports":
        intent = _first_pattern(title, SPORTS_INTENT_PATTERNS)
        if intent:
            return intent
        if market.event_kind:
            return market.event_kind
        if market.event_action:
            return market.event_action
        if market.competition and market.market_type == "winner":
            return f"{market.competition}_winner"
        if market.market_type == "player_prop":
            return "player_prop"
        if market.market_type == "winner":
            return "winner"

    elif market.category == "politics":
        intent = _first_pattern(title, POLITICS_INTENT_PATTERNS)
        if intent:
            return intent
        if market.market_type == "winner":
            return "election_winner"

    elif market.category == "crypto":
        intent = _first_pattern(title, CRYPTO_INTENT_PATTERNS)
        if intent:
            return intent
        if market.threshold is not None:
            return "price_threshold"

    elif market.category == "economy":
        intent = _first_pattern(title, ECONOMY_INTENT_PATTERNS)
        if intent:
            return intent
        if market.metric:
            return f"{market.metric}_threshold"

    return None


def infer_entity_key(market: ParsedMarket) -> Optional[str]:
    """Return the primary real-world entity whose outcome resolves the market."""
    if market.category == "sports":
        if market.player:
            return f"player:{market.player}"
        if market.teams:
            return "teams:" + "+".join(sorted(market.teams))
        if market.event_subject:
            return f"subject:{market.event_subject}"
        if market.competition:
            return f"competition:{market.competition}"

    elif market.category == "politics":
        if market.candidate:
            return f"candidate:{market.candidate}"
        if market.party:
            return f"party:{market.party}"
        geography = market.state or market.country
        if geography and market.office:
            return f"race:{geography}:{market.office}"

    elif market.category == "crypto":
        if market.asset:
            return f"asset:{market.asset}"

    elif market.category == "economy":
        if market.metric:
            geography = market.country or "unknown_country"
            return f"metric:{geography}:{market.metric}"

    return None


def build_event_object(market: ParsedMarket) -> Optional[EventObject]:
    intent = infer_market_intent(market)
    entity = infer_entity_key(market)
    if not intent or not entity:
        return None

    scope_parts: List[str] = []
    if market.category == "sports":
        scope_parts.extend(
            value for value in (
                market.sport,
                market.league,
                market.competition,
                market.event_scope,
            )
            if value
        )
    elif market.category == "politics":
        scope_parts.extend(
            value for value in (
                market.country,
                market.state,
                market.office,
                market.subtype,
            )
            if value
        )
    elif market.category == "crypto":
        scope_parts.extend(
            value for value in (
                market.asset,
                market.direction,
                str(market.threshold) if market.threshold is not None else None,
            )
            if value
        )
    elif market.category == "economy":
        scope_parts.extend(
            value for value in (
                market.country,
                market.metric,
                market.period,
                market.comparison,
                str(market.threshold) if market.threshold is not None else None,
            )
            if value
        )

    scope = "|".join(scope_parts)
    key = "|".join(
        (
            market.category,
            entity,
            intent,
            str(market.year or ""),
            scope,
        )
    )
    return EventObject(
        category=market.category,
        entity=entity,
        intent=intent,
        year=market.year,
        scope=scope,
        key=key,
    )


def annotate_event_objects(markets: Sequence[ParsedMarket]) -> int:
    annotated = 0
    for market in markets:
        event = build_event_object(market)
        if not event:
            continue
        market.market_intent = event.intent
        market.entity_key = event.entity
        market.event_object_key = event.key
        annotated += 1
    return annotated


def _graph_keys(event: EventObject) -> Set[str]:
    """Strict and relaxed keys for recall without entity-only grouping."""
    keys = {
        f"strict|{event.category}|{event.entity}|{event.intent}|"
        f"{event.year or ''}|{event.scope}",
        f"entity_intent|{event.category}|{event.entity}|{event.intent}",
    }
    if event.year:
        keys.add(
            f"entity_intent_year|{event.category}|{event.entity}|"
            f"{event.intent}|{event.year}"
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
    """Compare all contracts inside compatible entity+intent event nodes."""
    poly_graph = build_event_graph(polymarket)
    pair_hits: Counter[Tuple[str, str]] = Counter()
    pair_objects: Dict[Tuple[str, str], Tuple[ParsedMarket, ParsedMarket]] = {}

    for kalshi_market in kalshi:
        event = build_event_object(kalshi_market)
        if not event:
            continue

        for key in _graph_keys(event):
            for poly_market in poly_graph.get(key, []):
                pair_id = (kalshi_market.source_id, poly_market.source_id)
                pair_hits[pair_id] += 1
                pair_objects[pair_id] = (kalshi_market, poly_market)

    pairs = [
        (pair_objects[pair_id][0], pair_objects[pair_id][1], hits)
        for pair_id, hits in pair_hits.items()
    ]
    pairs.sort(key=lambda item: item[2], reverse=True)
    return pairs


def find_event_graph_matches(
    kalshi: Sequence[ParsedMarket],
    polymarket: Sequence[ParsedMarket],
) -> Tuple[List[MatchResult], List[MatchResult], List[MatchResult]]:
    annotate_event_objects(kalshi)
    annotate_event_objects(polymarket)

    pairs = event_graph_candidate_pairs(kalshi, polymarket)
    print(f"[EventGraph] Candidate pairs generated: {len(pairs)}")

    accepted: List[MatchResult] = []
    review: List[MatchResult] = []
    all_scored: List[MatchResult] = []

    for kalshi_market, poly_market, hits in pairs:
        result = compare_markets(kalshi_market, poly_market, hits)
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
    """Export every EventObject so grouping can be inspected."""
    annotate_event_objects(kalshi)
    annotate_event_objects(polymarket)

    path = Path(export_dir)
    path.mkdir(parents=True, exist_ok=True)
    csv_path = path / "event_graph_nodes.csv"

    rows = []
    for market in [*kalshi, *polymarket]:
        if not market.event_object_key:
            continue
        rows.append(
            {
                "platform": market.platform,
                "source_id": market.source_id,
                "category": market.category,
                "entity_key": market.entity_key,
                "market_intent": market.market_intent,
                "year": market.year or "",
                "event_object_key": market.event_object_key,
                "title": market.title,
            }
        )

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
                "title",
            ),
        )
        writer.writeheader()
        writer.writerows(rows)

    return csv_path
