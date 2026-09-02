"""Portfolio status and cycle history API routes."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from src.api.auth import require_api_key
from src.api.deps import get_pg_store
from src.strategies.promotion import GLOBAL_LIVE_PROMOTION_ENABLED
from src.strategies.registry import StrategyRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portfolio", tags=["portfolio"], dependencies=[Depends(require_api_key)])


def _fetch_lifecycle_fields(strategy_ids: list[str], pg) -> dict[str, dict]:
    """Query strategy_lifecycle for mode and approved. Fail-open: returns {} on error."""
    try:
        conn = pg._get_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT strategy_id, mode, approved FROM strategy_lifecycle "
                "WHERE strategy_id = ANY(%s)",
                (strategy_ids,),
            )
            rows = cur.fetchall()
        result: dict[str, dict] = {}
        for row in rows:
            # Support both dict-like (RealDictCursor) and tuple rows
            if hasattr(row, "keys"):
                sid, mode, approved = row["strategy_id"], row["mode"], row["approved"]
            else:
                sid, mode, approved = row[0], row[1], row[2]
            result[sid] = {"mode": mode, "approved": bool(approved)}
        return result
    except Exception as exc:
        logger.warning("Could not fetch lifecycle fields: %s — mode/approved will be null", exc)
        return {}


def _live_authorized(mode: str | None) -> bool:
    """True only when the strategy is in 'live' mode AND the global promotion flag is on.

    Fail-closed by construction: an unknown mode (DB unreachable, missing lifecycle
    row) is not 'live', so the answer is False. Never returns True by omission —
    the frontend renders "live_authorized: false" from this, and a display that
    guesses "authorized" when it cannot tell is the one failure mode that matters.
    """
    return mode == "live" and GLOBAL_LIVE_PROMOTION_ENABLED


@router.get("/status")
async def portfolio_status(pg=Depends(get_pg_store)):
    """Return current portfolio status: active strategies, allocations, last cycle.

    Each strategy entry includes mode and approved from strategy_lifecycle
    (null if DB unavailable — fail-open so the status endpoint always responds).
    """
    registry = StrategyRegistry()
    active = registry.get_active_strategies()

    # Fetch governance fields from DB (fail-open: null on error)
    lifecycle = _fetch_lifecycle_fields([e.strategy_id for e in active], pg)

    strategies = [
        {
            "strategy_id": e.strategy_id,
            "allocation_pct": e.allocation_pct,
            "schedule": e.schedule,
            "enabled": e.enabled,
            "mode": lifecycle.get(e.strategy_id, {}).get("mode"),
            "approved": lifecycle.get(e.strategy_id, {}).get("approved"),
            # Governance flags, added 2026-09-02 when the Strategies page was removed
            # and this endpoint became the only authorization surface. Both are derived
            # from real sources — config/strategies.yaml and the lifecycle row — never
            # from a hardcoded snapshot, which is exactly what the deleted page did.
            "promotion_blocked": bool(e.promotion_blocked),
            "live_authorized": _live_authorized(lifecycle.get(e.strategy_id, {}).get("mode")),
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
