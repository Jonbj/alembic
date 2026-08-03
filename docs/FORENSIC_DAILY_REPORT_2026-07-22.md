# Forensic Daily Report — 2026-07-22

Analista: Claude (sessione autonoma read-only) · Generato: 2026-07-23
Timezone operativo: **UTC** (`celery_app.py`: `timezone="UTC"`, `enable_utc=True` — non ambiguo).
Fonti: PostgreSQL `trading` (query dirette, API REST inaccessibile — vedi §12), log Docker `worker`/`worker-inference` (finestra disponibile: dal restart container 2026-07-22 12:13:54 UTC in poi — copre l'intera giornata di mercato).

---

## 1. Executive Summary

Giornata a bassissima attività: 195 news ingerite (2 fonti), 196 sentiment signal generati, ma solo **5 decisioni execution non-SKIP** (2 BUY, 3 SELL) su 283 valutazioni totali — il resto è `SKIP_THRESHOLD`. Nessun ordine live: S1=`supervised_paper`, S4=`paper`, engine=`portfolio` (confermato). Ollama praticamente sempre disponibile (1 solo timeout su ~24 cicli sentiment). Il fix del bug #59 (BUY su fallback/desync, PR #114) risulta deployato stamattina (~07:53 UTC merge, worker restart 12:13:54 UTC) e **nessuna nuova occorrenza oggi**. Tre problemi reali: (1) il kill-switch operatore ("test") ha bloccato 8 cicli portfolio (14:07–15:52 UTC) cancellando ripetutamente gli ordini pendenti — conferma memoria nota; (2) `mobile_alert_task` ha fallito **100% delle esecuzioni (480/480)** per tutta la giornata per un bug strutturale (dipendenza Redis mai inizializzata nel processo worker); (3) la posizione WDC aperta il 07-21 con sentiment −0.385 (bug #59, pre-fix) è rimasta **orfana**: due ordini SELL sottomessi (07-21 e 07-22) mai riconciliati, trade tuttora aperto in DB, guardia pyramiding ora blocca correttamente i re-entry ma la posizione economica reale è incerta senza accesso al broker. Nessuna anomalia trovata su: SELL con sentiment positivo, roundtrip <30min, ordini duplicati/stesso minuto, news con timestamp futuri, trade fuori orario.

**Verdict: OK con warning.**

---

## 2. Verdict Finale

**OK con warning** — la pipeline end-to-end (news→sentiment→segnale→decisione→ordine→fill parziale) ha funzionato correttamente nella stragrande maggioranza dei casi, i guardrail (pyramiding guard, cancel-before-sell, paper/live separation, risk constraints) hanno operato come previsto, e un bug noto (#59) risulta effettivamente fixato in produzione. Il downgrade da "OK" a "OK con warning" è dovuto a: un failure rate del 100% su un intero worker task (mobile alert) passato inosservato per tutta la giornata, una posizione orfana non riconciliata, e il kill-switch operatore che ha sottratto ~2h di finestra di trading. Nessuno di questi ha causato perdite anomale o ordini scorretti verso il broker in violazione dei constraint di rischio.

---

## 3. Timeline 2026-07-22 (UTC)

| Ora UTC | Componente | Evento |
|---|---|---|
| ~07:40 (da memoria, non nei log disponibili) | Operatore | `system:halted_by_operator` attivato, motivo "test", no TTL (da memoria sessione precedente) |
| 09:53:27 | Git/Deploy | Merge PR #114 "fix(s4): block BUYs on fallback signals + fix signal_id↔score desync" |
| 12:13:54 | Docker | Restart `alembic-worker-1` (verosimilmente deploy PR #114) — inizio finestra log disponibile |
| 14:00:00 | `loss-feedback-check` | Trigger S1: EWMA R −0.54, 10 consecutive losses, rolling P&L −$169.43 → threshold 0.30→0.00, regime_scale 0.41→0.33 |
| 14:00:00 | `loss-feedback-check` | Trigger S4: EWMA R −0.34, 5 consecutive losses, rolling P&L +$121.05 → threshold 0.40→0.45, regime_scale 0.64→0.51 |
| 14:00:00–19:48 | `sentiment-worker` | ~24 cicli, 195 news processate, 196 sentiment_signals scritti |
| 14:01–19:49 | `run-news-ingestion` / `run-alpaca-ingestion` | Ingest continuo gdelt_gkg (101) + alpaca_benzinga (94) |
| **14:07–15:52** | `portfolio-cycle` | **8 cicli consecutivi saltati** — "Portfolio cycle skipped — kill-switch active: test" + "EMERGENCY: cancelled all pending Alpaca orders" ad ogni ciclo |
| 16:07:00 | `execution_decisions` #3532 | BUY GE (S1 momentum, score 0.0127, peso 1.3%) — primo ciclo portfolio non bloccato |
| 16:22:01 | `execution_decisions` #3552 | SELL WDC (S1 momentum, peso 0.7%) — ordine `87132adc…` |
| 16:22:01 | `execution_decisions` #3553 | SELL BA (`[expired] S4 signal expired age=22.1h>4h`) — chiude trade #375, net +$12.50 |
| 16:22:10 | log worker | "Cancelled 1 protective stop(s) for WDC before SELL" (cancel-before-sell funziona) |
| 19:03:13 | worker-inference | Timeout Ollama (90s) per glm-5.2 e gpt-oss su ticker DB → fallback FinBERT (unico caso del giorno) |
| 19:07:10 / 19:22:08 | worker | "P0-05 pyramiding guard: skipping BUY for WDC — open trade exists in DB" (2 volte) |
| 19:22:00 | `execution_decisions` #3788 | SELL GE ("s1_weight_drop", peso 0%) — chiude trade #403, net −$9.25 |
| 19:37:00 | `execution_decisions` #3789 | BUY GE (S1 momentum, score 0.01272, peso 1.3%) — riapertura 15 min dopo la SELL |
| 19:37:06 | worker | "S4: no signals in DB for last 96 hours" — singolo ciclo, isolato |
| 14:00–21:59 | `mobile-alert-evaluation` | **480/480 esecuzioni fallite** — `HTTPException(503, 'Cache unavailable')` |
| 22:30:00 | `risk-monitor` | risk_reports#40: NAV $109,973.29, daily_pnl +$177.86, drawdown 0.093765 (identico a ieri), herfindahl 1.0 |

---

## 4. Tabella News Ingest

| Fonte | Count | Prima news | Ultima news | Discarded | Extraction method |
|---|---|---|---|---|---|
| gdelt_gkg | 101 | 14:45:21 | 19:48:22 | 0 | org_lookup |
| alpaca_benzinga | 94 | 14:01:34 | 19:46:52 | 0 | source_metadata |
| **Totale** | **195** | 14:01:34 | 19:48:22 | 0 | — |

- Duplicati cross-provider su `(url, ticker)`: **0**.
- Righe con `content_hash` ripetuto: 35 gruppi, ma **sempre con ticker diversi** nello stesso gruppo (es. `b0b622…` → AMD,DELL,GOOGL,IBM,IWM,QQQ,RDDT,TSLA,XLE) — è estrazione multi-entity legittima (un articolo, più ticker), **non duplicazione** dello stesso segnale sullo stesso ticker.
- News con `published_at > fetched_at` (timestamp futuro): 0.
- News stale (`fetched_at - published_at > 48h`): 0.
- `published_at` NULL: 0. `body_snippet`/`raw_sentiment` NULL: 0.
- News fuori market hours (prima 13:30 o dopo 20:00 UTC): 0 — ma vedi [DAY-006] sul gap 13:30–14:00.

**Top ticker per volume news:** MS(25), GS(20), MU(9), GOOGL(8), TSM(8), NVDA(6), SPCX(5), TSLA(5), AMD(5), TXN(5), DB(5), DIS(5).

**Top news per impatto sul segnale (|score sentiment| più alto):** AMD 0.545 (17:30, ensemble conf 0.75), TSM 0.5125 (14:30, conf 0.625), NVDA 0.4875 (14:32, singolo modello gpt-oss), ORCL −0.4375 (16:32, conf 0.675).

**Confidenza analisi: High** (dati completi, nessun NULL, query dirette su tabella sorgente).

---

## 5. Tabella Performance Modelli LLM

| model_id | Risposte | Ineligible (conf&lt;0.4) | Avg polarity | Avg confidence | Min/Max polarity |
|---|---|---|---|---|---|
| glm-5.2:cloud | 195 | 157 (80.5%) | 0.038 | 0.254 | −0.7 / 0.75 |
| gpt-oss:20b-cloud | 195 | 96 (49.2%) | 0.038 | 0.396 | −0.6 / 1.0 |

**Composizione ensemble finale (`sentiment_signals.model_id`), 196 righe:**

| model_id (contributori) | Count | % | Avg score | Avg confidence |
|---|---|---|---|---|
| ensemble:glm-5.2+gpt-oss (entrambi eleggibili) | 116 | 59.2% | 0.030 | 0.301 |
| ensemble:gpt-oss:20b-cloud (solo) | 70 | 35.7% | 0.023 | 0.498 |
| ensemble:glm-5.2:cloud (solo) | 9 | 4.6% | 0.086 | 0.578 |
| finbert (hard fallback) | 1 | 0.5% | 0.023 | 0.204 |

- **Timeout Ollama hard**: 1 evento (19:03:13, ticker DB, entrambi i modelli 90s timeout).
- **Refusal/invalid JSON**: nessuna evidenza nei log (nessun errore di parsing).
- **Disagreement massimo** (ensemble_std): AXP 0.283, GM 0.247, TSLA 0.247 (×2), DB 0.247 — tutti sotto la soglia di divergenza (0.30 costruttore / 0.40 live worker), quindi mai scartati per divergenza pura oggi.
- **Score estremi**: AMD +0.545, TSM +0.5125, ORCL −0.4375, NOW −0.42 — tutti con confidence ≥0.6 e generati da ensemble reale (no dominanza di un solo modello sui casi più estremi, tranne NVDA 0.4875 e MS/NOW/GS/TSM singoli in top-15).

**Verifica funzionale:**
- Output LLM validato prima del signal store: **sì**, `eligible = confidence >= min_confidence(0.4)`, scritto per audit anche quando ineligible (`pg_store.py:1748`).
- Gestione varianza alta: **sì**, `ensemble_std >= divergence_threshold` → fallback; oggi mai raggiunta.
- News duplicate pesano più volte: solo nel senso legittimo multi-ticker (§4); nessuna doppia pesatura sullo stesso ticker.
- Stessa news → segnali multipli sullo stesso ticker: non osservato.
- Confidence bassa riduce il peso: sì, `score = polarity × confidence` per costruzione, e i modelli con confidence bassa vengono marcati `eligible=false` ed esclusi dal calcolo pesato.
- Chiamata offline/background: confermato, `worker-inference` (queue `inference`, concorrenza 1), mai nel loop di esecuzione.
- Rischio hallucination diretta in trading: mitigato da min_confidence + divergence check + FinBERT fallback; nessun caso oggi di score estremo con confidence bassa che abbia generato un ordine.

**Confidenza analisi: High.**

---

## 6. Tabella Segnali Finali per Ticker (top 15 per volume)

| Symbol | N | Avg score | Min | Max | Avg confidence | Avg ensemble_std |
|---|---|---|---|---|---|---|
| MS | 25 | 0.030 | −0.08 | 0.42 | 0.321 | 0.011 |
| GS | 20 | 0.033 | −0.12 | 0.42 | 0.369 | 0.007 |
| MU | 9 | −0.016 | −0.12 | 0.04 | 0.281 | 0.024 |
| TSM | 8 | 0.096 | −0.24 | 0.5125 | 0.409 | 0.075 |
| GOOGL | 8 | −0.010 | −0.10 | 0.04 | 0.384 | 0 |
| NVDA | 6 | 0.170 | 0 | 0.4875 | 0.412 | 0.024 |
| SPCX | 5 | −0.026 | −0.08 | 0 | 0.320 | 0 |
| TSLA | 5 | 0.015 | −0.015 | 0.06 | 0.470 | 0.099 |
| TXN | 5 | −0.026 | −0.15 | 0.04 | 0.325 | 0.021 |
| DB | 5 | −0.136 | −0.2975 | 0.023 | 0.426 | 0.078 |
| AMD | 5 | 0.201 | −0.0075 | 0.545 | 0.395 | 0.057 |

Nessuno di questi segnali sentiment ha generato direttamente un ordine oggi (tutte le BUY/SELL execution_decisions con `signal_id` NULL derivano da S1 momentum o da scadenza segnale S4, non da un match diretto sentiment→ordine — vedi §7).

---

## 7. Tabella Ordini Generati/Eseguiti

`execution_decisions` 2026-07-22: **283 totali** → 278 `SKIP_THRESHOLD`, 3 SELL, 2 BUY. `constraints_fired: []` su tutti i 16 `portfolio_cycles` registrati (nessun cap/circuit-breaker automatico attivato oggi, oltre al kill-switch manuale).

| Tick time | Strategia | Symbol | Azione | Order ID | Rationale | Trade collegato | Esito |
|---|---|---|---|---|---|---|---|
| 16:07:00 | S1 | GE | BUY | 4449339d… | momentum, peso 1.3%, score 0.0127 | #403 entry $344.52, qty 2.296 | aperto poi chiuso stesso giorno |
| 16:22:01 | S1 | WDC | SELL | 87132adc… | momentum, peso 0.7% | #373 (entry 07-21, S4) | **mai riconciliato** — vedi [DAY-002] |
| 16:22:01 | S4 | BA | SELL | c1cc8e29… | `[expired]` segnale S4 scaduto (22.1h>4h) | #375 | fill $207.06, net **+$12.50** |
| 19:22:00 | S1 | GE | SELL | cd644fd0… | `s1_weight_drop`, peso 0% | #403 | fill $340.68, net **−$9.25** |
| 19:37:00 | S1 | GE | BUY | 464a4a31… | momentum, peso 1.3%, score 0.01272 | #404 entry $341.70, qty 2.305 | **ancora aperto** a fine giornata |

Tutti gli order_id sono univoci (nessun duplicato/race sullo stesso minuto). Nessun ordine generato senza `decision` corrispondente. Paper/live: confermato paper per entrambe le strategie (`strategy_lifecycle`: S1=`supervised_paper`, S4=`paper`; `config/trading.yaml` → `execution.engine: portfolio`).

**Confidenza analisi: High** su decisioni/trade nel DB; **Medium** sullo stato reale a mercato di WDC (API/broker non verificabile oggi, vedi §12).

---

## 8. Tabella PnL / Rendimento

| Metrica | Valore | Fonte |
|---|---|---|
| PnL realizzato (trade chiusi il 07-22) | **+$3.25 netto** (lordo $4.35, costi $1.10) | `trades` (2 chiusure: BA +$12.50, GE −$9.25) |
| PnL mark-to-market giornaliero (book intero, 44 posizioni) | **+$177.86** | `risk_reports#40` (NAV 109,846.90 → 109,973.29) |
| PnL non realizzato per singolo ticker | **non calcolabile** | nessuna tabella prezzi/posizioni accessibile senza broker (API 403) |
| PnL per strategia (S1 vs S4) isolato oggi | S1: −$9.25 realizzato (GE); S4: +$12.50 realizzato (BA) | `trades.stop_strategy` |
| Slippage stimato | BA $0.67, GE(#403) $0.43 (= `cost_usd`≈`slippage_est`) | `trades.slippage_est` |
| Costi/commissioni | $1.10 totali sui 2 trade chiusi | `trades.cost_usd` |
| Sharpe portfolio (rolling, da risk_reports) | −4.89 | `risk_reports#40` |
| combined_drawdown | 0.093765 (identico a ieri, 15 decimali) | `risk_reports#40` vs `#39` — **vedi [DAY-007]** |

**Nota importante:** il PnL realizzato da `trades` ($3.25) e il PnL mark-to-market del book ($177.86) misurano cose diverse — il secondo include la rivalutazione delle 44 posizioni aperte (non solo i 2 trade chiusi oggi) e **non va confuso con "rendimento della strategia"**. Non esiste una tabella `positions` in Postgres con prezzo corrente per ricostruire il PnL non realizzato per singolo ticker — servirebbe l'endpoint `/api/positions` (oggi inaccessibile, JWT scaduto) o l'API Alpaca diretta.

---

## 9. Analisi Correttezza Buy/Sell

| Check | Esito |
|---|---|
| BUY solo se consentito | ✅ nessuna BUY su fallback FinBERT oggi (fix PR #114 attivo) |
| SELL/exit corretti | ✅ BA per scadenza segnale S4 (22.1h>4h, corretto), GE per weight-drop S1 |
| Stop-loss rispettati | ✅ "Cancelled 1 protective stop(s) for WDC before SELL" — cancel-before-sell funziona (PR #69) |
| Signal flip rispettato | ✅ nessun flip BUY/SELL contraddittorio sullo stesso ciclo |
| Max holding / signal expiry | ✅ BA chiuso correttamente a 22.1h > max_age 4h |
| Rebalance band | ⚠️ GE ha oscillato BUY→SELL→BUY con score S1 quasi identico (0.012717 vs 0.012717) — vedi [DAY-004] |
| Ordini duplicati | ✅ nessuno (order_id sempre univoci) |
| Ordini contrari ravvicinati senza rationale | ⚠️ GE SELL 19:22 → BUY 19:37 (15 min) — rationale presente ma segnale sottostante invariato, vedi [DAY-004] |
| Ticker non consentiti | ✅ nessuno |
| Ordini fuori orario | ✅ tutti 16:07–19:37 UTC, dentro la finestra operativa |
| Trade su dati stale | ✅ guardia attiva (`S1 compute_signal: dropped... stale-tailed`, AZN/SPCX scartati 16 volte) |
| Trade su LLM output non valido | ✅ nessuno (eligible/ineligible correttamente separati) |
| Circuit breaker attivo → blocco trade | ✅ kill-switch operatore ha bloccato correttamente 8 cicli (14:07–15:52) |
| Strategia disabilitata → blocco | N/A (S1/S2 disabled a parte, non toccata oggi; S2 già `disabled`) |
| Paper/live coerente | ✅ confermato |
| Idempotenza retry Celery | ⚠️ **da verificare**: WDC ha 2 SELL order_id distinti registrati come tentativi di chiusura della stessa trade (#373) senza mai riuscire — vedi [DAY-002] |
| Reconciliation ordini↔fill↔posizioni | ❌ **fallita per WDC #373** — vedi [DAY-002] |

---

## 10. Anomalie Trovate

### [DAY-001] Kill-switch operatore blocca 8 cicli portfolio e cancella ordini pendenti ripetutamente

- Tipo: Anomalia (operativa, non software)
- Area: Ops / Risk
- Evidenza:
  - file/log/tabella: log `worker`, righe 14:07:00–15:52:00
  - timestamp: 2026-07-22 14:07:00 → 15:52:00 UTC
  - snippet: `"Portfolio cycle skipped — kill-switch active: test"` + `"EMERGENCY: cancelled all pending Alpaca orders (kill-switch active)"` ripetuto 8 volte (ogni ciclo da 14:07 a 15:52)
- Descrizione: il flag operatore `system:halted_by_operator` (motivo "test", nessun TTL, secondo memoria di sessione precedente attivato alle 07:40) è rimasto attivo fino a un momento tra 15:52 e 16:07 UTC, bloccando 8 cicli di portfolio (2h) e facendo cancellare ad ogni ciclo TUTTI gli ordini pendenti su Alpaca, inclusi eventuali stop protettivi.
- Impatto: nessun ordine generato per 2h di mercato; se esistevano stop-loss pendenti su posizioni aperte, sono stati cancellati ripetutamente senza essere ripristinati fino alla riattivazione — book scoperto da protezione per la durata dell'halt.
- Severità: High
- Confidenza: High (log diretti + coerente con memoria operativa)
- Azione consigliata: aggiungere TTL obbligatorio al kill-switch manuale + alert immediato (non silenzioso) quando è attivo durante market hours; verificare se gli stop protettivi vengono ripristinati automaticamente alla riattivazione.
- Test/monitor consigliato: monitor che alerti se `system:halted_by_operator` resta attivo > N minuti durante market hours; test che verifichi il repristino degli stop dopo un halt.

### [DAY-002] Trade WDC #373 orfano: 2 ordini SELL sottomessi, mai riconciliati, posizione bloccata in stato ambiguo

- Tipo: Bug
- Area: Orders / Broker / Data
- Evidenza:
  - file/log/tabella: `trades` id=373, `execution_decisions` id=3484 (07-21) e 3552 (07-22)
  - timestamp: entry 2026-07-21 16:37:01; SELL#1 2026-07-21 18:22:00 (order `bf7fe4b8…`); SELL#2 2026-07-22 16:22:01 (order `87132adc…`)
  - snippet: `trades.exit_order_ids = {bf7fe4b8-...,87132adc-...}` ma `exit_price`, `exit_time`, `exit_reason` tutti NULL; log 07-22 19:07:10/19:22:08: `"P0-05 pyramiding guard: skipping BUY for WDC — open trade exists in DB"`
- Descrizione: la trade #373 (entrata 07-21 su sentiment −0.385, bug #59 pre-fix) ha ricevuto due tentativi di SELL in due giorni diversi, entrambi registrati nell'array `exit_order_ids`, ma nessuno dei due ha mai popolato i campi di chiusura. Il sistema oggi considera correttamente (in modo difensivo) la posizione ancora aperta e blocca i tentativi di ri-BUY di S1, ma non è verificabile se il secondo SELL sia stato effettivamente evaso dal broker (API inaccessibile, vedi §12).
- Impatto: possibile posizione fantasma nel DB (se il broker ha effettivamente chiuso la posizione, il sistema continua a "vederla" aperta indefinitamente, bloccando ogni futuro segnale S1/S4 legittimo su WDC) oppure — scenario peggiore — due ordini SELL realmente inviati sullo stesso lotto (rischio di vendita allo scoperto non intenzionale se entrambi fossero stati eseguiti).
- Severità: High
- Confidenza: Medium (evidenza DB solida, ma manca verifica lato broker)
- Azione consigliata: query diretta allo stato ordine Alpaca per `bf7fe4b8-0cb3-491b-8b6b-6a6d40746a0b` e `87132adc-c968-48ab-b1df-3547b384c340`; eseguire manualmente `reconcile_fills` mirato su WDC; se la posizione è realmente chiusa, correggere manualmente `trades.exit_*` per sbloccare la guardia pyramiding.
- Test/monitor consigliato: alert automatico su trade con `exit_order_ids` non vuoto ma `exit_time IS NULL` da più di N ore.

### [DAY-003] `mobile_alert_task.run_mobile_alert_evaluation`: 100% failure rate (480/480) per l'intera giornata

- Tipo: Bug
- Area: Ops / Frontend (mobile monitoring)
- Evidenza:
  - file/log/tabella: log `worker`, `src/api/deps.py:30`, `src/mobile_monitoring/builder.py:93`
  - timestamp: 2026-07-22 14:00:00 → 21:59:00 (ogni minuto, 480 esecuzioni, 0 successi)
  - snippet: `HTTPException(status_code=503, detail='Cache unavailable')`; `builder.py:93: self.redis = redis or get_redis_store()`; `deps.py:25-30: get_redis_store() raise HTTPException(503) if _redis_client is None`
- Descrizione: `MobileSnapshotBuilder` chiama di default `get_redis_store()` da `src.api.deps`, una dependency FastAPI il cui client Redis viene inizializzato solo dal lifespan-startup del processo **API**. Il task Celery gira nel processo **worker**, dove `init_redis()` non viene mai chiamato → `_redis_client` è sempre `None` → ogni invocazione fallisce, sempre, strutturalmente (non è un outage Redis transitorio: il container Redis è sano e usato con successo da tutto il resto della pipeline).
- Impatto: **zero incident detection / notifiche push mobile per l'intera giornata di mercato** (e verosimilmente per ogni giorno da quando questo task esiste, essendo un bug strutturale non un evento).
- Severità: Critical (per il dominio "mobile monitoring"; nessun impatto sul trading core)
- Confidenza: High (root cause identificata nel codice, 480/480 falliti, 0 successi)
- Azione consigliata: passare esplicitamente un client Redis dedicato al worker a `MobileSnapshotBuilder(redis=...)` invece di affidarsi al default che dipende dal lifespan FastAPI; aggiungere un test che esegua il task in un contesto Celery puro (senza app FastAPI) per intercettare la regressione.
- Test/monitor consigliato: alert su tasso di successo `run_mobile_alert_evaluation` < 100% su finestra 1h; test di integrazione che invoca il task senza bootstrap FastAPI.

### [DAY-004] GE whipsaw: BUY→SELL→BUY in 3.5h con score S1 sostanzialmente invariato

- Tipo: Anomalia
- Area: Signal / Orders
- Evidenza:
  - file/log/tabella: `execution_decisions` 3532/3788/3789, `trades` 403/404
  - timestamp: BUY 16:07:00 (score 0.0127168…) → SELL 19:22:00 (`s1_weight_drop`, peso 0%) → BUY 19:37:00 (score 0.0127173…)
  - snippet: `reason: "S1 momentum: time-series momentum signal, portfolio weight 1.3%."` (identico su entrambe le BUY)
- Descrizione: il peso target di S1 per GE è passato da positivo a 0% e di nuovo a un valore quasi identico in 3 cicli, con lo score sottostante praticamente invariato (differenza in sesta cifra decimale) — sintomo tipico di un ranking/cutoff relativo dove GE oscilla appena sopra/sotto la soglia per effetto di piccoli movimenti di *altri* ticker nel ranking, non di un cambio di segnale reale su GE.
- Impatto: 2 costi di transazione evitabili (~$0.43 + ~$0.41 in `cost_usd`) e una perdita realizzata di −$9.25 su un ciclo di round-trip senza reale variazione di segnale.
- Severità: Medium
- Confidenza: Medium (pattern coerente ma non ho accesso al ranking completo degli altri ticker per confermare la causa esatta)
- Azione consigliata: introdurre una banda di isteresi (rebalance band) sul ranking S1 in prossimità della soglia di ingresso/uscita per evitare whipsaw su variazioni marginali.
- Test/monitor consigliato: monitor su trade re-aperti entro N minuti dalla chiusura sullo stesso ticker/strategia con score quasi identico.

### [DAY-005] Loss-feedback ratchet: doppia riduzione regime_scale S1 sulla stessa evidenza stale

- Tipo: Rischio
- Area: Risk
- Evidenza:
  - file/log/tabella: log `worker`, `loss-feedback-check`
  - timestamp: 14:00:00 e 18:30:00
  - snippet: entrambe le righe riportano **identici** `EWMA R -0.54, 10 consecutive losses, rolling P&L $-169.43`; la prima riduce `regime_scale 0.41→0.33`, la seconda (4.5h dopo, oltre il cooldown di 4h dichiarato in `celery_app.py`) riduce ulteriormente `0.33→0.26` senza alcuna nuova perdita realizzata nel frattempo (nessuna trade S1 chiusa tra 14:00 e 18:30 tranne GE alle 19:22, dopo il secondo trigger).
- Descrizione: il meccanismo di loss-feedback sembra ri-applicare una penalizzazione basata sulle stesse statistiche stale non appena scade il cooldown interno di 4h, invece di richiedere nuova evidenza di perdita per un secondo taglio.
- Impatto: de-risking cumulativo (0.41→0.33→0.26, −37% circa) di S1 basato su un solo episodio di perdita, non su un peggioramento reale — coerente con il pattern "ratchet" già osservato in memoria storica del progetto.
- Severità: Medium
- Confidenza: Medium (comportamento osservato, non ho letto il codice esatto di `run_loss_feedback_check` per confermare se la stessa finestra statistica viene riletta senza refresh)
- Azione consigliata: verificare in `src/workers/performance.py` se `run_loss_feedback_check` richiede evidenza fresca (nuove trade chiuse) prima di un secondo taglio, o se basta la scadenza del cooldown sullo stesso stato.
- Test/monitor consigliato: test che verifichi che un secondo trigger di loss-feedback nella stessa "loss episode" (nessuna nuova trade chiusa) non causi un'ulteriore riduzione di regime_scale.

### [DAY-006] Schedule crontab non DST-aware: primi 30 min di mercato (13:30–14:00 UTC) sistematicamente esclusi

- Tipo: Ambiguità / Rischio strutturale
- Area: Data / Ops
- Evidenza:
  - file/log/tabella: `src/workers/celery_app.py:68-70,131-137,190-196`; `news_log` min(fetched_at)=14:01:34/14:45:21
  - timestamp: ogni giorno, 13:30–14:00 UTC (oggi confermato: prima news alle 14:01:34, primo ciclo sentiment alle 14:00:00)
  - snippet: `crontab(minute="*/15", hour="14-21", day_of_week="1-5")`, commento `"14:00-21:00 UTC = 9am-4pm ET"` — errato: in EDT (luglio, UTC-4) il mercato apre alle 13:30 UTC, non 14:00.
- Descrizione: lo schedule Celery è fisso in UTC e non si adatta al passaggio EST/EDT. Durante l'orario legale estivo (come oggi), news ingestion, sentiment worker e portfolio-cycle partono 30 minuti dopo l'apertura reale del mercato, perdendo sistematicamente la finestra più volatile/ricca di notizie post-apertura.
- Impatto: possibile perdita sistematica di segnale nei primi 30 minuti di ogni sessione, tutto l'anno durante EDT (circa metà dell'anno).
- Severità: Medium
- Confidenza: High (verificabile nel codice, comportamento confermato dai dati di oggi)
- Azione consigliata: rendere lo schedule DST-aware (calcolare l'offset ET dinamicamente) o quantomeno anticipare lo start a 13:30 UTC tutto l'anno (costo: 30 min extra di idle in inverno) e correggere il commento fuorviante nel codice.
- Test/monitor consigliato: test che verifichi la prima esecuzione giornaliera rispetto all'apertura NYSE reale (calendario mercato), non rispetto a un'ora UTC fissa.

### [DAY-007] `combined_drawdown` e `herfindahl_index` — bug preesistenti, ancora non fixati, valore sospetto stale oggi

- Tipo: Bug (già noto — GitHub issue #75 aperta)
- Area: PnL / Risk
- Evidenza:
  - file/log/tabella: `risk_reports` id=39 (07-21) e id=40 (07-22)
  - timestamp: 2026-07-21 22:30:00 e 2026-07-22 22:30:00
  - snippet: `combined_drawdown = 0.09376477905550713` identico a 15 cifre decimali su due giorni consecutivi; `herfindahl_index = 1.000000` costante su almeno 3 giorni (07-20, 07-21, 07-22)
- Descrizione: già segnalato in issue #75 (aperta, "Minor bugs from forensic 07-15"). La riproduzione odierna con valore `combined_drawdown` identico all'ultima cifra tra due giorni diversi rafforza il sospetto che il valore non venga ricalcolato quotidianamente ma "trascinato" da uno stato non aggiornato.
- Impatto: dashboard di rischio fuorviante (drawdown reale del book è verosimilmente diverso; herfindahl=1.0 implicherebbe concentrazione totale, incompatibile con 44 posizioni aperte).
- Severità: Medium
- Confidenza: High (dato ripetuto su più giorni, issue già tracciata)
- Azione consigliata: nessuna nuova — sollecitare il fix di #75 già aperta.
- Test/monitor consigliato: come da #75.

### [DAY-008] `S4: no signals in DB for last 96 hours` — blip isolato in un singolo ciclo

- Tipo: Anomalia
- Area: Signal
- Evidenza:
  - file/log/tabella: log `worker`, `src/workers/portfolio_scheduler.py:3081-3085`
  - timestamp: 2026-07-22 19:37:06
  - snippet: `"S4: no signals in DB for last %d hours — strategy will produce no orders"`
- Descrizione: un singolo ciclo (19:37) ha ricevuto 0 righe dalla query dei segnali S4, nonostante `sentiment_signals` contenesse righe generate poco prima (19:22, 19:03) e poco dopo (19:48). Il ciclo precedente e successivo hanno caricato segnali regolarmente — non è un pattern ripetuto.
- Impatto: S4 non ha valutato nuove entry per un ciclo (basso impatto, evento isolato).
- Severità: Low
- Confidenza: Medium (evento singolo, non riproducibile dai soli log)
- Azione consigliata: nessuna azione immediata; monitorare se si ripete.
- Test/monitor consigliato: contatore di occorrenze di questo warning su base settimanale — escalare se la frequenza aumenta.

### [DAY-009] Endpoint API REST inaccessibile (JWT scaduto) durante la sessione di audit

- Tipo: Ambiguità / Rischio operativo
- Area: Ops / Data
- Evidenza:
  - file/log/tabella: risposta HTTP diretta
  - timestamp: 2026-07-23 (inizio sessione di audit)
  - snippet: `{"detail":"Invalid or expired JWT token"}` su `/api/decisions`, `/api/trades`, `/api/signals`, `/api/positions`, `/api/orders` con il token fornito
- Descrizione: il token Bearer fornito per l'audit non è stato accettato dall'API (403). L'analisi è stata quindi condotta interamente via query dirette a PostgreSQL e log Docker, fonte comunque più autorevole ma non identica a ciò che vedrebbe un consumer dell'API (es. frontend/mobile).
- Impatto: impossibile verificare se anche i consumer legittimi (frontend, mobile app) stiano sperimentando lo stesso problema di autenticazione oggi.
- Severità: Low (per l'audit; potenzialmente Medium se il problema è condiviso con utenti reali)
- Confidenza: High
- Azione consigliata: verificare se il JWT scade per policy (rotazione token) o è un bug di validazione; rigenerare il token per l'audit successivo.
- Test/monitor consigliato: alert su tasso di 401/403 anomalo sull'API pubblica.

---

## 11. False Positive / Aree Corrette

- **Nessuna SELL con sentiment positivo (bug A5)** trovata oggi.
- **Nessun roundtrip <30 min** (BUY+SELL stesso ticker stesso ciclo).
- **Nessun ordine duplicato o generato nello stesso minuto** (race condition scheduler) — tutti gli `order_id` sono univoci con timestamp coerenti.
- **Nessuna news con timestamp futuro o "stale" (>48h)**.
- **Nessun trade fuori orario** di mercato.
- **Righe `content_hash` ripetute** inizialmente sospette risultano estrazione multi-entity legittima (un articolo → più ticker), non duplicazione di segnale.
- **Fix bug #59 (BUY su sentiment fortemente negativo/desync) confermato attivo**: nessuna nuova BUY generata da segnale fallback o con score/sentiment desincronizzato oggi, coerente con il deploy PR #114 di stamattina.
- **Cancel-before-sell (PR #69) funziona**: log conferma cancellazione esplicita dello stop protettivo prima di ogni SELL (es. WDC 16:22:10).
- **Pyramiding guard (P0-05) funziona correttamente**: ha bloccato ogni tentativo di ri-BUY su ticker con trade già aperta (686 occorrenze osservate, tutte coerenti).
- **Ollama sostanzialmente sempre disponibile**: 1 solo timeout hard su ~24 cicli sentiment/196 news — molto meglio del pattern storico (70-86% fallback) osservato a fine giugno/inizio luglio.
- **Nessun constraint di rischio automatico attivato** (`constraints_fired: []` su tutti i 16 cicli) — solo il kill-switch manuale ha bloccato l'attività.
- **Guardia dati stale S1** attiva e funzionante (AZN/SPCX scartati 16 volte per osservazioni prezzo insufficienti).

---

## 12. Dati Mancanti o Non Accessibili

| Dato | Motivo | Query/azione che servirebbe |
|---|---|---|
| Stato reale ordini Alpaca (fill/reject) per `bf7fe4b8…` e `87132adc…` (WDC) | API `/api/orders` 403 (JWT scaduto); nessuna chiamata diretta al broker consentita in questa sessione read-only | Rigenerare JWT valido o interrogare Alpaca API direttamente (fuori scope di questa sessione) |
| PnL non realizzato per singolo ticker sulle 44 posizioni aperte | Nessuna tabella `positions`/prezzi correnti in Postgres | `/api/positions` (richiede JWT valido) o snapshot prezzi Alpaca |
| Log worker/beat prima delle 12:13:54 UTC del 07-22 | Container riavviato (deploy PR #114); `docker logs` mostra solo dal restart | Log aggregator esterno (se esiste) o log persistiti su disco prima del restart |
| Conferma esatta ora attivazione kill-switch (07:40 da memoria) | Fuori dalla finestra log disponibile | Verificare `audit_log`/Redis TTL history se conservato |
| `performance_metrics` per `metric_date=2026-07-22` | Tabella vuota (0 righe) — il job `performance-daily` gira alle 03:00 UTC del giorno successivo (07-23); possibile non ancora eseguito o fallito silenziosamente al momento dell'audit | Ri-controllare `performance_metrics` dopo le 03:00 UTC del 07-23 |

---

## 13. Raccomandazioni Immediate

1. **Verificare manualmente lo stato broker della posizione WDC** (#373) e riconciliare `trades.exit_*` di conseguenza [DAY-002].
2. **Fixare `mobile_alert_task`** passando un client Redis dedicato invece di riusare la dependency FastAPI-only [DAY-003] — impatto: 100% failure rate, probabilmente da giorni.
3. **Aggiungere TTL obbligatorio + alert** al kill-switch manuale `system:halted_by_operator` per evitare halt prolungati non intenzionali [DAY-001].
4. **Rigenerare il token JWT** usato per l'audit/API (403 durante tutta la sessione) [DAY-009].
5. Sollecitare il fix già tracciato in **issue #75** (herfindahl/combined_drawdown) — oggi ulteriormente confermato stale [DAY-007].

---

## 14. Test o Monitor da Aggiungere

- Alert su trade con `exit_order_ids` non vuoto ma `exit_time IS NULL` da oltre N ore (reconciliation gap).
- Alert sul tasso di successo di `run_mobile_alert_evaluation` (deve essere ~100%, non 0%).
- Alert se `system:halted_by_operator` è attivo durante market hours per più di N minuti.
- Monitor su whipsaw: trade riaperti entro N minuti dalla chiusura sullo stesso ticker/strategia con score quasi identico.
- Monitor sul rapporto ineligible/eligible per modello LLM (oggi glm-5.2 80.5% ineligible) — non ancora un problema (fallback rate reale 0.5%), ma da tracciare nel tempo.
- Test di integrazione per task Celery che dipendono da `src/api/deps.py` (nessuno dovrebbe farlo senza bootstrap esplicito).

---

## 15. Ticket Tecnici Suggeriti (Remediation, non patch)

1. **Bug — mobile_alert_task 100% failure**: `MobileSnapshotBuilder` di default chiama una dependency FastAPI-only (`get_redis_store`) da un contesto Celery dove non è mai inizializzata. Area: Ops/Mobile. Severità: Critical (dominio mobile monitoring).
2. **Bug/Rischio — WDC trade #373 orfana**: due SELL sottomessi in due giorni diversi mai riconciliati; guardia pyramiding blocca re-entry legittimi su un dato potenzialmente stale. Area: Orders/Broker.
3. **Rischio — kill-switch senza TTL**: un halt manuale "test" ha bloccato 2h di trading e cancellato ripetutamente ordini pendenti. Area: Risk/Ops.
4. **Rischio — loss-feedback ratchet su evidenza stale**: possibile doppio taglio di regime_scale sulla stessa loss episode dopo scadenza cooldown. Area: Risk.
5. **Ambiguità — schedule non DST-aware**: perdita sistematica dei primi 30 min di mercato durante EDT. Area: Data/Ops.
6. **Bug minore (già tracciato, #75)** — herfindahl_index/combined_drawdown degeneri, riconfermato oggi.
7. **Miglioria — rebalance band S1**: whipsaw GE (BUY→SELL→BUY in 3.5h) per oscillazione marginale nel ranking. Area: Signal/Orders.

---

## 16. Stato Sistema

| Metrica | Valore |
|---|---|
| Ollama up/down | **Up** per l'intera giornata tranne 1 timeout isolato (19:03:13, ticker DB, 90s su entrambi i modelli) → downtime effettivo trascurabile (<2 min su ~6h di operatività) |
| FinBERT hard-fallback rate | 1/196 sentiment_signals = **0.51%** (ben al di sotto della soglia storica 70-86% osservata a fine giugno) |
| Tasso "ineligible" per modello (conf<0.4, diverso da hard fallback) | glm-5.2: 80.5% · gpt-oss: 49.2% — implica solo 59.2% delle signal sono vero ensemble a 2 modelli |
| Worker restart events | 1 (`alembic-worker-1`, 2026-07-22 12:13:54 UTC — correlato al merge PR #114 delle 09:53 UTC) |
| Altri container | `beat`, `api`, `worker-inference`, `frontend`, `postgres`, `redis` — tutti "Up 24 hours" al momento dell'audit, nessun restart aggiuntivo rilevato |
| Kill-switch manuale | Attivo per almeno 14:07–15:52 UTC (2h), motivo "test" (da log + memoria) |
| mobile_alert_task success rate | **0% (0/480)** per l'intera giornata — vedi [DAY-003] |
