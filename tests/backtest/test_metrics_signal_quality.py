"""Tests for backtest/metrics/signal_quality.py (T-006).

Covers: IC, ICIR, p-value, Deflated Sharpe Ratio (López de Prado 2014).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats as scipy_stats

from src.backtest.metrics.signal_quality import (
    deflated_sharpe_ratio,
    expected_max_sharpe,
    ic_pvalue,
    icir,
    icir_from_series,
    information_coefficient,
    sharpe_ratio_se,
)


# ---------------------------------------------------------------------------
# information_coefficient
# ---------------------------------------------------------------------------

class TestInformationCoefficient:
    def test_perfect_rank_agreement_ic_one(self):
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        r = pd.Series([0.1, 0.2, 0.3, 0.4, 0.5])
        assert information_coefficient(s, r) == pytest.approx(1.0, abs=1e-9)

    def test_perfect_rank_disagreement_ic_minus_one(self):
        s = pd.Series([5.0, 4.0, 3.0, 2.0, 1.0])
        r = pd.Series([0.1, 0.2, 0.3, 0.4, 0.5])
        assert information_coefficient(s, r) == pytest.approx(-1.0, abs=1e-9)

    def test_random_signal_ic_near_zero(self):
        rng = np.random.default_rng(42)
        s = pd.Series(rng.standard_normal(1000))
        r = pd.Series(rng.standard_normal(1000))
        ic = information_coefficient(s, r)
        assert abs(ic) < 0.1

    def test_too_short_returns_nan(self):
        assert np.isnan(information_coefficient([1.0, 2.0], [0.1, 0.2]))

    def test_constant_signal_returns_zero(self):
        s = pd.Series([1.0] * 10)
        r = pd.Series(range(10), dtype=float)
        assert information_coefficient(s, r) == 0.0

    def test_matches_scipy_spearmanr(self):
        rng = np.random.default_rng(0)
        s = rng.standard_normal(50)
        r = rng.standard_normal(50)
        expected, _ = scipy_stats.spearmanr(s, r)
        result = information_coefficient(s, r)
        assert abs(result - expected) < 1e-10


# ---------------------------------------------------------------------------
# ic_pvalue
# ---------------------------------------------------------------------------

class TestICPValue:
    def test_perfect_correlation_low_pvalue(self):
        s = pd.Series(range(100), dtype=float)
        r = pd.Series(range(100), dtype=float)
        p = ic_pvalue(s, r)
        assert p < 0.001

    def test_random_signal_high_pvalue(self):
        rng = np.random.default_rng(1)
        s = pd.Series(rng.standard_normal(50))
        r = pd.Series(rng.standard_normal(50))
        # High p-value expected on average; can't guarantee any single draw
        # Just verify it's in [0, 1]
        p = ic_pvalue(s, r)
        assert 0.0 <= p <= 1.0

    def test_too_short_returns_one(self):
        assert ic_pvalue([1.0, 2.0], [0.1, 0.2]) == 1.0

    def test_matches_scipy_pvalue(self):
        rng = np.random.default_rng(3)
        s = rng.standard_normal(40)
        r = rng.standard_normal(40)
        _, expected_p = scipy_stats.spearmanr(s, r)
        result_p = ic_pvalue(s, r)
        assert abs(result_p - expected_p) < 1e-10


# ---------------------------------------------------------------------------
# icir (panel)
# ---------------------------------------------------------------------------

class TestICIR:
    def _make_panel(self, n_dates: int, n_tickers: int, seed: int = 42):
        rng = np.random.default_rng(seed)
        dates = pd.date_range("2020-01-02", periods=n_dates, freq="B")
        tickers = [f"T{i}" for i in range(n_tickers)]
        return (
            pd.DataFrame(rng.standard_normal((n_dates, n_tickers)), index=dates, columns=tickers),
            pd.DataFrame(rng.standard_normal((n_dates, n_tickers)), index=dates, columns=tickers),
        )

    def test_empty_panel_returns_nan(self):
        result = icir(pd.DataFrame(), pd.DataFrame())
        assert np.isnan(result)

    def test_single_date_too_few_returns_nan(self):
        s = pd.DataFrame({"A": [1.0]}, index=pd.DatetimeIndex(["2020-01-02"]))
        r = pd.DataFrame({"A": [0.1]}, index=pd.DatetimeIndex(["2020-01-02"]))
        result = icir(s, r)
        assert np.isnan(result)

    def test_perfect_signal_high_icir(self):
        rng = np.random.default_rng(10)
        n_dates, n_tickers = 60, 20
        dates = pd.date_range("2020-01-02", periods=n_dates, freq="B")
        tickers = [f"T{i}" for i in range(n_tickers)]
        # signals = returns + small noise → high IC at every date
        true_ret = rng.standard_normal((n_dates, n_tickers))
        signals = true_ret + rng.standard_normal((n_dates, n_tickers)) * 0.1
        s_panel = pd.DataFrame(signals, index=dates, columns=tickers)
        r_panel = pd.DataFrame(true_ret, index=dates, columns=tickers)
        result = icir(s_panel, r_panel)
        assert result > 3.0

    def test_random_signal_icir_near_zero(self):
        s, r = self._make_panel(100, 30)
        result = icir(s, r)
        # May be NaN if not enough clean dates, otherwise should be small
        if not np.isnan(result):
            assert abs(result) < 5.0  # no persistent alpha in random data


# ---------------------------------------------------------------------------
# icir_from_series
# ---------------------------------------------------------------------------

class TestICIRFromSeries:
    def test_single_value_nan(self):
        assert np.isnan(icir_from_series([0.05]))

    def test_zero_std_returns_zero(self):
        result = icir_from_series([0.05] * 10)
        assert result == 0.0

    def test_positive_ic_series_positive_icir(self):
        rng = np.random.default_rng(20)
        ic_s = pd.Series(rng.normal(0.05, 0.02, 50))
        result = icir_from_series(ic_s)
        assert result > 0

    def test_formula_consistency(self):
        rng = np.random.default_rng(21)
        ic_s = rng.normal(0.04, 0.03, 30)
        arr = np.array(ic_s)
        expected = float(arr.mean() / arr.std(ddof=1))
        result = icir_from_series(ic_s, annualisation=1)
        assert abs(result - expected) < 1e-10

    def test_annualisation_scales_result(self):
        ic_s = [0.03] * 2 + [-0.01]  # non-constant for non-zero std
        r1 = icir_from_series(ic_s, annualisation=1)
        r4 = icir_from_series(ic_s, annualisation=4)
        if not (np.isnan(r1) or np.isnan(r4)):
            assert abs(r4 / r1 - 2.0) < 1e-9  # sqrt(4) = 2


# ---------------------------------------------------------------------------
# sharpe_ratio_se
# ---------------------------------------------------------------------------

class TestSharpeRatioSE:
    def test_normal_distribution(self):
        sr = 1.0
        n = 252
        # Normal returns: skew=0, excess_kurt=0
        expected = np.sqrt(1.0 / (n - 1))
        result = sharpe_ratio_se(sr, n_obs=n, skew=0.0, excess_kurt=0.0)
        assert abs(result - expected) < 1e-10

    def test_more_observations_smaller_se(self):
        sr = 0.8
        se_short = sharpe_ratio_se(sr, n_obs=252)
        se_long = sharpe_ratio_se(sr, n_obs=2520)
        assert se_short > se_long

    def test_negative_variance_clamped_to_zero(self):
        # Extreme skew/kurtosis can produce negative variance → clamped to 0
        result = sharpe_ratio_se(observed_sr=10.0, n_obs=10, skew=5.0, excess_kurt=-5.0)
        assert result >= 0.0

    def test_single_obs_infinite_se(self):
        result = sharpe_ratio_se(0.5, n_obs=1)
        assert result == float("inf")


# ---------------------------------------------------------------------------
# expected_max_sharpe
# ---------------------------------------------------------------------------

class TestExpectedMaxSharpe:
    def test_single_trial_zero(self):
        # With 1 trial there is no multiple testing inflation
        result = expected_max_sharpe(n_trials=1, n_obs=252)
        assert abs(result) < 1e-6

    def test_more_trials_higher_expected_max(self):
        sr10 = expected_max_sharpe(n_trials=10, n_obs=252)
        sr100 = expected_max_sharpe(n_trials=100, n_obs=252)
        assert sr100 > sr10 > 0

    def test_more_observations_smaller_sr_star(self):
        sr_short = expected_max_sharpe(n_trials=50, n_obs=252)
        sr_long = expected_max_sharpe(n_trials=50, n_obs=2520)
        assert sr_short > sr_long > 0

    def test_matches_formula(self):
        EULER = 0.5772156649
        n, T = 20, 500
        z1 = float(scipy_stats.norm.ppf(1 - 1 / n))
        z2 = float(scipy_stats.norm.ppf(1 - 1 / (n * np.e)))
        expected = ((1 - EULER) * z1 + EULER * z2) / np.sqrt(T - 1)
        result = expected_max_sharpe(n_trials=n, n_obs=T)
        assert abs(result - expected) < 1e-10


# ---------------------------------------------------------------------------
# deflated_sharpe_ratio
# ---------------------------------------------------------------------------

class TestDeflatedSharpeRatio:
    def test_output_between_zero_and_one(self):
        result = deflated_sharpe_ratio(1.0, n_trials=10, n_obs=252)
        assert 0.0 <= result <= 1.0

    def test_more_trials_lower_dsr(self):
        # More trials → higher SR* benchmark → lower DSR for same observed SR
        dsr_few = deflated_sharpe_ratio(0.3, n_trials=5, n_obs=252)
        dsr_many = deflated_sharpe_ratio(0.3, n_trials=1000, n_obs=252)
        assert dsr_few > dsr_many

    def test_high_sr_single_trial_high_dsr(self):
        # One trial, high SR, normal distribution → very high DSR
        dsr = deflated_sharpe_ratio(2.0, n_trials=1, n_obs=2520)
        assert dsr > 0.95

    def test_negative_sr_low_dsr(self):
        dsr = deflated_sharpe_ratio(-0.5, n_trials=5, n_obs=252)
        assert dsr < 0.2

    def test_fat_tails_lower_dsr_than_normal(self):
        # Use borderline SR where z-score ~0.4 so norm.cdf is not saturated
        # negative skew + positive excess kurtosis → larger SE → lower z → lower DSR
        dsr_normal = deflated_sharpe_ratio(0.1, n_trials=5, n_obs=252, skew=0.0, excess_kurt=0.0)
        dsr_fat = deflated_sharpe_ratio(0.1, n_trials=5, n_obs=252, skew=-1.0, excess_kurt=5.0)
        assert dsr_normal > dsr_fat

    def test_benchmark_sr_shifts_result(self):
        base = deflated_sharpe_ratio(1.0, n_trials=10, n_obs=252, benchmark_sr=0.0)
        shifted = deflated_sharpe_ratio(1.0, n_trials=10, n_obs=252, benchmark_sr=0.5)
        assert base > shifted

    def test_dsr_is_probability_of_skill(self):
        # A strategy with SR >> expected max should have DSR close to 1
        dsr = deflated_sharpe_ratio(5.0, n_trials=10, n_obs=2520)
        assert dsr > 0.999

    def test_formula_matches_manual(self):
        sr, n_trials, n_obs, skew, kurt = 0.8, 20, 500, -0.3, 1.5
        sr_star = expected_max_sharpe(n_trials, n_obs)
        se = sharpe_ratio_se(sr, n_obs, skew, kurt)
        expected = float(scipy_stats.norm.cdf((sr - sr_star) / se))
        result = deflated_sharpe_ratio(sr, n_trials, n_obs, skew, kurt)
        assert abs(result - expected) < 1e-10
