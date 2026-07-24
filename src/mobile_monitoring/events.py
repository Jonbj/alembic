"""Safe mobile event projection with signed keyset pagination."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import asyncpg

from src.api.jwt_utils import _secret
from src.mobile_monitoring.models import (
    EventCategory,
    EventEntity,
    EventHistoryEntry,
    EventItem,
    EventMeasure,
)


class CursorError(ValueError):
    """Raised when an event cursor is malformed or has an invalid signature."""


@dataclass(frozen=True)
class EventPage:
    """One stable keyset-paginated event page."""

    items: list[EventItem]
    next_cursor: str | None


def encode_cursor(occurred_at: datetime, event_id: UUID) -> str:
    """Encode and sign the exclusive lower-bound tuple."""
    payload = json.dumps(
        [occurred_at.isoformat(), str(event_id)],
        separators=(",", ":"),
    ).encode()
    signature = hmac.new(_secret().encode(), payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(payload + signature).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Verify and decode an opaque event cursor."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode())
        payload, supplied_signature = raw[:-32], raw[-32:]
        expected_signature = hmac.new(
            _secret().encode(),
            payload,
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise CursorError("invalid cursor signature")
        timestamp, event_id = json.loads(payload)
        occurred_at = datetime.fromisoformat(timestamp)
        if occurred_at.tzinfo is None:
            raise CursorError("cursor timestamp must include timezone")
        return occurred_at, UUID(event_id)
    except CursorError:
        raise
    except Exception as exc:
        raise CursorError("invalid cursor") from exc


class MobileEventStore:
    """Read-side event store for ``GET /api/mobile/v1/events``."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def list_events(
        self,
        *,
        category: EventCategory,
        days: int,
        cursor: str | None,
        limit: int,
        now: datetime | None = None,
    ) -> EventPage:
        since = (now or datetime.now(timezone.utc)) - timedelta(days=days)
        cursor_at: datetime | None = None
        cursor_id: UUID | None = None
        if cursor:
            cursor_at, cursor_id = decode_cursor(cursor)

        args: list[Any] = [since]
        where = ["occurred_at >= $1"]
        if category == EventCategory.CRITICAL:
            args.append("critical")
            where.append(f"severity = ${len(args)}")
        elif category in {EventCategory.TRADING, EventCategory.SYSTEM}:
            args.append(category.value)
            where.append(f"category = ${len(args)}")
        if cursor_at is not None and cursor_id is not None:
            args.extend([cursor_at, cursor_id])
            where.append(
                f"(occurred_at, id) < (${len(args) - 1}, ${len(args)})"
            )
        args.append(limit + 1)
        sql = f"""
            SELECT id, kind, category, severity, status, occurred_at,
                   first_observed_at, last_observed_at, resolved_at, title,
                   summary, entity_type, entity_id, details
            FROM mobile_events
            WHERE {" AND ".join(where)}
            ORDER BY occurred_at DESC, id DESC
            LIMIT ${len(args)}
        """
        async with self.pool.acquire() as conn:
            rows = list(await conn.fetch(sql, *args))
            visible_rows = rows[:limit]
            history = await self._load_history(
                conn,
                [row["id"] for row in visible_rows],
            )
        items = [
            self._row_to_item(row, history.get(row["id"], []))
            for row in visible_rows
        ]
        next_cursor = None
        if len(rows) > limit and visible_rows:
            last = visible_rows[-1]
            next_cursor = encode_cursor(last["occurred_at"], last["id"])
        return EventPage(items=items, next_cursor=next_cursor)

    async def _load_history(
        self,
        conn: asyncpg.Connection,
        event_ids: list[UUID],
    ) -> dict[UUID, list[EventHistoryEntry]]:
        if not event_ids:
            return {}
        rows = await conn.fetch(
            """
            SELECT event_id, state, occurred_at
            FROM mobile_event_history
            WHERE event_id = ANY($1::uuid[])
            ORDER BY occurred_at
            """,
            event_ids,
        )
        history: dict[UUID, list[EventHistoryEntry]] = {}
        for row in rows:
            history.setdefault(row["event_id"], []).append(
                EventHistoryEntry(state=row["state"], at=row["occurred_at"])
            )
        return history

    @staticmethod
    def _safe_text(value: str | None, limit: int) -> str | None:
        if value is None:
            return None
        compact = " ".join(value.split())
        return compact if len(compact) <= limit else f"{compact[: limit - 1]}…"

    @staticmethod
    def _row_to_item(
        row: asyncpg.Record,
        history: list[EventHistoryEntry],
    ) -> EventItem:
        entity = (
            EventEntity(type=row["entity_type"], id=row["entity_id"])
            if row["entity_type"]
            else None
        )
        details = row["details"] or {}
        measure = None
        if isinstance(details, dict) and "measure_value" in details:
            measure = EventMeasure(
                value=details.get("measure_value"),
                unit=details.get("measure_unit"),
                threshold=details.get("measure_threshold"),
            )
        if not history:
            history = [
                EventHistoryEntry(
                    state=row["status"],
                    at=row["last_observed_at"],
                )
            ]
        return EventItem(
            id=row["id"],
            kind=row["kind"],
            category=row["category"],
            severity=row["severity"],
            status=row["status"],
            occurred_at=row["occurred_at"],
            updated_at=row["last_observed_at"],
            resolved_at=row["resolved_at"],
            title=MobileEventStore._safe_text(row["title"], 120) or "Evento",
            summary=MobileEventStore._safe_text(row["summary"], 400),
            entity=entity,
            measure=measure,
            history=history,
        )
