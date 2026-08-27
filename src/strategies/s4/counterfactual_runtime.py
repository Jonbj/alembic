"""Wiring read-only per replacement e opportunity cost S4 (#298).

Il modulo traduce le righe append-only gia' osservate nelle forme pure di
``counterfactual``. Non sceglie soglie, non invia ordini e non ricostruisce un
universo a posteriori: per ogni slot usa soltanto l'ultimo ``decision_slot``
che esisteva quando il capitale si e' liberato.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from src.strategies.s4.counterfactual import (
    FreedSlot,
    PolicyOutcome,
    SubstituteCandidate,
)

_TERMINAL_STATUSES = frozenset({"CLOSED", "RISK_EXITED"})


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def policy_outcome_from_row(row: Mapping[str, Any]) -> PolicyOutcome:
    """Adatta una riga di ``s4_exit_policy_current`` senza cambiarne il senso."""
    details = dict(row.get("details") or {})
    filled_at = row.get("filled_at")
    trigger_at = row.get("trigger_at")
    exit_at = filled_at or trigger_at
    return PolicyOutcome(
        intent_id=str(row["intent_id"]),
        policy_id=str(row["policy_id"]),
        symbol=str(row["symbol"]),
        d0=row.get("d0"),
        entry_fill_id=(
            str(details["entry_fill_id"])
            if details.get("entry_fill_id") is not None
            else None
        ),
        initial_notional=float(row.get("initial_notional") or 0.0),
        status=str(row.get("status") or "UNKNOWN"),
        exit_reason_code=str(row.get("reason_code") or "UNCLASSIFIED"),
        exit_at=_utc(exit_at) if exit_at is not None else None,
        virtual_exit_quantity=float(row.get("virtual_exit_quantity") or 0.0),
        net_pnl=(
            None if row.get("net_pnl") is None else float(row["net_pnl"])
        ),
        comparable=bool(row.get("comparable")),
    )


def build_freed_slots(
    outcomes: Sequence[PolicyOutcome],
    *,
    baseline_policy_id: str,
    policy_id: str,
) -> list[FreedSlot]:
    """Costruisce la finestra liberata dalla policy che esce per prima.

    Lo slot termina quando esce anche l'altra policy della coppia: oltre quel
    punto entrambe avrebbero di nuovo lo stesso capitale disponibile e non
    esiste piu' un opportunity cost attribuibile alla regola di uscita.
    """
    by_key = {
        (outcome.policy_id, outcome.intent_id): outcome for outcome in outcomes
    }
    intent_ids = sorted(
        outcome.intent_id
        for outcome in outcomes
        if outcome.policy_id == baseline_policy_id
    )
    slots: list[FreedSlot] = []
    for intent_id in intent_ids:
        baseline = by_key.get((baseline_policy_id, intent_id))
        challenger = by_key.get((policy_id, intent_id))
        if baseline is None or challenger is None:
            continue
        if (
            baseline.status not in _TERMINAL_STATUSES
            or challenger.status not in _TERMINAL_STATUSES
            or baseline.exit_at is None
            or challenger.exit_at is None
            or baseline.exit_at == challenger.exit_at
        ):
            continue
        earlier, later = sorted(
            (baseline, challenger), key=lambda outcome: _utc(outcome.exit_at)  # type: ignore[arg-type]
        )
        assert earlier.exit_at is not None and later.exit_at is not None
        slots.append(
            FreedSlot(
                intent_id=intent_id,
                symbol=earlier.symbol,
                policy_id=earlier.policy_id,
                freed_at=_utc(earlier.exit_at),
                freed_notional=earlier.initial_notional,
                slot_closes_at=_utc(later.exit_at),
            )
        )
    return slots


def _candidate_is_investable(row: Mapping[str, Any]) -> bool:
    reason = str(row.get("reason_code") or "")
    # Il primo escluso dal top-N e' proprio il sostituto potenziale: la sua
    # ``is_tradable`` e' falsa soltanto perche' lo slot non era ancora libero.
    if reason == "RANK_OUTSIDE_TOP_N":
        return True
    if reason.startswith("SKIP_") or reason == "BROKER_REJECT":
        return False
    return bool(row.get("is_tradable"))


def _s1_collision(row: Mapping[str, Any]) -> bool:
    state = dict(row.get("s1_state") or {})
    return bool(state.get("held_by_s1") or state.get("targeted"))


def _prices_in_window(
    bars: Sequence[tuple[datetime, float]],
    start: datetime,
    end: datetime,
) -> tuple[float, float | None]:
    observed = sorted(
        (_utc(at), float(price))
        for at, price in bars
        if price is not None and _utc(start) <= _utc(at) <= _utc(end)
    )
    if not observed:
        return 0.0, None
    return observed[0][1], observed[-1][1]


def build_point_in_time_candidates(
    slots: Sequence[FreedSlot],
    intent_rows: Sequence[Mapping[str, Any]],
    bars_by_symbol: Mapping[str, Sequence[tuple[datetime, float]]],
) -> dict[str, list[SubstituteCandidate]]:
    """Ricostruisce i candidati dall'ultimo universo noto quando apre lo slot."""
    result: dict[str, list[SubstituteCandidate]] = {}
    for slot in slots:
        eligible_rows = [
            row
            for row in intent_rows
            if row.get("decision_slot") is not None
            and row.get("occurred_at") is not None
            and row.get("decision_at") is not None
            and _utc(row["decision_slot"]) <= _utc(slot.freed_at)
            and _utc(row["occurred_at"]) <= _utc(slot.freed_at)
            and _utc(row["decision_at"]) <= _utc(slot.freed_at)
        ]
        if not eligible_rows:
            result[slot.intent_id] = []
            continue
        latest_slot = max(_utc(row["decision_slot"]) for row in eligible_rows)
        current_rows = [
            row
            for row in eligible_rows
            if _utc(row["decision_slot"]) == latest_slot
            and str(row.get("symbol") or "") != slot.symbol
        ]
        candidates: list[SubstituteCandidate] = []
        for row in sorted(
            current_rows,
            key=lambda item: (
                item.get("rank") is None,
                int(item.get("rank") or 0),
                str(item.get("symbol") or ""),
            ),
        ):
            symbol = str(row["symbol"])
            entry_price, exit_price = _prices_in_window(
                bars_by_symbol.get(symbol, ()),
                slot.freed_at,
                slot.slot_closes_at,
            )
            investable = _candidate_is_investable(row)
            candidates.append(
                SubstituteCandidate(
                    symbol=symbol,
                    signal_id=(
                        None
                        if row.get("signal_id") is None
                        else int(row["signal_id"])
                    ),
                    rank=None if row.get("rank") is None else int(row["rank"]),
                    observed_at=_utc(row["occurred_at"]),
                    universe_as_of=_utc(row["decision_at"]),
                    entry_price=entry_price,
                    exit_price=exit_price,
                    investable=investable,
                    collides_with_s1=_s1_collision(row),
                    investable_reason=(
                        None if investable else str(row.get("reason_code") or "UNKNOWN")
                    ),
                )
            )
        result[slot.intent_id] = candidates
    return result
