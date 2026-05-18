<div align="center">
  <img src="img/alembic.png" alt="Alembic" width="180"/>

  # Alembic — Open Source Finance

  **LLM-Based Algorithmic Trading System**

  *Alpha Miner paradigm: LLMs run offline, execution reads pre-computed signals from Redis*

  ![Tests](https://img.shields.io/badge/tests-594%20passing-brightgreen)
  ![Python](https://img.shields.io/badge/python-3.11%2B-blue)
  ![License](https://img.shields.io/badge/license-MIT-lightgrey)
</div>

---

## Architecture Overview

Alembic follows the **Alpha Miner paradigm**: all LLM inference happens offline, asynchronously, well before any trade decision. The execution engine never calls an LLM — it reads pre-computed signals from Redis. This decoupling means latency, LLM API outages, and budget exhaustion never block order placement.

The system runs as five loosely-coupled phases, each driven by a separate Celery worker:

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  PHASE 1 — NEWS INGESTION  (every 15 min, Mon–Fri market hours)             ║
║                                                                              ║
║  GDELT GKG v2 ──┐                                                            ║
║  MarketAux ─────┼──► NewsIngestionWorker ──► Redis news queue               ║
║  Alpaca News ───┘         (dedup via SHA-256 hash, TTL 4 h)                 ║
╚══════════════════════════════════════════════════════════════════════════════╝
                                    │ (consumed as fast as produced)
                                    ▼
╔══════════════════════════════════════════════════════════════════════════════╗
║  PHASE 2 — SENTIMENT PIPELINE  (every 15 min, Mon–Fri market hours)         ║
║                                                                              ║
║  Redis news queue ──► SentimentWorker                                        ║
║                           │                                                  ║
║                           ├──► LLM Ensemble (Opus + Qwen3.5 + DeepSeek)     ║
║                           │       DK-CoT prompting, budget-gated             ║
║                           │       divergence check (std > 0.30)              ║
║                           │                                                  ║
║                           └──► FinBERT fallback (divergence / budget OOM)   ║
║                                                                              ║
║                      polarity score [-1, +1] + confidence                   ║
║                           │                   │                              ║
║                           ▼                   ▼                              ║
║                    Redis (TTL 4h)       PostgreSQL audit                     ║
║                  sentiment:signal:{sym}  sentiment_signals table             ║
╚══════════════════════════════════════════════════════════════════════════════╝
                                                                               
╔══════════════════════════════════════════════════════════════════════════════╗
║  PHASE 3 — REGIME DETECTION  (daily, Mon–Fri 07:00 UTC)                     ║
║                                                                              ║
║  FRED API ─────────────┐                                                     ║
║  (VIX, T10Y2Y spread)  ├──► MacroSnapshot ──► LLM pair (Opus + DeepSeek)   ║
║  yfinance (SPY 20d) ───┘       consensus vote → RegimeLabel                 ║
║                                                                              ║
║  RegimeLabel ──► regime_multiplier written to Redis                          ║
║    bull=1.0×  │  sideways=0.7×  │  bear=0.4×  │  high_vol=0.2×             ║
╚══════════════════════════════════════════════════════════════════════════════╝
                   │                    │
                   │ multiplier         │ signals
                   ▼                    ▼
╔══════════════════════════════════════════════════════════════════════════════╗
║  PHASE 4 — EXECUTION ENGINE  (every 15 min, Mon–Fri 14:00–21:00 UTC)       ║
║                                                                              ║
║  ExecutionWorker per tick:                                                   ║
║    1. Kill-switch check   → abort if active                                  ║
║    2. EMA20 cache refresh → SPY + watchlist prices (yfinance)                ║
║    3. Drawdown cap check  → halt + alert if daily loss ≥ 10%                ║
║    4. For each symbol:                                                        ║
║         a. Read sentiment signal from Redis (freshness ≤ 30 min)            ║
║         b. Stop-loss check (if open position and price ≤ stop)               ║
║         c. BUY gate: score > 0.3 AND price > EMA20                          ║
║         d. Position size = base × regime_multiplier                          ║
║         e. Place market order via Alpaca SDK                                 ║
╚══════════════════════════════════════════════════════════════════════════════╝
                                    │
                                    ▼ (daily + weekly async)
╔══════════════════════════════════════════════════════════════════════════════╗
║  PHASE 5 — PERFORMANCE & WEIGHT OPTIMISATION LOOP                          ║
║                                                                              ║
║  Daily (03:00 UTC):  PerformanceWorker                                       ║
║    • Composite IC B4 + Newey-West HAC → IC report                           ║
║    • PSI + CUSUM drift detection → circuit breaker if regime shift          ║
║    • Post-mortem diagnostics → Telegram daily digest                        ║
║                                                                              ║
║  Weekly (Mon 04:00): LOO ICIR per model ──► weight suggestion               ║
║    • Guardrails: VIX < 30, no active freeze, weights in [0.10, 0.70]        ║
║    • Auto-apply if all guardrails pass                                       ║
║    • Otherwise → Telegram inline keyboard: [✅ Approve] [❌ Reject]         ║
║      Human approves → weights written to Redis → applied next tick          ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

### Core Principles

| Principle | Description |
|-----------|-------------|
| **LLM Offline** | No LLM is ever called synchronously inside the trading loop |
| **Signal Caching** | Signals cached in Redis with 4-hour TTL; stale signals are skipped, not used |
| **Audit Trail** | Every signal written to PostgreSQL — the foundation for IC/ICIR calculation and backtesting |
| **Graceful Degradation** | Redis OOM handled silently, FinBERT fallback on ensemble divergence, circuit breakers on drift |
| **Regime-Aware Sizing** | `regime_multiplier` (1.0×, 0.7×, 0.4×, 0.2×) applied to position size based on macro conditions |
| **Human-in-the-Loop** | Weight updates require Telegram approval when guardrails (VIX, drawdown, freeze) trigger |
| **Drawdown Cap** | Daily loss ≥ 10% auto-activates kill-switch + sends Telegram CRITICAL alert |
| **Budget Enforcement** | Daily LLM spend is tracked per-model; ensemble falls back to FinBERT when budget is exhausted |

---

## Tech Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| **LLM Ensemble** | Opus, Qwen3.5, DeepSeek-V4 | Sentiment analysis with DK-CoT |
| **Fallback Model** | FinBERT | Fallback when ensemble diverges or budget exhausted |
| **Task Queue** | Celery + Redis | Background task processing |
| **Cache** | Redis | Signal caching, kill-switch, counters, regime state |
| **Database** | PostgreSQL | Audit trail, performance metrics, weight change log |
| **API** | FastAPI | Signals, admin, performance, and weights endpoints |
| **Execution** | Alpaca SDK (paper + live) | Order placement, stop-loss, drawdown cap |
| **Notifications** | Telegram Bot | Alerts, daily reports, weight approval via inline keyboard |
| **Macro Data** | FRED API + yfinance | VIX, T10Y2Y yield curve, SPY 20d momentum |

---

## Project Structure

```
Alembic/
├── src/
│   ├── config.py              # Centralised config (Pydantic) — env vars, guardrails
│   ├── models/
│   │   ├── signals.py         # SentimentResult, LLMSentimentOutput
│   │   ├── news.py            # NewsItem
│   │   ├── performance.py     # PerformanceReport, PostMortem
│   │   └── regime.py          # RegimeState, RegimeOutput, MacroSnapshot, RegimeLabel
│   ├── llm/
│   │   ├── client.py          # LLMClient ABC + OpusClient, Qwen35Client, DeepseekClient
│   │   ├── ensemble.py        # EnsembleAggregator, run_ensemble_query
│   │   ├── finbert.py         # FinBERT fallback + entropic confidence mapping + score_articles()
│   │   └── budget.py          # LLMBudgetTracker (daily budget enforcement)
│   ├── connectors/
│   │   ├── base.py            # NewsConnector ABC
│   │   ├── deduplicator.py    # Redis hash-based deduplication
│   │   ├── gdelt_gkg.py       # GDELT GKG v2 bulk connector
│   │   ├── gdelt.py           # GDELT news connector
│   │   ├── marketaux.py       # MarketAux news connector
│   │   ├── alpaca_news.py     # Alpaca news connector
│   │   ├── macro.py           # FRED API: VIX, yield curve, SPY momentum
│   │   ├── ticker_extractor.py# Company name → ticker (PostgreSQL lookup)
│   │   └── sec_edgar.py       # SEC EDGAR 8-K/10-Q filing connector
│   ├── store/
│   │   ├── redis_store.py     # RedisStore: signals, kill-switch, weights, regime
│   │   └── pg_store.py        # PostgreSQLStore: audit, IC data, weight update log
│   ├── performance/
│   │   ├── ic.py              # Composite IC B4 + Newey-West HAC correction
│   │   ├── weights.py         # LOO ICIR + smoothing + guardrails
│   │   ├── drift.py           # PSI + CUSUM + circuit breakers
│   │   ├── postmortem.py      # Trigger logic + diagnostics
│   │   └── threshold.py       # Bucket IC + threshold suggester
│   ├── workers/
│   │   ├── celery_app.py      # Celery config + beat schedule (8 registered tasks)
│   │   ├── sentiment.py       # SentimentWorker: news → LLM → Redis/PG
│   │   ├── execution.py       # ExecutionWorker: signals → Alpaca orders + drawdown cap
│   │   ├── performance.py     # PerformanceWorker: IC, weights, drift, auto-apply
│   │   ├── regime.py          # RegimeDetector: macro → LLM pair → regime → Redis
│   │   ├── ingestion.py       # NewsIngestionWorker: GDELT/MarketAux/Alpaca → Redis queue
│   │   └── telegram_poller.py # TelegramPoller: /getUpdates → approve/reject weights
│   ├── api/
│   │   ├── main.py            # FastAPI application
│   │   ├── auth.py            # X-API-Key dependency
│   │   ├── deps.py            # Dependency injection (RedisStore, PostgreSQLStore)
│   │   └── routes/
│   │       ├── signals.py     # GET /api/signals/{symbol}, /history
│   │       ├── admin.py       # POST /api/admin/killswitch, /mode
│   │       └── performance.py # GET/POST /api/performance/*, /weights/*
│   ├── notifications/
│   │   ├── base.py            # AlertLevel enum + Notifier Protocol
│   │   └── telegram.py        # TelegramNotifier + format helpers
│   ├── analysis/
│   │   └── backtest.py        # A/B comparison: GDELT+FinBERT vs buy-and-hold
│   └── text/
│       └── sanitizer.py       # sanitize_text(): BiDi, emoji, NFKC normalisation
├── scripts/
│   ├── run_backtest.py        # GKG backtest runner (multi-month, checkpoint every 50 rows)
│   └── gdelt_ab_test.py       # GDELT A/B test CLI
├── tests/                     # 594 tests — mirrors src/ structure
├── migrations/
│   └── 001_initial.sql        # DB schema: sentiment_signals, llm_spending, weight_update_log
├── config/
│   └── workers.yaml           # Operational thresholds (IC window, PSI, ensemble, ecc.)
├── img/
│   └── alembic.png            # Application logo
├── docs/
│   ├── ARCHITECTURE.md        # Full technical architecture documentation
│   └── API.md                 # API reference with examples
└── pyproject.toml             # Project metadata + dependencies
```

---

## Setup

### Prerequisites

- Python 3.11+
- Redis 7+
- PostgreSQL 15+
- Docker (for local Redis + PG)

### Installation

```bash
git clone https://github.com/your-org/Alembic.git
cd Alembic

pip install -e ".[dev]"
cp .env.example .env
# Edit .env with your credentials
```

### Start Services (Development)

```bash
# Redis + PostgreSQL
docker-compose up -d

# Celery worker
celery -A src.workers.celery_app worker --loglevel=info

# Celery beat (scheduler)
celery -A src.workers.celery_app beat --loglevel=info

# FastAPI
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

---

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ADMIN_API_KEY` | ✅ | — | API key for admin endpoints (min 32 chars) |
| `DATABASE_URL` | ✅ | — | PostgreSQL connection string |
| `REDIS_URL` | ✅ | `redis://localhost:6379/0` | Redis connection string |
| `ALPACA_API_KEY` | ✅ | — | Alpaca API key |
| `ALPACA_SECRET_KEY` | ✅ | — | Alpaca secret key |
| `ALPACA_BASE_URL` | ❌ | paper URL | `https://paper-api.alpaca.markets` for paper trading |
| `TELEGRAM_BOT_TOKEN` | ❌ | — | Telegram bot token (from @BotFather) |
| `TELEGRAM_CHAT_ID` | ❌ | — | Channel or group ID for alerts |
| `TELEGRAM_ALLOWED_USER_IDS` | ❌ | — | Comma-separated Telegram user IDs for weight approval |
| `FRED_API_KEY` | ❌ | — | FRED API key for VIX and yield curve |
| `LLM_DAILY_BUDGET_USD` | ❌ | `50.0` | Daily LLM budget in USD |
| `WATCHLIST_SYMBOLS` | ❌ | — | Comma-separated symbols for ExecutionWorker |
| `AUTO_APPLY_ENABLED` | ❌ | `true` | Toggle auto-apply weights |
| `AUTO_APPLY_VIX_THRESHOLD` | ❌ | `30.0` | Block auto-apply if VIX ≥ threshold |

### Operational Thresholds (`config/workers.yaml`)

```yaml
ensemble_min_confidence: 0.4      # Min confidence per model
ensemble_divergence_std: 0.30     # Max std for consensus
max_consecutive_fallbacks: 3      # Fallbacks → alert + sizing 50%
ic_window_days: 30
psi_yellow_threshold: 0.10
psi_red_threshold: 0.25
weight_floor: 0.10
weight_cap: 0.70
```

---

## Celery Beat Schedule

| Task | Frequency | Time (UTC) | Description |
|------|-----------|------------|-------------|
| `execution-worker` | Every 15 min | Mon–Fri 14:00–21:00 | Signals → Alpaca orders + drawdown cap |
| `sentiment-worker` | Every 15 min | Mon–Fri 14:00–21:00 | News → LLM sentiment → Redis/PG |
| `ingestion-gdelt` | Every 15 min | Mon–Fri 14:00–21:00 | GDELT GKG → news queue |
| `ingestion-marketaux` | Every 15 min | Mon–Fri 14:00–21:00 | MarketAux → news queue |
| `ingestion-alpaca` | Every 15 min | Mon–Fri 14:00–21:00 | Alpaca news → news queue |
| `performance-daily` | Daily | 03:00 | IC report + Telegram alert |
| `performance-weekly` | Weekly | Mon 04:00 | LOO ICIR → weight suggestion |
| `regime-detector` | Daily | Mon–Fri 07:00 | Macro → LLM pair → regime → Redis |
| `poll-telegram-updates` | Every 5s | Always | Process approve/reject taps |

---

## API Reference

### Signal Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/signals/{symbol}` | GET | — | Latest signal for symbol |
| `/api/signals/history` | GET | — | Paginated signal history |

### Admin Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/admin/killswitch` | POST | ✅ | Activate kill-switch (halt all trading) |
| `/api/admin/mode` | POST | ✅ | Set operating mode: `paper` / `semi_auto` / `full_auto` |

### Performance & Weights Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/performance/latest` | GET | — | Latest performance report |
| `/api/weights/current` | GET | — | Current ensemble weights |
| `/api/weights/suggestion` | GET | — | Pending weight suggestion (with expiry) |
| `/api/weights/approve` | POST | ✅ | Approve suggested or force custom weights |

---

## Testing

```bash
python -m pytest tests/ -v
python -m pytest tests/workers/ -v
python -m pytest tests/ --cov=src --cov-report=html
```

### Test Coverage

| Category | Tests |
|----------|-------|
| Workers (sentiment, execution, performance, regime, poller) | 82 |
| Performance (IC, weights, drift, postmortem, threshold) | 89 |
| Stores (Redis, Postgres, budget) | 60 |
| LLM (client, ensemble, finbert) | 27 |
| API (routes, auth, weight approval) | 12 |
| Connectors (GDELT, MarketAux, macro, deduplicator) | 20 |
| Notifications (base protocol, telegram formatters) | 25 |
| Analysis (backtest, GDELT A/B) | 16 |
| Security, config, models | 28 |
| QuantConnect | 6 |
| **Total** | **594** |

---

## Roadmap

### Completed ✅
- LLM ensemble + FinBERT fallback with entropic confidence
- Budget tracker (daily limit, per-model costs)
- Redis/PostgreSQL dual persistence
- SentimentWorker + PerformanceWorker (Composite IC B4, Newey-West HAC, PSI, CUSUM)
- RegimeDetector (bull/sideways/bear/high_vol → position multiplier)
- Auto-apply weights with Telegram inline keyboard approval
- NewsIngestionWorker (GDELT GKG v2, MarketAux, Alpaca news, ticker extraction)
- ExecutionWorker (Alpaca paper/live, EMA momentum filter, stop-loss, drawdown cap)
- Infrastructure alerting: Redis unreachable, Alpaca unreachable, drawdown cap (B2)
- `Notifier` Protocol + `AlertLevel` enum for dependency injection
- GDELT GKG backtest pipeline (multi-month, checkpoint, IC/ICIR validation)

### In Progress 🔄
- Phase A: Paper trading validation (3–5 weeks, needs host deployment)
- GKG backtest Nov 2025 → IC/ICIR results pending

### Planned 📋
- Phase B: Drawdown alerting, `semi_auto` Telegram approval per-order, daily report verification, credential rotation
- Phase C: Alpaca live account go-live
- Zeygos Signal Connector (pre-interpreted BUY/SELL signals via Telegram)
- QuantConnect Lean integration for institutional multi-asset backtesting

---

## Security

| Vulnerability | Fix |
|---------------|-----|
| Command injection (subprocess) | `ALLOWED_MODEL_IDS` frozenset allowlist |
| SQL injection (INTERVAL) | Parameterised query with `|| ' days'::interval` |
| BiDi override characters | Stripped in `sanitize_text()` |
| Redis OOM | Try/except on all write operations |
| ZeroDivisionError ensemble | `if total_conf == 0` guard |
| PostgreSQL connection leak | Rollback on exception in `pg_store` |
| Telegram replay attack | Token `SHA256(computed_at)[:8]` per suggestion |
| Telegram unauthorised tap | `TELEGRAM_ALLOWED_USER_IDS` allowlist |

---

## License

MIT License — see `LICENSE` for details.
