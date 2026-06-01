"""S2 strategy: regime modulation overlay.

Maps a RegimeLabel to a position scale factor and optionally applies it to a
PutSignal, scaling quantity down by floor(quantity * scale).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import floor
from typing import Optional

from src.models.regime import RegimeLabel
from src.strategies.s2.config import S2Config
from src.strategies.s2.signal import PutSignal

_REASONS: dict[str, str] = {
    "bull": "VRP selling works well in calm/uptrend; full position",
    "sideways": "Moderate risk, contango typical; slightly reduced position",
    "bear": "High volatility, risk of sharp moves against short puts; significantly reduced",
    "high_vol": "Extreme risk; no new positions allowed",
}


@dataclass
class RegimeModulation:
    regime: RegimeLabel
    position_scale: float
    reason: str


def modulate_by_regime(
    regime: RegimeLabel,
    config: Optional[S2Config] = None,
) -> RegimeModulation:
    """Return the position scale for the given regime.

    Uses config.regime_scales when provided, otherwise S2Config defaults.
    """
    cfg = config or S2Config()
    scale = cfg.regime_scales[regime]
    return RegimeModulation(regime=regime, position_scale=scale, reason=_REASONS[regime])


def apply_regime_scale(
    signal: PutSignal,
    modulation: RegimeModulation,
) -> Optional[PutSignal]:
    """Apply regime scale to a PutSignal.

    Returns None when scale is 0.0 or when floor(quantity * scale) < 1.
    Otherwise returns a new PutSignal with quantity and collateral updated.
    """
    if modulation.position_scale == 0.0:
        return None
    new_qty = floor(signal.quantity * modulation.position_scale)
    if new_qty < 1:
        return None
    return replace(
        signal,
        quantity=new_qty,
        collateral=signal.strike * new_qty * 100,
    )
