"""Rate-limit dependencies for security-sensitive API endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader
from redis import Redis, RedisError
from starlette.concurrency import run_in_threadpool

from src.api.auth import require_api_key
from src.api.deps import get_redis_client
from src.config import config
from src.rate_limit import FixedWindowRateLimiter

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _source(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


def get_admin_login_rate_limiter(
    redis: Annotated[Redis, Depends(get_redis_client)],
) -> FixedWindowRateLimiter:
    """Build the shared limiter for the browser-admin login boundary."""
    return FixedWindowRateLimiter(
        redis,
        namespace="api:auth:login",
        limit=config.API_LOGIN_RATE_LIMIT,
        window_seconds=config.API_LOGIN_RATE_WINDOW_SECONDS,
    )


def get_admin_action_rate_limiter(
    redis: Annotated[Redis, Depends(get_redis_client)],
) -> FixedWindowRateLimiter:
    """Build the shared limiter for security-sensitive admin mutations."""
    return FixedWindowRateLimiter(
        redis,
        namespace="api:admin:mutation",
        limit=config.API_ADMIN_ACTION_RATE_LIMIT,
        window_seconds=config.API_ADMIN_ACTION_RATE_WINDOW_SECONDS,
    )


async def require_rate_limited_admin(
    request: Request,
    limiter: Annotated[FixedWindowRateLimiter, Depends(get_admin_action_rate_limiter)],
    x_api_key: Annotated[str | None, Security(_api_key_header)],
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """Rate-limit a sensitive mutation before accepting admin credentials."""
    source = f"{request.method}:{request.url.path}:{_source(request)}"
    try:
        result = await run_in_threadpool(limiter.check, source=source)
    except RedisError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rate limiter unavailable",
        ) from None
    if not result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests",
            headers={"Retry-After": str(result.retry_after_seconds)},
        )
    return await require_api_key(
        x_api_key=x_api_key,
        authorization=authorization,
    )
