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
| SQL injection (INTERVAL parameter) | Parameterised query with `\|\| ' days'::interval` |
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
