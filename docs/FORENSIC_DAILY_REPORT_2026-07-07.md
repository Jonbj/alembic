# Forensic Daily Report — 2026-07-07

Analista: Trading Systems Forensic Analyst + Senior Backend Engineer + Quant Operations Reviewer (sessione autonoma, read-only)
Generato: 2026-07-08
Timezone operativo: **UTC** (esplicito in `src/workers/celery_app.py`: `timezone="UTC"`, `enable_utc=True` — nessuna ambiguità).
Market hours di riferimento: 13:30–20:00 UTC. Finestra operativa scheduler (sentiment/GDELT/portfolio cycle): **14:00–21:00 UTC, Lun–Ven**.

---

## 1. Executive Summary

Il 7 luglio 2026 la pipeline ha operato in **modalità paper** (S1 `supervised_paper`, S4 `paper`, entrambe `approved=true`; nessun ordine live). Sono stati generati **0 nuovi ingressi (BUY)** e **4 uscite**: 2 stop-loss (MRVL, AVGO) alle 14:07 UTC e 2 rebalance-sell (AMZN, DB) alle 16:37 UTC, tutte con fill confermato lato Alpaca paper (submitted→filled tracciato). PnL realizzato netto: **-212,27 USD**. Il sistema ha chiuso la giornata flat (esposizione 0%).

News ingest: 292 righe in `news_log` (gdelt_gkg 199, alpaca_benzinga 93) da 817 item accodati; nessun timestamp futuro, nessun problema di sanitizzazione rilevato. Fallback FinBERT al 78,9% (232/294 segnali) — coerente col trend 70–86% dell'ultima settimana, quindi **non è un'anomalia specifica del 7/7** ma una condizione cronica.

**La scoperta più rilevante**: i log stdout di tutti e 7 i container Docker e la tabella di audit `audit_log` si sono **azzerati contemporaneamente il 2026-07-06 verso le 17:07–17:09 UTC e non sono mai ripresi**, nemmeno dopo un restart completo dello stack (tutti e 7 i container, incluso Postgres/Redis) avvenuto il 07-07 alle 14:38:53 UTC. Il giorno target ricade quindi interamente in una finestra di **osservabilità azzerata**: la pipeline di trading ha continuato a scrivere sulle tabelle operative (decisioni, trade, segnali) con dati internamente coerenti, ma non esiste alcuna evidenza di log applicativo né di audit trail per tutto il 07-07. Root cause non determinabile in questa sessione (nessun accesso sudo/filesystem host).

## 2. Verdict Finale

**OK con warning — osservabilità compromessa.**

La logica funzionale osservabile via DB/API (segnali → decisioni → ordini → fill → posizioni) è internamente coerente, correttamente gated (soglie rispettate, nessun ordine spurio, paper/live coerente, nessuna pyramiding, nessun roundtrip anomalo). Tuttavia il blackout di log/audit copre l'intera giornata target, per cui **una parte sostanziale delle verifiche richieste in Fase 4 (latenza LLM, timeout/retry granulari, eccezioni Celery) non è verificabile** con le fonti disponibili in questa sessione. Il verdetto non è "processo non affidabile" perché i dati DB disponibili non mostrano comportamento scorretto, ma "non verificabile" per la componente di log/telemetria — da qui il warning.

---

## 3. Timeline del 2026-07-07 (UTC)

| Ora UTC | Componente | Evento | Fonte |
|---|---|---|---|
| 06:42:31 | Risk monitor | Snapshot rischio: NAV 110.160,81 USD, exposure 6,75%, 4 posizioni aperte (ereditate dal 07-06) | `risk_reports` id=24 |
| 06:43:10 | News ingest (GDELT) | Prima news del giorno in `news_log` | `news_log` min(fetched_at) |
| 14:00 | Scheduler | Apertura finestra operativa (sentiment-worker + GDELT ogni 15 min, Lun-Ven) | `celery_app.py` beat schedule |
| 14:07:00.777 (07-06, per riferimento) | S4 | Entry BUY MRVL (score 0,033, ensemble glm-5.2) | `execution_decisions` id 1175 (giorno precedente) |
| 14:07:00.809 | Risk/Exit | **Stop-loss** MRVL (-10,1%) e AVGO (-3,5%) chiusi contemporaneamente; **non presenti in `execution_decisions`**, solo in `trades` (`exit_reason=stop_loss`) | `trades` id 236,237; portfolio_cycles id 294 (orders_count=0 — vedi [DAY-005]) |
| 14:15:51 | LLM budget | Prima spesa LLM del giorno registrata | `llm_budget` id 1756 |
| 14:16:20 | LLM ensemble | Prima risposta ensemble (kimi-k2.6/glm-5.2) del giorno | `llm_responses` min(generated_at) |
| 14:22:04 | Execution | Prime `execution_decisions` con `tick_time` del giorno (4 righe, tutte SKIP_THRESHOLD) | `execution_decisions` |
| **14:38:53.9xx** | Infra | **Restart completo dello stack**: tutti e 7 i container (api, worker, worker-inference, beat, frontend, postgres, redis) ripartono nello stesso secondo, `RestartCount=0` (non crash-loop) | `docker inspect` |
| 14:37→14:52 | Portfolio cycle | Cadenza 15 min non interrotta dal restart (nessun ciclo saltato) | `portfolio_cycles` |
| 16:37:00.680 | Portfolio combiner | Unico ciclo del giorno con ordini: 2 SELL (AMZN, DB), `allocation_weight=0.0` — rebalance-out per score sotto soglia (non bug sentiment, vedi §11) | `portfolio_cycles` id 304; `execution_decisions` id 1505,1506 |
| 16:37:04.9–07.5 | Alpaca (paper) | Ordini submitted→filled: DB 208ms, AMZN 2,57s | `/api/orders` (Alpaca order lifecycle) |
| 19:52:03.6 | Execution | Ultimo batch di `execution_decisions` (9 righe, tutte SKIP_THRESHOLD) | `execution_decisions` |
| 21:49:03 | LLM ensemble | Ultima risposta ensemble del giorno | `llm_responses` max(generated_at) |
| 21:49:47 | News/Sentiment | Ultima news processata e ultimo incremento `fallback_counters` (consecutive_fallback=2) | `news_log`, `fallback_counters` |
| 22:30:00 | Risk monitor | Snapshot rischio EOD: NAV 110.088,68 USD, exposure **0%** (flat, coerente con le 4 chiusure) | `risk_reports` id=25 |

**Nota critica sulla finestra di osservabilità**: dal 2026-07-06 ~17:07–17:09 UTC fino ad almeno il momento di questa analisi (2026-07-08 12:33 UTC), **nessun log stdout container e nessuna riga `audit_log`** sono stati prodotti (vedi [DAY-001]). La timeline sopra è quindi ricostruita **esclusivamente da timestamp e contenuti delle tabelle operative del DB** (`execution_decisions`, `trades`, `portfolio_cycles`, `sentiment_signals`, `llm_responses`, `risk_reports`), che sono rimaste popolate correttamente per tutto il giorno nonostante il blackout di log/audit — non da log applicativi.

---

## 4. Tabella News Ingest

### Per fonte (day = 2026-07-07, da `ingestion_stats_daily`)

| Fonte | Fetched | Queued (→Redis) | Duplicates | Discarded no-ticker | In `news_log` (finale) |
|---|---|---|---|---|---|
| alpaca_benzinga | 830 | 577 | 3.336¹ | 0 | 93 |
| gdelt_gkg | 2.393 | 240 | 209 | 2.009 (84%) | 199 |

¹ Il contatore `duplicates` è per coppia `(url, ticker)` post fan-out multi-ticker, non per articolo grezzo — un solo articolo con 10 ticker genera fino a 10 controlli di duplicazione. Il valore >fetched è quindi spiegabile e non indica un problema di raccolta (vedi [DAY-006]).

Gap tra "queued" (817 totali) e righe finali in `news_log` (292): attribuibile ai filtri legittimi del `SentimentWorker` (`skipped_stale`, `skipped_neutral`, `skipped_not_tradable`) — **non verificabile con contatori esatti per il 07-07** perché i log che riportano queste statistiche per-run sono nella finestra di blackout (vedi §12).

### Per ticker (top, da `news_log`)

| Ticker | News | Segnali generati | Score medio | Fallback FinBERT |
|---|---|---|---|---|
| MS | 43 | 44 | +0,020 | 41/44 (93%) |
| MU | 41 | 41 | -0,124 | 27/41 (66%) |
| GS | 33 | 33 | +0,022 | 32/33 (97%) |
| DB | 13 | 13 | -0,085 | 12/13 (92%) |
| SHEL | 11 | 11 | +0,051 | 7/11 |
| SPCX | 9 | 9 | +0,192 | 6/9 |
| LLY | 8 | 8 | -0,041 | 8/8 (100%) |
| AAPL | 7 | 7 | +0,074 | 5/7 |
| AMAT | 7 | 7 | -0,165 | 5/7 |

### Qualità/problemi rilevati

- **Timestamp futuri o pre-fetch**: nessuno (`published_at > fetched_at` → 0 righe).
- **Duplicati cross-provider stesso giorno**: nessuno rilevato con `content_hash` uguale tra `gdelt_gkg` e `alpaca_benzinga` — i duplicati con hash ripetuto sono sempre intra-fonte, fan-out multi-ticker dello stesso articolo (es. articolo Benzinga "Samsung selloff..." → 10 ticker: AAPL, AMZN, GOOGL, META, MSFT, MU, NVDA, QQQ, SPCX, SPY — vedi [DAY-006]).
- **GDELT**: 84% degli articoli scartati per assenza di ticker riconosciuto (`discarded_no_ticker`) — atteso per un feed generalista (molte notizie macro senza società specifica).
- **discarded_reason**: colonna sempre vuota nei 292 record del giorno — coerente col fatto che gli item scartati non arrivano mai a `news_log` (lo scarto avviene prima dell'insert), quindi la colonna non è popolata per design in questo path.
- **SPCX**: assente dalla tabella `ticker_lookup` (alias resolver) ma **esplicitamente presente nel watchlist configurato** (`config/trading.yaml:119`) — non è un artefatto del resolver, arriva via `source_metadata` di Benzinga o direttamente da watchlist, non via `org_lookup`/GDELT. Verificato, non è un'anomalia (vedi §11).
- **Coda Redis**: `news:queue` con **62 item non ancora processati** al momento dell'ispezione (07-08 12:33, fuori orario di mercato); `news:processing` = 0 (nessun item bloccato in-flight). Plausibilmente normale accumulo pre-market in attesa del prossimo avvio worker (14:00 UTC), ma non confermabile con certezza senza i log del worker.

**Confidenza analisi ingest: Alta** (dati DB completi e coerenti tra le tabelle `ingestion_stats_daily` e `news_log`).

---

## 5. Tabella Performance Modelli LLM

| Modello | Risposte totali | Eligible (conf≥0.4) | Non-eligible | Polarity media (eligible) | Confidence media (eligible) | Range polarity |
|---|---|---|---|---|---|---|
| glm-5.2:cloud | 62 | 49 | 13 | +0,024 | 0,596 | -0,80 / +0,80 |
| kimi-k2.6:cloud | 62 | 41 | 21 | -0,072 | 0,605 | -0,75 / +0,75 |

- **Chiamate totali ensemble**: 124 (62 signal-attempt × 2 modelli).
- **Esito aggregazione**: 62/294 segnali (21,1%) hanno usato l'ensemble con successo; **232/294 (78,9%) sono andati in fallback FinBERT**, motivo riportato uniformemente `"FinBERT fallback (ensemble divergence)"` — **mai** timeout né budget esaurito (`llm_budget.budget_exhausted=false`, speso solo 0,105 USD sui 294 segnali).
- **Soglia di divergenza**: `divergence_threshold=0.30` sullo std delle polarity tra i 2 modelli (`src/llm/ensemble.py`) → con solo 2 modelli, std≥0.30 equivale a |polarity_kimi − polarity_glm| ≥ 0,60 su una scala [-1,+1].
- **Trend fallback ultimi 5 giorni operativi**: 70,3% (07-01) → 79,5% (07-02) → 86,4% (07-03) → 76,1% (07-06) → **78,9% (07-07)**. Il tasso del 7/7 è nella norma del periodo — **non è un'anomalia del giorno target**, ma una condizione cronica che merita revisione strategica (vedi [DAY-002]).
- **Latenza media per chiamata**: **non verificabile** — richiederebbe i log per-item del worker-inference, nella finestra di blackout (vedi §12).
- **Validazione output prima dell'ingresso nel signal store**: sì — `min_confidence=0.4` filtra gli output non affidabili (34/124 risposte scartate come `eligible=false`); JSON schema strutturato via function calling (`LLMSentimentOutput`).
- **Gestione varianza alta**: sì, per design — divergenza ≥0.30 declassa a FinBERT invece di usare un valore medio potenzialmente fuorviante.
- **News duplicate pesano più volte?**: sì, per design — fan-out multi-ticker (stesso `content_hash`, ticker diversi) genera segnali indipendenti per ogni ticker menzionato; nessuna evidenza che la **stessa** coppia (url,ticker) abbia generato più di un segnale (vincolo UNIQUE su `sentiment_signals(symbol, generated_at)` e `news_log(url,ticker)`).
- **Confidence bassa riduce il peso?**: sì — `score = polarity × confidence` (formula CLAUDE.md rispettata, verificato a campione sui valori in `sentiment_signals`).
- **Chiamate offline/background, mai nel trading loop?**: confermato — `SentimentWorker` gira su coda Celery `inference` separata (`worker-inference`, concurrency=1), il portfolio cycle legge solo segnali già scritti in DB/Redis, mai chiamate LLM sincrone nel ciclo di esecuzione.
- **Rischio hallucination diretto in decisione**: basso — score passa sempre per `ema_pass` + soglia (`feedback threshold` dinamica, 0,40 osservato il 07-07) prima di diventare un ordine; nessun ordine generato con score sotto soglia il 07-07.

**Confidenza analisi LLM: Media** — le distribuzioni statistiche sono solide (dati DB), ma latenza, retry e dettaglio errore per singola chiamata non sono verificabili per il blackout log.

---

## 6. Tabella Segnali Finali per Ticker (2026-07-07, top 15 per volume)

| Ticker | N. segnali | Score medio | Score min/max | Fallback | Decisione più comune |
|---|---|---|---|---|---|
| MS | 44 | +0,020 | -0,35 / +0,40 | 41/44 | SKIP_THRESHOLD |
| MU | 41 | -0,124 | -0,60 / +0,45 | 27/41 | SKIP_THRESHOLD |
| GS | 33 | +0,022 | -0,30 / +0,35 | 32/33 | SKIP_THRESHOLD |
| DB | 13 | -0,085 | — | 12/13 | SKIP_THRESHOLD → 1 SELL (rebalance) |
| SHEL | 11 | +0,051 | — | 7/11 | SKIP_THRESHOLD |
| SPCX | 9 | +0,192 | — | 6/9 | SKIP_THRESHOLD |
| LLY | 8 | -0,041 | — | 8/8 | SKIP_THRESHOLD |
| AAPL | 7 | +0,074 | — | 5/7 | SKIP_THRESHOLD |
| CAT | 7 | +0,009 | — | 7/7 | SKIP_THRESHOLD |
| AMAT | 7 | -0,165 | — | 5/7 | SKIP_THRESHOLD |
| MSFT | 6 | +0,015 | — | 4/6 | SKIP_THRESHOLD |
| QQQ | 6 | -0,021 | — | 4/6 | SKIP_THRESHOLD |
| GOOGL | 5 | +0,019 | — | 5/5 | SKIP_THRESHOLD |
| DIS | 5 | -0,017 | — | 4/5 | SKIP_THRESHOLD |
| TSM | 5 | +0,105 | — | 3/5 | SKIP_THRESHOLD |
| **AMZN** | 3 | — | — | — | **SELL (rebalance, score decaduto)** |

**294 segnali totali generati, 314 decisioni valutate (`execution_decisions`), di cui 312 SKIP_THRESHOLD (99,4%) e 2 SELL.** Nessun ticker ha superato la soglia di ingresso (0,40) il 07-07 — coerente con `regime_mult=0,7` osservato su tutte le decisioni (throttle di regime attivo, non 1,0).

---

## 7. Tabella Ordini Generati/Eseguiti

| # | Timestamp decisione | Strategia | Ticker | Azione | Qty | Prezzo atteso | Prezzo fill | Stato | Broker | Rationale | Risk check |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 07-07 14:07:00 (mercato) | Risk (synthetic stop-loss, FIX-C) | MRVL | SELL (close) | 6,2296 | entry 256,65 | 230,71 | filled | Alpaca paper | Stop-loss breach -10,1% (soglia configurata 2%) | Sì, ma **fuori da `execution_decisions`** (vedi [DAY-004]) |
| 2 | 07-07 14:07:00 | Risk (synthetic stop-loss) | AVGO | SELL (close) | 3,1542 | entry 379,74 | 366,31 | filled | Alpaca paper | Stop-loss breach -3,5% | Idem |
| 3 | 07-07 16:37:00.680 | S4 portfolio combiner | AMZN | SELL (rebalance→0%) | 9,7277 | entry 245,14 | 245,06 | filled (submit 16:37:04.937, fill 16:37:07.510, ~2,6s) | Alpaca paper | Score decaduto a +0,275 (sotto soglia mantenimento 0,40) | Sì — `execution_decisions` id 1505 |
| 4 | 07-07 16:37:00.680 | S4 portfolio combiner | DB | SELL (rebalance→0%) | 64,6127 | entry 36,90 | 36,89 | filled (submit 16:37:05.085, fill 16:37:05.293, ~0,2s) | Alpaca paper | Score decaduto a +0,073 (sotto soglia mantenimento 0,40) | Sì — `execution_decisions` id 1506 |

**Nessun BUY il 07-07.** Nessun reject, nessun cancel, nessun ordine parziale osservato. Tutti gli ordini risultano `status=filled` sia in `trades` sia nell'endpoint `/api/orders` (dati Alpaca broker).

Riconciliazione ordini↔fill↔posizioni: **OK**. `entry_order_id`/`exit_order_id` in `trades` coincidono con gli `order_id` in `execution_decisions` (per gli ordini S4) e con gli `id` in `/api/orders`; `/api/positions` ritorna `[]` (flat), coerente con `total_exposure=0` in `risk_reports` a fine giornata.

**Nota di data-model**: `trades.decision_id` punta alla decisione di **entry** (BUY), non a quella di **exit** — per risalire al rationale dell'uscita occorre joinare su `exit_order_id = execution_decisions.order_id`, non su `decision_id`. Non è un bug (i dati sono presenti e coerenti), ma uno strumento di reconciliation automatica ingenuo rischia di leggere il rationale sbagliato.

---

## 8. Tabella PnL/Rendimento

| Trade | Ticker | Entry | Exit | Qty | Gross PnL | Slippage | Cost (bps) | Cost (USD) | Net PnL | Motivo uscita |
|---|---|---|---|---|---|---|---|---|---|---|
| 236 | MRVL | 256,65 (07-06) | 230,71 | 6,2296 | -161,60 | 0,878 | 5,28 | 0,878 | **-162,48** | stop_loss |
| 237 | AVGO | 379,74 (07-06) | 366,31 | 3,1542 | -42,36 | 0,655 | 5,24 | 0,655 | **-43,02** | stop_loss |
| 238 | AMZN | 245,14 (07-06) | 245,06 | 9,7277 | -0,71 | 0,496 | 1,85 | 0,496 | **-1,21** | portfolio_sell |
| 239 | DB | 36,90 (07-06) | 36,89 | 64,6127 | -0,65 | 4,915 | 20,35 | 4,915 | **-5,56** | portfolio_sell |
| **Totale realizzato 07-07** | | | | | **-205,32** | **6,94** | | **6,94** | **-212,27** | |

- **PnL realizzato 07-07**: -212,27 USD (4 chiusure, tutte in perdita).
- **PnL non realizzato al 07-07**: 0 USD — nessuna posizione aperta a fine giornata (`/api/positions` = `[]`).
- **PnL per ticker**: vedi tabella sopra (nessuna aggregazione ulteriore necessaria, 1 trade/ticker).
- **PnL per strategia**: i 4 trade sono tutti riconducibili a segnali S4 in origine (BUY entry 07-06), ma le 2 uscite stop-loss sono un meccanismo di risk management trasversale (FIX-C), non attribuibile a una strategia specifica.
- **Posizioni aperte prima del 07-07 impattate**: tutte e 4 (nessuna posizione era stata aperta *durante* il 07-07: `entry_time` per tutte e 4 ricade nel 07-06).
- **NAV**: 110.160,81 (06:42) → 110.088,68 (22:30) = -72,13 USD. La differenza rispetto al PnL realizzato (-212,27) è plausibile: parte della perdita MRVL/AVGO era già mark-to-market nel NAV delle 06:42 (le posizioni erano già in drawdown prima del primo snapshot del giorno) — **non riconciliato in dettaglio**: servirebbe una query sul book intraday mark-to-market (non disponibile) per una bridge completa NAV-aperture→chiusure. Dato mancante, non inventato.
- **Costi/commissioni**: `cost_usd` totale 6,94 USD sui 4 trade; DB mostra `spread_cost_bps=20,0` (nettamente più alto degli altri, coerente con liquidità inferiore per un ADR europeo) — non anomalo, solo caratteristica dello strumento.
- **Slippage**: stimato sempre uguale a `cost_usd` nella tabella `trades` (stesso valore in entrambe le colonne) — da verificare se è un aliasing intenzionale delle due colonne o una ridondanza nello schema (non bloccante, nota per pulizia dati).

**Confidenza PnL: Alta** per i realizzati (dati completi in `trades` + conferma broker via `/api/orders`); **Bassa** per la bridge NAV intraday completa (dato mancante).

---

## 9. Analisi Correttezza Buy/Sell

| Check | Esito | Note |
|---|---|---|
| BUY generati solo se consentiti | ✅ N/A | 0 BUY il 07-07 |
| SELL/exit generati correttamente | ✅ OK | 2 stop-loss + 2 rebalance, tutti con rationale tracciato |
| Stop-loss rispettati | ⚠️ Warning | Soglia 2% configurata, breach osservati 10,1% e 3,5% — vedi [DAY-003] |
| Signal flip rispettato | ✅ OK | Nessun flip osservato (nessun BUY il giorno stesso su ticker appena venduto) |
| Max holding days | ✅ N/A (non verificato/non applicabile ai 4 trade, tutti <24h) | |
| Rebalance band rispettata | ✅ OK | AMZN/DB chiusi per score sotto soglia mantenimento 0,40 — logica corretta e documentata (FIX-F) |
| Ordini duplicati | ✅ Nessuno | 2 ordini stesso timestamp (16:37:00.680) ma simboli diversi, id univoci — batch legittimo, non race condition |
| Ordini contrari ravvicinati stesso ticker | ✅ Nessuno | Nessun roundtrip <30 min; nessun BUY+SELL stesso ticker lo stesso giorno |
| Ordini su ticker non consentiti | ✅ OK | Tutti i ticker coinvolti presenti nel watchlist configurato |
| Ordini fuori orario | ✅ OK | Tutti entro 14:07–16:37 UTC, dentro la finestra di mercato |
| Trade su dati stale | ⚠️ Non verificabile | Filtro `skipped_stale` esiste nel codice ma conteggio per-run non accessibile (log mancanti) |
| Trade con LLM output non valido | ✅ OK | `eligible=false` correttamente escluso dall'aggregazione |
| Circuit breaker attivo | ✅ OK, non attivato | Nessuna evidenza di trigger nel giorno |
| Strategia disabilitata | ✅ OK | Solo S1/S4 (`approved=true`) hanno girato; S2 `disabled`, S7 `research` non hanno generato attività |
| Paper/live coerente | ✅ OK | `strategy_lifecycle`: S1=`supervised_paper`, S4=`paper`; tutti gli ordini via Alpaca **paper** endpoint |
| Idempotenza retry Celery | ✅ Presente nel codice (`_apply_idempotency_filter`) | Non stressata da errori osservabili nel giorno (nessun retry rilevato in DB) |
| Reconciliation ordini/fill/posizioni | ✅ OK | Vedi §7 |

---

## 10. Anomalie Trovate

### [DAY-001] Blackout totale di log applicativi e audit trail

* Tipo: Anomalia
* Area: Ops
* Evidenza:
  * file/log/tabella: `docker logs alembic-{worker,worker-inference,beat,api}-1`; tabella `audit_log`
  * timestamp: ultimo evento in tutte le fonti = **2026-07-06 17:07:04–17:09:27 UTC**; nessun evento successivo fino a 2026-07-08 12:33 UTC (momento dell'analisi)
  * snippet/query: `SELECT count(*), max(created_at) FROM audit_log;` → `5335 righe, max=2026-07-06 17:07:04.577756+00`; `docker logs <container> | tail` → ultima riga datata 2026-07-06 17:09:27
* Descrizione: sia i log stdout (json-file, tutti e 7 i container) sia la tabella di audit compliance `audit_log` smettono di ricevere scritture nello stesso istante (finestra di 2 minuti), e non riprendono **nemmeno dopo un restart completo dello stack** avvenuto il 07-07 alle 14:38:53 UTC. Le tabelle operative (`trades`, `execution_decisions`, `sentiment_signals`, `portfolio_cycles`, `risk_reports`) hanno invece continuato a essere scritte normalmente per tutto il 07-07, quindi la pipeline di trading NON si è fermata — solo la componente di osservabilità/audit.
* Impatto: l'intera giornata target (07-07) ricade in questa finestra di blackout. Non è possibile verificare latenze LLM, errori/timeout Ollama granulari, eccezioni Celery, retry, azioni admin/manuali. L'auditabilità richiesta esplicitamente da CLAUDE.md ("priorità a auditabilità, riproducibilità, idempotenza e safety") è compromessa per >43 ore consecutive al momento dell'analisi.
* Severità: **Critical**
* Confidenza: **High** (correlazione temporale precisa tra fonti indipendenti: log Docker di 4 container diversi + tabella DB separata, tutti fermi allo stesso istante)
* Azione consigliata: escalation immediata a infra owner; verificare spazio disco host, stato del docker log driver (`json-file`, max-size 50m/max-file 5), eventuali eccezioni silenziate nel path di scrittura di `audit_log` (potrebbero condividere un handler/connessione). Non risolvibile in questa sessione (permessi filesystem host negati, no sudo).
* Test/monitor consigliato: alert su "età ultima riga `audit_log`" e su "età ultima riga di log container" indipendenti dagli health-check applicativi (che in questo caso avrebbero riportato falsamente "tutto ok").

### [DAY-002] Tasso di fallback FinBERT cronicamente alto (78,9% il 07-07, 70–86% ultima settimana)

* Tipo: Rischio
* Area: LLM
* Evidenza:
  * file/log/tabella: `sentiment_signals`, `src/llm/ensemble.py:190` (`divergence_threshold=0.30`)
  * timestamp: intera giornata 07-07
  * snippet/query: `SELECT count(*), sum(fallback_used::int) FROM sentiment_signals WHERE generated_at::date='2026-07-07'` → 294 / 232
* Descrizione: 232/294 segnali del giorno sono stati generati da FinBERT (fallback deterministico) invece che dall'ensemble kimi-k2.6/glm-5.2, sempre per superamento della soglia di divergenza (std≥0,30), mai per timeout o budget. Il trend è identico nei 5 giorni precedenti — condizione strutturale, non un incidente del 07-07.
* Impatto: il "DK-CoT ensemble" che è il cuore del design (CLAUDE.md, sezione Prompt Engineering) guida solo ~1 segnale su 5; il resto usa un classificatore locale più semplice. Riduce il valore atteso dell'architettura "Alpha Miner" basata su ragionamento LLM strutturato.
* Severità: **High** (strategico, non bloccante operativamente)
* Confidenza: **High**
* Azione consigliata: rivedere la soglia di divergenza (0,30 con solo 2 modelli è severa: richiede accordo entro 0,60 di polarity) o ampliare il pool di modelli attivi in ensemble (il pool candidato in CLAUDE.md include qwen3.5, deepseek-v4-pro, glm-5.1 oltre ai 2 correnti).
* Test/monitor consigliato: dashboard/alert su fallback rate a 7gg mobile con soglia (es. >60% sostenuto) come SLO esplicito, non solo osservazione post-hoc.

### [DAY-003] Stop-loss triggerato ben oltre la soglia configurata (2%)

* Tipo: Rischio
* Area: Risk
* Evidenza:
  * file/log/tabella: `trades` id 236 (MRVL), 237 (AVGO); `config/trading.yaml:153` (`stop_loss: 0.02`)
  * timestamp: 2026-07-07 14:07:00.809715 UTC (primo ciclo di mercato del giorno)
  * snippet/query: MRVL entry 256,65 → exit 230,71 = **-10,1%**; AVGO entry 379,74 → exit 366,31 = **-3,5%**
* Descrizione: entrambe le posizioni sono state chiuse per stop-loss al primo controllo di mercato del giorno (14:07 UTC), con drawdown 1,75x–5x oltre la soglia configurata del 2%. Il controllo stop-loss (`_stop_loss_breached_symbols`, FIX-C) gira solo dentro il ciclo portfolio a cadenza 15 min, attivo unicamente 14:00–21:00 UTC — nessun monitoraggio overnight/pre-market. Ipotesi più probabile: gap di prezzo overnight/pre-market non intercettato prima della riapertura del monitoraggio, ma **non confermabile** senza un feed prezzi intraday continuo (dato non disponibile in questa sessione).
* Impatto: rischio reale di slippage-oltre-lo-stop su gap overnight; il -10,1% su MRVL è 5 volte la soglia nominale.
* Severità: **Medium** (limitazione architetturale nota, non bug di codice — ma impatto economico concreto)
* Confidenza: **Medium** (meccanismo plausibile e coerente col codice, ma root cause del gap di prezzo non verificata con dati di prezzo intraday)
* Azione consigliata: valutare un controllo stop-loss anche pre-market/after-hours, o quantomeno un controllo immediato all'apertura (13:30 UTC) invece di attendere il primo ciclo schedulato (14:07).
* Test/monitor consigliato: test che simuli un gap overnight >soglia e verifichi tempo-a-chiusura e slippage risultante; monitor su "drawdown effettivo alla chiusura stop-loss" vs soglia nominale, con alert se il rapporto supera 1,5x.

### [DAY-004] Uscite stop-loss non tracciate in `execution_decisions`

* Tipo: Ambiguità
* Area: Risk / Data
* Evidenza:
  * file/log/tabella: `execution_decisions` (0 righe per MRVL/AVGO su tutto il 07-07); `trades` id 236,237; `src/workers/portfolio_scheduler.py` (meccanismo FIX-C "synthetic stop-loss", esplicitamente fuori da `final_orders`)
* Descrizione: le uscite per stop-loss sono per design un path separato dal combiner di portafoglio e non producono righe in `execution_decisions` (la tabella che dovrebbe essere la fonte "ufficiale" di audit delle decisioni). L'unica traccia è in `trades.exit_reason='stop_loss'`.
* Impatto: chi fa query di audit/monitoraggio su `execution_decisions` come fonte primaria non vede le uscite di risk management — frammentazione della audit trail su due tabelle con semantiche diverse.
* Severità: **Medium**
* Confidenza: **High** (comportamento confermato nel codice, non un'inferenza)
* Azione consigliata: loggare anche le uscite stop-loss in `execution_decisions` (o in una vista unificata) per avere un'unica fonte di verità sulle decisioni.
* Test/monitor consigliato: query di reconciliation periodica `trades.exit_reason` vs presenza in `execution_decisions`, alert su mismatch.

### [DAY-005] Restart completo dello stack durante l'orario di mercato

* Tipo: Anomalia
* Area: Ops
* Evidenza:
  * file/log/tabella: `docker inspect` (tutti e 7 i container, `StartedAt=2026-07-07T14:38:53.9xxZ`, incluso `alembic-postgres-1` e `alembic-redis-1`)
* Descrizione: l'intero stack (inclusi DB e Redis) è ripartito nello stesso secondo alle 14:38:53 UTC, dentro la finestra di mercato attiva (13:30–20:00 UTC). Non è chiaro se si tratti di un riavvio pianificato (deploy) o di un evento host (reboot, OOM) — non determinabile senza log (blackout in corso, vedi [DAY-001]).
* Impatto: nessun ciclo di portfolio è stato saltato (cadenza 14:37→14:52 intatta), quindi impatto operativo diretto nullo il 07-07; resta comunque un evento di rischio non spiegato durante l'orario di trading.
* Severità: **Medium**
* Confidenza: **High** sull'evento, **Low** sulla causa
* Azione consigliata: chiedere conferma se si è trattato di un deploy pianificato; se non pianificato, trattarlo come incidente collegato a [DAY-001].
* Test/monitor consigliato: alert su restart di container critici durante l'orario di mercato.

### [DAY-006] Fan-out multi-ticker da articolo generico di mercato

* Tipo: Rischio (basso, informativo)
* Area: News / Signal
* Evidenza:
  * file/log/tabella: `news_log`, `content_hash='acb65cb6...'`
  * snippet/query: 1 articolo Benzinga ("Samsung selloff sends warning to US investors, Amazon enters AI debt binge, Iran hits a ship") → 10 ticker distinti: AAPL, AMZN, GOOGL, META, MSFT, MU, NVDA, QQQ, SPCX, SPY
* Descrizione: un singolo articolo di opinione a carattere macro genera 10 segnali di sentiment indipendenti, uno per ticker, dal medesimo contenuto generico — comportamento by design (fan-out per-ticker, documentato nel codice), ma il contenuto non è specifico per nessuno dei 10 titoli.
* Impatto: rischio di diluizione/qualità del segnale — un reasoning LLM "generico" applicato a 10 ticker diversi potrebbe non riflettere analisi ticker-specifica genuina, anche se ogni score resta comunque soggetto alle soglie standard prima di diventare un ordine.
* Severità: **Low**
* Confidenza: **Medium**
* Azione consigliata: nessuna azione urgente; valutare un metric di qualità che distingua segnali da articoli "single-ticker" vs "multi-ticker fan-out" per pesare diversamente in fase di backtest/attribution.
* Test/monitor consigliato: metrica settimanale su % segnali da fan-out multi-ticker (>5 ticker/articolo) vs totale.

### [DAY-007] `/api/health` riporta `mode` hardcoded e non veritiero

* Tipo: Bug
* Area: Frontend/Ops (API)
* Evidenza:
  * file/log/tabella: `src/api/main.py:38`
  * snippet/query: `return {"status": "ok", "mode": "backtest"}` — valore letterale, non letto da config
* Descrizione: l'endpoint ritorna sempre `"mode":"backtest"` indipendentemente dalla modalità reale (`execution.engine=portfolio`, strategie in `paper`). Non impatta l'esecuzione (nessun path di codice legge questo campo per decisioni), ma è fuorviante per chiunque lo usi per monitoraggio.
* Impatto: basso, ma rischio di falso affidamento su questo campo per dashboard/alert esterni.
* Severità: **Low**
* Confidenza: **High**
* Azione consigliata: leggere il valore reale da `config.trading.yaml` (`execution.engine`) o da `strategy_lifecycle`.
* Test/monitor consigliato: test di regressione che verifichi `mode` coerente con la config effettiva.

### [DAY-008] Metrica `duplicates` in `ingestion_stats_daily` fuorviante per il nome

* Tipo: Ambiguità
* Area: Data
* Evidenza:
  * file/log/tabella: `ingestion_stats_daily` (day=2026-07-07, source=alpaca_benzinga: `fetched=830`, `duplicates=3336`)
* Descrizione: il contatore "duplicates" è incrementato per ogni coppia `(url, ticker)` già vista, dopo il fan-out per-ticker — non per articolo grezzo. Un valore 4x superiore a "fetched" è quindi matematicamente corretto ma leggibile come anomalia da chi non conosce l'implementazione.
* Impatto: nessuno funzionale; rischio di falsi allarmi in dashboard/report futuri basati su questa tabella.
* Severità: **Low**
* Confidenza: **High**
* Azione consigliata: rinominare o documentare esplicitamente la metrica (es. `duplicate_ticker_pairs`).
* Test/monitor consigliato: nessuno specifico, solo chiarezza documentale.

---

## 11. False Positive / Aree Corrette

- **"SELL con sentiment positivo" (pattern bug A5 nel checklist)** — AMZN (score +0,275) e DB (score +0,073) sono stati venduti nonostante score positivo. **Verificato come corretto**: non è un'inversione di polarità, ma un rebalance-to-zero perché lo score è decaduto sotto la soglia di mantenimento posizione (0,40 — cfr. entry score originali: AMZN 0,403, DB 0,561, entrambi appena sopra soglia all'ingresso il 07-06). Confermato dal codice (`portfolio_scheduler.py`, commento FIX-F: "S4 signal present but not driving a position"). **Nessun bug.**
- **SPCX assente da `ticker_lookup`** — verificato presente esplicitamente nel watchlist (`config/trading.yaml:119`); arriva via `source_metadata` (Benzinga), non necessita di voce alias. **Nessuna anomalia.**
- **Pyramiding / BUY ripetuti** — 0 BUY il 07-07, check non applicabile, nessuna violazione possibile.
- **Roundtrip <30 min stesso simbolo** — nessuno; tutti gli entry risalgono al 07-06, tutte le exit al 07-07.
- **Ordini duplicati stesso minuto** — i 2 SELL delle 16:37:00.680 sono simboli diversi con `order_id` univoci, generati dallo stesso ciclo batch legittimo — non una race condition.
- **Timezone** — nessuna ambiguità: UTC esplicito nel codice.
- **Paper/live** — confermato coerente: `strategy_lifecycle` mostra S1/S4 in modalità paper, tutti gli ordini via endpoint Alpaca paper.
- **Reconciliation ordini↔fill↔posizioni** — nessuna discrepanza: `trades`, `execution_decisions.order_id` e `/api/orders` sono tra loro coerenti; `/api/positions` flat a fine giornata coerente con `total_exposure=0`.

---

## 12. Dati Mancanti o Non Accessibili

| Dato richiesto | Stato | Query/fonte che servirebbe |
|---|---|---|
| Log applicativi Celery/worker per il 07-07 (latenza LLM, errori, retry, timeout Ollama) | **Non disponibile** (blackout, vedi [DAY-001]) | Log persistiti fuori dal container (es. log shipping esterno), se esistono |
| `audit_log` per il 07-07 (azioni manuali/admin) | **Non disponibile** (0 righe) | Stesso — dipende dal root cause di [DAY-001] |
| Statistiche per-run `skipped_stale`/`skipped_neutral`/`skipped_not_tradable` del SentimentWorker per il 07-07 | **Non disponibile** (erano solo nei log) | Idem |
| Feed prezzi intraday continuo (1-min) per MRVL/AVGO tra 07-06 20:00 UTC e 07-07 14:07 UTC | **Non disponibile in questa sessione** | Alpaca historical bars (coerente con CLAUDE.md — "forward returns from Alpaca historical, not yfinance") |
| Root cause tecnico del blackout log/audit | **Non determinabile** | Accesso host/filesystem con sudo, spazio disco, stato docker daemon (permission denied in questa sessione) |
| `performance_metrics` (composite_ic, icir, drift_level) per 07-06/07-07 | **Vuoto** (0 righe) | Verificare se il job `performance-daily` (03:00 UTC) è effettivamente girato — non verificabile senza log |
| Bridge completa NAV intraday (mark-to-market prima/dopo ogni chiusura) | **Non disponibile** | Snapshot NAV a granularità più fine di quella disponibile in `risk_reports` (solo 2 punti/giorno) |

---

## 13. Raccomandazioni Immediate

1. **Escalation urgente** su [DAY-001]: il blackout di log/audit è attivo da >43 ore al momento dell'analisi e copre l'intero giorno target. Priorità massima.
2. Confermare se il restart stack delle 14:38:53 UTC ([DAY-005]) sia stato un deploy pianificato; se no, trattarlo come parte dello stesso incidente di [DAY-001].
3. Verificare spazio disco sull'host Docker (causa comune per blackout simultaneo di log driver + scritture DB fallite silenziosamente).
4. Non fidarsi di `/api/health.mode` per determinare lo stato operativo reale finché [DAY-007] non è corretto.

## 14. Test o Monitor da Aggiungere

- Alert su "età ultima riga `audit_log`" e "età ultimo log container" **indipendenti** dagli health-check applicativi standard.
- SLO esplicito su FinBERT fallback rate (soglia consigliata: alert se >60% su media mobile 7gg).
- Monitor su profondità `news:queue` in Redis con soglia di allarme calibrata sull'orario (pre-market vs market hours).
- Test automatico di reconciliation `trades.exit_reason` vs presenza corrispondente in `execution_decisions`.
- Test che simuli gap di prezzo overnight superiore alla soglia stop-loss e verifichi il comportamento a mercato aperto.
- Alert su restart di container critici (api/worker/worker-inference/postgres/redis) durante l'orario di mercato (13:30–20:00 UTC).

## 15. Ticket Tecnici Suggeriti

1. **[Critical]** Root-cause del blackout log/audit iniziato 2026-07-06 ~17:07 UTC, tuttora attivo.
2. **[High]** Aggiungere monitor di liveness per log container e freschezza `audit_log`, disaccoppiato dagli health-check applicativi.
3. **[Medium]** Rivalutare `divergence_threshold` (0,30) o ampliare il pool modelli ensemble per ridurre il fallback rate cronico (~79%).
4. **[Medium]** Estendere copertura monitoraggio stop-loss oltre la finestra 14:00–21:00 UTC / cadenza 15 min.
5. **[Medium]** Unificare in `execution_decisions` (o vista dedicata) anche le uscite stop-loss "synthetic" (FIX-C).
6. **[Low]** Correggere `/api/health` per riportare il `mode` reale da config.
7. **[Low]** Rinominare/documentare la metrica `duplicates` in `ingestion_stats_daily`.

## 16. Stato Sistema

- **Ollama up/down**: non spento — 62/294 segnali (21,1%) hanno completato con successo l'ensemble nel corso del giorno, quindi il servizio ha risposto correttamente più volte. Non ci sono evidenze DB di timeout puri (`reasoning` non riporta mai "Ollama timeout" il 07-07); il fallback è sempre per divergenza, non per irraggiungibilità. **Non determinabile un downtime specifico** senza i log (blackout).
- **FinBERT fallback rate**: **78,9%** delle decisioni/segnali del giorno (232/294) — coerente col trend 70–86% della settimana precedente (condizione cronica, non specifica del 07-07).
- **Worker restart events**: 1 evento confermato — restart simultaneo di tutti e 7 i container alle 2026-07-07 14:38:53 UTC (`RestartCount=0`, quindi non un crash-loop rilevato dalla restart policy Docker). Causa non determinata. Nessun ciclo di portfolio saltato per effetto del restart.
