"""Regression tests for API CORS and rate-limit hardening (#43)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import MagicMock

from src.api.deps import get_redis_client, get_redis_store
from src.api.main import app


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


@pytest.mark.asyncio
@pytest.mark.require_auth
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
