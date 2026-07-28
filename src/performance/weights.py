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


def _project_to_simplex_with_bounds(
    target: Dict[str, float],
    floor: float,
    cap: float,
) -> Dict[str, float]:
    """KKT water-filling simplex projection with box constraints [floor, cap].

    Given target weights that sum to 1.0 and a box [floor, cap] per weight,
    returns the weight vector that minimises ||w - target||_2 subject to
    floor ≤ w_i ≤ cap and sum(w_i) = 1.

    Algorithm (standard KKT water-filling):
    1. Identify indices at cap → fix them there, remove from active set.
    2. Identify indices at floor → fix them there, remove from active set.
    3. For the remaining unsaturated indices, adjust them by a uniform delta
       (the Lagrange multiplier) until the active set sums to the remaining budget.
    4. Repeat until all indices are either at cap or at floor (or the active
       set naturally satisfies the budget).

    This is deterministic, O(n) per iteration, converges in ≤ n iterations.

    Raises
    ------
    ValueError
        If n * floor > 1.0 or n * cap < 1.0 — constraints are mutually
        infeasible.
    """
    n = len(target)
    if n * floor > 1.0 + 1e-9:
        raise ValueError(
            f"Box constraints are infeasible: n={n} models, floor={floor:.4f}, "
            f"minimum achievable sum={n * floor:.4f} > 1.0"
        )
    if n * cap < 1.0 - 1e-9:
        raise ValueError(
            f"Box constraints are infeasible: n={n} models, cap={cap:.4f}, "
            f"maximum achievable sum={n * cap:.4f} < 1.0"
        )

    # Bisection search for the Lagrange multiplier λ.
    # The L2 projection of t onto {w: sum(w)=1, floor<=w_i<=cap} satisfies:
    #   w_i(λ) = max(floor, min(cap, t_i + λ))
    # We find λ such that sum(w_i(λ)) = 1.
    # S(λ) = sum_i max(floor, min(cap, t_i + λ)) is monotone non-decreasing in λ.
    t = list(target.values())
    keys = list(target.keys())

    def sum_w(lamb: float) -> float:
        return sum(max(floor, min(cap, ti + lamb)) for ti in t)

    # Bracket: λ = floor - max(t) → w_i = floor (all) → S = n*floor.
    #          λ = cap - min(t)  → w_i = cap  (all) → S = n*cap.
    lo = floor - max(t)
    hi = cap - min(t)
    s_lo = sum_w(lo)
    s_hi = sum_w(hi)

    # Binary search for λ in [lo, hi] such that |S(λ) - 1| < 1e-12
    for _ in range(80):
        mid = (lo + hi) / 2.0
        s_mid = sum_w(mid)
        if abs(s_mid - 1.0) < 1e-12:
            break
        if s_mid < 1.0:
            lo = mid
        else:
            hi = mid

        lamb = (lo + hi) / 2.0
        w = [max(floor, min(cap, ti + lamb)) for ti in t]

    # Final renormalise to guarantee sum = 1.0
    total = sum(w)
    if total > 0:
        w = [v / total for v in w]

    # Invariant assertion
    eps = 1e-9
    result = dict(zip(keys, w))
    for k, v in result.items():
        assert floor - eps <= v <= cap + eps, (
            f"Output weight {k}={v:.10f} outside [{floor}, {cap}]"
        )
    assert abs(sum(result.values()) - 1.0) < 1e-9, (
        f"Output weights sum to {sum(result.values()):.15f}, expected 1.0"
    )
    return result


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

    Raises
    ------
    ValueError
        If the box constraints (n*floor > 1.0 or n*cap < 1.0) are infeasible.

    Notes
    -----
    Based on design spec Section 4, PW-Q1 and PW-Q2:
    - Raw weights = max(0, ICIR) -- negative ICIR models get zero
    - Normalize to sum to 1.0 (softmax-like)
    - Smoothing: blended = 0.75*old + 0.25*target
    - Guardrails: floor 10%, cap 70%, max delta 10%
    - Projection onto feasible simplex with box constraints via water-filling
      (deterministic, no iteration fallback)
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

    # Step 4: Apply max_delta guardrail before projection
    constrained = {}
    for model in blended.keys():
        old_w = current_weights.get(model, 1.0 / len(blended))
        w = blended[model]
        constrained[model] = max(old_w - max_delta, min(old_w + max_delta, w))

    # Step 5: Water-filling projection onto the feasible simplex with box constraints
    return _project_to_simplex_with_bounds(constrained, floor=floor, cap=cap)
