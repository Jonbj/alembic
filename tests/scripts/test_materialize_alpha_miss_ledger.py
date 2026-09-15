"""Materializzatore deterministico del ledger alpha-miss (#287).

L'orchestratore e' sottile: carica dossier, candidati e ledger, delega ogni
decisione ai moduli puri (prompt_contract, candidates) e scrive solo se la
validazione passa. Qui si verifica il wiring I/O e che un rifiuto lasci i
file di evidenza esattamente come li ha trovati.
"""

import json

import pytest

import scripts.materialize_alpha_miss_ledger as orch
from src.analysis.dossier.candidates import CANDIDATES_SCHEMA_VERSION
from src.analysis.dossier.prompt_contract import PROMPT_VERSION


DOSSIER = {
    "schema_version": "3.1",
    "data": "2026-09-15",
    "mercato": {"mover_3pct": 7, "up": 5, "down": 2, "dispersione_sigma": 0.021},
}

FINDINGS = {
    "schema_version": "1",
    "prossimo_id": 5,
    "findings": [
        {
            "id": "F-004",
            "titolo": "Titolo esistente",
            "tipo": "alpha_miss",
            "confidenza": "congetturale",
            "primo_avvistamento": "2026-08-01",
            "occorrenze": [],
            "costo_cumulato_usd": 0.0,
            "occorrenze_non_stimate": 0,
            "stato": "aperto",
            "issue": None,
        }
    ],
}


def _riga(data="2026-09-15"):
    return {
        "data": data,
        "spy": 0.001,
        "qqq": -0.002,
        "dispersione_sigma": 0.021,
        "mover_3pct": 7,
        "up": 5,
        "down": 2,
        "watchlist_zero_news": 40,
        "tema": "non chiaro",
        "miss": {
            "NO_NEWS": 1,
            "THIN_NEUTRAL": 0,
            "WRONG_SIGN": 0,
            "FILTERED": 0,
            "OUT_OF_STRATEGY_SCOPE": 0,
        },
        "catturati": 2,
        "book": {
            "equity": 110000.0,
            "realizzato": -12.5,
            "mtm": None,
            "s1_realizzato": -10.0,
            "s4_realizzato": -2.5,
        },
    }


def _candidato(**extra):
    candidato = {
        "finding_id": "F-004",
        "titolo": None,
        "tipo": "alpha_miss",
        "confidenza": "congetturale",
        "costo_usd": 132.0,
        "formula_costo": "2200 * 0.06",
        "nota": "ORCL mancato",
        "fonte": "ALPHA_MISS_REPORT_2026-09-15.md §7",
        "esposizione": "ORCL in watchlist, non detenuto",
        "evidenza_contraria": "nessun segnale sopra gate",
        "non_occorrenza": "mai mover nelle sedute precedenti",
        "next_evidence": "contare le sedute con news effective-timely su ORCL",
        "meccanismo": "news dopo il close",
        "alternative_scartate": ["beta settore"],
        "giustificazione_nuovo": None,
    }
    candidato.update(extra)
    return candidato


def _candidati(data="2026-09-15", findings=None, market=None, **extra):
    payload = {
        "schema_version": CANDIDATES_SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "data": data,
        "market_daily": market if market is not None else _riga(data),
        "findings": findings if findings is not None else [_candidato()],
    }
    payload.update(extra)
    return payload


@pytest.fixture()
def files(tmp_path):
    return {
        "dossier": tmp_path / "dossier.json",
        "candidates": tmp_path / "candidates.json",
        "findings": tmp_path / "findings.json",
        "market": tmp_path / "market_daily.jsonl",
    }


def _prepara(files, *, candidati=None, findings=None, dossier=None, righe=None):
    files["dossier"].write_text(json.dumps(dossier if dossier is not None else DOSSIER))
    files["candidates"].write_text(
        json.dumps(candidati if candidati is not None else _candidati())
    )
    files["findings"].write_text(json.dumps(findings if findings is not None else FINDINGS))
    files["market"].write_text(
        "".join(json.dumps(r) + "\n" for r in (righe if righe is not None else []))
    )


def _argv(files, extra=()):
    return [
        "--dossier", str(files["dossier"]),
        "--candidates", str(files["candidates"]),
        "--findings", str(files["findings"]),
        "--market-daily", str(files["market"]),
        *extra,
    ]


def test_materializza_ledger_valido(tmp_path, capsys, files):
    _prepara(files)

    codice = orch.main(_argv(files))

    assert codice == 0
    righe = [json.loads(l) for l in files["market"].read_text().splitlines() if l.strip()]
    assert [r["data"] for r in righe] == ["2026-09-15"]
    findings = json.loads(files["findings"].read_text())
    assert findings["findings"][0]["occorrenze"][0]["costo_usd"] == 132.0
    assert findings["findings"][0]["costo_cumulato_usd"] == 132.0
    out = capsys.readouterr().out
    assert "LEDGER_STATUS=materializzato" in out


def test_candidati_invalidi_lasciano_i_file_inalterati(capsys, files):
    _prepara(files, candidati=_candidati(prompt_version="altro"))
    prima_findings = files["findings"].read_text()
    prima_market = files["market"].read_text()

    codice = orch.main(_argv(files))

    assert codice == 1
    assert files["findings"].read_text() == prima_findings
    assert files["market"].read_text() == prima_market
    out = capsys.readouterr().out
    assert "LEDGER_STATUS=rifiutato" in out
    assert "prompt_version" in out


def test_dossier_incompatibile_rifiuta_prima_di_toccare_i_file(capsys, files):
    _prepara(files, dossier={**DOSSIER, "schema_version": "9.9"})
    prima_findings = files["findings"].read_text()

    codice = orch.main(_argv(files))

    assert codice == 1
    assert files["findings"].read_text() == prima_findings
    assert "LEDGER_STATUS=rifiutato" in capsys.readouterr().out


def test_candidati_con_data_diversa_dal_dossier_vengono_rifiutati(capsys, files):
    _prepara(files, candidati=_candidati(data="2026-09-14"))

    codice = orch.main(_argv(files))

    assert codice == 1
    assert "LEDGER_STATUS=rifiutato" in capsys.readouterr().out


def test_giorno_gia_materializzato_e_idempotente(capsys, files):
    _prepara(files, righe=[_riga()])
    findings_aggiornati = json.loads(json.dumps(FINDINGS))
    findings_aggiornati["findings"][0]["occorrenze"] = [
        {"data": "2026-09-15", "costo_usd": 132.0, "nota": "ORCL mancato", "fonte": "x"}
    ]
    files["findings"].write_text(json.dumps(findings_aggiornati))

    codice = orch.main(_argv(files))

    assert codice == 0
    out = capsys.readouterr().out
    assert "LEDGER_STATUS=nessuna_modifica" in out
    righe = [json.loads(l) for l in files["market"].read_text().splitlines() if l.strip()]
    assert len(righe) == 1


def test_il_jsonl_scritto_resta_valida_e_le_righe_vecchie_restano_tali(files, capsys):
    vecchia = _riga(data="2026-09-12")
    _prepara(files, righe=[vecchia])

    codice = orch.main(_argv(files))

    assert codice == 0
    righe = [json.loads(l) for l in files["market"].read_text().splitlines() if l.strip()]
    assert [r["data"] for r in righe] == ["2026-09-12", "2026-09-15"]
    assert righe[0] == vecchia


def test_solo_digest_rende_cinque_righe_dal_ledger_materializzato(capsys, files):
    _prepara(files)
    economico = files["dossier"].parent / "economic_pnl.json"
    economico.write_text(json.dumps({
        "scoreboard": {
            "giorno": {"n": 27, "denominatore": 40},
            "s4_vs_200": {"cumulato": 123.4, "soglia": 200.0, "within": True},
        }
    }))
    orch.main(_argv(files))  # materializza
    capsys.readouterr()

    codice = orch.main([
        "--solo-digest",
        "--data", "2026-09-15",
        "--dossier", str(files["dossier"]),
        "--findings", str(files["findings"]),
        "--market-daily", str(files["market"]),
        "--economic-pnl", str(economico),
    ])

    assert codice == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "🔎 Alpha-miss 2026-09-15: 7 mover (5↑ 2↓), dispersione σ 2.1%"
    assert len([l for l in out if l.strip()]) == 5


def test_solo_digest_con_riga_assente_dichiara_data_incomplete(capsys, files):
    _prepara(files)
    codice = orch.main([
        "--solo-digest",
        "--data", "2026-09-15",
        "--dossier", str(files["dossier"]),
        "--findings", str(files["findings"]),
        "--market-daily", str(files["market"]),
    ])

    assert codice == 0
    out = capsys.readouterr().out
    assert "DATA_INCOMPLETE" in out