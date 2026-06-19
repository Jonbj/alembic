"""P1-PORTFOLIO-COMBINER-RISK — Net-exposure cap and BUY/SELL conflict resolution.

Problems identified in ALEMBIC_REMEDIATION_MASTER_PLAN_2026-06-18 (WS-09):

1. PortfolioCombiner.aggregate() calculates total_exposure but never enforces a cap.
   If strategies together issue too many BUYs, the portfolio can be over-leveraged.
   Fix: enforce a net_exposure_cap (fraction of NAV); drop excess BUY orders.

2. When strategy S1 says BUY AAPL and strategy S4 says SELL AAPL for the same bar,
   both orders are passed downstream. Submitting both is undefined behavior at the
   broker: fills are race-condition-dependent and can open/close in the wrong order.
   Fix: detect BUY+SELL conflict per symbol; drop both conflicting orders.

Tests:
- test_net_exposure_cap_blocks_over_allocation
- test_net_exposure_cap_allows_orders_within_cap
- test_conflict_resolution_skips_opposing_signals
- test_non_conflicting_orders_pass_through
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.backtest.engine.types import Order, OrderSide, OrderType
from src.portfolio.combiner import PortfolioCombiner
from src.portfolio.types import CombinedOrder

_TS = datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc)


def _make_order(symbol: str, side: OrderSide, qty: float, strategy_id: str = "S1") -> Order:
    return Order(
        order_id=f"{symbol}-{side}-{strategy_id}",
        timestamp=_TS,
        symbol=symbol,
        side=side,
        quantity=qty,
        order_type=OrderType.MARKET,
        strategy_id=strategy_id,
    )


def _make_snapshot(prices: dict[str, float]) -> MagicMock:
    snap = MagicMock()
    snap.price_of.side_effect = lambda sym: prices.get(sym)
    return snap


def _make_portfolio(cash: float = 100_000.0) -> MagicMock:
    port = MagicMock()
    port.cash = cash
    port.all_positions.return_value = []
    return port


def _make_replay() -> MagicMock:
    return MagicMock()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Net-exposure cap
# ─────────────────────────────────────────────────────────────────────────────

class TestNetExposureCap:

    def test_net_exposure_cap_blocks_over_allocation(self):
        """BUY orders that would push total exposure over net_exposure_cap are dropped.

        NAV = 100,000. Cap = 0.8 → max notional = 80,000.
        S1 wants to buy 900 AAPL @ $100 = 90,000 notional → exceeds cap.
        PortfolioCombiner must drop enough BUY orders so total notional ≤ 80,000.
        """
        big_buy = _make_order("AAPL", OrderSide.BUY, qty=900.0, strategy_id="S1")  # $90k notional
        s1 = MagicMock(return_value=[big_buy])

        combiner = PortfolioCombiner(
            strategies={"S1": (s1, 0.5)},
            net_exposure_cap=0.80,
        )
        market = _make_snapshot({"AAPL": 100.0})
        combined, state = combiner.aggregate(
            ts=_TS,
            data_replay=_make_replay(),
            portfolio=_make_portfolio(cash=100_000.0),
            market=market,
        )

        buy_notional = sum(
            o.quantity * (market.price_of(o.symbol) or 0.0)
            for o in combined
            if o.side == OrderSide.BUY
        )
        assert buy_notional <= 80_000.0, (
            f"BUY notional {buy_notional:.0f} exceeds net_exposure_cap of 80,000. "
            "Combiner must drop excess BUY orders to enforce the cap."
        )

    def test_net_exposure_cap_allows_orders_within_cap(self):
        """BUY orders within the cap must pass through unchanged.

        NAV = 100,000. Cap = 0.8 → max notional = 80,000.
        S1 wants to buy 500 AAPL @ $100 = 50,000 notional → within cap.
        All orders should be present in output.
        """
        buy = _make_order("AAPL", OrderSide.BUY, qty=500.0, strategy_id="S1")  # $50k notional
        s1 = MagicMock(return_value=[buy])

        combiner = PortfolioCombiner(
            strategies={"S1": (s1, 0.5)},
            net_exposure_cap=0.80,
        )
        market = _make_snapshot({"AAPL": 100.0})
        combined, state = combiner.aggregate(
            ts=_TS,
            data_replay=_make_replay(),
            portfolio=_make_portfolio(cash=100_000.0),
            market=market,
        )

        buy_orders = [o for o in combined if o.side == OrderSide.BUY and o.symbol == "AAPL"]
        assert len(buy_orders) == 1, (
            "BUY orders within the cap must pass through. "
            f"Expected 1 AAPL BUY order, got {len(buy_orders)}."
        )

    def test_cap_violation_recorded_in_state(self):
        """When a cap violation occurs, PortfolioState.constraint_violations must be non-empty."""
        big_buy = _make_order("AAPL", OrderSide.BUY, qty=900.0, strategy_id="S1")
        s1 = MagicMock(return_value=[big_buy])

        combiner = PortfolioCombiner(
            strategies={"S1": (s1, 0.5)},
            net_exposure_cap=0.80,
        )
        market = _make_snapshot({"AAPL": 100.0})
        _, state = combiner.aggregate(
            ts=_TS,
            data_replay=_make_replay(),
            portfolio=_make_portfolio(cash=100_000.0),
            market=market,
        )

        assert len(state.constraint_violations) >= 1, (
            "When net_exposure_cap is breached, at least one ConstraintViolation "
            "must be recorded in PortfolioState so operators can audit cap enforcement."
        )
        violation = state.constraint_violations[0]
        assert violation.current_value > violation.threshold, (
            "ConstraintViolation.current_value (actual exposure) must be > threshold (cap). "
            f"Got current={violation.current_value}, threshold={violation.threshold}."
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. BUY/SELL conflict resolution
# ─────────────────────────────────────────────────────────────────────────────

class TestConflictResolution:

    def test_conflict_resolution_skips_opposing_signals(self):
        """When S1 says BUY AAPL and S4 says SELL AAPL, both orders must be dropped.

        Submitting conflicting BUY+SELL for the same symbol on the same bar is
        undefined behavior at the broker: fills are race-condition-dependent and
        can open/close positions in the wrong order. Safest resolution: drop both.
        """
        buy_aapl = _make_order("AAPL", OrderSide.BUY, qty=100.0, strategy_id="S1")
        sell_aapl = _make_order("AAPL", OrderSide.SELL, qty=50.0, strategy_id="S4")

        s1 = MagicMock(return_value=[buy_aapl])
        s4 = MagicMock(return_value=[sell_aapl])

        combiner = PortfolioCombiner(
            strategies={"S1": (s1, 0.5), "S4": (s4, 0.1)},
        )
        market = _make_snapshot({"AAPL": 100.0})
        combined, state = combiner.aggregate(
            ts=_TS,
            data_replay=_make_replay(),
            portfolio=_make_portfolio(),
            market=market,
        )

        aapl_orders = [o for o in combined if o.symbol == "AAPL"]
        assert len(aapl_orders) == 0, (
            f"BUY+SELL conflict for AAPL must result in both orders being dropped. "
            f"Got {len(aapl_orders)} AAPL order(s): {[(o.side, o.strategy_id) for o in aapl_orders]}."
        )

    def test_non_conflicting_orders_pass_through(self):
        """Orders for different symbols (no conflict) must all pass through."""
        buy_aapl = _make_order("AAPL", OrderSide.BUY, qty=100.0, strategy_id="S1")
        buy_msft = _make_order("MSFT", OrderSide.BUY, qty=50.0, strategy_id="S4")

        s1 = MagicMock(return_value=[buy_aapl])
        s4 = MagicMock(return_value=[buy_msft])

        combiner = PortfolioCombiner(
            strategies={"S1": (s1, 0.5), "S4": (s4, 0.1)},
        )
        market = _make_snapshot({"AAPL": 100.0, "MSFT": 80.0})
        combined, state = combiner.aggregate(
            ts=_TS,
            data_replay=_make_replay(),
            portfolio=_make_portfolio(),
            market=market,
        )

        symbols = {o.symbol for o in combined}
        assert "AAPL" in symbols, "Non-conflicting AAPL BUY must pass through"
        assert "MSFT" in symbols, "Non-conflicting MSFT BUY must pass through"

    def test_same_side_same_symbol_from_two_strategies_passes_through(self):
        """When S1 and S4 both say BUY AAPL (no conflict), both orders must be kept.

        Two BUYs for the same symbol from different strategies is fine — it means
        both strategies agree. Only BUY+SELL on the same symbol is a conflict.
        """
        buy1 = _make_order("AAPL", OrderSide.BUY, qty=100.0, strategy_id="S1")
        buy2 = _make_order("AAPL", OrderSide.BUY, qty=50.0, strategy_id="S4")

        s1 = MagicMock(return_value=[buy1])
        s4 = MagicMock(return_value=[buy2])

        combiner = PortfolioCombiner(
            strategies={"S1": (s1, 0.5), "S4": (s4, 0.1)},
        )
        market = _make_snapshot({"AAPL": 100.0})
        combined, state = combiner.aggregate(
            ts=_TS,
            data_replay=_make_replay(),
            portfolio=_make_portfolio(),
            market=market,
        )

        aapl_orders = [o for o in combined if o.symbol == "AAPL"]
        assert len(aapl_orders) == 2, (
            f"Two BUY orders for AAPL (no conflict) must both pass through. "
            f"Got {len(aapl_orders)}."
        )
