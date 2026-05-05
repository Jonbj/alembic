"""Tests for detect_regime Celery task."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.regime import MacroSnapshot, RegimeOutput, RegimeState


class TestDetectRegime:
    """8 scenarios covering all consensus branches including invalid regime."""

    BULL = RegimeOutput(regime="bull", confidence=0.85, reasoning="uptrend", data_quality="complete")
    BEAR = RegimeOutput(regime="bear", confidence=0.78, reasoning="downturn", data_quality="complete")
    PARTIAL = RegimeOutput(regime="bull", confidence=0.5, reasoning="x", data_quality="partial")
    # Invalid regime for testing validation

    def _make_redis(self, current_regime=None):
        mock = MagicMock()
        mock.get_regime.return_value = current_regime
        mock.set_regime = MagicMock()
        mock.set_qc_sizing_multiplier = MagicMock()
        return mock

    def _make_config(self):
        from src.config import Config
        return Config(
            ADMIN_API_KEY="test-api-key-for-testing-only-12345678",
            DATABASE_URL="postgresql://localhost:5432/test",
            REGIME_LLM_MODEL_1="opus",
            REGIME_LLM_MODEL_2="qwen3.5:cloud",
            REGIME_MULTIPLIER_BULL=1.0,
            REGIME_MULTIPLIER_SIDEWAYS=0.7,
            REGIME_MULTIPLIER_BEAR=0.4,
            REGIME_MULTIPLIER_HIGH_VOL=0.2,
            REGIME_REDIS_TTL_SECONDS=90000,
        )

    def _run(self, llm_return, redis, notifier, cfg, vix=18.4, yield_curve=0.3, spy=4.2):
        """Run detect_regime with all dependencies patched (normal path)."""
        with patch("src.workers.regime.RedisStore", return_value=redis), \
             patch("src.workers.regime.TelegramNotifier", return_value=notifier), \
             patch("src.workers.regime._run_llm_pair", new=AsyncMock(return_value=llm_return)), \
             patch("src.workers.regime._make_llm_client", return_value=MagicMock()), \
             patch("src.workers.regime.config", cfg), \
             patch("src.workers.regime.fetch_vix_from_fred", return_value=vix), \
             patch("src.workers.regime.fetch_yield_curve", return_value=yield_curve), \
             patch("src.workers.regime.fetch_spy_momentum_20d", return_value=spy):
            from src.workers.regime import detect_regime
            detect_regime()

    # 1. All signals ok, LLM consensus → regime applied
    def test_consensus_applies_regime(self):
        redis = self._make_redis()
        notifier = MagicMock()
        notifier.send_alert = AsyncMock()
        cfg = self._make_config()

        self._run((self.BULL, self.BULL), redis, notifier, cfg)

        redis.set_regime.assert_called_once()
        state = redis.set_regime.call_args[0][0]
        assert state.regime == "bull"
        assert state.multiplier == pytest.approx(1.0)
        assert state.disagreement is False
        redis.set_qc_sizing_multiplier.assert_called_once_with(1.0, ttl=90000)
        # First run (no previous) → Telegram sent
        notifier.send_alert.assert_called_once()

    # 2. LLM disagreement → conservative multiplier, Telegram ⚠️
    def test_disagreement_applies_conservative_regime(self):
        redis = self._make_redis()
        notifier = MagicMock()
        notifier.send_alert = AsyncMock()
        cfg = self._make_config()

        # bull vs bear → should pick bear (lower multiplier)
        self._run((self.BULL, self.BEAR), redis, notifier, cfg)

        state = redis.set_regime.call_args[0][0]
        assert state.regime == "bear"
        assert state.multiplier == pytest.approx(0.4)
        assert state.disagreement is True
        notifier.send_alert.assert_called_once()
        msg = notifier.send_alert.call_args[0][0]
        assert "Disaccordo" in msg or "bear" in msg.lower()

    # 8. Invalid regime from LLM → Redis unchanged, Telegram 🚨
    def test_invalid_regime_from_llm_no_redis_write(self):
        # Create an output with valid structure but we'll mock it to return invalid regime
        from unittest.mock import Mock
        invalid_output = Mock(spec=RegimeOutput)
        invalid_output.regime = "crash"  # Invalid regime
        invalid_output.data_quality = "complete"
        invalid_output.model_dump.return_value = {"regime": "crash", "confidence": 0.9}

        redis = self._make_redis()
        notifier = MagicMock()
        notifier.send_alert = AsyncMock()
        cfg = self._make_config()

        # Patch _run_llm_pair to return our mock with invalid regime
        with patch("src.workers.regime.RedisStore", return_value=redis), \
             patch("src.workers.regime.TelegramNotifier", return_value=notifier), \
             patch("src.workers.regime._run_llm_pair", new=AsyncMock(return_value=(invalid_output, self.BULL))), \
             patch("src.workers.regime._make_llm_client", return_value=MagicMock()), \
             patch("src.workers.regime.config", cfg), \
             patch("src.workers.regime.fetch_vix_from_fred", return_value=18.4), \
             patch("src.workers.regime.fetch_yield_curve", return_value=0.3), \
             patch("src.workers.regime.fetch_spy_momentum_20d", return_value=4.2):
            from src.workers.regime import detect_regime
            detect_regime()

        redis.set_regime.assert_not_called()
        redis.set_qc_sizing_multiplier.assert_not_called()
        notifier.send_alert.assert_called_once()
        msg = notifier.send_alert.call_args[0][0]
        assert "🚨" in msg

    # 3. LLM-1 fails → use LLM-2
    def test_one_llm_failure_uses_other(self):
        redis = self._make_redis()
        notifier = MagicMock()
        notifier.send_alert = AsyncMock()
        cfg = self._make_config()

        self._run((None, self.BEAR), redis, notifier, cfg)

        state = redis.set_regime.call_args[0][0]
        assert state.regime == "bear"
        assert state.disagreement is False

    # 4. Both LLMs fail → Redis unchanged, Telegram 🚨
    def test_both_llms_fail_no_redis_write(self):
        redis = self._make_redis()
        notifier = MagicMock()
        notifier.send_alert = AsyncMock()
        cfg = self._make_config()

        self._run((None, None), redis, notifier, cfg)

        redis.set_regime.assert_not_called()
        redis.set_qc_sizing_multiplier.assert_not_called()
        notifier.send_alert.assert_called_once()
        msg = notifier.send_alert.call_args[0][0]
        assert "🚨" in msg

    # 5. data_quality partial → Redis unchanged, Telegram ⚠️
    def test_partial_data_quality_no_redis_write(self):
        redis = self._make_redis()
        notifier = MagicMock()
        notifier.send_alert = AsyncMock()
        cfg = self._make_config()

        self._run((self.PARTIAL, self.BULL), redis, notifier, cfg)

        redis.set_regime.assert_not_called()
        notifier.send_alert.assert_called_once()
        msg = notifier.send_alert.call_args[0][0]
        assert "⚠️" in msg

    # 6. Regime unchanged from previous → no Telegram
    def test_regime_unchanged_no_telegram(self):
        previous = RegimeState(
            regime="bull",
            multiplier=1.0,
            macro_snapshot=MacroSnapshot(vix=15.0, yield_curve=0.3, spy_momentum_20d=4.0),
            llm_outputs=[],
            detected_at=datetime(2026, 5, 4, 7, 0, 0, tzinfo=timezone.utc),
        )
        redis = self._make_redis(current_regime=previous)
        notifier = MagicMock()
        notifier.send_alert = AsyncMock()
        cfg = self._make_config()

        self._run((self.BULL, self.BULL), redis, notifier, cfg)

        redis.set_regime.assert_called_once()
        notifier.send_alert.assert_not_called()

    # 7. Macro data fetch fails → Redis unchanged, Telegram 🚨
    def test_macro_fetch_failure_no_redis_write(self):
        redis = self._make_redis()
        notifier = MagicMock()
        notifier.send_alert = AsyncMock()
        cfg = self._make_config()

        with patch("src.workers.regime.RedisStore", return_value=redis), \
             patch("src.workers.regime.TelegramNotifier", return_value=notifier), \
             patch("src.workers.regime.config", cfg), \
             patch("src.workers.regime.fetch_vix_from_fred", side_effect=Exception("network error")), \
             patch("src.workers.regime.fetch_yield_curve", return_value=0.3), \
             patch("src.workers.regime.fetch_spy_momentum_20d", return_value=4.2):
            from src.workers.regime import detect_regime
            detect_regime()

        redis.set_regime.assert_not_called()
        notifier.send_alert.assert_called_once()
        msg = notifier.send_alert.call_args[0][0]
        assert "🚨" in msg
