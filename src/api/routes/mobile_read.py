"""Read-only mobile monitoring routes.

All endpoints live under /api/mobile/v1 and require a valid mobile access token.
They are intentionally read-only: no trading, strategy, config, or kill-switch
mutations are exposed.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request, Response, status
from packaging.version import InvalidVersion, Version
from redis import Redis

from src.api.dependencies import get_pool
from src.api.deps import get_redis_client
from src.api.mobile_errors import MobileAPIError
from src.api.routes.mobile_auth import require_mobile_token
from src.config import config
from src.mobile_monitoring.events import CursorError, MobileEventStore
from src.mobile_monitoring.models import (
    EventCategory,
    EventsResponse,
    MobileReadResponse,
    Period,
    PerformanceResponse,
    PositionsResponse,
    SnapshotResponse,
)
from src.mobile_monitoring.performance import MobilePerformanceService
from src.mobile_monitoring.read_model import (
    MobileReadBundle,
    RedisMobileReadModelStore,
    ResilientMobileReadModelReader,
    UnsafeReadModelError,
    bundle_age_seconds,
    ensure_bundle_safe,
    load_mobile_read_model,
)
from src.portfolio.spy import load_cached_spy_closes

router = APIRouter(tags=["mobile-read"])
logger = logging.getLogger(__name__)


def _app_version(request: Request) -> str | None:
    """Read the caller's app version from the X-App-Version header."""
    return request.headers.get("x-app-version") or request.headers.get("X-App-Version")


def _check_app_version(request: Request, response: MobileReadResponse) -> None:
    """Raise 426 Upgrade Required if the caller's app version is below the minimum."""
    app_version = _app_version(request)
    if not app_version:
        return
    try:
        if Version(app_version) < Version(response.min_supported_app_version):
            raise MobileAPIError(
                status.HTTP_426_UPGRADE_REQUIRED,
                "upgrade_required",
                "App version is below the minimum supported version.",
                details={
                    "app_version": app_version,
                    "min_supported_app_version": response.min_supported_app_version,
                    "latest_app_version": response.latest_app_version,
                },
            )
    except InvalidVersion:
        # Malformed version strings are ignored; the device will be prompted once it sends a valid version.
        pass


def _etag_for(response: MobileReadResponse) -> str:
    """Return a weak validator for domain data, excluding volatile age metadata."""
    body = json.dumps(
        response.model_dump(
            mode="json",
            exclude={"as_of", "data_age_seconds"},
        ),
        sort_keys=True,
        separators=(",", ":"),
    )
    return f'W/"{hashlib.sha256(body.encode()).hexdigest()}"'


def _render_read_response(
    request: Request,
    response: MobileReadResponse,
    extra_headers: dict[str, str] | None = None,
) -> Response:
    """Apply app-version gate and ETag/If-None-Match handling."""
    _check_app_version(request, response)
    etag = _etag_for(response)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
    if extra_headers:
        headers.update(extra_headers)
    return Response(
        content=response.model_dump_json(),
        media_type="application/json",
        headers=headers,
    )


async def _read_model(
    request: Request,
    redis: Redis = Depends(get_redis_client),
) -> ResilientMobileReadModelReader:
    """Return the Redis-first reader with a durable PostgreSQL fallback."""
    return ResilientMobileReadModelReader(
        RedisMobileReadModelStore(redis),
        await get_pool(request),
    )


async def _event_store(request: Request) -> MobileEventStore:
    return MobileEventStore(pool=await get_pool(request))


async def _performance_service(
    request: Request,
    redis: Redis = Depends(get_redis_client),
) -> MobilePerformanceService:
    """Build the DB/cache projection with broker-free cached SPY enrichment."""
    pool = await get_pool(request)
    return MobilePerformanceService(
        pool,
        ResilientMobileReadModelReader(
            RedisMobileReadModelStore(redis),
            pool,
        ),
        spy_loader=lambda start, end: load_cached_spy_closes(
            start,
            end,
            redis,
        ),
    )


async def _load_bundle(store: Any) -> MobileReadBundle:
    """Load one safe coherent bundle without contacting broker dependencies."""
    try:
        bundle = await load_mobile_read_model(store)
    except Exception as exc:
        logger.exception("Mobile snapshot read-model load failed")
        raise MobileAPIError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "snapshot_unavailable",
            "Monitoring snapshot is temporarily unavailable.",
            retryable=True,
        ) from exc
    if bundle is None:
        raise MobileAPIError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "snapshot_unavailable",
            "Monitoring snapshot is temporarily unavailable.",
            retryable=True,
        )
    try:
        ensure_bundle_safe(bundle)
    except UnsafeReadModelError as exc:
        raise MobileAPIError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "snapshot_unavailable",
            "Monitoring snapshot is temporarily unavailable.",
            retryable=True,
            details={"data_age_seconds": exc.age_seconds},
        ) from exc
    return bundle


@router.get("/snapshot", response_model=SnapshotResponse)
async def snapshot(
    request: Request,
    claims: dict[str, Any] = Depends(require_mobile_token),
    store: Any = Depends(_read_model),
) -> Response:
    """Return the latest coherent monitoring snapshot without broker fan-out."""
    del claims
    bundle = await _load_bundle(store)
    resp = bundle.snapshot.model_copy(
        update={"data_age_seconds": bundle_age_seconds(bundle)}
    )
    return _render_read_response(request, resp)


@router.get("/performance", response_model=PerformanceResponse)
async def performance(
    request: Request,
    period: str = "1m",
    claims: dict[str, Any] = Depends(require_mobile_token),
    service: MobilePerformanceService = Depends(_performance_service),
) -> Response:
    """Return NAV performance for one approved period."""
    del claims
    try:
        Period(period)
    except ValueError as exc:
        raise MobileAPIError(
            status.HTTP_400_BAD_REQUEST,
            "invalid_period",
            f"Invalid period: {period}",
        ) from exc
    try:
        resp = await service.build(period=period)
    except Exception as exc:
        logger.exception("Mobile performance projection failed")
        raise MobileAPIError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "performance_unavailable",
            "Performance data is temporarily unavailable.",
            retryable=True,
        ) from exc
    return _render_read_response(request, resp)


@router.get("/positions", response_model=PositionsResponse)
async def positions(
    request: Request,
    claims: dict[str, Any] = Depends(require_mobile_token),
    read_model: Any = Depends(_read_model),
) -> Response:
    """Return positions derived from the same broker read as the snapshot."""
    del claims
    bundle = await _load_bundle(read_model)
    resp = bundle.positions.model_copy(
        update={"data_age_seconds": bundle_age_seconds(bundle)}
    )
    return _render_read_response(request, resp)


@router.get("/events", response_model=EventsResponse)
async def events(
    request: Request,
    category: str = "all",
    days: int = 7,
    cursor: str | None = None,
    limit: int = 50,
    claims: dict[str, Any] = Depends(require_mobile_token),
    store: MobileEventStore = Depends(_event_store),
) -> Response:
    """Return the safe operator event feed with signed keyset pagination."""
    del claims
    try:
        cat = EventCategory(category)
    except ValueError as exc:
        raise MobileAPIError(
            status.HTTP_400_BAD_REQUEST,
            "invalid_category",
            f"Invalid category: {category}",
        ) from exc

    if not (1 <= days <= 30):
        raise MobileAPIError(
            status.HTTP_400_BAD_REQUEST,
            "invalid_days",
            "days must be between 1 and 30",
        )
    if not (1 <= limit <= 200):
        raise MobileAPIError(
            status.HTTP_400_BAD_REQUEST,
            "invalid_limit",
            "limit must be between 1 and 200",
        )

    try:
        page = await store.list_events(
            category=cat,
            days=days,
            cursor=cursor,
            limit=limit,
        )
    except CursorError as exc:
        raise MobileAPIError(
            status.HTTP_400_BAD_REQUEST,
            "invalid_cursor",
            "Invalid event cursor",
        ) from exc
    except Exception as exc:
        logger.exception("Mobile event projection failed")
        raise MobileAPIError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "events_unavailable",
            "Event feed is temporarily unavailable.",
            retryable=True,
        ) from exc

    as_of = datetime.now(timezone.utc)

    resp = EventsResponse(
        as_of=as_of,
        data_age_seconds=0,
        currency="USD",
        min_supported_app_version=config.MIN_SUPPORTED_MOBILE_APP_VERSION,
        latest_app_version=config.LATEST_MOBILE_APP_VERSION,
        items=page.items,
        next_cursor=page.next_cursor,
    )
    return _render_read_response(request, resp)
