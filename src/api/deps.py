"""FastAPI dependency factories (shared by routes, avoids circular import with main.py)."""
from __future__ import annotations

from typing import Optional

from redis import Redis

_redis_client: Optional[Redis] = None


def get_redis_store():
    """FastAPI dependency: RedisStore backed by the app-lifecycle Redis client."""
    from src.store.redis_store import RedisStore
    if _redis_client is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Cache unavailable")
    return RedisStore(_redis_client)


def get_pg_store():
    """FastAPI dependency: PostgreSQLStore (new connection from pool per request)."""
    from src.store.pg_store import PostgreSQLStore
    return PostgreSQLStore()
