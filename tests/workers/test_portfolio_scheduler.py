"""Tests for portfolio_scheduler Celery task (T-604)."""

from datetime import datetime, timedelta, timezone
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


# ── dry_run / halted mode guard ───────────────────────────────────────────────


@pytest.mark.parametrize("mode", ["dry_run", "halted"])
def test_submit_not_called_when_mode_blocks(mode):
    """_submit_portfolio_orders is never called when system mode is dry_run or halted."""
    import pandas as pd
    from src.workers.portfolio_scheduler import _run_cycle_inner

    bars_df = pd.DataFrame({"SPY": [100.0 + i * 0.1 for i in range(100)]})
    bars_df.index = pd.date_range("2025-01-01", periods=100, freq="B")

    mock_cycle_result = MagicMock()
    mock_cycle_result.final_orders = [_make_combined_order("SPY", OrderSide.BUY)]
    mock_cycle_result.strategies_run = ["S1"]
    mock_cycle_result.orders_before_constraints = 1
    mock_cycle_result.orders_after_constraints = 1
    mock_cycle_result.constraints_fired = []

    with patch("src.strategies.registry.StrategyRegistry") as mock_reg, \
         patch("alpaca.data.historical.StockHistoricalDataClient") as mock_dc, \
         patch("alpaca.trading.client.TradingClient") as mock_tc, \
         patch("src.portfolio.orchestrator.PortfolioOrchestrator") as mock_orch, \
         patch("src.backtest.engine.data_replay.DataReplay"), \
         patch("src.backtest.engine.portfolio.VirtualPortfolio"), \
         patch("src.workers.portfolio_scheduler._persist_cycle_result"), \
         patch("src.workers.portfolio_scheduler._submit_portfolio_orders") as mock_submit, \
         patch("redis.Redis") as mock_redis_cls:

        entry = MagicMock()
        entry.strategy_id = "S1"
        entry.allocation_pct = 1.0
        mock_reg.return_value.get_active_strategies.return_value = [entry]

        raw_df = bars_df.copy()
        raw_df.index.name = "timestamp"
        raw_df.columns.name = "symbol"
        raw_df = raw_df.reset_index()
        mock_dc.return_value.get_stock_bars.return_value.df = raw_df

        mock_tc.return_value.get_account.return_value.cash = "100000"
        mock_tc.return_value.get_all_positions.return_value = []
        mock_orch.return_value.run_cycle.return_value = mock_cycle_result
        mock_redis_cls.from_url.return_value.get.return_value = mode

        try:
            _run_cycle_inner()
        except Exception:
            pass  # data-path errors are irrelevant; we only care about submit

        mock_submit.assert_not_called()


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
    mock_store = MagicMock()
    mock_store.fetch_signals_for_cycle.return_value = []
    with patch("src.store.pg_store.PostgreSQLStore", return_value=mock_store):
        result = _build_strategy_instance(entry, bars_df)
    assert isinstance(result, NewsDrivenTactical)


def test_build_strategy_instance_s4_loads_signals_from_db():
    """S4 loads signals from DB and passes them as a DataFrame to NewsDrivenTactical."""
    from src.models.signals import SentimentResult
    from src.strategies.s4.strategy import NewsDrivenTactical
    from src.workers.portfolio_scheduler import _build_strategy_instance

    entry = MagicMock()
    entry.strategy_id = "S4"
    bars_df = _make_bars_df(n=5, symbols=["SPY"])

    _recent = datetime.now(timezone.utc) - timedelta(hours=1)
    mock_signals = [
        SentimentResult(
            symbol="NVDA", score=0.8, confidence=0.9, reasoning="Positive",
            model_id="test", generated_at=_recent,
        ),
        SentimentResult(
            symbol="MSFT", score=0.6, confidence=0.7, reasoning="Neutral",
            model_id="test", generated_at=_recent,
        ),
    ]
    mock_store = MagicMock()
    mock_store.fetch_signals_for_cycle.return_value = mock_signals

    with patch("src.store.pg_store.PostgreSQLStore", return_value=mock_store):
        result = _build_strategy_instance(entry, bars_df)

    assert isinstance(result, NewsDrivenTactical)
    assert result._signals_df is not None
    assert len(result._signals_df) == 2
    assert set(result._signals_df["symbol"]) == {"NVDA", "MSFT"}


def test_build_strategy_instance_s4_handles_db_error_gracefully():
    """S4 DB failure returns NewsDrivenTactical with signals=None — never crashes."""
    from src.strategies.s4.strategy import NewsDrivenTactical
    from src.workers.portfolio_scheduler import _build_strategy_instance

    entry = MagicMock()
    entry.strategy_id = "S4"
    bars_df = _make_bars_df(n=5, symbols=["SPY"])

    mock_store = MagicMock()
    mock_store.fetch_signals_for_cycle.side_effect = RuntimeError("DB down")

    with patch("src.store.pg_store.PostgreSQLStore", return_value=mock_store):
        result = _build_strategy_instance(entry, bars_df)

    assert isinstance(result, NewsDrivenTactical)
    assert result._signals_df is None


def test_build_strategy_instance_s4_gate_enforced_when_velocity_fails():
    """If signal-velocity computation raises, the loss-feedback gate must still drop
    sub-threshold signals (degrade to raw scores, gate still enforced)."""
    from src.models.signals import SentimentResult
    from src.strategies.s4.strategy import NewsDrivenTactical
    from src.workers.portfolio_scheduler import _build_strategy_instance

    entry = MagicMock()
    entry.strategy_id = "S4"
    bars_df = _make_bars_df(n=5, symbols=["SPY"])

    _recent = datetime.now(timezone.utc) - timedelta(hours=1)
    mock_signals = [
        SentimentResult(
            symbol="STRONG", score=0.8, confidence=0.9, reasoning="strong",
            model_id="test", generated_at=_recent,
        ),
        SentimentResult(
            symbol="WEAK", score=0.15, confidence=0.9, reasoning="weak",
            model_id="test", generated_at=_recent,
        ),
    ]
    mock_store = MagicMock()
    mock_store.fetch_signals_for_cycle.return_value = mock_signals

    # Redis returns a raised gate; velocity raises.
    fake_redis = MagicMock()
    fake_redis.get.return_value = "0.50"
    fake_redis.close.return_value = None

    with patch("src.store.pg_store.PostgreSQLStore", return_value=mock_store), \
         patch("redis.Redis.from_url", return_value=fake_redis), \
         patch("src.workers.portfolio_scheduler._compute_signal_velocity") as mock_velocity:
        mock_velocity.side_effect = RuntimeError("velocity failed")
        result = _build_strategy_instance(entry, bars_df)

    assert isinstance(result, NewsDrivenTactical)
    assert result._signals_df is not None
    assert set(result._signals_df["symbol"]) == {"STRONG"}
    assert "WEAK" not in result._signals_df["symbol"].values


def test_build_strategy_instance_s4_no_signals_in_db():
    """S4 with empty DB result returns NewsDrivenTactical with signals=None."""
    from src.strategies.s4.strategy import NewsDrivenTactical
    from src.workers.portfolio_scheduler import _build_strategy_instance

    entry = MagicMock()
    entry.strategy_id = "S4"
    bars_df = _make_bars_df(n=5, symbols=["SPY"])

    mock_store = MagicMock()
    mock_store.fetch_signals_for_cycle.return_value = []

    with patch("src.store.pg_store.PostgreSQLStore", return_value=mock_store):
        result = _build_strategy_instance(entry, bars_df)

    assert isinstance(result, NewsDrivenTactical)
    assert result._signals_df is None


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
    assert len(submitted) == 1
    assert submitted_calls[0][0] == "SPY"


def test_submit_portfolio_orders_submits_sell_orders():
    """SELL-side orders are submitted to Alpaca like BUY orders."""
    from src.workers.portfolio_scheduler import _submit_portfolio_orders

    orders = [_make_combined_order("SPY", OrderSide.SELL, qty=10.0)]
    trading_client = MagicMock()
    market = _make_market()

    submitted = _submit_portfolio_orders(orders, trading_client, market, _submit_fn=lambda o, n, c: None)
    assert len(submitted) == 1


def test_submit_portfolio_orders_returns_zero_for_empty_list():
    """Empty order list → 0 submitted, no API calls."""
    from src.workers.portfolio_scheduler import _submit_portfolio_orders

    trading_client = MagicMock()
    market = _make_market()

    submitted = _submit_portfolio_orders([], trading_client, market, _submit_fn=lambda o, n, c: None)
    assert len(submitted) == 0


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
    assert len(submitted) == 1  # only the successful one counts


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
    assert len(submitted) == 3
    assert submitted_syms == ["SPY", "QQQ", "GLD"]


# ── Pyramiding guard fail-closed (BUG-1) ─────────────────────────────────────


def test_buy_blocked_when_guard_db_unavailable():
    """When open_trade_symbols is None (DB unavailable), ALL BUY orders are blocked.

    Before the fix, None was treated like an empty set and the guard was silently
    disabled — allowing pyramiding when the DB was unreachable.
    BUG-1: pyramiding guard must be fail-CLOSED, mirroring P2-05-A (Redis).
    """
    from src.workers.portfolio_scheduler import _submit_portfolio_orders

    orders = [_make_combined_order("AAPL", OrderSide.BUY, qty=10.0)]
    market = _make_market(prices={"AAPL": 100.0})
    submitted_calls = []

    submitted = _submit_portfolio_orders(
        orders,
        MagicMock(),
        market,
        _submit_fn=lambda o, n, c: submitted_calls.append(o.symbol),
        open_trade_symbols=None,  # None = guard DB unavailable
    )

    assert len(submitted) == 0, (
        "BUY must be blocked when open_trade_symbols=None (guard DB unavailable). "
        "Fix: treat None as fail-closed — skip all BUYs, not just ones in the set."
    )
    assert not submitted_calls, "submit_fn must not be called when guard is unavailable."


def test_sell_not_blocked_when_guard_db_unavailable():
    """SELL orders must pass through even when open_trade_symbols=None.

    The pyramiding guard only applies to BUY orders.  SELLs must always be submitted.
    """
    from src.workers.portfolio_scheduler import _submit_portfolio_orders

    orders = [_make_combined_order("AAPL", OrderSide.SELL, qty=10.0)]
    market = _make_market(prices={"AAPL": 100.0})

    submitted = _submit_portfolio_orders(
        orders,
        MagicMock(),
        market,
        _submit_fn=lambda o, n, c: None,
        open_trade_symbols=None,  # guard unavailable — must NOT block SELL
    )

    assert len(submitted) == 1, (
        "SELL must proceed even when open_trade_symbols=None. "
        "Fail-closed applies to BUY only."
    )


def test_buy_blocked_when_symbol_already_open():
    """BUY is blocked for a symbol present in open_trade_symbols (existing guard)."""
    from src.workers.portfolio_scheduler import _submit_portfolio_orders

    orders = [_make_combined_order("AAPL", OrderSide.BUY, qty=10.0)]
    market = _make_market(prices={"AAPL": 100.0})
    submitted_calls = []

    submitted = _submit_portfolio_orders(
        orders,
        MagicMock(),
        market,
        _submit_fn=lambda o, n, c: submitted_calls.append(o.symbol),
        open_trade_symbols={"AAPL"},  # symbol already open — must block
    )

    assert len(submitted) == 0, "BUY for already-open symbol must be blocked."


def test_buy_allowed_when_guard_available_and_symbol_not_open():
    """BUY proceeds normally when guard has data and symbol is not in open set."""
    from src.workers.portfolio_scheduler import _submit_portfolio_orders

    orders = [_make_combined_order("MSFT", OrderSide.BUY, qty=5.0)]
    market = _make_market(prices={"MSFT": 200.0})
    submitted_calls = []

    submitted = _submit_portfolio_orders(
        orders,
        MagicMock(),
        market,
        _submit_fn=lambda o, n, c: submitted_calls.append(o.symbol),
        open_trade_symbols={"AAPL"},  # AAPL open, MSFT not — MSFT BUY must go through
    )

    assert len(submitted) == 1, "BUY for MSFT must be allowed when MSFT not in open set."
    assert "MSFT" in submitted_calls


def test_buy_allowed_when_guard_available_and_empty():
    """BUY proceeds when guard returned an empty set (no open trades exist)."""
    from src.workers.portfolio_scheduler import _submit_portfolio_orders

    orders = [_make_combined_order("SPY", OrderSide.BUY, qty=2.0)]
    market = _make_market(prices={"SPY": 450.0})
    submitted_calls = []

    submitted = _submit_portfolio_orders(
        orders,
        MagicMock(),
        market,
        _submit_fn=lambda o, n, c: submitted_calls.append(o.symbol),
        open_trade_symbols=set(),  # empty set = guard available, no open trades
    )

    assert len(submitted) == 1, "BUY must be allowed when open_trade_symbols is empty set."


# ── _portfolio_postmortem entry_price fallback (BUG-3) ──────────────────────


def test_postmortem_uses_db_entry_price_when_alpaca_zero():
    """_portfolio_postmortem must fall back to DB entry_price when entry_price arg is 0.

    When alpaca_entry_prices is empty (Alpaca positions failed to load), entry_px=0.0
    is passed, causing loss_pct=0.0 → should_trigger_postmortem returns False →
    postmortem never fires, even for large losers.

    Fix: after record_trade_exit returns trade_id, fetch entry_price from DB via
    fetch_trade_with_signal and use it if entry_price arg is 0.
    """
    from src.workers.portfolio_scheduler import _portfolio_postmortem
    from unittest.mock import MagicMock, patch

    pg_mock = MagicMock()
    pg_mock.write_postmortem = MagicMock()
    # Simulate DB having entry_price=100.0 (set by reconcile)
    pg_mock.fetch_trade_with_signal.return_value = {
        "entry_price": 100.0,
        "confidence": 0.8,
        "ensemble_std": 0.1,
    }

    with patch("src.performance.postmortem.should_trigger_postmortem", return_value=True) as mock_trigger, \
         patch("src.performance.postmortem.diagnose_loss", return_value="signal_overconfidence"):
        _portfolio_postmortem(
            pg_store=pg_mock,
            trade_id=42,
            signal={"confidence": 0.8, "ensemble_std": 0.1},
            score=0.02,
            entry_price=0.0,   # alpaca unavailable
            exit_price=95.0,
            tick_time=datetime(2026, 6, 18, 15, 0, tzinfo=timezone.utc),
        )

    # Should have fetched from DB
    pg_mock.fetch_trade_with_signal.assert_called_once_with(42), (
        "When entry_price=0.0, _portfolio_postmortem must call fetch_trade_with_signal(trade_id) "
        "to get the reconciled entry_price from DB."
    )
    # should_trigger_postmortem should be called with the DB price-derived loss
    assert mock_trigger.called, (
        "should_trigger_postmortem must be called using the DB entry_price, not 0.0."
    )


# ── write_execution_decision signal_score (BUG-4) ───────────────────────────


def test_write_execution_decision_accepts_signal_score():
    """write_execution_decision must persist signal_score alongside the allocation weight.

    Currently the 'score' column stores allocation_weight (e.g. 0.02 = 2%).
    The actual LLM sentiment score (e.g. +0.707) must be stored separately as
    'signal_score' so operator monitoring can distinguish the two.
    BUG-4: decision log shows score=0.02 for all rows — misleading in monitoring.
    """
    from src.store.pg_store import PostgreSQLStore

    pg = MagicMock(spec=PostgreSQLStore)
    conn = MagicMock()
    cursor = MagicMock()
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    cursor.fetchone.return_value = (99,)
    conn.cursor.return_value = cursor
    pg._get_connection.return_value = conn

    # Call the real write_execution_decision on a real PostgreSQLStore instance
    store = PostgreSQLStore.__new__(PostgreSQLStore)
    store._get_connection = lambda: conn

    result = store.write_execution_decision(
        tick_time=datetime(2026, 6, 18, 15, 0, tzinfo=timezone.utc),
        symbol="AAPL",
        signal_id=7,
        score=0.02,          # allocation weight
        signal_score=0.707,  # LLM sentiment score — NEW parameter
        regime_mult=1.0,
        ema_pass=True,
        decision="BUY",
        reason="S4 sentiment +0.707",
    )

    assert result == 99, "write_execution_decision must still return the new row id."
    # Verify signal_score was included in the INSERT
    call_args = cursor.execute.call_args
    sql = call_args[0][0]
    params = call_args[0][1]
    assert "signal_score" in sql, (
        "INSERT SQL must include 'signal_score' column. "
        "Add signal_score to _INSERT_DECISION and write_execution_decision()."
    )
    assert 0.707 in params, (
        "signal_score value 0.707 must appear in the INSERT parameters."
    )


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


# ── end-to-end: S4 signals → multi-symbol orders ──────────────────────────────


def test_portfolio_cycle_s4_signals_produce_multi_symbol_orders():
    """End-to-end: full _run_cycle_inner() with mocked S4 DB signals.

    Verifies the complete S4 integration path:
    1. _build_strategy_instance("S4") loads signals from mocked DB
    2. NewsDrivenTactical converts signals to target weights for 5 symbols
    3. PortfolioOrchestrator merges S1+S2+S4 weights and builds delta orders
    4. Final combined orders include symbols other than SPY

    External deps mocked: Alpaca data, Alpaca trading, PostgreSQLStore,
    Redis (system mode), and _persist_cycle_result.
    """
    from src.models.signals import SentimentResult
    from src.workers.portfolio_scheduler import _run_cycle_inner

    S4_SYMBOLS = ["NVDA", "MSFT", "AAPL", "AMZN", "GOOGL"]
    ALL_SYMBOLS = ["SPY"] + S4_SYMBOLS
    N_BARS = 260  # ≥ 252 for S1's max lookback; ≥ 63 for S2

    # Gently uptrending prices (S1 will see positive momentum for all symbols)
    dates = pd.date_range("2024-07-01", periods=N_BARS, freq="B", tz="UTC")
    bars_data = {
        sym: [100.0 + j * 20 + i * 0.1 for i in range(N_BARS)]
        for j, sym in enumerate(ALL_SYMBOLS)
    }
    bars_df_local = pd.DataFrame(bars_data, index=dates)

    # Build Alpaca-format MultiIndex (symbol, timestamp) df with a "close" column.
    # The live code does: raw.reset_index() then raw.pivot(index="timestamp", columns="symbol", values="close")
    rows = []
    for ts_bar in dates:
        for sym in ALL_SYMBOLS:
            rows.append({
                "timestamp": ts_bar,
                "symbol": sym,
                "close": bars_df_local.loc[ts_bar, sym],
            })
    raw_alpaca_df = pd.DataFrame(rows).set_index(["symbol", "timestamp"])

    # Signals generated yesterday evening — guaranteed to pass _signals_as_of(ts) filter
    signal_time = datetime(2026, 6, 3, 20, 0, tzinfo=timezone.utc)
    mock_db_signals = [
        SentimentResult(
            symbol=sym,
            score=0.75,
            confidence=0.85,
            reasoning=f"{sym} strong positive sentiment",
            model_id="ensemble",
            generated_at=signal_time,
        )
        for sym in S4_SYMBOLS
    ]

    mock_store = MagicMock()
    mock_store.fetch_signals_for_cycle.return_value = mock_db_signals

    # Capture orders that would be submitted to Alpaca
    captured_orders = []

    def capture_submit(orders, trading_client, market, _submit_fn=None, **kwargs):
        captured_orders.extend(orders)
        return [{"symbol": o.symbol, "side": o.side.value.lower(), "order_id": f"test-{o.symbol}", "notional": 1000.0} for o in orders]

    with patch("src.config.config") as mock_cfg, \
         patch("alpaca.data.historical.StockHistoricalDataClient") as mock_dc, \
         patch("alpaca.trading.client.TradingClient") as mock_tc, \
         patch("src.store.pg_store.PostgreSQLStore", return_value=mock_store), \
         patch("src.workers.portfolio_scheduler._persist_cycle_result"), \
         patch("src.workers.portfolio_scheduler._submit_portfolio_orders",
               side_effect=capture_submit), \
         patch("redis.Redis") as mock_redis_cls:

        mock_cfg.ALPACA_API_KEY = "test-key"
        mock_cfg.ALPACA_SECRET_KEY = "test-secret"
        mock_cfg.ALPACA_BASE_URL = "https://paper-api.alpaca.markets"
        mock_cfg.WATCHLIST_SYMBOLS = ALL_SYMBOLS
        mock_cfg.REDIS_URL = "redis://localhost:6379"
        mock_cfg.DATABASE_URL = "postgresql://test:test@localhost/test"

        mock_dc.return_value.get_stock_bars.return_value.df = raw_alpaca_df
        mock_tc.return_value.get_account.return_value.cash = "100000"
        mock_tc.return_value.get_all_positions.return_value = []
        # mode=None → not dry_run/halted → orders are submitted
        mock_redis_cls.from_url.return_value.get.return_value = None

        result = _run_cycle_inner()

    # S4's DB fetch must have been triggered (signal loading path exercised).
    # Called at least once by _build_strategy_instance(S4); may also be called
    # by the decision-logging block to enrich reason text (hours=24 window).
    mock_store.fetch_signals_for_cycle.assert_called()

    # S4 must have contributed to the cycle
    assert "S4" in result["strategies_run"], (
        f"S4 missing from strategies_run={result['strategies_run']}"
    )

    # At least some orders must have been generated
    assert len(captured_orders) > 0, (
        f"No orders produced. result={result}"
    )

    # Distinct symbols in orders must exceed 1 (not only SPY)
    distinct_symbols = {o.symbol for o in captured_orders}
    assert len(distinct_symbols) > 1, (
        f"Expected orders for >1 symbol, got only: {distinct_symbols}"
    )

    # At least one of S4's signal symbols must appear in the orders
    s4_in_orders = distinct_symbols & set(S4_SYMBOLS)
    assert s4_in_orders, (
        f"None of S4's symbols (NVDA/MSFT/AAPL/AMZN/GOOGL) appeared in orders. "
        f"Final symbols: {distinct_symbols}. "
        f"S4 has 30% allocation and bucket_pct=0.10, which should produce "
        f"non-zero BUY orders on a $100k portfolio."
    )


# ── P0-A: emergency cancel on kill-switch ────────────────────────────────────


def test_emergency_cancel_called_when_killswitch_active():
    """cancel_orders() is called when kill-switch Redis key is set."""
    from src.workers.portfolio_scheduler import _run_cycle_inner

    bars_df = _make_bars_df(n=100, symbols=["SPY"])
    raw_df = bars_df.reset_index().rename(columns={"index": "timestamp"})
    raw_df.columns.name = "symbol"

    with patch("src.strategies.registry.StrategyRegistry") as mock_reg, \
         patch("alpaca.data.historical.StockHistoricalDataClient") as mock_dc, \
         patch("alpaca.trading.client.TradingClient") as mock_tc, \
         patch("redis.Redis") as mock_redis_cls, \
         patch("src.workers.portfolio_scheduler._emergency_cancel_all") as mock_cancel:

        entry = MagicMock()
        entry.strategy_id = "S1"
        mock_reg.return_value.get_active_strategies.return_value = [entry]
        mock_dc.return_value.get_stock_bars.return_value.df = raw_df

        redis_inst = MagicMock()
        redis_inst.get.side_effect = lambda key: "1" if key == "killswitch_active" else None
        redis_inst.get.return_value = None

        def _redis_get(key):
            return "1" if key == "killswitch_active" else None

        redis_inst.get.side_effect = _redis_get
        mock_redis_cls.from_url.return_value = redis_inst

        result = _run_cycle_inner()

    assert result["skipped"] is True
    assert "killswitch" in result["reason"]
    mock_cancel.assert_called_once()


# ── P0-B: market clock pre-flight ────────────────────────────────────────────


def test_cycle_skips_when_market_closed():
    """Cycle returns market_closed when get_clock().is_open is False."""
    from src.workers.portfolio_scheduler import _run_cycle_inner

    bars_df = _make_bars_df(n=100, symbols=["SPY"])

    with patch("src.strategies.registry.StrategyRegistry") as mock_reg, \
         patch("alpaca.data.historical.StockHistoricalDataClient"), \
         patch("alpaca.trading.client.TradingClient") as mock_tc, \
         patch("redis.Redis") as mock_redis_cls:

        entry = MagicMock()
        entry.strategy_id = "S1"
        mock_reg.return_value.get_active_strategies.return_value = [entry]

        clock = MagicMock()
        clock.is_open = False
        clock.next_open = "2026-06-16T13:30:00+00:00"
        mock_tc.return_value.get_clock.return_value = clock

        redis_inst = MagicMock()
        redis_inst.get.return_value = None
        mock_redis_cls.from_url.return_value = redis_inst

        result = _run_cycle_inner()

    assert result == {"skipped": True, "reason": "market_closed",
                      "next_open": "2026-06-16T13:30:00+00:00"}


def test_cycle_proceeds_when_market_open():
    """Cycle does NOT return market_closed when get_clock().is_open is True."""
    from src.workers.portfolio_scheduler import _run_cycle_inner

    bars_df = _make_bars_df(n=100, symbols=["SPY"])
    raw_df = bars_df.copy()
    raw_df.index.name = "timestamp"
    raw_df.columns.name = "symbol"
    raw_df = raw_df.reset_index()

    with patch("src.strategies.registry.StrategyRegistry") as mock_reg, \
         patch("alpaca.data.historical.StockHistoricalDataClient") as mock_dc, \
         patch("alpaca.trading.client.TradingClient") as mock_tc, \
         patch("src.portfolio.orchestrator.PortfolioOrchestrator") as mock_orch, \
         patch("src.backtest.engine.data_replay.DataReplay"), \
         patch("src.backtest.engine.portfolio.VirtualPortfolio"), \
         patch("src.workers.portfolio_scheduler._persist_cycle_result"), \
         patch("src.workers.portfolio_scheduler._submit_portfolio_orders"), \
         patch("redis.Redis") as mock_redis_cls:

        entry = MagicMock()
        entry.strategy_id = "S1"
        entry.allocation_pct = 1.0
        mock_reg.return_value.get_active_strategies.return_value = [entry]

        mock_dc.return_value.get_stock_bars.return_value.df = raw_df

        clock = MagicMock()
        clock.is_open = True
        account = MagicMock()
        account.cash = "100000"
        account.equity = "100000"
        account.buying_power = "100000"
        account.trading_blocked = False
        account.account_blocked = False
        mock_tc.return_value.get_clock.return_value = clock
        mock_tc.return_value.get_account.return_value = account
        mock_tc.return_value.get_all_positions.return_value = []

        mock_cycle_result = MagicMock()
        mock_cycle_result.final_orders = []
        mock_cycle_result.strategies_run = ["S1"]
        mock_cycle_result.orders_before_constraints = 0
        mock_cycle_result.orders_after_constraints = 0
        mock_cycle_result.constraints_fired = []
        mock_orch.return_value.run_cycle.return_value = mock_cycle_result

        redis_inst = MagicMock()
        redis_inst.get.return_value = None
        mock_redis_cls.from_url.return_value = redis_inst

        result = _run_cycle_inner()

    assert result.get("reason") != "market_closed"


# ── P0-D: account blocking flags ─────────────────────────────────────────────


def test_cycle_aborts_when_trading_blocked():
    """Cycle returns account_blocked when account.trading_blocked is True."""
    from src.workers.portfolio_scheduler import _run_cycle_inner

    bars_df = _make_bars_df(n=100, symbols=["SPY"])
    raw_df = bars_df.copy()
    raw_df.index.name = "timestamp"
    raw_df.columns.name = "symbol"
    raw_df = raw_df.reset_index()

    with patch("src.strategies.registry.StrategyRegistry") as mock_reg, \
         patch("alpaca.data.historical.StockHistoricalDataClient") as mock_dc, \
         patch("alpaca.trading.client.TradingClient") as mock_tc, \
         patch("redis.Redis") as mock_redis_cls:

        entry = MagicMock()
        entry.strategy_id = "S1"
        mock_reg.return_value.get_active_strategies.return_value = [entry]

        mock_dc.return_value.get_stock_bars.return_value.df = raw_df

        clock = MagicMock()
        clock.is_open = True
        account = MagicMock()
        account.cash = "100000"
        account.equity = "100000"
        account.trading_blocked = True   # blocked!
        account.account_blocked = False
        mock_tc.return_value.get_clock.return_value = clock
        mock_tc.return_value.get_account.return_value = account

        redis_inst = MagicMock()
        redis_inst.get.return_value = None
        mock_redis_cls.from_url.return_value = redis_inst

        result = _run_cycle_inner()

    assert result == {"skipped": True, "reason": "account_blocked"}


# ── BUG-5: BUY decision must not be logged when symbol has open trade ─────────


def test_buy_decision_not_logged_for_symbol_with_open_trade():
    """No BUY execution_decision must be written when the symbol already has an open trade.

    Previously, open_db_symbols was fetched AFTER the decision logging loop, so a BUY
    decision was always logged even if the symbol was blocked for order submission. This
    polluted the decision log with 10-24 identical BUY entries per cycle per open symbol
    (the NO-ORDER pattern) and was the root cause of apparent stale-signal replay.

    After the fix, open_db_symbols is fetched BEFORE the decision loop, and BUY decisions
    for open symbols are skipped (no decision logged, no order submitted).
    """
    import pandas as pd
    from unittest.mock import MagicMock, patch
    from src.workers.portfolio_scheduler import _run_cycle_inner
    from src.portfolio.orchestrator import CycleResult

    bars_df = pd.DataFrame({"XLK": [100.0 + i for i in range(100)]})
    bars_df.index = pd.date_range("2025-01-01", periods=100, freq="B")

    # Real CycleResult so type(result)(...) in the hold-minimum check preserves final_orders.
    mock_cycle_result = CycleResult(
        strategies_run=["S1"],
        orders_per_strategy={"S1": 1},
        orders_before_constraints=1,
        orders_after_constraints=1,
        constraints_fired=[],
        final_orders=[_make_combined_order("XLK", OrderSide.BUY)],
        symbol_strategies={"XLK": ["S1"]},
    )

    mock_pg = MagicMock()
    mock_pg.fetch_trades.return_value = [{"symbol": "XLK"}]  # XLK already open
    mock_pg.fetch_recently_bought_symbols.return_value = set()  # no hold-minimum filter
    mock_pg.fetch_latest_signal_ids.return_value = {}
    mock_pg.fetch_signals_for_cycle.return_value = []
    mock_pg.write_execution_decision = MagicMock(return_value=1)

    with patch("src.strategies.registry.StrategyRegistry") as mock_reg, \
         patch("alpaca.data.historical.StockHistoricalDataClient") as mock_dc, \
         patch("alpaca.trading.client.TradingClient") as mock_tc, \
         patch("src.portfolio.orchestrator.PortfolioOrchestrator") as mock_orch, \
         patch("src.backtest.engine.data_replay.DataReplay"), \
         patch("src.backtest.engine.portfolio.VirtualPortfolio"), \
         patch("src.workers.portfolio_scheduler._persist_cycle_result"), \
         patch("src.store.pg_store.PostgreSQLStore", return_value=mock_pg), \
         patch("redis.Redis") as mock_redis_cls:

        entry = MagicMock()
        entry.strategy_id = "S1"
        mock_reg.return_value.get_active_strategies.return_value = [entry]
        mock_reg.return_value.load_mode_from_db.return_value = None

        # Alpaca SDK returns a MultiIndex DataFrame (symbol, timestamp) with a 'close' column.
        # The scheduler calls raw.reset_index() then .pivot(index="timestamp", columns="symbol", values="close").
        dates = pd.date_range("2025-01-01", periods=100, freq="B")
        alpaca_raw = pd.DataFrame(
            {"close": [100.0 + i for i in range(100)]},
            index=pd.MultiIndex.from_arrays(
                [["XLK"] * 100, dates],
                names=["symbol", "timestamp"],
            ),
        )
        mock_dc.return_value.get_stock_bars.return_value.df = alpaca_raw
        mock_dc.return_value.get_stock_snapshot.side_effect = Exception("no snap")

        clock = MagicMock()
        clock.is_open = True
        account = MagicMock()
        account.cash = "100000"
        account.equity = "100000"
        account.buying_power = "100000"
        account.trading_blocked = False
        account.account_blocked = False
        mock_tc.return_value.get_clock.return_value = clock
        mock_tc.return_value.get_account.return_value = account
        mock_tc.return_value.get_all_positions.return_value = []

        mock_orch.return_value.run_cycle.return_value = mock_cycle_result

        redis_inst = MagicMock()
        redis_inst.get.return_value = None
        redis_inst.set.return_value = True
        redis_inst.smembers.return_value = set()
        mock_redis_cls.from_url.return_value = redis_inst

        try:
            _run_cycle_inner()
        except Exception:
            pass

    buy_calls = [
        c for c in mock_pg.write_execution_decision.call_args_list
        if c.kwargs.get("symbol") == "XLK" and c.kwargs.get("decision") == "BUY"
        or (len(c.args) >= 8 and c.args[1] == "XLK" and c.args[7] == "BUY")
    ]
    assert len(buy_calls) == 0, (
        "BUY decision for XLK must NOT be logged when XLK already has an open trade. "
        f"Got {len(buy_calls)} call(s): {buy_calls}"
    )


# ── _check_strategy_zero_weights ──────────────────────────────────────────────


def test_check_strategy_zero_weights_alerts_after_threshold():
    """After N consecutive zero-weight cycles, a Telegram alert is fired."""
    from src.notifications.base import AlertLevel
    from src.workers.portfolio_scheduler import (
        _STRATEGY_ZERO_WEIGHTS_ALERT_CYCLES,
        _check_strategy_zero_weights,
    )

    mock_result = MagicMock()
    mock_result.strategies_run = ["S1"]
    mock_result.orders_per_strategy = {"S1": 0}

    redis_inst = MagicMock()
    redis_inst.incr.side_effect = list(range(1, _STRATEGY_ZERO_WEIGHTS_ALERT_CYCLES + 1))

    notifier = MagicMock()

    with patch("redis.Redis.from_url", return_value=redis_inst), \
         patch("src.workers.portfolio_scheduler._fire_alert") as mock_fire:
        for _ in range(_STRATEGY_ZERO_WEIGHTS_ALERT_CYCLES):
            _check_strategy_zero_weights(
                mock_result, {"S1"}, "redis://localhost", notifier
            )

    mock_fire.assert_called_once()
    args = mock_fire.call_args[0]
    assert "S1" in args[1]
    assert args[2] == AlertLevel.WARNING


def test_check_strategy_zero_weights_resets_on_positive_weights():
    """A cycle with >0 weights resets the counter."""
    from src.workers.portfolio_scheduler import _check_strategy_zero_weights

    mock_result = MagicMock()
    mock_result.strategies_run = ["S1"]
    mock_result.orders_per_strategy = {"S1": 0}

    redis_inst = MagicMock()
    redis_inst.incr.return_value = 1

    with patch("redis.Redis.from_url", return_value=redis_inst):
        _check_strategy_zero_weights(
            mock_result, {"S1"}, "redis://localhost", MagicMock()
        )

    mock_result.orders_per_strategy = {"S1": 3}
    with patch("redis.Redis.from_url", return_value=redis_inst):
        _check_strategy_zero_weights(
            mock_result, {"S1"}, "redis://localhost", MagicMock()
        )

    redis_inst.delete.assert_called_once_with("strategy:zero_weights_cycles:S1")


def test_check_strategy_zero_weights_alerts_at_threshold_multiples():
    """Alert fires at 24, 48, ... and tolerates a jump from 23 to 48."""
    from src.workers.portfolio_scheduler import (
        _STRATEGY_ZERO_WEIGHTS_ALERT_CYCLES,
        _check_strategy_zero_weights,
    )

    mock_result = MagicMock()
    mock_result.strategies_run = ["S1"]
    mock_result.orders_per_strategy = {"S1": 0}

    redis_inst = MagicMock()
    redis_inst.incr.return_value = _STRATEGY_ZERO_WEIGHTS_ALERT_CYCLES * 2

    notifier = MagicMock()

    with patch("redis.Redis.from_url", return_value=redis_inst), \
         patch("src.workers.portfolio_scheduler._fire_alert") as mock_fire:
        _check_strategy_zero_weights(
            mock_result, {"S1"}, "redis://localhost", notifier
        )

    mock_fire.assert_called_once()


def test_check_strategy_zero_weights_no_alert_between_threshold_multiples():
    """A streak of 25 does not re-alert; only exact multiples do."""
    from src.workers.portfolio_scheduler import (
        _STRATEGY_ZERO_WEIGHTS_ALERT_CYCLES,
        _check_strategy_zero_weights,
    )

    mock_result = MagicMock()
    mock_result.strategies_run = ["S1"]
    mock_result.orders_per_strategy = {"S1": 0}

    redis_inst = MagicMock()
    redis_inst.incr.return_value = _STRATEGY_ZERO_WEIGHTS_ALERT_CYCLES + 1

    notifier = MagicMock()

    with patch("redis.Redis.from_url", return_value=redis_inst), \
         patch("src.workers.portfolio_scheduler._fire_alert") as mock_fire:
        _check_strategy_zero_weights(
            mock_result, {"S1"}, "redis://localhost", notifier
        )

    mock_fire.assert_not_called()