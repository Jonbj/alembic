"""
Threshold suggestion module for LLM trading signals.

Implements:
- Bucket IC analysis: computes IC/ICIR for confidence buckets
- Threshold suggestion: finds optimal confidence threshold to filter low-quality signals

The goal is to identify the minimum confidence level below which predictive power
(IC) degrades significantly, allowing the system to filter out low-quality signals.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple
import numpy as np

from .ic import compute_composite_ic, compute_icir


# Default confidence buckets as specified in the design plan
DEFAULT_BUCKETS = [
    (0.0, 0.3),   # Low confidence
    (0.3, 0.5),   # Medium-low confidence
    (0.5, 0.7),   # Medium-high confidence
    (0.7, 1.0),   # High confidence
]


@dataclass
class BucketICResult:
    """IC analysis result for a single confidence bucket."""
    bucket_range: Tuple[float, float]
    sample_count: int
    composite_ic: float
    icir: float
    mean_confidence: float
    hit_rate: float


@dataclass
class ThresholdSuggestion:
    """Result of threshold suggestion analysis."""
    suggested_threshold: float
    reasoning: str
    bucket_results: List[BucketICResult]
    max_icir_bucket: Optional[Tuple[float, float]]
    degradation_point: Optional[float]


def bucket_ic_analysis(
    scores: List[float],
    forward_returns: List[float],
    confidences: List[float],
    buckets: Optional[List[Tuple[float, float]]] = None,
    min_samples_per_bucket: int = 10,
) -> List[BucketICResult]:
    """
    Compute IC and ICIR for each confidence bucket.

    This analysis reveals how predictive power varies across different confidence
    levels, helping identify where IC starts to degrade.

    Args:
        scores: LLM sentiment scores (range [-1, +1])
        forward_returns: Realized forward returns over the prediction horizon
        confidences: Model confidences (range [0, 1])
        buckets: List of (low, high) confidence ranges.
                 Defaults to [(0, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 1.0)]
        min_samples_per_bucket: Minimum samples required to compute IC for a bucket.
                                Buckets with fewer samples get ic=0, icir=0.

    Returns:
        List of BucketICResult, one per bucket (in the same order as input buckets).

    Notes:
        - Uses composite IC (0.5*Spearman + 0.3*weighted_hit_rate + 0.2*(1-Brier))
        - ICIR uses Newey-West HAC correction by default
    """
    if buckets is None:
        buckets = DEFAULT_BUCKETS.copy()

    if len(scores) != len(forward_returns) or len(scores) != len(confidences):
        raise ValueError("scores, forward_returns, and confidences must have same length")

    if len(scores) == 0:
        raise ValueError("scores, forward_returns, and confidences cannot be empty")

    scores_arr = np.array(scores)
    returns_arr = np.array(forward_returns)
    conf_arr = np.array(confidences)

    results = []

    for low, high in buckets:
        # Filter samples within this confidence bucket
        # Use [low, high) for all but the last bucket, which is [low, high]
        if high == 1.0:
            mask = (conf_arr >= low) & (conf_arr <= high)
        else:
            mask = (conf_arr >= low) & (conf_arr < high)

        bucket_scores = scores_arr[mask].tolist()
        bucket_returns = returns_arr[mask].tolist()
        bucket_confs = conf_arr[mask].tolist()

        n_samples = len(bucket_scores)

        if n_samples < min_samples_per_bucket:
            # Not enough samples - return zeros
            results.append(BucketICResult(
                bucket_range=(low, high),
                sample_count=n_samples,
                composite_ic=0.0,
                icir=0.0,
                mean_confidence=float(np.mean(bucket_confs)) if bucket_confs else 0.0,
                hit_rate=0.0,
            ))
            continue

        # Compute composite IC
        ic_result = compute_composite_ic(bucket_scores, bucket_returns, bucket_confs)

        # Compute ICIR
        icir_result = compute_icir(bucket_scores, bucket_returns, bucket_confs)

        # Compute simple hit rate (unweighted)
        score_signs = np.sign(np.array(bucket_scores))
        return_signs = np.sign(np.array(bucket_returns))
        hits = (score_signs == return_signs) & (score_signs != 0) & (return_signs != 0)
        hit_rate = float(np.sum(hits) / len(hits)) if len(hits) > 0 else 0.0

        results.append(BucketICResult(
            bucket_range=(low, high),
            sample_count=n_samples,
            composite_ic=ic_result.composite_ic,
            icir=icir_result.icir,
            mean_confidence=float(np.mean(bucket_confs)),
            hit_rate=hit_rate,
        ))

    return results


def suggest_threshold(
    scores: List[float],
    forward_returns: List[float],
    confidences: List[float],
    buckets: Optional[List[Tuple[float, float]]] = None,
    min_samples_per_bucket: int = 10,
) -> ThresholdSuggestion:
    """
    Suggest an optimal confidence threshold for filtering low-quality signals.

    The suggested threshold is the confidence level below which IC/ICIR starts
    to degrade significantly. This allows the system to filter out signals that
    are unlikely to be predictive.

    Algorithm:
    1. Compute IC/ICIR for each confidence bucket
    2. Find the bucket with maximum ICIR (best risk-adjusted predictive power)
    3. Identify the degradation point: where ICIR drops below 50% of max
    4. Suggest threshold = lower bound of the best ICIR bucket

    Args:
        scores: LLM sentiment scores (range [-1, +1])
        forward_returns: Realized forward returns
        confidences: Model confidences (range [0, 1])
        buckets: Confidence bucket ranges. Defaults to DEFAULT_BUCKETS.
        min_samples_per_bucket: Minimum samples for valid IC computation.

    Returns:
        ThresholdSuggestion with:
        - suggested_threshold: The recommended minimum confidence
        - reasoning: Human-readable explanation
        - bucket_results: Full IC analysis per bucket
        - max_icir_bucket: The bucket range with highest ICIR
        - degradation_point: Confidence where ICIR drops significantly (if found)

    Notes:
        - If all buckets have ICIR <= 0, returns threshold=0.5 (conservative default)
        - If max ICIR bucket is the lowest confidence bucket, threshold = 0
          (no filtering recommended - even low confidence signals are predictive)
    """
    bucket_results = bucket_ic_analysis(
        scores, forward_returns, confidences, buckets, min_samples_per_bucket
    )

    # Find bucket with maximum ICIR (among buckets with sufficient samples)
    valid_buckets = [(i, r) for i, r in enumerate(bucket_results) if r.sample_count >= min_samples_per_bucket]

    if not valid_buckets:
        # No valid buckets - return conservative default
        return ThresholdSuggestion(
            suggested_threshold=0.5,
            reasoning="Insufficient samples in all buckets - using conservative default threshold",
            bucket_results=bucket_results,
            max_icir_bucket=None,
            degradation_point=None,
        )

    # Find max ICIR bucket
    max_icir_idx, max_icir_result = max(valid_buckets, key=lambda x: x[1].icir)
    max_icir_bucket = max_icir_result.bucket_range
    max_icir_value = max_icir_result.icir

    # Find degradation point: where ICIR drops below 50% of max
    degradation_point = None
    threshold_50_pct = max_icir_value * 0.5

    for i, result in enumerate(bucket_results):
        if result.sample_count < min_samples_per_bucket:
            continue
        if result.icir < threshold_50_pct:
            # ICIR degraded at this bucket
            degradation_point = result.bucket_range[0]
            break

    # Determine suggested threshold
    if max_icir_value <= 0:
        # All ICIR values are negative or zero - use conservative default
        suggested_threshold = 0.5
        reasoning = (
            f"All buckets have non-positive ICIR (max={max_icir_value:.3f}). "
            f"Using conservative default threshold of 0.5."
        )
    elif max_icir_idx == 0:
        # Best bucket is lowest confidence - no filtering needed
        suggested_threshold = 0.0
        reasoning = (
            f"Lowest confidence bucket ({max_icir_bucket[0]}-{max_icir_bucket[1]}) "
            f"has highest ICIR ({max_icir_value:.3f}). No filtering recommended."
        )
    else:
        # Suggest threshold = lower bound of best ICIR bucket
        suggested_threshold = max_icir_bucket[0]
        reasoning = (
            f"Bucket {max_icir_bucket[0]}-{max_icir_bucket[1]} has highest ICIR ({max_icir_value:.3f}). "
            f"Suggest filtering signals with confidence < {suggested_threshold:.2f}. "
            f"ICIR degradation point at confidence {degradation_point}."
        )

    return ThresholdSuggestion(
        suggested_threshold=suggested_threshold,
        reasoning=reasoning,
        bucket_results=bucket_results,
        max_icir_bucket=max_icir_bucket,
        degradation_point=degradation_point,
    )
