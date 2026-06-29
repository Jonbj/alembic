"""Tests for automatic Ollama semaphore slot-leak recovery.

When all semaphore slots are leaked (SoftTimeLimitExceeded kills a task
mid-inference), the next run_sentiment_worker invocation resets the semaphore
so inference can resume automatically — no manual intervention needed.

Safety guarantee: worker-inference has concurrency=1, so if a new task is
starting, the previous one has already terminated (dead = no longer holding
slots). Resetting at task startup is always safe.
"""
from unittest.mock import MagicMock, call


def test_resets_semaphore_when_all_slots_leaked():
    """0 slots + init flag present → DEL both keys so next acquire re-initializes."""
    from src.workers.sentiment import _recover_ollama_semaphore_if_leaked

    mock_redis = MagicMock()
    mock_redis.llen.return_value = 0    # no slots available
    mock_redis.exists.return_value = 1  # init flag set (semaphore was initialized)

    _recover_ollama_semaphore_if_leaked(mock_redis)

    mock_redis.delete.assert_called_once_with("ollama:sem", "ollama:sem:init")


def test_no_action_when_slots_available():
    """Slots still available → semaphore is healthy, do not touch it."""
    from src.workers.sentiment import _recover_ollama_semaphore_if_leaked

    mock_redis = MagicMock()
    mock_redis.llen.return_value = 2    # 2 of 3 slots free (1 in use)
    mock_redis.exists.return_value = 1

    _recover_ollama_semaphore_if_leaked(mock_redis)

    mock_redis.delete.assert_not_called()


def test_no_action_on_first_ever_init():
    """Init flag absent (semaphore never initialized) → nothing to recover."""
    from src.workers.sentiment import _recover_ollama_semaphore_if_leaked

    mock_redis = MagicMock()
    mock_redis.llen.return_value = 0
    mock_redis.exists.return_value = 0  # no init flag = first run ever

    _recover_ollama_semaphore_if_leaked(mock_redis)

    mock_redis.delete.assert_not_called()


def test_partial_slot_loss_not_recovered():
    """1 slot still present (partial leak) → leave it alone, avoid false positives."""
    from src.workers.sentiment import _recover_ollama_semaphore_if_leaked

    mock_redis = MagicMock()
    mock_redis.llen.return_value = 1    # 1 slot remains (2 leaked)
    mock_redis.exists.return_value = 1

    _recover_ollama_semaphore_if_leaked(mock_redis)

    mock_redis.delete.assert_not_called()


def test_redis_error_does_not_crash_worker():
    """If Redis is unavailable during check, the worker must still proceed."""
    from src.workers.sentiment import _recover_ollama_semaphore_if_leaked

    mock_redis = MagicMock()
    mock_redis.llen.side_effect = Exception("Redis connection refused")

    # Must not raise
    _recover_ollama_semaphore_if_leaked(mock_redis)
