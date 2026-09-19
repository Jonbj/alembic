"""#550 (F-073) — write_execution_decision persiste il moltiplicatore velocity.

`signal_score` resta il punteggio GREZZO del segnale (semantica documentata:
quello che l'analisi IC correla coi forward return). `velocity_multiplier` e'
il campo nuovo che spiega la differenza fra il grezzo e il punteggio che il
gate ha effettivamente valutato.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.store.pg_store import PostgreSQLStore


def _store_with_spy_conn():
    conn = MagicMock()
    cursor = MagicMock()
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    cursor.fetchone.return_value = (99,)
    conn.cursor.return_value = cursor
    store = PostgreSQLStore.__new__(PostgreSQLStore)
    store._get_connection = lambda: conn
    return store, cursor


def test_l_insert_include_velocity_multiplier_e_il_suo_valore():
    store, cursor = _store_with_spy_conn()

    store.write_execution_decision(
        tick_time=datetime(2026, 9, 17, 16, 7, tzinfo=timezone.utc),
        symbol="BA",
        signal_id=11429,
        score=0.02,
        signal_score=0.27375,
        velocity_multiplier=1.2,
        regime_mult=1.0,
        ema_pass=True,
        decision="BUY",
        reason="S4 news-driven",
    )

    sql = cursor.execute.call_args[0][0]
    params = cursor.execute.call_args[0][1]
    assert "velocity_multiplier" in sql
    assert 1.2 in params


def test_velocity_multiplier_default_none_per_righe_non_strumentate():
    """Chi non lo passa (SKIP_STALE, SKIP_FALLBACK, righe pre-S4) scrive NULL:
    «non strumentato», non moltiplicatore unitario implicito."""
    store, cursor = _store_with_spy_conn()

    store.write_execution_decision(
        tick_time=datetime(2026, 9, 17, 16, 7, tzinfo=timezone.utc),
        symbol="INTC",
        signal_id=1,
        score=0.0,
        signal_score=0.42,
        regime_mult=1.0,
        ema_pass=False,
        decision="SKIP_STALE",
        reason="signal 20h old",
    )

    params = cursor.execute.call_args[0][1]
    assert params[-1] is None or None in params


def test_il_placeholder_count_combacia_con_le_colonne():
    """Un INSERT con colonne e VALUES disallineati fallisce solo a runtime,
    sul primo ciclo live: il conto dei %s si verifica qui."""
    store, cursor = _store_with_spy_conn()

    store.write_execution_decision(
        tick_time=datetime(2026, 9, 17, 16, 7, tzinfo=timezone.utc),
        symbol="BA",
        signal_id=None,
        score=0.0,
        signal_score=0.18,
        velocity_multiplier=None,
        regime_mult=1.0,
        ema_pass=False,
        decision="SKIP_THRESHOLD",
        reason="score 0.180 < feedback threshold 0.350",
    )

    sql = cursor.execute.call_args[0][0]
    params = cursor.execute.call_args[0][1]
    colonne = sql.split("(")[1].split(")")[0]
    assert len(colonne.split(",")) == len(params)
