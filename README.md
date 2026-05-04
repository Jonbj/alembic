# LLM Trading System — Alpha Miner Architecture

Sistema di trading algoritmico basato su LLM che segue il paradigma **"Alpha Miner"**: i modelli LLM operano come motore **offline** di generazione segnali, **mai nel loop critico di esecuzione**.

## Panoramica Architetturale

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    OFFLINE SENTIMENT PIPELINE                           │
│                                                                         │
│  [News/GDELT/RSS] → [Celery SentimentWorker] → [Redis TTL 4h]          │
│                                          │                              │
│                                          ↓                              │
│                                   [PostgreSQL Audit]                    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ↓ (lettura a ogni tick)
┌─────────────────────────────────────────────────────────────────────────┐
│                    EXECUTION ENGINE (QuantConnect Lean)                 │
│                                                                         │
│  Legge segnali pre-calcolati da Redis → Calcola position sizing         │
│  → Esegue ordini su broker (IBKR, Binance, ecc.)                       │
└─────────────────────────────────────────────────────────────────────────┘
```

### Principi Chiave

| Principio | Descrizione |
|-----------|-------------|
| **LLM Offline** | Nessun LLM viene chiamato sincronamente dentro `OnData()` o loop di trading |
| **Signal Caching** | Segnali cached in Redis con TTL 4 ore |
| **Audit Trail** | Tutti i segnali scritti su PostgreSQL per backtest e IC calculation |
| **Graceful Degradation** | Redis OOM gestito, fallback a FinBERT, circuit breaker |

---

## Tech Stack

| Componente | Tecnologia | Scopo |
|------------|------------|-------|
| **LLM Ensemble** | Opus, Qwen3.5, DeepSeek-V4 | Sentiment analysis con DK-CoT |
| **Fallback Model** | FinBERT | Fallback quando ensemble diverge o budget exhausted |
| **Message Queue** | Celery + Redis | Background task processing |
| **Cache** | Redis | Signal caching (TTL 4h), kill-switch, counters |
| **Database** | PostgreSQL | Audit trail, performance metrics |
| **API** | FastAPI | Endpoints per segnali, admin, performance |
| **Execution** | QuantConnect Lean | Backtesting e live trading |

---

## Struttura del Progetto

```
trading/
├── src/
│   ├── config.py              # Configurazione centralizzata (Pydantic)
│   ├── models/
│   │   ├── signals.py         # SentimentResult, LLMSentimentOutput
│   │   ├── news.py            # NewsItem, LLMBudgetTracker
│   │   └── performance.py     # PerformanceReport, PostMortem
│   ├── llm/
│   │   ├── client.py          # LLMClient ABC + Opus/Qwen/Deepseek
│   │   ├── ensemble.py        # EnsembleAggregator, run_ensemble_query
│   │   ├── finbert.py         # FinBERT fallback + entropic mapping
│   │   └── budget.py          # LLMBudgetTracker (daily budget enforcement)
│   ├── connectors/
│   │   ├── base.py            # NewsConnector ABC
│   │   ├── deduplicator.py    # Redis hash-based dedup
│   │   ├── rss.py             # RSS feed connector
│   │   └── gdelt.py           # GDELT news connector
│   ├── store/
│   │   ├── redis_store.py     # RedisStore (signals, kill-switch, counters)
│   │   └── pg_store.py        # PostgreSQLStore (audit, IC data)
│   ├── performance/
│   │   ├── ic.py              # Composite IC B4 + Newey-West HAC
│   │   ├── weights.py         # LOO ICIR + smoothing
│   │   ├── drift.py           # PSI + CUSUM + circuit breakers
│   │   ├── postmortem.py      # Trigger logic + diagnosi
│   │   └── threshold.py       # Bucket IC + threshold suggester
│   ├── workers/
│   │   ├── celery_app.py      # Celery configuration + beat schedule
│   │   ├── sentiment.py       # SentimentWorker task
│   │   └── performance.py     # PerformanceWorker task
│   ├── api/
│   │   ├── main.py            # FastAPI application
│   │   ├── auth.py            # X-API-Key dependency
│   │   └── routes/
│   │       ├── signals.py     # GET /api/signals/{symbol}
│   │       ├── admin.py       # POST /api/admin/killswitch, /mode
│   │       └── performance.py # GET /api/performance/latest
│   ├── notifications/
│   │   └── telegram.py        # TelegramNotifier (alerts, reports)
│   └── text/
│       └── sanitizer.py       # sanitize_text() (BiDi, emoji, NFKC)
├── quantconnect/
│   ├── signal_data.py         # LLMSignalData (PythonData feed)
│   └── intraday_strategy.py   # Intraday 1h strategy
├── tests/
│   ├── llm/                   # LLM client, ensemble, finbert tests
│   ├── performance/           # IC, weights, drift, postmortem tests
│   ├── workers/               # SentimentWorker, PerformanceWorker tests
│   ├── api/                   # FastAPI route tests
│   ├── connectors/            # RSS, GDELT, deduplicator tests
│   └── test_*.py              # Security fixes, budget, stores tests
├── migrations/
│   └── 001_initial.sql        # Database schema
├── config/
│   └── workers.yaml           # Soglie operative (ic_window, psi, ecc.)
├── docs/
│   ├── superpowers/
│   │   ├── specs/             # Specifiche tecniche dettagliate
│   │   └── plans/             # Piani di implementazione Fase 1, 1b, 2
│   ├── ARCHITECTURE.md        # Documentazione architetturale
│   └── API.md                 # API reference completa
└── pyproject.toml             # Project metadata + dependencies
```

---

## Setup e Installazione

### Prerequisiti

- Python 3.11+
- Redis 7+
- PostgreSQL 15+
- Celery 5+

### Installazione

```bash
# Clona il repository
git clone https://github.com/your-org/trading.git
cd trading

# Installa dipendenze
pip install -e ".[dev]"

# Copia ambiente
cp .env.example .env

# Modifica .env con le tue credenziali
# ADMIN_API_KEY, DATABASE_URL, REDIS_URL, TELEGRAM_BOT_TOKEN
```

### Avvio Servizi (Development)

```bash
# Avvia Redis e PostgreSQL
docker-compose up -d redis postgres

# Avvia Celery worker
celery -A src.workers.celery_app worker --loglevel=info

# Avvia Celery beat (scheduler)
celery -A src.workers.celery_app beat --loglevel=info

# Avvia FastAPI
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

---

## Configurazione

### Variabili d'Ambiente

| Variabile | Obbligatoria | Default | Descrizione |
|-----------|--------------|---------|-------------|
| `ADMIN_API_KEY` | ✅ | — | API key per endpoint admin (min 32 char) |
| `DATABASE_URL` | ✅ | — | PostgreSQL connection string |
| `REDIS_URL` | ✅ | `redis://localhost:6379/0` | Redis connection string |
| `TELEGRAM_BOT_TOKEN` | ❌ | — | Token bot Telegram per alert |
| `TELEGRAM_CHAT_ID` | ❌ | — | Chat ID canale Telegram |
| `LLM_DAILY_BUDGET_USD` | ❌ | `50.0` | Budget giornaliero LLM |
| `CLAUDE_CLI_PATH` | ❌ | `claude` | Path per Claude CLI |

### Soglie Operative (`config/workers.yaml`)

```yaml
# Ensemble thresholds
ensemble_min_confidence: 0.4      # Minima confidence per modello
ensemble_divergence_std: 0.30     # Std max per consenso

# Fallback settings
max_consecutive_fallbacks: 3      # Fallback → alert + QC sizing 50%

# Performance tracking
ic_window_days: 30                # Window per IC calculation
psi_yellow_threshold: 0.10        # Moderate drift
psi_red_threshold: 0.25           # Severe drift

# Weight update guardrails
weight_floor: 0.10                # Minima weight per modello
weight_cap: 0.70                  # Massima weight per modello
weight_max_delta: 0.10            # Max change per update
```

---

## Componenti Principali

### 1. LLM Ensemble

L'ensemble interroga **3 modelli in parallelo** (Opus, Qwen3.5, DeepSeek) e aggrega i risultati con **confidence-weighted average**.

```python
from src.llm.client import OpusClient, Qwen35Client, DeepseekClient
from src.llm.ensemble import EnsembleAggregator, run_ensemble_query
from src.models.news import LLMSentimentOutput

clients = [OpusClient(), Qwen35Client(), DeepseekClient()]
aggregator = EnsembleAggregator(
    min_confidence=0.4,
    divergence_threshold=0.30
)

outputs = await run_ensemble_query(
    prompt="Analyze this news...",
    clients=clients,
    response_schema=LLMSentimentOutput,
    symbol="AAPL"
)

result = aggregator.aggregate(outputs)
# result = None se divergence o no eligible models
```

#### Signal Intensity Formula

```
signal_intensity = 0.60 * confidence + 0.40 * sentiment_polarity
```

### 2. FinBERT Fallback

Quando l'ensemble **diverge** (std ≥ 0.30) o **nessun modello** supera la confidence threshold, il sistema fallback a FinBERT.

```python
from src.llm.finbert import FinBERTClient

finbert = FinBERTClient()
result = finbert.analyze(text="Fed raises rates...", symbol="SPY")

# Entropic confidence mapping
# confidence = 1 - H(p)/H_max (normalized entropy)
```

### 3. Budget Tracker

Il budget tracker enforce il **budget giornaliero LLM** e blocca le chiamate quando exhausted.

```python
from src.llm.budget import LLMBudgetTracker, LLMBudgetExhaustedError

tracker = LLMBudgetTracker(conn)

try:
    await tracker.check_budget()  # Raise LLMBudgetExhaustedError se exhausted
    await tracker.record_spending(
        model_id="opus",
        input_tokens=1500,
        output_tokens=500
    )
except LLMBudgetExhaustedError:
    # Fallback a FinBERT (gratis)
    pass
```

### 4. RedisStore

Redis memorizza:
- **Segnali** (TTL 4 ore)
- **Kill-switch state**
- **Fallback counter** (circuit breaker)
- **Budget exhausted flag**
- **Ensemble weights**

```python
from src.store.redis_store import RedisStore

store = RedisStore()

# Write signal
store.write_sentiment(result)

# Read signal
signal = store.read_sentiment("AAPL")

# Kill-switch
store.activate_killswitch(reason="VIX spike > 40")
if store.is_killswitch_active():
    halt_trading()

# Fallback counter
count = store.increment_fallback_counter()
if count >= 3:
    reduce_position_sizing(0.5)  # 50% reduction
```

### 5. PostgreSQLStore

PostgreSQL memorizza:
- **Audit trail** di tutti i segnali
- **Forward returns** per IC calculation
- **Spending records** per budget tracking

```python
from src.store.pg_store import PostgreSQLStore

pg = PostgreSQLStore()

# Write signal
pg.write_signal(result)

# Fetch for IC calculation
rows = pg.fetch_signals_for_ic(symbol="AAPL", days=30)
# [(score, forward_return, generated_at, model_id, fallback_used), ...]
```

### 6. Performance Worker

Il PerformanceWorker calcola giornalmente:
- **Composite IC B4** (0.5×Spearman + 0.3×hit_rate + 0.2×(1−Brier))
- **ICIR** con Newey-West HAC correction
- **PSI** per drift detection
- **CUSUM** per change point detection

```python
from src.performance.ic import compute_composite_ic, compute_icir
from src.performance.drift import compute_psi, detect_drift

# Composite IC
ic_result = compute_composite_ic(scores, returns, confidences)
# ic_result.composite_ic, ic_result.spearman, ic_result.hit_rate, ic_result.brier

# ICIR with HAC
icir_result = compute_icir(scores, returns, confidences)
# icir_result.icir, icir_result.newey_west_std

# PSI
psi = compute_psi(baseline_90gg, current_7gg)
# psi > 0.10 = yellow alert, psi > 0.25 = red alert
```

### 7. Circuit Breakers

Il sistema ha **hard** e **soft** circuit breakers:

```python
HARD_BREAKERS = {
    "vix_spike":       lambda ctx: ctx.vix > 40 or ctx.vix_1d_change > 0.30,
    "system_drawdown": lambda ctx: ctx.portfolio_drawdown > 0.05,
    "ic_negative_run": lambda ctx: ctx.consecutive_negative_ic_days >= 5,
}

SOFT_WARNINGS = {
    "earnings_concentration": lambda ctx: ctx.portfolio_earnings_pct > 0.50,
    "cross_asset_corr":       lambda ctx: ctx.cross_asset_correlation > 0.90,
}
```

---

## API Reference

### Signal Endpoints

| Endpoint | Method | Auth | Descrizione |
|----------|--------|------|-------------|
| `/api/signals/{symbol}` | GET | No | Ultimo segnale per simbolo |
| `/api/signals/history` | GET | No | Storia segnali (paginata) |

### Admin Endpoints

| Endpoint | Method | Auth | Descrizione |
|----------|--------|------|-------------|
| `/api/admin/killswitch` | POST | ✅ | Attiva kill-switch |
| `/api/admin/mode` | POST | ✅ | Set operating mode |

### Performance Endpoints

| Endpoint | Method | Auth | Descrizione |
|----------|--------|------|-------------|
| `/api/performance/latest` | GET | No | Ultimo performance report |
| `/api/weights/current` | GET | No | Pesi ensemble correnti |
| `/api/weights/approve` | POST | ✅ | Approva nuovi pesi |

---

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific category
python -m pytest tests/llm/ -v
python -m pytest tests/performance/ -v
python -m pytest tests/test_security_fixes.py -v

# Run with coverage
python -m pytest tests/ --cov=src --cov-report=html
```

### Test Coverage Attuale

| Categoria | Test Count | Status |
|-----------|------------|--------|
| LLM (client, ensemble, finbert) | 17 | ✅ |
| Performance (IC, weights, drift) | 89 | ✅ |
| Workers (sentiment, performance) | 24 | ✅ |
| API (routes, auth) | 8 | ✅ |
| Connectors (RSS, GDELT, dedup) | 14 | ✅ |
| Security fixes | 15 | ✅ |
| Stores (Redis, Postgres) | 27 | ✅ |
| **TOTALE** | **281** | **✅** |

---

## Security

### Fix Implementati (P0)

| Vulnerabilità | Fix |
|---------------|-----|
| Command injection (subprocess) | `ALLOWED_MODEL_IDS` frozenset |
| CLI path non validato | `shutil.which()` + existence check |
| SQL injection (INTERVAL) | Parametrized query con `|| ' days'::interval` |
| BiDi override characters | Rimozione in `sanitize_text()` |
| Emoji nel JSON | Regex removal in `sanitize_text()` |
| Redis OOM | Try/except in tutte le write operation |
| ZeroDivisionError | Check `if total_conf == 0` |
| Connection leak | Rollback su eccezione in `pg_store` |

---

## Monitoraggio e Alerting

### Telegram Alerts

Il sistema invia alert per:
- **Kill-switch activation** (VIX spike, drawdown)
- **Budget exhausted** (LLM daily limit)
- **Fallback threshold** (3+ consecutivi → QC sizing 50%)
- **Drift detection** (PSI > 0.10 yellow, > 0.25 red)
- **Performance report** (giornaliero)

### Redis Keys

| Key | Tipo | TTL | Descrizione |
|-----|------|-----|-------------|
| `signal:{symbol}:sentiment` | String | 4h | Ultimo segnale |
| `killswitch_active` | String | — | Flag attivo/inattivo |
| `fallback:consecutive:count` | Counter | 24h | Fallback counter |
| `qc:sizing_multiplier` | String | 24h | Position sizing (1.0 o 0.5) |
| `budget:exhausted` | String | ~24h | Flag budget exhausted |
| `ensemble:weights:current` | String | 30gg | Pesi correnti |
| `performance:latest_report` | String | 7gg | Ultimo report |
| `ensemble:divergence:log` | List | 24h | Log divergenze |

---

## Roadmap

### Fase 1 (Completata) ✅
- [x] LLM ensemble + FinBERT fallback
- [x] Budget tracker
- [x] Redis/PostgreSQL stores
- [x] SentimentWorker + PerformanceWorker
- [x] Composite IC + Newey-West
- [x] PSI + CUSUM drift detection
- [x] FastAPI endpoints
- [x] QuantConnect integration
- [x] 281 test passing

### Fase 1b (Scalability)
- [ ] Redis connection pooling
- [ ] Celery worker autoscaling
- [ ] Structured logging (JSON)
- [ ] Health check endpoints
- [ ] Backup script PostgreSQL

### Fase 2 (Auto-Update Weights)
- [ ] LOO ICIR weight computation
- [ ] Weight smoothing (0.75 old + 0.25 new)
- [ ] Guardrails (floor 10%, cap 70%, max delta 10%)
- [ ] Manual approval workflow
- [ ] Audit trail weight changes

---

## License

MIT License — vedere file `LICENSE` per dettagli.
