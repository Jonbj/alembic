"""Gate 1 – Statistical Significance.

Strategy must demonstrate:
  • Positive Sharpe ratio
  • p-value < 0.05 (t-test that SR > 0)
  • Deflated Sharpe Ratio (DSR) > 0.5
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from src.backtest.gates.gate_types import GateResult
from src.backtest.metrics.performance import sharpe_ratio
from src.backtest.metrics.signal_quality import deflated_sharpe_ratio


def _sr_pvalue(returns: pd.Series, periods: int = 252) -> float:
    """Two-sided p-value for H0: Sharpe Ratio == 0.

    Uses the asymptotic normal approximation of SR distribution.
    """
    n = len(returns)
    if n < 2:
        return 1.0
    sr = sharpe_ratio(returns, periods=periods)
    se = np.sqrt((1.0 + 0.5 * sr ** 2) / n) if n > 0 else float("inf")
    if se == 0:
        return 1.0
    t_stat = sr / se
    return float(2 * (1 - scipy_stats.norm.cdf(abs(t_stat))))


def gate_1_significance(
    returns: pd.Series,
    n_trials: int = 1,
    periods: int = 252,
    min_sharpe: float = 0.0,
    max_pvalue: float = 0.05,
    min_dsr: float = 0.5,
) -> GateResult:
    """Gate 1: Statistical significance of the Sharpe ratio."""
    sr = sharpe_ratio(returns, periods=periods)
    pval = _sr_pvalue(returns, periods=periods)

    # Compute skewness and excess kurtosis for DSR
    skew_val = float(returns.skew()) if len(returns) >= 3 else 0.0
    kurt_val = float(returns.kurtosis()) if len(returns) >= 4 else 0.0  # excess kurt

    dsr = deflated_sharpe_ratio(
        observed_sr=sr,
        n_trials=n_trials,
        n_obs=len(returns),
        skew=skew_val,
        excess_kurt=kurt_val,
    )

    passed = sr > min_sharpe and pval < max_pvalue and dsr > min_dsr
    return GateResult(
        passed=passed,
        details={
            "sharpe": round(float(sr), 4),
            "p_value": round(float(pval), 6),
            "dsr": round(float(dsr), 4),
            "thresholds": {
                "min_sharpe": min_sharpe,
                "max_pvalue": max_pvalue,
                "min_dsr": min_dsr,
            },
        },
    )
