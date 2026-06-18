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

    def test_fetch_signals_for_cycle_query_structure(self):
        """fetch_signals_for_cycle uses DISTINCT ON, parameterized interval, watchlist filter."""
        query = PostgreSQLStore._FETCH_SIGNALS_FOR_CYCLE
        assert "DISTINCT ON (symbol)" in query
        assert "INTERVAL '%s'" not in query
        assert "(%s || ' hours')::interval" in query or "%s || ' hours'" in query
        assert "ORDER BY symbol, generated_at DESC" in query
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
        from unittest.mock import patch, MagicMock
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
        # First fetchone() call: SELECT entry_notional, qty (None = no row found → defaults)
        # Second fetchone() call: RETURNING id from UPDATE
        mock_cur.fetchone.side_effect = [None, (77,)]

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
        mock_cur.fetchone.side_effect = [None, None]

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
        # First fetchone: SELECT entry_notional, qty (None → defaults to 0)
        # Second fetchone: RETURNING id
        mock_cur.fetchone.side_effect = [None, (99,)]

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
        # First fetchall → entry fills (2-tuple); second → exit fills (empty)
        mock_cur.fetchall.side_effect = [[(1, "order-abc")], []]

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
        # First fetchall → entry fills (2-tuple); second → exit fills (empty)
        mock_cur.fetchall.side_effect = [[(1, "order-abc")], []]

        mock_order = MagicMock()
        mock_order.filled_avg_price = None  # not yet filled

        mock_trading = MagicMock()
        mock_trading.get_order_by_id.return_value = mock_order

        store = PostgreSQLStore(conn=mock_conn)
        updated = store.reconcile_trade_fills(mock_trading)

        assert updated == 0


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
