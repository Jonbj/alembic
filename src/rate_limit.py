"""Redis-backed fixed-window rate limiting shared by API boundaries."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Protocol

_FIXED_WINDOW_SCRIPT = """
local count = redis.call("INCR", KEYS[1])
if count == 1 then
    redis.call("EXPIRE", KEYS[1], ARGV[1])
end
local ttl = redis.call("TTL", KEYS[1])
return {count, ttl}
"""


class RedisEvalClient(Protocol):
    """Minimal Redis capability required by the fixed-window limiter."""

    def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: str,
    ) -> Any:
        """Evaluate a Lua script and return its Redis result."""


@dataclass(frozen=True)
class RateLimitResult:
    """Decision returned after consuming one or more request budgets."""

    allowed: bool
    retry_after_seconds: int


class FixedWindowRateLimiter:
    """Atomically limit a namespace across one or more hashed dimensions."""

    def __init__(
        self,
        redis: RedisEvalClient,
        *,
        namespace: str,
        limit: int,
        window_seconds: int,
    ) -> None:
        if not namespace:
            raise ValueError("namespace must not be empty")
        if limit < 1:
            raise ValueError("limit must be positive")
        if window_seconds < 1:
            raise ValueError("window_seconds must be positive")
        self._redis = redis
        self._namespace = namespace
        self._limit = limit
        self._window_seconds = window_seconds

    def check(self, **dimensions: str) -> RateLimitResult:
        """Consume every supplied dimension and return their combined decision."""
        if not dimensions:
            raise ValueError("at least one rate-limit dimension is required")

        retry_after = 0
        allowed = True
        for dimension, value in dimensions.items():
            count, ttl = self._increment(self._key(dimension, value))
            if count > self._limit:
                allowed = False
                retry_after = max(retry_after, ttl)
        return RateLimitResult(
            allowed=allowed,
            retry_after_seconds=retry_after,
        )

    def _increment(self, key: str) -> tuple[int, int]:
        result = self._redis.eval(
            _FIXED_WINDOW_SCRIPT,
            1,
            key,
            str(self._window_seconds),
        )
        count, ttl = int(result[0]), int(result[1])
        return count, ttl if ttl > 0 else self._window_seconds

    def _key(self, dimension: str, value: str) -> str:
        digest = hashlib.sha256(value.encode()).hexdigest()
        return f"rate-limit:{self._namespace}:{dimension}:{digest}"
