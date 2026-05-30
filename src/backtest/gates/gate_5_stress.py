"""Gate 5 – Stress Testing.

Strategy must survive known stress periods (2008 GFC, 2020 COVID, 2022 rate hikes):
  • Positive cumulative return in each stress period (or within tolerance)
  • Maximum drawdown within acceptable bounds during stress periods
"""
from __future__ import annotations

import pandas as pd

from src.backtest.gates.gate_types import GateResult
from src.backtest.metrics.performance import sharpe_ratio
from src.backtest.metrics.risk import max_drawdown


def gate_5_stress(
    stress_returns: dict[str, pd.Series],
    periods: int = 252,
    min_cumulative_return: float = -0.10,
    max_drawdown_allowed: float = -0.30,
) -> GateResult:
    """Gate 5: Stress period survival.

    Parameters
    ----------
    stress_returns : dict[str, pd.Series]
        Mapping stress period name → daily return Series.
        Expected keys: '2008_gfc', '2020_covid', '2022_rate_hikes'.
    periods : int
        Annualisation factor.
    min_cumulative_return : float
        Minimum cumulative return allowed in each stress period.
        0.0 means no loss is tolerated; use negative to allow some loss.
    max_drawdown_allowed : float
        Maximum acceptable drawdown (negative, e.g. -0.30 means -30%).

    """
    if not stress_returns:
        return GateResult(passed=False, details={"error": "no stress period data"})

    period_results: dict[str, dict] = {}
    n_passing = 0

    for name, rets in stress_returns.items():
        if len(rets) < 2:
            period_results[name] = {
                "cumulative_return": 0.0,
                "max_drawdown": 0.0,
                "sharpe": 0.0,
                "passed": False,
            }
            continue

        cum_ret = float((1 + rets).prod() - 1)
        mdd = float(max_drawdown(rets))
        sr = float(sharpe_ratio(rets, periods=periods))

        period_passed = cum_ret > min_cumulative_return and mdd > max_drawdown_allowed
        if period_passed:
            n_passing += 1

        period_results[name] = {
            "cumulative_return": round(cum_ret, 4),
            "max_drawdown": round(mdd, 4),
            "sharpe": round(sr, 4),
            "passed": period_passed,
        }

    passed = n_passing == len(stress_returns)

    return GateResult(
        passed=passed,
        details={
            "period_results": period_results,
            "n_passing": n_passing,
            "n_total": len(stress_returns),
            "thresholds": {
                "min_cumulative_return": min_cumulative_return,
                "max_drawdown_allowed": max_drawdown_allowed,
            },
        },
    )
