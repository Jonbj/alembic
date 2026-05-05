"""Tests for Telegram notification formatters."""

from datetime import date, datetime, timezone

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
