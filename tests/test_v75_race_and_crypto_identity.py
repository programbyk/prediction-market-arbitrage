from core.event_engine import EventEngine
from legacy.scanner_v6_1 import MarketPrice, ParsedMarket
from matcher.event_graph import event_graph_candidate_pairs

def pm(platform, sid, title, year=None):
    return ParsedMarket(
        platform=platform, source_id=sid, title=title, raw={},
        price=MarketPrice(yes=0.4, no=0.6),
        category="politics", market_type="winner", year=year,
        country="usa", canonical_country="usa",
        party="republican_party", canonical_party="republican_party",
    )

def test_different_candidate_and_district_do_not_pair():
    k = pm("kalshi", "k1",
        "Will it be confirmed that Tim Moffitt is the NC-11 Republican nominee on Aug 11, 2026?",
        2026)
    p = pm("polymarket", "p1",
        "Will Catalina Lauf be the Republican nominee for FL-19?")
    engine = EventEngine()
    a, b = engine.build(k), engine.build(p)
    assert a and b
    assert a.canonical_candidate == "tim_moffitt"
    assert b.canonical_candidate == "catalina_lauf"
    assert a.district == 11 and b.district == 19
    assert event_graph_candidate_pairs([k], [p]) == []

def test_same_candidate_same_race_can_pair():
    k = pm("kalshi", "k2",
        "Will it be confirmed that Tim Moffitt is the NC-11 Republican nominee on Aug 11, 2026?",
        2026)
    p = pm("polymarket", "p2",
        "Will Tim Moffitt be the Republican nominee for NC-11 in 2026?", 2026)
    assert len(event_graph_candidate_pairs([k], [p])) == 1

def test_crypto_contract_types():
    snapshot = ParsedMarket(
        platform="kalshi", source_id="c1",
        title="Ripple price at Aug 5, 2026 at 5pm EDT? | $1.37 or above",
        raw={}, price=MarketPrice(yes=0.4, no=0.6),
        category="crypto", market_type="unknown", asset="xrp", year=2026,
    )
    reach = ParsedMarket(
        platform="polymarket", source_id="c2",
        title="Will XRP reach $5 by December 31, 2026?",
        raw={}, price=MarketPrice(yes=0.4, no=0.6),
        category="crypto", market_type="unknown", asset="xrp", year=2026,
    )
    engine = EventEngine()
    a, b = engine.build(snapshot), engine.build(reach)
    assert a and b
    assert a.contract_type == "price_snapshot"
    assert b.contract_type == "price_reach"
