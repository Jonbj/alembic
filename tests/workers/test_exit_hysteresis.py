"""Anti-churn exit hysteresis (point 1).

The regime fix (FIX-A) raised position sizes ~4x, which amplified rebalance churn:
names were sold the moment the 90-min hold floor lifted, then rebought (TSM 3x,
AMD/AMZN 2x in 2 days). A symmetric no-trade band can't fix this (exit gap == entry
gap at ~0.85% NAV positions). Exit hysteresis makes exits sticky: a SELL is only
allowed once a position has been targeted for exit for N consecutive cycles.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest


def _order(symbol: str, side: str):
    from src.backtest.engine.types import Order, OrderSide
    side_enum = OrderSide.BUY if side == "BUY" else OrderSide.SELL
    return Order.market_order(
        ts=datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc),
        symbol=symbol, side=side_enum, qty=1.0,
    )


class _FakeRedis:
    """Minimal in-memory Redis supporting the ops the helper uses."""
    def __init__(self):
        self.store: dict[str, int] = {}
    def incr(self, k):
        self.store[k] = self.store.get(k, 0) + 1
        return self.store[k]
    def expire(self, k, ttl):
        pass
    def delete(self, k):
        self.store.pop(k, None)
    def close(self):
        pass


def _patch_redis(fake):
    return patch("redis.Redis.from_url", return_value=fake)


class TestExitHysteresis:
    def test_first_exit_cycle_suppressed(self):
        """A SELL on the first cycle it appears is held (streak 1 < 2)."""
        from src.workers.portfolio_scheduler import _apply_exit_hysteresis
        fake = _FakeRedis()
        with _patch_redis(fake):
            out = _apply_exit_hysteresis([_order("TSM", "SELL")], "redis://x", 2)
        assert out == []  # suppressed

    def test_second_consecutive_exit_allowed(self):
        """Two consecutive cycles targeting exit → the SELL goes through."""
        from src.workers.portfolio_scheduler import _apply_exit_hysteresis
        fake = _FakeRedis()
        with _patch_redis(fake):
            _apply_exit_hysteresis([_order("TSM", "SELL")], "redis://x", 2)   # streak 1
            out = _apply_exit_hysteresis([_order("TSM", "SELL")], "redis://x", 2)  # streak 2
        assert [o.symbol for o in out] == ["TSM"]

    def test_buy_resets_streak(self):
        """A BUY clears the exit streak so the flicker restarts (name re-wanted)."""
        from src.workers.portfolio_scheduler import _apply_exit_hysteresis
        fake = _FakeRedis()
        with _patch_redis(fake):
            _apply_exit_hysteresis([_order("TSM", "SELL")], "redis://x", 2)   # streak 1
            _apply_exit_hysteresis([_order("TSM", "BUY")], "redis://x", 2)    # reset
            out = _apply_exit_hysteresis([_order("TSM", "SELL")], "redis://x", 2)  # streak 1 again
        assert out == []  # suppressed again — flicker did not accumulate

    def test_buy_always_passes_through(self):
        from src.workers.portfolio_scheduler import _apply_exit_hysteresis
        fake = _FakeRedis()
        with _patch_redis(fake):
            out = _apply_exit_hysteresis([_order("AAPL", "BUY")], "redis://x", 2)
        assert [o.symbol for o in out] == ["AAPL"]

    def test_zero_persistence_disables(self):
        from src.workers.portfolio_scheduler import _apply_exit_hysteresis
        fake = _FakeRedis()
        with _patch_redis(fake):
            out = _apply_exit_hysteresis([_order("TSM", "SELL")], "redis://x", 0)
        assert [o.symbol for o in out] == ["TSM"]  # not suppressed

    def test_redis_error_fail_open(self):
        """If Redis is unreachable, do not suppress (don't strand positions)."""
        from src.workers.portfolio_scheduler import _apply_exit_hysteresis
        with patch("redis.Redis.from_url", side_effect=ConnectionError("down")):
            out = _apply_exit_hysteresis([_order("TSM", "SELL")], "redis://x", 2)
        assert [o.symbol for o in out] == ["TSM"]

    def test_mixed_buy_and_sell(self):
        """BUY passes; first-cycle SELL suppressed — both in the same cycle."""
        from src.workers.portfolio_scheduler import _apply_exit_hysteresis
        fake = _FakeRedis()
        with _patch_redis(fake):
            out = _apply_exit_hysteresis(
                [_order("AAPL", "BUY"), _order("TSM", "SELL")], "redis://x", 2
            )
        assert [o.symbol for o in out] == ["AAPL"]

    def test_empty_orders(self):
        from src.workers.portfolio_scheduler import _apply_exit_hysteresis
        assert _apply_exit_hysteresis([], "redis://x", 2) == []


class TestExitPersistenceConfig:
    def test_default_from_config(self):
        from src.workers.portfolio_scheduler import _get_exit_persistence_cycles
        # trading.yaml sets execution.exit_persistence_cycles: 2
        assert _get_exit_persistence_cycles() == 2
