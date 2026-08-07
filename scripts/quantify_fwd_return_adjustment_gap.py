#!/usr/bin/env python3
"""Quantify raw-vs-adjusted forward-return contamination in sentiment_signals.

Read-only diagnostic. Replicates run_forward_return_worker (src/workers/performance.py)
exactly but with adjustment="all", diffs per-signal against the stored (raw) forward
return, and reports:
  - contamination distribution per horizon (1d/3d/5d)
  - IC (Pearson score~fwd) on stored-raw vs recomputed-adjusted
  - worst-case symbols/dates + a raw-validation pass on the worst cases

Contamination = stored_raw - adjusted. For a split/dividend falling inside the
hold window, raw bars carry a spurious drop that adjusted bars remove, so
contamination is negative (raw understates the true return).

Run inside the worker container (Alpaca creds + DB):
    docker compose exec worker python scripts/quantify_fwd_return_adjustment_gap.py
"""
from __future__ import annotations

import math
import os
import sys
import time
from collections import defaultdict
from datetime import timedelta, timezone

import psycopg2
import psycopg2.extras


HORIZONS = (1, 3, 5)
COL_FOR_N = {1: "forward_return", 3: "forward_return_3d", 5: "forward_return_5d"}
CONTAM_BUCKETS = (0.001, 0.02, 0.10)  # 10bp / 200bp / 10%


def _conn():
    url = os.environ.get("DATABASE_URL", "postgresql://trading:trading@postgres:5432/trading")
    return psycopg2.connect(url)


def _client():
    from alpaca.data.historical import StockHistoricalDataClient
    from src.config import config
    return StockHistoricalDataClient(config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY)


def _fetch_daily(client, symbols, start, end, adjustment):
    """Return {symbol: {date: close}} for the given symbols over [start,end]."""
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.data.enums import DataFeed

    out: dict[str, dict] = {}
    chunk = 50
    for i in range(0, len(symbols), chunk):
        batch = symbols[i:i + chunk]
        req = StockBarsRequest(
            symbol_or_symbols=batch,
            timeframe=TimeFrame.Day,
            start=start - timedelta(days=2),
            end=end + timedelta(days=12),
            feed=DataFeed.IEX,
            adjustment=adjustment,
        )
        df = client.get_stock_bars(req).df
        if df.empty:
            continue
        if hasattr(df.index, "levels"):  # MultiIndex (symbol, timestamp)
            for sym in batch:
                if sym in df.index.get_level_values(0):
                    sub = df.loc[sym].sort_index()
                    out[sym] = {idx.date(): float(row["close"]) for idx, row in sub.iterrows()}
        else:
            df = df.sort_index()
            # single-symbol fallback
            sym = batch[0]
            out[sym] = {idx.date(): float(row["close"]) for idx, row in df.iterrows()}
        time.sleep(0.05)
    return out


def recompute(close_by_date, generated_at):
    """Replicate worker entry/exit logic. Returns {1:,3:,5:} or None."""
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    signal_date = generated_at.date()
    if generated_at.hour >= 21:  # after 4pm ET close -> next session
        signal_date += timedelta(days=1)
    trading_dates = sorted(d for d in close_by_date if d >= signal_date)
    if not trading_dates:
        return None
    c0 = close_by_date[trading_dates[0]]
    if c0 == 0:
        return None
    out = {}
    for n in HORIZONS:
        out[n] = (close_by_date[trading_dates[n]] - c0) / c0 if len(trading_dates) > n else None
    return out


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    vy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if vx == 0 or vy == 0:
        return None
    return cov / (vx * vy)


def main():
    client = _client()
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT symbol, generated_at, score, confidence,
                          forward_return, forward_return_3d, forward_return_5d
                   FROM sentiment_signals
                   WHERE forward_return IS NOT NULL
                   ORDER BY symbol, generated_at"""
            )
            rows = cur.fetchall()
    print(f"Loaded {len(rows)} signals with forward_return", flush=True)

    by_symbol: dict[str, list] = defaultdict(list)
    for r in rows:
        by_symbol[r["symbol"]].append(r)

    symbols = sorted(by_symbol)
    all_ts = [r["generated_at"] for r in rows]
    start, end = min(all_ts), max(all_ts)
    print(f"Fetching ADJUSTED daily bars for {len(symbols)} symbols over {start.date()}..{end.date()}", flush=True)
    adj_close = _fetch_daily(client, symbols, start, end, adjustment="all")
    print(f"  got bars for {len(adj_close)}/{len(symbols)} symbols", flush=True)

    deltas: dict[int, list] = {n: [] for n in HORIZONS}
    score_adj: dict[int, list] = {n: [] for n in HORIZONS}
    score_stored: dict[int, list] = {n: [] for n in HORIZONS}
    worst: dict[int, list] = {n: [] for n in HORIZONS}
    n_recomputed = 0

    for sym, sigs in by_symbol.items():
        cbd = adj_close.get(sym)
        if not cbd:
            continue
        for s in sigs:
            rec = recompute(cbd, s["generated_at"])
            if rec is None:
                continue
            n_recomputed += 1
            for n in HORIZONS:
                adj = rec[n]
                stored = s[COL_FOR_N[n]]
                if adj is None or stored is None:
                    continue
                d = stored - adj
                deltas[n].append(d)
                score_adj[n].append((s["score"], adj))
                score_stored[n].append((s["score"], stored))
                if abs(d) > 1e-5:
                    worst[n].append((abs(d), d, sym, s["generated_at"], stored, adj))

    print(f"\nSignals recomputed (adjusted): {n_recomputed}", flush=True)
    summary = {}
    for n in HORIZONS:
        ds = deltas[n]
        if not ds:
            print(f"\n=== h={n}d: no pairs ===")
            continue
        n_total = len(ds)
        buckets = {b: sum(1 for d in ds if abs(d) > b) for b in CONTAM_BUCKETS}
        mean_d = sum(ds) / n_total
        ic_raw = pearson([x for x, _ in score_stored[n]], [y for _, y in score_stored[n]])
        ic_adj = pearson([x for x, _ in score_adj[n]], [y for _, y in score_adj[n]])
        worst[n].sort(reverse=True)
        summary[n] = dict(n=n_total, buckets=buckets, mean=mean_d, ic_raw=ic_raw, ic_adj=ic_adj)
        print(f"\n=== h={n}d  (N={n_total}) ===")
        print(f"  |contam|>0.1% (div-class):  {buckets[0.001]:>5}  ({100*buckets[0.001]/n_total:5.2f}%)")
        print(f"  |contam|>2%   (split-class):{buckets[0.02]:>5}  ({100*buckets[0.02]/n_total:6.3f}%)")
        print(f"  |contam|>10%  (extreme):    {buckets[0.10]:>5}  ({100*buckets[0.10]/n_total:7.4f}%)")
        print(f"  mean contam = {mean_d*100:+.4f}%   (negative => raw understates return)")
        if ic_raw is not None and ic_adj is not None:
            print(f"  IC(Pearson score~fwd)  raw={ic_raw:+.4f}  adj={ic_adj:+.4f}  delta={ic_adj-ic_raw:+.4f}")
        print(f"  top-5 worst:")
        for ad, d, sym, ts, st, aj in worst[n][:5]:
            print(f"    {sym:6} @ {ts:%Y-%m-%d}: stored={st*100:+8.3f}% adj={aj*100:+8.3f}% contam={d*100:+8.3f}%")

    # --- Raw-validation pass on the worst 1d cases: confirm stored ≈ fresh-raw ---
    worst_1d = sorted(worst[1], reverse=True)[:8]
    if worst_1d:
        val_syms = sorted({w[2] for w in worst_1d})
        print(f"\n=== RAW validation on {len(val_syms)} worst-1d symbols ({', '.join(val_syms)}) ===", flush=True)
        raw_close = _fetch_daily(client, val_syms, start, end, adjustment="raw")
        for ad, d, sym, ts, st, aj in worst_1d:
            cbd = raw_close.get(sym)
            if not cbd:
                continue
            rec = recompute(cbd, ts)
            raw = rec[1] if rec else None
            if raw is not None:
                print(f"  {sym:6} @ {ts:%Y-%m-%d}: stored={st*100:+8.3f}% fresh_raw={raw*100:+8.3f}% adj={aj*100:+8.3f}%  "
                      f"stored-raw={ (st-raw)*100:+.4f}%  raw-adj={ (raw-aj)*100:+.4f}%")


if __name__ == "__main__":
    main()