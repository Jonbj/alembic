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

    def test_submit_failure_recorded_not_raised(self):
        from src.portfolio.fractional_stop_orders import execute_protective_stop_plans, ProtectiveStopPlan

        plan = ProtectiveStopPlan(action="create", symbol="AAPL", whole_qty=2, stop_price=88.0)
        tc = MagicMock()
        tc.submit_order.side_effect = RuntimeError("broker reject")

        summary = execute_protective_stop_plans([plan], tc)

        assert summary["created"] == 0
        assert len(summary["errors"]) == 1
        assert summary["errors"][0]["symbol"] == "AAPL"
