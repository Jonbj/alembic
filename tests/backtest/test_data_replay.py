"""Tests for DataReplay point-in-time enforcement."""
import pandas as pd
import pytest

from src.backtest.engine.data_replay import DataReplay


def make_prices(n: int = 10, start: str = "2023-01-02") -> pd.DataFrame:
    dates = pd.date_range(start, periods=n, freq="B")
    return pd.DataFrame(
        {"SPY": [400.0 + i for i in range(n)]},
        index=dates,
    )


def make_volumes(n: int = 10, start: str = "2023-01-02") -> pd.DataFrame:
    dates = pd.date_range(start, periods=n, freq="B")
    return pd.DataFrame({"SPY": [1_000_000.0] * n}, index=dates)


class TestDataReplayConstruction:
    def test_rejects_non_datetime_index(self) -> None:
        df = pd.DataFrame({"SPY": [1.0, 2.0]}, index=[0, 1])
        with pytest.raises(ValueError, match="DatetimeIndex"):
            DataReplay(df)

    def test_timesteps_sorted(self) -> None:
        prices = make_prices(5)
        replay = DataReplay(prices)
        ts = replay.timesteps()
        for i in range(1, len(ts)):
            assert ts[i] > ts[i - 1]

    def test_first_last_timestep(self) -> None:
        prices = make_prices(5)
        replay = DataReplay(prices)
        assert replay.first_timestep() == prices.index[0]
        assert replay.last_timestep() == prices.index[-1]


class TestDataReplayPricesUntil:
    def test_prices_until_excludes_future(self) -> None:
        prices = make_prices(10)
        replay = DataReplay(prices)

        cutoff = prices.index[4]
        history = replay.prices_until(cutoff)

        assert history.index.max() == cutoff
        assert len(history) == 5

    def test_prices_until_all_past(self) -> None:
        prices = make_prices(10)
        replay = DataReplay(prices)

        history = replay.prices_until(prices.index[-1])
        assert len(history) == 10

    def test_returns_until_excludes_future(self) -> None:
        prices = make_prices(10)
        replay = DataReplay(prices)

        cutoff = prices.index[5]
        returns = replay.returns_until(cutoff)

        assert returns.index.max() <= cutoff
        assert len(returns) > 0


class TestDataReplayMarketAt:
    def test_market_at_exact_timestamp(self) -> None:
        prices = make_prices(5)
        replay = DataReplay(prices)

        ts = prices.index[2]
        market = replay.market_at(ts)

        assert market.timestamp == ts
        assert market.price_of("SPY") == pytest.approx(402.0)

    def test_market_at_nearest_preceding_when_missing(self) -> None:
        prices = make_prices(5)
        replay = DataReplay(prices)

        # Ask for a time between two timesteps
        between = prices.index[2] + pd.Timedelta(hours=12)
        market = replay.market_at(between)

        assert market.timestamp == prices.index[2]

    def test_market_at_before_data_raises(self) -> None:
        prices = make_prices(5)
        replay = DataReplay(prices)

        before = prices.index[0] - pd.Timedelta(days=10)
        with pytest.raises(ValueError):
            replay.market_at(before)

    def test_market_with_volumes(self) -> None:
        prices = make_prices(25)
        volumes = make_volumes(25)
        replay = DataReplay(prices, volumes)

        ts = prices.index[-1]
        market = replay.market_at(ts)
        assert market.volumes.get("SPY", 0) > 0

    def test_market_adv_defaults_without_volumes(self) -> None:
        prices = make_prices(5)
        replay = DataReplay(prices)

        market = replay.market_at(prices.index[-1])
        assert market.adv_20d.get("SPY") == 500_000.0

    def test_market_adv_computed_with_volumes(self) -> None:
        prices = make_prices(25)
        volumes = make_volumes(25)
        replay = DataReplay(prices, volumes)

        market = replay.market_at(prices.index[-1])
        # adv_20d should be 1_000_000 (constant volume)
        assert market.adv_20d.get("SPY") == pytest.approx(1_000_000.0)
