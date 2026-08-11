"""Tests for ExecutionWorker."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.notifications.base import AlertLevel
from src.workers.execution import (
    ENTRY_THRESHOLD,
    MAX_DRAWDOWN_PCT,
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
    # Feedback keys: None means use defaults (no active adjustment)
    redis_store.get_feedback_entry_threshold.return_value = None
    redis_store.get_feedback_entry_threshold.return_value = None
    return redis_store


def _make_client(
    portfolio_value: float = 100_000,
    last_equity: float | None = None,
    positions: dict | None = None,
):
    client = MagicMock()
    account = MagicMock()
    account.portfolio_value = str(portfolio_value)
    account.last_equity = str(last_equity) if last_equity is not None else None
    client.get_account.return_value = account
    client.get_all_positions.return_value = list((positions or {}).values())
    return client


def _make_notifier():
    notifier = MagicMock()
    notifier.send_alert = AsyncMock(return_value=True)
    return notifier


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
    # Price must be provided (via data_client+cache) — without price, BUY is blocked
    # because the stop-loss level cannot be computed.
    cache = {"AAPL": {"ema": 90.0, "price": 100.0}}
    with patch("src.workers.execution._build_market_cache", return_value=cache):
        stats = run_execution_cycle(["AAPL"], redis, client, data_client=MagicMock())
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
    # With price=100: qty = round(notional / price, 4) = round(7000 / 100, 4) = 70.0
    cache = {"AAPL": {"ema": 90.0, "price": 100.0}}
    with patch("src.workers.execution._build_market_cache", return_value=cache):
        run_execution_cycle(["AAPL"], redis, client, data_client=MagicMock())

    call_args = client.submit_order.call_args[0][0]
    expected_notional = 100_000 * MAX_POSITION_PCT * 0.7   # = 7000
    expected_qty = round(expected_notional / 100.0, 4)      # = 70.0
    assert call_args.qty == pytest.approx(expected_qty)


def test_regime_absent_uses_conservative_fallback():
    """When no regime key is in Redis, execution uses 0.2× notional (high_vol fallback)."""
    redis = _make_redis(signal=_signal(score=0.6))
    redis.get_regime.return_value = None  # simulate Redis cold / regime worker not yet run
    client = _make_client(portfolio_value=100_000)
    # With price=100: qty = round(notional / price) = round(2000 / 100) = 20.0
    cache = {"AAPL": {"ema": 90.0, "price": 100.0}}
    with patch("src.workers.execution._build_market_cache", return_value=cache):
        run_execution_cycle(["AAPL"], redis, client, data_client=MagicMock())

    call_args = client.submit_order.call_args[0][0]
    expected_notional = 100_000 * MAX_POSITION_PCT * 0.2    # = 2000
    expected_qty = round(expected_notional / 100.0, 4)       # = 20.0
    assert call_args.qty == pytest.approx(expected_qty)


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
    # Provide price so submit_order is actually reached (and triggers the error)
    cache = {"AAPL": {"ema": 90.0, "price": 100.0}}
    with patch("src.workers.execution._build_market_cache", return_value=cache):
        stats = run_execution_cycle(["AAPL"], redis, client, data_client=MagicMock())
    assert stats["errors"] == 1


def test_account_fetch_error_returns_early():
    redis = _make_redis(signal=_signal(score=0.8))
    client = _make_client()
    client.get_account.side_effect = Exception("connection refused")
    stats = run_execution_cycle(["AAPL", "MSFT"], redis, client)
    assert stats["errors"] == 1
    assert stats["orders_placed"] == 0


# --- EMA momentum filter ---

def _make_data_client(cache_override: dict | None = None):
    """Return a mock data_client that feeds _build_market_cache via patching."""
    return MagicMock()


def _run_with_ema(symbol: str, ema: float | None, price: float | None, score: float = 0.6):
    """Helper: run one symbol through execution with a pre-built market cache."""
    from src.workers.execution import run_execution_cycle

    redis = _make_redis(signal=_signal(score=score))
    client = _make_client(portfolio_value=100_000)
    data_client = _make_data_client()

    cache = {symbol: {"ema": ema, "price": price}}
    with patch("src.workers.execution._build_market_cache", return_value=cache):
        stats = run_execution_cycle([symbol], redis, client, data_client=data_client)
    return stats, client


def test_ema_price_above_ema_places_order():
    stats, client = _run_with_ema("AAPL", ema=150.0, price=155.0)
    assert stats["orders_placed"] == 1
    assert stats["skipped_momentum"] == 0
    client.submit_order.assert_called_once()


def test_ema_price_below_ema_skips_entry():
    stats, client = _run_with_ema("AAPL", ema=160.0, price=155.0)
    assert stats["orders_placed"] == 0
    assert stats["skipped_momentum"] == 1
    client.submit_order.assert_not_called()


def test_ema_price_equal_to_ema_skips_entry():
    stats, client = _run_with_ema("AAPL", ema=155.0, price=155.0)
    assert stats["orders_placed"] == 0
    assert stats["skipped_momentum"] == 1


def test_ema_unavailable_skips_entry():
    stats, client = _run_with_ema("AAPL", ema=None, price=155.0)
    assert stats["orders_placed"] == 0
    assert stats["skipped_momentum"] == 1


def test_ema_price_unavailable_skips_entry():
    stats, client = _run_with_ema("AAPL", ema=150.0, price=None)
    assert stats["orders_placed"] == 0
    assert stats["skipped_momentum"] == 1


def test_no_data_client_blocks_order_no_price():
    """When data_client=None, price is unavailable so BUY is blocked (no stop-loss level).

    Previously this placed an unprotected order (no bracket). Now it's blocked:
    we never BUY without a known price to compute the broker-side stop-loss.
    """
    redis = _make_redis(signal=_signal(score=0.6))
    client = _make_client(portfolio_value=100_000)
    stats = run_execution_cycle(["AAPL"], redis, client, data_client=None)
    assert stats["orders_placed"] == 0
    assert stats["skipped_momentum"] == 1  # counted as skipped_momentum (fail-safe EMA path)


def test_stop_loss_checked_regardless_of_ema():
    """Stop-loss on existing positions must fire even if EMA data is absent."""
    entry = 100.0
    current = entry * (1 - STOP_LOSS_PCT - 0.01)
    pos = _make_position("AAPL", avg_entry=entry, current=current)
    client = _make_client(positions={"AAPL": pos})
    redis = _make_redis(signal=_signal(score=0.8))
    data_client = _make_data_client()

    with patch("src.workers.execution._build_market_cache", return_value={"AAPL": {"ema": None, "price": None}}):
        stats = run_execution_cycle(["AAPL"], redis, client, data_client=data_client)

    assert stats["stop_losses_triggered"] == 1


# --- B1: drawdown cap ---

def test_drawdown_cap_activates_killswitch():
    """Portfolio drops ≥ MAX_DRAWDOWN_PCT from last_equity → kill-switch activated, no orders."""
    last_equity = 100_000.0
    portfolio_value = last_equity * (1 - MAX_DRAWDOWN_PCT - 0.01)  # 11% drop — over cap
    redis = _make_redis(signal=_signal(score=0.8))
    client = _make_client(portfolio_value=portfolio_value, last_equity=last_equity)

    stats = run_execution_cycle(["AAPL", "MSFT"], redis, client)

    redis.activate_killswitch.assert_called_once()
    assert stats["orders_placed"] == 0


def test_drawdown_within_cap_no_killswitch():
    """Small daily loss below threshold → execution proceeds normally."""
    last_equity = 100_000.0
    portfolio_value = last_equity * 0.98  # 2% drop — well below the 5% YAML cap
    redis = _make_redis(signal=_signal(score=0.8))
    client = _make_client(portfolio_value=portfolio_value, last_equity=last_equity)
    cache = {"AAPL": {"ema": 90.0, "price": 100.0}}
    with patch("src.workers.execution._build_market_cache", return_value=cache):
        stats = run_execution_cycle(["AAPL"], redis, client, data_client=MagicMock())

    redis.activate_killswitch.assert_not_called()
    assert stats["orders_placed"] == 1


def test_drawdown_at_exact_cap_triggers():
    """Drawdown exactly at MAX_DRAWDOWN_PCT triggers the cap."""
    last_equity = 100_000.0
    portfolio_value = last_equity * (1 - MAX_DRAWDOWN_PCT)  # exactly 10%
    redis = _make_redis(signal=_signal(score=0.8))
    client = _make_client(portfolio_value=portfolio_value, last_equity=last_equity)

    stats = run_execution_cycle(["AAPL"], redis, client)

    redis.activate_killswitch.assert_called_once()


def test_drawdown_cap_missing_last_equity_does_not_crash():
    """If Alpaca does not provide last_equity, skip cap check and continue normally."""
    redis = _make_redis(signal=_signal(score=0.8))
    client = _make_client(portfolio_value=80_000, last_equity=None)  # no baseline
    cache = {"AAPL": {"ema": 90.0, "price": 100.0}}
    with patch("src.workers.execution._build_market_cache", return_value=cache):
        stats = run_execution_cycle(["AAPL"], redis, client, data_client=MagicMock())

    redis.activate_killswitch.assert_not_called()
    assert stats["orders_placed"] == 1


# --- B2: Telegram alerts for infrastructure errors ---

def test_drawdown_cap_sends_critical_alert():
    """Drawdown cap trigger → notifier.send_alert called with CRITICAL level."""
    last_equity = 100_000.0
    portfolio_value = last_equity * (1 - MAX_DRAWDOWN_PCT - 0.01)
    redis = _make_redis(signal=_signal(score=0.8))
    client = _make_client(portfolio_value=portfolio_value, last_equity=last_equity)
    notifier = _make_notifier()

    run_execution_cycle(["AAPL"], redis, client, notifier=notifier)

    notifier.send_alert.assert_called_once()
    _, kwargs = notifier.send_alert.call_args
    assert kwargs["level"] == AlertLevel.CRITICAL


def test_alpaca_unreachable_sends_critical_alert():
    """Alpaca API error → notifier.send_alert called with CRITICAL."""
    redis = _make_redis(signal=_signal(score=0.8))
    client = _make_client()
    client.get_account.side_effect = Exception("connection refused")
    notifier = _make_notifier()

    stats = run_execution_cycle(["AAPL"], redis, client, notifier=notifier)

    assert stats["errors"] == 1
    notifier.send_alert.assert_called_once()
    _, kwargs = notifier.send_alert.call_args
    assert kwargs["level"] == AlertLevel.CRITICAL


def test_redis_unreachable_sends_critical_alert():
    """Redis connection error → notifier.send_alert with CRITICAL, errors incremented."""
    redis = _make_redis(signal=_signal(score=0.8))
    redis.is_killswitch_active.side_effect = Exception("Redis connection refused")
    client = _make_client()
    notifier = _make_notifier()

    stats = run_execution_cycle(["AAPL"], redis, client, notifier=notifier)

    assert stats["errors"] == 1
    notifier.send_alert.assert_called_once()
    _, kwargs = notifier.send_alert.call_args
    assert kwargs["level"] == AlertLevel.CRITICAL


def test_no_alert_without_notifier():
    """All error conditions with notifier=None must not crash."""
    redis = _make_redis(signal=_signal(score=0.8))
    client = _make_client()
    client.get_account.side_effect = Exception("Alpaca down")

    stats = run_execution_cycle(["AAPL"], redis, client, notifier=None)

    assert stats["errors"] == 1


# --- pending orders / duplicate BUY guard ---

def test_pending_order_prevents_duplicate_buy():
    """Symbol with pending Alpaca order must not receive a second BUY."""
    pending = MagicMock()
    pending.symbol = "AAPL"

    redis = _make_redis(signal=_signal(score=0.8))
    client = _make_client(portfolio_value=100_000)
    client.get_orders.return_value = [pending]

    stats = run_execution_cycle(["AAPL"], redis, client)

    assert stats["orders_placed"] == 0
    assert stats["skipped_position"] == 1
    client.submit_order.assert_not_called()


def test_pending_orders_api_failure_blocks_new_entries():
    """If get_orders() raises, no new BUY is placed this cycle (fail-safe)."""
    redis = _make_redis(signal=_signal(score=0.8))
    client = _make_client(portfolio_value=100_000)
    client.get_orders.side_effect = Exception("Alpaca API error")
    notifier = _make_notifier()

    stats = run_execution_cycle(["AAPL"], redis, client, notifier=notifier)

    assert stats["orders_placed"] == 0
    assert stats["skipped_position"] == 1
    client.submit_order.assert_not_called()
    # Should fire a CRITICAL alert when the orders endpoint is unreachable
    notifier.send_alert.assert_called_once()
    _, kwargs = notifier.send_alert.call_args
    assert kwargs["level"] == AlertLevel.CRITICAL


def test_pending_orders_failure_does_not_block_stop_loss():
    """Even when get_orders() fails, stop-loss on open positions must still fire."""
    entry = 100.0
    current = entry * (1 - STOP_LOSS_PCT - 0.01)
    pos = _make_position("AAPL", avg_entry=entry, current=current)
    client = _make_client(positions={"AAPL": pos})
    client.get_orders.side_effect = Exception("Alpaca API error")

    redis = _make_redis(signal=_signal(score=0.8))

    stats = run_execution_cycle(["AAPL"], redis, client)

    assert stats["stop_losses_triggered"] == 1
    client.close_position.assert_called_once_with("AAPL")


class TestDecisionLogging:
    """run_execution_cycle writes execution decisions for candidates (score > threshold)."""

    def _make_signal(self, score=0.5, fallback=False, signal_id=7):
        from datetime import datetime, timezone
        return {
            "score": score, "fallback_used": fallback, "signal_id": signal_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _make_account(self, portfolio_value=10000.0):
        account = MagicMock()
        account.portfolio_value = str(portfolio_value)
        account.last_equity = str(portfolio_value)
        return account

    def test_buy_writes_decision_and_opens_trade(self):
        from unittest.mock import MagicMock, patch
        from src.workers.execution import run_execution_cycle
        from src.store.redis_store import RedisStore

        mock_redis = MagicMock(spec=RedisStore)
        mock_redis.is_killswitch_active.return_value = False
        mock_redis.get_regime.return_value = MagicMock(multiplier=1.0)
        mock_redis.read_sentiment.return_value = self._make_signal(score=0.5)
        mock_redis.get_feedback_entry_threshold.return_value = None

        mock_trading = MagicMock()
        mock_trading.get_account.return_value = self._make_account()
        mock_trading.get_all_positions.return_value = []
        mock_trading.get_orders.return_value = []
        submitted = MagicMock()
        submitted.id = "order-uuid-1"
        mock_trading.submit_order.return_value = submitted

        mock_pg = MagicMock()
        mock_pg.write_execution_decision.return_value = 99

        cache = {"AAPL": {"ema": 90.0, "price": 100.0}}
        with patch("src.workers.execution._build_market_cache", return_value=cache):
            stats = run_execution_cycle(
                symbols=["AAPL"],
                redis_store=mock_redis,
                trading_client=mock_trading,
                pg_store=mock_pg,
                data_client=MagicMock(),
            )

        assert stats["orders_placed"] == 1
        mock_pg.write_execution_decision.assert_called_once()
        call_kwargs = mock_pg.write_execution_decision.call_args[1]
        assert call_kwargs["decision"] == "BUY"
        assert call_kwargs["order_id"] == "order-uuid-1"
        mock_pg.open_trade.assert_called_once()

    def test_below_threshold_no_decision_written(self):
        from unittest.mock import MagicMock
        from src.workers.execution import run_execution_cycle
        from src.store.redis_store import RedisStore

        mock_redis = MagicMock(spec=RedisStore)
        mock_redis.is_killswitch_active.return_value = False
        mock_redis.get_regime.return_value = MagicMock(multiplier=1.0)
        mock_redis.read_sentiment.return_value = self._make_signal(score=0.1)  # below threshold

        mock_trading = MagicMock()
        mock_trading.get_account.return_value = self._make_account()
        mock_trading.get_all_positions.return_value = []
        mock_trading.get_orders.return_value = []

        mock_pg = MagicMock()

        run_execution_cycle(
            symbols=["AAPL"],
            redis_store=mock_redis,
            trading_client=mock_trading,
            pg_store=mock_pg,
        )

        mock_pg.write_execution_decision.assert_not_called()

    def test_stop_loss_writes_close_trade(self):
        from unittest.mock import MagicMock, patch
        from src.workers.execution import run_execution_cycle
        from src.store.redis_store import RedisStore

        mock_redis = MagicMock(spec=RedisStore)
        mock_redis.is_killswitch_active.return_value = False
        mock_redis.get_regime.return_value = MagicMock(multiplier=1.0)
        mock_redis.read_sentiment.return_value = self._make_signal(score=0.5)

        pos = MagicMock()
        pos.symbol = "AAPL"
        pos.avg_entry_price = "200.0"
        pos.current_price = "190.0"  # 5% drop — triggers 2% stop

        mock_trading = MagicMock()
        mock_trading.get_account.return_value = self._make_account()
        mock_trading.get_all_positions.return_value = [pos]
        mock_trading.get_orders.return_value = []

        mock_pg = MagicMock()

        stats = run_execution_cycle(
            symbols=["AAPL"],
            redis_store=mock_redis,
            trading_client=mock_trading,
            pg_store=mock_pg,
        )

        assert stats["stop_losses_triggered"] == 1
        mock_pg.close_trade.assert_called_once()
        call_kwargs = mock_pg.close_trade.call_args[1]
        assert call_kwargs["symbol"] == "AAPL"
        assert call_kwargs["exit_reason"] == "stop_loss"

    def test_no_pg_store_still_places_order(self):
        """pg_store=None → decisions/trades silently skipped, order still placed."""
        from unittest.mock import MagicMock, patch
        from src.workers.execution import run_execution_cycle
        from src.store.redis_store import RedisStore

        mock_redis = MagicMock(spec=RedisStore)
        mock_redis.is_killswitch_active.return_value = False
        mock_redis.get_regime.return_value = MagicMock(multiplier=1.0)
        mock_redis.read_sentiment.return_value = self._make_signal(score=0.5)
        mock_redis.get_feedback_entry_threshold.return_value = None

        mock_trading = MagicMock()
        mock_trading.get_account.return_value = self._make_account()
        mock_trading.get_all_positions.return_value = []
        mock_trading.get_orders.return_value = []
        mock_trading.submit_order.return_value = MagicMock(id="x")

        cache = {"AAPL": {"ema": 90.0, "price": 100.0}}
        with patch("src.workers.execution._build_market_cache", return_value=cache):
            stats = run_execution_cycle(
                symbols=["AAPL"],
                redis_store=mock_redis,
                trading_client=mock_trading,
                pg_store=None,
                data_client=MagicMock(),
            )
        assert stats["orders_placed"] == 1
