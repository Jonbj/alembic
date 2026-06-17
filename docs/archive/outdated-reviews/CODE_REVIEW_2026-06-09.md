# Code Review Completa - 2026-06-09

## Contesto

Review approfondita dell'intero progetto Alembic, con attenzione a:

- bug funzionali e regressioni operative;
- pattern di sviluppo non corretti;
- duplicazione e mancato riuso;
- separazione dei confini di dominio;
- uso di Domain-Driven Design, servizi applicativi e adapter;
- qualita dei test e affidabilita della suite;
- contratti API/frontend.

Worktree al momento della review:

- modificato: `pyproject.toml`
- modificato: `src/api/routes/performance.py`
- vari documenti non tracciati in `docs/`

I file non sono stati modificati durante la review, a parte la creazione di questo documento.

## Verifiche Eseguite

### Python compile

Comando:

```bash
python -m compileall -q src scripts quantconnect
```

Risultato: passa.

### Frontend lint

Comando:

```bash
npm run lint
```

Risultato: fallisce con 6 errori e 3 warning.

Errori principali:

- `frontend/src/api/strategies.ts:21`: uso di `any`.
- `frontend/src/pages/Config.tsx:17`: `setState` sincrono dentro `useEffect`.
- `frontend/src/pages/News.tsx:10`: blocco `catch` vuoto.
- `frontend/src/pages/Performance.tsx:250`: mutazione di variabile durante render/memo.
- `frontend/src/pages/Strategies.tsx:5`: import inutilizzato `ReferenceLine`.
- `frontend/src/pages/Strategies.tsx:12`: import inutilizzato `Strategy`.

Warning principali:

- `frontend/src/components/layout/Layout.tsx`: dipendenze mancanti in `useEffect`.
- `frontend/src/pages/Performance.tsx`: espressione `daily` instabile come dipendenza di `useMemo`.
- `frontend/src/pages/Signals.tsx`: TanStack Virtual non compatibile con memoizzazione React Compiler.

### Backend test suite

Comando:

```bash
env UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q
```

Risultato:

```text
1952 passed, 13 failed, 35 warnings
```

Nota: il primo tentativo senza rete era fallito per DNS/PyPI. Il test completo e stato eseguito con permesso di rete.

Failure osservate:

- `tests/portfolio/test_decay_monitor.py`
  - `run_decay_check` e una funzione, ma i test si aspettano un Celery task con `.run()`.
- `tests/test_llm_client.py`
  - patch di `config.OLLAMA_API_KEY` non ha effetto sul client effettivo, quindi il test riceve `Exhausted retries` invece di `OLLAMA_API_KEY is not set`.
- `tests/workers/test_execution_worker.py`
  - accesso diretto a `redis_store._r` rompe mock e blocca il ciclo.
  - aspettative su ordine/notional non allineate al costruttore Alpaca mockato.
- `tests/workers/test_performance_worker.py`
  - warning atteso su basso `avg_net_pnl` non appare.
- `tests/workers/test_portfolio_scheduler.py`
  - `run_portfolio_cycle` e funzione, non Celery task con `.run()`.
  - import Alpaca fallisce in un test per contaminazione globale dei moduli stub.

## Findings Critici

### 1. Portfolio engine puo inviare ordini ignorando il kill-switch

File: `src/workers/portfolio_scheduler.py`

Il portfolio scheduler controlla solo `system:mode` prima di inviare ordini:

- se `system:mode` e `dry_run` o `halted`, non invia ordini;
- non controlla `killswitch_active`;
- se Redis non e leggibile, logga warning e procede comunque con submission.

Questo e pericoloso per un sistema di trading. La semantica corretta dovrebbe essere fail-closed: se Redis o lo stato operativo non sono disponibili, non inviare ordini.

Impatto:

- un kill-switch attivo potrebbe fermare il legacy execution worker ma non il portfolio scheduler;
- un outage Redis potrebbe portare a ordini non desiderati;
- il comportamento reale diverge dalla promessa operativa di controllo centralizzato.

Raccomandazione:

- introdurre un servizio unico `TradingGate` o `ExecutionGuard`;
- controllare `operator_halt`, `killswitch_active`, `system:mode`, credenziali e connettivita;
- usare lo stesso guard in legacy execution e portfolio execution;
- fallire chiuso su errore di lettura.

### 2. Stop-loss legacy subordinato al segnale fresco

File: `src/workers/execution.py`

Nel ciclo legacy:

1. legge il segnale sentiment;
2. se il segnale manca o e stale, fa `continue`;
3. solo dopo controlla le posizioni aperte e lo stop-loss.

Questo significa che una posizione gia aperta puo non essere chiusa se il sentiment non e fresco.

Impatto:

- rischio operativo diretto;
- stop-loss software non affidabile;
- comportamento contrario alla priorita naturale: prima protezione downside, poi nuove entry.

Raccomandazione:

- spostare il controllo stop-loss prima della lettura/freshness del segnale;
- usare prezzo/posizione broker come input primario;
- usare il segnale solo per entry e decision logging, non per gestione risk exit.

### 3. Vincoli portfolio applicati ai delta order, non all'esposizione finale

File:

- `src/portfolio/orchestrator.py`
- `src/portfolio/constraints.py`

L'orchestrator produce delta orders a partire da target weights. Il `ConstraintEnforcer`, pero, valida solo il notional dei BUY correnti, non l'esposizione post-trade.

Esempio:

- NAV 100k;
- posizione attuale AAPL 15k;
- cap single asset 10k;
- nuovo BUY AAPL 2k.

Il constraint vede solo 2k e passa, anche se l'esposizione finale diventa 17k.

Impatto:

- cap di singolo asset, settore e portfolio possono essere violati;
- rischio reale non coincide con rischio misurato;
- la correzione deve avvenire sul target portfolio, non solo sugli ordini.

Raccomandazione:

- modellare `PortfolioTarget` e `PostTradeExposure`;
- applicare constraints su esposizione finale;
- generare delta orders solo dopo enforcement del target;
- testare scenari con posizioni preesistenti gia oltre cap.

### 4. Constraint per-strategy quasi disattivato dal merge

File:

- `src/portfolio/orchestrator.py`
- `src/portfolio/constraints.py`

Gli ordini finali vengono marcati con `strategy_id="merged"`, ma `ConstraintEnforcer` cerca l'allocazione con:

```python
alloc_pct = allocations.get(strategy_id, 1.0)
```

Poiche `merged` non e una strategia configurata, il fallback e `1.0`, quindi il cap risulta molto piu largo del previsto.

Impatto:

- il limite di esposizione per strategia non rappresenta piu le sleeve reali;
- le contribuzioni S1/S2/S4 vengono perse nel passaggio a ordine merged;
- il logging ha dovuto reintrodurre `symbol_strategies`, segnale che il modello ordine non porta abbastanza dominio.

Raccomandazione:

- conservare attribution per ordine o per target weight;
- distinguere `CombinedOrder` da `AttributedOrder`;
- applicare constraints prima del flattening, oppure arricchire gli ordini con contributi per strategia.

### 5. Test suite contaminata da stub globali in `sys.modules`

File: `tests/workers/test_killswitch_recovery.py`

Il test inserisce stub in `sys.modules` per `alpaca`, `redis`, `src.config`, `src.workers.celery_app` e altri moduli. Non li ripulisce a fine test.

Sintomi osservati:

- failure successiva con `ModuleNotFoundError: No module named 'alpaca.data.enums'; 'alpaca.data' is not a package`;
- task Celery visti come semplici funzioni;
- risultati dipendenti dall'ordine di esecuzione.

Impatto:

- suite non deterministica;
- problemi reali possono essere mascherati o creati artificialmente;
- aumenta molto il costo di debug.

Raccomandazione:

- sostituire stub globali con fixture `monkeypatch` con teardown automatico;
- preferire patch puntuali su oggetti importati;
- evitare di stubbare package top-level gia installati;
- se serve isolamento pesante, usare `pytest.importorskip` o test separati.

## Findings Importanti

### 6. Accesso diretto a dettagli privati Redis

File:

- `src/workers/execution.py`
- `src/workers/performance.py`
- `src/store/redis_store.py`

Molti componenti accedono a `redis_store._r` direttamente. Esempi:

- scrittura `portfolio:value`;
- lettura chiavi performance;
- dedup alert overnight;
- suggestion snapshot.

Questo rompe l'incapsulamento di `RedisStore` e rende i test fragili. In `execution.py`, un mock senza `_r` causa abort del ciclo durante il blocco account fetch, generando log fuorviante: "Failed to fetch account from Alpaca".

Raccomandazione:

- aggiungere metodi pubblici a `RedisStore`;
- vietare accessi a `_r` fuori dallo store;
- introdurre interface/protocol per cache/state store nei servizi applicativi.

### 7. Configurazione YAML letta in troppi punti e con path incoerenti

File:

- `src/config.py`
- `src/api/routes/config_routes.py`
- `src/api/routes/signals.py`
- `src/api/routes/trading.py`
- `src/workers/execution.py`
- `src/workers/performance.py`
- `src/workers/portfolio_scheduler.py`

Il progetto legge `config/trading.yaml` da molti moduli, con path diversi. In `trading.py` viene usato `/app/config/trading.yaml`, mentre altrove il path e derivato dal repo.

Impatto:

- comportamento diverso tra Docker, test e dev locale;
- duplicazione parsing/default;
- cambi configurazione difficili da validare.

Raccomandazione:

- introdurre `TradingConfigRepository`;
- validare YAML con Pydantic;
- caricare config una volta per ciclo/task;
- rimuovere path hardcoded.

### 8. Endpoint config scrive YAML arbitrario senza schema

File: `src/api/routes/config_routes.py`

`POST /api/config` accetta `updates: dict`, fa deep merge e scrive direttamente su file.

Problemi:

- nessuna whitelist di sezioni;
- nessuna validazione tipi/range;
- scrittura non atomica;
- possibile configurazione parzialmente corrotta se il processo si interrompe durante write.

Raccomandazione:

- usare schema Pydantic per sezioni modificabili;
- validare range, ticker, percentuali;
- scrivere su temp file e rename atomico;
- mantenere audit log per modifiche operative.

### 9. API senza response models stabili

Molte rotte restituiscono `dict` o `list[dict]`, per esempio in `src/api/routes/trading.py`.

Impatto:

- il frontend duplica tipi TypeScript manualmente;
- cambi backend possono rompere UI senza errore statico;
- OpenAPI meno utile;
- test meno precisi.

Raccomandazione:

- definire DTO Pydantic per response e request;
- usare `response_model=...`;
- generare tipi frontend da OpenAPI, oppure centralizzare contratti in `frontend/src/api/types`.

### 10. Logging/telemetria portfolio prima del gate operativo

File: `src/workers/portfolio_scheduler.py`

Il codice scrive decisioni in `execution_decisions` prima di controllare se `system:mode` e `dry_run` o `halted`.

Impatto:

- la UI puo mostrare decisioni operative anche se nessun ordine e stato inviato;
- la semantica di `execution_decisions` diventa ambigua;
- analytics/counterfactual possono mescolare segnali "intended" e "submitted".

Raccomandazione:

- distinguere `INTENDED`, `BLOCKED_BY_MODE`, `SUBMITTED`, `FAILED`;
- spostare il gate prima del logging o includere lo stato gate nel record;
- persistire un `cycle_status`.

### 11. Rotta `/api/trades` cambia source in base a config con mapping incompleto

File: `src/api/routes/trading.py`

In portfolio mode, `/api/trades` legge ordini Alpaca e li mappa a una struttura simile ai trade DB. Questo mapping:

- non calcola P&L reale;
- tratta singoli ordini come trade;
- usa `portfolio_buy`/`portfolio_sell` come `exit_reason`;
- non lega buy e sell in round-trip;
- non usa lo stesso modello dati di `trades`.

Impatto:

- dashboard trade e analytics possono mostrare dati semanticamente diversi in base a `execution.engine`;
- UI e utente vedono "trade" che sono in realta order fills.

Raccomandazione:

- introdurre un vero `TradeLedger`;
- riconciliare ordini broker in trade round-trip;
- mantenere un solo source of truth per UI e analytics.

### 12. Nuova enrichment API weekly accoppia read path ad Alpaca live

File: `src/api/routes/performance.py`

La rotta `GET /api/performance/weekly` arricchisce il report cache con chiamate live ad Alpaca.

Problemi:

- una read API diventa dipendente da broker availability;
- il catch `except Exception: pass` nasconde errori;
- la risposta puo cambiare a ogni lettura anche se il report e "weekly";
- mescola report storico e stato live.

Raccomandazione:

- separare `weekly_report` da `live_capital_efficiency`;
- esporre campo `live_enrichment_status`;
- loggare errori in modo osservabile;
- non mutare il report cache in-place se e oggetto condiviso.

## Pattern Architetturali

### Domain-Driven Design: presente nei tipi, debole nei confini

Punti positivi:

- esistono value object/dataclass in `portfolio`, `strategies`, `models`;
- ci sono concetti di dominio chiari: signal, regime, trade, strategy, portfolio cycle, constraints;
- alcuni protocolli/adapter esistono, per esempio `Notifier` e `BrokerAdapter`.

Problema principale:

La logica applicativa vive spesso nei worker insieme a infrastruttura. I worker conoscono:

- Redis;
- PostgreSQL;
- Alpaca;
- Telegram;
- YAML;
- modelli di dominio;
- serializzazione e logging.

Questo rende difficile capire dove stia il dominio e dove inizi l'infrastruttura.

Direzione consigliata:

```text
src/domain/
  trading/
  portfolio/
  signals/
  risk/

src/application/
  run_execution_cycle.py
  run_portfolio_cycle.py
  compute_weekly_report.py

src/infrastructure/
  redis/
  postgres/
  alpaca/
  telegram/
  yaml_config/

src/api/
  routes + DTO

src/workers/
  thin Celery wrappers
```

I worker dovrebbero diventare entrypoint sottili che chiamano use case applicativi.

### Store object troppo grandi

`src/store/pg_store.py` supera 1400 righe e contiene:

- sentiment signals;
- news log;
- llm responses;
- execution decisions;
- trades;
- analytics;
- retention;
- portfolio cycles;
- weight updates.

Questo e un classico god object.

Possibile divisione:

- `SignalRepository`
- `NewsRepository`
- `TradeRepository`
- `ExecutionDecisionRepository`
- `PortfolioCycleRepository`
- `WeightRepository`
- `BudgetRepository`

Benefici:

- test piu piccoli;
- query ownership piu chiara;
- minore rischio di regressione;
- contratti piu facili da tipizzare.

### Duplicazione di accesso a broker e database

Pattern ricorrente:

- molti worker aprono `Redis.from_url`;
- molti worker aprono `psycopg2.connect`;
- varie rotte costruiscono client broker direttamente via dependency generica;
- i servizi usano `config` globale.

Raccomandazione:

- centralizzare factory e lifecycle;
- iniettare adapter nei use case;
- evitare global config nei moduli di dominio.

### Frontend: pagine troppo "smart"

Pagine grandi:

- `frontend/src/pages/Docs.tsx`
- `frontend/src/pages/Performance.tsx`
- `frontend/src/pages/Strategies.tsx`
- `frontend/src/pages/Backtest.tsx`

Problema:

Le pagine mescolano:

- query API;
- stato form;
- formatting numerico;
- mapping dati;
- layout;
- chart configuration;
- help text.

Raccomandazione:

- estrarre hook tipo `usePerformanceData`, `useStrategyDetail`;
- estrarre componenti `ChartPanel`, `MetricGrid`, `ConfigForm`, `DecisionTable`;
- centralizzare formatter (`formatCurrency`, `formatPct`, `formatDateTime`);
- usare response types generati o condivisi.

### Test: molte coperture, ma isolamento da migliorare

Punti positivi:

- suite ampia: 1965 test totali nel run osservato;
- copertura estesa su workers, portfolio, strategies, API, connectors.

Problemi:

- stub globali in `sys.modules`;
- test che patchano `src.config.config` dopo import gia avvenuti;
- test che dipendono da task Celery `.run()` ma decorator stub lo trasforma in funzione;
- mock troppo lontani dal comportamento reale Alpaca/Celery.

Raccomandazione:

- fixture centralizzate per config;
- niente patch globali persistenti;
- adapter fake invece di monkeypatch profondo;
- contract tests per broker adapter;
- test separati per dominio puro e infrastruttura.

## Priorita di Intervento

### P0 - Sicurezza operativa trading

1. Unificare kill-switch/mode guard tra legacy e portfolio engine.
2. Far fallire chiuso il portfolio scheduler se Redis non e disponibile.
3. Spostare stop-loss prima della freshness del segnale.
4. Applicare risk constraints su esposizione post-trade.

### P1 - Stabilita test e contratti

1. Rimuovere stub globali da `test_killswitch_recovery`.
2. Riparare i 13 test falliti.
3. Aggiungere test per kill-switch in portfolio scheduler.
4. Aggiungere test per stop-loss con segnale stale.
5. Aggiungere response models Pydantic alle rotte principali.

### P2 - Architettura e manutenibilita

1. Spezzare `PostgreSQLStore`.
2. Introdurre `TradingConfigRepository`.
3. Estrarre use case dai worker.
4. Rimuovere accessi a `RedisStore._r`.
5. Separare trade ledger da order feed Alpaca.

### P3 - Frontend

1. Sistemare lint.
2. Estrarre hook dati e componenti riutilizzabili.
3. Centralizzare formatter.
4. Generare o consolidare tipi API.

## Conclusione

Il progetto ha una base ricca e molti test, ma sta crescendo in modo da accumulare accoppiamento tra dominio e infrastruttura. La priorita non dovrebbe essere una grande riscrittura, ma una serie di tagli mirati:

- rendere i gate di trading centralizzati e fail-closed;
- spostare la logica di dominio fuori dai worker;
- trasformare store e config in repository/adapters con contratti espliciti;
- stabilizzare la suite eliminando patch globali;
- dare al frontend contratti e componenti riutilizzabili.

Questi interventi riducono rischio operativo e migliorano molto la velocita di sviluppo futura.
