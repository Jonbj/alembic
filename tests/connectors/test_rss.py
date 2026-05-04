"""Tests for RSS connector."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timezone

from src.connectors.rss import RSSConnector


SAMPLE_FEED = {
    "entries": [
        {
            "id": "http://reuters.com/1",
            "title": "Fed raises rates by 25bp",
            "summary": "The Federal Reserve raised interest rates by 25 basis points.",
            "link": "http://reuters.com/1",
            "published_parsed": (2026, 5, 3, 10, 0, 0, 5, 123, 0),
            "tags": [{"term": "ECONOMY"}],
        }
    ]
}


@pytest.mark.asyncio
async def test_rss_yields_news_items():
    """Test that RSS connector yields properly formatted news items."""
    connector = RSSConnector(
        feed_url="http://feeds.reuters.com/reuters/businessNews",
        source_name="reuters",
        asset_tags=["SPY"],
    )
    with patch("feedparser.parse", return_value=SAMPLE_FEED):
        items = []
        async for item in connector.fetch():
            items.append(item)

    assert len(items) == 1
    assert items[0].source == "reuters"
    assert items[0].language == "en"
    assert "SPY" in items[0].asset_tags
    assert "Fed raises rates by 25bp" in items[0].title
    assert "Federal Reserve" in items[0].body


@pytest.mark.asyncio
async def test_rss_skips_empty_body():
    """Test that RSS connector skips items with empty body."""
    connector = RSSConnector(
        feed_url="http://example.com/rss",
        source_name="test",
        asset_tags=[],
    )
    empty_feed = {
        "entries": [
            {
                "id": "1",
                "title": "Title",
                "summary": "",
                "link": "http://x.com",
                "published_parsed": None,
            }
        ]
    }
    with patch("feedparser.parse", return_value=empty_feed):
        items = [item async for item in connector.fetch()]

    assert len(items) == 0


@pytest.mark.asyncio
async def test_rss_multiple_entries():
    """Test that RSS connector handles multiple entries correctly."""
    connector = RSSConnector(
        feed_url="http://example.com/rss",
        source_name="test",
        asset_tags=["AAPL", "GOOGL"],
    )
    multi_feed = {
        "entries": [
            {
                "id": "1",
                "title": "First news",
                "summary": "First body content",
                "link": "http://example.com/1",
                "published_parsed": (2026, 5, 3, 10, 0, 0, 5, 123, 0),
            },
            {
                "id": "2",
                "title": "Second news",
                "summary": "Second body content",
                "link": "http://example.com/2",
                "published_parsed": (2026, 5, 3, 11, 0, 0, 5, 123, 0),
            },
        ]
    }
    with patch("feedparser.parse", return_value=multi_feed):
        items = [item async for item in connector.fetch()]

    assert len(items) == 2
    assert items[0].title == "First news"
    assert items[1].title == "Second news"
    assert items[0].asset_tags == ["AAPL", "GOOGL"]
    assert items[1].asset_tags == ["AAPL", "GOOGL"]


@pytest.mark.asyncio
async def test_rss_uses_current_time_when_no_timestamp():
    """Test that RSS connector uses current time when no timestamp is provided."""
    connector = RSSConnector(
        feed_url="http://example.com/rss",
        source_name="test",
        asset_tags=[],
    )
    feed_no_time = {
        "entries": [
            {
                "id": "1",
                "title": "Title",
                "summary": "Body",
                "link": "http://x.com",
                "published_parsed": None,
            }
        ]
    }
    with patch("feedparser.parse", return_value=feed_no_time):
        items = [item async for item in connector.fetch()]

    assert len(items) == 1
    assert items[0].timestamp.tzinfo == timezone.utc


@pytest.mark.asyncio
async def test_rss_content_fallback():
    """Test that RSS connector falls back to content field when summary is missing."""
    connector = RSSConnector(
        feed_url="http://example.com/rss",
        source_name="test",
        asset_tags=[],
    )
    feed_with_content = {
        "entries": [
            {
                "id": "1",
                "title": "Title",
                "content": [{"value": "Content value here"}],
                "link": "http://x.com",
                "published_parsed": None,
            }
        ]
    }
    with patch("feedparser.parse", return_value=feed_with_content):
        items = [item async for item in connector.fetch()]

    assert len(items) == 1
    assert items[0].body == "Content value here"
