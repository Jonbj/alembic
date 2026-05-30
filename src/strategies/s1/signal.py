"""Time-series momentum signal computation for S1 strategy."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.strategies.s1.sizing import compute_weights

_DEFAULT_LOOKBACKS: tuple[int, ...] = (21, 63, 126, 252)
_DEFAULT_VOL_WINDOW: int = 63


def _exponential_lb_weights(lookbacks: tuple[int, ...]) -> np.ndarray:
    """Exponential weights indexed by lookback rank (longer → more weight)."""
    n = len(lookbacks)
    order = np.argsort(lookbacks)  # ascending sort indices
    raw = np.exp(np.arange(n, dtype=float))  # [1, e, e^2, ...]
    weights = np.empty(n)
    for rank, idx in enumerate(order):
        weights[idx] = raw[rank]
    return weights / weights.sum()


def compute_signal(
    prices: pd.DataFrame,
    lookbacks: tuple[int, ...] = _DEFAULT_LOOKBACKS,
    vol_window: int = _DEFAULT_VOL_WINDOW,
    lb_weights: tuple[float, ...] | None = None,
) -> pd.DataFrame:
    """Compute multi-lookback vol-normalized momentum signal with cross-sectional z-score.

    Steps:
    1. For each lookback lb: ret_lb = price / price.shift(lb) - 1
    2. Vol-normalize: ret_lb / rolling_annualized_vol
    3. Weighted sum across lookbacks (exponential, longer = more weight)
    4. Cross-sectional z-score across the universe at each date

    Args:
        prices: Wide DataFrame, columns=tickers, index=DatetimeIndex.
        lookbacks: Lookback windows in trading days.
        vol_window: Rolling window for annualized vol denominator.
        lb_weights: Override lookback weights (must match len(lookbacks), need not sum to 1).

    Returns:
        Long-format DataFrame with columns: ticker, as_of, signal.
        Only rows where all tickers have valid data are included (no look-ahead).
    """
    if lb_weights is None:
        weights = _exponential_lb_weights(lookbacks)
    else:
        w = np.array(lb_weights, dtype=float)
        weights = w / w.sum()

    ann_factor = np.sqrt(252)
    daily_rets = prices.pct_change()
    rolling_vol = daily_rets.rolling(vol_window).std() * ann_factor

    # Accumulate weighted vol-normalized returns
    signal_raw = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    nan_mask = pd.DataFrame(False, index=prices.index, columns=prices.columns)

    for lb, w in zip(lookbacks, weights):
        lb_ret = prices / prices.shift(lb) - 1
        vol_norm = lb_ret / rolling_vol
        signal_raw += w * vol_norm.fillna(0.0)
        nan_mask |= vol_norm.isna()

    # Propagate NaN: rows where any component was NaN become NaN
    signal_raw[nan_mask] = np.nan

    # Keep only rows where ALL tickers have valid signals
    valid_rows = signal_raw.notna().all(axis=1)
    signal_raw = signal_raw[valid_rows]

    # Cross-sectional z-score
    cross_mean = signal_raw.mean(axis=1)
    cross_std = signal_raw.std(axis=1, ddof=1)

    # Drop degenerate rows (std = 0 or NaN, e.g. single-ticker or flat)
    valid_std = (cross_std > 1e-12) & cross_std.notna()
    signal_raw = signal_raw[valid_std]
    cross_mean = cross_mean[valid_std]
    cross_std = cross_std[valid_std]

    signal_zscored = signal_raw.sub(cross_mean, axis=0).div(cross_std, axis=0)

    # Reshape to long format
    long_df = signal_zscored.stack().reset_index()
    long_df.columns = ["as_of", "ticker", "signal"]
    long_df = long_df.dropna(subset=["signal"])

    return long_df[["ticker", "as_of", "signal"]].reset_index(drop=True)


def generate_signals(
    prices: pd.DataFrame,
    lookbacks: tuple[int, ...] = _DEFAULT_LOOKBACKS,
    vol_window_signal: int = _DEFAULT_VOL_WINDOW,
    vol_window_sizing: int = 60,
    lb_weights: tuple[float, ...] | None = None,
    target_vol: float = 0.10,
    max_weight: float = 0.20,
) -> pd.DataFrame:
    """Combine momentum signal and inverse-vol sizing into a single DataFrame.

    Args:
        prices: Wide DataFrame, columns=tickers, index=DatetimeIndex.
        lookbacks: Lookback windows for momentum signal.
        vol_window_signal: Rolling vol window used in signal computation.
        vol_window_sizing: Rolling vol window used for position sizing.
        lb_weights: Override lookback weights.
        target_vol: Annualized target vol per position.
        max_weight: Maximum position weight cap.

    Returns:
        Long-format DataFrame with columns: ticker, as_of, signal, weight.
    """
    signals = compute_signal(prices, lookbacks, vol_window_signal, lb_weights)
    weights = compute_weights(prices, vol_window_sizing, target_vol, max_weight)

    merged = signals.merge(weights, on=["ticker", "as_of"], how="inner")
    return merged.reset_index(drop=True)
