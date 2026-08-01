"""Motore di calibrazione del momentum. Modulo puro: nessun I/O.

Le funzioni ragionano su POSIZIONI in una lista ordinata di giorni di borsa, non
su date di calendario: "lookback 252" in letteratura significa 252 giorni di
BORSA, e sottrarre giorni di calendario darebbe un risultato diverso e sbagliato.
"""
from __future__ import annotations

import math
import statistics


def momentum_scores(
    closes: dict[str, dict[int, float]],
    idx: int,
    lookback: int,
    skip: int,
) -> dict[str, float]:
    """Rendimento di formazione fra due posizioni della serie.

    Convenzione 12-2: lookback=242, skip=21 (circa 12 mesi saltando l'ultimo).

    Args:
        closes: {simbolo: {posizione: prezzo di chiusura}}.
        idx: posizione della data di valutazione.
        lookback: ampiezza della finestra di formazione, in giorni di borsa.
        skip: giorni di borsa recenti da escludere.

    Returns:
        {simbolo: rendimento di formazione}. Un simbolo senza entrambi gli
        estremi, o con prezzo iniziale nullo, viene ESCLUSO — mai stimato.
    """
    fine = idx - skip
    inizio = fine - lookback
    if inizio < 0:
        return {}

    out: dict[str, float] = {}
    for sym, serie in closes.items():
        p0 = serie.get(inizio)
        p1 = serie.get(fine)
        if p0 is None or p1 is None or p0 == 0:
            continue
        out[sym] = p1 / p0 - 1.0
    return out
