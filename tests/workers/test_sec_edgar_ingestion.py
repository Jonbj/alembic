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


def _dedup(duplicate_by_id: bool = False, duplicate_content: bool = False) -> MagicMock:
    """Build a Deduplicator mock with both dedup methods set explicitly.

    _process_sec_edgar_items checks ``is_duplicate_by_id(item) OR
    is_duplicate_content_symbol(item)``, so a default MagicMock (truthy) would
    mark every item as a duplicate. Set both returns explicitly.
    """
    d = MagicMock()
    d.is_duplicate_by_id.return_value = duplicate_by_id
    d.is_duplicate_content_symbol.return_value = duplicate_content
    return d


# The Celery entry-point run_sec_edgar_ingestion_worker() is disabled by default
# since 2026-07-02 (SEC_EDGAR_INGESTION_ENABLED=0) and short-circuits to
# {"skipped": True, ...}. The testable unit is the pure _process_sec_edgar_items
# helper it delegates to, which returns {fetched, queued, filtered, duplicates}.

def test_sec_edgar_worker_queues_watchlist_items():
    """Pure processor queues items whose ticker is in the watchlist, filters the rest."""
    from src.workers.ingestion import _process_sec_edgar_items
    items = [
        _make_edgar_item("AAPL"),
        _make_edgar_item("UNKNOWN_CORP"),  # non in watchlist
        _make_edgar_item("MSFT"),
    ]
    mock_redis = MagicMock()
    watchlist = {"AAPL", "MSFT", "GOOGL"}

    result = _process_sec_edgar_items(items, watchlist, _dedup(), mock_redis)

    assert result["queued"] == 2        # AAPL + MSFT
    assert result["filtered"] == 1      # UNKNOWN_CORP
    assert mock_redis.rpush.call_count == 2


def test_sec_edgar_worker_deduplicates():
    """Pure processor skips an item already seen (by id)."""
    from src.workers.ingestion import _process_sec_edgar_items
    items = [_make_edgar_item("AAPL")]
    mock_redis = MagicMock()
    watchlist = {"AAPL"}

    result = _process_sec_edgar_items(items, watchlist, _dedup(duplicate_by_id=True), mock_redis)

    assert result["queued"] == 0
    assert result["duplicates"] == 1
    assert mock_redis.rpush.call_count == 0


def test_sec_edgar_worker_skips_item_with_no_ticker():
    """Item senza asset_tags viene skippato (filtered)."""
    from src.workers.ingestion import _process_sec_edgar_items
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
    watchlist = {"AAPL"}

    result = _process_sec_edgar_items([item_no_ticker], watchlist, _dedup(), mock_redis)

    assert result["queued"] == 0
    assert result["filtered"] == 1
    assert mock_redis.rpush.call_count == 0


def test_sec_edgar_worker_entrypoint_disabled_by_default(monkeypatch):
    """The Celery entry-point is OFF by default (2026-07-02) and short-circuits
    without touching the connector — guards against running the broken CIK path
    until the CIK→ticker attribution is fixed."""
    monkeypatch.delenv("SEC_EDGAR_INGESTION_ENABLED", raising=False)
    from src.workers.ingestion import run_sec_edgar_ingestion_worker
    result = run_sec_edgar_ingestion_worker()
    assert result == {"skipped": True, "reason": "sec_edgar_ingestion_disabled"}
