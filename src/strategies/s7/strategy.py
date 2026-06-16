"""PEADStrategy: allocates to earnings-beat stocks within hold period."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.models.pead import SurpriseSignal


@dataclass
class PEADConfig:
    """Configuration for the S7 PEAD sleeve."""

    max_position_pct: float = 0.05
    max_sleeve_pct: float = 0.25
    min_confidence: float = 0.70
    surprise_threshold: float = 0.05
    hold_days: int = 20
    strategy_id: str = "S7"


class PEADStrategy:
    """S7: Post-Earnings Announcement Drift long-only sleeve.

    Allocates equal weight to active beat signals up to position and sleeve caps.
    Miss signals are not allocated; they serve as a trigger for exit in the caller.
    """

    def __init__(self, config: PEADConfig | None = None) -> None:
        self._cfg = config or PEADConfig()

    def compute_target_weights(
        self,
        signals: list[SurpriseSignal],
        as_of: datetime | None = None,
    ) -> dict[str, float]:
        """Return {symbol: weight} for active beat signals within sleeve constraints.

        Only "beat" signals that are:
        - still within hold period
        - above min_confidence

        are included. Weights are capped at max_position_pct, total sleeve
        capped at max_sleeve_pct.
        """
        ts = as_of or datetime.now(timezone.utc)
        cfg = self._cfg

        eligible: list[SurpriseSignal] = [
            s for s in signals
            if s.direction == "beat"
            and s.confidence >= cfg.min_confidence
            and s.is_active(as_of=ts)
        ]

        if not eligible:
            return {}

        weights: dict[str, float] = {}
        sleeve_used = 0.0

        for sig in eligible:
            if sleeve_used >= cfg.max_sleeve_pct:
                break
            alloc = min(cfg.max_position_pct, cfg.max_sleeve_pct - sleeve_used)
            if alloc <= 0:
                break
            weights[sig.symbol] = alloc
            sleeve_used += alloc

        return weights
