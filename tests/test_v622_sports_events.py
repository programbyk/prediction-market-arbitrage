from legacy.scanner_v6_1 import (
    candidate_compatible,
    parse_market,
)


def parse_poly(identifier: str, question: str):
    return parse_market(
        "polymarket",
        {
            "id": identifier,
            "question": question,
            "outcomes": ["Yes", "No"],
            "outcomePrices": ["0.40", "0.60"],
        },
    )


def test_lebron_joining_and_retiring_are_different_events():
    joining = parse_poly(
        "join",
        "Will any Source Agency announce that LeBron James is joining any NBA team "
        "after issuance and before July 23, 2026?",
    )
    retiring = parse_poly(
        "retire",
        "Will LeBron James retire before next NBA season?",
    )

    assert joining.event_subject == "lebron_james"
    assert retiring.event_subject == "lebron_james"
    assert joining.event_action == "join_team"
    assert retiring.event_action == "retire"
    assert candidate_compatible(joining, retiring) is False


def test_same_retirement_event_remains_candidate():
    first = parse_poly(
        "retire-1",
        "Will LeBron James retire before the next NBA season?",
    )
    second = parse_poly(
        "retire-2",
        "LeBron James to retire before next NBA season?",
    )

    assert first.event_subject == "lebron_james"
    assert second.event_subject == "lebron_james"
    assert first.event_action == "retire"
    assert second.event_action == "retire"
    assert candidate_compatible(first, second) is True
