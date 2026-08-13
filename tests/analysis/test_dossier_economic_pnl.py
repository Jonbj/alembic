"""P&L economico della carta di osservazione (#278).

La carta (docs/evidence/OBSERVATION_CHARTER.md, "Definizione: P&L economico")
dice: per ogni posizione, il movimento di prezzo attribuibile alla finestra --
si marca dal close del primo giorno della finestra (o dal prezzo di ingresso,
se successivo) al prezzo corrente (o al prezzo di uscita, se anteriore),
moltiplicato per la quantita'. Somma su tutte le posizioni, aperte e chiuse.

Questi test inchiodano quella definizione esatta, inclusi i due casi limite che
la prosa della carta descrive: ingresso nella finestra (mark dall'entry, non
dal close del primo giorno) e uscita nella finestra (mark all'exit_price).
"""

from datetime import date

import pytest

from src.analysis.dossier.economic_pnl import (
    attribute_strategy,
    compute_economic_pnl,
    mark_from,
    position_series,
)

W_START = date(2026, 8, 3)


def _pos(
    symbol="AAA",
    stop_strategy=None,
    signal_id=None,
    entry_price=100.0,
    entry_date=date(2026, 7, 10),
    exit_price=None,
    exit_date=None,
    qty=10.0,
):
    return {
        "symbol": symbol,
        "stop_strategy": stop_strategy,
        "signal_id": signal_id,
        "entry_price": entry_price,
        "entry_date": entry_date,
        "exit_price": exit_price,
        "exit_date": exit_date,
        "qty": qty,
    }


# --- attribuzione (#278 acceptance: niente fallback S1 arbitrario) ----------


def test_attribuzione_stop_strategy_vince_su_signal_id():
    """stop_strategy e' la fonte autorevole (incidente trade 361 del 2026-07-17)."""
    assert attribute_strategy("S1", 42) == "S1"
    assert attribute_strategy("S4", None) == "S4"


def test_attribuzione_signal_id_dà_s4_se_stop_strategy_mancante():
    assert attribute_strategy(None, 42) == "S4"


def test_attribuzione_senza_niente_e_contaminazione_non_s1():
    """Il dossier legacy farebbe CASE WHEN signal_id IS NOT NULL THEN 'S4' ELSE 'S1':
    assegnerebbe S1. La carta (#278) vieta l'assegnazione arbitraria -> CONTAMINAZIONE."""
    assert attribute_strategy(None, None) == "CONTAMINAZIONE"


# --- mark_from: close del primo giorno, o entry se successivo ---------------


def test_mark_from_posizione_pre_finestra_usa_close_del_primo_giorno():
    closes = {W_START: {"AAA": 105.0}}
    assert mark_from(_pos(entry_date=date(2026, 7, 10)), W_START, closes) == 105.0


def test_mark_from_ingresso_nel_primo_giorno_usa_close_non_entry():
    """'se successivo' = strettamente dopo. Ingresso sul primo giorno -> close."""
    closes = {W_START: {"AAA": 105.0}}
    assert mark_from(_pos(entry_date=W_START, entry_price=100.0), W_START, closes) == 105.0


def test_mark_from_ingresso_dopo_il_primo_giorno_usa_entry_price():
    closes = {W_START: {"AAA": 105.0}}
    assert mark_from(
        _pos(entry_date=date(2026, 8, 5), entry_price=102.0), W_START, closes
    ) == 102.0


def test_mark_from_close_primo_giorno_mancante_restituisce_none():
    """Non si inventa un valore: posa pre-finestra senza close di riferimento e' non marcabile."""
    assert mark_from(_pos(entry_date=date(2026, 7, 10)), W_START, {}) is None


# --- position_series: la serie cumulata per posizione ----------------------


def test_serie_posizione_pre_finestra_aperta_parte_da_zero_sul_primo_giorno():
    """cum[window_start] = (close_start - close_start)*qty = 0: la baseline e' il close stesso."""
    days = [date(2026, 8, 3), date(2026, 8, 4), date(2026, 8, 5)]
    closes = {
        date(2026, 8, 3): {"AAA": 100.0},
        date(2026, 8, 4): {"AAA": 104.0},
        date(2026, 8, 5): {"AAA": 101.0},
    }
    s = position_series(_pos(entry_date=date(2026, 7, 10), entry_price=90.0, qty=10.0),
                        days, W_START, closes)
    assert s[date(2026, 8, 3)] == pytest.approx(0.0)
    assert s[date(2026, 8, 4)] == pytest.approx(40.0)   # (104-100)*10
    assert s[date(2026, 8, 5)] == pytest.approx(10.0)   # (101-100)*10


def test_serie_ingresso_nella_finestra_parte_dall_entry_price():
    days = [date(2026, 8, 3), date(2026, 8, 4), date(2026, 8, 5)]
    closes = {
        date(2026, 8, 3): {"AAA": 100.0},
        date(2026, 8, 4): {"AAA": 104.0},
        date(2026, 8, 5): {"AAA": 106.0},
    }
    s = position_series(
        _pos(entry_date=date(2026, 8, 4), entry_price=102.0, qty=10.0),
        days, W_START, closes,
    )
    assert s[date(2026, 8, 3)] == pytest.approx(0.0)    # non ancora aperta
    assert s[date(2026, 8, 4)] == pytest.approx(20.0)   # (104-102)*10
    assert s[date(2026, 8, 5)] == pytest.approx(40.0)   # (106-102)*10


def test_serie_uscita_nella_finestra_marca_all_exit_price_e_poi_costante():
    days = [date(2026, 8, 3), date(2026, 8, 4), date(2026, 8, 5)]
    closes = {
        date(2026, 8, 3): {"AAA": 100.0},
        date(2026, 8, 4): {"AAA": 104.0},
        date(2026, 8, 5): {"AAA": 106.0},
    }
    s = position_series(
        _pos(entry_date=date(2026, 7, 10), exit_date=date(2026, 8, 4), exit_price=103.0, qty=10.0),
        days, W_START, closes,
    )
    assert s[date(2026, 8, 3)] == pytest.approx(0.0)
    assert s[date(2026, 8, 4)] == pytest.approx(30.0)   # (103-100)*10
    assert s[date(2026, 8, 5)] == pytest.approx(30.0)   # costante: uscita gia' avvenuta


def test_serie_barra_mancante_carry_forward_del_ultimo_mark_daily_zero():
    """Un giorno senza barra non si inventa un prezzo: il mark resta l'ultimo noto."""
    days = [date(2026, 8, 3), date(2026, 8, 4), date(2026, 8, 5)]
    closes = {
        date(2026, 8, 3): {"AAA": 100.0},
        # 08-04 mancante
        date(2026, 8, 5): {"AAA": 106.0},
    }
    s = position_series(_pos(entry_date=date(2026, 7, 10), qty=10.0), days, W_START, closes)
    assert s[date(2026, 8, 4)] == pytest.approx(0.0)    # carry forward di close_start
    assert s[date(2026, 8, 5)] == pytest.approx(60.0)   # (106-100)*10


def test_serie_posizione_non_marcabile_torna_none_ogni_giorno():
    days = [date(2026, 8, 3), date(2026, 8, 4)]
    s = position_series(_pos(entry_date=date(2026, 7, 10)), days, W_START, {})
    assert s[date(2026, 8, 3)] is None
    assert s[date(2026, 8, 4)] is None


# --- compute_economic_pnl: aggregazione per strategia ----------------------


def test_compute_esclude_posizioni_senza_entry_price_o_qty():
    days = [date(2026, 8, 3)]
    closes = {date(2026, 8, 3): {"AAA": 100.0}}
    res = compute_economic_pnl(
        [_pos(symbol="AAA", stop_strategy="S1", entry_price=None),
         _pos(symbol="BBB", stop_strategy="S1", qty=None)],
        days, W_START, closes,
    )
    assert res["esclusi"] == 2
    assert res["numerosita"]["S1"] == 0


def test_compute_esclude_posizione_chiusa_senza_exit_price():
    days = [date(2026, 8, 3)]
    closes = {date(2026, 8, 3): {"AAA": 100.0}}
    res = compute_economic_pnl(
        [_pos(stop_strategy="S1", exit_date=date(2026, 8, 3), exit_price=None)],
        days, W_START, closes,
    )
    assert res["esclusi"] == 1


def test_compute_book_e_somma_di_s1_s4_contaminazione():
    days = [date(2026, 8, 3), date(2026, 8, 4)]
    closes = {
        date(2026, 8, 3): {"AAA": 100.0, "BBB": 100.0, "CCC": 100.0},
        date(2026, 8, 4): {"AAA": 110.0, "BBB": 108.0, "CCC": 90.0},
    }
    res = compute_economic_pnl(
        [_pos(symbol="AAA", stop_strategy="S1", qty=10.0),
         _pos(symbol="BBB", stop_strategy="S4", qty=10.0),
         _pos(symbol="CCC", stop_strategy=None, signal_id=None, qty=10.0)],
        days, W_START, closes,
    )
    # cum al giorno 4: S1=(110-100)*10=100, S4=(108-100)*10=80, CONTAM=-100
    assert res["cumulato"]["S1"][date(2026, 8, 4)] == pytest.approx(100.0)
    assert res["cumulato"]["S4"][date(2026, 8, 4)] == pytest.approx(80.0)
    assert res["cumulato"]["CONTAMINAZIONE"][date(2026, 8, 4)] == pytest.approx(-100.0)
    assert res["cumulato"]["BOOK"][date(2026, 8, 4)] == pytest.approx(80.0)


def test_compute_giornaliero_e_differenza_prima_del_cumulato():
    days = [date(2026, 8, 3), date(2026, 8, 4), date(2026, 8, 5)]
    closes = {
        date(2026, 8, 3): {"AAA": 100.0},
        date(2026, 8, 4): {"AAA": 104.0},
        date(2026, 8, 5): {"AAA": 101.0},
    }
    res = compute_economic_pnl([_pos(symbol="AAA", stop_strategy="S1", qty=10.0)],
                               days, W_START, closes)
    assert res["giornaliero"]["S1"][date(2026, 8, 3)] == pytest.approx(0.0)
    assert res["giornaliero"]["S1"][date(2026, 8, 4)] == pytest.approx(40.0)
    assert res["giornaliero"]["S1"][date(2026, 8, 5)] == pytest.approx(-30.0)


def test_compute_contaminazione_non_finisce_in_s1_ne_s4():
    """Le 12 posizioni del 2026-07-10 senza stop_strategy ne' signal_id non devono
    essere assorbite in S1 (come farebbe il dossier legacy) ne' in S4."""
    days = [date(2026, 8, 3)]
    closes = {date(2026, 8, 3): {"AAA": 100.0}}
    res = compute_economic_pnl(
        [_pos(symbol="AAA", stop_strategy=None, signal_id=None, entry_date=date(2026, 7, 10),
              entry_price=90.0, qty=10.0)],
        days, W_START, closes,
    )
    assert res["numerosita"]["S1"] == 0
    assert res["numerosita"]["S4"] == 0
    assert res["numerosita"]["CONTAMINAZIONE"] == 1


def test_compute_capital_base_somma_mark_from_per_qty():
    """Base di capitale al mark del primo giorno, per il benchmark SPY di S1."""
    days = [date(2026, 8, 3)]
    closes = {date(2026, 8, 3): {"AAA": 100.0, "BBB": 50.0}}
    res = compute_economic_pnl(
        [_pos(symbol="AAA", stop_strategy="S1", qty=10.0),
         _pos(symbol="BBB", stop_strategy="S1", qty=4.0)],
        days, W_START, closes,
    )
    # capital_base S1 = 100*10 + 50*4 = 1200
    assert res["capital_base"]["S1"] == pytest.approx(1200.0)


def test_compute_capital_base_ingresso_nella_finestra_usa_entry_price():
    days = [date(2026, 8, 3), date(2026, 8, 4)]
    closes = {date(2026, 8, 3): {"AAA": 100.0}, date(2026, 8, 4): {"AAA": 110.0}}
    res = compute_economic_pnl(
        [_pos(symbol="AAA", stop_strategy="S1", entry_date=date(2026, 8, 4),
              entry_price=105.0, qty=10.0)],
        days, W_START, closes,
    )
    assert res["capital_base"]["S1"] == pytest.approx(1050.0)


def test_compute_missing_conta_le_posizioni_non_marcabili_per_giorno():
    days = [date(2026, 8, 3)]
    # close del primo giorno mancante per AAA -> posizione pre-finestra non marcabile
    res = compute_economic_pnl(
        [_pos(symbol="AAA", stop_strategy="S1", entry_date=date(2026, 7, 10))],
        days, W_START, {},
    )
    assert res["missing"]["S1"][date(2026, 8, 3)] == 1