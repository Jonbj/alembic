"""T-501: ConstraintEnforcer tests."""
from __future__ import annotations

from datetime import datetime

import pytest

from src.backtest.engine.types import MarketSnapshot, Order, OrderSide
from src.portfolio.constraints import ConstraintEnforcer
from src.portfolio.types import CombinedOrder


# ── Helpers ────────────────────────────────────────────────────────────────────

def _market(prices_dict: dict) -> MarketSnapshot:
    return MarketSnapshot(
        timestamp=datetime(2024, 1, 15),
        prices=prices_dict,
        volumes={k: 1_000_000.0 for k in prices_dict},
        adv_20d={k: 1_000_000.0 for k in prices_dict},
    )


def _combined(symbol, side, qty, strategy_id, alloc_wt) -> CombinedOrder:
    order = Order.market_order(datetime(2024, 1, 15), symbol, side, qty, strategy_id)
    return CombinedOrder.from_order(order, allocation_weight=alloc_wt)


# unit-price market: notional == quantity, 10 assets for portfolio-exposure tests
@pytest.fixture
def unit_market():
    return _market({f"A{i}": 1.0 for i in range(10)})


@pytest.fixture
def std_allocations():
    return {"S1": 0.5, "S2": 0.2, "S4": 0.3}


# ── No-violation baseline ──────────────────────────────────────────────────────

def test_no_violations_all_orders_unchanged(unit_market, std_allocations):
    # 4 orders × 80 each = 320 < 50% of 1000 (=500); each 80 < 10% of 1000 (=100)
    orders = [_combined(f"A{i}", OrderSide.BUY, 80.0, "S1", 0.5) for i in range(4)]
    enforcer = ConstraintEnforcer()
    result, violations = enforcer.enforce(orders, unit_market, nav=1000.0, allocations=std_allocations)
    assert violations == []
    assert all(o.quantity == pytest.approx(80.0) for o in result)


# ── MAX_SINGLE_ASSET_PCT ───────────────────────────────────────────────────────

def test_single_asset_reduces_oversized_buy(unit_market, std_allocations):
    # A0 @ 1.0, qty=200, nav=1000 → notional=200=20% > 10% → reduce to 100
    enforcer = ConstraintEnforcer(max_single_asset_pct=0.10, max_portfolio_exposure=10.0, max_strategy_overshoot=100.0)
    orders = [_combined("A0", OrderSide.BUY, 200.0, "S1", 0.5)]
    result, violations = enforcer.enforce(orders, unit_market, nav=1000.0, allocations=std_allocations)
    assert result[0].quantity == pytest.approx(100.0)


def test_single_asset_records_violation(unit_market, std_allocations):
    enforcer = ConstraintEnforcer(max_single_asset_pct=0.10, max_portfolio_exposure=10.0, max_strategy_overshoot=100.0)
    orders = [_combined("A0", OrderSide.BUY, 200.0, "S1", 0.5)]
    result, violations = enforcer.enforce(orders, unit_market, nav=1000.0, allocations=std_allocations)
    assert len(violations) == 1
    assert violations[0].constraint_name == "MAX_SINGLE_ASSET_PCT"


def test_single_asset_violation_carries_strategy_id(unit_market, std_allocations):
    enforcer = ConstraintEnforcer(max_single_asset_pct=0.10, max_portfolio_exposure=10.0, max_strategy_overshoot=100.0)
    orders = [_combined("A0", OrderSide.BUY, 200.0, "S1", 0.5)]
    result, violations = enforcer.enforce(orders, unit_market, nav=1000.0, allocations=std_allocations)
    assert violations[0].strategy_id == "S1"


def test_single_asset_sell_orders_not_constrained(unit_market, std_allocations):
    enforcer = ConstraintEnforcer(max_single_asset_pct=0.10, max_portfolio_exposure=10.0, max_strategy_overshoot=100.0)
    orders = [_combined("A0", OrderSide.SELL, 500.0, "S1", 0.5)]
    result, violations = enforcer.enforce(orders, unit_market, nav=1000.0, allocations=std_allocations)
    assert violations == []
    assert result[0].quantity == pytest.approx(500.0)


def test_single_asset_exactly_at_limit_no_violation(unit_market, std_allocations):
    # qty=100 @ 1.0 = 100 = exactly 10% of 1000 → no violation
    enforcer = ConstraintEnforcer(max_single_asset_pct=0.10, max_portfolio_exposure=10.0, max_strategy_overshoot=100.0)
    orders = [_combined("A0", OrderSide.BUY, 100.0, "S1", 0.5)]
    result, violations = enforcer.enforce(orders, unit_market, nav=1000.0, allocations=std_allocations)
    assert violations == []
    assert result[0].quantity == pytest.approx(100.0)


def test_single_asset_violation_records_correct_values(unit_market, std_allocations):
    enforcer = ConstraintEnforcer(max_single_asset_pct=0.10, max_portfolio_exposure=10.0, max_strategy_overshoot=100.0)
    orders = [_combined("A0", OrderSide.BUY, 200.0, "S1", 0.5)]
    result, violations = enforcer.enforce(orders, unit_market, nav=1000.0, allocations=std_allocations)
    assert violations[0].threshold == pytest.approx(0.10)
    assert violations[0].current_value == pytest.approx(0.20)  # 200/1000


# ── MAX_STRATEGY_EXPOSURE ──────────────────────────────────────────────────────

def test_strategy_exposure_reduces_oversized_strategy(unit_market, std_allocations):
    # S1 alloc=50%, overshoot=1.5 → cap=75% of nav=1000 → 750
    # 8 orders × 100 = 800 > 750 → scale 750/800=0.9375 → each 93.75
    enforcer = ConstraintEnforcer(max_single_asset_pct=1.0, max_portfolio_exposure=10.0, max_strategy_overshoot=1.5)
    orders = [_combined(f"A{i}", OrderSide.BUY, 100.0, "S1", 0.5) for i in range(8)]
    result, violations = enforcer.enforce(orders, unit_market, nav=1000.0, allocations=std_allocations)
    total_qty = sum(o.quantity for o in result)
    assert total_qty == pytest.approx(750.0)


def test_strategy_exposure_within_limit_unchanged(unit_market, std_allocations):
    # S1 alloc=50%, cap=750; 7 orders × 100 = 700 < 750 → no change
    enforcer = ConstraintEnforcer(max_single_asset_pct=1.0, max_portfolio_exposure=10.0, max_strategy_overshoot=1.5)
    orders = [_combined(f"A{i}", OrderSide.BUY, 100.0, "S1", 0.5) for i in range(7)]
    result, violations = enforcer.enforce(orders, unit_market, nav=1000.0, allocations=std_allocations)
    assert violations == []
    assert all(o.quantity == pytest.approx(100.0) for o in result)


def test_strategy_exposure_records_violation(unit_market, std_allocations):
    enforcer = ConstraintEnforcer(max_single_asset_pct=1.0, max_portfolio_exposure=10.0, max_strategy_overshoot=1.5)
    orders = [_combined(f"A{i}", OrderSide.BUY, 100.0, "S1", 0.5) for i in range(8)]
    result, violations = enforcer.enforce(orders, unit_market, nav=1000.0, allocations=std_allocations)
    names = [v.constraint_name for v in violations]
    assert "MAX_STRATEGY_EXPOSURE" in names


def test_strategy_exposure_only_reduces_that_strategy(unit_market, std_allocations):
    # S1 violates, S2 does not; S2 orders should be untouched
    enforcer = ConstraintEnforcer(max_single_asset_pct=1.0, max_portfolio_exposure=10.0, max_strategy_overshoot=1.5)
    s1_orders = [_combined(f"A{i}", OrderSide.BUY, 100.0, "S1", 0.5) for i in range(8)]
    s2_orders = [_combined("A8", OrderSide.BUY, 50.0, "S2", 0.2)]  # 50 < 20%*1.5*1000=300
    result, violations = enforcer.enforce(s1_orders + s2_orders, unit_market, nav=1000.0, allocations=std_allocations)
    s2_result = [o for o in result if o.strategy_id == "S2"]
    assert s2_result[0].quantity == pytest.approx(50.0)


# ── MAX_PORTFOLIO_EXPOSURE ─────────────────────────────────────────────────────

def test_portfolio_exposure_reduces_all_buy_orders_proportionally(unit_market, std_allocations):
    # 7 orders × 90 = 630 > 50% of 1000 (=500) → scale 500/630 ≈ 0.7937
    enforcer = ConstraintEnforcer(max_single_asset_pct=1.0, max_portfolio_exposure=0.5, max_strategy_overshoot=100.0)
    orders = [_combined(f"A{i}", OrderSide.BUY, 90.0, "S1", 0.5) for i in range(7)]
    result, violations = enforcer.enforce(orders, unit_market, nav=1000.0, allocations=std_allocations)
    total_qty = sum(o.quantity for o in result)
    assert total_qty == pytest.approx(500.0, rel=1e-4)


def test_portfolio_exposure_within_limit_no_reduction(unit_market, std_allocations):
    # 4 orders × 90 = 360 < 50% of 1000 (=500)
    enforcer = ConstraintEnforcer(max_single_asset_pct=1.0, max_portfolio_exposure=0.5, max_strategy_overshoot=100.0)
    orders = [_combined(f"A{i}", OrderSide.BUY, 90.0, "S1", 0.5) for i in range(4)]
    result, violations = enforcer.enforce(orders, unit_market, nav=1000.0, allocations=std_allocations)
    assert violations == []
    assert all(o.quantity == pytest.approx(90.0) for o in result)


def test_portfolio_exposure_records_violation(unit_market, std_allocations):
    enforcer = ConstraintEnforcer(max_single_asset_pct=1.0, max_portfolio_exposure=0.5, max_strategy_overshoot=100.0)
    orders = [_combined(f"A{i}", OrderSide.BUY, 90.0, "S1", 0.5) for i in range(7)]
    result, violations = enforcer.enforce(orders, unit_market, nav=1000.0, allocations=std_allocations)
    names = [v.constraint_name for v in violations]
    assert "MAX_PORTFOLIO_EXPOSURE" in names


def test_portfolio_exposure_sell_orders_not_scaled(unit_market, std_allocations):
    # Mix of BUY (violating) and SELL (should not be scaled)
    enforcer = ConstraintEnforcer(max_single_asset_pct=1.0, max_portfolio_exposure=0.5, max_strategy_overshoot=100.0)
    buy_orders = [_combined(f"A{i}", OrderSide.BUY, 90.0, "S1", 0.5) for i in range(7)]
    sell_order = _combined("A9", OrderSide.SELL, 200.0, "S1", 0.5)
    result, violations = enforcer.enforce(buy_orders + [sell_order], unit_market, nav=1000.0, allocations=std_allocations)
    sell_result = [o for o in result if o.side == OrderSide.SELL]
    assert sell_result[0].quantity == pytest.approx(200.0)


def test_portfolio_exposure_proportional_scaling_preserves_ratios(unit_market, std_allocations):
    # Two BUY orders with different sizes; ratio should be preserved after scaling
    enforcer = ConstraintEnforcer(max_single_asset_pct=1.0, max_portfolio_exposure=0.5, max_strategy_overshoot=100.0)
    o1 = _combined("A0", OrderSide.BUY, 300.0, "S1", 0.5)
    o2 = _combined("A1", OrderSide.BUY, 300.0, "S1", 0.5)
    result, violations = enforcer.enforce([o1, o2], unit_market, nav=1000.0, allocations=std_allocations)
    # Both 300 each = 600 > 500; scale to 250 each
    assert result[0].quantity == pytest.approx(result[1].quantity)
    assert result[0].quantity == pytest.approx(250.0)


# ── Edge cases ─────────────────────────────────────────────────────────────────

def test_zero_nav_returns_empty(unit_market, std_allocations):
    enforcer = ConstraintEnforcer()
    orders = [_combined("A0", OrderSide.BUY, 100.0, "S1", 0.5)]
    result, violations = enforcer.enforce(orders, unit_market, nav=0.0, allocations=std_allocations)
    assert result == []
    assert violations == []


def test_empty_orders_returns_empty_no_violations(unit_market, std_allocations):
    enforcer = ConstraintEnforcer()
    result, violations = enforcer.enforce([], unit_market, nav=100_000.0, allocations=std_allocations)
    assert result == []
    assert violations == []


def test_multiple_violations_all_recorded(unit_market, std_allocations):
    # Two assets each violate single-asset cap (80 > 5%*1000=50), then after
    # reduction to 50 each the combined 100 still exceeds the strategy cap
    # (S1=50%, overshoot=0.15 → cap=75). Both constraint types must be recorded.
    enforcer = ConstraintEnforcer(
        max_single_asset_pct=0.05, max_portfolio_exposure=10.0, max_strategy_overshoot=0.15
    )
    orders = [
        _combined("A0", OrderSide.BUY, 80.0, "S1", 0.5),
        _combined("A1", OrderSide.BUY, 80.0, "S1", 0.5),
    ]
    result, violations = enforcer.enforce(orders, unit_market, nav=1000.0, allocations=std_allocations)
    constraint_names = [v.constraint_name for v in violations]
    assert "MAX_SINGLE_ASSET_PCT" in constraint_names
    assert "MAX_STRATEGY_EXPOSURE" in constraint_names
