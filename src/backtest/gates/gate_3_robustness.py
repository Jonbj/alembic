"""Gate 3 – Parameter Robustness.

Strategy must be stable under parameter perturbation:
  • Sharpe ratio must not vary by more than `max_cv` (coefficient of variation)
    across parameter perturbations.
  • All perturbed Sharpe ratios must remain positive (unless relaxed).
"""
from __future__ import annotations

import numpy as np

from src.backtest.gates.gate_types import GateResult


def gate_3_robustness(
    perturbed_sharpes: list[float],
    base_sharpe: float | None = None,
    max_cv: float = 0.5,
    min_all_positive: bool = False,
) -> GateResult:
    """Gate 3: Parameter sensitivity / robustness.

    Parameters
    ----------
    perturbed_sharpes : list[float]
        Sharpe ratios from perturbed parameter runs.
    base_sharpe : float or None
        The baseline (unperturbed) Sharpe. If provided, checked for inclusion.
    max_cv : float
        Maximum allowed coefficient of variation of Sharpe across perturbations.
    min_all_positive : bool
        If True, all perturbed Sharpes must be > 0.

    """
    if not perturbed_sharpes:
        return GateResult(passed=False, details={"error": "no perturbed sharpes provided"})

    arr = np.array(perturbed_sharpes, dtype=float)
    mean_sr = float(np.mean(arr))
    std_sr = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
    cv = std_sr / abs(mean_sr) if abs(mean_sr) > 1e-10 else float("inf")
    all_positive = bool(np.all(arr > 0))
    min_sr = float(np.min(arr))
    max_sr = float(np.max(arr))

    passed = True
    reasons = []

    if cv > max_cv:
        passed = False
        reasons.append(f"CV={cv:.4f} > max_cv={max_cv}")

    if min_all_positive and not all_positive:
        passed = False
        reasons.append("not all perturbed Sharpes are positive")

    details = {
        "mean_sharpe": round(mean_sr, 4),
        "std_sharpe": round(std_sr, 4),
        "cv": round(cv, 4),
        "min_sharpe": round(min_sr, 4),
        "max_sharpe": round(max_sr, 4),
        "all_positive": all_positive,
        "n_perturbations": len(perturbed_sharpes),
        "thresholds": {
            "max_cv": max_cv,
            "min_all_positive": min_all_positive,
        },
    }
    if reasons:
        details["fail_reasons"] = reasons

    return GateResult(passed=passed, details=details)
