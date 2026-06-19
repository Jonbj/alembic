"""P0-06 — Kill-switch fail-closed + pre-submission re-check.

Problems:
1. Race window: kill-switch is checked only at cycle start (B2). If activated
   between B2 and order submission, orders go through anyway.
2. No fail-closed on pre-submission check: if Redis is unreachable at that point,
   the system should default to NOT submitting, not to submitting.

Fixes:
1. _is_ks_active_failclosed(): helper that returns True when Redis is unreachable.
2. Pre-submission re-check in _run_cycle_inner: if kill-switch is active OR Redis
   is unreachable at submission time, abort with _emergency_cancel_all().
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestIsKsActiveFailclosed:
    """_is_ks_active_failclosed must return True when Redis is unreachable (fail-closed)."""

    def test_returns_false_when_neither_key_set(self):
        """Kill-switch not active → returns False."""
        from src.workers.portfolio_scheduler import _is_ks_active_failclosed

        with patch("src.workers.portfolio_scheduler._R" if False else "redis.Redis") as mock_cls:
            inst = MagicMock()
            inst.get.return_value = None
            mock_cls.from_url.return_value = inst
            with patch("src.workers.portfolio_scheduler._is_ks_active_failclosed",
                       wraps=_is_ks_active_failclosed):
                pass  # just import-check

        with patch("redis.Redis") as mock_cls:
            inst = MagicMock()
            inst.get.return_value = None
            mock_cls.from_url.return_value = inst
            result = _is_ks_active_failclosed("redis://localhost:6379/0")
        assert result is False

    def test_returns_true_when_killswitch_active_key_set(self):
        """killswitch_active key set → returns True."""
        from src.workers.portfolio_scheduler import _is_ks_active_failclosed

        with patch("redis.Redis") as mock_cls:
            inst = MagicMock()
            inst.get.side_effect = lambda k: "1" if k == "killswitch_active" else None
            mock_cls.from_url.return_value = inst
            result = _is_ks_active_failclosed("redis://localhost:6379/0")
        assert result is True

    def test_returns_true_when_operator_halt_key_set(self):
        """system:halted_by_operator key set → returns True."""
        from src.workers.portfolio_scheduler import _is_ks_active_failclosed

        with patch("redis.Redis") as mock_cls:
            inst = MagicMock()
            inst.get.side_effect = lambda k: "1" if k == "system:halted_by_operator" else None
            mock_cls.from_url.return_value = inst
            result = _is_ks_active_failclosed("redis://localhost:6379/0")
        assert result is True

    def test_returns_true_when_redis_unreachable(self):
        """Redis unreachable → returns True (fail-closed: assume halted)."""
        from src.workers.portfolio_scheduler import _is_ks_active_failclosed

        with patch("redis.Redis") as mock_cls:
            mock_cls.from_url.side_effect = ConnectionError("Redis down")
            result = _is_ks_active_failclosed("redis://localhost:6379/0")
        assert result is True, (
            "_is_ks_active_failclosed must return True when Redis is unreachable — "
            "P0-06 requires fail-closed behavior: if we can't verify it's safe, don't trade."
        )

    def test_returns_true_when_redis_get_raises(self):
        """Redis.get raises unexpectedly → returns True (fail-closed)."""
        from src.workers.portfolio_scheduler import _is_ks_active_failclosed

        with patch("redis.Redis") as mock_cls:
            inst = MagicMock()
            inst.get.side_effect = Exception("timeout")
            mock_cls.from_url.return_value = inst
            result = _is_ks_active_failclosed("redis://localhost:6379/0")
        assert result is True


class TestKillSwitchPreventsSubmission:
    """_submit_portfolio_orders must not be called when kill-switch activates mid-cycle."""

    def test_kill_switch_prevents_submission_when_active_presubmit(self):
        """If _is_ks_active_failclosed returns True at pre-submission, submission is skipped."""
        from src.workers.portfolio_scheduler import _run_cycle_inner

        with patch("src.strategies.registry.StrategyRegistry") as mock_reg, \
             patch("alpaca.data.historical.StockHistoricalDataClient") as mock_dc, \
             patch("alpaca.trading.client.TradingClient") as mock_tc, \
             patch("redis.Redis") as mock_redis_cls, \
             patch("src.workers.portfolio_scheduler._submit_portfolio_orders") as mock_submit, \
             patch("src.workers.portfolio_scheduler._is_ks_active_failclosed") as mock_ks, \
             patch("src.workers.portfolio_scheduler._emergency_cancel_all"):

            # B2 check at cycle start: kill-switch NOT active
            # Pre-submission re-check: kill-switch NOW active
            ks_call_count = [0]
            def ks_side_effect(url):
                ks_call_count[0] += 1
                return ks_call_count[0] > 1  # False on first, True on second+
            mock_ks.side_effect = ks_side_effect

            entry = MagicMock()
            entry.strategy_id = "S1"
            entry.allocation_pct = 0.50
            entry.enabled = True
            mock_reg.return_value.get_active_strategies.return_value = [entry]

            import pandas as pd
            raw_df = pd.DataFrame(
                {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
                index=pd.date_range("2026-06-01", periods=100, freq="1min"),
            )
            mock_dc.return_value.get_stock_bars.return_value.df = raw_df

            redis_inst = MagicMock()
            redis_inst.get.return_value = None
            mock_redis_cls.from_url.return_value = redis_inst

            clock = MagicMock()
            clock.is_open = True
            account = MagicMock()
            account.portfolio_value = "100000"
            mock_tc.return_value.get_clock.return_value = clock
            mock_tc.return_value.get_account.return_value = account
            mock_tc.return_value.get_all_positions.return_value = []
            mock_tc.return_value.get_orders.return_value = []

            _run_cycle_inner()

        mock_submit.assert_not_called(), (
            "_submit_portfolio_orders must not be called when kill-switch activates mid-cycle"
        )
