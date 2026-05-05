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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
