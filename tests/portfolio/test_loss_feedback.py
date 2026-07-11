"""Tests for src/portfolio/loss_feedback (Phase 5 per-strategy risk-normalized feedback)."""

from __future__ import annotations

from src.portfolio.loss_feedback import (
    FeedbackOutcome,
    evaluate_strategy_feedback,
    r_multiple,
    risk_budget_at_entry,
    strategy_for_trade,
    update_ewma_r,
)


def _trade(
    net_pnl: float,
    signal_id: int | None = None,
    stop_strategy: str | None = None,
    entry_notional: float = 1000.0,
    stop_d_init: float | None = 0.02,
    exit_reason: str = "stop_loss",
) -> dict:
    return {
        "net_pnl": net_pnl,
        "signal_id": signal_id,
        "stop_strategy": stop_strategy,
        "entry_notional": entry_notional,
        "stop_d_init": stop_d_init,
        "exit_reason": exit_reason,
    }


def test_strategy_for_trade_prefers_stop_strategy():
    assert strategy_for_trade(_trade(0, stop_strategy="S1")) == "S1"


def test_strategy_for_trade_falls_back_to_signal_id():
    assert strategy_for_trade(_trade(0, signal_id=123)) == "S4"


def test_strategy_for_trade_defaults_to_s1():
    assert strategy_for_trade(_trade(0)) == "S1"


def test_risk_budget_uses_stop_d_init():
    assert risk_budget_at_entry(_trade(0, entry_notional=1000, stop_d_init=0.05)) == 50.0


def test_risk_budget_falls_back_to_default_stop():
    assert risk_budget_at_entry(_trade(0, entry_notional=1000, stop_d_init=None)) == 20.0


def test_r_multiple():
    # budget = 1000 * 0.02 = 20; net_pnl = -40 -> R = -2
    assert r_multiple(_trade(-40, entry_notional=1000, stop_d_init=0.02)) == -2.0


def test_update_ewma_r():
    assert update_ewma_r(0.0, -2.0, alpha=0.3) == pytest.approx(-0.6)


def test_evaluate_strategy_feedback_triggers_on_consecutive_losses():
    trades = [_trade(-20), _trade(-20), _trade(-20)]
    out = evaluate_strategy_feedback(trades, "S1")
    assert out.triggered is True
    assert out.consecutive_losses == 3


def test_evaluate_strategy_feedback_triggers_on_ewma_r_band():
    # Three -2R losses: EWMA = -2 (first), then -2 (stable). Should breach -0.5.
    trades = [_trade(-40, entry_notional=1000, stop_d_init=0.02) for _ in range(3)]
    out = evaluate_strategy_feedback(trades, "S1", alpha=0.5)
    assert out.ewma_r <= -0.5
    assert out.triggered is True


def test_evaluate_strategy_feedback_no_trigger_on_wins():
    trades = [_trade(20), _trade(20), _trade(20)]
    out = evaluate_strategy_feedback(trades, "S1")
    assert out.triggered is False


def test_non_teaching_trades_do_not_contribute():
    # sentiment_reversal and LEGACY_FLATTEN are ignored.
    trades = [
        _trade(-20, exit_reason="sentiment_reversal"),
        _trade(-20, exit_reason="LEGACY_FLATTEN"),
        _trade(-20, exit_reason="stop_loss"),
    ]
    out = evaluate_strategy_feedback(trades, "S1")
    assert out.consecutive_losses == 1


import pytest  # noqa: E402
