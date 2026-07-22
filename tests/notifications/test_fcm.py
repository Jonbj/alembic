"""Tests for the privacy-safe FCM delivery adapter."""

from __future__ import annotations


from src.notifications.fcm import FakeFcmAdapter, build_fcm_payload, get_fcm_adapter


class TestFcmAdapter:
    async def test_fake_adapter_returns_accepted(self):
        adapter = FakeFcmAdapter()
        payload = build_fcm_payload(
            event_id="ev-1",
            transition="open",
            severity="critical",
        )
        result = await adapter.send(device_token="tok", payload=payload)
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

    async def test_default_adapter_is_fake_when_no_service_account(self, monkeypatch):
        monkeypatch.delenv("FIREBASE_SERVICE_ACCOUNT_PATH", raising=False)
        adapter = get_fcm_adapter()
        assert isinstance(adapter, FakeFcmAdapter)
