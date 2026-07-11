#!/usr/bin/env python3
"""Command-line entry point."""
import argparse

import legacy.scanner_v6_1 as legacy_config
from scanner.engine import run_scan

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prediction-market arbitrage scanner for Kalshi + Polymarket."
    )
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument(
        "--min-confidence",
        type=int,
        default=legacy_config.MIN_MATCH_CONFIDENCE,
    )
    parser.add_argument(
        "--review-confidence",
        type=int,
        default=legacy_config.REVIEW_MIN_CONFIDENCE,
    )
    parser.add_argument(
        "--min-profit",
        type=float,
        default=legacy_config.MIN_ARBITRAGE_PROFIT,
    )
    parser.add_argument(
        "--show-candidates",
        type=int,
        default=legacy_config.SHOW_TOP_CANDIDATES,
    )
    parser.add_argument("--debug", action="store_true")
    return parser

def main() -> None:
    args = build_arg_parser().parse_args()

    # Update the source-of-truth module used by all compatibility adapters.
    legacy_config.MIN_MATCH_CONFIDENCE = args.min_confidence
    legacy_config.REVIEW_MIN_CONFIDENCE = args.review_confidence
    legacy_config.MIN_ARBITRAGE_PROFIT = args.min_profit
    legacy_config.SHOW_TOP_CANDIDATES = args.show_candidates
    legacy_config.DEBUG = args.debug

    run_scan(use_cache=not args.no_cache)

if __name__ == "__main__":
    main()
