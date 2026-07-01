"""Finnhub company-news connector — clean explicit ticker tagging (US equities).

Each article is tagged to the queried symbol via Finnhub's per-company endpoint, so no
NER/regex extraction is needed (extraction_method='source_metadata', like Alpaca/Benzinga)
— which is the whole point: it kills ticker false positives at the source. Free tier:
60 req/min, US company news. We use the ticker-tagged articles, NOT the (premium)
aggregated sentiment score — sentiment stays our LLM's job.

Docs: https://finnhub.io/docs/api/company-news
"""
import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import aiohttp

from src.connectors.base import NewsConnector
from src.models.news import NewsItem

logger = logging.getLogger(__name__)

_FINNHUB_NEWS_URL = "https://finnhub.io/api/v1/company-news"
# ~55 req/min, comfortably under the 60/min free-tier limit (96 symbols ≈ 2 min/cycle).
_REQ_INTERVAL_S = 1.1


class FinnhubNewsConnector(NewsConnector):
    """Fetch per-company news from Finnhub for the configured symbols.

    Implements NewsConnector ABC. One request per symbol over a recent date window;
    each returned article is tagged to that symbol (curated, not inferred).
    """

    def __init__(self, api_key: str, symbols: list[str] | None = None, lookback_days: int = 1):
        self._api_key = api_key
        self._symbols = symbols or []
        self._lookback_days = max(1, lookback_days)

    async def fetch(self) -> AsyncIterator[NewsItem]:
        today = datetime.now(timezone.utc).date()
        frm = (today - timedelta(days=self._lookback_days)).isoformat()
        to = today.isoformat()

        async with aiohttp.ClientSession() as session:
            for symbol in self._symbols:
                params = {"symbol": symbol, "from": frm, "to": to, "token": self._api_key}
                try:
                    async with session.get(_FINNHUB_NEWS_URL, params=params) as resp:
                        if resp.status == 429:
                            logger.warning("Finnhub rate limited (429) on %s — backing off", symbol)
                            await asyncio.sleep(2.0)
                            continue
                        if resp.status != 200:
                            logger.warning("Finnhub returned %d for %s", resp.status, symbol)
                            await asyncio.sleep(_REQ_INTERVAL_S)
                            continue
                        articles = await resp.json()
                except Exception as exc:
                    logger.warning("Finnhub fetch failed for %s: %s", symbol, exc)
                    articles = None

                for article in articles or []:
                    item = self._parse_article(article, symbol)
                    if item is not None:
                        yield item

                await asyncio.sleep(_REQ_INTERVAL_S)  # throttle to the free-tier limit

    def _parse_article(self, article: dict, symbol: str) -> NewsItem | None:
        """Convert a Finnhub company-news article to a NewsItem. None if empty text."""
        summary = (article.get("summary") or "").strip()
        headline = (article.get("headline") or "").strip()
        body = summary or headline
        if not body:
            return None

        url = article.get("url", "")
        ts_unix = article.get("datetime")
        try:
            ts = (
                datetime.fromtimestamp(int(ts_unix), tz=timezone.utc)
                if ts_unix else datetime.now(timezone.utc)
            )
        except (ValueError, TypeError, OSError):
            ts = datetime.now(timezone.utc)

        # Tag to the queried symbol — an explicit curated tag, never NER inference.
        return NewsItem(
            id=f"finnhub:{article.get('id', url)}",
            body=body,
            title=headline,
            url=url,
            timestamp=ts,
            source="finnhub",
            asset_tags=[symbol],
            extraction_method="source_metadata",
            language="en",
        )
