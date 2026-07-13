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
