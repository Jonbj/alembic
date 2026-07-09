"""T-103: S1 TimeSeriesMomentum strategy module tests."""
from __future__ import annotations

import uuid
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.backtest.engine.data_replay import DataReplay
from src.backtest.engine.portfolio import VirtualPortfolio
from src.backtest.engine.types import Fill, Order, OrderSide, RebalanceFrequency
from src.strategies.s1.strategy import S1Config, TimeSeriesMomentum


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

N = 400


@pytest.fixture
def prices() -> pd.DataFrame:
    """400 business days: A strong uptrend, B strong downtrend."""
    rng = np.random.default_rng(42)
    dates = pd.date_range("2020-01-01", periods=N, freq="B")
    a = 100 * np.exp(np.cumsum(rng.normal(0.0015, 0.008, N)))
    b = 100 * np.exp(np.cumsum(rng.normal(-0.0015, 0.008, N)))
    return pd.DataFrame({"A": a, "B": b}, index=dates)


@pytest.fixture
def short_prices() -> pd.DataFrame:
    """Only 100 days — insufficient for valid signals (needs > 252)."""
    rng = np.random.default_rng(1)
    dates = pd.date_range("2020-01-01", periods=100, freq="B")
    vals = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, 100)))
    return pd.DataFrame({"A": vals, "B": vals * 1.01}, index=dates)


@pytest.fixture
def config() -> S1Config:
    return S1Config()


@pytest.fixture
def strategy(prices: pd.DataFrame, config: S1Config) -> TimeSeriesMomentum:
    return TimeSeriesMomentum(prices, config)


@pytest.fixture
def data_replay(prices: pd.DataFrame) -> DataReplay:
    return DataReplay(prices)


@pytest.fixture
def last_ts(strategy: TimeSeriesMomentum):
    """Last date with a valid precomputed signal."""
    return strategy._signal_wide.index[-1]


@pytest.fixture
def first_signal_ts(strategy: TimeSeriesMomentum):
    """First date with a valid precomputed signal."""
    return strategy._signal_wide.index[0]


@pytest.fixture
def market(data_replay: DataReplay, last_ts):
    return data_replay.market_at(last_ts)


@pytest.fixture
def empty_portfolio() -> VirtualPortfolio:
    return VirtualPortfolio(initial_cash=100_000.0)


@pytest.fixture
def portfolio_with_b(prices: pd.DataFrame) -> VirtualPortfolio:
    """Portfolio holding 10 shares of B (bought at day 300)."""
    portfolio = VirtualPortfolio(initial_cash=100_000.0)
    buy_ts = prices.index[300]
    buy_price = float(prices.loc[buy_ts, "B"])
    portfolio.apply_fill(
        Fill(
            fill_id=str(uuid.uuid4()),
            order_id=str(uuid.uuid4()),
            timestamp=buy_ts,
            symbol="B",
            side=OrderSide.BUY,
            quantity=10.0,
            fill_price=buy_price,
            commission=0.0,
            slippage_bps=0.0,
            strategy_id="S1",
        )
    )
    return portfolio


# ---------------------------------------------------------------------------
# S1Config
# ---------------------------------------------------------------------------


class TestS1Config:
    def test_default_values(self) -> None:
        cfg = S1Config()
        assert cfg.strategy_id == "S1"
        assert cfg.lookbacks == (21, 63, 126, 252)
        assert cfg.signal_threshold == 0.0
        assert cfg.rebalance_frequency == RebalanceFrequency.MONTHLY

    def test_from_yaml_custom(self, tmp_path: Path) -> None:
        content = (
            'strategy_id: "S1_TEST"\n'
            "lookbacks: [21, 63]\n"
            "vol_window_signal: 42\n"
            "vol_window_sizing: 30\n"
            "target_vol: 0.15\n"
            "max_weight: 0.25\n"
            "signal_threshold: 0.5\n"
            "rebalance_frequency: DAILY\n"
        )
        cfg_file = tmp_path / "s1.yaml"
        cfg_file.write_text(content)
        cfg = S1Config.from_yaml(cfg_file)

        assert cfg.strategy_id == "S1_TEST"
        assert cfg.lookbacks == (21, 63)
        assert cfg.vol_window_signal == 42
        assert cfg.vol_window_sizing == 30
        assert abs(cfg.target_vol - 0.15) < 1e-9
        assert abs(cfg.max_weight - 0.25) < 1e-9
        assert abs(cfg.signal_threshold - 0.5) < 1e-9
        assert cfg.rebalance_frequency == RebalanceFrequency.DAILY

    def test_from_project_yaml(self) -> None:
        cfg = S1Config.from_yaml(Path("config/s1_strategy.yaml"))
        assert cfg.strategy_id is not None
        assert len(cfg.lookbacks) > 0
        assert cfg.target_vol > 0


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    def test_passes_with_sufficient_history(self, strategy: TimeSeriesMomentum) -> None:
        assert strategy.health_check() is True

    def test_fails_with_too_short_history(
        self, short_prices: pd.DataFrame, config: S1Config
    ) -> None:
        strat = TimeSeriesMomentum(short_prices, config)
        assert strat.health_check() is False


# ---------------------------------------------------------------------------
# compute_target_weights
# ---------------------------------------------------------------------------


class TestComputeTargetWeights:
    def test_returns_dict(
        self, strategy: TimeSeriesMomentum, prices: pd.DataFrame
    ) -> None:
        result = strategy.compute_target_weights(prices)
        assert isinstance(result, dict)

    def test_uptrend_ticker_included_in_target(
        self, strategy: TimeSeriesMomentum, prices: pd.DataFrame
    ) -> None:
        result = strategy.compute_target_weights(prices)
        assert "A" in result
        assert result["A"] > 0

    def test_downtrend_ticker_excluded_from_target(
        self, strategy: TimeSeriesMomentum, prices: pd.DataFrame
    ) -> None:
        result = strategy.compute_target_weights(prices)
        assert "B" not in result

    def test_all_weights_are_positive_floats(
        self, strategy: TimeSeriesMomentum, prices: pd.DataFrame
    ) -> None:
        result = strategy.compute_target_weights(prices)
        assert all(isinstance(v, float) for v in result.values())
        assert all(v > 0 for v in result.values())

    def test_returns_empty_when_history_too_short(
        self, short_prices: pd.DataFrame, config: S1Config
    ) -> None:
        strat = TimeSeriesMomentum(short_prices, config)
        assert strat.compute_target_weights(short_prices) == {}


class TestSleeveNormalization:
    def test_weights_sum_capped_at_one(self) -> None:
        # 16 uptrending tickers → the cross-sectional z-score puts roughly half
        # above the mean (positive signal), each inverse-vol weight capped at
        # max_weight=0.20 → the sleeve sum lands well above 1.0 without
        # normalization (portfolio over-allocation before the enforcer).
        idx = pd.date_range("2023-01-02", periods=400, freq="B")
        rng = np.random.default_rng(7)
        data = {}
        for i in range(16):
            drift = 0.0008 + 0.0002 * i
            noise = rng.normal(0, 0.01, len(idx))
            data[f"T{i:02d}"] = 100 * np.exp(np.cumsum(drift + noise))
        prices = pd.DataFrame(data, index=idx)

        strat = TimeSeriesMomentum(prices=prices, config=S1Config())
        weights = strat.compute_target_weights(prices)

        assert weights, "expected non-empty target weights"
        assert sum(weights.values()) <= 1.0 + 1e-9
        assert all(w > 0 for w in weights.values())


# ---------------------------------------------------------------------------
# Strategy callable — return type
# ---------------------------------------------------------------------------


class TestStrategyCallableInterface:
    def test_returns_list(
        self,
        strategy: TimeSeriesMomentum,
        last_ts,
        data_replay: DataReplay,
        empty_portfolio: VirtualPortfolio,
        market,
    ) -> None:
        result = strategy(last_ts, data_replay, empty_portfolio, market)
        assert isinstance(result, list)

    def test_elements_are_order_instances(
        self,
        strategy: TimeSeriesMomentum,
        last_ts,
        data_replay: DataReplay,
        empty_portfolio: VirtualPortfolio,
        market,
    ) -> None:
        result = strategy(last_ts, data_replay, empty_portfolio, market)
        assert all(isinstance(o, Order) for o in result)

    def test_orders_have_correct_strategy_id(
        self,
        strategy: TimeSeriesMomentum,
        last_ts,
        data_replay: DataReplay,
        empty_portfolio: VirtualPortfolio,
        market,
    ) -> None:
        orders = strategy(last_ts, data_replay, empty_portfolio, market)
        for o in orders:
            assert o.strategy_id == "S1"


# ---------------------------------------------------------------------------
# Entry rule
# ---------------------------------------------------------------------------


class TestEntryRule:
    def test_buy_order_for_positive_signal_ticker(
        self,
        strategy: TimeSeriesMomentum,
        last_ts,
        data_replay: DataReplay,
        empty_portfolio: VirtualPortfolio,
        market,
    ) -> None:
        orders = strategy(last_ts, data_replay, empty_portfolio, market)
        buy_symbols = {o.symbol for o in orders if o.side == OrderSide.BUY}
        assert "A" in buy_symbols

    def test_no_buy_order_for_negative_signal_ticker(
        self,
        strategy: TimeSeriesMomentum,
        last_ts,
        data_replay: DataReplay,
        empty_portfolio: VirtualPortfolio,
        market,
    ) -> None:
        orders = strategy(last_ts, data_replay, empty_portfolio, market)
        buy_symbols = {o.symbol for o in orders if o.side == OrderSide.BUY}
        assert "B" not in buy_symbols


# ---------------------------------------------------------------------------
# Exit rule
# ---------------------------------------------------------------------------


class TestExitRule:
    def test_sell_order_for_held_position_with_negative_signal(
        self,
        prices: pd.DataFrame,
        config: S1Config,
        data_replay: DataReplay,
        portfolio_with_b: VirtualPortfolio,
        last_ts,
        market,
    ) -> None:
        strat = TimeSeriesMomentum(prices, config)
        orders = strat(last_ts, data_replay, portfolio_with_b, market)
        sell_symbols = {o.symbol for o in orders if o.side == OrderSide.SELL}
        assert "B" in sell_symbols

    def test_sell_quantity_matches_held_position(
        self,
        prices: pd.DataFrame,
        config: S1Config,
        data_replay: DataReplay,
        portfolio_with_b: VirtualPortfolio,
        last_ts,
        market,
    ) -> None:
        strat = TimeSeriesMomentum(prices, config)
        orders = strat(last_ts, data_replay, portfolio_with_b, market)
        sell_orders = [o for o in orders if o.symbol == "B" and o.side == OrderSide.SELL]
        assert len(sell_orders) == 1
        assert abs(sell_orders[0].quantity - 10.0) < 1e-6


# ---------------------------------------------------------------------------
# Rebalance timing (MONTHLY)
# ---------------------------------------------------------------------------


class TestRebalanceTiming:
    def test_first_call_always_rebalances(
        self,
        strategy: TimeSeriesMomentum,
        first_signal_ts,
        data_replay: DataReplay,
        empty_portfolio: VirtualPortfolio,
    ) -> None:
        market = data_replay.market_at(first_signal_ts)
        orders = strategy(first_signal_ts, data_replay, empty_portfolio, market)
        assert len(orders) > 0

    def test_same_month_call_returns_no_orders(
        self,
        strategy: TimeSeriesMomentum,
        first_signal_ts,
        data_replay: DataReplay,
        empty_portfolio: VirtualPortfolio,
    ) -> None:
        idx = strategy._signal_wide.index
        same_month = idx[
            (idx.month == first_signal_ts.month)
            & (idx.year == first_signal_ts.year)
            & (idx > first_signal_ts)
        ]
        if len(same_month) == 0:
            pytest.skip("No same-month follow-up date in signal range")
        ts2 = same_month[0]

        market1 = data_replay.market_at(first_signal_ts)
        market2 = data_replay.market_at(ts2)
        strategy(first_signal_ts, data_replay, empty_portfolio, market1)
        orders = strategy(ts2, data_replay, empty_portfolio, market2)
        assert orders == []

    def test_next_month_call_rebalances(
        self,
        strategy: TimeSeriesMomentum,
        first_signal_ts,
        data_replay: DataReplay,
        empty_portfolio: VirtualPortfolio,
    ) -> None:
        idx = strategy._signal_wide.index
        next_month = idx[
            (
                (idx.month > first_signal_ts.month) & (idx.year == first_signal_ts.year)
            )
            | (idx.year > first_signal_ts.year)
        ]
        if len(next_month) == 0:
            pytest.skip("No next-month date in signal range")
        ts_next = next_month[0]

        market1 = data_replay.market_at(first_signal_ts)
        market_next = data_replay.market_at(ts_next)
        strategy(first_signal_ts, data_replay, empty_portfolio, market1)
        orders = strategy(ts_next, data_replay, empty_portfolio, market_next)
        # Next month triggers a rebalance; empty portfolio → BUY for positive-signal ticker
        assert len(orders) > 0

    def test_daily_frequency_rebalances_every_call(
        self,
        prices: pd.DataFrame,
        first_signal_ts,
        data_replay: DataReplay,
    ) -> None:
        config = S1Config(rebalance_frequency=RebalanceFrequency.DAILY)
        strat = TimeSeriesMomentum(prices, config)

        idx = strat._signal_wide.index
        same_month = idx[
            (idx.month == first_signal_ts.month)
            & (idx.year == first_signal_ts.year)
            & (idx > first_signal_ts)
        ]
        if len(same_month) == 0:
            pytest.skip("No same-month follow-up date")
        ts2 = same_month[0]

        portfolio = VirtualPortfolio(initial_cash=100_000.0)
        market1 = data_replay.market_at(first_signal_ts)
        market2 = data_replay.market_at(ts2)

        strat(first_signal_ts, data_replay, portfolio, market1)
        orders = strat(ts2, data_replay, portfolio, market2)
        # DAILY freq means same-month call still rebalances
        assert strat._last_rebalance == ts2
