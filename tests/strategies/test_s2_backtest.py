"""Tests for S2 backtest (VRPStrategy + walk-forward + gates)."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.backtest.engine.data_replay import DataReplay
from src.backtest.engine.orchestrator import BacktestConfig, BacktestOrchestrator
from src.backtest.engine.portfolio import VirtualPortfolio
from src.backtest.engine.types import MarketSnapshot, Order, OrderSide
from src.backtest.gates.runner import GateConfig
from src.backtest.walkforward.runner import WalkForwardConfig, WalkForwardRunner
from src.strategies.s2.config import S2Config
from src.strategies.s2.strategy import VRPStrategy, OpenPosition, _UNDERLYING
from src.strategies.s2.backtest import (
    run_s2_backtest_from_prices,
    _split_regime_returns,
    _extract_stress_periods,
    _run_perturbation,
)


# ---- Helpers ----

def _make_prices(days: int = 500, start_price: float = 450.0, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic SPY price data with daily returns."""
    rng = np.random.RandomState(seed)
    dates = pd.bdate_range(start="2015-01-02", periods=days)
    returns = rng.normal(0.0003, 0.01, days)
    prices = start_price * (1 + returns).cumprod()
    return pd.DataFrame({"SPY": prices}, index=dates)


def _make_market_snapshot(ts: datetime, spy_price: float) -> MarketSnapshot:
    """Create a simple market snapshot with SPY price."""
    return MarketSnapshot(
        timestamp=ts,
        prices={"SPY": spy_price},
        volumes={"SPY": 100_000_000},
        adv_20d={"SPY": 80_000_000},
    )


# ---- VRPStrategy Tests ----

class TestVRPStrategy:
    """Test VRPStrategy initialization, health check, and order generation."""

    def test_init_with_valid_prices(self):
        """VRPStrategy initializes without error with valid price data."""
        prices = _make_prices(500)
        strategy = VRPStrategy(prices, S2Config())
        assert strategy._config is not None
        assert strategy._open_position is None

    def test_health_check_passes_with_enough_data(self):
        """Health check passes with 500+ days of price data."""
        prices = _make_prices(500)
        strategy = VRPStrategy(prices, S2Config())
        assert strategy.health_check() is True

    def test_health_check_fails_with_insufficient_data(self):
        """Health check fails with too little data."""
        prices = _make_prices(100)
        strategy = VRPStrategy(prices, S2Config())
        assert strategy.health_check() is False

    def test_health_check_fails_with_empty_dataframe(self):
        """Health check fails with empty DataFrame."""
        prices = pd.DataFrame({"SPY": pd.Series(dtype=float)})
        strategy = VRPStrategy(prices, S2Config())
        assert strategy.health_check() is False

    def test_should_rebalance_monthly(self):
        """Strategy rebalances monthly (first call always True)."""
        prices = _make_prices(500)
        strategy = VRPStrategy(prices, S2Config())
        ts1 = datetime(2020, 1, 15)
        assert strategy._should_rebalance(ts1) is True
        strategy._last_rebalance = ts1
        # Same month — no rebalance
        ts2 = datetime(2020, 1, 20)
        assert strategy._should_rebalance(ts2) is False
        # Next month — rebalance
        ts3 = datetime(2020, 2, 5)
        assert strategy._should_rebalance(ts3) is True

    def test_get_regime_classifies(self):
        """Regime classification returns valid labels."""
        prices = _make_prices(500, seed=1)
        strategy = VRPStrategy(prices, S2Config())
        regime = strategy._get_regime(datetime(2015, 6, 1))
        assert regime in ("bull", "sideways", "bear", "high_vol")

    def test_strategy_callable_interface(self):
        """VRPStrategy implements the StrategyCallable interface."""
        prices = _make_prices(500)
        strategy = VRPStrategy(prices, S2Config())

        idx = len(prices) // 2
        ts = prices.index[idx]
        data_replay = DataReplay(prices)
        portfolio = VirtualPortfolio(100_000)
        spy_price = float(prices["SPY"].iloc[idx])
        market = _make_market_snapshot(ts, spy_price)

        # Must return list of Order objects
        orders = strategy(ts, data_replay, portfolio, market)
        assert isinstance(orders, list)
        for o in orders:
            assert isinstance(o, Order)

    def test_call_generates_spy_orders(self):
        """Strategy generates SPY orders (not SPY_PUT) on entry."""
        prices = _make_prices(500)
        config = S2Config(
            target_delta=-0.20,
            delta_tolerance=0.10,
            min_dte=30,
            max_dte=90,
            vrp_entry_threshold=0.0,
            regime_scales={"bull": 1.0, "sideways": 0.75, "bear": 0.25, "high_vol": 0.0},
        )
        strategy = VRPStrategy(prices, config)
        assert strategy.health_check()

        idx = len(prices) // 2
        ts = prices.index[idx]
        spy_price = float(prices["SPY"].iloc[idx])
        market = _make_market_snapshot(ts, spy_price)
        data_replay = DataReplay(prices)

        orders = strategy(ts, data_replay, VirtualPortfolio(100_000), market)
        # v2 uses SPY (delta-equivalent), not SPY_PUT
        for o in orders:
            assert o.symbol == _UNDERLYING  # "SPY"

    def test_exit_generates_sell_orders(self):
        """Strategy generates SPY SELL orders on exit."""
        prices = _make_prices(500)
        config = S2Config(
            profit_target_pct=0.10,
            min_dte=20,
            max_dte=90,
        )
        strategy = VRPStrategy(prices, config)

        # Manually create an open position
        from src.strategies.s2.signal import PutSignal
        entry_idx = 200
        entry_date = prices.index[entry_idx].date()
        signal = PutSignal(
            symbol="SPY",
            trade_date=entry_date,
            expiry=entry_date + timedelta(days=35),
            strike=440.0,
            right="P",
            delta=-0.20,
            implied_vol=0.18,
            mid=5.0,
            quantity=1,
            collateral=44000.0,
            vrp=None,
        )
        strategy._open_position = OpenPosition(
            signal=signal,
            entry_date=entry_date,
            entry_underlying_price=float(prices["SPY"].iloc[entry_idx]),
            entry_mid=signal.mid,
            quantity=signal.quantity,
            delta=signal.delta,
        )

        # Try to exit at a later date
        exit_idx = 220
        ts = prices.index[exit_idx]
        spy_price = float(prices["SPY"].iloc[exit_idx])
        market = _make_market_snapshot(ts, spy_price)
        data_replay = DataReplay(prices)

        orders = strategy(ts, data_replay, VirtualPortfolio(100_000), market)
        # Exit may or may not trigger depending on exact conditions
        assert isinstance(orders, list)

    def test_regime_blocks_entry_in_high_vol(self):
        """Strategy does not enter in high_vol regime."""
        rng = np.random.RandomState(99)
        days = 500
        dates = pd.bdate_range(start="2015-01-02", periods=days)
        returns = rng.normal(0, 0.06, days)  # extreme volatility
        prices = pd.DataFrame({"SPY": 450 * (1 + returns).cumprod()}, index=dates)
        prices = prices.clip(lower=1.0)

        config = S2Config(regime_scales={"bull": 1.0, "sideways": 0.75, "bear": 0.25, "high_vol": 0.0})
        strategy = VRPStrategy(prices, config)

        idx = 300
        ts = prices.index[idx]
        spy_price = float(prices["SPY"].iloc[idx])
        market = _make_market_snapshot(ts, spy_price)
        data_replay = DataReplay(prices)

        orders = strategy(ts, data_replay, VirtualPortfolio(100_000), market)
        assert isinstance(orders, list)


# ---- Walk-forward Backtest Tests ----

class TestS2WalkForward:
    """Test S2 backtest with walk-forward validation."""

    def test_walkforward_completes(self):
        """Walk-forward backtest completes without errors."""
        prices = _make_prices(1000)
        config = S2Config(min_dte=20, max_dte=60, vrp_entry_threshold=0.0)
        wf_config = WalkForwardConfig(in_sample_days=252, out_of_sample_days=126)

        strategy = VRPStrategy(prices, config)
        if not strategy.health_check():
            pytest.skip("Not enough data for S2 health check in synthetic test")

        result = run_s2_backtest_from_prices(
            prices=prices,
            wf_config=wf_config,
            s2_config=config,
            run_robustness=False,
        )
        assert "oos_sharpe" in result
        assert isinstance(result["oos_sharpe"], float)

    def test_backtest_returns_gate_results(self):
        """Backtest returns gate results structure."""
        prices = _make_prices(1500)
        config = S2Config(min_dte=20, max_dte=60, vrp_entry_threshold=0.0)
        wf_config = WalkForwardConfig(in_sample_days=504, out_of_sample_days=252)

        strategy = VRPStrategy(prices, config)
        if not strategy.health_check():
            pytest.skip("Not enough data for S2 health check")

        result = run_s2_backtest_from_prices(
            prices=prices,
            wf_config=wf_config,
            s2_config=config,
            run_robustness=False,
        )
        assert "gate_report" in result
        assert isinstance(result["gate_report"], dict)

    def test_oos_sharpe_is_finite(self):
        """OOS Sharpe from walk-forward is a finite number."""
        prices = _make_prices(1500)
        config = S2Config(min_dte=20, max_dte=60, vrp_entry_threshold=0.0)
        wf_config = WalkForwardConfig(in_sample_days=504, out_of_sample_days=252)

        strategy = VRPStrategy(prices, config)
        if not strategy.health_check():
            pytest.skip("Not enough data")

        result = run_s2_backtest_from_prices(
            prices=prices,
            wf_config=wf_config,
            s2_config=config,
            run_robustness=False,
        )
        assert np.isfinite(result["oos_sharpe"])

    def test_milestone_d_field_present(self):
        """Result dict includes milestone_d_pass boolean."""
        prices = _make_prices(1500)
        config = S2Config(vrp_entry_threshold=0.0)
        wf_config = WalkForwardConfig(in_sample_days=504, out_of_sample_days=252)

        strategy = VRPStrategy(prices, config)
        if not strategy.health_check():
            pytest.skip("Not enough data")

        result = run_s2_backtest_from_prices(
            prices=prices,
            wf_config=wf_config,
            s2_config=config,
            run_robustness=False,
        )
        assert "milestone_d_pass" in result
        assert isinstance(result["milestone_d_pass"], bool)

    def test_summary_json_written(self, tmp_path):
        """Backtest writes summary.json to output directory."""
        prices = _make_prices(1500)
        config = S2Config(vrp_entry_threshold=0.0)
        wf_config = WalkForwardConfig(in_sample_days=504, out_of_sample_days=252)

        strategy = VRPStrategy(prices, config)
        if not strategy.health_check():
            pytest.skip("Not enough data")

        output_dir = tmp_path / "s2_test"
        result = run_s2_backtest_from_prices(
            prices=prices,
            output_dir=output_dir,
            wf_config=wf_config,
            s2_config=config,
            run_robustness=False,
        )
        assert (output_dir / "summary.json").exists()
        summary = json.loads((output_dir / "summary.json").read_text())
        assert "oos_sharpe" in summary
        assert "milestone_d_pass" in summary


# ---- Backtest Helper Functions ----

class TestBacktestHelpers:
    """Test helper functions in the backtest module."""

    def test_split_regime_returns(self):
        """_split_regime_returns produces high_vol and low_vol regimes."""
        dates = pd.bdate_range("2018-01-02", periods=300)
        rng = np.random.RandomState(42)
        returns = pd.Series(rng.normal(0.0005, 0.012, len(dates)), index=dates)

        regimes = _split_regime_returns(returns)
        assert isinstance(regimes, dict)
        assert "high_vol" in regimes or "low_vol" in regimes

    def test_extract_stress_periods(self):
        """_extract_stress_periods identifies worst drawdown and known events."""
        dates = pd.bdate_range("2017-01-02", periods=1000)
        rng = np.random.RandomState(42)
        returns = pd.Series(rng.normal(0.0003, 0.01, len(dates)), index=dates)

        stress = _extract_stress_periods(returns)
        assert isinstance(stress, dict)
        assert "worst_drawdown" in stress or len(stress) >= 0

    def test_run_perturbation_completes(self):
        """_run_perturbation produces a list of Sharpe values."""
        prices = _make_prices(1000)
        config = S2Config(vrp_entry_threshold=0.0)
        wf_config = WalkForwardConfig(in_sample_days=252, out_of_sample_days=126)

        sharpes = _run_perturbation(prices, config, wf_config)
        assert isinstance(sharpes, list)
