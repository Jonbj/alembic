"""Alpaca Markets WebSocket news stream connector.

Complements AlpacaNewsConnector (REST polling) with real-time streaming.
Latency from Benzinga publication to callback: typically < 1 second.

Usage: run as a long-lived Celery task or standalone process.
Each received article is queued to the sentiment pipeline via Celery.

WebSocket auto-reconnects on disconnect (handled by alpaca-py internals).
Graceful stop via .stop() sets an asyncio event watched by the run loop.

alpaca-py retries a failed connection with only `asyncio.sleep(0)` between
attempts and logs a full traceback each time: with DNS down (2026-10-02,
2026-10-12/13) that wrote ~3M tracebacks/day and filled the disk. The
reconnect is therefore throttled here with an exponential backoff.
"""

import asyncio
import logging
import time

log = logging.getLogger(__name__)

RECONNECT_BASE_DELAY_S = 1.0
RECONNECT_MAX_DELAY_S = 60.0
# A connection that lasted at least this long counts as healthy: the next
# reconnect starts again without delay.
RECONNECT_STABLE_S = 300.0


class ReconnectBackoff:
    """Delay before the next connection attempt.

    Attempts closer than RECONNECT_STABLE_S to the previous one escalate the
    delay (1s, 2s, 4s … capped at RECONNECT_MAX_DELAY_S); a longer gap means
    the previous connection was healthy and resets it. Attempt start times are
    measured after the wait, so the wait itself never counts as stability.
    """

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._last_start: float | None = None
        self._failures = 0

    def next_delay(self) -> float:
        if self._last_start is None:
            return 0.0
        if self._clock() - self._last_start >= RECONNECT_STABLE_S:
            self._failures = 0
            return 0.0
        self._failures += 1
        return min(
            RECONNECT_MAX_DELAY_S,
            RECONNECT_BASE_DELAY_S * 2 ** (self._failures - 1),
        )

    def mark_start(self) -> None:
        self._last_start = self._clock()


def _build_backoff_stream_cls():
    from alpaca.data.live import NewsDataStream

    class BackoffNewsDataStream(NewsDataStream):
        """NewsDataStream whose (re)connections are throttled by ReconnectBackoff."""

        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self._reconnect_backoff = ReconnectBackoff()

        async def _start_ws(self) -> None:
            delay = self._reconnect_backoff.next_delay()
            if delay:
                log.warning("News stream reconnect in %.0fs", delay)
                await asyncio.sleep(delay)
            self._reconnect_backoff.mark_start()
            await super()._start_ws()

    return BackoffNewsDataStream


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
        return _build_backoff_stream_cls()(
            api_key=self._api_key, secret_key=self._secret_key
        )

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
