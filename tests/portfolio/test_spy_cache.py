"""Tests for the broker-free SPY cache reader used by mobile HTTP routes."""

import json
from unittest.mock import MagicMock

from redis import Redis

from src.portfolio.spy import load_cached_spy_closes


def test_cached_spy_loader_returns_cached_values_without_broker_fallback() -> None:
    redis = MagicMock(spec=Redis)
    redis.get.return_value = json.dumps({"2026-07-22": 625.5})

    closes = load_cached_spy_closes("2026-07-01", "2026-07-23", redis)

    assert closes == {"2026-07-22": 625.5}
    redis.get.assert_called_once()


def test_cached_spy_loader_returns_none_on_cache_miss() -> None:
    redis = MagicMock(spec=Redis)
    redis.get.return_value = None

    assert load_cached_spy_closes("2026-07-01", "2026-07-23", redis) is None
