"""Contratto deterministico della misura di latenza d'uscita S1 (#489)."""

from datetime import datetime, timezone

import pandas as pd
import pytest

from measure_s1_exit_latency import measure_trade_latency


def test_misura_flip_ritardo_e_scomposizione_del_pnl() -> None:
    sessions = pd.date_range("2026-01-02", periods=5, freq="B", tz="UTC")
    signals = pd.DataFrame(
        {"TXN": [0.40, -0.10, 0.20, -0.30, -0.50]},
        index=sessions,
    )
    closes = pd.DataFrame(
        {"TXN": [100.0, 99.0, 103.0, 101.0, 96.0]},
        index=sessions,
    )
    trade = {
        "trade_id": 17,
        "symbol": "TXN",
        "entry_time": datetime(2026, 1, 2, 15, 0, tzinfo=timezone.utc),
        "entry_price": 100.0,
        "exit_time": datetime(2026, 1, 8, 15, 0, tzinfo=timezone.utc),
        "exit_price": 95.0,
        "qty": 2.0,
        "gross_pnl": -10.0,
        "net_pnl": -10.2,
    }

    measured = measure_trade_latency(trade, signals, closes)

    # Il negativo del 5 gennaio non e' il flip rilevante: il segnale torna
    # positivo e solo il 7 inizia la sequenza negativa attiva all'uscita.
    assert measured["flip_date"] == "2026-01-07"
    assert measured["delay_sessions"] == 1
    assert measured["flip_close"] == pytest.approx(101.0)
    assert measured["pnl_before_flip_usd"] == pytest.approx(2.0)
    assert measured["pnl_after_flip_usd"] == pytest.approx(-12.0)
    assert measured["gross_pnl_reconstructed_usd"] == pytest.approx(-10.0)


def test_un_segnale_non_negativo_all_uscita_non_inventa_un_flip() -> None:
    sessions = pd.date_range("2026-01-02", periods=3, freq="B", tz="UTC")
    signals = pd.DataFrame({"ARM": [-0.2, 0.1, 0.3]}, index=sessions)
    closes = pd.DataFrame({"ARM": [100.0, 99.0, 98.0]}, index=sessions)
    trade = {
        "trade_id": 18,
        "symbol": "ARM",
        "entry_time": sessions[0].to_pydatetime(),
        "entry_price": 100.0,
        "exit_time": sessions[-1].to_pydatetime(),
        "exit_price": 98.0,
        "qty": 1.0,
        "gross_pnl": -2.0,
        "net_pnl": -2.1,
    }

    measured = measure_trade_latency(trade, signals, closes)

    assert measured["flip_date"] is None
    assert measured["delay_sessions"] is None
    assert measured["pnl_before_flip_usd"] is None
    assert measured["pnl_after_flip_usd"] is None

