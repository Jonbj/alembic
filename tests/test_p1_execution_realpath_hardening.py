"""P1-EXECUTION-REALPATH-HARDENING — Safety gaps in the execution real-path.

Problems identified in ALEMBIC_REMEDIATION_MASTER_PLAN_2026-06-18 (WS-03):

1. BUY without stop-loss when price unavailable:
   run_execution_cycle falls through to a plain MarketOrderRequest (no bracket/
   stop-loss leg) when the EMA cache cannot provide a price. An unprotected BUY
   leaves the position with unlimited downside until the 15-min software poll fires.
   Fix: when price is None, log SKIP_NO_PRICE and skip the entry — never BUY
   without a stop-loss attached.

2. Market clock failure must abort cycle (test for existing portfolio_scheduler logic):
   When get_clock() raises an exception, the cycle must abort (fail-closed), not
   proceed with potentially stale orders. The portfolio_scheduler already implements
   this but had no test for the exception-raising path. Adding it to ensure the
   behavior is pinned and doesn't regress.

3. Pending-order guard: already verified in test_p0_05_execution_safety.py and
   P1-S4-FRESHNESS-IDEMPOTENCY; documented here for completeness.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch


def _fresh_signal(symbol: str, score: float = 0.5) -> dict:
    return {
        "symbol": symbol,
        "score": score,
        "generated_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
        "confidence": 0.8,
        "fallback_used": False,
        "signal_id": 1,
    }


def _make_alpaca_account(portfolio_value=100_000.0, last_equity=100_000.0):
    acc = MagicMock()
    acc.portfolio_value = str(portfolio_value)
    acc.buying_power = str(portfolio_value)
    acc.last_equity = str(last_equity)
    return acc


# ─────────────────────────────────────────────────────────────────────────────
# 1. BUY without stop-loss guard
# ─────────────────────────────────────────────────────────────────────────────

class TestBuyAlwaysHasStopLoss:

    def test_buy_with_price_available_uses_oto_bracket(self):
        """When price is available, BUY must use OTO order class with stop-loss."""
        from src.workers.execution import run_execution_cycle
        from src.store.redis_store import RedisStore

        redis_store = MagicMock(spec=RedisStore)
        redis_store.is_killswitch_active.return_value = False
        redis_store.get_regime.return_value = MagicMock(multiplier=1.0)
        redis_store.read_sentiment.return_value = _fresh_signal("SPY", score=0.8)
        redis_store.get_feedback_entry_threshold.return_value = None
        redis_store.get_feedback_entry_threshold.return_value = None

        trading_client = MagicMock()
        trading_client.get_account.return_value = _make_alpaca_account()
        trading_client.get_all_positions.return_value = []
        trading_client.get_orders.return_value = []
        submitted_orders = []
        trading_client.submit_order.side_effect = lambda req: submitted_orders.append(req) or MagicMock(id="ord-1")

        # data_client returns a price via EMA cache
        # We patch _build_market_cache to return a valid price
        with patch("src.workers.execution._build_market_cache") as mock_cache:
            mock_cache.return_value = {"SPY": {"ema": 440.0, "price": 450.0}}
            run_execution_cycle(
                symbols=["SPY"],
                redis_store=redis_store,
                trading_client=trading_client,
                data_client=MagicMock(),
            )

        assert len(submitted_orders) == 1
        order = submitted_orders[0]
        # OTO order class carries the stop-loss leg
        from alpaca.trading.enums import OrderClass
        assert order.order_class == OrderClass.OTO, (
            "BUY with known price must use OTO bracket to attach a stop-loss leg"
        )
        assert order.stop_loss is not None, "OTO order must include a stop_loss leg"

    def test_buy_blocked_when_price_unavailable(self):
        """When price is None (EMA cache miss), BUY must be blocked — no order placed.

        The alternative (plain MarketOrderRequest without bracket) would leave the
        position unprotected until the next software-poll stop-loss check fires.
        Fail-safe: skip the entry rather than risk unlimited downside.
        """
        from src.workers.execution import run_execution_cycle
        from src.store.redis_store import RedisStore

        redis_store = MagicMock(spec=RedisStore)
        redis_store.is_killswitch_active.return_value = False
        redis_store.get_regime.return_value = MagicMock(multiplier=1.0)
        redis_store.read_sentiment.return_value = _fresh_signal("SPY", score=0.8)
        redis_store.get_feedback_entry_threshold.return_value = None
        redis_store.get_feedback_entry_threshold.return_value = None

        trading_client = MagicMock()
        trading_client.get_account.return_value = _make_alpaca_account()
        trading_client.get_all_positions.return_value = []
        trading_client.get_orders.return_value = []

        # EMA cache: price is None — can't compute stop-loss price
        with patch("src.workers.execution._build_market_cache") as mock_cache:
            mock_cache.return_value = {"SPY": {"ema": None, "price": None}}
            stats = run_execution_cycle(
                symbols=["SPY"],
                redis_store=redis_store,
                trading_client=trading_client,
                data_client=MagicMock(),
            )

        assert trading_client.submit_order.call_count == 0, (
            "No order should be placed when price is unavailable — "
            "a BUY without a stop-loss price is unsafe."
        )
        assert stats["orders_placed"] == 0

    def test_buy_blocked_when_data_client_unavailable(self):
        """When data_client is None (no EMA), BUY must be blocked rather than placed without stop-loss."""
        from src.workers.execution import run_execution_cycle
        from src.store.redis_store import RedisStore

        redis_store = MagicMock(spec=RedisStore)
        redis_store.is_killswitch_active.return_value = False
        redis_store.get_regime.return_value = MagicMock(multiplier=1.0)
        redis_store.read_sentiment.return_value = _fresh_signal("SPY", score=0.9)
        redis_store.get_feedback_entry_threshold.return_value = None
        redis_store.get_feedback_entry_threshold.return_value = None

        trading_client = MagicMock()
        trading_client.get_account.return_value = _make_alpaca_account()
        trading_client.get_all_positions.return_value = []
        trading_client.get_orders.return_value = []

        stats = run_execution_cycle(
            symbols=["SPY"],
            redis_store=redis_store,
            trading_client=trading_client,
            data_client=None,  # no EMA client → no price → no stop-loss → must block
        )

        assert trading_client.submit_order.call_count == 0, (
            "Without data_client, price is unknown so stop-loss price cannot be computed. "
            "BUY must be blocked, not placed without stop-loss protection."
        )
        assert stats["orders_placed"] == 0

    def test_stats_skipped_momentum_incremented_when_price_missing(self):
        """skipped_momentum counter must be incremented when price is None and entry is blocked."""
        from src.workers.execution import run_execution_cycle
        from src.store.redis_store import RedisStore

        redis_store = MagicMock(spec=RedisStore)
        redis_store.is_killswitch_active.return_value = False
        redis_store.get_regime.return_value = MagicMock(multiplier=1.0)
        redis_store.read_sentiment.return_value = _fresh_signal("SPY", score=0.8)
        redis_store.get_feedback_entry_threshold.return_value = None
        redis_store.get_feedback_entry_threshold.return_value = None

        trading_client = MagicMock()
        trading_client.get_account.return_value = _make_alpaca_account()
        trading_client.get_all_positions.return_value = []
        trading_client.get_orders.return_value = []

        with patch("src.workers.execution._build_market_cache") as mock_cache:
            mock_cache.return_value = {"SPY": {"ema": None, "price": None}}
            stats = run_execution_cycle(
                symbols=["SPY"],
                redis_store=redis_store,
                trading_client=trading_client,
                data_client=MagicMock(),
            )

        assert stats["skipped_momentum"] > 0, (
            "Skipping an entry due to missing price must increment skipped_momentum "
            "so the operator can see it in the stats dashboard."
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Market clock failure aborts cycle (portfolio_scheduler path)
# ─────────────────────────────────────────────────────────────────────────────

class TestMarketClockFailClosedAbortsCycle:

    def test_clock_exception_aborts_cycle(self, approved_strategy):
        """When get_clock() raises, _run_cycle_inner must return error='clock_unavailable'.

        The portfolio_scheduler already implements this (P0-07 fail-closed). This test
        pins the behavior so it doesn't regress.
        """
        from src.workers.portfolio_scheduler import _run_cycle_inner
        from unittest.mock import patch, MagicMock

        with patch("src.strategies.registry.StrategyRegistry") as mock_reg, \
             patch("alpaca.data.historical.StockHistoricalDataClient"), \
             patch("alpaca.trading.client.TradingClient") as mock_tc, \
             patch("redis.Redis") as mock_redis_cls:

            entry = MagicMock()
            entry.strategy_id = "S1"
            mock_reg.return_value.get_active_strategies.return_value = [entry]

            # Clock API raises — e.g., network timeout
            mock_tc.return_value.get_clock.side_effect = RuntimeError("Connection timeout")

            redis_inst = MagicMock()
            redis_inst.get.return_value = None
            mock_redis_cls.from_url.return_value = redis_inst

            with approved_strategy("S1"):
                result = _run_cycle_inner()

        assert result.get("error") == "clock_unavailable", (
            "When get_clock() raises, cycle must abort with error='clock_unavailable'. "
            "Proceeding without knowing market state risks placing orders to a closed market."
        )

    def test_clock_exception_does_not_place_orders(self):
        """When get_clock() raises, no orders must be submitted."""
        from src.workers.portfolio_scheduler import _run_cycle_inner

        with patch("src.strategies.registry.StrategyRegistry") as mock_reg, \
             patch("alpaca.data.historical.StockHistoricalDataClient"), \
             patch("alpaca.trading.client.TradingClient") as mock_tc, \
             patch("redis.Redis") as mock_redis_cls:

            entry = MagicMock()
            entry.strategy_id = "S1"
            mock_reg.return_value.get_active_strategies.return_value = [entry]

            mock_tc.return_value.get_clock.side_effect = ConnectionError("Clock API down")

            redis_inst = MagicMock()
            redis_inst.get.return_value = None
            mock_redis_cls.from_url.return_value = redis_inst

            _run_cycle_inner()

        # No orders should be submitted since we aborted before reaching order logic
        mock_tc.return_value.submit_order.assert_not_called()
