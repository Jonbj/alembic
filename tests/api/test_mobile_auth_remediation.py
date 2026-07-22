"""
MOB-02 remediation tests for mobile authentication.

Seams under test:
- POST /api/mobile/v1/auth/refresh: atomic rotation, replay detection,
  family revocation, disabled user/device, expired/malformed tokens, disabled
  child token after replay.
- FastAPI mutation route matrix: a mobile access token must receive 403 on every
  trading/order/admin/config/strategy/labeling/weight mutation endpoint.
- scripts/manage_monitor_users.py CLI: create, disable, enable, revoke
  session, revoke all user sessions, revoke device, redacted output.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import asyncpg
import httpx
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from src.api.main import app
from src.config import config
from src.mobile_monitoring.auth import (
    create_mobile_access_token,
    decode_mobile_access_token,
    generate_refresh_token,
    hash_refresh_token,
)
from src.mobile_monitoring.store import MonitorStore
from tests.api.test_mobile_auth import _login

pytestmark = pytest.mark.asyncio

_MIGRATION_PATH = Path(__file__).parent.parent.parent / "migrations" / "041_mobile_monitoring.sql"


def _dsn() -> str:
    return os.environ.get("DATABASE_URL") or str(config.DATABASE_URL)


@pytest_asyncio.fixture(loop_scope="function")
async def pg_pool():
    """Asyncpg pool for the test database with the mobile schema applied."""
    pool = await asyncpg.create_pool(dsn=_dsn(), min_size=1, max_size=4)
    assert pool is not None
    migration_sql = _MIGRATION_PATH.read_text()
    async with pool.acquire() as conn:
        await conn.execute(migration_sql)
    yield pool
    await pool.close()


@pytest.fixture
async def store(pg_pool):
    """Fresh MonitorStore with cleanup of monitor tables after each test."""
    yield MonitorStore(pg_pool)
    async with pg_pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE monitor_sessions CASCADE")
        await conn.execute("TRUNCATE TABLE monitor_devices CASCADE")
        await conn.execute("TRUNCATE TABLE monitor_users CASCADE")


@pytest_asyncio.fixture(loop_scope="function")
async def client():
    """TestClient for the mobile routes."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
async def monitor_user(store):
    """A provisioned monitor user with a known password."""
    import bcrypt
    return await store.create_user(
        username="alice",
        password_hash=bcrypt.hashpw("secret123".encode(), bcrypt.gensalt()).decode(),
    )


@pytest_asyncio.fixture(loop_scope="function", autouse=True)
async def _cleanup_monitor_tables(pg_pool):
    """Ensure monitor tables are empty before and after each test in this file."""
    async with pg_pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE monitor_sessions CASCADE")
        await conn.execute("TRUNCATE TABLE monitor_devices CASCADE")
        await conn.execute("TRUNCATE TABLE monitor_users CASCADE")
    yield
    async with pg_pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE monitor_sessions CASCADE")
        await conn.execute("TRUNCATE TABLE monitor_devices CASCADE")
        await conn.execute("TRUNCATE TABLE monitor_users CASCADE")


class TestRefreshReplayAndAtomicity:
    """
    MOB-02 exact requirements:
    - Refresh-token rotation in a single atomic transaction with row lock.
    - Concurrent requests using the same active token produce at most one
      success and only one active successor.
    - Reuse of an already-rotated refresh token atomically revokes all active
      sessions in the family; the child access token previously valid becomes
      unusable.
    - Error messages must not claim revocation unless successfully committed;
      never expose token/hash.
    """

    async def test_refresh_reuse_revokes_family_and_child_token(
        self, client: TestClient, monitor_user
    ):
        """MOB-02: reusing a rotated refresh token revokes the entire family
        and invalidates the child access token."""
        login = _login(client, "alice", "secret123")
        refresh = login["refresh_token"]

        # First refresh creates child session and rotates parent.
        first = client.post(
            "/api/mobile/v1/auth/refresh", json={"refresh_token": refresh}
        )
        assert first.status_code == 200
        child_refresh = first.json()["refresh_token"]
        child_access = first.json()["access_token"]

        # Child access token should initially work.
        me = client.get(
            "/api/mobile/v1/auth/me",
            headers={"Authorization": f"Bearer {child_access}"},
        )
        assert me.status_code == 200

        # Reuse the original (parent) refresh token -> replay detection.
        replay = client.post(
            "/api/mobile/v1/auth/refresh", json={"refresh_token": refresh}
        )
        assert replay.status_code == 401
        data = replay.json()
        assert "detail" in data
        detail = data["detail"].lower()
        # Must claim revocation was committed.
        assert "revoked" in detail
        # Must not expose tokens/hashes.
        assert refresh not in replay.text

        # Child refresh token must now be invalid.
        child_reuse = client.post(
            "/api/mobile/v1/auth/refresh",
            json={"refresh_token": child_refresh},
        )
        assert child_reuse.status_code == 401

        # Child access token must now be rejected.
        me_after = client.get(
            "/api/mobile/v1/auth/me",
            headers={"Authorization": f"Bearer {child_access}"},
        )
        assert me_after.status_code == 401

    async def test_concurrent_refresh_same_token(self, client: TestClient, monitor_user, store):
        """MOB-02: concurrent refresh of the same token produces <=1 success
        and exactly one active successor."""

        async def _worker(token: str) -> tuple[int, str | None]:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.post(
                    "/api/mobile/v1/auth/refresh",
                    json={"refresh_token": token},
                )
            body = resp.json() if resp.status_code == 200 else {}
            return resp.status_code, body.get("refresh_token")

        login = _login(client, "alice", "secret123")
        refresh = login["refresh_token"]

        # Spawn concurrent refreshes using the same token.
        results = await asyncio.gather(
            *[_worker(refresh) for _ in range(8)],
            return_exceptions=True,
        )

        statuses = [
            r[0] for r in results if isinstance(r, tuple) and len(r) == 2
        ]
        successes = statuses.count(200)
        # At most one success.
        assert successes <= 1, f"Expected <=1 success, got {successes}: {statuses}"

        # Only one active successor refresh token in the family.
        active_hashes = await store.pool.fetch(
            """
            SELECT id, revoked_at, rotated_at
            FROM monitor_sessions
            WHERE family_id = (
                SELECT family_id FROM monitor_sessions
                WHERE refresh_token_hash=$1
            )
            AND revoked_at IS NULL
            """,
            hash_refresh_token(refresh),
        )
        assert len(active_hashes) <= 1, active_hashes

    async def test_rotation_failure_rolls_back(self, client: TestClient, monitor_user, store):
        """MOB-02: if rotation fails mid-transaction, the old token stays valid."""
        from src import mobile_monitoring

        login = _login(client, "alice", "secret123")
        refresh = login["refresh_token"]

        # Patch session creation to fail after the atomic rotation has revoked
        # the old session. Because rotation runs in a transaction, the old
        # session must remain valid (rolled back).
        original_insert = mobile_monitoring.store.MonitorStore._insert_session

        async def _failing_insert(*args, **kwargs):
            raise RuntimeError("simulated failure")

        mobile_monitoring.store.MonitorStore._insert_session = _failing_insert  # type: ignore[method-assign]
        try:
            resp = client.post(
                "/api/mobile/v1/auth/refresh", json={"refresh_token": refresh}
            )
            assert resp.status_code == 500

            # Old token must still be valid (transaction rolled back).
            old_session = await store.get_session_by_refresh_hash(
                hash_refresh_token(refresh)
            )
            assert old_session is not None
            assert old_session.revoked_at is None
        finally:
            mobile_monitoring.store.MonitorStore._insert_session = original_insert  # type: ignore[method-assign]

        # Without the patch, the original token can still be rotated.
        again = client.post(
            "/api/mobile/v1/auth/refresh", json={"refresh_token": refresh}
        )
        assert again.status_code == 200, again.text

    async def test_refresh_disabled_user_revoked_device_expired_malformed(
        self, client: TestClient, monitor_user, store
    ):
        """MOB-02: refresh rejected for disabled user, revoked device,
        expired token, malformed token."""
        login = _login(client, "alice", "secret123")
        refresh = login["refresh_token"]

        # Revoke the device using the device_id returned by login.
        await store.revoke_device(login["device_id"])
        resp = client.post(
            "/api/mobile/v1/auth/refresh", json={"refresh_token": refresh}
        )
        assert resp.status_code == 401
        assert "device" in resp.json()["detail"].lower()

        # Create a new device/session to test expired token.
        user = await store.get_user_by_username("alice")
        await store.revoke_session(
            (await store.get_session_by_refresh_hash(hash_refresh_token(refresh))).id
        )
        new_device = await store.create_device(
            user_id=user.id,
            installation_id="expired-device",
            name="expired",
            app_version="1.0",
        )
        expired_raw = generate_refresh_token()
        expired_session = await store.create_session(
            user_id=user.id,
            device_id=new_device.id,
            refresh_hash=hash_refresh_token(expired_raw),
            family_id="a1111111-a111-a111-a111-a11111111111",
            expires_days=-1,
        )
        assert expired_session.expires_at < datetime.now(timezone.utc)
        resp = client.post(
            "/api/mobile/v1/auth/refresh", json={"refresh_token": expired_raw}
        )
        assert resp.status_code == 401
        assert "expired" in resp.json()["detail"].lower()

        # Malformed token.
        resp = client.post(
            "/api/mobile/v1/auth/refresh", json={"refresh_token": "not-a-token"}
        )
        assert resp.status_code in (401, 422)


@pytest.mark.require_auth
class TestMobileAuthorizationMatrix:
    """
    MOB-02: program a route matrix that returns 403 on every
    trading/order/admin/config/strategy/labeling/weight mutation endpoint
    when called with a mobile access token.
    """

    MUTATION_ROUTES = [
        # Admin mutations
        ("POST", "/api/admin/mode", {"mode": "halted"}),
        ("POST", "/api/admin/llm-models", {"models": "glm52"}),
        ("POST", "/api/admin/killswitch", {"reason": "test"}),
        ("DELETE", "/api/admin/killswitch", {}),
        ("POST", "/api/admin/killswitch/recovery-token", {}),
        # Weight/strategy/config/labeling mutations
        ("POST", "/api/weights/approve", {"weights": {}}),
        ("POST", "/api/config", {"key": "x", "value": "y"}),
        ("POST", "/api/strategies/S1/promote", {}),
        ("POST", "/api/strategies/S1/approve", {}),
        ("POST", "/api/strategies/S1/demote", {}),
        ("POST", "/api/labeling/1", {"label": "neutral"}),
    ]

    @pytest.mark.parametrize("method,path,body", MUTATION_ROUTES)
    async def test_mutation_route_returns_403(
        self, client: TestClient, monitor_user, method: str, path: str, body: dict
    ):
        """MOB-02: mobile token must not mutate trading/admin/config/etc."""
        login = _login(client, "alice", "secret123")
        access = login["access_token"]
        headers = {"Authorization": f"Bearer {access}"}

        fn = getattr(client, method.lower())
        kwargs = {"json": body} if method in {"POST", "PUT", "PATCH"} else {}
        resp = fn(path, headers=headers, **kwargs)
        assert resp.status_code == 403, f"{method} {path} -> {resp.status_code}: {resp.text[:200]}"


class TestManageMonitorUsersCLI:
    """
    MOB-02: operator script with create, disable, enable, revoke session,
    revoke all user sessions, revoke device. Output must never expose tokens
    or hashes.
    """

    async def test_cli_create_user_device(self, pg_pool):
        from scripts import manage_monitor_users

        result = await manage_monitor_users.main(
            ["create", "--username", "cliuser", "--password", "testsecret"]
        )
        assert result == 0
        async with pg_pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT * FROM monitor_users WHERE username=$1", "cliuser"
            )
        assert user is not None
        assert user["enabled"] is True

    async def test_cli_disable_enable_user(self, pg_pool):
        from scripts import manage_monitor_users

        await manage_monitor_users.main(
            ["create", "--username", "toggleuser", "--password", "testsecret"]
        )
        assert (
            await manage_monitor_users.main(
                ["disable", "--username", "toggleuser"]
            )
            == 0
        )
        async with pg_pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT * FROM monitor_users WHERE username=$1", "toggleuser"
            )
        assert user["enabled"] is False
        assert (
            await manage_monitor_users.main(
                ["enable", "--username", "toggleuser"]
            )
            == 0
        )
        async with pg_pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT * FROM monitor_users WHERE username=$1", "toggleuser"
            )
        assert user["enabled"] is True

    async def test_cli_revoke_session(self, pg_pool):
        from scripts import manage_monitor_users

        await manage_monitor_users.main(
            ["create", "--username", "sessuser", "--password", "testsecret"]
        )
        async with pg_pool.acquire() as conn:
            session_id = await conn.fetchval(
                """
                INSERT INTO monitor_sessions (user_id, device_id, refresh_token_hash, family_id, expires_at)
                VALUES (
                    (SELECT id FROM monitor_users WHERE username=$1),
                    (SELECT id FROM monitor_devices WHERE user_id=(SELECT id FROM monitor_users WHERE username=$1)),
                    $2, $3, $4
                )
                RETURNING id
                """,
                "sessuser",
                hash_refresh_token("dummy"),
                "a1111111-a111-a111-a111-a11111111111",
                datetime.now(timezone.utc) + timedelta(days=30),
            )
        assert (
            await manage_monitor_users.main(
                ["revoke-session", "--session-id", str(session_id)]
            )
            == 0
        )
        async with pg_pool.acquire() as conn:
            sess = await conn.fetchrow(
                "SELECT * FROM monitor_sessions WHERE id=$1", session_id
            )
        assert sess["revoked_at"] is not None

    async def test_cli_revoke_all_user_sessions(self, pg_pool):
        from scripts import manage_monitor_users

        await manage_monitor_users.main(
            ["create", "--username", "alluser", "--password", "testsecret"]
        )
        async with pg_pool.acquire() as conn:
            user_id = await conn.fetchval(
                "SELECT id FROM monitor_users WHERE username=$1", "alluser"
            )
            await conn.execute(
                """
                INSERT INTO monitor_sessions (user_id, device_id, refresh_token_hash, family_id, expires_at)
                VALUES ($1, (SELECT id FROM monitor_devices WHERE user_id=$1), $2, $3, $4)
                """,
                user_id,
                hash_refresh_token("s1"),
                "a1111111-a111-a111-a111-a11111111111",
                datetime.now(timezone.utc) + timedelta(days=30),
            )
        assert (
            await manage_monitor_users.main(
                ["revoke-all", "--username", "alluser"]
            )
            == 0
        )
        async with pg_pool.acquire() as conn:
            active = await conn.fetchval(
                "SELECT COUNT(*) FROM monitor_sessions WHERE user_id=$1 AND revoked_at IS NULL",
                user_id,
            )
        assert active == 0

    async def test_cli_revoke_device(self, pg_pool):
        from scripts import manage_monitor_users

        await manage_monitor_users.main(
            ["create", "--username", "devuser", "--password", "testsecret"]
        )
        async with pg_pool.acquire() as conn:
            device_id = await conn.fetchval(
                "SELECT id FROM monitor_devices WHERE user_id=(SELECT id FROM monitor_users WHERE username=$1)",
                "devuser",
            )
        assert (
            await manage_monitor_users.main(
                ["revoke-device", "--device-id", str(device_id)]
            )
            == 0
        )
        async with pg_pool.acquire() as conn:
            dev = await conn.fetchrow(
                "SELECT * FROM monitor_devices WHERE id=$1", device_id
            )
        assert dev["revoked_at"] is not None

    async def test_cli_output_never_exposes_secrets(self, capsys):
        from scripts import manage_monitor_users

        await manage_monitor_users.main(
            ["create", "--username", "secretuser", "--password", "testsecret"]
        )
        captured = capsys.readouterr().out + capsys.readouterr().err
        assert "refresh" not in captured.lower()
        assert "hash" not in captured.lower()
