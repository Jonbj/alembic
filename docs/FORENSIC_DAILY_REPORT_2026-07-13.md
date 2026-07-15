# Forensic Daily Report — 2026-07-13

Analista: sessione autonoma Claude (Trading Systems Forensic Analyst + Senior Backend Engineer + Quant Operations Reviewer)
Modalità: read-only, nessuna modifica al sistema, nessun ordine inviato.
Timezone operativo: **UTC** (`celery_app.py`: `timezone="UTC"`, `enable_utc=True`). Tutti i timestamp in questo report sono UTC salvo indicazione contraria.

---

## 1. Executive Summary

Giornata operativa **paper trading al 100%** (S1=`supervised_paper`, S4=`paper`, nessuna strategia in `live`). 24 cicli di portfolio (14:07→19:52 UTC), 34 ordini generati e tutti eseguiti (`filled`), 13 BUY / 21 SELL, nessun reject/cancel. PnL realizzato del giorno ≈ **-$232** (14 stop-loss simultanei sul cohort S1 di venerdì 07-10 pesano per ≈ -$241; 5 chiusure S4 miste). Trovato un bug sistemico di **disallineamento DST**: la finestra Celery (14:00-21:00 UTC) non insegue l'orario reale di mercato in EDT (13:30-20:00 UTC) — il sistema perde i primi 30 min di sessione e continua a ingerire/valutare news per ~1h45m dopo la chiusura reale, producendo ~89 segnali/giorno (≈29% del volume) mai valutati da un ciclo di portfolio. Trovata evidenza concreta di **misattribuzione ticker** (MS, GS, META agganciati a notizie su tutt'altro soggetto — Musk/SpaceX, Verra Mobility, Nebius) tra i segnali di score più estremo della giornata; il resolver-shadow le marca correttamente `NO_TRADE_LOW_RESOLUTION_CONFIDENCE` ma l'enforcement resta gated (comportamento atteso, non un bug nuovo). Trovato un bug di **riconciliazione trade/ordini** su SHEL (uscita in 3 tranche, il ledger `trades` registra solo la prima). Fallback FinBERT al 57% (176/309), interamente per divergenza ensemble (Ollama sempre up, 0 timeout). Log Docker per il 07-13 non disponibili (container riavviati il 07-14 12:11 UTC): tutte le evidenze derivano da stato persistito in Postgres/Redis, non da log applicativi.

## 2. Verdict Finale

**OK con warning** — nessuna violazione di safety/paper-live, nessun ordine fuori processo, nessun circuit breaker mancato; ma persistono inefficienze sistemiche note (fallback rate, gap DST) e un bug di riconciliazione PnL isolato (SHEL) più un cluster di stop-loss che consuma gran parte del P&L del giorno — nessuno di questi è nuovo rispetto a quanto già tracciato in memoria di progetto, ma qui vengono quantificati con dati freschi del 07-13.

---

## 3. Timeline del 2026-07-13 (UTC)

| Ora | Componente | Evento |
|---|---|---|
| 13:30 | Mercato (NYSE, EDT) | Apertura reale sessione cash — **nessuna ingestion/scoring attivo** (vedi [DAY-001]) |
| 14:00-14:02 | Ingestion worker | Prima esecuzione ingest Alpaca/Benzinga + GDELT GKG del giorno (crontab `*/15, 14-21 UTC`) |
| 14:02:01–14:03:35 | Sentiment worker | 5 chiamate `kimi-k2.6:cloud` — selezione modelli momentaneamente su "all" (vedi [DAY-007], noto/gestito) |
| 14:07:01.16 | Portfolio cycle #390 | 34 ordini: chiusura stop-loss di 9/14 posizioni del cohort S1 aperto 07-10 (batch a millisecondo identico) + apertura DELL/PANW/WDC/XOM (S1) |
| 14:09:32 | Sentiment worker | Prime risposte `gpt-oss:20b-cloud` — pair `glm52,gptoss` confermato attivo |
| 14:22:00 | Portfolio cycle #391 | Chiusura PFE (S4, +$43.89, unico grande win del giorno) |
| 15:07:01 | Portfolio cycle #394 | BUY SHEL, HOOD (S4 news-driven) |
| 15:22-15:52 | Portfolio cycle | BUY META, BA (S4) |
| 16:37:00.59 | Portfolio cycle #400 | Chiusura stop-loss dei restanti 5/14 del cohort 07-10 (AMAT, XLK, VALE, TSM, CAT) |
| 17:22:01 | Portfolio cycle #403 | BUY TM (S4) |
| 18:22:00.76 | Portfolio cycle #407 | SELL SHEL tranche 1/3 (1.32 az. @84.06); BUY DIS (S4, $5,275 notional) |
| 19:07:00.59 | Portfolio cycle #410 | SELL TM (portfolio_sell); BUY SPCX, JPM (S4) |
| 19:22:00.66 | Portfolio cycle #411 | SELL SHEL tranche 2/3 (0.42 az.); SELL HOOD (segnale S4 scaduto, age 4.4h); BUY CVX (S1) |
| 19:37:00.61 | Portfolio cycle #412 | SELL META (segnale S4 scaduto, age 4.4h) |
| 19:52:00.63 | Portfolio cycle #413 (ultimo del giorno) | SELL SHEL tranche 3/3 (16.28 az., weight→0%) |
| 20:00:12–21:45:45 | Ingestion + Sentiment worker | Continuano a ingerire/valutare (88 news, 89 segnali) **dopo** la chiusura reale — nessun ciclo di portfolio li consuma (vedi [DAY-001]) |
| 21:45:39 | Sentiment worker | Ultimo segnale del giorno (`gpt-oss:20b-cloud`) |
| 22:30:00.68 | Risk monitor | Unico `risk_reports` del giorno: NAV $109,918.53, exposure 26.38%, drawdown 6.21%, alerts=[] |

Nessun ciclo di portfolio tra 20:07 e 21:52 UTC (8 slot schedulati mancanti) — comportamento identico, non isolato, sui giorni 07-07/08/09/10 campionati (sempre ultimo ciclo a 19:52). Non è un crash: `portfolio_scheduler.py` interroga l'orologio reale Alpaca (`trading_client.get_clock().is_open`) e si ferma correttamente a mercato chiuso — vedi [DAY-001] per il vero problema (a monte, sull'ingestion).

---

## 4. Tabella News Ingest (2026-07-13)

| Fonte | Fetched | Queued (→Redis) | Persistiti in `news_log` | Duplicates | Discarded no-ticker | Ticker distinti |
|---|---:|---:|---:|---:|---:|---:|
| alpaca_benzinga | 677 | 353 | 99 | 2,885 | 0 | 43 |
| gdelt_gkg | 2,506 | 305 | 207 | 207 | 2,178 | 23 |
| **Totale** | 3,183 | 658 | 306 | 3,092 | 2,178 | ~55 uniche |

Note metodologiche:
- `fetched`→`queued`: filtro dedup a livello ingest (`Deduplicator.is_duplicate_by_id`/`is_duplicate_content_symbol`) + (per GDELT) filtro watchlist/no-ticker.
- `queued`→persistito in `news_log`: **non** è un gap 1:1 comparabile — `news_log` viene scritto **solo** quando il worker di sentiment processa l'item fino in fondo (successo ensemble o fallback FinBERT), non al semplice dequeue. Il divario (353→99 per Benzinga, 305→207 per GDELT) è in parte spiegato da skip legittimi (news stale >`MAX_NEWS_AGE_HOURS`, pre-filtro MarketAux neutro, drop pre-inferenza del resolver shadow) — ma questi contatori (`skipped_stale`, `skipped_neutral`, `skipped_not_tradable`) **non sono persistiti in una tabella interrogabile**, solo nel return value del task Celery (vedi [DAY-009]). Non è quindi possibile riconciliare esattamente il gap con i soli dati DB.
- Duplicate rate elevato ma coerente con la storia recente (2,885-3,746 duplicati/giorno su Benzinga negli ultimi 5 giorni campionati) — non è un'anomalia isolata del 07-13.
- Nessuna news con `published_at` futuro o >48h nel passato rispetto a `fetched_at` trovata in `news_log`.
- Nessuna news `fetched_at` prima delle 13:30 UTC (primo item 14:02 UTC) — coerente con [DAY-001].
- 88 news ingerite dopo le 20:00 UTC (chiusura reale mercato in EDT).

**Top ticker per volume news (07-13):** MS (55 segnali generati, mai in top-15 fetch ma alto numero di articoli GDELT collegati — vedi [DAY-002]), GS (40), MU (38), TSM (24), DIS (14).

**Problemi trovati:** vedi [DAY-002] (misattribuzione ticker), [DAY-003] (near-duplicate wire syndication elude il content-hash dedup).

**Confidenza analisi:** Alta per i conteggi (dati DB diretti); Media per la spiegazione del gap queued→persistito (log applicativi non disponibili per confermare la ripartizione esatta tra stale/neutral/not_tradable).

---

## 5. Tabella Performance Modelli LLM (2026-07-13)

### Segnali finali per modello/fallback (`sentiment_signals`)

| model_id | fallback | n | conf. media | score medio | prima–ultima esecuzione |
|---|---|---:|---:|---:|---|
| finbert | true | 176 | 0.349 | 0.002 | 14:02:01 – 21:45:46 |
| ensemble: gpt-oss:20b-cloud (solo) | false | 88 | 0.486 | 0.014 | 14:09:32 – 21:45:40 |
| ensemble: glm-5.2+gpt-oss (accordo) | false | 36 | 0.569 | 0.089 | 14:09:37 – 21:31:15 |
| ensemble: glm-5.2:cloud (solo) | false | 9 | 0.761 | 0.100 | 14:45:44 – 20:46:17 |
| **Totale** | | **309** | | | |

**FinBERT fallback rate: 176/309 = 57.0%**, distribuito uniformemente nella giornata (48-72% per ora, min 15:00h 38%, max 18:00h 72%) — non concentrato in una finestra, quindi non riconducibile a un evento episodico (es. rate limit temporaneo).

### Raw responses per modello (`llm_responses`, eligible = ha contribuito al segnale finale)

| model_id | eligible | n | polarity media | confidence media |
|---|---|---:|---:|---:|
| glm-5.2:cloud | false | 264 | -0.003 | 0.170 |
| gpt-oss:20b-cloud | false | 180 | 0.001 | 0.266 |
| gpt-oss:20b-cloud | true | 124 | 0.056 | 0.511 |
| glm-5.2:cloud | true | 45 | 0.156 | 0.607 |
| kimi-k2.6:cloud | false | 5 | 0.000 | 0.140 |

- **0 timeout Ollama, 0 fallback per budget esaurito** — tutti i 176 fallback hanno `reasoning = "FinBERT fallback (ensemble divergence)"`. Ollama Cloud: **100% up, 0 ore di downtime rilevate il 07-13**.
- `llm_budget`: $0.103 spesi (57,313 input + 7,907 output token), `budget_exhausted=false` — budget non è mai stato un fattore.
- `fallback_counters.consecutive_fallback = 1` a fine giornata — nessuna sequenza di fallback runaway.
- Incidente selezione modelli a inizio giornata: vedi [DAY-007].

**Verifica funzionale:**
- Output LLM validato prima di entrare nel signal store? **Sì** — solo output `eligible=true` (non-fallback) alimentano l'ensemble; su fallback tutti i raw output vengono forzati `eligible=false` e persistiti comunque per audit (non silenziosamente scartati).
- Ensemble gestisce varianza alta? **Sì by design** — sopra soglia (`ENSEMBLE_DIVERGENCE_STD`, default 0.40) scatta fallback FinBERT; qui il meccanismo ha funzionato 176 volte, ma il tasso resta alto (problema noto, non nuovo — vedi [DAY-006]).
- News duplicate pesano più volte? **Sì per i near-duplicate da wire syndication** (content_hash diverso per boilerplate diverso) — vedi [DAY-003].
- Stessa news → segnali multipli? Solo se ri-fetchata su ticker diversi (comportamento per-ticker atteso) o se il dedup content-hash non la cattura (vedi [DAY-003]).
- Confidence bassa riduce il peso? **Sì** — `score = polarity × confidence` per costruzione (formula CLAUDE.md rispettata, verificato su più righe: es. score=-0.755 con confidence 0.821 su MS/GS).
- Modelli chiamati offline/background, mai nel trading loop? **Confermato** — `run_sentiment_worker` è un task Celery separato; `portfolio_scheduler` legge solo segnali già scritti.
- Rischio hallucination diretta in decisione? **Basso strutturalmente** (score numerico validato, no free-text in esecuzione) ma **il rischio reale è a monte, sull'attribuzione del ticker**, non sulla valutazione del sentiment — vedi [DAY-002].

---

## 6. Tabella Segnali Finali per Ticker (top 15 per volume, 07-13)

| Symbol | N segnali | Score medio | Score min | Score max | % fallback FinBERT |
|---|---:|---:|---:|---:|---:|
| MS | 55 | 0.059 | -0.755 | 0.658 | 78% |
| GS | 40 | 0.013 | -0.755 | 0.420 | 35% |
| MU | 38 | 0.009 | -0.330 | 0.372 | 53% |
| TSM | 24 | 0.020 | -0.210 | 0.641 | 71% |
| DIS | 14 | 0.020 | -0.460 | 0.308 | 50% |
| DB | 10 | -0.037 | -0.354 | 0.076 | 90% |
| AMD | 10 | -0.026 | -0.220 | 0.246 | 50% |
| SHEL | 7 | 0.060 | 0.011 | 0.224 | 43% |
| SPCX | 6 | 0.074 | -0.153 | 0.248 | 50% |
| NVDA | 6 | 0.042 | -0.100 | 0.285 | 33% |
| TM | 6 | 0.014 | -0.132 | 0.195 | 50% |
| CAT | 5 | 0.038 | 0.006 | 0.131 | 80% |
| C | 5 | 0.041 | 0.000 | 0.169 | 60% |
| META | 5 | -0.151 | -0.673 | 0.269 | 60% |
| BAC | 4 | 0.052 | 0.000 | 0.169 | 0% |

MS/GS ricevono il maggior volume di segnali del giorno ma **non sono mai stati tradati** — coerente col fatto che il resolver-shadow li marca sistematicamente a bassa confidenza (vedi [DAY-002]).

---

## 7. Tabella Ordini Generati/Eseguiti (2026-07-13)

34 ordini totali, **tutti `filled`**, 13 BUY / 21 SELL, 0 reject/cancel. Strategia: S1=21, S4=13.

| Symbol | Side | Qty | Prezzo fill | Ora fill | Strategia | Trade ID | Note |
|---|---|---:|---:|---|---|---|---|
| AMD,ARM,ASML,INTC,MRVL,MU,NOK,SOXX,TXN | SELL | var. | var. | 14:07:07-09 | S1 | 247,248,249,260,265,267,268,274,277 | stop_loss (cohort 07-10), batch 1/2 |
| DELL | BUY | — (notional $397.55) | 427.69 | 14:07:07 | S1 | 293 | apertura |
| PANW | BUY | — ($730.98) | 321.34 | 14:07:07 | S1 | 294 | apertura |
| WDC | BUY | — ($452.27) | 540.414 | 14:07:07 | S1 | 295 | apertura |
| XOM | BUY | — ($783.63) | 142.52 | 14:07:08 | S1 | 296 | apertura |
| PFE | SELL | 203.24 | 24.52 | 14:22:05 | S4 | 289 | portfolio_sell, **+$43.89** |
| SHEL | BUY | — ($1,501.38) | 83.31 | 15:07:06 | S4 | 297 | apertura |
| HOOD | BUY | — ($1,501.38) | 111.25 | 15:07:06 | S4 | 298 | apertura |
| META | BUY | — ($1,501.48) | 660.04 | 15:22:05 | S4 | 299 | apertura |
| BA | BUY | — ($1,199.75) | 217.99 | 15:52:05 | S4 | 300 | apertura |
| AMAT,CAT,TSM,VALE,XLK | SELL | var. | var. | 16:37:05-06 | S1 | 246,252,276,280,283 | stop_loss (cohort 07-10), batch 2/2 |
| TM | BUY | — ($1,993.83) | 174.98 | 17:22:11 | S4 | 301 | apertura |
| SHEL | SELL | 1.322 | 84.06 | 18:22:09 | S4 | 297 (tranche 1/3) | vedi [DAY-005] |
| DIS | BUY | — ($5,275.35) | 96.03 | 18:22:09 | S4 | 302 | apertura, notional anomalmente grande |
| TM | SELL | 11.395 | 174.31 | 19:07:06 | S4 | 301 | portfolio_sell |
| SPCX | BUY | — ($1,193.01) | 137.52 | 19:07:05 | S4 | 303 | apertura |
| JPM | BUY | — ($1,193.01) | 334.90 | 19:07:06 | S4 | 304 | apertura |
| SHEL | SELL | 0.418 | 84.132 | 19:22:05 | S1 | 297 (tranche 2/3) | vedi [DAY-005] |
| HOOD | SELL | 13.495 | 109.28 | 19:22:05 | S4 | 298 | segnale scaduto (age 4.4h) |
| CVX | BUY | — ($741.71) | 182.25 | 19:22:05 | S1 | 305 | apertura |
| META | SELL | 2.275 | 658.36 | 19:37:05 | S4 | 299 | segnale scaduto (age 4.4h) |
| SHEL | SELL | 16.281 | 84.03 | 19:52:04 | S1 | 297 (tranche 3/3) | vedi [DAY-005] |

Note: gli ordini BUY mostrano `qty=None` nell'endpoint `/api/orders` (probabile bug di serializzazione — Alpaca notional-order restituisce `filled_qty`, non `qty`; il qty reale è ricostruibile da `entry_notional/entry_price` in `trades`). Basso impatto operativo, ma rende l'endpoint inaffidabile per un audit rapido del lato BUY — vedi [DAY-010] considerazioni API a parte.

Nessun ordine duplicato nello stesso minuto sullo stesso simbolo; nessun ordine fuori dai 24 tick di ciclo; nessun ordine senza `decision_id` associato.

---

## 8. Tabella PnL/Rendimento (2026-07-13)

### Realizzato (trade chiusi con `exit_time` nel 07-13)

| Cohort | N trade | Net PnL totale |
|---|---:|---:|
| Stop-loss cohort S1 (aperto 07-10, chiuso 07-13 in 2 batch) | 14 | **-$240.87** |
| PFE (S4, portfolio_sell) | 1 | +$43.89 |
| SHEL (S4→S1 rebalance, 3 tranche — vedi [DAY-005]) | 1 | +$10.43 (probabile lieve sovrastima, vedi finding) |
| HOOD (S4, segnale scaduto) | 1 | -$29.67 |
| META (S4, segnale scaduto) | 1 | -$4.12 |
| TM (S4, portfolio_sell) | 1 | -$11.73 |
| **Totale realizzato 07-13** | **19** | **≈ -$232.07** |

### Non realizzato (posizioni aperte il 07-13, snapshot **al momento della query, 2026-07-14**, non a chiusura 07-13 — NON usare come rendimento di giornata)

| Symbol | Qty | Entry | Prezzo corrente (snapshot 07-14) | Unrealized P&L |
|---|---:|---:|---:|---:|
| DELL | 0.930 | 427.69 | 443.00 | +$14.23 |
| PANW | 2.275 | 321.34 | 330.99 | +$21.95 |
| WDC | 0.837 | 540.41 | 587.50 | +$39.41 |
| XOM | 5.498 | 142.52 | 145.21 | +$14.79 |
| BA | 5.504 | 217.99 | 217.00 | -$5.45 |
| DIS | 54.934 | 96.03 | 96.15 | +$6.59 |
| SPCX | 8.675 | 137.52 | 140.50 | +$25.85 |
| JPM | 3.562 | 334.90 | 327.00 | -$28.14 |
| CVX | 4.070 | 182.25 | 183.22 | +$3.95 |

**Slippage/costi:** colonne `cost_bps`, `cost_usd`, `slippage_est` presenti nello schema `trades` ma **NULL su tutte le 19 righe** del 07-13 — dato non popolato, non calcolabile senza modificare codice/dati. Non ricostruito.

**Dati mancanti per il PnL:** prezzo di chiusura ufficiale del 07-13 per marcare correttamente le posizioni ancora aperte a fine giornata (avremmo bisogno di una query storica Alpaca a EOD 07-13, non disponibile via le API esposte in questa sessione); breakdown costi/commissioni.

---

## 9. Analisi Correttezza Buy/Sell

| Check | Esito |
|---|---|
| Buy generati solo quando consentito (strategia approvata) | ✅ S1/S4 entrambe `approved=true`, nessun ordine da S2 (disabled) o S7 (research) |
| Sell/exit generati correttamente | ✅ (stop_loss, portfolio_sell, segnale scaduto — tutte causali legittime) |
| Stop-loss rispettati | ⚠️ Rispettati meccanicamente (config `stop_loss: 0.02, mode: fixed`), ma innescano un cluster ampio — vedi [DAY-004] |
| Signal flip rispettato | ✅ Nessun BUY+SELL contraddittorio sullo stesso segnale nello stesso ciclo |
| Max holding days rispettato | Non verificabile con certezza sul cohort 07-10→07-13 (mancano `stop_*` metadata su quelle righe); nessun parametro esplicito di "max holding days" trovato in config oltre al max_age 4h dei segnali S4 |
| Rebalance band rispettata | ✅ Le tranche SHEL (2.5%→1.3%→1.2%→0%) sono coerenti con un rebalance progressivo, non un errore di banda |
| Niente ordini duplicati | ✅ verificato su tutti i 34 ordini |
| Niente ordini contrari ravvicinati senza rationale | ✅ ogni SELL ha un `reason` esplicito in `execution_decisions` |
| Niente ordini su ticker non consentiti | ✅ tutti simboli noti/liquidi |
| Niente ordini fuori orario | ✅ tutti entro 14:07-19:52, dentro l'orario reale di mercato |
| Niente trade su dati stale | ✅ meccanismo di `max_age` per segnali S4 attivo e osservato in azione (HOOD, META) |
| Niente trade se LLM output non valido | ✅ fallback FinBERT sempre usato in caso di divergenza, mai un output grezzo non validato |
| Niente trade se circuit breaker attivo | ✅ nessun kill-switch attivo osservato, `constraints_fired=[]` su tutti i 24 cicli |
| Niente trade se strategia disabilitata | ✅ |
| Paper/live coerente | ✅ **100% paper** per l'intera giornata |
| Idempotenza su retry Celery | ✅ **12 `SIGNAL_DUPLICATE_SKIP` osservati** in `audit_log` — il guard idempotente ha correttamente bloccato re-invii duplicati per HOOD/SHEL/META/BA nello stesso `session_date` |
| Reconciliation ordini↔fill↔posizioni | ⚠️ **Fallisce per SHEL** — vedi [DAY-005]; per tutti gli altri 33 ordini la reconciliation è pulita 1:1 |

---

## 10. Anomalie Trovate

### [DAY-001] Disallineamento DST tra finestra Celery e mercato reale — spreco sistemico di segnali

- Tipo: Bug
- Area: Ops / Signal
- Evidenza:
  - file/log/tabella: `src/workers/celery_app.py` righe 66, 129-134 (crontab `minute="*/15", hour="14-21"`); `src/workers/portfolio_scheduler.py` righe 1178-1190 (`trading_client.get_clock().is_open`); tabelle `portfolio_cycles`, `sentiment_signals`, `news_log`
  - timestamp: ingestion/sentiment attivi solo da 14:02 UTC (non 13:30) e fino a 21:45 UTC (non 20:00); ultimo `portfolio_cycles` del giorno: 19:52:00.63
  - snippet/query: `SELECT count(*) FROM sentiment_signals WHERE generated_at >= '2026-07-13 19:52:00+00'` → 89; `SELECT date_trunc('day',timestamp), max(timestamp) FROM portfolio_cycles GROUP BY 1` → 19:52 identico su 07-07,08,09,10,13
- Descrizione: il crontab di ingestion/sentiment-worker usa una finestra UTC fissa (14:00-21:00) che corrisponde a mercato 9:00-16:00 ET **solo in orario solare (EST)**. In estate (EDT, UTC-4, in vigore ora) il mercato reale è 13:30-20:00 UTC. Il `portfolio_scheduler` interroga correttamente l'orologio reale di Alpaca e si ferma a mercato chiuso (~19:52 UTC, ultimo tick prima delle 20:00), ma l'ingestion/sentiment-worker non ha lo stesso guard e continua fino alle ~21:45 UTC.
- Impatto: (a) i primi ~30 minuti di sessione (13:30-14:00 UTC), spesso i più ricchi di notizie/volatilità, non vengono coperti da alcuna ingestion; (b) ~89 segnali/giorno (≈29% del volume totale di sentiment_signals) vengono generati dopo la chiusura reale, non arrivano mai a un ciclo di portfolio quel giorno, e per il giorno successivo saranno quasi certamente scaduti rispetto al gate di freschezza (`MAX_NEWS_AGE_HOURS`/max_age 4h per S4) — spesa LLM reale (budget, latenza, carico Ollama Cloud) totalmente non monetizzabile in decisione.
- Severità: High
- Confidenza: High (pattern osservato identico su 5 giorni consecutivi campionati, spiegazione cross-validata via codice)
- Azione consigliata: allineare la crontab Celery all'orario di mercato reale con DST awareness (usare l'orologio Alpaca anche per il gate di ingestion/sentiment-worker, o calcolare la finestra a runtime da un calendario di mercato invece di un crontab UTC statico).
- Test/monitor consigliato: alert giornaliero se `count(sentiment_signals generated dopo l'orario di chiusura reale del giorno)/count(totale) > soglia`; test di regressione che verifichi la finestra effettiva contro il calendario NYSE per un campione di date EST e EDT.

### [DAY-002] Ticker misattribuiti tra i segnali di score più estremo della giornata

- Tipo: Bug / Rischio
- Area: News / Signal
- Evidenza:
  - file/log/tabella: `sentiment_signals` join `news_log`; `news_resolved_entities`
  - timestamp: 2026-07-13 18:30:32 (MS/GS, score -0.755), 15:45:33 (META, score -0.673), 15:30:09 / 16:15:51 / 15:45:17 (MS, score +0.53/+0.64/+0.66)
  - snippet/query: `SELECT symbol, score, model_id, title FROM sentiment_signals s JOIN news_log n ON s.news_log_id=n.id ORDER BY abs(score) DESC LIMIT 10` → MS/GS abbinati a "Musk's Net Worth Drops Below $900 Billion With SpaceX Nearing IPO Value"; META abbinato a "Why Is Nebius Stock Falling on Monday?"; MS abbinato a notizie su Verra Mobility (VRRM), TWFG, Seagate (STX)
- Descrizione: 7 dei 10 segnali con `|score|` più alto del giorno sono generati da articoli GDELT il cui soggetto reale è un'altra azienda (co-menzione o keyword-tagging GDELT, non subject-matter). Il resolver deterministico shadow (`news_resolved_entities`) marca correttamente **309/396 (78%)** delle risoluzioni del giorno come `NO_TRADE_LOW_RESOLUTION_CONFIDENCE` e altre 87 (22%) come `NO_TRADE_NOT_TRADABLE` — inclusi tutti gli esempi sopra — ma per design (QX-01, misurazione prima di enforcement) questi segnali continuano comunque ad alimentare `sentiment_signals` e la pipeline di decisione.
- Impatto: MS/GS non sono mai stati tradati (nessuna posizione aperta), quindi nessun impatto P&L diretto oggi. Ma lo stesso canale GDELT ha contribuito (fra altri articoli più pertinenti) al segnale aggregato che ha portato al BUY DIS da $5,275 — la size più grande della giornata. Questo è esattamente il rischio "worst-case error" descritto in CLAUDE.md (ticker errato = ordine su titolo non correlato), oggi confinato allo stadio di segnale ma con evidenza diretta che, se l'enforcement fosse live, ~94% delle risoluzioni GDELT del giorno verrebbe bloccato.
- Severità: High
- Confidenza: High
- Azione consigliata: nessuna azione di codice richiesta ora (comportamento coerente col piano QX-01 già in corso) — raccomandato accelerare la valutazione del golden label set per decidere se attivare enforcement sulla fascia `NO_TRADE_LOW_RESOLUTION_CONFIDENCE`, dato il volume (78% del traffico giornaliero).
- Test/monitor consigliato: dashboard giornaliera "% segnali con verdict shadow NO_TRADE che sarebbero comunque entrati in una decisione BUY/SELL" per quantificare l'esposizione reale prima del flip.

### [DAY-003] Wire syndication near-duplicate elude il dedup content-hash

- Tipo: Bug
- Area: News / Ops
- Evidenza:
  - file/log/tabella: `news_log` (colonna `content_hash`), ticker=DIS
  - timestamp: 10 articoli fetchati tra 18:15:26 e 21:30:47 del 07-13
  - snippet/query: `SELECT content_hash, title FROM news_log WHERE ticker='DIS' AND title LIKE '%California%'` → 10 righe, 10 `content_hash` **tutti distinti**, stesso testo di base "California, 11 states suing to block Paramount's $110 billion Warner Bros deal" ripubblicato da 8-10 siti di stazioni radio locali (GDELT syndication)
- Descrizione: il content-hash è sensibile a differenze minori nel testo (probabile branding/suffix per-stazione nel titolo o nel body), quindi non riconosce ripubblicazioni quasi-identiche dello stesso comunicato/notizia come duplicati. Ognuna genera una riga `news_log` distinta e un `sentiment_signals` distinto (almeno 2 hanno innescato una vera chiamata ensemble, non solo FinBERT).
- Impatto: pseudo-replicazione dell'evidenza per DIS (lo stesso evento pesa fino a ~10x nell'aggregazione invece di 1x), più spreco di budget LLM.
- Severità: Medium
- Confidenza: High
- Azione consigliata: dedup near-duplicate (es. similarity su titolo normalizzato/testo, o dedup su `(published window, primary entity, normalized headline)`), non solo hash esatto.
- Test/monitor consigliato: contatore giornaliero "articoli con similarity >0.9 al titolo normalizzato non deduplicati" come regression gate.

### [DAY-004] Cluster stop-loss simultaneo sul cohort S1 di venerdì 07-10

- Tipo: Rischio (non un bug nuovo — corrobora [project_stop_loss_evidence_2026_07_10])
- Area: Risk / PnL
- Evidenza:
  - file/log/tabella: `trades` (id 246-283)
  - timestamp: entry tutte 2026-07-10 14:07:01.160712+00; exit in due batch: 2026-07-13 14:07:01.636192+00 (9 posizioni) e 2026-07-13 16:37:00.59273+00 (5 posizioni)
  - snippet/query: `SELECT * FROM trades WHERE entry_time='2026-07-10 14:07:01.160712+00'` → 14 righe, tutte `exit_reason='stop_loss'`
- Descrizione: l'intero cohort di 14 posizioni S1 aperte nello stesso ciclo di venerdì 07-10 è stato liquidato per stop-loss in due tick discreti il lunedì successivo (gap di weekend), con perdita aggregata di **-$240.87**. Config: `stop_loss: 0.02, stop_loss_mode: fixed`. Le righe non hanno `stop_strategy`/`stop_mode`/`stop_vol_at_entry` popolati (colonne pre-esistenti l'introduzione di quei metadata), quindi non è possibile ricostruire con precisione se ogni singolo stop sia stato innescato da rumore infra-2σ come già documentato per trade dello stesso tipo il 07-10.
- Impatto: -$240.87 è la voce di P&L singola più grande della giornata (più del doppio delle uscite S4 combinate). Conferma con dati freschi il problema già in redesign (vol_scaled stop, gate Kimi in corso).
- Severità: High
- Confidenza: High
- Azione consigliata: nessuna nuova azione — proseguire il gate della redesign stop-loss già pianificata (`docs/superpowers/plans/2026-07-11-stop-loss-redesign.md`); considerare priorità più alta dato il costo quantificato oggi.
- Test/monitor consigliato: alert su "N posizioni chiuse per stop_loss nello stesso tick" > soglia (es. >3) come segnale di correlazione sistemica non gestita da un cap di settore/cohort.

### [DAY-005] Uscita multi-tranche SHEL non riconciliata nel ledger `trades`

- Tipo: Bug
- Area: PnL / Orders / Data
- Evidenza:
  - file/log/tabella: `trades` id 297; `/api/orders` (order_id `5e96b54a`, `f4f55d7e`, `9ee39316`); `execution_decisions` id 2784, 2794, 2800, 2803
  - timestamp: entry 15:07:06 (18.021 az @ 83.31); sell tranche 18:22:09 (1.322 az @84.06, trade_id=297), 19:22:05 (0.418 az @84.132, trade_id=NULL), 19:52:04 (16.281 az @84.03, trade_id=NULL)
- Descrizione: la posizione SHEL è stata smontata in 3 vendite parziali su 3 cicli di portfolio distinti (rebalance progressivo 2.5%→1.3%→1.2%→0%). La riga `trades.id=297` registra `exit_price=84.06` (prezzo della sola prima tranche) applicato per costruzione all'intera quantità originale (18.021 az.), sovrastimando lievemente il gross_pnl (~$13.52 registrato vs ~$13.10 con media pesata reale ≈84.037) e datando l'uscita alle 18:22 invece delle 19:52 reali. Le tranche 2 e 3 (16.7 az. su 18.0, cioè il 93% della size) non hanno alcuna riga `trades` associata (`trade_id=NULL`) — invisibili a qualunque rollup di PnL per trade/strategia. In più, l'ordine della prima tranche espone `decision_id=2784` (la decisione di BUY originale) invece di `2794` (la vera decisione SELL che l'ha causato), inquinando l'attribuzione causale nell'audit trail.
- Impatto: PnL per-trade leggermente sbagliato su questo caso specifico (~$0.4, basso in valore assoluto qui, ma il meccanismo è strutturale e potrebbe pesare molto di più su spread prezzo più ampi tra tranche); più in generale, ogni volta che una posizione viene smontata in >1 vendita parziale su cicli separati, il ledger `trades` sottostima sistematicamente ciò che è effettivamente accaduto sul book.
- Severità: High
- Confidenza: High
- Azione consigliata: modellare l'uscita di una posizione come N "exit legs" collegati a un unico trade (o ricalcolare `exit_price` come media pesata su tutte le vendite associate allo stesso `entry_order_id`) invece di assumere un singolo exit fill; correggere il join usato da `/api/orders` per popolare `decision_id` con la decisione effettivamente causante l'ordine, non quella di entry.
- Test/monitor consigliato: query di reconciliation periodica "somma qty delle vendite per entry_order_id vs trades.qty" con alert su mismatch; test che verifichi `sum(exit orders qty) == trades.qty` per ogni trade chiuso.

### [DAY-006] Fallback rate FinBERT al 57% — problema noto, confermato con dati freschi

- Tipo: Rischio (tracciato — non nuovo)
- Area: LLM
- Evidenza:
  - file/log/tabella: `sentiment_signals` (176/309 fallback, reasoning="FinBERT fallback (ensemble divergence)")
- Descrizione: coerente con `project_ensemble_divergence_order_drought` (memoria: 70-86% storicamente, soglia alzata 0.30→0.40 inefficace). Oggi 57% — leggero miglioramento ma ancora la maggioranza dei segnali S4 non usa l'ensemble a due modelli come da design.
- Impatto: la parte "DK-CoT ensemble" del sistema, per più della metà dei segnali, è di fatto sostituita da FinBERT (modello locale, meno sofisticato).
- Severità: Medium
- Confidenza: High
- Azione consigliata: nessuna nuova — il problema resta aperto nel backlog citato in memoria (persist dei raw output divergenti, valutazione swap coppia o terzo modello).
- Test/monitor consigliato: già presente in memoria; suggerito solo di aggiungere il breakdown orario (già disponibile in questa analisi) al monitor esistente per verificare se è uniforme o a burst.

### [DAY-007] Incidente selezione modelli "all" a inizio giornata — già rilevato e corretto lo stesso giorno

- Tipo: Corretto (rischio residuo Low)
- Area: LLM / Ops
- Evidenza:
  - file/log/tabella: `llm_responses` (model_id='kimi-k2.6:cloud', 5 righe, 14:02:01-14:03:35); Redis `config:sentiment_llm_models` = `glm52,gptoss` (verificato ora)
- Descrizione: coerente con l'incidente già in memoria (`project_s4_program_package`): la selezione modelli è tornata brevemente al default "all" (che include `kimi`, `in_all=True`), poi corretta. La finestra kimi (14:02-14:03) e l'inizio delle risposte gpt-oss (14:09:32) sono coerenti con "corretto e verificato live alle 14:16" citato in memoria.
- Impatto: 5 chiamate kimi, tutte marcate `eligible=false` — nessun segnale corrotto.
- Severità: Low
- Confidenza: High
- Azione consigliata: nessuna (hardening UI già in valutazione per prevenire reversioni al default lato frontend).
- Test/monitor consigliato: alert su qualunque comparsa di `model_id` non nella coppia attesa in `llm_responses`.

### [DAY-008] Herfindahl index = 1.000000 nel risk report — valore sospetto

- Tipo: Ambiguità / possibile Bug
- Area: Risk
- Evidenza:
  - file/log/tabella: `risk_reports`, unica riga 2026-07-13 22:30:00
  - snippet/query: `total_exposure=0.263829, herfindahl_index=1.000000, combined_drawdown=0.062087`
- Descrizione: un HHI esattamente 1.000000 indica concentrazione totale su un singolo bucket, incoerente con un'esposizione del 26.4% distribuita su ~30+ posizioni aperte quel giorno. Non è stato verificato il codice di calcolo per confermare se sia un placeholder/default o un bug nella formula (es. calcolo a livello strategia con denominatore errato) — non ho approfondito per limiti di tempo.
- Impatto: se l'HHI è realmente rotto, qualunque alert di concentrazione basato su questa metrica è inefficace (falso negativo o falso positivo costante).
- Severità: Medium
- Confidenza: Low/Medium (non verificato a livello di codice)
- Azione consigliata: ispezionare la funzione che popola `risk_reports.herfindahl_index` e validare contro un calcolo manuale sulle posizioni reali del 07-13.
- Test/monitor consigliato: unit test che calcoli HHI atteso su un book sintetico noto e lo confronti con l'output della funzione.

### [DAY-009] Log Docker non disponibili per il 07-13 — gap di auditabilità

- Tipo: Ambiguità / Rischio operativo
- Area: Ops / Data
- Evidenza:
  - file/log/tabella: `docker inspect alembic-worker-1 --format '{{.State.StartedAt}}'` → `2026-07-14T12:11:21Z`; `docker compose logs worker --since 48h` → 131 righe totali, tutte post-riavvio
- Descrizione: i container `worker`/`worker-inference` sono stati riavviati il 07-14 alle 12:11 UTC (causa fuori scope di questa analisi), troncando la log history Docker. Nessun log applicativo (ERROR/WARNING, contatori `skipped_stale`/`skipped_neutral`/`skipped_not_tradable`/`finbert_fallbacks` del task Celery, eventuali stack trace) è recuperabile per il 07-13. Questi contatori vengono restituiti solo come return-value del task Celery, mai persistiti in una tabella queryable.
- Impatto: diverse ricostruzioni in questo report (gap ingest queued→persistito, causa esatta di eventuali errori silenziosi) si basano solo su inferenza dallo stato DB, non su conferma diretta nei log.
- Severità: Medium
- Confidenza: High
- Azione consigliata: instradare i log applicativi verso uno store persistente/esterno (non solo stdout Docker con retention legata al ciclo di vita del container); persistere i contatori di skip del sentiment-worker in una tabella (es. estensione di `ingestion_stats_daily` o nuova `sentiment_worker_stats_daily`).
- Test/monitor consigliato: verificare che la retention dei log applicativi sopravviva ai riavvii container prima del prossimo controllo giornaliero.

### [DAY-010] Token Bearer JWT fornito non valido sull'API — richiesto workaround X-API-Key

- Tipo: Ambiguità operativa
- Area: Ops
- Evidenza:
  - file/log/tabella: risposta HTTP diretta
  - snippet/query: `curl -H "Authorization: Bearer <token>" .../api/decisions` → `403 {"detail":"Invalid or expired JWT token"}`; stesso valore come `X-API-Key` → `200 OK`
- Descrizione: il token fornito nel prompt operativo di questa sessione non è un JWT valido per lo schema `Authorization: Bearer`, ma funziona come `X-API-Key` (vedi `src/api/auth.py`). Il template/runbook usato per queste sessioni autonome sembra assumere lo schema sbagliato.
- Impatto: nessuno sul risultato finale (workaround trovato e usato per l'intera analisi), ma rischio che una futura sessione autonoma senza questo fallback fallisca l'intera raccolta dati via API.
- Severità: Low
- Confidenza: High
- Azione consigliata: aggiornare il template/runbook della sessione forensic giornaliera per usare `X-API-Key`, o emettere correttamente un JWT via `/api/auth/login` se si vuole mantenere Bearer.
- Test/monitor consigliato: n/a (fix di configurazione/documentazione).

---

## 11. False Positive / Aree Risultate Corrette

- **SELL con sentiment positivo (pattern bug A5):** verificato specificamente sulle SELL con reason "segnale scaduto" (HOOD score dichiarato +0.172, META +0.269, SHEL +0.060) — **non è un'inversione di segno**: sono uscite per età del segnale (>4h max_age), il segno del sentiment è irrilevante per questo trigger by design. Nessuna vendita innescata da un segnale S4 realmente e attivamente positivo osservata.
- **Ordini duplicati nello stesso minuto (race condition scheduler):** cercato su tutti i 34 ordini del giorno — nessun caso trovato.
- **Pyramiding (BUY ripetuto >3 volte senza SELL):** nessun simbolo ha ricevuto più di 1 BUY consecutivo il 07-13; anzi, l'`audit_log` mostra **12 eventi `SIGNAL_DUPLICATE_SKIP`** (HOOD, SHEL×3, META, BA×4) che dimostrano il guard di idempotenza per `session_date` funzionante correttamente contro re-invii duplicati dello stesso segnale.
- **Fallback su tutti i simboli (Ollama giù):** non riscontrato — fallback sempre per divergenza ensemble, mai per timeout; nessuna ora con fallback rate=100%.
- **Paper/live:** confermato paper al 100%, nessuna ambiguità nei dati.
- **Circuit breaker / risk limits:** `constraints_fired=[]` su tutti i 24 cicli, nessun blocco necessario né mancato rilevato.
- **Timestamp futuri / anomalie di fuso orario nelle news:** nessuno trovato in `news_log` per il 07-13 (il problema di fuso è a livello di *scheduling*, non di dati ingested — vedi [DAY-001]).
- **Score < 0.05 che generano ordini:** il campo `score` in `trades`/`execution_decisions` per S1 **coincide per costruzione col peso di portafoglio** (es. "portfolio weight 1.2%" = score 0.012), non con una metrica di confidenza/significatività — quasi tutte le entry S1 hanno score <0.05 by design (sizing frazionato su molte posizioni), non è un bypass di soglia. Da notare come possibile fonte di confusione terminologica in audit futuri, ma non un bug.

---

## 12. Dati Mancanti o Non Accessibili

- Log applicativi Celery/worker del 07-13 (container riavviati 07-14 12:11 UTC) — vedi [DAY-009].
- Contatori di skip del sentiment-worker (`skipped_stale`, `skipped_neutral`, `skipped_not_tradable`) non persistiti in tabella — solo return-value Celery, non recuperabile oggi.
- Prezzo di chiusura ufficiale EOD del 07-13 per marcare correttamente le 9 posizioni ancora aperte a fine giornata (il valore mostrato in §8 è uno snapshot al 07-14, non l'EOD 07-13) — servirebbe una query storica Alpaca bars per `2026-07-13` close.
- Colonne `cost_bps`, `cost_usd`, `slippage_est` in `trades`: schema presente, dati NULL su tutte le righe del giorno — non calcolabile senza intervento su pipeline dati.
- Codice di calcolo di `herfindahl_index` non ispezionato — vedi [DAY-008].
- Causa del riavvio dei container `worker`/`worker-inference` avvenuto il 07-14 12:11 UTC: fuori dallo scope temporale di questa analisi (07-13), non indagata.

---

## 13. Raccomandazioni Immediate

1. Allineare la finestra Celery di ingestion/sentiment-worker all'orario di mercato reale (DST-aware) — [DAY-001], impatto quantificato ~29% di spreco giornaliero sul volume di segnali.
2. Correggere la riconciliazione multi-tranche in `trades`/`/api/orders` — [DAY-005], integrità del ledger PnL.
3. Persistere i log applicativi/contatori di skip in modo sopravvivente ai riavvii container — [DAY-009], prerequisito per audit futuri affidabili.
4. Verificare la formula di `herfindahl_index` — [DAY-008], possibile falso segnale di rischio (in entrambe le direzioni).
5. Aggiornare il runbook di autenticazione API per le sessioni forensi autonome (`X-API-Key`, non Bearer) — [DAY-010].

## 14. Test o Monitor da Aggiungere

- Alert giornaliero: % di `sentiment_signals` generati dopo l'orario di chiusura reale (calendario NYSE-aware) sul totale.
- Alert su N posizioni chiuse per `stop_loss` nello stesso tick di ciclo (soglia, es. >3) come segnale di correlazione di cohort non gestita.
- Query di reconciliation periodica: somma qty vendite per `entry_order_id` vs `trades.qty`.
- Dashboard "% segnali con verdict resolver-shadow NO_TRADE che sarebbero comunque entrati in una decisione" per quantificare l'esposizione prima dell'enforcement QX-01.
- Contatore giornaliero di articoli near-duplicate (similarity titolo) non catturati dal content-hash dedup.
- Unit test per `herfindahl_index` contro un book sintetico noto.

## 15. Ticket Tecnici Suggeriti

- **TICKET-A:** Ingestion/sentiment-worker: sostituire la finestra crontab UTC fissa con un gate basato su calendario di mercato DST-aware (stesso pattern già usato in `portfolio_scheduler._is_ks_active_failclosed`/Alpaca clock). Rif. [DAY-001].
- **TICKET-B:** `trades`: modellare uscite multi-tranche (più exit fill per un singolo entry) invece di un singolo `exit_price`/`exit_time`; correggere il join `decision_id` in `/api/orders` per usare la decisione causante l'ordine, non quella di entry. Rif. [DAY-005].
- **TICKET-C:** Persistere in tabella i contatori `skipped_stale`/`skipped_neutral`/`skipped_not_tradable`/`finbert_fallbacks` del sentiment-worker (oggi solo return-value Celery). Rif. [DAY-009].
- **TICKET-D:** Dedup near-duplicate per wire-syndication (GDELT ripubblicato da più siti locali). Rif. [DAY-003].
- **TICKET-E:** Verificare/correggere il calcolo di `herfindahl_index` in `risk_reports`. Rif. [DAY-008].
- **TICKET-F:** `/api/orders`: popolare `qty` anche per ordini BUY notional-based (oggi sempre `None`). Rif. §7.
- **TICKET-G:** Aggiornare runbook auth per sessioni forensi autonome a `X-API-Key`. Rif. [DAY-010].

## 16. Stato Sistema

- **Ollama:** 100% up il 07-13, **0 ore di downtime rilevate** (0 fallback per timeout su 176 fallback totali).
- **FinBERT fallback rate:** 176/309 = **57.0%** delle decisioni di sentiment, interamente per divergenza ensemble (soglia `ENSEMBLE_DIVERGENCE_STD`), non per indisponibilità o budget.
- **Worker restart events:** nessuna evidenza di restart durante l'orario di mercato del 07-13 (cadenza dei 24 `portfolio_cycles` completa e senza buchi tra 14:07 e 19:52). Un restart dei container `worker`/`worker-inference` **è avvenuto il 07-14 12:11 UTC** (fuori dalla finestra di analisi, causa non indagata) e ha reso indisponibili i log Docker per il 07-13 — vedi [DAY-009].
