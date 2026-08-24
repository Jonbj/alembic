"""#282 — validator del ledger e dei pannelli longitudinali.

Criteri di accettazione della issue: il validator controlla ID, somme,
date/finestra, duplicati, append-only, dossier hash e completeness. Ogni test
fissa UN check introducendo un difetto mirato e verificando che venga segnalato,
piu' il caso sano che passa.
"""

from __future__ import annotations

import datetime as dt
import hashlib

from src.analysis.dossier import ledger_validator as lv
from src.analysis.dossier import panels


WINDOW = (dt.date(2026, 8, 3), dt.date(2026, 9, 28))


def _findings_ok() -> dict:
    return {
        "schema_version": 1,
        "prossimo_id": 3,
        "findings": [
            {"id": "F-001", "titolo": "t1", "tipo": "osservazione",
             "confidenza": "congetturale", "primo_avvistamento": "2026-08-03",
             "occorrenze": [
                 {"data": "2026-08-03", "costo_usd": 10.0, "nota": "n", "fonte": "R"},
                 {"data": "2026-08-04", "costo_usd": 5.0, "nota": "n", "fonte": "R"},
             ],
             "costo_cumulato_usd": 15.0, "stato": "aperto", "issue": None,
             "occorrenze_non_stimate": 0},
        ],
    }


def _occ_ok(**overrides) -> dict:
    base = {
        "schema_version": panels.LEDGER_SCHEMA_VERSION,
        "causal_event_id": "miss:2026-08-04:AAPL",
        "data": "2026-08-04",
        "tickers": ["AAPL"],
        "signal_ids": [101], "trade_ids": [], "news_log_ids": [101],
        "segment": "BELOW_GATE",
        "confidenza": "congetturale",
        "actual_usd": None, "attributed_usd": None,
        "missed_usd": 100.0, "avoided_usd": None,
        "formula": "gross=...", "estimator_version": "2.0",
        "primary_finding": None, "primary": True,
        "fonte": "dossier/2026-08-04.json",
        "dossier_hash": "h-0804",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# ID
# ---------------------------------------------------------------------------

def test_validate_findings_rigetta_id_non_conforme_e_duplicato():
    f = _findings_ok()
    f["findings"][0]["id"] = "X-001"  # formato sbagliato
    res = lv.validate_findings(f, window=WINDOW)
    assert not res["ok"]
    assert any("id" in e.lower() for e in res["errors"])

    f = _findings_ok()
    f["findings"].append(dict(f["findings"][0]))  # id duplicato = riuso
    res = lv.validate_findings(f, window=WINDOW)
    assert not res["ok"]
    assert any("duplicat" in e.lower() or "rius" in e.lower() for e in res["errors"])


def test_validate_panels_rigetta_primary_finding_inesistente():
    occ = [_occ_ok(primary_finding="F-999")]
    defs = panels.build_definitions(_findings_ok())
    res = lv.validate_panels(
        {"occurrences": occ, "definitions": defs}, dossier_hashes={}, window=WINDOW)
    assert not res["ok"]
    assert any("primary_finding" in e for e in res["errors"])


def test_validate_panels_rigetta_causal_event_id_malformato():
    occ = [_occ_ok(causal_event_id="bogus:not-an-id:")]  # kind non ammesso
    res = lv.validate_panels(
        {"occurrences": occ, "definitions": []}, dossier_hashes={}, window=WINDOW)
    assert not res["ok"]
    assert any("causal_event_id" in e for e in res["errors"])


# ---------------------------------------------------------------------------
# Somme
# ---------------------------------------------------------------------------

def test_validate_findings_rigetta_costo_cumulato_incoerente():
    f = _findings_ok()
    f["findings"][0]["costo_cumulato_usd"] = 999.0  # != somma occorrenze (15.0)
    res = lv.validate_findings(f, window=WINDOW)
    assert not res["ok"]
    assert any("costo" in e.lower() or "somm" in e.lower() for e in res["errors"])


def test_validate_panels_rigetta_doppio_primary_per_stesso_ticker_day():
    # due occorrenze sullo stesso (data, ticker) che both portano primary_finding
    # = due finding che reclamano lo stesso costo => doppio conteggio vietato
    occ = [
        _occ_ok(causal_event_id="miss:2026-08-04:AAPL", primary_finding="F-001"),
        _occ_ok(causal_event_id="trade:726", primary_finding="F-002",
                actual_usd=12.5, segment="trade"),
    ]
    defs = [{"id": "F-001"}, {"id": "F-002"}]
    res = lv.validate_panels(
        {"occurrences": occ, "definitions": defs}, dossier_hashes={}, window=WINDOW)
    assert not res["ok"]
    assert any("primary" in e.lower() for e in res["errors"])


# ---------------------------------------------------------------------------
# Date / finestra
# ---------------------------------------------------------------------------

def test_validate_findings_rigetta_occorrenza_prima_di_primo_avvistamento():
    f = _findings_ok()
    f["findings"][0]["primo_avvistamento"] = "2026-08-10"
    res = lv.validate_findings(f, window=WINDOW)
    assert not res["ok"]
    assert any("avvistamento" in e.lower() or "primo" in e.lower() for e in res["errors"])


def test_validate_findings_rigetta_data_fuori_finestra():
    f = _findings_ok()
    f["findings"][0]["occorrenze"].append(
        {"data": "2026-10-01", "costo_usd": 1.0, "nota": "n", "fonte": "R"})
    res = lv.validate_findings(f, window=WINDOW)
    assert not res["ok"]
    assert any("finestra" in e.lower() or "window" in e.lower() for e in res["errors"])


def test_validate_panels_rigetta_occurrence_data_incoerente_con_id():
    occ = [_occ_ok(data="2026-08-05")]  # l'id dice 2026-08-04
    res = lv.validate_panels(
        {"occurrences": occ, "definitions": []}, dossier_hashes={}, window=WINDOW)
    assert not res["ok"]
    assert any("data" in e.lower() and "id" in e.lower() for e in res["errors"])


# ---------------------------------------------------------------------------
# Duplicati + append-only
# ---------------------------------------------------------------------------

def test_validate_panels_rigetta_causal_event_id_duplicato():
    occ = [_occ_ok(), _occ_ok()]  # stesso id due volte = doppio conteggio
    res = lv.validate_panels(
        {"occurrences": occ, "definitions": []}, dossier_hashes={}, window=WINDOW)
    assert not res["ok"]
    assert any("duplicat" in e.lower() for e in res["errors"])


def test_validate_panels_rigetta_ledger_non_ordinato_append_only():
    # riga con data precedente dopo una piu' recente = non append-only
    occ = [
        _occ_ok(data="2026-08-05", causal_event_id="miss:2026-08-05:MSFT"),
        _occ_ok(),  # 2026-08-04 dopo 2026-08-05: regressione
    ]
    res = lv.validate_panels(
        {"occurrences": occ, "definitions": []}, dossier_hashes={}, window=WINDOW)
    assert not res["ok"]
    assert any("append" in e.lower() or "ordin" in e.lower() for e in res["errors"])


# ---------------------------------------------------------------------------
# Dossier hash
# ---------------------------------------------------------------------------

def test_validate_panels_rigetta_dossier_hash_non_corrispondente():
    occ = [_occ_ok(dossier_hash="claim")]
    res = lv.validate_panels(
        {"occurrences": occ, "definitions": []},
        dossier_hashes={"2026-08-04": "actual"}, window=WINDOW)
    assert not res["ok"]
    assert any("hash" in e.lower() for e in res["errors"])


def test_validate_panels_accetta_dossier_hash_corrispondente():
    occ = [_occ_ok(dossier_hash="actual")]
    res = lv.validate_panels(
        {"occurrences": occ, "definitions": []},
        dossier_hashes={"2026-08-04": "actual"}, window=WINDOW)
    assert not any("hash" in e.lower() for e in res["errors"])


# ---------------------------------------------------------------------------
# Completeness
# ---------------------------------------------------------------------------

def test_validate_panels_segnala_giornata_dossier_senza_occorrenze():
    res = lv.validate_panels(
        {"occurrences": [], "definitions": []},
        dossier_hashes={"2026-08-04": "actual"}, window=WINDOW)
    assert not res["ok"]
    assert any("complet" in e.lower() or "copert" in e.lower() for e in res["errors"])


def test_validate_panels_segnala_ticker_day_mancante_nel_pannello():
    # il pannello ticker-day copre AAPL e MSFT, ma il dossier movers sono 3
    d = panels.build_ticker_day_panel  # placeholder, vedi sotto
    # costruito esplicitamente: pannello con un ticker, dossier con due movers
    ticker_day = [
        {"schema_version": panels.PANELS_SCHEMA_VERSION, "data": "2026-08-04",
         "ticker": "AAPL", "causal_event_id": "miss:2026-08-04:AAPL",
         "segment": "NO_NEWS", "dossier_hash": "h"}]
    movers = {"AAPL": 0.05, "MSFT": 0.06}
    res = lv.validate_panels(
        {"occurrences": [_occ_ok()], "definitions": [],
         "ticker_day": ticker_day},
        dossier_hashes={"2026-08-04": "h"}, window=WINDOW,
        dossier_movers={"2026-08-04": movers})
    assert not res["ok"]
    assert any("MSFT" in e or "mover" in e.lower() for e in res["errors"])


# ---------------------------------------------------------------------------
# caso sano
# ---------------------------------------------------------------------------

def test_validate_ledger_accetta_snapshot_sano():
    f = _findings_ok()
    defs = panels.build_definitions(f)
    occ = [_occ_ok()]
    res = lv.validate_ledger(
        findings=f, occurrences=occ, definitions=defs,
        dossier_hashes={"2026-08-04": "h-0804"}, window=WINDOW)
    assert res["ok"], res["errors"]