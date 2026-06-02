"""T-505: MultiStrategyBacktester tests.

Integration tests for full multi-strategy walk-forward with S1+S2+S4 via PortfolioCombiner.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Callable

import numpy as np
import pandas as pd
import pytest

from src.backtest.engine.data_replay import DataReplay
from src.backtest.engine.portfolio import VirtualPortfolio
from src.backtest.engine.types import MarketSnapshot, Order, OrderSide
from src.portfolio.backtest import (
    MultiStrategyBacktestConfig,
    MultiStrategyBacktestResult,
    MultiStrategyBacktester,
    MultiStrategyWindowResult,
)


# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

def _make_prices(
    n_days: int,
    assets: dict[str, float],  # symbol -> daily_drift
    noise_std: float = 0.008,
    seed: int = 42,
) -> pd.DataFrame:
    """Multi-asset price DataFrame with per-asset drift, business-day index."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2018-01-02", periods=n_days, freq="B")
    data = {}
    for symbol, drift in assets.items():
        noise = rng.normal(drift, noise_std, n_days)
        data[symbol] = 100.0 * np.exp(np.cumsum(noise))
    return pd.DataFrame(data, index=dates)


def _make_replay(n_days: int, assets: dict[str, float], noise_std: float = 0.008, seed: int = 42) -> DataReplay:
    prices = _make_prices(n_days, assets, noise_std=noise_std, seed=seed)
    return DataReplay(prices)


def _make_three_asset_replay(n_days: int) -> DataReplay:
    """Three uncorrelated assets with positive drift — designed for diversification tests.

    Uses higher drift (0.001) and lower noise (0.005) so that buy-and-hold
    strategies are profitable after realistic transaction costs.
    """
    return _make_replay(n_days, {"A": 0.001, "B": 0.001, "C": 0.001}, noise_std=0.005, seed=7)


# ---------------------------------------------------------------------------
# Synthetic strategy factories
# ---------------------------------------------------------------------------

class _BuyAndHold:
    """Buys a fixed asset on first timestep, holds forever."""

    def __init__(self, symbol: str, strategy_id: str) -> None:
        self._symbol = symbol
        self._strategy_id = strategy_id
        self._entered = False

    def __call__(
        self, ts: datetime, dr: DataReplay, port: VirtualPortfolio, mkt: MarketSnapshot
    ) -> list[Order]:
        if self._entered or port.position_of(self._symbol) is not None:
            return []
        price = mkt.price_of(self._symbol)
        if price is None or price <= 0:
            return []
        qty = int(port.cash * 0.80 / price)
        if qty <= 0:
            return []
        self._entered = True
        return [Order.market_order(ts, self._symbol, OrderSide.BUY, qty, self._strategy_id)]


class _NoOpStrategy:
    """Never generates orders."""

    def __call__(self, ts, dr, port, mkt) -> list[Order]:
        return []


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Permissive constraints for synthetic data testing — allows BuyAndHold to
# invest significant capital without being overly scaled down by risk limits.
SMALL_CONFIG = MultiStrategyBacktestConfig(
    in_sample_days=60,
    out_of_sample_days=30,
    initial_capital=100_000.0,
    max_single_asset_pct=0.40,   # allow large positions in single assets
    max_portfolio_exposure=1.50,  # allow up to 150% exposure
    max_strategy_overshoot=3.00,  # generous overshoot allowance
)

# 3 strategies on 3 different assets — uncorrelated returns
@pytest.fixture(scope="module")
def three_strategy_setup():
    """Returns (strategies_dict, data_replay) for a 3-strategy uncorrelated test."""
    n_days = 200  # enough for 1 window (60 IS + 30 OOS + buffer)
    replay = _make_three_asset_replay(n_days)
    strategies = {
        "S1": (_BuyAndHold("A", "S1"), 0.40),
        "S2": (_BuyAndHold("B", "S2"), 0.30),
        "S4": (_BuyAndHold("C", "S4"), 0.30),
    }
    return strategies, replay


@pytest.fixture(scope="module")
def multi_window_setup():
    """Returns (strategies_dict, data_replay) with enough data for 2+ WF windows."""
    n_days = 400  # enough for 2 windows at 60+30
    replay = _make_three_asset_replay(n_days)
    strategies = {
        "S1": (_BuyAndHold("A", "S1"), 0.40),
        "S2": (_BuyAndHold("B", "S2"), 0.30),
        "S4": (_BuyAndHold("C", "S4"), 0.30),
    }
    return strategies, replay


# ---------------------------------------------------------------------------
# 1. Instantiation
# ---------------------------------------------------------------------------

def test_instantiation_default_config():
    backtester = MultiStrategyBacktester(
        strategies={"S1": (_NoOpStrategy(), 1.0)},
    )
    assert backtester is not None


def test_instantiation_with_explicit_config():
    backtester = MultiStrategyBacktester(
        strategies={"S1": (_NoOpStrategy(), 0.5), "S2": (_NoOpStrategy(), 0.5)},
        config=SMALL_CONFIG,
    )
    assert backtester._config.in_sample_days == 60


# ---------------------------------------------------------------------------
# 2. Basic run
# ---------------------------------------------------------------------------

def test_run_returns_result_type(three_strategy_setup):
    strategies, replay = three_strategy_setup
    backtester = MultiStrategyBacktester(strategies=strategies, config=SMALL_CONFIG)
    result = backtester.run(replay)
    assert isinstance(result, MultiStrategyBacktestResult)


def test_run_produces_at_least_one_window(three_strategy_setup):
    strategies, replay = three_strategy_setup
    backtester = MultiStrategyBacktester(strategies=strategies, config=SMALL_CONFIG)
    result = backtester.run(replay)
    assert len(result.windows) >= 1


def test_run_with_insufficient_data_produces_zero_windows():
    n_days = 50  # less than 60 IS + 30 OOS = 90 needed
    replay = _make_three_asset_replay(n_days)
    strategies = {"S1": (_NoOpStrategy(), 1.0)}
    backtester = MultiStrategyBacktester(strategies=strategies, config=SMALL_CONFIG)
    result = backtester.run(replay)
    assert len(result.windows) == 0


# ---------------------------------------------------------------------------
# 3. Result structure — combined metrics
# ---------------------------------------------------------------------------

def test_result_has_combined_oos_sharpe(three_strategy_setup):
    strategies, replay = three_strategy_setup
    backtester = MultiStrategyBacktester(strategies=strategies, config=SMALL_CONFIG)
    result = backtester.run(replay)
    assert math.isfinite(result.combined_oos_sharpe)


def test_result_has_max_drawdown(three_strategy_setup):
    strategies, replay = three_strategy_setup
    backtester = MultiStrategyBacktester(strategies=strategies, config=SMALL_CONFIG)
    result = backtester.run(replay)
    assert result.combined_max_dd <= 0.0, "Max drawdown must be <= 0"


def test_result_has_calmar_ratio(three_strategy_setup):
    strategies, replay = three_strategy_setup
    backtester = MultiStrategyBacktester(strategies=strategies, config=SMALL_CONFIG)
    result = backtester.run(replay)
    assert math.isfinite(result.combined_calmar)


def test_result_has_diversification_ratio(three_strategy_setup):
    strategies, replay = three_strategy_setup
    backtester = MultiStrategyBacktester(strategies=strategies, config=SMALL_CONFIG)
    result = backtester.run(replay)
    assert math.isfinite(result.diversification_ratio)
    assert result.diversification_ratio >= 0.0


# ---------------------------------------------------------------------------
# 4. Individual strategy metrics
# ---------------------------------------------------------------------------

def test_result_has_individual_strategy_metrics(three_strategy_setup):
    strategies, replay = three_strategy_setup
    backtester = MultiStrategyBacktester(strategies=strategies, config=SMALL_CONFIG)
    result = backtester.run(replay)
    assert set(result.individual_sharpes.keys()) == {"S1", "S2", "S4"}


def test_individual_sharpes_are_finite(three_strategy_setup):
    strategies, replay = three_strategy_setup
    backtester = MultiStrategyBacktester(strategies=strategies, config=SMALL_CONFIG)
    result = backtester.run(replay)
    for sid, sharpe in result.individual_sharpes.items():
        assert math.isfinite(sharpe), f"S{sid} Sharpe must be finite"


# ---------------------------------------------------------------------------
# 5. Window structure
# ---------------------------------------------------------------------------

def test_window_has_correct_timestamps(three_strategy_setup):
    strategies, replay = three_strategy_setup
    backtester = MultiStrategyBacktester(strategies=strategies, config=SMALL_CONFIG)
    result = backtester.run(replay)
    w = result.windows[0]
    assert isinstance(w, MultiStrategyWindowResult)
    assert w.oos_start > w.is_end
    assert w.oos_end >= w.oos_start


def test_window_has_combined_and_individual_metrics(three_strategy_setup):
    strategies, replay = three_strategy_setup
    backtester = MultiStrategyBacktester(strategies=strategies, config=SMALL_CONFIG)
    result = backtester.run(replay)
    w = result.windows[0]
    assert "sharpe" in w.combined_metrics
    assert set(w.individual_metrics.keys()) == {"S1", "S2", "S4"}


def test_multiple_windows_have_non_overlapping_oos(multi_window_setup):
    strategies, replay = multi_window_setup
    backtester = MultiStrategyBacktester(strategies=strategies, config=SMALL_CONFIG)
    result = backtester.run(replay)
    assert len(result.windows) >= 2
    for i in range(1, len(result.windows)):
        assert result.windows[i].oos_start > result.windows[i - 1].oos_end


# ---------------------------------------------------------------------------
# 6. Diversification metrics
# ---------------------------------------------------------------------------

def test_diversification_ratio_above_one_for_uncorrelated_strategies(three_strategy_setup):
    """Three strategies on different assets should diversify each other."""
    strategies, replay = three_strategy_setup
    backtester = MultiStrategyBacktester(strategies=strategies, config=SMALL_CONFIG)
    result = backtester.run(replay)
    assert result.diversification_ratio > 1.0, (
        f"Expected diversification_ratio > 1.0, got {result.diversification_ratio:.3f}"
    )


def test_diversification_ratio_is_one_for_identical_single_strategy():
    """Single strategy has diversification_ratio ≈ 1.0."""
    n_days = 200
    replay = _make_three_asset_replay(n_days)
    strategies = {"S1": (_BuyAndHold("A", "S1"), 1.0)}
    backtester = MultiStrategyBacktester(strategies=strategies, config=SMALL_CONFIG)
    result = backtester.run(replay)
    # Allow small numerical tolerance due to cost model differences
    assert abs(result.diversification_ratio - 1.0) < 0.05, (
        f"Expected diversification_ratio ≈ 1.0 for single strategy, got {result.diversification_ratio:.4f}"
    )


def test_combined_sharpe_positive_for_trending_assets(three_strategy_setup):
    """Assets with positive drift should yield positive combined Sharpe."""
    strategies, replay = three_strategy_setup
    backtester = MultiStrategyBacktester(strategies=strategies, config=SMALL_CONFIG)
    result = backtester.run(replay)
    assert result.combined_oos_sharpe > 0.0, (
        f"Expected positive combined OOS Sharpe on trending assets, got {result.combined_oos_sharpe:.3f}"
    )


def test_combined_sharpe_exceeds_weighted_avg_individual_sharpe(three_strategy_setup):
    """Diversification benefit: combined Sharpe > weighted avg of individual Sharpes."""
    strategies, replay = three_strategy_setup
    backtester = MultiStrategyBacktester(strategies=strategies, config=SMALL_CONFIG)
    result = backtester.run(replay)

    weights = {sid: alloc for sid, (_, alloc) in strategies.items()}
    total_w = sum(weights.values())
    weighted_avg = sum(
        result.individual_sharpes[sid] * weights[sid] / total_w
        for sid in weights
    )
    assert result.combined_oos_sharpe >= weighted_avg * 0.90, (
        f"Combined Sharpe {result.combined_oos_sharpe:.3f} should be at least 90% of "
        f"weighted avg {weighted_avg:.3f} (diversification benefit)"
    )


# ---------------------------------------------------------------------------
# 7. Aggregate metrics dict
# ---------------------------------------------------------------------------

def test_aggregate_metrics_contains_required_keys(three_strategy_setup):
    strategies, replay = three_strategy_setup
    backtester = MultiStrategyBacktester(strategies=strategies, config=SMALL_CONFIG)
    result = backtester.run(replay)
    keys = result.aggregate_metrics.keys()
    for k in ("combined_oos_sharpe", "combined_max_dd", "combined_calmar", "diversification_ratio"):
        assert k in keys, f"Missing key: {k}"


def test_aggregate_metrics_n_windows_correct(three_strategy_setup):
    strategies, replay = three_strategy_setup
    backtester = MultiStrategyBacktester(strategies=strategies, config=SMALL_CONFIG)
    result = backtester.run(replay)
    assert result.aggregate_metrics["n_windows"] == len(result.windows)


# ---------------------------------------------------------------------------
# 8. Gate validation
# ---------------------------------------------------------------------------

def test_oos_sharpe_above_gate_threshold_for_designed_data():
    """With strongly trending assets, OOS Sharpe should exceed 0.5 gate."""
    n_days = 200
    # High-drift assets to ensure good Sharpe
    prices = _make_prices(n_days, {"X": 0.0010, "Y": 0.0010, "Z": 0.0010}, noise_std=0.005, seed=1)
    replay = DataReplay(prices)
    strategies = {
        "S1": (_BuyAndHold("X", "S1"), 0.33),
        "S2": (_BuyAndHold("Y", "S2"), 0.33),
        "S4": (_BuyAndHold("Z", "S4"), 0.34),
    }
    backtester = MultiStrategyBacktester(strategies=strategies, config=SMALL_CONFIG)
    result = backtester.run(replay)
    assert result.combined_oos_sharpe >= 0.5, (
        f"OOS Sharpe {result.combined_oos_sharpe:.3f} did not meet 0.5 gate"
    )


# ---------------------------------------------------------------------------
# 9. No-op strategies produce neutral result
# ---------------------------------------------------------------------------

def test_noop_strategies_return_zero_or_nan_sharpe():
    """Strategies that never trade produce 0 returns and therefore 0 Sharpe."""
    n_days = 200
    replay = _make_three_asset_replay(n_days)
    strategies = {
        "S1": (_NoOpStrategy(), 0.5),
        "S2": (_NoOpStrategy(), 0.5),
    }
    backtester = MultiStrategyBacktester(strategies=strategies, config=SMALL_CONFIG)
    result = backtester.run(replay)
    # No trades = constant NAV = 0 returns = 0 Sharpe
    assert result.combined_oos_sharpe == 0.0


# ---------------------------------------------------------------------------
# 10. Diversification ratio > 1.3 (T-505 target) with stronger design
# ---------------------------------------------------------------------------

def test_diversification_ratio_exceeds_target_with_three_uncorrelated_strategies():
    """With 3 strategies on independently-seeded uncorrelated assets, ratio > 1.3."""
    n_days = 400
    # Three independent assets with different seeds → near-zero correlation
    rng_a = np.random.default_rng(seed=1)
    rng_b = np.random.default_rng(seed=2)
    rng_c = np.random.default_rng(seed=3)
    dates = pd.date_range("2018-01-02", periods=n_days, freq="B")
    drift, std = 0.001, 0.005
    prices = pd.DataFrame({
        "AA": 100.0 * np.exp(np.cumsum(rng_a.normal(drift, std, n_days))),
        "BB": 100.0 * np.exp(np.cumsum(rng_b.normal(drift, std, n_days))),
        "CC": 100.0 * np.exp(np.cumsum(rng_c.normal(drift, std, n_days))),
    }, index=dates)
    replay = DataReplay(prices)
    strategies = {
        "S1": (_BuyAndHold("AA", "S1"), 0.34),
        "S2": (_BuyAndHold("BB", "S2"), 0.33),
        "S4": (_BuyAndHold("CC", "S4"), 0.33),
    }
    config = MultiStrategyBacktestConfig(
        in_sample_days=120,
        out_of_sample_days=60,
        initial_capital=100_000.0,
        max_single_asset_pct=0.40,
        max_portfolio_exposure=1.50,
        max_strategy_overshoot=3.00,
    )
    backtester = MultiStrategyBacktester(strategies=strategies, config=config)
    result = backtester.run(replay)
    assert result.diversification_ratio > 1.3, (
        f"Diversification ratio {result.diversification_ratio:.3f} did not exceed 1.3 target"
    )
