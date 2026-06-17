# Small/Mid-Cap Watchlist Evaluation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add DELL and MRVL to the watchlist immediately, then build two scripts to evaluate whether small/mid-cap symbols (CRDO, ALAB, GFS, ADI) deserve watchlist inclusion via IC backtest and S4 portfolio comparison.

**Architecture:** `scripts/backtest_smallmid_ic.py` follows the exact 4-phase structure of the existing `scripts/run_backtest.py` but uses `AlpacaNewsConnector.fetch_historical()` instead of GDELT. `scripts/compare_s4_universes.py` calls the existing `run_s4_backtest_from_prices_and_signals()` twice (restricted vs expanded universe) and prints a recommendation. No new modules — only two new scripts.

**Tech Stack:** psycopg2, alpaca-py, yfinance (forward returns), existing `src/performance/ic.py`, `src/backtest/report.py`, `src/strategies/s4/backtest.py`

---

## Task 0: Add DELL and MRVL to watchlist

**Files:**
- Modify: `config/trading.yaml`

- [ ] **Step 1: Edit trading.yaml**

Add both symbols in the `# --- Semiconductors / AI hardware ---` section, after `TSM` (line 26):

```yaml
    # --- Semiconductors / AI hardware ---
    - AMD
    - AVGO
    - QCOM
    - TXN
    - INTC
    - MU
    - ASML
    - ARM
    - AMAT
    - TSM
    - MRVL
    - DELL
```

- [ ] **Step 2: Verify config loads**

```bash
.venv/bin/python -c "
from src.config import config
wl = config.WATCHLIST_SYMBOLS
assert 'DELL' in wl, 'DELL missing'
assert 'MRVL' in wl, 'MRVL missing'
print(f'Watchlist has {len(wl)} symbols. DELL and MRVL present.')
"
```

Expected output: `Watchlist has N symbols. DELL and MRVL present.`

- [ ] **Step 3: Run existing tests to confirm no regression**

```bash
.venv/bin/python -m pytest tests/test_pg_store.py tests/workers/test_portfolio_scheduler.py -q
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add config/trading.yaml
git commit -m "feat(watchlist): add DELL and MRVL (large-cap AI chip peers)"
```

---

## Task 1: IC Backtest Script — Phase 1 (Alpaca fetch → pending rows)

**Files:**
- Create: `scripts/backtest_smallmid_ic.py`

- [ ] **Step 1: Create script skeleton with CLI and Phase 1 fetch**

Create `scripts/backtest_smallmid_ic.py`:

```python
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
    ON CONFLICT ON CONSTRAINT idx_backtest_signals_dedup DO NOTHING
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

        async def _fetch():
            return [item async for item in connector.fetch_historical(start, end)]

        items = asyncio.run(_fetch())
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
                if cur.rowcount > 0:
                    inserted += 1
        pg_conn.commit()

    log.info("Phase 1 complete: %d pending rows inserted", inserted)
    return inserted


def _has_existing_rows(pg_conn, run_id: str) -> int:
    with pg_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM backtest_signals WHERE run_id = %s", (run_id,))
        return cur.fetchone()[0]


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

    pg_conn = psycopg2.connect(config.DATABASE_URL)
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
```

- [ ] **Step 2: Verify Phase 1 imports load**

```bash
.venv/bin/python -c "import scripts.backtest_smallmid_ic" 2>&1 || \
  .venv/bin/python scripts/backtest_smallmid_ic.py --help
```

Expected: help text printed, no ImportError.

---

## Task 2: IC Backtest Script — Phase 2 (LLM inference)

**Files:**
- Modify: `scripts/backtest_smallmid_ic.py` — add `phase2_infer` and helper functions

- [ ] **Step 1: Add inference helper and Phase 2 to script**

Add the following functions to `scripts/backtest_smallmid_ic.py` after `_has_existing_rows` and before `main`:

```python
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
    """Estimate cost: 2 models × ~300 input + ~100 output tokens × cloud rates."""
    cost_per_call = (300 * 2.0 + 100 * 6.0) / 1_000_000
    return pending_count * 2 * cost_per_call


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
            if processed - last_checkpoint >= 50 or batch_start + len(batch) >= total:
                pg_conn.commit()
                log.info("Phase 2 checkpoint: %d/%d scored", processed, total)
                last_checkpoint = processed

    log.info("Phase 2 complete: %d rows scored", processed)
    return processed
```

- [ ] **Step 2: Smoke-test dry-run Phase 2 (with pre-seeded row)**

```bash
# Insert one test row manually and verify dry-run scores it
docker exec alembic-postgres-1 psql -U trading -d trading -c "
  INSERT INTO backtest_signals (run_id, symbol, article_title, article_url, generated_at, news_source)
  VALUES ('test-dryrun-001', 'CRDO', 'Test article', 'http://test.example/1',
          NOW() - INTERVAL '1 day', 'alpaca_benzinga')
  ON CONFLICT ON CONSTRAINT idx_backtest_signals_dedup DO NOTHING;"

.venv/bin/python scripts/backtest_smallmid_ic.py \
  --symbols CRDO --baseline INTC \
  --days 2 --run-id test-dryrun-001 \
  --dry-run --yes --skip-phase1

docker exec alembic-postgres-1 psql -U trading -d trading -c "
  SELECT symbol, score, model_id FROM backtest_signals WHERE run_id = 'test-dryrun-001';"
```

Expected: `CRDO | 0.0 | dry_run`

```bash
# Clean up
docker exec alembic-postgres-1 psql -U trading -d trading -c \
  "DELETE FROM backtest_signals WHERE run_id = 'test-dryrun-001';"
```

---

## Task 3: IC Backtest Script — Phase 3 and 4 (returns + report + gate)

**Files:**
- Modify: `scripts/backtest_smallmid_ic.py` — add `phase3_forward_returns`, `phase4_report_and_gate`

- [ ] **Step 1: Add Phase 3 forward returns to script**

Add after `phase2_infer` in `scripts/backtest_smallmid_ic.py`:

```python
def phase3_forward_returns(pg_conn, run_id: str, start: datetime, end: datetime) -> int:
    """Phase 3: populate forward_return_1h/4h/24h from yfinance."""
    from src.backtest.forward_returns import ForwardReturnCalculator
    log.info("Phase 3: computing forward returns for run_id=%s", run_id)
    calc = ForwardReturnCalculator(pg_conn)
    updated = calc.populate(run_id, start, end)
    log.info("Phase 3 complete: %d rows updated", updated)
    return updated
```

- [ ] **Step 2: Add Phase 4 report and gate check to script**

Add after `phase3_forward_returns`:

```python
def phase4_report_and_gate(pg_conn, run_id: str, candidate_symbols: list[str]) -> None:
    """Phase 4: build IC/ICIR report and print promotion gate results.

    Builds the standard BacktestReportBuilder report (IC at 1h/4h/24h),
    then prints a per-symbol gate table for candidate symbols:
      PROMOTED if IC_24h >= IC_THRESHOLD AND ICIR_24h >= ICIR_THRESHOLD.
    """
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
    for sym in candidate_symbols:
        sym_data = report.by_symbol.get(sym, {})
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

    print("-" * 60)

    if promoted:
        print(f"\nPromoted symbols (pass both gates): {', '.join(promoted)}")
        print("Next step: run scripts/compare_s4_universes.py with these symbols.")
    else:
        print("\nNo symbols promoted. Recommendation: do not expand universe.")
        print("(IC_24h threshold: >=0.15, ICIR_24h threshold: >=2.0)")

    Path("reports").mkdir(exist_ok=True)
    out_path = Path(f"reports/backtest_{run_id}.json")
    out_path.write_text(json.dumps(report.to_dict(), indent=2))
    print(f"\nReport saved to {out_path}")
```

- [ ] **Step 3: Run full dry-run end-to-end with real Phase 1**

```bash
.venv/bin/python scripts/backtest_smallmid_ic.py \
  --symbols CRDO ALAB GFS ADI \
  --baseline INTC NVDA MU AMD \
  --days 7 \
  --run-id alpaca-smallmid-dryrun \
  --dry-run --yes
```

Expected output:
- Phase 1 inserts some rows (Alpaca news fetched for 8 symbols)
- Phase 2 scores all rows with `score=0.0, model_id=dry_run`
- Phase 3 populates forward returns from yfinance
- Phase 4 prints report + gate table (all NO for dry-run since scores are 0.0)
- `reports/backtest_alpaca-smallmid-dryrun.json` created

```bash
# Clean up dry-run data
docker exec alembic-postgres-1 psql -U trading -d trading -c \
  "DELETE FROM backtest_signals WHERE run_id = 'alpaca-smallmid-dryrun';"
rm -f reports/backtest_alpaca-smallmid-dryrun.json
```

- [ ] **Step 4: Commit**

```bash
git add scripts/backtest_smallmid_ic.py
git commit -m "feat(scripts): add Alpaca IC backtest script for small/mid-cap evaluation"
```

---

## Task 4: Portfolio Comparison Script

**Files:**
- Create: `scripts/compare_s4_universes.py`

- [ ] **Step 1: Create the portfolio comparison script**

Create `scripts/compare_s4_universes.py`:

```python
#!/usr/bin/env python3
"""S4 universe comparison: watchlist-only vs watchlist + promoted symbols.

Usage:
    python scripts/compare_s4_universes.py \\
      --promoted CRDO ALAB \\
      --run-id alpaca-smallmid-2506 \\
      --days 90

Loads signals from backtest_signals for the given run_id.
Runs run_s4_backtest_from_prices_and_signals() twice:
  - Universe A: current watchlist only
  - Universe B: watchlist + promoted symbols
Prints comparison and writes reports/s4_universe_comparison.json.

NOTE: With only 90 days of signals, uses in_sample_days=45 / out_of_sample_days=45.
Results are directional, not statistically conclusive.
"""

import argparse
import json
import logging
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _fetch_prices(symbols: list[str], days: int) -> pd.DataFrame:
    """Fetch daily close prices from Alpaca for the last N days."""
    from datetime import datetime, timezone
    from alpaca.data.enums import DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from src.config import config

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days * 2)  # extra buffer for weekends/holidays

    client = StockHistoricalDataClient(
        api_key=config.ALPACA_API_KEY,
        secret_key=config.ALPACA_SECRET_KEY,
    )
    request = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
        feed=DataFeed.IEX,
    )
    raw = client.get_stock_bars(request).df
    if raw.empty:
        return pd.DataFrame()
    raw = raw.reset_index()
    prices = raw.pivot(index="timestamp", columns="symbol", values="close")
    # Keep only last `days` trading days
    if len(prices) > days:
        prices = prices.iloc[-days:]
    return prices


def _load_signals_from_db(run_id_pattern: str) -> pd.DataFrame:
    """Load signals from backtest_signals for run_ids matching the pattern."""
    import psycopg2
    from src.config import config

    conn = psycopg2.connect(config.DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT symbol, score, confidence, 'unknown' AS reasoning,
                       model_id, 0.0 AS ensemble_std, fallback_used, generated_at
                FROM backtest_signals
                WHERE run_id LIKE %s
                  AND score IS NOT NULL
                ORDER BY generated_at
            """, (run_id_pattern + "%",))
            rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=[
        "symbol", "score", "confidence", "reasoning",
        "model_id", "ensemble_std", "fallback_used", "generated_at",
    ])
    df["generated_at"] = pd.to_datetime(df["generated_at"])
    if df["generated_at"].dt.tz is not None:
        df["generated_at"] = df["generated_at"].dt.tz_localize(None)
    return df


def _run_comparison(
    prices_a: pd.DataFrame,
    prices_b: pd.DataFrame,
    signals_a: pd.DataFrame,
    signals_b: pd.DataFrame,
    label_a: str,
    label_b: str,
) -> dict:
    """Run backtest for both universes and return comparison dict."""
    from src.backtest.walkforward.runner import WalkForwardConfig
    from src.strategies.s4.backtest import run_s4_backtest_from_prices_and_signals

    # Short window config for 90-day signal window
    wf_cfg = WalkForwardConfig(in_sample_days=45, out_of_sample_days=45)

    log.info("Running backtest for %s (%d symbols, %d signals)...",
             label_a, len(prices_a.columns), len(signals_a))
    result_a = run_s4_backtest_from_prices_and_signals(
        prices=prices_a,
        signals_df=signals_a,
        output_dir=Path(f"reports/s4_{label_a.lower().replace(' ', '_')}"),
        wf_config=wf_cfg,
        run_robustness=False,
    )

    log.info("Running backtest for %s (%d symbols, %d signals)...",
             label_b, len(prices_b.columns), len(signals_b))
    result_b = run_s4_backtest_from_prices_and_signals(
        prices=prices_b,
        signals_df=signals_b,
        output_dir=Path(f"reports/s4_{label_b.lower().replace(' ', '_')}"),
        wf_config=wf_cfg,
        run_robustness=False,
    )

    return {"a": result_a, "b": result_b, "label_a": label_a, "label_b": label_b}


def _print_comparison(comp: dict, promoted: list[str]) -> None:
    """Print side-by-side comparison and recommendation."""
    a, b = comp["a"], comp["b"]
    la, lb = comp["label_a"], comp["label_b"]

    sharpe_a = a.get("oos_sharpe", 0.0)
    sharpe_b = b.get("oos_sharpe", 0.0)

    print("\n" + "=" * 60)
    print("S4 UNIVERSE COMPARISON")
    print("=" * 60)
    print(f"{'Metric':<25} {la:>15} {lb:>15}")
    print("-" * 60)
    print(f"{'OOS Sharpe':<25} {sharpe_a:>15.4f} {sharpe_b:>15.4f}")

    gates_a = a.get("all_gates_pass", False)
    gates_b = b.get("all_gates_pass", False)
    print(f"{'All gates pass':<25} {str(gates_a):>15} {str(gates_b):>15}")
    print("-" * 60)

    print("\n⚠️  NOTE: 90-day signal window — results are directional only.")
    print("    in_sample_days=45, out_of_sample_days=45 (not production config)\n")

    sharpe_improved = sharpe_b > sharpe_a
    label = "YES" if sharpe_improved else "NO"

    print(f"OOS Sharpe B > A: {label}  ({sharpe_b:.4f} vs {sharpe_a:.4f})")

    if sharpe_improved:
        print(f"\nRECOMMENDATION: add {', '.join(promoted)} to watchlist")
        print("  IC_24h >= 0.15         (verified in IC backtest)")
        print("  ICIR_24h >= 2.0        (verified in IC backtest)")
        print(f"  OOS Sharpe B > A       ({sharpe_b:.4f} vs {sharpe_a:.4f})")
        print("\nACTION REQUIRED: manually add symbols to config/trading.yaml")
    else:
        print("\nRECOMMENDATION: do NOT add symbols — Sharpe did not improve.")
        print(f"  OOS Sharpe B ({sharpe_b:.4f}) <= Sharpe A ({sharpe_a:.4f})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare S4 performance with/without promoted symbols")
    parser.add_argument("--promoted", nargs="+", required=True,
                        help="Promoted symbols from IC backtest gate (e.g. CRDO ALAB)")
    parser.add_argument("--run-id", required=True,
                        help="Run ID prefix used in backtest_smallmid_ic.py (e.g. alpaca-smallmid-2506)")
    parser.add_argument("--days", type=int, default=90,
                        help="Price history window in days (must match IC backtest, default 90)")
    args = parser.parse_args()

    from src.config import config

    watchlist = list(config.WATCHLIST_SYMBOLS or [])
    promoted = args.promoted
    expanded = list(dict.fromkeys(watchlist + promoted))  # dedup, preserve order

    log.info("Fetching prices for Universe A (%d symbols)...", len(watchlist))
    prices_a = _fetch_prices(watchlist, args.days)

    log.info("Fetching prices for Universe B (%d symbols)...", len(expanded))
    prices_b = _fetch_prices(expanded, args.days)

    if prices_a.empty or prices_b.empty:
        log.error("No price data returned — check Alpaca credentials and symbols")
        raise SystemExit(1)

    log.info("Loading signals from DB (run_id prefix: %s)...", args.run_id)
    all_signals = _load_signals_from_db(args.run_id)
    if all_signals.empty:
        log.error("No signals found for run_id prefix '%s' — run IC backtest first", args.run_id)
        raise SystemExit(1)

    signals_a = all_signals[all_signals["symbol"].isin(prices_a.columns)]
    signals_b = all_signals[all_signals["symbol"].isin(prices_b.columns)]

    log.info("Universe A: %d symbols, %d signals", len(prices_a.columns), len(signals_a))
    log.info("Universe B: %d symbols, %d signals", len(prices_b.columns), len(signals_b))

    comp = _run_comparison(
        prices_a=prices_a, prices_b=prices_b,
        signals_a=signals_a, signals_b=signals_b,
        label_a="Universe A (watchlist)",
        label_b="Universe B (watchlist+promoted)",
    )

    _print_comparison(comp, promoted)

    Path("reports").mkdir(exist_ok=True)
    out = {
        "promoted_symbols": promoted,
        "run_id": args.run_id,
        "universe_a": {"symbols": len(prices_a.columns), **comp["a"]},
        "universe_b": {"symbols": len(prices_b.columns), **comp["b"]},
    }
    out_path = Path("reports/s4_universe_comparison.json")
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nFull comparison saved to {out_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify script loads**

```bash
.venv/bin/python scripts/compare_s4_universes.py --help
```

Expected: help text printed, no ImportError.

- [ ] **Step 3: Commit**

```bash
git add scripts/compare_s4_universes.py
git commit -m "feat(scripts): add S4 universe comparison script for small/mid-cap promotion gate"
```

---

## Task 5: Run the Real IC Backtest

*Prerequisites: Alpaca API key configured, LLM clients reachable (or use --dry-run for smoke test).*

- [ ] **Step 1: Run real 90-day IC backtest**

```bash
.venv/bin/python scripts/backtest_smallmid_ic.py \
  --symbols CRDO ALAB GFS ADI \
  --baseline INTC NVDA MU AMD \
  --days 90 \
  --run-id alpaca-smallmid-2506 \
  --concurrency 5
```

Expected: Phase 1 inserts hundreds of rows, Phase 2 runs LLM inference (cost prompt appears), Phase 3 populates forward returns, Phase 4 prints gate table.

- [ ] **Step 2: Note promoted symbols from output**

Record which symbols printed `YES` in the gate table. If none: process stops. If ≥1: proceed to Task 6.

- [ ] **Step 3: Commit report**

```bash
git add reports/backtest_alpaca-smallmid-2506.json
git commit -m "data: IC backtest results for small/mid-cap candidates (alpaca-smallmid-2506)"
```

---

## Task 6: Run Portfolio Comparison (only if ≥1 symbol promoted)

*Prerequisites: Task 5 complete, at least one symbol passed the gate.*

- [ ] **Step 1: Run S4 universe comparison**

Replace `CRDO ALAB` with whichever symbols were promoted in Task 5:

```bash
.venv/bin/python scripts/compare_s4_universes.py \
  --promoted CRDO ALAB \
  --run-id alpaca-smallmid-2506 \
  --days 90
```

Expected: prints side-by-side OOS Sharpe comparison and final RECOMMENDATION.

- [ ] **Step 2: Act on recommendation**

If RECOMMENDATION says add symbols: manually edit `config/trading.yaml` to add them to the watchlist. Follow the same pattern as Task 0 (semiconductors section or a new `# --- Small/Mid-Cap AI ---` subsection).

If RECOMMENDATION says do not add: no changes needed.

- [ ] **Step 3: Commit results**

```bash
git add reports/s4_universe_comparison.json
# If symbols were added:
git add config/trading.yaml
git commit -m "data: S4 universe comparison — small/mid-cap promotion decision"
```

---

## Self-Review Checklist

- [x] **Spec coverage:**
  - Step 0 (DELL/MRVL) → Task 0 ✓
  - Step 1 (IC backtest) → Tasks 1–3 ✓
  - Step 2 (gate) → Task 3 Phase 4 ✓
  - Step 3 (portfolio comparison) → Task 4 ✓
  - Step 4 (recommendation output) → Task 4 `_print_comparison` ✓

- [x] **No placeholders:** All code blocks contain complete implementations.

- [x] **Type consistency:**
  - `phase1_fetch`, `phase2_infer`, `phase3_forward_returns`, `phase4_report_and_gate` all receive `pg_conn, run_id` as first two args — consistent.
  - `_INSERT_PENDING` / `_SELECT_PENDING` / `_UPDATE_SCORED` / `_DRY_RUN_UPDATE` constants defined in Task 1 and used in Tasks 2–3 — all present.
  - `BacktestReportBuilder(pg_conn).build(run_id)` — matches `src/backtest/report.py` API (verified).
  - `ForwardReturnCalculator(pg_conn).populate(run_id, start, end)` — matches `src/backtest/forward_returns.py` API (verified).
  - `run_s4_backtest_from_prices_and_signals(prices, signals_df, output_dir, wf_config, run_robustness)` — matches `src/strategies/s4/backtest.py` signature (verified).
  - `WalkForwardConfig(in_sample_days=45, out_of_sample_days=45)` — field names verified against `src/backtest/walkforward/runner.py`.
