"""Candidati ledger alpha-miss: validazione meccanica (#287, L3/P1).

La sessione LLM non appende piu' direttamente a findings.json e
market_daily.jsonl: emette un file di candidati che questo modulo valida
meccanicamente prima che il materializzatore lo applichi. Ogni regola qui e'
una delle regole che prima vivevano solo nel prompt, come prosa.
"""

import pytest

from src.analysis.dossier.candidates import (
    CANDIDATES_SCHEMA_VERSION,
    CHIAVI_MISS,
    CHIAVI_RIGA_MARKET,
    valida_candidati,
)
from src.analysis.dossier.prompt_contract import PROMPT_VERSION


def _riga_market(data="2026-09-15", **extra):
    riga = {
        "data": data,
        "spy": 0.001,
        "qqq": -0.002,
        "dispersione_sigma": 0.021,
        "mover_3pct": 7,
        "up": 5,
        "down": 2,
        "watchlist_zero_news": 40,
        "tema": "non chiaro",
        "miss": {c: 0 for c in CHIAVI_MISS},
        "catturati": 3,
        "book": {
            "equity": 110000.0,
            "realizzato": -12.5,
            "mtm": None,
            "s1_realizzato": -10.0,
            "s4_realizzato": -2.5,
        },
    }
    riga.update(extra)
    return riga


def _candidato_finding(**extra):
    candidato = {
        "finding_id": "F-004",
        "titolo": None,
        "tipo": "alpha_miss",
        "confidenza": "congetturale",
        "costo_usd": 132.0,
        "formula_costo": "2200 * 0.06 (size S4 ~2% NAV su mover +6%)",
        "nota": "ORCL +6% non intercettato",
        "fonte": "ALPHA_MISS_REPORT_2026-09-15.md §7",
        "esposizione": "ORCL era in watchlist e non detenuto: seduta esposta",
        "evidenza_contraria": "nessun segnale sopra gate su ORCL nel giorno",
        "non_occorrenza": "nelle 26 sedute precedenti ORCL non era mai mover",
        "next_evidence": "contare per quante sedute ORCL ha news effective-timely",
        "meccanismo": "news pubblicata dopo il close, nessun ciclo eleggibile",
        "alternative_scartate": ["beta di settore: il ritorno residuo vs XLK e' ancora +5%"],
        "giustificazione_nuovo": None,
    }
    candidato.update(extra)
    return candidato


def _findings():
    return {
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


def _candidati(**extra):
    payload = {
        "schema_version": CANDIDATES_SCHEMA_VERSION,
        "prompt_version": PROMPT_VERSION,
        "data": "2026-09-15",
        "market_daily": _riga_market(),
        "findings": [_candidato_finding()],
    }
    payload.update(extra)
    return payload


def test_payload_valido_passa():
    esito = valida_candidati(_candidati(), _findings(), righe_market=[])

    assert esito["ok"] is True, esito["errors"]
    assert esito["errors"] == []


def test_prompt_version_diverso_viene_rifiutato():
    payload = _candidati(prompt_version="alpha_miss_v0")
    esito = valida_candidati(payload, _findings(), righe_market=[])

    assert esito["ok"] is False
    assert any("prompt_version" in e for e in esito["errors"])


def test_riga_market_con_chiavi_errate_viene_rifiutata():
    riga = _riga_market()
    riga.pop("tema")
    riga["tema_pattern"] = "x"
    esito = valida_candidati(_candidati(market_daily=riga), _findings(), righe_market=[])

    assert esito["ok"] is False
    assert any("tema" in e for e in esito["errors"])


def test_riga_market_con_data_diversa_dalla_seduta_viene_rifiutata():
    riga = _riga_market(data="2026-09-14")
    esito = valida_candidati(
        _candidati(data="2026-09-15", market_daily=riga), _findings(), righe_market=[]
    )

    assert esito["ok"] is False
    assert any("data" in e for e in esito["errors"])


def test_riga_gia_presente_non_e_un_errore_ma_un_avviso():
    righe = [_riga_market(data="2026-09-15")]
    esito = valida_candidati(_candidati(), _findings(), righe_market=righe)

    assert esito["ok"] is True
    assert any("gia' presente" in w for w in esito["warnings"])


def test_costo_stimato_senza_formula_viene_rifiutato():
    candidato = _candidato_finding(formula_costo="")
    esito = valida_candidati(
        _candidati(findings=[candidato]), _findings(), righe_market=[]
    )

    assert esito["ok"] is False
    assert any("formula_costo" in e for e in esito["errors"])


def test_costo_null_senza_formula_e_ammesso():
    candidato = _candidato_finding(costo_usd=None, formula_costo=None)
    esito = valida_candidati(
        _candidati(findings=[candidato]), _findings(), righe_market=[]
    )

    assert esito["ok"] is True, esito["errors"]


def test_finding_sconosciuto_viene_rifiutato():
    candidato = _candidato_finding(finding_id="F-999")
    esito = valida_candidati(
        _candidati(findings=[candidato]), _findings(), righe_market=[]
    )

    assert esito["ok"] is False
    assert any("F-999" in e for e in esito["errors"])


def test_nuovo_finding_richiede_titolo_e_giustificazione():
    candidato = _candidato_finding(finding_id="F-NUOVO", giustificazione_nuovo=None)
    esito = valida_candidati(
        _candidati(findings=[candidato]), _findings(), righe_market=[]
    )

    assert esito["ok"] is False
    assert any("giustificazione_nuovo" in e for e in esito["errors"])


def test_nuovo_finding_completo_passa():
    candidato = _candidato_finding(
        finding_id="F-NUOVO",
        titolo="Nuovo difetto strutturale",
        giustificazione_nuovo="non riconduceibile a nessun finding aperto: manca",
    )
    esito = valida_candidati(
        _candidati(findings=[candidato]), _findings(), righe_market=[]
    )

    assert esito["ok"] is True, esito["errors"]


def test_confidenza_diversa_dal_record_esistente_viene_rifiutata():
    candidato = _candidato_finding(confidenza="misurata")
    esito = valida_candidati(
        _candidati(findings=[candidato]), _findings(), righe_market=[]
    )

    assert esito["ok"] is False
    assert any("confidenza" in e for e in esito["errors"])


def test_candidato_privo_di_campo_audit_viene_rifiutato():
    candidato = _candidato_finding(evidenza_contraria="")
    esito = valida_candidati(
        _candidati(findings=[candidato]), _findings(), righe_market=[]
    )

    assert esito["ok"] is False
    assert any("evidenza_contraria" in e for e in esito["errors"])


def test_candidato_senza_alternative_scartate_viene_rifiutato():
    candidato = _candidato_finding(alternative_scartate=[])
    esito = valida_candidati(
        _candidati(findings=[candidato]), _findings(), righe_market=[]
    )

    assert esito["ok"] is False
    assert any("alternative_scartate" in e for e in esito["errors"])


def test_occorrenza_dello_stesso_giorno_su_finding_esistente_avvisa():
    findings = _findings()
    findings["findings"][0]["occorrenze"] = [
        {"data": "2026-09-15", "costo_usd": 1.0, "nota": "gia' qui", "fonte": "x"}
    ]
    esito = valida_candidati(_candidati(), findings, righe_market=[])

    assert esito["ok"] is True
    assert any("2026-09-15" in w for w in esito["warnings"])


def test_le_chiavi_della_riga_dichiarano_lo_schema_del_ledger():
    # Lo schema e' la riga pre-registrata in market_daily.jsonl: cambiarlo
    # qui e' una discontinuita' di misura, non un refactor.
    assert CHIAVI_RIGA_MARKET == (
        "data", "spy", "qqq", "dispersione_sigma", "mover_3pct", "up", "down",
        "watchlist_zero_news", "tema", "miss", "catturati", "book",
    )

# --- applicazione ----------------------------------------------------------


from src.analysis.dossier.candidates import applica_candidati


def test_riga_market_nuova_viene_appesa_tale_e_quale():
    esito = applica_candidati(_candidati(), _findings(), righe_market=[])

    assert esito["mercato"] == "aggiunta"
    assert len(esito["righe"]) == 1
    assert esito["righe"][0] == _riga_market()


def test_riga_market_gia_presente_non_viene_appesa_due_volte():
    righe = [_riga_market()]
    esito = applica_candidati(_candidati(), _findings(), righe_market=righe)

    assert esito["mercato"] == "riga_gia_presente"
    assert len(esito["righe"]) == 1


def test_occorrenza_su_finding_esistente_usa_lo_schema_storico_a_quattro_campi():
    esito = applica_candidati(_candidati(), _findings(), righe_market=[])

    record = esito["findings"]["findings"][0]
    assert len(record["occorrenze"]) == 1
    occorrenza = record["occorrenze"][0]
    assert set(occorrenza.keys()) == {"data", "costo_usd", "nota", "fonte"}
    assert occorrenza["data"] == "2026-09-15"
    assert occorrenza["costo_usd"] == 132.0


def test_costo_cumulato_e_occorrenze_non_stimate_sono_ricalcolati_dal_codice():
    findings = _findings()
    findings["findings"][0]["occorrenze"] = [
        {"data": "2026-09-10", "costo_usd": 10.0, "nota": "a", "fonte": "x"},
        {"data": "2026-09-12", "costo_usd": None, "nota": "b", "fonte": "x"},
    ]
    esito = applica_candidati(_candidati(), findings, righe_market=[])

    record = esito["findings"]["findings"][0]
    assert record["costo_cumulato_usd"] == pytest.approx(142.0)
    assert record["occorrenze_non_stimate"] == 1


def test_finding_nuovo_prende_id_da_prossimo_id_e_lo_avanza():
    candidato = _candidato_finding(
        finding_id="F-NUOVO",
        titolo="Nuovo difetto strutturale",
        giustificazione_nuovo="non riconduceibile a nessun finding aperto: manca",
    )
    esito = applica_candidati(
        _candidati(findings=[candidato]), _findings(), righe_market=[]
    )

    assert esito["findings"]["prossimo_id"] == 5 + 1
    nuovo = esito["findings"]["findings"][-1]
    assert nuovo["id"] == "F-005"
    assert nuovo["titolo"] == "Nuovo difetto strutturale"
    assert nuovo["tipo"] == "alpha_miss"
    assert nuovo["confidenza"] == "congetturale"
    assert nuovo["primo_avvistamento"] == "2026-09-15"
    assert nuovo["stato"] == "aperto"
    assert nuovo["issue"] is None
    assert len(nuovo["occorrenze"]) == 1
    assert nuovo["costo_cumulato_usd"] == pytest.approx(132.0)


def test_occorrenza_doppia_per_finding_e_giorno_viene_saltata():
    findings = _findings()
    findings["findings"][0]["occorrenze"] = [
        {"data": "2026-09-15", "costo_usd": 1.0, "nota": "gia' qui", "fonte": "x"}
    ]
    esito = applica_candidati(_candidati(), findings, righe_market=[])

    record = esito["findings"]["findings"][0]
    assert len(record["occorrenze"]) == 1
    assert record["occorrenze"][0]["nota"] == "gia' qui"
    assert any("saltato" in w for w in esito["warnings"])


def test_applicare_non_muta_il_ledger_e_le_righe_di_partenza():
    findings = _findings()
    righe: list = []

    applica_candidati(_candidati(), findings, righe_market=righe)

    assert findings["findings"][0]["occorrenze"] == []
    assert righe == []


def test_payload_senza_findings_applica_solo_la_riga_di_mercato():
    esito = applica_candidati(_candidati(findings=[]), _findings(), righe_market=[])

    assert esito["mercato"] == "aggiunta"
    assert esito["findings"]["findings"] == _findings()["findings"]
    assert esito["applicati"] == []
