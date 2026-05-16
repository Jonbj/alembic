"""MarketAux news connector — primary live news source.

Free tier: 100 req/day, 3 articles/req, real-time included.
Paid Basic ($29/mo): 2,500 req/day, 20 articles/req.

Key advantage over NewsAPI: real-time on free tier + pre-computed entity sentiment.
The sentiment_score per entity allows pre-filtering before LLM inference, reducing
token spend by ~60-80% on neutral articles.
"""

import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import aiohttp

from src.connectors.base import NewsConnector
from src.models.news import MarketAuxNewsItem

logger = logging.getLogger(__name__)

_MARKETAUX_BASE_URL = "https://api.marketaux.com/v1/news/all"
_DEFAULT_MAX_REQUESTS = 95


class MarketAuxAuthError(Exception):
    """Raised on HTTP 401 — invalid API key."""


class MarketAuxRateLimitError(Exception):
    """Raised when the daily request budget is exhausted."""


class MarketAuxConnector(NewsConnector):
    """Fetch financial news from MarketAux v1 API.

    Implements NewsConnector ABC.

    - fetch(): polls recent articles for the configured symbols (live use,
      call every 5 min).
    - fetch_historical(): paginates over a date range (backtest use).

    Both yield MarketAuxNewsItem which extends NewsItem with marketaux_sentiment
    (the pre-computed entity sentiment score, -1 to +1). Downstream workers can
    use this to skip near-zero articles before spending LLM tokens.
    """

    def __init__(
        self,
        api_key: str,
        symbols: list[str] | None = None,
        max_requests_per_day: int = _DEFAULT_MAX_REQUESTS,
    ):
        self._api_key = api_key
        self._symbols = symbols or []
        self._max_requests = max_requests_per_day
        self._requests_made = 0

    async def fetch(self) -> AsyncIterator[MarketAuxNewsItem]:
        """Poll recent articles for the configured symbols (live trading).

        Fetches the latest page (no date filter) — intended to be called
        every ~5 minutes by the live ingestion worker. Deduplication is
        handled upstream by the Redis deduplicator (TTL 2h).
        """
        if self._requests_made >= self._max_requests:
            raise MarketAuxRateLimitError(
                f"Daily budget exhausted ({self._requests_made}/{self._max_requests})"
            )

        params = self._build_params(page=1)

        async with aiohttp.ClientSession() as session:
            async with session.get(_MARKETAUX_BASE_URL, params=params) as resp:
                self._requests_made += 1
                self._check_status(resp.status)
                resp.raise_for_status()
                data = await resp.json()

        for article in data.get("data", []):
            item = self._parse_article(article)
            if item is not None:
                yield item

    async def fetch_historical(
        self,
        start: datetime,
        end: datetime,
    ) -> AsyncIterator[MarketAuxNewsItem]:
        """Paginate through articles for the configured symbols over a date range.

        Stops when all pages are exhausted or the rate limit is hit.

        Args:
            start: Start of range (UTC).
            end: End of range (UTC).
        """
        page = 1

        while True:
            if self._requests_made >= self._max_requests:
                raise MarketAuxRateLimitError(
                    f"Daily budget exhausted ({self._requests_made}/{self._max_requests})"
                )

            params = self._build_params(
                page=page,
                published_after=start.strftime("%Y-%m-%dT%H:%M"),
                published_before=end.strftime("%Y-%m-%dT%H:%M"),
            )

            async with aiohttp.ClientSession() as session:
                async with session.get(_MARKETAUX_BASE_URL, params=params) as resp:
                    self._requests_made += 1
                    self._check_status(resp.status)
                    resp.raise_for_status()
                    data = await resp.json()

            articles = data.get("data", [])
            meta = data.get("meta", {})

            for article in articles:
                item = self._parse_article(article)
                if item is not None:
                    yield item

            # Stop when this page returned fewer items than the limit (last page)
            # or when there are no more results
            returned = meta.get("returned", 0)
            limit = meta.get("limit", 3)
            if returned < limit or returned == 0:
                break

            page += 1

    def _build_params(
        self,
        page: int = 1,
        published_after: str | None = None,
        published_before: str | None = None,
    ) -> dict:
        params: dict = {
            "api_token": self._api_key,
            "language": "en",
            "page": page,
        }
        if self._symbols:
            params["symbols"] = ",".join(self._symbols)
        if published_after:
            params["published_after"] = published_after
        if published_before:
            params["published_before"] = published_before
        return params

    def _check_status(self, status: int) -> None:
        if status == 401:
            raise MarketAuxAuthError("MarketAux returned 401 — check MARKETAUX_API_KEY")
        if status == 429:
            raise MarketAuxRateLimitError("MarketAux returned 429 — daily limit reached")
        if status >= 500:
            logger.warning("MarketAux server error %d — skipping page", status)

    def _parse_article(self, article: dict) -> MarketAuxNewsItem | None:
        """Convert a MarketAux article dict to a MarketAuxNewsItem.

        Returns None if both description and snippet are empty.
        """
        description = (article.get("description") or "").strip()
        snippet = (article.get("snippet") or "").strip()
        body = f"{description} {snippet}".strip()

        if not body:
            return None

        url = article.get("url", "")
        title = article.get("title", "")
        published_at = article.get("published_at", "")
        source_domain = article.get("source", "marketaux")

        try:
            ts = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            ts = datetime.now(timezone.utc)

        # Extract ticker symbols and sentiment from entities
        entities = article.get("entities") or []
        asset_tags = [e["symbol"] for e in entities if e.get("symbol")]

        # Use the sentiment of the first matching entity (highest confidence)
        sentiment: float | None = None
        for entity in entities:
            score = entity.get("sentiment_score")
            if score is not None:
                sentiment = float(score)
                break

        return MarketAuxNewsItem(
            id=f"{url}",
            body=body,
            title=title,
            url=url,
            timestamp=ts,
            source="marketaux",
            asset_tags=asset_tags or list(self._symbols),
            language="en",
            marketaux_sentiment=sentiment,
        )
