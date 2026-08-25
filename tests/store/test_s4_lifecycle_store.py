"""#295: persistenza append-only del lifecycle S4 al confine broker."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from src.store.pg_store import PostgreSQLStore
from src.strategies.s4.lifecycle import (
    BrokerOrderSnapshot,
    SubmittedIntent,
    apply_virtual_s4_exit,
    reconcile_entry,
)


UTC = timezone.utc
TS = datetime(2026, 8, 25, 15, 7, tzinfo=UTC)


def _store_and_cursor():
    conn = MagicMock()
    cursor = MagicMock()
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cursor
    return PostgreSQLStore(conn=conn, use_pool=False), conn, cursor


def _intent() -> SubmittedIntent:
    return SubmittedIntent(
        intent_id="34d6c4c0-bcb2-55ef-a0f4-e3db1a4a13b0",
        symbol="AMD",
        order_id="alpaca-order-1",
        submitted_at=TS,
        requested_quantity=2.0,
        requested_notional=210.0,
        first_executable_price=105.0,
        first_executable_price_source="alpaca_snapshot.latest_trade",
        policy_version="s4-exit-trial:1.0.0",
        sleeve_contributions={"S4": 0.01},
    )


def _entry():
    return reconcile_entry(
        _intent(),
        BrokerOrderSnapshot(
            order_id="alpaca-order-1",
            status="filled",
            filled_at=TS,
            filled_quantity=2.0,
            filled_avg_price=105.25,
        ),
        sessions=[],
        observed_at=TS,
        broker_position_quantity=2.0,
    )


def test_migrazione_rende_eventi_append_only_e_offre_viste_di_coverage():
    migration = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "051_s4_shadow_lifecycle.sql"
    ).read_text()

    assert "CREATE TABLE IF NOT EXISTS s4_lifecycle_events" in migration
    assert "prevent_s4_lifecycle_event_mutation" in migration
    assert "CREATE VIEW s4_lifecycle_current" in migration
    assert "CREATE VIEW s4_lifecycle_validation" in migration
    assert "CREATE VIEW s4_lifecycle_residuals" in migration
    assert "reconstructible" in migration
    assert "unattributed_quantity" in migration
    assert "fill_price" in migration


def test_writer_accetta_entry_ed_exit_virtuale_con_idempotenza():
    store, conn, cursor = _store_and_cursor()
    entry = _entry()
    virtual_exit = apply_virtual_s4_exit(
        entry,
        quantity=0.5,
        price=110.0,
        observed_at=datetime(2026, 8, 27, 19, 55, tzinfo=UTC),
        reason_code="P1_TIME_DUE",
    )

    store.write_s4_lifecycle_events([entry, virtual_exit])

    cursor.executemany.assert_called_once()
    sql, params = cursor.executemany.call_args.args
    assert "INSERT INTO s4_lifecycle_events" in sql
    assert "ON CONFLICT (event_id) DO NOTHING" in sql
    assert len(params) == 2
    assert params[0][0] == entry.event_id
    assert params[1][0] == virtual_exit.event_id
    assert params[1][5] is None  # nessun order_id broker per una exit virtuale
    conn.commit.assert_called_once()


def test_fetch_submitted_intents_mappa_snapshot_e_versione_senza_inferenze():
    store, _, cursor = _store_and_cursor()
    cursor.fetchall.return_value = [{
        "intent_id": "34d6c4c0-bcb2-55ef-a0f4-e3db1a4a13b0",
        "symbol": "AMD",
        "order_id": "alpaca-order-1",
        "submitted_at": TS,
        "requested_quantity": 2.0,
        "requested_notional": 210.0,
        "first_executable_price": 105.0,
        "first_executable_price_source": "alpaca_snapshot.latest_trade",
        "policy_version": "s4-exit-trial:1.0.0",
        "sleeve_contributions": {"S1": 0.05, "S4": 0.01},
        "submission_reason_code": "SUBMITTED",
        "submission_error": None,
    }]

    [intent] = store.fetch_s4_submitted_intents()

    assert intent == SubmittedIntent(
        intent_id="34d6c4c0-bcb2-55ef-a0f4-e3db1a4a13b0",
        symbol="AMD",
        order_id="alpaca-order-1",
        submitted_at=TS,
        requested_quantity=2.0,
        requested_notional=210.0,
        first_executable_price=105.0,
        first_executable_price_source="alpaca_snapshot.latest_trade",
        policy_version="s4-exit-trial:1.0.0",
        sleeve_contributions={"S1": 0.05, "S4": 0.01},
        submission_reason_code="SUBMITTED",
        submission_error=None,
    )
    sql = cursor.execute.call_args.args[0]
    assert "event_type = 'disposition'" in sql
    assert "reason_code IN ('SUBMITTED', 'BROKER_REJECT')" in sql


def test_fetch_include_reject_pre_ack_senza_inventare_un_order_id():
    store, _, cursor = _store_and_cursor()
    cursor.fetchall.return_value = [{
        "intent_id": "34d6c4c0-bcb2-55ef-a0f4-e3db1a4a13b0",
        "symbol": "AMD",
        "order_id": None,
        "submitted_at": TS,
        "requested_quantity": 2.0,
        "requested_notional": 210.0,
        "first_executable_price": 105.0,
        "first_executable_price_source": "portfolio_market_snapshot.latest_price",
        "policy_version": "s4-exit-trial:1.0.0",
        "sleeve_contributions": {"S4": 0.01},
        "submission_reason_code": "BROKER_REJECT",
        "submission_error": "APIError",
    }]

    [intent] = store.fetch_s4_submitted_intents()

    assert intent.order_id is None
    assert intent.submission_reason_code == "BROKER_REJECT"
    assert intent.submission_error == "APIError"


def test_writer_rollback_su_errore():
    store, conn, cursor = _store_and_cursor()
    cursor.executemany.side_effect = RuntimeError("db down")

    try:
        store.write_s4_lifecycle_events([_entry()])
    except RuntimeError:
        pass
    else:
        raise AssertionError("write_s4_lifecycle_events must propagate failures")

    conn.rollback.assert_called_once()
