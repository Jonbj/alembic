"""Tests for the Redis deduplicator."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.connectors.deduplicator import Deduplicator, compute_dedup_hash
from src.models.news import NewsItem


def make_item(title: str, body: str) -> NewsItem:
    """Create a test NewsItem with the given title and body."""
    return NewsItem(
        id="x",
        source="test",
        timestamp=datetime.now(timezone.utc),
        title=title,
        body=body,
        url="http://test.com",
        language="en",
        asset_tags=["AAPL"],
    )


def test_hash_deterministic():
    """Test that hash is deterministic for the same item."""
    item = make_item("Fed raises rates", "The Fed raised rates by 25bp.")
    h1 = compute_dedup_hash(item)
    h2 = compute_dedup_hash(item)
    assert h1 == h2


def test_hash_differs_on_content():
    """Test that hash differs when body content differs."""
    a = make_item("Fed raises rates", "body A")
    b = make_item("Fed raises rates", "body B")
    assert compute_dedup_hash(a) != compute_dedup_hash(b)


def test_deduplicator_first_seen_returns_false():
    """Test that first occurrence returns False (not a duplicate)."""
    mock_redis = MagicMock()
    mock_redis.set.return_value = True  # SET NX succeeded = first time
    dedup = Deduplicator(mock_redis)
    item = make_item("title", "body")
    assert dedup.is_duplicate(item) is False


def test_deduplicator_second_seen_returns_true():
    """Test that second occurrence returns True (is a duplicate)."""
    mock_redis = MagicMock()
    mock_redis.set.return_value = None  # SET NX failed = already exists
    dedup = Deduplicator(mock_redis)
    item = make_item("title", "body")
    assert dedup.is_duplicate(item) is True


def test_is_duplicate_by_id_first_seen_returns_false():
    """First occurrence by ID returns False."""
    mock_redis = MagicMock()
    mock_redis.set.return_value = True
    dedup = Deduplicator(mock_redis)
    item = make_item("same title", "same body")
    assert dedup.is_duplicate_by_id(item) is False


def test_is_duplicate_by_id_second_seen_returns_true():
    """Second occurrence by ID returns True."""
    mock_redis = MagicMock()
    mock_redis.set.return_value = None
    dedup = Deduplicator(mock_redis)
    item = make_item("same title", "same body")
    assert dedup.is_duplicate_by_id(item) is True


def test_same_content_different_id_not_duplicate():
    """Two items with same title/body but different IDs are not duplicates via is_duplicate_by_id."""
    calls = {}

    def fake_set(key, val, ex, nx):
        if key not in calls:
            calls[key] = True
            return True  # first time
        return None  # subsequent

    mock_redis = MagicMock()
    mock_redis.set.side_effect = fake_set
    dedup = Deduplicator(mock_redis)

    item_aapl = NewsItem(
        id="https://example.com/article:AAPL",
        source="test", timestamp=datetime.now(timezone.utc),
        title="Apple and Microsoft earnings", body="Apple and Microsoft earnings",
        url="https://example.com/article", language="en", asset_tags=["AAPL"],
    )
    item_msft = NewsItem(
        id="https://example.com/article:MSFT",
        source="test", timestamp=datetime.now(timezone.utc),
        title="Apple and Microsoft earnings", body="Apple and Microsoft earnings",
        url="https://example.com/article", language="en", asset_tags=["MSFT"],
    )
    assert dedup.is_duplicate_by_id(item_aapl) is False
    assert dedup.is_duplicate_by_id(item_msft) is False
