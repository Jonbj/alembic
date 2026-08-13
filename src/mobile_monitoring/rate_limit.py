"""Redis-backed fixed-window rate limiting for mobile authentication."""

from __future__ import annotations

from src.rate_limit import FixedWindowRateLimiter, RateLimitResult, RedisEvalClient


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
        self._limiter = FixedWindowRateLimiter(
            redis,
            namespace="mobile:auth:login",
            limit=limit,
            window_seconds=window_seconds,
        )

    def check(self, username: str, source: str) -> RateLimitResult:
        """Consume username and source budgets and return the combined decision."""
        return self._limiter.check(
            username=username.casefold(),
            source=source,
        )
