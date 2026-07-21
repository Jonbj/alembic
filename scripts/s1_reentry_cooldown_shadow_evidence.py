#!/usr/bin/env python3
"""#71 S1 re-entry cooldown — shadow evidence report (flip-decision support).

Read-only. s1_reentry_cooldown_enabled ships OFF by default (#71,
2026-07-21): every weight-0 S1 SELL is tagged exit_mechanism='s1_weight_drop'
(#72) and starts a Redis cooldown key (s1_reentry_cooldown:{symbol}, default
30 min) regardless of the flag — but the BUY-side check in
_submit_portfolio_orders is skipped entirely while the flag is off, so
(unlike #61's whipsaw damping) there is no inline "[would_suppress]"
annotation written to the decision reason text.

This script reconstructs the same evidence after the fact: for every
s1_weight_drop exit, it looks for a subsequent S1-only BUY (reason LIKE
'S1 momentum%' — S4/S2 involvement takes a different reason-text prefix,
see _resolve_buy_origin_strategy in portfolio_scheduler.py) on the same
symbol within the configured cooldown window. A match means "the cooldown,
if enabled, would have blocked this BUY".

Net P&L per case is joined from `trades` on symbol + exit_time within a
5-minute window of the SELL decision's tick_time (there is no direct FK
from execution_decisions to the trade it closed) — same convention as
scripts/whipsaw_shadow_evidence.py (#83).

Caveat: exit_mechanism='s1_weight_drop' is a new tag (#72, deployed same
day as #71, 2026-07-21) — historical incidents that motivated the fix
(SBUX/GE/XLF, 2026-07-17) predate the tag and won't appear here. This
script's population only starts accumulating from deploy day forward.

Flip-decision tracking: issue #85.

Run inside the worker container:
    docker compose exec worker python scripts/s1_reentry_cooldown_shadow_evidence.py
Or locally with the live DB:
    DATABASE_URL=postgresql://trading:trading@localhost:5432/trading \
        .venv/bin/python scripts/s1_reentry_cooldown_shadow_evidence.py
"""
from __future__ import annotations

import os

import psycopg2
import psycopg2.extras

_COOLDOWN_MINUTES_DEFAULT = 30


def _conn():
    url = os.environ.get(
        "DATABASE_URL", "postgresql://trading:trading@postgres:5432/trading"
    )
    return psycopg2.connect(url)


def main() -> int:
    conn = _conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, tick_time, symbol, score AS signal_score, reason
            FROM execution_decisions
            WHERE exit_mechanism = 's1_weight_drop'
            ORDER BY tick_time
            """
        )
        drops = cur.fetchall()

        if not drops:
            print("No s1_weight_drop exits logged yet (#72 tag deployed "
                  "2026-07-21, same day as #71). Nothing to report.")
            return 0

        cases = []
        for d in drops:
            cur.execute(
                """
                SELECT tick_time, id
                FROM execution_decisions
                WHERE symbol = %s
                  AND decision = 'BUY'
                  AND reason LIKE 'S1 momentum%%'
                  AND tick_time > %s
                  AND tick_time <= %s + (%s || ' minutes')::interval
                ORDER BY tick_time
                LIMIT 1
                """,
                (d["symbol"], d["tick_time"], d["tick_time"], _COOLDOWN_MINUTES_DEFAULT),
            )
            rebuy = cur.fetchone()
            would_block = rebuy is not None

            cur.execute(
                """
                SELECT net_pnl FROM trades
                WHERE symbol = %s
                  AND exit_time IS NOT NULL
                  AND ABS(EXTRACT(EPOCH FROM (exit_time - %s))) < 300
                ORDER BY ABS(EXTRACT(EPOCH FROM (exit_time - %s)))
                LIMIT 1
                """,
                (d["symbol"], d["tick_time"], d["tick_time"]),
            )
            match = cur.fetchone()
            net_pnl = match["net_pnl"] if match else None

            cases.append({
                "tick_time": d["tick_time"], "symbol": d["symbol"],
                "would_block": would_block,
                "rebuy_time": rebuy["tick_time"] if rebuy else None,
                "net_pnl": net_pnl,
            })

        n = len(cases)
        n_block = sum(1 for c in cases if c["would_block"])
        pnl_known = [c["net_pnl"] for c in cases if c["net_pnl"] is not None]
        pnl_total = sum(pnl_known) if pnl_known else None

        print(f"== #71 S1 re-entry cooldown shadow evidence: {n} s1_weight_drop exit(s) "
              f"since #72 deploy (2026-07-21) ==\n")
        print(f"{'date/time (UTC)':<20} {'symbol':<8} {'would_block':<13} {'rebuy_time':<20} {'net_pnl':>10}")
        for c in cases:
            pnl_str = f"{c['net_pnl']:.2f}" if c["net_pnl"] is not None else "n/a"
            rebuy_str = c["rebuy_time"].strftime("%Y-%m-%d %H:%M") if c["rebuy_time"] else "-"
            print(
                f"{c['tick_time'].strftime('%Y-%m-%d %H:%M'):<20} {c['symbol']:<8} "
                f"{str(c['would_block']):<13} {rebuy_str:<20} {pnl_str:>10}"
            )

        print()
        print(f"would_block=True : {n_block}/{n} ({100.0*n_block/n:.0f}%)")
        if pnl_total is not None:
            print(f"total net_pnl (all {len(pnl_known)} matched exit trades) : ${pnl_total:.2f}")
        print(
            "\nNote: would_block=True means an S1-only BUY on the same symbol occurred "
            "within the cooldown window after the weight-0 exit — i.e. the cooldown, if "
            "enabled, would have prevented that specific re-buy. It does not by itself mean "
            "the re-buy was unprofitable (check net_pnl of the re-buy trade separately). "
            "See issue #85 for the flip criteria."
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
