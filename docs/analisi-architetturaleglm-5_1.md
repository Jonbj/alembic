# Analisi Architetturale Critica — LLM Trading System

**Data:** 2026-05-03  
**Fonti analizzate:** `docs/LLM Trading System Integration.docx`, `docs/superpowers/specs/2026-05-03-trading-system-design.md`, `CLAUDE.md`, brainstorm sessions  

---

## 1. Panoramica del Sistema

**Scopo:** Sistema di trading algoritmico multi-asset che utilizza Large Language Models come generatore offline di segnali (sentiment, regime, alpha), mai nel percorso critico di esecuzione. Paradigma "Alpha Miner".

**Tipo di trading:** Algorithmic trading a media/bassa frequenza — **non HFT**. Dual-layer: intraday (5m–1h) e swing trading (4h–1D). L'LLM genera segnali asincroni; il motore di esecuzione li consuma come dati pre-calcolati.

**Flusso generale dei dati:**

```
[Fonti News/Macro] → [Sanitizzazione + Normalizzazione]
       ↓
[Redis Queue (NewsItem)]
       ↓
[Celery Workers: Sentiment / Regime / Alpha Miner]
       ↓
[Signal Store: Redis (hot) + PostgreSQL (audit)]
       ↓
[QuantConnect Lean: OnData() legge segnali come Custom Data Feed]
       ↓
[Broker: IB / Alpaca]
```

**Ciclo operativo previsto:** Backtest → Paper → Semi-auto (approvazione umana via Telegram) → Full-auto.

---

## 2. Architettura

### Componenti principali

| Componente | Responsabilità | Stato |
|---|---|---|
| **Data Ingestion Layer** | Raccolta news/macro da fonti eterogenee via pattern Connector | Design |
| **Sanitizzazione Pipeline** | Normalizzazione Unicode, strip HTML, rimozione caratteri invisibili, troncamento, NER check | Design |
| **LLM Pipeline (3 Worker)** | Sentiment Worker (15 min), Regime Detector (1h), Alpha Miner (overnight) | Design |
| **Signal Store** | Redis (hot cache con TTL) + PostgreSQL (audit/storico) | Design |
| **FastAPI Control Plane** | API bridge per segnali + admin (mode switch, kill-switch) | Design |
| **QuantConnect Lean** | Execution engine: backtesting + live trading | Design |
| **Monitoring & Alerting** | Fase 1: Telegram + structured logging; Fase 2: Prometheus+Grafana | Design |

### Pattern architetturale

Il sistema è definito come **"monolite modulare"**: singolo repo Python con moduli a responsabilità singola, progettato per essere decomposto in microservizi in futuro. Il flusso dati è **event-driven asincrono**: Celery beat schedula i worker; Redis funge da message bus e cache; PostgreSQL garantisce persistenza e audit.

Il brainstorm ha valutato tre alternative:
- **A) Monolite Orchestrato** — un processo, semplice ma fragile
- **B) Microservizi Event-Driven** — fault isolation, complessità operativa
- **C) Monolite Modulare** (scelta finale) — compromesso: semplicità iniziale + interfaccie pulite per futura scomposizione

### Diagramma logico

```
                    ┌─────────────────────────────────────────┐
                    │         Data Ingestion Layer             │
                    │  RSSConnector  NewsAPI  SEC  GDELT  FRED │
                    └──────────────────┬──────────────────────┘
                                       │ sanitize() → translate()
                                       ▼
                    ┌──────────────────┐──────────────────────┐
                    │              Redis Queue                 │
                    │        (NewsItem per fonte)              │
                    └──────────────────┬──────────────────────┘
                                       │ Celery consume
                    ┌──────────────────▼──────────────────────┐
                    │            LLM Pipeline                   │
                    │  ┌──────────┐ ┌──────────┐ ┌───────────┐ │
                    │  │Sentiment │ │ Regime   │ │Alpha Miner│ │
                    │  │Worker   │ │ Detector │ │(overnight)│ │
                    │  │(15 min) │ │ (1 h)   │ │           │ │
                    │  └────┬─────┘ └────┬─────┘ └─────┬─────┘ │
                    └───────┼─────────────┼──────────────┼─────┘
                            │             │              │
                    ┌───────▼─────────────▼──────────────▼─────┐
                    │             Signal Store                   │
                    │  Redis (hot, TTL 2-4h) │ PostgreSQL (cold) │
                    └──────────────────┬─────────────────────────┘
                                       │ FastAPI REST
                    ┌──────────────────▼─────────────────────────┐
                    │       QuantConnect Lean Execution           │
                    │  LLMSignalData (Custom Feed) → OnData()     │
                    │  Intraday Strategy │ Swing Strategy          │
                    │  Risk Manager (circuit breaker hard-coded)  │
                    └──────────────────┬─────────────────────────┘
                                       │
                              ┌────────▼────────┐
                              │  Broker (IB/    │
                              │  Alpaca)        │
                              └────────────────┘
```

**Componente orizzontale:** FastAPI Control Plane espone `/api/signals`, `/api/admin/mode`, `/api/admin/killswitch`, `/api/health` — leggibile sia da QC che da operatori umani.

### Valutazione architetturale

**Punti di forza:**
- Il disaccoppiamento LLM/execution è architetturalmente solido e ben motivato dalla letteratura (Alpha Miner paradigm)
- La fallback hierarchy (LLM → FinBERT → cache → sizing conservativo) dimostra consapevolezza del rischio
- Il pattern Connector per le fonti è estensibile senza modificare il core
- La scelta "monolite modulare" è pragmatica per la fase attuale

**Criticità:**
- **Nessun codice esistente.** Tutto è allo stato di design — nessun prototipo, nessuna proof-of-concept. Il rischio è che le interfacce astratte (LLMClient, NewsConnector) si rivelino inadeguate al primo contatto con la realtà
- **Monolite modulare vs. microservizi:** la promessa "pronto per essere decomposto" è un'assunzione non verificata. Se i confini dei moduli non sono netti dalla Fase 1, la decomposizione sarà una riscrittura
- **Single point of failure:** Redis è sia message bus che hot cache. Se Redis va giù, il Sentiment Worker non riceve notizie, QC non legge segnali live, il kill-switch non è raggiungibile via `/api/health`. La doc non menziona Redis HA (Sentinel/Cluster)
- **FastAPI come SPOF:** se il Control Plane cade, QC non può leggere i segnali. Non c'è fallback locale documentato

---

## 3. Gestione dei Dati

### Fonti dei dati

**Fase 1 (gratuita):** RSS (Reuters, AP, MarketWatch, CNBC, Sole 24 Ore), NewsAPI (100 req/day), SEC EDGAR (8-K/10-K/10-Q), GDELT (global events), FRED/ECB (macro).

**Fase 2+ (a pagamento o utente-mediated):** EmailConnector (IMAP/Gmail per newsletter premium), TelegramConnector (canali finanziari), Bloomberg/Refinitiv (istituzionale), SeekingAlpha, Twitter/X.

### Modalità di ingestione e storage

- **Ingestion:** polling via `fetch()` asincrono. Frequenze: 60s (RSS), 5 min (NewsAPI), real-time (EDGAR), 15 min (GDELT), 1h (FRED)
- **Normalizzazione:** pipeline obbligatoria (NFKC → bleach → invisible chars → ticker NER → truncate → translate → NewsItem)
- **Hot storage:** Redis queue per NewsItem, Redis cache per segnali (TTL 2-4h)
- **Cold storage:** PostgreSQL per segnali storici + audit trail (con indici su `symbol, timestamp`)

### Latenza e gestione real-time vs. batch

- **News → Sentiment:** latenza minima 15 min (intervallo Celery beat). Questo è accettabile per il layer swing, ma **problematico per l'intraday**: una notizia breaking su un titolo può muovere il prezzo in secondi, ma il segnale arriva al più presto 15 minuti dopo. La doc menziona batch "fino a 10 notizie per chiamata" ma non specifica se il batch è per fonte o per simbolo
- **Segnale → QC:** la latenza dipende dal polling di `LLMSignalData.GetSource()`. QuantConnect non documenta con precisione l'intervallo di polling per Custom Data via REST. Da verificare empiricamente

### Qualità e validazione dei dati

**Punti di forza:**
- La sanitizzazione Unicode è ben motivata dalla letteratura (omoglifi adversarial, -17.7% rendimento annuo)
- Il troncamento a 4000 token limita attacchi di prompt injection per lunghezza
- Il NER check su ticker simbolici è una difesa specifica e valida

**Criticità:**
- **Nessun meccanismo di deduplicazione esplicito** per le fonti. RSS + NewsAPI possono fornire la stessa notizia. Il semantic cache sul Sentiment Worker mitiga il problema Lato LLM, ma la stessa notizia entra due volte nella pipeline, consumando slot del batch
- **Nessuna validazione temporale sui NewsItem.** Se una fonte ritorna una notizia vecchia (es. RSS feed non aggiornato), il Sentiment Worker la processa ugualmente. Manca un filtro `if news.timestamp < now - max_age: skip`
- **La traduzione automatica** (DeepL/Google) introduce un'ulteriore fonte di perdita di significato e potenziale distorsione del sentiment, specialmente per linguaggi con ambiguità intrinseca (es. italiano finanziario). La doc non menziona validazione della qualità della traduzione
- **GDELT come fonte di sentiment:** GDELT è noto per avere un rapporto segnale-rumore molto basso e bias geografico. La doc non specifica filtri di qualità per i dati GDELT

---

## 4. Logica di Trading

### Come vengono definite le strategie

**Due strategie predefinite:**

1. **Intraday Strategy** (5m–1h): momentum + sentiment score. Entry quando `sentiment_score > 0.3` e momentum confermato
2. **Swing Strategy** (4h–1D): regime-aware positioning. Position size = `base_size × regime.position_multiplier`. Entry su breakout + sentiment positivo

**Alpha Miner** genera strategie aggiuntive: ciclo autonomo overnight (max 5 iterazioni), scrive codice Python per QC, lancia backtest via MCP Server, promuove a `candidate` se Sharpe > 1.0 e MaxDD < 15%.

### Separazione tra strategia e infrastruttura

**Ben definita nel design:**
- I worker LLM producono segnali (dati), non decisioni di trading
- QC consuma segnali come Custom Data Feed — la strategia è puro codice QC che legge dati
- Il Risk Manager è hard-coded in QC, non modificabile via API

**Criticità:**
- Le soglie di entry (`sentiment_score > 0.3`) sono documentate come costanti, ma non c'è un meccanismo per calibrarle dinamicamente. In un mercato bull, 0.3 potrebbe essere troppo basso (troppi falsi positivi); in un mercato volatile, troppo alto (perdi segnali reali). La doc non menziona ottimizzazione adattiva delle soglie
- **Alpha Miner genera codice Python per QC**, ma non c'è un processo formale di code review prima del backtest. Il codice generato dall'LLM potrebbe contenere look-ahead bias, errori logici, o sfruttare accidentalmente dati futuri. Il design menziona che "il codice gira nell'ambiente isolato di QC" ma l'isolamento è di esecuzione, non di validazione logica

### Backtesting e simulazione

- QuantConnect Lean è il motore di backtesting (event-driven, multi-asset)
- L'Alpha Miner usa il MCP Server per lanciare backtest programmaticamente
- Il Signal Store PostgreSQL rende disponibili i segnali storici per backtest QC via `/api/signals/history`

**Criticità:**
- **Survivorship bias non menzionato.** Se il backtest usa solo i ticker attualmente attivi, ignora aziende delistate/bancarotta. Questo è un problema noto e grave in qualunque sistema di backtesting
- **Nessun out-of-sample validation documentato** per le strategie generate dall'Alpha Miner. Con max 5 iterazioni, il rischio di overfitting sul backtest è concreto
- **Il gate "Sharpe > 1.0 AND MaxDD < 15%" è debole.** Sharpe > 1.0 è raggiungibile da molte strategie mediocri in periodi bull. Manca un requisito su Sharpe adjustato per il benchmark, o su metriche come Calmar Ratio, Sortino Ratio, o profit factor

### Parametrizzazione e configurabilità

- YAML config per connectors, workers, trading
- Modalità operative via API: backtest → paper → semi_auto → full_auto
- Regime multiplier controlla il sizing dinamicamente

**Criticità:**
- **La modalità è letta da `/api/admin/mode` a "ogni generazione d'ordine"** — questo significa una chiamata HTTP per ogni ordine. Se l'API è lenta o irraggiungibile, QC cosa fa? La doc non specifica il comportamento di default (presumibilmente `halted`, ma è un'assunzione)

---

## 5. Execution & Integrazione con Broker/Exchange

### Modalità di invio ordini

- QuantConnect Lean gestisce l'invio ordini al broker
- Broker supportati: Interactive Brokers, Alpaca (configurabile)
- Modalità semi-auto: notifica Telegram → approvazione umana entro 5 min → timeout → scarta

### Gestione errori, retry e fallback

**Nella doc di design:** il focus è quasi esclusivamente sui fallback LLM (LLM → FinBERT → cache → sizing conservativo). La gestione degli errori a livello di execution è delegata a QuantConnect Lean senza specifica.

**Criticità:**
- **Nessuna documentazione su retry policy per ordini rejected/partially filled.** QC supporta `OnOrderEvent()` per gestire questi casi, ma il design non lo menziona
- **Il kill-switch chiude tutte le posizioni "a mercato"** — in mercati illiquidi o fuori orario, questo può causare slippage catastrofico. La doc non menziona limiti di orario per il kill-switch
- **Semi-auto timeout (5 min)** è arbitrario e potenzialmente pericoloso: un ordine scartato per timeout in un mercato che si muove velocemente potrebbe essere un'opportunità persa o un disastro evitato — non c'è modo di distinguere

### Slippage, latenza e gestione della liquidità

- **Latenza LLM:** mitigata dal disaccoppiamento (segnali pre-calcolati)
- **Latenza execution:** dipende da QC + broker. Non documentata
- **Slippage:** non menzionato nella doc di design. QuantConnect supporta modelli di slippage, ma il design non specifica quale usare

**Criticità critica:** per un sistema che opera su timeframe 5m-1h, lo slippage di 1-2 tick può erodere significativamente il rendimento, specialmente su asset meno liquidi (small cap, forex esotico). La mancanza di modellizzazione dello slippage nel design è un rischio significativo.

---

## 6. Risk Management

### Meccanismi di controllo rischio

| Meccanismo | Soglia | Azione | Implementato in |
|---|---|---|---|
| Daily drawdown | > 5% | Pausa nuove posizioni | QC (hard-coded) |
| Daily drawdown | > 10% | Stop ordini + alert | QC (hard-coded) |
| Max posizione singola | > 10% portafoglio | Ordine rifiutato | QC (hard-coded) |
| Rate limiting | > 10 ordini/min | Rate limit | QC (hard-coded) |
| Score estremo | \|score\| > 0.8 | Size ×0.5 | QC (hard-coded) |
| Regime conservativo | uncertain/risk_off | Multiplier 0.3 | QC legge da Signal Store |
| Confidence bassa | < 0.4 | Segnale scartato | LLM Worker |

### Protezioni contro comportamenti anomali

- Ensemble divergence per il regime (2 chiamate → se divergono → uncertain)
- Budget giornaliero LLM con cap
- 3 segnali scartati consecutivi → alert + sizing ×0.5
- Kill-switch con sequenza definita (mode=halted → cancella ordini → chiudi posizioni → stop workers → notifica)

### Fail-safe e circuit breaker

**Ben progettati concettualmente.** Tre livelli (sanitizzazione → guardrail LLM → circuit breaker trading) con fallback cascade chiara.

**Criticità:**
- **Il daily drawdown è calcolato su base giornaliera.** Un flash crash può causare >10% drawdown in minuti. Il sistema potrebbe non reagire abbastanza velocemente se QC controlla il drawdown solo alla risoluzione della barra (5m/15m/1h). Manca un meccanismo di **intra-bar monitoring**
- **"Hard-coded in QC, non modificabile via API"** è una sicurezza, ma anche una limitazione: se le soglie sono sbagliate, serve un deploy. E se qualcuno modifica il codice QC accidentalmente? Non c'è un meccanismo di **immutability verification**
- **Il kill-switch chiude posizioni "a mercato"** senza consideration per il contesto. In un flash crash, chiudere a mercato può realizzare perdite che si sarebbero invertite. Manca un'opzione di kill-switch conservativo (chiudi solo posizioni in profitto, mantieni quelle in loss con stop-loss aggiustato)
- **Nessun position limit assoluto per asset class.** Il 10% per singola posizione è buono, ma se il sistema apre 10 posizioni al 10% ciascuna, è il 100% del portafoglio. Manca un **gross exposure limit**
- **Nessun correlation risk management.** Se tutte le posizioni sono long su tech stocks correlate, un evento settoriale può colpire tutto il portafoglio simultaneamente. Il regime detector mitiga parzialmente, ma non è un substituto per una vera gestione della correlazione

---

## 7. Scalabilità e Performance

### Colli di bottiglia potenziali

1. **Redis SPOF:** singola istanza Redis come message bus + cache. Sotto carico (molti connector + molti worker + QC polling), la latenza Redis può aumentare. Senza HA, un crash Redis blocca tutto il sistema
2. **Celery beat scheduling:** i worker sono schedulati a intervalli fissi. Se il batch di notizie è grande (es. dopo un weekend), il Sentiment Worker potrebbe accumulare ritardo
3. **LLM API rate limits:** Claude/GPT-4o/Gemini hanno rate limits per RPM/TPM. Il design non specifica come gestire il rate limiting del provider LLM (diverso dal budget giornaliero)
4. **FastAPI come bottleneck:** ogni tick di QC fa una chiamata HTTP a `/api/signals/{symbol}`. Per N simboli × M timeframe, il traffico può essere significativo
5. **PostgreSQL write throughput:** ogni segnale è scritto in PostgreSQL. Sotto carico sostenuto, le write possono accumularsi

### Strategie di scaling

Il design menziona "pronto per essere decomposto in microservizi" ma senza specifiche operative:

- **Scaling verticale:** non menzionato
- **Scaling orizzontale:** i Celery worker possono essere scalati aggiungendo processi, ma la doc non specifica come
- **Redis:** nessun piano per Redis Cluster/Sentinel
- **PostgreSQL:** nessun piano per read replicas

### Gestione della concorrenza

- Celery gestisce la concorrenza dei worker
- FastAPI è async (ASGI)
- QC è single-threaded nel suo event loop

**Criticità:**
- **Race condition potenziale:** se il Sentiment Worker e il Regime Detector scrivono simultaneamente sullo stesso key Redis per lo stesso simbolo, c'è rischio di lettura parziale da parte di QC. La doc non menziona transazioni o atomicità Redis
- **Celery task idempotency:** non documentata. Se un task fallisce e viene ritentato, il segnale potrebbe essere scritto due volte in PostgreSQL

---

## 8. Affidabilità e Resilienza

### Gestione dei guasti

**Fallback hierarchy documentata:** LLM → FinBERT locale → ultimo segnale valido in cache → sizing conservativo fisso.

Questo è un buon design. Tuttavia:

**Criticità:**
- **FinBERT come fallback:** FinBERT è un modello di sentiment classification (positive/negative/neutral), non un modello di reasoning. Il suo output non è comparabile con il DK-CoT del Sentiment Worker (che produce reasoning + confidence + polarity). La doc non specifica come mappare l'output FinBERT nel modello `SentimentResult`
- **"Ultimo segnale valido in cache"** — se il segnale è stale (TTL 4h per sentiment, 2h per regime), potrebbe non riflettere le condizioni attuali. Un regime "risk_on" di 2 ore fa potrebbe essere pericoloso se il mercato è crashato nel frattempo
- **Nessun health check proattivo per i connector.** Se Reuters RSS cambia formato, il RSSConnector potrebbe smettere di funzionare silenziosamente. La doc menziona alert per "worker down > 5 minuti" ma non per "connector restituisce 0 notizie" (che potrebbe indicare un problema, non un giorno tranquillo)

### Logging, monitoring, alerting

**Fase 1:** structured JSON logging → file + stdout + Telegram alerts.  
**Fase 2:** Prometheus + Grafana.

**Alert documentati:** segnale stale, budget LLM >80%, drawdown >3%, worker down >5min, alpha candidate trovato, kill-switch attivato.

**Criticità:**
- **Manca alert per:** volume ordini anormale, fill rate anomalo, latenza broker crescente, correlazione posizioni elevata, drift del sentiment (score sistematicamente alto/basso per periodi prolungati)
- **Telegram come canale di alert è fragile.** Se l'API Telegram è rate-limited o il bot è bannato, gli alert non arrivano. Manca un canale di fallback (email, SMS, webhook Slack)
- **Nessun audit log per le decisioni di trading.** Il PostgreSQL salva i segnali, ma non le decisioni effettive (perché un ordine è stato piazzato/rifiutato, quali guardrail sono scattati). Questo è critico per il debugging post-mortem e la compliance

### Recovery e disaster handling

- Kill-switch come meccanismo di emergency stop
- Riattivazione solo manuale via API (`POST /api/admin/mode {"mode": "paper"}`)

**Criticità:**
- **Nessun recovery automatico documentato.** Se Redis crasha e viene riavviato, i segnali in cache sono persi. Il sistema torna in modalità "ultimo segnale in PostgreSQL", ma la doc non specifica questo flusso
- **Nessun backup/restore strategy per PostgreSQL.** Per un sistema che deve mantenere audit trail, l'assenza di un piano di backup è un rischio di compliance
- **Nessun runbook per incident response.** Cosa fare se il sistema piazza ordini errati? Come si reverte? Come si investiga?

---

## 9. Sicurezza

### Gestione credenziali/API key

**Non documentata.** La doc menziona "API cloud (Claude/GPT-4o/Gemini)", "DeepL/Google Translate API", "Alpaca/IB broker", "Telegram Bot API", "NewsAPI", "FRED API", "SEC EDGAR API" — tutte richiedono credenziali. Ma non c'è alcuna menzione di:
- Dove sono memorizzate le API key
- Come sono protette (env vars, vault, encrypted config)
- Rotazione delle key
- Revoca in caso di compromissione

**Rischio critico.** Per un sistema che gestisce denaro reale (fase 3+), la gestione delle credenziali è un requisito non opzionale.

### Protezione da accessi non autorizzati

- Il kill-switch è accessibile via `POST /api/admin/killswitch` — senza autenticazione documentata
- Il mode switch è accessibile via `POST /api/admin/mode` — senza autenticazione documentata
- I segnali sono esposti su `GET /api/signals/{symbol}` — senza autenticazione documentata

**Rischio critico.** Qualsiasi servizio sulla rete può: (1) leggere i segnali, (2) cambiare la modalità, (3) attivare il kill-switch. Per un sistema di trading, questo è inaccettabile.

### Audit e tracciabilità

- PostgreSQL salva `model_id` e `worker_version` per ogni segnale — buon inizio
- **Ma non c'è audit delle azioni di trading** (chi ha approvato un ordine semi-auto, quando, perché)
- **Non c'è audit delle azioni amministrative** (chi ha attivato/disattivato il kill-switch, chi ha cambiato modalità)

### Altre preoccupazioni di sicurezza

- **Prompt injection via news:** la sanitizzazione Unicode mitiga gli omoglifi, ma non protegge da prompt injection semantica (notizie scritte per manipolare l'LLM, non tramite caratteri speciali). Un articolo ben scritto che inganna un analista umano può ingannare anche l'LLM
- **Alpha Miner code injection:** l'Alpha Miner genera codice Python per QC. Sebbene QC sia sandboxed, il codice generato potrebbe sfruttare feature di QC per fare cose impreviste (es. scrivere nell'Object Store, modificare parametri). La doc menziona "il codice Python generato non può fare syscall arbitrarie" ma non c'è una verifica formale di questo asserto
- **EmailConnector legge email personali:** accedere alla casella email dell'utente via IMAP/Gmail API espone contenuti sensibili non finanziari alla pipeline di sanitizzazione. La doc non menziona filtri per isolare solo le email rilevanti

---

## 10. Qualità del Codice e Manutenibilità

### Modularità

**Nel design:** ben strutturato. Pattern Connector, LLMClient astratto, worker indipendenti, Signal Store come interfaccia pulita.

**Criticità:** il design è elegante ma non ancora implementato. La modularità dipende interamente dalla disciplina di implementazione. Senza test automatici che verifichino le interfacce, la modularità può degradare rapidamente.

### Testabilità

**Non documentata.** Non c'è menzione di:
- Unit test per i connector
- Integration test per la pipeline di sanitizzazione
- Test per i fallback (simulare timeout LLM, confidence bassa, ecc.)
- Test per i circuit breaker (simulare drawdown, rate limiting)
- Property-based testing per la sanitizzazione Unicode
- Mock strategy per QC

**Rischio elevato.** Un sistema di trading senza strategy di test è un sistema dove i bug si scoprono a mercato aperto.

### Chiarezza e completezza della documentazione

**La documentazione di ricerca (docx) è eccellente:** ben strutturata, con riferimenti accademici, analisi comparata dei paradigmi, specifiche ingegneristiche dettagliate.

**La design spec (markdown) è buona** come blueprint iniziale, ma ha lacune operative significative:
- Mancano dettagli su deployment, configurazione, monitoring operativo
- Mancano esempi di prompt completi (DK-CoT)
- Mancano specifiche di test
- Mancano runbook operativi
- Le interfacce sono definite come classi astratte ma senza specifica formale dei contratti (pre/post condizioni, invarianti)

---

## 11. Problemi e Rischi Principali

| # | Rischio | Impatto | Probabilità | Note |
|---|---|---|---|---|
| 1 | **Redis SPOF** — singola istanza come message bus + cache | Critico: intero sistema down | Media | Nessun HA pianificato |
| 2 | **Nessuna autenticazione API** — chiunque può leggere segnali, cambiare modalità, attivare kill-switch | Critico: perdita finanziaria, manipolazione | Alta se esposto su rete | Non menzionata |
| 3 | **Gestione credenziali non documentata** — API key senza protezione | Critico: compromissione account | Alta | 10+ servizi con credenziali |
| 4 | **Latenza sentiment intraday** — 15 min minimo tra news e segnale | Alto: segnali stale per intraday 5m | Alta | Contraddizione timeframe |
| 5 | **Alpha Miner overfitting** — max 5 iterazioni, gate debole (Sharpe > 1.0) | Alto: strategie non robuste | Media | Manca out-of-sample validation |
| 6 | **Nessun survivorship bias** nel backtest | Alto: rendimenti sovrastimati | Alta | Problema noto in quant |
| 7 | **FinBERT fallback semantic mismatch** — output non comparabile con DK-CoT | Medio: segnali incoerenti | Media | Mapping non specificato |
| 8 | **No position correlation management** — 10 posizioni × 10% = 100% correlated | Medio: loss concentrato | Media | Solo regime detector parziale |
| 9 | **Kill-switch chiude a mercato** senza contesto | Alto: slippage catastrofico in mercati illiquidi | Bassa ma grave | Nessun orario/condizione check |
| 10 | **Nessun audit trail per trading decisions** | Medio: impossibile debugging post-mortem | Alta | Solo segnali salvati, non decisioni |
| 11 | **EmailConnector privacy** — legge email personali | Medio: esposizione dati sensibili | Media se implementato | Filtri non specificati |
| 12 | **No testing strategy** | Alto: bug scoperti in produzione | Alta | Zero menzione di test |

---

## 12. Miglioramenti Suggeriti

### Quick wins (implementabili nella Fase 1)

1. **Aggiungere autenticazione alla FastAPI.** API key header o JWT per tutti gli endpoint `/api/admin/*` e `/api/signals/*`. Implementazione: `Depends(api_key_header)` in FastAPI. Tempo: ~2 ore.

2. **Secret management.** Usare `python-dotenv` + `.env` file (non committato) per Fase 1; pianificare HashiCorp Vault o AWS Secrets Manager per Fase 3+. Tempo: ~1 ora per .env.

3. **Aggiungere idempotency key ai Celery task.** Evita doppio processing se un task viene ritentato. Tempo: ~2 ore.

4. **Aggiungere timestamp filter ai NewsItem.** `if news.timestamp < now - max_age: skip`. Previene processing di notizie stale. Tempo: ~30 min.

5. **Aggiungere `X-Request-ID` e tracing distribuito** (anche solo log correlato). Tempo: ~2 ore.

6. **Documentare il mapping FinBERT → SentimentResult.** Definire come mappare le 3 classi FinBERT (positive/negative/neutral) in `polarity` e `confidence` per il modello `SentimentResult`. Tempo: ~1 ora.

### Miglioramenti architetturali (Fase 2)

7. **Redis HA.** Configurare Redis Sentinel (minimo 3 nodi) per failover automatico. Critico prima del live trading. Complessità: media.

8. **Intra-bar drawdown monitoring.** Aggiungere un check del drawdown più frequentemente della risoluzione della barra. Opzioni: (a) QC `OnMinute` callback, (b) thread separato che monitora il portafoglio via QC API. Complessità: media.

9. **Gross exposure limit + correlation check.** Aggiungere limiti all'esposizione totale (es. max 200% gross, max 100% net) e un controllo di correlazione (es. max N posizioni nello stesso settore). Complessità: media-alta.

10. **Survivorship bias-free backtest data.** Usare QC's delisted equity data o dataset con survivorship bias correction. Complessità: bassa (QC lo supporta nativamente).

11. **Alpha Miner gate rinforzato.** Modificare i criteri di promozione: Sharpe > 1.5, MaxDD < 12%, **+ out-of-sample test obbligatorio** (walk-forward o ultimi 6 mesi esclusi dall'ottimizzazione), minimum trade count (es. > 100), profit factor > 1.5. Complessità: media.

12. **Audit log per trading decisions e admin actions.** Tabella PostgreSQL separata per loggare ogni ordine piazzato/rifiutato con motivo, ogni cambio modalità, ogni kill-switch activation. Complessità: bassa.

13. **Alert channel diversification.** Aggiungere email come fallback di Telegram. Considerare webhook generico (Slack, PagerDuty). Complessità: bassa.

### Interventi strutturali (Fase 3+)

14. **Latenza sentiment per intraday.** Valutare un Sentiment Worker "fast path" con intervallo 1-2 min per le notizie breaking (es. SEC 8-K, Reuters). Questo richiede: (a) prioritizzazione nella Redis queue, (b) LLM call singola (non batch) per notizie ad alta priorità, (c) budget LLM separato. Complessità: alta.

15. **Formal contract testing.** Implementare pact-style testing tra i moduli (Connector → Pipeline → Signal Store → QC). Verifica che le interfacce siano rispettate. Complessità: alta.

16. **Supervisor agent per Alpha Miner.** Prima di promuovere una strategia, un secondo LLM (o un set di regole deterministiche) verifica: no look-ahead bias, no data snooping, logica di trading coerente con l'ipotesi. Complessità: alta.

17. **Deployment pipeline con smoke tests automatici.** Ogni deploy di una nuova strategia o configurazione deve passare un set di test automatici su carta (paper trading di 24h minimo). Complessità: media-alta.

18. **Runbook operazionale.** Documentare procedure per: ordini errati, sistema down, broker disconnesso, LLM provider down, investigazione perdite. Complessità: bassa ma essenziale.

---

## Sintesi

Il design documentato è **ambizioso e concettualmente solido**. La scelta del paradigma Alpha Miner, il disaccoppiamento LLM/execution, la fallback hierarchy e i circuit breaker dimostrano una comprensione profonda dei rischi di integrare LLM nel trading.

Tuttavia, il sistema è **interamente allo stato di design** senza alcuna implementazione. I principali gap sono:

1. **Sicurezza operativa** (autenticazione API, gestione credenziali) — risolvibili rapidamente
2. **Resilienza infrastrutturale** (Redis SPOF, recovery) — richiedono pianificazione
3. **Validazione del backtest** (survivorship bias, overfitting, gate deboli) — critici per la affidabilità del sistema
4. **Testing** (zero documentato) — essenziale prima di qualunque deploy con denaro reale
5. **Audit e compliance** (decision log, admin actions) — critici per il debugging e la responsabilità

La priorità dovrebbe essere: implementare i quick wins di sicurezza (1-6) nella Fase 1, poi affrontare la resilienza e la validazione del backtest nella Fase 2, e solo dopo passare al semi-auto/live. Nessun capitale reale dovrebbe essere esposto senza: autenticazione API, Redis HA, audit trail, e almeno un ciclo completo di paper trading con metriche verificate.