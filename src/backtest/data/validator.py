"""Data quality validation for OHLCV DataFrames."""
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd


@dataclass
class ValidationResult:
    symbol: str
    is_valid: bool
    gaps: list[tuple[date, date]]
    spikes: list[date]
    has_adj_close: bool
    trading_days: int
    nan_fraction: float


def validate_ohlcv(
    symbol: str,
    df: pd.DataFrame,
    max_gap_days: int = 5,
    spike_threshold: float = 0.25,
    max_nan_fraction: float = 0.05,
) -> ValidationResult:
    """Check OHLCV DataFrame for gaps, spikes, missing Adj Close, and NaN density."""
    has_adj_close = "Adj Close" in df.columns
    trading_days = len(df)

    price_col = "Adj Close" if has_adj_close else ("Close" if "Close" in df.columns else None)
    if price_col and price_col in df.columns:
        nan_fraction = float(df[price_col].isna().mean())
    else:
        nan_fraction = 1.0

    # Detect business-day gaps using np.busday_count (O(n), no calendar assumptions)
    gaps: list[tuple[date, date]] = []
    if len(df) > 1:
        dates_arr = df.index.date
        dates_np = df.index.values.astype("datetime64[D]")
        bday_counts = np.busday_count(dates_np[:-1], dates_np[1:])
        missing = bday_counts - 1  # 0 for consecutive business days
        for i in np.where(missing > max_gap_days)[0]:
            gaps.append((dates_arr[i], dates_arr[i + 1]))

    # Detect anomalous spikes in Adj Close (or Close if Adj Close missing)
    spikes: list[date] = []
    if price_col and price_col in df.columns and len(df) > 1:
        pct_change = df[price_col].pct_change().abs()
        spike_mask = pct_change > spike_threshold
        spikes = [ts.date() for ts in df.index[spike_mask]]

    is_valid = (
        has_adj_close
        and len(gaps) == 0
        and len(spikes) == 0
        and nan_fraction <= max_nan_fraction
    )

    return ValidationResult(
        symbol=symbol,
        is_valid=is_valid,
        gaps=gaps,
        spikes=spikes,
        has_adj_close=has_adj_close,
        trading_days=trading_days,
        nan_fraction=nan_fraction,
    )


def validate_universe_data(
    data: dict[str, pd.DataFrame],
    max_gap_days: int = 5,
    spike_threshold: float = 0.25,
    max_nan_fraction: float = 0.05,
) -> dict[str, ValidationResult]:
    """Run validate_ohlcv for each symbol in data, return results keyed by symbol."""
    return {
        symbol: validate_ohlcv(symbol, df, max_gap_days, spike_threshold, max_nan_fraction)
        for symbol, df in data.items()
    }
