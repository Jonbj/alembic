# Forensic Daily Report — 2026-09-08 (martedì)

**Generato:** 2026-09-09 · **Timezone operativo:** UTC (`src/workers/celery_app.py:53-54`, `timezone="UTC"`, `enable_utc=True` — nessuna ambiguità)
**Sessione:** RTH 13:30–20:00 UTC (EDT). Prima seduta dopo il Labor Day (2026-09-07, mercato chiuso).
**Modalità:** paper (`portfolio_monitor_snapshots.broker_environment='paper'`, `mode='paper'`, `source='alpaca_paper'`; `config/trading.yaml → execution.engine: portfolio`).
**Analisi:** read-only. Nessun file modificato oltre a questo report e a `docs/evidence/findings.json`.

---

## 1. Executive summary

La pipeline ha girato end-to-end senza interruzioni strutturali: 24 cicli di portafoglio regolari
(14:07→19:52, cadenza 15 min esatta), 202 righe news, 214 segnali, 682 righe di Decision Log,
7 BUY e 5 SELL, tutti riconciliati a fill reali. Il NAV chiude a **109.912,36 $** contro
109.973,67 $ di apertura: **−61,31 $ (−0,056%)**, con **−163,44 $ realizzati** (tutti S4) e
un miglioramento del non realizzato che assorbe il resto. Nessun ordine duplicato, nessun ordine
fuori orario, nessun ordine senza risk check, nessun ordine su segnale fallback.
Due difetti nuovi e sostanziali. Primo: alle 15:20 il task sentiment è stato ucciso dal soft time
limit (780 s) e la successiva crash-recovery ha rimesso in coda **12 articoli i cui segnali erano già
stati persistiti** — la stessa notizia è stata scorata due volte, con esiti diversi, e la seconda riga
è quella che il ranker considera autoritativa. Secondo: il punteggio scritto in
`execution_decisions.signal_score` è quello **grezzo**, non quello moltiplicato dalla signal-velocity
che il gate valuta davvero: NVDA risulta comprata a 0,266 con gate a 0,300, e la contraddizione si
scioglie solo leggendo i log. Terzo problema, misurato: **131 articoli** (24% della coda Alpaca)
scartati `stale` fra le 13:00 e le 14:00 dopo **~23 ore in coda** — la notizia della sera prima
e del festivo non arriva mai al modello. Restano aperte 15 recidive già a ledger, fra cui la finestra
cieca 13:30–14:07 (DST), il Telegram 400 sugli alert di loss-feedback, e il token forense rifiutato
su tutti gli endpoint REST. Nota controintuitiva e verificata: le uscite `below_entry_gate` di oggi,
che di norma classifichiamo come churn, hanno prodotto un **saldo netto positivo di +36,57 $**
rispetto al tenere le posizioni fino a fine seduta.

## 2. Verdict finale

### **OK con warning**

Il processo ha funzionato: nessun ordine sbagliato, nessun ordine fantasma, nessuna
disallineamento fra decisione, ordine, fill e posizione. I warning che impediscono un OK pieno sono
due **difetti di correttezza dell'evidenza** — non della trading logic — e come tali rientrano
nell'esenzione della `OBSERVATION_CHARTER.md`:

1. **[DAY-001]** il re-scoring non idempotente inquina `sentiment_signals` con righe duplicate della
   stessa notizia: qualunque IC, copertura o funnel calcolato su quelle righe è sbagliato;
2. **[DAY-002]** il punteggio persistito nella Decision Log non è quello valutato al gate: ogni
   misura che ricalcola "quali segnali hanno passato il gate" dal DB **diverge dalla produzione**
   (stessa classe di #169 e #467).

Nessuna delle due giustifica una taratura, e in questo report non se ne propone alcuna.

---

## 3. Timeline del 2026-09-08 (UTC)

| Ora | Componente | Evento | Esito | Fonte |
|---|---|---|---|---|
| 00:00–09:00 | worker-news-stream | WebSocket Alpaca attivo tutta la notte, articoli accodati in `news:queue` | 32 riconnessioni, 16 `TimeoutError`/DNS | `logs/containers/worker-news-stream-2026-09-08.log` |
| 02:44, 04:00, 04:18 | worker-inference | `run_sentiment_worker` auto-concatenato fuori seduta | ok, ma non drena il backlog notturno | worker-inference log |
| 09:01–09:07 | worker-inference | Telegram polling: `Temporary failure in name resolution` ×18 | ~6,5 min di DNS morto | worker-inference log:19601-19658 |
| 09:03:32 | mobile_events | 2 incidenti **critical**: «Dati broker non aggiornati», «Degradazione market_clock» | poi `recovered` | `mobile_events` |
| 10:30:07 | worker-inference | `Warm shutdown` + `WorkerLostError(SIGTERM) Job: 117` | redeploy pre-market | worker-inference log:22880 |
| 13:00–14:00 | sentiment | **131 articoli scartati `stale`**, età media 23,6 h, attesa in coda 23,2 h | scarto silenzioso | `news_queue_drops` |
| 13:30:00 | beat | `regime-detector-premarket` — unica task schedulata a 13:30 | ok | `celery_app.py:143-147` |
| 13:30:00 | mobile_events | **critical** «Ciclo di portafoglio in ritardo» + warning «Segnali sentiment in ritardo» | recovered a 14:07 | `mobile_events` |
| **13:30–14:07** | **portfolio / ingest** | **Finestra cieca: mercato aperto, nessun ciclo, nessuna ingestione** | 37 min | `portfolio_cycles`, `celery_app.py` `hour="14-21"` |
| 13:31:19 | news_log | Prima riga della giornata (alpaca_benzinga) | — | `news_log` |
| 14:00 | beat | Prima `sentiment-worker` + `run-alpaca-ingestion` + `run-news-ingestion` schedulate | ok | beat log |
| 14:07:00 | portfolio-cycle #1 | S1 rebalance gate chiuso (mensile, #185); S4: 25 segnali → 15 stale → 14 freschi → gate scarta 11 → **3** | 2 BUY (QCOM, NVO), 1 SELL (CRM) | worker log:3813-3830 |
| 14:07:04 | S4 | `SKIP_FALLBACK` ×6, `SKIP_STALE` ×3 (QQQ/XLE/XLK, 91 h), `SKIP_PYRAMIDING` SNOW | ok | `execution_decisions` |
| 14:07:07 | risk #161 | **AMAT non protetta a −22,8%** (qty 0,8571, `sub_one_share`) | alert Telegram **400** | worker log:3828-3830 |
| 14:22:00 | portfolio-cycle #2 | BUY HOOD; **SELL CRM** `[no_signal]` dopo isteresi 2 cicli | −106,01 $ realizzati | `trades` id 979 |
| 14:30:00 | loss-feedback | Ratchet S4 congelato: EWMA R −1,36, 2 perdite consecutive, soglia 0,30→0,30 | alert Telegram **400** | worker log:3969-3971 |
| 15:08:56 | sentiment | Tutti i modelli in timeout su GOOGL → FinBERT; **breaker fallback count=3 → callback in eccezione asyncio** | allerta persa | worker-inference log:31673 |
| 15:08–15:20 | sentiment | 12 articoli scorati e persistiti nel ciclo poi ucciso | segnali scritti, ack mai fatto | `sentiment_signals` |
| 15:20:24 | sentiment | **`SoftTimeLimitExceeded` (780 s)** su `run_sentiment_worker` | ciclo abortito a metà | worker-inference log:31682 |
| 15:23:16 | sentiment | **«Recovering 12 stuck items from news:processing into news:queue»** | 12 articoli ri-accodati | worker-inference log:31950 |
| 15:35–15:45 | sentiment | Gli stessi 12 articoli **ri-scorati**, con risultati diversi | 12 segnali duplicati | `sentiment_signals` |
| 15:37:00 | portfolio-cycle #7 | BUY SPCX @152,80 (score 0,420) | — | `trades` id 985 |
| 16:22:00 | portfolio-cycle #10 | BUY AZN @160,13 (score 0,566) | posizione ancora aperta | `trades` id 986 |
| 16:52:00 | portfolio-cycle #12 | **SELL HOOD e QCOM** `[below_entry_gate]` su segnali freschi (0,4 h e 0,3 h) | −36,53 $ e −17,31 $ | `execution_decisions` 19458-19459 |
| 17:52:00 | portfolio-cycle #16 | BUY NVDA, `signal_score` **0,266** registrato con gate 0,300 | gate passato via velocity boost, non tracciato | `execution_decisions` 19580 |
| 18:07:00 | portfolio-cycle #17 | **SELL SPCX** `[below_entry_gate]`, segnale 0,000 di 0,3 h | −1,14 $ | `trades` id 985 |
| 18:52:00 | portfolio-cycle #20 | **RI-BUY SPCX @153,64** (score 0,369), 45 min dopo l'uscita | churn confermato | `trades` id 988 |
| 19:00:01 | loss-feedback | S4: 5 perdite consecutive, rolling P&L −267,39 $ | alert Telegram **400** | worker log:5776 |
| 19:37:00 | portfolio-cycle #23 | **SELL NVDA** `[below_entry_gate]`, tenuta 105 min = primo beat legale post-hold | `hold_minimum_expiry` (#430) | `trades` id 987 |
| 19:52:00 | portfolio-cycle #24 | Ultimo ciclo della seduta | ok | `portfolio_cycles` |
| 20:00:00 | monitor | NAV di chiusura 109.912,36 $, 45 posizioni, unrealized +1.240,65 $ | — | `portfolio_monitor_snapshots` |
| 20:20:10 | worker-inference | `Warm shutdown` + `WorkerLostError(SIGTERM) Job: 7002` | redeploy post-close | worker-inference log:44327 |
| 22:30:01 | risk_reports | NAV 109.892,22, exposure 32,7%, HHI 0,0263, drawdown 1,24%, `alerts: []` | ok | `risk_reports` |
| 22:50:00 | mobile | warning «Griglia portfolio-cycle fuori seduta», «Copertura news assente su PFE / UNH» (#324) | recovered | `mobile_events` |
| 22:55:00 | stale-drop-alert | `stale_drop_share` 29,0% > soglia 25% → Telegram **200 OK** | consegnato | worker log:7097 |

---

## 4. Tabella news ingest

### 4.1 Per fonte

| Fonte | fetched | queued | duplicates | no_ticker | stale | parse_fail | righe in `news_log` | articoli unici | ticker distinti |
|---|---|---|---|---|---|---|---|---|---|
| alpaca_benzinga | 1.001 | 542 | **4.646** | 0 | 157 | 0 | 185 | 105 | 52 |
| gdelt_gkg | 1.934 | 17 | 2 | **1.915 (99,0%)** | 0 | 0 | 17 | 17 | 10 |
| **Totale** | 2.935 | 559 | 4.648 | 1.915 | 157 | 0 | **202** | **122** | 58 |

`duplicates` (4.646) supera `fetched` (1.001) di 4,6× perché conta le righe ticker-fanout, non gli
articoli: contatore non confrontabile con il suo denominatore (**F-007**, 22ª occorrenza).

### 4.2 Copertura temporale

| Ora UTC | alpaca | gdelt |
|---|---|---|
| 13:00 | 25 | 0 |
| 14:00 | 35 | 3 |
| 15:00 | 33 | 6 |
| 16:00 | 28 | 3 |
| 17:00 | 39 | 2 |
| 18:00 | 16 | 3 |
| 19:00 | 9 | 0 |

**Zero righe prima delle 13:00 e dopo le 19:59.** L'ingestione batch è schedulata `hour="14-21"`;
le righe delle 13:00 arrivano dal WebSocket. Nessuna copertura pre-market né after-hours effettiva.

### 4.3 Latenza di ingestione (published_at → created_at)

| Fonte | n | p50 | p90 | min |
|---|---|---|---|---|
| alpaca_benzinga | 185 | **20,8 min** | 89,9 min | 0 min |
| gdelt_gkg | 17 | 26,1 min | 48,8 min | 2 min |

**Miglioramento reale** rispetto alla mediana storica di ~1 h 50 m registrata su F-019: il
WebSocket sta lavorando. Ma il guadagno è annullato a monte dallo scarto `stale` di massa
descritto in [DAY-003].

### 4.4 Scarti (`news_queue_drops`)

| Motivo | Stadio | n | età media | attesa in coda |
|---|---|---|---|---|
| duplicate_id | ingestion | 4.646 | — | 0,00 h |
| no_ticker | ingestion | 1.915 | — | 0,00 h |
| not_tradable | sentiment | 187 | — | 0,67 h |
| **stale** | sentiment | **157** | **20,22 h** | **19,40 h** |
| duplicate_content | ingestion | 2 | — | 0,00 h |

Ripartizione oraria degli scarti `stale`: **131 alle 13:00** (età 23,6 h, coda 23,2 h),
10 alle 14:00, 16 alle 19:00.

### 4.5 Top ticker per volume

| Ticker | righe | articoli unici |
|---|---|---|
| SPY | 18 | 18 |
| AMZN | 12 | 12 |
| GOOGL | 10 | 10 |
| SPCX | 9 | 9 |
| NVDA | 9 | 9 |
| META / HOOD | 8 | 8 |
| TSLA / QCOM | 7 | 7 |

Concentrazione: top-5 share 26,2%, HHI 0,030 — distribuzione sana, nessun ticker dominante.

### 4.6 Qualità e sanitizzazione

- **Campi mancanti: zero.** 0 righe senza titolo, corpo, ticker o `published_at`.
- **Timestamp futuri: zero** (`published_at > created_at` → 0 righe).
- `extraction_method`: 185 `source_metadata`, 17 `org_lookup`. **Nessuna riga `resolver`**
  — il resolver deterministico continua a non emettere verdetti `RESOLVED` (**F-057**).
- Mapping rilevanza: 84 `ISSUER_SPECIFIC`, **118 `TAG_UNCONFIRMED`**, 0 `SECTOR_MACRO`,
  0 `FALSE_ENTITY_MATCH`. Il 58% delle attribuzioni resta non confermata.
- Copertura effective-timely: **46 ticker su 96 (47,9%)**; 37 simboli di watchlist con zero news.
- Fan-out: 122 articoli unici → 202 righe (80 mapping extra). Il 63,2% delle righe dei candidati
  miss viene da articoli multi-ticker.

### 4.7 Top news per impatto sul segnale

| Ora | Ticker | Score | Titolo (troncato) | Esito |
|---|---|---|---|---|
| 16:15 | AZN | **+0,566** | FDA approval | BUY 16:22 |
| 14:27 | QCOM | **+0,578** | (annuncio prodotto) | scartata da anti-pyramiding |
| 14:15 | HOOD | +0,420 | espansione bull case | BUY 14:22 (signal 9867, 0,414) |
| 15:24 | SPCX | +0,420 | Pivotal Research initiation | BUY 15:37 |
| 13:54 | NVO | +0,409 | Phase 3 positivi | BUY 14:07 |
| 18:50 | SPCX | +0,369 | FCC apre spettro | RI-BUY 18:52 |
| 17:51 | NVDA | +0,266 | dichiarazione CEO su AGI | BUY 17:52 (via velocity boost) |
| 17:38 | NFLX | **−0,420** | — | nessuna azione (S4 long-only) |

### 4.8 Problemi trovati — news

1. **[DAY-003]** 131 articoli scartati stale dopo ~23 h in coda.
2. GDELT scarta il 99,0% di quello che raccoglie per assenza di ticker (1.915/1.934).
3. Contatore `duplicates` incoerente col denominatore (F-007).
4. Un articolo content-mill («How To Trade SPY, QQQ, AAPL, MSFT, NVDA, GOOGL, META, And TSLA»)
   fanned-out su 8 ticker, tutti scorati **0,000** — 8 righe di rumore (F-012/F-066).
5. Attribuzione ticker non confermata sul 58% delle righe (F-057).

**Confidenza dell'analisi news: Alta.** Tutte le cifre vengono da `news_log`,
`ingestion_stats_daily`, `news_queue_drops` e `stale_drop_metrics_daily` incrociate fra loro.

---

## 5. Tabella performance modelli LLM

### 5.1 Chiamate e affidabilità

| Modello | risposte persistite | eligible | timeout Ollama | rate limit | polarity media | confidence media | σ(polarity) |
|---|---|---|---|---|---|---|---|
| glm-5.2:cloud | 179 | 77 (43,0%) | 31 | 4 | +0,1126 | 0,3774 | 0,2688 |
| gpt-oss:20b-cloud | 177 | 77 (43,5%) | 33 | 4 | +0,1044 | 0,4707 | 0,2901 |
| finbert (fallback) | — | — | — | — | — | — | — |
| **Totale** | **356** | 154 | **64** | **8** | | | |

Tasso di successo delle chiamate: 356 / (356+64+8) = **83,2%**.
**Refusal / output non parsabile: 0** (`ingestion_stats_daily.parse_fail = 0`, nessun errore di
parse nei log).
**Latenza per chiamata: non persistita** — vedi §12.

### 5.2 Provenienza dei 214 segnali

| model_id | n | quota |
|---|---|---|
| `ensemble:glm-5.2:cloud+gpt-oss:20b-cloud` | 134 | 62,6% |
| `single:gpt-oss:20b-cloud` | 39 | 18,2% |
| `finbert` | 29 | 13,6% |
| `single:glm-5.2:cloud` | 12 | 5,6% |
| **fallback_used = true** | **80** | **37,4%** |

Pesi ensemble in vigore (`ensemble:weights:current`): glm-5.2 0,70 / gpt-oss 0,30, `source: auto_apply`.
Coppia attiva (`config:sentiment_llm_models`): `glm52,gptoss` — conforme a CLAUDE.md.

### 5.3 Distribuzione degli score (polarity × confidence)

| Metrica | Valore |
|---|---|
| n | 214 |
| media | +0,0631 |
| min / max | −0,420 / +0,578 |
| **≥ +0,30 (gate)** | **20 (9,3%)** |
| ≤ −0,30 | 3 (1,4%) |
| \|score\| < 0,05 («thin») | **106 (49,5%)** |
| esattamente 0,000 | 41 (19,2%) |

Metà dei segnali della giornata è indistinguibile da zero.

### 5.4 Disaccordo fra modelli

Segnali con `ensemble_std > 0,20`: **12**.

| Ticker | score finale | ensemble_std | polarity glm | polarity oss |
|---|---|---|---|---|
| T | — | — | +0,35 | **−0,30** |
| QQQ | — | — | +0,05 | +0,65 |
| AMZN | +0,026 | 0,389 | +0,25 | **−0,30** |
| GE | +0,028 | 0,389 | −0,15 | **+0,40** |
| VZ | **+0,244** | 0,389 | +0,15 | +0,70 |
| PLTR | −0,023 | 0,354 | +0,15 | **−0,35** |
| MRVL | +0,291 | 0,283 | — | — |
| QCOM | −0,154 | 0,269 | — | — |

Cinque coppie hanno **segno opposto**. `ensemble_std` non è mai un gate: viene solo persistito
(**F-037**). VZ arriva a score +0,244 partendo da 0,15 vs 0,70 senza che la divergenza abbia
alcun effetto.

### 5.5 Verifica funzionale

| Domanda | Risposta | Evidenza |
|---|---|---|
| L'output LLM è validato prima del signal store? | **Parzialmente.** Parse JSON sì (0 parse_fail); enum e range **no** — nessuna normalizzazione persistita | F-055, `llm_responses` |
| L'ensemble gestisce la varianza alta? | **No.** `ensemble_std` calcolato e scritto, mai usato come gate | F-037, 12 casi oggi |
| Le news duplicate pesano più volte? | **Sì, oggi 12 volte** — e non per fan-out ma per re-scoring | **[DAY-001]** |
| La stessa news può generare segnali multipli? | **Sì** — 12 gruppi `news_log_id` con 2 righe ciascuno | **[DAY-001]** |
| Confidence bassa riduce il peso? | **Sì.** `score = polarity × confidence` verificato su tutte le righe | `sentiment.py` |
| I modelli sono chiamati offline/background? | **Sì.** Coda `inference`, `worker-inference` concurrency=1; il ciclo portfolio legge solo dal DB | `celery_app.py`, worker log |
| Rischio che un'allucinazione entri in decisione? | **Mitigato ma non nullo.** Ensemble a 2 modelli, `SKIP_FALLBACK` esclude i single-model dal ranking BUY (15 volte oggi), ma nessun supervisor agent e nessun gate di varianza | `execution_decisions` |

**Tutti e 7 i BUY della giornata provengono da segnali ensemble, nessuno da fallback.** Questo è
il comportamento corretto e va detto: la guardia #108 ha funzionato 15 volte su 15.

---

## 6. Tabella segnali finali per ticker

Ticker con almeno un \|score\| ≥ 0,25 (22 su 59 con segnale):

| Ticker | n segnali | max | min | fallback | Sopra gate? | Azione |
|---|---|---|---|---|---|---|
| QCOM | 7 | **+0,578** | −0,154 | 2 | sì | BUY 14:07 → SELL 16:52 |
| AZN | 2 | **+0,566** | +0,423 | 0 | sì | BUY 16:22 (aperta) |
| VZ | 5 | +0,560 | −0,240 | 3 | sì | nessuna |
| INTC | 5 | +0,498 | −0,165 | 1 | sì | nessuna |
| XLE | 3 | +0,487 | 0,000 | 0 | sì | SKIP_PYRAMIDING |
| QQQ | 5 | +0,455 | −0,277 | 3 | sì | SKIP_STALE |
| XOM | 2 | +0,431 | +0,193 | 1 | sì | SKIP_PYRAMIDING |
| HOOD | 8 | +0,420 | +0,012 | 2 | sì | BUY 14:22 → SELL 16:52 |
| SPCX | 9 | +0,420 | −0,031 | 2 | sì | BUY 15:37 → SELL 18:07 → BUY 18:52 |
| NVO | 1 | +0,409 | +0,409 | 0 | sì | BUY 14:07 (aperta) |
| CVX | 2 | +0,399 | +0,233 | 0 | sì | nessuna (FIX-D preserved) |
| ORCL | 6 | +0,395 | −0,100 | 2 | sì | nessuna |
| MRVL | 1 | +0,291 | +0,291 | 0 | no | SKIP_PYRAMIDING |
| AVGO | 2 | +0,288 | +0,174 | 0 | no | nessuna |
| AMAT | 2 | +0,267 | +0,051 | 0 | no | nessuna |
| NVDA | 10 | +0,266 | −0,150 | 4 | **via boost** | BUY 17:52 → SELL 19:37 |
| NOW | 1 | +0,260 | +0,260 | 0 | no | nessuna (fan-out, titolo su Robinhood) |
| MRK | 3 | +0,258 | +0,150 | 2 | no | nessuna |
| XLV | 4 | +0,006 | **−0,300** | 2 | ribassista | **nessuna azione** |
| F | 2 | +0,001 | **−0,299** | 1 | ribassista | nessuna azione |
| NFLX | 2 | 0,000 | **−0,420** | 1 | ribassista | nessuna azione |
| IWM | 1 | **−0,303** | −0,303 | 0 | ribassista | nessuna azione |

**Imbuto S4 aggregato sui 24 cicli:**

| Stadio | Totale | Note |
|---|---|---|
| Segnali valutati (`last 96h`) | 864 letture | somma per ciclo |
| Scartati `entry-freshness` (news > 2 h, solo simboli non detenuti, #150) | **451** | |
| Scartati fallback dal ranking BUY (#108) | 97 | |
| Scartati `stale` (> 4 h) | 132 | |
| Preservati da FIX-D (stale ma posizione aperta, nessun contro-segnale) | 43 | |
| **Segnali freschi caricati** | **775** | |
| **Scartati dal gate 0,300** | **644 (83,1%)** | = 644 righe `SKIP_THRESHOLD` ✓ |
| **Sopravvissuti al gate** | **131 (16,9%)** | |
| BUY effettivi | 7 | |

Il conteggio dei drop nel log (644/775) coincide **esattamente** con le righe `SKIP_THRESHOLD` in
`execution_decisions`: la strumentazione del gate è affidabile.

---

## 7. Tabella ordini generati / eseguiti

Tutti gli ordini provengono da `portfolio-cycle` (`execution.engine=portfolio`; il worker legacy
ha loggato `skipped` ad ogni giro). Broker: **Alpaca paper**. Tutti market order, tutti `FILLED`,
**zero reject, zero cancel, zero ordini fuori orario, zero duplicati** (verificato:
`GROUP BY symbol, minute, decision HAVING COUNT(*)>1` → 0 righe).

| # | Decisione | Strategia | Ticker | Azione | Qty | Prezzo atteso | Prezzo fill | Slippage | Stato | Segnale (id/score) | Risk check | Anomalia |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 14:07:00 | S4 | QCOM | BUY | 8,1359 | 176,28 | **176,50** | +12,5 bp | FILLED | 9861 / +0,424 | gate ✓, pyramiding ✓, freshness ✓ | — |
| 2 | 14:07:00 | S4 | NVO | BUY | 31,3115 | — | 45,8611 | n/d | FILLED | 9854 / +0,409 | ✓ | — |
| 3 | 14:22:00 | S4 | HOOD | BUY | 11,5656 | 123,99 | **124,18** | +15,3 bp | FILLED | 9867 / +0,414 | ✓ | — |
| 4 | 14:22:00 | S4 | CRM | **SELL** | 5,1797 | — | 247,19 | n/d | FILLED | **NULL** `[no_signal]` | isteresi 2 cicli ✓ | signal_id NULL (F-011) |
| 5 | 15:37:00 | S4 | SPCX | BUY | 9,4232 | 152,80 | 152,80 | 0,0 bp | FILLED | 9916 / +0,420 | ✓ | — |
| 6 | 16:22:00 | S4 | AZN | BUY | 8,9792 | — | 160,13 | n/d | FILLED | 9957 / +0,566 | ✓ | — |
| 7 | 16:52:00 | S4 | HOOD | **SELL** | 11,5656 | — | 121,09 | n/d | FILLED | **NULL** `[below_entry_gate]` sig. 0,4 h score +0,132 | hold 150 min ✓, isteresi ✓ | signal_id NULL |
| 8 | 16:52:00 | S4 | QCOM | **SELL** | 8,1359 | — | 174,47 | n/d | FILLED | **NULL** `[below_entry_gate]` sig. 0,3 h score **+0,284** | hold 165 min ✓ | **[DAY-006]** |
| 9 | 17:52:00 | S4 | NVDA | BUY | 6,3715 | 225,91 | **225,98** | +3,1 bp | FILLED | 10014 / **+0,266** | gate passato via boost | **[DAY-002]** |
| 10 | 18:07:00 | S4 | SPCX | **SELL** | 9,4232 | — | 152,84 | n/d | FILLED | **NULL** `[below_entry_gate]` score **+0,000** | hold 150 min ✓ | **[DAY-005]** |
| 11 | 18:52:00 | S4 | SPCX | **BUY** | 9,3552 | 153,66 | 153,64 | −1,3 bp | FILLED | 10031 / +0,369 | ✓ | **[DAY-005]** ri-entrata a 45 min |
| 12 | 19:37:00 | S4 | NVDA | **SELL** | 6,3715 | — | 225,64 | n/d | FILLED | **NULL** `[below_entry_gate]` score +0,219 | hold 105 min = primo beat legale | `hold_minimum_expiry` (#430) |

**Decisioni non eseguite** (`execution_decisions`, 682 righe totali):

| Decisione | n | Note |
|---|---|---|
| SKIP_THRESHOLD | 644 | 83,1% dei segnali freschi |
| SKIP_FALLBACK | 15 | #108, single-model esclusi dal ranking BUY |
| SKIP_PYRAMIDING | 8 | P0-05; SNOW, QCOM ×2, XOM, XLE, HOOD, SPCX, MRVL |
| SKIP_STALE | 3 | QQQ 91,1 h, XLE 90,9 h, XLK 90,9 h |
| BUY | 7 | |
| SELL | 5 | |

**Copertura `signal_id`:** 676/682 (99,1%). Mancante su **5/5 SELL** e 1/8 SKIP_PYRAMIDING —
il dossier stesso segnala `regressions: ["SELL","SKIP_PYRAMIDING"]` (**F-011**).

**Cap / limiti applicati:** `constraints_fired: []` su tutti i 24 cicli — nessun limite di
esposizione o settore è scattato. Esposizione lorda 32,7%, HHI 0,0263, drawdown 1,24% contro il
kill-switch a 5%: **circuit breaker non attivo, correttamente**. `regime_mult = 0,70` su tutte le
decisioni. Peso target 2,0% del NAV per posizione S4 (≈2.200 $), coerente col design.

**`portfolio_cycles.orders_count`** (3–7 per ciclo, 113 in totale) conta gli ordini *target*, non
quelli inviati (12 reali): telemetria fuorviante (**F-014**).

---

## 8. Tabella PnL / rendimento

### 8.1 NAV

| Voce | Valore |
|---|---|
| Equity chiusura precedente (09-04) | 109.973,67 $ |
| NAV 13:30 (apertura) | 110.073,54 $ |
| NAV 20:00 (chiusura) | **109.912,36 $** |
| **Variazione di giornata** | **−61,31 $ (−0,056%)** |
| Cash | 73.914,46 $ |
| Esposizione lorda | 32,75% |
| Non realizzato a chiusura | +1.240,65 $ |
| Posizioni aperte | 45 |
| Drawdown corrente | 0,66% (snapshot) / 1,24% (`risk_reports` 22:30) |

### 8.2 P&L realizzato (5 chiusure, tutte S4)

| Trade | Ticker | Ingresso | Uscita | Tenuta | Gross | Costi | **Net** | Motivo |
|---|---|---|---|---|---|---|---|---|
| 979 | CRM | 09-03 18:37 @267,51 | 09-08 14:22 @247,19 | 115,8 h | −105,25 | 0,76 | **−106,01** | `portfolio_sell` [no_signal] |
| 984 | HOOD | 14:22 @124,18 | 16:52 @121,09 | 2,50 h | −35,74 | 0,79 | **−36,53** | `portfolio_sell` [below_entry_gate] |
| 982 | QCOM | 14:07 @176,50 | 16:52 @174,47 | 2,75 h | −16,52 | 0,79 | **−17,31** | `portfolio_sell` [below_entry_gate] |
| 987 | NVDA | 17:52 @225,98 | 19:37 @225,64 | 1,75 h | −2,17 | 0,29 | **−2,45** | `hold_minimum_expiry` |
| 985 | SPCX | 15:37 @152,80 | 18:07 @152,84 | 2,50 h | +0,38 | 1,51 | **−1,14** | `portfolio_sell` [below_entry_gate] |
| | | | | | **−159,29** | **4,14** | **−163,44** | |

**Attribuzione per strategia: S4 −163,44 $, S1 0,00 $** (S1 non ha ribilanciato: gate mensile
chiuso, ultimo ribilanciamento 2026-09-01, conforme a #185).

**Posizioni aperte prima del 2026-09-08:** una sola chiusura (CRM, aperta 09-03) → **−106,01 $**,
il **64,9% della perdita realizzata della giornata**.
**Posizioni aperte il 2026-09-08 e chiuse in giornata:** 4 → **−57,42 $**.

### 8.3 Mark-to-EOD delle 7 entrate di giornata

| Ticker | Ora | Prezzo ingresso | MTM EOD | Quota del movimento già avvenuta prima del segnale | Rend. titolo |
|---|---|---|---|---|---|
| NVO | 14:07 | 45,8611 | **−21,95** | 0,669 | −3,09% |
| QCOM | 14:07 | 176,50 | **−19,61** | 0,618 | +3,17% |
| HOOD | 14:22 | 124,18 | **−79,11** | 0,115 | −3,91% |
| SPCX | 15:37 | 152,80 | **+6,31** | 0,849 | +3,73% |
| AZN | 16:22 | 160,13 | −0,81 | **0,977** | −1,63% |
| NVDA | 17:52 | 225,98 | −1,59 | **0,966** | −2,01% |
| SPCX | 18:52 | 153,64 | −1,59 | **1,038** | +3,73% |
| **Totale** | | | **−118,35** | mediana **0,849** | |

Su 4 entrate su 7 **oltre l'84% del movimento del titolo era già avvenuto** quando il segnale è
stato scorato; su SPCX-bis il 104% (il movimento era finito) — **F-030**.

### 8.4 Costi e slippage

Commissioni Alpaca paper: **0**. Costi modellati (`cost_usd`): 4,14 $ sulle 5 chiusure.
`cost_bps` 1,77–10,27 con `spread_cost_bps` 1,5–10,0 e `impact_cost_bps` ≈0,27.

**Slippage reale osservato** dal ledger `s4_lifecycle_events`
(`fill_price` vs `first_executable_price`):

| Ticker | atteso | fill | Δ | bp |
|---|---|---|---|---|
| HOOD | 123,99 | 124,18 | +0,19 | **+15,3** |
| QCOM | 176,28 | 176,50 | +0,22 | **+12,5** |
| NVDA | 225,91 | 225,98 | +0,07 | +3,1 |
| SPCX #1 | 152,80 | 152,80 | 0,00 | 0,0 |
| SPCX #2 | 153,66 | 153,64 | −0,02 | −1,3 |

Su HOOD e QCOM lo slippage d'ingresso da solo (2,20 $ e 1,79 $) **supera il costo di andata e
ritorno modellato** (0,79 $ ciascuno): il modello di costo sottostima di ~2,5–3× su questi nomi.
`trades.slippage_est` è una **copia byte-identica** di `cost_usd` su tutte e 5 le righe: lo
slippage reale, che il ledger misura, non viene mai scritto lì (**F-015**).

### 8.5 Effetto netto delle uscite `below_entry_gate` (controfattuale corto)

| Ticker | Net realizzato | MTM EOD se tenuta | Δ uscita |
|---|---|---|---|
| HOOD | −36,53 | −79,11 | **+42,58** |
| QCOM | −17,31 | −19,61 | **+2,30** |
| NVDA | −2,45 | −1,59 | −0,86 |
| SPCX | −1,14 | +6,31 | **−7,45** |
| **Totale** | | | **+36,57** |

**Il churn di oggi ha fatto guadagnare 36,57 $.** Questo non assolve il meccanismo — è la
sua varianza, non il suo valore atteso — ma va registrato perché contraddice la lettura per
default.

---

## 9. Analisi correttezza buy/sell

| Controllo | Esito | Evidenza |
|---|---|---|
| BUY generati solo quando consentito | **✓** | 7/7 sopra gate (uno via velocity boost), 7/7 ensemble non-fallback, 7/7 freshness < 2 h, anti-pyramiding applicato 8 volte |
| SELL / exit generati correttamente | **✓ con riserva** | 5/5 hanno `reason` esplicito e classificazione; ma `signal_id` NULL su 5/5 |
| Stop-loss rispettati | **N/A per design** | `risk.stop_loss: 0.0` dal 2026-07-15 (decisione documentata in `trading.yaml:167-181`). `stop_decisions` vuota dal 2026-07-14: **non è un guasto**. Shadow attivo: 324 righe `would_breach_fixed`, 24 `d_hard_breached` (solo AMAT) |
| Signal flip rispettato | **✓** | Nessun BUY su score negativo; i 4 segnali ≤ −0,30 non hanno prodotto azione (S4 long-only) |
| Max holding days rispettato | **✓** | Nessuna posizione oltre il limite; CRM chiusa a 4,8 giorni |
| `hold_minimum_minutes` (90) rispettato | **✓** | Tenute 105, 150, 150, 165 min — tutte ≥ 90. NVDA a 105 min = primo beat legale, marcato `hold_minimum_expiry` (#430), comportamento corretto |
| `exit_persistence_cycles` (2) rispettato | **✓** | Log: «Exit hysteresis (2 cycles): held 1 position(s) flagged for exit: ['CRM']» prima della SELL di CRM |
| Rebalance band rispettata | **✓** | S1 gate mensile chiuso, 42 posizioni tenute senza ri-decisione (#185) |
| Ordini duplicati | **✓ nessuno** | `GROUP BY symbol, minute, decision HAVING COUNT(*)>1` → 0 righe |
| Ordini contrari ravvicinati | **⚠ 1 caso** | SPCX SELL 18:07 → BUY 18:52 (45 min). Con rationale esplicito su entrambi i lati, ma senza cooldown di ri-entrata — **[DAY-005]** |
| Roundtrip < 30 min | **✓ nessuno** | minimo 105 min |
| Pyramiding (>3 BUY consecutivi senza SELL) | **✓ nessuno** | guard P0-05 attivo, 8 blocchi |
| SELL con sentiment positivo (bug A5) | **⚠ 1 caso limite** | QCOM venduta su score **+0,284** — positivo ma sotto il gate 0,300. Semanticamente coerente col meccanismo, ma la soglia di uscita coincide con quella d'ingresso |
| Ordini su ticker non consentiti | **✓ nessuno** | tutti in watchlist |
| Ordini fuori orario | **✓ nessuno** | 14:07–19:52, tutto dentro 13:30–20:00 |
| Trade su dati stale | **✓ nessuno** | `SKIP_STALE` ×3, freshness gate ×451 |
| Trade su output LLM non valido | **✓ nessuno** | `SKIP_FALLBACK` ×15, 0 parse_fail |
| Trade con circuit breaker attivo | **✓ N/A** | drawdown 1,24% vs 5% |
| Strategia disabilitata | **✓** | `execution.engine=portfolio`; legacy worker `skipped` a ogni giro |
| Paper/live coerente | **✓** | `broker_environment='paper'`, `mode='paper'`, `source='alpaca_paper'` su tutti i 137 snapshot |
| Idempotenza retry Celery | **⚠ parziale** | Guard `SIGNAL_DUPLICATE_SKIP` funziona (48 blocchi). Ma il ciclo sentiment **non è idempotente** — **[DAY-001]** |
| Riconciliazione ordini/fill/posizioni | **✓** | 19 `ENTRY_RECONCILIATION` FILLED, 19/19 `reconstructible`, `fill_price` presente su tutte |

> **Avvertenza `exit_mechanism` (#184).** Le 5 righe SELL del 2026-09-08 sono **post-fix**:
> portano etichette osservate (`no_signal`, `below_entry_gate`) accompagnate dal testo completo
> del motivo, non dedotte dall'età dell'ultimo segnale. Nessuna riga `expired`/`whipsaw` in
> giornata, quindi **nessun conteggio di questo report è una stima per età**. Le righe storiche
> antecedenti al fix restano interpretabili solo secondo `docs/exit_mechanism_labels.md`.

---

## 10. Anomalie trovate

### [DAY-001] Re-scoring non idempotente dopo `SoftTimeLimitExceeded`: 12 articoli scorati due volte

* **Tipo:** Bug
* **Area:** LLM / Data
* **Evidenza:**
  * file/log/tabella: `logs/containers/worker-inference-2026-09-08.log:31682,31950`; `sentiment_signals`; `src/workers/sentiment.py:1196-1210,1211-1231,1374`
  * timestamp: 2026-09-08 15:08:56 → 15:20:24 → 15:23:16 → 15:45:44 UTC
  * snippet/query:
    ```
    15:20:24 ERROR run_sentiment_worker[6d1b5306…] raised unexpected: SoftTimeLimitExceeded()
    15:23:16 WARNING Recovering 12 stuck items from news:processing into news:queue
    ```
    ```sql
    SELECT news_log_id, COUNT(*) FROM sentiment_signals
    WHERE generated_at::date='2026-09-08' GROUP BY 1 HAVING COUNT(*)>1;
    -- 12 gruppi, 12 segnali in eccesso (news_log_id 9902-9913)
    ```
* **Descrizione:** `run_sentiment_worker` rimuove gli item da `news:processing` solo con una
  `delete()` alla **fine** del run (`sentiment.py:1374`), mentre i segnali vengono scritti
  **articolo per articolo** durante il batch. Quando il soft time limit (780 s) uccide il task a
  metà, gli articoli già scorati e persistiti restano in `news:processing`; il blocco di
  crash-recovery del run successivo li rimette in `news:queue` e li fa ri-scorare. Non esiste
  alcuna chiave di idempotenza né un controllo contro `sentiment_signals.news_log_id` già presente.
  I 12 articoli hanno prodotto risultati **diversi** al secondo giro (AAPL 0,2287 → 0,2298;
  GOOGL `finbert` 0,0098 → `single:gpt-oss` 0,060; SPY `single:glm` → `ensemble`), e poiché il
  ranker prende il segnale più recente per simbolo (F-023/F-056), è la **seconda** riga a diventare
  autoritativa.
* **Impatto:** contaminazione diretta della serie osservata. Ogni IC, copertura articoli, funnel e
  conteggio di segnali calcolato su `sentiment_signals` conta due volte gli stessi articoli, con
  valori diversi. In una giornata con volatilità dei tempi di risposta Ollama (64 timeout oggi) il
  soft time limit è raggiungibile di routine. Nessun ordine è stato generato dai 12 duplicati
  (score tutti ≈ 0), quindi il costo di oggi è di sola evidenza — ma la finestra di osservazione
  che si chiude il 2026-09-28 è esattamente ciò che viene inquinato.
* **Severità:** High
* **Confidenza:** High
* **Azione consigliata:** ticket di **correttezza** (esente dal freeze): rimuovere l'item da
  `news:processing` con `LREM` **subito dopo** la scrittura del suo segnale, invece della `delete()`
  finale di batch; in subordine, dedup difensiva su `(news_log_id, model_id)` prima dell'insert.
  Nessuna soglia toccata.
* **Test/monitor consigliato:** test che simuli `SoftTimeLimitExceeded` a metà batch e verifichi
  che il run successivo non riscriva segnali per `news_log_id` già presenti; monitor giornaliero
  `COUNT(*) FROM (SELECT news_log_id FROM sentiment_signals GROUP BY 1 HAVING COUNT(*)>1)` con
  soglia 0.

---

### [DAY-002] Il punteggio persistito nella Decision Log non è quello valutato al gate

* **Tipo:** Bug
* **Area:** Signal / Ops
* **Evidenza:**
  * file/log/tabella: `execution_decisions` id 19580; `sentiment_signals` id 10014;
    `src/workers/portfolio_scheduler.py:4306-4326`; `src/config.py:306-310`
  * timestamp: 2026-09-08 17:52:00 UTC
  * snippet/query:
    ```sql
    SELECT symbol, decision, signal_score FROM execution_decisions WHERE id=19580;
    -- NVDA | BUY | 0.2662500000000396
    ```
    ```
    17:52:03 INFO Signal velocity: 9/38 symbols adjusted
    17:52:03 INFO S4 feedback gate: dropped 34/38 signals below threshold 0.300
    ```
    `feedback:entry_threshold:S4` = `0.3`; `SIGNAL_VELOCITY_BOOST` = 0,20 → 0,26625 × 1,20 = **0,3195 ≥ 0,300**
* **Descrizione:** il gate confronta `signals_df["score"]` **dopo** l'applicazione del
  moltiplicatore di signal-velocity (`portfolio_scheduler.py:4315-4322`), ma
  `execution_decisions.signal_score` riceve il punteggio **grezzo**. Il Decision Log mostra quindi
  un BUY a 0,266 con gate dichiarato a 0,300: una contraddizione apparente risolvibile solo
  leggendo i log del worker, che non sopravvivono al redeploy (F-027). Il moltiplicatore applicato
  al singolo simbolo non è persistito da nessuna parte.
* **Impatto:** stessa classe di difetto di #169 e #467. Qualunque script di misura che ricostruisca
  «quali segnali hanno passato il gate» leggendo `execution_decisions.signal_score` **diverge dalla
  regola di produzione** e produce numeri sbagliati in modo silenzioso. Oggi riguarda 9 simboli su
  38 nell'ultimo ciclo e almeno 1 ordine reale.
* **Severità:** High
* **Confidenza:** High
* **Azione consigliata:** ticket di **correttezza**: persistere il punteggio effettivamente
  valutato al gate (o, in aggiunta, il moltiplicatore applicato) su `execution_decisions` e sul
  ledger degli intent S4. Nessuna soglia, nessun peso, nessun comportamento d'ordine cambia.
* **Test/monitor consigliato:** invariante giornaliera — per ogni riga `BUY`, il punteggio
  registrato deve essere ≥ soglia attiva **oppure** deve esistere un campo che spiega la differenza;
  0 violazioni ammesse.

---

### [DAY-003] 131 articoli scartati `stale` all'apertura dopo ~23 ore in coda

* **Tipo:** Anomalia (strutturale)
* **Area:** News / Ops
* **Evidenza:**
  * file/log/tabella: `news_queue_drops`, `stale_drop_metrics_daily`; `src/workers/celery_app.py:78-80`
  * timestamp: 2026-09-08 13:00–14:00 UTC
  * snippet/query:
    ```sql
    SELECT date_trunc('hour',dropped_at) h, COUNT(*), AVG(age_hours), 
           AVG(EXTRACT(EPOCH FROM (dropped_at-raw_ingested_at))/3600)
    FROM news_queue_drops WHERE dropped_at::date='2026-09-08' AND discarded_reason='stale'
    GROUP BY 1;
    -- 13:00 | 131 | 23.6 | 23.2
    ```
    `stale_drop_metrics_daily`: `stale_drop_share` 0,290 > `alert_threshold` 0,25, `alert_required = true`,
    `went_stale_in_queue` 130/157, `avg_queue_wait_hours` 19,40
* **Descrizione:** il worker WebSocket ingerisce 24/7 in `news:queue`, ma il consumatore è
  schedulato `hour="14-21", day_of_week="1-5"`. Le notizie della sera del 09-04 e dell'intero
  festivo 09-07 restano in coda ~23 ore e vengono scartate come `stale` (`MAX_NEWS_AGE_HOURS=2`)
  al primo drenaggio della mattina, **senza mai raggiungere un modello**. Sono il 24,2% di tutto
  ciò che è stato accodato da Alpaca in giornata. Il p50 di latenza di 20,8 min misurato in §4.3
  descrive solo i sopravvissuti: è una statistica condizionata alla sopravvivenza.
* **Impatto:** cecità sistematica su tutta la finestra overnight, pre-market e festiva — proprio
  quella in cui si concentrano earnings, FDA approval e annunci societari. L'alert **è** stato
  consegnato correttamente (Telegram 200 OK alle 22:55), quindi il problema è visibile, non ignoto.
* **Severità:** High
* **Confidenza:** High
* **Azione consigliata:** ticket. Il costo di oggi non è stimabile con segno determinato: i 7
  ingressi S4 della giornata hanno un MTM EOD aggregato di **−118,35 $**, quindi più ingressi non
  avrebbero ovviamente aiutato. **Non è una taratura**: la domanda è se il consumatore debba
  drenare la coda fuori seduta, non con quale soglia. Registrare per ricorrenza.
* **Test/monitor consigliato:** allarme quando `avg_queue_wait_hours` supera `MAX_NEWS_AGE_HOURS`,
  cioè quando la coda garantisce lo scarto per costruzione (oggi 19,4 h contro 2 h).

---

### [DAY-004] Finestra cieca 13:30–14:07 UTC: mercato aperto, nessun ciclo e nessuna ingestione

* **Tipo:** Bug
* **Area:** Ops
* **Evidenza:**
  * file/log/tabella: `src/workers/celery_app.py:80,153,164,186,226`; `portfolio_cycles`; `mobile_events`
  * timestamp: 2026-09-08 13:30:00–14:07:00 UTC
  * snippet/query: tutte le schedule operative usano `hour="14-21"` in UTC fisso. Primo
    `portfolio_cycles.timestamp` = 14:07:00. `mobile_events` alle 13:30:00: **critical** «Ciclo di
    portafoglio in ritardo» + warning «Segnali sentiment in ritardo».
* **Descrizione:** in EDT il NYSE apre alle 13:30 UTC, ma beat parte alle 14:00. I primi **37
  minuti** della seduta — la finestra a più alta dispersione — non hanno né ciclo di portafoglio né
  ingestione batch. Il sistema se ne accorge (l'incidente critical scatta puntuale) e poi lo
  richiude da solo alle 14:07. In EST (novembre–marzo) l'apertura è alle 14:30 e la finestra non
  esiste: il difetto è stagionale, il che spiega perché sopravvive.
* **Impatto:** oggi AZN aveva un segnale **+0,423 alle 13:31** — sopra il gate — e non ha potuto
  essere valutato fino alle 14:07. AZN è poi stata comprata alle 16:22 a 160,13, quando il 97,7%
  del movimento era già avvenuto. Il titolo ha chiuso a −1,63%: comprare prima avrebbe presumibilmente
  peggiorato, non migliorato, il risultato. Costo di oggi non determinabile nel segno.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** ticket di **correttezza** (l'incidente critical automatico ne dimostra
  già lo status di anomalia riconosciuta): derivare le finestre beat dal calendario Alpaca invece
  che da ore UTC fisse. Non è taratura — nessuna soglia cambia, cambia solo *quando* la stessa
  regola viene applicata.
* **Test/monitor consigliato:** test parametrizzato su una data EDT e una EST che verifichi che il
  primo ciclo cada entro 10 min dall'apertura restituita da `GetCalendarRequest`.

---

### [DAY-005] Churn SPCX: venduta a 152,84 e ricomprata a 153,64 dopo 45 minuti

* **Tipo:** Anomalia
* **Area:** Orders
* **Evidenza:**
  * file/log/tabella: `trades` id 985 e 988; `execution_decisions` id 19616 e 19725; `sentiment_signals` 9916, 10010, 10031
  * timestamp: 15:37 → 18:07 → 18:52 UTC
  * snippet/query:
    ```
    15:24 signal 9916  score +0.420  → BUY 15:37 @152.80
    17:46 signal 10010 score  0.000  → SELL 18:07 @152.84 [below_entry_gate]
    18:50 signal 10031 score +0.369  → BUY 18:52 @153.64
    ```
* **Descrizione:** la soglia d'uscita coincide con quella d'ingresso (0,300): non esiste banda
  morta, quindi un segnale che oscilla attorno al gate produce entrata → uscita → rientrata. Non
  esiste alcun cooldown di ri-entrata per S4 (`s1_reentry_cooldown_enabled: false` riguarda solo
  S1). Il guard `SIGNAL_DUPLICATE_SKIP` non interviene perché il segnale di rientrata ha un `id`
  diverso.
* **Impatto:** **costo misurato 9,04 $**. Tenendo la posizione dalle 15:37 a fine seduta il MTM
  EOD sarebbe stato **+6,31 $** (dossier `ingressi[SPCX@15:37].mtm_eod`); l'esito reale è
  −1,14 $ realizzati più −1,59 $ non realizzati = **−2,73 $**. Delta 9,04 $, di cui ~7,53 $ è il
  gap di prezzo pagato alla rientrata (0,80 $/azione × 9,42) e ~1,51 $ il costo di transazione
  aggiuntivo.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** **nessuna azione ora.** La banda morta e il cooldown sono taratura pura e
  restano congelati fino al 2026-09-28. Registrare per ricorrenza. Nota onesta: sull'intera
  giornata le uscite `below_entry_gate` hanno prodotto **+36,57 $** netti — SPCX è il caso peggiore,
  non quello tipico.
* **Test/monitor consigliato:** contatore giornaliero di sequenze BUY→SELL→BUY sullo stesso simbolo
  entro la seduta, con il delta di prezzo pagato alla rientrata.

---

### [DAY-006] QCOM venduta su segnale positivo a 0,284 mentre 7 minuti prima valeva 0,382

* **Tipo:** Anomalia
* **Area:** Signal / Orders
* **Evidenza:**
  * file/log/tabella: `sentiment_signals` id 9961, 9965, 9967; `execution_decisions` id 19459; `trades` id 982
  * timestamp: 2026-09-08 16:25–16:52 UTC
  * snippet/query:
    ```
    16:25:20  id 9961  ensemble  score +0.382   (sopra il gate)
    16:29:49  id 9965  single:glm score +0.293  (fallback)
    16:32:34  id 9967  ensemble  score +0.284   (sotto il gate)
    16:52:00  SELL [below_entry_gate] "age=0.3h … score=+0.284": weight 0.0%, position closed
    ```
* **Descrizione:** S4 usa **solo il segnale più recente per simbolo** (F-023/F-056). Tre segnali
  freschi entro 7 minuti, con dispersione 0,382 → 0,293 → 0,284, e l'ultimo — sotto il gate di
  0,016 — decide la liquidazione dell'intera posizione. Il segnale è ancora **positivo**: la
  posizione viene chiusa non per un contro-segnale ma perché la soglia d'uscita coincide con quella
  d'ingresso. Ricorre lo stesso giorno su HOOD (16:10 `single` 0,180 → 16:25 `ensemble` 0,132).
* **Impatto:** su questa uscita specifica il risultato è stato **favorevole**: −17,31 $ realizzati
  contro −19,61 $ se tenuta a fine seduta, quindi **+2,30 $**, al netto di 0,79 $ di costo
  aggiuntivo. Il difetto è nel meccanismo — un singolo campione a 7 minuti di distanza decide
  ~2.200 $ di esposizione — non nell'esito di oggi.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** **nessuna azione ora** (aggregazione multi-segnale e banda d'uscita sono
  taratura). Registrare per ricorrenza su F-023.
* **Test/monitor consigliato:** loggare, su ogni SELL `below_entry_gate`, il numero di segnali
  freschi disponibili per quel simbolo e la loro dispersione — oggi non è ricostruibile dal DB.

---

### [DAY-007] Tre alert Telegram respinti con 400 Bad Request, incluso l'unico su AMAT a −22,8%

* **Tipo:** Bug
* **Area:** Ops / Risk
* **Evidenza:**
  * file/log/tabella: `logs/containers/worker-2026-09-08.log:3828-3831, 3969-3972, 5776-5778`
  * timestamp: 14:07:07, 14:30:00, 19:00:01 UTC
  * snippet/query:
    ```
    14:07:07 WARNING #161: AMAT unprotected at -22.8% (qty 0.8571, status sub_one_share)
    14:07:07 POST …/sendMessage "HTTP/1.1 400 Bad Request"
    14:07:07 WARNING TelegramNotifier: Failed to send alert: Client error '400 Bad Request'
    ```
* **Descrizione:** il canale Telegram **funziona** (lo stale-drop alert delle 22:55 passa con
  200 OK): il 400 è specifico ai messaggi di `#161` e `loss-feedback`, quindi è un difetto di
  formato del payload, non di connettività. L'alert su AMAT è stato **loggato 24 volte** (una per
  ciclo) contro il «uno per simbolo al giorno» dichiarato in `trading.yaml:182-186`, e non compare
  in `mobile_events`: l'unico canale è quello che fallisce.
* **Impatto:** AMAT è al **−22,7% dall'ingresso** con `qty 0,8571 < 1` — non proteggibile da uno
  stop broker (F-022) — ed è l'unico simbolo che ha sfondato il `d_hard` shadow oggi (24 righe
  `d_hard_breached`). Esattamente la condizione che `trading.yaml:178-180` indica come trigger di
  revisione, e nessun essere umano l'ha ricevuta. Difetto di **osservabilità**, costo non stimabile.
* **Severità:** High
* **Confidenza:** High
* **Azione consigliata:** ticket. Corretto anche il fan-out: dedup «uno per simbolo al giorno» e
  fallback su `mobile_events` quando Telegram respinge.
* **Test/monitor consigliato:** test di contratto sul payload Telegram di ogni notifier; contatore
  di alert generati vs consegnati con soglia sulla differenza.

---

### [DAY-008] Il breaker di fallback spara ma il callback muore in un'eccezione asyncio

* **Tipo:** Bug
* **Area:** LLM / Ops
* **Evidenza:**
  * file/log/tabella: `logs/containers/worker-inference-2026-09-08.log:31673-31677`; `src/workers/sentiment.py:1110`
  * timestamp: 2026-09-08 15:08:56 UTC
  * snippet/query:
    ```
    15:08:56 INFO All ensemble models timed out for GOOGL, using FinBERT fallback
    15:08:56 WARNING Fallback breaker alert callback failed for count=3:
             asyncio.run() cannot be called from a running event loop
    15:08:56 RuntimeWarning: coroutine 'TelegramNotifier.send_fallback_alert' was never awaited
    ```
* **Descrizione:** ricorrenza esatta di F-071. Il breaker rileva correttamente 3 fallback
  consecutivi, ma `send_fallback_alert` è invocata con `asyncio.run()` dentro un event loop già
  attivo: l'eccezione viene catturata e degradata a warning, la coroutine non è mai attesa.
* **Impatto:** nella giornata con **64 timeout Ollama** e **37,4% di segnali in fallback**, il
  meccanismo pensato per segnalare il degrado dell'ensemble non ha prodotto alcuna allerta.
  Osservabilità, costo non stimabile.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** ticket già tracciato da F-071; sostituire `asyncio.run()` con uno
  scheduling compatibile con il loop corrente.
* **Test/monitor consigliato:** test che invochi il breaker da dentro un event loop e asserisca
  che l'alert venga effettivamente inviato.

---

### [DAY-009] Il token bearer del protocollo forense è rifiutato su tutti gli endpoint REST

* **Tipo:** Bug
* **Area:** Frontend / Ops
* **Evidenza:**
  * file/log/tabella: `logs/containers/api-2026-09-08.log`; risposta API
  * timestamp: sessione di analisi 2026-09-09
  * snippet/query:
    ```
    curl -H "Authorization: Bearer eJvMeu…" http://localhost:8001/api/positions
    → {"detail":"Invalid or expired JWT token"}
    ```
    8 risposte 403 nel log (`/api/positions` ×2, `/api/orders` ×2, `/api/trades`, `/api/signals`,
    `/api/decisions`, `/api/performance/latest`) contro 13.183 risposte 200 dal resto del traffico.
* **Descrizione:** dodicesima ricorrenza di F-041. Il token fornito dal protocollo forense non è
  accettato da nessun endpoint. L'API è sana per tutti gli altri client.
* **Impatto:** l'intera FASE «RISORSE DISPONIBILI» del protocollo è inutilizzabile; questo report
  è costruito interamente da query SQL e log, cioè da una fonte diversa da quella prescritta. Se
  API e DB divergessero non ci sarebbe modo di accorgersene.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** ticket: rigenerare il token o allineare il protocollo forense al
  meccanismo di auth realmente in uso.
* **Test/monitor consigliato:** smoke test in CI che chiami i 5 endpoint del protocollo col token
  documentato e pretenda 200.

---

### [DAY-010] `slippage_est` è una copia di `cost_usd`, mentre lo slippage reale è 2,5× il modello

* **Tipo:** Bug
* **Area:** PnL
* **Evidenza:**
  * file/log/tabella: `trades`; `s4_lifecycle_events`
  * timestamp: 2026-09-08
  * snippet/query:
    ```sql
    SELECT id,symbol,slippage_est,cost_usd FROM trades WHERE exit_time::date='2026-09-08';
    -- SPCX 1.5128518072839094 | 1.5128518072839094   (identici su tutte e 5 le righe)
    ```
    ```sql
    SELECT symbol, first_executable_price, fill_price FROM s4_lifecycle_events
    WHERE observed_at::date='2026-09-08';
    -- HOOD 123.99 → 124.18 (+15.3 bp) ; QCOM 176.28 → 176.50 (+12.5 bp)
    ```
* **Descrizione:** ricorrenza di F-015, con una quantificazione nuova: il ledger
  `s4_lifecycle_events` **contiene già** il prezzo atteso e il prezzo di fill, quindi lo slippage
  reale è misurabile — ma `trades.slippage_est` continua a essere il costo modellato copiato tale
  e quale.
* **Impatto:** su HOOD lo slippage d'ingresso da solo vale 2,20 $ contro 0,79 $ di costo
  round-trip modellato; su QCOM 1,79 $ contro 0,79 $. Il modello sottostima di ~2,5–3× e il P&L
  economico che ne discende è ottimista in modo sistematico.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** ticket di **correttezza**: popolare `slippage_est` dal delta
  `fill_price − first_executable_price` già persistito, invece di duplicare `cost_usd`.
* **Test/monitor consigliato:** invariante `slippage_est != cost_usd` su ogni trade con un evento
  di lifecycle disponibile.

---

### [DAY-011] `signal_id` NULL su 5 SELL su 5

* **Tipo:** Bug
* **Area:** Signal / Orders
* **Evidenza:**
  * file/log/tabella: `execution_decisions`; `docs/evidence/dossier/2026-09-08.json → decision_signal_id_coverage`
  * timestamp: 2026-09-08
  * snippet/query: `by_reason_code.SELL = {rows: 5, with_signal_id: 0, fill_rate: 0.0, expected_fill_rate: "must_be_full"}`;
    `regressions: ["SELL","SKIP_PYRAMIDING"]`
* **Descrizione:** ventiduesima ricorrenza di F-011. La copertura complessiva è ottima (676/682 =
  99,1%) ma è concentrata: **tutte** le SELL sono prive del riferimento al segnale che le ha
  causate, e 1 SKIP_PYRAMIDING su 8. Il testo del `reason` cita lo score e l'orario di generazione,
  quindi l'informazione esiste — semplicemente non è in una colonna interrogabile.
* **Impatto:** la catena segnale → uscita → P&L non è ricostruibile con SQL sul lato uscite. Ogni
  analisi di attribuzione delle uscite deve fare parsing del testo del motivo, cosa che questo
  report ha dovuto fare.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** ticket di **correttezza**: propagare `signal_id` sul percorso di uscita.
* **Test/monitor consigliato:** l'invariante è già calcolata dal dossier; farla fallire il job
  invece di limitarsi a registrarla in `regressions`.

---

### [DAY-012] `ENTRY_RECONCILIATION` riemesso 19 volte per 7 ingressi

* **Tipo:** Anomalia
* **Area:** Data
* **Evidenza:**
  * file/log/tabella: `s4_lifecycle_events`
  * timestamp: 2026-09-08 14:12–19:42 UTC
  * snippet/query:
    ```sql
    SELECT symbol, COUNT(*), MIN(observed_at), MAX(observed_at) FROM s4_lifecycle_events
    WHERE observed_at::date='2026-09-08' GROUP BY 1 ORDER BY 2 DESC;
    -- HOOD 5 | SPCX 4 | NVDA 4 | QCOM 2 | MSFT 1 | AZN 1 | NVO 1 | CRM 1
    ```
* **Descrizione:** ricorrenza di F-061. Lo stesso fill viene riemesso a ogni ciclo finché la
  posizione resta aperta: HOOD ha 5 righe identiche (stesso `fill_price` 124,18, stessa
  `filled_quantity`) fra le 14:27 e le 16:57. Compaiono anche MSFT e CRM, posizioni aperte in
  giorni precedenti. **Zero eventi di uscita** nonostante 5 chiusure.
* **Impatto:** un ledger append-only che riemette eventi derivati non è più append-only nel senso
  utile: contare gli ingressi da questa tabella dà 19 invece di 7, e le uscite non ci sono affatto.
  Costo non stimabile, ma il ledger degli intent S4 è uno strumento della finestra di osservazione.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** ticket di **correttezza**: emettere l'evento una sola volta per
  `(intent_id, event_type)` e aggiungere l'evento di uscita.
* **Test/monitor consigliato:** invariante `COUNT(DISTINCT intent_id) == COUNT(*)` per
  `event_type='ENTRY_RECONCILIATION'` nella giornata.

---

### [DAY-013] `duplicates` (4.646) supera `fetched` (1.001) di 4,6×

* **Tipo:** Bug
* **Area:** News / Data
* **Evidenza:**
  * file/log/tabella: `ingestion_stats_daily`; `logs/containers/worker-2026-09-08.log:3975`
  * timestamp: 2026-09-08 23:15 UTC (ultimo update)
  * snippet/query:
    ```
    alpaca_benzinga | fetched 1001 | queued 542 | duplicates 4646 | stale 157
    14:30:01 Alpaca ingestion stats: {'fetched': 28, 'tickers_found': 154, 'duplicates': 154}
    ```
* **Descrizione:** ventiduesima ricorrenza di F-007. `fetched` conta articoli, `duplicates` conta
  righe ticker-fanout: due unità diverse nello stesso record. Nel giro delle 14:30, 28 articoli
  producono 154 «duplicati».
* **Impatto:** il tasso di duplicazione della pipeline non è calcolabile da questa tabella, che è
  la fonte del pannello di qualità.
* **Severità:** Low
* **Confidenza:** High
* **Azione consigliata:** ticket: separare `duplicate_articles` da `duplicate_ticker_rows`.
* **Test/monitor consigliato:** invariante `duplicates <= fetched * max_tickers_per_article`.

---

### [DAY-014] Ensemble degradato: 64 timeout Ollama, 37,4% dei segnali in fallback

* **Tipo:** Anomalia
* **Area:** LLM
* **Evidenza:**
  * file/log/tabella: `logs/containers/worker-inference-2026-09-08.log`; `sentiment_signals`; `ensemble_cycle_health`
  * timestamp: distribuito su tutta la seduta, picco 15:08–15:20 UTC
  * snippet/query:
    ```
    33 × ensemble model failed: model=gpt-oss:20b-cloud error=Ollama timeout (90s)
    31 × ensemble model failed: model=glm-5.2:cloud   error=Ollama timeout (90s)
     8 × Ollama rate limit
    ```
    ```sql
    SELECT model_id, COUNT(*) FROM sentiment_signals WHERE generated_at::date='2026-09-08' GROUP BY 1;
    -- ensemble 134 | single:gpt-oss 39 | finbert 29 | single:glm 12   → 80/214 fallback (37,4%)
    ```
* **Descrizione:** ricorrenza di F-049 in forma attenuata: non un outage secco come il 2026-08-26,
  ma un degrado diffuso. `ensemble_cycle_health` mostra 50 cicli di cui 8 con `n_ensemble = 0` o 1.
  Il 13,6% dei segnali è FinBERT puro.
* **Impatto:** la guardia #108 ha protetto correttamente il lato ordini — **tutti e 7 i BUY vengono
  da segnali ensemble**, e i single-model sono stati esclusi 15 volte. Il costo è di copertura: 51
  simboli-evento hanno ricevuto un giudizio a un modello solo, che il ranker BUY poi ignora.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** nessuna azione ora (il timeout a 90 s è taratura). Registrare per
  ricorrenza; incrociare con **[DAY-001]**, perché è il degrado di latenza a portare il ciclo
  contro il soft time limit.
* **Test/monitor consigliato:** serie giornaliera di `fallback_share` con annotazione dei giorni
  in cui supera il 30%.

---

### [DAY-015] Divergenza d'ensemble mai usata come gate: 12 segnali con σ > 0,20, 5 di segno opposto

* **Tipo:** Rischio
* **Area:** LLM
* **Evidenza:**
  * file/log/tabella: `sentiment_signals`, `llm_responses`
  * timestamp: 2026-09-08
  * snippet/query:
    ```sql
    SELECT r1.signal_id, s.symbol, r1.polarity, r2.polarity FROM llm_responses r1
    JOIN llm_responses r2 USING (signal_id) JOIN sentiment_signals s ON s.id=r1.signal_id
    WHERE r1.model_id='glm-5.2:cloud' AND r2.model_id='gpt-oss:20b-cloud'
      AND ABS(r1.polarity-r2.polarity)>=0.5;
    -- T +0.35/-0.30 ; QQQ +0.05/+0.65 ; AMZN +0.25/-0.30 ; GE -0.15/+0.40 ; VZ +0.15/+0.70 ×2 ; PLTR +0.15/-0.35
    ```
* **Descrizione:** ricorrenza di F-037. `ensemble_std` è calcolato e persistito ma non entra in
  alcuna decisione. Su VZ i due modelli danno +0,15 e +0,70 e il risultato pesato (+0,244) entra nel
  pool senza alcuna marcatura di incertezza.
* **Impatto:** CLAUDE.md prescrive «Ensemble variance: flag high-variance outputs for human review
  or discard». Oggi nessuno dei 12 casi divergenti ha generato un ordine, quindi costo nullo, ma la
  mitigazione delle allucinazioni resta scritta e non implementata.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** nessuna azione ora (introdurre un gate di varianza è taratura pura).
  Registrare per ricorrenza.
* **Test/monitor consigliato:** contatore giornaliero di segnali con σ > 0,20 che superano il gate
  d'ingresso — oggi zero, ma è il numero che deciderà se il gate serve.

---

### [DAY-016] Fan-out content-mill: un articolo genera 8 segnali a zero

* **Tipo:** Anomalia
* **Area:** News / Signal
* **Evidenza:**
  * file/log/tabella: `news_log` id 9906-9913; `sentiment_signals`
  * timestamp: 2026-09-08 15:13–15:20 UTC
  * snippet/query:
    ```
    "How To Trade SPY, QQQ, AAPL, MSFT, NVDA, GOOGL, META, And TSLA"
    → AAPL 0.000 | GOOGL 0.000 | META 0.000 | MSFT 0.000 | NVDA 0.000 | QQQ 0.000 | SPY 0.000 | TSLA 0.000
    ```
* **Descrizione:** ricorrenza congiunta di F-012 e F-066. Un articolo senza contenuto informativo
  occupa 8 slot di inferenza, e — punto non secondario — è **fra i 12 ri-scorati** di [DAY-001],
  quindi ha consumato 16 chiamate. Stesso schema su NOW: score +0,260 da un articolo intitolato
  «Robinhood To Rally Around 23%? Here Are 10 Top Analyst Forecasts For Tuesday», con NOW a −4,99%
  in giornata; e su ADBE, score 0,000 da «Oracle Could Swing By $47.8 Billion After Earnings»,
  ADBE a −3,47%.
* **Impatto:** i 12 candidati miss della giornata hanno una `quota_righe_fanout` di **0,632**: due
  terzi delle righe che li riguardano vengono da articoli non specifici. Il modello scora
  correttamente **0,000** — non è un errore di giudizio, è spreco di budget e rumore nella serie.
* **Severità:** Low
* **Confidenza:** High
* **Azione consigliata:** nessuna azione ora; è materia del golden set QX-01 (enforcement gated).
  Registrare per ricorrenza.
* **Test/monitor consigliato:** quota giornaliera di segnali provenienti da articoli con
  `n_ticker_articolo >= 5`.

---

### [DAY-017] AMAT a −22,7% senza stop possibile e senza allerta consegnata

* **Tipo:** Rischio
* **Area:** Risk
* **Evidenza:**
  * file/log/tabella: `stop_shadow_log`; `logs/containers/worker-2026-09-08.log:3828`
  * timestamp: 14:07–19:52 UTC, 24 cicli consecutivi
  * snippet/query:
    ```sql
    SELECT symbol, MAX(entry_price), MIN(observed_price), MAX(d_hard) FROM stop_shadow_log
    WHERE cycle_ts::date='2026-09-08' AND d_hard_breached GROUP BY 1;
    -- AMAT | 593.798 | 458.89 | 0.20   → -22.72%
    ```
    `#161: 10/43 held positions are unprotectable (qty < 1): ['AMAT','AMD','ASML','CAT','DELL','LLY','MRVL','NOK','SPY','WDC']`
* **Descrizione:** ricorrenza di F-022. AMAT è l'unica posizione che ha sfondato il `d_hard`
  (12–20%) su tutti e 24 i cicli. Con `qty 0,8571 < 1 azione` non può avere uno stop broker.
  `trading.yaml:178-180` prevede esplicitamente: «Revisit: if any position rides past −15/20%
  (d_hard shadow), wire d_hard to a real broker order». La condizione si è verificata, e l'unico
  canale di notifica ha restituito 400 ([DAY-007]).
* **Impatto:** oggi AMAT ha guadagnato +3,98%, quindi nessuna perdita incrementale attribuibile.
  Ma 10 posizioni su 43 sono strutturalmente non proteggibili e il trigger di revisione documentato
  è scattato senza destinatario.
* **Severità:** High
* **Confidenza:** High
* **Azione consigliata:** la size minima ≥1 azione è **taratura** e resta congelata. La consegna
  dell'allerta no: va corretta con [DAY-007]. Registrare per ricorrenza.
* **Test/monitor consigliato:** incidente `mobile_events` (non solo Telegram) quando
  `d_hard_breached` è vero su ≥ 3 cicli consecutivi.

---

### [DAY-018] La notizia arriva dopo il movimento: mediana 85% su 7 ingressi

* **Tipo:** Osservazione
* **Area:** Signal
* **Evidenza:**
  * file/log/tabella: `docs/evidence/dossier/2026-09-08.json → ingressi[].quota_movimento_precedente_al_segnale`
  * timestamp: 2026-09-08
  * snippet/query: NVO 0,669 · QCOM 0,618 · HOOD 0,115 · SPCX 0,849 · AZN **0,977** · NVDA **0,966** · SPCX-bis **1,038**
* **Descrizione:** ricorrenza di F-030. Su 4 ingressi su 7 oltre l'84% del movimento del titolo era
  già avvenuto quando il segnale è stato scorato; su SPCX-bis il movimento era interamente
  concluso (quota > 1). Mediana 0,849.
* **Impatto:** il MTM EOD aggregato delle 7 entrate è **−118,35 $**. Ma i tre ingressi più «tardivi»
  (AZN, NVDA, SPCX-bis) sommano a **−3,99 $**, mentre i due più «tempestivi» (NVO 0,669 e QCOM
  0,618) sommano a **−41,56 $**: nella giornata di oggi la tempestività **non** predice l'esito, e
  attribuire il P&L a questo fattore sarebbe scorretto. Costo non stimabile.
* **Severità:** Medium
* **Confidenza:** Medium
* **Azione consigliata:** nessuna azione. Continuare la serie fino al 2026-09-28.
* **Test/monitor consigliato:** correlazione, sulla finestra completa, fra
  `quota_movimento_precedente_al_segnale` e MTM EOD dell'ingresso.

---

### [DAY-019] Quattro segnali ribassisti oltre il gate senza alcun percorso di uscita

* **Tipo:** Osservazione
* **Area:** Signal
* **Evidenza:**
  * file/log/tabella: `sentiment_signals`
  * timestamp: 2026-09-08
  * snippet/query: NFLX −0,420 · IWM −0,303 · XLV −0,300 · F −0,299
* **Descrizione:** ricorrenza di F-040. S4 è long-only e nessuno dei quattro simboli è a libro,
  quindi il segnale ribassista non può nemmeno chiudere una posizione. Il gate scarta i ribassisti
  in valore assoluto (`score.abs() >= threshold`), quindi la loro esistenza è registrata ma
  operativamente inerte.
* **Impatto:** nessun costo diretto oggi. La metà negativa del segnale sentiment è, per costruzione,
  non monetizzabile: solo il 1,4% dei segnali della giornata.
* **Severità:** Low
* **Confidenza:** High
* **Azione consigliata:** nessuna azione (è una scelta di design, non un difetto). Registrare.
* **Test/monitor consigliato:** già coperto dal dossier.

---

### [DAY-020] Attribuzione ticker non confermata sul 58% delle righe

* **Tipo:** Rischio
* **Area:** News
* **Evidenza:**
  * file/log/tabella: `docs/evidence/dossier/2026-09-08.json → copertura_articoli.totali.mapping_rilevanza`; `news_log.extraction_method`
  * timestamp: 2026-09-08
  * snippet/query: `ISSUER_SPECIFIC: 84 · TAG_UNCONFIRMED: 118 · SECTOR_MACRO: 0 · FALSE_ENTITY_MATCH: 0`;
    `extraction_method`: `source_metadata` 185, `org_lookup` 17, **`resolver` 0**
* **Descrizione:** ricorrenza di F-057. Il resolver deterministico dei ticker
  (`src/connectors/ticker_resolver*.py`) non emette un solo verdetto `RESOLVED`: l'intero flusso
  poggia sui tag del provider (185) e su `org_lookup` (17). CLAUDE.md prescrive che la risoluzione
  ticker sia «separata e deterministica» e che `false_positive_ticker_rate → 0`; oggi non è
  misurabile, perché il misuratore non gira.
* **Impatto:** nessun `FALSE_ENTITY_MATCH` rilevato oggi, ma il rilevatore stesso non è attivo.
  Su GDELT il fallback `org_lookup` è quello che F-020 associa storicamente alle attribuzioni
  errate sui ticker bancari.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** nessuna azione sullo scoring (enforcement gated sul golden set QX-01,
  per esplicita disposizione di CLAUDE.md). Registrare per ricorrenza.
* **Test/monitor consigliato:** contatore giornaliero di righe con `extraction_method='resolver'`;
  oggi zero, e zero è il segnale.

---

## 11. False positive e aree risultate corrette

Elementi che sembrano anomalie e **non lo sono** — verificati, non assunti:

1. **`stop_decisions` vuota dal 2026-07-14.** Non è un guasto: `risk.stop_loss: 0.0` disabilita
   deliberatamente lo stop protettivo dal 2026-07-15, con evidenza citata in
   `config/trading.yaml:167-181` (replay OOS: `no_protective` −56 $ contro `fixed_2pct` −419 $).
   Lo shadow gira regolarmente (1.089 righe oggi). **Corretto.**
2. **`stop_d_init = 0` su tutte le 7 posizioni S4 aperte.** Conseguenza diretta del punto 1.
3. **NVDA venduta a 105 minuti con `exit_reason = hold_minimum_expiry`.** 105 min = 7 × 900 s è
   esattamente il primo beat successivo al `hold_minimum_minutes` di 90: il marker #430 sta
   descrivendo correttamente ciò che è avvenuto, non nascondendo un'uscita anomala.
4. **S1 non ha eseguito alcun ordine.** Gate di ribilanciamento mensile chiuso (ultimo 2026-09-01),
   conforme al fix #185. Log esplicito su tutti e 24 i cicli.
5. **`portfolio_cycles` inizia alle 14:07 e non alle 13:37.** Effetto di [DAY-004], non un ciclo
   perso: la cadenza successiva è di 15 min esatti senza salti.
6. **`constraints_fired: []` su tutti i cicli.** Esposizione 32,7% su un cap ben più alto e HHI
   0,026: non c'era nulla da vincolare.
7. **Segnali di 91 ore d'età valutati e scartati.** Corretto: 09-04 venerdì → 09-07 Labor Day →
   09-08. `SKIP_STALE` con motivo esplicito.
8. **`SIGNAL_DUPLICATE_SKIP` ×48.** Il guard P1-S4 di idempotenza sugli ordini **funziona**: AZN e
   NVO sono stati bloccati correttamente sui cicli successivi al loro ingresso.
9. **Guardia anti-contraddizione del dossier:** 109 intenti valutabili, **0 soppressi**.
10. **Invariante rank/ranking_score (#401):** 131 righe esaminate, **0 violazioni**.
11. **Alert stale-drop consegnato** (Telegram 200 OK alle 22:55): il canale non è rotto in sé.
12. **Zero record malformati in `news_log`**: nessun titolo, corpo, ticker o `published_at`
    mancante; zero timestamp futuri; zero `parse_fail`.
13. **Le uscite `below_entry_gate` di oggi hanno prodotto +36,57 $** rispetto al tenere le
    posizioni: il meccanismo che classifichiamo come churn ha, in questa seduta, protetto capitale.

---

## 12. Dati mancanti o non accessibili

| Dato | Stato | Query/percorso che servirebbe |
|---|---|---|
| API REST (`/decisions`, `/trades`, `/signals`, `/positions`, `/orders`) | **403 su tutti** — [DAY-009] | token valido; report costruito interamente da SQL + log |
| Latenza per chiamata LLM | **Non persistita** | serve un campo `latency_ms` su `llm_responses`; oggi ricavabile solo per differenza fra timestamp di riga consecutivi, che non isola la chiamata |
| Prezzo atteso per NVO, CRM, AZN | **Assente** | `s4_lifecycle_events.first_executable_price` esiste solo per gli intent con ledger; NVO e AZN non hanno riga di confronto → slippage non calcolabile su 3 dei 7 ingressi |
| Benchmark SPY per il rendimento relativo | **Non recuperato** | F-016, fetch SPY fallisce per limite di sottoscrizione |
| Eventi di **uscita** in `s4_lifecycle_events` | **Assenti** — [DAY-012] | solo `ENTRY_RECONCILIATION`; le 5 uscite non hanno evento di ciclo di vita |
| `performance_metrics` per il 2026-09-08 | **0 righe** | `composite_ic`/`icir` non calcolati per la giornata |
| Provenienza di trasporto (REST vs WebSocket) su `news_log` | **Non persistita** | `source` vale `alpaca_benzinga` in entrambi i casi; impossibile attribuire il p50 di 20,8 min al WS |
| Log dei container antecedenti al 2026-09-04 | **Non disponibili** | F-027, rotazione a 6 giorni |
| Segnali disponibili al momento di ogni SELL | **Non ricostruibile** | vedi [DAY-006]: solo l'ultimo è citato nel testo del motivo |

---

## 13. Raccomandazioni immediate

Tutte le raccomandazioni rispettano il freeze di `OBSERVATION_CHARTER.md` fino al **2026-09-28**:
sono correzioni di correttezza o di osservabilità, **nessuna taratura**.

1. **Rendere idempotente il ciclo sentiment** ([DAY-001]). È la raccomandazione con la priorità più
   alta perché è l'unica che, se non applicata, rende **sbagliata** l'evidenza raccolta da qui alla
   chiusura della finestra. Passa il test di esenzione della carta.
2. **Persistere il punteggio valutato al gate** ([DAY-002]). Stessa motivazione: senza questo, ogni
   ri-misura del funnel dal DB diverge dalla produzione, esattamente come in #169/#467.
3. **Riparare la consegna degli alert** ([DAY-007], [DAY-008], [DAY-017]). Il sistema **sa** che
   AMAT è a −22,7% e che il breaker di fallback è scattato: nessuno dei due messaggi è arrivato.
   Correggere il payload Telegram e aggiungere un fallback su `mobile_events`.
4. **Rigenerare il token del protocollo forense** ([DAY-009]). Alla dodicesima ricorrenza, questo
   report continua a essere scritto da una fonte diversa da quella prescritta.
5. **Ancorare le finestre beat al calendario Alpaca** ([DAY-004]). Il sistema apre già un incidente
   critical alle 13:30 di ogni seduta EDT: la diagnosi è fatta, manca la correzione.

Non raccomandato ora, e va detto esplicitamente: banda morta fra gate d'ingresso e d'uscita,
cooldown di ri-entrata S4, aggregazione multi-segnale, gate di varianza d'ensemble, size minima
≥ 1 azione. Sono tutte tarature e restano congelate.

## 14. Test o monitor da aggiungere

| # | Monitor | Soglia | Motivo |
|---|---|---|---|
| M1 | `sentiment_signals` con `news_log_id` duplicato in giornata | **0** | [DAY-001] |
| M2 | Righe `BUY` con `signal_score` < soglia attiva e nessun campo che lo spieghi | **0** | [DAY-002] |
| M3 | `avg_queue_wait_hours` > `MAX_NEWS_AGE_HOURS` | allarme | [DAY-003]: la coda garantisce lo scarto per costruzione |
| M4 | Ritardo fra apertura da `GetCalendarRequest` e primo `portfolio_cycles.timestamp` | > 10 min | [DAY-004] |
| M5 | Sequenze BUY→SELL→BUY sullo stesso simbolo in seduta, con delta di prezzo alla rientrata | serie | [DAY-005] |
| M6 | Alert generati vs consegnati (per canale) | differenza > 0 | [DAY-007] |
| M7 | `d_hard_breached` su ≥ 3 cicli consecutivi → incidente `mobile_events` | attivo | [DAY-017] |
| M8 | `slippage_est == cost_usd` su trade con evento di lifecycle | **0** | [DAY-010] |
| M9 | `COUNT(DISTINCT intent_id) == COUNT(*)` per `ENTRY_RECONCILIATION` | uguaglianza | [DAY-012] |
| M10 | `fallback_share` giornaliero | annotare > 30% | [DAY-014] |
| M11 | Segnali con `ensemble_std > 0,20` che superano il gate | serie | [DAY-015] |
| M12 | Righe `news_log` con `extraction_method='resolver'` | serie (oggi 0) | [DAY-020] |
| M13 | Smoke test CI sui 5 endpoint del protocollo forense col token documentato | 200 | [DAY-009] |

### Test unitari / d'integrazione

* **T1** — simulare `SoftTimeLimitExceeded` a metà batch sentiment e asserire che il run successivo
  non riscriva segnali per `news_log_id` già presenti ([DAY-001]).
* **T2** — test parametrizzato su una data EDT e una EST: il primo ciclo deve cadere entro 10 min
  dall'apertura di calendario ([DAY-004]).
* **T3** — test di contratto sul payload Telegram di ogni notifier ([DAY-007]).
* **T4** — invocare il breaker di fallback da dentro un event loop attivo e asserire che l'alert
  parta davvero ([DAY-008]).

## 15. Ticket tecnici suggeriti

| ID | Titolo | Area | Priorità | Esente dal freeze? |
|---|---|---|---|---|
| T-A | Ciclo sentiment idempotente: `LREM` per item dopo la scrittura del segnale, non `delete()` di fine batch | LLM/Data | **P0** | **Sì** — senza, l'evidenza raccolta è sbagliata |
| T-B | Persistere su `execution_decisions` e sul ledger intent il punteggio valutato al gate (o il moltiplicatore velocity applicato) | Signal | **P0** | **Sì** — stessa classe di #169/#467 |
| T-C | Riparare il payload Telegram (400) e aggiungere fallback `mobile_events` per gli alert #161 e loss-feedback; dedup «uno per simbolo al giorno» | Ops/Risk | **P1** | Sì (osservabilità) |
| T-D | `send_fallback_alert` compatibile con event loop attivo (rimuovere `asyncio.run()` annidato) | LLM/Ops | P1 | Sì (osservabilità) — già F-071 |
| T-E | Finestre beat derivate da `GetCalendarRequest` invece che da `hour="14-21"` UTC fisso | Ops | P1 | Sì — applica la stessa regola nell'orario giusto |
| T-F | Propagare `signal_id` sul percorso di uscita; far fallire il job del dossier sulle `regressions` invece di solo registrarle | Signal | P1 | Sì — già F-011 |
| T-G | `trades.slippage_est` calcolata da `fill_price − first_executable_price` invece di copiare `cost_usd` | PnL | P1 | Sì — l'attribuzione dei costi è evidenza |
| T-H | `s4_lifecycle_events`: un solo evento per `(intent_id, event_type)` + eventi di uscita | Data | P2 | Sì — già F-061 |
| T-I | Rigenerare/allineare il token del protocollo forense sugli endpoint REST | Ops | P2 | Sì — già F-041 |
| T-J | Separare `duplicate_articles` da `duplicate_ticker_rows` in `ingestion_stats_daily` | Data | P3 | Sì — già F-007 |
| T-K | Persistere la latenza per chiamata su `llm_responses` e la provenienza di trasporto su `news_log` | Ops | P3 | Sì (strumentazione) |
| T-L | Consumo della coda news fuori seduta (decisione di design, non soglia) | News | P2 | **Da valutare** — vedi [DAY-003] |

## 16. Stato sistema

### Ollama

**Up per l'intera seduta, degradato.** Nessun outage secco: entrambi i modelli hanno risposto dalle
13:31:19 alle 19:52:08 senza buchi. Degrado misurato:

| Metrica | Valore |
|---|---|
| Timeout (90 s) | **64** (gpt-oss 33, glm 31) |
| Rate limit | 8 (4 + 4) |
| Risposte persistite | 356 |
| Tasso di successo | **83,2%** |
| Ore di downtime totale | **0** |
| Finestra di degrado più intensa | 15:08–15:20 UTC (3 fallback consecutivi → breaker scattato) |
| Timeout LLM su regime detection | 1 (`kimi-k2.6:cloud`, 07:00 UTC) |

### FinBERT / fallback

| Metrica | Valore |
|---|---|
| Segnali con `fallback_used = true` | **80 / 214 = 37,4%** |
| Segnali FinBERT puri | 29 / 214 = **13,6%** |
| Segnali single-model cloud | 51 / 214 = 23,8% |
| **Decisioni BUY da segnale fallback** | **0 / 7 = 0,0%** |
| `SKIP_FALLBACK` (guard #108 attivo) | 15 |
| Cicli `ensemble_cycle_health` con `n_ensemble = 0` | 3 su 50 |

La distinzione conta: il **37,4%** è il tasso di fallback sui *segnali*, ma il tasso di fallback
sulle *decisioni d'ordine* è **zero** — la guardia #108 ha tenuto su tutte e 15 le occasioni.

### Worker restart

| Ora UTC | Worker | Evento | Impatto |
|---|---|---|---|
| 10:30:07 | worker-inference | `Warm shutdown` + `WorkerLostError(SIGTERM) Job: 117` | pre-market, nessun ordine in volo |
| 20:20:10 | worker-inference | `Warm shutdown` + `WorkerLostError(SIGTERM) Job: 7002` | post-close, nessun ordine in volo |
| 15:20:24 | worker-inference | `SoftTimeLimitExceeded` su `run_sentiment_worker` (non un restart, ma perdita di task) | **→ [DAY-001]** |
| — | worker (main) | **0 restart, 0 righe ERROR** in tutta la giornata | — |
| — | beat | **0 errori**; 32 invii `sentiment-worker`, 24 `portfolio-cycle` in seduta | — |
| — | worker-news-stream | 32 riconnessioni WebSocket, 16 `TimeoutError`/DNS; nessun crash del processo | degradato ma vivo |

### Infrastruttura

| Componente | Stato |
|---|---|
| PostgreSQL (`alembic-postgres-1`) | ✓ nessun errore |
| Redis (`alembic-redis-1`) | ✓ `pipeline_health.redis: fresh, writeable, age 0s` su tutti gli snapshot |
| API | ✓ 13.183 risposte 200, 8 × 403 (tutte del protocollo forense) |
| Alpaca paper | ✓ 12 ordini, 12 fill, 0 reject |
| Telegram | ⚠ 3 × 400 su 4 invii (75% di fallimento sugli alert operativi) |
| DNS del container inference | ⚠ ~6,5 min di `Temporary failure in name resolution` alle 09:01–09:07 |

---

*Report generato in modalità read-only. Nessun commit, nessuna patch, nessun ordine.
`docs/evidence/findings.json` aggiornato in append come da protocollo.*
