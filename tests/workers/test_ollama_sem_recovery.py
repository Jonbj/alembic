"""Tests for automatic Ollama semaphore slot-leak recovery.

When all semaphore slots are leaked (SoftTimeLimitExceeded kills a task
mid-inference), the next run_sentiment_worker invocation resets the semaphore
so inference can resume automatically — no manual intervention needed.

Safety guarantee: worker-inference has concurrency=1, so if a new task is
starting, the previous one has already terminated (dead = no longer holding
slots). Resetting at task startup is always safe.
"""
from unittest.mock import MagicMock


def _redis(per_chiave):
    """Redis finto con LLEN diverso per pool: la recovery ora ne sorveglia due."""
    redis = MagicMock()
    redis.llen.side_effect = lambda k: per_chiave.get(k, 0)
    redis.exists.return_value = 1
    return redis


def test_resets_semaphore_when_all_slots_leaked():
    """0 slots + init flag present → DEL both keys so next acquire re-initializes.

    #368: ora vale per ENTRAMBI i pool, non solo per quello live.
    """
    from src.workers.sentiment import _recover_ollama_semaphore_if_leaked

    redis = _redis({"ollama:sem": 0, "ollama:sem:shadow": 0})

    _recover_ollama_semaphore_if_leaked(redis)

    chiavi = {c.args for c in redis.delete.call_args_list}
    assert ("ollama:sem", "ollama:sem:init") in chiavi
    assert ("ollama:sem:shadow", "ollama:sem:shadow:init") in chiavi


def test_no_action_when_slots_available():
    """Dotazione piena su entrambi i pool → sani, non toccarli."""
    from src.workers.sentiment import _recover_ollama_semaphore_if_leaked

    redis = _redis({"ollama:sem": 2, "ollama:sem:shadow": 3})

    _recover_ollama_semaphore_if_leaked(redis)

    redis.delete.assert_not_called()


def test_no_action_on_first_ever_init():
    """Init flag absent (semaphore never initialized) → nothing to recover."""
    from src.workers.sentiment import _recover_ollama_semaphore_if_leaked

    mock_redis = MagicMock()
    mock_redis.llen.return_value = 0
    mock_redis.exists.return_value = 0  # no init flag = first run ever

    _recover_ollama_semaphore_if_leaked(mock_redis)

    mock_redis.delete.assert_not_called()


def test_partial_slot_loss_is_recovered():
    """#368: una perdita PARZIALE ora viene ripristinata — inversione voluta.

    La versione precedente lasciava stare 1-2 slot mancanti «per evitare falsi
    positivi». Ma il falso positivo che si temeva non puo' esistere: a
    concurrency=1, all'avvio del task nessun altro detiene token, quindi un
    ammanco e' una perdita per definizione.

    Il costo del vecchio comportamento non era teorico: un pool che scende a
    1 slot su 3 non blocca nulla — quindi nessuno se ne accorge — ma ha un
    terzo della capacita', e continua a perderne finche' arriva a zero. E' la
    traiettoria che ha ucciso il pool shadow.
    """
    from src.workers.sentiment import _recover_ollama_semaphore_if_leaked

    redis = _redis({"ollama:sem": 2, "ollama:sem:shadow": 1})

    _recover_ollama_semaphore_if_leaked(redis)

    chiavi = {c.args for c in redis.delete.call_args_list}
    assert chiavi == {("ollama:sem:shadow", "ollama:sem:shadow:init")}, (
        "deve ripristinare solo il pool in ammanco, non quello sano"
    )


def test_redis_error_does_not_crash_worker():
    """If Redis is unavailable during check, the worker must still proceed."""
    from src.workers.sentiment import _recover_ollama_semaphore_if_leaked

    mock_redis = MagicMock()
    mock_redis.llen.side_effect = Exception("Redis connection refused")

    # Must not raise
    _recover_ollama_semaphore_if_leaked(mock_redis)
