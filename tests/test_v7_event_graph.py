from legacy.scanner_v6_1 import MarketPrice, ParsedMarket
from matcher.event_graph import (
    annotate_event_objects,
    event_graph_candidate_pairs,
    infer_market_intent,
)


def sports_market(source_id: str, platform: str, title: str, team: str):
    return ParsedMarket(
        platform=platform,
        source_id=source_id,
        title=title,
        raw={},
        price=MarketPrice(yes=0.4, no=0.6),
        category="sports",
        market_type="event",
        sport="american_football",
        league="nfl",
        teams=(team,),
        participant_type="team",
        year=2026,
    )


def test_same_team_different_intent_not_grouped():
    host = sports_market(
        "k1",
        "kalshi",
        "Will New England host a playoff game in 2026?",
        "new_england_patriots",
    )
    sacks = sports_market(
        "p1",
        "polymarket",
        "Will New England finish with the most sacks in 2026?",
        "new_england_patriots",
    )

    annotate_event_objects([host, sacks])

    assert host.market_intent == "playoff_host"
    assert sacks.market_intent == "most_sacks"
    assert event_graph_candidate_pairs([host], [sacks]) == []


def test_one_kalshi_market_can_have_multiple_poly_options():
    kalshi = sports_market(
        "k2",
        "kalshi",
        "Will New England host a playoff game in 2026?",
        "new_england_patriots",
    )
    poly_one = sports_market(
        "p2",
        "polymarket",
        "Will New England host a playoff game in the 2026 postseason?",
        "new_england_patriots",
    )
    poly_two = sports_market(
        "p3",
        "polymarket",
        "New England to host a playoff game in 2026?",
        "new_england_patriots",
    )

    pairs = event_graph_candidate_pairs(
        [kalshi],
        [poly_one, poly_two],
    )

    assert len(pairs) == 2
    assert {pair[1].source_id for pair in pairs} == {"p2", "p3"}
