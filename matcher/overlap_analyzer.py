"""Broad cross-platform overlap analysis.

This analyzer is deliberately more permissive than the strict matcher. It
helps identify where Kalshi and Polymarket appear to cover the same real-world
topics so parser and matcher work can be prioritized with evidence.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from models import ParsedMarket
from legacy.scanner_v6_1 import fuzzy_score, normalize_text


SUPPORTED_CATEGORIES = ("sports", "politics", "crypto", "economy")


@dataclass(frozen=True)
class OverlapCandidate:
    kalshi: ParsedMarket
    polymarket: ParsedMarket
    score: int
    category: str
    group: str
    reasons: Tuple[str, ...]


def overlap_group(market: ParsedMarket) -> str:
    if market.category == "sports":
        return "|".join(
            str(value or "")
            for value in (
                market.sport,
                market.league,
                market.competition,
                market.event_kind,
                market.year,
            )
        )
    if market.category == "politics":
        return "|".join(
            str(value or "")
            for value in (
                market.country,
                market.state,
                market.office,
                market.subtype,
                market.year,
            )
        )
    if market.category == "crypto":
        return "|".join(
            str(value or "")
            for value in (
                market.asset,
                market.market_type,
                market.direction,
                market.year,
            )
        )
    if market.category == "economy":
        return "|".join(
            str(value or "")
            for value in (
                market.country,
                market.metric,
                market.period,
                market.market_type,
            )
        )
    return ""


def candidate_keys(market: ParsedMarket) -> List[str]:
    """Recall-oriented index keys without category-wide Cartesian products."""
    keys: List[str] = []

    if market.category == "sports":
        if market.player:
            keys.append(f"sports|player|{market.player}")
        for team in market.teams:
            keys.append(f"sports|team|{team}")
        if market.competition:
            keys.append(f"sports|competition|{market.competition}")
        if market.event_kind:
            keys.append(f"sports|event_kind|{market.event_kind}")
        if market.league and market.year:
            keys.append(f"sports|league_year|{market.league}|{market.year}")
        elif market.league:
            keys.append(f"sports|league|{market.league}")

    elif market.category == "politics":
        if market.candidate:
            keys.append(f"politics|candidate|{market.candidate}")
        if market.state and market.office:
            keys.append(f"politics|state_office|{market.state}|{market.office}")
        if market.country and market.office and market.year:
            keys.append(
                f"politics|country_office_year|"
                f"{market.country}|{market.office}|{market.year}"
            )
        if market.party and market.office:
            keys.append(f"politics|party_office|{market.party}|{market.office}")

    elif market.category == "crypto":
        if market.asset:
            keys.append(f"crypto|asset|{market.asset}")
        if market.asset and market.threshold is not None:
            keys.append(
                f"crypto|asset_threshold|"
                f"{market.asset}|{round(market.threshold, 3)}"
            )

    elif market.category == "economy":
        if market.country and market.metric:
            keys.append(f"economy|country_metric|{market.country}|{market.metric}")
        if market.metric and market.period:
            keys.append(f"economy|metric_period|{market.metric}|{market.period}")
        if market.metric and market.threshold is not None:
            keys.append(
                f"economy|metric_threshold|"
                f"{market.metric}|{round(market.threshold, 3)}"
            )

    return keys


def score_overlap(
    kalshi: ParsedMarket,
    polymarket: ParsedMarket,
) -> Tuple[int, List[str]]:
    if kalshi.category != polymarket.category:
        return 0, []

    score = 15
    reasons = ["same category (+15)"]

    if kalshi.year and polymarket.year and kalshi.year == polymarket.year:
        score += 8
        reasons.append("same year (+8)")

    if kalshi.category == "sports":
        checks = (
            ("sport", kalshi.sport, polymarket.sport, 12),
            ("league", kalshi.league, polymarket.league, 12),
            ("competition", kalshi.competition, polymarket.competition, 18),
            ("event_kind", kalshi.event_kind, polymarket.event_kind, 18),
            (
                "participant_type",
                kalshi.participant_type,
                polymarket.participant_type,
                5,
            ),
        )
        for label, left, right, points in checks:
            if left and right and left == right:
                score += points
                reasons.append(f"same {label} (+{points})")

        if kalshi.player and polymarket.player:
            if kalshi.player == polymarket.player:
                score += 25
                reasons.append("same player/entity (+25)")
            else:
                score -= 20
                reasons.append("different player/entity (-20)")

        if kalshi.teams and polymarket.teams:
            if set(kalshi.teams) == set(polymarket.teams):
                score += 25
                reasons.append("same teams (+25)")
            elif set(kalshi.teams) & set(polymarket.teams):
                score += 8
                reasons.append("one shared team (+8)")

    elif kalshi.category == "politics":
        checks = (
            ("country", kalshi.country, polymarket.country, 10),
            ("state", kalshi.state, polymarket.state, 15),
            ("office", kalshi.office, polymarket.office, 18),
            ("candidate", kalshi.candidate, polymarket.candidate, 25),
            ("party", kalshi.party, polymarket.party, 12),
            ("subtype", kalshi.subtype, polymarket.subtype, 8),
        )
        for label, left, right, points in checks:
            if left and right and left == right:
                score += points
                reasons.append(f"same {label} (+{points})")

        if (
            kalshi.candidate
            and polymarket.candidate
            and kalshi.candidate != polymarket.candidate
        ):
            score -= 25
            reasons.append("different candidate (-25)")

    elif kalshi.category == "crypto":
        if kalshi.asset and polymarket.asset and kalshi.asset == polymarket.asset:
            score += 35
            reasons.append("same asset (+35)")
        if kalshi.direction and polymarket.direction:
            if kalshi.direction == polymarket.direction:
                score += 12
                reasons.append("same direction (+12)")
            else:
                score -= 15
                reasons.append("different direction (-15)")
        if kalshi.threshold is not None and polymarket.threshold is not None:
            tolerance = max(
                1.0,
                0.001 * max(kalshi.threshold, polymarket.threshold),
            )
            if abs(kalshi.threshold - polymarket.threshold) <= tolerance:
                score += 25
                reasons.append("same threshold (+25)")

    elif kalshi.category == "economy":
        checks = (
            ("country", kalshi.country, polymarket.country, 15),
            ("metric", kalshi.metric, polymarket.metric, 25),
            ("period", kalshi.period, polymarket.period, 20),
            ("comparison", kalshi.comparison, polymarket.comparison, 12),
        )
        for label, left, right, points in checks:
            if left and right and left == right:
                score += points
                reasons.append(f"same {label} (+{points})")
        if kalshi.threshold is not None and polymarket.threshold is not None:
            if abs(kalshi.threshold - polymarket.threshold) <= 0.001:
                score += 25
                reasons.append("same threshold (+25)")

    title_score = fuzzy_score(kalshi.title, polymarket.title)
    if title_score >= 85:
        score += 15
        reasons.append(f"high title similarity {title_score} (+15)")
    elif title_score >= 70:
        score += 8
        reasons.append(f"medium title similarity {title_score} (+8)")
    elif title_score >= 55:
        score += 3
        reasons.append(f"low title similarity {title_score} (+3)")

    return max(0, min(score, 100)), reasons


def generate_overlap_candidates(
    kalshi: Sequence[ParsedMarket],
    polymarket: Sequence[ParsedMarket],
    *,
    min_score: int = 45,
    top_per_kalshi: int = 5,
) -> List[OverlapCandidate]:
    poly_index: Dict[str, List[ParsedMarket]] = defaultdict(list)
    for market in polymarket:
        if market.category not in SUPPORTED_CATEGORIES:
            continue
        for key in candidate_keys(market):
            poly_index[key].append(market)

    output: List[OverlapCandidate] = []

    for kalshi_market in kalshi:
        if kalshi_market.category not in SUPPORTED_CATEGORIES:
            continue

        pool: Dict[str, ParsedMarket] = {}
        for key in candidate_keys(kalshi_market):
            for poly_market in poly_index.get(key, []):
                pool[poly_market.source_id] = poly_market

        scored: List[OverlapCandidate] = []
        for poly_market in pool.values():
            score, reasons = score_overlap(kalshi_market, poly_market)
            if score < min_score:
                continue
            scored.append(
                OverlapCandidate(
                    kalshi=kalshi_market,
                    polymarket=poly_market,
                    score=score,
                    category=kalshi_market.category,
                    group=overlap_group(kalshi_market),
                    reasons=tuple(reasons),
                )
            )

        scored.sort(key=lambda item: item.score, reverse=True)
        output.extend(scored[: max(1, top_per_kalshi)])

    output.sort(
        key=lambda item: (
            item.score,
            item.category,
            normalize_text(item.kalshi.title),
        ),
        reverse=True,
    )
    return output


def write_candidates_csv(
    candidates: Sequence[OverlapCandidate],
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = (
        "category",
        "group",
        "overlap_score",
        "kalshi_id",
        "kalshi_title",
        "polymarket_id",
        "polymarket_title",
        "reasons",
    )
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for candidate in candidates:
            writer.writerow({
                "category": candidate.category,
                "group": candidate.group,
                "overlap_score": candidate.score,
                "kalshi_id": candidate.kalshi.source_id,
                "kalshi_title": candidate.kalshi.title,
                "polymarket_id": candidate.polymarket.source_id,
                "polymarket_title": candidate.polymarket.title,
                "reasons": " | ".join(candidate.reasons),
            })


def analyze_overlap(
    kalshi: Sequence[ParsedMarket],
    polymarket: Sequence[ParsedMarket],
    *,
    min_score: int = 45,
    top_per_kalshi: int = 5,
    sample_limit: int = 20,
    export_dir: str = "exports",
) -> List[Path]:
    candidates = generate_overlap_candidates(
        kalshi,
        polymarket,
        min_score=min_score,
        top_per_kalshi=top_per_kalshi,
    )

    export_root = Path(export_dir)
    export_root.mkdir(parents=True, exist_ok=True)

    files: List[Path] = []
    all_path = export_root / "overlap_candidates_all.csv"
    write_candidates_csv(candidates, all_path)
    files.append(all_path)

    counts = Counter(item.category for item in candidates)

    print("\n" + "=" * 92)
    print("CROSS-PLATFORM OVERLAP ANALYZER")
    print("=" * 92)
    print(f"Minimum score: {min_score}")
    print(f"Top candidates retained per Kalshi market: {top_per_kalshi}")
    print(f"Total broad overlap candidates: {len(candidates)}")

    print("\nCandidates by category:")
    for category in SUPPORTED_CATEGORIES:
        print(f"  - {category}: {counts.get(category, 0)}")

    top_groups = {}
    for category in SUPPORTED_CATEGORIES:
        category_candidates = [
            item for item in candidates if item.category == category
        ]
        category_path = export_root / f"overlap_candidates_{category}.csv"
        write_candidates_csv(category_candidates, category_path)
        files.append(category_path)

        group_counts = Counter(item.group for item in category_candidates)
        top_groups[category] = group_counts.most_common(50)

        print(f"\nTop groups — {category}:")
        for group, count in group_counts.most_common(20):
            print(f"  - {group or '(incomplete identity)'}: {count}")

        print(
            f"\nTop {min(sample_limit, len(category_candidates))} "
            f"candidates — {category}:"
        )
        for index, item in enumerate(category_candidates[:sample_limit], 1):
            print("-" * 92)
            print(f"{index}. SCORE {item.score}/100")
            print(f"Kalshi:     {item.kalshi.title}")
            print(f"Polymarket: {item.polymarket.title}")
            print(f"Group: {item.group or '(incomplete identity)'}")
            for reason in item.reasons[:10]:
                print(f"  ✓ {reason}")

    summary_path = export_root / "overlap_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "total_candidates": len(candidates),
                "min_score": min_score,
                "top_per_kalshi": top_per_kalshi,
                "category_counts": dict(counts),
                "top_groups": top_groups,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    files.append(summary_path)

    print("\nReports exported:")
    for path in files:
        print(f"  - {path}")

    return files
