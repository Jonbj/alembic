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
    THIN_NEUTRAL    — segnali presenti ma |score| massimo < soglia_thin
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
"""

from __future__ import annotations

from collections import Counter
from typing import TypedDict


class SignalEvidence(TypedDict, total=False):
    """Contratto minimo del segnale che il classificatore guarda."""

    ora: str
    score: float
    fallback: bool


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
CAUSE_ORDER = ("NO_NEWS", "BELOW_GATE", "THIN_NEUTRAL", "NO_SIGNAL", "IN_PORTAFOGLIO")
NON_CLASSIFICATO = "NON_CLASSIFICATO"

DEFAULT_SOGLIA_THIN = 0.05
DEFAULT_SOGLIA_GATE = 0.30


def _max_score(segnali: list[SignalEvidence]) -> float:
    """Massimo |score| sui segnali del candidato. 0.0 se la lista e' vuota."""
    if not segnali:
        return 0.0
    return max(abs(float(s.get("score", 0.0))) for s in segnali)


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
        return "THIN_NEUTRAL"
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
    return {
        "totale_candidati": len(candidati),
        "conteggi": conteggi,
        "dominante": dominant_cause(conteggi),
        "soglie": {
            "thin": DEFAULT_SOGLIA_THIN,
            "gate": DEFAULT_SOGLIA_GATE,
        },
    }
