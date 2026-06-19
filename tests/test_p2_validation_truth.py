"""P2-03 Validation Truth Wiring — RED tests.

Verifies that:
  T1-T3: S1/S3/S4 backtests use extract_historical_stress_periods() instead of
         the synthetic _extract_stress_periods() for Gate 5 input.
  T4:    When OOS data has no overlap with any historical crisis period, stress_returns
         is None (gate_5 auto-fails with clear message, not silently passed).
  T5-T7: is_oos_degradation_ratio is a top-level key in S1/S3/S4 backtest return dict
         (currently buried in wf_aggregate).
  T8-T9: universe is accepted by run_s1_backtest_from_prices() and threaded through
         to TimeSeriesMomentum for PIT filtering; run_s1_backtest_full() passes the
         loaded universe down to the runner.

All 9 tests must be RED before implementation.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from src.backtest.walkforward.runner import WalkForwardConfig


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_gate_report_mock() -> MagicMock:
    """Minimal gate report mock — enough to satisfy all post-gate code paths."""
    gr = MagicMock()
    gr.overall_passed = True
    gr.gate_results = {}
    gr.summary.return_value = "mock-gate-summary"
    return gr


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def crisis_wf_config() -> WalkForwardConfig:
    """Small walk-forward: IS=300, OOS=100 — fast enough for test, OOS lands in 2020."""
    return WalkForwardConfig(in_sample_days=300, out_of_sample_days=100)


@pytest.fixture
def crisis_era_prices_s1() -> pd.DataFrame:
    """5-ticker prices starting 2019-01-01.

    With IS=300, OOS=100 the first OOS window starts ~2020-03-20 (300 business
    days after 2019-01-01), which overlaps the 2020 COVID crisis window
    (2020-02-19 – 2020-04-30).  extract_historical_stress_periods() will find
    '2020_covid'; the synthetic _extract_stress_periods() returns 'worst_drawdown'.
    """
    rng = np.random.default_rng(42)
    dates = pd.date_range("2019-01-01", periods=600, freq="B")
    tickers = ["A", "B", "C", "D", "E"]
    data = {t: 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, 600))) for t in tickers}
    return pd.DataFrame(data, index=dates)


@pytest.fixture
def crisis_era_prices_s3s4() -> pd.DataFrame:
    """SPY + 10 stocks starting 2019-01-01.  Same date rationale as crisis_era_prices_s1."""
    rng = np.random.default_rng(7)
    n = 600
    dates = pd.date_range("2019-01-01", periods=n, freq="B")
    spy_ret = rng.normal(0.0004, 0.008, n)
    spy = 300 * np.exp(np.cumsum(spy_ret))
    data: dict = {"SPY": spy}
    for i in range(10):
        beta = rng.uniform(0.5, 1.5)
        idio = rng.normal(0, 0.005, n)
        data[f"T{i + 1:02d}"] = 100 * np.exp(np.cumsum(beta * spy_ret + idio))
    return pd.DataFrame(data, index=dates)


@pytest.fixture
def crisis_signals(crisis_era_prices_s3s4: pd.DataFrame) -> pd.DataFrame:
    """Synthetic S4 signals aligned with crisis_era_prices_s3s4."""
    rng = np.random.default_rng(3)
    tickers = [c for c in crisis_era_prices_s3s4.columns if c != "SPY"]
    signal_dates = crisis_era_prices_s3s4.index[::5].tolist()
    rows = []
    for ts in signal_dates:
        for ticker in tickers:
            rows.append({
                "symbol": ticker,
                "score": float(rng.uniform(0.1, 0.9)),
                "confidence": float(rng.uniform(0.4, 0.9)),
                "reasoning": "synthetic",
                "model_id": "test",
                "ensemble_std": 0.0,
                "fallback_used": False,
                "generated_at": pd.Timestamp(ts),
            })
    return pd.DataFrame(rows)


@pytest.fixture
def no_overlap_prices() -> pd.DataFrame:
    """5-ticker prices starting 2023-01-01.

    OOS windows will land in 2024-2025, which has NO overlap with any of the
    three historical crisis periods (GFC 2008, COVID 2020, rates 2022).
    extract_historical_stress_periods() returns {} → stress_returns must be None.
    """
    rng = np.random.default_rng(99)
    dates = pd.date_range("2023-01-01", periods=600, freq="B")
    tickers = ["A", "B", "C", "D", "E"]
    data = {t: 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, 600))) for t in tickers}
    return pd.DataFrame(data, index=dates)


@pytest.fixture
def synthetic_prices_s1() -> pd.DataFrame:
    """Standard 5-ticker synthetic prices (2015-2018) used by most existing S1 tests."""
    rng = np.random.default_rng(42)
    dates = pd.date_range("2015-01-01", periods=800, freq="B")
    tickers = ["A", "B", "C", "D", "E"]
    data = {t: 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, 800))) for t in tickers}
    return pd.DataFrame(data, index=dates)


@pytest.fixture
def small_wf_config() -> WalkForwardConfig:
    return WalkForwardConfig(in_sample_days=400, out_of_sample_days=150)


@pytest.fixture
def synthetic_prices_s3() -> pd.DataFrame:
    """SPY + 15 stocks, 2015-2018, for S3 ratio test."""
    rng = np.random.default_rng(42)
    n = 900
    dates = pd.date_range("2015-01-01", periods=n, freq="B")
    spy_ret = rng.normal(0.0004, 0.008, n)
    spy = 300 * np.exp(np.cumsum(spy_ret))
    data: dict = {"SPY": spy}
    for i in range(15):
        beta = rng.uniform(0.5, 1.5)
        idio = rng.normal(0, 0.005, n)
        data[f"T{i + 1:02d}"] = 100 * np.exp(np.cumsum(beta * spy_ret + idio))
    return pd.DataFrame(data, index=dates)


@pytest.fixture
def synthetic_prices_s4() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    dates = pd.date_range("2015-01-01", periods=800, freq="B")
    tickers = ["SPY", "AAPL", "MSFT", "GOOG", "AMZN", "META"]
    data = {t: 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, 800))) for t in tickers}
    return pd.DataFrame(data, index=dates)


@pytest.fixture
def synthetic_signals_s4(synthetic_prices_s4: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(99)
    tickers = [c for c in synthetic_prices_s4.columns if c != "SPY"]
    signal_dates = synthetic_prices_s4.index[::5].tolist()
    rows = []
    for ts in signal_dates:
        for ticker in tickers:
            rows.append({
                "symbol": ticker,
                "score": float(rng.uniform(0.1, 0.9)),
                "confidence": float(rng.uniform(0.4, 0.9)),
                "reasoning": "synthetic",
                "model_id": "test_model",
                "ensemble_std": 0.0,
                "fallback_used": False,
                "generated_at": pd.Timestamp(ts),
            })
    return pd.DataFrame(rows)


@pytest.fixture
def small_s3_wf_config() -> WalkForwardConfig:
    return WalkForwardConfig(in_sample_days=500, out_of_sample_days=200)


@pytest.fixture
def small_s4_wf_config() -> WalkForwardConfig:
    return WalkForwardConfig(in_sample_days=400, out_of_sample_days=150)


# ─────────────────────────────────────────────────────────────────────────────
# T1-T4: Historical stress wiring
# ─────────────────────────────────────────────────────────────────────────────


class TestHistoricalStressWiring:

    def test_s1_stress_uses_historical_periods(
        self, crisis_era_prices_s1, crisis_wf_config, tmp_path
    ):
        """S1 backtest must pass historical stress period keys to Gate 5.

        When OOS data covers 2020, stress_returns must contain '2020_covid'.
        Currently _extract_stress_periods() always returns 'worst_drawdown'.
        Fix: replace with extract_historical_stress_periods().
        """
        from src.strategies.s1.backtest import run_s1_backtest_from_prices

        captured: dict = {}

        def fake_gates(*args, **kwargs):
            captured["stress_returns"] = kwargs.get("stress_returns")
            return _make_gate_report_mock()

        with patch("src.strategies.s1.backtest.run_all_gates", side_effect=fake_gates):
            run_s1_backtest_from_prices(
                prices=crisis_era_prices_s1,
                output_dir=tmp_path / "s1",
                wf_config=crisis_wf_config,
                run_robustness=False,
            )

        stress = captured.get("stress_returns")
        assert stress is not None, (
            "stress_returns must not be None when OOS data covers 2020. "
            "extract_historical_stress_periods() should find '2020_covid'."
        )
        assert "2020_covid" in stress, (
            f"stress_returns must contain '2020_covid' key when OOS spans 2020. "
            f"Got: {list(stress.keys())}. "
            "Replace _extract_stress_periods() with extract_historical_stress_periods() "
            "in src/strategies/s1/backtest.py."
        )

    def test_s3_stress_uses_historical_periods(
        self, crisis_era_prices_s3s4, crisis_wf_config, tmp_path
    ):
        """S3 backtest must pass historical stress period keys to Gate 5."""
        from src.strategies.s3.backtest import run_s3_backtest_from_prices
        from src.strategies.s3.strategy import S3Config

        captured: dict = {}

        def fake_gates(*args, **kwargs):
            captured["stress_returns"] = kwargs.get("stress_returns")
            return _make_gate_report_mock()

        with patch("src.strategies.s3.backtest.run_all_gates", side_effect=fake_gates):
            run_s3_backtest_from_prices(
                prices=crisis_era_prices_s3s4,
                output_dir=tmp_path / "s3",
                wf_config=crisis_wf_config,
                s3_config=S3Config(lookback=126, beta_window=126),
                run_robustness=False,
            )

        stress = captured.get("stress_returns")
        assert stress is not None, (
            "stress_returns must not be None when OOS data covers 2020."
        )
        assert "2020_covid" in stress, (
            f"stress_returns must contain '2020_covid' for S3. Got: {list(stress.keys())}. "
            "Replace _extract_stress_periods() with extract_historical_stress_periods() "
            "in src/strategies/s3/backtest.py."
        )

    def test_s4_stress_uses_historical_periods(
        self, crisis_era_prices_s3s4, crisis_signals, crisis_wf_config, tmp_path
    ):
        """S4 backtest must pass historical stress period keys to Gate 5."""
        from src.strategies.s4.backtest import run_s4_backtest_from_prices_and_signals
        from src.strategies.s4.config import S4Config

        captured: dict = {}

        def fake_gates(*args, **kwargs):
            captured["stress_returns"] = kwargs.get("stress_returns")
            return _make_gate_report_mock()

        with patch("src.strategies.s4.backtest.run_all_gates", side_effect=fake_gates):
            run_s4_backtest_from_prices_and_signals(
                prices=crisis_era_prices_s3s4,
                signals_df=crisis_signals,
                output_dir=tmp_path / "s4",
                wf_config=crisis_wf_config,
                run_robustness=False,
            )

        stress = captured.get("stress_returns")
        assert stress is not None, (
            "stress_returns must not be None when OOS data covers 2020."
        )
        assert "2020_covid" in stress, (
            f"stress_returns must contain '2020_covid' for S4. Got: {list(stress.keys())}. "
            "Replace _extract_stress_periods() with extract_historical_stress_periods() "
            "in src/strategies/s4/backtest.py."
        )

    def test_no_historical_overlap_yields_none_stress(
        self, no_overlap_prices, crisis_wf_config, tmp_path
    ):
        """When OOS data has no overlap with any crisis period, stress_returns must be None.

        This ensures gate_5 fails cleanly (no stress period data provided) rather
        than silently passing on synthetic data.  With 2023+ prices, no historical
        crisis window overlaps, so extract_historical_stress_periods() returns {}.
        The backtest must then pass stress_returns=None — NOT a synthetic slice.
        """
        from src.strategies.s1.backtest import run_s1_backtest_from_prices

        captured: dict = {}

        def fake_gates(*args, **kwargs):
            captured["stress_returns"] = kwargs.get("stress_returns")
            return _make_gate_report_mock()

        with patch("src.strategies.s1.backtest.run_all_gates", side_effect=fake_gates):
            run_s1_backtest_from_prices(
                prices=no_overlap_prices,
                output_dir=tmp_path / "s1_recent",
                wf_config=crisis_wf_config,
                run_robustness=False,
            )

        stress = captured.get("stress_returns")
        keys = list((stress or {}).keys())
        assert stress is None, (
            f"stress_returns must be None when OOS has no historical crisis overlap. "
            f"Got: {keys}. "
            "Replace _extract_stress_periods() with extract_historical_stress_periods(); "
            "pass `hist if hist else None` so gate_5 fails explicitly."
        )


# ─────────────────────────────────────────────────────────────────────────────
# T5-T7: is_oos_degradation_ratio as top-level key
# ─────────────────────────────────────────────────────────────────────────────


class TestDegradationRatioTopLevel:

    def test_s1_result_has_is_oos_degradation_ratio_toplevel(
        self, synthetic_prices_s1, small_wf_config, tmp_path
    ):
        """S1 backtest result must have 'is_oos_degradation_ratio' as a top-level key.

        Currently the ratio is in result['wf_aggregate']['is_oos_degradation_ratio'].
        It must also be at result['is_oos_degradation_ratio'] so callers don't need
        to dig into wf_aggregate.
        """
        from src.strategies.s1.backtest import run_s1_backtest_from_prices

        result = run_s1_backtest_from_prices(
            prices=synthetic_prices_s1,
            output_dir=tmp_path / "s1",
            wf_config=small_wf_config,
            run_robustness=False,
        )
        assert "is_oos_degradation_ratio" in result, (
            "'is_oos_degradation_ratio' must be a top-level key in the S1 backtest result. "
            "Currently it is only accessible via result['wf_aggregate']['is_oos_degradation_ratio']. "
            "Add it as a top-level key in run_s1_backtest_from_prices() return dict."
        )

    def test_s3_result_has_is_oos_degradation_ratio_toplevel(
        self, synthetic_prices_s3, small_s3_wf_config, tmp_path
    ):
        """S3 backtest result must have 'is_oos_degradation_ratio' as a top-level key."""
        from src.strategies.s3.backtest import run_s3_backtest_from_prices
        from src.strategies.s3.strategy import S3Config

        result = run_s3_backtest_from_prices(
            prices=synthetic_prices_s3,
            output_dir=tmp_path / "s3",
            wf_config=small_s3_wf_config,
            s3_config=S3Config(lookback=252, beta_window=252),
            run_robustness=False,
        )
        assert "is_oos_degradation_ratio" in result, (
            "'is_oos_degradation_ratio' must be a top-level key in the S3 backtest result. "
            "Add it to run_s3_backtest_from_prices() return dict."
        )

    def test_s4_result_has_is_oos_degradation_ratio_toplevel(
        self, synthetic_prices_s4, synthetic_signals_s4, small_s4_wf_config, tmp_path
    ):
        """S4 backtest result must have 'is_oos_degradation_ratio' as a top-level key."""
        from src.strategies.s4.backtest import run_s4_backtest_from_prices_and_signals

        result = run_s4_backtest_from_prices_and_signals(
            prices=synthetic_prices_s4,
            signals_df=synthetic_signals_s4,
            output_dir=tmp_path / "s4",
            wf_config=small_s4_wf_config,
            run_robustness=False,
        )
        assert "is_oos_degradation_ratio" in result, (
            "'is_oos_degradation_ratio' must be a top-level key in the S4 backtest result. "
            "Add it to run_s4_backtest_from_prices_and_signals() return dict."
        )


# ─────────────────────────────────────────────────────────────────────────────
# T8-T9: PIT universe wiring (S1)
# ─────────────────────────────────────────────────────────────────────────────


class TestPITUniverseWiring:

    def test_s1_backtest_from_prices_accepts_universe_param(
        self, synthetic_prices_s1, small_wf_config, tmp_path
    ):
        """run_s1_backtest_from_prices() must accept a universe= kwarg.

        P1-08 added universe support to TimeSeriesMomentum.__init__(), but the
        backtest caller (run_s1_backtest_from_prices) still constructs the strategy
        without passing universe.  Add universe=None param and thread it through.
        """
        from src.strategies.s1.backtest import run_s1_backtest_from_prices

        tickers = list(synthetic_prices_s1.columns)
        mock_universe = MagicMock()
        mock_universe.active_at.return_value = [
            MagicMock(symbol=t) for t in tickers
        ]

        try:
            run_s1_backtest_from_prices(
                prices=synthetic_prices_s1,
                output_dir=tmp_path / "s1_u",
                wf_config=small_wf_config,
                run_robustness=False,
                universe=mock_universe,
            )
        except TypeError as exc:
            pytest.fail(
                f"run_s1_backtest_from_prices() does not accept 'universe' parameter: {exc}. "
                "Add universe=None to the function signature and pass it to TimeSeriesMomentum()."
            )

        assert mock_universe.active_at.called, (
            "universe.active_at() must be called during backtest to apply PIT filtering. "
            "The universe param was accepted but not passed to TimeSeriesMomentum — "
            "it must be threaded through: TimeSeriesMomentum(prices, s1_config, universe=universe)."
        )

    def test_s1_backtest_full_passes_universe_to_runner(self, tmp_path):
        """run_s1_backtest_full() must pass the loaded universe to run_s1_backtest_from_prices().

        Currently it loads `universe = load_universe('s1')` but calls
        run_s1_backtest_from_prices(prices=..., output_dir=...) without universe.
        After fix, universe= must be forwarded.
        """
        mock_universe = MagicMock()
        mock_prices = MagicMock()
        captured: dict = {}

        def capture_from_prices(*args, **kwargs):
            captured["universe"] = kwargs.get("universe")
            return {
                "oos_sharpe": 0.5,
                "wf_aggregate": {"is_oos_degradation_ratio": 0.8},
                "gate_report": {},
                "milestone_b_pass": True,
                "report_path": str(tmp_path),
                "is_oos_degradation_ratio": 0.8,
            }

        with patch("src.strategies.s1.backtest.load_universe", return_value=mock_universe), \
             patch("src.backtest.data.cache.ParquetCache"), \
             patch("src.strategies.s1.backtest.DataLoader") as MockLoader, \
             patch(
                 "src.strategies.s1.backtest.run_s1_backtest_from_prices",
                 side_effect=capture_from_prices,
             ):
            MockLoader.return_value.get_aligned_prices.return_value = mock_prices
            from src.strategies.s1.backtest import run_s1_backtest_full
            run_s1_backtest_full(output_dir=tmp_path)

        assert captured.get("universe") is mock_universe, (
            "run_s1_backtest_full() must forward the loaded universe to "
            "run_s1_backtest_from_prices(universe=...). "
            f"Got: {captured.get('universe')}. "
            "Add `universe=universe` to the run_s1_backtest_from_prices() call."
        )
