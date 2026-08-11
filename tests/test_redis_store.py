"""Tests for Redis store - fallback counter verification."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.store.redis_store import RedisStore


class TestFallbackCounter:
    """Test consecutive fallback counter (circuit breaker)."""

    def test_increment_fallback_counter(self):
        """Test incrementing fallback counter."""
        mock_redis = MagicMock()
        mock_redis.incr.return_value = 1
        mock_redis.get.return_value = None

        store = RedisStore(redis_client=mock_redis)
        result = store.increment_fallback_counter()

        mock_redis.incr.assert_called_once_with("fallback:consecutive:count")
        mock_redis.expire.assert_called()  # TTL set
        assert result == 1

    def test_reset_fallback_counter(self):
        """Test resetting fallback counter."""
        mock_redis = MagicMock()

        store = RedisStore(redis_client=mock_redis)
        store.reset_fallback_counter()

        mock_redis.delete.assert_called_once_with("fallback:consecutive:count")

    def test_get_fallback_count(self):
        """Test getting current fallback count."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = b"3"

        store = RedisStore(redis_client=mock_redis)
        count = store.get_fallback_count()

        assert count == 3
        mock_redis.get.assert_called_once_with("fallback:consecutive:count")

    def test_get_fallback_count_zero(self):
        """Test getting fallback count when none exists."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        store = RedisStore(redis_client=mock_redis)
        count = store.get_fallback_count()

        assert count == 0

    def test_qc_sizing_multiplier_default(self):
        """Test default QC sizing multiplier is 1.0."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        store = RedisStore(redis_client=mock_redis)
        multiplier = store.get_qc_sizing_multiplier()

        assert multiplier == 1.0

    def test_qc_sizing_multiplier_after_threshold(self):
        """Test QC sizing multiplier is 0.5 after fallback threshold."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = b"0.5"

        store = RedisStore(redis_client=mock_redis)
        multiplier = store.get_qc_sizing_multiplier()

        assert multiplier == 0.5


class TestKillSwitch:
    """Test kill-switch functionality."""

    def test_activate_killswitch(self):
        """Test activating kill-switch."""
        mock_redis = MagicMock()
        mock_redis.pipeline.return_value = MagicMock()

        store = RedisStore(redis_client=mock_redis)
        store.activate_killswitch(reason="VIX spike")

        pipe = mock_redis.pipeline.return_value
        pipe.set.assert_any_call("killswitch_active", 1)
        pipe.execute.assert_called()

    def test_is_killswitch_active_drawdown_key(self):
        """is_killswitch_active returns True when the drawdown key is set."""
        mock_redis = MagicMock()
        mock_redis.get.side_effect = lambda key: b"1" if key == "killswitch_active" else None

        store = RedisStore(redis_client=mock_redis)
        assert store.is_killswitch_active() is True

    def test_is_killswitch_active_operator_key(self):
        """is_killswitch_active returns True when the operator halt key is set."""
        mock_redis = MagicMock()
        mock_redis.get.side_effect = lambda key: b"1" if key == "system:halted_by_operator" else None

        store = RedisStore(redis_client=mock_redis)
        assert store.is_killswitch_active() is True

    def test_is_killswitch_inactive(self):
        """Test checking kill-switch status when both keys are absent."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        store = RedisStore(redis_client=mock_redis)
        assert store.is_killswitch_active() is False

    def test_activate_operator_halt(self):
        """activate_operator_halt writes to the operator-specific key with no TTL."""
        mock_redis = MagicMock()
        mock_redis.pipeline.return_value = MagicMock()

        store = RedisStore(redis_client=mock_redis)
        store.activate_operator_halt("manual test halt")

        pipe = mock_redis.pipeline.return_value
        pipe.set.assert_any_call("system:halted_by_operator", 1)
        pipe.execute.assert_called()

    def test_deactivate_operator_halt(self):
        """deactivate_operator_halt clears the operator-specific key."""
        mock_redis = MagicMock()
        store = RedisStore(redis_client=mock_redis)
        store.deactivate_operator_halt()
        mock_redis.delete.assert_called_once_with(
            "system:halted_by_operator", "system:halted_by_operator_reason"
        )


class TestDivergenceLogging:
    """Test divergence logging."""

    def test_log_divergence(self):
        """Test logging divergence event."""
        mock_redis = MagicMock()

        store = RedisStore(redis_client=mock_redis)
        store.log_divergence(
            symbol="AAPL",
            std=0.35,
            model_scores={"opus": 0.5, "qwen": -0.5},
            event_type="ensemble_divergence",
        )

        mock_redis.lpush.assert_called()
        mock_redis.ltrim.assert_called()
        mock_redis.expire.assert_called()

    def test_get_recent_divergences(self):
        """Test getting recent divergence events."""
        import json

        mock_redis = MagicMock()
        mock_redis.lrange.return_value = [
            json.dumps({"symbol": "AAPL", "std": 0.35, "event_type": "divergence"}).encode()
        ]

        store = RedisStore(redis_client=mock_redis)
        divergences = store.get_recent_divergences()

        assert len(divergences) == 1
        assert divergences[0]["symbol"] == "AAPL"


class TestOperatingMode:
    """Test operating mode functionality (set_mode/get_mode)."""

    def test_set_mode(self):
        """Test setting operating mode."""
        mock_redis = MagicMock()

        store = RedisStore(redis_client=mock_redis)
        store.set_mode("halted")

        mock_redis.set.assert_called_once_with("system:mode", "halted")
        mock_redis.expire.assert_called()  # TTL set

    def test_get_mode(self):
        """Test getting current mode."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = "paper"  # Redis returns str, not bytes in mock

        store = RedisStore(redis_client=mock_redis)
        mode = store.get_mode()

        assert mode == "paper"
        mock_redis.get.assert_called_once_with("system:mode")

    def test_get_mode_none(self):
        """Test getting mode when not set."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        store = RedisStore(redis_client=mock_redis)
        mode = store.get_mode()

        assert mode is None


class TestRedisOOMHandling:
    """Test Redis OOM handling in write operations."""

    def test_set_mode_oom_handling(self):
        """Test set_mode handles Redis OOM gracefully."""
        mock_redis = MagicMock()
        mock_redis.set.side_effect = Exception("Redis OOM: out of memory")

        store = RedisStore(redis_client=mock_redis)
        # Should not raise - should print and continue
        store.set_mode("halted")

    def test_write_sentiment_oom_handling(self):
        """Test write_sentiment handles Redis OOM gracefully."""
        from src.models.signals import SentimentResult
        from datetime import datetime, timezone

        mock_redis = MagicMock()
        mock_redis.setex.side_effect = Exception("Redis OOM: out of memory")

        store = RedisStore(redis_client=mock_redis)
        result = SentimentResult(
            symbol="AAPL",
            score=0.5,
            confidence=0.8,
            reasoning="Test",
            model_id="ensemble",
            generated_at=datetime.now(timezone.utc),
        )
        # Should not raise - should print and continue
        store.write_sentiment(result)


class TestGetWeightSuggestion:
    """Test RedisStore.get_weight_suggestion()."""

    def test_returns_dict_when_key_exists(self):
        import json
        payload = {"suggested_weights": {"opus": 0.45}, "freeze_reason": ""}
        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps(payload).encode()

        store = RedisStore(redis_client=mock_redis)
        result = store.get_weight_suggestion()

        assert result == payload
        mock_redis.get.assert_called_once_with("ensemble:weights:suggestion")

    def test_returns_none_when_key_absent(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        store = RedisStore(redis_client=mock_redis)
        assert store.get_weight_suggestion() is None

    def test_returns_none_on_corrupted_json(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = b"not-valid-json"

        store = RedisStore(redis_client=mock_redis)
        assert store.get_weight_suggestion() is None


class TestGetPerformanceReport:
    """Test RedisStore.get_performance_report()."""

    def test_returns_dict_when_key_exists(self):
        payload = {"generated_at": "2026-05-05T10:00:00", "model_scores": {}}
        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps(payload).encode()

        store = RedisStore(redis_client=mock_redis)
        result = store.get_performance_report()

        assert result == payload
        mock_redis.get.assert_called_once_with("performance:latest_report")

    def test_returns_none_when_absent(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        store = RedisStore(redis_client=mock_redis)
        assert store.get_performance_report() is None


class TestGetCurrentWeightsStored:
    """Test RedisStore.get_current_weights_stored()."""

    def test_returns_dict_when_key_exists(self):
        payload = {"weights": {"opus": 0.34}, "source": "suggestion"}
        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps(payload).encode()

        store = RedisStore(redis_client=mock_redis)
        result = store.get_current_weights_stored()

        assert result == payload
        mock_redis.get.assert_called_once_with("ensemble:weights:current")

    def test_returns_none_when_absent(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        store = RedisStore(redis_client=mock_redis)
        assert store.get_current_weights_stored() is None


class TestVixCache:
    """Tests for RedisStore.get_vix_cached() and set_vix_cached()."""

    def test_get_returns_float_when_key_exists(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = b"18.45"

        store = RedisStore(redis_client=mock_redis)
        result = store.get_vix_cached()

        assert result == pytest.approx(18.45)
        mock_redis.get.assert_called_once_with("macro:vix:latest")

    def test_get_returns_none_when_absent(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        store = RedisStore(redis_client=mock_redis)
        assert store.get_vix_cached() is None

    def test_set_stores_with_ttl(self):
        mock_redis = MagicMock()

        store = RedisStore(redis_client=mock_redis)
        store.set_vix_cached(18.45, ttl=3600)

        mock_redis.setex.assert_called_once_with("macro:vix:latest", 3600, "18.45")

    def test_get_returns_none_on_corrupted_data(self):
        """Returns None when cached VIX data is not a valid float."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = b"not-a-number"

        store = RedisStore(redis_client=mock_redis)
        result = store.get_vix_cached()

        assert result is None


class TestRegimeRedis:
    """Tests for RegimeState persistence and set_qc_sizing_multiplier."""

    def _make_state(self, regime="bear"):
        from src.models.regime import MacroSnapshot, RegimeState
        return RegimeState(
            regime=regime,
            multiplier=0.4,
            macro_snapshot=MacroSnapshot(vix=28.4, yield_curve=-0.6, spy_momentum_20d=-7.1),
            llm_outputs=[{"regime": regime, "reasoning": "test"}],
            detected_at=datetime(2026, 5, 5, 7, 0, 0, tzinfo=timezone.utc),
        )

    def test_set_regime_calls_setex(self):
        mock_redis = MagicMock()
        store = RedisStore(redis_client=mock_redis)
        state = self._make_state()

        store.set_regime(state, ttl=90000)

        mock_redis.setex.assert_called_once()
        key, ttl, value = mock_redis.setex.call_args[0]
        assert key == "regime:current"
        assert ttl == 90000
        assert "bear" in value

    def test_get_regime_roundtrip(self):
        mock_redis = MagicMock()
        state = self._make_state()
        mock_redis.get.return_value = state.model_dump_json().encode()

        store = RedisStore(redis_client=mock_redis)
        result = store.get_regime()

        assert result is not None
        assert result.regime == "bear"
        assert result.multiplier == pytest.approx(0.4)
        assert result.macro_snapshot.vix == pytest.approx(28.4)
        mock_redis.get.assert_called_once_with("regime:current")

    def test_get_regime_returns_none_when_absent(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        store = RedisStore(redis_client=mock_redis)
        assert store.get_regime() is None

    def test_get_regime_returns_none_on_corrupted_data(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = b"not-valid-json"

        store = RedisStore(redis_client=mock_redis)
        assert store.get_regime() is None

    def test_set_qc_sizing_multiplier(self):
        mock_redis = MagicMock()
        store = RedisStore(redis_client=mock_redis)

        store.set_qc_sizing_multiplier(0.4, ttl=90000)

        mock_redis.setex.assert_called_once_with("qc:sizing_multiplier", 90000, "0.4")

    def test_set_qc_sizing_multiplier_bull(self):
        mock_redis = MagicMock()
        store = RedisStore(redis_client=mock_redis)

        store.set_qc_sizing_multiplier(1.0, ttl=90000)

        mock_redis.setex.assert_called_once_with("qc:sizing_multiplier", 90000, "1.0")


class TestTelegramPollerOffset:
    """Tests for RedisStore.get_offset() and set_offset()."""

    def test_get_offset_returns_int_when_key_exists(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = b"12345"

        store = RedisStore(redis_client=mock_redis)
        result = store.get_offset()

        assert result == 12345
        mock_redis.get.assert_called_once_with("telegram:poller:offset")

    def test_get_offset_returns_none_when_absent(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        store = RedisStore(redis_client=mock_redis)
        assert store.get_offset() is None

    def test_set_offset_stores_value(self):
        mock_redis = MagicMock()

        store = RedisStore(redis_client=mock_redis)
        store.set_offset(12345)

        mock_redis.set.assert_called_once_with("telegram:poller:offset", 12345)


class TestDeleteWeightSuggestion:
    """Tests for RedisStore.delete_weight_suggestion()."""

    def test_deletes_suggestion_key(self):
        mock_redis = MagicMock()

        store = RedisStore(redis_client=mock_redis)
        store.delete_weight_suggestion()

        mock_redis.delete.assert_called_once_with("ensemble:weights:suggestion")


class TestDepsInitClose:
    """Test deps.init_redis() / deps.close_redis() lifecycle helpers."""

    def test_get_redis_store_raises_503_before_init(self):
        import src.api.deps as deps
        original = deps._redis_client
        deps._redis_client = None
        try:
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                deps.get_redis_store()
            assert exc_info.value.status_code == 503
        finally:
            deps._redis_client = original

    def test_init_redis_makes_get_redis_store_return_store(self):
        import src.api.deps as deps
        original = deps._redis_client
        mock_redis = MagicMock()
        try:
            deps.init_redis(mock_redis)
            store = deps.get_redis_store()
            from src.store.redis_store import RedisStore
            assert isinstance(store, RedisStore)
        finally:
            deps._redis_client = original

    def test_close_redis_clears_client(self):
        import src.api.deps as deps
        original = deps._redis_client
        mock_redis = MagicMock()
        try:
            deps.init_redis(mock_redis)
            deps.close_redis()
            assert deps._redis_client is None
            mock_redis.close.assert_called_once()
        finally:
            deps._redis_client = original


class TestWriteSentimentSignalId:
    """write_sentiment(result, signal_id=N) must embed signal_id in the Redis value."""

    def test_write_sentiment_includes_signal_id(self):
        import json
        from unittest.mock import MagicMock
        from src.store.redis_store import RedisStore
        from src.models.signals import SentimentResult
        from datetime import datetime, timezone

        mock_redis = MagicMock()
        store = RedisStore(redis_client=mock_redis)

        result = SentimentResult(
            symbol="AAPL", score=0.5, confidence=0.8,
            reasoning="bullish", model_id="ensemble:glm",
            generated_at=datetime(2026, 6, 5, 12, tzinfo=timezone.utc),
        )
        store.write_sentiment(result, signal_id=99)

        _, args, _ = mock_redis.setex.mock_calls[0]
        payload = json.loads(args[2])
        assert payload["signal_id"] == 99

    def test_write_sentiment_without_signal_id_omits_key(self):
        import json
        from unittest.mock import MagicMock
        from src.store.redis_store import RedisStore
        from src.models.signals import SentimentResult
        from datetime import datetime, timezone

        mock_redis = MagicMock()
        store = RedisStore(redis_client=mock_redis)

        result = SentimentResult(
            symbol="MSFT", score=0.3, confidence=0.7,
            reasoning="ok", model_id="finbert",
            generated_at=datetime(2026, 6, 5, 12, tzinfo=timezone.utc),
        )
        store.write_sentiment(result)

        _, args, _ = mock_redis.setex.mock_calls[0]
        payload = json.loads(args[2])
        assert "signal_id" not in payload


class TestFeedbackTtlRefresh:
    """#163: the feedback keys are written ONLY by a ratchet/recovery/decay event but
    carry a 96h TTL, so a sleeve at rest lets them expire — live this disarmed the S4
    entry gate from 2026-07-28 17:22 UTC with no self-heal. refresh_feedback_ttl
    re-arms the TTL without touching the stored values."""

    def test_extends_ttl_on_every_feedback_key_for_the_sleeve(self):
        mock_redis = MagicMock()
        mock_redis.expire.return_value = 1
        store = RedisStore(redis_client=mock_redis)

        existed = store.refresh_feedback_ttl(strategy="S4", ttl=345600)

        assert existed is True
        touched = {c.args[0] for c in mock_redis.expire.call_args_list}
        assert {
            "feedback:entry_threshold:S4",
            "feedback:state:S4",
        } <= touched
        assert all(c.args[1] == 345600 for c in mock_redis.expire.call_args_list)

    def test_does_not_rewrite_the_values(self):
        """The whole point: extend the lease, do not touch what is stored."""
        mock_redis = MagicMock()
        mock_redis.expire.return_value = 1
        store = RedisStore(redis_client=mock_redis)

        store.refresh_feedback_ttl(strategy="S1", ttl=1000)

        mock_redis.setex.assert_not_called()
        mock_redis.set.assert_not_called()

    def test_keeps_the_legacy_bare_mirror_alive_for_s4(self):
        """set_feedback_entry_threshold mirrors S4 onto the bare key, and
        get_feedback_entry_threshold falls back to it — so the mirror must not be
        allowed to outlive or predecease the per-strategy key."""
        mock_redis = MagicMock()
        mock_redis.expire.return_value = 1
        store = RedisStore(redis_client=mock_redis)

        store.refresh_feedback_ttl(strategy="S4", ttl=1000)

        touched = {c.args[0] for c in mock_redis.expire.call_args_list}
        assert {"feedback:entry_threshold"} <= touched

    def test_does_not_touch_the_bare_mirror_for_other_sleeves(self):
        mock_redis = MagicMock()
        mock_redis.expire.return_value = 1
        store = RedisStore(redis_client=mock_redis)

        store.refresh_feedback_ttl(strategy="S1", ttl=1000)

        touched = {c.args[0] for c in mock_redis.expire.call_args_list}
        assert "feedback:entry_threshold" not in touched

    def test_returns_false_when_the_key_has_already_expired(self):
        """Redis EXPIRE on a missing key is a no-op returning 0 — that is the signal
        the caller needs to restore the value instead of silently doing nothing."""
        mock_redis = MagicMock()
        mock_redis.expire.return_value = 0
        store = RedisStore(redis_client=mock_redis)

        assert store.refresh_feedback_ttl(strategy="S4", ttl=1000) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
