"""NewsIngestionWorker — fetches broad financial news, extracts tickers, enqueues."""

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
    return [item async for item in connector.fetch()]


def _process_gkg_items(
    gkg_items: list[GKGNewsItem],
    extractor: TickerExtractor,
    deduplicator: Deduplicator,
    redis_client: Redis,
) -> dict:
    """Extract tickers, deduplicate, and push annotated NewsItems to news:queue.

    Returns a stats dict with keys: fetched, tickers_found, discarded, queued, duplicates.
    """
    stats = {"fetched": 0, "tickers_found": 0, "discarded": 0, "queued": 0, "duplicates": 0}

    for gkg_item in gkg_items:
        stats["fetched"] += 1
        tickers = extractor.extract(gkg_item.org_names)
        if not tickers:
            stats["discarded"] += 1
            continue

        stats["tickers_found"] += len(tickers)
        for ticker in tickers:
            item = NewsItem(
                id=f"{gkg_item.url}:{ticker}",
                source=gkg_item.source,
                timestamp=gkg_item.timestamp,
                title=gkg_item.title,
                body=gkg_item.body,
                url=gkg_item.url,
                language=gkg_item.language,
                asset_tags=[ticker],
            )
            if deduplicator.is_duplicate_by_id(item):
                stats["duplicates"] += 1
                continue
            redis_client.rpush("news:queue", item.model_dump_json())
            stats["queued"] += 1

    return stats


@app.task(name="src.workers.ingestion.run_news_ingestion_worker")
def run_news_ingestion_worker() -> dict:
    """Celery entry-point for NewsIngestionWorker.

    Fetches broad financial news from GDELT GKG, extracts tickers via
    PostgreSQL lookup, deduplicates by (url, ticker), and pushes annotated
    NewsItems to news:queue for the SentimentWorker to consume.
    """
    redis_client = Redis.from_url(config.REDIS_URL)
    pg_conn = psycopg2.connect(config.DATABASE_URL)

    try:
        connector = GDELTGKGConnector()
        extractor = TickerExtractor(pg_conn)
        deduplicator = Deduplicator(redis_client)

        gkg_items = asyncio.run(_fetch_gkg_items(connector))
        stats = _process_gkg_items(gkg_items, extractor, deduplicator, redis_client)

        log.info("Ingestion stats: %s", stats)
        return stats

    finally:
        pg_conn.close()
        redis_client.close()
