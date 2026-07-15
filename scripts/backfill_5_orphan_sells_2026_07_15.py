#!/usr/bin/env python3
"""Backfill the 5 orphaned SELL fills lost to the B33 trade-write-loop bug
(2026-07-15 14:22 UTC cycle).

Context: the 5 SELLs (NFLX/DIS/MSFT/NVO/TM, trade ids 322/323/324/330/332)
were submitted to Alpaca and FILLED, but the DB-write loop broke at the first
SELL's record_trade_exit (single try/except + re-raise), so the exit was never
recorded. Result: positions flat on Alpaca but still OPEN in DB (DB↔Alpaca
divergence, ~$9.7K phantom open exposure, P&L not captured, pyramiding guard
blocking re-BUYs).

This script closes the divergence by replaying the exact calls that should have
run, using real Alpaca order ids recovered from the order history:

  1. record_trade_exit(trade_id=..., exit_order_id=<alpaca_id>, is_final=True)
     for each of the 5 — sets exit_order_id / exit_order_ids / exit_time /
     exit_reason (COALESCE => idempotent; safe to re-run).
  2. reconcile_trade_fills(trading_client) — the normal daily path — fills
     exit_price / gross_pnl / net_pnl / cost fields from the Alpaca fills
     (only touches rows where exit_price IS NULL).

Read-only verification before/after; no exit_price/net_pnl written by hand.
Run:  .venv/bin/python scripts/backfill_5_orphan_sells_2026_07_15.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

# Alpaca order ids recovered from order history (window 14:15-14:35 UTC 07-15),
# all status=FILLED, filled_at 14:22:07-08, qty == entry qty => full close.
ORPHANS: list[dict] = [
    {"trade_id": 323, "symbol": "DIS",  "order_id": "29039f6c-1dbd-4d15-8af3-0560768076b6",
     "exit_time": datetime(2026, 7, 15, 14, 22, 8, 379657, tzinfo=timezone.utc)},
    {"trade_id": 324, "symbol": "MSFT", "order_id": "53362366-84ed-446a-9a96-d024b0a71aea",
     "exit_time": datetime(2026, 7, 15, 14, 22, 8, 427869, tzinfo=timezone.utc)},
    {"trade_id": 322, "symbol": "NFLX", "order_id": "a8b8dfab-2253-43e6-91ca-90ec7106e933",
     "exit_time": datetime(2026, 7, 15, 14, 22, 7, 152519, tzinfo=timezone.utc)},
    {"trade_id": 330, "symbol": "NVO",  "order_id": "4d6cdcd6-0c11-47de-a524-ada0a561db82",
     "exit_time": datetime(2026, 7, 15, 14, 22, 8, 334014, tzinfo=timezone.utc)},
    {"trade_id": 332, "symbol": "TM",   "order_id": "461f0907-dff1-4e52-a508-0d2ee281153b",
     "exit_time": datetime(2026, 7, 15, 14, 22, 8, 985633, tzinfo=timezone.utc)},
]
EXIT_REASON = "portfolio_sell"


def _show(pg, label: str) -> None:
    print(f"\n=== {label} ===")
    conn = pg._get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, symbol, exit_order_id, exit_time::text,
                          exit_price, gross_pnl, net_pnl
                   FROM trades WHERE id IN (322,323,324,330,332) ORDER BY id"""
            )
            print(f"{'id':>4} {'sym':5} {'exit_order_id':36} {'exit_time':27} {'exit_price':>10} {'gross_pnl':>10} {'net_pnl':>10}")
            for tid, sym, eoid, et, ep, gp, np_ in cur.fetchall():
                print(f"{tid:>4} {sym:5} {(eoid or '·'):36} {(et or '·'):27} "
                      f"{(ep if ep is not None else '·'):>10} "
                      f"{(gp if gp is not None else '·'):>10} "
                      f"{(np_ if np_ is not None else '·'):>10}")
        conn.rollback()  # read-only
    finally:
        pass


def main() -> int:
    from src.store.pg_store import PostgreSQLStore
    from alpaca.trading.client import TradingClient

    key = os.environ["ALPACA_API_KEY"]
    sec = os.environ["ALPACA_SECRET_KEY"]
    tc = TradingClient(key, sec, paper=True)

    pg = PostgreSQLStore()
    try:
        _show(pg, "BEFORE backfill")

        # Step 1: replay record_trade_exit for each orphan (idempotent via COALESCE).
        print("\n=== Step 1: record_trade_exit (5 orphans) ===")
        for o in ORPHANS:
            tid = pg.record_trade_exit(
                symbol=o["symbol"],
                exit_order_id=o["order_id"],
                exit_time=o["exit_time"],
                exit_reason=EXIT_REASON,
                trade_id=o["trade_id"],
                is_final=True,
            )
            print(f"  trade {o['trade_id']:>3} {o['symbol']:5} -> record_trade_exit returned trade_id={tid}")

        # Step 2: reconcile exit fills (sets exit_price/gross_pnl/net_pnl/costs).
        print("\n=== Step 2: reconcile_trade_fills ===")
        updated = pg.reconcile_trade_fills(tc)
        print(f"  reconcile_trade_fills updated {updated} row(s) total (entry+exit)")

        _show(pg, "AFTER backfill")

        # Final assertion: all 5 closed.
        conn = pg._get_connection()
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, symbol, exit_order_id IS NOT NULL AS has_oid,
                          exit_time IS NOT NULL AS has_time,
                          exit_price IS NOT NULL AS has_price,
                          net_pnl IS NOT NULL AS has_pnl
                   FROM trades WHERE id IN (322,323,324,330,332) ORDER BY id"""
            )
            bad = [(r[0], r[1]) for r in cur.fetchall()
                   if not (r[2] and r[3] and r[4] and r[5])]
        conn.rollback()
        if bad:
            print(f"\n!!! {len(bad)} trade(s) still incomplete: {bad}")
            return 1
        print("\nOK: all 5 orphans closed (exit_order_id + exit_time + exit_price + net_pnl set).")
        return 0
    finally:
        pg.close()


if __name__ == "__main__":
    sys.exit(main())