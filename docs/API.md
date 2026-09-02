# API Reference — Alembic LLM Trading System

**FastAPI REST API**
**Version:** 1.0.0
**Updated:** 2026-08-13

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
| `/api/orders` | **Yes** | `X-API-Key` |
| `/api/decisions` | **Yes** | `X-API-Key` |
| `/api/trades/*` | **Yes** | `X-API-Key` |
| `/api/system/decisions` | **Yes** | `X-API-Key` |
| `/api/system/readiness` | **Yes** | `X-API-Key` |
| `/api/system/scheduler` | **Yes** | `X-API-Key` |
| `/api/system/activity` | **Yes** | `X-API-Key` |
| `/api/mobile/v1/*` | **Monitor routes only** | `Authorization: Bearer <mobile-access-token>` |
| `/api/health` | No | — |

Generate an API key (minimum 32 characters):
```bash
openssl rand -hex 20
# Set as ADMIN_API_KEY in .env
```

### Browser admin security

The browser admin API is same-origin by default. Cross-origin clients must be
allowlisted explicitly; `*` is rejected at startup. Admin login attempts share
budgets by normalized username and source, while mode changes and kill-switch
activation are limited per source and endpoint. All limits are backed by Redis,
return `429` with `Retry-After` when exhausted, and fail closed with `503` if the
limiter is unavailable.

```dotenv
CORS_ALLOWED_ORIGINS=https://operator.example
API_LOGIN_RATE_LIMIT=5
API_LOGIN_RATE_WINDOW_SECONDS=300
API_ADMIN_ACTION_RATE_LIMIT=5
API_ADMIN_ACTION_RATE_WINDOW_SECONDS=60
```

---

## Mobile monitor authentication

Mobile identities are provisioned separately from the admin account. Their
short-lived JWTs use `aud=alembic-mobile`, are bound to a monitor user, device,
server session, and JTI, and cannot authenticate to Alembic mutation routes.

| Method | Endpoint | Authentication | Purpose |
|---|---|---|---|
| `POST` | `/api/mobile/v1/auth/login` | Username/password | Create a device-bound access/refresh session |
| `POST` | `/api/mobile/v1/auth/refresh` | Refresh token | Atomically rotate the refresh session |
| `POST` | `/api/mobile/v1/auth/logout` | Mobile bearer + refresh token | Revoke device sessions and clear push registration best effort |
| `GET` | `/api/mobile/v1/auth/me` | `monitor:read` | Return the monitor identity |
| `POST` | `/api/mobile/v1/devices` | `monitor:device` | Idempotently register/update an installation |
| `DELETE` | `/api/mobile/v1/devices/{device_id}` | `monitor:device` | Revoke an owned device and its sessions |

Access tokens expire after 15 minutes by default. Opaque refresh tokens expire
after 30 days, are stored only as hashes, rotate on every use, and revoke their
whole family when reuse is detected. Login attempts are limited independently
by normalized username and source address; `429` includes `Retry-After`.

Mobile v1 errors use one stable envelope:

```json
{
  "error": {
    "code": "invalid_credentials",
    "message": "Invalid credentials",
    "request_id": "b44f39f4-882e-4230-827f-418fc613aa3a",
    "retryable": false,
    "details": {}
  }
}
```

Relevant environment settings:

```dotenv
MOBILE_ACCESS_TOKEN_EXPIRE_MINUTES=15
MOBILE_REFRESH_TOKEN_EXPIRE_DAYS=30
MOBILE_LOGIN_RATE_LIMIT=5
MOBILE_LOGIN_RATE_WINDOW_SECONDS=300
MOBILE_TOKEN_PEPPER=
```

Provision and revoke monitor access only from the server:

```bash
# Interactive password input; plaintext is not printed or put in shell history.
uv run python scripts/manage_monitor_users.py create --username mobile-operator

uv run python scripts/manage_monitor_users.py disable --username mobile-operator
uv run python scripts/manage_monitor_users.py enable --username mobile-operator
uv run python scripts/manage_monitor_users.py revoke-all --username mobile-operator
uv run python scripts/manage_monitor_users.py revoke-session --session-id <uuid>
uv run python scripts/manage_monitor_users.py revoke-device --device-id <uuid>
```

The command output contains identifiers only; it never prints passwords,
refresh tokens, or token hashes.

---

## Mobile monitor read API

All four routes require a mobile bearer token with `monitor:read`. They are
read-only projections: HTTP requests read Redis/PostgreSQL and never contact
Alpaca. Successful responses include `contract_version`, `as_of`,
`data_age_seconds`, `currency`, `min_supported_app_version`, and
`latest_app_version`. Send `If-None-Match` with the returned weak `ETag` to
receive `304` when the domain data is unchanged.

The snapshot/positions reader chooses the newest coherent bundle across the
atomic Redis document and its PostgreSQL fallback. This keeps a detected
Redis-read-only degradation visible even when the primary cache cannot accept
the replacement document; normal stale-safety ceilings still apply.

### `GET /api/mobile/v1/snapshot`

Returns one server-built monitoring snapshot. `snapshot_id` and `as_of` are
shared with the positions projection produced by the same broker read.

**Query parameters:** none.

```json
{
  "contract_version": 1,
  "snapshot_id": "f3119d0a-4395-4320-9783-89a8bbc8024a",
  "as_of": "2026-07-23T14:05:00Z",
  "data_age_seconds": 12,
  "currency": "USD",
  "min_supported_app_version": "1.0.0",
  "latest_app_version": "1.0.0",
  "operational": {
    "state": "operational",
    "primary_reason": null,
    "mode": "paper",
    "market_phase": "open",
    "market_timezone": "America/New_York",
    "pipeline_expected": true,
    "next_expected_activity_at": "2026-07-23T20:00:00Z",
    "active_incident_count": 0
  },
  "portfolio": {
    "nav": 110307.36,
    "cash": 76998.12,
    "gross_exposure": 0.30201,
    "unrealized_pnl": -97.14
  },
  "pipeline": {
    "database": {"status": "fresh", "age_seconds": 0},
    "redis": {"status": "fresh", "age_seconds": 0, "writeable": true},
    "signal": {
      "status": "fresh",
      "age_seconds": 180,
      "freshness_budget_seconds": 900,
      "stale_after_seconds": 1380
    }
  },
  "strategies": [],
  "degradations": []
}
```

An absent or unsafe stale snapshot returns `503 snapshot_unavailable`; broker
or dependency failures are represented as nullable values plus degradations,
never invented zero NAV.

Scheduled pipeline components expose their server-configured freshness budget
and stale threshold in seconds. Android must render these values rather than
duplicating schedule constants.

### `GET /api/mobile/v1/performance`

Returns anchored broker-NAV performance, drawdown, realized trade P&L, and the
exposure-adjusted SPY benchmark. Benchmark values are all `null` with a
degradation when SPY or exposure history is unavailable.

**Query parameters:** `period` — `1w`, `1m` (default), `3m`, `6m`, `1y`, or
`all`.

```json
{
  "contract_version": 1,
  "as_of": "2026-07-23T14:05:00Z",
  "data_age_seconds": 12,
  "currency": "USD",
  "min_supported_app_version": "1.0.0",
  "latest_app_version": "1.0.0",
  "period": "1m",
  "period_start": "2026-06-23T14:05:00Z",
  "period_end": "2026-07-23T14:05:00Z",
  "history_data_age_seconds": 300,
  "benchmark_data_age_seconds": 64800,
  "summary": {
    "nav_start": 109850.0,
    "nav_end": 110307.36,
    "portfolio_return": 0.004164,
    "max_drawdown": 0.0182,
    "benchmark_return": 0.006027,
    "alpha": -0.001863
  },
  "points": [
    {
      "at": "2026-06-23T20:00:00Z",
      "nav": 109850.0,
      "drawdown": 0.0,
      "benchmark_nav": 109850.0
    }
  ],
  "degradations": []
}
```

### `GET /api/mobile/v1/positions`

Returns current positions sorted by worst unrealized return, then absolute
market value. Weights and gross exposure use absolute market values.

**Query parameters:** none.

```json
{
  "contract_version": 1,
  "snapshot_id": "f3119d0a-4395-4320-9783-89a8bbc8024a",
  "as_of": "2026-07-23T14:05:00Z",
  "data_age_seconds": 12,
  "currency": "USD",
  "min_supported_app_version": "1.0.0",
  "latest_app_version": "1.0.0",
  "summary": {
    "count": 1,
    "market_value": 6234.1,
    "unrealized_pnl": -77.88,
    "gross_exposure": 0.0565
  },
  "items": [
    {
      "symbol": "MSFT",
      "qty": 12.3456,
      "market_value": 6234.1,
      "position_weight": 0.0565,
      "unrealized_pnl": -77.88,
      "unrealized_return": -0.01234
    }
  ],
  "degradations": []
}
```

### `GET /api/mobile/v1/events`

Returns safe incident, order, position, and significant `BUY`/`SELL`/`HALT`
decision events. Normal `SKIP*` chatter is excluded. Pagination order is
`(occurred_at DESC, id DESC)` and `next_cursor` is opaque and HMAC-signed.

**Query parameters:** `category` (`all`, `critical`, `trading`, `system`;
default `all`), `days` (1–30; default 7), `cursor` (optional), and `limit`
(1–200; default 50).

```json
{
  "contract_version": 1,
  "as_of": "2026-07-23T14:05:00Z",
  "data_age_seconds": 0,
  "currency": "USD",
  "min_supported_app_version": "1.0.0",
  "latest_app_version": "1.0.0",
  "items": [
    {
      "id": "0e8b54ce-a9cf-4025-98d1-65fe0e915c62",
      "kind": "alert_incident",
      "category": "system",
      "severity": "critical",
      "status": "open",
      "occurred_at": "2026-07-23T14:00:00Z",
      "updated_at": "2026-07-23T14:05:00Z",
      "title": "Ciclo di portafoglio in ritardo",
      "history": [{"state": "open", "at": "2026-07-23T14:00:00Z"}]
    }
  ],
  "next_cursor": null
}
```

All routes return `426 upgrade_required` when `X-App-Version` is below
`min_supported_app_version`. Invalid query values/cursors return the mobile v1
error envelope with `400`; authentication failures return `401`/`403`.

---

## Signal Endpoints

### `GET /api/signals`

Get latest signals for all watchlist symbols. Falls back to PostgreSQL for any symbols not in Redis cache.
When `news_id` is provided, returns historical signals linked to that `news_log.id` instead of the latest watchlist view. This is used by the News trace links so a news row never points to an empty latest-signal page when its signal is historical.
When `signal_id` is provided, returns the exact historical signal row. This is used by Trading/Decision trace links when the originating signal is known but the news row is missing.

**Query parameters:** `symbol` (optional, filter to one symbol), `news_id` (optional, historical trace for one news row), `signal_id` (optional, exact historical signal)

**Response 200:**
```json
[
  {
    "symbol": "AAPL",
    "score": 0.42,
    "confidence": 0.78,
    "reasoning": "Strong bullish tone from earnings beat",
    "model_id": "ensemble:glm-5.2:cloud+gpt-oss:20b-cloud",
    "ensemble_std": 0.11,
    "fallback_used": false,
    "generated_at": "2026-06-03T10:30:00Z"
  }
]
```

### `GET /api/signals/{symbol}`

Get latest signal for a single symbol (Redis → PostgreSQL fallback).

**Response 404:** `{"detail": "No signal found for symbol: AAPL"}`

### ~~`GET /api/signals/history`~~ — NON ESISTE

> **Rimosso dalla documentazione il 2026-09-02.** Questa rotta non e' mai stata registrata:
> `src/api/routes/signals.py` espone solo `GET ""` e `GET "/{symbol}"`. Peggio, una chiamata a
> `/api/signals/history` non da' 404 di rotta ma viene catturata da `/{symbol}` con
> `symbol="history"`, quindi risponde `404 No signal found for symbol: history` — un messaggio
> che sembra "nessun dato" invece di "endpoint inesistente".
>
> Per lo storico dei segnali usare `GET /api/signals` (lista) con i suoi filtri.

---

## Quality Endpoints

### `GET /api/quality/metrics`
QX-02 dashboard data: per-model polarity/confidence distribution, signal near-zero/fallback
rates, extraction precision/recall from the QX-01 label set. Query param: `days` (default 14).

### `GET /api/quality/sources`
S2-1 Source Funnel & P&L (FIX-04): per-source ingestion funnel (`ingestion_stats_daily`),
signal latency p50/p95 (`generated_at − published_at`), near-zero rate, trade hit-rate and
net P&L, plus `trace_coverage` (signals linked to a news source). Query param: `days`
(default 14). Sources in `trades` without a `news_log` link report as `unknown`.
FIX-06 records the event-level reason and stage for discarded items in
`news_queue_drops`; stale and parse-failure events also increment the corresponding
per-source funnel counters shown by this endpoint.

### `GET /api/quality/ensemble_health`

Rollup per-ciclo della salute dell'ensemble (#427, PR #463 — deployata il 2026-09-01).
Legge `ensemble_cycle_health`: una riga per esecuzione del `SentimentWorker` con i conteggi
`n_ensemble` / `n_single` / `n_finbert` / `aggregate` e il flag `rth`.

**Query parameters:** `days` (default **7** — la tabella e' ad alta frequenza, una finestra a
30 giorni sono migliaia di righe)

**Response 200:**

```json
{
  "window_days": 7,
  "cycles": [
    {"cycle_started_at": "...", "cycle_ended_at": "...", "n_ensemble": 8,
     "n_single": 2, "n_finbert": 1, "aggregate": 11, "rth": true}
  ],
  "summary": {
    "n_cycles": 96, "total_ensemble": 512, "total_single": 180, "total_finbert": 44,
    "total_aggregate": 736, "rth_cycles": 52, "rth_share": 0.542,
    "full_ensemble_share": 0.696
  }
}
```

`full_ensemble_share` e' esattamente il numero che l'alert Telegram nel worker confronta con
0.5 (soglia: 50% di ensemble pieno su 2 cicli RTH), cosi' l'operatore vede arrivare un alert
prima che scatti. Vale `null` quando la finestra non ha prodotto segnali.

> **Nota di stato (2026-09-02):** la tabella e' ancora **vuota**. Il deploy e' atterrato alle
> 20:20 UTC del 2026-09-01, venti minuti dopo la chiusura, e fuori orario il worker esce con
> `{"skipped": true, "reason": "market_closed"}` prima di scrivere. Le prime righe sono attese
> dalla seduta del 2026-09-02.

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

System status snapshot (no auth): kill-switch state, operating mode, LLM model selection, and the current sentiment model registry.

```json
{
  "killswitch": false,
  "mode": "paper",
  "llm_models": "glm52,gptoss",
  "llm_model_registry": {
    "selection": "glm52,gptoss",
    "active_model_ids": ["glm-5.2:cloud", "gpt-oss:20b-cloud"],
    "economy_model": "glm52",
    "models": [
      {"key": "kimi", "model_id": "kimi-k2.6:cloud", "label": "Kimi K2.6", "active": false},
      {"key": "glm52", "model_id": "glm-5.2:cloud", "label": "GLM-5.2", "active": true},
      {"key": "qwen35", "model_id": "qwen3.5:cloud", "label": "Qwen3.5", "active": false},
      {"key": "gptoss", "model_id": "gpt-oss:20b-cloud", "label": "GPT-OSS 20B", "active": true}
    ]
  }
}
```

### `POST /api/admin/llm-models`

Restrict which models run in the ensemble (for token-budget savings).

```bash
curl -X POST http://localhost:8001/api/admin/llm-models \
  -H "X-API-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"models": "glm52"}'
```

Valid values are provided by the runtime registry (`src/llm/model_registry.py`). Current keys: `all`, `kimi`, `glm52`, plus the swap candidates `qwen35` and `gptoss` (registered with `in_all=False`, so they are selectable explicitly but excluded from the `all` expansion). Aliases (`glm`, `qwen`, `gpt-oss`, full model ids…) are canonicalized. Live selection since 2026-07-11: `glm52,gptoss`.

### `GET /api/llm/models`

Authenticated endpoint returning the model registry used by the frontend. The UI should use this endpoint instead of hardcoding model names, because Ollama model availability can change over time.

Esempio di risposta reale, catturata dal container `alembic-api-1` il **2026-09-02**:

```json
{
  "selection": "glm52,gptoss",
  "active_model_ids": ["glm-5.2:cloud", "gpt-oss:20b-cloud"],
  "economy_model": "glm52",
  "invalid": [],
  "models": [
    {"key": "kimi",   "model_id": "kimi-k2.6:cloud",    "label": "Kimi K2.6",   "active": false, "economy_default": false},
    {"key": "glm52",  "model_id": "glm-5.2:cloud",      "label": "GLM-5.2",     "active": true,  "economy_default": true},
    {"key": "qwen35", "model_id": "qwen3.5:cloud",      "label": "Qwen3.5",     "active": false, "economy_default": false},
    {"key": "gptoss", "model_id": "gpt-oss:20b-cloud",  "label": "GPT-OSS 20B", "active": true,  "economy_default": false}
  ]
}
```

> **Corretto il 2026-09-02.** Gli esempi precedenti mostravano `selection: "all"` con Kimi K2.6
> `active: true`: era la coppia di prima del 2026-07-11. Kimi resta *registrato* (quindi presente
> nella lista `models`) ma non e' attivo. Nota che il payload elenca **quattro** modelli, non due:
> `qwen35` e `gptoss` sono registrati con `in_all=False`, quindi selezionabili esplicitamente ma
> esclusi dall'espansione di `"all"`.

---

## Performance Endpoints

### `GET /api/performance/latest`

Latest PerformanceWorker report from Redis (IC, ICIR, drift alerts, post-mortems).

**Response 404:** no report computed yet (daily worker hasn't run).

### `GET /api/weights/current`

Current ensemble weights, filtered and normalized against the active sentiment model registry. Returns equal defaults across active models if no valid weights have been set.

Esempio di risposta reale (valori live al **2026-09-02**, riequilibrati dal LOO-ICIR):

```json
{
  "weights": {
    "glm-5.2:cloud": 0.70,
    "gpt-oss:20b-cloud": 0.30
  },
  "source": "auto_apply",
  "dropped_models": [],
  "model_registry": {"selection": "glm52,gptoss", "...": "..."}
}
```

`source` values: `auto_apply`, `telegram`, `suggestion`, `override`, `default`

`dropped_models` lists stored weights ignored because the model is not active in the current registry.

### `GET /api/weights/suggestion`

Current weight suggestion from LOO ICIR (if available, expires after 7 days).

```json
{
  "suggested_weights": {"glm-5.2:cloud": 0.68, "gpt-oss:20b-cloud": 0.32},
  "purified_icir": {"glm-5.2:cloud": 1.15, "gpt-oss:20b-cloud": 0.54},
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

Validation: each weight in `[0.10, 0.70]`, sum = 1.0 ± 0.001, model IDs active in the current sentiment model registry.

**Response:**
```json
{
  "applied_weights": {"glm-5.2:cloud": 0.50, "gpt-oss:20b-cloud": 0.50},
  "source": "suggestion",
  "log_id": 42,
  "dropped_models": []
}
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
          "id": 123,
          "symbol": "CAT",
          "signal_id": 456,
          "decision_id": 789,
          "news_log_id": 1444,
          "entry_order_id": "alpaca-order-id",
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
| `id` | Local trade id |
| `symbol` | Ticker symbol |
| `signal_id` | Linked `sentiment_signals.id`, if the trade came from an Alembic signal |
| `decision_id` | Linked `execution_decisions.id`, if available |
| `news_log_id` | Linked `news_log.id` through the originating signal, if available |
| `entry_order_id` | Broker order id for the entry |
| `entry_time` / `exit_time` | Timestamp ISO-8601 UTC |
| `entry_price` / `exit_price` | Prezzi di entrata/uscita |
| `qty` | Quantità |
| `gross_pnl` | P&L lordo prima dei costi (`null` per trade pre-migration) |
| `net_pnl` | P&L netto dopo i costi |
| `costs` | Calcolato dal frontend: `gross_pnl − net_pnl` (non nel payload JSON) |
| `exit_reason` | Motivo di chiusura (es. `portfolio_sell`, `stop_loss`) |

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

### `GET /api/positions`

Current open positions from Alpaca.

> **Corretto il 2026-09-02:** documentato fino a ieri come `/api/performance/positions`, che non
> esiste. La rotta e' registrata in `src/api/routes/trading.py` sotto il prefisso `/api` nudo.

---

## Trading Endpoints

### `GET /api/orders`

Recent Alpaca orders enriched with local Alembic trace ids when the broker order can be matched to an execution decision or trade.

**Query parameters:** `limit` (default 50, max 500), `order_id` (optional, exact broker order trace)

| Field | Meaning |
| --- | --- |
| `id` | Broker order id |
| `symbol` | Ticker symbol |
| `side` | Broker side, usually `buy` or `sell` |
| `qty` | Submitted quantity |
| `filled_avg_price` | Average fill price, or `null` when not filled |
| `status` | Broker order status |
| `filled_at` / `submitted_at` | Broker timestamps |
| `signal_id` | Originating `sentiment_signals.id`, or `null` for manual/unmatched broker orders |
| `decision_id` | Originating `execution_decisions.id`, or `null` |
| `news_log_id` | Originating `news_log.id` through the signal, or `null` |
| `trade_id` | Local `trades.id` when the order is linked to a recorded trade |

The enrichment is intentionally nullable: the Trading frontend only renders trace links when these ids exist, avoiding links to empty Signal/Decision views for orders that did not originate from Alembic.

### `GET /api/decisions`

Execution decision log from `execution_decisions`, enriched with originating signal/news metadata when available.

**Query parameters:** `symbol` (optional), `decision_id` (optional exact decision trace), `limit` (default 20, max 200)

| Field | Meaning |
| --- | --- |
| `id` | Local execution decision id |
| `tick_time` | Portfolio scheduler cycle timestamp |
| `symbol` | Ticker symbol |
| `signal_id` | Originating `sentiment_signals.id`, or `null` |
| `news_log_id` | Originating `news_log.id` through the signal, or `null` |
| `decision` | BUY/SELL or skip reason such as `SKIP_THRESHOLD`, `SKIP_EMA`, `SKIP_STALE` |
| `order_id` | Broker order id when the decision submitted an order |
| `signal_generated_at` | Timestamp of the originating signal, used to show signal-to-decision lag |
| `reason` | Human-readable scheduler reason |

---

## Portfolio Endpoints

> **Riscritta il 2026-09-02.** Questa sezione documentava tre rotte sotto `/api/portfolio/`
> (`cycles`, `risk`, `decay`) di cui **nessuna esiste**. Il router e' montato su `/portfolio`
> **senza** il prefisso `/api` (`src/api/routes/portfolio.py`) ed espone due sole rotte.

### `GET /portfolio/status`

Stato corrente del portafoglio: strategie attive con `allocation_pct`, `schedule`, `enabled`,
piu' `mode` e `approved` letti da `strategy_lifecycle` (null se il DB non risponde — fail-open,
l'endpoint risponde comunque), `promotion_blocked` da `config/strategies.yaml`,
`live_authorized` derivato fail-closed, e l'ultimo ciclo eseguito.

Dal 2026-09-02 questa e' **l'unica** superficie di autorizzazione delle strategie: la pagina
Strategies e le sue rotte di lettura sono state eliminate.

**Response 200:**

```json
{
  "active_strategies": 2,
  "strategies": [
    {"strategy_id": "S1", "allocation_pct": 0.50, "schedule": "...", "enabled": true,
     "mode": "supervised_paper", "approved": true,
     "promotion_blocked": true, "live_authorized": false}
  ],
  "last_cycle": {"timestamp": "...", "strategies_run": [], "orders_count": 0,
                 "constraints_fired": []}
}
```

### `GET /portfolio/cycle-history`

Ultimi N cicli di portafoglio da `portfolio_cycles`, con `final_orders` completo.

**Query parameters:** `limit` (default 30)

> Attenzione a `orders_count` e `final_orders`: contano gli ordini **target**, non quelli
> effettivamente inviati al broker (issue #437). I re-BUY su simboli gia' a libro compaiono in
> `final_orders` a ogni ciclo e vengono soppressi solo al momento della submit dalla guardia
> anti-pyramiding.

### Rapporti di rischio e decay — nessuna rotta HTTP

`risk_reports` e `decay_reports` sono tabelle PostgreSQL scritte dai task `risk-monitor` e
`decay-monitor`. **Non hanno un endpoint API.** Si leggono via SQL, oppure — per il rischio —
attraverso il campo `db_table` esposto da `/api/system/readiness`.

---

## News and LLM Endpoints

### `GET /api/news/recent`

Recent ingested news items from `news_log`. Query params: `ticker`, `source`, `limit`.

Each row also includes downstream trace counters:

| Field | Meaning |
| --- | --- |
| `signal_count` | Number of `sentiment_signals` rows linked through `news_log_id` |
| `decision_count` | Number of `execution_decisions` rows linked through those signals |
| `order_count` | Number of order/trade traces linked through those signals |

Rows also include `latest_signal_id` plus `latest_decision_*` diagnostic fields when the portfolio cycle produced an outcome for the news-derived signal. This includes strict fallback matching for skip rows such as `SKIP_THRESHOLD` that were historically logged without `signal_id` but match the same ticker, signal score, and post-signal time window.

### `GET /api/news/source-quality`

Per-source quality funnel over recent `news_log` rows. Query params: `days` (1-365, default 30).

The endpoint groups by `news_log.source` and returns article volume, ticker coverage, signal/decision/order conversion rates, average signal confidence, average publish-to-fetch latency, and closed-trade P&L where traceable through `news_log_id`.

Key fields: `news_count`, `with_ticker_count`, `signals_count`, `decisions_count`, `orders_count`, `closed_trades_count`, `signal_rate`, `decision_rate`, `order_rate`, `avg_confidence`, `avg_publish_to_fetch_minutes`, `win_rate`, `total_net_pnl`.

### `GET /api/llm/feedback`

Per-model LLM outputs joined to signals (for model quality analysis). Query params: `ticker`, `model_id`, `limit`.

---

## Backtest Endpoints

### `GET /api/backtest/runs`

List backtest run summaries from `backtest_signals`.

### `GET /api/backtest/{run_id}/signals`

Signals for a specific backtest run.

### `GET /api/backtest/{run_id}/summary`

Riepilogo di un run: metriche aggregate.

### `GET /api/backtest/{run_id}/pnl_curve`

Curva di P&L del run.

### `GET /api/backtest/{run_id}/model_ic`

IC per modello sul run.

### `GET /api/backtest/{run_id}/symbol_ic`

IC per simbolo sul run.

### `GET /api/backtest/{run_id}/bucket_analysis`

Analisi per bucket di score.

> **Corretto il 2026-09-02.** La documentazione precedente aveva il prefisso sbagliato
> (`/api/backtest/runs/{run_id}/...`: `runs` e' una rotta a se', non un segmento del path dei
> dettagli) e citava un `/report` che non esiste — le metriche IC/ICIR sono divise fra
> `model_ic`, `symbol_ic` e `bucket_analysis`. Verificato contro `src/api/routes/backtest*.py`
> e contro `openapi.json` del container `alembic-api-1`.

---

## Config Endpoint

### `GET /api/config`

Read operational config from `config/trading.yaml` (symbols watchlist, thresholds).

### `POST /api/config`

Update operational config (requires `X-API-Key`). Validates YAML structure before writing.

---

## Admin API Error Responses

Unless an endpoint documents otherwise, non-mobile admin API errors return
`{"detail": "..."}`. Mobile v1 uses the envelope documented above.

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
| `regime_scale` | float | Redis feedback scale state. Applied by legacy `execution.py`; in portfolio mode it is exposed for audit until portfolio sizing is explicitly wired to it. |
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
    "decision": "SKIP_THRESHOLD",
    "total_skips": 31,
    "computed": 29,
    "avg_return": 0.0014,
    "pct_profitable": 0.517,
    "sum_positive_returns": 0.061
  },
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
| `decision` | string | `SKIP_THRESHOLD`, `SKIP_EMA` or `SKIP_CAP` |
| `total_skips` | int | Total skipped signals in the window |
| `computed` | int | Skips with a 1h return computed (Alpaca bars available) |
| `avg_return` | float | Mean 1-hour return if entry had been taken |
| `pct_profitable` | float | Fraction of skips where 1h return > 0 |
| `sum_positive_returns` | float | Sum of all positive 1h returns (upside missed) |

`SKIP_POSITION` (already in position) is excluded — it is not a missed opportunity. `SKIP_STALE` and `SKIP_FALLBACK` are also excluded because they are signal freshness/reliability failures, not filters to relax.

Returns `[]` when no Phase C skip rows exist in the window or when rows are still pending the nightly `counterfactual-worker`. Use the status endpoint below to distinguish those cases.

### `GET /api/trades/analytics/counterfactual/status`

Raw Phase C coverage metadata for the Auto-Improve page. Use this endpoint to distinguish:

- no skip decisions in the window;
- skip decisions pending the nightly worker;
- worker has not run or last run failed/skipped;
- rows processed but 1-hour return data was unavailable.

**Query parameters:** `days` (int, default 7, range 1–90)

**Response 200:**
```json
{
  "days": 7,
  "last_processed_at": "2026-07-01T22:45:12+00:00",
  "raw_skip_counts": [
    {
      "decision": "SKIP_THRESHOLD",
      "total": 31,
      "processed": 29,
      "with_return": 27,
      "pending": 2,
      "included_in_phase_c": true
    },
    {
      "decision": "SKIP_STALE",
      "total": 14,
      "processed": 0,
      "with_return": 0,
      "pending": 14,
      "included_in_phase_c": false
    }
  ],
  "phase_c": {
    "total_skips": 31,
    "processed": 29,
    "with_return": 27,
    "pending": 2
  },
  "worker": {
    "last_run_at": "2026-07-01T22:45:00+00:00",
    "completed_at": "2026-07-01T22:45:12+00:00",
    "status": "ok",
    "reason": null,
    "updated": 27,
    "skipped_no_data": 2,
    "errors": 0,
    "total_decisions": 29
  },
  "next_run_hint": "22:45 UTC, Mon-Fri"
}
```

`worker` is read from Redis key `counterfactual:worker:last_run` and can be `null` if no run has been observed since the metadata key was introduced. `last_processed_at` is `MAX(counterfactual_computed_at)` over included Phase C rows.

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

Decision labels include `BUY`, `SELL`, `SKIP_THRESHOLD` (below active feedback gate), `SKIP_STALE` (signal expired), `SKIP_FALLBACK` (fallback-only signal), `SKIP_EMA` (price below EMA20), `SKIP_CAP` (position cap reached), `SKIP_POSITION` (already in position), `STOP_LOSS` (stop triggered).

---

## ~~PEAD Routes~~ — RIMOSSE il 2026-07-15 con S7

> **Sezione eliminata il 2026-09-02.** `GET /api/pead/signals` e `GET /api/pead/events` sono
> state documentate per sette settimane dopo essere state cancellate dal codice. S7 (PEAD,
> classificazione 8-K) e' stata ritirata il 2026-07-15 — edge ALPHA-A3 confutato, POC-2 FAIL —
> insieme a strategia, worker, task del beat, config e route API. Oggi `pead` compare in
> `src/` solo dentro i commenti che ne registrano la rimozione, e un test di guardia
> (`tests/test_p0_13_strategy_containment.py`) impedisce la re-introduzione accidentale.
>
> Storia completa: `docs/S7_LIFECYCLE_HISTORY_2026-07-15.md`. Configurazione di allora:
> `docs/llm-config.md`, sezione finale.

---

## Auth Endpoints

Autenticazione dell'operatore per il frontend React. Il token restituito da `/api/auth/login`
e' un JWT con scadenza `JWT_EXPIRE_MINUTES` (default 1440, cioe' 24h).

### `POST /api/auth/login`

Credenziali operatore (`ADMIN_USERNAME` / `ADMIN_PASSWORD_HASH`, bcrypt) → token.

### `GET /api/auth/me`

Identita' corrente. Richiede `X-API-Key`.

> Da non confondere con `/api/mobile/v1/auth/*`, che e' il flusso separato del client Android
> (login/logout/refresh/me + registrazione dispositivi) documentato piu' sopra.

---

## Strategies Endpoints — solo promotion gate

**Le rotte di lettura sono state eliminate il 2026-09-02**, insieme alla pagina Strategies
del frontend. `GET /api/strategies`, `/{id}`, `/{id}/backtest`, `/{id}/gates` e
`/{id}/sensitivity` servivano dizionari Python congelati al 2026-05-30 (S1) e al 2026-06-15
(S4), presentati come stato corrente accanto a un badge `LIVE`:

- `total_trades` 1247 per S1 contro **103** righe reali in `trades`; 223 per S4 contro **114**
- l'`universe` di S1 era quello del *backtest* (15 ETF: SPY, QQQ, TLT, GLD…) mentre S1 in
  produzione compra azioni singole dalla watchlist di 96 simboli — **zero sovrapposizione**
- la "Parameter Sensitivity" era generata da una gaussiana in codice, non misurata
- il pannello dei gate mostrava soglie inventate *piu' severe* di quelle vere in
  `reports/s1_backtest/gate_report.json` (che sono ~0.0), e due gate riportavano PASS con un
  `metric_value` sotto la propria soglia dichiarata
- la coppia dell'ensemble era descritta come "Kimi K2.6 + GLM-5.2", ritirata il 2026-07-11

Restano le tre POST del promotion gate (P2-02), che non contengono snapshot: scrivono su
`strategy_lifecycle` attraverso `src/strategies/promotion.py`. Richiedono `X-API-Key` e
`strategy_id` e' case-insensitive (normalizzato a maiuscolo).

| Endpoint | Metodo | Corpo | Descrizione |
|---|---|---|---|
| `/api/strategies/{strategy_id}/promote` | POST | `target_mode`, `gate_report_id?`, `requested_by` | Richiede una promozione di modo. 422 se il gate la rifiuta |
| `/api/strategies/{strategy_id}/approve` | POST | `approved_by` | Approva una promozione pendente. 422 se non ce n'e' una |
| `/api/strategies/{strategy_id}/demote` | POST | `new_mode`, `reason`, `demoted_by` | Retrocessione (sempre permessa, e' l'azione da circuit breaker) |

> **Difetto noto, non introdotto dalla rimozione:** `promotion.py::_fetch_lifecycle_row`
> seleziona `promotion_blocked` da `strategy_lifecycle`, ma **quella colonna non esiste sul DB
> live** (verificato il 2026-09-02). `promote` e `approve` falliscono quindi con HTTP 500. E'
> fail-closed — nessuna promozione puo' avvenire per errore — ma il gate non e' mai stato
> esercitato contro il DB reale. `demote` non tocca quel campo e funziona.

### Dov'e' finito lo stato di autorizzazione

In **`GET /portfolio/status`**, che lo legge da fonti vive: `mode` e `approved` da
`strategy_lifecycle`, `allocation_pct`, `enabled` e `promotion_blocked` da
`config/strategies.yaml`. `live_authorized` e' derivato fail-closed
(`mode == "live" AND GLOBAL_LIVE_PROMOTION_ENABLED`): un `mode` sconosciuto — DB
irraggiungibile, riga mancante — non e' `live`, quindi la risposta e' `false`.

---

## Validation Endpoint

### `GET /api/validation/metrics`

Metriche della pagina Validation. **Query parameters:** `days` (default 7).

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

See the Cockpit Runbooks section of `docs/operations.md` for remediation steps.

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
  "per_model": [ { "model_id": "glm-5.2:cloud", "n": 911, "mean_polarity": 0.044, "mean_confidence": 0.661, "near_zero_rate": 0.188, "eligible_rate": 1.0 } ],
  "signals": { "near_zero_rate": 0.341, "fallback_rate": 0.236, "mean_ensemble_std": 0.05 },
  "extraction": { "n_labeled": 17, "precision": 0.24, "recall": 0.40, "recall_in_watchlist": 1.0, "fp_per_article": 1.12, "macro_fp_per_article": 2.0 }
}
```

---

## Health Check

### `GET /api/health`

```json
{"status": "ok"}
```

**Liveness only.** It confirms the API process is up and answering — nothing else. It runs no
dependency check, and it **always returns 200**: it will answer `ok` with Redis or Postgres
down. Do not wire alerting to it expecting otherwise.

Until 2026-07-28 this endpoint also returned a `mode` field hardcoded to `"backtest"`, which
contradicted the authoritative source; it was removed (#138). For the trading mode use
`GET /api/admin/mode`.

For actual dependency health use **`GET /api/system/readiness`** (requires `ADMIN_API_KEY`),
which aggregates the operator alert flags from Redis and the DB. Note that it too always
returns HTTP 200 by design — the status code only says the endpoint ran; read the body flags.

---

## OpenAPI

- Swagger UI: `http://localhost:8001/docs`
- ReDoc: `http://localhost:8001/redoc`
- JSON schema: `http://localhost:8001/openapi.json`

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 7.1.0 | 2026-09-02 | **Rotte di lettura `/api/strategies` rimosse** (servivano snapshot hardcoded contraddetti dai dati reali) insieme alla pagina Strategies del frontend. Restano le tre POST del promotion gate. Lo stato di autorizzazione passa a `GET /portfolio/status`, che guadagna `promotion_blocked` e `live_authorized`. |
| 7.0.0 | 2026-09-02 | **Allineamento al runtime.** Rimosse le rotte PEAD (S7 ritirata il 2026-07-15). Corretto il prefisso backtest (`/api/backtest/{run_id}/...`) e sostituito l'inesistente `/report` con `summary`/`model_ic`/`symbol_ic`/`pnl_curve`/`bucket_analysis`. Riscritta la sezione Portfolio: le rotte reali sono `GET /portfolio/status` e `GET /portfolio/cycle-history`, **senza** prefisso `/api`; `/api/portfolio/{cycles,risk,decay}` non sono mai esistite e `risk_reports`/`decay_reports` non hanno superficie HTTP. `/api/performance/positions` → `/api/positions`. `/api/signals/history` marcata come inesistente. Aggiunte: `GET /api/quality/ensemble_health` (#427), sezioni **Auth**, **Strategies**, **Validation**. Tutti gli esempi di modello aggiornati alla coppia live `glm52,gptoss`. Verificato contro `openapi.json` di `alembic-api-1`. Corretta anche una fence di codice spuria dopo la tabella dei campi trade di `/api/performance/daily`: mandava in blocco di codice l'esempio `curl` e tutto il testo che seguiva. |
| 6.1.1 | 2026-06-26 | GET /api/performance/daily: trade-level detail now includes Costi column (gross_pnl − net_pnl per trade) in frontend drill-down |
| 6.1.0 | 2026-06-26 | GET /api/performance/daily: add total_gross_pnl and total_costs fields (gross/net breakdown); remove gross_profit/gross_loss fields |
| 6.0.0 | 2026-06-26 | GET /api/performance/daily (per-day P&L from trades table, with trade-level detail); documented GET /api/performance/weekly and GET /api/performance/pnl schemas |
| 5.0.0 | 2026-06-06 | Phase B: GET /api/feedback/status; Phase C: GET /api/trades/analytics/counterfactual |
| 4.0.0 | 2026-06-06 | Phase A analytics: trades, decisions, analytics/by-symbol, analytics/by-dimension, postmortem endpoints; kill switch GET+DELETE; trades/decisions require auth |
| 3.0.0 | 2026-06-03 | Full English rewrite; Phase G portfolio, risk, decay endpoints (**mai implementate come rotte HTTP** — vedi 7.0.0); new admin/llm-models, config endpoints |
| 2.0.0 | 2026-05-12 | Added GET /api/weights/suggestion; updated POST /api/weights/approve |
| 1.0.0 | 2026-05-04 | Initial release |
