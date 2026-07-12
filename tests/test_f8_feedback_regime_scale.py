"""F8 — scheduler-side helper that reads per-strategy feedback:regime_scale.

`_read_feedback_regime_scales` reads feedback:regime_scale:S* (with legacy
feedback:regime_scale fallback) and returns {strategy_id: scale} for strategies
with a non-identity scale. It is fail-open: any error → {} → no de-risking
applied (safe default). The scheduler passes the dict to the orchestrator
(apply gated by loss_feedback.apply_regime_scale) and logs the shadow.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_reads_per_strategy_scales():
    from src.workers.portfolio_scheduler import _read_feedback_regime_scales

    fake_redis = MagicMock()
    fake_redis.get.side_effect = lambda key: {
        "feedback:regime_scale:S1": "0.60",
        "feedback:regime_scale:S4": "0.80",
    }.get(key)
    with patch("redis.Redis.from_url", return_value=fake_redis):
        out = _read_feedback_regime_scales("redis://localhost:6379/0", ["S1", "S4"])
    assert out == {"S1": 0.60, "S4": 0.80}


def test_legacy_key_is_fallback_when_per_strategy_absent():
    from src.workers.portfolio_scheduler import _read_feedback_regime_scales

    fake_redis = MagicMock()
    # S1 has a per-strategy key; S4 does not → falls back to legacy key
    fake_redis.get.side_effect = lambda key: {
        "feedback:regime_scale:S1": "0.50",
        "feedback:regime_scale": "0.70",
    }.get(key)
    with patch("redis.Redis.from_url", return_value=fake_redis):
        out = _read_feedback_regime_scales("redis://localhost:6379/0", ["S1", "S4"])
    assert out == {"S1": 0.50, "S4": 0.70}


def test_identity_scale_excluded():
    """A scale of 1.0 (at rest) is not returned — nothing to apply."""
    from src.workers.portfolio_scheduler import _read_feedback_regime_scales

    fake_redis = MagicMock()
    fake_redis.get.side_effect = lambda key: {
        "feedback:regime_scale:S1": "1.0",
        "feedback:regime_scale:S4": "0.80",
    }.get(key)
    with patch("redis.Redis.from_url", return_value=fake_redis):
        out = _read_feedback_regime_scales("redis://localhost:6379/0", ["S1", "S4"])
    assert out == {"S4": 0.80}


def test_fail_open_on_error_returns_empty():
    """Any Redis failure → {} (no de-risking applied — safe default)."""
    from src.workers.portfolio_scheduler import _read_feedback_regime_scales

    with patch("redis.Redis.from_url", side_effect=ConnectionError("no redis")):
        out = _read_feedback_regime_scales("redis://localhost:6379/0", ["S1", "S4"])
    assert out == {}


def test_empty_strategy_ids_returns_empty():
    from src.workers.portfolio_scheduler import _read_feedback_regime_scales
    with patch("redis.Redis.from_url") as mock_from_url:
        out = _read_feedback_regime_scales("redis://localhost:6379/0", [])
    assert out == {}
    mock_from_url.assert_not_called()


def test_corrupt_scale_value_skipped():
    """A non-numeric value is skipped, others still returned."""
    from src.workers.portfolio_scheduler import _read_feedback_regime_scales

    fake_redis = MagicMock()
    fake_redis.get.side_effect = lambda key: {
        "feedback:regime_scale:S1": "not-a-number",
        "feedback:regime_scale:S4": "0.80",
    }.get(key)
    with patch("redis.Redis.from_url", return_value=fake_redis):
        out = _read_feedback_regime_scales("redis://localhost:6379/0", ["S1", "S4"])
    assert out == {"S4": 0.80}