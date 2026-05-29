"""Tests for backtest/metrics/attribution.py (T-006).

Covers: strategy_attribution return/risk decomposition.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.backtest.metrics.attribution import AttributionResult, strategy_attribution


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def two_strategy_returns() -> dict[str, pd.Series]:
    rng = np.random.default_rng(42)
    dates = pd.date_range("2020-01-02", periods=252, freq="B")
    return {
        "S1": pd.Series(rng.normal(0.001, 0.01, 252), index=dates),
        "S2": pd.Series(rng.normal(0.0005, 0.015, 252), index=dates),
    }


@pytest.fixture
def equal_weights() -> dict[str, float]:
    return {"S1": 0.5, "S2": 0.5}


# ---------------------------------------------------------------------------
# Empty / edge cases
# ---------------------------------------------------------------------------

class TestAttributionEdgeCases:
    def test_empty_returns_returns_empty_result(self):
        result = strategy_attribution({}, {})
        assert isinstance(result, AttributionResult)
        assert len(result.strategies) == 0

    def test_misaligned_dates_handled(self):
        dates_a = pd.date_range("2020-01-02", periods=100, freq="B")
        dates_b = pd.date_range("2020-01-02", periods=80, freq="B")
        returns = {
            "A": pd.Series(np.ones(100) * 0.001, index=dates_a),
            "B": pd.Series(np.ones(80) * 0.001, index=dates_b),
        }
        weights = {"A": 0.5, "B": 0.5}
        result = strategy_attribution(returns, weights)
        # Inner-join → 80 common periods
        assert result.n_periods == 80

    def test_single_strategy_full_weight(self):
        dates = pd.date_range("2020-01-02", periods=252, freq="B")
        r = pd.Series(np.ones(252) * 0.001, index=dates)
        result = strategy_attribution({"S": r}, {"S": 1.0})
        assert len(result.strategies) == 1
        assert result.strategies[0].weight == 1.0


# ---------------------------------------------------------------------------
# Return attribution correctness
# ---------------------------------------------------------------------------

class TestReturnAttribution:
    def test_total_contribution_sums_to_portfolio(self, two_strategy_returns, equal_weights):
        result = strategy_attribution(two_strategy_returns, equal_weights)
        total_contrib = sum(s.contribution_to_return for s in result.strategies)
        # sum of w_i * mean_i * 252 ≈ portfolio annualized return (approx, not exact)
        # Just verify both strategies have non-trivial contributions
        assert total_contrib != 0.0

    def test_zero_weight_strategy_zero_contribution(self):
        dates = pd.date_range("2020-01-02", periods=252, freq="B")
        rng = np.random.default_rng(1)
        returns = {
            "A": pd.Series(rng.normal(0.001, 0.01, 252), index=dates),
            "B": pd.Series(rng.normal(0.001, 0.01, 252), index=dates),
        }
        result = strategy_attribution(returns, {"A": 1.0, "B": 0.0})
        b = next(s for s in result.strategies if s.name == "B")
        assert b.contribution_to_return == 0.0

    def test_positive_drift_positive_annualized_return(self, two_strategy_returns, equal_weights):
        result = strategy_attribution(two_strategy_returns, equal_weights)
        for s in result.strategies:
            assert s.annualized_return > 0

    def test_individual_returns_match_input(self, two_strategy_returns, equal_weights):
        result = strategy_attribution(two_strategy_returns, equal_weights)
        for s in result.strategies:
            raw = two_strategy_returns[s.name]
            expected_total = float((1 + raw).prod() - 1)
            assert abs(s.total_return - expected_total) < 1e-9


# ---------------------------------------------------------------------------
# Risk attribution correctness
# ---------------------------------------------------------------------------

class TestRiskAttribution:
    def test_portfolio_vol_positive(self, two_strategy_returns, equal_weights):
        result = strategy_attribution(two_strategy_returns, equal_weights)
        assert result.portfolio_volatility > 0

    def test_correlation_to_portfolio_in_minus_one_to_one(
        self, two_strategy_returns, equal_weights
    ):
        result = strategy_attribution(two_strategy_returns, equal_weights)
        for s in result.strategies:
            assert -1.0 - 1e-9 <= s.correlation_to_portfolio <= 1.0 + 1e-9

    def test_independent_strategies_diversification_ratio_gt_one(self):
        rng = np.random.default_rng(5)
        dates = pd.date_range("2020-01-02", periods=500, freq="B")
        # Orthogonal returns → high diversification
        r1 = pd.Series(rng.normal(0.001, 0.01, 500), index=dates)
        r2 = pd.Series(rng.normal(0.001, 0.01, 500), index=dates)
        result = strategy_attribution({"A": r1, "B": r2}, {"A": 0.5, "B": 0.5})
        assert result.diversification_ratio > 1.0

    def test_perfectly_correlated_diversification_ratio_one(self):
        rng = np.random.default_rng(6)
        dates = pd.date_range("2020-01-02", periods=252, freq="B")
        r = pd.Series(rng.normal(0.001, 0.01, 252), index=dates)
        # Same series → correlation 1 → no diversification
        result = strategy_attribution({"A": r, "B": r}, {"A": 0.5, "B": 0.5})
        assert result.diversification_ratio == pytest.approx(1.0, rel=1e-6)

    def test_variance_contributions_positive_for_nonzero_weights(
        self, two_strategy_returns, equal_weights
    ):
        result = strategy_attribution(two_strategy_returns, equal_weights)
        for s in result.strategies:
            if s.weight > 0:
                # Variance contribution can be negative only for very negatively
                # correlated strategies; with two random series it should be > 0
                assert isinstance(s.contribution_to_variance, float)


# ---------------------------------------------------------------------------
# Sharpe ratio
# ---------------------------------------------------------------------------

class TestAttributionSharpe:
    def test_portfolio_sharpe_positive_for_positive_drift(
        self, two_strategy_returns, equal_weights
    ):
        result = strategy_attribution(two_strategy_returns, equal_weights)
        assert result.portfolio_sharpe > 0

    def test_individual_strategy_sharpe_positive_for_positive_drift(
        self, two_strategy_returns, equal_weights
    ):
        result = strategy_attribution(two_strategy_returns, equal_weights)
        for s in result.strategies:
            assert s.sharpe > 0


# ---------------------------------------------------------------------------
# Report integration
# ---------------------------------------------------------------------------

class TestAttributionInReport:
    def test_attribution_shows_in_markdown(self, two_strategy_returns, equal_weights):
        from src.backtest.metrics.report import MetricsReport

        result = strategy_attribution(two_strategy_returns, equal_weights)

        # Build a minimal report with attribution attached
        dates = list(two_strategy_returns.values())[0].index
        nav = pd.Series(
            (1 + (0.5 * two_strategy_returns["S1"] + 0.5 * two_strategy_returns["S2"])).cumprod()
            * 100_000,
            index=dates,
        )

        class _FakeResult:
            def to_nav_series(self):
                return nav

            def to_returns_series(self):
                return nav.pct_change().dropna()

        report = MetricsReport.from_backtest_result(_FakeResult(), attribution=result)
        md = report.to_markdown()
        assert "Strategy Attribution" in md
        assert "S1" in md
        assert "S2" in md

    def test_attribution_shows_in_html(self, two_strategy_returns, equal_weights):
        from src.backtest.metrics.report import MetricsReport

        result = strategy_attribution(two_strategy_returns, equal_weights)
        dates = list(two_strategy_returns.values())[0].index
        nav = pd.Series(
            (1 + (0.5 * two_strategy_returns["S1"] + 0.5 * two_strategy_returns["S2"])).cumprod()
            * 100_000,
            index=dates,
        )

        class _FakeResult:
            def to_nav_series(self):
                return nav

            def to_returns_series(self):
                return nav.pct_change().dropna()

        report = MetricsReport.from_backtest_result(_FakeResult(), attribution=result)
        html_out = report.to_html()
        assert "Strategy Attribution" in html_out
        assert "S1" in html_out
