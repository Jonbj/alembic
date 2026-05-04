# Architecture Review — LLM-based Algorithmic Trading System (Alpha Miner ATS)

**Data:** 2026-05-03  
**Documenti esaminati:** `docs/LLM Trading System Integration.docx`, `CLAUDE.md`  
**Tipo di review:** Analisi critica architetturale, qualità tecnica e rischi operativi.

---

## 1. Panoramica del sistema

**Scopo:** Realizzare un Algorithmic Trading System (ATS) che sfrutta Large Language Models (LLM) per generare segnali di sentiment e, potenzialmente, strategie quantitative (fattori alfa), integrandosi con framework di esecuzione esistenti (Backtrader, Freqtrade, QuantConnect Lean).

**Tipo di trading:** Predominantemente **algorithmic / event-driven a media/bassa frequenza**. Il paradigma "Alpha Miner" esclude esplicitamente l'uso di LLM nel percorso critico di esecuzione, rendendo impraticabile l'HFT o il market-making ultra-latency. L'orizzonte temporale è compatibile con strategie di momentum o mean-reversion su timeframe minutari/orari, alimentate da sentiment di news.

**Flusso generale dei dati:**

```
[Fonti testuali & market data]
           ↓
[Background LLM Worker] → pre-computazione sentiment / generazione codice strategia
           ↓
[Redis / PostgreSQL] → storage segnali allineati temporalmente
           ↓
[Execution Engine] (Backtrader/Freqtrade/QC) → lettura segnale a ogni tick
           ↓
[Broker/Exchange] → esecuzione ordine
```

Il flusso è logicamente corretto e rispetta il vincolo fondamentale di non introdurre latenza LLM nel ciclo di trading.

---

## 2. Architettura

**Componenti principali:**

1. **Data Ingestion Layer** — non esplicitamente modellato, ma implicato dalla necessità di raccogliere news e dati di mercato. Il documento menziona feed testuali (news, social, report utili) e dati storici OHLCV.
2. **Background LLM Worker** — Cuore del paradigma Alpha Miner. Processa testi offline o in batch, genera punteggi di sentiment o codice Python strategico. L'architettura suggerisce l'uso di FastAPI + Celery + Redis per orchestrare i task asincroni.
3. **Signal Store** — Database relazionale (PostgreSQL/Aurora) o cache in-memory (Redis) per memorizzare i segnali pre-computati con timestamp.
4. **Execution Engine** — Framework di terze parti (Backtrader, Freqtrade, QuantConnect Lean) che esegue la logica di trading deterministica leggendo i segnali dal Signal Store.
5. **Risk & Fallback Layer** — Parzialmente descritto: include guardrails per allucinazioni (RAG, ensemble variance, supervisor agent) e fallback deterministico.

**Pattern architetturali:**

- **Event-Driven:** Il documento enfatizza correttamente l'event processing loop per sistemi full-stack.
- **Disaccoppiamento (Decoupling):** Il divieto di chiamate sincrone LLM nel loop di esecuzione è un pattern architetturale fondamentale e ben posto.
- **Multi-Agent (MAS):** Menzionato come paradigma avanzato (analista tecnico, fondamentale, risk manager), ma non formalizzato per questa implementazione specifica.

**Diagramma logico descritto a parole:**

Il sistema è strutturato a **pipeline asincrona**: l'ingestione di dati testuali scatta un evento che viene consumato da un worker Celery; il worker invoca l'LLM (locale o remoto) e scrive il risultato in Redis/DB. L'execution engine, sincronizzato sul clock del mercato, effettua polling o riceve push notification sul segnale disponibile. Questo schema previene il blocco del thread di esecuzione, ma introduce una **dipendenza temporale implicita** tra la freschezza del segnale e la sua validità operativa.

**Criticità:** Il documento descrive paralleli tre framework target (Backtrader, Freqtrade, QuantConnect) senza operare una scelta architetturale definitiva. Questo genera un'**ambiguità progettuale grave**: il sistema finale è pensato come un meta-framework polimorfo, o come una suite di adapter? La mancanza di una decisione vincolante complica la definizione dei contratti di interfaccia tra Signal Store e Execution Engine.

---

## 3. Gestione dei dati

**Fonti dei dati:**

- Dati di mercato strutturati: OHLCV, L2 order book (per RL tattico).
- Dati testuali non strutturati: titoli di news, report societari, social media, comunicati banche centrali.

**Ingestione e storage:**

- L'ingestione testuale è il punto di ingresso più critico dal punto di vista della sicurezza (vedi Sezione 9).
- Lo storage utilizza PostgreSQL per dati persistenti (portafoglio, segnali storici) e Redis per stato transitorio e cache.
- Il documento suggerisce l'uso di CSV come formato di scambio per i segnali pre-computati in scenari Backtrader. Questo è un **anti-pattern operativo**: CSV manca di schema enforcement, tipizzazione e meccanismi di concorrenza; per sistemi di produzione si raccomanda fortemente un formato binario con schema (Parquet, Avro, Protobuf) o un time-series database (InfluxDB, TimescaleDB).

**Latenza e gestione real-time vs batch:**

- Il paradigma Alpha Miner privilegia il batch / near-real-time per l'elaborazione LLM.
- Per il live trading, il documento propone un processo in background che ascolta WebSocket/API news, elabora tramite LLM e deposita in Redis. Questo introduce una finestra di latenza variabile (centinaia di millisecondi — secondi) tra l'evento news e la disponibilità del segnale.
- **Assunzione non documentata:** non viene definito uno SLA di freschezza del segnale. Se il worker impiega 5 secondi a processare una notizia, il segnale potrebbe già essere economicamente obsoleto in mercati ad alta volatilità.

**Qualità e validazione dei dati:**

- Sanitizzazione testuale: menzionata come requisito assoluto (omoglifi Unicode, testo nascosto). Manca però uno **schema di validazione formale** e una pipeline di data quality (es. Great Expectations, Deequ) per controllare consistenza, completezza e tempestività dei dati di mercato.
- Non viene descritto un meccanismo di deduplicazione delle news o di gestione dei ritardi di pubblicazione (embargo, leak).

---

## 4. Logica di trading

**Definizione delle strategie:**

- Le strategie possono essere generate in due modi:
  1. **Offline (Alpha Miner):** L'LLM agisce come ricercatore quantitativo, genera ipotesi e codice Python, che viene validato tramite backtest automatico prima del deploy.
  2. **Feature injection:** L'LLM produce un segnale numerico (sentiment score) che viene utilizzato come feature esogena all'interno di una strategia codificata manualmente o da RL.

**Separazione strategia / infrastruttura:**

- La separazione è buona: l'LLM non è nel loop di esecuzione. La strategia implementata nel framework di trading è puramente deterministica e matematica.
- Tuttavia, la generazione automatica di codice strategico (AlphaGPT-style) introduce un **rischio di coupling implicito**: il codice generato dall'LLM potrebbe fare assunzioni sull'API del framework che non sono formalizzate in un contratto stabile.

**Backtesting e simulazione:**

- Il documento menziona il backtest come strumento di validazione scientifica per le strategie generate. Manca però una specifica su:
  - Walk-forward analysis vs simple hold-out.
  - Simulazione realistica di slippage, commissioni e market impact.
  - Gestione del survivorship bias e del look-ahead bias (Backtrader previene intrinsecamente il look-ahead, ma il data scientist potrebbe introdurlo nella fase di preparazione feature).

**Parametrizzazione e configurabilità:**

- Per Freqtrade, il documento nota correttamente che ROI e stoploss devono essere configurati nel JSON di strategia, non hardcodati.
- Manca un sistema centralizzato di configuration management (es. Consul, Etcd, o almeno un `config.yaml` versionato) per parametrizzare i threshold di sentiment, i pesi dello scoring e i modelli LLM usati.

---

## 5. Execution & integrazione con broker/exchange

**Modalità di invio ordini:**

- Backtrader: `backtrader_ib_insync` per Interactive Brokers (IBKR). Gestione asincrona del ciclo di vita ordine tramite `notify_order()`.
- Freqtrade: nativamente integrato con exchange crypto (Binance) tramite API REST.
- QuantConnect Lean: engine C# con supporto multi-asset e multi-broker.

**Gestione errori, retry e fallback:**

- Il documento è **gravemente carente** in questa sezione. Non vengono descritti:
  - Protocolli di retry con backoff esponenziale per ordini rifiutati.
  - Gestione degli ordini parzialmente riempiti.
  - Idempotenza delle richieste di ordine (fondamentale per prevenire doppie esposizioni in caso di retry).
  - Circuit breaker per disconnessioni broker o rate-limiting da exchange.
- Il fallback deterministico (es. media mobile) è descritto a livello di *segnale*, non a livello di *infrastruttura di esecuzione*. Se il broker API va offline, il sistema non ha una strategia di graceful degradation documentata.

**Slippage, latenza e liquidità:**

- Il documento riconosce che l'uso di LLM preclude l'HFT a causa della latenza di round-trip (ms → s).
- Tuttavia, non propone tecniche di ottimizzazione dell'esecuzione (Execution Algos: TWAP, VWAP, Implementation Shortfall) per ridurre lo slippage su ordini di grande dimensione.
- La gestione della liquidità è assente: non viene modellato l'impatto dell'ordine sul portafoglio ordini (market impact), né il rischio di esecuzione su asset illiquidi.

---

## 6. Risk management

**Meccanismi di controllo rischio:**

- Il documento enuncia l'obiettivo di ottimizzare Sharpe Ratio e Maximum Drawdown, ma non fornisce una specifica ingegneristica del risk layer.
- Mancano le seguenti componenti essenziali di un sistema di trading automatico:
  - **Position Sizing engine:** non è descritto un algoritmo di dimensionamento della posizione (es. Kelly Criterion, Fixed Fractional, Volatility Targeting).
  - **Stop Loss dinamico:** menzionato per Freqtrade ma non formalizzato per gli altri framework.
  - **Maximum Exposure Limit:** non definito.
  - **Portfolio-level Risk:** correlazione tra posizioni, stress test, Value at Risk (VaR).

**Protezioni contro comportamenti anomali:**

- Ensemble variance e supervisor agent per mitigare allucinazioni LLM: buono a livello concettuale.
- Manca un **Risk Manager autonomo** con regole deterministiche e sovrascrivibili che possa bloccare l'esecuzione indipendentemente dal segnale generato (es. "se il drawdown giornaliero supera il 2%, blocca tutti i nuovi ordini").

**Fail-safe e circuit breaker:**

- **Completamente assenti.** Non è descritto alcun circuit breaker software, né procedure di kill switch per arrestare immediatamente il trading in caso di anomalia critica (es. segnale errato su 100% del portafoglio, perdita di connettività dati, spike di latenza LLM).
- In un sistema che gestisce capitale reale, l'assenza di un kill switch documentato è un **rischio operativo inaccettabile**.

---

## 7. Scalabilità e performance

**Colli di bottiglia potenziali:**

1. **LLM Inference Latency:** Il worker asincrono è il collo più evidente. Se il volume di news supera la capacità di throughput del modello (specialmente modelli proprietari con rate limiting), i segnali si accumulano in coda e diventano obsoleti.
2. **Redis single point:** Se Redis è usato come unico signal store in-memory, diventa un SPOF (Single Point of Failure). Manca una strategia di replica o failover.
3. **Backtrader single-threaded:** Il motore Cerebro di Backtrader è single-threaded nel loop `next()`. Se la logica di lettura dal Signal Store si appesantisce (es. query SQL complessa), il ciclo di tick rallenta.
4. **Data Pipeline:** L'ingestione di dati testuali grezzi (HTML scraping) non è scalabile orizzontalmente senza un message broker robusto (es. Kafka, RabbitMQ). Celery + Redis può essere sufficiente per carichi moderati, ma non per flusso di tick-level data o news ad alta frequenza.

**Strategie di scaling:**

- Scaling verticale: GPU più potenti per l'inference locale (FinGPT con LoRA).
- Scaling orizzontale: più worker Celery per parallelizzare l'elaborazione LLM su più ticker.
- Manca una strategia di sharding dei dati storici o di partitioning per backtest massivi.

**Gestione della concorrenza:**

- Celery gestisce la concorrenza dei task LLM.
- L'execution engine (Backtrader) non è concorrente per definizione; Freqtrade è vettorializzato su Pandas (GIL-bound per calcoli puramente Python).
- Per operare su multi-asset in tempo reale, potrebbe essere necessario eseguire istanze multiple del bot o migrare verso un engine nativamente multi-threaded (QuantConnect Lean è più adatto a questo scopo).

---

## 8. Affidabilità e resilienza

**Gestione dei guasti:**

- Descritto un fallback deterministico (indicatori tecnici standard) in caso di timeout o alta varianza LLM. Questo è positivo.
- **Manca completamente:**
  - Gestione della perdita di connettività con il broker (reconnect logic, stato ordini pendenti).
  - Gestione della perdita di feed dati di mercato (stale data detection).
  - Recovery dello stato del portafoglio in caso di crash del processo (persistent state machine).

**Logging, monitoring, alerting:**

- Il documento è **muto** su questi aspetti. Non viene menzionata alcuna soluzione di osservabilità (Prometheus, Grafana, Datadog, ELK).
- Metriche critiche da monitorare in un ATS (P&L real-time, latency di esecuzione, slippage, fill rate, drawdown, queue depth dei worker LLM) non sono elencate.
- Manca un sistema di alerting per anomalie (es. ordine di dimensione insolitamente grande, segnale con sentiment estremo non filtrato).

**Recovery e disaster handling:**

- Non esiste una procedura documentata di:
  - Backup e restore del database dei segnali.
  - Disaster recovery in caso di perdita dell'intero cluster (multi-AZ, multi-region).
  - Rollback di una strategia deployata automaticamente dall'Alpha Miner.

---

## 9. Sicurezza

**Gestione credenziali / API key:**

- Il documento menziona l'integrazione con broker (IBKR, Binance) e API cloud (OpenAI, Anthropic), ma **non fornisce alcuna indicazione** su come memorizzare in sicurezza le chiavi API.
- Raccomandazione critica: le API key di trading devono essere gestite tramite un secrets manager (HashiCorp Vault, AWS Secrets Manager, Azure Key Vault) con rotazione periodica. Mai in file di configurazione in chiaro o variabili d'ambiente non cifrate su disco.

**Protezione da accessi non autorizzati:**

- Manca qualsiasi considerazione su:
  - Autenticazione e autorizzazione per le API del backend FastAPI.
  - Network segmentation (VPN, VPC) per l'accesso al broker.
  - Rate limiting sulle API esposte.

**Audit e tracciabilità:**

- Non è progettato un sistema di audit trail immutabile per:
  - Tracciare ogni decisione di trading (timestamp, segnale, prezzo, quantità, motivazione LLM).
  - Registrare ogni cambio di configurazione o deploy di strategia.
- In contesti istituzionali o anche solo per debugging forense, l'audit trail è un requisito non derogabile.

---

## 10. Qualità del codice e manutenibilità

**Modularità:**

- Il documento suggerisce l'intercambiabilità dei modelli LLM (cloud vs locale) e dei framework di trading, il che implica una buona intenzione di modularità.
- Tuttavia, mancano le **interfacce astratte** (es. classi base `SignalProvider`, `ExecutionAdapter`, `RiskManager`) che rendano questa modularità concreta. Senza contratti formali, il passaggio da Backtrader a Freqtrade richiede una riscrittura della strategia.

**Testabilità:**

- Menzionato il backtest come validazione scientifica per le strategie generate dall'Alpha Miner. Questo è un test di sistema, non unitario.
- **Assenti:**
  - Unit test per il codice di scoring del sentiment.
  - Integration test per la pipeline end-to-end (news → segnale → ordine simulato).
  - Property-based testing per i guardrails (es. verificare che l'input con omoglifi venga sempre normalizzato).
  - Test di performance / load test per i worker LLM.

**Chiarezza e completezza della documentazione:**

- Il documento `LLM Trading System Integration.docx` è ricco di riferimenti accademici e best practice di alto livello. È un ottimo documento di *visione* e *ricerca*.
- Come documento di *specifica ingegneristica* è inadeguato: mancano requisiti numerici (SLO), schemi di database, diagrammi di sequenza, definizioni API, matrici di configurazione.
- La documentazione fornisce troppe alternative (tre framework, molteplici modelli LLM) senza decisioni vincolanti, trasferendo il carico decisionale sullo sviluppatore in fase di implementazione.

---

## 11. Problemi e rischi principali

| Rischio | Impatto | Descrizione |
|---------|---------|-------------|
| **R1. Ambiguità framework target** | Alto | La mancata scelta tra Backtrader, Freqtrade e QuantConnect impedisce di solidificare i contratti di interfaccia e l'architettura del deployment. |
| **R2. Assenza di circuit breaker / kill switch** | Critico | In caso di baco, segnale errato o allucinazione non rilevata, il sistema può generare ordini dannosi senza un freno automatico. Impatto diretto sul capitale. |
| **R3. Gestione credenziali non specificata** | Critico | API key di trading e LLM in chiaro espongono a furto di fondi e abuso di risorse cloud. |
| **R4. Latenza non quantificata** | Medio-Alto | Senza SLA sui segnali, il sistema potrebbe operare su dati obsoleti in fasi di alta volatilità, generando slippage eccessivo o entry tardive. |
| **R5. Rischio adversarial non mitigato oltre la sanitizzazione** | Medio | La sanitizzazione degli omoglifi è un primo passo, ma non esiste un detection engine per notizie sintetiche (deepfake testuali) o campagne di disinformazione coordinate. |
| **R6. Overfitting del backtest** | Medio-Alto | Il paradigma Alpha Miner genera codice e ottimizza iper-parametri automaticamente. Senza un processo di paper trading e walk-forward validation rigoroso, il rischio di curve-fitting è elevatissimo. |
| **R7. Dipendenza da API proprietarie** | Medio | L'uso di GPT-4o/Claude introduce costi operativi non quantificati, rate limiting imprevedibile e dipendenza da fornitori esterni per la logica di decisione. |
| **R8. Assenza di osservabilità** | Medio | Senza monitoring e alerting, i guasti passano inosservati fino a che non si manifestano come perdite economiche. |
| **R9. Rischio operativo: deploy automatico strategie** | Alto | Se l'Alpha Miner genera, backtesta e deploya codice in autonomia, un baco nel codice generato o nel validatore può introdurre logiche di trading catastrophic. |
| **R10. Conformità normativa non affrontata** | Medio | MiFID II, GDPR, SEC Rule 15c3-5 (Market Access Rule) impongono requisiti di audit, risk controls pre-trade e reporting. Il documento non li menziona. |

---

## 12. Miglioramenti suggeriti

### Quick wins (basso sforzo, alto impatto)

1. **Aggiungere un kill switch software:** Un circuit breaker basato su drawdown massimo giornaliero, esposizione massima per singolo asset o numero massimo di ordini al minuto. Deve essere in grado di bloccare l'esecuzione indipendentemente dai segnali LLM.
2. **Definire un data contract per i segnali:** Sostituire il CSV con un formato tipizzato (Protobuf, Avro, Parquet) con schema versionato, timestamp e metadati di provenienza (modello LLM, versione prompt, confidenza).
3. **Implementare un audit log minimo:** Tracciare ogni ordine emesso con la motivazione del segnale associato (snapshot del testo sanitizzato e del prompt usato) in una store append-only.
4. **Gestione secrets:** Utilizzare un secrets manager per tutte le API key. Mai hardcodate.

### Interventi strutturali (medio/alto sforzo)

5. **Scegliere un framework primario e costruire adapter:** Operare una scelta architetturale tra Backtrader (flessibile, Python puro), Freqtrade (crypto-centric, vettorializzato) o QuantConnect Lean (istituzionale, multi-asset). Definire un'interfaccia comune `ExecutionEngine` con adapter specifici per ciascun framework. Questo de-blocca la progettazione del Signal Store.
6. **Costruire un Risk Manager dedicato:** Modulo autonomo, deterministico, che filtra ogni ordine prima dell'invio al broker. Deve implementare: position sizing, max exposure, correlazione portafoglio, stop loss obbligatori. Deve poter operare anche in assenza di segnali LLM.
7. **Stabilire SLO/SLI:** Definire metriche quantitative: latenza massima end-to-end (es. 95th percentile < 500ms per segnale), throughput minimo del worker (news/minuto), disponibilità del sistema di trading (es. 99.9%).
8. **Osservabilità:** Deployare stack di monitoring (Prometheus + Grafana) e alerting (PagerDuty/Opsgenie) su metriche tecniche e di business.
9. **Model Registry e prompt versioning:** Versionare i modelli LLM usati e i prompt DK-CoT. Reproducibilità essenziale per debugging e compliance.
10. **CI/CD per Alpha Miner:** Se il sistema genera codice automaticamente, il codice deve passare attraverso una pipeline di CI (linting, type checking, unit test su dati sintetici) prima di essere deployato. L'auto-deploy senza human-in-the-loop è troppo rischioso per un sistema di trading con capitale reale.
11. **Paper trading obbligatorio:** Ogni strategia generata dall'Alpha Miner deve superare una fase di paper trading (almeno 1-3 mesi) prima di ricevere capitale reale. Documentare metriche di performance durante questa fase.
12. **Conformità e legal review:** Inserire nel piano di progetto una review normativa (MiFID II best execution, market abuse regulation) e una valutazione GDPR per il trattamento dei dati testuali.

---

## Conclusione

La documentazione esaminata fornisce una solida base teorica e un insieme di best practice aggiornate per l'integrazione LLM nel trading quantitativo. Il paradigma "Alpha Miner" è architetturalmente corretto e mitiga il rischio più grande: l'introduzione di latenza e non-determinismo nel percorso critico di esecuzione.

Tuttavia, il documento si ferma a un livello di *direttive architetturali* e *survey tecnologica*. Per diventare un documento di ingegneria eseguibile, necessita urgentemente di:

- **Decisioni vincolanti** (framework, stack di deployment).
- **Requisiti numerici** (latenza, throughput, risk limits).
- **Specifiche di sicurezza e risk management** concrete.
- **Progettazione dell'osservabilità** (logging, monitoring, alerting).
- **Procedure operative** (kill switch, paper trading, rollback).

Senza questi elementi, il rischio di perdite economiche in produzione — per baco software, allucinazione LLM, anomalia di mercato o attacco adversarial — rimane inaccettabilmente alto.
