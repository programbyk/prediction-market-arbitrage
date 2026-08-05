from parsers.diagnostics import infer_suspected_category
from legacy.scanner_v6_1 import ParsedMarket, MarketPrice


def market(title: str):
    return ParsedMarket(
        platform="kalshi",
        source_id=title,
        title=title,
        raw={},
        price=MarketPrice(yes=0.5, no=0.5),
        category="other",
    )


def test_missed_sports_signal():
    category, reason, hits = infer_suspected_category(
        market("Will the Dodgers make the MLB postseason?")
    )
    assert category == "sports"
    assert "mlb" in hits or "postseason" in hits
    assert "missed sports" in reason.lower()


def test_unsupported_weather_signal():
    category, reason, hits = infer_suspected_category(
        market("Will New York receive more than 10 inches of snow?")
    )
    assert category == "weather"
    assert "snow" in hits
    assert "does not yet have" in reason.lower()


def test_unknown_market_without_signals():
    category, reason, hits = infer_suspected_category(
        market("Will the mystery event happen?")
    )
    assert category == "unsupported_or_unknown"
    assert hits == []
