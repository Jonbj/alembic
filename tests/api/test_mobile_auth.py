"""Integration tests for /api/mobile/v1/auth.

Tests cover the monitor-only auth boundary: login, refresh rotation, family-reuse
revocation, logout, device registration, and the rule that admin token decoding
rejects mobile-audience JWTs.

The tests assume migration 041 has been applied to the configured DATABASE_URL.
They create and delete rows in the monitor_* tables; they never touch production
portfolio tables.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import asyncpg
import bcrypt
import pytest
from fastapi.testclient import TestClient
from jose import JWTError

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-do-not-use-in-production")

from src.api.main import app  # noqa: E402
from src.config import config  # noqa: E402
from src.mobile_monitoring.auth import (  # noqa: E402
    create_mobile_access_token,
    decode_mobile_access_token,
    hash_refresh_token,
)
from src.mobile_monitoring.store import MonitorStore  # noqa: E402

_MIGRATION_PATH = Path(__file__).parent.parent.parent / "migrations" / "041_mobile_monitoring.sql"


def _dsn() -> str:
    return os.environ.get("DATABASE_URL") or str(config.DATABASE_URL)


@pytest.fixture
async def pool():
    """Asyncpg pool for the test database, with mobile schema applied once."""
    # The app lifespan normally creates the pool; for tests we create our own so
    # migrations and cleanup can run independently of route lifecycle.
    dsn = _dsn()
    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
    assert pool is not None
    migration_sql = _MIGRATION_PATH.read_text()
    async with pool.acquire() as conn:
        # Ensure the migration objects exist idempotently.
        await conn.execute(migration_sql)
    yield pool
    await pool.close()


@pytest.fixture
async def store(pool):
    """Fresh MonitorStore with cleanup of monitor tables after each test."""
    yield MonitorStore(pool)
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE monitor_sessions CASCADE")
        await conn.execute("TRUNCATE TABLE monitor_devices CASCADE")
        await conn.execute("TRUNCATE TABLE monitor_users CASCADE")


@pytest.fixture
async def client():
    """TestClient for the mobile routes."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
async def monitor_user(store):
    """A provisioned monitor user with a known password."""
    return await store.create_user(
        username="alice",
        password_hash=bcrypt.hashpw("secret123".encode(), bcrypt.gensalt()).decode(),
    )


@pytest.fixture
async def monitor_user_and_device(store, monitor_user):
    """User + registered Android device."""
    device = await store.create_device(
        user_id=monitor_user.id,
        installation_id=str(uuid.uuid4()),
        name="Pixel 9",
        app_version="1.0.0",
    )
    return monitor_user, device


def _login(client, username: str, password: str, installation_id: str | None = None) -> dict:
    installation_id = installation_id or str(uuid.uuid4())
    resp = client.post(
        "/api/mobile/v1/auth/login",
        json={
            "username": username,
            "password": password,
            "device": {
                "installation_id": installation_id,
                "name": "Pixel 9",
                "app_version": "1.0.0",
            },
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestMobileAuth:
    """Happy-path and negative tests for mobile auth."""

    async def test_login_creates_user_device_and_session(
        self, client, store, monitor_user
    ):
        print("DEBUG DATABASE_URL", os.environ.get("DATABASE_URL"))
        data = _login(client, "alice", "secret123")
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == config.MOBILE_ACCESS_TOKEN_EXPIRE_MINUTES * 60
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["username"] == "alice"
        assert data["device_id"] is not None

        # Decode token claims and assert mobile boundary.
        claims = decode_mobile_access_token(data["access_token"])
        assert claims["aud"] == "alembic-mobile"
        assert claims["type"] == "access"
        assert claims["scope"] == ["monitor:read", "monitor:device"]
        assert claims["device_id"] == str(data["device_id"])

        device = await store.get_device(data["device_id"])
        assert device is not None
        assert device.name == "Pixel 9"
        assert device.last_seen_at is not None

    async def test_login_invalid_password(self, client, monitor_user):
        resp = client.post(
            "/api/mobile/v1/auth/login",
            json={
                "username": "alice",
                "password": "wrong",
                "device": {
                    "installation_id": str(uuid.uuid4()),
                    "name": "Pixel 9",
                    "app_version": "1.0.0",
                },
            },
        )
        assert resp.status_code == 401

    async def test_refresh_rotates_token(self, client, store, monitor_user):
        first = _login(client, "alice", "secret123")
        old_refresh = first["refresh_token"]

        resp = client.post(
            "/api/mobile/v1/auth/refresh",
            json={"refresh_token": old_refresh},
        )
        assert resp.status_code == 200, resp.text
        second = resp.json()
        assert second["access_token"] != first["access_token"]
        assert second["refresh_token"] != old_refresh

        old_session = await store.get_session_by_refresh_hash(hash_refresh_token(old_refresh))
        assert old_session is not None
        assert old_session.revoked_at is not None

    async def test_refresh_reuse_revokes_family(
        self, client, store, monitor_user
    ):
        first = _login(client, "alice", "secret123")
        old_refresh = first["refresh_token"]

        # Consume the refresh once.
        resp1 = client.post(
            "/api/mobile/v1/auth/refresh",
            json={"refresh_token": old_refresh},
        )
        assert resp1.status_code == 200

        # Reusing the same refresh token must fail and revoke the family.
        resp2 = client.post(
            "/api/mobile/v1/auth/refresh",
            json={"refresh_token": old_refresh},
        )
        assert resp2.status_code == 401
        assert "reuse" in resp2.json()["detail"].lower()

    async def test_logout_revokes_sessions(self, client, store, monitor_user):
        login = _login(client, "alice", "secret123")
        resp = client.post(
            "/api/mobile/v1/auth/logout",
            json={"refresh_token": login["refresh_token"]},
            headers={"Authorization": f"Bearer {login['access_token']}"},
        )
        assert resp.status_code == 204

        # Refresh should now fail.
        resp2 = client.post(
            "/api/mobile/v1/auth/refresh",
            json={"refresh_token": login["refresh_token"]},
        )
        assert resp2.status_code == 401

    async def test_device_registration_requires_mobile_token(
        self, client, monitor_user
    ):
        resp = client.post(
            "/api/mobile/v1/auth/devices",
            json={
                "installation_id": str(uuid.uuid4()),
                "name": "Pixel 9b",
                "app_version": "1.0.1",
                "push_enabled": True,
            },
        )
        assert resp.status_code == 401

    async def test_device_registration_idempotent(
        self, client, monitor_user
    ):
        login = _login(client, "alice", "secret123")
        installation_id = str(uuid.uuid4())
        headers = {"Authorization": f"Bearer {login['access_token']}"}

        resp1 = client.post(
            "/api/mobile/v1/auth/devices",
            json={
                "installation_id": installation_id,
                "name": "Pixel 9b",
                "app_version": "1.0.1",
                "push_enabled": True,
            },
            headers=headers,
        )
        assert resp1.status_code == 200
        device1 = resp1.json()["device"]

        resp2 = client.post(
            "/api/mobile/v1/auth/devices",
            json={
                "installation_id": installation_id,
                "name": "Pixel 9b renamed",
                "app_version": "1.0.2",
                "push_enabled": False,
            },
            headers=headers,
        )
        assert resp2.status_code == 200
        device2 = resp2.json()["device"]
        assert device1["id"] == device2["id"]
        assert device2["name"] == "Pixel 9b renamed"
        assert device2["push_enabled"] is False


@pytest.mark.require_auth
class TestMobileAuthorizationMatrix:
    """Mobile tokens must not authenticate to admin routes."""

    async def test_admin_decode_rejects_mobile_audience(self, monitor_user):
        token = create_mobile_access_token(
            user_id=monitor_user.id,
            device_id=uuid.uuid4(),
        )
        with pytest.raises(JWTError, match="mobile token rejected"):
            from src.api.jwt_utils import decode_access_token

            decode_access_token(token)

    async def test_admin_route_rejects_mobile_bearer(self, client, monitor_user):
        token = create_mobile_access_token(
            user_id=monitor_user.id,
            device_id=uuid.uuid4(),
        )
        resp = client.get(
            "/api/admin/killswitch",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code in (401, 403)
