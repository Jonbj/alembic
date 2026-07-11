"""Migration 034: stop-loss redesign schema smoke test.

Connects to the database configured by DATABASE_URL. If the test database is
not reachable (e.g. the pytest default test_db has no credentials in this
environment), the tests skip rather than reroute to an operational database.
"""

from __future__ import annotations

import os
from typing import Any

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
def test_migration_034_columns_exist() -> None:
    """trades table has the freeze-at-entry stop columns."""
    expected = {
        "stop_strategy",
        "stop_mode",
        "stop_vol_at_entry",
        "stop_k",
        "stop_floor",
        "stop_cap",
        "stop_d_init",
        "stop_vol_source",
    }
    with _connect_or_skip() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'trades' AND column_name LIKE 'stop_%%'
                """
            )
            found = {row[0] for row in cur.fetchall()}
    assert expected <= found, f"Missing columns: {expected - found}"


@pytest.mark.skipif(
    os.environ.get("SKIP_DB_TESTS"),
    reason="SKIP_DB_TESTS set",
)
def test_migration_034_tables_exist_and_insertable() -> None:
    """stop_decisions and stop_shadow_log exist and accept a minimal row."""
    with _connect_or_skip() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_name IN ('stop_decisions', 'stop_shadow_log')
                """
            )
            found = {row[0] for row in cur.fetchall()}
            assert {"stop_decisions", "stop_shadow_log"} <= found

            cur.execute(
                """
                INSERT INTO stop_decisions (symbol, mode, cycle_ts)
                VALUES ('TEST', 'fixed', now()) RETURNING id
                """
            )
            decision_id: Any = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO stop_shadow_log (cycle_ts, symbol, d_init_fixed, trigger_fixed,
                                             would_breach_fixed, d_init_vol_scaled,
                                             trigger_vol_scaled, would_breach_vol_scaled)
                VALUES (now(), 'TEST', 0.02, 98.0, false, 0.03, 97.0, false)
                RETURNING id
                """
            )
            shadow_id: Any = cur.fetchone()[0]
            conn.commit()

            # Cleanup
            cur.execute("DELETE FROM stop_decisions WHERE id = %s", (decision_id,))
            cur.execute("DELETE FROM stop_shadow_log WHERE id = %s", (shadow_id,))
            conn.commit()
