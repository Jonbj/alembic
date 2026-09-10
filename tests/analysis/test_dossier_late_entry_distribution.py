"""#512: distribuzione congiunta quota di movimento x P&L realizzato."""

from __future__ import annotations

import pytest

from src.analysis.dossier.late_entry import (
    aggregate_late_entry_distribution,
    late_entry_rows_from_dossiers,
)


def test_associa_ingresso_a_trade_id_solo_con_identita_non_ambigua():
    dossiers = [{
        "data": "2026-09-03",
        "ingressi": [
            {
                "symbol": "PLTR", "strategia": "S4", "ora_utc": "18:37",
                "quota_movimento_precedente_al_segnale": 1.055,
                "denominatore_degenere": False,
            },
            {
                "symbol": "NVDA", "strategia": "S4", "ora_utc": "18:07",
                "quota_movimento_precedente_al_segnale": 0.64,
                "denominatore_degenere": False,
            },
        ],
        "intenti_ingresso_s4": [
            {
                "symbol": "PLTR", "decision_at": "2026-09-03T18:37:00+00:00",
                "final_reason_code": "SUBMITTED", "trade_id": 980,
            },
            {
                "symbol": "NVDA", "decision_at": "2026-09-03T18:07:00+00:00",
                "final_reason_code": "SUBMITTED", "trade_id": 977,
            },
        ],
    }]

    rows = late_entry_rows_from_dossiers(dossiers)

    assert [(row["symbol"], row["trade_id"]) for row in rows] == [
        ("PLTR", 980), ("NVDA", 977)
    ]


def test_distribuzione_separa_oltre_uno_degeneri_e_pnl_mancante():
    rows = [
        {"quota": 1.055, "denominatore_degenere": False, "trade_id": 1},
        {"quota": 1.40, "denominatore_degenere": False, "trade_id": 2},
        {"quota": 0.64, "denominatore_degenere": False, "trade_id": 3},
        {"quota": 0.20, "denominatore_degenere": True, "trade_id": 4},
        {"quota": None, "denominatore_degenere": True, "trade_id": None},
    ]

    out = aggregate_late_entry_distribution(
        rows, pnl_by_trade_id={1: -4.92, 2: None, 3: 12.0, 4: -3.0}
    )

    assert out["n_ingressi"] == 5
    assert out["n_con_pnl_realizzato"] == 3
    assert out["n_senza_identita_trade"] == 1
    oltre = next(bucket for bucket in out["bucket"] if bucket["fascia"] == ">=1.0")
    assert oltre["n"] == 2
    assert oltre["n_con_pnl_realizzato"] == 1
    assert oltre["somma_pnl_realizzato"] == pytest.approx(-4.92)
    degenere = next(
        bucket for bucket in out["bucket"] if bucket["fascia"] == "DEGENERATE"
    )
    assert degenere["n"] == 2
    assert degenere["somma_pnl_realizzato"] == pytest.approx(-3.0)

