"""Phase 2: stop-loss exits write a SELL execution_decisions row."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.store.pg_store import PostgreSQLStore
from src.workers.portfolio_scheduler import _stop_loss_breached_symbols


class _Pos:
    def __init__(self, symbol: str):
        self.symbol = symbol


class _Mkt:
    def __init__(self, prices: dict[str, float]):
        self.prices = prices


def test_fetch_open_trade_meta_maps_signal_id_to_s4():
    """An open trade with signal_id is S4; without signal_id is S1."""
    store = PostgreSQLStore.__new__(PostgreSQLStore)
    cursor = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    with patch.object(PostgreSQLStore, "_get_connection", return_value=conn):
        cursor.fetchone.return_value = (123,)
        assert store.fetch_open_trade_meta("AAPL") == {"signal_id": 123, "strategy": "S4"}

        cursor.fetchone.return_value = (None,)
        assert store.fetch_open_trade_meta("TSLA") == {"signal_id": None, "strategy": "S1"}

        cursor.fetchone.return_value = None
        assert store.fetch_open_trade_meta("MISSING") is None


def test_stop_loss_breached_symbols_includes_strategy_and_signal_id():
    """Breach dict carries strategy, signal_id and mode derived from the open trade."""
    mock_store = MagicMock()
    mock_store.fetch_open_trade_meta.return_value = {"signal_id": 42, "strategy": "S4"}

    with patch.object(PostgreSQLStore, "__new__", return_value=mock_store):
        out = _stop_loss_breached_symbols(
            [_Pos("AAPL")],
            {"AAPL": 100.0},
            _Mkt({"AAPL": 97.0}),
            0.02,
        )

    assert set(out.keys()) == {"AAPL"}
    dec = out["AAPL"]
    assert dec["strategy"] == "S4"
    assert dec["signal_id"] == 42
    assert dec["mode"] == "fixed"
    assert dec["trigger"] == 98.0
    mock_store.fetch_open_trade_meta.assert_called_once_with("AAPL")


def test_stop_loss_breached_symbols_fails_open_on_strategy_lookup_error():
    """If the strategy lookup raises, the breach is still recorded with None strategy."""
    mock_store = MagicMock()
    mock_store.fetch_open_trade_meta.side_effect = RuntimeError("DB down")

    with patch.object(PostgreSQLStore, "__new__", return_value=mock_store):
        out = _stop_loss_breached_symbols(
            [_Pos("AAPL")],
            {"AAPL": 100.0},
            _Mkt({"AAPL": 97.0}),
            0.02,
        )

    assert set(out.keys()) == {"AAPL"}
    assert out["AAPL"]["strategy"] is None
    assert out["AAPL"]["signal_id"] is None
