"""Integrazione della migrazione 046 (news_labels 2-annotator + adjudication), QX-01 #54.

La migrazione fa evolvere news_labels dallo schema single-annotator
(UNIQUE(url), una riga per articolo) allo schema 2-annotator + adjudication
della specifica (spec `docs/TICKER_SENTIMENT_QUALITY_REVIEW_2026-06-30.md`
§5.3-5.5): UNIQUE(news_log_id, annotator_id) + colonne adjudicated /
adjudicator_id, backfill di news_log_id dalle righe legacy url-keyed, e la
tabella news_label_splits per l'holdout 60/40.

Solo strumentazione/misura (freeze #171): nessuna taratura, nessun hot path.

Il test crea un database usa-e-getta sull'istanza Postgres raggiungibile e
applica le migrazioni dentro transazioni ribaltate; skip se Postgres non e'
disponibile (cosi' non aggiunge rumore alla CI gia' rossa per motivi ambientali).
"""

from __future__ import annotations

import os
import urllib.parse
from pathlib import Path

import psycopg2
import pytest

REPO = Path(__file__).resolve().parent.parent.parent
NEWS_LOG_MIGRATIONS = [
    (REPO / "migrations" / "006_add_news_log.sql").read_text(),
    (REPO / "migrations" / "027_news_log_published_at.sql").read_text(),
]
NEWS_LABELS_MIGRATION = (REPO / "migrations" / "029_news_labels.sql").read_text()
MIGRATION_046 = (REPO / "migrations" / "046_news_labels_2annotator.sql")

TEST_DB = "alembic_test_qx01_54"


def _candidate_urls() -> list[str]:
    configured = os.environ.get("DATABASE_URL", "postgresql://trading:trading@localhost:5432/trading")
    return [
        configured,
        "postgresql://trading:trading@localhost:5432/trading",
        "postgresql://trading:trading@localhost:5432/postgres",
    ]


def _maintenance_url(db_url: str) -> str:
    parsed = urllib.parse.urlparse(db_url)
    return urllib.parse.urlunparse(parsed._replace(path="/postgres"))


@pytest.fixture(scope="module")
def db_connection():
    """Crea un DB usa-e-getta, applica le migrazioni base di news_log, restituisce la connessione."""
    last_exc = None
    conn = None
    for url in _candidate_urls():
        try:
            psycopg2.connect(url, connect_timeout=3).close()
            base_url = url
            break
        except psycopg2.OperationalError as exc:
            last_exc = exc
    else:
        pytest.skip(f"Postgres non raggiungibile: {last_exc}")

    maint = psycopg2.connect(_maintenance_url(base_url))
    maint.autocommit = True
    try:
        with maint.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
            cur.execute(f"CREATE DATABASE {TEST_DB}")
    finally:
        maint.close()

    # Riusa le credenziali di base_url ma punta al DB di test.
    parsed = urllib.parse.urlparse(base_url)
    test_url = urllib.parse.urlunparse(parsed._replace(path=f"/{TEST_DB}"))
    conn = psycopg2.connect(test_url)
    conn.autocommit = True
    with conn.cursor() as cur:
        for sql in NEWS_LOG_MIGRATIONS:
            cur.execute(sql)
    yield conn
    conn.close()
    maint = psycopg2.connect(_maintenance_url(base_url))
    maint.autocommit = True
    try:
        with maint.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
    finally:
        maint.close()


def _reset_news_labels(cur) -> None:
    cur.execute("DROP TABLE IF EXISTS news_label_splits CASCADE")
    cur.execute("DROP TABLE IF EXISTS news_labels CASCADE")


class TestMigration046:
    """046 si applica pulita su schema base e impone le regole del 2-annotator."""

    def test_from_scratch_adds_columns_unique_and_splits_table(self, db_connection):
        cur = db_connection.cursor()
        try:
            _reset_news_labels(cur)
            cur.execute(NEWS_LABELS_MIGRATION)          # 029 (single-annotator)
            cur.execute(MIGRATION_046.read_text())       # 046 (upgrade)

            # Colonne nuove presenti.
            cur.execute(
                """SELECT column_name FROM information_schema.columns
                   WHERE table_name='news_labels' AND column_name IN
                         ('news_log_id','fetched_at','adjudicated','adjudicator_id')
                   ORDER BY column_name"""
            )
            assert [r[0] for r in cur.fetchall()] == sorted(
                ["news_log_id", "fetched_at", "adjudicated", "adjudicator_id"]
            )

            # Il vincolo legacy su url e' caduto, quello 2-annotator e' attivo.
            cur.execute(
                """SELECT indexname FROM pg_indexes
                   WHERE tablename='news_labels'
                     AND indexname IN ('news_labels_url_key',
                                       'news_labels_news_log_annotator_uniq')"""
            )
            names = {r[0] for r in cur.fetchall()}
            assert "news_labels_url_key" not in names
            assert "news_labels_news_log_annotator_uniq" in names

            # Tabella holdout presente.
            cur.execute(
                """SELECT 1 FROM information_schema.tables
                   WHERE table_name='news_label_splits'"""
            )
            assert cur.fetchone() is not None
        finally:
            cur.close()
            db_connection.rollback()

    def test_backfills_news_log_id_from_url_and_keeps_data(self, db_connection):
        """Path di upgrade: riga legacy url-keyed viene migrata senza perdere dati."""
        cur = db_connection.cursor()
        try:
            _reset_news_labels(cur)
            cur.execute(NEWS_LABELS_MIGRATION)          # 029
            # Una news_log esistente e una label legacy (single-annotator, url-keyed).
            cur.execute(
                """INSERT INTO news_log (title, url, source, ticker, body_snippet,
                                          raw_sentiment, fetched_at, published_at)
                   VALUES ('t', 'https://x/1', 'alpaca_benzinga', 'AAPL', 'b',
                           0.1, '2026-07-01 10:00:00+00', '2026-07-01 09:00:00+00')
                   RETURNING id"""
            )
            news_id = cur.fetchone()[0]
            cur.execute(
                """INSERT INTO news_labels (url, source, title, body_snippet,
                                             published_at, extracted_tickers,
                                             status, annotator_id, gt_tickers,
                                             gt_sentiment_dir)
                   VALUES ('https://x/1', 'alpaca_benzinga', 't', 'b',
                           '2026-07-01 09:00:00+00', '{AAPL}',
                           'labeled', 'operator', '{AAPL}', 'positive')"""
            )
            cur.execute(MIGRATION_046.read_text())      # 046 backfill

            cur.execute(
                """SELECT news_log_id, url, annotator_id, status, gt_tickers
                   FROM news_labels WHERE url='https://x/1'"""
            )
            row = cur.fetchone()
            assert row is not None
            assert row[0] == news_id          # backfill da url -> news_log.id
            assert row[1] == "https://x/1"    # url preservato (denormalizzato)
            assert row[2] == "operator"       # annotatore preservato
            assert row[3] == "labeled"
            assert row[4] == ["AAPL"]
        finally:
            cur.close()
            db_connection.rollback()

    def test_unique_allows_two_annotators_blocks_duplicate(self, db_connection):
        cur = db_connection.cursor()
        try:
            _reset_news_labels(cur)
            cur.execute(NEWS_LABELS_MIGRATION)
            cur.execute(
                """INSERT INTO news_log (title, url, source, ticker)
                   VALUES ('t','https://x/2','alpaca_benzinga','MSFT') RETURNING id"""
            )
            nid = cur.fetchone()[0]
            cur.execute(MIGRATION_046.read_text())

            # Due annotatori distinti sullo stesso articolo: ok (url denormalizzato,
            # come fa il sampler / la labeling flow su ogni riga).
            for ann in ("A", "B"):
                cur.execute(
                    """INSERT INTO news_labels (news_log_id, url, source, annotator_id, status)
                       VALUES (%s, 'https://x/2', 'alpaca_benzinga', %s, 'pending')""",
                    (nid, ann),
                )
            # Un terzo duplicato (stesso annotatore): deve essere rifiutato.
            with pytest.raises(psycopg2.errors.UniqueViolation):
                cur.execute(
                    """INSERT INTO news_labels (news_log_id, url, source, annotator_id, status)
                       VALUES (%s, 'https://x/2', 'alpaca_benzinga', 'A', 'pending')""",
                    (nid,),
                )
        finally:
            cur.close()
            db_connection.rollback()