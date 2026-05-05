"""Macro data connector — FRED API for VIX and other macro indicators."""

import httpx


def fetch_vix_from_fred(series_id: str = "VIXCLS", api_key: str = "") -> float:
    """Fetch latest VIX value from FRED.

    Uses authenticated JSON API when api_key is provided,
    falls back to public CSV endpoint otherwise.

    Example:
        >>> fetch_vix_from_fred(api_key="your-key")
        18.45

    Raises:
        httpx.HTTPStatusError: on non-2xx HTTP response
        httpx.TimeoutException: if request exceeds 10s timeout
        ValueError: if response cannot be parsed as float (empty or malformed)
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

    T10Y2Y is the 10-year minus 2-year Treasury yield spread in percentage
    points. Negative values indicate an inverted yield curve (recession signal).

    Raises:
        httpx.HTTPStatusError: on non-2xx HTTP response
        httpx.RequestError: on network failure
        ValueError: if response cannot be parsed
    """
    return fetch_vix_from_fred(series_id="T10Y2Y", api_key=api_key)


def fetch_spy_momentum_20d() -> float:
    """Fetch SPY 20-trading-day price momentum as percentage return.

    Returns:
        Momentum as float (e.g., 4.2 for +4.2%, -8.1 for -8.1%)

    Raises:
        ValueError: if fewer than 20 trading days of history available
    """
    import yfinance as yf

    ticker = yf.Ticker("SPY")
    hist = ticker.history(period="1mo")
    if len(hist) < 20:
        raise ValueError(
            f"Insufficient SPY price history: {len(hist)} days (need 20)"
        )
    close = hist["Close"]
    return float((close.iloc[-1] / close.iloc[-20] - 1) * 100)
