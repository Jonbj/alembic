"""Tests for data loader and parquet cache."""
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.backtest.data.loader import DataLoader
from src.backtest.data.cache import ParquetCache


class TestParquetCache:
    def test_put_and_get(self, synthetic_prices: pd.DataFrame, temp_cache_dir: Path) -> None:
        cache = ParquetCache(cache_dir=temp_cache_dir)
        cache.put("TEST", synthetic_prices)

        assert cache.has("TEST")
        retrieved = cache.get("TEST")
        # Parquet drops DatetimeIndex freq metadata on round-trip; check_freq=False
        pd.testing.assert_frame_equal(retrieved, synthetic_prices, check_freq=False)

    def test_get_with_date_filter(self, synthetic_prices: pd.DataFrame, temp_cache_dir: Path) -> None:
        cache = ParquetCache(cache_dir=temp_cache_dir)
        cache.put("TEST", synthetic_prices)

        filtered = cache.get("TEST", start=date(2022, 1, 1), end=date(2022, 12, 31))
        assert filtered.index.min() >= pd.Timestamp("2022-01-01")
        assert filtered.index.max() <= pd.Timestamp("2022-12-31")

    def test_missing_columns_raises(self, temp_cache_dir: Path) -> None:
        cache = ParquetCache(cache_dir=temp_cache_dir)
        bad_df = pd.DataFrame(
            {"Close": [1.0, 2.0, 3.0]},
            index=pd.date_range("2020-01-01", periods=3),
        )
        with pytest.raises(ValueError, match="Missing required columns"):
            cache.put("BAD", bad_df)

    def test_update_merges_data(self, synthetic_prices: pd.DataFrame, temp_cache_dir: Path) -> None:
        cache = ParquetCache(cache_dir=temp_cache_dir)
        first_half = synthetic_prices.iloc[: len(synthetic_prices) // 2]
        second_half = synthetic_prices.iloc[len(synthetic_prices) // 2 :]

        cache.put("TEST", first_half)
        cache.update("TEST", second_half)

        full = cache.get("TEST")
        assert len(full) == len(synthetic_prices)

    def test_has_returns_false_for_missing(self, temp_cache_dir: Path) -> None:
        cache = ParquetCache(cache_dir=temp_cache_dir)
        assert not cache.has("NONEXISTENT")

    def test_get_missing_raises(self, temp_cache_dir: Path) -> None:
        cache = ParquetCache(cache_dir=temp_cache_dir)
        with pytest.raises(KeyError):
            cache.get("NONEXISTENT")


class TestParquetCacheUpdate:
    def test_update_creates_if_missing(self, synthetic_prices: pd.DataFrame, temp_cache_dir: Path) -> None:
        cache = ParquetCache(cache_dir=temp_cache_dir)
        cache.update("NEW", synthetic_prices)
        assert cache.has("NEW")


class TestDataLoaderWithCache:
    def test_cache_hit_no_network(self, synthetic_prices: pd.DataFrame, temp_cache_dir: Path) -> None:
        cache = ParquetCache(cache_dir=temp_cache_dir)
        cache.put("FAKE", synthetic_prices)

        loader = DataLoader(cache=cache)
        df = loader.download("FAKE", start=date(2021, 1, 1), end=date(2022, 1, 1))

        assert not df.empty
        assert df.index.min() >= pd.Timestamp("2021-01-01")
        assert df.index.max() <= pd.Timestamp("2022-01-01")

    def test_force_refresh_ignores_cache(
        self, synthetic_prices: pd.DataFrame, temp_cache_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cache = ParquetCache(cache_dir=temp_cache_dir)
        cache.put("SPY", synthetic_prices)

        fetch_calls: list[str] = []

        def fake_fetch(self_inner: DataLoader, symbol: str, start: date, end: date) -> pd.DataFrame:
            fetch_calls.append(symbol)
            return synthetic_prices

        monkeypatch.setattr(DataLoader, "_fetch_yfinance", fake_fetch)
        loader = DataLoader(cache=cache)
        loader.download("SPY", start=date(2021, 1, 1), end=date(2022, 1, 1), force_refresh=True)

        assert "SPY" in fetch_calls

    def test_cache_miss_triggers_download(
        self, synthetic_prices: pd.DataFrame, temp_cache_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cache = ParquetCache(cache_dir=temp_cache_dir)

        def fake_fetch(self_inner: DataLoader, symbol: str, start: date, end: date) -> pd.DataFrame:
            return synthetic_prices

        monkeypatch.setattr(DataLoader, "_fetch_yfinance", fake_fetch)
        loader = DataLoader(cache=cache)
        df = loader.download("UNCACHED", start=date(2021, 1, 1), end=date(2022, 12, 31))

        assert not df.empty
        assert cache.has("UNCACHED")

    def test_partial_cache_extends_range(
        self, synthetic_prices: pd.DataFrame, temp_cache_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Cache covers 2020-2021, request asks for 2020-2022 → extend."""
        import numpy as np

        cache = ParquetCache(cache_dir=temp_cache_dir)
        partial = synthetic_prices.loc["2020-01-01":"2021-12-31"]
        cache.put("EXT", partial)

        extra_dates = pd.date_range("2022-01-01", "2022-12-31", freq="B")
        n = len(extra_dates)
        extra = pd.DataFrame(
            {
                "Open": np.ones(n) * 200,
                "High": np.ones(n) * 205,
                "Low": np.ones(n) * 195,
                "Close": np.ones(n) * 200,
                "Volume": np.ones(n) * 1_000_000,
                "Adj Close": np.ones(n) * 200,
            },
            index=extra_dates,
        )

        def fake_fetch(self_inner: DataLoader, symbol: str, start: date, end: date) -> pd.DataFrame:
            return extra

        monkeypatch.setattr(DataLoader, "_fetch_yfinance", fake_fetch)
        loader = DataLoader(cache=cache)
        df = loader.download("EXT", start=date(2020, 1, 1), end=date(2022, 12, 31))

        assert not df.empty
        assert df.index.max() >= pd.Timestamp("2022-01-03")

    def test_download_universe_skips_failures(
        self, synthetic_prices: pd.DataFrame, temp_cache_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.backtest.data.universe import Universe, UniverseAsset
        from datetime import date as dt

        assets = (
            UniverseAsset("GOOD", "EQUITY", dt(1993, 1, 1)),
            UniverseAsset("BAD", "EQUITY", dt(1993, 1, 1)),
        )
        universe = Universe("test", "Test", assets)

        def fake_download(self_inner: DataLoader, symbol: str, start: date, end: date | None = None, force_refresh: bool = False) -> pd.DataFrame:
            if symbol == "BAD":
                raise ValueError("simulated failure")
            return synthetic_prices

        monkeypatch.setattr(DataLoader, "download", fake_download)
        loader = DataLoader(cache=ParquetCache(cache_dir=temp_cache_dir))
        result = loader.download_universe(universe, start=dt(2021, 1, 1))

        assert "GOOD" in result
        assert "BAD" not in result

    def test_get_aligned_prices_shape(
        self, synthetic_prices: pd.DataFrame, temp_cache_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.backtest.data.universe import Universe, UniverseAsset
        from datetime import date as dt

        assets = (
            UniverseAsset("A", "EQUITY", dt(1993, 1, 1)),
            UniverseAsset("B", "EQUITY", dt(1993, 1, 1)),
        )
        universe = Universe("test", "Test", assets)

        def fake_download(self_inner: DataLoader, symbol: str, start: date, end: date | None = None, force_refresh: bool = False) -> pd.DataFrame:
            return synthetic_prices

        monkeypatch.setattr(DataLoader, "download", fake_download)
        loader = DataLoader(cache=ParquetCache(cache_dir=temp_cache_dir))
        prices = loader.get_aligned_prices(universe, start=dt(2021, 1, 1), end=dt(2022, 12, 31))

        assert prices.shape[1] == 2
        assert set(prices.columns) == {"A", "B"}
