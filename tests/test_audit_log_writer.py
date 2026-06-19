"""P0-12 (WS-13) — audit_log writer tests.

The audit_log table exists in the DB schema (migrations/001_initial.sql)
but PostgreSQLStore has no method to write to it — the audit chain is dead.
These tests are RED until write_audit_log() is added to PostgreSQLStore.
"""

import json
from unittest.mock import MagicMock, call

import pytest

from src.store.pg_store import PostgreSQLStore


class TestAuditLogWriterExists:
    """Verify the write_audit_log method exists before testing behavior."""

    def test_pg_store_has_write_audit_log(self):
        """PostgreSQLStore must expose write_audit_log() (WS-13 / P0-12)."""
        assert hasattr(PostgreSQLStore, "write_audit_log"), (
            "PostgreSQLStore.write_audit_log() is missing.\n"
            "The audit_log table exists in migrations/001_initial.sql but nothing "
            "writes to it. Add a synchronous write_audit_log() method."
        )

    def test_write_audit_log_is_callable(self):
        """write_audit_log must be a callable method."""
        assert callable(getattr(PostgreSQLStore, "write_audit_log", None))


class TestAuditLogWriterBehavior:
    """Verify write_audit_log inserts a row with the expected SQL."""

    @pytest.fixture()
    def store_with_mock_conn(self):
        """Return a PostgreSQLStore wired to a mock DB connection."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        store = PostgreSQLStore.__new__(PostgreSQLStore)
        store._get_connection = MagicMock(return_value=mock_conn)
        store._conn = mock_conn
        return store, mock_conn, mock_cursor

    def test_write_audit_log_calls_insert(self, store_with_mock_conn):
        """write_audit_log must execute an INSERT into audit_log."""
        store, _, mock_cursor = store_with_mock_conn

        store.write_audit_log(
            action="INSERT",
            table_name="trades",
            record_id=42,
            details={"symbol": "AAPL", "qty": 10},
        )

        assert mock_cursor.execute.called, (
            "write_audit_log did not call cursor.execute — no row was inserted."
        )
        sql, _params = mock_cursor.execute.call_args[0]
        assert "audit_log" in sql.lower(), (
            f"execute() was called but the SQL does not reference audit_log: {sql!r}"
        )

    def test_write_audit_log_passes_action_as_param(self, store_with_mock_conn):
        """The action value must be passed as a query parameter, not interpolated."""
        store, _, mock_cursor = store_with_mock_conn

        store.write_audit_log(
            action="KILLSWITCH_ACTIVATE",
            table_name="system",
            record_id=None,
            details={"reason": "manual"},
        )

        _sql, params = mock_cursor.execute.call_args[0]
        # action must appear in the params tuple, not baked into SQL
        assert any(
            "KILLSWITCH_ACTIVATE" in str(p) for p in params
        ), f"action not found in query params: {params}"

    def test_write_audit_log_commits(self, store_with_mock_conn):
        """write_audit_log must commit the transaction."""
        store, mock_conn, _ = store_with_mock_conn

        store.write_audit_log(
            action="INSERT",
            table_name="trades",
            record_id=1,
            details={},
        )

        mock_conn.commit.assert_called_once()


class TestOpenTradeTransactionalAudit:
    """open_trade must write the audit row in the same transaction as the trade INSERT (P0-12 follow-up)."""

    @pytest.fixture()
    def store_with_mock_conn(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        store = PostgreSQLStore.__new__(PostgreSQLStore)
        store._get_connection = MagicMock(return_value=mock_conn)
        store._conn = mock_conn
        return store, mock_conn, mock_cursor

    def test_open_trade_audit_row_includes_record_id(self, store_with_mock_conn):
        """open_trade must pass the returned trade id to the audit row as record_id."""
        store, mock_conn, mock_cursor = store_with_mock_conn
        # Simulate RETURNING id returning trade id = 77
        mock_cursor.fetchone.return_value = (77,)

        store.open_trade(
            symbol="AAPL",
            signal_id=1,
            decision_id=2,
            entry_order_id="ord-001",
            entry_time="2026-06-19T10:00:00Z",
            entry_notional=5000.0,
            score=0.05,
            regime_mult=1.0,
            qty=33.0,
            signal_score=0.7,
        )

        # Find the audit log INSERT call
        all_sql_calls = [str(c[0][0]) for c in mock_cursor.execute.call_args_list]
        audit_calls = [s for s in all_sql_calls if "audit_log" in s.lower()]
        assert audit_calls, "No audit_log INSERT found in open_trade — audit must be written transactionally"

        # Find params for the audit INSERT
        audit_call_idx = next(
            i for i, c in enumerate(mock_cursor.execute.call_args_list)
            if "audit_log" in str(c[0][0]).lower()
        )
        audit_params = mock_cursor.execute.call_args_list[audit_call_idx][0][1]
        # record_id is the 3rd positional param in _INSERT_AUDIT_LOG: (action, table_name, record_id, details)
        assert audit_params[2] == 77, (
            f"audit_log record_id must be the trade's returned id (77), got: {audit_params[2]}"
        )

    def test_open_trade_audit_and_trade_in_same_commit(self, store_with_mock_conn):
        """open_trade must commit exactly once — both INSERT and audit in a single transaction."""
        store, mock_conn, mock_cursor = store_with_mock_conn
        mock_cursor.fetchone.return_value = (42,)

        store.open_trade(
            symbol="MSFT",
            signal_id=None,
            decision_id=None,
            entry_order_id="ord-002",
            entry_time="2026-06-19T10:05:00Z",
            entry_notional=3000.0,
            score=0.03,
            regime_mult=0.8,
            qty=10.0,
            signal_score=0.6,
        )

        assert mock_conn.commit.call_count == 1, (
            f"open_trade must commit exactly once (got {mock_conn.commit.call_count}). "
            "Both the trade INSERT and audit INSERT must be in the same transaction."
        )

    def test_open_trade_rolls_back_if_audit_fails(self, store_with_mock_conn):
        """If the audit INSERT fails, the entire transaction must be rolled back."""
        store, mock_conn, mock_cursor = store_with_mock_conn
        # First execute (trade INSERT) succeeds; second (audit) raises
        mock_cursor.fetchone.return_value = (99,)
        call_count = [0]
        def execute_side_effect(sql, params=None):
            call_count[0] += 1
            if call_count[0] >= 2:
                raise Exception("audit DB error")
        mock_cursor.execute.side_effect = execute_side_effect

        with pytest.raises(Exception, match="audit DB error"):
            store.open_trade(
                symbol="GOOG",
                signal_id=None,
                decision_id=None,
                entry_order_id="ord-003",
                entry_time="2026-06-19T10:10:00Z",
                entry_notional=2000.0,
                score=0.02,
                regime_mult=1.0,
                qty=5.0,
                signal_score=0.5,
            )

        mock_conn.rollback.assert_called(), (
            "open_trade must rollback when the audit INSERT fails — "
            "a trade without an audit row must not be committed"
        )
        mock_conn.commit.assert_not_called()
