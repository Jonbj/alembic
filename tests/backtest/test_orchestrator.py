"""Tests for BacktestOrchestrator."""
from datetime import datetime

import pandas as pd
import pytest

from src.backtest.engine.data_replay import DataReplay
from src.backtest.engine.orchestrator import BacktestConfig, BacktestOrchestrator
from src.backtest.engine.portfolio import VirtualPortfolio
from src.backtest.engine.types import MarketSnapshot, Order, OrderSide


def make_linear_prices(n_days: int = 252, start_price: float = 400.0, end_price: float = 470.0) -> pd.DataFrame:
    dates = pd.date_range("2023-01-02", periods=n_days, freq="B")
    spy_prices = [
        start_price + (end_price - start_price) * i / (n_days - 1)
        for i in range(n_days)
    ]
    return pd.DataFrame({"SPY": spy_prices}, index=dates)


def make_volumes(n_days: int = 252) -> pd.DataFrame:
    dates = pd.date_range("2023-01-02", periods=n_days, freq="B")
    return pd.DataFrame({"SPY": [50_000_000.0] * n_days}, index=dates)


def buy_and_hold_strategy(
    ts: datetime,
    data_replay: DataReplay,
    portfolio: VirtualPortfolio,
    market: MarketSnapshot,
) -> list[Order]:
    if portfolio.position_of("SPY") is None:
        spy_price = market.price_of("SPY")
        if spy_price is None:
            return []
        qty = int(portfolio.cash * 0.95 / spy_price)
        return [Order.market_order(ts, "SPY", OrderSide.BUY, qty, "buy_hold")]
    return []


def no_op_strategy(
    ts: datetime,
    data_replay: DataReplay,
    portfolio: VirtualPortfolio,
    market: MarketSnapshot,
) -> list[Order]:
    return []


class TestBacktestOrchestrator:
    def test_no_op_nav_stays_flat(self) -> None:
        prices = make_linear_prices()
        replay = DataReplay(prices)
        orc = BacktestOrchestrator(BacktestConfig(initial_capital=100_000))
        result = orc.run(replay, no_op_strategy)

        for snap in result.snapshots:
            assert snap.total_nav == pytest.approx(100_000)

    def test_snapshot_count_equals_timesteps(self) -> None:
        prices = make_linear_prices(50)
        replay = DataReplay(prices)
        orc = BacktestOrchestrator(BacktestConfig(initial_capital=100_000))
        result = orc.run(replay, no_op_strategy)

        assert len(result.snapshots) == len(prices)

    def test_buy_and_hold_nav_grows(self) -> None:
        prices = make_linear_prices(252, start_price=400.0, end_price=470.0)
        volumes = make_volumes(252)
        replay = DataReplay(prices, volumes)
        orc = BacktestOrchestrator(BacktestConfig(initial_capital=100_000))
        result = orc.run(replay, buy_and_hold_strategy)

        final_nav = result.snapshots[-1].total_nav
        assert final_nav > 100_000, f"Final NAV should exceed initial: {final_nav}"

    def test_buy_and_hold_nav_in_expected_range(self) -> None:
        prices = make_linear_prices(252, start_price=400.0, end_price=470.0)
        volumes = make_volumes(252)
        replay = DataReplay(prices, volumes)
        orc = BacktestOrchestrator(BacktestConfig(initial_capital=100_000, spread_bps=5.0))
        result = orc.run(replay, buy_and_hold_strategy)

        final_nav = result.snapshots[-1].total_nav
        # 470/400 ≈ 17.5% gain on 95% invested → ~116,600 gross; minus slippage → ~108k-115k
        assert 107_000 < final_nav < 117_000, f"Final NAV out of expected range: {final_nav}"

    def test_fills_recorded(self) -> None:
        prices = make_linear_prices(50)
        replay = DataReplay(prices)
        orc = BacktestOrchestrator(BacktestConfig(initial_capital=100_000))
        result = orc.run(replay, buy_and_hold_strategy)

        assert len(result.fills) >= 1
        assert result.fills[0].symbol == "SPY"
        assert result.fills[0].side == OrderSide.BUY

    def test_nav_series_length(self) -> None:
        prices = make_linear_prices(50)
        replay = DataReplay(prices)
        orc = BacktestOrchestrator(BacktestConfig(initial_capital=100_000))
        result = orc.run(replay, no_op_strategy)

        nav = result.to_nav_series()
        assert len(nav) == 50

    def test_returns_series_no_nan(self) -> None:
        prices = make_linear_prices(50)
        replay = DataReplay(prices)
        orc = BacktestOrchestrator(BacktestConfig(initial_capital=100_000))
        result = orc.run(replay, no_op_strategy)

        rets = result.to_returns_series()
        assert not rets.isna().any()

    def test_order_for_missing_symbol_skipped(self) -> None:
        prices = make_linear_prices(10)
        replay = DataReplay(prices)
        orc = BacktestOrchestrator(BacktestConfig(initial_capital=100_000))

        def bad_strategy(ts, dr, port, mkt):
            return [Order.market_order(ts, "NONEXISTENT", OrderSide.BUY, 10, "test")]

        result = orc.run(replay, bad_strategy)
        # Should not crash; fills list empty (order skipped)
        assert len(result.fills) == 0
