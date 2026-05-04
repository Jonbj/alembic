"""Post-mortem analysis for losing trades.

Trigger logic (B5):
- loss_pct >= 0.03 (loss >= 3%)
- loss_pct >= 0.02 AND (|score| >= 0.5 OR ensemble_std >= 0.3)

Diagnosis categories (10 minimax):
- low_confidence_passed: confidence < threshold but signal used
- ensemble_divergence_ignored: high ensemble std, signal used anyway
- regime_mismatch: regime incompatible with signal direction
- news_staleness: old news at trade time
- market_gap: overnight event not anticipatable
- stop_too_tight: stop-loss hit by normal volatility
- correlated_portfolio_loss: cross-asset contagion
- model_drift_active: drift alert active at trade time
- threshold_boundary: score near 0.3 threshold (low conviction)
- unknown: no identifiable cause
"""

from dataclasses import dataclass
from typing import Literal


@dataclass
class TradeContext:
    """Context for diagnosing a losing trade."""

    loss_pct: float
    signal_score: float
    signal_confidence: float
    ensemble_std: float
    regime: str
    reasoning_summary: str
    signal_age_minutes: float = 0.0
    drift_alert_active: bool = False
    cross_asset_corr: float = 0.0
    stop_loss_pct: float = 0.02
    asset_volatility: float = 0.0
    was_overnight_gap: bool = False


# Confidence threshold below which signals should be filtered
CONFIDENCE_THRESHOLD = 0.4

# Score threshold for "conviction" trades
CONVICTION_SCORE_THRESHOLD = 0.5

# Ensemble std threshold for divergence
DIVERGENCE_STD_THRESHOLD = 0.3

# Signal staleness threshold (minutes)
SIGNAL_MAX_AGE_MIN = 30


def should_trigger_postmortem(
    loss_pct: float,
    score: float,
    ensemble_std: float,
) -> bool:
    """Determine if a loss should trigger post-mortem analysis.

    Trigger conditions (B5):
    - loss_pct >= 0.03 (loss >= 3%)
    - loss_pct >= 0.02 AND (|score| >= 0.5 OR ensemble_std >= 0.3)

    Args:
        loss_pct: Loss percentage as positive value (e.g., 0.03 for 3%)
        score: Signal score at trade entry [-1, +1]
        ensemble_std: Ensemble standard deviation at signal time

    Returns:
        True if post-mortem should be generated
    """
    if loss_pct >= 0.03:
        return True

    if loss_pct >= 0.02:
        if abs(score) >= CONVICTION_SCORE_THRESHOLD:
            return True
        if ensemble_std >= DIVERGENCE_STD_THRESHOLD:
            return True

    return False


def diagnose_loss(ctx: TradeContext) -> Literal[
    "low_confidence_passed",
    "ensemble_divergence_ignored",
    "regime_mismatch",
    "news_staleness",
    "market_gap",
    "stop_too_tight",
    "correlated_portfolio_loss",
    "model_drift_active",
    "threshold_boundary",
    "unknown",
]:
    """Diagnose the cause of a losing trade.

    Diagnosis priority (first match wins):
    1. market_gap: overnight gap events are external/unanticipatable
    2. model_drift_active: drift alert was active
    3. low_confidence_passed: confidence below threshold
    4. ensemble_divergence_ignored: high ensemble std
    5. regime_mismatch: regime vs signal direction mismatch
    6. news_staleness: signal too old
    7. correlated_portfolio_loss: high cross-asset correlation
    8. stop_too_tight: stop too tight for asset volatility
    9. threshold_boundary: score near decision boundary
    10. unknown: fallback

    Args:
        ctx: TradeContext with all relevant signals and context

    Returns:
        Diagnosis category string
    """
    # 1. Market gap - overnight events not anticipatable
    if ctx.was_overnight_gap:
        return "market_gap"

    # 2. Model drift active - drift alert was firing at trade time
    if ctx.drift_alert_active:
        return "model_drift_active"

    # 3. Low confidence passed - confidence below threshold but signal used
    if ctx.signal_confidence < CONFIDENCE_THRESHOLD:
        return "low_confidence_passed"

    # 4. Ensemble divergence ignored - high std but signal used
    if ctx.ensemble_std >= DIVERGENCE_STD_THRESHOLD:
        return "ensemble_divergence_ignored"

    # 5. Regime mismatch - regime incompatible with signal direction
    if _is_regime_mismatch(ctx.regime, ctx.signal_score):
        return "regime_mismatch"

    # 6. News staleness - signal too old at trade time
    if ctx.signal_age_minutes > SIGNAL_MAX_AGE_MIN:
        return "news_staleness"

    # 7. Correlated portfolio loss - cross-asset contagion
    if ctx.cross_asset_corr > 0.8:
        return "correlated_portfolio_loss"

    # 8. Stop too tight - stop-loss hit by normal volatility
    if _is_stop_too_tight(ctx.stop_loss_pct, ctx.asset_volatility, ctx.loss_pct):
        return "stop_too_tight"

    # 9. Threshold boundary - score near 0.3 (low conviction zone)
    if _is_threshold_boundary(ctx.signal_score):
        return "threshold_boundary"

    # 10. Unknown - no identifiable cause
    return "unknown"


def _is_regime_mismatch(regime: str, signal_score: float) -> bool:
    """Check if regime is incompatible with signal direction.

    Risk-off regimes should not have strong long signals.
    High vol regimes should not have high-conviction signals.

    Args:
        regime: Regime label at trade time
        signal_score: Signal score [-1, +1]

    Returns:
        True if regime/signal combination is suspicious
    """
    # Strong bullish signal in risk_off regime
    if regime == "risk_off" and signal_score > 0.5:
        return True

    # Strong bearish signal in risk_on regime
    if regime == "risk_on" and signal_score < -0.5:
        return True

    # High conviction signal in uncertain regime
    if regime == "uncertain" and abs(signal_score) > 0.6:
        return True

    # Any directional signal in high_vol regime
    if regime == "high_vol" and abs(signal_score) > 0.4:
        return True

    return False


def _is_stop_too_tight(
    stop_loss_pct: float,
    asset_volatility: float,
    loss_pct: float,
) -> bool:
    """Check if stop-loss was too tight for asset's normal volatility.

    Stop is "too tight" if:
    - Asset's typical daily range > 2x stop-loss
    - Loss was just beyond stop (not a major move)

    Args:
        stop_loss_pct: Configured stop-loss percentage
        asset_volatility: Asset's typical daily volatility (e.g., ATR/price)
        loss_pct: Actual loss percentage

    Returns:
        True if stop was likely too tight
    """
    if asset_volatility <= 0:
        return False

    # If asset's normal daily move is > 2x the stop, stop is too tight
    if asset_volatility > stop_loss_pct * 2:
        # And loss was close to stop (not a gap or major move)
        if loss_pct <= stop_loss_pct * 1.5:
            return True

    return False


def _is_threshold_boundary(score: float) -> bool:
    """Check if score is near the decision threshold (low conviction zone).

    Threshold boundary zone: |score| in [0.25, 0.35]
    This is the "fence" area where the model is uncertain.

    Args:
        score: Signal score [-1, +1]

    Returns:
        True if score is in boundary zone
    """
    abs_score = abs(score)
    return 0.25 <= abs_score <= 0.35
