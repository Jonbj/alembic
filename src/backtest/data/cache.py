"""Parquet caching layer for OHLCV data."""
from datetime import date
from pathlib import Path

import pandas as pd


class ParquetCache:
    """File-based cache for OHLCV data."""

    def __init__(self, cache_dir: Path = Path.home() / ".alembic_cache") -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, symbol: str) -> Path:
        return self.cache_dir / f"{symbol}.parquet"

    def has(self, symbol: str) -> bool:
        return self._path_for(symbol).exists()

    def get(
        self,
        symbol: str,
        start: date | None = None,
        end: date | None = None,
    ) -> pd.DataFrame:
        if not self.has(symbol):
            raise KeyError(f"No cached data for {symbol}")

        df = pd.read_parquet(self._path_for(symbol))

        if start:
            df = df[df.index >= pd.Timestamp(start)]
        if end:
            df = df[df.index <= pd.Timestamp(end)]

        return df

    def put(self, symbol: str, df: pd.DataFrame) -> None:
        required_cols = {"Open", "High", "Low", "Close", "Volume", "Adj Close"}
        missing = required_cols - set(df.columns)
        if missing:
            raise ValueError(f"Missing required columns: {missing}")
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError(f"Index must be DatetimeIndex, got {type(df.index)}")

        df.to_parquet(self._path_for(symbol))

    def update(self, symbol: str, df_new: pd.DataFrame) -> None:
        """Merge new data with existing cache."""
        if self.has(symbol):
            df_old = self.get(symbol)
            df_combined = pd.concat([df_old, df_new])
            df_combined = df_combined[~df_combined.index.duplicated(keep="last")]
            df_combined = df_combined.sort_index()
            self.put(symbol, df_combined)
        else:
            self.put(symbol, df_new)
