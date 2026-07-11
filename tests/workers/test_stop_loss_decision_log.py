"""Phase 2/3: stop-loss exits write a SELL execution_decisions row and stop_decisions fire log."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from src.portfolio.stop_policy import StopPolicy
from src.store.pg_store import PostgreSQLStore
from src.workers.portfolio_scheduler import _stop_loss_breached_symbols


class _Pos:
    def __init__(self, symbol: str):
        self.symbol = symbol


class _Mkt:
    def __init__(self, prices: dict[str, float]):
        self.prices = prices


def _fixed_policy():
    return StopPolicy({"stop_loss": 0.02, "stop_loss_mode": "fixed"}, bars_df=None)


def test_fetch_open_trade_meta_maps_signal_id_to_s4():
    """An open trade with signal_id is S4; without signal_id is S1."""
    store = PostgreSQLStore.__new__(PostgreSQLStore)
    cursor = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    with patch.object(PostgreSQLStore, "_get_connection", return_value=conn):
        cursor.fetchone.return_value = (123,)
        assert PostgreSQLStore.fetch_open_trade_meta(store, "AAPL") == {"signal_id": 123, "strategy": "S4"}

        cursor.fetchone.return_value = (None,)
        assert PostgreSQLStore.fetch_open_trade_meta(store, "TSLA") == {"signal_id": None, "strategy": "S1"}

        cursor.fetchone.return_value = None
        assert PostgreSQLStore.fetch_open_trade_meta(store, "MISSING") is None


def test_stop_loss_breached_symbols_uses_frozen_stop_when_present():
    """If a frozen stop exists on the open trade, it overrides the fallback fixed stop."""
    from src.portfolio.stop_policy import FrozenStop

    frozen = FrozenStop(
        strategy="S1", mode="fixed", vol_at_entry=None, sigma_eff=None,
        k=None, floor=None, cap=None, d_init=0.05, vol_source=None,
    )
    mock_store = MagicMock()
    mock_store.load_frozen_stop.return_value = frozen
    out = _stop_loss_breached_symbols(
        [_Pos("AAPL")], {"AAPL": 100.0}, _Mkt({"AAPL": 94.0}),
        _fixed_policy(), mock_store,
    )
    assert set(out.keys()) == {"AAPL"}
    assert out["AAPL"].d_init == 0.05
    assert out["AAPL"].trigger_price == pytest.approx(95.0)


def test_stop_loss_breached_symbols_falls_back_to_fixed_when_no_frozen_stop():
    """Pre-migration open trades fall back to the legacy fixed 2% stop."""
    mock_store = MagicMock()
    mock_store.load_frozen_stop.return_value = None
    out = _stop_loss_breached_symbols(
        [_Pos("AAPL")], {"AAPL": 100.0}, _Mkt({"AAPL": 97.0}),
        _fixed_policy(), mock_store,
    )
    assert set(out.keys()) == {"AAPL"}
    assert out["AAPL"].d_init == pytest.approx(0.02)
    assert out["AAPL"].trigger_price == pytest.approx(98.0)
