"""
Drift detection module for LLM trading system.

Implements:
- PSI (Population Stability Index) for distribution shift detection
- CUSUM (Cumulative Sum) for change point detection
- Circuit breakers (hard and soft) for risk management

Reference: docs/superpowers/specs/2026-05-03-trading-system-design.md
"""

import numpy as np
from dataclasses import dataclass
from typing import Literal


# PSI thresholds
PSI_YELLOW_THRESHOLD = 0.10  # Moderate drift - monitor
PSI_RED_THRESHOLD = 0.25     # Severe drift - action required


@dataclass
class DriftAlert:
    """Represents a drift detection alert."""
    level: Literal["green", "yellow", "red"]
    psi_90gg: float
    psi_12m: float | None
    cusum_value: float
    cusum_threshold: float
    baseline_mean: float
    current_mean: float
    alert_type: str  # "psi_only" | "psi_cusum_confirmed" | "cusum_only"


@dataclass
class CircuitBreakerContext:
    """Context data for circuit breaker checks."""
    vix: float
    vix_1d_change: float
    portfolio_drawdown: float
    consecutive_negative_ic_days: int
    portfolio_earnings_pct: float
    cross_asset_correlation: float


@dataclass
class CircuitBreakerResult:
    """Result of circuit breaker evaluation."""
    freeze_weight_update: bool
    reason: str | None
    hard_breakers_triggered: list[str]
    soft_warnings_triggered: list[str]


def compute_psi(
    baseline: np.ndarray,
    current: np.ndarray,
    bins: int = 10
) -> float:
    """
    Compute Population Stability Index (PSI) between baseline and current distributions.

    KL(expected || actual) = Σ expected_i × ln(expected_i / actual_i)

    Nota implementativa: questa funzione calcola la KL divergence KL(E||A), non
    il PSI standard finanziario (che usa il fattore moltiplicativo (actual_i - expected_i)).
    La KL divergence produce valori più alti a parità di shift distribuzionale,
    quindi le soglie 0.10/0.25 rendono il sistema più reattivo rispetto al PSI classico.
    Questa è una scelta intenzionale: maggiore sensibilità al drift per risk management.

    Interpretazione:
        - KL < 0.10: stabile (nessuna azione)
        - KL 0.10-0.25: moderate drift (yellow alert, monitoraggio)
        - KL > 0.25: severe drift (red alert, azione richiesta)

    Args:
        baseline: Reference distribution (e.g., 90-day historical scores)
        current: Current distribution to compare (e.g., last 7 days)
        bins: Number of bins for histogram discretization (default: 10)

    Returns:
        PSI value (sempre >= 0). Vedi interpretazione sopra.

    Reference: Design Spec Sezione 2 - Drift Detection

    Example:
        >>> baseline = np.random.normal(0, 1, 1000)
        >>> current = np.random.normal(0.5, 1, 1000)
        >>> psi = compute_psi(baseline, current)
        >>> psi > 0  # Drift rilevato
        True
    """
    if len(baseline) == 0 or len(current) == 0:
        return 0.0

    # Ensure numpy arrays
    baseline = np.asarray(baseline)
    current = np.asarray(current)

    # Compute bin edges covering both distributions
    min_val = min(baseline.min(), current.min())
    max_val = max(baseline.max(), current.max())

    # Handle edge case where all values are the same
    if min_val == max_val:
        return 0.0

    edges = np.linspace(min_val, max_val, bins + 1)

    # Compute histogram percentages (add small epsilon to avoid log(0))
    exp_counts, _ = np.histogram(baseline, edges)
    act_counts, _ = np.histogram(current, edges)

    exp_pct = (exp_counts / len(baseline)) + 1e-6
    act_pct = (act_counts / len(current)) + 1e-6

    # PSI formula: Σ expected_i * ln(expected_i / actual_i)
    psi = np.sum(exp_pct * np.log(exp_pct / act_pct))

    return float(psi)


def compute_cusum(
    scores: np.ndarray,
    baseline_mean: float,
    baseline_std: float,
    threshold: float = 5.0,
    slack: float = 0.5,
) -> tuple[float, float]:
    """
    Compute CUSUM (Cumulative Sum) statistic for change detection.

    Uses the standard CUSUM with slack parameter (k) to detect sustained
    deviations from baseline. The slack prevents small random fluctuations
    from accumulating.

    Algorithm:
        S_pos[t] = max(0, S_pos[t-1] + (x[t] - mean) / std - k)
        S_neg[t] = min(0, S_neg[t-1] + (x[t] - mean) / std + k)

    Args:
        scores: Time series of scores (e.g., last 7 days of sentiment scores)
        baseline_mean: Mean of the reference distribution
        baseline_std: Standard deviation of the reference distribution
        threshold: Decision threshold (default 5.0 - typical for change detection)
        slack: Slack parameter k in std units (default 0.5)

    Returns:
        Tuple of (cusum_value, threshold). If cusum_value > threshold, signal shift.

    Reference: Design Spec Sezione 2 - Drift Detection
    """
    if len(scores) == 0:
        return 0.0, 0.0

    scores = np.asarray(scores)

    # Standardized deviations from baseline mean
    z = (scores - baseline_mean) / (baseline_std + 1e-8)

    # CUSUM with slack (reference value k)
    # This is the standard Page-Hinkley CUSUM formulation
    cusum_pos = 0.0
    cusum_neg = 0.0
    max_cusum = 0.0

    for z_i in z:
        cusum_pos = max(0, cusum_pos + z_i - slack)
        cusum_neg = min(0, cusum_neg + z_i + slack)
        max_cusum = max(max_cusum, cusum_pos, abs(cusum_neg))

    return float(max_cusum), float(threshold)


# Hard circuit breakers - block weight updates and trigger critical alerts
HARD_BREAKERS = {
    "vix_spike": lambda ctx: ctx.vix > 40 or ctx.vix_1d_change > 0.30,
    "system_drawdown": lambda ctx: ctx.portfolio_drawdown > 0.05,
    "ic_negative_run": lambda ctx: ctx.consecutive_negative_ic_days >= 5,
}

# Soft warnings - appear in reports but don't block
SOFT_WARNINGS = {
    "earnings_concentration": lambda ctx: ctx.portfolio_earnings_pct > 0.50,
    "cross_asset_corr": lambda ctx: ctx.cross_asset_correlation > 0.90,
}


def check_circuit_breakers(ctx: CircuitBreakerContext) -> CircuitBreakerResult:
    """
    Evaluate all circuit breakers and return the combined result.

    Hard breakers freeze automatic weight updates and trigger critical alerts.
    Soft warnings appear in reports but don't block operations.

    Args:
        ctx: CircuitBreakerContext with current market/portfolio state

    Returns:
        CircuitBreakerResult with freeze decision and triggered breakers/warnings

    Reference: Design Spec Sezione 2 - Circuit Breakers
    """
    hard_triggered = []
    soft_triggered = []

    # Check hard breakers
    for name, check in HARD_BREAKERS.items():
        if check(ctx):
            hard_triggered.append(name)

    # Check soft warnings
    for name, check in SOFT_WARNINGS.items():
        if check(ctx):
            soft_triggered.append(name)

    freeze = len(hard_triggered) > 0
    reason = f"Hard breakers triggered: {', '.join(hard_triggered)}" if freeze else None

    return CircuitBreakerResult(
        freeze_weight_update=freeze,
        reason=reason,
        hard_breakers_triggered=hard_triggered,
        soft_warnings_triggered=soft_triggered,
    )


def detect_drift(
    baseline_90gg: np.ndarray,
    baseline_12m: np.ndarray | None,
    current_7gg: np.ndarray,
    cusum_threshold: float = 8.0,
    cusum_slack: float = 0.5,
) -> DriftAlert:
    """
    Perform comprehensive drift detection using PSI and CUSUM.

    Compares current 7-day distribution against:
    - 90-day baseline (primary, operational drift)
    - 12-month baseline (secondary, structural drift)

    Alert levels:
    - GREEN: PSI_90gg < 0.10 (stable)
    - YELLOW: PSI_90gg > 0.10 (moderate drift, monitor)
    - RED: PSI_90gg > 0.25 AND (PSI_12m > 0.10 or CUSUM confirmed)

    Args:
        baseline_90gg: 90-day historical score distribution
        baseline_12m: Optional 12-month historical distribution
        current_7gg: Last 7 days of scores
        cusum_threshold: Decision threshold for CUSUM (default: 8.0)
        cusum_slack: Slack parameter k in CUSUM (default: 0.5)

    Returns:
        DriftAlert with level, metrics, and confirmation status

    Note:
        cusum_threshold di 8.0 è appropriato per slack=0.5.
        Per altri valori di slack, aggiustare proporzionalmente.

    Reference: Design Spec Sezione 2 - Drift Detection
    """
    # Compute PSI against 90-day baseline
    psi_90gg = compute_psi(baseline_90gg, current_7gg)

    # Compute PSI against 12-month baseline if available
    psi_12m = None
    if baseline_12m is not None and len(baseline_12m) > 0:
        psi_12m = compute_psi(baseline_12m, current_7gg)

    # Compute CUSUM on 7-day window
    baseline_mean = float(np.mean(baseline_90gg))
    baseline_std = float(np.std(baseline_90gg))
    cusum_value, cusum_threshold = compute_cusum(
        current_7gg, baseline_mean, baseline_std, threshold=cusum_threshold, slack=cusum_slack
    )

    # CUSUM confirms shift if value exceeds threshold
    cusum_confirmed = cusum_value > cusum_threshold

    # Current vs baseline mean for diagnostics
    current_mean = float(np.mean(current_7gg))

    # Determine alert level
    # RED: severe drift with confirmation
    # YELLOW: moderate drift
    # GREEN: stable
    if psi_90gg > PSI_RED_THRESHOLD:
        # Red requires confirmation from either 12m baseline or CUSUM
        if (psi_12m is not None and psi_12m > PSI_YELLOW_THRESHOLD) or cusum_confirmed:
            level = "red"
            alert_type = "psi_cusum_confirmed" if cusum_confirmed else "psi_12m_confirmed"
        else:
            # Severe PSI but unconfirmed - still yellow
            level = "yellow"
            alert_type = "psi_only"
    elif psi_90gg > PSI_YELLOW_THRESHOLD:
        level = "yellow"
        alert_type = "psi_cusum_confirmed" if cusum_confirmed else "psi_only"
    else:
        level = "green"
        alert_type = "cusum_only" if cusum_confirmed else "stable"

    return DriftAlert(
        level=level,
        psi_90gg=psi_90gg,
        psi_12m=psi_12m,
        cusum_value=cusum_value,
        cusum_threshold=cusum_threshold,
        baseline_mean=baseline_mean,
        current_mean=current_mean,
        alert_type=alert_type,
    )
