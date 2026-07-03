#!/usr/bin/env python3
"""S7 PEAD — distribution analysis of the ALPHA-A5 event set (decision support).

The FMP gate run gave: BEAT drift +1.96% (PASS) but hit-rate 51% (FAIL). Before the
PO decides "expand universe vs shelve S7", this answers: is the +1.96% a broad edge
with noisy direction, or a few large winners dragging the mean ("coin flip + lottery
tickets")? And is it alpha at all, or just Jan-May market beta?

Reuses the harness fetchers (scripts/backtest_s7_pead.py). Outputs:
  - per-event CSV (reports/s7_backtest/alpha_a5_events_<date>.csv) for audit
  - distribution stats (mean/median/trimmed/quartiles/skew) for BEAT and MISS
  - SPY-excess versions of the same (same entry day, same 20-session window)
  - concentration: mean without top-N contributors
  - monotonicity by surprise-magnitude bucket, stability by month, split by cap

Run from the host:
    set -a; source .env; set +a
    .venv/bin/python scripts/analyze_s7_events.py
"""
from __future__ import annotations

import csv
import os
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.backtest_s7_pead import (  # noqa: E402
    _LARGE_CAP_USD_M,
    _MAX_EVENTS,
    _SURPRISE_THRESHOLD,
    _END,
    _START,
    _alpaca_bars,
    _fmp_earnings_paginated,
    _forward_return,
    _market_caps,
)


def _dist(rets: list[float]) -> dict:
    if not rets:
        return {}
    s = sorted(rets)
    n = len(s)
    trim = max(1, n // 10)
    trimmed = s[trim:-trim] if n > 2 * trim else s
    mean = st.mean(s)
    return {
        "n": n,
        "mean": mean,
        "median": st.median(s),
        "trimmed_mean_10": st.mean(trimmed),
        "std": st.stdev(s) if n > 1 else 0.0,
        "q1": s[n // 4],
        "q3": s[(3 * n) // 4],
        "min": s[0],
        "max": s[-1],
        "pct_pos": sum(1 for r in s if r > 0) / n,
        "skew_proxy": (mean - st.median(s)) / (st.stdev(s) if n > 1 and st.stdev(s) else 1),
    }


def _print_dist(label: str, d: dict) -> None:
    if not d:
        print(f"{label:28} n=0")
        return
    print(f"{label:28} n={d['n']:>3}  mean={d['mean']:+.2%}  median={d['median']:+.2%}  "
          f"trim10={d['trimmed_mean_10']:+.2%}  std={d['std']:.2%}  "
          f"q1={d['q1']:+.2%}  q3={d['q3']:+.2%}  min={d['min']:+.2%}  max={d['max']:+.2%}  "
          f">0: {d['pct_pos']:.0%}")


def main() -> None:
    key = os.environ.get("FMP_API_KEY", "")
    if not key:
        print("No FMP_API_KEY in env"); return

    print(f"# S7 PEAD event-distribution analysis — {_START}..{_END}\n")
    raw = _fmp_earnings_paginated(key, _START, _END)
    events = []
    for e in raw:
        a, est = e.get("epsActual"), e.get("epsEstimated")
        if a is None or not est:
            continue
        surprise = (a - est) / abs(est)
        if abs(surprise) < _SURPRISE_THRESHOLD:
            continue
        events.append({"symbol": e["symbol"], "date": e["date"],
                       "surprise": surprise, "dir": "BEAT" if surprise > 0 else "MISS"})
    events = events[:_MAX_EVENTS]
    symbols = sorted({e["symbol"] for e in events})
    print(f"Events |surprise|>={_SURPRISE_THRESHOLD}: {len(events)} on {len(symbols)} symbols")

    bars = _alpaca_bars(symbols + ["SPY"])
    caps = _market_caps(symbols, key)
    spy_bars = bars.get("SPY", [])

    rows = []
    for e in events:
        b = bars.get(e["symbol"])
        if not b:
            continue
        fr = _forward_return(b, e["date"])
        if fr is None:
            continue
        spy_fr = _forward_return(spy_bars, e["date"]) if spy_bars else None
        cap = caps.get(e["symbol"], 0.0)
        rows.append({
            "symbol": e["symbol"], "date": e["date"], "dir": e["dir"],
            "surprise": round(e["surprise"], 4), "ret_20d": round(fr, 4),
            "spy_20d": round(spy_fr, 4) if spy_fr is not None else "",
            "excess_20d": round(fr - spy_fr, 4) if spy_fr is not None else "",
            "cap_musd": round(cap, 0),
            "cap_bucket": ("large" if cap >= _LARGE_CAP_USD_M else
                           "small/mid" if cap > 0 else "unknown"),
            "month": e["date"][:7],
        })
    print(f"Events with price data: {len(rows)}\n")

    out_csv = os.path.join("reports", "s7_backtest",
                           f"alpha_a5_events_{datetime.now():%Y-%m-%d}.csv")
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"Per-event CSV → {out_csv}\n")

    beats = [r for r in rows if r["dir"] == "BEAT"]
    misses = [r for r in rows if r["dir"] == "MISS"]

    print("## Distribuzione ritorni 20d (raw)")
    _print_dist("BEAT raw", _dist([r["ret_20d"] for r in beats]))
    _print_dist("MISS raw", _dist([r["ret_20d"] for r in misses]))

    beats_x = [r for r in beats if r["excess_20d"] != ""]
    misses_x = [r for r in misses if r["excess_20d"] != ""]
    print("\n## Distribuzione ritorni 20d (excess vs SPY, stessa finestra)")
    _print_dist("BEAT excess", _dist([r["excess_20d"] for r in beats_x]))
    _print_dist("MISS excess", _dist([r["excess_20d"] for r in misses_x]))

    print("\n## Concentrazione (BEAT raw): la media regge senza i top winner?")
    s = sorted((r["ret_20d"] for r in beats), reverse=True)
    for k in (1, 3, 5):
        if len(s) > k:
            print(f"  mean senza top-{k}: {st.mean(s[k:]):+.2%}   (top-{k}: {['%+.1f%%' % (x*100) for x in s[:k]]})")

    print("\n## Monotonicità per magnitudine surprise (BEAT, excess vs SPY)")
    buckets = [("5-15%", 0.05, 0.15), ("15-50%", 0.15, 0.50), (">50%", 0.50, 99.0)]
    for label, lo, hi in buckets:
        sel = [r["excess_20d"] for r in beats_x if lo <= r["surprise"] < hi]
        d = _dist(sel)
        if d:
            print(f"  surprise {label:7}: n={d['n']:>3}  mean={d['mean']:+.2%}  median={d['median']:+.2%}  >0: {d['pct_pos']:.0%}")
        else:
            print(f"  surprise {label:7}: n=0")

    print("\n## Stabilità per mese (BEAT, excess vs SPY)")
    by_month: dict[str, list[float]] = defaultdict(list)
    for r in beats_x:
        by_month[r["month"]].append(r["excess_20d"])
    for m in sorted(by_month):
        d = _dist(by_month[m])
        print(f"  {m}: n={d['n']:>3}  mean={d['mean']:+.2%}  median={d['median']:+.2%}  >0: {d['pct_pos']:.0%}")

    print("\n## Split per market cap (BEAT, excess vs SPY)")
    by_cap: dict[str, list[float]] = defaultdict(list)
    for r in beats_x:
        by_cap[r["cap_bucket"]].append(r["excess_20d"])
    for cb in ("large", "small/mid", "unknown"):
        d = _dist(by_cap.get(cb, []))
        _print_dist(f"  {cb}", d)


if __name__ == "__main__":
    main()
