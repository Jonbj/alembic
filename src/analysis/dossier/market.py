"""Metriche di mercato del dossier.

Modulo puro: riceve prezzi e conteggi gia' caricati, non tocca rete ne' DB.
"""

from __future__ import annotations

import statistics
from typing import TypedDict


class SignalEvidence(TypedDict):
    """Segnale disponibile per spiegare un candidato miss."""

    ora: str
    score: float
    fallback: bool


class MarketMetrics(TypedDict):
    """Metriche deterministiche della watchlist per una giornata."""

    rendimenti: dict[str, float]
    dispersione_sigma: float | None
    mover_3pct: int
    up: int
    down: int
    watchlist_zero_news: int
    simboli_senza_dati: list[str]


MissCandidate = TypedDict(
    "MissCandidate",
    {
        "symbol": str,
        "return": float,
        "news_count": int,
        "segnali": list[SignalEvidence],
        "in_portafoglio": bool,
    },
)
MissCandidate.__doc__ = "Evidenza grezza su un mover non presente nel portafoglio."


def compute_market(
    closes: dict[str, tuple[float | None, float | None]],
    news_counts: dict[str, int],
    soglia_mover: float,
) -> MarketMetrics:
    """Calcola le metriche di mercato della giornata.

    Args:
        closes: {simbolo: (close_precedente, close_del_giorno)}. Un None su uno dei
            due valori significa dato mancante: il simbolo viene escluso dai
            rendimenti e riportato in "simboli_senza_dati". Non si inventa un valore.
        news_counts: {simbolo: numero di articoli quel giorno}. Un simbolo assente
            conta come zero.
        soglia_mover: soglia inclusiva su |rendimento| per contare come mover.

    Returns:
        dict con rendimenti, dispersione_sigma, mover_3pct, up, down,
        watchlist_zero_news, simboli_senza_dati.
    """
    rendimenti: dict[str, float] = {}
    senza_dati: list[str] = []

    for sym, (prec, oggi) in closes.items():
        if prec is None or oggi is None or prec == 0:
            senza_dati.append(sym)
            continue
        rendimenti[sym] = oggi / prec - 1.0

    valori = list(rendimenti.values())
    up = sum(1 for r in valori if r >= soglia_mover)
    down = sum(1 for r in valori if r <= -soglia_mover)

    # stdev campionaria: non definita sotto i due campioni -> None, non 0.0
    dispersione = statistics.stdev(valori) if len(valori) >= 2 else None

    zero_news = sum(1 for sym in closes if news_counts.get(sym, 0) == 0)

    return {
        "rendimenti": rendimenti,
        "dispersione_sigma": dispersione,
        "mover_3pct": up + down,
        "up": up,
        "down": down,
        "watchlist_zero_news": zero_news,
        "simboli_senza_dati": sorted(senza_dati),
    }


def compute_miss_candidates(
    rendimenti: dict[str, float],
    news_counts: dict[str, int],
    segnali: dict[str, list[SignalEvidence]],
    in_portafoglio: set[str],
    soglia_mover: float,
) -> list[MissCandidate]:
    """Raccoglie l'evidenza sui mover NON in portafoglio.

    Non classifica: la categoria del miss (NO_NEWS, THIN_NEUTRAL, ...) richiede di
    leggere il testo degli articoli ed e' compito della sessione, non di questo modulo.

    Ordinati per |rendimento| decrescente: i candidati piu' costosi per primi.
    """
    candidates: list[MissCandidate] = [
        {
            "symbol": sym,
            "return": ret,
            "news_count": news_counts.get(sym, 0),
            "segnali": segnali.get(sym, []),
            "in_portafoglio": False,
        }
        for sym, ret in rendimenti.items()
        if abs(ret) >= soglia_mover and sym not in in_portafoglio
    ]
    return sorted(
        candidates, key=lambda candidate: abs(candidate["return"]), reverse=True
    )
