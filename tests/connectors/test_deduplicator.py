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
