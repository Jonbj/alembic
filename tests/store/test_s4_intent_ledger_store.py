"""#294: persistenza idempotente e provenance del ledger intenti S4."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.models.signals import SentimentResult
from src.store.pg_store import PostgreSQLStore
from src.strategies.s4.config import S4Config
from src.strategies.s4.intent_ledger import S4IntentLedger, build_component_versions

_TS = datetime(2026, 8, 24, 14, 7, tzinfo=timezone.utc)


def _store_and_cursor():
    conn = MagicMock()
    cursor = MagicMock()
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cursor
    return PostgreSQLStore(conn=conn, use_pool=False), conn, cursor


def _event():
    versions = build_component_versions(
        config=S4Config(),
        risk_config={"s4_fixed_slot_sizing_enabled": True},
        code_version="abc1234",
        config_hash="deadbeef",
        policy_version="s4-exit-trial:v1",
    )
    signal = SentimentResult(
        symbol="AMD",
        score=0.6,
        confidence=0.9,
        reasoning="test",
        model_id="ensemble:test",
        generated_at=_TS,
        signal_id=42,
    )
    return S4IntentLedger(_TS, versions).capture([signal])[0]


def test_write_intent_events_e_batch_idempotente_append_only():
    store, conn, cursor = _store_and_cursor()

    store.write_s4_intent_events([_event(), _event()])

    cursor.executemany.assert_called_once()
    sql, params = cursor.executemany.call_args.args
    assert "INSERT INTO s4_intent_events" in sql
    assert "ON CONFLICT (event_id) DO NOTHING" in sql
    assert len(params) == 2
    assert params[0][0] == _event().event_id
    conn.commit.assert_called_once()


def test_write_intent_events_rollback_su_errore():
    store, conn, cursor = _store_and_cursor()
    cursor.executemany.side_effect = RuntimeError("db down")

    try:
        store.write_s4_intent_events([_event()])
    except RuntimeError:
        pass
    else:
        raise AssertionError("write_s4_intent_events must propagate persistence failures")

    conn.rollback.assert_called_once()


def test_fetch_signals_for_cycle_include_provenance_senza_cambiare_ordinamento():
    query = PostgreSQLStore._FETCH_SIGNALS_FOR_CYCLE

    assert "LEFT JOIN news_log" in query
    assert "LEFT JOIN LATERAL" in query
    assert "raw_ingested_at" in query
    assert "content_hash" in query
    assert "resolver_decision" in query
    assert "ORDER BY ss.symbol, ss.fallback_used ASC, ss.generated_at DESC" in query


def test_fetch_signals_for_cycle_mappa_la_provenance_point_in_time():
    store, _, cursor = _store_and_cursor()
    cursor.fetchall.return_value = [{
        "id": 42,
        "symbol": "AMD",
        "score": 0.6,
        "confidence": 0.9,
        "reasoning": "test",
        "model_id": "ensemble:test",
        "ensemble_std": 0.1,
        "fallback_used": False,
        "generated_at": _TS,
        "published_at": _TS,
        "news_log_id": 901,
        "first_seen_at": _TS,
        "news_source": "alpaca",
        "content_hash": "a" * 64,
        "extraction_method": "source_metadata",
        "resolver_decision": "RESOLVED",
        "resolver_method": "source_metadata",
    }]

    [signal] = store.fetch_signals_for_cycle(hours=4, symbols=["AMD"])

    assert signal.news_log_id == 901
    assert signal.first_seen_at == _TS
    assert signal.news_source == "alpaca"
    assert signal.content_hash == "a" * 64
    assert signal.resolver_decision == "RESOLVED"
    assert signal.resolver_method == "source_metadata"
