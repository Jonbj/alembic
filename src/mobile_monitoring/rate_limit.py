"""Redis-backed fixed-window rate limiting for mobile authentication."""

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
    """Minimal Redis capability required by the login limiter."""

    def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: str,
    ) -> Any:
        """Evaluate a Lua script and return its Redis result."""


@dataclass(frozen=True)
class RateLimitResult:
    """Decision returned for one login attempt."""

    allowed: bool
    retry_after_seconds: int


class MobileLoginRateLimiter:
    """Limit login attempts independently by normalized username and source."""

    def __init__(
        self,
        redis: RedisEvalClient,
        *,
        limit: int,
        window_seconds: int,
    ) -> None:
        """Create a fixed-window limiter using atomic Redis increments."""
        if limit < 1:
            raise ValueError("limit must be positive")
        if window_seconds < 1:
            raise ValueError("window_seconds must be positive")
        self._redis = redis
        self._limit = limit
        self._window_seconds = window_seconds

    def check(self, username: str, source: str) -> RateLimitResult:
        """Consume username and source budgets and return the combined decision."""
        username_count, username_ttl = self._increment(
            self._key("username", username.casefold())
        )
        source_count, source_ttl = self._increment(self._key("source", source))

        username_allowed = username_count <= self._limit
        source_allowed = source_count <= self._limit
        retry_after = max(
            username_ttl if not username_allowed else 0,
            source_ttl if not source_allowed else 0,
        )
        return RateLimitResult(
            allowed=username_allowed and source_allowed,
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

    @staticmethod
    def _key(dimension: str, value: str) -> str:
        digest = hashlib.sha256(value.encode()).hexdigest()
        return f"mobile:auth:login:{dimension}:{digest}"
