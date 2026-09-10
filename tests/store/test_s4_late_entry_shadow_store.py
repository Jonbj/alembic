"""#512: persistenza osservazioni late-entry su execution_decisions."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.models.signals import SentimentResult
from src.store.pg_store import PostgreSQLStore
from src.strategies.s4.config import S4Config
from src.strategies.s4.intent_ledger import S4IntentLedger, build_component_versions

_TS = datetime(2026, 9, 10, 16, 7, tzinfo=UTC)


def _versions():
    return build_component_versions(
        config=S4Config(),
        risk_config={"s4_fixed_slot_sizing_enabled": True},
        code_version="abc1234",
        config_hash="deadbeef",
        policy_version="s4-exit-trial:v1",
    )


def _events():
    ledger = S4IntentLedger(_TS, _versions())
    ledger.capture([
        SentimentResult(
            symbol="NVDA", signal_id=42, score=0.6, confidence=0.9,
            reasoning="test", model_id="ensemble:test", generated_at=_TS,
        ),
        SentimentResult(
            symbol="PLTR", signal_id=43, score=0.5, confidence=0.9,
            reasoning="test", model_id="ensemble:test", generated_at=_TS,
        ),
    ])
    ledger.attach_late_entry_context({
        "NVDA": {
            "decision_price": 108.0,
            "session_open": 100.0,
            "session_high": 110.0,
            "session_low": 100.0,
            "price_source": "alpaca_snapshot.latest_trade",
        },
    })
    return ledger.disposition_events(default_reason="UNCLASSIFIED")


def _store_and_cursor():
    conn = MagicMock()
    cursor = MagicMock()
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cursor
    return PostgreSQLStore(conn=conn, use_pool=False), conn, cursor


def test_scrive_una_osservazione_per_ogni_intento_anche_se_il_market_context_manca():
    store, conn, cursor = _store_and_cursor()

    store.write_s4_late_entry_observations(_events(), regime_mult=0.7)

    cursor.executemany.assert_called_once()
    sql, params = cursor.executemany.call_args.args
    assert "INSERT INTO execution_decisions" in sql
    assert "ON CONFLICT" in sql
    assert len(params) == 2
    assert {row[1] for row in params} == {"NVDA", "PLTR"}
    assert {row[7] for row in params} == {"SHADOW_LATE_ENTRY", "OBSERVE_LATE_ENTRY"}
    conn.commit.assert_called_once()


def test_rollback_se_la_persistenza_osservazionale_fallisce():
    store, conn, cursor = _store_and_cursor()
    cursor.executemany.side_effect = RuntimeError("db down")

    with pytest.raises(RuntimeError, match="db down"):
        store.write_s4_late_entry_observations(_events(), regime_mult=0.7)

    conn.rollback.assert_called_once()


def test_migrazione_collega_intent_e_metriche_pit_senza_cambiare_ordini():
    migration = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "066_s4_late_entry_shadow.sql"
    ).read_text()

    assert "s4_intent_id" in migration
    assert "session_range_percentile" in migration
    assert "shadow_late_entry" in migration
    assert "CREATE UNIQUE INDEX" in migration
