"""T-202: S3 signal — residual momentum with cross-sectional ranking."""
import numpy as np
import pandas as pd
import pytest

from src.strategies.s3.signal import (
    compute_beta,
    compute_cross_sectional_ranks,
    compute_residual_momentum,
    generate_s3_signals,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def simple_prices() -> pd.DataFrame:
    """Three-ticker dataset: SPY (market), A (= SPY, perfect beta=1), B (beta≈2)."""
    n = 550
    rng = np.random.default_rng(42)
    dates = pd.date_range("2018-01-01", periods=n, freq="B")

    spy_ret = rng.normal(0.0004, 0.01, n)
    spy = 100 * np.exp(np.cumsum(spy_ret))

    # Stock A: identical to market → beta exactly 1.0, residual_momentum exactly 0
    a = spy.copy()

    # Stock B: 2× leverage + noise → beta ≈ 2.0
    b_ret = 2.0 * spy_ret + rng.normal(0, 0.005, n)
    b = 100 * np.exp(np.cumsum(b_ret))

    return pd.DataFrame({"SPY": spy, "A": a, "B": b}, index=dates)


@pytest.fixture
def multi_stock_prices() -> pd.DataFrame:
    """SPY + 5 stocks with mixed betas, for cross-sectional tests."""
    n = 550
    rng = np.random.default_rng(7)
    dates = pd.date_range("2018-01-01", periods=n, freq="B")

    spy_ret = rng.normal(0.0004, 0.01, n)
    spy = 100 * np.exp(np.cumsum(spy_ret))

    stocks = {}
    for i, name in enumerate(["A", "B", "C", "D", "E"]):
        beta_factor = 0.5 + i * 0.25
        ret = beta_factor * spy_ret + rng.normal(0, 0.008, n)
        stocks[name] = 100 * np.exp(np.cumsum(ret))

    return pd.DataFrame({"SPY": spy, **stocks}, index=dates)


# ---------------------------------------------------------------------------
# compute_beta
# ---------------------------------------------------------------------------


class TestComputeBeta:
    def test_returns_wide_dataframe_without_market(self, simple_prices: pd.DataFrame) -> None:
        beta = compute_beta(simple_prices, market_col="SPY", window=252)
        assert isinstance(beta, pd.DataFrame)
        assert "SPY" not in beta.columns
        assert "A" in beta.columns and "B" in beta.columns
        assert len(beta) == len(simple_prices)

    def test_beta_nan_before_warmup(self, simple_prices: pd.DataFrame) -> None:
        beta = compute_beta(simple_prices, market_col="SPY", window=252)
        # Rows 0..251 must be NaN (252 returns needed → needs price indices 0..252)
        assert beta.iloc[:252].isna().all().all()

    def test_perfect_beta_equals_one(self, simple_prices: pd.DataFrame) -> None:
        """Stock A = SPY → rolling beta should be exactly 1.0 after warmup."""
        beta = compute_beta(simple_prices, market_col="SPY", window=252)
        valid = beta["A"].dropna()
        assert len(valid) > 50
        np.testing.assert_allclose(valid.values, 1.0, atol=1e-8)

    def test_high_beta_stock_close_to_two(self, simple_prices: pd.DataFrame) -> None:
        """Stock B is constructed as 2× market + noise → beta ≈ 2.0."""
        beta = compute_beta(simple_prices, market_col="SPY", window=252)
        valid = beta["B"].dropna()
        assert abs(valid.mean() - 2.0) < 0.20, (
            f"Expected beta ≈ 2.0 for B, got {valid.mean():.4f}"
        )


# ---------------------------------------------------------------------------
# compute_residual_momentum
# ---------------------------------------------------------------------------


class TestComputeResidualMomentum:
    def test_returns_wide_dataframe_without_market(self, simple_prices: pd.DataFrame) -> None:
        rm = compute_residual_momentum(simple_prices)
        assert "SPY" not in rm.columns
        assert set(rm.columns) == {"A", "B"}

    def test_output_shape_matches_input(self, simple_prices: pd.DataFrame) -> None:
        rm = compute_residual_momentum(simple_prices)
        n_stocks = len(simple_prices.columns) - 1
        assert rm.shape == (len(simple_prices), n_stocks)

    def test_nan_before_warmup(self, simple_prices: pd.DataFrame) -> None:
        rm = compute_residual_momentum(simple_prices, lookback=252, beta_window=252)
        # Price indices 0..251 yield NaN momentum or NaN beta
        assert rm.iloc[:252].isna().all().all()

    def test_stock_equal_to_market_has_zero_residual(self, simple_prices: pd.DataFrame) -> None:
        """Stock A = SPY exactly → beta=1, raw_mom=market_mom → residual = 0.0."""
        rm = compute_residual_momentum(simple_prices)
        valid_a = rm["A"].dropna()
        assert len(valid_a) > 50
        np.testing.assert_allclose(valid_a.values, 0.0, atol=1e-8)

    def test_no_market_column_in_output(self, multi_stock_prices: pd.DataFrame) -> None:
        rm = compute_residual_momentum(multi_stock_prices)
        assert "SPY" not in rm.columns


# ---------------------------------------------------------------------------
# compute_cross_sectional_ranks
# ---------------------------------------------------------------------------


class TestComputeCrossSectionalRanks:
    def test_output_columns(self) -> None:
        dates = pd.date_range("2020-01-01", periods=5, freq="B")
        rng = np.random.default_rng(0)
        rm = pd.DataFrame(rng.normal(size=(5, 3)), index=dates, columns=["A", "B", "C"])
        result = compute_cross_sectional_ranks(rm)
        assert list(result.columns) == ["as_of", "ticker", "residual_momentum", "rank", "decile"]

    def test_highest_residual_gets_highest_rank(self) -> None:
        dates = pd.date_range("2020-01-01", periods=1, freq="B")
        rm = pd.DataFrame({"A": [0.10], "B": [0.30], "C": [-0.10]}, index=dates)
        result = compute_cross_sectional_ranks(rm)
        b_rank = result.loc[result["ticker"] == "B", "rank"].iloc[0]
        c_rank = result.loc[result["ticker"] == "C", "rank"].iloc[0]
        assert b_rank == 3.0, f"B (highest) should have rank 3, got {b_rank}"
        assert c_rank == 1.0, f"C (lowest) should have rank 1, got {c_rank}"

    def test_decile_count_with_10_tickers(self) -> None:
        """10 tickers with distinct values → 10 deciles, one ticker each."""
        dates = pd.date_range("2020-01-01", periods=1, freq="B")
        tickers = [f"T{i}" for i in range(10)]
        rm = pd.DataFrame({t: [float(i)] for i, t in enumerate(tickers)}, index=dates)
        result = compute_cross_sectional_ranks(rm, n_deciles=10)
        assert set(result["decile"]) == set(range(1, 11))
        assert (result["decile"].value_counts() == 1).all()

    def test_decile_within_valid_range(self, multi_stock_prices: pd.DataFrame) -> None:
        rm = compute_residual_momentum(multi_stock_prices)
        valid = rm.dropna()
        result = compute_cross_sectional_ranks(valid)
        assert (result["decile"] >= 1).all()
        assert (result["decile"] <= 10).all()

    def test_one_row_per_ticker_per_date(self, multi_stock_prices: pd.DataFrame) -> None:
        rm = compute_residual_momentum(multi_stock_prices)
        valid = rm.dropna()
        result = compute_cross_sectional_ranks(valid)
        dupes = result.groupby(["as_of", "ticker"]).size()
        assert (dupes == 1).all(), "Duplicate (as_of, ticker) pairs found"

    def test_empty_input_returns_empty_dataframe(self) -> None:
        empty = pd.DataFrame(columns=["A", "B"])
        result = compute_cross_sectional_ranks(empty)
        assert result.empty
        assert list(result.columns) == ["as_of", "ticker", "residual_momentum", "rank", "decile"]


# ---------------------------------------------------------------------------
# No look-ahead bias
# ---------------------------------------------------------------------------


class TestNoLookahead:
    def test_signal_unchanged_after_appending_future_data(
        self, simple_prices: pd.DataFrame
    ) -> None:
        """Residual momentum at date T must not change when future data is appended."""
        all_dates = simple_prices.index
        cutoff_idx = len(all_dates) - 30
        cutoff = all_dates[cutoff_idx]

        prices_trunc = simple_prices.iloc[: cutoff_idx + 1]

        signals_full = generate_s3_signals(simple_prices)
        signals_trunc = generate_s3_signals(prices_trunc)

        full_at_cutoff = (
            signals_full[signals_full["as_of"] == cutoff]
            .set_index("ticker")["residual_momentum"]
            .sort_index()
        )
        trunc_at_cutoff = (
            signals_trunc[signals_trunc["as_of"] == cutoff]
            .set_index("ticker")["residual_momentum"]
            .sort_index()
        )

        assert not full_at_cutoff.empty, "No signal at cutoff in full dataset"
        assert not trunc_at_cutoff.empty, "No signal at cutoff in truncated dataset"
        pd.testing.assert_series_equal(full_at_cutoff, trunc_at_cutoff, check_names=False, rtol=1e-6)


# ---------------------------------------------------------------------------
# generate_s3_signals (end-to-end)
# ---------------------------------------------------------------------------


class TestGenerateS3Signals:
    def test_output_columns(self, simple_prices: pd.DataFrame) -> None:
        result = generate_s3_signals(simple_prices)
        assert list(result.columns) == ["as_of", "ticker", "residual_momentum", "rank", "decile"]

    def test_no_nan_in_output(self, simple_prices: pd.DataFrame) -> None:
        result = generate_s3_signals(simple_prices)
        assert not result.isna().any().any(), "NaN values found in output"

    def test_market_ticker_absent_from_output(self, simple_prices: pd.DataFrame) -> None:
        result = generate_s3_signals(simple_prices)
        assert "SPY" not in result["ticker"].values

    def test_output_has_rows_after_warmup(self, simple_prices: pd.DataFrame) -> None:
        result = generate_s3_signals(simple_prices)
        assert len(result) > 0
        expected_first = simple_prices.index[252]
        assert result["as_of"].min() >= expected_first

    def test_all_tickers_present_at_each_date(self, simple_prices: pd.DataFrame) -> None:
        result = generate_s3_signals(simple_prices)
        stock_tickers = set(c for c in simple_prices.columns if c != "SPY")
        ticker_counts = result.groupby("as_of")["ticker"].apply(set)
        assert (ticker_counts == stock_tickers).all(), "Some dates are missing tickers"

    def test_decile_is_integer_type(self, simple_prices: pd.DataFrame) -> None:
        result = generate_s3_signals(simple_prices)
        assert np.issubdtype(result["decile"].dtype, np.integer)

    def test_rank_is_float_type(self, simple_prices: pd.DataFrame) -> None:
        result = generate_s3_signals(simple_prices)
        assert np.issubdtype(result["rank"].dtype, np.floating)

    def test_end_to_end_multi_stock(self, multi_stock_prices: pd.DataFrame) -> None:
        result = generate_s3_signals(multi_stock_prices)
        assert not result.empty
        assert result["decile"].between(1, 10).all()
        assert "SPY" not in result["ticker"].values
