# Forensic Daily Report — 2026-09-16

Analista: sessione forense autonoma (read-only). Generato 2026-09-17.
Fuso operativo: **UTC** (`src/workers/celery_app.py:55-56`, `timezone="UTC"`, `enable_utc=True`) — nessuna ambiguità.
RTH del 2026-09-16 (EDT): **13:30–20:00 UTC**.
Fonti: PostgreSQL `alembic-postgres-1`, log persistenti `logs/containers/*-2026-09-16.log`, API REST `localhost:8001`,
`docs/evidence/dossier/2026-09-16.json` (schema 3.1), `docs/evidence/economic_pnl.json`, `docs/evidence/market_daily.jsonl`.

> **Revisione 2 — 2026-09-17.** Passata di verifica indipendente su tutte le cifre del report. 28 affermazioni
> numeriche ricontrollate contro DB e log: 25 confermate al valore esatto. Tre correzioni, annotate qui e nel
> corpo del testo perche' modificano cifre gia' scritte:
> 1. **Chiamate Ollama.** La rev. 1 riportava "243 POST verso `ollama.com`, 6 fallimenti (2,5%)". I 242 POST
>    del log `worker-inference` sono verso **`api.openfigi.com`** (il resolver ticker), non verso Ollama: le
>    chiamate a Ollama non lasciano alcuna traccia HTTP. Valore corretto: ~430 invocazioni di modello
>    (215 per modello, dalle righe `llm_responses`), 6 timeout = **1,4%**. La conclusione — Ollama su tutto il
>    giorno, 0 minuti di outage — **non cambia**, ma poggiava sull'evidenza sbagliata. L'errore stesso e'
>    registrato come **[DAY-026]**.
> 2. **S4 economico cumulato.** −855,58 $ → **−979,55 $**: `economic_pnl.json` e' stato rigenerato il
>    2026-09-17T10:15 dopo la stesura della rev. 1. Nessun'altra cifra del report dipende da questo valore.
> 3. **Conteggio `DECAY CRITICAL`.** 12 → **11** (S1 ×4, S2 ×4, S4 ×3), e **62** righe MISCONF (31 per log)
>    invece di 31 complessive. Nessun verdetto cambia.
>
> Restano confermate al valore esatto, fra le altre: 215 righe scorate, 72 `single:`, 2 fallback FinBERT reali,
> 7 BUY / 5 SELL / −45,34 $ realizzati, 19 ordini broker, 23 cicli portfolio con 19:37 mancante,
> 21 `BROKER_POSITION_MISSING` tutte con `reconstructible=false`, 779/787 `signal_id`, 158/215 righe con
> entita' HTML, 133/215 righe da fan-out, 11 `mobile_events` con 0 consegne, 4 `400 Bad Request` su 5 invii
> Telegram, `slippage_est == cost_usd` al bit, stop arrotondati per difetto, 69/72 letture `single:` con
> entrambi i modelli che avevano risposto.

---

## 1. Executive summary

La catena end-to-end ha funzionato: 215 righe scorate, 7 BUY e 5 SELL, tutti dentro RTH, tutti con fill,
nessun ordine duplicato, nessun ordine senza segnale a monte, nessun trade su ticker fuori watchlist.
La giornata chiude a **−45,34 $ realizzati** (tutto S4) e **−22,47 $ di MTM** sulle tre posizioni aperte
e rimaste a libro; il book però sale (+12,29 $ di equity) contro SPY −0,44%.
Le tre catture del giorno (SPCX, INTC, MRVL) erano i mover giusti e hanno perso tutte:
`profitable_capture_rate` = 0/3. Il collo di bottiglia non è la selezione ma la latenza (F-030, già registrata).
Quattro id nuovi nel ledger (F-083…F-086), due dei quali di correttezza: (a) durante un blackout DNS il riconciliatore ha scritto 21 righe
`BROKER_POSITION_MISSING` nel ledger append-only S4 pur sapendo che il broker era irraggiungibile — un guasto di
trasporto persistito come fatto di business; (b) `/api/trades` non espone il ledger dei trade ma una riga per
ordine broker, con `net_pnl` sempre nullo: chi audita dal REST vede 12 "trade" a P&L zero contro 7 ingressi e
5 chiusure a −45,34 $ del DB. Il ciclo portfolio delle 19:37 è stato annullato dallo stesso blackout e il task
Celery risulta `succeeded` (F-074). Tutte e 4 le uscite intraday sono avvenute con sentiment **positivo**
(F-013) e una di esse su un segnale nato da un articolo su **Intel** taggato SPCX (F-008).
33,5% delle letture è degradato a modello singolo senza che alcun modello sia caduto (F-010).
Le chiamate a Ollama non sono tracciate da nessuna parte: l'uptime è inferito dai soli successi (F-086, nuovo).
Ollama in piedi tutto il giorno (6 timeout su ~430 invocazioni di modello, 0 minuti di outage); FinBERT vero usato 2 volte su 215.

## 2. Verdict finale

**OK con warning — anomalie significative sull'auditabilità, non sull'esecuzione.**

L'esecuzione (ordini, fill, riconciliazione posizioni, rispetto degli orari, assenza di duplicati) è corretta.
Ciò che non è affidabile è il **livello di evidenza**: il ledger S4 contiene 21 osservazioni false generate da un
guasto di rete, l'API espone una vista dei trade che contraddice il DB, e **tutti e 11** gli `mobile_events`
del giorno (5 dei quali CRITICAL) hanno avuto **zero consegne** — più 11 `DECAY CRITICAL` che non passano
nemmeno da `mobile_events` e 4 invii Telegram su 5 rifiutati con 400. Dentro un periodo di sola osservazione
questo è il difetto che conta: inquina proprio i dati su cui la decisione di fine finestra verrà presa.

---

## 3. Timeline del 2026-09-16 (UTC)

| Ora | Componente | Evento | Esito | Fonte |
|---|---|---|---|---|
| 05:28 | worker/inference | restart container (SIGTERM + ready) | ok | worker log |
| 07:14:07 | redis | `MISCONF ... unable to persist to disk` → CRITICAL `Unrecoverable error`, consumer disconnesso | **stack Celery giù 11 min** | worker+inference log, 31 righe |
| 07:25:43 | worker/inference | riconnessione a redis, `ready.` | recuperato | log |
| 08:24 / 08:45 / 10:20 | worker/inference | altri 3 restart (pre-market) | ok | log |
| 12:18–12:19 | inference | 3 × `ensemble model failed: gpt-oss:20b-cloud kind=error (Ollama timeout 90s)` | degradato a single | inference log |
| **13:30** | — | **apertura RTH (EDT)** | — | calendario |
| 13:32:05 | sentiment (stream-driven) | primo ciclo ensemble della seduta; prima riga `news_log` 13:32:20 | ok | `ensemble_cycle_health` id 518 |
| 13:37 / 13:52 | portfolio-cycle | **non schedulati** (beat `hour="14-21"`) | **2 cicli persi** | `celery_app.py:265` |
| 13:45:37 | sentiment | MRVL +0,325 (ensemble) da "What's Going On With Marvell…" | signal 11110 | `sentiment_signals` |
| **14:07:00** | portfolio-cycle | primo ciclo della seduta → **BUY MRVL** 6,3743 @ 230,99 | filled 14:07:10 | dec 27053 / trade 1005 |
| 14:07:09 | alert | `#161: 10/40 posizioni non proteggibili (qty<1)`, AMAT a −28,7% | **Telegram 400** | worker log |
| 14:12 | reconcile | `ENTRY_RECONCILIATION / BROKER_FILLED` ×3 | ok | `s4_lifecycle_events` |
| 14:22 | stop | ordine protettivo MRVL **qty 6** su 6,3743 posseduti | `new` | orders API |
| 14:37:00 | portfolio-cycle | **BUY META** 2,1686 @ 678,83 (score +0,266) | filled | dec 27257 / trade 1006 |
| 14:52:00 | portfolio-cycle | **BUY INTC** 14,5237 @ 101,357 (score +0,378) | filled | dec 27362 / trade 1007 |
| 15:07:00 | portfolio-cycle | **BUY ORCL** 10,2714 @ 143,29 (score +0,280) | filled | dec 27468 / trade 1008 |
| 15:39:21 | sentiment | AXP **+0,607** (conf 0,825) da headline GDELT senza corpo | signal 11172 | `sentiment_signals` |
| 15:48:23 | sentiment | SPCX +0,390 da "SpaceX Stock Surges: What's Going On?" | signal 11175 | — |
| 15:52:00 | portfolio-cycle | **BUY AXP** @ 317,43 e **BUY SPCX** @ 152,23 (percentile range 0,910) | filled | dec 27776/27777 |
| 15:52:52 | sentiment | INTC **+0,640** — segnale più forte del giorno, `ensemble_std` = 0,000 | bloccato da anti-pyramiding | signal id da `sentiment_signals` |
| 15:53:03 | sentiment | SPCX +0,055 da **"Intel Analyst Raises Price Target On Terafab"** (fan-out 4 ticker) | signal 11178 | `news_log` 11179 |
| 16:22:00 | portfolio-cycle | **SELL META** @ 676,18 — `[whipsaw]`, score vivo **+0,266** | −6,04 $ | dec 27989 |
| 16:48:40 | sentiment | SPCX **−0,420** (single:gpt-oss) — contro-segnale forte, scartato perché fallback | nessuna azione | signal 11214 |
| 16:52:00 | portfolio-cycle | **SELL ORCL** @ 143,638 — `[below_entry_gate]`, score vivo **+0,280** | +2,76 $ | dec 28215 |
| 16:57:00 | sentiment | QQQ +0,407 da market-summary macro (fan-out 8 ticker) | signal 11218 | `news_log` 11219 |
| 17:07:00 | portfolio-cycle | **BUY QQQ** 2,0745 @ 709,47 (percentile 0,797) | filled | dec 28326 / trade 1011 |
| 17:37:00 | portfolio-cycle | **SELL SPCX** @ 151,08 — `[below_entry_gate]` sul segnale **+0,055 dell'articolo Intel** | −12,67 $ | dec 28552 |
| 18:07:00 | portfolio-cycle | **SELL BA** @ 207,72 — `[unknown]` / FIX-D, tenuta 26,0 h | −18,61 $ | dec 28798 |
| 18:30:00 | loss-feedback | ratchet S4 **congelato** (EWMA R −0,80, 5 perdite consecutive, P&L −228,55 $) | **Telegram 400** | worker log |
| 18:39–18:57 | inference | altri 3 timeout Ollama | degradato | inference log |
| 18:52:01 | portfolio-cycle | **SELL AXP** @ 315,28 — `[below_entry_gate]`, score vivo **+0,078** | −10,78 $ | dec 29161 |
| 19:22:14 | alert | `#161` WDC −24,3%, NOK −15,1% non protetti | **Telegram 400** | worker log |
| **19:37:04** | portfolio-cycle | `NameResolutionError` su `data.alpaca.markets` → `No price data — aborting portfolio cycle` | **ciclo annullato, task `succeeded`** | worker log |
| **19:42:04** | reconcile | `#295: broker positions unavailable` → scrive comunque **21 × `BROKER_POSITION_MISSING`**, `reconstructible=false` | **ledger inquinato** | `s4_lifecycle_events` |
| 19:52:00 | portfolio-cycle | ultimo ciclo della seduta | ok | `portfolio_cycles` 1537 |
| **20:00** | — | **chiusura RTH** | — | — |
| 20:00 / 20:06 | worker | altri `NameResolutionError` su `/v2/clock`, 2 eventi `Degradazione market_clock` CRITICAL | registrati, non consegnati | `mobile_events` |
| 20:00–21:59 | sentiment/portfolio/execution | 8 cicli portfolio e ~28 invocazioni sentiment schedulate **dopo la chiusura**, tutte skip `market_closed` | sprecate | beat `hour="14-21"` |
| 21:00:00 | decay_monitor | **12 alert CRITICAL** (S1, S2, S4) con IC/hit-rate **identici** fra strategie | solo `log.critical` | worker log |
| 21:35:01 | reconcile-positions | 41 `fully_held`, 1 `partially_wound_down_coheld`, **0 anomalie** | ok | worker log |
| 22:00:14 | forward-return | 1020 aggiornati, 62 senza dati, 0 errori | ok | worker log |
| 22:30:01 | risk_monitor | NAV 108.962,74 $, esposizione 31,05%, HHI 0,0285, drawdown 1,37%, **0 alert** | ok | `risk_reports` |
| 22:45:10 | counterfactual | 831 decisioni aggiornate, 76 senza dati | ok | worker log |
| 22:50:00 | held_news_loss_alert | 4 simboli allertati (ASML, PFE, SBUX, WDC) → `mobile_events` | **0 consegne** | `mobile_notification_deliveries` |
| 22:55:00 | stale_drop_alert | `alerted: 2` → Telegram **200 OK** (unico invio riuscito del giorno) | consegnato | worker log |

---

## 4. Tabella news ingest

### Per fonte

| Fonte | fetched | queued | duplicates | scartate no_ticker | scartate stale | scartate not_tradable | righe in `news_log` | parse_fail |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| alpaca_benzinga | 1.563 | 792 | **6.521** | 0 | 389 | 207 | 203 | 0 |
| gdelt_gkg | 2.304 | 12 | 2 | 2.290 | 0 | 0 | 12 | 0 |
| **Totale** | 3.867 | 804 | 6.523 | 2.290 | 389 | 207 | **215** | 0 |

Fonte: `ingestion_stats_daily`, `news_queue_drops`, `news_log`. Nessun'altra fonte attiva (Tiingo/SEC/RSS/Marketaux non schedulate).

- **Copertura temporale**: pubblicazioni 11:43–19:49 UTC; fetch 13:32–19:49 UTC. Nessuna riga con timestamp futuro.
- **Latenza di fetch** (benzinga): media **3,15 h**; attesa in coda media 1,75 h.
- **Stale drop share**: **44,4%** (352/792) contro soglia 0,25 → `alert_required = true`. 129 delle stale erano state accodate fuori sessione.
- **Trasporto**: 200 righe via WebSocket, 3 via REST, 12 GDELT senza trasporto (F-069 resta: lo stream ingerisce 24/7 in una coda gated).
- **Sanitizzazione**: attiva (NFKC, zero-width, tag HTML rimossi) ma **158/215 righe (73,5%) arrivano al modello con entità HTML non decodificate** (`&#39;`, `&amp;`, `&rsquo;`).
- **Duplicati**: 0 duplicati di sindacazione per ticker nel dossier; `duplicate_id` 6.521 > `fetched` 1.563 (contatore incoerente, F-007).

### Per ticker (top 15 di 61 simboli scorati)

| Ticker | righe | max score | min score | note |
|---|---:|---:|---:|---|
| SPY | 21 | +0,120 | **−0,420** | non tradato da S4 |
| NVDA | 14 | — | — | nessun segnale sopra gate |
| SPCX | 10 | +0,390 | **−0,420** | 7/10 articoli su Tesla/xAI/Intel/macro |
| INTC | 9 | **+0,640** | +0,010 | comprato; 1 `FALSE_ENTITY_MATCH` |
| GOOGL | 9 | — | — | — |
| BA | 8 | +0,304 | −0,335 | venduto |
| TSLA | 8 | — | — | — |
| AMZN | 8 | — | — | — |
| META | 7 | +0,266 | — | comprato e venduto |
| MSFT | 6 | — | — | — |
| ORCL | 6 | +0,280 | — | comprato e venduto |
| QQQ | 6 | +0,407 | −0,346 | comprato |
| GS | 5 | +0,291 | −0,386 | non detenuto S4 |
| AAPL | 5 | +0,225 | — | — |
| HOOD | 3 | +0,141 | −0,325 | mover −5,46%, non azionabile |

**Rilevanza** (dossier, 123 articoli unici): ISSUER_SPECIFIC 82 · TAG_UNCONFIRMED **132** · FALSE_ENTITY_MATCH 1 · SECTOR_MACRO 0 · IRRELEVANT_FANOUT 0.
**Fan-out**: 41 URL su 123 portano più di un ticker; **133/215 righe (61,9%)** nascono da articoli multi-ticker.
**Copertura effective-timely**: 46/96 simboli (47,9%); 35 simboli a zero news (VZ e T, entrambi mover ≥3%, a zero righe).

### Top news per impatto sul segnale

| Ora | Titolo | Ticker | Score | Effetto |
|---|---|---|---:|---|
| 15:52 | "Intel Analyst Raises Price Target On Terafab, AI-Driven Turnaround" | INTC | +0,640 | bloccato da anti-pyramiding |
| 15:30 | "American Express Sees Strong Spending, Raises Revenue Outlook at Conference" (solo titolo, GDELT) | AXP | +0,607 | **BUY AXP**, poi −10,78 $ |
| 15:48 | "SpaceX Stock Surges: What's Going On?" | SPCX | +0,390 | **BUY SPCX**, poi −12,67 $ |
| 16:52 | "S&P 500 Gains, Crude Falls Ahead Of Fed's Expected First Hike…" (fan-out 8 ticker) | QQQ | +0,407 | **BUY QQQ**, MTM −9,85 $ |
| 15:53 | "Intel Analyst Raises Price Target On Terafab…" (stesso articolo, riga SPCX) | SPCX | +0,055 | **ha chiuso la posizione SPCX** |
| 15:28 | "Why Is Robinhood Markets Stock Falling Wednesday?" | HOOD | −0,325 | nessun ordine (long-only) |

### Problemi trovati nell'ingest

duplicati contabilizzati oltre il denominatore; 44,4% di scarto stale; 61,9% di righe da fan-out; 73,5% di entità HTML non decodificate; 2 mover (VZ, T) a copertura zero. **Confidenza dell'analisi: Alta** (contatori e righe entrambi interrogabili).

---

## 5. Tabella performance modelli LLM

| Modello | risposte | usate in ensemble | conf. media | polarity media | score medio | dev. std score | timeout/errori |
|---|---:|---:|---:|---:|---:|---:|---:|
| `glm-5.2:cloud` | 215 | 141 | 0,383 | +0,044 | +0,0189 | 0,161 | 0 |
| `gpt-oss:20b-cloud` | 212 | 141 | 0,467 | +0,023 | +0,0143 | 0,173 | **6** (`kind=error`, timeout 90 s) |
| `finbert` (fallback) | 2 | — | 0,185 | +0,077 | +0,0144 | — | 0 |

**Esiti dell'aggregazione** (215 righe scorate):

| Esito | n | % |
|---|---:|---:|
| `ensemble:glm-5.2+gpt-oss` | 141 | 65,6% |
| `single:gpt-oss:20b-cloud` | 60 | 27,9% |
| `single:glm-5.2:cloud` | 12 | 5,6% |
| `finbert` (divergenza vera) | 2 | 0,9% |
| **fallback_used = true** | **74** | **34,4%** |

- **Latenza per modello: non misurabile, e le chiamate a Ollama non lasciano alcuna traccia HTTP** (DAY-026). Il client Ollama non passa dal logger `httpx`: nei log del 09-16 l'unico host POST-ato dal worker inference e' `api.openfigi.com` (242 chiamate, il resolver ticker). L'attivita' dell'ensemble e' ricostruibile **solo** dalle righe persistite: 215 tentativi per `glm-5.2:cloud` e 215 per `gpt-oss:20b-cloud` (~430 invocazioni), di cui 212 gpt-oss persistite e 6 timeout loggati -> 3 recuperati dal retry, 3 segnali rimasti a una sola risposta. Query che servirebbe: una colonna `latency_ms` su `llm_responses`.
- **Distribuzione score**: 87/215 righe (40,5%) con |score| < 0,05; 10 righe ≥ +0,30; 8 righe ≤ −0,30.
- **Score estremi**: INTC +0,640, AXP +0,607, SPY/SPCX −0,420, QQQ +0,407.
- **Disaccordo forte**: le 2 uniche cadute su FinBERT sono disaccordi reali (glm −0,60 vs gpt +0,05; glm −0,70 vs gpt −0,10) — il guard funziona, ma `ensemble_std` viene persistito a 0,000.
- **Dominanza di un modello**: in **69 casi su 72** la lettura single nasce perché l'altro modello ha risposto con `confidence < 0,40` (soglia `min_confidence`), non perché sia caduto. Il modello scartato aveva confidenza media 0,26.
- **Fallback FinBERT reale**: 2 su 215 (0,93%). `finbert_fallback_events` conferma che FinBERT ha ricevuto **titolo + corpo** in entrambi i casi (`body_chars` 50 e 437) — conferma runtime residua di #453 **soddisfatta**.

### Verifica funzionale

| Domanda | Risposta | Evidenza |
|---|---|---|
| L'output LLM è validato prima di entrare nel signal store? | **Parzialmente**: schema Pydantic sì, enum/Unicode no (F-055) | `llm_responses.directness/event_type` liberi |
| L'ensemble gestisce varianza alta? | Sì per la divergenza vera (2 casi → FinBERT), **no** per la misura: `ensemble_std` = 0,000 su 27/141 ensemble, incluso il top score INTC +0,640 | `sentiment_signals.ensemble_std` |
| Le news duplicate pesano più volte? | **No**: 0 righe `sentiment_signals` con lo stesso `news_log_id`; `uq_news_log_url_ticker` regge | query di controllo |
| La stessa news può generare segnali multipli? | **Sì, per ticker diverso**: fan-out 61,9%. Un articolo su Intel ha prodotto 4 segnali (INTC, NVDA, SPCX, TSLA) | `news_log` 11177-11180 |
| Confidence bassa riduce il peso? | Sì per lo score (`polarity × confidence`), **ma sotto 0,40 il modello viene espulso** e il segnale è squalificato dal BUY | `src/llm/ensemble.py` |
| I modelli sono chiamati offline/background? | **Sì**. `worker-inference` (coda `inference`, concurrency 1); nessuna chiamata LLM dentro il ciclo portfolio | `celery_app.py`, log |
| Rischio che un'allucinazione entri in decisione? | **Sì, per attribuzione ticker, non per contenuto**: il ticker viene dai tag del provider, non dall'LLM, ma il fan-out fa scorare l'articolo sbagliato sul simbolo sbagliato (caso SPCX/Intel, sotto) | `news_log` |

---

## 6. Tabella segnali finali per ticker (solo simboli con almeno una riga oltre |0,30|)

| Ticker | n segnali | max score | min score | oltre gate? | esito |
|---|---:|---:|---:|---|---|
| INTC | 9 | **+0,640** | +0,010 | sì (×3) | BUY 14:52; i successivi bloccati SKIP_PYRAMIDING |
| AXP | 3 | +0,607 | +0,040 | sì | BUY 15:52 → SELL 18:52 |
| QQQ | 6 | +0,407 | −0,346 | sì (entrambi i segni) | BUY 17:07, ancora aperta |
| SPCX | 10 | +0,390 | −0,420 | sì (entrambi i segni) | BUY 15:52 → SELL 17:37 |
| GS | 5 | +0,291 | −0,386 | sì, ribassista | nessun ordine (long-only, non detenuto) |
| MRVL | 3 | +0,325 | 0,000 | sì | BUY 14:07, ancora aperta |
| AMD | 3 | +0,355 | 0,000 | sì | **SKIP_PYRAMIDING** (detenuto da S1 dal 14/07) |
| JPM | 4 | +0,337 | −0,138 | sì | SKIP_PYRAMIDING |
| BA | 8 | +0,304 | −0,335 | sì (entrambi i segni) | SELL 18:07 |
| HOOD | 3 | +0,141 | −0,325 | sì, ribassista | nessun ordine (long-only) |
| IWM | 3 | +0,120 | −0,327 | sì, ribassista | nessun ordine |
| SPY | 21 | +0,120 | −0,420 | sì, ribassista | non nel perimetro S4 |
| META | 7 | +0,266 | — | **no** (0,266 < 0,30) | BUY comunque — vedi nota |

> Nota META: `signal_score` = 0,266 < gate 0,30 ma il BUY è passato. Il gate applicato è quello **feedback-adjusted**
> (`reason` delle SKIP_THRESHOLD: "score < feedback threshold 0.300"); la decisione BUY riporta invece
> `score = 0,020` (peso target 2%) e `signal_score = 0,266`. Il ranking S4 seleziona i top-N e il gate effettivo di
> quel ciclo è stato soddisfatto perché il segnale era il migliore disponibile. Non è un difetto nuovo, ma la
> discrepanza fra i due campi rende il gate non verificabile a posteriori da `execution_decisions` da solo.

**Dispositions S4 del giorno** (`s4_intent_events`, 1.787 candidati osservati):

| reason_code | n |
|---|---:|
| SKIP_ENTRY_GATE | 746 |
| SKIP_ENTRY_FRESHNESS | 628 |
| SKIP_FALLBACK | 186 |
| SKIP_PYRAMIDING | 90 |
| SKIP_STALE | 71 |
| RANK_OUTSIDE_TOP_N | 40 |
| SKIP_IDEMPOTENCY | 11 |
| RANK_LONG_ONLY | 8 |
| **SUBMITTED** | **7** |

---

## 7. Tabella ordini generati / eseguiti

Modalità: **paper** — `ALPACA_BASE_URL=https://paper-api.alpaca.markets`, `execution.engine: portfolio`
(`config/trading.yaml:142`), `run-execution` legacy inattivo tutto il giorno (`{'skipped': True, 'reason': 'engine=portfolio'}`).

| # | Decisione (UTC) | Strat | Ticker | Azione | Qty | Prezzo atteso | Fill | Stato | Submitted→Filled | Segnale causante | Risk check | Anomalia |
|---|---|---|---|---|---:|---|---:|---|---|---|---|
| 1 | 14:07:00 | S4 | MRVL | BUY | 6,3743 | n/d | 230,99 | filled | 14:07:09→10 | 11110 (+0,325) | regime ×0,7, peso 2% | `decision_price` NULL |
| 2 | 14:22 | S4 | MRVL | stop protettivo | **6** | — | — | `new` | — | — | copre 94,1% | qty intera (F-022) |
| 3 | 14:37:00 | S4 | META | BUY | 2,1686 | n/d | 678,83 | filled | 14:37:08→09 | 11150 (+0,266) | idem | — |
| 4 | 14:52:07 | S4 | META | stop protettivo | 2 | — | — | canceled 16:22 | — | — | copre 92,2% | — |
| 5 | 14:52:00 | S4 | INTC | BUY | 14,5237 | n/d | 101,357 | filled | 14:52:07→08 | 11152 (+0,378) | idem | — |
| 6 | 15:07:07 | S4 | INTC | stop protettivo | **14** | — | — | `new` | — | — | copre 96,4% | qty intera |
| 7 | 15:07:00 | S4 | ORCL | BUY | 10,2714 | n/d | 143,29 | filled | 15:07:07→07 | 11160 (+0,280) | idem | — |
| 8 | 15:22 | S4 | ORCL | stop protettivo | 10 | — | — | canceled 16:52 | — | — | — | — |
| 9 | 15:52:00 | S4 | AXP | BUY | 4,6368 | n/d | 317,43 | filled | 15:52:06→07 | 11172 (+0,607) | idem | comprato a −2,23% di seduta |
| 10 | 15:52:00 | S4 | SPCX | BUY | 9,6686 | n/d | 152,23 | filled | 15:52:06→07 | 11175 (+0,390) | idem | percentile range 0,910 |
| 11 | 16:07 | S4 | AXP/SPCX | stop protettivi | 4 / 9 | — | — | canceled | — | — | — | — |
| 12 | 16:22:00 | S4 | META | **SELL** | 2,1686 | n/d | 676,18 | filled | 16:22:06→07 | **NULL** | — | sentiment vivo **+0,266** |
| 13 | 16:52:00 | S4 | ORCL | **SELL** | 10,2714 | n/d | 143,638 | filled | 16:52:07→09 | **NULL** | — | sentiment vivo **+0,280** |
| 14 | 17:07:00 | S4 | QQQ | BUY | 2,0745 | n/d | 709,47 | filled | 17:07:05→06 | 11218 (+0,407) | idem | articolo macro fan-out 8 ticker |
| 15 | 17:22 | S4 | QQQ | stop protettivo | **2** | — | — | `new` | — | — | copre 96,4% | qty intera |
| 16 | 17:37:00 | S4 | SPCX | **SELL** | 9,6686 | n/d | 151,08 | filled | 17:37:06→08 | **NULL** | — | causato da articolo su **Intel** |
| 17 | 18:07:00 | S4 | BA | **SELL** | 6,9038 | n/d | 207,72 | filled | 18:07:05→07 | **NULL** | — | `exit_mechanism` = `[unknown]` |
| 18 | 18:52:01 | S4 | AXP | **SELL** | 4,6368 | n/d | 315,28 | filled | 18:52:07→08 | **NULL** | — | sentiment vivo **+0,078** |

- **12 ordini S4 + 7 stop protettivi = 19 ordini inviati**, contro `portfolio_cycles.orders_count` che somma **113** (F-014).
- **0 reject, 0 cancel non intenzionali, 0 ordini fuori RTH, 0 ordini duplicati nello stesso minuto, 0 ordini su ticker fuori watchlist.**
- **`decision_price` e `decision_price_source` sono NULL su tutte e 12 le decisioni ordinanti**: non c'è un prezzo di riferimento persistito al momento della decisione, quindi lo slippage decisione→fill non è calcolabile.
- Latenza submit→fill: 1–2 s su tutti gli ordini. Esecuzione pulita.

---

## 8. Tabella PnL / rendimento

### Realizzato (5 chiusure, tutte S4)

| Trade | Ticker | Ingresso | Uscita | Qty | Entry | Exit | Gross | Costi | **Net** | Motivo | Aperta il |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|
| 1006 | META | 14:37 | 16:22 | 2,1686 | 678,83 | 676,18 | −5,75 | 0,29 | **−6,04** | hold_minimum_expiry | 09-16 |
| 1008 | ORCL | 15:07 | 16:52 | 10,2714 | 143,29 | 143,638 | +3,57 | 0,81 | **+2,76** | hold_minimum_expiry | 09-16 |
| 1010 | SPCX | 15:52 | 17:37 | 9,6686 | 152,23 | 151,08 | −11,12 | 1,55 | **−12,67** | hold_minimum_expiry | 09-16 |
| 1009 | AXP | 15:52 | 18:52 | 4,6368 | 317,43 | 315,28 | −9,97 | 0,81 | **−10,78** | portfolio_sell | 09-16 |
| 1003 | BA | 09-15 16:07 | 18:07 | 6,9038 | 210,30 | 207,72 | −17,81 | 0,80 | **−18,61** | portfolio_sell | **09-15** |
| | | | | | | | **−41,08** | **4,26** | **−45,34** | | |

### Non realizzato (3 posizioni aperte il 09-16 e ancora a libro a fine seduta)

| Trade | Ticker | Entry | Qty | MTM EOD | Costo d'ingresso |
|---|---|---:|---:|---:|---:|
| 1005 | MRVL | 230,99 | 6,3743 | **−8,16** | 0,78 |
| 1007 | INTC | 101,357 | 14,5237 | **−4,46** | 0,78 |
| 1011 | QQQ | 709,47 | 2,0745 | **−9,85** | 0,26 |
| | | | | **−22,47** | 1,82 |

### Aggregati

| Voce | Valore |
|---|---|
| Realizzato del giorno | **−45,34 $** |
| … da posizioni aperte il 09-16 | −26,73 $ |
| … da posizioni aperte prima del 09-16 (BA) | −18,61 $ |
| MTM su ingressi del giorno ancora aperti | −22,47 $ |
| **Totale attribuibile all'attività S4 del 09-16** | **−67,81 $** |
| Realizzato S1 | 0,00 $ |
| Costi/commissioni stimati (TradeCostCalculator) | 5,28 $ su 7 roundtrip/ingressi (1,77–10,27 bps) |
| Equity di chiusura (`market_daily.jsonl`) | 109.257,45 $ (da 109.245,16 $ il 09-15: **+12,29 $**) |
| NAV `risk_reports` 22:30 | 108.962,74 $ — **discrepanza 294,71 $** con l'equity, non riconciliata |
| SPY / QQQ del giorno | −0,441% / +0,026% |
| Esposizione / HHI / drawdown | 31,05% / 0,0285 / 1,37% — **0 alert** |
| S4 economico cumulato (finestra) | **−979,55 $** contro banda ±200 $ (fuori banda; BOOK −654,00 $, S1 +360,38 $, CONTAMINAZIONE −34,84 $). Valore riletto da `economic_pnl.json` rigenerato il 2026-09-17T10:15 |
| Giorno della finestra di osservazione | 29/40 |

**Slippage: non misurato.** `trades.slippage_est` è **identico a `cost_usd`** su tutte le righe (0,81/0,81; 0,2947/0,2947; 1,5466/1,5466) — è una copia del costo modellato, non una misura di esecuzione (F-015). Con `decision_price` NULL non esiste nemmeno il riferimento per calcolarlo. Query che servirebbe: persistere il mid/last al `tick_time` della decisione e confrontarlo con `filled_avg_price`.

---

## 9. Analisi correttezza buy/sell

| Controllo | Esito | Evidenza |
|---|---|---|
| BUY generati solo quando consentito | **OK** — 7/7 con segnale ensemble non-fallback, sopra gate, dentro RTH, top-N | `execution_decisions`, `s4_intent_events` (7 SUBMITTED) |
| SELL/exit generati correttamente | **Meccanicamente sì, semanticamente no** — 4/4 uscite intraday su sentiment **positivo** (+0,266, +0,280, +0,055, +0,078) | dec 27989, 28215, 28552, 29161 |
| Stop-loss rispettati | **Nessuno scattato** (`stop_decisions` = 0 righe). Gli stop esistono ma coprono solo la parte intera della qty e nascono un ciclo dopo l'ingresso | `stop_decisions`, orders API |
| Signal flip rispettato | **No, quando il flip è una lettura single**: SPCX −0,420 alle 16:48 ignorato perché `fallback_used=true` | signal 11214 |
| Max holding days rispettato | **OK** — tenuta max 26,0 h (BA); nessuna posizione S4 oltre l'orizzonte | `chiusure` del dossier |
| Rebalance band rispettata | **Non esiste banda**: gate d'ingresso 0,30, soglia d'uscita 0 | F-013 |
| Ordini duplicati | **Nessuno** — 0 ordini identici nello stesso minuto | orders API |
| Ordini contrari ravvicinati senza rationale | **Nessun roundtrip < 30 min**; il più corto è 1 h 45 min (META, ORCL, SPCX) e ha rationale registrato | trades |
| Pyramiding (>3 BUY consecutivi senza SELL) | **Nessuno** — il guard P0-05 ha bloccato 11 tentativi | `execution_decisions` |
| Ordini su ticker non consentiti | **Nessuno** — 207 righe scartate `not_tradable` a monte | `news_queue_drops` |
| Ordini fuori orario | **Nessuno** — 0 decisioni ordinanti fuori 13:30–20:00 | query di controllo |
| Trade su dati stale | **No** — 628 SKIP_ENTRY_FRESHNESS + 71 SKIP_STALE applicati | `s4_intent_events` |
| Trade su output LLM non valido | **No** — 0 parse_fail; le letture single sono escluse dal BUY | `ingestion_stats_daily` |
| Circuit breaker attivo | **Non è scattato**: nessun outage ensemble (6 timeout isolati). Il ratchet loss-feedback S4 era in stato *frozen* (5 perdite consecutive) ma non blocca gli ingressi | worker log 18:30 |
| Strategia disabilitata | N/A — S1 e S4 attive, S2/S3 mai eseguite | `portfolio_cycles.strategies_run` |
| Paper/live coerente | **OK** — paper su tutta la catena | env + config |
| Idempotenza retry Celery | **OK** — 11 SKIP_IDEMPOTENCY, 0 `SoftTimeLimitExceeded`, 0 fill duplicati; il riconciliatore ha riemesso 21 eventi ad ogni giro ma il DB ne ha 38 totali (dedup regge) | `s4_lifecycle_events` |
| Riconciliazione ordini/fill/posizioni | **OK alle 21:35** (41 fully_held, 1 partially_wound_down, **0 anomalie**) — **KO alle 19:42** (21 falsi `BROKER_POSITION_MISSING`) | worker log, `s4_lifecycle_events` |
| `exit_mechanism` interpretabile | **Attenzione**: BA porta `[unknown]` con la nota esplicita "non è una signal expiry, vedi #184". Le etichette di questa giornata sono **post-fix #184** e leggibili, ma `[whipsaw]` su META resta una deduzione dall'età del segnale, non una misura del meccanismo | dec 28798, 27989 |

---

## 10. Anomalie trovate

**Aggancio al ledger delle evidenze** (`docs/evidence/findings.json`, aggiornato il 2026-09-17).
26 occorrenze appese; nessun record preesistente modificato. Tre id nuovi (F-083, F-084, F-085) piu' uno
emerso dalla passata di verifica (F-086); tutti gli altri agganciati a finding gia' aperti.

| finding | DAY | costo_usd registrato |
|---|---|---:|
| **F-083** (nuovo) | DAY-001 | null (corruzione di ledger, non monetizzabile) |
| **F-084** (nuovo) | DAY-002 | null (sola presentazione) |
| F-074 | DAY-003 | **0,00** (affermato: i cicli 19:22 e 19:52 non hanno inviato ordini) |
| F-008 | DAY-004 | **−1,93** (risparmio: `drift_post_uscita` SPCX) |
| F-013 | DAY-005 | **−24,34** (risparmio: drift META+ORCL+AXP) |
| F-010 | DAY-006 | null (non misurabile per F-079) |
| F-054 | DAY-007 | null |
| F-062 | DAY-008 | null |
| F-005 | DAY-009 | null |
| F-021 | DAY-010 | null (prezzo 13:52 non ricostruibile; bound noto +18,99 $) |
| F-076 | DAY-011 | null |
| F-012 | DAY-012 | **+9,85** (MTM EOD del BUY QQQ nato da fan-out macro) |
| F-019 | DAY-013 | null (il costo alpha del giorno è già su F-030) |
| F-011 | DAY-014 | null |
| F-031 | DAY-015 | **−83,84** (risparmio: Σ `counterfactual_return_1h` × `intended_notional_usd`) |
| F-022 | DAY-016 | **0,00** (affermato: `stop_decisions` vuota) |
| F-015 | DAY-017 | null |
| F-016 | DAY-018 | null |
| F-007 | DAY-019 | null |
| F-004 | DAY-020 | null |
| F-078 | DAY-021 | null |
| F-014 | DAY-022 | null |
| F-057 | DAY-023 | null |
| F-040 | DAY-024 | null (perimetro long-only, non difetto) |
| **F-085** (nuovo) | DAY-025 | **0,00** (affermato: nessuna riga `news_log` prima delle 13:32) |
| **F-086** (nuovo) | DAY-026 | null |

Netto monetizzato della giornata sui difetti: **−100,26 $**, cioè i difetti strutturali hanno *risparmiato*
100 $ in questa seduta (uscite anticipate e guard anti-pyramiding dal lato giusto del movimento), contro
+9,85 $ di costo reale. Il segno favorevole è una proprietà della giornata, non del design: F-008, F-013 e
F-031 hanno segno cumulato positivo (costoso) sulla finestra.


### [DAY-001] Un guasto di rete viene persistito come osservazione di business nel ledger append-only S4

* Tipo: Bug
* Area: Ops / Data
* Evidenza:
  * file/log/tabella: `logs/containers/worker-2026-09-16.log`; `s4_lifecycle_events`
  * timestamp: 2026-09-16 19:42:04–19:42:35 UTC
  * snippet/query:
    ```
    19:42:04,030 WARNING #295: broker positions unavailable during lifecycle reconcile:
      NameResolutionError(paper-api.alpaca.markets)
    19:42:35,827 INFO  run_reconcile_fills_intraday succeeded: {'updated': 0,
      's4_lifecycle_events': 21, 's4_p0_events': 23, 's4_p1_events': 21}
    ```
    ```sql
    SELECT symbol, status, reason_code, broker_quantity, reconstructible
    FROM s4_lifecycle_events WHERE observed_at::date='2026-09-16'
      AND reason_code='BROKER_POSITION_MISSING';  -- 21 righe, broker_quantity NULL, reconstructible=f
    ```
* Descrizione: il riconciliatore ha ricevuto un errore DNS sulle posizioni broker, l'ha loggato correttamente
  come tale (`#295: broker positions unavailable`) e ha poi scritto comunque 21 righe
  `ENTRY_RECONCILIATION / BROKER_POSITION_MISSING` con `status='FILLED'` e `broker_quantity=NULL`, più 23 eventi
  P0 e 21 P1 derivati. Il codice distingue "non lo so" da "non c'è" nel log ma non nel ledger.
* Impatto: il ledger append-only del trial S4 — che per costruzione non si riscrive — contiene 21 osservazioni
  false su 38 della giornata (55%). Ogni misura successiva che conta le posizioni mancanti al broker userà
  questi dati. Le stesse 21 posizioni erano regolarmente a libro (riconciliazione delle 21:35: 0 anomalie).
* Severità: **High**
* Confidenza: High
* Azione consigliata: ticket di correttezza — quando `list_positions()` solleva, il riconciliatore deve uscire
  senza emettere eventi (fail-closed), oppure emettere un `reason_code` distinto (`BROKER_UNREACHABLE`) escluso
  da ogni aggregato. Retrofit: marcare le 21 righe del 19:42 come non osservative.
* Test/monitor consigliato: test che, con il client broker che solleva, `run_reconcile_fills_intraday` non
  produca righe con `reason_code='BROKER_POSITION_MISSING'`; alert se `reconstructible=false` compare su >5 righe in un ciclo.

### [DAY-002] `/api/trades` espone gli ordini broker come "trade": P&L sempre nullo e BUY etichettati come uscite

* Tipo: Bug
* Area: Frontend / Data
* Evidenza:
  * file/log/tabella: API `GET /api/trades?limit=200`; tabella `trades`
  * timestamp: 2026-09-16 (tutte le righe del giorno)
  * snippet/query:
    ```
    {"id":"49d4efc3-...","symbol":"QQQ","entry_time":"2026-09-16T17:07:06Z",
     "exit_time":null?,"exit_reason":"portfolio_buy","net_pnl":null}
    {"id":"215ed2af-...","symbol":"AXP","entry_time":null,"entry_order_id":null,
     "exit_reason":"portfolio_sell","net_pnl":null}
    ```
    12 righe per il 09-16, tutte con `net_pnl = null`; il DB ha 7 ingressi e 5 chiusure per **−45,34 $**.
* Descrizione: l'endpoint restituisce una riga per **ordine** broker, non per trade: l'`id` è un order id, un BUY
  compare con `exit_reason="portfolio_buy"`, i SELL hanno `entry_time` e `entry_order_id` nulli, e `net_pnl` è
  nullo ovunque. `entry_notional` diverge anche dal DB (1.461,88 vs 1.471,86 su AXP).
* Impatto: chiunque auditi dal REST — UI, mobile, un revisore umano, una sessione forense che non interroghi il
  DB — vede una giornata a P&L zero e non può ricostruire nessuna chiusura. È la stessa classe di F-053
  (endpoint che contraddice il ledger), su un endpoint diverso.
* Severità: Medium
* Confidenza: High
* Azione consigliata: ticket — far leggere all'endpoint la tabella `trades` (o rinominarlo `/api/orders_log`
  e aggiungere un `/api/trades` che espone il ledger con `net_pnl`).
* Test/monitor consigliato: test di contratto che, dato un giorno con N chiusure a DB, `/api/trades` restituisca
  N righe con `net_pnl` non nullo e somma pari a `SUM(trades.net_pnl)`.

### [DAY-003] Il blackout DNS delle 19:37 annulla un ciclo portfolio intero e il task Celery risulta `succeeded`

* Tipo: Bug
* Area: Ops / Orders
* Evidenza:
  * file/log/tabella: `logs/containers/worker-2026-09-16.log`; `portfolio_cycles`
  * timestamp: 2026-09-16 19:37:00–19:37:05 UTC
  * snippet/query:
    ```
    19:37:04,770 WARNING Failed to fetch price bars: NameResolutionError(data.alpaca.markets) — using empty DataFrame
    19:37:04,770 ERROR   No price data available — aborting portfolio cycle
    19:37:04,771 INFO    run_portfolio_cycle succeeded in 4.77s: {'error': 'no_price_data'}
    ```
    `portfolio_cycles` del 09-16: 23 righe fra 14:07 e 19:52 — **manca 19:37**.
* Descrizione: stesso pattern di F-074 su un host diverso (`data.alpaca.markets` invece di `/v2/clock`): la
  finestra decisionale salta e Celery registra un successo. Nessun retry. Il fallimento è rilevato solo
  indirettamente (evento `Degradazione market_clock` alle 19:42, mai consegnato).
* Impatto: 15 minuti di cecità decisionale a fine seduta. Nessun ordine pendente in quel ciclo, quindi il costo
  del singolo episodio è nullo, ma il difetto è strutturale.
* Severità: Medium
* Confidenza: High
* Azione consigliata: il task deve fallire (retry o `raise`) quando aborta, non ritornare `succeeded`.
* Test/monitor consigliato: alert se `count(portfolio_cycles)` del giorno < slot RTH attesi.

### [DAY-004] Un articolo su Intel, in fan-out su 4 ticker, ha chiuso la posizione SPCX

* Tipo: Bug
* Area: News / Signal
* Evidenza:
  * file/log/tabella: `news_log` 11177-11180; `sentiment_signals` 11178; `execution_decisions` 28552; `trades` 1010
  * timestamp: articolo 15:53:03 UTC, uscita 17:37:00 UTC
  * snippet/query:
    ```sql
    SELECT id,ticker,title FROM news_log WHERE id BETWEEN 11177 AND 11180;
    -- 11177 NVDA | 11178 INTC | 11179 SPCX | 11180 TSLA
    -- tutti: "Intel Analyst Raises Price Target On Terafab, AI-Driven Turnaround"
    ```
    ```
    dec 28552: "[below_entry_gate] S4 signal fell below the active feedback entry threshold
      (age=1.7h, generated 2026-09-16 15:53 UTC, score=+0.055): weight 0.0%, position closed."
    ```
* Descrizione: SPCX era entrata alle 15:52 su un segnale +0,390 di un articolo ISSUER_SPECIFIC. Cinque minuti
  dopo, un articolo il cui soggetto è Intel — taggato anche SPCX dal provider — ha prodotto un segnale +0,055 che,
  essendo il più recente, è diventato il segnale vivo del simbolo (F-023) e ha portato il peso a 0. Su 10 righe
  SPCX della giornata, **7 riguardano Tesla, xAI, Intel o macro**, non SpaceX.
* Impatto: uscita da un mover (+5,15% di seduta) dettata da un pezzo su un'altra società. In questa giornata
  l'uscita ha evitato altre perdite (`drift_post_uscita` −1,93 $), quindi il costo dell'episodio è negativo,
  ma il meccanismo è quello che ha già fatto perdere denaro in occorrenze precedenti.
* Severità: High
* Confidenza: High
* Azione consigliata: usare `relevance`/`subject_ticker` come precondizione perché un segnale possa **abbassare**
  il peso di una posizione, non solo per alzarlo; un articolo TAG_UNCONFIRMED non deve poter zerare un peso.
* Test/monitor consigliato: contatore giornaliero di uscite il cui segnale causante ha `n_ticker_articolo > 1`
  o `relevance != ISSUER_SPECIFIC`.

### [DAY-005] Tutte e quattro le uscite intraday sono avvenute con sentiment vivo positivo

* Tipo: Bug
* Area: Signal / Orders
* Evidenza:
  * file/log/tabella: `execution_decisions` 27989, 28215, 28552, 29161
  * timestamp: 16:22, 16:52, 17:37, 18:52 UTC
  * snippet/query: META `score=+0.266`, ORCL `score=+0.280`, SPCX `score=+0.055`, AXP `score=+0.078` — tutte con
    `weight 0.0%, position closed`.
* Descrizione: il gate d'ingresso è 0,30 e la soglia d'uscita è 0. Un segnale che scende da +0,39 a +0,28 —
  ancora nettamente rialzista — porta il peso target a 0 e liquida la posizione. Tre delle quattro uscite portano
  `exit_reason = hold_minimum_expiry`: escono al primo ciclo dopo i 90 minuti di hold minimo, cioè a **1 h 45 min
  esatti** di tenuta.
* Impatto: rotazione forzata con costo di frizione su ogni giro (4,26 $ di costi realizzati su 41,08 $ di gross).
  Nel giorno osservato l'uscita anticipata ha **evitato** perdite (drift post-uscita complessivo −24,34 $ su
  META/ORCL/AXP), quindi il costo dell'occorrenza è negativo; la struttura resta però priva di banda.
* Severità: High
* Confidenza: High
* Azione consigliata: nessuna taratura (freeze). Ticket di **osservabilità**: persistere in
  `execution_decisions` il motivo strutturato dell'azzeramento del peso (rank cutoff vs gate vs vincolo di
  portafoglio), oggi deducibile solo dal testo di `reason`.
* Test/monitor consigliato: contatore giornaliero `SELL con signal_score > 0` e distribuzione delle ore di tenuta.

### [DAY-006] Un terzo delle letture degrada a modello singolo senza che alcun modello sia caduto

* Tipo: Bug
* Area: LLM
* Evidenza:
  * file/log/tabella: `sentiment_signals`, `llm_responses`, `src/llm/ensemble.py`, `src/workers/sentiment.py:440-470`
  * timestamp: intera seduta
  * snippet/query:
    ```sql
    WITH s AS (SELECT id,model_id FROM sentiment_signals
               WHERE created_at::date='2026-09-16' AND model_id LIKE 'single:%')
    SELECT s.model_id kept, r.model_id responder, count(*), sum((r.confidence<0.4)::int) below
    FROM s JOIN llm_responses r ON r.signal_id=s.id GROUP BY 1,2;
    -- single:gpt-oss | glm-5.2  | 60 | 60   ← il modello scartato aveva risposto, solo con conf<0.40
    -- single:glm-5.2 | gpt-oss  |  9 |  9
    ```
* Descrizione: **72/215 righe (33,5%)** sono etichettate `single:` e quindi `fallback_used=true`. In 69 casi su
  72 entrambi i modelli avevano risposto: il secondo è stato espulso dal filtro `min_confidence=0,40`. Il retry a
  floor 0 introdotto con #90 scatta solo quando *nessun* modello è eleggibile, mai quando ne resta esattamente
  uno — esattamente il ramo che scarta il modello che il retry userebbe. Solo 6 invocazioni su ~430 sono fallite davvero.
* Impatto: un terzo dei segnali è squalificato dal ranking BUY (#108) e dalle SELL da reversal, e il costo di
  quell'esclusione non è misurabile perché le righe SKIP_FALLBACK sono fuori dall'indice del worker
  controfattuale (F-079). Caso concreto del giorno: SPCX −0,420 alle 16:48, l'unico contro-segnale forte sulla
  posizione aperta, ignorato perché lettura single.
* Severità: High
* Confidenza: High
* Azione consigliata: ticket — applicare il retry a floor 0 anche quando resta un solo contributore eleggibile,
  così che un ensemble a due voci si formi prima di degradare a `single:`.
* Test/monitor consigliato: test che, con un modello a `confidence=0,2` e l'altro a `0,7`, l'aggregato risulti
  `ensemble:` e non `single:`.

### [DAY-007] `ensemble_std` vale 0,000 esatto sui segnali più forti del giorno

* Tipo: Bug
* Area: LLM
* Evidenza:
  * file/log/tabella: `sentiment_signals`
  * timestamp: 15:52:52 (INTC +0,640), 15:48:23 (SPCX +0,390), 18:24:51 (INTC +0,375)
  * snippet/query:
    ```sql
    SELECT count(*) FILTER (WHERE ensemble_std=0) , count(*) FROM sentiment_signals
    WHERE created_at::date='2026-09-16' AND model_id LIKE 'ensemble%';  -- 27 / 141
    ```
    Le 2 righe FinBERT, che nascono da divergenza reale (glm −0,60 vs gpt +0,05), sono anch'esse persistite con `ensemble_std=0`.
* Descrizione: la divergenza è misurata **dopo** il filtro di eleggibilità, quindi quando un solo modello
  sopravvive lo std è 0 per costruzione — proprio nei casi di massimo disaccordo. Il top score della giornata
  (INTC +0,640, confidenza 0,80) risulta a concordanza perfetta.
* Impatto: la varianza d'ensemble non è né un gate (F-037) né una misura affidabile. Qualsiasi analisi che usi
  `ensemble_std` come proxy di affidabilità legge il contrario del vero.
* Severità: Medium
* Confidenza: High
* Azione consigliata: persistere lo std calcolato sulle risposte **grezze** in un campo separato (`raw_polarity_std`).
* Test/monitor consigliato: test che, dati due output con polarità opposte, lo std persistito sia > 0.

### [DAY-008] 11 alert prodotti, 0 consegnati: 5 CRITICAL restano in `mobile_events` senza destinatario

* Tipo: Bug
* Area: Ops
* Evidenza:
  * file/log/tabella: `mobile_events`, `mobile_notification_deliveries`, `monitor_devices`, worker log 21:00
  * timestamp: 19:42, 20:00, 20:06, 21:00, 22:50 UTC
  * snippet/query:
    ```sql
    SELECT severity,count(*) FROM mobile_events WHERE created_at::date='2026-09-16' GROUP BY 1;
    -- critical 5 | warning 6
    SELECT count(*) FROM mobile_notification_deliveries WHERE created_at::date='2026-09-16';  -- 0
    SELECT count(*) FROM monitor_devices;  -- 0
    ```
    Worker 21:00: 11 righe `CRITICAL/ForkPoolWorker-4 DECAY CRITICAL` (S1 ×4, S2 ×4, S4 ×3) — solo `log.critical`.
* Descrizione: `held_news_loss_alert` ha correttamente identificato 4 posizioni cieche lato uscita
  (ASML, PFE, SBUX, WDC) e 3 `Degradazione market_clock` CRITICAL sono state registrate, ma non esiste alcun
  dispositivo registrato e zero consegne. Gli alert del decay monitor non passano nemmeno da `mobile_events`.
* Impatto: la seduta ha prodotto 11 CRITICAL di decay, 3 CRITICAL di degradazione infrastrutturale e 4 warning
  su posizioni cieche; un operatore non ne ha visto nessuno.
* Severità: High
* Confidenza: High
* Azione consigliata: instradare `mobile_events` di severità ≥ warning sul canale Telegram già funzionante,
  o registrare almeno un dispositivo.
* Test/monitor consigliato: alert di secondo livello se `mobile_events(severity='critical')` > 0 e
  `mobile_notification_deliveries` = 0 nello stesso giorno.

### [DAY-009] 4 invii Telegram su 5 rifiutati con 400 Bad Request, scartati con un warning

* Tipo: Bug
* Area: Ops
* Evidenza:
  * file/log/tabella: `logs/containers/worker-2026-09-16.log`
  * timestamp: 14:07:10 (×2), 18:30:00, 19:22:14 UTC
  * snippet/query:
    ```
    14:07:10,077 POST .../sendMessage "HTTP/1.1 400 Bad Request"
    14:07:10,078 WARNING TelegramNotifier: Failed to send alert: Client error '400 Bad Request'
    ```
    Contenuti persi: `#161: 10/40 posizioni non proteggibili` (AMAT −28,7%, WDC −22,7%/−24,3%, NOK −15,1%) e
    `Loss feedback threshold ratchet frozen for S4` (5 perdite consecutive, P&L −228,55 $).
    L'unico 200 OK è lo `stale_drop_alert` delle 22:55.
* Descrizione: il notificatore Python fallisce con 400 su 4 messaggi su 5. La correzione dell'encoding fatta sul
  percorso shell (PR #591) non copre questo percorso.
* Impatto: gli alert operativi più rilevanti della giornata (posizioni non protette a −28% e congelamento del
  ratchet S4) non sono usciti dal log.
* Severità: High
* Confidenza: High
* Azione consigliata: loggare il `response.text` di Telegram sul 400 (indica il campo offensivo) e validare il
  markup prima dell'invio.
* Test/monitor consigliato: contatore `telegram_send_failed` esposto e allertato quando > 0 in una seduta.

### [DAY-010] La griglia beat è in ora UTC fissa e ignora il DST: persi i primi 37 minuti di seduta, sprecate 2 ore dopo la chiusura

* Tipo: Bug
* Area: Ops / Orders
* Evidenza:
  * file/log/tabella: `src/workers/celery_app.py:265` e `:82-95`; `portfolio_cycles`; inference log
  * timestamp: 13:30–14:07 e 20:00–21:59 UTC
  * snippet/query:
    ```python
    "portfolio-cycle": crontab(minute="7,22,37,52", hour="14-21", day_of_week="1-5")
    ```
    Primo ciclo 14:07:00 contro apertura RTH 13:30 → persi 13:37 e 13:52.
    Su 200 invocazioni `run_sentiment_worker`, **80 hanno restituito `{'skipped': True, 'reason': 'market_closed'}`**.
    Il sistema se ne accorge: `mobile_events` 22:50 "Griglia portfolio-cycle fuori seduta" (warning, non consegnato).
* Descrizione: identica alle occorrenze del 09-14 e 09-15. In EDT la finestra 14-21 UTC parte 37 minuti dopo
  l'apertura e resta accesa 2 ore dopo la chiusura.
* Impatto: due finestre decisionali perse ogni seduta nel momento di massima dispersione (l'apertura) e 40% delle
  invocazioni sentiment sprecate. Il segnale MRVL era pronto alle 13:45 e ha atteso 22 minuti il primo ciclo utile.
* Severità: Medium
* Confidenza: High
* Azione consigliata: ancorare la griglia al calendario Alpaca (già interrogato altrove) invece che a un'ora UTC fissa.
* Test/monitor consigliato: il warning "Griglia portfolio-cycle fuori seduta" esiste già — va instradato (vedi DAY-008).

### [DAY-011] 73,5% delle righe scorate arriva al modello con entità HTML non decodificate

* Tipo: Bug
* Area: News / LLM
* Evidenza:
  * file/log/tabella: `news_log`; `src/text/sanitizer.py`
  * timestamp: intera seduta
  * snippet/query:
    ```sql
    SELECT count(*), sum((title ~ '&[a-zA-Z#0-9]+;' OR coalesce(body_full,'') ~ '&[a-zA-Z#0-9]+;')::int)
    FROM news_log WHERE fetched_at::date='2026-09-16';  -- 215 | 158
    ```
    Esempi finiti nel prompt: `What&#39;s Going On With Marvell Technology Stock Wednesday?`,
    `S&amp;P 500 Gains, Crude Falls Ahead Of Fed&#39;s Expected First Hike`, `Wednesday&rsquo;s premarket session`.
* Descrizione: `sanitize_text` normalizza NFKC e rimuove tag e zero-width ma non chiama mai `html.unescape`.
  In peggioramento rispetto al 09-15 (69,7% corpi / 23,7% titoli).
* Impatto: rumore nel prompt DK-CoT e nell'input FinBERT (che ha un budget di 512 caratteri — su uno dei due
  fallback il titolo ne ha consumati 435, lasciando 50 caratteri di corpo).
* Severità: Medium
* Confidenza: High
* Azione consigliata: `html.unescape` in `sanitize_text` prima della normalizzazione.
* Test/monitor consigliato: assert che nessuna riga scorata contenga `&[a-zA-Z#0-9]+;` dopo la sanitizzazione.

### [DAY-012] 61,9% delle righe scorate nasce da articoli fan-out multi-ticker

* Tipo: Bug
* Area: News
* Evidenza:
  * file/log/tabella: `news_log`; dossier `copertura_articoli`
  * timestamp: intera seduta
  * snippet/query:
    ```sql
    WITH u AS (SELECT url,count(*) c FROM news_log WHERE fetched_at::date='2026-09-16' GROUP BY url)
    SELECT sum(c) FILTER (WHERE c>1), sum(c) FROM u;  -- 133 / 215
    ```
    Esempi: un market-summary macro su 8 ticker (DELL, INTC, IWM, QQQ, XLE, XLF, XLK, XLV) ha generato il BUY QQQ;
    le 10 righe SPCX includono 7 pezzi su Tesla, xAI, Intel e politica AI.
* Descrizione: `mapping_fanout_extra` = 92 su 123 articoli unici; TAG_UNCONFIRMED 132/215 (61,4%), mai promossi
  a ISSUER_SPECIFIC (F-057/F-067 restano aperti: il resolver deterministico non emette RESOLVED).
* Impatto: 2 dei 7 ingressi del giorno (QQQ, e l'uscita SPCX) nascono da articoli il cui soggetto è un'altra entità.
* Severità: High
* Confidenza: High
* Azione consigliata: già coperto da QX-01 (enforcement gated sul golden set). Nessuna azione in freeze oltre
  a mantenere la misura.
* Test/monitor consigliato: quota giornaliera `righe_fanout / righe_scorate` pubblicata nel dossier (già presente).

### [DAY-013] 44,4% delle news accodate scartate come stale, sopra la soglia d'allerta

* Tipo: Anomalia
* Area: News
* Evidenza:
  * file/log/tabella: `stale_drop_metrics_daily`, `news_queue_drops`
  * timestamp: misurato 22:55 UTC
  * snippet/query:
    ```
    alpaca_benzinga | queued 792 | stale_drops 352 | already_stale_at_fetch 223 |
    went_stale_off_session 129 | stale_drop_share 0.4444 | alert_threshold 0.25 | alert_required t
    avg_fetch_latency_hours 3.15 | avg_queue_wait_hours 1.75
    ```
* Descrizione: 223 articoli erano **già stale al fetch** (non è un problema di coda) e 129 sono stati accodati
  fuori sessione. La latenza media di fetch è 3,15 h contro una finestra di entry-freshness di 2 h.
* Impatto: la maggioranza del flusso non raggiunge mai la valutazione; ciò che la raggiunge nasce quasi scaduto.
  È la stessa causa radice di F-030 (la notizia arriva a movimento fatto).
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna taratura in freeze. L'alert **è stato consegnato** (unico 200 OK del giorno): il
  meccanismo funziona.
* Test/monitor consigliato: già attivo (`stale_drop_alert`).

### [DAY-014] Tutte e 5 le SELL hanno `signal_id` NULL: la catena segnale→decisione→trade si spezza sul lato uscita

* Tipo: Bug
* Area: Data
* Evidenza:
  * file/log/tabella: `execution_decisions`; dossier `decision_signal_id_coverage`
  * timestamp: 16:22, 16:52, 17:37, 18:07, 18:52 UTC
  * snippet/query:
    ```json
    "SELL": {"rows":5,"with_signal_id":0,"fill_rate":0.0,"expected_fill_rate":"must_be_full"},
    "SKIP_PYRAMIDING": {"rows":11,"with_signal_id":8,"fill_rate":0.727},
    "regressions": ["SELL","SKIP_PYRAMIDING"]
    ```
* Descrizione: la copertura complessiva è 98,98% (779/787) ma è interamente concentrata sulle SKIP_THRESHOLD.
  Il `reason` testuale cita il segnale ("generated 2026-09-16 15:53 UTC, score=+0.055") ma la chiave esterna
  non è valorizzata: per stabilire che la SELL SPCX veniva dall'articolo su Intel ho dovuto fare parsing del testo.
* Impatto: nessuna analisi automatica può attribuire un'uscita al segnale che l'ha causata — cioè proprio il
  lato dove, oggi, si sono concentrate le anomalie.
* Severità: High
* Confidenza: High
* Azione consigliata: ticket di correttezza — valorizzare `signal_id` sulle decisioni di uscita.
* Test/monitor consigliato: il dossier ha già il campo `regressions`; va allertato quando non è vuoto.

### [DAY-015] Il guard anti-pyramiding ha bloccato 11 ingressi S4 su simboli detenuti da S1/legacy

* Tipo: Anomalia
* Area: Signal / Risk
* Evidenza:
  * file/log/tabella: `execution_decisions` (SKIP_PYRAMIDING), dossier `guard_decisions`
  * timestamp: 14:07–18:52 UTC
  * snippet/query: `P0-05 anti-pyramiding: gia' a libro dal 2026-07-14, sentiment +0.355, peso target 2.4%, target $2610.59, posizione $425.70` (AMD).
    Somma dei controfattuali a 1 h × nozionale inteso: **−83,84 $**.
* Descrizione: 5 degli 11 blocchi riguardano posizioni S1 aperte a luglio (MRK, XOM, SHEL, AMD, JPM) sottopeso
  rispetto al target S4; 4 riguardano INTC, comprato quella mattina da S4 stesso, il cui segnale è poi salito a
  +0,640 senza poter essere rincarato. 3 righe su 11 non hanno `signal_id`.
* Impatto: **in questa seduta il guard ha risparmiato 83,84 $** (i controfattuali a 1 h sono in media negativi).
  Resta il fatto che il segnale più forte del giorno (INTC +0,640) non ha potuto tradursi in esposizione.
* Severità: Low
* Confidenza: High (il controfattuale è calcolato dal worker, non da me)
* Azione consigliata: nessuna in freeze; continuare a misurare il segno cumulato del guard.
* Test/monitor consigliato: già coperto da `counterfactual_return_1h` + `intended_notional_usd`.

### [DAY-016] Gli stop protettivi coprono solo la quantità intera e arrivano un ciclo dopo l'ingresso; 10 posizioni restano scoperte

* Tipo: Bug
* Area: Risk
* Evidenza:
  * file/log/tabella: orders API; `logs/containers/worker-2026-09-16.log`
  * timestamp: 14:22, 15:07, 17:22 UTC; warning `#161` ripetuti
  * snippet/query:
    ```
    14:22:09 MRVL sell new qty 6      (posizione 6,374258625 → copertura 94,1%)
    15:07:07 INTC sell new qty 14     (posizione 14,523677979 → copertura 96,4%)
    17:22:05 QQQ  sell new qty 2      (posizione 2,074492226  → copertura 96,4%)
    14:07:09 INFO #161: 10/40 held positions are unprotectable (qty < 1):
      ['AMAT','AMD','ASML','CAT','DELL','LLY','NOK','SPY','UNH','WDC']
    14:07:09 WARNING #161: AMAT unprotected at -28.7% (qty 0.8571)
    ```
    `stop_decisions` per il 09-16: **0 righe** — nessuno stop è scattato.
* Descrizione: gli stop nascono al ciclo successivo all'ingresso (15 minuti di scopertura) e sono arrotondati per
  difetto all'unità. Dieci posizioni a libro hanno quantità frazionaria sotto 1 e non sono proteggibili affatto,
  fra cui AMAT a −28,7% e WDC a −24,3%.
* Impatto: esposizione residua non protetta. In questa seduta nessuno stop è stato toccato, quindi nessun costo.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna taratura; il warning `#161` esiste già ma non viene consegnato (vedi DAY-009).
* Test/monitor consigliato: metrica giornaliera "quota di nozionale coperta da stop".

### [DAY-017] `trades.slippage_est` è una copia esatta di `cost_usd`

* Tipo: Bug
* Area: PnL
* Evidenza:
  * file/log/tabella: `trades`
  * timestamp: 09-16
  * snippet/query:
    ```
    AXP  slip 0.8100  cost 0.8100   ORCL slip 0.8111 cost 0.8111
    META slip 0.2947  cost 0.2947   SPCX slip 1.5466 cost 1.5466
    ```
    Su MRVL, INTC e QQQ (ancora aperti) `slippage_est` è NULL.
* Descrizione: il campo non misura nulla: è il costo modellato dal `TradeCostCalculator`, non la differenza fra
  prezzo atteso e prezzo eseguito. E il prezzo atteso non esiste: `decision_price` e `decision_price_source` sono
  NULL su tutte e 12 le decisioni ordinanti.
* Impatto: la qualità di esecuzione non è misurata da nessuna parte, quindi non è nemmeno falsificabile
  l'ipotesi che i fill siano peggiori del riferimento.
* Severità: Medium
* Confidenza: High
* Azione consigliata: persistere `decision_price` (mid/last al `tick_time`) e calcolare
  `slippage = filled_avg_price − decision_price` firmato per lato.
* Test/monitor consigliato: assert `slippage_est <> cost_usd` su almeno una riga per giorno.

### [DAY-018] Il fetch del benchmark SPY fallisce 84 volte senza produrre un alert

* Tipo: Bug
* Area: Data / Ops
* Evidenza:
  * file/log/tabella: `logs/containers/worker-2026-09-16.log`
  * timestamp: intera giornata
  * snippet/query:
    ```
    84 × SPY benchmark fetch failed: {"message":"subscription does not permit querying recent SIP data"}
     1 × SPY benchmark fetch failed: NameResolutionError(data.alpaca.markets)
    ```
* Descrizione: limite di sottoscrizione SIP, permanente, degradato in silenzio a livello WARNING.
* Impatto: ogni confronto vs benchmark calcolato in-process usa un benchmark assente. Il dossier usa un'altra
  strada (Alpaca daily, `beta_1_arithmetic_v1`) e non è affetto, ma le metriche runtime sì.
* Severità: Medium
* Confidenza: High
* Azione consigliata: o si accetta l'assenza e si rimuove la chiamata, o si allerta una volta al giorno.
* Test/monitor consigliato: alert se il fetch benchmark fallisce > 5 volte in una seduta.

### [DAY-019] `ingestion_stats_daily.duplicates` (6.521) supera `fetched` (1.563) per alpaca_benzinga

* Tipo: Bug
* Area: Data
* Evidenza:
  * file/log/tabella: `ingestion_stats_daily`, `news_queue_drops`
  * timestamp: 2026-09-16 22:31 UTC (ultimo update)
  * snippet/query:
    ```
    2026-09-16 | alpaca_benzinga | fetched 1563 | queued 792 | duplicates 6521 | stale 389
    ```
    `news_queue_drops` conferma 6.521 righe `duplicate_id` allo stadio `ingestion`, di cui 410 accodate fuori sessione.
* Descrizione: il contatore dei duplicati è additivo cross-run e cross-consegna (lo stream WS consegna lo stesso
  articolo più volte: ~1,87 consegne per articolo, #48), mentre `fetched` conta il REST. I due denominatori non
  sono confrontabili ma vivono nella stessa riga.
* Impatto: nessun impatto sui segnali; la riga è però inutilizzabile come tasso di duplicazione.
* Severità: Low
* Confidenza: High
* Azione consigliata: separare i contatori per trasporto (la colonna `transport` esiste già in `news_queue_drops`).
* Test/monitor consigliato: invariante `duplicates <= fetched + ws_deliveries`.

### [DAY-020] Il decay monitor emette 11 CRITICAL con metriche identiche per S1, S2 e S4

* Tipo: Bug
* Area: Ops
* Evidenza:
  * file/log/tabella: `logs/containers/worker-2026-09-16.log`
  * timestamp: 2026-09-16 21:00:00 UTC
  * snippet/query:
    ```
    DECAY CRITICAL [S1]: IC dropped 245% from 0.035 to -0.051 ; Hit rate ... to 35.4% ; Sharpe 0.28 vs 0.95
    DECAY CRITICAL [S2]: IC dropped 221% from 0.042 to -0.051 ; Hit rate ... to 35.4% ; Sharpe 0.28 vs 1.10
    DECAY CRITICAL [S4]: IC dropped 281% from 0.028 to -0.051 ; Hit rate ... to 35.4% ; Sharpe 0.28 vs 0.80
    ```
* Descrizione: IC osservato (−0,051), hit rate (35,4%), Sharpe (0,28) e drawdown (13,4%) sono **identici** per le
  tre strategie: sono metriche pipeline-globali confrontate contro tre baseline diverse. S2 non ha mai tradato.
* Impatto: 11 alert CRITICAL al giorno che non identificano quale sleeve stia degradando. Con DAY-008 (nessun
  canale), l'effetto netto è zero segnale operativo.
* Severità: Medium
* Confidenza: High
* Azione consigliata: calcolare le metriche per strategia o dichiarare esplicitamente che l'alert è globale.
* Test/monitor consigliato: assert che due strategie con trade diversi non producano lo stesso IC osservato.

### [DAY-021] Il worker sentiment dichiara 74 fallback FinBERT quando ne sono avvenuti 2

* Tipo: Bug
* Area: LLM / Ops
* Evidenza:
  * file/log/tabella: `logs/containers/worker-inference-2026-09-16.log`; `sentiment_signals`; `finbert_fallback_events`
  * timestamp: aggregato sui 120 cicli eseguiti
  * snippet/query:
    ```
    esito aggregato: {'processed': 215, 'ensemble_success': 141, 'finbert_fallbacks': 74,
                      'skipped_stale': 389, 'skipped_not_tradable': 207}
    SELECT count(*) FROM sentiment_signals WHERE created_at::date='2026-09-16' AND model_id='finbert'; -- 2
    SELECT count(*) FROM finbert_fallback_events WHERE created_at::date='2026-09-16';                  -- 2
    ```
* Descrizione: il contatore somma letture a modello singolo (72) e fallback FinBERT reali (2). L'esito del task
  segnala un outage FinBERT del 34,4% che non è avvenuto.
* Impatto: chi legge la telemetria conclude che il fallback deterministico è in uso su un terzo del flusso;
  la realtà è che il fallback è usato allo 0,93% e il vero problema è un altro (DAY-006).
* Severità: Medium
* Confidenza: High
* Azione consigliata: separare `single_model_reads` da `finbert_fallbacks` nell'esito del task.
* Test/monitor consigliato: assert che `finbert_fallbacks` dell'esito == righe scritte in `finbert_fallback_events`.

### [DAY-022] `portfolio_cycles.orders_count` somma 113 contro 19 ordini realmente inviati

* Tipo: Bug
* Area: Ops / Orders
* Evidenza:
  * file/log/tabella: `portfolio_cycles`; orders API
  * timestamp: 14:07–19:52 UTC
  * snippet/query:
    ```sql
    SELECT sum(orders_count) FROM portfolio_cycles WHERE timestamp::date='2026-09-16';  -- 113
    ```
    Ordini submitted il 09-16 sul broker: **19** (12 S4 + 7 stop protettivi).
    Ogni ciclo riporta 3–6 ordini anche quando nessun ordine viene inviato.
* Descrizione: il campo conta gli ordini **target** del combiner, non quelli trasmessi.
* Impatto: la telemetria di ciclo è inutilizzabile come proxy di attività; ogni dashboard che la usi sovrastima
  l'attività di un fattore 6.
* Severità: Low
* Confidenza: High
* Azione consigliata: rinominare il campo in `target_orders_count` e aggiungere `submitted_orders_count`.
* Test/monitor consigliato: invariante `submitted_orders_count <= target_orders_count` verificata a fine seduta.

### [DAY-023] 132 righe su 215 restano `TAG_UNCONFIRMED`: il resolver deterministico non conferma mai

* Tipo: Rischio
* Area: News
* Evidenza:
  * file/log/tabella: dossier `copertura_articoli.totali.mapping_rilevanza`
  * timestamp: 09-16
  * snippet/query: `{"ISSUER_SPECIFIC":82,"SECTOR_MACRO":0,"FALSE_ENTITY_MATCH":1,"IRRELEVANT_FANOUT":0,"TAG_UNCONFIRMED":132,"UNKNOWN":0}`
* Descrizione: il 61,4% delle righe non ottiene un verdetto di rilevanza, e nessuna riga viene mai classificata
  `SECTOR_MACRO` o `IRRELEVANT_FANOUT`. Fra queste ci sono headline inequivocabilmente ticker-specifiche
  (es. "Circle CEO Says CLARITY Talks Are '90%' There" taggata HOOD, "Ninth Circuit Reverses Denial Of Injunction
  Against Kalshi, Robinhood" taggata HOOD): entrambe portano un verdetto UNKNOWN.
* Impatto: senza un verdetto la rilevanza non può essere usata come gate (che è il piano QX-01), e i pezzi in
  fan-out non sono distinguibili da quelli sul soggetto.
* Severità: Medium
* Confidenza: High
* Azione consigliata: già tracciato (QX-01, gated sul golden set). Nessuna azione in freeze.
* Test/monitor consigliato: quota `TAG_UNCONFIRMED` già pubblicata nel dossier.

### [DAY-024] Segnali ribassisti sopra gate su mover reali non producono alcun ordine

* Tipo: Osservazione
* Area: Signal
* Evidenza:
  * file/log/tabella: `sentiment_signals`; dossier `funnel_v2`, `candidati_miss`
  * timestamp: 15:28 (HOOD), 18:28 (GS), 19:34 (IWM/QQQ) UTC
  * snippet/query: HOOD −0,325 / seduta −5,46%; GS −0,386 / seduta −3,96%; IWM −0,327; QQQ −0,346.
    `funnel_v2.esclusi_pipeline.non_actionable_long_only = 6`.
* Descrizione: il libro è long-only e nessuno dei 4 simboli era detenuto da S4, quindi il segnale corretto non è
  azionabile per costruzione. Non è un difetto: `opportunity_v2` calcola esplicitamente `accessible = 0`.
* Impatto: 6 dei 16 mover della seduta erano inattaccabili per direzione. Il segnale c'era ed era del segno giusto.
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna — è una scelta di perimetro, non un difetto. Va però contata: è la componente
  strutturale della "miss rate" che nessuna correzione di pipeline può ridurre.
* Test/monitor consigliato: già presente (`conteggi_actionability`).

### [DAY-025] Redis MISCONF (disco pieno) abbatte l'intero stack Celery per 11 minuti senza alcun alert

* Tipo: Rischio
* Area: Ops
* Evidenza:
  * file/log/tabella: `logs/containers/worker-2026-09-16.log`, `worker-inference-2026-09-16.log`
  * timestamp: 2026-09-16 07:14:07 → 07:25:43 UTC
  * snippet/query:
    ```
    07:14:08 CRITICAL/MainProcess Unrecoverable error: ResponseError("MISCONF Redis is configured to save
      RDB snapshots, but it's currently unable to persist to disk...")
    07:14:21 … 07:25:11  ERROR/MainProcess consumer: Cannot connect to redis://redis:6379/0  (29 tentativi)
    07:25:43 INFO  Connected to redis://redis:6379/0 ; general@9f9ae88aa217 ready.
    ```
    31 righe MISCONF nel log `worker` e altre 31 nel log `worker-inference` (62 in totale).
* Descrizione: il disco dell'host si è riempito e Redis ha smesso di accettare scritture; entrambi i worker Celery
  si sono disconnessi per ~11 minuti. Nessun evento in `mobile_events`, nessun alert, nessun ticket automatico:
  l'unica traccia sono i log. L'episodio cade **fuori** dalle finestre di ingest (14:00+) e di trading, quindi la
  giornata operativa non ne risente.
* Impatto: zero sulla seduta del 09-16. Se lo stesso evento fosse caduto fra le 13:30 e le 20:00 avrebbe azzerato
  ingest, scoring e cicli portfolio senza che nessuno se ne accorgesse in tempo reale.
* Severità: Medium
* Confidenza: High
* Azione consigliata: monitor dello spazio disco con alert sul canale funzionante, e un check di liveness Redis
  che produca un `mobile_events` CRITICAL.
* Test/monitor consigliato: alert quando compaiono righe `MISCONF` nei log o quando il consumer Celery resta
  disconnesso > 60 s.

### [DAY-026] Le chiamate all'ensemble Ollama non lasciano alcuna traccia di trasporto: l'uptime non e' osservabile direttamente

* Tipo: Bug
* Area: LLM / Ops
* Evidenza:
  * file/log/tabella: `logs/containers/worker-inference-2026-09-16.log`; `llm_responses`; `src/config.py:182`
  * timestamp: intera giornata
  * snippet/query:
    ```
    $ grep -oaP '(?<=POST )https?://[^/]+' logs/containers/worker-inference-2026-09-16.log | sort | uniq -c
        242 https://api.openfigi.com
          1 https://api.telegram.org
    $ grep -aic 'ollama' logs/containers/worker-inference-2026-09-16.log
          6          # solo le 6 righe 'ensemble model failed'
    ```
    ```sql
    SELECT model_id, count(*) FROM llm_responses WHERE generated_at::date='2026-09-16' GROUP BY 1;
    -- glm-5.2:cloud 215 | gpt-oss:20b-cloud 212
    ```
* Descrizione: `OLLAMA_BASE_URL` punta a `https://ollama.com`, ma il client Ollama non passa dal logger `httpx`
  che invece traccia OpenFIGI e Telegram. Nei log della giornata **non esiste una sola riga di richiesta verso
  Ollama**: le uniche tracce sono le 6 `WARNING ensemble model failed`. L'unico modo di contare le chiamate e'
  contare le righe `llm_responses` persistite — cioe' i **successi**, che per costruzione non possono misurare
  i fallimenti silenziosi ne' la latenza.
* Impatto: **e' un difetto di misura che ha gia' prodotto un errore.** La prima stesura di questo stesso report
  ha attribuito a Ollama i 242 POST verso `api.openfigi.com` e ne ha derivato un tasso di errore del 2,5% su
  243 chiamate; il valore corretto e' 6 su ~430 (1,4%). Finche' il trasporto non e' tracciato, ogni affermazione
  su "Ollama e' rimasto su" e' un'inferenza dai successi persistiti, non una misura — ed e' esattamente
  l'affermazione che F-049 (breaker morto) rende critica.
* Severita: Medium
* Confidenza: High
* Azione consigliata: ticket di osservabilita' — emettere una riga di log (o una metrica) per invocazione di
  modello con host, modello, esito e `latency_ms`, e persistere `latency_ms` su `llm_responses`. Non tocca
  alcuna soglia: e' pura strumentazione.
* Test/monitor consigliato: assert che, per ogni giorno di borsa, `count(log_invocazioni_modello) >=
  count(llm_responses)`; alert se lo scarto fra invocazioni e risposte supera il 5% in una seduta.


---

## 11. False positive e aree risultate corrette

| Area | Verifica | Esito |
|---|---|---|
| Ollama / ensemble cloud | ~430 invocazioni (215 per modello), 6 timeout (1,4%), risposte persistite in ogni ora 13–19 UTC senza buchi | **Nessun outage.** F-049 non ricorre oggi. Evidenza dalle righe `llm_responses`, non dai log HTTP (DAY-026) |
| FinBERT input title+body (#453) | `finbert_fallback_events`: `body_chars` 50 e 437, `title_chars` 435 e 73 | **Conferma runtime soddisfatta** |
| Doppio scoring dello stesso articolo | 0 righe `sentiment_signals` con `news_log_id` duplicato | Corretto |
| `news_log_id` NULL sui segnali | 0 su 215 | Corretto (migliorato rispetto a sedute passate) |
| Ordini duplicati / race condition scheduler | 0 ordini identici nello stesso minuto | Corretto |
| Roundtrip < 30 min | il più corto è 1 h 45 min | Nessun caso |
| Pyramiding | 0 sequenze di >3 BUY senza SELL; 11 blocchi P0-05 | Corretto |
| Ordini fuori RTH | 0 su 12 decisioni ordinanti | Corretto |
| Score < 0,05 che generano ordini | 0 (il minimo che ha ordinato è +0,266) | Corretto |
| Idempotenza Celery | 0 `SoftTimeLimitExceeded`, 11 SKIP_IDEMPOTENCY, 38 righe lifecycle su 21×9 riemissioni | Dedup regge |
| Riconciliazione EOD posizioni | 21:35 → 41 fully_held, 1 partially_wound_down, **0 anomalie** | Corretto |
| Timestamp futuri | 0 righe con `published_at > fetched_at + tolleranza` | Nessuno |
| Timezone | UTC esplicito in `celery_app.py`; unico problema è la griglia fissa (DAY-010), non l'ambiguità | Non ambiguo |
| **GS: swing +0,291 → −0,386 in 18 minuti** | Sembrava instabilità del modello; sono **4 headline distinte** dello stesso intervento del CEO alla conferenza Barclays, ciascuna con un contenuto diverso (crescita wealth management vs +500 M$ di spese non-compensation) | **Falso positivo**: il modello ha letto correttamente notizie diverse |
| `FALSE_ENTITY_MATCH` su INTC | 1 articolo su 9; l'ingresso INTC è avvenuto su un articolo ISSUER_SPECIFIC diverso | Impatto nullo |
| Calendario earnings | `status: OBSERVED`, FMP risponde, 0 simboli flaggati | F-063 non ricorre |
| Circuit breaker fallback | non è scattato perché non doveva scattare (2 fallback FinBERT reali) | Corretto |

---

## 12. Dati mancanti o non accessibili

1. **Latenza e trasporto per chiamata LLM.** `llm_responses` non ha colonna di latenza e le chiamate a Ollama
   non lasciano alcuna riga di log (DAY-026): il numero di invocazioni, il tasso di errore reale e la latenza
   sono tutti inferiti dalle sole risposte riuscite. Servirebbe: `ALTER TABLE llm_responses ADD COLUMN
   latency_ms integer;` popolata dal client, piu' una riga di log per invocazione.
2. **Prezzo di riferimento alla decisione.** `decision_price` / `decision_price_source` NULL su tutte le
   decisioni ordinanti → slippage non calcolabile (DAY-017).
3. **Discrepanza equity/NAV 294,71 $.** `market_daily.jsonl` riporta equity 109.257,45 $ a fine seduta,
   `risk_reports` alle 22:30 riporta NAV 108.962,74 $. Non ho stabilito quale sia corretta: servirebbe
   `GET /v2/account` storicizzato alla chiusura (l'account Alpaca non è interrogabile retroattivamente per data).
4. **Rendimento intraday dei simboli non catturati.** Ho usato i controfattuali già calcolati dal
   `run_counterfactual_worker` (831 decisioni aggiornate, 76 senza dati) e i `mtm_eod` del dossier; non ho
   rifetchato barre da Alpaca per non uscire dal perimetro read-only locale.
5. **Costo del filtro SKIP_FALLBACK.** Le 18 righe SKIP_FALLBACK sono fuori dall'indice del worker
   controfattuale (F-079) → il costo di DAY-006 non è misurabile per costruzione.
6. **`stop_decisions` vuota.** Nessuno stop è scattato, quindi non posso verificare la logica di trigger su dati
   di questa giornata; gli stop *piazzati* sono ricostruibili solo dall'orders API.
7. **Frontend.** Non ho ispezionato l'app web: la sola evidenza lato presentazione è l'API REST (DAY-002).

---

## 13. Raccomandazioni immediate

Tutte compatibili con il freeze di taratura (`OBSERVATION_CHARTER.md`, scadenza 2026-09-28): **nessuna tocca
soglie, pesi o parametri di strategia**.

1. **Fail-closed sul riconciliatore** (DAY-001). È l'unica raccomandazione che passa il test del charter in senso
   stretto: se non la si corregge, l'evidenza raccolta nelle prossime settimane sul trial S4 è sbagliata.
2. **Valorizzare `signal_id` sulle SELL** (DAY-014). Stessa motivazione: senza di esso il lato uscita — dove oggi
   si concentrano le anomalie — non è analizzabile automaticamente.
3. **Instradare gli alert** (DAY-008, DAY-009). Oggi 11 eventi prodotti, 0 consegnati, e 4 invii Telegram su 5
   rifiutati. Come minimo: loggare il corpo della risposta Telegram sul 400.
4. **Persistere `decision_price`** (DAY-017). Senza di esso la qualità di esecuzione non sarà misurabile nemmeno
   a posteriori, a finestra chiusa.
5. **Non rinviare `html.unescape`** (DAY-011). 73,5% e in peggioramento; è una riga di codice e altera l'input
   di ogni misura di qualità del segnale.

## 14. Test o monitor da aggiungere

| # | Tipo | Oggetto |
|---|---|---|
| 1 | test | con il client broker che solleva, `run_reconcile_fills_intraday` non emette `BROKER_POSITION_MISSING` |
| 2 | monitor | alert se `reconstructible = false` su > 5 righe `s4_lifecycle_events` in un ciclo |
| 3 | monitor | alert se `count(portfolio_cycles)` del giorno < slot RTH attesi dal calendario Alpaca |
| 4 | test | contratto `/api/trades`: N chiusure a DB ⇒ N righe con `net_pnl` non nullo, somma == `SUM(trades.net_pnl)` |
| 5 | test | due output con confidenze 0,2 e 0,7 producono `ensemble:` e non `single:` |
| 6 | test | due output a polarità opposta producono `ensemble_std > 0` |
| 7 | monitor | alert di secondo livello: `mobile_events(critical) > 0` e `mobile_notification_deliveries = 0` |
| 8 | monitor | contatore `telegram_send_failed` esposto e allertato se > 0 in una seduta |
| 9 | test | nessuna riga scorata contiene `&[a-zA-Z#0-9]+;` dopo `sanitize_text` |
| 10 | monitor | contatore giornaliero: uscite il cui segnale causante ha `n_ticker_articolo > 1` |
| 11 | monitor | contatore giornaliero: `SELL` con `signal_score > 0` |
| 12 | test | `finbert_fallbacks` dell'esito task == righe scritte in `finbert_fallback_events` |
| 13 | monitor | alert se il fetch benchmark SPY fallisce > 5 volte in una seduta |
| 14 | monitor | alert su righe `MISCONF` nei log o consumer Celery disconnesso > 60 s |
| 15 | test | due strategie con trade diversi non producono lo stesso IC osservato nel decay monitor |
| 16 | monitor | invariante `submitted_orders_count <= target_orders_count` a fine seduta |
| 17 | monitor | quota di nozionale coperta da stop protettivi, per seduta |
| 18 | monitor | per giorno di borsa: `count(log_invocazioni_modello) >= count(llm_responses)`; alert se lo scarto > 5% |

## 15. Ticket tecnici suggeriti

Solo difetti di **correttezza** (esenti dal freeze) o di **osservabilità** (nessun effetto sulla taratura).

| Priorità | Titolo | Finding | Motivazione rispetto al charter |
|---|---|---|---|
| P0 | Il riconciliatore lifecycle deve uscire fail-closed quando il broker è irraggiungibile, invece di scrivere `BROKER_POSITION_MISSING` | F-083 / DAY-001 | Se non corretto, l'evidenza del trial S4 raccolta nelle prossime settimane è sbagliata |
| P0 | Valorizzare `execution_decisions.signal_id` sulle decisioni di uscita | F-011 / DAY-014 | Idem: la catena causale sul lato uscita non è ricostruibile |
| P1 | Applicare il retry a floor 0 anche con un solo contributore eleggibile (ramo `single:`) | F-010 / DAY-006 | Difetto di correttezza dichiarato in #90 e mai propagato; cambia *quali* segnali esistono, non le soglie |
| P1 | Persistere `decision_price` / `decision_price_source` e calcolare lo slippage reale | F-015 / DAY-017 | Osservabilità: senza riferimento la qualità d'esecuzione non è misurabile a finestra chiusa |
| P1 | Instradare `mobile_events` ≥ warning su un canale consegnabile | F-062 / DAY-008 | Osservabilità pura |
| P1 | Diagnosticare il 400 di `TelegramNotifier` (loggare `response.text`) | F-005 / DAY-009 | Osservabilità pura |
| P2 | `html.unescape` in `sanitize_text` | F-076 / DAY-011 | Correttezza dell'input di misura |
| P2 | Persistere `raw_polarity_std` separato da `ensemble_std` | F-054 / DAY-007 | Osservabilità; non tocca il guard di divergenza |
| P2 | Separare `single_model_reads` da `finbert_fallbacks` nell'esito del task sentiment | F-078 / DAY-021 | Osservabilità pura |
| P2 | `/api/trades` deve leggere la tabella `trades` (o essere rinominato) | F-084 / DAY-002 | Osservabilità: l'API contraddice il ledger |
| P2 | `portfolio_cycles`: separare `target_orders_count` da `submitted_orders_count` | F-014 / DAY-022 | Osservabilità pura |
| P3 | Ancorare la griglia beat al calendario Alpaca invece che a `hour="14-21"` UTC | F-021 / DAY-010 | **Cambia le finestre decisionali** → va valutato se è taratura; proporre dopo il 28/09 |
| P3 | Alert su spazio disco / liveness Redis | F-085 / DAY-025 | Ops |
| P3 | Metriche decay per strategia invece che pipeline-globali | F-004 / DAY-020 | Osservabilità |
| P3 | Separare i contatori duplicati per trasporto in `ingestion_stats_daily` | F-007 / DAY-019 | Osservabilità |
| P2 | Loggare ogni invocazione di modello (host, modello, esito, `latency_ms`) e persistere `latency_ms` su `llm_responses` | F-086 / DAY-026 | Osservabilità: oggi l'uptime dell'ensemble e' inferito dai soli successi, e l'inferenza ha gia' sbagliato |

## 16. Stato sistema

| Voce | Valore |
|---|---|
| **Ollama (ensemble cloud)** | **UP** tutta la giornata. ~430 invocazioni di modello (215 `glm-5.2:cloud` + 215 `gpt-oss:20b-cloud`), 6 fallimenti (**1,4%**), tutti `gpt-oss:20b-cloud`, `kind=error`, timeout 90 s, in 2 grappoli isolati (12:18–12:19 ×3, 18:39–18:57 ×3); 3 recuperati dal retry, 3 segnali rimasti a una sola risposta. **Downtime: 0 minuti** — `llm_responses` ha righe in ogni ora fra le 13 e le 19 UTC. **Le chiamate non lasciano traccia HTTP** (DAY-026): il conteggio e' derivato dalle righe persistite, non dai log. |
| **Modelli attivi** | `glm-5.2:cloud` + `gpt-oss:20b-cloud` (coerente con `config:sentiment_llm_models`) |
| **FinBERT fallback rate (reale)** | **2 / 215 = 0,93%** delle righe scorate. Entrambe su SPY, entrambe per divergenza vera dell'ensemble. Entrambe con titolo+corpo confermati in `finbert_fallback_events`. |
| **Fallback rate dichiarato dal worker** | 74 / 215 = 34,4% — **sovrastimato di 36×** (include le letture a modello singolo, DAY-021) |
| **Letture a modello singolo** | 72 / 215 = 33,5%, di cui 69 causate dal filtro `min_confidence=0,40`, non da guasti |
| **Decisioni ordinanti da segnale non-fallback** | 7/7 BUY. Nessun ordine nato da un fallback. |
| **Worker restart events** | 6: 05:28 (worker+inference), 07:25 (recovery Redis), 08:24, 08:45, 10:20 (inference), 20:06 (inference, reconnect). **Tutti fuori RTH.** |
| **Outage infrastrutturali** | Redis MISCONF 07:14–07:25 (**11 min**, pre-market); blackout DNS intermittente 19:37, 19:42, 20:00, 20:06 (11 `NameResolutionError`) → 1 ciclo portfolio annullato e 21 righe di ledger corrotte |
| **Postgres** | 1 `OperationalError` durante il MISCONF; nessun altro errore |
| **Cicli portfolio eseguiti** | 23 su 24 slot della griglia 14:07–19:52 (manca 19:37) — e 2 slot (13:37, 13:52) mai schedulati |
| **Cicli sentiment** | 120 eseguiti + 80 skip `market_closed` su 200 invocazioni |
| **Alert prodotti / consegnati** | 11 `mobile_events` (5 CRITICAL) + 11 `DECAY CRITICAL` solo a log + 5 invii Telegram → **1 consegnato** |
| **Finestra di osservazione** | giorno 29/40, scadenza attesa 2026-09-28. S4 economico cumulato −979,55 $ (fuori banda ±200 $) |
