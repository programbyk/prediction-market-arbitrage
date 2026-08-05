"""V7.2 Resolution Engine.

Separates *what* a market asks (intent) from *how it resolves*.

Examples:
- "XRP price at Aug 5, 2026 5pm" -> price_at_time
- "Will XRP reach $5 by Dec 31?" -> any_time_before
- "$1.30 to $1.32" -> bounded_range
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple

from models import ParsedMarket
from legacy.scanner_v6_1 import normalize_text


@dataclass(frozen=True)
class ResolutionSpec:
    resolution_type: str
    threshold: Optional[float] = None
    direction: Optional[str] = None
    resolution_time: Optional[str] = None
    deadline: Optional[str] = None
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None

    @property
    def key(self) -> str:
        parts = [
            self.resolution_type,
            str(self.threshold) if self.threshold is not None else "",
            self.direction or "",
            self.resolution_time or "",
            self.deadline or "",
            str(self.lower_bound) if self.lower_bound is not None else "",
            str(self.upper_bound) if self.upper_bound is not None else "",
        ]
        return "|".join(parts)


_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def _extract_date(text: str) -> Optional[str]:
    normalized = normalize_text(text)

    # Month Day, Year
    match = re.search(
        r"\b(" + "|".join(_MONTHS.keys()) + r")\s+(\d{1,2})(?:st|nd|rd|th)?"
        r"(?:\s*,?\s*(20\d{2}))?\b",
        normalized,
    )
    if match:
        month = _MONTHS[match.group(1)]
        day = int(match.group(2))
        year = int(match.group(3)) if match.group(3) else None
        if year:
            return f"{year:04d}-{month:02d}-{day:02d}"

    # YYYY-MM-DD
    match = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", normalized)
    if match:
        return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"

    # Dec 31 style with year elsewhere
    year_match = re.search(r"\b(20\d{2})\b", normalized)
    if year_match:
        year = int(year_match.group(1))
        month_day = re.search(
            r"\b(" + "|".join(_MONTHS.keys()) + r")\s+(\d{1,2})(?:st|nd|rd|th)?\b",
            normalized,
        )
        if month_day:
            month = _MONTHS[month_day.group(1)]
            day = int(month_day.group(2))
            return f"{year:04d}-{month:02d}-{day:02d}"

    return None


def _extract_time(text: str) -> Optional[str]:
    normalized = normalize_text(text)
    match = re.search(
        r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\s*(edt|est|utc|gmt|ct|et|pt)?\b",
        normalized,
    )
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    ampm = match.group(3)
    zone = (match.group(4) or "").upper()

    if ampm == "pm" and hour != 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0

    suffix = f" {zone}" if zone else ""
    return f"{hour:02d}:{minute:02d}{suffix}"


def _extract_range(text: str) -> Tuple[Optional[float], Optional[float]]:
    normalized = normalize_text(text)
    match = re.search(
        r"\$?\s*(\d+(?:\.\d+)?)\s*(?:to|-)\s*\$?\s*(\d+(?:\.\d+)?)",
        normalized,
    )
    if not match:
        return None, None
    return float(match.group(1)), float(match.group(2))


def _extract_threshold_and_direction(
    text: str,
) -> Tuple[Optional[float], Optional[str]]:
    normalized = normalize_text(text)

    patterns = (
        (r"\$?\s*(\d+(?:\.\d+)?)\s*(?:or )?(?:above|higher)", "over"),
        (r"\$?\s*(\d+(?:\.\d+)?)\s*(?:or )?(?:below|lower)", "under"),
        (r"(?:reach|exceed|above|over)\s*\$?\s*(\d+(?:\.\d+)?)", "over"),
        (r"(?:below|under)\s*\$?\s*(\d+(?:\.\d+)?)", "under"),
    )
    for pattern, direction in patterns:
        match = re.search(pattern, normalized)
        if match:
            return float(match.group(1)), direction

    return None, None


class ResolutionEngine:
    def resolve(self, market: ParsedMarket) -> Optional[ResolutionSpec]:
        title = market.title
        display_title = title.split("|", 1)[0].strip()
        normalized = normalize_text(title)

        lower, upper = _extract_range(title)
        threshold, parsed_direction = _extract_threshold_and_direction(title)
        direction = parsed_direction or market.direction

        date_value = _extract_date(title)
        time_value = _extract_time(title)
        timestamp = None
        if date_value and time_value:
            timestamp = f"{date_value}T{time_value}"
        elif date_value:
            timestamp = date_value

        # Range contracts must remain separate from binary threshold markets.
        if lower is not None and upper is not None:
            spec = ResolutionSpec(
                resolution_type="bounded_range",
                lower_bound=lower,
                upper_bound=upper,
                resolution_time=timestamp,
            )
            self._annotate(market, spec)
            return spec

        # Snapshot/closing price at a specific time.
        if re.search(
            r"\bprice at\b|\bat \d{1,2}(?::\d{2})?\s*(?:am|pm)\b"
            r"|\bclosing price\b|\bclose at\b",
            normalized,
        ):
            spec = ResolutionSpec(
                resolution_type="price_at_time",
                threshold=threshold or market.threshold,
                direction=direction,
                resolution_time=timestamp,
            )
            self._annotate(market, spec)
            return spec

        # Touch/reach before a deadline.
        if re.search(
            r"\b(?:reach|touch|hit|exceed)\b.*\b(?:by|before)\b",
            normalized,
        ):
            spec = ResolutionSpec(
                resolution_type="any_time_before",
                threshold=threshold or market.threshold,
                direction=direction or "over",
                deadline=timestamp,
            )
            self._annotate(market, spec)
            return spec

        # Above/below as of/on a date.
        if re.search(r"\b(?:above|below|over|under)\b", normalized):
            spec = ResolutionSpec(
                resolution_type="threshold_at_deadline"
                if timestamp
                else "threshold_generic",
                threshold=threshold or market.threshold,
                direction=direction,
                deadline=timestamp,
            )
            self._annotate(market, spec)
            return spec

        # Politics/sports/economy winner-style events.
        if market.market_intent:
            if market.market_intent.endswith("_winner") or market.market_intent in {
                "election_winner",
                "primary_winner",
                "match_winner",
                "series_winner",
                "map_winner",
                "division_winner",
                "conference_winner",
                "super_bowl_winner",
                "world_series_winner",
            }:
                spec = ResolutionSpec(
                    resolution_type="event_winner",
                    deadline=timestamp,
                )
                self._annotate(market, spec)
                return spec

        if market.market_intent:
            spec = ResolutionSpec(
                resolution_type="event_occurrence",
                deadline=timestamp,
            )
            self._annotate(market, spec)
            return spec

        return None

    @staticmethod
    def _annotate(market: ParsedMarket, spec: ResolutionSpec) -> None:
        market.resolution_type = spec.resolution_type
        market.resolution_time = spec.resolution_time
        market.deadline = spec.deadline
        market.lower_bound = spec.lower_bound
        market.upper_bound = spec.upper_bound
        if spec.threshold is not None:
            market.threshold = spec.threshold
        if spec.direction:
            market.direction = spec.direction
