"""Attribution metrics: per-strategy contribution to portfolio return and risk.

Brinson-style return attribution and risk decomposition.
Works with daily return series; weights are assumed to be held constant
within each period (rebalanced externally).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class StrategyContribution:
    """Single-strategy attribution result."""

    name: str
    weight: float
    total_return: float
    annualized_return: float
    annualized_volatility: float
    contribution_to_return: float
    contribution_to_variance: float
    sharpe: float
    correlation_to_portfolio: float


@dataclass
class AttributionResult:
    """Full attribution result for a multi-strategy portfolio."""

    strategies: list[StrategyContribution] = field(default_factory=list)
    portfolio_return: float = 0.0
    portfolio_volatility: float = 0.0
    portfolio_sharpe: float = 0.0
    diversification_ratio: float = 1.0
    n_periods: int = 0


def _safe_sharpe(returns: np.ndarray, periods: int = 252) -> float:
    """Annualised Sharpe; returns 0 when std is zero."""
    if len(returns) < 2:
        return 0.0
    std = float(np.std(returns, ddof=1))
    if std == 0.0:
        return 0.0
    return float(np.mean(returns) / std * np.sqrt(periods))


def strategy_attribution(
    strategy_returns: dict[str, pd.Series],
    weights: dict[str, float],
    periods: int = 252,
) -> AttributionResult:
    """Compute per-strategy return and risk contributions.

    Parameters
    ----------
    strategy_returns:
        Mapping of strategy name → daily return series.  All series must
        share a common DatetimeIndex; they are inner-joined automatically.
    weights:
        Mapping of strategy name → portfolio weight (must sum to ≤ 1).
        Any unweighted residual is treated as cash (zero return).
    periods:
        Trading periods per year for annualisation (default 252).

    Returns
    -------
    AttributionResult with per-strategy StrategyContribution objects and
    aggregate portfolio metrics.
    """
    if not strategy_returns or not weights:
        return AttributionResult()

    names = list(strategy_returns.keys())
    aligned = pd.DataFrame(strategy_returns).dropna()
    if aligned.empty:
        return AttributionResult()

    n = len(aligned)
    w = np.array([weights.get(name, 0.0) for name in names])
    R = aligned[names].values  # shape (n, k)

    # Portfolio daily returns
    port_r = R @ w  # shape (n,)
    port_mean = float(port_r.mean())
    port_std = float(np.std(port_r, ddof=1))
    port_total = float((1.0 + port_r).prod() - 1.0)
    port_ann_ret = float((1.0 + port_total) ** (periods / n) - 1.0) if n > 0 else 0.0
    port_ann_vol = float(port_std * np.sqrt(periods))
    port_sharpe = _safe_sharpe(port_r, periods)

    # Covariance matrix of strategies
    cov = np.cov(R.T, ddof=1)  # shape (k, k)
    if cov.ndim == 0:
        cov = np.array([[cov]])

    # Diversification ratio: weighted avg vol / portfolio vol
    indiv_vols = np.sqrt(np.diag(cov))
    weighted_avg_vol = float(w @ indiv_vols) * np.sqrt(periods)
    diversification_ratio = weighted_avg_vol / port_ann_vol if port_ann_vol > 0 else 1.0

    contributions: list[StrategyContribution] = []
    for i, name in enumerate(names):
        r_i = R[:, i]
        wi = float(w[i])
        total_i = float((1.0 + r_i).prod() - 1.0)
        ann_ret_i = float((1.0 + total_i) ** (periods / n) - 1.0) if n > 0 else 0.0
        ann_vol_i = float(np.std(r_i, ddof=1) * np.sqrt(periods))

        # Contribution to portfolio return: w_i * mean_i (additive)
        contrib_return = wi * float(np.mean(r_i))

        # Marginal risk contribution: w_i * (Σw)_i / σ_p
        # (Σw)_i = covariance of strategy i with the portfolio
        cov_with_port = float(cov[i] @ w)
        contrib_var = wi * cov_with_port  # fractional variance contribution

        # Correlation with portfolio
        if indiv_vols[i] > 0 and port_std > 0:
            corr = float(np.corrcoef(r_i, port_r)[0, 1])
        else:
            corr = 0.0

        contributions.append(StrategyContribution(
            name=name,
            weight=wi,
            total_return=total_i,
            annualized_return=ann_ret_i,
            annualized_volatility=ann_vol_i,
            contribution_to_return=contrib_return,
            contribution_to_variance=contrib_var,
            sharpe=_safe_sharpe(r_i, periods),
            correlation_to_portfolio=corr,
        ))

    return AttributionResult(
        strategies=contributions,
        portfolio_return=port_ann_ret,
        portfolio_volatility=port_ann_vol,
        portfolio_sharpe=port_sharpe,
        diversification_ratio=diversification_ratio,
        n_periods=n,
    )
