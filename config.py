"""Runtime configuration facade.

Values currently come from the tested V6.1 engine. This keeps one source
of truth while the implementation is migrated module by module.
"""
from legacy.scanner_v6_1 import (
    CACHE_DIR,
    CACHE_TTL_SECONDS,
    DEBUG,
    KALSHI_API_URL,
    KALSHI_LIMIT,
    KALSHI_MAX_PAGES,
    MAX_RETRIES,
    MIN_ARBITRAGE_PROFIT,
    MIN_MATCH_CONFIDENCE,
    POLYMARKET_API_URL,
    POLY_LIMIT,
    POLY_MAX_PAGES,
    REQUEST_TIMEOUT,
    RETRY_BACKOFF_BASE,
    REVIEW_MIN_CONFIDENCE,
    SHOW_TOP_CANDIDATES,
    SHOW_TOP_MATCHES,
)

__all__ = [name for name in globals() if name.isupper()]
