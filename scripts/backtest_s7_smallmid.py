#!/usr/bin/env python3
"""POC-1 S7 revival: PEAD su universo small/mid-cap ($300M–$10B), FMP Starter.

Gate pre-registrato (piano 2026-07-04): n>=30 BEAT small/mid, media excess vs IWM
a 20d netta di 30bps >= +1.5%, hit netto > 55%. Large-cap NON si ritesta (FAIL 07-03).

Run: set -a; source .env; set +a; .venv/bin/python scripts/backtest_s7_smallmid.py
"""
from __future__ import annotations

import csv
import os
import sys
import time
from datetime import datetime, timedelta

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scripts.backtest_s7_pead as _pead_mod  # noqa: E402
from scripts.backtest_s7_pead import (  # noqa: E402
    _SURPRISE_THRESHOLD, _alpaca_bars, _forward_return, _market_caps,
)
from scripts.s7_poc_helpers import (  # noqa: E402
    MIN_ADV_USD, adv_usd, classify_cap, gate_verdict_smallmid,
)

_FMP = "https://financialmodelingprep.com/stable"
_START = os.environ.get("BT_START", "2026-01-01")
_END = os.environ.get("BT_END", "2026-05-15")
# Default 600 riproduce il run 2026-07-04; override MAX_CAP_LOOKUPS=7000 copre
# l'intero universo (~6.200 simboli, Starter 300 call/min → solo runtime).
_MAX_CAP_LOOKUPS = int(os.environ.get("MAX_CAP_LOOKUPS", "600"))
# _market_caps() has its own internal cap (_MAX_SYMBOLS_FOR_CAP=150) sized for the
# OLD free-tier quota (~250 calls/day). Starter allows 300 calls/MIN, so raise it to
# match _MAX_CAP_LOOKUPS or the small/mid sample silently truncates to 150 symbols.
_pead_mod._MAX_SYMBOLS_FOR_CAP = _MAX_CAP_LOOKUPS


def _fmp_earnings_range(key: str, start: str, end: str) -> list[dict]:
    """Calendario earnings con from/to (sbloccato da Starter), chunk 30 giorni."""
    out: dict[tuple, dict] = {}
    d0 = datetime.fromisoformat(start).date()
    d1 = datetime.fromisoformat(end).date()
    cur = d0
    while cur <= d1:
        chunk_end = min(cur + timedelta(days=30), d1)
        r = httpx.get(f"{_FMP}/earnings-calendar",
                      params={"from": cur.isoformat(), "to": chunk_end.isoformat(),
                              "apikey": key}, timeout=30.0)
        r.raise_for_status()
        for e in r.json() or []:
            if e.get("date"):
                out[(e.get("symbol"), e["date"])] = e
        print(f"  ...calendar {cur}..{chunk_end}: cum {len(out)} records")
        time.sleep(0.25)
        cur = chunk_end + timedelta(days=1)
    return list(out.values())


def main() -> None:
    key = os.environ.get("FMP_API_KEY", "")
    if not key:
        print("No FMP_API_KEY in env"); return

    print(f"# POC-1 small/mid PEAD — {_START}..{_END}\n")
    raw = _fmp_earnings_range(key, _START, _END)
    events = []
    for e in raw:
        a, est = e.get("epsActual"), e.get("epsEstimated")
        if a is None or not est:
            continue
        surprise = (a - est) / abs(est)
        if abs(surprise) < _SURPRISE_THRESHOLD:
            continue
        events.append({"symbol": e["symbol"], "date": e["date"], "surprise": surprise,
                       "dir": "BEAT" if surprise > 0 else "MISS"})
    print(f"Eventi |surprise|>={_SURPRISE_THRESHOLD}: {len(events)}")

    symbols = sorted({e["symbol"] for e in events})
    # _market_caps() (reused from backtest_s7_pead.py) returns raw USD (e.g. AAPL ->
    # 4.5e12), while classify_cap() thresholds are in MILLIONS of USD (300..10_000) —
    # convert here or every real company clears the "large" floor trivially and
    # small/mid comes back empty (found via live diagnostic 2026-07-04: 599/600 "large").
    caps = {s: v / 1_000_000.0 for s, v in _market_caps(symbols[:_MAX_CAP_LOOKUPS], key).items()}
    smallmid_syms = {s for s, c in caps.items() if classify_cap(c) == "small/mid"}
    # Dash-suffixed tickers (e.g. "ABR-PD") are preferred/rights shares, not common
    # equity — out of scope for a PEAD study. Also: _alpaca_bars() batches 100 symbols
    # per request and its try/except zeroes out the WHOLE batch on any invalid symbol,
    # so one bad preferred ticker silently loses ~100 good common-stock symbols too
    # (found via live run 2026-07-04: 3 failed batches -> only 1/464 events survived).
    non_common = {s for s in smallmid_syms if "-" in s}
    common_syms = smallmid_syms - non_common
    events = [e for e in events if e["symbol"] in common_syms]
    print(f"Eventi small/mid ($300M–$10B): {len(events)} su {len(common_syms)} simboli comuni "
          f"({len(non_common)} preferred/rights esclusi pre-fetch: ticker con '-')")

    bars = _alpaca_bars(sorted(common_syms) + ["IWM"])
    iwm = bars.get("IWM", [])

    rows, no_bars, illiquid = [], 0, 0
    for e in events:
        b = bars.get(e["symbol"]) or []
        if len(b) < 25:
            no_bars += 1
            continue
        if adv_usd(b, e["date"]) < MIN_ADV_USD:
            illiquid += 1
            continue
        fr = _forward_return(b, e["date"])
        bench = _forward_return(iwm, e["date"])
        if fr is None or bench is None:
            no_bars += 1
            continue
        rows.append({"symbol": e["symbol"], "date": e["date"], "dir": e["dir"],
                     "surprise": round(e["surprise"], 4), "ret_20d": round(fr, 4),
                     "iwm_20d": round(bench, 4), "excess_20d": round(fr - bench, 4),
                     "cap_musd": round(caps.get(e["symbol"], 0.0), 0),
                     "adv_usd": round(adv_usd(b, e["date"]), 0)})
    print(f"Con barre+liquidità: {len(rows)} (scartati: {no_bars} no-bars IEX, {illiquid} illiquidi <$5M ADV)")
    print("NB: copertura IEX bassa sui small-cap è ANCHE un proxy di non-tradabilità via Alpaca.\n")

    os.makedirs("reports/s7_poc", exist_ok=True)
    out_csv = f"reports/s7_poc/poc1_smallmid_events_{datetime.now():%Y-%m-%d}.csv"
    if rows:
        with open(out_csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
        print(f"CSV → {out_csv}\n")

    for d in ("BEAT", "MISS"):
        sel = [r["excess_20d"] for r in rows if r["dir"] == d]
        sign = 1 if d == "BEAT" else -1
        v = gate_verdict_smallmid([sign * x for x in sel], cost_bps=30)
        print(f"{d}: n={v['n']} mean_net={v['mean_net']:+.2%} hit_net={v['hit_net']:.0%} → {v['verdict']}")

    beat = [r["excess_20d"] for r in rows if r["dir"] == "BEAT"]
    verdict = gate_verdict_smallmid(beat, cost_bps=30)
    tag = "INCONCLUSIVE_DATA" if verdict["n"] < 30 else verdict["verdict"]
    print(f"\n## GATE POC-1 (BEAT long, excess IWM, netto 30bps): {tag}")


if __name__ == "__main__":
    main()
