"""Causa deterministica del miss (#208).

Assegna a ogni candidato una delle 5 categorie della carta di osservazione,
derivate SOLO dai dati che il dossier gia' possiede (news_count, segnali,
in_portofoglio). Puro: nessun I/O. Le soglie sono parametri espliciti, mai
default impliciti, cosi' la classificazione e' riproducibile e la tabella del
report alpha-miner puo' essere calcolata meccanicamente.

Tassonomia (ordine di applicazione):
    IN_PORTAFOGLIO  — candidato gia' in posizione (non dovrebbe mai capitare dopo
                     il filtro di compute_miss_candidates, ma la tassonomia lo
                     prevede e il classificatore non assorbe l'eccezione)
    NO_NEWS         — news_count == 0
    NO_SIGNAL       — news_count > 0 ma segnali vuoto
    THIN_NEUTRAL    — segnali presenti, |score| massimo < soglia_thin, e il testo
                     scorato parla del ticker (o la provenienza non e' nota)
    OFF_TOPIC       — stesso regime di THIN_NEUTRAL, ma il testo scorato e'
                     ispezionabile (org_lookup) e NON cita il ticker (#244)
    OFF_TOPIC_NON_DECIDIBILE — stesso regime, ma il testo scorato non e'
                     ispezionabile (source_metadata: snippet troncato) (#244)
    BELOW_GATE      — |score| massimo in [soglia_thin, soglia_gate)
    NON_CLASSIFICATO — |score| massimo >= soglia_gate (segnale sopra il gate:
                     o non era un miss, o il dossier non sta filtrando bene)

Le soglie di default sono 0.05 (thin/neutral) e 0.30 (baseline feedback
entry_threshold di S4 — vedi `src/strategies/s4/config.py`). 0.30 e' congelato
dalla carta di osservazione #171; se cambia e' una taratura e questa funzione
riceve il valore aggiornato come argomento.

#208: `soglia_gate` DEVE essere letta da Redis (feedback:entry_threshold:S4)
al momento di costruzione del dossier. Tra il 07-31 e il 08-07 il ratchet
aveva spinto il gate a 0.40-0.45 (#191): usare il default fisso 0.30 avrebbe
mis-classificato come NON_CLASSIFICATO tutti i candidati con score fra 0.30
e la soglia effettiva — proprio nei giorni che il dossier deve spiegare.
L'orchestratore (`scripts/alpha_miner_dossier.py`) la passa come argomento;
la fallback al baseline e' compito dell'orchestratore, non di questo modulo.

#244: THIN_NEUTRAL confondeva due risposte OPPOSTE alla domanda di uscita n.1 —
«esiste una notizia su questo titolo ed e' poco informativa» (il sentiment
editoriale non ha alpha) e «non esiste una notizia su questo titolo, ne stiamo
scorando una su un'altra societa'» (difetto della pipeline). Il bucket viene
quindi spezzato in tre, SENZA toccare nessuna soglia (freeze #171): la
partizione avviene tutta dentro la regione |score| < soglia_thin, che resta
definita esattamente come prima.

La decidibilita' dipende dalla provenienza della riga (`extraction_method`):
    org_lookup      — GDELT GKG costruisce l'item con `body = title`
                      (`src/connectors/gdelt_gkg.py`, _parse_csv_row): il testo
                      scorato E' il titolo, quindi «il ticker compare nel testo
                      scorato?» e' verificabile sul dato persistito.
    source_metadata — Alpaca/Benzinga/Finnhub scorano uno snippet troncato che
                      il dossier non conserva: la domanda NON e' decidibile, e
                      dichiararlo e' piu' onesto che indovinare. Serve QX-01
                      (#30) per chiudere questo ramo.

Il fan-out degree (`n_ticker_articolo`) e' persistito accanto al segnale ma NON
entra nella decisione di OFF_TOPIC: e' una metrica propria (#169, ranker che
prende l'ultimo segnale per ticker), e usarla come proxy della rilevanza
renderebbe circolare la misura che #244 vuole leggere.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import TypedDict


class SignalEvidence(TypedDict, total=False):
    """Contratto minimo del segnale che il classificatore guarda."""

    ora: str
    score: float
    fallback: bool
    # #244 — provenienza della riga scorata. Opzionali: se assenti il
    # classificatore ricade sul comportamento pre-#244 (THIN_NEUTRAL).
    extraction_method: str
    testo_scorato: str
    n_ticker_articolo: int


# I candidati del dossier sono dict con i campi di MissCandidate, ma TypedDict
# non ammette chiavi riservate (`return` lo e'). Si dichiarano via docstring e
# il modulo vi accede con .get(). La forma e' compatibile con
# src/analysis/dossier/market.py:MissCandidate.
MissCandidate = dict
"""Candidato grezzo: {symbol, return, news_count, segnali, in_portafoglio}."""

ClassifiedCandidate = dict
"""Candidato con il campo `causa` aggiunto dal classificatore."""


# Nomi delle cause: l'ordine in CAUSE_ORDER determina la dominante in caso di
# pareggio (esclude NON_CLASSIFICATO, che non e' una causa del fenomeno).
CAUSE_ORDER = (
    "NO_NEWS",
    "BELOW_GATE",
    "THIN_NEUTRAL",
    "OFF_TOPIC",
    "OFF_TOPIC_NON_DECIDIBILE",
    "NO_SIGNAL",
    "IN_PORTAFOGLIO",
)
NON_CLASSIFICATO = "NON_CLASSIFICATO"

# I tre bucket in cui #244 spezza la vecchia THIN_NEUTRAL.
THIN_NEUTRAL = "THIN_NEUTRAL"
OFF_TOPIC = "OFF_TOPIC"
OFF_TOPIC_NON_DECIDIBILE = "OFF_TOPIC_NON_DECIDIBILE"
BUCKET_THIN = (THIN_NEUTRAL, OFF_TOPIC, OFF_TOPIC_NON_DECIDIBILE)

# Provenienze per cui il testo scorato e' interamente persistito (l'item viene
# costruito con `body = title`, verificato in src/connectors/gdelt_gkg.py e
# gdelt_doc.py): la domanda «il ticker compare nel testo scorato?» ha risposta.
METODI_DECIDIBILI = frozenset({"org_lookup", "gdelt_doc"})
# Provenienze che scorano uno snippet troncato che il dossier non conserva.
METODI_NON_DECIDIBILI = frozenset({"source_metadata"})
# Un `extraction_method` ASSENTE e' il caso dei dossier scritti prima di #244:
# ricade sul comportamento storico (THIN_NEUTRAL), non su non-decidibile, cosi'
# che la riclassificazione dei giorni gia' osservati sia una scelta esplicita
# del backfill e non un effetto collaterale.

DEFAULT_SOGLIA_THIN = 0.05
DEFAULT_SOGLIA_GATE = 0.30


def _max_score(segnali: list[SignalEvidence]) -> float:
    """Massimo |score| sui segnali del candidato. 0.0 se la lista e' vuota."""
    if not segnali:
        return 0.0
    return max(abs(float(s.get("score", 0.0))) for s in segnali)


def ticker_nel_testo(symbol: str, testo: str) -> bool:
    """True se `symbol` compare come token nel testo scorato.

    Confine non-alfanumerico su entrambi i lati: «$NVDA», «NVDA's» e «(NVDA)»
    contano; «NVDAX» no. Case-insensitive perche' i titoli GDELT arrivano anche
    in maiuscolo pieno. Deliberatamente NON prova a risolvere il nome della
    societa' («Nvidia» senza ticker): un matcher di ragione sociale e' un
    componente a sua volta da validare (QX-01, #30), e sovrastimerebbe
    THIN_NEUTRAL — cioe' sottostimerebbe proprio il difetto che #244 misura.
    Il risultato e' un limite INFERIORE su OFF_TOPIC.
    """
    if not symbol or not testo:
        return False
    pattern = rf"(?<![A-Za-z0-9]){re.escape(symbol)}(?![A-Za-z0-9])"
    return re.search(pattern, testo, re.IGNORECASE) is not None


def _verdetto_segnale(segnale: SignalEvidence, symbol: str) -> str:
    """Verdetto di rilevanza di UNA riga scorata: uno di

    `in_tema` | `off_topic` | `non_decidibile` | `senza_provenienza`.
    """
    metodo = str(segnale.get("extraction_method") or "").strip()
    if not metodo:
        return "senza_provenienza"
    if metodo in METODI_NON_DECIDIBILI:
        return "non_decidibile"
    if metodo not in METODI_DECIDIBILI:
        # Provenienza nota al dato ma non a questo modulo: non decidibile e'
        # l'unica risposta onesta (meglio di assumere che sia in tema).
        return "non_decidibile"
    testo = str(segnale.get("testo_scorato") or "")
    if not testo:
        # org_lookup senza testo persistito: decidibile in linea di principio,
        # non su questo dato. Va nel bucket dell'ignoranza, non in THIN_NEUTRAL.
        return "non_decidibile"
    return "in_tema" if ticker_nel_testo(symbol, testo) else "off_topic"


def _bucket_thin(candidato: MissCandidate, segnali: list[SignalEvidence]) -> str:
    """Spezza la regione |score| < soglia_thin nei tre bucket di #244.

    Precedenza: basta UNA riga in tema perche' il candidato resti THIN_NEUTRAL
    (esiste davvero una notizia poco informativa su quel titolo). OFF_TOPIC si
    dichiara solo se NESSUNA riga decidibile cita il ticker: e' un limite
    inferiore, coerente con `ticker_nel_testo`.

    Nessuna soglia entra qui dentro: la partizione e' interna a un bucket la cui
    frontiera resta quella congelata da #171.
    """
    symbol = str(candidato.get("symbol") or "")
    verdetti = {_verdetto_segnale(s, symbol) for s in segnali}
    if "in_tema" in verdetti:
        return THIN_NEUTRAL
    if "off_topic" in verdetti:
        return OFF_TOPIC
    if "non_decidibile" in verdetti:
        return OFF_TOPIC_NON_DECIDIBILE
    return THIN_NEUTRAL  # nessuna provenienza persistita: comportamento pre-#244


def quota_righe_fanout(segnali: list[SignalEvidence]) -> float | None:
    """Quota di righe scorate che nascono da un articolo multi-ticker (#244 Q3).

    None se nessuna riga porta `n_ticker_articolo`: assente != zero, e un 0.0
    inventato falserebbe la serie che #169 deve leggere. NON e' un input della
    classificazione — vedi la docstring di modulo.
    """
    noti = [s for s in segnali if s.get("n_ticker_articolo") is not None]
    if not noti:
        return None
    fanout = sum(1 for s in noti if int(s.get("n_ticker_articolo") or 0) >= 2)
    return fanout / len(noti)


def classify_miss_candidate(
    candidato: MissCandidate,
    soglia_thin: float = DEFAULT_SOGLIA_THIN,
    soglia_gate: float = DEFAULT_SOGLIA_GATE,
) -> str:
    """Classifica UN candidato. Esportata anche singolarmente per i test."""
    if candidato.get("in_portafoglio"):
        return "IN_PORTAFOGLIO"
    if int(candidato.get("news_count", 0) or 0) == 0:
        return "NO_NEWS"
    segnali = candidato.get("segnali") or []
    if not segnali:
        return "NO_SIGNAL"
    massimo = _max_score(segnali)
    if massimo < soglia_thin:
        return _bucket_thin(candidato, segnali)
    if massimo < soglia_gate:
        return "BELOW_GATE"
    return NON_CLASSIFICATO


def classify_miss_candidates(
    candidati: list[MissCandidate],
    soglia_thin: float = DEFAULT_SOGLIA_THIN,
    soglia_gate: float = DEFAULT_SOGLIA_GATE,
) -> list[ClassifiedCandidate]:
    """Restituisce una copia di `candidati` con il campo `causa` aggiunto.

    Non muta l'input: i candidati originali li riceve gia' l'orchestratore del
    dossier, e questa funzione produce il blocco da serializzare accanto.
    """
    out: list[ClassifiedCandidate] = []
    for c in candidati:
        copia: ClassifiedCandidate = {**c}  # type: ignore[misc]
        copia["causa"] = classify_miss_candidate(
            c, soglia_thin=soglia_thin, soglia_gate=soglia_gate
        )
        # #244 Q3: metrica propria, affiancata alla causa, mai un suo input.
        copia["quota_righe_fanout"] = quota_righe_fanout(c.get("segnali") or [])
        out.append(copia)
    return out


def count_by_cause(candidati: list[ClassifiedCandidate]) -> dict[str, int]:
    """Conteggio per causa, nell'ordine canonico della tassonomia.

    NON_CLASSIFICATO viene incluso se presente (per sorveglianza: se il filtro
    upstream smette di funzionare, il conteggio lo rivela), ma NON entra nella
    gerarchia della dominante.
    """
    counter: Counter[str] = Counter(c["causa"] for c in candidati if "causa" in c)
    # Forza l'ordine canonico + eventuali NON_CLASSIFICATO in coda.
    ordinato: dict[str, int] = {}
    for causa in CAUSE_ORDER:
        if counter.get(causa):
            ordinato[causa] = counter[causa]
    if counter.get(NON_CLASSIFICATO):
        ordinato[NON_CLASSIFICATO] = counter[NON_CLASSIFICATO]
    return ordinato


def dominant_cause(conteggi: dict[str, int]) -> str | None:
    """La causa con piu' occorrenze, oppure None se vuota o in pareggio.

    Il pareggio non e' una forzatura: la carta di osservazione del 2026-08-05
    (NO_NEWS=2, BELOW_GATE=2) mostra che capita, e dichiarare una dominante a
    caso sarebbe esattamente il difetto che la pre-registrazione vuole evitare.
    NON_CLASSIFICATO non concorre: e' strumentazione, non una causa del
    fenomeno.
    """
    filtrati = {k: v for k, v in conteggi.items() if k != NON_CLASSIFICATO}
    if not filtrati:
        return None
    massimo = max(filtrati.values())
    vincitori = [k for k, v in filtrati.items() if v == massimo]
    if len(vincitori) > 1:
        return None
    return vincitori[0]


def cause_del_giorno(candidati: list[ClassifiedCandidate]) -> dict:
    """Blocco `aggregati.cause_del_giorno`: conteggi, dominante, totale.

    Le soglie sono i DEFAULT del modulo: l'orchestratore che le vuole esplicite
    nel dossier deve sovrascriverle dopo la chiamata. Mantenere i default qui
    rende il blocco indipendente dai default del classificatore, cosi' se un
    giorno i default cambiano, la diff dei dossier retro-risulta evidente.
    """
    conteggi = count_by_cause(candidati)
    tutti_segnali = [s for c in candidati for s in (c.get("segnali") or [])]
    return {
        "totale_candidati": len(candidati),
        "conteggi": conteggi,
        "dominante": dominant_cause(conteggi),
        "soglie": {
            "thin": DEFAULT_SOGLIA_THIN,
            "gate": DEFAULT_SOGLIA_GATE,
        },
        # #244 Q3: quota di righe scorate nate da articoli multi-ticker, sul
        # giorno. None finche' il fan-out degree non e' persistito.
        "quota_righe_fanout": quota_righe_fanout(tutti_segnali),
    }
