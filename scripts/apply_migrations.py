#!/usr/bin/env python3
"""Apply ordered SQL migrations with a durable checksum ledger.

Fresh databases need no options. The long-lived pre-ledger database may be
adopted once with ``--bootstrap-existing-through 59``: the command first checks
the migration-059 sentinel, records the historical files as a baseline, then
executes migration 060 onward. No other implicit baseline is accepted.

Run:
    uv run python scripts/apply_migrations.py
    uv run python scripts/apply_migrations.py --bootstrap-existing-through 59
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import psycopg2
from psycopg2.extensions import connection as Connection


_MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
_FILENAME = re.compile(r"^(?P<version>\d{3})_.+\.sql$")
_LEDGER = "alembic_schema_migrations"
_ADVISORY_LOCK_KEY = 532_060
_LEGACY_BASELINE = 59
_LEGACY_SENTINEL = "ensemble_cycle_health"


class MigrationError(RuntimeError):
    """Migration state cannot be advanced without losing provenance."""


@dataclass(frozen=True)
class Migration:
    version: int
    filename: str
    path: Path
    checksum: str


@dataclass(frozen=True)
class MigrationResult:
    applied: tuple[str, ...]
    baselined: tuple[str, ...]
    already_applied: tuple[str, ...]


def _discover(paths: Iterable[Path]) -> tuple[Migration, ...]:
    migrations: list[Migration] = []
    versions: dict[int, str] = {}
    for raw_path in paths:
        path = Path(raw_path)
        match = _FILENAME.fullmatch(path.name)
        if match is None:
            raise MigrationError(f"invalid migration filename: {path.name}")
        version = int(match.group("version"))
        if version in versions:
            raise MigrationError(
                f"duplicate migration version {version:03d}: "
                f"{versions[version]} and {path.name}"
            )
        versions[version] = path.name
        migrations.append(
            Migration(
                version=version,
                filename=path.name,
                path=path,
                checksum=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        )
    return tuple(sorted(migrations, key=lambda item: (item.version, item.filename)))


def _ensure_ledger(conn: Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {_LEDGER} (
                filename        TEXT PRIMARY KEY,
                version         INTEGER NOT NULL UNIQUE,
                checksum_sha256 TEXT NOT NULL,
                execution_kind  TEXT NOT NULL
                    CHECK (execution_kind IN ('applied', 'baseline')),
                applied_at      TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    conn.commit()


def _load_ledger(conn: Connection) -> dict[str, tuple[int, str, str]]:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT filename, version, checksum_sha256, execution_kind
            FROM {_LEDGER}
            ORDER BY version
            """
        )
        return {
            filename: (version, checksum, execution_kind)
            for filename, version, checksum, execution_kind in cur.fetchall()
        }


def _database_has_user_objects(conn: Connection) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = ANY (current_schemas(false))
                  AND table_schema NOT IN ('pg_catalog', 'information_schema')
                  AND table_name <> %s
            )
            """,
            (_LEDGER,),
        )
        return bool(cur.fetchone()[0])


def _bootstrap_existing(
    conn: Connection,
    migrations: Sequence[Migration],
    through: int,
) -> tuple[str, ...]:
    if through != _LEGACY_BASELINE:
        raise MigrationError(
            "the only reviewed legacy baseline is 059; "
            f"refusing requested baseline {through:03d}"
        )
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (_LEGACY_SENTINEL,))
        if cur.fetchone()[0] is None:
            raise MigrationError(
                "cannot baseline through 059: required sentinel "
                f"{_LEGACY_SENTINEL!r} is absent"
            )

        historical = tuple(item for item in migrations if item.version <= through)
        if not historical or historical[-1].version != through:
            raise MigrationError(
                f"migration file {through:03d}_*.sql is absent from the source tree"
            )
        for item in historical:
            cur.execute(
                f"""
                INSERT INTO {_LEDGER} (
                    filename, version, checksum_sha256, execution_kind
                ) VALUES (%s, %s, %s, 'baseline')
                """,
                (item.filename, item.version, item.checksum),
            )
    conn.commit()
    return tuple(item.filename for item in historical)


def _validate_recorded(
    migrations: Sequence[Migration],
    recorded: dict[str, tuple[int, str, str]],
) -> tuple[str, ...]:
    source_by_name = {item.filename: item for item in migrations}
    missing_from_source = sorted(set(recorded) - set(source_by_name))
    if missing_from_source:
        raise MigrationError(
            "recorded migrations are missing from source: "
            + ", ".join(missing_from_source)
        )

    already: list[str] = []
    for filename, (version, checksum, _kind) in recorded.items():
        migration = source_by_name[filename]
        if migration.version != version:
            raise MigrationError(f"version mismatch for recorded migration {filename}")
        if migration.checksum != checksum:
            raise MigrationError(f"checksum mismatch for applied migration {filename}")
        already.append(filename)
    return tuple(sorted(already, key=lambda name: source_by_name[name].version))


def apply_migrations(
    conn: Connection,
    paths: Iterable[Path],
    *,
    bootstrap_existing_through: int | None = None,
) -> MigrationResult:
    """Apply missing migrations and return an auditable summary.

    Each migration and its ledger row commit atomically. The session advisory
    lock serialises deploys; after a failure, a later run resumes from the last
    committed file without re-executing it.
    """
    migrations = _discover(paths)
    if not migrations:
        return MigrationResult(applied=(), baselined=(), already_applied=())
    if (
        bootstrap_existing_through is not None
        and bootstrap_existing_through != _LEGACY_BASELINE
    ):
        raise MigrationError(
            "the only reviewed legacy baseline is 059; "
            f"refusing requested baseline {bootstrap_existing_through:03d}"
        )

    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_lock(%s)", (_ADVISORY_LOCK_KEY,))
    conn.commit()
    try:
        _ensure_ledger(conn)
        recorded = _load_ledger(conn)
        baselined: tuple[str, ...] = ()
        if not recorded:
            has_user_objects = _database_has_user_objects(conn)
            if has_user_objects:
                if bootstrap_existing_through is None:
                    raise MigrationError(
                        "refusing to apply from 001 to a non-empty database without "
                        "an explicit reviewed baseline"
                    )
                baselined = _bootstrap_existing(
                    conn, migrations, bootstrap_existing_through
                )
                recorded = _load_ledger(conn)

        already = _validate_recorded(migrations, recorded)
        applied: list[str] = []
        for item in migrations:
            if item.filename in recorded:
                continue
            try:
                with conn.cursor() as cur:
                    cur.execute(item.path.read_text())
                    cur.execute(
                        f"""
                        INSERT INTO {_LEDGER} (
                            filename, version, checksum_sha256, execution_kind
                        ) VALUES (%s, %s, %s, 'applied')
                        """,
                        (item.filename, item.version, item.checksum),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            applied.append(item.filename)
        return MigrationResult(
            applied=tuple(applied),
            baselined=baselined,
            already_applied=already,
        )
    finally:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_unlock(%s)", (_ADVISORY_LOCK_KEY,))
        conn.commit()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bootstrap-existing-through",
        type=int,
        default=None,
        metavar="VERSION",
        help="one-time guarded adoption of the reviewed legacy schema",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    database_url = os.environ.get(
        "DATABASE_URL", "postgresql://trading:trading@localhost:5432/trading"
    )
    paths = sorted(_MIGRATIONS_DIR.glob("*.sql"))
    if not paths:
        print("No migration files found.")
        return 0

    conn = psycopg2.connect(database_url)
    try:
        result = apply_migrations(
            conn,
            paths,
            bootstrap_existing_through=args.bootstrap_existing_through,
        )
    finally:
        conn.close()

    for filename in result.baselined:
        print(f"Baselined {filename}")
    for filename in result.applied:
        print(f"Applied {filename}")
    print(
        "Migration state: "
        f"{len(result.applied)} applied, "
        f"{len(result.baselined)} baselined, "
        f"{len(result.already_applied)} already recorded."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
