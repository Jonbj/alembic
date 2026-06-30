"""T-402: S4 NewsDrivenTactical strategy module tests."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.backtest.engine.portfolio import VirtualPortfolio
from src.backtest.engine.types import Fill, Order, OrderSide, RebalanceFrequency
from src.models.signals import SentimentResult
from src.strategies.s4.config import S4Config
from src.strategies.s4.strategy import NewsDrivenTactical


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = datetime(2024, 1, 8, tzinfo=timezone.utc)  # Monday week 2
_TS_SAME_WEEK = datetime(2024, 1, 9, tzinfo=timezone.utc)  # Tuesday same week
_TS_NEXT_WEEK = datetime(2024, 1, 15, tzinfo=timezone.utc)  # Monday week 3


def _sig(
    symbol: str,
    score: float = 0.6,
    confidence: float = 0.8,
    generated_at: datetime | None = None,
) -> SentimentResult:
    return SentimentResult(
        symbol=symbol,
        score=score,
        confidence=confidence,
        reasoning="test",
        model_id="test",
        generated_at=generated_at or _TS,
    )


def _make_signals_df(
    symbols: list[str],
    scores: list[float] | None = None,
    confidences: list[float] | None = None,
    generated_at: datetime | None = None,
) -> pd.DataFrame:
    n = len(symbols)
    ts = generated_at or _TS
    return pd.DataFrame(
        {
            "symbol": symbols,
            "score": scores or [0.6] * n,
            "confidence": confidences or [0.8] * n,
            "reasoning": ["test"] * n,
            "model_id": ["test_model"] * n,
            "ensemble_std": [0.0] * n,
            "fallback_used": [False] * n,
            "generated_at": [ts] * n,
        }
    )


def _mock_market(*symbols_prices: tuple[str, float]) -> MagicMock:
    market = MagicMock()
    price_map = dict(symbols_prices)
    market.price_of.side_effect = lambda s: price_map.get(s)
    return market


def _mock_data_replay() -> MagicMock:
    return MagicMock()


def _portfolio_with_position(symbol: str, qty: float, price: float) -> VirtualPortfolio:
    p = VirtualPortfolio(initial_cash=100_000.0)
    p.apply_fill(
        Fill(
            fill_id=str(uuid.uuid4()),
            order_id=str(uuid.uuid4()),
            timestamp=_TS,
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=qty,
            fill_price=price,
            commission=0.0,
            slippage_bps=0.0,
            strategy_id="S4",
        )
    )
    return p


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_default_config(self) -> None:
        cfg = S4Config()
        strat = NewsDrivenTactical(cfg)
        assert strat._config is cfg
        assert strat._signals_df is None
        assert strat._last_rebalance is None

    def test_with_signals_df(self) -> None:
        df = _make_signals_df(["AAPL", "MSFT", "GOOG"])
        strat = NewsDrivenTactical(S4Config(), signals=df)
        assert strat._signals_df is not None
        assert len(strat._signals_df) == 3

    def test_health_check_always_true(self) -> None:
        assert NewsDrivenTactical(S4Config()).health_check() is True
        assert NewsDrivenTactical(S4Config(), signals=pd.DataFrame()).health_check() is True


# ---------------------------------------------------------------------------
# compute_target_weights
# ---------------------------------------------------------------------------


class TestComputeTargetWeights:
    def test_returns_dict(self) -> None:
        signals = [_sig(f"T{i:02d}") for i in range(5)]
        strat = NewsDrivenTactical(S4Config())
        result = strat.compute_target_weights(signals, as_of=_TS)
        assert isinstance(result, dict)

    def test_correct_weights_for_top5(self) -> None:
        # 5 signals with sufficient confidence/score → all 5 selected, equal weights
        signals = [_sig(f"T{i:02d}", score=0.6 - i * 0.01) for i in range(5)]
        cfg = S4Config(n_top=5, bucket_pct=0.10, min_stocks=3)
        strat = NewsDrivenTactical(cfg)
        weights = strat.compute_target_weights(signals, as_of=_TS)
        assert len(weights) == 5
        expected_wt = 1.0 / 5  # sleeve-local weights sum to 1.0
        for w in weights.values():
            assert abs(w - expected_wt) < 1e-9

    def test_returns_empty_when_too_few_signals_pass_filter(self) -> None:
        # Only 2 signals pass, min_stocks=3 → empty result
        signals = [_sig("A", score=0.5, confidence=0.8), _sig("B", score=0.5, confidence=0.8)]
        cfg = S4Config(min_stocks=3)
        strat = NewsDrivenTactical(cfg)
        weights = strat.compute_target_weights(signals, as_of=_TS)
        assert weights == {}

    def test_negative_score_excluded(self) -> None:
        # S4 is long-only: negative effective_strength filtered out
        signals = [
            _sig("A", score=-0.8, confidence=0.9),
            _sig("B", score=0.6, confidence=0.8),
            _sig("C", score=0.5, confidence=0.8),
            _sig("D", score=0.5, confidence=0.8),
        ]
        cfg = S4Config(min_stocks=3, n_top=5)
        strat = NewsDrivenTactical(cfg)
        weights = strat.compute_target_weights(signals, as_of=_TS)
        assert "A" not in weights

    def test_returns_empty_when_no_signals(self) -> None:
        strat = NewsDrivenTactical(S4Config())
        assert strat.compute_target_weights([], as_of=_TS) == {}


# ---------------------------------------------------------------------------
# __call__ — no orders when no signals
# ---------------------------------------------------------------------------


class TestCallNoSignals:
    def test_empty_list_when_no_signals_df(self) -> None:
        strat = NewsDrivenTactical(S4Config())
        portfolio = VirtualPortfolio(initial_cash=100_000.0)
        market = _mock_market()
        result = strat(_TS, _mock_data_replay(), portfolio, market)
        assert result == []

    def test_empty_list_when_signals_do_not_pass_filter(self) -> None:
        # Only 2 low-confidence signals → below min_stocks=3
        df = _make_signals_df(
            ["AAPL", "MSFT"],
            confidences=[0.1, 0.1],  # below min_confidence=0.3
        )
        strat = NewsDrivenTactical(S4Config(), signals=df)
        portfolio = VirtualPortfolio(initial_cash=100_000.0)
        market = _mock_market()
        result = strat(_TS, _mock_data_replay(), portfolio, market)
        assert result == []


# ---------------------------------------------------------------------------
# __call__ — BUY orders for top-ranked tickers
# ---------------------------------------------------------------------------


class TestCallBuyOrders:
    def test_buy_orders_generated_for_top_tickers(self) -> None:
        symbols = [f"T{i:02d}" for i in range(5)]
        df = _make_signals_df(symbols)
        strat = NewsDrivenTactical(S4Config(n_top=5, bucket_pct=0.10, min_stocks=3), signals=df)
        portfolio = VirtualPortfolio(initial_cash=100_000.0)
        market = _mock_market(*[(s, 50.0) for s in symbols])

        orders = strat(_TS, _mock_data_replay(), portfolio, market)

        buy_symbols = {o.symbol for o in orders if o.side == OrderSide.BUY}
        assert buy_symbols == set(symbols)

    def test_buy_order_quantities_proportional_to_weights(self) -> None:
        symbols = ["AAPL", "MSFT", "GOOG", "AMZN", "META"]
        df = _make_signals_df(symbols)
        cfg = S4Config(n_top=5, bucket_pct=0.10, min_stocks=3)
        strat = NewsDrivenTactical(cfg, signals=df)
        portfolio = VirtualPortfolio(initial_cash=100_000.0)
        price = 100.0
        market = _mock_market(*[(s, price) for s in symbols])

        orders = strat(_TS, _mock_data_replay(), portfolio, market)

        buy_orders = [o for o in orders if o.side == OrderSide.BUY]
        nav = 100_000.0
        expected_qty = (nav * (1.0 / 5)) / price  # sleeve-local weights sum to 1.0
        for o in buy_orders:
            assert abs(o.quantity - expected_qty) < 1e-4

    def test_orders_are_order_instances(self) -> None:
        df = _make_signals_df([f"T{i:02d}" for i in range(5)])
        strat = NewsDrivenTactical(S4Config(), signals=df)
        portfolio = VirtualPortfolio(initial_cash=100_000.0)
        market = _mock_market(*[(f"T{i:02d}", 50.0) for i in range(5)])
        orders = strat(_TS, _mock_data_replay(), portfolio, market)
        assert all(isinstance(o, Order) for o in orders)

    def test_no_buy_when_price_unavailable(self) -> None:
        symbols = [f"T{i:02d}" for i in range(5)]
        df = _make_signals_df(symbols)
        strat = NewsDrivenTactical(S4Config(), signals=df)
        portfolio = VirtualPortfolio(initial_cash=100_000.0)
        # No prices in market → price_of returns None
        market = _mock_market()
        orders = strat(_TS, _mock_data_replay(), portfolio, market)
        buy_orders = [o for o in orders if o.side == OrderSide.BUY]
        assert buy_orders == []


# ---------------------------------------------------------------------------
# __call__ — SELL orders for out-of-target positions
# ---------------------------------------------------------------------------


class TestCallSellOrders:
    def test_sell_order_for_held_position_not_in_target(self) -> None:
        # Hold "OLD" stock; new signals don't include it → SELL
        symbols = [f"T{i:02d}" for i in range(5)]
        df = _make_signals_df(symbols)
        strat = NewsDrivenTactical(S4Config(n_top=5, bucket_pct=0.10, min_stocks=3), signals=df)

        portfolio = _portfolio_with_position("OLD", qty=10.0, price=50.0)
        market = _mock_market(*[(s, 50.0) for s in symbols] + [("OLD", 55.0)])

        orders = strat(_TS, _mock_data_replay(), portfolio, market)

        sell_orders = [o for o in orders if o.side == OrderSide.SELL and o.symbol == "OLD"]
        assert len(sell_orders) == 1
        assert abs(sell_orders[0].quantity - 10.0) < 1e-6

    def test_no_sell_when_position_in_target(self) -> None:
        symbols = [f"T{i:02d}" for i in range(5)]
        df = _make_signals_df(symbols)
        strat = NewsDrivenTactical(S4Config(n_top=5, bucket_pct=0.10, min_stocks=3), signals=df)

        # Already hold T00 (which will be in target) at correct qty
        nav = 100_000.0
        price = 100.0
        expected_qty = (nav * (0.10 / 5)) / price
        portfolio = _portfolio_with_position("T00", qty=expected_qty, price=price)
        market = _mock_market(*[(s, price) for s in symbols])

        orders = strat(_TS, _mock_data_replay(), portfolio, market)

        sell_symbols = {o.symbol for o in orders if o.side == OrderSide.SELL}
        assert "T00" not in sell_symbols


# ---------------------------------------------------------------------------
# Strategy ID
# ---------------------------------------------------------------------------


class TestStrategyId:
    def test_strategy_id_on_buy_orders(self) -> None:
        df = _make_signals_df([f"T{i:02d}" for i in range(5)])
        cfg = S4Config(strategy_id="S4_TEST")
        strat = NewsDrivenTactical(cfg, signals=df)
        portfolio = VirtualPortfolio(initial_cash=100_000.0)
        market = _mock_market(*[(f"T{i:02d}", 50.0) for i in range(5)])

        orders = strat(_TS, _mock_data_replay(), portfolio, market)

        for o in orders:
            assert o.strategy_id == "S4_TEST"

    def test_strategy_id_on_sell_orders(self) -> None:
        df = _make_signals_df([f"T{i:02d}" for i in range(5)])
        cfg = S4Config(strategy_id="S4_TEST")
        strat = NewsDrivenTactical(cfg, signals=df)
        portfolio = _portfolio_with_position("OLD", qty=5.0, price=50.0)
        market = _mock_market(
            *[(f"T{i:02d}", 50.0) for i in range(5)] + [("OLD", 50.0)]
        )

        orders = strat(_TS, _mock_data_replay(), portfolio, market)

        sell_orders = [o for o in orders if o.side == OrderSide.SELL]
        assert all(o.strategy_id == "S4_TEST" for o in sell_orders)


# ---------------------------------------------------------------------------
# Rebalance frequency (WEEKLY)
# ---------------------------------------------------------------------------


class TestRebalanceFrequency:
    def test_first_call_always_rebalances(self) -> None:
        df = _make_signals_df([f"T{i:02d}" for i in range(5)])
        strat = NewsDrivenTactical(S4Config(), signals=df)
        portfolio = VirtualPortfolio(initial_cash=100_000.0)
        market = _mock_market(*[(f"T{i:02d}", 50.0) for i in range(5)])

        orders = strat(_TS, _mock_data_replay(), portfolio, market)
        assert len(orders) > 0

    def test_same_week_call_returns_no_orders(self) -> None:
        # Default S4Config is DAILY — use WEEKLY explicitly to test weekly gate.
        df = _make_signals_df([f"T{i:02d}" for i in range(5)])
        cfg = S4Config(rebalance_frequency=RebalanceFrequency.WEEKLY)
        strat = NewsDrivenTactical(cfg, signals=df)
        portfolio = VirtualPortfolio(initial_cash=100_000.0)
        market1 = _mock_market(*[(f"T{i:02d}", 50.0) for i in range(5)])
        market2 = _mock_market(*[(f"T{i:02d}", 50.0) for i in range(5)])

        strat(_TS, _mock_data_replay(), portfolio, market1)
        orders = strat(_TS_SAME_WEEK, _mock_data_replay(), portfolio, market2)
        assert orders == []

    def test_next_week_call_rebalances(self) -> None:
        # Use WEEKLY explicitly so this test is independent of config defaults.
        df = _make_signals_df([f"T{i:02d}" for i in range(5)])
        cfg = S4Config(rebalance_frequency=RebalanceFrequency.WEEKLY)
        strat = NewsDrivenTactical(cfg, signals=df)
        portfolio = VirtualPortfolio(initial_cash=100_000.0)
        market1 = _mock_market(*[(f"T{i:02d}", 50.0) for i in range(5)])
        market2 = _mock_market(*[(f"T{i:02d}", 50.0) for i in range(5)])

        strat(_TS, _mock_data_replay(), portfolio, market1)
        orders = strat(_TS_NEXT_WEEK, _mock_data_replay(), portfolio, market2)
        assert strat._last_rebalance == _TS_NEXT_WEEK

    def test_daily_frequency_rebalances_every_call(self) -> None:
        df = _make_signals_df([f"T{i:02d}" for i in range(5)])
        cfg = S4Config(rebalance_frequency=RebalanceFrequency.DAILY)
        strat = NewsDrivenTactical(cfg, signals=df)
        portfolio = VirtualPortfolio(initial_cash=100_000.0)
        market = _mock_market(*[(f"T{i:02d}", 50.0) for i in range(5)])

        strat(_TS, _mock_data_replay(), portfolio, market)
        strat(_TS_SAME_WEEK, _mock_data_replay(), portfolio, market)
        assert strat._last_rebalance == _TS_SAME_WEEK


# ---------------------------------------------------------------------------
# Signal time-filtering (_signals_as_of)
# ---------------------------------------------------------------------------


class TestSignalTimeFiltering:
    def test_future_signals_excluded(self) -> None:
        future_ts = datetime(2024, 1, 15, tzinfo=timezone.utc)
        df = _make_signals_df(
            [f"T{i:02d}" for i in range(5)],
            generated_at=future_ts,
        )
        strat = NewsDrivenTactical(S4Config(), signals=df)
        portfolio = VirtualPortfolio(initial_cash=100_000.0)
        market = _mock_market(*[(f"T{i:02d}", 50.0) for i in range(5)])

        # ts is before generated_at → signals filtered out → no orders
        orders = strat(_TS, _mock_data_replay(), portfolio, market)
        assert orders == []

    def test_past_signals_included(self) -> None:
        # QS-07: past signals WITHIN the freshness window (max_signal_age_hours) are
        # included; staler ones are now dropped (backtest/live parity). 2h before _TS.
        past_ts = datetime(2024, 1, 7, 22, 0, tzinfo=timezone.utc)
        df = _make_signals_df(
            [f"T{i:02d}" for i in range(5)],
            generated_at=past_ts,
        )
        strat = NewsDrivenTactical(S4Config(), signals=df)
        portfolio = VirtualPortfolio(initial_cash=100_000.0)
        market = _mock_market(*[(f"T{i:02d}", 50.0) for i in range(5)])

        orders = strat(_TS, _mock_data_replay(), portfolio, market)
        buy_orders = [o for o in orders if o.side == OrderSide.BUY]
        assert len(buy_orders) > 0


# ---------------------------------------------------------------------------
# Public rebalance gate (should_rebalance / mark_rebalanced)
# ---------------------------------------------------------------------------


def test_s4_should_rebalance_true_on_first_call():
    from src.strategies.s4.strategy import NewsDrivenTactical
    from src.strategies.s4.config import S4Config
    from src.backtest.engine.types import RebalanceFrequency
    from datetime import datetime, timezone

    s4 = NewsDrivenTactical(S4Config(rebalance_frequency=RebalanceFrequency.WEEKLY))
    ts = datetime(2025, 6, 2, tzinfo=timezone.utc)
    assert s4.should_rebalance(ts) is True


def test_s4_should_rebalance_false_within_same_week():
    from src.strategies.s4.strategy import NewsDrivenTactical
    from src.strategies.s4.config import S4Config
    from src.backtest.engine.types import RebalanceFrequency
    from datetime import datetime, timezone

    s4 = NewsDrivenTactical(S4Config(rebalance_frequency=RebalanceFrequency.WEEKLY))
    s4.mark_rebalanced(datetime(2025, 6, 2, tzinfo=timezone.utc))
    ts = datetime(2025, 6, 4, tzinfo=timezone.utc)
    assert s4.should_rebalance(ts) is False


def test_s4_should_rebalance_true_next_week():
    from src.strategies.s4.strategy import NewsDrivenTactical
    from src.strategies.s4.config import S4Config
    from src.backtest.engine.types import RebalanceFrequency
    from datetime import datetime, timezone

    s4 = NewsDrivenTactical(S4Config(rebalance_frequency=RebalanceFrequency.WEEKLY))
    s4.mark_rebalanced(datetime(2025, 6, 2, tzinfo=timezone.utc))
    ts = datetime(2025, 6, 9, tzinfo=timezone.utc)
    assert s4.should_rebalance(ts) is True
