"""Tests for #62: broker-side protective stop for fractional Alpaca positions.

Alpaca rejects bracket/stop orders on notional/fractional quantities (error
42210000, verified live 2026-07-16). The fix submits a standalone GTC stop
SELL order sized to the whole-share floor of the position, reconciled every
cycle against any existing stop order for the symbol (idempotent sync).
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.portfolio.stop_policy import StopPolicy

RISK_CFG = {
    "stop_loss_mode": "fixed",
    "stop_loss": 0.0,
    "broker_disaster_stop": {
        "multiplier": 1.5,
        "sigma_multiple": 5.0,
        "floor_pct": 0.12,
        "cap_pct": 0.20,
    },
}


@pytest.fixture
def stop_policy():
    return StopPolicy(RISK_CFG)


@pytest.fixture
def cycle_ts():
    return datetime(2026, 7, 16, 15, 0, tzinfo=timezone.utc)


def _plan(**kwargs):
    from src.portfolio.fractional_stop_orders import plan_protective_stop

    defaults = dict(
        symbol="AAPL",
        position_qty=2.4578,
        avg_entry_price=100.0,
        strategy=None,
        current_sigma_eff=None,
        cycle_ts=None,
        existing_stop_orders=[],
    )
    defaults.update(kwargs)
    return plan_protective_stop(**defaults)


class TestPlanProtectiveStop:
    def test_skip_when_position_under_one_whole_share(self, stop_policy, cycle_ts):
        plan = _plan(position_qty=0.7, stop_policy=stop_policy, cycle_ts=cycle_ts)

        assert plan.action == "skip_no_whole_share"
        assert plan.whole_qty == 0
        assert plan.cancel_order_ids == ()

    def test_create_when_no_existing_stop_order(self, stop_policy, cycle_ts):
        plan = _plan(
            position_qty=2.4578, avg_entry_price=100.0,
            stop_policy=stop_policy, cycle_ts=cycle_ts, existing_stop_orders=[],
        )

        assert plan.action == "create"
        assert plan.symbol == "AAPL"
        assert plan.whole_qty == 2
        # fixed mode, stop_loss=0.0 -> d_init=0 -> d_hard = clip(5*0, 0.12, 0.20) = floor 0.12
        assert plan.stop_price == pytest.approx(100.0 * (1 - 0.12), abs=0.01)

    def test_noop_when_existing_order_already_matches(self, stop_policy, cycle_ts):
        from src.portfolio.fractional_stop_orders import ExistingStopOrder

        existing = ExistingStopOrder(id="ord-1", qty=2, stop_price=88.0)
        plan = _plan(
            position_qty=2.4578, avg_entry_price=100.0,
            stop_policy=stop_policy, cycle_ts=cycle_ts, existing_stop_orders=[existing],
        )

        assert plan.action == "noop"
        assert plan.cancel_order_ids == ()

    def test_replace_when_position_grew(self, stop_policy, cycle_ts):
        from src.portfolio.fractional_stop_orders import ExistingStopOrder

        existing = ExistingStopOrder(id="ord-1", qty=2, stop_price=88.0)
        plan = _plan(
            position_qty=5.1, avg_entry_price=100.0,
            stop_policy=stop_policy, cycle_ts=cycle_ts, existing_stop_orders=[existing],
        )

        assert plan.action == "replace"
        assert plan.whole_qty == 5
        assert plan.cancel_order_ids == ("ord-1",)

    def test_replace_when_stop_price_stale_beyond_tolerance(self, stop_policy, cycle_ts):
        from src.portfolio.fractional_stop_orders import ExistingStopOrder

        # Existing order at a stop_price far from the freshly computed one (avg_entry moved).
        existing = ExistingStopOrder(id="ord-1", qty=2, stop_price=50.0)
        plan = _plan(
            position_qty=2.4578, avg_entry_price=100.0,
            stop_policy=stop_policy, cycle_ts=cycle_ts, existing_stop_orders=[existing],
        )

        assert plan.action == "replace"
        assert plan.cancel_order_ids == ("ord-1",)

    def test_replace_consolidates_multiple_existing_orders(self, stop_policy, cycle_ts):
        from src.portfolio.fractional_stop_orders import ExistingStopOrder

        existing = [
            ExistingStopOrder(id="ord-1", qty=1, stop_price=88.0),
            ExistingStopOrder(id="ord-2", qty=1, stop_price=88.0),
        ]
        plan = _plan(
            position_qty=2.4578, avg_entry_price=100.0,
            stop_policy=stop_policy, cycle_ts=cycle_ts, existing_stop_orders=existing,
        )

        assert plan.action == "replace"
        assert set(plan.cancel_order_ids) == {"ord-1", "ord-2"}

    def test_stop_price_uses_current_sigma_when_wide_enough_to_exceed_floor(self, stop_policy, cycle_ts):
        # sigma_eff_current=0.05 -> sig_mult*sigma = 5*0.05 = 0.25, clipped to cap 0.20
        plan = _plan(
            position_qty=3.0, avg_entry_price=100.0, current_sigma_eff=0.05,
            stop_policy=stop_policy, cycle_ts=cycle_ts, existing_stop_orders=[],
        )

        assert plan.stop_price == pytest.approx(100.0 * (1 - 0.20), abs=0.01)


class TestBuildProtectiveStopPlans:
    def test_maps_each_position_to_a_plan(self, stop_policy, cycle_ts):
        from src.portfolio.fractional_stop_orders import build_protective_stop_plans

        positions = [
            SimpleNamespace(symbol="AAPL", qty="2.4578", avg_entry_price="100.0"),
            SimpleNamespace(symbol="MSFT", qty="0.5", avg_entry_price="300.0"),
        ]
        plans = build_protective_stop_plans(
            positions, stop_orders_by_symbol={}, stop_policy=stop_policy, cycle_ts=cycle_ts,
        )

        by_symbol = {p.symbol: p for p in plans}
        assert by_symbol["AAPL"].action == "create"
        assert by_symbol["AAPL"].whole_qty == 2
        assert by_symbol["MSFT"].action == "skip_no_whole_share"

    def test_passes_through_existing_orders_for_symbol(self, stop_policy, cycle_ts):
        from src.portfolio.fractional_stop_orders import build_protective_stop_plans, ExistingStopOrder

        positions = [SimpleNamespace(symbol="AAPL", qty="2.4578", avg_entry_price="100.0")]
        existing = ExistingStopOrder(id="ord-1", qty=2, stop_price=88.0)
        plans = build_protective_stop_plans(
            positions, stop_orders_by_symbol={"AAPL": [existing]},
            stop_policy=stop_policy, cycle_ts=cycle_ts,
        )

        assert plans[0].action == "noop"

    def test_orphan_stop_cancelled_when_position_fully_closed(self, stop_policy, cycle_ts):
        """#62 review finding (GLM): reconciliation was position-driven only — a
        symbol sold to zero drops out of get_all_positions() but its GTC stop
        order was never cancelled, leaking an orphan broker order indefinitely."""
        from src.portfolio.fractional_stop_orders import build_protective_stop_plans, ExistingStopOrder

        existing = ExistingStopOrder(id="ord-orphan", qty=2, stop_price=88.0)
        plans = build_protective_stop_plans(
            positions=[],  # AAPL fully closed — no longer in get_all_positions()
            stop_orders_by_symbol={"AAPL": [existing]},
            stop_policy=stop_policy, cycle_ts=cycle_ts,
        )

        assert len(plans) == 1
        assert plans[0].symbol == "AAPL"
        assert plans[0].action == "cancel_orphan"
        assert plans[0].cancel_order_ids == ("ord-orphan",)

    def test_orphan_cancellation_only_for_symbols_without_a_position(self, stop_policy, cycle_ts):
        from src.portfolio.fractional_stop_orders import build_protective_stop_plans, ExistingStopOrder

        positions = [SimpleNamespace(symbol="AAPL", qty="2.4578", avg_entry_price="100.0")]
        stop_orders_by_symbol = {
            "AAPL": [ExistingStopOrder(id="ord-1", qty=2, stop_price=88.0)],  # still held -> not orphan
            "MSFT": [ExistingStopOrder(id="ord-2", qty=1, stop_price=280.0)],  # closed -> orphan
        }
        plans = build_protective_stop_plans(
            positions, stop_orders_by_symbol, stop_policy=stop_policy, cycle_ts=cycle_ts,
        )

        by_symbol = {p.symbol: p for p in plans}
        assert by_symbol["AAPL"].action == "noop"
        assert by_symbol["MSFT"].action == "cancel_orphan"
        assert by_symbol["MSFT"].cancel_order_ids == ("ord-2",)


class TestExecuteProtectiveStopPlans:
    def test_create_submits_stop_order(self):
        from src.portfolio.fractional_stop_orders import execute_protective_stop_plans, ProtectiveStopPlan

        plan = ProtectiveStopPlan(action="create", symbol="AAPL", whole_qty=2, stop_price=88.0)
        tc = MagicMock()

        summary = execute_protective_stop_plans([plan], tc)

        tc.submit_order.assert_called_once()
        req = tc.submit_order.call_args[0][0]
        assert req.symbol == "AAPL"
        assert req.qty == 2
        assert req.stop_price == 88.0
        assert req.side.value == "sell"
        assert req.time_in_force.value == "gtc"
        tc.cancel_order_by_id.assert_not_called()
        assert summary["created"] == 1

    def test_replace_cancels_then_submits(self):
        from src.portfolio.fractional_stop_orders import execute_protective_stop_plans, ProtectiveStopPlan

        plan = ProtectiveStopPlan(
            action="replace", symbol="AAPL", whole_qty=5, stop_price=90.0, cancel_order_ids=("ord-1",),
        )
        tc = MagicMock()

        summary = execute_protective_stop_plans([plan], tc)

        tc.cancel_order_by_id.assert_called_once_with("ord-1")
        tc.submit_order.assert_called_once()
        assert summary["replaced"] == 1

    def test_noop_does_not_call_broker(self):
        from src.portfolio.fractional_stop_orders import execute_protective_stop_plans, ProtectiveStopPlan

        plan = ProtectiveStopPlan(action="noop", symbol="AAPL", whole_qty=2, stop_price=88.0)
        tc = MagicMock()

        summary = execute_protective_stop_plans([plan], tc)

        tc.submit_order.assert_not_called()
        tc.cancel_order_by_id.assert_not_called()
        assert summary["noop"] == 1

    def test_skip_does_not_call_broker(self):
        from src.portfolio.fractional_stop_orders import execute_protective_stop_plans, ProtectiveStopPlan

        plan = ProtectiveStopPlan(action="skip_no_whole_share", symbol="MSFT", whole_qty=0, stop_price=None)
        tc = MagicMock()

        summary = execute_protective_stop_plans([plan], tc)

        tc.submit_order.assert_not_called()
        assert summary["skipped"] == 1

    def test_cancel_orphan_cancels_without_submitting(self):
        from src.portfolio.fractional_stop_orders import execute_protective_stop_plans, ProtectiveStopPlan

        plan = ProtectiveStopPlan(
            action="cancel_orphan", symbol="AAPL", whole_qty=0, stop_price=None,
            cancel_order_ids=("ord-orphan",),
        )
        tc = MagicMock()

        summary = execute_protective_stop_plans([plan], tc)

        tc.cancel_order_by_id.assert_called_once_with("ord-orphan")
        tc.submit_order.assert_not_called()
        assert summary["cancelled_orphans"] == 1

    def test_submit_failure_recorded_not_raised(self):
        from src.portfolio.fractional_stop_orders import execute_protective_stop_plans, ProtectiveStopPlan

        plan = ProtectiveStopPlan(action="create", symbol="AAPL", whole_qty=2, stop_price=88.0)
        tc = MagicMock()
        tc.submit_order.side_effect = RuntimeError("broker reject")

        summary = execute_protective_stop_plans([plan], tc)

        assert summary["created"] == 0
        assert len(summary["errors"]) == 1
        assert summary["errors"][0]["symbol"] == "AAPL"


class TestCancelOpenStopSells:
    """Regression fix for #62: a live GTC protective stop reserves the whole-share
    qty of a position, so any scheduler market SELL for the full qty is rejected by
    Alpaca with 40310000 "insufficient qty available" (verified live 2026-07-16
    18:22 UTC, SOXX/INTC). Every scheduler SELL path must cancel the symbol's open
    stop SELLs first to free the reserved shares."""

    def _stop_order(self, order_id="stop-1", symbol="SOXX"):
        from alpaca.trading.enums import OrderType

        o = MagicMock()
        o.id = order_id
        o.symbol = symbol
        o.type = OrderType.STOP
        return o

    def _limit_order(self, order_id="limit-1", symbol="SOXX"):
        from alpaca.trading.enums import OrderType

        o = MagicMock()
        o.id = order_id
        o.symbol = symbol
        o.type = OrderType.LIMIT
        return o

    def test_cancels_only_open_stop_sells_and_returns_count(self):
        from src.portfolio.fractional_stop_orders import cancel_open_stop_sells

        tc = MagicMock()
        tc.get_orders.return_value = [self._stop_order("stop-1"), self._limit_order("limit-1")]

        cancelled = cancel_open_stop_sells(tc, "SOXX")

        assert cancelled == 1
        tc.cancel_order_by_id.assert_called_once_with("stop-1")
        req = tc.get_orders.call_args[0][0]
        assert req.symbols == ["SOXX"]
        assert req.status.value == "open"

    def test_fail_open_when_get_orders_raises(self):
        from src.portfolio.fractional_stop_orders import cancel_open_stop_sells

        tc = MagicMock()
        tc.get_orders.side_effect = RuntimeError("api down")

        assert cancel_open_stop_sells(tc, "SOXX") == 0
        tc.cancel_order_by_id.assert_not_called()

    def test_single_cancel_failure_does_not_abort_remaining(self):
        from src.portfolio.fractional_stop_orders import cancel_open_stop_sells

        tc = MagicMock()
        tc.get_orders.return_value = [self._stop_order("stop-1"), self._stop_order("stop-2")]
        tc.cancel_order_by_id.side_effect = [RuntimeError("gone"), None]

        assert cancel_open_stop_sells(tc, "SOXX") == 1


class TestQtyAvailableSizing:
    """#113: stop qty must not exceed shares actually free to reserve."""

    def test_sizes_stop_to_available_when_shares_held_for_orders(self, stop_policy, cycle_ts):
        # 5 whole shares held, but only 2.3 free (rest reserved by a pending SELL).
        plan = _plan(
            position_qty=5.4, qty_available=2.3, avg_entry_price=100.0,
            stop_policy=stop_policy, cycle_ts=cycle_ts, existing_stop_orders=[],
        )
        assert plan.action == "create"
        assert plan.whole_qty == 2  # floor(2.3), NOT floor(5.4)

    def test_skip_when_no_shares_available(self, stop_policy, cycle_ts):
        plan = _plan(
            position_qty=5.4, qty_available=0.0, avg_entry_price=100.0,
            stop_policy=stop_policy, cycle_ts=cycle_ts, existing_stop_orders=[],
        )
        assert plan.action == "skip_insufficient_qty"
        assert plan.whole_qty == 0

    def test_replace_adds_back_own_reserved_shares(self, stop_policy, cycle_ts):
        # All 5 shares reserved by our OWN existing stop → qty_available reads 0,
        # but cancelling that stop frees them, so we must still size to 5.
        from src.portfolio.fractional_stop_orders import ExistingStopOrder

        existing = ExistingStopOrder(id="ord-1", qty=5, stop_price=70.0)
        plan = _plan(
            position_qty=5.4, qty_available=0.0, avg_entry_price=100.0,
            stop_policy=stop_policy, cycle_ts=cycle_ts, existing_stop_orders=[existing],
        )
        assert plan.action in ("replace", "noop")
        assert plan.whole_qty == 5

    def test_none_qty_available_keeps_legacy_full_size(self, stop_policy, cycle_ts):
        plan = _plan(
            position_qty=5.4, qty_available=None, avg_entry_price=100.0,
            stop_policy=stop_policy, cycle_ts=cycle_ts, existing_stop_orders=[],
        )
        assert plan.action == "create"
        assert plan.whole_qty == 5
