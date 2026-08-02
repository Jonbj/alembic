"""Daily-bar loader backed by Alpaca, with parquet cache.

Sits ALONGSIDE `loader.py` (yfinance) rather than replacing it: that one is used
by five strategy backtests (`src/strategies/s{1,2,3,4}/backtest.py`,
`s3/universe.py`) and by `scripts/download_initial_data.py`. Swapping it in place
would touch all of them.

Why Alpaca for research: it is the same source that feeds live execution, so a
backtest and production see the same prices. That removes a whole class of silent
discrepancy — the kind where a backtest looks fine because it was fed a different
history than the one the system actually traded on.

Read-only: downloads and caches, never writes to the trading system.
"""
from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from src.backtest.data.cache import ParquetCache

log = logging.getLogger(__name__)

# Alpaca returns bars already adjusted for splits and dividends when
# adjustment="all", so Adj Close is set equal to Close. The cache schema requires
# the column; duplicating it is honest here, not a placeholder.
_CACHE_COLUMNS = ["Open", "High", "Low", "Close", "Volume", "Adj Close"]


class AlpacaDailyLoader:
    """Load daily OHLCV from Alpaca, cache as parquet, point-in-time safe."""

    def __init__(
        self,
        cache: ParquetCache | None = None,
        feed: str = "iex",
        api_key: str | None = None,
        secret_key: str | None = None,
    ) -> None:
        self._cache = cache or ParquetCache(Path.home() / ".alembic_cache_alpaca")
        self._feed = feed
        self._api_key = api_key or os.environ.get("ALPACA_API_KEY", "")
        self._secret_key = secret_key or os.environ.get("ALPACA_SECRET_KEY", "")
        self._client = None

    def _get_client(self):
        """Lazy: importing alpaca and building a client is not free, and a caller
        that hits the cache for every symbol should never need one."""
        if self._client is None:
            from alpaca.data.historical import StockHistoricalDataClient

            if not self._api_key or not self._secret_key:
                raise RuntimeError(
                    "ALPACA_API_KEY / ALPACA_SECRET_KEY missing — cannot download. "
                    "Note that .env is gitignored and therefore absent from worktrees."
                )
            self._client = StockHistoricalDataClient(self._api_key, self._secret_key)
        return self._client

    def download(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Daily bars for one symbol, served from cache when it already covers the range."""
        if self._cache.has(symbol):
            cached = self._cache.get(symbol)
            if not cached.empty:
                have_start = cached.index.min().date()
                have_end = cached.index.max().date()
                if have_start <= start and have_end >= end:
                    return self._cache.get(symbol, start=start, end=end)

        df = self._fetch(symbol, start, end)
        if df.empty:
            return df
        if self._cache.has(symbol):
            self._cache.update(symbol, df)
        else:
            self._cache.put(symbol, df)
        return self._cache.get(symbol, start=start, end=end)

    def _fetch(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Day,
            start=pd.Timestamp(start).to_pydatetime(),
            # Alpaca's end is exclusive of intraday but inclusive of the day bar;
            # one extra day costs nothing and avoids losing the final session.
            end=pd.Timestamp(end + timedelta(days=1)).to_pydatetime(),
            feed=self._feed,
            adjustment="all",
        )
        try:
            bars = self._get_client().get_stock_bars(req).df
        except Exception as exc:
            log.warning("Alpaca download failed for %s: %s", symbol, exc)
            return pd.DataFrame()

        if bars is None or bars.empty:
            return pd.DataFrame()

        if isinstance(bars.index, pd.MultiIndex):
            bars = bars.xs(symbol, level="symbol")

        out = pd.DataFrame(index=pd.DatetimeIndex(bars.index).tz_localize(None))
        out["Open"] = bars["open"].to_numpy()
        out["High"] = bars["high"].to_numpy()
        out["Low"] = bars["low"].to_numpy()
        out["Close"] = bars["close"].to_numpy()
        out["Volume"] = bars["volume"].to_numpy()
        out["Adj Close"] = bars["close"].to_numpy()
        return out[_CACHE_COLUMNS]

    def download_many(
        self, symbols: list[str], start: date, end: date
    ) -> dict[str, pd.DataFrame]:
        """Bars for several symbols. A symbol that fails is OMITTED, never faked.

        Returning an empty frame for a failed symbol would let it silently enter a
        calculation as "no movement", which is a false statement about the market.
        """
        out: dict[str, pd.DataFrame] = {}
        for sym in symbols:
            try:
                df = self.download(sym, start, end)
            except Exception as exc:
                log.warning("Skipping %s: %s", sym, exc)
                continue
            if not df.empty:
                out[sym] = df
        return out
