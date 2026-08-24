"""Tests for run_counterfactual_worker and helpers (Phase C)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.workers.performance import (
    _compute_1h_return,
    run_counterfactual_worker,
)


# ---------------------------------------------------------------------------
# Unit: _compute_1h_return
# ---------------------------------------------------------------------------

def _ts(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 6, 10, hour, minute, tzinfo=timezone.utc)


def _bars(*args) -> dict:
    """Build a bars_by_minute dict from (hour, minute, close) tuples."""
    return {_ts(h, m): float(c) for h, m, c in args}


class TestCompute1hReturn:
    def test_profit(self):
        bars = _bars((15, 0, 100), (16, 0, 105))
        ret = _compute_1h_return(bars, _ts(15, 0))
        assert ret == pytest.approx(0.05)

    def test_loss(self):
        bars = _bars((15, 0, 100), (16, 0, 95))
        ret = _compute_1h_return(bars, _ts(15, 0))
        assert ret == pytest.approx(-0.05)

    def test_flat(self):
        bars = _bars((15, 0, 100), (16, 0, 100))
        ret = _compute_1h_return(bars, _ts(15, 0))
        assert ret == pytest.approx(0.0)

    def test_missing_entry_bar_returns_none(self):
        bars = _bars((16, 0, 105))  # no entry bar at 15:00
        ret = _compute_1h_return(bars, _ts(15, 0))
        assert ret is None

    def test_missing_exit_bar_returns_none(self):
        bars = _bars((15, 0, 100))  # no exit bar at 16:00
        ret = _compute_1h_return(bars, _ts(15, 0))
        assert ret is None

    def test_entry_price_zero_returns_none(self):
        bars = _bars((15, 0, 0), (16, 0, 105))
        ret = _compute_1h_return(bars, _ts(15, 0))
        assert ret is None

    def test_seconds_and_microseconds_floored(self):
        """tick_time with seconds/microseconds is floored to the minute."""
        bars = _bars((15, 0, 100), (16, 0, 110))
        tick = datetime(2026, 6, 10, 15, 0, 30, 999999, tzinfo=timezone.utc)
        ret = _compute_1h_return(bars, tick)
        assert ret == pytest.approx(0.10)

    def test_custom_horizon(self):
        bars = _bars((15, 0, 100), (15, 30, 103))
        ret = _compute_1h_return(bars, _ts(15, 0), horizon_min=30)
        assert ret == pytest.approx(0.03)


# ---------------------------------------------------------------------------
# Integration: run_counterfactual_worker
# ---------------------------------------------------------------------------

def _make_decision(
    id: int,
    symbol: str = "AAPL",
    decision: str = "SKIP_EMA",
    tick_time: datetime | None = None,
) -> dict:
    if tick_time is None:
        tick_time = _ts(15, 0)
    return {
        "id": id,
        "symbol": symbol,
        "score": 0.45,
        "regime_mult": 1.0,
        "decision": decision,
        "tick_time": tick_time,
    }


def _make_bars_df(symbol: str, start_hour: int, prices: list[float]):
    """Build a fake Alpaca bars DataFrame."""
    import pandas as pd
    times = [datetime(2026, 6, 10, start_hour, i, tzinfo=timezone.utc) for i in range(len(prices))]
    idx = pd.MultiIndex.from_tuples([(symbol, t) for t in times], names=["symbol", "timestamp"])
    return pd.DataFrame({"close": prices, "open": prices, "high": prices, "low": prices}, index=idx)


def _patched_run(
    decisions: list[dict],
    bars_by_symbol: dict | None = None,
):
    """Patch all external deps and run the task."""
    mock_pg = MagicMock()
    mock_pg.fetch_skip_decisions_without_counterfactual.return_value = decisions

    def mock_get_stock_bars(req):
        symbol = req.symbol_or_symbols
        if bars_by_symbol and symbol in bars_by_symbol:
            result = MagicMock()
            result.df = bars_by_symbol[symbol]
            return result
        result = MagicMock()
        # Return empty DataFrame
        import pandas as pd
        result.df = pd.DataFrame()
        return result

    mock_data_client = MagicMock()
    mock_data_client.get_stock_bars.side_effect = mock_get_stock_bars

    with (
        patch("src.workers.performance.PostgreSQLStore", return_value=mock_pg),
        patch("psycopg2.connect"),
        patch("src.workers.performance.config") as mock_cfg,
        patch(
            "src.workers.performance.run_counterfactual_worker.__wrapped__",
            create=True,
        ),
    ):
        mock_cfg.ALPACA_API_KEY = "key"
        mock_cfg.ALPACA_SECRET_KEY = "secret"
        mock_cfg.DATABASE_URL = "postgresql://test"

        with patch(
            "src.workers.performance.StockHistoricalDataClient",
            return_value=mock_data_client,
        ) if False else patch(
            "alpaca.data.historical.StockHistoricalDataClient",
            return_value=mock_data_client,
        ):
            result = run_counterfactual_worker()

    return result, mock_pg


class TestNoCredentials:
    def test_skips_without_alpaca_credentials(self):
        with (
            patch("src.workers.performance.config") as mock_cfg,
            patch("psycopg2.connect"),
            patch("src.workers.performance.PostgreSQLStore"),
        ):
            mock_cfg.ALPACA_API_KEY = None
            mock_cfg.ALPACA_SECRET_KEY = None
            result = run_counterfactual_worker()

        assert result.get("skipped") is True
        assert result.get("reason") == "no_credentials"


class TestNoDecisions:
    def test_empty_result_when_no_pending_decisions(self):
        mock_pg = MagicMock()
        mock_pg.fetch_skip_decisions_without_counterfactual.return_value = []

        with (
            patch("src.workers.performance.PostgreSQLStore", return_value=mock_pg),
            patch("psycopg2.connect"),
            patch("src.workers.performance.config") as mock_cfg,
        ):
            mock_cfg.ALPACA_API_KEY = "key"
            mock_cfg.ALPACA_SECRET_KEY = "secret"
            mock_cfg.DATABASE_URL = "postgresql://test"
            result = run_counterfactual_worker()

        assert result["total_decisions"] == 0
        assert result["updated"] == 0
        mock_pg.bulk_set_counterfactual.assert_not_called()


# ---------------------------------------------------------------------------
# Unit: pg_store counterfactual methods
# ---------------------------------------------------------------------------

class TestPgStoreCounterfactual:
    """Unit tests for the three pg_store counterfactual methods."""

    def _make_store(self):
        from src.store.pg_store import PostgreSQLStore
        store = PostgreSQLStore.__new__(PostgreSQLStore)
        store._conn = MagicMock()
        store._get_connection = MagicMock(return_value=store._conn)
        return store

    def test_fetch_skip_decisions_executes_correct_sql(self):
        from src.store.pg_store import PostgreSQLStore
        store = self._make_store()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = []
        mock_cursor.description = [
            ("id",), ("tick_time",), ("symbol",), ("score",), ("regime_mult",), ("decision",)
        ]
        store._conn.cursor.return_value = mock_cursor

        store.fetch_skip_decisions_without_counterfactual(days_back=7, limit=100)

        called_sql = mock_cursor.execute.call_args[0][0]
        assert "SKIP_THRESHOLD" in called_sql
        assert "SKIP_EMA" in called_sql
        assert "SKIP_CAP" in called_sql
        # #315: senza questa riga SKIP_PYRAMIDING non riceve mai un
        # counterfactual_return_1h — i blocchi anti-pyramiding restano
        # illeggibili per la revisione di #230.
        assert "SKIP_PYRAMIDING" in called_sql
        assert "counterfactual_computed_at IS NULL" in called_sql

    def test_bulk_set_counterfactual_empty_list_returns_zero(self):
        from src.store.pg_store import PostgreSQLStore
        store = self._make_store()
        result = store.bulk_set_counterfactual([])
        assert result == 0
        store._conn.cursor.assert_not_called()

    def test_bulk_set_counterfactual_calls_executemany(self):
        from src.store.pg_store import PostgreSQLStore
        store = self._make_store()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.rowcount = 2
        store._conn.cursor.return_value = mock_cursor

        ts = datetime.now(timezone.utc)
        updates = [(1, 0.03, ts), (2, -0.01, ts)]
        result = store.bulk_set_counterfactual(updates)

        mock_cursor.executemany.assert_called_once()
        store._conn.commit.assert_called_once()
        assert result == 2

    def test_fetch_counterfactual_summary_returns_floats(self):
        from src.store.pg_store import PostgreSQLStore
        store = self._make_store()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.description = [
            ("decision",), ("total_skips",), ("computed",),
            ("avg_return",), ("pct_profitable",), ("sum_positive_returns",)
        ]
        mock_cursor.fetchall.return_value = [
            ("SKIP_EMA", 10, 8, 0.012345, 0.625, 0.098765),
        ]
        store._conn.cursor.return_value = mock_cursor

        rows = store.fetch_counterfactual_summary(days=7)

        assert len(rows) == 1
        assert rows[0]["decision"] == "SKIP_EMA"
        assert rows[0]["avg_return"] == pytest.approx(0.0123, abs=1e-3)
        assert rows[0]["pct_profitable"] == pytest.approx(0.625)


# ---------------------------------------------------------------------------
# Unit: _compute_1h_return with timezone handling
# ---------------------------------------------------------------------------

class TestTimezoneHandling:
    def test_naive_tick_time_treated_as_utc(self):
        """Bars keyed as UTC match naive tick_time via flooring."""
        naive_tick = datetime(2026, 6, 10, 15, 0, 0)  # no tzinfo
        bars = {
            datetime(2026, 6, 10, 15, 0, tzinfo=timezone.utc): 100.0,
            datetime(2026, 6, 10, 16, 0, tzinfo=timezone.utc): 108.0,
        }
        # _compute_1h_return floors but doesn't add tzinfo — key mismatch expected.
        # This tests the documented behavior: caller is responsible for UTC normalisation.
        ret = _compute_1h_return(bars, naive_tick)
        # naive key won't match UTC-aware keys → None
        assert ret is None

    def test_utc_aware_tick_matches_bars(self):
        bars = {
            datetime(2026, 6, 10, 15, 0, tzinfo=timezone.utc): 100.0,
            datetime(2026, 6, 10, 16, 0, tzinfo=timezone.utc): 112.0,
        }
        tick = datetime(2026, 6, 10, 15, 0, tzinfo=timezone.utc)
        ret = _compute_1h_return(bars, tick)
        assert ret == pytest.approx(0.12)


# ---------------------------------------------------------------------------
# #337 — coverage: pagination, tail-of-session, persisted reasons
# ---------------------------------------------------------------------------

from src.workers.performance import (  # noqa: E402
    _CF_FETCH_ERROR,
    _CF_HORIZON_AFTER_CLOSE,
    _CF_MISSING_ENTRY_BAR,
    _CF_MISSING_EXIT_BAR,
    _CF_NO_BARS,
    _CF_NO_BARS_AFTER_HORIZON,
    _CF_PENDING_OVERNIGHT,
    _CF_ZERO_ENTRY_PRICE,
    _COUNTERFACTUAL_MAX_ATTEMPTS,
    _counterfactual_outcome,
)


class TestCounterfactualOutcome:
    """The +1h window closing past the session must be distinguishable from a data gap."""

    def test_exit_bar_present_returns_1h(self):
        bars = _bars((15, 0, 100), (16, 0, 106))
        ret, overnight, reason = _counterfactual_outcome(bars, _ts(15, 0))
        assert ret == pytest.approx(0.06)
        assert overnight is None
        assert reason is None

    def test_missing_entry_bar_is_named(self):
        ret, overnight, reason = _counterfactual_outcome(_bars((16, 0, 105)), _ts(15, 0))
        assert (ret, overnight, reason) == (None, None, _CF_MISSING_ENTRY_BAR)

    def test_zero_entry_price_is_named(self):
        bars = _bars((15, 0, 0), (16, 0, 105))
        ret, overnight, reason = _counterfactual_outcome(bars, _ts(15, 0))
        assert (ret, overnight, reason) == (None, None, _CF_ZERO_ENTRY_PRICE)

    def test_intra_session_gap_is_not_an_overnight(self):
        """A hole at T+1h with the session still running is missing data, not a close."""
        bars = _bars((15, 0, 100), (16, 5, 104))  # nothing at 16:00, but 16:05 exists
        ret, overnight, reason = _counterfactual_outcome(bars, _ts(15, 0))
        assert (ret, overnight, reason) == (None, None, _CF_MISSING_EXIT_BAR)

    def test_tail_of_session_gets_overnight_return(self):
        """19:52 tick: +1h is past the 20:00 close, so the next session's open answers."""
        bars = {
            datetime(2026, 6, 10, 19, 52, tzinfo=timezone.utc): 100.0,
            datetime(2026, 6, 10, 19, 59, tzinfo=timezone.utc): 100.5,
            datetime(2026, 6, 11, 13, 30, tzinfo=timezone.utc): 103.0,
        }
        tick = datetime(2026, 6, 10, 19, 52, tzinfo=timezone.utc)
        ret, overnight, reason = _counterfactual_outcome(bars, tick)
        assert ret is None
        assert overnight == pytest.approx(0.03)
        assert reason == _CF_HORIZON_AFTER_CLOSE

    def test_next_session_not_yet_available_is_pending(self):
        """Run the same night and the next open does not exist yet — retry, don't give up."""
        bars = {
            datetime(2026, 6, 10, 19, 52, tzinfo=timezone.utc): 100.0,
            datetime(2026, 6, 10, 19, 59, tzinfo=timezone.utc): 100.5,
        }
        tick = datetime(2026, 6, 10, 19, 52, tzinfo=timezone.utc)
        ret, overnight, reason = _counterfactual_outcome(bars, tick)
        assert (ret, overnight, reason) == (None, None, _CF_PENDING_OVERNIGHT)


class TestPaginationToExhaustion:
    """#337 P1: a day with >500 skips must not lose its first hour."""

    def _store_with_pages(self, pages):
        from src.store.pg_store import PostgreSQLStore
        store = PostgreSQLStore.__new__(PostgreSQLStore)
        calls = []

        def fake_fetch(days_back=7, limit=500, before=None):
            calls.append({"days_back": days_back, "limit": limit, "before": before})
            return pages.pop(0) if pages else []

        store.fetch_skip_decisions_without_counterfactual = fake_fetch
        return store, calls

    def _rows(self, start_id, count):
        base = datetime(2026, 8, 20, 20, 0, tzinfo=timezone.utc)
        return [
            {"id": i, "tick_time": base - timedelta(minutes=i), "symbol": "AAPL",
             "score": 0.4, "regime_mult": 1.0, "decision": "SKIP_THRESHOLD",
             "counterfactual_attempts": 0}
            for i in range(start_id, start_id + count)
        ]

    def test_pages_until_short_page(self):
        pages = [self._rows(1, 500), self._rows(501, 107)]
        store, calls = self._store_with_pages(pages)

        rows = store.fetch_all_skip_decisions_without_counterfactual(page_size=500)

        # 607 skips on 2026-08-20 — the old LIMIT 500 lost 107 of them for good.
        assert len(rows) == 607
        assert len(calls) == 2
        assert calls[0]["before"] is None
        # Second page resumes strictly after the last row of the first.
        assert calls[1]["before"] == (rows[499]["tick_time"], rows[499]["id"])

    def test_stops_on_empty_page_when_last_page_is_exactly_full(self):
        store, calls = self._store_with_pages([self._rows(1, 10), []])
        rows = store.fetch_all_skip_decisions_without_counterfactual(page_size=10)
        assert len(rows) == 10
        assert len(calls) == 2

    def test_max_rows_bounds_a_runaway_backlog(self):
        pages = [self._rows(1, 500) for _ in range(20)]
        store, calls = self._store_with_pages(pages)
        rows = store.fetch_all_skip_decisions_without_counterfactual(page_size=500, max_rows=1200)
        assert len(rows) == 1200
        assert calls[-1]["limit"] == 200  # last page trimmed to the bound


class TestFetchPageSql:
    def _make_store(self):
        from src.store.pg_store import PostgreSQLStore
        store = PostgreSQLStore.__new__(PostgreSQLStore)
        store._conn = MagicMock()
        store._get_connection = MagicMock(return_value=store._conn)
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = []
        mock_cursor.description = [("id",), ("tick_time",), ("symbol",), ("score",),
                                   ("regime_mult",), ("decision",), ("counterfactual_attempts",)]
        store._conn.cursor.return_value = mock_cursor
        return store, mock_cursor

    def test_keyset_cursor_is_applied(self):
        store, cur = self._make_store()
        ts = datetime(2026, 8, 20, 15, 22, tzinfo=timezone.utc)
        store.fetch_skip_decisions_without_counterfactual(days_back=7, limit=500, before=(ts, 42))

        sql, params = cur.execute.call_args[0]
        assert "(tick_time, id) < (%s, %s)" in sql
        # Total order, otherwise ties on tick_time make the cursor skip or repeat rows.
        assert "ORDER BY tick_time DESC, id DESC" in sql
        assert list(params) == ["7", ts, 42, 500]

    def test_no_cursor_clause_on_first_page(self):
        store, cur = self._make_store()
        store.fetch_skip_decisions_without_counterfactual(days_back=7, limit=500)
        sql, params = cur.execute.call_args[0]
        assert "(tick_time, id) <" not in sql
        assert list(params) == ["7", 500]

    def test_attempts_column_is_selected(self):
        store, cur = self._make_store()
        store.fetch_skip_decisions_without_counterfactual()
        assert "counterfactual_attempts" in cur.execute.call_args[0][0]


class TestBulkSetCounterfactualOutcome:
    def _make_store(self):
        from src.store.pg_store import PostgreSQLStore
        store = PostgreSQLStore.__new__(PostgreSQLStore)
        store._conn = MagicMock()
        store._get_connection = MagicMock(return_value=store._conn)
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.rowcount = 1
        store._conn.cursor.return_value = mock_cursor
        return store, mock_cursor

    def test_six_tuple_writes_reason_and_overnight(self):
        store, cur = self._make_store()
        ts = datetime.now(timezone.utc)
        store.bulk_set_counterfactual([(7, None, ts, _CF_HORIZON_AFTER_CLOSE, 0.021, 1)])

        sql, rows = cur.executemany.call_args[0]
        assert "counterfactual_skip_reason" in sql
        assert "counterfactual_return_overnight" in sql
        assert rows == [(None, ts, _CF_HORIZON_AFTER_CLOSE, 0.021, 1, 7)]

    def test_legacy_three_tuple_still_accepted(self):
        store, cur = self._make_store()
        ts = datetime.now(timezone.utc)
        store.bulk_set_counterfactual([(7, 0.01, ts)])
        _, rows = cur.executemany.call_args[0]
        assert rows == [(0.01, ts, None, None, 0, 7)]


def _run_with_rows(decisions, bars_by_symbol=None, raise_for=None):
    """Run the worker against fake rows/bars and return (stats, updates written)."""
    import pandas as pd

    mock_pg = MagicMock()
    mock_pg.fetch_all_skip_decisions_without_counterfactual.return_value = decisions

    def mock_get_stock_bars(req):
        symbol = req.symbol_or_symbols
        if raise_for and symbol in raise_for:
            raise RuntimeError("alpaca down")
        result = MagicMock()
        result.df = (bars_by_symbol or {}).get(symbol, pd.DataFrame())
        return result

    mock_data_client = MagicMock()
    mock_data_client.get_stock_bars.side_effect = mock_get_stock_bars

    with (
        patch("src.workers.performance.PostgreSQLStore", return_value=mock_pg),
        patch("psycopg2.connect"),
        patch("src.workers.performance.RedisStore"),
        patch("src.workers.performance.retry_transient", side_effect=lambda fn: fn()),
        patch("src.workers.performance.config") as mock_cfg,
        patch("alpaca.data.historical.StockHistoricalDataClient", return_value=mock_data_client),
    ):
        mock_cfg.ALPACA_API_KEY = "key"
        mock_cfg.ALPACA_SECRET_KEY = "secret"
        mock_cfg.DATABASE_URL = "postgresql://test"
        stats = run_counterfactual_worker()

    updates = []
    if mock_pg.bulk_set_counterfactual.call_args:
        updates = mock_pg.bulk_set_counterfactual.call_args[0][0]
    return stats, {u[0]: u for u in updates}


def _bars_df(symbol: str, points: list[tuple[datetime, float]]):
    import pandas as pd
    idx = pd.MultiIndex.from_tuples([(symbol, t) for t, _ in points],
                                    names=["symbol", "timestamp"])
    closes = [c for _, c in points]
    return pd.DataFrame({"close": closes, "open": closes, "high": closes, "low": closes},
                        index=idx)


class TestWorkerPersistsOutcome:
    """#337 P2/P3: no row may end as a bare NULL with no explanation."""

    def test_uses_the_paginated_fetch(self):
        stats, _ = _run_with_rows([])
        assert stats["total_decisions"] == 0

    def test_normal_row_gets_return_and_no_reason(self):
        tick = datetime(2026, 6, 10, 15, 0, tzinfo=timezone.utc)
        d = {**_make_decision(1, "AAPL"), "tick_time": tick, "counterfactual_attempts": 0}
        bars = _bars_df("AAPL", [(tick, 100.0), (tick + timedelta(minutes=60), 104.0)])

        stats, updates = _run_with_rows([d], {"AAPL": bars})

        _id, ret, computed_at, reason, overnight, attempts = updates[1]
        assert ret == pytest.approx(0.04)
        assert computed_at is not None
        assert reason is None
        assert overnight is None
        assert stats["updated"] == 1

    def test_tail_row_gets_overnight_return_not_a_silent_null(self):
        tick = datetime(2026, 6, 10, 19, 52, tzinfo=timezone.utc)
        d = {**_make_decision(2, "AMAT"), "tick_time": tick, "counterfactual_attempts": 0}
        bars = _bars_df("AMAT", [
            (tick, 100.0),
            (datetime(2026, 6, 10, 19, 59, tzinfo=timezone.utc), 100.5),
            (datetime(2026, 6, 11, 13, 30, tzinfo=timezone.utc), 102.0),
        ])

        stats, updates = _run_with_rows([d], {"AMAT": bars})

        _id, ret, computed_at, reason, overnight, _ = updates[2]
        assert ret is None
        assert reason == _CF_HORIZON_AFTER_CLOSE
        assert overnight == pytest.approx(0.02)
        assert computed_at is not None  # resolved, not retried
        assert stats["overnight_computed"] == 1

    def test_pending_row_is_left_for_the_next_run(self):
        tick = datetime(2026, 6, 10, 19, 52, tzinfo=timezone.utc)
        d = {**_make_decision(3, "PANW"), "tick_time": tick, "counterfactual_attempts": 0}
        bars = _bars_df("PANW", [
            (tick, 100.0),
            (datetime(2026, 6, 10, 19, 59, tzinfo=timezone.utc), 100.5),
        ])

        stats, updates = _run_with_rows([d], {"PANW": bars})

        _id, ret, computed_at, reason, _overnight, attempts = updates[3]
        # computed_at stays NULL so the row is re-fetched tomorrow, but the
        # reason and the counter make the pending state explicit meanwhile.
        assert computed_at is None
        assert reason == _CF_PENDING_OVERNIGHT
        assert attempts == 1
        assert stats["pending_retry"] == 1

    def test_retry_budget_finalises_the_row(self):
        tick = datetime(2026, 6, 10, 19, 52, tzinfo=timezone.utc)
        d = {**_make_decision(4, "PANW"), "tick_time": tick,
             "counterfactual_attempts": _COUNTERFACTUAL_MAX_ATTEMPTS - 1}
        bars = _bars_df("PANW", [
            (tick, 100.0),
            (datetime(2026, 6, 10, 19, 59, tzinfo=timezone.utc), 100.5),
        ])

        stats, updates = _run_with_rows([d], {"PANW": bars})

        _id, ret, computed_at, reason, _overnight, attempts = updates[4]
        assert computed_at is not None  # no infinite loop
        # PENDING_OVERNIGHT would contradict a populated computed_at.
        assert reason == _CF_NO_BARS_AFTER_HORIZON
        assert attempts == _COUNTERFACTUAL_MAX_ATTEMPTS
        assert stats["attempts_exhausted"] == 1

    def test_no_bars_is_retried_then_named(self):
        tick = datetime(2026, 6, 10, 15, 0, tzinfo=timezone.utc)
        fresh = {**_make_decision(5, "DEAD"), "tick_time": tick, "counterfactual_attempts": 0}
        spent = {**_make_decision(6, "DEAD"), "tick_time": tick,
                 "counterfactual_attempts": _COUNTERFACTUAL_MAX_ATTEMPTS - 1}

        stats, updates = _run_with_rows([fresh, spent], {})

        assert updates[5][2] is None and updates[5][3] == _CF_NO_BARS
        assert updates[6][2] is not None and updates[6][3] == _CF_NO_BARS

    def test_fetch_error_is_named_and_counted_as_error(self):
        tick = datetime(2026, 6, 10, 15, 0, tzinfo=timezone.utc)
        d = {**_make_decision(7, "BOOM"), "tick_time": tick,
             "counterfactual_attempts": _COUNTERFACTUAL_MAX_ATTEMPTS - 1}

        stats, updates = _run_with_rows([d], {}, raise_for={"BOOM"})

        assert updates[7][3] == _CF_FETCH_ERROR
        assert updates[7][2] is not None
        assert stats["errors"] == 1

    def test_counters_partition_the_batch(self):
        """Every row lands in exactly one bucket — otherwise coverage is unreadable."""
        t15 = datetime(2026, 6, 10, 15, 0, tzinfo=timezone.utc)
        t1952 = datetime(2026, 6, 10, 19, 52, tzinfo=timezone.utc)
        rows = [
            {**_make_decision(10, "AAPL"), "tick_time": t15, "counterfactual_attempts": 0},
            {**_make_decision(11, "AMAT"), "tick_time": t1952, "counterfactual_attempts": 0},
            {**_make_decision(12, "PANW"), "tick_time": t1952, "counterfactual_attempts": 0},
            {**_make_decision(13, "DEAD"), "tick_time": t15, "counterfactual_attempts": 0},
            {**_make_decision(14, "BOOM"), "tick_time": t15, "counterfactual_attempts": 0},
        ]
        bars = {
            "AAPL": _bars_df("AAPL", [(t15, 100.0), (t15 + timedelta(minutes=60), 101.0)]),
            "AMAT": _bars_df("AMAT", [
                (t1952, 100.0),
                (datetime(2026, 6, 11, 13, 30, tzinfo=timezone.utc), 102.0)]),
            "PANW": _bars_df("PANW", [(t1952, 100.0)]),
        }

        stats, updates = _run_with_rows(rows, bars, raise_for={"BOOM"})

        assert len(updates) == 5
        bucket_sum = (
            stats["updated"] + stats["overnight_computed"] + stats["pending_retry"]
            + stats["skipped_no_data"] + stats["errors"]
        )
        assert bucket_sum == stats["total_decisions"] == 5
        # And no row is ever written with computed_at set but no explanation.
        for _id, ret, computed_at, reason, overnight, _a in updates.values():
            if computed_at is not None and ret is None:
                assert reason is not None
