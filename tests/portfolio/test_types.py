"""T-501: Portfolio types — CombinedOrder, ConstraintViolation, PortfolioState."""
from __future__ import annotations

import pytest

from src.backtest.engine.types import Order, OrderSide
from src.portfolio.types import CombinedOrder, ConstraintViolation, PortfolioState


@pytest.fixture
def sample_order() -> Order:
    from datetime import datetime
    return Order.market_order(
        ts=datetime(2024, 1, 15),
        symbol="AAPL",
        side=OrderSide.BUY,
        qty=10.0,
        strategy_id="S1",
    )


# ── CombinedOrder ─────────────────────────────────────────────────────────────

def test_combined_order_from_order_stores_allocation_weight(sample_order):
    co = CombinedOrder.from_order(sample_order, allocation_weight=0.5)
    assert co.allocation_weight == pytest.approx(0.5)


def test_combined_order_from_order_preserves_symbol(sample_order):
    co = CombinedOrder.from_order(sample_order, allocation_weight=0.5)
    assert co.symbol == "AAPL"


def test_combined_order_from_order_preserves_side(sample_order):
    co = CombinedOrder.from_order(sample_order, allocation_weight=0.5)
    assert co.side == OrderSide.BUY


def test_combined_order_from_order_preserves_quantity(sample_order):
    co = CombinedOrder.from_order(sample_order, allocation_weight=0.5)
    assert co.quantity == pytest.approx(10.0)


def test_combined_order_from_order_preserves_strategy_id(sample_order):
    co = CombinedOrder.from_order(sample_order, allocation_weight=0.5)
    assert co.strategy_id == "S1"


def test_combined_order_is_frozen(sample_order):
    co = CombinedOrder.from_order(sample_order, allocation_weight=0.5)
    with pytest.raises((AttributeError, TypeError)):
        co.quantity = 99.0  # type: ignore[misc]


# ── ConstraintViolation ────────────────────────────────────────────────────────

def test_constraint_violation_stores_all_fields():
    v = ConstraintViolation(
        strategy_id="S1",
        constraint_name="MAX_SINGLE_ASSET_PCT",
        current_value=0.15,
        threshold=0.10,
    )
    assert v.strategy_id == "S1"
    assert v.constraint_name == "MAX_SINGLE_ASSET_PCT"
    assert v.current_value == pytest.approx(0.15)
    assert v.threshold == pytest.approx(0.10)


# ── PortfolioState ─────────────────────────────────────────────────────────────

def test_portfolio_state_stores_nav():
    state = PortfolioState(
        nav=100_000.0,
        per_strategy_exposure={"S1": 50_000.0},
        total_exposure=50_000.0,
        constraint_violations=[],
    )
    assert state.nav == pytest.approx(100_000.0)


def test_portfolio_state_stores_per_strategy_exposure():
    state = PortfolioState(
        nav=100_000.0,
        per_strategy_exposure={"S1": 50_000.0, "S2": 20_000.0},
        total_exposure=70_000.0,
        constraint_violations=[],
    )
    assert state.per_strategy_exposure["S1"] == pytest.approx(50_000.0)
    assert state.per_strategy_exposure["S2"] == pytest.approx(20_000.0)


def test_portfolio_state_stores_total_exposure():
    state = PortfolioState(
        nav=100_000.0,
        per_strategy_exposure={"S1": 50_000.0},
        total_exposure=50_000.0,
        constraint_violations=[],
    )
    assert state.total_exposure == pytest.approx(50_000.0)


def test_portfolio_state_with_violations():
    v = ConstraintViolation("S1", "MAX_PORTFOLIO_EXPOSURE", 0.6, 0.5)
    state = PortfolioState(
        nav=100_000.0,
        per_strategy_exposure={"S1": 60_000.0},
        total_exposure=60_000.0,
        constraint_violations=[v],
    )
    assert len(state.constraint_violations) == 1
    assert state.constraint_violations[0].strategy_id == "S1"


def test_portfolio_state_empty_violations():
    state = PortfolioState(
        nav=100_000.0,
        per_strategy_exposure={},
        total_exposure=0.0,
        constraint_violations=[],
    )
    assert state.constraint_violations == []
