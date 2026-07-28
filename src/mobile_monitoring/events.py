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
        if len(cursor) > 2048:
            raise CursorError("cursor is too long")
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
        """Project incidents and significant trading lifecycle rows into one feed."""
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
            where.append(f"(occurred_at, id) < (${len(args) - 1}, ${len(args)})")
        args.append(limit + 1)
        sql = f"""
            WITH projected AS (
                SELECT
                    id, kind, category, severity, status, occurred_at,
                    first_observed_at, last_observed_at, resolved_at, title,
                    summary, entity_type, entity_id, details
                FROM mobile_events

                UNION ALL

                SELECT
                    md5('decision:' || id::text)::uuid AS id,
                    'decision'::text AS kind,
                    'trading'::text AS category,
                    'info'::text AS severity,
                    'closed'::text AS status,
                    tick_time AS occurred_at,
                    tick_time AS first_observed_at,
                    tick_time AS last_observed_at,
                    tick_time AS resolved_at,
                    'Decisione ' || UPPER(decision) || ' · ' || symbol AS title,
                    'Decisione operativa registrata.'::text AS summary,
                    'symbol'::text AS entity_type,
                    symbol::text AS entity_id,
                    NULL::jsonb AS details
                FROM execution_decisions
                WHERE UPPER(decision) IN ('BUY', 'SELL', 'HALT')

                UNION ALL

                SELECT
                    md5('order-submitted:' || id::text)::uuid AS id,
                    'order'::text AS kind,
                    'trading'::text AS category,
                    'info'::text AS severity,
                    'closed'::text AS status,
                    tick_time AS occurred_at,
                    tick_time AS first_observed_at,
                    tick_time AS last_observed_at,
                    tick_time AS resolved_at,
                    'Ordine ' || UPPER(decision) || ' inviato · ' || symbol
                        AS title,
                    'Ordine accettato dal percorso di esecuzione.'::text
                        AS summary,
                    'order'::text AS entity_type,
                    order_id::text AS entity_id,
                    NULL::jsonb AS details
                FROM execution_decisions
                WHERE order_id IS NOT NULL
                  AND UPPER(decision) IN ('BUY', 'SELL')

                UNION ALL

                SELECT
                    md5('order-filled-buy:' || id::text)::uuid AS id,
                    'order'::text AS kind,
                    'trading'::text AS category,
                    'info'::text AS severity,
                    'closed'::text AS status,
                    entry_time AS occurred_at,
                    entry_time AS first_observed_at,
                    entry_time AS last_observed_at,
                    entry_time AS resolved_at,
                    'Ordine BUY eseguito · ' || symbol AS title,
                    'Esecuzione di ingresso confermata.'::text AS summary,
                    'order'::text AS entity_type,
                    entry_order_id::text AS entity_id,
                    NULL::jsonb AS details
                FROM trades
                WHERE entry_order_id IS NOT NULL

                UNION ALL

                SELECT
                    md5('position-open:' || id::text)::uuid AS id,
                    'position'::text AS kind,
                    'trading'::text AS category,
                    'info'::text AS severity,
                    'closed'::text AS status,
                    entry_time AS occurred_at,
                    entry_time AS first_observed_at,
                    entry_time AS last_observed_at,
                    entry_time AS resolved_at,
                    'Posizione aperta · ' || symbol AS title,
                    'Apertura posizione registrata.'::text AS summary,
                    'position'::text AS entity_type,
                    id::text AS entity_id,
                    NULL::jsonb AS details
                FROM trades

                UNION ALL

                SELECT
                    md5('order-filled-sell:' || id::text)::uuid AS id,
                    'order'::text AS kind,
                    'trading'::text AS category,
                    'info'::text AS severity,
                    'closed'::text AS status,
                    exit_time AS occurred_at,
                    exit_time AS first_observed_at,
                    exit_time AS last_observed_at,
                    exit_time AS resolved_at,
                    'Ordine SELL eseguito · ' || symbol AS title,
                    'Esecuzione di uscita confermata.'::text AS summary,
                    'order'::text AS entity_type,
                    exit_order_id::text AS entity_id,
                    NULL::jsonb AS details
                FROM trades
                WHERE exit_time IS NOT NULL AND exit_order_id IS NOT NULL

                UNION ALL

                SELECT
                    md5('position-close:' || id::text)::uuid AS id,
                    'position'::text AS kind,
                    'trading'::text AS category,
                    'info'::text AS severity,
                    'closed'::text AS status,
                    exit_time AS occurred_at,
                    exit_time AS first_observed_at,
                    exit_time AS last_observed_at,
                    exit_time AS resolved_at,
                    'Posizione chiusa · ' || symbol AS title,
                    'Chiusura posizione registrata.'::text AS summary,
                    'position'::text AS entity_type,
                    id::text AS entity_id,
                    NULL::jsonb AS details
                FROM trades
                WHERE exit_time IS NOT NULL
            )
            SELECT id, kind, category, severity, status, occurred_at,
                   first_observed_at, last_observed_at, resolved_at, title,
                   summary, entity_type, entity_id, details
            FROM projected
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
            self._row_to_item(row, history.get(row["id"], [])) for row in visible_rows
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
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except json.JSONDecodeError:
                details = {}
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
