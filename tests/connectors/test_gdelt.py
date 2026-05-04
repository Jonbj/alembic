"""Tests for GDELT connector."""

import pytest
from unittest.mock import AsyncMock, patch

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


@pytest.mark.asyncio
async def test_gdelt_yields_items():
    """Test that GDELT connector yields NewsItem objects."""
    connector = GDELTConnector(
        query="Federal Reserve interest rates", asset_tags=["SPY"]
    )

    # Mock the aiohttp response
    mock_response = AsyncMock()
    mock_response.json = AsyncMock(return_value=SAMPLE_GDELT_RESPONSE)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession.get", return_value=mock_response):
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

    mock_response = AsyncMock()
    mock_response.json = AsyncMock(return_value={"articles": []})
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession.get", return_value=mock_response):
        items = [item async for item in connector.fetch()]

    assert items == []


@pytest.mark.asyncio
async def test_gdelt_missing_title_skipped():
    """Test that GDELT connector skips items without title."""
    connector = GDELTConnector(query="test", asset_tags=[])

    mock_response = AsyncMock()
    mock_response.json = AsyncMock(
        return_value={
            "articles": [
                {"url": "https://example.com/1", "title": "Valid title"},
                {"url": "https://example.com/2", "title": ""},
                {"url": "https://example.com/3"},  # No title key
            ]
        }
    )
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession.get", return_value=mock_response):
        items = [item async for item in connector.fetch()]

    assert len(items) == 1
    assert items[0].title == "Valid title"


@pytest.mark.asyncio
async def test_gdelt_invalid_timestamp_fallback():
    """Test that GDELT connector falls back to now() for invalid timestamps."""
    connector = GDELTConnector(query="test", asset_tags=[])

    mock_response = AsyncMock()
    mock_response.json = AsyncMock(
        return_value={
            "articles": [
                {
                    "url": "https://example.com/1",
                    "title": "Test article",
                    "seendate": "invalid-date",
                }
            ]
        }
    )
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession.get", return_value=mock_response):
        items = [item async for item in connector.fetch()]

    assert len(items) == 1
    # Timestamp should be set (fallback to now())
    assert items[0].timestamp is not None


@pytest.mark.asyncio
async def test_gdelt_title_used_as_body_proxy():
    """Test that GDELT connector uses title as body proxy."""
    connector = GDELTConnector(query="test", asset_tags=["AAPL"])

    mock_response = AsyncMock()
    mock_response.json = AsyncMock(
        return_value={
            "articles": [
                {
                    "url": "https://example.com/1",
                    "title": "Apple announces new product",
                    "seendate": "20260503T100000Z",
                }
            ]
        }
    )
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession.get", return_value=mock_response):
        items = [item async for item in connector.fetch()]

    assert len(items) == 1
    # Title should be used as body proxy
    assert items[0].title == items[0].body
    assert items[0].title == "Apple announces new product"
