"""Tests for pure backtest functions."""
import numpy as np
import pytest

from src.analysis.backtest import ABResult, compute_sharpe, compute_signal_returns, run_ab_comparison


class TestComputeSharpe:
    def test_positive_mean_returns_positive_sharpe(self):
        returns = [0.001, 0.002, -0.001, 0.003, 0.001] * 50
        assert compute_sharpe(returns) > 0

    def test_zero_std_returns_zero(self):
        # Identical values → std=0 → no division, returns 0
        assert compute_sharpe([0.005] * 50) == 0.0

    def test_empty_returns_zero(self):
        assert compute_sharpe([]) == 0.0

    def test_single_element_returns_zero(self):
        assert compute_sharpe([0.01]) == 0.0

    def test_annualization_factor(self):
        returns = [0.001, -0.002, 0.003, -0.001, 0.002] * 20
        s252 = compute_sharpe(returns, annualization=252)
        s1 = compute_sharpe(returns, annualization=1)
        # s252 / s1 should equal sqrt(252)
        assert abs(s252 / s1 - 252 ** 0.5) < 1e-9


class TestComputeSignalReturns:
    def test_positive_score_goes_long(self):
        assert compute_signal_returns([0.5], [0.02]) == [0.02]

    def test_negative_score_goes_short(self):
        assert compute_signal_returns([-0.5], [0.02]) == [-0.02]

    def test_zero_score_neutral(self):
        assert compute_signal_returns([0.0], [0.02]) == [0.0]

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError, match="same length"):
            compute_signal_returns([0.5, 0.3], [0.02])

    def test_multiple_days(self):
        scores = [0.5, -0.3, 0.0, 0.1]
        fwd = [0.01, 0.02, -0.01, -0.03]
        assert compute_signal_returns(scores, fwd) == [0.01, -0.02, 0.0, -0.03]


class TestRunABComparison:
    def test_gate_passes_with_perfect_predictor(self):
        rng = np.random.default_rng(0)
        fwd = rng.normal(0, 0.01, 252).tolist()
        # Perfect predictor: score has same sign as forward return
        scores = [abs(f) if f > 0 else -abs(f) for f in fwd]
        result = run_ab_comparison(scores, fwd, n_articles=500, threshold=0.1)
        assert result.gate_passed

    def test_gate_fails_with_zero_scores(self):
        # All-zero scores → no GDELT edge → GDELT Sharpe = 0
        fwd = [0.001] * 252
        scores = [0.0] * 252
        result = run_ab_comparison(scores, fwd, n_articles=0, threshold=0.1)
        assert not result.gate_passed
        assert result.sharpe_gdelt == 0.0

    def test_result_fields_populated(self):
        fwd = [0.01, -0.02, 0.005, 0.015]
        scores = [0.5, -0.3, 0.0, 0.8]
        result = run_ab_comparison(scores, fwd, n_articles=10, threshold=0.1)
        assert isinstance(result, ABResult)
        assert result.n_signals == 10
        assert result.n_trading_days == 4
        assert result.coverage_pct == 75.0   # 3/4 non-zero
        assert isinstance(result.delta_sharpe, float)
        assert isinstance(result.composite_ic, float)

    def test_coverage_pct_all_zeros(self):
        result = run_ab_comparison([0.0] * 10, [0.01] * 10, n_articles=0)
        assert result.coverage_pct == 0.0
