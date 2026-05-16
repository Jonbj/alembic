"""Tests for AlpacaNewsConnector."""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.connectors.alpaca_news import AlpacaNewsConnector, AlpacaNewsAuthError
from src.models.news import NewsItem


# --- skeleton ---

def test_connector_instantiates():
    conn = AlpacaNewsConnector(api_key="key", api_secret="secret", symbols=["AAPL"])
    assert conn is not None


def test_raises_auth_error_class_exists():
    with pytest.raises(AlpacaNewsAuthError):
        raise AlpacaNewsAuthError("bad creds")


# --- fetch_historical ---

_FAKE_RESPONSE = {
    "news": [
        {
            "id": 12345,
            "headline": "Apple reports record Q4 earnings",
            "summary": "Apple Inc. reported record fourth-quarter earnings on Thursday.",
            "content": "<p>Apple Inc. reported record fourth-quarter earnings...</p>",
            "url": "https://example.com/apple-q4",
            "created_at": "2025-11-05T20:30:00Z",
            "updated_at": "2025-11-05T20:30:00Z",
            "author": "Jane Doe",
            "source": "Benzinga",
            "symbols": ["AAPL"],
            "images": [],
        }
    ],
    "next_page_token": None,
}


@pytest.mark.asyncio
async def test_fetch_historical_yields_news_items():
    """Connector yields NewsItem with body=summary (Benzinga articles)."""
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value=_FAKE_RESPONSE)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    conn = AlpacaNewsConnector(api_key="key", api_secret="secret", symbols=["AAPL"])
    start = datetime(2025, 11, 1, tzinfo=timezone.utc)
    end = datetime(2025, 11, 30, tzinfo=timezone.utc)

    with patch("src.connectors.alpaca_news.aiohttp.ClientSession", return_value=mock_session):
        items = [item async for item in conn.fetch_historical(start, end)]

    assert len(items) == 1
    item = items[0]
    assert isinstance(item, NewsItem)
    assert "Apple Inc. reported record fourth-quarter earnings" in item.body
    assert item.url == "https://example.com/apple-q4"
    assert item.source == "alpaca_benzinga"
    assert "AAPL" in item.asset_tags


@pytest.mark.asyncio
async def test_skips_articles_with_no_text():
    """Articles with empty summary and content are not yielded."""
    fake_response = {
        "news": [
            {
                "id": 99,
                "headline": "Some headline",
                "summary": "",
                "content": "",
                "url": "https://example.com/empty",
                "created_at": "2025-11-05T10:00:00Z",
                "updated_at": "2025-11-05T10:00:00Z",
                "author": "",
                "source": "Benzinga",
                "symbols": ["GS"],
                "images": [],
            }
        ],
        "next_page_token": None,
    }
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value=fake_response)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    conn = AlpacaNewsConnector(api_key="key", api_secret="secret", symbols=["GS"])
    start = datetime(2025, 11, 1, tzinfo=timezone.utc)
    end = datetime(2025, 11, 30, tzinfo=timezone.utc)

    with patch("src.connectors.alpaca_news.aiohttp.ClientSession", return_value=mock_session):
        items = [item async for item in conn.fetch_historical(start, end)]

    assert items == []


@pytest.mark.asyncio
async def test_raises_auth_error_on_403():
    """Raises AlpacaNewsAuthError on HTTP 403."""
    mock_resp = AsyncMock()
    mock_resp.status = 403
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    conn = AlpacaNewsConnector(api_key="bad", api_secret="bad", symbols=["AAPL"])
    start = datetime(2025, 11, 1, tzinfo=timezone.utc)
    end = datetime(2025, 11, 30, tzinfo=timezone.utc)

    with patch("src.connectors.alpaca_news.aiohttp.ClientSession", return_value=mock_session):
        with pytest.raises(AlpacaNewsAuthError):
            async for _ in conn.fetch_historical(start, end):
                pass


@pytest.mark.asyncio
async def test_sends_auth_headers():
    """Sends APCA-API-KEY-ID and APCA-API-SECRET-KEY headers."""
    captured_kwargs: dict = {}

    def fake_get(url, params=None, headers=None):
        captured_kwargs["headers"] = headers or {}
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = AsyncMock(return_value={"news": [], "next_page_token": None})
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        return mock_resp

    mock_session = AsyncMock()
    mock_session.get = fake_get
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    conn = AlpacaNewsConnector(api_key="MY_KEY", api_secret="MY_SECRET", symbols=["AAPL"])
    start = datetime(2025, 11, 1, tzinfo=timezone.utc)
    end = datetime(2025, 11, 30, tzinfo=timezone.utc)

    with patch("src.connectors.alpaca_news.aiohttp.ClientSession", return_value=mock_session):
        async for _ in conn.fetch_historical(start, end):
            pass

    assert captured_kwargs["headers"]["APCA-API-KEY-ID"] == "MY_KEY"
    assert captured_kwargs["headers"]["APCA-API-SECRET-KEY"] == "MY_SECRET"


@pytest.mark.asyncio
async def test_paginates_with_next_page_token():
    """Follows next_page_token to fetch subsequent pages."""
    page1 = {
        "news": [
            {
                "id": 1,
                "headline": "Article 1",
                "summary": "First article summary.",
                "content": "",
                "url": "https://example.com/1",
                "created_at": "2025-11-05T10:00:00Z",
                "updated_at": "2025-11-05T10:00:00Z",
                "author": "",
                "source": "Benzinga",
                "symbols": ["AAPL"],
                "images": [],
            }
        ],
        "next_page_token": "token-abc",
    }
    page2 = {
        "news": [
            {
                "id": 2,
                "headline": "Article 2",
                "summary": "Second article summary.",
                "content": "",
                "url": "https://example.com/2",
                "created_at": "2025-11-04T10:00:00Z",
                "updated_at": "2025-11-04T10:00:00Z",
                "author": "",
                "source": "Benzinga",
                "symbols": ["AAPL"],
                "images": [],
            }
        ],
        "next_page_token": None,
    }

    call_count = 0

    def fake_get(url, params=None, headers=None):
        nonlocal call_count
        call_count += 1
        response_data = page1 if call_count == 1 else page2
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = AsyncMock(return_value=response_data)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        return mock_resp

    mock_session = AsyncMock()
    mock_session.get = fake_get
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    conn = AlpacaNewsConnector(api_key="key", api_secret="secret", symbols=["AAPL"])
    start = datetime(2025, 11, 1, tzinfo=timezone.utc)
    end = datetime(2025, 11, 30, tzinfo=timezone.utc)

    with patch("src.connectors.alpaca_news.aiohttp.ClientSession", return_value=mock_session):
        items = [item async for item in conn.fetch_historical(start, end)]

    assert len(items) == 2
    assert call_count == 2
