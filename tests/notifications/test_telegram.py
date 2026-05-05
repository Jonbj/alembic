"""Tests for Telegram notification formatters."""

from datetime import date

import pytest

from src.notifications.telegram import format_auto_apply_message, format_freeze_message


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
