"""Anti-whipsaw damping for S4 weight-0 SELL exits (#61).

Scope: only the "whipsaw" exit_mechanism (#60) — a fresh weak/neutral
re-signal zeroing an S4 position. NOT sentiment_reversal (strong bearish,
a separate code path) and NOT "expired"/"no_signal" (legitimate exits) —
damping those would be worse than the whipsaw this is meant to prevent.

Evidence (#61): 230 historical S4 portfolio_sell exits — intraday
(same-day entry+exit) exits average -$0.77 (40.2% win rate) vs overnight+
exits average +$2.64 (30.5% win rate). The existing 90-min hold-minimum
guard only delays whipsaw exits, it doesn't prevent them (real NVDA/IBM
cases held 105min/165min, both past the guard).

Design: require N (default 2) CONSECUTIVE cycles classified "whipsaw" for
the same symbol before letting the SELL through — a single weak/neutral
re-signal holds one more cycle; a second consecutive one confirms the exit.
Flag-gated, off by default (config/trading.yaml risk.s4_anti_whipsaw_damping_enabled).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WhipsawDampingDecision:
    """suppress=True => hold, don't submit the SELL this cycle. new_streak persists."""

    suppress: bool
    new_streak: int


def evaluate_whipsaw_damping(
    is_whipsaw: bool,
    prior_streak: int,
    confirm_cycles: int = 2,
) -> WhipsawDampingDecision:
    """Decide whether to suppress a weight-0 SELL classified "whipsaw" this cycle."""
    if not is_whipsaw:
        return WhipsawDampingDecision(suppress=False, new_streak=0)
    streak = prior_streak + 1
    if streak >= confirm_cycles:
        return WhipsawDampingDecision(suppress=False, new_streak=0)
    return WhipsawDampingDecision(suppress=True, new_streak=streak)
