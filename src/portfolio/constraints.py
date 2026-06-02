"""ConstraintEnforcer: apply portfolio-level risk constraints to combined orders."""
from __future__ import annotations

import logging

from src.backtest.engine.types import MarketSnapshot, OrderSide
from src.portfolio.types import CombinedOrder, ConstraintViolation

log = logging.getLogger(__name__)


class ConstraintEnforcer:
    """Enforce portfolio constraints by reducing orders proportionally when violated.

    Constraints applied in order:
        1. MAX_SINGLE_ASSET_PCT  — per-symbol BUY notional ≤ max_single_asset_pct × NAV
        2. MAX_STRATEGY_EXPOSURE — per-strategy BUY notional ≤ alloc_pct × max_strategy_overshoot × NAV
        3. MAX_PORTFOLIO_EXPOSURE — total BUY notional ≤ max_portfolio_exposure × NAV

    When violated, orders for the affected scope are scaled down proportionally.
    SELL orders are never constrained.
    """

    def __init__(
        self,
        max_single_asset_pct: float = 0.10,
        max_portfolio_exposure: float = 0.50,
        max_strategy_overshoot: float = 1.50,
    ) -> None:
        self._max_single_asset_pct = max_single_asset_pct
        self._max_portfolio_exposure = max_portfolio_exposure
        self._max_strategy_overshoot = max_strategy_overshoot

    def enforce(
        self,
        orders: list[CombinedOrder],
        market: MarketSnapshot,
        nav: float,
        allocations: dict[str, float],
    ) -> tuple[list[CombinedOrder], list[ConstraintViolation]]:
        """Return (adjusted_orders, violations). Orders are never increased."""
        if nav <= 0 or not orders:
            return [], []

        violations: list[ConstraintViolation] = []
        working = list(orders)

        working, v1 = self._enforce_single_asset(working, market, nav)
        violations.extend(v1)

        working, v2 = self._enforce_strategy_exposure(working, market, nav, allocations)
        violations.extend(v2)

        working, v3 = self._enforce_portfolio_exposure(working, market, nav)
        violations.extend(v3)

        return working, violations

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _buy_notional(self, order: CombinedOrder, market: MarketSnapshot) -> float:
        if order.side != OrderSide.BUY:
            return 0.0
        price = market.price_of(order.symbol)
        return order.quantity * price if price is not None else 0.0

    def _scale_orders(
        self, orders: list[CombinedOrder], indices: list[int], scale: float
    ) -> list[CombinedOrder]:
        result = list(orders)
        for i in indices:
            result[i] = result[i].with_quantity(result[i].quantity * scale)
        return result

    def _enforce_single_asset(
        self,
        orders: list[CombinedOrder],
        market: MarketSnapshot,
        nav: float,
    ) -> tuple[list[CombinedOrder], list[ConstraintViolation]]:
        cap = self._max_single_asset_pct * nav
        violations: list[ConstraintViolation] = []

        # Group BUY order indices by symbol
        by_symbol: dict[str, list[int]] = {}
        for i, o in enumerate(orders):
            if o.side == OrderSide.BUY:
                by_symbol.setdefault(o.symbol, []).append(i)

        working = list(orders)
        for symbol, idxs in by_symbol.items():
            price = market.price_of(symbol)
            if price is None or price <= 0:
                continue
            total_notional = sum(working[i].quantity * price for i in idxs)
            if total_notional > cap:
                scale = cap / total_notional
                working = self._scale_orders(working, idxs, scale)
                strategy_id = working[idxs[0]].strategy_id
                violations.append(ConstraintViolation(
                    strategy_id=strategy_id,
                    constraint_name="MAX_SINGLE_ASSET_PCT",
                    current_value=total_notional / nav,
                    threshold=self._max_single_asset_pct,
                ))
                log.warning(
                    "MAX_SINGLE_ASSET_PCT violated: symbol=%s strategy=%s "
                    "notional=%.0f cap=%.0f (scale=%.4f)",
                    symbol, strategy_id, total_notional, cap, scale,
                )

        return working, violations

    def _enforce_strategy_exposure(
        self,
        orders: list[CombinedOrder],
        market: MarketSnapshot,
        nav: float,
        allocations: dict[str, float],
    ) -> tuple[list[CombinedOrder], list[ConstraintViolation]]:
        violations: list[ConstraintViolation] = []

        by_strategy: dict[str, list[int]] = {}
        for i, o in enumerate(orders):
            if o.side == OrderSide.BUY:
                by_strategy.setdefault(o.strategy_id, []).append(i)

        working = list(orders)
        for strategy_id, idxs in by_strategy.items():
            alloc_pct = allocations.get(strategy_id, 1.0)
            cap = alloc_pct * self._max_strategy_overshoot * nav
            if cap <= 0:
                continue

            total_notional = sum(
                working[i].quantity * (market.price_of(working[i].symbol) or 0.0)
                for i in idxs
            )
            if total_notional > cap:
                scale = cap / total_notional
                working = self._scale_orders(working, idxs, scale)
                violations.append(ConstraintViolation(
                    strategy_id=strategy_id,
                    constraint_name="MAX_STRATEGY_EXPOSURE",
                    current_value=total_notional / nav,
                    threshold=alloc_pct * self._max_strategy_overshoot,
                ))
                log.warning(
                    "MAX_STRATEGY_EXPOSURE violated: strategy=%s notional=%.0f cap=%.0f (scale=%.4f)",
                    strategy_id, total_notional, cap, scale,
                )

        return working, violations

    def _enforce_portfolio_exposure(
        self,
        orders: list[CombinedOrder],
        market: MarketSnapshot,
        nav: float,
    ) -> tuple[list[CombinedOrder], list[ConstraintViolation]]:
        cap = self._max_portfolio_exposure * nav

        buy_idxs = [i for i, o in enumerate(orders) if o.side == OrderSide.BUY]
        total_notional = sum(
            orders[i].quantity * (market.price_of(orders[i].symbol) or 0.0)
            for i in buy_idxs
        )

        if total_notional <= cap:
            return orders, []

        scale = cap / total_notional
        working = self._scale_orders(list(orders), buy_idxs, scale)
        violations = [ConstraintViolation(
            strategy_id="portfolio",
            constraint_name="MAX_PORTFOLIO_EXPOSURE",
            current_value=total_notional / nav,
            threshold=self._max_portfolio_exposure,
        )]
        log.warning(
            "MAX_PORTFOLIO_EXPOSURE violated: total_notional=%.0f cap=%.0f (scale=%.4f)",
            total_notional, cap, scale,
        )
        return working, violations
