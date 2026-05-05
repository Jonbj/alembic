"""FastAPI dependency factories (shared by routes, avoids circular import with main.py)."""
from __future__ import annotations

from typing import Optional

from redis import Redis

_redis_client: Optional[Redis] = None


def init_redis(client: Redis) -> None:
    """Store the app-lifecycle Redis client (called from lifespan startup)."""
    global _redis_client
    _redis_client = client


def close_redis() -> None:
    """Close the Redis client and clear the reference (called from lifespan shutdown)."""
    global _redis_client
    if _redis_client is not None:
        _redis_client.close()
        _redis_client = None


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
