"""Operator safety cockpit: derives system state from the StrategyRegistry SoT.

All fields are read from the live registry — no hardcoded strategy lists.
"""
from __future__ import annotations

from datetime import datetime, timezone
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


def get_cockpit_alerts(
    pg,
    redis_client,
    beat_threshold_minutes: float = 60.0,
    staleness_hours: float = 2.0,
) -> dict:
    """Aggregate operator alert flags into a single health dict.

    Args:
        pg:                     PostgreSQLStore instance (uses _get_connection()).
        redis_client:           Raw Redis client (redis.Redis).
        beat_threshold_minutes: Flag worker_beat_lag when last cycle older than this.
        staleness_hours:        Flag stale_signals when last signal older than this.

    Returns:
        Dict with redis_healthy, redis_writeable, db_healthy, killswitch_active,
        stale_signals, worker_beat_lag, last_signal_age_minutes, last_cycle_age_minutes.
    """
    redis_healthy = False
    redis_writeable = False
    killswitch_active = False
    try:
        redis_client.ping()
        redis_healthy = True
        try:
            redis_client.set("readiness:ping", "1", ex=5)
            redis_writeable = True
        except Exception:
            pass
        try:
            killswitch_active = bool(redis_client.get("killswitch_active"))
        except Exception:
            pass
    except Exception:
        pass

    db_healthy = False
    last_signal_age_minutes: float | None = None
    last_cycle_age_minutes: float | None = None
    stale_signals = True
    worker_beat_lag = True
    try:
        conn = pg._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT MAX(generated_at) FROM sentiment_signals")
        row = cur.fetchone()
        last_signal_ts = row[0] if row else None
        cur.execute("SELECT MAX(timestamp) FROM portfolio_cycles")
        row = cur.fetchone()
        last_cycle_ts = row[0] if row else None
        db_healthy = True

        now = datetime.now(timezone.utc)
        if last_signal_ts is not None:
            if hasattr(last_signal_ts, "tzinfo") and last_signal_ts.tzinfo is None:
                last_signal_ts = last_signal_ts.replace(tzinfo=timezone.utc)
            last_signal_age_minutes = (now - last_signal_ts).total_seconds() / 60.0
            stale_signals = last_signal_age_minutes > staleness_hours * 60
        if last_cycle_ts is not None:
            if hasattr(last_cycle_ts, "tzinfo") and last_cycle_ts.tzinfo is None:
                last_cycle_ts = last_cycle_ts.replace(tzinfo=timezone.utc)
            last_cycle_age_minutes = (now - last_cycle_ts).total_seconds() / 60.0
            worker_beat_lag = last_cycle_age_minutes > beat_threshold_minutes
    except Exception:
        db_healthy = False

    return {
        "redis_healthy": redis_healthy,
        "redis_writeable": redis_writeable,
        "db_healthy": db_healthy,
        "killswitch_active": killswitch_active,
        "stale_signals": stale_signals,
        "worker_beat_lag": worker_beat_lag,
        "last_signal_age_minutes": last_signal_age_minutes,
        "last_cycle_age_minutes": last_cycle_age_minutes,
    }
