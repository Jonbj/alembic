# Trade Observability — Design Spec
**Date:** 2026-06-05  
**Status:** Approved

## Problem

The pipeline has no end-to-end traceability from news article → LLM signal → execution decision → order → P&L. Specifically:

- `news_log` and `sentiment_signals` are written sequentially but share no FK
- The execution worker logs only aggregate per-tick stats (89 symbols checked, N skipped) — no per-symbol record of why a symbol was bought or skipped
- Orders placed on Alpaca are not recorded in PG — no per-trade P&L history
- No commission-erosion analysis: unknown whether trade frequency is destroying margin

## Chosen Approach: Schema additions + synchronous writes (Approach A)

Three new schema objects + changes to sentiment pipeline, execution worker, weekly report, and frontend. Alpaca remains source of truth for fill prices; our DB holds decisional context (score, regime, signal).

---

## 1. Database Schema (migration `016`)

### 1a. `news_log_id` on `sentiment_signals`

```sql
ALTER TABLE sentiment_signals
  ADD COLUMN news_log_id BIGINT REFERENCES news_log(id) ON DELETE SET NULL;
```

Nullable: signals from backtest or manual injection remain valid without a news source.

### 1b. Table `execution_decisions`

One row per candidate symbol per tick (score > ENTRY_THRESHOLD). Not written for stale/fallback skips — only for symbols that reach the threshold and EMA evaluation stage.

```sql
CREATE TABLE execution_decisions (
    id           BIGSERIAL PRIMARY KEY,
    tick_time    TIMESTAMPTZ NOT NULL,
    symbol       VARCHAR(20) NOT NULL,
    signal_id    BIGINT REFERENCES sentiment_signals(id) ON DELETE SET NULL,
    score        DOUBLE PRECISION NOT NULL,
    regime_mult  DOUBLE PRECISION NOT NULL,
    ema_pass     BOOLEAN NOT NULL,
    decision     VARCHAR(20) NOT NULL,
    -- 'BUY' | 'SKIP_EMA' | 'SKIP_CAP' | 'SKIP_POSITION'
    -- (SKIP_THRESHOLD never appears: only symbols that passed the threshold are logged)
    order_id     TEXT,   -- Alpaca order UUID, NULL if not placed
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_execution_decisions_tick ON execution_decisions (tick_time DESC);
CREATE INDEX idx_execution_decisions_symbol ON execution_decisions (symbol, tick_time DESC);
```

### 1c. Table `trades`

One row per BUY order. Updated in-place when the position is closed (stop-loss or manual exit).

```sql
CREATE TABLE trades (
    id               BIGSERIAL PRIMARY KEY,
    symbol           VARCHAR(20) NOT NULL,
    signal_id        BIGINT REFERENCES sentiment_signals(id) ON DELETE SET NULL,
    decision_id      BIGINT REFERENCES execution_decisions(id) ON DELETE SET NULL,
    entry_order_id   TEXT NOT NULL,
    entry_price      DOUBLE PRECISION,   -- fill price from Alpaca; NULL until reconciled
    entry_time       TIMESTAMPTZ NOT NULL,
    entry_notional   DOUBLE PRECISION NOT NULL,
    score            DOUBLE PRECISION NOT NULL,
    regime_mult      DOUBLE PRECISION NOT NULL,
    exit_order_id    TEXT,
    exit_price       DOUBLE PRECISION,
    exit_time        TIMESTAMPTZ,
    exit_reason      VARCHAR(20),        -- 'stop_loss' | 'manual' | 'eod'
    qty              DOUBLE PRECISION,
    gross_pnl        DOUBLE PRECISION,   -- (exit_price - entry_price) * qty
    slippage_est     DOUBLE PRECISION,   -- entry_notional * 0.0005
    net_pnl          DOUBLE PRECISION,   -- gross_pnl - slippage_est
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_trades_symbol ON trades (symbol, entry_time DESC);
CREATE INDEX idx_trades_open ON trades (symbol) WHERE exit_time IS NULL;
CREATE INDEX idx_trades_closed ON trades (exit_time DESC) WHERE exit_time IS NOT NULL;
```

---

## 2. Sentiment Pipeline

**Goal:** link each `sentiment_signals` row to the `news_log` row that triggered it.

### Changes

**`pg_store.log_news_item()`** — currently returns `None`. Change return type to `int` (the inserted `news_log.id`). Uses `RETURNING id` on the INSERT.

**`pg_store.write_signal()`** — add optional parameter `news_log_id: int | None = None`. Writes to the new column.

**`pg_store.write_sentiment()`** in `redis_store` — add `signal_id` to the Redis payload so the execution worker can read it without a DB lookup.

**`process_news_item()` in `sentiment.py`** — updated call order:
```python
signal_id   = pg_store.write_signal(result)
news_log_id = pg_store.log_news_item(item, ticker, result.score)
if news_log_id:
    pg_store.link_signal_to_news(signal_id, news_log_id)
```
`link_signal_to_news` issues a single `UPDATE sentiment_signals SET news_log_id = %s WHERE id = %s` (cache-hot row, negligible cost).

The approach of writing signal first preserves the existing error boundary — a news_log write failure does not lose the signal.

---

## 3. Execution Worker

**Goal:** write one `execution_decisions` row per candidate per tick; write one `trades` row per BUY; update `trades` on stop-loss close.

### 3a. Decision log

After the EMA check, any symbol that reaches the final entry decision (regardless of outcome) writes a decision row. The `pg_store` call is inside the existing per-symbol `try/except` so a DB failure does not block the order.

`signal_id` is read from the Redis payload (added in §2 above).

### 3b. Trade open

Immediately after `trading_client.submit_order()` succeeds:
```python
pg_store.open_trade(
    symbol=symbol,
    signal_id=signal_id,
    decision_id=decision_id,
    entry_order_id=str(submitted_order.id),
    entry_time=datetime.now(timezone.utc),
    entry_notional=notional,
    score=score,
    regime_mult=regime_mult,
    qty=qty,        # None if notional-based order (no price available)
)
```

### 3c. Trade close

After `trading_client.close_position(symbol)` succeeds in the stop-loss block:
```python
pg_store.close_trade(
    symbol=symbol,
    exit_price=current_price,
    exit_time=datetime.now(timezone.utc),
    exit_reason='stop_loss',
)
```

`close_trade` finds the open trade by `symbol WHERE exit_time IS NULL` and updates it, computing P&L in SQL:
```sql
UPDATE trades SET
    exit_price   = %s,
    exit_time    = %s,
    exit_reason  = %s,
    gross_pnl    = (%s - entry_price) * qty,
    slippage_est = entry_notional * 0.0005,
    net_pnl      = ((%s - entry_price) * qty) - (entry_notional * 0.0005)
WHERE symbol = %s AND exit_time IS NULL
```

### 3d. Fill reconciliation (daily)

`run_daily_report` calls `pg_store.reconcile_trade_fills(trading_client)` which:
1. Fetches all `trades WHERE entry_price IS NULL AND entry_time > now() - 24h`
2. Queries Alpaca `GET /v2/orders/{entry_order_id}` for each
3. Updates `entry_price` and `qty` with the actual fill values

---

## 4. Weekly Report

New section appended to the existing `run_weekly_weights` Telegram message.

### Metrics

**P&L per trade:**
- Total closed trades (last 7 days)
- Win rate (% trades with net_pnl > 0)
- Avg gross P&L, avg slippage estimate, avg net P&L
- Alert ⚠️ if `avg_net_pnl < config.MIN_TRADE_PNL_THRESHOLD` (default: 5.0, configurable in `trading.yaml`)

**Frequency vs margin:**
- Trades/week, total notional deployed
- Gross P&L total, net P&L total, return on deployed notional
- Avg hold time (minutes)
- Estimated live slippage as % of gross P&L
- Alert ⚠️ if slippage estimate > 30% of gross P&L ("consider raising ENTRY_THRESHOLD")

New config key in `trading.yaml`:
```yaml
risk:
  min_trade_pnl_threshold: 5.0   # $ min net P&L per trade before warning
```

New helper `_format_trade_metrics_section(trades_summary: dict) -> str` in `performance.py`.
New PG query `fetch_trade_summary(days: int) -> dict` in `pg_store.py`.

---

## 5. API Endpoints

Added to `src/api/routes/trading.py` (already auth-gated at router level).

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/trades` | List trades. Query params: `symbol`, `status` (open/closed/all), `limit` (default 50) |
| GET | `/api/trades/summary` | Aggregated metrics. Query param: `days` (7/30/90, default 7) |
| GET | `/api/decisions` | Decision log. Query params: `symbol`, `limit` (default 20) |

Response shapes are flat dicts (no nested objects) to keep the frontend simple.

---

## 6. Frontend

### 6a. New page `Trades.tsx`

Added to navigation alongside existing Trading page.

**Top row — 4 summary cards:**
- Total trades (period selector: 7/30/90d)
- Win rate %
- Avg net P&L per trade
- Total net P&L

**Cumulative P&L chart** (recharts `LineChart`):
- X axis: trade close date
- Y axis: cumulative net P&L ($)
- Line color: green if current value > 0, red if < 0

**Trade table:**
- Columns: Symbol | Entry | Exit | Score | Regime | Entry $ | Exit $ | Hold | Net P&L | Exit reason
- Filters: symbol (text input), period (7/30/90d), status (open/closed/all)
- Row expand: shows news article title + source, LLM model used, signal_id

### 6b. Tab "Decision Log" in `Signals.tsx`

Second tab alongside existing signals view.

- Table: Tick time | Symbol | Score | Regime | EMA | Decision | Order ID
- Filter: symbol input
- Readable decision labels: "BUY", "Skip — below EMA", "Skip — cycle cap", "Skip — position open"
- Note: only symbols with score > ENTRY_THRESHOLD appear here; symbols skipped earlier (stale, fallback, below threshold) are not logged

### 6c. Section in `Performance.tsx`

Below existing IC/ICIR metrics:

- Bar chart (recharts `BarChart`): trades per week, last 8 weeks
- Bar chart: win rate per week, last 8 weeks

---

## Out of Scope

- Sell-side signals (system is long-only for paper trading phase)
- Frontend dashboard for live P&L curve (post-live)
- Per-sector analysis
- Slippage model more sophisticated than flat 0.05% (revisit post-live with real fill data)
