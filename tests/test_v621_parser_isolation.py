from knowledge.loader import KnowledgeBase
from legacy.scanner_v6_1 import detect_sports_identity, parse_market


def test_ucl_does_not_match_inside_nuclear():
    kb = KnowledgeBase()
    assert kb.resolve_sports_identity("Iran nuclear test before 2027?") is None


def test_fifa_does_not_match_as_part_of_person_name():
    sport, league, competition = detect_sports_identity(
        "Will Fifa Laopakdee win the 2nd round 3-ball matchup?"
    )
    assert sport == "golf"
    assert league == "pga"
    assert competition == "golf_round_matchup"


def test_political_nuclear_market_is_not_sports():
    market = parse_market(
        "polymarket",
        {
            "id": "iran-test",
            "question": "Iran nuclear test before 2027?",
            "outcomes": ["Yes", "No"],
            "outcomePrices": ["0.05", "0.95"],
        },
    )
    assert market.category != "sports"
    assert market.sport is None
    assert market.competition is None


def test_gop_nuclear_option_is_not_champions_league():
    market = parse_market(
        "polymarket",
        {
            "id": "gop-filibuster",
            "question": 'GOP uses "nuclear option" to break filibuster by December 31, 2026?',
            "outcomes": ["Yes", "No"],
            "outcomePrices": ["0.14", "0.86"],
        },
    )
    assert market.category != "sports"
    assert market.league is None
    assert market.competition is None


def test_real_ucl_alias_still_matches():
    identity = KnowledgeBase().resolve_sports_identity(
        "Will Real Madrid win the UCL?"
    )
    assert identity is not None
    assert identity.competition == "champions_league"
