"""Tests for Redis store - fallback counter verification."""

import json
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

    def test_is_killswitch_active(self):
        """Test checking kill-switch status."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = b"1"

        store = RedisStore(redis_client=mock_redis)
        assert store.is_killswitch_active() is True

    def test_is_killswitch_inactive(self):
        """Test checking kill-switch status when inactive."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        store = RedisStore(redis_client=mock_redis)
        assert store.is_killswitch_active() is False


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
