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
