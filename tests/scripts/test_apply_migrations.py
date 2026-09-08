"""Regression tests for the tracked deployment migration runner (#532)."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import psycopg2
import pytest

from scripts.apply_migrations import MigrationError, apply_migrations


@pytest.fixture
def migration_db():
    url = os.environ.get(
        "DATABASE_URL", "postgresql://trading:trading@localhost:5432/trading"
    )
    try:
        conn = psycopg2.connect(url, connect_timeout=3)
    except psycopg2.OperationalError as exc:
        pytest.skip(f"PostgreSQL locale non disponibile: {exc}")

    schema = f"test_deploy_migrations_{uuid4().hex}"
    try:
        with conn.cursor() as cur:
            cur.execute(f'CREATE SCHEMA "{schema}"')
            cur.execute(f'SET search_path TO "{schema}", pg_catalog')
        conn.commit()
        yield conn
    finally:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        conn.commit()
        conn.close()


def _migration(directory: Path, filename: str, sql: str) -> Path:
    path = directory / filename
    path.write_text(sql)
    return path


def _ledger_rows(conn) -> list[tuple[str, str]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT filename, execution_kind
            FROM alembic_schema_migrations
            ORDER BY filename
            """
        )
        return list(cur.fetchall())


def test_fresh_database_applies_in_order_and_records_checksums(
    migration_db, tmp_path: Path
):
    second = _migration(
        tmp_path,
        "002_second.sql",
        "ALTER TABLE first_table ADD COLUMN marker INTEGER NOT NULL DEFAULT 2;",
    )
    first = _migration(
        tmp_path,
        "001_first.sql",
        "CREATE TABLE first_table (id INTEGER PRIMARY KEY);",
    )

    result = apply_migrations(migration_db, [second, first])

    assert result.applied == ("001_first.sql", "002_second.sql")
    assert result.baselined == ()
    assert _ledger_rows(migration_db) == [
        ("001_first.sql", "applied"),
        ("002_second.sql", "applied"),
    ]


def test_fresh_database_ignores_legacy_baseline_option(
    migration_db, tmp_path: Path
):
    migration = _migration(
        tmp_path,
        "001_initial.sql",
        "CREATE TABLE fresh_table (id INTEGER PRIMARY KEY);",
    )

    result = apply_migrations(
        migration_db,
        [migration],
        bootstrap_existing_through=59,
    )

    assert result.applied == ("001_initial.sql",)
    assert result.baselined == ()
    assert _ledger_rows(migration_db) == [("001_initial.sql", "applied")]


def test_existing_database_requires_explicit_guarded_baseline(
    migration_db, tmp_path: Path
):
    with migration_db.cursor() as cur:
        cur.execute("CREATE TABLE unrelated_existing_table (id INTEGER)")
    migration_db.commit()
    migration = _migration(
        tmp_path, "001_initial.sql", "CREATE TABLE should_not_run (id INTEGER);"
    )

    with pytest.raises(MigrationError, match="non-empty database"):
        apply_migrations(migration_db, [migration])


def test_baseline_059_requires_sentinel_then_applies_060_onward(
    migration_db, tmp_path: Path
):
    migration_001 = _migration(
        tmp_path,
        "001_initial.sql",
        "CREATE TABLE legacy_table (id INTEGER);",
    )
    migration_059 = _migration(
        tmp_path,
        "059_ensemble_cycle_health.sql",
        "CREATE TABLE ensemble_cycle_health (id INTEGER);",
    )
    migration_060 = _migration(
        tmp_path,
        "060_new_metric.sql",
        "CREATE TABLE new_metric (id INTEGER);",
    )
    with migration_db.cursor() as cur:
        cur.execute("CREATE TABLE legacy_table (id INTEGER)")
        cur.execute("CREATE TABLE ensemble_cycle_health (id INTEGER)")
    migration_db.commit()

    result = apply_migrations(
        migration_db,
        [migration_060, migration_001, migration_059],
        bootstrap_existing_through=59,
    )

    assert result.baselined == (
        "001_initial.sql",
        "059_ensemble_cycle_health.sql",
    )
    assert result.applied == ("060_new_metric.sql",)
    assert _ledger_rows(migration_db) == [
        ("001_initial.sql", "baseline"),
        ("059_ensemble_cycle_health.sql", "baseline"),
        ("060_new_metric.sql", "applied"),
    ]


def test_baseline_refuses_missing_059_sentinel(migration_db, tmp_path: Path):
    migration = _migration(
        tmp_path,
        "059_ensemble_cycle_health.sql",
        "CREATE TABLE ensemble_cycle_health (id INTEGER);",
    )
    with migration_db.cursor() as cur:
        cur.execute("CREATE TABLE legacy_table_without_sentinel (id INTEGER)")
    migration_db.commit()

    with pytest.raises(MigrationError, match="ensemble_cycle_health"):
        apply_migrations(
            migration_db, [migration], bootstrap_existing_through=59
        )


def test_baseline_refuses_any_unreviewed_version(migration_db, tmp_path: Path):
    migration = _migration(
        tmp_path,
        "058_unreviewed.sql",
        "CREATE TABLE unreviewed (id INTEGER);",
    )

    with pytest.raises(MigrationError, match="only reviewed legacy baseline is 059"):
        apply_migrations(
            migration_db, [migration], bootstrap_existing_through=58
        )


def test_second_run_is_noop_and_checksum_drift_fails_closed(
    migration_db, tmp_path: Path
):
    migration = _migration(
        tmp_path,
        "001_initial.sql",
        "CREATE TABLE exactly_once (id INTEGER);",
    )
    first = apply_migrations(migration_db, [migration])
    second = apply_migrations(migration_db, [migration])

    assert first.applied == ("001_initial.sql",)
    assert second.applied == ()
    assert second.already_applied == ("001_initial.sql",)

    migration.write_text(
        "CREATE TABLE exactly_once (id INTEGER, changed_after_apply BOOLEAN);"
    )
    with pytest.raises(MigrationError, match="checksum mismatch"):
        apply_migrations(migration_db, [migration])
