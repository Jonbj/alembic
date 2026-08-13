"""Regression tests for API CORS and rate-limit hardening (#43)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from redis import RedisError
from starlette.middleware.cors import CORSMiddleware

from src.api.deps import get_redis_client, get_redis_store
from src.api.main import app
from src.config import Config, config


class _FixedWindowRedis:
    """Minimal Redis EVAL fake with one counter per limiter key."""

    def __init__(self) -> None:
        self.counts: defaultdict[str, int] = defaultdict(int)

    def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: object,
    ) -> Any:
        del script, numkeys
        key = str(keys_and_args[0])
        self.counts[key] += 1
        return [self.counts[key], int(keys_and_args[1])]


class _UnavailableRedis:
    def eval(self, *args: object, **kwargs: object) -> Any:
        del args, kwargs
        raise RedisError("unavailable")


@pytest.mark.asyncio
async def test_cors_preflight_denies_unlisted_origin_explicitly() -> None:
    """An unknown browser origin is rejected by the explicit CORS policy."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.options(
            "/api/auth/login",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_cors_middleware_uses_only_the_configured_allowlist() -> None:
    """The runtime policy never widens the configured origins implicitly."""
    cors = next(item for item in app.user_middleware if item.cls is CORSMiddleware)

    assert cors.kwargs["allow_origins"] == config.CORS_ALLOWED_ORIGINS
    assert "*" not in cors.kwargs["allow_origins"]


def test_cors_config_rejects_wildcard_origin() -> None:
    """A deployment cannot opt into wildcard CORS."""
    with pytest.raises(ValidationError, match="must not contain"):
        Config(
            ADMIN_API_KEY="a" * 32,
            DATABASE_URL="postgresql://localhost:5432/test",
            CORS_ALLOWED_ORIGINS=["*"],
        )


@pytest.mark.asyncio
@pytest.mark.require_auth
@pytest.mark.rate_limit
async def test_admin_login_is_rate_limited_by_source_and_username() -> None:
    """Repeated bad credentials consume the shared Redis login budget."""
    redis = _FixedWindowRedis()
    app.dependency_overrides[get_redis_client] = lambda: redis
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            responses = [
                await client.post(
                    "/api/auth/login",
                    json={"username": "admin", "password": "wrong"},
                )
                for _ in range(6)
            ]
    finally:
        app.dependency_overrides.pop(get_redis_client, None)

    assert [response.status_code for response in responses[:5]] == [401] * 5
    assert responses[5].status_code == 429
    assert responses[5].headers["Retry-After"] == "300"


@pytest.mark.asyncio
@pytest.mark.require_auth
@pytest.mark.rate_limit
async def test_admin_login_fails_closed_when_rate_limiter_is_unavailable() -> None:
    """A Redis outage cannot silently disable brute-force protection."""
    app.dependency_overrides[get_redis_client] = _UnavailableRedis
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/auth/login",
                json={"username": "admin", "password": "secret"},
            )
    finally:
        app.dependency_overrides.pop(get_redis_client, None)

    assert response.status_code == 503
    assert response.json()["detail"] == "Authentication temporarily unavailable"


@pytest.mark.asyncio
@pytest.mark.require_auth
@pytest.mark.rate_limit
@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/admin/mode", {"mode": "paper"}),
        ("/api/admin/killswitch", {}),
    ],
)
async def test_sensitive_admin_mutations_rate_limit_invalid_credentials(
    path: str,
    body: dict[str, str],
) -> None:
    """Authentication failures cannot bypass the per-source mutation budget."""
    redis = _FixedWindowRedis()
    app.dependency_overrides[get_redis_client] = lambda: redis
    redis_store = MagicMock()
    redis_store._r = redis
    app.dependency_overrides[get_redis_store] = lambda: redis_store
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            responses = [
                await client.post(
                    path,
                    json=body,
                    headers={"X-API-Key": "invalid"},
                )
                for _ in range(6)
            ]
    finally:
        app.dependency_overrides.pop(get_redis_client, None)
        app.dependency_overrides.pop(get_redis_store, None)

    assert [response.status_code for response in responses[:5]] == [403] * 5
    assert responses[5].status_code == 429
    assert responses[5].headers["Retry-After"] == "60"


@pytest.mark.asyncio
@pytest.mark.require_auth
@pytest.mark.rate_limit
async def test_sensitive_admin_mutation_fails_closed_without_limiter() -> None:
    """A Redis error blocks a mutation instead of silently removing its budget."""
    redis_store = MagicMock()
    app.dependency_overrides[get_redis_client] = _UnavailableRedis
    app.dependency_overrides[get_redis_store] = lambda: redis_store
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/admin/mode",
                json={"mode": "paper"},
                headers={"X-API-Key": "invalid"},
            )
    finally:
        app.dependency_overrides.pop(get_redis_client, None)
        app.dependency_overrides.pop(get_redis_store, None)

    assert response.status_code == 503
    assert response.json()["detail"] == "Rate limiter unavailable"
