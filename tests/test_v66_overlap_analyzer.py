from legacy.scanner_v6_1 import MarketPrice, ParsedMarket
from matcher.overlap_analyzer import generate_overlap_candidates


def make_market(platform: str, source_id: str, player: str):
    return ParsedMarket(
        platform=platform,
        source_id=source_id,
        title=f"Will {player} win the 2026 Home Run Derby?",
        raw={},
        price=MarketPrice(yes=0.4, no=0.6),
        category="sports",
        market_type="winner",
        sport="baseball",
        league="mlb",
        competition="home_run_derby",
        event_kind="championship_winner",
        participant_type="player",
        player=player,
        year=2026,
    )


def test_same_player_event_is_high_overlap():
    results = generate_overlap_candidates(
        [make_market("kalshi", "k1", "kyle_schwarber")],
        [make_market("polymarket", "p1", "kyle_schwarber")],
        min_score=40,
        top_per_kalshi=5,
    )
    assert len(results) == 1
    assert results[0].score >= 80


def test_different_player_is_not_kept_at_high_threshold():
    results = generate_overlap_candidates(
        [make_market("kalshi", "k2", "kyle_schwarber")],
        [make_market("polymarket", "p2", "aaron_judge")],
        min_score=95,
        top_per_kalshi=5,
    )
    assert results == []
