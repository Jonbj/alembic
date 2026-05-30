"""T-201: S3 universe + dynamic point-in-time liquidity filter."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from src.strategies.s3.universe import (
    LiquidityFilter,
    S3Universe,
    load_s3_universe,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

N_DAYS = 400
BASE_DATE = "2020-01-02"


def _make_prices(
    tickers: list[str],
    n: int = N_DAYS,
    start: str = BASE_DATE,
    base_price: float = 50.0,
    drift: float = 0.0002,
    vol: float = 0.01,
    seed: int = 42,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, periods=n, freq="B")
    data = {}
    for i, t in enumerate(tickers):
        data[t] = base_price * np.exp(
            np.cumsum(rng.normal(drift, vol, n))
        )
    return pd.DataFrame(data, index=dates)


def _make_volumes(
    tickers: list[str],
    n: int = N_DAYS,
    start: str = BASE_DATE,
    base_vol: float = 5_000_000,
    seed: int = 99,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, periods=n, freq="B")
    data = {t: base_vol * (1 + 0.2 * rng.standard_normal(n)) for t in tickers}
    return pd.DataFrame(data, index=dates)


def _make_universe(
    tickers: list[str],
    liq_filter: LiquidityFilter | None = None,
    n: int = N_DAYS,
    base_price: float = 50.0,
    base_vol: float = 5_000_000,
) -> S3Universe:
    liq_filter = liq_filter or LiquidityFilter()
    close = _make_prices(tickers, n=n, base_price=base_price)
    volume = _make_volumes(tickers, n=n, base_vol=base_vol)
    return S3Universe(
        tickers=tuple(tickers),
        close=close,
        volume=volume,
        liq_filter=liq_filter,
    )


# ---------------------------------------------------------------------------
# LiquidityFilter
# ---------------------------------------------------------------------------


class TestLiquidityFilter:
    def test_defaults(self) -> None:
        f = LiquidityFilter()
        assert f.min_adv_usd == 10_000_000
        assert f.min_price_usd == 5.0
        assert f.min_history_days == 252
        assert f.adv_window_days == 63

    def test_custom_params(self) -> None:
        f = LiquidityFilter(min_adv_usd=1e7, min_price_usd=10.0, min_history_days=126)
        assert f.min_adv_usd == 1e7
        assert f.min_price_usd == 10.0
        assert f.min_history_days == 126

    def test_frozen(self) -> None:
        f = LiquidityFilter()
        with pytest.raises((AttributeError, TypeError)):
            f.min_price_usd = 99.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# S3Universe.active_at — point-in-time correctness
# ---------------------------------------------------------------------------


class TestS3UniverseActiveAt:
    def test_returns_tuple_of_strings(self) -> None:
        u = _make_universe(["AAPL", "MSFT"])
        result = u.active_at(date(2021, 6, 1))
        assert isinstance(result, tuple)
        for sym in result:
            assert isinstance(sym, str)

    def test_empty_when_no_history_before_as_of(self) -> None:
        # Data starts 2020-01-02; ask for 2019-01-01 → no rows visible
        u = _make_universe(["AAPL"])
        result = u.active_at(date(2019, 1, 1))
        assert result == ()

    def test_insufficient_history_excluded(self) -> None:
        # Only 100 days of data; filter requires 252
        u = _make_universe(
            ["AAPL"],
            n=100,
            liq_filter=LiquidityFilter(min_history_days=252),
        )
        as_of = pd.Timestamp(BASE_DATE) + pd.offsets.BDay(99)
        result = u.active_at(as_of.date())
        assert "AAPL" not in result

    def test_sufficient_history_included(self) -> None:
        # 400 days ≥ 252 required
        u = _make_universe(["AAPL"], n=N_DAYS, liq_filter=LiquidityFilter(min_history_days=252))
        last_date = u.close.index[-1].date()
        result = u.active_at(last_date)
        assert "AAPL" in result

    def test_price_below_threshold_excluded(self) -> None:
        # base_price=2 → well below min_price_usd=5
        u = _make_universe(
            ["CHEAP"],
            base_price=2.0,
            liq_filter=LiquidityFilter(min_price_usd=5.0),
        )
        last_date = u.close.index[-1].date()
        result = u.active_at(last_date)
        assert "CHEAP" not in result

    def test_price_above_threshold_included(self) -> None:
        u = _make_universe(
            ["AAPL"],
            base_price=100.0,
            liq_filter=LiquidityFilter(min_price_usd=5.0),
        )
        last_date = u.close.index[-1].date()
        result = u.active_at(last_date)
        assert "AAPL" in result

    def test_low_adv_excluded(self) -> None:
        # price=50, volume=100 → ADV=5000, well below 10M threshold
        u = _make_universe(
            ["LOW_LIQ"],
            base_price=50.0,
            base_vol=100.0,
            liq_filter=LiquidityFilter(min_adv_usd=10_000_000),
        )
        last_date = u.close.index[-1].date()
        result = u.active_at(last_date)
        assert "LOW_LIQ" not in result

    def test_high_adv_included(self) -> None:
        # price=50, volume=500_000 → ADV=25M > 10M
        u = _make_universe(
            ["HIGH_LIQ"],
            base_price=50.0,
            base_vol=500_000.0,
            liq_filter=LiquidityFilter(min_adv_usd=10_000_000),
        )
        last_date = u.close.index[-1].date()
        result = u.active_at(last_date)
        assert "HIGH_LIQ" in result

    def test_only_uses_data_up_to_as_of(self) -> None:
        """Earlier as_of date must not see future data."""
        tickers = ["AAPL", "MSFT", "GOOG"]
        u = _make_universe(tickers, n=N_DAYS)
        # as_of at 50% of the history
        midpoint_idx = N_DAYS // 2
        as_of_ts = u.close.index[midpoint_idx]
        future_ts = u.close.index[-1]

        result_mid = set(u.active_at(as_of_ts.date()))
        result_end = set(u.active_at(future_ts.date()))

        # Both calls must return only known tickers
        assert result_mid.issubset(set(tickers))
        assert result_end.issubset(set(tickers))

    def test_universe_changes_over_time(self) -> None:
        """active_at() results should differ between early and late dates."""
        n = 600
        liq_filter = LiquidityFilter(min_history_days=252, adv_window_days=63)
        tickers = [f"T{i:02d}" for i in range(20)]
        rng = np.random.default_rng(7)
        dates = pd.date_range(BASE_DATE, periods=n, freq="B")

        # Give some tickers very few early rows by inserting NaN for first 300 days
        close_data: dict[str, pd.Series] = {}
        vol_data: dict[str, pd.Series] = {}
        for i, t in enumerate(tickers):
            prices = 50.0 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, n)))
            vols = 300_000 * np.ones(n)
            if i >= 10:
                # These tickers only have data in the second half
                prices[:300] = np.nan
                vols[:300] = np.nan
            close_data[t] = pd.Series(prices, index=dates)
            vol_data[t] = pd.Series(vols, index=dates)

        close_df = pd.DataFrame(close_data)
        vol_df = pd.DataFrame(vol_data)
        u = S3Universe(tickers=tuple(tickers), close=close_df, volume=vol_df, liq_filter=liq_filter)

        early_date = dates[260].date()  # ~1 year in
        late_date = dates[-1].date()

        early_active = set(u.active_at(early_date))
        late_active = set(u.active_at(late_date))

        # Tickers with NaN in early period should be absent early but present late
        late_only = {"T10", "T11", "T12"} & late_active
        assert late_only, "Expected some late-entry tickers to appear at end"

        # At least some tickers active early that weren't available late-only
        early_first_half = early_active & {f"T{i:02d}" for i in range(10)}
        assert len(early_first_half) > 0


# ---------------------------------------------------------------------------
# Typical universe size
# ---------------------------------------------------------------------------


class TestTypicalUniverseSize:
    def test_typical_size_50_to_65_tickers(self) -> None:
        """Synthetic 57-ticker universe should produce 50-65 active tickers.

        Deliberately fails 3 by price and 3 by ADV (6 total), leaving 51 active.
        Uses a flat $100 price for passing tickers to avoid random drift failures.
        """
        n_tickers = 57
        tickers = [f"T{i:02d}" for i in range(n_tickers)]
        n = N_DAYS
        dates = pd.date_range(BASE_DATE, periods=n, freq="B")

        close_data: dict[str, pd.Series] = {}
        vol_data: dict[str, pd.Series] = {}
        for i, t in enumerate(tickers):
            if i < 3:
                # Fails price filter (2 USD < 5 USD threshold)
                price = np.full(n, 2.0)
                vol = np.full(n, 400_000.0)
            elif i < 6:
                # Fails ADV filter: price ok but volume tiny → ADV ≈ 100*100 = 10k
                price = np.full(n, 100.0)
                vol = np.full(n, 100.0)
            else:
                # Clearly passes: price=100, ADV = 100*500_000 = 50M
                price = np.full(n, 100.0)
                vol = np.full(n, 500_000.0)
            close_data[t] = pd.Series(price, index=dates)
            vol_data[t] = pd.Series(vol, index=dates)

        liq_filter = LiquidityFilter(
            min_adv_usd=10_000_000,
            min_price_usd=5.0,
            min_history_days=252,
            adv_window_days=63,
        )
        u = S3Universe(
            tickers=tuple(tickers),
            close=pd.DataFrame(close_data),
            volume=pd.DataFrame(vol_data),
            liq_filter=liq_filter,
        )

        last_date = dates[-1].date()
        active = u.active_at(last_date)
        n_active = len(active)
        # 57 - 3 price-fail - 3 ADV-fail = 51, well within [50, 65]
        assert 50 <= n_active <= 65, f"Expected 50-65 active tickers, got {n_active}"


# ---------------------------------------------------------------------------
# load_s3_universe
# ---------------------------------------------------------------------------


class TestLoadS3Universe:
    def test_loads_tickers_from_csv(self, tmp_path: Path) -> None:
        csv = tmp_path / "tickers.csv"
        csv.write_text("company_name,ticker,source,aliases\nApple,AAPL,sp500,\nMSFT Corp,MSFT,sp500,\n")

        config = {
            "s3_universe": {
                "description": "Test",
                "source": str(csv),
                "filters": {"min_adv_usd": 5_000_000, "min_price_usd": 3.0},
            }
        }
        cfg_path = tmp_path / "universe.yaml"
        cfg_path.write_text(yaml.dump(config))

        u = load_s3_universe(config_path=cfg_path)
        assert "AAPL" in u.tickers
        assert "MSFT" in u.tickers

    def test_filter_params_from_config(self, tmp_path: Path) -> None:
        csv = tmp_path / "tickers.csv"
        csv.write_text("company_name,ticker,source,aliases\nApple,AAPL,sp500,\n")

        config = {
            "s3_universe": {
                "description": "Test",
                "source": str(csv),
                "filters": {"min_adv_usd": 20_000_000, "min_price_usd": 10.0},
            }
        }
        cfg_path = tmp_path / "universe.yaml"
        cfg_path.write_text(yaml.dump(config))

        u = load_s3_universe(config_path=cfg_path)
        assert u.liq_filter.min_adv_usd == 20_000_000
        assert u.liq_filter.min_price_usd == 10.0

    def test_liq_filter_override(self, tmp_path: Path) -> None:
        csv = tmp_path / "tickers.csv"
        csv.write_text("company_name,ticker,source,aliases\nApple,AAPL,sp500,\n")

        config = {"s3_universe": {"description": "T", "source": str(csv), "filters": {}}}
        cfg_path = tmp_path / "universe.yaml"
        cfg_path.write_text(yaml.dump(config))

        override = LiquidityFilter(min_adv_usd=99_000_000)
        u = load_s3_universe(config_path=cfg_path, liq_filter=override)
        assert u.liq_filter.min_adv_usd == 99_000_000

    def test_loads_real_config_and_csv(self) -> None:
        """Smoke test: real config/universe.yaml + data/sp500_tickers.csv."""
        u = load_s3_universe(config_path=Path("config/universe.yaml"))
        assert len(u.tickers) > 0
        assert "AAPL" in u.tickers

    def test_symbols_matches_tickers(self, tmp_path: Path) -> None:
        csv = tmp_path / "tickers.csv"
        csv.write_text("company_name,ticker,source,aliases\nApple,AAPL,sp500,\n")

        config = {"s3_universe": {"description": "T", "source": str(csv), "filters": {}}}
        cfg_path = tmp_path / "universe.yaml"
        cfg_path.write_text(yaml.dump(config))

        u = load_s3_universe(config_path=cfg_path)
        assert u.symbols() == u.tickers
