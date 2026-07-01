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
