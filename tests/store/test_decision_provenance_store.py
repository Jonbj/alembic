"""#596: la lookup di provenienza deve restituire righe davvero leggibili.

La prima versione usava il cursore di default (tuple) e poi ``r["signal_id"]``:
l'eccezione veniva assorbita dal fail-soft e ogni lookup tornava {} in silenzio.
"""

from unittest.mock import MagicMock

from psycopg2.extras import RealDictCursor

from src.store.pg_store import PostgreSQLStore


def _store_con_righe(righe):
    cur = MagicMock()
    cur.fetchall.return_value = righe
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    store = PostgreSQLStore.__new__(PostgreSQLStore)
    store._conn = conn
    store._use_pool = False
    return store, conn


def test_la_lookup_usa_un_cursore_a_dizionario():
    store, conn = _store_con_righe([
        {"signal_id": 7, "signal_symbol": "MU", "news_log_id": 9, "title": "t",
         "url": "u", "body_snippet": "b", "extraction_method": "source_metadata",
         "n_ticker_articolo": 2, "issuer_terms": ["Micron"]},
    ])

    out = store.fetch_decision_provenance([7])

    assert conn.cursor.call_args.kwargs.get("cursor_factory") is RealDictCursor
    assert out[7]["news_log_id"] == 9
    assert out[7]["issuer_terms"] == ["Micron"]
    assert "signal_id" not in out[7]


def test_la_query_porta_corpo_e_alias_dell_emittente():
    sql = PostgreSQLStore._FETCH_PROVENANCE_FOR_SIGNALS
    assert "n.body_snippet" in sql
    assert "ticker_lookup" in sql and "issuer_terms" in sql
