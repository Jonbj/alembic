"""Per-strategy, risk-normalized loss feedback.

Decouples the S1 and S4 loss-feedback ratchets so a loss in S1 does not poison
S4's entry threshold. Replaces count-based triggering with an EWMA of R-multiples:
R = net_pnl / (d_init * entry_notional).

This module is pure logic: no Redis I/O, no DB I/O. Callers pass trades and config.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


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


def _is_teaching_trade(exit_reason: str | None) -> bool:
    return exit_reason in TEACHING_EXIT_REASONS


def update_ewma_r(old_ewma: float | None, new_r: float, alpha: float = 0.3) -> float:
    """One-step EWMA update for R-multiples."""
    if old_ewma is None:
        return new_r
    return alpha * new_r + (1.0 - alpha) * old_ewma


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


@dataclass
class LossFeedback:
    """Stateful per-strategy loss-feedback ratchet.

    Usage:
        fb = LossFeedback(config)
        fb.record_exit("S1", "stop_loss", net_pnl=-40, risk_budget=20)
        outcome = fb.evaluate("S1")
        threshold = fb.threshold("S1")
    """

    config: dict
    # strategy -> list of recorded exits in chronological order
    _history: dict[str, list[dict]] = field(default_factory=dict)
    # strategy -> EWMA of R after the most recent teaching exit
    _ewma_r: dict[str, float | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Ensure default config values are present."""
        defaults = {
            "threshold_baseline": 0.30,
            "threshold_max": 0.60,
            "threshold_step": 0.05,
            "regime_scale_factor": 0.80,
            "regime_min_scale": 0.20,
            "ewma_alpha": 0.30,
            "trigger_band": -0.50,
            "recovery_band": 0.50,
            "consecutive_loss_trigger": 3,
            "recovery_win_streak": 3,
        }
        merged = {**defaults, **self.config}
        self.config = merged

    def record_exit(
        self,
        strategy: str,
        exit_reason: str,
        net_pnl: float,
        risk_budget: float,
    ) -> None:
        """Record one closed trade exit for the strategy sleeve.

        Only TEACHING_EXIT_REASONS affect the ratchet; others are ignored.
        """
        if not _is_teaching_trade(exit_reason):
            return
        if risk_budget <= 0:
            return
        r = net_pnl / risk_budget
        self._history.setdefault(strategy, []).append(
            {"net_pnl": net_pnl, "risk_budget": risk_budget, "r": r}
        )
        prior = self._ewma_r.get(strategy)
        self._ewma_r[strategy] = update_ewma_r(prior, r, self.config["ewma_alpha"])

    def evaluate(self, strategy: str) -> FeedbackOutcome:
        """Evaluate feedback state for one strategy after recorded exits."""
        history = self._history.get(strategy, [])

        # Consecutive loss/win counts over the most-recent teaching exits.
        consecutive_losses = 0
        consecutive_wins = 0
        for exit in reversed(history):
            pnl = exit["net_pnl"]
            if pnl < 0:
                if consecutive_wins > 0:
                    break
                consecutive_losses += 1
            elif pnl > 0:
                if consecutive_losses > 0:
                    break
                consecutive_wins += 1
            else:
                break

        rolling_net_pnl = sum(e["net_pnl"] for e in history)
        ewma_r = self._ewma_r.get(strategy)
        ewma_r = ewma_r if ewma_r is not None else 0.0

        trigger_band = self.config["trigger_band"]
        triggered = ewma_r <= trigger_band or consecutive_losses >= self.config["consecutive_loss_trigger"]

        reason_parts: list[str] = []
        if ewma_r <= trigger_band:
            reason_parts.append(f"EWMA R {ewma_r:.2f} <= {trigger_band}")
        if consecutive_losses >= self.config["consecutive_loss_trigger"]:
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

    def threshold(self, strategy: str) -> float:
        """Return the entry-threshold gate for a strategy.

        S1 has no discrete threshold gate today (continuous rebalance), so return 0.0.
        S4 returns the baseline.
        """
        if strategy == "S1":
            return 0.0
        return self.config["threshold_baseline"]

    def scale(self, _strategy: str) -> float:
        """Return the regime scale factor. Per-strategy scale is not used in v1."""
        return 1.0

    def state(self, strategy: str) -> dict:
        """Return serializable state for a strategy."""
        outcome = self.evaluate(strategy)
        return {
            "strategy": strategy,
            "ewma_r": outcome.ewma_r,
            "consecutive_losses": outcome.consecutive_losses,
            "consecutive_wins": outcome.consecutive_wins,
            "rolling_net_pnl": outcome.rolling_net_pnl,
            "triggered": outcome.triggered,
            "threshold": self.threshold(strategy),
        }

    def should_raise(self, strategy: str) -> bool:
        """True when the ratchet recommends raising the gate for this strategy."""
        return self.evaluate(strategy).triggered

    def should_recover(self, strategy: str) -> bool:
        """True when a win streak suggests lowering the gate."""
        outcome = self.evaluate(strategy)
        return (
            not outcome.triggered
            and outcome.consecutive_wins >= self.config["recovery_win_streak"]
        )


def evaluate_strategy_feedback(
    trades: list[dict],
    strategy: str,
    ewma_r_prior: float | None = None,
    trigger_band: float = -0.5,
    recovery_band: float = 0.5,
    alpha: float = 0.3,
) -> FeedbackOutcome:
    """Evaluate loss feedback for one strategy sleeve (legacy helper).

    Uses the most recent teaching trades for this strategy (already limited by the
    caller's lookback). Trigger fires when the EWMA of R drops below trigger_band.
    """
    fb = LossFeedback(
        {
            "trigger_band": trigger_band,
            "recovery_band": recovery_band,
            "ewma_alpha": alpha,
            "consecutive_loss_trigger": 3,
        }
    )
    if ewma_r_prior is not None:
        fb._ewma_r[strategy] = ewma_r_prior
    for t in trades:
        if _is_teaching_trade(t.get("exit_reason")):
            fb.record_exit(strategy, t.get("exit_reason", ""), t.get("net_pnl", 0.0), risk_budget_at_entry(t))
    return fb.evaluate(strategy)
