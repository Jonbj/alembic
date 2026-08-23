"""P&L totale per sleeve (realized + mark-to-market delle aperte), issue #210.

Issue #210 mostra che il P&L realizzato di S1 e' un campione selezionato
avversariamente dalla regola d'uscita (chiude quando perde rango momentum,
le vincenti restano aperte). La carta di osservazione (#171) definisce il
P&L economico (mark-from-first-day) ma non il **P&L totale**, che affianca
al realized la valutazione mark-to-market delle posizioni ancora aperte.

Questo modulo e' complementare a ``economic_pnl``: stessa attribuzione per
sleeve, stesso divieto di fallback S1 arbitrario (#278), ma la misura e'
diversa -- somma il realized chiuso nella finestra al MTMark delle aperte
al prezzo corrente, cosi' il verdetto del 28/09 non legga solo i perdenti.

DEFINIZIONE
-----------

Per ogni posizione nella finestra [window_start, as_of]:

* **realized**: ``net_pnl`` se la posizione e' chiusa nella finestra
  (``exit_date IS NOT None AND exit_date >= window_start``).
* **mark_to_market_open**: ``(current_price - entry_price) * qty`` se la
  posizione e' aperta (``exit_date IS None``). Se ``current_price`` manca
  per quel simbolo, la posizione e' "non marcabile" (non si inventa un
  prezzo) -- viene contata in ``non_marcabili`` e non contribuisce al MTMark.
* Posizioni chiuse *prima* di ``window_start`` non entrano: la finestra e'
  chiusa a sinistra anche per il realized, esattamente come per
  l'economico.

Per sleeve (S1 / S4 / CONTAMINAZIONE, piu' BOOK = somma delle tre), output::

    {
        "realized": float,
        "mark_to_market_open": float,
        "total": float,
        "n_closed": int,
        "n_open_marked": int,
        "n_open_unmarked": int,
    }

Compatibilita' col freeze #171: e' pura misura, non tocca nessuna taratura.
"""

from datetime import date

import pytest

from src.analysis.dossier.economic_pnl import CONTAMINAZIONE
from src.analysis.dossier.total_pnl import (
    compute_total_pnl,
    position_realized,
    position_mark_to_market,
)

W_START = date(2026, 8, 3)
AS_OF = date(2026, 8, 20)


def _pos(
    symbol="AAA",
    stop_strategy=None,
    signal_id=None,
    entry_price=100.0,
    entry_date=date(2026, 7, 10),
    exit_price=None,
    exit_date=None,
    net_pnl=None,
    qty=10.0,
):
    """Helper posizione con campi sufficienti sia per realized sia per MTMark."""
    return {
        "symbol": symbol,
        "stop_strategy": stop_strategy,
        "signal_id": signal_id,
        "entry_price": entry_price,
        "entry_date": entry_date,
        "exit_price": exit_price,
        "exit_date": exit_date,
        "net_pnl": net_pnl,
        "qty": qty,
    }


# --- realized: net_pnl sulle chiuse nella finestra -------------------------


def test_realized_posizione_chiusa_nella_finestra_restituisce_net_pnl():
    """Una posizione chiusa dentro la finestra realizza il suo net_pnl."""
    p = _pos(exit_date=date(2026, 8, 10), exit_price=110.0, net_pnl=50.0)
    assert position_realized(p, W_START) == pytest.approx(50.0)


def test_realized_posizione_ancora_aperta_restituisce_zero():
    """Una posizione aperta non ha realized -- vive nel MTMark."""
    p = _pos(exit_date=None, net_pnl=None)
    assert position_realized(p, W_START) == 0.0


def test_realized_posizione_chiusa_prima_della_finestra_restituisce_zero():
    """La finestra e' chiusa a sinistra anche per il realized."""
    p = _pos(exit_date=date(2026, 7, 30), exit_price=120.0, net_pnl=80.0)
    assert position_realized(p, W_START) == 0.0


def test_realized_posizione_chiusa_il_primo_giorno_della_finestra_conta():
    """Il confine e' inclusivo: uscita == window_start realizza."""
    p = _pos(exit_date=W_START, exit_price=105.0, net_pnl=20.0)
    assert position_realized(p, W_START) == pytest.approx(20.0)


def test_realized_chiusa_nella_finestra_ma_net_pnl_none_restituisce_zero():
    """Una chiusura senza net_pnl e' un dato mancante, non uno zero di realizzo."""
    p = _pos(exit_date=date(2026, 8, 10), exit_price=110.0, net_pnl=None)
    assert position_realized(p, W_START) == 0.0


# --- mark-to-market: aperte al prezzo corrente ------------------------------


def test_mtm_posizione_aperta_con_prezzo_corrente_calcola_differenza_per_qty():
    """Una posizione aperta al current_price dato vale (current - entry) * qty."""
    p = _pos(entry_price=100.0, qty=10.0, exit_date=None)
    assert position_mark_to_market(p, {"AAA": 110.0}) == pytest.approx(100.0)


def test_mtm_posizione_aperta_senza_prezzo_corrente_e_non_marcabile():
    """Se il prezzo corrente manca, niente MTMark -- non si inventa."""
    p = _pos(entry_price=100.0, qty=10.0, exit_date=None)
    assert position_mark_to_market(p, {}) is None


def test_mtm_posizione_chiusa_non_ha_mark_to_market():
    """Una posizione gia' chiusa ha gia' realizzato: il MTMark non si applica."""
    p = _pos(entry_price=100.0, qty=10.0, exit_date=date(2026, 8, 5),
             exit_price=110.0, net_pnl=100.0)
    assert position_mark_to_market(p, {"AAA": 200.0}) is None


def test_mtm_posizione_aperta_senza_entry_price_o_qty_non_marcabile():
    """Senza entry_price o qty non c'e' una base di costo: non si inventa."""
    assert position_mark_to_market(_pos(entry_price=None, exit_date=None),
                                  {"AAA": 110.0}) is None
    assert position_mark_to_market(_pos(qty=None, exit_date=None),
                                  {"AAA": 110.0}) is None


# --- compute_total_pnl: aggregazione per sleeve ----------------------------


def test_compute_book_e_somma_di_s1_s4_contaminazione():
    """La bucket BOOK = somma di S1 + S4 + CONTAMINAZIONE (#278).

    Caso: S1 = una chiusa in finestra +20; S4 = aperta +80; CONTAM = aperta
    -100. Tutte con qty=10. I realized vanno solo sulle chiuse, il MTMark
    solo sulle aperte.
    """
    current_prices = {"BBB": 108.0, "CCC": 90.0}
    positions = [
        # S1: una chiusa in finestra, +20 realizzati, niente MTMark (chiusa)
        _pos(symbol="AAA", stop_strategy="S1", qty=10.0,
             exit_date=date(2026, 8, 5), exit_price=110.0, net_pnl=20.0),
        # S4: aperta, MTMark = (108 - 100) * 10 = +80
        _pos(symbol="BBB", stop_strategy="S4", qty=10.0, entry_price=100.0),
        # CONTAMINAZIONE: aperta, MTMark = (90 - 100) * 10 = -100
        _pos(symbol="CCC", stop_strategy=None, signal_id=None, qty=10.0,
             entry_price=100.0),
    ]
    res = compute_total_pnl(positions, current_prices, W_START)
    assert res["S1"]["realized"] == pytest.approx(20.0)
    assert res["S1"]["mark_to_market_open"] == pytest.approx(0.0)
    assert res["S1"]["total"] == pytest.approx(20.0)
    assert res["S1"]["n_closed"] == 1
    assert res["S4"]["realized"] == pytest.approx(0.0)
    assert res["S4"]["mark_to_market_open"] == pytest.approx(80.0)
    assert res["S4"]["total"] == pytest.approx(80.0)
    assert res[CONTAMINAZIONE]["realized"] == pytest.approx(0.0)
    assert res[CONTAMINAZIONE]["mark_to_market_open"] == pytest.approx(-100.0)
    assert res[CONTAMINAZIONE]["total"] == pytest.approx(-100.0)
    assert res["BOOK"]["total"] == pytest.approx(20.0 + 80.0 - 100.0)


def test_compute_signal_id_da_s4_se_stop_strategy_mancante():
    """Stessa attribuzione del modulo economic_pnl (#278): signal_id -> S4."""
    current_prices = {"AAA": 110.0}
    positions = [
        _pos(symbol="AAA", stop_strategy=None, signal_id=42, qty=10.0,
             entry_price=100.0),
    ]
    res = compute_total_pnl(positions, current_prices, W_START)
    assert res["S4"]["mark_to_market_open"] == pytest.approx(100.0)
    assert res[CONTAMINAZIONE]["mark_to_market_open"] == pytest.approx(0.0)


def test_compute_senza_attribuzione_finisce_in_contaminazione_non_s1():
    """Vietato il fallback S1 arbitrario (criterio #278)."""
    current_prices = {"AAA": 110.0}
    positions = [
        _pos(symbol="AAA", stop_strategy=None, signal_id=None, qty=10.0,
             entry_price=100.0),
    ]
    res = compute_total_pnl(positions, current_prices, W_START)
    assert res[CONTAMINAZIONE]["mark_to_market_open"] == pytest.approx(100.0)
    assert res["S1"]["mark_to_market_open"] == 0.0


def test_compute_posizione_aperta_senza_prezzo_corrente_in_non_marcabili():
    """Aperta senza current_price: il MTMark non si inventa, si conta."""
    current_prices = {}  # AAA assente
    positions = [
        _pos(symbol="AAA", stop_strategy="S1", qty=10.0, entry_price=100.0),
    ]
    res = compute_total_pnl(positions, current_prices, W_START)
    assert res["S1"]["mark_to_market_open"] == pytest.approx(0.0)
    assert res["S1"]["n_open_unmarked"] == 1
    assert res["S1"]["n_open_marked"] == 0


def test_compute_realized_e_mtm_sullo_stesso_sleeve_si_sommano_in_total():
    """Il numero che verra' letto al 28/09: realized + MTMark per sleeve."""
    current_prices = {"BBB": 110.0}
    positions = [
        # chiusa in finestra, +20 realizzato
        _pos(symbol="AAA", stop_strategy="S1", qty=10.0,
             entry_price=100.0, exit_date=date(2026, 8, 10),
             exit_price=102.0, net_pnl=20.0),
        # altra posizione S1 ancora aperta, MTMark = (110 - 100) * 10 = +100
        _pos(symbol="BBB", stop_strategy="S1", qty=10.0,
             entry_price=100.0),
    ]
    res = compute_total_pnl(positions, current_prices, W_START)
    assert res["S1"]["realized"] == pytest.approx(20.0)
    assert res["S1"]["mark_to_market_open"] == pytest.approx(100.0)
    assert res["S1"]["total"] == pytest.approx(120.0)
    assert res["S1"]["n_closed"] == 1
    assert res["S1"]["n_open_marked"] == 1


def test_compute_posizioni_chiuse_prima_della_finestra_non_contano():
    """La finestra di realized e' [window_start, ...]: prima non entra."""
    current_prices = {"AAA": 110.0}
    positions = [
        _pos(symbol="AAA", stop_strategy="S1", qty=10.0,
             entry_price=100.0, exit_date=date(2026, 7, 30),
             exit_price=120.0, net_pnl=200.0),
    ]
    res = compute_total_pnl(positions, current_prices, W_START)
    assert res["S1"]["realized"] == 0.0
    assert res["S1"]["n_closed"] == 0


def test_compute_chiusa_in_finestra_con_net_pnl_zero_conta_come_chiusa():
    """Una chiusura in finestra con net_pnl=0 e' una chiusura: conta in n_closed."""
    current_prices = {}
    positions = [
        _pos(symbol="AAA", stop_strategy="S1", qty=10.0,
             entry_price=100.0, exit_date=date(2026, 8, 10),
             exit_price=100.0, net_pnl=0.0),
    ]
    res = compute_total_pnl(positions, current_prices, W_START)
    assert res["S1"]["realized"] == 0.0
    assert res["S1"]["n_closed"] == 1


def test_compute_chiusa_in_finestra_senza_net_pnl_conta_come_chiusa():
    """Una chiusura con net_pnl mancante (None) e' una chiusura lo stesso."""
    current_prices = {}
    positions = [
        _pos(symbol="AAA", stop_strategy="S1", qty=10.0,
             entry_price=100.0, exit_date=date(2026, 8, 10),
             exit_price=102.0, net_pnl=None),
    ]
    res = compute_total_pnl(positions, current_prices, W_START)
    assert res["S1"]["realized"] == 0.0
    assert res["S1"]["n_closed"] == 1


def test_compute_book_total_coerente_con_somma_sleeve():
    """Invariante: BOOK.total == S1.total + S4.total + CONTAMINAZIONE.total."""
    current_prices = {"AAA": 110.0, "BBB": 90.0, "CCC": 105.0}
    positions = [
        _pos(symbol="AAA", stop_strategy="S1", qty=5.0, entry_price=100.0),
        _pos(symbol="BBB", stop_strategy="S4", qty=5.0, entry_price=100.0),
        _pos(symbol="CCC", stop_strategy=None, signal_id=1, qty=5.0,
             entry_price=100.0),
    ]
    res = compute_total_pnl(positions, current_prices, W_START)
    s_sum = res["S1"]["total"] + res["S4"]["total"] + res[CONTAMINAZIONE]["total"]
    assert res["BOOK"]["total"] == pytest.approx(s_sum)
    assert res["BOOK"]["n_open_marked"] == (
        res["S1"]["n_open_marked"]
        + res["S4"]["n_open_marked"]
        + res[CONTAMINAZIONE]["n_open_marked"]
    )
