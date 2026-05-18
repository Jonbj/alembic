"""Tests for AlertLevel enum and Notifier Protocol."""
import pytest

from src.notifications.base import AlertLevel, Notifier


class TestAlertLevel:
    def test_info_value(self):
        assert AlertLevel.INFO == "info"

    def test_warning_value(self):
        assert AlertLevel.WARNING == "warning"

    def test_critical_value(self):
        assert AlertLevel.CRITICAL == "critical"

    def test_is_str_subclass(self):
        assert isinstance(AlertLevel.INFO, str)

    def test_can_use_as_dict_key_interchangeably_with_str(self):
        d = {"info": "ok"}
        assert d[AlertLevel.INFO] == "ok"


class TestNotifierProtocol:
    def test_class_with_send_alert_satisfies_protocol(self):
        class MockNotifier:
            async def send_alert(self, message: str, level: AlertLevel = AlertLevel.INFO) -> bool:
                return True

        assert isinstance(MockNotifier(), Notifier)

    def test_class_without_send_alert_does_not_satisfy(self):
        class NotANotifier:
            pass

        assert not isinstance(NotANotifier(), Notifier)

    def test_telegram_notifier_satisfies_protocol(self):
        from src.notifications.telegram import TelegramNotifier

        notifier = TelegramNotifier(bot_token="", chat_id="")
        assert isinstance(notifier, Notifier)

    @pytest.mark.asyncio
    async def test_send_alert_accepts_alert_level_enum(self):
        """TelegramNotifier.send_alert must accept AlertLevel without raising TypeError."""
        from src.notifications.telegram import TelegramNotifier
        from unittest.mock import patch, AsyncMock, MagicMock

        notifier = TelegramNotifier(bot_token="token", chat_id="123")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_async_ctx = AsyncMock()
        mock_async_ctx.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_async_ctx):
            result = await notifier.send_alert("test message", level=AlertLevel.CRITICAL)

        assert result is True

    @pytest.mark.asyncio
    async def test_send_alert_still_accepts_plain_string_level(self):
        """Backward compat: existing callers passing level='warning' must still work."""
        from src.notifications.telegram import TelegramNotifier
        from unittest.mock import patch, AsyncMock, MagicMock

        notifier = TelegramNotifier(bot_token="token", chat_id="123")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_async_ctx = AsyncMock()
        mock_async_ctx.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_async_ctx):
            result = await notifier.send_alert("test message", level="warning")

        assert result is True
