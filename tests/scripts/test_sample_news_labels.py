"""Integrazione del sampler QX-01 (#54): target a 400 e key su news_log_id.

Il sampler e' offline/deterministico (seed fisso). Dopo la migrazione 046 il
vincolo UNIQUE(url) non c'e' piu' -> l'idempotenza passa su news_log_id
(NOT EXISTS) e ogni riga porta news_log_id + fetched_at denormalizzati.
Skip se Postgres non e' raggiungibile.
"""

from __future__ import annotations

import os
import random
import urllib.parse
from pathlib import Path
from unittest.mock import patch

import psycopg2
import psycopg2.extras
import pytest

REPO = Path(__file__).resolve().parent.parent.parent
BASE_MIGRATIONS = [
    (REPO / "migrations" / "006_add_news_log.sql").read_text(),
    (REPO / "migrations" / "027_news_log_published_at.sql").read_text(),
    (REPO / "migrations" / "029_news_labels.sql").read_text(),
    (REPO / "migrations" / "030_news_log_extraction_method.sql").read_text(),
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
        sampler.main([])

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
        sampler.main([])
    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM news_labels WHERE status='pending'")
        assert cur.fetchone()[0] == 400
    conn.close()


# --- #461: finestra temporale + stratificazione per extraction_method -----------

def _seed_qt03_articles(url: str) -> None:
    """Articoli post-QT-03 (extraction_method valorizzato) per i test di finestra.

    200 alpaca_benzinga/source_metadata + 250 gdelt_gkg/org_lookup +
    5 marketaux/source_metadata pubblicati 2026-07-02 (dentro la finestra),
    piu' 20 alpaca_benzinga a metodo NULL pubblicati 2026-06-15 (fuori finestra):
    la popolazione reale post-QT-03 ha marketaux=5 (target storico 70 irrealizzabile).
    """
    conn = psycopg2.connect(url)
    conn.autocommit = True
    with conn.cursor() as cur:
        for source, method, n in (("alpaca_benzinga", "source_metadata", 200),
                                  ("gdelt_gkg", "org_lookup", 250),
                                  ("marketaux", "source_metadata", 5)):
            for i in range(n):
                cur.execute(
                    """INSERT INTO news_log (title, url, source, ticker, body_snippet,
                                              raw_sentiment, extraction_method,
                                              fetched_at, published_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s,
                               '2026-07-02 12:00:00+00', '2026-07-02 10:00:00+00')""",
                    (f"qt03 {source} {i}", f"https://qt03/{source}/{i}", source, "AAPL",
                     f"body {i}", 0.01 if i % 5 == 0 else 0.5, method),
                )
        for i in range(20):   # pre-QT-03: fuori finestra, extraction_method NULL
            cur.execute(
                """INSERT INTO news_log (title, url, source, ticker, body_snippet,
                                          raw_sentiment, fetched_at, published_at)
                   VALUES (%s, %s, 'alpaca_benzinga', 'AAPL', %s, 0.5,
                           '2026-06-15 12:00:00+00', '2026-06-15 10:00:00+00')""",
                (f"pre-qt03 {i}", f"https://qt03/pre/{i}", f"body {i}"),
            )
    conn.close()


def test_post_qt03_targets_are_explicit_per_extraction_method():
    # Target della finestra post-QT-03: espliciti per (source, extraction_method),
    # totale 400, marketaux ricalibrato sull'intera popolazione disponibile (5).
    targets = sampler._TARGETS_POST_QT03
    assert set(targets) == {
        ("alpaca_benzinga", "source_metadata"),
        ("gdelt_gkg", "org_lookup"),
        ("marketaux", "source_metadata"),
    }
    assert sum(targets.values()) == 400
    assert targets[("marketaux", "source_metadata")] == 5


def test_window_sampler_riserva_lo_strato_near_zero_ai_content_mill():
    """#508 — i template noti entrano nel golden set prima del near-zero casuale.

    Si riusa la quota near-zero gia' dichiarata dal sampler: nessun nuovo target
    o parametro di campionamento viene introdotto durante il freeze.
    """
    articles = [
        {
            "news_log_id": 1,
            "title": "If You Invested $100 In Goldman Sachs 15 Years Ago",
            "abs_sent": 0.002,
        },
        {
            "news_log_id": 2,
            "title": "6 Financials Stocks Whale Activity In Today's Session",
            "abs_sent": 0.0,
        },
        {"news_log_id": 3, "title": "Generic neutral one", "abs_sent": 0.01},
        {"news_log_id": 4, "title": "Generic neutral two", "abs_sent": 0.01},
        {"news_log_id": 5, "title": "Material earnings beat", "abs_sent": 0.5},
    ]

    picked = sampler._pick(
        articles, 5, random.Random(42), content_empty_stratum=True
    )

    # round(5 * 0.40) = 2: entrambi gli slot near-zero dedicati sono occupati
    # dai due casi CONTENT_EMPTY, non lasciati al sorteggio fra tutti i neutri.
    assert {row["news_log_id"] for row in picked[:2]} == {1, 2}


def test_da_window_stratifies_by_extraction_method(db_url):
    _seed_qt03_articles(db_url)
    with patch.dict(os.environ, {"DATABASE_URL": db_url}):
        sampler.main(["--da", "2026-07-01"])

    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        # Composizione per (source, extraction_method) delle sole righe della
        # finestra (url qt03/): deve coincidere coi target dichiarati, non ci
        # sono riempimenti silenziosi fra rami.
        cur.execute(
            """SELECT lbl.source, nl.extraction_method, COUNT(*)
                 FROM news_labels lbl JOIN news_log nl ON nl.id = lbl.news_log_id
                WHERE lbl.status = 'pending' AND lbl.url LIKE 'https://qt03/%'
                  AND nl.published_at < '2026-06-15'
                GROUP BY 1, 2"""
        )
        assert cur.fetchall() == []   # niente articoli fuori finestra

        cur.execute(
            """SELECT lbl.source, nl.extraction_method, COUNT(*)
                 FROM news_labels lbl JOIN news_log nl ON nl.id = lbl.news_log_id
                WHERE lbl.status = 'pending' AND lbl.url LIKE 'https://qt03/%'
                GROUP BY 1, 2 ORDER BY 1, 2"""
        )
        by_stratum = {(r[0], r[1]): r[2] for r in cur.fetchall()}
        assert by_stratum == dict(sampler._TARGETS_POST_QT03)
    conn.close()


def test_windowed_output_states_collinearity_limit(db_url, capsys):
    # Il limite method<->source e' una premessa della misura #405: deve stare
    # nell'output, non essere scoperto a valle. Run idempotente (gia' inseito).
    with patch.dict(os.environ, {"DATABASE_URL": db_url}):
        sampler.main(["--da", "2026-07-01"])
    out = capsys.readouterr().out
    assert "collinear" in out


def test_windowed_output_declares_untargeted_strata(db_url, capsys):
    # La composizione comprende anche fonti senza target: cnbc/regex va dichiarato
    # escluso, non puo' sparire solo perche' cnbc non compare nei target QX-01.
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO news_log (title, url, source, ticker, body_snippet,
                                      raw_sentiment, extraction_method,
                                      fetched_at, published_at)
               SELECT 'qt03 cnbc', 'https://qt03/cnbc/review-regression', 'cnbc',
                      'AAPL', 'body', 0.5, 'regex',
                      '2026-07-02 12:00:00+00', '2026-07-02 10:00:00+00'
                WHERE NOT EXISTS (
                      SELECT 1 FROM news_log
                       WHERE url = 'https://qt03/cnbc/review-regression')"""
        )
    conn.close()

    with patch.dict(os.environ, {"DATABASE_URL": db_url}), \
         patch.object(sampler, "_TARGETS_POST_QT03", {}):
        sampler.main(["--da", "2026-07-01"])
    out = capsys.readouterr().out
    assert "cnbc/regex: 1 available — excluded (no target for this stratum)" in out


def test_branch_under_target_is_loud_and_not_backfilled(db_url, capsys):
    # Target marketaux storico (70) irrealizzabile: 5 disponibili. Il ramo resta
    # sotto target, viene detto esplicitamente, exit code 1, e l'altro ramo NON
    # assorbe la differenza (gdelt resta al suo target).
    patched = dict(sampler._TARGETS_POST_QT03)
    patched[("marketaux", "source_metadata")] = 70
    with patch.dict(os.environ, {"DATABASE_URL": db_url}), \
         patch.object(sampler, "_TARGETS_POST_QT03", patched):
        with pytest.raises(SystemExit) as exc:
            sampler.main(["--da", "2026-07-01"])
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "marketaux/source_metadata" in out
    assert "UNDER TARGET" in out

    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        cur.execute(
            """SELECT COUNT(*) FROM news_labels lbl
                 JOIN news_log nl ON nl.id = lbl.news_log_id
                WHERE lbl.status = 'pending' AND lbl.url LIKE 'https://qt03/%'
                  AND nl.source = 'gdelt_gkg'"""
        )
        assert cur.fetchone()[0] == sampler._TARGETS_POST_QT03[("gdelt_gkg", "org_lookup")]
    conn.close()


def test_fetch_articles_respects_window_bounds(db_url):
    # --da e' inclusivo, --a copre l'intera giornata indicata (bound = giorno+1).
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    with conn.cursor() as cur:
        for i, pub in ((0, "2026-06-15 10:00:00+00"),   # prima di --da
                       (1, "2026-07-02 10:00:00+00"),   # dentro
                       (2, "2026-07-05 10:00:00+00")):  # dopo --a
            cur.execute(
                """INSERT INTO news_log (title, url, source, ticker, body_snippet,
                                          raw_sentiment, extraction_method,
                                          fetched_at, published_at)
                   VALUES (%s, %s, 'gdelt_gkg', 'AAPL', 'b', 0.5, 'org_lookup',
                           %s, %s)""",
                (f"win {i}", f"https://qt03win/{i}", pub, pub),
            )
    conn.close()

    import datetime
    conn = psycopg2.connect(db_url)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        rows = sampler._fetch_articles(cur, "gdelt_gkg",
                                       da=datetime.date(2026, 7, 1),
                                       a=datetime.date(2026, 7, 2))
    conn.close()
    assert sorted(r["url"] for r in rows if r["url"].startswith("https://qt03win/")) == \
        ["https://qt03win/1"]
