# LLM Trading System — Design Spec

**Data:** 2026-05-03  
**Aggiornato:** 2026-05-03 — post analisi multi-modello (8 modelli) + decisioni Q1–Q4 + Performance Worker  
**Status:** Approvato — pronto per implementazione

---

## Contesto e Obiettivo

Sistema di trading algoritmico multi-asset che integra Large Language Models come motore di generazione segnali **offline**, mai nel percorso critico di esecuzione degli ordini. Il sistema segue il paradigma "Alpha Miner" descritto in `docs/LLM Trading System Integration.docx`.

**Mercati:** Fase 1–2: equity USA + ETF. Fase 2+: crypto (BTC, ETH). Fase 3+: futures, forex  
**Orizzonte:** Dual-layer — intraday (1h) + swing trading (4h–1D)  
**Ciclo operativo:** Backtest → Paper Trading → Semi-automatico → Full-automatico  
**LLM:** Ensemble di 3 modelli via Claude CLI (`opus` + `qwen3.5:cloud` + `deepseek-v4-pro:cloud`), Consensus Gate aggregation  

---

## Architettura Generale

Il sistema è un **monolite modulare** — un singolo repository Python con moduli a responsabilità singola e interfacce pulite, progettato per essere decomposto in microservizi in futuro senza riscrittura.

```
[Data Ingestion Layer]  →  [LLM Pipeline]  →  [Signal Store]  →  [QuantConnect Lean]
   Connectors (RSS,           4 Celery           Redis (hot)        PythonData feed
   API, Email,                Workers            PostgreSQL         OnData() loop
   Telegram, ...)             asincroni          (cold/audit)       ordini / broker
                                    ↕                    ↑
                           FastAPI Control Plane         │ legge outcome reali
                           /api/signals · /api/admin     │
                           kill-switch · mode switch      │
                                                   [Performance Worker]
                                                   IC · weights · drift
                                                   post-mortem · report
```

**Principio invariante:** `OnData()` di QuantConnect non chiama mai l'LLM direttamente. Legge segnali pre-calcolati dal Signal Store come se fossero dati di mercato.

---

## Sezione 1 — Data Ingestion Layer

### Pattern Connector

Ogni fonte implementa un'unica interfaccia astratta:

```python
class NewsConnector(ABC):
    async def fetch() -> AsyncIterator[NewsItem]

@dataclass
class NewsItem:
    id: str
    source: str
    timestamp: datetime
    title: str
    body: str          # già sanitizzato
    url: str
    language: str      # "en" dopo traduzione
    asset_tags: list[str]
```

Aggiungere una fonte = implementare `NewsConnector` + aggiungere un blocco in `connectors.yaml`. Il core pipeline non cambia.

### Pipeline di normalizzazione (obbligatoria su ogni fonte)

```
raw text
  → unicode NFKC normalize        # mitiga omoglifi Unicode (adversarial news)
  → HTML/markdown strip
  → invisible chars removal       # zero-width spaces, hidden text
  → ticker NER homoglyph check    # verifica simboli azionari
  → max 4000 token truncation
  → translate to EN (se language != "en")  # DeepL/Google Translate API
  → deduplication: hash(title + body normalizzati) → skip se hash già visto nelle ultime 2h
  → staleness filter: if news.timestamp < now - 30min → skip
  → NewsItem
  → Redis queue
```

### Fonti — Fase 1 (gratuito)

| Connettore | Fonte | Frequenza | Layer target |
|---|---|---|---|
| `RSSConnector` | Reuters, AP, MarketWatch, CNBC, Il Sole 24 Ore | 60s poll | Sentiment |
| `NewsAPIConnector` | Aggregatore multi-fonte | 15 min (free tier: max 100 req/day) | Sentiment |
| `SECEdgarConnector` | Filing 8-K, 10-K, 10-Q | real-time EDGAR API | Sentiment swing + Alpha |
| `GDELTConnector` | Coverage globale open data | 15 min | Sentiment |
| `MacroConnector` | FRED API, ECB Data Portal | 1h | Regime |

### Fonti — Fase 2+ (plug-in futuri)

| Connettore | Accesso | Note |
|---|---|---|
| `EmailConnector` | IMAP / Gmail API | Legge newsletter premium (FT, WSJ, Bloomberg briefing) dalla casella dell'utente — aggira paywall senza violare ToS |
| `TelegramConnector` | Pyrogram / Bot API webhook | Canali finanziari curati; latenza quasi zero |
| `BloombergConnector` | B-PIPE API | Istituzionale |
| `RefinitivConnector` | Eikon API | Reuters premium |
| `SeekingAlphaConnector` | API ufficiale freemium | Earnings transcript |
| `XConnector` | Twitter API v2 | Account/listini finanziari |

---

## Sezione 2 — LLM Pipeline

### Astrazione provider

```python
class LLMClient(ABC):
    async def complete(prompt: str, response_schema: type[BaseModel]) -> BaseModel

# Implementazioni Fase 1: OpusClient · Qwen35Client · DeepseekClient (ensemble)
# Implementazioni Fase 3+: aggiungibili senza modifiche al business logic
```

### Worker 1 — Sentiment Worker

**Trigger:** Celery beat ogni 15 minuti (ore di mercato)  
**Input:** batch fino a 10 `NewsItem` dalla Redis queue  
**Prompt pattern:** Domain Knowledge Chain-of-Thought (DK-CoT)

```
Sistema: "Sei un analista azionario buy-side esperto..."
1. Role definition
2. Step-by-step reasoning su cash flow, competizione, profittabilità
3. Few-shot examples (2-3 casi analoghi con outcome noto)
4. Richiesta bull/bear case esplicito
5. Output forzato in JSON schema
```

**Ensemble Consensus Gate:**  
Lo stesso batch viene inviato in parallelo a 3 modelli via `asyncio.gather`. L'aggregatore applica il Consensus Gate:

```
models: [opus, qwen3.5:cloud, deepseek-v4-pro:cloud]
  ↓ asyncio.gather (latenza = max delle 3, non somma)
[SentimentResult_1, SentimentResult_2, SentimentResult_3]
  ↓ EnsembleAggregator
se std(polarity_i) < 0.25:           # modelli concordano
    score_final  = Σ(score_i × conf_i) / Σ(conf_i)
    conf_final   = mean(conf_i)
    ensemble     = True
altrimenti:                           # modelli divergono
    score_final  = 0.0, conf_final = 0.0
    → fallback FinBERT
    → log divergenza per analisi post-hoc
```

**Output:**
```python
class SentimentResult(BaseModel):
    symbol: str
    polarity: float              # [-1.0, +1.0]
    confidence: float            # [0.0, 1.0]
    score: float                 # polarity × confidence — range [-1.0, +1.0]
    reasoning: str               # dal modello con confidence massima
    source_ids: list[str]
    generated_at: datetime       # QC ignora se now - generated_at > 2× intervallo worker
    model_id: str                # "ensemble:opus+qwen3.5+deepseek" | "finbert"
    worker_version: str
    fallback_used: bool          # True se FinBERT ha sostituito l'ensemble
    worker_type: Literal["ensemble_llm", "single_llm", "finbert"]
```

**Fallback hierarchy:** Ensemble LLM → FinBERT locale (se divergenza o timeout) → ultimo segnale valido in cache → sizing conservativo fisso  
**Cache:** semantic cache su Redis — stessa notizia riformulata → risposta cached

---

### Worker 2 — Regime Detector

**Trigger:** Celery beat ogni ora  
**Input:** ultimi 7 giorni di `SentimentResult` aggregati per settore + dati macro (FRED: tassi, inflazione; VIX; ECB policy statements; headline news ultime 4h)

**Output:**
```python
class RegimeResult(BaseModel):
    label: Literal["risk_on", "risk_off", "high_vol", "trending", "ranging", "uncertain"]
    confidence: float
    key_factors: list[str]
    valid_until: datetime
    position_multiplier: float   # usato da QC per scalare il sizing
```

**Position multiplier per label:**

| Regime | Multiplier |
|---|---|
| `risk_on` | 1.0 |
| `trending` | 0.8 |
| `ranging` | 0.6 |
| `high_vol` | 0.5 |
| `risk_off` | 0.3 |
| `uncertain` | 0.3 |

**Guardrail ensemble:** 2 chiamate LLM parallele. Se le label divergono → `uncertain` automatico, log della divergenza per analisi post-hoc.

---

### Worker 3 — Alpha Miner

**Trigger:** Celery beat overnight (es. 02:00 UTC)  
**Modalità:** ciclo autonomo, max 5 iterazioni per sessione

**Ciclo:**
1. Genera ipotesi di strategia in linguaggio naturale
2. Traduce in codice Python per QuantConnect Lean
3. Lancia backtest via MCP Server (porta 3001)
4. Analizza risultati: Sharpe Ratio, Max Drawdown, Win Rate
5. Se risultati insufficienti → identifica componente fallimentare → itera
6. Se risultati soddisfacenti → archivia come `candidate`

**Output:**
```python
class AlphaCandidate(BaseModel):
    strategy_code: str
    hypothesis: str
    sharpe: float
    max_drawdown: float
    win_rate: float
    status: Literal["candidate", "approved", "rejected"]
    iterations: int
    backtest_period: tuple[date, date]
```

**Gate di promozione (tutti i criteri obbligatori):**
- `sharpe > 1.5`
- `max_drawdown < 0.12`
- `profit_factor > 1.5`
- `win_rate > 0` su almeno 100 trade
- **Walk-forward validation obbligatoria:** ultimi 6 mesi esclusi dall'ottimizzazione come out-of-sample

Se tutti i criteri sono soddisfatti → status `candidate` → notifica Telegram con summary → approvazione manuale → status `approved` → deploy in semi-auto.

**Sicurezza codice generato:** il backtest gira nell'ambiente isolato di QuantConnect Lean (container .NET); il codice Python generato non può fare syscall arbitrarie al di fuori dell'API QC.

---

### Worker 4 — Performance Worker

**Trigger:** Celery beat giornaliero (03:00 UTC, report IC) + settimanale (lunedì 04:00 UTC, weight update) + event-driven su ogni loss > 3%  
**Input:** `sentiment_signals`, `audit_log`, prezzi storici via `yfinance` (Fase 1–2) / QC API (Fase 3+)  
**Scopo:** chiudere il loop di feedback — misurare se i segnali LLM predicono correttamente i rendimenti, aggiustare i pesi dell'ensemble, rilevare drift dei modelli, generare post-mortem automatici.

#### Principio di funzionamento

```
T=0:  SentimentResult generato (score=-0.72, symbol=AAPL, confidence=0.85)
T=4h: prezzo AAPL: -1.8%   ← forward_return recuperato da yfinance
      IC contribution: corr(score=-0.72, return=-1.8%) → positivo, segnale corretto

Accumulato su N segnali (minimo 300 — B1):
  # IC composito — B4 (più robusto di Spearman solo)
  spearman_ic  = spearmanr(scores, returns).correlation
  weighted_hr  = mean(sign(scores)==sign(returns), weights=confidences)
  brier        = mean((confidences - (returns > 0)) ** 2)
  IC_composite = 0.5 * spearman_ic + 0.3 * weighted_hr + 0.2 * (1 - brier)

  ICIR = IC_mean / IC_std   ← stabilità nel tempo
  # Correzione Newey-West per autocorrelazione dei rendimenti
```

**Finestre di misurazione:**

| Strategia | Finestra forward return | Minimo campioni (B1) |
|---|---|---|
| Intraday 1h | 4h | 300 segnali (~6 giorni) |
| Swing 4h | 24h | 200 segnali (~4 giorni) |
| Swing 1D | 72h | 150 segnali (~3 giorni) |

#### Output schema

```python
class PerformanceReport(BaseModel):
    period_start: date
    period_end: date
    overall_ic: float           # IC aggregato su tutti i modelli
    icir: float                 # IC / std(IC) — stabilità
    hit_rate: float             # % segnali con segno corretto
    model_ic: dict[str, float]  # IC per modello: {"opus": 0.18, "qwen3.5": 0.14, ...}
    model_icir: dict[str, float]
    recommended_weights: dict[str, float]   # pesi suggeriti per l'ensemble
    weight_change_applied: bool             # True se auto-applicato
    threshold_analysis: dict[str, float]   # IC per range score: {"0.2-0.3": 0.05, "0.3-0.4": 0.12, ...}
    threshold_suggestion: float | None     # suggerisce nuova soglia se gain > 15%
    drift_alerts: list[str]               # modelli con distribuzione anomala
    post_mortems: list[PostMortem]
    generated_at: datetime
    report_version: str
```

Post-mortem generato se soddisfatta una delle seguenti condizioni (B5):
- `loss_pct >= 0.03` (perdita ≥ 3%)
- `loss_pct >= 0.02 AND (signal_score >= 0.5 OR ensemble_std >= 0.3)` — loss minore ma segnale era convinto o ensemble divergente

```python
def should_trigger_postmortem(loss_pct: float, score: float, std: float) -> bool:
    return loss_pct >= 0.03 or (loss_pct >= 0.02 and (abs(score) >= 0.5 or std >= 0.3))

class PostMortem(BaseModel):
    trade_id: UUID                  # riferimento audit_log
    symbol: str
    loss_pct: float
    signal_score: float
    signal_confidence: float
    ensemble_std: float             # divergenza ensemble al momento del segnale
    regime_at_trade: str
    reasoning_summary: str          # primi 200 char del reasoning LLM
    diagnosis: str                  # classificazione automatica causa perdita
    # diagnosis ∈ 10 categorie (B5 — minimax):
    #   "low_confidence_passed"         — confidence < soglia ma segnale usato
    #   "ensemble_divergence_ignored"   — std ensemble alta, segnale usato comunque
    #   "regime_mismatch"               — regime incompatibile con direzione segnale
    #   "news_staleness"                — notizia vecchia al momento del trade
    #   "market_gap"                    — evento overnight non anticipabile
    #   "stop_too_tight"                — stop-loss colpito da normale volatilità
    #   "correlated_portfolio_loss"     — perdita da contagio cross-asset
    #   "model_drift_active"            — drift alert attivo al momento del trade
    #   "threshold_boundary"            — score vicino alla soglia 0.3 (bassa convizione)
    #   "unknown"                       — nessuna causa identificabile
```

#### Aggiustamento pesi ensemble — settimanale (PW-Q1)

```python
# Update ogni lunedì su rolling window 30 giorni (~350 segnali)
# B3: Leave-one-out IC per correggere chicken-and-egg bias
def compute_purified_icir(model_signals, forward_returns, current_weights):
    purified = {}
    for target in model_signals:
        others = [m for m in model_signals if m != target]
        # IC calcolato su ensemble che ESCLUDE il modello target
        loo_scores = [
            sum(model_signals[m][i] * current_weights[m] for m in others)
            for i in range(len(model_signals[target]))
        ]
        ic_series = [spearmanr(loo_scores[w:w+30], forward_returns[w:w+30])[0]
                     for w in range(0, len(loo_scores)-30, 5)]
        purified[target] = mean(ic_series) / (std(ic_series) + 1e-8)  # ICIR
    return purified

def compute_new_weights(purified_icir, current_weights, alpha=0.25):
    # Smoothing α=0.25: nuovi pesi = 75% vecchi + 25% nuovi (PW-Q1)
    raw = {m: max(0.0, icir) for m, icir in purified_icir.items()}
    total = sum(raw.values()) or 1.0
    target = {m: v / total for m, v in raw.items()}

    # Smoothing
    blended = {m: (1 - alpha) * current_weights[m] + alpha * target[m] for m in target}

    # Guardrail: floor 10%, cap 70% (PW-Q2), max delta 10% per update
    clipped = {m: max(0.10, min(0.70, w)) for m, w in blended.items()}
    clipped = {m: max(current_weights[m]-0.10, min(current_weights[m]+0.10, w))
               for m, w in clipped.items()}

    total = sum(clipped.values())
    return {m: w / total for m, w in clipped.items()}

# Auto-apply se: N_campioni >= 300, ICIR_overall > 0.1, nessun circuit breaker attivo
# Altrimenti: report con raccomandazione → approvazione Telegram
```

#### Drift Detection

Due baseline parallele confrontate ogni domenica (04:30 UTC):

- **Baseline primaria (90 gg):** quasi mono-regime — rileva drift operativo recente
- **Baseline secondaria (12 mesi):** strutturale — rileva cambiamenti sistemici del modello

Alert livello giallo se solo la baseline primaria segnala drift. Alert livello rosso solo se entrambe concordano — riduce falsi positivi da cambio regime di mercato.

Metrica: **PSI (Population Stability Index)** + **CUSUM** (cumulativo su 7 giorni):

```python
def compute_psi(baseline: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
    """PSI = Σ (expected_i - actual_i) * ln(expected_i / actual_i)"""
    edges = np.linspace(min(baseline.min(), current.min()),
                        max(baseline.max(), current.max()), bins + 1)
    exp = np.histogram(baseline, edges)[0] / len(baseline) + 1e-6
    act = np.histogram(current,  edges)[0] / len(current)  + 1e-6
    return float(np.sum((exp - act) * np.log(exp / act)))

# Soglie PSI:
#   PSI < 0.10  → distribuzione stabile
#   PSI 0.10–0.25 → GIALLO: drift moderato, monitorare
#   PSI > 0.25  → ROSSO: drift severo, richiedere revisione

# CUSUM: accumula deviazioni dalla media baseline su finestra 7 gg
# Se CUSUM supera threshold fisso → conferma alert (second signal)

# Livello GIALLO = PSI_90gg > 0.10  (indipendente da 12 mesi)
# Livello ROSSO  = PSI_90gg > 0.25 AND PSI_12m > 0.10  (entrambe concordano)

# Cause tipiche da loggare nel drift_events:
# - Modello aggiornato dal provider (cambia output distribution)
# - Cambio di regime di mercato (il modello risponde diversamente)
# - Degradazione qualità news source (input corrotto)
```

**Circuit breaker — freeze auto-update pesi:**

```python
# HARD (bloccano l'aggiornamento automatico dei pesi + alert critico):
HARD_BREAKERS = {
    "vix_spike":        lambda ctx: ctx.vix > 40 or ctx.vix_1d_change > 0.30,
    "system_drawdown":  lambda ctx: ctx.portfolio_drawdown > 0.05,
    "ic_negative_run":  lambda ctx: ctx.consecutive_negative_ic_days >= 5,
    # gap asset > 5% → escluso dal calcolo IC (non blocca il sistema)
    "asset_gap":        lambda ctx: False,  # handled in IC calc, not here
}

# SOFT (appaiono nel report Telegram come avviso, non bloccano):
SOFT_WARNINGS = {
    "earnings_concentration": lambda ctx: ctx.portfolio_earnings_pct > 0.50,
    "cross_asset_corr":       lambda ctx: ctx.cross_asset_correlation > 0.90,
}

def should_freeze_weight_update(ctx) -> tuple[bool, str]:
    for name, check in HARD_BREAKERS.items():
        if check(ctx):
            return True, name
    return False, ""

# N.B.: gap apertura > 5% su singolo asset → quel giorno escluso dal
# calcolo IC di quell'asset, ma non blocca il sistema né congela i pesi.
```

#### Threshold Optimizer

Calcola IC per 5 bucket di score: `[0.1–0.2)`, `[0.2–0.3)`, `[0.3–0.4)`, `[0.4–0.6)`, `[0.6–1.0]`. Se il bucket `[0.35–1.0]` ha IC sistematicamente > 15% superiore al bucket `[0.3–1.0]`, genera una suggestion. **Non auto-applica mai la soglia** — richiede approvazione Telegram + 2 settimane di A/B test con la nuova soglia prima del deploy.

#### Nuove tabelle PostgreSQL

```sql
CREATE TABLE performance_metrics (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    period_start    DATE NOT NULL,
    period_end      DATE NOT NULL,
    model_id        VARCHAR(100),        -- NULL = aggregato ensemble
    symbol          VARCHAR(20),         -- NULL = tutti i simboli
    regime          regime_label_enum,   -- NULL = tutti i regimi
    ic              FLOAT,
    icir            FLOAT,
    hit_rate        FLOAT,
    sample_count    INTEGER,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_perf_period ON performance_metrics (period_end DESC, model_id);

CREATE TABLE model_weights (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    effective_from  TIMESTAMPTZ NOT NULL,
    model_id        VARCHAR(100) NOT NULL,
    weight          FLOAT NOT NULL CHECK (weight BETWEEN 0.0 AND 1.0),
    icir_basis      FLOAT,              -- ICIR usato per calcolare il peso
    auto_applied    BOOLEAN NOT NULL DEFAULT FALSE,
    approved_by     VARCHAR(50),        -- 'auto' | 'telegram:user_id'
    notes           TEXT
);
CREATE INDEX idx_weights_model_time ON model_weights (model_id, effective_from DESC);
```

#### Telegram report giornaliero

Ogni mattina (04:00 UTC), dopo l'elaborazione, invia:

```
📊 Performance Report — 2026-05-03
IC composito (30gg): 0.14  |  ICIR: 0.82  |  Hit Rate: 58.3%

Modelli:
  opus            IC=0.18 ↑  peso=42%
  qwen3.5         IC=0.13 →  peso=33%
  deepseek-v4     IC=0.09 ↓  peso=25%

⚠️ Drift GIALLO: deepseek-v4 (PSI_90gg=0.13 — solo baseline primaria)
⚠️ Soft warning: earnings concentration 54% (>50%)
💡 Threshold suggestion: 0.33 (+11% IC) — in attesa approvazione

Post-mortem: 2 loss ieri → dettaglio in /api/performance/2026-05-03
```

**Gate di sicurezza (hard breaker):** se `overall_ic < 0` per 5 giorni consecutivi → freeze auto-update pesi + alert critico + raccomandazione di sospendere il trading e tornare a FinBERT-only fino a diagnosi.

---

## Sezione 3 — Signal Store

### Redis (hot cache)

```
signal:{symbol}:sentiment   TTL 4h   → {score, confidence, fallback_used, ts}
signal:global:regime        TTL 2h   → {label, multiplier, ts}
signal:{symbol}:latest      TTL 4h   → snapshot merged (sentiment + regime) per QC
ensemble:divergence:log     TTL 24h  → lista divergenze per calibrazione
```

### PostgreSQL (cold storage / audit trail)

Tabelle separate per sentiment e regime — tipi di dato distinti, frequenze di scrittura diverse (sentiment 200/h, regime 1/h), query patterns non sovrapponibili.

```sql
-- ENUMs (B2 — prevengono inconsistenza dati)
CREATE TYPE worker_type_enum AS ENUM ('ensemble_llm', 'single_llm', 'finbert');
CREATE TYPE regime_label_enum AS ENUM ('risk_on', 'risk_off', 'high_vol', 'trending', 'ranging', 'uncertain');
CREATE TYPE audit_action_enum AS ENUM (
    'order_placed', 'order_rejected', 'mode_changed',
    'killswitch', 'extreme_score_approval', 'extreme_score_rejected',
    'worker_degraded', 'budget_alert'
);

-- Tabella segnali sentiment (B1 — separata da regime)
CREATE TABLE sentiment_signals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol          VARCHAR(20) NOT NULL,
    generated_at    TIMESTAMPTZ NOT NULL,
    polarity        FLOAT NOT NULL CHECK (polarity BETWEEN -1.0 AND 1.0),
    confidence      FLOAT NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
    score           FLOAT NOT NULL CHECK (score BETWEEN -1.0 AND 1.0),
    source_ids      TEXT[],
    reasoning       TEXT,
    worker_type     worker_type_enum NOT NULL,
    model_id        VARCHAR(100) NOT NULL,
    worker_version  VARCHAR(20) NOT NULL,
    fallback_used   BOOLEAN NOT NULL DEFAULT FALSE
);
-- BRIN index per range query backtest su time-series (I5)
CREATE INDEX idx_sentiment_symbol_time ON sentiment_signals (symbol, generated_at DESC);
CREATE INDEX idx_sentiment_time_brin ON sentiment_signals USING BRIN (generated_at);
-- Partial index per analisi fallback (I6)
CREATE INDEX idx_sentiment_fallback ON sentiment_signals (generated_at) WHERE fallback_used = TRUE;

-- Tabella segnali regime (B1 — separata)
CREATE TABLE regime_signals (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    generated_at        TIMESTAMPTZ NOT NULL,
    label               regime_label_enum NOT NULL,
    confidence          FLOAT NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
    key_factors         TEXT[],
    valid_until         TIMESTAMPTZ NOT NULL,
    position_multiplier FLOAT NOT NULL,
    model_id            VARCHAR(100) NOT NULL,
    worker_version      VARCHAR(20) NOT NULL
);
CREATE INDEX idx_regime_time ON regime_signals (generated_at DESC);
```

Ogni segnale porta `model_id` e `worker_version` per debug post-mortem in caso di perdite.

### Audit Log (tabella separata)

```sql
CREATE TABLE audit_log (
    id            UUID PRIMARY KEY,
    timestamp     TIMESTAMPTZ NOT NULL,
    action        VARCHAR(50),     -- 'order_placed', 'order_rejected', 'mode_changed',
                                   -- 'killswitch', 'extreme_score_approval', ecc.
    symbol        VARCHAR(20),
    quantity      FLOAT,
    price         FLOAT,
    signal_score  FLOAT,
    signal_id     UUID REFERENCES sentiment_signals(id),   -- nullable (alcuni eventi non hanno segnale)
    guardrail     VARCHAR(50),
    approved_by   VARCHAR(50),     -- 'auto' | 'telegram:user_id'
    reason        TEXT,
    action        audit_action_enum NOT NULL               -- B2: ENUM, non VARCHAR libero
);
```

Ogni ordine piazzato, rifiutato o approvato manualmente deve produrre una riga in `audit_log`. Essenziale per debugging post-mortem e tracciabilità delle decisioni.

### FastAPI Signal Bridge

```
GET  /api/signals/{symbol}      # live: Redis
GET  /api/signals/history       # backtest: PostgreSQL
GET  /api/regime                # regime corrente + multiplier
POST /api/admin/mode            # body: {"mode": "backtest|paper|semi_auto|full_auto"}
POST /api/admin/killswitch      # stop immediato
GET  /api/health                # health check tutti i componenti
GET  /api/performance/latest   # ultimo PerformanceReport
GET  /api/performance/{date}   # report specifico con post-mortems
GET  /api/weights/current      # pesi ensemble correnti
POST /api/weights/approve      # approva aggiornamento pesi suggerito
```

**Autenticazione:** tutti gli endpoint `/api/admin/*` richiedono header `X-API-Key`. Implementazione: `Depends(api_key_header)` FastAPI. La chiave è letta da variabile d'ambiente `ADMIN_API_KEY`.

**Gestione credenziali:** tutte le API key (LLM provider, broker, Telegram, news, traduzione) sono caricate da file `.env` (non committato, escluso da `.gitignore`). Fase 3+: migrazione a HashiCorp Vault o AWS Secrets Manager.

---

## Sezione 4 — QuantConnect Lean Integration

### Custom Data Feed

```python
class LLMSignalData(PythonData):
    def GetSource(self, config, date, isLive):
        if isLive:
            return SubscriptionDataSource(
                f"http://localhost:8000/api/signals/{config.Symbol}",
                SubscriptionTransportMedium.Rest
            )
        return SubscriptionDataSource(
            f"http://localhost:8000/api/signals/history?symbol={config.Symbol}&date={date}",
            SubscriptionTransportMedium.Rest
        )

    def Reader(self, config, line, date, isLive):
        data = json.loads(line)
        signal = LLMSignalData()
        signal.Symbol = config.Symbol
        signal.Time = datetime.fromisoformat(data["generated_at"])
        signal.Value = data["score"]
        signal["sentiment_score"] = data["score"]
        signal["regime_multiplier"] = data.get("regime_multiplier", 1.0)
        signal["confidence"] = data["confidence"]
        signal["generated_at"] = data["generated_at"]
        return signal

    # Freshness check in OnData():
    # age = (self.Time - signal.Time).total_seconds() / 60
    # if age > SIGNAL_MAX_AGE_MIN:   # default: 30 min (2× worker interval)
    #     → skip segnale, usa sizing conservativo
```

### Dual-Layer Strategy

**Intraday Strategy** (1h): momentum + sentiment score. Entry quando `sentiment_score > 0.3` e momentum confermato. Timeframe minimo: 1h. I timeframe 5m/15m sono esclusi — il worker a 15 min renderebbe il segnale sempre stale su barre più corte. Fast path sub-minuto valutabile in Fase 3 se giustificato da backtest.

**Swing Strategy** (4h–1D): regime-aware positioning. Position size = `base_size × regime.position_multiplier`. Entry su breakout + sentiment positivo. Timeframe: 4h, 1D.

**Risk Manager (condiviso):**
- Max position singola: 10% del portafoglio
- Stop-loss: 2% per trade intraday, 5% swing
- Max ordini/minuto: 10 (rate limiting)
- Score estremi (`|score| > 0.8`): in `semi_auto` → approvazione manuale Telegram obbligatoria; in `full_auto` → size ×0.5 automatico

### Modalità operative

La modalità è letta da `/api/admin/mode` a ogni generazione d'ordine:

| Modalità | Broker | Esecuzione |
|---|---|---|
| `backtest` | QC simulato | Automatica su dati storici |
| `paper` | Paper broker (Alpaca/IB sim) | Automatica, ordini finti |
| `semi_auto` | Broker reale | Notifica Telegram → approvazione umana entro 5 min → esecuzione; timeout → scarta |
| `full_auto` | Broker reale | Esecuzione diretta |

---

## Sezione 5 — Guardrails & Error Handling

### Livello 1 — Sanitizzazione input

Implementata nel modulo dedicato `src/text/` (B4 — modulo esplicito, non funzione isolata).  
Obbligatoria su ogni testo prima di costruire un prompt:

```python
# src/text/sanitizer.py
def sanitize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = bleach.clean(text, strip=True)
    text = re.sub(INVISIBLE_CHARS_PATTERN, "", text)
    text = text[:MAX_CHARS]            # MAX_CHARS configurabile (es. 16000 chars ≈ 4000 token)
    verify_ticker_ascii(text)          # rileva omoglifi su simboli
    return text
```

### Livello 2 — Guardrail LLM

| Condizione | Azione |
|---|---|
| Output non parsabile da Pydantic | Retry (max 2), poi fallback |
| `confidence < 0.4` (singolo modello) | Quel modello escluso dalla media ensemble |
| `std(polarity_i) > 0.25` tra i 3 modelli | Consensus Gate fallback → FinBERT, log divergenza |
| 3 consensus fallback consecutivi | Alert Telegram + QC sizing ×0.5 (modalità degradata) |
| Regime ensemble divergente | `label = "uncertain"`, `multiplier = 0.3` |
| Timeout LLM > 10s (singolo modello) | Modello escluso dal batch; se tutti timeout → FinBERT |
| Budget giornaliero LLM esaurito | Blocco chiamate + fallback completo FinBERT + alert |

**Fallback hierarchy:** Ensemble LLM (3 modelli) → FinBERT locale (se divergenza/timeout) → ultimo segnale valido in cache → sizing conservativo fisso.

### Livello 3 — Circuit Breaker Trading

Regole hard-coded in QuantConnect, non modificabili via API:

| Soglia | Azione |
|---|---|
| Daily drawdown > 5% | Pausa nuove posizioni |
| Daily drawdown > 10% | Stop ordini + alert |
| Posizione singola > 10% ptf | Ordine rifiutato |
| Ordini/min > 10 | Rate limiting |
| `\|score\| > 0.8` in `semi_auto` | Approvazione manuale Telegram obbligatoria (timeout 5 min → no trade) |
| `\|score\| > 0.8` in `full_auto` | Size ×0.5 automatico |

### Kill-switch

`POST /api/admin/killswitch` esegue in sequenza:
1. `mode = "halted"`
2. **Redis key `killswitch_active = 1`** — QC la legge direttamente a ogni tick (canale indipendente da FastAPI)
3. QC: cancella tutti gli ordini pending
4. QC: chiude tutte le posizioni aperte a mercato
5. Celery workers: stop accettazione nuovi job
6. Telegram: notifica con stato portafoglio al momento dello stop

Il punto 2 garantisce che il kill-switch funzioni anche se FastAPI è irraggiungibile — QC controlla la chiave Redis in `OnData()` prima di qualsiasi altra logica.

Riattivazione: cancellare la chiave `killswitch_active` + `POST /api/admin/mode {"mode": "paper"}` manuale.

### Monitoring & Alerting

**Fase 1 — Logging strutturato + Telegram:**

Alert automatici su:
- Segnale stale > 2× intervallo atteso
- Budget LLM > 80% consumato
- Drawdown giornaliero > 3%
- Worker down > 5 minuti
- Alpha candidate trovato (gate completo superato: Sharpe > 1.5, walk-forward ok)
- Kill-switch attivato

**Fase 2 — Prometheus + Grafana** (aggiunto quando il volume lo richiede, stessa codebase).

---

## Stack Tecnologico

| Componente | Tecnologia |
|---|---|
| Backend async | Python 3.11+, FastAPI, Celery, Redis |
| Database | PostgreSQL (segnali + audit), Redis (hot cache) |
| LLM provider | Ensemble: `opus` + `qwen3.5:cloud` + `deepseek-v4-pro:cloud` via Claude CLI (Consensus Gate) |
| LLM fallback | FinBERT (HuggingFace, locale, CPU) |
| Execution engine | QuantConnect Lean (Python interface) |
| Alpha R&D | QC MCP Server (Docker, porta 3001) |
| Traduzione testi | DeepL API / Google Translate API |
| Sanitizzazione | `unicodedata`, `bleach`, `re` |
| Schema validation | Pydantic v2 |
| Broker live | Interactive Brokers / Alpaca (configurabile) |
| Notifiche | Telegram Bot API |
| Monitoring | Structured logging (JSON) → file + stdout; Prometheus (fase 2) |
| Config | YAML (`connectors.yaml`, `workers.yaml`, `trading.yaml`) |

---

## Fasi di Sviluppo

### Fase 1 — Fondamenta (backtest, equity/ETF only)
- Setup repo, struttura moduli con `src/text/` esplicito (B4), Docker Compose
- File `.env` + `python-dotenv` per tutte le credenziali (non committato)
- Autenticazione `X-API-Key` su tutti gli endpoint `/api/admin/*` (B5)
- Implementare `NewsConnector` base + `RSSConnector` + `SECEdgarConnector` + `GDELTConnector`
- Implementare pipeline sanitizzazione in `src/text/sanitizer.py` (NFKC + dedup hash + staleness filter)
- Implementare `LLMClient` ABC + 3 client: `OpusClient`, `Qwen35Client`, `DeepseekClient`
- Implementare `EnsembleAggregator` con Consensus Gate (`std(polarity) < 0.25`)
- Implementare `SentimentWorker` con DK-CoT + ensemble + FinBERT fallback (mapping entropico, B3)
- Implementare Signal Store (Redis + PostgreSQL tabelle separate B1 + ENUMs B2) + tabella `audit_log`
- Implementare `LLMSignalData` con `Reader()` + freshness check in QC
- Kill-switch via Redis key `killswitch_active`
- Telegram bot base: solo alert (drawdown, worker down, budget, alpha candidate, kill-switch) — Q4
- Prima strategia intraday 1h in QC + backtest su dati storici equity USA (survivorship bias-free)
- **Pre-Fase 2:** pre-computare segnali su GDELT 2022–2024, eseguire A/B test sentiment vs no-sentiment — Q1
- Implementare `PerformanceWorker` base: IC tracker + daily report Telegram (tabelle `performance_metrics`, `model_weights`)

### Fase 2 — Regime + Alpha + Crypto (paper trading)
- **Gate obbligatorio:** A/B test GDELT completato con delta Sharpe ≥ 0.1 (o IR positivo su OOS 2024)
- `PerformanceWorker`: attivare ensemble weight adjuster (auto-apply con guardrail) + drift detector
- Implementare `RegimeDetector` con ensemble (2 chiamate parallele)
- Implementare `AlphaMiner` con loop R&D + MCP Server + gate rinforzato (Sharpe > 1.5, walk-forward)
- Aggiungere `RegimeResult` nel Signal Store (tabella `regime_signals`)
- Swing Strategy in QC con `position_multiplier`
- **Aggiungere crypto:** `BinanceConnector` + parametri rischio per asset class (stop-loss 6–10% BTC) — Q2
- Risk Manager: leggere asset class dal ticker, applicare parametri da sezione dedicata in `trading.yaml`
- Deploy paper trading su broker simulato (≥ 30 giorni prima di passare a semi-auto)
- Idempotency key sui Celery task per evitare duplicati su retry

### Fase 3 — Semi-auto (live con supervisione)
- Integrazione broker reale (IB o Alpaca)
- **Telegram approval flow** (Q4): command handler, timeout 5 min, `/killswitch` command, audit_log integration
- Implementare modalità `semi_auto` con approval flow Telegram per score > 0.8
- Circuit breaker completo + kill-switch
- `EmailConnector` + `TelegramConnector` come fonti aggiuntive
- Tuning soglie Sharpe/Drawdown per gate Alpha Miner
- `PerformanceWorker`: threshold optimizer attivo (suggestion + A/B test 2 settimane prima di deploy)

### Fase 4 — Full-auto
- Transizione a `full_auto` dopo periodo di validazione semi-auto
- Prometheus + Grafana dashboard
- Aggiunta provider LLM aggiuntivi (OpenAI, Gemini) per ensemble Regime
- Connettori a pagamento (Refinitiv, Seeking Alpha) se ROI lo giustifica
