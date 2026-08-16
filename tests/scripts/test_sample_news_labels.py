"""Integrazione del sampler QX-01 (#54): target a 400 e key su news_log_id.

Il sampler e' offline/deterministico (seed fisso). Dopo la migrazione 046 il
vincolo UNIQUE(url) non c'e' piu' -> l'idempotenza passa su news_log_id
(NOT EXISTS) e ogni riga porta news_log_id + fetched_at denormalizzati.
Skip se Postgres non e' raggiungibile.
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
TEST_DB = "alembic_test_qx01_sampler"

import scripts.sample_news_labels as sampler  # noqa: E402


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
                             ._replace(path="/postgres")
                             .geturl())
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
                             ._replace(path="/postgres")
                             .geturl())
    maint.autocommit = True
    try:
        with maint.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
    finally:
        maint.close()


def _seed(url: str) -> None:
    """200 articoli per fonte: 80 near-zero (|raw_sentiment|<0.05, 40%) + 120 forti."""
    conn = psycopg2.connect(url)
    conn.autocommit = True
    with conn.cursor() as cur:
        for source in ("alpaca_benzinga", "gdelt_gkg", "marketaux"):
            for i in range(200):
                near = i < 80
                sent = 0.01 if near else 0.5
                cur.execute(
                    """INSERT INTO news_log (title, url, source, ticker, body_snippet,
                                              raw_sentiment, fetched_at, published_at)
                       VALUES (%s, %s, %s, %s, %s, %s,
                               '2026-07-01 10:00:00+00', '2026-07-01 09:00:00+00')""",
                    (f"{source}-{i}", f"https://{source}/{i}", source, "AAPL",
                     f"body {i}", sent),
                )
    conn.close()


def test_targets_sum_to_400_with_spec_split():
    assert sampler._TARGETS == {"alpaca_benzinga": 180, "gdelt_gkg": 150, "marketaux": 70}
    assert sum(sampler._TARGETS.values()) == 400


def test_sampler_seeds_400_pending_rows_with_news_log_id(db_url):
    _seed(db_url)
    with patch.dict(os.environ, {"DATABASE_URL": db_url}):
        sampler.main()

    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        cur.execute("""SELECT source, COUNT(*) FROM news_labels
                       WHERE status='pending' GROUP BY source ORDER BY source""")
        by_source = dict(cur.fetchall())
        # tante righe quanto il target per fonte (tutte disponibili).
        assert by_source == {"alpaca_benzinga": 180, "gdelt_gkg": 150, "marketaux": 70}

        cur.execute("""SELECT COUNT(*) FROM news_labels
                       WHERE status='pending'
                         AND (news_log_id IS NULL OR fetched_at IS NULL)""")
        assert cur.fetchone()[0] == 0   # news_log_id + fetched_at sempre popolati

        # oversample near-zero: ~40% delle righe hanno |raw_sentiment|<0.05
        # (verificato via join con news_log sul news_log_id appena seminato).
        cur.execute(
            """SELECT COUNT(*) FILTER (WHERE ABS(nl.raw_sentiment) < 0.05)::numeric
                     / NULLIF(COUNT(*), 0) AS near_frac
                 FROM news_labels lbl JOIN news_log nl ON nl.id = lbl.news_log_id
                WHERE lbl.status='pending'"""
        )
        near_frac = cur.fetchone()[0]
        assert near_frac is not None and 0.35 <= near_frac <= 0.45
    conn.close()


def test_sampler_is_idempotent_on_news_log_id(db_url):
    # Il secondo run non inserisce nulla (gia' presente una riga per news_log_id).
    with patch.dict(os.environ, {"DATABASE_URL": db_url}):
        sampler.main()
    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM news_labels WHERE status='pending'")
        assert cur.fetchone()[0] == 400
    conn.close()