"""Performance metrics: Sharpe, Sortino, Calmar, annualized return/vol, Omega.

All formulas match empyrical 0.5.5 (same numerical output on identical inputs).
Reference: github.com/quantopian/empyrical/blob/master/empyrical/stats.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def annualized_return(returns: pd.Series, periods: int = TRADING_DAYS) -> float:
    """Geometric annualized return.

    Matches empyrical.annual_return (period='daily').
    """
    if len(returns) == 0:
        return 0.0
    ending_value = float((1.0 + returns).prod())
    if ending_value <= 0:
        return -1.0
    num_years = len(returns) / periods
    return float(ending_value ** (1.0 / num_years) - 1.0)


def annualized_volatility(returns: pd.Series, periods: int = TRADING_DAYS) -> float:
    """Annualized volatility (std of returns scaled by sqrt(periods)).

    Matches empyrical.annual_volatility (ddof=1).
    """
    if len(returns) < 2:
        return 0.0
    return float(returns.std(ddof=1) * np.sqrt(periods))


def sharpe_ratio(
    returns: pd.Series,
    risk_free: float = 0.0,
    periods: int = TRADING_DAYS,
) -> float:
    """Annualized Sharpe ratio.

    Formula: mean(r - rf_daily) / std(r - rf_daily, ddof=1) * sqrt(periods)
    risk_free is the annual risk-free rate. Matches empyrical.sharpe_ratio.
    """
    if len(returns) < 2:
        return 0.0
    rf_per_period = risk_free / periods
    excess = returns - rf_per_period
    std = float(excess.std(ddof=1))
    if std < 1e-14:
        return 0.0
    return float(excess.mean() / std * np.sqrt(periods))


def sortino_ratio(
    returns: pd.Series,
    required_return: float = 0.0,
    periods: int = TRADING_DAYS,
) -> float:
    """Annualized Sortino ratio (penalises only downside volatility).

    Formula: mean(r - mar) / sqrt(mean(min(r-mar, 0)^2)) * sqrt(periods)
    Uses mean of squared downside deviations (not std with ddof).
    Matches empyrical.sortino_ratio.
    """
    if len(returns) < 2:
        return 0.0
    mar = required_return / periods
    adj = returns - mar
    downside = np.minimum(adj, 0.0)
    downside_variance = float((downside ** 2).mean())
    if downside_variance < 1e-28:
        return 0.0
    downside_dev = np.sqrt(downside_variance)
    return float(float(adj.mean()) / downside_dev * np.sqrt(periods))


def calmar_ratio(
    returns: pd.Series,
    periods: int = TRADING_DAYS,
) -> float:
    """Calmar ratio = annualized_return / abs(max_drawdown).

    Returns 0.0 when max drawdown is zero (monotonically increasing NAV).
    Matches empyrical.calmar_ratio.
    """
    from src.backtest.metrics.risk import max_drawdown as _mdd
    ann_ret = annualized_return(returns, periods)
    mdd = _mdd(returns)
    if mdd == 0.0:
        return 0.0
    return float(ann_ret / abs(mdd))


def omega_ratio(
    returns: pd.Series,
    required_return: float = 0.0,
    periods: int = TRADING_DAYS,
) -> float:
    """Omega ratio: probability-weighted ratio of gains to losses above threshold.

    Matches empyrical.omega_ratio signature.
    """
    mar = required_return / periods
    gains = float((returns[returns > mar] - mar).sum())
    losses = float((mar - returns[returns < mar]).sum())
    if losses == 0.0:
        return np.inf if gains > 0 else 1.0
    return float(gains / losses)
