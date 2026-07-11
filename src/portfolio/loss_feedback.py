"""Per-strategy, risk-normalized loss feedback.

Decouples the S1 and S4 loss-feedback ratchets so a loss in S1 does not poison
S4's entry threshold. Replaces count-based triggering with an EWMA of R-multiples:
R = net_pnl / (d_init * entry_notional).

This module is pure logic: no Redis I/O, no DB I/O. Callers pass trades and config.
"""
from __future__ import annotations

from dataclasses import dataclass


# Exit reasons that should teach the loss-feedback ratchet.
TEACHING_EXIT_REASONS = {"stop_loss", "portfolio_sell"}


def strategy_for_trade(trade: dict) -> str:
    """Return the strategy sleeve for a closed trade.

    Uses the frozen stop_strategy persisted on the trade row (Phase 3+). Falls back
    to the same origin derivation as the Trace panel: S4 if signal-driven, S1 else.
    """
    strat = trade.get("stop_strategy")
    if strat:
        return strat
    return "S4" if trade.get("signal_id") is not None else "S1"


def risk_budget_at_entry(trade: dict, default_stop_pct: float = 0.02) -> float:
    """Return the $ risk budget frozen at entry: d_init * entry_notional.

    For pre-migration trades without stop_d_init, fall back to the legacy fixed stop.
    """
    notional = float(trade.get("entry_notional") or 0.0)
    if notional <= 0:
        return 0.0
    d_init = trade.get("stop_d_init")
    if d_init is None or d_init <= 0:
        d_init = default_stop_pct
    return notional * float(d_init)


def r_multiple(trade: dict) -> float:
    """R-multiple for a trade: net_pnl / risk_budget_at_entry.

    Returns 0.0 when the budget cannot be determined (e.g. missing notional).
    """
    budget = risk_budget_at_entry(trade)
    if budget <= 0:
        return 0.0
    net_pnl = float(trade.get("net_pnl") or 0.0)
    return net_pnl / budget


def _is_teaching_trade(trade: dict) -> bool:
    return trade.get("exit_reason") in TEACHING_EXIT_REASONS


@dataclass(frozen=True)
class FeedbackOutcome:
    """Result of a per-strategy feedback evaluation."""

    strategy: str
    triggered: bool
    ewma_r: float
    consecutive_losses: int
    consecutive_wins: int
    rolling_net_pnl: float
    reason: str


def update_ewma_r(old_ewma: float | None, new_r: float, alpha: float = 0.3) -> float:
    """One-step EWMA update for R-multiples."""
    if old_ewma is None:
        return new_r
    return alpha * new_r + (1.0 - alpha) * old_ewma


def evaluate_strategy_feedback(
    trades: list[dict],
    strategy: str,
    ewma_r_prior: float | None = None,
    trigger_band: float = -0.5,
    recovery_band: float = 0.5,
    alpha: float = 0.3,
) -> FeedbackOutcome:
    """Evaluate loss feedback for one strategy sleeve.

    Uses the most recent teaching trades for this strategy (already limited by the
    caller's lookback). Trigger fires when the EWMA of R drops below trigger_band.
    Recovery fires when EWMA of R rises above recovery_band and the most recent
    teaching trades are wins.

    Args:
        trades: Closed trades for this strategy, most-recent first.
        strategy: Strategy key ("S1", "S4", etc.).
        ewma_r_prior: Previously persisted EWMA of R for this strategy, if any.
        trigger_band: EWMA R threshold for raising the gate (negative).
        recovery_band: EWMA R threshold for stepping the gate back down.
        alpha: EWMA decay factor.
    """
    teaching = [t for t in trades if _is_teaching_trade(t)]

    # Consecutive loss/win counts over the most-recent teaching trades only.
    consecutive_losses = 0
    consecutive_wins = 0
    for t in teaching:
        net_pnl = float(t.get("net_pnl") or 0.0)
        if net_pnl < 0:
            consecutive_losses += 1
            consecutive_wins = 0
        elif net_pnl > 0:
            consecutive_wins += 1
            consecutive_losses = 0
        else:
            break

    rolling_net_pnl = sum(float(t.get("net_pnl") or 0.0) for t in teaching)

    # Update EWMA of R from most-recent to oldest so later trades have more weight.
    ewma_r = ewma_r_prior
    for t in reversed(teaching):
        ewma_r = update_ewma_r(ewma_r, r_multiple(t), alpha)
    ewma_r = ewma_r if ewma_r is not None else 0.0

    triggered = ewma_r <= trigger_band or consecutive_losses >= 3
    reason_parts: list[str] = []
    if ewma_r <= trigger_band:
        reason_parts.append(f"EWMA R {ewma_r:.2f} <= {trigger_band}")
    if consecutive_losses >= 3:
        reason_parts.append(f"{consecutive_losses} consecutive losses")
    reason = " + ".join(reason_parts) if reason_parts else "none"

    return FeedbackOutcome(
        strategy=strategy,
        triggered=triggered,
        ewma_r=round(ewma_r, 4),
        consecutive_losses=consecutive_losses,
        consecutive_wins=consecutive_wins,
        rolling_net_pnl=round(rolling_net_pnl, 2),
        reason=reason,
    )
