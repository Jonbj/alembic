"""Authentication middleware: accepts JWT Bearer token OR X-API-Key header."""
from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from jose import JWTError

from src.config import config

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(
    x_api_key: str | None = Security(_api_key_header),
    authorization: str | None = Header(default=None),
) -> str:
    """Accept either a JWT Bearer token or the legacy X-API-Key header.

    Bearer token: issued by POST /api/auth/login, preferred for browser clients.
    X-API-Key: static secret from config, kept for CLI / programmatic access.

    Returns the authenticated identity (username from JWT, or the raw key).
    Raises HTTP 403 if neither credential is valid.
    """
    # --- Try Bearer token first ---
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        try:
            from src.api.jwt_utils import decode_access_token
            return decode_access_token(token)
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid or expired JWT token",
            )

    # --- Fall back to X-API-Key ---
    if x_api_key and config.ADMIN_API_KEY and secrets.compare_digest(x_api_key, config.ADMIN_API_KEY):
        return x_api_key

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid or missing credentials",
    )
