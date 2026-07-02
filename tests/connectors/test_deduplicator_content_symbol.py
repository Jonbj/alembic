"""EN-03: cross-source content dedup. Same article text for the same ticker
from two different sources must be deduplicated; same text for two different
tickers must NOT (multi-ticker fan-out is legitimate)."""

from unittest.mock import MagicMock

from src.connectors.deduplicator import Deduplicator
from src.models.news import NewsItem


def _item(item_id: str, ticker: str, source: str) -> NewsItem:
    return NewsItem(
        id=item_id,
        title="Apple beats Q3 estimates",
        body="Apple Inc reported quarterly revenue above expectations...",
        source=source,
        asset_tags=[ticker],
    )


def _redis_first_insert_then_dup():
    """SET NX returns True on first insert, None when the key already exists."""
    r = MagicMock()
    seen: set[str] = set()

    def fake_set(key, value, ex=None, nx=None):
        if key in seen:
            return None
        seen.add(key)
        return True

    r.set.side_effect = fake_set
    return r


def test_same_content_same_ticker_cross_source_is_duplicate():
    dedup = Deduplicator(_redis_first_insert_then_dup())
    a = _item("https://benzinga.com/x:AAPL", "AAPL", "alpaca")
    b = _item("https://reuters.com/y:AAPL", "AAPL", "gdelt_gkg")  # id diverso, testo identico
    assert dedup.is_duplicate_content_symbol(a) is False
    assert dedup.is_duplicate_content_symbol(b) is True


def test_same_content_different_ticker_is_not_duplicate():
    dedup = Deduplicator(_redis_first_insert_then_dup())
    a = _item("https://x.com/1:AAPL", "AAPL", "alpaca")
    b = _item("https://x.com/1:MSFT", "MSFT", "alpaca")
    assert dedup.is_duplicate_content_symbol(a) is False
    assert dedup.is_duplicate_content_symbol(b) is False


def test_item_without_asset_tags_is_never_content_duplicate():
    dedup = Deduplicator(_redis_first_insert_then_dup())
    a = NewsItem(id="u:1", title="t", body="b", asset_tags=[])
    assert dedup.is_duplicate_content_symbol(a) is False
