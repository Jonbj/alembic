"""P&L economico della carta di osservazione (#278, M3 della roadmap consolidata).

Modulo puro: riceve posizioni e barre gia' caricate, non tocca rete ne' DB.
Nessuna formula vive nell'orchestratore: tutto passa di qui.

DEFINIZIONE (docs/evidence/OBSERVATION_CHARTER.md, "Definizione: P&L economico")::

    Per ogni posizione, il movimento di prezzo attribuibile alla finestra: si
    marca dal close del primo giorno della finestra (o dal prezzo di ingresso,
    se successivo) al prezzo corrente (o al prezzo di uscita, se anteriore),
    moltiplicato per la quantita'. Somma su tutte le posizioni, aperte e chiuse.

Conseguenze tradotte in codice:

* ``mark_from`` = close del primo giorno della finestra per le posizioni gia'
  aperte (entry ON o prima del primo giorno); = entry_price solo se l'ingresso
  e' *strettamente successivo* al primo giorno ("se successivo"). L'intraday
  del giorno di ingresso, quando questo coincide col primo giorno, NON entra
  nel P&L economico: la baseline e' il close stesso, per costruzione.
* ``mark_to`` al giorno D = exit_price se la posizione e' uscita ON o prima di
  D ("anteriore"), altrimenti il close di D (prezzo corrente a fine giornata).
* La serie cumulata per posizione e' (mark_to(D) - mark_from) * qty; quella
  giornaliera e' la prima differenza della cumulata, quindi il giorno 1 vale 0
  per le posizioni pre-finestra (la baseline e' il close del primo giorno).

Perche' esiste (e non si usa il realizzato): il P&L realizzato di S1 e'
strutturalmente distorto -- la sua regola d'uscita chiude solo le posizioni che
hanno perso rango momentum, le vincenti restano aperte (#134). La carta impone
di ignorare il realizzato e giudicare S1 sull'economico.

ATTRIBUZIONE (criterio di accettazione #278): una posizione senza attribuzione
di strategia NON viene assegnata arbitrariamente a S1. L'orchestratore del
dossier legacy usa ``COALESCE(stop_strategy, CASE WHEN signal_id IS NOT NULL
THEN 'S4' ELSE 'S1' END)`` -- il ramo ``ELSE 'S1'`` e' proprio l'assegnazione
arbitraria che la carta vieta. Qui:

* ``stop_strategy`` presente -> quella strategia (fonte autorevole: vedi
  incidente trade 361 del 2026-07-17 in portfolio_scheduler, dove signal_id
  avrebbe etichettato S1 un BUY S4 genuino);
* altrimenti ``signal_id`` presente -> ``S4`` (trade news-driven);
* altrimenti -> ``CONTAMINAZIONE``, bucket esposto a se' stante.

MISSINGNESS: non si inventano prezzi. Una posizione pre-finestra senza il close
del primo giorno e' non marcabile per l'intera finestra (serie tutta ``None``,
contata in ``missing``). Un giorno intermedio senza barra viene carry-forward
del mark (contributo giornaliero 0 quel giorno, il mark riprende quando la
barra torna) -- e' l'unica convenzione deterministica che non introduce un
prezzo fittizio e non spezza la continuita' della cumulata.
"""

from __future__ import annotations

from datetime import date
from typing import TypedDict


# Barre giornaliere: {giorno: {simbolo: close}}. Un simbolo assente un dato
# giorno conta come barra mancante (carry-forward), non come prezzo zero.
Closes = dict[date, dict[str, float]]


class Position(TypedDict):
    """Campi di una posizione necessari al P&L economico.

    ``stop_strategy`` e ``signal_id`` sono le due fonti di attribuzione;
    ``entry_date``/``exit_date`` sono date di borsa (UTC date, come fa
    l'orchestratore del dossier), non timestamp.
    """

    symbol: str
    stop_strategy: str | None
    signal_id: int | None
    entry_price: float | None
    entry_date: date | None
    exit_price: float | None
    exit_date: date | None
    qty: float | None


CONTAMINAZIONE = "CONTAMINAZIONE"
STRATEGIE = ("S1", "S4", CONTAMINAZIONE)


def attribute_strategy(stop_strategy: str | None, signal_id: int | None) -> str:
    """Attribuisce una posizione a S1 / S4 / CONTAMINAZIONE.

    Mai il fallback S1 del dossier legacy: una posizione senza stop_strategy e
    senza signal_id e' contaminazione, non S1 per default.
    """
    if stop_strategy:
        return stop_strategy
    if signal_id is not None:
        return "S4"
    return CONTAMINAZIONE


def mark_from(pos: Position, window_start: date, closes: Closes) -> float | None:
    """Prezzo di partenza del mark.

    Close del primo giorno della finestra per le posizioni aperte ON o prima;
    entry_price solo per ingressi *strettamente successivi* al primo giorno.
    ``None`` se il close di riferimento manca (posizione non marcabile).
    """
    if pos["entry_date"] is not None and pos["entry_date"] > window_start:
        return pos["entry_price"]
    return closes.get(window_start, {}).get(pos["symbol"])


def position_series(
    pos: Position,
    trading_days: list[date],
    window_start: date,
    closes: Closes,
) -> dict[date, float | None]:
    """Serie cumulata del P&L economico di una posizione per ogni giorno della finestra.

    ``None`` su ogni giorno se la posizione non e' marcabile (mark_from None o
    campi obbligatori mancanti). Carry-forward del mark sui giorni senza barra.
    """
    mf = mark_from(pos, window_start, closes)
    qty = pos["qty"]
    if (
        mf is None
        or qty is None
        or pos["entry_price"] is None
        or pos["entry_date"] is None
    ):
        return {d: None for d in trading_days}

    series: dict[date, float | None] = {}
    last_mark = mf  # mark corrente, per il carry-forward dei giorni senza barra
    for d in trading_days:
        if d < pos["entry_date"]:
            # posizione non ancora aperta: contributo zero
            series[d] = 0.0
            continue
        if pos["exit_date"] is not None and pos["exit_date"] <= d:
            target = pos["exit_price"]
        else:
            target = closes.get(d, {}).get(pos["symbol"])
        if target is None:
            # barra mancante: il mark resta l'ultimo noto (daily 0 quel giorno)
            series[d] = (last_mark - mf) * qty
            continue
        last_mark = target
        series[d] = (target - mf) * qty
    return series


def _esclusa(pos: Position) -> bool:
    """Una posizione e' esclusa dal calcolo se manca un campo obbligatorio o se
    e' chiusa senza exit_price (non marcabile all'uscita)."""
    return (
        pos["entry_price"] is None
        or pos["qty"] is None
        or pos["entry_date"] is None
        or (pos["exit_date"] is not None and pos["exit_price"] is None)
    )


def compute_economic_pnl(
    positions: list[Position],
    trading_days: list[date],
    window_start: date,
    closes: Closes,
) -> dict:
    """Serie economica giornaliera e cumulata per S1 / S4 / CONTAMINAZIONE / BOOK.

    Args:
        positions: posizioni aperte in qualche punto della finestra.
        trading_days: giorni di borsa della finestra, in ordine crescente.
        window_start: primo giorno della finestra (close di riferimento).
        closes: {giorno: {simbolo: close}}.

    Returns:
        dict con ``cumulato``/``giornaliero``/``missing`` ({strategia: {giorno: valore}}),
        ``capital_base`` ({strategia: notionale al mark del primo giorno}),
        ``esclusi`` (conteggio posizioni non calcolabili) e ``numerosita``
        ({strategia: numero posizioni}). ``BOOK`` = S1 + S4 + CONTAMINAZIONE.
    """
    giorni = sorted(trading_days)
    buckets: dict[str, list[Position]] = {s: [] for s in STRATEGIE}
    esclusi = 0
    for pos in positions:
        if _esclusa(pos):
            esclusi += 1
            continue
        buckets[attribute_strategy(pos.get("stop_strategy"), pos.get("signal_id"))].append(pos)

    serie_per_strat = {
        s: [position_series(p, giorni, window_start, closes) for p in buckets[s]]
        for s in STRATEGIE
    }

    cumulato: dict[str, dict[date, float]] = {}
    giornaliero: dict[str, dict[date, float]] = {}
    missing: dict[str, dict[date, int]] = {}
    capital_base: dict[str, float] = {}

    for s in STRATEGIE:
        cumulato[s] = {}
        giornaliero[s] = {}
        missing[s] = {}
        prev = 0.0
        for d in giorni:
            valori = [ps[d] for ps in serie_per_strat[s]]
            marcabili = [v for v in valori if v is not None]
            cumulato[s][d] = sum(marcabili)
            giornaliero[s][d] = cumulato[s][d] - prev
            prev = cumulato[s][d]
            missing[s][d] = len(valori) - len(marcabili)
        # base di capitale al mark del primo giorno: somma di mark_from * qty
        # sulle posizioni marcabili (quelle con close del primo giorno disponibile).
        cb = 0.0
        for p in buckets[s]:
            mf = mark_from(p, window_start, closes)
            if mf is not None and p["qty"] is not None:
                cb += mf * p["qty"]
        capital_base[s] = cb

    # BOOK = somma sui tre bucket (contaminazione inclusa, non nascosta)
    cumulato["BOOK"] = {}
    giornaliero["BOOK"] = {}
    missing["BOOK"] = {}
    prev = 0.0
    for d in giorni:
        c = cumulato["S1"][d] + cumulato["S4"][d] + cumulato[CONTAMINAZIONE][d]
        cumulato["BOOK"][d] = c
        giornaliero["BOOK"][d] = c - prev
        prev = c
        missing["BOOK"][d] = (
            missing["S1"][d] + missing["S4"][d] + missing[CONTAMINAZIONE][d]
        )
    capital_base["BOOK"] = (
        capital_base["S1"] + capital_base["S4"] + capital_base[CONTAMINAZIONE]
    )

    return {
        "cumulato": cumulato,
        "giornaliero": giornaliero,
        "missing": missing,
        "capital_base": capital_base,
        "esclusi": esclusi,
        "numerosita": {s: len(buckets[s]) for s in STRATEGIE},
    }