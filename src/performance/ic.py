"""
Information Coefficient (IC) computation module.

Implements:
- Composite IC (formula B4): 0.5×Spearman + 0.3×weighted_hit_rate + 0.2×(1−Brier)
- Newey-West HAC variance estimation for autocorrelated returns
- ICIR (Information Coefficient Information Ratio) with HAC correction
"""
import numpy as np
from scipy.stats import spearmanr
from dataclasses import dataclass
from typing import Optional


@dataclass
class ICResult:
    """Result of IC computation."""
    composite_ic: float
    spearman_ic: float
    weighted_hit_rate: float
    brier_score: float
    sample_count: int


@dataclass
class ICIRResult:
    """Result of ICIR computation with Newey-West correction."""
    icir: float
    ic_mean: float
    ic_std: float
    newey_west_std: Optional[float]
    lag: int
    sample_count: int = 0


def compute_composite_ic(scores: list[float], forward_returns: list[float],
                         confidences: Optional[list[float]] = None) -> ICResult:
    """
    Compute composite IC using formula B4.

    Composite IC = 0.5 × Spearman + 0.3 × weighted_hit_rate + 0.2 × (1 − Brier)

    Where:
    - Spearman: rank correlation between scores and forward_returns
    - weighted_hit_rate: % of correct sign predictions, weighted by confidence
    - Brier score: mean squared error between predicted direction and actual direction

    Args:
        scores: LLM sentiment scores (range [-1, +1])
        forward_returns: Realized forward returns over the prediction horizon
        confidences: Model confidences (range [0, 1]). If None, uses equal weights.

    Returns:
        ICResult with all components and sample count
    """
    if len(scores) != len(forward_returns):
        raise ValueError("scores and forward_returns must have same length")
    if len(scores) == 0:
        raise ValueError("scores cannot be empty")

    scores_arr = np.array(scores)
    returns_arr = np.array(forward_returns)
    n = len(scores_arr)

    # Handle confidences
    if confidences is None:
        conf_arr = np.ones(n)
    else:
        if len(confidences) != n:
            raise ValueError("confidences must have same length as scores")
        conf_arr = np.array(confidences)

    # 1. Spearman correlation (rank correlation)
    # Handle constant arrays (would cause spearman to return nan)
    if np.std(scores_arr) == 0 or np.std(returns_arr) == 0:
        spearman_ic = 0.0
    else:
        spearman_ic = float(spearmanr(scores_arr, returns_arr).correlation)
        if np.isnan(spearman_ic):
            spearman_ic = 0.0

    # 2. Weighted hit rate
    # Hit = sign(score) == sign(return). Zero score counts as miss.
    score_signs = np.sign(scores_arr)
    return_signs = np.sign(returns_arr)
    hits = (score_signs == return_signs) & (score_signs != 0) & (return_signs != 0)

    # Weighted hit rate: sum(confidence * hit) / sum(confidence)
    total_conf = np.sum(conf_arr)
    if total_conf > 0:
        weighted_hit_rate = float(np.sum(conf_arr * hits.astype(float)) / total_conf)
    else:
        weighted_hit_rate = 0.0

    # 3. Brier score
    # polarity = predicted probability of positive return
    # Map score [-1, +1] to probability [0, 1]: p = (score + 1) / 2
    # actual_direction: 1 if return > 0, 0 if return <= 0
    predicted_probs = (scores_arr + 1) / 2
    actual_directions = (returns_arr > 0).astype(float)
    brier_score = float(np.mean((predicted_probs - actual_directions) ** 2))

    # 4. Composite IC (formula B4)
    composite_ic = 0.5 * spearman_ic + 0.3 * weighted_hit_rate + 0.2 * (1 - brier_score)

    return ICResult(
        composite_ic=composite_ic,
        spearman_ic=spearman_ic,
        weighted_hit_rate=weighted_hit_rate,
        brier_score=brier_score,
        sample_count=n,
    )


def compute_newey_west_hac(values: list[float], lag: Optional[int] = None) -> float:
    """
    Compute Newey-West HAC (Heteroskedasticity and Autocorrelation Consistent)
    standard error for a series of values.

    The Newey-West estimator corrects for both heteroskedasticity and
    autocorrelation up to a specified lag order.

    Formula:
        Var_hac = (1/T) * [Sigma_0 + 2 * Sigma_{j=1}^{m} w_j * Sigma_j]

        where:
        - Sigma_0 = sum of squared deviations (variance term)
        - Sigma_j = sum of j-th order autocovariances
        - w_j = 1 - j/(m+1) (Bartlett weights)
        - m = lag order

    Args:
        values: Time series of values (e.g., per-period IC values)
        lag: Maximum lag for autocorrelation correction.
             If None, uses floor(4 * (n/100)^(2/9)) as rule of thumb.

    Returns:
        HAC-corrected standard error
    """
    values_arr = np.array(values)
    n = len(values_arr)

    if n == 0:
        raise ValueError("values cannot be empty")
    if n == 1:
        return 0.0

    # Center the values
    mean_val = np.mean(values_arr)
    centered = values_arr - mean_val

    # Determine lag using rule of thumb if not specified
    # lag = floor(4 * (n/100)^(2/9))
    if lag is None:
        lag = int(np.floor(4 * (n / 100) ** (2 / 9)))
    lag = min(lag, n - 1)  # Cannot have lag >= n

    if lag < 1:
        # No autocorrelation correction needed, return simple std error
        return float(np.std(values_arr, ddof=1) / np.sqrt(n))

    # Newey-West HAC variance estimator for the mean
    # Var(mean) = (1/n) * [gamma_0 + 2 * sum_{j=1}^{m} w_j * gamma_j]
    # where gamma_j = (1/n) * sum(centered_t * centered_{t-j}) is the j-th autocovariance

    # gamma_0: variance (autocovariance at lag 0)
    gamma_0 = np.mean(centered ** 2)

    # Autocovariance terms for each lag
    autocov_sum = 0.0
    for j in range(1, lag + 1):
        # j-th order autocovariance (averaged)
        gamma_j = np.mean(centered[:-j] * centered[j:])
        # Bartlett weight: w_j = 1 - j/(m+1)
        weight = 1.0 - j / (lag + 1)
        autocov_sum += weight * gamma_j

    # Newey-West variance of the mean
    nw_variance = (1.0 / n) * (gamma_0 + 2 * autocov_sum)

    # Ensure non-negative variance (can be slightly negative due to numerical issues)
    nw_variance = max(0.0, nw_variance)

    # Standard error = sqrt(variance)
    nw_std_error = np.sqrt(nw_variance)

    return float(nw_std_error)


def compute_icir(scores: list[float], forward_returns: list[float],
                 confidences: Optional[list[float]] = None,
                 use_newey_west: bool = True,
                 lag: Optional[int] = None,
                 min_samples: int = 30) -> ICIRResult:
    """
    Compute ICIR (Information Coefficient Information Ratio) with optional
    Newey-West HAC correction.

    ICIR = IC_mean / IC_std

    When use_newey_west=True, uses HAC-corrected standard deviation to account
    for autocorrelation in returns (common in financial time series).

    For rolling IC computation:
    - Splits data into overlapping windows
    - Computes composite IC for each window
    - IC_mean = mean of rolling ICs
    - IC_std = std of rolling ICs (or Newey-West corrected)

    Args:
        scores: LLM sentiment scores (range [-1, +1])
        forward_returns: Realized forward returns
        confidences: Model confidences (range [0, 1])
        use_newey_west: Whether to use Newey-West HAC correction
        lag: Lag for Newey-West. Auto-computed if None.
        min_samples: Minimum samples required. Returns icir=0 if below threshold.

    Returns:
        ICIRResult with icir, ic_mean, ic_std, and newey_west_std if computed
    """
    if len(scores) != len(forward_returns):
        raise ValueError("scores and forward_returns must have same length")

    n = len(scores)
    if n < min_samples:
        return ICIRResult(
            icir=0.0,
            ic_mean=0.0,
            ic_std=0.0,
            newey_west_std=None,
            lag=0,
        )

    # Compute rolling IC for each observation
    # Using a window-based approach for stability
    # Window size: min(30, n//2) to ensure enough windows
    window_size = min(30, max(10, n // 2))
    step = max(1, window_size // 3)  # Overlapping windows

    rolling_ics = []
    for start in range(0, n - window_size + 1, step):
        end = start + window_size
        window_scores = scores[start:end]
        window_returns = forward_returns[start:end]
        window_confs = confidences[start:end] if confidences else None

        ic_result = compute_composite_ic(window_scores, window_returns, window_confs)
        rolling_ics.append(ic_result.composite_ic)

    if len(rolling_ics) < 2:
        # Not enough windows for std computation
        # Fall back to single IC
        ic_result = compute_composite_ic(scores, forward_returns, confidences)
        return ICIRResult(
            icir=0.0,  # Cannot compute ratio without std
            ic_mean=ic_result.composite_ic,
            ic_std=0.0,
            newey_west_std=None,
            lag=0,
        )

    ics_arr = np.array(rolling_ics)
    ic_mean = float(np.mean(ics_arr))
    ic_std_simple = float(np.std(ics_arr, ddof=1))

    # Newey-West HAC correction
    newey_west_std = None
    actual_lag = 0

    if use_newey_west:
        newey_west_std = compute_newey_west_hac(rolling_ics, lag)
        actual_lag = lag if lag is not None else int(np.floor(4 * (len(rolling_ics) / 100) ** (2 / 9)))
        actual_lag = min(actual_lag, len(rolling_ics) - 1)
        # Use Newey-West std for ICIR if available and non-zero
        ic_std_for_ratio = newey_west_std if newey_west_std > 0 else ic_std_simple
    else:
        ic_std_for_ratio = ic_std_simple

    # ICIR = IC_mean / IC_std
    if ic_std_for_ratio > 0:
        icir = ic_mean / ic_std_for_ratio
    else:
        icir = 0.0

    return ICIRResult(
        icir=icir,
        ic_mean=ic_mean,
        ic_std=ic_std_simple,
        newey_west_std=newey_west_std,
        lag=actual_lag,
        sample_count=n,
    )
