"""Alpaca Markets WebSocket news stream connector.

Complements AlpacaNewsConnector (REST polling) with real-time streaming.
Latency from Benzinga publication to callback: typically < 1 second.

Usage: run as a long-lived Celery task or standalone process.
Each received article is queued to the sentiment pipeline via Celery.

WebSocket auto-reconnects on disconnect (handled by alpaca-py internals).
Graceful stop via .stop() sets an asyncio event watched by the run loop.
"""

import asyncio
import logging

log = logging.getLogger(__name__)


class AlpacaNewsStreamConnector:
    """Real-time news feed via Alpaca WebSocket.

    Subscribes to news for a list of symbols (or '*' for all news).
    On each article received, calls on_news_callback(article_dict).

    Args:
        api_key: Alpaca API key.
        secret_key: Alpaca secret key.
        symbols: List of ticker symbols to subscribe. Use ['*'] for all news.
        on_news_callback: Async callable(article_dict) called for each article.
    """

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        symbols: list[str],
        on_news_callback,
    ) -> None:
        self._api_key = api_key
        self._secret_key = secret_key
        self._symbols = symbols or ["*"]
        self._on_news_callback = on_news_callback
        self._stream = None
        self._stop_event: asyncio.Event | None = None

    def _build_stream(self):
        from alpaca.data.live import NewsDataStream
        return NewsDataStream(api_key=self._api_key, secret_key=self._secret_key)

    async def _handle_news(self, article) -> None:
        """Handler called by alpaca-py for each incoming article."""
        try:
            if hasattr(article, "model_dump"):
                article_dict = article.model_dump()
            elif hasattr(article, "__dict__"):
                article_dict = dict(article.__dict__)
            else:
                article_dict = dict(article)
            await self._on_news_callback(article_dict)
        except Exception as exc:
            log.warning("News stream handler error: %s", exc)

    def run(self) -> None:
        """Start the WebSocket stream synchronously (blocks until stopped)."""
        log.info("Starting Alpaca news stream for symbols: %s", self._symbols)
        try:
            self._stream = self._build_stream()
            self._stream.subscribe_news(self._handle_news, *self._symbols)
            self._stream.run()
        except Exception as exc:
            log.error("Alpaca news stream terminated: %s", exc)
        finally:
            log.info("Alpaca news stream stopped")

    def stop(self) -> None:
        """Signal the stream to stop gracefully."""
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception as exc:
                log.warning("News stream stop error: %s", exc)
