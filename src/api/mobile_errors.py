"""Canonical error envelope for the versioned mobile API."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi.responses import JSONResponse


class MobileAPIError(Exception):
    """Structured application error returned below ``/api/mobile/v1``."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Capture the stable public error contract without sensitive context."""
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}
        self.headers = headers


def render_mobile_error(error: MobileAPIError) -> JSONResponse:
    """Render a mobile API error using the approved top-level envelope."""
    return JSONResponse(
        status_code=error.status_code,
        content={
            "error": {
                "code": error.code,
                "message": error.message,
                "request_id": str(uuid4()),
                "retryable": error.retryable,
                "details": error.details,
            }
        },
        headers=error.headers,
    )
