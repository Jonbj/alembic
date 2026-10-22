# Forensic daily report — 2026-10-09 (venerdì)

Analisi read-only eseguita il 2026-10-22. Timezone operativo: UTC (`celery_app.py`). DST USA in vigore (EDT): RTH = 13:30–20:00 UTC. Le finestre beat a UTC fisso restano un'ambiguità strutturale (F-021). Fonti: DB `trading` (solo SELECT), API REST locale, `logs/containers/{worker,beat,api,worker-news-stream}-2026-10-09.log`, `logs/deploy_reconcile_2026-10-09.log`, `docs/evidence/dossier/2026-10-09.json`, `market_daily.jsonl`, `ALPHA_MISS_REPORT_2026-10-09.md`. **Non esiste `worker-inference-2026-10-09.log`**: il container non ha prodotto righe in tutta la giornata.

## 1. Executive summary

- **Seduta intera senza valutazione sentiment.** `worker-inference` era in warm shutdown dal 2026-10-08 16:20:12Z e non è ripartito (rientro solo il 2026-10-16). Il 10-09 ci sono 0 righe `news_log`, 0 `sentiment_signals`, 0 `llm_responses` e 0 `finbert_fallback_events`, su 96/96 simboli.
- La coda `inference` non aveva consumatori. Il beat ha emesso 32 `sentiment-worker`, 15 `sentiment-shadow-offsession`, 2 `regime-detector` e 17.280 `poll-telegram-updates`, mai eseguiti. `news_queue_census` è passata da 326 a **1.008** elementi (oldest 34 h); `ingestion_stats_daily` benzinga riporta queued 667.
- Ingest attivo e scoring fermo: il news-stream ha loggato 391 titoli (crollo telecom TMUS/T/VZ, rialzi ORCL/AMZN/BABA), ma nessuno è stato scorato.
- Nessun alert per l'arresto del consumatore. L'incidente `pipeline:signal_stale` (warning, aperto il 10-08 16:39) è rimasto aperto senza consegna: `mobile_notification_deliveries` vuota. Il Telegram del #161 (WDC −28,9%) alle 15:07 ha ricevuto 400.
- Il layer di esecuzione ha retto: 24/24 cicli portfolio (14:07–19:52), **0 ordini**, 0 trade aperti o chiusi. Tutti gli intent S4 (2.075) poggiano su segnali dal 10-05 al 10-08 e sono stati scartati per freschezza, fallback, gate, stale o pyramiding.
- La rilevazione di regime non è girata (coda inference). Il sizing ha usato in silenzio il `regime:current` del 10-08 13:30 (×0,7, TTL 72 h), senza warning.
- Il NAV paper è passato da 110.262,66 (prev close) a 110.635,67 (+373,01 $, +0,338%) contro SPY +0,60% e QQQ +0,49%. PnL realizzato 0. Il book detenuto all'open ha reso +215,61 $ fra open e close (S1 +98,06, S4 +117,55).
- Miss: BABA +5,36%, ORCL +4,59% e AMZN +3,29% erano NO_NEWS solo perché le news non sono state scorate (costo già registrato in F-096 dall'alpha-miss: 291,55 $).
- Ledger: 0 finding nuovi, 10 esistenti riconfermati (F-096, F-017, F-021, F-005, F-062, F-018, F-007, F-014, F-016, F-022).

## 2. Verdict finale

**Processo non affidabile** per la catena news→sentiment→segnale: per l'intera seduta il segnale non esiste. Le regole di esecuzione e di sicurezza hanno funzionato: nessun ordine da dati stale o fallback, riconciliazione OK, nessun ordine fuori orario. La seduta però non contiene evidenza di sentiment e va annotata come discontinuità nella serie osservata. La registrazione nel charter spetta all'operatore.

## 3. Timeline (UTC)

| Ora | Componente | Evento | Fonte |
|---|---|---|---|
| 00:00 | news queue | queue_depth 326 (eredità del 10-08), 301 stale | news_queue_census |
| 00:00–23:59 | beat | 17.280 `poll-telegram-updates`, 15 shadow, 32 sentiment-worker accodati su `inference`, **nessun consumatore** | beat log; assenza del log worker-inference |
| 03:00 | worker | daily performance report OK | worker log |
| 07:00 / 13:30 | beat | `regime-detector` e `regime-detector-premarket` accodati su `inference`, mai eseguiti | beat log, celery_app.py:136-150 |
| 13:30 | mobile_alert | `portfolio_cycle_late` critical (age 63.479 s), rientrato 14:08 (F-021) | mobile_events |
| 13:30 | snapshot | NAV 110.458,44, 41 posizioni, gross 34,4% | portfolio_monitor_snapshots |
| 14:07 | portfolio-cycle | primo ciclo; «S4: dropped 15/15 stale signals (age > 4h)»; FIX-D preserva 11 segnali stale su posizioni aperte; SKIP_PYRAMIDING PLTR/SAP (segnali 14701/14743 del 10-08) | worker log, execution_decisions |
| 14:12 → | reconcile-fills-intraday | `updated 0` a ogni giro | worker log |
| 14:20 | deploy reconcile | ef3e9848 → 4346fdab, solo doc/test, nessun rebuild (worker-inference non ricreato) | deploy_reconcile log |
| 15:07:08 | portfolio-cycle | #161 «9/41 unprotectable (qty < 1)»; WDC −28,9% → **Telegram 400** | worker log 4350-4353 |
| 14:07–19:52 | portfolio-cycle | 24/24 cicli; ogni ciclo `orders_count` 2 (BUY PLTR/SAP target) → 0 inviati (P0-05) | portfolio_cycles, worker log |
| 13:00–20:00 | news queue | 587 → 999 (+412 in RTH) | news_queue_census |
| 20:00 | snapshot | NAV 110.635,67 (+373,01), 41 posizioni | portfolio_monitor_snapshots |
| 20:07–21:52 | portfolio-cycle | «Market closed», skip (guard OK) | worker log |
| 21:00 | decay monitor | 6 DECAY CRITICAL (S1/S2/S4), solo log | worker log |
| 21:35 | reconcile-positions-eod | fully_held 41, anomalies 0 | worker log |
| 22:00 | forward-return-worker | updated 1.012 (segnali precedenti) | worker log |
| 22:30 | risk-monitor | n_alerts 0, exposure 0,345 | worker log, risk_reports 119 |
| 22:50 | held_news_loss_alert | NOK, WDC; `portfolio_cycle_session_grid` warning (open_gap 37,0 min) | mobile_events |
| 23:05 | worker | report giornaliero Telegram 200 | worker log |
| 23:59 | news queue | 1.008, oldest 34 h, 465 stale | news_queue_census |

## 4. News ingest

| Fonte | Righe news_log | fetched / queued / duplicates / no_ticker / stale | Note |
|---|---|---|---|
| alpaca_benzinga (REST + WS) | **0** | 1.098 / 667 / **6.487** / 0 / 0 | duplicates > fetched (F-007); accodate e mai consumate |
| gdelt_gkg | **0** | 2.002 / 15 / 3 / 1.984 / 0 | idem |
| worker-news-stream (log) | — | 391 righe «News stream:» | stesso titolo ripetuto più volte (consegne WS multiple); TMUS 77, T 78, VZ 88, AMZN 107, ORCL 25, PLTR 19, BABA 5 (da ALPHA_MISS §3) |

Copertura effective-timely 0/96, per interruzione del consumatore e non per scopertura dei provider. Le ultime righe `news_log` sono del 2026-10-08 16:15:23 e le prime successive del 2026-10-16 13:32:58. Non si possono verificare per questa seduta: duplicati cross-provider, ticker ambiguity, sanitizzazione, timestamp futuri. Il contenuto della coda non è persistito. Confidenza: alta sull'assenza; il contatore duplicates è inaffidabile (F-007).

## 5. Performance modelli LLM

| Modello | Richieste | Successi | Errori/timeout | Fallback FinBERT | Latenza |
|---|---|---|---|---|---|
| glm-5.3:cloud | 0 | 0 | — | — | — |
| gpt-oss:20b-cloud | 0 | 0 | — | — | — |
| FinBERT | — | — | — | 0 righe | — |

Nessuna chiamata LLM, perché il processo che le esegue era assente. La distribuzione polarity/confidence/score, il disaccordo e la dominanza non si possono calcolare. Lo stato di Ollama Cloud non è osservabile per il 10-09: il 10-08 aveva risposto 429 (quota) dalle 15:21. Verifica funzionale: gli LLM restano fuori dal trading loop (il ciclo portfolio ha girato senza di loro) e nessun output LLM è entrato nelle decisioni del giorno.

## 6. Segnali finali per ticker

Nessun segnale generato il 10-09. Le decisioni usano segnali precedenti:

| Ticker | Decisione (×cicli) | signal_id | signal_score medio | Nota |
|---|---|---|---|---|
| PLTR | SKIP_PYRAMIDING (persistito 1×, log 24×) | 14701 (10-08, +0,392) | — | già a libro |
| SAP | SKIP_PYRAMIDING (1×, log 24×) | 14743 (10-08, +0,354) | — | già a libro |
| C | SKIP_THRESHOLD ×24 | 14703 | 0,250 | preserve-stale (FIX-D) |
| MRVL / PFE | SKIP_THRESHOLD ×24 | 14636 / 14641 | 0,230 / 0,229 | preserve-stale |
| NOK / DELL | SKIP_THRESHOLD ×24 | 14382 / 14664 | 0,148 / 0,134 | preserve-stale |
| SHEL / TSM / PANW | SKIP_THRESHOLD ×24 | 14753 / 14747 / 14756 | 0,012 / 0,034 / 0,005 | preserve-stale |
| PBR | SKIP_THRESHOLD ×12 | 14030 | 0,255 | uscito dal preserve dopo le 17:07 |

Decisioni del giorno (`execution_decisions`, 2.281): OBSERVE_LATE_ENTRY 1.644, SHADOW_LATE_ENTRY 431, SKIP_THRESHOLD 204, SKIP_PYRAMIDING 2. Intent S4 (`s4_intent_events`, 2.075 candidati): SKIP_ENTRY_FRESHNESS 1.199, SKIP_FALLBACK 528, SKIP_ENTRY_GATE 204, SKIP_STALE 96, SKIP_PYRAMIDING 48. Copertura signal_id 206/206 (dossier). regime_mult 0,7 costante (regime del 10-08, vedi DAY-003). Circuit breaker: nessuno attivo.

## 7. Ordini

| Ora | Strategia | Ticker | Azione | Qty | Fill | Stato | Nota |
|---|---|---|---|---|---|---|---|
| — | — | — | — | — | — | — | **nessun ordine il 2026-10-09** |

/api/orders (100 ordini, 09-29 → 10-21): nessun ordine con submitted, filled o canceled il 10-09. `portfolio_cycles.orders_count` somma **48** su 24 cicli, ma nessuno è stato inviato (CombinedOrder BUY PLTR/SAP bloccati da P0-05, F-014). Broker: Alpaca paper (`broker_environment=paper`, `mode=paper` su tutti gli snapshot).

## 8. PnL / rendimento

| Voce | Valore |
|---|---|
| Realizzato S1 / S4 | 0,00 $ / 0,00 $ (nessuna chiusura) |
| NAV prev close → 20:00 | 110.262,66 → 110.635,67 = **+373,01 $ (+0,338%)** (include l'extended-hours prima dell'open: +195,78 alle 13:30) |
| Book detenuto, open→close (dossier `snapshot_apertura`) | +215,61 $ (S1 32 posizioni +98,06; S4 9 posizioni +117,55) |
| Migliori / peggiori | PLTR +60,37, PANW +55,78, SNOW +40,77, CSCO +29,99 / peggiore S1 −25,05, peggiore S4 −24,89 |
| Unrealized (snapshot) | 2.160,86 (10-08 20:00) → 2.532,65 (10-09 20:00) |
| Posizioni aperte il 10-09 | nessuna |
| Costi / slippage | 0 (nessun fill) |
| SPY / QQQ | +0,60% / +0,49% |

Il book (gross 34,4%) ha reso meno di SPY in termini relativi al NAV, coerente con l'esposizione parziale. Cash invariato (72.507,95).

## 9. Correttezza buy/sell

- BUY: nessuno. PLTR e SAP erano target BUY in ogni ciclo, ma bloccati correttamente da P0-05 (già a libro). Nessun ingresso su segnali di oltre 4 h (SKIP_ENTRY_FRESHNESS/SKIP_STALE): fail-safe corretto in assenza di dati freschi.
- SELL: nessuno. Il preserve-stale (FIX-D) ha tenuto 10-11 posizioni su segnali vecchi, senza nuove informazioni. ARM (S1, −3,27%) era EXIT_RISK con STALE_EXIT_SIGNAL (dossier). Comportamento documentato, ma il book è stato cieco lato uscita per tutta la seduta (NOK −11,6%, WDC −27,7% da ingresso; F-036/F-025, non riosservati qui come difetto nuovo).
- `exit_mechanism`: nessuna uscita il 10-09, quindi non c'è nessuna etichetta da interpretare.
- Nessun roundtrip, nessun BUY ripetuto, nessun ordine duplicato o fuori orario (20:07–21:52 skip «Market closed»), nessun ordine con score < 0,05.
- LLM non valido o assente: nessun trade. Circuit breaker: non attivo, non pertinente.
- Idempotenza: SKIP_PYRAMIDING persistito una volta per simbolo e giorno (2 righe), contro 48 intent: deduplica intenzionale.
- Reconciliation: 0 ordini, 0 trade; `reconcile-positions-eod` fully_held 41, anomalies 0; snapshot sempre a 41 posizioni. Coerente.

## 10. Anomalie

### [DAY-001] worker-inference assente per l'intera seduta: zero news scorate, coda a 1.008, nessun alert recapitato

* Tipo: Bug
* Area: Ops
* Evidenza:
  * file/log/tabella: assenza di `logs/containers/worker-inference-2026-10-09.log`; `beat-2026-10-09.log`; `news_queue_census`; `news_log`; `sentiment_signals`; `mobile_events`; `mobile_notification_deliveries`
  * timestamp: tutta la giornata; ultimo segnale 2026-10-08 16:15:23, primo successivo 2026-10-16 13:32:58
  * snippet/query: `SELECT count(*) FROM news_log WHERE created_at::date='2026-10-09'` → 0 (idem sentiment_signals, llm_responses, finbert_fallback_events); queue_depth 326 → 1.008, oldest_age 34 h; beat: 32 sentiment-worker, 15 sentiment-shadow-offsession, 17.280 poll-telegram-updates su `inference`
* Descrizione: è la continuazione del warm shutdown del 10-08 (F-096). Il deploy reconcile delle 14:20 («solo doc/test, nessun rebuild») non ricrea il container. L'unico incidente aperto è `pipeline:signal_stale` warning, senza canale di consegna.
* Impatto: seduta senza sentiment; 3 ENTRY_OPPORTUNITY perse (BABA, ORCL, AMZN) con titoli presenti nello stream. Costo già stimato nell'occorrenza ALPHA_MISS dello stesso giorno (291,55 $), qui non ricontato.
* Severità: Critical
* Confidenza: High
* Azione consigliata: ticket di correttezza: restart policy e watchdog del consumatore `inference` (F-096); registrare la discontinuità nel charter (operatore).
* Test/monitor consigliato: alert critical se in RTH queue_depth cresce e `sentiment_signals` resta a zero per più di 30 min; `celery inspect ping` della coda inference.

### [DAY-002] Task non-sentiment instradati sulla coda morta: poller Telegram e regime detector fermi in silenzio

* Tipo: Rischio
* Area: Ops
* Evidenza: celery_app.py:136-150 (regime su `inference`), :192-198 (poll-telegram-updates su `inference`); beat log: 17.280 poll e 2 regime accodati; worker log: nessuna riga `detect_regime`
* Descrizione: la caduta di un solo container disattiva tre funzioni indipendenti: scoring, flusso di approvazione Telegram e regime. Le code accumulano messaggi in Redis.
* Impatto: vedi DAY-003 per il regime; approvazioni Telegram non processate (nessuna pendente nota).
* Severità: Medium
* Confidenza: High
* Azione consigliata: registrare come parte di F-096 (nessuna taratura).
* Test/monitor consigliato: lunghezza della lista Redis `inference` come metrica.

### [DAY-003] Il sizing usa in silenzio il regime del giorno prima

* Tipo: Rischio
* Area: Risk
* Evidenza: `execution_decisions.regime_mult` = 0,7 su 2.281/2.281 righe; nessuna riga `P0-09` nel worker log del 10-09 (29 il 10-12, quando cade a ×0,2); `REGIME_REDIS_TTL_SECONDS` 259.200 (config.py:391); ultimo `detect_regime` riuscito il 10-08 13:30:43 (worker-inference log del 10-08)
* Descrizione: il regime non viene ricalcolato, ma la chiave da 72 h resta valida. Nessun log segnala che il valore è di ieri (F-017: fallimento silenzioso del regime).
* Impatto: nessun ordine il 10-09, quindi nessun costo. Sul 10-12 il fallback ×0,2 riduce il sizing.
* Severità: Low
* Confidenza: High
* Azione consigliata: registrare.
* Test/monitor consigliato: età di `regime:current` esposta nello snapshot; warning se supera 24 h.

### [DAY-004] Alert #161 WDC −28,9% rifiutato da Telegram (400)

* Tipo: Anomalia
* Area: Ops
* Evidenza: worker log righe 4351-4353, 15:07:08
* Descrizione: F-005. 9/41 posizioni non proteggibili (qty < 1), WDC a −28,9%; l'alert non è consegnato. `held_news_loss_alert` arriva alle 22:50, dopo il close.
* Impatto: nessun punto di decisione in RTH su WDC/NOK.
* Severità: Medium
* Confidenza: High
* Azione consigliata: correggere l'escape del messaggio (#591).
* Test/monitor consigliato: contatore sendMessage ≠ 200.

### [DAY-005] Stop non piazzabili su 9 posizioni frazionarie

* Tipo: Rischio
* Area: Risk
* Evidenza: worker log 15:07:08 «#161: 9/41 held positions are unprotectable (qty < 1): AMAT, AMD, ASML, CAT, DELL, LLY, NOK, SPY, WDC»
* Descrizione: F-022 (gli stop coprono solo la parte intera).
* Impatto: WDC −27,7% da ingresso senza stop.
* Severità: Low
* Confidenza: High
* Azione consigliata: registrare.
* Test/monitor consigliato: nozionale non protetto per giorno.

### [DAY-006] Decay CRITICAL senza canale; token Telegram nei log

* Tipo: Rischio
* Area: Ops
* Evidenza: worker log 21:00:00 (6 righe `DECAY CRITICAL`, IC −0,009, Sharpe −1,20); 3 righe con URL `api.telegram.org/bot<token>` nel worker log
* Descrizione: F-062, F-018. Oggi le righe con token sono poche solo perché il poller (worker-inference) non girava.
* Impatto: alert non recapitati; credenziale nei log.
* Severità: Medium
* Confidenza: High
* Azione consigliata: ruotare il token e alzare il livello del logger httpx.
* Test/monitor consigliato: grep CI per `bot[0-9]+:`.

### [DAY-007] Telemetria: orders_count 48 con 0 ordini inviati; duplicates > fetched; benchmark SPY

* Tipo: Anomalia
* Area: Data
* Evidenza: `portfolio_cycles` 10-09 sum(orders_count) 48, `/api/orders` 0 ordini; `ingestion_stats_daily` benzinga duplicates 6.487 contro fetched 1.098; 84 × «SPY benchmark fetch failed: subscription does not permit querying recent SIP data»
* Descrizione: F-014, F-007, F-016.
* Impatto: metriche operative non interpretabili senza incrocio.
* Severità: Low
* Confidenza: High
* Azione consigliata: registrare.
* Test/monitor consigliato: invariante duplicates ≤ fetched; orders_sent separato da orders_count.

### [DAY-008] Finestra beat UTC fissa: primo ciclo 37 min dopo l'open

* Tipo: Ambiguità
* Area: Ops
* Evidenza: `mobile_events` `portfolio_cycle_late` critical 13:30:01 → 14:08:00; `portfolio_cycle_session_grid` open_gap 37,01 min, close_gap 7,99 min
* Descrizione: F-021.
* Impatto: nessuno oggi (nessun segnale fresco).
* Severità: Low
* Confidenza: High
* Azione consigliata: registrare.
* Test/monitor consigliato: già presente (session_grid).

## 11. Aree corrette

- Nessun ingresso su segnali stale o fallback, nonostante 528 intent su segnali FinBERT del 10-08 e 1.199 oltre la finestra di freschezza.
- P0-05 anti-pyramiding attivo e persistito senza duplicati giornalieri.
- Guard «Market closed» su tutti i cicli 20:07–21:52 e sull'ingest fuori orario.
- Riconciliazione EOD: 41 fully_held, 0 anomalie; snapshot coerenti; paper coerente.
- Copertura signal_id 206/206 sulle decisioni con segnale.
- Nessun segnale senza news, nessun timestamp futuro (non ci sono righe).

## 12. Dati mancanti

- Log di worker-inference (inesistente) e causa del mancato riavvio: eventi Docker non persistiti.
- Contenuto della coda news (1.008 elementi): non persistito, quindi non è possibile ricostruire quali articoli avrebbero superato il gate.
- Stato di Ollama Cloud il 10-09: nessuna chiamata, quindi non osservabile (F-086).
- PnL non realizzato per ticker fuori dal dossier; slippage non pertinente (0 fill).

## 13. Raccomandazioni immediate

1. Watchdog e restart automatico di worker-inference (F-096), con alert critical recapitato (fuori host, F-094).
2. Annotare nel charter la discontinuità 2026-10-08 16:20Z → 2026-10-16 13:32Z (operatore).
3. Ruotare il token Telegram (F-018).
4. Nessuna taratura: tutte le proposte sono di strumentazione e correttezza.

## 14. Test / monitor da aggiungere

- Consumatore `inference` vivo: ping più profondità della lista Redis.
- RTH con zero `sentiment_signals` per più di 30 min → critical con consegna.
- Età di `regime:current` nello snapshot.
- Invariante duplicates ≤ fetched; orders_sent ≠ orders_count.

## 15. Ticket suggeriti

- Correttezza/Ops: restart policy, watchdog e alert per worker-inference (F-096); separare poller Telegram e regime dalla coda di inferenza (decisione di architettura, operatore).
- Correttezza: età del regime osservabile (F-017).
- Ops: canale per DECAY CRITICAL (F-062); redazione dei log (F-018).

## 16. Stato sistema

- Ollama: **non chiamato** per tutta la giornata (consumatore assente); downtime LLM effettivo 24 h, 6h30m in RTH su 6h30m.
- FinBERT fallback: 0 eventi (0 segnali); fallback rate non definito (nessuna decisione su segnali del giorno).
- Worker restart: nessun restart di worker-inference (assente tutto il giorno); worker principale stabile, nessun SoftTimeLimit. Deploy reconcile 14:20 senza rebuild.
- Telegram: 1 sendMessage 400 (15:07), 1 200 (23:05).
