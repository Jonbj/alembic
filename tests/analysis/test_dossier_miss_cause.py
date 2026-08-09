"""Causa deterministica del miss: trasforma l'evidenza grezza in una categoria
meccanica che soddisfa la domanda di uscita n.1 della carta di osservazione (#208).

Regole (in ordine):
- IN_PORTAFOGLIO  — gia' in posizione (non dovrebbe comparire dopo il filtro, ma la
  tassonomia lo prevede)
- NO_NEWS         — news_count == 0
- NO_SIGNAL       — news_count > 0 ma segnali vuoto
- THIN_NEUTRAL    — segnali esistenti ma |score| massimo sotto soglia_thin
- BELOW_GATE      — segnali esistenti con |score| massimo fra soglia_thin e soglia_gate
  (avremmo potuto comprare S4 se il segnale fosse stato sopra il gate)
"""

import pytest

from src.analysis.dossier.miss_cause import (
    classify_miss_candidates,
    count_by_cause,
    dominant_cause,
)


def _cand(
    symbol: str,
    news_count: int,
    segnali: list[dict],
    in_portafoglio: bool = False,
    return_: float = 0.05,
) -> dict:
    return {
        "symbol": symbol,
        "return": return_,
        "news_count": news_count,
        "segnali": segnali,
        "in_portafoglio": in_portafoglio,
    }


def test_no_news_se_conteggio_notizie_zero():
    out = classify_miss_candidates([_cand("BA", news_count=0, segnali=[])])
    assert out[0]["causa"] == "NO_NEWS"


def test_no_signal_se_notizie_presenti_ma_segnali_vuoto():
    out = classify_miss_candidates([_cand("RDDT", news_count=1, segnali=[])])
    assert out[0]["causa"] == "NO_SIGNAL"


def test_thin_neutral_se_max_score_sotto_soglia_thin():
    """Un segnale neutro (score 0.0) conta come THIN_NEUTRAL, non BELOW_GATE."""
    out = classify_miss_candidates([_cand("AZN", news_count=1, segnali=[
        {"ora": "18:45", "score": 0.0, "fallback": False}
    ])])
    assert out[0]["causa"] == "THIN_NEUTRAL"


def test_below_gate_se_max_score_tra_thin_e_gate():
    """SNOW il 2026-08-03: score 0.195 — sopra thin (0.05), sotto gate (0.30)."""
    out = classify_miss_candidates([_cand("SNOW", news_count=1, segnali=[
        {"ora": "16:30", "score": 0.195, "fallback": False}
    ])])
    assert out[0]["causa"] == "BELOW_GATE"


def test_segnale_fallback_con_punteggio_zero_non_puo_salvare_la_categoria():
    """Un fallback con score=0 e' neutro; non sale di categoria per il solo fallback."""
    out = classify_miss_candidates([_cand("IBM", news_count=1, segnali=[
        {"ora": "19:16", "score": 0.0, "fallback": True}
    ])])
    assert out[0]["causa"] == "THIN_NEUTRAL"


def test_classificazione_usata_sul_massimo_in_valore_assoluto():
    """Se ci sono piu' segnali, conta |max|. Caso SPCX 2026-08-03: max|score|=0.250."""
    out = classify_miss_candidates([_cand("SPCX", news_count=6, segnali=[
        {"ora": "14:15", "score": -0.100, "fallback": False},
        {"ora": "14:45", "score": 0.120, "fallback": True},
        {"ora": "16:46", "score": 0.0, "fallback": False},
        {"ora": "19:45", "score": -0.250, "fallback": False},
    ])])
    assert out[0]["causa"] == "BELOW_GATE"


def test_in_portafoglio_prevale_su_tutto_anche_se_news_count_zero():
    """Se in_portafoglio=True la causa e' IN_PORTAFOGLIO, non NO_NEWS.

    Non dovrebbe mai capitare perche' compute_miss_candidates filtra, ma la
    tassonomia della carta lo prevede e il classificatore non assorbe l'eccezione.
    """
    out = classify_miss_candidates([_cand("AAPL", news_count=0, segnali=[],
                                           in_portafoglio=True)])
    assert out[0]["causa"] == "IN_PORTAFOGLIO"


def test_sopra_gate_non_e_un_miss_classificabile_da_questa_tassonomia():
    """Un segnale sopra 0.30 con notizie non dovrebbe essere un miss di S4 — o
    il dossier non lo sta filtrando, o il trade e' avvenuto. Classifichiamo
    comunque come NON_CLASSIFICATO per non lasciare una chiave vuota (raro, ma
    difendiamo il campo)."""
    out = classify_miss_candidates([_cand("X", news_count=1, segnali=[
        {"ora": "15:00", "score": 0.45, "fallback": False}
    ])])
    assert out[0]["causa"] == "NON_CLASSIFICATO"


def test_conteggio_per_cause_aggregato():
    candidati = [
        _cand("BA", news_count=0, segnali=[]),
        _cand("HOOD", news_count=0, segnali=[]),
        _cand("SAP", news_count=0, segnali=[]),
        _cand("RDDT", news_count=1, segnali=[
            {"ora": "15:45", "score": 0.169, "fallback": False}
        ]),
        _cand("SNOW", news_count=1, segnali=[
            {"ora": "16:30", "score": 0.195, "fallback": False}
        ]),
        _cand("AZN", news_count=1, segnali=[
            {"ora": "18:45", "score": 0.0, "fallback": False}
        ]),
    ]
    out = classify_miss_candidates(candidati)
    counts = count_by_cause(out)
    assert counts == {"NO_NEWS": 3, "BELOW_GATE": 2, "THIN_NEUTRAL": 1}


def test_dominante_restituisce_la_causa_con_piu_occorrenze():
    counts = {"NO_NEWS": 3, "BELOW_GATE": 2, "THIN_NEUTRAL": 1}
    assert dominant_cause(counts) == "NO_NEWS"


def test_dominante_in_caso_di_pareggio_usa_ordine_stabilito():
    """Il pareggio del 2026-08-05 (NO_NEWS=2, BELOW_GATE=2) non ha dominante."""
    counts = {"NO_NEWS": 2, "BELOW_GATE": 2}
    assert dominant_cause(counts) is None


def test_dominante_su_conteggi_vuoti():
    assert dominant_cause({}) is None


def test_soglie_default_thin_005_gate_030():
    """I default della tassonomia: thin=0.05 (neutro), gate=0.30 (baseline S4)."""
    out = classify_miss_candidates([_cand("X", news_count=1, segnali=[
        {"ora": "14:00", "score": 0.06, "fallback": False}
    ])])
    assert out[0]["causa"] == "BELOW_GATE"


# --- #208: la soglia del dossier deve essere quella effettiva del giorno, non il
# default 0.30. Tra il 07-31 e il 08-07 il ratchet aveva spinto il gate a 0.40-0.45
# (issue #191): con score 0.35 il candidato e' un BELOW_GATE reale, NON un
# NON_CLASSIFICATO come vorrebbe il default. Il test e' la difesa minima: se la
# soglia scende, il candidato ri-beccheresta NON_CLASSIFICATO.

def test_soglia_gate_045_classifica_035_come_below_gate():
    """Con soglia 0.45, score 0.35 deve risultare BELOW_GATE (non NON_CLASSIFICATO)."""
    out = classify_miss_candidates(
        [_cand("AAPL", news_count=1, segnali=[
            {"ora": "15:30", "score": 0.35, "fallback": False}
        ])],
        soglia_gate=0.45,
    )
    assert out[0]["causa"] == "BELOW_GATE"


def test_soglia_gate_045_segnale_just_sotto_e_below_gate():
    """Il confine e' half-open [soglia_thin, soglia_gate): 0.44 con soglia 0.45 e' BELOW_GATE."""
    out = classify_miss_candidates(
        [_cand("AAPL", news_count=1, segnali=[
            {"ora": "15:30", "score": 0.44, "fallback": False}
        ])],
        soglia_gate=0.45,
    )
    assert out[0]["causa"] == "BELOW_GATE"


def test_soglia_gate_045_segnale_alla_soglia_diventa_non_classificato():
    """Alla soglia non e' un miss: NON_CLASSIFICATO e' il sentinel.

    La classificazione usa l'intervallo [soglia_thin, soglia_gate): score == soglia_gate
    esce dal dominio BELOW_GATE e finisce in NON_CLASSIFICATO. Coerente con il gate
    runtime `>=` (vedi _gate_is_active in portfolio_scheduler.py): il segnale NON
    viene filtrato dal gate e quindi NON doveva essere un miss in primo luogo.
    """
    out = classify_miss_candidates(
        [_cand("AAPL", news_count=1, segnali=[
            {"ora": "15:30", "score": 0.45, "fallback": False}
        ])],
        soglia_gate=0.45,
    )
    assert out[0]["causa"] == "NON_CLASSIFICATO"


def test_regressione_4_giorni_riproduce_la_tabella_della_issue():
    """Copia gli score reali dei dossier gia' scritti: la tabella della issue
    deve uscire identica, senza re-derivare dalla prosa del report."""
    candidati_0803 = [
        _cand("RDDT", 1, [{"ora": "15:45", "score": 0.169, "fallback": False}]),
        _cand("BA", 0, []),
        _cand("AZN", 1, [{"ora": "18:45", "score": 0.0, "fallback": False}]),
        _cand("SPCX", 6, [{"ora": "14:15", "score": -0.100, "fallback": False},
                          {"ora": "14:45", "score": 0.120, "fallback": True},
                          {"ora": "16:01", "score": -0.120, "fallback": True},
                          {"ora": "16:16", "score": 0.110, "fallback": True},
                          {"ora": "16:46", "score": 0.0, "fallback": False},
                          {"ora": "19:45", "score": -0.250, "fallback": False}]),
        _cand("SNOW", 1, [{"ora": "16:30", "score": 0.195, "fallback": False}]),
        _cand("HOOD", 0, []),
        _cand("BABA", 2, [{"ora": "17:00", "score": 0.0, "fallback": False},
                          {"ora": "17:30", "score": 0.230, "fallback": False}]),
        _cand("TSLA", 1, [{"ora": "14:16", "score": -0.012, "fallback": False}]),
        _cand("SAP", 0, []),
    ]
    candidati_0804 = [
        _cand("SPCX", 7, [{"ora": "14:45", "score": 0.0, "fallback": False},
                          {"ora": "14:45", "score": 0.0, "fallback": False},
                          {"ora": "17:16", "score": 0.019, "fallback": True},
                          {"ora": "17:30", "score": 0.0, "fallback": False},
                          {"ora": "18:00", "score": 0.0, "fallback": False},
                          {"ora": "19:16", "score": 0.450, "fallback": True},
                          {"ora": "19:45", "score": -0.300, "fallback": False}]),
        _cand("QCOM", 0, []),
        _cand("AVGO", 4, [{"ora": "16:45", "score": 0.276, "fallback": False},
                          {"ora": "17:45", "score": -0.120, "fallback": True},
                          {"ora": "18:46", "score": 0.120, "fallback": True},
                          {"ora": "19:30", "score": 0.133, "fallback": False}]),
        _cand("IBM", 1, [{"ora": "19:16", "score": 0.0, "fallback": True}]),
        _cand("HOOD", 0, []),
        _cand("NOW", 0, []),
        _cand("RDDT", 0, []),
        _cand("SAP", 0, []),
        _cand("SNOW", 0, []),
    ]
    candidati_0805 = [
        _cand("SPCX", 4, [{"ora": "14:30", "score": 0.107, "fallback": True},
                          {"ora": "17:30", "score": -0.170, "fallback": False},
                          {"ora": "18:31", "score": 0.0, "fallback": False},
                          {"ora": "19:00", "score": 0.0, "fallback": False}]),
        _cand("AZN", 0, []),
        _cand("NVDA", 6, [{"ora": "14:45", "score": 0.040, "fallback": True},
                          {"ora": "16:45", "score": -0.160, "fallback": True},
                          {"ora": "17:15", "score": 0.154, "fallback": False},
                          {"ora": "18:00", "score": 0.100, "fallback": False},
                          {"ora": "18:30", "score": 0.0, "fallback": False},
                          {"ora": "19:00", "score": 0.0, "fallback": False}]),
        _cand("QCOM", 0, []),
    ]
    candidati_0806 = [
        _cand("TMUS", 0, []),
        _cand("BA", 1, [{"ora": "18:15", "score": 0.0, "fallback": False}]),
        _cand("NVO", 2, [{"ora": "14:16", "score": 0.208, "fallback": False},
                          {"ora": "14:46", "score": 0.221, "fallback": False}]),
        _cand("CRM", 1, [{"ora": "18:30", "score": 0.0, "fallback": False}]),
    ]

    atteso = [
        ("2026-08-03", candidati_0803, {"NO_NEWS": 3, "BELOW_GATE": 4, "THIN_NEUTRAL": 2}),
        ("2026-08-04", candidati_0804, {"NO_NEWS": 6, "BELOW_GATE": 1, "THIN_NEUTRAL": 1, "NON_CLASSIFICATO": 1}),
        ("2026-08-05", candidati_0805, {"NO_NEWS": 2, "BELOW_GATE": 2}),
        ("2026-08-06", candidati_0806, {"NO_NEWS": 1, "BELOW_GATE": 1, "THIN_NEUTRAL": 2}),
    ]
    for giorno, candidati, expected_counts in atteso:
        out = classify_miss_candidates(candidati)
        counts = count_by_cause(out)
        assert counts == expected_counts, f"{giorno}: {counts} != {expected_counts}"
        # La somma di cause deve essere uguale al numero di candidati.
        assert sum(counts.values()) == len(candidati), f"{giorno}: somma sbagliata"
