"""P1-02 Real historical stress test — 2008, 2020, 2022 periods.

Problem (from audit): _extract_stress_periods() uses only the worst
drawdown from OOS returns (synthetic, not real dates). No test verifies
behavior against the actual 2008 crisis, 2020 COVID crash, 2022 drawdown.

Fix: add extract_historical_stress_periods(returns) that slices by real
calendar windows. Gate 5 stress test should use these when the data covers
those periods.
"""
from __future__ import annotations

import pytest
import pandas as pd
import numpy as np


class TestHistoricalStressModule:

    def test_module_exists(self):
        try:
            from src.backtest.gates.historical_stress import extract_historical_stress_periods
        except ImportError:
            pytest.fail("src.backtest.gates.historical_stress must export extract_historical_stress_periods()")

    def test_extracts_2008_period_when_data_covers_it(self):
        """extract_historical_stress_periods returns '2008_gfc' slice when data covers 2008-09."""
        from src.backtest.gates.historical_stress import extract_historical_stress_periods

        dates = pd.date_range("2005-01-01", "2015-12-31", freq="B")
        rng = np.random.default_rng(1)
        returns = pd.Series(rng.normal(0, 0.01, len(dates)), index=dates)

        periods = extract_historical_stress_periods(returns)

        assert "2008_gfc" in periods, (
            "extract_historical_stress_periods must return '2008_gfc' slice when "
            "returns cover 2008–2009. Got keys: " + str(list(periods.keys()))
        )
        assert len(periods["2008_gfc"]) > 0

    def test_extracts_2020_period_when_data_covers_it(self):
        """extract_historical_stress_periods returns '2020_covid' slice."""
        from src.backtest.gates.historical_stress import extract_historical_stress_periods

        dates = pd.date_range("2018-01-01", "2022-12-31", freq="B")
        rng = np.random.default_rng(2)
        returns = pd.Series(rng.normal(0, 0.01, len(dates)), index=dates)

        periods = extract_historical_stress_periods(returns)

        assert "2020_covid" in periods, (
            "extract_historical_stress_periods must return '2020_covid' slice. "
            "Got: " + str(list(periods.keys()))
        )
        assert len(periods["2020_covid"]) > 0

    def test_extracts_2022_period_when_data_covers_it(self):
        """extract_historical_stress_periods returns '2022_rates' slice."""
        from src.backtest.gates.historical_stress import extract_historical_stress_periods

        dates = pd.date_range("2020-01-01", "2024-12-31", freq="B")
        rng = np.random.default_rng(3)
        returns = pd.Series(rng.normal(0, 0.01, len(dates)), index=dates)

        periods = extract_historical_stress_periods(returns)

        assert "2022_rates" in periods, (
            "extract_historical_stress_periods must return '2022_rates' slice. "
            "Got: " + str(list(periods.keys()))
        )
        assert len(periods["2022_rates"]) > 0

    def test_skips_period_not_covered_by_data(self):
        """extract_historical_stress_periods omits periods outside the data range."""
        from src.backtest.gates.historical_stress import extract_historical_stress_periods

        # Data starts 2021 — no 2008 or 2020 coverage
        dates = pd.date_range("2021-01-01", "2024-12-31", freq="B")
        rng = np.random.default_rng(4)
        returns = pd.Series(rng.normal(0, 0.01, len(dates)), index=dates)

        periods = extract_historical_stress_periods(returns)

        assert "2008_gfc" not in periods, (
            "2008_gfc must not appear when data starts in 2021 (no coverage)."
        )
        assert "2020_covid" not in periods, (
            "2020_covid must not appear when data starts in 2021."
        )

    def test_returns_empty_dict_for_short_data(self):
        """extract_historical_stress_periods returns empty dict when no period overlaps."""
        from src.backtest.gates.historical_stress import extract_historical_stress_periods

        dates = pd.date_range("2015-06-01", "2015-12-31", freq="B")
        rng = np.random.default_rng(5)
        returns = pd.Series(rng.normal(0, 0.01, len(dates)), index=dates)

        periods = extract_historical_stress_periods(returns)
        assert isinstance(periods, dict)
        # All 3 stress periods are outside this 6-month window
        assert "2008_gfc" not in periods
        assert "2020_covid" not in periods
        assert "2022_rates" not in periods

    def test_stress_periods_have_correct_date_bounds(self):
        """The 2008 slice must fall within 2008-09-01 — 2009-06-30."""
        from src.backtest.gates.historical_stress import extract_historical_stress_periods

        dates = pd.date_range("2000-01-01", "2020-12-31", freq="B")
        rng = np.random.default_rng(6)
        returns = pd.Series(rng.normal(0, 0.01, len(dates)), index=dates)

        periods = extract_historical_stress_periods(returns)
        gfc = periods["2008_gfc"]

        assert gfc.index.min() >= pd.Timestamp("2008-09-01"), (
            f"2008_gfc period should start no earlier than 2008-09-01, got {gfc.index.min()}"
        )
        assert gfc.index.max() <= pd.Timestamp("2009-06-30"), (
            f"2008_gfc period should end no later than 2009-06-30, got {gfc.index.max()}"
        )
