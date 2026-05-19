"""
Ensemble aggregation for multiple LLM models in the LLM Trading System.

This module implements the core ensemble logic that combines predictions from
multiple LLM models (Opus, Qwen 3.5, DeepSeek-V4-Pro) into a single consensus
sentiment signal. The ensemble approach provides:

1. **Robustness**: Reduces variance from individual model errors
2. **Diversity**: Combines strengths of different model architectures
3. **Confidence calibration**: Agreement between models increases confidence
4. **Fallback detection**: High divergence triggers FinBERT fallback

Key Concepts:
- **Confidence-weighted average**: Models with higher confidence have more influence
- **Divergence threshold**: If models disagree too much (std >= 0.30), fallback to FinBERT
- **Minimum confidence**: Individual models must meet confidence threshold (0.4) to be eligible

Ensemble Flow:
    1. Query all models in parallel (asyncio.as_completed)
    2. Filter by minimum confidence
    3. Compute ensemble std (divergence metric)
    4. If std < threshold: return weighted average
    5. If std >= threshold: return None (trigger FinBERT fallback)

Usage Example:
    >>> from src.llm.ensemble import EnsembleAggregator, run_ensemble_query
    >>> from src.llm.client import OpusClient, Qwen35Client, DeepseekClient
    >>>
    >>> aggregator = EnsembleAggregator(
    ...     min_confidence=0.4,
    ...     divergence_threshold=0.30
    ... )
    >>> clients = [OpusClient(), Qwen35Client(), DeepseekClient()]
    >>>
    >>> outputs = await run_ensemble_query(
    ...     prompt="Analyze: Fed raises rates...",
    ...     clients=clients,
    ...     response_schema=LLMSentimentOutput,
    ...     symbol="SPY"
    ... )
    >>> result = aggregator.aggregate(outputs)
    >>> if result is None:
    ...     print("Ensemble diverged - use FinBERT fallback")

Author: LLM Trading System Team
Version: 1.0.0
"""

import numpy as np
from pydantic import BaseModel

from src.llm.client import LLMClient
from src.models.news import LLMSentimentOutput


class ModelOutput(BaseModel):
    """
    Standardized output from a single LLM model in the ensemble.

    This model normalizes the output format across different LLM providers
    (Anthropic, Alibaba, DeepSeek) into a common schema for aggregation.

    Attributes:
        symbol (str): Asset symbol being analyzed (e.g., "AAPL", "SPY")
        polarity (float): Sentiment polarity in range [-1.0, 1.0]
                          -1.0 = extremely bearish, +1.0 = extremely bullish
        confidence (float): Model confidence in range [0.0, 1.0]
                            Higher values indicate more certainty
        reasoning (str): Brief explanation of the model's verdict
                         (max ~200 characters for brevity)
        model_id (str): Identifier of the model that produced this output
                        (e.g., "opus", "qwen3.5:cloud", "deepseek-v4-pro:cloud")

    Example:
        >>> output = ModelOutput(
        ...     symbol="AAPL",
        ...     polarity=0.65,
        ...     confidence=0.82,
        ...     reasoning="Strong earnings beat with positive guidance",
        ...     model_id="opus"
        ... )
        >>> print(f"{output.model_id}: {output.polarity} (conf: {output.confidence})")
    """

    symbol: str
    polarity: float
    confidence: float
    reasoning: str
    model_id: str


class AggregatedResult(BaseModel):
    """
    Aggregated consensus result from the ensemble.

    This model represents the combined output after aggregating predictions
    from multiple LLM models. It includes both the consensus values and
    metadata about the ensemble's internal agreement.

    Attributes:
        symbol (str): Asset symbol being analyzed
        polarity (float): Consensus sentiment polarity [-1.0, 1.0]
                          Computed as confidence-weighted average
        confidence (float): Consensus confidence [0.0, 1.0]
                            Computed as mean of eligible model confidences
        reasoning (str): Reasoning from the highest-confidence model
        model_ids (list[str]): List of model IDs that contributed to the consensus
        ensemble_std (float): Standard deviation of polarities among eligible models
                              Used as divergence metric (threshold: 0.30)

    Interpretation:
        - ensemble_std < 0.10: Strong agreement (high confidence in consensus)
        - ensemble_std 0.10-0.30: Moderate agreement (acceptable variance)
        - ensemble_std >= 0.30: High divergence (trigger FinBERT fallback)

    Example:
        >>> result = AggregatedResult(
        ...     symbol="AAPL",
        ...     polarity=0.58,
        ...     confidence=0.75,
        ...     reasoning="Positive earnings with cautious outlook",
        ...     model_ids=["opus", "qwen3.5:cloud", "deepseek-v4-pro:cloud"],
        ...     ensemble_std=0.12
        ... )
        >>> signal_score = result.polarity * result.confidence  # 0.435
    """

    symbol: str
    polarity: float
    confidence: float
    reasoning: str
    model_ids: list[str]
    ensemble_std: float


class EnsembleAggregator:
    """
    Aggregates outputs from multiple LLM models into a consensus sentiment.

    The aggregator implements a confidence-weighted voting scheme with
    divergence detection:

    1. **Eligibility Filter**: Only models with confidence >= min_confidence are considered
    2. **Divergence Check**: If ensemble_std >= divergence_threshold, return None
    3. **Weighted Average**: Polarity weighted by individual model confidences
    4. **Consensus Confidence**: Mean of eligible model confidences

    Design Rationale:
        - Confidence weighting gives more influence to certain models
        - Divergence detection catches cases where models fundamentally disagree
        - Using reasoning from best model provides human-explainable output

    Attributes:
        min_confidence (float): Minimum confidence for a model to be eligible (default: 0.4)
        divergence_threshold (float): Max acceptable ensemble std (default: 0.30)

    Usage Example:
        >>> aggregator = EnsembleAggregator(
        ...     min_confidence=0.4,      # Models below 40% confidence are ignored
        ...     divergence_threshold=0.30  # Std >= 0.30 triggers fallback
        ... )
        >>> result = aggregator.aggregate([output1, output2, output3])
        >>> if result is None:
        ...     print("Divergence detected - falling back to FinBERT")
    """

    def __init__(self, min_confidence: float = 0.4, divergence_threshold: float = 0.30):
        """
        Initialize the ensemble aggregator with configurable thresholds.

        Args:
            min_confidence: Minimum confidence threshold for model eligibility.
                           Models with confidence < this value are excluded.
                           Typical value: 0.4 (40% confidence)
                           Range: [0.0, 1.0]

            divergence_threshold: Maximum acceptable standard deviation of polarities.
                                 If ensemble_std >= this value, aggregation fails
                                 and FinBERT fallback is triggered.
                                 Typical value: 0.30 (30% std)
                                 Range: [0.0, 1.0]

        Note:
            These thresholds are critical hyperparameters that affect the
            trade-off between ensemble coverage and prediction quality:
            - Lower min_confidence = more models included, but noisier consensus
            - Lower divergence_threshold = stricter agreement required, more fallbacks
        """
        self.min_confidence = min_confidence
        self.divergence_threshold = divergence_threshold

    def aggregate(self, outputs: list[ModelOutput], weights: dict[str, float] | None = None) -> AggregatedResult | None:
        """
        Aggregate model outputs into a single consensus result.

        This method implements the core ensemble aggregation algorithm:

        Step 1: Eligibility Filtering
            Filter outputs to only include models with confidence >= min_confidence.
            Models below the threshold are excluded from the consensus.

        Step 2: Edge Case Handling
            - If no models are eligible: return None (trigger fallback)
            - If only one model is eligible: use it (no divergence possible)

        Step 3: Divergence Calculation
            Compute standard deviation of polarities among eligible models.
            This measures how much the models disagree.

        Step 4: Divergence Check
            If std >= divergence_threshold AND multiple models: return None
            This catches cases where models fundamentally disagree.

        Step 5: Weighted Aggregation
            - Polarity: confidence-weighted average
            - Confidence: mean of eligible model confidences
            - Reasoning: from highest-confidence model

        Args:
            outputs: List of ModelOutput from each LLM model in the ensemble.
                    Length is typically 2-4 (one per model).

        Returns:
            AggregatedResult with consensus values, or None if:
            - No models meet minimum confidence threshold
            - Ensemble std exceeds divergence threshold (models disagree too much)
            - Total confidence is zero (edge case protection)

        Example:
            >>> aggregator = EnsembleAggregator()
            >>> outputs = [
            ...     ModelOutput(symbol="AAPL", polarity=0.6, confidence=0.8,
            ...                 reasoning="Bullish", model_id="opus"),
            ...     ModelOutput(symbol="AAPL", polarity=0.5, confidence=0.7,
            ...                 reasoning="Moderate bullish", model_id="qwen"),
            ... ]
            >>> result = aggregator.aggregate(outputs)
            >>> print(f"Consensus: {result.polarity} (conf: {result.confidence})")
            Consensus: 0.55 (conf: 0.75)
        """
        eligible = [o for o in outputs if o.confidence >= self.min_confidence]

        if not eligible:
            return None

        std = float(np.std([o.polarity for o in eligible], ddof=1)) if len(eligible) > 1 else 0.0

        if len(eligible) > 1 and std >= self.divergence_threshold:
            return None

        # Weight each model by confidence × per-model weight (from Redis LOO ICIR rebalancing).
        # Falls back to confidence-only when weights are not available.
        def _w(o: ModelOutput) -> float:
            return o.confidence * (weights.get(o.model_id, 1.0) if weights else 1.0)

        total_weight = sum(_w(o) for o in eligible)
        if total_weight == 0:
            return None
        weighted_polarity = sum(o.polarity * _w(o) for o in eligible) / total_weight
        mean_confidence = sum(o.confidence for o in eligible) / len(eligible)

        # Use reasoning from highest-confidence model
        best = max(eligible, key=lambda o: o.confidence)

        return AggregatedResult(
            symbol=eligible[0].symbol,
            # Clamping non necessario ma mantenuto per safety (weighted avg di valori in [-1,1] è sempre in [-1,1])
            polarity=max(-1.0, min(1.0, weighted_polarity)),
            confidence=mean_confidence,
            reasoning=best.reasoning,
            model_ids=[o.model_id for o in eligible],
            ensemble_std=std,
        )


async def run_ensemble_query(
    prompt: str,
    clients: list[LLMClient],
    response_schema: type[LLMSentimentOutput],
    symbol: str,
) -> list[ModelOutput]:
    """
    Run ensemble query across multiple models with CORRECT task tracking.

    Uses a dictionary to map each Task to its model_id, avoiding the bug where
    asyncio.as_completed returns results in arbitrary order and index-based
    lookup fails.

    Args:
        prompt: The prompt to send to all models
        clients: List of LLM clients to query (must not be empty)
        response_schema: Pydantic model for response validation
        symbol: Asset symbol for the query

    Returns:
        List of ModelOutput objects, one per successful model response

    Raises:
        ValueError: If clients list is empty
    """
    import asyncio

    # EDGE CASE: Handle empty clients list
    if not clients:
        print("Ensemble: No clients configured - returning empty results")
        return []

    # gather preserves order → model_id association is trivial (index-based)
    results = await asyncio.gather(
        *[client.complete(prompt, response_schema) for client in clients],
        return_exceptions=True,
    )

    raw_outputs: list[ModelOutput] = []
    for client, result in zip(clients, results):
        if isinstance(result, BaseException):
            print(f"Ensemble: Model {client.model_id} failed: {result}")
            continue
        raw_outputs.append(
            ModelOutput(
                symbol=symbol,
                polarity=result.polarity,
                confidence=result.confidence,
                reasoning=result.reasoning,
                model_id=client.model_id,
            )
        )

    return raw_outputs
