#!/usr/bin/env python3
"""Stage 2: manual model-comparison report (read-only — does not touch Redis and
does not disarm shadow mode; the auto-report Celery task does that on its own
7-day schedule, see src/workers/performance.run_shadow_comparison_report).

Fetches shadow (llm_shadow_responses) + live (llm_responses) per-model rows
since --since, joins forward returns from sentiment_signals, and prints the
same ranked markdown report an operator would get from the auto-report.

Run: .venv/bin/python scripts/report_model_comparison.py --since 2026-07-07T00:00:00+00:00
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.config import config  # noqa: E402
from src.performance.model_comparison import build_comparison, render_markdown  # noqa: E402
from src.store.pg_store import PostgreSQLStore  # noqa: E402

_COLS = ["news_log_id", "model_id", "polarity", "confidence", "parse_error"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", required=True, help="ISO timestamp, e.g. 2026-07-07T00:00:00+00:00")
    args = parser.parse_args()

    since = datetime.fromisoformat(args.since)

    pg = PostgreSQLStore()
    try:
        rows = pd.DataFrame(
            list(pg.fetch_shadow_rows(since)) + list(pg.fetch_live_response_rows(since)),
            columns=_COLS,
        )
        fwd = dict(pg.fetch_fwd_by_news(since))
    finally:
        pg.close()

    report = build_comparison(rows, fwd, divergence_threshold=config.ENSEMBLE_DIVERGENCE_STD)
    print(render_markdown(report))


if __name__ == "__main__":
    main()
