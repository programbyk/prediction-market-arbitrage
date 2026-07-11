"""Candidate generation and structured market matching."""
from typing import List, Sequence, Tuple
from legacy.scanner_v6_1 import (
    candidate_pairs,
    compare_markets,
    find_matches,
    is_review_candidate,
)
from models import MatchResult, ParsedMarket

__all__ = [
    "candidate_pairs",
    "compare_markets",
    "find_matches",
    "is_review_candidate",
    "MatchResult",
    "ParsedMarket",
]
