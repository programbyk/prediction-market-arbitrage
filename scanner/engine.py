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
from matcher.event_graph import find_event_graph_matches, export_event_graph
from parsers.parser import parse_market_collection
from parsers.diagnostics import run_parser_diagnostics
from matcher.overlap_analyzer import analyze_overlap


def print_cross_platform_coverage(kalshi, poly) -> None:
    """Print category counts before matching."""
    categories = sorted(
        {market.category for market in kalshi}
        | {market.category for market in poly}
    )

    print("\nCross-platform category coverage:")
    for category in categories:
        kalshi_count = sum(1 for market in kalshi if market.category == category)
        poly_count = sum(1 for market in poly if market.category == category)
        possible_overlap = min(kalshi_count, poly_count)
        print(
            f"  - {category}: Kalshi={kalshi_count}, "
            f"Polymarket={poly_count}, theoretical max overlap={possible_overlap}"
        )


def run_scan(
    use_cache: bool = True,
    *,
    diagnose_parser: bool = False,
    diagnostic_limit: int = 15,
    diagnostic_export_dir: str = "exports",
    analyze_overlap_mode: bool = False,
    overlap_min_score: int = 45,
    overlap_top_per_market: int = 5,
    overlap_samples: int = 20,
    legacy_matcher: bool = False,
) -> None:
    print("Prediction Market Arbitrage Scanner")
    print(f"Started: {datetime.now(timezone.utc).isoformat()}")
    if analyze_overlap_mode:
        print("Mode: V6.6 cross-platform overlap analyzer")
    elif diagnose_parser:
        print("Mode: V6.5 parser diagnostics")
    elif legacy_matcher:
        print("Mode: legacy strict matcher")
    else:
        print("Mode: V7 Event Graph Engine")

    kalshi_raw = fetch_kalshi_markets(use_cache=use_cache)
    poly_raw = fetch_polymarket_markets(use_cache=use_cache)

    kalshi = parse_market_collection("kalshi", kalshi_raw)
    poly = parse_market_collection("polymarket", poly_raw)

    print_market_summary("Kalshi", kalshi)
    print_market_summary("Polymarket", poly)
    print_cross_platform_coverage(kalshi, poly)

    if diagnose_parser:
        run_parser_diagnostics(
            kalshi,
            poly,
            sample_limit=max(1, diagnostic_limit),
            export_dir=diagnostic_export_dir,
        )
        print("\nParser diagnosis complete. Matching was skipped.")
        return

    if analyze_overlap_mode:
        analyze_overlap(
            kalshi,
            poly,
            min_score=max(0, min(100, overlap_min_score)),
            top_per_kalshi=max(1, overlap_top_per_market),
            sample_limit=max(1, overlap_samples),
            export_dir=diagnostic_export_dir,
        )
        print("\nOverlap analysis complete. Strict matching was skipped.")
        return

    if legacy_matcher:
        matches, review_matches, candidates = find_matches(kalshi, poly)
    else:
        graph_path = export_event_graph(
            kalshi,
            poly,
            export_dir=diagnostic_export_dir,
        )
        print(f"[EventGraph] Nodes exported to: {graph_path}")
        matches, review_matches, candidates = find_event_graph_matches(
            kalshi,
            poly,
        )

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
