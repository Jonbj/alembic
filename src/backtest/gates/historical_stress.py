"""Historical stress period definitions for Gate 5.

Slices a returns Series into named real-world drawdown periods.
Only periods that overlap with the data range are returned.
"""
from __future__ import annotations

import pandas as pd

# Named stress periods: (start_inclusive, end_inclusive)
HISTORICAL_STRESS_PERIODS: dict[str, tuple[str, str]] = {
    "2008_gfc":    ("2008-09-01", "2009-06-30"),   # Lehman → trough
    "2020_covid":  ("2020-02-19", "2020-04-30"),   # COVID crash
    "2022_rates":  ("2022-01-01", "2022-12-31"),   # rate-hike drawdown
}


def extract_historical_stress_periods(returns: pd.Series) -> dict[str, pd.Series]:
    """Slice returns into named real-world stress windows.

    Only periods that overlap with the index of `returns` are included.
    Returns an empty dict if none of the stress windows overlap the data.

    Args:
        returns: Daily returns pd.Series with a DatetimeIndex.

    Returns:
        Dict mapping period name → returns slice (may be shorter than full window
        if data only partially covers the stress period).
    """
    if returns.empty:
        return {}

    result: dict[str, pd.Series] = {}
    data_start = returns.index.min()
    data_end = returns.index.max()

    for name, (start_str, end_str) in HISTORICAL_STRESS_PERIODS.items():
        period_start = pd.Timestamp(start_str)
        period_end = pd.Timestamp(end_str)

        # Skip if data doesn't cover any part of this stress period
        if data_end < period_start or data_start > period_end:
            continue

        slice_ = returns.loc[period_start:period_end]
        if not slice_.empty:
            result[name] = slice_

    return result
