#!/usr/bin/env python3
"""Sample the QX-01 golden label set into news_labels (offline, deterministic).

Selects ~150 DISTINCT articles (by url) from news_log, stratified by source and
oversampling the near-zero-sentiment failure mode, with a fixed seed for
reproducibility. Populates extracted_tickers (the system's tickers, for later
precision/recall) and status='pending'. Idempotent (ON CONFLICT(url) DO NOTHING).

Run inside the worker container (reaches postgres):
    docker compose exec worker python scripts/sample_news_labels.py
"""
from __future__ import annotations

import os
import random

import psycopg2
import psycopg2.extras

_SEED = 42
# Per-source targets (sum 150). gdelt has headline-only bodies → text_adequacy hint.
_TARGETS = {"marketaux": 40, "alpaca_benzinga": 60, "gdelt_gkg": 50}
_NEAR_ZERO_FRACTION = 0.40   # oversample |raw_sentiment| < 0.05 (failure mode F2)
_NEAR_ZERO_THRESHOLD = 0.05


def _conn():
    url = os.environ.get("DATABASE_URL", "postgresql://trading:trading@postgres:5432/trading")
    return psycopg2.connect(url)


def _fetch_articles(cur, source: str) -> list[dict]:
    """Distinct articles for a source, with aggregated tickers and |raw_sentiment|."""
    cur.execute(
        """
        SELECT url,
               MAX(title)                          AS title,
               MAX(body_snippet)                   AS body_snippet,
               MAX(published_at)                   AS published_at,
               array_agg(DISTINCT ticker)          AS tickers,
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
                    cur.execute(
                        """
                        INSERT INTO news_labels
                            (url, source, title, body_snippet, published_at,
                             extracted_tickers, text_adequacy, status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending')
                        ON CONFLICT (url) DO NOTHING
                        """,
                        (a["url"], source, a["title"], a["body_snippet"],
                         a["published_at"], a["tickers"], adequacy),
                    )
                    inserted += cur.rowcount
                print(f"{source}: {len(articles)} available → picked {len(picked)}")
        conn.commit()
    print(f"Inserted {inserted} new label rows (pending).")


if __name__ == "__main__":
    main()
