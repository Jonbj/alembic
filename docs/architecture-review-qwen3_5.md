# Architettura LLM Trading System — Review Critica

**Data:** 2026-05-03
**Reviewer:** Claude Code (AI Software Architect)
**Documenti analizzati:**
- `docs/LLM Trading System Integration.docx` (specifiche complete in italiano)
- `docs/superpowers/specs/2026-05-03-trading-system-design.md` (design spec implementativa)
- `CLAUDE.md` (istruzioni progetto)

---

## 1. Panoramica del Sistema

### Scopo
Sistema di trading algoritmico multi-asset che utilizza Large Language Models come motore **offline** di generazione segnali e strategie, mai nel percorso critico di esecuzione ordini.

### Tipo di Trading
- **Paradigma:** Alpha Miner + Event-Driven
- **Orizzonti:** Dual-layer — intraday (5m–1h) + swing trading (4h–1D)
- **Mercati:** Multi-asset — equity, ETF, crypto, futures, forex
- **Ciclo operativo:** Backtest → Paper Trading → Semi-automatico → Full-automatico

### Flusso Dati
```
[Fonti Esterne] → [Data Ingestion] → [LLM Pipeline] → [Signal Store] → [QuantConnect Lean]
     ↓                  ↓                   ↓              ↓              ↓
  RSS, API,        Connettori        3 Worker         Redis (hot)    Execution engine
  Email, TG        normalizzazione   Celery           PostgreSQL     OnData() loop
```

**Valutazione:** L'architettura è ben concepita. Il disaccoppiamento tra LLM (offline) ed execution engine (deterministico) è il pattern corretto per sistemi di produzione.

---

## 2. Architettura

### Componenti Principali

| Componente | Responsabilità | Tecnologia |
|---|---|---|
| **Data Ingestion Layer** | Connettori normalizzati per fonti multiple | Python ABC + YAML config |
| **LLM Pipeline** | 3 worker Celery asincroni | Sentiment, Regime, Alpha Miner |
| **Signal Store** | Hot cache + audit trail | Redis (4h TTL) + PostgreSQL |
| **Execution Engine** | Lettura segnali + esecuzione ordini | QuantConnect Lean |
| **Control Plane** | API administration + kill-switch | FastAPI |
| **Notification** | Alert e approvazioni manuali | Telegram Bot |

### Pattern Architetturali

1. **Monolite Modulare** — singolo repository Python con moduli a responsabilità singola
2. **Event-Driven** — ciclo di elaborazione basato su eventi di mercato
3. **Circuit Breaker** — fallback deterministici su fallimento LLM
4. **Provider Agnostic** — astrazione LLM client per swap senza modifiche core

### Diagramma Logico (descrizione verbale)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         DATA INGESTION LAYER                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │   RSS    │ │ NewsAPI  │ │ SEC EDGAR│ │  GDELT   │ │  Macro   │      │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘      │
│       └────────────┴────────────┴────────────┴────────────┘            │
│                              │                                          │
│                    [Normalization Pipeline]                             │
│                    Unicode NFKC → Strip → Translate                     │
└────────────────────────────────┼────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           LLM PIPELINE (Celery)                         │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐      │
│  │ Sentiment Worker │  │ Regime Detector  │  │   Alpha Miner    │      │
│  │   (15 min)       │  │    (1 hour)      │  │  (overnight)     │      │
│  │ DK-CoT Prompt    │  │ Ensemble 2x LLM  │  │ R&D loop 5 iter  │      │
│  │ FinBERT fallback │  │ Divergence=unc.  │  │ MCP Server QC    │      │
│  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘      │
│           │                     │                     │                 │
│           └─────────────────────┴─────────────────────┘                 │
│                              │                                          │
│                    [Signal Store Write]                                 │
└────────────────────────────────┼────────────────────────────────────────┘
                                 │
                ┌────────────────┴────────────────┐
                ▼                                 ▼
┌───────────────────────────┐     ┌───────────────────────────┐
│      REDIS (HOT)          │     │    POSTGRES (COLD)        │
│  signal:{sym}:sentiment   │     │  signals (audit table)    │
│  signal:global:regime     │     │  model_id, worker_version │
│  TTL 4h                   │     │  reasoning (TEXT)         │
└─────────────┬─────────────┘     └─────────────┬─────────────┘
              │                                 │
              └────────────────┬────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      QUANTCONNECT LEAN ENGINE                           │
│  ┌─────────────────────────────────────────────────────────────┐       │
│  │  LLMSignalData (Custom PythonData)                          │       │
│  │  - GetSource() → HTTP localhost:8000/api/signals/{symbol}   │       │
│  │  - IsLive = true/false → routing dinamico                   │       │
│  └─────────────────────────────────────────────────────────────┘       │
│  ┌──────────────────┐              ┌──────────────────┐               │
│  │ Intraday Strat   │              │  Swing Strat     │               │
│  │ 5m, 15m, 1h      │              │  4h, 1D          │               │
│  │ sentiment > 0.3  │              │  regime-aware    │               │
│  └──────────────────┘              └──────────────────┘               │
│                    │                    │                              │
│                    └────────┬───────────┘                              │
│                             ▼                                          │
│  ┌─────────────────────────────────────────────────────────────┐       │
│  │              RISK MANAGER (hard-coded)                      │       │
│  │  - Max position: 10%                                        │       │
│  │  - Stop-loss: 2% (intraday), 5% (swing)                     │       │
│  │  - Rate limit: 10 ordini/min                                │       │
│  │  - Score estremi: size ×0.5                                 │       │
│  └─────────────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────────────┘
```

**Valutazione:** Architettura solida con separazione chiara delle responsabilità. Il monolite modulare è appropriato per la fase iniziale; la decomposizione in microservizi è pianificabile senza riscrittura.

---

## 3. Gestione dei Dati

### Fonti Dati

| Fonte | Tipo | Frequenza | Layer |
|---|---|---|---|
| Reuters, AP, MarketWatch | RSS | 60s poll | Sentiment |
| NewsAPI | Aggregatore | 5 min | Sentiment |
| SEC EDGAR | Filing 8-K, 10-K, 10-Q | real-time API | Sentiment + Alpha |
| GDELT | Coverage globale | 15 min | Sentiment |
| FRED, ECB | Dati macro | 1h | Regime |

**Fase 2+ (premium):** Email (newsletter FT/WSJ), Telegram canali, Bloomberg B-PIPE, Refinitiv Eikon, SeekingAlpha, Twitter API.

### Pipeline di Normalizzazione

```python
raw text
  → unicode NFKC normalize        # omoglifi Unicode
  → HTML/markdown strip
  → invisible chars removal       # zero-width spaces
  → ticker NER homoglyph check    # simboli ASCII-safe
  → max 4000 token truncation
  → translate to EN (se necessario)
  → NewsItem → Redis queue
```

### Valutazione Critica

**Punti di forza:**
- Sanitizzazione NFKC + invisible char removal è **essenziale** (vedi sezione adversarial news)
- Traduzione obbligatoria a inglese normalizza l'input per LLM
- Truncation a 4000 token previene costi eccessivi

**Rischi identificati:**
1. **Assunzione:** La traduzione automatica (DeepL/Google) non introduce bias semantici — **non validato**
2. **Gap:** Nessun controllo di qualità post-traduzione (es. confronto sentiment pre/post)
3. **Rischio operativo:** Paywall scraping via Email/Telegram può violare ToS di editori
4. **Latenza:** Polling RSS a 60s può perdere segnali intraday veloci

**Raccomandazione:** Aggiungere webhook per fonti critiche (SEC EDGAR ha push notifications) invece di polling.

---

## 4. Logica di Trading

### Strategie

**Intraday (5m–1h):**
- Entry: `sentiment_score > 0.3` + momentum confermato
- Timeframe: 5m, 15m, 1h

**Swing (4h–1D):**
- Entry: breakout + sentiment positivo
- Position sizing: `base_size × regime.position_multiplier`
- Timeframe: 4h, 1D

### Risk Manager (condiviso)

| Regola | Soglia | Azione |
|---|---|---|
| Max position singola | 10% portafoglio | Ordine rifiutato |
| Stop-loss intraday | 2% per trade | Hard stop |
| Stop-loss swing | 5% per trade | Hard stop |
| Ordini/minuto | 10 | Rate limiting |
| Score estremi | |score| > 0.8 | Size ×0.5 |

### Backtesting

- **Motore:** QuantConnect Lean (Python interface)
- **Dati:** Signal Store history da PostgreSQL
- **Gate Alpha Miner:** Sharpe > 1.0 AND Max Drawdown < 0.15 → candidate

**Valutazione:**

**Punti di forza:**
- Separazione netta tra strategia e infrastruttura
- Regime-aware positioning (multiplier dinamico)
- Risk manager hard-coded, non modificabile via API

**Rischi:**
1. **Assunzione non validata:** Soglie (0.3 per entry, 2%/5% stop) non sono backtestate nel documento
2. **Gap:** Nessun meccanismo di trailing stop o stop dinamico basato su volatilità (ATR)
3. **Rischio:** Score > 0.8 → size dimezzato è controintuitivo (i segnali forti meritano più capitale, non meno)

**Raccomandazione:** Rivedere la logica score estremi — considerare invece:
- Score > 0.8 → richiedi approvazione manuale (semi-auto)
- Oppure: score > 0.8 → size normale ma stop più stretto

---

## 5. Execution & Integrazione Broker

### Modalità di Esecuzione

| Modalità | Broker | Esecuzione |
|---|---|---|
| backtest | QC simulato | Automatica |
| paper | Alpaca/IB sim | Automatica (ordini finti) |
| semi_auto | Broker reale | Notifica Telegram → approvazione 5 min → execute |
| full_auto | Broker reale | Esecuzione diretta |

### Custom Data Feed

```python
class LLMSignalData(PythonData):
    def GetSource(self, config, date, isLive):
        if isLive:
            return SubscriptionDataSource(
                f"http://localhost:8000/api/signals/{config.Symbol}",
                SubscriptionTransportMedium.Rest
            )
        # ... history per backtest
```

### Valutazione Critica

**Punti di forza:**
- HTTP locale (localhost:8000) → latenza trascurabile (<1ms)
- Stessa interfaccia per backtest e live (consistenza garantita)

**Rischi critici:**
1. **Single point of failure:** FastAPI down → QuantConnect non riceve segnali → nessun trade
2. **Assunzione:** HTTP REST è abbastanza veloce per intraday 5m — **vero, ma non misurato**
3. **Gap:** Nessun meccanismo di cache locale in QuantConnect (se HTTP fallisce, crash)
4. **Rischio broker:** Interactive Brokers ha API complesse con gestione errori non banale

**Raccomandazioni:**
- Aggiungere fallback: se HTTP fallisce, leggi ultimo segnale valido da Redis direttamente
- Implementare health check tra QC e FastAPI prima di ogni esecuzione
- Documentare gestione errori IB: timeout, rejected orders, partial fills

---

## 6. Risk Management

### Livelli di Protezione

**Livello 1 — Sanitizzazione Input:**
```python
def sanitize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = bleach.clean(text, strip=True)
    text = re.sub(INVISIBLE_CHARS_PATTERN, "", text)
    text = text[:MAX_CHARS]
    verify_ticker_ascii(text)
    return text
```

**Livello 2 — Guardrail LLM:**

| Condizione | Azione |
|---|---|
| Output non parsabile (Pydantic) | Retry (max 2) → fallback |
| confidence < 0.4 | Segnale scartato → FinBERT |
| 3 segnali scartati consecutivi | Alert Telegram + QC sizing ×0.5 |
| Regime ensemble divergente | label="uncertain", multiplier=0.3 |
| Timeout LLM > 10s | Fallback immediato |
| Budget LLM > 80% | Blocco chiamate + FinBERT + alert |

**Fallback hierarchy:** LLM → FinBERT locale → ultimo segnale cache → sizing conservativo

**Livello 3 — Circuit Breaker Trading:**

| Soglia | Azione |
|---|---|
| Daily drawdown > 5% | Pausa nuove posizioni |
| Daily drawdown > 10% | Stop ordini + alert |
| Posizione singola > 10% | Ordine rifiutato |
| Ordini/min > 10 | Rate limiting |
| |score| > 0.8 | Size ×0.5 |

**Kill-switch:**
1. mode = "halted"
2. Cancella ordini pending
3. Chiudi posizioni a mercato
4. Stop Celery workers
5. Notifica Telegram

### Valutazione Critica

**Punti di forza:**
- Fallback hierarchy ben concepita (LLM → FinBERT → cache → conservative)
- Circuit breaker hard-coded, non bypassabile via API
- Kill-switch sequenziale con notify

**Rischi critici:**
1. **Gap:** Nessun meccanismo di "cool-down period" dopo drawdown > 5% — cosa succede dopo la pausa?
2. **Assunzione:** FinBERT è sempre disponibile e accurato — **non validato**
3. **Rischio:** 3 segnali scartati → sizing ×0.5 è una punizione al sistema quando invece dovrebbe proteggere
4. **Gap:** Nessun limite di drawdown per singola strategia (intraday vs swing)

**Raccomandazioni:**
- Aggiungere: dopo drawdown > 5%, richiedi approvazione manuale per riprendere
- FinBERT dovrebbe avere un suo health check (se il modello locale crasha, cosa succede?)
- Rivedere: 3 segnali scartati → alert + pause, non sizing ridotto

---

## 7. Scalabilità e Performance

### Colli di Bottiglia Potenziali

| Componente | Capacità | Rischio |
|---|---|---|
| RSS Polling (60s) | ~1000 articoli/ora | Basso |
| Celery Workers | Dipende da CPU/GPU | Medio |
| Redis (hot cache) | ~100k ops/sec | Basso |
| PostgreSQL | Dipende da query | Medio |
| FastAPI HTTP | ~10k req/sec | Basso |
| LLM API (cloud) | Rate limit + latenza | **Alto** |
| QuantConnect OnData() | 5m bar | Basso |

### Scaling Strategy

**Verticale (Fase 1-2):**
- Più CPU per Celery workers
- Redis e PostgreSQL su istanza dedicata

**Orizzontale (Fase 3+):**
- Multiple Celery workers per tipo (Sentiment, Regime, Alpha)
- Redis Sentinel per HA
- PostgreSQL read replicas per query history

### Valutazione Critica

**Rischi:**
1. **LLM API rate limit:** Claude/GPT-4o hanno limiti di request/minuto — non documentati
2. **Assunzione:** 15 minuti è sufficiente per processare batch di 10 NewsItem — **da validare**
3. **Gap:** Nessun piano di caching semantico dettagliato (come si gestiscono collisioni?)
4. **Rischio:** QuantConnect OnData() chiamato ogni 5m su multi-asset può creare congestione

**Raccomandazioni:**
- Misurare latenza end-to-end: news → sanitization → LLM → Redis → QC
- Implementare backpressure: se queue Redis > threshold, rallenta ingestione
- Considerare: batch NewsItem per settore (tutti tech insieme) per ottimizzare LLM calls

---

## 8. Affidabilità e Resilienza

### Gestione Guasti

| Scenario | Mitigazione |
|---|---|
| LLM API down | Fallback FinBERT |
| FastAPI down | Redis direct read (da implementare) |
| Celery worker down | Alert dopo 5 min |
| PostgreSQL down | Redis TTL esteso, no audit |
| Redis down | **CRITICO** — nessun segnale |
| QuantConnect crash | Paper trading fallback |

### Monitoring

**Fase 1 — Logging + Telegram:**
- Segnale stale > 2× intervallo
- Budget LLM > 80%
- Drawdown giornaliero > 3%
- Worker down > 5 min
- Alpha candidate trovato
- Kill-switch attivato

**Fase 2 — Prometheus + Grafana:**
- Dashboard in tempo reale
- Alerting su soglie configurabili

### Valutazione Critica

**Rischi critici:**
1. **Single point of failure:** Redis down → sistema bloccato (nessun fallback)
2. **Gap:** Nessun piano di disaster recovery (backup PostgreSQL? restore procedure?)
3. **Assunzione:** Telegram bot è sempre disponibile — **non vero** (rate limit, downtime)
4. **Rischio:** Logging strutturato su file può riempire disco (nessun log rotation menzionato)

**Raccomandazioni:**
- Redis Cluster o Sentinel per HA
- Implementare: se Redis down, scrivi segnali su file locale (CSV) e leggi da QC
- Aggiungere log rotation (max 100MB/file, keep 7 giorni)
- Piano DR: backup giornaliero PostgreSQL + restore test mensile

---

## 9. Sicurezza

### Gestione Credenziali

**Documentato:**
- API key LLM provider (Claude/GPT/Gemini)
- Broker credentials (IB/Alpaca)
- Telegram Bot token

**Non documentato:**
- Come sono memorizzate? (env vars, secrets manager, file cifrato?)
- Rotazione delle chiavi?
- Audit access?

### Protezione Accessi

**Implementato:**
- Kill-switch richiede POST /api/admin/killswitch (nessuna auth menzionata!)
- Mode switch richiede POST /api/admin/mode

**Rischi critici:**
1. **Vulnerabilità:** API admin senza autenticazione — **chiunque può haltare il sistema**
2. **Gap:** Nessun rate limiting su API admin
3. **Rischio:** Telegram bot token compromesso → attacker può approvare trade
4. **Gap:** Nessun audit log delle azioni admin

**Raccomandazioni urgenti:**
- Implementare API key authentication su /api/admin/*
- Aggiungere HMAC signature su webhook Telegram
- Audit log: chi ha fatto cosa, quando (timestamp + IP)
- Considerare: 2FA per approvazioni trade in semi_auto

---

## 10. Qualità del Codice e Manutenibilità

### Modularità

**Punti di forza:**
- Interfacce astratte (NewsConnector, LLMClient)
- Provider-agnostic (swap LLM senza modifiche core)
- YAML config per connettori e worker

**Struttura moduli (implicita):**
```
src/
├── connectors/       # RSS, NewsAPI, SEC, GDELT, Macro
├── llm/             # Client abstraction, Claude, OpenAI, Gemini
├── workers/         # Sentiment, Regime, Alpha Miner
├── signal_store/    # Redis + PostgreSQL handlers
├── api/             # FastAPI routes
├── quantconnect/    # LLMSignalData, strategie, risk manager
└── config/          # YAML loaders
```

### Testabilità

**Non documentato:**
- Strategia di testing (unit, integration, e2e?)
- Mock per LLM API?
- Test di regressione per strategie?
- Coverage target?

**Raccomandazioni:**
- Unit test: connettori (mock HTTP), sanitizzazione, scoring formula
- Integration test: Celery worker end-to-end (mock LLM)
- Backtest regression: ogni strategia deve passare historical test suite
- Target: 80% coverage su core logic, 100% su risk manager

### Documentazione

**Punti di forza:**
- CLAUDE.md chiaro e completo
- Design spec dettagliato (2026-05-03-trading-system-design.md)
- Documento Word con fondamenti teorici

**Gap:**
- Nessun diagramma di sequenza (news → trade)
- Nessuna specifica API dettagliata (OpenAPI/Swagger?)
- Nessun runbook operativo (cosa fare se X fallisce)

---

## 11. Problemi e Rischi Principali

### Riepilogo Rischi Critici

| ID | Rischio | Impatto | Probabilità | Priorità |
|---|---|---|---|---|
| **R1** | API admin senza autenticazione | **CRITICO** — halt system da attacker | Media | **P0** |
| **R2** | Redis single point of failure | **ALTO** — sistema bloccato | Media | **P0** |
| **R3** | Nessuna auth su Telegram webhook | **ALTO** — trade non autorizzati | Bassa | **P1** |
| **R4** | Fallback FinBERT non testato | **MEDIO** — segnali errati in fallback | Media | **P1** |
| **R5** | Score estremi → size ridotto (controintuitivo) | **MEDIO** — opportunità perse | Alta | **P2** |
| **R6** | Nessuna rotazione log | **BASSO** — disco pieno | Media | **P3** |
| **R7** | Assunzione traduzione senza bias | **MEDIO** — sentiment distorto | Alta | **P2** |
| **R8** | Nessun disaster recovery plan | **ALTO** — perdita dati audit | Bassa | **P2** |
| **R9** | LLM rate limit non documentato | **MEDIO** — segnali persi | Media | **P2** |
| **R10** | Nessun test strategy documentata | **MEDIO** — bug in produzione | Alta | **P1** |

### Rischi Operativi (Trading-Specific)

| ID | Rischio | Impatto | Mitigazione |
|---|---|---|---|
| **T1** | Slippage non modellato | Perdite in live | Backtest con slippage fee |
| **T2** | Liquidità insufficiente | Ordini parziali | Check volume pre-trade |
| **T3** | Broker API error | Ordini persi | Retry + alert |
| **T4** | Orario mercato non gestito | Trade fuori orario | Check market hours |
| **T5** | Corporate actions (split, dividend) | Prezzo distorto | Adjusted price feed |

---

## 12. Miglioramenti Suggeriti

### Quick Wins (Fase 1)

1. **API Authentication** — Aggiungere API key su /api/admin/* (1 giorno)
2. **Log Rotation** — Configurare logging con max 100MB/file (2 ore)
3. **Health Check Endpoint** — GET /api/health con status tutti i componenti (4 ore)
4. **Redis Fallback** — Se Redis down, leggi da file locale (1 giorno)
5. **Test Sanitizzazione** — Unit test per adversarial news (1 giorno)

### Interventi Strutturali (Fase 2)

1. **Redis Sentinel/Cluster** — HA per signal store (3 giorni)
2. **Disaster Recovery Plan** — Backup PostgreSQL + restore test (2 giorni)
3. **Audit Log** — Tutte le azioni admin loggate (1 giorno)
4. **Telegram HMAC** — Signature su webhook (4 ore)
5. **Test Suite** — Unit + integration test (1 settimana)

### Miglioramenti Architetturali (Fase 3)

1. **Microservizi** — Decomporre: ingestion, llm, signal-store, api (2 settimane)
2. **Event Sourcing** — Segnali come eventi immutabili (per audit completo)
3. **Multi-Region** — Redis + PostgreSQL replica su region diversa
4. **Feature Store** — Centralizzare feature per ML/LLM

### Miglioramenti Trading-Specific

1. **Dynamic Stop-Loss** — Basato su ATR/volatilità, non fisso
2. **Trailing Stop** — Lock profits su trend forti
3. **Position Sizing Ottimizzato** — Kelly criterion o half-Kelly
4. **Correlation Check** — Non aprire posizioni correlate > threshold
5. **Market Regime Detection** — Aggiungere indicatori tecnici (VIX, ADX)

---

## Conclusioni

### Giudizio Complessivo

**Voto: 7.5/10**

L'architettura è **ben concepita** e segue i pattern corretti per un sistema di trading basato su LLM:

**Punti di forza:**
- Disaccoppiamento LLM ↔ execution (corretto)
- Fallback hierarchy (robusto)
- Circuit breaker hard-coded (sicuro)
- Provider-agnostic (flessibile)

**Aree di miglioramento critiche:**
- Sicurezza API admin (urgente)
- Redis HA (necessario)
- Test strategy (mancante)
- Disaster recovery (non pianificato)

### Raccomandazione Finale

**Prima di andare in produzione:**
1. Implementare auth su API admin (**non negoziabile**)
2. Testare fallback FinBERT con adversarial news
3. Eseguire backtest con slippage e fees realistiche
4. Redigere runbook operativo (cosa fare se X fallisce)
5. Eseguire paper trading per ≥ 30 giorni prima di semi_auto

**Il sistema ha potenziale, ma richiede rigorosa validazione prima di esporre capitale reale.**

---

*Documento generato da Claude Code — AI Software Architect*
*Data: 2026-05-03*
