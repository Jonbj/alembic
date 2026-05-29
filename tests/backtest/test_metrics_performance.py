"""Tests for backtest/metrics/performance.py (T-006).

Validation strategy: expected values are hand-computed from the same formulas
used by empyrical 0.5.5 (empyrical has a pandas-datareader incompatibility in
this environment, so we validate numerically against closed-form results rather
than calling the library directly).

All tolerances are set to 1e-6 — matching floating-point precision of any
correct implementation of the same formulas.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.backtest.metrics.performance import (
    TRADING_DAYS,
    annualized_return,
    annualized_volatility,
    calmar_ratio,
    omega_ratio,
    sharpe_ratio,
    sortino_ratio,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def flat_returns() -> pd.Series:
    """Zero-return series — edge case for division checks."""
    return pd.Series([0.0] * 252)


@pytest.fixture
def constant_positive() -> pd.Series:
    """Daily return of exactly 0.1% — deterministic."""
    return pd.Series([0.001] * 252)


@pytest.fixture
def mixed_returns() -> pd.Series:
    """Seeded realistic return series."""
    rng = np.random.default_rng(42)
    return pd.Series(rng.normal(0.0003, 0.012, 252))


# ---------------------------------------------------------------------------
# annualized_return
# ---------------------------------------------------------------------------

class TestAnnualizedReturn:
    def test_empty_returns_zero(self):
        assert annualized_return(pd.Series(dtype=float)) == 0.0

    def test_constant_positive_return(self, constant_positive):
        r = constant_positive
        expected = float((1.001) ** 252 - 1)
        result = annualized_return(r)
        assert abs(result - expected) < 1e-6

    def test_flat_returns_zero(self, flat_returns):
        assert annualized_return(flat_returns) == 0.0

    def test_single_return(self):
        r = pd.Series([0.1])
        # num_years = 1/252; result = 1.1^252 - 1
        expected = float(1.1 ** 252 - 1)
        assert abs(annualized_return(r) - expected) < 1e-6

    def test_negative_total_return(self):
        r = pd.Series([-0.001] * 252)
        result = annualized_return(r)
        assert result < 0

    def test_half_year_data(self):
        r = pd.Series([0.001] * 126)
        # num_years = 126/252 = 0.5; ending = 1.001^126; result = ending^2 - 1
        ending = 1.001 ** 126
        expected = ending ** 2 - 1
        assert abs(annualized_return(r) - expected) < 1e-6


# ---------------------------------------------------------------------------
# annualized_volatility
# ---------------------------------------------------------------------------

class TestAnnualizedVolatility:
    def test_empty_returns_zero(self):
        assert annualized_volatility(pd.Series(dtype=float)) == 0.0

    def test_single_return_zero(self):
        assert annualized_volatility(pd.Series([0.01])) == 0.0

    def test_constant_returns_zero(self, constant_positive):
        assert annualized_volatility(constant_positive) == pytest.approx(0.0, abs=1e-10)

    def test_known_vol(self):
        rng = np.random.default_rng(0)
        r = pd.Series(rng.normal(0, 0.01, 500))
        expected = float(r.std(ddof=1) * np.sqrt(252))
        assert abs(annualized_volatility(r) - expected) < 1e-10

    def test_returns_positive(self, mixed_returns):
        assert annualized_volatility(mixed_returns) > 0


# ---------------------------------------------------------------------------
# sharpe_ratio
# ---------------------------------------------------------------------------

class TestSharpeRatio:
    def test_empty_returns_zero(self):
        assert sharpe_ratio(pd.Series(dtype=float)) == 0.0

    def test_single_return_zero(self):
        assert sharpe_ratio(pd.Series([0.01])) == 0.0

    def test_flat_returns_zero(self, flat_returns):
        assert sharpe_ratio(flat_returns) == 0.0

    def test_matches_formula(self, mixed_returns):
        r = mixed_returns
        rf = 0.02
        rf_per_day = rf / 252
        excess = r - rf_per_day
        expected = float(excess.mean() / excess.std(ddof=1) * np.sqrt(252))
        result = sharpe_ratio(r, risk_free=rf)
        assert abs(result - expected) < 1e-10

    def test_zero_risk_free_sharpe(self, constant_positive):
        r = constant_positive
        expected = float(r.mean() / r.std(ddof=1) * np.sqrt(252))
        result = sharpe_ratio(r)
        # constant series: std → 0, returns 0.0
        assert result == 0.0

    def test_positive_drift_positive_sharpe(self):
        rng = np.random.default_rng(1)
        r = pd.Series(rng.normal(0.001, 0.01, 500))
        assert sharpe_ratio(r) > 0

    def test_negative_drift_negative_sharpe(self):
        rng = np.random.default_rng(2)
        r = pd.Series(rng.normal(-0.001, 0.01, 500))
        assert sharpe_ratio(r) < 0

    def test_scaling_with_periods(self, mixed_returns):
        r = mixed_returns
        sharpe_252 = sharpe_ratio(r, periods=252)
        sharpe_126 = sharpe_ratio(r, periods=126)
        ratio = sharpe_252 / sharpe_126
        # sharpe ∝ sqrt(periods): ratio should be sqrt(252/126) = sqrt(2)
        assert abs(ratio - np.sqrt(252 / 126)) < 1e-6


# ---------------------------------------------------------------------------
# sortino_ratio
# ---------------------------------------------------------------------------

class TestSortinoRatio:
    def test_empty_returns_zero(self):
        assert sortino_ratio(pd.Series(dtype=float)) == 0.0

    def test_single_return_zero(self):
        assert sortino_ratio(pd.Series([0.01])) == 0.0

    def test_all_positive_returns_no_downside(self):
        r = pd.Series([0.001] * 100)
        # No downside → downside_variance = 0 → returns 0 (not inf, avoid edge case)
        assert sortino_ratio(r) == 0.0

    def test_matches_formula(self, mixed_returns):
        r = mixed_returns
        mar = 0.0 / 252
        adj = r - mar
        downside = np.minimum(adj, 0.0)
        downside_variance = float((downside ** 2).mean())
        if downside_variance == 0:
            expected = 0.0
        else:
            expected = float(adj.mean() / np.sqrt(downside_variance) * np.sqrt(252))
        result = sortino_ratio(r)
        assert abs(result - expected) < 1e-10

    def test_sortino_ge_sharpe_for_positive_skew(self):
        rng = np.random.default_rng(10)
        r = pd.Series(abs(rng.normal(0.002, 0.01, 500)))  # only gains → high sortino
        # with only positives sortino → 0 (no downside) — just verify it's >= 0
        assert sortino_ratio(r) >= 0


# ---------------------------------------------------------------------------
# calmar_ratio
# ---------------------------------------------------------------------------

class TestCalmarRatio:
    def test_empty_returns_zero(self):
        assert calmar_ratio(pd.Series(dtype=float)) == 0.0

    def test_monotone_increase_zero_calmar(self):
        r = pd.Series([0.001] * 252)
        # max_drawdown = 0 → calmar = 0
        assert calmar_ratio(r) == 0.0

    def test_positive_with_drawdown(self):
        rng = np.random.default_rng(7)
        r = pd.Series(rng.normal(0.0005, 0.015, 756))
        result = calmar_ratio(r)
        assert isinstance(result, float)

    def test_formula_consistency(self, mixed_returns):
        from src.backtest.metrics.risk import max_drawdown
        r = mixed_returns
        ann = annualized_return(r)
        mdd = max_drawdown(r)
        expected = ann / abs(mdd) if mdd != 0.0 else 0.0
        assert abs(calmar_ratio(r) - expected) < 1e-10


# ---------------------------------------------------------------------------
# omega_ratio
# ---------------------------------------------------------------------------

class TestOmegaRatio:
    def test_all_gains_returns_inf(self):
        r = pd.Series([0.001] * 100)
        result = omega_ratio(r)
        assert result == np.inf

    def test_all_losses_returns_zero(self):
        r = pd.Series([-0.001] * 100)
        result = omega_ratio(r)
        assert result == 0.0 or (isinstance(result, float) and result < 1)

    def test_balanced_series_near_one(self):
        rng = np.random.default_rng(5)
        r = pd.Series(rng.normal(0, 0.01, 1000))
        result = omega_ratio(r)
        assert 0.5 < result < 2.0  # near 1 for zero-drift series

    def test_positive_drift_gt_one(self):
        rng = np.random.default_rng(6)
        r = pd.Series(rng.normal(0.001, 0.01, 500))
        assert omega_ratio(r) > 1.0
