"""Tests for ensemble weight computation with LOO ICIR."""

import pytest
import numpy as np
from src.performance.weights import (
    compute_purified_icir,
    compute_new_weights,
    _compute_rolling_ic,
)


class TestComputeRollingIc:
    """Tests for the rolling IC helper function."""

    def test_rolling_ic_perfect_correlation(self):
        """Perfect positive correlation should yield IC ≈ 1.0."""
        scores = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        returns = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        ic_series = _compute_rolling_ic(scores, returns, window_size=5, step_size=1)
        assert len(ic_series) == 6  # (10 - 5 + 1) / 1 = 6 windows
        for ic in ic_series:
            assert ic > 0.9  # Near perfect correlation

    def test_rolling_ic_perfect_negative_correlation(self):
        """Perfect negative correlation should yield IC ≈ -1.0."""
        scores = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        returns = [1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1]
        ic_series = _compute_rolling_ic(scores, returns, window_size=5, step_size=1)
        for ic in ic_series:
            assert ic < -0.9  # Near perfect negative correlation

    def test_rolling_ic_no_correlation(self):
        """Random data should yield IC near 0."""
        np.random.seed(42)
        scores = np.random.randn(100).tolist()
        returns = np.random.randn(100).tolist()
        ic_series = _compute_rolling_ic(scores, returns, window_size=30, step_size=5)
        # IC should be small (no correlation)
        for ic in ic_series:
            assert abs(ic) < 0.5

    def test_rolling_ic_insufficient_samples(self):
        """Should return empty list if not enough samples for one window."""
        scores = [1, 2, 3]
        returns = [0.1, 0.2, 0.3]
        ic_series = _compute_rolling_ic(scores, returns, window_size=5, step_size=1)
        assert ic_series == []


class TestComputePurifiedIcir:
    """Tests for per-model ICIR computation used in weight rebalancing."""

    @pytest.fixture
    def sample_data(self):
        """Generate sample data with known correlation structure."""
        np.random.seed(42)
        n = 200

        # Model A: strong positive correlation with returns
        model_a = np.random.randn(n) * 0.5
        # Model B: moderate correlation
        model_b = np.random.randn(n) * 0.3
        # Model C: weak correlation
        model_c = np.random.randn(n) * 0.1

        # Each model's returns: partially driven by its own signal
        returns_a = 0.8 * model_a + np.random.randn(n) * 0.2
        returns_b = 0.5 * model_b + np.random.randn(n) * 0.3
        returns_c = 0.2 * model_c + np.random.randn(n) * 0.4

        model_signals = {
            "model_a": model_a.tolist(),
            "model_b": model_b.tolist(),
            "model_c": model_c.tolist(),
        }
        model_returns = {
            "model_a": returns_a.tolist(),
            "model_b": returns_b.tolist(),
            "model_c": returns_c.tolist(),
        }
        return model_signals, model_returns

    def test_purified_icir_returns_dict(self, sample_data):
        """Should return a dictionary with ICIR for each model."""
        model_signals, model_returns = sample_data
        current_weights = {"model_a": 0.4, "model_b": 0.35, "model_c": 0.25}

        result = compute_purified_icir(model_signals, model_returns, current_weights)

        assert isinstance(result, dict)
        assert set(result.keys()) == {"model_a", "model_b", "model_c"}
        for icir in result.values():
            assert isinstance(icir, float)

    def test_purified_icir_empty_input(self):
        """Should return empty dict for empty input."""
        assert compute_purified_icir({}, {}, {}) == {}

    def test_purified_icir_single_model(self):
        """Should handle single model."""
        np.random.seed(42)
        signals = np.random.randn(100).tolist()
        returns = (0.5 * np.array(signals) + np.random.randn(100) * 0.3).tolist()

        result = compute_purified_icir(
            {"single": signals}, {"single": returns}, {"single": 1.0}
        )

        assert "single" in result
        assert isinstance(result["single"], float)

    def test_purified_icir_better_model_has_higher_icir(self, sample_data):
        """Stronger model (higher signal/return correlation) gets higher ICIR.

        Higher ICIR → higher weight via compute_new_weights, which is correct.
        """
        model_signals, model_returns = sample_data
        current_weights = {"model_a": 0.4, "model_b": 0.35, "model_c": 0.25}

        result = compute_purified_icir(model_signals, model_returns, current_weights)

        # model_a has strongest signal/return correlation → highest ICIR
        # model_c has weakest correlation → lowest ICIR
        assert result["model_a"] > result["model_c"]


class TestComputeNewWeights:
    """Tests for weight computation with smoothing and guardrails."""

    def test_compute_new_weights_basic(self):
        """Should compute new weights from ICIR values."""
        purified_icir = {"opus": 0.8, "qwen35": 0.6, "deepseek": 0.4}
        current_weights = {"opus": 0.34, "qwen35": 0.33, "deepseek": 0.33}

        result = compute_new_weights(purified_icir, current_weights)

        assert isinstance(result, dict)
        assert sum(result.values()) == pytest.approx(1.0)
        # Higher ICIR should get higher weight
        assert result["opus"] > result["qwen35"] > result["deepseek"]

    def test_compute_new_weights_empty_icir(self):
        """Should return copy of current weights when ICIR is empty."""
        result = compute_new_weights({}, {"opus": 0.5, "qwen35": 0.5})
        assert result == {"opus": 0.5, "qwen35": 0.5}

    def test_compute_new_weights_all_negative_icir(self):
        """Should keep current weights when all ICIR are negative."""
        purified_icir = {"opus": -0.5, "qwen35": -0.3}
        current_weights = {"opus": 0.5, "qwen35": 0.5}

        result = compute_new_weights(purified_icir, current_weights)

        assert result == current_weights

    def test_compute_new_weights_floor(self):
        """No weight should go below floor (10%)."""
        # Deepseek has very low ICIR
        purified_icir = {"opus": 1.0, "qwen35": 0.9, "deepseek": 0.01}
        current_weights = {"opus": 0.34, "qwen35": 0.33, "deepseek": 0.33}

        result = compute_new_weights(purified_icir, current_weights, floor=0.10)

        for weight in result.values():
            assert weight >= 0.10 - 1e-6  # Small epsilon for floating point

    def test_compute_new_weights_cap(self):
        """No weight should exceed cap (70%)."""
        # Opus has much higher ICIR
        purified_icir = {"opus": 2.0, "qwen35": 0.3, "deepseek": 0.2}
        current_weights = {"opus": 0.34, "qwen35": 0.33, "deepseek": 0.33}

        result = compute_new_weights(purified_icir, current_weights, cap=0.70)

        for weight in result.values():
            assert weight <= 0.70 + 1e-6

    def test_compute_new_weights_max_delta(self):
        """
        Weights should not change more than max_delta (approximately).

        Note: After final normalization to ensure sum=1.0, max_delta may be
        slightly violated (< 1% relative). This test checks the delta is
        approximately respected.
        """
        purified_icir = {"opus": 2.0, "qwen35": 0.1, "deepseek": 0.1}
        current_weights = {"opus": 0.34, "qwen35": 0.33, "deepseek": 0.33}

        result = compute_new_weights(purified_icir, current_weights, max_delta=0.10)

        # Opus cannot jump from 0.34 to > 0.44 + small epsilon for normalization
        # The max_delta is applied before final normalization, so we allow ~2% slack
        assert result["opus"] <= 0.44 + 0.02  # 0.10 delta + normalization slack
        # But it should still be significantly constrained vs unconstrained
        assert result["opus"] < 0.60  # Would be ~0.65 without max_delta

    def test_compute_new_weights_smoothing(self):
        """Should apply smoothing: 75% old + 25% new."""
        purified_icir = {"opus": 1.0, "qwen35": 0.0}  # qwen35 gets 0 target weight
        current_weights = {"opus": 0.5, "qwen35": 0.5}

        result = compute_new_weights(purified_icir, current_weights, alpha=0.25)

        # Opus should increase but not to 1.0 (smoothing prevents drastic change)
        assert 0.5 < result["opus"] < 1.0
        assert 0.0 < result["qwen35"] < 0.5

    def test_compute_new_weights_sums_to_one(self):
        """Output weights must sum to 1.0."""
        purified_icir = {"a": 0.5, "b": 0.3, "c": 0.2, "d": 0.1}
        current_weights = {"a": 0.25, "b": 0.25, "c": 0.25, "d": 0.25}

        result = compute_new_weights(purified_icir, current_weights)

        assert sum(result.values()) == pytest.approx(1.0)

    def test_compute_new_weights_preserves_keys(self):
        """Output should have same keys as input."""
        purified_icir = {"model_x": 0.5, "model_y": 0.5}
        current_weights = {"model_x": 0.6, "model_y": 0.4}

        result = compute_new_weights(purified_icir, current_weights)

        assert set(result.keys()) == {"model_x", "model_y"}


class TestIntegration:
    """Integration tests for the full weight update pipeline."""

    def test_full_pipeline(self):
        """Test complete per-model ICIR → new weights pipeline."""
        np.random.seed(42)
        n = 300

        # Simulate three models with different predictive power
        model_a = np.random.randn(n)  # Strong
        model_b = np.random.randn(n)  # Medium
        model_c = np.random.randn(n)  # Weak

        # Each model's returns: proportional to its signal strength
        returns_a = 0.8 * model_a + np.random.randn(n) * 0.2
        returns_b = 0.5 * model_b + np.random.randn(n) * 0.3
        returns_c = 0.2 * model_c + np.random.randn(n) * 0.5

        model_signals = {
            "strong": model_a.tolist(),
            "medium": model_b.tolist(),
            "weak": model_c.tolist(),
        }
        model_returns = {
            "strong": returns_a.tolist(),
            "medium": returns_b.tolist(),
            "weak": returns_c.tolist(),
        }

        current_weights = {"strong": 0.34, "medium": 0.33, "weak": 0.33}

        # Step 1: Compute per-model ICIR
        icir = compute_purified_icir(model_signals, model_returns, current_weights)

        # Strong model has highest IC with its own returns → highest ICIR
        assert icir["strong"] > icir["weak"]

        # Step 2: Compute new weights — higher ICIR → higher weight (correct)
        new_weights = compute_new_weights(icir, current_weights)

        assert new_weights["strong"] >= new_weights["weak"]

        # Weights must sum to 1
        assert sum(new_weights.values()) == pytest.approx(1.0)

        # Guardrails must be respected
        for w in new_weights.values():
            assert 0.10 - 1e-6 <= w <= 0.70 + 1e-6
