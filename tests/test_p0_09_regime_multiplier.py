"""P0-09 — Regime multiplier applied, not hardcoded to 1.0.

Problem: portfolio_scheduler._run_cycle_inner passes regime_mult=1.0 to
write_execution_decision() and open_trade() even when the RedisStore
holds a non-1.0 multiplier (e.g. 0.2 for high_vol, 0.5 for caution).

This means the execution_decisions and trades tables show the wrong
regime multiplier — analytics and audit logs are inaccurate — and
position sizing is NOT scaled by regime (the actual sizing calculation
may or may not use regime_mult, but the recorded value is wrong for sure).

Fix: _run_cycle_inner reads regime:current from Redis and passes the
actual multiplier to write_execution_decision() and open_trade().
Falls back to 0.2 (fail-conservative, matching execution.py) when the
key is absent.

Acceptance: test_regime_multiplier_applied passes.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, call, patch

import pytest


def _regime_state_json(multiplier: float) -> str:
    return json.dumps({
        "regime": "caution" if multiplier == 0.5 else "high_vol",
        "multiplier": multiplier,
        "vix": 25.0,
        "yield_curve": -0.1,
        "spy_momentum": -2.0,
        "timestamp": "2026-06-19T09:00:00+00:00",
        "sources": [],
    })


class TestRegimeMultiplierRead:
    """_get_regime_multiplier_from_redis must read Redis and fallback correctly."""

    def test_reads_multiplier_from_redis(self):
        """When regime:current is set, return its multiplier field."""
        from src.workers.portfolio_scheduler import _get_regime_multiplier_from_redis

        with patch("redis.Redis") as mock_cls:
            inst = MagicMock()
            inst.get.return_value = _regime_state_json(0.5)
            mock_cls.from_url.return_value = inst
            result = _get_regime_multiplier_from_redis("redis://localhost:6379/0")

        assert result == pytest.approx(0.5)

    def test_falls_back_to_conservative_when_key_absent(self):
        """When regime:current is absent, return 0.2 (fail-conservative, not 1.0)."""
        from src.workers.portfolio_scheduler import _get_regime_multiplier_from_redis

        with patch("redis.Redis") as mock_cls:
            inst = MagicMock()
            inst.get.return_value = None
            mock_cls.from_url.return_value = inst
            result = _get_regime_multiplier_from_redis("redis://localhost:6379/0")

        assert result == pytest.approx(0.2), (
            "When regime:current is absent, must use 0.2 (high_vol fallback), NOT 1.0. "
            "1.0 would mean 'full allocation' which is incorrect without a known regime."
        )

    def test_falls_back_when_redis_unreachable(self):
        """When Redis is unreachable, return 0.2 (fail-conservative)."""
        from src.workers.portfolio_scheduler import _get_regime_multiplier_from_redis

        with patch("redis.Redis") as mock_cls:
            mock_cls.from_url.side_effect = ConnectionError("down")
            result = _get_regime_multiplier_from_redis("redis://localhost:6379/0")

        assert result == pytest.approx(0.2)

    def test_falls_back_when_json_corrupt(self):
        """Corrupt JSON in regime:current → return 0.2 (fail-conservative)."""
        from src.workers.portfolio_scheduler import _get_regime_multiplier_from_redis

        with patch("redis.Redis") as mock_cls:
            inst = MagicMock()
            inst.get.return_value = "{not valid json"
            mock_cls.from_url.return_value = inst
            result = _get_regime_multiplier_from_redis("redis://localhost:6379/0")

        assert result == pytest.approx(0.2)

    def test_high_vol_multiplier_02(self):
        """high_vol regime with multiplier=0.2 is read correctly."""
        from src.workers.portfolio_scheduler import _get_regime_multiplier_from_redis

        with patch("redis.Redis") as mock_cls:
            inst = MagicMock()
            inst.get.return_value = _regime_state_json(0.2)
            mock_cls.from_url.return_value = inst
            result = _get_regime_multiplier_from_redis("redis://localhost:6379/0")

        assert result == pytest.approx(0.2)

    def test_normal_multiplier_10(self):
        """Normal regime with multiplier=1.0 reads 1.0."""
        from src.workers.portfolio_scheduler import _get_regime_multiplier_from_redis

        with patch("redis.Redis") as mock_cls:
            inst = MagicMock()
            inst.get.return_value = json.dumps({
                "regime": "normal",
                "multiplier": 1.0,
                "vix": 15.0,
                "yield_curve": 0.3,
                "spy_momentum": 2.0,
                "timestamp": "2026-06-19T09:00:00+00:00",
                "sources": [],
            })
            mock_cls.from_url.return_value = inst
            result = _get_regime_multiplier_from_redis("redis://localhost:6379/0")

        assert result == pytest.approx(1.0)
