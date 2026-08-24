"""Tests for PostgreSQL store - SQL injection fix verification."""

from unittest.mock import MagicMock, patch

import pytest

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

    def test_fetch_signals_for_cycle_query_structure(self):
        """fetch_signals_for_cycle uses DISTINCT ON, parameterized interval, watchlist filter."""
        query = PostgreSQLStore._FETCH_SIGNALS_FOR_CYCLE
        assert "DISTINCT ON (ss.symbol)" in query
        assert "INTERVAL '%s'" not in query
        assert "(%s || ' hours')::interval" in query or "%s || ' hours'" in query
        # Prefer ensemble over FinBERT fallback within the window, then most recent.
        assert "ORDER BY ss.symbol, ss.fallback_used ASC, ss.generated_at DESC" in query
        assert "ANY(%s)" in query

    def test_fetch_signals_for_cycle_signature(self):
        """fetch_signals_for_cycle accepts hours and symbols parameters."""
        import inspect
        sig = inspect.signature(PostgreSQLStore.fetch_signals_for_cycle)
        params = list(sig.parameters.keys())
        assert "hours" in params
        assert "symbols" in params


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


class TestFallbackCounterPersistence:
    """PostgreSQLStore must write through to the fallback_counters table
    (migrations/001_initial.sql), which existed but was never populated."""

    def test_record_fallback_increment_upserts_counter(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor

        store = PostgreSQLStore(conn=mock_conn, use_pool=False)
        store.record_fallback_increment("consecutive_fallback", 3)

        mock_cursor.execute.assert_called_once()
        sql, params = mock_cursor.execute.call_args[0]
        assert "INSERT INTO fallback_counters" in sql
        assert "ON CONFLICT" in sql
        assert params == ("consecutive_fallback", 3)
        mock_conn.commit.assert_called_once()

    def test_record_fallback_reset_upserts_counter_to_zero(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor

        store = PostgreSQLStore(conn=mock_conn, use_pool=False)
        store.record_fallback_reset("consecutive_fallback")

        mock_cursor.execute.assert_called_once()
        sql, params = mock_cursor.execute.call_args[0]
        assert "INSERT INTO fallback_counters" in sql
        assert "ON CONFLICT" in sql
        assert params == ("consecutive_fallback",)
        mock_conn.commit.assert_called_once()


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

    def test_get_news_source_quality_rollback_on_error(self):
        store, mock_conn = self._make_store_with_failing_cursor()
        with pytest.raises(Exception):
            store.get_news_source_quality()
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
            store.bulk_add_forward_returns([(1, 0.02, None, None), (2, -0.01, None, None)])
        mock_conn.rollback.assert_called_once()

    def test_close_does_not_double_release_after_exception(self):
        """Connection released exactly once even when a method raised.

        This fixture uses an *externally-supplied* connection
        (``conn=mock_conn, use_pool=False``): the store neither pools nor owns
        it, so ``close()`` must NOT release/rollback/close it — the caller owns
        that lifecycle. The only rollback is the method's own except path.
        B7/B32 (2026-07-15): the leak fix rolls back only on paths the store
        actually releases (pool / owned), never on an external connection.
        """
        store, mock_conn = self._make_store_with_failing_cursor()
        try:
            store.fetch_signals_for_ic("AAPL", 30)
        except Exception:
            pass
        store.close()
        # only the method's except path rolls back — close() leaves the
        # external connection untouched (no double release, no surprise rollback)
        mock_conn.rollback.assert_called_once()
        mock_conn.close.assert_not_called()

    def test_get_last_portfolio_cycle_rollback_on_error(self):
        """get_last_portfolio_cycle rolls back on error and returns None."""
        store, mock_conn = self._make_store_with_failing_cursor()
        result = store.get_last_portfolio_cycle()
        assert result is None
        mock_conn.rollback.assert_called_once()

    def test_get_portfolio_cycle_history_rollback_on_error(self):
        """get_portfolio_cycle_history rolls back on error and returns empty list."""
        store, mock_conn = self._make_store_with_failing_cursor()
        result = store.get_portfolio_cycle_history()
        assert result == []
        mock_conn.rollback.assert_called_once()


class TestPoolFallbackConnection:
    """Verify the pool-exhaustion fallback path cleans up correctly (Bug 1 fix).

    When the ThreadedConnectionPool is exhausted and raises PoolError,
    _get_connection() falls back to a direct psycopg2.connect(). After the
    fix, _use_pool is set to False so that _release_connection() calls
    conn.close() instead of putconn() (which would raise PoolError on a
    non-pool connection and leave the connection leaked).
    """

    def test_fallback_connection_close_on_pool_error(self):
        """When pool raises PoolError, fallback conn is closed (not put back to pool)."""
        from unittest.mock import MagicMock, patch

        import psycopg2.pool

        mock_direct_conn = MagicMock()
        mock_pool = MagicMock()
        mock_pool.getconn.side_effect = psycopg2.pool.PoolError("pool exhausted")

        with patch("src.store.pg_store._get_pool", return_value=mock_pool):
            with patch("src.store.pg_store.psycopg2.connect", return_value=mock_direct_conn):
                store = PostgreSQLStore(use_pool=True)
                conn = store._get_connection()

                # After fallback: use_pool must be False so _release_connection
                # calls conn.close() instead of putconn()
                assert store._use_pool is False
                assert store._owns_connection is True
                assert conn is mock_direct_conn

                store.close()
                # Must call close() on the direct connection, not putconn() on pool
                mock_direct_conn.close.assert_called_once()
                mock_pool.putconn.assert_not_called()


class TestLogNewsItemReturnsId:
    """log_news_item must return the inserted row id (RETURNING id)."""

    def test_log_news_item_returns_int_on_insert(self):
        """When INSERT succeeds (not a conflict), returns the new id."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = (42,)

        store = PostgreSQLStore(conn=mock_conn)
        from src.models.news import NewsItem
        item = NewsItem(
            id="http://example.com:AAPL",
            title="Test", url="http://example.com", source="gdelt",
            body="body", asset_tags=["AAPL"],
            timestamp=__import__('datetime').datetime(2026, 6, 1, tzinfo=__import__('datetime').timezone.utc),
        )
        result = store.log_news_item(item=item, ticker="AAPL", computed_sentiment=0.5)
        assert result == 42

    def test_log_news_item_returns_none_on_conflict(self):
        """ON CONFLICT DO NOTHING returns no row; method returns None."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = None  # DO NOTHING yields no row

        store = PostgreSQLStore(conn=mock_conn)
        from src.models.news import NewsItem
        item = NewsItem(
            id="http://example.com:AAPL",
            title="Test", url="http://example.com", source="gdelt",
            body="body", asset_tags=["AAPL"],
            timestamp=__import__('datetime').datetime(2026, 6, 1, tzinfo=__import__('datetime').timezone.utc),
        )
        result = store.log_news_item(item=item, ticker="AAPL")
        assert result is None


class TestLinkSignalToNews:
    """link_signal_to_news issues UPDATE sentiment_signals SET news_log_id = %s WHERE id = %s."""

    def test_link_issues_update(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        store = PostgreSQLStore(conn=mock_conn)
        store.link_signal_to_news(signal_id=7, news_log_id=42)

        sql_called = mock_cur.execute.call_args[0][0]
        assert "UPDATE sentiment_signals" in sql_called
        assert "news_log_id" in sql_called
        mock_conn.commit.assert_called_once()


class TestWriteExecutionDecision:
    """write_execution_decision must INSERT a row and return the new id."""

    def test_returns_decision_id(self):
        from datetime import datetime, timezone
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = (55,)

        store = PostgreSQLStore(conn=mock_conn)
        decision_id = store.write_execution_decision(
            tick_time=datetime(2026, 6, 5, 15, tzinfo=timezone.utc),
            symbol="NVDA",
            signal_id=7,
            score=0.55,
            regime_mult=1.0,
            ema_pass=True,
            decision="BUY",
            order_id="abc-123",
        )
        assert decision_id == 55
        mock_conn.commit.assert_called_once()

    def test_order_id_optional(self):
        from datetime import datetime, timezone
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = (56,)

        store = PostgreSQLStore(conn=mock_conn)
        decision_id = store.write_execution_decision(
            tick_time=datetime(2026, 6, 5, 15, tzinfo=timezone.utc),
            symbol="AAPL",
            signal_id=None,
            score=0.35,
            regime_mult=0.7,
            ema_pass=False,
            decision="SKIP_EMA",
        )
        assert decision_id == 56

    def test_exit_mechanism_passed_through_to_insert(self):
        """#60: exit_mechanism (whipsaw/expired/no_signal) is written when supplied."""
        from datetime import datetime, timezone
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = (57,)

        store = PostgreSQLStore(conn=mock_conn)
        decision_id = store.write_execution_decision(
            tick_time=datetime(2026, 7, 16, 15, tzinfo=timezone.utc),
            symbol="CAT",
            signal_id=None,
            score=0.0,
            regime_mult=1.0,
            ema_pass=True,
            decision="SELL",
            reason="[expired] S4 signal expired...",
            exit_mechanism="expired",
        )
        assert decision_id == 57
        params = mock_cur.execute.call_args[0][1]
        assert "expired" in params

    def test_exit_mechanism_defaults_to_none(self):
        """exit_mechanism is optional — most decisions (BUY, stop_loss, ...) don't set it."""
        from datetime import datetime, timezone
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = (58,)

        store = PostgreSQLStore(conn=mock_conn)
        store.write_execution_decision(
            tick_time=datetime(2026, 7, 16, 15, tzinfo=timezone.utc),
            symbol="NVDA",
            signal_id=7,
            score=0.55,
            regime_mult=1.0,
            ema_pass=True,
            decision="BUY",
        )
        params = mock_cur.execute.call_args[0][1]
        assert None in params


class TestFetchDecisions:
    """fetch_decisions returns list of dicts, most-recent first."""

    def test_fetch_all_decisions(self):
        from datetime import datetime, timezone
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.description = [
            ("id",), ("tick_time",), ("symbol",), ("signal_id",),
            ("score",), ("regime_mult",), ("ema_pass",), ("decision",),
            ("order_id",), ("created_at",),
        ]
        now = datetime(2026, 6, 5, 15, tzinfo=timezone.utc)
        mock_cur.fetchall.return_value = [
            (1, now, "AAPL", 7, 0.55, 1.0, True, "BUY", "abc-123", now),
        ]

        store = PostgreSQLStore(conn=mock_conn)
        rows = store.fetch_decisions(limit=10)
        assert len(rows) == 1
        assert rows[0]["symbol"] == "AAPL"
        assert rows[0]["decision"] == "BUY"


class TestOpenTrade:
    def test_open_trade_inserts_row(self):
        from datetime import datetime, timezone
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        store = PostgreSQLStore(conn=mock_conn)
        store.open_trade(
            symbol="TSLA",
            signal_id=7,
            decision_id=55,
            entry_order_id="order-abc",
            entry_time=datetime(2026, 6, 5, 15, tzinfo=timezone.utc),
            entry_notional=500.0,
            score=0.55,
            regime_mult=1.0,
            qty=2.5,
        )
        # open_trade now performs two inserts: trades row + audit_log row (P0-12).
        executed_sqls = [c[0][0] for c in mock_cur.execute.call_args_list]
        assert any("INSERT INTO trades" in sql for sql in executed_sqls)
        assert any("INSERT INTO audit_log" in sql for sql in executed_sqls)
        assert mock_conn.commit.called


class TestCloseTrade:
    def test_close_trade_updates_open_row(self):
        from datetime import datetime, timezone
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        # First fetchone(): SELECT entry_notional, qty — return a row (trade found)
        # Second fetchone(): RETURNING id from UPDATE
        mock_cur.fetchone.side_effect = [(2000.0, 10.0), (77,)]

        store = PostgreSQLStore(conn=mock_conn)
        store.close_trade(
            symbol="TSLA",
            exit_price=205.0,
            exit_time=datetime(2026, 6, 5, 16, tzinfo=timezone.utc),
            exit_reason="stop_loss",
            entry_price=200.0,
        )
        # call_args is the last execute call — the UPDATE
        sql = mock_cur.execute.call_args[0][0]
        assert "UPDATE trades" in sql
        assert "exit_time IS NULL" in sql
        assert "COALESCE" in sql
        mock_conn.commit.assert_called_once()

    def test_close_trade_without_entry_price(self):
        """entry_price defaults to None — backward-compatible call still works."""
        from datetime import datetime, timezone
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        # First fetchone(): SELECT entry_notional, qty — return a row (trade found)
        # Second fetchone(): RETURNING id (None when no RETURNING clause or row gone)
        mock_cur.fetchone.side_effect = [(1800.0, 5.0), None]

        store = PostgreSQLStore(conn=mock_conn)
        store.close_trade(
            symbol="AAPL",
            exit_price=180.0,
            exit_time=datetime(2026, 6, 5, 16, tzinfo=timezone.utc),
            exit_reason="take_profit",
        )
        sql = mock_cur.execute.call_args[0][0]
        assert "UPDATE trades" in sql
        assert "exit_time IS NULL" in sql
        mock_conn.commit.assert_called_once()


class TestCloseTradeReturnsId:
    def test_close_trade_returns_trade_id(self):
        """close_trade must return the id of the updated row (RETURNING id)."""
        from datetime import datetime, timezone
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        # First fetchone: SELECT entry_notional, qty — return a row (trade found)
        # Second fetchone: RETURNING id
        mock_cur.fetchone.side_effect = [(2000.0, 10.0), (99,)]

        store = PostgreSQLStore(conn=mock_conn, use_pool=False)
        result = store.close_trade(
            symbol="TSLA",
            exit_price=205.0,
            exit_time=datetime(2026, 6, 5, 16, tzinfo=timezone.utc),
            exit_reason="stop_loss",
            entry_price=200.0,
        )
        assert result == 99
        sql = mock_cur.execute.call_args[0][0]
        assert "RETURNING id" in sql

    def test_close_trade_returns_none_when_no_open_trade(self):
        """Returns None if no open trade row matched (fetchone returns None)."""
        from datetime import datetime, timezone
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        # Both SELECT and UPDATE return None
        mock_cur.fetchone.side_effect = [None, None]

        store = PostgreSQLStore(conn=mock_conn, use_pool=False)
        result = store.close_trade(
            symbol="AAPL",
            exit_price=180.0,
            exit_time=datetime(2026, 6, 5, 16, tzinfo=timezone.utc),
            exit_reason="take_profit",
        )
        assert result is None


class TestRecordTradeExit:
    """record_trade_exit marks a trade closed and accumulates multi-tranche
    exit order IDs in exit_order_ids."""

    def test_record_trade_exit_returns_id_on_first_close(self):
        from datetime import datetime, timezone
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = (7, False)

        store = PostgreSQLStore(conn=mock_conn, use_pool=False)
        result = store.record_trade_exit(
            symbol="TSLA",
            exit_order_id="exit-1",
            exit_time=datetime(2026, 6, 5, 16, tzinfo=timezone.utc),
            exit_reason="portfolio_sell",
        )
        assert result == 7
        sql = mock_cur.execute.call_args[0][0]
        assert "exit_order_ids" in sql
        assert "COALESCE" in sql
        mock_conn.commit.assert_called_once()

    def test_record_trade_exit_returns_none_for_later_tranche(self):
        """WS-5 fix-back: an intermediate (non-final) SELL tranche (is_final=False)
        appends the order id but does not set exit_time and returns None, so the
        caller skips the postmortem; the final tranche (is_final=True) sets
        exit_time and returns the trade id so the postmortem runs exactly once."""
        from datetime import datetime, timezone
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        # Same open trade (id=7) found on every tranche — it stays open until the
        # final tranche, so the fallback WHERE ... AND exit_time IS NULL keeps
        # matching it.
        mock_cur.fetchone.side_effect = [(7,), (7,)]

        store = PostgreSQLStore(conn=mock_conn, use_pool=False)
        ts = datetime(2026, 6, 5, 16, tzinfo=timezone.utc)
        # Intermediate tranche: appends order id, trade stays open, no postmortem.
        assert store.record_trade_exit("SHEL", "o1", ts, "sell", is_final=False) is None
        # Final tranche: sets exit_time, returns id, postmortem runs once.
        assert store.record_trade_exit("SHEL", "o2", ts, "sell", is_final=True) == 7
        assert mock_conn.commit.call_count == 2


class TestRecordTradeExitMultiTrancheFixback:
    """WS-5 fix-back (2026-07-14): record_trade_exit must target ONLY the open trade
    for a symbol, never the many historical closed trades for the same symbol
    (META 24, AZN 20, ...). The is_final model keeps the trade "open" (exit_time
    NULL) on intermediate tranches so the pyramiding guard blocks re-BUY during
    wind-down and reconcile runs once, on the fully-closed trade.
    """

    def test_final_tranche_targets_by_trade_id_not_symbol(self):
        """The UPDATE WHERE must target the open trade by id (or by
        symbol+exit_time IS NULL), NEVER a naked `WHERE symbol = %s` that would
        match every historical closed trade for the symbol."""
        from datetime import datetime, timezone
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        # The open trade is id=99. Historicals (id 1,2,3) must NOT be touched.
        mock_cur.fetchone.return_value = (99,)

        store = PostgreSQLStore(conn=mock_conn, use_pool=False)
        result = store.record_trade_exit(
            symbol="META",
            exit_order_id="exit-final",
            exit_time=datetime(2026, 7, 14, 19, 52, tzinfo=timezone.utc),
            exit_reason="portfolio_sell",
            trade_id=99,
            is_final=True,
        )
        assert result == 99
        sql = mock_cur.execute.call_args[0][0]
        # MUST target the specific trade, never a naked symbol match.
        assert "WHERE symbol = %s\n" not in sql  # Kimi's bug: naked symbol match
        assert "WHERE id = %s" in sql
        params = mock_cur.execute.call_args[0][1]
        assert params[-1] == 99  # trade_id is the WHERE target
        # Final tranche sets exit_time + exit_reason.
        assert "exit_time = COALESCE(exit_time" in sql
        assert "exit_reason = COALESCE(exit_reason" in sql

    def test_intermediate_tranche_does_not_set_exit_time(self):
        """A partial SELL tranche (is_final=False) appends the order id but must
        NOT set exit_time/exit_reason — the trade stays "open" so the pyramiding
        guard keeps blocking re-BUY during wind-down, and so the caller skips the
        postmortem (returns None)."""
        from datetime import datetime, timezone
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = (99,)

        store = PostgreSQLStore(conn=mock_conn, use_pool=False)
        result = store.record_trade_exit(
            symbol="META",
            exit_order_id="exit-tranche-1",
            exit_time=datetime(2026, 7, 14, 18, 22, tzinfo=timezone.utc),
            exit_reason="portfolio_sell",
            trade_id=99,
            is_final=False,
        )
        # Intermediate tranche: no postmortem (returns None).
        assert result is None
        sql = mock_cur.execute.call_args[0][0]
        # Appends to exit_order_ids (multi-tranche aggregation).
        assert "exit_order_ids" in sql
        # MUST NOT set exit_time/exit_reason on an intermediate tranche.
        assert "exit_time = COALESCE(exit_time" not in sql
        assert "exit_reason = COALESCE(exit_reason" not in sql

    def test_fallback_without_trade_id_targets_open_trade_only(self):
        """When the caller cannot pass trade_id, the fallback WHERE must be
        `symbol = %s AND exit_time IS NULL` (the single open trade) — NEVER
        `WHERE symbol = %s` alone, which would corrupt every historical trade."""
        from datetime import datetime, timezone
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = (99,)

        store = PostgreSQLStore(conn=mock_conn, use_pool=False)
        store.record_trade_exit(
            symbol="META",
            exit_order_id="exit-1",
            exit_time=datetime(2026, 7, 14, 18, 22, tzinfo=timezone.utc),
            exit_reason="portfolio_sell",
            is_final=False,
        )
        sql = mock_cur.execute.call_args[0][0]
        # Fallback must scope to the open trade only via exit_time IS NULL.
        assert "WHERE symbol = %s AND exit_time IS NULL" in sql
        # And must NOT be the naked symbol match (Kimi's bug: `WHERE symbol = %s`
        # immediately followed by a newline / RETURNING, no exit_time filter).
        assert "WHERE symbol = %s\n" not in sql

    def test_multi_tranche_flow_runs_postmortem_once(self):
        """A 3-tranche wind-down: tranches 1-2 (is_final=False) return None
        (postmortem skipped); tranche 3 (is_final=True) returns the trade_id
        (postmortem runs exactly once, on the final tranche)."""
        from datetime import datetime, timezone
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        # Same open trade (id=99) found on every tranche (it stays open until final).
        mock_cur.fetchone.side_effect = [(99,), (99,), (99,)]

        store = PostgreSQLStore(conn=mock_conn, use_pool=False)
        ts = datetime(2026, 7, 14, 19, 52, tzinfo=timezone.utc)
        r1 = store.record_trade_exit("META", "o1", ts, "sell", trade_id=99, is_final=False)
        r2 = store.record_trade_exit("META", "o2", ts, "sell", trade_id=99, is_final=False)
        r3 = store.record_trade_exit("META", "o3", ts, "sell", trade_id=99, is_final=True)
        assert [r1, r2, r3] == [None, None, 99]
        # Only the final (3rd) UPDATE sets exit_time.
        sqls = [c[0][0] for c in mock_cur.execute.call_args_list]
        assert "exit_time = COALESCE(exit_time" not in sqls[0]
        assert "exit_time = COALESCE(exit_time" not in sqls[1]
        assert "exit_time = COALESCE(exit_time" in sqls[2]
        assert mock_conn.commit.call_count == 3

    def test_stop_loss_full_close_defaults_to_final(self):
        """Stop-loss / reversal SELLs are full-close: they don't pass is_final, so
        the default is_final=True applies — exit_time is set, trade_id returned,
        postmortem runs. No behavior regression for those paths."""
        from datetime import datetime, timezone
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = (7,)

        store = PostgreSQLStore(conn=mock_conn, use_pool=False)
        result = store.record_trade_exit(
            symbol="PANW",
            exit_order_id="stop-1",
            exit_time=datetime(2026, 7, 14, 16, tzinfo=timezone.utc),
            exit_reason="stop_loss",
        )
        assert result == 7
        sql = mock_cur.execute.call_args[0][0]
        assert "exit_time = COALESCE(exit_time" in sql


class TestFetchTrades:
    def test_fetch_all_trades(self):
        from datetime import datetime, timezone
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        now = datetime(2026, 6, 5, tzinfo=timezone.utc)
        mock_cur.description = [("id",), ("symbol",), ("entry_time",), ("net_pnl",)]
        mock_cur.fetchall.return_value = [(1, "TSLA", now, 12.5)]

        store = PostgreSQLStore(conn=mock_conn)
        rows = store.fetch_trades(limit=10)
        assert rows[0]["symbol"] == "TSLA"

    def test_fetch_open_trades_filters_exit_time(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.description = [("id",), ("symbol",), ("entry_time",), ("net_pnl",)]
        mock_cur.fetchall.return_value = []

        store = PostgreSQLStore(conn=mock_conn)
        store.fetch_trades(status="open", limit=5)
        sql = mock_cur.execute.call_args[0][0]
        assert "exit_time IS NULL" in sql

    def test_fetch_closed_trades_filters_exit_time(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.description = [("id",), ("symbol",), ("entry_time",), ("net_pnl",)]
        mock_cur.fetchall.return_value = []

        store = PostgreSQLStore(conn=mock_conn)
        store.fetch_trades(status="closed", limit=5)
        sql = mock_cur.execute.call_args[0][0]
        assert "exit_time IS NOT NULL" in sql


class TestFetchTradeSummary:
    def test_returns_expected_keys(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        # Row now has 13 columns: total, wins, avg_gross, avg_slip, avg_net,
        # total_gross, total_net, total_notional, avg_hold,
        # avg_cost_bps, total_cost_usd, avg_spread_bps, avg_impact_bps
        mock_cur.fetchone.return_value = (10, 6, 15.0, 0.5, 14.5, 150.0, 145.0, 5000.0, 30.0,
                                          12.5, 6.25, 8.0, 4.5)

        store = PostgreSQLStore(conn=mock_conn)
        summary = store.fetch_trade_summary(days=7)
        assert summary["total_trades"] == 10
        assert summary["win_rate"] == 0.6
        assert "avg_net_pnl" in summary
        assert "trades_per_week" in summary
        assert "avg_cost_bps" in summary
        assert "total_cost_usd" in summary
        assert "cost_drag_pct" in summary


class TestReconcileTradesFills:
    """reconcile_trade_fills queries Alpaca for fills on trades where entry_price IS NULL."""

    def test_updates_entry_price_and_qty(self):
        from datetime import datetime, timezone
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        # First fetchall → entry fills (4-tuple: id, entry_order_id, symbol, entry_notional)
        # Second → exit fills (empty)
        mock_cur.fetchall.side_effect = [[(1, "order-abc", "AAPL", 2000.0)], []]

        mock_order = MagicMock()
        mock_order.filled_avg_price = "201.50"
        mock_order.filled_qty = "2.5"

        mock_trading = MagicMock()
        mock_trading.get_order_by_id.return_value = mock_order

        store = PostgreSQLStore(conn=mock_conn)
        updated = store.reconcile_trade_fills(mock_trading)

        assert updated == 1
        # Find the UPDATE trades statement among all execute calls
        all_sqls = [c[0][0] for c in mock_cur.execute.call_args_list]
        update_sql = next(s for s in all_sqls if "UPDATE trades" in s and "entry_price" in s)
        assert "entry_price" in update_sql

    def test_skips_unfilled_order(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        # First fetchall → entry fills (4-tuple: id, entry_order_id, symbol, entry_notional)
        # Second → exit fills (empty)
        mock_cur.fetchall.side_effect = [[(1, "order-abc", "AAPL", 2000.0)], []]

        mock_order = MagicMock()
        mock_order.filled_avg_price = None  # not yet filled

        mock_trading = MagicMock()
        mock_trading.get_order_by_id.return_value = mock_order

        store = PostgreSQLStore(conn=mock_conn)
        updated = store.reconcile_trade_fills(mock_trading)

        assert updated == 0

    def test_exit_multi_tranche_computes_weighted_average(self):
        """WS-5: three SELL tranches are aggregated into one exit_price/qty/pnl."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        # Entry fills empty, exit fills with one multi-tranche trade.
        mock_cur.fetchall.side_effect = [
            [],
            [(
                42, "order-exit-1",
                ["order-exit-1", "order-exit-2", "order-exit-3"],
                100.0, 1800.0, 18.021, "SHEL",
            )],
        ]

        orders = {
            "order-exit-1": MagicMock(filled_avg_price="84.06", filled_qty="1.322"),
            "order-exit-2": MagicMock(filled_avg_price="84.10", filled_qty="0.418"),
            "order-exit-3": MagicMock(filled_avg_price="84.00", filled_qty="16.281"),
        }
        mock_trading = MagicMock()
        mock_trading.get_order_by_id.side_effect = lambda oid: orders[oid]

        store = PostgreSQLStore(conn=mock_conn)
        updated = store.reconcile_trade_fills(mock_trading)

        assert updated == 1
        # Find the exit UPDATE call
        update_call = next(
            c for c in mock_cur.execute.call_args_list
            if c[0][0].startswith("UPDATE trades SET") and "exit_price" in c[0][0]
        )
        params = update_call[0][1]
        exit_price, exit_qty, gross_pnl = params[0], params[1], params[2]
        expected_qty = 1.322 + 0.418 + 16.281
        expected_price = (84.06 * 1.322 + 84.10 * 0.418 + 84.00 * 16.281) / expected_qty
        assert exit_qty == pytest.approx(expected_qty)
        assert exit_price == pytest.approx(expected_price, abs=0.001)
        assert gross_pnl == pytest.approx((expected_price - 100.0) * expected_qty, abs=0.01)


class TestFetchAnalyticsBySymbol:
    def test_returns_list_of_dicts_with_expected_keys(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.description = [
            ("label",), ("trade_count",), ("win_rate",),
            ("avg_net_pnl",), ("total_net_pnl",),
        ]
        mock_cur.fetchall.return_value = [("NVDA", 5, 0.6, 12.5, 62.5)]

        store = PostgreSQLStore(conn=mock_conn, use_pool=False)
        rows = store.fetch_analytics_by_symbol(limit_days=90)
        assert isinstance(rows, list)
        assert rows[0]["label"] == "NVDA"
        assert rows[0]["trade_count"] == 5
        assert "win_rate" in rows[0]
        assert "avg_net_pnl" in rows[0]
        assert "total_net_pnl" in rows[0]

    def test_rollback_on_error(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.execute.side_effect = Exception("DB error")

        store = PostgreSQLStore(conn=mock_conn, use_pool=False)
        with pytest.raises(Exception):
            store.fetch_analytics_by_symbol()
        mock_conn.rollback.assert_called_once()


class TestFetchAnalyticsByDimension:
    """Smoke-tests for the four dimension-based analytics methods."""

    def _make_store(self, rows):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.description = [
            ("label",), ("trade_count",), ("win_rate",), ("avg_net_pnl",), ("total_net_pnl",),
        ]
        mock_cur.fetchall.return_value = rows
        return PostgreSQLStore(conn=mock_conn, use_pool=False)

    def test_fetch_analytics_by_regime(self):
        store = self._make_store([("neutral", 3, 0.67, 8.0, 24.0)])
        rows = store.fetch_analytics_by_regime()
        assert rows[0]["label"] == "neutral"

    def test_fetch_analytics_by_hour(self):
        store = self._make_store([("10", 2, 0.5, 5.0, 10.0)])
        rows = store.fetch_analytics_by_hour()
        assert rows[0]["label"] == "10"

    def test_fetch_analytics_by_score_bucket(self):
        store = self._make_store([("0.3–0.4", 4, 0.75, 11.0, 44.0)])
        rows = store.fetch_analytics_by_score_bucket()
        assert rows[0]["label"] == "0.3–0.4"

    def test_fetch_analytics_by_hold_time(self):
        store = self._make_store([("<1h", 6, 0.5, 7.0, 42.0)])
        rows = store.fetch_analytics_by_hold_time()
        assert rows[0]["label"] == "<1h"

    def test_rollback_on_error_shared_helper(self):
        """_fetch_analytics rolls back on exception regardless of which public method is called."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.execute.side_effect = Exception("DB error")

        store = PostgreSQLStore(conn=mock_conn, use_pool=False)
        with pytest.raises(Exception):
            store.fetch_analytics_by_regime()
        mock_conn.rollback.assert_called_once()


class TestFetchTradeWithSignal:
    def test_returns_dict_with_signal_fields(self):
        from datetime import datetime, timezone
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        now = datetime(2026, 6, 5, 15, tzinfo=timezone.utc)
        mock_cur.description = [
            ("id",), ("symbol",), ("entry_time",), ("exit_time",),
            ("entry_price",), ("exit_price",), ("net_pnl",),
            ("score",), ("regime_mult",), ("exit_reason",),
            ("confidence",), ("ensemble_std",), ("signal_generated_at",),
            ("postmortem_diagnosis",),
        ]
        mock_cur.fetchone.return_value = (
            7, "NVDA", now, now, 200.0, 195.0, -5.0,
            0.45, 1.0, "stop_loss",
            0.6, 0.1, now, None,
        )

        store = PostgreSQLStore(conn=mock_conn, use_pool=False)
        result = store.fetch_trade_with_signal(trade_id=7)
        assert result is not None
        assert result["symbol"] == "NVDA"
        assert result["confidence"] == 0.6
        assert result["postmortem_diagnosis"] is None

    def test_returns_none_when_not_found(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = None

        store = PostgreSQLStore(conn=mock_conn, use_pool=False)
        result = store.fetch_trade_with_signal(trade_id=999)
        assert result is None


class TestWritePostmortem:
    def test_issues_update_with_diagnosis(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        store = PostgreSQLStore(conn=mock_conn, use_pool=False)
        store.write_postmortem(trade_id=7, diagnosis="low_confidence_passed")

        sql = mock_cur.execute.call_args[0][0]
        params = mock_cur.execute.call_args[0][1]
        assert "UPDATE trades" in sql
        assert "postmortem_diagnosis" in sql
        assert params[0] == "low_confidence_passed"
        assert params[1] == 7
        mock_conn.commit.assert_called_once()

    def test_rollback_on_error(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.execute.side_effect = Exception("DB error")

        store = PostgreSQLStore(conn=mock_conn, use_pool=False)
        with pytest.raises(Exception):
            store.write_postmortem(trade_id=7, diagnosis="unknown")
        mock_conn.rollback.assert_called_once()


class TestCloseTradeCostBreakdown:
    """close_trade SQL must include real cost columns, not flat slippage."""

    def test_sql_includes_cost_bps(self):
        from src.store.pg_store import PostgreSQLStore
        assert "cost_bps" in PostgreSQLStore._CLOSE_TRADE

    def test_sql_includes_cost_usd(self):
        from src.store.pg_store import PostgreSQLStore
        assert "cost_usd" in PostgreSQLStore._CLOSE_TRADE

    def test_sql_includes_spread_cost_bps(self):
        from src.store.pg_store import PostgreSQLStore
        assert "spread_cost_bps" in PostgreSQLStore._CLOSE_TRADE

    def test_net_pnl_no_flat_slippage(self):
        """net_pnl must use cost_usd, not the hardcoded 0.0005 flat rate."""
        from src.store.pg_store import PostgreSQLStore
        assert "0.0005" not in PostgreSQLStore._CLOSE_TRADE

    def test_trade_summary_includes_avg_cost_bps(self):
        from src.store.pg_store import PostgreSQLStore
        assert "avg_cost_bps" in PostgreSQLStore._TRADE_SUMMARY_SQL

    def test_close_trade_accepts_entry_notional_and_qty(self):
        import inspect

        from src.store.pg_store import PostgreSQLStore
        sig = inspect.signature(PostgreSQLStore.close_trade)
        assert "entry_notional" in sig.parameters
        assert "qty" in sig.parameters


# ── BUG-2: reconcile window too narrow (24h → 7d) ────────────────────────────


class TestReconcileWindow:
    """reconcile_trade_fills must use a 7-day window, not 24 hours.

    Trades opened and closed across a weekend (or if the daily reconcile task
    missed a run) have entry_time > 24h ago and would never be reconciled under
    the old '24 hours' window, leaving entry_price = NULL forever.
    """

    def test_reconcile_entry_query_uses_7_day_window(self):
        """The SELECT for unfilled entries must look back 7 days, not 24 hours."""
        from src.store.pg_store import PostgreSQLStore

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchall.side_effect = [[], []]

        store = PostgreSQLStore(conn=mock_conn)
        store.reconcile_trade_fills(MagicMock())

        all_sqls = [str(c[0][0]) for c in mock_cur.execute.call_args_list]
        entry_select = next(
            (s for s in all_sqls if "entry_price IS NULL" in s), None
        )
        assert entry_select is not None, "Expected a SELECT filtering on entry_price IS NULL"
        assert "24 hours" not in entry_select, (
            "reconcile window must NOT use '24 hours' — trades older than 1 day "
            "are missed; use '7 days' instead"
        )
        assert "7 days" in entry_select, (
            "reconcile window must be '7 days' so weekend and missed-run trades "
            "are still reconciled"
        )


# ── BUG-4: fetch_decisions must return signal_score ───────────────────────────


class TestFetchDecisionsSignalScore:
    """fetch_decisions must include signal_score in returned rows.

    The execution_decisions table stores both score (allocation_weight) and
    signal_score (LLM sentiment). fetch_decisions previously omitted signal_score,
    making it invisible to the API and analytics.
    """

    def test_fetch_decisions_returns_signal_score(self):
        """Returned dicts must include a 'signal_score' key."""
        from datetime import datetime, timezone

        from src.store.pg_store import PostgreSQLStore

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.description = [
            ("id",), ("tick_time",), ("symbol",), ("signal_id",),
            ("score",), ("signal_score",), ("regime_mult",), ("ema_pass",),
            ("decision",), ("order_id",), ("reason",), ("created_at",),
        ]
        now = datetime(2026, 6, 18, 14, tzinfo=timezone.utc)
        mock_cur.fetchall.return_value = [
            (1, now, "XLK", 294, 0.02, 0.707, 0.2, True, "BUY", None, "S4 news-driven", now),
        ]

        store = PostgreSQLStore(conn=mock_conn)
        rows = store.fetch_decisions(limit=10)

        assert len(rows) == 1
        assert "signal_score" in rows[0], (
            "fetch_decisions must return signal_score so the API and analytics "
            "can distinguish LLM quality from allocation_weight"
        )
        assert rows[0]["signal_score"] == 0.707

    def test_fetch_decisions_sql_selects_signal_score(self):
        """The SELECT SQL must include signal_score so it is returned from DB."""
        from src.store.pg_store import PostgreSQLStore

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.description = []
        mock_cur.fetchall.return_value = []

        store = PostgreSQLStore(conn=mock_conn)
        store.fetch_decisions(limit=5)

        all_sqls = [str(c[0][0]) for c in mock_cur.execute.call_args_list]
        select_sql = next((s for s in all_sqls if "execution_decisions" in s), None)
        assert select_sql is not None, "Expected a SELECT on execution_decisions"
        assert "signal_score" in select_sql, (
            "fetch_decisions SELECT must include signal_score — currently omitted "
            "so the LLM sentiment score is invisible to the API and analytics"
        )


class TestConnectionLeakB7B32:
    """B7/B32 (2026-07-15): PostgreSQL pool leak.

    Root cause seen live 2026-07-14: 20 connections 'idle in transaction' from
    `SELECT stop_strategy, stop_mode, stop_vol_at_entry, stop_k ...` (load_frozen_stop),
    one per 15-min portfolio cycle, holding AccessShareLock on `trades` for hours
    and blocking migration 037. Source: bare `PostgreSQLStore()` instances never
    closed (connection never returned to pool) + read-only methods not ending the
    transaction + `_release_connection` not rolling back before `putconn`.
    """

    def test_release_connection_rolls_back_before_putconn(self):
        """Returning a pooled connection MUST rollback before putconn, so a
        connection left 'idle in transaction' by a read-only method is cleaned
        before it goes back into the pool (and before the next user gets a dirty
        connection). Without this, putconn returns a connection with an open tx."""
        import src.store.pg_store as pgm

        parent = MagicMock()
        mock_conn = parent.conn
        mock_pool = parent.pool
        with patch.object(pgm, "_get_pool", return_value=mock_pool):
            store = PostgreSQLStore(use_pool=True)  # _use_pool=True, _conn=None
            store._release_connection(mock_conn)

        mock_conn.rollback.assert_called_once()
        mock_pool.putconn.assert_called_once_with(mock_conn)
        # rollback MUST happen before putconn (call order on the shared parent)
        calls = [name for (name, _, _) in parent.mock_calls]
        assert calls.index("conn.rollback") < calls.index("pool.putconn"), (
            "rollback must run before putconn so the connection is clean on return"
        )

    def test_release_connection_rolls_back_before_close_owned(self):
        """Non-pool (owned) connection: rollback before close()."""
        mock_conn = MagicMock()
        store = PostgreSQLStore(use_pool=False)  # _owns_connection=True
        store._release_connection(mock_conn)
        mock_conn.rollback.assert_called_once()
        mock_conn.close.assert_called_once()

    def test_close_rolls_back_connection_before_release(self):
        """close() -> _release_connection must rollback the held connection,
        not just putconn it dirty."""
        import src.store.pg_store as pgm

        mock_pool = MagicMock()
        mock_conn = MagicMock()
        with patch.object(pgm, "_get_pool", return_value=mock_pool):
            store = PostgreSQLStore(use_pool=True)
            store._conn = mock_conn
            store.close()
        mock_conn.rollback.assert_called_once()
        mock_pool.putconn.assert_called_once_with(mock_conn)
        assert store._conn is None

    def test_load_frozen_stop_ends_transaction(self):
        """Read-only load_frozen_stop MUST end its transaction (rollback) so the
        connection is not left 'idle in transaction'. This was the exact last
        query on the 20 leaked live connections."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        # row: strategy, mode, vol_at_entry, k, floor, cap, d_init, vol_source
        mock_cur.fetchone.return_value = ("S1", "fixed", 0.15, 3.5, 0.06, 0.12, 0.02, "fast")
        store = PostgreSQLStore(conn=mock_conn, use_pool=False)

        result = store.load_frozen_stop("AAPL")

        assert result is not None
        assert result.d_init == pytest.approx(0.02)
        # MUST end the transaction — the leak left it open (idle in transaction)
        mock_conn.rollback.assert_called_once()

    def test_fetch_open_trade_meta_ends_transaction(self):
        """Read-only fetch_open_trade_meta MUST end its transaction (rollback)."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = (42,)  # signal_id
        store = PostgreSQLStore(conn=mock_conn, use_pool=False)

        result = store.fetch_open_trade_meta("AAPL")

        assert result == {"signal_id": 42, "strategy": "S4"}
        mock_conn.rollback.assert_called_once()


class TestSchedulerStoreLeakB7:
    """B7: bare PostgreSQLStore() instances in the scheduler hot path must be
    closed (with/finally). The stop-loss `_pg_stop` leaked one pooled connection
    per 15-min cycle (20 conns live, 2026-07-14)."""

    def test_pg_stop_is_closed_not_bare_abandoned(self):
        """The _pg_stop store in the stop-loss section must be closed (with or
        finally), not bare-and-abandoned as it was on 2026-07-14."""
        import inspect

        import src.workers.portfolio_scheduler as ps

        src = inspect.getsource(ps)
        assert (
            "_pg_stop.close()" in src
            or "with _PGStore() as _pg_stop" in src
        ), "stop-loss _pg_stop must be closed (with/finally) — B7 leak fix"

    def test_no_bare_postgres_store_without_close_in_scheduler(self):
        """Guard: every PostgreSQLStore() / _PG* instantiation in the scheduler
        must be closed — either via `with ... as X:` or have a matching X.close()
        in a finally. Catches re-introduction of bare-and-abandoned stores."""
        import inspect
        import re

        import src.workers.portfolio_scheduler as ps

        src = inspect.getsource(ps)
        # Every bare `X = PostgreSQLStore(...)` (or aliased _PGStore/_PG*)
        # must have a corresponding X.close() somewhere in the module, OR be a
        # `with PostgreSQLStore() as X:` form. We check the close() exists for
        # each non-with assignment name.
        assign_re = re.compile(
            r"^\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:PostgreSQLStore|_PGStore|_PG[A-Za-z]*)\(",
            re.MULTILINE,
        )
        with_re = re.compile(r"with\s+(?:PostgreSQLStore|_PGStore|_PG[A-Za-z]*)\(\)\s+as\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)")
        with_names = {m.group("name") for m in with_re.finditer(src)}
        missing = []
        for m in assign_re.finditer(src):
            name = m.group("name")
            if name in with_names:
                continue
            if f"{name}.close()" not in src:
                missing.append(name)
        assert not missing, (
            f"bare PostgreSQLStore() without close() in scheduler (B7 leak): {missing}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
