"""Tests for ensemble aggregation."""

import pytest

from src.llm.ensemble import EnsembleAggregator, ModelOutput


def _mo(polarity, confidence, model_id="m"):
    return ModelOutput(symbol="A", polarity=polarity, confidence=confidence,
                       reasoning="x", model_id=model_id)


class TestQS03AgreementWeighting:
    """QS-03: agreement (low std) increases confidence; disagreement discounts it."""

    def test_off_by_default_uses_mean_confidence(self):
        # std of [0.6,0.2] ≈ 0.283 (< 0.30 → not discarded); legacy = mean(0.8,0.6)=0.7
        agg = EnsembleAggregator()
        r = agg.aggregate([_mo(0.6, 0.8, "m1"), _mo(0.2, 0.6, "m2")])
        assert r.confidence == pytest.approx(0.7)

    def test_on_discounts_disagreement(self):
        agg = EnsembleAggregator(agreement_weighting=True)
        high_disagree = agg.aggregate([_mo(0.6, 0.8, "m1"), _mo(0.2, 0.6, "m2")])   # std≈0.283
        low_disagree = agg.aggregate([_mo(0.6, 0.8, "m1"), _mo(0.58, 0.6, "m2")])   # std≈0.014
        assert high_disagree.confidence < low_disagree.confidence
        assert high_disagree.confidence < 0.7                       # discounted below mean
        assert low_disagree.confidence == pytest.approx(0.7, abs=0.05)  # agreement ≈ mean

    def test_on_single_model_no_discount(self):
        agg = EnsembleAggregator(agreement_weighting=True)
        r = agg.aggregate([_mo(0.6, 0.8, "m1")])
        assert r.confidence == pytest.approx(0.8)  # std=0, single model → no change


class TestQS10FailureLogging:
    """QS-10: model failures are logged with a kind (timeout/invalid/error), not print()."""

    def test_classify_timeout(self):
        import asyncio
        from src.llm.ensemble import _classify_failure
        assert _classify_failure(asyncio.TimeoutError()) == "timeout"
        assert _classify_failure(TimeoutError()) == "timeout"

    def test_classify_invalid(self):
        from src.llm.ensemble import _classify_failure
        assert _classify_failure(ValueError("bad json")) == "invalid"
        assert _classify_failure(KeyError("missing")) == "invalid"

    def test_classify_error(self):
        from src.llm.ensemble import _classify_failure
        assert _classify_failure(RuntimeError("boom")) == "error"

    @pytest.mark.asyncio
    async def test_run_ensemble_query_logs_failure_kind(self, caplog):
        from unittest.mock import AsyncMock, MagicMock
        from src.llm.ensemble import run_ensemble_query
        from src.models.news import LLMSentimentOutput

        client = MagicMock()
        client.model_id = "kimi-k2.6:cloud"
        client.complete = AsyncMock(side_effect=ValueError("refused"))

        with caplog.at_level("WARNING"):
            out = await run_ensemble_query("p", [client], LLMSentimentOutput, "AAPL")

        assert out == []
        assert "kind=invalid" in caplog.text
        assert "model=kimi-k2.6:cloud" in caplog.text


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

    def test_aggregate_min_confidence_override_includes_low_confidence_models(self):
        """min_confidence override (per-call) lets a caller retry aggregation
        without the eligibility floor, without mutating the instance default.

        #90: both models below the instance's min_confidence=0.4 but tightly
        agreeing (small polarity spread) — the default call still returns None
        (unchanged behavior), but passing min_confidence=0.0 for this call
        aggregates them directly instead.
        """
        aggregator = EnsembleAggregator(min_confidence=0.4, divergence_threshold=0.40)
        outputs = [
            ModelOutput(symbol="AAPL", polarity=0.0, confidence=0.2,
                        reasoning="Sector-level, no direct read-through", model_id="glm"),
            ModelOutput(symbol="AAPL", polarity=0.1, confidence=0.25,
                        reasoning="Indirect sector tailwind only", model_id="gpt"),
        ]
        # Default (instance min_confidence=0.4): both below threshold → None, unchanged.
        assert aggregator.aggregate(outputs) is None

        # Override for this call only: both become eligible, low spread → aggregates.
        result = aggregator.aggregate(outputs, min_confidence=0.0)
        assert result is not None
        assert result.model_ids == ["glm", "gpt"]
        # confidence-weighted average of (0.0, 0.2) and (0.1, 0.25)
        assert abs(result.polarity - (0.0 * 0.2 + 0.1 * 0.25) / (0.2 + 0.25)) < 0.01
        assert abs(result.confidence - 0.225) < 0.01

        # Instance default is untouched by the override (no mutation).
        assert aggregator.min_confidence == 0.4
        assert aggregator.aggregate(outputs) is None

    def test_aggregate_min_confidence_override_still_detects_genuine_divergence(self):
        """The override only bypasses the confidence floor, not the divergence
        check — models that truly disagree (even at low individual confidence)
        must still return None so run_inference correctly falls back to FinBERT.
        """
        aggregator = EnsembleAggregator(min_confidence=0.4, divergence_threshold=0.40)
        outputs = [
            ModelOutput(symbol="AAPL", polarity=0.9, confidence=0.1,
                        reasoning="Bullish", model_id="glm"),
            ModelOutput(symbol="AAPL", polarity=-0.9, confidence=0.15,
                        reasoning="Bearish", model_id="gpt"),
        ]
        assert aggregator.aggregate(outputs) is None
        assert aggregator.aggregate(outputs, min_confidence=0.0) is None

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
