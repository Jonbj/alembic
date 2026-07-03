"""FIX-03 part 2: fetch_signals_for_cycle filters on event-time (published_at)."""

from unittest.mock import MagicMock, patch

from src.store.pg_store import PostgreSQLStore


def test_fetch_signals_sql_contains_published_at_gate():
    assert "published_at" in PostgreSQLStore._FETCH_SIGNALS_FOR_CYCLE
    # NULL-safe: legacy rows without published_at must not be dropped.
    assert "published_at IS NULL" in PostgreSQLStore._FETCH_SIGNALS_FOR_CYCLE


def test_fetch_signals_passes_news_age_parameter():
    store = PostgreSQLStore.__new__(PostgreSQLStore)  # skip real __init__/pool
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    with patch.object(PostgreSQLStore, "_get_connection", return_value=conn):
        store.fetch_signals_for_cycle(hours=4, symbols=["AAPL"], news_age_hours=2.0)
    params = cursor.execute.call_args[0][1]
    assert "2.0" in [str(p) for p in params]


def test_fetch_signals_default_has_no_event_time_gate():
    """Review follow-up: default news_age_hours=None must NOT narrow the window.

    Only the S4 entry path passes an explicit bound (FIX-03). The other callers
    (sell-protection at portfolio_scheduler ~624, audit/reason lookups ~1353/1371)
    need older-news signals — e.g. FIX-F's "signal expired 20.3h ago" reason text
    would be impossible under a 2h event-time gate.
    """
    store = PostgreSQLStore.__new__(PostgreSQLStore)
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    with patch.object(PostgreSQLStore, "_get_connection", return_value=conn):
        store.fetch_signals_for_cycle(hours=48, symbols=["AAPL"])
    params = cursor.execute.call_args[0][1]
    # effectively unbounded (1 year), i.e. the generated_at window dominates
    assert str(24 * 365) in [str(p) for p in params]
