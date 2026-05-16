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
    pg.autocommit = True  # DDL fuori da transazione esplicita
    try:
        with pg.cursor() as cur:
            # lock_timeout=0 → fallisce subito se non riesce ad acquisire il lock
            # invece di entrare in coda e bloccare il backtest attivo
            cur.execute("SET lock_timeout = '2s'")
            try:
                cur.execute(
                    "ALTER TABLE backtest_signals ADD COLUMN IF NOT EXISTS news_source VARCHAR"
                )
            except Exception as e:
                print(f"ALTER TABLE fallita (backtest attivo?): {e}")
                print("Riesegui la migrazione dopo che il backtest ha completato.")
                return

            cur.execute("SET lock_timeout = 0")  # reset per gli UPDATE

        pg.autocommit = False
        with pg.cursor() as cur:
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
