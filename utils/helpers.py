"""Independent utility functions for text and numeric normalization.

Stage 2.1 migration:
These helpers no longer depend on the legacy scanner. The legacy engine imports
them temporarily so behavior remains stable while the project is split safely.
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, List, Optional, Set


STOPWORDS = {
    "will", "the", "and", "that", "this", "with", "from", "have", "has",
    "over", "under", "above", "below", "before", "after", "market", "yes",
    "no", "into", "than", "more", "less", "election", "race", "win", "wins",
    "winner", "party", "candidate", "2024", "2025", "2026", "2027", "2028",
    "2029", "2030",
}


def bounded_alt(*alternatives: str) -> str:
    return r"\b(?:" + "|".join(alternatives) + r")\b"


def normalize_text(text: str) -> str:
    text = text or ""
    text = text.replace("\u2019", "'").replace("\u2013", "-").replace("\u2014", "-")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace(",", "")
    text = re.sub(r"[^a-z0-9$%\.\-\s']+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def words(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9']+", normalize_text(text))


def important_words(text: str) -> Set[str]:
    return {word for word in words(text) if len(word) > 3 and word not in STOPWORDS}


def parse_year(text: str) -> Optional[int]:
    years = re.findall(r"\b(20[2-4][0-9])\b", text)
    return int(years[0]) if years else None


def apply_magnitude(value: float, suffix: Optional[str]) -> float:
    if suffix == "k":
        return value * 1_000
    if suffix == "m":
        return value * 1_000_000
    if suffix == "b":
        return value * 1_000_000_000
    return value


def parse_number(text: str) -> Optional[float]:
    normalized = normalize_text(text)

    dollar = re.search(r"\$\s?(\d+(?:\.\d+)?)\s?(k|m|b)?\b", normalized)
    if dollar:
        return apply_magnitude(float(dollar.group(1)), dollar.group(2))

    percent = re.search(r"\b(\d+(?:\.\d+)?)\s?%", normalized)
    if percent:
        return float(percent.group(1))

    suffixed = re.search(r"\b(\d+(?:\.\d+)?)\s?(k|m|b)\b", normalized)
    if suffixed:
        return apply_magnitude(float(suffixed.group(1)), suffixed.group(2))

    for match in re.finditer(r"\b(\d+(?:\.\d+)?)\b", normalized):
        token = match.group(1)
        if re.match(r"^20[2-4][0-9]$", token):
            continue
        return float(token)

    return None


def safe_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def parse_json_maybe(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return value


__all__ = [
    "STOPWORDS",
    "apply_magnitude",
    "bounded_alt",
    "important_words",
    "normalize_text",
    "parse_json_maybe",
    "parse_number",
    "parse_year",
    "safe_float",
    "words",
]
