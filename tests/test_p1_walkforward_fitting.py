"""P1-13 Walk-forward IS/OOS fitting measurement.

Problem (from audit): WalkForwardRunner measures only OOS Sharpe.
IS Sharpe is never computed or compared. The IS/OOS degradation ratio
(how much worse OOS is vs IS) is the key metric for detecting overfitting.

Fix: WalkForwardResult.aggregate_metrics must include:
  - mean_is_sharpe: average IS Sharpe across windows
  - mean_oos_sharpe: same as existing mean_sharpe (alias for clarity)
  - is_oos_degradation_ratio: mean_oos_sharpe / mean_is_sharpe
    (1.0 = no degradation; 0.5 = OOS half as good; negative = OOS loses money)
"""
from __future__ import annotations

import pytest
import numpy as np
import pandas as pd
from unittest.mock import MagicMock


def _make_simple_strategy(seed=42):
    """Return a deterministic strategy callable (always BUY nothing)."""
    def strategy(ts, data_replay, portfolio, market):
        return []
    return strategy


class TestWalkForwardFittingMeasurement:

    def test_aggregate_metrics_has_mean_is_sharpe(self):
        """WalkForwardResult.aggregate_metrics must have 'mean_is_sharpe' key."""
        from src.backtest.walkforward.runner import WalkForwardRunner, WalkForwardConfig
        from src.backtest.engine.data_replay import DataReplay

        dates = pd.date_range("2015-01-01", periods=600, freq="B")
        rng = np.random.default_rng(42)
        prices = pd.DataFrame(
            {"SPY": 100 * (1 + rng.normal(0, 0.01, len(dates))).cumprod()},
            index=dates,
        )

        runner = WalkForwardRunner(
            wf_config=WalkForwardConfig(in_sample_days=200, out_of_sample_days=100)
        )
        result = runner.run(DataReplay(prices), _make_simple_strategy())

        assert "mean_is_sharpe" in result.aggregate_metrics, (
            "WalkForwardResult.aggregate_metrics must include 'mean_is_sharpe'. "
            "Without IS Sharpe we cannot measure IS/OOS degradation (overfitting). "
            f"Got keys: {list(result.aggregate_metrics.keys())}"
        )

    def test_aggregate_metrics_has_is_oos_degradation_ratio(self):
        """aggregate_metrics must have 'is_oos_degradation_ratio' key."""
        from src.backtest.walkforward.runner import WalkForwardRunner, WalkForwardConfig
        from src.backtest.engine.data_replay import DataReplay

        dates = pd.date_range("2015-01-01", periods=600, freq="B")
        rng = np.random.default_rng(42)
        prices = pd.DataFrame(
            {"SPY": 100 * (1 + rng.normal(0, 0.01, len(dates))).cumprod()},
            index=dates,
        )

        runner = WalkForwardRunner(
            wf_config=WalkForwardConfig(in_sample_days=200, out_of_sample_days=100)
        )
        result = runner.run(DataReplay(prices), _make_simple_strategy())

        assert "is_oos_degradation_ratio" in result.aggregate_metrics, (
            "WalkForwardResult.aggregate_metrics must include 'is_oos_degradation_ratio'. "
            "This is the key overfitting diagnostic: OOS Sharpe / IS Sharpe. "
            f"Got keys: {list(result.aggregate_metrics.keys())}"
        )

    def test_degradation_ratio_is_numeric(self):
        """is_oos_degradation_ratio must be a float (or None when IS Sharpe is 0)."""
        from src.backtest.walkforward.runner import WalkForwardRunner, WalkForwardConfig
        from src.backtest.engine.data_replay import DataReplay

        dates = pd.date_range("2015-01-01", periods=600, freq="B")
        rng = np.random.default_rng(42)
        prices = pd.DataFrame(
            {"SPY": 100 * (1 + rng.normal(0, 0.01, len(dates))).cumprod()},
            index=dates,
        )

        runner = WalkForwardRunner(
            wf_config=WalkForwardConfig(in_sample_days=200, out_of_sample_days=100)
        )
        result = runner.run(DataReplay(prices), _make_simple_strategy())

        ratio = result.aggregate_metrics["is_oos_degradation_ratio"]
        assert ratio is None or isinstance(ratio, (int, float)), (
            f"is_oos_degradation_ratio must be float or None, got {type(ratio)}"
        )

    def test_window_result_has_is_sharpe(self):
        """Each WindowResult must have 'is_sharpe' in oos_metrics (renamed to window_metrics)
        or IS sharpe accessible from the window."""
        from src.backtest.walkforward.runner import WalkForwardRunner, WalkForwardConfig
        from src.backtest.engine.data_replay import DataReplay

        dates = pd.date_range("2015-01-01", periods=600, freq="B")
        rng = np.random.default_rng(42)
        prices = pd.DataFrame(
            {"SPY": 100 * (1 + rng.normal(0, 0.01, len(dates))).cumprod()},
            index=dates,
        )

        runner = WalkForwardRunner(
            wf_config=WalkForwardConfig(in_sample_days=200, out_of_sample_days=100)
        )
        result = runner.run(DataReplay(prices), _make_simple_strategy())

        if result.windows:
            w = result.windows[0]
            assert hasattr(w, "is_sharpe") or "is_sharpe" in result.aggregate_metrics, (
                "Either WindowResult.is_sharpe or aggregate_metrics['is_sharpe'] must exist "
                "so IS performance is traceable per window."
            )
