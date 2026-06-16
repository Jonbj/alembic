"""Tests for JWT authentication — login endpoint and dual-auth middleware."""
import os

import pytest
from fastapi.testclient import TestClient

# Must be set before importing app (conftest already sets ADMIN_API_KEY)
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD_HASH"] = "$2b$12$i6qSOhZRTLWbWoSTukGsw.p2y0hEJEKmEqjHGwjuv3dXqB2Gy2WHO"  # "secret"
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-key-for-testing-only-not-for-prod"
os.environ["JWT_EXPIRE_MINUTES"] = "60"

from src.api.main import app  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture()
def valid_token(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "secret"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# Login endpoint
# ---------------------------------------------------------------------------

@pytest.mark.require_auth
def test_login_returns_jwt_on_valid_credentials(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "secret"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.require_auth
def test_login_returns_401_on_wrong_password(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "wrongpassword"})
    assert resp.status_code == 401


@pytest.mark.require_auth
def test_login_returns_401_on_wrong_username(client):
    resp = client.post("/api/auth/login", json={"username": "hacker", "password": "secret"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /api/auth/me
# ---------------------------------------------------------------------------

@pytest.mark.require_auth
def test_me_returns_username_with_valid_token(client, valid_token):
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {valid_token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "admin"


@pytest.mark.require_auth
def test_me_returns_403_without_token(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Dual-auth: protected endpoints accept both Bearer and X-API-Key
# ---------------------------------------------------------------------------

@pytest.mark.require_auth
def test_protected_endpoint_accepts_bearer_token(client, valid_token):
    resp = client.get("/api/signals", headers={"Authorization": f"Bearer {valid_token}"})
    # 200 or any non-auth error is acceptable — 403 means auth failed
    assert resp.status_code != 403


@pytest.mark.require_auth
def test_protected_endpoint_accepts_api_key(client):
    resp = client.get(
        "/api/signals",
        headers={"X-API-Key": "test-api-key-for-testing-only-12345678"},
    )
    assert resp.status_code != 403


@pytest.mark.require_auth
def test_protected_endpoint_rejects_no_credentials(client):
    resp = client.get("/api/signals")
    assert resp.status_code == 403


@pytest.mark.require_auth
def test_protected_endpoint_rejects_invalid_bearer(client):
    resp = client.get(
        "/api/signals",
        headers={"Authorization": "Bearer this.is.not.a.valid.jwt"},
    )
    assert resp.status_code == 403


@pytest.mark.require_auth
def test_protected_endpoint_rejects_expired_looking_token(client):
    # A well-formed JWT signed with a different key should be rejected
    import jose.jwt as jose_jwt
    bad_token = jose_jwt.encode(
        {"sub": "admin", "exp": 9999999999},
        "wrong-secret-key",
        algorithm="HS256",
    )
    resp = client.get(
        "/api/signals",
        headers={"Authorization": f"Bearer {bad_token}"},
    )
    assert resp.status_code == 403
