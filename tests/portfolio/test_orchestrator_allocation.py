"""Tests for sleeve-local allocation semantics in PortfolioOrchestrator.

Sleeve-local: a strategy's compute_target_weights() / implied order weights
represent fractions of its own sleeve, not the whole portfolio.
The orchestrator scales each by allocation_pct before summing.

Key invariant:
    portfolio_weight(sym) = sum(sleeve_weight(sym, s) * alloc_pct(s) for s in strategies)
"""

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from src.backtest.engine.data_replay import DataReplay
from src.backtest.engine.portfolio import VirtualPortfolio
from src.backtest.engine.types import MarketSnapshot, Order, OrderSide
from src.portfolio.constraints import ConstraintEnforcer
from src.portfolio.orchestrator import PortfolioOrchestrator
from src.strategies.registry import StrategyEntry, StrategyRegistry


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_registry(entries):
    registry = StrategyRegistry(load_defaults=False)
    for e in entries:
        registry.register(e)
    return registry


def _make_market(symbols=("AAPL",), price=100.0):
    return MarketSnapshot(
        timestamp=datetime(2024, 1, 15),
        prices={s: price for s in symbols},
        volumes={s: 1_000_000.0 for s in symbols},
        adv_20d={s: 1_000_000.0 for s in symbols},
    )


def _make_data_replay(symbols=("AAPL",)):
    dates = pd.date_range("2023-01-01", periods=50, freq="B")
    prices = pd.DataFrame({s: np.ones(50) * 100.0 for s in symbols}, index=dates)
    return DataReplay(prices)


def _make_portfolio(cash=100_000.0):
    return VirtualPortfolio(initial_cash=cash)


def _buy_order(symbol="AAPL", qty=100.0, strategy_id="S1"):
    return Order.market_order(datetime(2024, 1, 15), symbol, OrderSide.BUY, qty, strategy_id)


class _FixedStrategy:
    def __init__(self, orders=None):
        self.orders = orders or []

    def __call__(self, ts, data_replay, portfolio, market):
        return self.orders


# ── Single strategy: allocation_pct scales the implied weight ─────────────────

def test_single_strategy_allocation_scales_weight():
    """allocation_pct=0.50 on a single strategy halves its portfolio contribution.

    Strategy implies 20% portfolio weight (200 qty × $100 / $100k NAV).
    After sleeve scaling: 0.20 × 0.50 = 0.10 → 100 shares target.

    Old behaviour (normalization): 0.20 × 0.50 / 0.50 = 0.20 → 200 shares.
    """
    s1 = _FixedStrategy([_buy_order("AAPL", qty=200.0)])
    entry = StrategyEntry("S1", _FixedStrategy, 0.50, "30 14 * * 1-5")
    registry = _make_registry([entry])
    orch = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S1": s1},
        constraint_enforcer=ConstraintEnforcer(),
    )
    result = orch.run_cycle(
        ts=datetime(2024, 1, 15),
        data_replay=_make_data_replay(),
        portfolio=_make_portfolio(cash=100_000.0),
        market=_make_market(),
    )
    aapl = [o for o in result.final_orders if o.symbol == "AAPL"]
    assert len(aapl) == 1
    # 0.20 sleeve weight × 0.50 alloc → 10% of 100k at $100 = 100 shares
    assert aapl[0].quantity == pytest.approx(100.0, rel=0.01)


def test_full_allocation_passthrough():
    """allocation_pct=1.0 leaves the sleeve weight unchanged."""
    s1 = _FixedStrategy([_buy_order("AAPL", qty=200.0)])
    entry = StrategyEntry("S1", _FixedStrategy, 1.0, "30 14 * * 1-5")
    registry = _make_registry([entry])
    orch = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S1": s1},
        # Relax single-asset cap so the 20% weight isn't clipped (testing allocation math, not constraints)
        constraint_enforcer=ConstraintEnforcer(max_single_asset_pct=0.30),
    )
    result = orch.run_cycle(
        ts=datetime(2024, 1, 15),
        data_replay=_make_data_replay(),
        portfolio=_make_portfolio(cash=100_000.0),
        market=_make_market(),
    )
    aapl = [o for o in result.final_orders if o.symbol == "AAPL"]
    assert len(aapl) == 1
    # 0.20 sleeve weight × 1.0 alloc → 20% of 100k = 200 shares
    assert aapl[0].quantity == pytest.approx(200.0, rel=0.01)


def test_small_allocation_scales_down():
    """allocation_pct=0.10 scales the contribution to 10% of its sleeve claim."""
    s4 = _FixedStrategy([_buy_order("AAPL", qty=300.0, strategy_id="S4")])
    entry = StrategyEntry("S4", _FixedStrategy, 0.10, "30 14 * * 1-5")
    registry = _make_registry([entry])
    orch = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S4": s4},
        constraint_enforcer=ConstraintEnforcer(),
    )
    result = orch.run_cycle(
        ts=datetime(2024, 1, 15),
        data_replay=_make_data_replay(),
        portfolio=_make_portfolio(cash=100_000.0),
        market=_make_market(),
    )
    aapl = [o for o in result.final_orders if o.symbol == "AAPL"]
    assert len(aapl) == 1
    # 300*100/100k = 0.30 sleeve weight × 0.10 alloc → 3% → 30 shares
    assert aapl[0].quantity == pytest.approx(30.0, rel=0.01)


# ── Overlapping symbol: contributions are summed, not averaged ─────────────────

def test_overlapping_symbol_sums_sleeve_contributions():
    """Two strategies targeting the same symbol combine their capital contributions.

    S1 alloc=0.50: 200 qty → 0.20 sleeve weight → contributes 0.20 × 0.50 = 0.10
    S2 alloc=0.10: 300 qty → 0.30 sleeve weight → contributes 0.30 × 0.10 = 0.03
    Total AAPL weight: 0.13 → 130 shares at $100 with $100k portfolio.
    """
    s1 = _FixedStrategy([_buy_order("AAPL", qty=200.0, strategy_id="S1")])
    s2 = _FixedStrategy([_buy_order("AAPL", qty=300.0, strategy_id="S2")])
    entries = [
        StrategyEntry("S1", _FixedStrategy, 0.50, "30 14 * * 1-5"),
        StrategyEntry("S2", _FixedStrategy, 0.10, "30 14 * * 1-5"),
    ]
    registry = _make_registry(entries)
    orch = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S1": s1, "S2": s2},
        # Relax single-asset cap so 13% weight isn't clipped (testing allocation math, not constraints)
        constraint_enforcer=ConstraintEnforcer(max_single_asset_pct=0.30),
    )
    result = orch.run_cycle(
        ts=datetime(2024, 1, 15),
        data_replay=_make_data_replay(),
        portfolio=_make_portfolio(cash=100_000.0),
        market=_make_market(),
    )
    aapl = [o for o in result.final_orders if o.symbol == "AAPL"]
    assert len(aapl) == 1
    assert aapl[0].quantity == pytest.approx(130.0, rel=0.01)


def test_non_overlapping_symbols_independent():
    """Strategies holding different symbols don't interfere with each other."""
    s1 = _FixedStrategy([_buy_order("AAPL", qty=200.0, strategy_id="S1")])
    s4 = _FixedStrategy([_buy_order("MSFT", qty=100.0, strategy_id="S4")])
    entries = [
        StrategyEntry("S1", _FixedStrategy, 0.50, "30 14 * * 1-5"),
        StrategyEntry("S4", _FixedStrategy, 0.10, "30 14 * * 1-5"),
    ]
    registry = _make_registry(entries)
    market = _make_market(symbols=("AAPL", "MSFT"))
    orch = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S1": s1, "S4": s4},
        constraint_enforcer=ConstraintEnforcer(),
    )
    result = orch.run_cycle(
        ts=datetime(2024, 1, 15),
        data_replay=_make_data_replay(symbols=("AAPL", "MSFT")),
        portfolio=_make_portfolio(cash=100_000.0),
        market=market,
    )
    aapl = [o for o in result.final_orders if o.symbol == "AAPL"]
    msft = [o for o in result.final_orders if o.symbol == "MSFT"]
    assert len(aapl) == 1
    assert len(msft) == 1
    # AAPL: 0.20 × 0.50 = 0.10 → 100 shares
    assert aapl[0].quantity == pytest.approx(100.0, rel=0.01)
    # MSFT: 0.10 × 0.10 = 0.01 → 10 shares
    assert msft[0].quantity == pytest.approx(10.0, rel=0.01)


def test_portfolio_total_weight_respects_allocations():
    """Sum of all portfolio weights must not exceed sum of allocation_pcts."""
    s1 = _FixedStrategy([
        _buy_order("AAPL", qty=200.0, strategy_id="S1"),
        _buy_order("MSFT", qty=100.0, strategy_id="S1"),
    ])
    s4 = _FixedStrategy([
        _buy_order("AAPL", qty=50.0,  strategy_id="S4"),
        _buy_order("NVDA", qty=80.0,  strategy_id="S4"),
    ])
    entries = [
        StrategyEntry("S1", _FixedStrategy, 0.50, "30 14 * * 1-5"),
        StrategyEntry("S4", _FixedStrategy, 0.10, "30 14 * * 1-5"),
    ]
    registry = _make_registry(entries)
    market = _make_market(symbols=("AAPL", "MSFT", "NVDA"))
    orch = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S1": s1, "S4": s4},
        constraint_enforcer=ConstraintEnforcer(),
    )
    result = orch.run_cycle(
        ts=datetime(2024, 1, 15),
        data_replay=_make_data_replay(symbols=("AAPL", "MSFT", "NVDA")),
        portfolio=_make_portfolio(cash=100_000.0),
        market=market,
    )
    nav = 100_000.0
    total_notional = sum(o.quantity * 100.0 for o in result.final_orders if o.side == OrderSide.BUY)
    total_weight = total_notional / nav
    # allocation_pcts sum to 0.60; total deployed weight should be ≤ 0.60
    assert total_weight <= 0.60 + 1e-6
