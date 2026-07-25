"""Server-owned alert incident engine for the mobile monitor.

The engine turns system, risk, and order observations into deduplicated,
lifecycle-managed incidents and transactional notification outbox entries.
No financial detail, ticker, or token leaks into the outbox or FCM payload.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import asyncpg

from src.mobile_monitoring.models import EventCategory, EventKind, EventStatus, Severity

logger = logging.getLogger(__name__)


_SEVERITY_RANK = {Severity.INFO.value: 0, Severity.WARNING.value: 1, Severity.CRITICAL.value: 2}


def _severity_rank_value(severity: Severity) -> int:
    return _SEVERITY_RANK.get(severity.value, 0)


@dataclass(frozen=True)
class ObservationResult:
    """Outcome of recording one observation."""

    event_id: UUID | None
    fingerprint: str
    transition: str | None  # open, escalate, recover, close, observe, terminal
    severity: str | None
    status: str | None


class IncidentStore:
    """Persistence for mobile alert incidents and the notification outbox."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def record_observation(
        self,
        *,
        fingerprint: str,
        kind: EventKind,
        category: EventCategory,
        severity: Severity,
        title: str,
        summary: str | None = None,
        details: dict[str, Any] | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        occurred_at: datetime | None = None,
        expected: bool = False,
        recovery_observations_required: int = 1,
    ) -> ObservationResult:
        """Record an observation and transition the matching incident lifecycle.

        A single observation may `open`, `escalate`, `recover`, `close`, or merely
        update `last_observed_at` of an existing active incident. Terminal
        observations (expected=False, severity=INFO or order terminal events) are
        inserted directly as `closed` historical records.
        """
        occurred_at = occurred_at or datetime.now(timezone.utc)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtext($1))",
                    fingerprint,
                )
                existing = await conn.fetchrow(
                    """
                    SELECT id, status, severity, clear_observation_count
                    FROM mobile_events
                    WHERE fingerprint=$1
                    ORDER BY
                        CASE WHEN status IN ('open', 'escalated') THEN 0 ELSE 1 END,
                        occurred_at DESC
                    LIMIT 1
                    FOR UPDATE
                    """,
                    fingerprint,
                )

                if existing is None:
                    if severity == Severity.INFO and expected:
                        # Nothing to do: informational observations only matter when there is an active incident.
                        return ObservationResult(None, fingerprint, None, None, None)
                    status = EventStatus.CLOSED if not expected else EventStatus.OPEN
                    event_id = await self._insert_event(
                        conn,
                        fingerprint=fingerprint,
                        kind=kind,
                        category=category,
                        severity=severity,
                        status=status,
                        title=title,
                        summary=summary,
                        details=details,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        occurred_at=occurred_at,
                    )
                    await self._insert_history(conn, event_id, status.value, severity.value, details)
                    if status == EventStatus.OPEN:
                        await self._enqueue_deliveries(conn, event_id, "open")
                    elif kind == EventKind.ORDER:
                        await self._enqueue_deliveries(conn, event_id, "terminal")
                    return ObservationResult(event_id, fingerprint, status.value, severity.value, status.value)

                event_id = existing["id"]
                old_status = EventStatus(existing["status"])
                old_severity = Severity(existing["severity"])

                # Update last_observed_at for active incidents.
                if old_status in (EventStatus.OPEN, EventStatus.ESCALATED):
                    await conn.execute(
                        """
                        UPDATE mobile_events
                        SET last_observed_at=$1,
                            clear_observation_count=CASE
                                WHEN $2 THEN 0
                                ELSE clear_observation_count
                            END
                        WHERE id=$3
                        """,
                        occurred_at,
                        expected,
                        event_id,
                    )

                if old_status == EventStatus.OPEN and _severity_rank_value(severity) > _severity_rank_value(old_severity):
                    await conn.execute(
                        """
                        UPDATE mobile_events
                        SET status=$1, severity=$2, last_observed_at=$3
                        WHERE id=$4
                        """,
                        EventStatus.ESCALATED.value,
                        severity.value,
                        occurred_at,
                        event_id,
                    )
                    await self._insert_history(conn, event_id, EventStatus.ESCALATED.value, severity.value, details)
                    await self._enqueue_deliveries(conn, event_id, "escalate")
                    return ObservationResult(event_id, fingerprint, "escalate", severity.value, EventStatus.ESCALATED.value)

                if old_status in (EventStatus.OPEN, EventStatus.ESCALATED):
                    if not expected and severity != Severity.CRITICAL:
                        required = max(1, recovery_observations_required)
                        clear_count = existing["clear_observation_count"] + 1
                        if clear_count < required:
                            await conn.execute(
                                """
                                UPDATE mobile_events
                                SET clear_observation_count=$1
                                WHERE id=$2
                                """,
                                clear_count,
                                event_id,
                            )
                            return ObservationResult(
                                event_id,
                                fingerprint,
                                "observe",
                                old_severity.value,
                                old_status.value,
                            )
                        # Recovery: the fault condition has cleared.
                        await conn.execute(
                            """
                            UPDATE mobile_events
                            SET status=$1, resolved_at=$2, last_observed_at=$3,
                                clear_observation_count=$4
                            WHERE id=$5
                            """,
                            EventStatus.RECOVERED.value,
                            occurred_at,
                            occurred_at,
                            clear_count,
                            event_id,
                        )
                        await self._insert_history(conn, event_id, EventStatus.RECOVERED.value, old_severity.value, details)
                        await self._enqueue_deliveries(conn, event_id, "recover")
                        return ObservationResult(event_id, fingerprint, "recover", old_severity.value, EventStatus.RECOVERED.value)

                    # Same or lower severity: just observe.
                    return ObservationResult(event_id, fingerprint, "observe", old_severity.value, old_status.value)

                if old_status == EventStatus.RECOVERED and expected and _severity_rank_value(severity) >= _severity_rank_value(Severity.WARNING):
                    # A recurrence is a new incident cycle. It receives its own
                    # id/outbox transitions while the prior recovery remains
                    # immutable history.
                    event_id = await self._insert_event(
                        conn,
                        fingerprint=fingerprint,
                        kind=kind,
                        category=category,
                        severity=severity,
                        status=EventStatus.OPEN,
                        title=title,
                        summary=summary,
                        details=details,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        occurred_at=occurred_at,
                    )
                    await self._insert_history(conn, event_id, EventStatus.OPEN.value, severity.value, details)
                    await self._enqueue_deliveries(conn, event_id, "open")
                    return ObservationResult(event_id, fingerprint, "open", severity.value, EventStatus.OPEN.value)

                return ObservationResult(event_id, fingerprint, "observe", old_severity.value, old_status.value)

    async def close_incident(
        self,
        *,
        fingerprint: str,
        title: str | None = None,
        summary: str | None = None,
        details: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> ObservationResult:
        """Explicitly close an active incident (e.g. operator cleared)."""
        occurred_at = occurred_at or datetime.now(timezone.utc)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                existing = await conn.fetchrow(
                    "SELECT id, severity FROM mobile_events WHERE fingerprint=$1",
                    fingerprint,
                )
                if existing is None:
                    return ObservationResult(None, fingerprint, None, None, None)
                event_id = existing["id"]
                await conn.execute(
                    """
                    UPDATE mobile_events
                    SET status=$1, resolved_at=$2, last_observed_at=$3, title=COALESCE($4, title), summary=COALESCE($5, summary)
                    WHERE id=$6
                    """,
                    EventStatus.CLOSED.value,
                    occurred_at,
                    occurred_at,
                    title,
                    summary,
                    event_id,
                )
                await self._insert_history(conn, event_id, EventStatus.CLOSED.value, existing["severity"], details)
                await self._enqueue_deliveries(conn, event_id, "close")
                return ObservationResult(event_id, fingerprint, "close", existing["severity"], EventStatus.CLOSED.value)

    async def _insert_event(
        self,
        conn: asyncpg.Connection,
        *,
        fingerprint: str,
        kind: EventKind,
        category: EventCategory,
        severity: Severity,
        status: EventStatus,
        title: str,
        summary: str | None,
        details: dict[str, Any] | None,
        entity_type: str | None,
        entity_id: str | None,
        occurred_at: datetime,
    ) -> UUID:
        row = await conn.fetchrow(
            """
            INSERT INTO mobile_events (
                fingerprint, kind, category, severity, status,
                occurred_at, first_observed_at, last_observed_at,
                title, summary, entity_type, entity_id, details
            )
            VALUES ($1, $2, $3, $4, $5, $6, $6, $6, $7, $8, $9, $10, $11)
            RETURNING id
            """,
            fingerprint,
            kind.value,
            category.value,
            severity.value,
            status.value,
            occurred_at,
            title,
            summary,
            entity_type,
            entity_id,
            json.dumps(details) if details is not None else None,
        )
        return row["id"]

    async def _insert_history(
        self,
        conn: asyncpg.Connection,
        event_id: UUID,
        state: str,
        severity: str | None,
        details: dict[str, Any] | None,
        occurred_at: datetime | None = None,
    ) -> None:
        occurred_at = occurred_at or datetime.now(timezone.utc)
        await conn.execute(
            """
            INSERT INTO mobile_event_history (event_id, state, severity, details, occurred_at)
            VALUES ($1, $2, $3, $4, $5)
            """,
            event_id,
            state,
            severity,
            json.dumps(details) if details is not None else None,
            occurred_at,
        )

    async def _enqueue_deliveries(
        self,
        conn: asyncpg.Connection,
        event_id: UUID,
        transition: str,
    ) -> None:
        """Create one notification outbox row per push-enabled device."""
        rows = await conn.fetch(
            """
            SELECT id FROM monitor_devices
            WHERE revoked_at IS NULL
              AND push_enabled = TRUE
              AND firebase_installation_id IS NOT NULL
            """
        )
        for row in rows:
            await conn.execute(
                """
                INSERT INTO mobile_notification_deliveries (event_id, device_id, transition)
                VALUES ($1, $2, $3)
                ON CONFLICT (event_id, device_id, transition) DO NOTHING
                """,
                event_id,
                row["id"],
                transition,
            )

    async def list_due_deliveries(
        self,
        limit: int = 100,
        now: datetime | None = None,
    ) -> list[asyncpg.Record]:
        now = now or datetime.now(timezone.utc)
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                WITH candidates AS (
                    SELECT d.id
                    FROM mobile_notification_deliveries d
                    JOIN monitor_devices device ON device.id = d.device_id
                    WHERE d.sent_at IS NULL
                      AND d.failed_at IS NULL
                      AND (d.next_attempt_at IS NULL OR d.next_attempt_at <= $1)
                      AND (
                          d.claimed_at IS NULL
                          OR d.claimed_at <= $1 - INTERVAL '5 minutes'
                      )
                      AND device.revoked_at IS NULL
                      AND device.push_enabled = TRUE
                      AND device.firebase_installation_id IS NOT NULL
                    ORDER BY d.attempt_count ASC, d.created_at ASC
                    FOR UPDATE OF d SKIP LOCKED
                    LIMIT $2
                ),
                claimed AS (
                    UPDATE mobile_notification_deliveries d
                    SET claimed_at=$1, claim_id=gen_random_uuid()
                    FROM candidates c
                    WHERE d.id=c.id
                    RETURNING d.*
                )
                SELECT d.id, d.event_id, d.device_id, d.transition,
                       d.attempt_count, d.claimed_at, d.claim_id,
                       e.fingerprint, e.severity, e.status,
                       d.created_at AS delivery_created_at,
                       device.firebase_installation_id
                FROM claimed d
                JOIN mobile_events e ON e.id = d.event_id
                JOIN monitor_devices device ON device.id = d.device_id
                ORDER BY d.attempt_count ASC, d.created_at ASC
                """,
                now,
                limit,
            )

    async def record_delivery_attempt(
        self,
        delivery_id: int,
        claim_id: UUID,
        *,
        provider_message_id: str | None = None,
        failed_at: datetime | None = None,
        error_code: str | None = None,
        next_attempt_at: datetime | None = None,
        accepted_at: datetime | None = None,
    ) -> bool:
        async with self.pool.acquire() as conn:
            if next_attempt_at is not None:
                updated = await conn.fetchval(
                    """
                    UPDATE mobile_notification_deliveries
                    SET attempt_count = attempt_count + 1,
                        failed_at=NULL,
                        error_code=$1,
                        next_attempt_at=$2,
                        claimed_at=NULL,
                        claim_id=NULL
                    WHERE id=$3 AND claim_id=$4 AND sent_at IS NULL
                    RETURNING TRUE
                    """,
                    error_code,
                    next_attempt_at,
                    delivery_id,
                    claim_id,
                )
            elif failed_at is not None:
                updated = await conn.fetchval(
                    """
                    UPDATE mobile_notification_deliveries
                    SET attempt_count = attempt_count + 1,
                        failed_at=$1,
                        error_code=$2,
                        next_attempt_at=NULL,
                        claimed_at=NULL,
                        claim_id=NULL
                    WHERE id=$3 AND claim_id=$4 AND sent_at IS NULL
                    RETURNING TRUE
                    """,
                    failed_at,
                    error_code,
                    delivery_id,
                    claim_id,
                )
            else:
                updated = await conn.fetchval(
                    """
                    UPDATE mobile_notification_deliveries
                    SET attempt_count = attempt_count + 1,
                        provider_message_id=$1,
                        sent_at=$2,
                        failed_at=NULL,
                        error_code=NULL,
                        next_attempt_at=NULL,
                        claimed_at=NULL,
                        claim_id=NULL
                    WHERE id=$3 AND claim_id=$4 AND sent_at IS NULL
                    RETURNING TRUE
                    """,
                    provider_message_id,
                    accepted_at or datetime.now(timezone.utc),
                    delivery_id,
                    claim_id,
                )
        return bool(updated)

    async def disable_device_push(
        self,
        device_id: UUID,
        firebase_installation_id: str,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE monitor_devices
                SET push_enabled=FALSE, firebase_installation_id=NULL
                WHERE id=$1 AND firebase_installation_id=$2
                """,
                device_id,
                firebase_installation_id,
            )

    async def list_active_fingerprints(self) -> set[str]:
        return set(await self.list_active_incidents())

    async def list_active_incidents(self) -> dict[str, datetime]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT fingerprint, last_observed_at
                FROM mobile_events
                WHERE status IN ('open', 'escalated')
                """
            )
            return {
                r["fingerprint"]: r["last_observed_at"]
                for r in rows
            }
