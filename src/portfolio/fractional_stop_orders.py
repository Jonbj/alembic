"""Broker-side protective stop for fractional Alpaca positions (#62/#63).

Alpaca rejects bracket/stop orders on notional/fractional quantities (error
42210000) — verified live 2026-07-16 that a STANDALONE (non-bracket) GTC stop
order on the whole-share floor of a fractional position IS accepted. This
module computes the desired stop (idempotent, re-derived every cycle from the
current position + d_hard) and diffs it against whatever stop order already
exists so the caller can reconcile with the broker.

The fractional residual (below the whole-share floor) is not protected — see
issue #62 for the rationale (residual is typically a small % of notional).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from src.portfolio.stop_policy import StopPolicy

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExistingStopOrder:
    """A currently-open broker stop order for one symbol (caller-supplied, not Alpaca-typed)."""

    id: str
    qty: float
    stop_price: float


@dataclass(frozen=True)
class ProtectiveStopPlan:
    """What to do to keep one symbol's broker-side protective stop in sync."""

    action: str  # "skip_no_whole_share" | "create" | "replace" | "noop" | "cancel_orphan"
    symbol: str
    whole_qty: int
    stop_price: float | None
    cancel_order_ids: tuple[str, ...] = ()


def plan_protective_stop(
    symbol: str,
    position_qty: float,
    avg_entry_price: float,
    strategy: str | None,
    current_sigma_eff: float | None,
    stop_policy: StopPolicy,
    cycle_ts: datetime,
    existing_stop_orders: list[ExistingStopOrder],
    price_tolerance: float = 0.005,
) -> ProtectiveStopPlan:
    """Decide whether to create/replace/leave-alone the protective stop for one symbol."""
    whole_qty = math.floor(abs(position_qty))
    if whole_qty < 1:
        return ProtectiveStopPlan(action="skip_no_whole_share", symbol=symbol, whole_qty=0, stop_price=None)

    frozen = stop_policy.freeze(symbol, strategy, avg_entry_price, cycle_ts)
    d_hard = stop_policy.d_hard(symbol, frozen, current_sigma_eff)
    stop_price = round(avg_entry_price * (1.0 - d_hard), 2)

    if len(existing_stop_orders) == 1:
        existing = existing_stop_orders[0]
        qty_matches = int(existing.qty) == whole_qty
        price_matches = abs(existing.stop_price - stop_price) / stop_price <= price_tolerance
        if qty_matches and price_matches:
            return ProtectiveStopPlan(action="noop", symbol=symbol, whole_qty=whole_qty, stop_price=stop_price)

    if not existing_stop_orders:
        return ProtectiveStopPlan(action="create", symbol=symbol, whole_qty=whole_qty, stop_price=stop_price)

    cancel_ids = tuple(o.id for o in existing_stop_orders)
    return ProtectiveStopPlan(
        action="replace", symbol=symbol, whole_qty=whole_qty, stop_price=stop_price, cancel_order_ids=cancel_ids,
    )


def build_protective_stop_plans(
    positions: Sequence,
    stop_orders_by_symbol: dict[str, list[ExistingStopOrder]],
    stop_policy: StopPolicy,
    cycle_ts: datetime,
    strategy_by_symbol: dict[str, str | None] | None = None,
    sigma_by_symbol: dict[str, float | None] | None = None,
) -> list[ProtectiveStopPlan]:
    """Turn a list of Alpaca positions into one reconciliation plan per symbol.

    Also emits a "cancel_orphan" plan for any symbol in stop_orders_by_symbol
    that has NO current position — a fully-closed position (weight -> 0) drops
    out of get_all_positions() the very next cycle, so a purely position-driven
    reconciliation would never cancel its now-orphaned GTC stop order (#62
    review finding). Reconciliation must be the union of positions AND
    existing-stop symbols, not positions alone.
    """
    strategy_by_symbol = strategy_by_symbol or {}
    sigma_by_symbol = sigma_by_symbol or {}
    plans = []
    held_symbols: set[str] = set()
    for p in positions:
        symbol = p.symbol
        held_symbols.add(symbol)
        plans.append(
            plan_protective_stop(
                symbol=symbol,
                position_qty=float(p.qty),
                avg_entry_price=float(p.avg_entry_price),
                strategy=strategy_by_symbol.get(symbol),
                current_sigma_eff=sigma_by_symbol.get(symbol),
                stop_policy=stop_policy,
                cycle_ts=cycle_ts,
                existing_stop_orders=stop_orders_by_symbol.get(symbol, []),
            )
        )
    for symbol, existing in stop_orders_by_symbol.items():
        if symbol in held_symbols or not existing:
            continue
        plans.append(
            ProtectiveStopPlan(
                action="cancel_orphan", symbol=symbol, whole_qty=0, stop_price=None,
                cancel_order_ids=tuple(o.id for o in existing),
            )
        )
    return plans


def execute_protective_stop_plans(plans: Sequence[ProtectiveStopPlan], trading_client) -> dict:
    """Cancel stale orders and submit fresh stop orders per plan.

    Never raises on a per-symbol broker failure — errors are collected so one
    reject doesn't stop the rest of the book from being reconciled.
    """
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import StopOrderRequest

    summary: dict = {
        "created": 0, "replaced": 0, "noop": 0, "skipped": 0,
        "cancelled_orphans": 0, "errors": [],
    }
    for plan in plans:
        if plan.action == "skip_no_whole_share":
            summary["skipped"] += 1
            continue
        if plan.action == "noop":
            summary["noop"] += 1
            continue
        if plan.action == "cancel_orphan":
            try:
                for order_id in plan.cancel_order_ids:
                    trading_client.cancel_order_by_id(order_id)
                summary["cancelled_orphans"] += 1
            except Exception as exc:
                log.warning("Failed to cancel orphan stop for %s: %s", plan.symbol, exc)
                summary["errors"].append({"symbol": plan.symbol, "error": str(exc)})
            continue
        try:
            for order_id in plan.cancel_order_ids:
                trading_client.cancel_order_by_id(order_id)
            req = StopOrderRequest(
                symbol=plan.symbol,
                qty=plan.whole_qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.GTC,
                stop_price=plan.stop_price,
            )
            trading_client.submit_order(req)
            summary["created" if plan.action == "create" else "replaced"] += 1
        except Exception as exc:
            log.warning("Failed to sync protective stop for %s: %s", plan.symbol, exc)
            summary["errors"].append({"symbol": plan.symbol, "error": str(exc)})
    return summary
