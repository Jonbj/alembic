#!/usr/bin/env python3
"""Misura la firma di churn S1 descritta dalla issue #185.

Una uscita conta come churn solo se una posizione S1 chiusa da
``s1_weight_drop`` viene ricomprata da S1, allo stesso peso, tra 15 e 60
minuti dopo. Le righe senza ``order_id`` non rappresentano ordini eseguiti e
sono escluse. Lo script legge soltanto ``execution_decisions`` e ``trades``.
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta, timezone
from typing import Any


DEFAULT_DEPLOY_CUTOFF = datetime(2026, 8, 7, 14, 7, tzinfo=timezone.utc)
MIN_REENTRY_DELAY = timedelta(minutes=15)
MAX_REENTRY_DELAY = timedelta(minutes=60)


def _same_weight(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return False
    try:
        # portfolio_scheduler writes target weights in the Decision Log as a
        # percentage with one decimal (for example 1.2%).  The raw value moves
        # slightly with NAV between cycles, so compare the exact operator-visible
        # weight instead of pretending the binary floats should be identical.
        return f"{float(left) * 100:.1f}" == f"{float(right) * 100:.1f}"
    except (TypeError, ValueError):
        return False


def classify_drops(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Classifica le uscite S1 eseguite contro la firma prescritta da #185."""
    drops = [
        row
        for row in rows
        if row.get("decision") in {"SELL", "EXIT"}
        and row.get("exit_mechanism") == "s1_weight_drop"
        and row.get("strategy_id") == "S1"
        and row.get("order_id")
    ]
    buys_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if (
            row.get("decision") == "BUY"
            and row.get("strategy_id") == "S1"
            and row.get("order_id")
        ):
            buys_by_symbol.setdefault(str(row["symbol"]), []).append(row)
    for buys in buys_by_symbol.values():
        buys.sort(key=lambda row: row["tick_time"])

    classified: list[dict[str, Any]] = []
    for drop in drops:
        reentry_time = None
        for buy in buys_by_symbol.get(str(drop["symbol"]), []):
            delay = buy["tick_time"] - drop["tick_time"]
            if delay < MIN_REENTRY_DELAY:
                continue
            if delay > MAX_REENTRY_DELAY:
                break
            if _same_weight(drop.get("target_weight"), buy.get("target_weight")):
                reentry_time = buy["tick_time"]
                break
        classified.append(
            {
                "tick_time": drop["tick_time"],
                "symbol": drop["symbol"],
                "target_weight": drop.get("target_weight"),
                "reentry_time": reentry_time,
                "is_churn": reentry_time is not None,
            }
        )
    return classified


def per_session(
    drops: list[dict[str, Any]], deploy_cutoff: datetime
) -> list[dict[str, Any]]:
    """Aggrega le uscite per data UTC e le separa sul cutoff di deploy."""
    sessions: dict[str, dict[str, Any]] = {}
    for drop in drops:
        tick_time = drop["tick_time"].astimezone(timezone.utc)
        date = tick_time.date().isoformat()
        slot = sessions.setdefault(
            date,
            {"date": date, "phase": "post", "drops": 0, "churn": 0},
        )
        slot["drops"] += 1
        slot["churn"] += int(drop["is_churn"])
        if tick_time < deploy_cutoff:
            slot["phase"] = "pre"
    return sorted(sessions.values(), key=lambda row: row["date"])


def _fetch_rows(conn: Any, since: datetime) -> list[dict[str, Any]]:
    """Legge drop e BUY con attribuzione, peso e prova di submission."""
    from psycopg2.extras import RealDictCursor

    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            WITH drop_events AS (
                SELECT ed.tick_time,
                       ed.symbol,
                       ed.decision,
                       ed.exit_mechanism,
                       t.stop_strategy AS strategy_id,
                       t.score AS target_weight,
                       ed.order_id
                FROM execution_decisions ed
                JOIN trades t
                  ON ed.order_id = t.exit_order_id
                  OR ed.order_id = ANY(COALESCE(t.exit_order_ids, ARRAY[]::TEXT[]))
                WHERE ed.tick_time >= %s
                  AND ed.decision IN ('SELL', 'EXIT')
                  AND ed.exit_mechanism = 's1_weight_drop'
                  AND ed.order_id IS NOT NULL
            ),
            buy_events AS (
                SELECT ed.tick_time,
                       ed.symbol,
                       ed.decision,
                       ed.exit_mechanism,
                       t.stop_strategy AS strategy_id,
                       t.score AS target_weight,
                       ed.order_id
                FROM execution_decisions ed
                JOIN trades t
                  ON t.decision_id = ed.id
                 AND t.entry_order_id = ed.order_id
                WHERE ed.tick_time >= %s
                  AND ed.decision = 'BUY'
                  AND ed.order_id IS NOT NULL
            )
            SELECT * FROM drop_events
            UNION ALL
            SELECT * FROM buy_events
            ORDER BY tick_time
            """,
            (since, since),
        )
        return [dict(row) for row in cursor.fetchall()]


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _connect():
    import psycopg2

    database_url = os.environ.get(
        "DATABASE_URL", "postgresql://trading:trading@postgres:5432/trading"
    )
    return psycopg2.connect(database_url)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--deploy-cutoff",
        default=DEFAULT_DEPLOY_CUTOFF.isoformat(),
        help="Primo ribilanciamento S1 dopo il deploy del fix.",
    )
    parser.add_argument(
        "--since",
        default=(DEFAULT_DEPLOY_CUTOFF - timedelta(days=14)).isoformat(),
        help="Inizio della finestra letta dal DB.",
    )
    args = parser.parse_args()
    deploy_cutoff = _parse_timestamp(args.deploy_cutoff)
    since = _parse_timestamp(args.since)

    conn = _connect()
    try:
        drops = classify_drops(_fetch_rows(conn, since))
    finally:
        conn.close()
    sessions = per_session(drops, deploy_cutoff)

    print(f"{'date (UTC)':<12} {'phase':<6} {'drops':>6} {'churn':>6}")
    for session in sessions:
        print(
            f"{session['date']:<12} {session['phase']:<6} "
            f"{session['drops']:>6} {session['churn']:>6}"
        )

    pre = [session for session in sessions if session["phase"] == "pre"]
    post = [session for session in sessions if session["phase"] == "post"]
    pre_churn = sum(session["churn"] for session in pre)
    post_churn = sum(session["churn"] for session in post)
    print()
    print(f"pre-fix churn:  {pre_churn}")
    print(f"post-fix churn: {post_churn}")
    if post_churn:
        print("Firma ancora presente: la diagnosi di #185 e' incompleta.")
    else:
        print("Firma assente dopo il deploy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
