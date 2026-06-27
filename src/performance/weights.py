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
    Compute per-model LOO (Leave-One-Out) ICIR for ensemble weight rebalancing.

    For each model M:
    1. Compute baseline ensemble ICIR using all models' signals
    2. Compute ensemble ICIR after leaving out model M
    3. purified_icir[M] = baseline_ICIR - ICIR_without_M

    A positive purified ICIR means the model adds predictive value to the
    ensemble (removing it degrades performance). A negative value means
    the model hurts the ensemble.

    If only one model is available, falls back to its standalone ICIR
    (mean IC / std IC over a rolling window).

    Parameters
    ----------
    model_signals : Dict[str, List[float]]
        model_id -> list of signal scores.
    model_returns : Dict[str, List[float]]
        model_id -> list of forward returns aligned with model_signals[model_id].
    current_weights : Dict[str, float]
        Current ensemble weights (used to weight each model in baseline IC computation).
    window_size : int, default=30
        Rolling window size for IC calculation.
    step_size : int, default=5
        Step size between windows.

    Returns
    -------
    Dict[str, float]
        model_id -> LOO ICIR. Positive = model helps the ensemble.
    """
    if not model_signals:
        return {}

    models = list(model_signals.keys())

    # Single model: fall back to standalone ICIR
    if len(models) < 2:
        model = models[0]
        signals = model_signals[model]
        returns = model_returns.get(model, [])
        if len(signals) != len(returns) or len(signals) < window_size:
            return {model: 0.0}
        ic_series = _compute_rolling_ic(signals, returns, window_size, step_size)
        if not ic_series:
            return {model: 0.0}
        ic_array = np.array(ic_series)
        ic_std = float(np.std(ic_array)) + 1e-8
        return {model: float(np.mean(ic_array) / ic_std)}

    # Build aligned time-series for the ensemble.
    # Each model may have a different number of signals; we take the minimum
    # length across all models as the common evaluation window.
    min_len = min(len(model_signals[m]) for m in models)
    if min_len < window_size:
        # Not enough data for any LOO computation
        return {m: 0.0 for m in models}

    # Compute baseline ensemble ICIR using weighted-average signals
    baseline_icir = _compute_ensemble_icir(
        model_signals, model_returns, current_weights,
        exclude=None, window_size=window_size, step_size=step_size,
    )

    # LOO: compute ICIR with each model excluded
    purified_icir: Dict[str, float] = {}
    for model in models:
        loo_icir = _compute_ensemble_icir(
            model_signals, model_returns, current_weights,
            exclude=model, window_size=window_size, step_size=step_size,
        )
        # Positive = removing model degrades ensemble -> model adds value
        purified_icir[model] = baseline_icir - loo_icir

    return purified_icir


def _compute_ensemble_icir(
    model_signals: Dict[str, List[float]],
    model_returns: Dict[str, List[float]],
    current_weights: Dict[str, float],
    exclude: str | None = None,
    window_size: int = 30,
    step_size: int = 5,
) -> float:
    """Compute ICIR for the ensemble, optionally excluding one model.

    The ensemble signal at each time step is the weighted average of
    individual model signals, using current_weights. The forward return
    is the weighted average of model returns (or equivalently, the common
    forward return if all models predict the same underlying asset).

    ICIR = mean(rolling IC) / std(rolling IC).
    """
    models = [m for m in model_signals if m != exclude] if exclude else list(model_signals.keys())

    if not models:
        return 0.0

    # Normalize weights for the included models
    raw_weights = {m: current_weights.get(m, 1.0 / len(model_signals)) for m in models}
    total_w = sum(raw_weights.values())
    if total_w <= 0:
        return 0.0
    norm_weights = {m: w / total_w for m, w in raw_weights.items()}

    # Compute weighted-average ensemble signal and return at each time step.
    # All models must have the same length for alignment.
    min_len = min(len(model_signals[m]) for m in models)
    if min_len < window_size:
        return 0.0

    ensemble_signals = []
    ensemble_returns = []
    for i in range(min_len):
        sig = sum(model_signals[m][i] * norm_weights[m] for m in models)
        ret = sum(model_returns.get(m, [0.0] * min_len)[i] * norm_weights[m] for m in models)
        ensemble_signals.append(sig)
        ensemble_returns.append(ret)

    ic_series = _compute_rolling_ic(ensemble_signals, ensemble_returns, window_size, step_size)
    if not ic_series:
        return 0.0

    ic_array = np.array(ic_series)
    ic_std = float(np.std(ic_array)) + 1e-8
    return float(np.mean(ic_array) / ic_std)


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
    - Raw weights = max(0, ICIR) -- negative ICIR models get zero
    - Normalize to sum to 1.0 (softmax-like)
    - Smoothing: blended = 0.75*old + 0.25*target
    - Guardrails: floor 10%, cap 70%, max delta 10%
    - Re-normalize to sum to 1.0
    """
    if not purified_icir:
        return current_weights.copy()

    # Step 1: Raw weights from ICIR (negative ICIR -> 0)
    # Per design spec Section 4, PW-Q1: raw = max(0, ICIR)
    raw = {m: max(0.0, icir) for m, icir in purified_icir.items()}
    total = sum(raw.values())

    # Step 2: Normalize to target weights (softmax-like)
    if total > 0:
        target = {m: v / total for m, v in raw.items()}
    else:
        # All ICIR negative -- keep current weights unchanged
        return current_weights.copy()

    # Step 3: Smoothing -- 75% old + 25% new
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

    # Final re-normalization after max_delta clipping, then enforce [floor, cap].
    # Iterative projection: clip → renormalize → clip → renormalize until stable.
    # Converges in ≤3 iterations for typical 4-5 model ensembles.
    total = sum(constrained.values())
    if total <= 0:
        n = len(clipped)
        return {m: 1.0 / n for m in clipped.keys()}

    working = {m: w / total for m, w in constrained.items()}
    for _ in range(5):
        clipped2 = {m: max(floor, min(cap, w)) for m, w in working.items()}
        t = sum(clipped2.values())
        if t <= 0:
            break
        renormed = {m: w / t for m, w in clipped2.items()}
        # Check convergence: all values already within [floor, cap]
        if all(floor - 1e-9 <= v <= cap + 1e-9 for v in renormed.values()):
            return renormed
        working = renormed

    # Fallback: equal weights if projection fails to converge
    n = len(constrained)
    return {m: 1.0 / n for m in constrained.keys()}
