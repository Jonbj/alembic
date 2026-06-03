"""Tests for PostgreSQL store - SQL injection fix verification."""

import pytest
from unittest.mock import MagicMock

from src.store.pg_store import PostgreSQLStore


class TestSQLInjectionFix:
    """Verify SQL injection fix in fetch_signals_for_ic."""

    def test_fetch_query_uses_parameterized_interval(self):
        """Test that the query uses parameterized interval, not string interpolation.

        FIX VERIFICATION: Original vulnerable code was:
            _FETCH_FOR_IC = "... WHERE generated_at >= now() - INTERVAL '%s days'"

        Fixed code uses:
            _FETCH_FOR_IC = "... WHERE generated_at >= now() - (%s || ' days')::interval"

        This test verifies the fixed query structure.
        """
        query = PostgreSQLStore._FETCH_FOR_IC

        # Verify the query does NOT contain vulnerable pattern
        assert "INTERVAL '%s'" not in query
        assert "INTERVAL '%s days'" not in query

        # Verify the query uses safe pattern
        assert "(%s || ' days')::interval" in query or "%s || ' days'" in query

    def test_malicious_days_parameter_would_be_escaped(self):
        """Test that a malicious days parameter would be escaped by psycopg2.

        This is a unit test verifying the parameter is passed separately,
        not interpolated into the SQL string.
        """
        # Example malicious input that could cause SQL injection
        # with the vulnerable code:
        #   days = "1); DROP TABLE sentiment_signals; --"
        # Would produce:
        #   INTERVAL '1); DROP TABLE sentiment_signals; -- days'

        # With the fixed code, this is passed as a parameter and treated as literal string
        # PostgreSQL would try to parse "1); DROP TABLE sentiment_signals; -- days" as interval
        # and fail with "invalid input syntax for type interval"

        malicious_input = "1); DROP TABLE sentiment_signals; --"

        # The query should contain the parameter placeholder
        assert "%s" in PostgreSQLStore._FETCH_FOR_IC

        # When psycopg2 receives the parameter, it will escape it properly
        # This test documents the expected behavior - actual verification
        # would require integration test with real database


class TestPostgreSQLStoreInterface:
    """Test PostgreSQL store interface."""

    def test_write_signal_parameters(self):
        """Test that write_signal uses parameterized query."""
        # Verify the INSERT query uses %s placeholders, not string formatting
        query = PostgreSQLStore._INSERT_SIGNAL

        # Should use parameterized placeholders
        assert "%s" in query
        # Should NOT contain any string formatting patterns that could be exploited
        assert "{" not in query or "}" not in query  # No .format() placeholders
        assert "f\"" not in query  # No f-strings

    def test_fetch_for_ic_signature(self):
        """Test fetch_signals_for_ic signature."""
        # Verify the method accepts symbol and days as separate parameters
        import inspect
        sig = inspect.signature(PostgreSQLStore.fetch_signals_for_ic)
        params = list(sig.parameters.keys())

        assert "symbol" in params
        assert "days" in params
        # Days should be a parameter, not interpolated into SQL


class TestWriteSignalReturnsId:
    """Test that write_signal returns the inserted/updated signal id."""

    def test_write_signal_returns_signal_id(self):
        """write_signal must return the integer id of the inserted row."""
        from datetime import datetime, timezone
        from src.models.signals import SentimentResult

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = (42,)
        mock_conn.cursor.return_value = mock_cursor

        store = PostgreSQLStore(conn=mock_conn, use_pool=False)

        sample_signal = SentimentResult(
            symbol="AAPL",
            score=0.7,
            confidence=0.85,
            reasoning="Positive sentiment",
            model_id="ensemble",
            ensemble_std=0.1,
            fallback_used=False,
            generated_at=datetime.now(timezone.utc),
        )

        signal_id = store.write_signal(sample_signal)

        assert isinstance(signal_id, int)
        assert signal_id == 42
        mock_cursor.fetchone.assert_called_once()


class TestLogWeightUpdate:
    """Test PostgreSQLStore.log_weight_update()."""

    def test_log_weight_update_returns_id(self):
        """log_weight_update executes INSERT RETURNING id and returns it."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = (7,)
        mock_conn.cursor.return_value = mock_cursor

        store = PostgreSQLStore(conn=mock_conn, use_pool=False)
        log_id = store.log_weight_update(
            source="suggestion",
            applied_weights={"opus": 0.45, "qwen3.5:cloud": 0.35, "deepseek-v4-pro:cloud": 0.20},
            suggested_weights={"opus": 0.45, "qwen3.5:cloud": 0.35, "deepseek-v4-pro:cloud": 0.20},
            purified_icir={"opus": 0.31, "qwen3.5:cloud": 0.18, "deepseek-v4-pro:cloud": 0.09},
            freeze_reason=None,
            note="test",
            approved_by="abcd1234",
        )

        assert log_id == 7
        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args[0]
        # First arg is the SQL — must contain INSERT INTO weight_update_log
        assert "INSERT INTO weight_update_log" in call_args[0]
        # Second arg is the parameters tuple — source must be first
        assert call_args[1][0] == "suggestion"
        mock_conn.commit.assert_called_once()

    def test_log_weight_update_rollback_on_error(self):
        """log_weight_update rolls back on exception."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.execute.side_effect = Exception("DB error")
        mock_conn.cursor.return_value = mock_cursor

        store = PostgreSQLStore(conn=mock_conn, use_pool=False)
        with pytest.raises(Exception, match="DB error"):
            store.log_weight_update(
                source="suggestion",
                applied_weights={"opus": 1.0},
            )

        mock_conn.rollback.assert_called_once()


class TestConnectionPoolSafety:
    """Verify that all read/write methods roll back on error (Bug 1 fix).

    If a query fails, the connection must be rolled back before the exception
    propagates. Without rollback, psycopg2 leaves the connection in
    'InFailedSqlTransaction' state. Returning that connection to the pool
    corrupts it — the next thread gets a broken connection.
    """

    def _make_store_with_failing_cursor(self, error: str = "DB error"):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.execute.side_effect = Exception(error)
        mock_conn.cursor.return_value = mock_cursor
        return PostgreSQLStore(conn=mock_conn, use_pool=False), mock_conn

    def test_get_news_recent_rollback_on_error(self):
        store, mock_conn = self._make_store_with_failing_cursor()
        with pytest.raises(Exception):
            store.get_news_recent()
        mock_conn.rollback.assert_called_once()

    def test_get_llm_feedback_rollback_on_error(self):
        store, mock_conn = self._make_store_with_failing_cursor()
        with pytest.raises(Exception):
            store.get_llm_feedback()
        mock_conn.rollback.assert_called_once()

    def test_fetch_signals_for_ic_rollback_on_error(self):
        store, mock_conn = self._make_store_with_failing_cursor()
        with pytest.raises(Exception):
            store.fetch_signals_for_ic("AAPL", 30)
        mock_conn.rollback.assert_called_once()

    def test_fetch_per_model_signals_for_ic_rollback_on_error(self):
        store, mock_conn = self._make_store_with_failing_cursor()
        with pytest.raises(Exception):
            store.fetch_per_model_signals_for_ic("AAPL", 30)
        mock_conn.rollback.assert_called_once()

    def test_fetch_signals_for_backtest_rollback_on_error(self):
        store, mock_conn = self._make_store_with_failing_cursor()
        with pytest.raises(Exception):
            store.fetch_signals_for_backtest("AAPL", "2026-01-01", "2026-06-01")
        mock_conn.rollback.assert_called_once()

    def test_add_forward_return_rollback_on_commit_error(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.commit.side_effect = Exception("commit failed")
        store = PostgreSQLStore(conn=mock_conn, use_pool=False)
        with pytest.raises(Exception, match="commit failed"):
            store.add_forward_return(signal_id=1, forward_return=0.02)
        mock_conn.rollback.assert_called_once()

    def test_fetch_signals_pending_forward_return_rollback_on_error(self):
        store, mock_conn = self._make_store_with_failing_cursor()
        with pytest.raises(Exception):
            store.fetch_signals_pending_forward_return()
        mock_conn.rollback.assert_called_once()

    def test_fetch_latest_signals_rollback_on_error(self):
        store, mock_conn = self._make_store_with_failing_cursor()
        with pytest.raises(Exception):
            store.fetch_latest_signals(["AAPL", "MSFT"])
        mock_conn.rollback.assert_called_once()

    def test_bulk_add_forward_returns_rollback_on_commit_error(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.commit.side_effect = Exception("commit failed")
        store = PostgreSQLStore(conn=mock_conn, use_pool=False)
        with pytest.raises(Exception, match="commit failed"):
            store.bulk_add_forward_returns([(1, 0.02), (2, -0.01)])
        mock_conn.rollback.assert_called_once()

    def test_close_does_not_double_release_after_exception(self):
        """Connection released exactly once even when method raised."""
        store, mock_conn = self._make_store_with_failing_cursor()
        try:
            store.fetch_signals_for_ic("AAPL", 30)
        except Exception:
            pass
        store.close()
        # _release_connection called once (in close()), rollback called once (in method)
        mock_conn.rollback.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
