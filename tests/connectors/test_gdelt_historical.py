"""Tests for GDELTConnector.fetch_historical."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.connectors.gdelt import GDELTConnector

SAMPLE_ARTICLE = {
    "url": "https://reuters.com/1",
    "title": "AAPL earnings beat",
    "seendate": "20240115T100000Z",
}


def make_mock_resp(articles: list[dict]) -> AsyncMock:
    resp = AsyncMock()
    resp.json = AsyncMock(return_value={"articles": articles})
    resp.raise_for_status = MagicMock()  # synchronous in real aiohttp
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)
    return resp


@pytest.mark.asyncio
async def test_fetch_historical_yields_items():
    connector = GDELTConnector(query='"AAPL"', asset_tags=["AAPL"])
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 31, tzinfo=timezone.utc)

    with patch("aiohttp.ClientSession.get", return_value=make_mock_resp([SAMPLE_ARTICLE])):
        with patch("asyncio.sleep"):
            items = [item async for item in connector.fetch_historical(start, end)]

    assert len(items) == 1
    assert items[0].title == "AAPL earnings beat"
    assert items[0].source == "gdelt"


@pytest.mark.asyncio
async def test_fetch_historical_makes_one_call_per_month():
    """A 3-month range produces exactly 3 API calls."""
    connector = GDELTConnector(query='"AAPL"', asset_tags=["AAPL"])
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 3, 31, tzinfo=timezone.utc)

    call_count = 0

    def counting_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return make_mock_resp([])

    with patch("aiohttp.ClientSession.get", side_effect=counting_get):
        with patch("asyncio.sleep"):
            _ = [item async for item in connector.fetch_historical(start, end)]

    assert call_count == 3


@pytest.mark.asyncio
async def test_fetch_historical_continues_on_http_error():
    """Error on chunk 1 is skipped; chunk 2 articles are still yielded."""
    connector = GDELTConnector(query='"AAPL"', asset_tags=["AAPL"])
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 2, 28, tzinfo=timezone.utc)

    call_count = 0

    def failing_then_ok(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("HTTP 429")
        return make_mock_resp([SAMPLE_ARTICLE])

    with patch("aiohttp.ClientSession.get", side_effect=failing_then_ok):
        with patch("asyncio.sleep"):
            items = [item async for item in connector.fetch_historical(start, end)]

    assert len(items) == 1  # chunk 1 failed, chunk 2 succeeded


@pytest.mark.asyncio
async def test_fetch_historical_uses_gdelt_datetime_params():
    """STARTDATETIME and ENDDATETIME are sent in GDELT format."""
    connector = GDELTConnector(query='"MSFT"', asset_tags=["MSFT"])
    start = datetime(2024, 6, 1, tzinfo=timezone.utc)
    end = datetime(2024, 6, 30, tzinfo=timezone.utc)
    captured = {}

    def capture_get(url, params=None, **kwargs):
        captured.update(params or {})
        return make_mock_resp([])

    with patch("aiohttp.ClientSession.get", side_effect=capture_get):
        with patch("asyncio.sleep"):
            _ = [item async for item in connector.fetch_historical(start, end)]

    assert captured["STARTDATETIME"] == "20240601000000"
    assert "ENDDATETIME" in captured
