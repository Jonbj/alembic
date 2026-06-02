"""PortfolioCombiner: aggregate orders from multiple strategies with allocation weights."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Callable

from src.backtest.engine.data_replay import DataReplay
from src.backtest.engine.portfolio import VirtualPortfolio
from src.backtest.engine.types import MarketSnapshot, Order, OrderSide
from src.portfolio.types import CombinedOrder, PortfolioState

if TYPE_CHECKING:
    from src.portfolio.risk_parity import RiskParityAllocator
    from src.portfolio.vol_targeting import PortfolioVolTargeter

# (strategy_callable, allocation_pct)
_StrategyEntry = tuple[Callable, float]


class PortfolioCombiner:
    """Aggregate orders from multiple strategies and track notional exposure.

    Args:
        strategies: mapping of strategy_id → (callable, allocation_pct)
                    e.g. {"S1": (s1_instance, 0.50), "S2": (s2_instance, 0.20)}
        risk_parity_mode: when True, use risk_parity_allocator weights instead of
                          fixed allocation_pct values
        risk_parity_allocator: RiskParityAllocator instance; required when
                               risk_parity_mode=True
        vol_targeting_mode: when True, scale BUY quantities after aggregation
                            so portfolio vol ≈ vol_targeter.target_vol
        vol_targeter: PortfolioVolTargeter instance; required when
                      vol_targeting_mode=True
        strategy_returns: per-strategy daily return series used by vol_targeter
    """

    def __init__(
        self,
        strategies: dict[str, _StrategyEntry],
        risk_parity_mode: bool = False,
        risk_parity_allocator: "RiskParityAllocator | None" = None,
        vol_targeting_mode: bool = False,
        vol_targeter: "PortfolioVolTargeter | None" = None,
        strategy_returns: "dict[str, list[float]] | None" = None,
    ) -> None:
        self._strategies = strategies
        self._risk_parity_mode = risk_parity_mode
        self._risk_parity_allocator = risk_parity_allocator
        self._vol_targeting_mode = vol_targeting_mode
        self._vol_targeter = vol_targeter
        self._strategy_returns = strategy_returns or {}

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

        dynamic_weights: dict[str, float] | None = None
        if self._risk_parity_mode and self._risk_parity_allocator is not None:
            dynamic_weights = self._risk_parity_allocator.compute_weights()

        for strategy_id, (strategy, alloc_pct) in self._strategies.items():
            weight = dynamic_weights[strategy_id] if dynamic_weights is not None else alloc_pct
            orders: list[Order] = strategy(ts, data_replay, portfolio, market)
            exposure = 0.0

            for order in orders:
                combined.append(CombinedOrder.from_order(order, allocation_weight=weight))
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

        if self._vol_targeting_mode and self._vol_targeter is not None:
            estimated_vol = self._vol_targeter.estimate_vol(self._strategy_returns)
            scale = self._vol_targeter.compute_scale(estimated_vol)
            combined = self._vol_targeter.scale_orders(combined, scale)

        return combined, state

    # ------------------------------------------------------------------

    def _compute_nav(self, portfolio: VirtualPortfolio, market: MarketSnapshot) -> float:
        nav = portfolio.cash
        for pos in portfolio.all_positions():
            price = market.price_of(pos.symbol)
            if price is not None:
                nav += pos.market_value(price)
        return nav
