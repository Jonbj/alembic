"""P1-BACKTEST-TPLUS1-FILL — T+1 fill at next-bar open for backtest orchestrator.

Problem (P0-11 residual, acceptance audit 2026-06-18):
- Orchestrator fills orders at close[t] — the same bar on which the signal was generated.
- Real execution happens at open[t+1]: a signal observed at close[Thursday] is sent
  to the broker overnight and executed at Friday's open.
- Same-bar fill produces optimistic backtest performance (artificial alpha).

Fix:
- DataReplay accepts an optional `opens` DataFrame.
- DataReplay.market_at_open(ts) returns a MarketSnapshot using open prices (fallback to close).
- BacktestConfig.fill_at_next_open: bool = True enables T+1 fill.
- Orchestrator buffers orders from bar[t] and fills them at bar[t+1] open.
- Pending orders at the last bar are filled at close of last bar (not lost).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from src.backtest.engine.data_replay import DataReplay
from src.backtest.engine.orchestrator import BacktestConfig, BacktestOrchestrator
from src.backtest.engine.order_simulation import SimpleCostModel
from src.backtest.engine.portfolio import VirtualPortfolio
from src.backtest.engine.types import MarketSnapshot, Order, OrderSide


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_prices(closes: list[float], symbol: str = "SPY") -> pd.DataFrame:
    dates = pd.date_range("2024-01-02", periods=len(closes), freq="B")
    return pd.DataFrame({symbol: closes}, index=dates)


def _make_opens(opens: list[float], symbol: str = "SPY") -> pd.DataFrame:
    dates = pd.date_range("2024-01-02", periods=len(opens), freq="B")
    return pd.DataFrame({symbol: opens}, index=dates)


def _one_shot_buy(symbol: str = "SPY", qty: float = 10.0):
    """Strategy: buy once on the first bar, hold."""
    fired = []
    def _strategy(ts, dr, port, mkt):
        if not fired and mkt.has_price(symbol):
            fired.append(ts)
            return [Order.market_order(ts, symbol, OrderSide.BUY, qty, "test")]
        return []
    return _strategy


# ─────────────────────────────────────────────────────────────────────────────
# Group A — DataReplay opens API
# ─────────────────────────────────────────────────────────────────────────────

class TestDataReplayOpens:

    def test_data_replay_accepts_opens_dataframe(self):
        """DataReplay(prices, opens=opens_df) must not raise."""
        prices = _make_prices([100.0, 110.0, 120.0])
        opens = _make_opens([102.0, 112.0, 122.0])

        replay = DataReplay(prices, opens=opens)
        assert replay is not None

    def test_market_at_open_returns_open_prices(self):
        """market_at_open must return a snapshot with open prices, not close prices."""
        prices = _make_prices([100.0, 110.0, 120.0])
        opens = _make_opens([105.0, 115.0, 125.0])
        replay = DataReplay(prices, opens=opens)

        ts = prices.index[1]  # second bar
        snap = replay.market_at_open(ts)

        assert snap.price_of("SPY") == pytest.approx(115.0), (
            f"market_at_open must return open price 115.0, got {snap.price_of('SPY')}"
        )

    def test_market_at_open_falls_back_to_close_without_opens(self):
        """Without opens DataFrame, market_at_open must fall back to close prices."""
        prices = _make_prices([100.0, 110.0, 120.0])
        replay = DataReplay(prices)

        ts = prices.index[1]
        open_snap = replay.market_at_open(ts)
        close_snap = replay.market_at(ts)

        assert open_snap.price_of("SPY") == pytest.approx(close_snap.price_of("SPY")), (
            "Without opens, market_at_open must return close prices as fallback"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Group B — Orchestrator T+1 fill behavior
# ─────────────────────────────────────────────────────────────────────────────

class TestBacktestOrchestratorTPlus1:

    def test_backtest_config_has_fill_at_next_open_flag(self):
        """BacktestConfig must expose fill_at_next_open defaulting to True."""
        cfg = BacktestConfig()
        assert hasattr(cfg, "fill_at_next_open"), (
            "BacktestConfig must have fill_at_next_open field (P1-BACKTEST-TPLUS1-FILL)"
        )
        assert cfg.fill_at_next_open is True, "Default must be True (T+1 fill enabled)"

    def test_fill_timestamp_is_next_bar(self):
        """With T+1 fill active, fill timestamp must be bar[t+1], not bar[t] (decision bar)."""
        closes = [100.0, 110.0, 120.0, 130.0]
        prices = _make_prices(closes)
        replay = DataReplay(prices)
        cost = SimpleCostModel(spread_bps=0.0)
        orc = BacktestOrchestrator(BacktestConfig(fill_at_next_open=True), cost_model=cost)

        result = orc.run(replay, _one_shot_buy(qty=1.0))

        assert len(result.fills) == 1
        fill = result.fills[0]
        decision_ts = prices.index[0]
        fill_ts = prices.index[1]  # expected: next bar
        assert fill.timestamp == fill_ts, (
            f"Fill timestamp must be next bar ({fill_ts}), got {fill.timestamp}"
        )
        assert fill.timestamp != decision_ts, (
            "Fill timestamp must NOT equal the decision bar timestamp"
        )

    def test_fill_price_uses_next_bar_open(self):
        """With opens provided and fill_at_next_open=True, fill price is derived from open[t+1]."""
        prices = _make_prices([100.0, 110.0, 120.0, 130.0])
        opens = _make_opens([50.0, 108.0, 118.0, 128.0])  # open[1]=108, clearly distinct
        replay = DataReplay(prices, opens=opens)
        cost = SimpleCostModel(spread_bps=0.0)  # zero spread → fill_price == mid_price
        orc = BacktestOrchestrator(BacktestConfig(fill_at_next_open=True), cost_model=cost)

        result = orc.run(replay, _one_shot_buy(qty=1.0))

        assert len(result.fills) == 1
        fill = result.fills[0]
        # open[1] = 108.0 (day 2 open); close[0] = 100.0 (decision bar)
        assert fill.fill_price == pytest.approx(108.0, rel=1e-3), (
            f"Fill must use next bar open (108.0), got {fill.fill_price}. "
            f"Same-bar close was 100.0 — if you see ~100.0, T+1 fill is not working."
        )

    def test_same_bar_fill_when_fill_at_next_open_false(self):
        """With fill_at_next_open=False, fill price is derived from close[t] (backward compat)."""
        prices = _make_prices([100.0, 110.0, 120.0])
        opens = _make_opens([108.0, 118.0, 128.0])
        replay = DataReplay(prices, opens=opens)
        cost = SimpleCostModel(spread_bps=0.0)
        orc = BacktestOrchestrator(BacktestConfig(fill_at_next_open=False), cost_model=cost)

        result = orc.run(replay, _one_shot_buy(qty=1.0))

        assert len(result.fills) == 1
        fill = result.fills[0]
        # Must fill at close[0] = 100.0, not open[1] = 108.0
        assert fill.fill_price == pytest.approx(100.0, rel=1e-3), (
            f"With fill_at_next_open=False, must use same-bar close (100.0), got {fill.fill_price}"
        )

    def test_pending_orders_executed_at_bar_t1(self):
        """Orders queued at bar[t] appear in fills with timestamp bar[t+1]."""
        closes = [100.0, 200.0, 300.0, 400.0, 500.0]
        prices = _make_prices(closes)
        replay = DataReplay(prices)
        cost = SimpleCostModel(spread_bps=0.0)
        orc = BacktestOrchestrator(BacktestConfig(fill_at_next_open=True), cost_model=cost)

        result = orc.run(replay, _one_shot_buy(qty=1.0))

        assert len(result.fills) == 1
        # Buy was generated at index[0] (close=100), so fill must be at index[1]
        assert result.fills[0].timestamp == prices.index[1]

    def test_last_bar_pending_orders_are_filled(self):
        """Orders generated on the last bar are not lost — filled at last bar's close."""
        prices = _make_prices([100.0, 110.0])  # 2 bars only
        replay = DataReplay(prices)
        cost = SimpleCostModel(spread_bps=0.0)
        orc = BacktestOrchestrator(BacktestConfig(fill_at_next_open=True), cost_model=cost)

        # Strategy buys on bar[1] (the last bar) — no next bar exists
        last_fired = []
        def last_bar_strategy(ts, dr, port, mkt):
            if ts == prices.index[1] and not last_fired:
                last_fired.append(True)
                return [Order.market_order(ts, "SPY", OrderSide.BUY, 1.0, "test")]
            return []

        result = orc.run(replay, last_bar_strategy)
        # Must produce exactly 1 fill (not 0)
        assert len(result.fills) == 1, (
            "Orders from last bar must be filled (at last bar's close), not dropped"
        )

    def test_no_look_ahead_fill_uses_different_price_than_decision(self):
        """Fill price with T+1 is demonstrably different from the decision-bar close."""
        prices = _make_prices([100.0, 200.0, 300.0])  # prices change dramatically day to day
        opens = _make_opens([150.0, 250.0, 350.0])    # opens halfway between closes
        replay = DataReplay(prices, opens=opens)
        cost = SimpleCostModel(spread_bps=0.0)
        orc = BacktestOrchestrator(BacktestConfig(fill_at_next_open=True), cost_model=cost)

        result = orc.run(replay, _one_shot_buy(qty=1.0))

        assert len(result.fills) == 1
        fill = result.fills[0]
        decision_bar_close = 100.0
        next_bar_open = 250.0  # open[1] = 250.0
        # Fill must NOT be at decision-bar close
        assert fill.fill_price != pytest.approx(decision_bar_close, rel=1e-3), (
            f"Fill must not be at decision-bar close {decision_bar_close}"
        )
        assert fill.fill_price == pytest.approx(next_bar_open, rel=1e-3), (
            f"Fill must be at next-bar open {next_bar_open}, got {fill.fill_price}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Group C — Backtest numbers with T+1 fill
# ─────────────────────────────────────────────────────────────────────────────

class TestTPlus1BacktestNumbers:

    def test_tplus1_nav_different_from_same_bar_nav(self):
        """Final NAV with T+1 fill is different from same-bar fill when prices diverge."""
        # Close prices rise; opens are higher than previous close (gap-up pattern)
        n = 10
        closes = [100.0 + i * 10 for i in range(n)]   # 100, 110, 120, ..., 190
        opens  = [105.0 + i * 10 for i in range(n)]   # 105, 115, 125, ..., 195 (open > prev close)

        prices_df = _make_prices(closes)
        opens_df  = _make_opens(opens)
        cost = SimpleCostModel(spread_bps=0.0)

        replay_same = DataReplay(prices_df)
        orc_same = BacktestOrchestrator(BacktestConfig(fill_at_next_open=False, initial_capital=10_000), cost_model=cost)
        result_same = orc_same.run(replay_same, _one_shot_buy(qty=10.0))

        replay_t1 = DataReplay(prices_df, opens=opens_df)
        orc_t1 = BacktestOrchestrator(BacktestConfig(fill_at_next_open=True, initial_capital=10_000), cost_model=cost)
        result_t1 = orc_t1.run(replay_t1, _one_shot_buy(qty=10.0))

        nav_same = result_same.snapshots[-1].total_nav
        nav_t1   = result_t1.snapshots[-1].total_nav

        assert nav_same != pytest.approx(nav_t1, rel=1e-4), (
            f"T+1 fill NAV ({nav_t1}) must differ from same-bar NAV ({nav_same}) "
            f"when open != close of previous bar"
        )
