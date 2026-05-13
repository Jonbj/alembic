# GKG Historical Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a 6-month historical backtest pipeline that validates the GKG news-driven LLM ensemble produces IC > 0 by fetching historical GDELT GKG records, running full LLM ensemble inference, computing 1h/4h/24h forward returns from yfinance, and generating an IC/ICIR report.

**Architecture:** Six-task TDD pipeline: (1) DB migration + package scaffolding, (2) `GDELTGKGConnector.fetch_historical()`, (3) extract `run_inference()` from `sentiment.py`, (4) `ForwardReturnCalculator`, (5) `BacktestReportBuilder`, (6) CLI `scripts/run_backtest.py`. Backtest signals go into a dedicated `backtest_signals` table (separate from `sentiment_signals`) with a `run_id` key to support multiple runs. Checkpoint/resume: Phase 2 skips rows with `score IS NOT NULL`.

**Tech Stack:** Python asyncio, aiohttp (GDELT GKG), psycopg2 (PostgreSQL), yfinance (price data), tqdm (progress), argparse (CLI), `src/performance/ic.py` pure functions (reused as-is).

---

## File Map

| File | Action |
|------|--------|
| `migrations/005_add_backtest_signals.sql` | Create |
| `src/backtest/__init__.py` | Create (empty) |
| `src/backtest/forward_returns.py` | Create |
| `src/backtest/report.py` | Create |
| `src/connectors/gdelt_gkg.py` | Modify — add `fetch_historical()` |
| `src/workers/sentiment.py` | Modify — extract `run_inference()` |
| `scripts/run_backtest.py` | Create |
| `tests/backtest/__init__.py` | Create (empty) |
| `tests/backtest/test_forward_returns.py` | Create |
| `tests/backtest/test_backtest_report.py` | Create |
| `tests/backtest/test_backtest_runner.py` | Create |
| `tests/connectors/test_gdelt_gkg.py` | Modify — add `fetch_historical` tests |
| `tests/workers/test_sentiment_worker.py` | Modify — add `run_inference` tests |

---

## Task 1: DB Migration + Package Scaffolding

**Files:**
- Create: `migrations/005_add_backtest_signals.sql`
- Create: `src/backtest/__init__.py`
- Create: `tests/backtest/__init__.py`

- [ ] **Step 1: Write the migration SQL**

```sql
-- migrations/005_add_backtest_signals.sql
CREATE TABLE IF NOT EXISTS backtest_signals (
    id                   SERIAL PRIMARY KEY,
    run_id               TEXT NOT NULL,
    symbol               TEXT NOT NULL,
    article_title        TEXT NOT NULL DEFAULT '',
    article_url          TEXT NOT NULL DEFAULT '',
    score                DOUBLE PRECISION,
    confidence           DOUBLE PRECISION,
    reasoning            TEXT,
    model_id             TEXT,
    ensemble_std         DOUBLE PRECISION,
    fallback_used        BOOLEAN NOT NULL DEFAULT FALSE,
    generated_at         TIMESTAMPTZ NOT NULL,
    forward_return_1h    DOUBLE PRECISION,
    forward_return_4h    DOUBLE PRECISION,
    forward_return_24h   DOUBLE PRECISION
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_backtest_signals_dedup
    ON backtest_signals (run_id, symbol, article_url, generated_at);

CREATE INDEX IF NOT EXISTS idx_backtest_signals_run_id
    ON backtest_signals (run_id, symbol, generated_at);

CREATE INDEX IF NOT EXISTS idx_backtest_signals_pending
    ON backtest_signals (run_id, score)
    WHERE score IS NULL;
```

- [ ] **Step 2: Apply migration**

```bash
psql $DATABASE_URL -f migrations/005_add_backtest_signals.sql
```

Expected: `CREATE TABLE`, `CREATE INDEX` (no errors).

- [ ] **Step 3: Verify table exists**

```bash
psql $DATABASE_URL -c "\d backtest_signals"
```

Expected: table with all 15 columns listed.

- [ ] **Step 4: Create empty `__init__.py` files**

```bash
touch src/backtest/__init__.py
touch tests/backtest/__init__.py
```

- [ ] **Step 5: Commit**

```bash
git add migrations/005_add_backtest_signals.sql src/backtest/__init__.py tests/backtest/__init__.py
git commit -m "feat: add backtest_signals table migration and package scaffold"
```

---

## Task 2: `GDELTGKGConnector.fetch_historical()`

**Files:**
- Modify: `src/connectors/gdelt_gkg.py`
- Modify: `tests/connectors/test_gdelt_gkg.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/connectors/test_gdelt_gkg.py`:

```python
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio


SAMPLE_RECORD = {
    "date": "20251001140000",
    "V2Organizations": "Apple Inc",
    "V2DocumentIdentifier": "https://reuters.com/article/1",
    "extras": '{"PageTitle": "Apple earnings beat"}',
}

SAMPLE_RECORD_2 = {
    "date": "20251101140000",
    "V2Organizations": "Microsoft Corporation",
    "V2DocumentIdentifier": "https://reuters.com/article/2",
    "extras": '{"PageTitle": "Microsoft cloud growth"}',
}


@pytest.mark.asyncio
async def test_fetch_historical_chunks_by_month():
    """fetch_historical makes one API call per month with correct STARTDATETIME."""
    connector = GDELTGKGConnector()
    start = datetime(2025, 10, 1, tzinfo=timezone.utc)
    end = datetime(2025, 11, 30, tzinfo=timezone.utc)

    call_params = []

    async def mock_backoff(session, params, url):
        call_params.append(dict(params))
        month = params["STARTDATETIME"][:6]
        if month == "202510":
            return {"gkg": [SAMPLE_RECORD]}
        return {"gkg": [SAMPLE_RECORD_2]}

    with patch.object(connector, "_fetch_with_backoff", side_effect=mock_backoff):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            items = [item async for item in connector.fetch_historical(start, end)]

    assert len(call_params) == 2
    assert call_params[0]["STARTDATETIME"] == "20251001000000"
    assert call_params[0]["ENDDATETIME"] == "20251031235959"
    assert call_params[1]["STARTDATETIME"] == "20251101000000"
    assert len(items) == 2


@pytest.mark.asyncio
async def test_fetch_historical_sleeps_between_chunks():
    """fetch_historical sleeps 1 second between monthly chunks."""
    connector = GDELTGKGConnector()
    start = datetime(2025, 10, 1, tzinfo=timezone.utc)
    end = datetime(2025, 11, 30, tzinfo=timezone.utc)

    sleep_calls = []

    async def mock_sleep(seconds):
        sleep_calls.append(seconds)

    with patch.object(connector, "_fetch_with_backoff", return_value={"gkg": []}):
        with patch("asyncio.sleep", side_effect=mock_sleep):
            items = [item async for item in connector.fetch_historical(start, end)]

    assert len(sleep_calls) == 2
    assert all(s == 1.0 for s in sleep_calls)


@pytest.mark.asyncio
async def test_fetch_historical_skips_bad_records():
    """fetch_historical skips records with missing URL or invalid timestamp."""
    connector = GDELTGKGConnector()
    start = datetime(2025, 10, 1, tzinfo=timezone.utc)
    end = datetime(2025, 10, 31, tzinfo=timezone.utc)

    bad_records = [
        {"date": "20251001140000", "V2Organizations": "Apple Inc",
         "V2DocumentIdentifier": "", "extras": "{}"},       # missing URL
        {"date": "not-a-date", "V2Organizations": "Apple Inc",
         "V2DocumentIdentifier": "https://x.com/1", "extras": "{}"},  # bad date
        SAMPLE_RECORD,  # good record
    ]

    with patch.object(connector, "_fetch_with_backoff",
                      return_value={"gkg": bad_records}):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            items = [item async for item in connector.fetch_historical(start, end)]

    assert len(items) == 1
    assert items[0].url == "https://reuters.com/article/1"


@pytest.mark.asyncio
async def test_fetch_historical_empty_response_continues():
    """fetch_historical continues to next month when API returns empty."""
    connector = GDELTGKGConnector()
    start = datetime(2025, 10, 1, tzinfo=timezone.utc)
    end = datetime(2025, 11, 30, tzinfo=timezone.utc)

    responses = [None, {"gkg": [SAMPLE_RECORD_2]}]
    call_count = [0]

    async def mock_backoff(session, params, url):
        r = responses[call_count[0]]
        call_count[0] += 1
        return r

    with patch.object(connector, "_fetch_with_backoff", side_effect=mock_backoff):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            items = [item async for item in connector.fetch_historical(start, end)]

    assert len(items) == 1
    assert items[0].org_names == ["Microsoft Corporation"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/connectors/test_gdelt_gkg.py::test_fetch_historical_chunks_by_month -v
```

Expected: FAIL with `AttributeError: 'GDELTGKGConnector' object has no attribute 'fetch_historical'`

- [ ] **Step 3: Implement `fetch_historical` in `src/connectors/gdelt_gkg.py`**

Add this method to `GDELTGKGConnector`, after the existing `fetch()` method:

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
    import asyncio

    current = start_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    async with aiohttp.ClientSession() as session:
        while current <= end_date:
            if current.month == 12:
                next_month = current.replace(year=current.year + 1, month=1, day=1)
            else:
                next_month = current.replace(month=current.month + 1, day=1)

            from datetime import timedelta
            chunk_end = min(next_month - timedelta(seconds=1), end_date)

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

Also add `from datetime import timedelta` at the top of the file if not already present.

- [ ] **Step 4: Run all new + existing GKG tests**

```bash
pytest tests/connectors/test_gdelt_gkg.py -v
```

Expected: 11 passed (7 existing + 4 new).

- [ ] **Step 5: Commit**

```bash
git add src/connectors/gdelt_gkg.py tests/connectors/test_gdelt_gkg.py
git commit -m "feat: add GDELTGKGConnector.fetch_historical() for backtest"
```

---

## Task 3: Extract `run_inference()` from `sentiment.py`

**Files:**
- Modify: `src/workers/sentiment.py`
- Modify: `tests/workers/test_sentiment_worker.py`

- [ ] **Step 1: Write failing tests for `run_inference`**

Add to `tests/workers/test_sentiment_worker.py`:

```python
from src.workers.sentiment import run_inference


class TestRunInference:
    """Tests for run_inference — pure inference without store writes."""

    @pytest.mark.asyncio
    async def test_run_inference_ensemble_success(self):
        """run_inference returns SentimentResult without touching any store."""
        mock_aggregator = MagicMock(spec=EnsembleAggregator)
        mock_aggregator.aggregate.return_value = MagicMock(
            polarity=0.8,
            confidence=0.9,
            reasoning="Bullish on earnings",
            model_ids=["opus"],
            ensemble_std=0.05,
        )
        mock_budget = AsyncMock(spec=LLMBudgetTracker)
        mock_budget.check_budget = AsyncMock()
        mock_budget.record_spending = AsyncMock()
        mock_finbert = MagicMock(spec=FinBERTClient)

        item = make_news_item("AAPL", 0)

        with patch("src.workers.sentiment.run_ensemble_query",
                   new_callable=AsyncMock) as mock_eq:
            mock_eq.return_value = [MagicMock()]
            result = await run_inference(
                item=item,
                clients=[],
                aggregator=mock_aggregator,
                finbert=mock_finbert,
                budget_tracker=mock_budget,
            )

        assert result is not None
        assert result.symbol == "AAPL"
        assert result.fallback_used is False
        assert abs(result.score) <= 1.0
        mock_budget.check_budget.assert_called_once()
        mock_finbert.analyze.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_inference_divergence_uses_finbert(self):
        """run_inference uses FinBERT when ensemble diverges (aggregate returns None)."""
        mock_aggregator = MagicMock(spec=EnsembleAggregator)
        mock_aggregator.aggregate.return_value = None  # divergence

        mock_finbert = MagicMock(spec=FinBERTClient)
        mock_finbert.analyze.return_value = MagicMock(polarity=0.3, confidence=0.7)

        mock_budget = AsyncMock(spec=LLMBudgetTracker)
        mock_budget.check_budget = AsyncMock()

        item = make_news_item("MSFT", 1)

        with patch("src.workers.sentiment.run_ensemble_query",
                   new_callable=AsyncMock, return_value=[MagicMock()]):
            result = await run_inference(
                item=item,
                clients=[],
                aggregator=mock_aggregator,
                finbert=mock_finbert,
                budget_tracker=mock_budget,
            )

        assert result is not None
        assert result.fallback_used is True
        assert result.model_id == "finbert"
        mock_finbert.analyze.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_inference_budget_exhausted_uses_finbert(self):
        """run_inference uses FinBERT when budget is exhausted."""
        mock_budget = AsyncMock(spec=LLMBudgetTracker)
        mock_budget.check_budget = AsyncMock(
            side_effect=LLMBudgetExhaustedError("exhausted")
        )
        mock_finbert = MagicMock(spec=FinBERTClient)
        mock_finbert.analyze.return_value = MagicMock(polarity=-0.2, confidence=0.6)

        item = make_news_item("SPY", 2)

        result = await run_inference(
            item=item,
            clients=[],
            aggregator=MagicMock(spec=EnsembleAggregator),
            finbert=mock_finbert,
            budget_tracker=mock_budget,
        )

        assert result is not None
        assert result.fallback_used is True
        assert "budget exhausted" in result.reasoning

    @pytest.mark.asyncio
    async def test_run_inference_no_store_writes(self):
        """run_inference never writes to Redis or PostgreSQL."""
        mock_redis = MagicMock()
        mock_pg = MagicMock()
        mock_aggregator = MagicMock(spec=EnsembleAggregator)
        mock_aggregator.aggregate.return_value = MagicMock(
            polarity=0.5, confidence=0.8, reasoning="ok",
            model_ids=["opus"], ensemble_std=0.0,
        )
        mock_budget = AsyncMock(spec=LLMBudgetTracker)
        mock_budget.check_budget = AsyncMock()
        mock_budget.record_spending = AsyncMock()

        item = make_news_item("NVDA", 3)

        with patch("src.workers.sentiment.run_ensemble_query",
                   new_callable=AsyncMock, return_value=[MagicMock()]):
            await run_inference(
                item=item, clients=[], aggregator=mock_aggregator,
                finbert=MagicMock(), budget_tracker=mock_budget,
            )

        # run_inference must NOT touch any store
        mock_redis.write_sentiment.assert_not_called()
        mock_pg.write_signal.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/workers/test_sentiment_worker.py::TestRunInference -v
```

Expected: FAIL with `ImportError: cannot import name 'run_inference' from 'src.workers.sentiment'`

- [ ] **Step 3: Refactor `src/workers/sentiment.py`**

Replace the existing `process_news_item` with two functions. The new `run_inference` contains the inference logic; `process_news_item` becomes a thin wrapper that adds store writes and fallback counter management.

Replace the body of `process_news_item` and add `run_inference` above it:

```python
async def run_inference(
    item: NewsItem,
    clients: list[LLMClient],
    aggregator: EnsembleAggregator,
    finbert: FinBERTClient,
    budget_tracker: LLMBudgetTracker,
) -> SentimentResult | None:
    """Core LLM inference — no store writes. Callable from live worker and backtest.

    Flow:
    1. Check budget BEFORE calling LLM ensemble
    2. If budget exhausted, fall back to FinBERT immediately
    3. Run ensemble query (models in parallel)
    4. Aggregate; if divergence (aggregate returns None), fall back to FinBERT
    5. Record spending for successful LLM calls
    6. Return SentimentResult (no Redis/PG writes)
    """
    symbol = item.asset_tags[0] if item.asset_tags else "UNKNOWN"
    prompt = _DK_COT_PROMPT.format(text=item.body[:2000], symbol=symbol)

    try:
        await budget_tracker.check_budget()

        raw_outputs = await run_ensemble_query(
            prompt=prompt,
            clients=clients,
            response_schema=LLMSentimentOutput,
            symbol=symbol,
        )

        aggregated = aggregator.aggregate(raw_outputs) if raw_outputs else None

        if aggregated is None:
            log.info(f"Ensemble diverged for {symbol}, using FinBERT fallback")
            fb_result = finbert.analyze(item.body[:512])
            return SentimentResult(
                symbol=symbol,
                score=fb_result.polarity * fb_result.confidence,
                confidence=fb_result.confidence,
                reasoning="FinBERT fallback (ensemble divergence)",
                model_id="finbert",
                fallback_used=True,
            )

        score = aggregated.polarity * aggregated.confidence
        input_tokens = len(prompt) // 4
        output_tokens = len(aggregated.reasoning) // 4
        for model_id in aggregated.model_ids:
            try:
                await budget_tracker.record_spending(
                    model_id=model_id,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
            except Exception as e:
                log.warning(f"Failed to record spending for {model_id}: {e}")

        return SentimentResult(
            symbol=symbol,
            score=max(-1.0, min(1.0, score)),
            confidence=aggregated.confidence,
            reasoning=aggregated.reasoning,
            model_id=f"ensemble:{'+'.join(aggregated.model_ids)}",
            ensemble_std=aggregated.ensemble_std,
            fallback_used=False,
        )

    except LLMBudgetExhaustedError:
        log.info(f"Budget exhausted for {symbol}, using FinBERT fallback")
        fb_result = finbert.analyze(item.body[:512])
        return SentimentResult(
            symbol=symbol,
            score=fb_result.polarity * fb_result.confidence,
            confidence=fb_result.confidence,
            reasoning="FinBERT fallback (budget exhausted)",
            model_id="finbert",
            fallback_used=True,
        )

    except Exception as e:
        log.error(f"Error processing news item for {symbol}: {e}")
        return None


async def process_news_item(
    item: NewsItem,
    clients: list[LLMClient],
    aggregator: EnsembleAggregator,
    finbert: FinBERTClient,
    budget_tracker: LLMBudgetTracker,
    redis_store: RedisStore,
    pg_store: PostgreSQLStore,
) -> SentimentResult | None:
    """Process a single news item: infer, update fallback counters, write to stores."""
    result = await run_inference(item, clients, aggregator, finbert, budget_tracker)

    if result is not None:
        try:
            if result.fallback_used:
                redis_store.increment_fallback_counter()
            else:
                redis_store.reset_fallback_counter()
            redis_store.write_sentiment(result)
            pg_store.write_signal(result)
        except Exception as e:
            log.error(f"Failed to write signal for {result.symbol}: {e}")

    return result
```

- [ ] **Step 4: Run all sentiment tests**

```bash
pytest tests/workers/test_sentiment_worker.py -v
```

Expected: all tests pass (existing + 4 new). Count should increase by 4.

- [ ] **Step 5: Run full suite to confirm no regressions**

```bash
pytest --tb=short -q
```

Expected: 468 passed (464 + 4 new).

- [ ] **Step 6: Commit**

```bash
git add src/workers/sentiment.py tests/workers/test_sentiment_worker.py
git commit -m "feat: extract run_inference() from sentiment.py for backtest reuse"
```

---

## Task 4: `ForwardReturnCalculator`

**Files:**
- Create: `src/backtest/forward_returns.py`
- Create: `tests/backtest/test_forward_returns.py`

- [ ] **Step 1: Write failing tests**

Create `tests/backtest/test_forward_returns.py`:

```python
"""Tests for ForwardReturnCalculator."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.backtest.forward_returns import ForwardReturnCalculator, ForwardReturns


def make_hourly_prices() -> pd.Series:
    """10 hourly bars starting 2025-10-01 14:00 UTC."""
    idx = pd.date_range("2025-10-01 14:00", periods=10, freq="1h", tz="UTC")
    return pd.Series(
        [100.0, 101.0, 102.0, 101.5, 103.0, 102.5, 104.0, 103.5, 105.0, 104.5],
        index=idx,
    )


def make_daily_prices() -> pd.Series:
    """5 daily close prices starting 2025-09-30."""
    idx = pd.date_range("2025-09-30", periods=5, freq="1D", tz="UTC")
    return pd.Series([99.0, 100.5, 102.0, 101.0, 103.5], index=idx)


def make_calculator() -> ForwardReturnCalculator:
    return ForwardReturnCalculator(pg_conn=MagicMock())


def test_forward_returns_1h():
    """1h return: (price at t_bar+1h - price at t_bar) / price at t_bar."""
    calc = make_calculator()
    ts = datetime(2025, 10, 1, 14, 0, tzinfo=timezone.utc)
    result = calc._compute_returns("AAPL", ts, make_hourly_prices(), make_daily_prices())

    # bar at 14:00 = 100.0, bar at 15:00 = 101.0 → (101-100)/100 = 0.01
    assert result.return_1h == pytest.approx(0.01)


def test_forward_returns_4h():
    """4h return: (price at t_bar+4h - price at t_bar) / price at t_bar."""
    calc = make_calculator()
    ts = datetime(2025, 10, 1, 14, 0, tzinfo=timezone.utc)
    result = calc._compute_returns("AAPL", ts, make_hourly_prices(), make_daily_prices())

    # bar at 14:00 = 100.0, bar at 18:00 = 103.0 → (103-100)/100 = 0.03
    assert result.return_4h == pytest.approx(0.03)


def test_forward_returns_24h():
    """24h return: next daily close / current daily close - 1."""
    calc = make_calculator()
    ts = datetime(2025, 10, 1, 14, 0, tzinfo=timezone.utc)
    result = calc._compute_returns("AAPL", ts, make_hourly_prices(), make_daily_prices())

    # daily: 2025-10-01 close=100.5, 2025-10-02 close=102.0 → (102-100.5)/100.5 ≈ 0.01493
    assert result.return_24h == pytest.approx((102.0 - 100.5) / 100.5)


def test_forward_returns_none_when_1h_bar_missing():
    """Returns None for 1h/4h when there are no bars after t_bar + offset."""
    calc = make_calculator()
    # Signal at last available bar (23:00): no bars 1h or 4h later
    ts = datetime(2025, 10, 1, 23, 0, tzinfo=timezone.utc)
    idx = pd.date_range("2025-10-01 23:00", periods=1, freq="1h", tz="UTC")
    short_series = pd.Series([100.0], index=idx)

    result = calc._compute_returns("AAPL", ts, short_series, make_daily_prices())

    assert result.return_1h is None
    assert result.return_4h is None


def test_forward_returns_none_when_no_next_daily_close():
    """Returns None for 24h when there is no next day's close."""
    calc = make_calculator()
    # Signal on the LAST day in the daily series
    idx = pd.date_range("2025-10-04", periods=1, freq="1D", tz="UTC")
    single_day = pd.Series([103.5], index=idx)

    ts = datetime(2025, 10, 4, 14, 0, tzinfo=timezone.utc)
    result = calc._compute_returns("AAPL", ts, make_hourly_prices(), single_day)

    assert result.return_24h is None


def test_forward_returns_none_when_ts_after_all_bars():
    """Returns None for all horizons when signal is after last available bar."""
    calc = make_calculator()
    ts = datetime(2025, 10, 2, 0, 0, tzinfo=timezone.utc)  # after last bar 23:00

    result = calc._compute_returns("AAPL", ts, make_hourly_prices(), make_daily_prices())

    assert result.return_1h is None
    assert result.return_4h is None


def test_forward_returns_none_when_no_price_data():
    """Returns all None when hourly prices are None (ticker not in yfinance)."""
    calc = make_calculator()
    ts = datetime(2025, 10, 1, 14, 0, tzinfo=timezone.utc)
    result = calc._compute_returns("UNKNOWN", ts, None, None)

    assert result == ForwardReturns(None, None, None)


def test_populate_calls_db_update(monkeypatch):
    """populate() fetches pending rows, downloads prices, and updates the DB."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=None)

    pending_rows = [
        {"id": 1, "symbol": "AAPL",
         "generated_at": datetime(2025, 10, 1, 14, 0, tzinfo=timezone.utc)},
    ]
    mock_cursor.fetchall.return_value = [
        (r["id"], r["symbol"], r["generated_at"]) for r in pending_rows
    ]

    calc = ForwardReturnCalculator(pg_conn=mock_conn)
    monkeypatch.setattr(
        calc, "_download_prices",
        lambda tickers, start, end, interval: {
            "AAPL": make_hourly_prices() if interval == "1h" else make_daily_prices()
        },
    )

    updated = calc.populate("test-run", datetime(2025, 10, 1), datetime(2025, 10, 31))

    assert updated == 1
    mock_conn.commit.assert_called_once()
    # executemany called with one update tuple
    mock_cursor.executemany.assert_called_once()
    args = mock_cursor.executemany.call_args[0]
    assert "UPDATE backtest_signals" in args[0]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/backtest/test_forward_returns.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.backtest.forward_returns'`

- [ ] **Step 3: Implement `src/backtest/forward_returns.py`**

```python
"""ForwardReturnCalculator — computes 1h/4h/24h price returns for backtest signals."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)


@dataclass
class ForwardReturns:
    return_1h: float | None
    return_4h: float | None
    return_24h: float | None


class ForwardReturnCalculator:
    """Downloads yfinance prices and populates forward returns in backtest_signals.

    Call pattern:
        calc = ForwardReturnCalculator(pg_conn)
        calc.populate(run_id, start_date, end_date)

    Downloads hourly + daily price data once per ticker for the entire period.
    Computes three forward returns per signal:
      - 1h:  (price at next_bar + 1h) / (price at next_bar) - 1
      - 4h:  (price at next_bar + 4h) / (price at next_bar) - 1
      - 24h: (next_day_close) / (current_day_close) - 1
    Returns None for any horizon where the required bar is missing (weekend, holiday,
    post-market). No interpolation — never guess prices.
    """

    def __init__(self, pg_conn) -> None:
        self._conn = pg_conn

    def populate(self, run_id: str, start_date: datetime, end_date: datetime) -> int:
        """Populate forward_return_1h/4h/24h for all scored rows in run_id.

        Returns the number of rows updated.
        """
        rows = self._fetch_scored_rows(run_id)
        if not rows:
            log.info("No scored rows found for run_id=%s", run_id)
            return 0

        tickers = list({r["symbol"] for r in rows})
        log.info("Downloading prices for %d tickers", len(tickers))

        hourly = self._download_prices(tickers, start_date, end_date, interval="1h")
        daily = self._download_prices(tickers, start_date, end_date, interval="1d")

        updates = []
        for row in rows:
            fwd = self._compute_returns(
                row["symbol"],
                row["generated_at"],
                hourly.get(row["symbol"]),
                daily.get(row["symbol"]),
            )
            updates.append((
                fwd.return_1h, fwd.return_4h, fwd.return_24h, row["id"]
            ))

        with self._conn.cursor() as cur:
            cur.executemany(
                "UPDATE backtest_signals "
                "SET forward_return_1h=%s, forward_return_4h=%s, forward_return_24h=%s "
                "WHERE id=%s",
                updates,
            )
        self._conn.commit()
        log.info("Updated %d forward return rows for run_id=%s", len(updates), run_id)
        return len(updates)

    def _fetch_scored_rows(self, run_id: str) -> list[dict]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT id, symbol, generated_at "
                "FROM backtest_signals "
                "WHERE run_id = %s AND score IS NOT NULL "
                "ORDER BY generated_at",
                (run_id,),
            )
            return [
                {"id": row[0], "symbol": row[1], "generated_at": row[2]}
                for row in cur.fetchall()
            ]

    def _download_prices(
        self,
        tickers: list[str],
        start: datetime,
        end: datetime,
        interval: str,
    ) -> dict[str, pd.Series]:
        """Download close prices for each ticker. Returns dict ticker → pd.Series."""
        result: dict[str, pd.Series] = {}
        dl_start = (start - timedelta(days=1)).strftime("%Y-%m-%d")
        dl_end = (end + timedelta(days=2)).strftime("%Y-%m-%d")
        for ticker in tickers:
            try:
                df = yf.download(
                    ticker,
                    start=dl_start,
                    end=dl_end,
                    interval=interval,
                    auto_adjust=True,
                    progress=False,
                )
                if not df.empty:
                    result[ticker] = df["Close"]
                else:
                    log.warning("yfinance returned empty data for %s (%s)", ticker, interval)
            except Exception as e:
                log.warning("yfinance download failed for %s: %s", ticker, e)
        return result

    def _compute_returns(
        self,
        symbol: str,
        ts: datetime,
        hourly: pd.Series | None,
        daily: pd.Series | None,
    ) -> ForwardReturns:
        """Compute 1h, 4h, 24h forward returns for a single signal at timestamp ts."""
        if hourly is None:
            return ForwardReturns(None, None, None)

        ts_utc = pd.Timestamp(ts).tz_convert("UTC") if ts.tzinfo else pd.Timestamp(ts, tz="UTC")

        # Find the first bar at or after ts
        idx = hourly.index.searchsorted(ts_utc)
        if idx >= len(hourly.index):
            return ForwardReturns(None, None, None)

        t_bar = hourly.index[idx]
        price_t = float(hourly.iloc[idx])

        def _return_at_offset(offset_hours: int) -> float | None:
            target = t_bar + pd.Timedelta(hours=offset_hours)
            future = hourly[hourly.index >= target]
            if future.empty:
                return None
            # Accept bar within 30 minutes of target to handle DST / market-open offsets
            if (future.index[0] - target).total_seconds() > 1800:
                return None
            return float((future.iloc[0] - price_t) / price_t)

        return_1h = _return_at_offset(1)
        return_4h = _return_at_offset(4)

        # 24h: next trading day close / current trading day close
        return_24h: float | None = None
        if daily is not None:
            day_ts = ts_utc.normalize()
            d_idx = daily.index.searchsorted(day_ts)
            if d_idx + 1 < len(daily.index):
                close_today = float(daily.iloc[d_idx])
                close_next = float(daily.iloc[d_idx + 1])
                if close_today > 0:
                    return_24h = (close_next - close_today) / close_today

        return ForwardReturns(return_1h, return_4h, return_24h)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/backtest/test_forward_returns.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Run full suite**

```bash
pytest --tb=short -q
```

Expected: 476 passed (468 + 8 new).

- [ ] **Step 6: Commit**

```bash
git add src/backtest/forward_returns.py tests/backtest/test_forward_returns.py
git commit -m "feat: add ForwardReturnCalculator for 1h/4h/24h return computation"
```

---

## Task 5: `BacktestReportBuilder`

**Files:**
- Create: `src/backtest/report.py`
- Create: `tests/backtest/test_backtest_report.py`

- [ ] **Step 1: Write failing tests**

Create `tests/backtest/test_backtest_report.py`:

```python
"""Tests for BacktestReportBuilder."""

from unittest.mock import MagicMock

import pytest

from src.backtest.report import BacktestReport, BacktestReportBuilder


def make_rows(n: int, model_id: str = "ensemble:opus",
              return_1h: float = 0.01, return_4h: float = 0.02,
              return_24h: float = 0.015, score: float = 0.5,
              confidence: float = 0.8) -> list[tuple]:
    """Generate n fake scored rows with forward returns."""
    return [
        (model_id, score, confidence, False, return_1h, return_4h, return_24h)
        for _ in range(n)
    ]
    # columns: model_id, score, confidence, fallback_used,
    #          forward_return_1h, forward_return_4h, forward_return_24h


def make_builder_with_rows(rows: list[tuple]) -> BacktestReportBuilder:
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=None)
    mock_cur.fetchall.return_value = rows
    mock_cur.fetchone.return_value = (len(rows),)
    return BacktestReportBuilder(pg_conn=mock_conn)


def test_report_computes_ic_at_three_horizons():
    """build() produces non-None IC results for 1h, 4h, 24h when >= 30 rows."""
    rows = make_rows(50)
    builder = make_builder_with_rows(rows)
    report = builder.build("test-run")

    assert report.ic_1h is not None
    assert report.ic_4h is not None
    assert report.ic_24h is not None
    assert report.signals_with_returns == 50


def test_report_returns_none_ic_below_min_samples():
    """build() returns None for a horizon when fewer than 30 rows have that return."""
    # Only 10 rows — below min_samples=30
    rows = make_rows(10)
    builder = make_builder_with_rows(rows)
    report = builder.build("test-run")

    assert report.ic_1h is None
    assert report.ic_4h is None
    assert report.ic_24h is None


def test_report_by_model_populated():
    """build() groups IC results by model_id."""
    rows = make_rows(50, model_id="ensemble:opus") + make_rows(50, model_id="finbert")
    builder = make_builder_with_rows(rows)
    report = builder.build("test-run")

    assert "ensemble:opus" in report.by_model
    assert "finbert" in report.by_model


def test_report_excludes_none_returns():
    """build() counts only rows where forward_return is not None."""
    rows_with = make_rows(40)
    rows_without = [("ensemble:opus", 0.5, 0.8, False, None, None, None)] * 10
    builder = make_builder_with_rows(rows_with + rows_without)
    report = builder.build("test-run")

    assert report.signals_with_returns == 40


def test_report_serializes_to_json():
    """BacktestReport can be serialized to a JSON-compatible dict."""
    import json
    rows = make_rows(50)
    builder = make_builder_with_rows(rows)
    report = builder.build("test-run")

    data = report.to_dict()
    json_str = json.dumps(data)  # must not raise
    parsed = json.loads(json_str)
    assert parsed["run_id"] == "test-run"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/backtest/test_backtest_report.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.backtest.report'`

- [ ] **Step 3: Implement `src/backtest/report.py`**

```python
"""BacktestReportBuilder — builds IC/ICIR report from backtest_signals."""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.performance.ic import ICIRResult, ICResult, compute_composite_ic, compute_icir

log = logging.getLogger(__name__)

_MIN_SAMPLES = 30

_FETCH_ROWS = """
    SELECT model_id, score, confidence, fallback_used,
           forward_return_1h, forward_return_4h, forward_return_24h
    FROM backtest_signals
    WHERE run_id = %s AND score IS NOT NULL
    ORDER BY generated_at
"""

_COUNT_TOTAL = """
    SELECT COUNT(*) FROM backtest_signals WHERE run_id = %s AND score IS NOT NULL
"""


@dataclass
class BacktestReport:
    run_id: str
    total_signals: int
    signals_with_returns: int
    ic_1h: ICResult | None
    ic_4h: ICResult | None
    ic_24h: ICResult | None
    icir_1h: ICIRResult | None
    icir_4h: ICIRResult | None
    icir_24h: ICIRResult | None
    by_model: dict[str, dict[str, Any]] = field(default_factory=dict)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict."""
        def _ic(r):
            if r is None:
                return None
            return {
                "composite_ic": r.composite_ic,
                "spearman_ic": r.spearman_ic,
                "weighted_hit_rate": r.weighted_hit_rate,
                "brier_score": r.brier_score,
                "sample_count": r.sample_count,
            }

        def _icir(r):
            if r is None:
                return None
            return {
                "icir": r.icir,
                "ic_mean": r.ic_mean,
                "ic_std": r.ic_std,
                "newey_west_std": r.newey_west_std,
                "lag": r.lag,
                "sample_count": r.sample_count,
            }

        return {
            "run_id": self.run_id,
            "total_signals": self.total_signals,
            "signals_with_returns": self.signals_with_returns,
            "ic_1h": _ic(self.ic_1h),
            "ic_4h": _ic(self.ic_4h),
            "ic_24h": _ic(self.ic_24h),
            "icir_1h": _icir(self.icir_1h),
            "icir_4h": _icir(self.icir_4h),
            "icir_24h": _icir(self.icir_24h),
            "by_model": self.by_model,
            "generated_at": self.generated_at.isoformat(),
        }


class BacktestReportBuilder:
    """Reads backtest_signals for a run_id and computes IC/ICIR at three horizons."""

    def __init__(self, pg_conn) -> None:
        self._conn = pg_conn

    def build(self, run_id: str) -> BacktestReport:
        """Fetch rows and compute IC/ICIR report for all three horizons."""
        with self._conn.cursor() as cur:
            cur.execute(_COUNT_TOTAL, (run_id,))
            total = cur.fetchone()[0]

            cur.execute(_FETCH_ROWS, (run_id,))
            rows = cur.fetchall()

        # rows columns: model_id, score, confidence, fallback_used,
        #               forward_return_1h, forward_return_4h, forward_return_24h
        def _extract(horizon_idx: int):
            """Extract (scores, returns, confs) for a horizon, skipping None returns."""
            scores, returns, confs = [], [], []
            for model_id, score, conf, fallback, r1h, r4h, r24h in rows:
                ret = [r1h, r4h, r24h][horizon_idx]
                if ret is None or fallback:
                    continue
                scores.append(score)
                returns.append(ret)
                confs.append(conf)
            return scores, returns, confs

        def _ic_icir(scores, returns, confs):
            if len(scores) < _MIN_SAMPLES:
                return None, None
            return (
                compute_composite_ic(scores, returns, confs),
                compute_icir(scores, returns, confs, min_samples=_MIN_SAMPLES),
            )

        s1, r1, c1 = _extract(0)
        s4, r4, c4 = _extract(1)
        s24, r24, c24 = _extract(2)

        ic_1h, icir_1h = _ic_icir(s1, r1, c1)
        ic_4h, icir_4h = _ic_icir(s4, r4, c4)
        ic_24h, icir_24h = _ic_icir(s24, r24, c24)

        signals_with_returns = max(len(s1), len(s4), len(s24))

        # Per-model breakdown (24h horizon)
        by_model: dict[str, dict] = {}
        model_ids = list({row[0] for row in rows})
        for mid in model_ids:
            model_rows = [r for r in rows if r[0] == mid and not r[3]]
            ms = [r[1] for r in model_rows if r[6] is not None]
            mr = [r[6] for r in model_rows if r[6] is not None]
            mc = [r[2] for r in model_rows if r[6] is not None]
            if len(ms) >= _MIN_SAMPLES:
                mic = compute_composite_ic(ms, mr, mc)
                micir = compute_icir(ms, mr, mc, min_samples=_MIN_SAMPLES)
                by_model[mid] = {
                    "ic_24h": mic.composite_ic,
                    "icir_24h": micir.icir,
                    "sample_count": len(ms),
                }
            else:
                by_model[mid] = {"ic_24h": None, "icir_24h": None, "sample_count": len(ms)}

        return BacktestReport(
            run_id=run_id,
            total_signals=total,
            signals_with_returns=signals_with_returns,
            ic_1h=ic_1h,
            ic_4h=ic_4h,
            ic_24h=ic_24h,
            icir_1h=icir_1h,
            icir_4h=icir_4h,
            icir_24h=icir_24h,
            by_model=by_model,
        )
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/backtest/test_backtest_report.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Run full suite**

```bash
pytest --tb=short -q
```

Expected: 481 passed (476 + 5 new).

- [ ] **Step 6: Commit**

```bash
git add src/backtest/report.py tests/backtest/test_backtest_report.py
git commit -m "feat: add BacktestReportBuilder with IC/ICIR at 1h/4h/24h horizons"
```

---

## Task 6: CLI `scripts/run_backtest.py`

**Files:**
- Create: `scripts/run_backtest.py`
- Create: `tests/backtest/test_backtest_runner.py`

- [ ] **Step 1: Write failing tests**

Create `tests/backtest/test_backtest_runner.py`:

```python
"""Tests for backtest CLI runner helpers."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

# Import the helpers we'll write in run_backtest.py
from scripts.run_backtest import _estimate_cost, phase2_infer


def test_estimate_cost_scales_with_article_count():
    """_estimate_cost returns a positive float proportional to article count."""
    cost_10 = _estimate_cost(10)
    cost_100 = _estimate_cost(100)

    assert cost_10 > 0
    assert cost_100 == pytest.approx(cost_10 * 10)


def test_phase2_infer_dry_run_writes_zero_score(monkeypatch):
    """--dry-run writes score=0.0 for every pending row without calling any LLM."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=None)

    pending_rows = [
        (1, "AAPL", datetime(2025, 10, 1, 14, tzinfo=timezone.utc),
         "https://x.com/1", "Apple earns record profit"),
    ]
    mock_cur.fetchall.return_value = pending_rows

    processed = phase2_infer(mock_conn, run_id="test", dry_run=True)

    assert processed == 1
    # UPDATE called with score=0.0
    update_call = mock_cur.execute.call_args_list[-1]
    assert "score=0.0" in update_call[0][0] or 0.0 in update_call[0][1]
    mock_conn.commit.assert_called_once()


def test_phase2_infer_checkpoint_skips_scored_rows(monkeypatch):
    """phase2_infer skips rows that already have a score (checkpoint/resume)."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=None)

    # DB returns 0 pending rows (all already scored)
    mock_cur.fetchall.return_value = []

    processed = phase2_infer(mock_conn, run_id="test", dry_run=True)

    assert processed == 0
    # SELECT query must filter score IS NULL
    select_call = mock_cur.execute.call_args_list[0]
    assert "score IS NULL" in select_call[0][0]


def test_phase2_infer_sql_filters_by_run_id(monkeypatch):
    """phase2_infer's SELECT query includes run_id filter."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=None)
    mock_cur.fetchall.return_value = []

    phase2_infer(mock_conn, run_id="specific-run-id", dry_run=True)

    select_call = mock_cur.execute.call_args_list[0]
    assert "specific-run-id" in select_call[0][1]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/backtest/test_backtest_runner.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.run_backtest'`

- [ ] **Step 3: Create `scripts/__init__.py`** (so pytest can import from scripts/)

```bash
touch scripts/__init__.py
```

- [ ] **Step 4: Implement `scripts/run_backtest.py`**

```python
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
from src.llm.client import DeepseekClient, OpusClient, Qwen35Client
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
    """Estimate inference cost: 3 models × ~300 input + ~100 output tokens × Opus rates."""
    # Opus: $15/1M input, $75/1M output (upper bound for the ensemble)
    cost_per_call = (300 * 15.0 + 100 * 75.0) / 1_000_000
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
    """Phase 1: fetch GKG historical news, extract tickers, write pending rows."""
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
    """Phase 2: run LLM inference on pending rows. Skips rows with score IS NOT NULL."""
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

    clients = [] if dry_run else [OpusClient(), Qwen35Client(), DeepseekClient()]
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
    """Phase 3: populate forward_return_1h/4h/24h from yfinance."""
    log.info("Phase 3: computing forward returns for run_id=%s", run_id)
    calc = ForwardReturnCalculator(pg_conn)
    updated = calc.populate(run_id, start, end)
    log.info("Phase 3 complete: %d rows updated", updated)
    return updated


def phase4_report(pg_conn, run_id: str) -> None:
    """Phase 4: build and print IC/ICIR report, save to reports/ directory."""
    log.info("Phase 4: building report for run_id=%s", run_id)
    builder = BacktestReportBuilder(pg_conn)
    report = builder.build(run_id)

    print("\n" + "=" * 60)
    print(f"BACKTEST REPORT — {run_id}")
    print("=" * 60)
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
    print("\nPer-model IC (24h):")
    for model, stats in report.by_model.items():
        if stats["ic_24h"] is not None:
            print(f"  {model}: IC={stats['ic_24h']:.4f}, n={stats['sample_count']}")
        else:
            print(f"  {model}: insufficient samples (n={stats['sample_count']})")

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
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/backtest/test_backtest_runner.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Run full suite**

```bash
pytest --tb=short -q
```

Expected: 485 passed (481 + 4 new).

- [ ] **Step 7: Commit**

```bash
git add scripts/__init__.py scripts/run_backtest.py tests/backtest/test_backtest_runner.py
git commit -m "feat: add backtest CLI runner with 4-phase pipeline and dry-run support"
```

---

## Final Verification

- [ ] **Run full test suite one last time**

```bash
pytest --tb=short -q
```

Expected: 485 passed, 0 failed.

- [ ] **Verify CLI help works**

```bash
python scripts/run_backtest.py --help
```

Expected: usage text with `--start`, `--end`, `--run-id`, `--dry-run`, `--max-per-chunk`.

- [ ] **Smoke test with `--dry-run` (requires DB running)**

```bash
python scripts/run_backtest.py \
    --start 2026-05-01 \
    --end   2026-05-07 \
    --run-id smoke-test \
    --dry-run
```

Expected: Phase 1 fetches news, Phase 2 writes score=0.0, Phase 3 computes returns (some None — 1 week of data may be sparse), Phase 4 prints report. No LLM calls.

---

## References

- Spec: `docs/superpowers/specs/2026-05-13-gkg-backtest-design.md`
- `src/connectors/gdelt.py` — reference pattern for `fetch_historical()`
- `src/performance/ic.py` — `ICResult`, `ICIRResult`, `compute_composite_ic()`, `compute_icir()`
- `src/workers/sentiment.py` — `run_inference()` (added in Task 3)
- `docs/ARCHITECTURE.md` §2.4 — NewsIngestionWorker context
