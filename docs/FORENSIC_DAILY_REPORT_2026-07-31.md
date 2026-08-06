# Forensic Daily Report — 2026-07-31

Analista: sessione autonoma read-only. Timezone operativo: **UTC** (`src/workers/celery_app.py:51-52`,
`timezone="UTC", enable_utc=True`; tutti i cron della tabella a inizio file sono espressi in UTC).
Nessuna ambiguità di timezone nel codice — vedi [DAY-010] per un'ambiguità separata, sull'autenticazione
API del runbook.

Periodo di sola osservazione attivo (`docs/evidence/OBSERVATION_CHARTER.md`, iniziato 2026-08-03): nessuna
proposta di taratura. I ticket proposti in questo report (§13, §15) sono limitati a difetti di
correttezza — cioè quelli che, se non corretti, renderebbero sbagliata l'evidenza raccolta nelle
prossime settimane.

Fonte parallela già esistente sullo stesso giorno: `docs/ALPHA_MISS_REPORT_2026-07-31.md` (analisi
mover/miss sui 96 simboli watchlist, prodotta 2026-08-01). I numeri di P&L realizzato, split S1/S4 e i
finding [F-001]/[F-002] lì riportati sono stati **riverificati indipendentemente** con query dirette in
questo report (§8) e coincidono. Questo report copre l'intera pipeline end-to-end (non solo i mover) e
aggiunge scoperte nuove non presenti nell'alpha-miss report (§10).

---

## 1. Executive summary

- Pipeline end-to-end integra: 177 news ingerite (2 fonti), 179 segnali sentiment (100% con
  `news_log_id` popolato), 415 execution_decisions (17 BUY, 11 SELL, 386 SKIP_THRESHOLD, 1 SKIP_STALE),
  16 trade aperti/chiusi nel giorno. Nessun worker restart, nessun halt operatore, gate S4 (#163/#164)
  tenuto (soglia feedback osservata a 0.300, non disarmata).
- **Nessuna evidenza di Ollama down**: 63/179 segnali (35%) in fallback, ma tutti spiegabili da
  confidence/divergenza sotto soglia, zero errori di connessione nei log worker-inference del giorno.
  `fallback_counters` mostra reset multipli, mai uno streak prolungato.
- Guardrail funzionanti e verificati: pyramiding guard (#P0-05), duplicate-signal guard (S4), guard
  fallback-in-ranking (#108), reversal cooldown — tutti osservati in azione, zero violazioni trovate su
  roundtrip <30min, ordini duplicati nello stesso minuto, SELL-su-sentiment-positivo (bug A5 pattern).
- **4 anomalie nuove di correttezza/auditabilità** trovate in questo giro (non presenti in
  ALPHA_MISS_REPORT): metrica drawdown incoerente nello stesso risultato ([DAY-001]), decay monitor che
  confronta metriche pipeline-globali contro 3 baseline per-strategia distinte incluso un S2 mai tradato
  ([DAY-002]), un alert Telegram non consegnato (400) ([DAY-003]), e 7 decisioni BUY loggate senza
  ordine e senza causa persistita — solo nei log testuali ([DAY-004]).
- P&L realizzato del giorno: **+$6.37** (S1 −$11.17, S4 +$0.64, ABBV +$16.90 non attribuibile — [F-002]
  già noto). MTM giornaliero stimato book intero +$255.88 (Alpaca).

## 2. Verdict finale

**OK con warning.**

La pipeline ha funzionato end-to-end correttamente nei suoi meccanismi core (idempotenza, guard
anti-pyramiding, anti-duplicati, gate soglia). Le anomalie trovate sono di **osservabilità e coerenza
delle metriche di rischio/decay**, non di esecuzione errata di ordini: nessun trade è stato piazzato in
violazione delle regole di business. Il warning è motivato da [DAY-001] e [DAY-002], che se non corrette
possono produrre letture sbagliate delle metriche di rischio/decay proprio nel periodo in cui la carta di
osservazione le userà per decidere.

## 3. Timeline del 2026-07-31 (UTC)

| Ora UTC | Componente | Evento | Fonte |
|---|---|---|---|
| 00:00–06:xx | worker-inference | Polling Telegram continuo (getUpdates ogni 5s), nessuna attività di trading (pre-market) | docker logs worker-inference |
| 13:19:38 | alpaca_benzinga | Primo articolo ingerito del giorno | news_log min(published_at) |
| 13:30 | — | Apertura market hours (definizione operativa 13:30–20:00 UTC) | CLAUDE.md / celery_app.py |
| 14:00–18:00 | gdelt_gkg | Finestra di ingest GDELT (ogni 15 min, Mon-Fri 14:00-21:00 UTC) | news_log min/max published_at; celery_app.py |
| 14:00:00.480 | sentiment worker | 301 item in coda scartati come stale (>18h, backlog residuo del 07-30 sera) — drop corretto per evitare sentiment "fresco" su news vecchia | news_queue_drops (198 benzinga + 103 gdelt) |
| 14:16:27 | worker-inference | Primo run sentiment worker: 7 processed, 4 ensemble_success, 3 finbert_fallbacks (AMZN, MSFT, AAPL, META, NVDA, SHEL) | docker logs worker-inference |
| 14:22:00 | portfolio-cycle | BUY QQQ (S1), BUY AMZN (S4, score +0.795, trade 590); SELL ARM (S1); SELL HOOD/INFY/ORCL (S4 signal **expired**, age 18.6-20.9h > max 4h — no counter-signal, posizione chiusa) | execution_decisions 5269-5274; trades 585,587,588 |
| 14:52:00 | portfolio-cycle | BUY ORCL (S4, score +0.385, trade 591); chiusura ARM (net +$45.28) | execution_decisions 5299-5300; trades 586,591 |
| 15:07:00 | portfolio-cycle | SELL SBUX ([s1_weight_drop], chiude trade 579, net −$8.28) | execution_decisions 5316; trades 579 |
| 15:22:00 | portfolio-cycle | BUY SBUX (S1 momentum, trade 592) | execution_decisions 5334 |
| 16:07:00 | portfolio-cycle | SELL QQQ ([s1_weight_drop], chiude 589, net +$1.22); SELL ABBV (**sentiment_reversal**, score −0.640 < −0.35, chiude trade 245 aperto 07-10, net +$16.90 — [F-002], `stop_strategy` NULL) | execution_decisions 5385-5386; trades 589,245 |
| 16:07–17:52 | portfolio-cycle | **7 cicli consecutivi** (16:22,16:37,16:52,17:07,17:22,17:37,17:52): decisione persistita `BUY ABBV` con rationale S1 generico, ma bloccata a livello di codice da "Reversal cooldown" — nessun `order_id`, causa reale non persistita → **[DAY-004]** | execution_decisions 5404,5420,5437,5455,5475,5495,5514; docker logs worker |
| 17:07:00 | portfolio-cycle | Chiusura SBUX (trade 592, net −$4.11) | trades 592 |
| 17:22:00 | portfolio-cycle | BUY MA (S4, score +0.350, trade 594) | execution_decisions 5476; trades 594 |
| 17:52:00 | portfolio-cycle | BUY SBUX (trade 595); SELL ORCL (**whipsaw guard**, score +0.000, chiude 591, net +$2.16) | execution_decisions 5514-5516; trades 591,595 |
| 18:07:00 | portfolio-cycle | Cooldown ABBV scaduto: **BUY ABBV eseguito** (trade 596, primo ordine riuscito dopo 7 tentativi bloccati) | execution_decisions 5534; trades 596 |
| 18:37:00 | portfolio-cycle | SELL AMZN (**whipsaw guard**, score +0.080, chiude 590, net +$15.53) | execution_decisions 5575; trades 590 |
| 19:22:00 | portfolio-cycle | BUY MSFT (S4, score +0.5425, trade 597) — entry tardivo, 47 min dalla generazione segnale, ~72 min dalla chiusura | execution_decisions 5627; trades 597 |
| 19:30:16 | worker-inference | "Ensemble diverged for IWM, using FinBERT fallback" — unico evento di divergenza esplicita loggato nel giorno | docker logs worker-inference |
| 19:37:00 | portfolio-cycle | BUY AMZN (S4, score +0.664, trade 598, ri-apertura stesso giorno) | execution_decisions 5645; trades 598 |
| 19:52:07-08 | portfolio-cycle (EOD tick) | S1: drop 2 ticker sparsi/stale-tailed (AZN, SPCX); S4: drop 5 segnali fallback dal ranking BUY (#108); S4: drop **21/38 (55%)** segnali stale (age>4h) → [DAY-005]; duplicate-guard corretto per MA(6004)/MSFT(6068) "already fired today"; pyramiding guard (#P0-05) skippa correttamente ~40 BUY su simboli con trade già aperto | docker logs worker |
| 20:30:00 | worker (loss feedback) | WARNING: "Loss feedback triggered for S1: EWMA R −0.52, 1 consecutive losses, rolling P&L $−221.42 — threshold 0.30→0.00, regime scale 0.20→0.20" | docker logs worker |
| 20:30:00 | worker (Telegram) | **Alert Telegram NON consegnato**: "Failed to send alert: Client error '400 Bad Request'" → [DAY-003] | docker logs worker |
| 21:00:00 | decay-monitor (cron) | DECAY CRITICAL [S2]: "Max drawdown exceeds baseline by 6.9pp: 12.9% vs 6.0%" — S2 è disabilitato (0% allocazione, mai un trade in `trades`) e la metrica usata è pipeline-globale, non specifica di S2 → [DAY-002] | docker logs worker; decay_reports; ARCHITECTURE.md:209 |
| 22:00:17 | forward-return worker | Completato: updated=945, skipped=115, errors=0 | docker logs worker |
| 22:30:00.995 | risk_monitor_task | RISK ALERT: "Strategy portfolio drawdown 13.9% exceeds 10%" (report id=49) — ma la colonna `combined_drawdown` dello **stesso** report vale 0.0124 (1.24%) → [DAY-001] | risk_reports id=49 |
| 22:45:06 | counterfactual worker | Completato: updated=346, skipped=40, errors=0, total_decisions=386 | docker logs worker |
| *(fuori finestra)* 08-01 11:37 | mobile reconciliation | "Terminal mobile order reconciliation failed" — connessione rifiutata verso `paper-api.alpaca.markets` | docker logs worker — **evento del giorno successivo, riportato solo per §16 stato sistema, non nella timeline del 07-31** |

## 4. Tabella news ingest

| Fonte | Righe in `news_log` (07-31) | `extraction_method` | fetched (cum. giorno) | queued (cum. giorno) | duplicates (cum. giorno) | discarded_no_ticker |
|---|---:|---|---:|---:|---:|---:|
| gdelt_gkg | 106 | org_lookup | 2032 | 200 | 76 | 1795 |
| alpaca_benzinga | 71 | source_metadata | 657 | 340 | 2674 | 0 |

- Copertura temporale ingest: 13:19:38 → 18:12:29 UTC (benzinga), 14:00 → 18:00 UTC (gdelt, finestra
  cron piena).
- **0** news con timestamp futuro, **0** stale (`published_at` < `fetched_at` − 2gg), **0** `published_at`
  NULL.
- **301 item scartati come stale** all'inizio giornata (14:00:00, `news_queue_drops`): backlog di articoli
  del 07-30 sera rimasti in coda oltre la soglia età massima — comportamento corretto by-design (evita
  che una news vecchia riceva un timestamp di sentiment "fresco").
- Top ticker per volume news: MS (29), MU (17), GS (17), AMZN (10), SHEL (8), DB (8), MSFT (7), AAPL (7).
- **Copertura watchlist**: 55/96 simboli (57%) senza alcuna riga in `news_log` — vedi [F-001] già
  aperto nel ledger, qui riconfermato dalla stessa query indipendente.
- Nessun problema di ticker ambiguity osservato nell'estrazione (`org_lookup`/`source_metadata`, non
  bare-text cashtag matching in questo campione).
- **[DAY-006]** Un singolo articolo può generare fino a **8 righe** `news_log` distinte (una per ticker
  citato, es. "Michael Burry expands bets against Nvidia, Micron... buying Lululemon and DraftKings" →
  8 ticker), ciascuna delle quali alimenta un sentiment_signal indipendente dallo stesso testo. Per
  design (`uq_news_log_url_ticker` è su url+ticker, non solo url) — comportamento corretto, non un bug,
  ma segnalato perché risponde esplicitamente alla domanda "la stessa news può generare segnali
  multipli?" della Quarta Fase: sì, per ticker diversi, mai per lo stesso ticker due volte sullo stesso
  articolo.
- **[DAY-006b — ambiguità]** `ingestion_stats_daily.duplicates` per `alpaca_benzinga` (2674) supera
  `fetched` (657) nello stesso giorno. Il contatore è un UPSERT additivo cross-run
  (`src/store/pg_store.py:369`, `duplicates = duplicates + EXCLUDED.duplicates`), quindi un valore
  cumulato superiore al fetched giornaliero è plausibile se il poller ri-scansiona una finestra
  temporale che si sovrappone tra cicli — ma non è stato verificato indipendentemente contro i conteggi
  grezzi per ciclo. Confidenza: Low. Non blocca l'analisi (i 71 record finali in `news_log` sono
  verificati riga per riga), ma riduce l'affidabilità di `ingestion_stats_daily` come fonte di audit
  stand-alone.

## 5. Tabella performance modelli LLM

| Model | Risposte (07-31) | Ineligible (conf<0.4 o forzato da fallback) | Polarity media | Polarity min/max | Confidence media |
|---|---:|---:|---:|---:|---:|
| gpt-oss:20b-cloud | 179 | 145 (81%) | +0.037 | −0.800 / +0.750 | 0.413 |
| glm-5.2:cloud | 179 | 145 (81%) | +0.037 | −0.800 / +0.850 | 0.293 |

- Coppia attiva confermata in Redis: `config:sentiment_llm_models` = `glm52,gptoss` (coerente, non
  resettato a "all").
- **179 sentiment_signals** generati, **63 (35%) `fallback_used=True`** (single-model o FinBERT).
  Nessuno di questi corrisponde a una finestra di downtime Ollama sostenuta — vedi §16.
- Ensemble std medio 0.039, massimo 0.354 (ben sotto una divergenza sistemica).
- 145/179 (81%) righe `llm_responses` marcate `eligible=false`: la maggioranza (126, cioè 63 segnali ×
  2 modelli) è forzata da `force_ineligible=result.fallback_used` (`sentiment.py:572-576`) quando il
  segnale finale è andato in fallback; il residuo (~19) è coerente con letture single-model sotto
  soglia 0.4 individuale. Consistente con la nota di memoria pregressa ("Ensemble Divergence Order
  Drought", fallback 70-86% in altri periodi) — oggi il tasso è più basso (35%), non un nuovo problema.
- Nessun refusal/invalid-output osservato nei log del giorno; nessun timeout esplicito.
- Verifica funzionale (Quarta Fase):
  - Output validato prima di entrare nel signal store? **Sì** — soglia confidence 0.4 + divergence
    gate in `ensemble.py:284-291`, fallback deterministico (FinBERT) se non superata.
  - Confidence bassa riduce il peso? **Sì**, via `_w = confidence × weight` in `ensemble.py:295`.
  - Chiamate offline/background, mai nel trading loop? **Sì** — verificato: `sentiment.py` gira come
    task Celery separato dal ciclo `portfolio_scheduler`, che legge solo da Postgres/Redis già scritti.
  - Rischio hallucination diretto in decisione? **Basso** — c'è un gate di soglia (0.30-0.35) e i
    guardrail #108/pyramiding/duplicate-signal tra segnale e ordine; nessuna evidenza oggi di un
    segnale palesemente allucinato che abbia generato un trade (i 5 BUY S4 del giorno hanno reasoning
    coerente con notizie reali di earnings verificabili — AMZN AWS, MSFT Azure, MA/ORCL cloud deal).

## 6. Tabella segnali finali per ticker (top by volume, 07-31)

| Ticker | N segnali | Score medio | Score min/max | Fallback presente |
|---|---:|---:|---:|:---:|
| MS | 29 | +0.021 | −0.240/+0.360 | Sì |
| MU | 17 | +0.054 | −0.240/+0.324 | Sì |
| GS | 17 | −0.001 | −0.045/+0.040 | Sì |
| AMZN | 10 | +0.322 | 0.000/+0.680 | Sì |
| SHEL | 9 | −0.007 | −0.266/+0.120 | No |
| DB | 8 | −0.016 | −0.455/+0.180 | Sì |
| MSFT | 7 | +0.091 | −0.120/+0.543 | Sì |
| AAPL | 7 | −0.133 | −0.525/+0.380 | Sì |
| GOOGL | 4 | +0.070 | +0.010/+0.170 | Sì |
| META | 4 | −0.003 | −0.040/+0.040 | Sì |
| NVO | 3 | −0.261 | −0.395/−0.168 | No |

Nessun ticker con score estremo (|score|>0.7 a livello di segnale ensemble finale, escludendo la singola
polarity per-modello che tocca ±0.80-0.85). AMZN mostra il segnale medio più forte e coerente col
movimento reale (+15.3%). AAPL mostra score medio negativo (−0.133) coerente col calo (−7.35%, delusione
utili) — nessun caso WRONG_SIGN.

## 7. Tabella ordini generati/eseguiti (BUY/SELL, 07-31)

| ID decisione | Ora | Simbolo | Decisione | Score/signal_score | Rationale | Trade collegato | Esito |
|---|---|---|---|---|---|---|---|
| 5269 | 14:22 | ARM | SELL | 0.005 | S1 momentum | 586 | filled, chiuso 14:52 net +$45.28 |
| 5270 | 14:22 | QQQ | BUY | 0.012 | S1 momentum | 589 | filled, chiuso 16:07 net +$1.22 |
| 5271 | 14:22 | AMZN | BUY | signal +0.795 | S4 news (AWS Q2 beat) | 590 | filled, chiuso 18:37 net +$15.53 |
| 5272 | 14:22 | HOOD | SELL (expired) | — | S4 signal age 18.6h>4h | 587 | filled, net −$43.97 |
| 5273 | 14:22 | INFY | SELL (expired) | — | S4 signal age 18.6h>4h | 588 | filled, net −$12.68 |
| 5274 | 14:22 | ORCL | SELL (expired) | — | S4 signal age 20.9h>4h | 585 | filled, net −$5.67 |
| 5299 | 14:52 | ORCL | BUY | signal +0.385 | S4 news (Google Cloud/Oracle) | 591 | filled, chiuso 17:52 net +$2.16 |
| 5316 | 15:07 | SBUX | SELL | — | s1_weight_drop | 579 | filled, net −$8.28 |
| 5334 | 15:22 | SBUX | BUY | 0.012 | S1 momentum | 592 | filled, chiuso 17:07 net −$4.11 |
| 5385 | 16:07 | QQQ | SELL | — | s1_weight_drop | 589 | filled, net +$1.22 |
| 5386 | 16:07 | ABBV | SELL | signal −0.640 | sentiment_reversal (<−0.35) | 245 | filled, net +$16.90 ([F-002]) |
| 5404,5420,5437,5455,5475,5495,5514 | 16:22→17:52 | ABBV | BUY (loggato) | 0.012 | S1 momentum (testo generico) | — | **nessun ordine** — bloccato da reversal cooldown, non riflesso nel `reason` ([DAY-004]) |
| 5476 | 17:22 | MA | BUY | signal +0.350 | S4 news (Mastercard earnings) | 594 | filled, aperto a fine giorno |
| 5515 | 17:52 | SBUX | BUY | 0.012 | S1 momentum | 595 | filled, aperto a fine giorno |
| 5516 | 17:52 | ORCL | SELL | signal 0.000 | whipsaw guard | 591 | filled, net +$2.16 |
| 5534 | 18:07 | ABBV | BUY | 0.012 | S1 momentum (cooldown scaduto) | 596 | filled, aperto a fine giorno |
| 5575 | 18:37 | AMZN | SELL | signal +0.080 | whipsaw guard | 590 | filled, net +$15.53 |
| 5627 | 19:22 | MSFT | BUY | signal +0.5425 | S4 news (Azure/AI) | 597 | filled, aperto a fine giorno |
| 5645 | 19:37 | AMZN | BUY | signal +0.664 | S4 news (AWS) | 598 | filled, aperto a fine giorno |

Tutti gli ordini sono **paper** (`execution.engine=portfolio`, unico path attivo per submission —
verificato via `config/trading.yaml` e assenza di log `legacy_sentiment`). Nessun order_id duplicato,
nessun order piazzato fuori dall'intervallo 13:19-19:52 UTC osservato nel giorno.

## 8. Tabella PnL/rendimento (07-31)

| Voce | Valore | Fonte |
|---|---:|---|
| Realizzato totale (trade chiusi 07-31) | **+$6.37** | `trades`, riverificato: S1 −$11.17 + S4 +$0.64 + ABBV +$16.90 |
| Realizzato S1 | −$11.17 | SBUX(579) −8.28 + QQQ(589) +1.22 + SBUX(592) −4.11 |
| Realizzato S4 | +$0.64 | ORCL(585) −5.67 + HOOD −43.97 + INFY −12.68 + ARM +45.28 + AMZN(590) +15.53 + ORCL(591) +2.16 |
| ABBV (245) non attribuito | +$16.90 | `stop_strategy` NULL — [F-002], trade legacy pre-07-14 |
| MTM giornaliero book intero (Alpaca `profit_loss`) | +$262.25 | `docs/evidence/market_daily.jsonl` riga 07-31 |
| MTM stimato (Alpaca P&L − realizzato) | +$255.88 | derivato |
| Equity fine giornata | $109,502.32 | market_daily.jsonl |
| Cost/slippage totale sui trade chiusi 07-31 (10 chiusure) | ≈$9.97 (somma `cost_usd`) | `trades.cost_usd` |
| Drawdown strategia riportato in RISK ALERT (22:30) | 13.9% | `risk_reports` alert message / `per_strategy_metrics` |
| `combined_drawdown` nello stesso report (colonna dedicata) | 1.24% | `risk_reports.combined_drawdown` — **incoerente con la riga sopra, [DAY-001]** |

Nota: non è stato possibile scomporre il MTM per singola posizione con precisione oltre le stime già
pubblicate in ALPHA_MISS_REPORT (richiederebbe prezzi intraday per ogni simbolo in book, non solo i
mover); i numeri di posizione aperta più rilevanti (AMZN, GOOGL, MU, AAPL) sono già in quel report §4.
Nessun dato di performance è stato inventato.

## 9. Analisi correttezza buy/sell

| Controllo | Esito | Evidenza |
|---|---|---|
| BUY solo se consentito (no pyramiding) | **Corretto** | ~40 log "P0-05 pyramiding guard: skipping BUY" nel giorno, zero violazioni |
| SELL/exit generati correttamente | **Corretto** | 6 meccanismi osservati: portfolio_sell, s1_weight_drop, sentiment_reversal, whipsaw, expired (S4 stale), nessuna SELL orfana |
| Stop-loss rispettato | **N/A per design** | `stop_loss: 0.0` disabilitato da config (decisione operativa nota, non una scoperta di oggi) — nessuno stop scattato perché non armato |
| Signal flip rispettato | **Corretto** | ABBV sentiment_reversal a −0.640 ha chiuso la posizione long correttamente (nessun caso SELL-su-score-positivo, bug A5 pattern non trovato) |
| Max holding / freschezza segnale S4 | **Corretto (col rischio noto in [DAY-005])** | 3 SELL "expired" per segnali S4 >4h; 21/38 segnali droppati per età alla fine giornata |
| Rebalance band | **Non verificabile in dettaglio in questa sessione** | churn SBUX/ABBV/QQQ/ORCL osservato ma ogni riapertura è giustificata da un evento esplicito (weight_drop, cooldown scaduto, whipsaw) — nessuna evidenza di flip senza causa |
| Ordini duplicati | **Corretto** | zero righe con stesso simbolo+stesso minuto in `trades`; SIGNAL_DUPLICATE_SKIP verificato per MA/MSFT |
| Ordini contrari ravvicinati senza rationale | **Corretto** | ogni BUY/SELL ravvicinato ha un meccanismo esplicito loggato (whipsaw, cooldown, weight_drop) |
| Ordini su ticker non consentiti | **Non trovato** | tutti i simboli appartengono alla watchlist di `config/trading.yaml` |
| Ordini fuori orario | **Non trovato** | tutte le decisioni BUY/SELL tra 14:22 e 19:52 UTC, dentro 13:30-20:00 |
| Trade su dati stale | **Corretto** | guard esplicito droppa segnali stale prima della decisione (S4 age>4h, S1 sparse/stale-tailed) |
| Trade su LLM output non valido | **Corretto** | guard #108 esclude fallback dal ranking BUY |
| Circuit breaker attivo durante trading | **No** | `fallback_counters.consecutive_fallback` = 0 quasi tutto il giorno, mai un halt |
| Strategia disabilitata che genera ordini | **No** | solo S1/S4 hanno trade; S2 (disabilitato) zero trade, ma genera comunque un alert decay — vedi [DAY-002] |
| Paper/live coerente | **Corretto** | unico path attivo `execution.engine=portfolio` (paper) |
| Idempotenza retry Celery | **Corretto** | duplicate-signal guard esplicito (SIGNAL_DUPLICATE_SKIP) |
| Reconciliation ordini↔fill↔posizioni | **Coerente per il 07-31**; **fallita il giorno dopo** | tutti i trade del 07-31 hanno entry/exit price popolati; il fallimento di reconciliation Alpaca osservato è datato 08-01 11:37, fuori dalla finestra di questo report — vedi §16 |
| Roundtrip <30min stesso simbolo | **Non trovato** | durata minima trade osservata ~45 min (SBUX 592: 15:22→17:07 no; minima reale ARM 30 min 14:22→14:52 — verificato ≥30min in tutti i casi) |
| BUY ripetuto >3 volte senza SELL (pyramiding reale) | **Non trovato** | i 7 tentativi ABBV sono BUY bloccati (nessun fill), non pyramiding reale |
| Score<0.05 con ordine generato | **Non trovato** — attenzione a non confondere colonne | la colonna `score` per righe S1 (~0.01-0.02) NON è il segnale sentiment ma un peso di portafoglio; il vero segnale sentiment per gli ordini S4 è in `signal_score` (0.35-0.80, sempre sopra soglia) |
| Ordini identici stesso minuto | **Non trovato** | query dedicata su `trades` (symbol, minuto entry) — zero righe |

## 10. Anomalie trovate

### [DAY-001] Metrica drawdown incoerente all'interno dello stesso risultato di rischio

- Tipo: Bug
- Area: Risk
- Evidenza:
  - file/log/tabella: `risk_reports` id=49
  - timestamp: 2026-07-31 22:30:00.995 UTC
  - snippet/query: `alerts` = `[{"level":"ALERT","message":"Strategy portfolio drawdown 13.9% exceeds 10%","strategy_id":"portfolio"}]`; colonna `combined_drawdown` = `0.012429` (1.24%); `per_strategy_metrics->portfolio->drawdown` = `0.1387` (13.9%)
- Descrizione: lo stesso `risk_report` contiene due valori di drawdown "portfolio" incompatibili: la
  colonna dedicata `combined_drawdown` (1.24%) e il campo `drawdown` dentro `per_strategy_metrics`
  (13.9%, quello effettivamente usato per generare l'ALERT). Un lettore che consulti solo la colonna
  `combined_drawdown` (es. una dashboard o uno script di sintesi) vedrebbe un rischio 10× più basso di
  quello reale che ha effettivamente scatenato l'alert.
- Impatto: rischio di lettura falsata del drawdown reale durante il periodo di osservazione, proprio
  mentre la carta di osservazione userà queste metriche per le domande di uscita. Consistente con un
  problema già annotato in memoria di sessioni precedenti (Bug Sweep 2026-07-22, "combined_drawdown
  fuorviante") — oggi riconfermato con un caso concreto e quantificato.
- Severità: High
- Confidenza: High
- Azione consigliata: chiarire (ticket) quale delle due formule è quella corretta e far coincidere
  colonna dedicata e alert; nel frattempo, chi consulta `risk_reports` deve leggere
  `per_strategy_metrics->portfolio->drawdown`, non `combined_drawdown`.
- Test/monitor consigliato: assert automatico che `combined_drawdown` e
  `per_strategy_metrics->portfolio->drawdown` coincidano entro una tolleranza, con alert se divergono.

### [DAY-002] Decay monitor confronta metriche pipeline-globali contro 3 baseline per-strategia distinte, incluso un S2 mai tradato

- Tipo: Bug
- Area: Risk / Ops
- Evidenza:
  - file/log/tabella: `src/workers/decay_monitor_task.py:52-66` (`_fetch_actual_metrics`); `decay_reports`; log worker
  - timestamp: 2026-07-31 21:00:00 UTC
  - snippet/query: log `DECAY CRITICAL [S2]: Max drawdown exceeds baseline by 6.9pp: 12.9% vs 6.0%`; query su `sentiment_signals`/`portfolio_daily_state` in `_fetch_actual_metrics` **non filtra per `strategy_id`** (il commento nel codice lo dichiara esplicitamente: "Metrics are pipeline-global (no strategy_id column in the table)"); confermato su 3 giorni consecutivi (`decay_reports` 08-01/08-02) che S1, S2, S4 ricevono **valori identici** di `ic`, `sharpe`, `hit_rate`, `max_drawdown` nello stesso giorno, confrontati contro 3 baseline diverse
- Descrizione: `S2` è una strategia **disabilitata** (0% allocazione, "research", tutti i gate OOS
  falliti — `ARCHITECTURE.md:209`) e non ha **mai** un trade in `trades` (query dedicata: zero righe
  con `stop_strategy='S2'`). Ciò nonostante, il decay monitor le assegna quotidianamente le stesse
  metriche pipeline-globali di S1/S4 e genera alert CRITICAL/WARNING come se fosse una strategia viva
  in decadimento. Per S1, le metriche `ic`/`hit_rate` usate sono in realtà quelle di
  `sentiment_signals` (il dominio di S4, non di S1 momentum) — quindi anche l'alert su S1 non misura
  S1.
- Impatto: `decay_reports` non è utilizzabile come fonte per giudicare il decadimento/edge di una
  strategia specifica — esattamente il tipo di dato che la Domanda di uscita 2 della carta di
  osservazione ("S1 ha un edge?") potrebbe voler consultare. Rischio concreto di corrompere
  l'evidenza raccolta nelle prossime settimane se qualcuno usa `decay_reports` senza sapere che i
  numeri sono condivisi tra le 3 strategie.
- Severità: High
- Confidenza: High
- Azione consigliata: ticket di correttezza (ammesso dalla carta: se non corretto, l'evidenza futura
  su `decay_reports` è sbagliata) — filtrare le query di `_fetch_actual_metrics` per strategia (via
  `stop_strategy` su `trades`/join con `execution_decisions`), o quantomeno smettere di generare
  report per S2 finché resta disabilitata.
- Test/monitor consigliato: test che verifichi che `decay_reports.actual_value` per strategie diverse
  nello stesso giorno NON sia identico quando esistono dati strategy-specific sufficienti; skip
  esplicito per strategie con allocazione 0%.

### [DAY-003] Alert Telegram non consegnato per il trigger di loss-feedback S1

- Tipo: Bug
- Area: Ops
- Evidenza:
  - file/log/tabella: docker logs `worker`
  - timestamp: 2026-07-31 20:30:00 UTC
  - snippet/query: `WARNING: Loss feedback triggered for S1: EWMA R -0.52, ... rolling P&L $-221.42` seguito immediatamente da `WARNING: TelegramNotifier: Failed to send alert: Client error '400 Bad Request' for url 'https://api.telegram.org/bot.../sendMessage'`
- Descrizione: l'evento di loss-feedback (rilevante: soglia S1 abbassata 0.30→0.00) è stato scritto
  correttamente nei log e nel DB, ma la notifica verso l'operatore via Telegram è fallita con 400 Bad
  Request. Non è possibile determinare da qui se il payload malformato è sistemico o occasionale.
- Impatto: un evento operativamente rilevante (soglia S1 azzerata) potrebbe non essere stato notato
  dall'operatore in tempo reale. Non altera i dati di trading raccolti, ma è un gap nella catena di
  osservabilità durante il periodo di osservazione.
- Severità: Medium
- Confidenza: High (log esplicito)
- Azione consigliata: ticket per investigare il payload che genera 400 (probabile carattere non
  escapato in Markdown/HTML Telegram nel messaggio di loss-feedback) — non una taratura, un difetto di
  consegna del messaggio.
- Test/monitor consigliato: retry con backoff su 400 Telegram + alert secondario (log CRITICAL) se la
  consegna fallisce 2 volte di fila.

### [DAY-004] Decisioni "BUY" persistite senza ordine e senza causa reale nel campo `reason`

- Tipo: Bug
- Area: Orders / Data
- Evidenza:
  - file/log/tabella: `execution_decisions` id 5404,5420,5437,5455,5475,5495,5514; docker logs `worker`
  - timestamp: 2026-07-31 16:22:00 → 17:52:00 UTC (7 cicli da 15 min)
  - snippet/query: DB: `reason = "S1 momentum: time-series momentum signal, portfolio weight 1.2%."`, `order_id` vuoto per tutte e 7; log: `WARNING Reversal cooldown: skipping BUY for ABBV — force-sold on sentiment reversal`
- Descrizione: per 7 cicli consecutivi il sistema logga `decision=BUY` con un rationale che descrive
  l'intento di comprare al 1.2% di peso, ma il vero motivo per cui non è partito nessun ordine (guard
  di cooldown post-reversal) esiste solo nei log testuali del container, non nella riga persistita in
  `execution_decisions`. Un'analisi che usi solo il database (come richiesto da questo stesso
  protocollo forensic, "read-only, solo SELECT") avrebbe classificato queste 7 righe come "decisione
  BUY senza ordine generato" (pattern NO-ORDER richiesto esplicitamente dall'Ottava Fase) senza modo
  di distinguere un blocco intenzionale da un fallimento di sottomissione ordine.
- Impatto: auditabilità/correttezza dei dati storici — questo è esattamente il tipo di difetto che,
  se non corretto, produce evidenza sbagliata nelle analisi forensi successive (che potrebbero
  scambiare un cooldown per un bug di order submission, o viceversa).
- Severità: Medium
- Confidenza: High
- Azione consigliata: persistere la vera causa di skip (es. `decision="SKIP_COOLDOWN"` o un campo
  `block_reason` distinto) invece di lasciare `decision=BUY` con `order_id` NULL indistinguibile da un
  fallimento di submission.
- Test/monitor consigliato: assert che ogni riga con `decision='BUY'`/`'SELL'` e `order_id IS NULL`
  abbia un `reason` che spiega esplicitamente il blocco (non il solo rationale del segnale).

### [DAY-005] 55% dei segnali S4 scartati per età in un singolo ciclo di fine giornata

- Tipo: Osservazione
- Area: Signal
- Evidenza:
  - file/log/tabella: docker logs `worker`
  - timestamp: 2026-07-31 19:52:07 UTC
  - snippet/query: `WARNING S4: dropped 21/38 stale signals (age > 4h)`
- Descrizione: nel ciclo delle 19:52, più della metà dei segnali S4 disponibili era già oltre la
  soglia di freschezza (4h) al momento della valutazione. Stesso sintomo strutturale di [F-001]
  (scarsità di news editoriale utile sulla watchlist): pochi segnali arrivano, e quelli che arrivano
  spesso invecchiano prima che un ciclo di decisione li consideri utili.
- Impatto: riduce ulteriormente il tasso di segnali S4 effettivamente azionabili, oltre alla scarsità
  di copertura già nota. Nessuna proposta di taratura (cadenza/soglia età sono parametri congelati).
- Severità: Low
- Confidenza: Medium
- Azione consigliata: nessuna in questo periodo (congelato); solo evidenza per la domanda di uscita 1
  della carta.
- Test/monitor consigliato: tracciare giornalmente il tasso di drop-per-età come metrica di
  osservazione (non di azione).

### [DAY-006] Un articolo può generare segnali su più ticker dallo stesso testo (comportamento by-design)

- Tipo: Corretto
- Area: News / Signal
- Evidenza: `news_log`, query content_hash — un URL Benzinga ("Michael Burry expands bets against
  Nvidia, Micron...") genera 8 righe (una per ticker), ciascuna con un content_hash duplicato delle
  altre 7.
- Descrizione: risposta diretta alla domanda "la stessa news può generare segnali multipli?" della
  Quarta Fase — sì, ma solo su ticker diversi (mai duplicato sullo stesso ticker, protetto da
  `uq_news_log_url_ticker`). Comportamento intenzionale (estrazione per-ticker), non un bug.
- Severità: Low (informativo)
- Confidenza: High
- Azione consigliata: nessuna.

### [DAY-007] Guardrail anti-pyramiding, anti-duplicati e anti-whipsaw verificati funzionanti

- Tipo: Corretto
- Area: Orders / Risk
- Evidenza: docker logs `worker` — decine di righe `P0-05 pyramiding guard: skipping BUY`,
  `SIGNAL_DUPLICATE_SKIP` per MA/MSFT, `[whipsaw] ... would_suppress=True` per ORCL/AMZN.
- Descrizione: nessuna violazione trovata dei pattern richiesti esplicitamente dall'Ottava Fase (BUY
  ripetuto >3 volte senza SELL, ordini duplicati stesso minuto, roundtrip <30min). Riportato come
  falso-positivo/area corretta.
- Severità: — (nessuna azione)
- Confidenza: High
- Azione consigliata: nessuna.

### [DAY-008] Nessuna evidenza di outage Ollama nel giorno

- Tipo: Corretto / Non verificabile oltre questo
- Area: LLM / Ops
- Evidenza: docker logs `worker-inference` (nessun errore di connessione, nessun timeout verso
  ollama.com), `fallback_counters.consecutive_fallback` resettato più volte nel giorno, mai uno
  streak prolungato.
- Descrizione: il 35% di fallback osservato è spiegato da gating di confidence/divergenza
  dell'ensemble, non da un'infrastruttura down. Vedi §16 per il dettaglio richiesto.
- Severità: — (nessuna azione)
- Confidenza: Medium (assenza di errore nei log non è prova assoluta di zero downtime, ma è
  l'evidenza migliore disponibile in questa sessione read-only)
- Azione consigliata: nessuna.

### [DAY-009] Ambiguità sull'autenticazione API del runbook

- Tipo: Ambiguità
- Area: Ops
- Evidenza: `curl -H "Authorization: Bearer <token>" $BASE/decisions` → `403 {"detail":"Invalid or
  expired JWT token"}`; lo stesso segreto passato come `X-API-Key: <token>` funziona
  (`src/api/auth.py:15-46`).
- Descrizione: il runbook fornito per questa sessione istruisce a usare lo schema `Bearer`, ma il
  segreto fornito è la chiave statica `ADMIN_API_KEY`, che l'API accetta solo via header `X-API-Key`.
  Con `Bearer` l'API la interpreta come JWT e la rifiuta. Questo report ha usato `X-API-Key` per tutte
  le chiamate API dirette (poche, la maggior parte dell'evidenza viene da SQL diretto).
- Severità: Low
- Confidenza: High
- Azione consigliata: correggere la documentazione/il runbook di questo cron per usare
  `X-API-Key: <token>` invece di `Authorization: Bearer <token>`.
- Test/monitor consigliato: nessuno (documentazione, non codice).

## 11. False positive o aree risultate corrette

- Pyramiding: guard #P0-05 verificato attivo e corretto (§10, [DAY-007]).
- Duplicati ordine/segnale: `SIGNAL_DUPLICATE_SKIP` verificato attivo (§10, [DAY-007]).
- SELL con sentiment positivo (bug A5 pattern): non trovato — l'unico `sentiment_reversal` del giorno
  (ABBV) è scattato su score negativo, coerente con la direzione long della posizione.
- Roundtrip <30 min: non trovato, durata minima osservata sui trade chiusi è 30 min (ARM 14:22→14:52).
- Ordini fuori orario: non trovato, tutte le decisioni BUY/SELL tra 14:22 e 19:52 UTC.
- Ordini identici nello stesso minuto: non trovato.
- Ollama down: non trovato (§10, [DAY-008]).
- Traceability news→segnale: 100% dei 179 segnali ha `news_log_id` popolato (nessun caso NULL da
  conflitto url+ticker oggi).
- Timezone: nessuna ambiguità — UTC esplicito e consistente in codice e log.

## 12. Dati mancanti o non accessibili

- **Prezzi intraday per simbolo** oltre ai mover già coperti da `ALPHA_MISS_REPORT_2026-07-31.md`:
  servirebbe uno storico tick/minute-bar Alpaca per scomporre il MTM per singola posizione non-mover
  (es. tutte le posizioni in book aperte prima del 07-31). Query che servirebbe:
  `GetBarsRequest` Alpaca su ogni simbolo in book, timeframe 1Min, 2026-07-31.
- **Log Celery worker precedenti al 2026-07-28** (retention log Docker) — non necessario per questo
  giorno, segnalato solo come limite generale.
- **Commissioni broker esplicite**: `trades.cost_usd`/`slippage_est` sono stime interne
  (`cost_bps`/`impact_cost_bps`), non conferma diretta della commissione Alpaca (paper trading,
  presumibilmente $0, non verificato da statement broker in questa sessione).
- **Verifica indipendente della finestra di conteggio `ingestion_stats_daily.duplicates`** (§4,
  [DAY-006b]): servirebbe il log grezzo per-ciclo del poller GDELT/Benzinga, non disponibile oltre
  la finestra di retention Docker consultata.
- **Log frontend**: non consultati — nessuna anomalia riportata dall'utente lato UI per questo giorno,
  fuori scope rispetto alla pipeline dati.

## 13. Raccomandazioni immediate

Limitate a difetti di correttezza (nessuna taratura, come da carta di osservazione):

1. [DAY-001] Allineare `risk_reports.combined_drawdown` al valore effettivamente usato per generare
   l'alert (`per_strategy_metrics->portfolio->drawdown`), o documentare esplicitamente la differenza
   se intenzionale.
2. [DAY-002] Filtrare `_fetch_actual_metrics` per strategia in `decay_monitor_task.py`, o sospendere
   la generazione di decay report per S2 finché resta disabilitata (0% allocazione).
3. [DAY-004] Persistere la causa reale di skip (cooldown/whipsaw/altro guard) in un campo dedicato di
   `execution_decisions` invece di lasciare `decision=BUY` con `order_id` NULL indistinguibile da un
   fallimento di submission.

## 14. Test o monitor da aggiungere

- Assert giornaliero: `risk_reports.combined_drawdown` ≈ `per_strategy_metrics.portfolio.drawdown`
  (tolleranza da definire) — alert se divergono.
- Assert su `decay_reports`: valori `actual_value` non identici tra strategie diverse nello stesso
  giorno quando esistono dati strategy-specific sufficienti.
- Monitor su `execution_decisions`: percentuale di righe `decision IN ('BUY','SELL')` con `order_id`
  NULL e `reason` che NON menziona esplicitamente una causa di blocco — deve tendere a zero.
- Monitor su retry/fallimento consegna Telegram (contatore fallimenti consecutivi + alert secondario).
- Metrica di osservazione (non azione): tasso giornaliero di segnali S4 scartati per età (>4h) al
  momento della decisione.

## 15. Ticket tecnici suggeriti

- **T1** (Critico, correttezza): disallineamento `combined_drawdown` vs `per_strategy_metrics` in
  `risk_reports` — vedi [DAY-001].
- **T2** (Alto, correttezza): decay monitor usa metriche pipeline-globali per 3 strategie con baseline
  distinte, incluso S2 mai tradato — vedi [DAY-002].
- **T3** (Medio, ops): Telegram alert 400 Bad Request sul messaggio di loss-feedback — vedi [DAY-003].
- **T4** (Medio, correttezza/auditabilità): causa reale di skip non persistita in `execution_decisions`
  per decisioni BUY/SELL bloccate da guard interni — vedi [DAY-004].
- **T5** (Basso, documentazione): runbook cron usa schema `Bearer` non supportato dal segreto statico
  fornito — vedi [DAY-009].

Nessuno di questi è una proposta di taratura di soglie/pesi/parametri di strategia.

## 16. Stato sistema

- **Ollama**: nessuna evidenza di downtime nel 2026-07-31. Zero errori di connessione/timeout verso
  `ollama.com` nei log `worker-inference` del giorno. Fallback rate 35% (63/179 segnali) spiegato da
  gating di confidence/divergenza, non da infrastruttura down. Unico evento di divergenza esplicita
  loggato: IWM alle 19:30:16 UTC, risolto immediatamente (fallback_counters resettato subito dopo).
- **FinBERT fallback rate**: 35% dei segnali del giorno (63/179) sono andati in fallback (single-model
  o deterministico); 81% delle righe `llm_responses` individuali marcate `eligible=false` (in gran
  parte per effetto del flag `force_ineligible` sui segnali di fallback, non per doppio conteggio
  reale).
- **Worker restart events**: **zero**. Tutti e 4 i container (`worker`, `worker-inference`, `beat`,
  `api`) risultano avviati il 2026-07-30 13:49:39 UTC con `RestartCount=0`, quindi nessun restart ha
  interessato la giornata del 07-31.
- **Halt operatore**: chiave Redis `system:halted_by_operator` non impostata durante il giorno —
  nessun halt manuale attivo.
- **Gate S4 (#163/#164)**: tenuto — soglia feedback osservata correttamente a 0.300 nei log
  (`SKIP_THRESHOLD ... score X < feedback threshold 0.300`), non disarmata.
- **Evento fuori finestra**: 2026-08-01 11:37 UTC, "Terminal mobile order reconciliation failed" per
  connessione rifiutata verso `paper-api.alpaca.markets` — datato al giorno successivo a quello
  analizzato, riportato qui solo per completezza sullo stato sistema corrente, non incluso nella
  timeline/anomalie del 07-31.
