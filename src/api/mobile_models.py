"""Pydantic request/response models for the /api/mobile/v1 API surface.

These models wrap the shared domain contract in `src.mobile_monitoring.models`
with the authentication and device-management shapes defined in the approved
design spec.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.mobile_monitoring.models import DeviceResponse


class DeviceInfoRequest(BaseModel):
    """Device metadata supplied at first login."""

    model_config = ConfigDict(extra="forbid")

    installation_id: UUID
    name: str = Field(..., min_length=1, max_length=100)
    app_version: str = Field(..., min_length=1, max_length=20)


class LoginRequest(BaseModel):
    """POST /api/mobile/v1/auth/login request body."""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1)
    device: DeviceInfoRequest


class UserInfo(BaseModel):
    """Minimal user object returned after login."""

    id: UUID
    username: str


class LoginResponse(BaseModel):
    """POST /api/mobile/v1/auth/login response body."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., gt=0)
    refresh_token: str
    refresh_expires_at: datetime
    user: UserInfo
    device_id: UUID


class RefreshRequest(BaseModel):
    """POST /api/mobile/v1/auth/refresh request body."""

    model_config = ConfigDict(extra="forbid")

    refresh_token: str


class LogoutRequest(BaseModel):
    """POST /api/mobile/v1/auth/logout request body."""

    model_config = ConfigDict(extra="forbid")

    refresh_token: str


class DeviceRegistrationRequest(BaseModel):
    """POST /api/mobile/v1/devices request body.

    Idempotent by installation_id for the authenticated user/device session.
    """

    model_config = ConfigDict(extra="forbid")

    installation_id: UUID
    firebase_installation_id: str | None = None
    name: str = Field(..., min_length=1, max_length=100)
    app_version: str = Field(..., min_length=1, max_length=20)
    push_enabled: bool

    @model_validator(mode="after")
    def require_destination_when_push_is_enabled(self) -> "DeviceRegistrationRequest":
        if self.push_enabled and not self.firebase_installation_id:
            raise ValueError(
                "firebase_installation_id is required when push_enabled is true"
            )
        return self


class DeviceRegistrationResponse(BaseModel):
    """POST /api/mobile/v1/devices response body."""

    device: DeviceResponse


__all__ = [
    "DeviceInfoRequest",
    "DeviceRegistrationRequest",
    "DeviceRegistrationResponse",
    "DeviceResponse",
    "LoginRequest",
    "LoginResponse",
    "LogoutRequest",
    "RefreshRequest",
    "UserInfo",
]
