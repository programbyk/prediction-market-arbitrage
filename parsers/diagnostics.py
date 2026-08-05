"""Diagnostics for markets that fall into the ``other`` category."""
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from models import ParsedMarket
from legacy.scanner_v6_1 import normalize_text


SIGNALS: Dict[str, Tuple[str, ...]] = {
    "sports": (
        "nba", "nfl", "mlb", "nhl", "wnba", "epl", "premier league",
        "champions league", "world cup", "soccer", "football", "baseball",
        "basketball", "hockey", "tennis", "golf", "ufc", "mma", "boxing",
        "nascar", "formula 1", "f1", "cricket", "rugby", "match", "game",
        "playoffs", "postseason", "super bowl", "world series",
    ),
    "politics": (
        "election", "primary", "president", "presidential", "senate",
        "senator", "governor", "mayor", "congress", "democrat",
        "republican", "gop", "nominee", "nomination", "cabinet",
        "parliament", "prime minister", "approval rating", "electoral",
    ),
    "crypto": (
        "bitcoin", "btc", "ethereum", "eth", "solana", "sol", "xrp",
        "dogecoin", "doge", "crypto", "token", "blockchain", "stablecoin",
    ),
    "economy": (
        "inflation", "cpi", "gdp", "unemployment", "jobs report",
        "payrolls", "interest rate", "fed", "federal reserve", "recession",
        "treasury", "yield", "economic growth",
    ),
    "weather": (
        "temperature", "weather", "rain", "snow", "hurricane", "tornado",
        "storm", "heat", "degrees", "precipitation",
    ),
    "entertainment": (
        "oscar", "academy awards", "grammy", "emmy", "box office",
        "movie", "film", "album", "song", "billboard", "celebrity",
        "tv show", "netflix",
    ),
    "technology": (
        "apple", "google", "microsoft", "openai", "chatgpt", "ai model",
        "iphone", "android", "tesla", "spacex", "launch", "software",
    ),
    "geopolitics": (
        "war", "ceasefire", "invasion", "missile", "nuclear", "sanction",
        "peace deal", "military", "border", "territory",
    ),
}


def _contains_signal(text: str, term: str) -> bool:
    normalized_term = normalize_text(term)
    if " " in normalized_term:
        return normalized_term in text
    return re.search(rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])", text) is not None


def infer_suspected_category(market: ParsedMarket) -> Tuple[str, str, List[str]]:
    """Infer which parser family may have missed an ``other`` market."""
    display_title = market.title.split("|", 1)[0].strip()
    normalized = normalize_text(display_title)

    hits_by_category: Dict[str, List[str]] = {}
    for category, terms in SIGNALS.items():
        hits = [term for term in terms if _contains_signal(normalized, term)]
        if hits:
            hits_by_category[category] = hits

    if not hits_by_category:
        return (
            "unsupported_or_unknown",
            "No recognized signal for the currently supported parser families",
            [],
        )

    ranking = sorted(
        hits_by_category.items(),
        key=lambda item: (-len(item[1]), item[0]),
    )
    suspected, hits = ranking[0]

    if suspected in {"sports", "politics", "crypto", "economy"}:
        reason = (
            f"Likely missed {suspected} market: recognizable keywords were "
            "present, but the structured identity detector returned no category"
        )
    else:
        reason = (
            f"Likely valid {suspected} market, but this category does not yet "
            "have a dedicated parser"
        )
    return suspected, reason, hits


def _raw_metadata(market: ParsedMarket) -> Dict[str, str]:
    raw = market.raw or {}
    fields = (
        "ticker", "event_ticker", "series_ticker", "category",
        "title", "subtitle", "yes_sub_title", "no_sub_title",
        "question", "slug",
    )
    return {field: str(raw.get(field, "")) for field in fields if raw.get(field)}


def _series_prefix(market: ParsedMarket) -> str:
    raw = market.raw or {}
    value = str(raw.get("series_ticker") or raw.get("event_ticker") or "")
    if not value:
        return "(missing)"
    return value.split("-", 1)[0][:40]


def diagnose_other_markets(
    platform_name: str,
    markets: Sequence[ParsedMarket],
    *,
    sample_limit: int = 20,
    export_dir: str = "exports",
) -> Path:
    """Print and export a detailed report for ``other`` markets."""
    other = [m for m in markets if m.category == "other"]
    tradeable_other = [
        m for m in other
        if m.price and m.price.yes is not None and m.price.no is not None
    ]

    rows = []
    suspected_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    series_counts: Counter[str] = Counter()
    keyword_counts: Counter[str] = Counter()
    samples: Dict[str, List[ParsedMarket]] = defaultdict(list)

    for market in other:
        suspected, reason, hits = infer_suspected_category(market)
        suspected_counts[suspected] += 1
        reason_counts[reason] += 1
        series_counts[_series_prefix(market)] += 1
        keyword_counts.update(hits)
        if len(samples[suspected]) < sample_limit:
            samples[suspected].append(market)

        metadata = _raw_metadata(market)
        rows.append({
            "platform": market.platform,
            "source_id": market.source_id,
            "title": market.title,
            "market_type": market.market_type or "",
            "subtype": market.subtype or "",
            "tradeable": bool(
                market.price
                and market.price.yes is not None
                and market.price.no is not None
            ),
            "suspected_category": suspected,
            "diagnostic_reason": reason,
            "matched_signals": "; ".join(hits),
            "series_prefix": _series_prefix(market),
            "raw_metadata": json.dumps(metadata, ensure_ascii=False),
        })

    export_path = Path(export_dir)
    export_path.mkdir(parents=True, exist_ok=True)
    csv_path = export_path / f"{platform_name.lower()}_parser_other_diagnostics.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else [
            "platform", "source_id", "title", "market_type", "subtype",
            "tradeable", "suspected_category", "diagnostic_reason",
            "matched_signals", "series_prefix", "raw_metadata",
        ])
        writer.writeheader()
        writer.writerows(rows)

    print("\n" + "=" * 88)
    print(f"PARSER DIAGNOSTICS — {platform_name}")
    print("=" * 88)
    print(f"Total parsed markets: {len(markets)}")
    print(f"Category 'other': {len(other)}")
    print(f"Tradeable markets inside 'other': {len(tradeable_other)}")
    if markets:
        print(f"Other share: {len(other) / len(markets):.1%}")

    print("\nSuspected destination of 'other' markets:")
    for category, count in suspected_counts.most_common():
        print(f"  - {category}: {count}")

    print("\nTop Kalshi series/event prefixes among 'other':")
    for prefix, count in series_counts.most_common(20):
        print(f"  - {prefix}: {count}")

    print("\nMost frequent recognizable signals:")
    for signal, count in keyword_counts.most_common(25):
        print(f"  - {signal}: {count}")

    for category, category_samples in sorted(samples.items()):
        print(f"\nSamples suspected as {category} (up to {sample_limit}):")
        for index, market in enumerate(category_samples, 1):
            _, reason, hits = infer_suspected_category(market)
            title = market.title.replace("\n", " ")
            print(f"  {index}. {title[:220]}")
            print(f"     signals={hits or ['none']}")
            print(f"     reason={reason}")

    print(f"\nFull CSV exported to: {csv_path}")
    return csv_path


def run_parser_diagnostics(
    kalshi: Sequence[ParsedMarket],
    polymarket: Sequence[ParsedMarket],
    *,
    sample_limit: int = 20,
    export_dir: str = "exports",
) -> List[Path]:
    return [
        diagnose_other_markets(
            "Kalshi",
            kalshi,
            sample_limit=sample_limit,
            export_dir=export_dir,
        ),
        diagnose_other_markets(
            "Polymarket",
            polymarket,
            sample_limit=sample_limit,
            export_dir=export_dir,
        ),
    ]
