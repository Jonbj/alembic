"""Pending-forward-return query: must cover fallback signals and all horizons."""
from unittest.mock import MagicMock

import pytest

from src.store.pg_store import PostgreSQLStore


@pytest.fixture
def pg_store():
    """Create a PostgreSQLStore with mocked connection."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = mock_cursor
    return PostgreSQLStore(conn=mock_conn, use_pool=False)


def test_pending_query_includes_fallback_signals():
    """70-80% of the stream is FinBERT fallback; excluding it caps measurement
    coverage at ~29%. The pending query must NOT filter on fallback_used."""
    assert "fallback_used" not in PostgreSQLStore._FETCH_PENDING_FWD


def test_pending_query_covers_all_horizons():
    """A row stays pending until every horizon that can be computed is computed."""
    sql = PostgreSQLStore._FETCH_PENDING_FWD
    assert "forward_return IS NULL" in sql
    assert "forward_return_3d IS NULL" in sql
    assert "forward_return_5d IS NULL" in sql


def test_bulk_add_forward_returns_writes_three_horizons(pg_store):
    """Writer takes (id, fwd_1d, fwd_3d, fwd_5d); None preserves existing values
    via COALESCE so partially-computable rows can be completed later."""
    updates = [(42, 0.01, 0.02, None), (43, None, None, 0.05)]
    pg_store.bulk_add_forward_returns(updates)

    cur = pg_store._conn.cursor.return_value
    assert cur.executemany.call_count == 1
    sql, batch = cur.executemany.call_args[0]
    assert "COALESCE" in sql
    assert "forward_return_3d" in sql and "forward_return_5d" in sql
    batch = list(batch)
    # Param order: (fwd_1d, fwd_3d, fwd_5d, id)
    assert batch[0] == (0.01, 0.02, None, 42)
    assert batch[1] == (None, None, 0.05, 43)


def test_ic_queries_still_exclude_fallback_signals():
    """Populating forward_return on fallback rows is safe ONLY because every
    IC/LOO consumer filters fallback_used = FALSE in SQL. If someone removes
    one of those filters, FinBERT fallback rows would silently pollute the
    ensemble IC series. Three consumers exist as of 2026-07-12."""
    from pathlib import Path
    src = Path("src/store/pg_store.py").read_text()
    assert src.upper().count("FALLBACK_USED = FALSE") >= 3
