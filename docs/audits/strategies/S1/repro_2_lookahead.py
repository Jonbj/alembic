"""S1 audit — repro_2: full-window look-ahead in compute_signal ticker filter.

Counterexample: at the SAME as_of date, the set of included tickers (and therefore
the cross-sectional z-score of a surviving ticker) differs depending on whether the
panel passed to compute_signal contains ONLY data up to as_of, or the FULL panel
including future data. In the backtest the full panel is passed
(run_s1_backtest_from_prices -> generate_signals(prices=full)), so universe
selection at date t uses data from t+1..end. That is look-ahead bias.

Setup: 3 tickers over 100 business days.
  A, B : full coverage (survivors).
  C    : listed day 0, DELISTED after day 60 (NaN 61..99).
At as_of = day 50, C was a valid live ticker (full coverage 0..50).
  - TRUNCATED panel (data <= day50): C coverage = 100% -> included. Universe = {A,B,C}.
  - FULL panel (data through day99): C coverage = 61/100 = 61% < 75% -> dropped
    because of its FUTURE NaNs (delisting). Universe = {A,B}.
A's z-score at day 50 therefore differs between the two -> the backtest's value at
day 50 uses future information.

Audit artifact (read-only). Imports the real compute_signal.
Run: python docs/audits/strategies/S1/repro_2_lookahead.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from src.strategies.s1.signal import compute_signal  # noqa: E402

rng = np.random.default_rng(42)
N = 100
idx = pd.bdate_range("2024-01-01", periods=N)

A = pd.Series(rng.normal(100, 1, size=N).cumsum(), index=idx)
B = pd.Series(rng.normal(200, 1, size=N).cumsum(), index=idx)
C_full = pd.Series(rng.normal(50, 1, size=N).cumsum(), index=idx)
C_full.iloc[61:] = np.nan  # delisted after day 60

prices_full = pd.DataFrame({"A": A, "B": B, "C": C_full})
prices_trunc = prices_full.iloc[:51].copy()  # only up to day 50

as_of = prices_trunc.index[-1]
print(f"as_of = {as_of.date()}  (day 50 of 100)")

LB, VW = (10, 21), 10
sig_full = compute_signal(prices_full, lookbacks=LB, vol_window=VW, min_observation_ratio=0.75)
sig_trunc = compute_signal(prices_trunc, lookbacks=LB, vol_window=VW, min_observation_ratio=0.75)

incl_full = set(sig_full[sig_full["as_of"] <= as_of]["ticker"].unique()) if not sig_full.empty else set()
incl_trunc = set(sig_trunc["ticker"].unique()) if not sig_trunc.empty else set()
print(f"Universe at as_of — TRUNCATED (data<=as_of): {sorted(incl_trunc)}")
print(f"Universe at as_of — FULL (data through day99): {sorted(incl_full)}")

def zscore_at(df, ticker, date):
    if df.empty:
        return None
    row = df[(df["ticker"] == ticker) & (df["as_of"] == date)]
    return None if row.empty else float(row["signal"].iloc[0])

zA_trunc = zscore_at(sig_trunc, "A", as_of)
zA_full = zscore_at(sig_full, "A", as_of)
print(f"\nA's z-score at as_of — TRUNCATED: {zA_trunc!r}   FULL: {zA_full!r}")

c_in_trunc, c_in_full = "C" in incl_trunc, "C" in incl_full
print(f"\nC included (truncated)? {c_in_trunc}   C included (full)? {c_in_full}")

if c_in_trunc and not c_in_full and zA_trunc is not None and zA_full is not None and zA_trunc != zA_full:
    print("\nCONFIRMED: C is dropped at as_of=day50 solely because of NaNs on days 61..99")
    print("(future information). A's z-score at day 50 differs between truncated and full")
    print("panel -> backtest universe/signal at day 50 uses future data -> LOOK-AHEAD BIAS.")
else:
    print("\nResult not as predicted; inspect manually. (incl_trunc, incl_full, zA_trunc, zA_full)")
    print("  ->", sorted(incl_trunc), sorted(incl_full), zA_trunc, zA_full)