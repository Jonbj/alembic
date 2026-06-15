"""Tests for SEC EDGAR ingestion worker."""
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.models.news import NewsItem
from datetime import datetime, timezone


def _make_edgar_item(ticker: str, id_: str = None) -> NewsItem:
    return NewsItem(
        id=id_ or f"edgar:{ticker}:8-K-2026-06-16",
        source="sec_edgar",
        timestamp=datetime.now(timezone.utc),
        title=f"{ticker} — 8-K",
        body="Quarterly earnings report",
        url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001234",
        language="en",
        asset_tags=[ticker],
    )


def test_sec_edgar_worker_queues_watchlist_items():
    """Worker deve pushare items per ticker in watchlist, skippare gli altri."""
    items = [
        _make_edgar_item("AAPL"),
        _make_edgar_item("UNKNOWN_CORP"),  # non in watchlist
        _make_edgar_item("MSFT"),
    ]

    mock_redis = MagicMock()
    mock_dedup = MagicMock()
    mock_dedup.is_duplicate_by_id.return_value = False

    with patch("src.workers.ingestion.SECEdgarConnector") as mock_connector_cls, \
         patch("src.workers.ingestion.Deduplicator", return_value=mock_dedup), \
         patch("src.workers.ingestion.Redis") as mock_redis_cls, \
         patch("src.workers.ingestion.config") as mock_cfg:

        mock_cfg.WATCHLIST_SYMBOLS = ["AAPL", "MSFT", "GOOGL"]
        mock_cfg.REDIS_URL = "redis://localhost:6379/0"
        mock_redis_cls.from_url.return_value = mock_redis

        # SECEdgarConnector().fetch() è async generator
        async def fake_fetch():
            for item in items:
                yield item

        mock_connector_cls.return_value.fetch.return_value = fake_fetch()

        from src.workers.ingestion import run_sec_edgar_ingestion_worker
        result = run_sec_edgar_ingestion_worker()

    assert result["queued"] == 2        # AAPL + MSFT
    assert result["filtered"] == 1      # UNKNOWN_CORP
    assert mock_redis.rpush.call_count == 2


def test_sec_edgar_worker_deduplicates():
    """Worker deve skippare item già visto."""
    items = [_make_edgar_item("AAPL")]

    mock_redis = MagicMock()
    mock_dedup = MagicMock()
    mock_dedup.is_duplicate_by_id.return_value = True  # già in cache

    with patch("src.workers.ingestion.SECEdgarConnector") as mock_connector_cls, \
         patch("src.workers.ingestion.Deduplicator", return_value=mock_dedup), \
         patch("src.workers.ingestion.Redis") as mock_redis_cls, \
         patch("src.workers.ingestion.config") as mock_cfg:

        mock_cfg.WATCHLIST_SYMBOLS = ["AAPL"]
        mock_cfg.REDIS_URL = "redis://localhost:6379/0"
        mock_redis_cls.from_url.return_value = mock_redis

        async def fake_fetch():
            for item in items:
                yield item

        mock_connector_cls.return_value.fetch.return_value = fake_fetch()

        from src.workers.ingestion import run_sec_edgar_ingestion_worker
        result = run_sec_edgar_ingestion_worker()

    assert result["queued"] == 0
    assert result["duplicates"] == 1
    assert mock_redis.rpush.call_count == 0


def test_sec_edgar_worker_skips_item_with_no_ticker():
    """Item senza asset_tags viene skippato."""
    item_no_ticker = NewsItem(
        id="edgar:no-ticker",
        source="sec_edgar",
        timestamp=datetime.now(timezone.utc),
        title="Unknown Corp — 8-K",
        body="Filing body",
        url="https://www.sec.gov",
        language="en",
        asset_tags=[],  # nessun ticker
    )

    mock_redis = MagicMock()
    mock_dedup = MagicMock()

    with patch("src.workers.ingestion.SECEdgarConnector") as mock_connector_cls, \
         patch("src.workers.ingestion.Deduplicator", return_value=mock_dedup), \
         patch("src.workers.ingestion.Redis") as mock_redis_cls, \
         patch("src.workers.ingestion.config") as mock_cfg:

        mock_cfg.WATCHLIST_SYMBOLS = ["AAPL"]
        mock_cfg.REDIS_URL = "redis://localhost:6379/0"
        mock_redis_cls.from_url.return_value = mock_redis

        async def fake_fetch():
            yield item_no_ticker

        mock_connector_cls.return_value.fetch.return_value = fake_fetch()

        from src.workers.ingestion import run_sec_edgar_ingestion_worker
        result = run_sec_edgar_ingestion_worker()

    assert result["queued"] == 0
    assert result["filtered"] == 1
