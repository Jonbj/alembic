# GKG Historical Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate that the news-driven LLM ensemble pipeline (GDELTGKGConnector → TickerExtractor → SentimentWorker) produces signals with IC > 0 by running a 6-month historical backtest and computing forward returns at 1h, 4h, and 24h horizons.

**Architecture:** Offline four-phase CLI pipeline — fetch historical GKG news, run full LLM ensemble inference (with budget gate and checkpoint/resume), populate forward returns from yfinance, build IC/ICIR report. Backtest signals are stored in a dedicated `backtest_signals` PostgreSQL table (separate from `sentiment_signals`) to avoid polluting live data and to support multiple backtest runs via `run_id`.

**Tech Stack:** Python asyncio, aiohttp (GDELT GKG), psycopg2 (PostgreSQL), yfinance (price data), argparse (CLI), existing `compute_composite_ic`/`compute_icir` pure functions from `src/performance/ic.py`.

---

## 1. Context

The Fase 3 multi-asset news-driven pipeline is implemented and all 464 tests pass, but no historical validation has been run. The system has never been deployed live. Before deployment, we need evidence that GKG-sourced signals produce positive IC at at least one forward-return horizon.

**Why full LLM ensemble (not FinBERT only):** The backtest must validate exactly the system that will run in production — Opus + Qwen3.5 + DeepSeek. FinBERT-only would be a different signal.

**Why 6 months:** The PerformanceWorker requires `_MIN_SAMPLES = 300` for meaningful IC. 6 months of market-hours news (Mon–Fri 14:00–21:00 UTC) reliably exceeds this threshold across multiple tickers.

**Why three horizons (1h, 4h, 24h):** yfinance cost is zero. The 4h horizon validates `intraday_strategy.py` directly. The 24h horizon produces daily IC comparable to future live PerformanceWorker reports. The comparison across horizons reveals the signal's decay profile.

---

## 2. Data Model

### `backtest_signals` table

```sql
CREATE TABLE backtest_signals (
    id                   SERIAL PRIMARY KEY,
    run_id               TEXT NOT NULL,
    symbol               TEXT NOT NULL,
    score                DOUBLE PRECISION,        -- NULL until LLM inference completes
    confidence           DOUBLE PRECISION,
    reasoning            TEXT,
    model_id             TEXT,
    ensemble_std         DOUBLE PRECISION,
    fallback_used        BOOLEAN NOT NULL DEFAULT FALSE,
    generated_at         TIMESTAMPTZ NOT NULL,
    article_url          TEXT NOT NULL,
    forward_return_1h    DOUBLE PRECISION,        -- NULL until forward returns populated
    forward_return_4h    DOUBLE PRECISION,
    forward_return_24h   DOUBLE PRECISION
);

CREATE INDEX ON backtest_signals (run_id, symbol, generated_at);
CREATE INDEX ON backtest_signals (run_id, score) WHERE score IS NOT NULL;
```

No `UNIQUE(symbol, generated_at)` — multiple runs on the same period are explicitly allowed. The `run_id` is the logical key for isolating results.

`score IS NULL` marks pending rows (Phase 1 written, Phase 2 not yet run). The checkpoint logic in Phase 2 skips rows where `score IS NOT NULL`.

---

## 3. Component Design

### 3.1 `GDELTGKGConnector.fetch_historical()`

New method added to the existing `GDELTGKGConnector` class in `src/connectors/gdelt_gkg.py`. Follows the identical chunking pattern as `GDELTConnector.fetch_historical()`.

```python
async def fetch_historical(
    self,
    start_date: datetime,
    end_date: datetime,
    max_records_per_chunk: int = 250,
) -> AsyncIterator[GKGNewsItem]:
    """Fetch GKG records in [start_date, end_date] chunked by calendar month.

    One API call per month. Inherits exponential backoff from _GDELTBaseConnector.
    Sleeps 1s between chunks to respect GDELT rate limits.
    Records with missing URL or invalid timestamp are skipped (same as fetch()).
    """
    current = start_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    async with aiohttp.ClientSession() as session:
        while current <= end_date:
            # compute next_month and chunk_end (same logic as GDELTConnector)
            params = {
                "query": _GDELT_GKG_QUERY,
                "mode": "gkg",
                "maxrecords": max_records_per_chunk,
                "format": "json",
                "STARTDATETIME": current.strftime("%Y%m%d%H%M%S"),
                "ENDDATETIME": chunk_end.strftime("%Y%m%d%H%M%S"),
            }
            data = await self._fetch_with_backoff(session, params, url=_GDELT_GKG_URL)
            for record in (data or {}).get("gkg", []):
                item = self._parse_record(record)
                if item is not None:
                    yield item
            current = next_month
            await asyncio.sleep(1.0)
```

6 months = 6 API calls (+ retries on 429). `_parse_record()` is unchanged.

### 3.2 `ForwardReturnCalculator` (`src/backtest/forward_returns.py`)

Downloads hourly OHLCV data from yfinance once per ticker for the entire backtest period, then computes the three forward returns for every signal row in `backtest_signals`.

**Price fetch:**
```python
# One yfinance call per ticker; period expanded by ±2 days for edge signals
df = yf.download(ticker, start=start - timedelta(days=1),
                 end=end + timedelta(days=2),
                 interval="1h", auto_adjust=True)
hourly_prices[ticker] = df["Close"]

# Daily close for 24h horizon
df_daily = yf.download(ticker, start=..., end=..., interval="1d", auto_adjust=True)
daily_close[ticker] = df_daily["Close"]
```

**Return calculation per signal at timestamp `T`, ticker `X`:**
1. Find the next available hourly bar at or after `T` in `hourly_prices[X]` → `price_t`
2. `return_1h`: bar at `t_bar + 1h`. If bar missing (post-market, holiday): `None`.
3. `return_4h`: bar at `t_bar + 4h`. If missing: `None`.
4. `return_24h`: `(daily_close[day+1] - daily_close[day]) / daily_close[day]` where `day` is the trading day of `T`. If next close missing: `None`.

No interpolation. `None` rows are excluded from IC calculation, not imputed. This prevents look-ahead bias.

**DB update:**
```python
UPDATE backtest_signals
SET forward_return_1h = %s, forward_return_4h = %s, forward_return_24h = %s
WHERE id = %s
```

### 3.3 `BacktestReportBuilder` (`src/backtest/report.py`)

Fetches all rows for a `run_id` from `backtest_signals` and calls the existing pure functions.

```python
@dataclass
class BacktestReport:
    run_id: str
    period_start: datetime
    period_end: datetime
    total_signals: int
    signals_with_returns: int      # after discarding None
    ic_1h:   ICResult | None       # None if < 30 samples
    ic_4h:   ICResult | None
    ic_24h:  ICResult | None
    icir_1h:  ICIRResult | None
    icir_4h:  ICIRResult | None
    icir_24h: ICIRResult | None
    by_model: dict[str, dict]      # per-model IC/ICIR at all three horizons
    by_symbol: dict[str, dict]     # per-symbol 24h IC (for debugging weak tickers)
```

`BacktestReportBuilder.build(run_id, pg_conn)`:
1. Fetch rows where `score IS NOT NULL` for the given `run_id`
2. For each horizon, filter rows where `forward_return_{h} IS NOT NULL`
3. Call `compute_composite_ic(scores, returns, confidences)` and `compute_icir(...)`
4. Group by `model_id` and repeat
5. Group by `symbol` for the 24h horizon
6. Return `BacktestReport`; serialize to `reports/backtest_{run_id}.json`

Minimum 30 samples per group; returns `None` for that metric if below threshold (same convention as `PerformanceWorker`).

### 3.4 CLI `scripts/run_backtest.py`

```
python scripts/run_backtest.py \
    --start 2025-10-01 \
    --end   2026-04-30 \
    --run-id gkg-6m-v1 \
    [--dry-run]           # skip LLM: score=0.0, confidence=0.5
    [--max-per-chunk 250]
```

**Phase 1 — Fetch & ingest:**
- `asyncio.run(connector.fetch_historical(start, end))`
- For each `GKGNewsItem`: `TickerExtractor.extract(item.org_names)` → expand to one row per ticker
- Write to `backtest_signals` with `score=NULL` (pending)
- Progress bar via tqdm

**Phase 2 — LLM inference (with checkpoint/resume):**
- Before starting: estimate cost → `tokens_estimate × cost_per_token`. Prompt user for confirmation if estimated cost > $10.
- Fetch rows where `score IS NULL` for this `run_id`
- For each row: call `process_single_item(item, ensemble, budget_tracker) -> LLMSentimentOutput` — a new pure function extracted from the Celery task in `sentiment.py` that contains the core inference logic (ensemble query → aggregation → fallback). The Celery task becomes a thin wrapper around this function. Call `budget_tracker.check_budget()` inside `process_single_item` before the LLM call.
- On interrupt: partially completed rows already written; resume skips `score IS NOT NULL` rows
- `--dry-run`: writes `score=0.0, confidence=0.5, model_id="dry_run"` without any LLM call

**Phase 3 — Forward returns:**
- `ForwardReturnCalculator(pg_conn).populate(run_id, start, end)`
- Downloads yfinance data once per unique ticker
- Batch UPDATE to `backtest_signals`

**Phase 4 — Report:**
- `BacktestReportBuilder.build(run_id, pg_conn)`
- Prints formatted summary to stdout
- Saves `reports/backtest_{run_id}.json`

---

## 4. Error Handling

| Scenario | Behaviour |
|----------|-----------|
| GDELT chunk returns empty / HTTP error | Log warning, skip chunk, continue to next month |
| TickerExtractor finds no tickers | Article discarded (not written to `backtest_signals`), same as live pipeline |
| LLM budget exhausted mid-run | Phase 2 stops; partial rows remain; resume with `--run-id` same ID |
| yfinance returns no data for ticker | `forward_return_{h} = NULL` for all signals of that ticker; logged as warning |
| Signal outside market hours | `return_1h/4h = NULL` (no bar available); `return_24h` still computed from daily close |
| DB connection lost | psycopg2 exception propagates; script exits with error; resume on restart |

---

## 5. Testing Strategy

| Test | File | What it verifies |
|------|------|-----------------|
| `test_fetch_historical_chunks_by_month` | `tests/connectors/test_gdelt_gkg.py` | `fetch_historical()` calls API with correct `STARTDATETIME`/`ENDDATETIME` per chunk; sleeps 1s between chunks; handles empty response |
| `test_fetch_historical_skips_bad_records` | `tests/connectors/test_gdelt_gkg.py` | Records with missing URL or invalid timestamp skipped by `_parse_record()` |
| `test_forward_returns_1h_4h_24h` | `tests/backtest/test_forward_returns.py` | Correct calculation with mock DataFrame; values match expected arithmetic |
| `test_forward_returns_none_on_missing_bar` | `tests/backtest/test_forward_returns.py` | Returns `None` for 1h/4h when bar missing (weekend/holiday); no interpolation |
| `test_forward_returns_none_no_daily_close` | `tests/backtest/test_forward_returns.py` | Returns `None` for 24h when next daily close missing |
| `test_backtest_report_three_horizons` | `tests/backtest/test_backtest_report.py` | `BacktestReportBuilder.build()` computes IC/ICIR at all three horizons from mock rows |
| `test_backtest_report_below_min_samples` | `tests/backtest/test_backtest_report.py` | Returns `None` for horizon with < 30 samples |
| `test_backtest_report_by_model` | `tests/backtest/test_backtest_report.py` | per-model breakdown populated correctly |
| `test_backtest_checkpoint_skips_scored` | `tests/backtest/test_backtest_runner.py` | Phase 2 skips rows with `score IS NOT NULL` |
| `test_backtest_dry_run` | `tests/backtest/test_backtest_runner.py` | `--dry-run` writes `score=0.0` without calling LLM |

All tests use mocked yfinance, mocked GDELT API responses, and a mock psycopg2 cursor — no network calls in tests, no real DB required.

---

## 6. Files

| File | Action |
|------|--------|
| `migrations/005_add_backtest_signals.sql` | Create |
| `src/connectors/gdelt_gkg.py` | Modify — add `fetch_historical()` |
| `src/backtest/__init__.py` | Create (empty) |
| `src/backtest/forward_returns.py` | Create — `ForwardReturnCalculator` |
| `src/backtest/report.py` | Create — `BacktestReport`, `BacktestReportBuilder` |
| `scripts/run_backtest.py` | Create — CLI entry-point |
| `tests/backtest/__init__.py` | Create (empty) |
| `tests/backtest/test_forward_returns.py` | Create |
| `tests/backtest/test_backtest_report.py` | Create |
| `tests/backtest/test_backtest_runner.py` | Create |
| `tests/connectors/test_gdelt_gkg.py` | Modify — add `fetch_historical` tests |

---

## 7. References

- [Multi-Asset News-Driven Design Spec](2026-05-13-multi-asset-news-driven-design.md)
- `src/connectors/gdelt.py` — reference implementation for `fetch_historical()` pattern
- `src/performance/ic.py` — `compute_composite_ic()`, `compute_icir()` (reused as-is)
- `src/workers/sentiment.py` — sentiment inference logic to extract as callable function
- `docs/ARCHITECTURE.md` §2.4 — NewsIngestionWorker architecture
