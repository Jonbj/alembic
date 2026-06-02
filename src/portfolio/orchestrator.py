"""PortfolioOrchestrator: run a full portfolio cycle across all active strategies.

Each cycle:
    1. Calls each active strategy's callable → list[Order]
    2. Tags orders with allocation_weight from registry
    3. Applies ConstraintEnforcer (position size, exposure, sector, correlation)
    4. Optionally applies PortfolioVolTargeter when strategy_returns provided
    5. Returns CycleResult with per-strategy counts, constraint violations, final orders

Usage (Celery task):
    result = orchestrator.run_cycle(ts, data_replay, portfolio, market, strategy_returns)
    # submit result.final_orders to execution worker
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

        Args:
            ts:               Current timestamp.
            data_replay:      Historical price data for strategy signal computation.
            portfolio:        Current virtual portfolio state.
            market:           Current market snapshot (prices, volumes).
            strategy_returns: Optional per-strategy daily return series for vol targeting.

        Returns:
            CycleResult with strategies run, order counts, constraint violations, orders.
        """
        active = self._registry.get_active_strategies()
        allocations = {e.strategy_id: e.allocation_pct for e in active}

        strategies_run: list[str] = []
        orders_per_strategy: dict[str, int] = {}
        combined: list[CombinedOrder] = []

        nav = self._compute_nav(portfolio, market)

        for entry in active:
            callable_fn = self._instances.get(entry.strategy_id)
            if callable_fn is None:
                log.warning(
                    "No instance for strategy %s — not in strategy_instances, skipping",
                    entry.strategy_id,
                )
                continue

            try:
                orders = callable_fn(ts, data_replay, portfolio, market)
                strategies_run.append(entry.strategy_id)
                orders_per_strategy[entry.strategy_id] = len(orders)

                for order in orders:
                    combined.append(
                        CombinedOrder.from_order(order, allocation_weight=entry.allocation_pct)
                    )
            except Exception as exc:
                log.error(
                    "Strategy %s raised an exception — skipping: %s",
                    entry.strategy_id,
                    exc,
                )

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
            "Portfolio cycle complete: strategies=%s orders_before=%d "
            "orders_after=%d constraints=%d",
            strategies_run,
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

    def _compute_nav(self, portfolio: VirtualPortfolio, market: MarketSnapshot) -> float:
        nav = portfolio.cash
        for pos in portfolio.all_positions():
            price = market.price_of(pos.symbol)
            if price is not None:
                nav += pos.market_value(price)
        return nav
