"""T-104: S1 walk-forward backtest + gate validation tests."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.backtest.walkforward.runner import WalkForwardConfig
from src.strategies.s1.strategy import S1Config

# 800 business days → ~3.2 years; IS=400 OOS=150 yields 2 windows
N_DAYS = 800


@pytest.fixture
def synthetic_prices() -> pd.DataFrame:
    """Synthetic 5-ticker price series; no yfinance required."""
    rng = np.random.default_rng(42)
    dates = pd.date_range("2015-01-01", periods=N_DAYS, freq="B")
    tickers = ["A", "B", "C", "D", "E"]
    data = {t: 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, N_DAYS))) for t in tickers}
    return pd.DataFrame(data, index=dates)


@pytest.fixture
def small_wf_config() -> WalkForwardConfig:
    """Fast walk-forward: 400-day IS, 150-day OOS (avoids full 5-year run)."""
    return WalkForwardConfig(in_sample_days=400, out_of_sample_days=150)


# ---------------------------------------------------------------------------
# TestS1BacktestRuns
# ---------------------------------------------------------------------------


class TestS1BacktestRuns:
    def test_backtest_runs_without_error(
        self, synthetic_prices: pd.DataFrame, small_wf_config: WalkForwardConfig, tmp_path: Path
    ) -> None:
        from src.strategies.s1.backtest import run_s1_backtest_from_prices

        result = run_s1_backtest_from_prices(
            prices=synthetic_prices,
            output_dir=tmp_path / "s1_backtest",
            wf_config=small_wf_config,
            run_robustness=False,
        )
        assert isinstance(result, dict)

    def test_oos_sharpe_is_float(
        self, synthetic_prices: pd.DataFrame, small_wf_config: WalkForwardConfig, tmp_path: Path
    ) -> None:
        from src.strategies.s1.backtest import run_s1_backtest_from_prices

        result = run_s1_backtest_from_prices(
            prices=synthetic_prices,
            output_dir=tmp_path / "s1_backtest",
            wf_config=small_wf_config,
            run_robustness=False,
        )
        assert isinstance(result["oos_sharpe"], float)

    def test_results_contain_expected_keys(
        self, synthetic_prices: pd.DataFrame, small_wf_config: WalkForwardConfig, tmp_path: Path
    ) -> None:
        from src.strategies.s1.backtest import run_s1_backtest_from_prices

        result = run_s1_backtest_from_prices(
            prices=synthetic_prices,
            output_dir=tmp_path / "s1_backtest",
            wf_config=small_wf_config,
            run_robustness=False,
        )
        for key in ("oos_sharpe", "wf_aggregate", "gate_report", "milestone_b_pass", "report_path"):
            assert key in result, f"Missing key: {key}"

    def test_milestone_b_flag_is_bool(
        self, synthetic_prices: pd.DataFrame, small_wf_config: WalkForwardConfig, tmp_path: Path
    ) -> None:
        from src.strategies.s1.backtest import run_s1_backtest_from_prices

        result = run_s1_backtest_from_prices(
            prices=synthetic_prices,
            output_dir=tmp_path / "s1_backtest",
            wf_config=small_wf_config,
            run_robustness=False,
        )
        assert isinstance(result["milestone_b_pass"], bool)
        # milestone_b_pass must match oos_sharpe >= 0.5
        assert result["milestone_b_pass"] == (result["oos_sharpe"] >= 0.5)


# ---------------------------------------------------------------------------
# TestGateReportGenerated
# ---------------------------------------------------------------------------


class TestGateReportGenerated:
    def test_all_5_gates_present(
        self, synthetic_prices: pd.DataFrame, small_wf_config: WalkForwardConfig, tmp_path: Path
    ) -> None:
        from src.strategies.s1.backtest import run_s1_backtest_from_prices

        result = run_s1_backtest_from_prices(
            prices=synthetic_prices,
            output_dir=tmp_path / "s1_backtest",
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
        self, synthetic_prices: pd.DataFrame, small_wf_config: WalkForwardConfig, tmp_path: Path
    ) -> None:
        from src.strategies.s1.backtest import run_s1_backtest_from_prices

        result = run_s1_backtest_from_prices(
            prices=synthetic_prices,
            output_dir=tmp_path / "s1_backtest",
            wf_config=small_wf_config,
            run_robustness=False,
        )
        for name, gate in result["gate_report"].items():
            assert "passed" in gate, f"{name} missing 'passed' field"
            assert isinstance(gate["passed"], bool), f"{name} 'passed' must be bool"

    def test_gate_report_json_saved(
        self, synthetic_prices: pd.DataFrame, small_wf_config: WalkForwardConfig, tmp_path: Path
    ) -> None:
        from src.strategies.s1.backtest import run_s1_backtest_from_prices

        out_dir = tmp_path / "s1_backtest"
        run_s1_backtest_from_prices(
            prices=synthetic_prices,
            output_dir=out_dir,
            wf_config=small_wf_config,
            run_robustness=False,
        )
        assert (out_dir / "gate_report.json").exists()

    def test_summary_json_saved(
        self, synthetic_prices: pd.DataFrame, small_wf_config: WalkForwardConfig, tmp_path: Path
    ) -> None:
        from src.strategies.s1.backtest import run_s1_backtest_from_prices

        out_dir = tmp_path / "s1_backtest"
        run_s1_backtest_from_prices(
            prices=synthetic_prices,
            output_dir=out_dir,
            wf_config=small_wf_config,
            run_robustness=False,
        )
        assert (out_dir / "summary.json").exists()


# ---------------------------------------------------------------------------
# TestReportContents
# ---------------------------------------------------------------------------


class TestReportContents:
    def test_wf_aggregate_has_n_windows_ge_1(
        self, synthetic_prices: pd.DataFrame, small_wf_config: WalkForwardConfig, tmp_path: Path
    ) -> None:
        from src.strategies.s1.backtest import run_s1_backtest_from_prices

        result = run_s1_backtest_from_prices(
            prices=synthetic_prices,
            output_dir=tmp_path / "s1_backtest",
            wf_config=small_wf_config,
            run_robustness=False,
        )
        assert "n_windows" in result["wf_aggregate"]
        assert result["wf_aggregate"]["n_windows"] >= 1

    def test_summary_json_valid_and_has_sharpe(
        self, synthetic_prices: pd.DataFrame, small_wf_config: WalkForwardConfig, tmp_path: Path
    ) -> None:
        from src.strategies.s1.backtest import run_s1_backtest_from_prices

        out_dir = tmp_path / "s1_backtest"
        run_s1_backtest_from_prices(
            prices=synthetic_prices,
            output_dir=out_dir,
            wf_config=small_wf_config,
            run_robustness=False,
        )
        data = json.loads((out_dir / "summary.json").read_text())
        assert "oos_sharpe" in data

    def test_gate_report_json_parseable(
        self, synthetic_prices: pd.DataFrame, small_wf_config: WalkForwardConfig, tmp_path: Path
    ) -> None:
        from src.strategies.s1.backtest import run_s1_backtest_from_prices

        out_dir = tmp_path / "s1_backtest"
        run_s1_backtest_from_prices(
            prices=synthetic_prices,
            output_dir=out_dir,
            wf_config=small_wf_config,
            run_robustness=False,
        )
        data = json.loads((out_dir / "gate_report.json").read_text())
        assert isinstance(data, dict)
        assert len(data) == 5
