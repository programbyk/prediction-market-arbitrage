from core.entity_engine import EntityEngine
from core.intent_engine import IntentEngine
from core.event_engine import EventEngine
from legacy.scanner_v6_1 import MarketPrice, ParsedMarket
from matcher.event_graph import event_graph_candidate_pairs


def sports_market(source_id: str, platform: str, title: str):
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
        teams=("new_england_patriots",),
        participant_type="team",
        year=2026,
    )


def test_entity_engine_extracts_team():
    market = sports_market(
        "k1",
        "kalshi",
        "Will New England host a playoff game in 2026?",
    )
    entity = EntityEngine().resolve(market)
    assert entity is not None
    assert entity.key == "teams:new_england_patriots"


def test_intent_engine_uses_json_catalog():
    engine = IntentEngine()
    market = sports_market(
        "k2",
        "kalshi",
        "Will New England host a playoff game in 2026?",
    )
    assert engine.resolve(market) == "playoff_host"


def test_different_intents_do_not_share_graph_node():
    host = sports_market(
        "k3",
        "kalshi",
        "Will New England host a playoff game in 2026?",
    )
    sacks = sports_market(
        "p3",
        "polymarket",
        "Will New England finish with the most sacks in 2026?",
    )
    assert event_graph_candidate_pairs([host], [sacks]) == []


def test_one_kalshi_market_matches_multiple_poly_options():
    kalshi = sports_market(
        "k4",
        "kalshi",
        "Will New England host a playoff game in 2026?",
    )
    poly_one = sports_market(
        "p4",
        "polymarket",
        "Will New England host a playoff game in 2026?",
    )
    poly_two = sports_market(
        "p5",
        "polymarket",
        "New England to host playoff game in 2026?",
    )
    pairs = event_graph_candidate_pairs(
        [kalshi],
        [poly_one, poly_two],
    )
    assert len(pairs) == 2
