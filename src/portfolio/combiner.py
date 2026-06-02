"""PortfolioCombiner: aggregate orders from multiple strategies with allocation weights."""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from src.backtest.engine.data_replay import DataReplay
from src.backtest.engine.portfolio import VirtualPortfolio
from src.backtest.engine.types import MarketSnapshot, Order, OrderSide
from src.portfolio.types import CombinedOrder, PortfolioState

# (strategy_callable, allocation_pct)
_StrategyEntry = tuple[Callable, float]


class PortfolioCombiner:
    """Aggregate orders from multiple strategies and track notional exposure.

    Args:
        strategies: mapping of strategy_id → (callable, allocation_pct)
                    e.g. {"S1": (s1_instance, 0.50), "S2": (s2_instance, 0.20)}
    """

    def __init__(self, strategies: dict[str, _StrategyEntry]) -> None:
        self._strategies = strategies

    def aggregate(
        self,
        ts: datetime,
        data_replay: DataReplay,
        portfolio: VirtualPortfolio,
        market: MarketSnapshot,
    ) -> tuple[list[CombinedOrder], PortfolioState]:
        """Call every strategy, tag each order with strategy metadata, return aggregated state."""
        nav = self._compute_nav(portfolio, market)
        combined: list[CombinedOrder] = []
        per_strategy_exposure: dict[str, float] = {}

        for strategy_id, (strategy, alloc_pct) in self._strategies.items():
            orders: list[Order] = strategy(ts, data_replay, portfolio, market)
            exposure = 0.0

            for order in orders:
                combined.append(CombinedOrder.from_order(order, allocation_weight=alloc_pct))
                if order.side == OrderSide.BUY:
                    price = market.price_of(order.symbol)
                    if price is not None:
                        exposure += order.quantity * price

            per_strategy_exposure[strategy_id] = exposure

        total_exposure = sum(per_strategy_exposure.values())
        state = PortfolioState(
            nav=nav,
            per_strategy_exposure=per_strategy_exposure,
            total_exposure=total_exposure,
            constraint_violations=[],
        )
        return combined, state

    # ------------------------------------------------------------------

    def _compute_nav(self, portfolio: VirtualPortfolio, market: MarketSnapshot) -> float:
        nav = portfolio.cash
        for pos in portfolio.all_positions():
            price = market.price_of(pos.symbol)
            if price is not None:
                nav += pos.market_value(price)
        return nav
