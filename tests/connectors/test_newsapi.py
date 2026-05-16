"""Tests for NewsAPIConnector."""
import pytest
from src.connectors.newsapi import NewsAPIConnector, NewsAPIAuthError, NewsAPIRateLimitError


def test_connector_instantiates():
    conn = NewsAPIConnector(api_key="test-key")
    assert conn is not None


def test_raises_auth_error_class_exists():
    with pytest.raises(NewsAPIAuthError):
        raise NewsAPIAuthError("bad key")


def test_raises_rate_limit_error_class_exists():
    with pytest.raises(NewsAPIRateLimitError):
        raise NewsAPIRateLimitError("limit reached")


from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_fetch_historical_yields_news_items():
    """Connector yields NewsItem with body=description+content."""
    fake_response = {
        "articles": [
            {
                "title": "Goldman Sachs Q3 results",
                "description": "GS beats expectations",
                "content": "Revenue up 12% year-over-year [+]",
                "url": "https://example.com/gs-q3",
                "publishedAt": "2025-11-05T10:00:00Z",
                "source": {"name": "Reuters"},
            }
        ]
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

    conn = NewsAPIConnector(api_key="test-key")
    start = datetime(2025, 11, 1, tzinfo=timezone.utc)
    end = datetime(2025, 11, 30, tzinfo=timezone.utc)

    with patch("src.connectors.newsapi.aiohttp.ClientSession", return_value=mock_session):
        items = [item async for item in conn.fetch_historical("GS", "Goldman Sachs Group Inc", start, end)]

    assert len(items) == 1
    assert items[0].body == "GS beats expectations Revenue up 12% year-over-year [+]"
    assert items[0].url == "https://example.com/gs-q3"
    assert items[0].asset_tags == ["GS"]
    assert items[0].source == "newsapi"


@pytest.mark.asyncio
async def test_skips_articles_with_no_text():
    """Articles with empty description and content are not yielded."""
    fake_response = {
        "articles": [
            {
                "title": "Some article",
                "description": "",
                "content": None,
                "url": "https://example.com/empty",
                "publishedAt": "2025-11-05T10:00:00Z",
                "source": {"name": "Test"},
            }
        ]
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

    conn = NewsAPIConnector(api_key="test-key")
    start = datetime(2025, 11, 1, tzinfo=timezone.utc)
    end = datetime(2025, 11, 30, tzinfo=timezone.utc)

    with patch("src.connectors.newsapi.aiohttp.ClientSession", return_value=mock_session):
        items = [item async for item in conn.fetch_historical("GS", "Goldman Sachs", start, end)]

    assert items == []


@pytest.mark.asyncio
async def test_raises_rate_limit_error_at_budget():
    """Raises NewsAPIRateLimitError when request budget is exhausted."""
    conn = NewsAPIConnector(api_key="test-key", max_requests_per_day=2)
    conn._requests_made = 2  # already at limit

    start = datetime(2025, 11, 1, tzinfo=timezone.utc)
    end = datetime(2025, 11, 30, tzinfo=timezone.utc)

    with pytest.raises(NewsAPIRateLimitError):
        async for _ in conn.fetch_historical("GS", "Goldman Sachs", start, end):
            pass


@pytest.mark.asyncio
async def test_raises_auth_error_on_401():
    """Raises NewsAPIAuthError when API returns 401."""
    mock_resp = AsyncMock()
    mock_resp.status = 401
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    conn = NewsAPIConnector(api_key="bad-key")
    start = datetime(2025, 11, 1, tzinfo=timezone.utc)
    end = datetime(2025, 11, 30, tzinfo=timezone.utc)

    with patch("src.connectors.newsapi.aiohttp.ClientSession", return_value=mock_session):
        with pytest.raises(NewsAPIAuthError):
            async for _ in conn.fetch_historical("GS", "Goldman Sachs", start, end):
                pass


@pytest.mark.asyncio
async def test_uses_ticker_symbol_when_no_company_name():
    """Uses ticker symbol as query when company_name is empty."""
    captured_params = {}

    def fake_get(url, params=None):
        captured_params.update(params or {})
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = AsyncMock(return_value={"articles": []})
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        return mock_resp

    mock_session = AsyncMock()
    mock_session.get = fake_get
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    conn = NewsAPIConnector(api_key="test-key")
    start = datetime(2025, 11, 1, tzinfo=timezone.utc)
    end = datetime(2025, 11, 30, tzinfo=timezone.utc)

    with patch("src.connectors.newsapi.aiohttp.ClientSession", return_value=mock_session):
        async for _ in conn.fetch_historical("GS", "", start, end):
            pass

    assert captured_params["q"] == "GS"
