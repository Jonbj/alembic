"""FCM delivery adapter for mobile alert notifications.

Privacy rule: the FCM data payload contains only opaque incident metadata
(event_id, transition, severity, contract_version). No NAV, P&L, ticker,
reason, username, URL, or token is sent through FCM.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from src.config import config

logger = logging.getLogger(__name__)


class FcmDeliveryPort(Protocol):
    """Outbound FCM delivery port."""

    async def send(
        self,
        *,
        firebase_installation_id: str,
        payload: dict[str, Any],
    ) -> "FcmResult": ...


@dataclass(frozen=True)
class FcmResult:
    accepted: bool
    provider_message_id: str | None = None
    error_code: str | None = None
    terminal: bool = False


class FakeFcmAdapter(FcmDeliveryPort):
    """Inert adapter enabled explicitly in tests/development.

    Logs the generic payload shape without the destination identifier.
    """

    async def send(
        self,
        *,
        firebase_installation_id: str,
        payload: dict[str, Any],
    ) -> FcmResult:
        del firebase_installation_id
        logger.debug("FakeFcmAdapter: would send transition=%s severity=%s", payload.get("transition"), payload.get("severity"))
        return FcmResult(accepted=True, provider_message_id=f"fake:{payload.get('event_id', 'unknown')}")


class UnavailableFcmAdapter(FcmDeliveryPort):
    """Fail closed when a destination exists but Firebase is not configured."""

    async def send(
        self,
        *,
        firebase_installation_id: str,
        payload: dict[str, Any],
    ) -> FcmResult:
        del firebase_installation_id, payload
        return FcmResult(accepted=False, error_code="fcm_not_configured")


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
            project_id = getattr(config, "FCM_PROJECT_ID", None)
            options = {"projectId": project_id} if project_id else None
            self._app = firebase_admin.initialize_app(cred, options)
        except ValueError:
            # Already initialized in this process.
            self._app = firebase_admin.get_app()
        self._messaging = messaging
        return self._app

    async def send(
        self,
        *,
        firebase_installation_id: str,
        payload: dict[str, Any],
    ) -> FcmResult:
        self._initialize()
        message = self._messaging.Message(
            data={
                "event_id": str(payload.get("event_id", "")),
                "transition": payload.get("transition", ""),
                "severity": payload.get("severity", ""),
                "contract_version": str(payload.get("contract_version", "1")),
            },
            # Data-only messages are rendered by the Android client after
            # validation/deduplication. A notification payload would be rendered
            # automatically in background and bypass the biometric deep-link gate.
            android=self._messaging.AndroidConfig(priority="high"),
            fid=firebase_installation_id,
        )
        try:
            response = await asyncio.to_thread(
                self._messaging.send,
                message,
                app=self._app,
            )
            return FcmResult(accepted=True, provider_message_id=response)
        except self._messaging.UnregisteredError as exc:
            logger.warning("FCM destination rejected: %s", type(exc).__name__)
            return FcmResult(accepted=False, error_code="unregistered", terminal=True)
        except self._messaging.SenderIdMismatchError as exc:
            logger.warning("FCM destination rejected: %s", type(exc).__name__)
            return FcmResult(
                accepted=False,
                error_code="sender_id_mismatch",
                terminal=True,
            )
        except Exception as exc:
            logger.warning("FCM send failed: %s", type(exc).__name__)
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
    use_adc = getattr(config, "FCM_USE_APPLICATION_DEFAULT_CREDENTIALS", False)
    if service_account_path or use_adc:
        return FirebaseFcmAdapter()
    if getattr(config, "FCM_FAKE_DELIVERY_ENABLED", False):
        return FakeFcmAdapter()
    return UnavailableFcmAdapter()
