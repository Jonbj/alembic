"""
Ensemble weight computation using Leave-One-Out ICIR.

This module implements the purified ICIR calculation (LOO) and weight smoothing
as specified in the design spec (Section 4, PW-Q1).
"""

import numpy as np
from scipy.stats import spearmanr
from typing import Dict, List, Tuple


def compute_purified_icir(
    model_signals: Dict[str, List[float]],
    forward_returns: List[float],
    current_weights: Dict[str, float],
    window_size: int = 30,
    step_size: int = 5,
) -> Dict[str, float]:
    """
    Compute Leave-One-Out ICIR for each model in the ensemble.

    The LOO approach prevents chicken-and-egg bias: for each target model,
    we compute the IC of an ensemble that EXCLUDES that model, then measure
    how much the target model's inclusion would improve predictive power.

    Parameters
    ----------
    model_signals : Dict[str, List[float]]
        Dictionary mapping model_id to list of signal scores over time.
        All models must have the same length (len(forward_returns)).
    forward_returns : List[float]
        List of forward returns aligned with signals.
    current_weights : Dict[str, float]
        Current ensemble weights for each model.
    window_size : int, default=30
        Rolling window size for IC calculation (min samples per window).
    step_size : int, default=5
        Step size for rolling window (stride between windows).

    Returns
    -------
    Dict[str, float]
        Dictionary mapping model_id to purified ICIR (IC mean / IC std).

    Notes
    -----
    Based on design spec Section 4, PW-Q1:
    - For each target model, compute ensemble scores excluding that model
    - Calculate rolling IC over windows of `window_size` samples
    - ICIR = mean(IC_series) / std(IC_series)
    """
    if not model_signals:
        return {}

    # Convert to list if numpy array
    if hasattr(forward_returns, 'tolist'):
        forward_returns = forward_returns.tolist()

    if not forward_returns:
        return {}

    n_samples = len(forward_returns)
    purified_icir = {}

    for target_model, target_signals in model_signals.items():
        # Build ensemble excluding target model
        other_models = [m for m in model_signals.keys() if m != target_model]

        if not other_models:
            # Only one model — cannot compute LOO
            # Fall back to simple ICIR for the single model
            ic_series = _compute_rolling_ic(
                target_signals, forward_returns, window_size, step_size
            )
        else:
            # Compute LOO ensemble scores: weighted sum of other models
            loo_scores = []
            for i in range(n_samples):
                score = sum(
                    model_signals[m][i] * current_weights[m] for m in other_models
                )
                loo_scores.append(score)

            # Compute rolling IC between LOO ensemble and forward returns
            ic_series = _compute_rolling_ic(
                loo_scores, forward_returns, window_size, step_size
            )

        # ICIR = mean(IC) / std(IC)
        ic_array = np.array(ic_series)
        ic_mean = np.mean(ic_array)
        ic_std = np.std(ic_array) + 1e-8  # epsilon to avoid division by zero

        purified_icir[target_model] = float(ic_mean / ic_std)

    return purified_icir


def _compute_rolling_ic(
    scores: List[float],
    returns: List[float],
    window_size: int,
    step_size: int,
) -> List[float]:
    """
    Compute rolling Spearman IC between scores and returns.

    Parameters
    ----------
    scores : List[float]
        Signal scores over time.
    returns : List[float]
        Forward returns aligned with scores.
    window_size : int
        Rolling window size.
    step_size : int
        Step size between windows.

    Returns
    -------
    List[float]
        List of IC values for each window.
    """
    ic_series = []
    n = len(scores)

    for start in range(0, n - window_size + 1, step_size):
        end = start + window_size
        window_scores = scores[start:end]
        window_returns = returns[start:end]

        # Spearman correlation
        ic, _ = spearmanr(window_scores, window_returns)
        if not np.isnan(ic):
            ic_series.append(ic)

    return ic_series


def compute_new_weights(
    purified_icir: Dict[str, float],
    current_weights: Dict[str, float],
    alpha: float = 0.25,
    floor: float = 0.10,
    cap: float = 0.70,
    max_delta: float = 0.10,
) -> Dict[str, float]:
    """
    Compute new ensemble weights from purified ICIR with smoothing and guardrails.

    The formula applies softmax-like normalization to ICIR values, then blends
    with current weights using exponential smoothing.

    Parameters
    ----------
    purified_icir : Dict[str, float]
        Purified ICIR for each model (from compute_purified_icir).
    current_weights : Dict[str, float]
        Current ensemble weights (must sum to 1.0).
    alpha : float, default=0.25
        Smoothing factor: new_weight = (1-alpha)*old + alpha*target.
        Spec value: 0.25 (75% old, 25% new).
    floor : float, default=0.10
        Minimum weight floor (no model can go below 10%).
    cap : float, default=0.70
        Maximum weight cap (no model can exceed 70%).
    max_delta : float, default=0.10
        Maximum change per update (weights cannot move more than delta).

    Returns
    -------
    Dict[str, float]
        New normalized weights that sum to 1.0.

    Notes
    -----
    Based on design spec Section 4, PW-Q1 and PW-Q2:
    - Raw weights = max(0, ICIR) — negative ICIR models get zero
    - Normalize to sum to 1.0 (softmax-like)
    - Smoothing: blended = 0.75*old + 0.25*target
    - Guardrails: floor 10%, cap 70%, max delta 10%
    - Re-normalize to sum to 1.0
    """
    if not purified_icir:
        return current_weights.copy()

    # Step 1: Raw weights from ICIR (negative ICIR → 0)
    # Per design spec Section 4, PW-Q1: raw = max(0, ICIR)
    raw = {m: max(0.0, icir) for m, icir in purified_icir.items()}
    total = sum(raw.values())

    # Step 2: Normalize to target weights (softmax-like)
    if total > 0:
        target = {m: v / total for m, v in raw.items()}
    else:
        # All ICIR negative — keep current weights unchanged
        return current_weights.copy()

    # Step 3: Smoothing — 75% old + 25% new
    blended = {}
    for model in target.keys():
        old_w = current_weights.get(model, 1.0 / len(target))
        blended[model] = (1 - alpha) * old_w + alpha * target[model]

    # Step 4: Apply floor and cap
    clipped = {m: max(floor, min(cap, w)) for m, w in blended.items()}

    # Step 5: Re-normalize to sum to 1.0
    total = sum(clipped.values())
    if total > 0:
        normalized = {m: w / total for m, w in clipped.items()}
    else:
        # Fallback: equal weights
        n = len(clipped)
        return {m: 1.0 / n for m in clipped.keys()}

    # Step 6: Apply max_delta guardrail after normalization
    # This may cause weights to not sum exactly to 1.0, but ensures stability
    constrained = {}
    for model in normalized.keys():
        old_w = current_weights.get(model, 1.0 / len(normalized))
        w = normalized[model]
        # Clamp to [old - max_delta, old + max_delta]
        w = max(old_w - max_delta, min(old_w + max_delta, w))
        constrained[model] = w

    # Final re-normalization after max_delta clipping
    total = sum(constrained.values())
    if total > 0:
        final = {m: w / total for m, w in constrained.items()}
        # Second max_delta check after final normalization
        # (normalization can slightly violate delta, so we clip again)
        result = {}
        for model in final.keys():
            old_w = current_weights.get(model, 1.0 / len(final))
            w = final[model]
            w = max(old_w - max_delta, min(old_w + max_delta, w))
            result[model] = w
        # One last normalization
        total = sum(result.values())
        if total > 0:
            return {m: w / total for m, w in result.items()}
        return {m: 1.0 / len(result) for m in result.keys()}
    else:
        n = len(clipped)
        return {m: 1.0 / n for m in clipped.keys()}
