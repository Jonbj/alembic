"""Async dependency factories for /api/mobile/v1 routes."""
from __future__ import annotations

import os
from typing import Optional

import asyncpg
from fastapi import HTTPException, Request

from src.config import config

_asyncpg_pool: Optional[asyncpg.Pool] = None


def _asyncpg_dsn() -> str:
    """Return the current DATABASE_URL, preferring the environment variable.

    This lets test conftests override the DSN after `src.config` has already
    been imported, without mutating the frozen Config instance.
    """
    return os.environ.get("DATABASE_URL") or str(config.DATABASE_URL)


async def init_asyncpg_pool() -> asyncpg.Pool:
    """Create and cache the async Postgres pool used by mobile routes."""
    global _asyncpg_pool
    if _asyncpg_pool is None:
        _asyncpg_pool = await asyncpg.create_pool(
            dsn=_asyncpg_dsn(),
            min_size=1,
            max_size=10,
        )
    return _asyncpg_pool


async def close_asyncpg_pool() -> None:
    """Close the cached async Postgres pool."""
    global _asyncpg_pool
    if _asyncpg_pool is not None:
        await _asyncpg_pool.close()
        _asyncpg_pool = None


async def get_pool(request: Request) -> asyncpg.Pool:
    """FastAPI dependency: async Postgres pool for mobile monitoring endpoints."""
    try:
        return await init_asyncpg_pool()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}") from exc
