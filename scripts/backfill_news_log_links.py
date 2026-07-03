#!/usr/bin/env python3
"""FIX-05: backfill sentiment_signals.news_log_id for legacy rows (pre QS-09).

Conservative by design: a signal is linked ONLY when exactly one news_log row
matches (same ticker, published/logged within ±30 min of the signal). Ambiguous
or unmatched rows stay NULL and keep reporting as source='unknown' — a wrong
link would corrupt per-source P&L attribution, which is worse than a gap.

Usage (inside the worker container):
    python scripts/backfill_news_log_links.py            # dry-run (default)
    python scripts/backfill_news_log_links.py --apply    # write links
"""
from __future__ import annotations

import argparse

from src.store.pg_store import PostgreSQLStore

_FIND_CANDIDATES = """
    SELECT ss.id AS signal_id,
           (ARRAY_AGG(nl.id))[1] AS news_log_id,
           COUNT(*) AS n_matches
    FROM sentiment_signals ss
    JOIN news_log nl
      ON nl.ticker = ss.symbol
     AND nl.published_at IS NOT NULL
     AND ABS(EXTRACT(EPOCH FROM (ss.generated_at - nl.published_at))) < 1800
    WHERE ss.news_log_id IS NULL
    GROUP BY ss.id
"""

_APPLY = "UPDATE sentiment_signals SET news_log_id = %s WHERE id = %s AND news_log_id IS NULL"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write links (default: dry-run)")
    args = parser.parse_args()

    pg = PostgreSQLStore()
    try:
        conn = pg._get_connection()
        with conn.cursor() as cur:
            cur.execute(_FIND_CANDIDATES)
            rows = cur.fetchall()
        unambiguous = [(r[1], r[0]) for r in rows if r[2] == 1]
        print(f"signals without link matched: {len(rows)} "
              f"(unambiguous: {len(unambiguous)}, ambiguous skipped: {len(rows) - len(unambiguous)})")
        if not args.apply:
            print("dry-run — re-run with --apply to write")
            return
        with conn.cursor() as cur:
            for news_log_id, signal_id in unambiguous:
                cur.execute(_APPLY, (news_log_id, signal_id))
        conn.commit()
        print(f"linked {len(unambiguous)} signals")
    finally:
        pg.close()


if __name__ == "__main__":
    main()
