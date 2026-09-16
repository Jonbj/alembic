"""#541: i writer di persistenza portano la provenienza di trasporto in Postgres.

Una colonna che il writer lascia fuori dalla INSERT e' una colonna che non
esiste: e' gia' successo con `enqueued_off_session` (#432), e il test che lo
presidiava e' il motivo per cui qui ce n'e' uno per ciascuno dei tre writer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from src.models.news import NewsItem
from src.store.pg_store import PostgreSQLStore


def _store_e_cursore():
    store = PostgreSQLStore.__new__(PostgreSQLStore)
    cursor = MagicMock()
    cursor.fetchone.return_value = (1,)
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return store, cursor, conn


def _riga_di_scarto(**kwargs) -> dict:
    riga = {
        "item_id": "alpaca:1:AAPL",
        "article_id": "alpaca:1",
        "symbol": "AAPL",
        "source": "alpaca_benzinga",
        "published_at": None,
        "age_hours": None,
        "title": "t",
        "url": "https://example.test/1",
        "raw_ingested_at": None,
        "content_hash": "abc",
        "discarded_reason": "duplicate_id",
        "discard_stage": "ingestion",
        "enqueued_off_session": False,
    }
    riga.update(kwargs)
    return riga


# ── news_queue_drops ──────────────────────────────────────────────────────────


def test_record_news_discards_persiste_il_trasporto():
    store, cursor, conn = _store_e_cursore()

    with patch.object(PostgreSQLStore, "_get_connection", return_value=conn):
        store.record_news_discards([_riga_di_scarto(transport="ws")])

    sql = cursor.executemany.call_args[0][0]
    params = list(cursor.executemany.call_args[0][1])
    assert "transport" in sql
    assert "ws" in params[0]


def test_una_riga_senza_trasporto_non_rompe_la_insert():
    """I connettori senza variante WebSocket (GDELT, MarketAux, Finnhub, RSS,
    EDGAR) non conoscono il campo: devono scrivere NULL, non fallire."""
    store, cursor, conn = _store_e_cursore()
    riga = _riga_di_scarto()
    riga.pop("transport", None)

    with patch.object(PostgreSQLStore, "_get_connection", return_value=conn):
        store.record_news_discards([riga])

    params = list(cursor.executemany.call_args[0][1])
    assert None in params[0]
    conn.commit.assert_called_once()


def test_il_flag_di_seduta_resta_l_ultimo_parametro():
    """#432 asserisce posizionalmente `params[0][-1]`: la colonna nuova si
    inserisce prima, non in coda, per non spostare un contratto gia' testato."""
    store, cursor, conn = _store_e_cursore()

    with patch.object(PostgreSQLStore, "_get_connection", return_value=conn):
        store.record_news_discards(
            [_riga_di_scarto(transport="rest", enqueued_off_session=True)]
        )

    params = list(cursor.executemany.call_args[0][1])
    assert params[0][-1] is True


# ── news_log ──────────────────────────────────────────────────────────────────


def test_insert_news_log_dichiara_la_colonna_transport():
    assert "transport" in PostgreSQLStore._INSERT_NEWS_LOG


def test_log_news_item_persiste_il_trasporto_dell_item():
    store, cursor, conn = _store_e_cursore()
    item = NewsItem(
        id="u:AAPL", title="T", body="B", source="alpaca_benzinga",
        asset_tags=["AAPL"], transport="ws",
    )

    with patch.object(PostgreSQLStore, "_get_connection", return_value=conn):
        store.log_news_item(item=item, ticker="AAPL", computed_sentiment=0.4)

    params = cursor.execute.call_args[0][1]
    assert "ws" in params


def test_log_news_item_scrive_none_per_un_item_non_strumentato():
    store, cursor, conn = _store_e_cursore()
    item = NewsItem(id="u:AAPL", title="T", body="B", source="gdelt_gkg",
                    asset_tags=["AAPL"])

    with patch.object(PostgreSQLStore, "_get_connection", return_value=conn):
        store.log_news_item(item=item, ticker="AAPL")

    params = cursor.execute.call_args[0][1]
    assert params[-1] is None


# ── news_stream_subscriptions ─────────────────────────────────────────────────


def test_record_news_stream_subscription_persiste_simboli_e_cardinalita():
    """Senza questo snapshot il tasso di WS-missed non e' calcolabile sui soli
    simboli sottoscritti (DoD #541): la watchlist e' baked nell'immagine e non
    lascia traccia di quale fosse attiva al momento della pubblicazione."""
    store, cursor, conn = _store_e_cursore()

    with patch.object(PostgreSQLStore, "_get_connection", return_value=conn):
        store.record_news_stream_subscription(["AAPL", "MSFT"])

    sql, params = cursor.execute.call_args[0]
    assert "news_stream_subscriptions" in sql
    assert ["AAPL", "MSFT"] in params
    assert 2 in params
    conn.commit.assert_called_once()


def test_record_news_stream_subscription_non_propaga_errori():
    """E' telemetria in avvio di un processo long-lived: se Postgres e' giu', lo
    stream deve partire lo stesso — la news vale piu' della sua misura."""
    store, _cursor, conn = _store_e_cursore()
    conn.cursor.side_effect = RuntimeError("postgres down")

    with patch.object(PostgreSQLStore, "_get_connection", return_value=conn):
        store.record_news_stream_subscription(["AAPL"])


def test_una_sottoscrizione_vuota_non_scrive_nulla():
    store, cursor, conn = _store_e_cursore()

    with patch.object(PostgreSQLStore, "_get_connection", return_value=conn):
        store.record_news_stream_subscription([])

    cursor.execute.assert_not_called()
