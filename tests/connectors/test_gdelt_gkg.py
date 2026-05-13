"""Tests for GDELTGKGConnector."""

import json
from datetime import timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.connectors.gdelt_gkg import GDELTGKGConnector
from src.models.news import GKGNewsItem


SAMPLE_GKG_RESPONSE = {
    "gkg": [
        {
            "date": "20260513140000",
            "V2Organizations": "Apple Inc;Microsoft Corporation;",
            "V2DocumentIdentifier": "https://reuters.com/article/tech-q2",
            "V2SourceCommonName": "Reuters",
            "extras": json.dumps({"PageTitle": "Apple and Microsoft report strong Q2 earnings"}),
        }
    ]
}

SAMPLE_GKG_RESPONSE_MISSING_URL = {
    "gkg": [
        {
            "date": "20260513140000",
            "V2Organizations": "Apple Inc",
            "V2DocumentIdentifier": "",
            "extras": json.dumps({"PageTitle": "Some article"}),
        }
    ]
}

SAMPLE_GKG_RESPONSE_INVALID_DATE = {
    "gkg": [
        {
            "date": "not-a-date",
            "V2Organizations": "Apple Inc",
            "V2DocumentIdentifier": "https://example.com/article",
            "extras": json.dumps({"PageTitle": "Some article"}),
        }
    ]
}


def make_mock_resp(response_data: dict) -> AsyncMock:
    resp = AsyncMock()
    resp.json = AsyncMock(return_value=response_data)
    resp.raise_for_status = MagicMock()
    resp.status = 200
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)
    return resp


@pytest.mark.asyncio
async def test_gkg_yields_gkg_news_item():
    """Connector yields GKGNewsItem with org_names extracted from V2Organizations."""
    connector = GDELTGKGConnector()
    with patch("aiohttp.ClientSession.get", return_value=make_mock_resp(SAMPLE_GKG_RESPONSE)):
        items = [item async for item in connector.fetch()]

    assert len(items) == 1
    item = items[0]
    assert isinstance(item, GKGNewsItem)
    assert "Apple Inc" in item.org_names
    assert "Microsoft Corporation" in item.org_names
    assert item.url == "https://reuters.com/article/tech-q2"
    assert item.source == "gdelt_gkg"
    assert item.asset_tags == []


@pytest.mark.asyncio
async def test_gkg_title_from_page_title():
    """Title is extracted from extras.PageTitle."""
    connector = GDELTGKGConnector()
    with patch("aiohttp.ClientSession.get", return_value=make_mock_resp(SAMPLE_GKG_RESPONSE)):
        items = [item async for item in connector.fetch()]

    assert items[0].title == "Apple and Microsoft report strong Q2 earnings"
    assert items[0].body == items[0].title


@pytest.mark.asyncio
async def test_gkg_missing_url_skipped():
    """Records with empty V2DocumentIdentifier are skipped."""
    connector = GDELTGKGConnector()
    with patch("aiohttp.ClientSession.get", return_value=make_mock_resp(SAMPLE_GKG_RESPONSE_MISSING_URL)):
        items = [item async for item in connector.fetch()]

    assert items == []


@pytest.mark.asyncio
async def test_gkg_invalid_date_skipped():
    """Records with unparseable date are skipped (look-ahead bias prevention)."""
    connector = GDELTGKGConnector()
    with patch("aiohttp.ClientSession.get", return_value=make_mock_resp(SAMPLE_GKG_RESPONSE_INVALID_DATE)):
        items = [item async for item in connector.fetch()]

    assert items == []


@pytest.mark.asyncio
async def test_gkg_empty_response():
    """Empty gkg list yields no items."""
    connector = GDELTGKGConnector()
    with patch("aiohttp.ClientSession.get", return_value=make_mock_resp({"gkg": []})):
        items = [item async for item in connector.fetch()]

    assert items == []


@pytest.mark.asyncio
async def test_gkg_org_names_split_and_stripped():
    """V2Organizations semicolon-split, whitespace stripped, empty strings removed."""
    connector = GDELTGKGConnector()
    resp_data = {
        "gkg": [
            {
                "date": "20260513140000",
                "V2Organizations": " Apple Inc ; Microsoft Corporation ; ; ",
                "V2DocumentIdentifier": "https://example.com/1",
                "extras": json.dumps({"PageTitle": "Tech news"}),
            }
        ]
    }
    with patch("aiohttp.ClientSession.get", return_value=make_mock_resp(resp_data)):
        items = [item async for item in connector.fetch()]

    assert items[0].org_names == ["Apple Inc", "Microsoft Corporation"]


@pytest.mark.asyncio
async def test_gkg_timestamp_parsed_correctly():
    """date field parsed to UTC datetime."""
    connector = GDELTGKGConnector()
    with patch("aiohttp.ClientSession.get", return_value=make_mock_resp(SAMPLE_GKG_RESPONSE)):
        items = [item async for item in connector.fetch()]

    ts = items[0].timestamp
    assert ts.tzinfo == timezone.utc
    assert ts.year == 2026
    assert ts.month == 5
    assert ts.day == 13
    assert ts.hour == 14
