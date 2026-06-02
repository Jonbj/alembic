"""Tests for portfolio_scheduler Celery task (T-604)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

from src.backtest.engine.types import OrderSide, OrderType
from src.portfolio.types import CombinedOrder


def _make_combined_order(symbol: str, side: OrderSide = OrderSide.BUY, qty: float = 10.0) -> CombinedOrder:
    return CombinedOrder(
        order_id=f"oid-{symbol}",
        timestamp=datetime(2026, 6, 2, 14, 0, tzinfo=timezone.utc),
        symbol=symbol,
        side=side,
        quantity=qty,
        order_type=OrderType.MARKET,
        strategy_id="S1",
        allocation_weight=0.5,
    )


def _make_bars_df(n: int = 100, symbols: list[str] | None = None) -> pd.DataFrame:
    symbols = symbols or ["SPY", "QQQ", "GLD"]
    data = {sym: [100.0 + i * 0.1 for i in range(n)] for sym in symbols}
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    return pd.DataFrame(data, index=idx)


def _make_market(prices=None):
    from src.backtest.engine.types import MarketSnapshot
    prices = prices or {"SPY": 450.0}
    return MarketSnapshot(
        timestamp=datetime(2026, 6, 2, tzinfo=timezone.utc),
        prices=prices,
        volumes={sym: 1_000_000.0 for sym in prices},
        adv_20d={sym: 1_000_000.0 for sym in prices},
    )


# ── run_portfolio_cycle (Celery entry-point) ──────────────────────────────────


def test_run_portfolio_cycle_returns_skipped_when_no_api_key():
    """Task skips when Alpaca API key is not configured."""
    with patch("src.config.config") as mock_cfg:
        mock_cfg.ALPACA_API_KEY = ""
        mock_cfg.ALPACA_SECRET_KEY = "xxx"
        from src.workers.portfolio_scheduler import run_portfolio_cycle
        result = run_portfolio_cycle.run()
    assert result == {"skipped": True, "reason": "no_credentials"}


def test_run_portfolio_cycle_returns_skipped_when_no_secret_key():
    """Task skips when Alpaca secret key is not configured."""
    with patch("src.config.config") as mock_cfg:
        mock_cfg.ALPACA_API_KEY = "xxx"
        mock_cfg.ALPACA_SECRET_KEY = ""
        from src.workers.portfolio_scheduler import run_portfolio_cycle
        result = run_portfolio_cycle.run()
    assert result == {"skipped": True, "reason": "no_credentials"}


def test_run_portfolio_cycle_returns_error_dict_on_exception():
    """Unhandled exceptions are caught and returned as error dict."""
    with patch("src.config.config") as mock_cfg:
        mock_cfg.ALPACA_API_KEY = "xxx"
        mock_cfg.ALPACA_SECRET_KEY = "xxx"
        with patch(
            "src.workers.portfolio_scheduler._run_cycle_inner",
            side_effect=RuntimeError("boom"),
        ):
            from src.workers.portfolio_scheduler import run_portfolio_cycle
            result = run_portfolio_cycle.run()
    assert "error" in result
    assert "boom" in result["error"]


# ── _build_strategy_instance ──────────────────────────────────────────────────


def test_build_strategy_instance_s1_returns_none_with_insufficient_bars():
    """S1 needs ≥21 bars; returns None with fewer."""
    from src.workers.portfolio_scheduler import _build_strategy_instance

    entry = MagicMock()
    entry.strategy_id = "S1"
    bars_df = _make_bars_df(n=20, symbols=["SPY"])
    assert _build_strategy_instance(entry, bars_df) is None


def test_build_strategy_instance_s1_returns_instance_with_enough_bars():
    """S1 returns a TimeSeriesMomentum instance when bars ≥ 21."""
    from src.strategies.s1.strategy import TimeSeriesMomentum
    from src.workers.portfolio_scheduler import _build_strategy_instance

    entry = MagicMock()
    entry.strategy_id = "S1"
    bars_df = _make_bars_df(n=50, symbols=["SPY", "QQQ"])
    result = _build_strategy_instance(entry, bars_df)
    assert isinstance(result, TimeSeriesMomentum)


def test_build_strategy_instance_s2_creates_instance_without_spy():
    """S2 falls back to first column when SPY is absent — still returns instance."""
    from src.strategies.s2.strategy import VRPStrategy
    from src.workers.portfolio_scheduler import _build_strategy_instance

    entry = MagicMock()
    entry.strategy_id = "S2"
    bars_df = _make_bars_df(n=100, symbols=["QQQ", "GLD"])
    result = _build_strategy_instance(entry, bars_df)
    assert isinstance(result, VRPStrategy)


def test_build_strategy_instance_s2_returns_none_with_too_few_bars():
    """S2 requires ≥63 bars; returns None with fewer."""
    from src.workers.portfolio_scheduler import _build_strategy_instance

    entry = MagicMock()
    entry.strategy_id = "S2"
    bars_df = _make_bars_df(n=30, symbols=["SPY"])
    assert _build_strategy_instance(entry, bars_df) is None


def test_build_strategy_instance_s4_returns_instance():
    """S4 requires no minimum bars; always returns NewsDrivenTactical."""
    from src.strategies.s4.strategy import NewsDrivenTactical
    from src.workers.portfolio_scheduler import _build_strategy_instance

    entry = MagicMock()
    entry.strategy_id = "S4"
    bars_df = _make_bars_df(n=5, symbols=["SPY"])
    result = _build_strategy_instance(entry, bars_df)
    assert isinstance(result, NewsDrivenTactical)


def test_build_strategy_instance_returns_none_for_unknown_id():
    """Unknown strategy_id logs a warning and returns None."""
    from src.workers.portfolio_scheduler import _build_strategy_instance

    entry = MagicMock()
    entry.strategy_id = "S99"
    bars_df = _make_bars_df(n=100)
    assert _build_strategy_instance(entry, bars_df) is None


# ── _submit_portfolio_orders ──────────────────────────────────────────────────


def test_submit_portfolio_orders_places_buy_orders():
    """BUY-side combined orders are submitted via _submit_fn."""
    from src.workers.portfolio_scheduler import _submit_portfolio_orders

    orders = [_make_combined_order("SPY", OrderSide.BUY, qty=10.0)]
    trading_client = MagicMock()
    market = _make_market(prices={"SPY": 450.0})

    # Use _submit_fn to avoid alpaca import
    submitted_calls = []
    def mock_submit(order, notional, client):
        submitted_calls.append((order.symbol, notional))

    submitted = _submit_portfolio_orders(orders, trading_client, market, _submit_fn=mock_submit)
    assert submitted == 1
    assert submitted_calls[0][0] == "SPY"


def test_submit_portfolio_orders_submits_sell_orders():
    """SELL-side orders are submitted to Alpaca like BUY orders."""
    from src.workers.portfolio_scheduler import _submit_portfolio_orders

    orders = [_make_combined_order("SPY", OrderSide.SELL, qty=10.0)]
    trading_client = MagicMock()
    market = _make_market()

    submitted = _submit_portfolio_orders(orders, trading_client, market, _submit_fn=lambda o, n, c: None)
    assert submitted == 1


def test_submit_portfolio_orders_returns_zero_for_empty_list():
    """Empty order list → 0 submitted, no API calls."""
    from src.workers.portfolio_scheduler import _submit_portfolio_orders

    trading_client = MagicMock()
    market = _make_market()

    submitted = _submit_portfolio_orders([], trading_client, market, _submit_fn=lambda o, n, c: None)
    assert submitted == 0


def test_submit_portfolio_orders_continues_after_single_failure():
    """An error on one order does not abort remaining orders."""
    from src.workers.portfolio_scheduler import _submit_portfolio_orders

    orders = [
        _make_combined_order("SPY", OrderSide.BUY, qty=10.0),
        _make_combined_order("QQQ", OrderSide.BUY, qty=5.0),
    ]
    trading_client = MagicMock()
    market = _make_market(prices={"SPY": 100.0, "QQQ": 100.0})

    call_count = 0
    def mock_submit(order, notional, client):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("API error")

    submitted = _submit_portfolio_orders(orders, trading_client, market, _submit_fn=mock_submit)
    assert submitted == 1  # only the successful one counts


def test_submit_portfolio_orders_mixed_buy_sell():
    """Both BUY and SELL orders are submitted."""
    from src.workers.portfolio_scheduler import _submit_portfolio_orders

    orders = [
        _make_combined_order("SPY", OrderSide.BUY, qty=10.0),
        _make_combined_order("QQQ", OrderSide.SELL, qty=5.0),
        _make_combined_order("GLD", OrderSide.BUY, qty=3.0),
    ]
    trading_client = MagicMock()
    market = _make_market(prices={"SPY": 100.0, "QQQ": 100.0, "GLD": 100.0})

    submitted_syms = []
    def mock_submit(order, notional_or_qty, client):
        submitted_syms.append(order.symbol)

    submitted = _submit_portfolio_orders(orders, trading_client, market, _submit_fn=mock_submit)
    assert submitted == 3
    assert submitted_syms == ["SPY", "QQQ", "GLD"]


# ── _persist_cycle_result ─────────────────────────────────────────────────────


def test_persist_cycle_result_executes_insert():
    """Cycle stats are persisted to portfolio_cycles table."""
    from src.workers.portfolio_scheduler import _persist_cycle_result

    mock_cur = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    cycle_data = {
        "timestamp": datetime(2026, 6, 2, 14, 0, tzinfo=timezone.utc),
        "strategies_run": ["S1", "S2"],
        "orders_count": 3,
        "constraints_fired": [],
        "final_orders": [],
    }

    _persist_cycle_result(cycle_data, conn=mock_conn)
    mock_cur.execute.assert_called_once()
    mock_conn.commit.assert_called_once()


def test_persist_cycle_result_does_not_raise_on_db_error():
    """DB write failures are logged and swallowed — never crash the cycle."""
    from src.workers.portfolio_scheduler import _persist_cycle_result

    mock_cur = MagicMock()
    mock_cur.execute.side_effect = Exception("DB down")
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    cycle_data = {
        "timestamp": datetime(2026, 6, 2, 14, 0, tzinfo=timezone.utc),
        "strategies_run": ["S1"],
        "orders_count": 0,
        "constraints_fired": [],
        "final_orders": [],
    }

    # Must not raise
    _persist_cycle_result(cycle_data, conn=mock_conn)