"""EN-05: log_news_item persists raw_ingested_at and content_hash."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.models.news import NewsItem
from src.store.pg_store import PostgreSQLStore


def test_insert_news_log_sql_has_trace_columns():
    assert "raw_ingested_at" in PostgreSQLStore._INSERT_NEWS_LOG
    assert "content_hash" in PostgreSQLStore._INSERT_NEWS_LOG


def test_log_news_item_passes_trace_values():
    store = PostgreSQLStore.__new__(PostgreSQLStore)
    cursor = MagicMock()
    cursor.fetchone.return_value = (1,)
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    ts = datetime(2026, 7, 3, 15, 0, tzinfo=timezone.utc)
    item = NewsItem(id="u:AAPL", title="T", body="B", source="alpaca",
                    asset_tags=["AAPL"], raw_ingested_at=ts)
    with patch.object(PostgreSQLStore, "_get_connection", return_value=conn):
        store.log_news_item(item=item, ticker="AAPL", computed_sentiment=0.4)

    params = cursor.execute.call_args[0][1]
    assert ts in params                              # raw_ingested_at
    assert any(isinstance(p, str) and len(p) == 64 for p in params)  # sha256 hash
