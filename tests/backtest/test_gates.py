"""Tests for T-007 validation gates.

Test strategy:
  - Random strategy fails all 5 gates
  - SPY buy-and-hold passes Gates 1, 2, 5; fails Gates 3 and 4
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.backtest.gates.gate_types import GateResult, GateReport
from src.backtest.gates.gate_1_significance import gate_1_significance
from src.backtest.gates.gate_2_walkforward import gate_2_walkforward
from src.backtest.gates.gate_3_robustness import gate_3_robustness
from src.backtest.gates.gate_4_regime import gate_4_regime
from src.backtest.gates.gate_5_stress import gate_5_stress
from src.backtest.gates.runner import run_all_gates, GateConfig

TRADING_DAYS = 252


def _dates(n: int, start: str = "2018-01-02") -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=n)


@pytest.fixture
def random_returns() -> pd.Series:
    rng = np.random.default_rng(123)
    n = 5 * TRADING_DAYS
    daily = rng.normal(0.0, 0.015, n) - 0.0005
    return pd.Series(daily, index=_dates(n))


@pytest.fixture
def spy_like_returns() -> pd.Series:
    rng = np.random.default_rng(777)
    n = 10 * TRADING_DAYS
    daily = rng.normal(0.0005, 0.010, n)
    return pd.Series(daily, index=_dates(n, "2013-01-02"))


def _random_wf():
    rng = np.random.default_rng(456)
    result = []
    for _ in range(4):
        d = rng.normal(0.0, 0.015, TRADING_DAYS) - 0.0005
        result.append(pd.Series(d, index=_dates(TRADING_DAYS)))
    return result


def _spy_wf():
    rng = np.random.default_rng(888)
    result = []
    for _ in range(4):
        d = rng.normal(0.0005, 0.010, TRADING_DAYS)
        result.append(pd.Series(d, index=_dates(TRADING_DAYS)))
    return result


def _random_regimes():
    rng = np.random.default_rng(999)
    n = TRADING_DAYS
    dates = _dates(n)
    return {
        "bull": pd.Series(rng.normal(0.0, 0.015, n) - 0.0005, index=dates),
        "bear": pd.Series(rng.normal(0.0, 0.025, n) - 0.001, index=dates),
        "sideways": pd.Series(rng.normal(0.0, 0.010, n) - 0.001, index=dates),
    }


def _spy_regimes():
    rng = np.random.default_rng(555)
    n = TRADING_DAYS
    return {
        "bull": pd.Series(rng.normal(0.0010, 0.010, n), index=_dates(n, "2013-01-02")),
        "bear": pd.Series(rng.normal(-0.0010, 0.025, n), index=_dates(n, "2008-01-02")),
        "sideways": pd.Series(rng.normal(0.0005, 0.008, n), index=_dates(n, "2015-01-02")),
    }


def _random_stress():
    rng = np.random.default_rng(333)
    return {
        "2008_gfc": pd.Series(rng.normal(-0.003, 0.030, 252), index=_dates(252, "2008-01-02")),
        "2020_covid": pd.Series(rng.normal(-0.002, 0.035, 63), index=_dates(63, "2020-02-19")),
        "2022_rate_hikes": pd.Series(rng.normal(-0.001, 0.020, 252), index=_dates(252, "2022-01-03")),
    }


def _spy_stress():
    rng = np.random.default_rng(1111)
    return {
        "2008_gfc": pd.Series(rng.normal(0.0005, 0.025, 252), index=_dates(252, "2008-01-02")),
        "2020_covid": pd.Series(rng.normal(0.001, 0.030, 63), index=_dates(63, "2020-02-19")),
        "2022_rate_hikes": pd.Series(rng.normal(0.0004, 0.018, 252), index=_dates(252, "2022-01-03")),
    }


class TestGate1Significance:
    def test_random_fails(self, random_returns):
        result = gate_1_significance(random_returns)
        assert result.passed is False
        assert result.details["sharpe"] < 0.5

    def test_spy_passes(self, spy_like_returns):
        result = gate_1_significance(spy_like_returns)
        assert result.passed is True
        assert result.details["sharpe"] > 0.0


class TestGate2WalkForward:
    def test_random_fails(self):
        result = gate_2_walkforward(_random_wf())
        assert result.passed is False

    def test_spy_passes(self):
        result = gate_2_walkforward(_spy_wf())
        assert result.passed is True


class TestGate3Robustness:
    def test_random_fails(self):
        result = gate_3_robustness([0.1, -0.2, 0.3, -0.1, 0.05])
        assert result.passed is False

    def test_spy_fails_high_cv(self):
        result = gate_3_robustness([0.5, 1.2, -0.3, 0.8], max_cv=0.5)
        assert result.passed is False

    def test_tight_sharpes_pass(self):
        result = gate_3_robustness([1.1, 1.05, 1.15, 1.08, 1.12], max_cv=0.5)
        assert result.passed is True


class TestGate4Regime:
    def test_random_fails(self):
        result = gate_4_regime(_random_regimes())
        assert result.passed is False

    def test_spy_fails_bear_regime(self):
        result = gate_4_regime(_spy_regimes(), min_passing_regimes=3)
        assert result.passed is False

    def test_strong_strategy_passes(self):
        rng = np.random.default_rng(2024)
        n = TRADING_DAYS
        dates = _dates(n)
        regimes = {
            "bull": pd.Series(rng.normal(0.001, 0.010, n), index=dates),
            "bear": pd.Series(rng.normal(0.0005, 0.012, n), index=dates),
            "sideways": pd.Series(rng.normal(0.0008, 0.008, n), index=dates),
        }
        result = gate_4_regime(regimes, min_passing_regimes=3)
        assert result.passed is True


class TestGate5Stress:
    def test_random_fails(self):
        result = gate_5_stress(_random_stress())
        assert result.passed is False

    def test_spy_passes_stress(self):
        result = gate_5_stress(_spy_stress(), max_drawdown_allowed=-0.50)
        assert result.passed is True


class TestRunner:
    def test_random_fails_all(self, random_returns):
        report = run_all_gates(
            returns=random_returns,
            wf_results=_random_wf(),
            perturbed_sharpes=[0.1, -0.2, 0.3, -0.1],
            regime_returns=_random_regimes(),
            stress_returns=_random_stress(),
        )
        assert isinstance(report, GateReport)
        assert report.overall_passed is False
        assert all(not g.passed for g in report.gate_results.values())

    def test_spy_passes_1_2_5_fails_3_4(self, spy_like_returns):
        report = run_all_gates(
            returns=spy_like_returns,
            wf_results=_spy_wf(),
            perturbed_sharpes=[0.5, 1.2, -0.3, 0.8],
            regime_returns=_spy_regimes(),
            stress_returns=_spy_stress(),
            config=GateConfig(max_drawdown_allowed=-0.50),
        )
        assert report.gate_results["gate_1_significance"].passed is True
        assert report.gate_results["gate_2_walkforward"].passed is True
        assert report.gate_results["gate_3_robustness"].passed is False
        assert report.gate_results["gate_4_regime"].passed is False
        assert report.gate_results["gate_5_stress"].passed is True

    def test_report_summary(self, random_returns):
        report = run_all_gates(
            returns=random_returns,
            wf_results=_random_wf(),
            perturbed_sharpes=[0.1, -0.2, 0.3, -0.1],
            regime_returns=_random_regimes(),
            stress_returns=_random_stress(),
        )
        assert "GATE REPORT" in report.summary()


class TestEdgeCases:
    def test_empty_walkforward(self):
        result = gate_2_walkforward([])
        assert result.passed is False
        assert "error" in result.details

    def test_empty_perturbations(self):
        result = gate_3_robustness([])
        assert result.passed is False

    def test_single_window(self):
        rng = np.random.default_rng(42)
        daily = pd.Series(rng.normal(0.0005, 0.010, 252), index=_dates(252))
        result = gate_2_walkforward([daily])
        assert isinstance(result, GateResult)

    def test_zero_returns(self):
        zero = pd.Series(0.0, index=_dates(252))
        result = gate_1_significance(zero)
        assert result.passed is False

    def test_empty_returns(self):
        result = gate_1_significance(pd.Series(dtype=float))
        assert result.passed is False

    def test_gate_report_properties(self):
        report = GateReport()
        assert report.overall_passed is True
        assert report.passed_gates == []
        assert report.failed_gates == []
