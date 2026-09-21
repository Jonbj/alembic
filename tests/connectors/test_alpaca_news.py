"""Tests for AlpacaNewsConnector."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.connectors.alpaca_news import AlpacaNewsAuthError, AlpacaNewsConnector
from src.models.news import NewsItem
from src.text.sanitizer import sanitize_text

# --- skeleton ---

def test_connector_instantiates():
    conn = AlpacaNewsConnector(api_key="key", api_secret="secret", symbols=["AAPL"])
    assert conn is not None


def test_raises_auth_error_class_exists():
    with pytest.raises(AlpacaNewsAuthError):
        raise AlpacaNewsAuthError("bad creds")


def test_build_params_requests_full_content():
    conn = AlpacaNewsConnector(api_key="key", api_secret="secret", symbols=["AAPL"])

    assert conn._build_params()["include_content"] == "true"


def test_parse_article_prefers_html_stripped_content():
    conn = AlpacaNewsConnector(api_key="key", api_secret="secret", symbols=["AAPL"])
    article = {
        "id": 1,
        "headline": "Apple raises guidance",
        "summary": "Short teaser.",
        "content": "<p>Apple raised guidance.</p><p>Revenue accelerated.</p>",
        "url": "https://example.com/apple-guidance",
        "created_at": "2026-09-01T10:00:00Z",
        "symbols": ["AAPL"],
    }

    item = conn._parse_article(article)

    assert item is not None
    assert item.body == "Apple raised guidance. Revenue accelerated."


def test_parse_article_falls_back_to_summary_when_content_is_empty():
    conn = AlpacaNewsConnector(api_key="key", api_secret="secret", symbols=["AAPL"])
    article = {
        "id": 2,
        "headline": "Apple raises guidance",
        "summary": "Summary remains available.",
        "content": "   ",
        "url": "https://example.com/apple-summary",
        "created_at": "2026-09-01T10:00:00Z",
        "symbols": ["AAPL"],
    }

    item = conn._parse_article(article)

    assert item is not None
    assert item.body == "Summary remains available."


def test_long_content_supplies_full_downstream_body_limit():
    conn = AlpacaNewsConnector(api_key="key", api_secret="secret", symbols=["AAPL"])
    article = {
        "id": 3,
        "headline": "Apple reports results",
        "summary": "Short teaser.",
        "content": f"<p>{'A' * 400}</p><p>{'B' * 400}</p>",
        "url": "https://example.com/apple-results",
        "created_at": "2026-09-01T10:00:00Z",
        "symbols": ["AAPL"],
    }

    item = conn._parse_article(article)

    assert item is not None
    scored_body = sanitize_text(item.body)[:600]
    assert len(scored_body) == 600
    assert "<p>" not in scored_body


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
    """Connector yields NewsItem with the full Benzinga article body."""
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


# --- fetch_historical_raw (#610) ---

_FAKE_RESPONSE_WITH_EMPTY_BODY = {
    "news": [
        {
            "id": 1,
            "headline": "Apple reports record Q4 earnings",
            "summary": "Apple Inc. reported record fourth-quarter earnings.",
            "content": "<p>Full body.</p>",
            "url": "https://example.com/a",
            "created_at": "2025-11-05T20:30:00Z",
            "symbols": ["AAPL"],
        },
        {
            # Nessun corpo: fetch_historical lo scarta, l'archivio deve vederlo.
            "id": 2,
            "headline": "If You Invested $1000 In Apple 10 Years Ago",
            "summary": "",
            "content": "",
            "url": "https://example.com/b",
            "created_at": "2025-11-05T21:00:00Z",
            "symbols": ["AAPL", "MSFT"],
        },
    ],
    "next_page_token": None,
}


def _mock_session_returning(*payloads: dict):
    """Sessione aiohttp finta che restituisce i payload in ordine, uno per pagina."""
    responses = []
    for payload in payloads:
        resp = AsyncMock()
        resp.status = 200
        resp.raise_for_status = MagicMock()
        resp.json = AsyncMock(return_value=payload)
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        responses.append(resp)

    session = AsyncMock()
    session.get = MagicMock(side_effect=responses)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


@pytest.mark.asyncio
async def test_fetch_historical_raw_keeps_articles_that_the_parsed_path_drops():
    """L'archivio conserva gli articoli senza corpo; il path live li scarta.

    E' la distinzione che regge H-A della #610: un articolo senza summary ne'
    content non e' un template CONTENT_EMPTY (quelli il testo ce l'hanno), ed
    e' invisibile alla pipeline. Misurarli insieme confonderebbe due gruppi.
    """
    conn = AlpacaNewsConnector(api_key="key", api_secret="secret", symbols=["AAPL"])
    start = datetime(2025, 11, 1, tzinfo=timezone.utc)
    end = datetime(2025, 11, 30, tzinfo=timezone.utc)

    with patch(
        "src.connectors.alpaca_news.aiohttp.ClientSession",
        return_value=_mock_session_returning(_FAKE_RESPONSE_WITH_EMPTY_BODY),
    ):
        raw = [a async for a in conn.fetch_historical_raw(start, end)]

    with patch(
        "src.connectors.alpaca_news.aiohttp.ClientSession",
        return_value=_mock_session_returning(_FAKE_RESPONSE_WITH_EMPTY_BODY),
    ):
        parsed = [i async for i in conn.fetch_historical(start, end)]

    assert [a["id"] for a in raw] == [1, 2]
    assert len(parsed) == 1
    # i campi che la misura usa sopravvivono intatti
    assert raw[1]["symbols"] == ["AAPL", "MSFT"]
    assert raw[1]["created_at"] == "2025-11-05T21:00:00Z"
    assert raw[1]["headline"].startswith("If You Invested")


@pytest.mark.asyncio
async def test_fetch_historical_raw_follows_the_page_token() -> None:
    first = dict(_FAKE_RESPONSE_WITH_EMPTY_BODY, next_page_token="pag2")
    second = {"news": [dict(_FAKE_RESPONSE["news"][0], id=3)], "next_page_token": None}

    conn = AlpacaNewsConnector(api_key="key", api_secret="secret", symbols=["AAPL"])
    with patch(
        "src.connectors.alpaca_news.aiohttp.ClientSession",
        return_value=_mock_session_returning(first, second),
    ):
        raw = [
            a
            async for a in conn.fetch_historical_raw(
                datetime(2025, 11, 1, tzinfo=timezone.utc),
                datetime(2025, 11, 30, tzinfo=timezone.utc),
            )
        ]

    assert [a["id"] for a in raw] == [1, 2, 3]
