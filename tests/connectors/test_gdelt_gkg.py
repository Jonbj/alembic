"""Tests for GDELTGKGConnector."""

import asyncio
import json
from datetime import datetime, timezone
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

SAMPLE_RECORD = {
    "date": "20251001140000",
    "V2Organizations": "Apple Inc",
    "V2DocumentIdentifier": "https://reuters.com/article/1",
    "extras": '{"PageTitle": "Apple earnings beat"}',
}

SAMPLE_RECORD_2 = {
    "date": "20251101140000",
    "V2Organizations": "Microsoft Corporation",
    "V2DocumentIdentifier": "https://reuters.com/article/2",
    "extras": '{"PageTitle": "Microsoft cloud growth"}',
}


@pytest.mark.asyncio
async def test_fetch_historical_chunks_by_month():
    """fetch_historical makes one API call per month with correct STARTDATETIME."""
    connector = GDELTGKGConnector()
    start = datetime(2025, 10, 1, tzinfo=timezone.utc)
    end = datetime(2025, 11, 30, tzinfo=timezone.utc)

    call_params = []

    async def mock_backoff(session, params, url):
        call_params.append(dict(params))
        month = params["STARTDATETIME"][:6]
        if month == "202510":
            return {"gkg": [SAMPLE_RECORD]}
        return {"gkg": [SAMPLE_RECORD_2]}

    with patch.object(connector, "_fetch_with_backoff", side_effect=mock_backoff):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            items = [item async for item in connector.fetch_historical(start, end)]

    assert len(call_params) == 2
    assert call_params[0]["STARTDATETIME"] == "20251001000000"
    assert call_params[0]["ENDDATETIME"] == "20251031235959"
    assert call_params[1]["STARTDATETIME"] == "20251101000000"
    assert len(items) == 2


@pytest.mark.asyncio
async def test_fetch_historical_sleeps_between_chunks():
    """fetch_historical sleeps 1 second between monthly chunks."""
    connector = GDELTGKGConnector()
    start = datetime(2025, 10, 1, tzinfo=timezone.utc)
    end = datetime(2025, 11, 30, tzinfo=timezone.utc)

    sleep_calls = []

    async def mock_sleep(seconds):
        sleep_calls.append(seconds)

    with patch.object(connector, "_fetch_with_backoff", return_value={"gkg": []}):
        with patch("asyncio.sleep", side_effect=mock_sleep):
            items = [item async for item in connector.fetch_historical(start, end)]

    assert len(sleep_calls) == 2
    assert all(s == 1.0 for s in sleep_calls)


@pytest.mark.asyncio
async def test_fetch_historical_skips_bad_records():
    """fetch_historical skips records with missing URL or invalid timestamp."""
    connector = GDELTGKGConnector()
    start = datetime(2025, 10, 1, tzinfo=timezone.utc)
    end = datetime(2025, 10, 31, tzinfo=timezone.utc)

    bad_records = [
        {"date": "20251001140000", "V2Organizations": "Apple Inc",
         "V2DocumentIdentifier": "", "extras": "{}"},       # missing URL
        {"date": "not-a-date", "V2Organizations": "Apple Inc",
         "V2DocumentIdentifier": "https://x.com/1", "extras": "{}"},  # bad date
        SAMPLE_RECORD,  # good record
    ]

    with patch.object(connector, "_fetch_with_backoff",
                      return_value={"gkg": bad_records}):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            items = [item async for item in connector.fetch_historical(start, end)]

    assert len(items) == 1
    assert items[0].url == "https://reuters.com/article/1"


@pytest.mark.asyncio
async def test_fetch_historical_empty_response_continues():
    """fetch_historical continues to next month when API returns empty."""
    connector = GDELTGKGConnector()
    start = datetime(2025, 10, 1, tzinfo=timezone.utc)
    end = datetime(2025, 11, 30, tzinfo=timezone.utc)

    responses = [None, {"gkg": [SAMPLE_RECORD_2]}]
    call_count = [0]

    async def mock_backoff(session, params, url):
        r = responses[call_count[0]]
        call_count[0] += 1
        return r

    with patch.object(connector, "_fetch_with_backoff", side_effect=mock_backoff):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            items = [item async for item in connector.fetch_historical(start, end)]

    assert len(items) == 1
    assert items[0].org_names == ["Microsoft Corporation"]

