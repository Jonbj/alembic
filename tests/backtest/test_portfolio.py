"""Tests for VirtualPortfolio."""
from datetime import datetime

import pytest

from src.backtest.engine.portfolio import VirtualPortfolio
from src.backtest.engine.types import Fill, MarketSnapshot, OrderSide


def make_fill(
    symbol: str,
    side: OrderSide,
    qty: float,
    price: float,
    ts: datetime | None = None,
    commission: float = 0.0,
) -> Fill:
    return Fill(
        fill_id="fill-1",
        order_id="order-1",
        timestamp=ts or datetime(2024, 1, 1),
        symbol=symbol,
        side=side,
        quantity=qty,
        fill_price=price,
        commission=commission,
        slippage_bps=0.0,
        strategy_id="test",
    )


def make_market(symbol_prices: dict[str, float], ts: datetime | None = None) -> MarketSnapshot:
    return MarketSnapshot(
        timestamp=ts or datetime(2024, 1, 1),
        prices=symbol_prices,
        volumes={s: 1_000_000.0 for s in symbol_prices},
        adv_20d={s: 10_000_000.0 for s in symbol_prices},
    )


class TestVirtualPortfolioInitial:
    def test_initial_cash(self) -> None:
        p = VirtualPortfolio(initial_cash=100_000)
        assert p.cash == 100_000

    def test_initial_no_positions(self) -> None:
        p = VirtualPortfolio(initial_cash=100_000)
        assert p.all_positions() == ()


class TestVirtualPortfolioFills:
    def test_buy_creates_position(self) -> None:
        p = VirtualPortfolio(100_000)
        p.apply_fill(make_fill("SPY", OrderSide.BUY, 100, 400.0))

        pos = p.position_of("SPY")
        assert pos is not None
        assert pos.quantity == 100
        assert pos.avg_cost == 400.0
        assert p.cash == pytest.approx(100_000 - 40_000)

    def test_sell_reduces_position(self) -> None:
        p = VirtualPortfolio(100_000)
        p.apply_fill(make_fill("SPY", OrderSide.BUY, 100, 400.0))
        p.apply_fill(make_fill("SPY", OrderSide.SELL, 50, 410.0))

        pos = p.position_of("SPY")
        assert pos is not None
        assert pos.quantity == 50

    def test_sell_closes_position(self) -> None:
        p = VirtualPortfolio(100_000)
        p.apply_fill(make_fill("SPY", OrderSide.BUY, 100, 400.0))
        p.apply_fill(make_fill("SPY", OrderSide.SELL, 100, 410.0))

        assert p.position_of("SPY") is None
        assert p.cash == pytest.approx(100_000 - 40_000 + 41_000)

    def test_add_to_position_weighted_avg_cost(self) -> None:
        p = VirtualPortfolio(100_000)
        p.apply_fill(make_fill("SPY", OrderSide.BUY, 100, 400.0))
        p.apply_fill(make_fill("SPY", OrderSide.BUY, 100, 410.0))

        pos = p.position_of("SPY")
        assert pos is not None
        assert pos.quantity == 200
        assert pos.avg_cost == pytest.approx(405.0)

    def test_commission_deducted_from_cash(self) -> None:
        p = VirtualPortfolio(100_000)
        p.apply_fill(make_fill("SPY", OrderSide.BUY, 100, 400.0, commission=5.0))
        assert p.cash == pytest.approx(100_000 - 40_000 - 5.0)

    def test_short_position(self) -> None:
        p = VirtualPortfolio(100_000)
        p.apply_fill(make_fill("SPY", OrderSide.SELL, 100, 400.0))

        pos = p.position_of("SPY")
        assert pos is not None
        assert pos.quantity == -100
        assert p.cash == pytest.approx(100_000 + 40_000)

    def test_cross_zero_position(self) -> None:
        p = VirtualPortfolio(200_000)
        p.apply_fill(make_fill("SPY", OrderSide.BUY, 100, 400.0))
        p.apply_fill(make_fill("SPY", OrderSide.SELL, 150, 420.0))

        pos = p.position_of("SPY")
        assert pos is not None
        assert pos.quantity == -50
        assert pos.avg_cost == pytest.approx(420.0)

    def test_fills_log_accumulated(self) -> None:
        p = VirtualPortfolio(100_000)
        p.apply_fill(make_fill("SPY", OrderSide.BUY, 100, 400.0))
        p.apply_fill(make_fill("SPY", OrderSide.BUY, 50, 410.0))
        assert len(p.get_fills()) == 2


class TestMarkToMarket:
    def test_nav_with_position(self) -> None:
        p = VirtualPortfolio(100_000)
        p.apply_fill(make_fill("SPY", OrderSide.BUY, 100, 400.0))

        snapshot = p.mark_to_market(make_market({"SPY": 410.0}))
        # cash: 60_000, position: 100 * 410 = 41_000, nav = 101_000
        assert snapshot.total_nav == pytest.approx(101_000)

    def test_nav_no_positions(self) -> None:
        p = VirtualPortfolio(100_000)
        snapshot = p.mark_to_market(make_market({"SPY": 410.0}))
        assert snapshot.total_nav == pytest.approx(100_000)

    def test_snapshots_accumulated(self) -> None:
        p = VirtualPortfolio(100_000)
        p.mark_to_market(make_market({"SPY": 400.0}, ts=datetime(2024, 1, 1)))
        p.mark_to_market(make_market({"SPY": 410.0}, ts=datetime(2024, 1, 2)))
        assert len(p.get_snapshots()) == 2

    def test_missing_price_uses_avg_cost(self) -> None:
        p = VirtualPortfolio(100_000)
        p.apply_fill(make_fill("SPY", OrderSide.BUY, 100, 400.0))
        # Market has no SPY price → falls back to avg_cost
        snapshot = p.mark_to_market(make_market({"TLT": 100.0}))
        # cash: 60_000, position valued at avg_cost 400*100=40_000
        assert snapshot.total_nav == pytest.approx(100_000)

    def test_portfolio_snapshot_position_of(self) -> None:
        p = VirtualPortfolio(100_000)
        p.apply_fill(make_fill("SPY", OrderSide.BUY, 100, 400.0))
        snap = p.mark_to_market(make_market({"SPY": 400.0}))

        assert snap.position_of("SPY") is not None
        assert snap.position_of("UNKNOWN") is None

    def test_portfolio_snapshot_weights(self) -> None:
        p = VirtualPortfolio(100_000)
        p.apply_fill(make_fill("SPY", OrderSide.BUY, 100, 400.0))
        market = make_market({"SPY": 400.0})
        snap = p.mark_to_market(market)

        weights = snap.weights(market)
        assert "SPY" in weights
        # SPY value 40_000 / NAV 100_000 = 40%
        assert weights["SPY"] == pytest.approx(0.40)
