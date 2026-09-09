"""Backfill della provenienza nei dossier storici (#244) con riconciliazione #509.

Il backfill riclassifica con la serie legacy e ora riapplica anche la
riconciliazione col funnel_v2 persistito nel dossier: e' deterministico sul
dato gia' scritto, non interroga il DB per il verdetto (la riga funnel c'e'
gia') ed e' idempotente — rieseguirlo non degrada ne' `causa` ne'
`causa_legacy`.
"""

import json

import pytest

import scripts.backfill_provenienza_dossier as backfill


def _dossier_con_funnel() -> dict:
    """Dossier minimale: un candidato NON_CLASSIFICATO con verdetto funnel
    (TSLA 2026-09-03) e il blocco funnel_v2 persistito."""
    return {
        "schema_version": "2.1",
        "data": "2026-09-03",
        "soglia_gate_usata": 0.30,
        "candidati_miss": [
            {
                "symbol": "TSLA",
                "return": 0.0542,
                "news_count": 7,
                "in_portafoglio": False,
                "causa": "NON_CLASSIFICATO",
                "segnali": [
                    {"ora": "19:45", "score": 0.468, "fallback": True,
                     "extraction_method": "source_metadata",
                     "n_ticker_articolo": 1},
                ],
            },
        ],
        "funnel_v2": {
            "funnel_version": "1.0",
            "righe": [
                {
                    "symbol": "TSLA", "rendimento": 0.0542, "held": False,
                    "actionability": "ENTRY_OPPORTUNITY",
                    "pipeline": "FALLBACK_REJECT",
                    "pipeline_escluso_motivo": None,
                    "evidence": {"score_firmato": 0.468,
                                 "n_qualificanti_fallback": 1},
                    "legacy_causa": "NON_CLASSIFICATO",
                    "net_profitable": None, "net_opportunity_usd": -35.29,
                },
            ],
        },
        "aggregati": {
            "cause_del_giorno": {
                "totale_candidati": 1,
                "conteggi": {"NON_CLASSIFICATO": 1},
                "dominante": None,
                "soglie": {"thin": 0.05, "gate": 0.30},
                "quota_righe_fanout": 0.0,
            },
        },
    }


@pytest.fixture
def senza_provenienza_db(monkeypatch):
    """Nessuna riga arricchita dal DB: il backfill provenienza e' gia' stato
    fatto, la riconciliazione deve comunque girare sul dato persistito."""
    monkeypatch.setattr(backfill, "provenienza_del_giorno", lambda g: {})


def test_backfill_riapplica_la_riconciliazione_dal_funnel_persistito(
    tmp_path, senza_provenienza_db
):
    percorso = tmp_path / "2026-09-03.json"
    percorso.write_text(json.dumps(_dossier_con_funnel()))

    backfill.backfill_file(percorso, dry_run=False)
    dossier = json.loads(percorso.read_text())

    cand = dossier["candidati_miss"][0]
    assert cand["causa"] == "FALLBACK_REJECT"
    assert cand["causa_legacy"] == "NON_CLASSIFICATO"
    # la serie pre-registrata resta legacy (#288 Opzione 1)
    assert dossier["aggregati"]["cause_del_giorno"]["conteggi"] == {
        "NON_CLASSIFICATO": 1
    }


def test_backfill_riconciliazione_idempotente(tmp_path, senza_provenienza_db):
    """Rieseguire il backfill non degrada i campi della riconciliazione."""
    percorso = tmp_path / "2026-09-03.json"
    percorso.write_text(json.dumps(_dossier_con_funnel()))

    backfill.backfill_file(percorso, dry_run=False)
    backfill.backfill_file(percorso, dry_run=False)
    dossier = json.loads(percorso.read_text())

    cand = dossier["candidati_miss"][0]
    assert cand["causa"] == "FALLBACK_REJECT"
    assert cand["causa_legacy"] == "NON_CLASSIFICATO"


def test_backfill_senza_funnel_non_tocca_la_causa(tmp_path, senza_provenienza_db):
    """Dossier pre-#281 (PLTR 2026-09-02): nessun verdetto da promuovere, la
    causa resta il sentinel legacy e non nasce un causa_legacy fittizio."""
    dossier = _dossier_con_funnel()
    dossier["data"] = "2026-09-02"
    del dossier["funnel_v2"]
    percorso = tmp_path / "2026-09-02.json"
    percorso.write_text(json.dumps(dossier))

    risultato = backfill.backfill_file(percorso, dry_run=False)

    assert risultato["cambi_causa"] == {}
    cand = json.loads(percorso.read_text())["candidati_miss"][0]
    assert cand["causa"] == "NON_CLASSIFICATO"
    assert "causa_legacy" not in cand


def test_backfill_dry_run_non_scrive(tmp_path, senza_provenienza_db):
    percorso = tmp_path / "2026-09-03.json"
    originale = json.dumps(_dossier_con_funnel())
    percorso.write_text(originale)

    backfill.backfill_file(percorso, dry_run=True)

    assert percorso.read_text() == originale