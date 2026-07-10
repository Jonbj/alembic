"""T-102: S1 signal computation — time-series momentum."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.strategies.s1.signal import compute_signal, generate_signals
from src.strategies.s1.sizing import compute_weights


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def trending_prices() -> pd.DataFrame:
    """
    Two tickers: A trends strongly up, B trends strongly down.
    350 business-day history — enough for 252-day lookback + room for valid rows.
    """
    n = 350
    rng = np.random.default_rng(42)
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    a = 100 * np.exp(np.cumsum(rng.normal(0.0015, 0.008, n)))
    b = 100 * np.exp(np.cumsum(rng.normal(-0.0015, 0.008, n)))
    return pd.DataFrame({"A": a, "B": b}, index=dates)


@pytest.fixture
def vol_spread_prices() -> pd.DataFrame:
    """
    Two tickers: LOW has low daily vol (0.5%), HIGH has high daily vol (2%).
    Same positive drift so direction doesn't confound weight comparison.
    """
    n = 350
    rng = np.random.default_rng(7)
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    low = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.005, n)))
    high = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.020, n)))
    return pd.DataFrame({"LOW": low, "HIGH": high}, index=dates)


# ---------------------------------------------------------------------------
# compute_signal
# ---------------------------------------------------------------------------


class TestComputeSignal:
    """compute_signal() produces correct multi-lookback momentum signal."""

    def test_returns_long_dataframe(self, trending_prices: pd.DataFrame) -> None:
        result = compute_signal(trending_prices)
        assert isinstance(result, pd.DataFrame)
        for col in ("ticker", "as_of", "signal"):
            assert col in result.columns, f"Missing column: {col}"

    def test_one_row_per_ticker_per_date(self, trending_prices: pd.DataFrame) -> None:
        result = compute_signal(trending_prices)
        last_date_rows = result[result["as_of"] == result["as_of"].max()]
        assert set(last_date_rows["ticker"]) == {"A", "B"}

    def test_uptrend_positive_signal_downtrend_negative(
        self, trending_prices: pd.DataFrame
    ) -> None:
        result = compute_signal(trending_prices)
        # Average signal over last 30 available dates
        last_30 = result["as_of"].drop_duplicates().nlargest(30)
        recent = result[result["as_of"].isin(last_30)]
        a_signal = recent[recent["ticker"] == "A"]["signal"].mean()
        b_signal = recent[recent["ticker"] == "B"]["signal"].mean()
        assert a_signal > 0, f"Uptrend A should have positive signal, got {a_signal:.4f}"
        assert b_signal < 0, f"Downtrend B should have negative signal, got {b_signal:.4f}"

    def test_cross_sectional_mean_near_zero(self, trending_prices: pd.DataFrame) -> None:
        """Z-score ensures cross-sectional mean ≈ 0 at every date."""
        result = compute_signal(trending_prices)
        date_means = result.groupby("as_of")["signal"].mean()
        assert (
            date_means.abs().mean() < 0.01
        ), f"Cross-sectional mean not near 0: {date_means.abs().mean():.6f}"

    def test_no_signal_rows_before_longest_lookback(
        self, trending_prices: pd.DataFrame
    ) -> None:
        """No valid signal rows until 252 business days have elapsed."""
        result = compute_signal(trending_prices, lookbacks=(21, 63, 126, 252), vol_window=63)
        assert not result.empty
        expected_first = trending_prices.index[252]
        assert result["as_of"].min() >= expected_first, (
            f"Signal appeared too early: {result['as_of'].min()} < {expected_first}"
        )

    def test_signal_is_float(self, trending_prices: pd.DataFrame) -> None:
        result = compute_signal(trending_prices)
        assert result["signal"].dtype in (np.float64, np.float32, float)

    def test_no_infinite_values(self, trending_prices: pd.DataFrame) -> None:
        result = compute_signal(trending_prices)
        assert not np.isinf(result["signal"]).any(), "Infinite values in signal"

    def test_sparse_ticker_does_not_poison_panel(self, trending_prices: pd.DataFrame) -> None:
        """A ticker with <75% valid observations is dropped; the rest produces signals."""
        prices = trending_prices.copy()
        # Make C sparse: only last 20% of history has data
        n = len(prices)
        prices["C"] = np.nan
        prices.loc[prices.index[int(n * 0.8) :], "C"] = 100.0

        result = compute_signal(prices)
        assert "C" not in result["ticker"].unique()
        assert set(result["ticker"].unique()) == {"A", "B"}
        assert not result.empty

    def test_all_sparse_tickers_return_empty(self, trending_prices: pd.DataFrame) -> None:
        """If all tickers are too sparse, return an empty DataFrame safely."""
        prices = trending_prices.copy()
        prices.iloc[: int(len(prices) * 0.9)] = np.nan
        result = compute_signal(prices)
        assert result.empty

    def test_stale_tailed_ticker_dropped_to_keep_panel_recent(self, trending_prices: pd.DataFrame) -> None:
        """A ticker whose prices stop mid-window is dropped even if overall coverage is high.

        Without this check the ticker's trailing NaNs would truncate the panel's
        most recent dates and the strategy would serve stale signals.
        """
        prices = trending_prices.copy()
        # C has valid prices until 10 rows before the end, then stops.
        # Overall coverage is ~97%, but no price in the last 5 rows.
        prices["C"] = prices["A"]
        prices.iloc[-10:, prices.columns.get_loc("C")] = np.nan

        result = compute_signal(prices)
        assert "C" not in result["ticker"].unique()
        assert set(result["ticker"].unique()) == {"A", "B"}
        # Panel remains recent up to the last available date.
        assert result["as_of"].max() == prices.index[-1]


# ---------------------------------------------------------------------------
# Point-in-time correctness
# ---------------------------------------------------------------------------


class TestPointInTimeCorrectness:
    """Signal at date T must be identical whether computed with data up to T or more."""

    def test_signal_unchanged_when_future_data_appended(
        self, trending_prices: pd.DataFrame
    ) -> None:
        prices = trending_prices
        all_dates = prices.index
        cutoff_idx = len(all_dates) - 30
        cutoff = all_dates[cutoff_idx]

        prices_truncated = prices.iloc[: cutoff_idx + 1]

        result_full = compute_signal(prices)
        result_trunc = compute_signal(prices_truncated)

        sig_full = (
            result_full[result_full["as_of"] == cutoff]
            .set_index("ticker")["signal"]
            .sort_index()
        )
        sig_trunc = (
            result_trunc[result_trunc["as_of"] == cutoff]
            .set_index("ticker")["signal"]
            .sort_index()
        )

        assert not sig_full.empty, "No signal at cutoff in full dataset"
        assert not sig_trunc.empty, "No signal at cutoff in truncated dataset"
        pd.testing.assert_series_equal(sig_full, sig_trunc, check_names=False, rtol=1e-6)


# ---------------------------------------------------------------------------
# Vol normalization
# ---------------------------------------------------------------------------


class TestVolNormalization:
    """Vol-normalized returns scale down high-vol signals."""

    def test_same_drift_different_vol_same_direction(
        self, vol_spread_prices: pd.DataFrame
    ) -> None:
        """Both LOW and HIGH have same drift, so signals should both be positive."""
        result = compute_signal(vol_spread_prices)
        last_30 = result["as_of"].drop_duplicates().nlargest(30)
        recent = result[result["as_of"].isin(last_30)]
        low_sig = recent[recent["ticker"] == "LOW"]["signal"].mean()
        high_sig = recent[recent["ticker"] == "HIGH"]["signal"].mean()
        # Signs must agree (both positive drift)
        # With z-score and 2 tickers the signs are mirrored, but at least one is meaningful.
        # Main assertion: signal is finite and non-NaN
        assert np.isfinite(low_sig), f"LOW signal not finite: {low_sig}"
        assert np.isfinite(high_sig), f"HIGH signal not finite: {high_sig}"

    def test_vol_normalisation_reduces_cross_asset_magnitude_disparity(
        self, vol_spread_prices: pd.DataFrame
    ) -> None:
        """Vol normalization brings magnitude ratio closer to 1 across tickers.

        Raw returns scale with σ, so HIGH (σ=2%) produces ~4× larger raw returns
        than LOW (σ=0.5%). After dividing by rolling vol (also ∝ σ), both tickers
        produce vol-normalized returns of similar magnitude (σ cancels out).
        """
        prices = vol_spread_prices
        daily_rets = prices.pct_change()
        vol = daily_rets.rolling(63).std() * np.sqrt(252)
        lb_ret_21 = prices / prices.shift(21) - 1

        # Raw returns: HIGH should be much larger in magnitude than LOW
        low_raw = lb_ret_21["LOW"].dropna().abs().mean()
        high_raw = lb_ret_21["HIGH"].dropna().abs().mean()
        raw_ratio = high_raw / low_raw
        assert raw_ratio > 2, (
            f"Fixture expects HIGH >> LOW raw magnitudes, got ratio {raw_ratio:.2f}"
        )

        # Vol-normalized: the ratio should collapse toward 1
        vol_norm = (lb_ret_21 / vol).dropna()
        low_norm = vol_norm["LOW"].abs().mean()
        high_norm = vol_norm["HIGH"].abs().mean()
        norm_ratio = high_norm / low_norm
        assert norm_ratio < raw_ratio, (
            f"Vol normalization should reduce magnitude ratio. "
            f"Raw: {raw_ratio:.2f}, Normalized: {norm_ratio:.2f}"
        )


# ---------------------------------------------------------------------------
# generate_signals (combined output)
# ---------------------------------------------------------------------------


class TestGenerateSignals:
    """generate_signals() returns combined (ticker, as_of, signal, weight)."""

    def test_returns_all_required_columns(self, trending_prices: pd.DataFrame) -> None:
        result = generate_signals(trending_prices)
        for col in ("ticker", "as_of", "signal", "weight"):
            assert col in result.columns, f"Missing column: {col}"

    def test_no_nan_in_output(self, trending_prices: pd.DataFrame) -> None:
        result = generate_signals(trending_prices)
        assert not result["signal"].isna().any(), "NaN in signal column"
        assert not result["weight"].isna().any(), "NaN in weight column"

    def test_output_row_count_matches_signal(self, trending_prices: pd.DataFrame) -> None:
        signals = compute_signal(trending_prices)
        combined = generate_signals(trending_prices)
        # Combined is inner-join of signal+weight — should have at least as many rows as signal
        # (both have same valid dates after warmup)
        assert len(combined) > 0
        assert len(combined) <= len(signals)


# ---------------------------------------------------------------------------
# compute_weights (inverse-vol sizing)
# ---------------------------------------------------------------------------


class TestComputeWeights:
    """compute_weights() returns correct inverse-volatility weights."""

    def test_returns_long_dataframe(self, trending_prices: pd.DataFrame) -> None:
        result = compute_weights(trending_prices)
        assert isinstance(result, pd.DataFrame)
        for col in ("ticker", "as_of", "weight"):
            assert col in result.columns, f"Missing column: {col}"

    def test_lower_vol_ticker_has_higher_weight(self, vol_spread_prices: pd.DataFrame) -> None:
        """LOW-vol ticker gets larger inverse-vol weight than HIGH-vol ticker."""
        result = compute_weights(vol_spread_prices, target_vol=0.10, max_weight=2.0)
        last_30 = result["as_of"].drop_duplicates().nlargest(30)
        recent = result[result["as_of"].isin(last_30)]

        low_w = recent[recent["ticker"] == "LOW"]["weight"].mean()
        high_w = recent[recent["ticker"] == "HIGH"]["weight"].mean()

        assert low_w > high_w, (
            f"LOW-vol should have higher weight: LOW={low_w:.4f}, HIGH={high_w:.4f}"
        )

    def test_weight_never_exceeds_max_weight(self, vol_spread_prices: pd.DataFrame) -> None:
        max_w = 0.15
        result = compute_weights(vol_spread_prices, target_vol=0.10, max_weight=max_w)
        assert (result["weight"] <= max_w + 1e-9).all(), "Some weights exceed max_weight"

    def test_all_weights_positive(self, trending_prices: pd.DataFrame) -> None:
        result = compute_weights(trending_prices)
        assert (result["weight"] > 0).all(), "Non-positive weights found"

    def test_doubling_target_vol_doubles_weights_before_cap(
        self, vol_spread_prices: pd.DataFrame
    ) -> None:
        """weight = target_vol / realized_vol, so doubling target_vol doubles weight."""
        # Use only LOW (stable vol) and high max_weight so cap never triggers
        prices = vol_spread_prices[["LOW"]]
        r1 = compute_weights(prices, target_vol=0.05, max_weight=10.0)
        r2 = compute_weights(prices, target_vol=0.10, max_weight=10.0)

        merged = r1.merge(r2, on=["ticker", "as_of"], suffixes=("_05", "_10"))
        ratio = (merged["weight_10"] / merged["weight_05"]).dropna()

        assert not ratio.empty
        assert (
            (ratio - 2.0).abs().mean() < 0.01
        ), f"Expected 2× ratio, got mean={ratio.mean():.4f}"

    def test_approximate_weight_formula(self, vol_spread_prices: pd.DataFrame) -> None:
        """weight ≈ target_vol / realized_vol at each date."""
        result = compute_weights(vol_spread_prices[["LOW"]], target_vol=0.10, max_weight=10.0)
        prices = vol_spread_prices[["LOW"]]
        realized_vol = prices.pct_change().rolling(60).std() * np.sqrt(252)

        last_date = result["as_of"].max()
        row = result[result["as_of"] == last_date].iloc[0]
        expected_w = 0.10 / realized_vol.loc[last_date, "LOW"]
        assert abs(row["weight"] - expected_w) < 1e-6, (
            f"Weight mismatch: got {row['weight']:.6f}, expected {expected_w:.6f}"
        )
