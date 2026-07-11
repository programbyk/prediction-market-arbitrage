"""Kalshi market downloader."""
from typing import Any, Dict, List
from legacy.scanner_v6_1 import fetch_kalshi_markets as _fetch

def fetch_kalshi_markets(use_cache: bool = True) -> List[Dict[str, Any]]:
    return _fetch(use_cache=use_cache)

__all__ = ["fetch_kalshi_markets"]
