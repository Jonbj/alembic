"""Adattatore read-only fra osservazioni runtime e baseline P0 (#296)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from src.strategies.s4.lifecycle import S4LifecycleEvent
from src.strategies.s4.p0_baseline import (
    RuntimeExitObservation,
    VersionedTradeCostModel,
    load_p0_policy_snapshot,
    observe_p0_open,
    replay_p0,
)

log = logging.getLogger(__name__)


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value)).casefold()


def _lifecycle_from_row(row: dict[str, Any]) -> S4LifecycleEvent:
    return S4LifecycleEvent(
        event_id=str(row["event_id"]),
        intent_id=str(row["intent_id"]),
        event_type=row["event_type"],
        observed_at=row["observed_at"],
        symbol=row["symbol"],
        order_id=row.get("order_id"),
        status=row["status"],
        reason_code=row["reason_code"],
        fill_id=str(row["fill_id"]) if row.get("fill_id") else None,
        filled_at=row.get("filled_at"),
        filled_quantity=float(row.get("filled_quantity") or 0.0),
        filled_notional=float(row.get("filled_notional") or 0.0),
        fill_price=(float(row["fill_price"]) if row.get("fill_price") else None),
        first_executable_price=float(row.get("first_executable_price") or 0.0),
        first_executable_price_source=(
            row.get("first_executable_price_source") or "not_recorded"
        ),
        d0=row.get("d0"),
        due_session=row.get("due_session"),
        policy_version=row["policy_version"],
        s1_virtual_quantity=float(row.get("s1_virtual_quantity") or 0.0),
        s4_virtual_quantity=float(row.get("s4_virtual_quantity") or 0.0),
        broker_quantity=(
            float(row["broker_quantity"])
            if row.get("broker_quantity") is not None
            else None
        ),
        unattributed_quantity=(
            float(row["unattributed_quantity"])
            if row.get("unattributed_quantity") is not None
            else None
        ),
        reconstructible=bool(row.get("reconstructible")),
        details=dict(row.get("details") or {}),
    )


def _trigger_kind(
    row: dict[str, Any], orders: list[object]
) -> str:
    mechanism = row.get("exit_mechanism")
    if mechanism:
        return "target_weight_zero"
    reason = " ".join((
        str(row.get("runtime_exit_reason") or ""),
        str(row.get("runtime_reason") or ""),
    )).casefold()
    if "sentiment_reversal" in reason:
        return "sentiment_reversal"
    if len(row.get("runtime_order_ids") or ()) > 1:
        return "scale_out"
    order_types = {_enum_value(getattr(order, "type", "")) for order in orders}
    if "take_profit" in reason or "limit" in order_types:
        return "take_profit"
    if "trailing" in reason or "trailing_stop" in order_types:
        return "trailing"
    if "stop" in order_types or "stop_limit" in order_types:
        return "d_hard"
    if "stop_loss" in reason:
        return "tight_stop"
    return "unknown"


def _runtime_observation(
    row: dict[str, Any], trading_client
) -> RuntimeExitObservation:
    orders: list[object] = []
    for order_id in row.get("runtime_order_ids") or ():
        if not order_id:
            continue
        try:
            orders.append(trading_client.get_order_by_id(order_id))
        except Exception as exc:  # noqa: BLE001 - il client Alpaca non ha una base comune
            log.warning("#296: exit order %s unavailable for P0 replay: %s", order_id, exc)
            continue

    fills: list[tuple[datetime, float, float]] = []
    for order in orders:
        filled_at = getattr(order, "filled_at", None)
        if isinstance(filled_at, str):
            filled_at = datetime.fromisoformat(filled_at)
        if filled_at is not None and filled_at.tzinfo is None:
            filled_at = filled_at.replace(tzinfo=UTC)
        raw_qty = getattr(order, "filled_qty", None)
        raw_price = getattr(order, "filled_avg_price", None)
        if filled_at is None or raw_qty is None or raw_price is None:
            continue
        quantity = float(raw_qty)
        price = float(raw_price)
        if quantity > 0 and price > 0:
            fills.append((filled_at.astimezone(UTC), quantity, price))

    fills.sort(key=lambda fill: fill[0])
    total_quantity = sum(fill[1] for fill in fills)
    fill_price = (
        sum(price * quantity for _, quantity, price in fills) / total_quantity
        if total_quantity > 0
        else None
    )
    first_fill = fills[0] if fills else None
    trigger_at = row.get("trigger_at") or row["runtime_exit_time"]
    if trigger_at.tzinfo is None:
        trigger_at = trigger_at.replace(tzinfo=UTC)
    runtime_order_ids = [
        str(order_id) for order_id in (row.get("runtime_order_ids") or ()) if order_id
    ]
    return RuntimeExitObservation(
        runtime_decision_id=row.get("runtime_decision_id"),
        runtime_order_id=runtime_order_ids[0] if len(runtime_order_ids) == 1 else None,
        trigger_kind=_trigger_kind(row, orders),
        exit_mechanism=row.get("exit_mechanism"),
        trigger_at=trigger_at.astimezone(UTC),
        runtime_quantity=total_quantity,
        first_executable_at=first_fill[0] if first_fill else None,
        first_executable_price=first_fill[2] if first_fill else None,
        first_executable_price_source="alpaca_order.filled_avg_price",
        filled_at=max((fill[0] for fill in fills), default=None),
        filled_quantity=total_quantity,
        fill_price=fill_price,
        raw_reason=row.get("runtime_reason") or row.get("runtime_exit_reason"),
        runtime_order_ids=tuple(runtime_order_ids),
    )


def replay_p0_candidates(store, trading_client) -> int:
    """Proietta i close runtime su P0; usa sul broker soltanto letture per ID."""
    rows = store.fetch_s4_p0_replay_candidates()
    if not rows:
        return 0
    snapshot = load_p0_policy_snapshot()
    cost_model = VersionedTradeCostModel()
    events = []
    for row in rows:
        lifecycle = _lifecycle_from_row(row)
        if row.get("runtime_exit_time") is None:
            event = observe_p0_open(
                lifecycle,
                snapshot,
                cost_model,
                runtime_trade_id=row.get("runtime_trade_id"),
            )
        else:
            event = replay_p0(
                lifecycle,
                _runtime_observation(row, trading_client),
                snapshot,
                cost_model,
            )
        events.append(event)
    store.write_s4_exit_policy_events(events)
    return len(events)
