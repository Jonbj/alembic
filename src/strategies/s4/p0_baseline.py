"""Baseline P0 shadow del trial exit S4 (#296).

P0 osserva le decisioni e i fill E0 gia' prodotti dal runtime e li proietta
sulla sola quantita' virtuale S4. Il modulo non espone alcun client broker:
l'esecuzione resta una trasformazione pura e append-only ai bordi.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid5

import yaml

from src.strategies.s4.lifecycle import S4LifecycleEvent

_P0_NAMESPACE = UUID("10ad4bc3-ce9f-5b34-9f3d-9f8678f82960")
_QTY_TOLERANCE = 1e-9
_PRICE_TOLERANCE = 1e-9

_TARGET_ZERO_REASONS = {
    "no_signal": "P0_TARGET_ZERO_NO_SIGNAL",
    "expired": "P0_TARGET_ZERO_EXPIRED",
    "whipsaw": "P0_TARGET_ZERO_WHIPSAW",
    "unknown": "P0_TARGET_ZERO_UNKNOWN",
    "below_entry_gate": "P0_TARGET_ZERO_BELOW_ENTRY_GATE",
    "fallback_filtered": "P0_TARGET_ZERO_FALLBACK_FILTERED",
    "entry_freshness_filtered": "P0_TARGET_ZERO_ENTRY_FRESHNESS_FILTERED",
}
_DISABLED_REASONS = {
    "take_profit": "P0_TAKE_PROFIT_DISABLED",
    "trailing": "P0_TRAILING_DISABLED",
    "scale_out": "P0_SCALE_OUT_DISABLED",
    "tight_stop": "P0_TIGHT_STOP_DISABLED",
}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass(frozen=True)
class P0PolicySnapshot:
    version: str
    scope: str
    d_hard_enabled: bool
    take_profit_enabled: bool
    trailing_enabled: bool
    scale_out_enabled: bool
    tight_stop_enabled: bool
    source_hash: str


@dataclass(frozen=True)
class RuntimeExitObservation:
    runtime_decision_id: int | None
    runtime_order_id: str | None
    trigger_kind: str
    exit_mechanism: str | None
    trigger_at: datetime
    runtime_quantity: float
    first_executable_at: datetime | None
    first_executable_price: float | None
    first_executable_price_source: str
    filled_at: datetime | None
    filled_quantity: float
    fill_price: float | None
    raw_reason: str | None = None


@dataclass(frozen=True)
class P0ReplayEvent:
    event_id: str
    intent_id: str
    policy_id: str
    policy_version: str
    event_type: str
    observed_at: datetime
    d0: date | None
    symbol: str
    status: str
    reason_code: str
    trigger_at: datetime
    virtual_exit_quantity: float
    runtime_quantity: float
    first_executable_at: datetime | None
    first_executable_price: float | None
    first_executable_price_source: str
    filled_at: datetime | None
    fill_price: float | None
    initial_notional: float
    gross_pnl: float | None
    entry_cost_usd: float | None
    exit_cost_usd: float | None
    net_pnl: float | None
    cost_model_version: str
    runtime_decision_id: int | None
    runtime_order_id: str | None
    shadow_order_id: None
    comparable: bool
    divergence_reasons: tuple[str, ...]
    details: dict[str, object]


class CostModel(Protocol):
    version: str

    def compute(
        self,
        *,
        symbol: str,
        notional: float,
        qty: float,
        fill_price: float,
        side: str,
    ): ...


class VersionedTradeCostModel:
    """Adattatore condivisibile da P0 e challenger sul cost model congelato."""

    def __init__(self, config_path: Path = Path("config/cost_model.yaml")) -> None:
        from src.costs.calculator import TradeCostCalculator

        self._calculator = TradeCostCalculator(config_path)
        self.version = f"cost-model:{hashlib.sha256(config_path.read_bytes()).hexdigest()[:16]}"

    def compute(self, **kwargs):
        return self._calculator.compute(**kwargs)


def load_p0_policy_snapshot(
    path: Path | None = None,
) -> P0PolicySnapshot:
    """Carica P0 dalla controparte macchina e rifiuta derive dal contratto."""
    if path is None:
        path = Path(__file__).resolve().parents[3] / "config" / "s4_exit_trial.yaml"
    raw = path.read_bytes()
    payload = yaml.safe_load(raw) or {}
    contract = payload.get("contract") or {}
    p0 = (payload.get("policies") or {}).get("P0") or {}
    overlay = payload.get("risk_overlay") or {}

    if contract.get("scope") != "shadow_only" or contract.get("live_behaviour_changed"):
        raise ValueError("P0 contract must remain shadow-only")
    if p0.get("status") != "active" or p0.get("role") != "benchmark":
        raise ValueError("P0 must be the active benchmark")
    if p0.get("promotable") is not False:
        raise ValueError("P0 cannot be promotable")

    snapshot = P0PolicySnapshot(
        version=f"s4-exit-trial:{payload.get('version', 'unknown')}",
        scope=contract["scope"],
        d_hard_enabled=bool((overlay.get("d_hard") or {}).get("enabled")),
        take_profit_enabled=bool((overlay.get("take_profit") or {}).get("enabled")),
        trailing_enabled=bool((overlay.get("trailing") or {}).get("enabled")),
        scale_out_enabled=bool((overlay.get("scale_out") or {}).get("enabled")),
        tight_stop_enabled=bool(
            (overlay.get("tight_synthetic_stop") or {}).get("enabled")
        ),
        source_hash=hashlib.sha256(raw).hexdigest()[:16],
    )
    if not snapshot.d_hard_enabled:
        raise ValueError("P0 contract requires the common d_hard overlay")
    if any((
        snapshot.take_profit_enabled,
        snapshot.trailing_enabled,
        snapshot.scale_out_enabled,
        snapshot.tight_stop_enabled,
    )):
        raise ValueError("P0 contract forbids TP, trailing, scale-out and tight stop")
    return snapshot


def _reason_for(runtime: RuntimeExitObservation) -> tuple[str, str]:
    if runtime.trigger_kind in _DISABLED_REASONS:
        return "CENSORED", _DISABLED_REASONS[runtime.trigger_kind]
    if runtime.trigger_kind == "target_weight_zero":
        return "CLOSED", _TARGET_ZERO_REASONS.get(
            runtime.exit_mechanism or "unknown", "P0_TARGET_ZERO_UNKNOWN"
        )
    if runtime.trigger_kind == "sentiment_reversal":
        return "CLOSED", "P0_SENTIMENT_REVERSAL"
    if runtime.trigger_kind == "d_hard":
        return "RISK_EXITED", "P0_D_HARD"
    return "CENSORED", "P0_TRIGGER_UNCLASSIFIED"


def _expected_reason(runtime: RuntimeExitObservation) -> str:
    return _reason_for(runtime)[1]


def compare_p0_to_runtime(
    event: P0ReplayEvent,
    runtime: RuntimeExitObservation,
) -> tuple[str, ...]:
    """Confronto golden ordinato: trigger, quantita', tempo e primo prezzo."""
    divergences: list[str] = []
    if event.reason_code != _expected_reason(runtime):
        divergences.append("TRIGGER_MISMATCH")
    if abs(event.virtual_exit_quantity - runtime.runtime_quantity) > _QTY_TOLERANCE:
        divergences.append("QUANTITY_MISMATCH")
    if event.trigger_at != _utc(runtime.trigger_at):
        divergences.append("TRIGGER_TIME_MISMATCH")
    if event.first_executable_at != (
        _utc(runtime.first_executable_at) if runtime.first_executable_at else None
    ):
        divergences.append("FIRST_EXECUTABLE_TIME_MISMATCH")
    if (
        event.first_executable_price is None
        or runtime.first_executable_price is None
        or abs(event.first_executable_price - runtime.first_executable_price)
        > _PRICE_TOLERANCE
    ):
        divergences.append("FIRST_EXECUTABLE_PRICE_MISMATCH")
    return tuple(divergences)


def replay_p0(
    lifecycle: S4LifecycleEvent,
    runtime: RuntimeExitObservation,
    snapshot: P0PolicySnapshot,
    cost_model: CostModel,
) -> P0ReplayEvent:
    """Riproduce E0 sulla quantita' S4, senza inviare o alterare ordini."""
    status, reason_code = _reason_for(runtime)
    trigger_at = _utc(runtime.trigger_at)
    first_at = (
        _utc(runtime.first_executable_at) if runtime.first_executable_at else None
    )
    filled_at = _utc(runtime.filled_at) if runtime.filled_at else None
    virtual_quantity = lifecycle.s4_virtual_quantity if status != "CENSORED" else 0.0
    initial_notional = lifecycle.s4_virtual_quantity * (lifecycle.fill_price or 0.0)

    gross_pnl = entry_cost = exit_cost = net_pnl = None
    if status != "CENSORED" and (
        filled_at is None
        or runtime.fill_price is None
        or runtime.filled_quantity <= 0
        or first_at is None
        or runtime.first_executable_price is None
    ):
        status = "TRIGGERED"
        reason_code = "P0_EXIT_FILL_MISSING"
    elif status != "CENSORED":
        entry = cost_model.compute(
            symbol=lifecycle.symbol,
            notional=initial_notional,
            qty=lifecycle.s4_virtual_quantity,
            fill_price=float(lifecycle.fill_price or 0.0),
            side="BUY",
        )
        exit_notional = virtual_quantity * float(runtime.fill_price)
        exit_breakdown = cost_model.compute(
            symbol=lifecycle.symbol,
            notional=exit_notional,
            qty=virtual_quantity,
            fill_price=float(runtime.fill_price),
            side="SELL",
        )
        gross_pnl = (
            float(runtime.fill_price) - float(lifecycle.fill_price or 0.0)
        ) * virtual_quantity
        entry_cost = float(entry.total_cost_usd)
        exit_cost = float(exit_breakdown.total_cost_usd)
        net_pnl = gross_pnl - entry_cost - exit_cost

    fingerprint = "|".join((
        lifecycle.intent_id,
        snapshot.version,
        str(runtime.runtime_decision_id),
        runtime.runtime_order_id or "no-order",
        reason_code,
        trigger_at.isoformat(),
        "no-fill" if filled_at is None else filled_at.isoformat(),
        f"{runtime.filled_quantity:.12g}",
    ))
    event = P0ReplayEvent(
        event_id=str(uuid5(_P0_NAMESPACE, fingerprint)),
        intent_id=lifecycle.intent_id,
        policy_id="P0",
        policy_version=snapshot.version,
        event_type="P0_RUNTIME_REPLAY",
        observed_at=filled_at or trigger_at,
        d0=lifecycle.d0,
        symbol=lifecycle.symbol,
        status=status,
        reason_code=reason_code,
        trigger_at=trigger_at,
        virtual_exit_quantity=virtual_quantity,
        runtime_quantity=runtime.runtime_quantity,
        first_executable_at=first_at,
        first_executable_price=runtime.first_executable_price,
        first_executable_price_source=runtime.first_executable_price_source,
        filled_at=filled_at,
        fill_price=runtime.fill_price,
        initial_notional=initial_notional,
        gross_pnl=gross_pnl,
        entry_cost_usd=entry_cost,
        exit_cost_usd=exit_cost,
        net_pnl=net_pnl,
        cost_model_version=cost_model.version,
        runtime_decision_id=runtime.runtime_decision_id,
        runtime_order_id=runtime.runtime_order_id,
        shadow_order_id=None,
        comparable=False,
        divergence_reasons=(),
        details={
            "entry_fill_id": lifecycle.fill_id,
            "entry_first_executable_price": lifecycle.first_executable_price,
            "entry_policy_version": lifecycle.policy_version,
            "raw_runtime_reason": runtime.raw_reason,
            "snapshot_hash": snapshot.source_hash,
        },
    )
    if status == "TRIGGERED":
        divergences = ("EXIT_FILL_MISSING",)
    elif status == "CENSORED":
        divergences = (reason_code.removeprefix("P0_"),)
    else:
        divergences = compare_p0_to_runtime(event, runtime)
        if not lifecycle.reconstructible:
            divergences += ("ENTRY_NOT_RECONSTRUCTIBLE",)
    return replace(
        event,
        comparable=not divergences,
        divergence_reasons=divergences,
    )


def build_p0_replay_report(
    events: list[P0ReplayEvent],
    *,
    window_start: date,
    window_end: date,
    minimum_coverage: float = 0.95,
) -> dict[str, object]:
    """Misura la comparabilita' P0 su una riga logica per intento."""
    if window_end < window_start:
        raise ValueError("validation window ends before it starts")
    latest: dict[str, P0ReplayEvent] = {}
    for event in events:
        event_date = event.d0 or event.observed_at.date()
        if not window_start <= event_date <= window_end:
            continue
        current = latest.get(event.intent_id)
        if current is None or event.observed_at >= current.observed_at:
            latest[event.intent_id] = event
    total = len(latest)
    comparable = sum(event.comparable for event in latest.values())
    coverage = comparable / total if total else None
    residual = Counter(
        event.reason_code for event in latest.values() if not event.comparable
    )
    return {
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "minimum_coverage": minimum_coverage,
        "total": total,
        "comparable": comparable,
        "coverage": coverage,
        "meets_minimum": coverage is not None and coverage >= minimum_coverage,
        "residual_by_reason": dict(sorted(residual.items())),
    }
