# Forensic Daily Report — 2026-09-11 (venerdì)

**Generato:** 2026-09-14 · **Timezone operativo:** UTC — `src/workers/celery_app.py:54-55` (`timezone="UTC"`, `enable_utc=True`). Nessuna ambiguità.
**Sessione:** RTH 13:30–20:00 UTC (EDT). Pre-market 08:00–13:30 UTC, after-hours 20:00–24:00 UTC (barre Alpaca SIP).
**Modalità:** **paper**. Verificato, non assunto: `.env:52 ALPACA_BASE_URL=https://paper-api.alpaca.markets`, `docker exec alembic-worker-1 printenv` conferma lo stesso valore nel container, `portfolio_monitor_snapshots.broker_environment='paper'`, `mode='paper'`, `source='alpaca_paper'`. Motore: `config/trading.yaml → execution.engine: portfolio` (solo `portfolio-cycle` invia ordini; `run-execution` gira 32 volte a vuoto).
**Analisi:** read-only. Nessun ordine inviato, nessun worker avviato, nessuna pipeline rieseguita. Scritti solo questo file e `docs/evidence/findings.json`.
**Fonti:** `logs/containers/{worker,worker-inference,api,beat,worker-news-stream}-2026-09-11.log` (persistenti sull'host, sopravvissuti ai redeploy — vedi §11), Postgres `alembic-postgres-1`, Redis `alembic-redis-1`, API REST locale `:8001`, `docs/evidence/dossier/2026-09-11.json` (schema 3.1, generato 2026-09-14T08:00:32Z).

---

## 1. Executive summary

La pipeline ha funzionato end-to-end e ha prodotto 6 BUY e 3 SELL, tutti riconciliati a fill reali,
tutti su segnali sopra il gate 0,30, tutti dentro l'orario. NAV 109.748,67 → **109.737,29 $**
(−11,38 $, −0,010% sull'apertura; +257,14 $ contro la chiusura ufficiale precedente),
**+11,84 $ realizzati** (tutti S4) e +4,53 $ di MTM. Nessun ordine duplicato, nessun ordine su
segnale fallback, nessun roundtrip sotto i 30 minuti, nessun pyramiding, riconciliazione
ordini↔fill↔posizioni pulita (45 posizioni broker = 45 trade aperti in DB).
Il fatto della giornata non è un trade: è che **dalle 16:16 alle 17:03 UTC l'endpoint `/v2/clock`
di Alpaca ha risposto 500 e il sistema ha interpretato "orologio non disponibile" come "mercato
chiuso"**, spegnendo per 47 minuti di seduta 3 cicli di portafoglio, 11 cicli sentiment e 6 giri
di ingest — e registrando ogni task Celery come `succeeded`. Il secondo fatto è che
**527 delle 777 news accodate (67,8%) sono morte stale prima di essere valutate**, quarto giorno
consecutivo di escalation (29,0% → 37,1% → 53,1% → 67,8%): il consumatore non tiene il passo
dell'ingest e la soglia pre-registrata 0,25 è sfondata di quasi tre volte. Il terzo è il churn noto:
**due SELL su punteggio positivo** (RDDT +0,029, PLTR +0,000) costati 24,79 $ di drift lasciato
sul tavolo. Nessuna allerta è uscita dal sistema: 9 CRITICAL di decay monitor, 8 incidenti mobile
e 2 notifiche Telegram, zero consegne effettive.

## 2. Verdict finale

> **OK con warning — anomalie significative sull'infrastruttura di osservazione e di ingest, non sul money path.**

Il percorso decisionale (segnale → gate → ranking → ordine → fill → posizione → P&L) è corretto e
auditabile su tutti i 9 ordini della giornata. Le anomalie significative stanno a monte (ingest che
perde due terzi della coda, outage broker gestito con un fail-open nella direzione sbagliata) e a
valle (allerte che non escono, serie di evidenza con l'equity sbagliata). Non "processo non
affidabile": nessuna decisione della giornata è ricostruibile come errata. Non "OK" semplice:
un difetto del fail-open del clock può, in una giornata con segnali forti nella finestra sbagliata,
cancellare ordini senza lasciare traccia diversa da `succeeded`.

---

## 3. Timeline del 2026-09-11 (tutti gli orari UTC)

| ora | componente | evento | esito | fonte |
|---|---|---|---|---|
| 00:00–13:29 | `worker-news-stream` | WebSocket Benzinga ingerisce 24/7 in `news:queue`; nessun consumatore (sentiment gated `market_closed`) | coda che cresce | `worker-news-stream-2026-09-11.log`; `worker-inference` 98 skip `market_closed` |
| 13:30:00.96 | mobile alert | incident CRITICAL «Ciclo di portafoglio in ritardo» + WARNING «Segnali sentiment in ritardo» | recovered 14:07 | `mobile_events` |
| 13:30:00.01 | monitor | snapshot apertura: NAV 109.748,67 $, cash 77.185,35, 42 posizioni, gross 29,67%, drawdown 0,81% | ok | `portfolio_monitor_snapshots` |
| 13:31:12 | `sentiment-worker` | primo ciclo del giorno (`ensemble_cycle_health` id 297): 8 ensemble, 1 single, 1 FinBERT | ok | `ensemble_cycle_health` |
| 13:31:19.95 | `news_log` | prima riga scorata della giornata (ORCL/alpaca_benzinga) | ok | `news_log` |
| 13:00–14:00 | dedup/stale | **235 scarti `stale`** (età media 8,78 h) + 31 `not_tradable`: è il backlog notturno che muore alla campana | perdita | `news_queue_drops` |
| 13:42:50 | LLM | NOW scorato +0,435 (ensemble glm+gptoss), prezzo 131,455 | ok | `sentiment_signals` id 10498 |
| **14:07:00** | `portfolio-cycle` #1446 | **primo ciclo della seduta, 37 min dopo l'apertura**. BUY NOW (peso 2,0%); 3 SKIP_STALE (AAPL 19,7 h, SOXX 19,0 h, SHEL 18,3 h); SKIP_FALLBACK RDDT (+0,420, single-model); 99 SKIP_THRESHOLD | 1 ordine | `execution_decisions`, `portfolio_cycles` |
| 14:07:06 | broker | fill NOW @ **133,76** (2,31 $/azione sopra il prezzo al momento del punteggio) | filled | Alpaca order `3f4e7661` |
| 14:22:00 | #1447 | BUY ADBE +0,353 → fill @ 246,14; stop protettivo NOW sell **10** (posizione 10,757) | 2 ordini | `trades` 994 |
| 14:22:05 / 14:37:06 | Telegram | alert #161 (posizioni non proteggibili) → **HTTP 400 Bad Request** ×2 | non consegnato | `worker-2026-09-11.log` |
| 14:52:00 | #1449 | **SELL RDDT** `[below_entry_gate]` con **score +0,029** (età 0,2 h) → fill @ 155,20, net **−5,88 $** | uscita su segnale positivo | `execution_decisions` 21530 |
| 15:37:00 | #1452 | BUY SPCX +0,539 → 148,03; BUY PLTR +0,355 → 166,86 (stesso ciclo, simboli distinti) | 2 ordini | `trades` 995/996 |
| 16:07:00 | #1454 | **SELL ADBE** `[below_entry_gate]` con score **−0,135**, tenuta 105 min, net **+16,27 $** | uscita su flip reale | `trades` 994 |
| 16:07:04 | S1 | «dropped 2 sparse/stale-tailed ticker(s): AZN, SPCX»; gate di ribilanciamento chiuso (41 posizioni) | ok | `worker` log |
| **16:16:03** | Alpaca | **`/v2/clock` inizia a rispondere `{"message":"Internal Server Error"}`** → incident mobile CRITICAL «Degradazione market_clock» | inizio outage | `worker` log, `mobile_events` |
| 16:22 / 16:37 / 16:52 | `portfolio-cycle` | 3 cicli abortiti: `{'error': 'clock_unavailable'}` — **task Celery `succeeded`** | 3 cicli persi | `worker` log; `portfolio_cycles` ha 21 righe su 24 slot |
| 16:18–17:03 | `sentiment-worker` | **11 esecuzioni** chiuse con `{'skipped': True, 'reason': 'market_closed'}` in piena seduta | pipeline ferma | `worker-inference` log |
| 16:30 / 17:00 | ingest | `run_news_ingestion_worker` e `run_alpaca_ingestion_worker` → `{'skipped': True, 'reason': 'market_closed'}` (6 giri) | ingest fermo | `worker` log |
| 16:27–16:30 | Alpaca dati | `#295: Alpaca calendar unavailable`; `#297: bars unavailable` per PLTR, SPCX, HOOD, RDDT, AZN, NVDA, NOW, DIS; `SPY benchmark fetch failed` ×2 | degrado diffuso | `worker` log |
| 17:03:03 | Alpaca | ultimo 500 sul clock → **47 minuti di outage** | fine outage | `worker` log |
| 17:04:00 | mobile alert | CRITICAL «Ciclo di portafoglio in ritardo» + WARNING «Segnali sentiment in ritardo», entrambi `recovered` | osservato, non consegnato | `mobile_events` |
| 17:07:00 | #1455 | ciclo ripreso. SKIP_PYRAMIDING AMD (+0,420, posizione 418 $ su target 2.614 $) e AMAT | 0 ordini | `execution_decisions` |
| 17:22:00 | #1456 | SKIP_PYRAMIDING DELL (+0,390, posizione 519 $ su target 2.715 $) | 0 ordini | idem |
| 18:04:20 | LLM | TSLA scorato +0,366 | ok | `sentiment_signals` 10637 |
| 18:07:00 | #1459 | BUY ORCL +0,606 → fill @ 152,49 | 1 ordine | `trades` 997 |
| 18:22:00 | #1460 | **SELL PLTR** `[below_entry_gate]` con score **+0,000** (età 0,5 h), tenuta 165 min, net **+1,45 $** | uscita su segnale non negativo | `trades` 996 |
| 18:07–18:52 | ranking S4 | TSLA (+0,366, sopra gate, fresco) resta **rank 6 di top-5** per 4 slot: `RANK_OUTSIDE_TOP_N` nel ledger, **nessuna riga in `execution_decisions`** | invisibile 60 min | `s4_intent_events` |
| 19:07:00 | #1463 | BUY TSLA +0,366 → fill @ 364,74 (`SUBMITTED`, rank 5); **SKIP_PYRAMIDING ORCL +0,630** (comprata 1 h prima) | 1 ordine | `execution_decisions` 21961 / 21833 |
| 19:37:00 | #1465 | SKIP_PYRAMIDING BAC (+0,314, posizione 717 $ su target 2.912 $) | 0 ordini | idem |
| 19:52:00 | #1466 | ultimo ciclo della seduta | 0 ordini | `portfolio_cycles` 1466 |
| 19:57:32 | `news_log` | ultima riga scorata | ok | `news_log` |
| 20:00:00 | monitor | snapshot chiusura: NAV **109.737,29 $**, cash 73.276,07, **45 posizioni**, gross 33,23%, unrealized +1.148,07 | ok | `portfolio_monitor_snapshots` |
| 20:00–22:00 | ingest/sentiment | 24 skip `market_closed` (comportamento atteso) | ok | log |
| 21:00:00 | `decay-monitor` | **9 righe CRITICAL** per S1, S2 e S4 con **valori identici** (IC 0,035→−0,056, hit rate −23,1 pp, Sharpe 0,11) | solo `log.critical` | `worker` log |
| 22:45:00 | `counterfactual-worker` | calcolo `counterfactual_return_1h` sulle righe SKIP | ok | `execution_decisions` |
| 22:50:00 | mobile alert | WARNING «Griglia portfolio-cycle fuori seduta»; «Copertura news assente su ASML» e «su SBUX» | osservati | `mobile_events` |
| 22:55:00 | `stale-drop-alert` | `{'status':'ok','measured':2,'alerted':1}` — **alpaca_benzinga 0,678 > soglia 0,25** | allerta emessa, non consegnata | `worker` log, `stale_drop_metrics_daily` |
| 23:45:27 | `ingestion_stats_daily` | consolidamento contatori del giorno | ok | Postgres |

**Nessun restart di worker**: nessuna riga `celery@… ready`, `Warm shutdown` o `Cold shutdown` in
`worker-2026-09-11.log` né in `worker-inference-2026-09-11.log`.

---

## 4. News ingest

### 4.1 Per fonte

| fonte | fetched | queued | duplicates | no_ticker | stale | parse_fail | righe `news_log` | ticker distinti | quota stale |
|---|---|---|---|---|---|---|---|---|---|
| `alpaca_benzinga` | 1.417 | 779 | **6.650** | 0 | **527** | 0 | 166 | 53 | **67,8%** |
| `gdelt_gkg` | 1.531 | 8 | 1 | **1.522** | 0 | 0 | 8 | 7 | 0% |
| **totale** | 2.948 | 787 | 6.651 | 1.522 | 527 | 0 | **174** | 57 | — |

Scarti per motivo e stadio (`news_queue_drops`, finestra `dropped_at` sul giorno):

| motivo | stadio | n | di cui accodati fuori seduta | età media |
|---|---|---|---|---|
| `duplicate_id` | ingestion | 6.650 | 1.049 | — |
| `no_ticker` | ingestion | 1.522 | 0 | — |
| `stale` | sentiment | 527 | 235 | 7,45 h |
| `not_tradable` | sentiment | 131 | 35 | — |
| `duplicate_content` | ingestion | 1 | 0 | — |

Distribuzione oraria degli scarti `stale`: **235 fra le 13:00 e le 14:00** (età media 8,78 h — è il
backlog notturno che muore alla campana), poi 149 / 8 / 17 / 31 / 50 / 37 nelle ore successive.

### 4.2 Copertura temporale e qualità

* Prima riga scorata 13:31:19, ultima 19:57:32. **Nessuna riga `news_log` prima dell'apertura**: non è
  un buco di ingest, è che `news_log` registra il *consumo* (il WebSocket accoda 24/7, il consumatore
  è gated su `is_market_open()`).
* Latenza mediana `published_at → fetched_at` **0,29 h**, mediana in coda **0,26 h** — ma è un dato
  di sopravvissuti: i 527 articoli morti stale avevano età media 7,45 h.
* **0** timestamp futuri, **0** `published_at` NULL, **0** titoli vuoti, **0** `raw_ingested_at` NULL,
  **1** corpo sotto i 40 caratteri. 40 righe su 174 hanno `published_at` fuori RTH (backlog).
* Lunghezza media corpo **388 caratteri** (era ~151 in agosto): la deroga #454 `include_content` è
  operativa. Titolo medio 82 caratteri, presente su tutte le righe ed entra nel prompt (deroga #399).
* `extraction_method`: `source_metadata` 166 (alpaca_benzinga), `org_lookup` 8 (gdelt_gkg). Nessun `NULL`.
* **Sanitizzazione presente e applicata**: `src/text/sanitizer.py` (NFKC + rimozione homoglifi) è
  invocata in `src/workers/sentiment.py:425-426` su corpo e titolo *prima* del troncamento, e
  `sanitize_ticker` sul simbolo (`:433`). Il deduplicatore normalizza a sua volta in NFKC
  (`src/connectors/deduplicator.py:43-44`).

### 4.3 Per ticker (top 15 per righe scorate)

| ticker | righe | articoli unici | prima pubblicazione | ultima |
|---|---|---|---|---|
| ORCL | 19 | 19 | 12:46:59 | 18:54:25 |
| ADBE | 16 | 16 | 12:04:05 | 16:53:39 |
| SPY | 12 | 12 | 12:42:40 | 18:20:34 |
| NVDA | 9 | 9 | 12:45:02 | 19:34:19 |
| META / AMZN / QQQ / GOOGL / TSLA / MSFT / AAPL | 5 ciascuno | 5 | 11:46–14:48 | 17:27–19:34 |
| PLTR / AMD / XLK | 4 ciascuno | 4 | 12:46–16:21 | 17:35–18:30 |
| DELL / CVX / LLY / RDDT / NOK / HOOD / MS / SPCX | 3 ciascuno | 3 | — | — |

### 4.4 Fan-out e rilevanza

101 articoli unici → 174 righe. **25 articoli multi-ticker generano 98 righe (56,3% del totale)**;
il peggiore ne genera 10, due ne generano 8. Classificazione del dossier:
`ISSUER_SPECIFIC` 75, **`TAG_UNCONFIRMED` 98**, `FALSE_ENTITY_MATCH` 1, `CONTENT_EMPTY` 1, `SECTOR_MACRO` 0.
Copertura *effective timely* (issuer-specific, tempestivo, non vuoto): **38 ticker su 96 = 39,6%**.

### 4.5 Top news per impatto sul segnale

I 14 segnali sopra il gate 0,30 della giornata:

| ora | ticker | score | conf | ens_std | fallback | esito |
|---|---|---|---|---|---|---|
| 18:54 | ORCL | **+0,630** | 0,800 | 0,177 | no | SKIP_PYRAMIDING (già comprata alle 18:07) |
| 18:04 | ORCL | +0,606 | 0,825 | 0,071 | no | **BUY** |
| 14:15 | ORCL | +0,560 | 0,800 | 0,000 | no | sotto rank |
| 15:17 | ORCL | +0,560 | 0,800 | 0,000 | **sì** | SKIP_FALLBACK |
| 15:30 | SPCX | +0,539 | 0,775 | 0,283 | no | **BUY** |
| 13:42 | NOW | +0,435 | 0,725 | 0,000 | no | **BUY** |
| 13:37 | RDDT | +0,420 | 0,700 | 0,000 | **sì** | SKIP_FALLBACK |
| 17:06 | AMD | +0,420 | 0,700 | 0,000 | no | SKIP_PYRAMIDING (418 $ su 2.614 $ target) |
| 17:15 | DELL | +0,390 | 0,600 | 0,354 | no | SKIP_PYRAMIDING (519 $ su 2.715 $) |
| 18:04 | TSLA | +0,366 | 0,650 | 0,035 | no | **BUY** (dopo 60 min a rank 6) |
| 15:31 | PLTR | +0,355 | 0,650 | 0,141 | no | **BUY** |
| 14:20 | ADBE | +0,354 | 0,700 | 0,106 | no | **BUY** |
| 19:02 | MRVL | +0,316 | 0,725 | 0,035 | no | SKIP_PYRAMIDING |
| 19:34 | BAC | +0,314 | 0,625 | 0,106 | no | SKIP_PYRAMIDING (717 $ su 2.912 $) |

**Confidenza dell'analisi news: Alta.** Contatori, scarti e righe scorate sono su tre tabelle
indipendenti (`ingestion_stats_daily`, `news_queue_drops`, `news_log`) che concordano.

---

## 5. Valutazione LLM

Ensemble attivo: `glm-5.2:cloud` + `gpt-oss:20b-cloud` (Redis `config:sentiment_llm_models = glm52,gptoss`),
pesi `{glm 0,70; gpt-oss 0,30}` (`ensemble:weights:current`, `source: auto_apply`).

| modello | richieste | `eligible=true` | polarity media | confidence media | timeout Ollama | primo | ultimo |
|---|---|---|---|---|---|---|---|
| `glm-5.2:cloud` | 168 | 64 (38,1%) | +0,105 | 0,384 | 6 | 13:31:19 | 19:57:32 |
| `gpt-oss:20b-cloud` | 161 | 64 (39,8%) | +0,063 | 0,445 | 13 | 13:31:19 | 19:57:32 |

* **Refusal / output non parsabile: 0.** Nessuna riga di parse-fail nei log, `parse_fail = 0` su
  entrambe le fonti in `ingestion_stats_daily`.
* **Errori: 19 timeout a 90 s su ~340 tentativi (5,6%).** Nessun 429, nessun 5xx verso `ollama.com`
  (i 610 «429» del grep iniziale sono falsi positivi: sono i `?timeout=` degli URL Telegram).
  **Ollama è rimasto up tutta la sessione: 0 ore di downtime.**
* **Latenza per richiesta: non misurata.** `llm_responses` non ha colonna di latenza e i log non la
  emettono. Proxy disponibile: durata dei 50 cicli (`cycle_ended_at − cycle_started_at`), da 42 s a 10 min.
* **Composizione dell'ensemble sui 174 segnali** (`ensemble_cycle_health`, 50 cicli, 1 marcato `rth=false`):
  **117 full-ensemble (67,2%)**, **52 single-model (29,9%)**, **5 FinBERT (2,9%)**.
  `sentiment_signals.fallback_used = true` su **57/174 (32,8%)** — copre *sia* il single-model *sia* FinBERT.
* Distribuzione score: 80 righe su 174 nella banda [0,000; 0,096], 36 in [0,100; 0,194],
  39 negative (min −0,266), **14 sopra il gate 0,30**, massimo +0,630. Nessuno score a |1|.
* **Disaccordo fra modelli:** su 159 coppie complete, gap medio |Δpolarity| = **0,105**;
  **4 casi di segno opposto**, 3 con gap ≥ 0,50. Il peggiore: SPY con glm +0,20 contro gpt-oss −0,40.
* **Casi di dominanza di un singolo modello:** 52 segnali nati da un solo modello (l'altro in timeout).
  Questi sono correttamente marcati `fallback_used` e **bloccati a valle**: 25 righe `SKIP_FALLBACK`
  in `execution_decisions`, fra cui RDDT +0,420 e ORCL +0,560 — due segnali forti scartati per provenienza.
* **FinBERT:** 5 fallback totali (ORCL, MS, DIS, AMAT + 1), tutti preceduti da
  «All ensemble models timed out for X, using FinBERT fallback».

### Verifica funzionale

| domanda | risposta | evidenza |
|---|---|---|
| L'output LLM è validato prima del signal store? | **Parzialmente.** Lo schema JSON è forzato (function calling) e il parse non fallisce mai; ma non c'è validazione di enum né normalizzazione dei campi qualitativi (`directness`, `event_type`) — F-055 | `llm_responses` |
| L'ensemble gestisce la varianza alta? | **No.** `ensemble_std` è calcolato e persistito ma **non è mai un gate**: SPY con +0,20/−0,40 produce comunque un segnale — F-037 | §10 [DAY-012] |
| Le news duplicate pesano più volte? | **No a livello articolo** (dedup per `article_id` + `content_hash`, 6.651 scarti), **sì a livello ticker**: un articolo multi-ticker produce N righe indipendenti — F-012 | §4.4 |
| La stessa news può generare segnali multipli? | Sì, uno per ticker taggato. Vincolo `unique_signal_per_symbol_time` impedisce il doppione sullo stesso simbolo | schema `sentiment_signals` |
| Confidence bassa riduce il peso? | **Sì**, `score = polarity × confidence` è applicata: es. WMT polarity ≠ 0 con conf 0,15 → score 0,000 | `/api/signals` |
| I modelli sono chiamati offline? | **Sì.** Tutte le chiamate Ollama stanno in `worker-inference` (coda `inference`, concurrency 1). Il `portfolio-cycle` legge solo da Postgres/Redis: i 21 cicli durano < 8 s ciascuno | log |
| Rischio che un'allucinazione entri in decisione? | **Contenuto ma non nullo.** Il gate 0,30, il `SKIP_FALLBACK` e il ranking top-5 filtrano; ma non esiste supervisor agent né verifica RAG delle affermazioni quantitative, e `ensemble_std` non gatea | §10 |

---

## 6. Segnali, decisioni e ordini

### 6.1 Decision Log del giorno

620 righe in `execution_decisions` (tick 14:07 → 19:52):

| decisione | n | note |
|---|---|---|
| `SKIP_THRESHOLD` | 576 | score sotto 0,30 (soglia attiva `feedback:entry_threshold:S4 = 0.3`) |
| `SKIP_FALLBACK` | 25 | segnali single-model esclusi dal ranking BUY (#108) |
| `SKIP_PYRAMIDING` | 7 | guard P0-05 |
| `BUY` | 6 | |
| `SKIP_STALE` | 3 | AAPL 19,7 h, SOXX 19,0 h, SHEL 18,3 h |
| `SELL` | 3 | tutte `[below_entry_gate]` |

`regime_mult = 0,700` su tutte le righe (regime `sideways`, VIX 17,84 — Redis `regime:current`).
Peso target uniforme **2,0% del NAV** per ogni BUY S4 (slot fisso `bucket 10% / top-5`).

### 6.2 Ordini generati ed eseguiti

| ora | ticker | azione | qty | prezzo atteso | fill | stato | motore | segnale causante | risk check | anomalie |
|---|---|---|---|---|---|---|---|---|---|---|
| 14:07:05 | NOW | BUY | 10,757 | 131,455 (al punteggio) | **133,76** | filled | paper Alpaca | 10498 (+0,435) | gate 0,30 ✓, EMA ✓, pyramiding ✓ | +2,31 $/az. di drift (§10 DAY-004) |
| 14:22:05 | ADBE | BUY | 5,845 | 247,055 | **246,14** | filled | paper Alpaca | 10536 (+0,353) | ✓ | — |
| 14:22:05 | NOW | SELL (stop) | **10** | — | — | **new** (resting) | paper Alpaca | — | — | copre 92,9% della posizione |
| 14:37:06 | ADBE | SELL (stop) | **5** | — | — | canceled 16:07 | paper Alpaca | — | — | copriva 85,5% |
| 14:52:05 | RDDT | SELL | 9,278 | — | **155,20** | filled | paper Alpaca | **nessuno (`signal_id` NULL)** | below_entry_gate | **score +0,029, positivo** |
| 15:37:06 | SPCX | BUY | 9,725 | 148,27 | **148,03** | filled | paper Alpaca | 10565 (+0,539) | ✓ | — |
| 15:37:06 | PLTR | BUY | 8,628 | 166,74 | **166,86** | filled | paper Alpaca | 10569 (+0,355) | ✓ | — |
| 15:52:06 | PLTR | SELL (stop) | **8** | — | — | canceled 18:22 | paper Alpaca | — | — | copriva 92,7% |
| 15:52:06 | SPCX | SELL (stop) | **9** | — | — | **new** (resting) | paper Alpaca | — | — | copre 92,5% |
| 16:07:05 | ADBE | SELL | 5,845 | — | **249,06** | filled | paper Alpaca | **NULL** | below_entry_gate | score −0,135 (flip reale) |
| 18:07:05 | ORCL | BUY | 9,373 | 151,97 | **152,49** | filled | paper Alpaca | 10636 (+0,606) | ✓ | — |
| 18:22:08 | PLTR | SELL | 8,628 | — | **167,12** | filled | paper Alpaca | **NULL** | below_entry_gate | **score +0,000** |
| 18:22:08 | ORCL | SELL (stop) | **9** | — | — | **new** (resting) | paper Alpaca | — | — | copre 96,0% |
| 19:07:06 | TSLA | BUY | 3,940 | 364,365 | **364,74** | filled | paper Alpaca | 10637 (+0,366) | ✓ | 60 min a rank 6/5 |
| 19:22:06 | TSLA | SELL (stop) | **3** | — | — | **new** (resting) | paper Alpaca | — | — | copre **76,1%** |

15 ordini totali: 6 BUY (tutti filled), 3 SELL di uscita (tutti filled), 6 stop protettivi
(4 resting a fine giornata, 2 cancellati alla chiusura della posizione). **Nessun reject.**

### 6.3 Combiner, cap e circuit breaker

* Il **portfolio combiner gira**: `portfolio_cycles.final_orders` contiene 3–6 ordini target per ciclo
  (la differenza fra 3–6 target e 0–2 ordini effettivi è la banda di ribilanciamento; F-014 avverte
  che `orders_count` conta i target, non le sottomissioni).
* **`constraints_fired` è `[]` su tutti e 21 i cicli.** Nessun cap settoriale, di esposizione o di
  concentrazione ha mai fatto firing, e la colonna non distingue «nessun vincolo violato» da
  «nessun vincolo valutato» (§10 [DAY-015]).
* Gross exposure 29,67% → 33,23%, drawdown 0,81% → 0,82%: entrambi lontanissimi dai limiti.
  **Nessun circuit breaker attivo.** Il breaker del fallback non ha sparato (5 FinBERT sparsi su 50 cicli).
* Il guard anti-pyramiding P0-05 ha bloccato 7 ingressi, **5 dei quali su segnali sopra il gate**
  (ORCL +0,630, AMD +0,420, DELL +0,390, MRVL +0,316, BAC +0,314) con posizioni residue fra il
  **16% e il 25% dello slot target** — comportamento noto (F-031, già registrato per questa seduta).
* Distinzione paper/live: unica, esplicita e verificata (§intestazione). Non esiste una classe broker
  live nel path: `alpaca-py` diretto in `portfolio_scheduler.py`.

---

## 7. Rendimento e P&L

### 7.1 Quadro del giorno

| grandezza | valore | fonte |
|---|---|---|
| NAV apertura (13:30) | 109.748,67 $ | `portfolio_monitor_snapshots` |
| NAV chiusura (20:00) | **109.737,29 $** | idem |
| Variazione intra-seduta | **−11,38 $ (−0,010%)** | differenza |
| `nav_change_today` a 20:00 (vs chiusura ufficiale precedente 109.480,15 $) | **+257,14 $** | idem |
| Realizzato del giorno | **+11,84 $** (tutto S4, S1 = 0) | `trades` + `market_daily.jsonl` |
| MTM del giorno | +4,53 $ | `market_daily.jsonl` |
| Unrealized a chiusura | +1.148,07 $ | snapshot |
| Cash | 77.185,35 → 73.276,07 $ | snapshot |
| Posizioni | 42 → 45 | snapshot |

**Attenzione:** le due letture della variazione non sono in contraddizione, misurano oggetti diversi.
−11,38 $ è open→close del NAV; +257,14 $ include il gap notturno su 42 posizioni. Il dossier
(`decision_quality`) misura la terza: su 32.265,44 $ di nozionale detenuto all'apertura,
**P&L passivo +9,34 $**, **P&L effettivo −14,50 $**, quindi **effetto attivo delle uscite −23,84 $**.

### 7.2 Per trade chiuso

| trade | ticker | aperta | chiusa | tenuta | qty | entry | exit | **net P&L** | costo | motivo | drift post-uscita |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 992 | RDDT | 2026-09-10 18:07 | 14:52 | 20,75 h | 9,278 | 155,67 | 155,20 | **−5,88 $** | — | `portfolio_sell` | **+23,84 $** |
| 994 | ADBE | 14:22 | 16:07 | 1,75 h | 5,845 | 246,14 | 249,06 | **+16,27 $** | 0,79 $ | `hold_minimum_expiry` | +18,53 $ |
| 996 | PLTR | 15:37 | 18:22 | 2,75 h | 8,628 | 166,86 | 167,12 | **+1,45 $** | 0,79 $ | `portfolio_sell` | +0,95 $ |
| | | | | | | | | **+11,84 $** | | | **+43,32 $ lasciati** |

### 7.3 Posizioni aperte il 2026-09-11 (MTM a chiusura, dal dossier)

| trade | ticker | ora | entry | qty | **MTM EOD** | percentile d'ingresso | quota del movimento già avvenuta al segnale |
|---|---|---|---|---|---|---|---|
| 993 | NOW | 14:07 | 133,76 | 10,757 | **−13,23 $** | **0,830** | **1,606** (il movimento era finito) |
| 995 | SPCX | 15:37 | 148,03 | 9,725 | **+30,89 $** | 0,356 | −1,636 |
| 997 | ORCL | 18:07 | 152,49 | 9,373 | **−20,69 $** | 0,164 | 0,844 |
| 998 | TSLA | 19:07 | 364,74 | 3,940 | **+2,76 $** | 0,445 | 0,435 (denominatore degenere) |
| | | | | | **−0,27 $** | | |

### 7.4 Per strategia

Posizioni detenute all'apertura (`decision_quality.opening_snapshot`, 42 righe):

| strategia | n | nozionale apertura | P&L intraday effettivo |
|---|---|---|---|
| S1 | 37 | 26.112 $ | **−28,48 $** |
| S4 | 5 | 6.153 $ | **+13,98 $** |

Attribuzione beta=1 sullo stesso insieme: mercato **−18,14 $**, settore incrementale −1,91 $,
residuo **+29,39 $**. La giornata è stata di rally largo su hardware legacy (DELL +11,98%,
CSCO +4,37%, ARM +4,17%, MRVL +4,03%, TXN +3,82%; SPY +0,85%, QQQ +0,87%, 7 mover ≥3% **tutti al rialzo**):
il libro long-only ha partecipato poco perché 4 dei 7 mover erano già detenuti con nozionale
residuo minimo e 3 non sono stati presi.

### 7.5 Slippage e costi

* Costi modellati sui 6 ingressi: **5,79 $** totali (`trades.cost_usd`, da 0,25 $ su TSLA a 1,48 $ su SPCX).
* **Lo slippage non è misurato**: `trades.slippage_est` è popolato solo sui 2 trade chiusi ed è
  **identico a `cost_usd`** (ADBE 0,7921831711898006 in entrambe le colonne) — F-015, difetto noto.
  La qualità di esecuzione della giornata **non è valutabile** da questa colonna. Ricostruzione grezza
  dal dossier (prezzo alla decisione vs fill): NOW +0,51 $/az. avverso, ADBE −0,92 $/az. favorevole,
  SPCX −0,24 favorevole, PLTR +0,12 avverso, ORCL +0,52 avverso, TSLA +0,38 avverso.

### 7.6 P&L economico della finestra di osservazione (as-of 2026-09-11)

| serie | cumulato | soglia carta | dentro? |
|---|---|---|---|
| S4 | **−707,41 $** | ±200 $ | **no** |
| S1 | +948,72 $ (vs SPY +843,12 $ → **Δ +105,60 $**) | — | — |
| Book | +206,47 $ | — | — |
| Contaminazione | −34,84 $ (n=1) | — | — |
| Sedute osservate | **27 su 40** | minimo 40 | **no** (§10 [DAY-017]) |

---

## 8. Correttezza funzionale buy/sell

| controllo | esito | evidenza |
|---|---|---|
| BUY solo quando consentito | ✅ | 6/6 su score ≥ 0,30, non-fallback, non-stale, rank ≤ 5, `ema_pass=true`, nessuna posizione preesistente |
| SELL/exit generati correttamente | ⚠️ | 3/3 tecnicamente conformi a `below_entry_gate`, ma **2 su score ≥ 0** (§10 [DAY-003]) |
| Stop-loss rispettati | ⚠️ | 6 stop piazzati 15 min dopo l'ingresso, ma **solo sulla parte intera** (76,1%–96,0%) — §10 [DAY-011]. Nessuno è scattato. `stop_decisions` è vuota dal 2026-07-14 |
| Signal flip rispettato | ✅ | ADBE uscita su −0,135 |
| Max holding days rispettato | ✅ | tenute 1,75 h / 2,75 h / 20,75 h, tutte ≪ limite |
| Rebalance band rispettata | ✅ | 3–6 ordini target per ciclo, 0–2 sottomessi |
| Ordini duplicati | ✅ nessuno | 15 ordini, `order_id` distinti; SPCX e PLTR condividono il tick 15:37:06 ma sono simboli diversi |
| Ordini contrari ravvicinati | ✅ nessuno | roundtrip minimo **105 min** (ADBE). Nessun BUY→SELL→BUY nella stessa seduta |
| Pyramiding (>3 BUY senza SELL) | ✅ nessuno | 6 BUY su 6 simboli distinti; 7 tentativi bloccati da P0-05 |
| Ordini su ticker non consentiti | ✅ nessuno | NOW, ADBE, PLTR, SPCX, ORCL, TSLA, RDDT sono tutti in `config/trading.yaml → watchlist` (SPCX: riga 119, aggiunto 2026-06-30; è mappato in `sectors.etf_broad`) |
| Ordini fuori orario | ✅ nessuno | primo 14:07:05, ultimo 19:22:06, tutti dentro 13:30–20:00 |
| Trade su dati stale | ✅ nessuno | 3 SKIP_STALE emessi; nessun BUY su segnale > 4 h |
| Trade su output LLM non valido | ✅ nessuno | 0 parse-fail; 25 SKIP_FALLBACK |
| Trade con circuit breaker attivo | ✅ n/a | nessun breaker attivo |
| Trade su strategia disabilitata | ✅ nessuno | S4 attiva, S1 in gate di ribilanciamento chiuso (comportamento #185 corretto) |
| Paper/live coerente | ✅ | unica modalità, verificata su 3 fonti |
| Idempotenza retry Celery | ✅ osservata | `SKIP_IDEMPOTENCY` su TSLA al ciclo 19:22; `SIGNAL_DUPLICATE_SKIP` su NOW/PLTR/SPCX ai cicli successivi all'ingresso |
| Riconciliazione ordini↔fill↔posizioni | ✅ | 45 posizioni broker = 45 `trades` con `exit_time IS NULL`. 6 trade del giorno hanno `entry_order_id` corrispondente a un ordine `filled` |

**Nota obbligatoria su `exit_mechanism` (#184):** questo report **non** conta né interpreta
`execution_decisions.exit_mechanism`. Le 3 uscite della giornata sono classificate dal testo di
`reason` (`[below_entry_gate]`, tutte e tre) e da `trades.exit_reason`, che sono osservati, non dedotti
dall'età dell'ultimo segnale. Nessuna delle affermazioni di questa sezione dipende da righe pre-fix.

### Pattern operativi richiesti

| pattern | esito |
|---|---|
| Roundtrip < 30 min | **nessuno** (minimo 105 min) |
| BUY ripetuto > 3 volte senza SELL | **nessuno** |
| SELL con sentiment positivo (A5) | **2**: RDDT +0,029, PLTR +0,000 → [DAY-003] |
| `fallback_used=True` su tutti i simboli in un periodo | **no**: 32,8% sull'intera giornata, mai 100% in una finestra; Ollama sempre up |
| NO-ORDER (decisione creata, ordine assente) | **nessuno**: 6 BUY su 6 con `order_id` e fill |
| Score < 0,05 che generano ordini | **2 in uscita** (RDDT +0,029, PLTR +0,000); **nessuno in ingresso** |
| Ordini identici nello stesso minuto | **nessuno** |

---

## 9. Anomalie del 2026-09-11

### [DAY-001] (F-074) Outage `/v2/clock`: il fail-open è «mercato chiuso» e il blast radius va oltre i cicli portfolio

* **Tipo:** Bug
* **Area:** Ops / Broker
* **Evidenza:**
  * file/log/tabella: `logs/containers/worker-2026-09-11.log`, `worker-inference-2026-09-11.log`; `portfolio_cycles`; `mobile_events`
  * timestamp: 2026-09-11 **16:16:03 → 17:03:03 UTC** (47 minuti, in piena RTH)
  * snippet:
    ```
    16:22:03 ERROR  Could not fetch market clock: {"message":"Internal Server Error"}
    16:22:03 INFO   Task run_portfolio_cycle[7bde9346] succeeded in 3.65s: {'error': 'clock_unavailable'}
    16:30:03 ERROR  Could not fetch Alpaca market clock: {"message":"Internal Server Error"}
    16:30:03 INFO   Market closed — skipping GDELT ingestion
    16:30:03 INFO   Task run_news_ingestion_worker succeeded: {'skipped': True, 'reason': 'market_closed'}
    16:18:51 INFO   Task run_sentiment_worker succeeded: {'skipped': True, 'reason': 'market_closed'}
    ```
    ```sql
    SELECT count(*) FROM portfolio_cycles WHERE timestamp::date='2026-09-11';  -- 21, su 24 slot
    ```
* **Descrizione:** quando `/v2/clock` risponde 500, tre componenti distinti reagiscono e **tutti e
  tre nella direzione sbagliata**. Il ciclo di portafoglio esce con `{'error':'clock_unavailable'}`
  ma il task Celery è marcato `succeeded` (3 cicli persi: 16:22, 16:37, 16:52). Il worker sentiment e
  i due worker di ingest interpretano l'assenza di risposta come **«mercato chiuso»** e si spengono:
  11 esecuzioni sentiment e 6 giri di ingest saltati durante la seduta. In parallelo si degradano il
  calendario (`#295: Alpaca calendar unavailable`) e le barre (`#297: bars unavailable` su 8 simboli)
  e il benchmark SPY fallisce. L'unica traccia oltre i log è un incident `mobile_events` CRITICAL
  «Degradazione market_clock» alle 16:16, che non è stato consegnato a nessuno ([DAY-005]).
* **Impatto:** per 47 minuti di seduta il sistema è cieco e muto senza dichiararsi tale. In questa
  giornata il costo economico è nullo (nessun segnale sopra il gate esisteva nella finestra: fra le
  15:31 e le 17:06 il massimo è +0,229), ma il difetto è di **correttezza dell'evidenza**: ogni serie
  giornaliera che divide per «cicli attesi» o «news accodate» contiene un buco non dichiarato, e una
  ripetizione in una finestra con segnali forti cancella ordini senza lasciare un `failed`.
* **Severità:** High
* **Confidenza:** High
* **Azione consigliata:** ticket di correttezza — (a) `is_market_open()` deve distinguere
  «chiuso» da «sconosciuto» e il ramo sconosciuto deve essere **fail-closed sul trading ma fail-open
  sull'ingest** (accodare news non muove capitale); (b) `run_portfolio_cycle` deve sollevare, non
  restituire `{'error': ...}`, così che il task risulti `failed`; (c) cache dell'ultimo calendario
  noto con TTL, così che un 500 transitorio non equivalga a un giorno festivo.
* **Test/monitor consigliato:** test che inietti un 500 su `/v2/clock` e asserisca che il ciclo
  portfolio fallisca (non `succeed`) e che l'ingest continui; monitor giornaliero
  `count(portfolio_cycles) == slot_attesi_del_calendario` con allerta su disuguaglianza.

### [DAY-002] (F-019) Due terzi della coda news muoiono stale: 527/777, quarto giorno di escalation

* **Tipo:** Anomalia
* **Area:** News
* **Evidenza:**
  * tabella: `stale_drop_metrics_daily`, `news_queue_drops`, `ingestion_stats_daily`
  * timestamp: misurato alle 22:55:00 UTC sul giorno intero
  * query:
    ```sql
    SELECT day, queued, stale_drops, stale_drop_share FROM stale_drop_metrics_daily
    WHERE source='alpaca_benzinga' AND day>='2026-09-08';
    -- 09-08 541/157 0.290 | 09-09 526/195 0.371 | 09-10 850/451 0.531 | 09-11 777/527 0.678
    ```
* **Descrizione:** su 777 articoli accodati, **527 sono stati scartati `stale`** prima di essere
  valutati (età media 7,45 h contro `MAX_NEWS_AGE_HOURS = 2`). La quota è cresciuta per quattro
  sedute consecutive: 29,0% → 37,1% → 53,1% → **67,8%**, contro una soglia pre-registrata di 0,25.
  235 dei 527 erano accodati fuori seduta (è la coorte notturna, [DAY-016]); i restanti **292 sono
  stati accodati durante la seduta e sono comunque morti in coda**, cioè il consumatore non tiene
  il passo dell'ingest. La distribuzione oraria lo mostra: 235 scarti nella sola ora 13:00, con
  età media 8,78 h — il backlog notturno che viene svuotato e buttato alla campana.
* **Impatto:** il denominatore di ogni misura di copertura news è gonfiato e il segnale disponibile
  al ranker è una frazione minoritaria del flusso acquistato. **Costo diretto non attribuibile a
  questa seduta**: i 3 mover non presi (ARM, IBM, TXN) sono spiegati da copertura assente (IBM, TXN:
  zero articoli — già registrato su F-001 per il 09-11) e da fan-out off-topic (ARM — F-012), non
  da articoli morti in coda.
* **Severità:** High
* **Confidenza:** High
* **Azione consigliata:** **nessuna taratura** (`MAX_NEWS_AGE_HOURS` è congelato). Ticket di
  osservabilità: pubblicare separatamente la quota in-session e la quota off-session nell'allerta
  (già fatto con la migrazione 073, applicata però il 2026-09-12 — vedi §12) e dimensionare la
  capacità del consumatore rispetto al rate d'ingest misurato.
* **Test/monitor consigliato:** serie `news_queue_census` (migrazione 068) con allerta sulla
  profondità della coda alla campana, non solo sul rapporto a fine giornata.

### [DAY-003] (F-013) Due SELL su punteggio non negativo: RDDT a +0,029 e PLTR a +0,000

* **Tipo:** Bug
* **Area:** Signal / Orders
* **Evidenza:**
  * tabella: `execution_decisions` 21530 e 21865, `trades` 992 e 996, `docs/evidence/dossier/2026-09-11.json → decision_quality`
  * timestamp: 14:52:00 e 18:22:00 UTC
  * snippet:
    ```
    21530 RDDT SELL [below_entry_gate] ... (age=0.2h, generated 2026-09-11 14:39 UTC, score=+0.029): weight 0.0%, position closed.
    21865 PLTR SELL [below_entry_gate] ... (age=0.5h, generated 2026-09-11 17:54 UTC, score=+0.000): weight 0.0%, position closed.
    ```
* **Descrizione:** non esiste banda fra il gate d'ingresso (0,30) e il gate d'uscita (0). Un segnale
  di segno **positivo ma piccolo** azzera il peso target e liquida la posizione: RDDT chiusa su +0,029,
  PLTR su +0,000 esatto — cioè su un punteggio che non contiene informazione direzionale di alcun tipo.
* **Impatto:** costo **attribuito 24,79 $** su questa seduta. RDDT: era detenuta dall'apertura, quindi
  il dossier la prezza direttamente — `exit_active_effect` del libro = **−23,84 $**, che è esattamente
  il `drift_post_uscita` di RDDT (la posizione ha guadagnato 23,84 $ dopo essere stata venduta), a
  fronte di un realizzato di −5,88 $. PLTR: `drift_post_uscita` **+0,95 $**. Totale 24,79 $.
  (ADBE è esclusa dal conto: è uscita su −0,135, un flip di segno genuino, anche se ha lasciato
  +18,53 $ sul tavolo — il costo del *no-band* non è separabile da quello del flip.)
* **Severità:** High
* **Confidenza:** High
* **Azione consigliata:** **nessuna taratura** durante il freeze. Ticket già implicito nella
  decisione #182(a)/#334; qui serve solo che la banda d'uscita sia registrata come parametro da
  decidere il 2026-09-28, con il costo cumulato (ora 122,35 $ su 22 occorrenze) come input.
* **Test/monitor consigliato:** asserzione che nessun `SELL` con `reason LIKE '[below_entry_gate]%'`
  possa avere `score >= 0`; alert giornaliero su `count(SELL con score >= 0)`.

### [DAY-004] (F-021) La griglia beat parte a :07 dell'ora 14: 37 minuti di seduta senza cicli, e NOW li paga

* **Tipo:** Bug
* **Area:** Ops / Orders
* **Evidenza:**
  * file/log/tabella: `mobile_events`; `portfolio_cycles`; `docs/evidence/dossier/2026-09-11.json → timeline`
  * timestamp: 13:30:00 → 14:07:00 UTC
  * snippet:
    ```
    mobile_events: 13:30:00.955 critical "Ciclo di portafoglio in ritardo"  (recovered)
    mobile_events: 13:30:00.968 warning  "Segnali sentiment in ritardo"     (recovered)
    dossier timeline NOW: scored_at 13:42:50 price 131.455 -> eligible_cycle_at 14:07:00 price 133.25
    trades 993: entry_price 133.76, qty 10.757102272
    ```
* **Descrizione:** le finestre beat sono espresse in ore UTC fisse (`hour=14-21`) mentre la RTH in
  EDT apre alle 13:30 UTC. Il primo ciclo utile è quindi alle 14:07 e i primi **37 minuti** della
  seduta — quelli in cui viene smaltito tutto il backlog notturno e nascono 29 segnali — non hanno
  alcun ciclo di portafoglio. Il sistema se ne accorge da solo: emette un incident CRITICAL
  «Ciclo di portafoglio in ritardo» alle 13:30 **ogni giorno**, e lo marca `recovered` alle 14:07.
* **Impatto:** **costo attribuito 15,37 $** su questa seduta. NOW è stata scorata +0,435 alle 13:42:50
  con il titolo a 131,455 ed è stata comprata alle 14:07:06 a 133,76: 2,305 $/azione × 10,757 azioni
  = **24,80 $** di drift pagato in 24,2 minuti di attesa. Con una griglia ancorata all'apertura RTH
  (13:37 / 13:52 / 14:07) il segnale sarebbe stato raccolto alle 13:52, cioè 15 dei 24,2 minuti:
  quota pro-rata lineare **15,37 $**. È una ripartizione, non una controfattuale prezzata — la barra
  delle 13:52 non è stata recuperata, e il drift non è lineare.
* **Severità:** Medium
* **Confidenza:** Medium (il costo è pro-rata; l'esistenza del buco è High)
* **Azione consigliata:** ticket di correttezza — ancorare la griglia beat al calendario Alpaca
  (`GetCalendarRequest`) invece che a ore UTC fisse. Non è taratura: la cadenza di 15 minuti resta
  invariata, cambia solo il punto d'ancoraggio, ed è lo stesso difetto che riapparirà all'inverso al
  passaggio a EST.
* **Test/monitor consigliato:** test che, con il calendario su una seduta EST e una EDT, asserisca
  che il primo slot cada entro 15 minuti dall'apertura; monitor sul tempo fra `market_open` e primo
  `portfolio_cycles.timestamp`.

### [DAY-005] (F-062) Nove CRITICAL, otto incident e due notifiche: zero consegne

* **Tipo:** Bug
* **Area:** Ops
* **Evidenza:**
  * tabella: `mobile_events`, `mobile_notification_deliveries`; `logs/containers/worker-2026-09-11.log`
  * timestamp: 21:00:00 UTC (decay monitor), 16:16 e 17:04 (clock), 22:50 e 22:55
  * query:
    ```sql
    SELECT severity, count(*) FROM mobile_events WHERE created_at::date='2026-09-11' GROUP BY 1;
    -- critical 3 | warning 5
    SELECT count(*), max(created_at) FROM mobile_notification_deliveries;  -- 0 | NULL
    ```
* **Descrizione:** rispetto alle occorrenze precedenti il quadro è **migliorato a metà**:
  `mobile_events` ora è popolata (8 incident, fra cui la degradazione del clock e i due ritardi del
  ciclo) e lo `stale-drop-alert` ha correttamente emesso (`{'measured': 2, 'alerted': 1}`).
  Ma `mobile_notification_deliveries` è **vuota da sempre** (0 righe totali, non solo per il giorno):
  nessun incident è mai uscito dal database. In parallelo i 9 `DECAY CRITICAL` delle 21:00 esistono
  solo come `log.critical`, senza alcun canale.
* **Impatto:** la degradazione del clock di [DAY-001] è stata rilevata dal sistema alle 16:16 e
  nessun essere umano lo ha saputo fino a questa analisi, tre giorni dopo. Costo non stimabile
  (è osservabilità pura), ma è il moltiplicatore di ogni altro finding: tutto viene visto, niente viene detto.
* **Severità:** High
* **Confidenza:** High
* **Azione consigliata:** ticket — collegare `mobile_events` a un canale di consegna reale e
  instradarvi anche i CRITICAL del decay monitor. Fino ad allora, l'unico canale operativo è
  la lettura manuale del DB.
* **Test/monitor consigliato:** test d'integrazione che asserisca che un incident CRITICAL produca
  almeno una riga in `mobile_notification_deliveries`; monitor
  `count(mobile_events critical) > 0 AND count(deliveries) = 0` → allerta.

### [DAY-006] (F-005) Alert Telegram rifiutato con 400 Bad Request

* **Tipo:** Bug
* **Area:** Ops
* **Evidenza:**
  * file/log: `logs/containers/worker-2026-09-11.log`
  * timestamp: 14:22:05 e 14:37:06 UTC
  * snippet:
    ```
    14:22:05 INFO    HTTP Request: POST https://api.telegram.org/bot.../sendMessage "HTTP/1.1 400 Bad Request"
    14:22:05 WARNING TelegramNotifier: Failed to send alert: Client error '400 Bad Request'
    ```
* **Descrizione:** i due alert #161 (AMAT non protetta a −22,7%, WDC a −17,2%; 10 posizioni su 44
  hanno qty < 1 e non sono proteggibili) sono stati rifiutati dall'API Telegram. L'errore è loggato
  come WARNING e il flusso prosegue.
* **Impatto:** non stimabile in dollari — è il secondo canale d'allerta morto della giornata,
  insieme a [DAY-005].
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** loggare il **corpo** della risposta 400 (oggi si vede solo lo status) e
  trattare un 400 come errore di configurazione non ritentabile, con escalation.
* **Test/monitor consigliato:** contatore `telegram_send_failures` con allerta a >0 nella seduta.

### [DAY-007] (F-004) Il decay monitor confronta una metrica globale contro tre baseline per-strategia

* **Tipo:** Bug
* **Area:** Signal
* **Evidenza:**
  * file/log: `logs/containers/worker-2026-09-11.log`
  * timestamp: 21:00:00 UTC
  * snippet:
    ```
    21:00:00 CRITICAL DECAY CRITICAL [S1]: IC dropped 260% from 0.035 to -0.056
    21:00:00 CRITICAL DECAY CRITICAL [S2]: IC dropped 234% from 0.042 to -0.056
    21:00:00 CRITICAL DECAY CRITICAL [S4]: ... (stesso valore corrente)
    21:00:00 CRITICAL DECAY CRITICAL [S1]: Hit rate dropped 23.1pp from 54.0% to 30.9%
    21:00:00 CRITICAL DECAY CRITICAL [S2]: Hit rate dropped 25.1pp from 56.0% to 30.9%
    ```
* **Descrizione:** il valore *corrente* è identico per S1, S2 e S4 (IC −0,056, hit rate 30,9%,
  Sharpe 0,11): è una metrica calcolata sull'intera pipeline e poi confrontata contro tre baseline
  diverse. Le tre allerte non sono tre osservazioni indipendenti, sono la stessa osservazione ripetuta.
* **Impatto:** non stimabile in dollari. Se una di queste soglie venisse mai collegata a un'azione
  (sospensione di una sleeve), sospenderebbe la strategia sbagliata. Oggi è inerte perché il canale
  è morto ([DAY-005]) — due difetti che si mascherano a vicenda.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** ticket di correttezza — calcolare IC, hit rate e Sharpe per `strategy_id`
  prima del confronto, o dichiarare esplicitamente nel messaggio che la metrica è globale.
* **Test/monitor consigliato:** test che, con due strategie a P&L divergente, asserisca che le
  metriche di decay differiscano.

### [DAY-008] (F-011) `signal_id` NULL su 3 SELL su 3 e su 3 `SKIP_PYRAMIDING` su 7

* **Tipo:** Bug
* **Area:** Data
* **Evidenza:**
  * tabella: `execution_decisions`; `docs/evidence/dossier/2026-09-11.json → decision_signal_id_coverage`
  * timestamp: giorno intero
  * snippet: `"regressions": ["SELL", "SKIP_PYRAMIDING"]`, `SELL fill_rate 0.0 (expected must_be_full)`,
    `SKIP_PYRAMIDING fill_rate 0.571`
* **Descrizione:** copertura complessiva ottima (614/620 = 99,0%) ma concentrata esattamente dove
  serve: **nessuna delle 3 uscite ha un `signal_id`**, quindi la catena
  segnale → decisione → trade non è ricostruibile per chiave esterna sul lato uscita, proprio il lato
  su cui verte [DAY-003]. Per RDDT e PLTR il punteggio che ha causato la liquidazione è recuperabile
  solo facendo parsing del testo di `reason`. Tre `SKIP_PYRAMIDING` (CVX, MRVL, AMAT) non hanno né
  `signal_id` né `signal_score`.
* **Impatto:** non stimabile in dollari; rende ogni analisi delle uscite dipendente dal parsing di
  stringhe. È un difetto di **correttezza dell'evidenza**: le misure di ranking e di causa d'uscita
  costruite su `signal_id` escludono per costruzione tutte le uscite.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** ticket — popolare `signal_id` e `signal_score` sul ramo SELL e sul ramo
  pyramiding con il segnale che ha determinato il peso target.
* **Test/monitor consigliato:** l'invariante è già misurata dal dossier
  (`decision_signal_id_coverage.regressions`); mancano solo consegna e soglia.

### [DAY-009] (F-006) TSLA resta rank 6 di top-5 per 45 minuti senza lasciare una riga in `execution_decisions`

* **Tipo:** Anomalia
* **Area:** Signal / Data
* **Evidenza:**
  * tabella: `s4_intent_events` vs `execution_decisions`
  * timestamp: 18:07 → 19:07 UTC
  * query:
    ```sql
    SELECT decision_slot, rank, reason_code FROM s4_intent_events
    WHERE symbol='TSLA' AND event_type='disposition' AND decision_slot>='2026-09-11 18:00';
    -- 18:07 rank 6 RANK_OUTSIDE_TOP_N | 18:22 rank 6 | 18:37 rank 6 | 18:52 rank 6
    -- 19:07 rank 5 SUBMITTED          | 19:22 rank 5 SKIP_IDEMPOTENCY
    SELECT count(*) FROM execution_decisions
    WHERE symbol='TSLA' AND tick_time BETWEEN '2026-09-11 18:00' AND '2026-09-11 19:00';  -- 0
    ```
* **Descrizione:** il segnale TSLA +0,366, scorato alle 18:04, sopra il gate e fresco, è rimasto
  fuori dai top-5 per quattro slot consecutivi. Il ledger `s4_intent_events` lo registra
  correttamente (`RANK_OUTSIDE_TOP_N`), ma `execution_decisions` — che è la tabella letta dall'API,
  dal dossier e dalle serie pubblicate — **non contiene alcuna riga**, mentre contiene 30-32 righe
  `SKIP_THRESHOLD` per segnali *sotto* il gate negli stessi cicli. Un lettore di `execution_decisions`
  conclude che TSLA non fosse candidata; era candidata e in coda.
* **Impatto:** **nessun costo economico su questa occorrenza** — TSLA è stata comprata un'ora dopo
  a 364,74 contro i ~365,07 di 18:04, cioè leggermente meglio. Il costo è di auditabilità:
  una decisione di *non* comprare non è visibile dove si guardano le decisioni.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** ticket — persistere `SKIP_RANK` in `execution_decisions` come le altre
  SKIP (con la costante di esclusione già prevista per `LATE_ENTRY_OBSERVATION_DECISIONS`, così
  da non cambiare in silenzio il denominatore delle serie esistenti).
* **Test/monitor consigliato:** invariante giornaliera: ogni `signal_id` con score ≥ gate e non
  stale deve avere almeno una riga in `execution_decisions` per ogni ciclo in cui il ledger lo
  registra come candidato.

### [DAY-010] (F-007) 6.650 duplicati contro 1.417 fetched: il WebSocket consegna lo stesso articolo fino a 36 volte

* **Tipo:** Anomalia
* **Area:** News
* **Evidenza:**
  * tabella: `ingestion_stats_daily`, `news_queue_drops`; `logs/containers/worker-news-stream-2026-09-11.log`
  * timestamp: giorno intero
  * snippet:
    ```
    ingestion_stats_daily 2026-09-11 alpaca_benzinga: fetched 1417, queued 779, duplicates 6650
    worker-news-stream (conteggio righe identiche):
      36x "What's Going On With Qualcomm Stock Thursday?" [6 ticker]
      32x "Jensen Huang Calls NVIDIA the 'World's First and Only Growth..." [17 ticker]
      18x "Houthi Victory Raises Risks; Hotter CPI..." [12 ticker]
    ```
* **Descrizione:** i duplicati (6.650) superano di **4,7 volte** gli articoli scaricati (1.417).
  La causa è ora visibile nel log del worker WebSocket introdotto di recente: lo **stesso** articolo
  viene ri-consegnato decine di volte, e ogni consegna attraversa il deduplicatore per essere
  scartata. Il contatore è additivo e mescola le ri-consegne WS con le ri-letture REST.
* **Impatto:** non stimabile in dollari; è spreco di CPU e un contatore che non può essere letto
  come «quota di duplicazione» perché il denominatore è sbagliato.
* **Severità:** Low
* **Confidenza:** High
* **Azione consigliata:** ticket — separare i contatori per trasporto (WS vs REST), come già
  richiesto da #541, così che `duplicates/fetched` torni a essere un rapporto interpretabile.
* **Test/monitor consigliato:** allerta se `duplicates > 2 × fetched` su una fonte.

### [DAY-011] (F-022) Gli stop protettivi coprono dal 76,1% al 96,0% della posizione

* **Tipo:** Rischio
* **Area:** Risk
* **Evidenza:**
  * tabella: ordini Alpaca via `/api/orders`; `trades`
  * timestamp: 14:22:05, 14:37:06, 15:52:06 ×2, 18:22:08, 19:22:06 UTC
  * snippet:

    | stop | qty ordine | qty posizione | copertura |
    |---|---|---|---|
    | NOW | 10 | 10,757102272 | 92,9% |
    | ADBE | 5 | 5,845422792 | 85,5% |
    | PLTR | 8 | 8,627891645 | 92,7% |
    | SPCX | 9 | 9,725141853 | 92,5% |
    | ORCL | 9 | 9,372532301 | 96,0% |
    | **TSLA** | **3** | **3,94003948** | **76,1%** |

* **Descrizione:** lo stop viene piazzato sulla sola parte intera della quantità frazionaria, e
  sempre **un ciclo dopo** l'ingresso (15 minuti di esposizione senza copertura). Su TSLA, il titolo
  più caro, resta scoperto quasi un quarto della posizione. In parallelo, 10 posizioni su 44 hanno
  qty < 1 e non hanno alcuno stop (alert #161, non consegnato — [DAY-006]).
* **Impatto:** non stimabile su questa seduta (nessuno stop è scattato, nessun gap avverso).
  È esposizione, non costo.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** **nessuna taratura** (la size minima ≥ 1 azione è esplicitamente rinviata
  al 2026-09-28 dalla carta). Qui basta rendere la copertura una grandezza **osservata**:
  persistere `stop_qty / position_qty` per trade. `stop_decisions` è vuota dal 2026-07-14.
* **Test/monitor consigliato:** invariante giornaliera `stop_qty >= 0,99 × qty` su ogni trade aperto
  con stop; riattivare la scrittura di `stop_decisions`.

### [DAY-012] (F-054 / F-037) `eligible=false` su due terzi delle risposte che entrano comunque nell'ensemble, e la varianza non gatea mai

* **Tipo:** Bug
* **Area:** LLM
* **Evidenza:**
  * tabella: `llm_responses`, `sentiment_signals`
  * timestamp: giorno intero
  * query:
    ```sql
    SELECT model_id, count(*), sum(eligible::int) FROM llm_responses
    WHERE generated_at::date='2026-09-11' GROUP BY 1;
    -- glm-5.2:cloud 168 / 64 eligible | gpt-oss:20b-cloud 161 / 64 eligible
    ```
    Esempio di coppia a segno opposto con entrambi `eligible=false` e segnale emesso comunque:
    SPY glm +0,20 / gpt-oss −0,40 → `score 0,0012`, `confidence 0,0166`, `ensemble_std 0,000`.
* **Descrizione:** solo 64 risposte su 168 (glm) e 64 su 161 (gpt-oss) sono marcate `eligible`,
  eppure 117 cicli producono un segnale full-ensemble: il flag **non descrive** chi ha contribuito.
  Conseguenza diretta: `ensemble_std` vale **0,000 esatto** su 57 segnali su 174 — non perché i
  modelli concordino, ma perché il calcolo vede un solo contributore eleggibile. E in ogni caso
  `ensemble_std` **non è mai un gate d'ingresso**: è letto solo dal postmortem. Il caso SPY sopra è
  il massimo disaccordo della giornata (gap 0,60, segni opposti) e produce comunque una riga nel
  signal store.
* **Impatto:** non stimabile su questa seduta (nessuno dei 4 segnali a segno opposto ha superato il
  gate). È però **correttezza dell'evidenza**: qualunque analisi che filtri su `eligible` o che
  usi `ensemble_std` come proxy di consenso sta misurando un artefatto.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** ticket di correttezza — allineare `eligible` all'insieme effettivamente
  aggregato, e calcolare `ensemble_std` sui contributori reali. **Non** introdurre un gate di varianza:
  sarebbe taratura, congelata fino al 2026-09-28.
* **Test/monitor consigliato:** invariante `count(eligible=true per signal_id) == n_contributori
  dichiarati in model_id`; allerta su `ensemble_std = 0` con `model_id LIKE 'ensemble:%'`.

### [DAY-013] (F-053) `market_daily.jsonl` registra per il 2026-09-11 l'equity della chiusura precedente

* **Tipo:** Bug
* **Area:** PnL / Data
* **Evidenza:**
  * file/tabella: `docs/evidence/market_daily.jsonl`, `portfolio_monitor_snapshots`
  * timestamp: riga `"data": "2026-09-11"`
  * snippet:
    ```
    market_daily.jsonl 2026-09-11: "book": {"equity": 109480.15, ...}
    portfolio_monitor_snapshots 2026-09-11 20:00: nav 109737.29, previous_close_equity 109480.15
    ```
* **Descrizione:** il campo `book.equity` della riga del 2026-09-11 contiene **109.480,15 $**, che è
  esattamente `previous_close_equity` della seduta, cioè la chiusura ufficiale del 2026-09-10 —
  non il NAV di chiusura del giorno (109.737,29 $). Lo scarto è di **257,14 $**, cioè l'intera
  variazione della seduta. Il controllo sulle sedute precedenti mostra che il difetto **non è
  sistematico**: per il 2026-09-04 il valore (109.970,86) coincide col NAV di chiusura di quel giorno.
* **Impatto:** non stimabile come perdita, ma è **correttezza dell'evidenza** in senso stretto:
  `market_daily.jsonl` è una serie pubblicata che entra nella roadmap pesata del 2026-09-28 e la
  sua riga del 09-11 sposta l'equity di 257 $ nella direzione sbagliata.
* **Severità:** Medium
* **Confidenza:** Medium (la riga è verificata; la *causa* — snapshot letto fuori seduta o
  `last_equity` invece di `equity` — non lo è, e va confermata sul generatore)
* **Azione consigliata:** ticket di correttezza — il generatore deve leggere il NAV dallo snapshot
  delle 20:00 UTC della **stessa** data, non dal campo account corrente. Verificare se altre righe
  della finestra sono affette prima di qualunque correzione, e annotare la correzione come
  discontinuità nella carta.
* **Test/monitor consigliato:** invariante `market_daily[D].book.equity == snapshot(D, 20:00).nav`
  su tutta la finestra, eseguita prima del consolidamento della riga.

### [DAY-014] (F-064) Nove posizioni su 42 senza benchmark settoriale, e `missingness` è vuota

* **Tipo:** Bug
* **Area:** PnL
* **Evidenza:**
  * file: `docs/evidence/dossier/2026-09-11.json → decision_quality.opening_snapshot`
  * timestamp: snapshot all'apertura RTH
  * snippet: senza `sector_benchmark`: **RIO, ROKU, SPY, NOK, VALE, GM, CAT, SBUX, RDDT** (9/42);
    `missingness: []` su tutte
* **Descrizione:** l'attribuzione beta=1 assegna a queste 9 posizioni l'intero scarto dal mercato
  come `residual_usd`, perché non esiste un ETF settoriale mappato. Il campo `missingness` resta
  vuoto, quindi il dossier **non dichiara** che l'attribuzione settoriale è parziale.
  Sul totale della giornata: mercato −18,14 $, settore −1,91 $, **residuo +29,39 $** — il residuo
  è il termine dominante e contiene la quota settoriale non attribuita.
* **Impatto:** non stimabile in dollari. Rende il residuo (che è la grandezza da cui si legge
  «alpha») sistematicamente sovrastimato per un quinto del libro.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** ticket — completare `SECTOR_ETF_BY_SECTOR` per materials, media, consumer
  e il bucket `etf_broad`, **oppure** (se il mapping non esiste) popolare `missingness` in modo che
  il dato parziale sia dichiarato tale. La seconda è la correzione minima e non tocca alcuna soglia.
* **Test/monitor consigliato:** invariante: ogni riga senza `sector_benchmark` deve avere una voce
  in `missingness`.

### [DAY-015] (F-014) `constraints_fired` vuoto su tutti e 21 i cicli: non si distingue «nessuna violazione» da «nessuna valutazione»

* **Tipo:** Ambiguità
* **Area:** Risk
* **Evidenza:**
  * tabella: `portfolio_cycles`
  * timestamp: 14:07 → 19:52 UTC
  * query:
    ```sql
    SELECT count(*) FROM portfolio_cycles
    WHERE timestamp::date='2026-09-11' AND constraints_fired::text <> '[]';  -- 0
    ```
* **Descrizione:** in 21 cicli nessun vincolo di rischio (cap settoriale, esposizione lorda,
  concentrazione) ha mai lasciato traccia. È plausibile che sia corretto — gross exposure al
  29–33% contro limiti molto più alti, 45 posizioni ben diversificate — ma dalla tabella **non è
  possibile distinguerlo** dal caso in cui i vincoli non siano stati valutati affatto.
  Stesso problema di `rebalanced_strategies: []` e `zero_weight_symbols: {}` su tutti i cicli.
* **Impatto:** non stimabile. È un buco di auditabilità sul ramo risk, che è esattamente il ramo
  in cui un silenzio non è distinguibile da un guasto.
* **Severità:** Low
* **Confidenza:** High
* **Azione consigliata:** ticket — registrare i vincoli **valutati** oltre a quelli violati
  (`constraints_evaluated` / `constraints_fired`).
* **Test/monitor consigliato:** test che, forzando un cap settoriale sotto l'esposizione corrente,
  asserisca la comparsa della riga in `constraints_fired`.

### [DAY-016] (F-069) Il WebSocket ingerisce 24/7 in una coda il cui unico consumatore è gated sul mercato aperto

* **Tipo:** Bug
* **Area:** News / Ops
* **Evidenza:**
  * tabella: `news_queue_drops`; `logs/containers/worker-inference-2026-09-11.log`
  * timestamp: 00:00 → 13:30 UTC e 20:00 → 24:00 UTC
  * query:
    ```sql
    SELECT count(*) FILTER (WHERE enqueued_off_session) FROM news_queue_drops
    WHERE dropped_at::date='2026-09-11' AND discarded_reason='stale';  -- 235 su 527
    ```
    98 esecuzioni `run_sentiment_worker` chiuse con `{'skipped': True, 'reason': 'market_closed'}`.
* **Descrizione:** il worker di streaming accoda articoli tutta la notte; il consumatore sentiment
  si rifiuta di girare a mercato chiuso. Gli articoli maturano in coda e alla campana **235 di essi
  sono già oltre `MAX_NEWS_AGE_HOURS` e vengono buttati** — 44,6% di tutti gli scarti stale della
  giornata, con l'ora 13:00 che da sola ne concentra 235 a età media 8,78 h.
* **Impatto:** non stimabile su questa seduta (i 3 mover non presi sono spiegati altrimenti, §DAY-002).
  Strutturalmente, la finestra notturna è ingerita e buttata: il costo di rete è pagato, il valore no.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** la strumentazione è già decisa (turno ombra off-session, deroga #432
  Opzione C, e censimento coda migrazione 068) ma **non era attiva il 2026-09-11** (§12).
  Nessuna azione nuova: raccogliere l'evidenza dal turno ombra prima di proporre qualunque cambio.
* **Test/monitor consigliato:** serie `news_queue_census` con profondità della coda campionata 24/7,
  già prevista.

### [DAY-017] (F-076, nuovo) La finestra pre-registrata non può più raggiungere le 40 sedute

* **Tipo:** Rischio
* **Area:** Ops / Data
* **Evidenza:**
  * file: `docs/evidence/economic_pnl.json → scoreboard.giorno`, `docs/evidence/market_daily.jsonl`,
    `docs/evidence/OBSERVATION_CHARTER.md`, `docs/WEEKLY_FINDINGS_2026-37.md §1`
  * timestamp: as-of 2026-09-11
  * snippet:
    ```
    scoreboard.giorno: {"n": 27, "denominatore": 40}
    osservati: ... "2026-09-04", "2026-09-08", "2026-09-11"   <- mancano 09-09 e 09-10
    market_daily.jsonl: 28 righe, nessuna per 2026-09-09 né 2026-09-10
    ```
* **Descrizione:** la carta fissa un minimo di **40 sedute di borsa** con scadenza attesa
  2026-09-28. Al 2026-09-11 ne sono state osservate **27**. Le sedute del 09-09 e del 09-10 sono
  assenti dalla serie perché i cron di analisi sono morti sulla quota settimanale dell'account
  (documentato in `WEEKLY_FINDINGS_2026-37.md`): esistono i dossier grezzi ma non le righe di serie.
  Dal 2026-09-14 al 2026-09-28 restano **11 sedute** (14-18, 21-25, 28): 27 + 11 = **38 < 40**.
  Il minimo pre-registrato è aritmeticamente irraggiungibile alla scadenza attesa.
* **Impatto:** non stimabile in dollari, ma è il rischio più grave per la decisione del 2026-09-28:
  o la finestra si estende (e va registrato come discontinuità **prima** di vedere il risultato,
  non dopo), o il verdetto esce sotto il minimo dichiarato — cioè `INSUFFICIENT_N` per costruzione,
  esattamente l'esito che la carta ordina sopra PASS/FAIL.
* **Severità:** High
* **Confidenza:** High
* **Azione consigliata:** decisione dell'operatore **prima** del 2026-09-28, registrata nella carta:
  (a) recuperare 09-09 e 09-10 dai dossier grezzi già presenti — che è ricostruzione, non
  ri-misurazione, e va annotata come tale; oppure (b) estendere la scadenza di due sedute.
  L'alternativa implicita (concludere a 38 senza dirlo) è esclusa dalla carta.
* **Test/monitor consigliato:** un check giornaliero che confronti `scoreboard.giorno.n` con le
  sedute Alpaca trascorse dal 2026-08-03 e allerti sul primo giorno di scarto, invece di scoprirlo
  a due settimane dalla scadenza.

---

## 10. Anomalie già registrate per questa seduta (non ri-conteggiate)

Queste sono state osservate e confermate anche in questa analisi, ma hanno **già** un'occorrenza
del 2026-09-11 nel ledger, scritta da `docs/ALPHA_MISS_REPORT_2026-09-11.md`. Per non gonfiare la
ricorrenza non è stata aggiunta una seconda voce; il riferimento è alla voce esistente.

| finding | osservazione di oggi | occorrenza esistente |
|---|---|---|
| **F-001** copertura news | 39 simboli di watchlist a zero articoli; IBM e TXN, entrambi mover ≥ 3,8%, senza una riga | costo 171,13 $ (= 87,15 + 83,98, i due `gross_opportunity_usd`) |
| **F-009** gate 0,30 | 39 segnali negativi e 36 in [0,10; 0,19] scartati, nessuno tradotto in azione | costo `null` |
| **F-012** fan-out | 98 righe su 174 (56,3%) da articoli multi-ticker; ARM scorato 0,000 da un listicle a 8 ticker | costo 0,0 |
| **F-018** token Telegram in chiaro | **17.276** righe INFO con il bot token nell'URL in `worker-inference-2026-09-11.log` | costo `null` |
| **F-019** latenza ingest | vedi [DAY-002]: qui è registrata una **seconda** voce perché l'evidenza è diversa (quota di scarto, non latenza) — vedi nota nel ledger |
| **F-030** notizia in ritardo | NOW: `quota_movimento_precedente_al_segnale = 1,606`, percentile d'ingresso 0,830 | costo `null` |
| **F-031** guard pyramiding | 5 segnali sopra gate bloccati con posizioni al 16–25% dello slot | costo 41,47 $ |
| **F-048** uscite parziali | — | costo `null` |
| **F-074** outage clock | vedi [DAY-001]: **seconda** voce, con il blast radius su sentiment e ingest che la prima non copre |
| **F-075** `held_at_open_rate` | 4 mover su 7 «catturati» perché già detenuti, con nozionale residuo minimo | costo `null` |

---

## 11. False positive e aree risultate corrette

* **`F-027` (log distrutti dal redeploy): non ricorre.** Tutti e cinque i log della giornata target
  sono presenti e completi in `logs/containers/`, incluso il nuovo `worker-news-stream`.
* **`F-063` (calendario earnings cieco): risolto.** `calendario_earnings.status = "OBSERVED"`,
  `sources_succeeded: ["FMP earnings-calendar"]`, `streak_sedute_consecutive_unknown: 0`.
  Zero simboli con earnings in giornata — misurato, non assunto.
* **`F-041` (bearer token rifiutato sugli endpoint REST): non ricorre.** Tutti e cinque gli endpoint
  (`/decisions`, `/trades`, `/signals`, `/positions`, `/orders`) hanno risposto con `X-API-Key`.
* **`F-046` (il modello riceve solo il corpo): corretto e verificato in produzione.**
  Titolo presente su 174/174 righe (media 82 caratteri) e corpo medio salito a **388 caratteri**
  (era ~151): sia la deroga #399 (titolo nel prompt) sia la #454 (`include_content`) sono operative.
* **Sanitizzazione degli input:** presente e nel punto giusto della catena (§4.2). Non è una
  lacuna, contrariamente a quanto il vincolo di progetto richiede di verificare ogni volta.
* **Disciplina asincrona:** rispettata. Zero chiamate LLM nel ciclo di esecuzione — i 21 cicli
  portfolio durano meno di 8 secondi, tutta l'inferenza sta in `worker-inference` (coda dedicata,
  concurrency 1).
* **Idempotenza:** osservata e funzionante (`SKIP_IDEMPOTENCY`, `SIGNAL_DUPLICATE_SKIP`).
* **Riconciliazione:** 45 posizioni broker = 45 trade aperti in DB, nessuno scarto.
* **`F-072` (ciclo sentiment non idempotente): non ricorre.** Nessun `SoftTimeLimitExceeded`,
  nessun `Recovering N stuck items` in tutta la giornata.
* **`F-049` (ensemble giù a metà sessione): non ricorre.** Ollama up dalle 13:31 alle 19:57
  senza buchi; 19 timeout su ~340 tentativi.
* **`F-065` (ciclo sentiment fantasma): non ricorre.** 184 esecuzioni, tutte `succeeded`,
  tutte con esito registrato.
* **`F-068` (INSERT falliti su `s4_intent_events`): non ricorre.** 1.733 `candidate` +
  1.733 `disposition`, zero `disposizione_mancante`.
* **`F-017` (regime detection silenziosamente fallita): non verificabile per il 09-11.**
  `regime:current` in Redis porta `detected_at: 2026-09-14T07:01:42Z` (sovrascritto), e il worker
  log del 09-11 non emette righe di regime. L'unica traccia indiretta è che tutte le 620 decisioni
  della giornata portano `regime_mult = 0,700`, coerente con il regime `sideways` corrente.

---

## 12. Dati mancanti o non accessibili

1. **`finbert_fallback_events` è vuota per il 2026-09-11 — non misurata, non «zero fallback».**
   La migrazione `071_finbert_fallback_events.sql` risulta `applied_at = 2026-09-12 14:03:42Z`,
   cioè **il giorno dopo** quello analizzato. I 5 fallback FinBERT della giornata sono documentati
   solo dal log (`All ensemble models timed out for {ORCL, MS, DIS, AMAT, +1}, using FinBERT
   fallback`), **senza** la stringa esatta classificata né i contatori `title_chars`/`body_chars`.
   La conferma residua di #453 (quali componenti il fallback abbia davvero ricevuto)
   **resta non verificata per questa seduta**.
2. **`news_queue_census` non copre il 09-11**: migrazione 068 applicata il 2026-09-12 08:20Z.
   La profondità della coda notturna è inferita dagli scarti, non campionata.
3. **La riga `stale_drop_metrics_daily` del 09-11 è calcolata con la definizione PRE-#432 Opzione B**
   (migrazione `073_stale_drop_off_session.sql` applicata il 2026-09-12 14:03Z; il campo
   `went_stale_off_session` vale 0 su tutte le righe della settimana). Il 67,8% di [DAY-002] usa
   quindi l'aggregazione a coorti disallineate che la deroga del 2026-09-10 dichiara difettosa.
   Il conteggio in-session/off-session che ho riportato (292 / 235) è stato **ricalcolato
   direttamente da `news_queue_drops.enqueued_off_session`**, non letto da quella riga.
4. **`shadow_late_entry` / `s4_intent_id` sono NULL su tutte le decisioni del 09-11**: la
   strumentazione #512 è stata deployata dopo. La quota di movimento precedente al segnale è
   disponibile solo dal dossier (campo `quota_movimento_precedente_al_segnale`), non da
   `execution_decisions`.
5. **`sentiment_signals_offsession_shadow`**: il turno ombra off-session (deroga #432 Opzione C)
   non era attivo. La domanda «cosa avrebbe prodotto la coorte notturna» resta aperta per il 09-11.
6. **Latenza per singola chiamata LLM: non persistita.** `llm_responses` non ha colonna di latenza.
   Query che servirebbe, se la colonna esistesse:
   `SELECT model_id, percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms) FROM llm_responses WHERE generated_at::date='2026-09-11' GROUP BY 1;`
7. **Slippage: non misurabile** da `trades.slippage_est` (copia di `cost_usd`, F-015). Servirebbe
   persistere il mid NBBO al momento della sottomissione:
   `SELECT t.id, t.entry_price, q.mid_at_submit FROM trades t JOIN <tabella_quote_inesistente> q ...`
8. **Sedute 2026-09-09 e 2026-09-10 assenti dalle serie pubblicate** (`market_daily.jsonl`,
   `economic_pnl.json`, `findings.json`) — vedi [DAY-017]. I dossier grezzi esistono.
9. **`stop_decisions` è vuota dal 2026-07-14**: le decisioni di stop della giornata non sono
   ricostruibili se non dagli ordini broker.
10. **Log frontend**: non presenti in `logs/containers/`. Il container `alembic-frontend-1` gira da
    2026-09-05 ma non versa log persistenti; non è rilevante per questa analisi (nessuna interazione
    umana ha prodotto ordini).

---

## 13. Raccomandazioni immediate

Tutte compatibili con il freeze: nessuna tocca soglie, pesi, flag o parametri di strategia.

1. **Rendere fail-closed sul trading e fail-open sull'ingest il ramo «clock sconosciuto»**
   ([DAY-001]). È il difetto con il blast radius più largo e l'unico che può cancellare ordini
   in silenzio.
2. **Far uscire almeno un canale d'allerta** ([DAY-005], [DAY-006]). Finché `mobile_notification_deliveries`
   è vuota, ogni altro monitor proposto in questo report è teoria.
3. **Decidere entro il 2026-09-21 come chiudere il buco di 2 sedute** della finestra pre-registrata
   ([DAY-017]), registrando la decisione nella carta **prima** di guardare il risultato.
4. **Popolare `signal_id` sul ramo SELL** ([DAY-008]): senza, l'analisi delle uscite — che è dove
   sta il costo cumulato più alto del ledger (F-013, 122 $) — resta basata su parsing di stringhe.
5. **Verificare `market_daily.jsonl` su tutta la finestra** prima del 2026-09-28 ([DAY-013]):
   una riga con l'equity del giorno prima è un errore che si propaga alla roadmap pesata.

Esplicitamente **non** raccomandato: toccare la banda d'uscita ([DAY-003]), la size minima
([DAY-011]), il gate di varianza ([DAY-012]) o `MAX_NEWS_AGE_HOURS` ([DAY-002]). Sono tarature,
congelate fino al 2026-09-28, e l'evidenza raccolta oggi è l'input di quella decisione, non
un pretesto per anticiparla.

---

## 14. Test e monitor da aggiungere

| # | tipo | oggetto | asserzione |
|---|---|---|---|
| T1 | test unit | `is_market_open()` | con `/v2/clock` a 500 restituisce `UNKNOWN`, non `False` |
| T2 | test integrazione | `run_portfolio_cycle` | con clock a 500 il task risulta `failed`, non `succeeded` |
| T3 | monitor giornaliero | `portfolio_cycles` | `count(cicli) == slot attesi dal calendario Alpaca`, altrimenti allerta |
| T4 | monitor giornaliero | `execution_decisions` | `count(SELL con signal_score >= 0) == 0` |
| T5 | test | griglia beat | con calendario EST e EDT, primo slot entro 15 min dall'apertura |
| T6 | test integrazione | notifiche | un incident CRITICAL produce ≥ 1 riga in `mobile_notification_deliveries` |
| T7 | invariante dossier | `decision_signal_id_coverage` | `regressions == []` (già calcolata, manca la consegna) |
| T8 | invariante | ensemble | `count(eligible=true) == n contributori in model_id`; nessun `ensemble_std = 0` su `model_id LIKE 'ensemble:%'` |
| T9 | invariante | stop | `stop_qty >= 0,99 × qty` su ogni trade aperto con stop |
| T10 | invariante | evidenza | `market_daily[D].book.equity == snapshot(D, 20:00).nav` |
| T11 | invariante | evidenza | `scoreboard.giorno.n == sedute Alpaca trascorse dal 2026-08-03` |
| T12 | monitor | decay | metriche IC/hit-rate/Sharpe differenti fra strategie con P&L divergente |
| T13 | monitor | ingest | allerta se `duplicates > 2 × fetched` su una fonte |
| T14 | invariante | ranking | ogni candidato del ledger con score ≥ gate ha una riga in `execution_decisions` |

---

## 15. Ticket tecnici suggeriti

Solo difetti di **correttezza** (test della carta: «se non lo correggo, l'evidenza che raccolgo nelle
prossime settimane è sbagliata?»). Nessuna patch è stata applicata.

| # | titolo | finding | perché passa il test di esenzione |
|---|---|---|---|
| 1 | Clock sconosciuto ≠ mercato chiuso: fail-closed sul trading, fail-open sull'ingest | [DAY-001] F-074 | ogni serie che divide per «cicli attesi» o «news accodate» contiene buchi non dichiarati e ripetibili |
| 2 | `run_portfolio_cycle` deve fallire, non restituire `{'error': ...}` con esito `succeeded` | [DAY-001] F-074 | un fallimento invisibile a Celery è invisibile a qualunque monitor futuro |
| 3 | Ancorare la griglia beat al calendario Alpaca invece che a ore UTC fisse | [DAY-004] F-021 | i primi 37 minuti di ogni seduta EDT sono fuori misura, e il difetto si inverte a EST |
| 4 | Popolare `signal_id`/`signal_score` sul ramo SELL e su `SKIP_PYRAMIDING` | [DAY-008] F-011 | tutte le analisi d'uscita costruite su chiave esterna escludono per costruzione le uscite |
| 5 | Allineare `llm_responses.eligible` ai contributori reali e ricalcolare `ensemble_std` | [DAY-012] F-054/F-010 | `ensemble_std = 0` su un terzo dei segnali è un artefatto che falsifica ogni misura di consenso |
| 6 | Decay monitor: metriche per `strategy_id`, non globali | [DAY-007] F-004 | tre allerte identiche presentate come tre osservazioni indipendenti |
| 7 | `market_daily.jsonl`: leggere il NAV dallo snapshot 20:00 della stessa data | [DAY-013] F-053 | serie pubblicata che entra nella roadmap pesata con l'equity sbagliata |
| 8 | Dichiarare in `missingness` le posizioni senza benchmark settoriale | [DAY-014] F-064 | il residuo — la grandezza da cui si legge «alpha» — è sovrastimato su un quinto del libro senza avviso |
| 9 | Persistere `SKIP_RANK` in `execution_decisions` | [DAY-009] F-006 | una decisione di non comprare non è visibile dove si guardano le decisioni |
| 10 | Collegare `mobile_events` e i CRITICAL del decay a un canale di consegna | [DAY-005] F-062 | senza consegna, ogni monitor aggiunto è inerte |
| 11 | Recuperare o dichiarare le sedute 09-09 e 09-10 della finestra pre-registrata | [DAY-017] F-076 | il minimo di 40 sedute della carta è aritmeticamente irraggiungibile al 2026-09-28 |
| 12 | Separare i contatori duplicati per trasporto (WS vs REST) | [DAY-010] F-007 | `duplicates/fetched = 4,7` non è leggibile come quota di duplicazione |

---

## 16. Stato del sistema

| componente | stato | dettaglio |
|---|---|---|
| **Ollama Cloud** | ✅ **up, 0 ore di downtime** | Primo scoring 13:31:19, ultimo 19:57:32, nessun buco. 19 timeout a 90 s su ~340 tentativi (**5,6%**): `gpt-oss:20b-cloud` 13, `glm-5.2:cloud` 6. Nessun 429, nessun 5xx. |
| **FinBERT fallback** | **5 su 174 segnali = 2,9%** | ORCL, MS, DIS, AMAT + 1, tutti su timeout dell'intero ensemble. Dal lato decisioni: `SKIP_FALLBACK` **25 su 620 = 4,0%**. Nota: `sentiment_signals.fallback_used` è vero su **57/174 (32,8%)** perché include anche i 52 casi single-model, che **non** sono FinBERT. Le righe di `finbert_fallback_events` non esistono per questa data (§12.1). |
| **Composizione ensemble** | 117 full / 52 single / 5 FinBERT | su 50 cicli, 1 dei quali marcato `rth=false` alle 16:15 (durante l'outage del clock) |
| **Alpaca Trading/Data** | ⚠️ **degradato 47 min** | `/v2/clock` 500 dalle 16:16:03 alle 17:03:03; calendario e barre degradati fino alle ~16:30; benchmark SPY fallito 2 volte |
| **Worker restart** | ✅ **0 eventi** | nessun `ready.`, `Warm shutdown` o `Cold shutdown` in `worker` né in `worker-inference` |
| **Beat** | ✅ 20.381 task inviati | fra cui 32 `portfolio-cycle` (21 completati), 32 `sentiment-worker`, 32 `run-news-ingestion`, 32 `run-alpaca-ingestion`, 32 `run-execution` (a vuoto: `engine=portfolio`), **17.279 `poll-telegram-updates`** |
| **Postgres / Redis** | ✅ | `alembic-postgres-1` e `alembic-redis-1` healthy; schema alla migrazione 074 |
| **Canali d'allerta** | ❌ **tutti muti** | Telegram 400 ×2; `mobile_notification_deliveries` 0 righe (da sempre); decay CRITICAL solo su `log.critical` |
| **Configurazione attiva** | — | ensemble `glm52,gptoss`, pesi `{glm 0,70; gpt-oss 0,30}` (`auto_apply`); `feedback:entry_threshold:S4 = 0,3`; regime `sideways`, `multiplier 0,7`, VIX 17,84 |

---

*Report read-only. Nessun file modificato oltre a questo e a `docs/evidence/findings.json`.
Nessun commit, nessuna patch, nessun ordine.*
