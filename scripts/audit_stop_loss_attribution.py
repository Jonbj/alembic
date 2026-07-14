#!/usr/bin/env python3
"""Stop-loss exit attribution audit (passo-zero, F9a redesign).

Read-only / idempotent. Quantifies how reliably a closed trade's exit_reason is
attributed, so that any stop-out measurement rests on trusted data. Aligns with
the project's "measure before enforce" discipline (QX-01).

Context (verified in code, see docs/stop_loss_review_prompt.md):
  - The portfolio path writes exit_reason at SUBMIT time, not at reconcile time.
    The synthetic stop-loss SELL (portfolio_scheduler.py:1560) appends
    ``reason="stop_loss"`` to ``submitted_orders``; ``record_trade_exit``
    (pg_store.py:899) then sets ``trades.exit_reason`` keyed by
    ``WHERE symbol=%s AND exit_time IS NULL``.
  - ``reconcile_trade_fills`` (pg_store.py:1168) does NOT touch exit_reason; it
    only fills exit_price / gross_pnl / net_pnl / costs. So attribution is
    explicit at submit, and exit_price lags until the daily reconcile runs.

What this script measures:
  M1  exit_reason distribution over closed trades.
  M2  attribution coverage: closed trades missing exit_reason / exit_order_id.
  M3  stop-loss subset: count, reconciled-price coverage, P&L coverage.
  M4  execution_decisions coverage (Gap A): fraction of closed trades whose
      exit_order_id is back-filled onto an execution_decisions SELL row. The
      synthetic stop-loss never writes an execution_decision, so its exits are
      absent from the Decision Log — an attribution gap.
  M5  orphan exit orders: trade.exit_order_id with no matching decision row.
  M6  double-close: one exit_order_id on >1 trade (symbol-keyed match fragility).
  M7  pending P&L (Gap C): exit_reason set but exit_price / net_pnl still NULL
      (awaiting daily reconcile) — matters for any 15-min replay.
  M8  unreconciled entries: entry_price NULL on non-open trades.
  M9  S4 exit freshness: for sentiment-driven exits, signal age at exit time
      (surfaces the SPCX-class anomaly: exit citing a >max_age signal).

Gate (the "≥99% attribution" prerequisite before any stop-out measurement):
  closed trades with BOTH a non-empty exit_reason AND a non-null exit_order_id
  >= 99% of all closed trades. The script exits non-zero if the gate fails.

Run inside the worker container:
    docker compose exec worker python scripts/audit_stop_loss_attribution.py
Or locally with the live DB:
    DATABASE_URL=postgresql://trading:trading@localhost:5432/trading \
        .venv/bin/python scripts/audit_stop_loss_attribution.py
"""
from __future__ import annotations

import os
import sys

import psycopg2
import psycopg2.extras


def _conn():
    url = os.environ.get(
        "DATABASE_URL", "postgresql://trading:trading@postgres:5432/trading"
    )
    return psycopg2.connect(url)


def _q(cur, sql, params=None):
    cur.execute(sql, params or ())
    return cur.fetchall()


def _row(cur, sql, params=None):
    return _q(cur, sql, params)[0]


def _pct(num, den):
    return f"{100.0 * num / den:.2f}%" if den else "n/a"


def main():
    conn = _conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # ---- universe counts ----
        total = _row(cur, "SELECT COUNT(*) AS c FROM trades")["c"]
        closed = _row(cur, "SELECT COUNT(*) AS c FROM trades WHERE exit_time IS NOT NULL")["c"]
        open_ = total - closed
        print(f"== Universe: {total} trades ({closed} closed, {open_} open) ==\n")

        if closed == 0:
            print("No closed trades to audit. Gate trivially passes (nothing to measure).")
            return 0

        # ---- M1: exit_reason distribution ----
        print("M1  exit_reason distribution (closed trades):")
        for r in _q(cur, """
            SELECT COALESCE(NULLIF(exit_reason,''), '<NULL/empty>') AS reason, COUNT(*) AS c
            FROM trades WHERE exit_time IS NOT NULL
            GROUP BY reason ORDER BY c DESC
        """):
            print(f"    {r['reason']:<24} {r['c']:>5}  ({_pct(r['c'], closed)})")
        print()

        # ---- M2: attribution coverage ----
        # LEGACY_FLATTEN is an operational force-close (no broker exit_order_id by
        # construction), but exit_reason fully explains it — not an attribution gap.
        legacy = _row(cur, """
            SELECT COUNT(*) AS c FROM trades
            WHERE exit_time IS NOT NULL AND exit_reason = 'LEGACY_FLATTEN'
        """)["c"]
        attributable = closed - legacy  # denominator excluding legacy flattens
        no_reason = _row(cur, """
            SELECT COUNT(*) AS c FROM trades
            WHERE exit_time IS NOT NULL
              AND exit_reason IS DISTINCT FROM 'LEGACY_FLATTEN'
              AND (exit_reason IS NULL OR exit_reason = '')
        """)["c"]
        no_exit_oid = _row(cur, """
            SELECT COUNT(*) AS c FROM trades
            WHERE exit_time IS NOT NULL
              AND exit_reason IS DISTINCT FROM 'LEGACY_FLATTEN'
              AND exit_order_id IS NULL
        """)["c"]
        fully_attributed = _row(cur, """
            SELECT COUNT(*) AS c FROM trades
            WHERE exit_time IS NOT NULL
              AND exit_reason IS DISTINCT FROM 'LEGACY_FLATTEN'
              AND COALESCE(exit_reason,'') <> ''
              AND exit_order_id IS NOT NULL
        """)["c"]
        gate = fully_attributed / attributable if attributable else 1.0
        print("M2  attribution coverage:")
        print(f"    closed missing exit_reason   : {no_reason}  ({_pct(no_reason, attributable)})")
        print(f"    closed missing exit_order_id  : {no_exit_oid}  ({_pct(no_exit_oid, attributable)})")
        print(f"    LEGACY_FLATTEN (excluded)     : {legacy}  ({_pct(legacy, closed)} of closed)")
        print(f"    fully attributed (reason+oid) : {fully_attributed}  ({_pct(fully_attributed, attributable)})")
        print(f"    >> attribution gate (>=99%, excl. legacy) : {'PASS' if gate >= 0.99 else 'FAIL'}  ({gate*100:.2f}%)\n")

        # ---- M3: stop-loss subset ----
        sl = _row(cur, """
            SELECT COUNT(*) AS total,
                   COUNT(exit_order_id) AS with_oid,
                   COUNT(exit_price)    AS with_price,
                   COUNT(qty)           AS with_qty,
                   COUNT(net_pnl)       AS with_pnl
            FROM trades WHERE exit_reason = 'stop_loss'
        """)
        print("M3  stop_loss subset:")
        print(f"    total               : {sl['total']}")
        if sl['total']:
            print(f"    with exit_order_id  : {sl['with_oid']}  ({_pct(sl['with_oid'], sl['total'])})")
            print(f"    with exit_price     : {sl['with_price']}  ({_pct(sl['with_price'], sl['total'])})")
            print(f"    with qty            : {sl['with_qty']}  ({_pct(sl['with_qty'], sl['total'])})")
            print(f"    with net_pnl        : {sl['with_pnl']}  ({_pct(sl['with_pnl'], sl['total'])})")
        print()

        # ---- M4 + M5: execution_decisions coverage / orphan exits ----
        # Join trades.exit_order_id -> execution_decisions.order_id (legacy flatten
        # has no exit_order_id and is excluded from the orphan denominator).
        ed_join = _row(cur, """
            SELECT COUNT(*) AS c FROM trades t
            JOIN execution_decisions ed ON ed.order_id = t.exit_order_id
            WHERE t.exit_time IS NOT NULL
              AND t.exit_reason IS DISTINCT FROM 'LEGACY_FLATTEN'
        """)["c"]
        orphan = attributable - ed_join
        # Breakdown by exit_reason: does a matching SELL decision row exist?
        print("M4  execution_decisions coverage (Decision Log) per exit_reason:")
        for r in _q(cur, """
            WITH lab AS (
              SELECT exit_order_id,
                     COALESCE(NULLIF(exit_reason,''), '<NULL>') AS reason
              FROM trades WHERE exit_time IS NOT NULL
            )
            SELECT l.reason, COUNT(*) AS total, COUNT(ed.id) AS joined
            FROM lab l
            LEFT JOIN execution_decisions ed ON ed.order_id = l.exit_order_id
            GROUP BY l.reason ORDER BY total DESC
        """):
            print(f"    {r['reason']:<24} total {r['total']:>4}  joined {r['joined']:>4}  ({_pct(r['joined'], r['total'])})")
        print(f"M5  orphan exit orders (no decision row): {orphan}  ({_pct(orphan, closed)})")
        print(f"    -> stop_loss exits are expected to land here (Gap A: no SELL decision row written).\n")

        # ---- M6: double-close ----
        dups = _q(cur, """
            SELECT exit_order_id, COUNT(*) AS c FROM trades
            WHERE exit_order_id IS NOT NULL
            GROUP BY exit_order_id HAVING COUNT(*) > 1
            ORDER BY c DESC LIMIT 20
        """)
        print(f"M6  double-close (one exit_order_id on >1 trade): {len(dups)} order(s)")
        for d in dups[:5]:
            print(f"    {d['exit_order_id']}: on {d['c']} trades")
        print()

        # ---- M7: pending P&L ----
        pending = _row(cur, """
            SELECT COUNT(*) AS c FROM trades
            WHERE exit_time IS NOT NULL
              AND COALESCE(exit_reason,'') <> ''
              AND (exit_price IS NULL OR net_pnl IS NULL)
        """)["c"]
        pending_no_exit_px = _row(cur, """
            SELECT COUNT(*) AS c FROM trades
            WHERE exit_time IS NOT NULL AND exit_price IS NULL
        """)["c"]
        print("M7  pending P&L (exit_reason set, awaiting daily reconcile):")
        print(f"    exit_reason set but exit_price/net_pnl NULL : {pending}  ({_pct(pending, closed)})")
        print(f"    closed with exit_price NULL                 : {pending_no_exit_px}  ({_pct(pending_no_exit_px, closed)})")
        print()

        # ---- M8: unreconciled entries ----
        unrec_entry = _row(cur, """
            SELECT COUNT(*) AS c FROM trades
            WHERE entry_price IS NULL AND entry_time IS NOT NULL
              AND entry_time > now() - '7 days'::interval
        """)["c"]
        print(f"M8  unreconciled entry_price (last 7d, non-open): {unrec_entry}\n")

        # ---- M9: S4 exit freshness (sentiment-driven exits) ----
        # For exit_reason in ('stop_loss','sentiment_reversal','portfolio_sell')
        # joined to sentiment_signals via signal_id, report signal age at exit.
        print("M9  S4 exit freshness (exit citing signal age; SPCX-class anomaly):")
        rows = _q(cur, """
            SELECT t.symbol, t.exit_reason,
                   EXTRACT(EPOCH FROM (t.exit_time - ss.generated_at))/3600.0 AS signal_age_h,
                   t.exit_time, ss.generated_at
            FROM trades t
            LEFT JOIN sentiment_signals ss ON ss.id = t.signal_id
            WHERE t.exit_time IS NOT NULL
              AND t.signal_id IS NOT NULL
              AND t.exit_reason IN ('stop_loss','sentiment_reversal','portfolio_sell')
            ORDER BY t.exit_time DESC LIMIT 15
        """)
        stale = 0
        for r in rows:
            age = r["signal_age_h"]
            mark = ""
            if age is not None and age > 4.0:
                mark = "  <-- >4h (stale vs max_age)"
                stale += 1
            age_s = f"{age:.1f}h" if age is not None else "n/a"
            print(f"    {r['symbol']:<6} {r['exit_reason']:<20} sig_age={age_s:<8}{mark}")
        print(f"    (showing up to 15 most recent; {stale} stale >4h in this window)\n")

    conn.close()

    # ---- verdict ----
    print("=" * 64)
    print(f"ATTRIBUTION GATE: {'PASS' if gate >= 0.99 else 'FAIL'} ({gate*100:.2f}%)")
    notes = []
    if sl["total"] and sl["with_pnl"] < sl["total"]:
        notes.append(
            f"stop_loss P&L coverage {sl['with_pnl']}/{sl['total']} incomplete — "
            "daily reconcile has not caught up on some stops; "
            "a 15-min replay cannot rely on trades.net_pnl alone."
        )
    if orphan:
        notes.append(
            f"{orphan} closed trade(s) have no matching execution_decisions row — "
            "Decision Log is silent on those exits (incl. all stop_loss)."
        )
    if pending:
        notes.append(
            f"{pending} closed trade(s) lack exit_price/net_pnl — "
            "awaiting reconcile_trade_fills; defer measurement until reconciled."
        )
    if notes:
        print("Notes:")
        for n in notes:
            print(f"  - {n}")
    return 0 if gate >= 0.99 else 1


if __name__ == "__main__":
    sys.exit(main())