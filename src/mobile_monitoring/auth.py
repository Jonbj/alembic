"""Mobile monitor authentication helpers.

- Short-lived access JWTs with audience, type, scope, device, and JTI claims.
- Opaque refresh tokens that rotate, are stored only as hashes, and detect family
  reuse. Token plaintext never appears in logs.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from uuid import UUID, uuid4

from jose import JWTError, jwt

from src.config import config

_MOBILE_AUDIENCE = "alembic-mobile"
_ACCESS_TYPE = "access"


class MobileScopeError(JWTError):
    """Raised when a valid mobile token lacks a required monitor scope."""


class MobileAudienceError(JWTError):
    """Raised when a validly signed identity is not intended for mobile."""


def _secret() -> str:
    """Return the configured JWT secret (same signing key as admin tokens)."""
    from src.api.jwt_utils import _secret as admin_secret

    return admin_secret()


def _pepper() -> bytes:
    """Optional pepper bytes for refresh-token hashing."""
    pepper = config.MOBILE_TOKEN_PEPPER
    return pepper.encode() if pepper else b""


def hash_refresh_token(raw_token: str) -> str:
    """Return a deterministic, opaque hash of a refresh token for DB storage."""
    return hashlib.sha256(_pepper() + raw_token.encode()).hexdigest()


def generate_refresh_token() -> str:
    """Generate a URL-safe opaque token with at least 256 bits of entropy."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")


def create_session_family() -> UUID:
    """Create a new refresh-token family id."""
    return uuid4()


def create_mobile_access_token(
    *,
    user_id: UUID,
    device_id: UUID,
    scopes: list[str] | None = None,
    jti: UUID | None = None,
    expires_minutes: int | None = None,
) -> str:
    """Issue a mobile access token."""
    if scopes is None:
        scopes = ["monitor:read", "monitor:device"]
    jti = jti or uuid4()
    expire_minutes = (
        config.MOBILE_ACCESS_TOKEN_EXPIRE_MINUTES
        if expires_minutes is None
        else expires_minutes
    )
    expire = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    payload = {
        "sub": str(user_id),
        "aud": _MOBILE_AUDIENCE,
        "type": _ACCESS_TYPE,
        "scope": scopes,
        "device_id": str(device_id),
        "jti": str(jti),
        "exp": expire,
    }
    return jwt.encode(payload, _secret(), algorithm=config.JWT_ALGORITHM)


def decode_mobile_access_token(token: str) -> dict[str, Any]:
    """Validate and return mobile access-token claims.

    Raises JWTError on invalid/expired/wrong-audience tokens.
    """
    options = {
        "require": ["sub", "aud", "type", "scope", "device_id", "jti", "exp"],
        "verify_aud": True,
    }
    try:
        payload = jwt.decode(
            token,
            _secret(),
            algorithms=[config.JWT_ALGORITHM],
            audience=_MOBILE_AUDIENCE,
            options=options,
        )
    except JWTError as exc:
        # Distinguish a validly signed identity presented to the wrong audience
        # from an invalid signature or expired credential.  This preserves the
        # approved 403 contract without trusting any unverified token payload.
        try:
            signed_payload = jwt.decode(
                token,
                _secret(),
                algorithms=[config.JWT_ALGORITHM],
                options={"verify_aud": False},
            )
        except JWTError:
            raise exc
        audience = signed_payload.get("aud")
        if audience != _MOBILE_AUDIENCE and not (
            isinstance(audience, list) and _MOBILE_AUDIENCE in audience
        ):
            raise MobileAudienceError("token is not intended for mobile") from exc
        raise
    audience = payload.get("aud")
    if audience != _MOBILE_AUDIENCE and not (
        isinstance(audience, list) and _MOBILE_AUDIENCE in audience
    ):
        raise MobileAudienceError("token is not intended for mobile")
    if payload.get("type") != _ACCESS_TYPE:
        raise JWTError("invalid token type")
    scopes = payload.get("scope")
    if not isinstance(scopes, list) or not all(
        isinstance(scope, str) for scope in scopes
    ):
        raise JWTError("invalid scope claim")
    if "monitor:read" not in scopes:
        raise MobileScopeError("missing monitor:read scope")
    return payload


def parse_uuid_claim(claims: Mapping[str, Any], key: str) -> UUID:
    """Parse a UUID claim, raising JWTError on bad format."""
    try:
        return UUID(str(claims[key]))
    except (KeyError, TypeError, ValueError) as exc:
        raise JWTError(f"missing or invalid {key}") from exc
