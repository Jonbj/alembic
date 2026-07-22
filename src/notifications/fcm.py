"""FCM delivery adapter for mobile alert notifications.

Privacy rule: the FCM data payload contains only opaque incident metadata
(event_id, transition, severity, contract_version). No NAV, P&L, ticker,
reason, username, URL, or token is sent through FCM.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from src.config import config

logger = logging.getLogger(__name__)


class FcmDeliveryPort(Protocol):
    """Outbound FCM delivery port."""

    async def send(self, *, device_token: str, payload: dict[str, Any]) -> "FcmResult": ...


@dataclass(frozen=True)
class FcmResult:
    accepted: bool
    provider_message_id: str | None = None
    error_code: str | None = None
    terminal: bool = False


class FakeFcmAdapter(FcmDeliveryPort):
    """Inert adapter used in tests and when no Firebase credentials are configured.

    Logs the generic payload shape without the destination token so logs stay safe.
    """

    async def send(self, *, device_token: str, payload: dict[str, Any]) -> FcmResult:
        logger.debug("FakeFcmAdapter: would send transition=%s severity=%s", payload.get("transition"), payload.get("severity"))
        return FcmResult(accepted=True, provider_message_id=f"fake:{payload.get('event_id', 'unknown')}")


class FirebaseFcmAdapter(FcmDeliveryPort):
    """Firebase Admin SDK adapter.

    Initialized lazily from a mounted service-account JSON path. Falls back to
    application-default credentials only when explicitly enabled. Analytics is
    never enabled.
    """

    def __init__(self) -> None:
        self._app = None

    def _initialize(self) -> Any:
        if self._app is not None:
            return self._app
        try:
            import firebase_admin  # type: ignore[import-untyped]
            from firebase_admin import credentials, messaging  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError("firebase_admin is not installed") from exc

        service_account_path = getattr(config, "FIREBASE_SERVICE_ACCOUNT_PATH", None) or None
        cred = None
        if service_account_path:
            cred = credentials.Certificate(service_account_path)
        try:
            self._app = firebase_admin.initialize_app(cred)
        except ValueError:
            # Already initialized in this process.
            self._app = firebase_admin.get_app()
        self._messaging = messaging
        return self._app

    async def send(self, *, device_token: str, payload: dict[str, Any]) -> FcmResult:
        self._initialize()
        message = self._messaging.Message(
            data={
                "event_id": str(payload.get("event_id", "")),
                "transition": payload.get("transition", ""),
                "severity": payload.get("severity", ""),
                "contract_version": str(payload.get("contract_version", "1")),
            },
            notification=self._messaging.Notification(
                title="Alembic richiede attenzione",
                body="Alembic è tornato operativo" if payload.get("transition") == "recover" else "Alembic richiede attenzione",
            ),
            token=device_token,
        )
        try:
            response = self._messaging.send(message, app=self._app)
            return FcmResult(accepted=True, provider_message_id=response)
        except self._messaging.UnregisteredError as exc:
            logger.warning("FCM token unregistered: %s", exc)
            return FcmResult(accepted=False, error_code="unregistered", terminal=True)
        except Exception as exc:
            logger.warning("FCM send failed: %s", exc)
            return FcmResult(accepted=False, error_code="provider_error")


def build_fcm_payload(*, event_id: str, transition: str, severity: str, contract_version: int = 1) -> dict[str, Any]:
    """Build the minimal, privacy-safe FCM data payload."""
    return {
        "event_id": event_id,
        "transition": transition,
        "severity": severity,
        "contract_version": str(contract_version),
    }


def get_fcm_adapter() -> FcmDeliveryPort:
    """Return the configured FCM adapter."""
    service_account_path = getattr(config, "FIREBASE_SERVICE_ACCOUNT_PATH", None)
    if service_account_path:
        return FirebaseFcmAdapter()
    return FakeFcmAdapter()
