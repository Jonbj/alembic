"""Inverse-volatility position sizing for S1 strategy."""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_weights(
    prices: pd.DataFrame,
    vol_window: int = 60,
    target_vol: float = 0.10,
    max_weight: float = 0.20,
) -> pd.DataFrame:
    """Compute inverse-volatility position weights.

    weight = target_vol / realized_annualized_vol, capped at max_weight.

    Args:
        prices: Wide DataFrame, columns=tickers, index=DatetimeIndex.
        vol_window: Rolling window in days for realized vol estimation.
        target_vol: Annualized target volatility per position.
        max_weight: Maximum allowed weight (cap).

    Returns:
        Long-format DataFrame with columns: ticker, as_of, weight.
    """
    ann_factor = np.sqrt(252)
    daily_rets = prices.pct_change()
    ann_vol = daily_rets.rolling(vol_window).std() * ann_factor

    raw_weights = (target_vol / ann_vol).clip(upper=max_weight)

    # Drop warm-up rows (all tickers NaN)
    raw_weights = raw_weights.dropna(how="all")

    long_df = raw_weights.stack().reset_index()
    long_df.columns = ["as_of", "ticker", "weight"]
    long_df = long_df.dropna(subset=["weight"])

    return long_df[["ticker", "as_of", "weight"]].reset_index(drop=True)
