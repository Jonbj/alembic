"""Ricostruzione shadow del lifecycle S4 al confine broker (#295).

Il modulo e' puro: descrive fill e quantita' virtuali, ma non conosce ne'
invoca un client broker. La persistenza e il polling Alpaca restano ai bordi.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Literal
from uuid import UUID, uuid5


_LIFECYCLE_NAMESPACE = UUID("bf9f91ef-5392-5915-b3e6-9ad7b48a2950")
_QTY_EPSILON = 1e-9


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class MarketSession:
    session_date: date
    open_at: datetime
    close_at: datetime


@dataclass(frozen=True)
class SubmittedIntent:
    intent_id: str
    symbol: str
    order_id: str
    submitted_at: datetime
    requested_quantity: float
    requested_notional: float
    first_executable_price: float
    first_executable_price_source: str
    policy_version: str
    sleeve_contributions: dict[str, float]


@dataclass(frozen=True)
class BrokerOrderSnapshot:
    order_id: str
    status: str
    filled_at: datetime | None
    filled_quantity: float
    filled_avg_price: float | None
    lookup_error: str | None = None


@dataclass(frozen=True)
class S4LifecycleEvent:
    event_id: str
    intent_id: str
    event_type: str
    observed_at: datetime
    symbol: str
    order_id: str
    status: str
    reason_code: str
    fill_id: str | None
    filled_at: datetime | None
    filled_quantity: float
    filled_notional: float
    first_executable_price: float
    first_executable_price_source: str
    d0: date | None
    due_session: date | None
    policy_version: str
    s1_virtual_quantity: float
    s4_virtual_quantity: float
    broker_quantity: float | None
    unattributed_quantity: float | None
    reconstructible: bool
    details: dict[str, object]


@dataclass(frozen=True)
class S4VirtualExitEvent:
    event_id: str
    intent_id: str
    event_type: str
    observed_at: datetime
    symbol: str
    status: str
    reason_code: str
    price: float
    virtual_exit_quantity: float
    s1_virtual_quantity: float
    s4_virtual_quantity: float
    policy_version: str
    broker_order_id: None = None


def _status_and_reason(status: str, filled_quantity: float) -> tuple[str, str, bool]:
    normalized = status.casefold().replace("-", "_")
    if normalized in {"filled"}:
        return "FILLED", "BROKER_FILLED", True
    if normalized in {"partially_filled", "partial_fill"} or filled_quantity > 0:
        return "PARTIAL_FILL", "PARTIAL_FILL_OPEN", False
    if normalized in {"rejected", "suspended"}:
        return "REJECTED", "BROKER_REJECTED", True
    if normalized in {"canceled", "cancelled", "expired", "replaced"}:
        return "CANCELLED", "BROKER_CANCELLED", True
    return "MISSING_FILL", "AWAITING_FILL", False


def _fill_id(order: BrokerOrderSnapshot) -> str | None:
    if order.filled_quantity <= 0 or order.filled_at is None:
        return None
    raw = "|".join((
        order.order_id,
        _utc(order.filled_at).isoformat(),
        f"{order.filled_quantity:.12g}",
        "" if order.filled_avg_price is None else f"{order.filled_avg_price:.12g}",
    ))
    return str(uuid5(_LIFECYCLE_NAMESPACE, f"fill|{raw}"))


def _session_dates(
    filled_at: datetime | None, sessions: list[MarketSession]
) -> tuple[date | None, date | None, str | None]:
    if filled_at is None:
        return None, None, None
    fill_utc = _utc(filled_at)
    ordered = sorted(sessions, key=lambda session: session.session_date)
    index = next(
        (
            idx
            for idx, session in enumerate(ordered)
            if _utc(session.open_at) <= fill_utc <= _utc(session.close_at)
        ),
        None,
    )
    if index is None:
        return None, None, "FILL_OUTSIDE_RTH"
    if index + 2 >= len(ordered):
        return ordered[index].session_date, None, "CALENDAR_INCOMPLETE"
    return ordered[index].session_date, ordered[index + 2].session_date, None


def _virtual_quantities(
    filled_quantity: float, contributions: dict[str, float]
) -> tuple[float, float, str | None]:
    positive = {key: max(0.0, float(value)) for key, value in contributions.items()}
    total = sum(positive.values())
    if filled_quantity <= 0:
        return 0.0, 0.0, None
    if total <= 0 or positive.get("S4", 0.0) <= 0:
        return 0.0, 0.0, "SLEEVE_CONTRIBUTION_MISSING"
    s1 = filled_quantity * positive.get("S1", 0.0) / total
    s4 = filled_quantity * positive.get("S4", 0.0) / total
    return s1, s4, None


def reconcile_entry(
    intent: SubmittedIntent,
    order: BrokerOrderSnapshot,
    sessions: list[MarketSession],
    observed_at: datetime,
    *,
    broker_position_quantity: float | None,
    market_event: Literal["corporate_action", "gap"] | None = None,
) -> S4LifecycleEvent:
    """Riconcilia un intento con uno snapshot broker senza correggere residui."""
    if order.order_id != intent.order_id:
        raise ValueError("broker order does not belong to the submitted S4 intent")

    status, reason, reconstructible = _status_and_reason(
        order.status, order.filled_quantity
    )
    d0, due_session, session_error = _session_dates(order.filled_at, sessions)
    s1_qty, s4_qty, sleeve_error = _virtual_quantities(
        order.filled_quantity, intent.sleeve_contributions
    )
    virtual_total = s1_qty + s4_qty
    difference = (
        None
        if broker_position_quantity is None
        else float(broker_position_quantity) - virtual_total
    )

    if order.lookup_error is not None:
        status, reason, reconstructible = (
            "MISSING_FILL",
            "BROKER_ORDER_LOOKUP_FAILED",
            False,
        )
    elif market_event == "corporate_action":
        status, reason, reconstructible = "CENSORED", "CORPORATE_ACTION", False
    elif session_error is not None:
        status, reason, reconstructible = "CENSORED", session_error, False
    elif sleeve_error is not None:
        status, reason, reconstructible = "CENSORED", sleeve_error, False
    elif intent.first_executable_price <= 0:
        status, reason, reconstructible = (
            "CENSORED",
            "FIRST_EXECUTABLE_PRICE_MISSING",
            False,
        )
    elif broker_position_quantity is None:
        reason, reconstructible = "BROKER_POSITION_MISSING", False
    elif abs(difference or 0.0) > _QTY_EPSILON:
        reason = (
            "BROKER_SURPLUS_UNATTRIBUTED"
            if difference is not None and difference > 0
            else "BROKER_DEFICIT_UNEXPLAINED"
        )
        reconstructible = False
    elif market_event == "gap" and status == "FILLED":
        reason = "FILLED_AFTER_GAP"

    filled_notional = (
        order.filled_quantity * order.filled_avg_price
        if order.filled_avg_price is not None
        else 0.0
    )
    fill_id = _fill_id(order)
    fingerprint = "|".join((
        intent.intent_id,
        order.order_id,
        status,
        reason,
        fill_id or "no-fill",
        "missing" if broker_position_quantity is None else f"{broker_position_quantity:.12g}",
        market_event or "no-market-event",
    ))
    details: dict[str, object] = {
        "broker_status": order.status,
        "broker_lookup_error": order.lookup_error,
        "requested_quantity": intent.requested_quantity,
        "requested_notional": intent.requested_notional,
        "sleeve_contributions": dict(sorted(intent.sleeve_contributions.items())),
        "market_event": market_event,
    }
    return S4LifecycleEvent(
        event_id=str(uuid5(_LIFECYCLE_NAMESPACE, f"entry|{fingerprint}")),
        intent_id=intent.intent_id,
        event_type="ENTRY_RECONCILIATION",
        observed_at=_utc(observed_at),
        symbol=intent.symbol,
        order_id=order.order_id,
        status=status,
        reason_code=reason,
        fill_id=fill_id,
        filled_at=_utc(order.filled_at) if order.filled_at else None,
        filled_quantity=order.filled_quantity,
        filled_notional=filled_notional,
        first_executable_price=intent.first_executable_price,
        first_executable_price_source=intent.first_executable_price_source,
        d0=d0,
        due_session=due_session,
        policy_version=intent.policy_version,
        s1_virtual_quantity=s1_qty,
        s4_virtual_quantity=s4_qty,
        broker_quantity=broker_position_quantity,
        unattributed_quantity=difference,
        reconstructible=reconstructible,
        details=details,
    )


def apply_virtual_s4_exit(
    lifecycle: S4LifecycleEvent,
    *,
    quantity: float,
    price: float,
    observed_at: datetime,
    reason_code: str,
) -> S4VirtualExitEvent:
    """Applica un close solo alla sleeve virtuale; non esiste un broker seam."""
    if quantity <= 0:
        raise ValueError("virtual exit quantity must be positive")
    if quantity > lifecycle.s4_virtual_quantity + _QTY_EPSILON:
        raise ValueError("virtual exit quantity exceeds the S4 sleeve")
    remaining = max(0.0, lifecycle.s4_virtual_quantity - quantity)
    raw = "|".join((
        lifecycle.intent_id,
        reason_code,
        _utc(observed_at).isoformat(),
        f"{quantity:.12g}",
        f"{price:.12g}",
    ))
    return S4VirtualExitEvent(
        event_id=str(uuid5(_LIFECYCLE_NAMESPACE, f"virtual-exit|{raw}")),
        intent_id=lifecycle.intent_id,
        event_type="VIRTUAL_S4_EXIT",
        observed_at=_utc(observed_at),
        symbol=lifecycle.symbol,
        status="VIRTUAL_EXITED",
        reason_code=reason_code,
        price=price,
        virtual_exit_quantity=quantity,
        s1_virtual_quantity=lifecycle.s1_virtual_quantity,
        s4_virtual_quantity=remaining,
        policy_version=lifecycle.policy_version,
    )


def build_reconstruction_report(
    events: list[S4LifecycleEvent],
    *,
    window_start: date,
    window_end: date,
    minimum_coverage: float = 0.95,
) -> dict[str, object]:
    """Una riga logica per intento e residuo contato per reason code."""
    if window_end < window_start:
        raise ValueError("validation window ends before it starts")
    latest: dict[str, S4LifecycleEvent] = {}
    for event in events:
        event_date = event.d0 or event.observed_at.date()
        if not window_start <= event_date <= window_end:
            continue
        current = latest.get(event.intent_id)
        if current is None or event.observed_at >= current.observed_at:
            latest[event.intent_id] = event
    total = len(latest)
    reconstructed = sum(event.reconstructible for event in latest.values())
    coverage = reconstructed / total if total else None
    residual = Counter(
        event.reason_code for event in latest.values() if not event.reconstructible
    )
    return {
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "minimum_coverage": minimum_coverage,
        "total": total,
        "reconstructible": reconstructed,
        "coverage": coverage,
        "meets_minimum": coverage is not None and coverage >= minimum_coverage,
        "residual_by_reason": dict(sorted(residual.items())),
    }
