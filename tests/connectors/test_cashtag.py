"""Tests for the shared cashtag fallback (QT-01)."""
from src.connectors.cashtag import extract_cashtag_tickers


def test_extracts_cashtag_universe_tickers():
    assert set(extract_cashtag_tickers("$AAPL rose, $MSFT fell", {"AAPL", "MSFT", "GOOGL"})) == \
        {"AAPL", "MSFT"}


def test_no_cashtag_returns_empty():
    # bare tickers without a cashtag are NOT matched — that is the whole point of QT-01
    assert extract_cashtag_tickers("AAPL and MSFT both rose", {"AAPL", "MSFT"}) == []


def test_cashtag_outside_universe_ignored():
    assert extract_cashtag_tickers("$ZZZQ mooned", {"AAPL"}) == []


def test_empty_text():
    assert extract_cashtag_tickers("", {"AAPL"}) == []
    assert extract_cashtag_tickers(None, {"AAPL"}) == []


def test_short_cashtag_ticker():
    # short/ambiguous tickers are fine WITH a cashtag (explicit)
    assert extract_cashtag_tickers("$F gained on truck demand", {"F", "GM"}) == ["F"]
