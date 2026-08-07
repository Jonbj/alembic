"""S2 audit — repro_1: look-ahead in _split_regime_returns bull/bear classification.

backtest.py:202-211 classifies each OOS date t as 'bull' or 'bear' using

    fwd_21d = cum_return.shift(-21) / cum_return - 1
    bull_mask = fwd_21d > 0

i.e. the regime label of date t depends on the cumulative return from t to t+21
(FUTURE data). The gate_4 (regime) verdict in summary.json is computed on these
labels, so the regime gate is evaluated with hindsight: a date is labelled 'bull'
because the NEXT 21 days turned out positive.

This repro shows deterministically that, at a given date t, the bull/bear label
flips purely based on returns after t (which are unknowable at t).

Audit artifact (read-only). Does NOT import the strategy; replicates the one
line of logic to make the counterexample self-contained and obvious.
Run: python docs/audits/strategies/S2/repro_1_regime_lookahead.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# A 42-day OOS return series. Day 20 is the date under test.
# Days 0..20: flat (returns 0). Days 21..41: choose the future.
# Case A: days 21..41 are +1%/day  -> cum_return rises  -> fwd_21d at day 20 > 0 -> 'bull'
# Case B: days 21..41 are -1%/day  -> cum_return falls  -> fwd_21d at day 20 < 0 -> 'bear'
# Everything up to and INCLUDING day 20 is identical between A and B, yet the
# regime label of day 20 differs -> the label uses information from day 21..41.

idx = pd.bdate_range("2024-01-01", periods=42)
past = [0.0] * 21                 # days 0..20 (incl. day 20): identical in A and B
future_A = [0.01] * 21            # days 21..41: +1%/day
future_B = [-0.01] * 21           # days 21..41: -1%/day

rA = pd.Series(past + future_A, index=idx)
rB = pd.Series(past + future_B, index=idx)

t = idx[20]  # the date under test


def label_at(oos_returns: pd.Series, date) -> str:
    cum = (1 + oos_returns).cumprod()
    fwd = cum.shift(-21) / cum - 1
    return "bull" if fwd.loc[date] > 0 else "bear"


label_A = label_at(rA, t)
label_B = label_at(rB, t)

print(f"Date under test: {t.date()} (day 20)")
print(f"Returns days 0..20 (identical A,B): all 0.0")
print(f"Returns days 21..41 case A: +1%/day   case B: -1%/day")
print(f"\nRegime label at day 20 — case A (future up):   {label_A}")
print(f"Regime label at day 20 — case B (future down): {label_B}")

assert rA.loc[:t].equals(rB.loc[:t]), "past must be identical"
if label_A != label_B:
    print("\nCONFIRMED: the regime label of day 20 depends solely on returns on")
    print("days 21..41 (future). The regime gate (gate_4) is evaluated with")
    print("look-ahead bias -> the 'bull/bear' regime split is not knowable at t.")
else:
    print("\nResult not as predicted; inspect manually.")