"""Periodic producer for the coherent mobile read model.

The task reads broker account/positions, market context, Redis safety state,
PostgreSQL health/activity, and strategy lifecycle data. It atomically replaces
the Redis mobile document and persists NAV history on the expected cadence or a
material state transition. It never submits or mutates trading decisions.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import asyncpg
from redis import Redis
from starlette.concurrency import run_in_threadpool

from src.api.dependencies import init_asyncpg_pool
from src.config import config
from src.mobile_monitoring.builder import MobileSnapshotBuilder
from src.mobile_monitoring.read_model import (
    MobileReadBundle,
    MobileReadModelStore,
    RedisMobileReadModelStore,
)
from src.portfolio.spy import fetch_spy_closes
from src.store.redis_store import RedisStore
from src.workers._async_utils import run_async
from src.workers.celery_app import app

logger = logging.getLogger(__name__)
_MOBILE_PERFORMANCE_PERIOD_DAYS = (7, 30, 90, 180, 365)


def _warm_mobile_spy_cache(redis: Redis, as_of: datetime) -> None:
    """Populate broker-backed SPY ranges from the worker, never an HTTP request."""
    to_date = as_of.date().isoformat()
    for days in _MOBILE_PERFORMANCE_PERIOD_DAYS:
        from_date = (as_of - timedelta(days=days)).date().isoformat()
        fetch_spy_closes(from_date, to_date, redis)


def _material_state_signature(bundle: MobileReadBundle) -> tuple[object, ...]:
    snapshot = bundle.snapshot
    return (
        snapshot.operational.state,
        snapshot.operational.primary_reason,
        snapshot.operational.pipeline_expected,
        tuple(
            sorted(
                (name, component.status)
                for name, component in snapshot.pipeline.items()
            )
        ),
        tuple(
            sorted(
                (
                    degradation.component,
                    degradation.severity,
                    degradation.reason,
                )
                for degradation in snapshot.degradations
            )
        ),
    )


async def publish_mobile_read_model(
    *,
    builder: MobileSnapshotBuilder,
    read_model: MobileReadModelStore,
    pool: asyncpg.Pool,
    as_of: datetime | None = None,
) -> MobileReadBundle:
    """Build once, atomically publish, and periodically persist NAV history."""
    observed_at = as_of or datetime.now(timezone.utc)
    try:
        previous = await run_in_threadpool(read_model.load)
    except Exception as exc:
        logger.warning("Previous mobile read model could not be loaded: %s", exc)
        previous = None
    bundle = await builder.build_bundle(as_of=observed_at)
    await run_in_threadpool(read_model.save, bundle)
    cadence_due = (
        bundle.snapshot.operational.pipeline_expected and observed_at.minute % 5 == 0
    )
    state_changed = previous is not None and _material_state_signature(
        previous
    ) != _material_state_signature(bundle)
    if bundle.snapshot.portfolio.nav is not None and (cadence_due or state_changed):
        await _persist_snapshot(pool, bundle)
    return bundle


async def _persist_snapshot(
    pool: asyncpg.Pool,
    bundle: MobileReadBundle,
) -> None:
    snapshot = bundle.snapshot
    portfolio = snapshot.portfolio
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO portfolio_monitor_snapshots (
                snapshot_id, as_of, broker_environment, mode, nav,
                previous_close_equity, nav_change_today, cash,
                gross_exposure, gross_exposure_limit, unrealized_pnl,
                current_drawdown, drawdown_limit, open_positions, source,
                pipeline_health, degradations
            )
            VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                $13, $14, $15, $16::jsonb, $17::jsonb
            )
            ON CONFLICT (snapshot_id) DO NOTHING
            """,
            snapshot.snapshot_id,
            snapshot.as_of,
            "paper" if config.ALPACA_PAPER_MODE else "live",
            snapshot.operational.mode,
            portfolio.nav,
            (
                portfolio.nav - portfolio.nav_change_today
                if portfolio.nav is not None and portfolio.nav_change_today is not None
                else None
            ),
            portfolio.nav_change_today,
            portfolio.cash,
            portfolio.gross_exposure,
            portfolio.gross_exposure_limit,
            portfolio.unrealized_pnl,
            portfolio.current_drawdown,
            portfolio.drawdown_limit,
            portfolio.open_positions,
            portfolio.source,
            json.dumps(
                {
                    key: value.model_dump(mode="json")
                    for key, value in snapshot.pipeline.items()
                }
            ),
            json.dumps(
                [
                    degradation.model_dump(mode="json")
                    for degradation in snapshot.degradations
                ]
            ),
        )


async def _run_mobile_monitor_snapshot() -> None:
    pool = await init_asyncpg_pool()
    redis_client = Redis.from_url(config.REDIS_URL)
    redis_store = RedisStore(redis_client)
    read_model = RedisMobileReadModelStore(redis_client)
    try:
        bundle = await publish_mobile_read_model(
            builder=MobileSnapshotBuilder(pool=pool, redis=redis_store),
            read_model=read_model,
            pool=pool,
        )
        await run_in_threadpool(
            _warm_mobile_spy_cache,
            redis_client,
            bundle.snapshot.as_of,
        )
    finally:
        redis_client.close()


@app.task(name="src.workers.mobile_monitor_task.run_mobile_monitor_snapshot")
def run_mobile_monitor_snapshot() -> dict[str, int | str]:
    """Celery entrypoint using worker-owned Redis and the persistent event loop."""
    run_async(_run_mobile_monitor_snapshot())
    return {"status": "ok", "processed": 1}
