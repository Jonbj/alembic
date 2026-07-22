"""Tests for portfolio_scheduler Celery task (T-604)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

from src.backtest.engine.types import OrderSide, OrderType
from src.models.signals import SentimentResult
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


def test_build_strategy_instance_s4_fixed_slot_sizing_enabled_by_default():
    """#81: ON by default per explicit operator decision 2026-07-20 (real
    realized loss DB -$77.88 + an identical live position MSFT exposed to
    the same risk at decision time) — reads real config/trading.yaml."""
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
    assert result._config.fixed_slot_sizing is True


def test_build_strategy_instance_s4_fixed_slot_sizing_can_be_disabled_via_risk_config():
    """#81: rollback path — explicit False in risk config disables the fix."""
    from src.workers.portfolio_scheduler import _build_strategy_instance

    entry = MagicMock()
    entry.strategy_id = "S4"
    bars_df = _make_bars_df(n=5, symbols=["SPY"])
    mock_store = MagicMock()
    mock_store.fetch_signals_for_cycle.return_value = []
    with patch("src.store.pg_store.PostgreSQLStore", return_value=mock_store), \
         patch(
             "src.workers.portfolio_scheduler._load_risk_config",
             return_value={"s4_fixed_slot_sizing_enabled": False},
         ):
        result = _build_strategy_instance(entry, bars_df)

    assert result._config.fixed_slot_sizing is False


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


def test_submit_portfolio_orders_stop_risk_sizing_caps_qty():
    """A wide frozen stop caps notional so per-position loss at stop is bounded."""
    from src.portfolio.stop_policy import StopPolicy
    from src.workers.portfolio_scheduler import _submit_portfolio_orders

    risk_cfg = {
        "stop_loss": 0.02,
        "stop_loss_mode": "fixed",
        "stop_strategy_params": {
            "S1": {"k": 3.5, "floor": 0.06, "cap": 0.12},
            "default": {"k": 3.0, "floor": 0.04, "cap": 0.12},
        },
        "stop_risk_budget_bp_per_pos": 12,
        "stop_gap_buffer_pct": 0.005,
    }
    policy = StopPolicy(risk_cfg, bars_df=None)
    orders = [_make_combined_order("SPY", OrderSide.BUY, qty=10.0)]
    market = _make_market(prices={"SPY": 100.0})

    submitted_calls = []
    def mock_submit(order, notional, client):
        submitted_calls.append((order.symbol, order.quantity, notional))

    submitted = _submit_portfolio_orders(
        orders, MagicMock(), market, _submit_fn=mock_submit,
        risk_cfg=risk_cfg, stop_policy=policy, nav=10000.0,
    )
    assert len(submitted) == 1
    sym, qty, notional = submitted_calls[0]
    # max_notional = 10000 * 0.0012 / (0.02 + 0.005) = 480; max_qty = 480 / 100 = 4.8
    assert qty <= 4.9
    assert notional <= 490.0


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


# ── B33-follow-up: pinned S4 signal provenance (no "latest" re-fetch race) ───
#
# 2026-07-15 MSFT incident: the ranker used signal_id=3770 (score +0.165) to
# compute the BUY weight; ~34s later the decision-logging block re-queried
# "latest signal" and picked up signal_id=3773 (score -0.110, arrived after
# ranking) instead. The decision row and the idempotency fired-set both ended
# up pointing at the wrong signal. The fix: use CycleResult.symbol_signal_
# provenance (pinned by the orchestrator at weight-computation time) instead
# of re-fetching. These tests mock fetch_latest_signal_ids/fetch_signals_for_
# cycle to return the WRONG (later) signal, and assert the decision is logged
# with the PINNED (correct, earlier) one.


def test_s4_decision_uses_pinned_provenance_not_stale_refetch():
    """write_execution_decision must use the pinned signal_id/score from
    CycleResult.symbol_signal_provenance, not a fresh fetch_latest_signal_ids/
    fetch_signals_for_cycle call that could return a newer, different signal.
    """
    import pandas as pd
    from unittest.mock import MagicMock, patch
    from src.workers.portfolio_scheduler import _run_cycle_inner
    from src.portfolio.orchestrator import CycleResult

    bars_df = pd.DataFrame({"MSFT": [100.0 + i for i in range(100)]})
    bars_df.index = pd.date_range("2025-01-01", periods=100, freq="B")

    # Pinned at ranking time: the correct, bullish signal that drove the BUY.
    mock_cycle_result = CycleResult(
        strategies_run=["S4"],
        orders_per_strategy={"S4": 1},
        orders_before_constraints=1,
        orders_after_constraints=1,
        constraints_fired=[],
        final_orders=[_make_combined_order("MSFT", OrderSide.BUY)],
        symbol_strategies={"MSFT": ["S4"]},
        symbol_signal_provenance={
            "MSFT": {
                "signal_id": 3770, "score": 0.165,
                "reasoning": "bull case", "model_id": "ensemble:glm-5.2:cloud",
            },
        },
    )

    mock_pg = MagicMock()
    mock_pg.fetch_trades.return_value = []
    mock_pg.fetch_recently_bought_symbols.return_value = set()
    # A stale re-fetch would return the WRONG, later-arriving signal (3773,
    # -0.110) — if the fix works, these values must never reach the decision.
    mock_pg.fetch_latest_signal_ids.return_value = {"MSFT": 3773}
    mock_pg.fetch_signals_for_cycle.return_value = [
        SentimentResult(
            symbol="MSFT", score=-0.110, confidence=0.9,
            reasoning="bear case (arrived after ranking)", model_id="gpt-oss:20b-cloud",
            signal_id=3773,
        )
    ]
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
        entry.strategy_id = "S4"
        mock_reg.return_value.get_active_strategies.return_value = [entry]
        mock_reg.return_value.load_mode_from_db.return_value = None

        dates = pd.date_range("2025-01-01", periods=100, freq="B")
        alpaca_raw = pd.DataFrame(
            {"close": [100.0 + i for i in range(100)]},
            index=pd.MultiIndex.from_arrays(
                [["MSFT"] * 100, dates],
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

    msft_calls = [
        c for c in mock_pg.write_execution_decision.call_args_list
        if c.kwargs.get("symbol") == "MSFT"
    ]
    assert len(msft_calls) == 1, f"Expected exactly one MSFT decision, got {len(msft_calls)}"
    call_kwargs = msft_calls[0].kwargs
    assert call_kwargs["signal_id"] == 3770, (
        "Decision must use the PINNED signal_id (3770, ranked) not the stale "
        f"re-fetch (3773). Got {call_kwargs['signal_id']}."
    )
    assert call_kwargs["signal_score"] == 0.165, (
        "Decision must use the PINNED score (+0.165) not the stale re-fetch "
        f"(-0.110). Got {call_kwargs['signal_score']}."
    )


# ── #61: anti-whipsaw damping integration (full cycle) ────────────────────────


def _whipsaw_cycle_result():
    from src.portfolio.orchestrator import CycleResult
    from src.portfolio.types import CombinedOrder

    zero_weight_sell = CombinedOrder(
        order_id="oid-NVDA",
        timestamp=datetime(2026, 7, 16, 14, 0, tzinfo=timezone.utc),
        symbol="NVDA",
        side=OrderSide.SELL,
        quantity=5.0,
        order_type=OrderType.MARKET,
        strategy_id=None,
        allocation_weight=0.0,
    )
    return CycleResult(
        strategies_run=["S4"],
        orders_per_strategy={"S4": 1},
        orders_before_constraints=1,
        orders_after_constraints=1,
        constraints_fired=[],
        final_orders=[zero_weight_sell],
        symbol_strategies={},  # NVDA dropped out of ranking this cycle — empty strats
        symbol_signal_provenance={},
    )


def _run_whipsaw_cycle(risk_cfg_overrides: dict):
    import pandas as pd
    from unittest.mock import MagicMock, patch
    from src.workers.portfolio_scheduler import _run_cycle_inner

    mock_pg = MagicMock()
    mock_pg.fetch_trades.return_value = []
    mock_pg.fetch_recently_bought_symbols.return_value = set()
    mock_pg.fetch_latest_signal_ids.return_value = {}
    # Fresh (age < max_signal_age_hours=4h), weak/neutral score -> "whipsaw".
    fresh_gen_at = datetime.now(timezone.utc) - timedelta(hours=1)
    mock_pg.fetch_signals_for_cycle.return_value = [
        SentimentResult(
            symbol="NVDA", score=-0.02, confidence=0.5,
            reasoning="mixed signals", model_id="ensemble:glm-5.2:cloud",
            generated_at=fresh_gen_at,
        )
    ]
    mock_pg.write_execution_decision = MagicMock(return_value=1)

    with patch("src.strategies.registry.StrategyRegistry") as mock_reg, \
         patch("alpaca.data.historical.StockHistoricalDataClient") as mock_dc, \
         patch("alpaca.trading.client.TradingClient") as mock_tc, \
         patch("src.portfolio.orchestrator.PortfolioOrchestrator") as mock_orch, \
         patch("src.backtest.engine.data_replay.DataReplay"), \
         patch("src.backtest.engine.portfolio.VirtualPortfolio"), \
         patch("src.workers.portfolio_scheduler._persist_cycle_result"), \
         patch("src.workers.portfolio_scheduler._load_risk_config") as mock_risk_cfg, \
         patch("src.store.pg_store.PostgreSQLStore", return_value=mock_pg), \
         patch("redis.Redis") as mock_redis_cls:

        entry = MagicMock()
        entry.strategy_id = "S4"
        mock_reg.return_value.get_active_strategies.return_value = [entry]
        mock_reg.return_value.load_mode_from_db.return_value = None

        base_risk_cfg = {
            "max_portfolio_exposure": 0.50, "max_single_asset_pct": 0.10,
            "max_sector_exposure": 0.0, "stop_loss": 0.0, "portfolio_drawdown": 0.05,
            "stop_loss_mode": "fixed", "stop_strategy_params": {},
            "stop_sigma_lookback_fast": 20, "stop_sigma_lookback_slow": 63,
            "stop_sigma_ewma_floor_ratio": 0.8, "stop_risk_budget_bp_per_pos": 12,
            "stop_risk_budget_bp_aggregate": 100, "stop_gap_buffer_pct": 0.005,
            "stop_shadow_enabled": False,
            "broker_disaster_stop": {"multiplier": 1.5, "sigma_multiple": 5.0, "floor_pct": 0.12, "cap_pct": 0.20},
            "s4_anti_whipsaw_damping_enabled": False, "s4_anti_whipsaw_confirm_cycles": 2,
        }
        mock_risk_cfg.return_value = {**base_risk_cfg, **risk_cfg_overrides}

        dates = pd.date_range("2025-01-01", periods=100, freq="B")
        alpaca_raw = pd.DataFrame(
            {"close": [400.0 + i for i in range(100)]},
            index=pd.MultiIndex.from_arrays(
                [["NVDA"] * 100, dates],
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

        mock_orch.return_value.run_cycle.return_value = _whipsaw_cycle_result()

        redis_inst = MagicMock()
        redis_inst.get.return_value = None  # no prior whipsaw streak
        redis_inst.set.return_value = True
        redis_inst.smembers.return_value = set()
        # Pre-existing exit-persistence hysteresis (_apply_exit_hysteresis,
        # execution.exit_persistence_cycles) runs BEFORE the whipsaw check and
        # would otherwise suppress this synthetic order on its own (a bare
        # MagicMock().incr() coerces to 1 via int(), which is < the default
        # persistence_cycles=2). Simulate a position that already cleared that
        # separate gate, so this test exercises anti-whipsaw damping in isolation.
        redis_inst.incr.return_value = 99
        mock_redis_cls.from_url.return_value = redis_inst

        try:
            _run_cycle_inner()
        except Exception:
            import traceback
            traceback.print_exc()

    return mock_pg, redis_inst


def test_whipsaw_shadow_mode_sell_proceeds_with_annotated_reason():
    """Flag off (default): the SELL still happens, but the reason notes what
    damping WOULD have done — shadow measurement, no behavior change."""
    mock_pg, redis_inst = _run_whipsaw_cycle({"s4_anti_whipsaw_damping_enabled": False})

    nvda_calls = [
        c for c in mock_pg.write_execution_decision.call_args_list
        if c.kwargs.get("symbol") == "NVDA"
    ]
    assert len(nvda_calls) == 1, f"Expected exactly one NVDA decision (shadow doesn't block), got {len(nvda_calls)}"
    assert nvda_calls[0].kwargs["exit_mechanism"] == "whipsaw"
    assert "anti_whipsaw_shadow" in nvda_calls[0].kwargs["reason"]
    assert "would_suppress=True" in nvda_calls[0].kwargs["reason"]
    # Streak still tracked even in shadow mode, so a later flip doesn't start cold.
    assert call("s4:whipsaw_streak:NVDA", 1800, "1") in redis_inst.setex.call_args_list


def test_whipsaw_enabled_first_occurrence_suppresses_no_decision_logged():
    """Flag on, first whipsaw for this symbol: no decision row this cycle — held."""
    mock_pg, redis_inst = _run_whipsaw_cycle({"s4_anti_whipsaw_damping_enabled": True})

    nvda_calls = [
        c for c in mock_pg.write_execution_decision.call_args_list
        if c.kwargs.get("symbol") == "NVDA"
    ]
    assert nvda_calls == [], (
        f"First whipsaw occurrence with damping ON must be suppressed (no decision "
        f"logged this cycle), got {len(nvda_calls)} calls"
    )
    assert call("s4:whipsaw_streak:NVDA", 1800, "1") in redis_inst.setex.call_args_list


# ── #72: origin-aware exit tag, full-cycle wiring ────────────────────────────


def test_s1_origin_weight_drop_tagged_correctly_not_no_signal():
    """#72: a weight-0 SELL on a position opened by S1 must get [s1_weight_drop],
    not the S4-specific classifier's misleading [no_signal] tag. Reproduces the
    2026-07-17 SBUX incident (trades 348/360)."""
    import pandas as pd
    from src.portfolio.orchestrator import CycleResult
    from src.portfolio.types import CombinedOrder
    from src.workers.portfolio_scheduler import _run_cycle_inner

    zero_weight_sell = CombinedOrder(
        order_id="oid-SBUX",
        timestamp=datetime(2026, 7, 17, 14, 0, tzinfo=timezone.utc),
        symbol="SBUX",
        side=OrderSide.SELL,
        quantity=5.0,
        order_type=OrderType.MARKET,
        strategy_id=None,
        allocation_weight=0.0,
    )
    cycle_result = CycleResult(
        strategies_run=["S1"],
        orders_per_strategy={"S1": 0},
        orders_before_constraints=1,
        orders_after_constraints=1,
        constraints_fired=[],
        final_orders=[zero_weight_sell],
        symbol_strategies={},  # SBUX dropped from S1's own target this cycle
        symbol_signal_provenance={},
    )

    mock_pg = MagicMock()
    # SBUX has an open trade whose origin (stop_strategy) is S1.
    mock_pg.fetch_trades.return_value = [{"symbol": "SBUX", "stop_strategy": "S1"}]
    mock_pg.fetch_recently_bought_symbols.return_value = set()
    mock_pg.fetch_latest_signal_ids.return_value = {}
    mock_pg.fetch_signals_for_cycle.return_value = []  # SBUX never had an S4 signal
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

        dates = pd.date_range("2025-01-01", periods=100, freq="B")
        alpaca_raw = pd.DataFrame(
            {"close": [90.0 + i * 0.1 for i in range(100)]},
            index=pd.MultiIndex.from_arrays(
                [["SBUX"] * 100, dates],
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

        mock_orch.return_value.run_cycle.return_value = cycle_result

        redis_inst = MagicMock()
        redis_inst.get.return_value = None
        redis_inst.set.return_value = True
        redis_inst.smembers.return_value = set()
        # Pre-existing exit-persistence hysteresis (_apply_exit_hysteresis) runs
        # before decision logging — a bare MagicMock().incr() coerces to 1 via
        # int(), which is < the default persistence_cycles=2 and would suppress
        # this synthetic order before it's ever classified. Simulate a position
        # that already cleared that separate gate (same fix as the #61 tests).
        redis_inst.incr.return_value = 99
        mock_redis_cls.from_url.return_value = redis_inst

        try:
            _run_cycle_inner()
        except Exception:
            pass

    sbux_calls = [
        c for c in mock_pg.write_execution_decision.call_args_list
        if c.kwargs.get("symbol") == "SBUX"
    ]
    assert len(sbux_calls) == 1, f"Expected exactly one SBUX decision, got {len(sbux_calls)}"
    assert sbux_calls[0].kwargs["exit_mechanism"] == "s1_weight_drop"
    assert "[s1_weight_drop]" in sbux_calls[0].kwargs["reason"]
    assert "no_signal" not in sbux_calls[0].kwargs["reason"]


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


class TestSectorMapLoader:
    def test_load_sector_map_inverts_yaml(self, tmp_path, monkeypatch):
        cfg = tmp_path / "trading.yaml"
        cfg.write_text(
            "sectors:\n  semis: [NVDA, AMD]\n  tech: [AAPL]\n"
        )
        from src.workers import portfolio_scheduler as ps
        monkeypatch.setattr(ps, "_TRADING_YAML", cfg)
        result = ps._load_sector_map()
        assert result == {"NVDA": "semis", "AMD": "semis", "AAPL": "tech"}

    def test_load_sector_map_absent_returns_none(self, tmp_path, monkeypatch):
        cfg = tmp_path / "trading.yaml"
        cfg.write_text("risk: {}\n")
        from src.workers import portfolio_scheduler as ps
        monkeypatch.setattr(ps, "_TRADING_YAML", cfg)
        assert ps._load_sector_map() is None


# ── B33: per-order trade-write isolation ──────────────────────────────────────


def test_persist_trade_fills_isolates_per_order_sell_failure():
    """B33: a single failing SELL must NOT abort the remaining orders' DB writes.

    Root cause (2026-07-15, 5 SELLs lost): the trade-write tail wrapped every
    order in ONE try/except, and record_trade_exit re-raises DB errors
    (pg_store.py: `except Exception: conn.rollback(); raise`). So the first
    SELL that threw broke the loop, skipping record_trade_exit AND the
    order_id back-fill for every subsequent order — leaving 5 Alpaca fills
    unrecorded (DB↔Alpaca divergence). Fix: per-order try/except + rollback so
    the connection is reusable for the next order.
    """
    from src.workers.portfolio_scheduler import _persist_trade_fills

    pg = MagicMock()
    # First SELL raises (dead pooled connection), the next two succeed.
    pg.record_trade_exit.side_effect = [
        RuntimeError("server closed the connection unexpectedly"),
        324,  # MSFT
        322,  # NFLX
    ]
    pg.update_decision_order_id.return_value = None

    submitted = [
        {"symbol": "DIS", "side": "sell", "order_id": "ord-dis",
         "notional": 0.0, "reason": "portfolio_sell", "allocation_weight": 0.0},
        {"symbol": "MSFT", "side": "sell", "order_id": "ord-msft",
         "notional": 0.0, "reason": "portfolio_sell", "allocation_weight": 0.0},
        {"symbol": "NFLX", "side": "sell", "order_id": "ord-nflx",
         "notional": 0.0, "reason": "portfolio_sell", "allocation_weight": 0.0},
    ]
    open_trades = [
        {"symbol": "DIS", "id": 323},
        {"symbol": "MSFT", "id": 324},
        {"symbol": "NFLX", "id": 322},
    ]
    symbol_decisions = {
        "DIS": {"decision_id": "dec-dis"},
        "MSFT": {"decision_id": "dec-msft"},
        "NFLX": {"decision_id": "dec-nflx"},
    }
    market = MagicMock()
    market.prices = {"DIS": 100.0, "MSFT": 400.0, "NFLX": 600.0}

    with patch("src.store.pg_store.PostgreSQLStore", return_value=pg), \
         patch("src.workers.portfolio_scheduler._portfolio_postmortem"):
        failures = _persist_trade_fills(
            submitted,
            open_trades=open_trades,
            symbol_decisions=symbol_decisions,
            written_buy_order_ids=set(),
            stop_policy=None,
            market=market,
            alpaca_entry_prices={},
            s4_signals={},
            regime_mult=0.7,
            tick_time=datetime(2026, 7, 15, 14, 22, tzinfo=timezone.utc),
        )

    # DIS threw → exactly 1 failure reported.
    assert failures == 1, f"expected 1 failure, got {failures}"
    # record_trade_exit MUST have been called for ALL three orders (loop continued
    # past the DIS failure). This is the regression — pre-fix it stopped at DIS.
    called_syms = [c.kwargs["symbol"] for c in pg.record_trade_exit.call_args_list]
    assert called_syms == ["DIS", "MSFT", "NFLX"], (
        f"record_trade_exit must be called for every order even when one fails; "
        f"got {called_syms}"
    )
    # The order_id back-fill must have run for the orders AFTER the failure.
    backfilled = {c.args[0] for c in pg.update_decision_order_id.call_args_list}
    assert "dec-msft" in backfilled and "dec-nflx" in backfilled, (
        f"order_id back-fill must run for orders after the failure; got {backfilled}"
    )
    # The FAILED order (DIS) must NOT have its decision back-filled — its trade
    # row was never written, so linking the order_id would be misleading. Pre-I-1
    # the postmortem/back-fill ran inside the same try as the trade write; now a
    # trade-write failure `continue`s before reaching the back-fill.
    assert "dec-dis" not in backfilled, (
        f"back-fill must not run for the order whose trade write failed; got {backfilled}"
    )
    # Connection rolled back after the failure so the next order could reuse it
    # (otherwise psycopg2 'current transaction is aborted' cascades to all).
    pg.rollback.assert_called(), "rollback must be called after a per-order failure"
    # Connection returned to the pool on every path.
    pg.close.assert_called_once()


def test_persist_trade_fills_buy_failure_does_not_block_subsequent_sell():
    """B33: a failing BUY (legacy batch path) must not block a following SELL's write."""
    from src.workers.portfolio_scheduler import _persist_trade_fills

    pg = MagicMock()
    pg.open_trade.side_effect = [RuntimeError("pool exhausted mid-INSERT")]
    pg.record_trade_exit.return_value = 322  # NFLX SELL succeeds
    pg.update_decision_order_id.return_value = None

    submitted = [
        {"symbol": "AAPL", "side": "buy", "order_id": "ord-aapl",
         "notional": 1000.0, "qty": 5.0, "reason": "portfolio_buy"},
        {"symbol": "NFLX", "side": "sell", "order_id": "ord-nflx",
         "notional": 0.0, "reason": "portfolio_sell", "allocation_weight": 0.0},
    ]
    market = MagicMock()
    market.prices = {"AAPL": 200.0, "NFLX": 600.0}

    with patch("src.store.pg_store.PostgreSQLStore", return_value=pg), \
         patch("src.workers.portfolio_scheduler._portfolio_postmortem"):
        failures = _persist_trade_fills(
            submitted,
            open_trades=[{"symbol": "NFLX", "id": 322}],
            symbol_decisions={"AAPL": {"decision_id": "dec-aapl"},
                              "NFLX": {"decision_id": "dec-nflx"}},
            written_buy_order_ids=set(),
            stop_policy=None,
            market=market,
            alpaca_entry_prices={},
            s4_signals={},
            regime_mult=0.7,
            tick_time=datetime(2026, 7, 15, 14, 22, tzinfo=timezone.utc),
        )

    assert failures == 1, f"expected 1 failure (the BUY), got {failures}"
    # The SELL after the failed BUY must still be recorded.
    sell_syms = [c.kwargs["symbol"] for c in pg.record_trade_exit.call_args_list]
    assert sell_syms == ["NFLX"], (
        f"SELL after a failed BUY must still be written; got {sell_syms}"
    )
    pg.rollback.assert_called()
    pg.close.assert_called_once()


def test_persist_trade_fills_legacy_buy_path_uses_sym_strats_for_origin_strategy():
    """Reproduces the 2026-07-17 DB incident in the legacy batch write path:
    S4 contributed the weight this cycle (sym_strats) but signal_id is absent
    from the decision dict — frozen_stop.strategy must still resolve to S4,
    not fall back to the signal_id heuristic's "S1" guess."""
    from src.portfolio.stop_policy import StopPolicy
    from src.workers.portfolio_scheduler import _persist_trade_fills

    pg = MagicMock()
    pg.open_trade.return_value = None

    submitted = [
        {"symbol": "DB", "side": "buy", "order_id": "ord-db",
         "notional": 6181.23, "qty": 175.7, "reason": "portfolio_buy"},
    ]
    market = MagicMock()
    market.prices = {"DB": 35.18}
    stop_policy = StopPolicy({"stop_loss_mode": "fixed", "stop_loss": 0.0})

    with patch("src.store.pg_store.PostgreSQLStore", return_value=pg), \
         patch("src.workers.portfolio_scheduler._portfolio_postmortem"):
        _persist_trade_fills(
            submitted,
            open_trades=[],
            symbol_decisions={"DB": {"decision_id": "dec-db"}},  # no signal_id present
            written_buy_order_ids=set(),
            stop_policy=stop_policy,
            market=market,
            alpaca_entry_prices={},
            s4_signals={},
            regime_mult=1.0,
            tick_time=datetime(2026, 7, 17, 18, 52, tzinfo=timezone.utc),
            sym_strats={"DB": ["S4"]},
        )

    frozen_stop = pg.open_trade.call_args.kwargs["frozen_stop"]
    assert frozen_stop.strategy == "S4"


# ── #62/#63: broker-side protective stop sync for fractional positions ──────


def _fake_position(symbol: str, qty: str, avg_entry_price: str):
    from types import SimpleNamespace
    return SimpleNamespace(symbol=symbol, qty=qty, avg_entry_price=avg_entry_price)


def _fake_order(symbol: str, order_id: str, qty: str, stop_price: str, order_type):
    from types import SimpleNamespace
    return SimpleNamespace(symbol=symbol, id=order_id, qty=qty, stop_price=stop_price, type=order_type)


class TestSyncFractionalProtectiveStops:
    def test_fetches_positions_and_open_sell_orders(self):
        from src.workers.portfolio_scheduler import _sync_fractional_protective_stops
        from src.portfolio.stop_policy import StopPolicy

        tc = MagicMock()
        tc.get_all_positions.return_value = []
        tc.get_orders.return_value = []
        stop_policy = StopPolicy({"stop_loss_mode": "fixed", "stop_loss": 0.0})

        _sync_fractional_protective_stops(tc, stop_policy, datetime(2026, 7, 16, tzinfo=timezone.utc))

        tc.get_all_positions.assert_called_once()
        tc.get_orders.assert_called_once()

    def test_creates_stop_for_fractional_position_with_no_existing_stop(self):
        from alpaca.trading.enums import OrderType
        from src.workers.portfolio_scheduler import _sync_fractional_protective_stops
        from src.portfolio.stop_policy import StopPolicy

        tc = MagicMock()
        tc.get_all_positions.return_value = [_fake_position("AAPL", "2.4578", "100.0")]
        tc.get_orders.return_value = []
        stop_policy = StopPolicy({"stop_loss_mode": "fixed", "stop_loss": 0.0})

        summary = _sync_fractional_protective_stops(
            tc, stop_policy, datetime(2026, 7, 16, tzinfo=timezone.utc)
        )

        tc.submit_order.assert_called_once()
        assert summary["created"] == 1

    def test_ignores_non_stop_orders_when_checking_existing_protection(self):
        from alpaca.trading.enums import OrderType
        from src.workers.portfolio_scheduler import _sync_fractional_protective_stops
        from src.portfolio.stop_policy import StopPolicy

        tc = MagicMock()
        tc.get_all_positions.return_value = [_fake_position("AAPL", "2.4578", "100.0")]
        # A resting limit sell (take-profit) for the same symbol must NOT count as
        # existing protection — only a STOP-type order does.
        tc.get_orders.return_value = [
            _fake_order("AAPL", "limit-1", "2", "150.0", OrderType.LIMIT),
        ]
        stop_policy = StopPolicy({"stop_loss_mode": "fixed", "stop_loss": 0.0})

        summary = _sync_fractional_protective_stops(
            tc, stop_policy, datetime(2026, 7, 16, tzinfo=timezone.utc)
        )

        tc.submit_order.assert_called_once()
        assert summary["created"] == 1

    def test_noop_when_matching_stop_order_already_exists(self):
        from alpaca.trading.enums import OrderType
        from src.workers.portfolio_scheduler import _sync_fractional_protective_stops
        from src.portfolio.stop_policy import StopPolicy

        tc = MagicMock()
        tc.get_all_positions.return_value = [_fake_position("AAPL", "2.4578", "100.0")]
        # fixed mode, stop_loss=0.0 -> d_init=0 -> d_hard = floor 0.12 -> stop_price = 88.0
        tc.get_orders.return_value = [
            _fake_order("AAPL", "stop-1", "2", "88.0", OrderType.STOP),
        ]
        stop_policy = StopPolicy({"stop_loss_mode": "fixed", "stop_loss": 0.0})

        summary = _sync_fractional_protective_stops(
            tc, stop_policy, datetime(2026, 7, 16, tzinfo=timezone.utc)
        )

        tc.submit_order.assert_not_called()
        tc.cancel_order_by_id.assert_not_called()
        assert summary["noop"] == 1

    def test_cancels_orphan_stop_for_fully_closed_position(self):
        """#62 review finding (GLM): a symbol sold to zero drops out of
        get_all_positions() next cycle — its GTC stop must still be cancelled,
        not left dangling on the broker indefinitely."""
        from alpaca.trading.enums import OrderType
        from src.workers.portfolio_scheduler import _sync_fractional_protective_stops
        from src.portfolio.stop_policy import StopPolicy

        tc = MagicMock()
        tc.get_all_positions.return_value = []  # AAPL fully closed this cycle
        tc.get_orders.return_value = [
            _fake_order("AAPL", "stop-orphan", "2", "88.0", OrderType.STOP),
        ]
        stop_policy = StopPolicy({"stop_loss_mode": "fixed", "stop_loss": 0.0})

        summary = _sync_fractional_protective_stops(
            tc, stop_policy, datetime(2026, 7, 16, tzinfo=timezone.utc)
        )

        tc.cancel_order_by_id.assert_called_once_with("stop-orphan")
        tc.submit_order.assert_not_called()
        assert summary["cancelled_orphans"] == 1

    def test_returns_skip_marker_when_positions_fetch_fails(self):
        from src.workers.portfolio_scheduler import _sync_fractional_protective_stops
        from src.portfolio.stop_policy import StopPolicy

        tc = MagicMock()
        tc.get_all_positions.side_effect = RuntimeError("api down")
        stop_policy = StopPolicy({"stop_loss_mode": "fixed", "stop_loss": 0.0})

        summary = _sync_fractional_protective_stops(
            tc, stop_policy, datetime(2026, 7, 16, tzinfo=timezone.utc)
        )

        assert summary == {"skipped": "positions_fetch_failed"}
        tc.submit_order.assert_not_called()

    def test_returns_skip_marker_when_orders_fetch_fails(self):
        from src.workers.portfolio_scheduler import _sync_fractional_protective_stops
        from src.portfolio.stop_policy import StopPolicy

        tc = MagicMock()
        tc.get_all_positions.return_value = [_fake_position("AAPL", "2.4578", "100.0")]
        tc.get_orders.side_effect = RuntimeError("api down")
        stop_policy = StopPolicy({"stop_loss_mode": "fixed", "stop_loss": 0.0})

        summary = _sync_fractional_protective_stops(
            tc, stop_policy, datetime(2026, 7, 16, tzinfo=timezone.utc)
        )

        assert summary == {"skipped": "orders_fetch_failed"}
        tc.submit_order.assert_not_called()


# ── #71: S1 re-entry cooldown after a self-excluded weight drop ─────────────


class TestS1ReentryCooldownRedisHelpers:
    def test_get_returns_empty_set_when_no_keys(self):
        from src.workers.portfolio_scheduler import _get_s1_reentry_cooldown_symbols

        with patch("redis.Redis") as mock_cls:
            inst = MagicMock()
            inst.keys.return_value = []
            mock_cls.from_url.return_value = inst

            symbols = _get_s1_reentry_cooldown_symbols("redis://localhost:6379/0")

        assert symbols == set()

    def test_get_returns_symbols_from_keys(self):
        from src.workers.portfolio_scheduler import _get_s1_reentry_cooldown_symbols

        with patch("redis.Redis") as mock_cls:
            inst = MagicMock()
            inst.keys.return_value = ["s1_reentry_cooldown:SBUX", "s1_reentry_cooldown:GE"]
            mock_cls.from_url.return_value = inst

            symbols = _get_s1_reentry_cooldown_symbols("redis://localhost:6379/0")

        assert symbols == {"SBUX", "GE"}

    def test_get_returns_empty_set_on_redis_error(self):
        from src.workers.portfolio_scheduler import _get_s1_reentry_cooldown_symbols

        with patch("redis.Redis") as mock_cls:
            mock_cls.from_url.side_effect = RuntimeError("redis down")

            symbols = _get_s1_reentry_cooldown_symbols("redis://localhost:6379/0")

        assert symbols == set()

    def test_mark_sets_key_with_minutes_converted_to_ttl_seconds(self):
        from src.workers.portfolio_scheduler import _mark_s1_reentry_cooldown

        with patch("redis.Redis") as mock_cls:
            inst = MagicMock()
            mock_cls.from_url.return_value = inst

            _mark_s1_reentry_cooldown("redis://localhost:6379/0", "SBUX", minutes=30)

        inst.setex.assert_called_once_with("s1_reentry_cooldown:SBUX", 1800, "1")

    def test_mark_noop_when_minutes_not_positive(self):
        from src.workers.portfolio_scheduler import _mark_s1_reentry_cooldown

        with patch("redis.Redis") as mock_cls:
            inst = MagicMock()
            mock_cls.from_url.return_value = inst

            _mark_s1_reentry_cooldown("redis://localhost:6379/0", "SBUX", minutes=0)

        inst.setex.assert_not_called()


# ── #61: Redis-backed consecutive-whipsaw streak tracking ───────────────────


class TestWhipsawStreakRedisHelpers:
    def test_get_returns_zero_when_key_absent(self):
        from src.workers.portfolio_scheduler import _get_whipsaw_streak

        with patch("redis.Redis") as mock_cls:
            inst = MagicMock()
            inst.get.return_value = None
            mock_cls.from_url.return_value = inst

            streak = _get_whipsaw_streak("redis://localhost:6379/0", "NVDA")

        assert streak == 0

    def test_get_returns_persisted_value(self):
        from src.workers.portfolio_scheduler import _get_whipsaw_streak

        with patch("redis.Redis") as mock_cls:
            inst = MagicMock()
            inst.get.return_value = "1"
            mock_cls.from_url.return_value = inst

            streak = _get_whipsaw_streak("redis://localhost:6379/0", "NVDA")

        assert streak == 1

    def test_get_returns_zero_on_redis_error(self):
        from src.workers.portfolio_scheduler import _get_whipsaw_streak

        with patch("redis.Redis") as mock_cls:
            mock_cls.from_url.side_effect = RuntimeError("redis down")

            streak = _get_whipsaw_streak("redis://localhost:6379/0", "NVDA")

        assert streak == 0

    def test_set_positive_streak_calls_setex_with_ttl(self):
        from src.workers.portfolio_scheduler import _set_whipsaw_streak

        with patch("redis.Redis") as mock_cls:
            inst = MagicMock()
            mock_cls.from_url.return_value = inst

            _set_whipsaw_streak("redis://localhost:6379/0", "NVDA", 1)

        inst.setex.assert_called_once()
        key, ttl, value = inst.setex.call_args[0]
        assert key == "s4:whipsaw_streak:NVDA"
        assert ttl <= 1800
        assert value == "1"
        inst.delete.assert_not_called()

    def test_set_zero_streak_deletes_key(self):
        from src.workers.portfolio_scheduler import _set_whipsaw_streak

        with patch("redis.Redis") as mock_cls:
            inst = MagicMock()
            mock_cls.from_url.return_value = inst

            _set_whipsaw_streak("redis://localhost:6379/0", "NVDA", 0)

        inst.delete.assert_called_once_with("s4:whipsaw_streak:NVDA")
        inst.setex.assert_not_called()


class TestApplyWhipsawDampingFilter:
    """#61: _apply_whipsaw_damping_filter excludes only SELLs for suppressed symbols."""

    def test_no_suppressed_symbols_returns_orders_unchanged(self):
        from src.workers.portfolio_scheduler import _apply_whipsaw_damping_filter

        orders = [_make_combined_order("NVDA", side=OrderSide.SELL, qty=5.0)]

        result = _apply_whipsaw_damping_filter(orders, set())

        assert result == orders

    def test_filters_out_sell_for_suppressed_symbol(self):
        from src.workers.portfolio_scheduler import _apply_whipsaw_damping_filter

        sell = _make_combined_order("NVDA", side=OrderSide.SELL, qty=5.0)
        keep = _make_combined_order("IBM", side=OrderSide.SELL, qty=3.0)

        result = _apply_whipsaw_damping_filter([sell, keep], {"NVDA"})

        assert result == [keep]

    def test_never_filters_buy_orders(self):
        """A symbol landing in suppressed_syms only ever describes a held SELL — BUYs pass through."""
        from src.workers.portfolio_scheduler import _apply_whipsaw_damping_filter

        buy = _make_combined_order("NVDA", side=OrderSide.BUY, qty=5.0)

        result = _apply_whipsaw_damping_filter([buy], {"NVDA"})

        assert result == [buy]


# ── #62 regression fix: cancel protective stops before scheduler SELLs ───────
# A live GTC protective stop reserves the whole-share qty, so a full-qty market
# SELL is rejected by Alpaca with 40310000 (verified live 2026-07-16 18:22 UTC:
# SOXX/INTC reversal force-sells failed while their stops were open).


def _make_open_stop_order(symbol: str, order_id: str = "stop-1"):
    from alpaca.trading.enums import OrderType as _AOT

    o = MagicMock()
    o.id = order_id
    o.symbol = symbol
    o.type = _AOT.STOP
    return o


def test_submit_portfolio_orders_cancels_protective_stop_before_sell():
    """SELL path frees reserved shares: cancel the symbol's stop BEFORE submitting."""
    from src.workers.portfolio_scheduler import _submit_portfolio_orders

    orders = [_make_combined_order("SPY", OrderSide.SELL, qty=10.0)]
    trading_client = MagicMock()
    trading_client.get_orders.return_value = [_make_open_stop_order("SPY")]
    market = _make_market()

    events = []
    trading_client.cancel_order_by_id.side_effect = lambda oid: events.append(("cancel", oid))

    submitted = _submit_portfolio_orders(
        orders, trading_client, market,
        _submit_fn=lambda o, q, c: events.append(("submit", o.symbol)),
    )

    assert len(submitted) == 1
    assert events == [("cancel", "stop-1"), ("submit", "SPY")]


def test_submit_portfolio_orders_buy_does_not_touch_stop_orders():
    """BUY path never lists/cancels stop orders."""
    from src.workers.portfolio_scheduler import _submit_portfolio_orders

    orders = [_make_combined_order("SPY", OrderSide.BUY, qty=10.0)]
    trading_client = MagicMock()
    market = _make_market(prices={"SPY": 450.0})

    _submit_portfolio_orders(orders, trading_client, market, _submit_fn=lambda o, n, c: None)

    trading_client.get_orders.assert_not_called()
    trading_client.cancel_order_by_id.assert_not_called()


def test_submit_portfolio_orders_sell_proceeds_when_cancel_fails():
    """Fail-open: a broker error while freeing the stop must not block the SELL."""
    from src.workers.portfolio_scheduler import _submit_portfolio_orders

    orders = [_make_combined_order("SPY", OrderSide.SELL, qty=10.0)]
    trading_client = MagicMock()
    trading_client.get_orders.side_effect = RuntimeError("api down")
    market = _make_market()

    submitted = _submit_portfolio_orders(
        orders, trading_client, market, _submit_fn=lambda o, q, c: None,
    )

    assert len(submitted) == 1


# ── _submit_reversal_force_sells (extracted for testability after the 07-16
#    live failure: reversal force-sells silently blocked by protective stops) ──


def _make_alpaca_position(symbol: str, qty: float):
    p = MagicMock()
    p.symbol = symbol
    p.qty = str(qty)
    return p


def test_reversal_force_sell_cancels_protective_stop_then_submits():
    """The force-sell frees the symbol's reserved shares before the market SELL."""
    from src.workers.portfolio_scheduler import _submit_reversal_force_sells

    trading_client = MagicMock()
    trading_client.get_orders.return_value = [_make_open_stop_order("SOXX", "stop-7")]
    events = []
    trading_client.cancel_order_by_id.side_effect = lambda oid: events.append(("cancel", oid))
    resp = MagicMock()
    resp.id = "ord-9"
    trading_client.submit_order.side_effect = lambda req: events.append(("submit", req.symbol)) or resp

    submitted_orders = []
    with patch("src.store.pg_store.PostgreSQLStore") as _pgs:
        _submit_reversal_force_sells(
            reversal_sell_symbols={"SOXX": {"score": -0.42, "signal_id": 3861}},
            final_orders=[],
            stop_loss_sells={},
            alpaca_positions=[_make_alpaca_position("SOXX", 1.13)],
            trading_client=trading_client,
            submitted_orders=submitted_orders,
            ts=datetime(2026, 7, 16, 18, 22, tzinfo=timezone.utc),
            regime_mult=0.7,
            operating_mode="active",
        )

    assert events == [("cancel", "stop-7"), ("submit", "SOXX")]
    assert len(submitted_orders) == 1
    assert submitted_orders[0]["symbol"] == "SOXX"
    assert submitted_orders[0]["reason"] == "sentiment_reversal"
    assert submitted_orders[0]["order_id"] == "ord-9"
    # The Decision Log SELL row must actually be written (a silent NameError in
    # this block was caught by the blanket except and only logged as a warning).
    _pgs.return_value.write_execution_decision.assert_called_once()
    _dec_kwargs = _pgs.return_value.write_execution_decision.call_args.kwargs
    assert _dec_kwargs["symbol"] == "SOXX"
    assert _dec_kwargs["order_id"] == "ord-9"
    assert "sentiment_reversal" in _dec_kwargs["reason"]


def test_reversal_force_sell_skips_symbol_already_being_sold():
    """A symbol with a SELL already in final_orders must not be double-sold
    (guards the OrderSide 'SELL' vs 'sell' case mismatch found 2026-07-17)."""
    from src.workers.portfolio_scheduler import _submit_reversal_force_sells

    trading_client = MagicMock()
    submitted_orders = []
    _submit_reversal_force_sells(
        reversal_sell_symbols={"SOXX": {"score": -0.42, "signal_id": None}},
        final_orders=[_make_combined_order("SOXX", OrderSide.SELL, qty=1.13)],
        stop_loss_sells={},
        alpaca_positions=[_make_alpaca_position("SOXX", 1.13)],
        trading_client=trading_client,
        submitted_orders=submitted_orders,
        ts=datetime(2026, 7, 16, 18, 22, tzinfo=timezone.utc),
        regime_mult=0.7,
        operating_mode="active",
    )

    trading_client.submit_order.assert_not_called()
    assert submitted_orders == []


def test_reversal_force_sell_noop_in_dry_run_and_halted():
    """dry_run / halted modes never touch the broker."""
    from src.workers.portfolio_scheduler import _submit_reversal_force_sells

    for mode in ("dry_run", "halted"):
        trading_client = MagicMock()
        _submit_reversal_force_sells(
            reversal_sell_symbols={"SOXX": {"score": -0.42, "signal_id": None}},
            final_orders=[],
            stop_loss_sells={},
            alpaca_positions=[_make_alpaca_position("SOXX", 1.13)],
            trading_client=trading_client,
            submitted_orders=[],
            ts=datetime(2026, 7, 16, 18, 22, tzinfo=timezone.utc),
            regime_mult=0.7,
            operating_mode=mode,
        )
        trading_client.submit_order.assert_not_called()
        trading_client.cancel_order_by_id.assert_not_called()


# ── #67/#68: consume-on-fire marker + cross-strategy re-entry cooldown ────────


def test_reversal_force_sell_marks_consumed_and_cooldown():
    """After a successful force-sell the signal is consumed (never fires twice)
    and the symbol enters the re-entry cooldown (S1 must not rebuy in 15 min)."""
    from src.workers.portfolio_scheduler import _submit_reversal_force_sells

    trading_client = MagicMock()
    trading_client.get_orders.return_value = []
    resp = MagicMock()
    resp.id = "ord-9"
    trading_client.submit_order.return_value = resp
    redis_client = MagicMock()

    with patch("src.store.pg_store.PostgreSQLStore"):
        _submit_reversal_force_sells(
            reversal_sell_symbols={"SOXX": {"score": -0.42, "signal_id": 3861, "identity": "3861"}},
            final_orders=[],
            stop_loss_sells={},
            alpaca_positions=[_make_alpaca_position("SOXX", 1.13)],
            trading_client=trading_client,
            submitted_orders=[],
            ts=datetime(2026, 7, 16, 18, 22, tzinfo=timezone.utc),
            regime_mult=0.7,
            operating_mode="active",
            redis_client=redis_client,
        )

    setex_keys = {c.args[0]: c.args[2] for c in redis_client.setex.call_args_list}
    assert setex_keys.get("signal:SOXX:reversal_consumed") == "3861"
    assert "reversal_cooldown:SOXX" in setex_keys


def test_submit_portfolio_orders_skips_buy_in_reversal_cooldown():
    """A symbol force-sold for reversal must not be re-bought during the cooldown."""
    from src.workers.portfolio_scheduler import _submit_portfolio_orders

    orders = [_make_combined_order("SOXX", OrderSide.BUY, qty=1.0)]
    trading_client = MagicMock()
    market = _make_market(prices={"SOXX": 520.0})

    calls = []
    with patch(
        "src.workers.portfolio_scheduler._get_reversal_cooldown_symbols",
        return_value={"SOXX"},
    ), patch(
        "src.workers.portfolio_scheduler._get_stop_loss_cooldown_symbols",
        return_value=set(),
    ):
        submitted = _submit_portfolio_orders(
            orders, trading_client, market,
            _submit_fn=lambda o, n, c: calls.append(o.symbol),
        )

    assert submitted == []
    assert calls == []


# ── #71: S1 re-entry cooldown enforcement (BUY-side) ─────────────────────────


def test_submit_portfolio_orders_skips_s1_only_buy_in_reentry_cooldown_when_enabled():
    """S1 excluded SBUX last cycle; flag on -> S1's own re-BUY must be skipped."""
    from src.workers.portfolio_scheduler import _submit_portfolio_orders

    orders = [_make_combined_order("SBUX", OrderSide.BUY, qty=2.0)]
    trading_client = MagicMock()
    market = _make_market(prices={"SBUX": 90.0})

    calls = []
    with patch(
        "src.workers.portfolio_scheduler._get_reversal_cooldown_symbols",
        return_value=set(),
    ), patch(
        "src.workers.portfolio_scheduler._get_stop_loss_cooldown_symbols",
        return_value=set(),
    ), patch(
        "src.workers.portfolio_scheduler._get_s1_reentry_cooldown_symbols",
        return_value={"SBUX"},
    ):
        submitted = _submit_portfolio_orders(
            orders, trading_client, market,
            _submit_fn=lambda o, n, c: calls.append(o.symbol),
            risk_cfg={"s1_reentry_cooldown_enabled": True},
            sym_strats={"SBUX": ["S1"]},
        )

    assert submitted == []
    assert calls == []


def test_submit_portfolio_orders_does_not_block_s1_reentry_when_flag_disabled():
    """Same cooldown state, but the flag is off (default) -> BUY proceeds."""
    from src.workers.portfolio_scheduler import _submit_portfolio_orders

    orders = [_make_combined_order("SBUX", OrderSide.BUY, qty=2.0)]
    trading_client = MagicMock()
    market = _make_market(prices={"SBUX": 90.0})

    calls = []
    with patch(
        "src.workers.portfolio_scheduler._get_reversal_cooldown_symbols",
        return_value=set(),
    ), patch(
        "src.workers.portfolio_scheduler._get_stop_loss_cooldown_symbols",
        return_value=set(),
    ), patch(
        "src.workers.portfolio_scheduler._get_s1_reentry_cooldown_symbols",
        return_value={"SBUX"},
    ):
        submitted = _submit_portfolio_orders(
            orders, trading_client, market,
            _submit_fn=lambda o, n, c: calls.append(o.symbol),
            risk_cfg={"s1_reentry_cooldown_enabled": False},
            sym_strats={"SBUX": ["S1"]},
        )

    assert calls == ["SBUX"]


def test_submit_portfolio_orders_does_not_block_s4_buy_on_s1_cooldown_symbol():
    """S1 excluded SBUX, but THIS BUY is S4-driven (or mixed) — must not be
    vetoed by S1's own churn cooldown, unlike #68's cross-strategy block."""
    from src.workers.portfolio_scheduler import _submit_portfolio_orders

    orders = [_make_combined_order("SBUX", OrderSide.BUY, qty=2.0)]
    trading_client = MagicMock()
    market = _make_market(prices={"SBUX": 90.0})

    calls = []
    with patch(
        "src.workers.portfolio_scheduler._get_reversal_cooldown_symbols",
        return_value=set(),
    ), patch(
        "src.workers.portfolio_scheduler._get_stop_loss_cooldown_symbols",
        return_value=set(),
    ), patch(
        "src.workers.portfolio_scheduler._get_s1_reentry_cooldown_symbols",
        return_value={"SBUX"},
    ):
        submitted = _submit_portfolio_orders(
            orders, trading_client, market,
            _submit_fn=lambda o, n, c: calls.append(o.symbol),
            risk_cfg={"s1_reentry_cooldown_enabled": True},
            sym_strats={"SBUX": ["S4"]},
        )

    assert calls == ["SBUX"]


# ── B28-FIX origin-strategy attribution bug (2026-07-17 DB incident) ─────────
#
# trades.stop_strategy (and therefore which stop_strategy_params k/floor/cap
# apply to the position) was resolved via a binary heuristic —
# "S4" if decision.get("signal_id") else "S1" — instead of the accurate,
# already-computed _sym_strats mapping (CycleResult.symbol_strategies: which
# strategies actually contributed weight to this symbol THIS cycle). Real
# incident: trade 361 (DB, 2026-07-17) was a genuine S4 BUY (execution_
# decisions.reason said "S4 news-driven: sentiment +0.672...") but its
# signal_id wasn't present in _symbol_decisions at write time, so the
# heuristic silently mislabeled it "S1" — corrupting which stop params
# applied to a $6,181 position.


class TestResolveBuyOriginStrategy:
    def test_prefers_s4_from_sym_strats_even_when_signal_id_missing(self):
        """Reproduces the 2026-07-17 DB incident: S4 contributed the weight
        this cycle, but decision["signal_id"] is missing — must still resolve S4."""
        from src.workers.portfolio_scheduler import _resolve_buy_origin_strategy

        result = _resolve_buy_origin_strategy(
            "DB", sym_strats={"DB": ["S4"]}, decision={"decision_id": 3245},
        )

        assert result == "S4"

    def test_resolves_s1_from_sym_strats(self):
        from src.workers.portfolio_scheduler import _resolve_buy_origin_strategy

        result = _resolve_buy_origin_strategy(
            "SBUX", sym_strats={"SBUX": ["S1"]}, decision={},
        )

        assert result == "S1"

    def test_s4_takes_priority_when_both_contribute(self):
        from src.workers.portfolio_scheduler import _resolve_buy_origin_strategy

        result = _resolve_buy_origin_strategy(
            "XLK", sym_strats={"XLK": ["S1", "S4"]}, decision={},
        )

        assert result == "S4"

    def test_falls_back_to_first_strategy_for_other_combos(self):
        from src.workers.portfolio_scheduler import _resolve_buy_origin_strategy

        result = _resolve_buy_origin_strategy(
            "SPY", sym_strats={"SPY": ["S2"]}, decision={},
        )

        assert result == "S2"

    def test_defensive_fallback_to_legacy_heuristic_when_sym_strats_empty(self):
        """sym_strats missing an entry shouldn't happen for a just-submitted BUY,
        but stay defensive — fall back to the old signal_id heuristic rather
        than crash or silently mis-set None."""
        from src.workers.portfolio_scheduler import _resolve_buy_origin_strategy

        with_signal = _resolve_buy_origin_strategy(
            "AAPL", sym_strats={}, decision={"signal_id": 999},
        )
        without_signal = _resolve_buy_origin_strategy(
            "AAPL", sym_strats={}, decision={},
        )

        assert with_signal == "S4"
        assert without_signal == "S1"


# ── #32 F8 shadow persistence: build DB rows from result.feedback_shadow ──────


def test_build_f8_shadow_rows_one_row_per_strategy():
    from src.workers.portfolio_scheduler import _build_f8_shadow_rows

    ts = datetime(2026, 7, 21, 14, 0, tzinfo=timezone.utc)
    shadow = {
        "S1": {"scale": 0.512, "unscaled_weight": 0.5, "scaled_weight": 0.256, "applied": False},
        "S4": {"scale": 0.80, "unscaled_weight": 0.1, "scaled_weight": 0.08, "applied": False},
    }

    rows = _build_f8_shadow_rows(ts, shadow)

    assert len(rows) == 2
    by_strat = {r["strategy"]: r for r in rows}
    assert by_strat["S1"]["cycle_ts"] == ts
    assert by_strat["S1"]["scale"] == 0.512
    assert by_strat["S1"]["unscaled_weight"] == 0.5
    assert by_strat["S1"]["scaled_weight"] == 0.256
    assert by_strat["S1"]["applied"] is False
    assert by_strat["S4"]["scale"] == 0.80


def test_build_f8_shadow_rows_empty_when_no_shadow():
    from src.workers.portfolio_scheduler import _build_f8_shadow_rows

    assert _build_f8_shadow_rows(datetime.now(timezone.utc), {}) == []
    assert _build_f8_shadow_rows(datetime.now(timezone.utc), None) == []


def test_build_f8_shadow_rows_tolerates_missing_keys():
    """A malformed shadow entry must not crash the cycle — missing numeric
    fields default to None, not a KeyError."""
    from src.workers.portfolio_scheduler import _build_f8_shadow_rows

    rows = _build_f8_shadow_rows(
        datetime(2026, 7, 21, tzinfo=timezone.utc), {"S1": {"scale": 0.64}}
    )
    assert len(rows) == 1
    assert rows[0]["scale"] == 0.64
    assert rows[0]["unscaled_weight"] is None
    assert rows[0]["applied"] is None


# ── drawdown kill-switch peak seeding (bug 2026-07-22: peak never persisted) ──
# portfolio:peak_equity was never written because the write condition was
# `equity > peak` while peak defaulted to equity on an empty key — so the peak
# never seeded and the 5% drawdown cap could never fire.


def test_peak_and_drawdown_seeds_on_first_observation():
    from src.workers.portfolio_scheduler import _peak_and_drawdown
    peak, dd = _peak_and_drawdown(None, 110000.0)
    assert peak == 110000.0
    assert dd == 0.0


def test_peak_and_drawdown_measures_from_prior_peak():
    from src.workers.portfolio_scheduler import _peak_and_drawdown
    peak, dd = _peak_and_drawdown(120000.0, 108000.0)
    assert peak == 120000.0
    assert dd == pytest.approx((120000.0 - 108000.0) / 120000.0)  # 10%


def test_peak_and_drawdown_advances_on_new_high():
    from src.workers.portfolio_scheduler import _peak_and_drawdown
    peak, dd = _peak_and_drawdown(100000.0, 120000.0)
    assert peak == 120000.0
    assert dd == 0.0


# ── #108 — S4 BUY must not fire on FinBERT-fallback signals (mirror SELL guard) ─
from types import SimpleNamespace as _SNS


def test_filter_fallback_signals_drops_fallback_keeps_ensemble():
    from src.workers.portfolio_scheduler import _filter_fallback_signals
    sigs = [
        _SNS(symbol="AAPL", fallback_used=False),
        _SNS(symbol="WDC", fallback_used=True),   # FinBERT fallback → dropped for BUY
        _SNS(symbol="MSFT", fallback_used=False),
    ]
    keep, dropped = _filter_fallback_signals(sigs)
    assert [s.symbol for s in keep] == ["AAPL", "MSFT"]
    assert [s.symbol for s in dropped] == ["WDC"]


def test_filter_fallback_signals_all_ensemble_keeps_all():
    from src.workers.portfolio_scheduler import _filter_fallback_signals
    sigs = [_SNS(symbol="A", fallback_used=False), _SNS(symbol="B", fallback_used=False)]
    keep, dropped = _filter_fallback_signals(sigs)
    assert len(keep) == 2 and dropped == []


# ── #109 — logged S4 conviction must come from the SAME signal_id it links to ──


def test_s4_signal_metadata_matches_resolved_signal_id():
    """WDC regression: id resolved to the finbert +0.363 signal, so the logged
    score must be +0.363 — NOT the ensemble −0.385 that a separate query returns."""
    from src.workers.portfolio_scheduler import _s4_signal_metadata_by_id
    signal_ids = {"WDC": 4427}
    signals_by_id = [
        {"signal_id": 4427, "symbol": "WDC", "score": 0.363, "reasoning": "fb", "model_id": "finbert"},
        {"signal_id": 4390, "symbol": "WDC", "score": -0.385, "reasoning": "ens", "model_id": "ensemble"},
    ]
    out = _s4_signal_metadata_by_id(signal_ids, signals_by_id)
    assert out["WDC"]["score"] == 0.363
    assert out["WDC"]["model_id"] == "finbert"


def test_s4_signal_metadata_skips_symbol_with_no_matching_row():
    from src.workers.portfolio_scheduler import _s4_signal_metadata_by_id
    out = _s4_signal_metadata_by_id({"X": 99}, [{"signal_id": 1, "symbol": "Y", "score": 0.1, "reasoning": "", "model_id": "m"}])
    assert out == {}
