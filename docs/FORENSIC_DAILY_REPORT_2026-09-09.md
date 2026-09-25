# Forensic Daily Report — 2026-09-09 (mercoledì)

**Generato:** 2026-09-25 (seduta **recuperata** 16 giorni dopo: il ciclo forense del 09-09 non era mai stato eseguito — cfr. #563) · **Timezone operativo:** UTC (`src/workers/celery_app.py`, `timezone="UTC"`, `enable_utc=True` — nessuna ambiguità)
**Sessione:** RTH 13:30–20:00 UTC (EDT). Pre-market 08:00–13:30, post-market 20:00–24:00 UTC.
**Modalità:** paper (`portfolio_monitor_snapshots.broker_environment='paper'`, `mode='paper'`, `source='alpaca_paper'`; `config/trading.yaml → execution.engine: portfolio`).
**Analisi:** read-only. Nessun file modificato oltre a questo report e a `docs/evidence/findings.json`. Prezzi intraday letti dall'API dati storici Alpaca (barre 1 min e 1 giorno, `adjustment=all`), sola lettura, nessuna chiamata di trading.
**Fonti:** Postgres `alembic-postgres-1` (news_log, news_queue_drops, ingestion_stats_daily, sentiment_signals, llm_responses, execution_decisions, s4_intent_events, s4_lifecycle_events, trades, portfolio_cycles, portfolio_monitor_snapshots, finbert_fallback_events), log persistenti `logs/containers/*-2026-09-09.log`, REST `/api/orders` (X-API-Key), dossier `docs/evidence/dossier/2026-09-09.json` (generato 2026-09-24), `docs/ALPHA_MISS_REPORT_2026-09-09.md`.

---

## 1. Executive summary

La pipeline ha girato end-to-end senza interruzioni: 24 cicli di portafoglio a cadenza esatta di 15 min (14:07→19:52), 199 righe news, 199 segnali (1:1, nessun re-scoring), 736 righe di Decision Log, **2 BUY S4 (MU, DIS) e 1 SELL S4 (SPCX)**, tutti riconciliati a fill reali, più 2 stop protettivi GTC. NAV **109.910,06 → 109.767,54 $ (−142,52 $, −0,13%)** contro SPY −0,46%. L'unico realizzato è SPCX **−59,51 $** (`sentiment_reversal` su una notizia vera dell'emittente, lo sblocco del lockup): un'uscita corretta.
Nessun ordine duplicato, nessun ordine fuori orario o senza risk check, nessun ordine su segnale fallback, nessun ciclo mancante, Ollama su per tutta la sessione (17 timeout, 5 fallback FinBERT = 2,5% dei segnali).
Le anomalie sono recidive già a ledger, nessuna nuova. La più istruttiva: i due segnali issuer-specific più forti dell'apertura (**QCOM +0,706, HOOD +0,325**) erano pubblicati alle 11:48–11:50, sono rimasti in coda fino alla campana e sono arrivati al primo ciclo delle 14:07 con la finestra di freschezza da 2 h già consumata (`SKIP_ENTRY_FRESHNESS`). Stavolta il filtro ha fatto risparmiare: comprarli alle 14:07 avrebbe perso ~74 $. Allo stesso modo il guard P0-05 ha bloccato 40 intenti S4 su 6 titoli S1: a controfattuale corto, **−93 $ evitati**.
Un difetto di evidenza, già noto (F-048), tocca questa seduta a posteriori: MU è stata comprata per **1,407 azioni** (lifecycle, nozionale 1.456,82 $), ma `trades.qty` oggi vale 0,407 perché è stata riscritta il 09-14. Di conseguenza il dossier del 09-09, rigenerato il 09-24, dichiara `mtm_eod` MU a −3,11 $ invece di **−10,74 $**.
Restano aperte altre recidive: la finestra cieca 13:30–14:07, l'alert Telegram 400 sull'AMAT a −21%, 177 righe notturne scartate `stale` alle 13:37, la divergenza d'ensemble nascosta dal filtro di eleggibilità e gli alert DECAY CRITICAL solo a log.

## 2. Verdict finale

### **OK con warning**

Trading logic funzionalmente corretta su tutti gli ordini della giornata: ingresso solo sopra il gate, uscita su reversal vero, idempotenza (`SIGNAL_DUPLICATE_SKIP` ×4 su MU), stop GTC sul nozionale intero. I warning sono tutti recidive a ledger e riguardano due cose: l'**evidenza** (F-048 qty riscritta, F-073 provenienza mista di `signal_score`, F-078 contatori fallback, F-015 slippage, F-061 riemissioni) e l'**osservabilità/alerting** (F-005, F-062, F-017). Nessuno ha prodotto un ordine sbagliato oggi.

---

## 3. Timeline del 2026-09-09 (UTC)

| Ora (UTC) | Componente | Evento | Stato | Fonte |
|---|---|---|---|---|
| 00:00–00:13 | worker (mobile monitor) | 84× `SPY benchmark fetch failed: subscription does not permit querying recent SIP data` | warning, nessun alert | worker log |
| 00:00–13:30 | worker-news-stream (WS) | ingest notturno in `news:queue`; il consumatore risponde `market_closed` (~60 run da 0,45 s) | by design (F-069) | worker-inference log |
| 01:00–12:59 | dedup | 584 `duplicate_id` off-session scartati in coda (10:00: 429 righe su 2 articoli) | ok | `news_queue_drops` |
| 06:20:15 | worker, worker-inference | warm shutdown + riavvio (redeploy) | fuori sessione | log |
| 07:00:05 | regime | FRED `500 Internal Server Error` su VIXCLS → task `succeeded ... None` | **fallimento silenzioso** (F-017) | worker-inference log |
| 11:48 / 11:50 | provider | pubblicati gli articoli QCOM (Amazon $60B) e HOOD (initiation) | in coda | `news_log.published_at` |
| 13:30 | mercato | apertura RTH; NAV 109.856,37 $ (−53,69 $ di gap sul close prec.) | — | `portfolio_monitor_snapshots` |
| 13:37:01 | sentiment | primo run in sessione; FinBERT caricato da HF Hub (non autenticato) | ok | worker-inference log |
| 13:37 | sentiment | **177 righe (58 articoli) scartate `stale`**, tutte `enqueued_off_session`, età media 8,9 h | F-069 | `news_queue_drops` |
| 13:39–13:41 | Ollama | 2 timeout (1 per modello), nessun fallback FinBERT | degradazione minima | log |
| 13:41:49 | sentiment | **QCOM +0,706** (ensemble, conf 0,88) | segnale | `sentiment_signals` 10052 |
| 13:43:07 | sentiment | **HOOD +0,325** (ensemble) | segnale | 10053 |
| 13:45:41 | sentiment | primo task chiude in 527 s: 8 processati, 4 "finbert_fallbacks" (in realtà single-model) | ok | log |
| 13:55:38 | sentiment | AZN +0,420 `single:gpt-oss` (glm −0,1×0,3 ineleggibile) — segni opposti, `ensemble_std` 0,000 | F-054 | 10064 |
| 14:00:01 | ingest REST | primo fetch Alpaca della giornata (fetched 33, queued 20, dup 117) | ok | worker log |
| 14:07:06 | portfolio | **primo ciclo** (37 min dopo l'apertura): 27 segnali scartati per freshness, fra cui QCOM (età articolo 2h19) e HOOD | F-021 / F-019 | worker log, `s4_intent_events` |
| 14:07:08 | risk #161 | AMAT non proteggibile a −21,0% (qty 0,857) → alert Telegram **400 Bad Request** | F-022 / F-005 | worker log |
| 14:12 | lifecycle | 7 `ENTRY_RECONCILIATION` su ingressi del 09-08 (AZN, HOOD, NVO, QCOM, SPCX×2) | F-061 | `s4_lifecycle_events` |
| 14:14–14:19 | sentiment | "Oil Hits $100": XLE +0,531, XOM +0,517, CVX +0,505 | sopra gate, tutti detenuti | 10080–10086 |
| 14:22 | portfolio | CVX bloccato da P0-05 (S1) per 19 cicli; XLE (S4) per 23 | by design | `s4_intent_events` |
| 14:35:36 | Ollama | entrambi i modelli in timeout → FinBERT su DELL | fallback | 10101 |
| 14:43:34 | sentiment | MU +0,325 (×1,2 velocity = 0,390) | segnale | 10108 |
| **14:52:06** | **esecuzione** | **BUY MU** 1,407 sh @1035,406 (ordine `d464e257`), stop GTC 1 sh (`f7e44edd`) nello stesso ciclo | filled | `/api/orders`, lifecycle |
| 14:52–15:52 | idempotenza | 4× `SIGNAL_DUPLICATE_SKIP` su MU | ok | worker log |
| 15:19:07 | sentiment | SPCX −0,435 "Lockup Alert — 319 Million SPCX Shares Unlock Today" | segnale | 10117 |
| **15:22:05** | **esecuzione** | stop SPCX cancellato → **SELL SPCX** 9,355 sh @147,44, `sentiment_reversal` (−0,435 < −0,35) | filled, −59,51 $ | trade 988 |
| 15:28:06 | sentiment | CMCSA −0,386 ISSUER_SPECIFIC (CFO broadband) | nessun percorso (long-only) | 10118 |
| 15:44 / 19:25 | worker-inference | `Telegram polling HTTP error` (network unreachable / reset) | transitorio | log |
| 16:11:16 | sentiment | AMD +0,680 (×1,2 = 0,816) → 16:22 SKIP_PYRAMIDING (S1) | by design | 10128 |
| 16:23–17:42 | Ollama | 12 timeout, di cui 4 coppie → FinBERT su AMZN, GOOGL, QQQ, SPY | fallback | log, `sentiment_signals` |
| 16:48:14 | sentiment | task più lungo della giornata: 689 s (soft limit 780 s) | ok, vicino al limite | log |
| 18:48:45 | sentiment | DIS +0,351 (×1,2 = 0,421) CFO Disney+ margini | segnale | 10222 |
| **18:52:09** | **esecuzione** | **BUY DIS** 13,843 sh @104,4935 (ordine `4d40554c`) | filled | trade 990 |
| 19:07:23 | stop sync | stop GTC DIS 13 sh creato **un ciclo dopo** l'ingresso | F-022 | `/api/orders` `78086f38` |
| 19:15:09 | Ollama | ultimo timeout della giornata | — | log |
| 19:46:04 | mobile snapshot | Alpaca paper-api non raggiungibile (2 letture) | transitorio, nessun ciclo toccato | worker log |
| 19:52:01 | portfolio | ultimo ciclo (24°) | ok | `portfolio_cycles` |
| 20:00 | NAV | 109.767,54 $ (−142,52 $ sul close prec.), 46 posizioni | — | snapshots |
| 20:07–21:52 | portfolio | 8 run `market_closed` | by design | worker log |
| 20:20 / 22:20 | worker, worker-inference | warm shutdown + riavvio (redeploy) | fuori sessione | log |
| 21:00:00 | decay monitor | 10 `DECAY CRITICAL` (S1, S2, S4) con valori correnti identici; solo `log.critical` | F-004 / F-062 | worker log |
| 22:45:24 | ingest | ultimo aggiornamento `ingestion_stats_daily` alpaca_benzinga | — | tabella |
| n.d. | worker-news-stream | `socket.gaierror [Errno -5]` (DNS) sul WS news + riconnessione | **non databile**: il log non ha timestamp | news-stream log |

---

## 4. Tabella news ingest

### 4.1 Per fonte

| Fonte | fetched | queued | duplicates | discarded_no_ticker | discarded_stale | righe `news_log` | articoli unici | finestra `created_at` |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| alpaca_benzinga | 976 | 526 | **4.359** | 0 | 195 | 191 | 117 | 13:37:37 → 19:59:48 |
| gdelt_gkg | 1.816 | 8 | 0 | 1.808 | 0 | 8 | 8 | 14:33:07 → 19:47:23 |

`duplicates` supera `fetched` di 4,5× (F-007, [DAY-012]). GDELT conferma che serve solo come fonte marginale: il 99,6% delle righe viene scartato per assenza di ticker.

### 4.2 Copertura temporale e latenza (published → created)

| Ora UTC | righe | articoli | latenza mediana | latenza max | timestamp futuri |
|---|---:|---:|---:|---:|---:|
| 13:xx | 18 | 13 | **80,6 min** | 2 h | 0 |
| 14:xx | 48 | 33 | 40,8 min | 1 h | 0 |
| 15:xx | 9 | 8 | 1,9 min | <1 h | 0 |
| 16:xx | 32 | 14 | 2,9 min | <1 h | 0 |
| 17:xx | 45 | 25 | 4,1 min | <1 h | 0 |
| 18:xx | 26 | 20 | 1,1 min | <1 h | 0 |
| 19:xx | 21 | 12 | 2,0 min | <1 h | 0 |

Nessuna riga fuori sessione in `news_log`: il consumatore è gated da `market_closed`. Dalle 15:00 la latenza scende a pochi minuti, quindi il problema di latenza è tutto nell'arretrato d'apertura (F-069/F-019). In 15:xx ci sono solo 9 righe. Non c'è stato un outage: il worker gira regolarmente (`no_items_in_queue`), semplicemente arrivano poche notizie. È la finestra che la charter aveva chiamato «outage Ollama 15-16Z» e che si è già dimostrata inesistente (charter §Esiti, #432).

### 4.3 Scarti in coda (`news_queue_drops`, per `dropped_at`)

| Causa | off-session | in-session | articoli | nota |
|---|---:|---:|---:|---|
| `stale` | **177** (tutte alle 13:37) | 18 (14:xx) | 58 + 7 | età media 8,92 h off / 4,49 h in (le in-session erano già stale al fetch REST) |
| `duplicate_id` | 736 | 3.580 | — | 1,87+ consegne per articolo (WS+REST) |
| `no_ticker` | 0 | 1.808 | — | GDELT |
| `not_tradable` | 51 | 104 | — | simboli fuori watchlist |

### 4.4 Top ticker per volume

| Ticker | righe | segnali | max | min | media |
|---|---:|---:|---:|---:|---:|
| AAPL | 33 | 33 | +0,241 | −0,185 | +0,075 |
| SPY | 13 | 13 | +0,260 | −0,327 | +0,028 |
| NVDA | 9 | 9 | +0,201 | −0,120 | +0,017 |
| META | 7 | 7 | +0,234 | −0,080 | +0,054 |
| MU | 7 | 7 | +0,325 | −0,120 | +0,119 |
| AMD | 6 | 6 | **+0,680** | −0,015 | +0,134 |
| SPCX | 6 | 6 | +0,420 | **−0,435** | −0,025 |
| QQQ | 6 | 6 | +0,129 | −0,314 | −0,070 |
| DIS | 5 | 5 | +0,351 | +0,173 | +0,264 |
| DELL | 4 | 4 | +0,494 | +0,017 | +0,235 |

38/96 simboli di watchlist a zero righe (fra cui il mover IBM +3,38%, 7 sedute consecutive) — [DAY-023].

### 4.5 Qualità e sanitizzazione

- **Entità HTML non decodificate**: 57/199 righe (28,6%) con `&#39;`/`&amp;`/`&#8220;` nel titolo o nel corpo (es. «Merck &amp; Co», «Mad Money Lightning Round ,&#8221;») — [DAY-025], F-076 (fix in main dal 2026-09-21, non ancora attivo il 09-09).
- **Estrazione ticker**: `source_metadata` 191, `org_lookup` 8, **resolver 0** — [DAY-026], F-057.
- **Fan-out**: 30 `content_hash` su più ticker; 191 righe Benzinga → 117 articoli. Il dossier conta `TAG_UNCONFIRMED` 115/199 (57,8%) — [DAY-024], F-012.
- Nessun `published_at` NULL, nessun timestamp futuro, nessun corpo vuoto, nessun `discarded_reason` su `news_log`.
- Nessun articolo scorato due volte: 199 segnali su 199 `news_log_id` distinti. F-072 non si è manifestato: il task più lungo ha chiuso in 689 s contro un soft limit di 780 s.

### 4.6 Top news per impatto sul segnale

| Segnale | Ticker | Ora | Score | Titolo | Esito |
|---|---|---|---:|---|---|
| 10052 | QCOM | 13:41 | +0,706 | Amazon Gives Qualcomm a Major AI Boost With $60B Custom Chip Deal | `SKIP_ENTRY_FRESHNESS` alle 14:07 (articolo 11:48) |
| 10128 | AMD | 16:11 | +0,680 | Why Is AMD Stock Surging on Wednesday? | `SKIP_PYRAMIDING` (S1) |
| 10082 | XLE | 14:16 | +0,531 | Oil Hits $100: Which Stocks And ETFs Win Or Lose? | `SKIP_PYRAMIDING` (S4 detenuto) |
| 10084 | XOM | 14:18 | +0,517 | (idem, fan-out) | `SKIP_PYRAMIDING` (S1) |
| 10119 | DELL | 15:38 | +0,494 | Dell Refinances Debt Following Massive Sales Forecast Hike | `SKIP_PYRAMIDING` (S1) |
| 10117 | SPCX | 15:19 | −0,435 | SpaceX Lockup Alert — 319 Million SPCX Shares Unlock Today | **SELL SPCX** 15:22 |
| 10118 | CMCSA | 15:28 | −0,386 | Comcast CFO Says Q3 Broadband Subscriber Losses Unlikely To Improve | nessun percorso (long-only), CMCSA −6,61% |
| 10222 | DIS | 18:48 | +0,351 | Disney CFO Says Disney+ Had 13% Margin Last Quarter | **BUY DIS** 18:52 |
| 10108 | MU | 14:43 | +0,325 | Memory Is the New 'King' of Chips (Susquehanna) | **BUY MU** 14:52 |

### 4.7 Problemi trovati — news

[DAY-001] arretrato notturno scartato all'apertura · [DAY-002] segnali forti nati fuori finestra di freschezza · [DAY-012] duplicates > fetched · [DAY-023] 38/96 a zero news · [DAY-024] fan-out · [DAY-025] entità HTML · [DAY-026] resolver mai usato. Il log `worker-news-stream` non ha timestamp: non si può datare l'errore DNS del WebSocket (§12).

**Confidenza dell'analisi news: alta** (conteggi da tabelle persistite, riconciliati col log dei task: 177 `skipped_stale` al run delle 13:45 = 177 righe in `news_queue_drops`).

---

## 5. Tabella performance modelli LLM

### 5.1 Chiamate e affidabilità

| Modello | risposte persistite | eleggibili | ineleggibili | timeout (log) | polarity media (eleg.) | confidence media (eleg.) | score medio (eleg.) | min / max score |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| glm-5.2:cloud | 191 | 88 | 103 | 8 | +0,171 | 0,576 | +0,113 | −0,480 / +0,765 |
| gpt-oss:20b-cloud | 190 | 88 | 102 | 9 | +0,170 | 0,607 | +0,119 | −0,420 / +0,680 |
| FinBERT | 5 segnali | — | — | — | — | 0,26 | +0,012 | +0,007 / +0,017 |

`llm_responses` non ha una colonna di latenza e le chiamate Ollama non lasciano traccia di trasporto: **latenza media e p95 non misurabili** ([DAY-014], F-086). Nessun output invalido o refusal persistito. Tutte le 381 risposte hanno `directness` valorizzato, con valori nell'insieme atteso: direct 184, macro 66, sector 65, unclear 27, competitor_readthrough 22, customer_supplier 16, management 1.

### 5.2 Provenienza dei 199 segnali

| `model_id` | segnali | fallback | score medio | ≥ 0,30 in valore assoluto | σ media |
|---|---:|---:|---:|---:|---:|
| ensemble glm-5.2 + gpt-oss | 135 (67,8%) | no | +0,077 | 21 | 0,075 |
| single:gpt-oss | 46 | sì | +0,007 | 1 (AZN +0,420) | 0,000 |
| single:glm-5.2 | 13 | sì | +0,067 | 0 | 0,000 |
| finbert | 5 (2,5%) | sì | +0,012 | 0 | 0,000 |

59 segnali single-model (29,6%) vengono dal filtro di eleggibilità (`min_confidence`): un modello cade sotto soglia e l'altro resta solo. Non vengono da timeout. I 5 FinBERT corrispondono esattamente alle 5 coppie di timeout simultanei (14:35, 16:44, 16:46, 17:30, 17:32). I task però dichiarano **64** `finbert_fallbacks` ([DAY-013], F-078).

### 5.3 Disaccordo fra modelli

- 7 segnali ensemble con σ > 0,20, 16 con σ > 0,15. Massimi: JNJ −0,178 (σ 0,283), ADBE +0,180 (0,283), ROKU −0,273 (0,247), **SPY −0,327 (0,247, sopra il gate)**, GOOGL, AAPL, SPY (0,212). Nessun gate li ha trattati diversamente ([DAY-006], F-037).
- Sui single-model, 4 casi con i due modelli di **segno opposto** sono stati collassati a σ = 0. Il più forte: AZN 10064, glm −0,10×0,30 contro gpt-oss +0,60×0,70, score +0,420 ([DAY-005], F-054). Sul testo i due modelli leggono lo stesso articolo in due modi: Cramer «non metterebbe i soldi su AZN» contro l'approvazione FDA citata nel corpo.
- Nessun caso di un solo modello che domina l'ensemble oltre il peso: i pesi erano uguali.

### 5.4 Verifica funzionale

| Domanda | Esito | Evidenza |
|---|---|---|
| Output validato prima del signal store? | parziale | enum e JSON strutturato presenti; entità HTML non normalizzate (F-076) |
| L'ensemble gestisce la varianza alta? | **no** | σ non è un gate (F-037); σ nascosta sui single (F-054) |
| Le news duplicate pesano più volte? | no | 199 segnali / 199 `news_log_id`; `duplicate_id` scartati in coda |
| La stessa news genera segnali multipli? | sì, per fan-out | 30 hash multi-ticker (F-012) |
| Confidence bassa riduce il peso? | sì | score = polarity × confidence; filtro `min_confidence` |
| LLM offline/background? | **sì** | worker-inference (queue `inference`); il ciclo portfolio legge da DB |
| Rischio che un'allucinazione entri in decisione? | basso oggi | fallback esclusi dal ranking BUY (#108: TM, GM); entrambi i BUY su segnali ensemble ISSUER_SPECIFIC coerenti col testo |

---

## 6. Tabella segnali finali per ticker (sopra il gate 0,30 in valore assoluto, o decisivi)

| Ticker | Segnale | Score grezzo | Score al gate (×velocity) | Esito S4 | Motivo |
|---|---|---:|---:|---|---|
| QCOM | 10052 | +0,706 | — | nessun ordine | `SKIP_ENTRY_FRESHNESS` (articolo 2h19 alle 14:07) |
| AMD | 10128 | +0,680 | +0,816 | nessun ordine | P0-05, detenuto da S1 dal 07-14 |
| XLE | 10082/10160 | +0,531/+0,474 | — | nessun ordine | già detenuto S4 (23 cicli) |
| XOM | 10084/10086 | +0,517/+0,320 | — | nessun ordine | P0-05 (S1) |
| CVX | 10080/10085/10203 | +0,505/+0,371/+0,396 | — | nessun ordine | P0-05 (S1), 19 cicli |
| DELL | 10119 | +0,494 | — | nessun ordine | P0-05 (S1), 3 cicli |
| SPCX | 10117 | −0,435 | — | **SELL 15:22** | `sentiment_reversal` < −0,35 |
| AZN | 10064 | +0,420 (single) | — | nessun ordine | fallback + già detenuto S4 |
| SPCX | 10109 | +0,420 | — | nessun ordine | già detenuto (fan-out Howmet/GE) |
| CMCSA | 10118 | −0,386 | — | nessun ordine | long-only, non detenuto (F-040) |
| NKE | 10062 | −0,355 | −0,284 al gate | nessun ordine | long-only |
| DIS | 10222 | +0,351 | +0,421 | **BUY 18:52** | top-N, fresco |
| SPY | 10097 | −0,327 | — | nessun ordine | long-only, σ 0,247 |
| MU | 10108 | +0,325 | +0,390 | **BUY 14:52** | top-N, fresco |
| HOOD | 10053 | +0,325 | — | nessun ordine | `SKIP_ENTRY_FRESHNESS` |
| MRK | 10123 | +0,322 | — | nessun ordine | P0-05 (S1), 12 cicli |
| QQQ | 10096 | −0,314 | — | nessun ordine | long-only |

Disposizioni S4 del giorno (`s4_intent_events`, disposition): SKIP_ENTRY_GATE 715, SKIP_ENTRY_FRESHNESS 665, SKIP_STALE 118, SKIP_PYRAMIDING 114, RANK_OUTSIDE_TOP_N 40, RANK_LONG_ONLY 19, SKIP_FALLBACK 15, SKIP_IDEMPOTENCY 4, **SUBMITTED 2**.

---

## 7. Tabella ordini generati / eseguiti

| Decisione | Ora | Strat. | Ticker | Azione | Qty | Prezzo atteso (first executable) | Fill | Stato | Broker | Segnale | Risk check | Anomalie |
|---|---|---|---|---|---:|---:|---:|---|---|---|---|---|
| 19957 | 14:52:01 | S4 | MU | BUY (notional) | **1,407** | 1034,99 | 1035,406 | filled 14:52:06 | Alpaca paper | 10108 (+0,390) | gate, freshness, P0-05, top-N, idempotenza | `trades.qty` oggi 0,407 ([DAY-004]) |
| — | 14:52:06 | S4 (stop sync) | MU | SELL stop GTC | 1 | d_hard 12% | 908,56 (il 09-14) | filled 09-14 | Alpaca paper | — | stop d_hard | leg orfana il 09-14 (F-048) |
| 20013 | 15:22:01 | S4 | SPCX | SELL (close) | 9,355 | — | 147,44 | filled 15:22:07 | Alpaca paper | 10117 (−0,435) | hysteresis + reversal, stop cancellato prima | nessuna |
| 20460 | 18:52:01 | S4 | DIS | BUY (notional) | 13,843 | 104,48 | 104,4935 | filled 18:52:09 | Alpaca paper | 10222 (+0,421) | come MU | stop solo alle 19:07 ([DAY-008]) |
| — | 19:07:23 | S4 (stop sync) | DIS | SELL stop GTC | 13 | d_hard | — | canceled (prima dell'uscita del 09-10) | Alpaca paper | — | stop d_hard | copre 13/13,84 sh (parte intera) |

Nessun ordine rifiutato, nessun NO-ORDER: 2 BUY e 1 SELL in Decision Log corrispondono a 3 ordini e 3 fill. `portfolio_cycles.orders_count` somma **120** sui 24 cicli, contro 3 ordini di mercato realmente inviati ([DAY-017], F-014). `execution_decisions.score` sui BUY vale 0,020: è il peso di portafoglio (2%), non lo score del segnale. Il controllo "score < 0,05 con ordine" quindi non si applica. Lo score del segnale è in `signal_score`.

---

## 8. Tabella PnL / rendimento

### 8.1 NAV

| Voce | Valore |
|---|---:|
| Equity close precedente | 109.910,06 $ |
| NAV 13:30 | 109.856,37 $ (gap overnight −53,69 $) |
| NAV 20:00 | **109.767,54 $** |
| Variazione giornaliera | **−142,52 $ (−0,130%)** |
| SPY giornata | −0,46% |
| Posizioni aperte a fine seduta | 46 (45 all'apertura −1 +2) |
| `regime_mult` | 0,7 su tutti i cicli |

### 8.2 P&L realizzato

| Trade | Ticker | Strat. | Aperto | Chiuso | Entry | Exit | Qty | Lordo | Costi | **Netto** | Motivo |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|
| 988 | SPCX | S4 | 09-08 18:52 | 09-09 15:22 | 153,64 | 147,44 | 9,3552 | −58,00 | 1,51 | **−59,51** | `sentiment_reversal` |

Posizione aperta **prima** del 09-09. Tenere fino al close (147,55) avrebbe reso +1,03 $: l'uscita è stata corretta e neutra.

### 8.3 Mark-to-close degli ingressi del giorno (non realizzato)

| Ticker | Qty reale (broker) | Fill | Close | Mark | Nota |
|---|---:|---:|---:|---:|---|
| MU | 1,407 | 1035,406 | 1027,77 | **−10,74 $** | il dossier dichiara −3,11 $ su 0,407 sh ([DAY-004]) |
| DIS | 13,843 | 104,4935 | 104,18 | **−4,34 $** | |

### 8.4 Scomposizione open→close (dossier `snapshot_apertura`, confidenza misurata)

| Blocco | P&L intraday |
|---|---:|
| S1, 38 posizioni pregresse | +0,33 $ (UNH −19,18, GM −14,79 … INTC +20,96, C +13,58) |
| S4, 7 posizioni pregresse (incl. SPCX −43,03 fino all'uscita) | −72,13 $ |
| S4, ingressi del giorno | −15,08 $ (MU −10,74, DIS −4,34) |
| **Totale open→close** | **≈ −86,9 $** |
| Gap overnight (close prec. → open) | ≈ −55,6 $ (per differenza da NAV) |

### 8.5 Costi e slippage

| Trade | `cost_usd` | `slippage_est` | Slippage reale (fill − first executable) × qty |
|---|---:|---:|---:|
| 988 SPCX (uscita) | 1,51 | 1,51 | n.d. (nessun evento d'uscita con prezzo atteso) |
| 989 MU (ingresso) | 0,78 | 0,78 | +0,59 $ (0,416 × 1,407; 4,0 bp) |
| 990 DIS (ingresso) | 0,80 | 0,80 | +0,19 $ (0,0135 × 13,843; 1,3 bp) |

`slippage_est` è ancora una copia di `cost_usd` ([DAY-015], F-015). Il paper Alpaca non addebita commissioni: i costi sono modellati.

---

## 9. Analisi correttezza buy/sell

| Controllo | Esito | Evidenza |
|---|---|---|
| BUY solo quando consentito | ✅ | MU 0,390 e DIS 0,421 ≥ 0,30, ensemble, freschi, top-N, non detenuti |
| SELL/exit corretti | ✅ | SPCX: segnale −0,435 ISSUER_SPECIFIC < −0,35, hysteresis a 2 cicli, stop cancellato prima della vendita |
| Stop-loss rispettati | ⚠️ | stop GTC creati; DIS protetto solo 15 min dopo; AMAT (S1) non proteggibile a −21% tutto il giorno ([DAY-008]) |
| Signal flip | ✅ | unico flip = SPCX |
| Max holding / rebalance band | ✅ | S1 `held`, nessun ribilanciamento; nessuna uscita per età |
| Ordini duplicati | ✅ nessuno | 4× `SIGNAL_DUPLICATE_SKIP` MU, 4 `SKIP_IDEMPOTENCY` |
| Buy e sell ravvicinati / roundtrip < 30 min | ✅ nessuno | |
| Pyramiding (> 3 BUY senza SELL) | ✅ nessuno | P0-05 attivo (114 blocchi) |
| SELL con sentiment positivo (A5) | ✅ nessuno | |
| Ordini su ticker non consentiti | ✅ nessuno | MU, DIS, SPCX in watchlist |
| Ordini fuori orario | ✅ nessuno | fill alle 14:52, 15:22 e 18:52; stop GTC |
| Trade su dati stale | ✅ nessuno | 118 SKIP_STALE e 665 SKIP_ENTRY_FRESHNESS a monte |
| Trade su LLM output non valido / fallback | ✅ nessuno | SKIP_FALLBACK su TM, GM |
| Circuit breaker | n/a | nessun breaker attivo, `constraints=0` su 24 cicli |
| Strategia disabilitata | ✅ | solo S1 e S4 attive |
| Paper/live coerente | ✅ | `paper` in ogni snapshot |
| Idempotenza retry Celery | ✅ | nessun retry, nessun doppio scoring |
| Riconciliazione ordini/fill/posizioni | ⚠️ | 3 ordini ↔ 3 fill ↔ 3 trade; ma `trades.qty` MU oggi diverge dal fill (1,407 → 0,407, [DAY-004]) |

**exit_mechanism (#184):** l'unica uscita (SPCX) ha `exit_mechanism` NULL e `reason` esplicito `sentiment_reversal: score -0.435 < threshold -0.35`, dal ramo osservato. Questo report non conta né interpreta etichette `exit_mechanism` dedotte dall'età.

---

## 10. Anomalie trovate

### [DAY-001] 177 righe dell'arretrato notturno scartate `stale` alla prima passata della seduta

* Tipo: Anomalia (limite di design noto)
* Area: News
* Evidenza:
  * file/log/tabella: `news_queue_drops`; `worker-inference-2026-09-09.log`
  * timestamp: 13:37 (run chiuso alle 13:45:41 con `'skipped_stale': 177`)
  * snippet/query: `SELECT discarded_reason, enqueued_off_session, date_trunc('hour',dropped_at), count(*), count(distinct article_id), avg(age_hours) FROM news_queue_drops WHERE dropped_at::date='2026-09-09' GROUP BY 1,2,3` → stale/t/13:00 = 177 righe, 58 articoli, età 8,92 h
* Descrizione: il WS ingerisce di notte, il consumatore è gated da `market_closed` e alla campana butta tutto ciò che ha più di 2 h. Fra gli scartati ci sono il pezzo Muse su META (04:02, mover +6,55%) e le uniche due notizie societarie su UNH (posizione S1 cieca lato uscita, −8,65%).
* Impatto: l'informazione pre-market non raggiunge mai il modello, e le posizioni risultano "cieche" per colpa della coda, non del provider.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna taratura (freeze). La misura shadow off-session (#432 opzione C) è la strada già registrata.
* Test/monitor consigliato: incrociare `news_queue_drops` stale/off-session con `copertura_uscita` del dossier (proposta già in ALPHA_MISS 09-09 §8).

### [DAY-002] QCOM +0,706 e HOOD +0,325 nascono con la finestra di freschezza già consumata

* Tipo: Anomalia
* Area: News / Signal
* Evidenza:
  * file/log/tabella: `news_log` 10052/10053, `s4_intent_events`, worker log 14:07:06
  * timestamp: pubblicati 11:48:27 e 11:50:22, `raw_ingested_at` identico (WS), scorati 13:41:49 e 13:43:07, primo ciclo 14:07
  * snippet/query: `s4_intent_events` 14:07 QCOM `SKIP_ENTRY_FRESHNESS` (`signal_age_at_slot` 00:25:10); log `S4: dropped 27 signal(s) below entry-freshness (news_age_hours=2.0)`
* Descrizione: il segnale più forte della giornata, issuer-specific (accordo Amazon da 60 mld $), è scorato 1h53 dopo la pubblicazione perché resta in coda fino all'apertura. Al primo ciclo l'articolo ha 2h19 e viene scartato. HOOD fa la stessa fine.
* Impatto: oggi **nessun costo, anzi un risparmio**. Da prezzi Alpaca 1 min: QCOM 178,58 alle 14:07 → close 176,40 (−1,22%, −26,86 $ su 2.200 $); HOOD 117,80 → 115,28 (−2,14%, −47,06 $). Il movimento era già nel gap (F-030). Resta l'evidenza strutturale: la latenza consuma la finestra.
* Severità: Low (oggi)
* Confidenza: High
* Azione consigliata: nessuna taratura. Registrare la ricorrenza.
* Test/monitor consigliato: quota giornaliera dei segnali ≥ 0,30 con `SKIP_ENTRY_FRESHNESS` al primo slot e con `published_at` fuori sessione.

### [DAY-003] P0-05 blocca 40 intenti S4 su 6 titoli S1; tracciabilità 13/114 in Decision Log

* Tipo: Rischio (design)
* Area: Signal / Risk
* Evidenza:
  * file/log/tabella: `s4_intent_events` (reason_code `SKIP_PYRAMIDING`), `execution_decisions`, worker log `P0-05 pyramiding guard`
  * timestamp: 14:07–19:52
  * snippet/query: CVX 19 (primo 14:22), MRK 12 (16:52), MRVL 4 (14:07), DELL 3 (15:52), XOM 1 (14:07), AMD 1 (16:22, +0,816). Sui titoli S4 detenuti: AZN 24, NVO 24, XLE 23, SPCX 3.
* Descrizione: il guard lavora come progettato sui titoli S4. Sui titoli S1 impedisce a S4 di agire sui propri segnali. Solo 13 dei 114 blocchi arrivano in `execution_decisions`.
* Impatto: **controfattuale corto, −93,10 $ evitati**. Prezzo al primo slot bloccato → close, 2.200 $ a titolo: CVX +2,68, MRK −2,40, MRVL −57,79, DELL −38,55, XOM +7,66, AMD −4,70. Oggi il guard ha protetto.
* Severità: Low
* Confidenza: Medium (assume che ogni intento sarebbe entrato nel top-N)
* Azione consigliata: nessuna (freeze). Continuare a misurare il segno del costo nel tempo.
* Test/monitor consigliato: rapporto `SKIP_PYRAMIDING` intents / execution_decisions per giorno.

### [DAY-004] MU: fill da 1,407 azioni, ma `trades.qty` oggi vale 0,407 e il dossier del 09-09 ne eredita l'errore

* Tipo: Bug (evidenza)
* Area: PnL / Data
* Evidenza:
  * file/log/tabella: `s4_lifecycle_events` (MU, `filled_quantity` 1,407003629, `filled_notional` 1456,82), `trades` 989 (`qty` 0,407003629, `entry_notional` 1456,83, `quantity_remaining` 1), `/api/orders` `d464e257` e `f7e44edd`, `docs/evidence/dossier/2026-09-09.json` `ingressi[MU].mtm_eod` = −3,108
  * timestamp: fill 14:52:06; stop 1 sh inviato 14:52:06, riempito il 2026-09-14 13:32:07 @908,56
  * snippet/query: `SELECT qty, entry_notional, quantity_remaining FROM trades WHERE id=989;` → 0,407 × 1035,406 = 421,4 ≠ 1456,83
* Descrizione: il 09-14 la leg dello stop (1 sh) non è stata scritta su `trades` e `qty` è stata ridotta al residuo (F-048). Il dossier del 09-09, generato il 09-24, legge la `qty` mutata e retrodata l'errore: marca MU a −3,11 $ invece di −10,74 $, e la tabella del libro dell'ALPHA_MISS 09-09 riporta quantità 0,4070.
* Impatto: l'evidenza di una seduta chiusa cambia a seconda di quando si rigenera il dossier. Il P&L non registrato (−126,85 $ lordi) è già contato nell'occorrenza F-048 del 09-14.
* Severità: Medium
* Confidenza: High
* Azione consigliata: ticket di correttezza (esente dal freeze): `trades` non deve perdere la quantità d'ingresso; il dossier deve leggere la quantità dal lifecycle/fill, non dal ledger mutabile.
* Test/monitor consigliato: invariante `abs(entry_notional − qty·entry_price) / entry_notional < 1%` su ogni trade; test che rigenera un dossier storico dopo una chiusura parziale e confronta.

### [DAY-005] Divergenza di segno collassata a σ = 0 dal filtro di eleggibilità (AZN +0,420)

* Tipo: Rischio
* Area: LLM
* Evidenza:
  * file/log/tabella: `sentiment_signals` 10064, `llm_responses`
  * timestamp: 13:55:38
  * snippet/query: glm-5.2 polarity −0,10 × conf 0,30 (sotto soglia) · gpt-oss +0,60 × 0,70 → `single:gpt-oss` +0,420, `ensemble_std` 0,000. Altri 3 single-model con segni opposti.
* Descrizione: il modello dissenziente cade sotto `min_confidence` e sparisce, e con lui la misura del disaccordo. Il fix F-054 (`edfd73e0`, 2026-09-21) non era ancora in produzione.
* Impatto: nullo oggi (fallback escluso dal ranking BUY, AZN già detenuto, score positivo). Evidenza di varianza persa.
* Severità: Low
* Confidenza: High
* Azione consigliata: verificare dopo il deploy che il warning F-054 compaia su casi analoghi.
* Test/monitor consigliato: conteggio giornaliero di `ensemble_std=0` con risposte di segno opposto.

### [DAY-006] Sette segnali con σ > 0,20, uno sopra il gate, senza alcun trattamento

* Tipo: Rischio
* Area: LLM / Signal
* Evidenza:
  * file/log/tabella: `sentiment_signals` × `llm_responses`
  * timestamp: 13:50–18:43
  * snippet/query: SPY 10097 −0,327 (glm −0,65×0,60 / gpt-oss −0,30×0,60, σ 0,247); JNJ σ 0,283; ADBE σ 0,283; ROKU σ 0,247
* Descrizione: σ non è un gate d'ingresso né un flag di revisione; è letta solo dal postmortem.
* Impatto: nessun ordine oggi (tutti short-side o sotto gate).
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna taratura; resta nel backlog F-037.
* Test/monitor consigliato: quota giornaliera σ > 0,20 fra i segnali sopra gate.

### [DAY-007] Segnali ribassisti sopra il gate senza percorso: CMCSA −0,386 su un −6,61%

* Tipo: Rischio (design long-only)
* Area: Signal
* Evidenza:
  * file/log/tabella: `sentiment_signals` 10118, 10062, 10097, 10096; dossier `funnel_v2.righe[CMCSA]`
  * timestamp: 13:53–15:28
  * snippet/query: CMCSA −0,386 ISSUER_SPECIFIC (CFO broadband), NKE −0,355, SPY −0,327, QQQ −0,314 → `RANK_LONG_ONLY`
* Descrizione: l'unico uso del lato ribassista è l'uscita (SPCX, che ha funzionato). Sui titoli non detenuti il segnale è inerte per costruzione.
* Impatto: non stimabile nel book long-only.
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna (freeze).
* Test/monitor consigliato: già coperto dal funnel_v2 (`non_actionable_long_only`).

### [DAY-008] AMAT non proteggibile a −21% per tutta la seduta; lo stop DIS nasce un ciclo dopo l'ingresso

* Tipo: Rischio
* Area: Risk
* Evidenza:
  * file/log/tabella: worker log `#161`, `/api/orders` `78086f38`
  * timestamp: AMAT 14:07:08 (−21,0%) → 19:52:45 (−21,1%), 24 cicli; DIS BUY 18:52:09, stop 19:07:23
  * snippet/query: `#161: 10/45 held positions are unprotectable (qty < 1): ['AMAT','AMD','ASML','CAT','DELL','LLY','MRVL','NOK','SPY','WDC']`; `Fractional protective stop sync: {'created': 1 ...}` alle 19:07:23
* Descrizione: 10 posizioni sotto l'azione intera restano senza stop broker. AMAT è oltre il d_hard shadow (12–20%). DIS è rimasta scoperta 15 minuti; MU invece è stata protetta nello stesso ciclo.
* Impatto: rischio di coda non coperto; nessuna perdita materializzata oggi.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna taratura. L'alert deve almeno arrivare ([DAY-009]).
* Test/monitor consigliato: tempo ingresso → stop per ogni BUY.

### [DAY-009] Unico alert Telegram della giornata respinto con 400 (AMAT a −21%)

* Tipo: Bug
* Area: Ops
* Evidenza:
  * file/log/tabella: `worker-2026-09-09.log`
  * timestamp: 14:07:08,696
  * snippet/query: `TelegramNotifier: Failed to send alert: Client error '400 Bad Request' ... /sendMessage`
* Descrizione: l'alert #161 su AMAT non arriva all'operatore. Stesso meccanismo del 09-08 (escape HTML troncato da `curl -d`/payload, #591).
* Impatto: la sola posizione oltre il d_hard shadow non è segnalata.
* Severità: Medium
* Confidenza: High
* Azione consigliata: verificare che la correzione #591 copra anche il `TelegramNotifier` Python.
* Test/monitor consigliato: contatore dei 400 Telegram con alert di fallback su canale diverso.

### [DAY-010] Il bot token Telegram è in chiaro nel log httpx a livello INFO

* Tipo: Rischio (sicurezza)
* Area: Ops
* Evidenza:
  * file/log/tabella: `worker-2026-09-09.log`
  * timestamp: 14:07:08,696
  * snippet/query: `HTTP Request: POST https://api.telegram.org/bot<REDATTO>:<REDATTO>/sendMessage "HTTP/1.1 400 Bad Request"`
* Descrizione: il token compare integro nei log persistenti su disco.
* Impatto: esposizione di credenziale.
* Severità: Medium
* Confidenza: High
* Azione consigliata: logger `httpx` a WARNING, rotazione del token.
* Test/monitor consigliato: grep CI/cron per `bot[0-9]+:` nei log persistenti.

### [DAY-011] Finestra cieca 13:30–14:07: mercato aperto, nessun ciclo e nessun fetch REST

* Tipo: Anomalia
* Area: Ops
* Evidenza:
  * file/log/tabella: `portfolio_cycles`, worker log
  * timestamp: primo ciclo 14:07:01, primo fetch Alpaca REST 14:00:01; apertura 13:30 EDT
  * snippet/query: `SELECT min(timestamp) FROM portfolio_cycles WHERE timestamp::date='2026-09-09'` → 14:07:01
* Descrizione: le schedule beat usano `hour=14-21` UTC fisso. In EDT i primi 37 minuti di sessione sono scoperti.
* Impatto: nessun costo attribuibile oggi (QCOM sarebbe scaduto comunque entro le 13:48).
* Severità: Medium
* Confidenza: High
* Azione consigliata: già a ledger (F-021).
* Test/monitor consigliato: ritardo apertura → primo ciclo per seduta.

### [DAY-012] `duplicates` 4.359 contro `fetched` 976 per alpaca_benzinga

* Tipo: Bug (osservabilità)
* Area: Data
* Evidenza: `ingestion_stats_daily` 2026-09-09; log `Alpaca ingestion stats: {'fetched': 33, 'tickers_found': 135, 'queued': 0, 'duplicates': 135}` (14:15)
* Descrizione: il contatore conta coppie articolo×ticker e somma ogni polling.
* Impatto: il rapporto duplicati/fetched non è interpretabile.
* Severità: Low · Confidenza: High
* Azione consigliata: già a ledger (F-007).
* Test/monitor consigliato: invariante `duplicates ≤ tickers_found`.

### [DAY-013] Il task dichiara 64 `finbert_fallbacks`, ma FinBERT è intervenuto 5 volte

* Tipo: Bug (osservabilità)
* Area: LLM
* Evidenza: somma dei campi `finbert_fallbacks` nei risultati `run_sentiment_worker` = 64; `sentiment_signals` model_id='finbert' = 5; single-model = 59
* Descrizione: le letture a modello singolo sono contate come fallback FinBERT.
* Impatto: "FinBERT fallback rate" letto dai task = 32% invece di 2,5%.
* Severità: Low · Confidenza: High
* Azione consigliata: già a ledger (F-078).
* Test/monitor consigliato: riconciliazione giornaliera dei contatori del task con `sentiment_signals.model_id`.

### [DAY-014] Uptime e latenza Ollama non misurabili: restano 17 righe di timeout

* Tipo: Non verificabile
* Area: LLM / Ops
* Evidenza: `llm_responses` senza colonna di latenza; log con soli `Ollama timeout (Ns)` alle 13:39, 13:41, 14:35 ×2, 16:23, 16:42, 16:44 ×2, 16:46 ×2, 17:30 ×2, 17:32 ×2, 17:38, 17:42, 19:15
* Descrizione: l'unico indizio di salute è la durata dei task (58–689 s).
* Impatto: la domanda "Ollama up/down" si risponde solo per assenza di timeout.
* Severità: Low · Confidenza: High
* Azione consigliata: già a ledger (F-086).
* Test/monitor consigliato: latenza per chiamata persistita.

### [DAY-015] `slippage_est` = `cost_usd` sui 3 trade toccati; lo slippage reale è misurabile dal lifecycle

* Tipo: Bug (evidenza)
* Area: PnL
* Evidenza: trades 988/989/990 `slippage_est` = `cost_usd` (1,51 / 0,78 / 0,80); lifecycle MU 1035,406 vs 1034,99 (+0,59 $), DIS 104,4935 vs 104,48 (+0,19 $)
* Severità: Low · Confidenza: High
* Azione consigliata: già a ledger (F-015).
* Test/monitor consigliato: slippage da `fill_price − first_executable_price`.

### [DAY-016] `ENTRY_RECONCILIATION` riemesso: 9 righe per 2 ingressi del giorno

* Tipo: Bug (evidenza)
* Area: Data
* Evidenza: `s4_lifecycle_events` 09-09: AZN, HOOD, NVO, QCOM, SPCX `922327c4` (ingresso del 09-08 già chiuso il 09-08 alle 18:07) alle 14:12 **e** alle 15:27, SPCX `9cdf18d3` alle 15:27, MU 14:57, DIS 18:57
* Descrizione: gli ingressi del giorno prima vengono riconciliati di nuovo; SPCX `922327c4` compare due volte nella stessa giornata.
* Severità: Low · Confidenza: High
* Azione consigliata: già a ledger (F-061).
* Test/monitor consigliato: unicità `(order_id, event_type)`.

### [DAY-017] `portfolio_cycles.orders_count` = 120 contro 3 ordini inviati

* Tipo: Bug (osservabilità)
* Area: Orders
* Evidenza: `SELECT sum(orders_count) FROM portfolio_cycles WHERE timestamp::date='2026-09-09'` → 120; 5 `orders_before/after` per ciclo nel log
* Severità: Low · Confidenza: High
* Azione consigliata: già a ledger (F-014).
* Test/monitor consigliato: confronto `orders_count` ↔ ordini broker per ciclo.

### [DAY-018] `signal_score` a provenienza mista: moltiplicato sui BUY, grezzo sugli skip, `velocity_multiplier` NULL

* Tipo: Bug (evidenza)
* Area: Signal
* Evidenza: `execution_decisions` 19957 MU `signal_score` 0,390 = 0,325 × 1,2; 20460 DIS 0,421 = 0,351 × 1,2; SKIP_THRESHOLD HOOD 0,255 = grezzo; `velocity_multiplier` NULL su tutte le righe
* Descrizione: nella stessa colonna convivono due grandezze senza un marcatore che le distingua (migrazione 077/#550 successiva alla data).
* Severità: Low · Confidenza: High
* Azione consigliata: già a ledger (F-073).
* Test/monitor consigliato: `velocity_multiplier` NOT NULL dopo il deploy #550.

### [DAY-019] DECAY CRITICAL con valori correnti identici per S1, S2 e S4

* Tipo: Bug
* Area: Risk
* Evidenza: worker log 21:00:00: IC corrente −0,054 e hit rate 29,6% identici per S1, S2 e S4, confrontati con baseline 0,035 / 0,042 / 0,028
* Descrizione: metrica pipeline-globale contro baseline per-strategia (S2 non è nemmeno attiva).
* Severità: Low · Confidenza: High
* Azione consigliata: già a ledger (F-004).
* Test/monitor consigliato: test che fallisce se due strategie producono metriche correnti identiche.

### [DAY-020] I 10 alert CRITICAL del decay monitor esistono solo come `log.critical`

* Tipo: Bug
* Area: Ops
* Evidenza: worker log 21:00:00,022–033; nessuna consegna Telegram/mobile
* Severità: Low · Confidenza: High
* Azione consigliata: già a ledger (F-062).
* Test/monitor consigliato: ogni `CRITICAL` deve produrre un evento su un canale.

### [DAY-021] Il fetch del benchmark SPY fallisce 84 volte in 13 minuti (limite SIP)

* Tipo: Bug (osservabilità)
* Area: Data
* Evidenza: worker log 00:00:01–00:13:03, `subscription does not permit querying recent SIP data`
* Severità: Low · Confidenza: High
* Azione consigliata: già a ledger (F-016).
* Test/monitor consigliato: alert al primo fallimento persistente.

### [DAY-022] Rilevazione del regime fallita (FRED 500) e task registrato `succeeded`

* Tipo: Bug
* Area: Ops
* Evidenza: worker-inference log 07:00:05,022 `Failed to fetch macro data for regime detection: Server error '500'` → 07:00:05,255 `detect_regime ... succeeded in 5.25s: None`
* Descrizione: `regime_mult` resta 0,7 dal giorno prima; il fallimento non ha stato né alert.
* Severità: Low · Confidenza: High
* Azione consigliata: già a ledger (F-017).
* Test/monitor consigliato: età del regime corrente > 24 h → alert.

### [DAY-023] 38/96 simboli senza alcuna riga news, fra cui il mover IBM (+3,38%)

* Tipo: Anomalia
* Area: News
* Evidenza: dossier `mercato.watchlist_zero_news` = 38; IBM `sedute_consecutive_zero_articoli` 7, `candidati_miss[IBM].opportunity_v2.net_opportunity_usd` 82,29 $; 11 ticker in allerta (≥ 5 sedute)
* Descrizione: sull'unico mover NO_NEWS non c'è stata alcuna notizia, né in coda né in `news_log`.
* Impatto: 82,29 $ (congetturale, formula del dossier: primo ciclo eleggibile → close su 2.200 $, al netto dei costi).
* Severità: Medium · Confidenza: Medium
* Azione consigliata: nessuna taratura; decisione sulle fonti già in corso (#602).
* Test/monitor consigliato: `ticker_allerta_zero_articoli` nel digest.

### [DAY-024] Fan-out: 57,8% delle righe `TAG_UNCONFIRMED`, 30 articoli su più ticker

* Tipo: Anomalia
* Area: News / Signal
* Evidenza: dossier `mapping_rilevanza`; `news_log` 30 `content_hash` con più righe; SPCX 10109 +0,420 da «Elon Musk Spooked Howmet. GE Just Validated the Bull Case» (2 ticker)
* Impatto: nessun ordine nato da fan-out oggi (MU e DIS sono issuer/settore coerenti).
* Severità: Low · Confidenza: High
* Azione consigliata: già a ledger (F-012).
* Test/monitor consigliato: quota fan-out fra i segnali ≥ 0,30.

### [DAY-025] 57/199 righe con entità HTML non decodificate nel prompt

* Tipo: Bug
* Area: News / LLM
* Evidenza: `news_log` titoli e corpi con `&#39;`, `&amp;`, `&#8220;` (es. 10064 «Mad Money Lightning Round ,&#8221;», 10123 «Merck &amp; Co»)
* Severità: Low · Confidenza: High
* Azione consigliata: fix già in main (`edfd73e0`); verificarne il deploy.
* Test/monitor consigliato: conteggio giornaliero di `&#?[a-z0-9]+;` sugli input scorati.

### [DAY-026] Resolver deterministico mai usato: `source_metadata` 191, `org_lookup` 8, resolver 0

* Tipo: Anomalia
* Area: News
* Evidenza: `SELECT extraction_method, count(*) FROM news_log WHERE created_at::date='2026-09-09' GROUP BY 1`
* Severità: Low · Confidenza: High
* Azione consigliata: già a ledger (F-057); gated sul golden set (QX-01).
* Test/monitor consigliato: quota `resolver` > 0.

---

## 11. False positive e aree risultate corrette

- **«Outage Ollama 15-16Z»**: non esiste. In 15:xx ci sono 9 segnali, tutti ensemble, zero fallback e zero timeout. Il worker gira a vuoto (`no_items_in_queue`) perché arrivano poche notizie. Conferma della charter (§Esiti #432).
- **Uscita SPCX**: corretta. La notizia è vera e dell'emittente (lockup), lo stop è stato cancellato prima della vendita e tenere avrebbe reso solo +1,03 $.
- **Idempotenza**: `SIGNAL_DUPLICATE_SKIP` ×4 su MU, 4 `SKIP_IDEMPOTENCY`, nessun doppio ordine, nessun doppio scoring (199/199).
- **Stop MU**: creato nello stesso ciclo dell'ingresso, sulla parte intera della quantità reale (1 su 1,407), GTC.
- **Tracciabilità segnale → decisione**: 735/736 righe con `signal_id` (l'unico NULL è su un SKIP_PYRAMIDING). F-011 oggi non si manifesta.
- **Fallback esclusi dal BUY**: TM (+0,180) e GM (−0,120) `SKIP_FALLBACK`.
- **Guard P0-05 e freshness**: a controfattuale corto hanno evitato −93,10 $ e −73,92 $.
- **Nessuna riga in `news_log` fuori sessione**, nessun timestamp futuro, nessun ordine fuori orario.
- **API REST**: con `X-API-Key` tutti e 5 gli endpoint rispondono 200. F-041 (bearer JWT rifiutato) non si applica a questo protocollo.

## 12. Dati mancanti o non accessibili

- **`finbert_fallback_events`**: 0 righe il 09-09. La tabella esiste dal 2026-09-10, quindi il dato è **non misurato**, non "nessun fallback". Non si può confermare se FinBERT abbia visto parte del corpo nei 5 fallback (conferma residua di #453). I 5 segnali FinBERT hanno `reasoning` = «FinBERT fallback (Ollama timeout)».
- **Latenza e uptime Ollama**: nessuna persistenza (F-086).
- **`worker-news-stream-2026-09-09.log`**: le righe non hanno timestamp. L'errore DNS del WebSocket (`[Errno -5] No address associated with hostname`) e la riconnessione non sono databili, quindi non si può dire se abbiano aperto un buco nell'ingest. Query che servirebbe: gap in `news_queue_drops.raw_ingested_at` / `news_log.raw_ingested_at` con `transport='ws'`, ma `transport` è NULL su tutte le righe del giorno (migrazione 075 successiva).
- **`/api/trades` e `/api/decisions`** restituiscono solo le ultime righe (limit): per il 09-09 fa fede il DB. `/api/orders?limit=500` copre fino al 2026-07-27 ed è stato usato per gli ordini broker.
- **`economic_pnl.json`** non contiene il 09-09 (seduta recuperata); i cumulati dell'ALPHA_MISS la escludono.
- **Slippage in uscita** (SPCX): nessun evento lifecycle d'uscita con prezzo atteso.

## 13. Raccomandazioni immediate (solo correttezza, charter in vigore)

1. **[DAY-004]** Rendere immutabile la quantità d'ingresso in `trades` (o far leggere al dossier la quantità dal fill) prima che altri dossier storici vengano rigenerati. Oggi la rigenerazione riscrive la storia.
2. **[DAY-009]/[DAY-010]** Verificare che la correzione #591 copra il `TelegramNotifier`, abbassare `httpx` a WARNING e ruotare il token.
3. **[DAY-022]** Far fallire `detect_regime` quando la sorgente macro non risponde (stato + alert).
4. Aggiungere i timestamp al log di `worker-news-stream`.
5. Verificare in produzione il deploy di `edfd73e0` (F-054 + F-076).

## 14. Test o monitor da aggiungere

- Invariante `entry_notional ≈ qty × entry_price` su `trades`.
- Riconciliazione dei contatori del task sentiment (`finbert_fallbacks`, `ensemble_success`) con `sentiment_signals.model_id`.
- Tempo ingresso → primo stop broker per ogni BUY.
- Monitor "ritardo apertura → primo ciclo" e "segnali ≥ 0,30 scartati per freshness al primo slot".
- Quota `ensemble_std=0` con risposte di segno opposto.
- Consegna garantita degli alert `CRITICAL` (canale ≠ log).
- Timestamp obbligatorio in tutti i log dei container.

## 15. Ticket tecnici suggeriti

| Ticket | Tipo | Finding |
|---|---|---|
| `trades.qty` non deve essere riscritta alla chiusura; il dossier deve leggere la quantità dal lifecycle | correttezza evidenza | F-048 |
| `detect_regime`: fallimento con stato FAILURE + alert | correttezza | F-017 |
| Formato log con timestamp per `worker-news-stream` | osservabilità | — |
| Contatori del task sentiment coerenti con `model_id` | correttezza evidenza | F-078 |
| Verifica deploy `edfd73e0` in produzione | verifica | F-054, F-076 |

## 16. Stato sistema

### Ollama
- **Up** per tutta la sessione: nessun buco nei segnali ensemble dalle 13:41 alle 19:5x. **Downtime: 0 h.**
- 17 timeout (9 gpt-oss, 8 glm), di cui 5 coppie simultanee → FinBERT.
- Latenza non misurabile (F-086). Durata dei task sentiment: 58–689 s.

### FinBERT / fallback
- FinBERT: **5/199 segnali (2,5%)**; 0/3 decisioni d'ordine.
- Single-model (filtro eleggibilità): 59/199 (29,6%). Complessivo `fallback_used=true`: 64/199 (32,2%).
- Nessun periodo con fallback su tutti i simboli.
- `finbert_fallback_events`: non ancora esistente (dal 2026-09-10).

### Worker restart
- `worker` e `worker-inference`: warm shutdown + riavvio alle **06:20, 20:20, 22:20** (redeploy), tutti fuori sessione. Nessun restart in RTH.
- `worker-news-stream`: 1 errore DNS + riconnessione WebSocket, orario non determinabile.

### Infrastruttura
- Rete: errori transitori alle 15:44 e 19:25 (polling Telegram) e alle 19:46 (Alpaca paper-api, mobile snapshot). Nessun ciclo di portafoglio toccato.
- API: 10.472 risposte 200, 3 risposte 403, nessun `PoolError`.
