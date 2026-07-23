"""FastAPI application with lifespan for Redis connection management."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Awaitable, Callable
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from jose import JWTError, jwt
from redis import Redis

from src.api.dependencies import close_asyncpg_pool, init_asyncpg_pool  # noqa: F401
from src.api.deps import (  # noqa: F401
    close_redis,
    get_pg_store,
    get_redis_store,
    init_redis,
)
from src.api.jwt_utils import _secret
from src.api.mobile_errors import MobileAPIError, render_mobile_error
from src.config import config

_MOBILE_AUDIENCE = "alembic-mobile"
_MOBILE_PREFIX = "/api/mobile/v1"
_SAFE_HTTP_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_ALLOWED_MOBILE_WRITES = frozenset(
    {
        ("POST", "/api/mobile/v1/auth/login"),
        ("POST", "/api/mobile/v1/auth/refresh"),
        ("POST", "/api/mobile/v1/auth/logout"),
        ("POST", "/api/mobile/v1/devices"),
    }
)


def _is_allowed_mobile_write(method: str, path: str) -> bool:
    """Return whether an unsafe mobile method/path is explicitly classified."""
    if (method, path) in _ALLOWED_MOBILE_WRITES:
        return True
    prefix = "/api/mobile/v1/devices/"
    if method != "DELETE" or not path.startswith(prefix):
        return False
    device_id = path.removeprefix(prefix)
    if "/" in device_id:
        return False
    try:
        UUID(device_id)
    except ValueError:
        return False
    return True


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Open Redis connection on startup, close on shutdown."""
    if not config.JWT_SECRET_KEY:
        raise RuntimeError(
            "JWT_SECRET_KEY is not set. Refusing to start with an ephemeral key — "
            "tokens would differ across workers and be invalidated on every restart. "
            "Set the JWT_SECRET_KEY environment variable to a strong random secret "
            "(e.g. `openssl rand -hex 32`)."
        )
    init_redis(Redis.from_url(config.REDIS_URL))
    await init_asyncpg_pool()
    yield
    await close_asyncpg_pool()
    close_redis()


app = FastAPI(
    title="LLM Trading Signal API",
    description="Control plane for LLM-based algorithmic trading system",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(MobileAPIError)
async def mobile_api_error_handler(
    request: Request,
    error: MobileAPIError,
) -> JSONResponse:
    """Render the stable error contract for versioned mobile endpoints."""
    del request
    return render_mobile_error(error)


@app.exception_handler(RequestValidationError)
async def mobile_validation_error_handler(
    request: Request,
    error: RequestValidationError,
) -> Response:
    """Use the mobile envelope for invalid v1 input without changing admin APIs."""
    if request.url.path.startswith(f"{_MOBILE_PREFIX}/"):
        return render_mobile_error(
            MobileAPIError(
                400,
                "invalid_request",
                "Invalid request",
            )
        )
    return await request_validation_exception_handler(request, error)


@app.middleware("http")
async def mobile_token_boundary(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Keep mobile JWTs inside the explicitly read-only mobile boundary.

    Safe methods are permitted only below the mobile prefix. Mobile mutations
    fail closed unless their exact method/path pair is in the reviewed auth
    allowlist. Rejection happens before routing, so a forgotten dependency on a
    future endpoint cannot create a mutation path for mobile credentials.
    """
    path = request.url.path
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        try:
            payload = jwt.decode(
                token,
                _secret(),
                algorithms=[config.JWT_ALGORITHM],
                audience=_MOBILE_AUDIENCE,
            )
            audience = payload.get("aud")
            is_mobile_token = audience == _MOBILE_AUDIENCE or (
                isinstance(audience, list) and _MOBILE_AUDIENCE in audience
            )
            inside_mobile_api = path.startswith(f"{_MOBILE_PREFIX}/")
            permitted = inside_mobile_api and (
                request.method in _SAFE_HTTP_METHODS
                or _is_allowed_mobile_write(request.method, path)
            )
            if is_mobile_token and not permitted:
                return render_mobile_error(
                    MobileAPIError(
                        403,
                        "mobile_boundary_violation",
                        "Mobile token cannot access this resource",
                    )
                )
        except JWTError:
            pass
    return await call_next(request)


@app.get("/api/health")
async def health() -> dict[str, str]:
    """Return the API liveness state."""
    return {"status": "ok", "mode": "backtest"}


from src.api.routes import (  # noqa: E402
    admin,
    auth,
    backtest,
    config_routes,
    labeling_routes,
    llm_routes,
    mobile_auth,
    mobile_read,
    news_routes,
    performance,
    portfolio,
    quality_routes,
    signals,
    strategies,
    system_routes,
    trading,
    validation_routes,
)

app.include_router(auth.router)
app.include_router(mobile_auth.router, prefix="/api/mobile/v1")
app.include_router(mobile_auth.device_router, prefix="/api/mobile/v1")
app.include_router(mobile_read.router, prefix="/api/mobile/v1")
app.include_router(signals.router)
app.include_router(admin.router)
app.include_router(performance.router)
app.include_router(trading.router)
app.include_router(news_routes.router)
app.include_router(llm_routes.router)
app.include_router(config_routes.router)
app.include_router(backtest.router)
app.include_router(strategies.router)
app.include_router(portfolio.router)
app.include_router(system_routes.router)
app.include_router(validation_routes.router)
app.include_router(labeling_routes.router)
app.include_router(quality_routes.router)

import os  # noqa: E402

from fastapi.staticfiles import StaticFiles  # noqa: E402

_frontend_dist = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
if os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
