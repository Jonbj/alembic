"""Tests for ensemble aggregation."""

import pytest

from src.llm.ensemble import EnsembleAggregator, ModelOutput


class TestEnsembleAggregator:
    """Test ensemble aggregation logic."""

    def test_aggregate_single_model(self):
        """Test aggregation with single model."""
        aggregator = EnsembleAggregator(min_confidence=0.4, divergence_threshold=0.30)
        outputs = [
            ModelOutput(
                symbol="AAPL",
                polarity=0.5,
                confidence=0.8,
                reasoning="Test reasoning",
                model_id="opus",
            )
        ]
        result = aggregator.aggregate(outputs)
        assert result is not None
        assert result.polarity == 0.5
        assert result.confidence == 0.8

    def test_aggregate_divergence(self):
        """Test aggregation with high divergence."""
        aggregator = EnsembleAggregator(min_confidence=0.4, divergence_threshold=0.30)
        outputs = [
            ModelOutput(
                symbol="AAPL",
                polarity=0.8,
                confidence=0.8,
                reasoning="Bullish",
                model_id="opus",
            ),
            ModelOutput(
                symbol="AAPL",
                polarity=-0.8,
                confidence=0.8,
                reasoning="Bearish",
                model_id="qwen",
            ),
        ]
        result = aggregator.aggregate(outputs)
        # High divergence should return None
        assert result is None

    def test_aggregate_no_eligible_models(self):
        """Test aggregation when no models meet confidence threshold."""
        aggregator = EnsembleAggregator(min_confidence=0.4, divergence_threshold=0.30)
        outputs = [
            ModelOutput(
                symbol="AAPL",
                polarity=0.5,
                confidence=0.2,  # Below threshold
                reasoning="Low confidence",
                model_id="opus",
            )
        ]
        result = aggregator.aggregate(outputs)
        assert result is None

    def test_aggregate_zero_total_confidence(self):
        """Test aggregation handles zero total confidence (ZeroDivisionError fix)."""
        aggregator = EnsembleAggregator(min_confidence=0.0, divergence_threshold=0.30)
        outputs = [
            ModelOutput(
                symbol="AAPL",
                polarity=0.5,
                confidence=0.0,  # Zero confidence
                reasoning="Zero conf",
                model_id="opus",
            ),
            ModelOutput(
                symbol="AAPL",
                polarity=0.3,
                confidence=0.0,  # Zero confidence
                reasoning="Zero conf",
                model_id="qwen",
            ),
        ]
        # Should return None instead of raising ZeroDivisionError
        result = aggregator.aggregate(outputs)
        assert result is None

    def test_aggregate_weighted_average(self):
        """Test confidence-weighted average calculation."""
        aggregator = EnsembleAggregator(min_confidence=0.4, divergence_threshold=0.30)
        outputs = [
            ModelOutput(
                symbol="AAPL",
                polarity=0.8,
                confidence=0.9,
                reasoning="Strong bullish",
                model_id="opus",
            ),
            ModelOutput(
                symbol="AAPL",
                polarity=0.6,
                confidence=0.6,
                reasoning="Moderate bullish",
                model_id="qwen",
            ),
        ]
        result = aggregator.aggregate(outputs)
        assert result is not None
        # Weighted polarity = (0.8*0.9 + 0.6*0.6) / (0.9+0.6) = 1.08/1.5 = 0.72
        # Std con ddof=1 per [0.8, 0.6] = 0.141 < 0.30 (no divergence)
        assert abs(result.polarity - 0.72) < 0.01
        assert abs(result.ensemble_std - 0.141) < 0.01

    def test_aggregate_per_model_weights_applied(self):
        """LOO ICIR weights (Bug 2 fix): weights dict is read and shifts polarity.

        Without per-model weights both models contribute equally via confidence.
        With weights boosting the high-polarity model, the result must shift
        toward that model's polarity compared to the unweighted baseline.

        Polarities chosen so std([0.7, 0.4], ddof=1) ≈ 0.21 < divergence_threshold=0.30.
        """
        aggregator = EnsembleAggregator(min_confidence=0.4, divergence_threshold=0.30)
        outputs = [
            ModelOutput(symbol="AAPL", polarity=0.7, confidence=0.7,
                        reasoning="Bullish", model_id="high_model"),
            ModelOutput(symbol="AAPL", polarity=0.4, confidence=0.7,
                        reasoning="Mild bullish", model_id="low_model"),
        ]
        # Unweighted (weights=None): both LOO weights are 1.0
        # _w(high) = 0.7*1 = 0.7, _w(low) = 0.7*1 = 0.7, total = 1.4
        # polarity = (0.7*0.7 + 0.4*0.7) / 1.4 = 0.77/1.4 = 0.55
        result_unweighted = aggregator.aggregate(outputs, weights=None)
        assert result_unweighted is not None
        assert abs(result_unweighted.polarity - 0.55) < 0.01

        # Weighted: high_model gets LOO weight 3×
        # _w(high) = 0.7*3 = 2.1, _w(low) = 0.7*1 = 0.7, total = 2.8
        # polarity = (0.7*2.1 + 0.4*0.7) / 2.8 = (1.47+0.28)/2.8 = 1.75/2.8 ≈ 0.625
        result_weighted = aggregator.aggregate(outputs, weights={"high_model": 3.0, "low_model": 1.0})
        assert result_weighted is not None
        assert abs(result_weighted.polarity - 0.625) < 0.01
        # Weighted result is strictly higher than unweighted
        assert result_weighted.polarity > result_unweighted.polarity

    def test_aggregate_unknown_model_id_uses_default_weight(self):
        """Models absent from the weights dict default to weight 1.0 (not dropped)."""
        aggregator = EnsembleAggregator(min_confidence=0.4, divergence_threshold=0.30)
        outputs = [
            ModelOutput(symbol="AAPL", polarity=0.6, confidence=0.8,
                        reasoning="Bullish", model_id="known_model"),
            ModelOutput(symbol="AAPL", polarity=0.4, confidence=0.8,
                        reasoning="Mild bullish", model_id="unknown_model"),
        ]
        # unknown_model not in weights → treated as weight 1.0 (same as known_model)
        result = aggregator.aggregate(outputs, weights={"known_model": 1.0})
        assert result is not None
        # Both models get equal effective weight → polarity = (0.6+0.4)/2 = 0.50
        assert abs(result.polarity - 0.50) < 0.01
