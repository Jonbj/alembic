"""Mobile monitoring authentication routes.

Read-only monitor boundary: endpoints only create/rotate/delete mobile sessions.
No trading, admin, strategy, or labeling mutations are allowed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import bcrypt
from fastapi import APIRouter, Depends, Request, status
from redis import Redis, RedisError
from starlette.concurrency import run_in_threadpool

from src.api.dependencies import get_pool
from src.api.deps import get_redis_client
from src.api.mobile_errors import MobileAPIError
from src.api.mobile_models import (
    DeviceRegistrationRequest,
    DeviceRegistrationResponse,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    RefreshRequest,
    UserInfo,
)
from src.config import config
from src.mobile_monitoring.auth import (
    MobileAudienceError,
    MobileScopeError,
    create_mobile_access_token,
    create_session_family,
    decode_mobile_access_token,
    generate_refresh_token,
    hash_refresh_token,
    parse_uuid_claim,
)
from src.mobile_monitoring.models import DeviceResponse
from src.mobile_monitoring.rate_limit import MobileLoginRateLimiter
from src.mobile_monitoring.store import (
    MonitorDevice,
    MonitorPrincipalInactiveError,
    MonitorSession,
    MonitorStore,
    MonitorUser,
    RefreshExpiredError,
    ReplayDetectedError,
)

router = APIRouter(prefix="/auth", tags=["mobile-auth"])
device_router = APIRouter(prefix="/devices", tags=["mobile-devices"])
logger = logging.getLogger(__name__)
_DUMMY_PASSWORD_HASH = "$2b$12$xyOVls3LO38NjY8mXVN1Q.En.tz32WUD0b2LsJUd6ANr8En/DbJCC"


def _verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


async def _store(request: Request) -> MonitorStore:
    return MonitorStore(await get_pool(request))


def get_login_rate_limiter(
    redis: Redis = Depends(get_redis_client),
) -> MobileLoginRateLimiter:
    """Build the shared Redis-backed mobile login limiter."""
    return MobileLoginRateLimiter(
        redis,
        limit=config.MOBILE_LOGIN_RATE_LIMIT,
        window_seconds=config.MOBILE_LOGIN_RATE_WINDOW_SECONDS,
    )


async def require_mobile_token(
    request: Request,
) -> dict[str, Any]:
    """Dependency: validate mobile access token from Authorization header.

    In addition to JWT signature/audience/scope/expiry checks, the token's JTI
    must map to an active monitor session. Family-wide revocation therefore
    immediately invalidates outstanding access tokens.
    """
    auth = request.headers.get("authorization", "")
    if not auth or not auth.lower().startswith("bearer "):
        raise MobileAPIError(
            status.HTTP_401_UNAUTHORIZED,
            "authentication_required",
            "Missing bearer token",
        )
    token = auth[7:].strip()
    try:
        claims = decode_mobile_access_token(token)
        jti = parse_uuid_claim(claims, "jti")
        user_id = parse_uuid_claim(claims, "sub")
        device_id = parse_uuid_claim(claims, "device_id")
    except MobileScopeError as exc:
        raise MobileAPIError(
            status.HTTP_403_FORBIDDEN,
            "insufficient_scope",
            "Missing monitor:read scope",
        ) from exc
    except MobileAudienceError as exc:
        raise MobileAPIError(
            status.HTTP_403_FORBIDDEN,
            "invalid_audience",
            "Token is not intended for the mobile API",
        ) from exc
    except Exception as exc:
        raise MobileAPIError(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_access_token",
            "Invalid access token",
        ) from exc

    store = MonitorStore(await get_pool(request))
    session = await store.get_session_by_access_jti(jti)
    if (
        session is None
        or session.revoked_at is not None
        or session.user_id != user_id
        or session.device_id != device_id
    ):
        raise MobileAPIError(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_session",
            "Invalid session",
        )

    return claims


async def require_mobile_device_token(
    claims: dict[str, Any] = Depends(require_mobile_token),
) -> dict[str, Any]:
    """Require the explicit scope used by device registration and revocation."""
    if "monitor:device" not in claims.get("scope", []):
        raise MobileAPIError(
            status.HTTP_403_FORBIDDEN,
            "insufficient_scope",
            "Missing monitor:device scope",
        )
    return claims


def _response(
    user: MonitorUser,
    device: MonitorDevice,
    session: MonitorSession,
    access_token: str,
    refresh_token: str,
) -> LoginResponse:
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=config.MOBILE_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        refresh_token=refresh_token,
        refresh_expires_at=session.expires_at,
        user=UserInfo(id=user.id, username=user.username),
        device_id=device.id,
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    body: LoginRequest,
    limiter: MobileLoginRateLimiter = Depends(get_login_rate_limiter),
) -> LoginResponse:
    """Authenticate a provisioned monitor user and create a device session."""
    source = request.client.host if request.client is not None else "unknown"
    try:
        rate_limit = await run_in_threadpool(limiter.check, body.username, source)
    except RedisError:
        logger.exception("Mobile login rate limiter unavailable")
        raise MobileAPIError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "authentication_unavailable",
            "Authentication temporarily unavailable",
            retryable=True,
        ) from None
    if not rate_limit.allowed:
        raise MobileAPIError(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "rate_limited",
            "Too many login attempts",
            retryable=True,
            headers={"Retry-After": str(rate_limit.retry_after_seconds)},
        )

    store = await _store(request)
    user = await store.get_user_by_username(body.username)
    password_valid = await run_in_threadpool(
        _verify_password,
        body.password,
        user.password_hash if user is not None else _DUMMY_PASSWORD_HASH,
    )
    if user is None or not user.enabled or not password_valid:
        raise MobileAPIError(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_credentials",
            "Invalid credentials",
        )

    installation_id = str(body.device.installation_id)
    device = await store.get_device_by_installation(user.id, installation_id)

    if device is not None and device.revoked_at is not None:
        raise MobileAPIError(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_credentials",
            "Invalid credentials",
        )

    if device is None:
        device = await store.create_device(
            user_id=user.id,
            installation_id=installation_id,
            name=body.device.name,
            app_version=body.device.app_version,
        )

    await store.update_device(device.id, last_seen_at=datetime.now(timezone.utc))

    family_id = create_session_family()
    raw_refresh = generate_refresh_token()
    access_jti = uuid4()
    try:
        session = await store.create_login_session_atomic(
            user_id=user.id,
            device_id=device.id,
            refresh_hash=hash_refresh_token(raw_refresh),
            family_id=family_id,
            access_jti=access_jti,
        )
    except MonitorPrincipalInactiveError:
        raise MobileAPIError(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_credentials",
            "Invalid credentials",
        ) from None

    access_token = create_mobile_access_token(
        user_id=user.id,
        device_id=device.id,
        jti=access_jti,
    )

    return _response(user, device, session, access_token, raw_refresh)


@router.post("/refresh", response_model=LoginResponse)
async def refresh(request: Request, body: RefreshRequest) -> LoginResponse:
    """Rotate one refresh token and issue a new device-bound session."""
    store = await _store(request)
    old_hash = hash_refresh_token(body.refresh_token)
    old_session = await store.get_session_by_refresh_hash(old_hash)

    # Reuse of an already-rotated or revoked refresh token revokes the entire
    # family atomically. The error message only claims revocation when we have
    # successfully issued the revocation query.
    if old_session is None:
        raise MobileAPIError(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_refresh_token",
            "Invalid refresh token",
        )
    if old_session.revoked_at is not None:
        user = await store.get_user(old_session.user_id)
        device = (
            await store.get_device(old_session.device_id)
            if old_session.device_id
            else None
        )
        if (
            user is None
            or not user.enabled
            or device is None
            or device.revoked_at is not None
        ):
            raise MobileAPIError(
                status.HTTP_401_UNAUTHORIZED,
                "principal_inactive",
                "User or device inactive",
            )
        await store.revoke_family(old_session.family_id)
        raise MobileAPIError(
            status.HTTP_409_CONFLICT,
            "refresh_reuse",
            "Refresh token reuse detected; all family sessions revoked",
        )

    user = await store.get_user(old_session.user_id)
    device = (
        await store.get_device(old_session.device_id) if old_session.device_id else None
    )

    new_refresh = generate_refresh_token()
    access_jti = uuid4()
    try:
        new_session = await store.rotate_session_atomic(
            old_session,
            hash_refresh_token(new_refresh),
            access_jti=access_jti,
        )
    except ReplayDetectedError:
        # Atomic rotation already revoked the whole family before raising.
        raise MobileAPIError(
            status.HTTP_409_CONFLICT,
            "refresh_reuse",
            "Refresh token replay detected; all family sessions revoked",
        ) from None
    except RefreshExpiredError:
        raise MobileAPIError(
            status.HTTP_401_UNAUTHORIZED,
            "refresh_expired",
            "Refresh token expired",
        ) from None
    except MonitorPrincipalInactiveError:
        raise MobileAPIError(
            status.HTTP_401_UNAUTHORIZED,
            "principal_inactive",
            "User or device inactive",
        ) from None
    except Exception:
        # Any other failure rolled back the atomic transaction; do not claim
        # revocation occurred and do not expose internal details.
        logger.exception("Mobile refresh-token rotation failed")
        raise MobileAPIError(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "rotation_failed",
            "Token rotation failed",
            retryable=True,
        ) from None

    if user is None or device is None:
        await store.revoke_family(old_session.family_id)
        raise MobileAPIError(
            status.HTTP_401_UNAUTHORIZED,
            "principal_inactive",
            "User or device inactive",
        )

    access_token = create_mobile_access_token(
        user_id=user.id,
        device_id=device.id,
        jti=access_jti,
    )

    return _response(user, device, new_session, access_token, new_refresh)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    body: LogoutRequest,
    claims: dict[str, Any] = Depends(require_mobile_token),
) -> None:
    """Revoke every active session for the authenticated device."""
    store = await _store(request)
    refresh_hash = hash_refresh_token(body.refresh_token)
    session = await store.get_session_by_refresh_hash(refresh_hash)
    user_id = parse_uuid_claim(claims, "sub")
    device_id = parse_uuid_claim(claims, "device_id")
    if session is not None and (
        session.user_id != user_id or session.device_id != device_id
    ):
        raise MobileAPIError(
            status.HTTP_403_FORBIDDEN,
            "token_mismatch",
            "Token mismatch",
        )
    # Session invalidation is authoritative; clearing push registration is
    # cleanup and must not turn a completed logout into a client-visible error.
    await store.revoke_all_sessions_for_device(user_id, device_id)
    try:
        await store.clear_device_push_registration(device_id)
    except Exception:
        logger.exception("Mobile logout push-registration cleanup failed")


@device_router.post("", response_model=DeviceRegistrationResponse)
async def register_device(
    request: Request,
    body: DeviceRegistrationRequest,
    claims: dict[str, Any] = Depends(require_mobile_device_token),
) -> DeviceRegistrationResponse:
    """Register or update a notification device owned by the monitor user."""
    store = await _store(request)
    user_id = parse_uuid_claim(claims, "sub")

    installation_id = str(body.installation_id)
    existing = await store.get_device_by_installation(user_id, installation_id)

    if existing is None:
        device = await store.create_device(
            user_id=user_id,
            installation_id=installation_id,
            name=body.name,
            app_version=body.app_version,
            firebase_installation_id=body.firebase_installation_id,
            push_enabled=body.push_enabled,
        )
    else:
        await store.update_device(
            existing.id,
            name=body.name,
            app_version=body.app_version,
            firebase_installation_id=body.firebase_installation_id,
            push_enabled=body.push_enabled,
            last_seen_at=datetime.now(timezone.utc),
        )
        updated_device = await store.get_device(existing.id)
        if updated_device is None:
            raise MobileAPIError(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "device_update_failed",
                "Device update failed",
                retryable=True,
            )
        device = updated_device

    return DeviceRegistrationResponse(
        device=DeviceResponse(
            id=device.id,
            installation_id=device.installation_id,
            firebase_installation_id=device.firebase_installation_id,
            name=device.name,
            app_version=device.app_version,
            push_enabled=device.push_enabled,
            created_at=device.created_at,
            last_seen_at=device.last_seen_at,
        )
    )


@device_router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_device(
    device_id: UUID,
    request: Request,
    claims: dict[str, Any] = Depends(require_mobile_device_token),
) -> None:
    """Revoke an owned device and all access/refresh sessions bound to it."""
    store = await _store(request)
    user_id = parse_uuid_claim(claims, "sub")
    device = await store.get_device(device_id)
    if device is None or device.user_id != user_id:
        raise MobileAPIError(
            status.HTTP_404_NOT_FOUND,
            "device_not_found",
            "Device not found",
        )
    await store.revoke_device(device_id)


@router.get("/me", response_model=UserInfo)
async def me(
    request: Request,
    claims: dict[str, Any] = Depends(require_mobile_token),
) -> UserInfo:
    """Return the authenticated monitor identity."""
    store = await _store(request)
    user = await store.get_user(parse_uuid_claim(claims, "sub"))
    if user is None:
        raise MobileAPIError(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_session",
            "Invalid session",
        )
    return UserInfo(id=user.id, username=user.username)
