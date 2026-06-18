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
