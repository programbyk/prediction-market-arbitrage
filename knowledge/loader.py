"""Load and resolve canonical concepts from JSON knowledge files."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from utils.helpers import normalize_text


@dataclass(frozen=True)
class SportsIdentity:
    sport: str
    league: str
    competition: str


class KnowledgeBase:
    def __init__(self, directory: Optional[Path] = None) -> None:
        self.directory = directory or Path(__file__).resolve().parent
        self.sports = self._load("sports.json")
        self.politics = self._load("politics.json")
        self.crypto = self._load("crypto.json")
        self.economy = self._load("economy.json")

        self._sports_aliases = self._build_sports_aliases()
        self._generic_indexes = {
            "political_office": self._build_alias_index(self.politics.get("offices", {})),
            "political_stage": self._build_alias_index(self.politics.get("stages", {})),
            "crypto_asset": self._build_alias_index(self.crypto.get("assets", {})),
            "economy_metric": self._build_alias_index(self.economy.get("metrics", {})),
            "economy_comparison": self._build_alias_index(
                self.economy.get("comparisons", {})
            ),
        }

    def _load(self, filename: str) -> Dict[str, Any]:
        path = self.directory / filename
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def _build_alias_index(groups: Dict[str, Any]) -> Dict[str, str]:
        index: Dict[str, str] = {}
        for canonical, aliases in groups.items():
            for alias in [canonical, *aliases]:
                index[normalize_text(alias)] = canonical
        return index

    def _build_sports_aliases(self) -> Dict[str, SportsIdentity]:
        index: Dict[str, SportsIdentity] = {}
        for canonical, data in self.sports.get("competitions", {}).items():
            identity = SportsIdentity(
                sport=data["sport"],
                league=data["league"],
                competition=canonical,
            )
            for alias in [canonical.replace("_", " "), *data.get("aliases", [])]:
                index[normalize_text(alias)] = identity
        return index

    @staticmethod
    def _longest_match(text: str, index: Dict[str, Any]) -> Optional[Any]:
        normalized = normalize_text(text)
        matches = [
            (alias, value)
            for alias, value in index.items()
            if alias and alias in normalized
        ]
        if not matches:
            return None
        return max(matches, key=lambda item: len(item[0]))[1]

    def resolve_sports_identity(self, text: str) -> Optional[SportsIdentity]:
        return self._longest_match(text, self._sports_aliases)

    def resolve(self, concept_type: str, text: str) -> Optional[str]:
        if concept_type not in self._generic_indexes:
            raise KeyError(f"Unknown concept type: {concept_type}")
        return self._longest_match(text, self._generic_indexes[concept_type])


@lru_cache(maxsize=1)
def get_knowledge_base() -> KnowledgeBase:
    return KnowledgeBase()


__all__ = ["KnowledgeBase", "SportsIdentity", "get_knowledge_base"]
