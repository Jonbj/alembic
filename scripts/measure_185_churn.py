#!/usr/bin/env python3
"""#185 post-flip churn measurement — the operator's falsification test, runnable.

The defect #185 documents is a *signature*, not a drop count: an S1 position
liquidated by `s1_weight_drop` and then re-bought at the same weight within
15-60 minutes. The PR that fixed it (#188) shipped a verification query that
counted `trades.exit_reason LIKE '%s1_weight_drop%'` — but `trades.exit_reason`
only ever holds `portfolio_sell` / `sentiment_reversal`; the structured
mechanism lives in `execution_decisions.exit_mechanism`. That query returns
zero on every day, pre- or post-fix, so it can neither confirm the fix nor
raise the alarm the operator asked for ("if the churn doesn't stop, the
diagnosis was incomplete"). This script reads the right column and classifies
each drop against the re-entry signature, so a non-zero `churn` count post-fix
is the real signal that the diagnosis was incomplete.

Read-only. Run inside the worker container:
    docker compose exec worker python scripts/measure_185_churn.py
Or locally against the live DB:
    DATABASE_URL=postgresql://trading:trading@localhost:5432/trading \
        .venv/bin/python scripts/measure_185_churn.py

The deploy cutoff defaults to the first S1 rebalance after the #185 fix went
live (2026-08-07 14:07 UTC, read back from the worker log); override with
--deploy-cutoff for a different flip time.
"""
from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras

# First S1 rebalance after the #185 deploy — the cycle that wrote the
# rebalance clock and froze S1's book until the next monthly window. Drops at
# or after this timestamp are post-fix; the single BRK.B drop at 14:22 that
# day is the liquidation of a pre-fix position decided at this very rebalance,
# not churn (no re-entry follows).
DEFAULT_DEPLOY_CUTOFF = datetime(2026, 8, 7, 14, 7, 0, tzinfo=timezone.utc)

# The operator's churn window: re-entry "15-60 minuti" after the drop. We look
# up to the wide end; the lower bound is the natural cadence (a re-entry on the
# very next 15-min cycle is the canonical case), so only the upper bound gates.
REENTRY_WINDOW = timedelta(minutes=60)


def classify_drops(rows: list[dict], reentry_window: timedelta = REENTRY_WINDOW) -> list[dict]:
    """Classify each `s1_weight_drop` exit as churn or definitive.

    `rows` is a chronologically-ordered list of decision dicts with keys
    `tick_time` (tz-aware datetime), `symbol`, `decision`, `exit_mechanism`.
    A drop is *churn* when a BUY on the same symbol follows within
    `reentry_window`; otherwise it is a definitive (legitimate) liquidation.
    Returns one dict per drop: {tick_time, symbol, reentry_time, is_churn}.
    """
    drops = [r for r in rows if r.get("exit_mechanism") == "s1_weight_drop"]
    buys_by_symbol: dict[str, list[datetime]] = {}
    for r in rows:
        if r.get("decision") == "BUY":
            buys_by_symbol.setdefault(r["symbol"], []).append(r["tick_time"])

    out: list[dict] = []
    for d in drops:
        reentry: datetime | None = None
        for b in buys_by_symbol.get(d["symbol"], []):
            if b <= d["tick_time"]:
                continue
            if b - d["tick_time"] <= reentry_window:
                reentry = b
                break  # first re-entry within the window wins
        out.append({
            "tick_time": d["tick_time"],
            "symbol": d["symbol"],
            "reentry_time": reentry,
            "is_churn": reentry is not None,
        })
    return out


def per_session(drops: list[dict], deploy_cutoff: datetime) -> list[dict]:
    """Aggregate classified drops by UTC date, tagged pre/post the deploy cutoff.

    A drop whose `tick_time` is at or after `deploy_cutoff` is `post`; the
    cutoff is the first rebalance under the fix, so a drop at that instant is
    already the fix deciding, not the old code churning.
    """
    by_date: dict[str, dict] = {}
    for d in drops:
        date = d["tick_time"].astimezone(timezone.utc).date().isoformat()
        slot = by_date.setdefault(
            date, {"date": date, "drops": 0, "churn": 0, "_post": True}
        )
        slot["drops"] += 1
        if d["is_churn"]:
            slot["churn"] += 1
        # Phase is decided per-drop against the cutoff (mid-session on the
        # deploy day), so a session is "post" only when every one of its drops
        # fell at or after the fix took effect.
        if d["tick_time"].astimezone(timezone.utc) < deploy_cutoff:
            slot["_post"] = False
    for slot in by_date.values():
        slot["phase"] = "post" if slot.pop("_post") else "pre"
    return sorted(by_date.values(), key=lambda r: r["date"])


def _conn():
    url = os.environ.get(
        "DATABASE_URL", "postgresql://trading:trading@postgres:5432/trading"
    )
    return psycopg2.connect(url)


def _fetch_rows(conn, since: datetime) -> list[dict]:
    """Pull the S1 weight-drop exits and every BUY from `execution_decisions`.

    Only `s1_weight_drop` SELLs and BUYs are needed: classify_drops ignores
    every other row, so we don't fetch them. Ordered by tick_time so the
    re-entry scan in classify_drops sees buys in chronological order.
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT tick_time, symbol, decision, exit_mechanism
            FROM execution_decisions
            WHERE tick_time >= %s
              AND (
                (decision IN ('SELL', 'EXIT') AND exit_mechanism = 's1_weight_drop')
                OR decision = 'BUY'
              )
            ORDER BY tick_time
            """,
            (since,),
        )
        return [dict(r) for r in cur.fetchall()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--deploy-cutoff",
        default=DEFAULT_DEPLOY_CUTOFF.isoformat(),
        help="ISO timestamp of the first S1 rebalance under the #185 fix.",
    )
    parser.add_argument(
        "--since",
        default=(DEFAULT_DEPLOY_CUTOFF - timedelta(days=14)).isoformat(),
        help="ISO timestamp to start reading decisions from (default: 14d pre-fix).",
    )
    args = parser.parse_args()

    deploy_cutoff = datetime.fromisoformat(args.deploy_cutoff)
    if deploy_cutoff.tzinfo is None:
        deploy_cutoff = deploy_cutoff.replace(tzinfo=timezone.utc)
    since = datetime.fromisoformat(args.since)
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)

    conn = _conn()
    try:
        rows = _fetch_rows(conn, since)
    finally:
        conn.close()

    drops = classify_drops(rows)
    sessions = per_session(drops, deploy_cutoff)

    pre = [s for s in sessions if s["phase"] == "pre"]
    post = [s for s in sessions if s["phase"] == "post"]
    pre_churn = sum(s["churn"] for s in pre)
    post_churn = sum(s["churn"] for s in post)

    print(f"== #185 churn measurement: {since.date()} → {deploy_cutoff.date()} (deploy cutoff) ==")
    print()
    print(f"{'date (UTC)':<12} {'phase':<6} {'drops':>6} {'churn':>6}")
    for s in sessions:
        print(f"{s['date']:<12} {s['phase']:<6} {s['drops']:>6} {s['churn']:>6}")
    print()
    print(f"pre-fix  : {len(pre)} session(s), {sum(s['drops'] for s in pre)} drops, {pre_churn} churn")
    print(f"post-fix : {len(post)} session(s), {sum(s['drops'] for s in post)} drops, {post_churn} churn")
    print()
    if post_churn == 0:
        print("post-fix churn = 0: the s1_weight_drop -> re-entry signature is gone.")
    else:
        print(f"post-fix churn = {post_churn}: the signature persisted — the diagnosis was incomplete.")
    print(
        "\nNote: a non-churn drop (e.g. BRK.B 2026-08-07 14:22 UTC) is a definitive "
        "monthly liquidation decided at the rebalance, not churn. The pre/post S1 "
        "evidence series is not comparable across the deploy cutoff — the "
        "discontinuity is annotated at the 40-day synthesis per the observation charter."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())