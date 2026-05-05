"""Integration tests for gdelt_ab_test CLI — all external deps mocked."""
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from scripts.gdelt_ab_test import run_ab_test


def make_price_df(n_days: int = 260, start: str = "2024-01-02") -> pd.DataFrame:
    rng = np.random.default_rng(42)
    dates = pd.bdate_range(start=start, periods=n_days)
    prices = 100 * np.cumprod(1 + rng.normal(0.0005, 0.01, n_days))
    return pd.DataFrame({"Close": prices}, index=dates)


async def empty_async_gen(*args, **kwargs):
    """Async generator that yields nothing."""
    if False:
        yield  # Makes this a proper async generator


class TestRunABTest:
    @pytest.mark.asyncio
    async def test_result_contains_all_symbols(self):
        price_df = make_price_df()

        def mock_score_articles(articles, min_confidence=0.3):
            rng = np.random.default_rng(0)
            return [
                (date(2024, 1, 2) + timedelta(days=int(rng.integers(0, 250))),
                 float(rng.uniform(-0.5, 0.5)))
                for _ in range(50)
            ]

        with patch("scripts.gdelt_ab_test.score_articles", side_effect=mock_score_articles), \
             patch("scripts.gdelt_ab_test.GDELTConnector") as mock_gdelt_cls, \
             patch("scripts.gdelt_ab_test.yf.Ticker") as mock_ticker_cls:

            mock_connector = MagicMock()
            mock_connector.fetch_historical = empty_async_gen
            mock_gdelt_cls.return_value = mock_connector

            mock_ticker = MagicMock()
            mock_ticker.history.return_value = price_df
            mock_ticker_cls.return_value = mock_ticker

            result = await run_ab_test(
                symbols=["AAPL", "MSFT"],
                start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end=datetime(2024, 12, 31, tzinfo=timezone.utc),
                horizon=1,
                threshold=0.1,
                min_confidence=0.3,
            )

        assert "AAPL" in result["symbols"]
        assert "MSFT" in result["symbols"]
        assert "gate_passed_overall" in result
        assert "overall_delta_sharpe" in result

    @pytest.mark.asyncio
    async def test_gate_fails_with_no_articles(self):
        """Zero GDELT articles → no edge → gate should fail (delta_Sharpe < 0.1)."""
        price_df = make_price_df()

        with patch("scripts.gdelt_ab_test.score_articles", return_value=[]), \
             patch("scripts.gdelt_ab_test.GDELTConnector") as mock_gdelt_cls, \
             patch("scripts.gdelt_ab_test.yf.Ticker") as mock_ticker_cls:

            mock_connector = MagicMock()
            mock_connector.fetch_historical = empty_async_gen
            mock_gdelt_cls.return_value = mock_connector

            mock_ticker = MagicMock()
            mock_ticker.history.return_value = price_df
            mock_ticker_cls.return_value = mock_ticker

            result = await run_ab_test(
                symbols=["AAPL"],
                start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end=datetime(2024, 12, 31, tzinfo=timezone.utc),
                horizon=1,
                threshold=0.1,
                min_confidence=0.3,
            )

        assert result["gate_passed_overall"] is False
        assert result["symbols"]["AAPL"]["n_signals"] == 0

    @pytest.mark.asyncio
    async def test_result_schema(self):
        """Output dict matches the JSON schema from the spec."""
        price_df = make_price_df()

        with patch("scripts.gdelt_ab_test.score_articles", return_value=[]), \
             patch("scripts.gdelt_ab_test.GDELTConnector") as mock_gdelt_cls, \
             patch("scripts.gdelt_ab_test.yf.Ticker") as mock_ticker_cls:

            mock_connector = MagicMock()
            mock_connector.fetch_historical = empty_async_gen
            mock_gdelt_cls.return_value = mock_connector

            mock_ticker = MagicMock()
            mock_ticker.history.return_value = price_df
            mock_ticker_cls.return_value = mock_ticker

            result = await run_ab_test(
                symbols=["SPY"],
                start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end=datetime(2024, 3, 31, tzinfo=timezone.utc),
                horizon=1,
                threshold=0.1,
                min_confidence=0.3,
            )

        top = result["symbols"]["SPY"]
        for key in ("sharpe_baseline", "sharpe_gdelt", "delta_sharpe", "composite_ic",
                    "coverage_pct", "n_signals", "n_trading_days", "gate_passed"):
            assert key in top, f"Missing key: {key}"
