#!/usr/bin/env python3
"""POC-2a: scarica i transcript earnings (Alpha Vantage EARNINGS_CALL_TRANSCRIPT).

I transcript FMP richiedono il piano Ultimate → si usa Alpha Vantage free tier
(25 richieste/giorno, ~5 req/min): lo script è RESUMABILE — processa finché la
quota regge, poi si ferma pulito; va rilanciato nei giorni successivi finché la
copertura è completa (~5-10 giorni di calendario per ~120 eventi).

Eventi = union di reports/s7_backtest/alpha_a5_events_2026-07-03.csv (large)
e reports/s7_poc/poc1_smallmid_events_*.csv (small/mid, se esiste).
Cache: reports/s7_poc/transcripts/{SYM}_{DATE}.json — salta gli esistenti.
Match: AV chiave i transcript per fiscal quarter (nessuna data call) → si provano
i due trimestri precedenti l'evento (reported_quarter_candidates); il worst case
è un transcript vecchio (rumore), mai informazione futura.

Run: set -a; source .env; set +a; .venv/bin/python scripts/fetch_s7_transcripts.py
"""
from __future__ import annotations

import csv
import glob
import json
import os
import sys
import time

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.s7_poc_helpers import reported_quarter_candidates  # noqa: E402

_AV = "https://www.alphavantage.co/query"
_CACHE = "reports/s7_poc/transcripts"
_MAX_TRANSCRIPTS = 120  # cost cap pre-registrato


def _load_events() -> list[dict]:
    events, seen = [], set()
    paths = ["reports/s7_backtest/alpha_a5_events_2026-07-03.csv"]
    paths += sorted(glob.glob("reports/s7_poc/poc1_smallmid_events_*.csv"))
    for p in paths:
        if not os.path.exists(p):
            continue
        with open(p) as f:
            for r in csv.DictReader(f):
                k = (r["symbol"], r["date"])
                if k not in seen:
                    seen.add(k)
                    events.append(r)
    return events


def _fetch_quarter(key: str, symbol: str, quarter: str) -> dict | None:
    """Una chiamata AV. Ritorna {"_quota": msg} se la quota giornaliera è finita."""
    r = httpx.get(_AV, params={"function": "EARNINGS_CALL_TRANSCRIPT",
                               "symbol": symbol, "quarter": quarter,
                               "apikey": key}, timeout=30.0)
    if r.status_code != 200:
        return None
    data = r.json()
    if "Note" in data or "Information" in data:
        # AV embeds the raw API key in this message ("...detected your API key
        # as <KEY>...") — redact before it can ever be printed or logged.
        msg = str(data.get("Note") or data.get("Information")).replace(key, "***")
        return {"_quota": msg}
    if data.get("transcript"):
        return data
    return None


def main() -> None:
    key = os.environ.get("ALPHAVANTAGE_API_KEY", "")
    if not key:
        print("No ALPHAVANTAGE_API_KEY in env"); return
    os.makedirs(_CACHE, exist_ok=True)

    events = _load_events()[:_MAX_TRANSCRIPTS]
    print(f"Eventi da coprire (cap {_MAX_TRANSCRIPTS}): {len(events)}")
    hits = misses = cached = 0

    for e in events:
        sym, date = e["symbol"], e["date"]
        path = f"{_CACHE}/{sym}_{date}.json"
        if os.path.exists(path):
            cached += 1
            continue
        found = None
        for q in reported_quarter_candidates(date):
            data = _fetch_quarter(key, sym, q)
            time.sleep(13)  # free tier: 5 req/min
            if data and "_quota" in data:
                print(f"\n⏸ Quota giornaliera AV esaurita: {data['_quota'][:120]}")
                print(f"Coperti finora: {hits + cached} match, {misses} miss — rilanciare domani.")
                return
            if data:
                content = "\n".join(
                    f"{s.get('speaker', '?')} ({s.get('title', '')}): {s.get('content', '')}"
                    for s in data["transcript"])
                found = {"symbol": sym, "event_date": date, "quarter": q, "content": content}
                break
        if found:
            with open(path, "w") as f:
                json.dump(found, f)
            hits += 1
        else:
            misses += 1
        if (hits + misses) % 10 == 0:
            print(f"  ...{hits + misses} processati oggi (match {hits}, miss {misses})")

    total = hits + misses + cached
    print(f"\nMatch: {hits + cached}/{total} ({(hits + cached) / max(total, 1):.0%}) — miss {misses}")
    if total and (hits + cached) / total < 0.5:
        print("⚠️ Copertura <50% → il gate POC-2 sarà INCONCLUSIVE_DATA (pre-registrato)")


if __name__ == "__main__":
    main()
