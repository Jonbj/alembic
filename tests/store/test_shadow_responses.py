"""llm_shadow_responses writer — Stage 2 shadow mode."""

import pytest
from unittest.mock import MagicMock

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


def test_log_shadow_responses_inserts_rows(pg_store):
    """log_shadow_responses inserts one row per input dict."""
    rows = [
        {"news_log_id": 5, "symbol": "AAPL", "model_id": "kimi-k2.6:cloud",
         "polarity": 0.4, "confidence": 0.7, "reasoning": "r", "parse_error": False,
         "latency_ms": 2100},
        {"news_log_id": None, "symbol": "AAPL", "model_id": "qwen3.5:cloud",
         "polarity": None, "confidence": None, "reasoning": None, "parse_error": True,
         "latency_ms": 46000},
    ]
    pg_store.log_shadow_responses(rows)
    cur = pg_store._conn.cursor.return_value
    assert cur.executemany.call_count == 1
    _, batch = cur.executemany.call_args[0]
    batch = list(batch)
    assert len(batch) == 2
    assert batch[1][0] is None      # news_log_id nullable (URL-conflict path)
    assert batch[1][6] is True      # parse_error


def test_log_shadow_responses_empty_noop(pg_store):
    """log_shadow_responses with empty list writes nothing."""
    pg_store.log_shadow_responses([])
    assert pg_store._conn.cursor.return_value.executemany.call_count == 0
