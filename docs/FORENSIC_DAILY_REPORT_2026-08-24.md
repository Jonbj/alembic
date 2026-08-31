# Forensic Daily Report — 2026-08-24

> Analisi read-only della seduta di lunedì 2026-08-24. Fuso operativo **UTC**
> (`src/workers/celery_app.py:51-52`, `timezone="UTC"`, `enable_utc=True`) — nessuna
> ambiguità di timezone nel codice; l'ambiguità è invece nelle **finestre cron fisse**
> (vedi [DAY-013]).
> Sessione RTH del giorno: **13:30–20:00 UTC** (EDT, DST attivo).

---

## 1. Executive summary

Il processo end-to-end ha girato senza errori infrastrutturali: 124 news scorate, 248
chiamate LLM tutte andate a buon fine, **zero fallback FinBERT**, Ollama up al 100%,
24 cicli di portafoglio, 9 ordini generati e 9 eseguiti sul broker paper, riconciliazione
DB↔broker perfetta (46 trade aperti = 46 posizioni, nessun orfano, nessun ordine
non tracciato). Nessun ordine fuori orario, nessun duplicato, nessun circuit breaker
violato: esposizione 28–35% contro un tetto del 50%, drawdown 0,63–0,76% contro un
limite del 5%.

Le anomalie sono tutte **a monte**, nella qualità del segnale, e una ha un costo
misurato. L'articolo *"SpaceXAI Taps NVIDIA To Build Faster AI Agents"* — una notizia su
due società **private** — è stato mappato dal provider sul ticker quotato **SPCX** e
contemporaneamente su NVDA; il resolver deterministico ha emesso
`NO_TRADE_LOW_RESOLUTION_CONFIDENCE` e **il verdetto è stato ignorato**. Alle 17:07 sono
partiti due BUY simultanei da $1.883,19 l'uno nati dallo stesso pezzo: SPCX ha chiuso a
**−$21,82**, NVDA a −$4,69.

Il resto è ricorrenza nota: churn intraday su NVDA (due roundtrip da 1h45 nella stessa
seduta), regola "solo il segnale più recente" che rovescia un +0,378 con un −0,015,
51 simboli su 96 senza una riga di news, 76% delle righe scorate provenienti da fan-out
multi-ticker, e `risk_reports` che pubblica un `daily_pnl` di −$527,82 quando il NAV si è
mosso di −$265,74 e il realizzato è −$53,91.

P&L del giorno: NAV **109.864,64 $** (−265,74 $, −0,24%); realizzato S4 **−53,92 $** su
6 chiusure; P&L economico di finestra S1 −211,03 $, S4 −136,05 $.

## 2. Verdict finale

**OK con warning.**

La catena tecnica (ingest → dedup → LLM → segnale → decisione → ordine → fill → posizione
→ riconciliazione) è integra, auditabile e idempotente: ogni ordine sul broker ha la sua
decisione, la sua riga `trades` e la sua posizione, e viceversa. Non c'è un solo ordine
orfano né un fill non riconciliato.

Il warning è sulla **qualità dell'input**: un BUY reale da $1.883 è stato eseguito su un
ticker che il resolver interno del sistema aveva già classificato come non affidabile, e
il sistema non ha alcun meccanismo che ascolti quel verdetto. Non è "processo non
affidabile" perché il difetto è isolato, misurato e circoscritto a un componente
dichiaratamente in shadow-mode (QX-01, *measurement before enforcement*); è però la prima
volta nella finestra che quel gap produce una perdita tracciabile a una singola riga di DB.

---

## 3. Timeline del 2026-08-24 (tutti gli orari UTC)

| Ora | Componente | Evento | Esito | Fonte |
|---|---|---|---|---|
| 13:30:51 | `regime_detector` | Rilevazione regime su VIX 16,01 / curva +0,5 / momentum SPY 20g +3,20% | `bull`, multiplier **1.0**, 2 modelli concordi (conf. 0,72 / 0,82), `disagreement=false` | Redis `regime:current` |
| 13:30–14:00 | — | **Nessun task attivo**: ingest, sentiment e portfolio-cycle partono da `hour="14-21"` UTC | 30 min di sessione non coperti | `celery_app.py:151,210` |
| 14:00:36 | `sentiment` | Primo ciclo di scoring | primo segnale (QQQ −0,2275) | `sentiment_signals` |
| 14:00–19:45 | `run-news-ingestion` (\*/15) | 2.348 item letti → **124 righe** in `news_log` | 3.178 dup + 1.634 no-ticker + 232 stale + 127 non-tradable scartati | `ingestion_stats_daily`, `news_queue_drops` |
| 14:07:00 | `portfolio-cycle` #1 | S1+S4, 4 target | 3 SKIP_FALLBACK, 4 SKIP_PYRAMIDING, 0 ordini | `portfolio_cycles` id-ciclo 14:07 |
| 14:07:11 | S4 | NFLX: segnale `single:glm-5.2:cloud` +0,320 conf 0,80 (generato **2026-08-21 16:45**, 69,4 h) escluso dal ranking BUY per #108 | `SKIP_FALLBACK` | `execution_decisions` |
| 14:22:00 | S4 → broker | **SELL NFLX** 22,9390 @ 80,22 — `[fallback_filtered]`, peso azzerato dal filtro #108 | filled 14:22:11, net **−3,09 $** | ordine `14f14193…`, trade 751 |
| 14:30:22 | LLM | **MU +0,539** (glm 0,80/0,85 · gpt-oss 0,40/0,70) — score più alto della giornata | segnale 8744 | `sentiment_signals` |
| 14:37:00 | S4 → broker | **BUY NVDA** notional 1.883… (1.877,68 $) su segnale 8742 (+0,380 al momento del ranking) | filled @ 210,24, qty 8,9311 | ordine `8d3f364f…`, trade 782 |
| 14:37:09 | S4 | MU +0,539 e SOXX +0,360 bloccati da `SKIP_PYRAMIDING` (già a libro dal 28/07) | peso non allocato 2,3% / 2,5% | `execution_decisions` |
| 14:52:09 | `protective stop` | Stop su NVDA per **qty 8** (posizione 8,9311 → copertura 89,6%), 15 min dopo l'ingresso | poi `canceled` | ordine `fcc8e444…` |
| 15:30:57 | LLM | **BABA −0,402**, primo dei 5 segnali ribassisti sopra gate della giornata | nessun ordine (long-only) | `sentiment_signals` |
| 16:00:14 | LLM | **DIS +0,413** ma `single:gpt-oss:20b-cloud` → escluso dal ranking BUY (#108) | nessun ordine | segnale 8779 |
| 16:22:00 | S4 → broker | **SELL NVDA** 8,9311 @ 210,99 — `[below_entry_gate]`, segnale delle 15:15 sceso a **+0,192** | filled, net **+6,31 $** | trade 782 chiuso, tenuta 1h45 |
| 16:48:43 | Benzinga | Pubblicato *"SpaceXAI Taps NVIDIA To Build Faster AI Agents"* | **fan-out su NVDA (8796) e SPCX (8797)** | `news_log` |
| 17:00:02 | `ticker_resolver` | SPCX → `NO_TRADE_LOW_RESOLUTION_CONFIDENCE` (confidence 0,60) | **verdetto non applicato** | `news_resolved_entities` |
| 17:00:40/49 | LLM | NVDA **+0,378**, SPCX **+0,320** dallo stesso articolo | segnali 8796, 8797 | `sentiment_signals` |
| 17:07:00 | S4 → broker | **BUY SPCX** 1.883,19 $ @ 136,32 · **BUY NVDA** 1.883,19 $ @ 209,99 (stesso ciclo, stesso articolo) | entrambi filled entro 500 ms | trade 783, 784 |
| 17:22:00 | S4 → broker | **SELL AVGO** (`no_signal`, net −14,07 $) · **SELL HOOD** (`unknown`, net −16,56 $) | filled | trade 755, 756 |
| 17:22:06 | `protective stop` | Stop NVDA qty **8**/8,9680 e SPCX qty **13**/13,8144 | poi `canceled` | ordini `8dae075a…`, `d882701f…` |
| 17:22–19:07 | S4 | SPCX segnale 8797 riusato: **8 × `SIGNAL_DUPLICATE_SKIP`** — il guard anti-riacquisto funziona | nessun BUY ripetuto | `audit_log` |
| 18:52:00 | S4 → broker | **SELL NVDA** 8,9680 @ 209,51 — `[below_entry_gate]`, segnale delle 18:00 a **−0,015** | filled, net **−4,69 $** | trade 784, tenuta 1h45 |
| 19:15:23 | LLM | SPCX **+0,005** su *"AI's $220 Billion Bond Boom"* (altro fan-out) | segnale 8839 | `sentiment_signals` |
| 19:37:00 | S4 → broker | **SELL SPCX** 13,8144 @ 134,88 — `[below_entry_gate]` | filled, net **−21,82 $** | trade 783, tenuta 2h30 |
| 19:45:48 | `sentiment` | Ultimo scoring della giornata (NVDA +0,278) | `consecutive_fallback` resettato a 0 | `fallback_counters` |
| 19:52:00 | `portfolio-cycle` #24 | Ultimo ciclo | 0 ordini | `portfolio_cycles` |
| 20:00:00 | `portfolio_monitor` | Snapshot di chiusura | NAV **109.864,64**, cash 78.865,09, unrealized +1.093,86, **46 posizioni** | `portfolio_monitor_snapshots` |
| 21:00:00 | `decay-monitor` | 12 righe (S1/S2/S4 × 4 metriche) | **3 CRITICAL + 2 CRITICAL hit_rate**, valori identici fra strategie | `decay_reports` |
| 22:30:01 | `risk-monitor` | Report giornaliero | ALERT "portfolio drawdown 17.9% exceeds 10%", `daily_pnl` **−527,82 $** | `risk_reports` id 73 |

**Cicli:** 24 portfolio-cycle regolari a :07/:22/:37/:52 da 14:07 a 19:52, nessuno saltato,
`constraints_fired` vuoto in tutti e 24.

---

## 4. Tabella news ingest

### Per fonte

| Fonte | Letti | In coda | Duplicati | No-ticker | Stale | Parse fail | Righe in `news_log` | Articoli unici | Effective-timely |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `alpaca_benzinga` | 699 | 373 | **3.178** | 0 | 209 (età media 31,1 h) | 0 | 111 | 44 | 15 (34,1%) |
| `gdelt_gkg` | 1.649 | 17 | 0 | 1.634 | 23 (età media 67,2 h) | 0 | 13 | 13 | 13 (100%) |
| **Totale** | **2.348** | **390** | **3.178** | **1.634** | **232** | **0** | **124** | **57** | **28** |

Scarti aggiuntivi in fase `sentiment`: 127 `not_tradable` (`alpaca_benzinga`).

### Copertura e qualità

| Metrica | Valore | Fonte |
|---|---|---|
| Copertura temporale (fetch) | 14:00 → 19:45 UTC, buco 13:30–14:00 | `news_log` |
| Latenza publish → fetch | mediana **53,0 min**, media 48,9, max 115,8 | `news_log` |
| Timestamp futuri / `published_at > fetched_at` | **0 / 0** | `news_log` |
| Ticker distinti coperti | 45 su 96 (**51 simboli watchlist a zero news**) | dossier `mercato.watchlist_zero_news` |
| Copertura effective-timely | **21/96 ticker (21,9%)** | dossier `copertura_articoli` |
| Mapping per rilevanza | ISSUER_SPECIFIC 29 · **UNKNOWN 95** · SECTOR_MACRO 0 | dossier |
| Mapping fan-out extra | **67 su 124 righe (76,5%)** | dossier `cause_del_giorno.quota_righe_fanout` |
| Duplicati di sindacazione per ticker | 0 | dossier |
| Duplicati cross-provider | 0 (nessun titolo condiviso fra Benzinga e GDELT) | query su `news_log` |
| Metodo di estrazione | `source_metadata` 111 · `org_lookup` 13 | `news_log.extraction_method` |
| Verdetti resolver | **251, di cui 127 `NO_TRADE_NOT_TRADABLE` + 124 `NO_TRADE_LOW_RESOLUTION_CONFIDENCE` — zero approvazioni** | `news_resolved_entities` |

### Fan-out: i 5 articoli più moltiplicati

| Titolo (troncato) | Ticker generati |
|---|---|
| Memory Stocks Slide as Trump Threatens 50% Tariffs on Canadian Autos… | **13** — AMD, F, INTC, IWM, MRVL, MU, NVDA, QQQ, WDC, XLE, XLF, XLK, XLV |
| Samsung Crash Brings Semi Selling; Nvidia Earnings Ahead… | 9 — AAPL, AMZN, GOOGL, META, MSFT, NVDA, QQQ, SPY, TSLA |
| Trump's 50% Canada Auto Tariff Shock: These ETFs Could Be… | 8 — AAPL, F, GM, GOOGL, MSFT, MU, NVDA, TSLA |
| 10 Information Technology Stocks Whale Activity… | 6 — AAPL, ADBE, CRM, INTC, MU, NVDA |
| EXCLUSIVE: How AI's $220 Billion Bond Boom Competes… | 5 — AMZN, GOOGL, NVDA, PLTR, **SPCX** |

Un articolo sui dazi auto ha generato un segnale su **XLV** (ETF sanitario) e su **IWM**.

### Top news per impatto sul segnale

| Ora | Articolo | Ticker | Score | Conseguenza |
|---|---|---|---|---|
| 16:48 | SpaceXAI Taps NVIDIA To Build Faster AI Agents | **SPCX** | +0,320 | **BUY 1.883,19 $ → −21,82 $** |
| 16:48 | SpaceXAI Taps NVIDIA To Build Faster AI Agents | **NVDA** | +0,378 | **BUY 1.883,19 $ → −4,69 $** |
| 13:16 | Dan Ives Says Nvidia's 15% AI Server Price Hike Is Bullish… | NVDA | +0,316 | **BUY 1.877,68 $ → +6,31 $** |
| 13:12 | Micron CEO Sounds Alarm on AI Memory Crunch… | MU | **+0,539** | bloccato da anti-pyramiding |
| 15:45 | Disney Provides a Peek at the Next Phase… | DIS | +0,413 | escluso dal ranking (#108) |

---

## 5. Tabella performance modelli LLM

| Modello | Richieste | Successi | Errori | Timeout | Output invalido | `eligible=true` persistito | Polarity media | Polarity min/max | Confidence media |
|---|---:|---:|---:|---:|---:|---:|---:|---|---:|
| `glm-5.2:cloud` | 124 | 124 | 0 | 0 | 0 | **33 (26,6%)** | +0,0327 | −0,700 / +0,800 | 0,3004 |
| `gpt-oss:20b-cloud` | 124 | 124 | 0 | 0 | 0 | **33 (26,6%)** | +0,0339 | −0,680 / +0,800 | 0,4328 |
| `finbert` (fallback) | **0** | — | — | — | — | — | — | — | — |

**Latenza: non misurabile.** `llm_responses` non ha una colonna di latenza e i log dei
container sono stati azzerati dal redeploy del 2026-08-25 11:26 → [DAY-014].

### Etichetta d'ensemble sui 124 segnali

| `model_id` | N | `fallback_used` | Righe `llm_responses` con `eligible=true` |
|---|---:|---|---:|
| `ensemble:glm-5.2:cloud+gpt-oss:20b-cloud` | 81 (65,3%) | false | 33 segnali su 81 hanno 2 righe eligible; **48 ne hanno 0** |
| `single:gpt-oss:20b-cloud` | 39 (31,5%) | **true** | 0 |
| `single:glm-5.2:cloud` | 4 (3,2%) | **true** | 0 |

`fallback_used=true` su 43 segnali (34,7%) **non significa FinBERT**: significa che
l'aggregatore ha scartato uno dei due modelli sotto `min_confidence`. FinBERT non è mai
stato invocato. Vedi [DAY-019].

### Distribuzione degli score

| Statistica | Valore |
|---|---|
| Score medio | +0,0227 |
| Score min / max | −0,4020 (BABA) / **+0,5391 (MU)** |
| `ensemble_std` medio | 0,0501 |
| Segnali con \|score\| ≥ 0,30 (gate) | **14** su 124 (11,3%) — 9 rialzisti, **5 ribassisti** |
| Segnali con \|score\| < 0,05 | maggioranza (score medio 0,023) |
| Pesi ensemble attivi | glm-5.2 **0,70** / gpt-oss **0,30** (applicati 2026-08-24 04:00, `auto_apply`) |
| ICIR purificato usato per i pesi | glm +0,1045 · gpt-oss **−0,0288** (negativo, ma resta al 30%) |
| Spesa LLM | 0,1394 $ (71.711 token in / 8.874 out), budget non esaurito |

### Massimo disaccordo fra modelli

| Ticker | Score finale | `ensemble_std` | glm-5.2 (pol/conf) | gpt-oss (pol/conf) |
|---|---:|---:|---|---|
| LLY | +0,322 | 0,283 | 0,40 / 0,45 | **0,80** / 0,70 |
| MU | +0,539 | 0,283 | **0,80** / 0,85 | 0,40 / 0,70 |
| NVDA (8791) | +0,178 | 0,283 | 0,20 / 0,40 | 0,60 / 0,60 |
| SPCX (8797) | +0,320 | 0,283 | 0,60 / 0,70 | 0,20 / 0,60 |
| GM | −0,346 | 0,247 | −0,70 / 0,60 | −0,35 / 0,55 |

Il disaccordo massimo della giornata (std 0,283, cioè polarità che differiscono di 0,40)
non ha impedito a **SPCX** di generare un ordine: `ensemble_std` non è un gate d'ingresso.

### Verifica funzionale della catena LLM

| Domanda | Risposta | Evidenza |
|---|---|---|
| L'output LLM è validato prima del signal store? | **Parzialmente**. Schema JSON forzato (`LLMSentimentOutput`) e clamp a [−1,+1]; nessuna validazione semantica del ticker. | `sentiment.py:410,429` |
| L'ensemble gestisce la varianza alta? | **No come gate**. Alta divergenza → fallback/single-model, ma `ensemble_std` non blocca l'ordine. | 8797 std 0,283 → BUY |
| Le news duplicate pesano più volte? | **No** in ingest (3.178 dedup per `duplicate_id`). **Sì** in fan-out: un articolo = N segnali. | [DAY-002] |
| La stessa news può generare segnali multipli? | **Sì, per ticker diversi** — ed è quello che è successo alle 17:07. | trade 783+784 |
| Confidence bassa riduce il peso? | **Sì**: `score = polarity × confidence`, e sotto `min_confidence` il modello esce dall'ensemble. | `sentiment.py:410` |
| I modelli sono chiamati offline/background? | **Sì**. Coda Celery `inference`, concorrenza 1, mai dentro il loop di esecuzione. | `celery_app.py` |
| Un'allucinazione LLM può entrare in decisione? | **Sì.** Il reasoning del segnale SPCX 8754 dice testualmente *"If SPCX is an EV/autonomous-driving-related name…"*: il modello **specula sull'identità del ticker** e lo score entra comunque nel signal store. | [DAY-001] |

---

## 6. Tabella segnali finali per ticker

### I 14 segnali sopra il gate (0,30)

| Ora | Ticker | Score | Conf. | `model_id` | Esito | Ritorno del titolo |
|---|---|---:|---:|---|---|---:|
| 14:30 | MU | +0,430 | 0,70 | ensemble | SKIP_PYRAMIDING | −5,83% |
| 14:31 | **MU** | **+0,539** | 0,78 | ensemble | SKIP_PYRAMIDING | −5,83% |
| 14:31 | SOXX | +0,360 | 0,60 | ensemble | SKIP_PYRAMIDING | −2,67% |
| 14:30 | NVDA | +0,316 | 0,73 | ensemble | **BUY 14:37** | −2,91% |
| 15:30 | BABA | **−0,402** | 0,60 | ensemble | nessun ordine (long-only) | −0,73% |
| 15:45 | F | **−0,310** | 0,59 | ensemble | nessun ordine | −3,33% |
| 16:00 | DIS | +0,413 | 0,75 | `single:gpt-oss` | escluso #108 | **+2,63%** |
| 16:45 | MRVL | +0,368 | 0,65 | ensemble | SKIP_PYRAMIDING | −3,27% |
| 17:00 | LLY | +0,322 | 0,58 | ensemble | SKIP_PYRAMIDING | −0,67% |
| 17:00 | NVDA | +0,378 | 0,70 | ensemble | **BUY 17:07** | −2,91% |
| 17:00 | **SPCX** | +0,320 | 0,65 | ensemble | **BUY 17:07** | +0,24% |
| 19:00 | INTC | **−0,318** | 0,60 | ensemble | nessun ordine | −3,12% |
| 19:30 | F | **−0,310** | 0,58 | ensemble | nessun ordine | −3,33% |
| 19:30 | GM | **−0,346** | 0,58 | ensemble | nessun ordine | −1,08% |

**5 segnali ribassisti sopra gate, tutti col segno corretto sul close-to-close, zero
azionabili** (S4 è long-only). Sul tratto segnale→close però il vantaggio si dissolve:
BABA −0,18%, F +0,68% e +0,10%, INTC −0,56%, GM −0,06%; netto ≈ **+0,30 $** su size tipica
S4. La notizia arriva a movimento già avvenuto → [DAY-018] + [DAY-024].

### Segnali estremi in valore assoluto (top 8)

| Ticker | Score | Conf. | std | Articolo sorgente |
|---|---:|---:|---:|---|
| MU | +0,5391 | 0,775 | 0,283 | Micron CEO Sounds Alarm on AI Memory Crunch |
| MU | +0,4304 | 0,700 | 0,247 | (2° articolo Micron) |
| DIS | +0,4125 | 0,750 | 0,000 | Disney Provides a Peek at the Next Phase |
| BABA | −0,4020 | 0,600 | 0,071 | Alibaba Slides as $10.2B AI Sale Dilutes Investors |
| NVDA | +0,3780 | 0,700 | 0,141 | SpaceXAI Taps NVIDIA |
| MRVL | +0,3683 | 0,650 | 0,247 | Analyst Calls Marvell A Top Chip Pick |
| SOXX | +0,3600 | 0,600 | 0,000 | (fan-out semis) |
| GM | −0,3457 | 0,575 | 0,247 | (fan-out dazi auto) |

### Decisioni per tipo

| Decisione | N | Simboli | `signal_id` NULL |
|---|---:|---:|---:|
| SKIP_THRESHOLD | 566 | 45 | 566 |
| SKIP_FALLBACK | 10 | 9 | 10 |
| SKIP_PYRAMIDING | 10 | 7 | 4 |
| SELL | 6 | 5 | **6** |
| BUY | 3 | 2 | 0 |
| **Totale** | **595** | | **586 (98,5%)** |

---

## 7. Tabella ordini generati / eseguiti

Modalità broker: **paper** (`portfolio_monitor_snapshots.broker_environment='paper'`,
`mode='paper'`, `source='alpaca_paper'`; `TradingClient(paper=True)`). Nessuna ambiguità
paper/live.

| # | Decisione (UTC) | Strat. | Ticker | Azione | Qty / Notional | Prezzo fill | Stato | Segnale causante | Rationale / exit_mechanism | Anomalia |
|---|---|---|---|---|---|---:|---|---|---|---|
| 1 | 14:22:00 | S4 | NFLX | SELL (close) | 22,9390 | 80,22 | **filled** 14:22:11 | 8639 (21/08, 69,4 h) | `fallback_filtered` — #108 | [DAY-019] |
| 2 | 14:37:00 | S4 | NVDA | BUY | notional 1.877,68 → 8,9311 | 210,24 | **filled** 14:37:11 | **8742** (+0,380) | S4 news-driven, peso 2,0% | — |
| 3 | 14:52:09 | S4 | NVDA | SELL (stop protettivo) | **qty 8** su 8,9311 | — | **canceled** | — | stop a copertura 89,6%, posato 15 min dopo l'ingresso | [DAY-016] |
| 4 | 16:22:00 | S4 | NVDA | SELL (close) | 8,9311 | 210,99 | **filled** | segnale 15:15 → +0,192 | `below_entry_gate` | [DAY-003][DAY-004] |
| 5 | 17:07:00 | S4 | **SPCX** | BUY | notional 1.883,19 → 13,8144 | 136,32 | **filled** 17:07:05 | **8797** (+0,320) | S4 news-driven, peso 2,0% | **[DAY-001]** |
| 6 | 17:07:00 | S4 | NVDA | BUY | notional 1.883,19 → 8,9680 | 209,99 | **filled** 17:07:05 | **8796** (+0,378) | S4 news-driven, peso 2,0% | **[DAY-002]** |
| 7 | 17:22:00 | S4 | AVGO | SELL (close) | 5,1360 | 360,59 | **filled** | — | `no_signal` | — |
| 8 | 17:22:00 | S4 | HOOD | SELL (close) | 17,3385 | 106,92 | **filled** | — | `unknown` (post-#184) | — |
| 9 | 17:22:06 | S4 | NVDA | SELL (stop protettivo) | **qty 8** su 8,9680 | — | **canceled** | — | copertura 89,2% | [DAY-016] |
| 10 | 17:22:06 | S4 | SPCX | SELL (stop protettivo) | **qty 13** su 13,8144 | — | **canceled** | — | copertura 94,1% | [DAY-016] |
| 11 | 18:52:00 | S4 | NVDA | SELL (close) | 8,9680 | 209,51 | **filled** | segnale 18:00 → **−0,015** | `below_entry_gate` | [DAY-003][DAY-004] |
| 12 | 19:37:00 | S4 | SPCX | SELL (close) | 13,8144 | 134,88 | **filled** | segnale 19:15 → +0,005 | `below_entry_gate` | [DAY-004] |

**Riconciliazione ordini ↔ decisioni ↔ trade ↔ posizioni: perfetta.**
12 ordini sul broker = 9 filled (= 9 decisioni non-SKIP) + 3 stop protettivi cancellati.
Nessun ordine broker senza decisione, nessuna decisione senza ordine, 3 righe `INSERT trades`
in `audit_log` = 3 BUY. Riconciliazione posizioni: **46 trade aperti / 46 simboli detenuti**,
43 `fully_held` + 3 `partially_wound_down_coheld` (MRVL, NOK, WDC — residui legittimi da
co-detenzione), **0 orfani**, **0 posizioni non tracciate**.

**Idempotenza:** i `client_order_id` sono deterministici — `ambc-buy-<SYM>-<signal_id>` per
gli ingressi (dedup per segnale) e `ambc-sell-<SYM>-<YYYYMMDDTHHMM>` per le uscite (dedup
per slot di ciclo). Un retry Celery non può duplicare un ordine. Confermato lato applicativo
dagli 8 `SIGNAL_DUPLICATE_SKIP` su SPCX 8797 e 1 su NVDA 8742.

**Risk check applicati e superati (tutti e 24 i cicli):** esposizione lorda 28,2%–35,0%
contro limite 50,0%; drawdown corrente 0,63%–0,76% contro limite 5,0%; `regime_mult` 1,0
(regime `bull`); `constraints_fired = []`. Nessun circuit breaker attivato, e nessuno
avrebbe dovuto attivarsi.

---

## 8. Tabella PnL / rendimento

### Portafoglio (fonte: `portfolio_monitor_snapshots`, snapshot 20:00 UTC — broker Alpaca paper)

| Voce | Valore |
|---|---:|
| NAV a chiusura | **109.864,64 $** |
| Equity di chiusura precedente (ven. 21/08) | 110.130,38 $ |
| **Variazione NAV del giorno** | **−265,74 $ (−0,24%)** |
| Cash | 78.865,09 $ |
| Unrealized P&L (tutte le posizioni) | +1.093,86 $ |
| Esposizione lorda | 28,2% |
| Posizioni aperte | 46 |

### P&L realizzato — 6 chiusure, tutte S4

| Trade | Ticker | Ingresso | Uscita | Qty | Gross | Costi | **Net** | Aperta il |
|---:|---|---|---|---:|---:|---:|---:|---|
| 751 | NFLX | 19/08 17:07 @ 80,31 | 24/08 14:22 @ 80,22 | 22,9390 | −2,06 | 1,02 | **−3,09** | prima del 24/08 |
| 755 | AVGO | 20/08 17:07 @ 363,13 | 24/08 17:22 @ 360,59 | 5,1360 | −13,04 | 1,03 | **−14,07** | prima del 24/08 |
| 756 | HOOD | 21/08 17:07 @ 107,82 | 24/08 17:22 @ 106,92 | 17,3385 | −15,52 | 1,04 | **−16,56** | prima del 24/08 |
| 782 | NVDA | 24/08 14:37 @ 210,24 | 24/08 16:22 @ 210,99 | 8,9311 | +6,70 | 0,38 | **+6,31** | **il 24/08** |
| 784 | NVDA | 24/08 17:07 @ 209,99 | 24/08 18:52 @ 209,51 | 8,9680 | −4,30 | 0,38 | **−4,69** | **il 24/08** |
| 783 | SPCX | 24/08 17:07 @ 136,32 | 24/08 19:37 @ 134,88 | 13,8144 | −19,83 | 1,99 | **−21,82** | **il 24/08** |
| | | | | | **−48,05** | **5,84** | **−53,92** | |

- Da posizioni **aperte prima del 24/08**: **−33,72 $** (3 chiusure).
- Da posizioni **aperte il 24/08**: **−20,20 $** (3 chiusure, tutte intraday).
- **Commissioni/costi totali:** 5,84 $ (`trades.cost_usd`, modello `cost_model.yaml`).
- **Slippage: non misurato.** `trades.slippage_est` è una copia identica di `cost_usd` su
  tutte e 6 le righe → [DAY-011]. Query che servirebbe: confronto fra `filled_avg_price` e
  il mid del quote al `submitted_at` — il dato NBBO non è persistito.

### P&L economico di finestra per strategia (`docs/evidence/economic_pnl.json`, mark dal 2026-08-03)

| Strategia | Cumulato al 21/08 | Cumulato al 24/08 | **Delta del giorno** | Capital base | Posizioni |
|---|---:|---:|---:|---:|---:|
| S1 | +823,41 | **+612,38** | **−211,03** | 33.229,16 | 48 |
| S4 | −369,29 | **−505,34** | **−136,05** | 62.445,42 | 44 |
| CONTAMINAZIONE | +95,25 | +95,24 | −0,02 | 8.348,07 | 12 |
| **BOOK** | | | **≈ −347,10** | 104.022,66 | |

Il delta economico (−347,10 $) e la variazione NAV (−265,74 $) non coincidono: il P&L
economico marca solo le posizioni entrate nella finestra dal 2026-08-03 e non include cash,
dividendi e posizioni fuori finestra. Le due misure rispondono a domande diverse ed è
corretto che differiscano; è la terza misura, `risk_reports.daily_pnl = −527,82 $`, a non
essere riconciliabile con nessuna delle due → [DAY-005].

### P&L per ticker (chiusure del giorno)

| Ticker | Net realizzato |
|---|---:|
| NVDA (2 roundtrip) | **+1,62** |
| NFLX | −3,09 |
| AVGO | −14,07 |
| HOOD | −16,56 |
| SPCX | **−21,82** |

---

## 9. Analisi correttezza buy/sell

| Controllo | Esito | Evidenza |
|---|---|---|
| BUY generati solo quando consentito | **OK** | 3 BUY, tutti con `signal_id` valorizzato, score ≥ gate 0,30, `ema_pass=true`, `regime_mult=1.0`, entro RTH |
| SELL / exit generati correttamente | **OK meccanicamente, discutibile come politica** | 6 SELL, tutte con `exit_mechanism` popolato; 4 su 6 sono uscite a peso zero, non contro-segnali |
| Stop-loss rispettati | **Parziale** | 3 stop protettivi posati, tutti sulla sola **parte intera** della quantità (89,2%–94,1% di copertura) e con **15 min di ritardo** rispetto all'ingresso → [DAY-016]. `stop_decisions` vuota per il giorno: nessuno stop è mai scattato |
| Signal flip rispettato | **OK, ma con banda zero** | NVDA da +0,378 a −0,015 → SELL. Corretto per specifica; il problema è l'assenza di banda → [DAY-003] |
| Max holding days rispettato | **OK** | tenute 1h45 – 117h, nessuna oltre il limite |
| Rebalance band rispettata | **N/A** | nessun rebalance S1 il 24/08 (frequenza `MONTHLY` post-#185, corretto) |
| Ordini duplicati | **Nessuno** | `client_order_id` deterministici; 9 `SIGNAL_DUPLICATE_SKIP` a prova che il guard ha lavorato |
| Ordini contrari ravvicinati senza rationale | **Presenti ma motivati** | NVDA BUY 14:37 → SELL 16:22 → BUY 17:07 → SELL 18:52. Ogni transizione ha `reason` e `signal_id` tracciabile. Roundtrip minimo **1h45**, nessuno sotto i 30 min |
| Pyramiding (>3 BUY senza SELL) | **Nessuno** | il guard P0-05 ha bloccato 10 tentativi su 7 simboli |
| Ordini su ticker non consentiti | **Nessuno formalmente** — SPCX è in watchlist (`config/trading.yaml:119`, gruppo `etf_broad`) | ma il *contenuto* che lo ha attivato non riguardava l'emittente → [DAY-001] |
| Ordini fuori orario | **Nessuno** | primo ordine 14:22, ultimo 19:37, RTH 13:30–20:00 |
| Trade su dati stale | **Nessuno per gli ingressi** | i 3 BUY nascono da segnali di 6, 6 e 6 minuti. Un'uscita (NFLX) è stata valutata su un segnale di 69,4 h, preservato da FIX-D per posizione aperta: comportamento previsto |
| Trade con output LLM invalido | **Nessun output malformato** | 248/248 risposte parsate. Un output **semanticamente** dubbio è però passato → [DAY-001] |
| Trade con circuit breaker attivo | **N/A** | nessun breaker attivo; `trading_blocked=False`, account `ACTIVE` |
| Trade su strategia disabilitata | **Nessuno** | solo S1 e S4 in `strategies_run` in tutti i 24 cicli. S2 non gira (ma compare ancora in `decay_reports` → [DAY-006]) |
| Coerenza paper/live | **OK e inequivocabile** | `broker_environment='paper'` su tutti gli 82 snapshot |
| Idempotenza su retry Celery | **OK** | vedi §7 |
| Riconciliazione ordini/fill/posizioni | **OK, 46/46** | `scripts/reconcile_open_trades_vs_broker.py`, exit code 0 |
| SELL con sentiment positivo (bug A5) | **1 caso formale** | SPCX venduto alle 19:37 con l'ultimo segnale a **+0,005** — positivo ma sotto gate. È il ramo `below_entry_gate`, non un flip: comportamento previsto, non il bug A5 |

---

## 10. Anomalie trovate

### [DAY-001] BUY da $1.883 su SPCX generato da un articolo su società private, col verdetto `NO_TRADE` del resolver ignorato

* Tipo: **Bug**
* Area: **News / LLM**
* Evidenza:
  * file/log/tabella: `news_log` id 8797 · `news_resolved_entities` · `sentiment_signals` id 8797 · `execution_decisions` id 13959 · `trades` id 783
  * timestamp: articolo 2026-08-24 16:48:43 UTC · verdetto resolver 17:00:02 · ordine 17:07:05 · uscita 19:37
  * snippet/query:
    ```sql
    SELECT candidate_ticker, decision, resolution_confidence, extraction_method
    FROM news_resolved_entities
    WHERE created_at >= '2026-08-24' AND created_at < '2026-08-25'
      AND candidate_ticker = 'SPCX';
    -- 4 righe, tutte NO_TRADE_LOW_RESOLUTION_CONFIDENCE, confidence 0.60
    ```
    Titolo: *"SpaceXAI Taps NVIDIA To Build Faster AI Agents"*. Reasoning del segnale:
    *"Deploying NVIDIA Vera CPUs to expand Grok infrastructure signals direct capex
    investment that enhances SPCX's agentic AI capabilities…"*.
    Su un altro articolo dello stesso giorno (segnale 8754) il modello scrive:
    *"**If SPCX is an EV/autonomous-driving-related name**, Tesla's difficulty…"*.
* Descrizione: i 4 articoli mappati su SPCX il 24/08 parlano di SpaceX/SpaceXAI (società
  **non quotate**), di Anthropic, di Tesla Cybercab e del mercato obbligazionario AI.
  Nessuno riguarda l'emittente quotato con ticker SPCX. Il tag arriva dal provider
  (`extraction_method='source_metadata'`, cioè Benzinga). Il resolver deterministico —
  quello che `CLAUDE.md` descrive come la difesa contro l'errore peggiore, l'ordine sul
  titolo sbagliato — ha correttamente emesso `NO_TRADE_LOW_RESOLUTION_CONFIDENCE` su tutti
  e quattro, e il suo verdetto **non è collegato al path di scoring**: nessun consumatore
  legge `news_resolved_entities`. In un caso l'LLM ammette esplicitamente di non sapere
  cosa sia SPCX e produce comunque uno score che supera il gate.
  Aggravanti sull'osservabilità: (a) il resolver ha emesso **251 verdetti nella giornata e
  **tutti e 251 sono `NO_TRADE`** (127 `NOT_TRADABLE` + 124 `LOW_RESOLUTION_CONFIDENCE`) —
  zero approvazioni, quindi la sua confidence non è calibrata e non è utilizzabile come gate
  neppure volendo; (b) **tutte le 251 righe hanno `news_log_id = NULL`**, quindi il verdetto
  non è joinabile all'articolo che giudica se non per timestamp+ticker.
* Impatto: ordine reale da 1.883,19 $ (1,7% del NAV) su un titolo scelto da un mismatch di
  entità, chiuso in perdita a **−21,82 $**. È esattamente lo scenario che la sezione
  "Ticker Resolution" di `CLAUDE.md` definisce *worst-case error*. Il precedente è già nel
  codice: `portfolio_scheduler.py:4826` cita *"SPCX −0.573 fallback → −20.23 loss on
  2026-07-01"*.
* Severità: **High**
* Confidenza: **High**
* Azione consigliata: **remediation ticket di correttezza** (passa il test di esenzione
  della carta d'osservazione: senza correzione, ogni giornata futura in cui un fan-out
  colpisce un ticker mal risolto produce P&L attribuito a S4 che misura un difetto di
  risoluzione, non l'alpha della news). Due interventi, entrambi *senza* toccare tarature:
  (1) popolare `news_resolved_entities.news_log_id` così che il verdetto sia auditabile;
  (2) far scrivere il verdetto del resolver in `news_log` come colonna d'ombra, per poter
  misurare — sul golden set QX-01 — quanto costerebbe applicarlo. L'**enforcement** resta
  gated e fuori dal freeze.
* Test/monitor consigliato: contatore giornaliero `ordini_su_ticker_con_verdetto_NO_TRADE`;
  alert se > 0. Test di regressione: un articolo il cui unico soggetto è una società privata
  non deve produrre un segnale tradabile sul ticker omonimo.

### [DAY-002] Un solo articolo fan-out ha generato due BUY simultanei per 3.766 $ nello stesso ciclo

* Tipo: **Anomalia**
* Area: **Signal / Orders**
* Evidenza:
  * file/log/tabella: `news_log` id 8796 e 8797 · `execution_decisions` id 13959, 13960 · `trades` 783, 784
  * timestamp: 2026-08-24 17:07:00 UTC (stesso `tick_time` per entrambe le decisioni)
  * snippet/query:
    ```sql
    SELECT id, ticker, published_at, left(title,60) FROM news_log WHERE id IN (8796,8797);
    -- entrambe: 2026-08-24 16:48:43 | 'SpaceXAI Taps NVIDIA To Build Faster AI Agents'
    ```
* Descrizione: 67 dei 124 mapping della giornata (**76,5%**) sono fan-out extra. Il caso
  delle 17:07 è quello con conseguenza: lo stesso pezzo Benzinga è stato scorato due volte
  (NVDA +0,378, SPCX +0,320), entrambi gli score hanno superato il gate ed entrambi sono
  finiti nei top-N del ranker nello stesso ciclo. Il portafoglio ha così concentrato **3.766,38 $
  (3,4% del NAV) su un'unica fonte informativa**, che il combiner tratta come due segnali
  indipendenti. Caso estremo della giornata: l'articolo sui dazi auto canadesi ha generato
  13 segnali, fra cui XLV (ETF sanitario) e IWM.
* Impatto: la diversificazione dichiarata dal combiner è fittizia sulle posizioni nate da
  fan-out; il rischio di concentrazione informativa non è misurato da nessun vincolo
  (`constraints_fired` è vuoto in tutti e 24 i cicli). Costo del giorno sulla gamba NVDA:
  −4,69 $ (la gamba SPCX è prezzata su [DAY-001] per non contarla due volte).
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: nessuna taratura durante il freeze. Registrare in `portfolio_cycles`
  il `canonical_article_id` di ciascun target, così che al giorno 40 si possa misurare
  quanta parte del P&L S4 nasce da fan-out contro quanta da articoli issuer-specific.
* Test/monitor consigliato: metrica giornaliera "notional aperto per `canonical_article_id`",
  con la distribuzione in dashboard.

### [DAY-003] Churn intraday: due roundtrip NVDA da 1h45 nella stessa seduta, nessuna banda fra gate d'ingresso e uscita

* Tipo: **Bug**
* Area: **Signal / Orders**
* Evidenza:
  * file/log/tabella: `execution_decisions` id 13717, 13883, 13960, 14149 · `trades` 782, 784
  * timestamp: BUY 14:37 → SELL 16:22 → BUY 17:07 → SELL 18:52
  * snippet/query: `reason` = *"[below_entry_gate] S4 signal fell below the active feedback entry threshold (age=1.1h vs max_age=4h, generated 2026-08-24 15:15 UTC, score=+0.192)"*
* Descrizione: l'ingresso richiede score ≥ 0,30; l'uscita scatta appena il peso target va a
  0, cioè appena lo score scende **sotto lo stesso 0,30**. Con banda nulla, un segnale a
  +0,192 — direzione invariata, solo meno convinto — liquida la posizione. Due ore dopo un
  +0,378 la ricompra. Due roundtrip completi in 4h15.
* Impatto: costo di esecuzione puro del roundtrip aggiuntivo **0,38 $** (`trades.cost_usd`
  di 782 e 784, 0,38 $ ciascuno). Nella giornata il churn ha per caso *evitato* perdite
  (tenendo dalle 14:37 al close si sarebbe perso ≈16,6 $), ma il meccanismo è indifferente
  al segno: è un costo strutturale, non un'assicurazione.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: **nessuna** durante il freeze — l'introduzione di una banda d'isteresi
  è taratura, esplicitamente congelata fino al 2026-09-28. Continuare ad accumulare
  occorrenze e costo.
* Test/monitor consigliato: contatore giornaliero di roundtrip completi per simbolo e somma
  dei `cost_usd` attribuibili al secondo e successivi roundtrip.

### [DAY-004] S4 valuta solo il segnale più recente: un +0,378 viene rovesciato da un −0,015 su un fan-out generico

* Tipo: **Bug**
* Area: **Signal**
* Evidenza:
  * file/log/tabella: `execution_decisions` id 14149 e 14233 · `sentiment_signals` 8796, 8797, 8839
  * timestamp: 18:52 (NVDA), 19:37 (SPCX)
  * snippet/query: NVDA — segnale delle 18:00 con `score=-0.015` sostituisce il +0,378 delle
    17:00 e chiude la posizione. SPCX — segnale 8839 (+0,005, da *"How AI's $220 Billion Bond
    Boom Competes With the Treasury"*, fan-out a 5 ticker) sostituisce l'8797 (+0,320) e chiude.
* Descrizione: la strategia legge un solo segnale per simbolo, il più recente entro
  `max_signal_age`. Un articolo issuer-specific e ad alta convinzione viene quindi scavalcato
  da un pezzo macro generico che passa per lì qualche ora dopo, senza alcuna ponderazione per
  rilevanza (`ISSUER_SPECIFIC` vs `UNKNOWN`) né per convinzione.
* Impatto: la chiusura NVDA delle 18:52 vale **−4,69 $** realizzati. Sulla giornata il segno
  è irrilevante; strutturalmente, l'informazione migliore del giorno viene scartata da quella
  peggiore per il solo fatto di essere più recente.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: nessun cambio di comportamento durante il freeze. Registrare, accanto
  al segnale scelto, quelli scartati e la loro `relevance`, in modo che al giorno 40 il
  costo dell'ordinamento per sola recenza sia quantificabile.
* Test/monitor consigliato: contatore "chiusure causate da un segnale `UNKNOWN`/fan-out che
  ha sostituito un `ISSUER_SPECIFIC` più forte".

### [DAY-005] `risk_reports.daily_pnl` = −527,82 $ contro −265,74 $ di NAV e −53,91 $ di realizzato

* Tipo: **Bug**
* Area: **PnL / Risk**
* Evidenza:
  * file/log/tabella: `risk_reports` id 73 · `portfolio_daily_state` · `portfolio_monitor_snapshots` 20:00 · `src/portfolio/risk_monitor.py:174`
  * timestamp: 2026-08-24 22:30:01 UTC
  * snippet/query:
    ```sql
    SELECT snapshot_date, daily_return, net_pnl, n_trades FROM portfolio_daily_state
    WHERE snapshot_date = '2026-08-24';
    -- -0.004804430706709276 | -53.90917171938692 | 6
    ```
    `daily_pnl = float(rets[-1] * nav * weight)` → −0,004804 × 109.860,71 × 1,0 = **−527,82**
* Descrizione: `portfolio_daily_state.daily_return` è il **rendimento medio dei trade chiusi**
  nella giornata (6 trade, −0,48% medio), non il rendimento del NAV. Moltiplicarlo per l'intero
  NAV produce un numero che non è né il realizzato (−53,91 $) né la variazione di equity
  (−265,74 $). La stessa serie alimenta lo Sharpe (−4,72) e il drawdown (17,9%) che fa scattare
  ogni giorno l'ALERT *"Strategy portfolio drawdown 17.9% exceeds 10%"* — mentre il drawdown
  di equity misurato dal monitor di portafoglio nello stesso giorno è **0,76%**. In più,
  `combined_drawdown` resta inchiodato a 0,012429 il 22, il 23 e il 24 agosto.
* Impatto: il canale d'allarme di rischio è tarato su una grandezza sbagliata di un ordine di
  grandezza; l'ALERT quotidiano è rumore permanente e desensibilizza rispetto a un drawdown vero.
  Non c'è costo diretto in dollari.
* Severità: **High**
* Confidenza: **High**
* Azione consigliata: già tracciato come **issue #349**. Rientra nei difetti di correttezza
  esenti dal freeze: finché il drawdown pubblicato è quello di una serie sintetica, l'evidenza
  di rischio raccolta in questa finestra è inutilizzabile.
* Test/monitor consigliato: assert di riconciliazione — `|risk_reports.daily_pnl −
  portfolio_monitor_snapshots.nav_change_today|` sotto una tolleranza; fallimento = alert Ops.

### [DAY-006] `decay_monitor`: metriche identiche per S1, S2 e S4, e S2 è dismessa

* Tipo: **Bug**
* Area: **Ops / Risk**
* Evidenza:
  * file/log/tabella: `decay_reports`, 12 righe del 2026-08-24 21:00
  * timestamp: 2026-08-24 21:00:00 UTC
  * snippet/query: `sharpe` = −7,3429 · `hit_rate` = 0,2876 · `ic` = 0,0172 · `max_drawdown`
    = 0,1210 — **gli stessi quattro valori per tutte e tre le strategie**, confrontati contro
    baseline diverse (S1 0,95 / S2 1,10 / S4 0,80)
* Descrizione: il monitor calcola metriche a livello di pipeline globale e le confronta con
  baseline per-strategia. L'esito è meccanico: tre CRITICAL su `sharpe` e due su `hit_rate`
  ogni giorno, indipendentemente da cosa abbiano fatto le singole strategie. S2 non compare
  in `strategies_run` di nessuno dei 24 cicli — non gira — ma continua a produrre allarmi.
* Impatto: cinque allarmi CRITICAL al giorno privi di contenuto informativo. Nessun costo
  diretto; il costo è la cecità operativa che ne deriva.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: remediation ticket di correttezza — separare le serie per strategia e
  togliere S2 dal set. Non è taratura: nessuna soglia cambia, cambia quale serie viene misurata.
* Test/monitor consigliato: test che fallisce se due `strategy_id` distinti producono lo stesso
  `actual_value` sulla stessa metrica nello stesso report.

### [DAY-007] `ingestion_stats_daily.duplicates` (3.178) supera i `fetched` (699) sulla stessa riga

* Tipo: **Bug**
* Area: **Data / News**
* Evidenza:
  * file/log/tabella: `ingestion_stats_daily`, riga `2026-08-24 / alpaca_benzinga`
  * timestamp: `updated_at` 2026-08-24 19:45:01 UTC
  * snippet/query: `fetched=699, queued=373, duplicates=3178, discarded_stale=209`
* Descrizione: i due contatori hanno denominatori diversi — `fetched` conta gli item nuovi,
  `duplicates` accumula gli scarti su tutte le finestre sovrapposte dei 24 poll da 15 minuti.
  Sulla stessa riga di tabella la lettura naturale (*"il 82% di ciò che leggo è duplicato"*)
  è impossibile da fare. Ricorrenza costante: il 21/08 3.356 dup su 673 fetched.
* Impatto: nessun costo. La metrica di efficienza dell'ingest non è calcolabile.
* Severità: **Low**
* Confidenza: **High**
* Azione consigliata: rinominare il campo o riportarlo allo stesso denominatore. Fuori dal
  perimetro del freeze (è strumentazione).
* Test/monitor consigliato: invariante `duplicates ≤ fetched_raw` con `fetched_raw` esplicito.

### [DAY-008] 51 dei 96 simboli in watchlist senza una sola riga di news

* Tipo: **Osservazione**
* Area: **News**
* Evidenza:
  * file/log/tabella: dossier `docs/evidence/dossier/2026-08-24.json` → `mercato.watchlist_zero_news`
  * timestamp: giornata intera
  * snippet/query: `watchlist_zero_news = 51`; copertura effective-timely **21/96 (21,9%)**
* Descrizione: più della metà dell'universo investibile non produce alcun input al motore
  news-driven. Concentrazione: top-5 ticker = 44,8% degli articoli; il settore `tech` +
  `semis` da solo copre 15 dei 28 articoli effective-timely.
* Impatto: S4 può esprimersi solo su un quinto dell'universo; la domanda d'uscita
  *"la news ha alpha?"* verrà risposta su un campione strutturalmente ristretto. Non
  stimabile in dollari.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: nessuna azione nel freeze. È un dato d'ingresso per la sintesi del
  giorno 40: la copertura è un vincolo di capacità, non un difetto da correggere ora.
* Test/monitor consigliato: già in dossier; portare `watchlist_zero_news` sulla dashboard.

### [DAY-009] `llm_responses.eligible` è `false` su tutte le 248 righe, incluse quelle dei 33 segnali ensemble validi

* Tipo: **Bug**
* Area: **LLM / Data**
* Evidenza:
  * file/log/tabella: `llm_responses`, `sentiment_signals`
  * timestamp: giornata intera
  * snippet/query:
    ```sql
    WITH e AS (SELECT s.id, s.model_id, sum(r.eligible::int) n_elig
               FROM sentiment_signals s LEFT JOIN llm_responses r ON r.signal_id = s.id
               WHERE s.generated_at >= '2026-08-24' AND s.generated_at < '2026-08-25'
               GROUP BY 1,2)
    SELECT model_id, n_elig, count(*) FROM e GROUP BY 1,2;
    -- ensemble | 0 | 48   <-- 48 segnali "ensemble" con zero risposte eligible
    -- ensemble | 2 | 33
    -- single:* | 0 | 43
    ```
* Descrizione: il retry a `min_confidence=0` introdotto con #90 (`sentiment.py:384`) rende
  utilizzabili risposte che il primo passaggio aveva scartato, ma il flag `eligible` persistito
  resta quello del primo tentativo. Risultato: 48 segnali etichettati `ensemble` (cioè
  costruiti su entrambi i modelli) hanno **zero** righe `eligible=true`. Fra le righe
  `eligible=false` ce ne sono con confidence fino a **0,85**.
* Impatto: la ricostruzione a posteriori di quali modelli abbiano davvero contribuito a un
  segnale è impossibile dal DB. Nessun costo di trading.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: remediation di correttezza — riscrivere `eligible` dopo il retry. Tocca
  solo la persistenza, nessuna soglia: non è taratura.
* Test/monitor consigliato: invariante — un segnale `model_id LIKE 'ensemble:%'` deve avere
  esattamente 2 righe `eligible=true`.

### [DAY-010] `execution_decisions.signal_id` NULL su 586 righe su 595 (98,5%), incluse tutte e 6 le SELL

* Tipo: **Bug**
* Area: **Data / Orders**
* Evidenza:
  * file/log/tabella: `execution_decisions`
  * timestamp: giornata intera
  * snippet/query:
    ```sql
    SELECT count(*) tot, sum((signal_id IS NULL)::int) nullsig
    FROM execution_decisions WHERE tick_time >= '2026-08-24' AND tick_time < '2026-08-25';
    -- 595 | 586
    ```
* Descrizione: solo i 3 BUY portano il `signal_id`. Le 6 SELL, le 566 `SKIP_THRESHOLD` e le
  10 `SKIP_FALLBACK` no — anche quando il testo di `reason` cita esplicitamente lo score e
  l'ora del segnale che ha deciso l'uscita (es. *"generated 2026-08-24 18:00 UTC,
  score=-0.015"*). La catena segnale → decisione → uscita esiste in prosa e non in chiave
  esterna.
* Impatto: ogni analisi controfattuale sulle uscite deve fare parsing di testo libero. Nessun
  costo diretto, ma è l'ostacolo principale a misurare il costo di [DAY-003] e [DAY-004].
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: remediation di correttezza — valorizzare `signal_id` sul ramo di uscita.
  Passa il test di esenzione: senza, il costo dei difetti di churn non è misurabile e
  l'evidenza della finestra resta incompleta.
* Test/monitor consigliato: invariante — una decisione il cui `reason` contiene `score=` deve
  avere `signal_id NOT NULL`.

### [DAY-011] `trades.slippage_est` è una copia esatta di `cost_usd` su tutte le righe

* Tipo: **Bug**
* Area: **PnL / Broker**
* Evidenza:
  * file/log/tabella: `trades`, righe 751, 755, 756, 782, 783, 784
  * timestamp: giornata intera
  * snippet/query: `slippage_est` = 1,02 / 1,03 / 1,04 / 0,38 / 1,99 / 0,38 — identici ai
    rispettivi `cost_usd`
* Descrizione: il campo che dovrebbe misurare la qualità di esecuzione contiene il costo
  teorico del modello (`cost_model.yaml`), non la differenza fra prezzo atteso e prezzo
  ottenuto. Con ordini `notional` a mercato su un broker paper lo slippage vero è comunque
  fittizio, ma il campo dichiara di misurare una cosa e ne misura un'altra.
* Impatto: nessun costo. La voce "slippage" del P&L è priva di significato.
* Severità: **Low**
* Confidenza: **High**
* Azione consigliata: o si persiste il mid del quote al `submitted_at` e si calcola davvero,
  o si rinomina il campo. Strumentazione, non taratura.
* Test/monitor consigliato: test che fallisce se `slippage_est == cost_usd` su tutte le righe
  di una giornata.

### [DAY-012] `portfolio_cycles.orders_count` somma 113 contro 9 ordini realmente inviati, e `constraints_fired` è vuoto in tutti i 24 cicli

* Tipo: **Bug**
* Area: **Ops / Orders**
* Evidenza:
  * file/log/tabella: `portfolio_cycles`, 24 righe del 2026-08-24
  * timestamp: 14:07 – 19:52 UTC
  * snippet/query:
    ```sql
    SELECT sum(orders_count) FROM portfolio_cycles
    WHERE timestamp >= '2026-08-24' AND timestamp < '2026-08-25';  -- 113
    SELECT constraints_fired::text, count(*) FROM portfolio_cycles
    WHERE timestamp >= '2026-08-24' AND timestamp < '2026-08-25' GROUP BY 1;  -- [] | 24
    ```
* Descrizione: `orders_count` (e `final_orders`, di identica lunghezza) contiene i **pesi
  target** del ciclo, cioè le posizioni desiderate, non gli ordini emessi. Chi legge la
  telemetria vede 113 ordini in una giornata che ne ha prodotti 9. In parallelo
  `constraints_fired` resta vuoto anche nei cicli in cui l'anti-pyramiding ha bloccato 4
  allocazioni: i vincoli che scattano davvero non finiscono in quel campo.
* Impatto: nessun costo. La telemetria di ciclo non è utilizzabile per stimare l'attività di
  esecuzione né la pressione dei vincoli.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: separare `targets_count` da `orders_submitted_count`; popolare
  `constraints_fired` con i guard effettivamente scattati. Strumentazione.
* Test/monitor consigliato: riconciliazione giornaliera fra `sum(orders_submitted_count)` e
  il conteggio degli ordini broker.

### [DAY-013] Le finestre cron sono in ora UTC fissa e ignorano il DST: 30–37 minuti di sessione scoperti ogni giorno

* Tipo: **Bug**
* Area: **Ops**
* Evidenza:
  * file/log/tabella: `src/workers/celery_app.py:151` (`run-news-ingestion`, `hour="14-21"`),
    `:210` (`portfolio-cycle`, `minute="7,22,37,52", hour="14-21"`)
  * timestamp: apertura RTH 13:30 UTC · primo ingest 14:00:36 · primo ciclo 14:07:00
  * snippet/query: `crontab(minute="*/15", hour="14-21", day_of_week="1-5")`
* Descrizione: con l'ora legale americana attiva il mercato apre alle 13:30 UTC, ma ingest,
  sentiment e portfolio-cycle partono tutti alle 14:00/14:07. **I primi 30 minuti** — la
  finestra in cui le notizie della notte e del pre-market si scaricano sui prezzi — non
  vengono né lette né tradate. Pattern identico su tutte e 6 le sedute osservate dal 17/08
  (primo ciclo sempre 14:07:00, ultimo sempre 19:52:00).
* Impatto: non stimabile con i dati disponibili — servirebbe la distribuzione degli score
  che sarebbero stati prodotti in una finestra che non viene mai campionata. Il costo si
  manifesta come [DAY-024] (notizia già scontata all'arrivo).
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: derivare l'orario dal calendario Alpaca (`GetCalendarRequest`, già usato
  da `scripts/daily_alpha_miss_analysis.sh`) invece che da un `hour` fisso. Ricade fra i
  difetti di correttezza: la finestra osservata esclude sistematicamente il tratto di
  sessione più informativo, quindi l'evidenza raccolta è distorta per costruzione.
* Test/monitor consigliato: test che confronta il primo `tick_time` del giorno con l'apertura
  di calendario e fallisce se il ritardo supera un ciclo.

### [DAY-014] I log dei container non sopravvivono al redeploy: l'intera giornata analizzata è già persa

* Tipo: **Rischio**
* Area: **Ops**
* Evidenza:
  * file/log/tabella: `docker compose logs worker --timestamps | head`
  * timestamp: la prima riga di log disponibile è **2026-08-25T11:26:34Z**
  * snippet/query: `docker compose logs worker --since 48h | grep -cE "ERROR|WARNING"` → **0**
    (non "zero errori": zero righe in assoluto per il 24/08)
* Descrizione: `worker`, `worker-inference`, `api` e `beat` sono stati ricreati il 2026-08-25
  alle 11:26. Tutti i log del 2026-08-24 sono spariti. Di conseguenza, per questa giornata
  **non sono verificabili**: latenza per chiamata LLM, retry, eccezioni gestite silenziosamente,
  esito delle consegne Telegram, riavvii dei worker durante la seduta.
* Impatto: non stimabile in dollari. Riduce ogni report forense a ciò che è persistito su DB.
  Ricorrenza alta (10ª occorrenza).
* Severità: **High**
* Confidenza: **High**
* Azione consigliata: driver di logging persistente o spedizione a un sink esterno. È
  strumentazione, esente dal freeze; senza, metà delle domande di questo protocollo resta
  strutturalmente senza risposta.
* Test/monitor consigliato: check giornaliero che il più vecchio log disponibile preceda
  l'apertura della seduta analizzata.

### [DAY-015] 11 posizioni aperte su 46 senza attribuzione di strategia

* Tipo: **Osservazione**
* Area: **PnL / Data**
* Evidenza:
  * file/log/tabella: `scripts/reconcile_open_trades_vs_broker.py`, colonna `strat` vuota
  * timestamp: stato a chiusura 2026-08-24
  * snippet/query: BAC, GOOGL, GS, MS, PBR, RIO, ROKU, SPY, UBS, UNH, XLE — tutte aperte da
    45 giorni, precedenti alla patch di attribuzione
* Descrizione: legacy noto. Il P&L economico le raccoglie sotto `CONTAMINAZIONE` (12
  posizioni, +95,24 $, capital base 8.348,07 $) invece di attribuirle arbitrariamente a S1.
  Il trattamento è corretto; il residuo è che l'8,0% del capitale della finestra non è
  attribuibile.
* Impatto: nessun costo. Riduce la potenza statistica del confronto S1 vs S4 al giorno 40.
* Severità: **Low**
* Confidenza: **High**
* Azione consigliata: nessuna — riattribuire a posteriori sarebbe una riscrittura retroattiva,
  vietata dalla carta d'osservazione. Dichiarare il residuo nella sintesi finale.
* Test/monitor consigliato: già coperto dal campo `esclusi`/`numerosita` di `economic_pnl.json`.

### [DAY-016] Gli stop protettivi coprono solo la parte intera della posizione e arrivano 15 minuti dopo l'ingresso

* Tipo: **Bug**
* Area: **Risk / Orders**
* Evidenza:
  * file/log/tabella: ordini broker `ambc-pstop-NVDA-20260824T1452`, `…T1722`,
    `ambc-pstop-SPCX-20260824T1722`
  * timestamp: BUY NVDA 14:37:10 → stop 14:52:09 · BUY SPCX/NVDA 17:07:05 → stop 17:22:06
  * snippet/query: stop NVDA `qty=8` su posizione 8,9311 (**89,6%**) e su 8,9680 (**89,2%**);
    stop SPCX `qty=13` su 13,8144 (**94,1%**)
* Descrizione: gli ordini di ingresso sono `notional`, quindi producono quantità frazionarie;
  gli stop sono `qty` intere, perché lo stop su frazioni non è ammesso. La frazione resta
  scoperta. In più lo stop viene posato nel **ciclo successivo**, lasciando 15 minuti di
  esposizione totalmente non protetta subito dopo l'ingresso — la finestra in cui il prezzo
  è più vicino all'entry e uno shock è più probabile.
* Impatto: non stimabile — nessuno stop è scattato il 24/08 (`stop_decisions` vuota). Il costo
  si materializza solo su un gap avverso.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: nessuna nel freeze (dimensionare gli ingressi a quantità intere è
  taratura, già rinviata al 28/09). Registrare la quota scoperta per posizione così che sia
  quantificabile.
* Test/monitor consigliato: metrica giornaliera `min(copertura_stop)` e `max(ritardo_stop)`,
  con alert se il ritardo supera un ciclo.

### [DAY-017] L'anti-pyramiding ha bloccato i 5 segnali più forti della giornata, incluso il massimo assoluto

* Tipo: **Anomalia**
* Area: **Signal / Orders**
* Evidenza:
  * file/log/tabella: `execution_decisions`, 10 righe `SKIP_PYRAMIDING`
  * timestamp: 14:07 – 18:07 UTC
  * snippet/query: MU **+0,539** e +0,430 (a libro dal 28/07), MRVL +0,442 (dal 14/07),
    SOXX +0,360 (dal 28/07), SNOW +0,327 (dal 05/08), LLY +0,322 (dal 15/07) —
    *"P0-05 anti-pyramiding: gia' a libro dal …, peso non allocato 2,x%"*
* Descrizione: il guard P0-05 impedisce di aumentare una posizione già aperta. Il segnale
  più forte dell'intera giornata (MU +0,539, entrambi i modelli rialzisti, confidence 0,78)
  non ha prodotto nulla perché MU era a libro da 27 giorni — verosimilmente per conto di S1,
  con una tesi d'investimento del tutto diversa.
* Impatto: **congetturale**. Con size tipica S4 (~2.200 $) e movimento dal momento del
  segnale al close: MU +1,78% (894,16 → 910,08) ≈ +39,2 $, SOXX +1,24% ≈ +27,3 $,
  MRVL +0,21% ≈ +4,5 $, LLY +0,14% ≈ +3,1 $; SNOW non calcolato. Totale **≈ 74,10 $** di
  movimento non catturato. Da notare che il segno close-to-close di questi titoli è
  *negativo* (MU −5,83%): il vantaggio è interamente intraday, e questo è a sua volta
  informativo sul tipo di alpha che S4 potrebbe catturare.
* Severità: **Medium**
* Confidenza: **Medium** (la size è ipotetica, il movimento è misurato su barre SIP reali)
* Azione consigliata: nessuna nel freeze. La domanda "S4 deve poter aggiungere su un simbolo
  detenuto da S1?" è una decisione di prodotto, già collegata a #182/#338.
* Test/monitor consigliato: registrare per ogni `SKIP_PYRAMIDING` il movimento segnale→close,
  così che il costo cumulato del guard sia leggibile al giorno 40.

### [DAY-018] Cinque segnali ribassisti sopra gate, tutti col segno corretto, tutti non azionabili

* Tipo: **Osservazione**
* Area: **Signal**
* Evidenza:
  * file/log/tabella: `sentiment_signals` 8771 (BABA −0,402), 8776 e 8844 (F −0,310),
    8833 (INTC −0,318), 8845 (GM −0,346)
  * timestamp: 15:30 – 19:30 UTC
  * snippet/query: ritorni close-to-close BABA −0,73%, F −3,33%, INTC −3,12%, GM −1,08%
* Descrizione: S4 è long-only, quindi nessuno di questi segnali può diventare un ordine.
  Sul close-to-close hanno tutti il segno giusto. Sul tratto che conta — dal momento del
  segnale al close — il vantaggio evapora: BABA −0,18%, F +0,68% e +0,10%, INTC −0,56%,
  GM −0,06%. Uno short su ciascuno con size 2.200 $ avrebbe reso **≈ +0,30 $** netti.
* Impatto: **0,30 $** congetturali. Nota importante per la sintesi: il valore apparente dei
  segnali ribassisti in questa giornata è interamente un artefatto del guardare il ritorno
  di seduta invece che il ritorno da segnale.
* Severità: **Low**
* Confidenza: **Medium**
* Azione consigliata: nessuna. Estendere S4 al lato short è una decisione di prodotto fuori
  perimetro. Il dato serve alla domanda d'uscita.
* Test/monitor consigliato: già coperto dal dossier; aggiungere il ritorno segnale→close
  accanto al ritorno di seduta per i segnali sopra gate.

### [DAY-019] Il 35% dei segnali è etichettato "FinBERT fallback" senza che FinBERT sia mai stato chiamato, e l'esclusione viene usata anche per liquidare posizioni

* Tipo: **Bug**
* Area: **LLM / Orders**
* Evidenza:
  * file/log/tabella: `sentiment_signals` (43 righe `single:*` con `fallback_used=true`,
    0 righe `model_id='finbert'`) · `execution_decisions` id 13700 · `src/workers/sentiment.py:__label_from_model_count`
  * timestamp: SELL NFLX 2026-08-24 14:22:00 UTC
  * snippet/query: `reason` = *"[fallback_filtered] S4 signal excluded from the ranking as
    **FinBERT fallback**, #108 (no signal row found in the last 48h): weight 0.0%, position
    closed."* — mentre alle 14:07 lo stesso ciclo aveva loggato *"single-model fallback
    (single:glm-5.2:cloud, score **+0.320**, confidence 0.80)"*
* Descrizione: tre problemi sovrapposti. (1) **Etichetta falsa**: `fallback_used=true` viene
  scritto quando l'aggregatore scarta un modello sotto `min_confidence`, non quando si ricade
  su FinBERT; il 24/08 FinBERT non è stato invocato nemmeno una volta, eppure 43 segnali
  (34,7%) portano quel flag e i messaggi operativi parlano di FinBERT. (2) **Asimmetria**:
  #108 nasce per tenere fuori dal *ranking BUY* i segnali a bassa affidabilità — scelta
  difendibile — ma azzerando il peso target innesca anche il ramo *"vendi ciò che è uscito
  dal target"*, e una posizione aperta viene liquidata da un filtro pensato per gli ingressi.
  (3) **Contraddizione nell'audit trail**: la stessa decisione afferma di non aver trovato
  segnali in 48 h dopo averne appena citato uno con score e confidence.
* Impatto: DIS +0,413 (conf. 0,75) è stato escluso dal ranking alle 16:00 ed è **il titolo
  più in rialzo fra quelli con segnale sopra gate** (+2,63% di seduta; +0,62% dal segnale al
  close). Su un notional S4 tipico di 1.883 $ ≈ **11,70 $** non catturati. La SELL NFLX ha
  realizzato −3,09 $ (in quel caso l'uscita ha evitato ulteriori −4,82 $ di drift, quindi il
  costo del giorno è nullo — ma per caso, non per progetto).
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: la parte (1) — l'etichetta — è una correzione di sola nomenclatura e
  osservabilità, esente dal freeze e da fare: il tasso di "fallback FinBERT" riportato in ogni
  report è oggi sbagliato di un fattore infinito (0 chiamate reali contro 35% dichiarato).
  Le parti (2) e (3) vanno registrate e decise col pacchetto uscite #182/#338, non ora.
* Test/monitor consigliato: separare due metriche distinte — `finbert_fallback_rate`
  (`model_id='finbert'`) e `single_model_rate` (`model_id LIKE 'single:%'`) — e riportarle
  entrambe. Test: se `finbert_fallback_rate = 0`, nessun messaggio operativo può contenere
  la stringa "FinBERT fallback".

### [DAY-020] Latenza di ingestione: mediana 53 minuti fra pubblicazione e disponibilità

* Tipo: **Osservazione**
* Area: **News**
* Evidenza:
  * file/log/tabella: `news_log`, 124 righe del 24/08
  * timestamp: giornata intera
  * snippet/query: mediana **53,0 min**, media 48,9, massimo 115,8; 232 item scartati come
    `stale` con età media 31,1 h (Benzinga) e 67,2 h (GDELT)
* Descrizione: dato in miglioramento rispetto alla mediana storica di ~1h50m registrata in
  precedenza su questo stesso finding, ma resta sostanziale: con `max_signal_age = 4h`, quasi
  un quarto della vita utile del segnale è già consumato quando il segnale nasce.
* Impatto: non stimabile isolatamente; è la causa meccanica di [DAY-024].
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: nessuna nel freeze. Registrare il trend: il miglioramento va confermato
  su più sedute prima di trattarlo come strutturale.
* Test/monitor consigliato: percentile 50/90 della latenza publish→fetch in dashboard giornaliera.

### [DAY-021] Righe di test scritte nel database di produzione

* Tipo: **Bug**
* Area: **Ops / Data**
* Evidenza:
  * file/log/tabella: `ingestion_stats_daily`
  * timestamp: righe `2026-08-25 / reuters` (36 fetched, `updated_at` 12:38:53) e
    `2026-08-22 / reuters` (8 fetched, sabato)
  * snippet/query:
    ```sql
    SELECT day, source, fetched FROM ingestion_stats_daily WHERE day >= '2026-08-21' ORDER BY day DESC;
    ```
* Descrizione: `reuters` non è un provider attivo del sistema e le due righe cadono su un
  sabato e su un orario di sviluppo. Sono scritture della suite di test contro il DB live.
  Non toccano il 24/08 — sono state notate mentre si ricostruiva la serie di ingest — ma
  inquinano la stessa tabella su cui si legge la storia dell'ingest.
* Impatto: nessun costo di trading. Le serie storiche di ingest contengono righe non
  prodotte dal sistema in esercizio.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: isolare il DB di test. Passa il test di esenzione — righe di test dentro
  la serie osservata rendono sbagliata l'evidenza raccolta.
* Test/monitor consigliato: vincolo che rifiuti `source` fuori dall'insieme dei provider
  configurati; alert su scritture di ingest nei giorni di borsa chiusa.

### [DAY-022] Il fan-out attribuisce a GS un articolo su un collocamento indiano in cui la banca è solo bookrunner

* Tipo: **Bug**
* Area: **News**
* Evidenza:
  * file/log/tabella: `news_log` id 8781, `extraction_method='org_lookup'`, fonte `gdelt_gkg`
  * timestamp: 2026-08-24, fetch fra 15:00 e 16:00 UTC
  * snippet/query: titolo *"SoftBank sells Rs 2,888 crore worth shares in Lenskart; Societe
    Generale, **Goldman Sachs**, Motilal Oswal…"* → ticker **GS**
* Descrizione: `org_lookup` continua ad attribuire ai ticker bancari articoli in cui la banca
  compare nel boilerplate come intermediario o casa di analisi, non come soggetto. Ricorrenza
  costante del pattern MS/GS/DB.
* Impatto: il 24/08 il segnale GS risultante non ha superato il gate, quindi nessun ordine.
  Costo del giorno: nullo. Il difetto resta a monte di ogni futura decisione su GS.
* Severità: **Low**
* Confidenza: **High**
* Azione consigliata: nessuna nel freeze — è lo stesso perimetro di [DAY-001] (ticker
  resolution) e va affrontato insieme, con il resolver come gate misurato sul golden set.
* Test/monitor consigliato: caso di regressione nel golden set QX-01 con un articolo in cui
  la banca compare solo come bookrunner.

### [DAY-023] Un segnale di 69 ore è stato valutato contro un `max_signal_age` di 4 ore

* Tipo: **Corretto**
* Area: **Signal**
* Evidenza:
  * file/log/tabella: `sentiment_signals` id 8639 (generato 2026-08-21 16:45) ·
    `execution_decisions` id 13700
  * timestamp: valutato 2026-08-24 14:07:11 UTC (età 69,4 h)
  * snippet/query: *"single-model fallback (single:glm-5.2:cloud, score +0.320, confidence 0.80)"*
* Descrizione: a prima vista è una violazione di `max_signal_age`. Non lo è: è FIX-D che
  preserva deliberatamente il segnale di una posizione **aperta**, perché la scadenza di un
  segnale non è un contro-segnale (deroga #236 del 2026-08-14). Il comportamento è quello
  previsto e va registrato come conferma che la deroga è attiva e funzionante in live.
* Impatto: nessuno.
* Severità: **Low**
* Confidenza: **High**
* Azione consigliata: nessuna. Registrato per evitare che un report futuro lo classifichi
  come anomalia.
* Test/monitor consigliato: nessuno aggiuntivo.

### [DAY-024] La notizia arriva quando il 75–79% del movimento è già avvenuto

* Tipo: **Osservazione**
* Area: **Signal**
* Evidenza:
  * file/log/tabella: `docs/evidence/dossier/2026-08-24.json` → `ingressi[].quota_movimento_precedente_al_segnale`
  * timestamp: ingressi NVDA 14:37 e 17:07
  * snippet/query: NVDA 14:37 → **0,750**; NVDA 17:07 → **0,786**; entry percentile 0,359 e
    0,329 (cioè si entra nel terzo inferiore del range di giornata)
* Descrizione: su entrambi gli ingressi NVDA, tre quarti del movimento della giornata erano
  già stati fatti quando il segnale è nato. È la conseguenza combinata di [DAY-013] (30 minuti
  di sessione non campionati) e [DAY-020] (53 minuti di latenza mediana). Su SPCX il dossier
  segnala `denominatore_degenere=true`, quindi la quota 3,05 non è interpretabile.
* Impatto: non stimabile come singola occorrenza — è la misura strutturale di quanto edge
  resti disponibile al momento in cui S4 può agire. È probabilmente il dato più importante
  per la domanda d'uscita n.1.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: nessuna. Portare la mediana di `quota_movimento_precedente_al_segnale`
  fra le metriche principali della sintesi del giorno 40.
* Test/monitor consigliato: già in dossier.

---

## 11. False positive e aree risultate corrette

| Area | Verifica | Esito |
|---|---|---|
| **Ordini non tracciati sul broker** | 12 ordini Alpaca = 9 filled con decisione + 3 stop protettivi cancellati | **Corretto.** Il pattern di F-042 (BUY sul broker senza segnale né decisione) **non si ripresenta** |
| **Riconciliazione posizioni** | 46 trade aperti / 46 simboli detenuti, 0 orfani, 0 posizioni non tracciate | **Corretto** (`reconcile_open_trades_vs_broker.py`, exit 0) |
| **Disponibilità Ollama** | 248/248 chiamate riuscite, 0 timeout, 0 output invalidi, 0 chiamate FinBERT | **Corretto.** Nessun downtime |
| **Rilevazione di regime** | `regime:current` scritto alle 13:30:51 con `data_quality: complete`, 2 modelli concordi | **Corretto.** Il pattern "regime fallisce ma il task risulta succeeded" (F-017) **non si ripresenta** |
| **Benchmark SPY** | `benchmark:spy_closes:*` popolato fino al 2026-08-24 (763,47) | **Corretto.** Il fallimento permanente del fetch (F-016) **non si ripresenta** |
| **Uscite `sentiment_reversal`** | 0 il 24/08: tutte e 6 le uscite sono `portfolio_sell` su posizioni **proprie di S4** | **Corretto.** Il meccanismo oggetto della deroga #182(a) non ha toccato posizioni altrui |
| **Idempotenza** | `client_order_id` deterministici; 9 `SIGNAL_DUPLICATE_SKIP` (8 SPCX + 1 NVDA) | **Corretto.** Nessun ordine duplicato possibile su retry |
| **Guard anti-pyramiding** | 10 blocchi su 7 simboli | **Funzionante** (l'effetto è [DAY-017], non un malfunzionamento) |
| **Roundtrip < 30 min** | Roundtrip minimo osservato: **1h45** | **Nessuno.** Pattern assente |
| **BUY ripetuto > 3 volte senza SELL** | Massimo 2 BUY su NVDA, con SELL intermedia | **Nessuno** |
| **SELL con sentiment positivo (bug A5)** | SPCX venduto con ultimo segnale +0,005: positivo ma **sotto gate**, ramo `below_entry_gate` | **Non è il bug A5.** Comportamento previsto |
| **`fallback_used=True` su tutti i simboli** | 43/124 (34,7%), e comunque non FinBERT | **Nessun blackout Ollama** |
| **NO-ORDER (decisione senza ordine)** | 0 su 9 decisioni non-SKIP | **Nessuno** |
| **Score < 0,05 che generano ordini** | Score minimo fra i 3 BUY: **+0,320** | **Nessuno** |
| **Ordini identici nello stesso minuto** | I 2 BUY delle 17:07 sono su ticker diversi e con `client_order_id` diversi | **Nessuna race condition.** È [DAY-002], che è un problema di fonte, non di scheduler |
| **Ordini fuori orario** | Primo 14:22, ultimo 19:37, RTH 13:30–20:00 | **Nessuno** |
| **Timestamp futuri / `published_at > fetched_at`** | 0 / 0 | **Nessuno** |
| **Duplicati cross-provider** | 0 titoli condivisi fra Benzinga e GDELT | **Nessuno** |
| **Circuit breaker / limiti di rischio** | Esposizione max 35,0% (limite 50%), drawdown max 0,76% (limite 5%), `trading_blocked=False` | **Corretto**, nessun breaker doveva scattare |
| **Coerenza paper/live** | `broker_environment='paper'` su tutti gli 82 snapshot; `TradingClient(paper=True)` | **Corretto e inequivocabile** |
| **F-043 (tutti i segnali sopra gate rialzisti)** | 9 rialzisti **e 5 ribassisti** | **Non si ripresenta** |
| **Ratchet sulla soglia d'ingresso** | Redis `feedback:entry_threshold:S4` = **0.3** (baseline) | **Corretto**, il ratchet non ha rialzato il gate |
| **Coppia di modelli attiva** | Redis `config:sentiment_llm_models` = `glm52,gptoss` | **Corretto**, coincide con la coppia attesa |

---

## 12. Dati mancanti o non accessibili

| Cosa manca | Perché | Cosa servirebbe |
|---|---|---|
| **Latenza per chiamata LLM** | `llm_responses` non ha colonna di latenza e i log sono azzerati ([DAY-014]) | Colonna `latency_ms` in `llm_responses`, oppure log persistenti |
| **Log worker/beat/api del 24/08** | Container ricreati il 2026-08-25 11:26 | Driver di logging persistente ([DAY-014]) |
| **API REST locale** | Tutti e 5 gli endpoint richiesti dal protocollo (`/decisions`, `/trades`, `/signals`, `/positions`, `/orders`) rispondono **HTTP 403 `{"detail":"Invalid or expired JWT token"}`** con il bearer del protocollo | Il token forense non è accettato dall'API. Ricorrenza nota. Tutta l'analisi è stata rifatta via SQL diretto e via client Alpaca in sola lettura: **nessuna conclusione dipende dall'API** |
| **Slippage reale** | `trades.slippage_est` è una copia di `cost_usd` ([DAY-011]) e il NBBO non è persistito | Persistere il mid del quote al `submitted_at` |
| **Consegna degli alert** | `mobile_events` è **vuota in assoluto** (0 righe storiche) e `monitor_devices` ha 0 dispositivi: il canale mobile non è in uso. Il canale Telegram non è verificabile perché i log sono spariti | Non è un'anomalia della giornata: è un canale non attivato. Resta però che l'ALERT di rischio e i 5 CRITICAL di decay del 24/08 **non hanno una prova di consegna** |
| **`s4_intent_events` / `s4_lifecycle_events`** | Entrambe **vuote in assoluto** (0 righe): le tabelle di #350 esistono ma il cablaggio al path live non è ancora attivo | Atteso e coerente con lo stato dichiarato di #282/#350 (wiring cron post-freeze) |
| **`performance_metrics` del 24/08** | 0 righe | Da verificare se il popolamento sia previsto o dismesso |
| **Movimento segnale→close per SNOW** | Non incluso nel fetch di barre | Query `StockBarsRequest(SNOW, 5Min, 2026-08-24)` |
| **Ritorni della finestra 13:30–14:00** | Il sistema non campiona quella finestra ([DAY-013]) | Nessun dato ricostruibile: è assenza per costruzione |

---

## 13. Raccomandazioni immediate

1. **Collegare il verdetto del resolver alla catena di scoring, almeno in ombra** ([DAY-001]).
   Non enforcement — quello resta gated su QX-01 — ma la colonna deve esistere e il
   `news_log_id` deve essere popolato, altrimenti al giorno 40 non sapremo dire quanto è
   costato ignorarlo. Oggi il resolver produce 251 verdetti al giorno che nessuno legge e che
   non sono nemmeno joinabili all'articolo.
2. **Ricalibrare o dichiarare inutilizzabile la confidence del resolver** ([DAY-001]).
   251 verdetti, 251 `NO_TRADE`: un gate che rifiuta tutto non è un gate. Va misurato sul
   golden set prima di poter servire a qualcosa.
3. **Correggere `risk_reports.daily_pnl`, Sharpe e drawdown** ([DAY-005], issue #349 già
   aperta). Finché l'ALERT quotidiano dice 17,9% e il drawdown vero è 0,76%, il canale di
   rischio è rumore permanente.
4. **Separare `finbert_fallback_rate` da `single_model_rate`** ([DAY-019]). Il tasso di
   fallback riportato oggi in ogni report è 34,7% quando le chiamate FinBERT reali sono state
   **zero**. Questo numero finisce nella sintesi del giorno 40.
5. **Rendere persistenti i log dei container** ([DAY-014]). Alla decima occorrenza, il fatto
   che ogni forense giri su una giornata di cui i log sono già spariti va trattato come un
   difetto dello strumento di osservazione, non come sfortuna.
6. **Isolare il database di test** ([DAY-021]). Righe `reuters` dentro `ingestion_stats_daily`
   inquinano la serie storica su cui si legge l'ingest.
7. **Non toccare nulla di tarabile.** Banda d'isteresi ([DAY-003]), size intera per gli stop
   ([DAY-016]), politica di pyramiding ([DAY-017]), soglie: tutto congelato fino al 2026-09-28.

## 14. Test e monitor da aggiungere

| # | Test / monitor | Copre |
|---|---|---|
| T1 | Contatore giornaliero `ordini_su_ticker_con_verdetto_NO_TRADE`; alert se > 0 | [DAY-001] |
| T2 | Invariante: `news_resolved_entities.news_log_id NOT NULL` | [DAY-001] |
| T3 | Test di regressione: articolo il cui unico soggetto è una società privata non deve produrre segnale tradabile sul ticker omonimo | [DAY-001], [DAY-022] |
| T4 | Metrica "notional aperto per `canonical_article_id`" con distribuzione | [DAY-002] |
| T5 | Contatore roundtrip completi/simbolo/giorno + `cost_usd` dal secondo roundtrip in poi | [DAY-003] |
| T6 | Contatore "chiusure causate da un segnale fan-out che ha sostituito un ISSUER_SPECIFIC più forte" | [DAY-004] |
| T7 | Assert di riconciliazione `risk_reports.daily_pnl` ↔ `nav_change_today` entro tolleranza | [DAY-005] |
| T8 | Test: due `strategy_id` distinti non possono avere lo stesso `actual_value` sulla stessa metrica | [DAY-006] |
| T9 | Invariante: segnale `ensemble:%` ⇒ esattamente 2 righe `eligible=true` | [DAY-009] |
| T10 | Invariante: decisione con `score=` nel `reason` ⇒ `signal_id NOT NULL` | [DAY-010] |
| T11 | Test: `slippage_est == cost_usd` su tutte le righe di un giorno ⇒ fail | [DAY-011] |
| T12 | Riconciliazione `sum(orders_submitted_count)` ↔ conteggio ordini broker | [DAY-012] |
| T13 | Test: primo `tick_time` del giorno vs apertura di calendario Alpaca, fail se ritardo > 1 ciclo | [DAY-013] |
| T14 | Check: il log più vecchio disponibile precede l'apertura della seduta analizzata | [DAY-014] |
| T15 | Metriche `min(copertura_stop)` e `max(ritardo_stop)`, alert se ritardo > 1 ciclo | [DAY-016] |
| T16 | Movimento segnale→close registrato su ogni `SKIP_PYRAMIDING` | [DAY-017] |
| T17 | Ritorno segnale→close accanto al ritorno di seduta per ogni segnale sopra gate | [DAY-018], [DAY-024] |
| T18 | Test: se `finbert_fallback_rate = 0`, nessun messaggio operativo contiene "FinBERT fallback" | [DAY-019] |
| T19 | Percentili 50/90 della latenza publish→fetch in dashboard | [DAY-020] |
| T20 | Vincolo su `ingestion_stats_daily.source` limitato ai provider configurati | [DAY-021] |

## 15. Ticket tecnici suggeriti

> Tutti valutati contro il test di esenzione della carta d'osservazione: *«se non lo correggo,
> l'evidenza che raccolgo nelle prossime settimane è sbagliata?»*. **Nessuna proposta di
> taratura.**

| ID | Titolo | Passa il test di esenzione? | Priorità |
|---|---|---|---|
| **TK-1** | Popolare `news_resolved_entities.news_log_id` ed esporre il verdetto del resolver come colonna d'ombra in `news_log` | **Sì.** Senza, il costo dei mismatch di entità non è attribuibile e ogni giornata futura con un fan-out mal risolto contamina il P&L S4 | **P0** |
| **TK-2** | `risk_reports`: calcolare `daily_pnl`, Sharpe e drawdown sulla serie di equity invece che sul rendimento medio per trade (**#349, già aperta**) | **Sì.** L'evidenza di rischio della finestra è oggi non riconciliabile | **P0** |
| **TK-3** | Riscrivere `llm_responses.eligible` dopo il retry `min_confidence=0` di #90 | **Sì.** Senza, non è ricostruibile quali modelli abbiano generato un segnale | **P1** |
| **TK-4** | Valorizzare `execution_decisions.signal_id` sul ramo di uscita | **Sì.** È il blocco principale alla misura del costo di churn | **P1** |
| **TK-5** | Log persistenti per `worker`, `worker-inference`, `api`, `beat` | **Sì.** Strumento di osservazione, non oggetto osservato | **P1** |
| **TK-6** | Separare `finbert_fallback_rate` da `single_model_rate` e correggere i messaggi operativi | **Sì.** Un numero riportato in ogni sintesi è oggi sbagliato | **P1** |
| **TK-7** | Isolare il DB di test dalla produzione | **Sì.** Righe di test dentro la serie osservata | **P1** |
| **TK-8** | Derivare le finestre cron dal calendario Alpaca invece che da `hour="14-21"` fisso | **Sì.** La finestra osservata esclude sistematicamente il tratto più informativo della sessione | **P1** |
| **TK-9** | `decay_monitor`: serie per strategia, rimozione di S2 | **Sì.** Cambia quale serie si misura, non le soglie | **P2** |
| **TK-10** | `portfolio_cycles`: separare `targets_count` da `orders_submitted_count`; popolare `constraints_fired` | No — è pura strumentazione | **P2** |
| **TK-11** | Sbloccare il bearer token forense sugli endpoint REST | No — esiste un percorso alternativo (SQL diretto) | **P2** |
| **TK-12** | `trades.slippage_est`: calcolarlo davvero dal mid al `submitted_at`, o rinominarlo | No | **P3** |
| — | Banda d'isteresi ingresso/uscita, size intera per gli stop, politica di pyramiding | **No: taratura.** Congelate fino al 2026-09-28 | **Bloccate** |

## 16. Stato sistema

| Componente | Stato |
|---|---|
| **Ollama** | **UP, 0 ore di downtime.** 248/248 chiamate riuscite su 124 articoli, 0 timeout, 0 output invalidi. Ultima chiamata 19:45:48. `fallback_counters.consecutive_fallback = 0`, resettato alle 19:45:48 |
| **FinBERT fallback rate** | **0,0% delle decisioni** — `model_id='finbert'` compare **zero volte** il 24/08 (storicamente 1 riga il 18/08 e 1 il 20/08). Attenzione: il flag `fallback_used=true` è presente su 43 segnali (34,7%), ma indica **single-model**, non FinBERT → [DAY-019] |
| **Modelli attivi** | `glm-5.2:cloud` (peso 0,70) + `gpt-oss:20b-cloud` (peso 0,30), applicati alle 04:00 via `auto_apply`. ICIR purificato: glm +0,1045, gpt-oss **−0,0288** |
| **Budget LLM** | 0,1394 $ spesi (71.711 token in / 8.874 out), `budget_exhausted = false` |
| **Worker restart** | **Nessuno rilevabile durante la seduta**, ma non verificabile: `worker`, `worker-inference`, `api` e `beat` risultano ricreati il **2026-08-25 alle 11:26** (redeploy, ~1 h prima di questa analisi) e i log del 24/08 sono perduti → [DAY-014]. `postgres`, `redis` e `frontend` sono up da 7 giorni, quindi nessun restart dell'infrastruttura dati durante la seduta |
| **Beat / scheduling** | 24 portfolio-cycle su 24 attesi (14:07→19:52, cadenza 15 min), 24 ingest, 24 cicli di sentiment. Nessun ciclo saltato. `decay-monitor` 21:00 ✓, `risk-monitor` 22:30 ✓, `weight-rebalance` 04:00 ✓ |
| **Broker** | Alpaca **paper**, account `ACTIVE`, `trading_blocked = False`. 82 snapshot di monitoraggio (cadenza 5 min), `degradations = []` su tutti |
| **Database** | `alembic-postgres-1` healthy, up da 7 giorni. `alembic-redis-1` healthy |
| **API REST** | Up e healthy, ma **403 su tutti gli endpoint** con il bearer del protocollo forense |

---

*Report generato in sola lettura. Nessun file di codice modificato, nessun ordine inviato,
nessun worker avviato, nessuna pipeline rieseguita.*
