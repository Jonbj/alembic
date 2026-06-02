"""ConstraintEnforcer: apply portfolio-level risk constraints to combined orders."""
from __future__ import annotations

import logging
from typing import Optional

from src.backtest.engine.types import MarketSnapshot, OrderSide
from src.portfolio.types import CombinedOrder, ConstraintViolation

log = logging.getLogger(__name__)

_MAX_SECTOR_PCT = 0.25
_CORR_THRESHOLD = 0.70
_CORR_REDUCTION = 0.80
_MAX_ITERATIONS = 10


def _pearson_correlation(x: list[float], y: list[float]) -> float:
    n = min(len(x), len(y))
    if n < 2:
        return 0.0
    x, y = x[:n], y[:n]
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    sx = sum((xi - mx) ** 2 for xi in x) ** 0.5
    sy = sum((yi - my) ** 2 for yi in y) ** 0.5
    if sx == 0.0 or sy == 0.0:
        return 0.0
    return num / (sx * sy)


def _std_dev(returns: list[float]) -> float:
    n = len(returns)
    if n < 2:
        return 0.0
    m = sum(returns) / n
    return (sum((r - m) ** 2 for r in returns) / n) ** 0.5


class ConstraintEnforcer:
    """Enforce portfolio constraints by reducing orders proportionally when violated.

    Constraints applied iteratively (up to 10 passes) in order:
        1. MAX_SINGLE_ASSET_PCT    — per-symbol BUY notional ≤ max_single_asset_pct × NAV
        2. MAX_STRATEGY_EXPOSURE   — per-strategy BUY notional ≤ alloc_pct × max_strategy_overshoot × NAV
        3. MAX_PORTFOLIO_EXPOSURE  — total BUY notional ≤ max_portfolio_exposure × NAV
        4. MAX_SECTOR_EXPOSURE     — per-sector BUY notional ≤ 25% NAV (when sector_map provided)
        5. MAX_CORRELATION_CLUSTER — high-corr strategy pair: reduce higher-vol by 20%

    When violated, orders for the affected scope are scaled down proportionally.
    SELL orders are never constrained. Passes repeat until no violations or limit reached.
    """

    def __init__(
        self,
        max_single_asset_pct: float = 0.10,
        max_portfolio_exposure: float = 0.50,
        max_strategy_overshoot: float = 1.50,
        sector_map: Optional[dict[str, str]] = None,
        strategy_returns: Optional[dict[str, list[float]]] = None,
    ) -> None:
        self._max_single_asset_pct = max_single_asset_pct
        self._max_portfolio_exposure = max_portfolio_exposure
        self._max_strategy_overshoot = max_strategy_overshoot
        self._sector_map = sector_map
        self._strategy_returns = strategy_returns or {}

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

        all_violations: list[ConstraintViolation] = []
        working = list(orders)

        _corr_reduced: frozenset[tuple[str, str]] = frozenset()
        for _ in range(_MAX_ITERATIONS):
            pass_violations: list[ConstraintViolation] = []

            working, v1 = self._enforce_single_asset(working, market, nav)
            pass_violations.extend(v1)

            working, v2 = self._enforce_strategy_exposure(working, market, nav, allocations)
            pass_violations.extend(v2)

            working, v3 = self._enforce_portfolio_exposure(working, market, nav)
            pass_violations.extend(v3)

            working, v4 = self._enforce_sector_exposure(working, market, nav)
            pass_violations.extend(v4)

            working, v5 = self._enforce_correlation_cluster(working, _corr_reduced)
            pass_violations.extend(v5)

            # Track correlation pairs already reduced to avoid re-reducing
            corr_pairs = set(_corr_reduced)
            for v in v5:
                if v.constraint_name == "MAX_CORRELATION_CLUSTER":
                    # Find the pair from returns keys that includes this strategy
                    for sa in self._strategy_returns or {}:
                        for sb in self._strategy_returns:
                            if sa != sb and (sa == v.strategy_id or sb == v.strategy_id):
                                corr_pairs.add(tuple(sorted([sa, sb])))
            _corr_reduced = frozenset(corr_pairs)
            all_violations.extend(pass_violations)
            if not pass_violations:
                break

        return working, all_violations

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

    def _enforce_sector_exposure(
        self,
        orders: list[CombinedOrder],
        market: MarketSnapshot,
        nav: float,
    ) -> tuple[list[CombinedOrder], list[ConstraintViolation]]:
        if self._sector_map is None:
            return orders, []

        cap = _MAX_SECTOR_PCT * nav
        violations: list[ConstraintViolation] = []

        by_sector: dict[str, list[int]] = {}
        for i, o in enumerate(orders):
            if o.side == OrderSide.BUY:
                sector = self._sector_map.get(o.symbol, "unknown")
                by_sector.setdefault(sector, []).append(i)

        working = list(orders)
        for sector, idxs in by_sector.items():
            total_notional = sum(
                working[i].quantity * (market.price_of(working[i].symbol) or 0.0)
                for i in idxs
            )
            if total_notional > cap:
                scale = cap / total_notional
                working = self._scale_orders(working, idxs, scale)
                strategy_id = working[idxs[0]].strategy_id
                violations.append(ConstraintViolation(
                    strategy_id=strategy_id,
                    constraint_name="MAX_SECTOR_EXPOSURE",
                    current_value=total_notional / nav,
                    threshold=_MAX_SECTOR_PCT,
                ))
                log.warning(
                    "MAX_SECTOR_EXPOSURE violated: sector=%s strategy=%s "
                    "notional=%.0f cap=%.0f (scale=%.4f)",
                    sector, strategy_id, total_notional, cap, scale,
                )

        return working, violations

    def _enforce_correlation_cluster(
        self,
        orders: list[CombinedOrder],
        already_reduced: frozenset[tuple[str, str]] | None = None,
    ) -> tuple[list[CombinedOrder], list[ConstraintViolation]]:
        if not self._strategy_returns:
            return orders, []

        if already_reduced is None:
            already_reduced = frozenset()

        violations: list[ConstraintViolation] = []
        working = list(orders)
        strategies = list(self._strategy_returns.keys())

        for i, s_a in enumerate(strategies):
            for s_b in strategies[i + 1:]:
                pair = tuple(sorted([s_a, s_b]))
                if pair in already_reduced:
                    continue

                returns_a = self._strategy_returns[s_a]
                returns_b = self._strategy_returns[s_b]
                corr = _pearson_correlation(returns_a, returns_b)
                if corr <= _CORR_THRESHOLD:
                    continue

                std_a = _std_dev(returns_a)
                std_b = _std_dev(returns_b)
                reduce_id = s_a if std_a >= std_b else s_b

                idxs = [
                    j for j, o in enumerate(working)
                    if o.strategy_id == reduce_id and o.side == OrderSide.BUY
                ]
                if idxs:
                    working = self._scale_orders(working, idxs, _CORR_REDUCTION)

                violations.append(ConstraintViolation(
                    strategy_id=reduce_id,
                    constraint_name="MAX_CORRELATION_CLUSTER",
                    current_value=corr,
                    threshold=_CORR_THRESHOLD,
                ))
                log.warning(
                    "MAX_CORRELATION_CLUSTER violated: strategies=%s/%s corr=%.4f "
                    "reducing=%s by %.0f%%",
                    s_a, s_b, corr, reduce_id, (1 - _CORR_REDUCTION) * 100,
                )

        return working, violations
