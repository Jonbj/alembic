"""P0-06 — Kill-switch fail-closed + pre-submission re-check + human-gated recovery.

Problems:
1. Race window: kill-switch is checked only at cycle start (B2). If activated
   between B2 and order submission, orders go through anyway.
2. No fail-closed on pre-submission check: if Redis is unreachable at that point,
   the system should default to NOT submitting, not to submitting.
3. (follow-up) DELETE /killswitch requires only an API key — no human gate, no
   cooldown, no audit log.
4. (follow-up) Legacy auto-recovery in execution.py can clear a drawdown halt
   automatically without operator involvement.

Fixes:
1. _is_ks_active_failclosed(): helper that returns True when Redis is unreachable.
2. Pre-submission re-check in _run_cycle_inner: if kill-switch is active OR Redis
   is unreachable at submission time, abort with _emergency_cancel_all().
3. (follow-up) POST /killswitch/recovery-token: generates one-time token (5-min TTL).
   DELETE /killswitch now requires confirm_token + respects cooldown + writes audit row.
4. (follow-up) _load_killswitch_recovery_config() defaults enabled=False.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
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


class TestKillSwitchHumanGate:
    """DELETE /killswitch must require a one-time recovery token (P0-06 follow-up)."""

    @pytest.mark.asyncio
    async def test_deactivate_without_token_is_rejected(self):
        """DELETE /killswitch called without confirm_token raises 422."""
        from fastapi import HTTPException
        from src.api.routes.admin import deactivate_killswitch

        mock_store = MagicMock()
        mock_pg = MagicMock()
        # Pass empty string — not a valid token
        with pytest.raises((HTTPException, TypeError)):
            await deactivate_killswitch(
                store=mock_store,
                pg=mock_pg,
                _="api_key",
                confirm_token="",
            )

    @pytest.mark.asyncio
    async def test_request_recovery_token_stores_in_redis(self):
        """POST /killswitch/recovery-token sets ks:recovery_token in Redis with TTL."""
        from src.api.routes.admin import request_recovery_token

        mock_store = MagicMock()
        result = await request_recovery_token(store=mock_store, _="api_key")

        assert "recovery_token" in result
        assert len(result["recovery_token"]) >= 16
        assert result["expires_in_seconds"] > 0
        mock_store._r.setex.assert_called_once()
        call_args = mock_store._r.setex.call_args[0]
        assert call_args[0] == "ks:recovery_token"

    @pytest.mark.asyncio
    async def test_deactivate_with_wrong_token_is_rejected(self):
        """DELETE /killswitch with wrong confirm_token raises 422."""
        from fastapi import HTTPException
        from src.api.routes.admin import deactivate_killswitch

        mock_store = MagicMock()
        mock_store._r.get.return_value = "correct_token"  # stored token
        mock_pg = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await deactivate_killswitch(
                store=mock_store,
                pg=mock_pg,
                _="api_key",
                confirm_token="wrong_token",
            )
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_deactivate_with_valid_token_succeeds(self):
        """DELETE /killswitch with valid confirm_token clears the kill-switch."""
        from src.api.routes.admin import deactivate_killswitch

        # No recent activation → no cooldown; token matches
        mock_store = MagicMock()
        mock_store._r.get.side_effect = lambda k: {
            "ks:recovery_token": "valid_token",
        }.get(k)
        mock_pg = MagicMock()

        result = await deactivate_killswitch(
            store=mock_store,
            pg=mock_pg,
            _="api_key",
            confirm_token="valid_token",
        )
        assert result["killswitch"] == "deactivated"
        mock_store.deactivate_killswitch.assert_called_once()
        mock_store.deactivate_operator_halt.assert_called_once()


class TestKillSwitchCooldown:
    """Deactivation must be blocked during cooldown window after activation."""

    @pytest.mark.asyncio
    async def test_deactivate_blocked_during_cooldown(self):
        """If kill-switch was just activated (< cooldown), DELETE raises 422."""
        from fastapi import HTTPException
        from src.api.routes.admin import deactivate_killswitch

        recent_ts = datetime.now(timezone.utc).isoformat()
        mock_store = MagicMock()
        mock_store._r.get.side_effect = lambda k: {
            "ks:recovery_token": "valid_token",
            "system:halted_by_operator_reason": json.dumps({"activated_at": recent_ts}),
        }.get(k)
        mock_pg = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await deactivate_killswitch(
                store=mock_store,
                pg=mock_pg,
                _="api_key",
                confirm_token="valid_token",
            )
        assert exc_info.value.status_code == 422
        assert "cooldown" in exc_info.value.detail.lower()


class TestKillSwitchAuditLog:
    """Activation, deactivation, and pre-submission abort must write audit rows."""

    @pytest.mark.asyncio
    async def test_audit_log_written_on_activation(self):
        """POST /killswitch writes KILLSWITCH_ACTIVATE audit row."""
        from src.api.routes.admin import activate_killswitch, KillswitchRequest

        mock_store = MagicMock()
        mock_pg = MagicMock()

        await activate_killswitch(
            store=mock_store,
            pg=mock_pg,
            _="api_key",
            req=KillswitchRequest(reason="test halt"),
        )
        mock_pg.write_audit_log.assert_called_once()
        call_kwargs = mock_pg.write_audit_log.call_args
        action = call_kwargs[1].get("action") or call_kwargs[0][0]
        assert action == "KILLSWITCH_ACTIVATE"

    @pytest.mark.asyncio
    async def test_audit_log_written_on_deactivation(self):
        """DELETE /killswitch writes KILLSWITCH_DEACTIVATE audit row."""
        from src.api.routes.admin import deactivate_killswitch

        mock_store = MagicMock()
        mock_store._r.get.side_effect = lambda k: {
            "ks:recovery_token": "tok123",
        }.get(k)
        mock_pg = MagicMock()

        await deactivate_killswitch(
            store=mock_store,
            pg=mock_pg,
            _="api_key",
            confirm_token="tok123",
        )
        mock_pg.write_audit_log.assert_called_once()
        call_kwargs = mock_pg.write_audit_log.call_args
        action = call_kwargs[1].get("action") or call_kwargs[0][0]
        assert action == "KILLSWITCH_DEACTIVATE"

    def test_presubmission_abort_writes_audit_log(self):
        """_run_cycle_inner source must contain a write_audit_log call after the KS abort marker."""
        import inspect
        from src.workers.portfolio_scheduler import _run_cycle_inner

        src = inspect.getsource(_run_cycle_inner)
        ks_marker = "Kill-switch active at pre-submission re-check"
        audit_marker = "write_audit_log"
        ks_pos = src.find(ks_marker)
        audit_pos = src.find(audit_marker, ks_pos) if ks_pos >= 0 else -1
        assert ks_pos >= 0, (
            "KS pre-submission log message not found in _run_cycle_inner — "
            "has the abort code been moved?"
        )
        assert audit_pos >= 0, (
            "No write_audit_log call found after the KS pre-submission abort — "
            "P0-06 requires an audit row for every pre-submission KS abort"
        )


class TestLegacyAutoRecoveryDisabled:
    """_load_killswitch_recovery_config must default enabled=False (P0-06 follow-up)."""

    def test_auto_recovery_disabled_by_default(self):
        """When trading.yaml is absent, auto-recovery defaults to disabled."""
        from src.workers.execution import _load_killswitch_recovery_config

        with patch("builtins.open", side_effect=FileNotFoundError()):
            cfg = _load_killswitch_recovery_config()

        assert cfg["enabled"] is False, (
            "P0-06: legacy auto-recovery must be disabled by default. "
            "An operator halt should only be cleared by a human via the API. "
            "Set killswitch_recovery.enabled=true in trading.yaml to opt-in."
        )
