"""FastAPI application with lifespan for Redis connection management."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from redis import Redis

from src.api.deps import close_redis, get_pg_store, get_redis_store, init_redis  # noqa: F401
from src.config import config


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Open Redis connection on startup, close on shutdown."""
    init_redis(Redis.from_url(config.REDIS_URL))
    yield
    close_redis()


app = FastAPI(
    title="LLM Trading Signal API",
    description="Control plane for LLM-based algorithmic trading system",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "mode": "backtest"}


from src.api.routes import admin, backtest, config_routes, llm_routes, news_routes, performance, signals, trading  # noqa: E402

app.include_router(signals.router)
app.include_router(admin.router)
app.include_router(performance.router)
app.include_router(trading.router)
app.include_router(news_routes.router)
app.include_router(llm_routes.router)
app.include_router(config_routes.router)
app.include_router(backtest.router)

import os  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

_frontend_dist = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
if os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
