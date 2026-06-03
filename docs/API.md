# API Reference — Alembic LLM Trading System

**FastAPI REST API**
**Version:** 3.0.0
**Updated:** 2026-06-03

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

Daily P&L from Alpaca account history.

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
| 3.0.0 | 2026-06-03 | Full English rewrite; Phase G portfolio, risk, decay endpoints; new admin/llm-models, config endpoints |
| 2.0.0 | 2026-05-12 | Added GET /api/weights/suggestion; updated POST /api/weights/approve |
| 1.0.0 | 2026-05-04 | Initial release |
