# API Reference — Alembic LLM Trading System

**FastAPI REST API**
**Version:** 1.0.0
**Updated:** 2026-06-26

---

## Overview

Alembic exposes REST endpoints for:
- Querying sentiment signals (public)
- Admin controls: kill-switch, mode, LLM model selection (authenticated)
- Performance reports and ensemble weights (mixed auth)
- Portfolio and P&L data (public)
- Strategy and backtest management

### Base URLs

```
Development:  http://localhost:8001
Production:   https://api.your-domain.com
```

### Authentication

| Endpoint group | Auth Required | Header |
|----------------|---------------|--------|
| `/api/signals/*` | No | — |
| `/api/performance/*` | No | — |
| `/api/weights/current`, `/api/weights/suggestion` | No | — |
| `/api/weights/approve` | **Yes** | `X-API-Key` |
| `/api/admin/*` | **Yes** | `X-API-Key` |
| `/api/trades/*` | **Yes** | `X-API-Key` |
| `/api/system/decisions` | **Yes** | `X-API-Key` |
| `/api/system/readiness` | **Yes** | `X-API-Key` |
| `/api/system/scheduler` | **Yes** | `X-API-Key` |
| `/api/system/activity` | **Yes** | `X-API-Key` |
| `/api/health` | No | — |

Generate an API key (minimum 32 characters):
```bash
openssl rand -hex 20
# Set as ADMIN_API_KEY in .env
```

---

## Signal Endpoints

### `GET /api/signals`

Get latest signals for all watchlist symbols. Falls back to PostgreSQL for any symbols not in Redis cache.

**Query parameters:** `symbol` (optional, filter to one symbol)

**Response 200:**
```json
[
  {
    "symbol": "AAPL",
    "score": 0.42,
    "confidence": 0.78,
    "reasoning": "Strong bullish tone from earnings beat",
    "model_id": "ensemble:kimi-k2.6+qwen3.5+deepseek-v4-pro+glm-5.1",
    "ensemble_std": 0.11,
    "fallback_used": false,
    "generated_at": "2026-06-03T10:30:00Z"
  }
]
```

### `GET /api/signals/{symbol}`

Get latest signal for a single symbol (Redis → PostgreSQL fallback).

**Response 404:** `{"detail": "No signal found for symbol: AAPL"}`

### `GET /api/signals/history`

Paginated signal history from PostgreSQL.

**Query parameters:** `symbol` (required), `limit` (default 50, max 500), `offset` (default 0)

```bash
curl "http://localhost:8001/api/signals/history?symbol=AAPL&limit=100"
```

---

## Admin Endpoints

All admin endpoints require `X-API-Key` header.

### `POST /api/admin/killswitch`

Immediately halts all trading. Sets `killswitch_active=1` and `system:mode=halted` in Redis.

```bash
curl -X POST http://localhost:8001/api/admin/killswitch \
  -H "X-API-Key: $ADMIN_API_KEY"
```

**Response:** `{"killswitch": "activated", "mode": "halted"}`

### `GET /api/admin/mode`

Get current operating mode (no auth required).

**Response:** `{"mode": "paper"}`

### `POST /api/admin/mode`

Set operating mode.

**Valid modes:** `backtest`, `paper`, `semi_auto`, `full_auto`, `halted`, `dry_run`

```bash
curl -X POST http://localhost:8001/api/admin/mode \
  -H "X-API-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"mode": "paper"}'
```

### `GET /api/admin/status`

System status snapshot (no auth): kill-switch state, operating mode, LLM model selection.

```json
{"killswitch": false, "mode": "paper", "llm_models": "all"}
```

### `POST /api/admin/llm-models`

Restrict which models run in the ensemble (for token-budget savings).

```bash
curl -X POST http://localhost:8001/api/admin/llm-models \
  -H "X-API-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"models": "kimi,deepseek"}'
```

Valid values: `all`, `kimi`, `qwen`, `deepseek`, `glm` (comma-separated subset).

---

## Performance Endpoints

### `GET /api/performance/latest`

Latest PerformanceWorker report from Redis (IC, ICIR, drift alerts, post-mortems).

**Response 404:** no report computed yet (daily worker hasn't run).

### `GET /api/weights/current`

Current ensemble weights. Returns defaults (equal 0.25 each) if no weights have been set.

```json
{
  "weights": {
    "kimi-k2.6:cloud": 0.25,
    "qwen3.5:cloud": 0.25,
    "deepseek-v4-pro:cloud": 0.25,
    "glm-5.1:cloud": 0.25
  },
  "source": "default"
}
```

`source` values: `auto_apply`, `telegram`, `suggestion`, `override`, `default`

### `GET /api/weights/suggestion`

Current weight suggestion from LOO ICIR (if available, expires after 7 days).

```json
{
  "suggested_weights": {"kimi-k2.6:cloud": 0.32, "...": "..."},
  "purified_icir": {"kimi-k2.6:cloud": 1.15, "...": "..."},
  "freeze_reason": "VIX = 32.4 >= 30.0",
  "computed_at": "2026-06-02T04:00:12Z",
  "expires_at": "2026-06-09T04:00:12Z"
}
```

`freeze_reason` is an empty string when all guardrails pass.

### `POST /api/weights/approve`

Apply weight suggestion or force custom weights. Requires `X-API-Key`.

```json
{
  "override_weights": null,
  "note": "Manual approval post-NVDA earnings"
}
```

- `override_weights: null` → apply current suggestion (403 if `freeze_reason` non-empty)
- `override_weights: {...}` → force custom weights (bypasses freeze guardrails)

Validation: each weight in `[0.10, 0.70]`, sum = 1.0 ± 0.001, model IDs in `MODEL_COSTS`.

**Response:**
```json
{"applied_weights": {"kimi-k2.6:cloud": 0.30, "...": "..."}, "source": "suggestion", "log_id": 42}
```

### `GET /api/performance/pnl`

Daily P&L from Alpaca account portfolio history (equity-based, not trade-by-trade).

**Query parameters:** `period` (default `6M` — valid values: `1M`, `3M`, `6M`, `1Y`)

**Response 200:**
```json
{
  "daily": [{"date": "2026-06-25", "equity": 98500.0, "profit_loss": 47.55}],
  "monthly": [{"month": "2026-06", "pnl": 27.98}]
}
```

### `GET /api/performance/daily`

Per-day P&L breakdown from the local `trades` table (not Alpaca). Returns trade-level detail with per-day aggregation. Use this for forensic analysis of specific days or date ranges.

**Query parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `from_date` | `YYYY-MM-DD` | today − `days` | Inclusive start date |
| `to_date` | `YYYY-MM-DD` | today | Inclusive end date |
| `days` | int | 7 | Shortcut: last N days (ignored if `from_date`/`to_date` supplied) |

Max range: 365 days.

**Response 200:**
```json
{
  "from_date": "2026-06-24",
  "to_date": "2026-06-26",
  "days": [
    {
      "date": "2026-06-24",
      "trades_closed": 4,
      "total_gross_pnl": -19.09,
      "total_costs": -0.48,
      "total_net_pnl": -19.57,
      "winners": 0,
      "losers": 4,
      "trades": [
        {
          "symbol": "CAT",
          "entry_time": "2026-06-23T18:52:00Z",
          "exit_time": "2026-06-24T14:07:00Z",
          "entry_price": 982.99,
          "exit_price": 1037.60,
          "qty": 0.2857,
          "gross_pnl": 15.60,
          "net_pnl": 15.10,
          "exit_reason": "portfolio_sell"
        }
      ]
    }
  ],
  "summary": {
    "total_gross_pnl": 28.94,
    "total_costs": -0.96,
    "total_net_pnl": 27.98,
    "total_trades": 13,
    "winners": 4,
    "losers": 9,
    "win_rate": 0.3077,
    "positive_days": 1,
    "negative_days": 1
  }
}
```

**Campi per giornata:**

| Campo | Calcolo SQL | Descrizione |
|-------|------------|-------------|
| `total_gross_pnl` | `SUM(COALESCE(gross_pnl, net_pnl))` | P&L prima dei costi di transazione. `COALESCE` gestisce trade precedenti alla migration che hanno `gross_pnl = NULL` |
| `total_costs` | `SUM(gross_pnl − net_pnl)` | Erosione da slippage + spread stimati. Sempre ≤ 0. Zero per trade con `gross_pnl = NULL` |
| `total_net_pnl` | `SUM(net_pnl)` | Risultato effettivo dopo i costi |
| `winners` | `COUNT(net_pnl > 0)` | Trade chiusi in profitto |
| `losers` | `COUNT(net_pnl < 0)` | Trade chiusi in perdita |

**Campi per singolo trade (array `trades`):**

| Campo | Descrizione |
|-------|-------------|
| `symbol` | Ticker symbol |
| `entry_time` / `exit_time` | Timestamp ISO-8601 UTC |
| `entry_price` / `exit_price` | Prezzi di entrata/uscita |
| `qty` | Quantità |
| `gross_pnl` | P&L lordo prima dei costi (`null` per trade pre-migration) |
| `net_pnl` | P&L netto dopo i costi |
| `costs` | Calcolato dal frontend: `gross_pnl − net_pnl` (non nel payload JSON) |
| `exit_reason` | Motivo di chiusura (es. `portfolio_sell`, `stop_loss`) |
```

**Example:**
```bash
curl -H "X-API-Key: $ADMIN_API_KEY" \
  "http://localhost:8001/api/performance/daily?from_date=2026-06-24&to_date=2026-06-26"
```

**Note:** `total_net_pnl` may differ slightly from Alpaca's `profit_loss` because Alpaca calculates equity delta (includes unrealized P&L movements) while this endpoint sums `net_pnl` from closed trade records only.

### `GET /api/performance/weekly`

Structured weekly report from Redis cache (computed every Monday at 04:00 UTC, TTL 9 days). Enriched at read-time with live Alpaca account data and latest Redis regime state.

**Response 200:** See `WeeklyReport` TypeScript type in `frontend/src/api/performance.ts` for full schema. Sections: `trade_pnl`, `capital_efficiency`, `regime`, `feedback`, `infrastructure`, `weights`.

**Response 404:** No weekly report cached yet (first Monday hasn't run, or cache expired).

### `GET /api/performance/positions`

Current open positions from Alpaca.

---

## Portfolio Endpoints

### `GET /api/portfolio/cycles`

Recent portfolio orchestration cycles (strategy run, orders before/after constraints).

### `GET /api/portfolio/risk`

Latest risk report (Herfindahl index, combined drawdown, per-strategy metrics, alerts).

### `GET /api/portfolio/decay`

Latest decay monitor report (actual vs backtest baseline per strategy).

---

## News and LLM Endpoints

### `GET /api/news/recent`

Recent ingested news items from `news_log`. Query params: `ticker`, `source`, `limit`.

### `GET /api/llm/feedback`

Per-model LLM outputs joined to signals (for model quality analysis). Query params: `ticker`, `model_id`, `limit`.

---

## Backtest Endpoints

### `GET /api/backtest/runs`

List backtest run summaries from `backtest_signals`.

### `GET /api/backtest/runs/{run_id}/signals`

Signals for a specific backtest run.

### `GET /api/backtest/runs/{run_id}/report`

IC/ICIR backtest report for a specific run.

---

## Config Endpoint

### `GET /api/config`

Read operational config from `config/trading.yaml` (symbols watchlist, thresholds).

### `POST /api/config`

Update operational config (requires `X-API-Key`). Validates YAML structure before writing.

---

## Error Responses

All errors return `{"detail": "..."}`.

| Code | Meaning |
|------|---------|
| 400 | Invalid parameters |
| 401 | Missing or invalid API key |
| 403 | Frozen (guardrail active, no override provided) |
| 404 | Resource not found |
| 422 | Validation failed (weights, mode values) |
| 500 | Internal server error |

---

---

## Trades & Analytics Endpoints

All require `X-API-Key` header.

### `GET /api/trades`

List closed and/or open trades.

**Query parameters:** `symbol` (optional), `status` (`all` | `open` | `closed`, default `all`), `limit` (default 100, max 500)

**Response 200:**
```json
[
  {
    "id": 7,
    "symbol": "NVDA",
    "signal_id": 42,
    "decision_id": 18,
    "entry_order_id": "abc123",
    "entry_price": 200.0,
    "entry_time": "2026-06-05T14:30:00Z",
    "entry_notional": 1000.0,
    "score": 0.45,
    "regime_mult": 1.0,
    "exit_price": 196.0,
    "exit_time": "2026-06-05T16:00:00Z",
    "exit_reason": "stop_loss",
    "qty": 5.0,
    "gross_pnl": -20.0,
    "slippage_est": 0.5,
    "net_pnl": -20.5,
    "postmortem_diagnosis": "LOW_CONFIDENCE_PASSED",
    "created_at": "2026-06-05T14:30:01Z"
  }
]
```

### `GET /api/trades/summary`

Aggregated trade statistics for a rolling window.

**Query parameters:** `days` (default 30, max 365)

**Response 200:**
```json
{
  "total_trades": 12,
  "win_rate": 0.583,
  "avg_gross_pnl": 8.20,
  "avg_slippage_est": 0.50,
  "avg_net_pnl": 7.70,
  "total_gross_pnl": 98.4,
  "total_net_pnl": 92.4,
  "total_notional": 12000.0,
  "avg_hold_minutes": 87.5,
  "trades_per_week": 2.8,
  "return_on_notional": 0.0077,
  "slippage_pct_of_gross": 0.061
}
```

### `GET /api/trades/analytics/by-symbol`

P&L aggregated by symbol. Analytics-on-read (SQL GROUP BY, no cache).

**Query parameters:** `days` (default 90, 1–365)

**Response 200:**
```json
[
  {"label": "NVDA", "trade_count": 5, "win_rate": 0.6, "avg_net_pnl": 12.5, "total_net_pnl": 62.5}
]
```

### `GET /api/trades/analytics/by-dimension`

P&L aggregated by the requested dimension.

**Query parameters:** `dim` (required: `regime` | `hour` | `score` | `holdtime`), `days` (default 90)

| `dim` value | Grouping |
|-------------|----------|
| `regime` | regime_mult bucket: bear/caution/neutral/bull/strong_bull |
| `hour` | hour of day 9–16 EST |
| `score` | LLM score 0.1-wide bins (0.3–0.4, 0.4–0.5, …) |
| `holdtime` | hold duration: `<1h` / `1-4h` / `4-8h` / `extended` / `overnight` |

**Response 200:** same shape as `by-symbol` — `[{label, trade_count, win_rate, avg_net_pnl, total_net_pnl}]`

**Response 422:** invalid `dim` value.

### `GET /api/trades/postmortem/{trade_id}`

Full trade row joined with signal fields. Used to surface postmortem diagnosis detail.

**Response 200:**
```json
{
  "id": 7, "symbol": "NVDA",
  "entry_time": "2026-06-05T14:30:00Z", "exit_time": "2026-06-05T16:00:00Z",
  "entry_price": 200.0, "exit_price": 196.0, "net_pnl": -20.5,
  "score": 0.45, "regime_mult": 1.0, "exit_reason": "stop_loss",
  "confidence": 0.35, "ensemble_std": 0.08,
  "signal_generated_at": "2026-06-05T14:00:00Z",
  "postmortem_diagnosis": "LOW_CONFIDENCE_PASSED"
}
```

**Response 404:** trade not found.

---

## Feedback Loop Endpoint (Phase B)

Requires `X-API-Key` header.

### `GET /api/feedback/status`

Returns the current loss-feedback adjustments active in Redis. If no adjustment is active, returns baseline values.

**Response 200:**
```json
{
  "entry_threshold": 0.35,
  "entry_threshold_baseline": 0.30,
  "regime_scale": 0.80,
  "adjustment_active": true,
  "last_adjustment_ts": "2026-06-06T15:00:00Z",
  "last_reason": "3 consecutive losses",
  "consecutive_losses": 3,
  "rolling_net_pnl": -42.50
}
```

| Field | Type | Description |
|-------|------|-------------|
| `entry_threshold` | float | Effective entry threshold (baseline or Redis override) |
| `entry_threshold_baseline` | float | Module constant baseline (default 0.30) |
| `regime_scale` | float | Regime multiplier scaling factor (1.0 = no adjustment) |
| `adjustment_active` | bool | True if any Redis override is currently set |
| `last_adjustment_ts` | string\|null | ISO-8601 timestamp of last adjustment |
| `last_reason` | string\|null | Human-readable trigger description |
| `consecutive_losses` | int\|null | Loss streak that triggered the adjustment |
| `rolling_net_pnl` | float\|null | Rolling net P&L (last N trades) at trigger time |

When `adjustment_active = false` all values reflect the static module defaults.

---

## Counterfactual Analytics Endpoint (Phase C)

Requires `X-API-Key` header.

### `GET /api/trades/analytics/counterfactual`

Aggregate opportunity-cost statistics for skipped signals. Returns one row per skip decision type with 1-hour forward return stats computed nightly.

**Query parameters:** `days` (int, default 7, range 1–90)

**Response 200:**
```json
[
  {
    "decision": "SKIP_EMA",
    "total_skips": 42,
    "computed": 38,
    "avg_return": 0.0031,
    "pct_profitable": 0.526,
    "sum_positive_returns": 0.142
  },
  {
    "decision": "SKIP_CAP",
    "total_skips": 15,
    "computed": 15,
    "avg_return": -0.0008,
    "pct_profitable": 0.467,
    "sum_positive_returns": 0.038
  }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `decision` | string | `SKIP_EMA` or `SKIP_CAP` |
| `total_skips` | int | Total skipped signals in the window |
| `computed` | int | Skips with a 1h return computed (Alpaca bars available) |
| `avg_return` | float | Mean 1-hour return if entry had been taken |
| `pct_profitable` | float | Fraction of skips where 1h return > 0 |
| `sum_positive_returns` | float | Sum of all positive 1h returns (upside missed) |

`SKIP_POSITION` (already in position) is excluded — it is not a missed opportunity.

Returns `[]` until the first nightly `counterfactual-worker` run at 22:45 UTC.

---

## Decisions Endpoint

Requires `X-API-Key` header.

### `GET /api/system/decisions`

Execution decision log — one row per symbol per tick for every symbol that cleared `ENTRY_THRESHOLD`. Returns data from the `execution_decisions` PostgreSQL table; does NOT call the live broker.

**Query parameters:** `limit` (default 30, max 500)

**Response 200:**
```json
[
  {
    "id": 18,
    "tick_time": "2026-06-05T14:30:00Z",
    "symbol": "NVDA",
    "score": 0.45,
    "regime_mult": 1.0,
    "ema_pass": true,
    "decision": "BUY",
    "order_id": "abc123",
    "reason": "S4 sentiment score 0.45 > threshold 0.30; price above EMA20",
    "created_at": "2026-06-05T14:30:01Z"
  }
]
```

Decision labels: `BUY`, `SKIP_EMA` (price below EMA20), `SKIP_CAP` (position cap reached), `SKIP_POSITION` (already in position), `STOP_LOSS` (stop triggered).

---

## PEAD Routes

### `GET /api/pead/signals`

Segnali PEAD recenti (8-K filing classificati). Richiede `X-API-Key`.

**Query parameters:** `limit` (default 50, max 200), `symbol` (optional)

**Response 200:**
```json
[
  {
    "id": 1,
    "symbol": "AAPL",
    "score": 0.72,
    "direction": "positive",
    "confidence": 0.72,
    "category": "earnings_beat",
    "filing_url": "https://www.sec.gov/...",
    "classified_at": "2026-06-17T14:35:00Z"
  }
]
```

### `GET /api/pead/events`

Eventi earnings classificati (aggregati per simbolo). Richiede `X-API-Key`.

---

## System Routes

All `/api/system/*` endpoints require `X-API-Key` header.

### `GET /api/system/readiness` *(P2-04)*

Operator cockpit: aggregates 8 health/alert flags from Redis and PostgreSQL. Always returns HTTP 200 — inspect the body fields to determine health. A 200 response does NOT guarantee all systems are healthy.

**Response 200:**
```json
{
  "redis_healthy": true,
  "redis_writeable": true,
  "db_healthy": true,
  "killswitch_active": false,
  "stale_signals": false,
  "worker_beat_lag": false,
  "last_signal_age_minutes": 12.4,
  "last_cycle_age_minutes": 45.2
}
```

| Field | Healthy value | Meaning when unhealthy |
|-------|--------------|------------------------|
| `redis_healthy` | `true` | Redis PING failed — signal cache unreachable |
| `redis_writeable` | `true` | Redis MISCONF / AOF error — signals cannot be written |
| `db_healthy` | `true` | PostgreSQL query failed — audit trail unavailable |
| `killswitch_active` | `false` | Kill-switch is active — all order submission halted |
| `stale_signals` | `false` | Last sentiment signal older than 2 hours |
| `worker_beat_lag` | `false` | Last portfolio cycle older than 60 minutes |
| `last_signal_age_minutes` | any float | Minutes since last signal (null if no signals ever) |
| `last_cycle_age_minutes` | any float | Minutes since last cycle (null if no cycles ever) |

See `docs/RUNBOOK_OPERATOR_COCKPIT.md` (or `docs/operations.md` Cockpit Runbooks section) for remediation steps.

### `GET /api/system/decisions` *(P2-04)*

Recent execution decisions from `execution_decisions` table. Same data as the Decisions Endpoint above, via system router. Requires `X-API-Key`.

**Query parameters:** `limit` (default 30)

### `GET /api/system/scheduler`

Beat schedule with last-run timestamps from DB. Returns the static Celery beat schedule enriched with the most recent `MAX(timestamp)` from each task's DB table.

### `GET /api/system/activity`

Unified activity log — recent portfolio cycles, sentiment runs, news ingestion events, and trade decisions, sorted by time descending.

**Query parameters:** `limit` (default 60)

---

## Labeling Endpoints (QX-01 golden label set)

Offline/admin (require API key). Blind annotation: `next` never returns the system's extracted tickers.

### `GET /api/labeling/progress`

```json
{ "labeled": 17, "pending": 131, "total": 148 }
```

### `GET /api/labeling/next`

Next pending article — **blind** (no extracted tickers). Returns `{ "done": true }` when none remain.

```json
{ "done": false, "label_id": 1, "source": "marketaux", "title": "...", "body_snippet": "...", "published_at": "2025-11-01T00:00:00Z", "text_adequacy": "full" }
```

### `POST /api/labeling/{label_id}`

Save human ground truth; marks the row labeled.

**Body:** `gt_tickers` (list, [] = none), `gt_relevance` (company_specific|sector|macro|irrelevant), `gt_sentiment_dir` (positive|negative|neutral), `gt_sentiment_strength` ([-1,1]), `gt_rationale` (optional).

---

## Quality Endpoint (QX-02)

### `GET /api/quality/metrics`

Read-only sentiment + extraction quality. **Query parameters:** `days` (default 14).

```json
{
  "window_days": 14,
  "per_model": [ { "model_id": "kimi-k2.6:cloud", "n": 911, "mean_polarity": 0.044, "mean_confidence": 0.661, "near_zero_rate": 0.188, "eligible_rate": 1.0 } ],
  "signals": { "near_zero_rate": 0.341, "fallback_rate": 0.236, "mean_ensemble_std": 0.05 },
  "extraction": { "n_labeled": 17, "precision": 0.24, "recall": 0.40, "recall_in_watchlist": 1.0, "fp_per_article": 1.12, "macro_fp_per_article": 2.0 }
}
```

---

## Health Check

### `GET /api/health`

```json
{"status": "healthy", "redis": "connected", "postgres": "connected"}
```

Returns 503 if any dependency is unreachable.

---

## OpenAPI

- Swagger UI: `http://localhost:8001/docs`
- ReDoc: `http://localhost:8001/redoc`
- JSON schema: `http://localhost:8001/openapi.json`

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 6.1.1 | 2026-06-26 | GET /api/performance/daily: trade-level detail now includes Costi column (gross_pnl − net_pnl per trade) in frontend drill-down |
| 6.1.0 | 2026-06-26 | GET /api/performance/daily: add total_gross_pnl and total_costs fields (gross/net breakdown); remove gross_profit/gross_loss fields |
| 6.0.0 | 2026-06-26 | GET /api/performance/daily (per-day P&L from trades table, with trade-level detail); documented GET /api/performance/weekly and GET /api/performance/pnl schemas |
| 5.0.0 | 2026-06-06 | Phase B: GET /api/feedback/status; Phase C: GET /api/trades/analytics/counterfactual |
| 4.0.0 | 2026-06-06 | Phase A analytics: trades, decisions, analytics/by-symbol, analytics/by-dimension, postmortem endpoints; kill switch GET+DELETE; trades/decisions require auth |
| 3.0.0 | 2026-06-03 | Full English rewrite; Phase G portfolio, risk, decay endpoints; new admin/llm-models, config endpoints |
| 2.0.0 | 2026-05-12 | Added GET /api/weights/suggestion; updated POST /api/weights/approve |
| 1.0.0 | 2026-05-04 | Initial release |
