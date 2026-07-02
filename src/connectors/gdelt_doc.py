"""GDELT DOC 2.0 API connector — per-ticker query, explicit tagging.

Queries the GDELT DOC 2.0 API for each watchlist symbol by company name (or
$TICKER cashtag fallback). Unlike the legacy GKG bulk connector this is:
  - Mirated per ticker (no global-feed download + local filter)
  - Fresh (timespan=12h, sort=DateDesc)
  - Explicitly tagged to the queried ticker (extraction_method='gdelt_doc')
  - Fail-open: per-ticker errors are logged and skipped

NOTE: the DOC artlist endpoint does not include article bodies — only headline
+ metadata. The title is used as body proxy (headline-level sentiment).

API ref: https://api.gdeltproject.org/api/v2/doc/doc
"""
import asyncio
import hashlib
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import aiohttp

from src.connectors.base import NewsConnector
from src.models.news import NewsItem

logger = logging.getLogger(__name__)

_GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
# GDELT enforces "one request every 5 seconds" per IP. We use 6 s to stay safely
# under the limit. At 96 symbols × 6 s ≈ 10 min/cycle; use at most 30 symbols
# for the initial rollout (controlled via the beat schedule symbols list).
_REQ_INTERVAL_S = 6.0


class GdeltDocConnector(NewsConnector):
    """Fetch recent news from GDELT DOC 2.0 API for the configured symbols.

    One request per symbol; each article is explicitly tagged to the queried
    symbol (extraction_method='gdelt_doc'). No API key required.

    Args:
        symbols: Watchlist ticker symbols to query.
        ticker_names: Optional ticker→company-name mapping for building precise
            queries (e.g. {"AAPL": "Apple Inc"}). Missing entries fall back to
            the $TICKER cashtag form.
        timespan: GDELT time window (e.g. "12h", "1d"). Default "12h" aligns
            with _SENTIMENT_MAX_NEWS_AGE_HOURS in the sentiment worker.
        maxrecords: Max articles per symbol. Keep LOW (default 5) to avoid
            flooding the sentiment queue (lesson from Finnhub mini-spike).
    """

    def __init__(
        self,
        symbols: list[str] | None = None,
        ticker_names: dict[str, str] | None = None,
        timespan: str = "12h",
        maxrecords: int = 5,
    ):
        self._symbols = symbols or []
        self._ticker_names = ticker_names or {}
        self._timespan = timespan
        self._maxrecords = maxrecords

    def _build_query(self, symbol: str) -> str:
        """Build the GDELT query string for a symbol.

        Uses the company name when available (more precise), otherwise falls back
        to the $TICKER cashtag form (catches direct cashtag mentions in text).
        """
        name = self._ticker_names.get(symbol)
        if name:
            return f'"{name}" sourcelang:english'
        return f"${symbol} sourcelang:english"

    async def fetch(self) -> AsyncIterator[NewsItem]:
        async with aiohttp.ClientSession() as session:
            for symbol in self._symbols:
                params = {
                    "query": self._build_query(symbol),
                    "mode": "artlist",
                    "timespan": self._timespan,
                    "sort": "DateDesc",
                    "maxrecords": str(self._maxrecords),
                    "format": "json",
                }
                try:
                    async with session.get(_GDELT_DOC_URL, params=params) as resp:
                        if resp.status == 429:
                            logger.warning("GDELT DOC rate limited (429) for %s — skipping", symbol)
                            await asyncio.sleep(_REQ_INTERVAL_S)
                            continue
                        if resp.status != 200:
                            logger.warning("GDELT DOC returned HTTP %d for %s", resp.status, symbol)
                            await asyncio.sleep(_REQ_INTERVAL_S)
                            continue
                        # content_type=None: GDELT sometimes returns text/javascript
                        data = await resp.json(content_type=None)
                except Exception as exc:
                    logger.warning("GDELT DOC fetch failed for %s: %s", symbol, exc)
                    await asyncio.sleep(_REQ_INTERVAL_S)
                    continue

                for article in (data or {}).get("articles") or []:
                    item = self._parse_article(article, symbol)
                    if item is not None:
                        yield item

                await asyncio.sleep(_REQ_INTERVAL_S)

    def _parse_article(self, article: dict, symbol: str) -> NewsItem | None:
        """Convert a GDELT DOC artlist article to a NewsItem. None if title empty."""
        title = (article.get("title") or "").strip()
        if not title:
            return None

        url = article.get("url", "")
        seendate = article.get("seendate", "")
        try:
            ts = datetime.strptime(seendate, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            ts = datetime.now(timezone.utc)

        # Stable per-(article, ticker) ID for dedup — URL alone is not unique when
        # the same article covers multiple symbols.
        uid = hashlib.md5(f"{url}:{symbol}".encode()).hexdigest()[:16]

        return NewsItem(
            id=f"gdelt_doc:{uid}",
            body=title,   # DOC artlist has no body — title is the content
            title=title,
            url=url,
            timestamp=ts,
            source="gdelt",
            asset_tags=[symbol],
            extraction_method="gdelt_doc",
            language="en",
        )
