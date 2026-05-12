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
│  → Applica moltiplicatore regime → Esegue ordini su broker             │
└─────────────────────────────────────────────────────────────────────────┘
```

### Principi Chiave

| Principio | Descrizione |
|-----------|-------------|
| **LLM Offline** | Nessun LLM viene chiamato sincronamente dentro `OnData()` o loop di trading |
| **Signal Caching** | Segnali cached in Redis con TTL 4 ore |
| **Audit Trail** | Tutti i segnali scritti su PostgreSQL per backtest e IC calculation |
| **Graceful Degradation** | Redis OOM gestito, fallback a FinBERT, circuit breaker |
| **Regime-Aware Sizing** | QuantConnect legge `qc:sizing_multiplier` da Redis (1.0×, 0.7×, 0.4×, 0.2×) |
| **Human-in-the-Loop** | Approvazione pesi via Telegram inline keyboard prima dell'auto-apply |

---

## Tech Stack

| Componente | Tecnologia | Scopo |
|------------|------------|-------|
| **LLM Ensemble** | Opus, Qwen3.5, DeepSeek-V4 | Sentiment analysis con DK-CoT |
| **Fallback Model** | FinBERT | Fallback quando ensemble diverge o budget exhausted |
| **Message Queue** | Celery + Redis | Background task processing |
| **Cache** | Redis | Signal caching (TTL 4h), kill-switch, counters, regime state |
| **Database** | PostgreSQL | Audit trail, performance metrics, weight change log |
| **API** | FastAPI | Endpoints per segnali, admin, performance, pesi |
| **Execution** | QuantConnect Lean | Backtesting e live trading |
| **Notifications** | Telegram Bot | Alert, report giornalieri, approvazione pesi via keyboard |
| **Macro Data** | FRED API + yfinance | VIX, T10Y2Y yield curve, SPY momentum 20d |

---

## Struttura del Progetto

```
trading/
├── src/
│   ├── config.py              # Configurazione centralizzata (Pydantic) — env vars, guardrails
│   ├── models/
│   │   ├── signals.py         # SentimentResult, LLMSentimentOutput
│   │   ├── news.py            # NewsItem, LLMBudgetTracker
│   │   ├── performance.py     # PerformanceReport, PostMortem
│   │   └── regime.py          # RegimeState, RegimeOutput, MacroSnapshot, RegimeLabel
│   ├── llm/
│   │   ├── client.py          # LLMClient ABC + OpusClient, Qwen35Client, DeepseekClient
│   │   ├── ensemble.py        # EnsembleAggregator, run_ensemble_query
│   │   ├── finbert.py         # FinBERT fallback + entropic confidence mapping
│   │   └── budget.py          # LLMBudgetTracker (daily budget enforcement)
│   ├── connectors/
│   │   ├── base.py            # NewsConnector ABC
│   │   ├── deduplicator.py    # Redis hash-based deduplication
│   │   ├── rss.py             # RSS feed connector
│   │   ├── gdelt.py           # GDELT news connector
│   │   ├── macro.py           # FRED API: VIX, yield curve, SPY momentum
│   │   └── sec_edgar.py       # SEC EDGAR 8-K/10-Q filing connector
│   ├── store/
│   │   ├── redis_store.py     # RedisStore: signals, kill-switch, weights, regime, offset
│   │   └── pg_store.py        # PostgreSQLStore: audit, IC data, weight update log
│   ├── performance/
│   │   ├── ic.py              # Composite IC B4 + Newey-West HAC correction
│   │   ├── weights.py         # LOO ICIR + smoothing + guardrails
│   │   ├── drift.py           # PSI + CUSUM + circuit breakers
│   │   ├── postmortem.py      # Trigger logic + diagnosi
│   │   └── threshold.py       # Bucket IC + threshold suggester
│   ├── workers/
│   │   ├── celery_app.py      # Celery configuration + beat schedule (7 task registrations)
│   │   ├── sentiment.py       # SentimentWorker: news → LLM → Redis/PG
│   │   ├── performance.py     # PerformanceWorker: IC, pesi, drift, auto-apply
│   │   ├── regime.py          # RegimeDetector: macro → LLM pair → regime → Redis
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
│   │   └── telegram.py        # TelegramNotifier + format helpers per ogni alert type
│   └── text/
│       └── sanitizer.py       # sanitize_text(): BiDi, emoji, NFKC normalization
├── quantconnect/
│   ├── signal_data.py         # LLMSignalData (PythonData feed)
│   └── intraday_strategy.py   # Intraday 1h strategy
├── tests/
│   ├── llm/                   # LLM client, ensemble, finbert tests
│   ├── performance/           # IC, weights, drift, postmortem tests
│   ├── workers/               # SentimentWorker, PerformanceWorker, RegimeWorker, TelegramPoller
│   ├── api/                   # FastAPI route tests, weight approval tests
│   ├── connectors/            # RSS, GDELT, macro, deduplicator tests
│   ├── models/                # Regime, performance model tests
│   ├── notifications/         # Telegram format functions tests
│   ├── quantconnect/          # QuantConnect signal data tests
│   └── test_*.py              # Security fixes, budget, stores tests
├── migrations/
│   └── 001_initial.sql        # Database schema (sentiment_signals, llm_spending, weight_update_log)
├── config/
│   └── workers.yaml           # Soglie operative (ic_window, psi, ensemble thresholds, ecc.)
├── docs/
│   ├── superpowers/
│   │   ├── specs/             # Specifiche tecniche dettagliate per ogni feature
│   │   └── plans/             # Piani di implementazione Fase 1, 1b, 2
│   ├── ARCHITECTURE.md        # Documentazione architetturale completa
│   └── API.md                 # API reference completa con esempi
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
# ADMIN_API_KEY, DATABASE_URL, REDIS_URL, TELEGRAM_BOT_TOKEN, FRED_API_KEY, ecc.
```

### Avvio Servizi (Development)

```bash
# Avvia Redis e PostgreSQL
docker-compose up -d redis postgres

# Avvia Celery worker (elabora tutti i task)
celery -A src.workers.celery_app worker --loglevel=info

# Avvia Celery beat (scheduler — trig ga i task periodici)
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
| `TELEGRAM_BOT_TOKEN` | ❌ | — | Token bot Telegram (da @BotFather) |
| `TELEGRAM_CHAT_ID` | ❌ | — | Chat ID canale Telegram per alert |
| `TELEGRAM_ALLOWED_USER_IDS` | ❌ | — | ID Telegram autorizzati ad approvare pesi (comma-separated) |
| `FRED_API_KEY` | ❌ | — | API key FRED per VIX e yield curve (cade su CSV pubblico se assente) |
| `LLM_DAILY_BUDGET_USD` | ❌ | `50.0` | Budget giornaliero LLM in USD |
| `CLAUDE_CLI_PATH` | ❌ | `claude` | Path per Claude CLI binary |
| **Auto-apply guardrails** | | | |
| `AUTO_APPLY_ENABLED` | ❌ | `true` | Toggle auto-apply pesi (false = sempre freeze) |
| `AUTO_APPLY_VIX_THRESHOLD` | ❌ | `30.0` | Blocca auto-apply se VIX >= soglia |
| `AUTO_APPLY_IC_VARIANCE_THRESHOLD` | ❌ | `0.15` | Blocca se std(purified_icir) >= soglia |
| `AUTO_APPLY_WEIGHT_DELTA_MAX` | ❌ | `0.15` | Blocca se max(|Δpeso|) >= soglia |
| `AUTO_APPLY_VIX_REDIS_TTL_SECONDS` | ❌ | `3600` | Cache VIX in Redis per N secondi |
| `AUTO_APPLY_VIX_FRED_SERIES` | ❌ | `VIXCLS` | Serie FRED per VIX giornaliero |
| **Regime detection** | | | |
| `REGIME_LLM_MODEL_1` | ❌ | `opus` | Primo LLM per classificazione regime |
| `REGIME_LLM_MODEL_2` | ❌ | `qwen3.5:cloud` | Secondo LLM per classificazione regime |
| `REGIME_MULTIPLIER_BULL` | ❌ | `1.0` | Moltiplicatore QC sizing in regime bull |
| `REGIME_MULTIPLIER_SIDEWAYS` | ❌ | `0.7` | Moltiplicatore QC sizing in regime sideways |
| `REGIME_MULTIPLIER_BEAR` | ❌ | `0.4` | Moltiplicatore QC sizing in regime bear |
| `REGIME_MULTIPLIER_HIGH_VOL` | ❌ | `0.2` | Moltiplicatore QC sizing in regime high_vol |
| `REGIME_REDIS_TTL_SECONDS` | ❌ | `90000` | TTL regime in Redis (25h — sopravvive al gap notturno) |

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

## Celery Beat Schedule

| Task | Frequenza | Orario | Descrizione |
|------|-----------|--------|-------------|
| `sentiment-worker` | Ogni 15 min | Lun-Ven 14:00-21:00 UTC | News → LLM sentiment → Redis/PG |
| `performance-daily` | Giornaliero | 03:00 UTC | IC report + alert Telegram |
| `performance-weekly` | Settimanale | Lunedì 04:00 UTC | LOO ICIR → suggerimento pesi |
| `drift-detection` | Settimanale | Domenica 04:30 UTC | PSI + CUSUM drift detection |
| `check-suggestion-expiry` | Giornaliero | 05:00 UTC | Log pesi scaduti senza approvazione |
| `regime-detector` | Giornaliero | Lun-Ven 07:00 UTC | Macro → LLM pair → regime → Redis |
| `poll-telegram-updates` | Ogni 5 secondi | Sempre attivo | Processa tap approve/reject su keyboard |

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
# result = None se divergence o no eligible models → trigger FinBERT fallback
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
# confidence = 1 - H(p)/H_max (normalized Shannon entropy)
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

### 4. RegimeDetector

Il `detect_regime` task (Celery beat, Lun-Ven 07:00 UTC) classifica il regime macro giornaliero e aggiorna il moltiplicatore di position sizing.

```
Flusso:
  FRED API + yfinance → VIX, T10Y2Y, SPY_20d
  → LLM pair (Opus + Qwen3.5) in parallelo via asyncio.gather
  → Consensus (o regime più conservativo in caso di disaccordo)
  → Redis: regime:current, qc:sizing_multiplier
  → Telegram alert (solo se regime cambia)

Regimi:
  bull      → ×1.0 (full position sizing)
  sideways  → ×0.7
  bear      → ×0.4
  high_vol  → ×0.2 (massima riduzione del rischio)

Guardrails:
  - Dati macro fuori range (VIX ∉ [5,100]) → skip, alert 🚨
  - Entrambi i LLM falliscono → skip, alert 🚨
  - data_quality="partial" → skip, alert ⚠️
  - Disaccordo LLM → regime più conservativo, alert ⚠️ se cambia
```

```python
from src.models.regime import RegimeState
from src.store.redis_store import RedisStore

redis = RedisStore()
state: RegimeState | None = redis.get_regime()
if state:
    print(f"Regime: {state.regime} (×{state.multiplier})")
    print(f"VIX: {state.macro_snapshot.vix:.1f}")
```

### 5. Performance Worker

Il PerformanceWorker (5 task totali) calcola giornalmente/settimanalmente:
- **Composite IC B4** (0.5×Spearman + 0.3×hit_rate + 0.2×(1−Brier))
- **ICIR** con Newey-West HAC correction
- **PSI** e **CUSUM** per drift detection
- **LOO ICIR** per suggerimento pesi
- **Auto-apply guardrails** (G1-G4) con fallback a Telegram approval

```python
from src.performance.ic import compute_composite_ic, compute_icir

# Composite IC
ic_result = compute_composite_ic(scores, returns, confidences)
# ic_result.composite_ic, .spearman, .hit_rate, .brier

# ICIR with Newey-West HAC
icir_result = compute_icir(scores, returns, confidences)
# icir_result.icir, .newey_west_std
```

### 6. Auto-Apply Weights con Telegram Approval Flow

Quando il PerformanceWorker calcola nuovi pesi:

```
run_weekly_weights()
  → compute LOO ICIR → compute_new_weights()
  → store Redis: ensemble:weights:suggestion (7d TTL)
  → trigger: check_and_apply_weights.apply_async(countdown=5)

check_and_apply_weights()
  G1: AUTO_APPLY_ENABLED? → no → exit silenzioso
  G2: VIX < 30? → fetch da FRED (cache Redis 1h), fail-safe freeze
  G3: std(ICIR) < 0.15? → troppa varianza modelli → freeze
  G4: max(|Δpeso|) < 15%? → cambio troppo brusco → freeze

  Se PASS → set_ensemble_weights(source="auto_apply") + Telegram ✅
  Se FAIL → log PostgreSQL source="freeze"
           + Telegram ⚠️ con inline keyboard (✅ Approva / ❌ Rifiuta)

poll_telegram_updates() [ogni 5s via Celery beat]
  → GET /getUpdates
  → verifica user_id ∈ TELEGRAM_ALLOWED_USER_IDS
  → verifica token SHA256(computed_at)[:8] anti-replay
  → approve → set_ensemble_weights(source="telegram") + log PG
  → reject  → delete suggestion + log PG source="rejected_via_telegram"
```

### 7. RedisStore

Redis memorizza:
- **Segnali** (TTL 4 ore)
- **Kill-switch state** (no TTL)
- **Fallback counter** (circuit breaker, TTL 24h)
- **Budget exhausted flag** (TTL fino a mezzanotte)
- **Ensemble weights** correnti (TTL 30gg)
- **Weight suggestion** pendente (TTL 7gg) + snapshot (TTL 9gg)
- **Regime state** (TTL 25h)
- **VIX cached** (TTL 1h)
- **Telegram poller offset** (no TTL — persiste tra riavvii)

```python
from src.store.redis_store import RedisStore

store = RedisStore()

# Signal
store.write_sentiment(result)
signal = store.read_sentiment("AAPL")

# Kill-switch
store.activate_killswitch(reason="VIX spike > 40")
if store.is_killswitch_active():
    halt_trading()

# Regime
state = store.get_regime()
# state.regime, state.multiplier, state.macro_snapshot

# Weights
store.set_ensemble_weights({"opus": 0.4, "qwen3.5:cloud": 0.3, ...}, source="auto_apply")
```

### 8. PostgreSQLStore

PostgreSQL memorizza:
- **Audit trail** di tutti i segnali sentiment
- **Forward returns** per IC calculation
- **Spending records** per budget tracking
- **Weight update log** (ogni cambio pesi: source, before, after, freeze_reason)

```python
from src.store.pg_store import PostgreSQLStore

pg = PostgreSQLStore()

# Fetch for IC calculation
rows = pg.fetch_signals_for_ic(symbol="AAPL", days=30)
# [(score, forward_return, generated_at, model_id, fallback_used), ...]

# Log weight update
pg.log_weight_update(
    source="telegram",         # auto_apply | freeze | telegram | rejected_via_telegram | expired
    applied_weights={"opus": 0.4, ...},
    previous_weights={"opus": 0.34, ...},
    suggestion_data=suggestion,
)
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
| `/api/admin/killswitch` | POST | ✅ | Attiva kill-switch (halt trading) |
| `/api/admin/mode` | POST | ✅ | Set operating mode |

### Performance & Weights Endpoints

| Endpoint | Method | Auth | Descrizione |
|----------|--------|------|-------------|
| `/api/performance/latest` | GET | No | Ultimo performance report |
| `/api/weights/current` | GET | No | Pesi ensemble correnti |
| `/api/weights/suggestion` | GET | No | Suggerimento pesi pendente (con expiry) |
| `/api/weights/approve` | POST | ✅ | Approva pesi suggeriti o forza pesi custom |

---

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific category
python -m pytest tests/llm/ -v
python -m pytest tests/performance/ -v
python -m pytest tests/workers/ -v
python -m pytest tests/test_security_fixes.py -v

# Run with coverage
python -m pytest tests/ --cov=src --cov-report=html
```

### Test Coverage Attuale

| Categoria | Test Count | Status |
|-----------|------------|--------|
| LLM (client, ensemble, finbert) | 17 | ✅ |
| Performance (IC, weights, drift, postmortem, threshold) | 89 | ✅ |
| Workers (sentiment, performance, regime, telegram_poller) | 52 | ✅ |
| API (routes, auth, weight approval) | 12 | ✅ |
| Connectors (RSS, GDELT, macro, deduplicator) | 20 | ✅ |
| Models (regime, performance) | 8 | ✅ |
| Notifications (telegram format functions) | 15 | ✅ |
| QuantConnect (signal data) | 6 | ✅ |
| Security fixes | 15 | ✅ |
| Stores (Redis, Postgres, budget tracker) | 60 | ✅ |
| Config | 5 | ✅ |
| Analysis (backtest, finbert, GDELT AB) | 16 | ✅ |
| **TOTALE** | **433** | **✅** |

---

## Security

### Fix Implementati (P0)

| Vulnerabilità | Fix |
|---------------|-----|
| Command injection (subprocess) | `ALLOWED_MODEL_IDS` frozenset whitelist |
| CLI path non validato | `shutil.which()` + existence check |
| SQL injection (INTERVAL) | Parametrized query con `|| ' days'::interval` |
| BiDi override characters | Rimozione in `sanitize_text()` |
| Emoji nel JSON | Regex removal in `sanitize_text()` |
| Redis OOM | Try/except in tutte le write operations |
| ZeroDivisionError ensemble | Check `if total_conf == 0` |
| Connection leak PostgreSQL | Rollback su eccezione in `pg_store` |
| Telegram replay attack | Token SHA256(computed_at)[:8] per ogni suggestion |
| Telegram unauthorized tap | Allowlist TELEGRAM_ALLOWED_USER_IDS |

---

## Monitoraggio e Alerting

### Telegram Alerts

Il sistema invia alert per:
- **Kill-switch activation** (VIX spike, drawdown) → livello critical 🚨
- **Budget exhausted** (LLM daily limit raggiunto) → livello warning ⚠️
- **Fallback threshold** (3+ consecutivi → QC sizing 50%) → livello warning ⚠️
- **Drift detection** (PSI > 0.10 yellow, > 0.25 red) → livello warning/critical
- **Performance report** (giornaliero 03:00 UTC) → livello info 📊
- **Weight auto-apply** (successo guardrails) → livello info ✅
- **Weight freeze** (guardrail fallito) → con inline keyboard ✅/❌
- **Regime change** (solo al cambio, pre-market 07:00 UTC) → livello info/warning

### Redis Keys

| Key | Tipo | TTL | Descrizione |
|-----|------|-----|-------------|
| `signal:{symbol}:sentiment` | String | 4h | Ultimo segnale LLM per simbolo |
| `killswitch_active` | String | — | "1" = trading haltato |
| `killswitch_reason` | String | — | JSON con reason e timestamp |
| `fallback:consecutive:count` | Counter | 24h | Fallback counter (circuit breaker) |
| `fallback:alert_sent` | String | 24h | Flag dedup alert Telegram |
| `qc:sizing_multiplier` | String | 24h o regime TTL | Position sizing (1.0 / 0.5 / da regime) |
| `budget:exhausted` | String | fino a mezzanotte+1h | Flag budget LLM esaurito |
| `ensemble:weights:current` | String | 30gg | JSON pesi attivi + source |
| `ensemble:weights:suggestion` | String | 7gg | Suggerimento pesi pendente |
| `ensemble:weights:suggestion:snapshot` | String | 9gg | Backup snapshot (per expiry tracking) |
| `ensemble:divergence:log` | List | 24h | Log divergenze ensemble (max 1000) |
| `performance:latest_report` | String | 7gg | Ultimo JSON performance report |
| `performance:neg_ic_streak` | Counter | 30gg | Giorni consecutivi con IC negativo |
| `system:mode` | String | 30gg | Modalità operativa del sistema |
| `regime:current` | String | 25h | JSON RegimeState (regime + multiplier + snapshot LLM) |
| `macro:vix:latest` | String | 1h | VIX cached da FRED API |
| `telegram:poller:offset` | Integer | — | Ultimo update_id Telegram processato (no TTL) |
| `drift:alert:{model}` | String | 7gg | Alert drift per modello (PSI/CUSUM) |
| `market:vix` | String | — | VIX per circuit breaker (scritto da QuantConnect) |
| `portfolio:drawdown` | String | — | Drawdown portfolio (scritto da QuantConnect) |
| `portfolio:earnings_pct` | String | — | % portfolio in titoli con earnings imminenti |
| `market:cross_corr` | String | — | Correlazione cross-asset (scritto da QuantConnect) |

---

## Roadmap

### Fase 1 (Completata) ✅
- [x] LLM ensemble + FinBERT fallback
- [x] Budget tracker
- [x] Redis/PostgreSQL stores
- [x] SentimentWorker + PerformanceWorker
- [x] Composite IC + Newey-West HAC
- [x] PSI + CUSUM drift detection
- [x] FastAPI endpoints
- [x] QuantConnect integration
- [x] 281 test passing

### Fase 2 (Completata) ✅
- [x] LOO ICIR weight computation
- [x] Weight smoothing (0.75 old + 0.25 new)
- [x] Auto-apply guardrails (VIX, IC variance, weight delta)
- [x] Telegram approval flow (inline keyboard ✅/❌)
- [x] Audit trail weight changes (PostgreSQL weight_update_log)
- [x] RegimeDetector (bull/sideways/bear/high_vol → qc:sizing_multiplier)
- [x] Macro data connector (FRED API + yfinance)
- [x] 433 test passing

### Fase 1b (Scalability — In Progress)
- [ ] Redis connection pooling
- [ ] Celery worker autoscaling
- [ ] Structured logging (JSON)
- [ ] Health check endpoints espansi
- [ ] Backup script PostgreSQL

### Fase 3 (Planned)
- [ ] Multi-asset pipeline (ticker extraction da news)
- [ ] GDELT A/B test infrastructure
- [ ] Backtest framework integration (QuantConnect cloud)
- [ ] Position sizing adattivo basato su IC rolling

---

## License

MIT License — vedere file `LICENSE` per dettagli.
