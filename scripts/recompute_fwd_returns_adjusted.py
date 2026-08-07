#!/usr/bin/env python3
"""One-shot recompute of sentiment_signals forward_return_{,3d,5d} from ADJUSTED bars.

Overwrites the raw-computed values (issue #192) with adjustment=ALL close-to-close
returns, replicating run_forward_return_worker logic (src/workers/performance.py
~1650-1684): signal_date = generated_at.date() (+1d if hour>=21 UTC), T0 = first
trading day >= signal_date, fwd[n] = close-to-close over n trading days, n in {1,3,5}.

Direct UPDATE (no COALESCE) so horizons that can't be recomputed become NULL
(pending) instead of preserving the old raw value — this both clears contamination
and lets the worker retry them once bars mature.

BACKUP FIRST: backups/sentiment_signals_fwd_raw_backup_<date>.csv
DRY_RUN=1 prints samples + counts without committing.

Run inside the worker container:
    DRY_RUN=1 docker compose exec -T -e DRY_RUN=1 worker python - < scripts/recompute_fwd_returns_adjusted.py
    docker compose exec -T worker python - < scripts/recompute_fwd_returns_adjusted.py
"""
from __future__ import annotations

import os
import sys
import time
from collections import defaultdict
from datetime import timedelta, timezone

import psycopg2

HORIZONS = (1, 3, 5)
DRY_RUN = os.environ.get("DRY_RUN", "") == "1"


def _conn():
    return psycopg2.connect(os.environ.get("DATABASE_URL", "postgresql://trading:trading@postgres:5432/trading"))


def _client():
    from alpaca.data.historical import StockHistoricalDataClient
    from src.config import config
    return StockHistoricalDataClient(config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY)


def _fetch_adj(client, symbols, start, end):
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.data.enums import DataFeed, Adjustment

    out: dict[str, dict] = {}
    for i in range(0, len(symbols), 50):
        batch = symbols[i:i + 50]
        req = StockBarsRequest(
            symbol_or_symbols=batch, timeframe=TimeFrame.Day,
            start=start - timedelta(days=2), end=end + timedelta(days=12),
            feed=DataFeed.IEX, adjustment=Adjustment.ALL,
        )
        df = client.get_stock_bars(req).df
        if hasattr(df.index, "levels"):
            for s in batch:
                if s in df.index.get_level_values(0):
                    sub = df.loc[s].sort_index()
                    out[s] = {idx.date(): float(row["close"]) for idx, row in sub.iterrows()}
        time.sleep(0.05)
    return out


def recompute(cbd, generated_at):
    """Replicate worker entry/exit logic. Returns {1:,3:,5:} (None per horizon if
    unreachable) or None if no T0 bar at all."""
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    sd = generated_at.date()
    if generated_at.hour >= 21:
        sd += timedelta(days=1)
    td = sorted(d for d in cbd if d >= sd)
    if not td:
        return None
    c0 = cbd[td[0]]
    if c0 == 0:
        return None
    return {n: ((cbd[td[n]] - c0) / c0 if len(td) > n else None) for n in HORIZONS}


def main():
    client = _client()
    conn = _conn()
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, symbol, generated_at, forward_return, forward_return_3d, forward_return_5d
               FROM sentiment_signals
               WHERE forward_return IS NOT NULL OR forward_return_3d IS NOT NULL
                  OR forward_return_5d IS NOT NULL
               ORDER BY symbol, generated_at"""
        )
        rows = cur.fetchall()
    print(f"[{'DRY-RUN' if DRY_RUN else 'LIVE'}] Rows to recompute: {len(rows)}", flush=True)
    if not rows:
        print("Nothing to do.", flush=True)
        return

    by_sym: dict[str, list] = defaultdict(list)
    for r in rows:
        by_sym[r[1]].append(r)
    symbols = sorted(by_sym)
    all_ts = [r[2] for r in rows]
    start, end = min(all_ts), max(all_ts)
    print(f"Fetching ADJUSTED bars for {len(symbols)} symbols over {start.date()}..{end.date()}", flush=True)
    cbd = _fetch_adj(client, symbols, start, end)
    print(f"  got bars for {len(cbd)}/{len(symbols)} symbols", flush=True)

    updates = []
    n_full = n_partial = n_nodata = 0
    samples = []
    for sym, sigs in by_sym.items():
        c = cbd.get(sym)
        for r in sigs:
            rid, _, gen, old1, old3, old5 = r
            rec = recompute(c or {}, gen)
            if rec is None:
                # No T0 bar: NULL all three (clears contaminated raw, makes pending).
                updates.append((None, None, None, rid))
                n_nodata += 1
                continue
            new1, new3, new5 = rec[1], rec[3], rec[5]
            updates.append((new1, new3, new5, rid))
            if new1 is not None and new3 is not None and new5 is not None:
                n_full += 1
            else:
                n_partial += 1
            if len(samples) < 8 and old1 is not None and new1 is not None and abs(old1 - new1) > 0.001:
                samples.append((sym, gen, old1, new1, old5, new5))

    print(f"Computed: {len(updates)} updates | full={n_full} partial={n_partial} no_data(NULL)={n_nodata}", flush=True)
    print("Sample diffs (|old1d-new1d|>10bp):", flush=True)
    for sym, gen, old1, new1, old5, new5 in samples:
        print(f"  {sym:6} @ {gen:%Y-%m-%d}: 1d {old1*100:+8.3f}% -> {new1*100:+8.3f}%   "
              f"5d {('' if old5 is None else format(old5*100,'+8.3f'))}% -> {('' if new5 is None else format(new5*100,'+8.3f'))}%", flush=True)

    if DRY_RUN:
        print("[DRY-RUN] Not committing.", flush=True)
        return

    with conn.cursor() as cur:
        cur.executemany(
            "UPDATE sentiment_signals SET forward_return=%s, forward_return_3d=%s, forward_return_5d=%s WHERE id=%s",
            updates,
        )
        conn.commit()
    print(f"DONE: updated {len(updates)} rows with adjusted forward returns.", flush=True)
    conn.close()


if __name__ == "__main__":
    main()