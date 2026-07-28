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
from uuid import uuid4

import asyncpg
import bcrypt
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import Response
from jose import jwt
from starlette.routing import BaseRoute

from src.api.jwt_utils import _secret
from src.api.main import app
from src.api.routes.mobile_auth import get_login_rate_limiter
from src.config import config
from src.mobile_monitoring.auth import (
    generate_refresh_token,
    hash_refresh_token,
)
from src.mobile_monitoring.rate_limit import RateLimitResult
from src.mobile_monitoring.store import (
    MonitorPrincipalInactiveError,
    MonitorStore,
    ReplayDetectedError,
)
from tests.api.test_mobile_auth import _login

pytestmark = pytest.mark.asyncio


class _AllowLogin:
    """Test limiter that prevents integration tests sharing a Redis budget."""

    def check(self, username: str, source: str) -> RateLimitResult:
        del username, source
        return RateLimitResult(allowed=True, retry_after_seconds=0)


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
    return os.environ.get("DATABASE_URL") or str(config.DATABASE_URL)


def _error_message(response: Response) -> str:
    return str(response.json()["error"]["message"])


@pytest_asyncio.fixture(loop_scope="function")
async def pg_pool():
    """Asyncpg pool for the test database with the mobile schema applied."""
    pool = await asyncpg.create_pool(dsn=_dsn(), min_size=1, max_size=4)
    assert pool is not None
    async with pool.acquire() as conn:
        for migration_path in _MIGRATION_PATHS:
            await conn.execute(migration_path.read_text())
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
    app.dependency_overrides[get_login_rate_limiter] = _AllowLogin
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_login_rate_limiter, None)


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
        assert replay.status_code == 409
        data = replay.json()
        assert "error" in data
        detail = _error_message(replay).lower()
        # Must claim revocation was committed.
        assert "revoked" in detail
        # Must not expose tokens/hashes.
        assert refresh not in replay.text

        # Child refresh token must now be invalid.
        child_reuse = client.post(
            "/api/mobile/v1/auth/refresh",
            json={"refresh_token": child_refresh},
        )
        assert child_reuse.status_code == 409

        # Child access token must now be rejected.
        me_after = client.get(
            "/api/mobile/v1/auth/me",
            headers={"Authorization": f"Bearer {child_access}"},
        )
        assert me_after.status_code == 401

    async def test_concurrent_refresh_same_token(
        self, client: TestClient, monitor_user, store
    ):
        """Exactly one rotation succeeds and replay revokes its successor."""
        login = _login(client, "alice", "secret123")
        refresh = login["refresh_token"]
        old_session = await store.get_session_by_refresh_hash(
            hash_refresh_token(refresh)
        )
        assert old_session is not None

        results = await asyncio.gather(
            *[
                store.rotate_session_atomic(
                    old_session,
                    hash_refresh_token(generate_refresh_token()),
                    access_jti=uuid4(),
                )
                for _ in range(8)
            ],
            return_exceptions=True,
        )

        successes = [result for result in results if not isinstance(result, Exception)]
        failures = [result for result in results if isinstance(result, Exception)]
        assert len(successes) == 1
        assert len(failures) == 7
        assert all(isinstance(result, ReplayDetectedError) for result in failures)

        active_sessions = await store.pool.fetch(
            """
            SELECT id
            FROM monitor_sessions
            WHERE family_id=$1 AND revoked_at IS NULL
            """,
            old_session.family_id,
        )
        assert active_sessions == []

    async def test_rotation_failure_rolls_back(
        self, client: TestClient, monitor_user, store
    ):
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
        assert "device" in _error_message(resp).lower()

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
        assert "expired" in _error_message(resp).lower()

        # Malformed token.
        resp = client.post(
            "/api/mobile/v1/auth/refresh", json={"refresh_token": "not-a-token"}
        )
        assert resp.status_code in (401, 422)

    async def test_refresh_rejects_disabled_user(
        self, client: TestClient, monitor_user, store
    ):
        """A disabled user cannot rotate a previously issued refresh token."""
        login = _login(client, "alice", "secret123")
        await store.disable_user(monitor_user.id)

        response = client.post(
            "/api/mobile/v1/auth/refresh",
            json={"refresh_token": login["refresh_token"]},
        )

        assert response.status_code == 401
        assert "inactive" in _error_message(response).lower()

    async def test_unknown_well_formed_refresh_token_is_not_called_replay(
        self, client: TestClient, monitor_user
    ):
        """An unissued token gets a generic rejection without a revocation claim."""
        unknown_token = generate_refresh_token()

        response = client.post(
            "/api/mobile/v1/auth/refresh",
            json={"refresh_token": unknown_token},
        )

        assert response.status_code == 401
        detail = _error_message(response).lower()
        assert detail == "invalid refresh token"
        assert "replay" not in detail
        assert "revoked" not in detail
        assert unknown_token not in response.text

    async def test_disabling_user_invalidates_existing_access_token(
        self, client: TestClient, monitor_user, store
    ):
        """An operator disable takes effect for access JWTs already issued."""
        login = _login(client, "alice", "secret123")

        await store.disable_user(monitor_user.id)

        response = client.get(
            "/api/mobile/v1/auth/me",
            headers={"Authorization": f"Bearer {login['access_token']}"},
        )
        assert response.status_code == 401

    async def test_revoking_device_invalidates_existing_access_token(
        self, client: TestClient, monitor_user, store
    ):
        """An operator device revocation takes effect for existing access JWTs."""
        login = _login(client, "alice", "secret123")

        await store.revoke_device(login["device_id"])

        response = client.get(
            "/api/mobile/v1/auth/me",
            headers={"Authorization": f"Bearer {login['access_token']}"},
        )
        assert response.status_code == 401

    async def test_atomic_rotation_rechecks_disabled_user(
        self, client: TestClient, monitor_user, store
    ):
        """Rotation rejects a user disabled after the route's initial lookup."""
        login = _login(client, "alice", "secret123")
        old_session = await store.get_session_by_refresh_hash(
            hash_refresh_token(login["refresh_token"])
        )
        assert old_session is not None
        await store.pool.execute(
            "UPDATE monitor_users SET enabled=FALSE WHERE id=$1",
            monitor_user.id,
        )

        with pytest.raises(MonitorPrincipalInactiveError, match="inactive"):
            await store.rotate_session_atomic(
                old_session,
                hash_refresh_token(generate_refresh_token()),
                access_jti=uuid4(),
            )

        active_sessions = await store.pool.fetchval(
            """
            SELECT COUNT(*) FROM monitor_sessions
            WHERE family_id=$1 AND revoked_at IS NULL
            """,
            old_session.family_id,
        )
        assert active_sessions == 0


@pytest.mark.require_auth
class TestMobileAuthorizationMatrix:
    """
    MOB-02: program a route matrix that returns 403 on every
    trading/order/admin/config/strategy/labeling/weight mutation endpoint
    when called with a mobile access token.
    """

    # Programmatically discover every unsafe (non-GET/HEAD/OPTIONS) route. Only
    # the four explicitly classified mobile auth writes are excluded. This
    # makes a new mobile mutation fail closed until it is reviewed.
    MOBILE_WRITE_ALLOWLIST = {
        ("POST", "/api/mobile/v1/auth/login"),
        ("POST", "/api/mobile/v1/auth/refresh"),
        ("POST", "/api/mobile/v1/auth/logout"),
        ("POST", "/api/mobile/v1/devices"),
        ("DELETE", "/api/mobile/v1/devices/{device_id}"),
    }
    MUTATION_ROUTES: list[tuple[str, str, str, dict]] = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/"):
            continue
        methods: set[str] = getattr(route, "methods", set()) - {
            "GET",
            "HEAD",
            "OPTIONS",
        }
        for method in methods:
            if (method, path) in MOBILE_WRITE_ALLOWLIST:
                continue
            params: dict[str, object] = {}
            for name, convertor in getattr(route, "param_convertors", {}).items():
                convertor_name = type(convertor).__name__
                if convertor_name == "IntegerConvertor":
                    params[name] = 1
                elif convertor_name == "FloatConvertor":
                    params[name] = 1.0
                elif convertor_name == "UUIDConvertor":
                    params[name] = uuid4()
                else:
                    params[name] = "matrix-probe"
            concrete_path = str(route.url_path_for(route.name, **params))
            body = {"_matrix_probe": True}
            MUTATION_ROUTES.append((method, path, concrete_path, body))

    @pytest.mark.parametrize("method,route_path,path,body", MUTATION_ROUTES)
    async def test_mutation_route_returns_403_before_handler(
        self,
        client: TestClient,
        monitor_user,
        monkeypatch,
        method: str,
        route_path: str,
        path: str,
        body: dict,
    ):
        """A blocked mobile request never reaches the mutation handler."""
        login = _login(client, "alice", "secret123")
        access = login["access_token"]
        headers = {"Authorization": f"Bearer {access}"}

        matching_route: BaseRoute | None = next(
            (
                route
                for route in app.routes
                if getattr(route, "path", None) == route_path
                and method in getattr(route, "methods", set())
            ),
            None,
        )
        assert matching_route is not None

        async def _unexpected_handler(*args: Any, **kwargs: Any) -> None:
            raise AssertionError(f"Blocked handler reached: {method} {route_path}")

        monkeypatch.setattr(matching_route, "app", _unexpected_handler)
        fn = getattr(client, method.lower())
        kwargs = {"json": body} if method in {"POST", "PUT", "PATCH"} else {}
        resp = fn(path, headers=headers, **kwargs)
        assert resp.status_code == 403, (
            f"{method} {path} -> {resp.status_code}: {resp.text[:200]}"
        )

    async def test_future_mobile_mutation_is_denied_by_default(
        self, client: TestClient, monitor_user
    ):
        """A newly added mobile write is blocked until explicitly classified."""
        reached = False
        path = "/api/mobile/v1/_authorization-matrix-probe"

        async def probe() -> dict[str, bool]:
            nonlocal reached
            reached = True
            return {"reached": True}

        app.add_api_route(path, probe, methods=["POST"])
        route = app.routes[-1]
        try:
            access = _login(client, "alice", "secret123")["access_token"]
            response = client.post(
                path,
                headers={"Authorization": f"Bearer {access}"},
            )
            assert response.status_code == 403
            assert reached is False
        finally:
            app.router.routes.remove(route)

    async def test_mobile_audience_array_is_still_confined(
        self, client: TestClient, monitor_user
    ):
        """JWT audience arrays cannot bypass the mobile mutation boundary."""
        access = _login(client, "alice", "secret123")["access_token"]
        payload = jwt.get_unverified_claims(access)
        payload["aud"] = ["alembic-mobile", "another-service"]
        token = jwt.encode(payload, _secret(), algorithm=config.JWT_ALGORITHM)

        response = client.post(
            "/api/config",
            json={"_matrix_probe": True},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "mobile_boundary_violation"


class TestManageMonitorUsersCLI:
    """
    MOB-02: operator script with create, disable, enable, revoke session,
    revoke all user sessions, revoke device. Output must never expose tokens
    or hashes.
    """

    async def test_cli_rejects_plaintext_password_argument(self, capsys):
        """Plaintext credentials cannot be supplied through shell arguments."""
        from scripts import manage_monitor_users

        plaintext = "visible-in-shell-history"
        with pytest.raises(SystemExit):
            await manage_monitor_users.main(
                [
                    "create",
                    "--username",
                    "unsafe-user",
                    "--password",
                    plaintext,
                ]
            )
        result = capsys.readouterr()
        assert plaintext not in result.out
        assert plaintext not in result.err

    async def test_cli_create_user_device(self, pg_pool):
        from scripts import manage_monitor_users

        result = await manage_monitor_users.main(
            [
                "create",
                "--username",
                "cliuser",
                "--password-hash",
                bcrypt.hashpw("testsecret".encode(), bcrypt.gensalt()).decode(),
            ]
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
            [
                "create",
                "--username",
                "toggleuser",
                "--password-hash",
                bcrypt.hashpw("testsecret".encode(), bcrypt.gensalt()).decode(),
            ]
        )
        assert (
            await manage_monitor_users.main(["disable", "--username", "toggleuser"])
            == 0
        )
        async with pg_pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT * FROM monitor_users WHERE username=$1", "toggleuser"
            )
        assert user["enabled"] is False
        assert (
            await manage_monitor_users.main(["enable", "--username", "toggleuser"]) == 0
        )
        async with pg_pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT * FROM monitor_users WHERE username=$1", "toggleuser"
            )
        assert user["enabled"] is True

    async def test_cli_revoke_session(self, pg_pool):
        from scripts import manage_monitor_users

        await manage_monitor_users.main(
            [
                "create",
                "--username",
                "sessuser",
                "--password-hash",
                bcrypt.hashpw("testsecret".encode(), bcrypt.gensalt()).decode(),
            ]
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
            [
                "create",
                "--username",
                "alluser",
                "--password-hash",
                bcrypt.hashpw("testsecret".encode(), bcrypt.gensalt()).decode(),
            ]
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
            await manage_monitor_users.main(["revoke-all", "--username", "alluser"])
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
            [
                "create",
                "--username",
                "devuser",
                "--password-hash",
                bcrypt.hashpw("testsecret".encode(), bcrypt.gensalt()).decode(),
            ]
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

        password_hash = bcrypt.hashpw(
            "testsecret".encode(),
            bcrypt.gensalt(),
        ).decode()
        await manage_monitor_users.main(
            [
                "create",
                "--username",
                "secretuser",
                "--password-hash",
                password_hash,
            ]
        )
        result = capsys.readouterr()
        captured = result.out + result.err
        assert password_hash not in captured
        assert "testsecret" not in captured
        assert "refresh" not in captured.lower()
        assert "hash" not in captured.lower()
