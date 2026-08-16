"""FIX-06: discarded news is persisted with an explicit reason."""

from unittest.mock import MagicMock, patch

from src.store.pg_store import PostgreSQLStore


def test_record_news_discards_persists_reason_and_stage():
    store = PostgreSQLStore.__new__(PostgreSQLStore)
    cursor = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    rows = [
        {
            "item_id": "alpaca:1:AAPL",
            "article_id": "alpaca:1",
            "symbol": "AAPL",
            "source": "alpaca_benzinga",
            "published_at": None,
            "age_hours": None,
            "title": "duplicate",
            "url": "https://example.com/1",
            "raw_ingested_at": None,
            "content_hash": "abc",
            "discarded_reason": "duplicate_content",
            "discard_stage": "ingestion",
        }
    ]

    with patch.object(PostgreSQLStore, "_get_connection", return_value=conn):
        store.record_news_discards(rows)

    sql = cursor.executemany.call_args[0][0]
    params = list(cursor.executemany.call_args[0][1])
    assert "discarded_reason" in sql
    assert "discard_stage" in sql
    assert "duplicate_content" in params[0]
    assert "ingestion" in params[0]
    conn.commit.assert_called_once()
