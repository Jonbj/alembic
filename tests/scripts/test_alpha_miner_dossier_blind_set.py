"""Wiring del blind set nel dossier, senza riscrivere le sedute storiche (#511)."""

import json

import scripts.alpha_miner_dossier as dossier


def _coverage(raw: int, effective: int) -> dict:
    return {
        "per_ticker": {
            "ASML": {
                "articoli_unici": raw,
                "effective_timely_articles": effective,
            }
        }
    }


def test_blind_set_legge_i_dossier_precedenti_senza_modificarli(tmp_path):
    (tmp_path / "2026-09-01.json").write_text(
        json.dumps({"copertura_articoli": _coverage(0, 0)})
    )
    (tmp_path / "2026-09-02.json").write_text(
        json.dumps({"copertura_articoli": _coverage(0, 0)})
    )

    out = dossier._blind_set_copertura_articoli(
        _coverage(0, 0),
        giorno=dossier.date(2026, 9, 3),
        simboli=["ASML"],
        sedute=["2026-09-01", "2026-09-02", "2026-09-03"],
        dossier_dir=tmp_path,
    )

    row = out["per_ticker"]["ASML"]
    assert row["sedute_consecutive_zero_articoli"] == 3
    assert row["zero_articoli_streak_troncato_da"] == "finestra"
    assert (tmp_path / "2026-09-01.json").read_text() == json.dumps(
        {"copertura_articoli": _coverage(0, 0)}
    )