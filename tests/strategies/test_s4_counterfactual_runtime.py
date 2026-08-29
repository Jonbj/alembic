"""#298: wiring read-only dalle osservazioni alle viste controfattuali."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from src.strategies.s4.counterfactual import build_portfolio_counterfactual
from src.strategies.s4.counterfactual_runtime import (
    build_freed_slots,
    build_point_in_time_candidates,
    policy_outcome_from_row,
)

P0_EXIT = datetime(2026, 8, 25, 17, 52, 3, tzinfo=UTC)
P1_EXIT = datetime(2026, 8, 27, 19, 59, tzinfo=UTC)


def _policy_row(policy_id: str, **overrides) -> dict:
    values = {
        "intent_id": "intent-1",
        "policy_id": policy_id,
        "symbol": "AMD",
        "d0": date(2026, 8, 25),
        "initial_notional": 1000.0,
        "status": "CLOSED",
        "reason_code": (
            "P0_TARGET_ZERO_EXPIRED" if policy_id == "P0" else "P1_TIME_DUE"
        ),
        "trigger_at": P0_EXIT if policy_id == "P0" else P1_EXIT,
        "filled_at": P0_EXIT if policy_id == "P0" else P1_EXIT,
        "virtual_exit_quantity": 10.0,
        "net_pnl": 10.0 if policy_id == "P0" else 35.0,
        "comparable": True,
        "details": {"entry_fill_id": "fill-1"},
    }
    values.update(overrides)
    return values


def _intent_row(symbol: str, rank: int, **overrides) -> dict:
    values = {
        "intent_id": f"candidate-{symbol}",
        "symbol": symbol,
        "signal_id": rank,
        "rank": rank,
        "occurred_at": P0_EXIT - timedelta(seconds=3),
        "decision_slot": P0_EXIT.replace(second=0, microsecond=0),
        "decision_at": P0_EXIT - timedelta(seconds=3),
        "is_tradable": rank <= 5,
        "reason_code": "RANK_SELECTED" if rank <= 5 else "RANK_OUTSIDE_TOP_N",
        "s1_state": {"held_by_s1": False, "targeted": False},
        "anti_pyramiding": False,
    }
    values.update(overrides)
    return values


def test_policy_row_diventa_outcome_senza_reinterpretare_la_provenance():
    outcome = policy_outcome_from_row(_policy_row("P0"))

    assert outcome.intent_id == "intent-1"
    assert outcome.entry_fill_id == "fill-1"
    assert outcome.exit_at == P0_EXIT
    assert outcome.net_pnl == pytest.approx(10.0)
    assert outcome.comparable is True


def test_lo_slot_e_l_intervallo_fra_l_uscita_anticipata_e_quella_appaiata():
    outcomes = [
        policy_outcome_from_row(_policy_row("P0")),
        policy_outcome_from_row(_policy_row("P1")),
    ]

    [slot] = build_freed_slots(outcomes, baseline_policy_id="P0", policy_id="P1")

    assert slot.intent_id == "intent-1"
    assert slot.policy_id == "P0"
    assert slot.freed_at == P0_EXIT
    assert slot.slot_closes_at == P1_EXIT
    assert slot.freed_notional == pytest.approx(1000.0)


def test_se_la_challenger_esce_prima_lo_slot_appartiene_alla_challenger():
    outcomes = [
        policy_outcome_from_row(_policy_row("P0", filled_at=P1_EXIT)),
        policy_outcome_from_row(_policy_row("P1", filled_at=P0_EXIT)),
    ]

    [slot] = build_freed_slots(outcomes, baseline_policy_id="P0", policy_id="P1")

    assert slot.policy_id == "P1"
    assert slot.freed_at == P0_EXIT
    assert slot.slot_closes_at == P1_EXIT


def test_un_esito_non_terminale_non_inventa_uno_slot():
    outcomes = [
        policy_outcome_from_row(_policy_row("P0")),
        policy_outcome_from_row(
            _policy_row("P1", status="OPEN", filled_at=None, net_pnl=None)
        ),
    ]

    assert build_freed_slots(outcomes, baseline_policy_id="P0", policy_id="P1") == []


def test_i_candidati_usano_solo_l_ultimo_universo_gia_osservato_e_barre_nella_finestra():
    [slot] = build_freed_slots(
        [
            policy_outcome_from_row(_policy_row("P0")),
            policy_outcome_from_row(_policy_row("P1")),
        ],
        baseline_policy_id="P0",
        policy_id="P1",
    )
    previous_slot = P0_EXIT - timedelta(minutes=15)
    future_slot = P0_EXIT + timedelta(minutes=15)
    rows = [
        _intent_row("OLD", 1, decision_slot=previous_slot),
        _intent_row("NVDA", 6),
        _intent_row("AVGO", 7),
        _intent_row(
            "FUTURE",
            1,
            occurred_at=future_slot,
            decision_at=future_slot,
            decision_slot=future_slot,
        ),
    ]
    bars = {
        "NVDA": [
            (P0_EXIT - timedelta(minutes=1), 99.0),
            (P0_EXIT + timedelta(minutes=1), 100.0),
            (P1_EXIT - timedelta(minutes=1), 104.0),
            (P1_EXIT + timedelta(minutes=1), 999.0),
        ],
        "AVGO": [
            (P0_EXIT + timedelta(minutes=1), 200.0),
            (P1_EXIT - timedelta(minutes=1), 202.0),
        ],
    }

    candidates = build_point_in_time_candidates([slot], rows, bars)["intent-1"]

    assert [candidate.symbol for candidate in candidates] == ["NVDA", "AVGO"]
    assert candidates[0].rank == 6
    assert candidates[0].investable is True
    assert candidates[0].entry_price == pytest.approx(100.0)
    assert candidates[0].exit_price == pytest.approx(104.0)


def test_collisione_s1_e_capitale_non_investibile_restano_reason_distinti():
    [slot] = build_freed_slots(
        [
            policy_outcome_from_row(_policy_row("P0")),
            policy_outcome_from_row(_policy_row("P1")),
        ],
        baseline_policy_id="P0",
        policy_id="P1",
    )
    rows = [
        _intent_row(
            "S1COLL",
            6,
            s1_state={"held_by_s1": True, "targeted": False},
        ),
        _intent_row(
            "TOOSMALL",
            7,
            is_tradable=False,
            reason_code="SKIP_MIN_NOTIONAL",
        ),
    ]
    bars = {
        symbol: [(P0_EXIT, 100.0), (P1_EXIT, 101.0)]
        for symbol in ("S1COLL", "TOOSMALL")
    }

    candidates = build_point_in_time_candidates([slot], rows, bars)["intent-1"]

    assert candidates[0].collides_with_s1 is True
    assert candidates[1].investable is False
    assert candidates[1].investable_reason == "SKIP_MIN_NOTIONAL"


def test_un_ordine_gia_inviato_non_scavalca_il_primo_candidato_non_finanziato():
    [slot] = build_freed_slots(
        [
            policy_outcome_from_row(_policy_row("P0")),
            policy_outcome_from_row(_policy_row("P1")),
        ],
        baseline_policy_id="P0",
        policy_id="P1",
    )
    rows = [
        _intent_row(
            "META",
            2,
            reason_code="SUBMITTED",
            is_tradable=True,
        ),
        _intent_row("NVDA", 6),
    ]
    bars = {
        symbol: [(P0_EXIT, 100.0), (P1_EXIT, 104.0)]
        for symbol in ("META", "NVDA")
    }

    candidates = build_point_in_time_candidates([slot], rows, bars)["intent-1"]
    [record] = build_portfolio_counterfactual(
        [slot], {"intent-1": candidates}
    )

    assert candidates[0].symbol == "META"
    assert candidates[0].investable is False
    assert candidates[0].investable_reason == "SUBMITTED"
    assert record.substitute_symbol == "NVDA"
    assert record.point_in_time_rank == 6
    assert record.rejected_candidates == (
        ("META", "CANDIDATE_CAPITAL_NOT_INVESTABLE"),
    )
