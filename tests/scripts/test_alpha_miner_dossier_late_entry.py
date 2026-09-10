"""#512: wiring della distribuzione late-entry sulla finestra dossier."""

from __future__ import annotations

import json
from unittest.mock import patch

import scripts.alpha_miner_dossier as dossier


def test_finestra_rilegge_dossier_e_pnl_realizzato_per_trade_id(tmp_path):
    historical = {
        "data": "2026-09-02",
        "ingressi": [{
            "symbol": "NVDA", "strategia": "S4", "ora_utc": "18:07",
            "quota_movimento_precedente_al_segnale": 0.64,
            "denominatore_degenere": False,
        }],
        "intenti_ingresso_s4": [{
            "symbol": "NVDA", "decision_at": "2026-09-02T18:07:00+00:00",
            "trade_id": 977,
        }],
    }
    (tmp_path / "2026-09-02.json").write_text(json.dumps(historical))
    current_entries = [{
        "symbol": "PLTR", "strategia": "S4", "ora_utc": "18:37",
        "trade_id": 980,
        "quota_movimento_precedente_al_segnale": 1.055,
        "denominatore_degenere": False,
    }]

    with (
        patch.object(dossier, "OUT_DIR", tmp_path),
        patch.object(
            dossier,
            "_psql",
            return_value=[["977", "12.0"], ["980", "-4.92"]],
        ) as psql,
    ):
        out = dossier._distribuzione_late_entry_finestra(
            current_entries, [], dossier.date(2026, 9, 3)
        )

    assert out["dal"] == "2026-08-14"
    assert out["al"] == "2026-09-03"
    assert out["n_giorni_coperti"] == 2
    assert out["n_ingressi"] == 2
    assert out["n_con_pnl_realizzato"] == 2
    assert "977,980" in psql.call_args.args[0]
    oltre = next(bucket for bucket in out["bucket"] if bucket["fascia"] == ">=1.0")
    assert oltre["somma_pnl_realizzato"] == -4.92

