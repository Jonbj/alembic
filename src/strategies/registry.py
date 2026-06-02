"""StrategyRegistry: central registry for active trading strategies.

Default configuration (from portfolio design):
    S1 (TimeSeriesMomentum)  — 50% allocation
    S2 (VRPStrategy)         — 20% allocation
    S4 (NewsDrivenTactical)  — 30% allocation
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

# Weekday market-open cron: 9:30 AM ET = 14:30 UTC
_DEFAULT_SCHEDULE = "30 14 * * 1-5"


@dataclass
class StrategyEntry:
    """Metadata for a registered strategy.

    Args:
        strategy_id:    Unique identifier (e.g. "S1").
        strategy_class: Strategy class or callable instance.
        allocation_pct: Target portfolio allocation (0–1).
        schedule:       5-field cron expression for Celery beat.
        enabled:        Whether this strategy participates in live cycles.
    """
    strategy_id: str
    strategy_class: Any
    allocation_pct: float
    schedule: str
    enabled: bool = True


class StrategyRegistry:
    """Central registry of active strategies with allocation weights.

    Args:
        load_defaults: When True (default), pre-populates S1/S2/S4 entries.
                       Pass False to get an empty registry (useful in tests).
    """

    def __init__(self, load_defaults: bool = True) -> None:
        self._entries: dict[str, StrategyEntry] = {}
        if load_defaults:
            self._load_defaults()

    # ── Public API ─────────────────────────────────────────────────────────────

    def register(self, entry: StrategyEntry) -> None:
        """Add a strategy entry. Raises ValueError if strategy_id already exists."""
        if entry.strategy_id in self._entries:
            raise ValueError(
                f"Strategy '{entry.strategy_id}' already registered. "
                "Use set_enabled() to toggle or reload() to reset."
            )
        self._entries[entry.strategy_id] = entry

    def get_strategy(self, strategy_id: str) -> StrategyEntry:
        """Return a single entry by ID. Raises KeyError if not found."""
        if strategy_id not in self._entries:
            raise KeyError(f"Strategy '{strategy_id}' not registered")
        return self._entries[strategy_id]

    def get_active_strategies(self) -> list[StrategyEntry]:
        """Return all enabled strategy entries."""
        return [e for e in self._entries.values() if e.enabled]

    def get_strategy_ids(self) -> list[str]:
        """Return all registered strategy IDs (enabled and disabled)."""
        return list(self._entries.keys())

    def set_enabled(self, strategy_id: str, enabled: bool) -> None:
        """Enable or disable a strategy without removing it."""
        entry = self.get_strategy(strategy_id)
        self._entries[strategy_id] = StrategyEntry(
            strategy_id=entry.strategy_id,
            strategy_class=entry.strategy_class,
            allocation_pct=entry.allocation_pct,
            schedule=entry.schedule,
            enabled=enabled,
        )

    def reload(self) -> None:
        """Reset registry to default S1/S2/S4 configuration."""
        self._entries.clear()
        self._load_defaults()

    # ── Private ────────────────────────────────────────────────────────────────

    def _load_defaults(self) -> None:
        from src.strategies.s1.strategy import TimeSeriesMomentum
        from src.strategies.s2.strategy import VRPStrategy
        from src.strategies.s4.strategy import NewsDrivenTactical

        defaults = [
            StrategyEntry(
                strategy_id="S1",
                strategy_class=TimeSeriesMomentum,
                allocation_pct=0.50,
                schedule=_DEFAULT_SCHEDULE,
                enabled=True,
            ),
            StrategyEntry(
                strategy_id="S2",
                strategy_class=VRPStrategy,
                allocation_pct=0.20,
                schedule=_DEFAULT_SCHEDULE,
                enabled=True,
            ),
            StrategyEntry(
                strategy_id="S4",
                strategy_class=NewsDrivenTactical,
                allocation_pct=0.30,
                schedule=_DEFAULT_SCHEDULE,
                enabled=True,
            ),
        ]
        for entry in defaults:
            self._entries[entry.strategy_id] = entry
        log.debug("StrategyRegistry loaded defaults: %s", list(self._entries.keys()))
