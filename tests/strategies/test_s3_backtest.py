"""T-203: S3 walk-forward backtest + gate validation tests."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.backtest.walkforward.runner import WalkForwardConfig
from src.strategies.s3.strategy import S3Config

# 900 business days → ~3.6 years; IS=500 OOS=200 yields 2 windows
N_DAYS = 900
N_STOCKS = 15


def _make_synthetic_prices(n: int = N_DAYS, n_stocks: int = N_STOCKS, seed: int = 42) -> pd.DataFrame:
    """SPY + n_stocks with varying betas and drifts."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2015-01-01", periods=n, freq="B")

    spy_ret = rng.normal(0.0004, 0.008, n)
    spy = 300 * np.exp(np.cumsum(spy_ret))
    data = {"SPY": spy}

    for i in range(n_stocks):
        drift = rng.uniform(-0.001, 0.002)
        beta = rng.uniform(0.5, 1.5)
        idio = rng.normal(0, 0.005, n)
        log_ret = beta * spy_ret + idio + drift
        data[f"T{i+1:02d}"] = 100 * np.exp(np.cumsum(log_ret))

    return pd.DataFrame(data, index=dates)


@pytest.fixture
def synthetic_prices() -> pd.DataFrame:
    return _make_synthetic_prices()


@pytest.fixture
def small_wf_config() -> WalkForwardConfig:
    """Fast walk-forward: IS=500 days, OOS=200 days."""
    return WalkForwardConfig(in_sample_days=500, out_of_sample_days=200)


@pytest.fixture
def small_s3_config() -> S3Config:
    return S3Config(lookback=252, beta_window=252)


# ---------------------------------------------------------------------------
# TestS3BacktestRuns
# ---------------------------------------------------------------------------


class TestS3BacktestRuns:
    def test_backtest_runs_without_error(
        self,
        synthetic_prices: pd.DataFrame,
        small_wf_config: WalkForwardConfig,
        small_s3_config: S3Config,
        tmp_path: Path,
    ) -> None:
        from src.strategies.s3.backtest import run_s3_backtest_from_prices

        result = run_s3_backtest_from_prices(
            prices=synthetic_prices,
            output_dir=tmp_path / "s3_backtest",
            wf_config=small_wf_config,
            s3_config=small_s3_config,
            run_robustness=False,
        )
        assert isinstance(result, dict)

    def test_oos_sharpe_is_float(
        self,
        synthetic_prices: pd.DataFrame,
        small_wf_config: WalkForwardConfig,
        small_s3_config: S3Config,
        tmp_path: Path,
    ) -> None:
        from src.strategies.s3.backtest import run_s3_backtest_from_prices

        result = run_s3_backtest_from_prices(
            prices=synthetic_prices,
            output_dir=tmp_path / "s3_backtest",
            wf_config=small_wf_config,
            s3_config=small_s3_config,
            run_robustness=False,
        )
        assert isinstance(result["oos_sharpe"], float)

    def test_results_contain_expected_keys(
        self,
        synthetic_prices: pd.DataFrame,
        small_wf_config: WalkForwardConfig,
        small_s3_config: S3Config,
        tmp_path: Path,
    ) -> None:
        from src.strategies.s3.backtest import run_s3_backtest_from_prices

        result = run_s3_backtest_from_prices(
            prices=synthetic_prices,
            output_dir=tmp_path / "s3_backtest",
            wf_config=small_wf_config,
            s3_config=small_s3_config,
            run_robustness=False,
        )
        for key in ("oos_sharpe", "wf_aggregate", "gate_report", "milestone_c_pass", "report_path"):
            assert key in result, f"Missing key: {key}"

    def test_milestone_c_flag_is_bool(
        self,
        synthetic_prices: pd.DataFrame,
        small_wf_config: WalkForwardConfig,
        small_s3_config: S3Config,
        tmp_path: Path,
    ) -> None:
        from src.strategies.s3.backtest import run_s3_backtest_from_prices

        result = run_s3_backtest_from_prices(
            prices=synthetic_prices,
            output_dir=tmp_path / "s3_backtest",
            wf_config=small_wf_config,
            s3_config=small_s3_config,
            run_robustness=False,
        )
        assert isinstance(result["milestone_c_pass"], bool)

    def test_health_check_failure_raises(
        self,
        small_wf_config: WalkForwardConfig,
        tmp_path: Path,
    ) -> None:
        from src.strategies.s3.backtest import run_s3_backtest_from_prices

        # Only 100 days — too short for signals
        short_prices = _make_synthetic_prices(n=100)
        with pytest.raises(RuntimeError, match="health check failed"):
            run_s3_backtest_from_prices(
                prices=short_prices,
                output_dir=tmp_path / "s3_fail",
                wf_config=small_wf_config,
                run_robustness=False,
            )


# ---------------------------------------------------------------------------
# TestGateReportGenerated
# ---------------------------------------------------------------------------


class TestGateReportGenerated:
    def test_all_5_gates_present(
        self,
        synthetic_prices: pd.DataFrame,
        small_wf_config: WalkForwardConfig,
        small_s3_config: S3Config,
        tmp_path: Path,
    ) -> None:
        from src.strategies.s3.backtest import run_s3_backtest_from_prices

        result = run_s3_backtest_from_prices(
            prices=synthetic_prices,
            output_dir=tmp_path / "s3_backtest",
            wf_config=small_wf_config,
            s3_config=small_s3_config,
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
        self,
        synthetic_prices: pd.DataFrame,
        small_wf_config: WalkForwardConfig,
        small_s3_config: S3Config,
        tmp_path: Path,
    ) -> None:
        from src.strategies.s3.backtest import run_s3_backtest_from_prices

        result = run_s3_backtest_from_prices(
            prices=synthetic_prices,
            output_dir=tmp_path / "s3_backtest",
            wf_config=small_wf_config,
            s3_config=small_s3_config,
            run_robustness=False,
        )
        for name, gate in result["gate_report"].items():
            assert "passed" in gate, f"{name} missing 'passed' field"
            assert isinstance(gate["passed"], bool), f"{name} 'passed' must be bool"

    def test_gate_report_json_saved(
        self,
        synthetic_prices: pd.DataFrame,
        small_wf_config: WalkForwardConfig,
        small_s3_config: S3Config,
        tmp_path: Path,
    ) -> None:
        from src.strategies.s3.backtest import run_s3_backtest_from_prices

        out_dir = tmp_path / "s3_backtest"
        run_s3_backtest_from_prices(
            prices=synthetic_prices,
            output_dir=out_dir,
            wf_config=small_wf_config,
            s3_config=small_s3_config,
            run_robustness=False,
        )
        assert (out_dir / "gate_report.json").exists()

    def test_summary_json_saved(
        self,
        synthetic_prices: pd.DataFrame,
        small_wf_config: WalkForwardConfig,
        small_s3_config: S3Config,
        tmp_path: Path,
    ) -> None:
        from src.strategies.s3.backtest import run_s3_backtest_from_prices

        out_dir = tmp_path / "s3_backtest"
        run_s3_backtest_from_prices(
            prices=synthetic_prices,
            output_dir=out_dir,
            wf_config=small_wf_config,
            s3_config=small_s3_config,
            run_robustness=False,
        )
        assert (out_dir / "summary.json").exists()


# ---------------------------------------------------------------------------
# TestReportContents
# ---------------------------------------------------------------------------


class TestReportContents:
    def test_wf_aggregate_has_n_windows_ge_1(
        self,
        synthetic_prices: pd.DataFrame,
        small_wf_config: WalkForwardConfig,
        small_s3_config: S3Config,
        tmp_path: Path,
    ) -> None:
        from src.strategies.s3.backtest import run_s3_backtest_from_prices

        result = run_s3_backtest_from_prices(
            prices=synthetic_prices,
            output_dir=tmp_path / "s3_backtest",
            wf_config=small_wf_config,
            s3_config=small_s3_config,
            run_robustness=False,
        )
        assert "n_windows" in result["wf_aggregate"]
        assert result["wf_aggregate"]["n_windows"] >= 1

    def test_summary_json_valid_and_has_sharpe(
        self,
        synthetic_prices: pd.DataFrame,
        small_wf_config: WalkForwardConfig,
        small_s3_config: S3Config,
        tmp_path: Path,
    ) -> None:
        from src.strategies.s3.backtest import run_s3_backtest_from_prices

        out_dir = tmp_path / "s3_backtest"
        run_s3_backtest_from_prices(
            prices=synthetic_prices,
            output_dir=out_dir,
            wf_config=small_wf_config,
            s3_config=small_s3_config,
            run_robustness=False,
        )
        data = json.loads((out_dir / "summary.json").read_text())
        assert "oos_sharpe" in data
        assert "milestone_c_pass" in data

    def test_gate_report_json_parseable(
        self,
        synthetic_prices: pd.DataFrame,
        small_wf_config: WalkForwardConfig,
        small_s3_config: S3Config,
        tmp_path: Path,
    ) -> None:
        from src.strategies.s3.backtest import run_s3_backtest_from_prices

        out_dir = tmp_path / "s3_backtest"
        run_s3_backtest_from_prices(
            prices=synthetic_prices,
            output_dir=out_dir,
            wf_config=small_wf_config,
            s3_config=small_s3_config,
            run_robustness=False,
        )
        data = json.loads((out_dir / "gate_report.json").read_text())
        assert isinstance(data, dict)
        assert len(data) == 5
