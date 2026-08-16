#!/usr/bin/env python3
"""Sample the QX-01 golden label set into news_labels (offline, deterministic).

Selects 400 DISTINCT articles (by url) from news_log — 180 alpaca_benzinga /
150 gdelt_gkg / 70 marketaux (spec §5.9 Fase 1) — stratified by source and
oversampling the near-zero-sentiment failure mode, with a fixed seed for
reproducibility. Populates extracted_tickers (the system's tickers, for later
precision/recall) and status='pending'. Each row carries news_log_id +
fetched_at denormalized (schema 2-annotator, migrazione 046). Idempotent: one
pending row per article, guarded on news_log_id (il vecchio ON CONFLICT(url) non
esiste piu' — UNIQUE e' ora (news_log_id, annotator_id)).

Run inside the worker container (reaches postgres):
    docker compose exec worker python scripts/sample_news_labels.py
"""
from __future__ import annotations

import os
import random

import psycopg2
import psycopg2.extras

_SEED = 42
# Per-source targets (sum 400 — spec §5.9 Fase 1). gdelt has headline-only bodies
# → text_adequacy hint. 180/150/70 = alpaca_benzinga / gdelt_gkg / marketaux.
_TARGETS = {"alpaca_benzinga": 180, "gdelt_gkg": 150, "marketaux": 70}
_NEAR_ZERO_FRACTION = 0.40   # oversample |raw_sentiment| < 0.05 (failure mode F2)
_NEAR_ZERO_THRESHOLD = 0.05


def _conn():
    url = os.environ.get("DATABASE_URL", "postgresql://trading:trading@postgres:5432/trading")
    return psycopg2.connect(url)


def _fetch_articles(cur, source: str) -> list[dict]:
    """Distinct articles for a source, with aggregated tickers and |raw_sentiment|.

    news_log ha una riga per (url, ticker): per articolo si prende un news_log_id
    rappresentativo (MAX(id)) piu' fetched_at, mantenuti denormalizzati su ogni
    riga di news_labels (lo schema 2-annotator keya su news_log_id)."""
    cur.execute(
        """
        SELECT MAX(id)                        AS news_log_id,
               url,
               MAX(title)                     AS title,
               MAX(body_snippet)               AS body_snippet,
               MAX(published_at)               AS published_at,
               MAX(fetched_at)                 AS fetched_at,
               array_agg(DISTINCT ticker)      AS tickers,
               MAX(ABS(COALESCE(raw_sentiment,0))) AS abs_sent
        FROM news_log
        WHERE source = %s AND url <> ''
        GROUP BY url
        """,
        (source,),
    )
    return [dict(r) for r in cur.fetchall()]


def _pick(articles: list[dict], n: int, rng: random.Random) -> list[dict]:
    """Pick n articles, oversampling near-zero sentiment, deterministically."""
    near = [a for a in articles if a["abs_sent"] < _NEAR_ZERO_THRESHOLD]
    rest = [a for a in articles if a["abs_sent"] >= _NEAR_ZERO_THRESHOLD]
    rng.shuffle(near)
    rng.shuffle(rest)
    n_near = min(len(near), int(round(n * _NEAR_ZERO_FRACTION)))
    picked = near[:n_near] + rest[: n - n_near]
    # top up from whatever remains if a bucket was short
    if len(picked) < n:
        remaining = (near[n_near:] + rest[n - n_near:])
        picked += remaining[: n - len(picked)]
    return picked[:n]


def main() -> None:
    rng = random.Random(_SEED)
    inserted = 0
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            for source, target in _TARGETS.items():
                articles = _fetch_articles(cur, source)
                picked = _pick(articles, target, rng)
                adequacy = "headline_only" if source == "gdelt_gkg" else "full"
                for a in picked:
                    # Idempotenza su news_log_id: una pending row per articolo.
                    # (ON CONFLICT (url) non e' piu' valido dopo la 046; annotator_id
                    # e' NULL sulle pending — il vincolo UNIQUE(news_log_id, annotator_id)
                    # tratta i NULL come distinti, quindi serve il guard NOT EXISTS.)
                    cur.execute(
                        """
                        INSERT INTO news_labels
                            (news_log_id, url, source, title, body_snippet,
                             published_at, fetched_at, extracted_tickers,
                             text_adequacy, status)
                        SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending'
                        WHERE NOT EXISTS (
                            SELECT 1 FROM news_labels WHERE news_log_id = %s
                        )
                        """,
                        (a["news_log_id"], a["url"], source, a["title"],
                         a["body_snippet"], a["published_at"], a["fetched_at"],
                         a["tickers"], adequacy, a["news_log_id"]),
                    )
                    inserted += cur.rowcount
                print(f"{source}: {len(articles)} available → picked {len(picked)}")
        conn.commit()
    print(f"Inserted {inserted} new label rows (pending).")


if __name__ == "__main__":
    main()
