"""Authentication routes: login, logout, me."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.api.auth import require_api_key
from src.api.jwt_utils import create_access_token, decode_access_token, verify_password
from src.config import config

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    username: str


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest) -> TokenResponse:
    """Exchange username + password for a JWT access token."""
    if not config.ADMIN_PASSWORD_HASH:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_PASSWORD_HASH not configured — set it in .env",
        )
    valid = (
        body.username == config.ADMIN_USERNAME
        and verify_password(body.password, config.ADMIN_PASSWORD_HASH)
    )
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(access_token=create_access_token(body.username))


@router.get("/me", response_model=MeResponse)
async def me(username: str = Depends(require_api_key)) -> MeResponse:
    """Return the currently authenticated user."""
    return MeResponse(username=username if "@" not in username else username)
