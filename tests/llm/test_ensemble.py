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
