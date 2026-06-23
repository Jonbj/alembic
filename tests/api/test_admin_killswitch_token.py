"""Tests for kill-switch deactivation token: bytes vs str comparison bug (BUG-5).

The Redis GET command returns bytes in Python redis-py. The confirm_token query
parameter arriving via HTTP is a str. Before the fix, `stored_token != confirm_token`
always evaluated True (bytes != str) so every valid token was rejected.
"""
import os
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("ADMIN_API_KEY", "test-api-key-for-testing-only-12345678")

_API_KEY = "test-api-key-for-testing-only-12345678"
_AUTH = {"X-API-Key": _API_KEY}
_TOKEN = "abcdef1234567890abcdef1234567890"


def _make_app_client(raw_redis_mock, pg_mock=None):
    from src.api.main import app
    from src.api.deps import get_redis_store, get_pg_store

    if pg_mock is None:
        pg_mock = MagicMock()
        pg_mock.write_audit_log = MagicMock()

    redis_store_mock = MagicMock()
    redis_store_mock._r = raw_redis_mock
    redis_store_mock.deactivate_killswitch = MagicMock()
    redis_store_mock.deactivate_operator_halt = MagicMock()
    redis_store_mock.set_mode = MagicMock()

    app.dependency_overrides[get_redis_store] = lambda: redis_store_mock
    app.dependency_overrides[get_pg_store] = lambda: pg_mock
    client = TestClient(app, raise_server_exceptions=False)
    return client, app, get_redis_store, get_pg_store


def _make_raw_redis(token_as_bytes=True, cooldown_ok=True):
    """Build a minimal raw Redis mock for the deactivation endpoint."""
    r = MagicMock()
    r.delete = MagicMock()

    stored = _TOKEN.encode() if token_as_bytes else _TOKEN
    r.get = MagicMock(side_effect=lambda key: (
        stored if key == "ks:recovery_token"
        else (
            # Return a reason JSON that is old enough to pass cooldown
            json.dumps({
                "activated_at": (
                    datetime.now(timezone.utc) - timedelta(seconds=300)
                ).isoformat()
            }).encode()
            if key in ("system:halted_by_operator_reason", "killswitch_reason") and cooldown_ok
            else None
        )
    ))
    return r


class TestKillswitchTokenBytesVsStr:

    def test_valid_token_stored_as_bytes_is_accepted(self):
        """DELETE /killswitch with a correct token should succeed even when Redis
        returns the token as bytes (the common redis-py behavior).

        Before the fix this always returned 422 because b'token' != 'token'.
        """
        raw_r = _make_raw_redis(token_as_bytes=True)
        client, app, get_redis_store, get_pg_store = _make_app_client(raw_r)
        try:
            resp = client.delete(
                f"/api/admin/killswitch?confirm_token={_TOKEN}",
                headers=_AUTH,
            )
        finally:
            app.dependency_overrides.pop(get_redis_store, None)
            app.dependency_overrides.pop(get_pg_store, None)

        assert resp.status_code == 200, (
            f"Expected 200 when token matches (bytes vs str). "
            f"Got {resp.status_code}: {resp.text}. "
            "Fix: decode stored bytes before comparison in deactivate_killswitch()."
        )

    def test_valid_token_stored_as_str_is_accepted(self):
        """DELETE /killswitch with matching str token must also succeed when Redis
        returns the value as str (edge case or future redis versions)."""
        raw_r = _make_raw_redis(token_as_bytes=False)
        client, app, get_redis_store, get_pg_store = _make_app_client(raw_r)
        try:
            resp = client.delete(
                f"/api/admin/killswitch?confirm_token={_TOKEN}",
                headers=_AUTH,
            )
        finally:
            app.dependency_overrides.pop(get_redis_store, None)
            app.dependency_overrides.pop(get_pg_store, None)

        assert resp.status_code == 200, (
            f"Expected 200 when token matches as str. Got {resp.status_code}: {resp.text}."
        )

    def test_wrong_token_is_rejected(self):
        """DELETE /killswitch with a wrong token must return 422 regardless of encoding."""
        raw_r = _make_raw_redis(token_as_bytes=True)
        client, app, get_redis_store, get_pg_store = _make_app_client(raw_r)
        try:
            resp = client.delete(
                "/api/admin/killswitch?confirm_token=wrongtoken",
                headers=_AUTH,
            )
        finally:
            app.dependency_overrides.pop(get_redis_store, None)
            app.dependency_overrides.pop(get_pg_store, None)

        assert resp.status_code == 422, (
            f"Expected 422 for wrong token. Got {resp.status_code}: {resp.text}."
        )

    def test_missing_token_is_rejected(self):
        """DELETE /killswitch without confirm_token must return 422."""
        raw_r = _make_raw_redis(token_as_bytes=True)
        client, app, get_redis_store, get_pg_store = _make_app_client(raw_r)
        try:
            resp = client.delete("/api/admin/killswitch", headers=_AUTH)
        finally:
            app.dependency_overrides.pop(get_redis_store, None)
            app.dependency_overrides.pop(get_pg_store, None)

        assert resp.status_code == 422, (
            f"Expected 422 when confirm_token is absent. Got {resp.status_code}."
        )

    def test_expired_token_none_is_rejected(self):
        """DELETE /killswitch when stored token is None (expired) must return 422."""
        raw_r = MagicMock()
        raw_r.get = MagicMock(return_value=None)
        raw_r.delete = MagicMock()
        client, app, get_redis_store, get_pg_store = _make_app_client(raw_r)
        try:
            resp = client.delete(
                f"/api/admin/killswitch?confirm_token={_TOKEN}",
                headers=_AUTH,
            )
        finally:
            app.dependency_overrides.pop(get_redis_store, None)
            app.dependency_overrides.pop(get_pg_store, None)

        assert resp.status_code == 422, (
            f"Expected 422 when stored token is None (expired). Got {resp.status_code}."
        )
