#!/usr/bin/env python3
"""NewsAPI enrichment backtest runner.

Usage:
    python scripts/run_backtest_newsapi.py \\
        --source-run-id gkg-nov25-v1 \\
        --target-run-id gkg-nov25-newsapi-v1 \\
        --start 2025-11-01 \\
        --end   2025-11-30 \\
        [--dry-run]

Phases:
    0. Fetch NewsAPI articles for each unique ticker in source-run-id → insert into backtest_signals
    2. LLM inference (checkpoint/resume; skips score IS NOT NULL rows)
    3. ForwardReturnCalculator: populate 1h/4h/24h from yfinance
    4. BacktestReportBuilder: compute IC/ICIR, print + save JSON
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone

import psycopg2
from tqdm import tqdm

from src.config import config
from src.connectors.newsapi import (
    NewsAPIAuthError,
    NewsAPIConnector,
    NewsAPIPaidPlanError,
    NewsAPIRateLimitError,
)

# Reuse phases 2-4 unchanged from run_backtest
from scripts.run_backtest import phase2_infer, phase3_forward_returns, phase4_report

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

_INSERT_NEWSAPI = """
    INSERT INTO backtest_signals (run_id, symbol, article_title, article_url, generated_at)
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (run_id, symbol, article_url, generated_at) DO NOTHING
"""


def _get_tickers_with_companies(pg_conn, source_run_id: str) -> list[tuple[str, str]]:
    """Return [(ticker, company_name), ...] for all unique tickers in source run."""
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT bs.symbol, COALESCE(tl.company_name, '') as company_name
            FROM backtest_signals bs
            LEFT JOIN ticker_lookup tl ON tl.ticker = bs.symbol
            WHERE bs.run_id = %s
            ORDER BY bs.symbol
            """,
            (source_run_id,),
        )
        return cur.fetchall()


def phase0_fetch_newsapi(
    pg_conn,
    source_run_id: str,
    target_run_id: str,
    start: datetime,
    end: datetime,
) -> int:
    """Phase 0: fetch NewsAPI articles for each ticker, insert into backtest_signals.

    Skips Phase 0 entirely if target_run_id already has rows (resume support).
    Stops gracefully on rate limit — remaining tickers are skipped but phases 2-4 run.
    """
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM backtest_signals WHERE run_id = %s", (target_run_id,)
        )
        existing = cur.fetchone()[0]

    if existing > 0:
        log.info(
            "Phase 0: skipped — %d rows already exist for run_id=%s", existing, target_run_id
        )
        return existing

    if not config.NEWSAPI_KEY:
        log.error("Phase 0: NEWSAPI_KEY is not set — aborting")
        sys.exit(1)

    tickers = _get_tickers_with_companies(pg_conn, source_run_id)
    log.info(
        "Phase 0: fetching NewsAPI for %d tickers from %s to %s",
        len(tickers),
        start.date(),
        end.date(),
    )

    connector = NewsAPIConnector(api_key=config.NEWSAPI_KEY)
    inserted = 0

    with pg_conn.cursor() as cur:
        for ticker, company_name in tqdm(tickers, desc="Phase 0: NewsAPI fetch"):
            try:
                items = []

                async def _collect(t=ticker, cn=company_name):
                    async for item in connector.fetch_historical(t, cn, start, end):
                        items.append(item)

                asyncio.run(_collect())

                for item in items:
                    cur.execute(
                        _INSERT_NEWSAPI,
                        (target_run_id, ticker, item.body, item.url, item.timestamp),
                    )
                    if cur.rowcount > 0:
                        inserted += 1

            except NewsAPIRateLimitError:
                log.warning(
                    "Phase 0: rate limit reached after %d requests — stopping fetch. "
                    "Remaining tickers skipped. Re-run tomorrow to complete.",
                    connector._requests_made,
                )
                break
            except NewsAPIPaidPlanError as e:
                log.error(
                    "Phase 0: %s\n"
                    "  → The date range %s–%s is older than 1 month.\n"
                    "  → Free plan only allows articles from the past 30 days.\n"
                    "  → To use historical data, upgrade to NewsAPI Developer plan.",
                    e,
                    start.date(),
                    end.date(),
                )
                sys.exit(1)
            except NewsAPIAuthError:
                log.error("Phase 0: invalid NEWSAPI_KEY — check your .env file")
                sys.exit(1)

    pg_conn.commit()
    log.info(
        "Phase 0 complete: %d articles inserted, %d API requests used",
        inserted,
        connector._requests_made,
    )
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="Run NewsAPI enrichment backtest")
    parser.add_argument(
        "--source-run-id",
        required=True,
        help="Existing GDELT run to copy tickers from (e.g. gkg-nov25-v1)",
    )
    parser.add_argument(
        "--target-run-id",
        required=True,
        help="New run ID for NewsAPI results (e.g. gkg-nov25-newsapi-v1)",
    )
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip LLM inference; write score=0.0 for testing",
    )
    args = parser.parse_args()

    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)

    pg_conn = psycopg2.connect(config.DATABASE_URL)
    try:
        phase0_fetch_newsapi(pg_conn, args.source_run_id, args.target_run_id, start, end)
        phase2_infer(pg_conn, args.target_run_id, dry_run=args.dry_run)
        phase3_forward_returns(pg_conn, args.target_run_id, start, end)
        phase4_report(pg_conn, args.target_run_id)
    finally:
        pg_conn.close()


if __name__ == "__main__":
    main()
