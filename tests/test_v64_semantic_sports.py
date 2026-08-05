from legacy.scanner_v6_1 import candidate_compatible, parse_market


def parse(platform: str, identifier: str, question: str):
    raw = {
        "id": identifier,
        "question": question,
        "outcomes": ["Yes", "No"],
        "outcomePrices": ["0.40", "0.60"],
    }
    if platform == "kalshi":
        raw = {
            "ticker": identifier,
            "title": question,
            "yes_ask_dollars": "0.40",
            "no_ask_dollars": "0.60",
        }
    return parse_market(platform, raw)


def test_relegation_and_team_of_year_are_not_candidates():
    relegation = parse(
        "kalshi",
        "tottenham-relegation",
        "Will Tottenham be relegated from EPL in 2026-27 Season?",
    )
    team_of_year = parse(
        "polymarket",
        "raya-pfa",
        "Will David Raya be named to the 2026 PFA Premier League Team of the Year?",
    )

    assert relegation.event_kind == "relegation"
    assert team_of_year.event_kind == "team_of_the_year"
    assert candidate_compatible(relegation, team_of_year) is False


def test_same_relegation_proposition_remains_candidate():
    first = parse(
        "kalshi",
        "tottenham-1",
        "Will Tottenham be relegated from the EPL in the 2026-27 season?",
    )
    second = parse(
        "polymarket",
        "tottenham-2",
        "Tottenham to be relegated from the Premier League in 2026?",
    )

    assert first.event_kind == "relegation"
    assert second.event_kind == "relegation"
    assert first.player == "tottenham"
    assert second.player == "tottenham"
    assert candidate_compatible(first, second) is True


def test_team_of_year_extracts_player():
    market = parse(
        "polymarket",
        "raya",
        "Will David Raya be named to the 2026 PFA Premier League Team of the Year?",
    )
    assert market.event_kind == "team_of_the_year"
    assert market.participant_type == "player"
    assert market.player == "david_raya"
