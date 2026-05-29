"""ANTI-LOOK-AHEAD TEST SUITE. Critical.

These tests guarantee that the backtest engine NEVER reads future data.
If any of these fail, the backtest engine is invalidated and no strategy
can be considered validated until they pass.
"""
import pandas as pd
import pytest

from src.backtest.engine.data_replay import DataReplay
from src.backtest.engine.orchestrator import BacktestConfig, BacktestOrchestrator


SENTINEL_VALUE = -999_999.0


def make_prices_with_future_sentinel() -> pd.DataFrame:
    """Normal prices + sentinel value on future dates.

    If a strategy ever reads SENTINEL_VALUE, it indicates look-ahead leakage.
    """
    dates = pd.date_range("2023-01-02", "2023-12-29", freq="B")
    normal_prices = [100.0 + i * 0.1 for i in range(len(dates))]

    # Sentinel: last 50% of the period has value SENTINEL_VALUE.
    # If the strategy "sees" these prices before reaching those dates, it's a bug.
    mid = len(dates) // 2
    sentinel_prices = list(normal_prices[:mid]) + [SENTINEL_VALUE] * (len(dates) - mid)

    return pd.DataFrame({"TEST": sentinel_prices}, index=dates)


class TestAntiLookahead:
    def test_data_replay_does_not_expose_future_data(self) -> None:
        """prices_until(t) must contain only prices with index <= t."""
        prices = make_prices_with_future_sentinel()
        replay = DataReplay(prices)

        cutoff = prices.index[100]
        history = replay.prices_until(cutoff)

        assert history.index.max() == cutoff
        assert (history["TEST"] != SENTINEL_VALUE).all(), (
            "prices_until is returning future sentinel data!"
        )

    def test_market_at_is_point_in_time(self) -> None:
        """market_at(t) returns the state AT t, not beyond."""
        prices = make_prices_with_future_sentinel()
        replay = DataReplay(prices)

        # Read at t = 50 (well before sentinel kicks in at t = 130)
        ts = prices.index[50]
        market = replay.market_at(ts)

        assert market.timestamp == ts
        assert market.price_of("TEST") != SENTINEL_VALUE

    def test_strategy_cannot_see_future_in_orchestrator(self) -> None:
        """A strategy during backtest receives only point-in-time data.

        When the orchestrator is at timestep t < sentinel_start, prices_until(t)
        must not contain any sentinel values. Once t >= sentinel_start the sentinel
        IS the current price and seeing it is correct — that is not look-ahead.
        """
        prices = make_prices_with_future_sentinel()
        replay = DataReplay(prices)

        mid = len(prices) // 2
        sentinel_start_ts = prices.index[mid]

        premature_sentinel: list = []

        def sentinel_detector(ts, data_replay, portfolio, market):
            if ts < sentinel_start_ts:
                history = data_replay.prices_until(ts)
                if (history["TEST"] == SENTINEL_VALUE).any():
                    premature_sentinel.append(ts)
            return []

        orchestrator = BacktestOrchestrator(BacktestConfig(initial_capital=100_000))
        orchestrator.run(replay, sentinel_detector)

        assert premature_sentinel == [], (
            f"Strategy saw future sentinel before sentinel date: {premature_sentinel[:5]}"
        )

    def test_returns_until_does_not_use_future(self) -> None:
        """returns_until(t) must not include returns computed from future prices."""
        prices = make_prices_with_future_sentinel()
        replay = DataReplay(prices)

        cutoff = prices.index[100]
        returns = replay.returns_until(cutoff)

        assert returns.index.max() <= cutoff
        # A return that uses the sentinel as numerator would be massively negative
        assert not (returns["TEST"] < -0.99).any(), (
            "returns_until is contaminated by future sentinel"
        )

    def test_timesteps_returned_in_order(self) -> None:
        """Sanity: timesteps must be sorted ascending."""
        prices = make_prices_with_future_sentinel()
        replay = DataReplay(prices)

        timesteps = replay.timesteps()
        for i in range(1, len(timesteps)):
            assert timesteps[i] > timesteps[i - 1], (
                f"Timesteps not sorted at index {i}"
            )

    def test_prices_until_boundary_is_inclusive(self) -> None:
        """prices_until(t) must include t itself (inclusive upper bound)."""
        prices = make_prices_with_future_sentinel()
        replay = DataReplay(prices)

        cutoff = prices.index[50]
        history = replay.prices_until(cutoff)

        assert cutoff in history.index

    def test_market_at_does_not_see_next_day_price(self) -> None:
        """market_at(t) price must equal the price on date t, not t+1."""
        dates = pd.date_range("2023-01-02", periods=10, freq="B")
        # Price jumps dramatically on day 5 — if look-ahead, day 4 market would show high price
        prices_values = [100.0] * 4 + [SENTINEL_VALUE] * 6
        prices = pd.DataFrame({"SPY": prices_values}, index=dates)
        replay = DataReplay(prices)

        market = replay.market_at(dates[3])  # last normal day
        assert market.price_of("SPY") == pytest.approx(100.0), (
            "market_at is leaking next-day sentinel price"
        )


class TestAntiLookaheadRegression:
    def test_rolling_indicator_uses_only_history(self) -> None:
        """Bug pattern: rolling indicator computed on FULL series instead of history.

        A strategy computing a 20d MA at timestep t must use
        prices_until(t).rolling(20).mean(), NOT prices.rolling(20).mean().
        """
        prices = make_prices_with_future_sentinel()
        replay = DataReplay(prices)

        # Evaluate at t=50, well before sentinel at t=130
        ts = prices.index[50]

        correct_history = replay.prices_until(ts)
        correct_ma = correct_history["TEST"].rolling(20).mean().iloc[-1]

        assert correct_ma != SENTINEL_VALUE
        assert not pd.isna(correct_ma)
        # MA of normal prices around index 50 (value ≈ 100 + 50*0.1 = 105, window avg ~103)
        assert 90.0 < correct_ma < 120.0

    def test_negative_shift_exposes_future(self) -> None:
        """Demonstrate that shift(-1) on full series leaks future data.

        This test documents a known bad pattern rather than asserting engine
        behavior — it shows the footgun that prices_until() prevents.
        """
        prices = make_prices_with_future_sentinel()
        mid = len(prices) // 2
        # A naive shift(-1) on full series: at index mid-1, the value is from mid (sentinel)
        shifted = prices["TEST"].shift(-1)
        sentinel_leaked = shifted.iloc[mid - 1] == SENTINEL_VALUE
        assert sentinel_leaked, (
            "shift(-1) on full series should expose future sentinel — "
            "this confirms why strategies must use prices_until() instead"
        )

    def test_orchestrator_market_snapshot_is_not_future(self) -> None:
        """The MarketSnapshot passed to the strategy at timestep t must not contain future prices."""
        prices = make_prices_with_future_sentinel()
        replay = DataReplay(prices)
        mid = len(prices) // 2

        future_prices_seen: list = []

        def sentinel_market_checker(ts, data_replay, portfolio, market):
            if market.price_of("TEST") == SENTINEL_VALUE:
                future_prices_seen.append(ts)
            return []

        orchestrator = BacktestOrchestrator(BacktestConfig(initial_capital=100_000))
        orchestrator.run(replay, sentinel_market_checker)

        # The sentinel appears in the second half — the strategy IS allowed to see
        # it at those timestamps (that's point-in-time correct). The invariant is
        # that the strategy must NOT see sentinel before mid.
        pre_mid_violations = [
            ts for ts in future_prices_seen if prices.index.get_loc(ts) < mid
        ]
        assert pre_mid_violations == [], (
            f"Strategy received sentinel price before sentinel date: {pre_mid_violations[:3]}"
        )
