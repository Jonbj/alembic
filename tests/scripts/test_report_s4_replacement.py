"""#298: il comando operativo pubblica le due viste riconciliate."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

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
