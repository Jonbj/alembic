"""Tests for condition-based kill-switch recovery in the execution worker."""
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

# Modules that must be stubbed so execution.py can be imported without the full stack.
# Installed inside _apply_module_stubs and removed on teardown — no module-level side effects.
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


@pytest.fixture(autouse=True, scope="module")
def _apply_module_stubs():
    """Install and restore all stubs for this module, preventing session contamination."""
    # Install stubs for modules not yet present; track what we freshly add.
    freshly_stubbed = []
    for mod in _STUBS:
        if mod not in sys.modules:
            sys.modules[mod] = MagicMock()
            freshly_stubbed.append(mod)

    redis_mod = sys.modules["redis"]
    config_mod = sys.modules["src.config"]
    celery_app_mod = sys.modules["src.workers.celery_app"]
    cost_mod = sys.modules["src.costs.calculator"]

    saved_redis_cls = getattr(redis_mod, "Redis", None)
    saved_config = getattr(config_mod, "config", None)
    saved_app = getattr(celery_app_mod, "app", None)
    saved_cost_calc = getattr(cost_mod, "TradeCostCalculator", None)

    redis_mod.Redis = MagicMock
    config_mod.config = MagicMock(
        ALPACA_API_KEY="test", ALPACA_SECRET_KEY="test", REDIS_URL="redis://localhost"
    )
    stub_app = MagicMock()
    stub_app.task = lambda *a, **kw: (lambda f: f)
    celery_app_mod.app = stub_app
    cost_mod.TradeCostCalculator = MagicMock

    yield

    # Restore attribute overwrites
    redis_mod.Redis = saved_redis_cls
    config_mod.config = saved_config
    celery_app_mod.app = saved_app
    cost_mod.TradeCostCalculator = saved_cost_calc

    # Remove freshly-installed module stubs so they don't leak into later test files
    for mod in freshly_stubbed:
        sys.modules.pop(mod, None)


def _make_redis(
    ks_active=True,
    operator_halt=False,
    activated_hours_ago=3.0,
    regime_mult=0.7,
):
    """Build a minimal RedisStore mock for recovery tests using public methods."""
    redis = MagicMock()

    redis.is_drawdown_killswitch_active.return_value = ks_active
    redis.is_operator_halted.return_value = operator_halt
    redis.is_killswitch_active.return_value = ks_active or operator_halt

    if ks_active:
        activated_at = (
            datetime.now(timezone.utc) - timedelta(hours=activated_hours_ago)
        ).isoformat()
        redis.get_killswitch_reason.return_value = {
            "reason": "test",
            "activated_at": activated_at,
        }
    else:
        redis.get_killswitch_reason.return_value = None

    redis.deactivate_killswitch = MagicMock()
    return redis


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
