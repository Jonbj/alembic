# Forensic Daily Report — 2026-09-24

Sessione forense autonoma, sola lettura (eseguita il 2026-10-01). Fuso operativo **UTC** (`src/workers/celery_app.py`,
`timezone="UTC"`, `enable_utc=True`): tutti i timestamp di questo report sono UTC. Seduta RTH 13:30–20:00 UTC (EDT).
Conto **paper** verificato, non assunto: `ALPACA_BASE_URL` punta a `paper-api.alpaca.markets` e
`portfolio_monitor_snapshots.broker_environment='paper'` su 87/87 istantanee della giornata. `execution.engine=portfolio`.

Periodo di **sola osservazione** (`docs/evidence/OBSERVATION_CHARTER.md`, scadenza 2026-09-28). Nessuna taratura
proposta. I ticket riguardano solo difetti di correttezza o di strumentazione.

Contesto: cinque ricreazioni di `worker`/`worker-inference`/`beat` (06:20, 08:20, 10:02, 12:20, 21:01), tutte fuori
seduta, dopo i merge del giorno (#657, #634, #658, #644, #640, #660, #645, #642, #639, #636, #662). Il charter registra
due interventi operatore del 24/09: backfill dei duplicati F-072 (#551) e 28 alias bare-stem su `ticker_lookup`
(#566). Per lo stesso giorno esiste già `docs/ALPHA_MISS_REPORT_2026-09-24.md`, che ha registrato con costo F-013
(1,04 $), F-023 (1,28 $) e F-059 (3,31 $). Qui quegli episodi sono agganciati con `costo_usd: null` per non contarli
due volte.

---

## 1. Executive summary

La pipeline ha girato end-to-end: 222 righe scorate (207 Benzinga WS + 15 GDELT) → 222 segnali → 24 cicli portfolio
(14:07–19:52) → 1 BUY e 4 SELL S4, tutti `filled` sul conto paper. Nessun ordine fuori orario, duplicato, senza
segnale o su dati stale. Ollama è rimasto su tutta la seduta, con un grappolo di timeout fra 14:00 e 14:35 che ha
prodotto 5 dei 7 fallback FinBERT reali (3,2% dei segnali). NAV 109.882,53 → 109.954,31 $ (**+71,78 $, +0,07%**)
contro SPY −0,08%. S4 chiude circa **+89,7 $** close-to-close, S1 circa −19 $. Il realizzato è +10,84 $ (META +31,38
e +18,26, NOW +1,69, BA −40,49).

Il guadagno S4 del giorno **non viene dalla regola S4**. INTC (+69,57 $), MU (+12,66 $) e le altre posizioni S4 dentro
il target congelato di S1 ricevono segnali freschi sotto gate e non escono, mentre META, NOW e BA (fuori dal target)
escono alla stessa regola. Alla regola dichiarata la S4 avrebbe venduto quelle posizioni fra 14:22 e 15:37, e il
giorno sarebbe stato circa **−3 $** invece di +89,7 $ (F-089, −93,13 $ attribuito). I pesi d'ensemble restano 0,5/0,5
(108/108 segnali riprodotti, F-088). `/api/trades` dichiara +152,48 $ di realizzato lordo contro i +12,44 $ del ledger
(F-084).

## 2. Verdict

**Anomalie significative.**

Il percorso del denaro è corretto: ogni ordine ha segnale o causa nel `reason`, gate, risk check e fill riconciliato
col broker. Ma la P&L S4 del giorno dipende interamente da posizioni la cui uscita S4 è disarmata (F-089). La serie
degli score resta a pesi non dichiarati (F-088), e oggi questo toglie un BUY QCOM che ai pesi dichiarati sarebbe
partito. L'endpoint di P&L dei trade riporta un realizzato 12 volte quello vero (F-084). Nessuno dei tre richiede di
fermare il sistema. Tutti e tre vanno dichiarati prima della sintesi di fine osservazione (28/09).

---

## 3. Timeline del 2026-09-24 (UTC)

| Ora | Componente | Evento | Esito | Fonte |
|---|---|---|---|---|
| 00:00–13:29 | `worker-news-stream` | WS Benzinga 24/7; 107 dispatch `run_sentiment_worker` | tutti `skipped: market_closed` | `worker-inference-2026-09-24.log` |
| 01:25–22:01 | ingest | 358 `duplicate_id` WS fuori seduta | scartati | `news_queue_drops` |
| 06:20 · 08:20 · 10:02 · 12:20 · 21:01 | deploy | Warm shutdown `worker`/`worker-inference` + restart `beat` | job inference 1391 (08:20) e 1650 (12:20) persi con SIGTERM; 69 «connection limit exceeded» sul WS news | log |
| 07:00–07:01 | `detect_regime` | SIDEWAYS ×0,7 | riuscito (72 s) | log inference |
| 08:13 · 09:02 | alert | `pipeline:broker_stale` critical (Alpaca read failed) | rientrati in < 1 min, fuori seduta | `mobile_events` |
| 11:28–11:29 · 22:28–22:29 | `sentiment_shadow` | SoftTimeLimit → TimeLimitExceeded(840) → SIGKILL, lotto di 12 item perso | turno prosegue | log inference |
| 13:30:01 | alert | `pipeline:portfolio_cycle_late` critical + `signal_stale` warning | rientrati 14:08 / 13:33 | `mobile_events` |
| 13:31:59 | sentiment | drena la coda notturna: **188 stale** (età mediana 5,7 h) + 47 not_tradable | scartati | `news_queue_drops` |
| 13:32:51 | sentiment | primo segnale | — | `sentiment_signals` |
| 13:36–13:57 | sentiment | QQQ −0,128, MU +0,169, WDC −0,110 (ensemble, posizioni S4 nel target S1) | **nessuna uscita** (DAY-001) | 12441/12450/12460 |
| 13:49 | sentiment | META −0,026 (roundup «Stock Market Today … Futures Drop») | primo ciclo sotto gate per META | 12453 |
| 14:00–14:35 | Ollama | 11 timeout di modello nell'ora; **5 fallback FinBERT** (META e MSFT sullo stesso articolo, SOXX, SPCX, META) | segnali FinBERT | `finbert_fallback_events` 29–33 |
| **14:07:00** | `portfolio-cycle` | **primo ciclo, 37 min dopo l'apertura** | «Exit hysteresis (2 cycles): ['META']» | `portfolio_cycles`, log |
| 14:07:09 | Telegram | alert #161 (AMAT −21,7%, WDC sub-one-share) | **400 Bad Request** | log worker |
| 14:20:06 | sentiment | META +0,131 (Citizens alza il target a $885, pubbl. 13:11) · INTC 0,000 (TD Cowen Hold) | META esce, INTC no | 12477, 12479 |
| **14:22:00** | S4 → broker | **SELL META** 1,935 `below_entry_gate` (+0,131) | filled @766,52 | decisione 42936, trade 1027 |
| 14:22:07 | Telegram | secondo alert #161 | **400** | log |
| 14:40:28 | sentiment | QCOM +0,266 (ai pesi 0,7/0,3 sarebbe 0,337) | SKIP_THRESHOLD | 12497 |
| 15:13 | sentiment | PANW +0,005 (ensemble) | nessuna uscita (DAY-001) | 12526 |
| 15:14:36 | sentiment | BA −0,04 single gpt-oss (fallback) | conta da controsegnale | 12527 |
| 15:22:04 | S4 | «Exit hysteresis (2 cycles): ['BA']» | — | log |
| 15:29:33 | sentiment | **META +0,306** (JPMorgan PT $920) × velocity 1,20 → 0,367 | sopra gate | 12532 |
| **15:37:00** | S4 → broker | **BUY META** 1,8855 · **SELL BA** 7,1904 `fallback_filtered` | filled @767,07 e @196,34 | decisioni 43511/43512, trade 1028/1026 |
| 15:37:08 | stop sync | stop META qty 1 su 1,8855 (**53%**), stesso ciclo dell'ingresso | `new`, poi cancellato | ordine `b074f541` |
| 16:10:04 | sentiment | **LLY +0,368** (FDA insulina settimanale) | SKIP_PYRAMIDING ×3 (a libro da S1) | 12553 |
| 17:43:39 | sentiment | NOW 0,000 (articolo «Whale Activity») | isteresi 17:52 | 12587 |
| **18:07:00** | S4 → broker | **SELL NOW** 2,9791 `below_entry_gate` | filled @138,18 | decisione 44693, trade 1022 |
| 18:27–18:35 | sentiment | META +0,293 (Raymond James) sovrascritto da 0,000 FANOUT (AST SpaceMobile) | — | 12628 → 12637 |
| **18:52:00** | S4 → broker | **SELL META** 1,8855 `below_entry_gate` (0,000) | filled @776,91 | decisione 45066, trade 1028 |
| 19:52:00 | `portfolio-cycle` | ultimo ciclo in seduta | — | `portfolio_cycles` |
| 20:00:00 | snapshot | NAV 109.954,31 $, **+71,78 $**, 43 posizioni | — | `portfolio_monitor_snapshots` |
| 20:07–21:52 | `portfolio-cycle` | 8 cicli fuori seduta senza esito | no-op | log worker |
| 21:00:00 | `decay_monitor` | 8 righe **DECAY CRITICAL** (S1/S2/S4 stesso IC −0,034) | solo log | log worker |
| 21:35:01 | `reconcile-positions` | 41 `fully_held` + 2 `partially_wound_down_coheld`, **anomalies: 0** | — | log worker |
| 22:50:00–01 | alert | `portfolio_cycle_session_grid` + `held_no_news_loss` CSCO/UBS/VALE | **aperti e chiusi in 1 s** | `mobile_events` |

---

## 4. News ingest

### 4.1 Per fonte

| Fonte | Trasporto | Estrazione | Righe scorate | Articoli distinti | Ticker | Prima–ultima riga | Lag pub→riga mediano / p90 | Fetched (stats) | Duplicati (stats) | Scartati |
|---|---|---|---|---|---|---|---|---|---|---|
| alpaca_benzinga | ws 207 / rest 0 | source_metadata | 207 | 114 | 63 | 13:32:51–19:53:52 | 11,3 min / 64,8 | 937 | **5.191** | 214 stale, 223 not_tradable |
| gdelt_gkg | — | org_lookup | 15 | 15 | 9 | 14:53:23–19:45:26 | 3,7 min / 36,4 | 2.090 | 2 | 2.073 no_ticker, 2 duplicate_content |

* Nessun timestamp futuro (`published_at > created_at`: 0). Nessun `discarded_reason` sulle righe scorate.
* Corpi Benzinga tutti presenti. **Corpi GDELT = titolo in 15/15 righe.**
* Fan-out: 129 URL distinti → 222 righe; **30 articoli multi-ticker generano 123 righe (55,4%)**, massimo 19 (DAY-013).
* Copie sindacate GDELT: la «force majeure» Oracle entra 3 volte su ORCL, il leak dei deal Morgan Stanley 2 volte su MS (DAY-014).
* Stale: 188 dalla coda notturna WS (13:31:59, età mediana 5,7 h) e 26 in seduta (età mediana 19 h, fan-out di un articolo energy del 23/09 21:07).
* Nessun gruppo duplicato per `news_log_id` in `sentiment_signals`: il guard `on_persisted` (#551/F-072) tiene.
* Entità HTML in `news_log`: 138/222 righe (il path Benzinga persiste il grezzo). **Gli input FinBERT del giorno ne
  sono privi in 7/7**, anche quando il titolo a DB contiene `&#39;` (evento 29): la decodifica funziona almeno su
  quel ramo. Il testo passato agli LLM non è persistito → non verificabile oltre questo punto.
* Copertura (dossier): 31/96 simboli di watchlist senza righe `news_log` (42 il 23/09; parte del miglioramento viene
  dagli alias #566, discontinuità dichiarata nel charter); effective-timely 45/96.
* Nessun buco di ingest in seduta. L'unico vuoto WS > 25 min in seduta (19:21–19:50) coincide con zero articoli
  pubblicati nella finestra, anche lato REST: è silenzio della fonte, non un'interruzione.

### 4.2 Per ticker (top 15 per righe)

| Ticker | Righe | Ensemble | Single/FinBERT | Max | Min | Ultimo |
|---|---|---|---|---|---|---|
| SPY | 26 | 14 | 12 | +0,180 | −0,210 | +0,072 |
| META | 17 | 6 | 11 | +0,360 | −0,150 | +0,163 |
| NVDA | 13 | 5 | 8 | +0,130 | −0,120 | +0,120 |
| ORCL | 13 | 7 | 6 | +0,040 | −0,255 | −0,104 |
| GOOGL | 11 | 5 | 6 | +0,150 | −0,300 | +0,150 |
| MCD | 9 | 6 | 3 | 0,000 | −0,280 | −0,220 |
| MSFT | 9 | 2 | 7 | +0,060 | −0,240 | 0,000 |
| MU | 7 | 4 | 3 | +0,169 | −0,280 | +0,130 |
| AMZN | 6 | 4 | 2 | +0,210 | −0,021 | 0,000 |
| QQQ | 5 | 2 | 3 | +0,150 | −0,270 | −0,270 |
| LLY | 4 | 3 | 1 | +0,368 | −0,038 | −0,038 |
| AAPL | 4 | 2 | 2 | +0,053 | −0,020 | 0,000 |
| AVGO | 4 | 0 | 4 | −0,050 | −0,420 | −0,050 |
| MS | 4 | 2 | 2 | −0,216 | −0,420 | −0,420 |
| XLE | 4 | 0 | 4 | +0,240 | +0,009 | +0,012 |

### 4.3 Top news per impatto sul segnale

| Segnale | Ticker | Score | News | Esito |
|---|---|---|---|---|
| 12477 | META | +0,131 | «Citizens … Raises Price Target to $885» (pubbl. 13:11, riga 14:20) | SELL 14:22, +31,38 $ net (DAY-004) |
| 12527 | BA | −0,040 (single) | «Redwire, Rocket Lab, Firefly Split a $981 Million Space Force Pie» | SELL 15:37, −40,49 $ net (DAY-006) |
| 12532 | META | +0,306 | «JP Morgan … Raises Price Target to $920» | BUY 15:37, poi +18,26 $ net |
| 12553 | LLY | +0,368 | «Lilly Wins FDA Nod For Weekly Insulin…» | SKIP_PYRAMIDING (S1 a libro) (DAY-008) |
| 12587 | NOW | 0,000 | «10 Information Technology Stocks Whale Activity…» | SELL 18:07, +1,69 $ |
| 12637 | META | 0,000 | «Why Is AST SpaceMobile Stock Surging on Thursday?» (FANOUT) | SELL 18:52 (DAY-005) |
| 12479 | INTC | 0,000 | TD Cowen «Reiterates Hold» | nessuna SELL: INTC nel target S1 (DAY-001) |
| 12497 | QCOM | +0,266 | «Qualcomm Renews Patent License With Apple…» | sotto gate a 0,5/0,5, sopra a 0,7/0,3 (DAY-002) |

**Confidenza dell'analisi ingest: alta** per volumi, fonti e fan-out (letture dirette dal DB). Media sulla copertura
(metrica del dossier, non ricalcolata).

---

## 5. Performance modelli LLM

| Modello | Risposte | Eleggibili (flag) | Sotto floor 0,40 | Conf. mediana | Polarity media | Pos/Neg/Zero | Timeout (log, giorno / seduta) |
|---|---|---|---|---|---|---|---|
| glm-5.3:cloud | 211 | 48 | **159 (75,4%)** | 0,30 | −0,009 | 89/89/33 | 13 / 8 |
| gpt-oss:20b-cloud | 213 | 48 | 64 (30,0%) | 0,42 | −0,055 | 71/99/43 | 14 / 11 |

| Tipo segnale | Righe | % | Score medio | Min | Max | Sopra gate \|0,30\| | `ensemble_std`=0 |
|---|---|---|---|---|---|---|---|
| ensemble glm-5.3+gpt-oss | 108 | 48,6% | −0,007 | −0,290 | +0,368 | 2 | 34 |
| single gpt-oss (fallback_used) | 101 | 45,5% | −0,049 | −0,420 | +0,400 | 7 | 15 |
| single glm-5.3 (fallback_used) | 6 | 2,7% | +0,020 | −0,200 | +0,200 | 0 | 3 |
| finbert (reale) | 7 | 3,2% | −0,003 | −0,051 | +0,010 | 0 | 7 |

* **Latenza**: nessuna telemetria per chiamata (F-086). Dai log: 62 task sentiment con item (222 item); durata
  mediana 151,7 s, **per-item mediana 60,2 s**, 16 task > 300 s, max 663,6 s. `raw_ingested_at`→segnale mediana
  **675 s** (295 s il 23/09); pubblicazione→segnale Benzinga mediana 11,3 min, p90 64,8 min (DAY-012).
* **Refusal/invalid output**: nessun parse-fail nei log. Timeout di modello: 27 nel giorno, 19 in seduta, concentrati
  14:00–14:35 (11) e 18:00–18:40 (6). Nessuna finestra di outage: ogni ciclo ha avuto segnali ensemble.
* **Disaccordo**: sui 108 ensemble, 6 a segni opposti e 10 con spread ≥ 0,30; sui 97 single gpt-oss con due risposte,
  14 a segni opposti (DAY-010).
* **Pesi effettivi**: 0,5/0,5. Score riprodotto a pesi uguali su **108/108** segnali ensemble (0,593/0,407, il valore
  ora in `ensemble:weights:current`, ne riproduce 40; 0,7/0,3 ne riproduce 34); 129 WARNING «Ignoring weights for
  inactive sentiment models: ['glm-5.2:cloud']». Con 0,7/0,3 cambia lato gate solo QCOM 12497 (0,266 → 0,337) (DAY-002).
* **Dominanza di un modello**: 107 segnali su 222 sono lettura di un solo modello (101 gpt-oss). Nei 60 ensemble
  senza nessun `eligible=true` entrambi i modelli contribuiscono via retry a floor 0 (DAY-011).
* **Fallback FinBERT reale**: 7 (META ×3, MSFT, SOXX, SPCX, NVDA), tutti «Ollama timeout», tutti con `body_chars` > 0:
  FinBERT ha visto parte del corpo. Gli eventi 29 (META) e 30 (MSFT) hanno lo stesso input («Google, OpenAI and
  Anthropic AI Safety Group…»): fan-out anche sul fallback. Gli esiti task dichiarano **114** `finbert_fallbacks` (DAY-009).
* **Verifica funzionale**: l'output passa per `aggregate()` con floor di confidenza e retry; la varianza è misurata
  (`ensemble_std`) ma non è un gate (F-037/F-054). Le copie sindacate GDELT pesano più volte (DAY-014). Uno stesso
  articolo genera segnali su più ticker (DAY-013). Confidenza bassa riduce il peso (`_w = confidence × weight`) e lo
  score (× confidenza media). I modelli girano solo nel `worker-inference` (coda `inference`); il ciclo portfolio legge
  `sentiment_signals` dal DB → nessuna chiamata LLM nel percorso ordini. Le letture single-model sono escluse dal
  ranking BUY (363 `SKIP_FALLBACK`) ma **contano come controsegnale in uscita**: BA è uscita su una di esse (DAY-006).

---

## 6. Segnali finali per ticker (quelli che hanno toccato il gate o un ordine)

| Ticker | Segnale | Ora | Score | Tipo | Destino |
|---|---|---|---|---|---|
| WDC | 12451 / 12460 | 13:46 / 13:57 | +0,400 / −0,110 | single (articolo Sandisk) / ensemble | nessuna uscita: WDC nel target S1 |
| META | 12453 → 12477 | 13:49 → 14:20 | −0,026 → +0,131 | ensemble | isteresi 14:07 → **SELL 14:22** |
| INTC | 12479 | 14:20 | 0,000 | ensemble | nessuna uscita (target S1) |
| QCOM | 12497 | 14:40 | +0,266 | ensemble | SKIP_THRESHOLD ×11 (a 0,7/0,3: 0,337) |
| NFLX / GOOGL | 12503 / 12538 | 14:47 / 15:42 | −0,360 / −0,300 | single gpt-oss | SKIP_FALLBACK; long-only |
| BA | 12527 | 15:14 | −0,040 | single gpt-oss | controsegnale → **SELL 15:37** `fallback_filtered` |
| META | 12532 | 15:29 | +0,306 (× 1,20 = 0,367) | ensemble | **BUY 15:37**; poi SKIP_IDEMPOTENCY ×7 |
| META | 12550 | 16:02 | +0,360 | single gpt-oss | SKIP_FALLBACK |
| LLY | 12553 | 16:10 | +0,368 | ensemble | SKIP_PYRAMIDING ×3 (S1) |
| NOW | 12587 | 17:43 | 0,000 | ensemble | isteresi 17:52 → **SELL 18:07** |
| AVGO | 12597 / 12608 | 17:55 / 18:08 | −0,360 / −0,420 | single gpt-oss | SKIP_FALLBACK; long-only |
| META | 12628 → 12637 | 18:27 → 18:35 | +0,293 → 0,000 | ensemble (FANOUT) | **SELL 18:52** |
| MS | 12658 | 19:45 | −0,420 | single gpt-oss (GDELT, strategist) | long-only (DAY-015) |

Disposizioni S4 (`s4_intent_events`, per `decision_slot`): 2.013 candidati osservati; SKIP_ENTRY_GATE 766,
SKIP_ENTRY_FRESHNESS 728, SKIP_FALLBACK 363, SKIP_STALE 125, **SKIP_PYRAMIDING 23** (contro **2** righe
`execution_decisions`), SKIP_IDEMPOTENCY 7, SUBMITTED 1. Nessun RANK_LONG_ONLY né RANK_OUTSIDE_TOP_N: i ribassisti
sopra gate erano tutti single-model.

---

## 7. Ordini generati/eseguiti

| Decisione | Strategia | Ticker | Azione | Qty | Prezzo atteso | Fill | Stato | Broker | Rationale | Segnale | Risk check | Anomalie |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 14:22:00 (42936) | S4 | META | SELL | 1,935 | n/d (`decision_price` NULL) | 766,52 | filled 14:22:07 | Alpaca paper | `below_entry_gate` su +0,131 | NULL | isteresi 2 cicli | SELL con sentiment positivo (F-013); `signal_id` NULL |
| 15:37:00 (43512) | S4 | BA | SELL | 7,1904 | n/d | 196,34 | filled 15:37:08 | Alpaca paper | `fallback_filtered`, ma il `reason` cita il segnale d'ingresso 12338 | NULL | isteresi | causa reale = lettura single −0,04 (F-059) |
| 15:37:00 (43511) | S4 | META | BUY | 1,8855 | n/d | 767,07 | filled 15:37:07 | Alpaca paper | +0,306 × velocity 1,20 = 0,367, peso 2,0%, regime 0,7 | 12532 | gate, top-N, P0-05, idempotenza | rientro 0,55 $/az. sopra l'uscita delle 14:22 (F-013) |
| 15:37:08 | S4 stop | META | SELL stop | 1 | — | — | new → canceled | Alpaca paper | stop protettivo | — | — | copertura **53%** (F-022) |
| 18:07:00 (44693) | S4 | NOW | SELL | 2,9791 | n/d | 138,18 | filled 18:07:08 | Alpaca paper | `below_entry_gate` su 0,000 | NULL | isteresi | `signal_id` NULL |
| 18:52:00 (45066) | S4 | META | SELL | 1,8855 | n/d | 776,91 | filled 18:52:06 | Alpaca paper | `below_entry_gate` su 0,000 FANOUT | NULL | isteresi | segnale +0,293 sovrascritto (F-023) |

Nessun ordine S1 (gate di ribilanciamento chiuso, ultimo ribilanciamento 2026-09-01). `orders_count` somma 35 sui 24
cicli contro 5 ordini inviati (DAY-020). `/api/orders` lega le 4 SELL al `signal_id`/`decision_id` dell'**ingresso**
(es. SELL META 18:52 → 12532/43511) invece che alla decisione d'uscita (DAY-003).

---

## 8. PnL / rendimento

Prezzi: `docs/evidence/dossier/2026-09-24.json` e `2026-09-23.json` (`snapshot_apertura.close_price`, Alpaca SIP
`adjustment=all`) e barre al minuto Alpaca SIP (sola lettura). Close-to-close 23/09 → 24/09.

| Voce | Ticker | Qty | Da → A | $ | Tipo |
|---|---|---|---|---|---|
| Realizzato (aperta 23/09) | META #1027 | 1,935 | 750,152 → 766,52 | **+31,38** net (+43,38 maturati oggi da 744,10) | realizzato |
| Realizzato (aperta 23/09) | BA #1026 | 7,1904 | 201,86 → 196,34 | **−40,49** net (−25,81 oggi da 199,93) | realizzato |
| Realizzato (aperta 21/09) | NOW #1022 | 2,9791 | 137,54 → 138,18 | **+1,69** net (−7,75 oggi da 140,78) | realizzato |
| Aperta e chiusa oggi | META #1028 | 1,8855 | 767,07 → 776,91 | **+18,26** net (+18,55 lordo) | realizzato |
| Pre-esistente S4 (target S1) | INTC | 14,5237 | 122,60 → 127,39 | +69,57 | non realizzato |
| Pre-esistente S4 (target S1) | MU | 1,4634 | 1071,88 → 1080,53 | +12,66 | non realizzato |
| Pre-esistente S4 (target S1) | CSCO | 17,1357 | 106,43 → 106,97 | +9,25 | non realizzato |
| Pre-esistente S4 (target S1) | XLE | 22,0056 | 62,37 → 62,60 | +5,06 | non realizzato |
| Pre-esistente S4 (target S1) | QQQ | 2,0745 | 741,21 → 741,10 | −0,23 | non realizzato |
| Pre-esistente S4 (target S1) | WDC | 0,3347 | 473,69 → 450,31 | −7,83 (il dossier la riporta a qty 0, DAY-017) | non realizzato |
| Pre-esistente S4 (target S1) | MRVL | 6,3743 | 260,90 → 258,95 | −12,43 | non realizzato |
| Pre-esistente S4 (target S1) | PANW | 3,8762 | 393,30 → 389,92 | −13,10 | non realizzato |
| **S4 giornata** | | | | **≈ +91,3 lordo, ≈ +89,7 netto** (`cost_usd` modellato 1,60 $) | |
| S1 giornata | | | | ≈ −19,2 (−15,4 dal dossier, corretto di −3,7 $ per l'azione UNH in più a ledger) | |
| **Book (broker)** | | | 109.882,53 → 109.954,31 | **+71,78** (snapshot 20:00; Alpaca history 109.953,87) | equity |

* Riconciliazione: S4 +91,3 + S1 −19,2 = +72,1 contro +71,8 del book. Lo scarto di 0,3 $ è nei costi modellati e
  nello snapshot delle 20:00 contro il close. Benchmark: SPY −0,08%, QQQ −0,01%.
* Per strategia: S4 ≈ +90 $, S1 ≈ −19 $. **Le posizioni S4 nel target S1 fanno +73,0 $**; quelle fuori dal target
  (META, BA, NOW e il rientro META) +16,7 $ netti. Alla regola S4 dichiarata la sleeve avrebbe fatto circa −3 $ (DAY-001).
* Slippage: non misurabile. `decision_price` è NULL sulle 5 decisioni d'ordine e `slippage_est` copia `cost_usd` (F-015).
  Proxy barra del ciclo → fill: META SELL 14:22 766,65 → 766,52 (−0,02%); BUY META 15:37 767,09 → 767,07; BA 196,38 →
  196,34; NOW 18:07 138,25 → 138,18; META 18:52 776,86 → 776,91. Tutti entro ±0,05%.
* Commissioni: 0 (Alpaca). `cost_usd` modellato: 0,29 + 0,80 + 0,22 + 0,29 = 1,60 $.
* `/api/trades` dichiara per le stesse uscite: META 18:52 `entry_price` **720,99**, `gross_pnl` **+105,44**; BA
  `entry_price` 189,65, **+48,10**; META 14:22 `entry_price` 767,07 (il BUY successivo), **−1,06**; NOW `gross_pnl` null.
  Somma +152,48 $ contro +12,44 $ lordi del ledger `trades` (DAY-003).

---

## 9. Correttezza buy/sell

| Controllo | Esito | Nota |
|---|---|---|
| BUY solo quando consentito | ✅ | 1 BUY, ensemble 0,306 × velocity 1,20 ≥ 0,30, top-N, P0-05 e idempotenza verificati |
| SELL/exit corretti | ⚠️ | META, NOW e BA escono secondo la regola dichiarata. **5 posizioni S4 nel target S1 con segnale fresco ensemble sotto gate non escono** (DAY-001). BA esce su una lettura single-model che il ranking BUY scarta (DAY-006) |
| Stop-loss | ⚠️ | nessuno scattato. Stop META 1028 creato nello stesso ciclo dell'ingresso ma al **53%**. 11/46 posizioni sub-one-share senza stop: AMAT −21,7%, WDC −17,9% (DAY-016) |
| Signal flip | ⚠️ | QQQ −0,128/−0,228 e WDC −0,110 su posizioni S4 senza uscita (DAY-001) |
| Max holding days | ❌ | WDC 65 giorni, CSCO 30, XLE 24 (DAY-001, F-025) |
| Rebalance band | ⚠️ | nessuna banda fra gate 0,30 e uscita: META SELL a +0,131 e ri-BUY 75 min dopo a +0,306 (DAY-004) |
| Ordini duplicati | ✅ | nessuno. 7 `SKIP_IDEMPOTENCY` su META 12532 |
| Ordini contrari ravvicinati senza rationale | ⚠️ | META SELL 14:22 → BUY 15:37 → SELL 18:52, ognuno con rationale ma è churn |
| Ticker non consentiti | ✅ | tutti in watchlist |
| Fuori orario | ✅ | fra 14:22 e 18:52; 8 cicli dopo la chiusura sono no-op |
| Dati stale | ✅ | 125 SKIP_STALE, 728 SKIP_ENTRY_FRESHNESS; 188 articoli notturni scartati all'apertura |
| LLM output non valido | ✅ | nessun parse-fail. Single-model esclusi dal ranking BUY (ma non dalle uscite, DAY-006) |
| Circuit breaker | ✅ | nessun breaker attivo; loss-feedback eseguito senza scatti |
| Strategia disabilitata | ✅ | S1+S4 attive, `execution.engine=portfolio` |
| Paper/live | ✅ | paper verificato (URL e 87 snapshot) |
| Idempotenza retry Celery | ✅ | nessun doppio invio; nessun retry dei task portfolio; i job persi nei deploy erano sentiment/inference fuori seduta |
| Riconciliazione | ⚠️ | 41/43 al centesimo. UNH ledger 1,5926 vs broker 0,5926 e WDC ledger 2,981 vs residuo 0,3347, «anomalies: 0» (DAY-017) |

Pattern specifici:
* Roundtrip < 30 min: **nessuno** (META 15:37 → 18:52, 3h15).
* Pyramiding > 3 BUY: **nessuno**.
* SELL con sentiment positivo: **sì**, META 14:22 su +0,131 (DAY-004).
* `fallback_used=True` su tutti i simboli: **no**. Il 51,4% di letture non-ensemble è floor di confidenza su glm-5.3, non outage.
* NO-ORDER: **no** (5 decisioni d'ordine, 5 ordini).
* Score < 0,05 che genera ordine: **SELL NOW e SELL META 18:52 su 0,000, SELL BA su −0,04**: uscite per regola, non ingressi.
* Ordini identici nello stesso minuto: **no**. BUY META, SELL BA e stop META alle 15:37 riguardano simboli/lati diversi.

`exit_mechanism`: le quattro righe del 24/09 (`below_entry_gate` ×3, `fallback_filtered` ×1) sono **post-#184**, cioè
disposizioni osservate e non stime per età. `trades.exit_reason` dice `portfolio_sell` per le stesse uscite: è un
vocabolario diverso, non una contraddizione.

---

## 10. Anomalie trovate

### [DAY-001] Cinque posizioni S4 nel target congelato di S1 ricevono un segnale ensemble fresco sotto gate e non escono

* Tipo: Bug
* Area: Signal / Orders / Risk
* Evidenza:
  * file/log/tabella: `sentiment_signals`; `execution_decisions`; Redis `strategy:rebalance_state:S1` (`last_rebalance` 2026-09-01T14:07); log worker; barre Alpaca SIP 1 min
  * timestamp: 13:36–15:13
  * snippet/query:
    ```
    QQQ 12441 -0,128 (13:36), 12603 -0,228 (18:03) · MU 12450 +0,169 (13:44), 12486 -0,030, 12586 0,000, 12653 +0,130
    WDC 12460 -0,110 (13:57) · INTC 12479 0,000 (14:20) · PANW 12526 +0,005 (15:13)   [tutti ensemble, fallback_used=false]
    S1 target_weights: INTC 0,0145 MU 0,0118 PANW 0,0211 QQQ 0,0236 WDC 0,0116 (anche MRVL, XLE, CSCO)
    "Exit hysteresis (2 cycles)": solo ['META'] 14:07, ['BA'] 15:22, ['NOW'] 17:52 — mai INTC/MU/PANW/QQQ/WDC
    ```
* Descrizione: stesso meccanismo del 22–23/09. Il combiner somma il peso S1 congelato, che contiene simboli comprati
  da S4, quindi `below_entry_gate` non porta la posizione a zero. META, NOW e BA, fuori da quel target, escono alla
  stessa regola nello stesso giorno. Il checklist dell'alpha-miss del 24/09 dà F-089 «not_exposed» guardando solo CSCO:
  è smentito da queste cinque posizioni.
* Impatto: vendita al secondo ciclo dopo il primo segnale fresco sotto gate, al prezzo d'apertura della barra, contro
  il close. INTC 14:37 @124,10 → 127,39: +47,78 · MU 14:22 @1052,46 → 1080,53: +41,08 · QQQ 14:22 @737,03 → 741,10:
  +8,44 · PANW 15:37 @390,38 → 389,92: −1,78 · WDC 14:22 @457,45 → 450,31: −2,39. Tenerle ha reso **+93,13 $** (costo
  −93,13, attribuito). La S4 del giorno (≈ +89,7 $) sarebbe circa −3 $ alla regola dichiarata.
* Severità: High
* Confidenza: High sul meccanismo. Medium sul costo (isteresi a 2 cicli, prezzo = open della barra, MRVL e XLE esclusi
  perché avevano solo letture single-model).
* Azione consigliata: il ticket di correttezza del 22/09 resta valido (quota S4 separata dal target S1). Prima della
  sintesi va dichiarato nel charter che la P&L S4 di queste posizioni non è P&L della regola S4. Va corretta anche la
  voce F-089 del checklist alpha-miss, che oggi la dà non esposta.
* Test/monitor consigliato: monitor giornaliero «posizioni S4 nel target S1 con segnale fresco sotto gate e nessuna SELL».
* → ledger **F-089**

### [DAY-002] Pesi d'ensemble ancora 0,5/0,5: ai pesi dichiarati QCOM 12497 supera il gate

* Tipo: Bug
* Area: LLM / Signal / Orders
* Evidenza:
  * file/log/tabella: `worker-inference-2026-09-24.log`; `sentiment_signals` × `llm_responses`; `src/llm/ensemble.py:327-334`; Redis `ensemble:weights:current`
  * timestamp: tutta la seduta; 129 WARNING
  * snippet/query:
    ```
    WARNING Ignoring weights for inactive sentiment models: ['glm-5.2:cloud']   (x129)
    score = Σ p·c·w / Σ c·w × mean(c): pesi uguali 108/108; 0,593/0,407 40/108; 0,7/0,3 34/108
    0,7/0,3 → QCOM 12497 0,266 → 0,337 (gate 0,30, velocity 1,0)   META 12532 0,306 → 0,274 (× 1,20 = 0,329, BUY invariato)
    ensemble:weights:current oggi = {glm-5.3: 0,593, gpt-oss: 0,407, source: telegram}: non usato il 24/09
    ```
* Descrizione: il difetto del 22–23/09 persiste. Il valore `source: telegram` ora in Redis non era in uso il 24/09
  (lo score si riproduce solo a pesi uguali e il WARNING su glm-5.2 continua fino a fine seduta), quindi il cambio è
  successivo e va datato quando sarà registrato.
* Impatto: ai pesi 0,7/0,3 QCOM entra alle 14:52 (@192,63) e, sul segnale ensemble 12589 0,000 delle 17:47, esce alle
  18:07 (@193,26). Con la taglia S4 di riferimento (2.200 $, 11,42 az.) sono **+7,19 $** non presi (congetturale; la
  lettura single 12544 0,000 delle 15:48 non avrebbe forzato l'uscita perché 12497 era ancora fresco).
* Severità: High per l'interpretabilità della serie · Confidenza: High sul meccanismo, Low sul controfattuale
* Azione consigliata: correggere l'annotazione del charter (pesi effettivi 0,5/0,5 dal 22/09 07:32), con la data
  esatta del cambio `source: telegram`.
* Test/monitor consigliato: persistere per segnale i pesi effettivi usati.
* → ledger **F-088**

### [DAY-003] `/api/trades` dichiara +152,48 $ di realizzato contro +12,44 $ del ledger

* Tipo: Bug · Area: Frontend / PnL
* Evidenza: `/api/trades` riga `fa968184` (SELL META 18:52): `entry_price` 720,99, `gross_pnl` +105,44; `b560682f`
  (BA): `entry_price` 189,65, +48,10; `efc32e69` (META 14:22): `entry_price` 767,07, −1,06; `84041754` (NOW): null.
  Ledger `trades` 1028/1026/1027/1022: +18,55 / −39,69 / +31,67 / +1,91 lordi. `/api/orders` lega le SELL a
  `signal_id`/`decision_id` dell'ingresso.
* Descrizione: F-084. Oggi l'errore cambia il segno di BA e moltiplica per 12 il realizzato del giorno.
* Severità: Medium · Confidenza: High
* → ledger **F-084**

### [DAY-004] META venduta a +0,131 e ricomprata 75 minuti dopo a +0,306

* Tipo: Anomalia · Area: Orders / Signal
* Evidenza: `execution_decisions` 42936 («[below_entry_gate] … generated 2026-09-24 14:20 UTC, score=+0.131»), 43511; `trades` 1027, 1028
* Descrizione: nessuna banda fra gate d'ingresso e uscita (F-013). Costo già registrato dall'alpha-miss del 24/09
  (1,04 $) → null qui.
* Severità: Low · Confidenza: High
* → ledger **F-013**

### [DAY-005] META rivenduta alle 18:52 su uno 0,000 FANOUT che sovrascrive un +0,293 issuer-specifico

* Tipo: Anomalia · Area: Signal
* Evidenza: `execution_decisions` 45066 («generated 2026-09-24 18:35 UTC, score=+0.000»); segnali 12628 (18:27, +0,293) e 12637 (18:35, 0,000, «Why Is AST SpaceMobile Stock Surging…»)
* Descrizione: F-023. Costo già registrato dall'alpha-miss (1,28 $) → null qui.
* Severità: Low · Confidenza: High
* → ledger **F-023**

### [DAY-006] BA chiusa da una lettura single-model che il ranking BUY scarta

* Tipo: Bug · Area: Signal / Orders
* Evidenza: segnale 12527 (`single:gpt-oss`, −0,04, conf 0,40, 15:14); log 15:22/15:37 «dropped … fallback signal(s) from BUY ranking (#108): [… 'BA' …]» e FIX-D senza BA; decisione 43512 `fallback_filtered` che cita il segnale 12338 del 23/09
* Descrizione: F-059. Asimmetria: alle 18:52 la lettura single META 12646 (+0,163) è invece ignorata e la decisione usa
  l'ensemble precedente. Costo già registrato dall'alpha-miss (3,31 $) → null qui.
* Severità: Medium · Confidenza: High
* → ledger **F-059**

### [DAY-007] Primo ciclo alle 14:07: oggi il ritardo ha rimandato l'uscita META a un prezzo migliore

* Tipo: Anomalia · Area: Ops / Orders
* Evidenza: `portfolio_cycles` primo 14:07:00; `mobile_events` `portfolio_cycle_late` 13:30–14:08; barre META 14:07 759,05 / 14:22 766,65
* Descrizione: F-021. Con un ciclo alle 13:52 il segnale META delle 13:49 (−0,026) avrebbe avviato l'isteresi e la
  vendita sarebbe partita alle 14:07.
* Impatto: 1,935 × (759,05 − 766,52) = **−14,45 $** (attribuito: il ritardo oggi ha reso 14,45 $).
* Severità: Medium · Confidenza: Medium
* → ledger **F-021**

### [DAY-008] P0-05 blocca LLY +0,368 (a libro da S1) e traccia 2 blocchi su 23

* Tipo: Anomalia · Area: Orders / Data
* Evidenza: `s4_intent_events` SKIP_PYRAMIDING 23 (NOW 15 e BA 5 su posizioni S4, LLY 3 su posizione S1); `execution_decisions` SKIP_PYRAMIDING 2; log «P0-05 pyramiding guard: skipping BUY for LLY — open trade exists in DB» ×3
* Descrizione: F-031.
* Impatto: BUY LLY 16:22 @1196,66 con 2.200 $ (1,838 az.) → close 1181,89 = **−27,15 $**. Il blocco ha evitato una
  perdita (congetturale).
* Severità: Medium · Confidenza: Medium
* → ledger **F-031**

### [DAY-009] 51,4% dei segnali non-ensemble; gli esiti task dichiarano 114 fallback FinBERT contro 7 reali

* Tipo: Anomalia · Area: LLM / Data
* Evidenza: `sentiment_signals.model_id` `single:*` 107/222, `finbert` 7; somma `finbert_fallbacks` negli esiti task 114; `finbert_fallback_events` 7 righe. glm-5.3 sotto floor 159/211.
* Descrizione: F-078. La quota non-ensemble è stabile (51,4% il 23/09). I 7 FinBERT reali vengono da timeout, non da floor.
* Severità: Medium · Confidenza: High
* → ledger **F-078**

### [DAY-010] Disaccordo fra modelli invisibile alla guardia: 20 segni opposti, 24 spread ≥ 0,30

* Tipo: Anomalia · Area: LLM
* Evidenza: join `llm_responses` su 205 segnali a due risposte: ensemble 6 opposti/10 spread, single gpt-oss 14/14.
* Impatto: nessun ordine → costo non stimato.
* Severità: Low · Confidenza: High
* → ledger **F-054**

### [DAY-011] 60 dei 108 segnali d'ensemble senza nessuna risposta `eligible`

* Tipo: Anomalia · Area: Data / LLM
* Evidenza: join `sentiment_signals` × `llm_responses`: 60 con `eligible` 0/2, 48 con 2/2, 0 con 1/2.
* Severità: Low · Confidenza: High
* → ledger **F-010**

### [DAY-012] Latenza di scoring: 60 s per articolo, ingest→segnale raddoppiato (675 s)

* Tipo: Anomalia · Area: LLM / Ops
* Evidenza: log task: per-item mediana 60,2 s, 16 task > 300 s, max 663,6 s; `raw_ingested_at`→segnale mediana 675 s (295 s il 23/09); pub→segnale Benzinga p90 64,8 min. Il Citizens su META (pubbl. 13:11) diventa riga alle 14:20.
* Severità: Medium · Confidenza: Medium
* → ledger **F-019**

### [DAY-013] Fan-out: 55% delle righe scorate da articoli multi-ticker, anche sul fallback FinBERT

* Tipo: Rischio · Area: News
* Evidenza: 129 URL → 222 righe; 30 multi-ticker → 123 righe, massimo 19. `finbert_fallback_events` 29 (META) e 30 (MSFT) con input identico. L'uscita META delle 18:52 nasce da una riga FANOUT (DAY-005).
* Severità: Medium · Confidenza: High
* → ledger **F-012**

### [DAY-014] Copie sindacate GDELT: Oracle «force majeure» ×3, leak Morgan Stanley ×2

* Tipo: Anomalia · Area: News / Data
* Evidenza: `news_log` GDELT ORCL: «Oracle Invokes 'Force Majeure'…: Bloomberg Report» −0,155, «Oracle shares fall as company invokes…» −0,255, «Oracle invokes force majeure over New Mexico data centre project» −0,104; MS: «…rushes to contain fallout as leaked list…» −0,275, «…rushes to check fallout after deal list leak» −0,270
* Descrizione: F-090. Nessun ordine (ribassi non detenuti, long-only).
* Severità: Low · Confidenza: High
* → ledger **F-090**

### [DAY-015] org_lookup attribuisce a DB, GS e MS articoli in cui la banca è solo la fonte dell'opinione

* Tipo: Anomalia · Area: News / Data
* Evidenza: GDELT: DB «Deutsche Bank … Issues Positive Forecast for ServiceNow (NYSE:NOW) Stock» (0,000); GS «Brazilian stock to get boost from U.S. expansion, Goldman Sachs says» (0,000); MS 12658 «The longest run of earnings upgrades in 5 years just ended. Morgan Stanley sees 7% downside» **−0,420** (single gpt-oss)
* Descrizione: F-020. L'MS −0,42 è una previsione sul mercato attribuita al titolo MS. Nessun ordine (long-only, single-model).
* Severità: Low · Confidenza: High
* → ledger **F-020**

### [DAY-016] Stop META al 53%; AMAT e WDC senza stop

* Tipo: Rischio · Area: Risk / Broker
* Evidenza: ordine `b074f541` (META qty 1 su 1,8855, 15:37:08, stesso ciclo dell'ingresso); log «#161: 11/46 held positions are unprotectable (qty < 1)», «AMAT unprotected at -21.7%», «WDC unprotected at -17.9%» (×24 ciascuno)
* Descrizione: F-022. Oggi lo stop è creato nello stesso ciclo, non uno dopo; la copertura resta parziale.
* Severità: Medium · Confidenza: High
* → ledger **F-022**

### [DAY-017] UNH con un'azione di scarto e WDC azzerata nel dossier, «anomalies: 0»

* Tipo: Bug · Area: PnL / Broker
* Evidenza: `trades` UNH qty 1,5926 contro broker 0,5926; `trades` 373 WDC qty 2,981, `quantity_remaining` 0,3347; dossier `snapshot_apertura` WDC `qty_open` 0 (`exit_fill_qty_exceeds_trade_qty`); `reconcile-positions` 21:35 «partially_wound_down_coheld: 2, anomalies: 0»
* Descrizione: F-048. La P&L di seduta WDC (−7,83 $ close-to-close, −5,16 $ open→close) manca dal dossier; quella UNH è gonfiata di +3,72 $.
* Severità: Medium · Confidenza: High
* → ledger **F-048**

### [DAY-018] Le quattro SELL non portano `signal_id`

* Tipo: Anomalia · Area: Data
* Evidenza: `execution_decisions` 42936, 43512, 44693, 45066: `signal_id` NULL; dossier `decision_signal_id_coverage.regressions`=["SELL"]
* Severità: Low · Confidenza: High
* → ledger **F-011**

### [DAY-019] `decision_price` NULL sulle decisioni d'ordine

* Tipo: Anomalia · Area: PnL / Data
* Evidenza: `execution_decisions` 42936/43511/43512/44693/45066 `decision_price` NULL; `trades.slippage_est` = `cost_usd` (0,29/0,80/0,22/0,29).
* Severità: Low · Confidenza: High
* → ledger **F-015**

### [DAY-020] `orders_count` 35 contro 5 ordini inviati

* Tipo: Anomalia · Area: Ops
* Evidenza: `portfolio_cycles` somma `orders_count` 35 su 24 cicli; esiti task: 14:07 `final_orders` 2, `submitted` 0; 14:22 `final_orders` 3, `submitted` 1
* Severità: Low · Confidenza: High
* → ledger **F-014**

### [DAY-021] Decay monitor: S1, S2 e S4 con lo stesso IC (−0,034) e lo stesso Sharpe (−6,37)

* Tipo: Anomalia · Area: Risk
* Evidenza: log 21:00:00 `DECAY CRITICAL [S1]: IC dropped 198% from 0.035 to -0.034`, `[S2] … 0.042 to -0.034`, `[S4] … 0.028 to -0.034`; Sharpe −6,37 su tutte e tre
* Severità: Medium · Confidenza: High
* → ledger **F-004**

### [DAY-022] Gli 8 DECAY CRITICAL restano nel log

* Tipo: Anomalia · Area: Ops
* Evidenza: nessuna riga `mobile_events` fra 21:00 e 21:05
* Severità: Medium · Confidenza: High
* → ledger **F-062**

### [DAY-023] Telegram 400 Bad Request sugli alert #161

* Tipo: Bug · Area: Ops
* Evidenza: log worker 14:07:09 e 14:22:07 «TelegramNotifier: Failed to send alert: Client error '400 Bad Request'»
* Severità: Medium · Confidenza: High
* → ledger **F-005**

### [DAY-024] Segreti in chiaro nei log: bot token Telegram e `api_key` FRED

* Tipo: Rischio · Area: Ops
* Evidenza: URL `api.telegram.org/bot<token>` in 17.260 righe di `worker-inference-2026-09-24.log` e 6 di `worker-2026-09-24.log`; `api_key=` in 4 righe del log inference. Valori non riportati qui.
* Severità: Medium · Confidenza: High
* → ledger **F-018**

### [DAY-025] Benchmark SPY: 84 fetch falliti per limite SIP, nessun alert

* Tipo: Anomalia · Area: Data
* Evidenza: `SPY benchmark fetch failed: {"message":"subscription does not permit querying recent SIP data"}` ×84
* Severità: Low · Confidenza: High
* → ledger **F-016**

### [DAY-026] `ingestion_stats_daily`: 5.191 duplicati contro 937 fetched per alpaca_benzinga

* Tipo: Anomalia · Area: Data
* Evidenza: `ingestion_stats_daily` 2026-09-24; `news_queue_drops` `duplicate_id` 5.191 (2.739 rest, 2.452 ws)
* Severità: Low · Confidenza: High
* → ledger **F-007**

### [DAY-027] Quattro alert della sera aperti e chiusi nello stesso secondo

* Tipo: Bug · Area: Ops
* Evidenza: `mobile_events` `pipeline:portfolio_cycle_session_grid`, `coverage:held_no_news_loss:CSCO/UBS/VALE`: `first_observed_at` 22:50:00, `resolved_at` 22:50:01
* Severità: Medium · Confidenza: High
* → ledger **F-058**

### [DAY-028] Coda notturna WS: 188 articoli scartati stale all'apertura

* Tipo: Anomalia · Area: News / Ops
* Evidenza: `news_queue_drops` `stale` ws `enqueued_off_session=true` 188 (13:31:59, età mediana 5,7 h) + 47 not_tradable; 107 dispatch `market_closed`
* Severità: Low · Confidenza: High
* → ledger **F-069**

### [DAY-029] Copertura news: 31/96 simboli senza righe, 3 posizioni cieche lato uscita

* Tipo: Anomalia · Area: News
* Evidenza: dossier `watchlist_zero_news` 31; `ticker_allerta_zero_articoli` HD, INFY, JD, MMM, SAP, SNOW, VALE; `copertura_uscita` VALE (S1, −7,38%), UBS (S1), CSCO (S4), nozionale cieco 3.184,87 $
* Severità: Medium · Confidenza: High
* → ledger **F-001**

---

## 11. False positive o aree risultate corrette

* **Paper/live**: paper su 87/87 snapshot. Nessuna ambiguità.
* **Timezone**: UTC esplicito in `celery_app.py`. Il buco 13:30–14:07 è F-021 (DST), non un'ambiguità di fuso.
* **Deploy**: cinque ricreazioni dei worker, tutte fuori seduta. I job persi con SIGTERM (08:20, 12:20) erano
  sentiment/inference a mercato chiuso. Nessun ciclo portfolio perso.
* **Idempotenza**: 7 `SKIP_IDEMPOTENCY`, nessun doppio invio.
* **Duplicati di scoring (F-072)**: nessun `news_log_id` con più di un segnale. Il guard `on_persisted` è attivo.
* **Ordini senza segnale**: nessuno. Il BUY ha `signal_id`; le SELL hanno la causa nel `reason` (F-011 è tracciabilità, non assenza).
* **Ollama**: nessun outage. 19 timeout di modello in seduta, 7 fallback FinBERT reali (3,2%).
* **F-076**: gli input FinBERT sono privi di entità HTML in 7/7, anche dove il titolo a DB le contiene. Il testo
  passato agli LLM non è persistito, quindi il fix non è verificabile oltre questo punto.
* **F-030**: contraddetto oggi. L'unico ingresso (META 15:37) ha `quota_movimento_precedente_al_segnale` 0,68 e
  `mtm_eod` +19,84 $.
* **F-043**: contraddetto oggi. I due segnali ensemble sopra gate (META, LLY) sono rialzisti e i titoli chiudono in
  rialzo (+4,50%, +2,68%).
* **F-040**: non esposto. I ribassisti sopra gate erano tutti single-model.
* **F-017**: non esposto. `detect_regime` riuscito alle 07:01.
* **Slippage**: entro ±0,05% su tutti i fill (proxy barra del ciclo).
* **Riconciliazione**: 41/43 posizioni coincidono col broker. Le posizioni correnti di `/api/positions` (01/10) non
  valgono per il 24/09 e non sono state usate.
* **Timestamp futuri**: nessuno.

## 12. Dati mancanti o non accessibili

* Latenza e esito per singola chiamata Ollama (F-086): ricostruiti solo dai log dei task.
* Testo effettivamente inviato agli LLM (prompt sanitizzato): non persistito.
* Pesi effettivi per segnale: non persistiti. Ricostruiti riproducendo lo score.
* Data del cambio `ensemble:weights:current` → `source: telegram`: non ricostruibile da Redis (nessuno storico).
* `worker-news-stream-2026-09-24.log` non ha timestamp: i 69 errori «connection limit exceeded» (unico giorno della
  settimana con questo errore) non si collocano nel tempo. Dai conteggi (76 tentativi, 6 connessioni riuscite, 5 avvii)
  coincidono con le 5 ricreazioni fuori seduta, e l'ingest WS non mostra buchi in seduta. Non registrato come anomalia.
* `decision_price` per le decisioni d'ordine: NULL. Lo slippage è stimato solo col proxy della barra al minuto.
* `economic_pnl.json` fermo al 17/09: i cumulati di carta non includono questa seduta.

## 13. Raccomandazioni immediate

1. **Charter** (correzione di strumento, non taratura): dichiarare che (a) la P&L S4 delle posizioni nel target S1
   congelato non è P&L della regola S4 (F-089: oggi +93 $ su +90 $ del giorno) e (b) i pesi effettivi sono 0,5/0,5
   dal 22/09 07:32 almeno fino a fine 24/09 (F-088).
2. Correggere il checklist alpha-miss del 24/09 su F-089 («not_exposed» → esposto su INTC, MU, PANW, QQQ, WDC).
3. Non leggere `/api/trades` per il P&L dei roundtrip: usare il ledger `trades` (F-084).
4. Ruotare il bot token Telegram e la chiave FRED, entrambi presenti in chiaro nei log persistenti (F-018).

## 14. Test o monitor da aggiungere

* Monitor «posizioni S4 nel target S1 con segnale fresco sotto gate e nessuna SELL» (F-089).
* Persistenza per segnale dei pesi effettivi e delle risposte eleggibili (F-088, F-010).
* Test di uscita: una lettura single-model non deve avere in uscita un ruolo diverso da quello che ha nel ranking (F-059).
* Test di `/api/trades` con SELL seguita da un BUY sullo stesso simbolo nella stessa seduta (F-084).
* Timestamp nel logger di `worker-news-stream` e contatore delle riconnessioni WS fallite.

## 15. Ticket tecnici suggeriti (solo correttezza)

* **F-089**: separare la quota S4 dal target congelato S1 nel combiner (già proposto il 22/09).
* **F-088**: una rinomina di `model_id` deve migrare o invalidare in modo esplicito i pesi, invece di cadere sul default con un WARNING.
* **F-084**: `/api/trades` e `/api/orders` devono esporre il ledger `trades` e la decisione d'uscita, non l'ordine broker accoppiato all'ingresso.
* **F-059**: rendere coerente il trattamento delle letture single-model fra ranking BUY e controsegnale d'uscita, e
  persistere nel `reason` il segnale che ha davvero causato l'uscita.
* **F-048**: il dossier deve leggere il residuo `quantity_remaining` e non azzerare la posizione.
* **F-018**: redazione del token negli URL loggati da httpx.

## 16. Stato sistema

| Voce | Valore |
|---|---|
| Ollama | **up** tutta la seduta. Downtime 0 h. Timeout di modello: 27 nel giorno (13 glm-5.3, 14 gpt-oss), 19 in seduta; grappoli 14:00–14:35 e 18:00–18:40, senza finestre di outage |
| FinBERT fallback reale | 7/222 segnali (**3,2%**). Le decisioni d'ordine su FinBERT sono 0/5 |
| Letture single-model (`fallback_used=true`) | 107/222 (48,2%) + 7 FinBERT = 114, quanto dichiarato dagli esiti task come «finbert_fallbacks» (F-078) |
| Worker restart | 06:20, 08:20, 10:02, 12:20, 21:01: Warm shutdown `worker` e `worker-inference` + restart `beat` (deploy). Job inference 1391 e 1650 persi con SIGTERM; 11:29 e 22:29 SIGKILL ForkPoolWorker (shadow, TimeLimitExceeded 840 s). **Nessun restart in seduta** |
| WS news | 69 «connection limit exceeded» (auth) sui riavvii; nessun buco di ingest in seduta |
| Redis / Postgres | nessun MISCONF o errore di connessione nei log |
| Alert | `portfolio_cycle_late` 13:30–14:08 critical; `broker_stale` 08:13 e 09:02 critical (< 1 min); 4 alert serali chiusi in 1 s; 2 Telegram 400 |
