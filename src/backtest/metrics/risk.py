"""Risk metrics: max drawdown, VaR, ES, tail ratio, skewness, kurtosis.

All formulas match empyrical 0.5.5 (same numerical output on identical inputs).
Reference: github.com/quantopian/empyrical/blob/master/empyrical/stats.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats


def max_drawdown(returns: pd.Series) -> float:
    """Maximum peak-to-trough drawdown (≤ 0).

    Prepends 1.0 to the cumulative return series so the very first negative
    bar is captured. Matches empyrical.max_drawdown.
    """
    if len(returns) == 0:
        return 0.0
    cumulative = np.empty(len(returns) + 1)
    cumulative[0] = 1.0
    np.cumprod(1.0 + np.asarray(returns), out=cumulative[1:])
    peak = np.fmax.accumulate(cumulative)
    drawdown = (cumulative - peak) / peak
    return float(np.nanmin(drawdown))


def drawdown_series(returns: pd.Series) -> pd.Series:
    """Per-timestep drawdown relative to previous peak (≤ 0).

    Returned series is aligned with the input returns index.
    """
    if len(returns) == 0:
        return pd.Series(dtype=float)
    cumulative = np.empty(len(returns) + 1)
    cumulative[0] = 1.0
    np.cumprod(1.0 + np.asarray(returns), out=cumulative[1:])
    peak = np.fmax.accumulate(cumulative)
    dd = (cumulative - peak) / peak
    return pd.Series(dd[1:], index=returns.index)


def value_at_risk(returns: pd.Series, cutoff: float = 0.05) -> float:
    """Historical VaR at given confidence level (negative number = loss).

    cutoff=0.05 → 5th percentile (95% VaR).
    Matches empyrical.value_at_risk.
    """
    if len(returns) == 0:
        return 0.0
    return float(np.percentile(returns, 100.0 * cutoff))


def expected_shortfall(returns: pd.Series, cutoff: float = 0.05) -> float:
    """Expected shortfall (CVaR): mean of worst `cutoff` fraction of returns.

    Formula matches empyrical.conditional_value_at_risk exactly:
        cutoff_index = int((n-1) * cutoff)
        ES = mean of the (cutoff_index+1) smallest returns
    Uses np.partition for O(n) selection (same as empyrical).
    """
    n = len(returns)
    if n == 0:
        return 0.0
    arr = np.asarray(returns)
    cutoff_index = int((n - 1) * cutoff)
    return float(np.mean(np.partition(arr, cutoff_index)[: cutoff_index + 1]))


def tail_ratio(returns: pd.Series) -> float:
    """Ratio of 95th percentile gain to abs(5th percentile loss).

    Matches empyrical.tail_ratio.
    """
    if len(returns) == 0:
        return np.nan
    p95 = np.percentile(returns, 95)
    p5 = np.percentile(returns, 5)
    if p5 == 0.0:
        return np.nan
    return float(abs(p95) / abs(p5))


def skewness(returns: pd.Series) -> float:
    """Sample skewness of return distribution.

    Uses scipy.stats.skew (Fisher's definition, bias=True).
    """
    if len(returns) < 3:
        return 0.0
    return float(scipy_stats.skew(returns, bias=True))


def excess_kurtosis(returns: pd.Series) -> float:
    """Excess kurtosis of return distribution (Fisher definition, normal = 0).

    Uses scipy.stats.kurtosis (excess=True by default, bias=True).
    """
    if len(returns) < 4:
        return 0.0
    return float(scipy_stats.kurtosis(returns, bias=True, fisher=True))
