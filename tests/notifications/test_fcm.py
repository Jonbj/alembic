"""Tests for the privacy-safe FCM delivery adapter."""

from __future__ import annotations


from types import SimpleNamespace

from src.notifications.fcm import (
    FakeFcmAdapter,
    FirebaseFcmAdapter,
    UnavailableFcmAdapter,
    build_fcm_payload,
    get_fcm_adapter,
)


class _FakeMessaging:
    class UnregisteredError(Exception):
        pass

    class SenderIdMismatchError(Exception):
        pass

    class Notification:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class Message:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    def __init__(self):
        self.message = None

    def send(self, message, *, app):
        self.message = message
        assert app is not None
        return "provider-message-id"


class TestFcmAdapter:
    async def test_fake_adapter_returns_accepted(self):
        adapter = FakeFcmAdapter()
        payload = build_fcm_payload(
            event_id="ev-1",
            transition="open",
            severity="critical",
        )
        result = await adapter.send(
            firebase_installation_id="fid",
            payload=payload,
        )
        assert result.accepted
        assert result.provider_message_id is not None
        assert result.error_code is None
        assert not result.terminal

    async def test_payload_contains_only_safe_keys(self):
        payload = build_fcm_payload(
            event_id="ev-1",
            transition="open",
            severity="critical",
        )
        assert set(payload.keys()) == {"event_id", "transition", "severity", "contract_version"}
        assert "nav" not in payload
        assert "ticker" not in payload
        assert "token" not in payload

    async def test_firebase_adapter_targets_fid(self):
        messaging = _FakeMessaging()
        adapter = FirebaseFcmAdapter()
        adapter._app = object()
        adapter._messaging = messaging

        result = await adapter.send(
            firebase_installation_id="firebase-installation-id",
            payload=build_fcm_payload(
                event_id="ev-1",
                transition="open",
                severity="critical",
            ),
        )

        assert result.accepted
        assert messaging.message.kwargs["fid"] == "firebase-installation-id"
        assert "token" not in messaging.message.kwargs

    async def test_fake_adapter_must_be_explicitly_enabled(self, monkeypatch):
        monkeypatch.setattr(
            "src.notifications.fcm.config",
            SimpleNamespace(
                FIREBASE_SERVICE_ACCOUNT_PATH=None,
                FCM_FAKE_DELIVERY_ENABLED=True,
            ),
        )
        adapter = get_fcm_adapter()
        assert isinstance(adapter, FakeFcmAdapter)

    async def test_missing_credentials_fail_closed(self, monkeypatch):
        monkeypatch.setattr(
            "src.notifications.fcm.config",
            SimpleNamespace(
                FIREBASE_SERVICE_ACCOUNT_PATH=None,
                FCM_FAKE_DELIVERY_ENABLED=False,
            ),
        )
        adapter = get_fcm_adapter()
        assert isinstance(adapter, UnavailableFcmAdapter)
        result = await adapter.send(
            firebase_installation_id="secret",
            payload={},
        )
        assert not result.accepted
        assert result.error_code == "fcm_not_configured"
