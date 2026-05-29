"""Data loader: download from Yahoo (default), cache as parquet, multi-symbol API."""
from datetime import date
import logging
import time

import pandas as pd
import yfinance as yf

from src.backtest.data.cache import ParquetCache
from src.backtest.data.universe import Universe


log = logging.getLogger(__name__)


class DataLoader:
    """Load daily OHLCV data, cache on parquet, point-in-time safe."""

    def __init__(self, cache: ParquetCache | None = None) -> None:
        self.cache = cache or ParquetCache()

    def download(
        self,
        symbol: str,
        start: date,
        end: date | None = None,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """Download data for symbol, cache, return DataFrame.

        Args:
            symbol: ticker e.g. 'SPY'
            start: start date (inclusive)
            end: end date (exclusive), default today
            force_refresh: if True, ignore cache and re-download

        Returns:
            DataFrame with Open, High, Low, Close, Volume, Adj Close columns,
            DatetimeIndex.
        """
        end = end or date.today()

        if not force_refresh and self.cache.has(symbol):
            cached_df = self.cache.get(symbol)
            cached_start = cached_df.index.min().date()
            cached_end = cached_df.index.max().date()

            if cached_start <= start and cached_end >= end:
                return cached_df[
                    (cached_df.index >= pd.Timestamp(start))
                    & (cached_df.index <= pd.Timestamp(end))
                ]

            if cached_end >= start:
                log.info("Extending cache for %s: %s → %s", symbol, cached_end, end)
                new_data = self._fetch_yfinance(symbol, cached_end, end)
                self.cache.update(symbol, new_data)
                full = self.cache.get(symbol)
                return full[
                    (full.index >= pd.Timestamp(start))
                    & (full.index <= pd.Timestamp(end))
                ]

        log.info("Downloading %s from %s to %s", symbol, start, end)
        df = self._fetch_yfinance(symbol, start, end)
        self.cache.put(symbol, df)
        return df

    def _fetch_yfinance(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Fetch from yfinance with retry."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                df = yf.download(
                    symbol,
                    start=start.isoformat(),
                    end=end.isoformat(),
                    auto_adjust=False,
                    progress=False,
                    threads=False,
                )
                if df.empty:
                    raise ValueError(f"Empty data returned for {symbol}")

                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)

                if df.index.tz is not None:
                    df.index = df.index.tz_localize(None)

                # Ensure Adj Close column exists (yfinance sometimes names it differently)
                if "Adj Close" not in df.columns and "Close" in df.columns:
                    df["Adj Close"] = df["Close"]

                return df
            except Exception as e:
                log.warning(
                    "Attempt %d/%d failed for %s: %s",
                    attempt + 1,
                    max_retries,
                    symbol,
                    e,
                )
                if attempt == max_retries - 1:
                    raise
                time.sleep(2 ** attempt)

        raise RuntimeError(f"All retries exhausted for {symbol}")

    def download_universe(
        self,
        universe: Universe,
        start: date,
        end: date | None = None,
    ) -> dict[str, pd.DataFrame]:
        """Download data for all tickers in universe."""
        result: dict[str, pd.DataFrame] = {}
        for asset in universe.assets:
            try:
                df = self.download(asset.symbol, start, end)
                result[asset.symbol] = df
            except Exception as e:
                log.error("Failed to download %s: %s", asset.symbol, e)
        return result

    def get_aligned_prices(
        self,
        universe: Universe,
        start: date,
        end: date | None = None,
        field: str = "Adj Close",
    ) -> pd.DataFrame:
        """Returns DataFrame columns=tickers, index=date, values=adj close."""
        data = self.download_universe(universe, start, end)
        prices = pd.DataFrame({sym: df[field] for sym, df in data.items()})
        prices = prices.ffill(limit=5)
        return prices
