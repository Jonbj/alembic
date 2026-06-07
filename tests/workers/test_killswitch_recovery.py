"""Tests for condition-based kill-switch recovery in the execution worker."""
import json
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

# Stub heavy system deps so execution.py can be imported without the full stack.
_STUBS = [
    "redis", "alpaca", "alpaca.trading", "alpaca.trading.client",
    "alpaca.trading.enums", "alpaca.trading.requests",
    "alpaca.data", "alpaca.data.historical",
    "alpaca.data.models", "alpaca.data.requests",
    "alpaca.data.timeframe",
    "src.store.redis_store", "src.store.pg_store",
    "src.workers.celery_app", "src.notifications.telegram",
    "src.costs.calculator", "src.config",
    "celery", "celery.utils.log",
]
_freshly_stubbed = []
for _mod in _STUBS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()
        _freshly_stubbed.append(_mod)

# Redis.from_url must return a MagicMock, not raise
sys.modules["redis"].Redis = MagicMock

# src.config needs real attributes
sys.modules["src.config"].config = MagicMock(
    ALPACA_API_KEY="test", ALPACA_SECRET_KEY="test", REDIS_URL="redis://localhost"
)

# celery app stub
sys.modules["src.workers.celery_app"].app = MagicMock()
sys.modules["src.workers.celery_app"].app.task = lambda *a, **kw: (lambda f: f)

# TradeCostCalculator stub
sys.modules["src.costs.calculator"].TradeCostCalculator = MagicMock


def _make_redis(
    ks_active=True,
    operator_halt=False,
    activated_hours_ago=3.0,
    regime_mult=0.7,
):
    """Build a minimal RedisStore mock for recovery tests."""
    redis = MagicMock()

    # killswitch_active key
    redis._r.get.side_effect = lambda key: _redis_get(
        key, ks_active, operator_halt, activated_hours_ago
    )
    redis._r.delete = MagicMock()
    redis._r.set = MagicMock()
    redis._r.setex = MagicMock()

    # is_killswitch_active mirrors both keys
    redis.is_killswitch_active.return_value = ks_active or operator_halt
    redis.deactivate_killswitch = MagicMock()
    return redis


def _redis_get(key, ks_active, operator_halt, activated_hours_ago):
    if key == "killswitch_active":
        return b"1" if ks_active else None
    if key == "system:halted_by_operator":
        return b"1" if operator_halt else None
    if key == "killswitch_reason":
        if not ks_active:
            return None
        activated_at = (
            datetime.now(timezone.utc) - timedelta(hours=activated_hours_ago)
        ).isoformat()
        return json.dumps({"reason": "test", "activated_at": activated_at}).encode()
    return None


class TestTryKillswitchRecovery:
    def _call(self, redis, portfolio_value=98_000, last_equity=100_000, regime_mult=0.7, notifier=None):
        from src.workers.execution import _try_killswitch_recovery
        return _try_killswitch_recovery(redis, portfolio_value, last_equity, regime_mult, notifier)

    def test_deactivates_when_all_conditions_met(self):
        # drawdown = (100k - 98k) / 100k = 2% < 2.5% threshold, held 3h > 2h, regime=0.7
        redis = _make_redis(ks_active=True, operator_halt=False, activated_hours_ago=3.0)
        result = self._call(redis, portfolio_value=98_000, last_equity=100_000, regime_mult=0.7)
        assert result is True
        redis.deactivate_killswitch.assert_called_once()

    def test_does_not_deactivate_operator_halt(self):
        # operator halt must never be auto-cleared
        redis = _make_redis(ks_active=True, operator_halt=True, activated_hours_ago=5.0)
        result = self._call(redis, portfolio_value=99_000, last_equity=100_000, regime_mult=1.0)
        assert result is False
        redis.deactivate_killswitch.assert_not_called()

    def test_does_not_deactivate_when_no_killswitch(self):
        redis = _make_redis(ks_active=False, operator_halt=False)
        result = self._call(redis, portfolio_value=100_000, last_equity=100_000, regime_mult=1.0)
        assert result is False
        redis.deactivate_killswitch.assert_not_called()

    def test_does_not_deactivate_before_min_hold_time(self):
        # Only held 0.5h — below 2h minimum
        redis = _make_redis(ks_active=True, activated_hours_ago=0.5)
        result = self._call(redis, portfolio_value=98_500, last_equity=100_000, regime_mult=0.7)
        assert result is False
        redis.deactivate_killswitch.assert_not_called()

    def test_does_not_deactivate_when_drawdown_still_high(self):
        # drawdown = (100k - 96k) / 100k = 4% > 2.5% threshold
        redis = _make_redis(ks_active=True, activated_hours_ago=3.0)
        result = self._call(redis, portfolio_value=96_000, last_equity=100_000, regime_mult=0.7)
        assert result is False
        redis.deactivate_killswitch.assert_not_called()

    def test_does_not_deactivate_in_panic_regime(self):
        # regime_mult=0.2 (high_vol / panic) — blocked
        redis = _make_redis(ks_active=True, activated_hours_ago=3.0)
        result = self._call(redis, portfolio_value=98_500, last_equity=100_000, regime_mult=0.2)
        assert result is False
        redis.deactivate_killswitch.assert_not_called()

    def test_deactivates_when_disabled_returns_false(self):
        redis = _make_redis(ks_active=True, activated_hours_ago=4.0)
        with patch("src.workers.execution._load_killswitch_recovery_config",
                   return_value={"enabled": False}):
            result = self._call(redis, portfolio_value=98_000, last_equity=100_000, regime_mult=0.7)
        assert result is False
        redis.deactivate_killswitch.assert_not_called()

    def test_boundary_drawdown_just_below_threshold(self):
        # drawdown = (100k - 97_501) / 100k = 2.499% < 2.5% → should unlock
        redis = _make_redis(ks_active=True, activated_hours_ago=3.0)
        result = self._call(redis, portfolio_value=97_501, last_equity=100_000, regime_mult=0.7)
        assert result is True

    def test_boundary_drawdown_at_threshold(self):
        # drawdown = (100k - 97_500) / 100k = 2.5% >= 2.5% → should NOT unlock
        redis = _make_redis(ks_active=True, activated_hours_ago=3.0)
        result = self._call(redis, portfolio_value=97_500, last_equity=100_000, regime_mult=0.7)
        assert result is False

    def test_sideways_regime_allowed(self):
        # regime_mult=0.7 (sideways) — not panic, should unlock if other conditions ok
        redis = _make_redis(ks_active=True, activated_hours_ago=3.0)
        result = self._call(redis, portfolio_value=98_000, last_equity=100_000, regime_mult=0.7)
        assert result is True

    def test_zero_last_equity_skips_recovery(self):
        # last_equity=0 means we can't compute drawdown — skip silently
        redis = _make_redis(ks_active=True, activated_hours_ago=3.0)
        result = self._call(redis, portfolio_value=98_000, last_equity=0.0, regime_mult=0.7)
        assert result is False
        redis.deactivate_killswitch.assert_not_called()
