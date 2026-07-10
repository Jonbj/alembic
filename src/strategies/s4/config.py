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
    signals_lookback_hours: int = 96  # covers 3-day US market holiday gap (Fri→Tue ≈ 88h)
    max_signal_age_hours: int = 4
    rebalance_frequency: RebalanceFrequency = field(
        default=RebalanceFrequency.DAILY
    )
