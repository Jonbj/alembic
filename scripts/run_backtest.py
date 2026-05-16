#!/usr/bin/env python3
"""Historical GKG backtest runner.

Usage:
    python scripts/run_backtest.py \\
        --start 2025-10-01 \\
        --end   2026-04-30 \\
        --run-id gkg-6m-v1 \\
        [--dry-run] \\
        [--max-per-chunk 250]

Phases:
    1. Fetch GKG historical news → TickerExtractor → write pending rows
    2. LLM inference (checkpoint/resume; skips score IS NOT NULL rows)
    3. ForwardReturnCalculator: populate 1h/4h/24h from yfinance
    4. BacktestReportBuilder: compute IC/ICIR, print + save JSON
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from tqdm import tqdm

from src.backtest.forward_returns import ForwardReturnCalculator
from src.backtest.report import BacktestReportBuilder
from src.config import config
from src.connectors.gdelt_gkg import GDELTGKGConnector
from src.connectors.ticker_extractor import TickerExtractor
from src.llm.budget import LLMBudgetTracker
from src.llm.client import DeepseekClient, GlmClient, Qwen35Client
from src.llm.ensemble import EnsembleAggregator
from src.llm.finbert import FinBERTClient
from src.models.news import NewsItem
from src.workers.sentiment import run_inference

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

_INSERT_PENDING = """
    INSERT INTO backtest_signals (run_id, symbol, article_title, article_url, generated_at)
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (run_id, symbol, article_url, generated_at) DO NOTHING
"""

_SELECT_PENDING = """
    SELECT id, symbol, generated_at, article_url, article_title
    FROM backtest_signals
    WHERE run_id = %s AND score IS NULL
    ORDER BY generated_at
"""

_UPDATE_SCORED = """
    UPDATE backtest_signals
    SET score=%s, confidence=%s, reasoning=%s, model_id=%s,
        ensemble_std=%s, fallback_used=%s
    WHERE id=%s
"""

_DRY_RUN_UPDATE = """
    UPDATE backtest_signals
    SET score=0.0, confidence=0.5, reasoning='dry_run',
        model_id='dry_run', fallback_used=FALSE
    WHERE id=%s
"""


def _estimate_cost(pending_count: int) -> float:
    """Estimate inference cost: 3 models × ~300 input + ~100 output tokens × cloud rates.

    Uses conservative cloud model pricing ($2/1M input, $6/1M output) — an upper
    bound for GLM-5.1, Qwen3.5, and DeepSeek-V4-Pro accessed via Ollama cloud.
    Actual Ollama cloud rates are typically lower; this prevents surprise bills.
    Prompts a human confirmation if estimate > $10.
    """
    # Conservative upper bound for Ollama :cloud models
    cost_per_call = (300 * 2.0 + 100 * 6.0) / 1_000_000
    return pending_count * 3 * cost_per_call


def phase1_fetch(
    connector: GDELTGKGConnector,
    extractor: TickerExtractor,
    pg_conn,
    run_id: str,
    start: datetime,
    end: datetime,
    max_per_chunk: int,
) -> int:
    """Phase 1: fetch GKG historical news, extract tickers, write pending rows.

    Why async → sync bridge via asyncio.run?
      The connector is async (aiohttp), but the CLI is synchronous for simplicity.
      We collect all GKG items into a list before entering the synchronous
      PostgreSQL loop. For 6 months × 250 records this is ~1500 items — negligible
      memory footprint.

    Why INSERT … ON CONFLICT DO NOTHING?
      Re-running the same backtest period with the same run_id should be idempotent.
      The unique index (run_id, symbol, article_url, generated_at) prevents duplicates.
    """
    log.info("Phase 1: fetching GKG news from %s to %s", start.date(), end.date())

    async def _fetch():
        return [item async for item in connector.fetch_historical(start, end, max_per_chunk)]

    gkg_items = asyncio.run(_fetch())
    log.info("Fetched %d GKG records", len(gkg_items))

    inserted = 0
    with pg_conn.cursor() as cur:
        for item in tqdm(gkg_items, desc="Phase 1: extracting tickers"):
            tickers = extractor.extract(item.org_names)
            for ticker in tickers:
                cur.execute(_INSERT_PENDING, (
                    run_id, ticker, item.title or "", item.url, item.timestamp
                ))
                if cur.rowcount > 0:
                    inserted += 1
    pg_conn.commit()
    log.info("Phase 1 complete: %d pending rows", inserted)
    return inserted


def phase2_infer(pg_conn, run_id: str, dry_run: bool) -> int:
    """Phase 2: run LLM inference on pending rows. Skips rows with score IS NOT NULL.

    Checkpoint / resume semantics:
      - SELECT filters `score IS NULL`. If Phase 2 crashes after processing 500
        of 1000 rows, the 500 scored rows remain in the DB. On restart, the
        SELECT skips them automatically — no extra state file needed.

    Dry-run mode:
      - Writes score=0.0, confidence=0.5 without any LLM call.
      - Useful for testing the pipeline end-to-end without API costs.
      - Still requires a FinBERTClient instance (no-op, not called for dry-run).

    Cost guardrail:
      - Calls _estimate_cost() before inference. If > $10, prompts user for
        confirmation. Prevents accidental 6-month full-ensemble runs.

    Why instantiate clients inside phase2_infer (not main)?
      Keeps client lifecycle scoped to the phase that actually uses them.
      If Phase 2 is skipped (all rows already scored), no clients are created.
    """
    with pg_conn.cursor() as cur:
        cur.execute(_SELECT_PENDING, (run_id,))
        rows = cur.fetchall()

    if not rows:
        log.info("Phase 2: no pending rows for run_id=%s", run_id)
        return 0

    if not dry_run:
        est = _estimate_cost(len(rows))
        print(f"\nEstimated inference cost: ${est:.2f} for {len(rows)} articles × 3 models")
        if est > 10.0:
            answer = input("Continue? [y/N] ").strip().lower()
            if answer != "y":
                print("Aborted.")
                sys.exit(0)

    clients = [] if dry_run else [GlmClient(), Qwen35Client(), DeepseekClient()]
    aggregator = EnsembleAggregator(
        min_confidence=config.ENSEMBLE_MIN_CONFIDENCE,
        divergence_threshold=config.ENSEMBLE_DIVERGENCE_STD,
    )
    finbert = FinBERTClient()
    budget_tracker = LLMBudgetTracker(conn=pg_conn)

    processed = 0
    with pg_conn.cursor() as cur:
        for row_id, symbol, generated_at, article_url, article_title in tqdm(
            rows, desc="Phase 2: inference"
        ):
            if dry_run:
                cur.execute(_DRY_RUN_UPDATE, (row_id,))
                processed += 1
                continue

            # Reconstruct a minimal NewsItem from DB columns.
            # Body = title (GKG only stores title, no full article text).
            item = NewsItem(
                id=f"{article_url}:{symbol}",
                body=article_title or "",
                title=article_title or "",
                asset_tags=[symbol],
                url=article_url,
                timestamp=generated_at,
            )
            result = asyncio.run(
                run_inference(item, clients, aggregator, finbert, budget_tracker)
            )
            if result is not None:
                cur.execute(_UPDATE_SCORED, (
                    result.score, result.confidence, result.reasoning,
                    result.model_id, result.ensemble_std, result.fallback_used,
                    row_id,
                ))
                processed += 1

    pg_conn.commit()
    log.info("Phase 2 complete: %d rows scored", processed)
    return processed


def phase3_forward_returns(pg_conn, run_id: str, start: datetime, end: datetime) -> int:
    """Phase 3: populate forward_return_1h/4h/24h from yfinance.

    Delegates entirely to ForwardReturnCalculator.populate().
    See src/backtest/forward_returns.py for the vectorized download logic.
    """
    log.info("Phase 3: computing forward returns for run_id=%s", run_id)
    calc = ForwardReturnCalculator(pg_conn)
    updated = calc.populate(run_id, start, end)
    log.info("Phase 3 complete: %d rows updated", updated)
    return updated


def phase4_report(pg_conn, run_id: str) -> None:
    """Phase 4: build and print IC/ICIR report, save to reports/ directory.

    Output:
      - stdout: human-readable summary (horizons + per-model 24h IC).
      - JSON:   reports/backtest_{run_id}.json (machine-readable for CI / dashboards).
    """
    log.info("Phase 4: building report for run_id=%s", run_id)
    builder = BacktestReportBuilder(pg_conn)
    report = builder.build(run_id)

    print("\n" + "=" * 60)
    print(f"BACKTEST REPORT — {run_id}")
    print("=" * 60)
    if report.period_start and report.period_end:
        print(f"Period:                 {report.period_start.date()} → {report.period_end.date()}")
    print(f"Total signals:          {report.total_signals}")
    print(f"Signals with returns:   {report.signals_with_returns}")
    for horizon, ic, icir in [
        ("1h",  report.ic_1h,  report.icir_1h),
        ("4h",  report.ic_4h,  report.icir_4h),
        ("24h", report.ic_24h, report.icir_24h),
    ]:
        if ic is not None:
            print(f"\nHorizon {horizon}:")
            print(f"  Composite IC:  {ic.composite_ic:.4f}")
            print(f"  Spearman IC:   {ic.spearman_ic:.4f}")
            print(f"  ICIR:          {icir.icir:.4f}" if icir else "  ICIR: n/a")
        else:
            print(f"\nHorizon {horizon}: insufficient samples (<30)")
    print("\nPer-model IC (all horizons):")
    for model, stats in report.by_model.items():
        parts = []
        for h in ("1h", "4h", "24h"):
            v = stats.get(f"ic_{h}")
            parts.append(f"{h}={'n/a' if v is None else f'{v:.4f}'}")
        print(f"  {model}: {', '.join(parts)}, n={stats['sample_count']}")

    Path("reports").mkdir(exist_ok=True)
    out_path = Path(f"reports/backtest_{run_id}.json")
    out_path.write_text(json.dumps(report.to_dict(), indent=2))
    print(f"\nReport saved to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run GKG historical backtest")
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--run-id", required=True, help="Unique run identifier")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip LLM inference; write score=0.0 for testing")
    parser.add_argument("--max-per-chunk", type=int, default=250,
                        help="Max GKG records per monthly chunk (default 250)")
    args = parser.parse_args()

    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)

    pg_conn = psycopg2.connect(config.DATABASE_URL)
    try:
        connector = GDELTGKGConnector(max_records=args.max_per_chunk)
        extractor = TickerExtractor(pg_conn)

        phase1_fetch(connector, extractor, pg_conn, args.run_id, start, end,
                     args.max_per_chunk)
        phase2_infer(pg_conn, args.run_id, dry_run=args.dry_run)
        phase3_forward_returns(pg_conn, args.run_id, start, end)
        phase4_report(pg_conn, args.run_id)
    finally:
        pg_conn.close()


if __name__ == "__main__":
    main()
