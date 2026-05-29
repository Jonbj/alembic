"""Core immutable types for backtest engine."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional
import uuid


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class RebalanceFrequency(str, Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


@dataclass(frozen=True)
class Order:
    order_id: str
    timestamp: datetime
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    strategy_id: str = "unknown"

    @classmethod
    def market_order(
        cls,
        ts: datetime,
        symbol: str,
        side: OrderSide,
        qty: float,
        strategy_id: str = "unknown",
    ) -> "Order":
        return cls(
            order_id=str(uuid.uuid4()),
            timestamp=ts,
            symbol=symbol,
            side=side,
            quantity=qty,
            order_type=OrderType.MARKET,
            strategy_id=strategy_id,
        )


@dataclass(frozen=True)
class Fill:
    fill_id: str
    order_id: str
    timestamp: datetime
    symbol: str
    side: OrderSide
    quantity: float
    fill_price: float
    commission: float
    slippage_bps: float
    strategy_id: str

    @property
    def gross_value(self) -> float:
        return self.quantity * self.fill_price

    @property
    def net_value(self) -> float:
        """Negative for buys (cash out), positive for sells (cash in)."""
        sign = -1 if self.side == OrderSide.BUY else 1
        return sign * self.gross_value - self.commission


@dataclass(frozen=True)
class Position:
    symbol: str
    quantity: float
    avg_cost: float

    @property
    def is_long(self) -> bool:
        return self.quantity > 0

    @property
    def is_flat(self) -> bool:
        return self.quantity == 0

    def market_value(self, current_price: float) -> float:
        return self.quantity * current_price

    def unrealized_pnl(self, current_price: float) -> float:
        return (current_price - self.avg_cost) * self.quantity


@dataclass(frozen=True)
class MarketSnapshot:
    timestamp: datetime
    prices: dict[str, float]
    volumes: dict[str, float]
    adv_20d: dict[str, float]

    def has_price(self, symbol: str) -> bool:
        return symbol in self.prices

    def price_of(self, symbol: str) -> Optional[float]:
        return self.prices.get(symbol)


@dataclass(frozen=True)
class PortfolioSnapshot:
    timestamp: datetime
    cash: float
    positions: tuple["Position", ...]
    total_nav: float

    def position_of(self, symbol: str) -> Optional["Position"]:
        for p in self.positions:
            if p.symbol == symbol:
                return p
        return None

    def weights(self, market: MarketSnapshot) -> dict[str, float]:
        result: dict[str, float] = {}
        for p in self.positions:
            price = market.price_of(p.symbol)
            if price is not None and self.total_nav > 0:
                result[p.symbol] = p.market_value(price) / self.total_nav
        return result
