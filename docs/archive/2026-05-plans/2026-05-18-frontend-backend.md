# Frontend Backend Extensions — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the FastAPI backend with 6 new endpoints and 2 new DB tables that the frontend dashboard will consume, plus a nightly retention sweep to keep `news_log` and `llm_responses` bounded.

**Architecture:** SentimentWorker writes each processed article to `news_log` and the per-model outputs to `llm_responses` before returning. New FastAPI route files expose this data plus Alpaca positions/orders and config read/write. A nightly Celery task deletes rows older than configurable retention thresholds.

**Tech Stack:** Python 3.11, FastAPI, psycopg2, alpaca-py, Celery, PostgreSQL, pytest

---

## File Map

**New files:**
- `migrations/006_add_news_log.sql`
- `migrations/007_add_llm_responses.sql`
- `src/workers/retention.py`
- `src/api/routes/trading.py`
- `src/api/routes/news_routes.py`
- `src/api/routes/llm_routes.py`
- `src/api/routes/config_routes.py`
- `tests/store/test_pg_news_llm.py`
- `tests/workers/test_retention.py`
- `tests/api/test_trading_routes.py`
- `tests/api/test_news_routes.py`
- `tests/api/test_llm_routes.py`
- `tests/api/test_config_routes.py`

**Modified files:**
- `src/store/pg_store.py` — `write_signal` returns `int`; 4 new methods
- `src/workers/sentiment.py` — `run_inference` returns tuple; `process_news_item` logs news + LLM outputs
- `src/workers/celery_app.py` — add retention beat entry
- `src/api/deps.py` — add `get_alpaca_trading_client`
- `src/api/routes/performance.py` — add `/api/performance/pnl`
- `src/api/main.py` — register 4 new routers
- `scripts/run_backtest.py` — update call site for new `run_inference` return type
- `tests/workers/test_sentiment_worker.py` — update for new return type
- `config/trading.yaml` — add `retention` section

---

## Task 1: DB Migrations — news_log and llm_responses

**Files:**
- Create: `migrations/006_add_news_log.sql`
- Create: `migrations/007_add_llm_responses.sql`

- [ ] **Step 1: Create migration 006**

```sql
-- migrations/006_add_news_log.sql
-- Stores each news article processed by SentimentWorker (title, url, source, ticker).
-- Retention: rows older than RETENTION_DAYS deleted by run_retention_sweep().

CREATE TABLE IF NOT EXISTS news_log (
    id          BIGSERIAL PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT '',
    url         TEXT NOT NULL DEFAULT '',
    source      VARCHAR(50) NOT NULL,
    ticker      VARCHAR(20) NOT NULL,
    body_snippet TEXT,
    raw_sentiment DOUBLE PRECISION,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_news_log_time_brin
    ON news_log USING BRIN (fetched_at);

CREATE INDEX IF NOT EXISTS idx_news_log_ticker_time
    ON news_log (ticker, fetched_at DESC);

CREATE INDEX IF NOT EXISTS idx_news_log_source_time
    ON news_log (source, fetched_at DESC);
```

- [ ] **Step 2: Create migration 007**

```sql
-- migrations/007_add_llm_responses.sql
-- Stores individual model outputs before ensemble aggregation.
-- Retention: rows older than RETENTION_DAYS deleted by run_retention_sweep().

CREATE TABLE IF NOT EXISTS llm_responses (
    id           BIGSERIAL PRIMARY KEY,
    signal_id    BIGINT REFERENCES sentiment_signals(id) ON DELETE CASCADE,
    model_id     VARCHAR(50) NOT NULL,
    polarity     DOUBLE PRECISION NOT NULL,
    confidence   DOUBLE PRECISION NOT NULL,
    reasoning    TEXT,
    eligible     BOOLEAN NOT NULL DEFAULT TRUE,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_llm_responses_signal
    ON llm_responses (signal_id);

CREATE INDEX IF NOT EXISTS idx_llm_responses_time_brin
    ON llm_responses USING BRIN (generated_at);

CREATE INDEX IF NOT EXISTS idx_llm_responses_model_time
    ON llm_responses (model_id, generated_at DESC);
```

- [ ] **Step 3: Apply both migrations**

```bash
psql "$DATABASE_URL" -f migrations/006_add_news_log.sql
psql "$DATABASE_URL" -f migrations/007_add_llm_responses.sql
```

Expected: `CREATE TABLE`, `CREATE INDEX` lines, no errors.

- [ ] **Step 4: Commit**

```bash
git add migrations/006_add_news_log.sql migrations/007_add_llm_responses.sql
git commit -m "feat: add news_log and llm_responses tables (migrations 006-007)"
```

---

## Task 2: pg_store — write_signal returns signal_id

**Files:**
- Modify: `src/store/pg_store.py`
- Test: `tests/store/test_pg_store.py` (existing)

- [ ] **Step 1: Write failing test**

Add to `tests/store/test_pg_store.py` (find the existing `TestPostgreSQLStore` class or add a new test):

```python
def test_write_signal_returns_signal_id(pg_store, sample_signal):
    """write_signal must return the integer id of the inserted row."""
    signal_id = pg_store.write_signal(sample_signal)
    assert isinstance(signal_id, int)
    assert signal_id > 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/store/test_pg_store.py::test_write_signal_returns_signal_id -v
```

Expected: `FAILED — AssertionError: assert None` (currently returns None).

- [ ] **Step 3: Add RETURNING id to _INSERT_SIGNAL and return the id**

In `src/store/pg_store.py`, update the `_INSERT_SIGNAL` constant:

```python
    _INSERT_SIGNAL = """
        INSERT INTO sentiment_signals (
            symbol, score, confidence, reasoning, model_id,
            ensemble_std, fallback_used, generated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (symbol, generated_at) DO UPDATE SET
            score = EXCLUDED.score,
            confidence = EXCLUDED.confidence,
            reasoning = EXCLUDED.reasoning,
            model_id = EXCLUDED.model_id,
            ensemble_std = EXCLUDED.ensemble_std,
            fallback_used = EXCLUDED.fallback_used
        RETURNING id
    """
```

Update `write_signal` signature and body:

```python
    def write_signal(self, result: SentimentResult) -> int:
        """Write sentiment signal to database. Returns the inserted/updated row id."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    self._INSERT_SIGNAL,
                    (
                        result.symbol,
                        result.score,
                        result.confidence,
                        result.reasoning,
                        result.model_id,
                        result.ensemble_std,
                        result.fallback_used,
                        result.generated_at,
                    ),
                )
                row = cur.fetchone()
                signal_id: int = row[0]
            conn.commit()
            return signal_id
        except Exception:
            conn.rollback()
            raise
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/store/test_pg_store.py::test_write_signal_returns_signal_id -v
```

Expected: `PASSED`.

- [ ] **Step 5: Verify existing tests still pass**

```bash
pytest tests/store/test_pg_store.py -v
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/store/pg_store.py tests/store/test_pg_store.py
git commit -m "feat: write_signal returns inserted signal_id (RETURNING id)"
```

---

## Task 3: pg_store — write methods for news_log and llm_responses

**Files:**
- Modify: `src/store/pg_store.py`
- Create: `tests/store/test_pg_news_llm.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/store/test_pg_news_llm.py
import pytest
from datetime import datetime, timezone
from src.store.pg_store import PostgreSQLStore
from src.models.news import NewsItem


@pytest.fixture
def pg_store(pg_conn):
    return PostgreSQLStore(conn=pg_conn)


@pytest.fixture
def sample_news_item():
    return NewsItem(
        id="https://example.com/article:AAPL",
        body="Apple quarterly results beat expectations significantly.",
        title="Apple beats Q3 estimates",
        source="gdelt_gkg",
        url="https://example.com/article",
        asset_tags=["AAPL"],
        timestamp=datetime(2026, 5, 18, 14, 0, tzinfo=timezone.utc),
    )


def test_log_news_item_inserts_row(pg_store, sample_news_item):
    """log_news_item inserts one row into news_log."""
    pg_store.log_news_item(
        item=sample_news_item,
        ticker="AAPL",
    )
    conn = pg_store._get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT title, source, ticker FROM news_log WHERE url = %s",
                    ("https://example.com/article",))
        row = cur.fetchone()
    assert row is not None
    assert row[0] == "Apple beats Q3 estimates"
    assert row[1] == "gdelt_gkg"
    assert row[2] == "AAPL"


def test_log_llm_responses_inserts_rows(pg_store, sample_signal):
    """log_llm_responses inserts one row per ModelOutput."""
    from src.llm.ensemble import ModelOutput
    signal_id = pg_store.write_signal(sample_signal)
    outputs = [
        ModelOutput(symbol="AAPL", polarity=0.7, confidence=0.85,
                    reasoning="Positive earnings.", model_id="opus"),
        ModelOutput(symbol="AAPL", polarity=0.6, confidence=0.80,
                    reasoning="Beat estimates.", model_id="qwen3.5:cloud"),
    ]
    pg_store.log_llm_responses(signal_id=signal_id, outputs=outputs)
    conn = pg_store._get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT model_id FROM llm_responses WHERE signal_id = %s ORDER BY model_id",
                    (signal_id,))
        rows = cur.fetchall()
    assert len(rows) == 2
    assert {r[0] for r in rows} == {"opus", "qwen3.5:cloud"}


def test_log_llm_responses_empty_list_is_noop(pg_store, sample_signal):
    """log_llm_responses with empty list writes nothing and does not raise."""
    signal_id = pg_store.write_signal(sample_signal)
    pg_store.log_llm_responses(signal_id=signal_id, outputs=[])
    conn = pg_store._get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM llm_responses WHERE signal_id = %s", (signal_id,))
        count = cur.fetchone()[0]
    assert count == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/store/test_pg_news_llm.py -v
```

Expected: `AttributeError: 'PostgreSQLStore' object has no attribute 'log_news_item'`.

- [ ] **Step 3: Add write methods to pg_store**

Add to `src/store/pg_store.py` after `write_signal`:

```python
    _INSERT_NEWS_LOG = """
        INSERT INTO news_log (title, url, source, ticker, body_snippet, raw_sentiment, fetched_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
    """

    _INSERT_LLM_RESPONSE = """
        INSERT INTO llm_responses (signal_id, model_id, polarity, confidence, reasoning, eligible, generated_at)
        VALUES (%s, %s, %s, %s, %s, %s, now())
    """

    def log_news_item(self, item: "NewsItem", ticker: str) -> None:
        """Write article metadata to news_log. Skips silently on conflict."""
        from src.models.news import MarketAuxNewsItem
        raw_sentiment = item.raw_sentiment if isinstance(item, MarketAuxNewsItem) else None  # type: ignore[attr-defined]
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    self._INSERT_NEWS_LOG,
                    (
                        item.title[:500] if item.title else "",
                        item.url[:1000] if item.url else "",
                        item.source,
                        ticker,
                        item.body[:500] if item.body else None,
                        raw_sentiment,
                        item.timestamp,
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def log_llm_responses(self, signal_id: int, outputs: "list[ModelOutput]") -> None:
        """Write per-model outputs to llm_responses. No-op for empty list."""
        if not outputs:
            return
        from src.llm.ensemble import ModelOutput  # noqa: F401 (type hint)
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                for out in outputs:
                    cur.execute(
                        self._INSERT_LLM_RESPONSE,
                        (
                            signal_id,
                            out.model_id,
                            out.polarity,
                            out.confidence,
                            out.reasoning,
                            True,
                        ),
                    )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
```

Add the `TYPE_CHECKING` import at top of `pg_store.py` if not present:

```python
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.models.news import NewsItem
    from src.llm.ensemble import ModelOutput
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/store/test_pg_news_llm.py -v
```

Expected: all `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add src/store/pg_store.py tests/store/test_pg_news_llm.py
git commit -m "feat: pg_store — log_news_item and log_llm_responses write methods"
```

---

## Task 4: pg_store — read methods for new tables

**Files:**
- Modify: `src/store/pg_store.py`
- Modify: `tests/store/test_pg_news_llm.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/store/test_pg_news_llm.py`:

```python
def test_get_news_recent_returns_rows(pg_store, sample_news_item):
    """get_news_recent returns a list of dicts with expected keys."""
    pg_store.log_news_item(item=sample_news_item, ticker="AAPL")
    rows = pg_store.get_news_recent(limit=10)
    assert len(rows) >= 1
    first = rows[0]
    assert "title" in first
    assert "ticker" in first
    assert "source" in first
    assert "fetched_at" in first


def test_get_news_recent_filters_by_ticker(pg_store, sample_news_item):
    """get_news_recent with ticker filter returns only matching rows."""
    pg_store.log_news_item(item=sample_news_item, ticker="AAPL")
    rows = pg_store.get_news_recent(limit=10, ticker="MSFT")
    assert all(r["ticker"] == "MSFT" for r in rows)


def test_get_llm_feedback_returns_rows(pg_store, sample_signal):
    """get_llm_feedback returns rows with model_id and polarity."""
    from src.llm.ensemble import ModelOutput
    signal_id = pg_store.write_signal(sample_signal)
    outputs = [ModelOutput(symbol="AAPL", polarity=0.7, confidence=0.85,
                           reasoning="Good.", model_id="opus")]
    pg_store.log_llm_responses(signal_id=signal_id, outputs=outputs)
    rows = pg_store.get_llm_feedback(limit=10)
    assert len(rows) >= 1
    assert "model_id" in rows[0]
    assert "polarity" in rows[0]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/store/test_pg_news_llm.py::test_get_news_recent_returns_rows \
       tests/store/test_pg_news_llm.py::test_get_llm_feedback_returns_rows -v
```

Expected: `AttributeError: 'PostgreSQLStore' object has no attribute 'get_news_recent'`.

- [ ] **Step 3: Add read methods to pg_store**

Add to `src/store/pg_store.py`:

```python
    def get_news_recent(
        self,
        limit: int = 100,
        ticker: str | None = None,
        source: str | None = None,
    ) -> list[dict]:
        """Return recent news_log rows as dicts, newest first."""
        from datetime import timezone
        filters = []
        params: list = []
        if ticker:
            filters.append("ticker = %s")
            params.append(ticker)
        if source:
            filters.append("source = %s")
            params.append(source)
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        params.append(limit)
        conn = self._get_connection()
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT id, title, url, source, ticker, raw_sentiment, fetched_at "
                f"FROM news_log {where} ORDER BY fetched_at DESC LIMIT %s",
                params,
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def get_llm_feedback(
        self,
        limit: int = 50,
        ticker: str | None = None,
        model_id: str | None = None,
    ) -> list[dict]:
        """Return recent llm_responses joined with sentiment_signals, newest first."""
        filters = []
        params: list = []
        if ticker:
            filters.append("s.symbol = %s")
            params.append(ticker)
        if model_id:
            filters.append("r.model_id = %s")
            params.append(model_id)
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        params.append(limit)
        conn = self._get_connection()
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT r.id, r.signal_id, s.symbol, r.model_id, r.polarity,
                       r.confidence, r.reasoning, r.eligible, r.generated_at,
                       s.fallback_used, s.ensemble_std
                FROM llm_responses r
                JOIN sentiment_signals s ON s.id = r.signal_id
                {where}
                ORDER BY r.generated_at DESC
                LIMIT %s
                """,
                params,
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/store/test_pg_news_llm.py -v
```

Expected: all `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add src/store/pg_store.py tests/store/test_pg_news_llm.py
git commit -m "feat: pg_store — get_news_recent and get_llm_feedback read methods"
```

---

## Task 5: sentiment.py — run_inference returns raw outputs + process_news_item logs them

**Files:**
- Modify: `src/workers/sentiment.py`
- Modify: `scripts/run_backtest.py`
- Modify: `tests/workers/test_sentiment_worker.py`

- [ ] **Step 1: Update existing tests for new return type**

In `tests/workers/test_sentiment_worker.py`, find all `result = await run_inference(...)` calls and change them to unpack the tuple. Example:

```python
# Before
result = await run_inference(item, clients, aggregator, finbert, budget_tracker)
assert result.symbol == "AAPL"

# After
result, raw_outputs = await run_inference(item, clients, aggregator, finbert, budget_tracker)
assert result.symbol == "AAPL"
```

Add new assertions to verify raw_outputs is returned:

```python
# In test_run_inference_ensemble_success:
result, raw_outputs = await run_inference(...)
assert result is not None
assert isinstance(raw_outputs, list)
assert len(raw_outputs) > 0
assert raw_outputs[0].model_id is not None

# In test_run_inference_divergence_uses_finbert:
result, raw_outputs = await run_inference(...)
assert result.model_id == "finbert"
assert raw_outputs == []  # no outputs on fallback
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/workers/test_sentiment_worker.py -v -k "run_inference"
```

Expected: `FAILED — cannot unpack non-iterable SentimentResult`.

- [ ] **Step 3: Update run_inference to return tuple**

In `src/workers/sentiment.py`, change the function signature and all return statements:

```python
from src.llm.ensemble import ModelOutput  # add this import at top

async def run_inference(
    item: NewsItem,
    clients: list[LLMClient],
    aggregator: EnsembleAggregator,
    finbert: FinBERTClient,
    budget_tracker: LLMBudgetTracker,
) -> tuple[SentimentResult, list[ModelOutput]] | None:
```

Change the FinBERT fallback returns (two locations) to include empty list:

```python
# Divergence fallback
return SentimentResult(
    symbol=symbol,
    score=fb_result.polarity * fb_result.confidence,
    confidence=fb_result.confidence,
    reasoning="FinBERT fallback (ensemble divergence)",
    model_id="finbert",
    fallback_used=True,
), []

# Budget fallback
return SentimentResult(
    symbol=symbol,
    score=fb_result.polarity * fb_result.confidence,
    confidence=fb_result.confidence,
    reasoning="FinBERT fallback (budget exhausted)",
    model_id="finbert",
    fallback_used=True,
), []
```

Change the success return to include raw_outputs:

```python
        return SentimentResult(
            symbol=symbol,
            score=max(-1.0, min(1.0, score)),
            confidence=aggregated.confidence,
            reasoning=aggregated.reasoning,
            model_id=f"ensemble:{'+'.join(aggregated.model_ids)}",
            ensemble_std=aggregated.ensemble_std,
            fallback_used=False,
        ), raw_outputs
```

Change the exception return:

```python
    except Exception as e:
        log.error(f"Error processing news item for {symbol}: {e}")
        return None
```

(This stays as `None` — callers already handle `None`.)

- [ ] **Step 4: Run sentiment tests to verify they pass**

```bash
pytest tests/workers/test_sentiment_worker.py -v
```

Expected: all `PASSED`.

- [ ] **Step 5: Update process_news_item to log news + LLM responses**

In `src/workers/sentiment.py`, update `process_news_item`:

```python
async def process_news_item(
    item: NewsItem,
    redis_store: RedisStore,
    pg_store: PostgreSQLStore,
    clients: list[LLMClient],
    aggregator: EnsembleAggregator,
    finbert: FinBERTClient,
    budget_tracker: LLMBudgetTracker,
) -> None:
    inference_result = await run_inference(item, clients, aggregator, finbert, budget_tracker)
    if inference_result is None:
        return
    result, raw_outputs = inference_result
    try:
        ticker = result.symbol
        redis_store.write_sentiment(result)
        signal_id = pg_store.write_signal(result)
        pg_store.log_news_item(item=item, ticker=ticker)
        if raw_outputs:
            pg_store.log_llm_responses(signal_id=signal_id, outputs=raw_outputs)
    except Exception as e:
        log.error(f"Failed to write signal for {result.symbol}: {e}")
```

- [ ] **Step 6: Update run_backtest.py call site**

In `scripts/run_backtest.py`, find the `run_inference` call (line ~199) and unpack:

```python
# Before
result = await asyncio.ensure_future(
    run_inference(item, clients, aggregator, finbert, budget_tracker)
)

# After
inference_result = await asyncio.ensure_future(
    run_inference(item, clients, aggregator, finbert, budget_tracker)
)
result = inference_result[0] if inference_result is not None else None
```

- [ ] **Step 7: Run full test suite**

```bash
pytest tests/ -v --tb=short -q
```

Expected: all green (594+ tests pass).

- [ ] **Step 8: Commit**

```bash
git add src/workers/sentiment.py scripts/run_backtest.py tests/workers/test_sentiment_worker.py
git commit -m "feat: sentiment pipeline logs news_log + llm_responses after scoring"
```

---

## Task 6: Retention worker

**Files:**
- Create: `src/workers/retention.py`
- Create: `tests/workers/test_retention.py`
- Modify: `src/workers/celery_app.py`
- Modify: `config/trading.yaml`

- [ ] **Step 1: Add retention config to trading.yaml**

```yaml
retention:
  news_log_days: 180      # delete news_log rows older than N days
  llm_responses_days: 365 # delete llm_responses rows older than N days
```

- [ ] **Step 2: Add pg_store delete methods**

Add to `src/store/pg_store.py`:

```python
    def delete_old_news_log(self, older_than_days: int) -> int:
        """Delete news_log rows older than given days. Returns deleted count."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM news_log WHERE fetched_at < now() - (%s || ' days')::interval",
                    (str(older_than_days),),
                )
                deleted = cur.rowcount
            conn.commit()
            return deleted
        except Exception:
            conn.rollback()
            raise

    def delete_old_llm_responses(self, older_than_days: int) -> int:
        """Delete llm_responses rows older than given days. Returns deleted count."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM llm_responses WHERE generated_at < now() - (%s || ' days')::interval",
                    (str(older_than_days),),
                )
                deleted = cur.rowcount
            conn.commit()
            return deleted
        except Exception:
            conn.rollback()
            raise
```

- [ ] **Step 3: Write failing tests**

```python
# tests/workers/test_retention.py
import pytest
from unittest.mock import MagicMock, patch
from src.workers.retention import run_retention_sweep


def test_retention_sweep_calls_delete_methods():
    """run_retention_sweep calls both delete methods with configured thresholds."""
    mock_pg = MagicMock()
    mock_pg.delete_old_news_log.return_value = 42
    mock_pg.delete_old_llm_responses.return_value = 100

    with patch("src.workers.retention.PostgreSQLStore", return_value=mock_pg), \
         patch("src.workers.retention.psycopg2.connect"), \
         patch("src.workers.retention.config") as mock_cfg:
        mock_cfg.DATABASE_URL = "postgresql://test"
        result = run_retention_sweep()

    mock_pg.delete_old_news_log.assert_called_once()
    mock_pg.delete_old_llm_responses.assert_called_once()
    assert result["deleted_news_log"] == 42
    assert result["deleted_llm_responses"] == 100


def test_retention_sweep_returns_stats():
    """run_retention_sweep returns a stats dict with deleted counts."""
    mock_pg = MagicMock()
    mock_pg.delete_old_news_log.return_value = 0
    mock_pg.delete_old_llm_responses.return_value = 0

    with patch("src.workers.retention.PostgreSQLStore", return_value=mock_pg), \
         patch("src.workers.retention.psycopg2.connect"), \
         patch("src.workers.retention.config") as mock_cfg:
        mock_cfg.DATABASE_URL = "postgresql://test"
        result = run_retention_sweep()

    assert "deleted_news_log" in result
    assert "deleted_llm_responses" in result
```

- [ ] **Step 4: Run tests to verify they fail**

```bash
pytest tests/workers/test_retention.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.workers.retention'`.

- [ ] **Step 5: Create retention worker**

```python
# src/workers/retention.py
"""Nightly sweep to delete old rows from news_log and llm_responses.

Runs daily at 03:30 UTC via Celery beat. Default thresholds from config/trading.yaml:
  - news_log: 180 days
  - llm_responses: 365 days
"""
import logging

import psycopg2

from src.config import config
from src.store.pg_store import PostgreSQLStore
from src.workers.celery_app import app

log = logging.getLogger(__name__)

_DEFAULT_NEWS_DAYS = 180
_DEFAULT_LLM_DAYS = 365


@app.task(name="src.workers.retention.run_retention_sweep")
def run_retention_sweep() -> dict:
    """Delete old rows from news_log and llm_responses. Returns deleted counts."""
    trading_cfg = _load_retention_config()
    news_days = trading_cfg.get("news_log_days", _DEFAULT_NEWS_DAYS)
    llm_days = trading_cfg.get("llm_responses_days", _DEFAULT_LLM_DAYS)

    pg_conn = psycopg2.connect(config.DATABASE_URL)
    pg_store = PostgreSQLStore(conn=pg_conn)
    try:
        deleted_news = pg_store.delete_old_news_log(older_than_days=news_days)
        deleted_llm = pg_store.delete_old_llm_responses(older_than_days=llm_days)
        log.info(
            "Retention sweep complete: deleted %d news_log rows (>%dd), "
            "%d llm_responses rows (>%dd)",
            deleted_news, news_days, deleted_llm, llm_days,
        )
        return {"deleted_news_log": deleted_news, "deleted_llm_responses": deleted_llm}
    finally:
        pg_store.close()


def _load_retention_config() -> dict:
    try:
        import yaml
        with open("config/trading.yaml") as f:
            return yaml.safe_load(f).get("retention", {})
    except Exception:
        return {}
```

- [ ] **Step 6: Add retention beat entry to celery_app.py**

In `src/workers/celery_app.py`, add to `beat_schedule`:

```python
    "run-retention-sweep": {
        "task": "src.workers.retention.run_retention_sweep",
        "schedule": crontab(hour=3, minute=30),
    },
```

- [ ] **Step 7: Run retention tests**

```bash
pytest tests/workers/test_retention.py -v
```

Expected: all `PASSED`.

- [ ] **Step 8: Commit**

```bash
git add src/workers/retention.py src/workers/celery_app.py src/store/pg_store.py \
        config/trading.yaml tests/workers/test_retention.py
git commit -m "feat: nightly retention sweep for news_log and llm_responses"
```

---

## Task 7: Alpaca dependency + /api/positions + /api/orders

**Files:**
- Modify: `src/api/deps.py`
- Create: `src/api/routes/trading.py`
- Create: `tests/api/test_trading_routes.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/api/test_trading_routes.py
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from src.api.main import app


def _mock_alpaca_client(positions=None, orders=None):
    client = MagicMock()
    client.get_all_positions.return_value = positions or []
    client.get_orders.return_value = orders or []
    return client


def test_get_positions_returns_list():
    """GET /api/positions returns a list of positions."""
    mock_pos = MagicMock()
    mock_pos.symbol = "AAPL"
    mock_pos.qty = "10"
    mock_pos.market_value = "1820.50"
    mock_pos.unrealized_pl = "45.20"
    mock_pos.unrealized_plpc = "0.0254"
    mock_pos.avg_entry_price = "177.53"
    mock_pos.current_price = "182.05"

    client = _mock_alpaca_client(positions=[mock_pos])
    with patch("src.api.routes.trading.get_alpaca_trading_client", return_value=client):
        tc = TestClient(app)
        resp = tc.get("/api/positions")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["symbol"] == "AAPL"
    assert "unrealized_pl" in data[0]


def test_get_orders_returns_list():
    """GET /api/orders returns a list of orders."""
    mock_order = MagicMock()
    mock_order.id = "abc-123"
    mock_order.symbol = "AAPL"
    mock_order.side.value = "buy"
    mock_order.qty = "10"
    mock_order.filled_avg_price = "177.53"
    mock_order.status.value = "filled"
    mock_order.filled_at = None
    mock_order.submitted_at = None

    client = _mock_alpaca_client(orders=[mock_order])
    with patch("src.api.routes.trading.get_alpaca_trading_client", return_value=client):
        tc = TestClient(app)
        resp = tc.get("/api/orders")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["symbol"] == "AAPL"
    assert data[0]["side"] == "buy"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/api/test_trading_routes.py -v
```

Expected: `404 Not Found` for both endpoints.

- [ ] **Step 3: Add get_alpaca_trading_client to deps.py**

```python
# Add to src/api/deps.py

def get_alpaca_trading_client():
    """FastAPI dependency: Alpaca TradingClient from app config."""
    from alpaca.trading.client import TradingClient
    from src.config import config
    return TradingClient(
        api_key=config.ALPACA_API_KEY,
        secret_key=config.ALPACA_SECRET_KEY,
        paper=config.ALPACA_BASE_URL.startswith("https://paper"),
    )
```

- [ ] **Step 4: Create trading routes**

```python
# src/api/routes/trading.py
"""Alpaca positions and order history endpoints."""
from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.deps import get_alpaca_trading_client

router = APIRouter(prefix="/api")


@router.get("/positions")
def get_positions(
    client: Annotated[object, Depends(get_alpaca_trading_client)],
) -> list[dict]:
    """Return all open positions from Alpaca."""
    positions = client.get_all_positions()
    return [
        {
            "symbol": p.symbol,
            "qty": str(p.qty),
            "market_value": str(p.market_value),
            "unrealized_pl": str(p.unrealized_pl),
            "unrealized_plpc": str(p.unrealized_plpc),
            "avg_entry_price": str(p.avg_entry_price),
            "current_price": str(p.current_price),
        }
        for p in positions
    ]


@router.get("/orders")
def get_orders(
    client: Annotated[object, Depends(get_alpaca_trading_client)],
    limit: int = 50,
) -> list[dict]:
    """Return order history from Alpaca (filled + cancelled)."""
    from alpaca.trading.requests import GetOrdersRequest
    from alpaca.trading.enums import QueryOrderStatus
    orders = client.get_orders(GetOrdersRequest(
        status=QueryOrderStatus.ALL,
        limit=min(limit, 500),
    ))
    return [
        {
            "id": str(o.id),
            "symbol": o.symbol,
            "side": o.side.value,
            "qty": str(o.qty),
            "filled_avg_price": str(o.filled_avg_price) if o.filled_avg_price else None,
            "status": o.status.value,
            "filled_at": o.filled_at.isoformat() if o.filled_at else None,
            "submitted_at": o.submitted_at.isoformat() if o.submitted_at else None,
        }
        for o in orders
    ]
```

- [ ] **Step 5: Update tests to use dependency_overrides (not patch)**

Replace the test bodies in `tests/api/test_trading_routes.py` to use FastAPI's DI override — consistent with other API tests in this codebase:

```python
# tests/api/test_trading_routes.py
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from src.api.main import app
from src.api.deps import get_alpaca_trading_client


def test_get_positions_returns_list():
    """GET /api/positions returns a list of positions."""
    mock_pos = MagicMock()
    mock_pos.symbol = "AAPL"
    mock_pos.qty = "10"
    mock_pos.market_value = "1820.50"
    mock_pos.unrealized_pl = "45.20"
    mock_pos.unrealized_plpc = "0.0254"
    mock_pos.avg_entry_price = "177.53"
    mock_pos.current_price = "182.05"

    mock_client = MagicMock()
    mock_client.get_all_positions.return_value = [mock_pos]
    app.dependency_overrides[get_alpaca_trading_client] = lambda: mock_client

    tc = TestClient(app)
    resp = tc.get("/api/positions")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["symbol"] == "AAPL"
    assert "unrealized_pl" in data[0]


def test_get_orders_returns_list():
    """GET /api/orders returns a list of orders."""
    mock_order = MagicMock()
    mock_order.id = "abc-123"
    mock_order.symbol = "AAPL"
    mock_order.side.value = "buy"
    mock_order.qty = "10"
    mock_order.filled_avg_price = "177.53"
    mock_order.status.value = "filled"
    mock_order.filled_at = None
    mock_order.submitted_at = None

    mock_client = MagicMock()
    mock_client.get_orders.return_value = [mock_order]
    app.dependency_overrides[get_alpaca_trading_client] = lambda: mock_client

    tc = TestClient(app)
    resp = tc.get("/api/orders")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["symbol"] == "AAPL"
    assert data[0]["side"] == "buy"
```

- [ ] **Step 6: Register router in main.py**

In `src/api/main.py`, add:

```python
from src.api.routes import admin, performance, signals, trading  # add trading

app.include_router(trading.router)
```

- [ ] **Step 7: Run tests**

```bash
pytest tests/api/test_trading_routes.py -v
```

Expected: all `PASSED`.

- [ ] **Step 8: Commit**

```bash
git add src/api/deps.py src/api/routes/trading.py src/api/main.py \
        tests/api/test_trading_routes.py
git commit -m "feat: /api/positions and /api/orders endpoints (Alpaca)"
```

---

## Task 8: /api/news/recent and /api/llm/feedback

**Files:**
- Create: `src/api/routes/news_routes.py`
- Create: `src/api/routes/llm_routes.py`
- Create: `tests/api/test_news_routes.py`
- Create: `tests/api/test_llm_routes.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/api/test_news_routes.py
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from src.api.main import app
from src.api.deps import get_pg_store


def test_get_news_recent_returns_list():
    """GET /api/news/recent returns a list."""
    mock_pg = MagicMock()
    mock_pg.get_news_recent.return_value = [
        {"id": 1, "title": "AAPL beats Q3", "ticker": "AAPL",
         "source": "gdelt_gkg", "fetched_at": "2026-05-18T14:00:00+00:00"}
    ]
    app.dependency_overrides[get_pg_store] = lambda: mock_pg
    tc = TestClient(app)
    resp = tc.get("/api/news/recent")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["ticker"] == "AAPL"


def test_get_news_recent_passes_ticker_filter():
    """GET /api/news/recent?ticker=MSFT passes filter to pg_store."""
    mock_pg = MagicMock()
    mock_pg.get_news_recent.return_value = []
    app.dependency_overrides[get_pg_store] = lambda: mock_pg
    tc = TestClient(app)
    tc.get("/api/news/recent?ticker=MSFT&limit=20")
    app.dependency_overrides.clear()
    mock_pg.get_news_recent.assert_called_once_with(limit=20, ticker="MSFT", source=None)
```

```python
# tests/api/test_llm_routes.py
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from src.api.main import app
from src.api.deps import get_pg_store


def test_get_llm_feedback_returns_list():
    """GET /api/llm/feedback returns a list."""
    mock_pg = MagicMock()
    mock_pg.get_llm_feedback.return_value = [
        {"id": 1, "symbol": "AAPL", "model_id": "opus",
         "polarity": 0.7, "confidence": 0.85, "reasoning": "Good."}
    ]
    app.dependency_overrides[get_pg_store] = lambda: mock_pg
    tc = TestClient(app)
    resp = tc.get("/api/llm/feedback")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()[0]["model_id"] == "opus"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/api/test_news_routes.py tests/api/test_llm_routes.py -v
```

Expected: `404 Not Found`.

- [ ] **Step 3: Create news_routes.py**

```python
# src/api/routes/news_routes.py
"""News log endpoint."""
from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.deps import get_pg_store
from src.store.pg_store import PostgreSQLStore

router = APIRouter(prefix="/api/news")


@router.get("/recent")
def get_news_recent(
    pg: Annotated[PostgreSQLStore, Depends(get_pg_store)],
    limit: int = 100,
    ticker: str | None = None,
    source: str | None = None,
) -> list[dict]:
    """Return recent news articles processed by the sentiment pipeline."""
    return pg.get_news_recent(limit=min(limit, 500), ticker=ticker, source=source)
```

- [ ] **Step 4: Create llm_routes.py**

```python
# src/api/routes/llm_routes.py
"""LLM per-model response endpoint."""
from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.deps import get_pg_store
from src.store.pg_store import PostgreSQLStore

router = APIRouter(prefix="/api/llm")


@router.get("/feedback")
def get_llm_feedback(
    pg: Annotated[PostgreSQLStore, Depends(get_pg_store)],
    limit: int = 50,
    ticker: str | None = None,
    model_id: str | None = None,
) -> list[dict]:
    """Return per-model LLM outputs for processed articles."""
    return pg.get_llm_feedback(limit=min(limit, 200), ticker=ticker, model_id=model_id)
```

- [ ] **Step 5: Register routers in main.py**

```python
from src.api.routes import admin, llm_routes, news_routes, performance, signals, trading

app.include_router(news_routes.router)
app.include_router(llm_routes.router)
```

- [ ] **Step 6: Run tests**

```bash
pytest tests/api/test_news_routes.py tests/api/test_llm_routes.py -v
```

Expected: all `PASSED`.

- [ ] **Step 7: Commit**

```bash
git add src/api/routes/news_routes.py src/api/routes/llm_routes.py \
        src/api/main.py tests/api/test_news_routes.py tests/api/test_llm_routes.py
git commit -m "feat: /api/news/recent and /api/llm/feedback endpoints"
```

---

## Task 9: /api/performance/pnl

**Files:**
- Modify: `src/api/routes/performance.py`
- Modify: `tests/api/test_performance_routes.py` (existing or create)

- [ ] **Step 1: Write failing test**

```python
# Add to tests/api/ (create test_performance_pnl.py if needed)
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from src.api.main import app


def test_get_pnl_returns_monthly_list():
    """GET /api/performance/pnl returns monthly and cumulative P&L."""
    mock_history = MagicMock()
    mock_history.timestamp = [1700000000, 1702678400, 1705356800]
    mock_history.equity = [100000.0, 101500.0, 103200.0]
    mock_history.profit_loss = [0.0, 1500.0, 1700.0]

    mock_client = MagicMock()
    mock_client.get_portfolio_history.return_value = mock_history

    with patch("src.api.routes.performance.get_alpaca_trading_client",
               return_value=mock_client):
        tc = TestClient(app)
        resp = tc.get("/api/performance/pnl")

    assert resp.status_code == 200
    data = resp.json()
    assert "monthly" in data
    assert "daily" in data
    assert isinstance(data["monthly"], list)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/api/test_performance_pnl.py -v
```

Expected: `404 Not Found`.

- [ ] **Step 3: Add /api/performance/pnl to performance.py**

Add to `src/api/routes/performance.py`:

```python
from src.api.deps import get_alpaca_trading_client  # add import

@router.get("/performance/pnl")
def get_pnl(
    client: Annotated[object, Depends(get_alpaca_trading_client)],
    period: str = "6M",
) -> dict:
    """Return portfolio P&L history from Alpaca (daily + monthly aggregate)."""
    from alpaca.trading.requests import GetPortfolioHistoryRequest
    from collections import defaultdict
    from datetime import datetime, timezone

    history = client.get_portfolio_history(
        GetPortfolioHistoryRequest(period=period, timeframe="1D")
    )

    daily = []
    monthly: dict[str, float] = defaultdict(float)

    timestamps = history.timestamp or []
    profit_loss = history.profit_loss or []
    equities = history.equity or []

    for ts, pl, eq in zip(timestamps, profit_loss, equities):
        if ts is None:
            continue
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        date_str = dt.strftime("%Y-%m-%d")
        month_str = dt.strftime("%Y-%m")
        daily.append({"date": date_str, "equity": eq, "profit_loss": pl or 0.0})
        monthly[month_str] += pl or 0.0

    return {
        "daily": daily,
        "monthly": [{"month": k, "pnl": round(v, 2)} for k, v in sorted(monthly.items())],
    }
```

- [ ] **Step 4: Run test**

```bash
pytest tests/api/test_performance_pnl.py -v
```

Expected: `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add src/api/routes/performance.py tests/api/test_performance_pnl.py
git commit -m "feat: /api/performance/pnl endpoint (Alpaca portfolio history)"
```

---

## Task 10: /api/config GET + POST

**Files:**
- Create: `src/api/routes/config_routes.py`
- Create: `tests/api/test_config_routes.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/api/test_config_routes.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import mock_open, patch
from src.api.main import app

_SAMPLE_YAML = """
symbols:
  watchlist:
    - AAPL
    - MSFT
risk:
  portfolio_drawdown: 0.05
"""


def test_get_config_returns_yaml_as_dict():
    """GET /api/config returns trading.yaml as a dict."""
    with patch("builtins.open", mock_open(read_data=_SAMPLE_YAML)):
        tc = TestClient(app)
        resp = tc.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "symbols" in data
    assert "AAPL" in data["symbols"]["watchlist"]


def test_post_config_requires_api_key():
    """POST /api/config without API key returns 403."""
    tc = TestClient(app)
    resp = tc.post("/api/config", json={"symbols": {"watchlist": ["AAPL"]}})
    assert resp.status_code == 403


def test_post_config_updates_watchlist(tmp_path):
    """POST /api/config with API key updates config/trading.yaml."""
    import os
    yaml_file = tmp_path / "trading.yaml"
    yaml_file.write_text(_SAMPLE_YAML)

    with patch("src.api.routes.config_routes._CONFIG_PATH", str(yaml_file)), \
         patch.dict(os.environ, {"ADMIN_API_KEY": "test-key"}):
        tc = TestClient(app)
        resp = tc.post(
            "/api/config",
            json={"symbols": {"watchlist": ["AAPL", "MSFT", "NVDA"]}},
            headers={"X-API-Key": "test-key"},
        )
    assert resp.status_code == 200
    assert "NVDA" in yaml_file.read_text()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/api/test_config_routes.py -v
```

Expected: `404 Not Found` for GET, `404` for POST.

- [ ] **Step 3: Create config_routes.py**

```python
# src/api/routes/config_routes.py
"""Runtime config read/write via config/trading.yaml."""
from typing import Annotated

import yaml
from fastapi import APIRouter, Depends, HTTPException

from src.api.auth import require_api_key

router = APIRouter(prefix="/api")

_CONFIG_PATH = "config/trading.yaml"


def _read_config() -> dict:
    try:
        with open(_CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="config/trading.yaml not found")


@router.get("/config")
def get_config() -> dict:
    """Return the current trading.yaml as a JSON object."""
    return _read_config()


@router.post("/config")
def update_config(
    updates: dict,
    api_key: Annotated[str, Depends(require_api_key)],
) -> dict:
    """Merge updates into trading.yaml and persist. Requires API key.

    Only top-level keys present in updates are changed; other keys are preserved.
    The running Celery workers read config at task start, so changes take effect
    on the next task invocation without a restart.
    """
    current = _read_config()
    _deep_merge(current, updates)
    with open(_CONFIG_PATH, "w") as f:
        yaml.dump(current, f, default_flow_style=False, allow_unicode=True)
    return current


def _deep_merge(base: dict, updates: dict) -> None:
    """Recursively merge updates into base in place."""
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
```

- [ ] **Step 4: Register router in main.py**

```python
from src.api.routes import admin, config_routes, llm_routes, news_routes, performance, signals, trading

app.include_router(config_routes.router)
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/api/test_config_routes.py -v
```

Expected: all `PASSED`.

- [ ] **Step 6: Run full test suite to confirm no regressions**

```bash
pytest tests/ -q --tb=short
```

Expected: all green.

- [ ] **Step 7: Final commit**

```bash
git add src/api/routes/config_routes.py src/api/main.py tests/api/test_config_routes.py
git commit -m "feat: /api/config GET+POST endpoint (trading.yaml read/write)"
```

---

## Plan B (next document)

After this plan is fully implemented and all tests pass, the Frontend SPA plan (`2026-05-18-frontend-spa.md`) can begin. It depends on all endpoints from this plan being available.
