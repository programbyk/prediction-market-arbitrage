from knowledge.loader import KnowledgeBase


def test_home_run_derby_alias():
    kb = KnowledgeBase()
    result = kb.resolve_sports_identity("Will Kyle Schwarber win the HR Derby?")
    assert result is not None
    assert result.competition == "home_run_derby"
    assert result.sport == "baseball"
    assert result.league == "mlb"


def test_hank_aaron_is_not_mvp():
    kb = KnowledgeBase()
    result = kb.resolve_sports_identity(
        "Will Kyle Schwarber win the National League Hank Aaron Award?"
    )
    assert result is not None
    assert result.competition == "nl_hank_aaron"


def test_champions_league_alias():
    kb = KnowledgeBase()
    result = kb.resolve_sports_identity("Will Real Madrid win the UCL?")
    assert result is not None
    assert result.competition == "champions_league"


def test_political_office_resolution():
    kb = KnowledgeBase()
    assert kb.resolve("political_office", "Texas gubernatorial election") == "governor"


def test_crypto_alias_resolution():
    kb = KnowledgeBase()
    assert kb.resolve("crypto_asset", "Will BTC exceed $150k?") == "bitcoin"


def test_economy_metric_resolution():
    kb = KnowledgeBase()
    assert (
        kb.resolve("economy_metric", "Will the unemployment rate exceed 7%?")
        == "unemployment_rate"
    )
