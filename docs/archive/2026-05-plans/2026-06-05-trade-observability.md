# Trade Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add end-to-end traceability from news article → sentiment signal → execution decision → order → P&L, plus commission-erosion analysis in the weekly report and a Trades UI page.

**Architecture:** Three DB tables (`news_log_id` FK on `sentiment_signals`, `execution_decisions`, `trades`) written synchronously alongside existing logic. Alpaca remains source of truth for fill prices; own DB holds decisional context. Execution worker gains `pg_store` optional param so tests need no DB.

**Tech Stack:** PostgreSQL (psycopg2), FastAPI, Celery, Redis, React + React Query + recharts, Alpaca SDK.

---

### Task 1: SQL Migration 016

**Files:**
- Create: `migrations/016_trade_observability.sql`

- [ ] **Step 1: Write the migration file**

```sql
-- migrations/016_trade_observability.sql

-- 1a. Link sentiment_signals to the news article that triggered them
ALTER TABLE sentiment_signals
    ADD COLUMN IF NOT EXISTS news_log_id BIGINT
        REFERENCES news_log(id) ON DELETE SET NULL;

-- 1b. Execution decision log (one row per symbol per tick, score > threshold only)
CREATE TABLE IF NOT EXISTS execution_decisions (
    id           BIGSERIAL PRIMARY KEY,
    tick_time    TIMESTAMPTZ NOT NULL,
    symbol       VARCHAR(20) NOT NULL,
    signal_id    BIGINT REFERENCES sentiment_signals(id) ON DELETE SET NULL,
    score        DOUBLE PRECISION NOT NULL,
    regime_mult  DOUBLE PRECISION NOT NULL,
    ema_pass     BOOLEAN NOT NULL,
    decision     VARCHAR(20) NOT NULL,
    order_id     TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_execution_decisions_tick
    ON execution_decisions (tick_time DESC);
CREATE INDEX IF NOT EXISTS idx_execution_decisions_symbol
    ON execution_decisions (symbol, tick_time DESC);

-- 1c. Per-trade P&L tracking
CREATE TABLE IF NOT EXISTS trades (
    id               BIGSERIAL PRIMARY KEY,
    symbol           VARCHAR(20) NOT NULL,
    signal_id        BIGINT REFERENCES sentiment_signals(id) ON DELETE SET NULL,
    decision_id      BIGINT REFERENCES execution_decisions(id) ON DELETE SET NULL,
    entry_order_id   TEXT NOT NULL,
    entry_price      DOUBLE PRECISION,
    entry_time       TIMESTAMPTZ NOT NULL,
    entry_notional   DOUBLE PRECISION NOT NULL,
    score            DOUBLE PRECISION NOT NULL,
    regime_mult      DOUBLE PRECISION NOT NULL,
    exit_order_id    TEXT,
    exit_price       DOUBLE PRECISION,
    exit_time        TIMESTAMPTZ,
    exit_reason      VARCHAR(20),
    qty              DOUBLE PRECISION,
    gross_pnl        DOUBLE PRECISION,
    slippage_est     DOUBLE PRECISION,
    net_pnl          DOUBLE PRECISION,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_trades_symbol
    ON trades (symbol, entry_time DESC);
CREATE INDEX IF NOT EXISTS idx_trades_open
    ON trades (symbol) WHERE exit_time IS NULL;
CREATE INDEX IF NOT EXISTS idx_trades_closed
    ON trades (exit_time DESC) WHERE exit_time IS NOT NULL;
```

- [ ] **Step 2: Verify the file is syntactically valid**

```bash
psql $DATABASE_URL -f migrations/016_trade_observability.sql
```

Expected: no errors. (Requires a running DB. If unavailable, review the SQL manually — all statements use `IF NOT EXISTS`.)

- [ ] **Step 3: Commit**

```bash
git add migrations/016_trade_observability.sql
git commit -m "feat(migrations): 016 — trade observability schema (decisions + trades tables, news_log_id FK)"
```

---

### Task 2: pg_store — log_news_item returns id + link_signal_to_news

**Files:**
- Modify: `src/store/pg_store.py` (lines 164–217)
- Test: `tests/test_pg_store.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pg_store.py`:

```python
class TestLogNewsItemReturnsId:
    """log_news_item must return the inserted row id (RETURNING id)."""

    def test_log_news_item_returns_int_on_insert(self):
        """When INSERT succeeds (not a conflict), returns the new id."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = (42,)

        store = PostgreSQLStore(conn=mock_conn)
        from src.models.news import NewsItem
        item = NewsItem(
            title="Test", url="http://example.com", source="gdelt",
            body="body", asset_tags=["AAPL"],
            timestamp=__import__('datetime').datetime(2026, 6, 1, tzinfo=__import__('datetime').timezone.utc),
        )
        result = store.log_news_item(item=item, ticker="AAPL", computed_sentiment=0.5)
        assert result == 42

    def test_log_news_item_returns_none_on_conflict(self):
        """ON CONFLICT DO NOTHING returns no row; method returns None."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = None  # DO NOTHING yields no row

        store = PostgreSQLStore(conn=mock_conn)
        from src.models.news import NewsItem
        item = NewsItem(
            title="Test", url="http://example.com", source="gdelt",
            body="body", asset_tags=["AAPL"],
            timestamp=__import__('datetime').datetime(2026, 6, 1, tzinfo=__import__('datetime').timezone.utc),
        )
        result = store.log_news_item(item=item, ticker="AAPL")
        assert result is None


class TestLinkSignalToNews:
    """link_signal_to_news issues UPDATE sentiment_signals SET news_log_id = %s WHERE id = %s."""

    def test_link_issues_update(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        store = PostgreSQLStore(conn=mock_conn)
        store.link_signal_to_news(signal_id=7, news_log_id=42)

        sql_called = mock_cur.execute.call_args[0][0]
        assert "UPDATE sentiment_signals" in sql_called
        assert "news_log_id" in sql_called
        mock_conn.commit.assert_called_once()
```

- [ ] **Step 2: Run to verify failure**

```bash
source .venv/bin/activate && pytest tests/test_pg_store.py::TestLogNewsItemReturnsId tests/test_pg_store.py::TestLinkSignalToNews -v
```

Expected: `FAILED` — `log_news_item` returns `None`, `link_signal_to_news` doesn't exist.

- [ ] **Step 3: Implement the changes in pg_store.py**

Change `_INSERT_NEWS_LOG` (line 164) to add `RETURNING id`:

```python
    _INSERT_NEWS_LOG = """
        INSERT INTO news_log (title, url, source, ticker, body_snippet, raw_sentiment, fetched_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (url, ticker) DO NOTHING
        RETURNING id
    """
```

Change `log_news_item` return type from `None` to `int | None`:

```python
    def log_news_item(
        self,
        item: NewsItem,
        ticker: str,
        computed_sentiment: float | None = None,
    ) -> int | None:
        """Write article metadata to news_log. Returns inserted id, or None on conflict."""
        from src.models.news import MarketAuxNewsItem

        if computed_sentiment is not None:
            raw_sentiment = computed_sentiment
        else:
            raw_sentiment = item.marketaux_sentiment if isinstance(item, MarketAuxNewsItem) else None
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
                row = cur.fetchone()
            conn.commit()
            return int(row[0]) if row else None
        except Exception:
            conn.rollback()
            raise
```

Add `_LINK_SIGNAL_TO_NEWS` and `link_signal_to_news` after `log_news_item`:

```python
    _LINK_SIGNAL_TO_NEWS = """
        UPDATE sentiment_signals SET news_log_id = %s WHERE id = %s
    """

    def link_signal_to_news(self, signal_id: int, news_log_id: int) -> None:
        """Set news_log_id on an already-written sentiment_signals row."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(self._LINK_SIGNAL_TO_NEWS, (news_log_id, signal_id))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_pg_store.py::TestLogNewsItemReturnsId tests/test_pg_store.py::TestLinkSignalToNews -v
```

Expected: all PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/store/pg_store.py tests/test_pg_store.py
git commit -m "feat(pg_store): log_news_item returns int|None; add link_signal_to_news"
```

---

### Task 3: write_sentiment includes signal_id in Redis payload

**Files:**
- Modify: `src/store/redis_store.py` (lines 84–99)
- Test: `tests/test_redis_store.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_redis_store.py`:

```python
class TestWriteSentimentSignalId:
    """write_sentiment(result, signal_id=N) must embed signal_id in the Redis value."""

    def test_write_sentiment_includes_signal_id(self):
        import json
        from unittest.mock import MagicMock
        from src.store.redis_store import RedisStore
        from src.models.signals import SentimentResult
        from datetime import datetime, timezone

        mock_redis = MagicMock()
        store = RedisStore(redis_client=mock_redis)

        result = SentimentResult(
            symbol="AAPL", score=0.5, confidence=0.8,
            reasoning="bullish", model_id="ensemble:glm",
            generated_at=datetime(2026, 6, 5, 12, tzinfo=timezone.utc),
        )
        store.write_sentiment(result, signal_id=99)

        _, args, _ = mock_redis.setex.mock_calls[0]
        payload = json.loads(args[2])
        assert payload["signal_id"] == 99

    def test_write_sentiment_without_signal_id_omits_key(self):
        import json
        from unittest.mock import MagicMock
        from src.store.redis_store import RedisStore
        from src.models.signals import SentimentResult
        from datetime import datetime, timezone

        mock_redis = MagicMock()
        store = RedisStore(redis_client=mock_redis)

        result = SentimentResult(
            symbol="MSFT", score=0.3, confidence=0.7,
            reasoning="ok", model_id="finbert",
            generated_at=datetime(2026, 6, 5, 12, tzinfo=timezone.utc),
        )
        store.write_sentiment(result)

        _, args, _ = mock_redis.setex.mock_calls[0]
        payload = json.loads(args[2])
        assert "signal_id" not in payload
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_redis_store.py::TestWriteSentimentSignalId -v
```

Expected: FAILED — `write_sentiment` doesn't accept `signal_id` param.

- [ ] **Step 3: Implement**

Replace `write_sentiment` in `src/store/redis_store.py`:

```python
    def write_sentiment(self, result: SentimentResult, signal_id: int | None = None) -> None:
        """Write sentiment signal to Redis cache.

        Args:
            result:    Sentiment result to cache.
            signal_id: DB row id from pg_store.write_signal(), embedded in the payload
                       so the execution worker can read it without a DB round-trip.
        """
        import json

        key = f"signal:{result.symbol}:sentiment"
        payload = json.loads(result.model_dump_json())
        if signal_id is not None:
            payload["signal_id"] = signal_id
        try:
            self._r.setex(key, self._signal_ttl, json.dumps(payload))
        except Exception as e:
            error_msg = str(e)
            if "OOM" in error_msg or "out of memory" in error_msg.lower():
                print(f"RedisStore: Redis OOM - dropping sentiment signal for {result.symbol}")
            else:
                raise
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_redis_store.py::TestWriteSentimentSignalId -v
```

Expected: PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/store/redis_store.py tests/test_redis_store.py
git commit -m "feat(redis_store): write_sentiment embeds signal_id in Redis payload"
```

---

### Task 4: sentiment.py — wire news_log_id correlation

**Files:**
- Modify: `src/workers/sentiment.py` (lines 159–171, `process_news_item`)
- Test: `tests/workers/test_sentiment_worker.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/workers/test_sentiment_worker.py`:

```python
class TestProcessNewsItemCorrelation:
    """process_news_item must write signal first, then link to news_log row."""

    @pytest.mark.asyncio
    async def test_news_log_id_linked_after_write(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from src.workers.sentiment import process_news_item
        from src.models.signals import SentimentResult
        from src.models.news import NewsItem
        from datetime import datetime, timezone

        item = NewsItem(
            title="T", url="http://u.com", source="gdelt",
            body="b", asset_tags=["AAPL"],
            timestamp=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        result = SentimentResult(
            symbol="AAPL", score=0.6, confidence=0.9,
            reasoning="r", model_id="ensemble:glm",
        )

        mock_pg = MagicMock()
        mock_pg.write_signal.return_value = 7       # signal_id = 7
        mock_pg.log_news_item.return_value = 42     # news_log_id = 42

        mock_redis = MagicMock()
        mock_clients = []
        mock_aggregator = MagicMock()
        mock_finbert = MagicMock()
        mock_budget = MagicMock()
        mock_budget.check_budget = AsyncMock()

        with patch(
            "src.workers.sentiment.run_inference",
            new=AsyncMock(return_value=(result, [])),
        ):
            await process_news_item(
                item=item,
                clients=mock_clients,
                aggregator=mock_aggregator,
                finbert=mock_finbert,
                budget_tracker=mock_budget,
                redis_store=mock_redis,
                pg_store=mock_pg,
            )

        # signal written first
        mock_pg.write_signal.assert_called_once()
        # Redis write called with signal_id=7
        mock_redis.write_sentiment.assert_called_once()
        call_kwargs = mock_redis.write_sentiment.call_args
        assert call_kwargs[1].get("signal_id") == 7 or (
            len(call_kwargs[0]) > 1 and call_kwargs[0][1] == 7
        )
        # news_log_id linked
        mock_pg.link_signal_to_news.assert_called_once_with(signal_id=7, news_log_id=42)

    @pytest.mark.asyncio
    async def test_news_log_conflict_skips_link(self):
        """When log_news_item returns None (duplicate), link_signal_to_news is NOT called."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from src.workers.sentiment import process_news_item
        from src.models.signals import SentimentResult
        from src.models.news import NewsItem
        from datetime import datetime, timezone

        item = NewsItem(
            title="T", url="http://u.com", source="gdelt",
            body="b", asset_tags=["AAPL"],
            timestamp=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        result = SentimentResult(
            symbol="AAPL", score=0.6, confidence=0.9,
            reasoning="r", model_id="ensemble:glm",
        )

        mock_pg = MagicMock()
        mock_pg.write_signal.return_value = 7
        mock_pg.log_news_item.return_value = None   # conflict → no id

        mock_redis = MagicMock()

        with patch(
            "src.workers.sentiment.run_inference",
            new=AsyncMock(return_value=(result, [])),
        ):
            await process_news_item(
                item=item, clients=[], aggregator=MagicMock(),
                finbert=MagicMock(), budget_tracker=MagicMock(),
                redis_store=mock_redis, pg_store=mock_pg,
            )

        mock_pg.link_signal_to_news.assert_not_called()
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/workers/test_sentiment_worker.py::TestProcessNewsItemCorrelation -v
```

Expected: FAILED — `write_sentiment` called without `signal_id`, `link_signal_to_news` not called.

- [ ] **Step 3: Implement**

Replace the `try:` block inside `process_news_item` (lines 159–171 in `src/workers/sentiment.py`):

```python
    try:
        ticker = result.symbol
        if result.fallback_used:
            redis_store.increment_fallback_counter()
        else:
            redis_store.reset_fallback_counter()
        signal_id = pg_store.write_signal(result)
        redis_store.write_sentiment(result, signal_id=signal_id)
        news_log_id = pg_store.log_news_item(item=item, ticker=ticker, computed_sentiment=result.score)
        if news_log_id:
            pg_store.link_signal_to_news(signal_id=signal_id, news_log_id=news_log_id)
        if raw_outputs:
            pg_store.log_llm_responses(signal_id=signal_id, outputs=raw_outputs)
    except Exception as e:
        log.error(f"Failed to write signal for {result.symbol}: {e}")
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/workers/test_sentiment_worker.py::TestProcessNewsItemCorrelation -v
```

Expected: PASSED.

- [ ] **Step 5: Run full sentiment test suite to check for regressions**

```bash
pytest tests/workers/test_sentiment_worker.py -v
```

Expected: all PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/workers/sentiment.py tests/workers/test_sentiment_worker.py
git commit -m "feat(sentiment): wire news_log_id correlation — write_signal first, then link to news_log row"
```

---

### Task 5: pg_store — write_execution_decision + fetch_decisions

**Files:**
- Modify: `src/store/pg_store.py`
- Test: `tests/test_pg_store.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pg_store.py`:

```python
class TestWriteExecutionDecision:
    """write_execution_decision must INSERT a row and return the new id."""

    def test_returns_decision_id(self):
        from datetime import datetime, timezone
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = (55,)

        store = PostgreSQLStore(conn=mock_conn)
        decision_id = store.write_execution_decision(
            tick_time=datetime(2026, 6, 5, 15, tzinfo=timezone.utc),
            symbol="NVDA",
            signal_id=7,
            score=0.55,
            regime_mult=1.0,
            ema_pass=True,
            decision="BUY",
            order_id="abc-123",
        )
        assert decision_id == 55
        mock_conn.commit.assert_called_once()

    def test_order_id_optional(self):
        from datetime import datetime, timezone
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = (56,)

        store = PostgreSQLStore(conn=mock_conn)
        decision_id = store.write_execution_decision(
            tick_time=datetime(2026, 6, 5, 15, tzinfo=timezone.utc),
            symbol="AAPL",
            signal_id=None,
            score=0.35,
            regime_mult=0.7,
            ema_pass=False,
            decision="SKIP_EMA",
        )
        assert decision_id == 56


class TestFetchDecisions:
    """fetch_decisions returns list of dicts, most-recent first."""

    def test_fetch_all_decisions(self):
        from datetime import datetime, timezone
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.description = [
            ("id",), ("tick_time",), ("symbol",), ("signal_id",),
            ("score",), ("regime_mult",), ("ema_pass",), ("decision",),
            ("order_id",), ("created_at",),
        ]
        now = datetime(2026, 6, 5, 15, tzinfo=timezone.utc)
        mock_cur.fetchall.return_value = [
            (1, now, "AAPL", 7, 0.55, 1.0, True, "BUY", "abc-123", now),
        ]

        store = PostgreSQLStore(conn=mock_conn)
        rows = store.fetch_decisions(limit=10)
        assert len(rows) == 1
        assert rows[0]["symbol"] == "AAPL"
        assert rows[0]["decision"] == "BUY"
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_pg_store.py::TestWriteExecutionDecision tests/test_pg_store.py::TestFetchDecisions -v
```

Expected: FAILED — methods don't exist.

- [ ] **Step 3: Implement**

Add to `src/store/pg_store.py` after `link_signal_to_news`:

```python
    _INSERT_DECISION = """
        INSERT INTO execution_decisions
            (tick_time, symbol, signal_id, score, regime_mult, ema_pass, decision, order_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """

    def write_execution_decision(
        self,
        tick_time,
        symbol: str,
        signal_id: int | None,
        score: float,
        regime_mult: float,
        ema_pass: bool,
        decision: str,
        order_id: str | None = None,
    ) -> int:
        """Insert one execution decision row. Returns the new id."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    self._INSERT_DECISION,
                    (tick_time, symbol, signal_id, score, regime_mult, ema_pass, decision, order_id),
                )
                row = cur.fetchone()
            conn.commit()
            return int(row[0])
        except Exception:
            conn.rollback()
            raise

    def fetch_decisions(
        self,
        symbol: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Return decision log rows, most-recent first."""
        filters = []
        params: list = []
        if symbol:
            filters.append("symbol = %s")
            params.append(symbol)
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        params.append(limit)
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""SELECT id, tick_time, symbol, signal_id, score, regime_mult,
                               ema_pass, decision, order_id, created_at
                        FROM execution_decisions {where}
                        ORDER BY tick_time DESC LIMIT %s""",
                    params,
                )
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception:
            conn.rollback()
            raise
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_pg_store.py::TestWriteExecutionDecision tests/test_pg_store.py::TestFetchDecisions -v
```

Expected: PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/store/pg_store.py tests/test_pg_store.py
git commit -m "feat(pg_store): add write_execution_decision and fetch_decisions"
```

---

### Task 6: pg_store — open_trade, close_trade, fetch_trades, fetch_trade_summary

**Files:**
- Modify: `src/store/pg_store.py`
- Test: `tests/test_pg_store.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pg_store.py`:

```python
class TestOpenTrade:
    def test_open_trade_inserts_row(self):
        from datetime import datetime, timezone
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        store = PostgreSQLStore(conn=mock_conn)
        store.open_trade(
            symbol="TSLA",
            signal_id=7,
            decision_id=55,
            entry_order_id="order-abc",
            entry_time=datetime(2026, 6, 5, 15, tzinfo=timezone.utc),
            entry_notional=500.0,
            score=0.55,
            regime_mult=1.0,
            qty=2.5,
        )
        mock_cur.execute.assert_called_once()
        sql = mock_cur.execute.call_args[0][0]
        assert "INSERT INTO trades" in sql
        mock_conn.commit.assert_called_once()


class TestCloseTrade:
    def test_close_trade_updates_open_row(self):
        from datetime import datetime, timezone
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        store = PostgreSQLStore(conn=mock_conn)
        store.close_trade(
            symbol="TSLA",
            exit_price=205.0,
            exit_time=datetime(2026, 6, 5, 16, tzinfo=timezone.utc),
            exit_reason="stop_loss",
        )
        sql = mock_cur.execute.call_args[0][0]
        assert "UPDATE trades" in sql
        assert "exit_time IS NULL" in sql
        mock_conn.commit.assert_called_once()


class TestFetchTrades:
    def test_fetch_all_trades(self):
        from datetime import datetime, timezone
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        now = datetime(2026, 6, 5, tzinfo=timezone.utc)
        mock_cur.description = [("id",), ("symbol",), ("entry_time",), ("net_pnl",)]
        mock_cur.fetchall.return_value = [(1, "TSLA", now, 12.5)]

        store = PostgreSQLStore(conn=mock_conn)
        rows = store.fetch_trades(limit=10)
        assert rows[0]["symbol"] == "TSLA"

    def test_fetch_open_trades_filters_exit_time(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.description = [("id",), ("symbol",), ("entry_time",), ("net_pnl",)]
        mock_cur.fetchall.return_value = []

        store = PostgreSQLStore(conn=mock_conn)
        store.fetch_trades(status="open", limit=5)
        sql = mock_cur.execute.call_args[0][0]
        assert "exit_time IS NULL" in sql

    def test_fetch_closed_trades_filters_exit_time(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.description = [("id",), ("symbol",), ("entry_time",), ("net_pnl",)]
        mock_cur.fetchall.return_value = []

        store = PostgreSQLStore(conn=mock_conn)
        store.fetch_trades(status="closed", limit=5)
        sql = mock_cur.execute.call_args[0][0]
        assert "exit_time IS NOT NULL" in sql


class TestFetchTradeSummary:
    def test_returns_expected_keys(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = (10, 6, 15.0, 0.5, 14.5, 150.0, 145.0, 5000.0, 30.0)

        store = PostgreSQLStore(conn=mock_conn)
        summary = store.fetch_trade_summary(days=7)
        assert summary["total_trades"] == 10
        assert summary["win_rate"] == 0.6
        assert "avg_net_pnl" in summary
        assert "trades_per_week" in summary
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_pg_store.py::TestOpenTrade tests/test_pg_store.py::TestCloseTrade tests/test_pg_store.py::TestFetchTrades tests/test_pg_store.py::TestFetchTradeSummary -v
```

Expected: all FAILED — methods don't exist.

- [ ] **Step 3: Implement**

Add to `src/store/pg_store.py` after `fetch_decisions`:

```python
    _INSERT_TRADE = """
        INSERT INTO trades
            (symbol, signal_id, decision_id, entry_order_id,
             entry_time, entry_notional, score, regime_mult, qty)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    _CLOSE_TRADE = """
        UPDATE trades SET
            exit_price   = %s,
            exit_time    = %s,
            exit_reason  = %s,
            gross_pnl    = (%s - entry_price) * qty,
            slippage_est = entry_notional * 0.0005,
            net_pnl      = ((%s - entry_price) * qty) - (entry_notional * 0.0005)
        WHERE symbol = %s AND exit_time IS NULL
    """

    def open_trade(
        self,
        symbol: str,
        signal_id: int | None,
        decision_id: int | None,
        entry_order_id: str,
        entry_time,
        entry_notional: float,
        score: float,
        regime_mult: float,
        qty: float | None = None,
    ) -> None:
        """Insert an open trade row (entry_price populated later by reconcile)."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    self._INSERT_TRADE,
                    (symbol, signal_id, decision_id, entry_order_id,
                     entry_time, entry_notional, score, regime_mult, qty),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def close_trade(
        self,
        symbol: str,
        exit_price: float,
        exit_time,
        exit_reason: str,
    ) -> None:
        """Update the open trade row for symbol with exit data and compute P&L."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    self._CLOSE_TRADE,
                    (exit_price, exit_time, exit_reason,
                     exit_price, exit_price, symbol),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def fetch_trades(
        self,
        symbol: str | None = None,
        status: str = "all",
        limit: int = 50,
    ) -> list[dict]:
        """Return trades, most-recent first. status: 'open' | 'closed' | 'all'."""
        filters = []
        params: list = []
        if symbol:
            filters.append("symbol = %s")
            params.append(symbol)
        if status == "open":
            filters.append("exit_time IS NULL")
        elif status == "closed":
            filters.append("exit_time IS NOT NULL")
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        params.append(limit)
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""SELECT id, symbol, signal_id, decision_id, entry_order_id,
                               entry_price, entry_time, entry_notional, score, regime_mult,
                               exit_price, exit_time, exit_reason, qty,
                               gross_pnl, slippage_est, net_pnl, created_at
                        FROM trades {where}
                        ORDER BY entry_time DESC LIMIT %s""",
                    params,
                )
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception:
            conn.rollback()
            raise

    _TRADE_SUMMARY_SQL = """
        SELECT
            COUNT(*) AS total_trades,
            SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) AS wins,
            COALESCE(AVG(gross_pnl), 0) AS avg_gross_pnl,
            COALESCE(AVG(slippage_est), 0) AS avg_slippage_est,
            COALESCE(AVG(net_pnl), 0) AS avg_net_pnl,
            COALESCE(SUM(gross_pnl), 0) AS total_gross_pnl,
            COALESCE(SUM(net_pnl), 0) AS total_net_pnl,
            COALESCE(SUM(entry_notional), 0) AS total_notional,
            COALESCE(
                AVG(EXTRACT(EPOCH FROM (exit_time - entry_time)) / 60), 0
            ) AS avg_hold_minutes
        FROM trades
        WHERE exit_time IS NOT NULL
          AND exit_time >= now() - (%s || ' days')::interval
    """

    def fetch_trade_summary(self, days: int = 7) -> dict:
        """Return aggregated P&L metrics for closed trades in the last `days` days."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(self._TRADE_SUMMARY_SQL, (str(days),))
                row = cur.fetchone()
            if not row:
                return {k: 0 for k in [
                    "total_trades", "win_rate", "avg_gross_pnl", "avg_slippage_est",
                    "avg_net_pnl", "total_gross_pnl", "total_net_pnl",
                    "total_notional", "avg_hold_minutes", "trades_per_week",
                    "return_on_notional", "slippage_pct_of_gross",
                ]}
            (total, wins, avg_gross, avg_slip, avg_net,
             total_gross, total_net, total_notional, avg_hold) = row
            total = int(total)
            wins = int(wins or 0)
            win_rate = (wins / total) if total > 0 else 0.0
            trades_per_week = (total / days) * 7
            return_on_notional = (float(total_net) / float(total_notional)) if total_notional else 0.0
            slippage_pct = (float(avg_slip) / float(avg_gross)) if avg_gross else 0.0
            return {
                "total_trades": total,
                "win_rate": round(win_rate, 4),
                "avg_gross_pnl": round(float(avg_gross), 2),
                "avg_slippage_est": round(float(avg_slip), 2),
                "avg_net_pnl": round(float(avg_net), 2),
                "total_gross_pnl": round(float(total_gross), 2),
                "total_net_pnl": round(float(total_net), 2),
                "total_notional": round(float(total_notional), 2),
                "avg_hold_minutes": round(float(avg_hold), 1),
                "trades_per_week": round(trades_per_week, 1),
                "return_on_notional": round(return_on_notional, 4),
                "slippage_pct_of_gross": round(slippage_pct, 4),
            }
        except Exception:
            conn.rollback()
            raise
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_pg_store.py::TestOpenTrade tests/test_pg_store.py::TestCloseTrade tests/test_pg_store.py::TestFetchTrades tests/test_pg_store.py::TestFetchTradeSummary -v
```

Expected: all PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/store/pg_store.py tests/test_pg_store.py
git commit -m "feat(pg_store): add open_trade, close_trade, fetch_trades, fetch_trade_summary"
```

---

### Task 7: execution.py — pg_store param, decision log, trade lifecycle

**Files:**
- Modify: `src/workers/execution.py`
- Test: `tests/workers/test_execution_worker.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/workers/test_execution_worker.py`:

```python
class TestDecisionLogging:
    """run_execution_cycle writes execution decisions for candidates (score > threshold)."""

    def _make_signal(self, score=0.5, fallback=False, signal_id=7):
        from datetime import datetime, timezone
        return {
            "score": score, "fallback_used": fallback, "signal_id": signal_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _make_account(self, portfolio_value=10000.0):
        account = MagicMock()
        account.portfolio_value = str(portfolio_value)
        account.last_equity = str(portfolio_value)
        return account

    def test_buy_writes_decision_and_opens_trade(self):
        from unittest.mock import MagicMock, patch
        from src.workers.execution import run_execution_cycle
        from src.store.redis_store import RedisStore

        mock_redis = MagicMock(spec=RedisStore)
        mock_redis.is_killswitch_active.return_value = False
        mock_redis.get_regime.return_value = MagicMock(multiplier=1.0)
        mock_redis.read_sentiment.return_value = self._make_signal(score=0.5)

        mock_trading = MagicMock()
        mock_trading.get_account.return_value = self._make_account()
        mock_trading.get_all_positions.return_value = []
        mock_trading.get_orders.return_value = []
        submitted = MagicMock()
        submitted.id = "order-uuid-1"
        mock_trading.submit_order.return_value = submitted

        mock_pg = MagicMock()
        mock_pg.write_execution_decision.return_value = 99

        stats = run_execution_cycle(
            symbols=["AAPL"],
            redis_store=mock_redis,
            trading_client=mock_trading,
            pg_store=mock_pg,
        )

        assert stats["orders_placed"] == 1
        mock_pg.write_execution_decision.assert_called_once()
        call_kwargs = mock_pg.write_execution_decision.call_args[1]
        assert call_kwargs["decision"] == "BUY"
        assert call_kwargs["order_id"] == "order-uuid-1"
        mock_pg.open_trade.assert_called_once()

    def test_below_threshold_no_decision_written(self):
        from unittest.mock import MagicMock
        from src.workers.execution import run_execution_cycle
        from src.store.redis_store import RedisStore

        mock_redis = MagicMock(spec=RedisStore)
        mock_redis.is_killswitch_active.return_value = False
        mock_redis.get_regime.return_value = MagicMock(multiplier=1.0)
        mock_redis.read_sentiment.return_value = self._make_signal(score=0.1)  # below threshold

        mock_trading = MagicMock()
        mock_trading.get_account.return_value = self._make_account()
        mock_trading.get_all_positions.return_value = []
        mock_trading.get_orders.return_value = []

        mock_pg = MagicMock()

        run_execution_cycle(
            symbols=["AAPL"],
            redis_store=mock_redis,
            trading_client=mock_trading,
            pg_store=mock_pg,
        )

        mock_pg.write_execution_decision.assert_not_called()

    def test_stop_loss_writes_close_trade(self):
        from unittest.mock import MagicMock
        from src.workers.execution import run_execution_cycle
        from src.store.redis_store import RedisStore

        mock_redis = MagicMock(spec=RedisStore)
        mock_redis.is_killswitch_active.return_value = False
        mock_redis.get_regime.return_value = MagicMock(multiplier=1.0)
        mock_redis.read_sentiment.return_value = self._make_signal(score=0.5)

        pos = MagicMock()
        pos.avg_entry_price = "200.0"
        pos.current_price = "190.0"  # 5% drop, triggers 2% stop

        mock_trading = MagicMock()
        mock_trading.get_account.return_value = self._make_account()
        mock_trading.get_all_positions.return_value = [pos]
        mock_trading.get_orders.return_value = []
        mock_trading.get_all_positions.return_value.__iter__ = lambda self: iter([pos])
        # make open_positions dict work
        pos.symbol = "AAPL"

        mock_pg = MagicMock()

        with MagicMock() as _:
            # Provide open_positions as {symbol: pos}
            from unittest.mock import patch
            with patch.object(mock_trading, "get_all_positions", return_value=[pos]):
                stats = run_execution_cycle(
                    symbols=["AAPL"],
                    redis_store=mock_redis,
                    trading_client=mock_trading,
                    pg_store=mock_pg,
                )

        assert stats["stop_losses_triggered"] == 1
        mock_pg.close_trade.assert_called_once()
        call_kwargs = mock_pg.close_trade.call_args[1]
        assert call_kwargs["symbol"] == "AAPL"
        assert call_kwargs["exit_reason"] == "stop_loss"

    def test_no_pg_store_still_places_order(self):
        """pg_store=None → decisions/trades silently skipped, order still placed."""
        from unittest.mock import MagicMock
        from src.workers.execution import run_execution_cycle
        from src.store.redis_store import RedisStore

        mock_redis = MagicMock(spec=RedisStore)
        mock_redis.is_killswitch_active.return_value = False
        mock_redis.get_regime.return_value = MagicMock(multiplier=1.0)
        mock_redis.read_sentiment.return_value = self._make_signal(score=0.5)

        mock_trading = MagicMock()
        mock_trading.get_account.return_value = self._make_account()
        mock_trading.get_all_positions.return_value = []
        mock_trading.get_orders.return_value = []
        mock_trading.submit_order.return_value = MagicMock(id="x")

        stats = run_execution_cycle(
            symbols=["AAPL"],
            redis_store=mock_redis,
            trading_client=mock_trading,
            pg_store=None,
        )
        assert stats["orders_placed"] == 1
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/workers/test_execution_worker.py::TestDecisionLogging -v
```

Expected: FAILED — `run_execution_cycle` doesn't accept `pg_store` param, no decision writes.

- [ ] **Step 3: Implement changes in execution.py**

Add `_write_decision` helper after `_fire_alert` (around line 134):

```python
def _write_decision(
    pg_store,
    tick_time,
    symbol: str,
    signal_id: int | None,
    score: float,
    regime_mult: float,
    ema_pass: bool,
    decision: str,
    order_id: str | None = None,
) -> int | None:
    """Write one execution decision row. Returns decision_id or None on failure/no-store."""
    if pg_store is None:
        return None
    try:
        return pg_store.write_execution_decision(
            tick_time=tick_time,
            symbol=symbol,
            signal_id=signal_id,
            score=score,
            regime_mult=regime_mult,
            ema_pass=ema_pass,
            decision=decision,
            order_id=order_id,
        )
    except Exception as e:
        log.warning("Failed to write execution decision for %s: %s", symbol, e)
        return None
```

Change `run_execution_cycle` signature (line 153):

```python
def run_execution_cycle(
    symbols: list[str],
    redis_store: RedisStore,
    trading_client,
    data_client=None,
    notifier: "Notifier | None" = None,
    pg_store=None,
) -> dict:
```

Inside the per-symbol loop, after `score` and `fallback_used` are extracted, add `signal_id`:

```python
            score = float(signal.get("score", 0.0))
            fallback_used = bool(signal.get("fallback_used", False))
            signal_id: int | None = signal.get("signal_id")

            # Skip FinBERT fallback signals — lower quality, not ensemble
            if fallback_used:
                log.debug("Skipping fallback signal for %s", symbol)
                stats["skipped_stale"] += 1
                continue
```

Add a `tick_time` variable at start of the loop:

```python
        try:
            tick_time = datetime.now(timezone.utc)
            # --- Signal read ---
```

After stop-loss success (after `stats["stop_losses_triggered"] += 1`), add close_trade:

```python
                        stats["stop_losses_triggered"] += 1
                        if pg_store is not None:
                            try:
                                pg_store.close_trade(
                                    symbol=symbol,
                                    exit_price=current_price,
                                    exit_time=tick_time,
                                    exit_reason="stop_loss",
                                )
                            except Exception as trade_exc:
                                log.warning("Failed to close trade record for %s: %s", symbol, trade_exc)
```

After `if score <= ENTRY_THRESHOLD: continue`, add SKIP_POSITION log for open positions with score above threshold. Move the `if pending_orders` block log:

```python
            # --- Entry logic ---
            if pending_orders is None or symbol in pending_orders:
                log.debug("Pending order check unavailable or order exists for %s — skip", symbol)
                stats["skipped_position"] += 1
                _write_decision(pg_store, tick_time, symbol, signal_id, score, regime_mult,
                                ema_pass=True, decision="SKIP_POSITION")
                continue
```

Also add SKIP_POSITION log for healthy open positions. Replace the `else` block (line 302–306):

```python
                else:
                    # Position open and healthy — idempotent, no pyramiding
                    stats["skipped_position"] += 1
                    log.debug("Position already open for %s — skipping entry", symbol)
                    if score > ENTRY_THRESHOLD:
                        _write_decision(pg_store, tick_time, symbol, signal_id, score, regime_mult,
                                        ema_pass=True, decision="SKIP_POSITION")
```

In the EMA filter block, add SKIP_EMA decision logs:

```python
            ema_pass = True
            if data_client:
                cached = market_cache.get(symbol, {})
                ema = cached.get("ema")
                price = cached.get("price")
                if ema is None or price is None:
                    log.debug("EMA/price unavailable for %s — skipping entry (fail-safe)", symbol)
                    stats["skipped_momentum"] += 1
                    _write_decision(pg_store, tick_time, symbol, signal_id, score, regime_mult,
                                    ema_pass=False, decision="SKIP_EMA")
                    continue
                elif price <= ema:
                    log.debug(
                        "Price below EMA20 for %s (price=%.2f ema=%.2f) — bearish, skip",
                        symbol, price, ema,
                    )
                    stats["skipped_momentum"] += 1
                    _write_decision(pg_store, tick_time, symbol, signal_id, score, regime_mult,
                                    ema_pass=False, decision="SKIP_EMA")
                    continue
```

In the cycle cap block, add SKIP_CAP log:

```python
            if cycle_notional + notional > cycle_cap:
                log.info(
                    "Cycle cap reached (%.2f/%.2f) — skipping %s",
                    cycle_notional, cycle_cap, symbol,
                )
                stats["skipped_cycle_cap"] += 1
                _write_decision(pg_store, tick_time, symbol, signal_id, score, regime_mult,
                                ema_pass=ema_pass, decision="SKIP_CAP")
                continue
```

Track `qty` as a variable (define before the `if price is not None` block):

```python
            qty: float | None = None
            cached = market_cache.get(symbol, {})
            price = cached.get("price")

            if price is not None:
                qty = round(notional / price, 4)
                stop_price_val = round(price * (1 - STOP_LOSS_PCT), 2)
                order = MarketOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.DAY,
                    order_class=OrderClass.OTO,
                    stop_loss=StopLossRequest(stop_price=stop_price_val),
                )
            else:
                order = MarketOrderRequest(
                    symbol=symbol,
                    notional=round(notional, 2),
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.DAY,
                )
            submitted_order = trading_client.submit_order(order)
            order_id_str = str(submitted_order.id)
            cycle_notional += notional
            stats["orders_placed"] += 1
            decision_id = _write_decision(
                pg_store, tick_time, symbol, signal_id, score, regime_mult,
                ema_pass=ema_pass, decision="BUY", order_id=order_id_str,
            )
            if pg_store is not None:
                try:
                    pg_store.open_trade(
                        symbol=symbol,
                        signal_id=signal_id,
                        decision_id=decision_id,
                        entry_order_id=order_id_str,
                        entry_time=tick_time,
                        entry_notional=notional,
                        score=score,
                        regime_mult=regime_mult,
                        qty=qty,
                    )
                except Exception as trade_exc:
                    log.warning("Failed to open trade record for %s: %s", symbol, trade_exc)
```

Update `run_execution_worker` to instantiate pg_store and pass it (after `notifier = TelegramNotifier()`):

```python
    import psycopg2
    from src.store.pg_store import PostgreSQLStore
    pg_conn = psycopg2.connect(config.DATABASE_URL)
    pg_store = PostgreSQLStore(conn=pg_conn)

    try:
        stats = run_execution_cycle(
            symbols=config.WATCHLIST_SYMBOLS or [],
            redis_store=redis_store,
            trading_client=trading_client,
            data_client=data_client,
            notifier=notifier,
            pg_store=pg_store,
        )
        log.info("Execution stats: %s", stats)
        return stats
    finally:
        redis_store.close()
        redis_client.close()
        pg_store.close()
        pg_conn.close()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/workers/test_execution_worker.py -v
```

Expected: all PASSED (new tests + existing).

- [ ] **Step 5: Commit**

```bash
git add src/workers/execution.py tests/workers/test_execution_worker.py
git commit -m "feat(execution): add pg_store param, decision log, trade open/close lifecycle"
```

---

### Task 8: pg_store — reconcile_trade_fills

**Files:**
- Modify: `src/store/pg_store.py`
- Test: `tests/test_pg_store.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pg_store.py`:

```python
class TestReconcileTraideFills:
    """reconcile_trade_fills queries Alpaca for fills on trades where entry_price IS NULL."""

    def test_updates_entry_price_and_qty(self):
        from datetime import datetime, timezone
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchall.return_value = [(1, "order-abc")]

        mock_order = MagicMock()
        mock_order.filled_avg_price = "201.50"
        mock_order.filled_qty = "2.5"

        mock_trading = MagicMock()
        mock_trading.get_order_by_id.return_value = mock_order

        store = PostgreSQLStore(conn=mock_conn)
        updated = store.reconcile_trade_fills(mock_trading)

        assert updated == 1
        update_sql = mock_cur.execute.call_args_list[-1][0][0]
        assert "UPDATE trades" in update_sql
        assert "entry_price" in update_sql

    def test_skips_unfilled_order(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchall.return_value = [(1, "order-abc")]

        mock_order = MagicMock()
        mock_order.filled_avg_price = None  # not yet filled

        mock_trading = MagicMock()
        mock_trading.get_order_by_id.return_value = mock_order

        store = PostgreSQLStore(conn=mock_conn)
        updated = store.reconcile_trade_fills(mock_trading)

        assert updated == 0
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_pg_store.py::TestReconcileTraideFills -v
```

Expected: FAILED — method doesn't exist.

- [ ] **Step 3: Implement**

Add to `src/store/pg_store.py` after `fetch_trade_summary`:

```python
    def reconcile_trade_fills(self, trading_client) -> int:
        """Fetch fill prices from Alpaca for trades where entry_price IS NULL.

        Called daily (run_daily_report). Returns the count of rows updated.
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, entry_order_id FROM trades
                       WHERE entry_price IS NULL
                         AND entry_time > now() - '24 hours'::interval"""
                )
                rows = cur.fetchall()
            updated = 0
            for trade_id, order_id in rows:
                try:
                    order = trading_client.get_order_by_id(order_id)
                    if order.filled_avg_price is None:
                        continue
                    fill_price = float(order.filled_avg_price)
                    fill_qty = float(order.filled_qty) if order.filled_qty else None
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE trades SET entry_price = %s, qty = %s WHERE id = %s",
                            (fill_price, fill_qty, trade_id),
                        )
                    updated += 1
                except Exception as e:
                    log.warning("Failed to reconcile order %s: %s", order_id, e)
            conn.commit()
            return updated
        except Exception:
            conn.rollback()
            raise
```

Add `import logging` (if not already present) and `log = logging.getLogger(__name__)` at the module level of `pg_store.py`.

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_pg_store.py::TestReconcileTraideFills -v
```

Expected: PASSED.

- [ ] **Step 5: Run the full pg_store test suite**

```bash
pytest tests/test_pg_store.py -v
```

Expected: all PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/store/pg_store.py tests/test_pg_store.py
git commit -m "feat(pg_store): add reconcile_trade_fills (daily fill price sync from Alpaca)"
```

---

### Task 9: performance.py — trade metrics in weekly report + daily reconcile

**Files:**
- Modify: `src/workers/performance.py`
- Modify: `config/trading.yaml`
- Modify: `src/config.py`
- Test: `tests/workers/test_performance_worker.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/workers/test_performance_worker.py`:

```python
class TestFormatTradeMetrics:
    """_format_trade_metrics_section produces expected Telegram-ready text."""

    def test_all_metrics_present(self):
        from src.workers.performance import _format_trade_metrics_section
        summary = {
            "total_trades": 12,
            "win_rate": 0.583,
            "avg_gross_pnl": 18.5,
            "avg_slippage_est": 0.8,
            "avg_net_pnl": 17.7,
            "total_gross_pnl": 222.0,
            "total_net_pnl": 212.4,
            "total_notional": 6000.0,
            "trades_per_week": 12.0,
            "return_on_notional": 0.0354,
            "avg_hold_minutes": 45.0,
            "slippage_pct_of_gross": 0.043,
        }
        text = _format_trade_metrics_section(summary)
        assert "58.3%" in text  # win rate
        assert "12" in text     # total trades
        assert "17.70" in text  # avg net pnl

    def test_high_slippage_triggers_warning(self):
        from src.workers.performance import _format_trade_metrics_section
        summary = {
            "total_trades": 5,
            "win_rate": 0.4,
            "avg_gross_pnl": 10.0,
            "avg_slippage_est": 4.0,
            "avg_net_pnl": 6.0,
            "total_gross_pnl": 50.0,
            "total_net_pnl": 30.0,
            "total_notional": 2500.0,
            "trades_per_week": 5.0,
            "return_on_notional": 0.012,
            "avg_hold_minutes": 30.0,
            "slippage_pct_of_gross": 0.40,  # 40% > 30% threshold
        }
        text = _format_trade_metrics_section(summary)
        assert "⚠️" in text

    def test_low_avg_net_pnl_triggers_warning(self):
        from src.workers.performance import _format_trade_metrics_section
        summary = {
            "total_trades": 5,
            "win_rate": 0.4,
            "avg_gross_pnl": 3.0,
            "avg_slippage_est": 0.5,
            "avg_net_pnl": 2.5,  # below $5.0 threshold
            "total_gross_pnl": 15.0,
            "total_net_pnl": 12.5,
            "total_notional": 2500.0,
            "trades_per_week": 5.0,
            "return_on_notional": 0.005,
            "avg_hold_minutes": 25.0,
            "slippage_pct_of_gross": 0.17,
        }
        text = _format_trade_metrics_section(summary)
        assert "⚠️" in text
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/workers/test_performance_worker.py::TestFormatTradeMetrics -v
```

Expected: FAILED — `_format_trade_metrics_section` doesn't exist.

- [ ] **Step 3: Add config key to trading.yaml**

In `config/trading.yaml`, under the `risk:` section, add:

```yaml
  min_trade_pnl_threshold: 5.0   # $ min avg net P&L per trade before ⚠️ alert in weekly report
```

- [ ] **Step 4: Add config attribute to src/config.py**

In `src/config.py`, after `AUTO_APPLY_IC_VARIANCE_THRESHOLD`:

```python
    MIN_TRADE_PNL_THRESHOLD: float = Field(
        default_factory=lambda: float(
            _load_trading_yaml().get("risk", {}).get("min_trade_pnl_threshold", 5.0)
        )
    )
```

- [ ] **Step 5: Implement _format_trade_metrics_section in performance.py**

Add near the top of `src/workers/performance.py` (after imports), alongside other module constants:

```python
_SLIPPAGE_WARN_PCT = 0.30   # ⚠️ if estimated slippage > 30% of gross P&L
```

Add the function before `run_daily_report`:

```python
def _format_trade_metrics_section(trades_summary: dict) -> str:
    """Format the trade P&L section for the weekly Telegram report."""
    from src.config import config

    total = trades_summary.get("total_trades", 0)
    if total == 0:
        return "\n📊 *Trade P&L (last 7d)*\nNo closed trades in period."

    win_pct = trades_summary.get("win_rate", 0) * 100
    avg_net = trades_summary.get("avg_net_pnl", 0)
    avg_gross = trades_summary.get("avg_gross_pnl", 0)
    avg_slip = trades_summary.get("avg_slippage_est", 0)
    total_net = trades_summary.get("total_net_pnl", 0)
    total_gross = trades_summary.get("total_gross_pnl", 0)
    total_notional = trades_summary.get("total_notional", 0)
    tpw = trades_summary.get("trades_per_week", 0)
    avg_hold = trades_summary.get("avg_hold_minutes", 0)
    slip_pct = trades_summary.get("slippage_pct_of_gross", 0)
    ron = trades_summary.get("return_on_notional", 0) * 100

    warnings = []
    if avg_net < config.MIN_TRADE_PNL_THRESHOLD:
        warnings.append(f"⚠️ avg net P&L ${avg_net:.2f} < ${config.MIN_TRADE_PNL_THRESHOLD:.2f} threshold")
    if slip_pct > _SLIPPAGE_WARN_PCT:
        warnings.append(f"⚠️ slippage {slip_pct*100:.1f}% of gross — consider raising ENTRY_THRESHOLD")

    warn_str = "\n" + "\n".join(warnings) if warnings else ""

    return (
        f"\n📊 *Trade P&L (last 7d)*\n"
        f"Trades: {total} | Win rate: {win_pct:.1f}%\n"
        f"Avg gross P&L: ${avg_gross:.2f} | Avg slippage: ${avg_slip:.2f} | Avg net: ${avg_net:.2f}\n"
        f"Total gross: ${total_gross:.2f} | Total net: ${total_net:.2f}\n"
        f"\n📈 *Frequency vs Margin*\n"
        f"Trades/week: {tpw:.1f} | Total notional: ${total_notional:.0f}\n"
        f"Return on notional: {ron:.2f}% | Avg hold: {avg_hold:.0f}min\n"
        f"Est. slippage: {slip_pct*100:.1f}% of gross P&L"
        f"{warn_str}"
    )
```

- [ ] **Step 6: Wire into run_weekly_weights and run_daily_report**

In `run_weekly_weights`, after building the Telegram message, add before sending:

```python
        # Append trade P&L section
        try:
            trade_summary = pg.fetch_trade_summary(days=7)
            message += _format_trade_metrics_section(trade_summary)
        except Exception as e:
            log.warning("Failed to fetch trade summary for weekly report: %s", e)
```

In `run_daily_report`, after existing logic (near the end, before the `finally` block), add:

```python
        # Reconcile fill prices from Alpaca for trades placed in last 24h
        if config.ALPACA_API_KEY and config.ALPACA_SECRET_KEY:
            try:
                from alpaca.trading.client import TradingClient
                tc = TradingClient(
                    api_key=config.ALPACA_API_KEY,
                    secret_key=config.ALPACA_SECRET_KEY,
                    paper="paper-api" in config.ALPACA_BASE_URL,
                )
                updated = pg.reconcile_trade_fills(tc)
                log.info("Reconciled %d trade fill(s) from Alpaca", updated)
            except Exception as e:
                log.warning("Fill reconciliation failed: %s", e)
```

- [ ] **Step 7: Run tests**

```bash
pytest tests/workers/test_performance_worker.py::TestFormatTradeMetrics -v
```

Expected: PASSED.

- [ ] **Step 8: Run full performance test suite**

```bash
pytest tests/workers/test_performance_worker.py -v
```

Expected: all PASSED.

- [ ] **Step 9: Commit**

```bash
git add src/workers/performance.py config/trading.yaml src/config.py tests/workers/test_performance_worker.py
git commit -m "feat(performance): add trade P&L section to weekly report + daily fill reconciliation"
```

---

### Task 10: API endpoints — /api/trades, /api/trades/summary, /api/decisions

**Files:**
- Modify: `src/api/routes/trading.py`
- Test: `tests/api/test_trading_routes.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/test_trading_routes.py`:

```python
from src.api.deps import get_pg_store

_skip_auth = lambda: "test-key"


class TestTradesEndpoints:
    def test_get_trades_returns_list(self):
        mock_pg = MagicMock()
        mock_pg.fetch_trades.return_value = [
            {"id": 1, "symbol": "AAPL", "entry_time": "2026-06-05T10:00:00+00:00",
             "net_pnl": 12.5, "exit_time": None}
        ]
        app.dependency_overrides[get_pg_store] = lambda: mock_pg
        app.dependency_overrides[require_api_key] = _skip_auth

        tc = TestClient(app)
        resp = tc.get("/api/trades")
        app.dependency_overrides.clear()

        assert resp.status_code == 200
        assert resp.json()[0]["symbol"] == "AAPL"

    def test_get_trades_summary(self):
        mock_pg = MagicMock()
        mock_pg.fetch_trade_summary.return_value = {
            "total_trades": 5, "win_rate": 0.6, "avg_net_pnl": 14.0,
            "total_net_pnl": 70.0, "trades_per_week": 5.0,
            "avg_gross_pnl": 15.0, "avg_slippage_est": 1.0,
            "total_gross_pnl": 75.0, "total_notional": 3000.0,
            "avg_hold_minutes": 40.0, "return_on_notional": 0.023,
            "slippage_pct_of_gross": 0.07,
        }
        app.dependency_overrides[get_pg_store] = lambda: mock_pg
        app.dependency_overrides[require_api_key] = _skip_auth

        tc = TestClient(app)
        resp = tc.get("/api/trades/summary?days=7")
        app.dependency_overrides.clear()

        assert resp.status_code == 200
        assert resp.json()["total_trades"] == 5

    def test_get_decisions_returns_list(self):
        mock_pg = MagicMock()
        mock_pg.fetch_decisions.return_value = [
            {"id": 1, "tick_time": "2026-06-05T10:00:00+00:00",
             "symbol": "NVDA", "score": 0.55, "decision": "BUY", "order_id": "x"}
        ]
        app.dependency_overrides[get_pg_store] = lambda: mock_pg
        app.dependency_overrides[require_api_key] = _skip_auth

        tc = TestClient(app)
        resp = tc.get("/api/decisions")
        app.dependency_overrides.clear()

        assert resp.status_code == 200
        assert resp.json()[0]["decision"] == "BUY"

    def test_trades_requires_auth(self):
        tc = TestClient(app)
        resp = tc.get("/api/trades")
        assert resp.status_code == 403
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/api/test_trading_routes.py::TestTradesEndpoints -v
```

Expected: FAILED — endpoints don't exist.

- [ ] **Step 3: Implement**

Append to `src/api/routes/trading.py`:

```python
from typing import Annotated
from fastapi import Depends, Query
from src.api.deps import get_pg_store


@router.get("/trades")
def get_trades(
    pg: Annotated[object, Depends(get_pg_store)],
    symbol: str | None = None,
    status: str = Query(default="all", pattern="^(open|closed|all)$"),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict]:
    """List trades with optional symbol/status filter."""
    return pg.fetch_trades(symbol=symbol, status=status, limit=limit)


@router.get("/trades/summary")
def get_trades_summary(
    pg: Annotated[object, Depends(get_pg_store)],
    days: int = Query(default=7, ge=1, le=90),
) -> dict:
    """Aggregated P&L metrics for closed trades."""
    return pg.fetch_trade_summary(days=days)


@router.get("/decisions")
def get_decisions(
    pg: Annotated[object, Depends(get_pg_store)],
    symbol: str | None = None,
    limit: int = Query(default=20, ge=1, le=200),
) -> list[dict]:
    """Execution decision log (score > threshold candidates only)."""
    return pg.fetch_decisions(symbol=symbol, limit=limit)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/api/test_trading_routes.py -v
```

Expected: all PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/api/routes/trading.py tests/api/test_trading_routes.py
git commit -m "feat(api): add /api/trades, /api/trades/summary, /api/decisions endpoints"
```

---

### Task 11: Frontend API layer — trades.ts

**Files:**
- Create: `frontend/src/api/trades.ts`

- [ ] **Step 1: Create the file**

```typescript
// frontend/src/api/trades.ts
import { apiFetch } from './client'

export interface Trade {
  id: number
  symbol: string
  signal_id: number | null
  decision_id: number | null
  entry_order_id: string
  entry_price: number | null
  entry_time: string
  entry_notional: number
  score: number
  regime_mult: number
  exit_price: number | null
  exit_time: string | null
  exit_reason: string | null
  qty: number | null
  gross_pnl: number | null
  slippage_est: number | null
  net_pnl: number | null
  created_at: string
}

export interface TradesSummary {
  total_trades: number
  win_rate: number
  avg_gross_pnl: number
  avg_slippage_est: number
  avg_net_pnl: number
  total_gross_pnl: number
  total_net_pnl: number
  total_notional: number
  avg_hold_minutes: number
  trades_per_week: number
  return_on_notional: number
  slippage_pct_of_gross: number
}

export interface Decision {
  id: number
  tick_time: string
  symbol: string
  signal_id: number | null
  score: number
  regime_mult: number
  ema_pass: boolean
  decision: string
  order_id: string | null
  created_at: string
}

export type TradeStatus = 'open' | 'closed' | 'all'
export type SummaryPeriod = 7 | 30 | 90

export const fetchTrades = (symbol?: string, status: TradeStatus = 'all', limit = 50) => {
  const params = new URLSearchParams({ status, limit: String(limit) })
  if (symbol) params.set('symbol', symbol)
  return apiFetch<Trade[]>(`/api/trades?${params}`)
}

export const fetchTradesSummary = (days: SummaryPeriod = 7) =>
  apiFetch<TradesSummary>(`/api/trades/summary?days=${days}`)

export const fetchDecisions = (symbol?: string, limit = 20) => {
  const params = new URLSearchParams({ limit: String(limit) })
  if (symbol) params.set('symbol', symbol)
  return apiFetch<Decision[]>(`/api/decisions?${params}`)
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors related to `trades.ts`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/trades.ts
git commit -m "feat(frontend/api): add trades.ts — Trade, TradesSummary, Decision types and fetch functions"
```

---

### Task 12: Frontend — Trades.tsx page

**Files:**
- Create: `frontend/src/pages/Trades.tsx`

- [ ] **Step 1: Create the file**

```typescript
// frontend/src/pages/Trades.tsx
import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer,
} from 'recharts'
import { fetchTrades, fetchTradesSummary, type Trade, type TradeStatus, type SummaryPeriod } from '@/api/trades'

const PERIODS: SummaryPeriod[] = [7, 30, 90]

function fmt(v: number | null, prefix = '$') {
  if (v == null) return '—'
  return `${prefix}${v.toFixed(2)}`
}

function fmtPct(v: number | null) {
  if (v == null) return '—'
  return `${(v * 100).toFixed(1)}%`
}

function holdLabel(mins: number | null) {
  if (mins == null) return '—'
  if (mins < 60) return `${Math.round(mins)}m`
  return `${(mins / 60).toFixed(1)}h`
}

export default function Trades() {
  const [period, setPeriod] = useState<SummaryPeriod>(7)
  const [statusFilter, setStatusFilter] = useState<TradeStatus>('all')
  const [symbolFilter, setSymbolFilter] = useState('')
  const [expandedId, setExpandedId] = useState<number | null>(null)

  const { data: summary } = useQuery({
    queryKey: ['trades-summary', period],
    queryFn: () => fetchTradesSummary(period),
    refetchInterval: 120000,
  })

  const { data: trades = [], isLoading } = useQuery({
    queryKey: ['trades', statusFilter, period],
    queryFn: () => fetchTrades(undefined, statusFilter, 200),
    refetchInterval: 120000,
  })

  const filtered = useMemo(() =>
    trades.filter((t: Trade) =>
      !symbolFilter || t.symbol.toLowerCase().includes(symbolFilter.toLowerCase())
    ), [trades, symbolFilter])

  // Cumulative P&L for closed trades sorted by exit_time
  const cumulativeData = useMemo(() => {
    const closed = filtered
      .filter(t => t.exit_time && t.net_pnl != null)
      .sort((a, b) => (a.exit_time! > b.exit_time! ? 1 : -1))
    let cum = 0
    return closed.map(t => {
      cum += t.net_pnl!
      return { date: t.exit_time!.slice(0, 10), cumulative: parseFloat(cum.toFixed(2)) }
    })
  }, [filtered])

  const lineColor = (cumulativeData.at(-1)?.cumulative ?? 0) >= 0 ? '#22c55e' : '#ef4444'

  const totalNetPnl = summary?.total_net_pnl ?? 0

  return (
    <div style={{ position: 'relative' }}>
      <h2 style={{ margin: '0 0 20px', fontSize: 20, fontWeight: 700 }}>Trades</h2>

      {/* Period selector */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 20 }}>
        {PERIODS.map(p => (
          <button
            key={p}
            onClick={() => setPeriod(p)}
            style={{
              padding: '4px 12px', borderRadius: 6, border: 'none', cursor: 'pointer',
              background: period === p ? '#3b82f6' : '#334155',
              color: 'white', fontSize: 13,
            }}
          >{p}d</button>
        ))}
      </div>

      {/* Summary cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24 }}>
        {[
          { label: 'Total Trades', value: String(summary?.total_trades ?? '—') },
          { label: 'Win Rate', value: fmtPct(summary?.win_rate ?? null) },
          { label: 'Avg Net P&L', value: fmt(summary?.avg_net_pnl ?? null) },
          { label: 'Total Net P&L', value: fmt(totalNetPnl), color: totalNetPnl >= 0 ? '#22c55e' : '#ef4444' },
        ].map(c => (
          <div key={c.label} style={{ background: '#1e293b', borderRadius: 8, padding: '14px 16px' }}>
            <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>{c.label}</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: c.color ?? 'white' }}>{c.value}</div>
          </div>
        ))}
      </div>

      {/* Cumulative P&L chart */}
      {cumulativeData.length > 0 && (
        <div style={{ background: '#1e293b', borderRadius: 8, padding: 16, marginBottom: 24 }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>Cumulative Net P&L</div>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={cumulativeData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="date" tick={{ fill: '#94a3b8', fontSize: 11 }} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} tickFormatter={v => `$${v}`} />
              <Tooltip formatter={(v: number) => [`$${v.toFixed(2)}`, 'Cumulative']} />
              <Line type="monotone" dataKey="cumulative" stroke={lineColor} dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Filters */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <input
          value={symbolFilter}
          onChange={e => setSymbolFilter(e.target.value)}
          placeholder="Filter symbol…"
          style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #334155', background: '#0f172a', color: 'white', fontSize: 13, width: 140 }}
        />
        {(['all', 'open', 'closed'] as TradeStatus[]).map(s => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            style={{
              padding: '4px 12px', borderRadius: 6, border: 'none', cursor: 'pointer',
              background: statusFilter === s ? '#3b82f6' : '#334155',
              color: 'white', fontSize: 13, textTransform: 'capitalize',
            }}
          >{s}</button>
        ))}
      </div>

      {/* Trade table */}
      {isLoading ? (
        <div style={{ color: '#64748b', padding: 20 }}>Loading…</div>
      ) : (
        <div style={{ background: '#1e293b', borderRadius: 8, overflow: 'hidden' }}>
          <div style={{
            display: 'grid',
            gridTemplateColumns: '8% 10% 10% 7% 7% 9% 9% 7% 9% 12% 12%',
            padding: '8px 12px', background: '#0f172a',
            fontSize: 11, color: '#64748b', fontWeight: 600, textTransform: 'uppercase',
          }}>
            {['Symbol', 'Entry', 'Exit', 'Score', 'Regime', 'Entry $', 'Exit $', 'Hold', 'Net P&L', 'Exit Reason', 'Decision'].map(h => (
              <span key={h}>{h}</span>
            ))}
          </div>
          {filtered.map((t: Trade) => (
            <div key={t.id}>
              <div
                onClick={() => setExpandedId(expandedId === t.id ? null : t.id)}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '8% 10% 10% 7% 7% 9% 9% 7% 9% 12% 12%',
                  padding: '8px 12px', fontSize: 13, cursor: 'pointer',
                  borderTop: '1px solid #0f172a',
                  background: expandedId === t.id ? '#0f172a' : 'transparent',
                }}
              >
                <span style={{ fontWeight: 600 }}>{t.symbol}</span>
                <span style={{ color: '#94a3b8' }}>{t.entry_time.slice(0, 10)}</span>
                <span style={{ color: '#94a3b8' }}>{t.exit_time?.slice(0, 10) ?? '—'}</span>
                <span>{t.score.toFixed(2)}</span>
                <span>{t.regime_mult.toFixed(2)}×</span>
                <span>{fmt(t.entry_price)}</span>
                <span>{fmt(t.exit_price)}</span>
                <span>{holdLabel(t.exit_time ? ((new Date(t.exit_time).getTime() - new Date(t.entry_time).getTime()) / 60000) : null)}</span>
                <span style={{ color: (t.net_pnl ?? 0) >= 0 ? '#22c55e' : '#ef4444' }}>
                  {fmt(t.net_pnl)}
                </span>
                <span style={{ color: '#94a3b8', fontSize: 12 }}>{t.exit_reason ?? '—'}</span>
                <span style={{ color: '#94a3b8', fontSize: 12 }}>ID {t.decision_id ?? '—'}</span>
              </div>
              {expandedId === t.id && (
                <div style={{ padding: '8px 12px 12px', background: '#0f172a', fontSize: 12, color: '#94a3b8' }}>
                  <span>signal_id: {t.signal_id ?? '—'}</span>
                  {' | '}
                  <span>order: {t.entry_order_id}</span>
                  {' | '}
                  <span>notional: {fmt(t.entry_notional)}</span>
                  {' | '}
                  <span>slippage est: {fmt(t.slippage_est)}</span>
                  {' | '}
                  <span>gross P&L: {fmt(t.gross_pnl)}</span>
                </div>
              )}
            </div>
          ))}
          {filtered.length === 0 && (
            <div style={{ padding: 20, color: '#64748b', textAlign: 'center' }}>No trades found.</div>
          )}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors related to `Trades.tsx`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Trades.tsx
git commit -m "feat(frontend): add Trades.tsx page — summary cards, cumulative P&L chart, trade table"
```

---

### Task 13: Frontend — Decision Log tab in Signals.tsx

**Files:**
- Modify: `frontend/src/pages/Signals.tsx`

- [ ] **Step 1: Implement the Decision Log tab**

Read the full current `Signals.tsx`, then wrap the existing content in a tab layout. The current signals view becomes "Signals" tab; add "Decision Log" as second tab.

At the top of `Signals.tsx`, add imports:

```typescript
import { fetchDecisions, type Decision } from '@/api/trades'
```

Add a `tab` state variable after existing `useState` calls:

```typescript
  const [tab, setTab] = useState<'signals' | 'decisions'>('signals')
```

Add the decisions query after the signals query:

```typescript
  const { data: decisions = [], isLoading: decisionsLoading } = useQuery({
    queryKey: ['decisions'],
    queryFn: () => fetchDecisions(ticker || undefined, 100),
    enabled: tab === 'decisions',
    refetchInterval: 60000,
  })
```

Wrap the existing return JSX: add a tab bar before the existing `<h2>` and conditionally render the decisions table. Replace the `return (` with:

```tsx
  const DECISION_LABELS: Record<string, string> = {
    BUY: 'BUY',
    SKIP_EMA: 'Skip — below EMA',
    SKIP_CAP: 'Skip — cycle cap',
    SKIP_POSITION: 'Skip — position open',
  }

  return (
    <div style={{ position: 'relative' }}>
      <div style={{ display: 'flex', gap: 0, marginBottom: 20, borderBottom: '1px solid #334155' }}>
        {(['signals', 'decisions'] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              padding: '8px 20px', border: 'none', cursor: 'pointer',
              background: 'transparent',
              color: tab === t ? '#3b82f6' : '#64748b',
              borderBottom: tab === t ? '2px solid #3b82f6' : '2px solid transparent',
              fontWeight: tab === t ? 600 : 400, fontSize: 14,
              textTransform: 'capitalize',
            }}
          >{t === 'signals' ? 'Signals' : 'Decision Log'}</button>
        ))}
      </div>

      {tab === 'decisions' && (
        <div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <input
              value={ticker}
              onChange={e => setTicker(e.target.value)}
              placeholder="Filter symbol…"
              style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #334155', background: '#0f172a', color: 'white', fontSize: 13, width: 140 }}
            />
          </div>
          {decisionsLoading ? (
            <div style={{ color: '#64748b', padding: 20 }}>Loading…</div>
          ) : (
            <div style={{ background: '#1e293b', borderRadius: 8, overflow: 'hidden' }}>
              <div style={{
                display: 'grid', gridTemplateColumns: '15% 10% 9% 9% 7% 22% 28%',
                padding: '8px 12px', background: '#0f172a',
                fontSize: 11, color: '#64748b', fontWeight: 600, textTransform: 'uppercase',
              }}>
                {['Tick Time', 'Symbol', 'Score', 'Regime', 'EMA', 'Decision', 'Order ID'].map(h => (
                  <span key={h}>{h}</span>
                ))}
              </div>
              {decisions.map((d: Decision) => (
                <div key={d.id} style={{
                  display: 'grid', gridTemplateColumns: '15% 10% 9% 9% 7% 22% 28%',
                  padding: '8px 12px', fontSize: 13, borderTop: '1px solid #0f172a',
                }}>
                  <span style={{ color: '#94a3b8' }}>{d.tick_time.slice(0, 16).replace('T', ' ')}</span>
                  <span style={{ fontWeight: 600 }}>{d.symbol}</span>
                  <span>{d.score.toFixed(2)}</span>
                  <span>{d.regime_mult.toFixed(2)}×</span>
                  <span>{d.ema_pass ? '✓' : '✗'}</span>
                  <span style={{
                    color: d.decision === 'BUY' ? '#22c55e' : '#94a3b8',
                    fontWeight: d.decision === 'BUY' ? 600 : 400,
                  }}>{DECISION_LABELS[d.decision] ?? d.decision}</span>
                  <span style={{ color: '#64748b', fontSize: 11 }}>{d.order_id ?? '—'}</span>
                </div>
              ))}
              {decisions.length === 0 && (
                <div style={{ padding: 20, color: '#64748b', textAlign: 'center' }}>No decisions logged yet.</div>
              )}
            </div>
          )}
        </div>
      )}

      {tab === 'signals' && (
        // === existing Signals content (h2, HelpButton, filters, virtualizer, table) ===
```

Close the JSX at the end with an extra `)}` after the existing closing `</div>`.

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: no type errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Signals.tsx
git commit -m "feat(frontend): add Decision Log tab to Signals page"
```

---

### Task 14: Frontend — Performance.tsx trade frequency charts

**Files:**
- Modify: `frontend/src/pages/Performance.tsx`

- [ ] **Step 1: Add trade frequency section**

At the top of `Performance.tsx`, add imports:

```typescript
import { BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer } from 'recharts'
import { fetchTradesSummary } from '@/api/trades'
```

Add trade summary query after existing pnl query:

```typescript
  const { data: tradeSummary } = useQuery({
    queryKey: ['trades-summary-perf', 30],
    queryFn: () => fetchTradesSummary(30),
    refetchInterval: 300000,
  })
```

Append before the closing `</div>` of the return, after the existing monthly table:

```tsx
      {/* Trade frequency section */}
      {tradeSummary && tradeSummary.total_trades > 0 && (
        <div style={{ marginTop: 32 }}>
          <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 600 }}>Trade Activity (last 30d)</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            {/* Trades/week summary bar */}
            <div style={{ background: '#1e293b', borderRadius: 8, padding: 16 }}>
              <div style={{ fontSize: 13, color: '#94a3b8', marginBottom: 12 }}>Summary</div>
              {[
                ['Trades', String(tradeSummary.total_trades)],
                ['Trades/week', tradeSummary.trades_per_week.toFixed(1)],
                ['Win rate', `${(tradeSummary.win_rate * 100).toFixed(1)}%`],
                ['Avg net P&L', `$${tradeSummary.avg_net_pnl.toFixed(2)}`],
                ['Total net P&L', `$${tradeSummary.total_net_pnl.toFixed(2)}`],
                ['Avg hold', `${tradeSummary.avg_hold_minutes.toFixed(0)}min`],
                ['Slippage % gross', `${(tradeSummary.slippage_pct_of_gross * 100).toFixed(1)}%`],
              ].map(([label, value]) => (
                <div key={label} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #0f172a', fontSize: 13 }}>
                  <span style={{ color: '#64748b' }}>{label}</span>
                  <span style={{ fontWeight: 600 }}>{value}</span>
                </div>
              ))}
            </div>
            {/* Return on notional mini-chart */}
            <div style={{ background: '#1e293b', borderRadius: 8, padding: 16 }}>
              <div style={{ fontSize: 13, color: '#94a3b8', marginBottom: 12 }}>Notional & P&L</div>
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={[
                  { label: 'Total Notional', value: tradeSummary.total_notional },
                  { label: 'Gross P&L', value: tradeSummary.total_gross_pnl },
                  { label: 'Net P&L', value: tradeSummary.total_net_pnl },
                ]}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="label" tick={{ fill: '#94a3b8', fontSize: 10 }} />
                  <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} tickFormatter={v => `$${v}`} />
                  <Tooltip formatter={(v: number) => [`$${v.toFixed(2)}`]} />
                  <Bar dataKey="value" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Performance.tsx
git commit -m "feat(frontend): add trade activity section to Performance page (summary + P&L bar chart)"
```

---

### Task 15: Frontend routing — App.tsx + Sidebar.tsx

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/Sidebar.tsx`

- [ ] **Step 1: Add Trades route to App.tsx**

In `frontend/src/App.tsx`:

Add lazy import after existing lazy declarations:

```typescript
const Trades      = lazy(() => import('@/pages/Trades'))
```

Add route after the `/trading` route:

```tsx
                <Route path="/trades"       element={<Trades />} />
```

- [ ] **Step 2: Add Trades nav entry to Sidebar.tsx**

In `frontend/src/components/layout/Sidebar.tsx`, add after the Trading entry in the `NAV` array:

```typescript
  { to: '/trades',     label: 'Trades',      icon: '💰' },
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 4: Build to confirm no runtime bundle errors**

```bash
cd frontend && npm run build 2>&1 | tail -20
```

Expected: Build completed. No module resolution errors.

- [ ] **Step 5: Run full test suite**

```bash
source .venv/bin/activate && pytest -x -q 2>&1 | tail -20
```

Expected: all tests pass.

- [ ] **Step 6: Final commit**

```bash
git add frontend/src/App.tsx frontend/src/components/layout/Sidebar.tsx
git commit -m "feat(frontend): wire Trades page into routing and sidebar navigation"
```

---

## Spec Coverage Check

| Spec section | Task(s) covering it |
|---|---|
| §1a `news_log_id` FK on `sentiment_signals` | Task 1, 2 |
| §1b `execution_decisions` table + indexes | Task 1, 5 |
| §1c `trades` table + indexes | Task 1, 6 |
| §2 `log_news_item` returns id | Task 2 |
| §2 `link_signal_to_news` | Task 2 |
| §2 `signal_id` in Redis payload | Task 3 |
| §2 call order in `process_news_item` | Task 4 |
| §3a decision log in execution worker | Task 7 |
| §3b `open_trade` after BUY | Task 6, 7 |
| §3c `close_trade` after stop-loss | Task 6, 7 |
| §3d `reconcile_trade_fills` daily | Task 8, 9 |
| §4 weekly report trade metrics | Task 9 |
| §4 `min_trade_pnl_threshold` config key | Task 9 |
| §5 GET /api/trades | Task 10 |
| §5 GET /api/trades/summary | Task 10 |
| §5 GET /api/decisions | Task 10 |
| §6a Trades.tsx page | Task 11, 12, 15 |
| §6b Decision Log tab in Signals.tsx | Task 13 |
| §6c Trade activity in Performance.tsx | Task 14 |
