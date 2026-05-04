"""GDELT news connector."""

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import aiohttp

from src.connectors.base import NewsConnector
from src.models.news import NewsItem
from src.text.sanitizer import sanitize_text

_GDELT_DOC2_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


class GDELTConnector(NewsConnector):
    """GDELT API connector for news ingestion.

    Fetches recent news articles from the GDELT 2.0 API, sanitizes content,
    and yields NewsItem objects asynchronously.

    Note:
        GDELT artlist mode returns only article titles (no full body).
        The title is used as a proxy for the body field.
    """

    def __init__(
        self,
        query: str,
        asset_tags: list[str],
        max_records: int = 50,
        timespan: str = "15min",
    ):
        """Initialize GDELT connector.

        Args:
            query: GDELT query string (e.g., "Federal Reserve interest rates")
            asset_tags: List of asset tags to associate with all items
            max_records: Maximum number of articles to fetch (default 50)
            timespan: Time window for search (default "15min")
        """
        self.query = query
        self.asset_tags = asset_tags
        self.max_records = max_records
        self.timespan = timespan

    async def fetch(self) -> AsyncIterator[NewsItem]:
        """Fetch and yield sanitized NewsItem objects from GDELT API.

        Yields:
            NewsItem objects with sanitized title (title used as body proxy)

        Note:
            - GDELT artlist mode provides title only
            - Title is used as body proxy
            - Skips items without title
            - Falls back to now() if timestamp parsing fails
        """
        params = {
            "query": self.query,
            "mode": "artlist",
            "maxrecords": self.max_records,
            "format": "json",
            "timespan": self.timespan,
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(_GDELT_DOC2_URL, params=params) as resp:
                data = await resp.json(content_type=None)

        for article in data.get("articles", []):
            title = article.get("title", "")

            # Skip items without title
            if not title:
                continue

            # Sanitize title
            try:
                clean_title = sanitize_text(title)
            except ValueError:
                # Homoglyph attack detected — skip item
                continue

            # Parse timestamp (format: YYYYMMDDTHHMMSSZ)
            raw_date = article.get("seendate", "")
            try:
                ts = datetime.strptime(raw_date, "%Y%m%dT%H%M%SZ").replace(
                    tzinfo=timezone.utc
                )
            except (ValueError, TypeError):
                # Fallback to now() if parsing fails
                ts = datetime.now(timezone.utc)

            yield NewsItem(
                id=article.get("url", ""),
                source="gdelt",
                timestamp=ts,
                title=clean_title,
                body=clean_title,  # GDELT artlist provides title only; use as proxy
                url=article.get("url", ""),
                language="en",
                asset_tags=self.asset_tags,
            )
