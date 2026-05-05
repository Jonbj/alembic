"""FastAPI application with lifespan for Redis connection management."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from redis import Redis

from src.api import deps
from src.config import config

# Re-export dependency functions so existing tests can still do:
#   from src.api.main import app, get_redis_store, get_pg_store
from src.api.deps import get_pg_store, get_redis_store  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Open Redis connection on startup, close on shutdown."""
    deps._redis_client = Redis.from_url(config.REDIS_URL)
    yield
    deps._redis_client.close()
    deps._redis_client = None


app = FastAPI(
    title="LLM Trading Signal API",
    description="Control plane for LLM-based algorithmic trading system",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "mode": "backtest"}


from src.api.routes import admin, performance, signals  # noqa: E402

app.include_router(signals.router)
app.include_router(admin.router)
app.include_router(performance.router)
