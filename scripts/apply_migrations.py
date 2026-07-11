#!/usr/bin/env python3
"""Apply all migrations/*.sql files, in order, to DATABASE_URL.

The project has no migration-tracking table — migrations have historically been
applied by hand, once, to the long-lived local/prod database. This script replays
the full numbered sequence against a database from scratch (CI's fresh Postgres
service container, or a new local setup). Not safe to rerun against a database that
already has some migrations applied: non-idempotent DDL (e.g. CREATE TYPE without an
IF NOT EXISTS guard) will error on a second pass.

Run:
    .venv/bin/python scripts/apply_migrations.py
"""
from __future__ import annotations

import glob
import os

import psycopg2

_MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "migrations")


def main() -> None:
    database_url = os.environ.get(
        "DATABASE_URL", "postgresql://trading:trading@localhost:5432/trading"
    )
    paths = sorted(glob.glob(os.path.join(_MIGRATIONS_DIR, "*.sql")))
    if not paths:
        print("No migration files found.")
        return

    conn = psycopg2.connect(database_url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            for path in paths:
                print(f"Applying {os.path.basename(path)}")
                with open(path) as f:
                    cur.execute(f.read())
    finally:
        conn.close()
    print(f"Applied {len(paths)} migrations.")


if __name__ == "__main__":
    main()
