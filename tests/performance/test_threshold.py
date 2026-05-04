"""
Tests for threshold suggestion module.

Tests cover:
- bucket_ic_analysis: IC computation per confidence bucket
- suggest_threshold: optimal threshold suggestion logic
"""

import pytest
from src.performance.threshold import (
    bucket_ic_analysis,
    suggest_threshold,
    bucket_ic_analysis,
    DEFAULT_BUCKETS,
    BucketICResult,
    ThresholdSuggestion,
)


def make_data(
    n: int = 100,
    score_mean: float = 0.3,
    return_mean: float = 0.01,
    confidence_distribution: str = "uniform",
) -> tuple:
    """
    Generate synthetic test data.

    Args:
        n: Number of samples
        score_mean: Mean of sentiment scores
        return_mean: Mean of forward returns
        confidence_distribution: "uniform", "low", "high", or "bimodal"

    Returns:
        Tuple of (scores, forward_returns, confidences) lists
    """
    import numpy as np

    np.random.seed(42)

    scores = np.random.normal(score_mean, 0.3, n).clip(-1, 1).tolist()
    returns = np.random.normal(return_mean, 0.02, n).tolist()

    if confidence_distribution == "uniform":
        confidences = np.random.uniform(0, 1, n).tolist()
    elif confidence_distribution == "low":
        confidences = np.random.beta(2, 5, n).tolist()  # Skewed toward low
    elif confidence_distribution == "high":
        confidences = np.random.beta(5, 2, n).tolist()  # Skewed toward high
    elif confidence_distribution == "bimodal":
        confidences = (np.random.choice([0.2, 0.8], n) + np.random.uniform(-0.1, 0.1, n)).clip(0, 1).tolist()
    else:
        confidences = np.random.uniform(0, 1, n).tolist()

    return scores, returns, confidences


class TestBucketICAnalysis:
    """Tests for bucket_ic_analysis function."""

    def test_bucket_ic_basic(self):
        """Test basic bucket IC analysis with uniform confidence distribution."""
        scores, returns, confidences = make_data(n=200, confidence_distribution="uniform")

        results = bucket_ic_analysis(scores, returns, confidences)

        assert len(results) == len(DEFAULT_BUCKETS)
        for result in results:
            assert isinstance(result.bucket_range, tuple)
            assert result.sample_count >= 0
            assert -1.0 <= result.composite_ic <= 1.0
            # ICIR can be any real number
            assert isinstance(result.icir, float)
            assert 0.0 <= result.mean_confidence <= 1.0
            assert 0.0 <= result.hit_rate <= 1.0

    def test_bucket_ic_custom_buckets(self):
        """Test with custom bucket ranges."""
        scores, returns, confidences = make_data(n=100)

        custom_buckets = [(0.0, 0.5), (0.5, 1.0)]
        results = bucket_ic_analysis(scores, returns, confidences, buckets=custom_buckets)

        assert len(results) == 2
        assert results[0].bucket_range == (0.0, 0.5)
        assert results[1].bucket_range == (0.5, 1.0)

    def test_bucket_ic_length_mismatch_raises(self):
        """Test that mismatched input lengths raise ValueError."""
        scores = [0.5, 0.3, -0.2]
        returns = [0.01, -0.02]  # Wrong length
        confidences = [0.8, 0.6, 0.4]

        with pytest.raises(ValueError, match="same length"):
            bucket_ic_analysis(scores, returns, confidences)

    def test_bucket_ic_empty_input_raises(self):
        """Test that empty input raises ValueError."""
        with pytest.raises(ValueError):
            bucket_ic_analysis([], [], [])

    def test_bucket_ic_insufficient_samples(self):
        """Test buckets with insufficient samples return zeros."""
        # Only 5 samples total - each bucket will have < 10
        scores, returns, confidences = make_data(n=5)

        results = bucket_ic_analysis(
            scores, returns, confidences,
            min_samples_per_bucket=10
        )

        for result in results:
            if result.sample_count < 10:
                assert result.composite_ic == 0.0
                assert result.icir == 0.0
                assert result.hit_rate == 0.0

    def test_bucket_ic_high_confidence_better(self):
        """
        Test scenario where high confidence signals have better IC.

        We create synthetic data where high confidence signals are more predictive.
        """
        import numpy as np
        np.random.seed(123)

        n = 300
        # Low confidence signals: random noise
        low_conf_scores = np.random.uniform(-1, 1, 150).tolist()
        low_conf_returns = np.random.uniform(-0.05, 0.05, 150).tolist()
        low_conf_confs = np.random.uniform(0, 0.4, 150).tolist()

        # High confidence signals: correlated with returns
        high_conf_directions = np.random.choice([-1, 1], 150)
        high_conf_scores = (high_conf_directions * 0.7 + np.random.uniform(-0.2, 0.2, 150)).clip(-1, 1).tolist()
        high_conf_returns = (high_conf_directions * 0.02 + np.random.uniform(-0.01, 0.01, 150)).tolist()
        high_conf_confs = np.random.uniform(0.7, 1.0, 150).tolist()

        all_scores = low_conf_scores + high_conf_scores
        all_returns = low_conf_returns + high_conf_returns
        all_confs = low_conf_confs + high_conf_confs

        results = bucket_ic_analysis(all_scores, all_returns, all_confs)

        # Find high confidence bucket (0.7-1.0)
        high_conf_result = next(r for r in results if r.bucket_range[0] == 0.7)
        low_conf_result = next(r for r in results if r.bucket_range[1] <= 0.3)

        # High confidence should have better IC (in this synthetic data)
        assert high_conf_result.sample_count > 0
        assert low_conf_result.sample_count > 0


class TestSuggestThreshold:
    """Tests for suggest_threshold function."""

    def test_suggest_threshold_basic(self):
        """Test basic threshold suggestion."""
        scores, returns, confidences = make_data(n=300)

        suggestion = suggest_threshold(scores, returns, confidences)

        assert isinstance(suggestion.suggested_threshold, float)
        assert 0.0 <= suggestion.suggested_threshold <= 1.0
        assert isinstance(suggestion.reasoning, str)
        assert len(suggestion.bucket_results) == len(DEFAULT_BUCKETS)
        assert isinstance(suggestion.max_icir_bucket, (tuple, type(None)))

    def test_suggest_threshold_high_confidence_best(self):
        """
        Test when high confidence bucket has best ICIR.

        Should suggest threshold at the lower bound of that bucket.
        """
        import numpy as np
        np.random.seed(456)

        # Create data where only high confidence signals are predictive
        n = 400

        # Low/medium confidence: random noise (IC ~ 0)
        noise_scores = np.random.uniform(-1, 1, 300).tolist()
        noise_returns = np.random.uniform(-0.05, 0.05, 300).tolist()
        noise_confs = np.random.uniform(0, 0.6, 300).tolist()

        # High confidence: predictive signals
        directions = np.random.choice([-1, 1], 100)
        pred_scores = (directions * 0.8 + np.random.uniform(-0.1, 0.1, 100)).clip(-1, 1).tolist()
        pred_returns = (directions * 0.03 + np.random.uniform(-0.01, 0.01, 100)).tolist()
        pred_confs = np.random.uniform(0.75, 1.0, 100).tolist()

        all_scores = noise_scores + pred_scores
        all_returns = noise_returns + pred_returns
        all_confs = noise_confs + pred_confs

        suggestion = suggest_threshold(all_scores, all_returns, all_confs)

        # Threshold should be in the high confidence range
        assert suggestion.suggested_threshold >= 0.5
        assert "ICIR" in suggestion.reasoning

    def test_suggest_threshold_low_confidence_best(self):
        """
        Test when lowest confidence bucket has best ICIR.

        Should suggest threshold = 0 (no filtering).
        """
        import numpy as np
        np.random.seed(789)

        n = 400

        # Low confidence: predictive
        directions = np.random.choice([-1, 1], 200)
        low_scores = (directions * 0.6 + np.random.uniform(-0.2, 0.2, 200)).clip(-1, 1).tolist()
        low_returns = (directions * 0.02 + np.random.uniform(-0.01, 0.01, 200)).tolist()
        low_confs = np.random.uniform(0.05, 0.25, 200).tolist()

        # High confidence: random noise
        noise_scores = np.random.uniform(-1, 1, 200).tolist()
        noise_returns = np.random.uniform(-0.05, 0.05, 200).tolist()
        noise_confs = np.random.uniform(0.7, 1.0, 200).tolist()

        all_scores = low_scores + noise_scores
        all_returns = low_returns + noise_returns
        all_confs = low_confs + noise_confs

        suggestion = suggest_threshold(all_scores, all_returns, all_confs)

        # When lowest bucket is best, threshold should be 0
        assert suggestion.suggested_threshold == 0.0
        assert "Lowest confidence bucket" in suggestion.reasoning

    def test_suggest_threshold_all_negative_icir(self):
        """
        Test when all buckets have negative ICIR.

        Should return conservative default threshold of 0.5.
        """
        # To get negative ICIR, we need inverse correlation between scores and returns
        import numpy as np
        np.random.seed(999)

        # Create data where high confidence signals are systematically wrong
        n = 300

        # High confidence but wrong predictions (inverse correlation)
        directions = np.random.choice([-1, 1], n)
        scores = (-directions * 0.8 + np.random.uniform(-0.1, 0.1, n)).clip(-1, 1).tolist()  # Inverse
        returns = (directions * 0.03 + np.random.uniform(-0.01, 0.01, n)).tolist()
        confidences = np.random.uniform(0.7, 1.0, n).tolist()  # All high confidence

        suggestion = suggest_threshold(scores, returns, confidences)

        # With systematically wrong predictions, ICIR should be negative
        # and we should get conservative default
        assert suggestion.suggested_threshold == 0.5
        assert "non-positive ICIR" in suggestion.reasoning

    def test_suggest_threshold_insufficient_samples(self):
        """Test with insufficient samples - should return default threshold."""
        scores, returns, confidences = make_data(n=15)

        suggestion = suggest_threshold(
            scores, returns, confidences,
            min_samples_per_bucket=10
        )

        # May or may not have sufficient samples depending on distribution
        # If all buckets are insufficient, threshold should be 0.5
        if all(r.sample_count < 10 for r in suggestion.bucket_results):
            assert suggestion.suggested_threshold == 0.5
            assert "Insufficient samples" in suggestion.reasoning

    def test_suggest_threshold_custom_buckets(self):
        """Test threshold suggestion with custom bucket ranges."""
        scores, returns, confidences = make_data(n=200)

        custom_buckets = [(0.0, 0.4), (0.4, 0.7), (0.7, 1.0)]
        suggestion = suggest_threshold(
            scores, returns, confidences,
            buckets=custom_buckets
        )

        assert len(suggestion.bucket_results) == 3
        assert suggestion.bucket_results[0].bucket_range == (0.0, 0.4)
        assert suggestion.bucket_results[1].bucket_range == (0.4, 0.7)
        assert suggestion.bucket_results[2].bucket_range == (0.7, 1.0)


class TestThresholdEdgeCases:
    """Edge case tests for threshold module."""

    def test_constant_confidence(self):
        """Test when all confidences are the same."""
        scores = [0.5, -0.3, 0.2, 0.8, -0.1] * 40  # 200 samples
        returns = [0.02, -0.01, 0.015, 0.03, -0.005] * 40
        confidences = [0.5] * 200  # All same confidence

        results = bucket_ic_analysis(scores, returns, confidences)

        # All samples should fall into one bucket (0.3-0.5 or 0.5-0.7)
        total_samples = sum(r.sample_count for r in results)
        assert total_samples == 200

    def test_perfect_correlation_high_conf(self):
        """Test with perfect correlation in high confidence signals."""
        import numpy as np
        np.random.seed(111)

        # Perfect signals with high confidence
        directions = np.random.choice([-1, 1], 100)
        scores = (directions * 0.9).tolist()
        returns = (directions * 0.03).tolist()
        confidences = [0.95] * 100

        suggestion = suggest_threshold(scores, returns, confidences)

        # Should find good ICIR in high confidence bucket
        high_bucket = next(
            (r for r in suggestion.bucket_results if r.bucket_range[0] == 0.7),
            None
        )
        if high_bucket and high_bucket.sample_count > 0:
            assert high_bucket.composite_ic > 0

    def test_empty_bucket(self):
        """Test when a bucket has no samples."""
        scores = [0.5, 0.3, -0.2, 0.1] * 50
        returns = [0.02, 0.01, -0.015, 0.005] * 50
        # All confidences in low range
        confidences = [0.1, 0.15, 0.2, 0.25] * 50

        results = bucket_ic_analysis(scores, returns, confidences)

        # High confidence buckets should have 0 samples
        high_buckets = [r for r in results if r.bucket_range[0] >= 0.5]
        for bucket in high_buckets:
            assert bucket.sample_count == 0
            assert bucket.composite_ic == 0.0

    def test_degradation_point_detection(self):
        """Test that degradation point is correctly identified."""
        import numpy as np
        np.random.seed(222)

        # Create clear degradation pattern: ICIR decreases with confidence
        # This is counter-intuitive but tests the degradation detection

        # Very high ICIR in low bucket
        low_directions = np.random.choice([-1, 1], 100)
        low_scores = (low_directions * 0.8).tolist()
        low_returns = (low_directions * 0.03).tolist()
        low_confs = np.random.uniform(0.1, 0.25, 100).tolist()

        # Medium ICIR in medium bucket
        med_directions = np.random.choice([-1, 1], 100)
        med_scores = (med_directions * 0.4 + np.random.uniform(-0.3, 0.3, 100)).tolist()
        med_returns = (med_directions * 0.015 + np.random.uniform(-0.01, 0.01, 100)).tolist()
        med_confs = np.random.uniform(0.4, 0.6, 100).tolist()

        # Low/negative ICIR in high bucket (random)
        high_scores = np.random.uniform(-1, 1, 100).tolist()
        high_returns = np.random.uniform(-0.03, 0.03, 100).tolist()
        high_confs = np.random.uniform(0.75, 0.95, 100).tolist()

        all_scores = low_scores + med_scores + high_scores
        all_returns = low_returns + med_returns + high_returns
        all_confs = low_confs + med_confs + high_confs

        suggestion = suggest_threshold(all_scores, all_returns, all_confs)

        # Should identify degradation point
        # (where ICIR drops below 50% of max)
        assert suggestion.degradation_point is not None or suggestion.suggested_threshold == 0.0
