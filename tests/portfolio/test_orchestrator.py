"""T-601: PortfolioOrchestrator tests."""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from src.backtest.engine.data_replay import DataReplay
from src.backtest.engine.portfolio import VirtualPortfolio
from src.backtest.engine.types import MarketSnapshot, Order, OrderSide
from src.portfolio.constraints import ConstraintEnforcer
from src.portfolio.orchestrator import CycleResult, PortfolioOrchestrator
from src.portfolio.vol_targeting import PortfolioVolTargeter
from src.strategies.registry import StrategyEntry, StrategyRegistry


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_registry(entries: list[StrategyEntry]) -> StrategyRegistry:
    registry = StrategyRegistry(load_defaults=False)
    for e in entries:
        registry.register(e)
    return registry


def _make_market(symbols: tuple = ("AAPL",)) -> MarketSnapshot:
    return MarketSnapshot(
        timestamp=datetime(2024, 1, 15),
        prices={s: 100.0 for s in symbols},
        volumes={s: 1_000_000.0 for s in symbols},
        adv_20d={s: 1_000_000.0 for s in symbols},
    )


def _make_data_replay() -> DataReplay:
    dates = pd.date_range("2023-01-01", periods=50, freq="B")
    prices = pd.DataFrame({"AAPL": np.ones(50) * 100.0}, index=dates)
    return DataReplay(prices)


def _make_portfolio(cash: float = 100_000.0) -> VirtualPortfolio:
    return VirtualPortfolio(initial_cash=cash)


def _make_order(
    symbol: str = "AAPL",
    side: OrderSide = OrderSide.BUY,
    qty: float = 10.0,
    strategy_id: str = "S1",
) -> Order:
    return Order.market_order(datetime(2024, 1, 15), symbol, side, qty, strategy_id)


class _FixedStrategy:
    """Returns a preset list of orders on every call."""
    def __init__(self, orders=None):
        self.orders = orders or []
        self.call_count = 0

    def __call__(self, ts, data_replay, portfolio, market):
        self.call_count += 1
        return self.orders


class _ErrorStrategy:
    """Always raises to test graceful error handling."""
    def __call__(self, ts, data_replay, portfolio, market):
        raise RuntimeError("Strategy failure")


# ── CycleResult ───────────────────────────────────────────────────────────────

def test_cycle_result_has_strategies_run_field():
    result = CycleResult(
        strategies_run=["S1"],
        orders_per_strategy={"S1": 2},
        orders_before_constraints=2,
        orders_after_constraints=2,
        constraints_fired=[],
        final_orders=[],
    )
    assert result.strategies_run == ["S1"]


def test_cycle_result_has_orders_count_fields():
    result = CycleResult(
        strategies_run=["S1"],
        orders_per_strategy={"S1": 3},
        orders_before_constraints=3,
        orders_after_constraints=2,
        constraints_fired=[],
        final_orders=[],
    )
    assert result.orders_before_constraints == 3
    assert result.orders_after_constraints == 2


def test_cycle_result_has_constraints_fired_field():
    result = CycleResult(
        strategies_run=[],
        orders_per_strategy={},
        orders_before_constraints=0,
        orders_after_constraints=0,
        constraints_fired=[],
        final_orders=[],
    )
    assert result.constraints_fired == []


# ── PortfolioOrchestrator basic ───────────────────────────────────────────────

def test_orchestrator_returns_cycle_result():
    entry = StrategyEntry("S1", _FixedStrategy, 1.0, "30 14 * * 1-5")
    registry = _make_registry([entry])
    orch = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S1": _FixedStrategy()},
        constraint_enforcer=ConstraintEnforcer(),
    )
    result = orch.run_cycle(
        ts=datetime(2024, 1, 15),
        data_replay=_make_data_replay(),
        portfolio=_make_portfolio(),
        market=_make_market(),
    )
    assert isinstance(result, CycleResult)


def test_orchestrator_calls_all_active_strategies():
    s1 = _FixedStrategy([_make_order(strategy_id="S1")])
    s2 = _FixedStrategy([_make_order(strategy_id="S2")])
    entries = [
        StrategyEntry("S1", _FixedStrategy, 0.6, "30 14 * * 1-5"),
        StrategyEntry("S2", _FixedStrategy, 0.4, "30 14 * * 1-5"),
    ]
    registry = _make_registry(entries)
    orch = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S1": s1, "S2": s2},
        constraint_enforcer=ConstraintEnforcer(),
    )
    orch.run_cycle(
        ts=datetime(2024, 1, 15),
        data_replay=_make_data_replay(),
        portfolio=_make_portfolio(),
        market=_make_market(),
    )
    assert s1.call_count == 1
    assert s2.call_count == 1


def test_orchestrator_strategies_run_matches_active():
    s1 = _FixedStrategy()
    s2 = _FixedStrategy()
    entries = [
        StrategyEntry("S1", _FixedStrategy, 0.6, "30 14 * * 1-5"),
        StrategyEntry("S2", _FixedStrategy, 0.4, "30 14 * * 1-5"),
    ]
    registry = _make_registry(entries)
    orch = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S1": s1, "S2": s2},
        constraint_enforcer=ConstraintEnforcer(),
    )
    result = orch.run_cycle(
        ts=datetime(2024, 1, 15),
        data_replay=_make_data_replay(),
        portfolio=_make_portfolio(),
        market=_make_market(),
    )
    assert set(result.strategies_run) == {"S1", "S2"}


def test_orchestrator_orders_per_strategy():
    """With weight-then-order, orders_per_strategy counts unique symbols in target weights."""
    s1 = _FixedStrategy([
        _make_order(strategy_id="S1"),
        _make_order(strategy_id="S1"),
    ])
    entries = [StrategyEntry("S1", _FixedStrategy, 1.0, "30 14 * * 1-5")]
    registry = _make_registry(entries)
    orch = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S1": s1},
        constraint_enforcer=ConstraintEnforcer(),
    )
    result = orch.run_cycle(
        ts=datetime(2024, 1, 15),
        data_replay=_make_data_replay(),
        portfolio=_make_portfolio(),
        market=_make_market(),
    )
    # Same symbol AAPL appears once in target weights
    assert result.orders_per_strategy["S1"] >= 1


def test_orchestrator_orders_before_constraints_count():
    """With weight-then-order, both strategies target AAPL → merged into 1 delta order."""
    s1 = _FixedStrategy([_make_order(strategy_id="S1")])
    s2 = _FixedStrategy([_make_order(strategy_id="S2")])
    entries = [
        StrategyEntry("S1", _FixedStrategy, 0.6, "30 14 * * 1-5"),
        StrategyEntry("S2", _FixedStrategy, 0.4, "30 14 * * 1-5"),
    ]
    registry = _make_registry(entries)
    orch = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S1": s1, "S2": s2},
        constraint_enforcer=ConstraintEnforcer(),
    )
    result = orch.run_cycle(
        ts=datetime(2024, 1, 15),
        data_replay=_make_data_replay(),
        portfolio=_make_portfolio(),
        market=_make_market(),
    )
    # Both target AAPL → 1 merged delta order
    assert result.orders_before_constraints >= 1


def test_orchestrator_empty_strategies_returns_empty_result():
    registry = _make_registry([])
    orch = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={},
        constraint_enforcer=ConstraintEnforcer(),
    )
    result = orch.run_cycle(
        ts=datetime(2024, 1, 15),
        data_replay=_make_data_replay(),
        portfolio=_make_portfolio(),
        market=_make_market(),
    )
    assert result.strategies_run == []
    assert result.final_orders == []


def test_orchestrator_disabled_strategy_not_called():
    s1 = _FixedStrategy([_make_order(strategy_id="S1")])
    s2 = _FixedStrategy([_make_order(strategy_id="S2")])
    entries = [
        StrategyEntry("S1", _FixedStrategy, 0.6, "30 14 * * 1-5", enabled=True),
        StrategyEntry("S2", _FixedStrategy, 0.4, "30 14 * * 1-5", enabled=False),
    ]
    registry = _make_registry(entries)
    orch = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S1": s1, "S2": s2},
        constraint_enforcer=ConstraintEnforcer(),
    )
    result = orch.run_cycle(
        ts=datetime(2024, 1, 15),
        data_replay=_make_data_replay(),
        portfolio=_make_portfolio(),
        market=_make_market(),
    )
    assert s2.call_count == 0
    assert "S2" not in result.strategies_run


def test_orchestrator_handles_strategy_exception_gracefully():
    err_strategy = _ErrorStrategy()
    s1 = _FixedStrategy([_make_order(strategy_id="S1")])
    entries = [
        StrategyEntry("S1", _FixedStrategy, 0.6, "30 14 * * 1-5"),
        StrategyEntry("ERR", _ErrorStrategy, 0.4, "30 14 * * 1-5"),
    ]
    registry = _make_registry(entries)
    orch = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S1": s1, "ERR": err_strategy},
        constraint_enforcer=ConstraintEnforcer(),
    )
    result = orch.run_cycle(
        ts=datetime(2024, 1, 15),
        data_replay=_make_data_replay(),
        portfolio=_make_portfolio(),
        market=_make_market(),
    )
    assert "S1" in result.strategies_run
    assert "ERR" not in result.strategies_run


def test_orchestrator_missing_instance_skipped_gracefully():
    """A strategy in the registry with no instance in strategy_instances is skipped."""
    entries = [StrategyEntry("S1", _FixedStrategy, 1.0, "30 14 * * 1-5")]
    registry = _make_registry(entries)
    orch = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={},  # No S1 instance
        constraint_enforcer=ConstraintEnforcer(),
    )
    result = orch.run_cycle(
        ts=datetime(2024, 1, 15),
        data_replay=_make_data_replay(),
        portfolio=_make_portfolio(),
        market=_make_market(),
    )
    assert result.strategies_run == []


# ── Weight-then-order ──────────────────────────────────────────────────────────

def test_orchestrator_weight_merge_no_double_counting():
    """Two strategies targeting AAPL should NOT produce 2x orders for AAPL.

    With weight-then-order, S1 alloc=0.6 w=0.01 + S2 alloc=0.4 w=0.01
    → merged w = 0.006 + 0.004 = 0.01 → 1 order for AAPL.
    """
    s1 = _FixedStrategy([_make_order(strategy_id="S1")])
    s2 = _FixedStrategy([_make_order(strategy_id="S2")])
    entries = [
        StrategyEntry("S1", _FixedStrategy, 0.5, "30 14 * * 1-5"),
        StrategyEntry("S2", _FixedStrategy, 0.5, "30 14 * * 1-5"),
    ]
    registry = _make_registry(entries)
    orch = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S1": s1, "S2": s2},
        constraint_enforcer=ConstraintEnforcer(),
    )
    result = orch.run_cycle(
        ts=datetime(2024, 1, 15),
        data_replay=_make_data_replay(),
        portfolio=_make_portfolio(),
        market=_make_market(),
    )
    # AAPL should appear exactly once in final_orders
    aapl_orders = [o for o in result.final_orders if o.symbol == "AAPL"]
    assert len(aapl_orders) == 1


# ── Constraints ───────────────────────────────────────────────────────────────

def test_orchestrator_applies_constraint_enforcer():
    """A very large BUY order should be scaled down by constraints."""
    big_order = _make_order(symbol="AAPL", side=OrderSide.BUY, qty=10_000.0, strategy_id="S1")
    s1 = _FixedStrategy([big_order])
    entries = [StrategyEntry("S1", _FixedStrategy, 1.0, "30 14 * * 1-5")]
    registry = _make_registry(entries)
    orch = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S1": s1},
        constraint_enforcer=ConstraintEnforcer(max_single_asset_pct=0.10),
    )
    result = orch.run_cycle(
        ts=datetime(2024, 1, 15),
        data_replay=_make_data_replay(),
        portfolio=_make_portfolio(cash=100_000.0),
        market=_make_market(symbols=("AAPL",)),
    )
    # 10000 qty × $100 = $1M >> 10% of $100k NAV ($10k cap)
    assert len(result.final_orders) == 1
    assert result.final_orders[0].quantity < 10_000.0


def test_orchestrator_constraints_fired_when_violated():
    big_order = _make_order(symbol="AAPL", side=OrderSide.BUY, qty=10_000.0, strategy_id="S1")
    s1 = _FixedStrategy([big_order])
    entries = [StrategyEntry("S1", _FixedStrategy, 1.0, "30 14 * * 1-5")]
    registry = _make_registry(entries)
    orch = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S1": s1},
        constraint_enforcer=ConstraintEnforcer(max_single_asset_pct=0.10),
    )
    result = orch.run_cycle(
        ts=datetime(2024, 1, 15),
        data_replay=_make_data_replay(),
        portfolio=_make_portfolio(cash=100_000.0),
        market=_make_market(symbols=("AAPL",)),
    )
    assert len(result.constraints_fired) >= 1


def test_orchestrator_orders_after_constraints_lte_before():
    s1 = _FixedStrategy([
        _make_order(strategy_id="S1"),
        _make_order(strategy_id="S1"),
    ])
    entries = [StrategyEntry("S1", _FixedStrategy, 1.0, "30 14 * * 1-5")]
    registry = _make_registry(entries)
    orch = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S1": s1},
        constraint_enforcer=ConstraintEnforcer(),
    )
    result = orch.run_cycle(
        ts=datetime(2024, 1, 15),
        data_replay=_make_data_replay(),
        portfolio=_make_portfolio(),
        market=_make_market(),
    )
    assert result.orders_after_constraints <= result.orders_before_constraints


# ── Vol targeting ─────────────────────────────────────────────────────────────

def test_orchestrator_vol_targeting_applied():
    """High-vol returns → scale < 1 → qty reduced."""
    buy_order = _make_order(symbol="AAPL", side=OrderSide.BUY, qty=100.0, strategy_id="S1")
    s1 = _FixedStrategy([buy_order])
    entries = [StrategyEntry("S1", _FixedStrategy, 1.0, "30 14 * * 1-5")]
    registry = _make_registry(entries)
    high_vol_returns = [0.05, -0.05, 0.10, -0.10, 0.08] * 20

    orch = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S1": s1},
        constraint_enforcer=ConstraintEnforcer(),
        vol_targeter=PortfolioVolTargeter(target_vol=0.01),  # very tight target
    )
    result = orch.run_cycle(
        ts=datetime(2024, 1, 15),
        data_replay=_make_data_replay(),
        portfolio=_make_portfolio(),
        market=_make_market(),
        strategy_returns={"S1": high_vol_returns},
    )
    assert len(result.final_orders) == 1
    assert result.final_orders[0].quantity < 100.0


def test_orchestrator_no_vol_targeting_when_returns_none():
    """Vol targeting skipped when strategy_returns is None."""
    buy_order = _make_order(symbol="AAPL", side=OrderSide.BUY, qty=100.0, strategy_id="S1")
    s1 = _FixedStrategy([buy_order])
    entries = [StrategyEntry("S1", _FixedStrategy, 1.0, "30 14 * * 1-5")]
    registry = _make_registry(entries)
    orch = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S1": s1},
        constraint_enforcer=ConstraintEnforcer(),
        vol_targeter=PortfolioVolTargeter(target_vol=0.10),
    )
    result = orch.run_cycle(
        ts=datetime(2024, 1, 15),
        data_replay=_make_data_replay(),
        portfolio=_make_portfolio(),
        market=_make_market(),
        strategy_returns=None,
    )
    assert result.final_orders[0].quantity == pytest.approx(100.0)


# ── P2-05-C: vol_targeter must run before enforcer ───────────────────────────


def test_vol_targeter_called_before_enforcer(mocker):
    """P2-05-C: PortfolioVolTargeter.scale_orders must be called BEFORE enforcer.enforce.

    Current (wrong) order: enforce → vol_scale → cap can be violated.
    Fixed order: vol_scale → enforce → cap is always final word.
    """
    buy_order = _make_order(symbol="AAPL", side=OrderSide.BUY, qty=100.0, strategy_id="S1")
    s1 = _FixedStrategy([buy_order])
    entries = [StrategyEntry("S1", _FixedStrategy, 1.0, "30 14 * * 1-5")]
    registry = _make_registry(entries)

    call_order: list[str] = []

    enforcer = ConstraintEnforcer()
    vol_targeter = PortfolioVolTargeter(target_vol=0.10)

    original_enforce = enforcer.enforce
    original_scale_orders = vol_targeter.scale_orders

    def recording_enforce(*args, **kwargs):
        call_order.append("enforce")
        return original_enforce(*args, **kwargs)

    def recording_scale_orders(*args, **kwargs):
        call_order.append("scale_orders")
        return original_scale_orders(*args, **kwargs)

    mocker.patch.object(enforcer, "enforce", side_effect=recording_enforce)
    mocker.patch.object(vol_targeter, "scale_orders", side_effect=recording_scale_orders)

    orch = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S1": s1},
        constraint_enforcer=enforcer,
        vol_targeter=vol_targeter,
    )
    low_vol_returns = [0.001] * 50  # low vol → scale > 1.0
    orch.run_cycle(
        ts=datetime(2024, 1, 15),
        data_replay=_make_data_replay(),
        portfolio=_make_portfolio(),
        market=_make_market(),
        strategy_returns={"S1": low_vol_returns},
    )

    assert call_order == ["scale_orders", "enforce"], (
        f"Expected vol_targeter before enforcer, got: {call_order}"
    )


def test_cap_is_final_after_vol_scaling_above_one(mocker):
    """P2-05-C: when vol scale > 1.0, final orders must not exceed the portfolio cap.

    Setup: 3 BUY orders at $100 each × 10 shares = $3,000 total (30% of $10,000 NAV).
    Cap = 40% of NAV = $4,000. compute_scale is forced to 2.0 via mock.

    After fix (vol_scale → enforce):
        vol_scale: 3,000 → 6,000; enforce: 6,000 > 4,000 → clip to 4,000. ✓

    Before fix (enforce → vol_scale):
        enforce sees 3,000 < 4,000 → no clip; vol_scale: 3,000 × 2 = 6,000 > 4,000. ✗
    """
    nav = 10_000.0
    cap = 0.40

    orders = [
        _make_order("AAPL", OrderSide.BUY, qty=10.0, strategy_id="S1"),
        _make_order("SPY",  OrderSide.BUY, qty=10.0, strategy_id="S1"),
        _make_order("QQQ",  OrderSide.BUY, qty=10.0, strategy_id="S1"),
    ]
    s1 = _FixedStrategy(orders)
    entries = [StrategyEntry("S1", _FixedStrategy, 1.0, "30 14 * * 1-5")]
    registry = _make_registry(entries)

    market = _make_market(symbols=("AAPL", "SPY", "QQQ"))  # all at $100

    vol_targeter = PortfolioVolTargeter(target_vol=0.10)
    # Force compute_scale to return 2.0: initial $3,000 × 2 = $6,000 > cap $4,000.
    mocker.patch.object(vol_targeter, "compute_scale", return_value=2.0)

    orch = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S1": s1},
        constraint_enforcer=ConstraintEnforcer(
            max_portfolio_exposure=cap,
            max_single_asset_pct=0.20,
        ),
        vol_targeter=vol_targeter,
    )

    low_vol_returns = [0.002, -0.002] * 25  # nonzero → estimate_vol called; scale mocked to 2.0

    portfolio = _make_portfolio(cash=nav)

    result = orch.run_cycle(
        ts=datetime(2024, 1, 15),
        data_replay=_make_data_replay(),
        portfolio=portfolio,
        market=market,
        strategy_returns={"S1": low_vol_returns},
    )

    buy_notional = sum(
        market.prices[o.symbol] * o.quantity
        for o in result.final_orders
        if o.side == OrderSide.BUY
    )
    assert buy_notional <= cap * nav + 1e-6, (
        f"Cap violated: buy_notional={buy_notional:.2f} > cap*nav={cap * nav:.2f}"
    )