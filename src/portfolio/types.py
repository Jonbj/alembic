"""Portfolio types: CombinedOrder, ConstraintViolation, PortfolioState."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from src.backtest.engine.types import Order


@dataclass(frozen=True)
class CombinedOrder(Order):
    """An Order tagged with portfolio-level metadata."""

    allocation_weight: float = 1.0

    @classmethod
    def from_order(cls, order: Order, allocation_weight: float) -> "CombinedOrder":
        return cls(
            order_id=order.order_id,
            timestamp=order.timestamp,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            order_type=order.order_type,
            limit_price=order.limit_price,
            strategy_id=order.strategy_id,
            allocation_weight=allocation_weight,
        )

    def with_quantity(self, quantity: float) -> "CombinedOrder":
        return dataclasses.replace(self, quantity=quantity)


@dataclass(frozen=True)
class ConstraintViolation:
    strategy_id: str
    constraint_name: str
    current_value: float
    threshold: float


@dataclass
class PortfolioState:
    nav: float
    per_strategy_exposure: dict[str, float]
    total_exposure: float
    constraint_violations: list[ConstraintViolation]
