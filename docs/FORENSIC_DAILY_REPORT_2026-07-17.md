# FORENSIC DAILY REPORT — 2026-07-17 (venerdì)

*Generato: 2026-07-20 ~12:40 UTC, sessione autonoma read-only. Timezone operativo: **UTC** (verificato in `src/workers/celery_app.py:49` → `timezone="UTC"`). Mercato USA: 13:30–20:00 UTC. Modalità broker: **PAPER** (verificato: `ALPACA_BASE_URL=https://paper-api.alpaca.markets`, chiave `PK…`, `ALPACA_PAPER_MODE` default true, `execution.engine=portfolio` in `config/trading.yaml`).*

---

## 1. Executive Summary

1. Il processo end-to-end ha girato regolarmente (24/24 cicli di portafoglio, ingest attivo 14:00–20:00 UTC, 189 news → 191 segnali → 7 ordini portfolio, tutti filled in 1–2 s, kill-switch/drawdown check attivi), **ma la giornata contiene un errore worst-case**: il BUY più grande del giorno — **DB (Deutsche Bank), $6.181, 10% di peso** — è stato generato da una news di **Fuller, Smith & Turner PLC** (pub inglese, LSE) mappata al ticker DB via `org_lookup` di GDELT, scorata **solo dal titolo** e da **un solo modello** (gpt-oss, glm sotto soglia confidence). È la classe di errore che il design definisce "worst-case" (ordine su titolo non correlato) e che il gate QX-01 tiene volutamente non-enforced.
2. Secondo problema strutturale: **i fill degli stop protettivi GTC non vengono riconciliati nel ledger** — lo stop ARM è scattato il 17/07 alle 13:35:58 UTC (−$34.34 realizzati) e quello NOK il 16/07 sera (−$57.8), ma i trade 308/314 risultano **ancora aperti** nel DB; le posizioni broker divergono dal ledger di esattamente 1 azione ARM e 41 azioni NOK.
3. Il **loop churn S1↔S4** (issue #67/#68, fix mergiato solo il 19/07) era ancora attivo: SBUX venduta da S4 `no_signal` alle 14:37, ricomprata da S1 alle 14:52, rivenduta alle 16:37; XLF chiusa da un segnale S4 "expired" di score **+0.010** e ricomprata da S1 un'ora dopo. Costo diretto ≈ −$18.5.
4. Nota positiva verificata: **il fix cancel-before-sell (PR #69, deploy 07-17 07:07 UTC) funziona live** — lo stop SBUX è stato cancellato prima della SELL delle 16:37 (era la verifica pendente).
5. PnL: NAV 109.474,38 a EOD (−$115,60 sul giorno, −0,11%); realizzato registrato −$18,47; realizzato **non registrato** −$34,34 (stop ARM). Fallback FinBERT al 47% dei segnali — tutti per **bassa confidence di entrambi i modelli**, zero divergenze vere.

## 2. Verdict finale

**ANOMALIE SIGNIFICATIVE.**
Il processo è auditabile e i controlli di sicurezza (paper mode, kill-switch, threshold, anti-pyramiding, stop) hanno operato, ma: (a) un ordine reale da $6.2K è nato da un ticker sbagliato (rischio già teorizzato, oggi materializzato); (b) il ledger trades diverge dal broker per fill di stop mai riconciliati (PnL realizzato sottostimato e 2 posizioni fantasma); (c) il loop di churn cross-strategy, già noto, ha continuato a bruciare spread fino al deploy del fix (19/07). Nessuna evidenza di ordini fuori orario, duplicati, o violazioni paper/live.

---

## 3. Timeline del 2026-07-17 (UTC)

| Ora (UTC) | Componente | Evento | Fonte |
|---|---|---|---|
| (07-16 18:04) | worker-inference | container avviato — attivo senza restart per tutto il 17/07 | `docker inspect` |
| 07:07 (da memoria sessione 07-17) | deploy | PR #69 cancel-before-sell deployata | memoria progetto |
| 08:21–08:27 | worker-inference | outage rete container: Telegram polling `Network is unreachable` / DNS fail (fuori orario mercato, nessun impatto trading) | docker logs worker-inference |
| 13:30 | mercato | apertura NYSE; regime run P0-09 schedulata 13:30 (non verificabile: log worker persi) | beat schedule |
| **13:35:58** | broker Alpaca | **stop GTC ARM (qty 1, submitted 07-16 18:07) FILLED @ 248.14** (entry 282.48, −12%) — **mai riconciliato nel DB** | /api/orders |
| 14:00 | beat | apertura finestra ingest (benzinga + gdelt ogni 15′, cron `hour=14-21`) | celery_app.py |
| 14:07:00 | portfolio-cycle #1/24 | S1 **BUY GE** $754 @ 355.51 (filled 14:07:10); stop protettivi INTC (3 sh) e SOXX (1 sh) piazzati | execution_decisions 3032, orders |
| 14:12 | reconcile-fills | prima run (cron :12/:27/:42/:57) — **non aggancia il fill dello stop ARM** (trade senza `exit_order_id`) | schedule + trades |
| 14:15:16 | ingest | prima news del giorno in `news_log` (benzinga) | news_log |
| 14:15:37 | sentiment | **UNH +0.700** (unico caso pair-agreement forte: glm+gpt-oss, news vera "UnitedHealth Q2 beat") | sentiment_signals 3990 |
| 14:22 | cycle #2 | stop protettivo GE (2 sh) piazzato; target combiner include UNH ~11.2% ma **anti-pyramiding P0-05 sopprime il re-BUY** (posizione UNH già esistente) — nessuna decision row | orders, portfolio_cycles 487 |
| 14:31:47 | sentiment | segnale XLF +0.010 (finbert, news "Leading And Lagging Sectors") — sarà la causa dell'exit "expired" delle 18:52 | sentiment_signals 3996 |
| 14:37:00 | cycle #3 | **S4 SELL SBUX `no_signal`** (posizione S1 del 16/07; SBUX non ha MAI avuto segnali S4 il 15–17/07) → trade 348 chiuso **−$6.77** | execution_decisions 3046 |
| 14:52:00 | cycle #4 | **S1 re-BUY SBUX** $752 @107.56 (15 min dopo la SELL — loop #67/#68) | execution_decisions 3059 |
| 15:07 | cycle #5 | stop SBUX (6 sh) piazzato; iniziano gli SKIP_THRESHOLD UNH (`score 0.100 < feedback threshold 0.350` — segnale decaduto) | orders, execution_decisions 3073 |
| 16:37:00 | cycle #11 | **stop SBUX CANCELED → S4 SELL SBUX `no_signal`** filled @106.51 → trade 360 chiuso **−$7.75**. ✅ Verifica live cancel-before-sell PR #69: PASS | orders, execution_decisions 3172 |
| 17:00 | fonte esterna | pubblicata la news finanzen.ch "Fuller, Smith & Turner PLC: Transaction in own shares" | news_log 4148 |
| 18:45:52 | sentiment | la news Fuller Smith viene scorata **+0.560 per il ticker DB** (solo gpt-oss; glm sotto min-confidence) | sentiment_signals 4148 |
| 18:52:00 | cycle #20 | **S4 BUY DB $6.181** (signal_score 0.672 ≥ 0.35) — **ticker errato** — e **S4 SELL XLF `expired`** (segnale +0.010 age 4.3h > 4h) → trade 349 chiuso **−$3.95** | execution_decisions 3245/3246 |
| 19:00:58 | sentiment | stessa news Fuller Smith ri-scorata (URL variante) per DB: −0.001 finbert — doppio scoring della stessa storia | sentiment_signals 4157 |
| 19:07 | cycle #21 | stop protettivo DB (175 sh) piazzato | orders |
| 19:46:26 | sentiment | ultimo segnale del giorno; `consecutive_fallback` reset a 0 | fallback_counters |
| 19:52:00 | cycle #24 | **S1 re-BUY XLF** $767 @56.28 (1h dopo la SELL expired — loop) | execution_decisions 3258 |
| 20:00 | mercato | chiusura NYSE | — |
| 22:30:00 | risk report EOD | NAV **109.474,38** (−115,60 dod), exposure 32.17% (da 26.84%), drawdown 7.64%, herfindahl 1.0 (degenere), alerts `[]` | risk_reports |

Non presenti/non verificabili: report performance 03:00 UTC e regime run 13:30 (log worker/beat/api del 17/07 persi — container ricreati 19/07 22:17 UTC). Il cron forense delle 14:30 **non ha prodotto** `FORENSIC_DAILY_REPORT_2026-07-16.md` (failure silenzioso).

---

## 4. News ingest

### Per fonte (da `ingestion_stats_daily` + `news_log`)

| Fonte | Fetched | Queued | Duplicati (contatore) | Scartate no-ticker | Stale | Parse fail | **Salvate in news_log** | Prima | Ultima |
|---|---|---|---|---|---|---|---|---|---|
| alpaca_benzinga | 556 | 227 | 2013¹ | 0 | 0 | 0 | **76** | 14:15:16 | 19:46:26 |
| gdelt_gkg | 1851 | 203 | 134 | **1646** | 0 | 0 | **113** | 15:00:19 | 19:15:14 |
| **Totale** | 2407 | 430 | — | 1646 | 0 | 0 | **189** | 14:15 | 19:46 |

¹ Il contatore duplicati benzinga (2013 > fetched) è cumulativo sui poll ripetuti degli stessi item nella giornata — semantica del contatore, non un'anomalia dei dati.

- Copertura oraria: 15/45/44/33/28/24 news nelle ore 14–19 UTC — nessun buco nella finestra attiva. **Nessun ingest 00:00–14:00 e 20:00–24:00: by design** (beat `hour="14-21"`), ma i primi 30′ di mercato (13:30–14:00) restano scoperti.
- Lag pubblicazione→ingest: media 87 min, max 2h (prevalentemente gdelt). Nessun timestamp futuro (0 news con `published_at` > `created_at`+5′). Nessuna news marcata `discarded_reason`.
- Dedup: vincolo unico `(url, ticker)`; **33 gruppi di `content_hash` duplicati** salvati comunque nella giornata (stessa storia con URL/ticker diversi passa la dedup). Caso concreto: "Fuller, Smith & Turner: Transaction in own shares" salvata e **scorata 3 volte** (2× per DB con URL varianti, 1× per MS).
- Sanitizzazione: attiva (`sanitize_text`/`sanitize_ticker` chiamati prima del prompt, `src/workers/sentiment.py:202-204`).

### Per ticker (segnali generati; top per |score| max)

| Ticker | # segnali | avg score | max |score| | # fallback | Nota |
|---|---|---|---|---|---|
| MS | 27 | +0.018 | 0.701 | 19 | **~tutte news NON su Morgan Stanley** (Air France-KLM, Danske Bank, Visa, Cytek, Adidas…) |
| TSM | 19 | +0.059 | 0.604 | 11 | coverage ripetuta |
| MU | 19 | −0.003 | 0.360 | 7 | mista (alcune legittime con $cashtag) |
| GS | 16 | +0.038 | 0.317 | 10 | ambiguità simile a MS |
| NVDA | 8 | −0.084 | 0.415 | 5 | — |
| NFLX | 7 | −0.183 | 0.623 | 1 | price-target cuts (legittima) |
| SPCX | 5 | −0.211 | 0.480 | 0 | — |
| DB | 4 | +0.159 | 0.560 | 3 | **4/4 news non su Deutsche Bank** (Fuller Smith ×2, Capital One, JPMorgan) |
| AMD | 4 | −0.233 | 0.660 | 1 | — |
| UNH | 2 | +0.413 | 0.700 | 0 | news autentica Q2 beat |

### Top news per impatto sul segnale

1. **"Fuller, Smith & Turner PLC: Transaction in own shares"** (finanzen.ch, gdelt, `org_lookup`) → DB +0.560 → **unico ordine S4 del giorno ($6.181)**. Ticker errato.
2. **"UnitedHealth Analysts Increase Their Forecasts After Better-Than-Expected Q2"** → UNH +0.700 (pair agreement) → **nessun ordine** (anti-pyramiding su posizione esistente; poi decay sotto soglia).
3. **"Leading And Lagging Sectors For July 17"** → XLF +0.010 (finbert) → ha innescato l'exit `expired` di XLF alle 18:52.
4. "Cytek Biosciences Short Interest Down 50.2%" → **MS −0.701** (finbert, ticker errato) — nessun ordine (sotto soglia/il simbolo non ha superato il gate).

Confidenza dell'analisi ingest: **alta** (DB completo; contatori `ingestion_stats_daily` con semantica parzialmente ambigua sul campo `queued`).

---

## 5. Performance modelli LLM

| Modello | Richieste | Risposte | Timeout | Eligible (contributo all'ensemble) | Avg polarity | Avg confidence | Note |
|---|---|---|---|---|---|---|---|
| gpt-oss:20b-cloud (Ollama Cloud) | 191 | 191 (100%) | 0 | **93 (48.7%)** | −0.017 | 0.388 | ha dominato: 76 ensemble single-model |
| glm-5.2:cloud (Ollama Cloud) | 191 | 191 (100%) | 0 | **25 (13.1%)** | −0.024 | **0.248** | quasi sempre sotto min-confidence 0.4 |
| FinBERT (fallback locale) | 90 | 90 | 0 | 90 segnali (47.1%) | — | — | decide di fatto metà dei segnali |
| kimi-k2.6:cloud (shadow) | 191 | 191 | 0 | 0 (shadow-only) | — | — | `llm_shadow_responses` |
| qwen3.5:cloud (shadow) | 191 | 191 | 0 | 0 (shadow-only) | — | — | `llm_shadow_responses` |

- **Latenza: non persistita** (né in `llm_responses` né altrove; log worker del 17/07 persi) — gap di osservabilità.
- Budget: $0.0683 spesi (40.273 token in / 5.142 out), mai esaurito.
- Composizione ensemble dei 191 segnali: 17 pair completo (glm+gpt-oss), 76 solo gpt-oss, 8 solo glm, 90 FinBERT fallback.
- **Scomposizione dei 90 fallback (verificata su `llm_responses`): 90/90 = entrambi i modelli sotto min-confidence 0.4; 0 casi di divergenza direzionale vera.** L'etichetta di sistema "FinBERT fallback (ensemble divergence)" è quindi fuorviante per la coppia attuale: il problema non è disaccordo, è confidence bassa cronica (specie glm-5.2, avg 0.248).

### Verifica funzionale (Fase 4)

| Domanda | Esito |
|---|---|
| Output LLM validato prima del signal store? | **Sì** — schema JSON (`LLMSentimentOutput`), min-confidence 0.4 per modello, clamp score [−1,1] |
| Ensemble gestisce varianza alta? | Sì (soglia std 0.40 → fallback), ma il caso non si è mai presentato il 17/07 |
| News duplicate pesano più volte? | **Sì** — 3 segnali dalla stessa storia Fuller Smith (dedup solo per (url,ticker)) |
| Stessa news → segnali multipli? | Sì, su ticker diversi (Fuller Smith → DB e MS) |
| Confidence bassa riduce il peso? | Sì, a zero sotto 0.4 (esclusione, non downweight) |
| Modelli fuori dal trading loop? | **Sì** — worker-inference separato, scheduler legge solo dal DB |
| Rischio hallucination → decisione trading? | **Materializzato indirettamente**: non hallucination del modello ma ticker errato a monte; il modello ha scorato correttamente una news vera, attribuita al simbolo sbagliato, e l'ordine è partito senza verifica del resolver (enforcement gated su QX-01) |

---

## 6. Segnali finali per ticker → decisioni (Fase 5)

Soglia operativa S4: **0.350** (feedback threshold, ratchet). Regime_mult 0.7 su tutti i cicli. Execution decisions del giorno: 220 SKIP_THRESHOLD, 4 BUY, 3 SELL. Strategie attive: S1 (momentum) + S4 (news) — S7 rimossa dal 07-15.

| Ticker | Max signal_score visto al gate | Esito |
|---|---|---|
| DB | **0.672** (18:52) | **BUY $6.181** (unico sopra soglia — ticker errato) |
| TSM | 0.308 | SKIP_THRESHOLD ×11 |
| BP | 0.300 | SKIP ×1 |
| MU | 0.279 | SKIP ×15 |
| NOK | 0.240 | SKIP ×11 |
| HOOD | 0.199 | SKIP ×9 |
| UNH | 0.100 (ma segnale raw 0.700 alle 14:15) | SKIP ×4 dopo decay; **nessun ordine nel momento caldo per anti-pyramiding** |
| ERIC/MS/SPCX/LLY/AAPL/MSFT… | ≤0.18 | SKIP |

S1 (momentum, path a peso fisso ~1.24%): BUY GE 14:07, re-BUY SBUX 14:52, re-BUY XLF 19:52. SELL S4-driven: SBUX ×2 (`no_signal`), XLF (`expired`).

Nota di coerenza: `signal_score` della decisione DB (0.672) ≠ score raw del segnale (0.560) — la trasformazione di aggregazione/decay S4 non è ricostruibile dalla decision row perché **`signal_id` è NULL** nel path portfolio (vedi DAY-005); il collegamento è stato ricostruito manualmente (unico segnale DB compatibile per modello/orario).

---

## 7. Ordini generati/eseguiti (Fase 5)

### Ordini portfolio (7/7 filled, engine=portfolio, Alpaca **paper**)

| Ts decisione | Strat | Ticker | Azione | Qty | Fill px | Stato | Rationale | Risk check | Anomalie |
|---|---|---|---|---|---|---|---|---|---|
| 14:07:00 | S1 | GE | BUY | 2.1218 | 355.51 | filled 14:07:10 | momentum, peso 1.2% | kill-switch/drawdown/market-clock OK | — |
| 14:37:00 | S4 | SBUX | SELL | 7.1310 | 107.44 | filled 14:37:08 | `no_signal` weight 0% | idem | **loop #67/#68: posizione S1, S4 non ha mai avuto segnali SBUX** |
| 14:52:00 | S1 | SBUX | BUY | 6.9907 | 107.56 | filled 14:52:08 | momentum 1.2% | idem | re-entry 15′ dopo la SELL |
| 16:37:00 | S4 | SBUX | SELL | 6.9907 | 106.51 | filled 16:37:10 | `no_signal` | stop cancellato prima (PR #69 ✅) | secondo giro del loop |
| 18:52:00 | S4 | DB | BUY | 175.7027 | 35.18 | filled 18:52:09 | sentiment +0.672, peso 10% | soglia 0.35 passata; cap posizione OK (5.6% NAV) | **ticker errato (DAY-001)** |
| 18:52:00 | S4 | XLF | SELL | 13.6707 | 56.25 | filled 18:52:08 | `expired` (age 4.3h > 4h, score +0.010) | idem | segnale-spazzatura ha preso ownership di posizione S1 |
| 19:52:00 | S1 | XLF | BUY | 13.6345 | 56.28 | filled 19:52:06 | momentum 1.2% | idem | re-entry 1h dopo la SELL |

### Ordini stop protettivi (whole-share GTC, `_sync_fractional_protective_stops` #62/#63)

| Ts submit | Ticker | Qty (posizione) | Stato al 20/07 |
|---|---|---|---|
| 14:07:10 | INTC | 3 (3.89) | new (aperto) |
| 14:07:10 | SOXX | 1 (1.13) | new |
| 14:22:06 | GE | 2 (2.12) | new |
| 15:07:10 | SBUX | 6 (6.99) | **canceled 16:37 (cancel-before-sell OK)** |
| 19:07:06 | DB | 175 (175.70) | new |
| *(07-16 18:07)* | ARM | 1 (1.21) | **FILLED 07-17 13:35:58 @248.14 — non riconciliato (DAY-002)** |

- Corrispondenza decisioni↔ordini: 7/7 (nessun ordine senza decisione, nessuna decisione BUY/SELL senza ordine). Gli stop non hanno decision row (by design).
- Nessun ordine fuori orario (tutti 13:35–19:52 UTC, mercato aperto). Nessun duplicato nello stesso minuto (DB+XLF alle 18:52:07 sono simboli diversi dello stesso ciclo).

---

## 8. PnL / Rendimento (Fase 6)

| Voce | Valore | Fonte |
|---|---|---|
| NAV EOD 07-16 → 07-17 | 109.589,98 → **109.474,38** (**−$115,60**, −0,11%) | risk_reports 22:30 UTC |
| Exposure | 26,84% → **32,17%** (+5,3pp, quasi tutto il BUY DB) | risk_reports |
| Realizzato registrato (3 trade chiusi) | **−$18,47** netto (SBUX −6,77; SBUX −7,75; XLF −3,95; gross −17,21, costi $1,25, 5,2 bps/trade) | trades |
| Realizzato **NON registrato** | **−$34,34** (stop ARM 1 sh: 248,14 vs 282,48) + −$57,81 di NOK già maturato il 07-16 | orders API vs trades |
| Non realizzato posizioni pre-esistenti | delta MTM incluso nel −115,60; snapshot intraday non disponibile (solo EOD 22:30) | — |
| Posizioni aperte il 17/07 (a oggi 20/07) | GE −$4,82; DB +$5,27; XLF −? (in corso) | /api/positions |
| PnL per strategia | Tutti i 3 realizzati sono churn S1↔S4 (entry S1, exit S4-mechanism). Zero exit S4-su-S4 | trades + decisions |
| Commissioni | $0 (paper Alpaca); costi modellati 5,2 bps/exit | trades cost_* |

Cosa manca per un PnL intraday completo: serie NAV intraday (esiste solo lo snapshot risk_report 22:30; query utile: Alpaca `get_portfolio_history(period='1D', timeframe='5Min')` dal client paper) e il backfill dei 2 exit stop mancanti.

---

## 9. Correttezza funzionale BUY/SELL (Fase 7)

| Controllo | Esito |
|---|---|
| BUY solo quando consentito (soglia, kill-switch, mercato aperto, strategia approvata) | ✅ (DB unico sopra soglia; 24 cicli con pre-flight market-clock) |
| SELL/exit corretti | ⚠️ Meccanicamente sì (`no_signal`/`expired` documentati in reason), ma il criterio di ownership S4 su posizioni S1 è il bug #67/#68 (fix post-17/07) |
| Stop-loss rispettati | ⚠️ Stop ARM eseguito dal broker ma **invisibile al ledger**; frazioni non coperte dagli stop whole-share (dust ARM 0.21 sh, NOK 0.56 sh) |
| Signal flip rispettato | ✅ nessun flip contraddittorio nello stesso ciclo (il caso MSFT del 07-15 non si è ripetuto) |
| Max holding / rebalance band | ✅ S4 max_age 4h applicato (XLF); band non violata |
| Ordini duplicati / race scheduler | ✅ nessuno (lock ciclo attivo, `cycle_lock` nel codice) |
| Ordini contrari ravvicinati senza rationale | ⚠️ SBUX SELL 14:37 → BUY 14:52 (15′) e XLF SELL 18:52 → BUY 19:52: rationale presente ma è il loop noto — economicamente ingiustificato |
| Ticker consentiti | ⚠️ DB è nell'universo tradabile, ma il segnale proveniva da una società NON nell'universo (Fuller Smith) |
| Trade su dati stale | ⚠️ XLF exit guidato da un segnale di 4.3h (gate age l'ha correttamente chiuso; ma il segnale stesso era junk +0.010) |
| Trade con LLM output invalido | ✅ nessuno (validazione schema + min-confidence attive) |
| Circuit breaker / strategia disabilitata | ✅ kill-switch verificato per ciclo; drawdown 7.6% sotto cap; S7 rimossa e assente |
| Paper/live coerente | ✅ tutte le evidenze puntano a paper (URL, chiave PK, engine unico) |
| Idempotenza retry Celery | ✅ P2-05-A fail-closed su Redis; nessun doppio submit osservato |
| Riconciliazione ordini/fill/posizioni | ❌ **FALLITA per gli stop GTC** (ARM/NOK); OK per i 7 ordini portfolio (fill 1:1, trade_id linkati) |

---

## 10. Anomalie trovate

### [DAY-001] BUY $6.181 su DB (Deutsche Bank) generato da news di Fuller, Smith & Turner PLC (ticker errato)

* Tipo: Anomalia (worst-case error di design)
* Area: News / Signal / Orders
* Evidenza:
  * file/log/tabella: `news_log` id 4148 (url finanzen.ch "fuller-smith-&-turner-plc-transaction-in-own-shares", ticker=DB, `extraction_method=org_lookup`, body_snippet = solo titolo), `sentiment_signals` id 4148 (score +0.560, `ensemble:gpt-oss:20b-cloud`), `execution_decisions` id 3245 (BUY, signal_score 0.672, reason cita "share buyback… EPS… management confidence"), `trades` id 361 ($6.181,23), ordine Alpaca `df23bc4a` filled 18:52:09 @35.18
  * timestamp: news published 17:00 UTC, scored 18:45:52, BUY 18:52:00
  * snippet/query: `SELECT url, ticker, extraction_method FROM news_log WHERE id=4148;`
* Descrizione: l'org-lookup GDELT ha mappato una comunicazione di buyback di un pub-operator britannico (LSE: FSTA) al ticker NYSE DB. Il segnale è stato scorato dal solo titolo (600 char ma il body è il titolo), da un solo modello (glm sotto min-confidence), ha superato la soglia 0.35 e ha prodotto **la posizione più grande del giorno (10% peso, 5.6% NAV)**. Il resolver deterministico esiste ma l'enforcement è gated su QX-01 (misurazione-prima-di-enforcement).
* Impatto: posizione $6.181 su un titolo per cui non esiste alcuna informazione reale; su live sarebbe capitale reale esposto a caso. Al 20/07 la posizione è +$5.27 (fortuna, non correttezza).
* Severità: **Critical**
* Confidenza: High
* Azione consigliata: bridge-rule pre-QX-01: bloccare (o richiedere conferma resolver) i segnali da `org_lookup`/bare-text su ticker ≤2 caratteri o della lista ambigui quando generano ordini sopra una soglia notional; in alternativa cap peso per segnali single-model+org_lookup.
* Test/monitor consigliato: monitor giornaliero "ordini il cui segnale proviene da news con `extraction_method != cashtag/alias` su ticker ambigui"; test unit che una news org_lookup su ticker ambiguo non superi il gate ordini senza conferma resolver.

### [DAY-002] Fill degli stop protettivi GTC mai riconciliati nel ledger (ARM il 17/07, NOK il 16/07)

* Tipo: Bug
* Area: Broker / PnL / Data
* Evidenza:
  * file/log/tabella: /api/orders (ARM sell qty=1 submitted 07-16 18:07:10, **filled 2026-07-17 13:35:58 @248.14**; NOK sell qty=41 filled 07-16 19:48:19 @10.31); `trades` id 308 (ARM) e 314 (NOK) **exit_time NULL, exit_order_id NULL, exit_order_ids NULL**; `stop_decisions` vuota per questi simboli; broker vs ledger: ARM 0.2059 vs 1.2059, NOK 0.5640 vs 41.5640
  * timestamp: 2026-07-17 13:35:58 UTC (ARM), 2026-07-16 19:48:19 (NOK)
  * snippet/query: reconciliazione posizioni vs `SELECT symbol,SUM(qty) FROM trades WHERE exit_time IS NULL GROUP BY symbol`
* Descrizione: gli stop whole-share creati da `_sync_fractional_protective_stops` (#62/#63) non registrano il proprio order-id sul trade (`exit_order_id`); quando lo stop scatta, il task `reconcile-fills` non ha nulla da agganciare e l'exit non viene mai scritto. Risultato: 2 posizioni fantasma nel ledger, PnL realizzato sottostimato di ~$92 cumulati, `exit_reason=stop_loss` mai attribuito, analytics/feedback loop (rolling P&L, ratchet) alimentati con dati errati.
* Impatto: divergenza persistente ledger↔broker (3+ giorni), PnL e attribution sbagliati; il sizing live non è impattato (usa le posizioni broker).
* Severità: **High**
* Confidenza: High
* Azione consigliata: ticket P0: (a) backfill exit dei trade 308/314 dai fill Alpaca; (b) registrare l'order-id dello stop su `trades.exit_order_ids` (o tabella ponte) al momento del submit/sync; (c) estendere reconcile-fills agli ordini SELL filled non riconducibili a decisioni.
* Test/monitor consigliato: monitor giornaliero qty broker vs ledger per simbolo (alert su |Δ|>0.01); test integrazione "stop GTC fill → trade chiuso con exit_reason=stop_loss".

### [DAY-003] Loop churn S1↔S4 attivo (2 giri su SBUX + 1 su XLF), costo −$18.5

* Tipo: Bug noto (fix #67/#68 mergiato 07-19, NON attivo il 17/07)
* Area: Signal / Orders
* Evidenza:
  * file/log/tabella: `execution_decisions` 3046/3059/3172 (SBUX), 3246/3258 (XLF); `trades` 348 (−6.77), 360 (−7.75), 349 (−3.95); `sentiment_signals`: **zero segnali S4 SBUX il 15–17/07**; XLF exit guidato dal segnale +0.010 delle 14:31
  * timestamp: 14:37→14:52→16:37 (SBUX), 18:52→19:52 (XLF)
* Descrizione: S4 vende posizioni originate da S1 per `no_signal`/`expired` (ownership impropria), S1 le ricompra al ciclo successivo in cui il suo segnale riappare. Nel caso XLF l'ownership S4 nasce da un segnale-spazzatura (+0.010, sector-recap).
* Impatto: −$18.47 realizzati + spread/slippage; conferma la necessità del fix age-gate+consume+cooldown deployato il 19/07.
* Severità: Medium (già rimediato a valle; da verificare live questa settimana)
* Confidenza: High
* Azione consigliata: verificare nei report dei prossimi giorni che il cooldown 2h e l'age-gate 60′ abbiano azzerato i roundtrip; valutare (issue #70) il criterio di ownership per posizioni lone-survivor.
* Test/monitor consigliato: monitor "roundtrip stesso simbolo < 4h" con conteggio giornaliero atteso = 0.

### [DAY-004] Inquinamento sistematico dei ticker ambigui da GDELT org_lookup (MS 27/27, DB 4/4, GS/ERIC/NOK sospetti)

* Tipo: Anomalia
* Area: News / Data
* Evidenza: `sentiment_signals`+`news_log` 07-17: le 27 news→MS includono Air France-KLM, Zhongji Innolight, Danske Bank, Visa, REGENXBIO, Adidas, Cytek, Macerich…; le 4 news→DB: Fuller Smith ×2, Capital One, JPMorgan
* Descrizione: il path org_lookup assegna ticker mono/bi-carattere a news di società estranee su scala sistematica; il rumore consuma budget LLM, gonfia i fallback e periodicamente supera la soglia (DAY-001).
* Impatto: qualità segnale S4 degradata sulla coda dei ticker ambigui; costo LLM sprecato (~metà dei 191 scoring del giorno è su ticker sospetti).
* Severità: Medium (High come causa-radice di DAY-001)
* Confidenza: High
* Azione consigliata: quantificare con il golden set QX-01 la FP-rate di org_lookup sui ticker ambigui; nel frattempo escludere i ticker della lista ambigui dal path org_lookup (richiedere $cashtag come già fa il bare-text path).
* Test/monitor consigliato: metrica giornaliera "share di news per ticker ambiguo con extraction_method=org_lookup" sulla Quality dashboard.

### [DAY-005] Decisioni e trade S4 senza `signal_id` (audit trail interrotto)

* Tipo: Bug
* Area: Data / Ops
* Evidenza: `execution_decisions` id 3245 e `trades` id 361: `signal_id NULL`; il link al segnale 4148 è stato ricostruito manualmente via simbolo+modello+orario
* Descrizione: nel path portfolio la decision row S4 riporta `signal_score` ma non il riferimento al segnale; la catena news→segnale→decisione→ordine→trade non è navigabile automaticamente.
* Impatto: auditabilità ridotta proprio nel percorso che ha prodotto DAY-001; counterfactual/attribution incompleti.
* Severità: Medium
* Confidenza: High
* Azione consigliata: popolare `signal_id` (o l'elenco dei segnali aggregati) nella decision row S4 e propagarlo a `trades`.
* Test/monitor consigliato: assert in test che ogni decisione BUY S4 abbia `signal_id NOT NULL`.

### [DAY-006] Etichetta fallback "ensemble divergence" errata: 90/90 fallback sono "both models low-confidence"

* Tipo: Anomalia / telemetria fuorviante
* Area: LLM
* Evidenza: query su `llm_responses`×`sentiment_signals` 07-17: nei 90 segnali fallback, entrambe le confidence < 0.4 in 90 casi; 0 casi con entrambe ≥0.4 (divergenza vera)
* Descrizione: `run_inference` etichetta ogni aggregato None come "divergence", ma con la coppia glm-5.2+gpt-oss la causa reale è la confidence cronicamente bassa di glm (avg 0.248) e spesso anche di gpt-oss. La narrativa storica "disaccordo direzionale kimi⇄glm" non descrive la coppia attuale.
* Impatto: diagnosi errata del collo di bottiglia #1 di S4; le decisioni operatore (swap coppia, soglie) si basano su una causa sbagliata.
* Severità: Medium
* Confidenza: High
* Azione consigliata: distinguere i fallback reason (`low_confidence` vs `divergence` vs `timeout`) nel reasoning persistito e nei contatori; rivalutare glm-5.2 nel pair (13% di contributo effettivo).
* Test/monitor consigliato: contatore giornaliero fallback per causa; alert se un modello contribuisce <20% per 3 giorni.

### [DAY-007] Log Docker di worker/beat/api del 17/07 persi (container ricreati 19/07 22:17)

* Tipo: Rischio ricorrente
* Area: Ops
* Evidenza: `docker inspect` StartedAt 2026-07-19T22:17; `docker logs` worker/beat: 0 righe con "2026-07-17"
* Descrizione: terza occorrenza documentata (12/07, 16/07, 19/07): la ricreazione dei container azzera i log json-file; la forensica del giorno si fa solo da Postgres, perdendo il dettaglio del combiner (es. il salto UNH delle 14:22-14:52 non è più dimostrabile riga-per-riga).
* Impatto: auditabilità operativa ridotta; impossibile verificare regime-run 13:30, report 03:00, cadenze interne.
* Severità: Medium
* Confidenza: High
* Azione consigliata: log shipping persistente (volume + rotazione, o Loki/vector) — ticket già implicito nei report precedenti, va formalizzato come issue.
* Test/monitor consigliato: healthcheck che verifichi la presenza di log del giorno precedente per i container core.

### [DAY-008] Pesi ensemble stale riferiti a modelli inattivi (kimi-k2.6, qwen3.5)

* Tipo: Anomalia minore
* Area: LLM / Ops
* Evidenza: worker-inference log 07-17, ogni 15′: `Ignoring weights for inactive sentiment models: ['kimi-k2.6:cloud', 'qwen3.5:cloud']`
* Descrizione: `ensemble:weights:current` contiene ancora i pesi LOO-ICIR della vecchia coppia; i modelli live girano presumibilmente a peso default.
* Impatto: il rebalancing LOO-ICIR non sta pesando la coppia live; log noise.
* Severità: Low
* Confidenza: High
* Azione consigliata: rigenerare i pesi per glm-5.2/gpt-oss o pulire la chiave Redis.
* Test/monitor consigliato: warning aggregato (non per-run) quando i pesi non coprono i modelli attivi.

### [DAY-009] Buco di copertura 13:30–14:07 UTC (primi 37′ di mercato senza ingest né cicli; lo stop ARM è scattato lì)

* Tipo: Ambiguità / scelta di design non documentata
* Area: Ops / Orders
* Evidenza: beat schedule `hour="14-21"` per ingest/cycles; primo ciclo 14:07, prime news 14:15 (pattern identico 13–17/07); fill ARM 13:35:58 in finestra cieca
* Descrizione: il sistema apre 37 minuti dopo il mercato. Gli stop GTC lato broker coprono il gap (per la parte whole-share), ma nessun processo interno osserva quella mezz'ora (la reconcile parte alle 14:12 e comunque non aggancia gli stop — DAY-002).
* Impatto: eventi di apertura (gap-down, stop trigger) invisibili fino alle 14:07+.
* Severità: Low (diventa Medium se si va live)
* Confidenza: High
* Azione consigliata: documentare la scelta o estendere la finestra beat a `hour="13-21"` con guard sul market-clock.
* Test/monitor consigliato: —

### [DAY-010] Dust positions non gestite (NOK 0.56 sh = $5.8; ARM 0.21 sh = $56)

* Tipo: Anomalia minore (conseguenza di DAY-002 + stop whole-share)
* Area: Broker / Risk
* Evidenza: /api/positions; stop whole-share (vincolo Alpaca sugli ordini stop frazionari)
* Descrizione: dopo un trigger di stop whole-share resta una frazione non protetta e sotto la `_MIN_ORDER_NOTIONAL=100` — nessun processo la chiude.
* Severità: Low · Confidenza: High
* Azione consigliata: task di dust-cleanup (market SELL frazionale quando qty < 1 e nessun trade attivo la referenzia).
* Test/monitor consigliato: report settimanale posizioni < $100 senza trade aperto.

### [DAY-011] Cron forense del 17/07 non ha prodotto il report del 16/07

* Tipo: Anomalia
* Area: Ops
* Evidenza: `docs/` contiene FORENSIC del 14 e 15 ma non del 16; cron 14:30 feriali attivo
* Descrizione: failure silenzioso (timeout 600s è la causa storicamente nota).
* Severità: Low · Confidenza: Medium
* Azione consigliata: ack/notify sull'esito del cron (exit code + file prodotto).

### [DAY-012] `qty: "None"` in /api/orders per i BUY frazionari (bug noto 07-15, ancora presente)

* Tipo: Bug minore · Area: Frontend/API
* Evidenza: /api/orders, tutti i BUY notional-based (`qty="None"`, es. XLF 19:52)
* Severità: Low · Confidenza: High
* Azione consigliata: già tracciato il 07-15 — resta aperto.

### [DAY-013] herfindahl_index degenere = 1.000000 nei risk report (bug noto, ancora presente)

* Tipo: Bug minore · Area: Risk
* Evidenza: risk_reports 07-16 e 07-17: 1.000000 con 46 posizioni
* Severità: Low · Confidenza: High

---

## 11. False positive / aree risultate corrette

- **PR #69 cancel-before-sell: VERIFICATO LIVE** — stop SBUX `canceled` alle 16:37 prima della SELL filled; la regressione P0 #66 (stop GTC che bloccavano le SELL) è chiusa anche empiricamente.
- **UNH senza ordine nonostante segnale +0.700**: NON è un silent-drop — è l'anti-pyramiding P0-05 (posizione UNH già in book dal 07-10) che sopprime il re-BUY, comportamento intenzionale e documentato nel codice (`portfolio_scheduler.py:183-191`). Da rivedere come *design gap* (S4 non può mai scalare un simbolo già detenuto: la news vera non ha tradato, quella falsa sì), ma nessun bug.
- **Nessun BUY long-only violato** (il DAY-001 del 07-15 su MSFT non si è ripetuto: nessun BUY con sentiment negativo).
- **Ollama Cloud stabile**: 191/191 risposte da entrambi i modelli, zero timeout, budget non esaurito.
- **Idempotenza e race**: nessun ordine duplicato, nessun doppio ciclo (lock verificato), 24/24 cicli regolari.
- **Ingest senza buchi nella finestra attiva**, zero news con timestamp futuri, zero parse fail.
- **Outage rete 08:21–08:27** del container inference: solo polling Telegram, fuori dalla finestra operativa — nessun impatto.

## 12. Dati mancanti o non accessibili

- **Log Docker worker/beat/api del 17/07** (container ricreati 19/07 22:17) — ricostruzione solo da Postgres/API; regime-run 13:30 e report 03:00 non verificabili.
- **Latenza per chiamata LLM**: non persistita in alcuna tabella.
- **NAV intraday**: solo snapshot 22:30 (risk_reports); query utile: Alpaca `get_portfolio_history(timeframe='5Min')`.
- **`performance_metrics`**: vuota per la data (0 righe) — pipeline IC/ICIR non ha scritto.
- Il **Bearer token fornito nel prompt è l'ADMIN_API_KEY**, non un JWT: le API rispondono solo con header `X-API-Key` (il prompt operativo del cron andrebbe aggiornato).
- `portfolio_cycles.final_orders` è una lista di `repr()` Python, non JSON strutturato — parsing fragile per l'audit.

## 13. Raccomandazioni immediate

1. **Backfill degli exit ARM (trade 308) e NOK (trade 314)** dai fill Alpaca e correzione del PnL realizzato (−$92 cumulati non a ledger). [DAY-002]
2. **Registrare l'order-id degli stop protettivi sul trade al submit** e coprire il caso nel reconcile-fills. [DAY-002]
3. **Bridge-rule anti-wrong-ticker** (pre-QX-01): nessun ordine da segnali `org_lookup` su ticker ≤2 char / lista ambigui senza conferma resolver, o cap notional dedicato. [DAY-001/004]
4. **Verificare nei prossimi 2–3 giorni** l'efficacia live del fix reversal (age-gate/consume/cooldown, deploy 19/07): attesa = zero roundtrip <4h. [DAY-003]
5. **Distinguere i fallback reason** (low_confidence vs divergence vs timeout) e rivalutare glm-5.2 nella coppia (contribuisce al 13%). [DAY-006]
6. **Log shipping persistente** per worker/beat/api. [DAY-007]

## 14. Test / monitor da aggiungere

- Monitor giornaliero **qty broker vs SUM(trades aperti)** per simbolo, alert su |Δ|>0.01 sh (avrebbe preso ARM/NOK il giorno stesso).
- Test integrazione: stop GTC fill → trade chiuso con `exit_reason=stop_loss` + PnL scritto.
- Monitor "ordini originati da news `org_lookup` su ticker ambigui" (target: 0 senza conferma resolver).
- Contatore fallback per causa (low_confidence/divergence/timeout) + alert contributo modello <20% per 3 giorni.
- Assert: decisioni BUY S4 con `signal_id NOT NULL`.
- Monitor roundtrip stesso simbolo <4h (target 0 post-fix #67/#68).
- Healthcheck presenza log del giorno precedente + esito cron forense (file prodotto sì/no).

## 15. Ticket tecnici suggeriti

1. **P0 — Stop-fill reconciliation**: exit-linkage degli stop GTC + backfill trade 308/314 (DAY-002, include dust-cleanup DAY-010).
2. **P1 — Wrong-ticker guard per org_lookup su ticker ambigui** (DAY-001/DAY-004; collegare a QX-01/#30 e alla lista ambigui del resolver).
3. **P1 — signal_id nel path portfolio S4** (DAY-005).
4. **P2 — Fallback reason taxonomy + pesi ensemble per la coppia live** (DAY-006/DAY-008).
5. **P2 — Log persistence per container core** (DAY-007).
6. **P3 — Estensione/documentazione finestra 13:30–14:00** (DAY-009); **fix qty=None /api/orders** (DAY-012); **herfindahl** (DAY-013); **esito cron forense** (DAY-011).

## 16. Stato sistema

- **Ollama Cloud: UP tutto il giorno** — 191/191 risposte per entrambi i modelli del pair, 0 timeout, 0 ore di downtime osservate nella finestra operativa. Budget $0.068 (non esaurito). Shadow scoring attivo (kimi-k2.6 + qwen3.5, 382 risposte).
- **FinBERT fallback rate: 47,1% dei segnali** (90/191), causa unica: entrambe le confidence <0.4. Nessuna delle decisioni ordine del giorno è però nata da un segnale fallback (il BUY DB era gpt-oss single-model; gli ordini S1 non usano sentiment).
- **Worker restart events**: nessun restart osservato il 17/07 (worker-inference attivo ininterrottamente dal 16/07 18:04; worker/beat/api ricreati solo il 19/07 22:17 — i log del 17/07 sono andati persi con la ricreazione). Outage di rete del container inference 08:21–08:27 UTC senza impatto operativo.
- Ensemble pair live: glm-5.2 + gpt-oss (conferma da llm_responses); pesi LOO-ICIR stale (riferiti a kimi/qwen).
- NAV 109.474,38 · exposure 32,17% · drawdown 7,64% · 46 posizioni (che includono 2 posizioni-fantasma di ledger: ARM/NOK parzialmente chiuse al broker).
