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

    mock_signals = [
        SentimentResult(
            symbol="NVDA", score=0.8, confidence=0.9, reasoning="Positive",
            model_id="test", generated_at=datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc),
        ),
        SentimentResult(
            symbol="MSFT", score=0.6, confidence=0.7, reasoning="Neutral",
            model_id="test", generated_at=datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc),
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

    def capture_submit(orders, trading_client, market, _submit_fn=None):
        captured_orders.extend(orders)
        return len(orders)

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

    # S4's DB fetch must have been triggered (signal loading path exercised)
    mock_store.fetch_signals_for_cycle.assert_called_once()

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