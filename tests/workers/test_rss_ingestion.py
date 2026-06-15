"""Tests for RSS ingestion worker."""
import re
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from src.models.news import NewsItem


def _make_rss_item(title: str, body: str = "", ticker: str = "") -> NewsItem:
    return NewsItem(
        id=f"rss:{hash(title)}",
        source="reuters",
        timestamp=datetime.now(timezone.utc),
        title=title,
        body=body,
        url="https://reuters.com/article/foo",
        language="en",
        asset_tags=[ticker] if ticker else [],
    )


class TestExtractTickersFromText:
    def test_finds_ticker_in_title(self):
        from src.workers.ingestion import _extract_tickers_from_text
        result = _extract_tickers_from_text("AAPL shares rose 3% today", {"AAPL", "MSFT"})
        assert "AAPL" in result
        assert "MSFT" not in result

    def test_finds_multiple_tickers(self):
        from src.workers.ingestion import _extract_tickers_from_text
        result = _extract_tickers_from_text("AAPL and MSFT both up", {"AAPL", "MSFT", "GOOGL"})
        assert set(result) == {"AAPL", "MSFT"}

    def test_no_match_returns_empty(self):
        from src.workers.ingestion import _extract_tickers_from_text
        result = _extract_tickers_from_text("Federal Reserve raises rates", {"AAPL", "MSFT"})
        assert result == []

    def test_partial_word_not_matched(self):
        """'APPS' non deve matchare 'APP' nella watchlist."""
        from src.workers.ingestion import _extract_tickers_from_text
        result = _extract_tickers_from_text("APPS rallied today", {"APP"})
        assert result == []


def test_rss_worker_queues_items_with_ticker_match():
    """Worker deve pushare solo articoli con almeno un ticker della watchlist."""
    items = [
        _make_rss_item("AAPL quarterly results beat estimates"),      # match
        _make_rss_item("Federal Reserve holds rates steady"),          # no match
        _make_rss_item("MSFT Azure revenue grows 30%"),                # match
    ]

    mock_redis = MagicMock()
    mock_dedup = MagicMock()
    mock_dedup.is_duplicate_by_id.return_value = False

    with patch("src.workers.ingestion.RSSConnector") as mock_rss_cls, \
         patch("src.workers.ingestion.Deduplicator", return_value=mock_dedup), \
         patch("src.workers.ingestion.Redis") as mock_redis_cls, \
         patch("src.workers.ingestion.config") as mock_cfg:

        mock_cfg.WATCHLIST_SYMBOLS = ["AAPL", "MSFT", "GOOGL"]
        mock_cfg.REDIS_URL = "redis://localhost:6379/0"
        mock_redis_cls.from_url.return_value = mock_redis

        async def fake_fetch():
            for item in items:
                yield item

        mock_rss_cls.return_value.fetch.return_value = fake_fetch()

        from src.workers.ingestion import run_rss_ingestion_worker
        result = run_rss_ingestion_worker()

    # AAPL article → 1 push; MSFT article → 1 push; Federal Reserve → filtered
    assert result["queued"] == 2
    assert result["filtered"] == 1


def test_rss_worker_expands_per_ticker():
    """Articolo con 2 ticker → 2 item separati in coda."""
    items = [_make_rss_item("AAPL and MSFT both surge on AI news")]

    mock_redis = MagicMock()
    mock_dedup = MagicMock()
    mock_dedup.is_duplicate_by_id.return_value = False

    with patch("src.workers.ingestion.RSSConnector") as mock_rss_cls, \
         patch("src.workers.ingestion.Deduplicator", return_value=mock_dedup), \
         patch("src.workers.ingestion.Redis") as mock_redis_cls, \
         patch("src.workers.ingestion.config") as mock_cfg:

        mock_cfg.WATCHLIST_SYMBOLS = ["AAPL", "MSFT"]
        mock_cfg.REDIS_URL = "redis://localhost:6379/0"
        mock_redis_cls.from_url.return_value = mock_redis

        async def fake_fetch():
            for item in items:
                yield item

        mock_rss_cls.return_value.fetch.return_value = fake_fetch()

        from src.workers.ingestion import run_rss_ingestion_worker
        result = run_rss_ingestion_worker()

    assert result["queued"] == 2  # un item per AAPL, uno per MSFT
    assert mock_redis.rpush.call_count == 2
