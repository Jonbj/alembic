"""Inverse-volatility position sizing for S1 strategy."""
from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np
import pandas as pd


def compute_sizing_metrics(
    *,
    target_weights: Mapping[str, float],
    signals: Mapping[str, float],
    raw_weights: Mapping[str, float],
    max_weight: float,
) -> dict[str, int | float | None]:
    """Describe how concentrated an S1 target is without changing its weights.

    ``target_weights`` are the sleeve-local weights after the existing
    sum-to-one normalization. ``raw_weights`` are the inverse-vol weights before
    that normalization, so a name clipped by ``max_weight`` remains observable.
    Spearman is undefined when fewer than two aligned names exist or either rank
    vector is constant; JSON-facing callers receive ``None`` instead of NaN.
    """
    target = {
        ticker: float(weight)
        for ticker, weight in target_weights.items()
        if math.isfinite(float(weight)) and float(weight) > 0
    }
    n_target = len(target)
    squared_sum = sum(weight**2 for weight in target.values())
    n_eff = 1.0 / squared_sum if squared_sum > 0 else 0.0

    cap_bound = sum(
        1
        for ticker in target
        if ticker in raw_weights
        and math.isclose(
            float(raw_weights[ticker]),
            max_weight,
            rel_tol=1e-9,
            abs_tol=1e-12,
        )
    )
    cap_bound_share = cap_bound / n_target if n_target else 0.0

    aligned = [
        ticker
        for ticker in target
        if ticker in signals and math.isfinite(float(signals[ticker]))
    ]
    spearman: float | None = None
    if len(aligned) >= 2:
        signal_ranks = pd.Series(
            [float(signals[ticker]) for ticker in aligned], dtype=float
        ).rank(method="average")
        weight_ranks = pd.Series(
            [target[ticker] for ticker in aligned], dtype=float
        ).rank(method="average")
        if signal_ranks.nunique() > 1 and weight_ranks.nunique() > 1:
            correlation = signal_ranks.corr(weight_ranks)
            if pd.notna(correlation):
                spearman = float(correlation)

    return {
        "n_target": n_target,
        "n_eff": n_eff,
        "cap_bound_share": cap_bound_share,
        "spearman_signal_weight": spearman,
    }


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
