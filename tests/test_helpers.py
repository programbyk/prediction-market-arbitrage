from utils.helpers import (
    normalize_text,
    parse_json_maybe,
    parse_number,
    parse_year,
    safe_float,
)


def test_normalize_text_removes_accents():
    assert normalize_text("Raphaël Éric") == "raphael eric"


def test_parse_number_ignores_year():
    assert parse_number("Will inflation be above 4.25% in 2026?") == 4.25


def test_parse_number_magnitude():
    assert parse_number("Will Bitcoin exceed $150k?") == 150000.0


def test_parse_year():
    assert parse_year("Election winner in 2028") == 2028


def test_safe_float():
    assert safe_float("0.42") == 0.42
    assert safe_float("bad") is None
    assert safe_float(-1) is None


def test_parse_json_maybe():
    assert parse_json_maybe('["Yes", "No"]') == ["Yes", "No"]
    assert parse_json_maybe("not-json") == "not-json"
