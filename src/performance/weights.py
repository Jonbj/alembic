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
    model_returns: Dict[str, List[float]],
    current_weights: Dict[str, float],
    window_size: int = 30,
    step_size: int = 5,
) -> Dict[str, float]:
    """
    Compute per-model rolling ICIR for use in ensemble weight rebalancing.

    For each model, computes ICIR on that model's own signals and forward
    returns. Higher ICIR → model is more predictive → gets more weight via
    compute_new_weights().

    Parameters
    ----------
    model_signals : Dict[str, List[float]]
        model_id → list of signal scores.
    model_returns : Dict[str, List[float]]
        model_id → list of forward returns aligned with model_signals[model_id].
    current_weights : Dict[str, float]
        Current ensemble weights (unused here, kept for API compatibility).
    window_size : int, default=30
        Rolling window size for IC calculation.
    step_size : int, default=5
        Step size between windows.

    Returns
    -------
    Dict[str, float]
        model_id → ICIR (mean IC / std IC). Higher = better.
    """
    if not model_signals:
        return {}

    purified_icir: Dict[str, float] = {}

    for model, signals in model_signals.items():
        returns = model_returns.get(model, [])
        if len(signals) != len(returns) or len(signals) < window_size:
            purified_icir[model] = 0.0
            continue

        ic_series = _compute_rolling_ic(signals, returns, window_size, step_size)
        if not ic_series:
            purified_icir[model] = 0.0
            continue

        ic_array = np.array(ic_series)
        ic_std = float(np.std(ic_array)) + 1e-8
        purified_icir[model] = float(np.mean(ic_array) / ic_std)

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
