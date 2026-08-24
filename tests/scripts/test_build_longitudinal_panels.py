"""#282 — test end-to-end dell'orchestratore ``build_longitudinal_panels``.

Esercita ``costruisci()`` sui dossier reali tracciati in ``docs/evidence/dossier``
(senza DB: i dossier sono JSON versionati commit). Verifica che i pannelli
longitudinali siano coerenti e che il validator li accetti sui dati di
osservazione reali, non solo sui fixture sintetici delle unit test.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def report():
    # L'orchestratore risolve i percorsi da PROJECT_DIR di scripts/; lo si
    # carica come modulo dai scripts (sul pythonpath di pytest).
    if str(PROJECT_DIR / "scripts") not in sys.path:
        sys.path.insert(0, str(PROJECT_DIR / "scripts"))
    mod = importlib.import_module("build_longitudinal_panels")
    return mod.costruisci()


def test_costruisci_valida_ok_sui_dossier_reali(report):
    assert report["validation"]["ok"], report["validation"]["errors"]


def test_il_ledger_ha_causal_event_id_univoci(report):
    ids = [o["causal_event_id"] for o in report["occurrences"]]
    assert len(ids) == len(set(ids)), "causal_event_id duplicato nel ledger reale"


def test_il_pannello_ticker_day_copre_ogni_giorno(report):
    # ogni giorno con dossier ha almeno un ticker-day row (nessun giorno
    # droppato dal pannello longitudinale).
    from collections import defaultdict

    by_day = defaultdict(set)
    for row in report["ticker_day"]:
        by_day[row["data"]].add(row["ticker"])
    assert report["n_giorni"] >= 1
    assert all(by_day[d] for d in report["giorni"])


def test_le_definitions_non_portano_occorrenze(report):
    for d in report["definitions"]:
        assert "occorrenze" not in d, "la vista definitions deve separare le occorrenze"
        assert "id" in d and "stato" in d


def test_ogni_occorrenza_di_trade_ha_un_id_univoco_e_actual_usd_misurato(report):
    trades = [o for o in report["occurrences"] if o["segment"] == "trade"]
    # i trade sono il verdetto definitivo (uscita): actual_usd e' il pnl_net
    for o in trades:
        assert o["confidenza"] == "misurata"
        assert o["actual_usd"] is not None
    # gli id dei trade sono univoci (include gli exit:...:idx ambigui)
    ids = [o["causal_event_id"] for o in trades]
    assert len(ids) == len(set(ids))


def test_la_provenienza_dichiara_primary_finding_non_attribuito(report):
    # costruito senza --write: la funzione restituisce il report, non scrive.
    assert "primary_finding resta null" in report["provenance"]["note"]


def test_decision_quality_e_una_serie_giornaliera_con_rollup(report):
    assert len(report["decision_quality"]) == report["n_giorni"]
    assert report["decision_quality_rollup"]["n_giorni"] == report["n_giorni"]
    # I dossier storici non vengono riscritti: il buco dello snapshot apertura
    # resta esplicito invece di diventare passivo=0.
    legacy = next(
        row
        for row in report["decision_quality"]
        if "opening_snapshot_not_available_in_legacy_dossier" in row["missingness"]
    )
    assert legacy["summary"]["passive_pnl_usd"] is None
    if report["decision_quality_rollup"]["n_giorni_snapshot_apertura_mancante"] == report[
        "n_giorni"
    ]:
        assert report["decision_quality_rollup"]["totali_usd"]["passive_pnl_usd"] is None


# ---------------------------------------------------------------------------
# #286 — falsificabilita' e sintesi cablate nell'orchestratore.
# ---------------------------------------------------------------------------


def test_il_report_ha_le_sezioni_di_falsificabilita(report):
    f = report["falsifiability"]
    for k in ("views", "contamination_summary", "status_events", "validation",
              "synthesis", "weekly_rollup", "annotations_used", "provenance"):
        assert k in f, f"manca falsifiability.{k}"


def test_le_viste_di_falsificabilita_arricchiscono_ogni_finding(report):
    fs = report["falsifiability"]["views"]["findings"]
    assert fs, "nessun finding nelle viste di falsificabilita'"
    for f in fs:
        # campi misurati (carta):
        assert "giorni_distinti" in f
        assert "costo_cumulato_in_finestra_usd" in f
        assert "dimensione" in f
        assert "oltre_soglia" in f
        # campi di giudizio (default null / not_exposed):
        assert f["stato_falsificazione"] == "not_exposed"
        assert f["prova_decisiva"] is None
        # esposizione null finche' non c'e' relazione_finding_causa:
        assert "giorni_esposti" in f


def test_il_31_luglio_non_conta_verso_i_giorni_distinti(report):
    # AC1: il 31/07 e' escluso. F-001 ha un'occorrenza 2026-07-31 nei dati reali:
    # non deve gonfiare giorni_distinti ne' costo.
    import json
    fj = json.load(open(PROJECT_DIR / "docs" / "evidence" / "findings.json"))
    f001 = next(x for x in fj["findings"] if x["id"] == "F-001")
    has_31 = any(o.get("data") == "2026-07-31" for o in f001["occorrenze"])
    assert has_31, "premessa: F-001 ha un'occorrenza 2026-07-31 nei dati reali"
    view = next(
        f for f in report["falsifiability"]["views"]["findings"] if f["id"] == "F-001"
    )
    # ricalcola i giorni distinti senza il 31/07: la vista non lo conta.
    giorni_senza_31 = {
        o["data"] for o in f001["occorrenze"]
        if o.get("data") != "2026-07-31"
    }
    assert view["giorni_distinti"] == len(giorni_senza_31)


def test_la_synthesis_ha_le_quattro_sezioni(report):
    syn = report["falsifiability"]["synthesis"]
    for k in ("cambi", "soglie", "pnl_economico", "integrita"):
        assert k in syn, f"manca synthesis.{k}"
    assert syn["scope"]["tipo"] == "synthesis"


def test_il_weekly_rollup_copre_ogni_settimana_con_dossier(report):
    weekly = report["falsifiability"]["weekly_rollup"]
    assert weekly, "nessun weekly rollup prodotto"
    for label, roll in weekly.items():
        assert roll["scope"]["tipo"] == "weekly"
        assert roll["scope"]["settimana"] == label
        for k in ("cambi", "soglie", "pnl_economico", "integrita"):
            assert k in roll


def test_la_validazione_di_falsificabilita_passa_sui_dati_reali(report):
    vf = report["falsifiability"]["validation"]
    assert vf["ok"], vf["errors"]


def test_la_provenanza_dichiara_findings_json_non_modificato(report):
    note = report["falsifiability"]["provenance"]["note"]
    assert "findings.json" in note and "non" in note.lower() or "read-only" in note


def test_la_synthesis_diffa_contro_la_run_precedente(report):
    # #286: il synthesis calcola i cambi contro la run precedente iniettata.
    # Due run sugli stessi dati non producono cambi (nulla e' mutato); la prima
    # run senza precedente li produce tutti come nuovi. Questo fissa che il
    # previous e' letto dalla posizione giusta (views.findings, non il blocco
    # falsifiability intero).
    import importlib
    mod = importlib.import_module("build_longitudinal_panels")
    # seconda run con la prima come precedente: nessun cambiamento atteso.
    r2 = mod.costruisci(previous_report=report)
    cambi = r2["falsifiability"]["synthesis"]["cambi"]
    assert cambi == [], (
        "la seconda run sugli stessi dati non deve produrre cambi; trovati: "
        f"{cambi[:3]}"
    )
