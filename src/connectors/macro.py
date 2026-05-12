"""Macro data connector — FRED API and yfinance for regime detection inputs.

This module provides three functions consumed by src/workers/regime.py to build
the MacroSnapshot fed into the LLM regime classification prompt:

    fetch_vix_from_fred()    → VIX (CBOE Volatility Index, daily FRED series VIXCLS)
    fetch_yield_curve()      → T10Y2Y spread in % (10Y − 2Y Treasury, inverted = recession)
    fetch_spy_momentum_20d() → SPY 20-trading-day price return in %

Authentication strategy for FRED:
    - With FRED_API_KEY (env var): uses authenticated JSON endpoint (preferred in production,
      higher rate limits, guaranteed JSON structure)
    - Without key: falls back to public CSV endpoint (sufficient for daily VIX, no key required)

VIX caching:
    The performance worker (check_and_apply_weights) also calls fetch_vix_from_fred()
    but wraps it with a Redis 1-hour cache via RedisStore.set_vix_cached() to avoid
    hammering FRED on every weight check cycle.

Validation:
    All three functions raise ValueError on empty or malformed responses. The
    detect_regime() task validates returned values against reasonable ranges
    (VIX ∈ [5, 100], T10Y2Y ∈ [-5%, +5%], SPY ∈ [-50%, +50%]) before using them.
"""

import httpx


def fetch_vix_from_fred(series_id: str = "VIXCLS", api_key: str = "") -> float:
    """Fetch latest daily observation for a FRED series (default: VIXCLS).

    Used for both VIX (series_id="VIXCLS") and yield curve (series_id="T10Y2Y").
    The same function handles both because FRED uses the same response format.

    Authentication:
        With api_key → JSON API: sorted desc, limit 1 → observations[0]["value"]
        Without api_key → CSV fallback: last line of fredgraph.csv → parts[1]

    Args:
        series_id: FRED series ID (default "VIXCLS" for VIX)
        api_key: FRED API key from FRED_API_KEY env var (empty string = no key)

    Returns:
        Latest observation as float

    Raises:
        httpx.HTTPStatusError: on non-2xx HTTP response
        httpx.TimeoutException: if request exceeds 10s timeout
        ValueError: if response is empty or cannot be parsed as float
    """
    if api_key:
        url = "https://api.stlouisfed.org/fred/series/observations"
        params = {
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "limit": 1,
            "sort_order": "desc",
        }
        resp = httpx.get(url, params=params, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        observations = data.get("observations", [])
        if not observations:
            raise ValueError("FRED returned no observations")
        return float(observations[0]["value"])
    else:
        # Public CSV endpoint — no rate limiting but slower to parse
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        resp = httpx.get(url, timeout=10.0)
        resp.raise_for_status()
        lines = resp.text.strip().split("\n")
        if len(lines) < 2:
            raise ValueError(f"CSV response has insufficient lines: {len(lines)}")
        parts = lines[-1].split(",")
        if len(parts) < 2:
            raise ValueError(f"CSV last line malformed: {lines[-1]}")
        return float(parts[1])


def fetch_yield_curve(api_key: str = "") -> float:
    """Fetch T10Y2Y yield curve spread from FRED.

    T10Y2Y = 10-year Treasury yield minus 2-year Treasury yield, in percentage
    points. A negative value (inverted yield curve) is historically a leading
    indicator of recession and a bear market signal in the LLM regime prompt.

    Delegates to fetch_vix_from_fred(series_id="T10Y2Y") — same FRED format.

    Args:
        api_key: FRED API key (empty = public CSV fallback)

    Returns:
        T10Y2Y spread as float, e.g. -0.8 for an inverted curve

    Raises:
        httpx.HTTPStatusError: on non-2xx HTTP response
        httpx.RequestError: on network failure
        ValueError: if response cannot be parsed
    """
    return fetch_vix_from_fred(series_id="T10Y2Y", api_key=api_key)


def fetch_spy_momentum_20d() -> float:
    """Fetch SPY 20-trading-day price momentum as a percentage return.

    20 trading days ≈ 1 calendar month. Used as a trend signal in the regime
    prompt: strong negative momentum (< -8%) is a bear market indicator.

    Uses yfinance with period="2mo" to ensure ≥ 20 trading days are available
    even in short months or after market holidays.

    Returns:
        Momentum in %, e.g. 4.2 for +4.2%, -8.1 for -8.1%

    Raises:
        ValueError: if fewer than 20 trading days of history are available
            (e.g. SPY suspended or yfinance data gap)
    """
    import yfinance as yf

    ticker = yf.Ticker("SPY")
    hist = ticker.history(period="2mo")  # 2mo guarantees ≥ 20 trading days
    if len(hist) < 20:
        raise ValueError(
            f"Insufficient SPY price history: {len(hist)} days (need 20)"
        )
    close = hist["Close"]
    return float((close.iloc[-1] / close.iloc[-20] - 1) * 100)
