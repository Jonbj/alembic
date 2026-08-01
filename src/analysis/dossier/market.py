"""Metriche di mercato del dossier.

Modulo puro: riceve prezzi e conteggi gia' caricati, non tocca rete ne' DB.
"""
from __future__ import annotations

import statistics


def compute_market(
    closes: dict[str, tuple[float | None, float | None]],
    news_counts: dict[str, int],
    soglia_mover: float,
) -> dict:
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
