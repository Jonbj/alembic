"""Tests for run_loss_feedback_check (Phase 5 — per-strategy risk-normalized feedback).

Covers:
  - Disabled / no-trades skip paths
  - Per-strategy ratchet isolation (S1 loss must not affect S4 threshold)
  - R-multiple / EWMA trigger and recovery
  - Cooldown, temporal decay, Redis writes
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

def _make_trade(
    net_pnl: float,
    *,
    signal_id: int | None = None,
    entry_notional: float = 1000.0,
    stop_d_init: float = 0.02,
    exit_reason: str = "stop_loss",
    trade_id: int | None = None,
) -> dict:
    """Return a closed trade fixture.

    signal_id=None  -> strategy S1 (momentum/rebalance)
    signal_id=set   -> strategy S4 (news-driven signal)
    """
    trade = {
        "net_pnl": net_pnl,
        "symbol": "AAPL",
        "entry_time": datetime.now(timezone.utc).isoformat(),
        "signal_id": signal_id,
        "entry_notional": entry_notional,
        "stop_d_init": stop_d_init,
        "exit_reason": exit_reason,
    }
    if trade_id is not None:
        trade["id"] = trade_id
    return trade


def _make_trades(
    pnls: list[float],
    *,
    signal_id: int | None = None,
    exit_reason: str = "stop_loss",
) -> list[dict]:
    """Most-recent first (matching fetch_trades ordering)."""
    return [
        _make_trade(pnl, signal_id=signal_id, exit_reason=exit_reason)
        for pnl in pnls
    ]


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


def test_apply_regime_scale_defaults_to_false():
    """F8 ships shadow-only: apply_regime_scale must default to False so the
    feedback regime scale is measured (shadow-logged) but NOT applied to sizing
    until an operator flips it after the shadow gate passes (QX-01)."""
    with patch("builtins.open", side_effect=FileNotFoundError):
        cfg = _load_loss_feedback_config()
    assert cfg.get("apply_regime_scale") is False, (
        "apply_regime_scale must default False — measure-before-enforce"
    )


def test_trading_yaml_ships_apply_regime_scale_false():
    """The shipped config must keep apply_regime_scale: false until the F8 shadow
    gate passes — guards against an accidental live flip."""
    cfg = _load_loss_feedback_config()  # reads the real config/trading.yaml
    assert cfg.get("apply_regime_scale") is False, (
        "config/trading.yaml must ship apply_regime_scale: false (shadow-only)"
    )


# ---------------------------------------------------------------------------
# Integration: run_loss_feedback_check (per-strategy)
# ---------------------------------------------------------------------------

def _default_cfg():
    return {
        "enabled": True,
        "consecutive_loss_trigger": 3,
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
    cfg_override: dict | None = None,
):
    """Helper that patches all external dependencies and runs the task."""
    cfg = {**_default_cfg(), **(cfg_override or {})}

    mock_redis = MagicMock()
    mock_redis.get_feedback_entry_threshold.return_value = redis_threshold
    mock_redis.get_feedback_regime_scale.return_value = redis_scale
    mock_redis.get_feedback_state.return_value = redis_state

    mock_pg = MagicMock()
    mock_pg.fetch_trades.return_value = trades

    with (
        patch("src.workers.performance._load_loss_feedback_config", return_value=cfg),
        patch("src.workers.performance.RedisStore", return_value=mock_redis),
        patch("src.workers.performance.PostgreSQLStore", return_value=mock_pg),
        patch("src.workers.performance.TelegramNotifier"),
        patch("src.workers.performance.run_async"),
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
    def test_s4_3_consecutive_losses_triggers(self):
        trades = _make_trades([-5, -10, -3, 8, 2], signal_id=123)
        result, mock_redis = _patched_run(trades)

        assert result["adjusted"] is True
        s4 = result["per_strategy"]["S4"]
        assert s4["triggered"] is True
        assert s4["consecutive_losses"] == 3
        mock_redis.set_feedback_entry_threshold.assert_called_once()
        mock_redis.set_feedback_regime_scale.assert_called_once()

    def test_threshold_raised_by_step(self):
        trades = _make_trades([-5, -10, -3, 8, 2], signal_id=123)
        result, _ = _patched_run(trades, redis_threshold=0.30)

        s4 = result["per_strategy"]["S4"]
        assert s4["new_threshold"] == pytest.approx(0.35)

    def test_regime_scale_reduced_by_factor(self):
        trades = _make_trades([-5, -10, -3, 8, 2], signal_id=123)
        result, _ = _patched_run(trades, redis_scale=1.0)

        s4 = result["per_strategy"]["S4"]
        assert s4["new_scale"] == pytest.approx(0.80)

    def test_2_consecutive_losses_does_not_trigger(self):
        trades = _make_trades([-5, -10, 8, 9, 10], signal_id=123)
        result, _ = _patched_run(trades)

        s4 = result["per_strategy"]["S4"]
        assert s4["triggered"] is False
        assert result["adjusted"] is False


class TestPerStrategyIsolation:
    def test_s1_losses_do_not_poison_s4_threshold(self):
        """Three S1 stop-out losses must not adjust the S4 entry threshold."""
        # Most recent first: three S1 losses, then two S4 wins.
        trades = [
            _make_trade(-20, signal_id=None),   # S1
            _make_trade(-30, signal_id=None),   # S1
            _make_trade(-25, signal_id=None),   # S1
            _make_trade(10, signal_id=999),     # S4 win
            _make_trade(5, signal_id=999),      # S4 win
        ]
        result, mock_redis = _patched_run(trades, redis_threshold=0.30)

        assert result["per_strategy"]["S1"]["triggered"] is True
        assert result["per_strategy"]["S4"]["triggered"] is False
        # S4 threshold must stay untouched.
        for call in mock_redis.set_feedback_entry_threshold.call_args_list:
            assert call.kwargs.get("strategy") != "S4"


class TestTriggerOnEwmaR:
    def test_large_r_losses_trigger_via_ewma(self):
        """Three -2R losses produce EWMA R <= -0.5, which triggers S4."""
        trades = [
            _make_trade(-40, signal_id=123, entry_notional=1000, stop_d_init=0.02),
            _make_trade(-40, signal_id=123, entry_notional=1000, stop_d_init=0.02),
            _make_trade(-40, signal_id=123, entry_notional=1000, stop_d_init=0.02),
        ]
        result, _ = _patched_run(trades)
        s4 = result["per_strategy"]["S4"]
        assert s4["ewma_r"] <= -0.5
        assert s4["triggered"] is True
        assert result["adjusted"] is True


class TestThresholdCap:
    def test_threshold_capped_at_max(self):
        trades = _make_trades([-5, -10, -3, 8, 2], signal_id=123)
        result, _ = _patched_run(trades, redis_threshold=0.58)

        s4 = result["per_strategy"]["S4"]
        assert s4["new_threshold"] == pytest.approx(0.60)

    def test_regime_scale_floored_at_min(self):
        trades = _make_trades([-5, -10, -3, 8, 2], signal_id=123)
        result, _ = _patched_run(trades, redis_scale=0.22)

        s4 = result["per_strategy"]["S4"]
        assert s4["new_scale"] == pytest.approx(0.20)


class TestCooldown:
    def test_adjustment_skipped_within_cooldown(self):
        trades = _make_trades([-5, -10, -3, 8, 2], signal_id=123)
        recent_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        result, mock_redis = _patched_run(
            trades,
            redis_state={"last_adjustment_ts": recent_ts},
        )

        s4 = result["per_strategy"]["S4"]
        assert s4["cooldown_ok"] is False
        assert s4["adjusted"] is False
        mock_redis.set_feedback_entry_threshold.assert_not_called()

    def test_adjustment_allowed_after_cooldown(self):
        trades = _make_trades([-5, -10, -3, 8, 2], signal_id=123)
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        result, mock_redis = _patched_run(
            trades,
            redis_state={"last_adjustment_ts": old_ts},
        )

        s4 = result["per_strategy"]["S4"]
        assert s4["cooldown_ok"] is True
        assert s4["adjusted"] is True
        mock_redis.set_feedback_entry_threshold.assert_called_once()


class TestRecovery:
    def test_win_streak_steps_threshold_down(self):
        # 3 consecutive S4 wins, threshold above baseline
        trades = _make_trades([5, 10, 3, -1, 2], signal_id=123)
        result, mock_redis = _patched_run(
            trades,
            redis_threshold=0.40,
            redis_scale=0.80,
        )

        s4 = result["per_strategy"]["S4"]
        assert s4["triggered"] is False
        assert s4["recovered"] is True
        assert s4["new_threshold"] == pytest.approx(0.35)

    def test_no_recovery_when_already_at_baseline(self):
        trades = _make_trades([5, 10, 3, 2, 1], signal_id=123)
        result, mock_redis = _patched_run(
            trades,
            redis_threshold=0.30,
            redis_scale=1.0,
        )

        s4 = result["per_strategy"]["S4"]
        assert s4["recovered"] is False
        mock_redis.set_feedback_entry_threshold.assert_not_called()

    def test_insufficient_win_streak_no_recovery(self):
        # Only 2 consecutive wins, need 3
        trades = _make_trades([5, 10, -1, 2, 1], signal_id=123)
        result, _ = _patched_run(
            trades,
            redis_threshold=0.40,
            cfg_override={"recovery_win_streak": 3},
        )

        s4 = result["per_strategy"]["S4"]
        assert s4["recovered"] is False


class TestTemporalDecay:
    def test_threshold_decays_after_quiet_period(self):
        # No trigger, current threshold above baseline, quiet > 24h
        trades = _make_trades([5, 3, -1, 2, 1], signal_id=123)
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        result, mock_redis = _patched_run(
            trades,
            redis_threshold=0.40,
            redis_state={"last_adjustment_ts": old_ts, "reason": "triggered"},
        )

        s4 = result["per_strategy"]["S4"]
        assert s4["decayed"] is True
        assert s4["new_threshold"] == pytest.approx(0.35)
        mock_redis.set_feedback_entry_threshold.assert_called_once()

    def test_no_decay_within_decay_window(self):
        trades = _make_trades([5, 3, -1, 2, 1], signal_id=123)
        recent_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        result, mock_redis = _patched_run(
            trades,
            redis_threshold=0.40,
            redis_state={"last_adjustment_ts": recent_ts, "reason": "triggered"},
        )

        s4 = result["per_strategy"]["S4"]
        assert s4["decayed"] is False
        mock_redis.set_feedback_entry_threshold.assert_not_called()

    def test_s1_scale_decays_after_quiet_period(self):
        """F8: S1's suppressed regime_scale must decay on the quiet period even
        though S1's entry threshold is held at 0.0 (no entry gate).

        Pre-fix the decay branch guard `current_threshold > baseline` excluded
        S1 (0.0 > 0.30 is False), leaving its scale stuck until a 3-win streak —
        a one-way suppressor on the strategy that bled most on 2026-07-10.
        Post-fix decay fires when the scale is suppressed (current_scale < 1.0)
        independent of the threshold.
        """
        # S1 trades, not triggered, only 2 consecutive wins (< recovery_win_streak)
        trades = _make_trades([5, 3, -1, 2, 1], signal_id=None)
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        result, mock_redis = _patched_run(
            trades,
            redis_threshold=0.0,   # S1 always 0.0
            redis_scale=0.50,      # suppressed
            redis_state={"last_adjustment_ts": old_ts, "reason": "triggered"},
        )

        s1 = result["per_strategy"]["S1"]
        assert s1["decayed"] is True, (
            "S1 suppressed scale must decay on quiet period (F8) — pre-fix it was "
            "stuck because the decay guard required threshold > baseline"
        )
        assert s1["new_scale"] == pytest.approx(0.625, rel=1e-4), (
            "0.50 / 0.80 = 0.625"
        )
        mock_redis.set_feedback_regime_scale.assert_called_once()

    def test_s4_scale_decays_when_threshold_at_baseline_but_scale_suppressed(self):
        """F8: a non-S1 strategy whose threshold is already at baseline but
        whose scale is still suppressed must decay the scale. Pre-fix the
        early-return in _step_threshold_down (current_threshold <= baseline)
        short-circuited and left the scale stuck."""
        trades = _make_trades([5, 3, -1, 2, 1], signal_id=123)
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        result, mock_redis = _patched_run(
            trades,
            redis_threshold=0.30,  # at baseline
            redis_scale=0.50,      # suppressed
            redis_state={"last_adjustment_ts": old_ts, "reason": "triggered"},
        )

        s4 = result["per_strategy"]["S4"]
        assert s4["decayed"] is True, (
            "Suppressed scale must decay even when threshold is at baseline (F8)"
        )
        assert s4["new_scale"] == pytest.approx(0.625, rel=1e-4)
        assert s4["new_threshold"] == pytest.approx(0.30, rel=1e-4), (
            "threshold already at baseline — unchanged"
        )

    def test_no_decay_when_s1_fully_at_rest(self):
        """S1 with threshold=0.0 and scale=1.0 has nothing to decay — guard
        against the early-return change over-firing."""
        trades = _make_trades([5, 3, -1, 2, 1], signal_id=None)
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        result, mock_redis = _patched_run(
            trades,
            redis_threshold=0.0,
            redis_scale=1.0,       # at rest
            redis_state={"last_adjustment_ts": old_ts, "reason": "triggered"},
        )

        s1 = result["per_strategy"]["S1"]
        assert s1["decayed"] is False
        mock_redis.set_feedback_regime_scale.assert_not_called()


class TestRedisWrites:
    def test_state_written_on_trigger(self):
        trades = _make_trades([-5, -10, -3, 8, 2], signal_id=123)
        _, mock_redis = _patched_run(trades)

        assert mock_redis.set_feedback_state.call_count == 1
        state_arg = mock_redis.set_feedback_state.call_args[0][0]
        assert state_arg["reason"] != ""  # per-strategy reason
        assert "last_adjustment_ts" in state_arg
        assert "threshold_before" in state_arg
        assert "threshold_after" in state_arg

    def test_state_written_on_recovery(self):
        trades = _make_trades([5, 10, 3, 2, 1], signal_id=123)
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


class TestStaleEvidenceGuard:
    """Loss-feedback ratchet must not re-step on the same evidence trade (#122)."""

    def _s4_triggering_trades(self) -> list[dict]:
        """Most-recent first: 3 S4 stop-loss losses then 2 wins.

        The most recent teaching trade (id=100) is the evidence used to ratchet.
        """
        return [
            _make_trade(-5, signal_id=123, trade_id=100),
            _make_trade(-10, signal_id=123, trade_id=99),
            _make_trade(-3, signal_id=123, trade_id=98),
            _make_trade(8, signal_id=123, trade_id=97),
            _make_trade(2, signal_id=123, trade_id=96),
        ]

    def test_skips_reapply_on_same_evidence_after_cooldown(self):
        """After cooldown, identical evidence trade must not re-apply the step-down."""
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        result, mock_redis = _patched_run(
            self._s4_triggering_trades(),
            redis_state={
                "last_adjustment_ts": old_ts,
                "last_trigger_evidence_trade_id": 100,
            },
        )

        s4 = result["per_strategy"]["S4"]
        assert s4["triggered"] is True
        assert s4["cooldown_ok"] is True
        assert s4["adjusted"] is False
        assert s4.get("skipped_stale_evidence") is True
        mock_redis.set_feedback_entry_threshold.assert_not_called()
        mock_redis.set_feedback_regime_scale.assert_not_called()

    def test_reapplies_when_new_teaching_trade_closed(self):
        """A fresh teaching trade (different id) is new evidence — ratchet applies."""
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        result, mock_redis = _patched_run(
            self._s4_triggering_trades(),
            redis_state={
                "last_adjustment_ts": old_ts,
                "last_trigger_evidence_trade_id": 99,
            },
        )

        s4 = result["per_strategy"]["S4"]
        assert s4["triggered"] is True
        assert s4["cooldown_ok"] is True
        assert s4["adjusted"] is True
        assert s4.get("skipped_stale_evidence") is not True
        mock_redis.set_feedback_entry_threshold.assert_called_once()
        mock_redis.set_feedback_regime_scale.assert_called_once()

    def test_applies_when_prior_state_has_no_evidence_id(self):
        """Backward compatibility: missing evidence id never blocks the ratchet."""
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        result, mock_redis = _patched_run(
            self._s4_triggering_trades(),
            redis_state={"last_adjustment_ts": old_ts},
        )

        s4 = result["per_strategy"]["S4"]
        assert s4["triggered"] is True
        assert s4["adjusted"] is True
        assert s4.get("skipped_stale_evidence") is not True
        mock_redis.set_feedback_entry_threshold.assert_called_once()
        mock_redis.set_feedback_regime_scale.assert_called_once()

    def test_persists_evidence_id_on_apply(self):
        """The applied state must remember the evidence trade id that caused it."""
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        _, mock_redis = _patched_run(
            self._s4_triggering_trades(),
            redis_state={"last_adjustment_ts": old_ts},
        )

        state_arg = mock_redis.set_feedback_state.call_args[0][0]
        assert state_arg["last_trigger_evidence_trade_id"] == 100


class TestShadowComparisonToggle:
    """Tests for shadow mode arm/disarm toggle helpers (Stage 2 model comparison)."""

    def test_shadow_toggle_roundtrip(self):
        """Shadow toggle should support set → get → clear lifecycle."""
        mock_redis = MagicMock()
        mock_redis._r = MagicMock()

        from src.store.redis_store import RedisStore

        redis_store = RedisStore(redis_client=mock_redis)

        # Set
        redis_store.set_shadow_comparison_start("2026-07-13T14:00:00+00:00")
        mock_redis.set.assert_called_once()

        # Get
        mock_redis.get.return_value = "2026-07-13T14:00:00+00:00"
        result = redis_store.get_shadow_comparison_start()
        mock_redis.get.assert_called_with("shadow:model_comparison:started_at")
        assert result == "2026-07-13T14:00:00+00:00"

        # Clear
        redis_store.clear_shadow_comparison_start()
        mock_redis.delete.assert_called_with("shadow:model_comparison:started_at")

    def test_shadow_toggle_get_returns_none_when_absent(self):
        """get_shadow_comparison_start should return None if key is absent."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        from src.store.redis_store import RedisStore

        redis_store = RedisStore(redis_client=mock_redis)
        result = redis_store.get_shadow_comparison_start()
        assert result is None

    def test_shadow_toggle_get_handles_bytes(self):
        """get_shadow_comparison_start should decode bytes if needed."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = b"2026-07-13T14:00:00+00:00"

        from src.store.redis_store import RedisStore

        redis_store = RedisStore(redis_client=mock_redis)
        result = redis_store.get_shadow_comparison_start()
        assert result == "2026-07-13T14:00:00+00:00"
