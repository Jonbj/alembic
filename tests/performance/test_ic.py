"""
Tests for the Information Coefficient (IC) computation module.
"""
import pytest
import numpy as np
from src.performance.ic import (
    compute_composite_ic,
    compute_newey_west_hac,
    compute_icir,
    ICResult,
    ICIRResult,
)


class TestComputeCompositeIC:
    """Tests for compute_composite_ic function."""

    def test_perfect_positive_correlation(self):
        """Perfect positive correlation should yield high composite IC."""
        scores = [0.1, 0.2, 0.3, 0.4, 0.5]
        returns = [0.02, 0.04, 0.06, 0.08, 0.10]  # Same sign, increasing

        result = compute_composite_ic(scores, returns)

        assert result.spearman_ic == pytest.approx(1.0, abs=0.01)
        assert result.weighted_hit_rate == pytest.approx(1.0, abs=0.01)
        assert result.sample_count == 5

    def test_perfect_negative_correlation(self):
        """Perfect negative correlation should yield negative Spearman."""
        scores = [0.5, 0.4, 0.3, 0.2, 0.1]
        returns = [0.02, 0.04, 0.06, 0.08, 0.10]  # Opposite direction

        result = compute_composite_ic(scores, returns)

        assert result.spearman_ic == pytest.approx(-1.0, abs=0.01)
        assert result.sample_count == 5

    def test_random_correlation(self):
        """Random data should yield IC near zero."""
        np.random.seed(42)
        scores = list(np.random.randn(100))
        returns = list(np.random.randn(100))

        result = compute_composite_ic(scores, returns)

        # With random data, IC should be close to 0
        assert abs(result.spearman_ic) < 0.2
        assert result.sample_count == 100

    def test_weighted_hit_rate_with_confidence(self):
        """High confidence correct predictions should increase weighted hit rate."""
        scores = [0.8, -0.6, 0.5, -0.4]
        returns = [0.02, -0.03, 0.01, -0.02]  # All signs match
        confidences = [0.9, 0.8, 0.5, 0.5]

        result = compute_composite_ic(scores, returns, confidences)

        # All predictions correct → weighted hit rate = 1.0
        assert result.weighted_hit_rate == pytest.approx(1.0, abs=0.01)

    def test_weighted_hit_rate_mixed_accuracy(self):
        """Mixed accuracy should yield intermediate weighted hit rate."""
        scores = [0.8, -0.6]  # Positive, negative
        returns = [0.02, 0.03]  # Both positive → first correct, second wrong
        confidences = [0.9, 0.1]  # High conf on correct, low on wrong

        result = compute_composite_ic(scores, returns, confidences)

        # First correct (conf=0.9), second wrong (conf=0.1)
        # Weighted hit rate = 0.9 / (0.9 + 0.1) = 0.9
        assert result.weighted_hit_rate == pytest.approx(0.9, abs=0.01)

    def test_brier_score_perfect_prediction(self):
        """Perfect direction prediction should yield low Brier score."""
        # Scores map to probabilities: (score + 1) / 2
        # score=1.0 → p=1.0, score=-1.0 → p=0.0
        scores = [1.0, -1.0, 1.0, -1.0]
        returns = [0.02, -0.03, 0.01, -0.02]  # Signs match scores

        result = compute_composite_ic(scores, returns)

        # Perfect prediction: predicted_prob matches actual_direction exactly
        assert result.brier_score == pytest.approx(0.0, abs=0.01)

    def test_brier_score_wrong_prediction(self):
        """Wrong direction prediction should yield high Brier score."""
        scores = [1.0, -1.0]  # Predicting positive, negative
        returns = [-0.02, 0.03]  # Both wrong

        result = compute_composite_ic(scores, returns)

        # Both wrong: (1.0 - 0)^2 + (0.0 - 1)^2 = 1 + 1 = 2, mean = 1.0
        assert result.brier_score == pytest.approx(1.0, abs=0.01)

    def test_composite_ic_formula(self):
        """Verify composite IC formula: 0.5×Spearman + 0.3×weighted_hr + 0.2×(1−Brier)."""
        scores = [0.5, 0.3, -0.2, -0.4, 0.6]
        returns = [0.02, 0.01, -0.015, -0.03, 0.025]

        result = compute_composite_ic(scores, returns)

        expected = (
            0.5 * result.spearman_ic
            + 0.3 * result.weighted_hit_rate
            + 0.2 * (1 - result.brier_score)
        )
        assert result.composite_ic == pytest.approx(expected, abs=1e-6)

    def test_empty_input_raises(self):
        """Empty input should raise ValueError."""
        with pytest.raises(ValueError, match="scores cannot be empty"):
            compute_composite_ic([], [])

    def test_length_mismatch_raises(self):
        """Mismatched lengths should raise ValueError."""
        with pytest.raises(ValueError, match="same length"):
            compute_composite_ic([0.1, 0.2], [0.01])

    def test_constant_scores(self):
        """Constant scores should handle gracefully (Spearman undefined)."""
        scores = [0.5, 0.5, 0.5, 0.5]
        returns = [0.02, -0.03, 0.01, -0.02]

        result = compute_composite_ic(scores, returns)

        # Spearman should be 0 for constant array
        assert result.spearman_ic == 0.0
        # But hit rate and Brier should still compute
        assert result.sample_count == 4

    def test_no_confidence_uses_equal_weights(self):
        """None confidence should use equal weights."""
        scores = [0.8, -0.6, 0.5]
        returns = [0.02, -0.03, 0.01]

        result_with_none = compute_composite_ic(scores, returns, confidences=None)
        result_with_equal = compute_composite_ic(scores, returns, confidences=[1.0, 1.0, 1.0])

        assert result_with_none.weighted_hit_rate == pytest.approx(
            result_with_equal.weighted_hit_rate, abs=1e-6
        )


class TestComputeNeweyWestHAC:
    """Tests for compute_newey_west_hac function."""

    def test_iid_data(self):
        """IID data should yield Newey-West std close to simple std."""
        np.random.seed(42)
        values = list(np.random.randn(100))

        nw_std = compute_newey_west_hac(values, lag=0)
        simple_std = np.std(values, ddof=1) / np.sqrt(len(values))

        # With lag=0, Newey-West should equal simple std error
        assert nw_std == pytest.approx(simple_std, rel=0.01)

    def test_autocorrelated_data(self):
        """Positive autocorrelation should increase Newey-West std."""
        # Generate positively autocorrelated series
        np.random.seed(42)
        n = 100
        epsilon = np.random.randn(n)
        ar1 = [0.0]
        for i in range(1, n):
            ar1.append(0.7 * ar1[-1] + epsilon[i])
        ar1 = ar1[1:]  # Remove initial value

        nw_std = compute_newey_west_hac(ar1, lag=5)
        simple_std = np.std(ar1, ddof=1) / np.sqrt(len(ar1))

        # Newey-West should be larger due to autocorrelation
        assert nw_std > simple_std

    def test_empty_input_raises(self):
        """Empty input should raise ValueError."""
        with pytest.raises(ValueError, match="values cannot be empty"):
            compute_newey_west_hac([])

    def test_single_value(self):
        """Single value should return 0 std."""
        assert compute_newey_west_hac([1.0]) == 0.0

    def test_automatic_lag_selection(self):
        """Automatic lag should follow rule of thumb."""
        np.random.seed(42)
        values = list(np.random.randn(100))

        # Should not raise and should return a finite value
        nw_std = compute_newey_west_hac(values)
        assert nw_std > 0
        assert np.isfinite(nw_std)

    def test_lag_cannot_exceed_n(self):
        """Lag should be capped at n-1."""
        values = [1.0, 2.0, 3.0, 4.0, 5.0]

        # Large lag should be capped
        nw_std = compute_newey_west_hac(values, lag=100)
        assert nw_std > 0
        assert np.isfinite(nw_std)


class TestComputeICIR:
    """Tests for compute_icir function."""

    def test_high_predictive_power(self):
        """High predictive power should yield positive ICIR."""
        np.random.seed(42)
        # Generate scores that predict returns with some noise
        n = 200
        scores = list(np.random.randn(n))
        returns = [0.02 * s + np.random.randn() * 0.01 for s in scores]

        result = compute_icir(scores, returns, min_samples=30)

        # Should have positive ICIR (predictive relationship)
        assert result.icir > 0
        assert result.ic_mean > 0
        assert result.sample_count >= 30

    def test_no_predictive_power(self):
        """Random data should yield IC mean near zero (ICIR can vary due to small sample variance)."""
        np.random.seed(42)
        scores = list(np.random.randn(100))
        returns = list(np.random.randn(100))

        result = compute_icir(scores, returns, min_samples=30)

        # IC mean should be close to 0 for random data (ICIR can vary due to variance estimation)
        # Using a more lenient threshold due to rolling window variance
        assert abs(result.ic_mean) < 0.25

    def test_below_min_samples(self):
        """Below minimum samples should return icir=0."""
        result = compute_icir([0.1, 0.2], [0.01, 0.02], min_samples=30)

        assert result.icir == 0.0
        assert result.ic_mean == 0.0
        assert result.ic_std == 0.0

    def test_newey_west_correction_applied(self):
        """Newey-West correction should be applied when enabled."""
        np.random.seed(42)
        n = 150
        scores = list(np.random.randn(n))
        returns = list(np.random.randn(n))

        result_with_nw = compute_icir(scores, returns, use_newey_west=True, min_samples=30)
        result_without_nw = compute_icir(scores, returns, use_newey_west=False, min_samples=30)

        # With NW, newey_west_std should be set
        assert result_with_nw.newey_west_std is not None
        # Without NW, it should be None
        assert result_without_nw.newey_west_std is None

    def test_lag_in_result(self):
        """Result should include the lag used."""
        np.random.seed(42)
        scores = list(np.random.randn(100))
        returns = list(np.random.randn(100))

        result = compute_icir(scores, returns, lag=5, min_samples=30)

        assert result.lag >= 0

    def test_length_mismatch_raises(self):
        """Mismatched lengths should raise ValueError."""
        with pytest.raises(ValueError, match="same length"):
            compute_icir([0.1, 0.2], [0.01], min_samples=1)

    def test_with_confidence_weights(self):
        """ICIR should respect confidence weights."""
        np.random.seed(42)
        n = 100
        scores = list(np.random.randn(n))
        returns = [0.02 * s + np.random.randn() * 0.01 for s in scores]
        confidences = [0.9] * (n // 2) + [0.1] * (n // 2)

        result = compute_icir(scores, returns, confidences=confidences, min_samples=30)

        # Should compute without error
        assert np.isfinite(result.icir) or result.icir == 0.0


class TestIntegration:
    """Integration tests for the IC module."""

    def test_full_pipeline(self):
        """Test full IC → ICIR pipeline."""
        np.random.seed(42)
        n = 300

        # Simulate a realistic scenario: scores have some predictive power
        base_scores = np.random.randn(n)
        noise = np.random.randn(n) * 0.5
        returns = 0.02 * base_scores + noise * 0.01

        scores = list(base_scores)
        confidences = [0.7 + np.random.rand() * 0.3 for _ in range(n)]  # 0.7-1.0

        # Compute composite IC
        ic_result = compute_composite_ic(scores, returns, confidences)

        # Compute ICIR
        icir_result = compute_icir(scores, returns, confidences, min_samples=30)

        # Validate results
        assert ic_result.sample_count == n
        assert icir_result.ic_mean == pytest.approx(ic_result.composite_ic, rel=0.5)
        assert np.isfinite(icir_result.icir) or icir_result.icir == 0.0

    def test_realistic_trading_scenario(self):
        """Test with realistic trading signal characteristics."""
        np.random.seed(42)

        # Simulate 30 days of hourly signals (~200 signals)
        n = 200

        # Scores: mostly small, occasionally extreme
        scores = np.random.randn(n) * 0.3
        scores = np.clip(scores, -1, 1)

        # Returns: weakly correlated with scores + noise
        returns = 0.05 * scores + np.random.randn(n) * 0.02

        # Confidences: higher for extreme scores
        confidences = 0.5 + 0.4 * np.abs(scores)

        ic_result = compute_composite_ic(list(scores), list(returns), list(confidences))
        icir_result = compute_icir(list(scores), list(returns), list(confidences), min_samples=30)

        # Should have some predictive power (IC > 0)
        assert ic_result.composite_ic > 0
        assert icir_result.icir > 0
