<div align="center">
  <img src="../img/alembic.png" alt="Alembic" width="140"/>
</div>

# Alembic — Technical Architecture

**Technical Architecture Document**
**Version:** 7.1.0
**Date:** 2026-07-03
**Status:** Phase A/B/C + Portfolio Governance + Sprint 1 remediation (FIX-01/02/03, EN-03, B13/B20, resolver enforcement, gate thresholds) + S2-1 Source P&L Funnel. S7 REMOVED 2026-07-15 (ALPHA-A3 confuted, POC-2 FAIL).

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
│  (GDELT GKG,                    (id + content-hash dedup, TTL)   │
│   Alpaca News;     ▼                                             │
│   MarketAux/RSS SentimentWorker ──► LLM Ensemble (2 models)      │
│   OFF 2026-07-03)                                                │
│                                         ↓              ↓         │
│                                   Redis signal    PostgreSQL      │
│                                   (TTL 4h)        audit trail    │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                   REGIME DETECTION (daily 07:00 UTC)              │
│                                                                   │
│  FRED API (VIX, T10Y2Y) ──► RegimeDetector ──► Redis            │
│  yfinance (SPY momentum)      LLM pair       regime:current +   │
│                                              qc:sizing_multiplier│
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│      PORTFOLIO ORCHESTRATION (every 15 min, 14-21 UTC, Mon-Fri)   │
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
│  Daily 22:45: CounterfactualWorker → 1h return for gate skips    │
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
│    ├── detect: EWMA R <= -0.50 OR N consecutive teaching losses  │
│    ├── on trigger: raise ENTRY_THRESHOLD (Redis, 96h TTL)        │
│    │              send Telegram ⚠️ alert                          │
│    ├── recovery: consecutive wins → step back toward baseline    │
│    ├── decay: 24h without a trigger → step back one notch        │
│    └── cooldown: max 1 adjustment per 4h                         │
│    Portfolio scheduler enforces feedback:entry_threshold         │
│                                                                   │
│  Phase C — Counterfactual / Opportunity Cost (daily 22:45 UTC)   │
│    CounterfactualWorker                                           │
│    ├── fetch SKIP_THRESHOLD + SKIP_EMA + SKIP_CAP rows            │
│    │   without counterfactual                                     │
│    ├── fetch 1-min Alpaca bars per symbol                        │
│    ├── compute return = (price_T+1h - price_T) / price_T         │
│    └── bulk-write counterfactual_return_1h to execution_decisions│
│    API: GET /api/trades/analytics/counterfactual                 │
│    Frontend: /auto-improve → "Phase C — Opportunity Cost" card   │
└──────────────────────────────────────────────────────────────────┘
```

> The companion `feedback:regime_scale:S*` lever that lived next to
> `feedback:entry_threshold:S*` (F8) was retired 2026-08-10 (#134, lifecycle:
> `docs/F8_LIFECYCLE_HISTORY_2026-08-10.md`): premise falsified on the
> per-DAY unit, mechanism independently broken. Only the threshold ratchet
> survives.

---

## 2. Component Catalogue

### 2.1 News Ingestion

| Component | File | Role |
|-----------|------|------|
| `GDELTGKGConnector` | `src/connectors/gdelt_gkg.py` | Fetches 15-min GKG bulk CSVs, extracts English financial themes |
| `MarketAuxConnector` | `src/connectors/marketaux.py` | **Disabled from beat 2026-07-03 (FIX-01, net-negative)** — paid news API with pre-tagged tickers; env-gated |
| `AlpacaNewsConnector` | `src/connectors/alpaca_news.py` | Broker-native Benzinga news |
| `SecEdgarConnector` | `src/connectors/sec_edgar.py` | SEC EDGAR 8-K/10-Q filings |
| `NewsDeduplicator` | `src/connectors/deduplicator.py` | id dedup + **content-hash+ticker cross-source dedup (EN-03)** via Redis SET NX (TTL 4h) |
| `TickerExtractor` | `src/connectors/ticker_extractor.py` | Company name → ticker via PostgreSQL lookup |

> `EarningsCalendarProvider` (`src/connectors/earnings_calendar.py`) and the PEAD
> 8-K worker/strategy were **REMOVED 2026-07-15** with S7 retirement. See
> `docs/S7_LIFECYCLE_HISTORY_2026-07-15.md`.

### 2.2 Sentiment Pipeline

| Component | File | Role |
|-----------|------|------|
| `SentimentWorker` | `src/workers/sentiment.py` | Consumes `news:queue`; skips news older than `MAX_NEWS_AGE_HOURS` (**2h**, FIX-03) pre-inference; resolver runs **before** inference and drops `NO_TRADE_NOT_TRADABLE` items (conservative enforcement, fail-open); writes signal with `published_at` |
| `LLMClient` (ABC) | `src/llm/client.py` | Ollama cloud clients; active pair via Redis `config:sentiment_llm_models` (dal 2026-07-11: `glm52,gptoss`); registry `src/llm/model_registry.py` — i candidati swap (qwen35, gptoss) hanno `in_all=False`, quindi "all" resta il set live a 2 modelli |
| Stage-2 shadow | `src/workers/shadow_*` + `llm_shadow_responses` (migration 038) | Model-comparison shadow mode (merged 2026-07-15): dedicated `ollama:sem:shadow` pool, Redis arm/disarm toggle, fire-and-forget candidate scoring with total live-path isolation, pairwise comparison (models + pair replay), 7-day auto-report with self-disarm. Shadows candidate models against the live pair without touching the productive path. Armato via `scripts/auto_arm_shadow_monday.sh` (cron lunedì 09:00 Rome). |
| `EnsembleAggregator` | `src/llm/ensemble.py` | Weighted averaging + divergence check (std ≥ `ENSEMBLE_DIVERGENCE_STD`, **0.40** dal 2026-07-09; i raw output divergenti sono persistiti in `llm_responses` con `eligible=false` dal 2026-07-11) |
| `FinBERTClient` | `src/llm/finbert.py` | Local fallback: entropic confidence from 3-class softmax |
| `LLMBudgetTracker` | `src/llm/budget.py` | Daily spend cap per model — PostgreSQL `llm_budget` + Redis `budget_exhausted` flag |
| `sanitize_text` | `src/text/sanitizer.py` | Strip BiDi overrides, homoglyphs, NFKC normalisation |

**Signal formula:** `score = polarity × confidence` where polarity ∈ [-1, +1] and confidence ∈ [0, 1].

**Per-symbol selection (live cycle):** `fetch_signals_for_cycle` returns one signal per
symbol within the freshness window (`max_signal_age_hours`, default 4h), preferring the
most recent **ensemble** signal over a FinBERT fallback (`ORDER BY symbol,
fallback_used ASC, generated_at DESC`). A low-conviction fallback generated after a
strong ensemble signal therefore does not overwrite it; a fallback is used only when no
ensemble signal exists in the window.

**Event-time gate (FIX-03):** the live cycle additionally filters on
`sentiment_signals.published_at` — signals whose *news* is older than
`MAX_NEWS_AGE_HOURS` (default 2h) are excluded from S4 entry, even if the signal itself
is recent. NULL `published_at` (legacy rows) passes. The bound is applied **only** at
the S4 entry fetch; sell-protection and audit lookups deliberately see older signals
(`fetch_signals_for_cycle(news_age_hours=None)` default).

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
| `ConstraintEnforcer` | `src/portfolio/constraints.py` | 5-pass risk constraint enforcement (single-asset, strategy-exposure, portfolio-exposure, **sector-exposure**, correlation-cluster) |
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

**Sector exposure cap (2026-07-13, shipped disabled):** the `MAX_SECTOR_EXPOSURE` pass is wired (sector map: 96 symbols / 11 groups). `risk.max_sector_exposure: 0.0` in `trading.yaml` = DISABLED (≤0 disables). Complementary to F9a — caps concentration, does not fix sub-sigma stops. Operator flip value suggested: 0.10.

### 2.5 Strategies

| ID | Name | Allocation | Status | Logic |
|----|------|-----------|--------|-------|
| **S1** | Multi-Lookback Relative Momentum | 50% | `supervised_paper` (demoted P0-01) | Multi-lookback (1M/3M/6M/12M) vol-normalised returns, cross-sectional z-score across universe; inverse-vol sizing. **Live not authorized.** |
| **S2** | Volatility Risk Premium | 0% | **Disabled** (research) | Proxy: overnight gap on low-VRP days. OOS Sharpe −0.55; all gates failed. Needs options infrastructure for v2 |
| **S3** | Cross-Sectional Residual Momentum | 0% | Research | Cross-sectional rank of residual 1-12M returns; PIT sizing wired (P1-07); gate 3/5 failed |
| **S4** | News-Driven Tactical | 10% | `promotion_blocked` (P0-13) | LLM ensemble sentiment → BUY gate: score > 0.3 AND price > EMA20; capped at 10% until dedicated gate report |

> **S7 (PEAD) — REMOVED 2026-07-15.** Strategy dir, workers, routes, beat tasks
> (`pead-ingestion`, `earnings-pead`), config and tests deleted. The declared edge
> (transcript tone → alpha, ALPHA-A3) was confuted at decision-grade (POC-2 FAIL
> n=73, IC≈0; POC-1 INCONCLUSIVE n=15; ALPHA-A5 large-cap FAIL = beta). PO-5
> conditional *"Se POC-2 FAIL → REMOVE"* activated. Lifecycle history +
> evidence: `docs/S7_LIFECYCLE_HISTORY_2026-07-15.md`, `reports/s7_*`. Code
> recoverable from git. Re-introduction requires a fresh design + gate pass (guard:
> `tests/test_p0_13_strategy_containment.py::TestS7NotInOperationalRegistry`).

Allocation and enabled/disabled state are configured in `config/strategies.yaml`. The authoritative runtime state is in the `strategy_lifecycle` DB table. Live trading is NOT authorized for any strategy.

### 2.5b Worker Split

| Worker | Concurrency | Queue | Handles |
|--------|-------------|-------|---------|
| `worker` | 4 | `celery` | Tutti i task tranne FinBERT/Ollama |
| `worker-inference` | 1 | `inference` | Sentiment (FinBERT+Ollama), Regime |

Il `worker-inference` ha concurrency=1 per garantire un singolo processo Python che carica FinBERT una sola volta — con concurrency>1, ogni subprocess allocava una copia del modello causando OOM. I task su queue `inference` sono: `sentiment-worker`, `regime-detector`. (PEAD beat tasks removed 2026-07-15 con S7.)

### 2.5c Portfolio Cycle Safeguards

- **Redis cycle lock**: `SET portfolio:cycle:lock NX EX 1200` — previene run concorrenti del portfolio orchestrator. TTL 20 min (sopra lo schedule di 15 min). Implementato in `src/workers/portfolio_scheduler.py`.
- **Hold minimum 90 min** (`execution.hold_minimum_minutes`, trading.yaml): le SELL su simboli comprati negli ultimi 90 minuti vengono filtrate tramite `fetch_recently_bought_symbols()` in `src/store/pg_store.py`. Previene roundtrip involontari S4→S1 (S4 compra, S1 riequilibra e vende nello stesso ciclo). Gli exit da stop-loss bypassano il filtro.
- **FinBERT int8 quantization**: quantizzazione dinamica `torch.qint8` applicata al caricamento del modello in `src/llm/finbert.py` — riduce footprint RAM ~50% senza perdita significativa di accuratezza sul task di sentiment classification.

### 2.5d Stop-Loss Policy (F9a redesign, 2026-07-11/12)

The portfolio path (engine=portfolio) handles stops via `StopPolicy` (`src/portfolio/stop_policy.py`), NOT the legacy ExecutionWorker checklist in §2.6.

| Component | File | Role |
|-----------|------|------|
| `StopPolicy` | `src/portfolio/stop_policy.py` | Freeze-at-entry + per-cycle protective check + `d_hard` broker disaster distance |
| `FrozenStop` | dataclass | Persisted on the trade row at entry: `mode`, `vol_at_entry`, `sigma_eff`, `k`, `floor`, `cap`, `d_init`, `vol_source` |
| `_stop_loss_breached_symbols` | `src/workers/portfolio_scheduler.py` | Per-cycle: force-close positions at/below the frozen protective trigger |
| `StopPolicy.d_hard` | `src/portfolio/stop_policy.py` | Broker disaster stop distance — wider than `d_init`, `clip([floor_pct, cap_pct])`, default 12-20% |
| `stop_decisions` / `stop_shadow_log` | PostgreSQL (migration 034) | Fire log + shadow audit (d_hard trigger/breach per held position) |

**Modes** (`config/trading.yaml` → `risk.stop_loss_mode`):
- `fixed` (ship): `d_init = stop_loss` (flat pct). 2026-07-15: `stop_loss: 0.0` → protective check **disabled** (see Current state).
- `vol_scaled` (implemented, parked): `d_init = clip(k·σ_entry, floor, cap)` per strategy (`stop_strategy_params`). Gate OOS FAIL 07-12 (bootstrap 41.5%); recalibrated 07-15 (Kimi) to S1 (k8/0.04/0.15), S4 (k8/0.025/0.12) → PASS marginale (71.6%); **not enabled** — operator chose the more aggressive no-protective path.

**Stop-risk sizing (§6.4):** a wider stop sizes down qty so $ risk per position is bounded (`Notional ≤ NAV·B_strat / (d_init + gap_buffer)`). Active in the live scheduler order-sizing path.

**Current state (2026-07-15, paper):** protective 2% stop **DISABLED** (`stop_loss: 0.0`). Rationale: Kimi OOS replay showed `no_protective` cum P&L $-56 vs `fixed_2pct` $-419 — the 2% noise stop destroyed 7.5x more alpha than it protected (07-10 PANW/WDC/DELL stop-outs on 0.26-0.53σ that recovered). `stop_shadow_enabled: true` keeps `d_hard` (12-20%) as SHADOW telemetry only (`stop_shadow_log`) — no enforced floor. Revisit trigger: if a position rides past -15/20% per the shadow log, wire `d_hard` to a real broker order (catastrophe-only). Disable guard: `_stop_loss_breached_symbols` returns `{}` when `stop_loss <= 0 and mode == fixed`.

### 2.6 Execution Engine

| Component | File | Role |
|-----------|------|------|
| `ExecutionWorker` | `src/workers/execution.py` | Sequential safety checklist → Alpaca orders |
| Alpaca order submission | `alpaca-py` diretto in `execution.py` / `portfolio_scheduler.py` | Nessuna classe `AlpacaBroker` esiste; `src/brokers/ibkr_adapter.py` contiene solo `IBKRAdapter` (non usato dal path live) |
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
| `LossFeedbackCheck` | `src/workers/performance.py` | Phase B: detects loss patterns, adjusts entry threshold and writes feedback audit state |
| `CounterfactualWorker` | `src/workers/performance.py` | Phase C: computes 1h return for every skipped trade |
| `MobileMonitorSnapshot` | `src/workers/mobile_monitor_task.py` | Produces one coherent atomic Redis read model per minute, persists a PostgreSQL fallback (immediately on Redis write failure; otherwise on history cadence), and warms bounded SPY caches outside HTTP requests |
| `MobileAlertEvaluator` | `src/workers/mobile_alert_task.py` | Evaluates incident lifecycle, reconciles rejected/canceled broker orders into the durable event feed, and drains the notification outbox |
| Mobile read API | `src/api/routes/mobile_read.py` | Read-only `/api/mobile/v1` snapshot, performance, positions, and signed-cursor event projections; HTTP handlers never fan out to Alpaca |
| `ICCalculator` | `src/performance/ic.py` | Composite IC B4 with Newey-West HAC standard errors |
| `WeightOptimiser` | `src/performance/weights.py` | LOO ICIR with guardrails (VIX, drawdown, floor/cap) |
| `DriftDetector` | `src/performance/drift.py` | PSI + CUSUM signal distribution drift |
| `diagnose_loss` | `src/performance/postmortem.py` | 10-category loss diagnosis; called by `_maybe_postmortem` after each stop-loss |
| `should_trigger_postmortem` | `src/performance/postmortem.py` | Gate: loss ≥ 3%, or loss ≥ 2% with low confidence or high ensemble_std |

**Postmortem diagnosis categories:** `LOW_SCORE_ENTRY`, `LOW_CONFIDENCE_PASSED`, `ADVERSE_REGIME`, `HIGH_VOLATILITY_EXIT`, `SIGNAL_TOO_OLD`, `HIGH_ENSEMBLE_DIVERGENCE`, `RISK_OFF_REGIME`, `STOP_LOSS_TIGHT`, `OVERNIGHT_RISK`, `UNKNOWN`

### 2.8 Operator Cockpit (P2-04)

| Component | File | Role |
|-----------|------|------|
| `get_cockpit_alerts()` | `src/monitoring/cockpit.py` | Aggregates 8 operator alert flags from Redis + DB |
| `GET /api/system/readiness` | `src/api/routes/system_routes.py` | HTTP endpoint exposing cockpit dict (always 200, check body) |
| `GET /api/system/decisions` | `src/api/routes/system_routes.py` | Recent execution decisions from `execution_decisions` table |
| `_check_divergence_and_alert()` | `src/workers/portfolio_scheduler.py` | Fires signal/order divergence Telegram alerts after each cycle |

**Cockpit alert keys (all returned by `get_cockpit_alerts()`):**

| Key | Healthy value | Alert condition |
|-----|--------------|-----------------|
| `redis_healthy` | `true` | Redis PING failed |
| `redis_writeable` | `true` | Redis SET failed — MISCONF / AOF error |
| `db_healthy` | `true` | PostgreSQL query raised exception |
| `killswitch_active` | `false` | Kill-switch key set in Redis |
| `stale_signals` | `false` | Last signal age > `staleness_hours` (default 2h) |
| `worker_beat_lag` | `false` | Last cycle age > `beat_threshold_minutes` (default 60 min) |
| `last_signal_age_minutes` | float/null | Minutes since last signal (null = no signals) |
| `last_cycle_age_minutes` | float/null | Minutes since last cycle (null = no cycles) |

**Redis MISCONF detection:** `redis_healthy=True` but `redis_writeable=False` means Redis accepted PING but rejected SET. This occurs when AOF/RDB persistence is misconfigured or disk is full. In this state signals cannot be written to Redis even though connectivity appears intact.

**Divergence alerting:** `_check_divergence_and_alert()` is called after each portfolio cycle. It fires `AlertLevel.WARNING` Telegram alerts when:
- `check_signal_divergence(signal_syms, order_syms)`: Jaccard overlap < 0.8 (defined in `src/monitoring/alerts.py`)
- `check_execution_divergence(fill_ratio, 1.0)`: |fill_ratio − 1.0| > 0.20

**Strategy lifecycle / promotion gate:** `src/strategies/promotion.py` implements an ordered state machine (`research → paper → supervised_paper → live`). Promotions require: `promotion_blocked=False`, `gate_report_id` set, `GLOBAL_LIVE_PROMOTION_ENABLED=True` (currently `False`), and sequential transition. Demotions are always allowed. Every transition is appended to `strategy_lifecycle_audit` (immutable). Authoritative runtime state: `strategy_lifecycle` DB table (historical P2 status archived in `docs/archive/2026-06-p2-milestone/`).

### 2.9 Trade Analytics Engine (Phase A)

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
| `cooldown_hours` | 4 | minimum hours between adjustments |
| `recovery_win_streak` | 3 | consecutive wins → step threshold back down (5→3, 2026-07-09) |
| `rolling_pnl_drawdown_pct` | 0.005 | il rolling loss deve superare questa frazione dell'equity per triggerare (2026-07-10; prima bastava un rolling P&L < 0 di qualsiasi entità) |
| `threshold_decay_hours` | 24 | decay automatico della soglia verso il baseline dopo 24h senza trigger (2026-07-10) |
| `feedback_ttl_hours` | 96 | Redis TTL — adjustments expire automatically (48→96 on 2026-07-21, #32: the check runs Mon–Fri only, so a 48h key expired across the weekend and reset the threshold to baseline every Monday) |

**Redis keys written:** `feedback:entry_threshold:<strategy>`, `feedback:state:<strategy>` (audit JSON). All carry the 96h TTL, so adjustments cannot persist indefinitely through system restarts.

**Portfolio scheduler reads** `feedback:entry_threshold:<strategy>` and enforces it before S4 ranking/order generation, logging dropped signals as `SKIP_THRESHOLD`.

> The companion `feedback:regime_scale:<strategy>` lever that previously sat next
> to `feedback:entry_threshold:<strategy>` (F8) was retired 2026-08-10 (#134,
> lifecycle: `docs/F8_LIFECYCLE_HISTORY_2026-08-10.md`). The per-day
> serial-dependence premise that an equity-curve de-risk rule requires
> disappears once a sleeve's many concurrent positions are de-duplicated to
> one observation per exit day (S1 +0.318 → +0.065, S4 +0.459 → +0.017), and
> the trigger/decay clocks collided in a way that made the recovery branch
> unreachable for losing sleeves. Code is recovered from git; re-introduction
> must pass for a fresh design + premise retest.

### 2.10 Counterfactual Analysis (Phase C)

Answers: *"For each trade we skipped, what would the 1-hour return have been?"*

- `SKIP_THRESHOLD`, `SKIP_EMA` and `SKIP_CAP` decisions are analysed. `SKIP_POSITION` is excluded (position was already open — it's not a missed opportunity). `SKIP_STALE` and `SKIP_FALLBACK` are excluded because they are signal freshness/reliability failures.
- Runs nightly at 22:45 UTC. Processes SKIP decisions from the last 7 days that don't have a counterfactual yet (`counterfactual_computed_at IS NULL`).
- Fetches 1-minute Alpaca bars per symbol. Computes: `return = (close_{T+60min} − close_T) / close_T`.
- Stores result in `execution_decisions.counterfactual_return_1h`.
- `GET /api/trades/analytics/counterfactual` aggregates by decision type: avg return, % profitable, total upside missed.

**Interpretation:**
- `SKIP_THRESHOLD` with high `avg_return` and enough observations → feedback gate may be too restrictive; review with IC/label evidence before changing thresholds.
- `SKIP_EMA` with high `avg_return` → EMA filter is too conservative; consider relaxing or removing it in strong-trend regimes.
- `SKIP_CAP` with high `sum_positive_returns` → cycle allocation cap is too tight; consider raising `MAX_CYCLE_NOTIONAL_PCT`.

### 2.11 Storage

| Store | Technology | Schema |
|-------|------------|--------|
| `RedisStore` | Redis 7 | `signal:{sym}:sentiment` TTL 4h; `killswitch_active`; `regime:current` (JSON) + `qc:sizing_multiplier`; `ensemble:weights:current`; `system:mode`; `feedback:entry_threshold`; `feedback:regime_scale`; `feedback:state`; `config:sentiment_llm_models`; `portfolio:value` |
| `PostgreSQLStore` | PostgreSQL 16 | `sentiment_signals`, `llm_responses`, `news_log`, `weight_update_log`, `backtest_signals`, `portfolio_cycles`, `risk_reports`, `decay_reports`, `execution_decisions`, `trades`, `strategy_lifecycle`, `strategy_lifecycle_audit` |

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
    decision                 VARCHAR(20) NOT NULL,  -- BUY | SELL | SKIP_THRESHOLD | SKIP_STALE | SKIP_FALLBACK | SKIP_EMA | SKIP_CAP | SKIP_POSITION
    order_id                 TEXT,
    reason                   TEXT,                  -- human-readable explanation (migration 020)
    counterfactual_return_1h DOUBLE PRECISION,      -- Phase C: NULL until computed nightly
    counterfactual_computed_at TIMESTAMPTZ,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- pead_signals: REMOVED 2026-07-15 con S7 retirement. (This DDL was doc-only — no
-- migration ever created the table in the live DB. The schema is kept here as a
-- historical record of the removed S7/PEAD surface; see S7_LIFECYCLE_HISTORY.)
-- CREATE TABLE pead_signals (
--     id              BIGSERIAL PRIMARY KEY,
--     symbol          VARCHAR(20) NOT NULL,
--     score           DOUBLE PRECISION,
--     direction       VARCHAR(20),   -- positive | negative | inline
--     confidence      DOUBLE PRECISION,
--     category        VARCHAR(50),   -- earnings_beat | earnings_miss | etc.
--     filing_url      TEXT,
--     classified_at   TIMESTAMPTZ NOT NULL DEFAULT now()
-- );

-- strategy_lifecycle (026): one row per strategy, immutable audit via strategy_lifecycle_audit
CREATE TABLE strategy_lifecycle (
    strategy_id      VARCHAR(20) PRIMARY KEY,
    mode             VARCHAR(30) NOT NULL,    -- research | paper | supervised_paper | live | disabled
    target_mode      VARCHAR(30),             -- pending promotion target (NULL if none)
    gate_report_id   TEXT,                   -- evidence link for promotion
    approved         BOOLEAN NOT NULL DEFAULT FALSE,
    promotion_blocked BOOLEAN NOT NULL DEFAULT FALSE,
    promoted_by      VARCHAR(100),
    promoted_at      TIMESTAMPTZ,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE strategy_lifecycle_audit (
    id               BIGSERIAL PRIMARY KEY,
    strategy_id      VARCHAR(20) NOT NULL,
    from_mode        VARCHAR(30),
    to_mode          VARCHAR(30),
    action           VARCHAR(20),  -- requested | approved | demoted
    actor            VARCHAR(100),
    reason           TEXT,
    gate_report_id   TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
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
    ├── dedup: by id AND by content-hash+ticker (EN-03, Redis SET NX TTL 4h)
    ├── TickerExtractor (PostgreSQL ticker_lookup) + RSS cashtag/ambiguity guard
    │       bare F/T/C/GS/CAT/ON… require a $cashtag (minimise false_positive_ticker_rate)
    │       [ticker-resolution layer: built/verified, enforcement gated — see §3.1]
    └── LPUSH news:queue (annotated NewsItem JSON)
    │
    ▼
SentimentWorker (batch 12 items/cycle, semaphore=2 concurrent)
    ├── skip news older than MAX_NEWS_AGE_HOURS (2h) — FIX-03
    ├── resolver (shadow log + conservative enforcement: NO_TRADE_NOT_TRADABLE dropped)
    ├── sanitize_text()
    ├── LLM Ensemble (2 × Ollama cloud, coppia da config:sentiment_llm_models — oggi GLM-5.2 + GPT-OSS 20B, asyncio.gather)
    │   ├── divergence check (std ≥ 0.40 → FinBERT via run_in_executor; raw outputs → llm_responses eligible=false)
    │   └── budget check (daily cap → FinBERT via run_in_executor)
    ├── score = polarity × confidence
    ├── SET signal:{sym}:sentiment EX 14400 (Redis, TTL 4h)
    └── INSERT sentiment_signals (PostgreSQL, permanent — includes published_at, news_log_id)
    │
    ▼
ExecutionWorker (every 15 min, active only when execution.engine=legacy_sentiment)
    ├── GET killswitch_active
    ├── GET regime:current (JSON) × GET feedback:regime_scale  (Phase B, legacy path)
    ├── GET feedback:entry_threshold (or default 0.30)      (Phase B)
    ├── For each symbol in watchlist:
    │   ├── GET signal:{sym}:sentiment
    │   ├── freshness check (< 30 min)
    │   ├── stop-loss check → close_trade() → _maybe_postmortem()
    │   ├── BUY gate: score > entry_threshold AND price > EMA20
    │   ├── order_notional = base × (regime_mult × feedback_scale)
    │   └── write_execution_decision() (one row per scored symbol)
    ├── open_trade() on BUY fill
    └── Alpaca SDK market order
    │
    ▼
PortfolioOrchestrator (every 15 min at :07/:22/:37/:52, active only when execution.engine=portfolio)
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

### 3.1 Ticker-resolution layer (design doc §4)

Separates **ticker resolution** from sentiment so a wrong ticker (an order on an
unrelated stock) is treated as the worst-case error. LLMs/extractors *propose*
candidates; a **deterministic resolver** decides the canonical, tradable symbol only
when evidence is strong and unambiguous, else emits a `NO_TRADE_*` reason.

```
candidate ticker(s) + company name
    │
    ▼
gather_evidence (src/connectors/ticker_resolver_providers.py)
    ├── source_ticker_match  (cashtag / broker / MarketAux metadata)   w .30
    ├── alias_match          (internal ticker_lookup)                   w .25
    ├── sec_openfigi_match   (SEC company_tickers ∨ OpenFIGI mapping)   w .20
    ├── llm_agreement        (LLM entity extraction agrees)             w .15
    └── tradable             (broker universe)                         w .10
    │
    ▼
resolve (src/connectors/ticker_resolver.py)  →  RESOLVED | NO_TRADE_*
    gates: confidence ≥ .80, ambiguity_margin ≥ .15, tradable, directness ≠ unclear
```

External providers are **fail-open** (an OpenFIGI/SEC outage lowers confidence, never
fabricates a match) and cached (OpenFIGI per-ticker; SEC company_tickers once). Config:
`OPENFIGI_API_KEY` (optional, raises rate limits), `SEC_USER_AGENT`.

**Status (2026-07-03):** conservative enforcement is **ON**: items whose resolver
verdict is `NO_TRADE_NOT_TRADABLE` are dropped before LLM inference (fail-open on
resolver errors; disable via `RESOLVER_ENFORCE_NOT_TRADABLE=0`). Finer gates
(`NO_TRADE_LOW_CONF`, ambiguity) remain observational until QX-01 calibration — the
2026-07-02 SNDK→AAPL mistag (see `docs/FORENSIC_DAILY_REPORT_2026-07-02.md`) was flagged
`NO_TRADE_LOW_RESOLUTION_CONFIDENCE` in shadow and is the standing evidence for
completing QX-01. Previous status (2026-06-30): decision core + providers built, unit-tested and verified live
(AAPL→RESOLVED, garbage→NO_TRADE, SEC NVIDIA→NVDA). **Shadow mode is wired** (Fase A):
the SentimentWorker resolves each news ticker and persists the verdict to
`news_resolved_entities` (`src/connectors/resolver_shadow.py`, fail-safe, flag
`RESOLVER_SHADOW_ENABLED`) **without gating the live signal** — so resolver precision can
be measured vs `news_labels`. **Enforcement remains gated** on QX-01: the confidence
thresholds assume LLM entity extraction (company_name + directness, design point 1) feeds
the resolver, and are calibrated on shadow data first (design doc §10). Already deployed:
the RSS cashtag/ambiguity guard (Increment 1).

### 3.2 Quality & measurement layer (QX-01 / QX-02)

Enforcement of the resolver, confidence calibration, and `risk_flags` gating are all
**gated on a golden label set (QX-01)** — measuring against dirty data would be
garbage-in/garbage-out. The measurement rails are built and offline/read-only (never in
the hot path):

| Piece | Where | Role |
|-------|-------|------|
| `news_labels` (migr. 029) | PostgreSQL | one row per distinct article; `extracted_tickers` (system) vs human `gt_*`; forward returns |
| `news_resolved_entities` (migr. 031) | PostgreSQL | resolver SHADOW verdict per news ticker (decision/confidence/ambiguity/directness/tradable + evidence); compared vs `news_labels` |
| `scripts/sample_news_labels.py` | offline | deterministic stratified sample (seed 42; marketaux/alpaca/gdelt; near-zero oversampled) |
| Labeling UI | `/labeling` + `/api/labeling/*` | **blind** annotation (no extracted tickers shown); ~30-60s/article |
| `scripts/compute_label_forward_returns.py` | offline | forward return 1h/1d/2d from **Alpaca historical** (point-in-time; not yfinance, R-09) |
| `scripts/validate_ticker_sentiment.py` | offline | extraction precision/recall/FP per source from the label set |
| Quality dashboard | `/quality` + `/api/quality/metrics` | live per-model polarity/confidence, near-zero/fallback rate, extraction precision |

**Source funnel (S2-1, 2026-07-03):** `ingestion_stats_daily` (migr. 033) persists
per-(day, source) counters (fetched/queued/duplicates/discarded); `news_log` gained
`raw_ingested_at` and `content_hash`. FIX-06 (migr. 047) persists every explicit
ingestion/sentiment discard in `news_queue_drops`, extending the stale-only ledger from
#149 with `discarded_reason` and `discard_stage`. The original
`news_log.discarded_reason` column remains unused intentionally: `news_log` is unique on
`(url, ticker)` and represents processed articles, so inserting duplicate discard events
there would either violate that contract or mark a successfully processed row as discarded.
`GET /api/quality/sources` aggregates funnel + per-source latency
(`generated_at − published_at`) + per-source trade P&L; the Quality page renders it with
removal-threshold verdicts (roadmap §7.4). Legacy signals without `news_log_id` report
as source `unknown` (backfill script matched 0 rows unambiguously — genuine 6-9 day gap).

`extraction_method` on `news_log` (QT-03: `source_metadata` / `cashtag` / `org_lookup` /
`regex`) lets precision be measured per extraction path and confirms QT-01 removed the
watchlist fallback. First pre-fix baseline (17 labels): extraction precision 0.24,
macro-FP 2.0. Next: complete annotation → forward returns → sentiment IC → calibrate →
enforce with **measured** gates.

---

## 4. Redis Key Schema

| Key | Type | TTL | Purpose |
|-----|------|-----|---------|
| `signal:{SYM}:sentiment` | JSON string | 4h | Latest signal per symbol |
| `news:queue` | List | — | Inbound article queue |
| `news:dedup:{HASH}` | String | 4h | Article id deduplication |
| `dedup:content:{HASH}:{SYM}` | String | 4h | Cross-source content dedup (EN-03) |
| `killswitch_active` | String (`0`/`1`) | None | Emergency halt flag |
| `system:mode` | String | None | Operating mode |
| `config:sentiment_llm_models` | String | None | Active ensemble pair selection (es. `glm52,gptoss`) |
| `regime:current` | JSON | 26h | Regime label + multiplier + macro snapshot |
| `qc:sizing_multiplier` | String (float) | 24h | Position-sizing multiplier derived from regime |
| `ensemble:weights:current` | JSON | None | Current model weights |
| `ensemble:weights:suggestion` | JSON | 7d | Pending weight suggestion |
| `budget_exhausted` | String flag | daily | LLM budget stop flag (spend ledger lives in PG `llm_budget`) |
| `portfolio:value` | String (float) | 24h | Equity cache scritta dal portfolio cycle (consumata dal loss-feedback relativo) |
| `strategy:zero_weights_cycles:{SID}` | Int counter | 7d | Watchdog: cicli consecutivi a zero pesi per strategia |
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
    forward_return FLOAT,          -- populated by ForwardReturnWorker (Alpaca daily bars)
    generated_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ,      -- event-time of the news (migr. 032, FIX-03); NULL = legacy
    news_log_id BIGINT,            -- trace link to news_log (QS-09)
    UNIQUE (symbol, generated_at)
);

-- S2-1 (migr. 033): per-source ingestion funnel, upsert-incremented by each worker run
CREATE TABLE ingestion_stats_daily (
    day                  DATE        NOT NULL,
    source               VARCHAR(50) NOT NULL,
    fetched              INTEGER     NOT NULL DEFAULT 0,
    queued               INTEGER     NOT NULL DEFAULT 0,
    duplicates           INTEGER     NOT NULL DEFAULT 0,
    discarded_no_ticker  INTEGER     NOT NULL DEFAULT 0,
    discarded_stale      INTEGER     NOT NULL DEFAULT 0,
    parse_fail           INTEGER     NOT NULL DEFAULT 0,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (day, source)
);
-- news_log also gained (migr. 033): raw_ingested_at, content_hash, discarded_reason
-- (the last field is legacy-unused; discard events live in news_queue_drops).

-- FIX-06 (migr. 047): event-level reasons at ingestion and sentiment gates.
-- The table name is retained because migration 044 created it for stale queue drops.
-- Reasons: no_ticker, stale, duplicate_id, duplicate_content, not_tradable,
--          parse_fail, near_neutral.
-- Stages: ingestion, sentiment.
CREATE TABLE news_queue_drops (
    id                 BIGSERIAL PRIMARY KEY,
    dropped_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    item_id            TEXT NOT NULL,
    article_id         TEXT NOT NULL,
    symbol             TEXT,
    source             TEXT,
    published_at       TIMESTAMPTZ,
    age_hours          DOUBLE PRECISION,
    title              TEXT,
    url                TEXT,
    raw_ingested_at    TIMESTAMPTZ,
    content_hash       VARCHAR(64),
    discarded_reason   VARCHAR(30) NOT NULL,
    discard_stage      VARCHAR(20) NOT NULL
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
| `run-alpaca-ingestion` | */15 14-21 Mon-Fri | Alpaca/Benzinga → news queue |
| `sentiment-worker` | */15 14-21 Mon-Fri | news queue → LLM → Redis/PG |
| `run-execution` | */15 14-21 Mon-Fri | signals → Alpaca orders (active only when `execution.engine=legacy_sentiment`) |
| `portfolio-cycle` | 7,22,37,52 14-21 Mon-Fri | **Active order path** — weight-then-order multi-strategy (when `execution.engine=portfolio`) |
| `regime-detector` | 7:00 Mon-Fri | FRED/yfinance → LLM → Redis |
| `regime-detector-premarket` | 13:30 Mon-Fri | Safety-net rerun 30 min before NYSE open (P0-09) |
| `reconcile-fills-intraday` | 12,27,42,57 14-21 Mon-Fri | Alpaca fill prices → trades table |
| `reconcile-fills-evening` | 21:30 Mon-Fri | EOD reconcile pass (B20 fixed 2026-07-03) |
| `forward-return-worker` | 22:00 daily | Populate forward returns from **Alpaca daily bars** |
| `risk-monitor` | 22:30 daily | HHI + correlation + drawdown |
| `performance-daily` | 3:00 daily | IC + drift + Telegram digest |
| `drift-detection` | 4:30 Sunday | PSI + CUSUM over weekly window |
| `check-suggestion-expiry` | 5:00 daily | Expire old weight suggestions |
| `performance-weekly` | 4:00 Monday | LOO ICIR → weight suggestion |
| `run-retention-sweep` | 3:30 daily | Nightly old data cleanup |
| `decay-monitor` | 21:00 daily (temporary during paper validation; monthly afterwards) | Actual vs backtest baseline |
| `poll-telegram-updates` | every 5 seconds | Weight approve/reject keyboard |
| `loss-feedback-check` | */30 14-21 Mon-Fri | Phase B: detect loss patterns → raise feedback threshold; write legacy/audit scale state |
| `counterfactual-worker` | 22:45 daily | Phase C: compute 1h counterfactual returns for SKIP_THRESHOLD/SKIP_EMA/SKIP_CAP rows |
| `mobile-monitor-snapshot` | every minute | Build and atomically publish the coherent Android monitoring read model |

> Removed from the beat (tasks kept, env-gated): `run-marketaux-ingestion` + `run-rss-ingestion` (FIX-01/02, 2026-07-03 — net-negative sources); `sec-edgar-ingestion` (2026-07-02, CIK→ticker bug); `finnhub-ingestion` (2026-07-01, flood).

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
| ~~Vol targeting not active~~ | **RESOLVED**: `strategy_returns` is passed to `run_cycle()` (`portfolio_scheduler.py` ~1136-1145); vol scaling executes before the ConstraintEnforcer (P2-05-C) | Done |
| Strategies API placeholder | `GET /api/strategies` equity curves use `random.gauss()`; gate `passed` values are not from actual metrics | Phase D |
| Analytics tab empty on fresh deploy | All analytics charts show "No data yet" until closed trades accumulate in the `trades` table | Operational |
| Auto-Improve counterfactual empty | Phase C data requires at least one nightly run of `counterfactual-worker` after SKIP decisions are recorded | Operational |
| S4 no dedicated gate report | `reports/s4_backtest/` does not exist; S4 allocation capped at 10% until this is produced | Research |
| S2 proxy vs real options | Current S2 is an equity proxy (overnight gap); actual cash-secured short put needs options chain data + IBKR adapter | Phase D |
| ConstraintEnforcer loses sleeve provenance | Final merged orders have `strategy_id="merged"`; per-sleeve exposure constraints cannot be enforced | Future |
| Feedback loop blind to S1 | Partially resolved: portfolio-cycle BUY trades are written immediately after `submit_order()` (B28 fix, 2026-07-02); SELL/stop-loss still batch-written | Monitor |
| ~~Risk monitor uses wrong NAV and placeholder exposure~~ | **RESOLVED** (2026-07-04): `_fetch_account_state()` reads real Alpaca equity as NAV and gross position value / equity as exposure; broker outage degrades to (0, 0) with a warning instead of a false alert (was: NAV from cumulative P&L, `total_exposure` hardcoded `1.0`, false "exposure 100% > 50%" alert daily — forensic report 2026-07-02) | Done |
| Ensemble barely load-bearing | 79.5% of 2026-07-02 signals fell back to FinBERT via divergence (not timeouts/budget) — the 2-model cloud ensemble is discarded 4 times out of 5. **Update 2026-07-11:** raising the threshold 0.30→0.40 had NO effect (fallback 75-80%): the kimi⇄glm disagreement is directional/bimodal, no threshold separates the modes. Pair swapped to glm-5.2+gpt-oss (2026-07-11); divergent raw outputs now persisted for audit; 3-model median ensemble spec'd in `docs/superpowers/plans/2026-07-11-three-model-ensemble-handoff.md` | Monitor fallback rate post-swap; decide 3-model go/no-go |

### P2-05 Resolved Safety Items (IMPLEMENTED — commit `55cbf56`, 2026-06-21)

All three P2-05 safety requirements are implemented and test-covered. Kimi P2 Acceptance Audit verdict: **`P2_ACCEPTED_WITH_RUNTIME_MONITORING`**. Controlled paper trading IS running on the live Alpaca paper stack (since 2026-07-14: `fixes-2026-07-14` merged `ff3de56` + deployed, migration 037 applied; 2026-07-15 pool-leak fix `06671f7` + stop flip `1f450c6` deployed). `GLOBAL_LIVE_PROMOTION_ENABLED` remains `False` — this is paper, not live money. Live go-live still requires the 90-day supervised_paper clock + explicit PO sign-off.

| Item | Fix | File |
|------|-----|------|
| P2-05-A: Idempotency fail-closed on Redis down | `_get_fired_signal_ids()` returns `None` on any Redis exception; `_apply_idempotency_filter()` skips all S4 BUYs when idempotency cannot be verified | `src/workers/portfolio_scheduler.py:302-335` |
| P2-05-B: Net exposure cap wired from config | `_load_risk_config()` reads `max_portfolio_exposure` and `max_single_asset_pct` from `config/trading.yaml`; passed to `ConstraintEnforcer` at each cycle | `src/workers/portfolio_scheduler.py:338-352` |
| P2-05-C: VolTargeter runs before enforcer | `PortfolioVolTargeter.scale_orders()` called before `ConstraintEnforcer.enforce()` — enforcer is the last constraint pass and cannot be re-violated by vol scaling | `src/portfolio/orchestrator.py:218-229` |

**Runtime monitoring watchlist (R-04 through R-12 remain open):** see `docs/RESIDUAL_RISK_REGISTER.md` for full tracking. Key open items: soft CI gates (mypy/pip-audit/gitleaks), S1 backtest report stale (needs PIT regeneration before promotion discussion), S4 no confirmed IC > placebo. (S7 removed 2026-07-15.)

Full P2 milestone history archived in `docs/archive/2026-06-p2-milestone/` (P2_STATUS + P2_ACCEPTANCE_AUDIT + preflight runbook).
