"""S4 strategy configuration."""
from __future__ import annotations

from dataclasses import dataclass, field

from src.backtest.engine.types import RebalanceFrequency


@dataclass
class S4Config:
    strategy_id: str = "S4"
    n_top: int = 5
    bucket_pct: float = 0.10
    min_confidence: float = 0.3
    min_score: float = 0.1
    min_stocks: int = 3
    signals_lookback_hours: int = 4
    rebalance_frequency: RebalanceFrequency = field(
        default=RebalanceFrequency.WEEKLY
    )
