"""Integration tests for /api/mobile/v1/auth.

Tests cover the monitor-only auth boundary: login, refresh rotation, family-reuse
revocation, logout, device registration, and the rule that admin token decoding
rejects mobile-audience JWTs.

The tests apply the mobile migrations to the configured DATABASE_URL.
They create and delete rows in the monitor_* tables; they never touch production
portfolio tables.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncpg
import bcrypt
import pytest
from fastapi.testclient import TestClient
from httpx import Response
from jose import JWTError, jwt

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-do-not-use-in-production")

from src.api.jwt_utils import create_access_token  # noqa: E402
from src.api.main import app  # noqa: E402
from src.api.routes.mobile_auth import get_login_rate_limiter  # noqa: E402
from src.config import config  # noqa: E402
from src.mobile_monitoring.auth import (  # noqa: E402
    create_mobile_access_token,
    decode_mobile_access_token,
    hash_refresh_token,
)
from src.mobile_monitoring.models import MobileErrorResponse  # noqa: E402
from src.mobile_monitoring.rate_limit import RateLimitResult  # noqa: E402
from src.mobile_monitoring.store import MonitorStore  # noqa: E402


class _AllowLogin:
    """Test rate limiter that never consumes a shared Redis budget."""

    def check(self, username: str, source: str) -> RateLimitResult:
        del username, source
        return RateLimitResult(allowed=True, retry_after_seconds=0)


_MIGRATION_PATHS = (
    Path(__file__).parent.parent.parent / "migrations" / "041_mobile_monitoring.sql",
    Path(__file__).parent.parent.parent
    / "migrations"
    / "042_mobile_session_access_jti.sql",
)


def _dsn() -> str:
    return os.environ.get("DATABASE_URL") or str(config.DATABASE_URL)


def _error_message(response: Response) -> str:
    return str(response.json()["error"]["message"])


@pytest.fixture
async def pool():
    """Asyncpg pool for the test database, with mobile schema applied once."""
    # The app lifespan normally creates the pool; for tests we create our own so
    # migrations and cleanup can run independently of route lifecycle.
    dsn = _dsn()
    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
    assert pool is not None
    async with pool.acquire() as conn:
        # Ensure the migration objects exist idempotently.
        for migration_path in _MIGRATION_PATHS:
            await conn.execute(migration_path.read_text())
    yield pool
    await pool.close()


@pytest.fixture
async def store(pool):
    """Fresh MonitorStore with cleanup of monitor tables after each test."""
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE monitor_sessions CASCADE")
        await conn.execute("TRUNCATE TABLE monitor_devices CASCADE")
        await conn.execute("TRUNCATE TABLE monitor_users CASCADE")
    yield MonitorStore(pool)
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE monitor_sessions CASCADE")
        await conn.execute("TRUNCATE TABLE monitor_devices CASCADE")
        await conn.execute("TRUNCATE TABLE monitor_users CASCADE")


@pytest.fixture
async def client():
    """TestClient for the mobile routes."""
    app.dependency_overrides[get_login_rate_limiter] = _AllowLogin
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_login_rate_limiter, None)


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


def _login(
    client, username: str, password: str, installation_id: str | None = None
) -> dict:
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
        assert _error_message(resp) == "Invalid credentials"

    async def test_login_unknown_user_has_uniform_error(self, client, monitor_user):
        """Unknown users and bad passwords return the same public error."""
        resp = client.post(
            "/api/mobile/v1/auth/login",
            json={
                "username": "unknown-user",
                "password": "wrong",
                "device": {
                    "installation_id": str(uuid.uuid4()),
                    "name": "Pixel 9",
                    "app_version": "1.0.0",
                },
            },
        )
        assert resp.status_code == 401
        assert _error_message(resp) == "Invalid credentials"

    @pytest.mark.parametrize("username", ["alice", "unknown-user"])
    async def test_login_oversized_password_has_uniform_error(
        self,
        client,
        monitor_user,
        username: str,
    ):
        """Bcrypt's 72-byte limit never becomes a public 500 or user oracle."""
        response = client.post(
            "/api/mobile/v1/auth/login",
            json={
                "username": username,
                "password": "x" * 100,
                "device": {
                    "installation_id": str(uuid.uuid4()),
                    "name": "Pixel 9",
                    "app_version": "1.0.0",
                },
            },
        )

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_credentials"
        MobileErrorResponse.model_validate(response.json())

    async def test_login_validation_uses_redacted_mobile_error_contract(self, client):
        """Invalid mobile input returns 400 without echoing rejected secrets."""
        password = "must-not-be-reflected"
        response = client.post(
            "/api/mobile/v1/auth/login",
            json={
                "username": "alice",
                "password": password,
                "unexpected": "field",
            },
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_request"
        MobileErrorResponse.model_validate(response.json())
        assert password not in response.text

    async def test_login_disabled_user_has_uniform_error(
        self, client, store, monitor_user
    ):
        """Disabled identities receive the same response as other failures."""
        await store.disable_user(monitor_user.id)

        response = client.post(
            "/api/mobile/v1/auth/login",
            json={
                "username": "alice",
                "password": "secret123",
                "device": {
                    "installation_id": str(uuid.uuid4()),
                    "name": "Pixel 9",
                    "app_version": "1.0.0",
                },
            },
        )

        assert response.status_code == 401
        assert _error_message(response) == "Invalid credentials"

    async def test_login_rechecks_user_inside_session_transaction(
        self, client, store, monitor_user, monkeypatch
    ):
        """A disable committed after credential lookup prevents session insert."""
        original = MonitorStore.create_login_session_atomic

        async def disable_then_create(session_store, **kwargs):
            await session_store.pool.execute(
                "UPDATE monitor_users SET enabled=FALSE WHERE id=$1",
                kwargs["user_id"],
            )
            return await original(session_store, **kwargs)

        monkeypatch.setattr(
            MonitorStore,
            "create_login_session_atomic",
            disable_then_create,
        )
        response = client.post(
            "/api/mobile/v1/auth/login",
            json={
                "username": "alice",
                "password": "secret123",
                "device": {
                    "installation_id": str(uuid.uuid4()),
                    "name": "Pixel 9",
                    "app_version": "1.0.0",
                },
            },
        )

        assert response.status_code == 401
        assert _error_message(response) == "Invalid credentials"
        assert (
            await store.pool.fetchval(
                "SELECT COUNT(*) FROM monitor_sessions WHERE user_id=$1",
                monitor_user.id,
            )
            == 0
        )

    async def test_login_rechecks_device_inside_session_transaction(
        self, client, store, monitor_user, monkeypatch
    ):
        """A device revocation committed after lookup prevents session insert."""
        installation_id = str(uuid.uuid4())
        device = await store.create_device(
            user_id=monitor_user.id,
            installation_id=installation_id,
            name="Pixel 9",
            app_version="1.0.0",
        )
        original = MonitorStore.create_login_session_atomic

        async def revoke_then_create(session_store, **kwargs):
            await session_store.pool.execute(
                """
                UPDATE monitor_devices
                SET revoked_at=NOW()
                WHERE id=$1
                """,
                kwargs["device_id"],
            )
            return await original(session_store, **kwargs)

        monkeypatch.setattr(
            MonitorStore,
            "create_login_session_atomic",
            revoke_then_create,
        )
        response = client.post(
            "/api/mobile/v1/auth/login",
            json={
                "username": "alice",
                "password": "secret123",
                "device": {
                    "installation_id": installation_id,
                    "name": "Pixel 9",
                    "app_version": "1.0.0",
                },
            },
        )

        assert response.status_code == 401
        assert _error_message(response) == "Invalid credentials"
        assert (
            await store.pool.fetchval(
                "SELECT COUNT(*) FROM monitor_sessions WHERE device_id=$1",
                device.id,
            )
            == 0
        )

    async def test_login_rate_limit_returns_429_for_known_and_unknown_users(
        self, client, monitor_user
    ):
        """Rate-limit behavior is independent of whether the username exists."""
        from src.mobile_monitoring.rate_limit import RateLimitResult

        class _DenyLogin:
            def check(self, username: str, source: str) -> RateLimitResult:
                del username, source
                return RateLimitResult(allowed=False, retry_after_seconds=42)

        app.dependency_overrides[get_login_rate_limiter] = _DenyLogin
        for username in ("alice", "unknown-user"):
            response = client.post(
                "/api/mobile/v1/auth/login",
                json={
                    "username": username,
                    "password": "wrong",
                    "device": {
                        "installation_id": str(uuid.uuid4()),
                        "name": "Pixel 9",
                        "app_version": "1.0.0",
                    },
                },
            )
            assert response.status_code == 429
            assert _error_message(response) == "Too many login attempts"
            assert response.headers["Retry-After"] == "42"

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

        old_session = await store.get_session_by_refresh_hash(
            hash_refresh_token(old_refresh)
        )
        new_session = await store.get_session_by_refresh_hash(
            hash_refresh_token(second["refresh_token"])
        )
        assert old_session is not None
        assert new_session is not None
        assert old_session.revoked_at is not None
        assert old_session.last_used_at is not None
        assert new_session.last_used_at is None
        assert new_session.expires_at == old_session.expires_at

    async def test_refresh_reuse_revokes_family(self, client, store, monitor_user):
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
        assert resp2.status_code == 409
        assert "reuse" in _error_message(resp2).lower()

    async def test_logout_revokes_sessions(self, client, store, monitor_user):
        login = _login(client, "alice", "secret123")
        await store.update_device(
            login["device_id"],
            firebase_installation_id="opaque-fid",
            push_enabled=True,
        )
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
        assert resp2.status_code == 409
        device = await store.get_device(login["device_id"])
        assert device.revoked_at is None
        assert device.firebase_installation_id is None
        assert device.push_enabled is False

    async def test_logout_keeps_session_revocation_when_push_cleanup_fails(
        self, client, store, monitor_user, monkeypatch
    ):
        """Device cleanup is best effort after durable session revocation."""
        login = _login(client, "alice", "secret123")

        async def fail_push_cleanup(*args, **kwargs):
            del args, kwargs
            raise RuntimeError("simulated push cleanup failure")

        monkeypatch.setattr(
            MonitorStore,
            "clear_device_push_registration",
            fail_push_cleanup,
        )
        response = client.post(
            "/api/mobile/v1/auth/logout",
            json={"refresh_token": login["refresh_token"]},
            headers={"Authorization": f"Bearer {login['access_token']}"},
        )

        assert response.status_code == 204
        session = await store.get_session_by_refresh_hash(
            hash_refresh_token(login["refresh_token"])
        )
        assert session is not None
        assert session.revoked_at is not None

    async def test_access_token_device_must_match_server_session(
        self, client, store, monitor_user
    ):
        """A validly signed token cannot substitute a different device claim."""
        login = _login(client, "alice", "secret123")
        session = await store.get_session_by_refresh_hash(
            hash_refresh_token(login["refresh_token"])
        )
        assert session is not None
        assert session.access_jti is not None
        mismatched = create_mobile_access_token(
            user_id=monitor_user.id,
            device_id=uuid.uuid4(),
            jti=session.access_jti,
        )

        response = client.get(
            "/api/mobile/v1/auth/me",
            headers={"Authorization": f"Bearer {mismatched}"},
        )

        assert response.status_code == 401

    @pytest.mark.parametrize(
        ("claim_override", "expires_minutes"),
        [
            ({"aud": "wrong-audience"}, 15),
            ({"type": "refresh"}, 15),
            ({"scope": ["monitor:device"]}, 15),
            ({"scope": "monitor:read"}, 15),
            ({}, -1),
        ],
    )
    async def test_access_token_rejects_invalid_contract_claims(
        self,
        monitor_user,
        claim_override,
        expires_minutes,
    ):
        """Audience, type, scope shape, and expiry are mandatory."""
        device_id = uuid.uuid4()
        payload = {
            "sub": str(monitor_user.id),
            "aud": "alembic-mobile",
            "type": "access",
            "scope": ["monitor:read", "monitor:device"],
            "device_id": str(device_id),
            "jti": str(uuid.uuid4()),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=expires_minutes),
        }
        payload.update(claim_override)
        from src.api.jwt_utils import _secret

        token = jwt.encode(payload, _secret(), algorithm=config.JWT_ALGORITHM)

        with pytest.raises(JWTError):
            decode_mobile_access_token(token)

    async def test_access_token_rejects_invalid_signature(self, monitor_user):
        """A token signed with another key is not a mobile credential."""
        payload = {
            "sub": str(monitor_user.id),
            "aud": "alembic-mobile",
            "type": "access",
            "scope": ["monitor:read"],
            "device_id": str(uuid.uuid4()),
            "jti": str(uuid.uuid4()),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        }
        token = jwt.encode(
            payload,
            "different-test-signing-key",
            algorithm=config.JWT_ALGORITHM,
        )

        with pytest.raises(JWTError):
            decode_mobile_access_token(token)

    async def test_access_token_empty_scope_does_not_receive_defaults(
        self, monitor_user
    ):
        """An explicitly empty scope set stays empty and fails validation."""
        token = create_mobile_access_token(
            user_id=monitor_user.id,
            device_id=uuid.uuid4(),
            scopes=[],
        )

        with pytest.raises(JWTError, match="scope"):
            decode_mobile_access_token(token)

    async def test_access_token_missing_read_scope_returns_403(
        self, client, store, monitor_user
    ):
        """A valid session without the route's read scope is forbidden."""
        login = _login(client, "alice", "secret123")
        session = await store.get_session_by_refresh_hash(
            hash_refresh_token(login["refresh_token"])
        )
        assert session is not None
        assert session.access_jti is not None
        token = create_mobile_access_token(
            user_id=monitor_user.id,
            device_id=login["device_id"],
            scopes=["monitor:device"],
            jti=session.access_jti,
        )

        response = client.get(
            "/api/mobile/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 403

    async def test_access_token_malformed_scope_returns_401(
        self, client, store, monitor_user
    ):
        """A signed token with a non-list scope claim is malformed, not scoped."""
        login = _login(client, "alice", "secret123")
        payload = jwt.get_unverified_claims(login["access_token"])
        payload["scope"] = "monitor:read"
        from src.api.jwt_utils import _secret

        token = jwt.encode(payload, _secret(), algorithm=config.JWT_ALGORITHM)
        response = client.get(
            "/api/mobile/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_access_token"

    async def test_device_registration_requires_mobile_token(
        self, client, monitor_user
    ):
        resp = client.post(
            "/api/mobile/v1/devices",
            json={
                "installation_id": str(uuid.uuid4()),
                "name": "Pixel 9b",
                "app_version": "1.0.1",
                "push_enabled": True,
            },
        )
        assert resp.status_code == 401

    async def test_device_registration_idempotent(self, client, monitor_user):
        login = _login(client, "alice", "secret123")
        installation_id = str(uuid.uuid4())
        headers = {"Authorization": f"Bearer {login['access_token']}"}

        resp1 = client.post(
            "/api/mobile/v1/devices",
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
            "/api/mobile/v1/devices",
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

    async def test_device_registration_requires_device_scope(
        self, client, store, monitor_user
    ):
        """A read-only token cannot register notification devices."""
        login = _login(client, "alice", "secret123")
        session = await store.get_session_by_refresh_hash(
            hash_refresh_token(login["refresh_token"])
        )
        assert session is not None
        assert session.access_jti is not None
        read_only_token = create_mobile_access_token(
            user_id=monitor_user.id,
            device_id=login["device_id"],
            scopes=["monitor:read"],
            jti=session.access_jti,
        )

        response = client.post(
            "/api/mobile/v1/devices",
            json={
                "installation_id": str(uuid.uuid4()),
                "name": "Pixel 9b",
                "app_version": "1.0.1",
                "push_enabled": True,
            },
            headers={"Authorization": f"Bearer {read_only_token}"},
        )

        assert response.status_code == 403

    async def test_device_revocation_invalidates_its_access_token(
        self, client, store, monitor_user
    ):
        """Revoking an owned device also revokes all of its active sessions."""
        login = _login(client, "alice", "secret123")
        headers = {"Authorization": f"Bearer {login['access_token']}"}

        response = client.delete(
            f"/api/mobile/v1/devices/{login['device_id']}",
            headers=headers,
        )

        assert response.status_code == 204
        me = client.get("/api/mobile/v1/auth/me", headers=headers)
        assert me.status_code == 401

    async def test_device_revocation_cannot_target_another_user(
        self, client, store, monitor_user
    ):
        """A monitor identity cannot revoke a device owned by another user."""
        alice_login = _login(client, "alice", "secret123")
        bob = await store.create_user(
            username="bob",
            password_hash=bcrypt.hashpw(
                "bob-secret".encode(),
                bcrypt.gensalt(),
            ).decode(),
        )
        bob_device = await store.create_device(
            user_id=bob.id,
            installation_id=str(uuid.uuid4()),
            name="Bob Pixel",
            app_version="1.0.0",
        )

        response = client.delete(
            f"/api/mobile/v1/devices/{bob_device.id}",
            headers={"Authorization": f"Bearer {alice_login['access_token']}"},
        )

        assert response.status_code == 404
        assert (await store.get_device(bob_device.id)).revoked_at is None


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

    async def test_mobile_route_rejects_legacy_admin_bearer_with_403(
        self, client, monitor_user
    ):
        """A valid admin identity has no mobile audience and is forbidden."""
        token = create_access_token("alice")

        response = client.get(
            "/api/mobile/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "invalid_audience"

    async def test_mobile_route_does_not_accept_admin_api_key(
        self, client, monitor_user
    ):
        """The admin API-key mechanism is not a mobile credential."""
        response = client.get(
            "/api/mobile/v1/auth/me",
            headers={"X-API-Key": "a" * 40},
        )

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "authentication_required"
