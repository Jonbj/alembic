"""P0-07 — Market calendar fail-closed.

Problem: if get_clock() raises, the cycle logs a warning and proceeds anyway
(line 279: "proceeding anyway"). This means orders can be submitted on holidays,
early-close days, or during exchange outages when Alpaca's clock API is down.

Fix: get_clock() failure must abort the cycle (fail-closed), not proceed.
Acceptance: test_clock_failure_aborts_cycle passes.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _make_base_mocks(redis_inst=None, clock=None):
    """Return context-manager patches for the minimal _run_cycle_inner setup."""
    if redis_inst is None:
        redis_inst = MagicMock()
        redis_inst.get.return_value = None
    if clock is None:
        clock = MagicMock()
        clock.is_open = True
    return redis_inst, clock


class TestClockFailureAbortsCycle:
    """get_clock() failure must abort the cycle, not proceed with order submission."""

    def test_clock_failure_aborts_cycle(self, approved_strategy):
        """When get_clock() raises, cycle must return error and NOT submit orders."""
        from src.workers.portfolio_scheduler import _run_cycle_inner

        redis_inst = MagicMock()
        redis_inst.get.return_value = None

        with patch("src.strategies.registry.StrategyRegistry") as mock_reg, \
             patch("alpaca.data.historical.StockHistoricalDataClient") as mock_dc, \
             patch("alpaca.trading.client.TradingClient") as mock_tc, \
             patch("redis.Redis") as mock_redis_cls, \
             patch("src.workers.portfolio_scheduler._submit_portfolio_orders") as mock_submit, \
             patch("src.workers.portfolio_scheduler._is_ks_active_failclosed", return_value=False):

            entry = MagicMock()
            entry.strategy_id = "S1"
            entry.allocation_pct = 0.50
            entry.enabled = True
            mock_reg.return_value.get_active_strategies.return_value = [entry]

            mock_tc.return_value.get_clock.side_effect = Exception("Alpaca clock API unreachable")
            mock_tc.return_value.get_account.return_value = MagicMock(portfolio_value="100000")
            mock_tc.return_value.get_all_positions.return_value = []
            mock_redis_cls.from_url.return_value = redis_inst

            with approved_strategy("S1"):
                result = _run_cycle_inner()

        # Must abort with a specific clock-related reason, not just any error.
        assert result.get("error") == "clock_unavailable" or (
            result.get("skipped") and "clock" in str(result.get("reason", ""))
        ), (
            f"Cycle must abort with clock_unavailable when get_clock() fails, got: {result}.\n"
            "Fix: change 'proceeding anyway' to return {'error': 'clock_unavailable'} "
            "in src/workers/portfolio_scheduler.py"
        )
        mock_submit.assert_not_called()

    def test_market_closed_aborts_cycle(self, approved_strategy):
        """is_open=False must skip cycle — existing behaviour preserved."""
        from src.workers.portfolio_scheduler import _run_cycle_inner

        redis_inst = MagicMock()
        redis_inst.get.return_value = None

        with patch("src.strategies.registry.StrategyRegistry") as mock_reg, \
             patch("alpaca.data.historical.StockHistoricalDataClient"), \
             patch("alpaca.trading.client.TradingClient") as mock_tc, \
             patch("redis.Redis") as mock_redis_cls, \
             patch("src.workers.portfolio_scheduler._submit_portfolio_orders") as mock_submit, \
             patch("src.workers.portfolio_scheduler._is_ks_active_failclosed", return_value=False):

            entry = MagicMock()
            entry.strategy_id = "S1"
            entry.enabled = True
            mock_reg.return_value.get_active_strategies.return_value = [entry]

            clock = MagicMock()
            clock.is_open = False
            clock.next_open = "2026-06-20T13:30:00+00:00"
            mock_tc.return_value.get_clock.return_value = clock
            mock_redis_cls.from_url.return_value = redis_inst

            with approved_strategy("S1"):
                result = _run_cycle_inner()

        assert result == {"skipped": True, "reason": "market_closed", "next_open": "2026-06-20T13:30:00+00:00"}
        mock_submit.assert_not_called()
