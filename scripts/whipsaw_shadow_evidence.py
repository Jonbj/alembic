#!/usr/bin/env python3
"""#61 anti-whipsaw damping — shadow evidence report (flip-decision support).

Read-only. s4_anti_whipsaw_damping_enabled ships OFF by default (#61,
2026-07-16): every weight-0 S4 SELL classified "whipsaw" (#60) is still
logged normally, but the reason text is annotated with what the damper
WOULD have done — "[anti_whipsaw_shadow: would_suppress=True/False,
streak=N/M]" — without changing execution. This script aggregates that
shadow annotation over time so the flip decision doesn't rely on anyone
remembering individual cases across sessions; the evidence lives in
Postgres, this script just reads it back.

Once the flag is flipped ON, first-occurrence whipsaws stop reaching this
code path at all (they're suppressed before a decision row is even
written) — so this script's population is inherently shadow-only and
naturally stops growing the day the flag flips, which is fine: at that
point the question becomes a live-behavior review, not a shadow one.

Net P&L per case is joined from `trades` on symbol + exit_time within a
5-minute window of the decision's tick_time (there is no direct FK from
execution_decisions to the trade it closed).

CAVEAT (#184): rows written before the #184 fix carry a "whipsaw" label
DEDUCED from the last signal's age, not observed — a weight-0 SELL whose
signal was fresher than max_signal_age_hours was tagged "whipsaw" whatever
actually zeroed the weight. Pre-fix rows start their reason with
"[whipsaw] Portfolio rebalance:"; post-fix ones with "[whipsaw] S4 signal
reached the portfolio engine fresh". See docs/exit_mechanism_labels.md.

Flip-decision tracking: issue #83.

Run inside the worker container:
    docker compose exec worker python scripts/whipsaw_shadow_evidence.py
Or locally with the live DB:
    DATABASE_URL=postgresql://trading:trading@localhost:5432/trading \
        .venv/bin/python scripts/whipsaw_shadow_evidence.py
"""
from __future__ import annotations

import os
import re

import psycopg2
import psycopg2.extras

_SHADOW_RE = re.compile(
    r"\[anti_whipsaw_shadow: would_suppress=(True|False), streak=(\d+)/(\d+)\]"
)


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
            SELECT tick_time, symbol, score AS signal_score, reason
            FROM execution_decisions
            WHERE exit_mechanism = 'whipsaw'
              AND reason LIKE '%anti_whipsaw_shadow%'
            ORDER BY tick_time
            """
        )
        rows = cur.fetchall()

        if not rows:
            print("No whipsaw shadow cases logged yet (flag off, no [whipsaw] "
                  "exits since #61 deployed 2026-07-16). Nothing to report.")
            return 0

        cases = []
        for r in rows:
            m = _SHADOW_RE.search(r["reason"])
            if not m:
                continue
            would_suppress = m.group(1) == "True"
            streak, confirm_cycles = int(m.group(2)), int(m.group(3))

            cur.execute(
                """
                SELECT net_pnl FROM trades
                WHERE symbol = %s
                  AND exit_time IS NOT NULL
                  AND ABS(EXTRACT(EPOCH FROM (exit_time - %s))) < 300
                ORDER BY ABS(EXTRACT(EPOCH FROM (exit_time - %s)))
                LIMIT 1
                """,
                (r["symbol"], r["tick_time"], r["tick_time"]),
            )
            match = cur.fetchone()
            net_pnl = match["net_pnl"] if match else None

            cases.append({
                "tick_time": r["tick_time"], "symbol": r["symbol"],
                "would_suppress": would_suppress, "streak": streak,
                "confirm_cycles": confirm_cycles, "net_pnl": net_pnl,
                # #184: pre-fix rows carry a deduced label; keep the text to count them.
                "reason": r["reason"],
            })

        n = len(cases)
        n_suppress = sum(1 for c in cases if c["would_suppress"])
        pnl_known = [c["net_pnl"] for c in cases if c["net_pnl"] is not None]
        pnl_total = sum(pnl_known) if pnl_known else None
        pnl_suppress = [c["net_pnl"] for c in cases if c["would_suppress"] and c["net_pnl"] is not None]
        pnl_suppress_total = sum(pnl_suppress) if pnl_suppress else None

        print(f"== #61 whipsaw shadow evidence: {n} case(s) since deploy (2026-07-16) ==")
        n_pre_fix = sum(
            1 for c in cases if c["reason"].startswith("[whipsaw] Portfolio rebalance:")
        )
        if n_pre_fix:
            print(
                f"   {n_pre_fix} of these carry a PRE-#184 label deduced from the signal's "
                "age, not observed — see docs/exit_mechanism_labels.md"
            )
        print()
        print(f"{'date/time (UTC)':<20} {'symbol':<8} {'would_suppress':<15} {'streak':<8} {'net_pnl':>10}")
        for c in cases:
            pnl_str = f"{c['net_pnl']:.2f}" if c["net_pnl"] is not None else "n/a"
            print(
                f"{c['tick_time'].strftime('%Y-%m-%d %H:%M'):<20} {c['symbol']:<8} "
                f"{str(c['would_suppress']):<15} {c['streak']}/{c['confirm_cycles']:<6} {pnl_str:>10}"
            )

        print()
        print(f"would_suppress=True : {n_suppress}/{n} ({100.0*n_suppress/n:.0f}%)")
        if pnl_total is not None:
            print(f"total net_pnl (all {len(pnl_known)} matched cases)      : ${pnl_total:.2f}")
        if pnl_suppress_total is not None:
            print(f"total net_pnl (would_suppress=True, matched) : ${pnl_suppress_total:.2f}"
                  " <- $ that a 1-cycle hold would have deferred (not necessarily saved: outcome unknown)")
        print(
            "\nNote: would_suppress=True does not mean the loss would have been avoided — "
            "only that the exit would have been held one more cycle. See issue #83 for the "
            "flip criteria and #61's known interaction with the always-on "
            "execution.exit_persistence_cycles hysteresis (effective delay is additive, "
            "not just confirm_cycles)."
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
