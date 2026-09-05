"""P2-D: Alpaca WebSocket news streaming worker.

Connects to the Alpaca news WebSocket and pipes real-time articles into the
ingestion + sentiment pipeline, reducing news→signal latency from minutes
(REST polling every 15 min) to < 1 second.

How to run (dedicated long-lived process, as deployed by Docker Compose):
    python -m src.workers.news_stream

The Celery task `run_news_stream` remains available for installations that use
a dedicated `news_stream` queue with concurrency=1. Do not run it on a shared
worker: the task blocks for the lifetime of the WebSocket connection.
"""

import logging

from redis import Redis

from src.config import config
from src.connectors.alpaca_news import AlpacaNewsConnector
from src.connectors.deduplicator import Deduplicator
from src.workers.celery_app import app

log = logging.getLogger(__name__)


def _process_alpaca_items(*args, **kwargs):
    from src.workers.ingestion import _process_alpaca_items as process

    return process(*args, **kwargs)


def _persist_ingestion_observability(*args, **kwargs) -> None:
    from src.workers.ingestion import _persist_ingestion_observability as persist

    persist(*args, **kwargs)


async def _on_news(article) -> None:
    """Callback: apply the REST ingestion contract, then trigger inference."""
    redis_client = None

    try:
        if hasattr(article, "model_dump"):
            data = article.model_dump()
        elif hasattr(article, "__dict__"):
            data = dict(article.__dict__)
        else:
            data = dict(article)

        parser = AlpacaNewsConnector(
            api_key="",
            api_secret="",
            symbols=list(config.WATCHLIST_SYMBOLS or []),
        )
        item = parser._parse_article(data)
        if item is None:
            log.debug("News stream discarded article without usable text")
            return

        log.info("News stream: %s [%s]", item.title[:60], item.asset_tags)
        redis_client = Redis.from_url(config.REDIS_URL)
        discard_rows: list[dict] = []
        stats = _process_alpaca_items(
            [item],
            Deduplicator(redis_client),
            redis_client,
            discard_rows=discard_rows,
        )
        _persist_ingestion_observability("alpaca_benzinga", stats, discard_rows)

        if stats["queued"]:
            # The stream process never loads FinBERT/Ollama: inference remains
            # isolated on worker-inference, as in the periodic REST path.
            app.send_task(
                "src.workers.sentiment.run_sentiment_worker", queue="inference"
            )
            log.debug("News stream triggered sentiment for %s", item.asset_tags)

    except Exception as exc:
        log.warning("News stream handler error: %s", exc)
    finally:
        if redis_client is not None:
            redis_client.close()


@app.task(name="src.workers.news_stream.run_news_stream", bind=True,
          max_retries=3, default_retry_delay=30)
def run_news_stream(self) -> dict:
    """Long-lived task: connect to Alpaca news WebSocket and stream to sentiment pipeline.

    Designed for a dedicated worker with concurrency=1 (-Q news_stream -c 1).
    Auto-retries up to 3 times on disconnect/error.
    """
    from src.config import config
    from src.connectors.alpaca_news_stream import AlpacaNewsStreamConnector

    if not config.ALPACA_API_KEY or not config.ALPACA_SECRET_KEY:
        log.warning("Alpaca credentials not configured — news stream task skipped")
        return {"skipped": True, "reason": "no_credentials"}

    symbols = list(config.WATCHLIST_SYMBOLS or ["*"])
    log.info("Starting Alpaca news WebSocket stream for %d symbols", len(symbols))

    connector = AlpacaNewsStreamConnector(
        api_key=config.ALPACA_API_KEY,
        secret_key=config.ALPACA_SECRET_KEY,
        symbols=symbols,
        on_news_callback=_on_news,
    )

    try:
        connector.run()
        return {"status": "stream_ended"}
    except Exception as exc:
        log.error("News stream error: %s — retrying", exc)
        raise self.retry(exc=exc)


if __name__ == "__main__":
    import logging as _logging

    from src.config import config
    from src.connectors.alpaca_news_stream import AlpacaNewsStreamConnector

    _logging.basicConfig(level=logging.INFO)

    async def _print_article(article) -> None:
        if hasattr(article, "model_dump"):
            data = article.model_dump()
        else:
            data = dict(article)
        print(f"[STREAM] {data.get('created_at')} {data.get('symbols')} — {data.get('headline', '')[:80]}")

    connector = AlpacaNewsStreamConnector(
        api_key=config.ALPACA_API_KEY,
        secret_key=config.ALPACA_SECRET_KEY,
        symbols=list(config.WATCHLIST_SYMBOLS or ["*"]),
        on_news_callback=_print_article,
    )
    print("Starting news stream (Ctrl+C to stop)…")
    connector.run()
