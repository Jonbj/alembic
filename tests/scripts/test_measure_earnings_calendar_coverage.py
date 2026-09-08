"""Test per scripts/measure_earnings_calendar_coverage.py (#507 step 5).

La misura della pre-registrazione `PREREGISTRAZIONE_CALENDARIO_EARNINGS_507.md`
gira una sola volta a finestra finita; qui si esercita la regola su dossier
finti in una directory temporanea, con la verita' FMP (GT-2) stubbata. Il flag
True non viene mai ricalcolato: si legge quello che il dossier ha persistito.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import scripts.measure_earnings_calendar_coverage as mec


def _sedute(n: int) -> list[str]:
    inizio = date(2026, 9, 8)
    return [(inizio + timedelta(days=i)).isoformat() for i in range(n)]


def _dossier_osservato(seduta: str, flaggati: list[str] | None = None) -> dict:
    return {
        "schema_version": "2.9",
        "calendario_earnings": {
            "status": "OBSERVED",
            "simboli_flaggati": sorted(flaggati or []),
            "missingness": [],
            "sources_succeeded": ["FMP earnings-calendar"],
            "streak_sedute_consecutive_unknown": 0,
        },
    }


def _dossier_cieco(seduta: str) -> dict:
    return {
        "schema_version": "2.9",
        "calendario_earnings": {
            "status": "UNKNOWN",
            "simboli_flaggati": None,
            "missingness": ["earnings_calendar_fetch_failed"],
            "sources_succeeded": [],
            "streak_sedute_consecutive_unknown": 1,
        },
    }


def _scrivi_dossier(dir_dossier: Path, seduta: str, payload: dict) -> None:
    dir_dossier.mkdir(parents=True, exist_ok=True)
    (dir_dossier / f"{seduta}.json").write_text(json.dumps(payload))


def _scrivi_gt1(percorso: Path, eventi: list[dict]) -> Path:
    percorso.write_text(json.dumps(eventi, ensure_ascii=False))
    return percorso


def _run(
    tmp_path: Path,
    dossier_payloads: dict[str, dict],
    gt1_eventi: list[dict],
    righe_fmp: dict[str, list] | None = None,
) -> tuple[dict, Path]:
    dir_dossier = tmp_path / "dossier"
    for seduta, payload in dossier_payloads.items():
        _scrivi_dossier(dir_dossier, seduta, payload)
    percorso_gt1 = _scrivi_gt1(tmp_path / "gt1.json", gt1_eventi)
    percorso_out = tmp_path / "coverage.json"

    def _risposta_fmp(url: str, *args, **kwargs):
        # _verita_fmp passa i parametri come kwargs, non nell'url
        seduta = (kwargs.get("params") or {}).get("from", "")
        return SimpleNamespace(
            json=lambda: (righe_fmp or {}).get(seduta, []),
            raise_for_status=lambda: None,
        )

    with (
        patch.dict("os.environ", {"FMP_API_KEY": "k"}),
        patch("httpx.get", side_effect=_risposta_fmp),
        patch(
            "sys.argv",
            [
                "measure_earnings_calendar_coverage.py",
                "--dossier-dir", str(dir_dossier),
                "--gt1-json", str(percorso_gt1),
                "--out", str(percorso_out),
            ],
        ),
    ):
        mec.main()

    return json.loads(percorso_out.read_text()), percorso_out


def test_recall_gt1_sotto_la_metasotto_il_50percento_è_inadeguata(tmp_path):
    sedute = _sedute(20)
    payloads = {s: _dossier_osservato(s, ["DELL"] if s == sedute[0] else []) for s in sedute}
    gt1 = [
        {"seduta": sedute[0], "simbolo": "DELL", "citazione": "report 09-08"},
        {"seduta": sedute[1], "simbolo": "ORCL", "citazione": "report 09-09"},
        {"seduta": sedute[2], "simbolo": "ADBE", "citazione": "report 09-10"},
        {"seduta": sedute[3], "simbolo": "CRM", "citazione": "report 09-11"},
        {"seduta": sedute[4], "simbolo": "MSFT", "citazione": "report 09-12"},
    ]
    evidenza, _ = _run(tmp_path, payloads, gt1)

    assert evidenza["esito"] == "INADEGUATA"
    assert evidenza["gt1"]["n_eventi"] == 5
    assert evidenza["gt1"]["n_flaggati"] == 1
    assert evidenza["gt1"]["recall"] == 0.2
    # l'evento marcabile porta la citazione con sé: la GT-1 è curata, verificabile
    assert evidenza["gt1"]["eventi"][0]["flaggato"] is True
    assert evidenza["gt1"]["eventi"][0]["citazione"] == "report 09-08"


def test_recall_gt1_sopra_la_soglia_è_adeguata(tmp_path):
    sedute = _sedute(20)
    flaggati = {sedute[0]: ["DELL", "ORCL", "ADBE"]}
    payloads = {s: _dossier_osservato(s, flaggati.get(s, [])) for s in sedute}
    gt1 = [
        {"seduta": sedute[0], "simbolo": "DELL", "citazione": "r"},
        {"seduta": sedute[0], "simbolo": "ORCL", "citazione": "r"},
        {"seduta": sedute[0], "simbolo": "ADBE", "citazione": "r"},
        {"seduta": sedute[1], "simbolo": "CRM", "citazione": "r"},
        {"seduta": sedute[2], "simbolo": "MSFT", "citazione": "r"},
    ]
    evidenza, _ = _run(tmp_path, payloads, gt1)
    assert evidenza["esito"] == "ADEGUATA"
    assert evidenza["gt1"]["recall"] == 0.6


def test_finestra_incompleta_è_insufficient_n(tmp_path):
    sedute = _sedute(15)
    payloads = {s: _dossier_osservato(s) for s in sedute}
    evidenza, _ = _run(tmp_path, payloads, [])
    assert evidenza["esito"] == "INSUFFICIENT_N"
    assert "finestra incompleta" in evidenza["motivo"]


def test_piu_di_4_sedute_unknown_è_cecita_ricomparsa(tmp_path):
    sedute = _sedute(20)
    payloads = {
        s: (_dossier_cieco(s) if i < 5 else _dossier_osservato(s))
        for i, s in enumerate(sedute)
    }
    gt1 = [{"seduta": sedute[6], "simbolo": "NVDA", "citazione": "r"}]
    evidenza, _ = _run(tmp_path, payloads, gt1)
    assert evidenza["esito"] == "INSUFFICIENT_N"
    assert "cecità ricomparsa" in evidenza["motivo"]
    assert evidenza["sedute"]["unknown"] == 5


def test_gt1_sotto_5_eventi_non_decide(tmp_path):
    sedute = _sedute(20)
    payloads = {s: _dossier_osservato(s) for s in sedute}
    gt1 = [
        {"seduta": sedute[0], "simbolo": "DELL", "citazione": "r"},
        {"seduta": sedute[1], "simbolo": "ORCL", "citazione": "r"},
        {"seduta": sedute[2], "simbolo": "ADBE", "citazione": "r"},
    ]
    evidenza, _ = _run(tmp_path, payloads, gt1)
    assert evidenza["esito"] == "INSUFFICIENT_N"
    assert "GT-1" in evidenza["motivo"]


def test_eventi_gt1_fuori_finestra_e_in_sedute_cieche_non_contano(tmp_path):
    sedute = _sedute(20)
    payloads = {s: _dossier_osservato(s, ["DELL"]) for s in sedute}
    payloads[sedute[2]] = _dossier_cieco(sedute[2])
    payloads[sedute[3]] = _dossier_cieco(sedute[3])
    gt1 = [
        {"seduta": sedute[0], "simbolo": "DELL", "citazione": "r"},
        {"seduta": "2026-09-02", "simbolo": "PANW", "citazione": "fuori finestra"},
        {"seduta": sedute[2], "simbolo": "SNOW", "citazione": "seduta cieca"},
        {"seduta": sedute[4], "simbolo": "ORCL", "citazione": "r"},
        {"seduta": sedute[5], "simbolo": "ADBE", "citazione": "r"},
        {"seduta": sedute[6], "simbolo": "CRM", "citazione": "r"},
        {"seduta": sedute[7], "simbolo": "NVDA", "citazione": "r"},
    ]
    evidenza, _ = _run(tmp_path, payloads, gt1)
    # 5 eventi in sedute usabili (1 fuori finestra, 1 in seduta cieca scartati),
    # 1 marcato -> recall 0.2 -> INADEGUATA
    assert evidenza["gt1"]["n_eventi"] == 5
    assert evidenza["gt1"]["fuori_finestra"] == 1
    assert evidenza["gt1"]["in_sedute_cieche"] == 1
    assert evidenza["esito"] == "INADEGUATA"


def test_gt2_letta_da_fmp_e_filtrata_sulla_watchlist(tmp_path):
    sedute = _sedute(20)
    payloads = {s: _dossier_osservato(s, ["ORCL"]) for s in sedute}
    gt1 = [
        {"seduta": sedute[0], "simbolo": "ORCL", "citazione": "r"},
        {"seduta": sedute[1], "simbolo": "ADBE", "citazione": "r"},
        {"seduta": sedute[2], "simbolo": "CRM", "citazione": "r"},
        {"seduta": sedute[3], "simbolo": "MSFT", "citazione": "r"},
        {"seduta": sedute[4], "simbolo": "NVDA", "citazione": "r"},
    ]
    righe_fmp = {
        sedute[0]: [
            {"symbol": "ORCL", "date": sedute[0]},
            {"symbol": "ZZZZ", "date": sedute[0]},  # fuori watchlist: fuori verita'
        ],
        sedute[1]: [{"symbol": "ADBE", "date": sedute[1]}],
    }
    evidenza, _ = _run(tmp_path, payloads, gt1, righe_fmp=righe_fmp)
    verita = evidenza["gt2"]["verita_per_seduta"]
    assert sorted(verita[sedute[0]]) == ["ORCL"]
    # ORCL flaggato dalla produzione, ADBE no: recall 0.5
    assert evidenza["gt2"]["n_eventi"] == 2
    assert evidenza["gt2"]["n_flaggati"] == 1
    assert evidenza["gt2"]["recall"] == 0.5
    # il lag di ingestione va riportato: ultima data vista nei record letti
    assert evidenza["gt2"]["ultimo_record_disponibile"] == sedute[1]


def test_fallback_intenti_quando_manca_il_campo_simboli_flaggati(tmp_path):
    sedute = _sedute(20)
    pre_campo = {
        "schema_version": "2.9",
        "calendario_earnings": {"status": "OBSERVED"},
        "intenti_ingresso_s4": [
            {"symbol": "DELL", "giorno_di_earnings": True},
            {"symbol": "MSFT", "giorno_di_earnings": False},
        ],
    }
    payloads = {s: _dossier_osservato(s) for s in sedute}
    payloads[sedute[0]] = pre_campo
    gt1 = [
        {"seduta": sedute[0], "simbolo": "DELL", "citazione": "r"},
        {"seduta": sedute[1], "simbolo": "ORCL", "citazione": "r"},
        {"seduta": sedute[2], "simbolo": "ADBE", "citazione": "r"},
        {"seduta": sedute[3], "simbolo": "CRM", "citazione": "r"},
        {"seduta": sedute[4], "simbolo": "MSFT", "citazione": "r"},
    ]
    evidenza, _ = _run(tmp_path, payloads, gt1)
    assert evidenza["gt1"]["n_flaggati"] == 1
    assert evidenza["per_seduta"][0]["fonte_flag"] == "intenti"
    # il confondo dichiarato: il fallback vede solo i simboli con un intento
    assert evidenza["per_seduta"][0]["nota_fonte_flag"]