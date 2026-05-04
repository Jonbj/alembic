"""RSS feed news connector."""

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from time import struct_time

import feedparser

from src.connectors.base import NewsConnector
from src.models.news import NewsItem
from src.text.sanitizer import sanitize_text


class RSSConnector(NewsConnector):
    """RSS feed connector for news ingestion.

    Fetches news items from RSS feeds, sanitizes content, and yields
    NewsItem objects asynchronously.
    """

    def __init__(self, feed_url: str, source_name: str, asset_tags: list[str]):
        """Initialize RSS connector.

        Args:
            feed_url: URL of the RSS feed
            source_name: Name of the news source (e.g., "reuters", "cnbc")
            asset_tags: List of asset tags to associate with all items
        """
        self.feed_url = feed_url
        self.source_name = source_name
        self.asset_tags = asset_tags

    async def fetch(self) -> AsyncIterator[NewsItem]:
        """Fetch and yield sanitized NewsItem objects from the RSS feed.

        Yields:
            NewsItem objects with sanitized title and body

        Note:
            - Uses asyncio.get_running_loop() for executor
            - Skips items with empty body
            - Skips items where sanitization fails (homoglyph attack)
        """
        loop = asyncio.get_running_loop()

        # Parse feed in executor to avoid blocking
        feed = await loop.run_in_executor(None, feedparser.parse, self.feed_url)

        for entry in feed.get("entries", []):
            # Extract body from summary or content
            body = entry.get("summary", "") or entry.get("content", [{}])[0].get("value", "")

            # Skip items with empty body
            if not body.strip():
                continue

            # Sanitize body and title
            try:
                clean_body = sanitize_text(body)
                clean_title = sanitize_text(entry.get("title", ""))
            except ValueError:
                # Homoglyph attack detected — skip item
                continue

            # Parse timestamp
            ts = entry.get("published_parsed")
            if ts and isinstance(ts, struct_time):
                timestamp = datetime(*ts[:6], tzinfo=timezone.utc)
            else:
                timestamp = datetime.now(timezone.utc)

            yield NewsItem(
                id=entry.get("id", entry.get("link", "")),
                source=self.source_name,
                timestamp=timestamp,
                title=clean_title,
                body=clean_body,
                url=entry.get("link", ""),
                language="en",
                asset_tags=self.asset_tags,
            )
