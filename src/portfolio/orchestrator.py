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
    # #185: strategies whose rebalance gate was closed this cycle — they held
    # their book instead of re-deciding weights. The scheduler needs them to
    # tell a legitimate hold apart from a silent death (_check_strategy_zero_weights).
    rebalance_skipped: list[str] = field(default_factory=list)
    # #185: sleeve-local weights each strategy actually DECIDED this cycle (absent
    # for the ones that held). The scheduler persists these so the next cycle can
    # rebuild the frozen target from Redis after the instance is thrown away.
    target_weights_per_strategy: dict[str, dict[str, float]] = field(default_factory=dict)
    # B33-follow-up: per-symbol {signal_id, score, reasoning, model_id} pinned
    # by S4 at the exact moment it computed weights this cycle. The scheduler
    # must use this for decision logging + idempotency instead of re-fetching
    # "latest signal" later, which can race a signal that arrives in between
    # (see the 2026-07-15 MSFT incident: ranker used +0.165, a later re-fetch
    # picked up a -0.110 signal that arrived 34s after). Only symbols S4
    # actually ranked this cycle are present; other strategies contribute none.
    symbol_signal_provenance: dict[str, dict] = field(default_factory=dict)


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
        last_target_weights: dict[str, dict[str, float]] | None = None,
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
            last_target_weights: Optional {strategy_id: sleeve-local weights} decided
                at that strategy's last rebalance. Only read for strategies whose
                `should_rebalance(ts)` gate is closed this cycle: they hold exactly
                the symbols they targeted then and still own now (#185). Missing or
                None → the sleeve contributes nothing, which is safe because a
                strategy with no rebalance memory always has its gate open.

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
        symbol_signal_provenance: dict[str, dict] = {}
        rebalance_skipped: list[str] = []
        target_weights_per_strategy: dict[str, dict[str, float]] = {}

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
                # #185: the declared rebalance cadence gates the whole sleeve. When
                # the gate is closed the strategy neither re-decides nor drifts —
                # it re-declares what it already holds, so the merge below sees a
                # zero delta instead of reading the missing symbols as "sell all".
                if not self._gate_open(callable_fn, ts):
                    tw = self._hold_weights(
                        entry.strategy_id, entry.allocation_pct,
                        portfolio, market, nav, last_target_weights,
                    )
                    rebalance_skipped.append(entry.strategy_id)
                    log.info(
                        "Strategy %s: rebalance gate closed — holding %d position(s), "
                        "no weight re-decision this cycle",
                        entry.strategy_id, len(tw),
                    )
                else:
                    # Strategy returns a list[Order], but we need target weights.
                    # Strategies that have compute_target_weights() — use those directly.
                    # For strategies that only return orders, we extract implied weights.
                    tw = self._extract_target_weights(
                        entry.strategy_id, callable_fn, ts, data_replay, portfolio, market, nav
                    )
                    target_weights_per_strategy[entry.strategy_id] = tw
                strategies_run.append(entry.strategy_id)
                orders_per_strategy[entry.strategy_id] = len(tw)

                # B33-follow-up: pin S4's per-symbol signal provenance right
                # here, in the same call that computed the weights — never
                # re-derived later from a fresh DB query.
                _provenance = getattr(callable_fn, "last_signal_provenance", None)
                if _provenance:
                    for sym in tw:
                        if sym in _provenance:
                            symbol_signal_provenance[sym] = _provenance[sym]

                # Merge: weighted sum (sleeve-local semantics).
                # Strategies produce sleeve-local weights (fraction of their own sleeve).
                # Multiplying by allocation_pct gives portfolio-level contribution.
                # Two strategies both holding a symbol correctly ADD their contributions —
                # that symbol genuinely receives combined capital from both sleeves.
                alloc = entry.allocation_pct
                for sym, wt in tw.items():
                    merged_weights[sym] = merged_weights.get(sym, 0.0) + wt * alloc
                    symbol_strategies.setdefault(sym, []).append(entry.strategy_id)

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
            "Portfolio cycle complete: strategies=%s held=%s merged_weights=%d symbols "
            "orders_before=%d orders_after=%d constraints=%d",
            strategies_run,
            rebalance_skipped,
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
            symbol_signal_provenance=symbol_signal_provenance,
            rebalance_skipped=rebalance_skipped,
            target_weights_per_strategy=target_weights_per_strategy,
        )

    # ── Private ────────────────────────────────────────────────────────────────

    @staticmethod
    def _gate_open(callable_fn, ts) -> bool:
        """Whether the strategy's declared rebalance cadence allows a decision at ts.

        Deliberately delegates to the strategy's own predicate — the same one the
        backtest calls from __call__ — so live and backtest cannot drift apart on
        cadence (#185). Strategies without the predicate rebalance every cycle.
        """
        if not hasattr(callable_fn, "should_rebalance"):
            return True
        return bool(callable_fn.should_rebalance(ts))

    def _hold_weights(
        self, strategy_id: str, alloc: float, portfolio, market, nav,
        last_target_weights: dict[str, dict[str, float]] | None,
    ) -> dict[str, float]:
        """Sleeve-local weights that reproduce what the strategy already holds.

        Derived from the *current* position value rather than from the frozen
        target, so `wt * alloc * nav / price` lands back on the exact quantity in
        the book: no drift trim, no re-entry, no liquidation. Restricted to the
        symbols decided at the last rebalance, so a position another sleeve owns
        is never claimed here — and a symbol closed meanwhile (a stop-out) is not
        bought back before the next rebalance window.
        """
        frozen = (last_target_weights or {}).get(strategy_id) or {}
        if nav <= 0 or alloc <= 0 or not frozen:
            return {}

        held: dict[str, float] = {}
        for symbol in frozen:
            pos = portfolio.position_of(symbol)
            if pos is None or pos.quantity <= 0:
                continue
            price = market.price_of(symbol)
            if price is None or price <= 0:
                continue
            held[symbol] = (pos.quantity * price / nav) / alloc
        return held

    def _extract_target_weights(
        self, strategy_id: str, callable_fn, ts, data_replay, portfolio, market, nav
    ) -> dict[str, float]:
        """Extract target weights from a strategy.

        Called only when the rebalance gate is open (see `_gate_open`).
        After computing weights, call mark_rebalanced(ts) if available.

        Strategies that expose compute_target_weights() → call that.
        Otherwise, run the callable to get orders → infer weights from order notional values.
        """
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