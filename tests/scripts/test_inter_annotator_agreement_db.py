"""Integrazione DB dello script inter-annotator agreement (#54).

Verifica il wiring I/O: _load_pairs legge le coppie 2-annotator dallo schema
046, _report stampa kappa + worklist disaccordi, --adjudicate marca le righe.
Seed con kappa noti (dir ~0.375 <0.7, ticker ~0.79 >=0.6, 2 disaccordi).
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
TEST_DB = "alembic_test_qx01_kappa"

import scripts.inter_annotator_agreement as iaa  # noqa: E402


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


# (annotator A dir, A tickers, annotator B dir, B tickers)
PAIRS = [
    ("positive", ["AAPL"], "positive", ["AAPL"]),                          # accordo
    ("negative", ["MSFT"], "negative", ["MSFT"]),                         # accordo
    ("neutral", [],        "neutral", []),                                # accordo (both_empty)
    ("positive", ["AAPL"], "negative", ["AAPL"]),                        # disaccordo dir
    ("positive", ["AAPL", "MSFT"], "positive", ["AAPL"]),                 # disaccordo ticker (overlap)
]


def _seed(url: str) -> list[int]:
    """5 articoli, 2 annotatori (A, B) ciascuno. Ritorna i news_log_id.

    Pulisce le tabelle prima di seminare: il DB e' module-scoped e piu' test
    chiamano _seed, cosi' ogni test parte da stato noto (5 articoli)."""
    ids = []
    conn = psycopg2.connect(url)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("TRUNCATE news_labels, news_label_splits, news_log RESTART IDENTITY CASCADE")
        for i, (da, ta, db_, tb) in enumerate(PAIRS):
            cur.execute(
                """INSERT INTO news_log (title, url, source, ticker)
                   VALUES (%s, %s, 'alpaca_benzinga', 'AAPL') RETURNING id""",
                (f"art{i}", f"https://art/{i}"),
            )
            nid = cur.fetchone()[0]
            ids.append(nid)
            for ann, d, tk in (("A", da, ta), ("B", db_, tb)):
                cur.execute(
                    """INSERT INTO news_labels
                           (news_log_id, url, source, annotator_id, status,
                            gt_tickers, gt_sentiment_dir)
                       VALUES (%s, %s, 'alpaca_benzinga', %s, 'labeled', %s, %s)""",
                    (nid, f"https://art/{i}", ann, tk, d),
                )
    conn.close()
    return ids


def test_load_pairs_groups_two_annotators(db_url):
    ids = _seed(db_url)
    conn = psycopg2.connect(db_url)
    by_source = iaa._load_pairs(conn)
    conn.close()
    assert sorted(by_source) == ["alpaca_benzinga"]
    items = by_source["alpaca_benzinga"]
    assert len(items) == 5
    # slot ordinati per annotator_id: A prima di B.
    assert items[0]["dir"] == ("positive", "positive")
    assert items[0]["tickers"] == ({"AAPL"}, {"AAPL"})


def test_report_prints_kappa_and_disagreement_worklist(db_url, capsys):
    _seed(db_url)
    with patch.dict(os.environ, {"DATABASE_URL": db_url}):
        rc = iaa.main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Inter-annotator agreement" in out
    # 5 coppie, dir sotto soglia (<0.7 → "no"), ticker sopra (>=0.6 → "OK").
    assert "no" in out and "OK" in out
    assert "Adjudication worklist — 2 disaccordi" in out


def test_adjudicate_marks_both_rows_of_an_article(db_url):
    ids = _seed(db_url)
    target = ids[3]  # l'articolo in disaccordo di direzione
    with patch.dict(os.environ, {"DATABASE_URL": db_url}):
        rc = iaa.main(["--adjudicate", str(target), "adjudicator_x"])
    assert rc == 0
    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        cur.execute(
            """SELECT adjudicated, adjudicator_id FROM news_labels
               WHERE news_log_id = %s ORDER BY annotator_id""",
            (target,),
        )
        rows = cur.fetchall()
    conn.close()
    assert rows == [(True, "adjudicator_x"), (True, "adjudicator_x")]


def test_adjudicate_missing_article_marks_zero(db_url, capsys):
    with patch.dict(os.environ, {"DATABASE_URL": db_url}):
        rc = iaa.main(["--adjudicate", "999999", "adjudicator_y"])
    assert rc == 0
    assert "righe marcate=0" in capsys.readouterr().out


def test_adjudicated_pair_drops_from_worklist(db_url, capsys):
    """Il rilievo della review: dopo --adjudicate la coppia non deve piu'
    comparire nella worklist del report successivo. Altrimenti adjudication
    e' solo un flag estetico e i disaccordi vengono riproposti all'infinito."""
    ids = _seed(db_url)
    target = ids[3]  # l'articolo in disaccordo di direzione (vedi PAIRS[3])
    with patch.dict(os.environ, {"DATABASE_URL": db_url}):
        iaa.main(["--adjudicate", str(target), "adjudicator_x"])
        capsys.readouterr().out  # scarta l'output di adjudicate
        rc2 = iaa.main([])       # report dopo adjudication
    out = capsys.readouterr().out
    assert rc2 == 0
    # La coppia marcata esce dal dataset: 4 coppie residue, 1 disaccordo
    # residuo (PAIRS[4] = ticker overlap, l'unico non ancora adjudicated).
    assert "4 coppie 2-annotator" in out
    assert "Adjudication worklist — 1 disaccordi" in out
    # La riga del worklist deve riferire l'altro news_log_id, non quello adjudicato.
    # L'output formatta il news_log_id con padding, quindi confronto diretto
    # solo sull'assenza del target adjudicated.
    assert f"news_log_id={target}" not in out
    assert f"news_log_id={ids[4]}" in out.replace(" ", "")


def test_adjudicated_pair_excluded_from_kappa(db_url):
    """Dopo adjudication la coppia non entra nemmeno nel calcolo del kappa
    (altrimenti il dato 'risolto' continua a peggiorare la metrica)."""
    ids = _seed(db_url)
    target = ids[3]
    with patch.dict(os.environ, {"DATABASE_URL": db_url}):
        # kappa pre-adjudication: 5 coppie, 2 disaccordi (dir + ticker).
        iaa.main([])
        # adjudicate la sola coppia in disaccordo di direzione.
        iaa.main(["--adjudicate", str(target), "adjudicator_x"])
        conn = psycopg2.connect(db_url)
        by_source_post = iaa._load_pairs(conn)
        conn.close()
    items_post = by_source_post["alpaca_benzinga"]
    # 4 coppie residue (PAIRS[3] escluso).
    assert len(items_post) == 4
    assert all(it["news_log_id"] != target for it in items_post)