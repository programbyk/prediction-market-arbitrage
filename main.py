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
    parser.add_argument(
        "--diagnose-parser",
        action="store_true",
        help="Analyze markets classified as 'other', export CSV reports, and exit.",
    )
    parser.add_argument(
        "--diagnostic-limit",
        type=int,
        default=15,
        help="Number of sample markets printed per suspected category.",
    )
    parser.add_argument(
        "--diagnostic-export-dir",
        default="exports",
        help="Directory for parser diagnostic CSV files.",
    )
    parser.add_argument(
        "--analyze-overlap",
        action="store_true",
        help="Generate broad Kalshi/Polymarket overlap reports and exit.",
    )
    parser.add_argument(
        "--overlap-min-score",
        type=int,
        default=45,
        help="Minimum broad overlap score, 0-100.",
    )
    parser.add_argument(
        "--overlap-top-per-market",
        type=int,
        default=5,
        help="Maximum Polymarket candidates retained per Kalshi market.",
    )
    parser.add_argument(
        "--overlap-samples",
        type=int,
        default=20,
        help="Examples printed per category.",
    )
    parser.add_argument(
        "--legacy-matcher",
        action="store_true",
        help="Use the pre-V7 candidate matcher instead of the Event Graph Engine.",
    )
    return parser

def main() -> None:
    args = build_arg_parser().parse_args()

    # Update the source-of-truth module used by all compatibility adapters.
    legacy_config.MIN_MATCH_CONFIDENCE = args.min_confidence
    legacy_config.REVIEW_MIN_CONFIDENCE = args.review_confidence
    legacy_config.MIN_ARBITRAGE_PROFIT = args.min_profit
    legacy_config.SHOW_TOP_CANDIDATES = args.show_candidates
    legacy_config.DEBUG = args.debug

    run_scan(
        use_cache=not args.no_cache,
        diagnose_parser=args.diagnose_parser,
        diagnostic_limit=args.diagnostic_limit,
        diagnostic_export_dir=args.diagnostic_export_dir,
        analyze_overlap_mode=args.analyze_overlap,
        overlap_min_score=args.overlap_min_score,
        overlap_top_per_market=args.overlap_top_per_market,
        overlap_samples=args.overlap_samples,
        legacy_matcher=args.legacy_matcher,
    )

if __name__ == "__main__":
    main()
