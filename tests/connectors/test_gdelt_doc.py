"""GDELT DOC 2.0 connector tests — parse + fetch (mocked aiohttp)."""
from datetime import timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.connectors.gdelt_doc import GdeltDocConnector

_ARTICLE = {
    "url": "https://reuters.com/technology/apple-beats-q3-earnings-2026-07-02",
    "title": "Apple beats Q3 earnings expectations",
    "seendate": "20260702T140000Z",
    "domain": "reuters.com",
    "language": "English",
    "sourcecountry": "United States",
}


def _conn(symbols=None, ticker_names=None):
    return GdeltDocConnector(
        symbols=symbols or ["AAPL"],
        ticker_names=ticker_names or {"AAPL": "Apple Inc"},
    )


def _mock_session(response_body: dict):
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value=response_body)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)
    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session


class TestParseArticle:
    def test_valid_article_returns_news_item(self):
        item = _conn()._parse_article(_ARTICLE, "AAPL")
        assert item is not None
        assert item.source == "gdelt"
        assert item.asset_tags == ["AAPL"]
        assert item.extraction_method == "gdelt_doc"
        assert item.body == "Apple beats Q3 earnings expectations"
        assert item.title == "Apple beats Q3 earnings expectations"
        assert item.timestamp.tzinfo == timezone.utc

    def test_empty_title_returns_none(self):
        assert _conn()._parse_article({**_ARTICLE, "title": ""}, "AAPL") is None

    def test_missing_title_returns_none(self):
        article = {k: v for k, v in _ARTICLE.items() if k != "title"}
        assert _conn()._parse_article(article, "AAPL") is None

    def test_seendate_parsed_as_utc(self):
        item = _conn()._parse_article(_ARTICLE, "AAPL")
        assert item.timestamp.year == 2026
        assert item.timestamp.month == 7
        assert item.timestamp.day == 2
        assert item.timestamp.hour == 14
        assert item.timestamp.tzinfo == timezone.utc

    def test_bad_seendate_falls_back_to_now(self):
        item = _conn()._parse_article({**_ARTICLE, "seendate": "not-a-date"}, "AAPL")
        assert item is not None
        assert item.timestamp.tzinfo == timezone.utc

    def test_id_includes_gdelt_doc_prefix(self):
        item = _conn()._parse_article(_ARTICLE, "AAPL")
        assert item.id.startswith("gdelt_doc:")


@pytest.mark.asyncio
async def test_fetch_yields_tagged_items():
    conn = _conn()
    mock_session = _mock_session({"articles": [_ARTICLE]})

    with patch("src.connectors.gdelt_doc.aiohttp.ClientSession", return_value=mock_session), \
         patch("src.connectors.gdelt_doc.asyncio.sleep", AsyncMock()):
        items = [i async for i in conn.fetch()]

    assert len(items) == 1
    assert items[0].asset_tags == ["AAPL"]
    assert items[0].source == "gdelt"
    assert items[0].extraction_method == "gdelt_doc"


@pytest.mark.asyncio
async def test_fetch_skips_on_rate_limit():
    """429 → skip ticker, no exception propagated (fail-open)."""
    mock_resp = MagicMock()
    mock_resp.status = 429
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)
    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("src.connectors.gdelt_doc.aiohttp.ClientSession", return_value=mock_session), \
         patch("src.connectors.gdelt_doc.asyncio.sleep", AsyncMock()):
        items = [i async for i in _conn().fetch()]

    assert items == []


@pytest.mark.asyncio
async def test_fetch_skips_on_network_error():
    """Connection error → skip ticker, no exception propagated (fail-open)."""
    mock_session = AsyncMock()
    mock_session.get = MagicMock(side_effect=Exception("connection refused"))
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("src.connectors.gdelt_doc.aiohttp.ClientSession", return_value=mock_session), \
         patch("src.connectors.gdelt_doc.asyncio.sleep", AsyncMock()):
        items = [i async for i in _conn().fetch()]

    assert items == []


@pytest.mark.asyncio
async def test_fetch_uses_company_name_in_query():
    """When ticker_names provides a name, GDELT query includes the company name."""
    conn = GdeltDocConnector(symbols=["AAPL"], ticker_names={"AAPL": "Apple Inc"})
    captured: dict = {}

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={"articles": []})
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    def capture_get(url, params=None, **kwargs):
        captured["params"] = params or {}
        return mock_resp

    mock_session = AsyncMock()
    mock_session.get = capture_get
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("src.connectors.gdelt_doc.aiohttp.ClientSession", return_value=mock_session), \
         patch("src.connectors.gdelt_doc.asyncio.sleep", AsyncMock()):
        _ = [i async for i in conn.fetch()]

    assert "Apple Inc" in captured["params"].get("query", "")
    assert "sourcelang:english" in captured["params"].get("query", "")


@pytest.mark.asyncio
async def test_fetch_falls_back_to_cashtag_when_no_name():
    """When no company name is known, query uses $TICKER cashtag."""
    conn = GdeltDocConnector(symbols=["XYZ"], ticker_names={})
    captured: dict = {}

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={"articles": []})
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    def capture_get(url, params=None, **kwargs):
        captured["params"] = params or {}
        return mock_resp

    mock_session = AsyncMock()
    mock_session.get = capture_get
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("src.connectors.gdelt_doc.aiohttp.ClientSession", return_value=mock_session), \
         patch("src.connectors.gdelt_doc.asyncio.sleep", AsyncMock()):
        _ = [i async for i in conn.fetch()]

    assert "$XYZ" in captured["params"].get("query", "")
