"""#296: persistenza append-only e input runtime del replay P0."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from src.store.pg_store import PostgreSQLStore
from src.strategies.s4.p0_baseline import P0ReplayEvent

TS = datetime(2026, 8, 25, 17, 52, tzinfo=UTC)


def _store_and_cursor():
    conn = MagicMock()
    cursor = MagicMock()
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cursor
    return PostgreSQLStore(conn=conn, use_pool=False), conn, cursor


def _event() -> P0ReplayEvent:
    return P0ReplayEvent(
        event_id="5e950738-40f7-5a54-9ab9-fd1458509b8e",
        intent_id="34d6c4c0-bcb2-55ef-a0f4-e3db1a4a13b0",
        policy_id="P0",
        policy_version="s4-exit-trial:1.0.0",
        event_type="P0_RUNTIME_REPLAY",
        observed_at=TS,
        d0=TS.date(),
        symbol="AMD",
        status="CLOSED",
        reason_code="P0_TARGET_ZERO_EXPIRED",
        trigger_at=TS,
        virtual_exit_quantity=2.0,
        runtime_quantity=2.0,
        first_executable_at=TS,
        first_executable_price=110.0,
        first_executable_price_source="alpaca_order.filled_avg_price",
        filled_at=TS,
        fill_price=110.0,
        initial_notional=210.5,
        gross_pnl=9.5,
        entry_cost_usd=1.0,
        exit_cost_usd=2.0,
        net_pnl=6.5,
        cost_model_version="cost-model:abcd1234",
        runtime_decision_id=901,
        runtime_order_id="exit-order-1",
        shadow_order_id=None,
        comparable=True,
        divergence_reasons=(),
        details={"snapshot_hash": "deadbeef"},
    )


def test_migrazione_crea_ledger_policy_append_only_e_viste_p0():
    migration = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "053_s4_p0_shadow_baseline.sql"
    ).read_text()

    assert "CREATE TABLE IF NOT EXISTS s4_exit_policy_events" in migration
    assert "prevent_s4_exit_policy_event_mutation" in migration
    assert "CREATE VIEW s4_exit_policy_current" in migration
    assert "CREATE VIEW s4_p0_validation" in migration
    assert "CREATE VIEW s4_p0_residuals" in migration
    assert "shadow_order_id" not in migration


def test_writer_persistente_e_idempotente_non_espone_un_ordine_shadow():
    store, conn, cursor = _store_and_cursor()

    store.write_s4_exit_policy_events([_event()])

    cursor.executemany.assert_called_once()
    sql, params = cursor.executemany.call_args.args
    assert "INSERT INTO s4_exit_policy_events" in sql
    assert "ON CONFLICT (event_id) DO NOTHING" in sql
    assert "shadow_order_id" not in sql
    assert params[0][0] == _event().event_id
    assert params[0][1] == _event().intent_id
    assert params[0][2] == "P0"
    conn.commit.assert_called_once()


def test_fetch_replay_candidates_include_aperti_e_trade_mancanti_nel_denominatore():
    store, conn, cursor = _store_and_cursor()
    cursor.fetchall.return_value = [{
        "intent_id": _event().intent_id,
        "entry_order_id": "entry-order-1",
        "runtime_order_ids": ["exit-order-1"],
        "runtime_decision_id": 901,
        "trigger_at": TS,
        "exit_mechanism": "expired",
    }]

    rows = store.fetch_s4_p0_replay_candidates()

    assert rows == cursor.fetchall.return_value
    sql = cursor.execute.call_args.args[0]
    assert "FROM s4_lifecycle_current lc" in sql
    assert "LEFT JOIN trades t ON t.entry_order_id = lc.order_id" in sql
    assert "LEFT JOIN LATERAL" in sql
    assert "s4_exit_policy_current" in sql
    assert "lc.filled_quantity > 0" in sql
    assert "t.exit_time IS NOT NULL" not in sql
    conn.rollback.assert_called_once()


def test_writer_esegue_rollback_su_errore():
    store, conn, cursor = _store_and_cursor()
    cursor.executemany.side_effect = RuntimeError("db down")

    try:
        store.write_s4_exit_policy_events([_event()])
    except RuntimeError:
        pass
    else:
        raise AssertionError("write_s4_exit_policy_events must propagate failures")

    conn.rollback.assert_called_once()
