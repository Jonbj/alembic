"""P&L totale per sleeve: realized + mark-to-market delle aperte (issue #210).

Modulo puro: riceve posizioni (chiuse + aperte) e un dict ``current_prices``
{symbol: prezzo_corrente}. Non tocca rete ne' DB. Complementare a
``economic_pnl``: stessa attribuzione per sleeve, stesso divieto di fallback
S1 arbitrario (criterio #278), ma **misura diversa** -- somma il realized
chiuso nella finestra al mark-to-market delle posizioni ancora aperte.

PERCHE' ESISTE (issue #210): il P&L realizzato di S1 e' un campione
selezionato avversariamente dalla regola d'uscita (#165) -- S1 chiude solo
quando una posizione perde rango momentum, mentre le vincenti restano
aperte. Il P&L economico (#278, mark-from-first-day) corregge la lettura ma
non dice cosa si e' effettivamente guadagnato/perduto: e' mark su tutta la
finestra, indipendentemente dall'uscita.

Il P&L totale qui calcolato affianca al realized la valutazione mark-to-market
delle aperte al prezzo corrente: e' la metrica che la issue #210 chiede di
mettere accanto al realized per il verdetto del 28/09. Le due letture --
realized da solo, e realized+MTMark -- possono divergere molto, ed e'
proprio la divergenza la firma dell'asimmetria di selezione.

ATTRIBUZIONE: delega a ``economic_pnl.attribute_strategy`` (stesso criterio
del dossier: ``stop_strategy`` se presente, altrimenti ``signal_id`` -> ``S4``,
altrimenti ``CONTAMINAZIONE``). Niente fallback ``S1`` arbitrario.

DEFINIZIONE OPERATIVA:

* **realized** (per posizione): ``net_pnl`` se la posizione e' chiusa dentro
  la finestra (``exit_date IS NOT None AND exit_date >= window_start``).
  Realized = 0 per le posizioni aperte o chiuse prima della finestra, e per
  le chiuse senza ``net_pnl`` (dato mancante, non uno zero di realizzo).
* **mark_to_market_open** (per posizione): ``(current_price - entry_price) *
  qty`` se la posizione e' aperta (``exit_date IS None``) **e** il prezzo
  corrente e' disponibile per quel simbolo. Se mancano ``entry_price`` o
  ``qty`` o ``current_price``, la posizione e' "non marcabile" e il MTMark
  vale 0 -- il conteggio va in ``n_open_unmarked`` cosi' la metrica non
  nasconde la copertura.
* **total** (per sleeve) = ``realized + mark_to_market_open``. ``BOOK`` =
  ``S1 + S4 + CONTAMINAZIONE``.

Compatibilita' col freeze #171: pura misura, non tocca nessuna taratura
(esattamente come il P&L economico di #278).
"""

from __future__ import annotations

from datetime import date
from typing import TypedDict

from src.analysis.dossier.economic_pnl import (
    CONTAMINAZIONE,
    STRATEGIE,
    attribute_strategy,
)


# Prezzi correnti per simbolo: {symbol: prezzo_corrente}. Simboli assenti non
# sono MTMark-zero, sono "non marcabili" e vanno contati in ``n_open_unmarked``.
CurrentPrices = dict[str, float]


class Position(TypedDict, total=False):
    """Campi di una posizione necessari al P&L totale.

    ``net_pnl`` e' obbligatorio per il realized ma puo' essere None se la
    riga del DB e' stata scritta senza (vedi migration 016). In quel caso
    la posizione resta nel conteggio ma non contribuisce al realized.
    """

    symbol: str
    stop_strategy: str | None
    signal_id: int | None
    entry_price: float | None
    entry_date: date | None
    exit_price: float | None
    exit_date: date | None
    net_pnl: float | None
    qty: float | None


class SleevePnl(TypedDict):
    realized: float
    mark_to_market_open: float
    total: float
    n_closed: int
    n_open_marked: int
    n_open_unmarked: int


def _empty_sleeve() -> SleevePnl:
    """Bucket vuoto: tutte le metriche a zero, conteggi a 0."""
    return {
        "realized": 0.0,
        "mark_to_market_open": 0.0,
        "total": 0.0,
        "n_closed": 0,
        "n_open_marked": 0,
        "n_open_unmarked": 0,
    }


def position_realized(pos: Position, window_start: date) -> float:
    """Realized di una singola posizione sulla finestra.

    Realized = ``net_pnl`` se la posizione e' chiusa nella finestra
    (``exit_date IS NOT None AND exit_date >= window_start``). Tutti gli
    altri casi restituiscono 0: la posizione o e' ancora aperta (vivra' nel
    MTMark), o e' stata chiusa prima della finestra (fuori perimetro), o
    non ha un ``net_pnl`` (dato mancante).
    """
    if pos.get("exit_date") is None:
        return 0.0
    if pos["exit_date"] < window_start:
        return 0.0
    net = pos.get("net_pnl")
    return float(net) if net is not None else 0.0


def position_mark_to_market(
    pos: Position, current_prices: CurrentPrices
) -> float | None:
    """Mark-to-market di una singola posizione aperta.

    ``None`` se la posizione non e' marcabile: chiusa, o senza ``entry_price`` /
    ``qty``, o senza prezzo corrente per quel simbolo. Il chiamante distingue
    "non marcabile" (None, contato in ``n_open_unmarked``) da MTMark-zero
    (prezzo corrente == entry_price, contato in ``n_open_marked``).
    """
    if pos.get("exit_date") is not None:
        # gia' chiusa: il realized la descrive
        return None
    entry_price = pos.get("entry_price")
    qty = pos.get("qty")
    if entry_price is None or qty is None:
        return None
    symbol = pos.get("symbol")
    if symbol is None or symbol not in current_prices:
        return None
    return (current_prices[symbol] - entry_price) * qty


def compute_total_pnl(
    positions: list[Position],
    current_prices: CurrentPrices,
    window_start: date,
) -> dict[str, SleevePnl]:
    """Per ogni sleeve (S1, S4, CONTAMINAZIONE, BOOK) realizza la triade.

    Args:
        positions: posizioni (chiuse o aperte) della finestra. Quelle chiuse
            *prima* di ``window_start`` sono ammesse ma ignorate (realized=0,
            MTMark=None).
        current_prices: ``{symbol: prezzo_corrente}``. Le posizioni aperte
            senza prezzo corrente vanno in ``n_open_unmarked``.
        window_start: primo giorno della finestra di realized (inclusivo).

    Returns:
        ``{strategia: SleevePnl}`` con le chiavi S1, S4, CONTAMINAZIONE, BOOK.
        BOOK = somma delle tre.
    """
    buckets: dict[str, SleevePnl] = {s: _empty_sleeve() for s in STRATEGIE}

    for pos in positions:
        sleeve = attribute_strategy(pos.get("stop_strategy"), pos.get("signal_id"))
        if sleeve == CONTAMINAZIONE:
            target = buckets[CONTAMINAZIONE]
        else:
            target = buckets[sleeve]

        # Chiusa in finestra: realizza il net_pnl (o 0 se mancante) e conta.
        if (pos.get("exit_date") is not None
                and pos.get("exit_date") >= window_start):
            target["realized"] += position_realized(pos, window_start)
            target["n_closed"] += 1

        # Aperta: MTMark al prezzo corrente, o conteggiata come non marcabile.
        if pos.get("exit_date") is None:
            mtm = position_mark_to_market(pos, current_prices)
            if mtm is None:
                target["n_open_unmarked"] += 1
            else:
                target["mark_to_market_open"] += mtm
                target["n_open_marked"] += 1

        target["total"] = target["realized"] + target["mark_to_market_open"]

    # BOOK = somma delle tre bucket -- esattamente come in economic_pnl.
    book = _empty_sleeve()
    for s in STRATEGIE:
        b = buckets[s]
        book["realized"] += b["realized"]
        book["mark_to_market_open"] += b["mark_to_market_open"]
        book["total"] += b["total"]
        book["n_closed"] += b["n_closed"]
        book["n_open_marked"] += b["n_open_marked"]
        book["n_open_unmarked"] += b["n_open_unmarked"]
    buckets["BOOK"] = book

    return buckets
