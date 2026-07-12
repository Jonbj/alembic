"""PortfolioOrchestrator: run a full portfolio cycle across all active strategies.

Each cycle:
    1. Collects sleeve-local target weights from each strategy.
    2. Merges weights as weighted sum (each multiplied by allocation_pct).
    3. Computes delta orders (BUY/SELL) from current portfolio to merged target.
    4. Optionally applies PortfolioVolTargeter (vol-targeting scale) when strategy_returns provided.
    5. Applies ConstraintEnforcer last — enforcer is the final word on risk caps.
    6. Returns CycleResult with per-strategy counts, constraint violations, final orders.

Step ordering matters: vol-targeter runs before enforcer so that the cap cannot be
re-violated by an upward vol scale (P2-05-C).

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
    symbol_strategies: dict[str, list[str]] = field(default_factory=dict)
    # F8 shadow: per-strategy {scale, unscaled_weight, scaled_weight} for strategies
    # whose feedback regime scale was != 1.0 this cycle. Lets the scheduler log the
    # deployment delta (measure-before-enforce) without applying the scale live.
    feedback_shadow: dict[str, dict] = field(default_factory=dict)


class PortfolioOrchestrator:
    """Orchestrate multi-strategy order generation with constraint enforcement.

    Uses weight-then-order approach: strategies output sleeve-local target weights,
    which are scaled by allocation_pct and summed before computing a single set of delta orders.

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
        feedback_scales: dict[str, float] | None = None,
        apply_feedback_scale: bool = True,
    ) -> CycleResult:
        """Execute one portfolio cycle.

        The key insight: each strategy produces sleeve-local target *weights* (not orders).
        We compute allocation-weighted-sum weights across strategies, then compute delta orders ONCE
        from the combined target vs current portfolio.

        Args:
            ts:               Current timestamp.
            data_replay:      Historical price data for strategy signal computation.
            portfolio:        Current virtual portfolio state.
            market:           Current market snapshot (prices, volumes).
            strategy_returns: Optional per-strategy daily return series for vol targeting.
            feedback_scales: Optional per-strategy sizing scale (F8 loss-feedback
                de-risk/re-risk throttle). Each strategy's `wt * alloc` contribution
                is multiplied by `feedback_scales.get(strategy_id, 1.0)` before the
                weighted-sum merge, preserving per-strategy isolation (a loss in one
                sleeve shrinks only that sleeve). None / missing strategy → 1.0
                (identity, zero behavior change when the scheduler flag is off).
            apply_feedback_scale: When False, the scale is NOT applied to the merge
                (weights stay unscaled) but `feedback_shadow` still records the
                would-be unscaled-vs-scaled delta. This is the measure-before-enforce
                path: the scheduler logs the shadow for N cycles before flipping the
                flag to True. Default True (passing scales applies them).

        Returns:
            CycleResult with strategies run, order counts, constraint violations, orders.
        """
        from uuid import uuid4

        active = self._registry.get_active_strategies()
        allocations = {e.strategy_id: e.allocation_pct for e in active}

        strategies_run: list[str] = []
        orders_per_strategy: dict[str, int] = {}
        merged_weights: dict[str, float] = {}
        symbol_strategies: dict[str, list[str]] = {}
        feedback_shadow: dict[str, dict] = {}

        # F8: per-strategy feedback regime scale (loss-feedback de-risk/re-risk
        # throttle). None / missing strategy → 1.0 (identity). Applied to each
        # strategy's sleeve contribution before the weighted-sum merge so a loss
        # in one sleeve shrinks only that sleeve (Phase 5 decouple preserved).
        _fb_scales = feedback_scales or {}

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

                # Merge: weighted sum (sleeve-local semantics).
                # Strategies produce sleeve-local weights (fraction of their own sleeve).
                # Multiplying by allocation_pct gives portfolio-level contribution.
                # Two strategies both holding a symbol correctly ADD their contributions —
                # that symbol genuinely receives combined capital from both sleeves.
                alloc = entry.allocation_pct
                _fb_scale = float(_fb_scales.get(entry.strategy_id, 1.0) or 1.0)
                _effective_scale = _fb_scale if apply_feedback_scale else 1.0
                for sym, wt in tw.items():
                    merged_weights[sym] = merged_weights.get(sym, 0.0) + wt * alloc * _effective_scale
                    symbol_strategies.setdefault(sym, []).append(entry.strategy_id)

                # F8 shadow: record this strategy's unscaled vs would-be-scaled
                # sleeve contribution so the scheduler can log the deployment delta.
                # Recorded whenever a non-identity scale is in play, regardless of
                # apply_feedback_scale — so measure-before-enforce can observe the
                # would-be effect without applying it.
                if _fb_scale != 1.0:
                    _unscaled = sum(wt * alloc for _, wt in tw.items())
                    feedback_shadow[entry.strategy_id] = {
                        "scale": _fb_scale,
                        "unscaled_weight": _unscaled,
                        "scaled_weight": _unscaled * _fb_scale,
                        "applied": apply_feedback_scale,
                    }

            except Exception as exc:
                log.error(
                    "Strategy %s raised an exception — skipping: %s",
                    entry.strategy_id,
                    exc,
                    exc_info=True,
                )

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

            if abs(delta) < max(1e-4, target_qty * 0.02):
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

        # P2-05-C: vol-targeter runs BEFORE enforcer so the enforcer has the final word
        # on risk caps. Running after would let vol-scaling push quantities above the
        # cap that enforce() just set (scale can be up to 2.0×).
        if self._vol_targeter is not None and combined and strategy_returns:
            estimated_vol = self._vol_targeter.estimate_vol(strategy_returns)
            scale = self._vol_targeter.compute_scale(estimated_vol)
            combined = self._vol_targeter.scale_orders(combined, scale)

        if combined and nav > 0:
            combined, violations = self._enforcer.enforce(
                combined, market, nav, allocations
            )

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
            symbol_strategies=symbol_strategies,
            feedback_shadow=feedback_shadow,
        )

    # ── Private ────────────────────────────────────────────────────────────────

    def _extract_target_weights(
        self, strategy_id: str, callable_fn, ts, data_replay, portfolio, market, nav
    ) -> dict[str, float]:
        """Extract target weights from a strategy.

        Strategies that expose should_rebalance(ts) → check the gate first.
        If the gate returns False, return {} (no rebalance this cycle).
        After computing weights, call mark_rebalanced(ts) if available.

        Strategies that expose compute_target_weights() → call that.
        Otherwise, run the callable to get orders → infer weights from order notional values.
        """
        # Check rebalance gate before computing
        if hasattr(callable_fn, 'should_rebalance'):
            if not callable_fn.should_rebalance(ts):
                log.debug("Strategy %s: rebalance gate blocked — skipping this cycle", strategy_id)
                return {}

        if hasattr(callable_fn, 'compute_target_weights'):
            if strategy_id == "S1":
                prices = data_replay.prices_until(ts)
                weights = callable_fn.compute_target_weights(prices)
            elif strategy_id == "S4":
                signals = getattr(callable_fn, '_signals_as_of', lambda t: None)(ts)
                weights = callable_fn.compute_target_weights(signals, as_of=ts)
            else:
                weights = {}

            # Mark rebalance time after successful computation
            if hasattr(callable_fn, 'mark_rebalanced'):
                callable_fn.mark_rebalanced(ts)
            return weights

        # S2 returns orders → infer weights
        orders = callable_fn(ts, data_replay, portfolio, market)
        if not orders:
            return {}

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