"""Tests for Bug 4: Duplicate BUY orders fix in PortfolioOrchestrator."""

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


def _make_registry(entries):
    registry = StrategyRegistry(load_defaults=False)
    for e in entries:
        registry.register(e)
    return registry


def _make_market(symbols=("AAPL",)):
    return MarketSnapshot(
        timestamp=datetime(2024, 1, 15),
        prices={s: 100.0 for s in symbols},
        volumes={s: 1_000_000.0 for s in symbols},
        adv_20d={s: 1_000_000.0 for s in symbols},
    )


def _make_data_replay(symbols=("AAPL",)):
    dates = pd.date_range("2023-01-01", periods=50, freq="B")
    prices = pd.DataFrame({s: np.ones(50) * 100.0 for s in symbols}, index=dates)
    return DataReplay(prices)


def _make_portfolio(cash=100_000.0):
    return VirtualPortfolio(initial_cash=cash)


class _FixedStrategy:
    def __init__(self, orders=None):
        self.orders = orders or []
        self.call_count = 0

    def __call__(self, ts, data_replay, portfolio, market):
        self.call_count += 1
        return self.orders


class TestDuplicateBuyBug4:
    """Bug 4 regression: two strategies targeting the same symbol must produce
    exactly one merged order, not two separate orders for the same symbol.

    Merge semantics (sleeve-local weighted sum):
      Each strategy produces sleeve-local weights. The orchestrator multiplies
      each weight by allocation_pct and sums contributions across strategies.

      S1 alloc=0.5 implies AAPL at w1, S2 alloc=0.5 implies AAPL at w2:
        merged_weight(AAPL) = w1 * 0.5 + w2 * 0.5  → single delta order

      When allocations sum to 1.0 (as in these tests), weighted sum == weighted
      average, so the numeric results are identical to the old normalized path.
      The difference matters when allocations sum < 1.0 (e.g., S1=50%, S4=10%):
        single strategy on AAPL at w: merged = w * 0.50  (not w * 0.50 / 0.50)
    """

    def test_no_duplicate_symbol_in_orders(self):
        """Each symbol should appear at most once in final orders."""
        buy_aapl = Order.market_order(datetime(2024, 1, 15), "AAPL", OrderSide.BUY, 10.0, "S1")
        buy_aapl2 = Order.market_order(datetime(2024, 1, 15), "AAPL", OrderSide.BUY, 5.0, "S2")
        s1 = _FixedStrategy([buy_aapl])
        s2 = _FixedStrategy([buy_aapl2])

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

        aapl_orders = [o for o in result.final_orders if o.symbol == "AAPL"]
        assert len(aapl_orders) == 1, \
            f"AAPL should appear exactly once in orders, got {len(aapl_orders)}"

    def test_merged_weights_dont_exceed_one(self):
        """Merged weights should never exceed 1.0 after normalization."""
        # Two strategies both heavily overweight AAPL
        buy_aapl_1 = Order.market_order(datetime(2024, 1, 15), "AAPL", OrderSide.BUY, 50.0, "S1")
        buy_aapl_2 = Order.market_order(datetime(2024, 1, 15), "AAPL", OrderSide.BUY, 80.0, "S2")
        s1 = _FixedStrategy([buy_aapl_1])
        s2 = _FixedStrategy([buy_aapl_2])

        entries = [
            StrategyEntry("S1", _FixedStrategy, 0.6, "30 14 * * 1-5"),
            StrategyEntry("S2", _FixedStrategy, 0.4, "30 14 * * 1-5"),
        ]
        registry = _make_registry(entries)
        orch = PortfolioOrchestrator(
            registry=registry,
            strategy_instances={"S1": s1, "S2": s2},
            constraint_enforcer=ConstraintEnforcer(max_single_asset_pct=1.0),
        )
        result = orch.run_cycle(
            ts=datetime(2024, 1, 15),
            data_replay=_make_data_replay(),
            portfolio=_make_portfolio(cash=1_000_000.0),
            market=_make_market(),
        )

        # The AAPL order quantity should not represent > 100% of NAV
        # (before the fix, summed weights could easily exceed 1.0)
        for order in result.final_orders:
            if order.symbol == "AAPL":
                notional = order.quantity * 100.0  # price = 100
                assert notional <= 1_000_000.0 * 1.01, \
                    f"AAPL notional {notional} exceeds NAV 1M (weight > 100%)"

    def test_three_strategies_same_symbol_one_order(self):
        """Three strategies all targeting AAPL should produce exactly 1 order."""
        s1 = _FixedStrategy([Order.market_order(datetime(2024, 1, 15), "AAPL", OrderSide.BUY, 10.0, "S1")])
        s2 = _FixedStrategy([Order.market_order(datetime(2024, 1, 15), "AAPL", OrderSide.BUY, 15.0, "S2")])
        s3 = _FixedStrategy([Order.market_order(datetime(2024, 1, 15), "AAPL", OrderSide.BUY, 5.0, "S3")])

        entries = [
            StrategyEntry("S1", _FixedStrategy, 0.4, "30 14 * * 1-5"),
            StrategyEntry("S2", _FixedStrategy, 0.35, "30 14 * * 1-5"),
            StrategyEntry("S3", _FixedStrategy, 0.25, "30 14 * * 1-5"),
        ]
        registry = _make_registry(entries)
        orch = PortfolioOrchestrator(
            registry=registry,
            strategy_instances={"S1": s1, "S2": s2, "S3": s3},
            constraint_enforcer=ConstraintEnforcer(),
        )
        result = orch.run_cycle(
            ts=datetime(2024, 1, 15),
            data_replay=_make_data_replay(),
            portfolio=_make_portfolio(),
            market=_make_market(),
        )

        aapl_orders = [o for o in result.final_orders if o.symbol == "AAPL"]
        assert len(aapl_orders) == 1
