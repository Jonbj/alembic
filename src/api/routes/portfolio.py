"""Portfolio status and cycle history API routes."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from src.api.deps import get_pg_store
from src.strategies.registry import StrategyRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/status")
async def portfolio_status(pg=Depends(get_pg_store)):
    """Return current portfolio status: active strategies, allocations, last cycle."""
    registry = StrategyRegistry()
    active = registry.get_active_strategies()

    strategies = [
        {
            "strategy_id": e.strategy_id,
            "allocation_pct": e.allocation_pct,
            "schedule": e.schedule,
            "enabled": e.enabled,
        }
        for e in active
    ]

    last_cycle = None
    try:
        row = pg.get_last_portfolio_cycle()
        if row:
            last_cycle = {
                "timestamp": row.get("timestamp"),
                "strategies_run": row.get("strategies_run", []),
                "orders_count": row.get("orders_count", 0),
                "constraints_fired": row.get("constraints_fired", []),
            }
    except Exception:
        logger.warning("Could not fetch last portfolio cycle", exc_info=True)

    return {
        "active_strategies": len(active),
        "strategies": strategies,
        "last_cycle": last_cycle,
    }


@router.get("/cycle-history")
async def portfolio_cycle_history(limit: int = 30, pg=Depends(get_pg_store)):
    """Return last N portfolio cycle results."""
    try:
        rows = pg.get_portfolio_cycle_history(limit=limit) or []
        return [
            {
                "timestamp": r.get("timestamp"),
                "strategies_run": r.get("strategies_run", []),
                "orders_count": r.get("orders_count", 0),
                "constraints_fired": r.get("constraints_fired", []),
                "final_orders": r.get("final_orders", []),
            }
            for r in rows
        ]
    except Exception:
        logger.warning("Could not fetch cycle history", exc_info=True)
        return []
