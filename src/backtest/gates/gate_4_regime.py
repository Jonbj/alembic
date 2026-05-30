"""Gate 4 – Regime Consistency.

Strategy must perform across market regimes (bull, bear, sideways):
  • Positive Sharpe in bull regime
  • Positive Sharpe in bear regime (or at minimum, not catastrophically negative)
  • Positive Sharpe in sideways regime
The actual threshold is configurable via min_regime_sharpe.
"""
from __future__ import annotations

import pandas as pd

from src.backtest.gates.gate_types import GateResult
from src.backtest.metrics.performance import sharpe_ratio


def gate_4_regime(
    regime_returns: dict[str, pd.Series],
    periods: int = 252,
    min_regime_sharpe: float = 0.0,
    min_passing_regimes: int = 3,
) -> GateResult:
    """Gate 4: Regime consistency.

    Parameters
    ----------
    regime_returns : dict[str, pd.Series]
        Mapping regime name → daily return Series.
        Expected keys: 'bull', 'bear', 'sideways' (but any keys work).
    periods : int
        Annualisation factor.
    min_regime_sharpe : float
        Minimum Sharpe per regime to count as "passing".
    min_passing_regimes : int
        Minimum number of regimes that must pass the Sharpe threshold.

    """
    if not regime_returns:
        return GateResult(passed=False, details={"error": "no regime data provided"})

    regime_sharpes: dict[str, float] = {}
    for name, rets in regime_returns.items():
        sr = float(sharpe_ratio(rets, periods=periods)) if len(rets) >= 2 else 0.0
        regime_sharpes[name] = round(sr, 4)

    n_passing = sum(1 for sr in regime_sharpes.values() if sr > min_regime_sharpe)
    passed = n_passing >= min_passing_regimes

    return GateResult(
        passed=passed,
        details={
            "regime_sharpes": regime_sharpes,
            "n_passing_regimes": n_passing,
            "n_total_regimes": len(regime_sharpes),
            "thresholds": {
                "min_regime_sharpe": min_regime_sharpe,
                "min_passing_regimes": min_passing_regimes,
            },
        },
    )
