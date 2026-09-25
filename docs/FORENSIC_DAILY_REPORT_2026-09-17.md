# Forensic Daily Report — 2026-09-17

Sessione forense autonoma, sola lettura, eseguita il 2026-09-24. Fuso operativo **UTC** (`src/workers/celery_app.py`:
`timezone="UTC"`, `enable_utc=True`). Tutti i timestamp del report sono UTC. RTH 13:30–20:00 UTC (EDT). Il conto
**paper** è verificato: `portfolio_monitor_snapshots.broker_environment='paper'` e `mode='paper'` su tutte le istantanee
della giornata.

Periodo di **sola osservazione** (`docs/evidence/OBSERVATION_CHARTER.md`, scadenza 2026-09-28). Il report non propone
tarature. I ticket riguardano solo difetti di correttezza o di strumentazione.

Contesto: ensemble **glm-5.2 + gpt-oss** (pre-swap GLM-5.3, avvenuto il 22/09). Fix F-076/F-054 (`edfd73e0`) **non ancora
deployato**. Tre ricreazioni dei worker fuori seduta (06:20, 08:20, 20:20). Questo report integra, senza duplicarlo,
`docs/ALPHA_MISS_REPORT_2026-09-17.md`, che ha già registrato occorrenze del 17/09 per F-012, F-030 e F-031.

---

## 1. Executive summary

La pipeline ha girato end-to-end senza interruzioni: 215 righe scorate (123 articoli; 202 Benzinga, 13 GDELT) → 215 segnali →
24 cicli portfolio → 5 BUY e 2 SELL S4, tutti `filled` sul conto paper, riconciliati (`anomalies: 0`). Nessun ordine fuori orario,
duplicato o senza segnale. L'idempotenza regge (22 `SKIP_IDEMPOTENCY`). Ollama è rimasto su per tutta la seduta: 11 timeout
gpt-oss fra le 13 e le 14, nessun fallback FinBERT reale (0 righe `finbert_fallback_events`), 86 segnali a modello singolo (40%).
NAV +549,60 $ (+0,50%) contro SPY +1,13% e QQQ +1,73%, con esposizione lorda 0,31–0,37. S4: realizzato +17,43 $ (SPCX +5,69,
META +11,74). Mark open→close ≈ +135,7 $, quasi tutto dalle 7 posizioni preesistenti (INTC +59,6, PANW +37,2).

Il difetto principale è **F-089, cinque giorni prima del suo primo avvistamento**. Sei posizioni S4, fra cui MU comprata oggi,
stanno nel target congelato di S1 e non escono. Hanno ricevuto segnali freschi sotto gate: XLE −0,325, QQQ −0,201, MU 0,000.
Il risultato è solo `SKIP_THRESHOLD`. Con la stessa regola SPCX, fuori dal target S1, è stata venduta a +0,042. Oggi il disarmo
costa 5,46 $ (attribuito). Pesa di più il fatto che la P&L S4 sia già contaminata da prima del 22/09. Il BUY BA passa il gate
solo col punteggio moltiplicato (0,274 × 1,2 = 0,3285). `execution_decisions` persiste invece il grezzo (F-073). Per il resto,
difetti di osservabilità già noti.

## 2. Verdict

**OK con warning, con un'anomalia significativa per l'evidenza (F-089).**

Il percorso del denaro è corretto: ogni ordine ha segnale, gate, ranking, P0-05, idempotenza, fill e riconciliazione. Il
problema è interpretativo. La serie S4 del 17/09 include sei posizioni la cui uscita S4 non può scattare. Va quindi letta
insieme alla dichiarazione che il charter dovrà fare per F-089. La contaminazione non parte dal 22/09 ma è almeno di
questa data.

---

## 3. Timeline del 2026-09-17 (UTC)

| Ora | Componente | Evento | Esito | Fonte |
|---|---|---|---|---|
| 00:00–13:29 | `worker-news-stream` | WS Benzinga 24/7; 106 dispatch di `run_sentiment_worker` fuori seduta | `skipped: market_closed` | `worker-inference-2026-09-17.log` |
| 02:00–13:33 | ingest WS | 727 `duplicate_id` accodati fuori seduta | scartati | `news_queue_drops` |
| 06:18:10 | Ollama | gpt-oss **503 Service Unavailable** (fuori seduta, shadow) | isolato | log inference |
| 06:20 / 08:20 | deploy | Warm shutdown di `worker` + `worker-inference`; `WorkerLostError` (SIGTERM) su 1 job ciascuno; «Restoring 4 unacknowledged message(s)» | ripartiti | log worker/inference |
| 07:00–07:01 | `detect_regime` | FRED VIX/T10Y2Y ok, regime **sideways ×0,7** | `succeeded` | log inference |
| 10:28–10:29 | `sentiment_shadow` | SoftTimeLimit → TimeLimitExceeded(840) → **SIGKILL** (lotto di 12 item) | turno prosegue | log inference |
| 11:15:35 | Ollama | glm-5.2 `invalid` (JSON non estraibile), fuori seduta | isolato | log inference |
| 13:30:00 | snapshot | NAV 109.280,36, 42 posizioni; degradazioni `signal`/`portfolio_cycle` stale | warning | `portfolio_monitor_snapshots` |
| 13:30:01 | alert | `pipeline:portfolio_cycle_late` **CRITICAL** (fino alle 14:08) + `signal_stale` (fino alle 13:35) | recovered | `mobile_events` |
| 13:30:40 | `detect_regime` | secondo giro, sideways ×0,7 | ok | log |
| 13:33:47 | `sentiment` | drenaggio coda notturna: **211 stale** + 82 `not_tradable` (WS, `enqueued_off_session`) | scartati | `news_queue_drops` |
| 13:34:15 | `sentiment` | primo segnale della seduta | — | `sentiment_signals` |
| 13:34:43 | `sentiment` | **CRM +0,423** (ensemble) sopra gate | sovrascritto 14:03 da 0,000 prima del primo ciclo (DAY-007) | 11314 → 11354 |
| 13:35–14:59 | Ollama | 11 timeout gpt-oss → segnali single glm | Ollama su | log inference |
| 14:00:00 | loss-feedback | S4 `triggered: True` (EWMA R −0,67, 6 perdite), **ratchet congelato** 0,30→0,30 | alert Telegram **400** | log worker |
| 14:00:53 | `sentiment` | **NVDA +0,496** (ensemble) | sovrascritto **76 s dopo** da +0,013 (DAY-008) | 11347 → 11351 |
| **14:07:00** | `portfolio-cycle` | **primo ciclo, 37 min dopo l'apertura** | `portfolio_cycle_late` rientra 14:08 | `portfolio_cycles` 1538 |
| 14:07:05 | S4 | «dropped 22/35 stale signals»; SKIP_PYRAMIDING XOM +0,42 e MRVL +0,309; SKIP_FALLBACK NOK +0,42 | nessun ordine | `execution_decisions`, log |
| 14:07–14:37 | S4 | INTC +0,219, PANW −0,008, XLE 0,000, QQQ −0,201, MRVL +0,218: posizioni S4 **tenute** | solo `SKIP_THRESHOLD` (DAY-001) | `execution_decisions` |
| 14:22:06 | Telegram | alert (AMAT/WDC scoperte) | **400 Bad Request** ×2 | log worker |
| 15:07:01 | S4 → broker | **BUY SPCX** 9,3537 @154,19 (segnale 11413 +0,355, rank 3) | `filled` 15:07:06 | trade 1012 |
| 15:22:05 | stop sync | stop SPCX qty 9 (96,2%) | canceled all'uscita | ordine `7aa7da66` |
| 15:37:01 | S4 → broker | **BUY META** 2,1248 @675,43 (11423 +0,450 → ranking 0,54) | `filled` | trade 1013 |
| 15:52:01 | S4 → broker | **BUY MU** 1,4634 @978,848 (11425 +0,493 → 0,592; `shadow_late_entry`, percentile 0,77) | `filled` | trade 1014 |
| 15:52:05 | stop sync | stop MU **qty 1 su 1,4634 (68,3%)** nello stesso ciclo; stop META qty 2 (94,1%) | MU `new` | ordini `b202b816`, `a85afb1b` |
| 16:07:01 | S4 → broker | **BUY BA** 7,1955 @199,23 (11429 **+0,274 grezzo**, 0,3285 dopo velocità, rank 5) | `filled` | trade 1015 (DAY-002) |
| 16:22:05 | stop sync | stop BA qty 7 (97,3%) | canceled | `fd38635c` |
| 16:52:01 | S4 → broker | **BUY NVO** 33,2014 @43,1093 (11457 +0,349 → 0,4186; percentile **0,97**) | `filled` | trade 1016 |
| 17:07:06 | stop sync | stop NVO qty 33 (99,4%) | canceled | `102d1903` |
| 17:14:14 | `sentiment` | SPCX +0,042 (glm +0,25/0,45 vs gpt −0,3/0,4 `ambiguous_entity`, std 0,389) | — | 11465 |
| 17:35:47 | `sentiment` | XLE **−0,325** (ensemble) su posizione S4 | tenuta (DAY-001) | `sentiment_signals` |
| 17:36:28 | `sentiment` | MU 0,000 (ensemble); hold minimo scaduto alle 17:22 | MU **non venduta** (DAY-001) | 11494 |
| 17:37:01 | S4 → broker | **SELL SPCX** (tutta) `below_entry_gate` su +0,042 | `filled` @154,96, net **+5,69 $** | trade 1012, `80d8050a` |
| 18:35–19:12 | `sentiment` | coda vuota (36 min senza segnali); alert `signal_stale` 18:59–19:13 | nessun guasto: `no_items_in_queue` | log, `mobile_events` |
| 19:52:01 | S4 → broker | **SELL META** (tutta) `fallback_filtered`: ensemble +0,45 invecchiato (4,3 h > 4 h), ultimo segnale single gpt-oss +0,04 | `filled` @681,09, net **+11,74 $** | trade 1013, `a507446f` |
| 19:52:21 | stop monitor | #161 AMAT **−29,6%**, WDC **−22,9%** scoperte (sub_one_share) | solo log | log worker |
| 19:55:40 | `sentiment` | ultimo segnale della seduta | — | — |
| 20:00:00 | snapshot | NAV **109.457,37**, variazione **+549,60 $**, 45 posizioni | — | `portfolio_monitor_snapshots` |
| 20:20 | deploy | terza ricreazione dei worker | fuori seduta | log |
| 21:00:00 | `decay_monitor` | 11 righe **DECAY CRITICAL** (S1/S2/S4 con lo stesso IC −0,054) | solo log | log worker |
| 21:30–21:57 | reconcile | `run_reconcile_fills_intraday` ×3: updated 0, 24 eventi lifecycle | ok | log worker |
| 21:35:02 | `reconcile-positions` | 44 `fully_held` + 1 `partially_wound_down_coheld`, **anomalies 0** | — | log worker |
| 22:50:00 | alert | `portfolio_cycle_session_grid` + `held_no_news_loss` PFE/SBUX **aperti e chiusi in 1 s** | — | `mobile_events` |

---

## 4. News ingest

### 4.1 Per fonte

| Fonte | Trasporto | Estrazione | Righe scorate | Articoli | Ticker | Prima–ultima | Lag pub→riga mediano / p90 | Fetched (stats) | Duplicati (stats) | Scartati (drops) |
|---|---|---|---|---|---|---|---|---|---|---|
| alpaca_benzinga | ws | source_metadata | 196 | 109 | 55 | 13:34:15–19:55:40 | 5,2 / 98,3 min | 1.559 | **7.291** | stale 211 (WS off-session) + 255 (REST), not_tradable 228 |
| alpaca_benzinga | rest | source_metadata | 6 | 1 | 6 | 14:16:04–14:17:12 | 93,3 min | (incl.) | (incl.) | — |
| gdelt_gkg | — | org_lookup | 13 | 13 | 9 | 14:51:46–19:55:08 | 4,3 / 11,8 min | 2.271 | 3 | 2.255 no_ticker |

* Nessun timestamp futuro (`published_at > created_at`: 0). Nessun `discarded_reason` sulle righe scorate. Nessun corpo mancante.
* **I corpi GDELT coincidono col titolo** (13/13 `body_full = title`). Nessuno ha però prodotto un ordine.
* Entità HTML (`&amp;`, `&#39;`…) nel corpo: 70/215 righe (64 WS + 6 REST). Il fix `edfd73e0` non era deployato: vedi DAY-015.
* Fan-out: 123 articoli producono 215 righe. **34 articoli multi-ticker ne generano 126 (58,6%)**, massimo 13 (DAY-006).
* Stale: 211 alle 13:33 (coda notturna WS) e 255 REST in seduta, età mediana 4,3 h (backfill di articoli già vecchi).
* `duplicate_id`: 5.455 REST + 1.109 WS in seduta + 727 WS fuori seduta. Il contatore `duplicates` supera `fetched` (DAY-023).
* Copertura: 60 simboli con almeno una riga. `no_news_backstop`: **36** simboli di watchlist a zero righe, di cui 2 mover (CMCSA, DELL).
* Buchi temporali: nessuno di trasporto. Il vuoto 18:35–19:12 è a coda vuota (`no_items_in_queue`, 2 righe `news_log` nella finestra).

### 4.2 Per ticker (top 16 per segnali)

| Ticker | Segnali | Ensemble | Max | Min | Ultimo |
|---|---|---|---|---|---|
| SPY | 21 | 11 | +0,412 | −0,210 | −0,180 |
| NVDA | 18 | 8 | +0,496 | −0,240 | +0,072 |
| CRM | 14 | 9 | +0,423 | −0,219 | −0,219 |
| AMZN | 13 | 8 | +0,271 | −0,080 | +0,060 |
| SPCX | 9 | 5 | +0,355 | −0,005 | +0,141 |
| INTC | 9 | 8 | +0,285 | −0,240 | 0,000 |
| MSFT | 7 | 2 | +0,150 | −0,240 | +0,040 |
| MU | 6 | 6 | +0,493 | 0,000 | +0,258 |
| GOOGL | 6 | 3 | +0,260 | −0,100 | +0,260 |
| TSLA | 6 | 5 | +0,066 | −0,243 | −0,243 |
| NOK | 6 | 3 | +0,420 | 0,000 | +0,192 |
| AAPL | 6 | 4 | +0,420 | −0,040 | +0,021 |
| ORCL | 5 | 4 | +0,220 | −0,149 | +0,021 |
| QQQ | 5 | 2 | +0,438 | −0,201 | −0,040 |
| META | 4 | 2 | +0,450 | −0,060 | +0,040 |
| AMD | 4 | 3 | +0,257 | −0,080 | 0,000 |

### 4.3 Top news per impatto sul segnale

| Segnale | Ticker | Score | Contenuto (dal reasoning) | Esito |
|---|---|---|---|---|
| 11425 | MU | +0,493 | avvertimento del CEO Intel sui prezzi delle memorie (glm: `already_priced_in`) | BUY 15:52, mark −1,97 $ |
| 11423 | META | +0,450 | BofA reitera Buy, PT 810 $ | BUY 15:37 → SELL 19:52, +11,74 $ |
| 11413 | SPCX | +0,355 | lancio USSF-259 (entrambi: `already_priced_in`) | BUY 15:07 → SELL 17:37, +5,69 $ |
| 11457 | NVO | +0,349 | parere EMA su FREHEMGO | BUY 16:52, mark +2,68 $ (+6,47 net alla chiusura del 18/09) |
| 11429 | BA | +0,274 (×1,2) | Lufthansa esercita 20 opzioni 737 MAX 10, «surprise factor limited» | BUY 16:07, mark −16,05 $ (−21,22 net il 18/09) |
| 11465 | SPCX | +0,042 | stesso tema, gpt-oss `ambiguous_entity` | SELL SPCX |
| — | ORCL/TMUS/RDDT | +0,22/+0,12/+0,20 | articolo macro «Nasdaq 100 Rallies…» (fan-out) | nessun ordine (ALPHA_MISS §8, F-012) |

**Confidenza dell'analisi ingest: alta** (letture dirette da `news_log`, `news_queue_drops`, `ingestion_stats_daily`).

---

## 5. Performance modelli LLM

| Modello | Risposte | `eligible`=true | Sotto floor 0,40 | Conf. mediana | Polarity media | Pos/Neg/Zero | Score medio (p×c) | Errori di trasporto in seduta |
|---|---|---|---|---|---|---|---|---|
| glm-5.2:cloud | 215 | 74 | 127 (59,1%) | 0,30 | +0,123 | 140/48/27 | +0,068 | 0 |
| gpt-oss:20b-cloud | 204 | 74 | 63 (30,9%) | 0,55 | +0,102 | 123/44/37 | +0,067 | **11 timeout** (13–14h) |

| Tipo segnale | Righe | % | Score medio | Min | Max | Sopra gate \|0,30\| | `ensemble_std`=0 |
|---|---|---|---|---|---|---|---|
| ensemble glm-5.2+gpt-oss | 129 | 60,0% | +0,100 | −0,325 | +0,496 | 17 | 31 (tutti a polarity identica) |
| single gpt-oss (`fallback_used`) | 67 | 31,2% | +0,024 | −0,240 | +0,420 | 4 | 67 |
| single glm-5.2 (`fallback_used`) | 19 | 8,8% | +0,055 | −0,120 | +0,420 | 2 | 19 |
| FinBERT (reale) | **0** | 0% | — | — | — | — | — |

* **Latenza**: nessuna telemetria per chiamata (F-086). Dai task: 77 cicli sentiment attivi, 215 item, durata mediana del task
  21,0 s, **per-item mediana 10,5 s**, massimo 193,7 s, nessun task oltre 300 s. Pub→segnale WS: mediana 5,2 min.
* **Errori**: 11 timeout gpt-oss in seduta (13:35–14:59). Fuori seduta (shadow): 13 timeout gpt-oss, 8 glm, un 503 gpt-oss
  alle 06:18 e un `invalid` glm alle 11:15. Nessun parse-fail in seduta.
* **Disaccordo**: su 204 segnali con due risposte, 24 hanno spread di polarity ≥ 0,30 e 10 hanno **segni opposti**. Esempio
  SPCX 11465: glm +0,25 contro gpt −0,3 (`ambiguous_entity`), std 0,389. Il segnale +0,042 ha chiuso la posizione (DAY-003).
* **Dominanza di un modello**: 86 segnali (40%) a modello singolo. Esclusi dal ranking BUY (28 righe `SKIP_FALLBACK`, 210 intenti).
  Restano però usabili come segnale d'uscita. META è uscita dopo che l'ultimo segnale ensemble è invecchiato ed è stato
  seguito solo da single gpt-oss.
* **`eligible`**: 55 dei 129 segnali ensemble hanno **zero** risposte `eligible=true` pur combinando due modelli (DAY-016, F-010).
* **Fallback FinBERT reali: 0.** `finbert_fallback_events` ha righe dal 14/09, quindi lo zero è misurato e non vuol dire «non
  misurato». L'esito del task dichiara invece `finbert_fallbacks: 86` (DAY-004).
* **Offline/background**: confermato. I modelli girano solo in `worker-inference` (coda `inference`) e il ciclo portfolio legge
  `sentiment_signals` dal DB. Nessuna chiamata LLM nel percorso ordini.
* **Validazione**: l'output passa da estrazione JSON (1 `invalid` scartato), floor di confidenza e filtro single-model per il
  BUY. I `risk_flags` (`already_priced_in` su SPCX/MU/BA/NVO) **non fanno da gate**, per disegno (QX-01).

---

## 6. Segnali finali per ticker (quelli arrivati a gate, ranking o ordine)

| Ticker | Segnale | Ora | Score grezzo | Ranking | Tipo | Destino |
|---|---|---|---|---|---|---|
| CRM | 11314 | 13:34:43 | +0,423 | — | ensemble | **mai valutato** (0,000 alle 14:03, primo ciclo 14:07) |
| NVDA | 11347 | 14:00:53 | +0,496 | — | ensemble | **mai valutato** (sovrascritto 14:02:09) |
| MRVL | 11348 | 14:01:03 | +0,309 | — | ensemble | SKIP_PYRAMIDING (S4 a libro) |
| NOK | 11353 | 14:02:40 | +0,420 | — | single glm | SKIP_FALLBACK |
| XOM | — | 14:07–16:07 | +0,42 | — | — | SKIP_PYRAMIDING ×9 (S1 a libro) |
| SHEL | — | 14:07–19:52 | +0,296 | — | — | SKIP_PYRAMIDING ×14, RANK_OUTSIDE_TOP_N ×10 |
| SPCX | 11413 | 14:59:13 | +0,355 | 0,355 | ensemble | **BUY 15:07** (rank 3) |
| META | 11423 | 15:36:10 | +0,450 | 0,540 | ensemble | **BUY 15:37** (rank 1) |
| MU | 11425 | 15:38:28 | +0,493 | 0,592 | ensemble | **BUY 15:52** (rank 1) |
| BA | 11429 | 15:52:51 | **+0,274** | **0,3285** | ensemble | **BUY 16:07** (rank 5) |
| NVO | 11457 | 16:45:23 | +0,349 | 0,419 | ensemble | **BUY 16:52** (rank 4) |
| AAPL | — | 16:52–17:52 | +0,42 | — | — | SKIP_PYRAMIDING ×3 (S1) |
| SPCX | 11465 | 17:14:14 | +0,042 | — | ensemble | **SELL 17:37** |
| QQQ | — | 17:30:22 | +0,438 | — | ensemble | SKIP_PYRAMIDING (S4 a libro) |
| XLE | — | 17:35:47 | −0,325 | — | ensemble | posizione S4 **tenuta** (SKIP_THRESHOLD) |

Disposizioni S4 (`s4_intent_events`): 1.973 candidati, SKIP_ENTRY_GATE 780, SKIP_ENTRY_FRESHNESS 742, SKIP_FALLBACK 210,
SKIP_STALE 120, **SKIP_PYRAMIDING 75** (contro **15** righe `execution_decisions`), SKIP_IDEMPOTENCY 22, RANK_OUTSIDE_TOP_N 19,
SUBMITTED 5. `execution_decisions`: OBSERVE_LATE_ENTRY 1.666, SKIP_THRESHOLD 780, SHADOW_LATE_ENTRY 307, SKIP_FALLBACK 28,
SKIP_PYRAMIDING 15, BUY 5, SKIP_STALE 2, SELL 2.

---

## 7. Ordini generati/eseguiti

| Decisione | Strategia | Ticker | Azione | Qty | Prezzo atteso (snapshot intento) | Fill | Stato | Broker | Rationale | Segnale | Risk check | Anomalie |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 15:07:01 (30092) | S4 | SPCX | BUY | 9,3537 | 154,155 | 154,19 | filled 15:07:06 | Alpaca paper | +0,355, peso 2,0%, regime 0,7 | 11413 | gate, rank 3, P0-05, idempotenza | `decision_price` NULL a DB (F-015) |
| 15:22:05 | S4 stop | SPCX | SELL stop | 9 | — | — | canceled | Alpaca paper | stop protettivo | — | — | 96,2%, un ciclo dopo (F-022) |
| 15:37:01 (30323) | S4 | META | BUY | 2,1248 | 675,42 | 675,43 | filled 15:37:05 | Alpaca paper | +0,450 (ranking 0,54) | 11423 | gate, rank 1 | — |
| 15:52:05 | S4 stop | META | SELL stop | 2 | — | — | canceled | Alpaca paper | stop | — | — | 94,1% |
| 15:52:01 (30435) | S4 | MU | BUY | 1,4634 | 978,67 | 978,848 | filled 15:52:05 | Alpaca paper | +0,493 (ranking 0,592) | 11425 | gate, rank 1 | `shadow_late_entry`; nel target S1 congelato (DAY-001) |
| 15:52:05 | S4 stop | MU | SELL stop | 1 | — | — | new | Alpaca paper | stop | — | — | **68,3%** (F-022) |
| 16:07:01 (30551) | S4 | BA | BUY | 7,1955 | 199,21 | 199,23 | filled 16:07:07 | Alpaca paper | +0,274 × velocità = 0,3285 | 11429 | gate (su boost), rank 5 | punteggio persistito < gate (DAY-002) |
| 16:22:05 | S4 stop | BA | SELL stop | 7 | — | — | canceled | Alpaca paper | stop | — | — | 97,3% |
| 16:52:01 (30897) | S4 | NVO | BUY | 33,2014 | 43,10 | 43,1093 | filled 16:52:09 | Alpaca paper | +0,349 (ranking 0,419) | 11457 | gate, rank 4 | percentile 0,97 (F-030) |
| 17:07:06 | S4 stop | NVO | SELL stop | 33 | — | — | canceled | Alpaca paper | stop | — | — | 99,4% |
| 17:37:01 (31249) | S4 | SPCX | SELL | 9,3537 | — | 154,96 | filled 17:37:07 | Alpaca paper | `below_entry_gate` +0,042, hold 2,5 h | NULL | stop cancellato prima | SELL con sentiment positivo (F-013); `signal_id` NULL (F-011) |
| 19:52:01 (32317) | S4 | META | SELL | 2,1248 | — | 681,09 | filled 19:52:22 | Alpaca paper | `fallback_filtered`: +0,45 invecchiato, ultimo single +0,04 | NULL | — | testo «FinBERT fallback» per un single gpt-oss (DAY-004) |

Nessun ordine S1: il gate di ribilanciamento è chiuso (ultimo 2026-09-01, «holding 42 position(s)»). `orders_count` 2–6 per
ciclo contro 0–1 inviati (DAY-011).

---

## 8. PnL / rendimento

Fonti: `trades`; `docs/evidence/dossier/2026-09-17.json` (`snapshot_apertura` open→close, `ingressi.mtm_eod`, prezzi Alpaca SIP);
`docs/evidence/economic_pnl.json` (close→close); barre al minuto Alpaca (sola lettura) per i controfattuali.

| Voce | Ticker | Qty | Da → A | $ | Tipo |
|---|---|---|---|---|---|
| Realizzato (aperta oggi) | SPCX #1012 | 9,3537 | 154,19 → 154,96 | **+5,69** net (gross 7,20, costi 1,52) | realizzato |
| Realizzato (aperta oggi) | META #1013 | 2,1248 | 675,43 → 681,09 | **+11,74** net (gross 12,03, costi 0,29) | realizzato |
| Aperta oggi | MU #1014 | 1,4634 | 978,848 → 977,50 | −1,97 | non realizzato |
| Aperta oggi | BA #1015 | 7,1955 | 199,23 → 197,0 | −16,05 | non realizzato |
| Aperta oggi | NVO #1016 | 33,2014 | 43,1093 → 43,19 | +2,68 | non realizzato |
| Preesistente S4 | INTC #1007 | ~14,53 | 104,70 → 108,80 | +59,55 | non realizzato (open→close) |
| Preesistente S4 | PANW #1001 | ~3,88 | 365,465 → 375,06 | +37,19 | idem |
| Preesistente S4 | XLE #922 | ~22,0 | 63,50 → 64,48 | +21,57 | idem |
| Preesistente S4 | CSCO #830 | ~17,1 | 109,72 → 110,24 | +8,91 | idem |
| Preesistente S4 | MRVL #1005 | ~6,37 | 240,07 → 240,76 | +4,40 | idem |
| Preesistente S4 | QQQ #1011 | ~2,07 | 715,95 → 716,92 | +2,01 | idem |
| Preesistente S4 | WDC #373 | 0,3347 | 427,28 → 423,87 | ≈0 (nozionale d'apertura 0 nel dossier) | idem |
| **S4 intraday** | | | | **≈ +135,7** (open→close; +17,43 realizzato) | |
| **S4 economico** | | | close→close | **+283,22** | `economic_pnl.json` |
| S1 (35 posizioni) | | | open→close | +48,58 · economico close→close **+304,56** | |
| **Book (broker)** | | | 108.907,77 → 109.457,37 | **+549,60 (+0,50%)** (snapshot 20:00); economico +587,77 | equity |

* Benchmark: SPY +1,13%, QQQ +1,73%. Esposizione lorda del book 0,31–0,37: il +0,50% è coerente con un beta ridotto e non
  va letto come alpha.
* Cumulato economico al 17/09 (giorno 30/40): S4 **−696,33 $**, S1 +664,95 $, BOOK −66,22 $.
* Il segno di S4 dipende dalle posizioni preesistenti, **6 delle quali non possono uscire per regola S4** (DAY-001).
* Slippage: `decision_price` è NULL in `execution_decisions` ma presente nello snapshot dell'intento. Proxy decisione→fill
  sui BUY: SPCX +2,3 bp, META +0,1, MU +1,8, BA +1,0, NVO +2,2. SELL: non misurabile. Commissioni 0 (Alpaca). Costo
  modellato 4,14 $ in `cost_usd`.
* `/api/trades` riporta la SELL META con `entry_price` 712,616 e `gross_pnl` **−66,99** (entry di un trade META precedente).
  Il ledger dice +12,03 (DAY-014).

---

## 9. Correttezza buy/sell

| Controllo | Esito | Nota |
|---|---|---|
| BUY solo quando consentito | ✅ | 5 BUY, ensemble, ranking ≥ 0,30 (BA solo col boost di velocità, per regola: DAY-002), top-N, P0-05, idempotenza |
| SELL/exit corretti | ⚠️ | SPCX e META chiuse secondo la regola dichiarata. **6 posizioni S4 nel target S1 non escono** (DAY-001) |
| Stop-loss | ⚠️ | nessuno scattato. Coperture 94–99%, MU **68,3%**. AMAT −29,6% e WDC −22,9% senza stop (sub-one-share) |
| Signal flip | ⚠️ | XLE −0,325, QQQ −0,201 su posizioni S4: nessuna uscita (DAY-001) |
| Max holding days | ⚠️ | CSCO dal 08-25, XLE dal 08-31: tenute dal combiner (DAY-001) |
| Rebalance band | ⚠️ | nessuna banda: SPCX venduta a +0,042 dopo un ingresso a +0,355 (DAY-003) |
| Ordini duplicati | ✅ | nessuno. 22 `SKIP_IDEMPOTENCY` / `SIGNAL_DUPLICATE_SKIP` |
| Ordini contrari ravvicinati | ✅ | nessun ri-ingresso dopo le SELL |
| Ticker non consentiti | ✅ | tutti in watchlist |
| Fuori orario | ✅ | ordini fra 15:07 e 19:52 |
| Dati stale | ✅ | 2 SKIP_STALE a DB (120 intenti), 742 SKIP_ENTRY_FRESHNESS |
| LLM output non valido | ✅ | nessun parse-fail in seduta. Single-model esclusi dal BUY |
| Circuit breaker | ✅ | loss-feedback S4 `triggered: True` ma ratchet congelato dal charter (0,30→0,30), coerente col freeze |
| Strategia disabilitata | ✅ | S1+S4 attive, `execution.engine=portfolio` |
| Paper/live | ✅ | paper verificato (snapshot) |
| Idempotenza retry Celery | ✅ | nessun doppio invio. I restart delle 06:20/08:20/20:20 sono fuori seduta |
| Riconciliazione | ⚠️ | 44 `fully_held` + 1 `partially_wound_down_coheld` con «anomalies: 0» (DAY-026) |

Pattern specifici:

* Roundtrip < 30 min: **nessuno** (SPCX 2,5 h, META 4,25 h).
* Pyramiding > 3 BUY: **nessuno**.
* SELL con sentiment positivo: **sì, 2**. SPCX a +0,042 (DAY-003). META con l'ultimo ensemble a +0,45 invecchiato e l'ultimo
  single a +0,04.
* `fallback_used=True` su tutti i simboli: **no**.
* NO-ORDER: **no** (7 decisioni d'ordine, 7 ordini).
* Score < 0,05 che genera ordine: **SELL SPCX su +0,042** (uscita per regola).
* Ordini identici nello stesso minuto: **no**.

`exit_mechanism`: le due righe del 17/09 (`below_entry_gate`, `fallback_filtered`) hanno il formato post-#184 (disposizione
nel testo del motivo). Sono quindi osservate, non stime per età. `trades.exit_reason` riporta `portfolio_sell` per entrambe:
è un vocabolario diverso, non un conflitto.

---

## 10. Anomalie trovate

### [DAY-001] Sei posizioni S4 nel target congelato di S1 non escono, compresa MU comprata oggi: F-089 era attivo già il 17/09

* Tipo: Bug
* Area: Signal / Orders / Risk
* Evidenza:
  * file/log/tabella: Redis `strategy:rebalance_state:S1` (`last_rebalance` 2026-09-01T14:07Z); `execution_decisions`; `sentiment_signals`; `trades`; barre Alpaca al minuto
  * timestamp: tutta la seduta
  * snippet/query:
    ```
    target S1 congelato: INTC 0,0145 PANW 0,0211 XLE 0,0236 CSCO 0,0236 MRVL 0,0120 QQQ 0,0236 WDC 0,0116 MU 0,0118
    segnali freschi sotto gate su posizioni S4: INTC +0,219 (14:05), PANW -0,008 (13:47), XLE 0,000 (14:08) e -0,325 (17:35),
      QQQ -0,201 (14:14), MRVL +0,218 (14:11), MU 0,036 (15:59) / 0,000 (17:36, hold minimo scaduto 17:22)
    execution_decisions: INTC 24, XLE 24, PANW 15, QQQ 13, MRVL 23, MU 11 righe SKIP_THRESHOLD; nessuna SELL
    stessa regola, simbolo fuori dal target S1: SPCX 17:37 SELL below_entry_gate su +0,042
    ```
* Descrizione: è lo stesso meccanismo registrato il 22/09 come F-089. Il combiner somma il peso S1 congelato e la quota S4
  portata a zero non viene venduta. MU mostra il caso limite: è stata comprata da S4 il 17/09 su un simbolo già nel target S1,
  quindi la sua uscita S4 è disarmata **dal primo minuto**.
* Impatto: controfattuale corto, stessa convenzione del 22/09 (vendita al secondo ciclo dopo il primo segnale fresco sotto
  gate, contro la chiusura):
  * INTC 14:22 @109,179: −5,51
  * PANW 14:22 @378,475: −13,24
  * XLE 14:37 @63,87: +13,42
  * QQQ 14:37 @716,621: +0,62
  * MRVL 14:37 @241,673: −5,82
  * MU 17:52 @974,035: +5,07

  Tenere ha reso **−5,46 $** rispetto alla regola, quindi il costo attribuito è **+5,46 $**. La P&L S4 è contaminata almeno
  dal 17/09, non dal 22/09.
* Severità: High · Confidenza: High sul meccanismo, Medium sul costo (isteresi approssimata)
* Azione consigliata: il ticket di correttezza di F-089 è già aperto. La dichiarazione nel charter deve partire almeno dal
  17/09 (ingresso MU) e coprire tutte le posizioni S4 su simboli del target S1.
* Test/monitor consigliato: allerta a ogni BUY S4 su un simbolo presente nel target S1 congelato.
* → ledger **F-089** (primo avvistamento anticipato al 2026-09-17)

### [DAY-002] BUY BA con `signal_score` 0,274 persistito sotto gate: il gate usa il punteggio moltiplicato, che a DB non c'è

* Tipo: Bug (osservabilità)
* Area: Signal / Data
* Evidenza:
  * file/log/tabella: `execution_decisions` 30551; `s4_intent_events` (SUBMITTED 16:07); `sentiment_signals` 11429
  * timestamp: 16:07:01
  * snippet/query: `signal_score=0.274`, `velocity_multiplier=NULL`; intento `snapshot.score=0.27375`, `ranking_score=0.3285`. Stesso schema su META 0,45→0,54, MU 0,493→0,592, NVO 0,349→0,419
* Descrizione: la decisione rispetta la regola (0,3285 ≥ 0,30), ma chi legge `execution_decisions` o `trades` vede un BUY sotto gate.
* Impatto: BA #1015 ha chiuso a −21,22 $ il 18/09. La perdita non è attribuibile al difetto, perché il BUY era conforme. Costo null.
* Severità: Medium · Confidenza: High
* Azione consigliata: PR #624 (#550), già aperta. Nessuna nuova azione.
* Test/monitor consigliato: invariante giornaliero «BUY con `signal_score` < gate senza `velocity_multiplier`» = 0.
* → ledger **F-073**

### [DAY-003] SPCX venduta a +0,042 due ore e mezza dopo l'ingresso a +0,355, su un segnale in disaccordo di segno

* Tipo: Anomalia · Area: Orders / Signal
* Evidenza: `execution_decisions` 31249; `sentiment_signals` 11465 (glm +0,25/0,45 `already_priced_in`, gpt −0,3/0,4 `ambiguous_entity`, std 0,389); `trades` 1012
* Descrizione: nessuna banda fra gate d'ingresso e uscita. Un segnale ad alta varianza e quasi nullo chiude la posizione.
* Impatto: tenendo fino alla chiusura (154,79) si avrebbe avuto −1,59 $ rispetto alla vendita a 154,96. **Costo −1,59 $** (la vendita ha reso).
* Severità: Low · Confidenza: High
* → ledger **F-013**

### [DAY-004] 86 «finbert_fallbacks» dichiarati, 0 reali; l'uscita META chiama «FinBERT fallback» un single gpt-oss

* Tipo: Bug (osservabilità) · Area: LLM / Data
* Evidenza: somma degli esiti `run_sentiment_worker` = `finbert_fallbacks: 86`; `finbert_fallback_events` del 17/09: **0 righe**; `sentiment_signals`: 67 single gpt-oss + 19 single glm; `execution_decisions` 32317: «[fallback_filtered] S4 signal excluded from the ranking as FinBERT fallback, #108 (… generated 15:36 UTC, score=+0.450)»
* Descrizione: il contatore del task e il testo del motivo d'uscita confondono i segnali a modello singolo con FinBERT. Il
  testo META cita inoltre come «fallback» il segnale ensemble 11423, che era la causa dell'età e non del filtro.
* Impatto: il tasso di fallback letto dai log è 40% invece di 0%. Costo null.
* Severità: Low · Confidenza: High
* → ledger **F-078**

### [DAY-005] Ingressi MU e NVO a movimento già consumato

* Tipo: Anomalia · Area: Signal
* Evidenza: intenti SUBMITTED: MU `session_range_percentile` 0,772, `shadow_late_entry=true`, dossier `quota_movimento_precedente_al_segnale` 1,059; NVO percentile **0,973**, `shadow_late_entry=true`
* Impatto: MU mark −1,97 $, NVO +2,68 $. Il costo del giorno è già registrato in F-030 da ALPHA_MISS_REPORT_2026-09-17 §8
  (80,74 $). Qui null per non contarlo due volte.
* Severità: Low · Confidenza: High
* → ledger **F-030**

### [DAY-006] Fan-out: 58,6% delle righe scorate viene da articoli multi-ticker

* Tipo: Rischio · Area: News
* Evidenza: `news_log.content_hash`: 123 articoli → 215 righe; 34 multi-ticker → 126 righe; massimo 13.
* Impatto: segnali di segno opposto al movimento su TMUS/RDDT e il miglior segnale ORCL da un pezzo macro (ALPHA_MISS §8).
  Costo null qui (già registrato in F-012 con l'occorrenza ALPHA_MISS).
* Severità: Medium · Confidenza: High
* → ledger **F-012**

### [DAY-007] Primo ciclo alle 14:07: CRM +0,423 delle 13:34 non ha mai visto un ciclo

* Tipo: Anomalia · Area: Ops / Orders
* Evidenza: `portfolio_cycles` 1538 (14:07:01); `mobile_events` `portfolio_cycle_late` 13:30→14:08; `sentiment_signals` 11314 (13:34:43, +0,423, ensemble) → 11354 (14:03:52, 0,000)
* Descrizione: le finestre beat in UTC fisso lasciano scoperti i primi 37 minuti in EDT. Con un ciclo alle 13:37, CRM (non a
  libro) sarebbe stata comprata.
* Impatto: congetturale, 2.200 $: ingresso 13:37 @243,25, chiusura 243,03 → **−1,99 $** (il buco ha evitato una piccola perdita).
* Severità: Medium · Confidenza: Medium
* → ledger **F-021**

### [DAY-008] NVDA +0,496 sovrascritto dopo 76 secondi da +0,013

* Tipo: Anomalia · Area: Signal
* Evidenza: `sentiment_signals` 11347 (14:00:53, +0,496, ensemble) → 11351 (14:02:09, +0,013); ciclo 14:07 `SKIP_THRESHOLD` su 11351
* Descrizione: S4 legge solo l'ultimo segnale per simbolo. Un segnale forte sparisce prima di qualunque ciclo.
* Impatto: congetturale, 2.200 $: ingresso 14:07 @218,715, chiusura 219,37 → **+6,59 $** non catturati.
* Severità: Low · Confidenza: Medium
* → ledger **F-023**

### [DAY-009] P0-05 blocca XOM +0,42 e AAPL +0,42 (a libro da S1) e traccia 15 blocchi su 75

* Tipo: Anomalia · Area: Orders / Data
* Evidenza: `s4_intent_events` SKIP_PYRAMIDING 75 (SHEL 14, QQQ 10, XLK 10, XOM 9, BA 9, META 8, MS 6, SPCX 4, AAPL 3, LLY 1, MRVL 1) contro 15 righe in `execution_decisions`
* Impatto: congetturale, 2.200 $: XOM 14:07 @161,81 → 163,26 (**+19,71 $**), AAPL 16:52 @335,569 → 337,09 (**+9,97 $**), totale
  **+29,68 $** non catturati. MRVL è escluso perché già registrato nell'occorrenza ALPHA_MISS.
* Severità: Medium · Confidenza: Medium
* → ledger **F-031**

### [DAY-010] Stop MU al 68,3% del nozionale; AMAT −29,6% e WDC −22,9% senza stop

* Tipo: Rischio · Area: Risk
* Evidenza: ordine `b202b816` (MU qty 1 su 1,4634); log «#161: AMAT unprotected at -29.6% … WDC unprotected at -22.9% (status sub_one_share)» ×24
* Impatto: nessuno stop scattato. Costo null.
* Severità: Medium · Confidenza: High
* → ledger **F-022**

### [DAY-011] `orders_count` 2–6 per ciclo contro 0–1 ordini inviati

* Tipo: Bug (osservabilità) · Area: Ops
* Evidenza: `portfolio_cycles` 1538–1561. `final_orders` include BUY su META/NVO/BA/QQQ/XLK già a libro, bloccati a valle.
* Impatto: telemetria del ciclo non interpretabile. Costo null. Severità: Low · Confidenza: High
* → ledger **F-014**

### [DAY-012] `decision_price` NULL su tutte e 7 le decisioni d'ordine, pur presente nello snapshot dell'intento

* Tipo: Bug (osservabilità) · Area: Data
* Evidenza: `execution_decisions` 30092/30323/30435/30551/30897/31249/32317 `decision_price` NULL; `s4_intent_events.snapshot.late_entry.decision_price` 154,155 / 675,42 / 978,67 / 199,21 / 43,10
* Impatto: slippage dei BUY ricostruibile solo dal ledger degli intenti, quello delle SELL per nulla. Costo null.
* Severità: Low · Confidenza: High
* → ledger **F-015**

### [DAY-013] Le 2 SELL hanno `signal_id` NULL

* Tipo: Bug (osservabilità) · Area: Data
* Evidenza: `execution_decisions` 31249, 32317. Il segnale causante è solo nel testo del motivo.
* Costo null. Severità: Low · Confidenza: High
* → ledger **F-011**

### [DAY-014] `/api/trades` mostra la SELL META a −66,99 $ invece di +12,03 $

* Tipo: Bug · Area: Frontend / Data
* Evidenza: `GET /api/trades`: `a507446f` META `entry_price` 712,616, `gross_pnl` −66,9863; `trades` 1013: 675,43 → 681,09, gross +12,03. Le righe BUY SPCX/META risultano ancora `open`.
* Impatto: chi legge la UI/API vede una perdita inesistente. Costo null.
* Severità: Medium · Confidenza: High
* → ledger **F-084**

### [DAY-015] Entità HTML nel testo mandato ai modelli: 70/215 righe, fix non ancora deployato

* Tipo: Bug · Area: News / LLM
* Evidenza: `news_log.body_full ~ '&(amp|#39|quot|lt|gt);'`: 70/215 righe (64 WS, 6 REST). Il fix `edfd73e0` è stato deployato il 22/09.
* Descrizione: il criterio del charter è il testo che raggiunge il modello. Il 17/09 non ci sono righe `finbert_fallback_events`
  per verificarlo direttamente, quindi l'occorrenza è **attribuita al codice pre-fix**, non misurata.
* Costo null. Severità: Low · Confidenza: Medium
* → ledger **F-076**

### [DAY-016] 55 dei 129 segnali ensemble hanno zero risposte `eligible=true`

* Tipo: Bug (osservabilità) · Area: LLM / Data
* Evidenza: join `sentiment_signals` (model_id `ensemble:*`) × `llm_responses`: 35 con polarity diverse e 20 identiche, tutte con `eligible=false` su entrambe le risposte
* Descrizione: il retry a floor 0 non è propagato al flag, per cui `eligible` non descrive i contributori reali.
* Costo null. Severità: Low · Confidenza: High
* → ledger **F-010**

### [DAY-017] DECAY CRITICAL con lo stesso IC −0,054 su S1, S2 e S4

* Tipo: Bug · Area: Risk / Ops
* Evidenza: log worker 21:00:00: «[S1] IC dropped 255% from 0.035 to -0.054», «[S2] … 0.042 to -0.054», «[S4] … 0.028 to -0.054»; drawdown 13,4% identico su S1 e S2 (S2 non attiva)
* Costo null. Severità: Medium · Confidenza: High
* → ledger **F-004**

### [DAY-018] Gli 11 DECAY CRITICAL restano nel log

* Tipo: Bug · Area: Ops
* Evidenza: `mobile_events` del 17/09 senza righe decay; nessun invio Telegram alle 21:00.
* Costo null. Severità: Medium · Confidenza: High
* → ledger **F-062**

### [DAY-019] Incidenti serali aperti e chiusi nello stesso secondo

* Tipo: Bug · Area: Ops
* Evidenza: `mobile_events` 22:50:00→22:50:01: `portfolio_cycle_session_grid`, `coverage:held_no_news_loss:PFE`, `…:SBUX`, tutti `recovered` in ~0,6 s
* Costo null. Severità: Medium · Confidenza: High
* → ledger **F-058**

### [DAY-020] Alert Telegram rifiutati (400)

* Tipo: Anomalia · Area: Ops
* Evidenza: log worker 14:00:00 (trigger loss-feedback S4) e 14:22:06 ×2 (AMAT/WDC scoperte): «TelegramNotifier: Failed to send alert: Client error '400 Bad Request'»
* Costo null. Severità: Medium · Confidenza: High
* → ledger **F-005**

### [DAY-021] Bot token Telegram e api_key FRED in chiaro nei log

* Tipo: Rischio · Area: Ops
* Evidenza: 17.270 righe con `api.telegram.org/bot…` in `worker-inference-2026-09-17.log`, 7 in `worker-2026-09-17.log`; URL FRED con `api_key=` alle 07:00:05
* Costo null. Severità: Medium · Confidenza: High
* → ledger **F-018**

### [DAY-022] Fetch benchmark SPY fallito 84 volte senza alert

* Tipo: Anomalia · Area: Data
* Evidenza: log worker, «SPY benchmark fetch failed: subscription does not permit querying recent SIP data» ×84
* Costo null. Severità: Low · Confidenza: High
* → ledger **F-016**

### [DAY-023] `duplicates` 7.291 contro `fetched` 1.559 per alpaca_benzinga

* Tipo: Anomalia · Area: Data
* Evidenza: `ingestion_stats_daily` 2026-09-17
* Costo null. Severità: Low · Confidenza: High
* → ledger **F-007**

### [DAY-024] 36 simboli di watchlist a zero righe news, 2 dei quali mover

* Tipo: Osservazione · Area: News
* Evidenza: dossier `no_news_backstop.population` {zero_news 36, movers 2 (CMCSA −3,46%, DELL +4,46%)}
* Costo null. Severità: Low · Confidenza: High
* → ledger **F-001**

### [DAY-025] Coda notturna WS drenata all'apertura: 211 stale, 82 not_tradable, 727 duplicati fuori seduta

* Tipo: Anomalia · Area: News / Ops
* Evidenza: `news_queue_drops` con `enqueued_off_session=true`; 106 dispatch `market_closed` nella notte
* Costo null. Severità: Low · Confidenza: High
* → ledger **F-069**

### [DAY-026] Il riconciliatore dichiara «anomalies: 0» con una posizione `partially_wound_down_coheld`

* Tipo: Bug · Area: Broker / Data
* Evidenza: log 21:35:02 `{'fully_held': 44, 'partially_wound_down_coheld': 1}, 'anomalies': 0`. Il simbolo non è nel log.
  È verosimilmente UNH, lo scarto noto di F-048, ma qui non è verificato.
* Costo null. Severità: Low · Confidenza: Medium
* → ledger **F-048**

---

## 11. False positive o aree risultate corrette

* **Timezone**: UTC esplicito nel codice. Nessun problema di DST oltre a F-021 (già noto).
* **Paper/live**: paper verificato. Nessun ordine live.
* **Ollama**: su per tutta la seduta, 11 timeout concentrati 13:35–14:59. Nessun fallback FinBERT reale e nessuna fase «tutti fallback».
* **`ensemble_std`=0 sui segnali ensemble** (31): tutti a polarity identica fra i due modelli. **F-054 non si presenta oggi.**
* **Vuoto segnali 18:35–19:12** e alert `signal_stale`: coda vuota, non un guasto.
* **Restart dei worker** (06:20/08:20/20:20): tutti fuori seduta. Messaggi non confermati ripristinati. Nessun ciclo perso.
* **Regime**: FRED ok alle 07:00 e alle 13:30 (a differenza del 22/09). Sideways ×0,7 applicato a tutti i BUY.
* **Loss-feedback S4**: trigger vero, ratchet congelato. È il comportamento atteso durante il freeze.
* **Idempotenza**: 22 SKIP_IDEMPOTENCY, nessun doppio ordine.
* **Nessun ordine senza segnale, fuori orario, duplicato o su ticker fuori watchlist.**
* **SELL META `fallback_filtered`**: l'uscita per età del segnale (4,3 h > 4 h) è conforme. Solo l'etichetta è sbagliata (DAY-004).

## 12. Dati mancanti o non accessibili

* Latenza per chiamata LLM e uptime Ollama: non persistiti (F-086). Stimati dai log dei task.
* Testo effettivo ricevuto dai modelli: verificabile solo sui fallback FinBERT (0 il 17/09). DAY-015 resta attribuito al codice.
* `decision_price` delle SELL: assente (DAY-012), quindi slippage d'uscita non misurabile.
* Simbolo della posizione `partially_wound_down_coheld`: non nel log. Servirebbe l'output completo di `run_reconcile_positions`.
* `economic_pnl.json` nella tree di lavoro ha `data` 2026-09-17. Il report ALPHA_MISS citava una versione as_of 09-16: i
  cumulati qui sono quelli al 17/09.

## 13. Raccomandazioni immediate

1. **Charter (F-089)**: la dichiarazione sulle posizioni S4 nel target S1 deve partire almeno dal 2026-09-17 (ingresso MU) e
   non dal 22/09. È una correzione di strumento, non una taratura.
2. Nessuna taratura: gate, isteresi, stop e freschezza restano congelati fino al 28/09.
3. Prima della sintesi del giorno 40, marcare nel report S4 quali posizioni erano gestibili dalla regola S4.

## 14. Test o monitor da aggiungere

* Invariante: BUY S4 su un simbolo nel target S1 congelato → allerta (DAY-001).
* Invariante: `execution_decisions` BUY con `signal_score` < gate e `velocity_multiplier` NULL = 0 (DAY-002).
* Contatore giornaliero `finbert_fallback_events` accanto a `finbert_fallbacks` del task, con allerta se divergono (DAY-004).
* Test di contratto `/api/trades`: una SELL eredita l'entry del proprio trade (DAY-014).
* Monitor «segnale ≥ gate sovrascritto prima del primo ciclo utile» (DAY-007/008).

## 15. Ticket tecnici suggeriti (solo correttezza)

* F-089: già tracciato dal 22/09. Aggiungere al ticket il caso MU (BUY S4 su simbolo già nel target S1 = uscita disarmata dall'ingresso).
* F-073 / #550: PR #624 aperta. Nessun nuovo ticket.
* F-084: l'endpoint `/api/trades` deve leggere il ledger `trades`, non ricostruire da ordini broker. Nessun nuovo ticket se già aperto.

## 16. Stato sistema

| Voce | Valore |
|---|---|
| Ollama | **up** per tutta la seduta; 0 h di downtime; 11 timeout gpt-oss (13:35–14:59), 0 errori glm in seduta |
| Ollama fuori seduta | 1 × 503 gpt-oss (06:18), 1 × invalid JSON glm (11:15), 21 timeout (shadow) |
| FinBERT fallback rate | **0%** dei segnali (0/215) e delle decisioni. `finbert_fallback_events`: 0 righe (misurato) |
| Single-model | 86/215 segnali (40,0%); 28 decisioni SKIP_FALLBACK |
| Worker restart | 3 ricreazioni (06:20, 08:20, 20:20), tutte fuori seduta; 2 `WorkerLostError` (SIGTERM); 1 SIGKILL shadow 10:29 (TimeLimit 840 s) |
| Cicli portfolio | 24/24 (14:07–19:52); primo ciclo 37 min dopo l'apertura |
| Alert | `portfolio_cycle_late` CRITICAL 13:30–14:08; 3 invii Telegram falliti (400); DECAY CRITICAL solo log |
