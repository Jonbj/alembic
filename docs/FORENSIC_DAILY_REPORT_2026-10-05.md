# Forensic Daily Report — 2026-10-05 (lunedì)

Timezone: UTC (beat `celery_app.py`); mercato in EDT, RTH 13:30–20:00 UTC. Modalità: sola lettura (DB, API, log host `logs/containers/*-2026-10-05.log`). Analisi eseguita il 2026-10-16: DB e API riflettono anche i giorni successivi; i dati del 10-05 sono stati filtrati per data.
Ambiente: tutti gli ordini sono `alpaca_paper` (`portfolio_monitor_snapshots.source`). Ledger di riferimento: `docs/evidence/findings.json` (F-001…F-095); carta di osservazione in vigore (freeze fino al 2026-09-28 scaduto/prorogato — nessuna taratura proposta qui).

## 1. Executive summary

- Giornata operativa regolare: 24/24 cicli portfolio (14:07→19:52, ogni 15 min), 9 decisioni BUY/SELL → 9 ordini broker, tutte con `order_id`; 0 ordini senza decisione, 0 duplicati, 0 roundtrip < 30 min (minimo 105 min), 0 pyramiding.
- Ordini: 5 BUY (VALE, SPCX, TSLA, BA, SPCX) e 4 SELL (INTC, VALE, SPCX, TSLA). Tutti S4; INTC era una posizione S4 aperta il 16/09.
- PnL realizzato 10-05 (ledger `trades`): **+238,23 $** netti, dei quali INTC +230,00 (aperta 09-16) e +8,23 dai tre round-trip intraday. NAV 110.199,99 → 110.380,54 (snapshot 20:00): +180,55 $ (+0,164 %). BA e SPCX (2ª entrata) sono rimaste aperte overnight: chiuse il 10-06 (−17,79 e +58,70 $).
- Ingest: Benzinga WS 221 + REST 4, GDELT 18 → 243 righe `news_log`, 243 segnali (1 segnale per articolo, nessuno duplicato). 294 articoli accodati fuori seduta scartati stale al primo ciclo (13:38).
- LLM: **solo 143/243 segnali (59 %) sono ensemble a 2 modelli**; 97 (40 %) sono `single:gpt-oss` (glm sotto soglia di confidenza), 3 `single:glm`, 3 FinBERT reali (1,2 %). Solo 58/143 ensemble hanno `eligible` su entrambi i modelli.
- 3 di 4 SELL sono uscite `below_entry_gate` con sentiment ancora positivo (+0,238, +0,275, +0,005) causate dalla sovrascrittura del segnale forte con uno più recente e debole (F-023/F-013). SPCX: SELL 17:07 → ri-BUY 18:37.
- Ensemble Ollama degradato (timeout 90 s, ~20 righe) più un blip DNS 18:36 (clock Alpaca) e 19:00 (entrambi i modelli → FinBERT). Nessun outage continuo.
- Osservabilità: Telegram 400 (14:07), 6 righe DECAY CRITICAL solo nel log, token del bot in chiaro in ~17.000 righe di log, `finbert_fallbacks` del worker = 100 contro 3 eventi reali.
- Nessuna anomalia di sicurezza o di correttezza contabile nuova: 11 occorrenze su finding esistenti, 0 finding nuovi.

## 2. Verdict finale

**OK con warning.** Processo end-to-end coerente e riconciliato (ordini ↔ decisioni ↔ trade ↔ fill). I warning sono tutti ricorrenze di difetti già noti (qualità dell'ensemble, osservabilità, sovrascrittura del segnale S4); nessun ordine errato.

## 3. Timeline del 2026-10-05 (UTC)

| Ora | Componente | Evento | Fonte |
|---|---|---|---|
| 00:18–00:29 | worker-inference (shadow) | 9 timeout Ollama 90 s (glm 6, gpt-oss 3…); `run_sentiment_shadow_worker` supera soft 780 s e hard 840 s (TimeLimitExceeded) | worker-inference log |
| 04:00 | worker | Telegram 400 Bad Request (alert + messaggio con tastiera) | worker log |
| 04:53–13:30 | sentiment | ~40 task `skipped: market_closed` (corretto) | worker-inference |
| 07:00:57 | regime | `LLM-2 failed in regime detection: Ollama 410 Gone` (F-017) | worker-inference |
| 13:28 | news-stream | Benzinga: VALE (premarket); la coda off-hours verrà consumata al 13:35 | news_log id 13914 |
| 13:30:00 | monitor | snapshot NAV 110.249,92 (prev close 110.199,99), 40 posizioni | portfolio_monitor_snapshots |
| 13:35–13:38 | sentiment | 1º ciclo: 4 elaborati, **268 stale scartati**, 8 non tradabili; 184 s | worker-inference |
| 13:30–14:07 | portfolio | nessun ciclo: finestra beat 14–21 UTC fissa (F-021, DST) → gap di 37 min | portfolio_cycles |
| 14:07:00 | portfolio | ciclo 1806: 0 ordini; 6 SKIP_FALLBACK, 5 SHADOW_LATE_ENTRY | portfolio_cycles |
| 14:07:08 | alert | Telegram 400 (F-005) | worker log |
| 14:10 | sentiment | segnale 13913 VALE +0,49 (ensemble) da articolo del 13:28 (latenza 42 min) | sentiment_signals |
| 14:22:00 | exec | **BUY VALE** @14,06 (dec 60228); **SELL INTC** @117,25 (dec 60303, sentiment_reversal −0,375); SKIP_PYRAMIDING LLY | execution_decisions/orders |
| 14:37 | exec | SKIP_PYRAMIDING PBR (+0,463) | dec 60335 |
| 15:22 | exec | **BUY SPCX** @167,157 (sentiment +0,372) | dec 60655 |
| 15:37 | exec | SKIP_PYRAMIDING TSM (+0,329) | dec 60764 |
| 16:07 | exec | **SELL VALE** @14,04 (below_entry_gate, segnale 14:35 a +0,238) | dec 60986 |
| 16:22 | exec | **BUY TSLA** @377,63 (+0,371) | dec 61095 |
| 17:07 | exec | **SELL SPCX** @167,816 (below_entry_gate, segnale 16:23 a +0,275); SKIP_PYRAMIDING XLK (+0,291) | dec 61431/61432 |
| 18:07 | exec | **SELL TSLA** @379,35 (below_entry_gate, segnale 16:45 a +0,005); **BUY BA** @192,90 (+0,396) | dec 61867/61866 |
| 18:36:46 | clock | errore DNS su `paper-api.alpaca.markets/v2/clock` (transitorio, ciclo 18:37 regolare) | worker-inference |
| 18:37 | exec | **BUY SPCX** @167,285 (nuovo segnale 14085, +0,372) | dec 62080 |
| 19:00:00 | sentiment | DNS su ollama.com: entrambi i modelli falliscono → FinBERT (`finbert` 19:00:00) | worker-inference |
| 19:07 | exec | SKIP_PYRAMIDING ABBV (+0,331) | dec 62295 |
| 19:52 | portfolio | ultimo ciclo (1829); 24 cicli totali | portfolio_cycles |
| 20:00 | monitor | NAV 110.380,54 (+180,55 su prev close) | snapshots |
| 21:00 | decay | 6× DECAY CRITICAL (S1/S2/S4: stesso Sharpe −3,66 e IC 0,003) solo nel log | worker log |
| 22:00–22:45 | performance | forward-return (1040 aggiornati), counterfactual (1191, 1051 aggiornati), 0 errori | worker log |
| 23:15 | ingest | `ingestion_stats_daily` chiuso: Benzinga fetched 925/duplicates 6081 | ingestion_stats_daily |

## 4. News ingest

### 4.1 Per fonte

| Fonte | Trasporto | Righe `news_log` | Ticker distinti | Fetched/queued/dup/stale (stats) | Note |
|---|---|---|---|---|---|
| alpaca_benzinga | ws | 221 | 63 | 925 / 610 / **6081** / 294 | `duplicates` ≫ `fetched` (F-007) |
| alpaca_benzinga | rest | 4 | 4 | (incluso) | 14:27–14:28 |
| gdelt_gkg | — | 18 | 9 | 1504 / 18 / 1 / 0 (1485 `no_ticker`) | solo `org_lookup` (18) |

Estrazione: `source_metadata` 225, `org_lookup` 18. `discarded_reason` NULL su tutte le 243 righe (i scarti sono solo nei contatori). Timestamp futuri: 0. Orari di creazione 13:35–19:33 (nessuna riga fuori RTH: la coda off-hours viene scartata/stale, F-069). Distribuzione oraria: 23/46/42/44/33/34/21 (13…19 UTC) senza buchi. Hash di contenuto duplicati: 30 gruppi (fan-out multi-ticker, atteso). `parse_fail` 0. Buchi WebSocket news-stream: 2 reconnect 1011 keepalive (343 righe di log, nessuna tempesta).

### 4.2 Per ticker (segnali)

| Ticker | N seg. | Score medio | Min | Max | Esito |
|---|---|---|---|---|---|
| SPY | 23 | −0,008 | −0,175 | 0,160 | — |
| NVDA | 17 | 0,045 | −0,120 | 0,350 | shadow late entry |
| GOOGL | 13 | 0,017 | −0,080 | 0,210 | — |
| META / MSFT | 12 / 12 | −0,002 / −0,004 | −0,21 / −0,36 | 0,04 / 0,27 | — |
| SPCX | 10 | 0,098 | −0,270 | 0,372 | BUY ×2, SELL |
| TSLA | 7 | 0,027 | −0,189 | 0,371 | BUY, SELL |
| TSM | 6 | 0,181 | 0,000 | 0,329 | SKIP_PYRAMIDING |
| MU | 4 | 0,220 | −0,180 | **0,680** | SKIP_FALLBACK (single-model); 1d fwd −1,7 % |
| PBR | 4 | 0,190 | 0,000 | 0,463 | SKIP_PYRAMIDING |
| VALE | — | — | — | 0,490 | BUY, SELL |
| INTC | 3 | −0,198 | −0,375 | −0,012 | SELL |

### 4.3 Top news per impatto

1. VALE 13:28 «Why Is Vale Stock Trading Higher On Monday?» (+0,49, macro: elezioni Brasile) → BUY 14:22; PnL trade −3,10 $. Articolo di commento a un movimento già avvenuto (+7 % premarket): F-030.
2. PBR «Brazilian Stocks Rally 14%…» (+0,463) → bloccato da P0-05 (S1 a libro).
3. INTC «Terafab Opportunity Gets Crowded: Musk Confirms Talks With TSM» (−0,375, `competitor_readthrough`, 5 ticker nell'articolo) → SELL 14:22. Forward 1d −3,25 %: uscita corretta ex post.
4. TSLA «Tesla Stock Trends Higher: What's Happening?» (+0,371) → BUY 16:22; il corpo cita davvero le consegne Q3 (nessuna invenzione).
5. SPCX «Morgan Stanley: cheap and getting cheaper» (+0,372) e «Analysts See Significant Upside» (+0,372): due articoli distinti, due ingressi.
6. BA «Awarded $14.7B Lockheed contract» (+0,396, corpo di 216 caratteri) → BUY 18:07.

**Problemi**: duplicati/fetch (F-007), latenza notizia→segnale 3–42 min (VALE 42 min, F-019), HTML entities nei titoli (`&#39;`, `&#8217;`) ancora presenti in `news_log.title` e nel corpo (F-076, il fix riguarda il sanitizer lato prompt; qui il dato grezzo). **Confidenza analisi ingest:** alta per i conteggi (DB), media per le cause dei duplicati.

## 5. Performance modelli LLM

| Modello | Risposte (llm_responses) | Pol. media | Conf. media | `eligible` | Timeout 90 s (log) | Latenza |
|---|---|---|---|---|---|---|
| glm-5.3:cloud | 234 | +0,045 | 0,304 | 58 | 12 (+DNS) | non persistita (F-086) |
| gpt-oss:20b-cloud | 240 | +0,012 | 0,447 | 58 | 8 (+DNS) | non persistita |

Segnali per tipo: ensemble 143, single:gpt-oss 94 (+3 nei conteggi sotto), single:glm 3, finbert 3 = 243. Il worker riporta `ensemble_success` 143 / `finbert_fallbacks` **100** / `skipped_stale` 294 su 79 task (latenza di ciclo media 149 s, max 441 s). Eventi FinBERT reali in `finbert_fallback_events`: 3 (motivo «Ollama timeout», `body_chars` medio 314: FinBERT ha visto parte del corpo). Distribuzione: nessuna polarity |>0,9|, nessuna coppia alta polarity/bassa confidence.

Disaccordo: 8 ensemble con `ensemble_std` > 0,2 (ABBV 0,318: glm +0,25 vs gpt-oss +0,70; TSLA 0,283; XLK 0,283; MSFT/NKE/MCD 0,247). ABBV (score +0,331) è stato poi bloccato da P0-05; nessuno di questi ha generato ordini. Dominio di un singolo modello: gpt-oss ha prodotto da solo 94 segnali (conf. media 0,51 vs 0,25 di glm sulle stesse righe), tutti esclusi dal ranking BUY da `SKIP_FALLBACK` (38 decisioni).

Verifiche funzionali: output strutturato validato prima del signal store (enum non normalizzati: F-055); dedup 1 segnale/articolo (nessun peso multiplo); confidence bassa riduce il peso via `score = polarity × confidence`; le chiamate LLM avvengono in `worker-inference` (offline, nessuna dentro `next()` o nel ciclo ordini); rischio hallucination: nessun caso rilevato oggi (TSLA e SPCX verificati sul corpo; VALE «Bolsonaro/fiscal discipline» presente nel corpo).

## 6. Segnali finali per ticker (che hanno prodotto o bloccato un'azione)

| Ticker | Segnale (id) | Score | Conf. | std | Gate 0,30 | Azione |
|---|---|---|---|---|---|---|
| VALE | 13913 | +0,490 | 0,70 | 0 | sì (×1,20 = 0,588) | BUY 14:22 |
| INTC | 13917 | −0,375 | 0,625 | 0 | uscita (−0,35) | SELL 14:22 |
| LLY | 13914 | +0,382 | — | — | sì | SKIP_PYRAMIDING (S1 a libro dal 07-15) |
| PBR | 13935 | +0,463 | — | — | sì | SKIP_PYRAMIDING |
| SPCX | 13973 | +0,372 | 0,65 | 0,035 | sì (×1,20) | BUY 15:22 |
| TSM | 13981 | +0,329 | — | — | sì | SKIP_PYRAMIDING |
| TSLA | 13997 | +0,371 | 0,675 | 0,071 | sì (×1,20) | BUY 16:22 |
| XLK | 14035 | +0,291 | — | 0,283 | sì (velocity) | SKIP_PYRAMIDING |
| BA | 14068 | +0,396 | 0,725 | 0,071 | sì | BUY 18:07 |
| SPCX | 14085 | +0,372 | 0,65 | 0,035 | sì (×1,20) | BUY 18:37 |
| ABBV | 14099 | +0,331 | — | 0,318 | sì | SKIP_PYRAMIDING |
| WDC | 13844 | −0,305 | — | — | — | SKIP_STALE (72,1 h > 4 h) |
| MU | 13925 | +0,680 | 0,80 | — | — | SKIP_FALLBACK (single-model) |

Decisioni totali del giorno: OBSERVE_LATE_ENTRY 1359, SKIP_THRESHOLD (centinaia, non contate), SHADOW_LATE_ENTRY 360, SKIP_FALLBACK 38, SKIP_PYRAMIDING 5, BUY 5, SELL 4, SKIP_STALE 1.

## 7. Ordini generati/eseguiti

| Ora | Strategia | Ticker | Azione | Qtà | Prezzo fill | Stato | Segnale | Decisione | Trade | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| 14:22 | S4 | VALE | BUY | ~111,09 | 14,06 | filled | 13913 | 60228 | 1050 | notional ≈ 1.562 $ |
| 14:22 | S4 | INTC | SELL | 14,5237 | 117,25 | filled | 13917 | 60303 | 1007 | sentiment_reversal |
| 15:22 | S4 | SPCX | BUY | 9,3525 | 167,157 | filled | 13973 | 60655 | 1051 | |
| 16:07 | S4 | VALE | SELL | 111,0868 | 14,04 | filled | — | 60986 | 1050 | stop frazionario (111 az.) annullato 14:37 |
| 16:22 | S4 | TSLA | BUY | 4,1352 | 377,63 | filled | 13997 | 61095 | 1052 | |
| 17:07 | S4 | SPCX | SELL | 9,3525 | 167,816 | filled | — | 61431 | 1051 | |
| 18:07 | S4 | TSLA | SELL | 4,1352 | 379,35 | filled | — | 61867 | 1052 | stop (4 az.) annullato 16:37 |
| 18:07 | S4 | BA | BUY | 8,064 | 192,90 | filled | 14068 | 61866 | 1053 | chiuso 10-06 |
| 18:37 | S4 | SPCX | BUY | 9,281 | 167,285 | filled | 14085 | 62080 | 1054 | chiuso 10-06 |

Ordini `canceled`: 5 stop protettivi frazionari (VALE, SPCX 15:37 e 18:52, TSLA, BA), cancellati prima/dopo il sell: ciclo normale di `Fractional protective stop sync`. Tutti gli ordini fra 14:22 e 18:37 (RTH). Paper account (`alpaca_paper`). Risk check: portfolio combiner (S1+S4) attivo in tutti i 24 cicli, peso target S4 2,0 % per ogni ingresso, `regime_mult` ×0,2 effetto sul notional (≈ 1.560 $ per ingresso invece di ~2.200 $, F-038).

## 8. PnL / rendimento

| Trade | Ticker | Aperto | Chiuso | Gross | Costi | Net | Origine |
|---|---|---|---|---|---|---|---|
| 1007 | INTC | 2026-09-16 | 10-05 14:22 | +230,82 | 0,82 | **+230,00** | pre-10-05 |
| 1050 | VALE | 10-05 14:22 | 10-05 16:07 | −2,22 | 0,88 | −3,10 | 10-05 |
| 1051 | SPCX | 10-05 15:22 | 10-05 17:07 | +6,17 | 1,64 | +4,53 | 10-05 |
| 1052 | TSLA | 10-05 16:22 | 10-05 18:07 | +7,11 | 0,31 | +6,80 | 10-05 |
| 1053 | BA | 10-05 18:07 | 10-06 16:52 | −16,93 | 0,86 | −17,79 | aperto 10-05, realizzato 10-06 |
| 1054 | SPCX | 10-05 18:37 | 10-06 16:07 | +60,33 | 1,63 | +58,70 | aperto 10-05, realizzato 10-06 |

- Realizzato 10-05: **+238,23 $** (= `portfolio_daily_state.net_pnl`, 4 trade). Per strategia: S4 +238,23 (INTC incluso: ma l'attribuzione per strategia è quella di `stop_strategy`).
- Non realizzato 10-05 di BA/SPCX: **non calcolabile** da DB (mancano i prezzi di chiusura 10-05; servirebbe `GET /v2/stocks/bars` Alpaca per BA e SPCX al 2026-10-05 21:00 UTC, oppure le posizioni a fine giornata).
- NAV: +180,55 $ (+0,164 %) a 20:00; `previous_close_equity` 110.199,99; chiusura ufficiale 10-05 = `previous_close_equity` del 10-06 = 110.376,05 (+176,06 $). La differenza fra NAV e realizzato (−58 $) è la variazione non realizzata del resto del book (~40 posizioni, 32.281 $ di valore a oggi) — non scomponibile per ticker senza gli snapshot posizione.
- `portfolio_daily_state.daily_return` = 0,03868 è **net_pnl / somma dei notional dei 4 trade chiusi** (238,23 / 6.158), non un rendimento del NAV (0,16 %): la metrica che alimenta il decay monitor non è un rendimento di portafoglio (F-004/F-053).
- Slippage: `trades.slippage_est` è copia di `cost_usd` (F-015) → qualità di esecuzione non misurata. Benchmark SPY non disponibile (F-016).

## 9. Analisi correttezza buy/sell

- BUY consentiti: tutti sopra il gate 0,30 (0,371–0,490 post-velocity), ensemble a 2 modelli, relevance corretta, entro `max_signal_age` 4 h; nessun BUY da fallback (38 SKIP_FALLBACK, di cui MU +0,68 corretto ex post).
- SELL: INTC (reversal −0,375 < −0,35) conforme; VALE/SPCX/TSLA `below_entry_gate` conformi alla regola ma con segnale positivo e sovrascrittura del segnale più recente (F-023). Le tre uscite avvengono a 105 minuti esatti (hold minimum), etichetta `trades.exit_reason=hold_minimum_expiry` coerente col meccanismo (la causa è `below_entry_gate` in `execution_decisions.exit_mechanism`): le righe sono post-#184, l'etichetta è osservata, non dedotta per età.
- Stop-loss: nessuno scattato; protezioni frazionarie create su VALE/SPCX/TSLA/BA e annullate alla chiusura. Max holding days: BA/SPCX in corso. Signal flip: INTC ok.
- Pyramiding: 5 segnali S4 sopra gate bloccati perché S1 detiene già il titolo (F-031).
- Duplicati / contrari: nessun ordine duplicato nello stesso minuto; SPCX SELL 17:07 → BUY 18:37 (90 min) con nuovo segnale distinto (F-013).
- Riconciliazione: 9 decisioni = 9 ordini filled = 6 trade (1007, 1050–1054); `signal_id` NULL su 3 delle 9 decisioni (le tre `below_entry_gate`, F-011). Circuit breaker: non attivato. Paper/live: solo paper.
- Telemetria cicli: `orders_count` 1–5 contro ≤1 ordine realmente inviato per ciclo (F-014): LLY BUY compare nel `final_orders` di 14 cicli senza mai partire (P0-05).
- Idempotenza Celery: nessun retry o doppio fill rilevato.

## 10. Anomalie trovate

### [DAY-001] Il 40 % dei segnali è single-model e solo il 41 % degli ensemble è `eligible` su entrambi i modelli

* Tipo: Anomalia · Area: LLM
* Evidenza: tabella `sentiment_signals`/`llm_responses` 2026-10-05; `SELECT model_id, count(*) FROM sentiment_signals WHERE generated_at::date='2026-10-05' GROUP BY 1` → ensemble 143, single:gpt-oss 94, single:glm 3, finbert 3; `eligible` 58/143. Log worker: `finbert_fallbacks: 100` contro 3 righe in `finbert_fallback_events`.
* Descrizione: glm risponde ma con confidence media 0,25 (< soglia) sulle 88 righe dove il segnale scivola a `single:gpt-oss`; il worker etichetta tutte come «finbert_fallbacks».
* Impatto: l'ensemble a 2 modelli decide su ~59 % dei segnali; i single-model sono esclusi dal ranking BUY (nessun ordine sbagliato), ma si perde copertura. MU +0,68 scartato (ex post corretto).
* Severità: Medium · Confidenza: High
* Azione consigliata: solo ricorrenza (F-010, F-078, F-054: masked divergence 107 righe di log).
* Test/monitor consigliato: contatore separato single-model/FinBERT reale e alert se single > 30 % in RTH.

### [DAY-002] Sovrascrittura del segnale forte S4 con uno più recente e debole → uscite con sentiment positivo e ri-ingresso

* Tipo: Anomalia · Area: Signal
* Evidenza: `execution_decisions` 60986 (VALE, score +0,238), 61431 (SPCX, +0,275), 61867 (TSLA, +0,005); trades 1050/1051/1052 chiusi esattamente a 105 min; SPCX SELL 17:07 @167,816 → BUY 18:37 @167,285 (trade 1054, chiuso 10-06 @173,79, +58,70 $).
* Descrizione: S4 usa solo l'ultimo segnale per simbolo (F-023) senza banda fra gate (0,30) e uscita (F-013): 3 SELL su 4 hanno sentiment positivo (pattern «SELL con sentiment positivo», non è il bug A5: è design di `below_entry_gate`).
* Impatto: SPCX churn: costo = costi extra 1,63 $ − 4,93 $ di prezzo migliore al ri-ingresso = −3,30 $ (guadagno). VALE −3,10 $ netti; TSLA +6,80 $. Effetto netto del giorno ≈ nullo ma la regola non è misurata.
* Severità: Medium · Confidenza: High
* Azione consigliata: ricorrenza su F-013 (SPCX, −3,30 $) e F-023 (VALE/TSLA/SPCX, non stimato).
* Test/monitor consigliato: già noti.

### [DAY-003] Cinque segnali S4 sopra il gate bloccati da P0-05 perché detenuti da S1

* Tipo: Anomalia · Area: Orders
* Evidenza: dec 60229 LLY +0,382, 60335 PBR +0,463, 60764 TSM +0,329, 61432 XLK +0,291, 62295 ABBV +0,331 (SKIP_PYRAMIDING); posizioni S1 da 794–1.010 $ contro target 2,7–2,9 % (≈ 3.000 $).
* Descrizione: il guard anti-pyramiding annulla gli ingressi S4 su titoli S1; `final_orders` di 14 cicli contiene ancora LLY BUY.
* Impatto: congetturale 2.200 $ × forward 1d (`sentiment_signals.forward_return`): LLY +26,18, PBR −32,78, TSM −16,28, XLK +11,00, ABBV +8,58 = **−3,30 $** (il blocco ha evitato una perdita netta marginale).
* Severità: Low · Confidenza: Medium
* Azione consigliata: ricorrenza F-031.
* Test/monitor consigliato: già noto.

### [DAY-004] Finestra beat fissa 14–21 UTC: primo ciclo portfolio 37 minuti dopo l'apertura (EDT)

* Tipo: Bug · Area: Ops
* Evidenza: `portfolio_cycles` primo ciclo 14:07:00; apertura 13:30 UTC; sentiment in funzione dalle 13:35.
* Descrizione / Impatto: DST non gestito (F-021). In questa giornata nessun segnale ≥ 0,30 esisteva prima delle 14:07 (query su `sentiment_signals` 13:30–14:07: 0 righe) → costo 0,0 $ misurato.
* Severità: Medium · Confidenza: High
* Azione consigliata: ricorrenza F-021.
* Test/monitor consigliato: test beat con calendario Alpaca in EDT/EST.

### [DAY-005] Ensemble Ollama degradato + blip DNS a 18:36 e 19:00

* Tipo: Rischio · Area: Ops
* Evidenza: worker-inference: ~20 `ensemble model failed … timeout (90s)` (glm 12, gpt-oss 8), 2× `Cannot connect to host ollama.com … Name or service not known` alle 19:00:00, `Could not fetch Alpaca market clock … NameResolution` alle 18:37; `finbert_fallback_events` 3 righe «Ollama timeout».
* Descrizione: nessun outage continuo (0 h di downtime misurate), ma nessuna traccia di trasporto/latenza e nessun alert (F-086, F-094, F-049). Il task shadow è stato ucciso dall'hard limit (840 s) alle 00:29.
* Impatto: fallback FinBERT a 19:00 (15 fallback nell'ora 19); clock transitorio senza effetto sul ciclo 18:37.
* Severità: Low · Confidenza: Medium
* Azione consigliata: ricorrenze F-086, F-049, F-094.
* Test/monitor consigliato: tabella di transport log per chiamate Ollama.

### [DAY-006] Osservabilità: Telegram 400, DECAY CRITICAL solo nel log, token del bot in chiaro

* Tipo: Anomalia · Area: Ops
* Evidenza: worker log 04:00 e 14:07:08 `Telegram… 400 Bad Request`; 21:00:00 6× `DECAY CRITICAL [S1/S2/S4]` con Sharpe −3,66 identico; worker-inference ~17.270 righe `getUpdates` con token nell'URL.
* Impatto: alert non recapitati; decay monitor non discrimina le strategie; segreto esposto nei log.
* Severità: Medium · Confidenza: High
* Azione consigliata: ricorrenze F-005, F-062, F-004, F-018 (+ rotazione del token se non fatta).
* Test/monitor consigliato: già noti.

### [DAY-007] Telemetria e catena decisione→segnale incompleta; regime con un solo LLM; duplicati ingest

* Tipo: Anomalia · Area: Data
* Evidenza: `execution_decisions`: signal_id NULL su 3/9 BUY/SELL; `portfolio_cycles.orders_count` 1–5 vs ≤1 ordine inviato; 07:00:57 `LLM-2 … regime detection: 410 Gone`; `ingestion_stats_daily` Benzinga duplicates 6081 > fetched 925.
* Impatto: auditabilità ridotta; regime sempre `sideways (×0,7)` senza disaccordo calcolabile.
* Severità: Low · Confidenza: High
* Azione consigliata: ricorrenze F-011, F-014, F-017, F-007.
* Test/monitor consigliato: già noti.

## 11. False positive o aree risultate corrette

- Nessun roundtrip < 30 min; nessun BUY ripetuto > 3 volte; nessun ordine identico nello stesso minuto; nessuna decisione BUY/SELL senza ordine; nessun ordine con score < 0,05 (BUY 0,37–0,49).
- SELL INTC corretto (fwd 1d −3,25 %, 3d −7,8 %); MU +0,68 correttamente escluso (fwd −1,7 %).
- Timestamp: nessun segnale con `published_at` > `generated_at`; UTC coerente; DST noto (DAY-004).
- I log host persistono (F-027 mitigato per il 10-05); nessun restart di worker osservato.
- Il fix `SKIP_STALE` (WDC 72 h) ha impedito l'uscita su segnale vecchio; fail-closed.

## 12. Dati mancanti o non accessibili

- Prezzi di chiusura 10-05 di BA/SPCX e delle altre posizioni (PnL non realizzato per ticker): query Alpaca bars 2026-10-05 o snapshot posizioni a fine seduta.
- Latenza per modello: non persistita (F-086).
- SPY benchmark: fetch fallito per limite SIP (F-016).
- Durata esatta del blip DNS 19:00 (nessun log di ripresa).
- `risk_reports` non ha colonna `created_at`: report di rischio del giorno non interrogato.

## 13. Raccomandazioni immediate

1. Nessuna taratura (freeze). Solo correttezza: separare nel worker i contatori single-model e FinBERT reale (F-078).
2. Persistere un log di trasporto per le chiamate Ollama (latenza, esito) — abilita la misura che manca per DAY-001/DAY-005.
3. Ruotare il token Telegram e togliere i URL dai log httpx (F-018).
4. Scrivere `signal_id` sulle decisioni `below_entry_gate` (F-011).

## 14. Test o monitor da aggiungere

- Alert su quota single-model/FinBERT > 30 % in RTH.
- Test di consistenza `daily_return` vs NAV.
- Controllo che `orders_count` del ciclo coincida con gli ordini inviati.
- Test beat in EDT: primo ciclo ≤ 13:35 UTC.

## 15. Ticket tecnici suggeriti

- F-078/F-010: contatori ensemble/single/FinBERT separati e `eligible` coerente (correttezza dell'evidenza).
- F-011: `signal_id` per le uscite `below_entry_gate`.
- F-021: finestra beat sensibile al DST.
- F-086: transport log Ollama.
- F-004: `daily_return` come rendimento NAV, decay per strategia.

## 16. Stato sistema

- **Ollama**: up con degradazione (≈ 20 timeout 90 s, 2 errori DNS alle 19:00); downtime continuo misurato: 0 h.
- **FinBERT fallback rate**: 3/243 = **1,2 %** di FinBERT reale; single-model 97/243 = 39,9 %; il contatore del worker riporta 100 (41,2 %), non affidabile (F-078).
- **Worker restart events**: 0 osservati (nessun banner di avvio nei log del 10-05); 1 `TimeLimitExceeded(840)` sul task shadow alle 00:29.
- Cicli portfolio: 24/24; sentiment: 79 task con contatori; Telegram: 2 consegne fallite.
