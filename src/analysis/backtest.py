"""Pure backtest functions for GDELT A/B test."""

from dataclasses import dataclass

import numpy as np

from src.performance.ic import compute_composite_ic


@dataclass
class ABResult:
    """A/B comparison result between GDELT-driven and buy-and-hold strategies."""
    sharpe_baseline: float
    sharpe_gdelt: float
    delta_sharpe: float
    composite_ic: float
    coverage_pct: float
    n_signals: int
    n_trading_days: int
    gate_passed: bool


def compute_sharpe(returns: list[float], annualization: int = 252) -> float:
    """Annualized Sharpe ratio. Returns 0.0 for empty or zero-variance inputs."""
    arr = np.array(returns, dtype=float)
    if len(arr) < 2:
        return 0.0
    std = float(np.std(arr, ddof=1))
    if std == 0.0:
        return 0.0
    return float(np.mean(arr) / std * np.sqrt(annualization))


def compute_signal_returns(
    daily_scores: list[float],
    fwd_returns: list[float],
) -> list[float]:
    """Long if score>0, short if score<0, flat if score=0."""
    if len(daily_scores) != len(fwd_returns):
        raise ValueError("daily_scores and fwd_returns must have the same length")
    result = []
    for score, ret in zip(daily_scores, fwd_returns):
        if score > 0:
            result.append(ret)
        elif score < 0:
            result.append(-ret)
        else:
            result.append(0.0)
    return result


def run_ab_comparison(
    daily_scores: list[float],
    fwd_returns: list[float],
    n_articles: int,
    threshold: float = 0.10,
) -> ABResult:
    """Compare GDELT-driven strategy vs buy-and-hold. Gate: delta_Sharpe >= threshold."""
    gdelt_returns = compute_signal_returns(daily_scores, fwd_returns)
    sharpe_baseline = compute_sharpe(fwd_returns)
    sharpe_gdelt = compute_sharpe(gdelt_returns)
    delta_sharpe = sharpe_gdelt - sharpe_baseline

    active_idx = [i for i, s in enumerate(daily_scores) if s != 0.0]
    if active_idx:
        ic_result = compute_composite_ic(
            [daily_scores[i] for i in active_idx],
            [fwd_returns[i] for i in active_idx],
        )
        composite_ic = ic_result.composite_ic
    else:
        composite_ic = 0.0

    n_trading_days = len(daily_scores)
    covered = sum(1 for s in daily_scores if s != 0.0)
    coverage_pct = (covered / n_trading_days * 100.0) if n_trading_days > 0 else 0.0

    return ABResult(
        sharpe_baseline=sharpe_baseline,
        sharpe_gdelt=sharpe_gdelt,
        delta_sharpe=delta_sharpe,
        composite_ic=composite_ic,
        coverage_pct=coverage_pct,
        n_signals=n_articles,
        n_trading_days=n_trading_days,
        gate_passed=delta_sharpe >= threshold,
    )
