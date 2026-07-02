#!/usr/bin/env python3
"""S7 PEAD backtest — the ALPHA-A5 go/no-go gate.

Tests whether post-earnings drift is real & tradeable BEFORE promoting S7:
  - fetch historical earnings surprises (Finnhub calendar: actual vs estimate EPS),
  - classify BEAT (>= threshold) / MISS (<= -threshold),
  - measure the 20-trading-day forward return (Alpaca daily bars), entering the trading
    day AFTER the announcement (no look-ahead),
  - split by market cap (Finnhub profile2) — large vs small/mid — because PEAD may be
    competed away in large caps.

Gate (per ROADMAP_DATA_ALPHA_2026-07-02 ALPHA-A5): BEAT drift >= +1.5% and hit-rate > 55%.
If large-cap drift ~0 but small/mid works → the alpha is in a different universe.

Run inside the worker container (Finnhub key + Alpaca creds + alpaca SDK):
    docker compose exec -T worker python scripts/backtest_s7_pead.py
"""
from __future__ import annotations

import os
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import httpx

_FINNHUB = "https://finnhub.io/api/v1"
_SURPRISE_THRESHOLD = 0.05
_HOLD_TRADING_DAYS = 20
_LARGE_CAP_USD_M = 10_000  # >= $10B = large cap
_MAX_EVENTS = 600          # bound API/runtime
# Window: 20 trading days must complete before ~now, so end well before today.
_START = os.environ.get("BT_START", "2026-01-01")
_END = os.environ.get("BT_END", "2026-05-15")


def _finnhub_earnings(key: str) -> list[dict]:
    r = httpx.get(f"{_FINNHUB}/calendar/earnings",
                  params={"from": _START, "to": _END, "token": key}, timeout=30.0)
    r.raise_for_status()
    return r.json().get("earningsCalendar", []) or []


def _market_caps(symbols: list[str], key: str) -> dict[str, float]:
    caps: dict[str, float] = {}
    for i, s in enumerate(symbols):
        try:
            r = httpx.get(f"{_FINNHUB}/stock/profile2",
                          params={"symbol": s, "token": key}, timeout=15.0)
            if r.status_code == 200:
                caps[s] = float(r.json().get("marketCapitalization") or 0.0)
        except Exception:
            pass
        time.sleep(1.05)  # 60/min free-tier limit
        if (i + 1) % 50 == 0:
            print(f"  ...market caps {i + 1}/{len(symbols)}")
    return caps


def _alpaca_bars(symbols: list[str]):
    from alpaca.data.enums import DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    from src.config import config
    client = StockHistoricalDataClient(config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY)
    start = datetime.fromisoformat(_START).replace(tzinfo=timezone.utc) - timedelta(days=5)
    end = datetime.fromisoformat(_END).replace(tzinfo=timezone.utc) + timedelta(days=45)
    out: dict[str, list] = {}
    for i in range(0, len(symbols), 100):  # batch
        batch = symbols[i:i + 100]
        try:
            req = StockBarsRequest(symbol_or_symbols=batch, timeframe=TimeFrame.Day,
                                   start=start, end=end, feed=DataFeed.IEX)
            data = client.get_stock_bars(req).data
            for s in batch:
                out[s] = sorted(data.get(s, []), key=lambda b: b.timestamp)
        except Exception as exc:
            print(f"  alpaca batch {i} failed: {exc}")
        print(f"  ...bars {min(i + 100, len(symbols))}/{len(symbols)}")
    return out


def _forward_return(bars: list, event_date: str) -> float | None:
    """Enter on the close of the first trading day AFTER event_date; exit +20 sessions."""
    try:
        ed = datetime.fromisoformat(event_date).date()
    except (ValueError, TypeError):
        return None
    entry_idx = next((j for j, b in enumerate(bars) if b.timestamp.date() > ed), None)
    if entry_idx is None or entry_idx + _HOLD_TRADING_DAYS >= len(bars):
        return None
    entry = bars[entry_idx].close
    exit_ = bars[entry_idx + _HOLD_TRADING_DAYS].close
    return (exit_ / entry - 1.0) if entry else None


def main() -> None:
    from src.config import config
    key = config.FINNHUB_API_KEY
    if not key:
        print("No FINNHUB_API_KEY"); return

    print(f"# S7 PEAD backtest — earnings {_START}..{_END}, hold {_HOLD_TRADING_DAYS}d\n")
    raw = _finnhub_earnings(key)
    events = []
    for e in raw:
        a, est = e.get("epsActual"), e.get("epsEstimate")
        if a is None or not est:
            continue
        surprise = (a - est) / abs(est)
        if abs(surprise) < _SURPRISE_THRESHOLD:
            continue
        events.append({"symbol": e["symbol"], "date": e["date"],
                       "surprise": surprise, "dir": "BEAT" if surprise > 0 else "MISS"})
    events = events[:_MAX_EVENTS]
    print(f"Earnings events with |surprise|>= {_SURPRISE_THRESHOLD}: {len(events)}")

    symbols = sorted({e["symbol"] for e in events})
    print(f"Unique symbols: {len(symbols)} — fetching Alpaca bars...")
    bars = _alpaca_bars(symbols)
    print("Fetching market caps (Finnhub, throttled)...")
    caps = _market_caps(symbols, key)

    # bucket: (cap_bucket, direction) → list of forward returns
    agg: dict[tuple, list[float]] = defaultdict(list)
    used = 0
    for e in events:
        b = bars.get(e["symbol"])
        if not b:
            continue
        fr = _forward_return(b, e["date"])
        if fr is None:
            continue
        cap = caps.get(e["symbol"], 0.0)
        bucket = "large" if cap >= _LARGE_CAP_USD_M else "small/mid"
        agg[(bucket, e["dir"])].append(fr)
        agg[("ALL", e["dir"])].append(fr)
        used += 1
    print(f"Events with price data: {used}\n")

    def stats(rets: list[float], direction: str) -> str:
        if not rets:
            return "  n=0"
        mean = sum(rets) / len(rets)
        # BEAT: correct = drift up (>0). MISS: correct = drift down (<0).
        correct = sum(1 for r in rets if (r > 0) == (direction == "BEAT"))
        hit = correct / len(rets)
        return f"  n={len(rets):>4}  mean_drift={mean:+.2%}  hit_rate={hit:.0%}"

    print(f"{'bucket':10} {'dir':5} stats (drift = 20d forward return; hit = correct-direction %)")
    for bucket in ("ALL", "large", "small/mid"):
        for d in ("BEAT", "MISS"):
            print(f"{bucket:10} {d:5}{stats(agg[(bucket, d)], d)}")

    # --- GATE verdict (BEAT long, the classic PEAD) ---
    print("\n## ALPHA-A5 GATE (BEAT long): drift >= +1.5% AND hit-rate > 55%")
    for bucket in ("ALL", "large", "small/mid"):
        rets = agg[(bucket, "BEAT")]
        if not rets:
            print(f"  {bucket:10}: n=0 — inconclusive"); continue
        mean = sum(rets) / len(rets)
        hit = sum(1 for r in rets if r > 0) / len(rets)
        verdict = "PASS" if (mean >= 0.015 and hit > 0.55 and len(rets) >= 30) else "FAIL"
        print(f"  {bucket:10}: drift={mean:+.2%} hit={hit:.0%} n={len(rets)} → {verdict}")


if __name__ == "__main__":
    main()
