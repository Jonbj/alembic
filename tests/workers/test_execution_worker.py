"""Tests for ExecutionWorker."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.workers.execution import (
    ENTRY_THRESHOLD,
    MAX_POSITION_PCT,
    STOP_LOSS_PCT,
    _is_fresh,
    run_execution_cycle,
)


def _signal(score: float = 0.5, age_min: int = 5, fallback: bool = False) -> dict:
    ts = (datetime.now(timezone.utc) - timedelta(minutes=age_min)).isoformat()
    return {"score": score, "fallback_used": fallback, "generated_at": ts}


def _make_redis(signal: dict | None, killswitch: bool = False, regime_mult: float = 1.0):
    redis_store = MagicMock()
    redis_store.is_killswitch_active.return_value = killswitch
    redis_store.read_sentiment.return_value = signal
    regime = MagicMock()
    regime.multiplier = regime_mult
    redis_store.get_regime.return_value = regime
    return redis_store


def _make_client(portfolio_value: float = 100_000, positions: dict | None = None):
    client = MagicMock()
    account = MagicMock()
    account.portfolio_value = str(portfolio_value)
    client.get_account.return_value = account
    client.get_all_positions.return_value = list((positions or {}).values())
    return client


def _make_position(symbol: str, avg_entry: float, current: float):
    pos = MagicMock()
    pos.symbol = symbol
    pos.avg_entry_price = str(avg_entry)
    pos.current_price = str(current)
    return pos


# --- _is_fresh ---

def test_is_fresh_recent_signal():
    assert _is_fresh(_signal(age_min=5)) is True


def test_is_fresh_stale_signal():
    assert _is_fresh(_signal(age_min=60)) is False


def test_is_fresh_missing_timestamp():
    assert _is_fresh({"score": 0.5}) is False


def test_is_fresh_at_boundary():
    sig = _signal(age_min=29)
    assert _is_fresh(sig) is True


# --- kill-switch ---

def test_killswitch_skips_all_symbols():
    redis = _make_redis(signal=_signal(), killswitch=True)
    client = _make_client()
    stats = run_execution_cycle(["AAPL", "MSFT"], redis, client)
    assert stats["skipped_killswitch"] == 2
    client.submit_order.assert_not_called()


# --- stale / no signal ---

def test_stale_signal_skipped():
    redis = _make_redis(signal=_signal(age_min=60))
    client = _make_client()
    stats = run_execution_cycle(["AAPL"], redis, client)
    assert stats["skipped_stale"] == 1
    client.submit_order.assert_not_called()


def test_missing_signal_skipped():
    redis = _make_redis(signal=None)
    client = _make_client()
    stats = run_execution_cycle(["AAPL"], redis, client)
    assert stats["skipped_stale"] == 1
    client.submit_order.assert_not_called()


def test_fallback_signal_skipped():
    redis = _make_redis(signal=_signal(score=0.8, fallback=True))
    client = _make_client()
    stats = run_execution_cycle(["AAPL"], redis, client)
    assert stats["skipped_stale"] == 1
    client.submit_order.assert_not_called()


# --- entry logic ---

def test_score_above_threshold_places_order():
    redis = _make_redis(signal=_signal(score=0.5))
    client = _make_client(portfolio_value=100_000)
    stats = run_execution_cycle(["AAPL"], redis, client)
    assert stats["orders_placed"] == 1
    client.submit_order.assert_called_once()


def test_score_below_threshold_no_order():
    redis = _make_redis(signal=_signal(score=0.1))
    client = _make_client()
    stats = run_execution_cycle(["AAPL"], redis, client)
    assert stats["orders_placed"] == 0
    client.submit_order.assert_not_called()


def test_order_notional_uses_portfolio_and_regime():
    redis = _make_redis(signal=_signal(score=0.6), regime_mult=0.7)
    client = _make_client(portfolio_value=100_000)
    run_execution_cycle(["AAPL"], redis, client)

    call_args = client.submit_order.call_args[0][0]
    expected_notional = round(100_000 * MAX_POSITION_PCT * 0.7, 2)
    assert call_args.notional == pytest.approx(expected_notional)


# --- idempotency / no pyramiding ---

def test_existing_position_no_new_order():
    pos = _make_position("AAPL", avg_entry=150.0, current=155.0)
    client = _make_client(positions={"AAPL": pos})
    redis = _make_redis(signal=_signal(score=0.8))
    stats = run_execution_cycle(["AAPL"], redis, client)
    assert stats["skipped_position"] == 1
    client.submit_order.assert_not_called()


# --- stop-loss ---

def test_stop_loss_triggers_close():
    entry = 100.0
    current = entry * (1 - STOP_LOSS_PCT - 0.01)  # below stop
    pos = _make_position("AAPL", avg_entry=entry, current=current)
    client = _make_client(positions={"AAPL": pos})
    redis = _make_redis(signal=_signal(score=0.8))
    stats = run_execution_cycle(["AAPL"], redis, client)
    assert stats["stop_losses_triggered"] == 1
    client.close_position.assert_called_once_with("AAPL")
    client.submit_order.assert_not_called()


def test_stop_loss_not_triggered_above_price():
    entry = 100.0
    current = entry * 0.99  # above stop (stop is at 98.0)
    pos = _make_position("AAPL", avg_entry=entry, current=current)
    client = _make_client(positions={"AAPL": pos})
    redis = _make_redis(signal=_signal(score=0.8))
    stats = run_execution_cycle(["AAPL"], redis, client)
    assert stats["stop_losses_triggered"] == 0
    assert stats["skipped_position"] == 1


# --- error handling ---

def test_alpaca_error_counted_not_raised():
    redis = _make_redis(signal=_signal(score=0.8))
    client = _make_client()
    client.submit_order.side_effect = Exception("Alpaca API error")
    stats = run_execution_cycle(["AAPL"], redis, client)
    assert stats["errors"] == 1


def test_account_fetch_error_returns_early():
    redis = _make_redis(signal=_signal(score=0.8))
    client = _make_client()
    client.get_account.side_effect = Exception("connection refused")
    stats = run_execution_cycle(["AAPL", "MSFT"], redis, client)
    assert stats["errors"] == 1
    assert stats["orders_placed"] == 0
