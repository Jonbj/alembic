"""Backfill chirurgico dei dossier storici per #430."""

from scripts.backfill_hold_minimum_expiry_dossiers import backfill_payload


def test_backfill_aggiunge_solo_marker_istogramma_e_provenienza():
    payload = {
        "schema_version": "2.0",
        "data": "2026-08-18",
        "generato_il": "2026-08-22T06:30:16+00:00",
        "provenienza_dati": {"daily": {"feed": "SIP"}},
        "chiusure": [
            {
                "symbol": "HD",
                "strategia": "S4",
                "pnl_net": 2.686738,
                "exit_reason": "portfolio_sell",
                "ore_tenuta": 1.750004,
                "drift_post_uscita": -12.766095,
            },
            {
                "symbol": "GE",
                "strategia": "S1",
                "pnl_net": 10.0,
                "exit_reason": "portfolio_sell",
                "ore_tenuta": 24.0,
                "drift_post_uscita": None,
            },
        ],
        "aggregati": {"campo_precedente": 7},
    }

    result = backfill_payload(payload)

    assert result["schema_version"] == "2.0"
    assert result["generato_il"] == "2026-08-22T06:30:16+00:00"
    assert result["provenienza_dati"]["daily"] == {"feed": "SIP"}
    assert result["aggregati"]["campo_precedente"] == 7
    assert result["chiusure"][0]["exit_reason"] == "hold_minimum_expiry"
    assert result["chiusure"][1]["exit_reason"] == "portfolio_sell"
    assert result["aggregati"]["ore_tenuta_s4"]["buckets"][0] == {
        "durata_minuti": 105,
        "n": 1,
        "pnl_net": 2.686738,
        "drift_post_uscita": -12.766095,
    }
    assert "ore_tenuta_s4" in result["provenienza_dati"]
