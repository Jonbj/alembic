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


def check_signal_divergence(
    paper_signals: set[str],
    live_signals: set[str],
    threshold: float = 0.8,
) -> bool:
    """Return True when paper and live signal sets diverge beyond threshold.

    Measures Jaccard-style overlap: |intersection| / |union|.
    Both-empty is treated as identical (no divergence → False).

    Args:
        paper_signals:  Set of ticker symbols in paper-trading signal.
        live_signals:   Set of ticker symbols that live would trade.
        threshold:      Alert fires when overlap fraction < threshold.
    """
    if not paper_signals and not live_signals:
        return False
    union = paper_signals | live_signals
    intersection = paper_signals & live_signals
    overlap = len(intersection) / len(union)
    return overlap < threshold


def check_execution_divergence(
    paper_fill_ratio: float,
    live_fill_ratio: float,
    threshold: float = 0.20,
) -> bool:
    """Return True when paper and live fill ratios diverge beyond threshold.

    Args:
        paper_fill_ratio:  Fraction of paper order filled (0–1).
        live_fill_ratio:   Fraction of live order filled (0–1).
        threshold:         Alert fires when |paper - live| > threshold.
    """
    return abs(paper_fill_ratio - live_fill_ratio) > threshold
