# Backtest Inference Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Speed up `run_backtest.py` Phase 2 from ~16h to ~23min by processing articles in parallel batches and halving LLM calls (4 models → Kimi + Qwen3.5).

**Architecture:** Add module-level `_infer_batch` async coroutine that runs N articles concurrently via `asyncio.gather`. `phase2_infer` iterates over batches of size `concurrency` (default 5), calls `asyncio.run(_infer_batch(...))` once per batch, then writes results to DB synchronously. DB writes never overlap (psycopg2 safety preserved).

**Tech Stack:** Python asyncio, psycopg2, existing `run_inference` from `src/workers/sentiment.py`, OllamaKimiClient + OllamaQwen35Client from `src/llm/client.py`.

---

### Task 1: Reduce ensemble to 2 models and update cost estimate

**Files:**
- Modify: `scripts/run_backtest.py`
- Test: `tests/backtest/test_backtest_runner.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/backtest/test_backtest_runner.py`:

```python
def test_estimate_cost_uses_two_models():
    """_estimate_cost must reflect 2-model ensemble (not 4)."""
    # 1 article × 2 models × cost_per_call = cost_per_call × 2
    # cost_per_call = (300 * 2.0 + 100 * 6.0) / 1_000_000 = 0.0012 / 1000 = 0.0000012 * ... 
    # = (600 + 600) / 1_000_000 = 0.0000012... let's just verify ratio
    cost_1 = _estimate_cost(1)
    cost_2 = _estimate_cost(2)
    assert cost_2 == pytest.approx(cost_1 * 2)
    # 2 models: cost_per_call * 2 * n
    cost_per_call = (300 * 2.0 + 100 * 6.0) / 1_000_000
    assert cost_1 == pytest.approx(2 * cost_per_call)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/stefano/Documents/Projects/Alembic
PYTHONPATH=. pytest tests/backtest/test_backtest_runner.py::test_estimate_cost_uses_two_models -v
```

Expected: FAIL — current code multiplies by 4, not 2.

- [ ] **Step 3: Edit `scripts/run_backtest.py`**

Change the import line (line 36):

```python
from src.llm.client import OllamaKimiClient, OllamaQwen35Client
```

Change `_estimate_cost` docstring and multiplier (lines 73–83):

```python
def _estimate_cost(pending_count: int) -> float:
    """Estimate inference cost: 2 models × ~300 input + ~100 output tokens × cloud rates.

    Uses conservative cloud model pricing ($2/1M input, $6/1M output).
    Prompts a human confirmation if estimate > $10.
    """
    cost_per_call = (300 * 2.0 + 100 * 6.0) / 1_000_000
    return pending_count * 2 * cost_per_call
```

Change the cost display string in `phase2_infer` (line 161):

```python
        print(f"\nEstimated inference cost: ${est:.2f} for {len(rows)} articles × 2 models")
```

Change the clients line in `phase2_infer` (line 168):

```python
    clients = [] if dry_run else [OllamaKimiClient(), OllamaQwen35Client()]
```

- [ ] **Step 4: Run tests**

```bash
PYTHONPATH=. pytest tests/backtest/test_backtest_runner.py -v
```

Expected: all 4 tests PASS (including the new one and the existing 3).

- [ ] **Step 5: Commit**

```bash
git add scripts/run_backtest.py tests/backtest/test_backtest_runner.py
git commit -m "perf(backtest): reduce ensemble to 2 models (kimi + qwen3.5)"
```

---

### Task 2: Add `_infer_batch` async helper and `--concurrency` argument

**Files:**
- Modify: `scripts/run_backtest.py`
- Test: `tests/backtest/test_backtest_runner.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/backtest/test_backtest_runner.py` (add import at top: `from scripts.run_backtest import _infer_batch`):

```python
@pytest.mark.asyncio
async def test_infer_batch_returns_result_per_row():
    """_infer_batch returns one (row_id, result) tuple per input row."""
    from datetime import datetime, timezone
    from scripts.run_backtest import _infer_batch
    from unittest.mock import AsyncMock, MagicMock

    rows = [
        (42, "AAPL", datetime(2025, 12, 1, tzinfo=timezone.utc), "https://x.com/1", "Apple profit up"),
        (43, "MSFT", datetime(2025, 12, 1, tzinfo=timezone.utc), "https://x.com/2", "Microsoft beats"),
    ]

    mock_result = MagicMock()
    mock_result.score = 0.5
    mock_result.confidence = 0.8
    mock_result.reasoning = "bullish"
    mock_result.model_id = "ensemble:kimi+qwen"
    mock_result.ensemble_std = 0.05
    mock_result.fallback_used = False

    mock_run_inference = AsyncMock(return_value=(mock_result, []))

    with patch("scripts.run_backtest.run_inference", mock_run_inference):
        results = await _infer_batch(rows, clients=[], aggregator=MagicMock(),
                                     finbert=MagicMock(), budget_tracker=MagicMock())

    assert len(results) == 2
    assert results[0] == (42, (mock_result, []))
    assert results[1] == (43, (mock_result, []))
```

Add the `patch` import to the existing imports at the top of the test file:
```python
from unittest.mock import AsyncMock, MagicMock, call, patch
```

- [ ] **Step 2: Run test to verify it fails**

```bash
PYTHONPATH=. pytest tests/backtest/test_backtest_runner.py::test_infer_batch_returns_result_per_row -v
```

Expected: FAIL — `_infer_batch` not yet defined.

- [ ] **Step 3: Add `_infer_batch` to `scripts/run_backtest.py`**

Insert after the `_DRY_RUN_UPDATE` constant (after line 70), before `_estimate_cost`:

```python
async def _infer_batch(
    rows: list[tuple],
    clients: list,
    aggregator: EnsembleAggregator,
    finbert: "FinBERTClient",
    budget_tracker,
) -> list:
    """Run inference on a batch of DB rows in parallel.

    Each row is a tuple (row_id, symbol, generated_at, article_url, article_title).
    Returns list where each element is either (row_id, inference_result) or a
    BaseException (if that row's inference raised). Callers must check isinstance(item, BaseException).
    """
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
PYTHONPATH=. pytest tests/backtest/test_backtest_runner.py::test_infer_batch_returns_result_per_row -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_backtest.py tests/backtest/test_backtest_runner.py
git commit -m "feat(backtest): add _infer_batch for concurrent article inference"
```

---

### Task 3: Refactor `phase2_infer` to use batch parallelism

**Files:**
- Modify: `scripts/run_backtest.py`
- Test: `tests/backtest/test_backtest_runner.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/backtest/test_backtest_runner.py`:

```python
def test_phase2_infer_concurrency_param_accepted():
    """phase2_infer accepts a concurrency parameter without error."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=None)
    mock_cur.fetchall.return_value = []

    # Should not raise TypeError
    result = phase2_infer(mock_conn, run_id="test", dry_run=True, concurrency=3)
    assert result == 0


def test_phase2_infer_dry_run_batch_processes_all_rows():
    """dry_run with concurrency=2 still processes all rows."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=None)

    pending_rows = [
        (i, "AAPL", datetime(2025, 12, 1, tzinfo=timezone.utc), f"https://x.com/{i}", f"title {i}")
        for i in range(1, 6)  # 5 rows
    ]
    mock_cur.fetchall.return_value = pending_rows

    processed = phase2_infer(mock_conn, run_id="test", dry_run=True, concurrency=2)

    assert processed == 5
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=. pytest tests/backtest/test_backtest_runner.py::test_phase2_infer_concurrency_param_accepted tests/backtest/test_backtest_runner.py::test_phase2_infer_dry_run_batch_processes_all_rows -v
```

Expected: FAIL — `phase2_infer` does not accept `concurrency` yet.

- [ ] **Step 3: Rewrite `phase2_infer` in `scripts/run_backtest.py`**

Replace the entire `phase2_infer` function (lines 130–217) with:

```python
def phase2_infer(pg_conn, run_id: str, dry_run: bool, concurrency: int = 5) -> int:
    """Phase 2: run LLM inference on pending rows. Skips rows with score IS NOT NULL.

    Checkpoint / resume: SELECT filters `score IS NULL`; scored rows survive crashes.
    Dry-run: writes score=0.0 without any LLM call.
    Batch parallelism: articles are processed in batches of `concurrency` via asyncio.gather.
      DB writes remain synchronous (psycopg2 safety).
    Cost guardrail: prompts confirmation if estimated cost > $10.
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
        if est > 10.0:
            answer = input("Continue? [y/N] ").strip().lower()
            if answer != "y":
                print("Aborted.")
                sys.exit(0)

    clients = [] if dry_run else [OllamaKimiClient(), OllamaQwen35Client()]
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

            # Commit and checkpoint every ~50 rows.
            if processed - last_checkpoint >= 50 or batch_start + len(batch) >= total:
                pg_conn.commit()
                log.info("Phase 2 checkpoint: %d/%d scored", processed, total)
                last_checkpoint = processed

    pg_conn.commit()
    log.info("Phase 2 complete: %d rows scored", processed)
    return processed
```

- [ ] **Step 4: Run all backtest runner tests**

```bash
PYTHONPATH=. pytest tests/backtest/test_backtest_runner.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_backtest.py tests/backtest/test_backtest_runner.py
git commit -m "perf(backtest): parallel batch inference with configurable concurrency"
```

---

### Task 4: Add `--concurrency` CLI argument to `main`

**Files:**
- Modify: `scripts/run_backtest.py`

- [ ] **Step 1: Add argument and wire it through in `main`**

In the `main` function, after the `--phase1-only` argument (line 296), add:

```python
    parser.add_argument("--concurrency", type=int, default=5,
                        help="Number of articles to infer in parallel (default 5)")
```

Change the `phase2_infer` call in `main` (currently `phase2_infer(pg_conn, args.run_id, dry_run=args.dry_run)`) to:

```python
        phase2_infer(pg_conn, args.run_id, dry_run=args.dry_run, concurrency=args.concurrency)
```

Also update the module docstring at the top of the file to document the new flag:

```python
"""Historical GKG backtest runner.

Usage:
    python scripts/run_backtest.py \\
        --start 2025-10-01 \\
        --end   2026-04-30 \\
        --run-id gkg-6m-v1 \\
        [--dry-run] \\
        [--max-per-chunk 250] \\
        [--concurrency 5]

Phases:
    1. Fetch GKG historical news → TickerExtractor → write pending rows
    2. LLM inference (checkpoint/resume; skips score IS NOT NULL rows)
       Runs articles in parallel batches (--concurrency, default 5).
    3. ForwardReturnCalculator: populate 1h/4h/24h from yfinance
    4. BacktestReportBuilder: compute IC/ICIR, print + save JSON
"""
```

- [ ] **Step 2: Run full test suite**

```bash
PYTHONPATH=. pytest tests/backtest/ -v
```

Expected: all tests PASS.

- [ ] **Step 3: Smoke test — dry run**

```bash
set -a && source .env && set +a
PYTHONPATH=. python scripts/run_backtest.py \
    --start 2025-12-01 \
    --end   2025-12-31 \
    --run-id gkg-dec25-v1 \
    --dry-run \
    --concurrency 5
```

Expected: prints "Phase 2: no pending rows" (all rows already scored from previous runs) and completes immediately. If there are pending dry-run rows, they are scored quickly.

- [ ] **Step 4: Commit**

```bash
git add scripts/run_backtest.py
git commit -m "feat(backtest): add --concurrency CLI flag to phase2_infer"
```

---

### Task 5: Launch the actual backtest

- [ ] **Step 1: Launch with optimized settings**

```bash
cd /home/stefano/Documents/Projects/Alembic
set -a && source .env && set +a
LOG="logs/backtest_$(date +%Y%m%d_%H%M%S).log"
nohup PYTHONPATH=. python scripts/run_backtest.py \
    --start 2025-12-01 \
    --end   2025-12-31 \
    --run-id gkg-dec25-v1 \
    --concurrency 5 \
    > "$LOG" 2>&1 &
echo "PID: $!  LOG: $LOG"
tail -f "$LOG"
```

Expected: Phase 1 skipped (1937 rows exist), Phase 2 starts processing batches of 5. Progress bar should show significantly faster throughput than before.

- [ ] **Step 2: If Ollama cloud throttles, reduce concurrency**

If you see repeated timeout errors or HTTP 429 in the log, kill the process and relaunch with `--concurrency 3`:

```bash
kill <PID>
LOG="logs/backtest_$(date +%Y%m%d_%H%M%S).log"
nohup PYTHONPATH=. python scripts/run_backtest.py \
    --start 2025-12-01 \
    --end   2025-12-31 \
    --run-id gkg-dec25-v1 \
    --concurrency 3 \
    > "$LOG" 2>&1 &
echo "PID: $!  LOG: $LOG"
tail -f "$LOG"
```

The checkpoint/resume mechanism ensures no work is lost — already-scored rows are skipped automatically.
