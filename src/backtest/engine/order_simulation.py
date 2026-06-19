"""Simulate order fills with cost model.

Placeholder used by T-002 orchestrator; replaced by RealisticCostModel in T-003.
"""
import uuid

from src.backtest.engine.types import Fill, MarketSnapshot, Order, OrderSide


class SimpleCostModel:
    """Half-spread + flat commission. Replaced in T-003."""

    def __init__(
        self,
        spread_bps: float = 5.0,
        commission_per_share: float = 0.0,
    ) -> None:
        self.spread_bps = spread_bps
        self.commission_per_share = commission_per_share

    def simulate_fill(self, order: Order, market: MarketSnapshot) -> Fill:
        mid_price = market.price_of(order.symbol)
        if mid_price is None:
            raise ValueError(f"No price for {order.symbol} at {market.timestamp}")

        half_spread = mid_price * self.spread_bps / 10_000 / 2
        sign = 1 if order.side == OrderSide.BUY else -1
        fill_price = mid_price + sign * half_spread

        commission = self.commission_per_share * order.quantity

        return Fill(
            fill_id=str(uuid.uuid4()),
            order_id=order.order_id,
            timestamp=market.timestamp,  # fill time = when market executed it
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            fill_price=fill_price,
            commission=commission,
            slippage_bps=self.spread_bps / 2,
            strategy_id=order.strategy_id,
        )
