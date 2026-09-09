"""#509: la causa legacy consuma il verdetto funnel_v2.

Il classificatore legacy (#208) definisce NON_CLASSIFICATO per esclusione
(|score| massimo >= gate: "o non era un miss, o il dossier non filtra bene").
Il funnel v2 (#281), nello stesso dossier, sa gia' perche' quel candidato non e'
diventato un ingresso: il verdetto va promosso nella causa legacy, conservando
il valore storico in `causa_legacy`.

Vincolo #288 Opzione 1 (decisione PO 2026-09-05): la serie legacy pre-registrata
 resta invariata — `count_by_cause` e `cause_del_giorno` contano la serie
legacy anche dopo la promozione. Solo il campo per-candidato cambia.
"""

import pytest

from src.analysis.dossier.funnel import build_funnel, riconcilia_cause_con_funnel
from src.analysis.dossier.miss_cause import (
    NON_CLASSIFICATO,
    cause_del_giorno,
    classify_miss_candidates,
    count_by_cause,
)


def _candidato_sopra_gate(symbol="TSLA", return_=0.054):
    """Candidato con |score| massimo sopra il gate: legacy NON_CLASSIFICATO.

    I tre punteggi sono quelli veri di TSLA il 2026-09-03 (issue #509):
    l'unico qualificante e' fallback (#108), quindi il funnel v2 lo ferma a
    FALLBACK_REJECT.
    """
    return {
        "symbol": symbol,
        "return": return_,
        "news_count": 1,
        "segnali": [
            {"ora": "16:15", "score": 0.277, "fallback": False},
            {"ora": "19:15", "score": 0.221, "fallback": False},
            {"ora": "19:45", "score": 0.468, "fallback": True},
        ],
        "in_portafoglio": False,
    }


def _funnel_con_riga(symbol="TSLA", return_=0.054, pipeline="FALLBACK_REJECT",
                     actionability="ENTRY_OPPORTUNITY"):
    """Blocco funnel_v2 minimale con una riga per il simbolo.

    Costruito con build_funnel dove possibile, altrimenti a mano: il contratto
    della riconciliazione e' la forma pubblicata nel dossier, non il costruttore.
    """
    if pipeline is None:
        # mover non ENTRY_OPPORTUNITY: la riga porta solo l'asse actionability
        return {
            "funnel_version": "1.0",
            "righe": [{
                "symbol": symbol, "rendimento": return_, "held": False,
                "actionability": actionability, "pipeline": None,
                "pipeline_escluso_motivo": "non_actionable_long_only",
                "evidence": {}, "legacy_causa": NON_CLASSIFICATO,
                "net_profitable": None, "net_opportunity_usd": None,
            }],
        }
    return {
        "funnel_version": "1.0",
        "righe": [{
            "symbol": symbol, "rendimento": return_, "held": False,
            "actionability": actionability, "pipeline": pipeline,
            "pipeline_escluso_motivo": None,
            "evidence": {"score_firmato": 0.468, "n_qualificanti_fallback": 1},
            "legacy_causa": NON_CLASSIFICATO,
            "net_profitable": None, "net_opportunity_usd": -35.29,
        }],
    }


def test_regressione_509_sopra_gate_con_verdetto_non_resta_non_classificato():
    """La regressione che la issue #509 chiede punto per punto: un candidato
    con |score| >= gate NON resta NON_CLASSIFICATO quando funnel_v2 produce un
    verdetto per lo stesso simbolo."""
    candidati = classify_miss_candidates([_candidato_sopra_gate()])
    assert candidati[0]["causa"] == NON_CLASSIFICATO  # premessa: legacy

    riconcilia_cause_con_funnel(candidati, _funnel_con_riga())

    assert candidati[0]["causa"] == "FALLBACK_REJECT"
    assert candidati[0]["causa_legacy"] == NON_CLASSIFICATO


def test_promuove_actionability_quando_la_pipeline_non_si_valuta():
    """PLTR 2026-09-02: ribasso non detenuto in book long-only. La pipeline
    d'ingresso non si valuta, ma l'asse actionability risolve comunque il
    NON_CLASSIFICATO: NON_ACTIONABLE e' "non era un miss", con motivo noto."""
    candidati = classify_miss_candidates(
        [_candidato_sopra_gate("PLTR", return_=-0.058)]
    )
    assert candidati[0]["causa"] == NON_CLASSIFICATO

    riconcilia_cause_con_funnel(
        candidati, _funnel_con_riga("PLTR", -0.058, pipeline=None,
                                    actionability="NON_ACTIONABLE")
    )

    assert candidati[0]["causa"] == "NON_ACTIONABLE"
    assert candidati[0]["causa_legacy"] == NON_CLASSIFICATO


def test_senza_riga_funnel_la_causa_resta_non_classificato():
    """Dossier pre-funnel_v2 (tutti quelli prima del 2026-09-03): nessun
    verdetto da promuovere, la causa resta il sentinel legacy e non nasce
    un causa_legacy fittizio."""
    candidati = classify_miss_candidates([_candidato_sopra_gate()])

    riconcilia_cause_con_funnel(candidati, {"funnel_version": "1.0", "righe": []})

    assert candidati[0]["causa"] == NON_CLASSIFICATO
    assert "causa_legacy" not in candidati[0]


def test_solo_i_non_classificati_vengono_promossi():
    """Le altre categorie sono il vocabolario registrato della carta (#288):
    la riconciliazione non le tocca, nemmeno quando la riga funnel esiste."""
    candidati = classify_miss_candidates([
        _candidato_sopra_gate("TSLA"),
        {
            "symbol": "NVDA", "return": 0.05, "news_count": 1,
            "segnali": [{"ora": "17:00", "score": 0.19, "fallback": False}],
            "in_portafoglio": False,
        },  # BELOW_GATE
        {
            "symbol": "BA", "return": -0.05, "news_count": 0, "segnali": [],
            "in_portafoglio": False,
        },  # NO_NEWS
    ])
    funnel = _funnel_con_riga("TSLA")
    funnel["righe"].append({
        "symbol": "NVDA", "rendimento": 0.05, "held": False,
        "actionability": "ENTRY_OPPORTUNITY", "pipeline": "BELOW_GATE",
        "pipeline_escluso_motivo": None, "evidence": {},
        "legacy_causa": "BELOW_GATE", "net_profitable": None,
        "net_opportunity_usd": None,
    })
    funnel["righe"].append({
        "symbol": "BA", "rendimento": -0.05, "held": False,
        "actionability": "NON_ACTIONABLE", "pipeline": None,
        "pipeline_escluso_motivo": "non_actionable_long_only", "evidence": {},
        "legacy_causa": "NO_NEWS", "net_profitable": None,
        "net_opportunity_usd": None,
    })

    riconcilia_cause_con_funnel(candidati, funnel)

    by_symbol = {c["symbol"]: c for c in candidati}
    assert by_symbol["TSLA"]["causa"] == "FALLBACK_REJECT"
    assert by_symbol["NVDA"]["causa"] == "BELOW_GATE"  # intoccata
    assert by_symbol["BA"]["causa"] == "NO_NEWS"        # intoccata
    assert "causa_legacy" not in by_symbol["NVDA"]
    assert "causa_legacy" not in by_symbol["BA"]


def test_count_by_cause_conta_la_serie_legacy_dopo_la_promozione():
    """#288 Opzione 1: la serie pre-registrata resta invariata. Dopo la
    promozione il candidato vale FALLBACK_REJECT, ma il conteggio aggregato
    deve continuare a vederlo come NON_CLASSIFICATO — altrimenti `cause_del_giorno`
    e quindi il criterio di uscita n.1 cambierebbero a meta' finestra."""
    candidati = classify_miss_candidates([
        _candidato_sopra_gate("TSLA"),
        {
            "symbol": "BA", "return": -0.05, "news_count": 0, "segnali": [],
            "in_portafoglio": False,
        },
    ])
    prima = cause_del_giorno(candidati)

    riconcilia_cause_con_funnel(candidati, _funnel_con_riga("TSLA"))

    assert count_by_cause(candidati) == {"NO_NEWS": 1, NON_CLASSIFICATO: 1}
    # il blocco pubblicato e' identico a prima della promozione
    assert cause_del_giorno(candidati) == prima


def test_riconciliazione_idempotente():
    """Rilanciare la riconciliazione (backfill che riapplica piu' volte) non
    promuove due volte e non degrada il campo causa_legacy."""
    candidati = classify_miss_candidates([_candidato_sopra_gate()])
    funnel = _funnel_con_riga()

    riconcilia_cause_con_funnel(candidati, funnel)
    snapshot = {c["symbol"]: dict(c) for c in candidati}
    riconcilia_cause_con_funnel(candidati, funnel)

    assert {c["symbol"]: dict(c) for c in candidati} == snapshot


def test_riconciliazione_con_funnel_costruito_dal_modulo_puro():
    """Contratto end-to-end: il funnel vero (build_funnel) produce righe la
    cui forma la riconciliazione consuma senza adattamenti."""
    mover = {
        "symbol": "TSLA", "return": 0.054, "held": False, "in_universo": True,
        "articoli": {"effective_timely_articles": 1,
                     "rilevanza": {"ISSUER_SPECIFIC": 1}},
        "segnali": [{"ora": "19:45", "score": 0.468, "fallback": True}],
        "intenti": [], "guard": [], "ordine": None, "close": 250.0,
        "legacy_causa": NON_CLASSIFICATO,
        "opportunity_v2": None,
    }
    funnel = build_funnel([mover], soglia_gate=0.30)
    assert funnel["righe"][0]["pipeline"] == "FALLBACK_REJECT"

    candidati = classify_miss_candidates([_candidato_sopra_gate()])
    riconcilia_cause_con_funnel(candidati, funnel)
    assert candidati[0]["causa"] == "FALLBACK_REJECT"