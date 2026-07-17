from legacy.scanner_v6_1 import (
    MarketPrice,
    ParsedMarket,
    candidate_compatible,
    detect_sports_identity,
    parse_market,
)


def test_fifa_person_name_does_not_force_world_cup():
    sport, league, competition = detect_sports_identity(
        "Will Fifa Laopakdee win the 2nd round 3-ball matchup? | KXPGA3BALL"
    )
    assert sport == "golf"
    assert league == "pga"
    assert competition == "golf_round_matchup"


def test_world_cup_team_and_golf_player_are_not_candidates():
    golf = ParsedMarket(
        platform="kalshi",
        source_id="k1",
        title="Fifa Laopakdee 3-ball matchup",
        raw={},
        price=MarketPrice(yes=0.4, no=0.6),
        category="sports",
        market_type="winner",
        sport="golf",
        league="pga",
        competition="golf_round_matchup",
        participant_type="player",
        player="fifa_laopakdee",
        year=2026,
    )
    soccer = ParsedMarket(
        platform="polymarket",
        source_id="p1",
        title="Europe UEFA win FIFA World Cup",
        raw={},
        price=MarketPrice(yes=0.4, no=0.6),
        category="sports",
        market_type="winner",
        sport="soccer",
        league="fifa",
        competition="world_cup",
        participant_type="region",
        player="europe_uefa",
        year=2026,
    )
    assert candidate_compatible(golf, soccer) is False


def test_same_event_identity_remains_candidate():
    first = ParsedMarket(
        platform="kalshi",
        source_id="k2",
        title="Kyle Schwarber Home Run Derby",
        raw={},
        price=MarketPrice(yes=0.4, no=0.6),
        category="sports",
        market_type="winner",
        sport="baseball",
        league="mlb",
        competition="home_run_derby",
        participant_type="player",
        player="kyle_schwarber",
        year=2026,
    )
    second = ParsedMarket(
        platform="polymarket",
        source_id="p2",
        title="Kyle Schwarber HR Derby",
        raw={},
        price=MarketPrice(yes=0.4, no=0.6),
        category="sports",
        market_type="winner",
        sport="baseball",
        league="mlb",
        competition="home_run_derby",
        participant_type="player",
        player="kyle_schwarber",
        year=2026,
    )
    assert candidate_compatible(first, second) is True
