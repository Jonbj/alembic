"""Signal quality metrics: IC, ICIR, p-value, Deflated Sharpe Ratio.

IC (Information Coefficient) measures cross-sectional predictive power of a
signal: Spearman rank correlation between predicted and realised ranks.

ICIR = mean(IC_t) / std(IC_t) annualised — analogous to Sharpe for signals.

DSR (Deflated Sharpe Ratio) corrects the observed Sharpe ratio for multiple
testing and non-normality.  Reference: Bailey & López de Prado (2014),
"The Deflated Sharpe Ratio: Correcting for Selection Bias, Non-Normality,
and Non-Stationarity", Journal of Portfolio Management 40(5), 94-107.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

_EULER_GAMMA = 0.5772156649  # Euler-Mascheroni constant


def information_coefficient(
    signals: pd.Series | np.ndarray,
    forward_returns: pd.Series | np.ndarray,
) -> float:
    """Cross-sectional IC: Spearman rank correlation between signal and return.

    Returns NaN when fewer than 3 observations or constant input.
    """
    s = np.asarray(signals, dtype=float)
    r = np.asarray(forward_returns, dtype=float)
    if len(s) < 3:
        return float("nan")
    if np.std(s) == 0 or np.std(r) == 0:
        return 0.0
    corr, _ = scipy_stats.spearmanr(s, r)
    return float(corr) if not np.isnan(corr) else 0.0


def ic_pvalue(
    signals: pd.Series | np.ndarray,
    forward_returns: pd.Series | np.ndarray,
) -> float:
    """Two-tailed p-value for the IC under H₀: ρ = 0.

    Uses the t-distribution with df = n - 2.
    """
    s = np.asarray(signals, dtype=float)
    r = np.asarray(forward_returns, dtype=float)
    n = len(s)
    if n < 3:
        return 1.0
    _, pval = scipy_stats.spearmanr(s, r)
    return float(pval)


def icir(
    signals_panel: pd.DataFrame,
    forward_returns_panel: pd.DataFrame,
    annualisation: int = 252,
) -> float:
    """Annualised ICIR from cross-sectional panels.

    Parameters
    ----------
    signals_panel:
        DataFrame indexed by date, columns = tickers.  Each row is a
        cross-section of signals for that date.
    forward_returns_panel:
        Same shape as signals_panel.  Each row is the realised return
        for the next holding period.
    annualisation:
        Number of periods per year (252 for daily, 52 for weekly, …).

    Returns
    -------
    ICIR = mean(IC_t) / std(IC_t, ddof=1) * sqrt(annualisation)
    """
    if signals_panel.empty or forward_returns_panel.empty:
        return float("nan")

    ic_series: list[float] = []
    common_dates = signals_panel.index.intersection(forward_returns_panel.index)
    for date in common_dates:
        s = signals_panel.loc[date].dropna()
        r = forward_returns_panel.loc[date].dropna()
        common_tickers = s.index.intersection(r.index)
        if len(common_tickers) < 3:
            continue
        ic = information_coefficient(s.loc[common_tickers], r.loc[common_tickers])
        if not np.isnan(ic):
            ic_series.append(ic)

    if len(ic_series) < 2:
        return float("nan")

    arr = np.array(ic_series)
    std = float(arr.std(ddof=1))
    if std == 0.0:
        return 0.0
    return float(arr.mean() / std * np.sqrt(annualisation))


def icir_from_series(ic_series: pd.Series | list[float], annualisation: int = 1) -> float:
    """ICIR from a pre-computed time series of per-period IC values.

    ICIR = mean(IC_t) / std(IC_t, ddof=1) * sqrt(annualisation)
    annualisation=1 returns the raw ratio without time scaling.
    """
    arr = np.asarray(ic_series, dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 2:
        return float("nan")
    std = float(arr.std(ddof=1))
    if std == 0.0:
        return 0.0
    return float(arr.mean() / std * np.sqrt(annualisation))


def sharpe_ratio_se(
    observed_sr: float,
    n_obs: int,
    skew: float = 0.0,
    excess_kurt: float = 0.0,
) -> float:
    """Standard error of the Sharpe ratio adjusted for non-normality.

    From Bailey & López de Prado (2014), Eq. 2:
        σ(SR) = sqrt((1 - γ₃·SR + (γ₄/4)·SR²) / (T-1))

    where γ₃ = skewness and γ₄ = excess kurtosis.
    """
    if n_obs <= 1:
        return float("inf")
    variance = (1.0 - skew * observed_sr + (excess_kurt / 4.0) * observed_sr ** 2) / (n_obs - 1)
    return float(np.sqrt(max(variance, 0.0)))


def expected_max_sharpe(n_trials: int, n_obs: int) -> float:
    """Expected maximum Sharpe ratio from n_trials independent backtests.

    From Bailey & López de Prado (2014), Eq. 7:
        SR* = ((1−γ_EM)·Φ⁻¹(1−1/n) + γ_EM·Φ⁻¹(1−1/(n·e))) / sqrt(T−1)

    where γ_EM is the Euler-Mascheroni constant (≈ 0.5772).
    """
    if n_trials <= 1 or n_obs <= 1:
        return 0.0
    z1 = float(scipy_stats.norm.ppf(1.0 - 1.0 / n_trials))
    z2 = float(scipy_stats.norm.ppf(1.0 - 1.0 / (n_trials * np.e)))
    return float(((1.0 - _EULER_GAMMA) * z1 + _EULER_GAMMA * z2) / np.sqrt(n_obs - 1))


def deflated_sharpe_ratio(
    observed_sr: float,
    n_trials: int,
    n_obs: int,
    skew: float = 0.0,
    excess_kurt: float = 0.0,
    benchmark_sr: float = 0.0,
) -> float:
    """Deflated Sharpe Ratio (DSR).

    Probability that the observed Sharpe ratio survives multiple testing,
    corrected for non-normality of returns.

    From Bailey & López de Prado (2014), Eq. 8:
        DSR = Φ[(SR_obs - SR*) / σ(SR_obs)]

    Parameters
    ----------
    observed_sr:
        Sample Sharpe ratio of the strategy under evaluation (annualised).
    n_trials:
        Number of independent strategies/parameter sets tried.
    n_obs:
        Number of return observations (e.g. trading days).
    skew:
        Skewness of the return series (scipy convention).
    excess_kurt:
        Excess kurtosis of the return series (scipy convention, normal = 0).
    benchmark_sr:
        Additive adjustment to SR* (use 0 unless you have a prior).

    Returns
    -------
    float in [0, 1]: probability that the strategy is genuinely skilled.
    """
    sr_star = expected_max_sharpe(n_trials, n_obs) + benchmark_sr
    se = sharpe_ratio_se(observed_sr, n_obs, skew, excess_kurt)
    if se == 0.0 or not np.isfinite(se):
        return float(scipy_stats.norm.cdf(observed_sr - sr_star))
    return float(scipy_stats.norm.cdf((observed_sr - sr_star) / se))
