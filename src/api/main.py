"""FastAPI application with lifespan for Redis connection management."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from redis import Redis

from src.config import config
from src.store.redis_store import RedisStore

_redis_client: Redis | None = None


def get_redis_store() -> RedisStore:
    """Get RedisStore instance using the global Redis client.

    Returns:
        RedisStore instance for signal read/write operations
    """
    if _redis_client is None:
        raise RuntimeError("Redis client not initialized - lifespan context not active")
    return RedisStore(_redis_client)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager for Redis connection lifecycle.

    Opens Redis connection on startup and closes it on shutdown.
    """
    global _redis_client
    _redis_client = Redis.from_url(config.REDIS_URL)
    yield
    _redis_client.close()


app = FastAPI(
    title="LLM Trading Signal API",
    description="Control plane for LLM-based algorithmic trading system",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/api/health")
async def health() -> dict[str, str]:
    """Health check endpoint.

    Returns:
        Status and current operating mode
    """
    return {"status": "ok", "mode": "backtest"}


# Import and include routers after app creation to avoid circular imports
from src.api.routes import admin, performance, signals

app.include_router(signals.router)
app.include_router(admin.router)
app.include_router(performance.router)
