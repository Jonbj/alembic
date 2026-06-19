"""Alerting primitives for operator safety.

Each function returns True (alert!) / False (all-clear) so callers can
decide how to route the notification (Telegram, log, dashboard flag).
"""
from __future__ import annotations

from datetime import datetime, timezone


def check_worker_beat_lag(last_beat_ts: datetime, threshold_minutes: float) -> bool:
    """Return True when the most-recent worker heartbeat is older than threshold.

    A stale heartbeat means the Celery beat scheduler or inference worker is
    not running — signals are not being generated.

    Args:
        last_beat_ts:       Timestamp of the last received heartbeat (must be tz-aware).
        threshold_minutes:  Alert fires when beat age exceeds this value.
    """
    now = datetime.now(timezone.utc)
    lag_minutes = (now - last_beat_ts).total_seconds() / 60.0
    return lag_minutes > threshold_minutes


def check_fallback_rate(fallback_rate: float, threshold: float) -> bool:
    """Return True when the LLM-ensemble fallback rate exceeds threshold.

    A high fallback rate means most sentiment signals are coming from the
    FinBERT-only path (Ollama/Kimi ensemble unavailable), reducing signal quality.

    Args:
        fallback_rate:  Fraction of signals that fell back to FinBERT (0–1).
        threshold:      Alert fires when fallback_rate exceeds this value.
    """
    return fallback_rate > threshold
