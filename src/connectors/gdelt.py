"""GDELT news connector."""

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import aiohttp

from src.connectors.base import NewsConnector
from src.models.news import NewsItem
from src.text.sanitizer import sanitize_text

logger = logging.getLogger(__name__)

_GDELT_DOC2_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
_GDELT_BACKOFF_BASE = 2.0  # seconds for exponential backoff
_GDELT_BACKOFF_MAX = 60.0  # max wait between retries
_GDELT_MAX_RETRIES = 5


class GDELTConnector(NewsConnector):
    """GDELT API connector for news ingestion.

    Fetches news articles from GDELT 2.0 API, sanitizes content, and yields
    NewsItem objects. GDELT artlist mode returns titles only; title is used as
    body proxy.
    """

    def __init__(
        self,
        query: str,
        asset_tags: list[str],
        max_records: int = 50,
        timespan: str = "15min",
    ):
        self.query = query
        self.asset_tags = asset_tags
        self.max_records = max_records
        self.timespan = timespan

    async def fetch(self) -> AsyncIterator[NewsItem]:
        """Fetch recent articles using relative timespan (e.g. '15min')."""
        params = {
            "query": self.query,
            "mode": "artlist",
            "maxrecords": self.max_records,
            "format": "json",
            "timespan": self.timespan,
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(_GDELT_DOC2_URL, params=params) as resp:
                resp.raise_for_status()
                data = await resp.json()

        async for item in self._parse_articles(data.get("articles", [])):
            yield item

    async def fetch_historical(
        self,
        start_date: datetime,
        end_date: datetime,
        max_records_per_chunk: int = 250,
    ) -> AsyncIterator[NewsItem]:
        """Fetch articles in [start_date, end_date] chunked by calendar month.

        Makes one API call per month. Uses exponential backoff for rate limiting.
        HTTP errors on a single chunk are logged and skipped.
        """
        current = start_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        async with aiohttp.ClientSession() as session:
            while current <= end_date:
                if current.month == 12:
                    next_month = current.replace(year=current.year + 1, month=1, day=1)
                else:
                    next_month = current.replace(month=current.month + 1, day=1)

                chunk_end = min(next_month - timedelta(seconds=1), end_date)

                params = {
                    "query": self.query,
                    "mode": "artlist",
                    "maxrecords": max_records_per_chunk,
                    "format": "json",
                    "STARTDATETIME": current.strftime("%Y%m%d%H%M%S"),
                    "ENDDATETIME": chunk_end.strftime("%Y%m%d%H%M%S"),
                }

                try:
                    data = await self._fetch_with_backoff(session, params)
                    if data is not None:
                        async for item in self._parse_articles(data.get("articles", [])):
                            yield item
                except Exception as e:
                    logger.warning("GDELT historical chunk %s failed: %s", current.date(), e)

                current = next_month
                await asyncio.sleep(1.0)

    async def _fetch_with_backoff(
        self,
        session: aiohttp.ClientSession,
        params: dict,
    ) -> dict | None:
        """Fetch GDELT API with exponential backoff for rate limiting (HTTP 429)."""
        for attempt in range(_GDELT_MAX_RETRIES):
            try:
                async with session.get(_GDELT_DOC2_URL, params=params) as resp:
                    if resp.status == 429:
                        wait_time = min(_GDELT_BACKOFF_BASE * (2 ** attempt), _GDELT_BACKOFF_MAX)
                        logger.warning("GDELT rate limited, waiting %.1fs before retry", wait_time)
                        await asyncio.sleep(wait_time)
                        continue
                    resp.raise_for_status()
                    return await resp.json()
            except aiohttp.ClientResponseError as e:
                if e.status == 429 and attempt < _GDELT_MAX_RETRIES - 1:
                    continue  # Will retry with backoff
                logger.warning("GDELT HTTP error %s: %s", e.status, e.message)
                return None
        logger.warning("GDELT: Max retries exceeded after rate limiting")
        return None

    async def _parse_articles(self, articles: list[dict]) -> AsyncIterator[NewsItem]:
        """Parse raw GDELT article dicts into sanitized NewsItem objects.

        Articles with invalid/missing timestamps are skipped to avoid look-ahead bias.
        """
        for article in articles:
            title = article.get("title", "")
            if not title:
                continue
            clean_title = sanitize_text(title)
            raw_date = article.get("seendate", "")
            try:
                ts = datetime.strptime(raw_date, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                # Skip articles with invalid timestamps to avoid look-ahead bias
                # Using datetime.now() would corrupt historical backtest data
                logger.warning("Invalid timestamp %s for article %s, skipping", raw_date, article.get("url"))
                continue
            yield NewsItem(
                id=article.get("url", ""),
                source="gdelt",
                timestamp=ts,
                title=clean_title,
                body=clean_title,
                url=article.get("url", ""),
                language="en",
                asset_tags=self.asset_tags,
            )
