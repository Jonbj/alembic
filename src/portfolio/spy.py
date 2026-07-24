"""Bounded, fail-open SPY close history loader shared by API projections."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from src.config import config

log = logging.getLogger(__name__)


def spy_fetch_end_date(to_date: str, today: date) -> date:
    """Cap at yesterday because the configured data plan excludes current SIP data."""
    return min(date.fromisoformat(to_date), today - timedelta(days=1))


def fetch_spy_closes(
    from_date: str,
    to_date: str,
    redis: Any = None,
) -> dict[str, float] | None:
    """Return daily SPY closes with a one-hour cache; fail open on any error."""
    cache_key = f"benchmark:spy_closes:{from_date}:{to_date}"
    redis_client = getattr(redis, "_r", redis)
    if redis_client is not None:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass
    try:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        start = date.fromisoformat(from_date) - timedelta(days=10)
        end_date = spy_fetch_end_date(
            to_date,
            datetime.now(timezone.utc).date(),
        )
        if end_date < start:
            return None
        client = StockHistoricalDataClient(
            config.ALPACA_API_KEY,
            config.ALPACA_SECRET_KEY,
        )
        response: Any = client.get_stock_bars(
            StockBarsRequest(
                symbol_or_symbols=["SPY"],
                timeframe=TimeFrame.Day,
                start=datetime(
                    start.year,
                    start.month,
                    start.day,
                    tzinfo=timezone.utc,
                ),
                end=datetime(
                    end_date.year,
                    end_date.month,
                    end_date.day,
                    23,
                    59,
                    tzinfo=timezone.utc,
                ),
            )
        )
        closes = {
            bar.timestamp.date().isoformat(): float(bar.close)
            for bar in response.data.get("SPY", [])
        }
        if redis_client is not None and closes:
            try:
                redis_client.setex(cache_key, 3600, json.dumps(closes))
            except Exception:
                pass
        return closes or None
    except Exception as exc:
        log.warning("SPY benchmark fetch failed: %s", exc)
        return None
