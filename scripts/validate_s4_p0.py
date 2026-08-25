#!/usr/bin/env python3
"""Valida coverage e residui della baseline P0 su una finestra esplicita."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Sequence
from datetime import date

import psycopg2
from psycopg2.extras import RealDictCursor

from src.config import config

MINIMUM_COVERAGE = 0.95


def _fetch_rows(start: date, end: date) -> list[dict]:
    with (
        psycopg2.connect(config.DATABASE_URL) as conn,
        conn.cursor(cursor_factory=RealDictCursor) as cursor,
    ):
        cursor.execute(
            """
            SELECT comparable, reason_code
            FROM s4_exit_policy_current
            WHERE policy_id = 'P0'
              AND COALESCE(d0, observed_at::date) BETWEEN %s AND %s
            ORDER BY intent_id
            """,
            (start, end),
        )
        return [dict(row) for row in cursor.fetchall()]


def summarize(
    rows: list[dict],
    *,
    start: str,
    end: str,
    minimum_coverage: float = MINIMUM_COVERAGE,
) -> dict[str, object]:
    total = len(rows)
    comparable = sum(bool(row.get("comparable")) for row in rows)
    coverage = comparable / total if total else None
    residuals = Counter(
        str(row.get("reason_code") or "P0_UNCLASSIFIED")
        for row in rows
        if not row.get("comparable")
    )
    take_profit_count = residuals.get("P0_TAKE_PROFIT_DISABLED", 0)
    take_profit_rate = take_profit_count / total if total else None
    return {
        "window_start": start,
        "window_end": end,
        "minimum_coverage": minimum_coverage,
        "total": total,
        "comparable": comparable,
        "coverage": coverage,
        "meets_minimum": coverage is not None and coverage >= minimum_coverage,
        "take_profit_live_count": take_profit_count,
        "take_profit_live_rate": take_profit_rate,
        "take_profit_exceeds_contract_threshold": (
            take_profit_rate is not None and take_profit_rate > 0.05
        ),
        "residual_by_reason": dict(sorted(residuals.items())),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verifica il gate di comparabilita' P0 del trial exit S4 (#296)."
    )
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    args = parser.parse_args(argv)
    if args.end < args.start:
        parser.error("--end precede --start")

    rows = _fetch_rows(args.start, args.end)
    report = summarize(
        rows,
        start=args.start.isoformat(),
        end=args.end.isoformat(),
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if not rows:
        return 2
    return 0 if report["meets_minimum"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
