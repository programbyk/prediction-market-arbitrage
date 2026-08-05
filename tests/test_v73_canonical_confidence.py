from core.event_engine import EventEngine
from legacy.scanner_v6_1 import MarketPrice, ParsedMarket
from matcher.confidence_engine import semantic_confidence
from matcher.event_graph import event_graph_candidate_pairs


def kalshi_eala():
    return ParsedMarket(
        platform="kalshi",
        source_id="KXWTA-26USO-EALA",
        title=(
            "Will Alexandra Eala win the US Open Women's Singles? | "
            "Alexandra Eala | Alexandra Eala | KXWTA-26USO"
        ),
        raw={
            "ticker": "KXWTA-26USO-EALA",
            "event_ticker": "KXWTA-26USO",
            "series_ticker": "KXWTA",
        },
        price=MarketPrice(yes=0.08, no=0.93),
        category="sports",
        market_type="winner",
        sport="tennis",
        player="alexandra_eala",
        participant_type="participant",
    )


def poly_eala():
    return ParsedMarket(
        platform="polymarket",
        source_id="poly-eala-uso-2026",
        title="Will Alexandra Eala win the 2026 Women’s US Open?",
        raw={},
        price=MarketPrice(yes=0.0395, no=0.9605),
        category="sports",
        market_type="winner",
        sport="tennis",
        player="alexandra_eala",
        participant_type="participant",
        year=2026,
    )


def test_kalshi_ticker_infers_year_and_tournament():
    market = kalshi_eala()
    event = EventEngine().build(market)

    assert event is not None
    assert market.year == 2026
    assert market.competition == "us_open_womens_singles"
    assert event.resolution_type == "event_winner"


def test_first_real_match_becomes_accepted():
    kalshi = kalshi_eala()
    poly = poly_eala()

    pairs = event_graph_candidate_pairs([kalshi], [poly])
    assert len(pairs) == 1

    engine = EventEngine()
    kalshi_event = engine.build(kalshi)
    poly_event = engine.build(poly)

    assert kalshi_event is not None and poly_event is not None
    assert kalshi_event.entity.key == poly_event.entity.key
    assert kalshi_event.competition == poly_event.competition
    assert kalshi_event.year == poly_event.year == 2026

    result = semantic_confidence(
        kalshi,
        poly,
        kalshi_event,
        poly_event,
        pairs[0][2],
    )
    assert result.accepted is True
    assert result.confidence >= 90


def test_different_tournament_is_rejected():
    kalshi = kalshi_eala()
    poly = poly_eala()
    poly.title = "Will Alexandra Eala win the 2026 Women's Australian Open?"

    engine = EventEngine()
    left = engine.build(kalshi)
    right = engine.build(poly)

    assert left is not None and right is not None
    result = semantic_confidence(kalshi, poly, left, right, 1)
    assert result.accepted is False
    assert any("competition mismatch" in item for item in result.rejects)
