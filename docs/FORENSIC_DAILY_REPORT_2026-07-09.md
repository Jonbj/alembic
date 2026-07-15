# Forensic Daily Report — 2026-07-09

Analista: Trading Systems Forensic Analyst + Senior Backend Engineer + Quant Operations Reviewer (sessione autonoma, read-only)
Generato: 2026-07-10
Timezone operativo: **UTC** (esplicito in `src/workers/celery_app.py:51`, `timezone="UTC"`; nessuna ambiguità).
Market hours di riferimento: 13:30–20:00 UTC. Finestra sentiment/news: 14:00–21:45 UTC; finestra portfolio-cycle: 24 cicli, 14:07–19:52 UTC (pattern identico a 07-07/07-08).

---

## 1. Executive Summary

Il 9 luglio 2026 il sistema (modalità **paper** confermata: `execution.engine=portfolio`, ordini su `paper-api.alpaca.markets`) ha eseguito **solo 2 ordini, entrambi SELL alle 14:22 UTC**: chiusura CVX per segnale S4 scaduto (age 19,1h > max_age 4h, FIX-F) e chiusura XOM per **stop-loss sintetico** (-2,04%, soglia 2% — FIX-C, funzionalmente corretto). PnL realizzato: **-70,74 USD** (CVX -20,17, XOM -50,58). NAV 110.122,03 → 110.057,22 (-64,81, riconciliato). Dopo le 14:22 il portafoglio è rimasto **a deployment 0% per il resto della giornata**: la soglia d'ingresso loss-feedback era già a **0,55 dal primo ciclo (14:07)** ed è salita a **0,60 (= threshold_max) alle ~18:30** sotto la vecchia regola "qualsiasi rolling P&L negativo ogni 4h" — i fix (trigger a 0,5% equity, decay 24h) sono stati committati e deployati solo il 07-10 alle 07:52 UTC. Miglior candidato scartato: DELL a 0,546 contro soglia 0,550 (**-0,004**).

News ingest: 291 righe (108 benzinga, 183 gdelt), volumi normali, nessun timestamp futuro/campo mancante. **Il fix divergenza ensemble (STD 0,30→0,40, deployato 12:07) ha funzionato**: 0 fallback per divergenza su 60 tentativi (max std 0,177); il fallback FinBERT resta però al **79,6%** perché ora è interamente vincolato dalla capacità (234 segnali senza alcuna chiamata ensemble). Scoperte nuove: **`forward_return` a zero dal 07-06** (degrado dal 06-29) → il ribilanciamento pesi LLM del 07-06 è girato su ICIR tutti-zero; **`audit_log` a 0 righe per l'intera giornata**; log Docker del giorno persi di nuovo (recreate 07-10 07:52); mis-attribution ticker in peggioramento ed estesa oltre MS/GS (MS 61 segnali; near-miss: MS aggregato 0,465 vs soglia base 0,45).

## 2. Verdict Finale

**Anomalie significative** (esecuzione del giorno funzionalmente corretta).

Le 2 esecuzioni reali sono corrette e riconciliate (stop-loss rispettato, expiry-SELL con rationale tracciato, fill Alpaca coerenti, nessun ordine spurio/duplicato/fuori orario). Il verdetto peggiora rispetto a "OK con warning" per lo stato dei loop di controllo e misurazione: (a) audit trail a **zero righe** in un giorno con 2 esecuzioni reali (4° giorno consecutivo di `SIGNAL_STALE_SKIP` rotto + chiusure trade mai auditate by-design); (b) log applicativi del giorno **fisicamente persi per la seconda volta consecutiva**; (c) pipeline `forward_return` **morta da 3 giorni** con conseguente ribilanciamento pesi modelli su dati vuoti; (d) drought totale (0 BUY) prodotto da un ratchet già riconosciuto come difettoso e fixato solo il giorno dopo; (e) mis-attribution ticker che ha sfiorato un BUY su ticker errato (MS 0,465 vs base 0,45 — protetto solo dalla soglia alzata).

---

## 3. Timeline del 2026-07-09 (UTC)

| Ora UTC | Componente | Evento | Fonte |
|---|---|---|---|
| 12:07:38 | Infra | Recreate container `worker`/`worker-inference`/`api`/`beat` — deploy fix divergenza (ENSEMBLE_DIVERGENCE_STD 0,30→0,40, recovery_win_streak 5→3). Pre-finestra di mercato | `docker inspect` (rilevato nel report 07-08) |
| 13:30:45 | Regime detector | Regime `sideways`, multiplier **0,7** (VIX 16,13, yield curve 0,35, SPY mom 20d +1,39), 2 LLM concordi, `disagreement=false` | Redis `regime:current` |
| 14:01:59 | News ingest | Primo item benzinga in `news_log` (orario normale, a differenza del ritardo del 07-08) | `news_log` |
| 14:07:01 | Portfolio cycle | Primo ciclo del giorno (24 totali fino a 19:52). **Escalation loss-feedback 0,50→0,55 inferita qui**: i primi SKIP delle 14:07:06 mostrano già "feedback threshold 0.550" (il 07-08 chiudeva a 0,50; nessun ciclo intermedio; cooldown 4h scaduto) | `portfolio_cycles`, `execution_decisions` reason |
| 14:22:00.677 | Ciclo 343 | **SELL CVX** (combiner: "S4 signal expired age=19.1h > max_age=4h, score=+0.275, no counter-signal") + **force-close XOM** (stop-loss sintetico FIX-C: prezzo ≤ entry×0,98). XOM **senza riga in `execution_decisions`** e fuori da `orders_count` (=1) | `execution_decisions` id 2004; `trades` 242/243; codice `portfolio_scheduler.py` |
| 14:22:05.3–05.5 | Alpaca paper | Submit dei 2 ordini market sell_to_close; fill 14:22:07.68–07.70 (~2,4s). CVX fill 174,70; XOM fill 138,364743 | Alpaca `/v2/orders` |
| 14:22+ | Portafoglio | **Deployment 0%** — nessuna posizione aperta per il resto della giornata | `trades`, `/api/positions`, `risk_reports` |
| 15:03:54 | News ingest | Primo item gdelt_gkg (avvio ~15:00 anche il 07-07 e 07-08 → pattern strutturale, non anomalia del giorno) | `news_log` |
| 15:07:48 | Infra | Recreate container `frontend` (deploy fix Quality page Decimal) | `docker inspect` |
| 16:32–17:37 | Sentiment/S4 | Cluster di score alti: MS 0,575 e 0,554 (**mis-attribuiti**: Raymond James, W.R. Berkley/Mizuho), DELL 0,455 raw → aggregato **0,546** alle 17:22/17:37, MU 0,477 — tutti SKIP a soglia 0,550 | `sentiment_signals`, `execution_decisions` |
| ~18:30 | Loss-feedback | **Seconda escalation 0,55→0,60 (= threshold_max)**: prime reason "threshold 0.600" alle 18:37:06. Compatibile con la vecchia regola rolling-PnL-negativo e/o con 3 perdite consecutive (AZN 07-08, CVX, XOM); trigger esatto non verificabile (Redis `feedback:*` resettato il 07-10, log persi) | `execution_decisions` reason |
| 18:31:27 | Sentiment | MU raw **+0,680** ("Micron Shares Surge Past $1,000...") — l'aggregato MU ai cicli successivi resta però ≤0,282 (diluizione EMA da 40 segnali MU rumorosi, molti mis-attribuiti) | `sentiment_signals`, `execution_decisions` |
| 19:52:00.6 | Portfolio cycle | Ultimo ciclo del giorno (24/24 — fine finestra by-design, identico a 07-07/07-08) | `portfolio_cycles` |
| 20:00 | Mercato | Chiusura market hours | — |
| 20:00–21:48 | Sentiment | **82 segnali generati dopo l'ultimo ciclo**, incluso MU **+0,680 ensemble non-fallback alle 21:46** — mai valutati da alcun ciclo (silent drop ricorrente; fix SKIP_STALE non ancora deployato il 07-09) | `sentiment_signals` |
| 21:45:00–01 | Ingestion stats | Scrittura `ingestion_stats_daily` per entrambe le fonti | `ingestion_stats_daily.updated_at` |
| 21:48:16 | Sentiment | Ultimo item del giorno; `consecutive_fallback=7` (reset alle 21:46 dal successo ensemble MU) | `news_log`, `fallback_counters` |
| 22:00 | Forward-return worker | Schedulato — **risultato: 0/294 segnali del giorno con `forward_return`** (pipeline a zero dal 07-06, vedi [DAY-005]) | `sentiment_signals` |
| 22:30:00.64 | Risk monitor | Snapshot EOD: NAV **110.057,22** USD, exposure **0,0000**, drawdown combinato 5,45%, `alerts=[]` | `risk_reports` id 27 |

**Nota su osservabilità**: come per il 07-08, la timeline è ricostruita esclusivamente da DB (`execution_decisions`, `trades`, `portfolio_cycles`, `sentiment_signals`, `llm_responses`, `risk_reports`, `ingestion_stats_daily`), Redis e Alpaca `/v2/orders`. I log container del 07-09 sono **fisicamente persi** (recreate 07-10 07:52, vedi [DAY-003]); `audit_log` è a **0 righe** per il giorno (vedi [DAY-002]).

---

## 4. Tabella News Ingest

### Per fonte (day = 2026-07-09, da `ingestion_stats_daily` + `news_log`)

| Fonte | Fetched | Queued | Duplicates¹ | Discarded no-ticker | Stale | Parse fail | In `news_log` |
|---|---|---|---|---|---|---|---|
| alpaca_benzinga | 923 | 342 | 3.513 | 0 | 0 | 0 | 108 (14:01–21:48) |
| gdelt_gkg | 2.557 | 239 | 58 | 2.303 (90%) | 0 | 0 | 183 (15:03–21:47) |

¹ Contatore per coppia `(url, ticker)` post fan-out, non per articolo — stessa metrica fuorviante già documentata (07-07 [DAY-008]).

Gap queued (581) → `news_log` (291): filtri `SentimentWorker` (stale/neutral/not-tradable), conteggi per-run **non verificabili** (log persi).

### Per ticker (top da `sentiment_signals`, 294 segnali totali)

| Ticker | N | Score medio | Min/Max | Fallback | Note |
|---|---|---|---|---|---|
| **MS** | **61** | +0,074 | -0,19/+0,58 | 54/61 | **Mis-attribution: campione 12/12 titoli estranei a Morgan Stanley** (vedi [DAY-004]); peggio dei 47 del 07-08 |
| MU | 40 | +0,104 | -0,42/+0,68 | 27/40 | Mix di news legittime ($250B expansion) e mis-attribuite (Baystreet/TSX) |
| GS | 18 | +0,006 | -0,42/+0,47 | 18/18 | Stesso pattern MS (es. "ASX to open higher" → GS) |
| TSM | 12 | +0,039 | 0,00/+0,13 | 10/12 | |
| AMAT | 12 | +0,151 | 0,00/+0,53 | 9/12 | News legittima CEO demand visibility |
| NVDA | 11 | +0,044 | -0,10/+0,31 | 8/11 | |
| MSFT | 8 | -0,009 | -0,10/+0,11 | 4/8 | |
| SPCX | 7 | +0,027 | 0,00/+0,10 | 7/7 | News SpaceX-IPO da metadata Benzinga; **ticker assente da `ticker_lookup`** (vedi §10 nota in [DAY-004]) |
| META | 7 | +0,098 | +0,01/+0,30 | 6/7 | |
| NOK / AMZN / DIS | 6 | — | — | — | AMZN max +0,42 |

### Top news per impatto sul segnale (|score| più alto)

| Ticker | Score | Path | Titolo | Valutazione |
|---|---|---|---|---|
| MU | +0,680 | ensemble | "Micron Expanded U.S. AI Investments by $250 Billion..." (21:46) | Legittima, **mai valutata** (post-cicli) |
| MU | +0,680 | gdelt | "Micron Shares Surge Past $1,000 After $250 Billion US Expansion" (18:31) | Legittima, diluita dall'aggregato EMA |
| WMT | +0,635 | fallback | "Americans Are Driving Less But Paying More — and 7-Eleven Just Proved it" | **Mis-attribuita** (7-Eleven → WMT) |
| MS | +0,575 | fallback | "Raymond James Financial (NYSE:RJF) Stock Price Expected to Rise" | **Mis-attribuita** |
| MS | +0,554 | fallback | "W.R. Berkley (NYSE:WRB)... Mizuho Analyst Says" | **Mis-attribuita** |
| AMAT | +0,525 | ensemble | "Applied Materials CEO Sees 'Tremendous Visibility' Into Demand" | Legittima → skip a 0,55 |
| GS | +0,471 | fallback | "ASX to open higher; Tech stocks push Wall Street higher..." (20:47) | **Mis-attribuita**, post-cicli |
| DELL | +0,455 | ensemble | "Why Is Dell Technologies Stock Surging Thursday?" | Legittima → aggregato 0,546, **skip per 0,004** |
| PBR | +0,455 | ensemble | "Oil Shock Returns: Hormuz Crisis Rattles World" | Borderline (settoriale, non su PBR) |
| RIO | -0,441 | fallback | "European stock indices fell 1.2-2.7% on Wednesday" | **Mis-attribuita** |

### Qualità/problemi

- Timestamp futuri: **0**; `published_at` mancante: **0**; duplicati cross-provider (stesso `content_hash`): **0**.
- GDELT: **183/183 (100%)** `body_snippet` = titolo (nessun body reale) — invariato.
- Avvio GDELT ~15:00: pattern identico 07-07/07-08/07-09 → strutturale, non anomalia del giorno (ridimensiona il [DAY-005] del report 07-08, che riguardava benzinga).
- 5 dei 10 top-score del giorno sono mis-attribuiti — la coda alta della distribuzione è dominata dal rumore di attribuzione ([DAY-004]).

**Confidenza analisi ingest: Alta** (volumi/timestamp/duplicati da DB completo); **Media** sul gap queued→news_log (log persi).

---

## 5. Tabella Performance Modelli LLM

| Modello | Risposte | Eligible (conf≥0,4) | Polarity media (elig.) | Confidence media (elig.) | Range polarity |
|---|---|---|---|---|---|
| glm-5.2:cloud | 59 | 48 | +0,180 | 0,576 | -0,60/+0,85 |
| kimi-k2.6:cloud | 60 | 35 | +0,011 | 0,567 | -0,50/+0,70 |

- **Tentativi ensemble**: 60 su 294 segnali (20,4%); 59 con entrambe le risposte, **1 con una sola risposta** (COST id 2490, solo kimi — comunque accettato come ensemble non-fallback, vedi [DAY-010]).
- **Fix divergenza deployato alle 12:07 ha funzionato**: `ensemble_std` max 0,177 (media 0,022), ben sotto la nuova soglia 0,40 → **0 fallback per divergenza** (prima del fix la divergenza era la causa dichiarata dei fallback).
- **Fallback FinBERT: 234/294 = 79,6%** — interamente **capacity-driven**: tutti i 234 fallback hanno **zero** chiamate LLM associate (mai tentato l'ensemble — semaforo/concurrency=1 su worker-inference), nessuno per divergenza. Trend: 71,8% (07-08) → 79,6% (07-09): il fix divergenza non abbassa il rate perché il collo di bottiglia è la capacità.
- Tentativi per ora: 7 (h14), 3 (h15), 11 (h16), 12 (h17), 10 (h18), 10 (h19), 2 (h20), 5 (h21) — nessuna finestra di down Ollama; `consecutive_fallback` max 7 (21:48).
- **Budget**: 0,0970 USD, `budget_exhausted=false`.
- **Latenza/timeout/retry per chiamata: non verificabili** (log persi, [DAY-003]). L'unica risposta mancante (glm su COST) è compatibile con un errore/timeout singolo, non confermabile.
- Validazione output: sì — `eligible=false` filtra 36/119 risposte (min confidence 0,4); JSON strutturato.
- Chiamate offline/background: confermato (queue `inference` separata, nessuna chiamata nel trading loop).
- Confidence bassa riduce il peso: sì (`score = polarity × confidence`, verificato a campione).
- Rischio hallucination→decisione: come il 07-08, il rischio dominante resta **a monte** (attribuzione ticker errata, [DAY-004]), non l'invenzione di fatti da parte del modello.
- **Pesi modelli**: `weight_update_log` (auto_apply 07-06) assegna qwen3.5 0,59 + kimi 0,41, ma il runtime usa **glm-5.2 + kimi** → mismatch pesi/modelli, aggravato da `purified_icir` tutti 0,0 (vedi [DAY-005]/[DAY-006]).

**Confidenza analisi LLM: Media** — distribuzioni solide da DB; latenza/cause dei mancati tentativi non verificabili.

---

## 6. Tabella Segnali Finali per Ticker

Nessun ticker ha superato la soglia d'ingresso (0,55 fino alle 18:22, 0,60 dalle 18:37). Decisioni: **284 SKIP_THRESHOLD, 1 SELL, 0 BUY** (285 totali; nessun SKIP_EMA/SKIP_CAP/SKIP_STALE).

| Ticker | Miglior aggregato (`signal_score`) | Ora | Soglia al momento | Esito |
|---|---|---|---|---|
| DELL | **0,546** | 17:22, 17:37 | 0,550 | SKIP per **0,004** |
| MU | 0,477 | 17:07 | 0,550 | SKIP (raw +0,68 alle 18:31 diluito a ≤0,282 dall'EMA) |
| MS | 0,465 | 16:52–17:22 | 0,550 | SKIP — **mis-attribuito**; sopra la soglia base 0,45 |
| AMZN | 0,460 | 16:37 | 0,550 | SKIP |
| PBR | 0,455 | 16:52–17:22 | 0,550 | SKIP |
| LLY | 0,432 | 18:37 | 0,600 | SKIP |
| AMAT | 0,425 | 17:22–18:07 | 0,550 | SKIP |
| CVX | (expired +0,275) | 14:22 | — | **SELL** (rebalance→0, FIX-F) |
| XOM | — | 14:22 | — | **Force-close stop-loss** (senza decision row, [DAY-008]) |

---

## 7. Tabella Ordini Generati/Eseguiti

| # | Timestamp decisione | Strategia/Path | Ticker | Azione | Qty | Prezzo fill | Stato | Broker | Rationale | Risk check |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 14:22:00.677 | S4 combiner (ciclo 343) | CVX | SELL (close) | 13,73362867 | 174,70 | filled (submit 14:22:05.33, fill 14:22:07.70, ~2,4s) | Alpaca **paper** | Segnale S4 scaduto (19,1h > 4h), score residuo +0,275, nessun counter-signal | Sì — decision id 2004 |
| 2 | 14:22:00.677 | **Stop-loss sintetico FIX-C** (fuori combiner) | XOM | SELL (force-close) | 17,120362503 | 138,364743 | filled (submit 14:22:05.48, fill 14:22:07.68, ~2,2s) | Alpaca **paper** | Prezzo ≤ entry 141,24 × 0,98 = 138,4152 (fill -2,04%) | Sì (stop 2% da `trading.yaml`) — **ma nessuna riga `execution_decisions`/`audit_log`** ([DAY-008]) |

- Alpaca `/v2/orders` per il 07-09 restituisce **esattamente 2 ordini** (entrambi market, `sell_to_close`, `status=filled`): nessun BUY, nessun reject/cancel/parziale, nessun ordine duplicato o fuori orario.
- `portfolio_cycles` id 343: `orders_count=1`, `final_orders` = solo CVX — l'ordine XOM del path stop-loss **non è contato** (audit gap, non doppio invio).
- Reconciliation: `trades.exit_order_id` (242→d3868d6e, 243→dca45d82) = id Alpaca; posizioni post-close = 0 sia su `/api/positions` sia su `risk_reports` (exposure 0,0000). **OK**.
- S1 (`supervised_paper`, sleeve 50%): ha girato in tutti i 24 cicli (`strategies_run=["S1","S4"]`) ma **zero pesi/ordini** — continuazione del problema noto "S1 dead since 06-01" (fix mergiati e deployati il 07-10, fuori target-day).

---

## 8. Tabella PnL/Rendimento

| Trade | Ticker | Entry (07-08) | Exit (07-09) | Qty | Gross PnL | Cost USD | Net PnL | Motivo uscita |
|---|---|---|---|---|---|---|---|---|
| 242 | CVX | 176,07 | 174,70 | 13,73362867 | -18,82 | 1,35 | **-20,17** | portfolio_sell (signal expired) |
| 243 | XOM | 141,24 | 138,364743 | 17,120362503 | -49,23 | 1,35 | **-50,58** | **stop_loss** |
| **Totale realizzato 07-09** | | | | | **-68,04** | **2,70** | **-70,74** | |

- **PnL realizzato 07-09**: -70,74 USD (2 chiusure, 0 vincenti). Entrambe le posizioni erano state aperte il 07-08 (nessuna posizione aperta il 07-09 → PnL da posizioni nuove: n/a).
- **PnL non realizzato EOD**: 0 (nessuna posizione aperta dopo le 14:22).
- **PnL per strategia**: entrambi i trade S4; S1/S2/S7 senza attività.
- **NAV bridge**: 110.122,03 (07-08 22:30) → 110.057,22 (07-09 22:30) = **-64,81**, coerente col realizzato -70,74 al netto del MTM negativo (~-6) già incorporato nello snapshot NAV del 07-08 sulle stesse posizioni. **Confidenza Alta**.
- **Costi**: 5,35 bps per lato (2,70 USD totali sulle chiusure); `slippage_est` = `cost_usd` (stesso aliasing noto dal 07-07, non bloccante).
- **Rendimento della strategia vs PnL intraday**: le due perdite derivano da posizioni entrate il 07-08 su news petrolio (Hormuz) e chiuse dal decadimento/stop — funzionalmente corrette ("un trade può perdere denaro ma essere funzionalmente corretto").

---

## 9. Analisi Correttezza Buy/Sell

| Check | Esito | Note |
|---|---|---|
| BUY generati solo se consentiti | ✅ N/A (0 BUY) | Nessun aggregato ha superato la soglia 0,55/0,60 |
| SELL/exit corretti | ✅ OK | CVX: expiry FIX-F con rationale completo; XOM: stop 2% rispettato (fill -2,04%) |
| Stop-loss rispettati | ✅ OK | XOM force-close al primo ciclo utile con breach; cooldown same-day re-entry (`stop_loss_today:XOM`) previsto dal codice — non testato da re-entry (0 BUY) |
| Signal flip rispettato | ✅ OK | CVX venduto con score residuo **+0,275**: non è "SELL con sentiment positivo" (bug A5) ma expiry-to-zero — verificato nel reason |
| Max holding days | ✅ OK | Holding ~20h, sotto ogni limite |
| Rebalance band | ✅ OK | Unico rebalance è la chiusura CVX |
| Ordini duplicati | ✅ Nessuno | 2 ordini, simboli distinti; `SIGNAL_DUPLICATE_SKIP`=0 (nessuna entry da duplicare) |
| Buy+sell ravvicinati / roundtrip <30min | ✅ Nessuno | |
| Pyramiding (>3 BUY senza SELL) | ✅ Nessuno | |
| Ticker non consentiti | ✅ OK | CVX/XOM da posizioni legittime del 07-08 |
| Ordini fuori orario | ✅ OK | 14:22 UTC, dentro market hours |
| Trade su dati stale | ⚠️ Parziale | Il filtro stale ha **funzionato** (la chiusura CVX è proprio il suo effetto), ma il suo audit trail (`SIGNAL_STALE_SKIP`) è a zero righe dal 07-06 ([DAY-002]) — conteggi non verificabili |
| Trade con LLM output non valido | ✅ OK | `eligible=false` escluso; ma vedi [DAY-010] (ensemble a 1 modello) |
| Circuit breaker | ✅ OK, non attivato | `constraints_fired=[]` su tutti i 24 cicli |
| Strategia disabilitata | ✅ OK | S2 `disabled` e S7 `research`: zero attività |
| Paper/live coerente | ✅ OK | Endpoint `paper-api.alpaca.markets` verificato direttamente; `execution.engine=portfolio` |
| Idempotenza retry Celery | ⚠️ Non testata oggi | Nessun retry osservabile (log persi); nessun sintomo (0 duplicati) |
| Reconciliation ordini/fill/posizioni | ✅ OK | Vedi §7 |
| Loss-feedback | ⚠️ Corretto per config-allora-vigente, difettoso by-design | Escalation 0,50→0,55→0,60 sotto la vecchia regola; fix committati 07-10 ([DAY-001]) |

Nota cosmetica: le reason degli SKIP stampano lo score in valore assoluto ("score 0.144 < feedback threshold" per un aggregato di **-0,144**) — fuorviante in lettura rapida.

---

## 10. Anomalie Trovate

### [DAY-001] Giornata a 0 BUY: ratchet loss-feedback (vecchia regola) a 0,55→0,60, deployment 0% dal pomeriggio

* Tipo: Anomalia / Rischio
* Area: Risk / Signal
* Evidenza:
  * file/log/tabella: `execution_decisions.reason` ("score X < feedback threshold 0.550" 14:07:06→18:22:06, "…0.600" 18:37:06→19:52:07); `config/trading.yaml` §loss_feedback (commenti datati 2026-07-09); git log ee13c50/3ef745b (committati **2026-07-10 01:10/09:33**, deployati 07:52)
  * timestamp: 14:07:06 (prima soglia 0,55), 18:37:06 (prima soglia 0,60)
  * snippet/query: `SELECT substring(reason from 'threshold [0-9.]+'), min(created_at), max(created_at), count(*) FROM execution_decisions WHERE created_at::date='2026-07-09' AND decision='SKIP_THRESHOLD' GROUP BY 1` → 239 righe a 0,550, 45 a 0,600
* Descrizione: il giorno è iniziato con soglia già a 0,55 (escalation al primo ciclo 14:07, ereditando lo 0,50 del 07-08 con cooldown 4h scaduto) ed è salito a 0,60 (=threshold_max) alle ~18:30 dopo le perdite realizzate CVX/XOM — compatibile sia con la vecchia regola "qualsiasi rolling P&L negativo" sia con `consecutive_loss_trigger=3` (AZN 07-08, CVX, XOM). Il trigger esatto non è ricostruibile (Redis `feedback:*` resettato il 07-10, log persi). Il miglior candidato legittimo (DELL, aggregato 0,546) è stato scartato per 0,004. La base threshold è 0,45: la giornata ha richiesto il 22–33% in più.
* Impatto: deployment 0% dalle 14:22 a fine giornata su un book ~110K (costo-opportunità non quantificabile senza controfattuale; DELL "Stock Surging" era il caso più vicino). È la manifestazione massima del loop di underdeployment documentato in `docs/AS-IS_FINDINGS_2026-07-10.md`.
* Severità: High
* Confidenza: High (soglie documentate riga per riga nelle reason); Media sul trigger esatto delle escalation
* Azione consigliata: già intrapresa il 07-10 (ee13c50: trigger rolling a 0,5% equity, decay 24h, gate fuori dal velocity block) — **verificare nei prossimi giorni che il decay 24h riporti effettivamente la soglia verso la baseline 0,30** e che l'escalation non si ri-inneschi con perdite immateriali.
* Test/monitor consigliato: metrica giornaliera "entry_threshold effettiva per ciclo" persistita a DB (non solo Redis volatile) + alert se soglia ≥0,55 per >24h.

### [DAY-002] `audit_log` a ZERO righe per l'intera giornata (4° giorno di `SIGNAL_STALE_SKIP` rotto; chiusure trade mai auditate)

* Tipo: Anomalia
* Area: Ops / Data
* Evidenza:
  * file/log/tabella: `audit_log`
  * timestamp: ultima riga `SIGNAL_STALE_SKIP` in assoluto: 2026-07-06 17:07:04; ultima riga qualsiasi: 2026-07-08 18:22:07
  * snippet/query: `SELECT count(*) FROM audit_log WHERE created_at::date='2026-07-09'` → **0**; `SELECT action, count(*) FROM audit_log WHERE created_at>='2026-06-25' GROUP BY 1` → solo INSERT (40), SIGNAL_DUPLICATE_SKIP (106), SIGNAL_STALE_SKIP (4427, ferma al 07-06)
* Descrizione: peggioramento del [DAY-001] del report 07-08. Oggi il giorno intero è a zero righe perché: (a) il path `SIGNAL_STALE_SKIP` resta rotto dal 07-06 (4° giorno); (b) le **chiusure** di trade non hanno mai avuto un'azione di audit (esistono solo INSERT su apertura — verificato su tutta la storia della tabella); (c) non ci sono state aperture. Risultato: un giorno con 2 esecuzioni reali e un ratchet di rischio attivato due volte non ha **alcuna** traccia in `audit_log`.
* Impatto: audit trail nullo proprio nelle giornate in cui il sistema fa solo exit (le più delicate per il PnL); la Fase 7 ("niente trade se dati stale") resta verificabile solo indirettamente.
* Severità: High
* Confidenza: High
* Azione consigliata: (1) root-cause del path `SIGNAL_STALE_SKIP` (aperto da 4 giorni, ticket già suggerito nel report 07-08); (2) aggiungere azioni di audit per chiusura trade (`UPDATE`/`CLOSE`) e per gli adjustment loss-feedback.
* Test/monitor consigliato: alert "0 righe audit_log in un giorno di mercato con ≥1 ordine eseguito".

### [DAY-003] Log Docker del giorno target persi di nuovo (recreate 07-10 07:52 UTC) — seconda volta consecutiva

* Tipo: Anomalia / Ambiguità
* Area: Ops
* Evidenza:
  * file/log/tabella: `docker inspect alembic-{worker,worker-inference,api,beat}-1` → `StartedAt=2026-07-10T07:52:04Z`, `RestartCount=0`
  * snippet/query: `docker compose logs worker --since 48h | grep -c "2026-07-09"` → **0** (idem worker-inference)
* Descrizione: i 4 container applicativi sono stati ricreati alle 07:52 del 07-10 (deploy dei fix S1/loss-feedback, evento noto e documentato in sessione), cancellando irreversibilmente i log json-file del 07-09. È la **replica esatta** del [DAY-002] del report 07-08: la raccomandazione "log shipping esterno prima del prossimo recreate" non è stata implementata ed è di nuovo costata l'osservabilità di un'intera giornata (latenza LLM, retry Celery, eccezioni, cause del mancato tentativo ensemble su 234 segnali).
* Impatto: Fase 4 (latenza/timeout/refusal) e parti della Fase 7 (idempotenza retry) strutturalmente non verificabili per il secondo giorno consecutivo.
* Severità: Medium (aggravante: recidiva immediata dopo raccomandazione esplicita)
* Confidenza: High
* Azione consigliata: log shipping persistente (Loki/file su volume/driver journald) **prima** del prossimo deploy; in alternativa, procedura operativa minima: `docker compose logs > dump` prima di ogni `up --build`.
* Test/monitor consigliato: check pre-deploy automatico che esporti i log correnti.

### [DAY-004] Mis-attribution ticker in peggioramento ed estesa oltre MS/GS: domina la coda alta degli score; near-miss su MS

* Tipo: Bug
* Area: News / Signal
* Evidenza:
  * file/log/tabella: `news_log`, `sentiment_signals`; campioni: MS ← "Raymond James Financial (NYSE:RJF)..." (+0,575), MS ← "W.R. Berkley... Mizuho" (+0,554), WMT ← "…7-Eleven Just Proved it" (+0,635), MU ← "Baystreet.ca - TSX Enjoys Gains" (+0,524), GS ← "ASX to open higher…" (+0,471), RIO ← "European stock indices fell" (-0,441)
  * timestamp: intera giornata
  * snippet/query: `SELECT title FROM news_log WHERE fetched_at::date='2026-07-09' AND ticker='MS' LIMIT 12` → 12/12 titoli estranei a Morgan Stanley; MS = 61 segnali (20,7%→**20,7%+**: 61/294), vs 47 del 07-08
* Descrizione: continuazione aggravata del [DAY-003] del report 07-08. MS sale a 61 segnali/giorno; il pattern ora è chiaramente visibile anche su WMT, MU, RIO oltre a GS. **5 dei 10 score più alti del giorno sono mis-attribuiti.** Due effetti concreti misurati oggi: (1) **near-miss**: l'aggregato MS ha toccato 0,465 — sopra la soglia base 0,45; solo il ratchet a 0,55 ([DAY-001]) ha impedito un BUY su Morgan Stanley motivato da news su Raymond James/W.R. Berkley; (2) **diluizione**: i 40 segnali MU (molti rumore mis-attribuito, min -0,42) hanno diluito via EMA il segnale legittimo forte (+0,68, Micron $250B) tenendo l'aggregato ≤0,282 — il rumore di attribuzione non solo rischia falsi BUY, **sopprime anche i BUY legittimi**.
* Impatto: il worst-case error di CLAUDE.md (ordine su ticker non correlato) è stato evitato per coincidenza di soglie, non per struttura; l'alpha capture sul caso legittimo più forte del giorno (MU) è stato azzerato dalla diluizione.
* Severità: High
* Confidenza: High
* Azione consigliata: come da report 07-08 (filtro di prominenza su `org_lookup`), estendendo il controllo anche al path `source_metadata` di Benzinga (es. QQQ-war article taggato SPCX; SPCX peraltro **assente da `ticker_lookup`** eppure segnalato 7 volte — verificare da dove arriva la sua tradability).
* Test/monitor consigliato: metrica "% news con company name assente dal titolo" per ticker; regressione resolver con dataset "banca/broker citato come fonte".

### [DAY-005] Pipeline `forward_return` morta dal 07-06 (degrado dal 06-29): loop IC/ICIR e ribilanciamento pesi modelli girano su dati vuoti

* Tipo: Anomalia / Bug
* Area: Data / LLM
* Evidenza:
  * file/log/tabella: `sentiment_signals.forward_return`; task `src.workers.performance.run_forward_return_worker` (beat 22:00 UTC); `weight_update_log` id 9
  * timestamp: coverage per giorno: ~65% fino al 06-26 → 35/18/29/21/10 (06-29→07-03) → **0 dal 07-06** (0/109, 0/294, 0/227, 0/294)
  * snippet/query: `SELECT created_at::date, count(*) FILTER (WHERE forward_return IS NOT NULL), count(*) FROM sentiment_signals WHERE created_at>='2026-06-22' GROUP BY 1`
* Descrizione: il worker delle 22:00 che popola `forward_return` (necessario per IC/ICIR, decay monitor e LOO-rebalancing dei modelli) non popola più nulla da 4 giorni, con degrado progressivo iniziato il 06-29 (data del GLM-swap). Conseguenza già materializzata: l'auto_apply pesi del 07-06 (`weight_update_log` id 9) riporta `purified_icir` = {glm: 0,0, qwen: 0,0, kimi: 0,0} e `ic_variance=0,0` — ossia il ribilanciamento è stato applicato **senza alcun dato di performance**. Root cause non determinabile in sessione (log persi); candidati: breakage del fetch prezzi forward (Alpaca historical), o filtro sui segnali eleggibili.
* Impatto: tutta la catena "misura → pesa i modelli → seleziona l'ensemble" è cieca da giorni; la Stage 2 del model comparison (shadow mode) e il gate QX-01 dipendono da questi dati.
* Severità: High
* Confidenza: High sull'evidenza (coverage a zero), Low sulla root cause
* Azione consigliata: ticket dedicato: eseguire manualmente `run_forward_return_worker` in ambiente controllato con logging verboso e ispezionare l'esito; verificare le date di breakage (06-29 e 07-06) contro i deploy.
* Test/monitor consigliato: alert "coverage forward_return del giorno T-1 = 0%" alle 23:00 UTC; guard nell'auto_apply: rifiutare il ribilanciamento se `purified_icir` è tutto-zero.

### [DAY-006] Mismatch pesi/modelli: `weight_update_log` pesa qwen3.5+kimi, il runtime usa glm-5.2+kimi

* Tipo: Anomalia / Ambiguità
* Area: LLM
* Evidenza:
  * file/log/tabella: `weight_update_log` id 9 (auto_apply 07-06: qwen3.5 0,5925 + kimi 0,4075); `llm_responses` 07-09 (solo glm-5.2:cloud e kimi-k2.6:cloud)
* Descrizione: i pesi applicati il 07-06 si riferiscono a una coppia (qwen3.5+kimi) diversa da quella effettivamente in produzione dal GLM-swap del 06-29 (glm-5.2+kimi). Non è determinabile in sessione se il runtime ignori i pesi (fallback equal-weight) o li applichi a chiavi inesistenti; in entrambi i casi la ponderazione dell'ensemble non riflette il log.
* Impatto: combinato con [DAY-005], il meccanismo di pesatura adattiva è di fatto non operativo/incoerente; l'aggregato ensemble potrebbe essere equal-weight non intenzionale.
* Severità: Medium
* Confidenza: High sul mismatch documentale, Low sull'effetto runtime esatto
* Azione consigliata: verificare `redis_store.get_llm_models()` e il consumo dei pesi in `sentiment.py`; allineare le chiavi dei pesi alla coppia attiva o invalidare i pesi al model-swap.
* Test/monitor consigliato: assert/warning quando i modelli in `weight_update_log.applied_weights` ≠ modelli attivi.

### [DAY-007] 82 segnali post-19:52 mai valutati, incluso il miglior segnale legittimo del giorno (MU +0,680 ensemble, 21:46)

* Tipo: Anomalia (ricorrente, nota)
* Area: Signal / Ops
* Evidenza:
  * file/log/tabella: `sentiment_signals` (82 righe 19:52–21:48), `portfolio_cycles` (ultimo ciclo 19:52:00)
  * snippet/query: `SELECT count(*), max(abs(score)) FROM sentiment_signals WHERE created_at::date='2026-07-09' AND created_at > '2026-07-09 19:52:01'` → 82, 0,68
* Descrizione: la pipeline sentiment gira fino alle 21:48 (finestra beat 14–21) mentre l'ultimo portfolio cycle è alle 19:52: tutti i segnali delle ultime ~2h muoiono senza valutazione né traccia (il fix "SKIP_STALE logging" scritto il 07-09 in sessione **non era ancora deployato** — nessuna decisione SKIP_STALE nel giorno; deploy avvenuto col rebuild del 07-10). Il caso MU +0,680 (ensemble, non-fallback, news Micron legittima) è il segnale più alto del giorno ed è arrivato a mercato chiuso: il mattino dopo sarebbe comunque scaduto (>4h).
* Impatto: ~28% dei segnali del giorno (82/294) non entra mai nel processo decisionale; budget LLM speso su segnali non azionabili; il pattern è confermato per il 6° giorno (07-02, 03, 07, 08, 09).
* Severità: Medium
* Confidenza: High
* Azione consigliata: decidere esplicitamente il destino dei segnali late-day: (a) fermare il sentiment alle ~20:00, o (b) valutarli in un ciclo pre-market del giorno dopo con logica dedicata (età > 4h li rende inutilizzabili con la config attuale). Con il fix SKIP_STALE deployato, verificare che dal 07-10 compaia il logging.
* Test/monitor consigliato: metrica giornaliera "segnali generati dopo l'ultimo ciclo" + "di cui sopra soglia".

### [DAY-008] Force-close stop-loss (XOM) senza riga in `execution_decisions` né audit; `orders_count` lo esclude

* Tipo: Bug (di auditabilità, non di esecuzione)
* Area: Orders / Data
* Evidenza:
  * file/log/tabella: `execution_decisions` (nessuna riga XOM il 07-09), `portfolio_cycles` id 343 (`orders_count=1`, `final_orders` solo CVX), `trades` id 243 (`exit_reason=stop_loss`), Alpaca order dca45d82
  * timestamp: 14:22:00–14:22:07
* Descrizione: il path FIX-C (stop-loss sintetico) force-chiude la posizione **bypassando** il combiner: l'ordine reale arriva al broker e aggiorna `trades`, ma non produce alcuna riga decisionale né di audit, e non è contato in `orders_count`. Chi ricostruisce la giornata dal solo Decision Log vede 1 ordine dove ne sono partiti 2. È l'unico caso odierno della categoria "ordine senza decisione tracciata" della checklist Fase 8.
* Impatto: audit trail incompleto sul path più critico (perdite forzate); metriche per-ciclo sottostimate.
* Severità: Medium
* Confidenza: High
* Azione consigliata: scrivere una `execution_decisions` sintetica (decision=`STOP_LOSS`) e una riga audit per ogni force-close; includerlo in `orders_count` o in un campo dedicato.
* Test/monitor consigliato: reconciliation giornaliera "ordini Alpaca vs decisioni con order_id" con alert sui non appaiati (oggi: 1/2 non appaiato).

### [DAY-009] `/api/trades` restituisce record order-shaped con campi errati/di default (XOM: `exit_reason=portfolio_sell`, score 0, regime_mult 1, entry null)

* Tipo: Bug
* Area: Frontend / Data
* Evidenza:
  * file/log/tabella: `GET /api/trades?limit=2` → id = UUID ordine Alpaca, `entry_time/entry_price/net_pnl=null`, XOM `exit_reason="portfolio_sell"`; DB `trades` id 243 → `exit_reason='stop_loss'`, net_pnl -50,58
  * timestamp: momento dell'analisi (07-10)
* Descrizione: l'endpoint `/trades` non riflette la tabella `trades` del DB ma una ricostruzione dagli ordini broker con default fabbricati: l'exit_reason vero (stop_loss) è sostituito da "portfolio_sell", PnL e prezzi d'ingresso sono null, score/regime_mult sono costanti fittizie. Chi audita (o la UI) tramite l'API vede dati diversi — e più benigni — di quelli reali.
* Impatto: auditabilità/UI fuorviante; nel caso specifico nasconde che il sistema ha subito uno stop-loss.
* Severità: Medium
* Confidenza: High
* Azione consigliata: far leggere all'endpoint la tabella `trades` (join con ordini solo per lo stato), o rinominarlo `/orders_history`.
* Test/monitor consigliato: test di contratto API: per un trade chiuso con stop_loss, `/trades` deve riportare `exit_reason=stop_loss` e net_pnl ≠ null.

### [DAY-010] Segnale "ensemble" accettato con una sola risposta modello (COST, id 2490)

* Tipo: Ambiguità / Rischio
* Area: LLM
* Evidenza:
  * file/log/tabella: `sentiment_signals` id 2490 (COST, -0,12, model_id `ensemble:kimi-k2.6:cloud`, fallback_used=false) con **1 sola** riga `llm_responses` (kimi); tutte le altre 59 aggregazioni hanno 2 risposte
* Descrizione: quando uno dei due modelli non risponde (errore/timeout — non verificabile, log persi), l'aggregatore può produrre comunque un segnale marcato ensemble non-fallback basato su un singolo modello, senza possibilità di check di divergenza. Caso singolo oggi, score piccolo, nessun impatto decisionale.
* Impatto: potenziale bypass silenzioso del principio di ensemble in giornate con instabilità di un provider.
* Severità: Low
* Confidenza: High sul dato, Media sull'interpretazione del path
* Azione consigliata: richiedere ≥2 risposte eligible per marcare un segnale come ensemble; altrimenti degradare esplicitamente a FinBERT o marcare `single_model=true`.
* Test/monitor consigliato: conteggio giornaliero segnali ensemble con <2 risposte.

### [DAY-011] Risorse di audit della procedura: token Bearer rifiutato (serve `X-API-Key`); `/api/health.mode` ancora "backtest"

* Tipo: Ambiguità / Corretto-con-nota
* Area: Ops / Frontend
* Evidenza:
  * `curl -H "Authorization: Bearer <ADMIN_API_KEY>"` → `{"detail":"Invalid or expired JWT token"}`; `src/api/auth.py` accetta il medesimo valore solo come header `X-API-Key`; `GET /api/health` → `{"status":"ok","mode":"backtest"}` (issue nota dal 07-07, non fixata)
* Descrizione: la chiave fornita nelle istruzioni operative è l'`ADMIN_API_KEY` statica, che il backend accetta esclusivamente via header `X-API-Key`; passata come Bearer viene interpretata come JWT e rifiutata. L'analisi API è stata completata con l'header corretto. `health.mode=backtest` resta hardcoded su uno stack che opera in paper.
* Impatto: nessuno sui dati (workaround immediato); rischio di false conclusioni "API down" in run automatizzate future.
* Severità: Low
* Confidenza: High
* Azione consigliata: aggiornare il runbook/prompt della sessione forense con `X-API-Key`; fixare `health.mode`.
* Test/monitor consigliato: — (documentale).

---

## 11. False Positive o Aree Risultate Corrette

- **"SELL con sentiment positivo" (bug A5)**: CVX venduto con score residuo +0,275 → **corretto**, expiry FIX-F (age 19,1h > 4h) con reason esplicita, non inversione di segno.
- **Stop-loss XOM**: trigger a -2,04% contro soglia 2% → **corretto e puntuale** (primo ciclo utile); il meccanismo sintetico FIX-C ha funzionato in produzione.
- **"Cicli portfolio fermi alle 19:52"**: sospetto iniziale di gap → **falso positivo**: 24 cicli 14:07–19:52 è il pattern identico di 07-07 e 07-08 (fine finestra by-design).
- **"Avvio GDELT ritardato alle 15:03"**: → **falso positivo come anomalia del giorno**: GDELT parte ~15:00 anche il 07-07 e 07-08 (pattern strutturale della fonte, distinto dal ritardo benzinga del 07-08).
- **"Score < 0,05 che hanno generato ordini"**: `trades.score=0,05` sui 2 trade è il **target weight** (semantica nota, [DAY-004] del report 07-08), non il sentiment; `signal_score` reale 0,455/0,4375. Nessun ordine da score piccoli.
- **Ordini identici nello stesso minuto**: i 2 sell alle 14:22:05 sono simboli diversi su path diversi → nessuna race condition.
- **Fallback=100% prolungato (Ollama down)**: assente — tentativi ensemble riusciti in ogni fascia oraria; Ollama up tutto il giorno.
- **Fix divergenza ensemble**: **verificato funzionante il primo giorno di deploy** — 0 fallback per divergenza su 60 tentativi (max std 0,177 vs soglia 0,40).
- **Regime detector**: sideways/0,7 alle 13:30:45, 2 LLM concordi — nessun fallback ×0,2.
- **Nessun timestamp futuro, nessun `published_at` mancante, nessun duplicato cross-provider.**
- **Budget LLM**: 0,097 USD, mai esaurito.
- **NAV bridge riconciliato** (-64,81 vs -70,74 realizzato, delta spiegato dal MTM già nello snapshot 07-08).

## 12. Dati Mancanti o Non Accessibili

| Dato richiesto | Stato | Cosa servirebbe |
|---|---|---|
| Log applicativi 07-09 (latenza LLM, retry, eccezioni, cause dei 234 ensemble non tentati) | **Perso** — recreate container 07-10 07:52 ([DAY-003]) | Log shipping persistente |
| Trigger esatto delle 2 escalation loss-feedback (14:07, 18:37) | **Non ricostruibile** — Redis `feedback:*` resettato il 07-10, nessuna persistenza DB degli adjustment | Persistenza a DB degli eventi loss-feedback |
| Conteggio segnali scartati per staleness | **Non disponibile** — `SIGNAL_STALE_SKIP` rotto dal 07-06 ([DAY-002]) | Fix del path audit |
| Root cause `forward_return`=0 dal 07-06 | **Non determinabile** (log persi) | Run manuale strumentata di `run_forward_return_worker` |
| Prezzi intraday XOM 14:07–14:22 (per validare che lo stop non potesse scattare al ciclo precedente) | Non disponibili in sessione | Alpaca historical bars 1-min |
| MTM EOD esatto per posizioni (n/a oggi: nessuna aperta) | — | — |
| Latenza media per chiamata LLM | **Non disponibile** (log persi) | — |

## 13. Raccomandazioni Immediate

1. **Verificare nei prossimi 2 giorni l'effetto dei fix deployati il 07-10**: (a) decay 24h della soglia loss-feedback verso 0,30; (b) comparsa del logging SKIP_STALE; (c) S1 che produce pesi. Il 07-09 dimostra il costo pieno del ratchet (0 BUY con segnali legittimi a 0,546).
2. **[DAY-005] è la scoperta nuova più urgente**: senza `forward_return` l'intero loop di misura (IC/ICIR, decay monitor, pesatura modelli, QX-01) è cieco da 4 giorni e ha già auto-applicato pesi su dati vuoti. Diagnosi manuale del worker delle 22:00.
3. **Log shipping**: seconda giornata consecutiva persa per recreate. Implementare prima del prossimo deploy (raccomandazione ripetuta dal report 07-08, non attuata).
4. **Mis-attribution ([DAY-004])**: il near-miss MS (0,465 > base 0,45) mostra che il rischio è ora quantitativamente vicino alle soglie; prioritizzare il filtro di prominenza.
5. Aggiungere trail decisionale al path stop-loss ([DAY-008]) e correggere `/api/trades` ([DAY-009]).

## 14. Test o Monitor da Aggiungere

- Alert "coverage `forward_return` T-1 = 0%" (23:00 UTC) + guard anti-auto_apply su ICIR tutto-zero.
- Persistenza DB (+ alert) degli eventi loss-feedback: timestamp, trigger, soglia prima/dopo.
- Reconciliation giornaliera ordini Alpaca ↔ `execution_decisions.order_id` (oggi avrebbe segnalato XOM).
- Alert "0 righe `audit_log` in giorno con ordini eseguiti".
- Metrica "segnali post-ultimo-ciclo" e "% news con company name assente dal titolo" (già raccomandata il 07-08).
- Test contratto `/api/trades` su exit_reason/net_pnl.
- Export log automatico pre-deploy.

## 15. Ticket Tecnici Suggeriti

1. **[High]** Diagnosi e fix `run_forward_return_worker`: coverage 0% dal 07-06, degrado dal 06-29; includere guard su auto_apply con ICIR nullo ([DAY-005], [DAY-006]).
2. **[High]** Filtro di prominenza per `org_lookup` GDELT **e** validazione dei tag `source_metadata` Benzinga (SPCX assente da `ticker_lookup` ma segnalato); riduce sia i falsi BUY sia la diluizione EMA dei segnali legittimi ([DAY-004]).
3. **[High]** Fix `SIGNAL_STALE_SKIP` (4° giorno) + azioni audit per chiusure trade e adjustment loss-feedback ([DAY-002]).
4. **[Medium]** Decision/audit row per il path stop-loss FIX-C ([DAY-008]).
5. **[Medium]** `/api/trades` deve leggere la tabella `trades` ([DAY-009]).
6. **[Medium]** Log shipping persistente pre-deploy ([DAY-003] — riportato dal 07-08, recidiva).
7. **[Low]** Ensemble con <2 risposte: marcatura esplicita o degrado a FinBERT ([DAY-010]).
8. **[Low]** Runbook sessione forense: header `X-API-Key`; fix `health.mode` hardcoded ([DAY-011]).
9. **[Low]** Reason SKIP con valore assoluto dello score (cosmetico, §9).

## 16. Stato Sistema

- **Ollama**: **up per l'intera giornata** — 0 ore di downtime rilevabili: tentativi ensemble riusciti in tutte le 8 fasce orarie (60 tentativi, 119 risposte); 1 sola risposta mancante (glm su COST, 1 evento). Il fix divergenza (0,30→0,40) ha azzerato i fallback da divergenza.
- **FinBERT fallback rate**: **79,6%** (234/294) — in rialzo vs 71,8% del 07-08 e dentro la banda cronica 70–86%; composizione cambiata: oggi è **100% capacity-driven** (ensemble mai tentato), 0% divergence-driven.
- **Worker restart events**: **0 restart durante il giorno target**. Due eventi di recreate ai bordi: `worker`/`worker-inference`/`api`/`beat` ricreati il 07-09 **12:07:38** (pre-market, deploy fix divergenza — già rilevato nel report 07-08) e di nuovo il 07-10 **07:52:04** (deploy fix S1/loss-feedback, con perdita dei log del 07-09); `frontend` ricreato il 07-09 **15:07:48** (deploy fix Quality page); `postgres`/`redis` stabili dal 07-07 14:38.
- **Deployment**: 2,2% a inizio giornata (CVX+XOM) → **0% dalle 14:22 a fine giornata**; NAV 110.057,22 (-64,81 sul giorno).
