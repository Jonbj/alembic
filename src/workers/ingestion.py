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
from src.connectors.deduplicator import Deduplicator
from src.connectors.gdelt_gkg import GDELTGKGConnector
from src.connectors.ticker_extractor import TickerExtractor
from src.models.news import GKGNewsItem, NewsItem
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
