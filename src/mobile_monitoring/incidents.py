"""Server-owned alert incident engine for the mobile monitor.

The engine turns system, risk, and order observations into deduplicated,
lifecycle-managed incidents and transactional notification outbox entries.
No financial detail, ticker, or token leaks into the outbox or FCM payload.
"""

from __future__ import annotations

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
                existing = await conn.fetchrow(
                    "SELECT id, status, severity FROM mobile_events WHERE fingerprint=$1",
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
                        "UPDATE mobile_events SET last_observed_at=$1 WHERE id=$2",
                        occurred_at,
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
                        # Recovery: the fault condition has cleared.
                        await conn.execute(
                            """
                            UPDATE mobile_events
                            SET status=$1, resolved_at=$2, last_observed_at=$3
                            WHERE id=$4
                            """,
                            EventStatus.RECOVERED.value,
                            occurred_at,
                            occurred_at,
                            event_id,
                        )
                        await self._insert_history(conn, event_id, EventStatus.RECOVERED.value, old_severity.value, details)
                        await self._enqueue_deliveries(conn, event_id, "recover")
                        return ObservationResult(event_id, fingerprint, "recover", old_severity.value, EventStatus.RECOVERED.value)

                    # Same or lower severity: just observe.
                    return ObservationResult(event_id, fingerprint, "observe", old_severity.value, old_status.value)

                if old_status == EventStatus.RECOVERED and expected and _severity_rank_value(severity) >= _severity_rank_value(Severity.WARNING):
                    # Re-open a recovered incident.
                    await conn.execute(
                        """
                        UPDATE mobile_events
                        SET status=$1, severity=$2, resolved_at=NULL, last_observed_at=$3
                        WHERE id=$4
                        """,
                        EventStatus.OPEN.value,
                        severity.value,
                        occurred_at,
                        event_id,
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
            details,
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
            details,
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
            WHERE revoked_at IS NULL AND push_enabled = TRUE
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
                SELECT d.id, d.event_id, d.device_id, d.transition, d.attempt_count,
                       e.fingerprint, e.severity, e.status
                FROM mobile_notification_deliveries d
                JOIN mobile_events e ON e.id = d.event_id
                WHERE d.sent_at IS NULL AND d.failed_at IS NULL
                  AND (d.next_attempt_at IS NULL OR d.next_attempt_at <= $1)
                ORDER BY d.attempt_count ASC, d.created_at ASC
                LIMIT $2
                """,
                now,
                limit,
            )

    async def record_delivery_attempt(
        self,
        delivery_id: int,
        *,
        provider_message_id: str | None = None,
        failed_at: datetime | None = None,
        error_code: str | None = None,
        next_attempt_at: datetime | None = None,
    ) -> None:
        async with self.pool.acquire() as conn:
            if failed_at is not None:
                await conn.execute(
                    """
                    UPDATE mobile_notification_deliveries
                    SET attempt_count = attempt_count + 1,
                        failed_at=$1,
                        error_code=$2,
                        next_attempt_at=$3
                    WHERE id=$4
                    """,
                    failed_at,
                    error_code,
                    next_attempt_at,
                    delivery_id,
                )
            else:
                await conn.execute(
                    """
                    UPDATE mobile_notification_deliveries
                    SET attempt_count = attempt_count + 1,
                        provider_message_id=$1,
                        sent_at=$2
                    WHERE id=$3
                    """,
                    provider_message_id,
                    datetime.now(timezone.utc),
                    delivery_id,
                )

    async def disable_device_push(self, device_id: UUID) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE monitor_devices SET push_enabled=FALSE WHERE id=$1",
                device_id,
            )

    async def list_active_fingerprints(self) -> set[str]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT fingerprint FROM mobile_events WHERE status IN ('open', 'escalated')"
            )
            return {r["fingerprint"] for r in rows}
