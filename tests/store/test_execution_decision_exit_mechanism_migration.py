"""Migration 039: execution_decisions.exit_mechanism schema smoke test (#60).

Connects to the database configured by DATABASE_URL. If the test database is
not reachable (e.g. the pytest default test_db has no credentials in this
environment), the tests skip rather than reroute to an operational database.
"""

from __future__ import annotations

import os

import psycopg2
import pytest


def _connect_or_skip() -> psycopg2.extensions.connection:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        pytest.skip("DATABASE_URL not set")
    try:
        return psycopg2.connect(url)
    except psycopg2.OperationalError as exc:
        pytest.skip(f"Database unreachable for migration smoke test: {exc}")


@pytest.mark.skipif(
    os.environ.get("SKIP_DB_TESTS"),
    reason="SKIP_DB_TESTS set",
)
def test_migration_039_exit_mechanism_column_exists() -> None:
    """execution_decisions has the exit_mechanism column."""
    with _connect_or_skip() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'execution_decisions' AND column_name = 'exit_mechanism'
                """
            )
            found = cur.fetchall()
    assert len(found) == 1, "execution_decisions.exit_mechanism column is missing"
