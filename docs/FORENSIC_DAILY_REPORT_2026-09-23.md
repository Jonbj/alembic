# Forensic Daily Report — 2026-09-23

Sessione forense autonoma, sola lettura (eseguita il 2026-09-30). Fuso operativo **UTC** (`src/workers/celery_app.py`,
`timezone="UTC"`, `enable_utc=True`): tutti i timestamp di questo report sono UTC. Seduta RTH 13:30–20:00 UTC (EDT).
Conto **paper** verificato, non assunto: `ALPACA_BASE_URL=https://paper-api.alpaca.markets` e
`portfolio_monitor_snapshots.broker_environment='paper'` su 84/84 istantanee della giornata.

Periodo di **sola osservazione** (`docs/evidence/OBSERVATION_CHARTER.md`, scadenza 2026-09-28). Nessuna taratura
proposta. I ticket riguardano solo difetti di correttezza o di strumentazione.

Contesto di deploy: alle **10:08** i worker (`worker`, `worker-inference`, `beat`) sono stati ricreati dopo il merge
della PR #647 (solo artefatti documentali #539, nessun cambio di comportamento). È la seconda seduta con GLM-5.3.
Per lo stesso giorno esiste già `docs/ALPHA_MISS_REPORT_2026-09-23.md`, che ha registrato F-013, F-030 e F-031 con
costo. Qui quegli episodi sono agganciati con `costo_usd: null` per non contarli due volte.

---

## 1. Executive summary

La pipeline ha girato end-to-end: 214 righe scorate (198 Benzinga WS/REST + 16 GDELT) → 214 segnali → 24 cicli
portfolio (14:07–19:52) → 2 SELL e 2 BUY S4, tutti `filled` sul conto paper. Nessun ordine fuori orario, duplicato,
senza segnale o su dati stale. L'idempotenza regge (20 `SKIP_IDEMPOTENCY`). Ollama è rimasto su tutta la seduta:
11 timeout in seduta e 1 fallback FinBERT reale (0,5%). NAV 110.038 → 109.885 $ (**−153,40 $, −0,14%**) contro
SPY −0,72%. S4 chiude circa **−54 $** close-to-close. Il realizzato è −58,71 $ (BABA −68,67 da ieri, META +9,96).

Due difetti già noti hanno cambiato il book anche oggi. (1) Sei posizioni S4 che stanno nel target congelato di S1
(INTC, MRVL, XLE, QQQ, MU, PANW) ricevono un segnale fresco sotto gate e **non escono**. BABA e META, fuori da quel
target, escono alla stessa regola. Tenerle ha reso +75,92 $, ma non è la regola S4 (F-089). (2) I pesi d'ensemble
restano 0,5/0,5 invece dei 0,7/0,3 dichiarati nel charter (103/103 segnali riprodotti). Oggi questo **cambia un
ordine**: con 0,7/0,3 il BUY META delle 18:07 (0,315 → 0,282) non parte e il rientro slitta alle 19:52.
Costo stimato 9,02 $ (F-088). Le letture a modello singolo salgono al **51,4%** dei segnali (35,3% il 22/09).

## 2. Verdict

**Anomalie significative.**

Il percorso del denaro è corretto: ogni ordine ha segnale, gate, risk check e fill riconciliato. Ma la P&L S4 del
giorno dipende ancora da posizioni la cui uscita S4 è disarmata (F-089), e da oggi la serie degli score a pesi non
dichiarati produce ordini diversi da quelli che il charter descrive (F-088). Nessuno dei due richiede di fermare il
sistema. Entrambi vanno dichiarati prima della sintesi di fine osservazione (28/09).

---

## 3. Timeline del 2026-09-23 (UTC)

| Ora | Componente | Evento | Esito | Fonte |
|---|---|---|---|---|
| 00:00–13:29 | `worker-news-stream` | WS Benzinga 24/7; 105 dispatch `run_sentiment_worker` | tutti `skipped: market_closed` | `worker-inference-2026-09-23.log` |
| 02:07–21:07 | ingest | 560 `duplicate_id` WS fuori seduta | scartati | `news_queue_drops` |
| 07:00:03 | `detect_regime` | FRED `VIXCLS` → **500** | task `succeeded … None` (F-017); `api_key` in chiaro nel log | log inference |
| 07:43–07:55 | alert | `pipeline:broker_stale` critical (snapshot 300 s) | rientrato da solo in 12 min, fuori seduta | `mobile_events` |
| 10:08 | deploy | PR #647 (docs) → Warm shutdown `worker`/`worker-inference`, restart `beat` | job 19420 (inference) perso con SIGTERM | log |
| 10:28–10:29 | `sentiment_shadow` | SoftTimeLimit → TimeLimitExceeded(840) → **SIGKILL** ForkPoolWorker-1, lotto di 12 item perso | turno prosegue | log inference |
| 13:30:00 | alert | `pipeline:portfolio_cycle_late` critical + `signal_stale` warning | aperti | `mobile_events` |
| 13:30:58 | `detect_regime` | secondo giro | SIDEWAYS ×0,7 | log inference |
| 13:34–13:49 | sentiment | drena la coda notturna: **196 stale** + 53 not_tradable | scartati | `news_queue_drops` |
| 13:34:56 | sentiment | primo segnale | — | `sentiment_signals` |
| 13:47 | sentiment | BABA −0,007 (roundup pre-market che cita BABA −3,4%) | diventa l'ultimo segnale BABA | log/decisione 40349 |
| 13:58:42 | sentiment | META +0,285 (ensemble), 14:11 META +0,101 | sotto gate | 12243 |
| **14:07:00** | `portfolio-cycle` | **primo ciclo, 37 min dopo l'apertura** | «Exit hysteresis (2 cycles): ['BABA','META']» | `portfolio_cycles`, log |
| 14:07:04 | S4 gate | CSCO SKIP_STALE (−0,294 del 22/09, 20 h) | posizione S4 tenuta | decisione 40225 |
| 14:07:07 | Telegram | alert #161 (AMAT −21,3%, WDC −15,6% scoperte) | **400 Bad Request** | log worker |
| **14:22:00** | S4 → broker | **SELL BABA** 12,3415 (−0,007) e **SELL META** 1,9489 (+0,101), `below_entry_gate` | filled @110,86 e @744,21 | decisioni 40349/40350, trade 1024/1025 |
| 14:22:07 | Telegram | secondo alert #161 | **400** | log |
| 14:29:22 | sentiment | BABA −0,420 (single gpt-oss, GDELT «Alibaba Falls 4%…») | già fuori | 12269 |
| 13:51–15:14 | sentiment | segnali freschi sotto gate su INTC, MRVL, XLE, QQQ, MU (posizioni S4 nel target S1) | **nessuna SELL** (DAY-001) | `sentiment_signals` |
| 16:19:32 | sentiment | **BA +0,315** (glm 0,6/0,65, gpt 0,4/0,6) | sopra gate | 12338 |
| **16:22:00** | S4 → broker | **BUY BA** 7,1904 @201,86 | filled 16:22:06 | decisione 41198, trade 1026 |
| 16:37:07 | stop sync | stop BA qty 7 su 7,1904 (97,4%), un ciclo dopo l'ingresso | `new`, poi cancellato | ordine `61bb2af0` |
| 16:41:45 | FinBERT | unico fallback reale (NVDA, Ollama timeout, body_chars 458) | +0,015 | `finbert_fallback_events` 28 |
| 17:11–17:16 | sentiment | IWM −0,375, NVDA −0,345, PLTR −0,318, **QQQ −0,333**, PANW −0,228 | RANK_LONG_ONLY; QQQ/PANW S4 tenute | 12364–12369 |
| 17:46:24 | sentiment | **BP +0,375** | SKIP_PYRAMIDING ×9 dalle 17:52 (S1 a libro) | 12382, decisione 41858 |
| 17:57:45 | sentiment | MCD −0,405 («Admits It Is 'Falling Short'») | RANK_LONG_ONLY | 12387 |
| 18:05:54 | sentiment | **META +0,315** (a 0,7/0,3 sarebbe 0,282) | sopra gate | 12390 |
| **18:07:00** | S4 → broker | **BUY META** 1,935 @750,152 (5,94 $/az. sopra l'uscita delle 14:22) | filled 18:07:07 | decisione 41969, trade 1027 |
| 18:07:07 | stop sync | stop META **qty 1 su 1,935 (51,7%)** | `new` | ordine `541c314b` |
| 19:06:17 | sentiment | TSM +0,455 (single gpt-oss; glm 0,15/0,35 sotto floor) | SKIP_FALLBACK | 12417 |
| 19:52:00 | `portfolio-cycle` | ultimo ciclo; META 12436 +0,335 → SKIP_PYRAMIDING | — | decisione 42719 |
| 20:00:00 | snapshot | NAV 109.884,88 $, **−153,40 $**, 46 posizioni | — | `portfolio_monitor_snapshots` |
| 20:07–21:52 | `portfolio-cycle` | 8 cicli fuori seduta senza esito | no-op | log worker |
| 21:00:00 | `decay_monitor` | 8 righe **DECAY CRITICAL** (S1/S2/S4 stesso IC −0,041) | solo log | log worker |
| 21:35:02 | `reconcile-positions` | 45 `fully_held` + 1 `partially_wound_down_coheld` (UNH), **anomalies: 0** | — | log worker |
| 22:50:00–01 | alert | `portfolio_cycle_session_grid` (open gap 37,0 min) + `held_no_news_loss` SBUX/VALE/WDC | **aperti e chiusi in 1 s** | `mobile_events` |
| 23:05:00 | Telegram | alert serale | **400 Bad Request** | log worker |

---

## 4. News ingest

### 4.1 Per fonte

| Fonte | Trasporto | Estrazione | Righe scorate | Articoli distinti | Ticker | Prima–ultima riga | Lag pub→riga mediano / p90 | Fetched (stats) | Duplicati (stats) | Scartati |
|---|---|---|---|---|---|---|---|---|---|---|
| alpaca_benzinga | ws 195 / rest 3 | source_metadata | 198 | 129 | 50 | 13:34:56–19:51:55 | 5,7 min / 61,1 (ws) | 1.555 | **6.525** | 436 stale, 232 not_tradable |
| gdelt_gkg | — | org_lookup | 16 | 16 | 11 | 14:29:22–19:48:23 | 2,7 min / 22,6 | 2.118 | 3 | 2.099 no_ticker, 3 duplicate_content |

* Nessun timestamp futuro (`published_at > created_at`: 0). Nessun `discarded_reason` sulle righe scorate.
* Corpi Benzinga tutti presenti. **Corpi GDELT = titolo in 16/16 righe.**
* Fan-out: 145 articoli distinti → 214 righe; **34 articoli multi-ticker generano 103 righe (48,1%)**, massimo 9.
* Copie sindacate GDELT: la notizia del leak dei deal Morgan Stanley entra 4 volte su MS con `content_hash` diversi (DAY-014).
* Stale: 196 dalla coda notturna WS (13:34–13:49, età mediana 5,6 h) e 240 `transport=rest` in seduta (età mediana 4,2 h, backfill di articoli vecchi).
* Entità HTML in `news_log`: 64/198 righe Benzinga (il path Benzinga persiste il grezzo, vedi charter). L'unico input
  FinBERT del giorno non ne contiene. Il testo effettivamente passato agli LLM non è persistito → non verificabile qui.
* Copertura (dossier): 42/96 simboli di watchlist senza righe `news_log`, effective-timely 40/96; 54 simboli con almeno un segnale.
* Nessun buco temporale in seduta: righe scorate in ogni ora 13–19. Nessun errore fonte nei log (a parte il limite SIP del benchmark, §10).

### 4.2 Per ticker (top 16 per righe)

| Ticker | Righe | Ensemble | Single/FinBERT | Max | Min | Ultimo |
|---|---|---|---|---|---|---|
| SPY | 29 | 6 | 23 | +0,120 | −0,330 | +0,008 |
| AMZN | 15 | 7 | 8 | +0,090 | −0,244 | +0,003 |
| META | 15 | 10 | 5 | +0,335 | −0,180 | +0,335 |
| NVDA | 13 | 5 | 8 | +0,125 | −0,345 | −0,120 |
| GOOGL | 13 | 8 | 5 | +0,175 | −0,240 | −0,010 |
| MSFT | 10 | 6 | 4 | +0,250 | −0,080 | −0,060 |
| AAPL | 9 | 6 | 3 | +0,026 | −0,210 | −0,066 |
| MU | 7 | 2 | 5 | +0,240 | −0,266 | −0,240 |
| MCD | 7 | 5 | 2 | +0,120 | −0,405 | −0,360 |
| TSLA | 7 | 3 | 4 | +0,193 | −0,060 | 0,000 |
| PLTR | 6 | 2 | 4 | +0,140 | −0,318 | −0,318 |
| MS | 5 | 2 | 3 | 0,000 | −0,150 | 0,000 |
| QQQ | 4 | 3 | 1 | +0,013 | −0,333 | −0,030 |
| BABA | 4 | 3 | 1 | +0,236 | −0,420 | 0,000 |
| PANW | 4 | 3 | 1 | +0,200 | −0,228 | +0,044 |
| COST | 3 | 0 | 3 | +0,040 | −0,150 | −0,150 |

### 4.3 Top news per impatto sul segnale

| Segnale | Ticker | Score | News | Esito |
|---|---|---|---|---|
| (13:47) | BABA | −0,007 | roundup pre-market multi-ticker (cita BABA −3,4%) | SELL BABA 14:22, −68,67 $ net (DAY-007) |
| (14:11) | META | +0,101 | «What's Going On With Meta Platforms Stock Wednesday?» | SELL META 14:22, +9,96 $ (DAY-003) |
| 12338 | BA | +0,315 | SPEEA labor deal + ordine Turkish Airlines | BUY 16:22, mtm −13,88 $ (DAY-004) |
| 12390 | META | +0,315 | «Meta Platforms: 4 Reasons Why This Analyst Is Bullish On Muse» | BUY 18:07, mtm −11,71 $ (DAY-002/003) |
| 12382 | BP | +0,375 | «BP Stock Gains Amid JPMorgan Upgrade, Oil Rally» | SKIP_PYRAMIDING ×9 (DAY-005) |
| 12387 | MCD | −0,405 | «McDonald's Admits It Is 'Falling Short' On Execution» | RANK_LONG_ONLY (DAY-008) |
| 12417 | TSM | +0,455 | single gpt-oss | SKIP_FALLBACK (DAY-009) |

**Confidenza dell'analisi ingest: alta** per volumi, fonti e fan-out (letture dirette dal DB). Media sulla copertura
(metrica del dossier, non ricalcolata).

---

## 5. Performance modelli LLM

| Modello | Risposte | Eleggibili (flag) | Sotto floor 0,40 | Conf. mediana | Polarity media | Pos/Neg/Zero | Timeout (log, giorno / seduta) |
|---|---|---|---|---|---|---|---|
| glm-5.3:cloud | 206 | 43 | **157 (76,2%)** | 0,30 | −0,005 | 88/84/34 | 15 / 6 |
| gpt-oss:20b-cloud | 211 | 43 | 67 (31,8%) | 0,45 | −0,024 | 87/83/41 | 16 / 5 |

| Tipo segnale | Righe | % | Score medio | Min | Max | Sopra gate \|0,30\| | `ensemble_std`=0 |
|---|---|---|---|---|---|---|---|
| ensemble glm-5.3+gpt-oss | 103 | 48,1% | −0,004 | −0,405 | +0,375 | 11 | 33 |
| single gpt-oss (fallback_used) | 102 | 47,7% | −0,022 | −0,420 | +0,455 | 5 | 23 |
| single glm-5.3 (fallback_used) | 8 | 3,7% | −0,039 | −0,220 | +0,140 | 0 | 4 |
| finbert (reale) | 1 | 0,5% | +0,015 | — | — | 0 | 1 |

* **Latenza**: nessuna telemetria per chiamata (F-086). Dai log: 130 task sentiment in seduta, 74 con item (214 item);
  durata mediana 141,4 s, **per-item mediana 61,2 s**, 9 task > 300 s, max 623,5 s. Pubblicazione→segnale Benzinga
  mediana 5,7 min, p90 62,6 min; `raw_ingested_at`→segnale mediana 295 s (DAY-012).
* **Refusal/invalid output**: nessun parse-fail nei log. Timeout: 31 nel giorno, 11 in seduta. Nessuna finestra di outage.
* **Disaccordo**: su 204 segnali con due risposte, 10 a segni opposti e 16 con spread ≥ 0,30. Esempio TSM 12417:
  gpt-oss +0,65/0,70, glm +0,15/0,35 (sotto floor) → single +0,455, `ensemble_std` 0,354 (DAY-010).
* **Pesi effettivi**: 0,5/0,5. Score riprodotto a pesi uguali su **103/103** segnali ensemble; 143 WARNING «Ignoring
  weights for inactive sentiment models: ['glm-5.2:cloud']». Con 0,7/0,3 cambia lato gate solo META 12390 (DAY-002).
* **Dominanza di un modello**: 110 segnali su 214 sono lettura di un solo modello (gpt-oss in 102). Nei 60 ensemble
  senza nessun `eligible=true` entrambi i modelli contribuiscono via retry a floor 0 (DAY-011).
* **Fallback FinBERT reale**: 1 (NVDA 16:41, «Ollama timeout», `title_chars` 52, `body_chars` 458 > 0: FinBERT ha visto
  parte del corpo; nessuna entità HTML nell'input). Gli esiti task dichiarano **111** `finbert_fallbacks` (DAY-009).
* **Verifica funzionale**: l'output passa per `aggregate()` con floor di confidenza e retry; la varianza è misurata
  (`ensemble_std`) ma non è un gate (F-037/F-054). Le news duplicate tra copie sindacate GDELT pesano più volte
  (DAY-014). Uno stesso articolo genera segnali su più ticker (fan-out, DAY-013). Confidenza bassa riduce il peso
  (`_w = confidence × weight`) e lo score (× confidenza media). I modelli girano solo nel `worker-inference` (coda
  `inference`); il ciclo portfolio legge `sentiment_signals` dal DB → nessuna chiamata LLM nel percorso ordini.
  Il rischio hallucination resta: un singolo LLM (gpt-oss) può produrre da solo uno score sopra gate, che oggi è
  però escluso dal ranking BUY (`SKIP_FALLBACK`, 237 intenti).

---

## 6. Segnali finali per ticker (quelli che hanno toccato il gate o un ordine)

| Ticker | Segnale | Ora | Score | Tipo | Destino |
|---|---|---|---|---|---|
| BABA | (13:47) | 13:47 | −0,007 | ensemble | uscita `below_entry_gate` → **SELL 14:22** |
| META | 12243 / (14:11) | 13:58 / 14:11 | +0,285 / +0,101 | ensemble | uscita `below_entry_gate` → **SELL 14:22** |
| BABA | 12269 | 14:29:22 | −0,420 | single gpt-oss | già fuori; long-only |
| SPY | 12273 | 14:34:16 | −0,330 | single gpt-oss | sovrascritto 1 min dopo (−0,090) |
| GS | 12326 | 16:01:04 | −0,300 | single gpt-oss | long-only |
| BA | 12338 | 16:19:32 | +0,315 | ensemble | **BUY 16:22** |
| IWM / NVDA / QQQ | 12364/12366/12369 | 17:11–17:15 | −0,375/−0,345/−0,333 | ensemble | RANK_LONG_ONLY (QQQ S4 a libro: tenuta) |
| PLTR | 12368 | 17:15:36 | −0,318 | ensemble | SKIP_ENTRY_GATE/long-only |
| BP | 12382 | 17:46:24 | +0,375 | ensemble | SKIP_PYRAMIDING ×9 (S1 dal 09-01) |
| MCD | 12387/12398/12431 | 17:57–19:44 | −0,405/−0,331/−0,360 | ensemble | RANK_LONG_ONLY |
| META | 12390 | 18:05:54 | +0,315 | ensemble | **BUY 18:07** |
| LLY | 12402 | 18:30:46 | +0,300 | single gpt-oss (GDELT) | SKIP_FALLBACK |
| TSM | 12417 | 19:06:17 | +0,455 | single gpt-oss | SKIP_FALLBACK |
| META | 12436 | 19:49:42 | +0,335 | ensemble | SKIP_PYRAMIDING (S4 già a libro) |

Disposizioni S4 (`s4_intent_events`, per `decision_slot`): 1.851 candidati; SKIP_ENTRY_GATE 684, SKIP_ENTRY_FRESHNESS 651,
SKIP_FALLBACK 237, SKIP_STALE 179, **SKIP_PYRAMIDING 55** (contro **2** righe `execution_decisions`), RANK_LONG_ONLY 23,
SKIP_IDEMPOTENCY 20, SUBMITTED 2. Nessun RANK_OUTSIDE_TOP_N. SKIP_PYRAMIDING su segnali di giorni prima: NOW 11920
(21/09) ×24, SOXX 12117 (22/09) ×12, GM 11807 (21/09) ×9.

---

## 7. Ordini generati/eseguiti

| Decisione | Strategia | Ticker | Azione | Qty | Prezzo atteso | Fill | Stato | Broker | Rationale | Segnale | Risk check | Anomalie |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 14:22:00 (40349) | S4 | BABA | SELL | 12,3415 | n/d (`decision_price` NULL) | 110,86 | filled 14:22:09 | Alpaca paper | `below_entry_gate` su −0,007 (13:47), isteresi 2 cicli | NULL | isteresi; stop 92b18075 cancellato | uscita da roundup multi-ticker (F-008, esito favorevole), `signal_id` NULL |
| 14:22:00 (40350) | S4 | META | SELL | 1,9489 | n/d | 744,21 | filled 14:22:08 | Alpaca paper | `below_entry_gate` su +0,101 | NULL | isteresi; stop 81142bf6 cancellato | SELL con sentiment positivo, ricomprata alle 18:07 (F-013) |
| 16:22:00 (41198) | S4 | BA | BUY | 7,1904 | n/d | 201,86 | filled 16:22:06 | Alpaca paper | +0,315, peso 2,0%, regime 0,7 | 12338 | gate 0,30, top-N, P0-05, idempotenza | ingresso a movimento avvenuto (F-030) |
| 16:37:07 | S4 stop | BA | SELL stop | 7 | — | — | new → canceled (24/09) | Alpaca paper | stop protettivo | — | — | 97,4%, un ciclo dopo l'ingresso (F-022) |
| 18:07:00 (41969) | S4 | META | BUY | 1,935 | n/d | 750,152 | filled 18:07:07 | Alpaca paper | +0,315, peso 2,0% | 12390 | gate, top-N, P0-05 | a pesi 0,7/0,3 non sarebbe partito (F-088); rientro +5,94 $/az. (F-013) |
| 18:07:07 | S4 stop | META | SELL stop | 1 | — | — | new → canceled (24/09) | Alpaca paper | stop | — | — | **51,7%** di copertura (F-022) |

Nessun ordine S1 (gate di ribilanciamento chiuso, ultimo ribilanciamento 2026-09-01). `orders_before_constraints` 2–5
per ciclo contro `submitted` 0–2 (4 in tutto) (F-014).

---

## 8. PnL / rendimento

Prezzi: `docs/evidence/dossier/2026-09-23.json` (Alpaca SIP, `adjustment=all`) e barre al minuto Alpaca SIP (sola lettura).
Close-to-close 22/09 → 23/09.

| Voce | Ticker | Qty | Da → A | $ | Tipo |
|---|---|---|---|---|---|
| Realizzato (aperta 22/09) | BABA #1024 | 12,3415 | 116,36 → 110,86 | **−68,67** net (di cui −67,26 maturati oggi da 116,31) | realizzato |
| Realizzato (aperta 22/09) | META #1025 | 1,9489 | 738,95 → 744,21 | **+9,96** net (+14,84 oggi da 736,60) | realizzato |
| Aperta oggi | BA #1026 | 7,1904 | 201,86 → 199,93 | −13,88 | non realizzato |
| Aperta oggi | META #1027 | 1,935 | 750,152 → 744,10 | −11,71 | non realizzato |
| Pre-esistente S4 | PANW | 3,8762 | 374,57 → 393,30 | +72,60 | non realizzato |
| Pre-esistente S4 | XLE | 22,0056 | 61,78 → 62,37 | +12,98 | non realizzato |
| Pre-esistente S4 | NOW | 2,9791 | 137,00 → 140,78 | +11,26 | non realizzato |
| Pre-esistente S4 | WDC | 0,3347 | 464,60 → 473,69 | +3,04 (il dossier la riporta a qty 0, DAY-016) | non realizzato |
| Pre-esistente S4 | CSCO | 17,1357 | 106,44 → 106,43 | −0,17 | non realizzato |
| Pre-esistente S4 | MRVL | 6,3743 | 262,36 → 260,90 | −9,31 | non realizzato |
| Pre-esistente S4 | QQQ | 2,0745 | 747,46 → 741,21 | −12,97 | non realizzato |
| Pre-esistente S4 | INTC | 14,5237 | 123,86 → 122,60 | −18,30 | non realizzato |
| Pre-esistente S4 | MU | 1,4634 | 1096,16 → 1071,88 | −35,53 | non realizzato |
| **S4 giornata** | | | | **≈ −54,4** (costi esclusi; `cost_usd` modellato 2,17 $) | |
| S1 giornata | | | | ≈ −102,9 (close-to-close sul `snapshot_apertura`) | |
| **Book (broker)** | | | 110.038,28 → 109.884,88 | **−153,40** (snapshot 20:00; Alpaca history 109.882,53) | equity |

* Riconciliazione: S4 −54,4 + S1 −102,9 = −157,3 contro −153,4 del book. Lo scarto di 3,9 $ viene da snapshot delle
  20:00 contro close ufficiale e dai costi. Benchmark: SPY −0,72%, QQQ −0,84%. Il book batte SPY perché è esposto al
  36% e sovrappesa energy/software.
* Per strategia: S4 ≈ −54 $, S1 ≈ −103 $. La S4 senza le 6 posizioni nel target S1 (vendute alla regola) avrebbe fatto
  circa −130 $ (DAY-001).
* Slippage: non misurabile. `decision_price` è NULL sulle 4 decisioni d'ordine e `slippage_est` copia `cost_usd` (F-015).
  Proxy segnale/ciclo→fill: BA 201,77 (barra 16:22) → 201,86 (+0,04%); META 749,89 (18:07) → 750,15 (+0,03%);
  BABA 110,90 (14:22) → 110,86; META 744,83 → 744,21 (−0,08%).
* Commissioni: 0 (Alpaca). `cost_usd` modellato: 0,79 + 0,29 + 0,80 + 0,29 = 2,17 $.
* `/api/trades` mostra la SELL META delle 14:22 con `entry_price` 750,152 (quello del BUY delle 18:07) e `gross_pnl`
  **−11,58**, mentre il ledger `trades` dice +10,25 (DAY-017).

---

## 9. Correttezza buy/sell

| Controllo | Esito | Nota |
|---|---|---|
| BUY solo quando consentito | ✅ | 2 BUY, entrambi ensemble ≥ 0,30, top-N, P0-05 e idempotenza verificati |
| SELL/exit corretti | ⚠️ | BABA e META escono secondo la regola dichiarata. **6 posizioni S4 nel target S1 con segnale fresco sotto gate non escono** (DAY-001) |
| Stop-loss | ⚠️ | nessuno scattato. Coperture BA 97,4% (un ciclo dopo), META **51,7%**. AMAT −21%, WDC −16% senza stop (sub-one-share) |
| Signal flip | ⚠️ | QQQ −0,333 e PANW −0,228 su posizioni S4 senza uscita (DAY-001) |
| Max holding days | ❌ | WDC 64 giorni, CSCO 29, XLE 23 (DAY-001, F-025) |
| Rebalance band | ⚠️ | nessuna banda fra gate 0,30 e uscita: META SELL a +0,101 e ri-BUY 3h45 dopo a +0,315 (DAY-003) |
| Ordini duplicati | ✅ | nessuno. 20 `SKIP_IDEMPOTENCY` |
| Ordini contrari ravvicinati senza rationale | ⚠️ | META SELL 14:22 → BUY 18:07, entrambi con rationale ma è churn |
| Ticker non consentiti | ✅ | tutti in watchlist |
| Fuori orario | ✅ | fra 14:22 e 18:07; 8 cicli dopo la chiusura sono no-op |
| Dati stale | ✅ | 179 SKIP_STALE, 651 SKIP_ENTRY_FRESHNESS; CSCO tenuta dal preserve-stale (F-025) |
| LLM output non valido | ✅ | nessun parse-fail. Single-model esclusi dal ranking BUY |
| Circuit breaker | ✅ | nessun breaker attivo. Loss-feedback S4 non scattato |
| Strategia disabilitata | ✅ | S1+S4 attive, `execution.engine=portfolio` |
| Paper/live | ✅ | paper verificato (URL e 84 snapshot) |
| Idempotenza retry Celery | ✅ | nessun doppio invio; nessun retry dei task portfolio |
| Riconciliazione | ⚠️ | 45/46 al centesimo. UNH ledger 1,5926 vs broker 0,5926, «anomalies: 0» (DAY-016) |

Pattern specifici:
* Roundtrip < 30 min: **nessuno**.
* Pyramiding > 3 BUY: **nessuno**.
* SELL con sentiment positivo: **sì**, META +0,101 (DAY-003).
* `fallback_used=True` su tutti i simboli: **no**. Ollama è rimasto su tutta la seduta; il 51,4% di letture single è floor, non outage.
* NO-ORDER: **no** (4 decisioni, 4 ordini).
* Score < 0,05 che genera ordine: **SELL BABA su −0,007**, uscita per regola (DAY-007).
* Ordini identici nello stesso minuto: **no**. Le due SELL delle 14:22 sono su simboli diversi.

`exit_mechanism`: le due righe del 23/09 (`below_entry_gate`) sono **post-#184**, cioè disposizioni osservate e non
stime per età. `trades.exit_reason` dice `portfolio_sell` per le stesse uscite: è un vocabolario diverso, non una
contraddizione.

---

## 10. Anomalie trovate

### [DAY-001] Sei posizioni S4 nel target congelato di S1 ricevono un segnale fresco sotto gate e non escono

* Tipo: Bug
* Area: Signal / Orders / Risk
* Evidenza:
  * file/log/tabella: `sentiment_signals`; `execution_decisions`; `trades`; barre Alpaca SIP 1 min; dossier `snapshot_apertura`
  * timestamp: 13:44–17:15
  * snippet/query:
    ```
    INTC 12238 -0,035 (13:51) · MRVL 12233 0,000 (13:44) · XLE 12250 +0,018 (14:04)
    QQQ 12266 -0,156 (14:27), 12369 -0,333 (17:15) · MU 12311 +0,203 (15:14) · PANW 12367 -0,228 (17:13)
    execution_decisions QQQ: SKIP_THRESHOLD x13, OBSERVE_LATE_ENTRY x24 — nessuna SELL
    BABA e META (fuori dal target S1): "Exit hysteresis (2 cycles) ... ['BABA','META']" 14:07 → SELL 14:22
    ```
* Descrizione: è lo stesso meccanismo del 22/09. Il combiner somma il peso S1 congelato al 01/09, che contiene simboli
  comprati da S4, quindi la regola `below_entry_gate` non riesce a portarli a zero. BABA e META escono alla stessa
  regola nello stesso ciclo. CSCO (ultimo segnale −0,294 del 22/09) resta per preserve-stale.
* Impatto: vendita al secondo ciclo dopo il primo segnale fresco sotto gate, contro il close. INTC 14:22 @119,94
  +38,63 · MRVL 14:22 @257,22 +23,46 · XLE 14:22 @62,84 −10,34 · QQQ 14:52 @740,70 +1,06 · MU 15:37 @1075,64 −5,50 ·
  PANW 17:37 @385,92 +28,61. Tenerle ha reso **+75,92 $** (costo −75,92, attribuito). La P&L S4 del giorno (≈ −54 $)
  sarebbe circa −130 $ alla regola dichiarata.
* Severità: High
* Confidenza: High sul meccanismo. Medium sul costo (isteresi approssimata a 2 cicli, prezzo = open della barra).
* Azione consigliata: il ticket di correttezza del 22/09 resta valido (quota S4 separata dal target S1). Prima della
  sintesi va dichiarato nel charter che la P&L S4 di queste posizioni non è P&L della regola S4.
* Test/monitor consigliato: monitor giornaliero «posizioni S4 nel target S1 con segnale fresco sotto gate e nessuna SELL».
* → ledger **F-089**

### [DAY-002] Pesi d'ensemble ancora 0,5/0,5: oggi il BUY META delle 18:07 esiste solo per questo

* Tipo: Bug
* Area: LLM / Signal / Orders
* Evidenza:
  * file/log/tabella: `worker-inference-2026-09-23.log`; `sentiment_signals` × `llm_responses`; `src/llm/ensemble.py:327-334`
  * timestamp: tutta la seduta; 143 WARNING
  * snippet/query:
    ```
    WARNING Ignoring weights for inactive sentiment models: ['glm-5.2:cloud']   (x143)
    score = Σ p·c·w / Σ c·w × mean(c): pesi uguali riproducono 103/103 segnali ensemble
    0,7/0,3 → META 12390 0,315 → 0,282 (sotto gate)   META 12436 0,335 → 0,312   BA 0,315 → 0,340
    ```
* Descrizione: il difetto del 22/09 persiste. Il charter dichiara pesi «ereditati come stantii» (0,7/0,3); in realtà
  sono 0,5/0,5. Oggi la differenza tocca un ordine: senza il difetto META non si compra alle 18:07 e si compra alle
  19:52 sul segnale 12436.
* Impatto: stesso nozionale (1.451,5 $). Ingresso alle 19:52 @~745,48 → mark a close 744,10 = −2,69 $, contro il
  `mtm_eod` −11,71 $ del trade 1027. Costo **9,02 $** (attribuito). Il 24/09 il trade 1027 chiude a +31,38 $, ma è
  fuori dall'orizzonte corto.
* Severità: High per l'interpretabilità della serie · Confidenza: High sul meccanismo, Medium sul controfattuale
* Azione consigliata: correggere l'annotazione del charter (pesi effettivi 0,5/0,5 dal 22/09 07:32). Nota: oggi
  `ensemble:weights:current` contiene `{glm-5.3: 0,593, gpt-oss: 0,407, source: telegram}`. Il cambio è successivo al
  23/09 e va registrato come discontinuità con la sua data.
* Test/monitor consigliato: persistere per segnale i pesi effettivi usati.
* → ledger **F-088**

### [DAY-003] META venduta a +0,101 e ricomprata 3h45 dopo a 5,94 $/azione in più

* Tipo: Anomalia · Area: Orders / Signal
* Evidenza: `execution_decisions` 40350 («[below_entry_gate] … generated 14:11 UTC, score=+0.101»), 41969; `trades` 1025, 1027
* Descrizione: nessuna banda fra gate d'ingresso e uscita (F-013). Il costo è già registrato dall'alpha-miss del
  23/09 (11,50 $) → null qui.
* Severità: Low · Confidenza: High
* → ledger **F-013**

### [DAY-004] BA e META comprate a movimento già avvenuto

* Tipo: Anomalia · Area: News / Signal
* Evidenza: dossier `ingressi`: BA `quota_movimento_precedente_al_segnale` 1,99, `mtm_eod` −13,88; META `denominatore_degenere`, `mtm_eod` −11,71
* Descrizione: F-030. Costo già registrato dall'alpha-miss (13,88 $) → null qui.
* Severità: Medium · Confidenza: High
* → ledger **F-030**

### [DAY-005] P0-05 blocca BP +0,375 (a libro da S1) nove volte, e traccia 2 blocchi su 55

* Tipo: Anomalia · Area: Orders / Data
* Evidenza: `execution_decisions` 41858 (17:52, «gia' a libro dal 2026-09-01»), 42719 (META 19:52); `s4_intent_events` SKIP_PYRAMIDING 55; NOW/SOXX/GM su segnali di 1–2 giorni prima
* Descrizione: F-031. Costo già registrato dall'alpha-miss (−4,46 $) → null qui.
* Severità: Medium · Confidenza: High
* → ledger **F-031**

### [DAY-006] Primo ciclo alle 14:07: l'uscita BABA slitta di un ciclo

* Tipo: Anomalia · Area: Ops / Orders
* Evidenza: `portfolio_cycles` primo 14:07:00; `mobile_events` `portfolio_cycle_session_grid` open_gap 37,01 min; barre BABA 14:07 111,26 / 14:22 110,90
* Descrizione: con un ciclo alle 13:52 il segnale BABA delle 13:47 avrebbe fatto scattare l'isteresi e la vendita
  alle 14:07.
* Impatto: 12,3415 × (111,26 − 110,86) = **4,94 $** (attribuito).
* Severità: Medium · Confidenza: Medium
* → ledger **F-021**

### [DAY-007] BABA chiusa da un roundup multi-ticker con score −0,007

* Tipo: Anomalia · Area: News / Signal
* Evidenza: decisione 40349 («generated 2026-09-23 13:47 UTC, score=-0.007»); `trades` 1024
* Descrizione: il meccanismo è quello di F-008 (un articolo multi-ticker con score quasi nullo chiude una posizione
  aperta su un segnale specifico). Qui però l'esito è favorevole: il roundup riporta un −3,4% pre-market reale e il
  segnale successivo è −0,42.
* Impatto: tenendo fino al close (110,80) si perdevano altri 0,74 $ → costo **−0,74 $** (attribuito).
* Severità: Low · Confidenza: High
* → ledger **F-008**

### [DAY-008] Quattro segnali ribassisti sopra gate col segno giusto: solo RANK_LONG_ONLY

* Tipo: Anomalia · Area: Signal
* Evidenza: `s4_intent_events` RANK_LONG_ONLY: QQQ ×11, IWM ×8, MCD ×2, NVDA ×2
* Impatto: congetturale, short da 2.200 $ dal primo ciclo utile al close. MCD −7,13 · IWM +2,57 · QQQ −4,28 ·
  NVDA −9,90 = **−18,74 $**. I segnali erano retrospettivi e il vincolo long-only ha evitato una perdita.
* Severità: Low · Confidenza: Medium
* → ledger **F-040**

### [DAY-009] 51,4% dei segnali a modello singolo marcati fallback; esiti task dichiarano 111 fallback FinBERT contro 1 reale

* Tipo: Anomalia · Area: LLM / Data
* Evidenza: `sentiment_signals.model_id` `single:*` 110/214 (102 gpt-oss), 101 con due risposte a DB; somma
  `finbert_fallbacks` negli esiti task 111; `finbert_fallback_events` 1 riga. glm-5.3 sotto floor 157/206.
* Descrizione: la quota single passa da 35,3% (22/09) a 51,4%. Le letture single sono escluse dal ranking BUY: 237
  SKIP_FALLBACK, fra cui TSM +0,455 (congetturale −2,26 $, non sommato).
* Severità: Medium · Confidenza: High
* → ledger **F-078**

### [DAY-010] Disaccordo fra modelli invisibile alla guardia: 10 segni opposti, 16 spread ≥ 0,30

* Tipo: Anomalia · Area: LLM
* Evidenza: join `llm_responses` su 204 segnali a due risposte. TSM 12417 `ensemble_std` 0,354 ma single.
* Impatto: nessun ordine → costo non stimato.
* Severità: Low · Confidenza: High
* → ledger **F-054**

### [DAY-011] 60 dei 103 segnali d'ensemble senza nessuna risposta `eligible`

* Tipo: Anomalia · Area: Data / LLM
* Evidenza: join `sentiment_signals` × `llm_responses`: 60 con `eligible` 0/2, 43 con 2/2.
* Severità: Low · Confidenza: High
* → ledger **F-010**

### [DAY-012] Latenza di scoring ancora ~6× (61 s per articolo)

* Tipo: Anomalia · Area: LLM / Ops
* Evidenza: log task: per-item mediana 61,2 s, 9 task > 300 s, max 623,5 s; pub→segnale Benzinga p90 62,6 min
* Severità: Medium · Confidenza: Medium
* → ledger **F-019**

### [DAY-013] Fan-out: 48% delle righe scorate da articoli multi-ticker

* Tipo: Rischio · Area: News
* Evidenza: 145 articoli → 214 righe; 34 multi-ticker → 103 righe, massimo 9. Il roundup che ha chiuso BABA è uno di questi (DAY-007).
* Severità: Medium · Confidenza: High
* → ledger **F-012**

### [DAY-014] La stessa notizia Morgan Stanley entra quattro volte da GDELT

* Tipo: Anomalia · Area: News / Data
* Evidenza: `news_log` GDELT MS: «…staffer accidentally emails internal list…», «…accidentally leaks 100 plus deal pipeline…», «…Asia deal plans leaked…», «…employee accidentally leaks confidential Asia deal list…»; score −0,068/−0,150/−0,020/−0,080
* Descrizione: copie sindacate con `content_hash` diversi e corpo = titolo superano la dedup. Nessun ordine.
* Severità: Low · Confidenza: High
* → ledger **F-090**

### [DAY-015] Stop META al 51,7%, stop BA un ciclo dopo; AMAT e WDC senza stop

* Tipo: Rischio · Area: Risk / Broker
* Evidenza: ordini `541c314b` (META qty 1 su 1,935), `61bb2af0` (BA 7 su 7,1904, 16:37); log `#161: AMAT unprotected at -21.3%`, `WDC … -15.6%`, «10/46 held positions are unprotectable»
* Severità: Medium · Confidenza: High
* → ledger **F-022**

### [DAY-016] UNH con 1 azione di scarto e «anomalies: 0»; WDC azzerata nel dossier

* Tipo: Bug · Area: PnL / Broker
* Evidenza: `trades` 279 qty 1,592634 (`quantity_remaining` NULL) contro broker 0,592634; `trades` 373 WDC qty 2,981,
  `quantity_remaining` 0,3347, dossier `snapshot_apertura` WDC `qty_open` 0 → P&L di seduta WDC omesso (~+3,6 $ open→close)
* Severità: Medium · Confidenza: High
* → ledger **F-048**

### [DAY-017] `/api/trades` attribuisce alla SELL META il prezzo del BUY successivo: −11,58 $ invece di +10,25 $

* Tipo: Bug · Area: Frontend / PnL
* Evidenza: `/api/trades` riga `d930c3e0`: `entry_price` 750,152, `gross_pnl` −11,5802. `trades` 1025: entry 738,95,
  gross +10,25. SELL BABA `9cd644bf`: entry e P&L null. `/api/orders` lega le SELL al `signal_id`/`decision_id`
  dell'ingresso (12214/39855 invece della decisione 40350).
* Severità: Medium · Confidenza: High
* → ledger **F-084**

### [DAY-018] Le due SELL non portano `signal_id`

* Tipo: Anomalia · Area: Data
* Evidenza: `execution_decisions` 40349, 40350: `signal_id` NULL
* Severità: Low · Confidenza: High
* → ledger **F-011**

### [DAY-019] `decision_price` NULL sugli ordini, popolato sulle righe osservazionali

* Tipo: Anomalia · Area: PnL / Data
* Evidenza: `execution_decisions` 40349/40350/41198/41969 `decision_price` NULL; le righe `OBSERVE_LATE_ENTRY` dello stesso ciclo lo hanno (es. 40249 AAPL 337,97). `trades.slippage_est` = `cost_usd`.
* Severità: Low · Confidenza: High
* → ledger **F-015**

### [DAY-020] `orders_before_constraints` 2–5 contro 0–2 ordini inviati

* Tipo: Anomalia · Area: Ops
* Evidenza: esiti `run_portfolio_cycle` 14:07–19:52
* Severità: Low · Confidenza: High
* → ledger **F-014**

### [DAY-021] Decay monitor: S1, S2 e S4 con lo stesso IC (−0,041), S1 e S2 con lo stesso drawdown (13,5%)

* Tipo: Anomalia · Area: Risk
* Evidenza: log 21:00:00 `DECAY CRITICAL [S1] IC … 0.035 to -0.041`, `[S2] … 0.042 to -0.041`, `[S4] … 0.028 to -0.041`
* Severità: Medium · Confidenza: High
* → ledger **F-004**

### [DAY-022] Gli 8 DECAY CRITICAL restano nel log

* Tipo: Anomalia · Area: Ops
* Evidenza: nessuna riga `mobile_events` fra 21:00 e 21:05
* Severità: Medium · Confidenza: High
* → ledger **F-062**

### [DAY-023] Telegram 400 Bad Request su tre alert

* Tipo: Bug · Area: Ops
* Evidenza: log worker 14:07:07, 14:22:07 (alert #161), 23:05:00
* Severità: Medium · Confidenza: High
* → ledger **F-005**

### [DAY-024] Segreti in chiaro nei log: bot token Telegram e `api_key` FRED

* Tipo: Rischio · Area: Ops
* Evidenza: `worker-2026-09-23.log` (7 righe, incluse le WARNING d'errore), `worker-inference-2026-09-23.log` (a ogni
  poll Telegram; `api_key=` FRED in 4 righe, 07:00 e 13:30). Valori non riportati qui.
* Severità: Medium · Confidenza: High
* → ledger **F-018**

### [DAY-025] Benchmark SPY: 84 fetch falliti per limite SIP, nessun alert

* Tipo: Anomalia · Area: Data
* Evidenza: `SPY benchmark fetch failed` ×84 nel log worker
* Severità: Low · Confidenza: High
* → ledger **F-016**

### [DAY-026] Regime detection 07:00: FRED 500 e task «succeeded … None»

* Tipo: Anomalia · Area: Ops
* Evidenza: log inference 07:00:03 ERROR + 07:00:04 `succeeded in 4.0s: None`; il giro delle 13:30 riesce
* Severità: Low · Confidenza: High
* → ledger **F-017**

### [DAY-027] `ingestion_stats_daily`: 6.525 duplicati contro 1.555 fetched per alpaca_benzinga

* Tipo: Anomalia · Area: Data
* Evidenza: `ingestion_stats_daily` 2026-09-23; `news_queue_drops` `duplicate_id` 6.525 (5.252 rest, 1.273 ws)
* Severità: Low · Confidenza: High
* → ledger **F-007**

### [DAY-028] Quattro alert della sera aperti e chiusi nello stesso secondo

* Tipo: Bug · Area: Ops
* Evidenza: `mobile_events` `pipeline:portfolio_cycle_session_grid`, `coverage:held_no_news_loss:SBUX/VALE/WDC`: `first_observed_at` 22:50:00, `resolved_at` 22:50:01
* Severità: Medium · Confidenza: High
* → ledger **F-058**

### [DAY-029] Coda notturna WS: 196 articoli scartati stale all'apertura

* Tipo: Anomalia · Area: News / Ops
* Evidenza: `news_queue_drops` `stale` ws `enqueued_off_session=true` 196 (13:34–13:49, età mediana 5,6 h) + 53 not_tradable; 105 dispatch `market_closed`
* Severità: Low · Confidenza: High
* → ledger **F-069**

### [DAY-030] Copertura news: 42/96 simboli senza righe

* Tipo: Anomalia · Area: News
* Evidenza: dossier `no_news_backstop` 42 simboli a zero righe (DB e NVO mover); `ticker_allerta_zero_articoli` ADBE, CMCSA, HD, INFY, MMM, RIO, ROKU, SAP, SBUX, SNOW, VALE
* Severità: Medium · Confidenza: High
* → ledger **F-001**

---

## 11. False positive o aree risultate corrette

* **Paper/live**: paper su 84/84 snapshot. Nessuna ambiguità.
* **Timezone**: UTC esplicito in `celery_app.py`. Il buco delle 13:30–14:07 è F-021 (DST), non un'ambiguità di fuso.
* **Idempotenza**: 20 `SKIP_IDEMPOTENCY`, nessun doppio invio. I due ordini delle 14:22 riguardano simboli diversi.
* **Ordini senza segnale**: nessuno. I 2 BUY hanno `signal_id`; le 2 SELL hanno la causa nel `reason` (F-011 è tracciabilità, non assenza).
* **Deploy 10:08**: PR #647 solo documentale; nessun effetto sul comportamento in seduta.
* **Ollama**: nessun outage. 11 timeout in seduta, 1 fallback FinBERT reale.
* **Uscita BABA**: F-008 come meccanismo, ma corretta nel merito (−0,74 $ evitati; segnale successivo −0,42).
* **F-023 (ultimo segnale vince)**: nessun segnale sopra gate sovrascritto con effetto d'ordine. NVDA −0,345 e SPY
  −0,330 sono stati sovrascritti prima del ciclo, ma erano ribassisti (long-only).
* **F-043**: contraddetto oggi. Ci sono segnali ribassisti ensemble sopra gate (MCD, IWM, NVDA, QQQ, PLTR).
* **F-076**: l'input FinBERT del giorno è privo di entità HTML. Il testo passato agli LLM non è persistito, quindi il
  fix non è verificabile oltre questo punto.
* **Riconciliazione**: 45/46 posizioni coincidono col broker. Le posizioni correnti di `/api/positions` (30/09) non
  valgono per il 23/09 e non sono state usate.
* **Timestamp futuri**: nessuno.

## 12. Dati mancanti o non accessibili

* Latenza e esito per singola chiamata Ollama (F-086): ricostruiti solo dai log dei task.
* Testo effettivamente inviato agli LLM (prompt sanitizzato): non persistito.
* Pesi effettivi per segnale: non persistiti. Ricostruiti riproducendo lo score.
* `canceled_at` degli stop: `/api/orders` non lo espone (solo `status`).
* `decision_price` per le decisioni d'ordine: NULL. Lo slippage è stimato solo col proxy della barra al minuto.
* `economic_pnl.json` fermo al 17/09 (vedi alpha-miss §2): i cumulati di carta non includono questa seduta.
* Query utile, non eseguita perché fuori ambito: P&L per sleeve della quota S4 dentro il target S1 sulla finestra intera,
  `trades` × `strategy:rebalance_state:S1`.

## 13. Raccomandazioni immediate

1. **Charter** (correzione di strumento, non taratura): dichiarare che (a) la P&L S4 delle posizioni nel target S1
   congelato non è P&L della regola S4 (F-089) e (b) i pesi effettivi sono 0,5/0,5 dal 22/09 07:32 fino al cambio
   `source: telegram` successivo (F-088), con la data esatta di quel cambio.
2. Non leggere `/api/trades` per il P&L dei roundtrip: usare il ledger `trades` (F-084).
3. Ruotare il bot token Telegram e la chiave FRED, entrambi presenti in chiaro nei log persistenti (F-018).

## 14. Test o monitor da aggiungere

* Monitor «posizioni S4 nel target S1 con segnale fresco sotto gate e nessuna SELL» (F-089).
* Persistenza per segnale dei pesi effettivi e delle risposte eleggibili (F-088, F-010).
* Contatore giornaliero della quota di segnali single-model per modello escluso, confrontato con `finbert_fallback_events` (F-078).
* Test di `/api/trades` con SELL seguita da un BUY sullo stesso simbolo nella stessa seduta (F-084).
* Test del dossier con posizione a uscite parziali (`quantity_remaining` < `qty`): `qty_open` deve essere il residuo (F-048).

## 15. Ticket tecnici suggeriti (solo correttezza)

* **F-089**: separare la quota S4 dal target congelato S1 nel combiner (già proposto il 22/09).
* **F-088**: una rinomina di `model_id` deve migrare o invalidare in modo esplicito i pesi, invece di cadere sul default con un WARNING.
* **F-084**: `/api/trades` e `/api/orders` devono esporre il ledger `trades` e la decisione d'uscita, non l'ordine broker accoppiato all'ingresso.
* **F-048**: il dossier deve leggere il residuo `quantity_remaining` e non azzerare la posizione.
* **F-018**: redazione del token negli URL loggati da httpx.

## 16. Stato sistema

| Voce | Valore |
|---|---|
| Ollama | **up** tutta la seduta. Downtime 0 h. Timeout: 31 nel giorno (15 glm-5.3, 16 gpt-oss), 11 in seduta; nessuna finestra consecutiva |
| FinBERT fallback reale | 1/214 segnali (**0,5%**). Le decisioni d'ordine su FinBERT sono 0/4 |
| Letture single-model (`fallback_used=true`) | 110/214 (51,4%); esiti task dichiarano 111 «finbert_fallbacks» (F-078) |
| Worker restart | 10:08 Warm shutdown `worker` e `worker-inference` + restart `beat` (deploy PR #647); job 19420 perso con SIGTERM; 10:29 SIGKILL ForkPoolWorker-1 (shadow, TimeLimitExceeded 840 s). Nessun restart in seduta |
| Redis / Postgres | nessun MISCONF o errore di connessione nei log |
| Alert | `portfolio_cycle_late` 13:30–14:08 critical; `broker_stale` 07:43–07:55 critical; 4 alert serali chiusi in 1 s; 3 Telegram 400 |
