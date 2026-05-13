"""Seed the ticker_lookup table from data/sp500_tickers.csv.

Run once after applying migration 004:
    python scripts/seed_ticker_lookup.py
"""
import csv
import os
import sys
from pathlib import Path

import psycopg2

DATA_PATH = Path(__file__).parent.parent / "data" / "sp500_tickers.csv"


def seed(database_url: str) -> int:
    conn = psycopg2.connect(database_url)
    inserted = 0
    try:
        with conn.cursor() as cur:
            with DATA_PATH.open() as f:
                reader = csv.DictReader(f)
                for row in reader:
                    raw_aliases = row.get("aliases", "").strip()
                    aliases = [a.strip() for a in raw_aliases.split("|") if a.strip()]
                    cur.execute(
                        """
                        INSERT INTO ticker_lookup (company_name, ticker, source, aliases)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (lower(company_name), ticker) DO NOTHING
                        """,
                        (row["company_name"], row["ticker"], row["source"], aliases),
                    )
                    if cur.rowcount:
                        inserted += 1
        conn.commit()
    finally:
        conn.close()
    return inserted


if __name__ == "__main__":
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)
    n = seed(url)
    print(f"Inserted {n} rows into ticker_lookup")
