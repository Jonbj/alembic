"""PortfolioOrchestrator: run a full portfolio cycle across all active strategies.

Each cycle:
    1. Collects target weights from each strategy, scaled by allocation_pct.
    2. Merges target weights across strategies (weighted average).
    3. Computes delta orders (BUY/SELL) from current portfolio to merged target.
    4. Applies ConstraintEnforcer.
    5. Optionally applies PortfolioVolTargeter when strategy_returns provided.
    6. Returns CycleResult with per-strategy counts, constraint violations, final orders.

This approach avoids the double-counting bug where each strategy independently
generates full-portfolio orders, which when merged additively produce 2x quantities.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Callable

from src.backtest.engine.portfolio import VirtualPortfolio
from src.backtest.engine.types import MarketSnapshot, OrderSide
from src.portfolio.constraints import ConstraintEnforcer
from src.portfolio.types import CombinedOrder, ConstraintViolation

if TYPE_CHECKING:
    from src.backtest.engine.data_replay import DataReplay
    from src.portfolio.vol_targeting import PortfolioVolTargeter
    from src.strategies.registry import StrategyRegistry

log = logging.getLogger(__name__)


@dataclass
class CycleResult:
    """Result from a single PortfolioOrchestrator cycle."""
    strategies_run: list[str]
    orders_per_strategy: dict[str, int]
    orders_before_constraints: int
    orders_after_constraints: int
    constraints_fired: list[ConstraintViolation]
    final_orders: list[CombinedOrder]


class PortfolioOrchestrator:
    """Orchestrate multi-strategy order generation with constraint enforcement.

    Uses weight-then-order approach: strategies output target weights,
    which are merged by allocation_pct before computing a single set of delta orders.

    Args:
        registry:            StrategyRegistry providing active entries + allocations.
        strategy_instances:  Mapping of strategy_id → initialized callable.
                             Only strategies present here AND active in registry run.
        constraint_enforcer: Applies risk constraints to combined orders.
        vol_targeter:        Optional vol overlay; applied when strategy_returns passed.
    """

    def __init__(
        self,
        registry: "StrategyRegistry",
        strategy_instances: dict[str, Callable],
        constraint_enforcer: ConstraintEnforcer,
        vol_targeter: "PortfolioVolTargeter | None" = None,
    ) -> None:
        self._registry = registry
        self._instances = strategy_instances
        self._enforcer = constraint_enforcer
        self._vol_targeter = vol_targeter

    def run_cycle(
        self,
        ts: datetime,
        data_replay: "DataReplay",
        portfolio: VirtualPortfolio,
        market: MarketSnapshot,
        strategy_returns: dict[str, list[float]] | None = None,
    ) -> CycleResult:
        """Execute one portfolio cycle.

        The key insight: each strategy produces target *weights* (not orders).
        We compute allocation-weighted-average weights across strategies, then compute delta orders ONCE
        from the combined target vs current portfolio.

        Args:
            ts:               Current timestamp.
            data_replay:      Historical price data for strategy signal computation.
            portfolio:        Current virtual portfolio state.
            market:           Current market snapshot (prices, volumes).
            strategy_returns: Optional per-strategy daily return series for vol targeting.

        Returns:
            CycleResult with strategies run, order counts, constraint violations, orders.
        """
        from uuid import uuid4

        active = self._registry.get_active_strategies()
        allocations = {e.strategy_id: e.allocation_pct for e in active}

        strategies_run: list[str] = []
        orders_per_strategy: dict[str, int] = {}
        merged_weights: dict[str, float] = {}
        _weight_alloc_sum: dict[str, float] = {}

        nav = self._compute_nav(portfolio, market)

        # Step 1: Collect target weights from each strategy
        for entry in active:
            callable_fn = self._instances.get(entry.strategy_id)
            if callable_fn is None:
                log.warning(
                    "No instance for strategy %s — not in strategy_instances, skipping",
                    entry.strategy_id,
                )
                continue

            try:
                # Strategy returns a list[Order], but we need target weights.
                # Strategies that have compute_target_weights() — use those directly.
                # For strategies that only return orders, we extract implied weights.
                tw = self._extract_target_weights(
                    entry.strategy_id, callable_fn, ts, data_replay, portfolio, market, nav
                )
                strategies_run.append(entry.strategy_id)
                orders_per_strategy[entry.strategy_id] = len(tw)

                # Merge: allocation-weighted average (NOT sum).
                # Summing was the root cause of Bug 4 - two strategies each
                # targeting AAPL at 50% would produce 100%+ allocation instead
                # of the correct ~50% (weighted by each strategy's allocation).
                alloc = entry.allocation_pct
                for sym, wt in tw.items():
                    merged_weights[sym] = merged_weights.get(sym, 0.0) + wt * alloc
                    _weight_alloc_sum[sym] = _weight_alloc_sum.get(sym, 0.0) + alloc

            except Exception as exc:
                log.error(
                    "Strategy %s raised an exception — skipping: %s",
                    entry.strategy_id,
                    exc,
                    exc_info=True,
                )

        # Normalize: convert cumulative (wt * alloc) to allocation-weighted average.
        # Without this, two strategies targeting the same symbol would have
        # their contributions summed, potentially exceeding 100% (Bug 4).
        for sym in list(merged_weights.keys()):
            total_alloc = _weight_alloc_sum.get(sym, 0.0)
            if total_alloc > 0:
                merged_weights[sym] = merged_weights[sym] / total_alloc

        # Step 2: Build delta orders from merged target weights
        combined: list[CombinedOrder] = []
        for sym, target_wt in merged_weights.items():
            if target_wt <= 0:
                # If weight is 0 or negative → full SELL
                pos = portfolio.position_of(sym)
                if pos is not None and pos.quantity > 0:
                    combined.append(CombinedOrder(
                        order_id=str(uuid4()),
                        timestamp=ts,
                        symbol=sym,
                        side=OrderSide.SELL,
                        quantity=pos.quantity,
                        order_type="MARKET",
                        limit_price=None,
                        strategy_id="merged",
                        allocation_weight=1.0,
                    ))
                continue

            price = market.price_of(sym)
            if price is None or price <= 0:
                continue

            target_qty = (nav * target_wt) / price
            pos = portfolio.position_of(sym)
            current_qty = pos.quantity if pos is not None else 0.0
            delta = target_qty - current_qty

            if abs(delta) < 1e-4:
                continue

            side = OrderSide.BUY if delta > 0 else OrderSide.SELL
            qty = abs(delta)
            combined.append(CombinedOrder(
                order_id=str(uuid4()),
                timestamp=ts,
                symbol=sym,
                side=side,
                quantity=qty,
                order_type="MARKET",
                limit_price=None,
                strategy_id="merged",
                allocation_weight=target_wt,
            ))

        # Sell any positions whose symbol dropped out of the merged target entirely.
        # This handles the case where a strategy that previously held a position
        # no longer recommends it — without this loop, exited symbols would persist
        # indefinitely in the portfolio.
        for pos in portfolio.all_positions():
            if pos.symbol not in merged_weights:
                price = market.price_of(pos.symbol)
                if price is not None and pos.quantity > 0:
                    combined.append(CombinedOrder(
                        order_id=str(uuid4()),
                        timestamp=ts,
                        symbol=pos.symbol,
                        side=OrderSide.SELL,
                        quantity=pos.quantity,
                        order_type="MARKET",
                        limit_price=None,
                        strategy_id="merged",
                        allocation_weight=0.0,
                    ))

        orders_before = len(combined)
        violations: list[ConstraintViolation] = []

        if combined and nav > 0:
            combined, violations = self._enforcer.enforce(
                combined, market, nav, allocations
            )

        if self._vol_targeter is not None and combined and strategy_returns:
            estimated_vol = self._vol_targeter.estimate_vol(strategy_returns)
            scale = self._vol_targeter.compute_scale(estimated_vol)
            combined = self._vol_targeter.scale_orders(combined, scale)

        log.info(
            "Portfolio cycle complete: strategies=%s merged_weights=%d symbols "
            "orders_before=%d orders_after=%d constraints=%d",
            strategies_run,
            len(merged_weights),
            orders_before,
            len(combined),
            len(violations),
        )

        return CycleResult(
            strategies_run=strategies_run,
            orders_per_strategy=orders_per_strategy,
            orders_before_constraints=orders_before,
            orders_after_constraints=len(combined),
            constraints_fired=violations,
            final_orders=combined,
        )

    # ── Private ────────────────────────────────────────────────────────────────

    def _extract_target_weights(
        self, strategy_id: str, callable_fn, ts, data_replay, portfolio, market, nav
    ) -> dict[str, float]:
        """Extract target weights from a strategy.

        Strategies that expose compute_target_weights() → call that.
        Otherwise, run the callable to get orders → infer weights from order values.
        """
        # S1 and S4 have a compute_target_weights() method that maps directly to
        # the weight-then-order contract. S2 returns Order objects (it's position-
        # based, not weight-based), so we infer weights from order notional values.
        if hasattr(callable_fn, 'compute_target_weights'):
            if strategy_id == "S1":
                prices = data_replay.prices_until(ts)
                return callable_fn.compute_target_weights(prices)
            elif strategy_id == "S4":
                signals = getattr(callable_fn, '_signals_as_of', lambda t: None)(ts)
                return callable_fn.compute_target_weights(signals, as_of=ts)

        # S2 returns orders → infer weights
        orders = callable_fn(ts, data_replay, portfolio, market)
        if not orders:
            return {}

        # Convert orders to implied weights
        weights: dict[str, float] = {}
        for order in orders:
            price = market.price_of(order.symbol)
            if price is None or price <= 0 or nav <= 0:
                continue
            value = price * order.quantity
            wt = value / nav
            sign = 1.0 if order.side == OrderSide.BUY else -1.0
            weights[order.symbol] = weights.get(order.symbol, 0.0) + sign * wt

        return weights

    def _compute_nav(self, portfolio: VirtualPortfolio, market: MarketSnapshot) -> float:
        nav = portfolio.cash
        for pos in portfolio.all_positions():
            price = market.price_of(pos.symbol)
            if price is not None:
                nav += pos.market_value(price)
        return nav