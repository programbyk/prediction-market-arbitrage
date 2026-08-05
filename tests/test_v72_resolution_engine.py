from core.event_engine import EventEngine
from core.resolution_engine import ResolutionEngine
from legacy.scanner_v6_1 import MarketPrice, ParsedMarket
from matcher.event_graph import event_graph_candidate_pairs


def crypto_market(
    source_id: str,
    platform: str,
    title: str,
    threshold: float | None = None,
):
    return ParsedMarket(
        platform=platform,
        source_id=source_id,
        title=title,
        raw={},
        price=MarketPrice(yes=0.4, no=0.6),
        category="crypto",
        market_type="unknown",
        asset="xrp",
        threshold=threshold,
        year=2026,
    )


def test_price_at_time_and_reach_before_are_different():
    snapshot = crypto_market(
        "k1",
        "kalshi",
        "Ripple price at Aug 5, 2026 at 5pm EDT? | $1.37991 or above",
        1.37991,
    )
    reach = crypto_market(
        "p1",
        "polymarket",
        "Will XRP reach $5.00 by December 31, 2026?",
        5.0,
    )

    engine = EventEngine()
    left = engine.build(snapshot)
    right = engine.build(reach)

    assert left is not None and right is not None
    assert left.resolution_type == "price_at_time"
    assert right.resolution_type == "any_time_before"
    assert event_graph_candidate_pairs([snapshot], [reach]) == []


def test_range_contract_is_not_threshold_contract():
    range_market = crypto_market(
        "k2",
        "kalshi",
        "Ripple price at Aug 5, 2026 at 5pm EDT? | $1.30 to $1.3199",
    )
    threshold_market = crypto_market(
        "p2",
        "polymarket",
        "Will XRP reach $1.30 by December 31, 2026?",
        1.30,
    )

    engine = ResolutionEngine()
    range_spec = engine.resolve(range_market)
    threshold_spec = engine.resolve(threshold_market)

    assert range_spec is not None
    assert range_spec.resolution_type == "bounded_range"
    assert range_spec.lower_bound == 1.30
    assert range_spec.upper_bound == 1.3199

    assert threshold_spec is not None
    assert threshold_spec.resolution_type == "any_time_before"
    assert event_graph_candidate_pairs([range_market], [threshold_market]) == []


def test_same_threshold_and_same_deadline_can_pair():
    kalshi = crypto_market(
        "k3",
        "kalshi",
        "Will XRP reach $5.00 by December 31, 2026?",
        5.0,
    )
    poly = crypto_market(
        "p3",
        "polymarket",
        "XRP to reach $5 before December 31, 2026?",
        5.0,
    )

    pairs = event_graph_candidate_pairs([kalshi], [poly])
    assert len(pairs) == 1
