"""Application orchestration for the modular scanner."""
from datetime import datetime, timezone

from arbitrage.calculator import calculate_arbitrage
from fetchers.kalshi import fetch_kalshi_markets
from fetchers.polymarket import fetch_polymarket_markets
from legacy.scanner_v6_1 import (
    REVIEW_MIN_CONFIDENCE,
    MIN_MATCH_CONFIDENCE,
    SHOW_TOP_CANDIDATES,
    SHOW_TOP_MATCHES,
    print_arbitrage,
    print_market_summary,
    print_match,
)
from matcher.matcher import find_matches
from parsers.parser import parse_market_collection

def run_scan(use_cache: bool = True) -> None:
    print("Prediction Market Arbitrage Scanner")
    print(f"Started: {datetime.now(timezone.utc).isoformat()}")
    print("Mode: modular V6.1 compatibility architecture")

    kalshi_raw = fetch_kalshi_markets(use_cache=use_cache)
    poly_raw = fetch_polymarket_markets(use_cache=use_cache)

    kalshi = parse_market_collection("kalshi", kalshi_raw)
    poly = parse_market_collection("polymarket", poly_raw)

    print_market_summary("Kalshi", kalshi)
    print_market_summary("Polymarket", poly)

    matches, review_matches, candidates = find_matches(kalshi, poly)

    print(f"\nAccepted matches: {len(matches)}")
    for i, match in enumerate(matches[:SHOW_TOP_MATCHES], 1):
        print_match(match, i)

    print(
        f"\nReview matches "
        f"({REVIEW_MIN_CONFIDENCE}-{MIN_MATCH_CONFIDENCE - 1}): "
        f"{len(review_matches)}"
    )
    for i, match in enumerate(review_matches[:SHOW_TOP_CANDIDATES], 1):
        print_match(match, i, label="REVIEW")

    if not matches and not review_matches and candidates:
        print(
            f"\nNo accepted or review matches. Top "
            f"{min(SHOW_TOP_CANDIDATES, len(candidates))} "
            f"rejected candidates for debugging:"
        )
        for i, candidate in enumerate(candidates[:SHOW_TOP_CANDIDATES], 1):
            print_match(candidate, i, label="REJECTED CANDIDATE")

    opportunities = calculate_arbitrage(matches)
    print(f"\nArbitrage opportunities: {len(opportunities)}")
    for i, opportunity in enumerate(opportunities[:20], 1):
        print_arbitrage(opportunity, i)

    if not opportunities:
        print("\nNo gross arbitrage above threshold found in this run.")
