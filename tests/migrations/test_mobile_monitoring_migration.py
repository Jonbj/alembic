"""Integration test for the mobile monitoring migration (041).

The test executes the migration inside a rolled-back transaction against the
configured DATABASE_URL and verifies tables, indexes, and the active-incident
and delivery unique constraints.
"""

from __future__ import annotations

import os
import urllib.parse
from pathlib import Path

import psycopg2
import pytest

MIGRATION_PATH = (
    Path(__file__).parent.parent.parent / "migrations" / "041_mobile_monitoring.sql"
)
ACCESS_JTI_MIGRATION_PATH = (
    Path(__file__).parent.parent.parent
    / "migrations"
    / "042_mobile_session_access_jti.sql"
)
FCM_DELIVERY_MIGRATION_PATH = (
    Path(__file__).parent.parent.parent
    / "migrations"
    / "043_mobile_fcm_delivery.sql"
)

MOBILE_TABLES = [
    "monitor_users",
    "monitor_devices",
    "monitor_sessions",
    "portfolio_monitor_snapshots",
    "mobile_events",
    "mobile_event_history",
    "mobile_notification_deliveries",
]


@pytest.fixture(scope="module")
def db_connection():
    """Connect to the test database, creating it if necessary."""

    def _connect(url: str):
        return psycopg2.connect(url)

    def _try_urls(urls: list[str]):
        last_exc = None
        for url in urls:
            try:
                return _connect(url)
            except psycopg2.OperationalError as exc:
                last_exc = exc
        raise last_exc

    # Prefer the configured DATABASE_URL, then the standard local docker-compose
    # credentials, then a password-less localhost fallback.
    configured = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/test_db")
    candidates = [
        configured,
        "postgresql://trading:trading@localhost:5432/trading",
        "postgresql://trading:trading@localhost:5432/test_db",
    ]
    # De-duplicate while preserving order.
    seen = set()
    unique_candidates: list[str] = []
    for url in candidates:
        if url not in seen:
            seen.add(url)
            unique_candidates.append(url)

    try:
        conn = _try_urls(unique_candidates)
    except psycopg2.OperationalError as exc:
        if "does not exist" in str(exc).lower():
            parsed = urllib.parse.urlparse(unique_candidates[0])
            maintenance_url = urllib.parse.urlunparse(parsed._replace(path="/postgres"))
            maintenance = psycopg2.connect(maintenance_url)
            maintenance.autocommit = True
            with maintenance.cursor() as cur:
                db_name = parsed.path.lstrip("/")
                cur.execute(f"CREATE DATABASE {db_name}")
            maintenance.close()
            conn = _try_urls(unique_candidates)
        else:
            raise
    yield conn
    conn.close()


class TestMobileMonitoringMigration:
    """041 applies cleanly and enforces its integrity rules."""

    def test_042_upgrades_database_that_already_applied_041(self, db_connection):
        """The access-token binding is delivered by a forward-only migration."""
        conn = db_connection
        conn.autocommit = False
        cur = conn.cursor()
        try:
            for table in reversed(MOBILE_TABLES):
                cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
            cur.execute(MIGRATION_PATH.read_text())

            cur.execute(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema='public'
                  AND table_name='monitor_sessions'
                  AND column_name='access_jti'
                """
            )
            assert cur.fetchone() is None

            cur.execute(ACCESS_JTI_MIGRATION_PATH.read_text())

            cur.execute(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema='public'
                  AND table_name='monitor_sessions'
                  AND column_name='access_jti'
                """
            )
            assert cur.fetchone() is not None
            cur.execute(
                """
                SELECT indexdef FROM pg_indexes
                WHERE schemaname='public'
                  AND indexname='idx_monitor_sessions_access_jti'
                """
            )
            index = cur.fetchone()
            assert index is not None
            assert "UNIQUE INDEX" in index[0]
        finally:
            cur.close()
            conn.rollback()

    def test_043_adds_recovery_counter_and_outbox_lease(
        self, db_connection
    ):
        conn = db_connection
        conn.autocommit = False
        cur = conn.cursor()
        try:
            for table in reversed(MOBILE_TABLES):
                cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
            cur.execute(MIGRATION_PATH.read_text())
            cur.execute(ACCESS_JTI_MIGRATION_PATH.read_text())
            cur.execute(FCM_DELIVERY_MIGRATION_PATH.read_text())

            expected = {
                ("mobile_events", "clear_observation_count"),
                ("mobile_notification_deliveries", "claimed_at"),
                ("mobile_notification_deliveries", "claim_id"),
            }
            cur.execute(
                """
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema='public'
                  AND (table_name, column_name) IN (
                      ('mobile_events', 'clear_observation_count'),
                      ('mobile_notification_deliveries', 'claimed_at'),
                      ('mobile_notification_deliveries', 'claim_id')
                  )
                """
            )
            assert set(cur.fetchall()) == expected
        finally:
            cur.close()
            conn.rollback()

    def test_migration_applies_and_tables_exist(self, db_connection):
        migration_sql = MIGRATION_PATH.read_text()
        conn = db_connection
        conn.autocommit = False
        cur = conn.cursor()
        try:
            # Start with a clean slate within the transaction.
            for table in reversed(MOBILE_TABLES):
                cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

            cur.execute(migration_sql)

            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = ANY(%s)
                """,
                (MOBILE_TABLES,),
            )
            found = {row[0] for row in cur.fetchall()}
            assert found == set(MOBILE_TABLES)

            # Verify the active-incident partial unique index exists.
            cur.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND indexname = 'idx_mobile_events_active_fingerprint'
                """
            )
            assert cur.fetchone() is not None
        finally:
            cur.close()
            conn.rollback()

    def test_active_incident_fingerprint_unique(self, db_connection):
        migration_sql = MIGRATION_PATH.read_text()
        conn = db_connection
        conn.autocommit = False
        cur = conn.cursor()
        try:
            for table in reversed(MOBILE_TABLES):
                cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
            cur.execute(migration_sql)

            cur.execute(
                """
                INSERT INTO monitor_users (id, username, password_hash, enabled)
                VALUES (gen_random_uuid(), 'monitor-test', '$2b$12$testhash', TRUE)
                RETURNING id
                """
            )
            cur.fetchone()[0]

            fingerprint = "pipeline:portfolio_cycle_late"
            cur.execute(
                """
                INSERT INTO mobile_events (
                    fingerprint, kind, category, severity, status,
                    occurred_at, first_observed_at, last_observed_at, title
                ) VALUES (%s, 'alert_incident', 'system', 'warning', 'open',
                          now(), now(), now(), 'first')
                RETURNING id
                """,
                (fingerprint,),
            )
            cur.fetchone()[0]

            with pytest.raises(psycopg2.IntegrityError):
                cur.execute(
                    """
                    INSERT INTO mobile_events (
                        fingerprint, kind, category, severity, status,
                        occurred_at, first_observed_at, last_observed_at, title
                    ) VALUES (%s, 'alert_incident', 'system', 'warning', 'open',
                              now(), now(), now(), 'duplicate')
                    """,
                    (fingerprint,),
                )
            conn.rollback()
            cur = conn.cursor()
            for table in reversed(MOBILE_TABLES):
                cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
            cur.execute(migration_sql)

            # A second active event with a different fingerprint is allowed.
            cur.execute(
                """
                INSERT INTO mobile_events (
                    fingerprint, kind, category, severity, status,
                    occurred_at, first_observed_at, last_observed_at, title
                ) VALUES (%s, 'alert_incident', 'system', 'warning', 'open',
                          now(), now(), now(), 'other')
                """,
                ("risk:drawdown:paper",),
            )
            assert cur.rowcount == 1
        finally:
            cur.close()
            conn.rollback()

    def test_delivery_unique_per_event_device_transition(self, db_connection):
        migration_sql = MIGRATION_PATH.read_text()
        conn = db_connection
        conn.autocommit = False
        cur = conn.cursor()
        try:
            for table in reversed(MOBILE_TABLES):
                cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
            cur.execute(migration_sql)

            cur.execute(
                """
                INSERT INTO monitor_users (id, username, password_hash, enabled)
                VALUES (gen_random_uuid(), 'monitor-test', '$2b$12$testhash', TRUE)
                RETURNING id
                """
            )
            user_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO monitor_devices (id, user_id, installation_id, push_enabled)
                VALUES (gen_random_uuid(), %s, 'inst-1', TRUE)
                RETURNING id
                """,
                (user_id,),
            )
            device_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO mobile_events (
                    fingerprint, kind, category, severity, status,
                    occurred_at, first_observed_at, last_observed_at, title
                ) VALUES ('pipeline:portfolio_cycle_late', 'alert_incident', 'system',
                          'warning', 'open', now(), now(), now(), 'first')
                RETURNING id
                """
            )
            event_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO mobile_notification_deliveries
                    (event_id, device_id, transition)
                VALUES (%s, %s, 'opened')
                """,
                (event_id, device_id),
            )

            with pytest.raises(psycopg2.IntegrityError):
                cur.execute(
                    """
                    INSERT INTO mobile_notification_deliveries
                        (event_id, device_id, transition)
                    VALUES (%s, %s, 'opened')
                    """,
                    (event_id, device_id),
                )
        finally:
            cur.close()
            conn.rollback()

    def test_nullable_financial_columns(self, db_connection):
        """Financial snapshot columns accept NULL and never default to zero."""
        migration_sql = MIGRATION_PATH.read_text()
        conn = db_connection
        conn.autocommit = False
        cur = conn.cursor()
        try:
            for table in reversed(MOBILE_TABLES):
                cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
            cur.execute(migration_sql)

            cur.execute(
                """
                INSERT INTO portfolio_monitor_snapshots
                    (snapshot_id, as_of, broker_environment, mode,
                     nav, cash, gross_exposure, open_positions, source)
                VALUES (gen_random_uuid(), now(), 'paper', 'paper',
                        NULL, NULL, NULL, NULL, 'alpaca_paper')
                RETURNING nav, cash, gross_exposure, open_positions
                """
            )
            nav, cash, gross_exposure, open_positions = cur.fetchone()
            assert nav is None
            assert cash is None
            assert gross_exposure is None
            assert open_positions is None
        finally:
            cur.close()
            conn.rollback()
