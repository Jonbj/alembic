"""#298: il comando operativo pubblica le due viste riconciliate."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest

import scripts.report_s4_replacement as report_script

P0_EXIT = datetime(2026, 8, 25, 17, 52, tzinfo=UTC)
P1_EXIT = datetime(2026, 8, 27, 19, 59, tzinfo=UTC)


def _policy_rows() -> list[dict]:
    common = {
        "intent_id": "intent-1",
        "symbol": "AMD",
        "d0": date(2026, 8, 25),
        "initial_notional": 1000.0,
        "status": "CLOSED",
        "virtual_exit_quantity": 10.0,
        "comparable": True,
        "details": {"entry_fill_id": "fill-1"},
    }
    return [
        {
            **common,
            "policy_id": "P0",
            "reason_code": "P0_TARGET_ZERO_EXPIRED",
            "trigger_at": P0_EXIT,
            "filled_at": P0_EXIT,
            "net_pnl": 10.0,
        },
        {
            **common,
            "policy_id": "P1",
            "reason_code": "P1_TIME_DUE",
            "trigger_at": P1_EXIT,
            "filled_at": P1_EXIT,
            "net_pnl": 35.0,
        },
    ]


def test_cli_stampa_report_e_dettaglio_sostituto(monkeypatch, capsys):
    monkeypatch.setattr(report_script, "_fetch_policy_rows", lambda start, end: _policy_rows())
    monkeypatch.setattr(
        report_script,
        "_fetch_intent_rows",
        lambda until: [
            {
                "intent_id": "candidate-nvda",
                "symbol": "NVDA",
                "signal_id": 5001,
                "rank": 6,
                "occurred_at": P0_EXIT - timedelta(seconds=1),
                "decision_slot": P0_EXIT,
                "decision_at": P0_EXIT - timedelta(seconds=1),
                "is_tradable": False,
                "reason_code": "RANK_OUTSIDE_TOP_N",
                "s1_state": {},
                "anti_pyramiding": False,
            }
        ],
    )
    monkeypatch.setattr(
        report_script,
        "_fetch_candidate_bars",
        lambda symbols, start, end: {
            "NVDA": [(P0_EXIT, 100.0), (P1_EXIT, 104.0)]
        },
    )
    monkeypatch.setattr(
        report_script,
        "_fetch_session_dates",
        lambda start, end: [date(2026, 8, day) for day in (25, 26, 27)],
    )
    monkeypatch.setattr(report_script, "VersionedTradeCostModel", lambda: None)

    exit_code = report_script.main(["--start", "2026-08-25", "--end", "2026-08-27"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["paired"]["comparable"] == 1
    assert payload["paired_records"][0]["intent_id"] == "intent-1"
    assert payload["paired_records"][0]["initial_notional"] == 1000.0
    assert payload["paired_records"][0]["exclusion_reasons"] == []
    assert payload["slots"]["substitutes_selected"] == 1
    assert payload["replacement_records"][0]["substitute_symbol"] == "NVDA"
    assert payload["replacement_records"][0]["point_in_time_rank"] == 6
    assert payload["reconciliation"]["reconciled"] is True


def test_cli_distingue_una_finestra_senza_esiti(monkeypatch, capsys):
    monkeypatch.setattr(report_script, "_fetch_policy_rows", lambda start, end: [])

    exit_code = report_script.main(["--start", "2026-08-25", "--end", "2026-08-27"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["paired"]["total"] == 0


def _holding_rows() -> list[dict]:
    """P0 chiusa, P1 ancora aperta: la coppia esiste ma non e' misurabile."""
    common = {
        "intent_id": "intent-1",
        "symbol": "AMD",
        "d0": date(2026, 8, 25),
        "initial_notional": 1000.0,
        "virtual_exit_quantity": 10.0,
        "comparable": True,
        "details": {"entry_fill_id": "fill-1"},
    }
    return [
        {
            **common,
            "policy_id": "P0",
            "status": "CLOSED",
            "reason_code": "P0_TARGET_ZERO_EXPIRED",
            "trigger_at": P0_EXIT,
            "filled_at": P0_EXIT,
            "net_pnl": 10.0,
        },
        {
            **common,
            "policy_id": "P1",
            "status": "OPEN",
            "reason_code": "P1_HOLDING",
            "trigger_at": P0_EXIT,
            "filled_at": None,
            "net_pnl": None,
        },
    ]


def test_una_finestra_senza_coppie_comparabili_non_e_un_successo(monkeypatch, capsys):
    """Riconciliare zero con zero riesce sempre: non e' una misura.

    Lo stato precedente ritornava 0 con `comparable: 0` e `mean_delta_bps:
    null`, perche' guardava `total` invece di `comparable`. Un cron che usa
    l'exit code come gate avrebbe letto "finestra a posto" proprio quando la
    metrica primaria non esiste.
    """
    monkeypatch.setattr(
        report_script, "_fetch_policy_rows", lambda start, end: _holding_rows()
    )
    monkeypatch.setattr(report_script, "_fetch_intent_rows", lambda until: [])
    monkeypatch.setattr(report_script, "_fetch_candidate_bars", lambda *a, **k: {})
    monkeypatch.setattr(
        report_script,
        "_fetch_session_dates",
        lambda start, end: [date(2026, 8, d) for d in (25, 26, 27)],
    )

    exit_code = report_script.main(["--start", "2026-08-25", "--end", "2026-08-27"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["paired"]["total"] == 1
    assert payload["paired"]["comparable"] == 0
    assert payload["paired"]["mean_delta_bps"] is None
    assert payload["reconciliation"]["reconciled"] is True
    assert exit_code == 2


def test_un_intento_ancora_aperto_non_e_un_uscita_non_classificata():
    """`unclassified` e' per un'uscita che non sappiamo leggere, non per una che manca."""
    from src.strategies.s4.counterfactual import (
        EXIT_FAMILY_OPEN,
        EXIT_FAMILY_UNCLASSIFIED,
        classify_exit_reason,
    )

    assert classify_exit_reason("P1_HOLDING") == EXIT_FAMILY_OPEN
    assert classify_exit_reason("P0_RUNTIME_OPEN") == EXIT_FAMILY_OPEN
    assert classify_exit_reason("QUALCOSA_DI_IGNOTO") == EXIT_FAMILY_UNCLASSIFIED


def test_il_report_pubblica_il_verdetto_del_valutatore(monkeypatch, capsys):
    """Le due viste e il verdetto leggono le stesse coppie, non due sorgenti."""
    monkeypatch.setattr(
        report_script, "_fetch_policy_rows", lambda start, end: _policy_rows()
    )
    monkeypatch.setattr(report_script, "_fetch_intent_rows", lambda until: [])
    monkeypatch.setattr(report_script, "_fetch_candidate_bars", lambda *a, **k: {})
    monkeypatch.setattr(
        report_script,
        "_fetch_session_dates",
        lambda start, end: [date(2026, 8, d) for d in (25, 26, 27)],
    )

    report_script.main(["--start", "2026-08-25", "--end", "2026-08-27"])

    payload = json.loads(capsys.readouterr().out)
    evaluation = payload["evaluation"]
    assert evaluation["observations"] == payload["paired"]["comparable"]
    assert evaluation["cluster_unit"] == "d0_session"
    # `N_cluster` e' ancora null nel contratto: nessun verdetto e' dovuto
    assert evaluation["decision_due"] is False
    assert "N_cluster_not_derived" in evaluation["steps"][0]["notes"]
    assert evaluation["promoted_policy_id"] is None


def test_il_dettaglio_replacement_usa_la_stessa_coorte_d0_del_riepilogo(
    monkeypatch, capsys
):
    rows = _policy_rows()
    for row in _policy_rows():
        rows.append({**row, "intent_id": "intent-senza-d0", "d0": None})

    monkeypatch.setattr(report_script, "_fetch_policy_rows", lambda start, end: rows)
    monkeypatch.setattr(report_script, "_fetch_intent_rows", lambda until: [])
    monkeypatch.setattr(report_script, "_fetch_candidate_bars", lambda *a, **k: {})
    monkeypatch.setattr(
        report_script,
        "_fetch_session_dates",
        lambda start, end: [date(2026, 8, d) for d in (25, 26, 27)],
    )

    exit_code = report_script.main(["--start", "2026-08-25", "--end", "2026-08-27"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["paired"]["total"] == 1
    assert payload["slots"]["total"] == 1
    assert [row["intent_id"] for row in payload["replacement_records"]] == [
        "intent-1"
    ]


def test_anche_una_finestra_vuota_espone_il_blocco_di_valutazione(monkeypatch, capsys):
    """Una chiave che appare solo a volte costringe il consumatore a indovinare."""
    monkeypatch.setattr(report_script, "_fetch_policy_rows", lambda start, end: [])

    exit_code = report_script.main(["--start", "2026-08-25", "--end", "2026-08-27"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["evaluation"]["observations"] == 0
    assert "no_comparable_pairs" in payload["evaluation"]["steps"][0]["notes"]


def test_una_finestra_di_sole_attese_dichiara_gli_slot_non_ancora_misurati(
    monkeypatch, capsys
):
    """`slots.total: 0` da solo si legge come "nessun opportunity cost".

    Con la P1 che tiene fino a D+2, ogni intento ancora aperto spariva dal
    blocco portfolio-level: il report pubblicava zero slot, zero capitale
    inattivo e `reconciled: true` su una coorte in cui nessuno slot era
    determinato. Il buco ora e' nominato e conta quanto le coppie pubblicate.
    """
    monkeypatch.setattr(
        report_script, "_fetch_policy_rows", lambda start, end: _holding_rows()
    )
    monkeypatch.setattr(report_script, "_fetch_intent_rows", lambda until: [])
    monkeypatch.setattr(report_script, "_fetch_candidate_bars", lambda *a, **k: {})
    monkeypatch.setattr(
        report_script,
        "_fetch_session_dates",
        lambda start, end: [date(2026, 8, d) for d in (25, 26, 27)],
    )

    report_script.main(["--start", "2026-08-25", "--end", "2026-08-27"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["slots"]["total"] == 0
    assert payload["slots"]["without_slot"] == 1
    assert payload["slots"]["without_slot_by_reason"] == {
        "SLOT_CHALLENGER_STILL_OPEN": 1
    }
    assert payload["slots"]["without_slot"] == payload["paired"]["total"]


def _overlapping_rows() -> list[dict]:
    """Due intenti liberati dalla stessa policy mentre il primo slot e' aperto."""
    common = {
        "d0": date(2026, 8, 25),
        "initial_notional": 1000.0,
        "status": "CLOSED",
        "virtual_exit_quantity": 10.0,
        "comparable": True,
    }
    rows: list[dict] = []
    for index, (intent_id, symbol, freed_at) in enumerate(
        (
            ("intent-1", "AMD", P0_EXIT),
            ("intent-2", "MSFT", P0_EXIT + timedelta(hours=1)),
        )
    ):
        rows.append(
            {
                **common,
                "intent_id": intent_id,
                "symbol": symbol,
                "details": {"entry_fill_id": f"fill-{index}"},
                "policy_id": "P0",
                "reason_code": "P0_TARGET_ZERO_EXPIRED",
                "trigger_at": freed_at,
                "filled_at": freed_at,
                "net_pnl": 10.0,
            }
        )
        rows.append(
            {
                **common,
                "intent_id": intent_id,
                "symbol": symbol,
                "details": {"entry_fill_id": f"fill-{index}"},
                "policy_id": "P1",
                "reason_code": "P1_TIME_DUE",
                "trigger_at": P1_EXIT,
                "filled_at": P1_EXIT,
                "net_pnl": 35.0,
            }
        )
    return rows


def test_lo_stesso_sostituto_non_viene_accreditato_a_due_slot(monkeypatch, capsys):
    """Il replacement non puo' valere piu' del capitale davvero libero.

    Due slot sovrapposti leggono lo stesso universo point-in-time: senza
    esclusiva il primo candidato veniva comprato due volte e il P&L
    incrementale pubblicato dal report valeva il doppio.
    """
    monkeypatch.setattr(
        report_script, "_fetch_policy_rows", lambda start, end: _overlapping_rows()
    )
    monkeypatch.setattr(
        report_script,
        "_fetch_intent_rows",
        lambda until: [
            {
                "intent_id": "candidate-nvda",
                "symbol": "NVDA",
                "signal_id": 5001,
                "rank": 6,
                "occurred_at": P0_EXIT - timedelta(seconds=1),
                "decision_slot": P0_EXIT,
                "decision_at": P0_EXIT - timedelta(seconds=1),
                "is_tradable": False,
                "reason_code": "RANK_OUTSIDE_TOP_N",
                "s1_state": {},
                "anti_pyramiding": False,
            }
        ],
    )
    monkeypatch.setattr(
        report_script,
        "_fetch_candidate_bars",
        lambda symbols, start, end: {
            "NVDA": [
                (P0_EXIT, 100.0),
                (P0_EXIT + timedelta(hours=1), 100.0),
                (P1_EXIT, 104.0),
            ]
        },
    )
    monkeypatch.setattr(
        report_script,
        "_fetch_session_dates",
        lambda start, end: [date(2026, 8, day) for day in (25, 26, 27)],
    )
    monkeypatch.setattr(report_script, "VersionedTradeCostModel", lambda: None)

    report_script.main(["--start", "2026-08-25", "--end", "2026-08-27"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["slots"]["total"] == 2
    assert payload["slots"]["substitutes_selected"] == 1
    # +4% su un solo slot da 1000 USD, non su due
    assert payload["slots"]["incremental_pnl_usd"] == pytest.approx(-40.0)
    occupato = [
        row
        for row in payload["replacement_records"]
        if row["substitute_symbol"] is None
    ]
    assert ["NVDA", "CANDIDATE_SUBSTITUTE_ALREADY_HELD"] in occupato[0][
        "rejected_candidates"
    ]


def test_il_verdetto_legge_la_stessa_coorte_d0_del_riepilogo(monkeypatch, capsys):
    """L'ultimo blocco che leggeva le coppie intere invece della coorte.

    Il valutatore riceveva `comparison.pairs`, non le coppie pubblicate dalla
    finestra: oggi coincidono solo perche' la SQL filtra sullo stesso D0, ma il
    verdetto e' l'unico blocco che diventa una decisione, quindi non puo'
    dipendere da un filtro che vive in un'altra funzione.
    """
    rows = _policy_rows()
    for row in _policy_rows():
        rows.append(
            {**row, "intent_id": "intent-coorte-precedente", "d0": date(2026, 8, 21)}
        )

    monkeypatch.setattr(report_script, "_fetch_policy_rows", lambda start, end: rows)
    monkeypatch.setattr(report_script, "_fetch_intent_rows", lambda until: [])
    monkeypatch.setattr(report_script, "_fetch_candidate_bars", lambda *a, **k: {})
    monkeypatch.setattr(
        report_script,
        "_fetch_session_dates",
        lambda start, end: [date(2026, 8, d) for d in (21, 24, 25, 26, 27)],
    )

    report_script.main(["--start", "2026-08-25", "--end", "2026-08-27"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["paired"]["comparable"] == 1
    assert payload["evaluation"]["observations"] == 1
    assert payload["evaluation"]["clusters_observed"] == 1
