"""Finnhub connector: explicit ticker tagging (source_metadata), no NER."""
from datetime import timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.connectors.finnhub_news import FinnhubNewsConnector

_ARTICLE = {
    "id": 123, "headline": "Apple beats earnings", "summary": "Apple reported strong Q3.",
    "url": "https://ex.com/a", "datetime": 1782950400, "source": "CNBC", "related": "AAPL",
}


def _conn():
    return FinnhubNewsConnector(api_key="k", symbols=["AAPL"])


class TestParseArticle:
    def test_valid_article(self):
        item = _conn()._parse_article(_ARTICLE, "AAPL")
        assert item is not None
        assert item.source == "finnhub"
        assert item.asset_tags == ["AAPL"]
        assert item.extraction_method == "source_metadata"   # curated, not NER
        assert item.body == "Apple reported strong Q3."
        assert item.title == "Apple beats earnings"
        assert item.timestamp.tzinfo is not None

    def test_empty_text_returns_none(self):
        assert _conn()._parse_article({"id": 1, "headline": "", "summary": ""}, "AAPL") is None

    def test_headline_only_used_as_body(self):
        item = _conn()._parse_article({"id": 2, "headline": "Breaking", "summary": ""}, "AAPL")
        assert item is not None and item.body == "Breaking"

    def test_bad_datetime_does_not_crash(self):
        item = _conn()._parse_article({"id": 3, "headline": "x", "summary": "y", "datetime": "oops"}, "AAPL")
        assert item is not None and item.timestamp.tzinfo == timezone.utc


@pytest.mark.asyncio
async def test_fetch_yields_tagged_items():
    conn = FinnhubNewsConnector(api_key="k", symbols=["AAPL"])
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value=[_ARTICLE])
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)
    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("src.connectors.finnhub_news.aiohttp.ClientSession", return_value=mock_session), \
         patch("src.connectors.finnhub_news.asyncio.sleep", AsyncMock()):
        items = [i async for i in conn.fetch()]

    assert len(items) == 1
    assert items[0].asset_tags == ["AAPL"]
    assert items[0].source == "finnhub"
    assert items[0].extraction_method == "source_metadata"
