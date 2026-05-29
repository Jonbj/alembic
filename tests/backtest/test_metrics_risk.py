"""Tests for backtest/metrics/risk.py (T-006).

Expected values are derived from the same closed-form formulas used by
empyrical 0.5.5.  See module docstring in risk.py for formula references.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.backtest.metrics.risk import (
    drawdown_series,
    excess_kurtosis,
    expected_shortfall,
    max_drawdown,
    skewness,
    tail_ratio,
    value_at_risk,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def monotone_up():
    """Prices that only rise — no drawdown possible."""
    return pd.Series([0.001] * 252)


@pytest.fixture
def mixed_returns():
    rng = np.random.default_rng(42)
    return pd.Series(rng.normal(0.0003, 0.012, 500))


@pytest.fixture
def crash_series():
    """One big crash followed by recovery."""
    half = 126
    down = pd.Series([-0.01] * half)
    up = pd.Series([0.01] * half)
    return pd.concat([down, up], ignore_index=True)


# ---------------------------------------------------------------------------
# max_drawdown
# ---------------------------------------------------------------------------

class TestMaxDrawdown:
    def test_empty_returns_zero(self):
        assert max_drawdown(pd.Series(dtype=float)) == 0.0

    def test_monotone_up_zero_drawdown(self, monotone_up):
        assert max_drawdown(monotone_up) == pytest.approx(0.0, abs=1e-9)

    def test_single_negative_return(self):
        r = pd.Series([-0.1])
        # cumulative: [1, 0.9]; peak: [1, 1]; drawdown: [0, -0.1]
        assert max_drawdown(r) == pytest.approx(-0.1, rel=1e-9)

    def test_all_losses_deep_drawdown(self):
        r = pd.Series([-0.01] * 100)
        # cumulative after 100 steps of -1%: 0.99^100 ≈ 0.366
        result = max_drawdown(r)
        expected = float(0.99 ** 100 - 1)
        assert abs(result - expected) < 1e-6

    def test_matches_empyrical_formula(self, mixed_returns):
        r = mixed_returns
        cum = np.empty(len(r) + 1)
        cum[0] = 1.0
        np.cumprod(1.0 + np.asarray(r), out=cum[1:])
        peak = np.fmax.accumulate(cum)
        expected = float(np.nanmin((cum - peak) / peak))
        assert abs(max_drawdown(r) - expected) < 1e-10

    def test_returns_non_positive(self, mixed_returns):
        assert max_drawdown(mixed_returns) <= 0.0

    def test_crash_and_recover(self, crash_series):
        mdd = max_drawdown(crash_series)
        # 126 steps of -1%: 0.99^126 ≈ 0.282 → drawdown ≈ -0.718
        assert mdd < -0.5


# ---------------------------------------------------------------------------
# drawdown_series
# ---------------------------------------------------------------------------

class TestDrawdownSeries:
    def test_empty_returns_empty_series(self):
        result = drawdown_series(pd.Series(dtype=float))
        assert result.empty

    def test_same_length_as_input(self, mixed_returns):
        dd = drawdown_series(mixed_returns)
        assert len(dd) == len(mixed_returns)

    def test_all_non_positive(self, mixed_returns):
        dd = drawdown_series(mixed_returns)
        assert (dd <= 1e-12).all()

    def test_minimum_equals_max_drawdown(self, mixed_returns):
        dd = drawdown_series(mixed_returns)
        assert abs(float(dd.min()) - max_drawdown(mixed_returns)) < 1e-10

    def test_monotone_up_all_zero(self, monotone_up):
        dd = drawdown_series(monotone_up)
        assert (dd >= -1e-10).all()

    def test_index_preserved(self, mixed_returns):
        dd = drawdown_series(mixed_returns)
        assert list(dd.index) == list(mixed_returns.index)


# ---------------------------------------------------------------------------
# value_at_risk
# ---------------------------------------------------------------------------

class TestValueAtRisk:
    def test_empty_returns_zero(self):
        assert value_at_risk(pd.Series(dtype=float)) == 0.0

    def test_matches_numpy_percentile(self, mixed_returns):
        r = mixed_returns
        expected = float(np.percentile(r, 5.0))
        assert abs(value_at_risk(r, cutoff=0.05) - expected) < 1e-10

    def test_higher_cutoff_less_extreme(self, mixed_returns):
        var_01 = value_at_risk(mixed_returns, cutoff=0.01)
        var_05 = value_at_risk(mixed_returns, cutoff=0.05)
        assert var_01 <= var_05

    def test_negative_for_mixed_returns(self, mixed_returns):
        assert value_at_risk(mixed_returns, cutoff=0.05) < 0

    def test_constant_positive_returns(self):
        r = pd.Series([0.001] * 100)
        assert value_at_risk(r, cutoff=0.05) > 0


# ---------------------------------------------------------------------------
# expected_shortfall
# ---------------------------------------------------------------------------

class TestExpectedShortfall:
    def test_empty_returns_zero(self):
        assert expected_shortfall(pd.Series(dtype=float)) == 0.0

    def test_es_more_extreme_than_var(self, mixed_returns):
        var = value_at_risk(mixed_returns, cutoff=0.05)
        es = expected_shortfall(mixed_returns, cutoff=0.05)
        assert es <= var

    def test_matches_formula(self, mixed_returns):
        r = mixed_returns
        n = len(r)
        cutoff_idx = int(n * 0.05)
        cutoff_idx = max(cutoff_idx, 1)
        sorted_r = np.sort(np.asarray(r))
        expected = float(sorted_r[:cutoff_idx].mean())
        assert abs(expected_shortfall(r, cutoff=0.05) - expected) < 1e-10

    def test_higher_cutoff_less_extreme_es(self, mixed_returns):
        es_01 = expected_shortfall(mixed_returns, cutoff=0.01)
        es_05 = expected_shortfall(mixed_returns, cutoff=0.05)
        assert es_01 <= es_05


# ---------------------------------------------------------------------------
# tail_ratio
# ---------------------------------------------------------------------------

class TestTailRatio:
    def test_empty_returns_nan(self):
        assert np.isnan(tail_ratio(pd.Series(dtype=float)))

    def test_symmetric_distribution_near_one(self):
        rng = np.random.default_rng(99)
        r = pd.Series(rng.normal(0, 0.01, 10_000))
        result = tail_ratio(r)
        assert 0.8 < result < 1.2

    def test_matches_formula(self, mixed_returns):
        r = mixed_returns
        p95 = np.percentile(r, 95)
        p5 = np.percentile(r, 5)
        expected = abs(p95) / abs(p5) if p5 != 0 else float("nan")
        result = tail_ratio(r)
        assert abs(result - expected) < 1e-10


# ---------------------------------------------------------------------------
# skewness
# ---------------------------------------------------------------------------

class TestSkewness:
    def test_symmetric_near_zero(self):
        rng = np.random.default_rng(7)
        r = pd.Series(rng.normal(0, 1, 10_000))
        assert abs(skewness(r)) < 0.1

    def test_right_skewed_positive(self):
        rng = np.random.default_rng(8)
        r = pd.Series(rng.exponential(1, 1000))
        assert skewness(r) > 0.5

    def test_short_series_zero(self):
        assert skewness(pd.Series([0.1, 0.2])) == 0.0

    def test_matches_scipy(self, mixed_returns):
        from scipy import stats
        expected = float(stats.skew(mixed_returns, bias=True))
        assert abs(skewness(mixed_returns) - expected) < 1e-10


# ---------------------------------------------------------------------------
# excess_kurtosis
# ---------------------------------------------------------------------------

class TestExcessKurtosis:
    def test_normal_distribution_near_zero(self):
        rng = np.random.default_rng(9)
        r = pd.Series(rng.normal(0, 1, 50_000))
        assert abs(excess_kurtosis(r)) < 0.2

    def test_fat_tails_positive_excess_kurtosis(self):
        rng = np.random.default_rng(11)
        r = pd.Series(rng.standard_t(df=3, size=50_000))
        assert excess_kurtosis(r) > 2.0

    def test_short_series_zero(self):
        assert excess_kurtosis(pd.Series([0.1, 0.2, 0.3])) == 0.0

    def test_matches_scipy(self, mixed_returns):
        from scipy import stats
        expected = float(stats.kurtosis(mixed_returns, bias=True, fisher=True))
        assert abs(excess_kurtosis(mixed_returns) - expected) < 1e-10
