"""Tests for MarketAuxConnector."""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.connectors.marketaux import MarketAuxConnector, MarketAuxRateLimitError, MarketAuxAuthError
from src.models.news import MarketAuxNewsItem


# --- skeleton ---

def test_connector_instantiates():
    conn = MarketAuxConnector(api_key="test-key", symbols=["AAPL", "MSFT"])
    assert conn is not None


def test_raises_auth_error_class_exists():
    with pytest.raises(MarketAuxAuthError):
        raise MarketAuxAuthError("bad key")


def test_raises_rate_limit_error_class_exists():
    with pytest.raises(MarketAuxRateLimitError):
        raise MarketAuxRateLimitError("limit reached")


# --- fetch_historical ---

_FAKE_RESPONSE_ONE_PAGE = {
    "meta": {"found": 1, "returned": 1, "limit": 3, "page": 1},
    "data": [
        {
            "uuid": "abc-123",
            "title": "Apple hits all-time high",
            "description": "Apple shares rose sharply after earnings beat.",
            "snippet": "Revenue up 15% year-over-year.",
            "url": "https://example.com/apple-ath",
            "published_at": "2025-11-05T14:00:00Z",
            "source": "reuters.com",
            "entities": [
                {
                    "symbol": "AAPL",
                    "name": "Apple Inc",
                    "exchange": "NASDAQ",
                    "sentiment": "positive",
                    "sentiment_score": 0.72,
                }
            ],
        }
    ],
}


@pytest.mark.asyncio
async def test_fetch_historical_yields_marketaux_news_items():
    """Connector yields MarketAuxNewsItem with body=description+snippet and sentiment."""
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = AsyncMock(return_value=_FAKE_RESPONSE_ONE_PAGE)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    conn = MarketAuxConnector(api_key="test-key", symbols=["AAPL"])
    start = datetime(2025, 11, 1, tzinfo=timezone.utc)
    end = datetime(2025, 11, 30, tzinfo=timezone.utc)

    with patch("src.connectors.marketaux.aiohttp.ClientSession", return_value=mock_session):
        items = [item async for item in conn.fetch_historical(start, end)]

    assert len(items) == 1
    item = items[0]
    assert isinstance(item, MarketAuxNewsItem)
    assert item.body == "Apple shares rose sharply after earnings beat. Revenue up 15% year-over-year."
    assert item.url == "https://example.com/apple-ath"
    assert item.source == "marketaux"
    assert item.marketaux_sentiment == pytest.approx(0.72)
    assert "AAPL" in item.asset_tags


@pytest.mark.asyncio
async def test_skips_articles_with_no_text():
    """Articles with empty description and snippet are not yielded."""
    fake_response = {
        "meta": {"found": 1, "returned": 1, "limit": 3, "page": 1},
        "data": [
            {
                "uuid": "xyz",
                "title": "Some title",
                "description": "",
                "snippet": None,
                "url": "https://example.com/empty",
                "published_at": "2025-11-05T14:00:00Z",
                "source": "test.com",
                "entities": [],
            }
        ],
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

    conn = MarketAuxConnector(api_key="test-key", symbols=["AAPL"])
    start = datetime(2025, 11, 1, tzinfo=timezone.utc)
    end = datetime(2025, 11, 30, tzinfo=timezone.utc)

    with patch("src.connectors.marketaux.aiohttp.ClientSession", return_value=mock_session):
        items = [item async for item in conn.fetch_historical(start, end)]

    assert items == []


@pytest.mark.asyncio
async def test_raises_rate_limit_when_budget_exhausted():
    """Raises MarketAuxRateLimitError when request budget is exhausted before fetch."""
    conn = MarketAuxConnector(api_key="test-key", symbols=["AAPL"], max_requests_per_day=2)
    conn._requests_made = 2

    start = datetime(2025, 11, 1, tzinfo=timezone.utc)
    end = datetime(2025, 11, 30, tzinfo=timezone.utc)

    with pytest.raises(MarketAuxRateLimitError):
        async for _ in conn.fetch_historical(start, end):
            pass


@pytest.mark.asyncio
async def test_raises_auth_error_on_401():
    """Raises MarketAuxAuthError on HTTP 401."""
    mock_resp = AsyncMock()
    mock_resp.status = 401
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    conn = MarketAuxConnector(api_key="bad-key", symbols=["AAPL"])
    start = datetime(2025, 11, 1, tzinfo=timezone.utc)
    end = datetime(2025, 11, 30, tzinfo=timezone.utc)

    with patch("src.connectors.marketaux.aiohttp.ClientSession", return_value=mock_session):
        with pytest.raises(MarketAuxAuthError):
            async for _ in conn.fetch_historical(start, end):
                pass


@pytest.mark.asyncio
async def test_uses_symbols_as_query_param():
    """Passes symbols as comma-separated query parameter."""
    captured_params = {}

    def fake_get(url, params=None):
        captured_params.update(params or {})
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = AsyncMock(return_value={"meta": {"found": 0, "returned": 0, "limit": 3, "page": 1}, "data": []})
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        return mock_resp

    mock_session = AsyncMock()
    mock_session.get = fake_get
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    conn = MarketAuxConnector(api_key="test-key", symbols=["AAPL", "MSFT", "GS"])
    start = datetime(2025, 11, 1, tzinfo=timezone.utc)
    end = datetime(2025, 11, 30, tzinfo=timezone.utc)

    with patch("src.connectors.marketaux.aiohttp.ClientSession", return_value=mock_session):
        async for _ in conn.fetch_historical(start, end):
            pass

    assert captured_params["symbols"] == "AAPL,MSFT,GS"


@pytest.mark.asyncio
async def test_sentiment_is_none_when_no_matching_entity():
    """marketaux_sentiment is None when no entity matches the article's symbols."""
    fake_response = {
        "meta": {"found": 1, "returned": 1, "limit": 3, "page": 1},
        "data": [
            {
                "uuid": "no-entity",
                "title": "Market news",
                "description": "General market update.",
                "snippet": "Stocks rose.",
                "url": "https://example.com/market",
                "published_at": "2025-11-05T14:00:00Z",
                "source": "bloomberg.com",
                "entities": [],  # no entity → no sentiment
            }
        ],
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

    conn = MarketAuxConnector(api_key="test-key", symbols=["AAPL"])
    start = datetime(2025, 11, 1, tzinfo=timezone.utc)
    end = datetime(2025, 11, 30, tzinfo=timezone.utc)

    with patch("src.connectors.marketaux.aiohttp.ClientSession", return_value=mock_session):
        items = [item async for item in conn.fetch_historical(start, end)]

    assert len(items) == 1
    assert items[0].marketaux_sentiment is None
