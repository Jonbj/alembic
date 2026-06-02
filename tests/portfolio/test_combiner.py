"""T-501: PortfolioCombiner tests."""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from src.backtest.engine.data_replay import DataReplay
from src.backtest.engine.portfolio import VirtualPortfolio
from src.backtest.engine.types import MarketSnapshot, Order, OrderSide
from src.portfolio.combiner import PortfolioCombiner
from src.portfolio.types import CombinedOrder


# ── Helpers ────────────────────────────────────────────────────────────────────

def _prices(symbols=("SPY", "AAPL", "MSFT"), n=50) -> pd.DataFrame:
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    data = {s: np.ones(n) * 100.0 for s in symbols}
    return pd.DataFrame(data, index=dates)


def _market(prices_dict: dict) -> MarketSnapshot:
    return MarketSnapshot(
        timestamp=datetime(2023, 3, 15),
        prices=prices_dict,
        volumes={k: 1_000_000.0 for k in prices_dict},
        adv_20d={k: 1_000_000.0 for k in prices_dict},
    )


def _order(symbol="AAPL", side=OrderSide.BUY, qty=10.0, strategy_id="S1") -> Order:
    return Order.market_order(datetime(2023, 3, 15), symbol, side, qty, strategy_id)


class _FixedStrategy:
    """Returns a preset list of orders; counts calls."""

    def __init__(self, orders: list[Order]):
        self._orders = orders
        self.calls = 0

    def __call__(self, ts, data_replay, portfolio, market) -> list[Order]:
        self.calls += 1
        return self._orders


class _EmptyStrategy:
    def __call__(self, ts, data_replay, portfolio, market) -> list[Order]:
        return []


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def data_replay() -> DataReplay:
    return DataReplay(_prices())


@pytest.fixture
def portfolio() -> VirtualPortfolio:
    return VirtualPortfolio(initial_cash=100_000.0)


@pytest.fixture
def market() -> MarketSnapshot:
    return _market({"SPY": 400.0, "AAPL": 150.0, "MSFT": 300.0})


@pytest.fixture
def ts() -> datetime:
    return datetime(2023, 3, 15)


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_empty_strategies_returns_empty_orders(data_replay, portfolio, market, ts):
    combiner = PortfolioCombiner({})
    orders, state = combiner.aggregate(ts, data_replay, portfolio, market)
    assert orders == []


def test_empty_strategies_returns_zero_total_exposure(data_replay, portfolio, market, ts):
    combiner = PortfolioCombiner({})
    orders, state = combiner.aggregate(ts, data_replay, portfolio, market)
    assert state.total_exposure == pytest.approx(0.0)


def test_aggregate_calls_each_strategy_once(data_replay, portfolio, market, ts):
    s1, s2 = _FixedStrategy([]), _FixedStrategy([])
    combiner = PortfolioCombiner({"S1": (s1, 0.5), "S2": (s2, 0.2)})
    combiner.aggregate(ts, data_replay, portfolio, market)
    assert s1.calls == 1
    assert s2.calls == 1


def test_aggregate_returns_combined_orders_not_plain_orders(data_replay, portfolio, market, ts):
    s1 = _FixedStrategy([_order("AAPL", OrderSide.BUY, 10.0, "S1")])
    combiner = PortfolioCombiner({"S1": (s1, 0.5)})
    orders, _ = combiner.aggregate(ts, data_replay, portfolio, market)
    assert len(orders) == 1
    assert isinstance(orders[0], CombinedOrder)


def test_aggregate_tags_correct_strategy_id(data_replay, portfolio, market, ts):
    s1 = _FixedStrategy([_order("AAPL", OrderSide.BUY, 10.0, "S1")])
    combiner = PortfolioCombiner({"S1": (s1, 0.5)})
    orders, _ = combiner.aggregate(ts, data_replay, portfolio, market)
    assert orders[0].strategy_id == "S1"


def test_aggregate_tags_correct_allocation_weight(data_replay, portfolio, market, ts):
    s1 = _FixedStrategy([_order("AAPL", OrderSide.BUY, 10.0, "S1")])
    combiner = PortfolioCombiner({"S1": (s1, 0.5)})
    orders, _ = combiner.aggregate(ts, data_replay, portfolio, market)
    assert orders[0].allocation_weight == pytest.approx(0.5)


def test_aggregate_combines_orders_from_two_strategies(data_replay, portfolio, market, ts):
    s1 = _FixedStrategy([_order("AAPL", OrderSide.BUY, 10.0, "S1")])
    s2 = _FixedStrategy([_order("SPY", OrderSide.BUY, 5.0, "S2")])
    combiner = PortfolioCombiner({"S1": (s1, 0.5), "S2": (s2, 0.2)})
    orders, _ = combiner.aggregate(ts, data_replay, portfolio, market)
    assert len(orders) == 2
    assert {o.symbol for o in orders} == {"AAPL", "SPY"}


def test_aggregate_combines_orders_from_three_strategies(data_replay, portfolio, market, ts):
    s1 = _FixedStrategy([_order("AAPL", OrderSide.BUY, 5.0, "S1")])
    s2 = _FixedStrategy([_order("SPY", OrderSide.BUY, 3.0, "S2")])
    s4 = _FixedStrategy([_order("MSFT", OrderSide.BUY, 7.0, "S4")])
    combiner = PortfolioCombiner({"S1": (s1, 0.5), "S2": (s2, 0.2), "S4": (s4, 0.3)})
    orders, _ = combiner.aggregate(ts, data_replay, portfolio, market)
    assert len(orders) == 3
    assert {o.symbol for o in orders} == {"AAPL", "SPY", "MSFT"}


def test_aggregate_per_strategy_exposure_counts_buy_notional(data_replay, portfolio, market, ts):
    # AAPL @ 150, qty=10 → notional 1500
    s1 = _FixedStrategy([_order("AAPL", OrderSide.BUY, 10.0, "S1")])
    combiner = PortfolioCombiner({"S1": (s1, 0.5)})
    _, state = combiner.aggregate(ts, data_replay, portfolio, market)
    assert state.per_strategy_exposure["S1"] == pytest.approx(1500.0)


def test_aggregate_total_exposure_sums_all_strategies(data_replay, portfolio, market, ts):
    # AAPL @ 150, qty=10 → 1500; SPY @ 400, qty=5 → 2000; total=3500
    s1 = _FixedStrategy([_order("AAPL", OrderSide.BUY, 10.0, "S1")])
    s2 = _FixedStrategy([_order("SPY", OrderSide.BUY, 5.0, "S2")])
    combiner = PortfolioCombiner({"S1": (s1, 0.5), "S2": (s2, 0.2)})
    _, state = combiner.aggregate(ts, data_replay, portfolio, market)
    assert state.total_exposure == pytest.approx(3500.0)


def test_aggregate_zero_order_strategy_has_zero_exposure(data_replay, portfolio, market, ts):
    combiner = PortfolioCombiner({"S1": (_EmptyStrategy(), 0.5)})
    orders, state = combiner.aggregate(ts, data_replay, portfolio, market)
    assert orders == []
    assert state.per_strategy_exposure["S1"] == pytest.approx(0.0)


def test_aggregate_nav_equals_portfolio_cash_when_no_positions(data_replay, portfolio, market, ts):
    combiner = PortfolioCombiner({"S1": (_EmptyStrategy(), 0.5)})
    _, state = combiner.aggregate(ts, data_replay, portfolio, market)
    assert state.nav == pytest.approx(100_000.0)


def test_aggregate_sell_orders_not_counted_in_exposure(data_replay, portfolio, market, ts):
    sell = _order("AAPL", OrderSide.SELL, 10.0, "S1")
    s1 = _FixedStrategy([sell])
    combiner = PortfolioCombiner({"S1": (s1, 0.5)})
    _, state = combiner.aggregate(ts, data_replay, portfolio, market)
    assert state.per_strategy_exposure["S1"] == pytest.approx(0.0)
    assert state.total_exposure == pytest.approx(0.0)


def test_aggregate_preserves_original_order_quantity(data_replay, portfolio, market, ts):
    s1 = _FixedStrategy([_order("AAPL", OrderSide.BUY, 10.0, "S1")])
    combiner = PortfolioCombiner({"S1": (s1, 0.5)})
    orders, _ = combiner.aggregate(ts, data_replay, portfolio, market)
    assert orders[0].quantity == pytest.approx(10.0)


def test_aggregate_multiple_orders_from_one_strategy_sums_exposure(data_replay, portfolio, market, ts):
    # AAPL@150 qty=10→1500, MSFT@300 qty=5→1500; total S1=3000
    o1 = _order("AAPL", OrderSide.BUY, 10.0, "S1")
    o2 = _order("MSFT", OrderSide.BUY, 5.0, "S1")
    s1 = _FixedStrategy([o1, o2])
    combiner = PortfolioCombiner({"S1": (s1, 0.5)})
    orders, state = combiner.aggregate(ts, data_replay, portfolio, market)
    assert len(orders) == 2
    assert state.per_strategy_exposure["S1"] == pytest.approx(3000.0)


def test_aggregate_different_allocation_weights_per_strategy(data_replay, portfolio, market, ts):
    s1 = _FixedStrategy([_order("AAPL", OrderSide.BUY, 1.0, "S1")])
    s4 = _FixedStrategy([_order("MSFT", OrderSide.BUY, 1.0, "S4")])
    combiner = PortfolioCombiner({"S1": (s1, 0.5), "S4": (s4, 0.3)})
    orders, _ = combiner.aggregate(ts, data_replay, portfolio, market)
    s1_order = next(o for o in orders if o.strategy_id == "S1")
    s4_order = next(o for o in orders if o.strategy_id == "S4")
    assert s1_order.allocation_weight == pytest.approx(0.5)
    assert s4_order.allocation_weight == pytest.approx(0.3)
