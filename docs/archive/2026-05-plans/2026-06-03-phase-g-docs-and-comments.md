# Phase G — Documentation & Code Comments Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete all documentation files and add targeted code comments to make the codebase ready for the paper-trading validation period.

**Architecture:** Documentation is split across README.md (overview), docs/*.md (deep dives), and inline comments. Most source files already have module-level docstrings; the gaps are: wrong test counts, missing Phase G portfolio content, Italian-language docs that must be English, and missing new doc files.

**Tech Stack:** Markdown, Python docstrings

---

## Scope map

### Files to modify
- `README.md` — update test count (594→1714), add Phase G portfolio orchestrator, update project structure
- `docs/API.md` — translate to English, add new endpoints (portfolio, config, strategies, trading, news, llm)
- `docs/ARCHITECTURE.md` — translate to English, add Phase G (portfolio module, multi-strategy)

### Files to create
- `docs/strategies.md` — S1/S2/S4/S3 strategy details
- `docs/operations.md` — Docker, Celery beat, Grafana, monitoring, troubleshooting
- `docs/deployment.md` — production deployment guide

### Source files to annotate (add comments where WHY is non-obvious)
- `src/portfolio/orchestrator.py`
- `src/portfolio/constraints.py`
- `src/portfolio/vol_targeting.py`
- `src/portfolio/combiner.py`
- `src/portfolio/backtest.py`
- `src/portfolio/risk_parity.py`
- `src/workers/portfolio_scheduler.py`
- `src/workers/decay_monitor_task.py`
- `src/workers/risk_monitor_task.py`
- `src/workers/celery_app.py`
- `src/api/routes/signals.py`
- `src/api/routes/admin.py`
- `src/api/routes/performance.py`
- `src/api/routes/portfolio.py`
- `src/api/routes/news_routes.py`
- `src/api/routes/llm_routes.py`
- `src/api/routes/trading.py`
- `src/api/routes/backtest.py`
- `src/api/routes/config_routes.py`
- `src/api/routes/strategies.py`
- `src/store/pg_store.py`
- `scripts/run_backtest.py`

---

## Task 1: Update README.md

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update test badge count**

Find and replace in `README.md`:
```
![Tests](https://img.shields.io/badge/tests-594%20passing-brightgreen)
```
Replace with:
```
![Tests](https://img.shields.io/badge/tests-1714%20passing-brightgreen)
```

- [ ] **Step 2: Add Phase G Portfolio Orchestrator to Architecture Overview**

After the `### Phase 5 — Performance & Weight Optimisation` section (around line 177), insert:

```markdown
### Phase G — Portfolio Orchestration (Multi-Strategy)

The `PortfolioOrchestrator` runs hourly during market hours and coordinates all active strategies using a **weight-then-order** architecture. Instead of each strategy independently generating full-portfolio orders (which causes double-counting when merged), strategies output **target weights**; the orchestrator merges them by allocation percentage, then computes a single set of delta orders.

**Cycle:**
1. Each active strategy (`S1`, `S2`, `S4`) produces target weights (fractions of NAV) scaled by its `allocation_pct`
2. Weights are merged across strategies: `merged[sym] += strategy_weight[sym] × alloc_pct`
3. Delta orders are computed: `target_qty - current_qty` per symbol
4. `ConstraintEnforcer` applies five sequential constraints (per-asset, per-strategy, portfolio, sector, correlation)
5. Optional `PortfolioVolTargeter` scales BUY quantities so the portfolio hits 10% annualised vol
6. Orders are submitted to Alpaca; cycle result is persisted to `portfolio_cycles`

**Monitoring:**
- `DecayMonitor` (monthly): compares IC/hit-rate/Sharpe against backtest baselines
- `PortfolioRiskMonitor` (daily): computes Herfindahl index, correlation matrix, drawdown per strategy
```

- [ ] **Step 3: Update project structure section**

Find the project structure block and add:
```
│   ├── portfolio/
│   │   ├── orchestrator.py    # PortfolioOrchestrator: weight-then-order multi-strategy cycle
│   │   ├── constraints.py     # ConstraintEnforcer: 5-pass risk constraint application
│   │   ├── vol_targeting.py   # PortfolioVolTargeter: EWMA vol estimation + order scaling
│   │   ├── decay_monitor.py   # DecayMonitor: actual vs backtest baseline comparison
│   │   ├── risk_monitor.py    # PortfolioRiskMonitor: drawdown + correlation + HHI alerts
│   │   ├── combiner.py        # Signal combiner (cross-sectional aggregation)
│   │   ├── risk_parity.py     # Risk parity weight allocation
│   │   └── types.py           # CombinedOrder, ConstraintViolation, PortfolioState
│   ├── strategies/
│   │   ├── s1/                # Time-Series Momentum (Moskowitz et al.)
│   │   ├── s2/                # Volatility Risk Premium (VRP) overnight strategy
│   │   ├── s3/                # Cross-Sectional Momentum (R&D sleeve)
│   │   └── s4/                # News-Driven Tactical (LLM ensemble signals)
```

- [ ] **Step 4: Update test coverage table**

Replace the existing test count table with:
```markdown
| Category | Tests |
|----------|-------|
| Workers (sentiment, execution, performance, regime, poller, portfolio) | ~120 |
| Performance (IC, weights, drift, postmortem, threshold) | ~89 |
| Portfolio (orchestrator, constraints, vol-targeting, risk-monitor, decay) | ~90 |
| Strategies (S1, S2, S3, S4) | ~200 |
| Backtest (engine, walkforward, metrics, gates, costs) | ~400 |
| Stores (Redis, Postgres, budget) | ~60 |
| LLM (client, ensemble, finbert) | ~27 |
| API (routes, auth, weight approval) | ~80 |
| Connectors (GDELT, MarketAux, macro, deduplicator) | ~20 |
| Notifications (base protocol, telegram formatters) | ~25 |
| Analysis (backtest, GDELT A/B) | ~16 |
| Security, config, models | ~28 |
| Frontend (React components) | ~559 |
| **Total** | **~1714** |
```

- [ ] **Step 5: Update Celery Beat Schedule table**

Add the three new Phase G tasks to the beat schedule table:
```markdown
| `portfolio-cycle` | Hourly | Mon–Fri 14:00–21:00 | Multi-strategy weight-then-order cycle |
| `risk-monitor` | Daily | 22:30 | Per-strategy + combined risk metrics |
| `decay-monitor` | Monthly | 1st 23:00 | Actual vs backtest baseline decay check |
```

- [ ] **Step 6: Verify the changes look correct**

Run:
```bash
head -20 README.md && grep -n "1714\|Phase G\|portfolio-cycle\|decay-monitor" README.md
```
Expected: output shows 1714 in badge, Phase G section present, new tasks in schedule.

- [ ] **Step 7: No commit yet — docs committed together in Task 7**

---

## Task 2: Translate and update docs/API.md to English

**Files:**
- Modify: `docs/API.md`

- [ ] **Step 1: Rewrite docs/API.md in English with all endpoints**

Replace the entire file with:

```markdown
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
  "weights": {"kimi-k2.6:cloud": 0.25, "qwen3.5:cloud": 0.25, "deepseek-v4-pro:cloud": 0.25, "glm-5.1:cloud": 0.25},
  "source": "default"
}
```

`source` values: `auto_apply`, `telegram`, `suggestion`, `override`, `default`

### `GET /api/weights/suggestion`

Current weight suggestion from LOO ICIR (if available, expires after 7 days).

```json
{
  "suggested_weights": {"kimi-k2.6:cloud": 0.32, ...},
  "purified_icir": {"kimi-k2.6:cloud": 1.15, ...},
  "freeze_reason": "VIX = 32.4 >= 30.0",
  "computed_at": "2026-06-02T04:00:12Z",
  "expires_at": "2026-06-09T04:00:12Z"
}
```

`freeze_reason` is empty string when all guardrails pass.

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
{"applied_weights": {"kimi-k2.6:cloud": 0.30, ...}, "source": "suggestion", "log_id": 42}
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
```

- [ ] **Step 2: Verify**

```bash
grep -n "Phase G\|portfolio\|decay\|3.0.0" docs/API.md | head -20
```
Expected: lines referencing Phase G, portfolio endpoints, 3.0.0 version.

---

## Task 3: Translate and update docs/ARCHITECTURE.md to English

**Files:**
- Modify: `docs/ARCHITECTURE.md`

- [ ] **Step 1: Check current file length**

```bash
wc -l docs/ARCHITECTURE.md
```

- [ ] **Step 2: Rewrite docs/ARCHITECTURE.md**

Replace the entire file with the following (preserve the content but translate to English and add Phase G):

```markdown
<div align="center">
  <img src="../img/alembic.png" alt="Alembic" width="140"/>
</div>

# Alembic — Technical Architecture

**Technical Architecture Document**  
**Version:** 4.0.0  
**Date:** 2026-06-03  
**Status:** Phase G Complete — Portfolio Orchestrator + Paper Trading Live

---

## 1. Architectural Overview

### 1.1 Alpha Miner Paradigm

Alembic implements the **Alpha Miner** paradigm: LLMs operate exclusively offline as a research engine. Signals are pre-computed and cached. The execution engine **never calls an LLM synchronously** during the trading loop.

```
[News Sources] → [Background LLM Workers] → [Redis / PostgreSQL]
                                                     ↓
               [Execution Engine (Alpaca SDK)] reads signal at tick
```

### 1.2 Component Interaction Map

```
┌──────────────────────────────────────────────────────────────────┐
│                   OFFLINE SENTIMENT PIPELINE                      │
│                                                                   │
│  News Sources ──► NewsIngestionWorker ──► Redis news:queue       │
│  (GDELT GKG,                              (SHA-256 dedup, TTL)   │
│   MarketAux,       ▼                                             │
│   Alpaca News) SentimentWorker ──► LLM Ensemble (4 models)       │
│                                         ↓              ↓         │
│                                   Redis signal    PostgreSQL      │
│                                   (TTL 4h)        audit trail    │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                   REGIME DETECTION (daily 07:00 UTC)              │
│                                                                   │
│  FRED API (VIX, T10Y2Y) ──► RegimeDetector ──► Redis            │
│  yfinance (SPY 20d EMA)       LLM pair          regime_multiplier│
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│           PORTFOLIO ORCHESTRATION (hourly 14-21 UTC, Mon-Fri)     │
│                                                                   │
│  StrategyRegistry ──► S1/S2/S4 target weights                    │
│                            ↓ merge by allocation_pct             │
│                    PortfolioOrchestrator                          │
│                            ↓ delta orders                         │
│                    ConstraintEnforcer ──► VolTargeter             │
│                            ↓                                      │
│                    Alpaca SDK (paper/live)                        │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│              PERFORMANCE & MONITORING LOOP                        │
│                                                                   │
│  Daily 22:00: ForwardReturnWorker → populate sentiment_signals   │
│  Daily 03:00: PerformanceWorker → IC + drift + Telegram digest   │
│  Daily 22:30: RiskMonitor → HHI + correlation + drawdown alerts  │
│  Mon  04:00: WeightOptimiser → LOO ICIR → auto-apply / Telegram  │
│  Monthly 1st: DecayMonitor → actual vs backtest baseline         │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. Component Catalogue

### 2.1 News Ingestion

| Component | File | Role |
|-----------|------|------|
| `GDELTGKGConnector` | `src/connectors/gdelt_gkg.py` | Fetches 15-min GKG bulk CSVs, extracts English financial themes |
| `MarketAuxConnector` | `src/connectors/marketaux.py` | Paid news API with pre-tagged ticker symbols |
| `AlpacaNewsConnector` | `src/connectors/alpaca_news.py` | Broker-native Benzinga news |
| `SecEdgarConnector` | `src/connectors/sec_edgar.py` | SEC EDGAR 8-K/10-Q filings |
| `NewsDeduplicator` | `src/connectors/deduplicator.py` | SHA-256 hash dedup via Redis set (TTL 2h) |
| `TickerExtractor` | `src/connectors/ticker_extractor.py` | Company name → ticker via PostgreSQL lookup |

### 2.2 Sentiment Pipeline

| Component | File | Role |
|-----------|------|------|
| `SentimentWorker` | `src/workers/sentiment.py` | Consumes `news:queue`, runs ensemble, writes signal |
| `LLMClient` (ABC) | `src/llm/client.py` | Ollama cloud clients: Kimi K2.6, Qwen3.5, DeepSeek-V4-Pro, GLM-5.1 |
| `EnsembleAggregator` | `src/llm/ensemble.py` | Weighted averaging + divergence check (std > 0.30) |
| `FinBERTClient` | `src/llm/finbert.py` | Local fallback: entropic confidence from 3-class softmax |
| `LLMBudgetTracker` | `src/llm/budget.py` | Daily spend cap per model via Redis counters |
| `sanitize_text` | `src/text/sanitizer.py` | Strip BiDi overrides, homoglyphs, NFKC normalisation |

**Signal formula:** `score = polarity × confidence` where polarity ∈ [-1, +1] and confidence ∈ [0, 1].

### 2.3 Regime Detection

| Component | File | Role |
|-----------|------|------|
| `RegimeDetector` | `src/workers/regime.py` | Daily macro → LLM pair → regime label |
| `MacroConnector` | `src/connectors/macro.py` | FRED API: VIX, T10Y2Y; yfinance: SPY EMA20 |

Regime multipliers applied to position sizes:

| Label | Multiplier | Typical conditions |
|-------|-----------|-------------------|
| `bull` | 1.0× | VIX low, spread positive, SPY uptrend |
| `sideways` | 0.7× | Moderate VIX, flat spread |
| `bear` | 0.4× | Elevated VIX, negative spread |
| `high_vol` | 0.2× | VIX spike >30 |

### 2.4 Portfolio Orchestration (Phase G)

| Component | File | Role |
|-----------|------|------|
| `PortfolioOrchestrator` | `src/portfolio/orchestrator.py` | Weight-then-order multi-strategy cycle |
| `StrategyRegistry` | `src/strategies/registry.py` | Active strategy entries + allocation percentages |
| `ConstraintEnforcer` | `src/portfolio/constraints.py` | 5-pass risk constraint enforcement |
| `PortfolioVolTargeter` | `src/portfolio/vol_targeting.py` | EWMA vol estimation + BUY order scaling |
| `PortfolioRiskMonitor` | `src/portfolio/risk_monitor.py` | Daily HHI, correlation, drawdown alerts |
| `DecayMonitor` | `src/portfolio/decay_monitor.py` | Monthly actual vs backtest baseline |
| `run_portfolio_cycle` | `src/workers/portfolio_scheduler.py` | Celery task: fetch prices → orchestrate → submit to Alpaca |

**Weight-then-order design rationale:**  
Each strategy outputs target weights (fractions of NAV). These are merged with `merged[sym] += weight × alloc_pct`. Delta orders are then computed once against the current portfolio. This prevents the double-counting bug where independent strategies each generate full-portfolio orders that are then naively merged.

### 2.5 Strategies

| ID | Name | Logic |
|----|------|-------|
| **S1** | Time-Series Momentum | 12-1 month total return signal (Moskowitz et al.), EMA filter, vol-scaled sizing |
| **S2** | Volatility Risk Premium | Overnight gap on low-VRP days (implied > realised vol → mean-reversion) |
| **S3** | Cross-Sectional Momentum | R&D sleeve: cross-sectional rank of 1-12 month returns |
| **S4** | News-Driven Tactical | LLM ensemble sentiment → BUY gate: score > 0.3 AND price > EMA20 |

### 2.6 Execution Engine

| Component | File | Role |
|-----------|------|------|
| `ExecutionWorker` | `src/workers/execution.py` | Sequential safety checklist → Alpaca orders |
| `AlpacaBroker` | `src/brokers/ibkr_adapter.py` | Order placement adapter |

Execution checklist (per tick):
1. Kill-switch check (abort if active)
2. EMA20 cache refresh (yfinance)
3. Daily drawdown cap check (≥10% → set kill-switch)
4. Per-symbol: freshness check → stop-loss → BUY gate → position size × regime multiplier

### 2.7 Performance & Monitoring

| Component | File | Role |
|-----------|------|------|
| `PerformanceWorker` | `src/workers/performance.py` | IC (B4 + Newey-West HAC), drift (PSI + CUSUM), auto-weights |
| `ForwardReturnWorker` | `src/workers/performance.py` | Populates `sentiment_signals.forward_return` at market close |
| `ICCalculator` | `src/performance/ic.py` | Composite IC B4 with Newey-West HAC standard errors |
| `WeightOptimiser` | `src/performance/weights.py` | LOO ICIR with guardrails (VIX, drawdown, floor/cap) |
| `DriftDetector` | `src/performance/drift.py` | PSI + CUSUM signal distribution drift |
| `PostMortem` | `src/performance/postmortem.py` | Diagnostic on significant drawdown days |

### 2.8 Storage

| Store | Technology | Schema |
|-------|------------|--------|
| `RedisStore` | Redis 7 | `sentiment:signal:{sym}` TTL 4h; `killswitch_active`; `regime_multiplier`; `ensemble:weights:current`; `system:mode` |
| `PostgreSQLStore` | PostgreSQL 16 | `sentiment_signals`, `llm_responses`, `news_log`, `weight_update_log`, `backtest_signals`, `portfolio_cycles`, `risk_reports`, `decay_reports` |

---

## 3. Data Flow

```
Article arrives via GDELT/MarketAux/Alpaca
    │
    ▼
NewsIngestionWorker
    ├── SHA-256 dedup (Redis set, TTL 2h)
    ├── TickerExtractor (PostgreSQL lookup)
    └── LPUSH news:queue (annotated NewsItem JSON)
    │
    ▼
SentimentWorker (BLPOP news:queue)
    ├── sanitize_text()
    ├── LLM Ensemble (4 × Ollama cloud, parallel)
    │   ├── divergence check (std > 0.30 → FinBERT)
    │   └── budget check (daily cap → exclude model or FinBERT)
    ├── score = polarity × confidence
    ├── SET sentiment:signal:{sym} EX 14400 (Redis, TTL 4h)
    └── INSERT sentiment_signals (PostgreSQL, permanent)
    │
    ▼
ExecutionWorker (every 15 min)
    ├── GET killswitch_active
    ├── GET regime_multiplier
    ├── For each symbol in watchlist:
    │   ├── GET sentiment:signal:{sym}
    │   ├── freshness check (< 30 min)
    │   ├── BUY gate: score > 0.3 AND price > EMA20
    │   └── order_notional = base × regime_multiplier
    └── Alpaca SDK market order
    │
    ▼
PortfolioOrchestrator (hourly)
    ├── S1.compute_target_weights(prices)
    ├── S2(ts, data_replay, portfolio, market) → orders → implied weights
    ├── S4.compute_target_weights(signals, as_of=ts)
    ├── merge: merged[sym] += wt × alloc_pct
    ├── delta orders: target_qty - current_qty
    ├── ConstraintEnforcer (5 passes)
    ├── PortfolioVolTargeter (scale to 10% annual vol)
    └── Alpaca SDK market orders
```

---

## 4. Redis Key Schema

| Key | Type | TTL | Purpose |
|-----|------|-----|---------|
| `sentiment:signal:{SYM}` | JSON string | 4h | Latest signal per symbol |
| `news:queue` | List | — | Inbound article queue |
| `news:dedup:{HASH}` | String | 2h | Article URL deduplication |
| `killswitch_active` | String (`0`/`1`) | None | Emergency halt flag |
| `system:mode` | String | None | Operating mode |
| `llm:models` | String | None | Active LLM subset |
| `regime_multiplier` | String (float) | 26h | Current regime position scale |
| `regime_label` | String | 26h | Current regime label |
| `ensemble:weights:current` | JSON | None | Current model weights |
| `ensemble:weights:suggestion` | JSON | 7d | Pending weight suggestion |
| `llm:budget:{MODEL}:{DATE}` | String (float) | 2d | Daily LLM spend counter |
| `performance:report:latest` | JSON | None | Latest PerformanceWorker output |

---

## 5. PostgreSQL Schema

```sql
-- Core signal tables
CREATE TABLE sentiment_signals (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    score FLOAT NOT NULL,
    confidence FLOAT NOT NULL,
    reasoning TEXT,
    model_id VARCHAR(200),
    ensemble_std FLOAT,
    fallback_used BOOLEAN DEFAULT FALSE,
    forward_return FLOAT,          -- populated by ForwardReturnWorker
    generated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (symbol, generated_at)
);

CREATE TABLE llm_responses (
    id SERIAL PRIMARY KEY,
    signal_id INTEGER REFERENCES sentiment_signals(id),
    model_id VARCHAR(100),
    polarity FLOAT,
    confidence FLOAT,
    reasoning TEXT,
    eligible BOOLEAN,
    generated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE weight_update_log (
    id SERIAL PRIMARY KEY,
    source VARCHAR(50),
    applied_weights JSONB,
    suggested_weights JSONB,
    purified_icir JSONB,
    freeze_reason TEXT,
    note TEXT,
    approved_by VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Portfolio tables (Phase G)
CREATE TABLE portfolio_cycles (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ,
    strategies_run JSONB,
    orders_count INTEGER,
    constraints_fired JSONB,
    final_orders JSONB
);

CREATE TABLE risk_reports (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ,
    nav FLOAT,
    total_exposure FLOAT,
    herfindahl_index FLOAT,
    combined_drawdown FLOAT,
    per_strategy_metrics JSONB,
    alerts JSONB
);

CREATE TABLE decay_reports (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ,
    strategy_id VARCHAR(20),
    metric VARCHAR(50),
    baseline_value FLOAT,
    actual_value FLOAT,
    decay_score FLOAT,
    alert_level VARCHAR(20),
    notes JSONB
);
```

---

## 6. Celery Beat Schedule

| Task | Cron (UTC) | Description |
|------|-----------|-------------|
| `run-news-ingestion` | */15 14-21 Mon-Fri | GDELT GKG → news queue |
| `run-marketaux-ingestion` | */15 14-21 Mon-Fri | MarketAux → news queue |
| `run-alpaca-ingestion` | */15 14-21 Mon-Fri | Alpaca/Benzinga → news queue |
| `sentiment-worker` | */15 14-21 Mon-Fri | news queue → LLM → Redis/PG |
| `run-execution` | */15 14-21 Mon-Fri | signals → Alpaca orders |
| `portfolio-cycle` | 0 14-21 Mon-Fri | Weight-then-order multi-strategy |
| `regime-detector` | 7:00 Mon-Fri | FRED/yfinance → LLM → Redis |
| `forward-return-worker` | 22:00 daily | Populate forward returns from yfinance |
| `risk-monitor` | 22:30 daily | HHI + correlation + drawdown |
| `performance-daily` | 3:00 daily | IC + drift + Telegram digest |
| `drift-detection` | 4:30 Sunday | PSI + CUSUM over weekly window |
| `check-suggestion-expiry` | 5:00 daily | Expire old weight suggestions |
| `performance-weekly` | 4:00 Monday | LOO ICIR → weight suggestion |
| `run-retention-sweep` | 3:30 daily | Nightly old data cleanup |
| `decay-monitor` | 23:00 1st of month | Actual vs backtest baseline |
| `poll-telegram-updates` | every 5 seconds | Weight approve/reject keyboard |

---

## 7. Security Considerations

| Threat | Mitigation |
|--------|-----------|
| Prompt injection via news text | `sanitize_text()`: strips BiDi overrides, homoglyphs, NFKC normalisation |
| SQL injection (INTERVAL parameter) | Parameterised query with `|| ' days'::interval` |
| Command injection (LLM model IDs) | `ALLOWED_MODEL_IDS` frozenset allowlist |
| API key timing attack | `hmac.compare_digest` in `auth.py` |
| Telegram replay | SHA-256 token hash `computed_at[:8]` per weight suggestion |
| Telegram unauthorised tap | `TELEGRAM_ALLOWED_USER_IDS` allowlist |
| Redis OOM | try/except on all write operations; silent on error |
| PostgreSQL connection leak | `finally: pg.close()` in all Celery tasks |

---

## 8. Known Gaps (Pre-Live)

See `README.md` → *Pre-Live Blockers* section for the authoritative list of critical bugs
(pool leak, weights never read from Redis, LOO ICIR data source, duplicate BUY orders).
```

- [ ] **Step 3: Verify**

```bash
grep -n "Phase G\|Weight-then-order\|4.0.0\|portfolio_cycles" docs/ARCHITECTURE.md | head -20
```

---

## Task 4: Create docs/strategies.md

**Files:**
- Create: `docs/strategies.md`

- [ ] **Step 1: Write docs/strategies.md**

```markdown
# Alembic — Strategy Reference

This document describes each trading strategy, its signal logic, sizing rules, and integration with the portfolio orchestrator.

---

## S1 — Time-Series Momentum

**Type:** Trend-following long/short  
**File:** `src/strategies/s1/`  
**Allocation:** Configurable via `StrategyRegistry`

### Signal Logic

Implements the Moskowitz, Ooi & Pedersen (2012) time-series momentum signal:
```
signal = sign(total_return_{t-12, t-1}) × annualised_sharpe_ratio
```

- **Lookback:** 12 months, skip the most recent month (avoids short-term reversal)
- **Entry:** Long when signal > 0, skip when signal ≤ 0 (long-only in this implementation)
- **EMA filter:** Price must be above EMA20 to enter (confirms trend direction)

### Sizing

`src/strategies/s1/sizing.py`:
- `base_weight = 1 / N_symbols` (equal-weight across signals)
- `vol_scaled_weight = base_weight × (target_vol / realised_vol)` using EWMA vol (60-day span)
- Output: dict of `{symbol: target_weight}` passed to PortfolioOrchestrator

### Key Parameters (`S1Config`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `lookback_months` | 12 | Return lookback window |
| `skip_months` | 1 | Short-term reversal skip |
| `ema_period` | 20 | Trend filter EMA days |
| `target_vol` | 0.15 | Annualised vol target |

### Integration

S1 exposes `compute_target_weights(prices: pd.DataFrame) → dict[str, float]`. The orchestrator calls this directly when S1 is active.

---

## S2 — Volatility Risk Premium (VRP)

**Type:** Mean-reversion, overnight gap  
**File:** `src/strategies/s2/`  
**Allocation:** Configurable via `StrategyRegistry`

### Signal Logic

Exploits the **volatility risk premium**: implied vol (VIX) tends to exceed realised vol, meaning the market over-pays for fear. When VRP (VIX / realised_vol_20d - 1) is high, mean-reversion is more likely.

- **VRP threshold:** `vrp > 0.20` (20% implied premium over realised)
- **Entry:** At market close (hold overnight, exit at next open)
- **Direction:** Long SPY when VRP is elevated (expect overnight gap up)

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `vrp_threshold` | 0.20 | Minimum implied/realised premium |
| `lookback_days` | 63 | Realised vol window (≈ 3 months) |
| `position_size` | 0.25 | Fraction of NAV per trade |

### Integration

S2 runs as a callable `(ts, data_replay, portfolio, market) → list[Order]`. The orchestrator converts orders to implied weights for merging.

---

## S4 — News-Driven Tactical

**Type:** News sentiment momentum  
**File:** `src/strategies/s4/`  
**Allocation:** Configurable via `StrategyRegistry`

### Signal Logic

Reads pre-computed LLM ensemble sentiment signals from Redis (written by the SentimentWorker every 15 min). Entry conditions:
1. `score > 0.3` — signal is meaningfully bullish (filters near-neutral signals)
2. `price > EMA20` — price is in an uptrend (avoids buying into a downtrend on sentiment alone)

Exit conditions:
- Stop-loss: position closed if price falls to `entry_price × (1 - stop_loss_pct)`
- Signal expiry: signal older than 30 min → skip (stale news has no edge)

### Scoring Formula

```
score = polarity × confidence
```

Where `polarity ∈ [-1, +1]` is the direction of sentiment and `confidence ∈ [0, 1]` is model certainty. A strong call with low confidence yields a small score — the formula correctly penalises uncertainty.

### LLM Ensemble

Four models queried in parallel via Ollama cloud:
- Kimi K2.6, Qwen3.5, DeepSeek-V4-Pro, GLM-5.1

Each uses **DK-CoT** (Domain Knowledge Chain-of-Thought) prompting:
1. Act as buy-side analyst
2. Reason through cash flows, competition, profitability
3. Provide explicit bull/bear cases
4. Return structured JSON (`polarity`, `confidence`, `reasoning`)

**Divergence check:** If `std(scores) > 0.30` → discard ensemble, use FinBERT local fallback.

### FinBERT Fallback

FinBERT (BERT fine-tuned on financial text) runs locally. Confidence uses **entropic confidence**:
```
confidence = 1 - H(p) / log(3)
```
where `H(p)` is Shannon entropy of the 3-class softmax (positive/negative/neutral). A peaked distribution → high confidence; flat distribution → near-zero score.

### Regime Scaling

Position size is scaled by `regime_multiplier` (written to Redis by RegimeDetector):
```
order_notional = base_size × regime_multiplier
```

The multiplier (0.2× to 1.0×) prevents full-size entries during bear markets or volatility spikes, even when the sentiment signal is strongly positive.

### Key Parameters (`S4Config`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `score_threshold` | 0.3 | Minimum score to trigger BUY |
| `signal_max_age_min` | 30 | Max signal age before stale |
| `stop_loss_pct` | 0.05 | 5% stop-loss from entry |
| `base_position_size` | 0.02 | 2% of NAV per position |

---

## S3 — Cross-Sectional Momentum (R&D Sleeve)

**Status:** Research/development — not deployed in paper trading  
**Type:** Cross-sectional equity momentum  
**File:** `src/strategies/s3/`

### Signal Logic

Ranks all universe securities by 12-1 month return. Goes long top quintile (Q5), short bottom quintile (Q1). Rebalances monthly.

**Universe:** `src/strategies/s3/universe.py` — S&P 500 constituents filtered by liquidity.

**Status:** Gate validation pending. Not active in `StrategyRegistry` until backtest gates pass.

---

## Portfolio Orchestration

All active strategies flow through the `PortfolioOrchestrator` using a **weight-then-order** architecture:

```
S1.compute_target_weights(prices)    → {AAPL: 0.05, NVDA: 0.03, ...}
S2(ts, data_replay, ...)            → orders → implied weights
S4.compute_target_weights(signals)   → {AAPL: 0.02, MSFT: 0.01, ...}

merged = {}
for strategy, alloc_pct in [(S1, 0.50), (S2, 0.30), (S4, 0.20)]:
    for sym, wt in strategy_weights.items():
        merged[sym] = merged.get(sym, 0) + wt * alloc_pct

delta_orders = [BUY/SELL target_qty - current_qty for each sym in merged]
```

This eliminates the double-counting problem where independent strategies each submit full-portfolio orders that would be additively merged.

### Constraint Enforcement

Applied iteratively (up to 10 passes) after weight merging:

| Constraint | Default | Action |
|-----------|---------|--------|
| Max single asset | 10% NAV | Scale down BUY |
| Max strategy exposure | alloc_pct × 1.5 | Scale down excess |
| Max portfolio exposure | 95% NAV | Scale all BUYs |
| Max sector exposure | 25% NAV | Scale sector BUYs |
| Max correlation cluster | corr > 0.70 | Reduce higher-vol |

### Volatility Overlay

`PortfolioVolTargeter` computes EWMA portfolio vol from strategy return histories. BUY quantities are scaled by `target_vol / estimated_vol` (clamped to [0.5×, 2.0×]) so the portfolio targets 10% annualised volatility.
```

- [ ] **Step 2: Verify**

```bash
wc -l docs/strategies.md && grep -n "S1\|S2\|S4\|S3\|Orchestrat" docs/strategies.md | head -20
```

---

## Task 5: Create docs/operations.md

**Files:**
- Create: `docs/operations.md`

- [ ] **Step 1: Write docs/operations.md**

```markdown
# Alembic — Operations Guide

Day-to-day operational reference for running, monitoring, and troubleshooting the system.

---

## Docker Compose Services

| Service | Port | Role |
|---------|------|------|
| `postgres` | 5432 | PostgreSQL 16 (trading database) |
| `redis` | 6379 | Redis 7 (signal cache, task queue) |
| `api` | 8001→8000 | FastAPI application |
| `worker` | — | Celery worker (all task queues) |
| `beat` | — | Celery beat (task scheduler) |
| `frontend` | 3000→80 | React dashboard (Nginx) |
| `grafana` | 3001→3000 | Grafana dashboards |
| `backtest` | — | One-shot backtest runner (profile: backtest) |

### Common Commands

```bash
# Start all services
docker compose up -d

# Rebuild and restart (after code changes)
docker compose build api worker beat frontend
docker compose up -d api worker beat frontend

# View logs (follow)
docker compose logs -f worker
docker compose logs -f beat
docker compose logs -f api

# Stop all services
docker compose down

# Restart a single service
docker compose restart worker

# Run backtest (starts the backtest profile)
docker compose --profile backtest run --rm backtest \
  python scripts/run_backtest.py --start 2025-10-01 --end 2026-04-30 --run-id gkg-6m-v1
```

### Health Checks

```bash
# API health
curl http://localhost:8001/api/health

# PostgreSQL readiness
docker compose exec postgres pg_isready -U trading

# Redis ping
docker compose exec redis redis-cli ping

# Celery worker status
docker compose exec worker celery -A src.workers.celery_app inspect active
```

---

## Celery Beat Schedule

Beat schedules are defined in `src/workers/celery_app.py`. All times are UTC.

| Task name | Cron | Description |
|-----------|------|-------------|
| `run-news-ingestion` | */15 14-21 Mon-Fri | GDELT GKG → news:queue |
| `run-marketaux-ingestion` | */15 14-21 Mon-Fri | MarketAux → news:queue |
| `run-alpaca-ingestion` | */15 14-21 Mon-Fri | Alpaca/Benzinga → news:queue |
| `sentiment-worker` | */15 14-21 Mon-Fri | news:queue → LLM → Redis + PG |
| `run-execution` | */15 14-21 Mon-Fri | signals → Alpaca orders |
| `portfolio-cycle` | 0 14-21 Mon-Fri | PortfolioOrchestrator multi-strategy |
| `regime-detector` | 7:00 Mon-Fri | Macro → LLM pair → regime → Redis |
| `forward-return-worker` | 22:00 daily | Populate `forward_return` after close |
| `risk-monitor` | 22:30 daily | HHI + correlation + drawdown alerts |
| `performance-daily` | 3:00 daily | IC report + drift + Telegram digest |
| `drift-detection` | 4:30 Sunday | PSI + CUSUM over full window |
| `check-suggestion-expiry` | 5:00 daily | Expire stale weight suggestions |
| `performance-weekly` | 4:00 Monday | LOO ICIR → weight suggestion |
| `run-retention-sweep` | 3:30 daily | Old data cleanup |
| `decay-monitor` | 23:00 1st of month | Actual vs backtest baseline |
| `poll-telegram-updates` | every 5s | Process approve/reject callbacks |

### Manual Task Triggering

```bash
# Trigger sentiment worker manually
docker compose exec worker celery -A src.workers.celery_app call \
  src.workers.sentiment.run_sentiment_worker

# Trigger regime detection now
docker compose exec worker celery -A src.workers.celery_app call \
  src.workers.regime.detect_regime

# Run forward-return worker immediately
docker compose exec worker celery -A src.workers.celery_app call \
  src.workers.performance.run_forward_return_worker

# Check scheduled tasks
docker compose exec beat celery -A src.workers.celery_app inspect scheduled
```

---

## Redis Operations

```bash
# Connect to Redis CLI
docker compose exec redis redis-cli

# Read current signal for a symbol
GET sentiment:signal:AAPL

# Check kill-switch state
GET killswitch_active

# Check current operating mode
GET system:mode

# Read regime multiplier
GET regime_multiplier

# Read current ensemble weights
GET ensemble:weights:current

# Check LLM daily budget for a model
GET llm:budget:kimi-k2.6:cloud:2026-06-03

# View news queue depth
LLEN news:queue

# Manually set kill-switch
SET killswitch_active 1

# Manually clear kill-switch (use only after investigation)
SET killswitch_active 0

# Set paper trading mode
SET system:mode paper
```

---

## PostgreSQL Operations

```bash
# Connect to database
docker compose exec postgres psql -U trading -d trading

# Recent signals
SELECT symbol, score, confidence, generated_at 
FROM sentiment_signals 
ORDER BY generated_at DESC 
LIMIT 20;

# IC by symbol over last 30 days
SELECT symbol, 
       CORR(score, forward_return) AS ic,
       COUNT(*) AS n
FROM sentiment_signals
WHERE generated_at >= now() - INTERVAL '30 days'
  AND forward_return IS NOT NULL
GROUP BY symbol
ORDER BY ic DESC;

# Weight update history
SELECT source, applied_weights, freeze_reason, created_at 
FROM weight_update_log 
ORDER BY created_at DESC 
LIMIT 10;

# Recent portfolio cycles
SELECT timestamp, strategies_run, orders_count, constraints_fired
FROM portfolio_cycles
ORDER BY timestamp DESC
LIMIT 10;

# Latest risk report
SELECT timestamp, nav, combined_drawdown, herfindahl_index, jsonb_array_length(alerts) AS n_alerts
FROM risk_reports
ORDER BY timestamp DESC
LIMIT 5;

# Backtest run summary
SELECT run_id, 
       COUNT(*) AS total,
       COUNT(score) AS scored,
       AVG(score) AS avg_score
FROM backtest_signals
GROUP BY run_id
ORDER BY MIN(generated_at) DESC;
```

---

## Grafana Dashboards

Grafana runs on port 3001. Default credentials: `admin / alembic123`.

Anonymous read access is enabled — no login required for viewing.

### Dashboard provisioning

Dashboards are auto-provisioned from `grafana/dashboards/*.json`. To add a new dashboard:
1. Create/export the dashboard JSON from the UI
2. Save to `grafana/dashboards/your-dashboard.json`
3. Restart Grafana: `docker compose restart grafana`

### Data source

The Grafana PostgreSQL data source connects to the `trading` database at `postgres:5432`. Connection is configured in `grafana/provisioning/datasources/`.

### Key panels to watch during paper trading

- **Signal score distribution** — median score and std per day; watch for mean drift
- **IC rolling 30d** — information coefficient; should be consistently positive
- **Daily P&L** — from Alpaca paper account equity curve
- **Kill-switch events** — any unintended activations during overnight sessions
- **Sentiment queue depth** — `news:queue` LLEN; should drain to 0 within 15 min of each ingest

---

## Monitoring Alerts (Telegram)

Telegram alerts are sent to `TELEGRAM_CHAT_ID` via the bot token configured in `.env`.

| Alert type | Level | Trigger |
|-----------|-------|---------|
| Daily IC digest | INFO | Daily 03:00 PerformanceWorker |
| IC below threshold N consecutive days | CRITICAL | Circuit breaker fires |
| PSI > 0.25 (signal distribution drift) | CRITICAL | DriftDetector |
| Weight suggestion ready (guardrails passed) | INFO | Monday 04:00 |
| Weight approval required (guardrail blocked) | INFO | Inline [✅ Approve] [❌ Reject] |
| Drawdown cap reached (≥10% daily loss) | CRITICAL | ExecutionWorker |
| Decay metric CRITICAL | CRITICAL | DecayMonitor (monthly) |
| Risk alert (drawdown, weight drift) | WARNING | RiskMonitor (daily) |

---

## Troubleshooting

### Kill-switch stuck active

```bash
# Check who activated it
docker compose logs worker | grep "kill.switch"

# Clear manually after investigation
docker compose exec redis redis-cli SET killswitch_active 0
docker compose exec redis redis-cli SET system:mode paper
```

### News queue not draining

```bash
# Check queue depth
docker compose exec redis redis-cli LLEN news:queue

# Check sentiment worker logs
docker compose logs worker | grep "SentimentWorker\|sentiment" | tail -50

# Check if beat is running
docker compose ps beat
```

### No signals in Redis

1. Check `news:queue` has items (ingestion running?)
2. Check `system:mode` — if `halted`, no new signals written
3. Check `llm:budget:*` keys — daily budget may be exhausted
4. Check worker logs for LLM connection errors (Ollama cloud timeout)

### PostgreSQL connection pool exhausted

Symptom: `psycopg2.pool.PoolError: connection pool exhausted`

Cause: A worker process did not call `pg.close()` in its `finally` block.

Fix:
```bash
# Restart the worker to release all connections
docker compose restart worker

# Verify pool recovery
docker compose exec postgres psql -U trading -d trading \
  -c "SELECT count(*) FROM pg_stat_activity WHERE datname='trading';"
```

### FinBERT cold-start latency

First article in a new worker process triggers FinBERT model load from disk (~10–30s). This is normal. Subsequent calls in the same process reuse the loaded model.

### Alpaca order rejected

Common causes:
- `account not active` — paper account may need reactivation
- `insufficient buying power` — portfolio fully invested; position already held
- `asset not tradable` — symbol halted or delisted; system logs error and continues

Check logs: `docker compose logs worker | grep "Alpaca\|alpaca\|order" | tail -50`

### yfinance stale data

yfinance occasionally returns cached or incorrect data. If EMA20 values look wrong:
```bash
# Trigger an immediate regime detection with fresh data
docker compose exec worker celery -A src.workers.celery_app call \
  src.workers.regime.detect_regime
```
```

- [ ] **Step 2: Verify**

```bash
wc -l docs/operations.md && grep -n "Docker\|Redis\|Grafana\|Troubleshoot" docs/operations.md | head -15
```

---

## Task 6: Create docs/deployment.md

**Files:**
- Create: `docs/deployment.md`

- [ ] **Step 1: Write docs/deployment.md**

```markdown
# Alembic — Deployment Guide

Step-by-step guide for deploying Alembic to a VPS or cloud instance for paper trading and live trading.

---

## Prerequisites

- Ubuntu 22.04+ (or equivalent Linux)
- Docker 24+ and Docker Compose v2
- Python 3.11+ (for running tests locally)
- Git

---

## Environment Variables

Create `.env` in the project root. All required variables must be set before starting services.

```bash
cp .env.example .env
# Edit .env with your credentials
```

### Required

| Variable | Description |
|----------|-------------|
| `ADMIN_API_KEY` | API key for admin endpoints (min 32 chars; generate with `openssl rand -hex 20`) |
| `DATABASE_URL` | PostgreSQL connection string: `postgresql://trading:trading@postgres:5432/trading` |
| `REDIS_URL` | Redis URL: `redis://redis:6379/0` |
| `ALPACA_API_KEY` | Alpaca API key (from Alpaca dashboard) |
| `ALPACA_SECRET_KEY` | Alpaca secret key |

### Broker

| Variable | Default | Description |
|----------|---------|-------------|
| `ALPACA_BASE_URL` | `https://paper-api.alpaca.markets` | Use paper URL for paper trading |

### Notifications (optional but strongly recommended)

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | From @BotFather |
| `TELEGRAM_CHAT_ID` | Group or channel ID for alerts |
| `TELEGRAM_ALLOWED_USER_IDS` | Comma-separated IDs allowed to approve weights |

### LLM Ensemble

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama cloud or local endpoint |
| `LLM_DAILY_BUDGET_USD` | `50.0` | Daily token spend cap |

### FRED / Macro Data

| Variable | Description |
|----------|-------------|
| `FRED_API_KEY` | FRED API key for VIX and T10Y2Y data |

### Operational

| Variable | Default | Description |
|----------|---------|-------------|
| `WATCHLIST_SYMBOLS` | — | Comma-separated symbols for ExecutionWorker (e.g. `AAPL,NVDA,MSFT,GOOGL`) |
| `AUTO_APPLY_ENABLED` | `true` | Auto-apply weight suggestions when guardrails pass |
| `AUTO_APPLY_VIX_THRESHOLD` | `30.0` | Block auto-apply when VIX ≥ threshold |

---

## Database Initialisation

The PostgreSQL schema must be applied before first run:

```bash
# Apply migration
docker compose up -d postgres
docker compose exec postgres psql -U trading -d trading -f /dev/stdin < migrations/001_initial.sql

# Verify tables exist
docker compose exec postgres psql -U trading -d trading \
  -c "\dt" | grep -E "sentiment|llm|news|weight|portfolio|risk|decay"
```

---

## First Deployment

```bash
# 1. Clone and enter directory
git clone https://github.com/your-org/Alembic.git
cd Alembic
cp .env.example .env
# Edit .env

# 2. Build images
docker compose build

# 3. Start infrastructure services first
docker compose up -d postgres redis
sleep 10  # wait for health checks

# 4. Apply database schema
docker compose exec postgres psql -U trading -d trading -f /dev/stdin < migrations/001_initial.sql

# 5. Start application services
docker compose up -d api worker beat frontend grafana

# 6. Verify all services healthy
docker compose ps
```

---

## Verifying the Deployment

```bash
# API health
curl http://localhost:8001/api/health
# Expected: {"status": "healthy", "redis": "connected", "postgres": "connected"}

# Check operating mode (default: not set)
curl http://localhost:8001/api/admin/status
# Expected: {"killswitch": false, "mode": "unknown", "llm_models": "all"}

# Set paper trading mode
curl -X POST http://localhost:8001/api/admin/mode \
  -H "X-API-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"mode": "paper"}'

# Verify beat schedule is running
docker compose exec beat celery -A src.workers.celery_app inspect scheduled
```

---

## Update Deployment

```bash
# Pull latest changes
git pull origin main

# Rebuild images (only services that changed)
docker compose build api worker beat

# Rolling restart
docker compose up -d --no-deps api worker beat

# Verify
docker compose ps
curl http://localhost:8001/api/health
```

---

## Health Checks

All services have Docker health checks defined in `docker-compose.yml`:

| Service | Check | Interval |
|---------|-------|---------|
| `postgres` | `pg_isready -U trading` | 5s |
| `redis` | `redis-cli ping` | 5s |
| `api` | `GET /api/health` HTTP 200 | 10s |

Services marked `depends_on: condition: service_healthy` will not start until dependencies pass health checks.

---

## Rollback

```bash
# Revert to previous git commit
git log --oneline -5  # find the target commit hash
git checkout <previous-hash>

# Rebuild and redeploy
docker compose build api worker beat
docker compose up -d --no-deps api worker beat

# Verify rollback
docker compose ps && curl http://localhost:8001/api/health
```

If the database schema changed (new migration), rollback may require restoring a database backup. Always snapshot `pgdata` volume before applying migrations.

---

## Backup and Restore

```bash
# Backup PostgreSQL data
docker compose exec postgres pg_dump -U trading trading > backup-$(date +%Y%m%d).sql

# Backup Redis snapshot
docker compose exec redis redis-cli SAVE
docker cp $(docker compose ps -q redis):/data/dump.rdb redis-backup-$(date +%Y%m%d).rdb

# Restore PostgreSQL
docker compose exec postgres psql -U trading trading < backup-20260603.sql
```

---

## Production Security Checklist

Before going live on a real brokerage account:

- [ ] Rotate `ADMIN_API_KEY` (never use a dev key in production)
- [ ] Set `ALPACA_BASE_URL` to the live endpoint (not paper)
- [ ] Restrict `TELEGRAM_ALLOWED_USER_IDS` to authorised operators only
- [ ] Verify `.env` is not committed to git (`git status` shows `.env` under `.gitignore`)
- [ ] Set `AUTO_APPLY_ENABLED=false` for first week of paper trading (manual weight approval)
- [ ] Test kill-switch works: `POST /api/admin/killswitch`, verify mode=halted in Redis
- [ ] Confirm Telegram alerts are received (deploy sends test alert)
- [ ] Verify drawdown cap: set `10%` as starting threshold, monitor first session
- [ ] Enable Grafana authentication for production (disable anonymous access)
```

- [ ] **Step 2: Verify**

```bash
wc -l docs/deployment.md && grep -n "Required\|Rollback\|Backup\|Checklist" docs/deployment.md | head -10
```

---

## Task 7: Add targeted comments to portfolio source files

**Files:**
- Modify: `src/portfolio/orchestrator.py`
- Modify: `src/portfolio/constraints.py`
- Modify: `src/portfolio/vol_targeting.py`

The existing docstrings are already reasonable. This task adds **WHY** comments at the most non-obvious decision points only.

- [ ] **Step 1: Read src/portfolio/orchestrator.py and add missing WHY comments**

In `orchestrator.py`, the module docstring already explains the weight-then-order rationale. Add one inline comment in `run_cycle()` before the "Also sell positions not in merged targets" block:

```python
# Sell any positions whose symbol dropped out of the merged target entirely.
# This handles the case where a strategy that previously held a position
# no longer recommends it — without this loop, exited symbols would persist
# indefinitely in the portfolio.
for pos in portfolio.all_positions():
```

Add one comment before the `_extract_target_weights` dispatch:

```python
# S1 and S4 have a compute_target_weights() method that maps directly to
# the weight-then-order contract. S2 returns Order objects (it's position-
# based, not weight-based), so we infer weights from order notional values.
```

- [ ] **Step 2: Read src/portfolio/constraints.py and add WHY comments**

In `ConstraintEnforcer.__init__` or class docstring, after the existing constraint list, add:

```python
# Constraints are applied iteratively because reducing one order can push
# another constraint into violation (e.g., scaling a high-NAV order down
# may suddenly make a correlated-cluster constraint fire). Up to 10 passes
# guarantees convergence without infinite loops.
```

- [ ] **Step 3: Read src/portfolio/vol_targeting.py and add WHY comment**

In `compute_scale()` method, add before the clamp:

```python
# Clamp scale to [0.5, 2.0] to prevent extreme de-leveraging or over-leveraging.
# Without a floor, a vol spike could scale all orders to near-zero (fully
# exiting all positions). Without a cap, a low-vol period could push leverage
# to 2× or more, violating broker margin requirements.
```

- [ ] **Step 4: Verify files edited correctly**

```bash
grep -n "WHY\|Sell any\|S1 and S4\|Constraints are applied\|Clamp scale" \
  src/portfolio/orchestrator.py src/portfolio/constraints.py src/portfolio/vol_targeting.py
```
Expected: the grep matches in each file.

---

## Task 8: Add targeted comments to workers

**Files:**
- Modify: `src/workers/portfolio_scheduler.py`
- Modify: `src/workers/decay_monitor_task.py`

- [ ] **Step 1: Read portfolio_scheduler.py and add WHY comment for position loading**

After the `alpaca_positions` loading block (around line 137), there is already a comment. Verify it reads:
```python
# Load existing Alpaca positions so delta-orders are computed correctly.
# Without this, the VirtualPortfolio is empty → nav ≈ 0 when account.cash ≈ 0
# (all equity already invested) → all target quantities ≈ 0 → 0 orders.
```
If missing, add it.

- [ ] **Step 2: Read decay_monitor_task.py and add WHY comment for baselines**

In `_BASELINES`, add a comment explaining the source:
```python
# Baseline metrics established from GKG backtest (gkg-6m-v1, Nov 2025 – Apr 2026).
# These are NOT live-validated — they are best-effort estimates. Update after
# first 90 days of paper trading with actual measured metrics.
_BASELINES: dict[str, dict[str, float]] = {
```

- [ ] **Step 3: Verify**

```bash
grep -n "Load existing\|Baseline metrics" \
  src/workers/portfolio_scheduler.py src/workers/decay_monitor_task.py
```

---

## Task 9: Add targeted comments to API routes

**Files:**
- Modify: `src/api/routes/signals.py`
- Modify: `src/api/routes/performance.py`
- Read: `src/api/routes/portfolio.py`, `src/api/routes/trading.py`, `src/api/routes/news_routes.py`, `src/api/routes/llm_routes.py`, `src/api/routes/config_routes.py`, `src/api/routes/strategies.py`, `src/api/routes/backtest.py`

- [ ] **Step 1: Read all API route files and add module-level docstrings where missing**

For any route file that lacks a module-level docstring, add one describing the endpoint group and auth requirements.

Run:
```bash
head -5 src/api/routes/portfolio.py src/api/routes/trading.py \
  src/api/routes/news_routes.py src/api/routes/llm_routes.py \
  src/api/routes/config_routes.py src/api/routes/strategies.py \
  src/api/routes/backtest.py
```

For each file missing a docstring, add:
```python
"""<Endpoint group> endpoints. Auth: <required/not required>."""
```

- [ ] **Step 2: Add WHY comment in signals.py for Redis→PG fallback**

In `get_all_signals()`, after the Phase 1 comment block, add:
```python
# Redis is the primary source (sub-millisecond reads). PostgreSQL fallback handles
# the case where a symbol is in the watchlist but no fresh signal was generated
# in the last 4h (TTL expired). This prevents returning an empty list when Redis
# is temporarily empty after a restart.
```

- [ ] **Step 3: Verify**

```bash
grep -n '"""' src/api/routes/portfolio.py src/api/routes/trading.py \
  src/api/routes/news_routes.py src/api/routes/llm_routes.py \
  src/api/routes/config_routes.py src/api/routes/strategies.py \
  src/api/routes/backtest.py | head -20
```

---

## Task 10: Add targeted comments to src/store/pg_store.py

**Files:**
- Modify: `src/store/pg_store.py`

- [ ] **Step 1: Read pg_store.py lines 100-400 to identify gaps**

```bash
# Read the rest of the file
```

- [ ] **Step 2: Add WHY comment for pool fallback logic**

In `_get_connection()`, after the `PoolError` except block, add:
```python
# Pool exhaustion fallback: create a direct connection instead of blocking.
# This is an emergency path — if the pool is exhausted it means many
# connections were not returned via close(). Investigate root cause.
```

- [ ] **Step 3: Add WHY comment for `ON CONFLICT DO UPDATE` in _INSERT_SIGNAL**

Add inline comment after the `_INSERT_SIGNAL` SQL:
```python
# ON CONFLICT upsert rather than INSERT ONLY: two workers may process different
# articles for the same symbol in the same 15-min window. Last-write-wins is
# intentional here — the more recent article's signal overwrites the older one.
```

- [ ] **Step 4: Verify**

```bash
grep -n "Pool exhaustion\|ON CONFLICT upsert\|emergency path" src/store/pg_store.py
```

---

## Task 11: Add targeted comments to scripts/run_backtest.py

**Files:**
- Modify: `scripts/run_backtest.py`

- [ ] **Step 1: Read scripts/run_backtest.py fully**

```bash
wc -l scripts/run_backtest.py
```

Then read the full file.

- [ ] **Step 2: Add WHY comment for the checkpoint mechanism**

In the main loop where `score IS NULL` rows are selected and processed, add:
```python
# Checkpoint/resume: only process rows where score IS NULL. If the script is
# interrupted mid-run (API timeout, OOM), re-running with the same --run-id
# skips already-scored rows. This makes the backtest idempotent under failure.
```

- [ ] **Step 3: Add WHY comment for dry-run path**

In `_DRY_RUN_UPDATE` usage, add:
```python
# Dry-run writes placeholder scores (0.0) rather than skipping, so the
# forward-return and IC pipeline can still run as a smoke test without
# spending LLM tokens.
```

- [ ] **Step 4: Verify**

```bash
grep -n "Checkpoint\|Dry-run writes\|placeholder" scripts/run_backtest.py
```

---

## Task 12: Commit documentation changes

**Files:** All docs/*.md and README.md

- [ ] **Step 1: Stage documentation files only**

```bash
git add README.md docs/API.md docs/ARCHITECTURE.md docs/strategies.md docs/operations.md docs/deployment.md
```

- [ ] **Step 2: Verify staged files**

```bash
git diff --cached --stat
```
Expected: 6 files changed, only .md files.

- [ ] **Step 3: Commit**

```bash
git commit -m "$(cat <<'EOF'
docs: comprehensive documentation update for Phase G completion

- README: update test count to 1714, add Phase G portfolio orchestrator
  section, update project structure and Celery beat schedule tables
- docs/API.md: full English rewrite with Phase G endpoints (portfolio,
  risk, decay, config, strategies, news, llm)
- docs/ARCHITECTURE.md: translated to English, Phase G architecture,
  Redis key schema, PostgreSQL schema, security table
- docs/strategies.md: new — S1/S2/S3/S4 strategy details, parameters,
  ensemble logic, weight-then-order orchestration reference
- docs/operations.md: new — Docker commands, Celery beat schedule,
  Redis/PG operations, Grafana dashboards, troubleshooting guide
- docs/deployment.md: new — environment variables, first deployment
  steps, health checks, rollback, production security checklist

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4: Verify commit**

```bash
git log --oneline -3
```
Expected: new commit at HEAD with docs message.

---

## Task 13: Commit code comment changes

**Files:** Modified source files

- [ ] **Step 1: Check which source files were modified**

```bash
git diff --name-only HEAD
```
Expected: list of .py files in src/ and scripts/.

- [ ] **Step 2: Stage source files**

```bash
git add src/portfolio/orchestrator.py src/portfolio/constraints.py \
        src/portfolio/vol_targeting.py src/workers/portfolio_scheduler.py \
        src/workers/decay_monitor_task.py src/api/routes/signals.py \
        src/api/routes/performance.py src/store/pg_store.py \
        scripts/run_backtest.py
# Also add any route files that got module docstrings
git add src/api/routes/
```

- [ ] **Step 3: Commit**

```bash
git commit -m "$(cat <<'EOF'
docs: add targeted WHY comments and missing docstrings to Phase G code

- portfolio/orchestrator.py: WHY comments for position exit loop and
  strategy dispatch (S1/S4 weight API vs S2 order→weight inference)
- portfolio/constraints.py: WHY for iterative multi-pass enforcement
- portfolio/vol_targeting.py: WHY for [0.5, 2.0] scale clamp
- workers/portfolio_scheduler.py: confirm position-loading comment
- workers/decay_monitor_task.py: note that baselines are pre-live estimates
- api/routes/signals.py: WHY for Redis→PG fallback design
- api/routes/*: add missing module docstrings to route files
- store/pg_store.py: WHY for pool-exhaustion fallback and upsert choice
- scripts/run_backtest.py: WHY for checkpoint/resume and dry-run semantics

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4: Verify**

```bash
git log --oneline -3
```

---

## Task 14: Rebuild Docker containers

- [ ] **Step 1: Build application images**

```bash
docker compose build api worker beat frontend
```
Expected: `Successfully built` for each image.

- [ ] **Step 2: Deploy updated containers**

```bash
docker compose up -d api worker beat frontend
```
Expected: containers restarted or recreated.

- [ ] **Step 3: Verify all containers healthy**

```bash
docker compose ps
```
Expected: all services show `Up` / `healthy`.

- [ ] **Step 4: Verify API is up**

```bash
curl -s http://localhost:8001/api/health | python3 -m json.tool
```
Expected: `{"status": "healthy", ...}`

---

## Task 15: Run full test suite and report

- [ ] **Step 1: Run tests**

```bash
uv run pytest tests/ -q --tb=line 2>&1 | tail -20
```

- [ ] **Step 2: Verify test count**

Expected: `~1714 passed` (within ±5 of that count). Record actual number.

- [ ] **Step 3: Report to user**

Report: total tests passing, any failures (with file and error), Docker container status.

---

## Self-Review

### Spec coverage check

| Requirement | Task |
|-------------|------|
| README.md updated | Task 1 |
| docs/API.md English + new endpoints | Task 2 |
| docs/ARCHITECTURE.md English + Phase G | Task 3 |
| docs/strategies.md | Task 4 |
| docs/operations.md | Task 5 |
| docs/deployment.md | Task 6 |
| src/portfolio/ comments | Task 7 |
| src/workers/ comments | Task 8 |
| src/api/routes/ comments | Task 9 |
| src/store/pg_store.py comments | Task 10 |
| scripts/run_backtest.py comments | Task 11 |
| Commit docs | Task 12 |
| Commit comments | Task 13 |
| Docker rebuild + deploy | Task 14 |
| Test suite verification | Task 15 |

All requirements covered. ✅

### Placeholder scan

No TBD, TODO, or "implement later" in this plan. All code snippets are complete. ✅

### Type consistency

Only markdown, SQL, and inline comment snippets — no type cross-references needed. ✅
