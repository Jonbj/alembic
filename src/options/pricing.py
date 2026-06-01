"""Black-Scholes option pricing, Greeks, and implied volatility solver.

Provides a standalone pricing library used by both the option chain ingestion
pipeline (src.data.options.ingestion) and strategy/signal modules.
"""

from __future__ import annotations

import math

from scipy.special import ndtr  # standard normal CDF, faster than scipy.stats.norm


def black_scholes_price(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    right: str,
) -> float:
    """Price a European option using Black-Scholes.

    Args:
        S:     underlying price
        K:     strike price
        T:     time to expiry in years (0 = expired at this instant)
        r:     continuously compounded risk-free rate (e.g. 0.05)
        sigma: implied volatility (e.g. 0.20)
        right: 'C' for call, 'P' for put

    Returns:
        Option price >= 0.
    """
    if T <= 0:
        if right == "C":
            return max(S - K, 0.0)
        return max(K - S, 0.0)

    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    disc = math.exp(-r * T)

    if right == "C":
        return S * ndtr(d1) - K * disc * ndtr(d2)
    return K * disc * ndtr(-d2) - S * ndtr(-d1)


def compute_greeks(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    right: str,
) -> dict[str, float]:
    """Compute first-order Greeks (delta, gamma, theta, vega).

    Args:
        S, K, T, r, sigma, right: same as black_scholes_price

    Returns:
        Dict with keys: delta, gamma, theta, vega
        theta is per calendar day.
        vega is per 1% change in implied vol.
    """
    if T <= 0:
        if right == "C":
            delta = 1.0 if S > K else 0.0
        else:
            delta = -1.0 if S < K else 0.0
        return {"delta": delta, "gamma": 0.0, "theta": 0.0, "vega": 0.0}

    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T

    # Standard normal PDF at d1
    phi_d1 = math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi)
    disc = math.exp(-r * T)

    delta = ndtr(d1) if right == "C" else ndtr(d1) - 1.0
    gamma = phi_d1 / (S * sigma * sqrt_T)

    theta_base = -(S * phi_d1 * sigma) / (2 * sqrt_T)
    if right == "C":
        theta = (theta_base - r * K * disc * ndtr(d2)) / 365
    else:
        theta = (theta_base + r * K * disc * ndtr(-d2)) / 365

    # Vega: per 1% change in vol
    vega = S * phi_d1 * sqrt_T / 100

    return {"delta": delta, "gamma": gamma, "theta": theta, "vega": vega}


def implied_vol(
    market_price: float,
    S: float,
    K: float,
    T: float,
    r: float,
    right: str,
    *,
    tol: float = 1e-6,
    max_iter: int = 50,
) -> float:
    """Solve for implied volatility using Newton-Raphson with bisection fallback.

    Args:
        market_price: observed option market price (mid or last)
        S, K, T, r, right: same as black_scholes_price
        tol:      convergence tolerance on price difference
        max_iter: maximum Newton-Raphson iterations before falling back

    Returns:
        Implied volatility sigma such that BS(sigma) ≈ market_price.

    Raises:
        ValueError: if T <= 0, market_price <= 0, or no solution exists in
                    the valid volatility range [1e-4, 10.0].
    """
    if T <= 0:
        raise ValueError("T must be positive for implied vol computation")
    if market_price <= 0:
        raise ValueError(f"market_price must be positive, got {market_price}")

    _LO_SIGMA, _HI_SIGMA = 1e-4, 10.0
    lo_price = black_scholes_price(S, K, T, r, _LO_SIGMA, right)
    hi_price = black_scholes_price(S, K, T, r, _HI_SIGMA, right)

    if market_price < lo_price - tol:
        raise ValueError(
            f"market_price {market_price:.4f} is below the minimum achievable "
            f"BS price {lo_price:.4f} (below no-arbitrage lower bound)"
        )
    if market_price > hi_price + tol:
        raise ValueError(
            f"market_price {market_price:.4f} exceeds maximum achievable "
            f"BS price {hi_price:.4f} at sigma={_HI_SIGMA}"
        )

    # Brenner-Subrahmanyam approximation for ATM: good initial guess
    sigma = market_price / S * math.sqrt(2 * math.pi / T)
    sigma = max(_LO_SIGMA, min(_HI_SIGMA, sigma))

    # Newton-Raphson: f(sigma) = BS(sigma) - market_price; f'(sigma) = vega
    sqrt_T = math.sqrt(T)
    for _ in range(max_iter):
        price = black_scholes_price(S, K, T, r, sigma, right)
        diff = price - market_price
        if abs(diff) < tol:
            return sigma

        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
        phi_d1 = math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi)
        vega = S * phi_d1 * sqrt_T  # dBS/dsigma (actual, not per-1%)

        if abs(vega) < 1e-12:
            break  # degenerate vega — fall through to bisection

        sigma -= diff / vega
        sigma = max(_LO_SIGMA, min(_HI_SIGMA, sigma))

    # Bisection fallback — guaranteed convergence within [lo, hi]
    lo, hi = _LO_SIGMA, _HI_SIGMA
    for _ in range(100):
        mid = (lo + hi) / 2
        mid_price = black_scholes_price(S, K, T, r, mid, right)
        if abs(mid_price - market_price) < tol:
            return mid
        if mid_price < market_price:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-8:
            break

    mid = (lo + hi) / 2
    mid_price = black_scholes_price(S, K, T, r, mid, right)
    if abs(mid_price - market_price) < tol * 1000:
        return mid

    raise ValueError(
        f"implied_vol failed to converge for market_price={market_price:.4f}, "
        f"S={S}, K={K}, T={T}, right={right}"
    )
