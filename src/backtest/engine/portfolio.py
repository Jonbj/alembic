"""Virtual portfolio: track positions, apply fills, mark-to-market."""
import logging

from src.backtest.engine.types import (
    Fill,
    MarketSnapshot,
    OrderSide,
    Position,
    PortfolioSnapshot,
)


log = logging.getLogger(__name__)


class VirtualPortfolio:
    """Mutable portfolio state for backtest simulation only. Not for live trading."""

    def __init__(self, initial_cash: float) -> None:
        self._cash = initial_cash
        self._positions: dict[str, Position] = {}
        self._fills_log: list[Fill] = []
        self._snapshots: list[PortfolioSnapshot] = []

    @property
    def cash(self) -> float:
        return self._cash

    def load_position(self, symbol: str, quantity: float, avg_cost: float) -> None:
        """Inject an existing position (e.g. from Alpaca) without touching cash."""
        if abs(quantity) > 1e-9:
            self._positions[symbol] = Position(
                symbol=symbol,
                quantity=quantity,
                avg_cost=avg_cost,
            )

    def position_of(self, symbol: str) -> Position | None:
        return self._positions.get(symbol)

    def all_positions(self) -> tuple[Position, ...]:
        return tuple(p for p in self._positions.values() if not p.is_flat)

    def apply_fill(self, fill: Fill) -> None:
        """Apply fill: update cash and positions."""
        self._cash += fill.net_value

        current = self._positions.get(fill.symbol)
        if current is None:
            new_qty = fill.quantity if fill.side == OrderSide.BUY else -fill.quantity
            self._positions[fill.symbol] = Position(
                symbol=fill.symbol,
                quantity=new_qty,
                avg_cost=fill.fill_price,
            )
        else:
            sign = 1 if fill.side == OrderSide.BUY else -1
            new_qty = current.quantity + sign * fill.quantity

            if new_qty == 0:
                del self._positions[fill.symbol]
            elif (current.quantity > 0 and new_qty > 0) or (
                current.quantity < 0 and new_qty < 0
            ):
                total_cost = (
                    current.avg_cost * abs(current.quantity)
                    + fill.fill_price * fill.quantity
                )
                new_avg = total_cost / abs(new_qty)
                self._positions[fill.symbol] = Position(
                    symbol=fill.symbol,
                    quantity=new_qty,
                    avg_cost=new_avg,
                )
            else:
                # Crossed zero: new direction, new avg cost
                self._positions[fill.symbol] = Position(
                    symbol=fill.symbol,
                    quantity=new_qty,
                    avg_cost=fill.fill_price,
                )

        self._fills_log.append(fill)

    def mark_to_market(self, market: MarketSnapshot) -> PortfolioSnapshot:
        """Compute NAV at current market prices, save snapshot."""
        total_position_value = 0.0
        for pos in self._positions.values():
            price = market.price_of(pos.symbol)
            if price is None:
                log.warning(
                    "No price for %s at %s, using avg_cost", pos.symbol, market.timestamp
                )
                price = pos.avg_cost
            total_position_value += pos.market_value(price)

        total_nav = self._cash + total_position_value
        snapshot = PortfolioSnapshot(
            timestamp=market.timestamp,
            cash=self._cash,
            positions=tuple(self._positions.values()),
            total_nav=total_nav,
        )
        self._snapshots.append(snapshot)
        return snapshot

    def get_snapshots(self) -> tuple[PortfolioSnapshot, ...]:
        return tuple(self._snapshots)

    def get_fills(self) -> tuple[Fill, ...]:
        return tuple(self._fills_log)
