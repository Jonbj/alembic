"""S4 strategy configuration."""
from __future__ import annotations

from dataclasses import dataclass, field

from src.backtest.engine.types import RebalanceFrequency


@dataclass
class S4Config:
    strategy_id: str = "S4"
    n_top: int = 5
    bucket_pct: float = 0.10
    # min_score / min_confidence are RANKER PREFILTERS, not the order threshold. The live
    # order gate is feedback:entry_threshold (baseline 0.30, raised dynamically by the
    # loss-feedback loop, enforced in portfolio_scheduler). See docs/strategies.md
    # §"Signal Logic (live = portfolio path)" — Threshold map.
    min_confidence: float = 0.3
    min_score: float = 0.1
    # The live entry gate (feedback:entry_threshold) is enforced upstream in the
    # portfolio scheduler. By the time signals reach the ranker they have already
    # passed the gate, so requiring >1 stock here would silently discard a lone
    # survivor and choke capital deployment.
    min_stocks: int = 1
    # #81: when True, each selected ticker gets a FIXED weight of 1/n_top,
    # regardless of how many candidates actually passed the gate that cycle —
    # unused slots stay undeployed instead of being redistributed to the
    # survivors. Fixes the lone-survivor concentration bug (a single
    # gate-surviving ticker getting the full 10% sleeve bucket instead of its
    # 2% slot; real losses 2026-07-17 DB -$77.88, 2026-07-20 MSFT same
    # pattern). No effect when n_selected == n_top (the common case). ON by
    # default per explicit operator decision 2026-07-20 (real realized loss +
    # an identical live position exposed to the same risk at decision time) —
    # overrides this repo's usual off-by-default discipline, same as #62/#63.
    # Set False (or config/trading.yaml risk.s4_fixed_slot_sizing_enabled:
    # false) to roll back to the legacy formula.
    fixed_slot_sizing: bool = True
    signals_lookback_hours: int = 96  # covers 3-day US market holiday gap (Fri→Tue ≈ 88h)
    max_signal_age_hours: int = 4
    rebalance_frequency: RebalanceFrequency = field(
        default=RebalanceFrequency.DAILY
    )
