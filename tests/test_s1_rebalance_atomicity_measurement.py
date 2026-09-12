"""Misura deterministica del drift fra decisione e SELL S1 (#468)."""

from datetime import UTC, datetime

import pandas as pd
import pytest


def _ts(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 9, 1, hour, minute, second, tzinfo=UTC)


def test_measure_exit_drift_usa_solo_barre_complete() -> None:
    from scripts.measure_s1_rebalance_atomicity import measure_exit_drift

    closes = pd.DataFrame(
        {"GE": [100.0, 999.0, 100.3, 777.0]},
        index=pd.DatetimeIndex(
            [_ts(14, 6), _ts(14, 7), _ts(14, 21), _ts(14, 22)]
        ),
    )
    event = {
        "symbol": "GE",
        "quantity": 2.0,
        "decision_time": _ts(14, 7, 0),
        "exit_time": _ts(14, 22, 0),
    }

    measured = measure_exit_drift(event, closes)

    # Alle 14:07 la barra 14:07 non era ancora completa; idem alle 14:22.
    assert measured["decision_price"] == pytest.approx(100.0)
    assert measured["exit_price"] == pytest.approx(100.3)
    assert measured["drift_pct"] == pytest.approx(0.003)
    assert measured["drift_usd"] == pytest.approx(0.6)
    assert measured["delay_minutes"] == pytest.approx(15.0)
    assert measured["status"] == "measured"


def test_measure_exit_drift_dichiara_il_prezzo_mancante() -> None:
    from scripts.measure_s1_rebalance_atomicity import measure_exit_drift

    closes = pd.DataFrame(
        {"GE": [100.0]},
        index=pd.DatetimeIndex([_ts(14, 6)]),
    )
    event = {
        "symbol": "MMM",
        "quantity": 3.0,
        "decision_time": _ts(14, 7),
        "exit_time": _ts(14, 22),
    }

    measured = measure_exit_drift(event, closes)

    assert measured["status"] == "missing_price"
    assert measured["drift_usd"] is None


def test_summarize_aggregates_signed_seller_drift() -> None:
    from scripts.measure_s1_rebalance_atomicity import summarize

    summary = summarize(
        [
            {"status": "measured", "delay_minutes": 15.0, "drift_usd": 5.0},
            {"status": "measured", "delay_minutes": 15.0, "drift_usd": -2.0},
            {"status": "missing_price", "delay_minutes": 15.0, "drift_usd": None},
        ]
    )

    assert summary == {
        "symbols_total": 3,
        "symbols_measured": 2,
        "symbols_missing_price": 1,
        "median_delay_minutes": 15.0,
        "total_drift_usd": pytest.approx(3.0),
    }
