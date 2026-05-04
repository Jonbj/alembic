# Architettura del Sistema — LLM Trading System

**Documento di Architettura Tecnica**  
**Versione:** 1.0.0  
**Data:** 2026-05-04  
**Stato:** Fase 1 Completata

---

## 1. Panoramica Architetturale

### 1.1 Paradigma Alpha Miner

Questo sistema implementa il paradigma **"Alpha Miner"** per l'integrazione di LLM in sistemi di trading algoritmico:

> **Principio Fondamentale:** I modelli LLM operano **esclusivamente offline** come motore di ricerca alpha. I segnali sono pre-calcolati e cached. Il motore di esecuzione **non chiama mai API LLM sincronamente** durante il loop di trading.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         OFFLINE SENTIMENT PIPELINE                           │
│                                                                              │
│   ┌──────────────┐     ┌─────────────────────┐     ┌─────────────────────┐  │
│   │ News Sources │────▶│ Celery Sentiment    │────▶│ Redis Cache (TTL)   │  │
│   │ - RSS Feeds  │     │ Worker (async)      │     │ - Signali 4h        │  │
│   │ - GDELT      │     │ - LLM Ensemble      │     │ - Kill-switch       │  │
│   │ - SEC EDGAR  │     │ - FinBERT Fallback  │     │ - Counters          │  │
│   └──────────────┘     └─────────────────────┘     └─────────────────────┘  │
│                                              │                               │
│                                              ▼                               │
│                                     ┌─────────────────────┐                  │
│                                     │ PostgreSQL (Audit)  │                  │
│                                     │ - Tutti i segnali   │                  │
│                                     │ - Forward returns   │                  │
│                                     │ - Spending records  │                  │
│                                     └─────────────────────┘                  │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      │ Lettura a ogni tick
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         EXECUTION ENGINE (QuantConnect)                      │
│                                                                              │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │ OnData() - Ogni tick (1ms - 1min)                                    │  │
│   │   1. Leggi segnale da Redis (O(1), locale)                           │  │
│   │   2. Calcola position sizing (QC multiplier da Redis)                │  │
│   │   3. Verifica kill-switch                                            │  │
│   │   4. Esegui ordine se segnale valido                                 │  │
│   │                                                                      │  │
│   │   ❌ NO chiamate API LLM                                             │  │
│   │   ❌ NO attese I/O                                                   │  │
│   │   ❌ NO serializzazione JSON                                         │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Perché Alpha Miner?

| Approccio | Latenza | Costo | Affidabilità | Complessità |
|-----------|---------|-------|--------------|-------------|
| **LLM in-loop** | ~2-10s per chiamata | $0.01-0.10 per tick | Dipende da API | Alta (timeout, retry) |
| **Alpha Miner** | <1ms (Redis GET) | $0.0001 per tick (cached) | 99.9% (locale) | Bassa |

**Conclusione:** Alpha Miner riduce latenza di **1000-10000x** e costi di **100-1000x**.

---

## 2. Componenti Principali

### 2.1 LLM Ensemble

#### Architettura

```
                    ┌─────────────────────────────────────────────┐
                    │           run_ensemble_query()              │
                    │                                             │
prompt ────────────▶│  ┌─────────────┐  ┌─────────────┐          │
                    │  │ OpusClient  │  │ Qwen35Client │          │
                    │  │ (async)     │  │ (async)     │          │
                    │  └──────┬──────┘  └──────┬──────┘          │
                    │         │                │                 │
                    │         ▼                ▼                 │
                    │  ┌─────────────────────────────────┐      │
                    │  │   asyncio.as_completed(tasks)   │      │
                    │  │   (completion order, non input) │      │
                    │  └─────────────────────────────────┘      │
                    │         │                │                 │
                    │         ▼                ▼                 │
                    │  ┌─────────────────────────────────┐      │
                    │  │      EnsembleAggregator         │      │
                    │  │  - Confidence-weighted avg      │      │
                    │  │  - Divergence check (std < 0.30)│      │
                    │  └─────────────────────────────────┘      │
                    └─────────────────────────────────────────────┘
                                         │
                         ┌───────────────┼───────────────┐
                         │               │               │
                         ▼               ▼               ▼
                  Aggregated      Divergence      No Eligible
                  Result          (std ≥ 0.30)    Models
                         │               │               │
                         │               └───────┬───────┘
                         │                       │
                         │                       ▼
                         │              FinBERT Fallback
                         │
                         ▼
                  Redis Write + PG Audit
```

#### Formula di Aggregazione

```python
# Confidence-weighted average
total_conf = sum(model.confidence for model in eligible_models)
weighted_polarity = sum(
    model.polarity * model.confidence for model in eligible_models
) / total_conf

# Mean confidence (per hit rate calculation)
mean_confidence = total_conf / len(eligible_models)

# Ensemble standard deviation (divergence metric)
ensemble_std = np.std([model.polarity for model in eligible_models])
```

#### Divergence Detection

```python
# Se std ≥ threshold, i modelli discordano troppo → fallback
if len(eligible) > 1 and ensemble_std >= divergence_threshold:
    return None  # Trigger FinBERT fallback
```

**Soglia operativa:** `divergence_threshold = 0.30`

---

### 2.2 FinBERT Fallback con Entropic Confidence Mapping

#### Perché Entropic Mapping?

FinBERT produce **softmax probabilities** (es. `[0.1, 0.8, 0.1]` per `[neg, pos, neu]`).
La confidence "grezza" (max probability) non cattura l'**incertezza della distribuzione**.

**Esempio:**
- `[0.05, 0.90, 0.05]` → confidence = 0.90 (distribuzione "piccata", alta certezza)
- `[0.30, 0.35, 0.35]` → confidence = 0.35 (distribuzione "piatta", bassa certezza)

#### Formula Entropica

```python
def map_finbert_confidence(softmax_probs: list[float]) -> float:
    """
    Converte softmax probabilities in confidence usando entropia normalizzata.
    
    H(p) = -Σ p_i * log(p_i)  (entropia di Shannon)
    H_max = log(n)  (entropia massima, distribuzione uniforme)
    confidence = 1 - H(p) / H_max
    """
    import numpy as np
    probs = np.array(softmax_probs)
    entropy = -np.sum(probs * np.log(probs + 1e-9))
    max_entropy = np.log(len(probs))  # 3 classi → log(3) ≈ 1.099
    confidence = 1.0 - (entropy / max_entropy)
    return float(np.clip(confidence, 0.0, 1.0))
```

**Interpretazione:**
- `confidence ≈ 1.0` → entropia bassa, distribuzione "piccata" (certo)
- `confidence ≈ 0.0` → entropia alta, distribuzione "piatta" (incerto)

---

### 2.3 Budget Tracker

#### Architettura

```
┌─────────────────────────────────────────────────────────────────┐
│                    LLMBudgetTracker                             │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  check_budget()                                           │ │
│  │    1. Leggi spent_today da Redis                          │ │
│  │    2. Confronta con LLM_DAILY_BUDGET_USD                  │ │
│  │    3. Raise LLMBudgetExhaustedError se exceeded           │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  record_spending(model_id, input_tokens, output_tokens)   │ │
│  │    1. Calcola costo: (input * input_rate + output * out)  │ │
│  │    2. Incrementa spent_today in Redis                     │ │
│  │    3. Scrivi audit record su PostgreSQL                   │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  Redis: spent_today:counter (TTL: 24h)                          │
│  PostgreSQL: llm_spending (audit trail)                         │
└─────────────────────────────────────────────────────────────────┘
```

#### Model Costs (per 1M tokens)

| Modello | Input ($/1M) | Output ($/1M) |
|---------|--------------|---------------|
| Opus    | 15.0         | 75.0          |
| Sonnet  | 3.0          | 15.0          |
| Haiku   | 0.25         | 1.25          |
| Qwen3.5 | 2.0          | 6.0           |
| DeepSeek-V4-Pro | 4.0  | 12.0          |

#### Budget Enforcement Flow

```python
async def process_news_item(item: NewsItem):
    try:
        # STEP 1: Check budget BEFORE calling LLM
        await budget_tracker.check_budget()  # Raise se exhausted
        
        # STEP 2: Call LLM ensemble
        outputs = await run_ensemble_query(...)
        result = aggregator.aggregate(outputs)
        
        # STEP 3: Record spending
        for model_id in ensemble_model_ids:
            await budget_tracker.record_spending(...)
            
    except LLMBudgetExhaustedError:
        # STEP 4: Fallback a FinBERT (gratis)
        result = await finbert.analyze(item.body)
```

---

### 2.4 RedisStore

#### Keys e Strutture Dati

| Key Pattern | Tipo | TTL | Descrizione |
|-------------|------|-----|-------------|
| `signal:{symbol}:sentiment` | String | 4h | Ultimo segnale per simbolo |
| `killswitch_active` | String | — | "1" = attivo, "0" = inattivo |
| `killswitch_reason` | String | — | JSON con reason e timestamp |
| `fallback:consecutive:count` | Counter | 24h | Fallback counter (circuit breaker) |
| `fallback:alert_sent` | String | 24h | Dedup flag per alert |
| `qc:sizing_multiplier` | String | 24h | "1.0" o "0.5" (dopo 3 fallback) |
| `budget:exhausted` | String | ~24h | "1" = budget exhausted |
| `ensemble:weights:current` | String | 30gg | JSON con weights e source |
| `ensemble:divergence:log` | List | 24h | Log delle divergenze (max 1000) |
| `performance:latest_report` | String | 7gg | JSON performance report |
| `performance:neg_ic_streak` | String | 30gg | Counter giorni IC negativo |
| `system:mode` | String | 30gg | "backtest", "paper", "full_auto", "halted" |

#### OOM Handling Pattern

```python
def write_sentiment(self, result: SentimentResult) -> None:
    """Scrive segnale su Redis con gestione OOM."""
    key = f"signal:{result.symbol}:sentiment"
    try:
        self._r.setex(key, self._signal_ttl, result.model_dump_json())
    except Exception as e:
        error_msg = str(e)
        if "OOM" in error_msg or "out of memory" in error_msg.lower():
            # Graceful degradation: logga e scarta
            print(f"RedisStore: Redis OOM - dropping signal for {result.symbol}")
        else:
            # Altri errori: propaga
            raise
```

**Perché OOM handling?** Redis ha memoria limitata. In production, meglio scattare segnali non critici che crashare.

---

### 2.5 PostgreSQLStore

#### Schema Database

```sql
-- Sentiment signals (audit + IC calculation)
CREATE TABLE sentiment_signals (
    id SERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    score DOUBLE PRECISION NOT NULL,          -- polarity * confidence
    confidence DOUBLE PRECISION NOT NULL,
    reasoning TEXT,
    model_id TEXT NOT NULL,                   -- "opus", "qwen3.5:cloud", ecc.
    ensemble_std DOUBLE PRECISION,            -- std se ensemble, NULL se FinBERT
    fallback_used BOOLEAN NOT NULL DEFAULT FALSE,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    forward_return DOUBLE PRECISION,          -- Popolato da PerformanceWorker
    
    UNIQUE(symbol, generated_at)              -- Upsert su segnale duplicato
);

-- Indici per performance
CREATE INDEX idx_sentiment_signals_symbol_time 
    ON sentiment_signals(symbol, generated_at DESC);
CREATE INDEX idx_sentiment_signals_forward_return 
    ON sentiment_signals(forward_return) 
    WHERE forward_return IS NOT NULL AND NOT fallback_used;

-- LLM spending (budget tracking)
CREATE TABLE llm_spending (
    id SERIAL PRIMARY KEY,
    model_id TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_usd DOUBLE PRECISION NOT NULL,
    spent_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_llm_spending_date 
    ON llm_spending(spent_at DESC);
```

#### Connection Pooling

```python
_db_pool = pool.ThreadedConnectionPool(
    minconn=2,      # Minimo 2 connessioni sempre attive
    maxconn=20,     # Massimo 20 connessioni concurrenti
    dsn=config.DATABASE_URL,
    timeout=30,     # CRITICAL: Raise dopo 30s invece di hang
)
```

**Perché pooling?** Creare connessioni PostgreSQL è costoso (~10-50ms). Il pooling riutilizza connessioni esistenti.

#### Rollback su Errore

```python
def write_signal(self, result: SentimentResult) -> None:
    conn = self._get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(self._INSERT_SIGNAL, (...))
        conn.commit()
    except Exception:
        conn.rollback()  # CRITICAL: Rollback su errore
        raise
```

---

## 3. Performance Worker

### 3.1 Composite IC B4

#### Formula

```
IC_composite = 0.5 × Spearman(score, forward_return)
             + 0.3 × weighted_hit_rate
             + 0.2 × (1 − Brier_score)
```

#### Componenti

| Componente | Peso | Descrizione |
|------------|------|-------------|
| **Spearman** | 50% | Correlazione rank-order tra segnale e return |
| **Weighted Hit Rate** | 30% | % di segnali con segno corretto (pesato per confidence) |
| **1 − Brier** | 20% | Accuratezza calibration (1 - MSE) |

#### Forward Return Calculation

```python
# Forward return a h orizzonti (1h, 4h, 24h)
forward_return_h = (price_t+h - price_t) / price_t

# Per backtest: usa close-to-close return
# Per live: usa return realizzato effettivo
```

---

### 3.2 Newey-West HAC Correction

#### Perché HAC?

Le serie temporali finanziarie hanno **autocorrelazione** (i return di oggi correlano con quelli di ieri). La std "grezza" sottostima il rischio.

#### Formula Newey-West

```python
def newey_west_std(residuals: np.ndarray, max_lag: int = 5) -> float:
    """
    Calcola std con correzione Newey-West per autocorrelazione.
    
    ω_j = 1 - j/(max_lag+1)  (pesi di Bartlett)
    HAC_var = σ² + 2 × Σ ω_j × γ_j
    HAC_std = sqrt(HAC_var)
    """
    n = len(residuals)
    sigma_sq = np.var(residuals)
    
    hac_var = sigma_sq
    for j in range(1, max_lag + 1):
        gamma_j = np.cov(residuals[:-j], residuals[j:])[0, 1]
        omega_j = 1 - j / (max_lag + 1)  # Bartlett weights
        hac_var += 2 * omega_j * gamma_j
    
    return float(np.sqrt(hac_var))
```

---

### 3.3 PSI (Population Stability Index)

#### Formula

```
PSI = Σ (expected_i × ln(expected_i / actual_i))
```

#### Interpretazione

| PSI Value | Interpretazione | Azione |
|-----------|-----------------|--------|
| < 0.10 | Stabile | Nessuna azione |
| 0.10 - 0.25 | Moderate drift | Monitoraggio aumentato |
| > 0.25 | Severe drift | Freeze weight update + alert |

#### Calcolo Pratico

```python
def compute_psi(baseline: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
    # 1. Crea bin edges che coprono entrambe le distribuzioni
    edges = np.linspace(min(baseline), max(current), bins + 1)
    
    # 2. Calcola percentuali per bin
    exp_pct = np.histogram(baseline, edges)[0] / len(baseline) + 1e-6
    act_pct = np.histogram(current, edges)[0] / len(current) + 1e-6
    
    # 3. Applica formula PSI
    psi = np.sum(exp_pct * np.log(exp_pct / act_pct))
    return float(psi)
```

---

### 3.4 CUSUM (Page-Hinkley)

#### Formula

```
S_pos[t] = max(0, S_pos[t-1] + (x[t] - μ) / σ - k)
S_neg[t] = min(0, S_neg[t-1] + (x[t] - μ) / σ + k)

CUSUM = max(S_pos, |S_neg|)
```

Dove:
- `μ` = baseline mean
- `σ` = baseline std
- `k` = slack parameter (tipicamente 0.5)

#### Interpretazione

| CUSUM Value | Interpretazione |
|-------------|-----------------|
| < 5.0 | Nessuno shift rilevato |
| 5.0 - 8.0 | Possibile shift (monitorare) |
| > 8.0 | Shift confermato (azione richiesta) |

---

## 4. Circuit Breakers

### 4.1 Hard Breakers (Trading Halt)

```python
HARD_BREAKERS = {
    "vix_spike": lambda ctx: ctx.vix > 40 or ctx.vix_1d_change > 0.30,
    # VIX > 40 = panico di mercato
    # VIX +30% in 1 giorno = spike improvviso
    
    "system_drawdown": lambda ctx: ctx.portfolio_drawdown > 0.05,
    # Drawdown > 5% = perdita significativa
    
    "ic_negative_run": lambda ctx: ctx.consecutive_negative_ic_days >= 5,
    # 5 giorni consecutivi con IC negativo = modello rotto
}
```

**Azione:** Freeze weight update + alert critico + possibile halt trading.

### 4.2 Soft Warnings (Monitoraggio)

```python
SOFT_WARNINGS = {
    "earnings_concentration": lambda ctx: ctx.portfolio_earnings_pct > 0.50,
    # >50% portfolio in aziende che riportano earnings = rischio concentrazione
    
    "cross_asset_correlation": lambda ctx: ctx.cross_asset_correlation > 0.90,
    # Correlazione >90% = mercato direzionale, alpha difficile
}
```

**Azione:** Warning nel report, nessuna azione automatica.

---

## 5. Security Architecture

### 5.1 Command Injection Prevention

#### Problema

```python
# ❌ SBAGLIATO: command injection possibile
subprocess.run(["claude", "--model", model_id, ...])
# Se model_id = "opus; rm -rf /", esegue rm -rf /
```

#### Fix: ALLOWED_MODEL_IDS

```python
ALLOWED_MODEL_IDS = frozenset({
    "opus", "sonnet", "haiku",
    "qwen3.5:cloud", "deepseek-v4-pro:cloud",
    "qwen3-coder-next:cloud", "devstral-small-2:24b-cloud",
    # ... tutti i modelli validi
})

def _validate_model_id(self, model_id: str) -> None:
    if model_id not in ALLOWED_MODEL_IDS:
        raise ValueError(f"Invalid model_id: {model_id!r}")
```

---

### 5.2 SQL Injection Prevention

#### Problema

```python
# ❌ SBAGLIATO: SQL injection possibile
cur.execute(f"SELECT * FROM signals WHERE date >= now() - INTERVAL '{days} days'")
```

#### Fix: Parametrized Query

```python
# ✅ CORRETTO: PostgreSQL interval arithmetic
cur.execute(
    "SELECT * FROM signals WHERE date >= now() - (%s || ' days')::interval",
    (str(days),)
)
```

---

### 5.3 Input Sanitization

#### BiDi Override Characters

```python
# Caratteri BiDi usati per RTL attack
BIDI_CHARS = ["‮", "‭", "‬", "⁧", "⁦", "⁨", "⁩"]

def sanitize_text(text: str) -> str:
    # NFKC normalization
    text = unicodedata.normalize("NFKC", text)
    
    # Remove BiDi override
    for char in BIDI_CHARS:
        text = text.replace(char, "")
    
    # Remove emoji
    emoji_pattern = re.compile("[\U0001F600-\U0001F64F]+")
    text = emoji_pattern.sub("", text)
    
    return text
```

---

## 6. Deployment

### 6.1 Development

```bash
# Docker Compose (Redis + PostgreSQL)
docker-compose up -d

# Celery worker
celery -A src.workers.celery_app worker --loglevel=info

# Celery beat (scheduler)
celery -A src.workers.celery_app beat --loglevel=info

# FastAPI
uvicorn src.api.main:app --reload
```

### 6.2 Production

```bash
# Redis cluster (3 master + 3 replica)
redis-cli --cluster create redis1:6379 redis2:6379 redis3:6379

# PostgreSQL (primary + replica)
pg_ctl start -D /var/lib/postgresql/data
pg_basebackup -h primary -D /var/lib/postgresql/data -U replicator

# Celery (autoscaling)
celery -A src.workers.celery_app worker \
    --autoscale=20,5 \
    --max-tasks-per-child=1000 \
    --loglevel=info

# FastAPI (gunicorn + uvicorn workers)
gunicorn src.api.main:app \
    -w 4 \
    -k uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000
```

---

## 7. Monitoring

### 7.1 Metrics da Monitorare

| Metric | Soglia | Azione |
|--------|--------|--------|
| Redis memory | >80% | Alert, cleanup |
| PostgreSQL connections | >15/20 | Scale up pool |
| Celery task latency | >30s | Alert, investigate |
| LLM budget spent | >80% | Warning |
| Fallback rate | >20% | Investigate ensemble |
| PSI 90gg | >0.10 | Monitoraggio |
| IC (rolling 7gg) | <0 | Investigate |

### 7.2 Redis Monitoring Commands

```bash
# Memory usage
redis-cli INFO memory

# Keyspace
redis-cli INFO keyspace

# Slow log
redis-cli SLOWLOG GET 10

# Memory per key pattern
redis-cli --bigkeys
```

---

## 8. Decision Log

### 8.1 Perché Celery e non asyncio puro?

**Decisione:** Celery per task scheduling e retry logic.

**Motivazione:**
- `celery beat` gestisce schedule complessi (15min, daily, weekly)
- Retry automatici con exponential backoff
- Task result backend (Redis)
- Monitoring con Flower

**Trade-off:** Overhead di ~100ms per task startup.

---

### 8.2 Perché Redis e non solo PostgreSQL?

**Decisione:** Redis per signal caching, PostgreSQL per audit.

**Motivazione:**
- Redis: O(1) read/write, TTL nativo, atomic operations
- PostgreSQL: ACID, query complesse, IC calculation

**Trade-off:** Duplicazione dati (Redis cache + PG audit).

---

### 8.3 Perché 3 modelli nell'ensemble?

**Decisione:** Opus + Qwen3.5 + DeepSeek-V4-Pro.

**Motivazione:**
- Diversità: 3 provider diversi (Anthropic, Alibaba, DeepSeek)
- Costo: ~$0.03 per query (bilanciato)
- Performance: IC > 0.10 in backtest

**Trade-off:** Se un provider è down, ensemble degrada a 2 modelli.

---

## 9. Appendix

### 9.1 Glossario

| Termine | Definizione |
|---------|-------------|
| **IC** | Information Coefficient: correlazione tra segnale e return |
| **ICIR** | IC / IC std: risk-adjusted IC |
| **PSI** | Population Stability Index: drift detection |
| **CUSUM** | Cumulative Sum: change point detection |
| **HAC** | Heteroskedasticity and Autocorrelation Consistent |
| **LOO** | Leave-One-Out: cross-validation per weights |

### 9.2 Riferimenti

- [Design Spec](docs/superpowers/specs/2026-05-03-trading-system-design.md)
- [Fase 1 Plan](docs/superpowers/plans/FASE1-START.md)
- [API Docs](docs/API.md)
