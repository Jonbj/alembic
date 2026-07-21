"""Mobile monitoring authentication routes.

Read-only monitor boundary: endpoints only create/rotate/delete mobile sessions.
No trading, admin, strategy, or labeling mutations are allowed.
"""

from __future__ import annotations

from datetime import datetime, timezone

import bcrypt
from fastapi import APIRouter, HTTPException, Request, status

from src.api.dependencies import get_pool
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
    create_mobile_access_token,
    create_session_family,
    decode_mobile_access_token,
    generate_refresh_token,
    hash_refresh_token,
    parse_uuid_claim,
)
from src.mobile_monitoring.models import DeviceResponse
from src.mobile_monitoring.store import MonitorStore

router = APIRouter(prefix="/auth", tags=["mobile-auth"])

async def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


async def _verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


async def _store(request: Request) -> MonitorStore:
    return MonitorStore(await get_pool(request))


async def _require_mobile_token(request: Request) -> dict:
    """Dependency: validate mobile access token from Authorization header."""
    auth = request.headers.get("authorization", "")
    if not auth or not auth.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = auth[7:].strip()
    try:
        claims = decode_mobile_access_token(token)
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    return claims


def _response(user, device, session, access_token: str, refresh_token: str) -> LoginResponse:
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
) -> LoginResponse:
    store = await _store(request)
    user = await store.get_user_by_username(body.username)
    if user is None or not user.enabled:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not await _verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    installation_id = str(body.device.installation_id)
    device = await store.get_device_by_installation(user.id, installation_id)

    if device is not None and device.revoked_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Device revoked")

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
    session = await store.create_session(
        user_id=user.id,
        device_id=device.id,
        refresh_hash=hash_refresh_token(raw_refresh),
        family_id=family_id,
    )

    access_token = create_mobile_access_token(
        user_id=user.id,
        device_id=device.id,
    )

    return _response(user, device, session, access_token, raw_refresh)


@router.post("/refresh", response_model=LoginResponse)
async def refresh(request: Request, body: RefreshRequest) -> LoginResponse:
    store = await _store(request)
    old_hash = hash_refresh_token(body.refresh_token)
    old_session = await store.get_session_by_refresh_hash(old_hash)

    if old_session is None or old_session.revoked_at is not None:
        known = await store.pool.fetchrow(
            "SELECT id FROM monitor_sessions WHERE refresh_token_hash=$1", old_hash
        )
        if known:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Refresh token reuse detected; session revoked",
            )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")

    if old_session.expires_at < datetime.now(timezone.utc):
        await store.revoke_session(old_session.id)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token expired")

    user = await store.get_user(old_session.user_id)
    device = await store.get_device(old_session.device_id) if old_session.device_id else None
    if user is None or not user.enabled or device is None or device.revoked_at is not None:
        await store.revoke_session(old_session.id)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User or device inactive")

    # Replay detection: any later active session in the same family means this token
    # was already consumed.
    active_same_family = await store.pool.fetchval(
        """
        SELECT COUNT(*) FROM monitor_sessions
        WHERE family_id=$1 AND created_at > $2 AND revoked_at IS NULL
        """,
        old_session.family_id,
        old_session.created_at,
    )
    if active_same_family:
        await store.revoke_all_sessions_for_device(user.id, device.id)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Refresh token replay detected; device sessions revoked",
        )

    new_refresh = generate_refresh_token()
    new_session = await store.rotate_session(
        old_session,
        hash_refresh_token(new_refresh),
    )
    await store.mark_session_used(new_session.id)

    access_token = create_mobile_access_token(
        user_id=user.id,
        device_id=device.id,
    )

    return _response(user, device, new_session, access_token, new_refresh)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, body: LogoutRequest) -> None:
    claims = await _require_mobile_token(request)
    store = await _store(request)
    refresh_hash = hash_refresh_token(body.refresh_token)
    session = await store.get_session_by_refresh_hash(refresh_hash)
    user_id = parse_uuid_claim(claims, "sub")
    device_id = parse_uuid_claim(claims, "device_id")
    if session is not None and (session.user_id != user_id or session.device_id != device_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Token mismatch")
    # Revoke the whole device family for the authenticated device.
    await store.revoke_all_sessions_for_device(user_id, device_id)


@router.post("/devices", response_model=DeviceRegistrationResponse)
async def register_device(
    request: Request,
    body: DeviceRegistrationRequest,
) -> DeviceRegistrationResponse:
    claims = await _require_mobile_token(request)
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
        device = await store.get_device(existing.id)
        if device is None:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Device update failed")

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


@router.get("/me", response_model=UserInfo)
async def me(request: Request) -> UserInfo:
    claims = await _require_mobile_token(request)
    store = await _store(request)
    user = await store.get_user(parse_uuid_claim(claims, "sub"))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return UserInfo(id=user.id, username=user.username)
