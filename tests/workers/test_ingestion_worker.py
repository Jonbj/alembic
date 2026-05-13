"""Tests for NewsIngestionWorker."""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.news import GKGNewsItem, NewsItem


def make_gkg_item(url: str, org_names: list[str], title: str = "Tech news") -> GKGNewsItem:
    return GKGNewsItem(
        id=url,
        source="gdelt_gkg",
        timestamp=datetime.now(timezone.utc),
        title=title,
        body=title,
        url=url,
        language="en",
        asset_tags=[],
        org_names=org_names,
    )


@pytest.mark.asyncio
async def test_ingestion_worker_queues_item_with_ticker():
    """Article with known org name queues one NewsItem with ticker."""
    from src.workers.ingestion import _process_gkg_items

    gkg_items = [make_gkg_item("https://example.com/1", ["Apple Inc"])]
    mock_extractor = MagicMock()
    mock_extractor.extract.return_value = ["AAPL"]
    mock_dedup = MagicMock()
    mock_dedup.is_duplicate_by_id.return_value = False
    mock_redis = MagicMock()

    stats = _process_gkg_items(gkg_items, mock_extractor, mock_dedup, mock_redis)

    assert stats["queued"] == 1
    assert stats["discarded"] == 0
    assert mock_redis.rpush.call_count == 1
    pushed_data = json.loads(mock_redis.rpush.call_args[0][1])
    assert pushed_data["asset_tags"] == ["AAPL"]
    assert pushed_data["id"] == "https://example.com/1:AAPL"


@pytest.mark.asyncio
async def test_ingestion_worker_discards_no_ticker():
    """Article with no known org name is discarded."""
    from src.workers.ingestion import _process_gkg_items

    gkg_items = [make_gkg_item("https://example.com/2", ["Unknown Corp XYZ"])]
    mock_extractor = MagicMock()
    mock_extractor.extract.return_value = []
    mock_dedup = MagicMock()
    mock_redis = MagicMock()

    stats = _process_gkg_items(gkg_items, mock_extractor, mock_dedup, mock_redis)

    assert stats["discarded"] == 1
    assert stats["queued"] == 0
    mock_redis.rpush.assert_not_called()


def test_ingestion_worker_multi_ticker_article():
    """Article mentioning two orgs creates two separate NewsItems."""
    from src.workers.ingestion import _process_gkg_items

    gkg_items = [make_gkg_item("https://example.com/3", ["Apple Inc", "Microsoft Corporation"])]
    mock_extractor = MagicMock()
    mock_extractor.extract.return_value = ["AAPL", "MSFT"]
    mock_dedup = MagicMock()
    mock_dedup.is_duplicate_by_id.return_value = False
    mock_redis = MagicMock()

    stats = _process_gkg_items(gkg_items, mock_extractor, mock_dedup, mock_redis)

    assert stats["tickers_found"] == 2
    assert stats["queued"] == 2
    assert mock_redis.rpush.call_count == 2
    ids = [json.loads(c[0][1])["id"] for c in mock_redis.rpush.call_args_list]
    assert "https://example.com/3:AAPL" in ids
    assert "https://example.com/3:MSFT" in ids


def test_ingestion_worker_dedup_blocks_second():
    """Duplicate (url, ticker) combination is not queued twice."""
    from src.workers.ingestion import _process_gkg_items

    gkg_items = [
        make_gkg_item("https://example.com/4", ["Apple Inc"]),
        make_gkg_item("https://example.com/4", ["Apple Inc"]),
    ]
    mock_extractor = MagicMock()
    mock_extractor.extract.return_value = ["AAPL"]

    call_count = {"n": 0}

    def dedup_side_effect(item):
        call_count["n"] += 1
        return call_count["n"] > 1  # first is False, subsequent True

    mock_dedup = MagicMock()
    mock_dedup.is_duplicate_by_id.side_effect = dedup_side_effect
    mock_redis = MagicMock()

    stats = _process_gkg_items(gkg_items, mock_extractor, mock_dedup, mock_redis)

    assert stats["queued"] == 1
    assert stats["duplicates"] == 1


def test_ingestion_worker_returns_correct_stats():
    """Stats dict contains all expected keys with correct values."""
    from src.workers.ingestion import _process_gkg_items

    gkg_items = [
        make_gkg_item("https://a.com/1", ["Apple Inc"]),
        make_gkg_item("https://a.com/2", []),
    ]
    mock_extractor = MagicMock()
    mock_extractor.extract.side_effect = [["AAPL"], []]
    mock_dedup = MagicMock()
    mock_dedup.is_duplicate_by_id.return_value = False
    mock_redis = MagicMock()

    stats = _process_gkg_items(gkg_items, mock_extractor, mock_dedup, mock_redis)

    assert stats["fetched"] == 2
    assert stats["tickers_found"] == 1
    assert stats["discarded"] == 1
    assert stats["queued"] == 1
    assert stats["duplicates"] == 0
