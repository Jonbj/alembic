"""NewsAPI v2 connector for enriched article text backfill."""

import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import aiohttp

from src.connectors.base import NewsConnector
from src.models.news import NewsItem

logger = logging.getLogger(__name__)

_NEWSAPI_BASE_URL = "https://newsapi.org/v2/everything"
_DEFAULT_MAX_REQUESTS = 95  # stay under free tier limit of 100/day


class NewsAPIAuthError(Exception):
    """Raised when NewsAPI returns HTTP 401 (invalid or missing API key)."""


class NewsAPIRateLimitError(Exception):
    """Raised when the daily request budget is exhausted."""


class NewsAPIPaidPlanError(Exception):
    """Raised when the query requires a paid NewsAPI plan (HTTP 426).

    The free plan only allows articles from the past month. Historical
    queries (>30 days ago) require the Developer plan or higher.
    """


class NewsAPIConnector(NewsConnector):
    """Fetch articles from NewsAPI v2 /everything endpoint.

    Implements NewsConnector ABC. Primary use: historical backfill by
    ticker+company name for a date range.

    Rate limiting: raises NewsAPIRateLimitError when _requests_made
    reaches max_requests_per_day. The caller should catch this and stop
    gracefully rather than aborting.
    """

    def __init__(self, api_key: str, max_requests_per_day: int = _DEFAULT_MAX_REQUESTS):
        self._api_key = api_key
        self._max_requests = max_requests_per_day
        self._requests_made = 0

    async def fetch(self) -> AsyncIterator[NewsItem]:
        """Live fetch — not implemented yet (backfill only for now)."""
        return
        yield  # make it an async generator

    async def fetch_historical(
        self,
        ticker: str,
        company_name: str,
        start: datetime,
        end: datetime,
    ) -> AsyncIterator[NewsItem]:
        """Fetch articles for one ticker over a date range.

        Args:
            ticker: Stock ticker symbol, e.g. "GS"
            company_name: Full company name for search, e.g. "Goldman Sachs Group Inc"
            start: Start datetime (UTC)
            end: End datetime (UTC)

        Yields:
            NewsItem with body=description+content, url, timestamp, source="newsapi"

        Raises:
            NewsAPIRateLimitError: when request budget exhausted
            NewsAPIAuthError: when API key is invalid (HTTP 401)
        """
        if self._requests_made >= self._max_requests:
            raise NewsAPIRateLimitError(
                f"Daily request budget exhausted ({self._requests_made}/{self._max_requests})"
            )

        query = company_name.strip() if company_name.strip() else ticker
        params = {
            "q": query,
            "from": start.date().isoformat(),
            "to": end.date().isoformat(),
            "language": "en",
            "pageSize": 100,
            "sortBy": "publishedAt",
            "apiKey": self._api_key,
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(_NEWSAPI_BASE_URL, params=params) as resp:
                self._requests_made += 1

                if resp.status == 401:
                    raise NewsAPIAuthError("NewsAPI returned 401 — check NEWSAPI_KEY")
                if resp.status == 426:
                    raise NewsAPIPaidPlanError(
                        "NewsAPI returned 426 — free plan only allows articles from the past "
                        "month. Upgrade to Developer plan for historical data."
                    )
                if resp.status == 429:
                    raise NewsAPIRateLimitError("NewsAPI returned 429 — daily limit reached")
                if resp.status >= 500:
                    logger.warning(
                        "NewsAPI server error %d for ticker %s — skipping", resp.status, ticker
                    )
                    return

                resp.raise_for_status()
                data = await resp.json()

        for article in data.get("articles", []):
            item = self._parse_article(article, ticker)
            if item is not None:
                yield item

    def _parse_article(self, article: dict, ticker: str) -> NewsItem | None:
        """Convert a NewsAPI article dict to a NewsItem.

        Returns None if both description and content are empty.
        """
        description = (article.get("description") or "").strip()
        content = (article.get("content") or "").strip()
        body = f"{description} {content}".strip()

        if not body:
            return None

        url = article.get("url", "")
        title = article.get("title", "")
        published_at = article.get("publishedAt", "")

        try:
            ts = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            ts = datetime.now(timezone.utc)

        return NewsItem(
            id=f"{url}:{ticker}",
            body=body,
            title=title,
            url=url,
            timestamp=ts,
            source="newsapi",
            asset_tags=[ticker],
            language="en",
        )
