"""Atomic Redis-backed read model for the versioned mobile monitor."""

from __future__ import annotations

import inspect
import logging
from datetime import datetime, timezone
from typing import Protocol, TypeAlias, cast

import asyncpg
from pydantic import BaseModel
from redis import Redis
from starlette.concurrency import run_in_threadpool

from src.mobile_monitoring.models import PositionsResponse, SnapshotResponse

_READ_MODEL_KEY = "mobile:read-model:v1"
logger = logging.getLogger(__name__)


class UnsafeReadModelError(RuntimeError):
    """Raised when a cached read model is older than its safety ceiling."""

    def __init__(self, age_seconds: int) -> None:
        super().__init__("mobile read model is stale")
        self.age_seconds = age_seconds


class MobileReadBundle(BaseModel):
    """One coherent snapshot and positions projection from a single broker read."""

    snapshot: SnapshotResponse
    positions: PositionsResponse


class MobileReadModelReader(Protocol):
    """Synchronous read seam implemented by Redis and lightweight test stores."""

    def load(self) -> MobileReadBundle | None:
        """Return the current coherent bundle, or ``None`` when absent."""


class AsyncMobileReadModelReader(Protocol):
    """Asynchronous read seam implemented by multi-store readers."""

    async def load(self) -> MobileReadBundle | None:
        """Return the newest coherent bundle, or ``None`` when absent."""


MobileReadModelSource: TypeAlias = (
    MobileReadModelReader | AsyncMobileReadModelReader
)


class MobileReadModelStore(MobileReadModelReader, Protocol):
    """Read/write storage seam used by the worker publisher."""

    def save(self, bundle: MobileReadBundle) -> None:
        """Atomically replace the current coherent bundle."""


class RedisMobileReadModelStore:
    """Store the complete read model as one atomic Redis value."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def load(self) -> MobileReadBundle | None:
        """Load and validate the complete atomic Redis document."""
        raw = cast(bytes | str | None, self._redis.get(_READ_MODEL_KEY))
        if raw is None:
            return None
        return MobileReadBundle.model_validate_json(raw)

    def save(self, bundle: MobileReadBundle) -> None:
        """Atomically replace the complete Redis document with one SET."""
        self._redis.set(_READ_MODEL_KEY, bundle.model_dump_json())


async def load_mobile_read_model(
    store: MobileReadModelSource,
) -> MobileReadBundle | None:
    """Load a sync or async read-model adapter without blocking the event loop."""
    load = store.load
    if inspect.iscoroutinefunction(load):
        return await load()
    return await run_in_threadpool(load)


class ResilientMobileReadModelReader:
    """Read Redis first and fall back to the latest durable PostgreSQL bundle."""

    def __init__(
        self,
        primary: MobileReadModelStore,
        pool: asyncpg.Pool,
    ) -> None:
        self._primary = primary
        self._pool = pool

    async def load(self) -> MobileReadBundle | None:
        """Return the newest safe candidate across Redis and PostgreSQL."""
        try:
            primary = await load_mobile_read_model(self._primary)
        except Exception as exc:
            logger.warning("Primary mobile read model unavailable: %s", exc)
            primary = None
        async with self._pool.acquire() as conn:
            raw = await conn.fetchval(
                """
                SELECT pipeline_health -> '_mobile_read_bundle'
                FROM portfolio_monitor_snapshots
                WHERE pipeline_health ? '_mobile_read_bundle'
                ORDER BY as_of DESC
                LIMIT 1
                """
            )
        if raw is None:
            return primary
        if isinstance(raw, (bytes, str)):
            fallback = MobileReadBundle.model_validate_json(raw)
        else:
            fallback = MobileReadBundle.model_validate(raw)
        if primary is None or fallback.snapshot.as_of > primary.snapshot.as_of:
            return fallback
        return primary


def bundle_age_seconds(
    bundle: MobileReadBundle,
    *,
    now: datetime | None = None,
) -> int:
    """Return the non-negative age of a coherent bundle."""
    observed = now or datetime.now(timezone.utc)
    return max(0, int((observed - bundle.snapshot.as_of).total_seconds()))


def ensure_bundle_safe(
    bundle: MobileReadBundle,
    *,
    now: datetime | None = None,
) -> int:
    """Return bundle age or raise when the market-aware safe ceiling is exceeded."""
    age = bundle_age_seconds(bundle, now=now)
    safe_ceiling = 300 if bundle.snapshot.operational.pipeline_expected else 1800
    if age > safe_ceiling:
        raise UnsafeReadModelError(age)
    return age
