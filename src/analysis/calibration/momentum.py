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


def select_top(scores: dict[str, float], n_top: int) -> tuple[str, ...]:
    """I migliori n per punteggio, con pareggio risolto alfabeticamente.

    Il tie-break alfabetico non e' estetica: senza, l'ordine dipende
    dall'iterazione del dizionario e due esecuzioni sugli stessi dati possono
    dare panieri diversi. Una calibrazione deve essere riproducibile.

    Nota: NON filtra i punteggi negativi. Long-only significa che non shortiamo
    i perdenti, non che escludiamo i vincitori relativi in un mercato in calo.
    Il filtro di momentum assoluto e' un'ipotesi a se' (dual momentum), non un
    default silenzioso.
    """
    ordinati = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return tuple(sym for sym, _ in ordinati[:n_top])


def equal_weighted_return(
    symbols: tuple[str, ...],
    closes: dict[str, dict[int, float]],
    start: int,
    end: int,
) -> float | None:
    """Media aritmetica dei rendimenti dei componenti fra due posizioni.

    Equipesato significa media dei RENDIMENTI, non rendimento di un indice
    pesato per prezzo: due titoli a 10$ e 1000$ contribuiscono uguale.

    Un simbolo senza entrambi i prezzi viene SALTATO, non contato come zero:
    contarlo come zero significherebbe affermare che non si e' mosso, che e'
    un'affermazione falsa. Restituisce None se nessun simbolo e' valutabile.
    """
    rendimenti: list[float] = []
    for sym in symbols:
        serie = closes.get(sym, {})
        p0 = serie.get(start)
        p1 = serie.get(end)
        if p0 is None or p1 is None or p0 == 0:
            continue
        rendimenti.append(p1 / p0 - 1.0)
    if not rendimenti:
        return None
    return sum(rendimenti) / len(rendimenti)
