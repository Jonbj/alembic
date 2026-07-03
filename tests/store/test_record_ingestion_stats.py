"""EN-06: per-source funnel counters upserted into ingestion_stats_daily."""

from unittest.mock import MagicMock, patch

from src.store.pg_store import PostgreSQLStore


def _store_with_cursor():
    store = PostgreSQLStore.__new__(PostgreSQLStore)
    cursor = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return store, cursor, conn


def test_record_ingestion_stats_maps_synonyms_and_upserts():
    store, cursor, conn = _store_with_cursor()
    with patch.object(PostgreSQLStore, "_get_connection", return_value=conn):
        store.record_ingestion_stats(
            "gdelt_gkg",
            {"fetched": 10, "queued": 3, "duplicates": 5, "skipped_no_ticker": 2},
        )
    sql = cursor.execute.call_args[0][0]
    params = cursor.execute.call_args[0][1]
    assert "ingestion_stats_daily" in sql and "ON CONFLICT" in sql
    assert "gdelt_gkg" in params
    assert 10 in params and 3 in params and 5 in params and 2 in params


def test_record_ingestion_stats_never_raises():
    """Telemetry must be fail-safe: a DB error cannot break an ingestion task."""
    store = PostgreSQLStore.__new__(PostgreSQLStore)
    with patch.object(PostgreSQLStore, "_get_connection", side_effect=RuntimeError("db down")):
        store.record_ingestion_stats("alpaca", {"fetched": 1})  # must not raise


def test_record_ingestion_stats_ignores_unknown_keys():
    store, cursor, conn = _store_with_cursor()
    with patch.object(PostgreSQLStore, "_get_connection", return_value=conn):
        store.record_ingestion_stats("rss", {"weird_counter": 99})
    # all-zero rows are not written
    cursor.execute.assert_not_called()


def test_record_ingestion_stats_maps_real_gkg_discarded_key():
    """GKG worker's real key is 'discarded' (no-ticker), not 'skipped_no_ticker'."""
    store, cursor, conn = _store_with_cursor()
    with patch.object(PostgreSQLStore, "_get_connection", return_value=conn):
        store.record_ingestion_stats("gdelt_gkg", {"fetched": 4, "discarded": 2})
    params = cursor.execute.call_args[0][1]
    assert 2 in params


def test_record_ingestion_stats_maps_real_rss_filtered_key():
    """RSS/EDGAR worker's real key is 'filtered' (no watchlist match)."""
    store, cursor, conn = _store_with_cursor()
    with patch.object(PostgreSQLStore, "_get_connection", return_value=conn):
        store.record_ingestion_stats("rss", {"fetched": 7, "filtered": 3})
    params = cursor.execute.call_args[0][1]
    assert 3 in params
