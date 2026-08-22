"""#244 — THIN_NEUTRAL spezzato in tre bucket.

Il vecchio THIN_NEUTRAL rispondeva a due domande opposte con la stessa parola:
«c'e' una notizia su questo titolo ed e' poco informativa» (il sentiment
editoriale non ha alpha) e «non c'e' nessuna notizia su questo titolo, stiamo
scorando un pezzo su un'altra societa'» (difetto della pipeline). Questi test
fissano la partizione:

- OFF_TOPIC                 — riga org_lookup, ticker assente dal testo scorato
                              (decidibile perche' GDELT GKG costruisce l'item
                              con body == title)
- THIN_NEUTRAL              — ticker citato, |score| sotto soglia_thin
- OFF_TOPIC_NON_DECIDIBILE  — riga source_metadata: snippet troncato, la
                              domanda non ha risposta su questo dato (QX-01/#30)

Nessuna soglia si muove (freeze #171): la partizione e' tutta interna alla
regione |score| < soglia_thin, la cui frontiera resta 0.05.
"""

from src.analysis.dossier.miss_cause import (
    classify_miss_candidate,
    classify_miss_candidates,
    count_by_cause,
    quota_righe_fanout,
    ticker_nel_testo,
)


def _cand(symbol: str, segnali: list[dict], news_count: int | None = None) -> dict:
    return {
        "symbol": symbol,
        "return": -0.04,
        "news_count": len(segnali) if news_count is None else news_count,
        "segnali": segnali,
        "in_portafoglio": False,
    }


def _seg(score: float, metodo: str = "", testo: str = "", n_ticker: int | None = None) -> dict:
    s: dict = {"ora": "18:30", "score": score, "fallback": False}
    if metodo:
        s["extraction_method"] = metodo
        s["testo_scorato"] = testo
    if n_ticker is not None:
        s["n_ticker_articolo"] = n_ticker
    return s


# --- bucket 1: OFF_TOPIC ---------------------------------------------------

def test_off_topic_org_lookup_senza_ticker_nel_titolo():
    """SPCX 2026-08-11: sei righe di copertura, zero sul ticker."""
    cand = _cand("SPCX", [
        _seg(0.0, "org_lookup", "10 Communication Services Stocks With Whale Alerts"),
        _seg(0.02, "org_lookup", "Rocket Lab Stock Soars On New Contract"),
    ])
    assert classify_miss_candidate(cand) == "OFF_TOPIC"


def test_off_topic_non_scatta_sopra_soglia_thin():
    """Sopra 0.05 la classificazione resta BELOW_GATE: le soglie non si toccano."""
    cand = _cand("SPCX", [
        _seg(0.19, "org_lookup", "Rocket Lab Stock Soars On New Contract"),
    ])
    assert classify_miss_candidate(cand) == "BELOW_GATE"


def test_una_riga_in_tema_riporta_il_candidato_a_thin_neutral():
    """OFF_TOPIC e' un limite inferiore: basta una riga che cita il ticker."""
    cand = _cand("NVDA", [
        _seg(0.01, "org_lookup", "Lumentum Posts Solid Q4 Results"),
        _seg(0.02, "org_lookup", "NVDA slips in late trading"),
    ])
    assert classify_miss_candidate(cand) == "THIN_NEUTRAL"


# --- bucket 2: THIN_NEUTRAL ------------------------------------------------

def test_thin_neutral_se_il_ticker_e_citato():
    cand = _cand("AZN", [_seg(0.0, "org_lookup", "AZN holds steady after trial update")])
    assert classify_miss_candidate(cand) == "THIN_NEUTRAL"


def test_thin_neutral_resta_il_default_senza_provenienza():
    """I dossier scritti prima di #244 non hanno extraction_method: la loro
    classificazione non deve cambiare da sola. La riclassificazione dei giorni
    gia' osservati e' una scelta esplicita del backfill."""
    cand = _cand("AZN", [_seg(0.0)])
    assert classify_miss_candidate(cand) == "THIN_NEUTRAL"


# --- bucket 3: OFF_TOPIC_NON_DECIDIBILE ------------------------------------

def test_non_decidibile_su_source_metadata():
    """Snippet troncato: il dossier non conserva il testo scorato."""
    cand = _cand("MU", [_seg(0.0, "source_metadata", "Baystreet.ca - Futures mixed as...")])
    assert classify_miss_candidate(cand) == "OFF_TOPIC_NON_DECIDIBILE"


def test_non_decidibile_anche_se_lo_snippet_cita_il_ticker():
    """Lo snippet e' troncato: che il ticker compaia nel frammento persistito non
    dice se compariva nel testo effettivamente scorato. Non si indovina."""
    cand = _cand("MU", [_seg(0.0, "source_metadata", "G&S Capital Sells 4,094 Shares of MU")])
    assert classify_miss_candidate(cand) == "OFF_TOPIC_NON_DECIDIBILE"


def test_org_lookup_senza_testo_persistito_e_non_decidibile():
    cand = _cand("MU", [_seg(0.0, "org_lookup", "")])
    assert classify_miss_candidate(cand) == "OFF_TOPIC_NON_DECIDIBILE"


def test_provenienza_ignota_a_questo_modulo_e_non_decidibile():
    cand = _cand("MU", [_seg(0.0, "metodo_futuro", "qualcosa")])
    assert classify_miss_candidate(cand) == "OFF_TOPIC_NON_DECIDIBILE"


def test_precedenza_off_topic_su_non_decidibile():
    """Una riga decidibile e fuori tema batte l'ignoranza sulle altre."""
    cand = _cand("SPCX", [
        _seg(0.0, "source_metadata", "Baystreet.ca - Futures mixed"),
        _seg(0.0, "org_lookup", "Tesla recalls 12,000 vehicles"),
    ])
    assert classify_miss_candidate(cand) == "OFF_TOPIC"


# --- i tre bucket insieme --------------------------------------------------

def test_i_tre_bucket_convivono_nel_conteggio_del_giorno():
    candidati = [
        _cand("SPCX", [_seg(0.0, "org_lookup", "10 Stocks With Whale Alerts")]),
        _cand("AZN", [_seg(0.0, "org_lookup", "AZN holds steady")]),
        _cand("MU", [_seg(0.0, "source_metadata", "Baystreet futures wrap")]),
        _cand("BA", [], news_count=0),
    ]
    counts = count_by_cause(classify_miss_candidates(candidati))
    assert counts == {
        "NO_NEWS": 1,
        "THIN_NEUTRAL": 1,
        "OFF_TOPIC": 1,
        "OFF_TOPIC_NON_DECIDIBILE": 1,
    }
    assert sum(counts.values()) == len(candidati)


def test_la_somma_dei_tre_bucket_e_il_vecchio_thin_neutral():
    """Invariante di partizione: nessun candidato entra o esce dalla regione
    |score| < soglia_thin per effetto di #244."""
    segnali_thin = [
        [_seg(0.0, "org_lookup", "Whale alerts roundup")],
        [_seg(0.01, "org_lookup", "AZN holds steady")],
        [_seg(0.04, "source_metadata", "Futures wrap")],
        [_seg(0.02)],
    ]
    candidati = [_cand("AZN", s) for s in segnali_thin]
    cause = {c["causa"] for c in classify_miss_candidates(candidati)}
    assert cause <= {"THIN_NEUTRAL", "OFF_TOPIC", "OFF_TOPIC_NON_DECIDIBILE"}


# --- riconoscimento del ticker nel testo -----------------------------------

def test_ticker_nel_testo_confini_di_token():
    assert ticker_nel_testo("MU", "G&S Capital Sells 4,094 Shares of MU")
    assert ticker_nel_testo("NVDA", "$NVDA rallies")
    assert ticker_nel_testo("NVDA", "(NVDA) up 3%")
    assert ticker_nel_testo("NVDA", "nvda up 3%")
    assert not ticker_nel_testo("MU", "Micron beats on revenue")  # limite inferiore noto
    assert not ticker_nel_testo("NVDA", "NVDAX fund inflows")
    assert not ticker_nel_testo("NVDA", "")
    assert not ticker_nel_testo("", "qualsiasi cosa")


# --- Q3: fan-out degree come metrica propria -------------------------------

def test_quota_righe_fanout_none_se_il_campo_non_e_persistito():
    assert quota_righe_fanout([_seg(0.0), _seg(0.1)]) is None


def test_quota_righe_fanout_conta_le_righe_da_articoli_multi_ticker():
    segnali = [
        _seg(0.0, n_ticker=3),
        _seg(0.0, n_ticker=1),
        _seg(0.0, n_ticker=2),
        _seg(0.0, n_ticker=1),
    ]
    assert quota_righe_fanout(segnali) == 0.5


def test_il_fan_out_degree_non_influenza_la_causa():
    """Q3 esplicito: il fan-out e' metrica propria (#169), non un input di
    OFF_TOPIC. Stesse righe, solo n_ticker diverso -> stessa causa."""
    base = _cand("AZN", [_seg(0.0, "org_lookup", "AZN holds steady", n_ticker=1)])
    fanout = _cand("AZN", [_seg(0.0, "org_lookup", "AZN holds steady", n_ticker=9)])
    assert classify_miss_candidate(base) == classify_miss_candidate(fanout) == "THIN_NEUTRAL"


def test_quota_persistita_su_ogni_candidato_classificato():
    out = classify_miss_candidates([
        _cand("AZN", [_seg(0.0, "org_lookup", "AZN holds steady", n_ticker=4)]),
        _cand("BA", [], news_count=0),
    ])
    assert out[0]["quota_righe_fanout"] == 1.0
    assert out[1]["quota_righe_fanout"] is None
