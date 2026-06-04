#!/usr/bin/env python3
"""Alpaca/Benzinga IC backtest for small/mid-cap watchlist candidates.

Usage:
    python scripts/backtest_smallmid_ic.py \\
      --symbols CRDO ALAB GFS ADI \\
      --baseline INTC NVDA MU AMD \\
      --days 90 \\
      --run-id alpaca-smallmid-2506 \\
      [--dry-run] \\
      [--concurrency 5] \\
      [--yes]

Phases:
    1. Fetch Alpaca/Benzinga historical news per symbol, write pending rows
    2. LLM inference (checkpoint/resume; skips score IS NOT NULL rows)
    3. ForwardReturnCalculator: populate 1h/4h/24h from yfinance
    4. BacktestReportBuilder: compute IC/ICIR, print report
    5. Gate check: print promotion table (IC_24h >= 0.15 AND ICIR_24h >= 2.0)
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
from tqdm import tqdm

from src.config import config
from src.connectors.alpaca_news import AlpacaNewsConnector
from src.llm.budget import NoOpBudgetTracker
from src.llm.client import OllamaDeepseekClient, OllamaGlmClient
from src.llm.ensemble import EnsembleAggregator
from src.llm.finbert import FinBERTClient
from src.models.news import NewsItem
from src.workers.sentiment import run_inference

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

IC_THRESHOLD = 0.15
ICIR_THRESHOLD = 2.0

_INSERT_PENDING = """
    INSERT INTO backtest_signals (run_id, symbol, article_title, article_url, generated_at, news_source)
    VALUES (%s, %s, %s, %s, %s, %s)
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


async def _collect_news(connector, start: datetime, end: datetime):
    """Async helper to collect news items from a connector."""
    return [item async for item in connector.fetch_historical(start, end)]


async def _infer_batch(
    rows: list[tuple],
    clients: list,
    aggregator: EnsembleAggregator,
    finbert: FinBERTClient,
    budget_tracker: NoOpBudgetTracker,
) -> list:
    """Run inference on a batch of DB rows in parallel via asyncio.gather."""
    async def _single(row):
        row_id, symbol, generated_at, article_url, article_title = row
        item = NewsItem(
            id=f"{article_url}:{symbol}",
            body=article_title or "",
            title=article_title or "",
            asset_tags=[symbol],
            url=article_url,
            timestamp=generated_at,
        )
        result = await run_inference(item, clients, aggregator, finbert, budget_tracker)
        return row_id, result

    return await asyncio.gather(*[_single(row) for row in rows], return_exceptions=True)


def _estimate_cost(pending_count: int) -> float:
    """Estimate cost: 2 models × (~300 input tokens @ $2/M + ~100 output tokens @ $6/M)."""
    cost_per_model_call = (300 * 2.0 + 100 * 6.0) / 1_000_000
    return pending_count * 2 * cost_per_model_call


def phase1_fetch(pg_conn, run_id: str, symbols: list[str], start: datetime, end: datetime) -> int:
    """Phase 1: fetch Alpaca historical news per symbol, write pending rows.

    One AlpacaNewsConnector per symbol so Benzinga filtering is exact.
    Inserts only article_title + article_url (body not stored; inferred at Phase 2).
    Idempotent: ON CONFLICT DO NOTHING via (run_id, symbol, article_url, generated_at).
    """
    if not config.ALPACA_API_KEY or not config.ALPACA_SECRET_KEY:
        log.error("ALPACA_API_KEY / ALPACA_SECRET_KEY not set")
        sys.exit(1)

    inserted = 0
    for symbol in symbols:
        log.info("Phase 1: fetching Alpaca news for %s (%s → %s)", symbol, start.date(), end.date())
        connector = AlpacaNewsConnector(
            api_key=config.ALPACA_API_KEY,
            api_secret=config.ALPACA_SECRET_KEY,
            symbols=[symbol],
        )

        items = asyncio.run(_collect_news(connector, start, end))
        log.info("  %s: %d articles fetched", symbol, len(items))

        with pg_conn.cursor() as cur:
            for item in items:
                cur.execute(_INSERT_PENDING, (
                    run_id, symbol,
                    item.title[:500] if item.title else "",
                    item.url[:1000] if item.url else "",
                    item.timestamp,
                    "alpaca_benzinga",
                ))
                if cur.rowcount == 1:
                    inserted += 1
        pg_conn.commit()

    log.info("Phase 1 complete: %d pending rows inserted", inserted)
    return inserted


def _has_existing_rows(pg_conn, run_id: str) -> int:
    with pg_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM backtest_signals WHERE run_id = %s", (run_id,))
        return cur.fetchone()[0]


def phase2_infer(pg_conn, run_id: str, dry_run: bool, concurrency: int = 5, yes: bool = False) -> int:
    """Phase 2: run LLM inference on pending rows. Skips rows with score IS NOT NULL.

    Checkpoint/resume: SELECT filters score IS NULL; scored rows survive crashes.
    """
    with pg_conn.cursor() as cur:
        cur.execute(_SELECT_PENDING, (run_id,))
        rows = cur.fetchall()

    if not rows:
        log.info("Phase 2: no pending rows for run_id=%s", run_id)
        return 0

    if not dry_run:
        est = _estimate_cost(len(rows))
        print(f"\nEstimated inference cost: ${est:.2f} for {len(rows)} articles × 2 models")
        if est > 10.0 and not yes:
            answer = input("Continue? [y/N] ").strip().lower()
            if answer != "y":
                print("Aborted.")
                sys.exit(0)

    clients = [] if dry_run else [OllamaGlmClient(), OllamaDeepseekClient()]
    aggregator = EnsembleAggregator(
        min_confidence=config.ENSEMBLE_MIN_CONFIDENCE,
        divergence_threshold=config.ENSEMBLE_DIVERGENCE_STD,
    )
    finbert = FinBERTClient()
    budget_tracker = NoOpBudgetTracker()

    total = len(rows)
    processed = 0
    last_checkpoint = 0

    with pg_conn.cursor() as cur, tqdm(total=total, desc="Phase 2: inference") as pbar:
        for batch_start in range(0, total, concurrency):
            batch = rows[batch_start : batch_start + concurrency]

            if dry_run:
                for (row_id, *_) in batch:
                    cur.execute(_DRY_RUN_UPDATE, (row_id,))
                    processed += 1
            else:
                batch_results = asyncio.run(
                    _infer_batch(batch, clients, aggregator, finbert, budget_tracker)
                )
                for item in batch_results:
                    if isinstance(item, BaseException):
                        log.warning("Batch item failed: %s", item)
                        continue
                    row_id, inference_result = item
                    if inference_result is not None:
                        result, _ = inference_result
                        cur.execute(_UPDATE_SCORED, (
                            result.score, result.confidence, result.reasoning,
                            result.model_id, result.ensemble_std, result.fallback_used,
                            row_id,
                        ))
                        processed += 1

            pbar.update(len(batch))
            if processed - last_checkpoint >= 50:
                pg_conn.commit()
                log.info("Phase 2 checkpoint: %d/%d scored", processed, total)
                last_checkpoint = processed

    # Final safety commit — ensures last partial batch is persisted
    pg_conn.commit()
    log.info("Phase 2 complete: %d rows scored", processed)
    return processed


def phase3_forward_returns(pg_conn, run_id: str, start: datetime, end: datetime) -> int:
    """Phase 3: populate forward_return_1h/4h/24h from yfinance."""
    from src.backtest.forward_returns import ForwardReturnCalculator
    log.info("Phase 3: computing forward returns for run_id=%s", run_id)
    try:
        calc = ForwardReturnCalculator(pg_conn)
        updated = calc.populate(run_id, start, end)
        log.info("Phase 3 complete: %d rows updated", updated)
        return updated
    except Exception as exc:
        log.error("Phase 3 failed: %s", exc, exc_info=True)
        raise


def phase4_report_and_gate(pg_conn, run_id: str, candidate_symbols: list[str]) -> None:
    """Phase 4: build IC/ICIR report and print promotion gate results."""
    from src.backtest.report import BacktestReportBuilder

    log.info("Phase 4: building report for run_id=%s", run_id)
    builder = BacktestReportBuilder(pg_conn)
    report = builder.build(run_id)

    print("\n" + "=" * 60)
    print(f"BACKTEST REPORT — {run_id}")
    print("=" * 60)
    if report.period_start and report.period_end:
        print(f"Period: {report.period_start.date()} → {report.period_end.date()}")
    print(f"Total signals:        {report.total_signals}")
    print(f"Signals with returns: {report.signals_with_returns}")

    for horizon, ic, icir in [
        ("1h",  report.ic_1h,  report.icir_1h),
        ("4h",  report.ic_4h,  report.icir_4h),
        ("24h", report.ic_24h, report.icir_24h),
    ]:
        if ic is not None:
            icir_val = f"{icir.icir:.4f}" if icir else "n/a"
            print(f"\nHorizon {horizon}:  IC={ic.composite_ic:.4f}  ICIR={icir_val}  n={ic.sample_count}")
        else:
            print(f"\nHorizon {horizon}: insufficient samples (<30)")

    # Per-symbol breakdown from report.by_symbol
    print("\n" + "-" * 60)
    print(f"{'Symbol':<8}  {'IC_24h':>8}  {'ICIR_24h':>10}  {'n':>5}  PROMOTED")
    print("-" * 60)

    promoted = []
    missing_data = []
    for sym in candidate_symbols:
        sym_data = report.by_symbol.get(sym, {})
        if not sym_data:
            missing_data.append(sym)
        ic_24h = sym_data.get("ic_24h")
        icir_24h = sym_data.get("icir_24h")
        n = sym_data.get("sample_count", 0)

        ic_str = f"{ic_24h:.4f}" if ic_24h is not None else "   n/a"
        icir_str = f"{icir_24h:.4f}" if icir_24h is not None else "     n/a"

        passes = (
            ic_24h is not None and icir_24h is not None
            and ic_24h >= IC_THRESHOLD and icir_24h >= ICIR_THRESHOLD
        )
        label = "YES" if passes else "NO"
        if passes:
            promoted.append(sym)
        print(f"{sym:<8}  {ic_str:>8}  {icir_str:>10}  {n:>5}  {label}")

    if missing_data:
        log.warning("No signal data found for: %s", ", ".join(missing_data))
    print("-" * 60)

    if promoted:
        print(f"\nPromoted symbols (pass both gates): {', '.join(promoted)}")
        print("Next step: run scripts/compare_s4_universes.py with these symbols.")
    else:
        print("\nNo symbols promoted. Recommendation: do not expand universe.")
        print("(IC_24h threshold: >=0.15, ICIR_24h threshold: >=2.0)")

    Path("reports").mkdir(exist_ok=True)
    out_path = Path(f"reports/backtest_{run_id}.json")
    out_path.write_text(json.dumps(report.to_dict(), indent=2, default=str))
    print(f"\nReport saved to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Alpaca IC backtest for small/mid-cap candidates")
    parser.add_argument("--symbols", nargs="+", required=True,
                        help="Candidate symbols to evaluate (e.g. CRDO ALAB GFS ADI)")
    parser.add_argument("--baseline", nargs="+", default=[],
                        help="Baseline watchlist symbols for comparison (e.g. INTC NVDA MU AMD)")
    parser.add_argument("--days", type=int, default=90,
                        help="Number of historical days to fetch (default 90)")
    parser.add_argument("--run-id", required=True,
                        help="Unique run identifier (e.g. alpaca-smallmid-2506)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip LLM inference; write score=0.0 (fast testing)")
    parser.add_argument("--concurrency", type=int, default=5,
                        help="LLM inference batch size (default 5)")
    parser.add_argument("--yes", action="store_true",
                        help="Skip cost confirmation prompt")
    parser.add_argument("--skip-phase1", action="store_true",
                        help="Skip news fetch (reuse existing rows for this run-id)")
    args = parser.parse_args()

    all_symbols = args.symbols + args.baseline
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=args.days)

    pg_conn = psycopg2.connect(config.DATABASE_URL.replace("+asyncpg", ""))
    try:
        existing = _has_existing_rows(pg_conn, args.run_id)
        if args.skip_phase1 or existing > 0:
            log.info("Phase 1: skipped — %d rows already exist for run_id=%s", existing, args.run_id)
        else:
            phase1_fetch(pg_conn, args.run_id, all_symbols, start, end)

        phase2_infer(pg_conn, args.run_id, dry_run=args.dry_run,
                     concurrency=args.concurrency, yes=args.yes)
        phase3_forward_returns(pg_conn, args.run_id, start, end)
        phase4_report_and_gate(pg_conn, args.run_id, candidate_symbols=args.symbols)
    finally:
        pg_conn.close()


if __name__ == "__main__":
    main()
