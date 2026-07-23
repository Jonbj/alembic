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


class RefreshExpiredError(Exception):
    """Raised after an expired refresh-token family has been revoked."""


class MonitorPrincipalInactiveError(Exception):
    """Raised after an inactive user/device refresh family has been revoked."""


@dataclass(frozen=True)
class MonitorUser:
    """Separately provisioned identity allowed to use the monitor API."""

    id: UUID
    username: str
    password_hash: str
    enabled: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class MonitorDevice:
    """Registered mobile installation and its notification state."""

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
    """One device-bound refresh/access session in a rotation family."""

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

    def __init__(self, pool: asyncpg.Pool) -> None:
        """Bind mobile auth persistence to an application-owned asyncpg pool."""
        self.pool = pool

    async def get_user_by_username(self, username: str) -> MonitorUser | None:
        """Return a monitor user by case-normalized username."""
        row = await self.pool.fetchrow(
            "SELECT * FROM monitor_users WHERE username=$1", username.lower()
        )
        if not row:
            return None
        return self._user_from_row(row)

    async def get_user(self, user_id: UUID) -> MonitorUser | None:
        """Return a monitor user by identifier."""
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
        """Create a monitor identity with an already-hashed password."""
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
        """Return a registered monitor device by identifier."""
        row = await self.pool.fetchrow(
            "SELECT * FROM monitor_devices WHERE id=$1", device_id
        )
        if not row:
            return None
        return self._device_from_row(row)

    async def get_device_by_installation(
        self, user_id: UUID, installation_id: str
    ) -> MonitorDevice | None:
        """Return a user's device for one installation identifier."""
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
        """Register a monitor device owned by a provisioned user."""
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
        """Update only the provided mutable device attributes."""
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
        sql = (
            "UPDATE monitor_devices SET "
            + ", ".join(parts)
            + " WHERE id=$"
            + str(len(values))
        )
        await self.pool.execute(sql, *values)

    async def revoke_device(self, device_id: UUID) -> None:
        """Revoke a device and all of its active sessions atomically."""
        now = datetime.now(timezone.utc)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE monitor_devices SET revoked_at=$1 WHERE id=$2",
                    now,
                    device_id,
                )
                await conn.execute(
                    """
                    UPDATE monitor_sessions
                    SET revoked_at=$1
                    WHERE device_id=$2 AND revoked_at IS NULL
                    """,
                    now,
                    device_id,
                )

    async def clear_device_push_registration(self, device_id: UUID) -> None:
        """Remove push delivery state without security-revoking the device."""
        await self.pool.execute(
            """
            UPDATE monitor_devices
            SET firebase_installation_id=NULL, push_enabled=FALSE
            WHERE id=$1
            """,
            device_id,
        )

    async def get_session_by_refresh_hash(
        self, refresh_hash: str
    ) -> MonitorSession | None:
        """Return the session containing an opaque refresh-token hash."""
        row = await self.pool.fetchrow(
            "SELECT * FROM monitor_sessions WHERE refresh_token_hash=$1", refresh_hash
        )
        if not row:
            return None
        return self._session_from_row(row)

    async def _insert_session(
        self,
        conn: asyncpg.Connection,
        *,
        user_id: UUID,
        device_id: UUID | None,
        refresh_hash: str,
        family_id: UUID,
        expires_at: datetime,
        access_jti: UUID | None = None,
    ) -> MonitorSession:
        """Create a device session in a caller-selected rotation family."""
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
        """Create a device-bound session with the configured absolute expiry."""
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

    async def create_login_session_atomic(
        self,
        *,
        user_id: UUID,
        device_id: UUID,
        refresh_hash: str,
        family_id: UUID,
        access_jti: UUID,
    ) -> MonitorSession:
        """Create a login session only while its user and device remain active."""
        expires_at = datetime.now(timezone.utc) + timedelta(
            days=config.MOBILE_REFRESH_TOKEN_EXPIRE_DAYS
        )
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                user_enabled = await conn.fetchval(
                    """
                    SELECT enabled FROM monitor_users
                    WHERE id=$1
                    FOR UPDATE
                    """,
                    user_id,
                )
                device = await conn.fetchrow(
                    """
                    SELECT user_id, revoked_at FROM monitor_devices
                    WHERE id=$1
                    FOR UPDATE
                    """,
                    device_id,
                )
                if (
                    user_enabled is not True
                    or device is None
                    or device["user_id"] != user_id
                    or device["revoked_at"] is not None
                ):
                    raise MonitorPrincipalInactiveError(
                        "Monitor user or device inactive"
                    )
                return await self._insert_session(
                    conn,
                    user_id=user_id,
                    device_id=device_id,
                    refresh_hash=refresh_hash,
                    family_id=family_id,
                    expires_at=expires_at,
                    access_jti=access_jti,
                )

    async def rotate_session_atomic(
        self,
        old_session: MonitorSession,
        new_refresh_hash: str,
        now: datetime | None = None,
        access_jti: UUID | None = None,
    ) -> MonitorSession:
        """Rotate once under row lock, committing family revocation on replay."""
        now = now or datetime.now(timezone.utc)
        rejection: Exception | None = None
        new_session: MonitorSession | None = None
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                user_enabled = await conn.fetchval(
                    """
                    SELECT enabled FROM monitor_users
                    WHERE id=$1
                    FOR UPDATE
                    """,
                    old_session.user_id,
                )
                device = (
                    await conn.fetchrow(
                        """
                        SELECT id, revoked_at FROM monitor_devices
                        WHERE id=$1
                        FOR UPDATE
                        """,
                        old_session.device_id,
                    )
                    if old_session.device_id is not None
                    else None
                )
                row = await conn.fetchrow(
                    """
                    SELECT * FROM monitor_sessions
                    WHERE id=$1
                    FOR UPDATE
                    """,
                    old_session.id,
                )
                family_id = (
                    row["family_id"] if row is not None else old_session.family_id
                )
                if row is None or row["revoked_at"] is not None:
                    await conn.execute(
                        """
                        UPDATE monitor_sessions SET revoked_at=$1
                        WHERE family_id=$2 AND revoked_at IS NULL
                        """,
                        now,
                        family_id,
                    )
                    rejection = ReplayDetectedError("Refresh token replay detected")
                elif row["expires_at"] < now:
                    await conn.execute(
                        """
                        UPDATE monitor_sessions SET revoked_at=$1
                        WHERE family_id=$2 AND revoked_at IS NULL
                        """,
                        now,
                        family_id,
                    )
                    rejection = RefreshExpiredError("Refresh token expired")
                elif (
                    user_enabled is not True
                    or device is None
                    or device["revoked_at"] is not None
                ):
                    await conn.execute(
                        """
                        UPDATE monitor_sessions SET revoked_at=$1
                        WHERE family_id=$2 AND revoked_at IS NULL
                        """,
                        now,
                        family_id,
                    )
                    rejection = MonitorPrincipalInactiveError(
                        "Monitor user or device inactive"
                    )
                else:
                    await conn.execute(
                        """
                        UPDATE monitor_sessions
                        SET revoked_at=$1, rotated_at=$2, last_used_at=$3
                        WHERE id=$4
                        """,
                        now,
                        now,
                        now,
                        old_session.id,
                    )
                    new_session = await self._insert_session(
                        conn,
                        user_id=row["user_id"],
                        device_id=row["device_id"],
                        refresh_hash=new_refresh_hash,
                        family_id=family_id,
                        expires_at=row["expires_at"],
                        access_jti=access_jti,
                    )

        if rejection is not None:
            raise rejection
        if new_session is None:
            raise RuntimeError("Session rotation completed without a result")
        return new_session

    async def revoke_session(self, session_id: UUID) -> None:
        """Revoke one monitor session."""
        await self.pool.execute(
            """
            UPDATE monitor_sessions SET revoked_at=$1
            WHERE id=$2 AND revoked_at IS NULL
            """,
            datetime.now(timezone.utc),
            session_id,
        )

    async def get_session_by_id(self, session_id: UUID) -> MonitorSession | None:
        """Return a monitor session by identifier."""
        row = await self.pool.fetchrow(
            "SELECT * FROM monitor_sessions WHERE id=$1", session_id
        )
        if not row:
            return None
        return self._session_from_row(row)

    async def get_session_by_access_jti(
        self, access_jti: UUID
    ) -> MonitorSession | None:
        """Return an active session whose user and device are still enabled."""
        row = await self.pool.fetchrow(
            """
            SELECT session.*
            FROM monitor_sessions AS session
            JOIN monitor_users AS monitor_user
              ON monitor_user.id=session.user_id
            JOIN monitor_devices AS device
              ON device.id=session.device_id
            WHERE session.access_jti=$1
              AND session.revoked_at IS NULL
              AND monitor_user.enabled=TRUE
              AND device.revoked_at IS NULL
            """,
            access_jti,
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

    async def revoke_all_sessions_for_device(
        self, user_id: UUID, device_id: UUID
    ) -> None:
        """Revoke all sessions for one device owned by the supplied user."""
        await self.pool.execute(
            """
            UPDATE monitor_sessions SET revoked_at=$1
            WHERE user_id=$2 AND device_id=$3 AND revoked_at IS NULL
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
        """Disable a user and revoke every active session atomically."""
        now = datetime.now(timezone.utc)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE monitor_users
                    SET enabled=FALSE, updated_at=$1
                    WHERE id=$2
                    """,
                    now,
                    user_id,
                )
                await conn.execute(
                    """
                    UPDATE monitor_sessions
                    SET revoked_at=$1
                    WHERE user_id=$2 AND revoked_at IS NULL
                    """,
                    now,
                    user_id,
                )

    async def enable_user(self, user_id: UUID) -> None:
        """Re-enable login for a monitor user without restoring old sessions."""
        await self.pool.execute(
            """
            UPDATE monitor_users
            SET enabled=TRUE, updated_at=$1
            WHERE id=$2
            """,
            datetime.now(timezone.utc),
            user_id,
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
