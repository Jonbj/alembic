"""Tests for the mobile incident engine and outbox persistence."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest

_MIGRATION_PATHS = (
    Path(__file__).parent.parent.parent / "migrations" / "041_mobile_monitoring.sql",
    Path(__file__).parent.parent.parent
    / "migrations"
    / "042_mobile_session_access_jti.sql",
    Path(__file__).parent.parent.parent
    / "migrations"
    / "043_mobile_fcm_delivery.sql",
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
        firebase_installation_id="test-firebase-installation-id",
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

    async def test_recovery_can_require_two_clear_observations(
        self, store, user_device
    ):
        from src.mobile_monitoring.models import EventCategory, EventKind, Severity

        common = {
            "fingerprint": "risk:exposure:paper",
            "kind": EventKind.ALERT_INCIDENT,
            "category": EventCategory.CRITICAL,
            "title": "Limite esposizione",
        }
        await store.record_observation(
            **common,
            severity=Severity.CRITICAL,
            expected=True,
        )
        first = await store.record_observation(
            **common,
            severity=Severity.INFO,
            expected=False,
            recovery_observations_required=2,
        )
        second = await store.record_observation(
            **common,
            severity=Severity.INFO,
            expected=False,
            recovery_observations_required=2,
        )

        assert first.transition == "observe"
        assert second.transition == "recover"
        async with store.pool.acquire() as conn:
            deliveries = await conn.fetch(
                """
                SELECT transition
                FROM mobile_notification_deliveries
                ORDER BY created_at
                """
            )
        assert [row["transition"] for row in deliveries] == ["open", "recover"]

    async def test_fault_observation_resets_recovery_confirmation(
        self, store, user_device
    ):
        from src.mobile_monitoring.models import EventCategory, EventKind, Severity

        common = {
            "fingerprint": "system:redis",
            "kind": EventKind.ALERT_INCIDENT,
            "category": EventCategory.SYSTEM,
            "title": "Redis unavailable",
        }
        await store.record_observation(
            **common, severity=Severity.CRITICAL, expected=True
        )
        await store.record_observation(
            **common,
            severity=Severity.INFO,
            expected=False,
            recovery_observations_required=2,
        )
        await store.record_observation(
            **common, severity=Severity.CRITICAL, expected=True
        )
        result = await store.record_observation(
            **common,
            severity=Severity.INFO,
            expected=False,
            recovery_observations_required=2,
        )

        assert result.transition == "observe"

    async def test_recurrence_after_recovery_is_a_new_notifiable_incident(
        self, store, user_device
    ):
        from src.mobile_monitoring.models import EventCategory, EventKind, Severity

        common = {
            "fingerprint": "system:killswitch",
            "kind": EventKind.ALERT_INCIDENT,
            "category": EventCategory.CRITICAL,
            "title": "Killswitch attivo",
        }
        first = await store.record_observation(
            **common, severity=Severity.CRITICAL, expected=True
        )
        await store.record_observation(
            **common, severity=Severity.INFO, expected=False
        )
        recurrence = await store.record_observation(
            **common, severity=Severity.CRITICAL, expected=True
        )

        assert recurrence.transition == "open"
        assert recurrence.event_id != first.event_id
        async with store.pool.acquire() as conn:
            transitions = await conn.fetch(
                """
                SELECT transition
                FROM mobile_notification_deliveries
                ORDER BY created_at, id
                """
            )
        assert [row["transition"] for row in transitions] == [
            "open",
            "recover",
            "open",
        ]

    async def test_concurrent_recurrence_serializes_per_fingerprint(
        self, store, user_device
    ):
        from src.mobile_monitoring.models import EventCategory, EventKind, Severity

        common = {
            "fingerprint": "system:killswitch",
            "kind": EventKind.ALERT_INCIDENT,
            "category": EventCategory.CRITICAL,
            "title": "Killswitch attivo",
        }
        await store.record_observation(
            **common, severity=Severity.CRITICAL, expected=True
        )
        await store.record_observation(
            **common, severity=Severity.INFO, expected=False
        )

        results = await asyncio.gather(
            store.record_observation(
                **common, severity=Severity.CRITICAL, expected=True
            ),
            store.record_observation(
                **common, severity=Severity.CRITICAL, expected=True
            ),
        )

        assert {result.transition for result in results} == {"open", "observe"}
        async with store.pool.acquire() as conn:
            active_count = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM mobile_events
                WHERE fingerprint='system:killswitch'
                  AND status IN ('open', 'escalated')
                """
            )
        assert active_count == 1

    async def test_terminal_order_event_is_closed_historical(
        self, store, user_device
    ):
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
            deliveries = await conn.fetch(
                """
                SELECT transition
                FROM mobile_notification_deliveries
                WHERE event_id=$1
                """,
                event["id"],
            )
            assert [delivery["transition"] for delivery in deliveries] == ["terminal"]


class TestNotificationOutbox:
    async def test_due_delivery_contains_real_token_and_is_claimed(
        self, store, user_device
    ):
        from src.mobile_monitoring.models import EventCategory, EventKind, Severity

        await store.record_observation(
            fingerprint="system:killswitch",
            kind=EventKind.ALERT_INCIDENT,
            category=EventCategory.CRITICAL,
            severity=Severity.CRITICAL,
            title="Killswitch attivo",
            expected=True,
        )

        rows = await store.list_due_deliveries()
        assert len(rows) == 1
        assert (
            rows[0]["firebase_installation_id"]
            == "test-firebase-installation-id"
        )
        assert rows[0]["claimed_at"] is not None
        assert await store.list_due_deliveries() == []

    async def test_transient_failure_remains_due_after_backoff(
        self, store, user_device
    ):
        from datetime import datetime, timedelta, timezone

        from src.mobile_monitoring.models import EventCategory, EventKind, Severity

        now = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)
        await store.record_observation(
            fingerprint="system:killswitch",
            kind=EventKind.ALERT_INCIDENT,
            category=EventCategory.CRITICAL,
            severity=Severity.CRITICAL,
            title="Killswitch attivo",
            expected=True,
            occurred_at=now,
        )
        [row] = await store.list_due_deliveries(now=now)
        await store.record_delivery_attempt(
            row["id"],
            row["claim_id"],
            error_code="provider_unavailable",
            next_attempt_at=now + timedelta(minutes=2),
        )

        assert await store.list_due_deliveries(now=now + timedelta(minutes=1)) == []
        retry = await store.list_due_deliveries(now=now + timedelta(minutes=2))
        assert len(retry) == 1
        assert retry[0]["attempt_count"] == 1

    async def test_terminal_failure_is_not_retried_and_disables_destination(
        self, store, user_device
    ):
        from datetime import datetime, timezone

        from src.mobile_monitoring.models import EventCategory, EventKind, Severity

        await store.record_observation(
            fingerprint="system:killswitch",
            kind=EventKind.ALERT_INCIDENT,
            category=EventCategory.CRITICAL,
            severity=Severity.CRITICAL,
            title="Killswitch attivo",
            expected=True,
        )
        [row] = await store.list_due_deliveries()
        await store.record_delivery_attempt(
            row["id"],
            row["claim_id"],
            failed_at=datetime.now(timezone.utc),
            error_code="unregistered",
        )
        await store.disable_device_push(
            row["device_id"],
            row["firebase_installation_id"],
        )

        assert await store.list_due_deliveries() == []
        async with store.pool.acquire() as conn:
            device = await conn.fetchrow(
                """
                SELECT push_enabled, firebase_installation_id
                FROM monitor_devices
                """
            )
        assert device["push_enabled"] is False
        assert device["firebase_installation_id"] is None

    async def test_expired_claim_is_fenced_after_reclaim(
        self, store, user_device
    ):
        from datetime import datetime, timedelta, timezone

        from src.mobile_monitoring.models import EventCategory, EventKind, Severity

        now = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)
        await store.record_observation(
            fingerprint="system:killswitch",
            kind=EventKind.ALERT_INCIDENT,
            category=EventCategory.CRITICAL,
            severity=Severity.CRITICAL,
            title="Killswitch attivo",
            expected=True,
            occurred_at=now,
        )
        [first] = await store.list_due_deliveries(now=now)
        [reclaimed] = await store.list_due_deliveries(
            now=now + timedelta(minutes=6)
        )
        assert reclaimed["claim_id"] != first["claim_id"]

        stale_recorded = await store.record_delivery_attempt(
            first["id"],
            first["claim_id"],
            provider_message_id="stale-provider-id",
            accepted_at=now + timedelta(minutes=6),
        )
        current_recorded = await store.record_delivery_attempt(
            reclaimed["id"],
            reclaimed["claim_id"],
            provider_message_id="current-provider-id",
            accepted_at=now + timedelta(minutes=6),
        )

        assert stale_recorded is False
        assert current_recorded is True
        async with store.pool.acquire() as conn:
            delivery = await conn.fetchrow(
                """
                SELECT attempt_count, provider_message_id
                FROM mobile_notification_deliveries
                WHERE id=$1
                """,
                first["id"],
            )
        assert delivery["attempt_count"] == 1
        assert delivery["provider_message_id"] == "current-provider-id"

    async def test_terminal_result_for_old_fid_does_not_disable_rotated_fid(
        self, store, user_device
    ):
        from datetime import datetime, timezone

        from src.mobile_monitoring.models import EventCategory, EventKind, Severity
        from src.mobile_monitoring.store import MonitorStore

        await store.record_observation(
            fingerprint="system:killswitch",
            kind=EventKind.ALERT_INCIDENT,
            category=EventCategory.CRITICAL,
            severity=Severity.CRITICAL,
            title="Killswitch attivo",
            expected=True,
        )
        [row] = await store.list_due_deliveries()
        await MonitorStore(store.pool).update_device(
            row["device_id"],
            firebase_installation_id="rotated-firebase-installation-id",
        )
        recorded = await store.record_delivery_attempt(
            row["id"],
            row["claim_id"],
            failed_at=datetime.now(timezone.utc),
            error_code="unregistered",
        )
        assert recorded is True
        await store.disable_device_push(
            row["device_id"],
            row["firebase_installation_id"],
        )

        async with store.pool.acquire() as conn:
            device = await conn.fetchrow(
                """
                SELECT push_enabled, firebase_installation_id
                FROM monitor_devices
                WHERE id=$1
                """,
                row["device_id"],
            )
        assert device["push_enabled"] is True
        assert (
            device["firebase_installation_id"]
            == "rotated-firebase-installation-id"
        )


class TestSyntheticAlertDelivery:
    @pytest.mark.parametrize(
        ("snapshot_overrides", "fingerprint"),
        [
            (
                {"state": "blocked", "reason": "killswitch_active"},
                "system:killswitch",
            ),
            (
                {"cycle_status": "aging"},
                "pipeline:portfolio_cycle_late",
            ),
            (
                {"drawdown": 0.10},
                "risk:drawdown:paper",
            ),
            (
                {"exposure": 1.0},
                "risk:exposure:paper",
            ),
        ],
    )
    async def test_rule_opens_once_and_fake_fcm_accepts_once(
        self,
        store,
        user_device,
        monkeypatch,
        snapshot_overrides,
        fingerprint,
    ):
        from src.mobile_monitoring.builder import MobileSnapshotBuilder
        from src.notifications.fcm import FakeFcmAdapter
        from src.workers.mobile_alert_task import (
            MobileAlertEvaluator,
            dispatch_due_notifications,
        )

        now = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)

        def component(status):
            return SimpleNamespace(status=status, age_seconds=60)

        snapshot = SimpleNamespace(
            as_of=now,
            operational=SimpleNamespace(
                state=snapshot_overrides.get("state", "operational"),
                primary_reason=snapshot_overrides.get("reason"),
                mode="paper",
                pipeline_expected=True,
            ),
            pipeline={
                "broker": component("fresh"),
                "portfolio_cycle": component(
                    snapshot_overrides.get("cycle_status", "fresh")
                ),
                "signal": component("fresh"),
            },
            portfolio=SimpleNamespace(
                current_drawdown=snapshot_overrides.get("drawdown", 0.01),
                drawdown_limit=0.10,
                gross_exposure=snapshot_overrides.get("exposure", 0.20),
                gross_exposure_limit=1.0,
            ),
            degradations=[],
        )
        builder = MagicMock(spec=MobileSnapshotBuilder)
        builder.build_snapshot = AsyncMock(return_value=snapshot)
        evaluator = MobileAlertEvaluator(store=store, builder=builder)

        await evaluator.evaluate()
        await evaluator.evaluate()
        monkeypatch.setattr(
            "src.workers.mobile_alert_task.get_fcm_adapter",
            MagicMock(return_value=FakeFcmAdapter()),
        )
        await dispatch_due_notifications(store.pool, now=now)

        async with store.pool.acquire() as conn:
            events = await conn.fetch(
                """
                SELECT id
                FROM mobile_events
                WHERE fingerprint=$1
                """,
                fingerprint,
            )
            history_count = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM mobile_event_history
                WHERE event_id=$1
                """,
                events[0]["id"],
            )
            deliveries = await conn.fetch(
                """
                SELECT attempt_count, sent_at
                FROM mobile_notification_deliveries
                WHERE event_id=$1
                """,
                events[0]["id"],
            )

        assert len(events) == 1
        assert history_count == 1
        assert len(deliveries) == 1
        assert deliveries[0]["attempt_count"] == 1
        assert deliveries[0]["sent_at"] == now
