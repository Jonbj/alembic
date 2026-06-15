"""Tests for signal velocity scoring."""
import json
import pytest
from unittest.mock import MagicMock


class TestRedisStoreSignalHistory:
    def test_append_signal_history_pushes_and_trims(self):
        """append_signal_history deve LPUSH e mantenere max 5 elementi."""
        from src.store.redis_store import RedisStore

        store = RedisStore.__new__(RedisStore)
        store._r = MagicMock()

        store.append_signal_history("AAPL", 0.6)

        store._r.lpush.assert_called_once()
        call_args = store._r.lpush.call_args[0]
        assert call_args[0] == "signal:AAPL:history"
        assert json.loads(call_args[1])["score"] == 0.6

        store._r.ltrim.assert_called_once_with("signal:AAPL:history", 0, 4)

    def test_get_signal_history_returns_list_of_scores(self):
        """get_signal_history deve ritornare lista di float."""
        from src.store.redis_store import RedisStore

        store = RedisStore.__new__(RedisStore)
        store._r = MagicMock()
        store._r.lrange.return_value = [
            json.dumps({"score": 0.6}),
            json.dumps({"score": 0.3}),
            json.dumps({"score": 0.1}),
        ]

        result = store.get_signal_history("AAPL", n=3)

        assert result == [0.6, 0.3, 0.1]
        store._r.lrange.assert_called_once_with("signal:AAPL:history", 0, 2)

    def test_get_signal_history_returns_empty_on_no_data(self):
        """Nessun dato Redis → lista vuota."""
        from src.store.redis_store import RedisStore

        store = RedisStore.__new__(RedisStore)
        store._r = MagicMock()
        store._r.lrange.return_value = []

        result = store.get_signal_history("NVDA", n=3)
        assert result == []


class TestComputeSignalVelocity:
    def test_positive_velocity_returns_boost(self):
        """Score crescente → multiplier = 1 + boost."""
        from src.workers.portfolio_scheduler import _compute_signal_velocity
        mock_redis = MagicMock()
        # history newest first: 0.6, 0.3, 0.1 → velocity = 0.6 - 0.1 = 0.5 > 0.30
        mock_redis.lrange.return_value = [
            json.dumps({"score": 0.6}),
            json.dumps({"score": 0.3}),
            json.dumps({"score": 0.1}),
        ]

        multiplier = _compute_signal_velocity("AAPL", mock_redis, threshold=0.30, boost=0.20)

        assert multiplier == pytest.approx(1.20)

    def test_negative_velocity_returns_penalty(self):
        """Score decrescente → multiplier = 1 - boost."""
        from src.workers.portfolio_scheduler import _compute_signal_velocity
        mock_redis = MagicMock()
        # velocity = -0.5 - 0.1 = -0.6 < -0.30
        mock_redis.lrange.return_value = [
            json.dumps({"score": -0.5}),
            json.dumps({"score": -0.2}),
            json.dumps({"score": 0.1}),
        ]

        multiplier = _compute_signal_velocity("AAPL", mock_redis, threshold=0.30, boost=0.20)

        assert multiplier == pytest.approx(0.80)

    def test_stable_signal_returns_neutral(self):
        """Score stabile → multiplier = 1.0."""
        from src.workers.portfolio_scheduler import _compute_signal_velocity
        mock_redis = MagicMock()
        mock_redis.lrange.return_value = [
            json.dumps({"score": 0.5}),
            json.dumps({"score": 0.5}),
            json.dumps({"score": 0.5}),
        ]

        multiplier = _compute_signal_velocity("AAPL", mock_redis, threshold=0.30, boost=0.20)

        assert multiplier == pytest.approx(1.0)

    def test_insufficient_history_returns_neutral(self):
        """Meno di 2 punti in history → multiplier = 1.0."""
        from src.workers.portfolio_scheduler import _compute_signal_velocity
        mock_redis = MagicMock()
        mock_redis.lrange.return_value = [json.dumps({"score": 0.5})]

        multiplier = _compute_signal_velocity("AAPL", mock_redis, threshold=0.30, boost=0.20)

        assert multiplier == pytest.approx(1.0)
