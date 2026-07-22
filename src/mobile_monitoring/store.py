"""Persistence helpers for mobile monitor users, devices, and sessions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import asyncpg

from src.config import config


class ReplayDetectedError(Exception):
    """Raised when a refresh token is reused; the family has been revoked."""


class RotationError(Exception):
    """Raised when atomic rotation fails before commit."""


@dataclass(frozen=True)
class MonitorUser:
    id: UUID
    username: str
    password_hash: str
    enabled: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class MonitorDevice:
    id: UUID
    user_id: UUID
    installation_id: str
    firebase_installation_id: str | None
    name: str
    app_version: str
    push_enabled: bool
    last_seen_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


@dataclass(frozen=True)
class MonitorSession:
    id: UUID
    user_id: UUID
    device_id: UUID | None
    refresh_token_hash: str
    family_id: UUID
    access_jti: UUID | None
    expires_at: datetime
    last_used_at: datetime | None
    rotated_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class MonitorStore:
    """Async DB operations for mobile monitoring auth."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def get_user_by_username(self, username: str) -> MonitorUser | None:
        row = await self.pool.fetchrow(
            "SELECT * FROM monitor_users WHERE username=$1", username.lower()
        )
        if not row:
            return None
        return self._user_from_row(row)

    async def get_user(self, user_id: UUID) -> MonitorUser | None:
        row = await self.pool.fetchrow(
            "SELECT * FROM monitor_users WHERE id=$1", user_id
        )
        if not row:
            return None
        return self._user_from_row(row)

    async def create_user(
        self,
        *,
        username: str,
        password_hash: str,
    ) -> MonitorUser:
        row = await self.pool.fetchrow(
            """
            INSERT INTO monitor_users (username, password_hash)
            VALUES ($1, $2)
            RETURNING *
            """,
            username.lower(),
            password_hash,
        )
        return self._user_from_row(row)

    async def get_device(self, device_id: UUID) -> MonitorDevice | None:
        row = await self.pool.fetchrow(
            "SELECT * FROM monitor_devices WHERE id=$1", device_id
        )
        if not row:
            return None
        return self._device_from_row(row)

    async def get_device_by_installation(
        self, user_id: UUID, installation_id: str
    ) -> MonitorDevice | None:
        row = await self.pool.fetchrow(
            """
            SELECT * FROM monitor_devices
            WHERE user_id=$1 AND installation_id=$2
            """,
            user_id,
            str(installation_id),
        )
        if not row:
            return None
        return self._device_from_row(row)

    async def create_device(
        self,
        *,
        user_id: UUID,
        installation_id: str,
        name: str,
        app_version: str,
        firebase_installation_id: str | None = None,
        push_enabled: bool = False,
    ) -> MonitorDevice:
        row = await self.pool.fetchrow(
            """
            INSERT INTO monitor_devices (
                user_id, installation_id, firebase_installation_id,
                name, app_version, push_enabled
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
            """,
            user_id,
            str(installation_id),
            firebase_installation_id,
            name,
            app_version,
            push_enabled,
        )
        return self._device_from_row(row)

    async def update_device(
        self,
        device_id: UUID,
        *,
        name: str | None = None,
        app_version: str | None = None,
        firebase_installation_id: str | None = None,
        push_enabled: bool | None = None,
        last_seen_at: datetime | None = None,
    ) -> None:
        # Build a dynamic SET clause safely.
        parts: list[str] = []
        values: list[Any] = []
        if name is not None:
            parts.append("name=$" + str(len(values) + 1))
            values.append(name)
        if app_version is not None:
            parts.append("app_version=$" + str(len(values) + 1))
            values.append(app_version)
        if firebase_installation_id is not None:
            parts.append("firebase_installation_id=$" + str(len(values) + 1))
            values.append(firebase_installation_id)
        if push_enabled is not None:
            parts.append("push_enabled=$" + str(len(values) + 1))
            values.append(push_enabled)
        if last_seen_at is not None:
            parts.append("last_seen_at=$" + str(len(values) + 1))
            values.append(last_seen_at)
        if not parts:
            return
        values.append(device_id)
        sql = "UPDATE monitor_devices SET " + ", ".join(parts) + " WHERE id=$" + str(len(values))
        await self.pool.execute(sql, *values)

    async def revoke_device(self, device_id: UUID) -> None:
        await self.pool.execute(
            "UPDATE monitor_devices SET revoked_at=$1 WHERE id=$2",
            datetime.now(timezone.utc),
            device_id,
        )

    async def get_session_by_refresh_hash(self, refresh_hash: str) -> MonitorSession | None:
        row = await self.pool.fetchrow(
            "SELECT * FROM monitor_sessions WHERE refresh_token_hash=$1", refresh_hash
        )
        if not row:
            return None
        return self._session_from_row(row)

    async def _insert_session(
        self,
        conn,
        *,
        user_id: UUID,
        device_id: UUID | None,
        refresh_hash: str,
        family_id: UUID,
        expires_at: datetime,
        access_jti: UUID | None = None,
    ) -> MonitorSession:
        row = await conn.fetchrow(
            """
            INSERT INTO monitor_sessions
                (user_id, device_id, refresh_token_hash, family_id, expires_at, access_jti)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
            """,
            user_id,
            device_id,
            refresh_hash,
            family_id,
            expires_at,
            access_jti,
        )
        return self._session_from_row(row)

    async def create_session(
        self,
        *,
        user_id: UUID,
        device_id: UUID | None,
        refresh_hash: str,
        family_id: UUID,
        expires_days: int | None = None,
        access_jti: UUID | None = None,
    ) -> MonitorSession:
        expires_days = expires_days or config.MOBILE_REFRESH_TOKEN_EXPIRE_DAYS
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)
        async with self.pool.acquire() as conn:
            return await self._insert_session(
                conn,
                user_id=user_id,
                device_id=device_id,
                refresh_hash=refresh_hash,
                family_id=family_id,
                expires_at=expires_at,
                access_jti=access_jti,
            )

    async def rotate_session(
        self,
        old_session: MonitorSession,
        new_refresh_hash: str,
        access_jti: UUID | None = None,
    ) -> MonitorSession:
        now = datetime.now(timezone.utc)
        await self.pool.execute(
            "UPDATE monitor_sessions SET revoked_at=$1, rotated_at=$2 WHERE id=$3",
            now,
            now,
            old_session.id,
        )
        return await self.create_session(
            user_id=old_session.user_id,
            device_id=old_session.device_id,
            refresh_hash=new_refresh_hash,
            family_id=old_session.family_id,
            access_jti=access_jti,
        )

    async def rotate_session_atomic(
        self,
        old_session: MonitorSession,
        new_refresh_hash: str,
        now: datetime | None = None,
        access_jti: UUID | None = None,
    ) -> MonitorSession:
        """Atomically rotate a refresh token under row lock.

        Runs in a single transaction:
        1. Lock the old session row with FOR UPDATE.
        2. If a later active session exists in the same family, revoke the whole
           family and raise ReplayDetectedError.
        3. Revoke the old session and insert the successor.

        Any exception before commit rolls back, leaving the old token valid.
        """
        now = now or datetime.now(timezone.utc)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT * FROM monitor_sessions
                    WHERE id=$1 AND revoked_at IS NULL
                    FOR UPDATE
                    """,
                    old_session.id,
                )
                if row is None:
                    # The session was revoked between lookup and lock.
                    raise ReplayDetectedError("Refresh token already revoked")

                later_active = await conn.fetchval(
                    """
                    SELECT COUNT(*) FROM monitor_sessions
                    WHERE family_id=$1 AND created_at > $2 AND revoked_at IS NULL
                    """,
                    row["family_id"],
                    row["created_at"],
                )
                if later_active:
                    await conn.execute(
                        """
                        UPDATE monitor_sessions SET revoked_at=$1
                        WHERE family_id=$2 AND revoked_at IS NULL
                        """,
                        now,
                        row["family_id"],
                    )
                    raise ReplayDetectedError("Refresh token replay detected")

                await conn.execute(
                    """
                    UPDATE monitor_sessions
                    SET revoked_at=$1, rotated_at=$2
                    WHERE id=$3
                    """,
                    now,
                    now,
                    old_session.id,
                )
                expires_at = now + timedelta(days=config.MOBILE_REFRESH_TOKEN_EXPIRE_DAYS)
                return await self._insert_session(
                    conn,
                    user_id=row["user_id"],
                    device_id=row["device_id"],
                    refresh_hash=new_refresh_hash,
                    family_id=row["family_id"],
                    expires_at=expires_at,
                    access_jti=access_jti,
                )

    async def revoke_session(self, session_id: UUID) -> None:
        await self.pool.execute(
            "UPDATE monitor_sessions SET revoked_at=$1 WHERE id=$2",
            datetime.now(timezone.utc),
            session_id,
        )

    async def get_session_by_id(self, session_id: UUID) -> MonitorSession | None:
        row = await self.pool.fetchrow(
            "SELECT * FROM monitor_sessions WHERE id=$1", session_id
        )
        if not row:
            return None
        return self._session_from_row(row)

    async def get_session_by_access_jti(self, access_jti: UUID) -> MonitorSession | None:
        row = await self.pool.fetchrow(
            "SELECT * FROM monitor_sessions WHERE access_jti=$1", access_jti
        )
        if not row:
            return None
        return self._session_from_row(row)

    async def revoke_family(self, family_id: UUID, now: datetime | None = None) -> None:
        """Revoke every active session in a refresh-token family."""
        now = now or datetime.now(timezone.utc)
        await self.pool.execute(
            """
            UPDATE monitor_sessions SET revoked_at=$1
            WHERE family_id=$2 AND revoked_at IS NULL
            """,
            now,
            family_id,
        )

    async def revoke_all_sessions_for_device(self, user_id: UUID, device_id: UUID) -> None:
        await self.pool.execute(
            """
            UPDATE monitor_sessions SET revoked_at=$1
            WHERE user_id=$2 AND device_id=$3
            """,
            datetime.now(timezone.utc),
            user_id,
            device_id,
        )

    async def revoke_all_sessions_for_user(self, user_id: UUID) -> None:
        """Revoke every active session for a monitor user."""
        await self.pool.execute(
            """
            UPDATE monitor_sessions SET revoked_at=$1
            WHERE user_id=$2 AND revoked_at IS NULL
            """,
            datetime.now(timezone.utc),
            user_id,
        )

    async def disable_user(self, user_id: UUID) -> None:
        await self.pool.execute(
            """
            UPDATE monitor_users
            SET enabled=FALSE, updated_at=$1
            WHERE id=$2
            """,
            datetime.now(timezone.utc),
            user_id,
        )

    async def enable_user(self, user_id: UUID) -> None:
        await self.pool.execute(
            """
            UPDATE monitor_users
            SET enabled=TRUE, updated_at=$1
            WHERE id=$2
            """,
            datetime.now(timezone.utc),
            user_id,
        )

    async def mark_session_used(self, session_id: UUID) -> None:
        await self.pool.execute(
            "UPDATE monitor_sessions SET last_used_at=$1 WHERE id=$2",
            datetime.now(timezone.utc),
            session_id,
        )

    # -- helpers ---------------------------------------------------------

    def _user_from_row(self, row: asyncpg.Record) -> MonitorUser:
        return MonitorUser(
            id=row["id"],
            username=row["username"],
            password_hash=row["password_hash"],
            enabled=row["enabled"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _device_from_row(self, row: asyncpg.Record) -> MonitorDevice:
        return MonitorDevice(
            id=row["id"],
            user_id=row["user_id"],
            installation_id=row["installation_id"],
            firebase_installation_id=row["firebase_installation_id"],
            name=row["name"],
            app_version=row["app_version"],
            push_enabled=row["push_enabled"],
            last_seen_at=row["last_seen_at"],
            revoked_at=row["revoked_at"],
            created_at=row["created_at"],
        )

    def _session_from_row(self, row: asyncpg.Record) -> MonitorSession:
        return MonitorSession(
            id=row["id"],
            user_id=row["user_id"],
            device_id=row["device_id"],
            refresh_token_hash=row["refresh_token_hash"],
            family_id=row["family_id"],
            access_jti=row.get("access_jti"),
            expires_at=row["expires_at"],
            last_used_at=row["last_used_at"],
            rotated_at=row["rotated_at"],
            revoked_at=row["revoked_at"],
            created_at=row["created_at"],
        )
