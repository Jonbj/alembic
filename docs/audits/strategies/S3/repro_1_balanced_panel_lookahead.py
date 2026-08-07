"""S3 BUG-A reproduction: balanced-panel date selection is look-ahead.

signal.py:136  valid_rows = residual.notna().all(axis=1)

A date t is admitted to the backtest iff ALL tickers in the panel have a
non-NaN residual at t. When the panel contains a ticker listed in the future
(e.g. IPO at 2012-01-01) but selected because it is a survivor today, that
ticker has NaN close for t < 2012 -> residual NaN -> the date t is DROPPED
from the backtest even though it was fully observable PIT with the tickers
that existed then.

This is the same mechanism as S1 BUG-2. The set of admissible backtest dates
is determined by the future-listed tickers in the panel -> look-ahead in date
selection.

Run: python docs/audits/strategies/S3/repro_1_balanced_panel_lookahead.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

# Import the real S3 signal generator.
ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
from src.strategies.s3.signal import generate_s3_signals  # noqa: E402


def main() -> None:
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2010-01-01", "2014-12-31")

    # SPY market: always present full history.
    spy = pd.Series(100 + np.cumsum(rng.normal(0, 0.01, len(dates))), index=dates)

    # OLD ticker: listed since 2010 (full history), a survivor today.
    old = pd.Series(50 + np.cumsum(rng.normal(0, 0.012, len(dates))), index=dates)

    # FUTURE-listed ticker: IPO 2012-01-02. NaN before listing.
    future = pd.Series(index=dates, dtype=float)
    future.loc[dates[0]: pd.Timestamp("2011-12-30")] = np.nan
    future_vals = 30 + np.cumsum(rng.normal(0, 0.015, (dates >= pd.Timestamp("2012-01-02")).sum()))
    future.loc[pd.Timestamp("2012-01-02"):] = future_vals

    prices = pd.DataFrame({"SPY": spy, "OLD": old, "FUTURE": future})

    # S3 signal gen with the balanced-panel filter (the real code path).
    sigs = generate_s3_signals(prices, market_col="SPY", lookback=252, beta_window=252)

    admitted_dates = sorted(set(sigs["as_of"]))
    first_admitted = pd.Timestamp(admitted_dates[0])
    future_listing = pd.Timestamp("2012-01-02")
    lookback_end_for_future = future_listing + pd.Timedelta(days=252 * 1.4)  # ~252 trading days

    print("=== S3 BUG-A: balanced-panel look-ahead ===")
    print(f"price history start : {dates[0].date()}")
    print(f"FUTURE listing date : {future_listing.date()}")
    print(f"OLD ticker present from : {dates[0].date()} (full history, observable PIT)")
    print(f"first admitted backtest date: {first_admitted.date()}")
    print(f"expected if no look-ahead (OLD-only observable): ~{dates[0].date()} + 252td")
    print(f"expected with FUTURE in panel: ~{future_listing.date()} + 252td = ~{lookback_end_for_future.date()}")
    print()
    print(f"admitted dates count: {len(admitted_dates)}")
    print(f"first 3 admitted: {[d.date() for d in admitted_dates[:3]]}")

    # Verdict: first admitted date must be AFTER the future listing + lookback,
    # proving the future-listed ticker (unobservable PIT before 2012) controls
    # which dates the backtest can use.
    if first_admitted > future_listing:
        print("\nCONFIRMED: the first admissible backtest date is gated by the "
              "future-listed ticker (IPO 2012), not by the tickers observable "
              "PIT. The balanced-panel filter (signal.py:136) leaks future "
              "listing info into date selection -> look-ahead.")
    else:
        print("\nNOT CONFIRMED by this construction.")


if __name__ == "__main__":
    main()