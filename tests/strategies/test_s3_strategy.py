"""T-203: S3 CrossSectionalMomentum strategy module tests."""
from __future__ import annotations

import uuid

import numpy as np
import pandas as pd
import pytest

from src.backtest.engine.data_replay import DataReplay
from src.backtest.engine.portfolio import VirtualPortfolio
from src.backtest.engine.types import Fill, Order, OrderSide, RebalanceFrequency
from src.strategies.s3.strategy import S3Config, CrossSectionalMomentum


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

N = 600  # enough for lookback=252 + beta_window=252 + margin


def _make_prices(n: int = N, seed: int = 42, n_stocks: int = 15) -> pd.DataFrame:
    """Synthetic prices: SPY + n_stocks with varying trends."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2018-01-01", periods=n, freq="B")

    spy = 300 * np.exp(np.cumsum(rng.normal(0.0004, 0.008, n)))
    data = {"SPY": spy}

    for i in range(n_stocks):
        # vary drift to create spread in residual momentum
        drift = rng.uniform(-0.001, 0.002)
        beta = rng.uniform(0.5, 1.5)
        idio = rng.normal(0, 0.005, n)
        log_ret = beta * np.log(spy / np.concatenate([[spy[0]], spy[:-1]])) + idio + drift
        data[f"T{i+1:02d}"] = 100 * np.exp(np.cumsum(log_ret))

    return pd.DataFrame(data, index=dates)


@pytest.fixture
def prices() -> pd.DataFrame:
    return _make_prices()


@pytest.fixture
def short_prices() -> pd.DataFrame:
    """Only 200 days — insufficient for valid signals (needs > 252+252)."""
    return _make_prices(n=200, n_stocks=15)


@pytest.fixture
def config() -> S3Config:
    return S3Config()


@pytest.fixture
def strategy(prices: pd.DataFrame, config: S3Config) -> CrossSectionalMomentum:
    return CrossSectionalMomentum(prices, config)


@pytest.fixture
def data_replay(prices: pd.DataFrame) -> DataReplay:
    return DataReplay(prices)


@pytest.fixture
def last_ts(strategy: CrossSectionalMomentum):
    return strategy._rank_wide.index[-1]


@pytest.fixture
def first_signal_ts(strategy: CrossSectionalMomentum):
    return strategy._rank_wide.index[0]


@pytest.fixture
def market(data_replay: DataReplay, last_ts):
    return data_replay.market_at(last_ts)


@pytest.fixture
def empty_portfolio() -> VirtualPortfolio:
    return VirtualPortfolio(initial_cash=100_000.0)


# ---------------------------------------------------------------------------
# S3Config
# ---------------------------------------------------------------------------


class TestS3Config:
    def test_default_values(self) -> None:
        cfg = S3Config()
        assert cfg.strategy_id == "S3"
        assert cfg.lookback == 252
        assert cfg.beta_window == 252
        assert cfg.n_deciles == 10
        assert cfg.long_decile == 10
        assert cfg.short_decile == 1
        assert cfg.rebalance_frequency == RebalanceFrequency.MONTHLY

    def test_long_only_config(self) -> None:
        cfg = S3Config(short_decile=None)
        assert cfg.short_decile is None


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    def test_passes_with_sufficient_history(
        self, strategy: CrossSectionalMomentum
    ) -> None:
        assert strategy.health_check() is True

    def test_fails_with_too_short_history(
        self, short_prices: pd.DataFrame, config: S3Config
    ) -> None:
        strat = CrossSectionalMomentum(short_prices, config)
        assert strat.health_check() is False


# ---------------------------------------------------------------------------
# compute_target_weights
# ---------------------------------------------------------------------------


class TestComputeTargetWeights:
    def test_returns_dict(
        self, strategy: CrossSectionalMomentum, prices: pd.DataFrame
    ) -> None:
        result = strategy.compute_target_weights(prices)
        assert isinstance(result, dict)

    def test_long_positions_have_positive_weight(
        self, strategy: CrossSectionalMomentum, prices: pd.DataFrame
    ) -> None:
        result = strategy.compute_target_weights(prices)
        long_weights = {k: v for k, v in result.items() if v > 0}
        assert len(long_weights) > 0

    def test_short_positions_have_negative_weight(
        self, strategy: CrossSectionalMomentum, prices: pd.DataFrame
    ) -> None:
        result = strategy.compute_target_weights(prices)
        short_weights = {k: v for k, v in result.items() if v < 0}
        assert len(short_weights) > 0

    def test_weights_respect_max_weight(
        self, strategy: CrossSectionalMomentum, prices: pd.DataFrame
    ) -> None:
        result = strategy.compute_target_weights(prices)
        for w in result.values():
            assert abs(w) <= strategy._config.max_weight + 1e-9

    def test_long_only_no_short_positions(
        self, prices: pd.DataFrame
    ) -> None:
        cfg = S3Config(short_decile=None)
        strat = CrossSectionalMomentum(prices, cfg)
        result = strat.compute_target_weights(prices)
        assert all(v >= 0 for v in result.values())

    def test_returns_empty_when_history_too_short(
        self, short_prices: pd.DataFrame, config: S3Config
    ) -> None:
        strat = CrossSectionalMomentum(short_prices, config)
        assert strat.compute_target_weights(short_prices) == {}

    def test_spy_not_in_weights(
        self, strategy: CrossSectionalMomentum, prices: pd.DataFrame
    ) -> None:
        result = strategy.compute_target_weights(prices)
        assert "SPY" not in result


# ---------------------------------------------------------------------------
# Strategy callable interface
# ---------------------------------------------------------------------------


class TestStrategyCallableInterface:
    def test_returns_list(
        self,
        strategy: CrossSectionalMomentum,
        last_ts,
        data_replay: DataReplay,
        empty_portfolio: VirtualPortfolio,
        market,
    ) -> None:
        result = strategy(last_ts, data_replay, empty_portfolio, market)
        assert isinstance(result, list)

    def test_elements_are_order_instances(
        self,
        strategy: CrossSectionalMomentum,
        last_ts,
        data_replay: DataReplay,
        empty_portfolio: VirtualPortfolio,
        market,
    ) -> None:
        result = strategy(last_ts, data_replay, empty_portfolio, market)
        assert all(isinstance(o, Order) for o in result)

    def test_orders_have_correct_strategy_id(
        self,
        strategy: CrossSectionalMomentum,
        last_ts,
        data_replay: DataReplay,
        empty_portfolio: VirtualPortfolio,
        market,
    ) -> None:
        orders = strategy(last_ts, data_replay, empty_portfolio, market)
        for o in orders:
            assert o.strategy_id == "S3"


# ---------------------------------------------------------------------------
# Rebalance timing (MONTHLY)
# ---------------------------------------------------------------------------


class TestRebalanceTiming:
    def test_first_call_always_rebalances(
        self,
        strategy: CrossSectionalMomentum,
        first_signal_ts,
        data_replay: DataReplay,
        empty_portfolio: VirtualPortfolio,
    ) -> None:
        market = data_replay.market_at(first_signal_ts)
        orders = strategy(first_signal_ts, data_replay, empty_portfolio, market)
        assert len(orders) > 0

    def test_same_month_call_returns_no_orders(
        self,
        strategy: CrossSectionalMomentum,
        first_signal_ts,
        data_replay: DataReplay,
        empty_portfolio: VirtualPortfolio,
    ) -> None:
        idx = strategy._rank_wide.index
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
        strategy: CrossSectionalMomentum,
        first_signal_ts,
        data_replay: DataReplay,
        empty_portfolio: VirtualPortfolio,
    ) -> None:
        idx = strategy._rank_wide.index
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
        assert len(orders) > 0

    def test_daily_frequency_rebalances_every_call(
        self,
        prices: pd.DataFrame,
        first_signal_ts,
        data_replay: DataReplay,
    ) -> None:
        config = S3Config(rebalance_frequency=RebalanceFrequency.DAILY)
        strat = CrossSectionalMomentum(prices, config)

        idx = strat._rank_wide.index
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
        strat(ts2, data_replay, portfolio, market2)
        assert strat._last_rebalance == ts2
