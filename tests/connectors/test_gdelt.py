"""Tests for GDELT connector."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.connectors.gdelt import GDELTConnector


SAMPLE_GDELT_RESPONSE = {
    "articles": [
        {
            "url": "https://reuters.com/article/fed-rates-123",
            "title": "Fed raises interest rates by 25 basis points",
            "seendate": "20260503T100000Z",
            "sourcecountry": "United States",
            "language": "English",
            "domain": "reuters.com",
        }
    ]
}


def make_mock_resp(response_data: dict) -> AsyncMock:
    """Create a mock aiohttp response. raise_for_status is sync (MagicMock)."""
    resp = AsyncMock()
    resp.json = AsyncMock(return_value=response_data)
    resp.raise_for_status = MagicMock()  # synchronous in real aiohttp
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)
    return resp


@pytest.mark.asyncio
async def test_gdelt_yields_items():
    """Test that GDELT connector yields NewsItem objects."""
    connector = GDELTConnector(
        query="Federal Reserve interest rates", asset_tags=["SPY"]
    )

    with patch("aiohttp.ClientSession.get", return_value=make_mock_resp(SAMPLE_GDELT_RESPONSE)):
        items = [item async for item in connector.fetch()]

    assert len(items) == 1
    assert items[0].source == "gdelt"
    assert items[0].title == "Fed raises interest rates by 25 basis points"
    assert items[0].url == "https://reuters.com/article/fed-rates-123"
    assert "SPY" in items[0].asset_tags


@pytest.mark.asyncio
async def test_gdelt_empty_response():
    """Test that GDELT connector handles empty response."""
    connector = GDELTConnector(query="test", asset_tags=[])

    with patch("aiohttp.ClientSession.get", return_value=make_mock_resp({"articles": []})):
        items = [item async for item in connector.fetch()]

    assert items == []


@pytest.mark.asyncio
async def test_gdelt_missing_title_skipped():
    """Test that GDELT connector skips items without title."""
    connector = GDELTConnector(query="test", asset_tags=[])

    data = {
        "articles": [
            {"url": "https://example.com/1", "title": "Valid title", "seendate": "20260503T100000Z"},
            {"url": "https://example.com/2", "title": "", "seendate": "20260503T100000Z"},
            {"url": "https://example.com/3", "seendate": "20260503T100000Z"},  # No title key
        ]
    }
    with patch("aiohttp.ClientSession.get", return_value=make_mock_resp(data)):
        items = [item async for item in connector.fetch()]

    assert len(items) == 1
    assert items[0].title == "Valid title"


@pytest.mark.asyncio
async def test_gdelt_invalid_timestamp_skipped():
    """Test that GDELT connector skips articles with invalid timestamps (no look-ahead bias)."""
    connector = GDELTConnector(query="test", asset_tags=[])

    data = {
        "articles": [
            {
                "url": "https://example.com/1",
                "title": "Test article",
                "seendate": "invalid-date",
            }
        ]
    }
    with patch("aiohttp.ClientSession.get", return_value=make_mock_resp(data)):
        items = [item async for item in connector.fetch()]

    assert len(items) == 0


@pytest.mark.asyncio
async def test_gdelt_title_used_as_body_proxy():
    """Test that GDELT connector uses title as body proxy."""
    connector = GDELTConnector(query="test", asset_tags=["AAPL"])

    data = {
        "articles": [
            {
                "url": "https://example.com/1",
                "title": "Apple announces new product",
                "seendate": "20260503T100000Z",
            }
        ]
    }
    with patch("aiohttp.ClientSession.get", return_value=make_mock_resp(data)):
        items = [item async for item in connector.fetch()]

    assert len(items) == 1
    assert items[0].title == items[0].body
    assert items[0].title == "Apple announces new product"
