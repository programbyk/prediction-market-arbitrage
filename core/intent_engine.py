"""Resolve market intent using JSON knowledge files."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

from models import ParsedMarket
from legacy.scanner_v6_1 import normalize_text


class IntentEngine:
    def __init__(self, directory: Optional[Path] = None) -> None:
        self.directory = (
            directory
            or Path(__file__).resolve().parents[1] / "knowledge" / "intents"
        )
        self.catalogs = {
            category: self._load(f"{category}.json")
            for category in ("sports", "politics", "crypto", "economy")
        }
        self._compiled = {
            category: self._compile_catalog(catalog)
            for category, catalog in self.catalogs.items()
        }

    def _load(self, filename: str) -> Dict[str, list[str]]:
        path = self.directory / filename
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def _compile_catalog(catalog: Dict[str, list[str]]):
        compiled = []
        for canonical, aliases in catalog.items():
            for alias in aliases:
                normalized = normalize_text(alias)
                pattern = (
                    r"(?<![a-z0-9])"
                    + re.escape(normalized).replace(r"\ ", r"\s+")
                    + r"(?![a-z0-9])"
                )
                compiled.append(
                    (len(normalized), canonical, re.compile(pattern))
                )
        compiled.sort(key=lambda item: item[0], reverse=True)
        return compiled

    def resolve_text(self, category: str, text: str) -> Optional[str]:
        normalized = normalize_text(text)
        for _, canonical, pattern in self._compiled.get(category, []):
            if pattern.search(normalized):
                return canonical
        return None

    def resolve(self, market: ParsedMarket) -> Optional[str]:
        display_title = market.title.split("|", 1)[0].strip()
        resolved = self.resolve_text(market.category, display_title)
        if resolved:
            return resolved

        # Structured fallbacks preserve coverage while JSON catalogs grow.
        if market.category == "sports":
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
            if market.market_type == "winner":
                return "election_winner"

        elif market.category == "crypto":
            if market.threshold is not None:
                return "price_threshold"

        elif market.category == "economy":
            if market.metric:
                return f"{market.metric}_threshold"

        return None


@lru_cache(maxsize=1)
def get_intent_engine() -> IntentEngine:
    return IntentEngine()
