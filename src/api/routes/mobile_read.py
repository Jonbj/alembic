"""Read-only mobile monitoring routes.

All endpoints live under /api/mobile/v1 and require a valid mobile access token.
They are intentionally read-only: no trading, strategy, config, or kill-switch
mutations are exposed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from packaging.version import Version

from src.api.dependencies import get_pool
from src.api.routes.mobile_auth import require_mobile_token
from src.config import config
from src.mobile_monitoring.builder import MobileEventStore, MobileSnapshotBuilder
from src.mobile_monitoring.models import (
    EventCategory,
    EventsResponse,
    MobileReadResponse,
    Period,
    PerformanceResponse,
    PositionsResponse,
    SnapshotResponse,
)

router = APIRouter(prefix="/read", tags=["mobile-read"])


def _request_id() -> UUID:
    return uuid4()


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
            raise HTTPException(
                status_code=status.HTTP_426_UPGRADE_REQUIRED,
                detail={
                    "error": {
                        "code": "upgrade_required",
                        "message": "App version is below the minimum supported version.",
                        "request_id": str(_request_id()),
                        "retryable": False,
                        "details": {
                            "app_version": app_version,
                            "min_supported_app_version": response.min_supported_app_version,
                            "latest_app_version": response.latest_app_version,
                        },
                    }
                },
            )
    except Exception:
        # Malformed version strings are ignored; the device will be prompted once it sends a valid version.
        pass


def _etag_for(response: MobileReadResponse) -> str:
    """Return a strong ETag for a read response."""
    body = response.model_dump_json()
    return f'"{hashlib.sha256(body.encode()).hexdigest()}"'


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


async def _builder(request: Request) -> MobileSnapshotBuilder:
    return MobileSnapshotBuilder(pool=await get_pool(request))


async def _event_store(request: Request) -> MobileEventStore:
    return MobileEventStore(pool=await get_pool(request))


@router.get("/snapshot", response_model=SnapshotResponse)
async def snapshot(
    request: Request,
    claims: dict = Depends(require_mobile_token),
    builder: MobileSnapshotBuilder = Depends(_builder),
) -> SnapshotResponse:
    try:
        resp = await builder.build_snapshot()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "snapshot_unavailable",
                    "message": f"Monitoring snapshot is temporarily unavailable: {exc}",
                    "request_id": str(_request_id()),
                    "retryable": True,
                    "details": {},
                }
            },
        ) from exc
    return _render_read_response(request, resp)


@router.get("/performance", response_model=PerformanceResponse)
async def performance(
    request: Request,
    period: str = "1m",
    claims: dict = Depends(require_mobile_token),
    builder: MobileSnapshotBuilder = Depends(_builder),
) -> PerformanceResponse:
    try:
        Period(period)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "invalid_period",
                    "message": f"Invalid period: {period}",
                    "request_id": str(_request_id()),
                    "retryable": False,
                    "details": {},
                }
            },
        ) from exc
    try:
        resp = await builder.build_performance(period=period)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "performance_unavailable",
                    "message": f"Performance data is temporarily unavailable: {exc}",
                    "request_id": str(_request_id()),
                    "retryable": True,
                    "details": {},
                }
            },
        ) from exc
    return _render_read_response(request, resp)


@router.get("/positions", response_model=PositionsResponse)
async def positions(
    request: Request,
    claims: dict = Depends(require_mobile_token),
    builder: MobileSnapshotBuilder = Depends(_builder),
) -> PositionsResponse:
    try:
        resp = await builder.build_positions()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "positions_unavailable",
                    "message": f"Positions are temporarily unavailable: {exc}",
                    "request_id": str(_request_id()),
                    "retryable": True,
                    "details": {},
                }
            },
        ) from exc
    return _render_read_response(request, resp)


@router.get("/events", response_model=EventsResponse)
async def events(
    request: Request,
    category: str = "all",
    days: int = 7,
    cursor: str | None = None,
    limit: int = 50,
    claims: dict = Depends(require_mobile_token),
    store: MobileEventStore = Depends(_event_store),
) -> EventsResponse:
    try:
        cat = EventCategory(category)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "invalid_category",
                    "message": f"Invalid category: {category}",
                    "request_id": str(_request_id()),
                    "retryable": False,
                    "details": {},
                }
            },
        ) from exc

    if not (1 <= days <= 90):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "invalid_days",
                    "message": "days must be between 1 and 90",
                    "request_id": str(_request_id()),
                    "retryable": False,
                    "details": {},
                }
            },
        )
    if not (1 <= limit <= 200):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "invalid_limit",
                    "message": "limit must be between 1 and 200",
                    "request_id": str(_request_id()),
                    "retryable": False,
                    "details": {},
                }
            },
        )

    try:
        items = await store.list_events(
            category=cat,
            days=days,
            cursor=cursor,
            limit=limit,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "events_unavailable",
                    "message": f"Event feed is temporarily unavailable: {exc}",
                    "request_id": str(_request_id()),
                    "retryable": True,
                    "details": {},
                }
            },
        ) from exc

    as_of = datetime.now(timezone.utc)
    next_cursor = None
    if len(items) > limit:
        # Not implemented: real cursor signing would go here.
        next_cursor = None

    resp = EventsResponse(
        as_of=as_of,
        data_age_seconds=0,
        currency="USD",
        min_supported_app_version=config.MIN_SUPPORTED_MOBILE_APP_VERSION,
        latest_app_version=config.LATEST_MOBILE_APP_VERSION,
        items=items[:limit],
        next_cursor=next_cursor,
    )
    return _render_read_response(request, resp)
