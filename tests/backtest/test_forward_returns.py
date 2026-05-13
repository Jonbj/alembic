"""Tests for ForwardReturnCalculator."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.backtest.forward_returns import ForwardReturnCalculator, ForwardReturns


def make_hourly_prices() -> pd.Series:
    """10 hourly bars starting 2025-10-01 14:00 UTC."""
    idx = pd.date_range("2025-10-01 14:00", periods=10, freq="1h", tz="UTC")
    return pd.Series(
        [100.0, 101.0, 102.0, 101.5, 103.0, 102.5, 104.0, 103.5, 105.0, 104.5],
        index=idx,
    )


def make_daily_prices() -> pd.Series:
    """5 daily close prices starting 2025-09-30."""
    idx = pd.date_range("2025-09-30", periods=5, freq="1D", tz="UTC")
    return pd.Series([99.0, 100.5, 102.0, 101.0, 103.5], index=idx)


def make_calculator() -> ForwardReturnCalculator:
    return ForwardReturnCalculator(pg_conn=MagicMock())


def test_forward_returns_1h():
    """1h return: (price at t_bar+1h - price at t_bar) / price at t_bar."""
    calc = make_calculator()
    ts = datetime(2025, 10, 1, 14, 0, tzinfo=timezone.utc)
    result = calc._compute_returns("AAPL", ts, make_hourly_prices(), make_daily_prices())

    # bar at 14:00 = 100.0, bar at 15:00 = 101.0 → (101-100)/100 = 0.01
    assert result.return_1h == pytest.approx(0.01)


def test_forward_returns_4h():
    """4h return: (price at t_bar+4h - price at t_bar) / price at t_bar."""
    calc = make_calculator()
    ts = datetime(2025, 10, 1, 14, 0, tzinfo=timezone.utc)
    result = calc._compute_returns("AAPL", ts, make_hourly_prices(), make_daily_prices())

    # bar at 14:00 = 100.0, bar at 18:00 = 103.0 → (103-100)/100 = 0.03
    assert result.return_4h == pytest.approx(0.03)


def test_forward_returns_24h():
    """24h return: next daily close / current daily close - 1."""
    calc = make_calculator()
    ts = datetime(2025, 10, 1, 14, 0, tzinfo=timezone.utc)
    result = calc._compute_returns("AAPL", ts, make_hourly_prices(), make_daily_prices())

    # daily: 2025-10-01 close=100.5, 2025-10-02 close=102.0 → (102-100.5)/100.5 ≈ 0.01493
    assert result.return_24h == pytest.approx((102.0 - 100.5) / 100.5)


def test_forward_returns_none_when_1h_bar_missing():
    """Returns None for 1h/4h when there are no bars after t_bar + offset."""
    calc = make_calculator()
    # Signal at last available bar (23:00): no bars 1h or 4h later
    ts = datetime(2025, 10, 1, 23, 0, tzinfo=timezone.utc)
    idx = pd.date_range("2025-10-01 23:00", periods=1, freq="1h", tz="UTC")
    short_series = pd.Series([100.0], index=idx)

    result = calc._compute_returns("AAPL", ts, short_series, make_daily_prices())

    assert result.return_1h is None
    assert result.return_4h is None


def test_forward_returns_none_when_no_next_daily_close():
    """Returns None for 24h when there is no next day's close."""
    calc = make_calculator()
    # Signal on the LAST day in the daily series
    idx = pd.date_range("2025-10-04", periods=1, freq="1D", tz="UTC")
    single_day = pd.Series([103.5], index=idx)

    ts = datetime(2025, 10, 4, 14, 0, tzinfo=timezone.utc)
    result = calc._compute_returns("AAPL", ts, make_hourly_prices(), single_day)

    assert result.return_24h is None


def test_forward_returns_none_when_ts_after_all_bars():
    """Returns None for all horizons when signal is after last available bar."""
    calc = make_calculator()
    ts = datetime(2025, 10, 2, 0, 0, tzinfo=timezone.utc)  # after last bar 23:00

    result = calc._compute_returns("AAPL", ts, make_hourly_prices(), make_daily_prices())

    assert result.return_1h is None
    assert result.return_4h is None


def test_forward_returns_none_when_no_price_data():
    """Returns all None when hourly prices are None (ticker not in yfinance)."""
    calc = make_calculator()
    ts = datetime(2025, 10, 1, 14, 0, tzinfo=timezone.utc)
    result = calc._compute_returns("UNKNOWN", ts, None, None)

    assert result == ForwardReturns(None, None, None)


def test_populate_calls_db_update(monkeypatch):
    """populate() fetches pending rows, downloads prices, and updates the DB."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=None)

    pending_rows = [
        {"id": 1, "symbol": "AAPL",
         "generated_at": datetime(2025, 10, 1, 14, 0, tzinfo=timezone.utc)},
    ]
    mock_cursor.fetchall.return_value = [
        (r["id"], r["symbol"], r["generated_at"]) for r in pending_rows
    ]

    calc = ForwardReturnCalculator(pg_conn=mock_conn)
    monkeypatch.setattr(
        calc, "_download_prices",
        lambda tickers, start, end, interval: {
            "AAPL": make_hourly_prices() if interval == "1h" else make_daily_prices()
        },
    )

    updated = calc.populate("test-run", datetime(2025, 10, 1), datetime(2025, 10, 31))

    assert updated == 1
    mock_conn.commit.assert_called_once()
    # executemany called with one update tuple
    mock_cursor.executemany.assert_called_once()
    args = mock_cursor.executemany.call_args[0]
    assert "UPDATE backtest_signals" in args[0]
