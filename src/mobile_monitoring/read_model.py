"""Atomic Redis-backed read model for the versioned mobile monitor."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol, cast

from pydantic import BaseModel
from redis import Redis

from src.mobile_monitoring.models import PositionsResponse, SnapshotResponse

_READ_MODEL_KEY = "mobile:read-model:v1"


class UnsafeReadModelError(RuntimeError):
    """Raised when a cached read model is older than its safety ceiling."""

    def __init__(self, age_seconds: int) -> None:
        super().__init__("mobile read model is stale")
        self.age_seconds = age_seconds


class MobileReadBundle(BaseModel):
    """One coherent snapshot and positions projection from a single broker read."""

    snapshot: SnapshotResponse
    positions: PositionsResponse


class MobileReadModelStore(Protocol):
    """Storage seam used by the worker writer and HTTP readers."""

    def load(self) -> MobileReadBundle | None:
        """Return the current coherent bundle, or ``None`` when absent."""

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
