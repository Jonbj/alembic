"""S2 strategy configuration."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class S2Config:
    target_delta: float = -0.20
    delta_tolerance: float = 0.05
    min_dte: int = 30
    max_dte: int = 45
    min_open_interest: int = 100
    min_volume: int = 10
    max_collateral_pct: float = 0.20
    vrp_entry_threshold: float = 0.0
