"""Tests for the mobile incident engine and outbox persistence."""

from __future__ import annotations

import os
from pathlib import Path

import asyncpg
import pytest

_MIGRATION_PATHS = (
    Path(__file__).parent.parent.parent / "migrations" / "041_mobile_monitoring.sql",
    Path(__file__).parent.parent.parent
    / "migrations"
    / "042_mobile_session_access_jti.sql",
)


def _dsn() -> str:
    from src.config import config

    return os.environ.get("DATABASE_URL") or str(config.DATABASE_URL)


@pytest.fixture
async def pool():
    dsn = _dsn()
    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
    async with pool.acquire() as conn:
        for migration_path in _MIGRATION_PATHS:
            await conn.execute(migration_path.read_text())
    yield pool
    await pool.close()


@pytest.fixture
async def store(pool):
    from src.mobile_monitoring.incidents import IncidentStore

    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE mobile_notification_deliveries CASCADE")
        await conn.execute("TRUNCATE TABLE mobile_event_history CASCADE")
        await conn.execute("TRUNCATE TABLE mobile_events CASCADE")
        await conn.execute("TRUNCATE TABLE monitor_sessions CASCADE")
        await conn.execute("TRUNCATE TABLE monitor_devices CASCADE")
        await conn.execute("TRUNCATE TABLE monitor_users CASCADE")
    yield IncidentStore(pool)
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE mobile_notification_deliveries CASCADE")
        await conn.execute("TRUNCATE TABLE mobile_event_history CASCADE")
        await conn.execute("TRUNCATE TABLE mobile_events CASCADE")
        await conn.execute("TRUNCATE TABLE monitor_sessions CASCADE")
        await conn.execute("TRUNCATE TABLE monitor_devices CASCADE")
        await conn.execute("TRUNCATE TABLE monitor_users CASCADE")


@pytest.fixture
async def user_device(pool):
    from src.mobile_monitoring.store import MonitorStore

    s = MonitorStore(pool)
    import bcrypt

    user = await s.create_user(
        username="monitor",
        password_hash=bcrypt.hashpw("x".encode(), bcrypt.gensalt()).decode(),
    )
    device = await s.create_device(
        user_id=user.id,
        installation_id="inst-1",
        name="Pixel 9",
        app_version="1.0.0",
        push_enabled=True,
    )
    return user, device


class TestIncidentLifecycle:
    async def test_open_incident_creates_event_history_and_outbox(
        self, store, user_device
    ):
        from src.mobile_monitoring.models import EventCategory, EventKind, Severity

        result = await store.record_observation(
            fingerprint="system:killswitch",
            kind=EventKind.ALERT_INCIDENT,
            category=EventCategory.CRITICAL,
            severity=Severity.CRITICAL,
            title="Killswitch attivo",
            summary="Halt",
            expected=True,
        )
        assert result.transition == "open"
        async with store.pool.acquire() as conn:
            event = await conn.fetchrow(
                "SELECT * FROM mobile_events WHERE fingerprint=$1", "system:killswitch"
            )
            assert event["status"] == "open"
            assert event["severity"] == "critical"
            history = await conn.fetch(
                "SELECT * FROM mobile_event_history WHERE event_id=$1", event["id"]
            )
            assert len(history) == 1
            deliveries = await conn.fetch(
                "SELECT * FROM mobile_notification_deliveries WHERE event_id=$1",
                event["id"],
            )
            assert len(deliveries) == 1
            assert deliveries[0]["transition"] == "open"

    async def test_repeated_observation_updates_last_seen_without_duplicate_open(
        self, store
    ):
        from src.mobile_monitoring.models import EventCategory, EventKind, Severity

        await store.record_observation(
            fingerprint="system:killswitch",
            kind=EventKind.ALERT_INCIDENT,
            category=EventCategory.CRITICAL,
            severity=Severity.CRITICAL,
            title="Killswitch attivo",
            summary="Halt",
            expected=True,
        )
        result2 = await store.record_observation(
            fingerprint="system:killswitch",
            kind=EventKind.ALERT_INCIDENT,
            category=EventCategory.CRITICAL,
            severity=Severity.CRITICAL,
            title="Killswitch attivo",
            summary="Halt",
            expected=True,
        )
        assert result2.transition == "observe"
        async with store.pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM mobile_events WHERE fingerprint=$1",
                "system:killswitch",
            )
            assert count == 1

    async def test_escalate_increases_severity(self, store):
        from src.mobile_monitoring.models import EventCategory, EventKind, Severity

        await store.record_observation(
            fingerprint="pipeline:broker_stale",
            kind=EventKind.ALERT_INCIDENT,
            category=EventCategory.TRADING,
            severity=Severity.WARNING,
            title="Broker aging",
            summary="Aging",
            expected=True,
        )
        result = await store.record_observation(
            fingerprint="pipeline:broker_stale",
            kind=EventKind.ALERT_INCIDENT,
            category=EventCategory.TRADING,
            severity=Severity.CRITICAL,
            title="Broker stale",
            summary="Stale",
            expected=True,
        )
        assert result.transition == "escalate"
        async with store.pool.acquire() as conn:
            event = await conn.fetchrow(
                "SELECT * FROM mobile_events WHERE fingerprint=$1",
                "pipeline:broker_stale",
            )
            assert event["status"] == "escalated"
            assert event["severity"] == "critical"

    async def test_recovery_creates_recover_delivery(self, store, user_device):
        from src.mobile_monitoring.models import EventCategory, EventKind, Severity

        await store.record_observation(
            fingerprint="pipeline:broker_stale",
            kind=EventKind.ALERT_INCIDENT,
            category=EventCategory.TRADING,
            severity=Severity.WARNING,
            title="Broker stale",
            summary="Stale",
            expected=True,
        )
        result = await store.record_observation(
            fingerprint="pipeline:broker_stale",
            kind=EventKind.ALERT_INCIDENT,
            category=EventCategory.SYSTEM,
            severity=Severity.INFO,
            title="Condizione rientrata",
            summary="Cleared",
            expected=False,
        )
        assert result.transition == "recover"
        async with store.pool.acquire() as conn:
            event = await conn.fetchrow(
                "SELECT * FROM mobile_events WHERE fingerprint=$1",
                "pipeline:broker_stale",
            )
            assert event["status"] == "recovered"
            deliveries = await conn.fetch(
                "SELECT transition FROM mobile_notification_deliveries WHERE event_id=$1 ORDER BY created_at",
                event["id"],
            )
            assert [d["transition"] for d in deliveries] == ["open", "recover"]

    async def test_terminal_order_event_is_closed_historical(self, store):
        from src.mobile_monitoring.models import EventCategory, EventKind, Severity

        result = await store.record_observation(
            fingerprint="order:123:rejected",
            kind=EventKind.ORDER,
            category=EventCategory.TRADING,
            severity=Severity.CRITICAL,
            title="Ordine rejected",
            summary="Rejected",
            entity_type="order",
            entity_id="123",
            expected=False,
        )
        assert result.transition == "closed"
        async with store.pool.acquire() as conn:
            event = await conn.fetchrow(
                "SELECT * FROM mobile_events WHERE fingerprint=$1", "order:123:rejected"
            )
            assert event["status"] == "closed"
