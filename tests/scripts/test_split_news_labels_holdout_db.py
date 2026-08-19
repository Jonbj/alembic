"""Integrazione DB del holdout split 60/40 (#54).

Persiste lo split in news_label_splits (migrazione 046), idempotente (salta i
news_log_id gia' assegnati), ~60/40. Skip se Postgres non e' raggiungibile.
"""

from __future__ import annotations

import os
import urllib.parse
from pathlib import Path
from unittest.mock import patch

import psycopg2
import pytest

REPO = Path(__file__).resolve().parent.parent.parent
BASE_MIGRATIONS = [
    (REPO / "migrations" / "006_add_news_log.sql").read_text(),
    (REPO / "migrations" / "027_news_log_published_at.sql").read_text(),
    (REPO / "migrations" / "029_news_labels.sql").read_text(),
    (REPO / "migrations" / "046_news_labels_2annotator.sql").read_text(),
]
TEST_DB = "alembic_test_qx01_holdout"

import scripts.split_news_labels_holdout as holdout  # noqa: E402


def _test_url() -> str | None:
    for url in (
        os.environ.get("DATABASE_URL", ""),
        "postgresql://trading:trading@localhost:5432/trading",
        "postgresql://trading:trading@localhost:5432/postgres",
    ):
        if not url:
            continue
        try:
            psycopg2.connect(url, connect_timeout=3).close()
            return url
        except psycopg2.OperationalError:
            continue
    return None


@pytest.fixture(scope="module")
def db_url():
    base = _test_url()
    if base is None:
        pytest.skip("Postgres non raggiungibile")
    maint = psycopg2.connect(urllib.parse.urlparse(base)
                             ._replace(path="/postgres").geturl())
    maint.autocommit = True
    try:
        with maint.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
            cur.execute(f"CREATE DATABASE {TEST_DB}")
    finally:
        maint.close()
    url = urllib.parse.urlparse(base)._replace(path=f"/{TEST_DB}").geturl()
    conn = psycopg2.connect(url)
    conn.autocommit = True
    with conn.cursor() as cur:
        for sql in BASE_MIGRATIONS:
            cur.execute(sql)
    conn.close()
    yield url
    maint = psycopg2.connect(urllib.parse.urlparse(base)
                             ._replace(path="/postgres").geturl())
    maint.autocommit = True
    try:
        with maint.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
    finally:
        maint.close()


def _seed_articles(url: str, n: int = 10) -> None:
    conn = psycopg2.connect(url)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("TRUNCATE news_labels, news_label_splits, news_log RESTART IDENTITY CASCADE")
        for i in range(n):
            cur.execute(
                """INSERT INTO news_log (title, url, source, ticker)
                   VALUES (%s, %s, 'alpaca_benzinga', 'AAPL') RETURNING id""",
                (f"a{i}", f"https://a/{i}"),
            )
            nid = cur.fetchone()[0]
            cur.execute(
                """INSERT INTO news_labels (news_log_id, url, source, status)
                   VALUES (%s, %s, 'alpaca_benzinga', 'pending')""",
                (nid, f"https://a/{i}"),
            )
    conn.close()


def test_main_assigns_60_40_and_persists(db_url):
    _seed_articles(db_url, n=10)
    with patch.dict(os.environ, {"DATABASE_URL": db_url}):
        rc = holdout.main()
    assert rc == 0
    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        cur.execute("SELECT split, COUNT(*) FROM news_label_splits GROUP BY split")
        counts = dict(cur.fetchall())
    conn.close()
    assert counts == {"train": 6, "test": 4}   # round(10*0.6)=6


def test_main_is_idempotent(db_url, capsys):
    # Stato lasciato dal test precedente: 10 articoli gia' assegnati.
    with patch.dict(os.environ, {"DATABASE_URL": db_url}):
        rc = holdout.main()
    assert rc == 0
    assert "Nessun nuovo news_log_id da assegnare" in capsys.readouterr().out
    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM news_label_splits")
        assert cur.fetchone()[0] == 10
    conn.close()


def test_split_is_deterministic_across_runs(db_url):
    # Nuovi 10 articoli (id 11..20) → stessi split del primo batch per quegli id.
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("TRUNCATE news_labels, news_label_splits, news_log RESTART IDENTITY CASCADE")
        for i in range(10):
            cur.execute(
                """INSERT INTO news_log (title, url, source, ticker)
                   VALUES (%s, %s, 'alpaca_benzinga', 'AAPL') RETURNING id""",
                (f"b{i}", f"https://b/{i}"),
            )
            nid = cur.fetchone()[0]
            cur.execute(
                """INSERT INTO news_labels (news_log_id, url, source, status)
                   VALUES (%s, %s, 'alpaca_benzinga', 'pending')""",
                (nid, f"https://b/{i}"),
            )
    conn.close()
    expected = holdout.assign_splits(list(range(1, 11)))
    with patch.dict(os.environ, {"DATABASE_URL": db_url}):
        holdout.main()
    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        cur.execute("SELECT news_log_id, split FROM news_label_splits ORDER BY news_log_id")
        got = {r[0]: r[1] for r in cur.fetchall()}
    conn.close()
    assert got == expected