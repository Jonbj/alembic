"""Authentication module for FastAPI API key dependency."""

import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from src.config import config

_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(key: str | None = Security(_header)) -> str:
    """Validate X-API-Key header against config.ADMIN_API_KEY.

    Args:
        key: API key from X-API-Key header

    Returns:
        The validated API key

    Raises:
        HTTPException: 403 if key is missing or invalid
    """
    if key is None or not secrets.compare_digest(key, config.ADMIN_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key"
        )
    return key
