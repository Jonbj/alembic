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
