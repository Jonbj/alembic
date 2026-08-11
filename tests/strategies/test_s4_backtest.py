"""T-403: S4 walk-forward backtest + gate validation tests."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from src.backtest.walkforward.runner import WalkForwardConfig
from src.strategies.s4.config import S4Config

# 800 business days (~3.2 years); IS=400 OOS=150 yields 2 windows
N_DAYS = 800


@pytest.fixture
def synthetic_prices() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    dates = pd.date_range("2015-01-01", periods=N_DAYS, freq="B")
    tickers = ["SPY", "AAPL", "MSFT", "GOOG", "AMZN", "META"]
    data = {t: 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, N_DAYS))) for t in tickers}
    return pd.DataFrame(data, index=dates)


@pytest.fixture
def synthetic_signals(synthetic_prices: pd.DataFrame) -> pd.DataFrame:
    """Synthetic sentiment signals aligned with price dates (~weekly cadence, tz-naive)."""
    rng = np.random.default_rng(99)
    tickers = [c for c in synthetic_prices.columns if c != "SPY"]
    signal_dates = synthetic_prices.index[::5].tolist()
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
def small_wf_config() -> WalkForwardConfig:
    return WalkForwardConfig(in_sample_days=400, out_of_sample_days=150)


# ---------------------------------------------------------------------------
# TestS4BacktestRuns
# ---------------------------------------------------------------------------


class TestS4BacktestRuns:
    def test_backtest_runs_without_error(
        self, synthetic_prices, synthetic_signals, small_wf_config, tmp_path
    ) -> None:
        from src.strategies.s4.backtest import run_s4_backtest_from_prices_and_signals

        result = run_s4_backtest_from_prices_and_signals(
            prices=synthetic_prices,
            signals_df=synthetic_signals,
            output_dir=tmp_path / "s4_backtest",
            wf_config=small_wf_config,
            run_robustness=False,
        )
        assert isinstance(result, dict)

    def test_oos_sharpe_is_float(
        self, synthetic_prices, synthetic_signals, small_wf_config, tmp_path
    ) -> None:
        from src.strategies.s4.backtest import run_s4_backtest_from_prices_and_signals

        result = run_s4_backtest_from_prices_and_signals(
            prices=synthetic_prices,
            signals_df=synthetic_signals,
            output_dir=tmp_path / "s4_backtest",
            wf_config=small_wf_config,
            run_robustness=False,
        )
        assert isinstance(result["oos_sharpe"], float)

    def test_result_has_expected_keys(
        self, synthetic_prices, synthetic_signals, small_wf_config, tmp_path
    ) -> None:
        from src.strategies.s4.backtest import run_s4_backtest_from_prices_and_signals

        result = run_s4_backtest_from_prices_and_signals(
            prices=synthetic_prices,
            signals_df=synthetic_signals,
            output_dir=tmp_path / "s4_backtest",
            wf_config=small_wf_config,
            run_robustness=False,
        )
        for key in (
            "oos_sharpe",
            "wf_aggregate",
            "gate_report",
            "hard_gates_pass",
            "all_gates_pass",
            "report_path",
        ):
            assert key in result, f"Missing key: {key}"

    def test_hard_gates_pass_is_bool(
        self, synthetic_prices, synthetic_signals, small_wf_config, tmp_path
    ) -> None:
        from src.strategies.s4.backtest import run_s4_backtest_from_prices_and_signals

        result = run_s4_backtest_from_prices_and_signals(
            prices=synthetic_prices,
            signals_df=synthetic_signals,
            output_dir=tmp_path / "s4_backtest",
            wf_config=small_wf_config,
            run_robustness=False,
        )
        assert isinstance(result["hard_gates_pass"], bool)

    def test_empty_signals_runs_without_crash(
        self, synthetic_prices, small_wf_config, tmp_path
    ) -> None:
        from src.strategies.s4.backtest import run_s4_backtest_from_prices_and_signals

        empty_signals = pd.DataFrame(
            columns=["symbol", "score", "confidence", "generated_at"]
        )
        result = run_s4_backtest_from_prices_and_signals(
            prices=synthetic_prices,
            signals_df=empty_signals,
            output_dir=tmp_path / "s4_backtest",
            wf_config=small_wf_config,
            run_robustness=False,
        )
        assert isinstance(result["oos_sharpe"], float)

    def test_wf_aggregate_has_n_windows_ge_1(
        self, synthetic_prices, synthetic_signals, small_wf_config, tmp_path
    ) -> None:
        from src.strategies.s4.backtest import run_s4_backtest_from_prices_and_signals

        result = run_s4_backtest_from_prices_and_signals(
            prices=synthetic_prices,
            signals_df=synthetic_signals,
            output_dir=tmp_path / "s4_backtest",
            wf_config=small_wf_config,
            run_robustness=False,
        )
        assert result["wf_aggregate"].get("n_windows", 0) >= 1


# ---------------------------------------------------------------------------
# TestGateReportGenerated
# ---------------------------------------------------------------------------


class TestGateReportGenerated:
    def test_all_5_gates_present(
        self, synthetic_prices, synthetic_signals, small_wf_config, tmp_path
    ) -> None:
        from src.strategies.s4.backtest import run_s4_backtest_from_prices_and_signals

        result = run_s4_backtest_from_prices_and_signals(
            prices=synthetic_prices,
            signals_df=synthetic_signals,
            output_dir=tmp_path / "s4_backtest",
            wf_config=small_wf_config,
            run_robustness=False,
        )
        expected = {
            "gate_1_significance",
            "gate_2_walkforward",
            "gate_3_robustness",
            "gate_4_regime",
            "gate_5_stress",
        }
        assert set(result["gate_report"].keys()) == expected

    def test_each_gate_has_passed_field(
        self, synthetic_prices, synthetic_signals, small_wf_config, tmp_path
    ) -> None:
        from src.strategies.s4.backtest import run_s4_backtest_from_prices_and_signals

        result = run_s4_backtest_from_prices_and_signals(
            prices=synthetic_prices,
            signals_df=synthetic_signals,
            output_dir=tmp_path / "s4_backtest",
            wf_config=small_wf_config,
            run_robustness=False,
        )
        for name, gate in result["gate_report"].items():
            assert "passed" in gate, f"{name} missing 'passed'"
            assert isinstance(gate["passed"], bool)

    def test_gate_report_json_saved(
        self, synthetic_prices, synthetic_signals, small_wf_config, tmp_path
    ) -> None:
        from src.strategies.s4.backtest import run_s4_backtest_from_prices_and_signals

        out_dir = tmp_path / "s4_backtest"
        run_s4_backtest_from_prices_and_signals(
            prices=synthetic_prices,
            signals_df=synthetic_signals,
            output_dir=out_dir,
            wf_config=small_wf_config,
            run_robustness=False,
        )
        assert (out_dir / "gate_report.json").exists()

    def test_summary_json_saved(
        self, synthetic_prices, synthetic_signals, small_wf_config, tmp_path
    ) -> None:
        from src.strategies.s4.backtest import run_s4_backtest_from_prices_and_signals

        out_dir = tmp_path / "s4_backtest"
        run_s4_backtest_from_prices_and_signals(
            prices=synthetic_prices,
            signals_df=synthetic_signals,
            output_dir=out_dir,
            wf_config=small_wf_config,
            run_robustness=False,
        )
        assert (out_dir / "summary.json").exists()

    def test_summary_json_has_sharpe(
        self, synthetic_prices, synthetic_signals, small_wf_config, tmp_path
    ) -> None:
        from src.strategies.s4.backtest import run_s4_backtest_from_prices_and_signals

        out_dir = tmp_path / "s4_backtest"
        run_s4_backtest_from_prices_and_signals(
            prices=synthetic_prices,
            signals_df=synthetic_signals,
            output_dir=out_dir,
            wf_config=small_wf_config,
            run_robustness=False,
        )
        data = json.loads((out_dir / "summary.json").read_text())
        assert "oos_sharpe" in data

    def test_gate_report_json_has_5_gates(
        self, synthetic_prices, synthetic_signals, small_wf_config, tmp_path
    ) -> None:
        from src.strategies.s4.backtest import run_s4_backtest_from_prices_and_signals

        out_dir = tmp_path / "s4_backtest"
        run_s4_backtest_from_prices_and_signals(
            prices=synthetic_prices,
            signals_df=synthetic_signals,
            output_dir=out_dir,
            wf_config=small_wf_config,
            run_robustness=False,
        )
        data = json.loads((out_dir / "gate_report.json").read_text())
        assert len([key for key in data if key.startswith("gate_")]) == 5
        assert data["synthetic"] is False
        assert data["decision_eligible"] is True


# ---------------------------------------------------------------------------
# TestPerturbation
# ---------------------------------------------------------------------------


class TestPerturbation:
    def test_perturbation_returns_list_of_floats(
        self, synthetic_prices, synthetic_signals, small_wf_config
    ) -> None:
        from src.strategies.s4.backtest import _run_perturbation

        sharpes = _run_perturbation(
            synthetic_prices, synthetic_signals, S4Config(), small_wf_config
        )
        assert isinstance(sharpes, list)
        assert len(sharpes) >= 1
        assert all(isinstance(s, float) for s in sharpes)

    def test_perturbation_produces_multiple_sharpes(
        self, synthetic_prices, synthetic_signals, small_wf_config
    ) -> None:
        from src.strategies.s4.backtest import _run_perturbation

        sharpes = _run_perturbation(
            synthetic_prices, synthetic_signals, S4Config(), small_wf_config
        )
        assert len(sharpes) >= 3


# ---------------------------------------------------------------------------
# TestRegimeReturns
# ---------------------------------------------------------------------------


class TestRegimeReturns:
    def test_split_regime_returns_regimes_present(self) -> None:
        from src.strategies.s4.backtest import _split_regime_returns

        rng = np.random.default_rng(0)
        dates = pd.date_range("2015-01-01", periods=200, freq="B")
        returns = pd.Series(rng.normal(0.001, 0.01, 200), index=dates)

        regimes = _split_regime_returns(returns)
        assert len(regimes) >= 1

    def test_split_regime_returns_non_overlapping(self) -> None:
        from src.strategies.s4.backtest import _split_regime_returns

        rng = np.random.default_rng(1)
        dates = pd.date_range("2015-01-01", periods=200, freq="B")
        returns = pd.Series(rng.normal(0.001, 0.01, 200), index=dates)

        regimes = _split_regime_returns(returns)
        if "high_vol" in regimes and "low_vol" in regimes:
            overlap = set(regimes["high_vol"].index) & set(regimes["low_vol"].index)
            assert len(overlap) == 0


# ---------------------------------------------------------------------------
# TestTimezoneNormalization
# ---------------------------------------------------------------------------


class TestTimezoneNormalization:
    def test_tz_aware_signals_handled_without_error(
        self, synthetic_prices, small_wf_config, tmp_path
    ) -> None:
        """tz-aware generated_at columns must be normalized and not raise TypeError."""
        from src.strategies.s4.backtest import run_s4_backtest_from_prices_and_signals

        rng = np.random.default_rng(7)
        tickers = [c for c in synthetic_prices.columns if c != "SPY"]
        signal_dates = synthetic_prices.index[::10].tolist()
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
                    "generated_at": pd.Timestamp(ts, tz="UTC"),  # tz-aware
                })
        tz_signals = pd.DataFrame(rows)

        result = run_s4_backtest_from_prices_and_signals(
            prices=synthetic_prices,
            signals_df=tz_signals,
            output_dir=tmp_path / "s4_backtest",
            wf_config=small_wf_config,
            run_robustness=False,
        )
        assert isinstance(result["oos_sharpe"], float)


# ---------------------------------------------------------------------------
# Regression: pd.concat timestamp preservation (B-05 fix)
# ---------------------------------------------------------------------------


class TestConcatTimestampPreservation:
    def test_oos_sharpe_computed_from_timestamped_returns(
        self, synthetic_prices, synthetic_signals, small_wf_config, tmp_path
    ) -> None:
        """Regression: pd.concat(ignore_index=True) dropped DatetimeIndex →
        Sharpe annualized over wrong period count. Fixed to sort_index()."""
        from src.strategies.s4.backtest import run_s4_backtest_from_prices_and_signals

        result = run_s4_backtest_from_prices_and_signals(
            prices=synthetic_prices,
            signals_df=synthetic_signals,
            output_dir=tmp_path / "s4_bt_concat",
            wf_config=small_wf_config,
            run_robustness=False,
        )
        sharpe = result["oos_sharpe"]
        assert isinstance(sharpe, float)
        assert sharpe == sharpe  # not NaN
