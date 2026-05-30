"""T-105: S1 sensitivity analysis tests."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.backtest.walkforward.runner import WalkForwardConfig
from src.strategies.s1.sensitivity import run_sensitivity_grid


N_DAYS = 800


@pytest.fixture
def synthetic_prices() -> pd.DataFrame:
    """Synthetic 5-ticker price series."""
    rng = np.random.default_rng(42)
    dates = pd.date_range("2015-01-01", periods=N_DAYS, freq="B")
    tickers = ["A", "B", "C", "D", "E"]
    data = {t: 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, N_DAYS))) for t in tickers}
    return pd.DataFrame(data, index=dates)


@pytest.fixture
def small_wf_config() -> WalkForwardConfig:
    return WalkForwardConfig(in_sample_days=400, out_of_sample_days=150)


class TestSensitivityGrid:
    def test_runs_without_error(self, synthetic_prices, small_wf_config) -> None:
        result = run_sensitivity_grid(
            synthetic_prices,
            lookback_longs=(252, 378),
            vol_windows=(30, 60),
            thresholds=(0.0, 0.5),
            wf_config=small_wf_config,
        )
        assert isinstance(result, dict)

    def test_surface_lookback_vol_shape(self, synthetic_prices, small_wf_config) -> None:
        result = run_sensitivity_grid(
            synthetic_prices,
            lookback_longs=(252, 378),
            vol_windows=(30, 60),
            thresholds=(0.0,),
            wf_config=small_wf_config,
        )
        lv = result["surface_lookback_vol"]
        assert lv.shape[0] == 2  # 2 lookbacks
        assert lv.shape[1] == 2  # 2 vol windows

    def test_base_sharpe_is_float(self, synthetic_prices, small_wf_config) -> None:
        result = run_sensitivity_grid(
            synthetic_prices,
            lookback_longs=(252,),
            vol_windows=(60,),
            thresholds=(0.0,),
            wf_config=small_wf_config,
        )
        assert isinstance(result["base_sharpe"], float)

    def test_all_results_list(self, synthetic_prices, small_wf_config) -> None:
        result = run_sensitivity_grid(
            synthetic_prices,
            lookback_longs=(252, 378),
            vol_windows=(30, 60),
            thresholds=(0.0, 0.5),
            wf_config=small_wf_config,
        )
        assert isinstance(result["all_results"], list)
        assert len(result["all_results"]) > 0

    def test_output_dir_created(self, synthetic_prices, small_wf_config, tmp_path) -> None:
        out = tmp_path / "sensitivity_report"
        run_sensitivity_grid(
            synthetic_prices,
            lookback_longs=(252,),
            vol_windows=(60,),
            thresholds=(0.0,),
            wf_config=small_wf_config,
            output_dir=out,
        )
        assert (out / "sensitivity.json").exists()
        assert (out / "sensitivity_report.txt").exists()

    def test_sharpe_values_are_numeric(self, synthetic_prices, small_wf_config) -> None:
        result = run_sensitivity_grid(
            synthetic_prices,
            lookback_longs=(252,),
            vol_windows=(60,),
            thresholds=(0.0,),
            wf_config=small_wf_config,
        )
        lv = result["surface_lookback_vol"]
        for col in lv.columns:
            for val in lv[col]:
                assert isinstance(val, float) or np.isnan(val)
