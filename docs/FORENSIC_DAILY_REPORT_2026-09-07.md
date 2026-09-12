# Report forense giornaliero — 2026-09-07

Generato: 2026-09-08 (sessione autonoma, sola lettura)
Fuso operativo: **UTC** (`src/workers/celery_app.py:53` → `timezone="UTC"`). Nessuna ambiguità.
Modalità broker verificata: **paper** (`portfolio_monitor_snapshots.mode='paper'`,
`broker_environment='paper'`; `config/trading.yaml:142` → `execution.engine: portfolio`).

---

## 1. Executive summary

**2026-09-07 è il Labor Day: borsa USA chiusa.** Non è una giornata operativa e il sistema lo ha
riconosciuto correttamente. Beat ha emesso tutti i 32+32+32+32 task di mercato previsti dal
`day_of_week="1-5"` (il lunedì festivo resta un lunedì per crontab) e **ogni singolo task si è
autofermato** con `{'skipped': True, 'reason': 'market_closed'}`: 32 ingest GDELT, 32 ingest
Alpaca, 33 sentiment, 32 portfolio-cycle (con `next_open: 2026-09-08 09:30-04:00`, corretto).
`run-execution` ha risposto `engine=portfolio`, quindi nessun doppio path di esecuzione.

Conseguenza: **0 news, 0 chiamate LLM, 0 segnali, 0 decisioni, 0 ordini, 0 fill, 0 P&L
realizzato**. Il libro è rimasto immobile a 43 posizioni (38 S1 / 5 S4) e NAV 109.973,67 $,
identico al centesimo a sabato e domenica — coerente con un mercato chiuso. La riconciliazione
broker delle 21:35 ha trovato 43/43 posizioni `fully_held`, `anomalies: 0`.

I batch notturni hanno invece girato: forward-return (470 righe aggiornate), risk-monitor,
decay-monitor, held-news-loss (UNH), pesi ensemble (auto-apply con `max_delta=3,3e-13`, cioè
nessun movimento reale). Alle **14:20 UTC è atterrato un deploy da 27 commit** (backend
ricostruito, tutti i container riavviati una volta) che ha introdotto il worker
`worker-news-stream`: dalle 23:00 UTC il WebSocket Alpaca ingerisce **senza guardia di mercato**
in una coda il cui unico consumatore è invece gated da `market_closed`. Il DB di produzione era
ancora indietro di **6 migrazioni** (060→065), regolarizzate solo il 2026-09-08 alle 10:36.

## 2. Verdict finale

**OK con warning.**

La catena di trading è funzionalmente corretta per la giornata: il guard di calendario ha retto su
tutti i rami, nessun ordine è stato generato o inviato, nessuna posizione è stata toccata, la
riconciliazione col broker è 1:1. Il downgrade da "OK" non riguarda decisioni di trading — non ce
ne sono state — ma tre cose che rendono meno affidabile l'evidenza raccolta:

1. il nuovo worker di streaming news è stato messo in produzione **rotto a metà** (produce in una
   coda il cui consumatore è chiuso fuori orario) e il difetto è già misurabile: 232 elementi in
   coda al 2026-09-08 13:15, 130 dei quali (56%) già oltre la soglia di freschezza;
2. il DB è rimasto 6 migrazioni indietro per tutta la giornata (F-068 non ancora rimediata al
   2026-09-07), e solo la chiusura di borsa ha evitato un secondo giorno di ledger S4 perso;
3. gli endpoint REST del protocollo forense continuano a rifiutare il bearer token (F-041),
   quindi **la verifica prescritta via API non è stata eseguibile** ed è stata surrogata da query
   dirette a PostgreSQL, Redis e log persistenti.

Nessun `[DAY-xxx]` di questa giornata è un difetto di trading. Sono difetti di osservabilità,
processo di rilascio e correttezza dell'evidenza.

## 3. Timeline del 2026-09-07 (UTC)

| Ora | Componente | Evento | Esito | Fonte |
|---|---|---|---|---|
| 00:00–23:59 | beat | `poll-telegram-updates` ×17.277, `mobile-monitor-snapshot` ×1.440, `mobile-alert-evaluation` ×1.440 | tutti `succeeded` | `beat-2026-09-07.log` |
| 03:00:00 | worker | `performance.run_daily_report` | ok — "Overall IC: 0.2328, ICIR: 13.730"; `Reconciled 0 trade fill(s)` | `worker-2026-09-07.log:891` |
| 03:30:00 | worker | `retention.run_retention_sweep` | `{'deleted_news_log': 0, 'deleted_llm_responses': 0}` | worker log |
| 04:00:00 | worker | `performance.run_weekly_weights` (lunedì) | pesi calcolati; **alert Telegram 400 Bad Request** | worker log |
| 04:00:05 | worker | `check_and_apply_weights` | **auto-apply** glm-5.2 0,70 / gpt-oss 0,30, `max_delta=3,27e-13` → nessun cambio effettivo | `weight_update_log` id=19 |
| 05:00:00 | worker | `check_suggestion_expiry` | ok | worker log |
| 08:00–08:11 | cron host | `daily_alpha_miss_analysis.sh` (target **2026-09-04**) | dossier 09-04 scritto, `saltati non-borsa: 0`, giorno 25/40 | `logs/alpha_miss_analysis_2026-09-07.log` |
| 08:10 | cron host | `daily_s4_ic.sh` | `INSUFFICIENT_N (n=59, richiesto=213)` | `logs/s4_ic_2026-09-07.log` |
| 12:30–12:43 | cron host | `daily_analysis.sh` (target **2026-09-04**) | report forense 09-04 scritto e pushato | `logs/daily_analysis_2026-09-07.log` |
| 13:30 | beat | `regime-detector-premarket` | inviato (coda inference) | beat log |
| **14:00:00** | **worker/inference** | **prima finestra di mercato**: news-ingestion, alpaca-ingestion, sentiment, execution | **tutti `skipped: market_closed`** (execution: `engine=portfolio`) | worker log |
| 14:07:00 | worker | primo `portfolio-cycle` | `skipped: market_closed`, `next_open: 2026-09-08 09:30-04:00` | worker log |
| 14:12:05 | worker | primo `reconcile-fills-intraday` | `updated: 0`, riporta 13 lifecycle / 4 P0 / 7 P1 **considerati** | worker log |
| **14:20:01–14:20:39** | **host** | **`deploy_reconcile.sh`: riconciliazione e5512c9d → 38c94399, 27 commit, backend ricostruito** | tutti i container riavviati (1 `Warm shutdown` per worker) | `logs/deploy_reconcile_2026-09-07.log` |
| 14:20:22–24 | beat/worker/inference | ripartenza | `beat: Starting`, `general@376bebe1c02d ready`, `inference@a1c47ddc92be ready` | log container |
| 14:15→21:45 | worker | ciclo 15-minuti ripetuto ×32 su ingest/sentiment/execution + ×32 portfolio-cycle | 100% `market_closed` | worker log |
| 17:27:00 | worker | `reconcile-fills-intraday` | scrive le uniche 3 righe derivate del giorno: 1 `s4_lifecycle_events` (AVGO ENTRY_RECONCILIATION) + 2 `s4_exit_policy_events` (P0_RUNTIME_REPLAY, P1_TIME_ONLY_DECISION) | tabelle DB |
| 17:27 / 19:42 | worker | popolazione di replay del ledger S4 | scende **13 → 12 → 11** a mercato chiuso (finestra a 7 giorni di calendario) | worker log |
| 21:00:00 | worker | `decay-monitor` | **6 alert CRITICAL** (S1/S2/S4 con metriche identiche), nessun canale | worker log |
| 21:30:05 | worker | `reconcile-fills-evening` | `updated: 0` | worker log |
| 21:35:01 | worker | `reconcile-positions-eod` | `{'fully_held': 43}`, `anomalies: 0`, autoclose `dry_run: True` | worker log |
| 21:40:00 | worker | `shadow-comparison-report` | `skipped: window_open` | worker log |
| 22:00:12 | worker | `forward-return-worker` | `updated: 470, skipped_no_data: 175, errors: 0` | worker log |
| 22:20 | host | `deploy_reconcile` | nessun nuovo commit | deploy log |
| 22:30:01 | worker | `risk-monitor` | report id=87, NAV 109.973,67, exposure 0,2998, drawdown 0,012429, **0 alert**, `per_strategy_metrics: {}` | `risk_reports` |
| 22:45:00 | worker | `counterfactual-worker` | `total_decisions: 0` (nulla da calcolare) | worker log |
| 22:50:00 | worker | `held-news-loss-alert` | `alerted: 1 (UNH)`; `session_grid: skipped/no_market_session` | worker log + `mobile_events` |
| 22:50:01 | worker | valutatore mobile | l'incidente UNH è marcato `recovered` **0,39 s dopo** l'apertura | `mobile_events` |
| 22:55:00 | worker | `stale-drop-alert` | `measured: 0, alerted: 0` | worker log |
| **23:00:18** | **worker-news-stream** | **prima notizia dal WebSocket Alpaca** (GOOGL) → coda + `run_sentiment_worker` dispatchato | il sentiment risponde **`market_closed`**: l'articolo resta in coda | `worker-news-stream-2026-09-07.log`, `worker-inference-2026-09-07.log` |

Restart worker registrati nella giornata: **1** (14:20 UTC, deploy). Nessun crash, nessun
`Traceback`, nessun task `failed`.

## 4. Tabella news ingest

### Per fonte

| Fonte | Fetched | Queued | Duplicati | Scartati no-ticker | Scartati stale | Parse fail | Righe `news_log` |
|---|---|---|---|---|---|---|---|
| gdelt_gkg | **0** (32 cicli `market_closed`) | 0 | 0 | 0 | 0 | 0 | 0 |
| alpaca_benzinga (polling REST) | **0** (32 cicli `market_closed`) | 0 | 0 | 0 | 0 | 0 | 0 |
| alpaca_benzinga (**WebSocket**, dalle 23:00) | 1 | 1 | 0 | 0 | 0 | 0 | **0** |
| **Totale giornata** | **1** | **1** | 0 | 0 | 0 | 0 | **0** |

Riferimento: `ingestion_stats_daily` per `day='2026-09-07'` contiene **una sola riga**
(`alpaca_benzinga`, `updated_at 2026-09-07 23:00:18`), scritta dal worker di streaming.

### Per ticker

Non producibile: `SELECT count(*) FROM news_log WHERE created_at::date='2026-09-07'` → **0**.
L'ultima riga in `news_log` di tutto il database è `2026-09-04 19:45:34+00`. Nessun ticker ha
ricevuto copertura il 2026-09-07. Coerente con borsa chiusa; **non** è un guasto di ingest.

### Top news per impatto sul segnale

Nessuna: zero articoli scorati, zero segnali. L'unico articolo intercettato
("$100 Invested In Alphabet 10 Years Ago Would Be Worth This M…", tag `['GOOGL']`) non è mai
entrato in `news_log` perché il consumatore era chiuso.

### Problemi trovati sull'ingest

* Nessun duplicato, nessuna news stale, nessun timestamp futuro, nessun buco temporale: campione
  vuoto per costruzione.
* **Un problema reale c'è**, ma è a monte: la coda `news:queue` **non viene svuotata a fine
  sessione**. Al 2026-09-08 13:15 contiene 232 elementi, di cui 28 con `raw_ingested_at` del
  **2026-09-04** — residui mai drenati da quattro giorni. Vedi `[DAY-001]`.
* Confidenza dell'analisi ingest: **Alta** (tre fonti indipendenti concordi: log beat, log worker,
  `ingestion_stats_daily`/`news_log`).

## 5. Tabella performance modelli LLM

| Modello | Richieste | Successi | Errori | Timeout | Refusal/invalid | Latenza media | Distribuzione score |
|---|---|---|---|---|---|---|---|
| glm-5.2:cloud | **0** | 0 | 0 | 0 | 0 | n/d | campione vuoto |
| gpt-oss:20b-cloud | **0** | 0 | 0 | 0 | 0 | n/d | campione vuoto |
| FinBERT (fallback) | **0** | 0 | 0 | 0 | 0 | n/d | campione vuoto |

`llm_responses` per `generated_at::date='2026-09-07'` → 0 righe. `llm_budget` non ha riga per il
2026-09-07 (ultima: 2026-09-04, 0,151908 $). `ensemble_cycle_health` → 0 righe.

**Fallback rate FinBERT: n/d** (0 decisioni, non 0%). **Disaccordo fra modelli: n/d.**
**Downtime Ollama: non misurabile** — nessuna chiamata è stata tentata, quindi l'assenza di errori
non è prova di disponibilità.

Pesi ensemble in vigore a fine giornata (`ensemble:weights:current`):
`{"glm-5.2:cloud": 0.70, "gpt-oss:20b-cloud": 0.30}`, `source: auto_apply`. L'auto-apply del
04:00 ha mosso i pesi di 3,27e-13 — sono al tetto/pavimento da 09-07 e 08-31 e 08-24. Le ICIR
purificate divergono di un ordine di grandezza (glm 0,1269 vs gpt-oss 0,0113) ma il floor 0,30
impedisce che si traduca in peso. **Osservazione, non taratura** (periodo di freeze).

### Verifica funzionale (invarianti, verificate sul codice)

| Domanda | Esito | Evidenza |
|---|---|---|
| Output LLM validato prima del signal store? | **Parziale, difetto noto** | F-055 aperto: enum non validato né normalizzato in persistenza |
| L'ensemble gestisce varianza alta? | **No come gate** | F-037/F-054 aperti: `ensemble_std` letto solo dal postmortem, aggirato dal filtro di eleggibilità |
| Le news duplicate pesano più volte? | Deduplicate su `content_hash` + `Deduplicator(redis)` | `src/workers/news_stream.py:81` |
| La stessa news può generare segnali multipli? | **Sì, per fan-out multi-ticker** | F-012 aperto |
| Confidence bassa riduce il peso? | Sì, `score = polarity × confidence` | `src/workers/sentiment.py` |
| I modelli sono chiamati offline/background? | **Sì** | coda `inference`, concurrency=1; nessuna chiamata in `next()`/loop |
| Hallucination può entrare in decisione? | Mitigata (ensemble 2 modelli + resolver ticker), non azzerata | F-057 aperto: il resolver non ha mai emesso `RESOLVED` |

Nessuna di queste è osservabile il 2026-09-07: sono lo stato del sistema, non misure della
giornata.

## 6. Tabella segnali finali per ticker

**Nessun segnale.** `sentiment_signals` per `created_at::date='2026-09-07'` → 0 righe.
`s4_intent_events` → 0 righe. Ultimo segnale in DB: `2026-09-04 19:45:34+00`.

Soglia d'ingresso S4 in vigore (Redis `feedback:entry_threshold:S4`): **0,30** — invariata,
coerente con il freeze e con la deroga #191.

## 7. Tabella ordini generati/eseguiti

**Nessun ordine.** `execution_decisions` → 0 righe; `trades` (created/exit) → 0 righe;
`portfolio_cycles` → 0 righe; `stop_decisions` → 0 righe.

| Ora | Strategia | Ticker | Azione | Qty | Prezzo atteso | Fill | Stato | Motore | Rationale |
|---|---|---|---|---|---|---|---|---|---|
| — | — | — | — | — | — | — | — | — | *nessuna riga: mercato chiuso* |

L'unica attività "ordine-adiacente" è la **riconciliazione**, che ha letto (non scritto) il
broker: `reconcile-positions-eod` alle 21:35 riporta `{'fully_held': 43}`, `anomalies: 0`,
autoclose in `dry_run: True`. Corrisponde esattamente ai 43 `trades` con `exit_time IS NULL`.

## 8. Tabella PnL/rendimento

| Voce | Valore | Fonte |
|---|---|---|
| P&L realizzato 2026-09-07 | **0,00 $** (0 trade chiusi) | `trades.exit_time::date='2026-09-07'` → 0 righe |
| Variazione P&L non realizzato | **0,00 $** | NAV identico a 09-05 e 09-06 |
| NAV a fine giornata | **109.973,67 $** | `risk_reports` id=87, 22:30:01 |
| NAV 09-05 / 09-06 | 109.973,67 $ / 109.973,67 $ | `risk_reports` id 85, 86 |
| Esposizione lorda | 29,98 % | `risk_reports` id=87 |
| Herfindahl | 0,02729 | `risk_reports` id=87 |
| Posizioni aperte | 43 (38 S1 + 5 S4) | `trades WHERE exit_time IS NULL` |
| Notional d'ingresso del libro | 33.985,82 $ (S1 26.258,73 / S4 7.727,09) | idem |
| Slippage stimato | **n/d** — 0 esecuzioni; inoltre F-015: `slippage_est` è copia di `cost_usd` | `trades` |
| Commissioni/costi | **0,00 $** | nessun ordine |

P&L realizzato per sleeve, settimana precedente (contesto, non giornata):

| Data | S1 | S4 |
|---|---|---|
| 2026-09-01 | −113,70 $ (5) | −23,06 $ (1) |
| 2026-09-02 | −29,38 $ (2) | +19,79 $ (3) |
| 2026-09-03 | +50,64 $ (1) | +42,93 $ (5) |
| 2026-09-04 | +12,19 $ (1) | −53,06 $ (1) |
| **2026-09-07** | **0,00 $ (0)** | **0,00 $ (0)** |

Nota di consistenza: `risk_reports.combined_drawdown` vale **0,012429** identico su tutti e 7 i
report dal 09-01 al 09-07, mentre lo snapshot mobile del 09-08 riporta `current_drawdown`
**0,005760**. Due numeri incompatibili per la stessa grandezza — vedi `[DAY-006]`.

## 9. Analisi correttezza buy/sell

Nessun ordine è stato prodotto, quindi ogni controllo è verificato **per vacuità** salvo dove
indicato. Non è un pass debole: la domanda vera è *se il sistema avesse potuto* emettere ordini, e
la risposta è no su ogni ramo.

| Controllo | Esito | Evidenza |
|---|---|---|
| BUY generati solo quando consentito | ✅ vacuo + guard attivo | 32/32 `portfolio-cycle` → `market_closed` |
| SELL/exit generati correttamente | ✅ vacuo | 0 righe `execution_decisions` |
| Stop-loss rispettati | ✅ vacuo | `stop_decisions` 0 righe |
| Signal flip / max holding days / rebalance band | ✅ vacuo | nessun segnale in finestra |
| Ordini duplicati | ✅ nessuno | 0 ordini |
| Ordini contrari ravvicinati (roundtrip <30 min) | ✅ nessuno | 0 ordini |
| Ordini su ticker non consentiti | ✅ nessuno | 0 ordini |
| **Ordini fuori orario** | ✅ **nessuno, e il guard è la ragione** | tutti e 4 i rami (ingest/sentiment/execution/portfolio) hanno risposto `market_closed`; `next_open` calcolato correttamente al 2026-09-08 09:30-04:00, cioè **il Labor Day è stato riconosciuto dal calendario Alpaca**, non dedotto dal giorno della settimana |
| Nessun trade su dati stale | ✅ | 0 trade |
| Nessun trade con output LLM invalido | ✅ vacuo | 0 chiamate LLM |
| Circuit breaker attivo? | non applicabile | 0 cicli eseguiti |
| Strategia disabilitata? | n/a | `execution.engine: portfolio`; `run-execution` ha risposto `engine=portfolio` su 32/32 cicli → **nessun doppio motore** |
| Coerenza paper/live | ✅ **paper** | `portfolio_monitor_snapshots.mode='paper'`, `broker_environment='paper'` |
| Idempotenza su retry Celery | ✅ osservata | 33 cicli di `reconcile-fills-intraday` hanno riproposto gli stessi eventi derivati; solo 3 righe scritte (chiavi `event_id` deterministiche UUID5) |
| Riconciliazione ordini/fill/posizioni | ✅ **1:1** | broker 43 posizioni `fully_held` = 43 `trades` aperti, `anomalies: 0` |

### Nota obbligatoria su `exit_mechanism` (#184)

Questo report **non conta né interpreta** `exit_mechanism`: la giornata non ha uscite. Le uscite
citate nella tabella di contesto (§8) sono lette da `trades.exit_reason`, che è il motivo scritto
al momento della chiusura, non l'etichetta dedotta per età. Nessuna riga pre-fix #184 è stata
usata per produrre numeri in questo report.

## 10. Anomalie trovate

### [DAY-001] Il worker di streaming news ingerisce fuori orario in una coda il cui consumatore è chiuso

* **Tipo:** Bug
* **Area:** News / Ops
* **Evidenza:**
  * file/log/tabella: `src/workers/news_stream.py:55-95`, `logs/containers/worker-news-stream-2026-09-07.log`, `logs/containers/worker-inference-2026-09-07.log`, Redis `news:queue`, `ingestion_stats_daily`
  * timestamp: 2026-09-07T23:00:18Z (prima notizia), 2026-09-07T23:00:20Z (sentiment skip)
  * snippet/query:
    ```
    23:00:18 INFO:__main__:News stream: $100 Invested In Alphabet 10 Years Ago ... [['GOOGL']]
    23:00:18 ingestion_stats_daily: alpaca_benzinga fetched=1 queued=1
    23:00:20 run_sentiment_worker succeeded: {'skipped': True, 'reason': 'market_closed'}
    ```
    ```
    $ redis-cli LLEN news:queue   # 2026-09-08 13:15Z
    232      # 130 (56%) gia' oltre MAX_NEWS_AGE_HOURS=2; p50 eta' 2,85h; max 94,4h
    ```
* **Descrizione:** il deploy delle 14:20 del 2026-09-07 (27 commit) ha attivato
  `worker-news-stream`. `_handle_article()` non ha alcuna guardia di calendario: parsa, deduplica,
  accoda e dispatcha `run_sentiment_worker` in qualunque momento. Il consumatore invece è gated
  (`src/workers/sentiment.py:1121`, `if not is_market_open(): return {'skipped': True, 'reason':
  'market_closed'}`) **e** la finestra beat è 14:00–21:00 UTC. Risultato: tutto ciò che il
  WebSocket cattura fuori da quella finestra si accumula in `news:queue` e invecchia oltre
  `MAX_NEWS_AGE_HOURS=2`, per essere poi scartato come stale senza mai costare una chiamata LLM.
  Il 2026-09-07 l'effetto è 1 articolo; il 2026-09-08 alle 13:15 sono già 203 articoli catturati
  dalle 02:00 alle 13:00 UTC, di cui **93 certamente oltre soglia** prima che il consumatore apra.
  In più `_persist_ingestion_observability("alpaca_benzinga", …)` scrive nella **stessa riga** di
  `ingestion_stats_daily` usata dal polling REST: le due vie di ingestione diventano
  indistinguibili nella serie storica.
* **Impatto:** la capability comprata con #455 (latenza <1 s invece di p50 ~1h50m) è in produzione
  ma non produce nulla, e nel farlo inquina la serie `ingestion_stats_daily` che è la base di
  F-007/F-019. Nessuna perdita di trading rispetto al baseline precedente — prima quelle notizie
  non venivano nemmeno catturate.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** ticket di correttezza — o il consumatore drena la coda anche fuori
  orario (accettando che `_is_stale_news` scarti), o il produttore smette di accodare quando
  `is_market_open()` è falso; e in ogni caso `source` distinto (`alpaca_benzinga_stream`) in
  `ingestion_stats_daily`. **Non toccare `MAX_NEWS_AGE_HOURS`: è taratura, congelata al 28/09.**
* **Test/monitor consigliato:** test che con mercato chiuso `_handle_article` non lasci elementi
  orfani in `news:queue`; alert quando `LLEN news:queue > N` all'apertura della finestra.

### [DAY-002] Le finestre e i budget di retry dei job derivati sono in tempo di parete, non in sedute

* **Tipo:** Bug
* **Area:** Data / PnL
* **Evidenza:**
  * file/log/tabella: `src/store/pg_store.py:900-903`, `logs/containers/worker-2026-09-07.log`, `execution_decisions`
  * timestamp: 2026-09-07T14:12→21:57 (33 cicli); 2026-09-06T22:45 (`attempts_exhausted: 4`)
  * snippet/query:
    ```sql
    -- fetch_s4_submitted_intents
    WHERE event_type='disposition' AND reason_code IN ('SUBMITTED','BROKER_REJECT')
      AND occurred_at > now() - '7 days'::interval
    ```
    ```
    14:12:05 {'updated': 0, 's4_lifecycle_events': 13, 's4_p0_events': 4, 's4_p1_events': 7}
    17:27:05 {'updated': 0, 's4_lifecycle_events': 12, 's4_p0_events': 5, 's4_p1_events': 7}
    19:42:05 {'updated': 0, 's4_lifecycle_events': 11, 's4_p0_events': 4, 's4_p1_events': 7}
    ```
    ```
    09-05 counterfactual: {'pending_retry': 4, ...}
    09-06 counterfactual: {'attempts_exhausted': 4, ...}
    09-07 counterfactual: {'total_decisions': 0, ...}
    ```
* **Descrizione:** due meccanismi derivati misurano il tempo in giorni di calendario invece che in
  sedute. (a) La popolazione di replay del ledger S4 è definita da una finestra di 7 giorni di
  parete: il 2026-09-07, **a mercato chiuso e con zero attività**, gli intent replayati sono scesi
  da 13 a 11 semplicemente perché l'orologio avanzava. Un ponte di tre giorni (sab/dom/festivo)
  consuma il 43% della finestra senza che una sola seduta sia passata. (b) Il budget di retry del
  worker controfattuale è stato speso il 09-05 e il 09-06 — giorni in cui **per costruzione**
  nessuna barra nuova può esistere — esaurendo i 3 tentativi su 4 decisioni
  (`SHEL` ×3 e `MMM` ×1 del 2026-09-04 19:22–19:52, tutte `SKIP_THRESHOLD`,
  `counterfactual_skip_reason = NO_BARS_AFTER_HORIZON`), che restano definitivamente senza
  controfattuale. Lo stesso pattern si era già verificato il 2026-08-28 (4 `SHEL`).
* **Impatto:** l'evidenza raccolta nella finestra di osservazione perde righe per ragioni di
  calendario, non di mercato. Il costo di trading è nullo (le 4 decisioni sono `SKIP_THRESHOLD`,
  nessun ordine), ma il costo sull'**evidenza** è reale e cresce a ogni ponte: l'ultima ora di
  ogni seduta è la più esposta, perché l'orizzonte +1h cade oltre le 20:00 UTC.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** ticket di correttezza (esente dal freeze: senza questo, l'evidenza delle
  prossime settimane è incompleta in modo non casuale). Contare sedute di borsa, non giorni, sia
  nella finestra di `fetch_s4_submitted_intents` sia nel decremento del budget di retry
  controfattuale; non decrementare i tentativi quando il mercato è chiuso.
* **Test/monitor consigliato:** test con calendario che include un ponte di 3 giorni, asserendo
  popolazione di replay invariata e `counterfactual_attempts` invariato.

### [DAY-003] Il DB di produzione è rimasto 6 migrazioni indietro per tutta la giornata; il redeploy automatico non applica migrazioni

* **Tipo:** Bug
* **Area:** Ops / Data
* **Evidenza:**
  * file/log/tabella: `alembic_schema_migrations`, `scripts/deploy_reconcile.sh`, `logs/deploy_reconcile_2026-09-07.log`
  * timestamp: 2026-09-07T14:20:04Z (deploy 27 commit); 2026-09-08T10:36:00Z (migrazioni applicate)
  * snippet/query:
    ```
    2026-09-07T14:20:04Z === Riconciliazione e5512c9d → 38c94399 (27 commit, da ricostruire: backend) ===
    $ grep -c 'migrat|psql' scripts/deploy_reconcile.sh   # 0
    ```
    ```
    060_s4_burned_slot_metrics.sql .. 065_news_poc_samples.sql  applied_at = 2026-09-08 10:36:00
    ```
* **Descrizione:** il 2026-09-07 il DB non aveva ancora le colonne della migrazione 060
  (`held_at_rank`, `signal_age_at_slot`), la causa già registrata come F-068 dell'azzeramento del
  ledger `s4_intent_events` del 2026-09-04. Non solo: erano pendenti **sei** migrazioni (060→065),
  regolarizzate solo il 2026-09-08 alle 10:36. Nel frattempo il cron `deploy_reconcile.sh`, che
  gira ogni 2 ore, ha ricostruito il backend con 27 commit alle 14:20 del 09-07 **senza alcuna
  fase di migrazione** — lo script non contiene un solo riferimento a `psql` o a `migrations/`.
  Il codice nuovo va in produzione contro uno schema vecchio, per progetto.
* **Impatto:** il 2026-09-07 il danno è nullo **solo perché la borsa era chiusa**: nessun ciclo ha
  tentato l'INSERT fallito. Al primo giorno di borsa utile il ledger S4 sarebbe stato perso di
  nuovo. La rimedia è arrivata il 09-08 alle 10:36, tre ore prima dell'apertura.
* **Severità:** High
* **Confidenza:** High
* **Azione consigliata:** ticket di correttezza: `deploy_reconcile.sh` deve applicare le
  migrazioni pendenti prima di far ripartire i container, e fallire rumorosamente (non `exit 0`)
  se non ci riesce.
* **Test/monitor consigliato:** monitor che confronta `max(version)` in `alembic_schema_migrations`
  con il massimo file in `migrations/` e apre un incidente `critical` se divergono.

### [DAY-004] Il bearer token del protocollo forense è rifiutato su tutti gli endpoint REST (ricorrenza F-041)

* **Tipo:** Bug
* **Area:** Frontend / Ops
* **Evidenza:**
  * file/log/tabella: `logs/containers/api-2026-09-07.log`
  * timestamp: 2026-09-07 (unica risposta non-200 della giornata su 9.057 richieste)
  * snippet/query:
    ```
    "403 GET /api/decisions?limit=5"
    $ curl -H "Authorization: Bearer __ALEMBIC_API_KEY__" .../api/positions
    {"detail":"Invalid or expired JWT token"}     # idem su decisions, trades, signals, orders
    ```
* **Descrizione:** il canale di verifica prescritto dal protocollo forense è inagibile da settimane.
  Tutte e cinque le API richieste rispondono `Invalid or expired JWT token`. L'analisi è stata
  ricostruita da PostgreSQL, Redis e log persistenti — sorgenti valide ma non le stesse: le API
  sono l'unico punto in cui si vede ciò che *l'operatore* vede.
* **Impatto:** ogni report forense perde la verifica incrociata DB↔API. Un disallineamento fra le
  due (esattamente la classe di F-053, "storico P&L etichettato col giorno sbagliato") sarebbe
  invisibile a questa analisi.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** emettere e documentare un token di servizio a lunga scadenza per il cron
  forense, o un percorso di auth dedicato.
* **Test/monitor consigliato:** smoke test nel cron forense che fallisce rumorosamente se i 5
  endpoint non rispondono 200.

### [DAY-005] Il decay monitor emette 6 CRITICAL con metriche identiche per S1/S2/S4 e nessun canale (ricorrenza F-004 + F-062)

* **Tipo:** Bug
* **Area:** Ops / Signal
* **Evidenza:**
  * file/log/tabella: `logs/containers/worker-2026-09-07.log`, `mobile_events`
  * timestamp: 2026-09-07T21:00:00Z
  * snippet/query:
    ```
    CRITICAL DECAY [S1]: IC dropped 240% from 0.035 to -0.049 | Hit rate 54.0% -> 28.9%
    CRITICAL DECAY [S2]: IC dropped 217% from 0.042 to -0.049 | Hit rate 56.0% -> 28.9%
    CRITICAL DECAY [S4]: IC dropped 276% from 0.028 to -0.049 | Hit rate 52.0% -> 28.9%
    ```
    ```sql
    SELECT count(*) FROM mobile_events
     WHERE created_at::date='2026-09-07' AND kind='alert_incident';  -- 0
    ```
* **Descrizione:** il valore "corrente" è **identico** (−0,049 / 28,9%) per tre strategie con
  libri, orizzonti e numerosità diversi: è una metrica pipeline-globale confrontata con tre
  baseline distinte (F-004). In più il job è girato su un giorno **senza seduta**, quindi le
  metriche non sono cambiate da venerdì eppure l'alert si ripete. E i sei CRITICAL non hanno
  raggiunto nessuno: zero `mobile_events` di tipo `alert_incident`, solo `log.critical` (F-062).
  Sulla stessa giornata `run_daily_report` alle 03:00 ha pubblicato "Overall IC: 0.2328, ICIR:
  13.730": due serie di IC incompatibili, prodotte a 18 ore di distanza dallo stesso sistema, senza
  che nulla le riconcili. Un ICIR di 13,7 non è un valore plausibile per un segnale azionario.
* **Impatto:** l'allarme più forte che il sistema sa emettere è, allo stesso tempo, sbagliato nei
  numeri e muto nel canale. Chi legge i log si abitua a ignorarlo.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** già coperto da F-004/F-062. Aggiungere: sopprimere il decay check nei
  giorni senza seduta (non ricalcola nulla) e riconciliare le due definizioni di IC.
* **Test/monitor consigliato:** test che asserisce IC per-strategia distinti su input distinti;
  test che ogni `log.critical` del decay monitor produca un `mobile_events` corrispondente.

### [DAY-006] `risk_reports.combined_drawdown` è congelato a 0,012429 e `per_strategy_metrics` è vuoto (ricorrenza F-003 + F-050)

* **Tipo:** Bug
* **Area:** Risk
* **Evidenza:**
  * file/log/tabella: `risk_reports`, `portfolio_monitor_snapshots`
  * timestamp: 2026-09-07T22:30:01Z (report id=87)
  * snippet/query:
    ```
    id | timestamp   | nav        | combined_drawdown | per_strategy_metrics
    81 | 2026-09-01  | 109683.43  | 0.012429          | {}
    ...
    87 | 2026-09-07  | 109973.67  | 0.012429          | {}
    ```
    ```
    portfolio_monitor_snapshots 2026-09-08 09:08 -> current_drawdown = 0.005760
    ```
* **Descrizione:** sette report consecutivi, NAV che oscilla di ~400 $, e `combined_drawdown`
  identico alla sesta cifra decimale. Nello stesso periodo lo snapshot mobile calcola 0,005760 per
  la stessa grandezza. `per_strategy_metrics` resta `{}` da quando la voce sintetica `portfolio` è
  stata rimossa (F-050): **nessuna sleeve ha un drawdown sorvegliato**.
* **Impatto:** il report di rischio giornaliero non è utilizzabile per rilevare un drawdown, che è
  la sua unica ragione d'essere. `alerts: []` su 7 giorni non è informazione.
* **Severità:** High
* **Confidenza:** High
* **Azione consigliata:** già coperto da F-003/F-050; questa è la settima occorrenza consecutiva
  con lo stesso valore, il che è un dato nuovo: non è rumore, è un valore che non viene ricalcolato.
* **Test/monitor consigliato:** test che, dato un NAV in calo, `combined_drawdown` cresca;
  invariante che `per_strategy_metrics` non sia mai vuoto con ≥1 sleeve attiva.

### [DAY-007] L'incidente "copertura news assente su UNH" viene chiuso 0,39 s dopo l'apertura (ricorrenza F-058)

* **Tipo:** Bug
* **Area:** Ops
* **Evidenza:**
  * file/log/tabella: `mobile_events`
  * timestamp: `occurred_at 2026-09-07 22:50:00.748971+00` → `last_observed_at 22:50:01.13893+00`
  * snippet/query:
    ```
    kind=position severity=warning status=recovered
    title="Copertura news assente su UNH"
    details={"return_from_entry": -0.0713, "zero_news_sessions": 2, "signals_today": 0}
    ```
* **Descrizione:** l'alert EOD introdotto con la deroga #324 ha fatto esattamente il suo lavoro —
  UNH è a −7,13% dall'ingresso con 2 sedute senza righe news — ed è stato marcato `recovered` dal
  valutatore mobile generico 390 ms dopo, prima che qualunque essere umano potesse vederlo. Stesso
  esito il 09-04 su UNH, il 09-03 su ASML e WDC, il 09-02 su ASML.
* **Impatto:** il canale operatore-nel-ciclo aperto dalla deroga #324 è, di fatto, chiuso. La
  deroga è registrata nella carta come strumentazione utile; l'evidenza dice che non consegna.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** già coperto da F-058 (il valutatore generico chiude incidenti di cui non
  è proprietario). Nessuna azione nuova, ma la ricorrenza è ora 5 giornate su 5 con alert.
* **Test/monitor consigliato:** test che un incidente `position` sopravviva ad almeno un ciclo del
  valutatore generico.

### [DAY-008] La telemetria della riconciliazione conta gli eventi considerati, non quelli scritti (ricorrenza F-061)

* **Tipo:** Anomalia
* **Area:** Ops
* **Evidenza:**
  * file/log/tabella: `logs/containers/worker-2026-09-07.log`, `s4_lifecycle_events`, `s4_exit_policy_events`
  * timestamp: 33 cicli fra 14:12 e 21:57 UTC
  * snippet/query:
    ```
    33 cicli riportano s4_lifecycle_events 11-13, s4_p0_events 4-5, s4_p1_events 7
    -> ~780 "eventi" dichiarati nella giornata
    SELECT count(*) FROM s4_lifecycle_events  WHERE created_at::date='2026-09-07';  -- 1
    SELECT count(*) FROM s4_exit_policy_events WHERE created_at::date='2026-09-07'; -- 2
    ```
* **Descrizione:** `_reconcile_s4_lifecycles` restituisce `len(events)` — gli eventi *costruiti* —
  mentre `write_s4_lifecycle_events` è idempotente su `event_id` UUID5 e ne scrive quasi zero.
  Il valore di ritorno è il numero che finisce nei log e in qualunque cruscotto lo legga.
  Stessa forma di F-014 (`orders_count` conta i target, non i piazzati).
* **Impatto:** nullo sui dati (l'idempotenza funziona, ed è anzi una prova positiva: 33 retry, 3
  righe); reale sulla leggibilità: chi guarda i log crede che il ledger stia scrivendo 780 eventi
  su una giornata di borsa chiusa.
* **Severità:** Low
* **Confidenza:** High
* **Azione consigliata:** restituire il conteggio di righe effettivamente inserite (`rowcount`
  dell'`ON CONFLICT DO NOTHING`) accanto a quello dei candidati.
* **Test/monitor consigliato:** test che, ripetendo la riconciliazione due volte, il secondo giro
  riporti 0 scritture.

### [DAY-009] Il bot token Telegram compare in chiaro 17.278 volte nei log persistenti della giornata (ricorrenza F-018)

* **Tipo:** Rischio
* **Area:** Ops
* **Evidenza:**
  * file/log/tabella: `logs/containers/worker-inference-2026-09-07.log` (17.275), `logs/containers/worker-2026-09-07.log` (3)
  * timestamp: tutta la giornata, ogni 5 secondi
  * snippet/query:
    ```
    INFO HTTP Request: GET https://api.telegram.org/bot8611445937:AAH3...Q5c/getUpdates?...
    ```
* **Descrizione:** il poller Telegram gira ogni 5 secondi e httpx logga l'URL completo a livello
  INFO, token incluso. I log sono ora **persistenti su host** (`logs/containers/`, per progetto,
  dopo F-027) e versionabili per errore. Un solo giorno produce 17.278 copie del segreto.
* **Impatto:** chiunque abbia accesso in lettura alla directory dei log ha il controllo del bot.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** portare `httpx` a WARNING nei worker, o filtro di redazione sul logger.
* **Test/monitor consigliato:** grep nel CI/pre-commit che fallisce se un pattern `bot\d+:AA`
  compare in `logs/`.

### [DAY-010] Il fetch del benchmark SPY fallisce 84 volte in una giornata senza seduta (ricorrenza F-016)

* **Tipo:** Anomalia
* **Area:** Data
* **Evidenza:**
  * file/log/tabella: `logs/containers/worker-2026-09-07.log`
  * timestamp: tutta la giornata
  * snippet/query:
    ```
    WARNING SPY benchmark fetch failed: {"message":"subscription does not permit querying recent SIP data"}
    ```
* **Descrizione:** limite di sottoscrizione SIP, errore permanente e noto. La novità del 09-07 è
  che il fallimento si ripete 84 volte **in un giorno in cui non esiste una barra SPY da
  scaricare**: il chiamante non consulta il calendario prima di provare.
* **Impatto:** nessun benchmark relativo disponibile per l'attribuzione; rumore che nasconde
  warning veri. Il conteggio 84 è inflazionato dai retry a vuoto.
* **Severità:** Low
* **Confidenza:** High
* **Azione consigliata:** già coperto da F-016; aggiungere il gate di calendario prima del retry.
* **Test/monitor consigliato:** asserire zero tentativi di fetch benchmark con mercato chiuso.

### [DAY-011] L'alert Telegram del suggerimento pesi fallisce con 400, quello di auto-apply passa (ricorrenza F-005)

* **Tipo:** Bug
* **Area:** Ops
* **Evidenza:**
  * file/log/tabella: `logs/containers/worker-2026-09-07.log`
  * timestamp: 2026-09-07T04:00:00Z (400) vs 04:00:05Z (200)
  * snippet/query:
    ```
    04:00:00 POST .../sendMessage "HTTP/1.1 400 Bad Request"
    04:00:00 WARNING TelegramNotifier: Failed to send alert
    04:00:05 POST .../sendMessage "HTTP/1.1 200 OK"
    04:00:05 INFO Weights auto-applied successfully
    ```
* **Descrizione:** due messaggi consecutivi dallo stesso notifier verso la stessa chat: il primo
  (il *suggerimento* di pesi) è rifiutato con 400, il secondo (l'*applicazione* avvenuta) passa.
  Il 400 è quasi certamente un problema di formattazione/markup del messaggio, non di credenziali —
  altrimenti fallirebbero entrambi. L'operatore riceve "pesi applicati" senza aver mai ricevuto
  "questi sono i pesi proposti".
* **Impatto:** notifica asimmetrica: si comunica il fatto compiuto, non la proposta. In un periodo
  di freeze è esattamente il messaggio che si vorrebbe leggere prima.
* **Severità:** Medium
* **Confidenza:** Medium (la causa 400 è inferita dal contrasto con il 200 successivo, non letta
  dal corpo della risposta, che il notifier non logga)
* **Azione consigliata:** loggare il corpo della risposta Telegram in caso di 4xx; già tracciato
  come F-005.
* **Test/monitor consigliato:** test di serializzazione del messaggio di suggerimento pesi.

## 11. False positive e aree risultate corrette

Verificate esplicitamente e risultate **corrette** — vanno dette, perché su una giornata vuota è
facile scambiare il silenzio per un guasto:

1. **Il vuoto del 2026-09-07 non è un guasto.** Prima ipotesi scartata: i log beat mostravano zero
   task di mercato il 09-05 e il 09-06, e la lettura affrettata era "il beat è morto venerdì". Il
   2026-09-05 è **sabato**: `day_of_week="1-5"` funziona. Verificato con `date -d`.
2. **Il Labor Day è stato riconosciuto dal calendario del broker, non dedotto dal giorno.** Il
   `portfolio-cycle` riporta `next_open: '2026-09-08 09:30:00-04:00'`, che è la risposta di Alpaca,
   non un calcolo locale. Il rischio di un lunedì festivo trattato come feriale non si è
   materializzato.
3. **La riconciliazione broker↔DB è pulita:** 43 posizioni `fully_held`, `anomalies: 0`, contro 43
   `trades` aperti. Nessuna posizione fantasma, nessun ammanco.
4. **L'idempotenza sotto retry funziona:** 33 esecuzioni della riconciliazione S4 hanno prodotto 3
   righe. È la prova positiva che le chiavi `event_id` deterministiche fanno il loro mestiere.
5. **`portfolio_monitor_snapshots` a zero righe è corretto**, non un guasto: gli snapshot sono
   persistiti solo fra le 13:30 e le 20:00 delle giornate di seduta (verificato su 09-01→09-04).
6. **`run-execution` non ha mai potuto emettere ordini:** 32/32 cicli con `engine=portfolio`.
   Nessun doppio motore di esecuzione, coerente con `config/trading.yaml`.
7. **I cron host hanno mirato la seduta giusta:** sia `daily_analysis.sh` sia
   `daily_alpha_miss_analysis.sh`, girando il lunedì festivo, hanno preso come target il
   **2026-09-04**, con `saltati non-borsa: 0`. Nessun dossier fittizio per il 09-07.
8. **L'auto-apply dei pesi non è una violazione del freeze in sostanza:** `max_delta = 3,27e-13`,
   i pesi erano già al tetto 0,70/0,30 dal 2026-08-24. Resta però un meccanismo *automatico* che
   può muovere i pesi durante il freeze, della stessa famiglia del ratchet #191 — vedi §13.
9. **F-068 è stata rimediata**, il 2026-09-08 alle 10:36, tre ore prima dell'apertura. La giornata
   del 09-07 l'ha attraversata senza danni solo perché non c'era seduta (vedi `[DAY-003]`).

## 12. Dati mancanti o non accessibili

| Cosa manca | Perché | Query/azione che servirebbe |
|---|---|---|
| Verifica via API REST (decisions/trades/signals/positions/orders) | F-041, token rifiutato (`[DAY-004]`) | token di servizio valido, poi i 5 `curl` del protocollo |
| Stato di disponibilità Ollama il 2026-09-07 | zero chiamate: l'assenza di errori non prova l'uptime | probe di health indipendente dal traffico, es. un ping schedulato che scriva `ensemble_cycle_health` anche a mercato chiuso |
| Fallback rate FinBERT | denominatore zero | n/d per costruzione |
| Lista ordini lato broker per il 2026-09-07 | non interrogata: la sessione è read-only e il protocollo vieta chiamate al broker | `GET /v2/orders?after=2026-09-07T00:00:00Z&status=all`; **surrogato usato**: `reconcile-positions-eod` ha letto il broker e riportato `anomalies: 0` |
| P&L non realizzato per ticker al 2026-09-07 | nessuno snapshot persistito nei giorni senza seduta | il valore di riferimento è quello del 09-04 20:00; per il 09-07 sarebbe identico |
| Corpo della risposta Telegram 400 | il notifier non lo logga | vedi `[DAY-011]` |
| Definizione di "seduta" in `zero_news_sessions` dell'alert UNH | non ispezionata in questa sessione | leggere `build_exit_coverage`: se conta giorni di calendario, il 09-07 festivo gonfia il contatore |

## 13. Raccomandazioni immediate

1. **Chiudere il buco di rilascio (`[DAY-003]`).** `deploy_reconcile.sh` gira ogni 2 ore in
   automatico e mette in produzione codice contro uno schema non migrato. È il difetto con la
   probabilità più alta di ri-produrre un F-068 su una giornata di borsa vera.
2. **Decidere il destino del worker di streaming (`[DAY-001]`).** Oggi consuma quota API e
   inquina `ingestion_stats_daily` senza produrre una riga di `news_log`. Le due uscite ragionevoli
   sono "drena anche fuori orario" o "non accodare fuori orario"; la terza — lasciarlo così — è
   quella che sta correndo adesso.
3. **Riparare il canale forense (`[DAY-004]`).** Ogni giorno di ritardo è un report costruito su
   una sola fonte.
4. **Non toccare nulla di tarabile.** Freeze fino al 2026-09-28: `MAX_NEWS_AGE_HOURS`, la soglia
   0,30, il floor 0,30 dei pesi ensemble, le bande di rebalance restano dove sono. Tutti i ticket
   proposti sopra sono di correttezza e passano il test della carta ("se non lo correggo,
   l'evidenza delle prossime settimane è sbagliata?").
5. **Registrare due discontinuità nella carta di osservazione.** (a) Il deploy del 2026-09-07
   14:20 (27 commit, incluso `worker-news-stream`) è l'attuazione della deroga #454/#455/#456 del
   2026-09-01, la cui riga dice ancora "deploy non ancora avvenuto": va datata con
   `38c94399 @ 2026-09-07T14:20:39Z`. (b) L'applicazione delle migrazioni 060→065 il 2026-09-08
   alle 10:36 cambia cosa il sistema riesce a persistere: la serie `s4_intent_events` ha un buco
   dal 2026-09-04 al 2026-09-07 incluso.

## 14. Test o monitor da aggiungere

| # | Test/monitor | Difende da |
|---|---|---|
| T1 | Monitor: `max(alembic_schema_migrations.version)` vs massimo file in `migrations/` → incidente `critical` se divergono | `[DAY-003]`, F-068 |
| T2 | Monitor: `LLEN news:queue` all'apertura della finestra sentiment; alert oltre soglia | `[DAY-001]` |
| T3 | Test: con `is_market_open()==False`, `_handle_article` non lascia elementi orfani in coda | `[DAY-001]` |
| T4 | Test: finestra di `fetch_s4_submitted_intents` su un calendario con ponte di 3 giorni → popolazione invariata | `[DAY-002]` |
| T5 | Test: `counterfactual_attempts` non si decrementa nei giorni senza seduta | `[DAY-002]` |
| T6 | Smoke test nel cron forense: i 5 endpoint REST rispondono 200, altrimenti il cron fallisce | `[DAY-004]` |
| T7 | Test: IC per-strategia distinti a partire da input distinti nel decay monitor | `[DAY-005]`, F-004 |
| T8 | Invariante: ogni `log.critical` del decay monitor genera un `mobile_events` | `[DAY-005]`, F-062 |
| T9 | Test: NAV decrescente ⇒ `combined_drawdown` crescente; `per_strategy_metrics` mai vuoto con ≥1 sleeve | `[DAY-006]`, F-003/F-050 |
| T10 | Test: un incidente `position` sopravvive a un ciclo del valutatore generico | `[DAY-007]`, F-058 |
| T11 | Test: seconda riconciliazione consecutiva riporta 0 scritture effettive | `[DAY-008]`, F-061 |
| T12 | Guardia CI/pre-commit: pattern `bot\d+:AA` in `logs/` fa fallire | `[DAY-009]`, F-018 |
| T13 | Test: nessun tentativo di fetch benchmark con mercato chiuso | `[DAY-010]`, F-016 |

## 15. Ticket tecnici suggeriti

Tutti di **correttezza** (esenti dal freeze della carta di osservazione), nessuno di taratura.

| Priorità | Titolo | Finding | Note |
|---|---|---|---|
| P0 | `deploy_reconcile.sh`: applicare le migrazioni pendenti prima del restart, fallire rumorosamente | `[DAY-003]`, F-068 | il cron gira ogni 2h senza supervisione |
| P1 | `news_stream`: allineare produttore e consumatore sulla guardia di mercato + `source` distinto in `ingestion_stats_daily` | `[DAY-001]`, F-069 | non toccare `MAX_NEWS_AGE_HOURS` |
| P1 | Contare sedute, non giorni di calendario, nella finestra del ledger S4 e nel budget di retry controfattuale | `[DAY-002]`, F-070 | esente: senza, l'evidenza è incompleta in modo non casuale |
| P1 | Token di servizio per il protocollo forense | `[DAY-004]`, F-041 | sblocca la verifica incrociata |
| P2 | Riconciliare le due serie di IC (daily report vs decay monitor) e sopprimere il decay check nei giorni senza seduta | `[DAY-005]`, F-004 | ICIR 13,73 non è plausibile |
| P2 | Redazione del bot token nei log httpx | `[DAY-009]`, F-018 | 17.278 occorrenze/giorno su log persistenti |
| P3 | Telemetria di riconciliazione: righe scritte accanto a candidati | `[DAY-008]`, F-061 | |
| P3 | Gate di calendario prima del fetch benchmark | `[DAY-010]`, F-016 | |

## 16. Stato sistema

| Voce | Valore |
|---|---|
| **Ollama** | **Non verificabile.** Zero chiamate tentate in tutta la giornata (mercato chiuso): 0 righe in `llm_responses`, nessuna riga `llm_budget` per il 09-07, `ensemble_cycle_health` vuota. Ore di downtime: **n/d**, non 0. |
| **Fallback FinBERT** | **n/d** — 0 decisioni, denominatore nullo. Non è "0%". |
| **Ensemble attivo** | glm-5.2:cloud (peso 0,70) + gpt-oss:20b-cloud (0,30), `source: auto_apply`, invariati (`max_delta` 3,27e-13 all'auto-apply delle 04:00) |
| **Worker restart** | **1** — 2026-09-07T14:20:22–24Z, tutti i container (beat, worker, worker-inference, api) riavviati insieme dal deploy da 27 commit. Nessun crash, nessun `Warm shutdown` non pianificato. |
| **Nuovo componente in esecuzione** | `worker-news-stream` (WebSocket Alpaca), primo messaggio 23:00:18Z |
| **Errori/eccezioni non gestite** | **0** `Traceback`, 0 task Celery `failed` |
| **Warning ricorrenti** | 84× SPY benchmark (F-016), 2× Telegram 400 (F-005) |
| **Task Celery eseguiti** | worker: 6.574 righe di log / ~2.880 mobile + 289 di dominio; worker-inference: 34.554 poll Telegram + 33 sentiment + 4 regime |
| **Migrazioni DB pendenti a fine giornata** | **6** (060→065), applicate il 2026-09-08 10:36 |
| **NAV / posizioni a fine giornata** | 109.973,67 $ / 43 posizioni (38 S1, 5 S4), esposizione 29,98%, cash ~70% |
| **Modalità** | paper (`alpaca_paper`), `execution.engine: portfolio` |

---

*Report prodotto in sola lettura. Nessun file modificato oltre a questo e a
`docs/evidence/findings.json`. Nessun commit, nessun push, nessun ordine.*
