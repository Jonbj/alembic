<div align="center">
  <img src="../img/alembic.png" alt="Alembic" width="140"/>
</div>

# Alembic — Technical Architecture

**Technical Architecture Document**
**Version:** 7.0.0
**Date:** 2026-06-06
**Status:** Phase A (Trade Analytics) + Phase B (Loss Feedback Loop) + Phase C (Counterfactual Analysis) + Portfolio Governance

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
│  Daily 22:45: CounterfactualWorker → 1h return for SKIP rows     │
│  Daily 03:00: PerformanceWorker → IC + drift + Telegram digest   │
│  Daily 22:30: RiskMonitor → HHI + correlation + drawdown alerts  │
│  Mon  04:00: WeightOptimiser → LOO ICIR → auto-apply / Telegram  │
│  Monthly 1st: DecayMonitor → actual vs backtest baseline         │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│         TRADE OBSERVABILITY, ANALYTICS & AUTO-IMPROVE             │
│                                                                   │
│  Phase A — Trade Analytics Engine                                 │
│    ExecutionWorker (legacy) / PortfolioScheduler (portfolio mode) │
│    ├── write_execution_decision() → execution_decisions table    │
│    │   └── reason TEXT field: LLM reasoning + strategy + weight  │
│    ├── open_trade() / close_trade() → trades table               │
│    └── on stop-loss: _maybe_postmortem() → diagnose_loss()       │
│                           → trades.postmortem_diagnosis           │
│    Analytics API (on-read, no materialization)                   │
│    └── 5 GROUP BY queries over trades + sentiment_signals        │
│        (by symbol, regime, hour-of-day, score bucket, hold time) │
│                                                                   │
│  Phase B — Loss Feedback Loop (every 30 min, market hours)       │
│    LossFeedbackCheck                                              │
│    ├── fetch last N closed trades from PostgreSQL                │
│    ├── detect: N consecutive losses OR negative rolling P&L      │
│    ├── on trigger: raise ENTRY_THRESHOLD (Redis, 48h TTL)        │
│    │              reduce regime_scale (Redis, 48h TTL)           │
│    │              send Telegram ⚠️ alert                          │
│    ├── recovery: consecutive wins → step back toward baseline    │
│    └── cooldown: max 1 adjustment per 4h                         │
│    ExecutionWorker reads Redis keys at each cycle start           │
│                                                                   │
│  Phase C — Counterfactual / Opportunity Cost (daily 22:45 UTC)   │
│    CounterfactualWorker                                           │
│    ├── fetch SKIP_EMA + SKIP_CAP rows without counterfactual     │
│    ├── fetch 1-min Alpaca bars per symbol                        │
│    ├── compute return = (price_T+1h - price_T) / price_T         │
│    └── bulk-write counterfactual_return_1h to execution_decisions│
│    API: GET /api/trades/analytics/counterfactual                 │
│    Frontend: /auto-improve → "Phase C — Opportunity Cost" card   │
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
| `LLMClient` (ABC) | `src/llm/client.py` | Ollama cloud clients: Kimi K2.6, Qwen3.5 (DeepSeek/GLM removed — quota/quality trade-off) |
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
| `StrategyRegistry` | `src/strategies/registry.py` | Active strategy entries; reads `config/strategies.yaml` |
| `ConstraintEnforcer` | `src/portfolio/constraints.py` | 5-pass risk constraint enforcement |
| `PortfolioVolTargeter` | `src/portfolio/vol_targeting.py` | EWMA vol estimation + BUY order scaling |
| `PortfolioRiskMonitor` | `src/portfolio/risk_monitor.py` | Daily HHI, correlation, drawdown alerts |
| `DecayMonitor` | `src/portfolio/decay_monitor.py` | Monthly actual vs backtest baseline |
| `run_portfolio_cycle` | `src/workers/portfolio_scheduler.py` | Celery task: fetch prices → orchestrate → submit to Alpaca |

**Sleeve-local allocation contract:**
Strategies produce sleeve-local weights: fractions of their own sleeve, not the whole portfolio. The orchestrator scales each by `allocation_pct` before summing: `merged[sym] += sleeve_weight × alloc_pct`. This means `allocation_pct` is the sole lever for capital governance — halving S4's `allocation_pct` halves its real capital regardless of what signals it produces.

**Strategy config source of truth:**
`config/strategies.yaml` — allocations, enabled flags, mode labels. `StrategyRegistry` reads this at startup. Startup validation warns on: total enabled allocation > 1.0, S4 > 10%, S2 enabled without milestone gates.

**Execution engine flag:**
`config/trading.yaml` → `execution.engine` controls which worker sends orders:
- `portfolio` (default): only `portfolio-cycle` submits orders; `run-execution` returns early
- `legacy_sentiment`: only `run-execution` submits orders; `portfolio-cycle` returns early
- `disabled`: neither worker submits orders

### 2.5 Strategies

| ID | Name | Allocation | Status | Logic |
|----|------|-----------|--------|-------|
| **S1** | Multi-Lookback Relative Momentum | 50% | Live/paper core | Multi-lookback (1M/3M/6M/12M) vol-normalised returns, cross-sectional z-score across universe; inverse-vol sizing |
| **S2** | Volatility Risk Premium | 0% | **Disabled** (research) | Proxy: overnight gap on low-VRP days. OOS Sharpe −0.55; all gates failed. Needs options infrastructure for v2 |
| **S3** | Cross-Sectional Residual Momentum | 0% | Research | Cross-sectional rank of residual 1-12M returns; possible sizing lookahead; gate 3/5 failed |
| **S4** | News-Driven Tactical | 10% | Paper overlay | LLM ensemble sentiment → BUY gate: score > 0.3 AND price > EMA20; capped at 10% until dedicated gate report |
| **S7** | PEAD (Post-Earnings Announcement Drift) | 15% | Active | Classifica 8-K filing SEC via Ollama (LLM). Weight target basato sulla direzione della sorpresa (positiva/negativa). |

#### S7 — PEAD (Post-Earnings Announcement Drift)
Classifica gli 8-K filing SEC via Ollama (LLM). Il segnale PEAD alimenta il portfolio orchestrator con weight target basato sulla direzione del filing (sorpresa positiva/negativa). Worker: `src/workers/pead_worker.py`. Routes: `src/api/routes/pead_routes.py`. Schedule: ogni 30 min ore 14:00-21:00 UTC (beat: `pead-ingestion`, queue `inference`). Vedi `docs/strategies/s7-pead.md` per la documentazione completa.

Allocation and enabled/disabled state are configured in `config/strategies.yaml`. See that file for authoritative values.

### 2.5b Worker Split

| Worker | Concurrency | Queue | Handles |
|--------|-------------|-------|---------|
| `worker` | 4 | `celery` | Tutti i task tranne FinBERT/Ollama |
| `worker-inference` | 1 | `inference` | Sentiment (FinBERT+Ollama), Regime, PEAD |

Il `worker-inference` ha concurrency=1 per garantire un singolo processo Python che carica FinBERT una sola volta — con concurrency>1, ogni subprocess allocava una copia del modello causando OOM. I task su queue `inference` sono: `sentiment-worker`, `regime-detector`, `pead-ingestion`.

### 2.5c Portfolio Cycle Safeguards

- **Redis cycle lock**: `SET portfolio:cycle:lock NX EX 840` — previene run concorrenti del portfolio orchestrator. TTL 14 min (appena sotto lo schedule di 15 min). Implementato in `src/workers/portfolio_scheduler.py`.
- **Hold minimum 30 min**: le SELL su simboli comprati negli ultimi 30 minuti vengono filtrate tramite `fetch_recently_bought_symbols()` in `src/store/pg_store.py`. Previene roundtrip involontari S4→S1 (S4 compra, S1 riequilibra e vende nello stesso ciclo).
- **FinBERT int8 quantization**: quantizzazione dinamica `torch.qint8` applicata al caricamento del modello in `src/llm/finbert.py` — riduce footprint RAM ~50% senza perdita significativa di accuratezza sul task di sentiment classification.

### 2.6 Execution Engine

| Component | File | Role |
|-----------|------|------|
| `ExecutionWorker` | `src/workers/execution.py` | Sequential safety checklist → Alpaca orders |
| `AlpacaBroker` | `src/brokers/ibkr_adapter.py` | Order placement adapter |
| `_write_decision` | `src/workers/execution.py` | Log each scored symbol's outcome to `execution_decisions` |
| `_maybe_postmortem` | `src/workers/execution.py` | On stop-loss close: gate → diagnose → write `postmortem_diagnosis` |
| `_regime_label` | `src/workers/execution.py` | Convert numeric `regime_mult` to string label for `TradeContext` |

Execution checklist (per tick):
1. Engine guard: check `execution.engine` in `trading.yaml`; return early unless `engine=legacy_sentiment`
2. Kill-switch check (abort if active)
3. EMA20 cache refresh (yfinance, IEX feed on paper tier)
4. Daily drawdown cap check (≥ `risk.portfolio_drawdown` from `trading.yaml`, default 5% → set kill-switch)
5. Per-symbol: freshness check → stop-loss → BUY gate → position size × regime multiplier
6. Write `execution_decisions` row for every symbol that clears `ENTRY_THRESHOLD`
7. `open_trade()` on BUY fill; `close_trade()` on stop-loss (returns trade id)
8. `_maybe_postmortem()` after stop-loss close if loss ≥ 3% (or ≥ 2% with low confidence / high std)

### 2.7 Performance & Monitoring

| Component | File | Role |
|-----------|------|------|
| `PerformanceWorker` | `src/workers/performance.py` | IC (B4 + Newey-West HAC), drift (PSI + CUSUM), auto-weights |
| `ForwardReturnWorker` | `src/workers/performance.py` | Populates `sentiment_signals.forward_return` at market close |
| `LossFeedbackCheck` | `src/workers/performance.py` | Phase B: detects loss patterns, adjusts threshold + regime scale |
| `CounterfactualWorker` | `src/workers/performance.py` | Phase C: computes 1h return for every skipped trade |
| `ICCalculator` | `src/performance/ic.py` | Composite IC B4 with Newey-West HAC standard errors |
| `WeightOptimiser` | `src/performance/weights.py` | LOO ICIR with guardrails (VIX, drawdown, floor/cap) |
| `DriftDetector` | `src/performance/drift.py` | PSI + CUSUM signal distribution drift |
| `diagnose_loss` | `src/performance/postmortem.py` | 10-category loss diagnosis; called by `_maybe_postmortem` after each stop-loss |
| `should_trigger_postmortem` | `src/performance/postmortem.py` | Gate: loss ≥ 3%, or loss ≥ 2% with low confidence or high ensemble_std |

**Postmortem diagnosis categories:** `LOW_SCORE_ENTRY`, `LOW_CONFIDENCE_PASSED`, `ADVERSE_REGIME`, `HIGH_VOLATILITY_EXIT`, `SIGNAL_TOO_OLD`, `HIGH_ENSEMBLE_DIVERGENCE`, `RISK_OFF_REGIME`, `STOP_LOSS_TIGHT`, `OVERNIGHT_RISK`, `UNKNOWN`

### 2.8 Trade Analytics Engine (Phase A)

Analytics are computed **on-read** via SQL GROUP BY — no materialized tables. All five queries run over `trades` (and `sentiment_signals` for score-bucket dimension) filtered by `exit_time >= now() - N days`.

| Dimension | Grouping | Output |
|-----------|----------|--------|
| By Symbol | `trades.symbol` | `label, trade_count, win_rate, avg_net_pnl, total_net_pnl` |
| By Regime | `regime_mult` CASE bucket | same + regime label (bear/caution/neutral/bull/strong_bull) |
| By Hour | `EXTRACT(HOUR FROM entry_time AT TIME ZONE 'America/New_York')` | hour 9–16 EST |
| By Score Bucket | `FLOOR(ss.score * 10)` 0.1-wide bins | score range label (0.3–0.4, etc.) |
| By Hold Time | `exit_time - entry_time` CASE bucket | `<1h` / `1-4h` / `4-8h` / `extended` / `overnight` |

### 2.9 Loss Feedback Loop (Phase B)

Configured in `config/trading.yaml` under `loss_feedback:`.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `consecutive_loss_trigger` | 3 | N consecutive losses → raise threshold |
| `rolling_pnl_window` | 10 | trades summed for rolling P&L trigger |
| `threshold_step` | 0.05 | ENTRY_THRESHOLD raised by this amount per trigger |
| `threshold_max` | 0.60 | ceiling for raised threshold |
| `threshold_baseline` | 0.30 | target for recovery |
| `regime_scale_factor` | 0.80 | regime_mult multiplied by this on trigger |
| `regime_min_scale` | 0.20 | floor for regime scale |
| `cooldown_hours` | 4 | minimum hours between adjustments |
| `recovery_win_streak` | 5 | consecutive wins → step threshold back down |
| `feedback_ttl_hours` | 48 | Redis TTL — adjustments expire automatically |

**Redis keys written:** `feedback:entry_threshold`, `feedback:regime_scale`, `feedback:state` (audit JSON). All have 48h TTL, so adjustments cannot persist indefinitely through system restarts.

**ExecutionWorker reads** `feedback:entry_threshold` and `feedback:regime_scale` at the start of every 15-min cycle via `_load_entry_threshold()` and `_load_feedback_regime_scale()`. If the Redis keys are absent (no active adjustment), the module-level constant `ENTRY_THRESHOLD=0.30` and scale `1.0` are used.

### 2.10 Counterfactual Analysis (Phase C)

Answers: *"For each trade we skipped, what would the 1-hour return have been?"*

- Only `SKIP_EMA` and `SKIP_CAP` decisions are analysed. `SKIP_POSITION` is excluded (position was already open — it's not a missed opportunity).
- Runs nightly at 22:45 UTC. Processes SKIP decisions from the last 7 days that don't have a counterfactual yet (`counterfactual_computed_at IS NULL`).
- Fetches 1-minute Alpaca bars per symbol. Computes: `return = (close_{T+60min} − close_T) / close_T`.
- Stores result in `execution_decisions.counterfactual_return_1h`.
- `GET /api/trades/analytics/counterfactual` aggregates by decision type: avg return, % profitable, total upside missed.

**Interpretation:**
- `SKIP_EMA` with high `avg_return` → EMA filter is too conservative; consider relaxing or removing it in strong-trend regimes.
- `SKIP_CAP` with high `sum_positive_returns` → cycle allocation cap is too tight; consider raising `MAX_CYCLE_NOTIONAL_PCT`.

### 2.11 Storage

| Store | Technology | Schema |
|-------|------------|--------|
| `RedisStore` | Redis 7 | `sentiment:signal:{sym}` TTL 4h; `killswitch_active`; `regime_multiplier`; `ensemble:weights:current`; `system:mode`; `feedback:entry_threshold`; `feedback:regime_scale`; `feedback:state` |
| `PostgreSQLStore` | PostgreSQL 16 | `sentiment_signals`, `llm_responses`, `news_log`, `weight_update_log`, `backtest_signals`, `portfolio_cycles`, `risk_reports`, `decay_reports`, `execution_decisions`, `trades` |

**Tables added by migrations 016–018:**

```sql
-- execution_decisions (016): one row per symbol per tick, score > ENTRY_THRESHOLD
-- Added by migration 018: counterfactual columns
-- Added by migration 020: reason TEXT (human-readable explanation of each decision)
CREATE TABLE execution_decisions (
    id                       BIGSERIAL PRIMARY KEY,
    tick_time                TIMESTAMPTZ NOT NULL,
    symbol                   VARCHAR(20) NOT NULL,
    signal_id                BIGINT REFERENCES sentiment_signals(id),
    score                    DOUBLE PRECISION NOT NULL,
    regime_mult              DOUBLE PRECISION NOT NULL,
    ema_pass                 BOOLEAN NOT NULL,
    decision                 VARCHAR(20) NOT NULL,  -- BUY | SELL | SKIP_EMA | SKIP_CAP | SKIP_POSITION
    order_id                 TEXT,
    reason                   TEXT,                  -- human-readable explanation (migration 020)
    counterfactual_return_1h DOUBLE PRECISION,      -- Phase C: NULL until computed nightly
    counterfactual_computed_at TIMESTAMPTZ,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- trades (016): one row per round-trip (open → close)
-- Added by migration 017: postmortem_diagnosis
CREATE TABLE trades (
    id                   BIGSERIAL PRIMARY KEY,
    symbol               VARCHAR(20) NOT NULL,
    signal_id            BIGINT REFERENCES sentiment_signals(id),
    decision_id          BIGINT REFERENCES execution_decisions(id),
    entry_order_id       TEXT NOT NULL,
    entry_price          DOUBLE PRECISION,
    entry_time           TIMESTAMPTZ NOT NULL,
    entry_notional       DOUBLE PRECISION NOT NULL,
    score                DOUBLE PRECISION NOT NULL,
    regime_mult          DOUBLE PRECISION NOT NULL,
    exit_price           DOUBLE PRECISION,
    exit_time            TIMESTAMPTZ,
    exit_reason          VARCHAR(20),               -- stop_loss | take_profit | manual
    qty                  DOUBLE PRECISION,
    gross_pnl            DOUBLE PRECISION,
    slippage_est         DOUBLE PRECISION,
    net_pnl              DOUBLE PRECISION,
    postmortem_diagnosis TEXT,                      -- Phase A: NULL if no postmortem triggered
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

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
SentimentWorker (batch 21 items/cycle, semaphore=3 concurrent)
    ├── sanitize_text()
    ├── LLM Ensemble (2 × Ollama cloud: Kimi K2.6 + Qwen3.5-397B, asyncio.gather)
    │   ├── divergence check (std > 0.30 → FinBERT via run_in_executor)
    │   └── budget check (daily cap → FinBERT via run_in_executor)
    ├── score = polarity × confidence
    ├── SET sentiment:signal:{sym} EX 14400 (Redis, TTL 4h)
    └── INSERT sentiment_signals (PostgreSQL, permanent)
    │
    ▼
ExecutionWorker (every 15 min, active only when execution.engine=legacy_sentiment)
    ├── GET killswitch_active
    ├── GET regime_multiplier × GET feedback:regime_scale  (Phase B)
    ├── GET feedback:entry_threshold (or default 0.30)      (Phase B)
    ├── For each symbol in watchlist:
    │   ├── GET sentiment:signal:{sym}
    │   ├── freshness check (< 30 min)
    │   ├── stop-loss check → close_trade() → _maybe_postmortem()
    │   ├── BUY gate: score > entry_threshold AND price > EMA20
    │   ├── order_notional = base × (regime_mult × feedback_scale)
    │   └── write_execution_decision() (one row per scored symbol)
    ├── open_trade() on BUY fill
    └── Alpaca SDK market order
    │
    ▼
PortfolioOrchestrator (hourly, active only when execution.engine=portfolio)
    ├── StrategyRegistry → active entries from config/strategies.yaml
    │   currently: S1 (alloc=0.50) + S4 (alloc=0.10); S2 disabled
    ├── S1.compute_target_weights(prices) → sleeve-local weights
    ├── S4.compute_target_weights(signals, as_of=ts) → sleeve-local weights
    ├── merge: merged[sym] += sleeve_weight × alloc_pct  (weighted sum, NOT average)
    ├── delta orders: target_qty - current_qty
    ├── ConstraintEnforcer (5 passes)
    ├── PortfolioVolTargeter (instantiated but inactive — strategy_returns not wired)
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
| `run-execution` | */15 14-21 Mon-Fri | signals → Alpaca orders (active only when `execution.engine=legacy_sentiment`) |
| `portfolio-cycle` | 0 14-21 Mon-Fri | Weight-then-order multi-strategy (active only when `execution.engine=portfolio`) |
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
| `loss-feedback-check` | */30 14-21 Mon-Fri | Phase B: detect loss patterns → adjust threshold/regime scale |
| `counterfactual-worker` | 22:45 daily | Phase C: compute 1h counterfactual returns for SKIP rows |

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

See `README.md` → *Pre-Live Blockers* section for the authoritative list of critical bugs.

### Phase A + B + C Known Limitations

| Gap | Description | Planned |
|-----|-------------|---------|
| NULL P&L on notional orders | `qty` can be NULL at stop-loss close if fill hasn't been reconciled; `reconcile_trade_fills` window is 24h | Wire Alpaca position qty at close |
| Vol targeting not active | `PortfolioVolTargeter` is instantiated in `portfolio_scheduler.py` but `strategy_returns` is not passed to `run_cycle()` — vol scaling branch never executes | Wire strategy returns from DB |
| Strategies API placeholder | `GET /api/strategies` equity curves use `random.gauss()`; gate `passed` values are not from actual metrics | Phase D |
| Analytics tab empty on fresh deploy | All analytics charts show "No data yet" until closed trades accumulate in the `trades` table | Operational |
| Auto-Improve counterfactual empty | Phase C data requires at least one nightly run of `counterfactual-worker` after SKIP decisions are recorded | Operational |
| S4 no dedicated gate report | `reports/s4_backtest/` does not exist; S4 allocation capped at 10% until this is produced | Research |
| S2 proxy vs real options | Current S2 is an equity proxy (overnight gap); actual cash-secured short put needs options chain data + IBKR adapter | Phase D |
| ConstraintEnforcer loses sleeve provenance | Final merged orders have `strategy_id="merged"`; per-sleeve exposure constraints cannot be enforced | Future |
| Feedback loop blind to S1 | `run_loss_feedback_check` reads `trades` table which today is populated only by `run-execution` (S4 flow). Portfolio-cycle trades not yet written to `trades`. | Wire portfolio_scheduler to open/close_trade |
