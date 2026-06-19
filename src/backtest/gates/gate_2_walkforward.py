"""Gate 2 – Walk-Forward Consistency.

Strategy must demonstrate:
  • Positive out-of-sample Sharpe ratio
  • >= 50% of walk-forward windows with positive Sharpe
"""
from __future__ import annotations

import pandas as pd

from src.backtest.gates.gate_types import GateResult
from src.backtest.metrics.performance import sharpe_ratio


def gate_2_walkforward(
    wf_results: list[pd.Series],
    periods: int = 252,
    min_oos_sharpe: float = 0.0,
    min_positive_fraction: float = 0.5,
) -> GateResult:
    """Gate 2: Walk-forward consistency.

    Parameters
    ----------
    wf_results : list[pd.Series]
        List of out-of-sample return Series, one per walk-forward window.
    periods : int
        Annualisation factor.
    min_oos_sharpe : float
        Minimum aggregate OOS Sharpe (default 0).
    min_positive_fraction : float
        Minimum fraction of windows with positive Sharpe (default 0.5).

    """
    if not wf_results:
        return GateResult(passed=False, details={"error": "no walk-forward windows"})

    window_sharpes = []
    for i, r in enumerate(wf_results):
        sr = sharpe_ratio(r, periods=periods) if len(r) >= 2 else 0.0
        window_sharpes.append(float(sr))

    # Aggregate OOS: concatenate all windows
    all_returns = pd.concat(wf_results, ignore_index=True)
    aggregate_sr = float(sharpe_ratio(all_returns, periods=periods))

    # Denominator is ALL windows, including no-trade (zero-return) windows.
    # Excluding no-trade windows from the denominator cherry-picks the fraction:
    # a strategy that trades in 2/10 windows (both positive) would report 100%
    # positive fraction rather than 20%, hiding the fact it was flat 80% of the time.
    active_sharpes = [
        s for s, r in zip(window_sharpes, wf_results) if r.abs().sum() > 0
    ]
    n_positive = sum(1 for s in window_sharpes if s > 0)
    positive_fraction = n_positive / len(window_sharpes)

    passed = (
        aggregate_sr > min_oos_sharpe
        and positive_fraction >= min_positive_fraction
    )
    return GateResult(
        passed=passed,
        details={
            "oos_sharpe": round(aggregate_sr, 4),
            "n_windows": len(window_sharpes),
            "n_active_windows": len(active_sharpes),
            "n_positive": n_positive,
            "positive_fraction": round(positive_fraction, 4),
            "window_sharpes": [round(s, 4) for s in window_sharpes],
            "thresholds": {
                "min_oos_sharpe": min_oos_sharpe,
                "min_positive_fraction": min_positive_fraction,
            },
        },
    )
