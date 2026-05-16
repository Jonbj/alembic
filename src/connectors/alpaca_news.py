"""Alpaca Markets news connector — secondary live news source (Benzinga).

Free tier: 200 req/min, ~130-160 full articles/day from Benzinga.
Requires Alpaca API key (same credentials used for paper/live trading).

Key advantage: zero marginal cost when already using Alpaca for execution.
Benzinga is a premium financial news source with full article text.

Limitation: ~130-160 full articles/day on free tier. For 30 tickers at
~5 articles/ticker/day = 150 articles — right at the daily cap. On heavy
news days some articles may be missed; use MarketAux as primary source.
"""

import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import aiohttp

from src.connectors.base import NewsConnector
from src.models.news import NewsItem

logger = logging.getLogger(__name__)

_ALPACA_NEWS_URL = "https://data.alpaca.markets/v1beta1/news"


class AlpacaNewsAuthError(Exception):
    """Raised on HTTP 401/403 — invalid API key or secret."""


class AlpacaNewsConnector(NewsConnector):
    """Fetch financial news from Alpaca Markets v1beta1/news (Benzinga source).

    Implements NewsConnector ABC.

    - fetch(): returns recent articles for configured symbols (live use).
    - fetch_historical(): paginates via next_page_token over a date range.

    Auth: header-based (APCA-API-KEY-ID / APCA-API-SECRET-KEY), same
    credentials as the Alpaca execution broker — no extra account needed.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        symbols: list[str] | None = None,
        page_size: int = 50,
    ):
        self._api_key = api_key
        self._api_secret = api_secret
        self._symbols = symbols or []
        self._page_size = min(page_size, 50)  # Alpaca max is 50

    @property
    def _headers(self) -> dict:
        return {
            "APCA-API-KEY-ID": self._api_key,
            "APCA-API-SECRET-KEY": self._api_secret,
        }

    async def fetch(self) -> AsyncIterator[NewsItem]:
        """Poll most recent articles for the configured symbols (live trading).

        Returns the latest page without date filtering. Call every ~5 minutes;
        deduplication is handled upstream by the Redis deduplicator (TTL 2h).
        """
        params = self._build_params(limit=self._page_size)

        async with aiohttp.ClientSession() as session:
            async with session.get(_ALPACA_NEWS_URL, params=params, headers=self._headers) as resp:
                self._check_status(resp.status)
                resp.raise_for_status()
                data = await resp.json()

        for article in data.get("news", []):
            item = self._parse_article(article)
            if item is not None:
                yield item

    async def fetch_historical(
        self,
        start: datetime,
        end: datetime,
    ) -> AsyncIterator[NewsItem]:
        """Paginate through articles for the configured symbols over a date range.

        Uses cursor-based pagination (next_page_token). Stops when
        next_page_token is None (last page reached).

        Args:
            start: Start of range (UTC).
            end: End of range (UTC).
        """
        page_token: str | None = None

        while True:
            params = self._build_params(
                start=start,
                end=end,
                limit=self._page_size,
                page_token=page_token,
            )

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    _ALPACA_NEWS_URL, params=params, headers=self._headers
                ) as resp:
                    self._check_status(resp.status)
                    resp.raise_for_status()
                    data = await resp.json()

            for article in data.get("news", []):
                item = self._parse_article(article)
                if item is not None:
                    yield item

            page_token = data.get("next_page_token")
            if not page_token:
                break

    def _build_params(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 50,
        page_token: str | None = None,
    ) -> dict:
        params: dict = {"limit": limit, "sort": "desc"}
        if self._symbols:
            params["symbols"] = ",".join(self._symbols)
        if start:
            params["start"] = start.strftime("%Y-%m-%dT%H:%M:%SZ")
        if end:
            params["end"] = end.strftime("%Y-%m-%dT%H:%M:%SZ")
        if page_token:
            params["page_token"] = page_token
        return params

    def _check_status(self, status: int) -> None:
        if status in (401, 403):
            raise AlpacaNewsAuthError(
                f"Alpaca News returned {status} — check ALPACA_API_KEY / ALPACA_SECRET_KEY"
            )
        if status >= 500:
            logger.warning("Alpaca News server error %d — skipping page", status)

    def _parse_article(self, article: dict) -> NewsItem | None:
        """Convert an Alpaca news article dict to a NewsItem.

        Body: summary (preferred) or content (HTML-stripped fallback).
        Returns None if both are empty.
        """
        summary = (article.get("summary") or "").strip()
        content_raw = (article.get("content") or "").strip()

        # Strip basic HTML tags from content if summary is empty
        if not summary and content_raw:
            import re
            content_clean = re.sub(r"<[^>]+>", " ", content_raw).strip()
            content_clean = re.sub(r"\s+", " ", content_clean)
            body = content_clean
        else:
            body = summary

        if not body:
            return None

        url = article.get("url", "")
        headline = article.get("headline", "")
        created_at = article.get("created_at", "")
        symbols = article.get("symbols") or []

        try:
            ts = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            ts = datetime.now(timezone.utc)

        return NewsItem(
            id=f"alpaca:{article.get('id', url)}",
            body=body,
            title=headline,
            url=url,
            timestamp=ts,
            source="alpaca_benzinga",
            asset_tags=symbols or list(self._symbols),
            language="en",
        )
