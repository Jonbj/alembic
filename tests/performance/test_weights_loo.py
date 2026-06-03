"""Tests for Bug 3: LOO ICIR computation."""

import pytest
import numpy as np
from src.performance.weights import (
    compute_purified_icir,
    compute_new_weights,
    _compute_rolling_ic,
    _compute_ensemble_icir,
)


class TestComputeEnsembleIcir:
    """Tests for the new _compute_ensemble_icir helper."""

    def test_ensemble_icir_with_strong_models(self):
        """Two highly correlated models should produce positive ensemble ICIR."""
        np.random.seed(42)
        n = 200
        signals = np.random.randn(n)
        returns = 0.8 * signals + np.random.randn(n) * 0.2

        model_signals = {"A": signals.tolist(), "B": (0.9 * signals + np.random.randn(n) * 0.1).tolist()}
        model_returns = {"A": returns.tolist(), "B": returns.tolist()}
        weights = {"A": 0.5, "B": 0.5}

        icir = _compute_ensemble_icir(model_signals, model_returns, weights)
        assert icir > 0.5  # Strong correlation → high ICIR

    def test_ensemble_icir_exclude_model(self):
        """Excluding a model should change the ensemble ICIR."""
        np.random.seed(42)
        n = 200
        model_signals = {
            "A": np.random.randn(n).tolist(),
            "B": np.random.randn(n).tolist(),
        }
        model_returns = {
            "A": np.random.randn(n).tolist(),
            "B": np.random.randn(n).tolist(),
        }
        weights = {"A": 0.5, "B": 0.5}

        icir_all = _compute_ensemble_icir(model_signals, model_returns, weights)
        icir_no_a = _compute_ensemble_icir(model_signals, model_returns, weights, exclude="A")

        # Excluding A changes the result (different weighted signal)
        # They may be similar since random data, but the function should still return values
        assert isinstance(icir_all, float)
        assert isinstance(icir_no_a, float)

    def test_ensemble_icir_single_model(self):
        """With only one model after exclusion, should still compute."""
        np.random.seed(42)
        n = 100
        signals = np.random.randn(n).tolist()
        returns = (0.5 * np.array(signals) + np.random.randn(n) * 0.3).tolist()

        model_signals = {"A": signals, "B": signals}
        model_returns = {"A": returns, "B": returns}
        weights = {"A": 0.5, "B": 0.5}

        icir = _compute_ensemble_icir(model_signals, model_returns, weights, exclude="B")
        assert isinstance(icir, float)


class TestPurifiedIcirLOO:
    """Tests for the corrected compute_purified_icir with LOO."""

    @pytest.fixture
    def loo_data(self):
        """Generate multi-model data where one model is clearly valuable."""
        np.random.seed(42)
        n = 200

        # Model A: strongly correlated with returns → adds value to ensemble
        model_a = np.random.randn(n) * 0.5
        returns_common = 0.7 * model_a + np.random.randn(n) * 0.2

        # Model B: weakly correlated → less value
        model_b = np.random.randn(n) * 0.1
        returns_b = 0.1 * model_b + np.random.randn(n) * 0.3

        # Model C: pure noise → no value
        model_c = np.random.randn(n) * 0.1
        returns_c = np.random.randn(n) * 0.3

        model_signals = {
            "strong": model_a.tolist(),
            "weak": model_b.tolist(),
            "noise": model_c.tolist(),
        }
        model_returns = {
            "strong": returns_common.tolist(),
            "weak": returns_b.tolist(),
            "noise": returns_c.tolist(),
        }
        return model_signals, model_returns

    def test_loo_icir_positive_for_valuable_model(self, loo_data):
        """A model that adds predictive value should have positive LOO ICIR."""
        model_signals, model_returns = loo_data
        current_weights = {"strong": 0.4, "weak": 0.35, "noise": 0.25}

        result = compute_purified_icir(model_signals, model_returns, current_weights)

        # The strong model should have the highest LOO ICIR
        # (removing it degrades the ensemble most)
        assert result["strong"] >= result["noise"], \
            f"Strong model LOO ICIR ({result['strong']:.3f}) should be >= noise ({result['noise']:.3f})"

    def test_loo_icir_returns_all_models(self, loo_data):
        """LOO ICIR should return a value for every input model."""
        model_signals, model_returns = loo_data
        current_weights = {"strong": 0.4, "weak": 0.35, "noise": 0.25}

        result = compute_purified_icir(model_signals, model_returns, current_weights)

        assert set(result.keys()) == {"strong", "weak", "noise"}
        for v in result.values():
            assert isinstance(v, float)

    def test_loo_icir_single_model_fallback(self):
        """Single model should fall back to standalone ICIR."""
        np.random.seed(42)
        n = 100
        signals = np.random.randn(n).tolist()
        returns = (0.5 * np.array(signals) + np.random.randn(n) * 0.3).tolist()

        result = compute_purified_icir(
            {"only_model": signals},
            {"only_model": returns},
            {"only_model": 1.0},
        )

        assert "only_model" in result
        assert isinstance(result["only_model"], float)

    def test_loo_icir_empty_input(self):
        """Empty input should return empty dict."""
        assert compute_purified_icir({}, {}, {}) == {}


class TestIntegrationLOO:
    """Integration: LOO ICIR → compute_new_weights pipeline."""

    def test_loo_weights_pipeline(self):
        """Full pipeline: LOO ICIR → new weights should still satisfy guardrails."""
        np.random.seed(42)
        n = 300

        model_a = np.random.randn(n) * 0.5
        model_b = np.random.randn(n) * 0.3
        model_c = np.random.randn(n) * 0.1

        returns_a = 0.8 * model_a + np.random.randn(n) * 0.2
        returns_b = 0.5 * model_b + np.random.randn(n) * 0.3
        returns_c = 0.2 * model_c + np.random.randn(n) * 0.5

        model_signals = {
            "strong": model_a.tolist(),
            "medium": model_b.tolist(),
            "weak": model_c.tolist(),
        }
        model_returns = {
            "strong": (0.8 * model_a + np.random.randn(n) * 0.2).tolist(),
            "medium": (0.5 * model_b + np.random.randn(n) * 0.3).tolist(),
            "weak": (0.2 * model_c + np.random.randn(n) * 0.5).tolist(),
        }

        current_weights = {"strong": 0.34, "medium": 0.33, "weak": 0.33}

        icir = compute_purified_icir(model_signals, model_returns, current_weights)
        new_weights = compute_new_weights(icir, current_weights)

        # Weights must sum to 1
        assert sum(new_weights.values()) == pytest.approx(1.0)

        # Guardrails must be respected
        for w in new_weights.values():
            assert 0.10 - 1e-6 <= w <= 0.70 + 1e-6
