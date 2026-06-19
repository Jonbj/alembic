"""Operator safety cockpit: derives system state from the StrategyRegistry SoT.

All fields are read from the live registry — no hardcoded strategy lists.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.strategies.registry import StrategyRegistry


def get_cockpit_status(registry: "StrategyRegistry") -> dict:
    """Return a cockpit status snapshot derived entirely from the live registry.

    Args:
        registry: The active StrategyRegistry instance (single source of truth).

    Returns:
        Dict with:
          - ``strategies``: list of dicts, one per active (enabled) strategy,
            containing strategy_id, mode, allocation_pct, schedule, enabled.
          - ``total_allocation``: sum of enabled strategy allocations.
    """
    active = registry.get_active_strategies()
    strategies = [
        {
            "strategy_id": entry.strategy_id,
            "mode": entry.mode,
            "allocation_pct": entry.allocation_pct,
            "schedule": entry.schedule,
            "enabled": entry.enabled,
        }
        for entry in active
    ]
    return {
        "strategies": strategies,
        "total_allocation": round(sum(s["allocation_pct"] for s in strategies), 4),
    }
