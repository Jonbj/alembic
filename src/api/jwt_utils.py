"""JWT creation and validation utilities."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from src.config import config

_EPHEMERAL_KEY = secrets.token_hex(32)


def _secret() -> str:
    return config.JWT_SECRET_KEY or _EPHEMERAL_KEY


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def create_access_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=config.JWT_EXPIRE_MINUTES)
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, _secret(), algorithm=config.JWT_ALGORITHM)


def decode_access_token(token: str) -> str:
    """Return username from a valid token, raise JWTError on failure."""
    payload = jwt.decode(token, _secret(), algorithms=[config.JWT_ALGORITHM])
    username: str | None = payload.get("sub")
    if username is None:
        raise JWTError("missing sub claim")
    return username
