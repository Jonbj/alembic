"""Buying-power gate on the legacy sentiment execution BUY path."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


def _ts():
    return datetime(2026, 8, 7, 14, 0, tzinfo=timezone.utc)


def _apply(*, notional=1000.0, buying_power=500.0, mode="cap"):
    from src.workers.execution import _apply_buying_power_gate_legacy

    return _apply_buying_power_gate_legacy(
        notional=notional,
        buying_power=buying_power,
        price=100.0,
        symbol="AAPL",
        signal_id=1,
        score=0.5,
        regime_mult=1.0,
        tick_time=_ts(),
        pg_store=MagicMock(),
        notifier=None,
        mode=mode,
    )


@pytest.mark.parametrize("buying_power", [None, 0.0])
def test_unavailable_buying_power_skips(buying_power):
    assert _apply(buying_power=buying_power) is None


def test_cap_returns_capped_notional():
    assert _apply() == pytest.approx(500.0)


def test_shadow_returns_original_notional():
    assert _apply(mode="shadow") == pytest.approx(1000.0)


def test_pass_returns_original_notional():
    assert _apply(notional=100.0) == pytest.approx(100.0)


def test_off_returns_original_notional():
    assert _apply(buying_power=100.0, mode="off") == pytest.approx(1000.0)


@pytest.mark.parametrize(
    ("buying_power", "mode", "expected_decision"),
    [(500.0, "cap", "BUY_POWER_CAP"), (0.0, "shadow", "SKIP_BUY_POWER")],
)
def test_action_writes_decision(monkeypatch, buying_power, mode, expected_decision):
    from src.workers import execution

    captured = []
    monkeypatch.setattr(
        execution,
        "_write_decision",
        lambda *args, **kwargs: captured.append(kwargs),
    )
    monkeypatch.setattr(execution, "_fire_alert", lambda *args, **kwargs: None)

    _apply(buying_power=buying_power, mode=mode)

    assert captured[0]["decision"] == expected_decision


def test_shadow_emits_alert_and_decision(monkeypatch):
    from src.workers import execution

    alerts = []
    decisions = []
    monkeypatch.setattr(
        execution, "_fire_alert", lambda *args, **kwargs: alerts.append(args)
    )
    monkeypatch.setattr(
        execution,
        "_write_decision",
        lambda *args, **kwargs: decisions.append(kwargs),
    )

    assert _apply(mode="shadow") == pytest.approx(1000.0)
    assert len(alerts) == 1
    assert decisions[0]["decision"] == "BUY_POWER_SHADOW"


def test_execution_cycle_threads_zero_buying_power_and_skips_buy():
    from src.store.redis_store import RedisStore
    from src.workers.execution import run_execution_cycle

    redis_store = MagicMock(spec=RedisStore)
    redis_store.is_killswitch_active.return_value = False
    redis_store.get_regime.return_value = MagicMock(multiplier=1.0)
    redis_store.get_feedback_entry_threshold.return_value = None
    redis_store.read_sentiment.return_value = {
        "score": 0.8,
        "signal_id": 42,
        "fallback_used": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    account = MagicMock()
    account.portfolio_value = "10000"
    account.buying_power = "0"
    account.last_equity = "10000"
    trading_client = MagicMock()
    trading_client.get_account.return_value = account
    trading_client.get_all_positions.return_value = []
    trading_client.get_orders.return_value = []

    cache = {"AAPL": {"ema": 90.0, "price": 100.0}}
    with patch("src.workers.execution._build_market_cache", return_value=cache):
        stats = run_execution_cycle(
            ["AAPL"],
            redis_store,
            trading_client,
            data_client=MagicMock(),
            pg_store=MagicMock(),
        )

    assert stats["skipped_buy_power"] == 1
    assert stats["orders_placed"] == 0
    trading_client.submit_order.assert_not_called()
