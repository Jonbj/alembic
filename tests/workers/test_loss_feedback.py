"""Tests for run_loss_feedback_check (Phase B — Feedback Loop on Losses).

Covers:
  - Loss detection: consecutive losses, rolling P&L
  - Threshold and regime scale adjustments
  - Cooldown enforcement
  - Recovery (consecutive wins)
  - Disabled flag
  - No trades / insufficient trades
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.workers.performance import (
    _count_consecutive_losses,
    _count_consecutive_wins,
    _load_loss_feedback_config,
    run_loss_feedback_check,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_trade(net_pnl: float) -> dict:
    return {"net_pnl": net_pnl, "symbol": "AAPL", "entry_time": datetime.now(timezone.utc).isoformat()}


def _make_trades(pnls: list[float]) -> list[dict]:
    """Most-recent first (matching fetch_trades ordering)."""
    return [_make_trade(p) for p in pnls]


# ---------------------------------------------------------------------------
# Unit: consecutive loss/win counters
# ---------------------------------------------------------------------------

def test_consecutive_losses_all_losses():
    trades = _make_trades([-10, -5, -3])
    assert _count_consecutive_losses(trades) == 3


def test_consecutive_losses_win_breaks_streak():
    trades = _make_trades([-10, -5, 3, -2])
    assert _count_consecutive_losses(trades) == 2


def test_consecutive_losses_no_losses():
    trades = _make_trades([10, 5, 3])
    assert _count_consecutive_losses(trades) == 0


def test_consecutive_losses_empty():
    assert _count_consecutive_losses([]) == 0


def test_consecutive_wins_all_wins():
    trades = _make_trades([10, 5, 3])
    assert _count_consecutive_wins(trades) == 3


def test_consecutive_wins_loss_breaks_streak():
    trades = _make_trades([10, 5, -3, 2])
    assert _count_consecutive_wins(trades) == 2


def test_consecutive_wins_no_wins():
    trades = _make_trades([-10, -5, -3])
    assert _count_consecutive_wins(trades) == 0


# ---------------------------------------------------------------------------
# Unit: config loader
# ---------------------------------------------------------------------------

def test_load_loss_feedback_config_returns_defaults_on_missing_section():
    with patch("builtins.open", side_effect=FileNotFoundError):
        cfg = _load_loss_feedback_config()
    assert cfg["consecutive_loss_trigger"] == 3
    assert cfg["threshold_step"] == pytest.approx(0.05)
    assert cfg["threshold_baseline"] == pytest.approx(0.30)


# ---------------------------------------------------------------------------
# Integration: run_loss_feedback_check
# ---------------------------------------------------------------------------

def _default_cfg():
    return {
        "enabled": True,
        "consecutive_loss_trigger": 3,
        "rolling_pnl_window": 5,
        "rolling_pnl_drawdown_pct": 0.005,
        "rolling_pnl_trigger_floor_usd": 250.0,
        "threshold_step": 0.05,
        "threshold_max": 0.60,
        "threshold_baseline": 0.30,
        "threshold_decay_hours": 24,
        "regime_scale_factor": 0.80,
        "regime_min_scale": 0.20,
        "cooldown_hours": 4,
        "recovery_win_streak": 3,
        "feedback_ttl_hours": 48,
    }


def _patched_run(
    trades: list[dict],
    *,
    redis_threshold: float | None = None,
    redis_scale: float | None = None,
    redis_state: dict | None = None,
    redis_equity: float | None = None,
    cfg_override: dict | None = None,
):
    """Helper that patches all external dependencies and runs the task."""
    cfg = {**_default_cfg(), **(cfg_override or {})}

    mock_redis = MagicMock()
    mock_redis.get_feedback_entry_threshold.return_value = redis_threshold
    mock_redis.get_feedback_regime_scale.return_value = redis_scale
    mock_redis.get_feedback_state.return_value = redis_state
    mock_redis.get_portfolio_value.return_value = redis_equity

    mock_pg = MagicMock()
    mock_pg.fetch_trades.return_value = trades

    with (
        patch("src.workers.performance._load_loss_feedback_config", return_value=cfg),
        patch("src.workers.performance.RedisStore", return_value=mock_redis),
        patch("src.workers.performance.PostgreSQLStore", return_value=mock_pg),
        patch("src.workers.performance.TelegramNotifier"),
        patch("asyncio.run"),
    ):
        result = run_loss_feedback_check()

    return result, mock_redis


class TestDisabled:
    def test_disabled_flag_returns_skipped(self):
        result, _ = _patched_run([], cfg_override={"enabled": False})
        assert result == {"skipped": True, "reason": "disabled"}


class TestNoTrades:
    def test_no_trades_returns_skipped(self):
        result, _ = _patched_run([])
        assert result == {"skipped": True, "reason": "no_closed_trades"}


class TestTriggerOnConsecutiveLosses:
    def test_3_consecutive_losses_triggers(self):
        trades = _make_trades([-5, -10, -3, 8, 2])
        result, mock_redis = _patched_run(trades)

        assert result["triggered"] is True
        assert result["adjusted"] is True
        assert result["consecutive_losses"] == 3
        mock_redis.set_feedback_entry_threshold.assert_called_once()
        mock_redis.set_feedback_regime_scale.assert_called_once()

    def test_threshold_raised_by_step(self):
        trades = _make_trades([-5, -10, -3, 8, 2])
        result, _ = _patched_run(trades, redis_threshold=0.30)

        assert result["new_threshold"] == pytest.approx(0.35)

    def test_regime_scale_reduced_by_factor(self):
        trades = _make_trades([-5, -10, -3, 8, 2])
        result, _ = _patched_run(trades, redis_scale=1.0)

        assert result["new_scale"] == pytest.approx(0.80)

    def test_2_consecutive_losses_does_not_trigger(self):
        # 2 consecutive losses (below trigger=3) AND positive rolling P&L → no trigger
        trades = _make_trades([-5, -10, 8, 9, 10])
        result, _ = _patched_run(trades)

        assert result["triggered"] is False
        assert result["adjusted"] is False


class TestTriggerOnNegativeRollingPnl:
    def test_negative_rolling_pnl_triggers(self):
        # Rolling P&L must exceed 0.5% of equity ($100K * 0.005 = $500).
        trades = _make_trades([-600, 3, -2, 1, -2])
        # consecutive losses = 1 (below trigger=3), but rolling P&L drawdown > 0.5%
        result, mock_redis = _patched_run(trades, redis_equity=100_000.0)

        assert result["triggered"] is True
        assert result["adjusted"] is True
        assert result["rolling_net_pnl"] < -500

    def test_small_negative_rolling_pnl_does_not_trigger(self):
        """Noise-level loss (-$208 on $110K) must NOT raise the gate."""
        trades = _make_trades([-208, 3, -2, 1, -2])
        result, _ = _patched_run(trades, redis_equity=100_000.0)

        assert result["triggered"] is False
        assert result["adjusted"] is False

    def test_floor_used_when_equity_missing(self):
        """When portfolio:value is absent, the absolute floor applies."""
        # Sum -315 over window triggers (floor $250); sum -115 does not.
        result_hi, _ = _patched_run(_make_trades([-400, 40, 30, 10, 5]))
        assert result_hi["triggered"] is True
        result_lo, _ = _patched_run(_make_trades([-200, 40, 30, 10, 5]))
        assert result_lo["triggered"] is False

    def test_zero_drawdown_pct_disables_rolling_pnl_trigger(self):
        """rolling_pnl_drawdown_pct=0 must disable the rolling-P&L trigger entirely.

        Only consecutive losses should still be able to trigger.
        """
        # Large rolling loss but no consecutive losses and pct=0 → no trigger.
        trades = _make_trades([-600, 40, 30, -20, -50])
        result, _ = _patched_run(
            trades,
            redis_equity=100_000.0,
            cfg_override={"rolling_pnl_drawdown_pct": 0.0},
        )
        assert result["triggered"] is False
        assert result["adjusted"] is False
        assert result["rolling_loss_limit"] is None

    def test_positive_rolling_pnl_no_trigger(self):
        trades = _make_trades([5, 3, 2, -1, 1])
        result, _ = _patched_run(trades, redis_equity=100_000.0)

        assert result["triggered"] is False
        assert result["adjusted"] is False


class TestThresholdCap:
    def test_threshold_capped_at_max(self):
        trades = _make_trades([-5, -10, -3, 8, 2])
        # Already near max
        result, _ = _patched_run(trades, redis_threshold=0.58)

        assert result["new_threshold"] == pytest.approx(0.60)  # capped

    def test_regime_scale_floored_at_min(self):
        trades = _make_trades([-5, -10, -3, 8, 2])
        result, _ = _patched_run(trades, redis_scale=0.22)

        assert result["new_scale"] == pytest.approx(0.20)  # floored at regime_min_scale=0.20


class TestCooldown:
    def test_adjustment_skipped_within_cooldown(self):
        trades = _make_trades([-5, -10, -3, 8, 2])
        recent_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        result, mock_redis = _patched_run(
            trades,
            redis_state={"last_adjustment_ts": recent_ts},
        )

        assert result["cooldown_ok"] is False
        assert result["adjusted"] is False
        mock_redis.set_feedback_entry_threshold.assert_not_called()

    def test_adjustment_allowed_after_cooldown(self):
        trades = _make_trades([-5, -10, -3, 8, 2])
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        result, mock_redis = _patched_run(
            trades,
            redis_state={"last_adjustment_ts": old_ts},
        )

        assert result["cooldown_ok"] is True
        assert result["adjusted"] is True


class TestRecovery:
    def test_win_streak_steps_threshold_down(self):
        # 3 consecutive wins, threshold above baseline
        trades = _make_trades([5, 10, 3, -1, 2])
        result, mock_redis = _patched_run(
            trades,
            redis_threshold=0.40,  # above baseline 0.30
            redis_scale=0.80,
        )

        assert result["triggered"] is False
        assert result["recovered"] is True
        assert result["new_threshold"] == pytest.approx(0.35)

    def test_no_recovery_when_already_at_baseline(self):
        trades = _make_trades([5, 10, 3, 2, 1])
        result, mock_redis = _patched_run(
            trades,
            redis_threshold=0.30,  # already at baseline
            redis_scale=1.0,
        )

        assert result["recovered"] is False
        mock_redis.set_feedback_entry_threshold.assert_not_called()

    def test_insufficient_win_streak_no_recovery(self):
        # Only 2 consecutive wins, need 3
        trades = _make_trades([5, 10, -1, 2, 1])
        result, _ = _patched_run(
            trades,
            redis_threshold=0.40,
            cfg_override={"recovery_win_streak": 3},
        )

        assert result["recovered"] is False


class TestTemporalDecay:
    def test_threshold_decays_after_quiet_period(self):
        """After threshold_decay_hours with no trigger, the gate lowers by one step."""
        # 2 consecutive wins only, so recovery-by-wins does not fire.
        trades = _make_trades([5, 3, -1, 2, 1])
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        result, mock_redis = _patched_run(
            trades,
            redis_threshold=0.40,
            redis_state={"last_adjustment_ts": old_ts, "reason": "triggered"},
        )

        assert result["decayed"] is True
        assert result["new_threshold"] == pytest.approx(0.35)
        mock_redis.set_feedback_entry_threshold.assert_called_once()

    def test_no_decay_within_decay_window(self):
        """If the last adjustment is recent, no temporal decay occurs."""
        trades = _make_trades([5, 3, -1, 2, 1])
        recent_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        result, mock_redis = _patched_run(
            trades,
            redis_threshold=0.40,
            redis_state={"last_adjustment_ts": recent_ts, "reason": "triggered"},
        )

        assert result["decayed"] is False
        mock_redis.set_feedback_entry_threshold.assert_not_called()

    def test_no_decay_when_already_at_baseline(self):
        trades = _make_trades([5, 3, -1, 2, 1])
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        result, _ = _patched_run(
            trades,
            redis_threshold=0.30,
            redis_state={"last_adjustment_ts": old_ts, "reason": "triggered"},
        )

        assert result["decayed"] is False

    def test_decay_sends_baseline_reset_notification(self):
        """When decay reaches baseline, a Telegram reset alert is sent."""
        from unittest.mock import MagicMock, patch

        trades = _make_trades([5, 3, -1, 2, 1])
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        cfg = _default_cfg()
        mock_redis = MagicMock()
        mock_redis.get_feedback_entry_threshold.return_value = 0.31  # one step above baseline
        mock_redis.get_feedback_regime_scale.return_value = None
        mock_redis.get_feedback_state.return_value = {"last_adjustment_ts": old_ts, "reason": "triggered"}
        mock_redis.get_portfolio_value.return_value = 100_000.0
        mock_pg = MagicMock()
        mock_pg.fetch_trades.return_value = trades

        with patch("src.workers.performance._load_loss_feedback_config", return_value=cfg), \
             patch("src.workers.performance.RedisStore", return_value=mock_redis), \
             patch("src.workers.performance.PostgreSQLStore", return_value=mock_pg), \
             patch("src.workers.performance.TelegramNotifier") as mock_notifier_cls, \
             patch("src.workers.performance.run_async") as mock_run_async:
            run_loss_feedback_check()

        mock_notifier_cls.assert_called_once()
        mock_run_async.assert_called_once()
        send_alert_call = mock_notifier_cls.return_value.send_alert.call_args
        assert send_alert_call is not None
        msg = send_alert_call[0][0]
        assert "Loss Feedback Reset" in msg
        assert "0.30" in msg


class TestRedisWrites:
    def test_state_written_on_trigger(self):
        trades = _make_trades([-5, -10, -3, 8, 2])
        _, mock_redis = _patched_run(trades)

        mock_redis.set_feedback_state.assert_called_once()
        state_arg = mock_redis.set_feedback_state.call_args[0][0]
        assert state_arg["reason"] == "triggered"
        assert "last_adjustment_ts" in state_arg
        assert "threshold_before" in state_arg
        assert "threshold_after" in state_arg

    def test_state_written_on_recovery(self):
        trades = _make_trades([5, 10, 3, 2, 1])
        _, mock_redis = _patched_run(
            trades,
            redis_threshold=0.40,
            redis_scale=0.80,
        )

        mock_redis.set_feedback_state.assert_called_once()
        state_arg = mock_redis.set_feedback_state.call_args[0][0]
        assert state_arg["reason"] == "recovery"


class TestExecutionThresholdIntegration:
    """Verify execution.py reads Redis feedback threshold correctly."""

    def test_load_entry_threshold_falls_back_to_constant(self):
        from src.workers.execution import _load_entry_threshold, ENTRY_THRESHOLD

        mock_redis = MagicMock()
        mock_redis.get_feedback_entry_threshold.return_value = None
        assert _load_entry_threshold(mock_redis) == pytest.approx(ENTRY_THRESHOLD)

    def test_load_entry_threshold_uses_redis_value(self):
        from src.workers.execution import _load_entry_threshold

        mock_redis = MagicMock()
        mock_redis.get_feedback_entry_threshold.return_value = 0.45
        assert _load_entry_threshold(mock_redis) == pytest.approx(0.45)

    def test_load_feedback_regime_scale_defaults_to_one(self):
        from src.workers.execution import _load_feedback_regime_scale

        mock_redis = MagicMock()
        mock_redis.get_feedback_regime_scale.return_value = None
        assert _load_feedback_regime_scale(mock_redis) == pytest.approx(1.0)

    def test_load_feedback_regime_scale_uses_redis_value(self):
        from src.workers.execution import _load_feedback_regime_scale

        mock_redis = MagicMock()
        mock_redis.get_feedback_regime_scale.return_value = 0.64
        assert _load_feedback_regime_scale(mock_redis) == pytest.approx(0.64)
