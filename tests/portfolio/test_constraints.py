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


# ── MAX_SECTOR_EXPOSURE ────────────────────────────────────────────────────────

def test_sector_exposure_reduces_orders_when_sector_exceeds_25pct(unit_market, std_allocations):
    # tech: A0(150) + A1(150) = 300 > 25%*1000=250 → scale to 250
    sector_map = {"A0": "tech", "A1": "tech"}
    enforcer = ConstraintEnforcer(
        max_single_asset_pct=1.0, max_portfolio_exposure=10.0,
        max_strategy_overshoot=100.0, sector_map=sector_map,
    )
    orders = [
        _combined("A0", OrderSide.BUY, 150.0, "S1", 0.5),
        _combined("A1", OrderSide.BUY, 150.0, "S1", 0.5),
    ]
    result, _ = enforcer.enforce(orders, unit_market, nav=1000.0, allocations=std_allocations)
    total_qty = sum(o.quantity for o in result)
    assert total_qty == pytest.approx(250.0)


def test_sector_exposure_at_limit_no_violation(unit_market, std_allocations):
    # tech: 125 + 125 = 250 = exactly 25% → no sector violation
    sector_map = {"A0": "tech", "A1": "tech"}
    enforcer = ConstraintEnforcer(
        max_single_asset_pct=1.0, max_portfolio_exposure=10.0,
        max_strategy_overshoot=100.0, sector_map=sector_map,
    )
    orders = [
        _combined("A0", OrderSide.BUY, 125.0, "S1", 0.5),
        _combined("A1", OrderSide.BUY, 125.0, "S1", 0.5),
    ]
    _, violations = enforcer.enforce(orders, unit_market, nav=1000.0, allocations=std_allocations)
    assert not any(v.constraint_name == "MAX_SECTOR_EXPOSURE" for v in violations)


def test_sector_exposure_records_constraint_name(unit_market, std_allocations):
    sector_map = {"A0": "tech", "A1": "tech"}
    enforcer = ConstraintEnforcer(
        max_single_asset_pct=1.0, max_portfolio_exposure=10.0,
        max_strategy_overshoot=100.0, sector_map=sector_map,
    )
    orders = [
        _combined("A0", OrderSide.BUY, 150.0, "S1", 0.5),
        _combined("A1", OrderSide.BUY, 150.0, "S1", 0.5),
    ]
    _, violations = enforcer.enforce(orders, unit_market, nav=1000.0, allocations=std_allocations)
    assert any(v.constraint_name == "MAX_SECTOR_EXPOSURE" for v in violations)


def test_sector_exposure_violation_carries_strategy_id(unit_market, std_allocations):
    sector_map = {"A0": "tech", "A1": "tech"}
    enforcer = ConstraintEnforcer(
        max_single_asset_pct=1.0, max_portfolio_exposure=10.0,
        max_strategy_overshoot=100.0, sector_map=sector_map,
    )
    orders = [
        _combined("A0", OrderSide.BUY, 150.0, "S1", 0.5),
        _combined("A1", OrderSide.BUY, 150.0, "S1", 0.5),
    ]
    _, violations = enforcer.enforce(orders, unit_market, nav=1000.0, allocations=std_allocations)
    sector_v = [v for v in violations if v.constraint_name == "MAX_SECTOR_EXPOSURE"]
    assert sector_v
    assert all(v.strategy_id != "" for v in sector_v)


def test_sector_exposure_sell_orders_not_constrained(unit_market, std_allocations):
    sector_map = {"A0": "tech"}
    enforcer = ConstraintEnforcer(
        max_single_asset_pct=1.0, max_portfolio_exposure=10.0,
        max_strategy_overshoot=100.0, sector_map=sector_map,
    )
    orders = [_combined("A0", OrderSide.SELL, 500.0, "S1", 0.5)]
    result, violations = enforcer.enforce(orders, unit_market, nav=1000.0, allocations=std_allocations)
    assert not any(v.constraint_name == "MAX_SECTOR_EXPOSURE" for v in violations)
    assert result[0].quantity == pytest.approx(500.0)


def test_sector_exposure_only_violating_sector_reduced(unit_market, std_allocations):
    # tech violates (300 > 250), energy does not (50 < 250)
    sector_map = {"A0": "tech", "A1": "tech", "A2": "energy"}
    enforcer = ConstraintEnforcer(
        max_single_asset_pct=1.0, max_portfolio_exposure=10.0,
        max_strategy_overshoot=100.0, sector_map=sector_map,
    )
    orders = [
        _combined("A0", OrderSide.BUY, 150.0, "S1", 0.5),
        _combined("A1", OrderSide.BUY, 150.0, "S1", 0.5),
        _combined("A2", OrderSide.BUY, 50.0, "S2", 0.3),
    ]
    result, _ = enforcer.enforce(orders, unit_market, nav=1000.0, allocations=std_allocations)
    energy_order = next(o for o in result if o.symbol == "A2")
    assert energy_order.quantity == pytest.approx(50.0)


def test_sector_exposure_none_map_disables_constraint(unit_market, std_allocations):
    # No sector_map → sector constraint not applied even if exposure > 25%
    enforcer = ConstraintEnforcer(
        max_single_asset_pct=1.0, max_portfolio_exposure=10.0,
        max_strategy_overshoot=100.0,
    )
    orders = [
        _combined("A0", OrderSide.BUY, 150.0, "S1", 0.5),
        _combined("A1", OrderSide.BUY, 150.0, "S1", 0.5),
    ]
    _, violations = enforcer.enforce(orders, unit_market, nav=1000.0, allocations=std_allocations)
    assert not any(v.constraint_name == "MAX_SECTOR_EXPOSURE" for v in violations)


def test_sector_exposure_unknown_sector_tickers_grouped(unit_market, std_allocations):
    # empty sector_map → A0 and A1 both → "unknown" sector; total 300 > 250 → reduced
    enforcer = ConstraintEnforcer(
        max_single_asset_pct=1.0, max_portfolio_exposure=10.0,
        max_strategy_overshoot=100.0, sector_map={},
    )
    orders = [
        _combined("A0", OrderSide.BUY, 150.0, "S1", 0.5),
        _combined("A1", OrderSide.BUY, 150.0, "S1", 0.5),
    ]
    result, _ = enforcer.enforce(orders, unit_market, nav=1000.0, allocations=std_allocations)
    total_qty = sum(o.quantity for o in result)
    assert total_qty == pytest.approx(250.0)


# ── MAX_CORRELATION_CLUSTER ────────────────────────────────────────────────────

# S2 returns = 2×S1 → perfect correlation, higher volatility
_S1_RETURNS = [0.01, 0.02, 0.03, 0.04, 0.05]
_S2_RETURNS = [0.02, 0.04, 0.06, 0.08, 0.10]
# Low correlation with S1 (computed corr ≈ -0.31)
_S3_UNCORR = [0.05, -0.03, 0.04, -0.02, 0.01]


def test_correlation_reduces_higher_vol_strategy(unit_market, std_allocations):
    # S2 perfectly correlated with S1 and has higher std dev → S2 reduced
    enforcer = ConstraintEnforcer(
        max_single_asset_pct=1.0, max_portfolio_exposure=10.0,
        max_strategy_overshoot=100.0,
        strategy_returns={"S1": _S1_RETURNS, "S2": _S2_RETURNS},
    )
    orders = [
        _combined("A0", OrderSide.BUY, 100.0, "S1", 0.5),
        _combined("A1", OrderSide.BUY, 100.0, "S2", 0.3),
    ]
    result, _ = enforcer.enforce(orders, unit_market, nav=1000.0, allocations=std_allocations)
    s1_order = next(o for o in result if o.strategy_id == "S1")
    s2_order = next(o for o in result if o.strategy_id == "S2")
    assert s1_order.quantity == pytest.approx(100.0)
    assert s2_order.quantity < 100.0


def test_correlation_reduces_by_exactly_20_percent(unit_market, std_allocations):
    enforcer = ConstraintEnforcer(
        max_single_asset_pct=1.0, max_portfolio_exposure=10.0,
        max_strategy_overshoot=100.0,
        strategy_returns={"S1": _S1_RETURNS, "S2": _S2_RETURNS},
    )
    orders = [
        _combined("A0", OrderSide.BUY, 100.0, "S1", 0.5),
        _combined("A1", OrderSide.BUY, 100.0, "S2", 0.3),
    ]
    result, _ = enforcer.enforce(orders, unit_market, nav=1000.0, allocations=std_allocations)
    s2_order = next(o for o in result if o.strategy_id == "S2")
    assert s2_order.quantity == pytest.approx(80.0)


def test_correlation_below_threshold_no_reduction(unit_market, std_allocations):
    enforcer = ConstraintEnforcer(
        max_single_asset_pct=1.0, max_portfolio_exposure=10.0,
        max_strategy_overshoot=100.0,
        strategy_returns={"S1": _S1_RETURNS, "S2": _S3_UNCORR},
    )
    orders = [
        _combined("A0", OrderSide.BUY, 100.0, "S1", 0.5),
        _combined("A1", OrderSide.BUY, 100.0, "S2", 0.3),
    ]
    result, violations = enforcer.enforce(orders, unit_market, nav=1000.0, allocations=std_allocations)
    assert not any(v.constraint_name == "MAX_CORRELATION_CLUSTER" for v in violations)
    assert all(o.quantity == pytest.approx(100.0) for o in result)


def test_correlation_violation_records_constraint_name(unit_market, std_allocations):
    enforcer = ConstraintEnforcer(
        max_single_asset_pct=1.0, max_portfolio_exposure=10.0,
        max_strategy_overshoot=100.0,
        strategy_returns={"S1": _S1_RETURNS, "S2": _S2_RETURNS},
    )
    orders = [
        _combined("A0", OrderSide.BUY, 100.0, "S1", 0.5),
        _combined("A1", OrderSide.BUY, 100.0, "S2", 0.3),
    ]
    _, violations = enforcer.enforce(orders, unit_market, nav=1000.0, allocations=std_allocations)
    assert any(v.constraint_name == "MAX_CORRELATION_CLUSTER" for v in violations)


def test_correlation_violation_carries_strategy_id(unit_market, std_allocations):
    # S2 is the higher-vol strategy → violation strategy_id = "S2"
    enforcer = ConstraintEnforcer(
        max_single_asset_pct=1.0, max_portfolio_exposure=10.0,
        max_strategy_overshoot=100.0,
        strategy_returns={"S1": _S1_RETURNS, "S2": _S2_RETURNS},
    )
    orders = [
        _combined("A0", OrderSide.BUY, 100.0, "S1", 0.5),
        _combined("A1", OrderSide.BUY, 100.0, "S2", 0.3),
    ]
    _, violations = enforcer.enforce(orders, unit_market, nav=1000.0, allocations=std_allocations)
    corr_v = [v for v in violations if v.constraint_name == "MAX_CORRELATION_CLUSTER"]
    assert corr_v
    assert corr_v[0].strategy_id == "S2"


def test_correlation_empty_returns_no_constraint(unit_market, std_allocations):
    enforcer = ConstraintEnforcer(
        max_single_asset_pct=1.0, max_portfolio_exposure=10.0,
        max_strategy_overshoot=100.0, strategy_returns={},
    )
    orders = [
        _combined("A0", OrderSide.BUY, 100.0, "S1", 0.5),
        _combined("A1", OrderSide.BUY, 100.0, "S2", 0.3),
    ]
    result, violations = enforcer.enforce(orders, unit_market, nav=1000.0, allocations=std_allocations)
    assert not any(v.constraint_name == "MAX_CORRELATION_CLUSTER" for v in violations)
    assert all(o.quantity == pytest.approx(100.0) for o in result)


def test_correlation_insufficient_data_no_constraint(unit_market, std_allocations):
    # Only 1 data point per strategy → can't compute meaningful correlation
    enforcer = ConstraintEnforcer(
        max_single_asset_pct=1.0, max_portfolio_exposure=10.0,
        max_strategy_overshoot=100.0,
        strategy_returns={"S1": [0.05], "S2": [0.05]},
    )
    orders = [
        _combined("A0", OrderSide.BUY, 100.0, "S1", 0.5),
        _combined("A1", OrderSide.BUY, 100.0, "S2", 0.3),
    ]
    result, violations = enforcer.enforce(orders, unit_market, nav=1000.0, allocations=std_allocations)
    assert not any(v.constraint_name == "MAX_CORRELATION_CLUSTER" for v in violations)


# ── Iterative resolution ───────────────────────────────────────────────────────

def test_iterative_resolution_converges(std_allocations):
    # A0 and A1 each 200, single_asset cap=15% (150), sector=tech (cap=25%=250)
    # Pass 1: single_asset reduces each to 150; sector reduces to 125 each (300→250)
    # Pass 2: 125 ≤ 150 and 250 ≤ 250 → no violations → exits early
    market = _market({"A0": 1.0, "A1": 1.0})
    sector_map = {"A0": "tech", "A1": "tech"}
    enforcer = ConstraintEnforcer(
        max_single_asset_pct=0.15, max_portfolio_exposure=10.0,
        max_strategy_overshoot=100.0, sector_map=sector_map,
    )
    orders = [
        _combined("A0", OrderSide.BUY, 200.0, "S1", 0.5),
        _combined("A1", OrderSide.BUY, 200.0, "S1", 0.5),
    ]
    result, violations = enforcer.enforce(orders, market, nav=1000.0, allocations=std_allocations)
    assert any(v.constraint_name == "MAX_SINGLE_ASSET_PCT" for v in violations)
    assert any(v.constraint_name == "MAX_SECTOR_EXPOSURE" for v in violations)
    for o in result:
        assert o.quantity * 1.0 <= 0.15 * 1000.0 + 1e-9
    tech_total = sum(o.quantity for o in result if o.side == OrderSide.BUY)
    assert tech_total <= 0.25 * 1000.0 + 1e-9


def test_iterative_no_violations_completes_without_error(unit_market, std_allocations):
    # Clean scenario: no constraints fired → exits after first pass with no violations
    enforcer = ConstraintEnforcer()
    orders = [_combined(f"A{i}", OrderSide.BUY, 10.0, "S1", 0.5) for i in range(5)]
    result, violations = enforcer.enforce(orders, unit_market, nav=1000.0, allocations=std_allocations)
    assert violations == []
    assert all(o.quantity == pytest.approx(10.0) for o in result)


# ── Config-driven sector cap (max_sector_pct constructor param) ────────────────


class TestSectorCapConfig:
    def _orders_two_semis(self):
        # Two BUY orders in the same sector totalling 30% of a 100k NAV, using
        # the file's existing helpers. Unit-price market (like unit_market)
        # keeps notional == quantity: 15,000 qty each == $15,000 notional each.
        market = _market({"NVDA": 1.0, "AMD": 1.0})
        orders = [
            _combined("NVDA", OrderSide.BUY, 15_000.0, "S1", 0.5),
            _combined("AMD", OrderSide.BUY, 15_000.0, "S1", 0.5),
        ]
        return orders, market

    def test_sector_cap_param_overrides_module_default(self):
        # Isolate the sector constraint from MAX_SINGLE_ASSET_PCT (default 0.10
        # would otherwise scale each $15k order down to $10k first, landing
        # exactly at the 20% sector cap with no violation) — same isolation
        # pattern as every other MAX_SECTOR_EXPOSURE test in this file.
        enforcer = ConstraintEnforcer(
            sector_map={"NVDA": "semis", "AMD": "semis"},
            max_sector_pct=0.20,
            max_single_asset_pct=1.0, max_portfolio_exposure=10.0,
            max_strategy_overshoot=100.0,
        )
        orders, market = self._orders_two_semis()
        result, violations = enforcer.enforce(orders, market, nav=100_000, allocations={})
        assert any(v.constraint_name == "MAX_SECTOR_EXPOSURE" for v in violations)
        total = sum(o.quantity * market.price_of(o.symbol) for o in result if o.side.value == "BUY")
        assert total <= 0.20 * 100_000 + 1e-6

    def test_sector_cap_zero_disables(self):
        enforcer = ConstraintEnforcer(
            sector_map={"NVDA": "semis", "AMD": "semis"},
            max_sector_pct=0.0,
            max_single_asset_pct=1.0, max_portfolio_exposure=10.0,
            max_strategy_overshoot=100.0,
        )
        orders, market = self._orders_two_semis()
        _, violations = enforcer.enforce(orders, market, nav=100_000, allocations={})
        assert not any(v.constraint_name == "MAX_SECTOR_EXPOSURE" for v in violations)

    def test_default_unchanged_without_param(self):
        """Backtests constructing ConstraintEnforcer(sector_map=...) without the
        new param keep the historical 0.25 behavior."""
        enforcer = ConstraintEnforcer(sector_map={"NVDA": "semis"})
        assert enforcer._max_sector_pct == 0.25
