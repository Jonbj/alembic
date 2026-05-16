"""NewsIngestionWorker — fetches broad financial news, extracts tickers, enqueues.

This is the **orchestrator** of the news-driven pipeline. It runs as a Celery
task every 15 minutes (Mon–Fri market hours) and performs three steps:

  1. **Fetch** — calls `GDELTGKGConnector.fetch()` to retrieve recent financial
     news with organisation names from GDELT GKG.
  2. **Extract** — passes org names to `TickerExtractor`, which queries the
     PostgreSQL `ticker_lookup` table and returns ticker symbols.
  3. **Enqueue** — for each ticker found, builds a `NewsItem` with
     `asset_tags=[ticker]`, deduplicates by `(url, ticker)` via
     `Deduplicator.is_duplicate_by_id`, and pushes to Redis `news:queue`.

Multi-ticker articles:
  - An article mentioning Apple + Microsoft generates **two** separate
    `NewsItem` objects, each with a distinct `id="{url}:{ticker}"`.
  - This allows the SentimentWorker (downstream) to process each ticker
    independently while sharing the same article content.

Stats returned:
  - The Celery task returns a dict with keys:
    `fetched`, `tickers_found`, `discarded`, `queued`, `duplicates`.
    Useful for monitoring dashboards and alerting on ingestion health.

Connection lifecycle:
  - Redis and PostgreSQL connections are opened once per task invocation
    and closed in a `finally` block to avoid resource leaks during retries.
"""

import asyncio
import logging

import psycopg2
from redis import Redis

from src.config import config
from src.connectors.alpaca_news import AlpacaNewsConnector
from src.connectors.deduplicator import Deduplicator
from src.connectors.gdelt_gkg import GDELTGKGConnector
from src.connectors.marketaux import MarketAuxConnector
from src.connectors.ticker_extractor import TickerExtractor
from src.models.news import GKGNewsItem, MarketAuxNewsItem, NewsItem
from src.workers.celery_app import app

log = logging.getLogger(__name__)


async def _fetch_gkg_items(connector: GDELTGKGConnector) -> list[GKGNewsItem]:
    """Drain the async GDELT GKG iterator into a concrete list.

    This wrapper exists because the Celery task body is synchronous
    (Celery worker threads), while the connector is async. We bridge
    the two worlds by calling `asyncio.run()` once in the task entry-point
    and collecting all items before entering the synchronous `_process_gkg_items`.
    """
    return [item async for item in connector.fetch()]


def _process_gkg_items(
    gkg_items: list[GKGNewsItem],
    extractor: TickerExtractor,
    deduplicator: Deduplicator,
    redis_client: Redis,
) -> dict:
    """Extract tickers, deduplicate, and push annotated NewsItems to news:queue.

    This is a **pure function** (aside from Redis/Deduplicator I/O) to allow
    easy unit testing without a live Celery broker.

    Args:
        gkg_items: Raw GKG records from GDELT.
        extractor: TickerExtractor instance (with open PG connection).
        deduplicator: Deduplicator instance (with open Redis connection).
        redis_client: Redis client for LPUSH to news:queue.

    Returns:
        Stats dict with keys:
          - fetched:       total GKG records processed
          - tickers_found:   total ticker symbols extracted (before dedup)
          - discarded:       articles with zero ticker matches
          - queued:          items actually pushed to Redis
          - duplicates:      items skipped because (url, ticker) already seen
    """
    stats = {"fetched": 0, "tickers_found": 0, "discarded": 0, "queued": 0, "duplicates": 0}

    for gkg_item in gkg_items:
        stats["fetched"] += 1

        # Step 1: ticker extraction from organisation names
        tickers = extractor.extract(gkg_item.org_names)
        if not tickers:
            # No recognised company → article is irrelevant for trading signals.
            # Logged at DEBUG, not WARNING, because this is expected for many
            # generic financial news items (e.g. "Federal Reserve" has no ticker).
            stats["discarded"] += 1
            log.debug("No ticker found for %s (org_names=%s), discarding", gkg_item.url, gkg_item.org_names)
            continue

        stats["tickers_found"] += len(tickers)

        # Step 2: expand each ticker into a separate NewsItem
        for ticker in tickers:
            item = NewsItem(
                id=f"{gkg_item.url}:{ticker}",  # Composite ID for dedup by (url, ticker).
                source=gkg_item.source,
                timestamp=gkg_item.timestamp,
                title=gkg_item.title,
                body=gkg_item.body,
                url=gkg_item.url,
                language=gkg_item.language,
                asset_tags=[ticker],  # SentimentWorker consumes asset_tags[0].
            )

            # Step 3: deduplication
            if deduplicator.is_duplicate_by_id(item):
                stats["duplicates"] += 1
                continue

            # Step 4: enqueue to Redis
            redis_client.rpush("news:queue", item.model_dump_json())
            stats["queued"] += 1

    return stats


async def _fetch_marketaux_items(connector: MarketAuxConnector) -> list[MarketAuxNewsItem]:
    """Drain the async MarketAux iterator into a concrete list."""
    return [item async for item in connector.fetch()]


def _process_marketaux_items(
    items: list[MarketAuxNewsItem],
    deduplicator: Deduplicator,
    redis_client: Redis,
) -> dict:
    """Expand per-ticker, deduplicate, and push MarketAuxNewsItems to news:queue.

    Why expand per-ticker?
      Same reason as GDELT: an article mentioning AAPL + MSFT generates two
      independent SentimentWorker jobs so each ticker gets its own score.
      Each per-ticker item carries the article-level marketaux_sentiment so
      the SentimentWorker can apply the neutral pre-filter independently.
    """
    stats = {"fetched": 0, "tickers_found": 0, "queued": 0, "duplicates": 0}

    for item in items:
        stats["fetched"] += 1

        if not item.asset_tags:
            continue

        stats["tickers_found"] += len(item.asset_tags)

        for ticker in item.asset_tags:
            per_ticker = MarketAuxNewsItem(
                id=f"{item.url}:{ticker}",
                source=item.source,
                timestamp=item.timestamp,
                title=item.title,
                body=item.body,
                url=item.url,
                language=item.language,
                asset_tags=[ticker],
                marketaux_sentiment=item.marketaux_sentiment,
            )

            if deduplicator.is_duplicate_by_id(per_ticker):
                stats["duplicates"] += 1
                continue

            redis_client.rpush("news:queue", per_ticker.model_dump_json())
            stats["queued"] += 1

    return stats


@app.task(name="src.workers.ingestion.run_marketaux_ingestion_worker")
def run_marketaux_ingestion_worker() -> dict:
    """Celery entry-point for MarketAux news ingestion.

    Fetches recent articles for WATCHLIST_SYMBOLS from MarketAux, expands
    per-ticker, deduplicates, and pushes MarketAuxNewsItems to news:queue.

    Scheduling:
      - Celery beat: every 15 min, Mon–Fri 14:00–21:00 UTC
      - 28 calls/market session — well within the 100 req/day free-tier limit.

    Returns:
        Stats dict: fetched, tickers_found, queued, duplicates.
        Returns {"skipped": True} if MARKETAUX_API_KEY is not configured.
    """
    redis_client = Redis.from_url(config.REDIS_URL)

    if not config.MARKETAUX_API_KEY:
        log.warning("MARKETAUX_API_KEY not configured — skipping MarketAux ingestion")
        redis_client.close()
        return {"skipped": True, "reason": "no_api_key"}

    try:
        connector = MarketAuxConnector(
            api_key=config.MARKETAUX_API_KEY,
            symbols=config.WATCHLIST_SYMBOLS or [],
        )
        deduplicator = Deduplicator(redis_client)

        items = asyncio.run(_fetch_marketaux_items(connector))
        stats = _process_marketaux_items(items, deduplicator, redis_client)

        log.info("MarketAux ingestion stats: %s", stats)
        return stats

    finally:
        redis_client.close()


async def _fetch_alpaca_items(connector: AlpacaNewsConnector) -> list[NewsItem]:
    """Drain the async Alpaca News iterator into a concrete list."""
    return [item async for item in connector.fetch()]


def _process_alpaca_items(
    items: list[NewsItem],
    deduplicator: Deduplicator,
    redis_client: Redis,
) -> dict:
    """Expand per-ticker, deduplicate, and push Alpaca NewsItems to news:queue.

    Alpaca articles already contain US ticker symbols in asset_tags (from
    Benzinga metadata). No TickerExtractor needed.
    """
    stats = {"fetched": 0, "tickers_found": 0, "queued": 0, "duplicates": 0}

    for item in items:
        stats["fetched"] += 1

        if not item.asset_tags:
            continue

        stats["tickers_found"] += len(item.asset_tags)

        for ticker in item.asset_tags:
            per_ticker = NewsItem(
                id=f"{item.id}:{ticker}",
                source=item.source,
                timestamp=item.timestamp,
                title=item.title,
                body=item.body,
                url=item.url,
                language=item.language,
                asset_tags=[ticker],
            )

            if deduplicator.is_duplicate_by_id(per_ticker):
                stats["duplicates"] += 1
                continue

            redis_client.rpush("news:queue", per_ticker.model_dump_json())
            stats["queued"] += 1

    return stats


@app.task(name="src.workers.ingestion.run_alpaca_ingestion_worker")
def run_alpaca_ingestion_worker() -> dict:
    """Celery entry-point for Alpaca/Benzinga news ingestion.

    Fetches recent Benzinga articles for WATCHLIST_SYMBOLS via Alpaca News API,
    expands per-ticker, deduplicates, and pushes NewsItems to news:queue.

    Scheduling:
      - Celery beat: every 15 min, Mon–Fri 14:00–21:00 UTC (aligned with
        GDELT and MarketAux ingestion tasks).

    Returns:
        Stats dict: fetched, tickers_found, queued, duplicates.
        Returns {"skipped": True} if Alpaca credentials are not configured.
    """
    redis_client = Redis.from_url(config.REDIS_URL)

    if not config.ALPACA_API_KEY or not config.ALPACA_SECRET_KEY:
        log.warning("ALPACA_API_KEY/SECRET not configured — skipping Alpaca ingestion")
        redis_client.close()
        return {"skipped": True, "reason": "no_credentials"}

    try:
        connector = AlpacaNewsConnector(
            api_key=config.ALPACA_API_KEY,
            api_secret=config.ALPACA_SECRET_KEY,
            symbols=config.WATCHLIST_SYMBOLS or [],
        )
        deduplicator = Deduplicator(redis_client)

        items = asyncio.run(_fetch_alpaca_items(connector))
        stats = _process_alpaca_items(items, deduplicator, redis_client)

        log.info("Alpaca ingestion stats: %s", stats)
        return stats

    finally:
        redis_client.close()


@app.task(name="src.workers.ingestion.run_news_ingestion_worker")
def run_news_ingestion_worker() -> dict:
    """Celery entry-point for NewsIngestionWorker.

    Fetches broad financial news from GDELT GKG, extracts tickers via
    PostgreSQL lookup, deduplicates by (url, ticker), and pushes annotated
    NewsItems to news:queue for the SentimentWorker to consume.

    Scheduling:
      - Celery beat: every 15 min, Mon–Fri 14:00–21:00 UTC
        (configured in src/workers/celery_app.py).

    Returns:
        Stats dict (see `_process_gkg_items`).
    """
    # Open connections once per task. Closed in finally to avoid leaks.
    redis_client = Redis.from_url(config.REDIS_URL)
    pg_conn = psycopg2.connect(config.DATABASE_URL)

    try:
        connector = GDELTGKGConnector()
        extractor = TickerExtractor(pg_conn)
        deduplicator = Deduplicator(redis_client)

        # Bridge async fetch into sync Celery task
        gkg_items = asyncio.run(_fetch_gkg_items(connector))
        stats = _process_gkg_items(gkg_items, extractor, deduplicator, redis_client)

        log.info("Ingestion stats: %s", stats)
        return stats

    finally:
        pg_conn.close()
        redis_client.close()
