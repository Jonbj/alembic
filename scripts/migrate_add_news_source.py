#!/usr/bin/env python3
"""Migration: add news_source column to backtest_signals.

Safe to run while a backtest is in progress — PostgreSQL adds nullable
columns without locking the table for writes.

Run once:
    python scripts/migrate_add_news_source.py
"""
import psycopg2
from src.config import config


def run() -> None:
    pg = psycopg2.connect(config.DATABASE_URL)
    try:
        with pg.cursor() as cur:
            cur.execute(
                "ALTER TABLE backtest_signals ADD COLUMN IF NOT EXISTS news_source VARCHAR"
            )
            cur.execute(
                "UPDATE backtest_signals SET news_source = 'gdelt' "
                "WHERE news_source IS NULL AND run_id LIKE 'gkg-%'"
            )
            cur.execute(
                "UPDATE backtest_signals SET news_source = 'gdelt' "
                "WHERE news_source IS NULL AND run_id LIKE 'dry-%'"
            )
            pg.commit()

            cur.execute(
                "SELECT news_source, COUNT(*) FROM backtest_signals "
                "GROUP BY news_source ORDER BY news_source"
            )
            print("news_source distribution after migration:")
            for source, count in cur.fetchall():
                print(f"  {source or 'NULL'}: {count}")
    finally:
        pg.close()


if __name__ == "__main__":
    run()
