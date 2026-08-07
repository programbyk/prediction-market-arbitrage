from core.event_engine import EventEngine
from legacy.scanner_v6_1 import MarketPrice, ParsedMarket
from matcher.event_graph import event_graph_candidate_pairs

def pm(platform,sid,title,year=2026):
    return ParsedMarket(platform=platform,source_id=sid,title=title,raw={},price=MarketPrice(yes=.4,no=.6),category='politics',market_type='winner',year=year,party='democratic_party')

def test_country_scoped_parties():
    a=pm('kalshi','k','Will Democrats win All 4?'); a.raw={'ticker':'KXFOURSTATESEN-26NOV03'}
    b=pm('polymarket','p','Will the Swedish Social Democratic Party win the most seats in the 2026 Swedish parliamentary election?')
    e=EventEngine(); x=e.build(a); y=e.build(b)
    assert x and y and x.entity.key != y.entity.key
    assert x.canonical_country=='usa' and y.canonical_country=='sweden'

def test_candidate_vs_demographic_nominee():
    a=pm('kalshi','k2','Will Shawn Fain be the nominee for the Presidency for the Democratic party?',2028); a.raw={'ticker':'KXPRESNOMD-28'}
    b=pm('polymarket','p2','Will the 2028 Democratic Presidential nominee be a woman?',2028)
    e=EventEngine(); x=e.build(a); y=e.build(b)
    assert x and y and x.entity.key != y.entity.key
    assert x.proposition_subject_type=='candidate' and y.proposition_subject_type=='demographic'

def test_eala_pair_survives():
    a=ParsedMarket(platform='kalshi',source_id='k3',title="Will Alexandra Eala win the US Open Women's Singles?",raw={'ticker':'KXWTA-26USO-EALA'},price=MarketPrice(yes=.08,no=.93),category='sports',market_type='winner',sport='tennis',player='alexandra_eala',participant_type='participant')
    b=ParsedMarket(platform='polymarket',source_id='p3',title="Will Alexandra Eala win the 2026 Women's US Open?",raw={},price=MarketPrice(yes=.08,no=.92),category='sports',market_type='winner',sport='tennis',player='alexandra_eala',participant_type='participant',year=2026)
    assert len(event_graph_candidate_pairs([a],[b]))==1
