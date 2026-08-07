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


def summarize_excess(excess: list[float]) -> dict:
    """Statistiche riassuntive di una serie di extra-rendimenti periodali.

    ATTENZIONE ALL'INTERPRETAZIONE. La pre-registrazione
    (docs/evidence/PREREGISTRAZIONE_BACKTEST_S1.md) impone |t| >= 3.0 perche'
    con le decine di anomalie testate in letteratura la soglia convenzionale di
    1.96 produce in maggioranza falsi positivi (Harvey-Liu-Zhu 2016).

    E impone anche questo: se il t non raggiunge 3.0, l'esito da registrare e'
    "NON DIMOSTRATA su questo campione", non "falsa". Con l'effetto atteso
    (~0.3%/mese) servono oltre 100 mesi per raggiungere t=3 anche se l'effetto
    fosse reale e stabile: l'assenza di significativita' qui e' attesa per
    costruzione, non e' una scoperta.

    L'intervallo di confidenza usa l'approssimazione normale (1.96), valida per
    n >= ~30. Sotto quella soglia va letto come indicativo.
    """
    n = len(excess)
    if n == 0:
        return {"n": 0, "media": None, "dev_std": None, "t_stat": None,
                "ci_low": None, "ci_high": None, "supera_soglia_3": False}

    media = sum(excess) / n
    if n < 2:
        return {"n": n, "media": media, "dev_std": None, "t_stat": None,
                "ci_low": None, "ci_high": None, "supera_soglia_3": False}

    dev = statistics.stdev(excess)
    if dev == 0:
        return {"n": n, "media": media, "dev_std": dev, "t_stat": None,
                "ci_low": None, "ci_high": None, "supera_soglia_3": False}

    se = dev / math.sqrt(n)
    t = media / se
    return {
        "n": n,
        "media": media,
        "dev_std": dev,
        "t_stat": t,
        "ci_low": media - 1.96 * se,
        "ci_high": media + 1.96 * se,
        "supera_soglia_3": abs(t) >= 3.0,
    }
