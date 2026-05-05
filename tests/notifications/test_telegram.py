"""Tests for Telegram notification formatters."""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.notifications.telegram import (
    TelegramNotifier,
    format_auto_apply_message,
    format_freeze_message,
    format_freeze_message_with_keyboard,
)


class TestFormatAutoApplyMessage:
    """Tests for format_auto_apply_message()."""

    def test_contains_success_header(self):
        msg = format_auto_apply_message(
            new_weights={"opus": 0.45, "qwen3.5:cloud": 0.35, "deepseek-v4-pro:cloud": 0.20},
            current_weights={"opus": 0.34, "qwen3.5:cloud": 0.33, "deepseek-v4-pro:cloud": 0.33},
            guardrail_values={"vix": 18.4, "ic_variance": 0.08, "weight_delta_max": 0.11},
            next_review_date=date(2026, 5, 12),
        )
        assert "✅" in msg
        assert "automaticamente" in msg

    def test_shows_weight_delta(self):
        msg = format_auto_apply_message(
            new_weights={"opus": 0.45},
            current_weights={"opus": 0.34},
            guardrail_values={},
            next_review_date=date(2026, 5, 12),
        )
        assert "+11%" in msg or "+0.11" in msg or "11pp" in msg.lower() or "+11" in msg

    def test_shows_next_review_date(self):
        msg = format_auto_apply_message(
            new_weights={"opus": 1.0},
            current_weights={"opus": 1.0},
            guardrail_values={},
            next_review_date=date(2026, 5, 12),
        )
        assert "2026-05-12" in msg

    def test_shows_guardrail_values(self):
        msg = format_auto_apply_message(
            new_weights={"opus": 1.0},
            current_weights={"opus": 1.0},
            guardrail_values={"vix": 18.4, "ic_variance": 0.08, "weight_delta_max": 0.0},
            next_review_date=date(2026, 5, 12),
        )
        assert "18.4" in msg
        assert "0.08" in msg


class TestFormatFreezeMessage:
    """Tests for format_freeze_message()."""

    def test_contains_warning_header(self):
        msg = format_freeze_message(
            suggested_weights={"opus": 0.45},
            current_weights={"opus": 0.34},
            freeze_reason="VIX = 38.2 >= 30.0",
        )
        assert "⚠️" in msg
        assert "bloccato" in msg

    def test_shows_freeze_reason(self):
        msg = format_freeze_message(
            suggested_weights={"opus": 0.45},
            current_weights={"opus": 0.34},
            freeze_reason="VIX = 38.2 >= 30.0",
        )
        assert "VIX = 38.2" in msg

    def test_shows_suggested_weights_not_applied(self):
        msg = format_freeze_message(
            suggested_weights={"opus": 0.45},
            current_weights={"opus": 0.34},
            freeze_reason="VIX too high",
        )
        assert "NON applicati" in msg
        assert "45%" in msg

    def test_shows_manual_approval_hint(self):
        msg = format_freeze_message(
            suggested_weights={"opus": 0.45},
            current_weights={"opus": 0.34},
            freeze_reason="IC variance too high",
        )
        assert "/api/weights/approve" in msg


class TestFormatRegimeMessage:
    def _make_state(self, regime="bear", disagreement=False, prev_regime_in_outputs=None):
        from src.models.regime import MacroSnapshot, RegimeState
        outputs = [
            {"regime": prev_regime_in_outputs or regime, "reasoning": "Inverted curve"},
            {"regime": regime, "reasoning": "Selloff"},
        ]
        return RegimeState(
            regime=regime,
            multiplier={"bull": 1.0, "sideways": 0.7, "bear": 0.4, "high_vol": 0.2}[regime],
            macro_snapshot=MacroSnapshot(vix=28.4, yield_curve=-0.6, spy_momentum_20d=-7.1),
            llm_outputs=outputs,
            disagreement=disagreement,
            detected_at=datetime(2026, 5, 5, 7, 0, 0, tzinfo=timezone.utc),
        )

    def test_regime_change_shows_arrow(self):
        from src.notifications.telegram import format_regime_message
        state = self._make_state("bear")
        msg = format_regime_message(state, previous_regime="bull", disagreement=False)
        assert "BULL" in msg
        assert "BEAR" in msg
        assert "→" in msg
        assert "0.4" in msg

    def test_first_run_no_arrow(self):
        from src.notifications.telegram import format_regime_message
        state = self._make_state("bull")
        msg = format_regime_message(state, previous_regime=None, disagreement=False)
        assert "→" not in msg
        assert "BULL" in msg

    def test_disagreement_note_included(self):
        from src.notifications.telegram import format_regime_message
        state = self._make_state("bear", disagreement=True, prev_regime_in_outputs="bull")
        msg = format_regime_message(state, previous_regime="sideways", disagreement=True)
        assert "Disaccordo" in msg

    def test_macro_data_shown(self):
        from src.notifications.telegram import format_regime_message
        state = self._make_state("bear")
        msg = format_regime_message(state, previous_regime=None, disagreement=False)
        assert "28.4" in msg
        assert "-0.60" in msg or "-0.6" in msg
        assert "-7.1" in msg

    def test_reasoning_included(self):
        from src.notifications.telegram import format_regime_message
        state = self._make_state("bear")
        msg = format_regime_message(state, previous_regime=None, disagreement=False)
        assert "Inverted curve" in msg


class TestFormatFreezeMessageWithKeyboard:
    """Tests for format_freeze_message_with_keyboard()."""

    def test_returns_tuple_with_text_and_keyboard(self):
        text, keyboard = format_freeze_message_with_keyboard(
            suggested_weights={"opus": 0.45},
            current_weights={"opus": 0.34},
            freeze_reason="VIX = 38.2 >= 30.0",
            suggestion_token="abc12345",
        )
        assert isinstance(text, str)
        assert isinstance(keyboard, list)
        assert "⚠️" in text
        assert "bloccato" in text

    def test_keyboard_has_approve_button(self):
        _, keyboard = format_freeze_message_with_keyboard(
            suggested_weights={"opus": 0.45},
            current_weights={"opus": 0.34},
            freeze_reason="VIX too high",
            suggestion_token="abc12345",
        )
        assert len(keyboard) == 2  # Two rows
        approve_btn = keyboard[0][0]
        assert approve_btn["text"] == "✅ Approva"
        assert approve_btn["callback_data"] == "approve:abc12345"

    def test_keyboard_has_reject_button(self):
        _, keyboard = format_freeze_message_with_keyboard(
            suggested_weights={"opus": 0.45},
            current_weights={"opus": 0.34},
            freeze_reason="VIX too high",
            suggestion_token="xyz789",
        )
        reject_btn = keyboard[1][0]
        assert reject_btn["text"] == "❌ Rifiuta"
        assert reject_btn["callback_data"] == "reject:xyz789"

    def test_shows_suggested_weights(self):
        text, _ = format_freeze_message_with_keyboard(
            suggested_weights={"opus": 0.45},
            current_weights={"opus": 0.34},
            freeze_reason="IC variance",
            suggestion_token="token123",
        )
        assert "45%" in text
        assert "NON applicati" in text


class TestTelegramNotifierWithKeyboard:
    """Tests for TelegramNotifier.send_message_with_keyboard() and edit_message_reply_markup()."""

    def _make_notifier(self, token="test-bot-token", chat_id="123456"):
        return TelegramNotifier(bot_token=token, chat_id=chat_id)

    @pytest.mark.asyncio
    async def test_send_message_with_keyboard_returns_message_id(self):
        notifier = self._make_notifier()
        keyboard = [[{"text": "Btn", "callback_data": "data"}]]

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"result": {"message_id": 42}}

            # Properly mock async context manager and async post method
            mock_async_context = AsyncMock()
            mock_async_context.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_async_context

            message_id = await notifier.send_message_with_keyboard("Test", keyboard)

            assert message_id == 42

    @pytest.mark.asyncio
    async def test_send_message_with_keyboard_returns_none_on_failure(self):
        notifier = self._make_notifier()
        keyboard = [[{"text": "Btn", "callback_data": "data"}]]

        with patch("httpx.AsyncClient") as mock_client:
            mock_async_context = AsyncMock()
            mock_async_context.__aenter__.return_value.post.side_effect = Exception("Network error")
            mock_client.return_value = mock_async_context

            message_id = await notifier.send_message_with_keyboard("Test", keyboard)

            assert message_id is None

    @pytest.mark.asyncio
    async def test_send_message_with_keyboard_disabled(self):
        notifier = TelegramNotifier(bot_token="", chat_id="")
        keyboard = [[{"text": "Btn", "callback_data": "data"}]]

        message_id = await notifier.send_message_with_keyboard("Test", keyboard)

        assert message_id is None

    @pytest.mark.asyncio
    async def test_edit_message_reply_markup_success(self):
        notifier = self._make_notifier()

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()

            mock_async_context = AsyncMock()
            mock_async_context.__aenter__.return_value.post.return_value = mock_response
            mock_client.return_value = mock_async_context

            result = await notifier.edit_message_reply_markup(chat_id="123456", message_id=42, keyboard=None)

            assert result is True

    @pytest.mark.asyncio
    async def test_edit_message_reply_markup_with_keyboard(self):
        notifier = self._make_notifier()
        keyboard = [[{"text": "Btn", "callback_data": "data"}]]

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()

            mock_async_context = AsyncMock()
            mock_async_context.__aenter__.return_value.post.return_value = mock_response
            mock_client.return_value = mock_async_context

            result = await notifier.edit_message_reply_markup(chat_id="123456", message_id=42, keyboard=keyboard)

            assert result is True
            # Verify the payload included reply_markup
            call_args = mock_async_context.__aenter__.return_value.post.call_args
            assert "reply_markup" in call_args[1]["json"]

    @pytest.mark.asyncio
    async def test_edit_message_reply_markup_failure(self):
        notifier = self._make_notifier()

        with patch("httpx.AsyncClient") as mock_client:
            mock_async_context = AsyncMock()
            mock_async_context.__aenter__.return_value.post.side_effect = Exception("Network error")
            mock_client.return_value = mock_async_context

            result = await notifier.edit_message_reply_markup(chat_id="123456", message_id=42)

            assert result is False

    @pytest.mark.asyncio
    async def test_edit_message_reply_markup_disabled(self):
        notifier = TelegramNotifier(bot_token="", chat_id="")

        result = await notifier.edit_message_reply_markup(chat_id="123456", message_id=42)

        assert result is False
