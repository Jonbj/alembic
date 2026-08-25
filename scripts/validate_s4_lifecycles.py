#!/usr/bin/env python3
"""Valida coverage e residui del lifecycle S4 su una finestra esplicita."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date
from typing import Sequence

import psycopg2
from psycopg2.extras import RealDictCursor

from src.config import config


MINIMUM_COVERAGE = 0.95


def _fetch_rows(start: date, end: date) -> list[dict]:
    with psycopg2.connect(config.DATABASE_URL) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT reconstructible, reason_code
                FROM s4_lifecycle_current
                WHERE COALESCE(d0, observed_at::date) BETWEEN %s AND %s
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
    reconstructible = sum(bool(row.get("reconstructible")) for row in rows)
    coverage = reconstructible / total if total else None
    residuals = Counter(
        str(row.get("reason_code") or "UNCLASSIFIED")
        for row in rows
        if not row.get("reconstructible")
    )
    return {
        "window_start": start,
        "window_end": end,
        "minimum_coverage": minimum_coverage,
        "total": total,
        "reconstructible": reconstructible,
        "coverage": coverage,
        "meets_minimum": coverage is not None and coverage >= minimum_coverage,
        "residual_by_reason": dict(sorted(residuals.items())),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verifica il gate di ricostruibilita' lifecycle S4 (#295)."
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
