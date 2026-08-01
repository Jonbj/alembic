"""Metriche del book: ingressi, chiusure, aggregazioni."""
import pytest

from src.analysis.dossier.book import compute_entries


def _bar(open_=100.0, high=110.0, low=90.0, close=105.0):
    return {"open": open_, "high": high, "low": low, "close": close}


def test_entry_percentile_misura_dove_si_e_comprato_nel_range():
    """0 = comprato sul minimo del giorno, 1 = sul massimo."""
    trades = [{"symbol": "AAA", "strategia": "S1", "ora_utc": "14:07",
               "entry_price": 90.0, "qty": 10.0}]
    out = compute_entries(trades, {"AAA": _bar()})
    assert out[0]["entry_percentile"] == pytest.approx(0.0)

    trades[0]["entry_price"] = 110.0
    assert compute_entries(trades, {"AAA": _bar()})[0]["entry_percentile"] == pytest.approx(1.0)

    trades[0]["entry_price"] = 100.0
    assert compute_entries(trades, {"AAA": _bar()})[0]["entry_percentile"] == pytest.approx(0.5)


def test_caso_reale_f_inseguimento_del_massimo():
    """S1 compro' F a 16.02 il 2026-07-29, range 15.16-16.29, chiusura 15.28."""
    trades = [{"symbol": "F", "strategia": "S1", "ora_utc": "14:07",
               "entry_price": 16.02, "qty": 100.0}]
    bars = {"F": {"open": 15.55, "high": 16.29, "low": 15.16, "close": 15.28}}
    out = compute_entries(trades, bars)
    assert out[0]["entry_percentile"] == pytest.approx(0.7611, abs=1e-4)
    assert out[0]["mtm_eod"] == pytest.approx(-74.0)


def test_mtm_eod_e_vs_apertura():
    trades = [{"symbol": "AAA", "strategia": "S4", "ora_utc": "15:22",
               "entry_price": 102.0, "qty": 5.0}]
    out = compute_entries(trades, {"AAA": _bar()})
    assert out[0]["mtm_eod"] == pytest.approx(15.0)      # (105 - 102) * 5
    assert out[0]["vs_apertura"] == pytest.approx(25.0)  # (105 - 100) * 5


def test_range_degenere_da_percentile_none_non_divisione_per_zero():
    trades = [{"symbol": "AAA", "strategia": "S1", "ora_utc": "14:07",
               "entry_price": 100.0, "qty": 1.0}]
    bars = {"AAA": {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0}}
    assert compute_entries(trades, bars)[0]["entry_percentile"] is None


def test_simbolo_senza_barra_e_saltato_non_inventato():
    trades = [{"symbol": "ZZZ", "strategia": "S1", "ora_utc": "14:07",
               "entry_price": 10.0, "qty": 1.0}]
    out = compute_entries(trades, {})
    assert out[0]["entry_percentile"] is None
    assert out[0]["mtm_eod"] is None
