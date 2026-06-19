"""PortfolioCombiner: aggregate orders from multiple strategies with allocation weights."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Callable

from src.backtest.engine.types import MarketSnapshot, Order, OrderSide
from src.portfolio.types import CombinedOrder, ConstraintViolation, PortfolioState

if TYPE_CHECKING:
    from src.backtest.engine.data_replay import DataReplay
    from src.backtest.engine.portfolio import VirtualPortfolio
    from src.portfolio.risk_parity import RiskParityAllocator
    from src.portfolio.vol_targeting import PortfolioVolTargeter

log = logging.getLogger(__name__)

# (strategy_callable, allocation_pct)
_StrategyEntry = tuple[Callable, float]


class PortfolioCombiner:
    """Aggregate orders from multiple strategies and track notional exposure.

    Args:
        strategies: mapping of strategy_id → (callable, allocation_pct)
                    e.g. {"S1": (s1_instance, 0.50), "S2": (s2_instance, 0.20)}
        net_exposure_cap: maximum total notional as a fraction of NAV.
                          When set, BUY orders that would push gross exposure above
                          ``nav * net_exposure_cap`` are dropped and a ConstraintViolation
                          is recorded. When None (default), no cap is enforced.
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
        net_exposure_cap: "float | None" = None,
        risk_parity_mode: bool = False,
        risk_parity_allocator: "RiskParityAllocator | None" = None,
        vol_targeting_mode: bool = False,
        vol_targeter: "PortfolioVolTargeter | None" = None,
        strategy_returns: "dict[str, list[float]] | None" = None,
    ) -> None:
        self._strategies = strategies
        self._net_exposure_cap = net_exposure_cap
        self._risk_parity_mode = risk_parity_mode
        self._risk_parity_allocator = risk_parity_allocator
        self._vol_targeting_mode = vol_targeting_mode
        self._vol_targeter = vol_targeter
        self._strategy_returns = strategy_returns or {}

    def aggregate(
        self,
        ts: datetime,
        data_replay: "DataReplay",
        portfolio: "VirtualPortfolio",
        market: MarketSnapshot,
    ) -> tuple[list[CombinedOrder], PortfolioState]:
        """Call every strategy, tag each order with strategy metadata, return aggregated state."""
        nav = self._compute_nav(portfolio, market)
        raw: list[CombinedOrder] = []
        per_strategy_exposure: dict[str, float] = {}

        dynamic_weights: dict[str, float] | None = None
        if self._risk_parity_mode and self._risk_parity_allocator is not None:
            dynamic_weights = self._risk_parity_allocator.compute_weights()

        for strategy_id, (strategy, alloc_pct) in self._strategies.items():
            weight = dynamic_weights[strategy_id] if dynamic_weights is not None else alloc_pct
            orders: list[Order] = strategy(ts, data_replay, portfolio, market)
            exposure = 0.0

            for order in orders:
                raw.append(CombinedOrder.from_order(order, allocation_weight=weight))
                if order.side == OrderSide.BUY:
                    price = market.price_of(order.symbol)
                    if price is not None:
                        exposure += order.quantity * price

            per_strategy_exposure[strategy_id] = exposure

        # ── Risk controls ─────────────────────────────────────────────────────
        combined, violations = self._apply_risk_controls(raw, nav, market)
        # ─────────────────────────────────────────────────────────────────────

        total_exposure = sum(per_strategy_exposure.values())
        state = PortfolioState(
            nav=nav,
            per_strategy_exposure=per_strategy_exposure,
            total_exposure=total_exposure,
            constraint_violations=violations,
        )

        if self._vol_targeting_mode and self._vol_targeter is not None:
            estimated_vol = self._vol_targeter.estimate_vol(self._strategy_returns)
            scale = self._vol_targeter.compute_scale(estimated_vol)
            combined = self._vol_targeter.scale_orders(combined, scale)

        return combined, state

    # ------------------------------------------------------------------

    def _apply_risk_controls(
        self,
        orders: list[CombinedOrder],
        nav: float,
        market: MarketSnapshot,
    ) -> tuple[list[CombinedOrder], list[ConstraintViolation]]:
        """Apply net-exposure cap and BUY/SELL conflict resolution.

        Returns (filtered_orders, violations).
        """
        violations: list[ConstraintViolation] = []

        # 1. BUY/SELL conflict resolution — drop both sides when a symbol has
        #    opposing signals from different strategies.
        conflicted = self._find_conflicted_symbols(orders)
        if conflicted:
            log.warning(
                "BUY/SELL conflict on %s — dropping all orders for conflicted symbols",
                conflicted,
            )
        orders = [o for o in orders if o.symbol not in conflicted]

        # 2. Net-exposure cap — drop BUY orders that push gross exposure over the cap.
        #    Skipped when net_exposure_cap is None (opt-in only).
        if self._net_exposure_cap is None:
            return orders, violations

        cap_notional = nav * self._net_exposure_cap
        running_notional = 0.0
        passed: list[CombinedOrder] = []

        for order in orders:
            if order.side != OrderSide.BUY:
                passed.append(order)
                continue
            price = market.price_of(order.symbol)
            order_notional = order.quantity * (price or 0.0)
            if running_notional + order_notional <= cap_notional:
                passed.append(order)
                running_notional += order_notional
            else:
                log.warning(
                    "Net-exposure cap: dropping BUY %s qty=%.4f (would push notional to %.0f > cap %.0f)",
                    order.symbol,
                    order.quantity,
                    running_notional + order_notional,
                    cap_notional,
                )
                violations.append(
                    ConstraintViolation(
                        strategy_id=order.strategy_id,
                        constraint_name="net_exposure_cap",
                        current_value=running_notional + order_notional,
                        threshold=cap_notional,
                    )
                )

        return passed, violations

    @staticmethod
    def _find_conflicted_symbols(orders: list[CombinedOrder]) -> set[str]:
        """Return symbols that have both BUY and SELL orders (cross-strategy conflict)."""
        sides_by_symbol: dict[str, set[OrderSide]] = {}
        for o in orders:
            sides_by_symbol.setdefault(o.symbol, set()).add(o.side)
        return {sym for sym, sides in sides_by_symbol.items() if len(sides) > 1}

    def _compute_nav(self, portfolio: "VirtualPortfolio", market: MarketSnapshot) -> float:
        nav = portfolio.cash
        for pos in portfolio.all_positions():
            price = market.price_of(pos.symbol)
            if price is not None:
                nav += pos.market_value(price)
        return nav
