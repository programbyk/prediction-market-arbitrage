"""V7.3 canonical identity enrichment.

Uses platform metadata and human-facing text to fill stable identifiers before
EventObjects are created. This is especially important for Kalshi tickers such
as ``KXWTA-26USO`` where the year and tournament are encoded structurally.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from models import ParsedMarket
from legacy.scanner_v6_1 import normalize_text


@dataclass(frozen=True)
class CanonicalIdentity:
    year: Optional[int]
    competition: Optional[str]
    participant_type: Optional[str]


def infer_year_from_metadata(market: ParsedMarket) -> Optional[int]:
    if market.year:
        return market.year

    raw = market.raw or {}
    values = [
        str(raw.get("ticker") or ""),
        str(raw.get("event_ticker") or ""),
        str(raw.get("series_ticker") or ""),
        market.source_id or "",
        market.title or "",
    ]

    # Kalshi examples: KXWTA-26USO, KXMLBHRDERBY-26
    for value in values:
        match = re.search(r"(?:^|-)(2[4-9])(?:[A-Z0-9]|-|$)", value.upper())
        if match:
            return 2000 + int(match.group(1))

    # Generic four-digit year fallback.
    for value in values:
        match = re.search(r"\b(20\d{2})\b", value)
        if match:
            return int(match.group(1))

    return None


def infer_competition(market: ParsedMarket) -> Optional[str]:
    if market.competition:
        return market.competition

    text = normalize_text(market.title)
    raw = market.raw or {}
    metadata = " ".join(
        str(raw.get(field) or "")
        for field in ("ticker", "event_ticker", "series_ticker")
    ).upper()

    # Tennis Grand Slams
    if "us open" in text or "USO" in metadata:
        if any(token in text for token in ("women", "women s", "wta")) or "WTA" in metadata:
            return "us_open_womens_singles"
        if any(token in text for token in ("men", "men s", "atp")) or "ATP" in metadata:
            return "us_open_mens_singles"
        return "us_open"

    if "australian open" in text or "AO" in metadata:
        if "women" in text or "WTA" in metadata:
            return "australian_open_womens_singles"
        if "men" in text or "ATP" in metadata:
            return "australian_open_mens_singles"
        return "australian_open"

    if "wimbledon" in text:
        if "women" in text or "WTA" in metadata:
            return "wimbledon_womens_singles"
        if "men" in text or "ATP" in metadata:
            return "wimbledon_mens_singles"
        return "wimbledon"

    if "french open" in text or "roland garros" in text:
        if "women" in text or "WTA" in metadata:
            return "french_open_womens_singles"
        if "men" in text or "ATP" in metadata:
            return "french_open_mens_singles"
        return "french_open"

    return None


def enrich_canonical_identity(market: ParsedMarket) -> CanonicalIdentity:
    year = infer_year_from_metadata(market)
    competition = infer_competition(market)

    if year and not market.year:
        market.year = year
        market.parser_notes.append("year_inferred_from_metadata")

    if competition and not market.competition:
        market.competition = competition
        market.subtype = competition
        market.parser_notes.append("competition_inferred_canonically")

    participant_type = market.participant_type
    if market.category == "sports" and market.player and not participant_type:
        participant_type = "player"
        market.participant_type = participant_type

    return CanonicalIdentity(
        year=market.year,
        competition=market.competition,
        participant_type=market.participant_type,
    )
