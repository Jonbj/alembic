# Forensic Daily Report — 2026-09-29

Sessione forense autonoma, sola lettura (eseguita il 2026-10-08). Fuso operativo **UTC** (`src/workers/celery_app.py`, `timezone="UTC"`, `enable_utc=True`): tutti i timestamp sono UTC. Seduta RTH 13:30–20:00 UTC (EDT, martedì). Nessuna ambiguità di timezone nel codice; il DST resta il difetto noto F-021.
Conto **paper** verificato, non assunto: `portfolio_monitor_snapshots.broker_environment='paper'` su 82/82 istantanee del giorno; `source=alpaca_paper`; `execution.engine=portfolio`.

Periodo di **sola osservazione** (`docs/evidence/OBSERVATION_CHARTER.md`, congelamento dichiarato fino al 2026-09-28; giorno analizzato successivo): nessuna taratura proposta, i ticket riguardano solo difetti di correttezza o strumentazione.

**Nota sul ledger.** `findings.json` conteneva già 3 occorrenze del 29/09 scritte dal ciclo alpha-miss (F-009 costo 24,93 ORCL/ARM; F-012 ORCL fan-out; F-076 entità HTML). Qui non sono ricontate: F-009 non viene ripetuto; F-012 riceve una seconda occorrenza solo per un caso diverso (ticker `C` su articolo Coinbase) con `costo_usd: null`.

---

## 1. Executive summary

- Pipeline end-to-end funzionante: 258 righe news (246 Benzinga + 12 GDELT; 174 titoli distinti) → 258 segnali su 70 simboli → cicli portfolio 14:07–19:52 → **3 BUY e 3 SELL S4, tutti `filled`** sul conto paper; 1 SKIP_PYRAMIDING, 3 SKIP_STALE, 38 SKIP_FALLBACK, 789 SKIP_THRESHOLD.
- Ordini↔fill↔trades riconciliati (6 fill = 4 trade toccati: 1034 chiuso, 1035 aperto+chiuso, 1037 aperto+chiuso, 1036 SPCX aperto e chiuso il 30/09). Nessun ordine fuori orario, duplicato, round-trip < 30 min, pyramiding > 3, né ordine privo di rationale; `SIGNAL_DUPLICATE_SKIP` ha impedito ri-esecuzioni dello stesso segnale.
- P&L realizzato S4 **+6,42 $ netto** (META +25,23; NVDA −3,90 e −14,91). SPCX aperta a fine seduta, MTM ≈ +0,64 $ (dossier). Variazione equity di giornata ≈ **+24 $ (+0,02%)** (109.786,32 = `previous_close_equity` del 30/09 vs 109.762,17 snapshot 28/09 20:00), contro SPY −0,18%.
- **Nuovo difetto di correttezza (F-093):** per tutta la seduta il conto paper ha riportato `cash` fermo a 71.290,39 (identico al centesimo al 25/09) e `last_equity = 0`. NAV di snapshot sottostimato di ≈1.532 $ (108.259 a 20:00 contro 109.786 reali), `previous_close_equity = 0,00` e `nav_change_today = nav` su 82/82 snapshot; il sizing S4 ha usato un NAV di ≈108,1k (target SPCX 2.162,98 = 2% di 108.149).
- Le tre decisioni di uscita/rientro NVDA dipendono da difetti noti: **SELL 14:22 su +0,019** (F-023, conf 0,25), **BUY 15:52** a 230,58 (+0,96 $/az sopra l'uscita, F-013), **SELL 17:52 su +0,000** (conf 0,15). Tutte e tre le uscite avvengono con sentiment ≥ 0 (pattern A5, F-013).
- LLM: Ollama sempre raggiungibile, **42 timeout** (glm-5.3 20, gpt-oss 22) senza blackout. Il 48% dei segnali (126/258) ha `fallback_used=true` ma quasi tutti sono letture a modello singolo (F-078): **FinBERT reale = 1 segnale** (XLE −0,782, divergenza ensemble, 0,4%).
- Segnali ≥0,30: 10, di cui 3 hanno generato ordine (META, SPCX, NVDA). Un caso sospetto: **`C` +0,450** su articolo "Coinbase wins CFTC approval" (ticker da `source_metadata`); bloccato da SKIP_FALLBACK (#108), nessun ordine.
- Segreti in chiaro nei log: bot token Telegram (17.267 righe) e api_key (3 righe) (F-018). `DECAY CRITICAL` S1/S2 alle 21:00 solo su log, nessun canale (F-062).

## 2. Verdict

**OK con warning.**

Percorso del denaro corretto, solo paper, riconciliato e idempotente. Le warning: il difetto nuovo F-093 (account broker stantio → NAV/variazione giornaliera/sizing sbagliati, evidenza di NAV del 29/09 non utilizzabile), le decisioni NVDA guidate da difetti noti (F-013/F-023), un segnale su ticker plausibilmente fan-out (`C`), e i segreti nei log (F-018). Nessun difetto richiede di fermare il sistema.

**Avvertenza `exit_mechanism` (#184).** I 3 SELL del 29/09 portano il meccanismo **osservato** nel testo del motivo (`[below_entry_gate]`): post-fix, non stima per età. `trades.exit_reason='portfolio_sell'` è un vocabolario diverso e non va letto come meccanismo. Nessuna riga pre-fix è stata contata in questo report.

---

## 3. Timeline del 2026-09-29 (UTC)

| Ora | Componente | Evento | Esito | Fonte |
|---|---|---|---|---|
| 00:00–13:29 | `worker-news-stream` | WS Benzinga 24/7; 121 menzioni `market_closed` nel log inference | news non scorate fuori seduta | log, F-069 |
| 06:16–12:21 | Ollama cloud | cluster di timeout (glm-5.3 / gpt-oss) prevalentemente del worker shadow notturno | nessun blackout | `worker-inference` log |
| 07:00:17 | `detect_regime` | `Failed to fetch macro data for regime detection: The read operation timed out` | nessun alert | log, F-017 |
| 12:28:00 | `sentiment_shadow` | SoftTimeLimit 780 s, lotto di 3 item perso; turno prosegue | ok | log |
| 13:30:00 | snapshot / alert | NAV 108.302,18; `previous_close_equity=0`; cash 71.290,39; alert `portfolio_cycle_late` critical + `signal_stale` warning | rientrati | `portfolio_monitor_snapshots`, `mobile_events`, **F-093** |
| 13:32 | sentiment | primo segnale 13:32:27; ensemble_cycle_health #1199 | ok | `sentiment_signals` |
| 14:07:00 | portfolio-cycle #1 | primo tick (RTH aperta 13:30, 37 min senza ciclo); 3 SKIP_STALE (GM 18,5 h, MRK 21,4 h, XLK 21,0 h) | nessun ordine | `execution_decisions` 51072–51074, F-021 |
| 14:22:00 | portfolio-cycle | **SELL NVDA** 6,3995 az @229,617 `below_entry_gate` (segnale 13133 +0,019 conf 0,25, generato 14:02); stop cancellato prima | filled 14:22:08 | decisione 51209, trade 1034 |
| 15:22:00 | portfolio-cycle | **BUY META** @720,99, velocity ×1,20 → gate 0,404, peso 2,0% (segnale 13165 +0,337) | filled 15:22:07 | decisione 51625, trade 1035 |
| 15:37:00 | portfolio-cycle | **BUY SPCX** @149,175 (segnale 13186 +0,551, gate 0,661); stop META (2 az) creato 15:37 | filled 15:37:06 | decisione 51730, trade 1036 |
| 15:52:00 | portfolio-cycle | **BUY NVDA** @230,582 (segnale 13191 +0,354); stop SPCX (9 az) creato | filled 15:52:06 | decisione 51835, trade 1037 |
| 16:07–17:22 | portfolio-cycle | `SIGNAL_DUPLICATE_SKIP` su 13165/13186/13191 a ogni ciclo; stop NVDA (6 az) creato 16:07 | nessun ordine duplicato | log worker |
| 16:37:05 | portfolio-cycle | SKIP_PYRAMIDING SPCX (+0,318; target 2.162,98 vs posizione 1.454,48) | nessun ordine | decisione 52151 |
| 17:03:03 | sentiment | XLE −0,782: divergenza ensemble → FinBERT (−0,931, conf 0,84), 1 evento in `finbert_fallback_events` (body_chars 425) | segnale persistito | tabella, F-087 |
| 17:52:00 | portfolio-cycle | **SELL NVDA** 6,306 az @228,264 `below_entry_gate` (segnale 13260 +0,000 conf 0,15, 17:36) | filled 17:52:07 | decisione 52732, trade 1037 |
| 19:37:00 | portfolio-cycle | **SELL META** 2,0172 az @733,64 `below_entry_gate` (segnale 13316 +0,108) | filled 19:37:14 | decisione 53569, trade 1035 |
| 19:52 | portfolio-cycle | ultimo tick RTH | — | `execution_decisions` |
| 20:00 | snapshot | NAV 108.259,39 (stantio), 44 posizioni, drawdown 2,16% | paper | `portfolio_monitor_snapshots` |
| 21:00 | decay monitor | `DECAY CRITICAL` S1 e S2 (IC −0,016, Sharpe −7,16) solo `log.critical` | nessun canale | log, F-062 |
| 22:28–22:29 | `sentiment_shadow` | SoftTimeLimit → `TimeLimitExceeded(840)` → SIGKILL ForkPoolWorker-3, lotto di 12 item perso | turno prosegue | log |
| 22:50 | alert | `Griglia portfolio-cycle fuori seduta` warning | — | `mobile_events` |

## 4. Tabella news ingest

Fonte: `ingestion_stats_daily` (contatori additivi, cfr. F-007) e `news_log` (righe per giornata di `fetched_at`).

| Fonte | fetched | queued | duplicates | no_ticker | stale | righe `news_log` | URL distinti | trasporto |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| alpaca_benzinga | 939 | 680 | **4.302** | 0 | 198 | 246 | 162 | ws 243 / rest 3 |
| gdelt_gkg | 1.407 | 12 | 3 | 1.392 | 0 | 12 | 12 | — |

- Copertura temporale: pubblicazioni 11:47–19:59 (Benzinga), 14:45–19:45 (GDELT); fetch orari 13:00–20:00 senza buchi (29–53 righe/ora). Latenza mediana Benzinga fetch−published = **40 s** (WS); 38 segnali generati oltre 30 min dopo la pubblicazione.
- Timestamp futuri: 0. Righe scartate (`discarded_reason`): 0 su 258. Corpo mancante/< 20 car.: 13 (Benzinga).
- Estrazione ticker: `source_metadata` 246, `org_lookup` 12 (GDELT). 70 ticker distinti; SPY 54 righe (macro fan-out), NVDA 16, MSFT 13, GOOGL 11, META 10, SPCX 10, TSLA 8, ORCL 8, AMZN 7, NFLX 6. 174 titoli distinti su 258 righe = ~1,5 ticker/articolo (fan-out, F-012).
- Problemi: `duplicates` (4.302) ≫ `fetched` (939) — contatore additivo non verificabile (F-007); entità HTML `&#39;` ancora nei titoli scorati (F-076, già in ledger dal ciclo alpha-miss); `C` per articolo Coinbase (DAY-005). 26 simboli di watchlist a zero news (dossier).
- Confidenza analisi: **Alta** su conteggi/timestamp, **Media** su dedup cross-provider (nessuna chiave di confronto indipendente).

**Top news per impatto sul segnale (|score| ≥ 0,30):**

| Segnale | Simbolo | Score | Ora | Titolo | Esito |
|---|---|---:|---|---|---|
| 13156 | INFY | −0,422 | 14:45 | Infosys, Wipro crash a minimi a 6 anni | nessun ordine (short non previsto) |
| 13165 | META | +0,337 | 15:15 | "Beyond Advertising": Meta Muse | **BUY** 15:22 |
| 13170/13186 | SPCX | +0,468 / +0,551 | 15:23 / 15:34 | SpaceX–Anthropic compute agreements | **BUY** 15:37 |
| 13191 | NVDA | +0,354 | 15:44 | Nvidia buyback | **BUY** 15:52 |
| 13204 | C | +0,450 | 16:10 | Coinbase wins CFTC approval | SKIP_FALLBACK (single-model), DAY-005 |
| 13210 | SPCX | +0,318 | 16:33 | SpaceX Stock Rises Tuesday | SKIP_PYRAMIDING |
| 13218 | DIS | +0,330 | 16:44 | Disney Q4 / slate 2027 (tono misto) | SKIP_FALLBACK |
| 13232 | XLE | −0,782 | 17:03 | 30Y yield 2002 high; FICO −27% (macro) | FinBERT, DAY-007 |
| 13288 | MU | +0,360 | 18:09 | Micron Q4 preview | SKIP_FALLBACK |

## 5. Tabella performance modelli LLM

Fonte: `llm_responses` (258 segnali del giorno), log inference. La latenza per chiamata **non è persistita** (F-086): non disponibile.

| Modello | Risposte | `eligible` | Polarity media | Conf. media | Score medio (p×c) | Min / Max | Pos >0,2 / Neg <−0,2 | Timeout (log) |
|---|---:|---:|---:|---:|---:|---|---|---:|
| glm-5.3:cloud | 258 | 68 | +0,060 | 0,321 | +0,023 | −0,30 / +0,56 | 50 / 28 | 20 |
| gpt-oss:20b-cloud | 255 | 68 | +0,028 | 0,473 | +0,016 | −0,56 / +0,56 | 37 / 33 | 22 |
| finbert (fallback) | 1 | — | −0,931 | 0,84 | −0,782 | — | — | — |

Segnali per tipo: ensemble 132, single gpt-oss 118, single glm 7, FinBERT 1. `ensemble_std` medio 0,080; `|score|` medio 0,100; 117/258 con |score| < 0,05.

- Disaccordo forte (ensemble_std ≥ 0,25 su `llm_responses`): NVDA 13184 (glm +0,50/0,55 vs gpt +0,10/0,40), MRVL 13192 (idem), RDDT 13203 (−0,40 vs +0,05), **C 13204** (glm 0,00/0,20 vs gpt +0,60/0,75), DIS 13213 (+0,10 vs −0,30), SPY 13289 (−0,30 vs +0,20), SPY 13299. In 4 di questi un solo modello è contributore effettivo (F-054 masked divergence: `ensemble_std` calcolato sul solo contributore eleggibile = 0).
- Dominanza di un solo modello: 118 segnali `single:gpt-oss` (46%) — `eligible` è vero solo su 68/258 per modello (F-010): l'etichetta non rappresenta i contributori reali.
- Fallback FinBERT reale: 1/258 (0,4%), ricevuto titolo 85 car. + corpo 425 car. (`title_chars`/`body_chars` > 0: il modello ha visto il corpo). `fallback_used=true` su 126/258 (48,8%) è una sovra-dichiarazione (F-078).
- Verifica funzionale: l'LLM gira nel worker `inference` (offline), mai nel loop di trading (S4 legge `sentiment_signals`). L'output passa per la validazione enum/normalizzazione solo parziale (F-055). Le news duplicate tra più ticker generano più segnali (fan-out, F-012). `confidence` bassa riduce lo score (score = p × c): es. NVDA 13260 conf 0,15 → +0,000. Il rischio hallucination diretta in decisione è mitigato da gate 0,30 + esclusione single-model dal ranking BUY (#108) — vedi DAY-005.

## 6. Tabella segnali finali per ticker (decisioni rilevanti)

| Ticker | Segnale / score | Gate | Decisione | Note |
|---|---|---|---|---|
| META | 13165 +0,337 (ens.) | 0,404 (×1,20) | BUY 15:22 | peso 2,0%; uscita 19:37 su +0,108 |
| SPCX | 13186 +0,551 (ens.) | 0,661 | BUY 15:37 | segnale 13210 +0,318 → SKIP_PYRAMIDING 16:37 |
| NVDA | 13191 +0,354 (ens.) | 0,30 | BUY 15:52 | segnali successivi −0,06…+0,04 |
| NVDA | 13133 +0,019 conf 0,25 | < gate | SELL 14:22 | sovrascrive la posizione S4 del 28/09 (+0,405), F-023 |
| NVDA | 13260 +0,000 conf 0,15 | < gate | SELL 17:52 | idem |
| GM, MRK, XLK | −0,279 / −0,200 / −0,163 | — | SKIP_STALE 14:07 | segnali 18–21 h > 4 h |
| C | 13204 +0,450 (single) | — | SKIP_FALLBACK | DAY-005 |
| DIS, MU | +0,330 / +0,360 (single) | — | SKIP_FALLBACK | #108 |
| XLE | 13232 −0,782 (FinBERT) | — | nessuna (long-only) | DAY-007 |
| INFY | 13156 −0,422 (ens.) | — | nessuna | long-only |

Totali decisioni del giorno: OBSERVE_LATE_ENTRY 1.721, SKIP_THRESHOLD 789, SHADOW_LATE_ENTRY 149, SKIP_FALLBACK 38, BUY 3, SELL 3, SKIP_STALE 3, SKIP_PYRAMIDING 1.

## 7. Tabella ordini generati/eseguiti (paper Alpaca)

| Decisione | Ora UTC | Strategia | Ticker | Azione | Qty | Fill | Stato | Segnale | Risk check |
|---|---|---|---|---|---:|---:|---|---|---|
| 51209 | 14:22:07 | S4 | NVDA | SELL | 6,3995 | 229,6169 | filled | `signal_id` NULL (F-011) | cancellazione stop prima del SELL; `below_entry_gate` |
| 51625 | 15:22:06 | S4 | META | BUY | 2,0172 | 720,99 | filled | 13165 | peso 2,0%, regime_mult 0,7 |
| 51730 | 15:37:04 | S4 | SPCX | BUY | 9,7544 | 149,1749 | filled | 13186 | idem |
| 51835 | 15:52:05 | S4 | NVDA | BUY | 6,3063 | 230,5816 | filled | 13191 | idem |
| 52732 | 17:52:04 | S4 | NVDA | SELL | 6,3063 | 228,2637 | filled | `signal_id` NULL | `below_entry_gate` |
| 53569 | 19:37:13 | S4 | META | SELL | 2,0172 | 733,64 | filled | `signal_id` NULL | `below_entry_gate` |
| stop | 15:37 / 15:52 / 16:07 | S4 | META 2 / SPCX 9 / NVDA 6 | stop protettivo | — | — | canceled (META, NVDA prima del SELL; SPCX il 30/09) | — | creati un ciclo dopo l'ingresso (F-022) |

Prezzo atteso non persistito: slippage non misurabile (F-015). Nessun ordine S1 il 29/09 (`s1_realizzato = 0`).

## 8. Tabella PnL/rendimento

| Voce | Valore | Fonte / nota |
|---|---:|---|
| Realizzato S4 netto, totale | **+6,42 $** | trades 1034, 1035, 1037; `market_daily.jsonl` `book.s4_realizzato` |
| — NVDA 1034 (aperta 28/09, prima del giorno) | −3,90 $ netto (lordo −3,60; costo 0,30) | trade 1034 |
| — META 1035 (aperta e chiusa il 29/09) | +25,23 $ (lordo +25,52; costo 0,29) | trade 1035 |
| — NVDA 1037 (aperta e chiusa il 29/09) | −14,91 $ (lordo −14,62; costo 0,29) | trade 1037 |
| Non realizzato SPCX 1036 (aperta 29/09) | ≈ +0,64 $ | dossier `mtm_eod`; chiusa il 30/09 14:37 @151,35, +19,69 $ netto (fuori giornata) |
| Costi modellati (9/29) | 0,30 + 0,29 + 0,29 + 0,29 (+1,53 SPCX in ingresso) | `cost_usd` — modellati, non misurati (F-015) |
| P&L da posizioni pre-esistenti (S1, 44 posizioni) | non separabile dalle fonti disponibili | richiede `GET /v2/account/portfolio/history` + posizioni a 28/09 close |
| Variazione equity di giornata | ≈ **+24 $ (+0,02%)** | 109.786,32 (`previous_close_equity` 30/09) − 109.762,17 (snapshot 28/09 20:00). Approssimazione: lo snapshot 28/09 20:00 non è il close ufficiale |
| NAV snapshot 29/09 | 108.302 → 108.259 | **non attendibile** (F-093) |
| SPY / QQQ | −0,18% / +0,19% | `market_daily.jsonl` |

Per ticker: META +25,23, NVDA −18,81 (−3,90 −14,91), SPCX +0,64 non realizzato. Per strategia: S4 +6,42 realizzato; S1 non valutabile. `/api/trades` riporta NVDA −13,22 e −6,17 lordi e META senza P&L: sbagliati rispetto al ledger (F-084). Non è stato stimato alcun P&L mancante.

## 9. Analisi correttezza buy/sell

- **Buy consentiti:** 3 BUY con segnale ensemble (non fallback) ≥ gate (0,404 / 0,661 / 0,30), peso 2,0%, `regime_mult` 0,7. Corretto.
- **Sell/exit:** 3 SELL `below_entry_gate`; i segnali che li hanno causati hanno score ≥ 0 (+0,019, +0,000, +0,108): **sell con sentiment positivo** (pattern A5 / F-013), coerente col codice ma privo di banda d'isteresi.
- **Stop-loss:** nessuno scattato; stop protettivi creati un ciclo dopo ingresso e sulla parte intera (META 2 su 2,017; SPCX 9 su 9,754; NVDA 6 su 6,306) — F-022. Log #161: WDC non protetto a −18,1% (`sub_one_share`) in 3 occorrenze.
- **Signal flip, max holding, rebalance band:** nessuna uscita per questi meccanismi il 29/09 (S4 usa solo il segnale più recente per simbolo, F-023/F-025).
- **Duplicati:** nessun ordine identico nello stesso minuto; nessun round-trip < 30 min; nessun BUY ripetuto > 3. Round-trip NVDA 14:22 SELL → 15:52 BUY: 90 min (non < 30).
- **Contrari ravvicinati senza rationale:** NVDA SELL→BUY→SELL in 3,5 h con rationale esplicito ma flip-flop (F-013).
- **Ticker non consentiti / fuori orario:** nessuno; tutti i fill 14:22–19:37 UTC (RTH).
- **Dati stale:** 3 SKIP_STALE corretti (> 4 h). Nessun trade su segnale stale.
- **LLM non valido:** nessun trade da fallback single-model (38 SKIP_FALLBACK); il solo FinBERT (XLE) non ha generato ordine.
- **Circuit breaker:** nessuna evidenza di attivazione; drawdown 2,16–2,28% (valore da snapshot con NAV stantio).
- **Paper/live:** paper su 82/82 snapshot.
- **Idempotenza Celery:** `SIGNAL_DUPLICATE_SKIP` ha bloccato 13165/13186/13191 per 7 cicli; nessun ordine duplicato.
- **Riconciliazione:** 6 ordini di mercato filled ↔ 6 eventi di trade; 3 stop canceled coerenti con le uscite. Nessuna posizione non riconciliata rilevata (44 posizioni a inizio e fine).
- **NO-ORDER:** 6/6 decisioni BUY/SELL hanno `order_id`. **Score < 0,05 con ordine:** 2 SELL (+0,019, +0,000), uscite, non ingressi.

## 10. Anomalie trovate

### [DAY-001] Account broker stantio: cash congelato al 25/09 e last_equity = 0 per tutta la seduta (F-093, nuovo)

* Tipo: Bug
* Area: Broker / Data
* Evidenza:
  * file/log/tabella: `portfolio_monitor_snapshots`, `src/mobile_monitoring/builder.py:489-496`, `src/workers/mobile_monitor_task.py:143`
  * timestamp: 13:30–20:00 (82 snapshot)
  * snippet/query: `select as_of,cash,nav,previous_close_equity from portfolio_monitor_snapshots where as_of::date='2026-09-29'` → cash 71.290,39 (= snapshot 25/09 20:00), prev_close 0,00 su 82/82; 28/09 20:00 cash 72.822,27; 30/09 13:30 cash 72.847,38, prev_close 109.786,32
* Descrizione: offset costante di −1.531,88 $ sul cash rispetto al valore coerente (72.822,27 + P&L di cassa del giorno = 72.847,38), costante per l'intera seduta; `previous_close_equity` calcolato come `nav − nav_change_today` vale 0 (l'account restituiva `last_equity = 0`). Il 30/09 il feed torna normale. Anche il sizing S4 usa il NAV (target SPCX 2.162,98 = 2% × 108.149 invece di 2.196).
* Impatto: NAV, variazione giornaliera, drawdown (2,16–2,28%) e dimensionamento del 29/09 sbagliati di ≈1,4%; l'evidenza per-giorno basata sugli snapshot non è utilizzabile per il 29/09. I trade e i fill non sono toccati.
* Severità: Medium
* Confidenza: High (sull'effetto), Medium (sulla causa: lato broker paper vs cache locale non distinguibile dai log)
* Azione consigliata: ticket di correttezza: validare `account.last_equity > 0` e `cash` coerente con l'ultimo snapshot; degradare lo snapshot (`degradations`) invece di persistere; registrare il giorno come rottura nella serie nel charter.
* Test/monitor consigliato: monitor `previous_close_equity > 0` e `|Δcash − Σ cash flow ordini| < soglia` tra snapshot consecutivi.

### [DAY-002] Flip-flop NVDA SELL → BUY → SELL in una sessione (F-013)

* Tipo: Anomalia
* Area: Signal / Orders
* Evidenza:
  * file/log/tabella: `execution_decisions` 51209, 51835, 52732; trades 1034, 1037
  * timestamp: 14:22, 15:52, 17:52
  * snippet/query: SELL @229,617 → BUY @230,582 → SELL @228,264
* Descrizione: non c'è banda fra gate d'ingresso (0,30) e uscita (0); NVDA esce a +0,019, rientra a +0,354, esce a +0,000.
* Impatto: costo del rientro ≈ (230,5816 − 229,6169) × 6,3063 = 6,08 $ + 0,29 $ di costo dell'ingresso extra ≈ **6,38 $** (controfattuale corto: restare in posizione dal 14:22 al 15:52).
* Severità: Medium
* Confidenza: Medium
* Azione consigliata: già coperto da F-013 (nessuna nuova taratura durante il congelamento).
* Test/monitor consigliato: contatore giornaliero di inversioni per simbolo.

### [DAY-003] Uscite S4 su segnale più recente debole (F-023)

* Tipo: Anomalia
* Area: Signal
* Evidenza:
  * file/log/tabella: decisioni 51209 (segnale 13133 +0,019 conf 0,25), 52732 (13260 +0,000 conf 0,15)
  * timestamp: 14:22, 17:52
  * snippet/query: segnali NVDA 13133/13145/13150 (+0,019/+0,020/+0,275) vs posizione aperta su +0,405
* Descrizione: S4 valuta solo l'ultimo segnale per simbolo; un'unica lettura debole a bassa confidenza chiude la posizione.
* Impatto: in questo caso le uscite hanno evitato perdita (drift post-uscita negativo, dossier); costo non stimabile (`null`).
* Severità: Medium
* Confidenza: Medium
* Azione consigliata: coperto da F-023.
* Test/monitor consigliato: logging di `signal_age` e `confidence` dell'ultimo segnale nelle uscite.

### [DAY-004] SPCX cade nel tier di costo di default (F-034)

* Tipo: Anomalia
* Area: PnL
* Evidenza:
  * file/log/tabella: trade 1036 (`spread_cost_bps` 10,0, `cost_usd` 1,5296 vs 0,29 degli altri)
  * timestamp: 15:37
  * snippet/query: `select symbol,spread_cost_bps,cost_usd from trades where id in (1034..1037)`
* Descrizione: SPCX non ha tier in `config/cost_model.yaml`; il `net_pnl` include un costo modellato di 10 bps invece di 1,5.
* Impatto: sovrastima del costo ≈ 1,5296 − 0,2912 = **1,24 $** sul net_pnl di 1036 (modellato, non reale).
* Severità: Low
* Confidenza: Medium
* Azione consigliata: coperto da F-034.
* Test/monitor consigliato: test che ogni simbolo della watchlist abbia un tier.

### [DAY-005] Segnale +0,450 su `C` per articolo Coinbase (fan-out multi-ticker) (F-012)

* Tipo: Rischio
* Area: News / LLM
* Evidenza:
  * file/log/tabella: `news_log` 13205 (`extraction_method=source_metadata`), segnale 13204 (single gpt-oss +0,60/0,75, glm 0,00/0,20), decisione 53652 SKIP_FALLBACK
  * timestamp: 16:10
  * snippet/query: titolo "Coinbase Wins CFTC Approval for Its Own Clearinghouse", ticker `C`
* Descrizione: il tag provider porta `C` (Citigroup, ticker a una lettera) su una notizia il cui soggetto è Coinbase; lo score +0,45 deriva da un solo modello con l'altro in forte disaccordo. Non si può provare l'errore di tagging (l'articolo potrebbe citare Citi).
* Impatto: nessun ordine (bloccato da #108), ma senza quel filtro sarebbe stato un ordine su titolo non pertinente. Costo non stimabile.
* Severità: Medium
* Confidenza: Low
* Azione consigliata: coperto da F-012/F-020 (risoluzione ticker deterministica; golden set QX-01 prima dell'enforcement).
* Test/monitor consigliato: etichettare l'articolo nel golden set; monitor su ticker a una lettera da `source_metadata`.

### [DAY-006] 126/258 segnali marcati `fallback_used` e `eligible` non rappresentativo (F-010 / F-078)

* Tipo: Anomalia
* Area: LLM
* Evidenza:
  * file/log/tabella: `sentiment_signals.fallback_used`, `llm_responses.eligible` (68/258 per modello)
  * timestamp: intera seduta
  * snippet/query: `model_id` single:gpt-oss 118, single:glm 7, finbert 1
* Descrizione: il flag include le letture a modello singolo; `eligible` non riflette il contributore effettivo. FinBERT reale = 1 evento.
* Impatto: la metrica "tasso di fallback" è gonfiata (48,8% vs 0,4%) e il ramo single-model riduce l'ensemble effettivo; costo non stimabile.
* Severità: Low
* Confidenza: High
* Azione consigliata: coperto da F-010/F-078.
* Test/monitor consigliato: distinguere `finbert_used` da `single_model` nel contatore.

### [DAY-007] XLE −0,782 da FinBERT su divergenza d'ensemble (F-087)

* Tipo: Rischio
* Area: LLM / Signal
* Evidenza:
  * file/log/tabella: `finbert_fallback_events` (XLE, title 85, body 425, p −0,931 c 0,840), segnale 13232 `ensemble_std=0.000`
  * timestamp: 17:03:03
  * snippet/query: titolo "30-Year Yield Hits 2002 High; Credit-Score Giant FICO Plunges 27%: Stock Market Today"
* Descrizione: articolo macro/multi-tema su un ETF energia; la sostituzione dei due LLM con FinBERT emette un verdetto netto con `ensemble_std=0`, mascherando la divergenza.
* Impatto: nessun ordine (long-only, nessuna decisione BUY/SELL su XLE il 29/09); costo non stimabile.
* Severità: Medium
* Confidenza: Medium
* Azione consigliata: coperto da F-087.
* Test/monitor consigliato: persistere la std pre-fallback.

### [DAY-008] Contatore duplicati Benzinga superiore ai fetched (F-007)

* Tipo: Anomalia
* Area: News / Data
* Evidenza:
  * file/log/tabella: `ingestion_stats_daily` 2026-09-29/alpaca_benzinga: fetched 939, duplicates 4.302
  * timestamp: aggiornamento 23:45
  * snippet/query: `select * from ingestion_stats_daily where day='2026-09-29'`
* Descrizione: contatore cumulativo cross-run non verificabile in modo indipendente.
* Impatto: metrica di dedup non interpretabile; costo non stimabile.
* Severità: Low
* Confidenza: Medium
* Azione consigliata: coperto da F-007.
* Test/monitor consigliato: invariante duplicates ≤ fetched per run.

### [DAY-009] `/api/trades` espone righe per ordine con P&L errato (F-084)

* Tipo: Bug
* Area: Frontend / PnL
* Evidenza:
  * file/log/tabella: `GET /api/trades?limit=200`
  * timestamp: interrogazione 2026-10-08
  * snippet/query: NVDA 6,3063 gross −13,22 (ledger −14,62), NVDA 6,3995 gross −6,17 (ledger −3,60), META `net_pnl` null (ledger +25,23)
* Descrizione: l'endpoint non rappresenta il ledger `trades`.
* Impatto: chi legge l'API ottiene P&L diversi dal ledger.
* Severità: Low
* Confidenza: High
* Azione consigliata: coperto da F-084.
* Test/monitor consigliato: test di parità endpoint ↔ ledger.

### [DAY-010] Segreti in chiaro nei log (F-018)

* Tipo: Rischio
* Area: Ops
* Evidenza:
  * file/log/tabella: `logs/containers/worker-inference-2026-09-29.log` (17.267 righe con `api.telegram.org/bot<token>`, 3 con `api_key=`)
  * timestamp: intera giornata
  * snippet/query: `grep -c "api.telegram.org/bot" worker-inference-2026-09-29.log`
* Descrizione: httpx a livello INFO stampa token e chiavi negli URL.
* Impatto: esposizione di credenziali nei file di log persistiti sull'host.
* Severità: High
* Confidenza: High
* Azione consigliata: ruotare token/chiavi e silenziare il logger httpx (coperto da F-018).
* Test/monitor consigliato: scansione dei log persistiti per pattern di segreti.

### [DAY-011] Regime e benchmark SPY falliscono senza alert (F-017 / F-016)

* Tipo: Anomalia
* Area: Data / Risk
* Evidenza:
  * file/log/tabella: `worker-inference` 07:00:17 "Failed to fetch macro data for regime detection: The read operation timed out"; `worker` 84 warning "subscription does not permit querying recent SIP data"
  * timestamp: 07:00, intera seduta
  * snippet/query: `grep "SPY benchmark fetch failed" worker-2026-09-29.log | wc -l` → 84
* Descrizione: fallimenti silenziosi su una grandezza che moltiplica il sizing (`regime_mult` 0,7) e sul benchmark.
* Impatto: `regime_mult` potenzialmente stantio; costo non stimabile.
* Severità: Medium
* Confidenza: Medium
* Azione consigliata: coperto da F-017/F-016.
* Test/monitor consigliato: alert su regime non aggiornato oltre 24 h.

### [DAY-012] `DECAY CRITICAL` S1/S2 senza canale di notifica (F-062)

* Tipo: Rischio
* Area: Ops / Risk
* Evidenza:
  * file/log/tabella: `worker-2026-09-29.log` 21:00:00; `mobile_events` (nessun evento decay)
  * timestamp: 21:00
  * snippet/query: "DECAY CRITICAL [S1]: IC dropped 147%… Sharpe … -7.16 vs 0.95"
* Descrizione: gli alert critici restano su `log.critical`; metriche pipeline-globali (F-004).
* Impatto: nessun operatore informato; costo non stimabile.
* Severità: Medium
* Confidenza: High
* Azione consigliata: coperto da F-062.
* Test/monitor consigliato: test che ogni CRITICAL generi un `mobile_event`.

### [DAY-013] Primo ciclo portfolio alle 14:07 con apertura 13:30 (F-021)

* Tipo: Anomalia
* Area: Ops
* Evidenza:
  * file/log/tabella: `execution_decisions` min(tick_time) 14:07:00; `mobile_events` 13:30:01 `portfolio_cycle_late`
  * timestamp: 13:30–14:07
  * snippet/query: tick per ora: 12/10/12/11/11/11 (14–19)
* Descrizione: la finestra beat in UTC fisso ignora il DST: 37 minuti di seduta senza ciclo (il critical delle 13:30 ricorre ogni giorno).
* Impatto: ingressi precoci non possibili; costo non stimabile.
* Severità: Low
* Confidenza: High
* Azione consigliata: coperto da F-021.
* Test/monitor consigliato: test della finestra beat in EDT/EST.

### [DAY-014] Copertura stop parziale e ritardata (F-022)

* Tipo: Rischio
* Area: Orders / Risk
* Evidenza:
  * file/log/tabella: ordini stop META 2 (su 2,0172), SPCX 9 (su 9,7544), NVDA 6 (su 6,3063), creati 15:37/15:52/16:07; log `#161: WDC unprotected at -18.1% (qty 0.3347, status sub_one_share)`
  * timestamp: 15:37–16:07
  * snippet/query: `GET /api/orders` filtrato
* Descrizione: gli stop vengono creati un ciclo (15 min) dopo l'ingresso e coprono solo la quantità intera; WDC resta senza stop a −18,1%.
* Impatto: esposizione senza protezione; costo non stimabile.
* Severità: Medium
* Confidenza: High
* Azione consigliata: coperto da F-022.
* Test/monitor consigliato: monitor `protected_qty/position_qty` per simbolo.

### [DAY-015] Worker shadow: SoftTimeLimit → SIGKILL, lotto perso (F-072)

* Tipo: Anomalia
* Area: Ops / LLM
* Evidenza:
  * file/log/tabella: `worker-inference-2026-09-29.log` 12:28:00 e 22:28–22:29
  * timestamp: 12:28, 22:29
  * snippet/query: `Hard time limit (840s) exceeded for run_sentiment_shadow_worker`, `Process 'ForkPoolWorker-3' exited with 'signal 9'`
* Descrizione: il turno shadow notturno supera il limite, perde il lotto di 3/12 item; solo shadow, nessun effetto sul percorso live. Ricorre dal 22/09.
* Impatto: dati shadow incompleti; costo non stimabile.
* Severità: Low
* Confidenza: High
* Azione consigliata: aggancio a F-072 (stesso meccanismo SoftTimeLimit senza recupero idempotente).
* Test/monitor consigliato: metrica `shadow_items_lost`.

## 11. False positive o aree risultate corrette

- Nessun ordine fuori orario, duplicato o su ticker non consentito; `SIGNAL_DUPLICATE_SKIP` e SKIP_PYRAMIDING (SPCX) hanno funzionato.
- 38 SKIP_FALLBACK e 3 SKIP_STALE corretti; nessun ordine da lettura single-model.
- Riconciliazione ordini↔trades↔fill coerente; stop cancellati prima dei SELL.
- Ollama raggiungibile tutta la seduta (nessun blackout, nessun restart di container nei log del giorno).
- Latenza di ingest WS mediana 40 s (non è il problema F-019 del giorno).
- Pattern richiesti non riscontrati: round-trip < 30 min, BUY > 3 in sequenza, ordini identici nello stesso minuto, `fallback_used` su tutti i simboli, NO-ORDER.

## 12. Dati mancanti o non accessibili

- Latenza per chiamata LLM e esito per modello (timeout/refusal): non persistiti (F-086); i timeout sono conteggiati dai soli log.
- Prezzo atteso degli ordini e quindi slippage reale (F-015).
- Chiusura ufficiale Alpaca del 28/09 e P&L per posizione S1: servirebbe `GET /v2/account/portfolio/history?period=1W&timeframe=1D` + posizioni al 28/09 close.
- Causa di F-093 lato broker: servirebbe la risposta grezza di `GET /v2/account` del 29/09 mattina (non loggata).
- Snapshot del 28/09 20:00 usato come proxy del close di quel giorno.
- `exit_mechanism` osservato solo da testo del motivo; nessun conteggio aggregato.

## 13. Raccomandazioni immediate

1. Registrare nel charter la rottura della serie NAV del 29/09 (F-093) e non usare gli snapshot del giorno come evidenza.
2. Ruotare token Telegram e api_key FRED e silenziare httpx INFO (F-018).
3. Aggiungere validazione e degradazione dello snapshot quando `last_equity <= 0` o `cash` incoerente.
4. Nessuna taratura di soglie/gate fino alla scadenza del congelamento.

## 14. Test o monitor da aggiungere

- Invariante `previous_close_equity > 0` e riconciliazione del cash tra snapshot consecutivi (DAY-001).
- Contatore giornaliero di inversioni SELL→BUY per simbolo (DAY-002).
- Test di parità `/api/trades` ↔ tabella `trades` (DAY-009).
- Scansione segreti sui log persistiti (DAY-010).
- Alert per ogni `log.critical` del decay monitor (DAY-012).
- Metrica `shadow_items_lost` (DAY-015).

## 15. Ticket tecnici suggeriti (solo correttezza)

1. **Snapshot account stantio** — validare `last_equity`/`cash`, degradare lo snapshot, loggare la risposta grezza del broker (F-093).
2. **Redazione segreti nei log** — filtro logging su URL httpx (F-018).
3. **Parità `/api/trades`** con il ledger (F-084).
4. **Canale CRITICAL del decay monitor** (F-062).
5. **Recupero idempotente del worker shadow** dopo SoftTimeLimit (F-072).

## 16. Stato sistema

- **Ollama:** su per tutta la giornata, 0 h di downtime. 42 timeout a livello di chiamata (glm-5.3 20, gpt-oss 22; cluster 06:16–12:21, 14:09, 18:41–18:45, 22:19), assorbiti da retry/single-model.
- **FinBERT fallback rate:** reale **1/258 segnali = 0,4%** (1 evento in `finbert_fallback_events`, divergenza); il flag `fallback_used` copre 126/258 (48,8%) per F-078; letture single-model 125 (48,4%).
- **Worker restart:** nessun restart di container nei log del 29/09; 1 SIGKILL di ForkPoolWorker-3 (shadow) alle 22:29 e 1 `TimeLimitExceeded` (840 s), nessun impatto sul percorso live.
- **Alert:** `portfolio_cycle_late` critical (13:30), `signal_stale` warning (13:30), `Griglia portfolio-cycle fuori seduta` warning (22:50).
