"""P2-D: Alpaca WebSocket news streaming worker.

Connects to the Alpaca news WebSocket and pipes real-time articles into the
ingestion + sentiment pipeline, reducing news→signal latency from minutes
(REST polling every 15 min) to < 1 second.

How to run (dedicated long-lived process):
    celery -A src.workers.celery_app worker --loglevel=info -Q news_stream -c 1

The task `run_news_stream` is long-lived. Use a dedicated queue with concurrency=1.

Alternatively, standalone mode (for testing):
    python -m src.workers.news_stream
"""

import logging

from src.workers.celery_app import app

log = logging.getLogger(__name__)


async def _on_news(article) -> None:
    """Callback: persist article to DB then trigger sentiment worker."""
    from datetime import datetime, timezone

    from src.models.news import NewsItem
    from src.store.pg_store import PostgreSQLStore
    from src.workers.sentiment import run_sentiment_worker

    try:
        if hasattr(article, "model_dump"):
            data = article.model_dump()
        elif hasattr(article, "__dict__"):
            data = dict(article.__dict__)
        else:
            data = dict(article)

        headline = data.get("headline", "")
        url = data.get("url", "")
        summary = data.get("summary", "")
        symbols = data.get("symbols", [])
        created_at = data.get("created_at") or datetime.now(timezone.utc)

        log.info("News stream: %s [%s]", headline[:60], symbols)

        # Persist to news_log for each associated ticker
        article_id = str(data.get("id", "")) or url or headline[:64]
        pg = PostgreSQLStore()
        try:
            for sym in symbols:
                item = NewsItem(
                    id=f"{article_id}:{sym}",
                    title=headline,
                    url=url or f"alpaca-stream:{article_id}",
                    source="alpaca_stream",
                    body=summary or headline,
                    timestamp=created_at,
                )
                pg.log_news_item(item, ticker=sym)
        finally:
            pg.close()

        # Trigger sentiment worker immediately (processes all recent unscored news).
        run_sentiment_worker.delay()
        log.debug("News stream triggered sentiment for %s", symbols)

    except Exception as exc:
        log.warning("News stream handler error: %s", exc)


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
    import asyncio
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
