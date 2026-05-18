<div align="center">
  <img src="../img/alembic.png" alt="Alembic" width="140"/>
</div>

# Alembic — Architettura del Sistema

**Documento di Architettura Tecnica**  
**Versione:** 3.1.0  
**Data:** 2026-05-18  
**Stato:** Fase 3 Completata + ExecutionWorker + Phase B1/B2 (594 test passing)

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
│                                     │ - sentiment_signals │                  │
│                                     │ - llm_spending      │                  │
│                                     │ - weight_update_log │                  │
│                                     └─────────────────────┘                  │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│                    NEWS-DRIVEN INGESTION PIPELINE (Fase 3)                   │
│                                                                              │
│   ┌──────────────┐     ┌─────────────────────┐     ┌─────────────────────┐  │
│   │ GDELT GKG v2 │────▶│ NewsIngestionWorker │────▶│ Redis news:queue    │  │
│   │ (15min beat) │     │ (Celery task)       │     │ (annotated items)   │  │
│   │ V2Organiz.   │     │ - GDELTGKGConnector │     └──────────┬──────────┘  │
│   │ (org names)  │     │ - TickerExtractor   │                │             │
│   └──────────────┘     │   (PG lookup)       │                ▼             │
│                        │ - Deduplicator      │     ┌─────────────────────┐  │
│   ┌──────────────┐     │   (Redis SET NX)    │     │ SentimentWorker     │  │
│   │ PostgreSQL   │────▶│                     │     │ (existing, Fase 1)  │  │
│   │ ticker_lookup│     └─────────────────────┘     └─────────────────────┘  │
│   │ (company →   │                                                           │
│   │  ticker map) │     Stats returned per run:                               │
│   └──────────────┘     fetched / tickers_found / discarded / queued / dupes  │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│                       REGIME DETECTION PIPELINE (Fase 2)                     │
│                                                                              │
│   ┌──────────────┐     ┌─────────────────────┐     ┌─────────────────────┐  │
│   │ FRED API     │────▶│ detect_regime()     │────▶│ Redis               │  │
│   │ - VIX(CXLS) │     │ 07:00 UTC Lun-Ven   │     │ - regime:current    │  │
│   │ - T10Y2Y    │     │ 2 LLMs in parallel  │     │ - qc:sizing_mult.   │  │
│   ├──────────────┤     │ (Opus + Qwen3.5)    │     └─────────────────────┘  │
│   │ yfinance     │     │ Consensus/min mult. │                               │
│   │ - SPY 20d   │     └─────────────────────┘                               │
│   └──────────────┘                                                           │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│                 WEIGHT AUTO-APPLY + TELEGRAM APPROVAL FLOW (Fase 2)          │
│                                                                              │
│   run_weekly_weights()  ──────────────▶  check_and_apply_weights()           │
│   Lunedì 04:00 UTC          (5s)         G1: AUTO_APPLY_ENABLED?             │
│   LOO ICIR → new weights                 G2: VIX < 30?                       │
│   → Redis suggestion                     G3: std(ICIR) < 0.15?               │
│                                          G4: max(Δpeso) < 15%?               │
│                                               │          │                   │
│                                            PASS        FAIL                  │
│                                               │          │                   │
│                                       auto_apply   Telegram ⚠️ + keyboard    │
│                                                         │                    │
│                                          poll_telegram_updates() [5s]        │
│                                          ✅ approve / ❌ reject               │
└──────────────────────────────────────────────────────────────────────────────┘

                    ↓ (segnali + regime multiplier ogni 15 min)

┌──────────────────────────────────────────────────────────────────────────────┐
│                   EXECUTION ENGINE (Alpaca ExecutionWorker)                  │
│                                                                              │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │ run_execution_cycle() - Celery beat ogni 15 min (market hours)       │  │
│   │   1. Kill-switch Redis check → halt se attivo                        │  │
│   │   2. Batch EMA cache: fetch hourly bars, calcola 20-period EMA       │  │
│   │   3. Fetch account Alpaca + open positions (una chiamata)            │  │
│   │   4. Drawdown cap: se daily loss ≥ 10% → kill-switch + CRITICAL alert│  │
│   │   5. Per simbolo:                                                    │  │
│   │       a. Leggi signal da Redis (TTL 4h, max 30 min stale)            │  │
│   │       b. Posizione aperta → stop-loss o skip (no pyramiding)         │  │
│   │       c. score > 0.3 e price > EMA20 → market BUY order             │  │
│   │          Notional = portfolio × 10% × regime_multiplier             │  │
│   │                                                                      │  │
│   │   ❌ NO chiamate API LLM                                             │  │
│   │   ❌ NO attese I/O nel loop per-simbolo                              │  │
│   │   ✅ Alert CRITICAL Telegram se Redis/Alpaca irraggiungibili         │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│   Nota: QuantConnect Lean è il target per Phase C+ (backtesting             │
│   istituzionale multi-asset). Per paper trading validation (Phase A),       │
│   l'integrazione Alpaca diretta è più semplice e gira nello stack           │
│   esistente senza richiedere un account QC.                                  │
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

### 2.4 NewsIngestionWorker (Fase 3)

#### Ruolo nel Sistema

Il `NewsIngestionWorker` sostituisce il modello a **watchlist fissa** con un approccio **symbol-free**: invece di ricevere una lista predefinita di ticker, scansiona le notizie finanziarie globali e risolve automaticamente le aziende menzionate a ticker.

```
GDELT GKG v2  →  GDELTGKGConnector  →  GKGNewsItem (org_names=[…])
                                              │
                                    TickerExtractor.extract()
                                         PG lookup
                                              │
                                    ticker = ["AAPL", "MSFT", …]
                                              │
                                    ┌─────────┴────────┐
                                    │                  │
                              NewsItem               NewsItem
                            id="url:AAPL"         id="url:MSFT"
                            asset_tags=["AAPL"]   asset_tags=["MSFT"]
                                    │                  │
                            is_duplicate_by_id?  is_duplicate_by_id?
                                    │                  │
                              rpush news:queue    rpush news:queue
```

#### Deduplicazione

Due strategie coesistono nel `Deduplicator`:

| Metodo | Chiave Redis | Quando usarlo |
|--------|-------------|---------------|
| `is_duplicate()` | `dedup:{sha256(title+body)}` | SentimentWorker (stesso articolo, content-based) |
| `is_duplicate_by_id()` | `dedup:id:{sha256(item.id)}` | NewsIngestionWorker (stesso url×ticker, id-based) |

`is_duplicate_by_id()` è necessario perché lo stesso articolo genera più `NewsItem` con `id="{url}:{ticker}"`. Il content hash sarebbe identico per tutti i ticker — usarlo deduplicherebbe erroneamente il secondo ticker.

#### Espansione Multi-Ticker

Un articolo che menziona Apple + Microsoft genera **due** `NewsItem` separati:

```python
# Entrambi hanno lo stesso title/body
item_aapl = NewsItem(id="https://…:AAPL", asset_tags=["AAPL"], ...)
item_msft = NewsItem(id="https://…:MSFT", asset_tags=["MSFT"], ...)
```

Il `SentimentWorker` downstream legge `asset_tags[0]` — invariato rispetto a Fase 1.

---

### 2.5 RedisStore

#### Keys e Strutture Dati

| Key Pattern | Tipo | TTL | Descrizione |
|-------------|------|-----|-------------|
| `signal:{symbol}:sentiment` | String | 4h | Ultimo segnale LLM per simbolo |
| `killswitch_active` | String | — | "1" = trading haltato |
| `killswitch_reason` | String | — | JSON con reason e timestamp attivazione |
| `fallback:consecutive:count` | Counter | 24h | Fallback consecutivi (circuit breaker, reset al successo) |
| `fallback:alert_sent` | String | 24h | Dedup flag per alert Telegram fallback |
| `qc:sizing_multiplier` | String | 24h o regime TTL | "1.0"/"0.5" (fallback CB) oppure regime multiplier |
| `budget:exhausted` | String | fino a mezzanotte+1h | "1" = LLM budget esaurito per oggi |
| `ensemble:weights:current` | String | 30gg | JSON `{"weights": {...}, "source": "auto_apply\|telegram\|..."}` |
| `ensemble:weights:suggestion` | String | 7gg | Pesi proposti da LOO ICIR, in attesa di approvazione |
| `ensemble:weights:suggestion:snapshot` | String | 9gg | Backup snapshot per rilevare expiry senza approvazione |
| `ensemble:divergence:log` | List | 24h | Log divergenze ensemble (max 1000 entries) |
| `performance:latest_report` | String | 7gg | JSON PerformanceReport completo |
| `performance:neg_ic_streak` | Counter | 30gg | Giorni consecutivi con IC < 0 (circuit breaker) |
| `system:mode` | String | 30gg | `backtest\|paper\|semi_auto\|full_auto\|halted` |
| `regime:current` | String | 25h | JSON RegimeState (regime, multiplier, macro_snapshot, llm_outputs) |
| `macro:vix:latest` | String | 1h | VIX float cached da FRED API (riduce chiamate API) |
| `telegram:poller:offset` | Integer | — | Ultimo update_id Telegram (+1), no TTL — persiste tra riavvii |
| `drift:alert:{model}` | String | 7gg | JSON drift alert per modello (PSI, CUSUM, livello) |
| `market:vix` | String | — | VIX per circuit breaker (reserved — non ancora scritto) |
| `portfolio:earnings_pct` | String | — | % portfolio in titoli con earnings imminenti (reserved) |
| `market:cross_corr` | String | — | Correlazione cross-asset (reserved) |
| `news:queue` | List | — | Coda FIFO di NewsItem JSON (RPUSH da NewsIngestionWorker, LPOP da SentimentWorker) |
| `dedup:{sha256}` | String | 2h | Content-hash dedup per SentimentWorker (`is_duplicate`) |
| `dedup:id:{sha256}` | String | 2h | ID-hash dedup per NewsIngestionWorker (`is_duplicate_by_id`) |

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

### 2.6 PostgreSQLStore

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

### 2.7 Notifier Protocol

`src/notifications/base.py` definisce il contratto astratto per tutti gli alert di sistema.

```python
class AlertLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

@runtime_checkable
class Notifier(Protocol):
    async def send_alert(self, message: str, level: AlertLevel = AlertLevel.INFO) -> bool: ...
```

**Perché Protocol e non ABC?** `Protocol` di Python usa structural subtyping: qualsiasi classe con il metodo `send_alert` compatibile è automaticamente un `Notifier`, senza ereditare esplicitamente. Questo permette di iniettare mock nei test senza importare `TelegramNotifier`.

**`AlertLevel` come `str, Enum`:** I valori `"info"`, `"warning"`, `"critical"` sono identici agli string literal usati prima dell'introduzione dell'enum. I caller esistenti che passano `level="warning"` continuano a funzionare invariati.

**Pattern di utilizzo nei worker:**

```python
# In Celery task entry-point (production):
from src.notifications.telegram import TelegramNotifier
notifier = TelegramNotifier()
run_execution_cycle(..., notifier=notifier)

# In test (nessun alert, asserzione esplicita):
notifier = MagicMock()
notifier.send_alert = AsyncMock(return_value=True)
run_execution_cycle(..., notifier=notifier)
notifier.send_alert.assert_called_once()
```

**Worker che usano `TelegramNotifier` direttamente** (regime.py, performance.py): migrazione pianificata per Phase B quando si aggiungono i nuovi tipi di alert. Non è urgente finché i worker non richiedono dependency injection per il testing.

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

### 4.1 Drawdown Cap — ExecutionWorker (Implementato)

Il controllo più importante è in `src/workers/execution.py`. A ogni ciclo, **prima** di qualsiasi ordine:

```python
MAX_DRAWDOWN_PCT = 0.10  # 10% — configurabile via costante

last_equity = float(account.last_equity)   # equity di chiusura del giorno precedente (Alpaca)
drawdown = (last_equity - portfolio_value) / last_equity

if drawdown >= MAX_DRAWDOWN_PCT:
    redis_store.activate_killswitch(reason)   # nessun ordine fino a reset manuale
    _fire_alert(notifier, reason, AlertLevel.CRITICAL)
    return stats                              # ciclo interrotto
```

**Perché `last_equity` e non un valore configurato?** Alpaca restituisce nativamente l'equity di chiusura del giorno precedente. È la base naturale per il drawdown giornaliero senza richiedere uno stato esterno.

**Reset:** solo manuale via `DELETE /api/admin/killswitch`.

### 4.2 Hard Breakers — PerformanceWorker (Piano)

Guardrail pianificati per Phase B, non ancora implementati:

```python
HARD_BREAKERS = {
    "vix_spike": lambda ctx: ctx.vix > 40 or ctx.vix_1d_change > 0.30,
    "ic_negative_run": lambda ctx: ctx.consecutive_negative_ic_days >= 5,
}
```

**Azione pianificata:** Freeze weight update + alert critico + halt trading.

### 4.3 Soft Warnings — PerformanceWorker (Piano)

```python
SOFT_WARNINGS = {
    "earnings_concentration": lambda ctx: ctx.portfolio_earnings_pct > 0.50,
    "cross_asset_correlation": lambda ctx: ctx.cross_asset_correlation > 0.90,
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

## 6b. RegimeDetector

### 6b.1 Architettura

Il `detect_regime` task viene eseguito ogni giorno lavorativo alle **07:00 UTC** (pre-market US) da Celery beat.

```
FRED API ──┐
           ├──▶ fetch_vix_from_fred()    → vix: float
           └──▶ fetch_yield_curve()      → T10Y2Y: float (negative = inverted)
yfinance ──────▶ fetch_spy_momentum_20d() → % return su 20 trading days

Prompt DK-CoT ──▶ asyncio.gather(LLM1, LLM2)
                         │
                    r1, r2: RegimeOutput
                         │
              ┌──────────┴──────────┐
            consensus           disagreement
              │                     │
           regime = r1        regime = min multiplier
                                 (più conservativo)
              │
   MacroSnapshot + RegimeState
              │
         Redis: regime:current (TTL 25h)
         Redis: qc:sizing_multiplier (TTL 25h)
              │
     Telegram alert (solo se regime cambia)
```

### 6b.2 Regimi e Moltiplicatori

| Regime | Condizioni indicative | Moltiplicatore |
|--------|----------------------|----------------|
| `bull` | VIX < 20, SPY > +3%, T10Y2Y > 0 | 1.0× |
| `sideways` | VIX 15-25, SPY ∈ [-3%, +3%] | 0.7× |
| `bear` | SPY < -8% o T10Y2Y < -0.5% | 0.4× |
| `high_vol` | VIX > 30 | 0.2× |

Il regime viene risolto con **priorità**: `high_vol > bear > sideways > bull`.

### 6b.3 Guardrail Cascade

```
1. Dati macro fuori range → skip, alert 🚨, Redis non aggiornato
   - VIX ∉ [5, 100]
   - T10Y2Y ∉ [-5%, +5%]
   - SPY momentum ∉ [-50%, +50%]

2. Entrambi i LLM falliscono → skip, alert 🚨

3. data_quality="partial" (uno o entrambi) → skip, alert ⚠️

4. Regime label invalido (non in valid_regimes) → skip, alert 🚨

5. Disaccordo → moltiplicatore più conservativo, alert ⚠️ al cambio

6. Consenso → applica regime, alert 📊 solo se regime cambia
```

---

## 6c. Auto-Apply Weights + Telegram Approval Flow

### 6c.1 Flusso Completo

```
Lunedì 04:00 UTC
run_weekly_weights()
  1. Fetch signals da PG (30 giorni, no fallback)
  2. compute_purified_icir() — Leave-One-Out cross-validation
  3. compute_new_weights() — smoothing 0.75×old + 0.25×new + guardrails
  4. Store Redis: ensemble:weights:suggestion (7d TTL)
  5. Store Redis: ensemble:weights:suggestion:snapshot (9d TTL)
  6. Send Telegram informativo (osservazionale)
  7. Trigger: check_and_apply_weights.apply_async(countdown=5)

check_and_apply_weights()  [triggered 5s dopo]
  G1: AUTO_APPLY_ENABLED? → False → exit silenzioso
  G2: VIX < 30? → fetch FRED (Redis cache 1h), None → fail-safe freeze
  G3: std(purified_icir) < 0.15? → alta varianza → freeze
  G4: max(|Δpeso|) < 0.15? → cambio troppo brusco → freeze

  [PASS] → set_ensemble_weights(source="auto_apply")
          → delete snapshot
          → log PG: source="auto_apply", note={vix, ic_variance, max_delta}
          → Telegram ✅ con nuovi pesi e delta

  [FAIL] → log PG: source="freeze", freeze_reason=<guardrail>
          → Genera token = SHA256(computed_at)[:8]  [anti-replay]
          → Send Telegram ⚠️ con inline keyboard:
              [✅ Approva | approve:<token>]
              [❌ Rifiuta | reject:<token>]

poll_telegram_updates()  [ogni 5s via Celery beat]
  → GET /getUpdates?offset=<redis_offset>&timeout=1
  → Per ogni callback_query:
      1. user_id ∈ TELEGRAM_ALLOWED_USER_IDS? → no → skip silenzioso
      2. parse action + token da callback_data
      3. get_weight_suggestion() → None → "Già processata"
      4. token == SHA256(suggestion.computed_at)[:8]? → no → "Già processata"
      5. action="approve" → _handle_approve()
         - set_ensemble_weights(source="telegram")
         - delete_weight_suggestion()
         - log PG: source="telegram"
         - answerCallbackQuery "✅ Pesi applicati"
         - editMessageReplyMarkup (rimuovi keyboard)
      6. action="reject" → _handle_reject()
         - delete_weight_suggestion()
         - log PG: source="rejected_via_telegram", applied_weights={}
         - answerCallbackQuery "❌ Suggestion rifiutata"
         - editMessageReplyMarkup (rimuovi keyboard)
  → Aggiorna offset = last_update_id + 1
    (solo se nessun errore — garanzia idempotency)

check_suggestion_expiry()  [giornaliero 05:00 UTC]
  → snapshot presente + suggestion assente → expired senza approvazione
  → log PG: source="expired"
  → delete snapshot
```

### 6c.2 Proprietà di Idempotency

| Scenario | Comportamento |
|----------|---------------|
| Double-tap (stesso utente tappa due volte) | Prima tap elaborata, seconda trova suggestion=None → "Già processata" |
| Stale tap (nuovo giro di pesi calcolato) | Token cambia con nuovo computed_at → mismatch → "Già processata" |
| Redis down durante approve | Exception rilanciata, offset NON aggiornato → retry a 5s |
| Telegram API down | HTTPError caught, offset NON aggiornato → retry a 5s |

### 6c.3 Audit Trail PostgreSQL

Ogni evento nel ciclo pesi viene loggato in `weight_update_log`:

| source | Significato |
|--------|-------------|
| `auto_apply` | Guardrails passati, pesi applicati automaticamente |
| `freeze` | Guardrail fallito, nessun cambio |
| `telegram` | Operatore ha approvato via Telegram |
| `rejected_via_telegram` | Operatore ha rifiutato via Telegram |
| `suggestion` | Approvato via POST /api/weights/approve con pesi suggeriti |
| `override` | Approvato via POST /api/weights/approve con pesi custom |
| `expired` | Suggestion scaduta (7d TTL) senza approvazione |

---

## 6d. ExecutionWorker (Alpaca)

### 6d.1 Architettura

Il `run_execution_worker` task viene eseguito ogni **15 minuti** durante gli orari di mercato US (Lun–Ven 14:00–21:00 UTC) da Celery beat.

```
Redis ──▶ kill-switch check ──▶ halt se attivo
           │
           ▼
Alpaca Data API ──▶ _build_market_cache()
  batch: tutti i simboli         20-period EMA + last price
  una sola chiamata HTTP         per ogni simbolo
           │
           ▼
Alpaca Trading API ──▶ get_account() + get_all_positions()
  portfolio_value                una sola chiamata HTTP
  last_equity (giorno prec.)
  open_positions dict
           │
           ▼
Drawdown cap ─── (last_equity - portfolio_value) / last_equity ≥ 10%?
  Sì → activate_killswitch() + CRITICAL alert → return
  No → continua
           │
           ▼
Per ogni simbolo in WATCHLIST_SYMBOLS:
  read_sentiment(symbol) → stale o fallback? → skip
  symbol in open_positions?
    ├─ price < stop_price (entry × 0.98)? → close_position()
    └─ altrimenti → skip (idempotent, no pyramiding)
  score > 0.3 e price > EMA20?
    └─ submit_order(MarketOrderRequest, notional=ptf × 10% × regime_mult)
```

### 6d.2 Costanti Operative

| Costante | Valore | Descrizione |
|---|---|---|
| `ENTRY_THRESHOLD` | 0.30 | Score minimo per entry |
| `MAX_POSITION_PCT` | 0.10 | Max % portfolio per posizione |
| `STOP_LOSS_PCT` | 0.02 | Stop-loss: 2% sotto entry |
| `MAX_DRAWDOWN_PCT` | 0.10 | Drawdown giornaliero max prima del kill-switch |
| `SIGNAL_MAX_AGE_MIN` | 30 | Segnale accettato se non più vecchio di 30 min |
| `EMA_PERIOD` | 20 | EMA a 20 barre orarie |

### 6d.3 Modalità Operative (in roadmap)

| Modalità | Comportamento esecuzione ordini |
|---|---|
| `paper` | Automatica — Alpaca paper account (soldi finti) |
| `semi_auto` | **Da implementare**: Telegram approval per-ordine con timeout 5 min |
| `full_auto` | Automatica — Alpaca live account (soldi reali) |

La modalità `paper` è quella attiva per Phase A (paper trading validation). `semi_auto` è il prerequisito per Phase C (live). L'infrastruttura per leggere `system:mode` da Redis esiste già in `RedisStore.get_mode()` ma `run_execution_cycle` non la consulta ancora.

### 6d.4 Infrastructure Alerting (B2)

Tre eventi inviano un alert `CRITICAL` via `Notifier`:

| Evento | Messaggio |
|---|---|
| Redis irraggiungibile | "Redis non raggiungibile: \<exc\>" |
| Alpaca API irraggiungibile | "Alpaca API non raggiungibile: \<exc\>" |
| Drawdown cap scattato | "Drawdown cap attivato: daily drawdown X% ≥ 10%" |

Il `Notifier` è iniettato dal Celery task (`TelegramNotifier()`) e opzionale nei test.

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

### 8.4 Perché 2 LLM (non 3) per RegimeDetector?

**Decisione:** Solo 2 LLM per la classificazione del regime.

**Motivazione:**
- Il regime è una classificazione categorica (4 valori) non un segnale continuo
- Con 2 LLM, il tiebreak è deterministico: regime col moltiplicatore più basso (più conservativo)
- Con 3 LLM ci sarebbe 2-vs-1: più costoso, non aggiunge garanzie di sicurezza
- Il costo del terzo LLM non giustifica il margine di sicurezza extra (dato il fail-safe)

**Trade-off:** Con 2 LLM, se uno fallisce si usa solo l'altro con data_quality check.

---

### 8.5 Perché Alpaca direct e non QuantConnect per l'execution?

**Decisione:** `ExecutionWorker` chiama direttamente Alpaca SDK per paper trading (Phase A/B).

**Motivazione:**
- QC Lean richiede un account QC, file di dati storici e un ambiente Docker dedicato
- Per validare che la logica di esecuzione (kill-switch, stop-loss, drawdown cap) funzioni correttamente su infrastruttura reale, Alpaca paper è sufficiente e più semplice da debuggare
- Alpaca paper e live differiscono solo per l'URL (`paper-api.alpaca.markets` vs `api.alpaca.markets`) — il passaggio a live è una riga nel `.env`

**Trade-off:** QC Lean offre backtesting istituzionale multi-asset con dati storici completi. Resta il target per Phase C+ quando i volumi e la complessità lo giustificheranno.

---

### 8.6 Perché token SHA256(computed_at)[:8] per l'anti-replay?

**Decisione:** Token derivato dal timestamp della suggestion anziché da un UUID random.

**Motivazione:**
- Il token viene generato due volte (in `check_and_apply_weights` e `_compute_suggestion_token`) senza doversi passare lo stato
- Se viene calcolata una nuova suggestion, il token cambia automaticamente (computed_at cambia)
- Il poller ricomputa il token da Redis ogni volta → sempre in sync con la suggestion attuale
- 8 hex chars = 32 bit di entropia — sufficiente per prevenire replay in questo contesto

**Trade-off:** Il token è prevedibile se si conosce computed_at, ma l'attaccante dovrebbe anche essere nell'allowlist.

---

## 9. Appendix

### 9.1 Glossario

| Termine | Definizione |
|---------|-------------|
| **IC** | Information Coefficient: correlazione tra segnale e return |
| **Regime** | Classificazione macro del mercato: bull / sideways / bear / high_vol |
| **LOO ICIR** | Leave-One-Out IC Information Ratio: cross-validation per stabilità dei pesi |
| **Auto-apply** | Applicazione automatica di nuovi pesi ensemble quando tutti i guardrail passano |
| **Freeze** | Blocco auto-apply per guardrail fallito; richiede approvazione manuale |
| **Token anti-replay** | SHA256(computed_at)[:8] che identifica univocamente una suggestion |
| **Callback Query** | Evento Telegram generato dal tap su un bottone inline keyboard |
| **ICIR** | IC / IC std: risk-adjusted IC |
| **PSI** | Population Stability Index: drift detection |
| **CUSUM** | Cumulative Sum: change point detection |
| **HAC** | Heteroskedasticity and Autocorrelation Consistent |
| **LOO** | Leave-One-Out: cross-validation per weights |

### 9.2 Riferimenti

- [Design Spec (Fase 1)](docs/superpowers/specs/2026-05-03-trading-system-design.md)
- [Fase 1 Plan](docs/superpowers/plans/FASE1-START.md)
- [Multi-Asset News-Driven Design Spec (Fase 3)](docs/superpowers/specs/2026-05-13-multi-asset-news-driven-design.md)
- [Multi-Asset News-Driven Plan (Fase 3)](docs/superpowers/plans/2026-05-13-multi-asset-news-driven.md)
- [API Docs](docs/API.md)
