"""Tests for the Redis-backed mobile login rate limiter."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from src.mobile_monitoring.rate_limit import MobileLoginRateLimiter


class FakeRedisEvalClient:
    """Minimal Redis EVAL fake implementing the limiter's fixed-window script."""

    def __init__(self) -> None:
        self.counts: defaultdict[str, int] = defaultdict(int)

    def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: object,
    ) -> Any:
        del script, numkeys
        key = str(keys_and_args[0])
        self.counts[key] += 1
        return [self.counts[key], int(keys_and_args[1])]


def test_username_budget_applies_across_source_addresses() -> None:
    """Changing IP does not bypass the per-username attempt budget."""
    limiter = MobileLoginRateLimiter(FakeRedisEvalClient(), limit=2, window_seconds=60)

    assert limiter.check("alice", "10.0.0.1").allowed is True
    assert limiter.check("ALICE", "10.0.0.2").allowed is True
    result = limiter.check("alice", "10.0.0.3")

    assert result.allowed is False
    assert result.retry_after_seconds == 60


def test_source_budget_applies_across_usernames() -> None:
    """Changing username does not bypass the per-source attempt budget."""
    limiter = MobileLoginRateLimiter(FakeRedisEvalClient(), limit=2, window_seconds=60)

    assert limiter.check("alice", "10.0.0.1").allowed is True
    assert limiter.check("bob", "10.0.0.1").allowed is True
    result = limiter.check("carol", "10.0.0.1")

    assert result.allowed is False


def test_rate_limit_keys_do_not_contain_username_or_source() -> None:
    """Redis keys contain digests rather than identity/source values."""
    redis = FakeRedisEvalClient()
    limiter = MobileLoginRateLimiter(redis, limit=2, window_seconds=60)

    limiter.check("Sensitive.User", "192.0.2.10")

    keys = " ".join(redis.counts)
    assert "sensitive.user" not in keys
    assert "192.0.2.10" not in keys
