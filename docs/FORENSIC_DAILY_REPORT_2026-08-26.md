# Forensic Daily Report — 2026-08-26

**Timezone operativo: UTC**, verificato nel codice (`src/workers/celery_app.py:51-52` →
`timezone="UTC"`, `enable_utc=True`). Nessuna ambiguità. RTH del 2026-08-26 = **13:30–20:00 UTC**
(EDT, DST attivo). Sessione regolare confermata dalle barre Alpaca SIP nel dossier
(`regular.first_bar_at 13:30:00+00`, `last_bar_at 19:55:00+00`, 78 barre da 5 min).

**Fonti usate.** Query dirette `docker exec alembic-postgres-1 psql -U trading -d trading`
(`news_log`, `news_queue_drops`, `ingestion_stats_daily`, `sentiment_signals`, `llm_responses`,
`llm_budget`, `fallback_counters`, `execution_decisions`, `portfolio_cycles`, `trades`,
`audit_log`, `risk_reports`, `stop_decisions`, `stop_shadow_log`, `s4_intent_events`,
`s4_lifecycle_events`, `s4_exit_policy_events`); Redis (`docker exec alembic-redis-1 redis-cli`);
`docs/evidence/dossier/2026-08-26.json` (deterministico, Alpaca SIP `adjustment=all`); lettura
codice in `src/`.

**Fonti NON disponibili.**
1. **API REST locale**: tutti gli endpoint indicati nel prompt rispondono
   `{"detail":"Invalid or expired JWT token"}` con l'header `Authorization: Bearer <token>`
   (**[F-041]**, quinta occorrenza). Nessun dato del report proviene dalla REST.
2. **Log dei container del 2026-08-26**: inesistenti. I container `worker`, `worker-inference`,
   `beat`, `api` sono stati ricreati il 2026-08-27 alle 10:13:59 UTC per il deploy di
   `c9f77d2`/`c885643`/`2be7b32`; la prima riga di log disponibile è
   `[2026-08-27 10:14:04]`, `docker compose logs worker-inference | grep -c 2026-08-26` = **0**
   (**[F-027]**). Conseguenza diretta: l'anomalia principale della giornata (§10 [DAY-001]) è
   **datata al secondo dai contatori a DB ma non diagnosticabile** — lo stack trace o lo status
   HTTP di Ollama Cloud non esiste più.
3. **Broker Alpaca**: non interrogato in questa sessione (modalità read-only, nessuna chiamata
   broker). Per la riconciliazione posizioni cito
   `docs/ALPHA_MISS_REPORT_2026-08-26.md` §7 [F-048], che l'ha eseguita lo stesso giorno.

> **Avvertenza `exit_mechanism` (#184).** Le due uscite della giornata portano
> `execution_decisions.exit_mechanism = 'below_entry_gate'` e un `reason` che nomina il ramo di
> codice, l'età del segnale e lo score (`age=0.3h vs max_age=4h ... score=-0.006`). È quindi una
> **etichetta osservata**, non dedotta dall'età dell'ultimo segnale a DB: nessun conteggio di
> questo report è una stima per orologio. Nessuna riga pre-fix è stata contata.

---

## 1. Executive summary

Il 2026-08-26 la pipeline ha girato end-to-end senza crash, ma **ha perso metà del suo apparato
di valutazione a metà sessione e nessuno lo ha saputo**. L'ultima risposta dei due modelli
Ollama Cloud è alle **15:31:00.458 UTC**; dalle 15:45 alla chiusura (19:45) **tutti i 79 segnali
residui sono FinBERT puro** — 81,6% di fallback sulla giornata contro 28–40% nelle otto sedute
precedenti e **0,0% il 2026-08-25**. Il budget LLM non era esaurito ($0,0377 spesi contro ~$0,20
tipici, `budget_exhausted=false`), quindi è un guasto del provider, non un limite di spesa. Il
circuit breaker è scattato alle 15:45:07 e non ha avvisato nessuno: la sua azione di sizing
(`qc:sizing_multiplier=0.5`) **non è letta da alcun consumatore** e la callback Telegram
`on_fallback_alert` **non è mai passata da alcun chiamante di produzione** — codice morto su
entrambi i rami (§10 [DAY-001]). Effetto a valle: i 79 segnali FinBERT non hanno
`directness`/`event_type`, quindi 80 righe su 114 hanno `relevance=UNKNOWN` nel dossier, e la
regola #108 li esclude dal ranking BUY. **Su tutta la giornata un solo segnale non-fallback ha
superato il gate 0,30 (MU +0,3084) ed è stato bloccato da P0-05 perché il titolo era già a
libro: zero ingressi erano possibili per costruzione.** Le uniche due operazioni sono **uscite**:
NVDA venduta 14:22 (−$18,73) su un articolo *su Goldman Sachs e l'"atrofia cognitiva" da AI*
(score −0,0056), e META venduta 15:07 (+$61,68) su un listicle *"Here's How Much $1000 Invested
In Meta 10 Years Ago Would Be Worth Today"* (score esattamente 0,000). Entrambe **ex-post
redditizie** (drift evitato −$9,21 e −$39,65), entrambe **funzionalmente sbagliate**: assenza di
informazione trattata come contro-segnale. Realizzato del giorno **+$42,95**; NAV 110.073,75 $;
drawdown 1,24%; esposizione 29,34%. Tre esecuzioni della suite di test hanno scritto e cancellato
righe nel DB di produzione pre-market.

## 2. Verdict finale

> **ANOMALIE SIGNIFICATIVE.**

Non "processo non affidabile": la catena ha girato, i 24 cicli portfolio sono a cadenza esatta di
15 minuti senza buchi, la contabilità di ingest quadra, le due uscite sono tracciate al centesimo
e nessun ordine è stato inviato fuori orario, duplicato o senza risk check. Ma:

* un componente centrale (l'ensemble LLM) è stato **giù per 4h14m su una sessione di 6h30m** e il
  meccanismo che doveva segnalarlo è **codice morto verificato** — questo è un difetto di
  correttezza dell'osservabilità, non una taratura;
* le **due sole decisioni della giornata** sono state prese su articoli a informazione nulla, con
  un segnale a 0,000 che liquida una posizione da 2% del NAV;
* **zero ingressi possibili** per la combinazione outage + #108 + P0-05, il che rende la seduta
  quasi priva di contenuto informativo per la domanda di uscita n.1 del periodo di osservazione.

## 3. Timeline del 2026-08-26 (tutti gli orari UTC)

| Ora UTC | Fase | Componente | Evento | Evidenza |
|---|---|---|---|---|
| 07:13:54 | pre-market | suite di test | INSERT di 4 righe `trades` `TEST_STOP_*` nel DB **di produzione** | `audit_log` 14912-14915 |
| 07:14:58 | pre-market | suite di test | 1 riga `news_queue_drops` `reuters`, `url='https://reuters.com/article/foo'` | `news_queue_drops` |
| 08:14:55 | pre-market | suite di test | secondo run: altre 4 righe `TEST_STOP_*` | `audit_log` 14916-14919 |
| 08:15:59 | pre-market | suite di test | secondo drop `reuters` fixture | `news_queue_drops` |
| 08:36:30 | pre-market | suite di test | terzo run: altre 4 righe `TEST_STOP_*` | `audit_log` 14920-14923 |
| 08:37:34 | pre-market | suite di test | terzo drop `reuters` + `ingestion_stats_daily(2026-08-26,'reuters',12,12,…)` | `ingestion_stats_daily.updated_at` |
| — | — | — | Le 12 righe `TEST_STOP_*` sono state **cancellate senza traccia** (`MAX(trades.id)=831`, id 832-846 consumati) | `trades`, `audit_log` |
| 13:30:00 | **apertura RTH** | — | prima barra SIP della sessione regolare | dossier `sessioni.regular` |
| 13:30–14:07 | market hours | beat | **37 minuti senza alcun ciclo portfolio né ingest**: `crontab(minute="7,22,37,52", hour="14-21")` | `celery_app.py:210` |
| 14:00:30 | market hours | ingest | primo fetch: 21 righe `alpaca_benzinga` + 2 `gdelt_gkg` | `news_log.fetched_at` |
| 14:00:30 | market hours | LLM | prima chiamata ensemble del giorno (`glm-5.2:cloud` + `gpt-oss:20b-cloud`) | `llm_responses`, `llm_budget.created_at` |
| 14:00:41 | market hours | scoring | NVDA **+0,078** su "Nvidia Earnings Prediction Market Preview" (ensemble, conf 0,40) | `sentiment_signals` 8954 |
| 14:03:46 | market hours | scoring | NVDA **−0,0056** su "Goldman Sachs Executive … 'Cognitive Atrophy'" (ensemble, conf 0,175) | `sentiment_signals` 8960 |
| 14:07:00 | market hours | portfolio-cycle | **primo ciclo**. 5 target BUY (CSCO, DELL, LLY, SOXX, META), 0 inviati | `portfolio_cycles` |
| 14:07:04 | market hours | S4 guard | XOM `SKIP_STALE` (22,1h > 4h); 33 `SIGNAL_STALE_SKIP` in `audit_log`; LLY/META/CSCO `SKIP_PYRAMIDING` | `execution_decisions`, `audit_log` 14924-14947 |
| 14:12:00 | market hours | lifecycle S4 | 3 fill del 08-25 (CSCO 19:07, META 19:52, NVDA 19:07) marcati **`CENSORED / FILL_OUTSIDE_RTH`** — erano dentro RTH | `s4_lifecycle_events` |
| 14:16:12 | market hours | scoring | NVDA **+0,22** (`single:gpt-oss:20b-cloud`, `fallback_used=true` → ineleggibile) | `sentiment_signals` 8967 |
| **14:22:00** | market hours | **ordine 1** | **SELL NVDA** 8,945614 @ 210,69 — `below_entry_gate`, segnale 8960 (−0,006, età 0,3h). Realizzato **−$18,73** | `trades` 829, `execution_decisions` |
| 14:31:12 | market hours | scoring | MU **+0,3084** ensemble — **unico segnale non-fallback sopra gate della giornata** | `sentiment_signals` 8972 |
| 14:45:12 | market hours | scoring | META **0,000** (conf 0,20) su "Here's How Much $1000 Invested In Meta 10 Years Ago…" | `sentiment_signals` 8975 |
| 14:52:04 | market hours | S4 guard | MU `SKIP_PYRAMIDING` (a libro dal 07-28, peso non allocato 2,0%) | `execution_decisions` |
| **15:07:00** | market hours | **ordine 2** | **SELL META** 3,340955 @ 588,0088 — `below_entry_gate`, segnale 8975 (+0,000, età 0,4h). Realizzato **+$61,68** | `trades` 831 |
| 15:12:00 | market hours | lifecycle S4 | quarta censura `FILL_OUTSIDE_RTH` (META) | `s4_lifecycle_events` |
| **15:31:00.458** | market hours | **LLM** | **ULTIMA risposta Ollama Cloud della giornata** (META, ensemble, +0,0182) | `llm_responses`, `llm_budget.updated_at` |
| 15:45:06 | market hours | **outage** | primo scoring **FinBERT puro**. `consecutive_fallback` riparte da 1 | `sentiment_signals` 8988, `fallback_counters.reset_at 15:31:00` |
| 15:45:07.379 | market hours | circuit breaker | soglia 3 raggiunta → `qc:sizing_multiplier=0.5`, `fallback:alert_sent=1`, 1 riga in `ensemble:divergence:log`. **Nessun alert, nessun consumatore** | Redis `ensemble:divergence:log` |
| 15:45–19:45 | market hours | outage | **79 segnali consecutivi FinBERT**, 0 chiamate Ollama, 0 ripristini | `sentiment_signals`, `fallback_counters` |
| 17:15:04 | market hours | scoring | MS **+0,3421** FinBERT — sopra gate, escluso da #108 | `sentiment_signals` 9016 |
| 19:15 / 19:45 | market hours | scoring | SPCX **−0,3356** poi **+0,5609**: inversione di segno FinBERT in 30 min | `sentiment_signals` 9050, 9060 |
| 19:30:05 | market hours | scoring | NVO **−0,5533** (segnale più forte del giorno, ribassista → inutilizzabile long-only) | `sentiment_signals` 9056 |
| 19:45:07.786 | market hours | outage | ultimo incremento `consecutive_fallback` → **79** | `fallback_counters.last_increment_at` |
| 19:52:00 | market hours | portfolio-cycle | **24° e ultimo ciclo**. 3 target BUY, 0 inviati | `portfolio_cycles` |
| 20:00:00 | **chiusura RTH** | — | — | — |
| 20:07–21:52 | post-market | beat | 8 slot di ciclo previsti dal crontab (`hour="14-21"`) **senza alcuna riga** in `portfolio_cycles` | `portfolio_cycles` |
| 22:30:01 | batch notturno | risk monitor | `risk_reports`: NAV 110.073,75, esposizione 0,2934, HHI 0,0250, drawdown 0,0124, `alerts=[]`, `per_strategy_metrics={}` | `risk_reports` |
| 2026-08-27 08:06:41 | — | dossier | dossier 2026-08-26 generato (a mano, dopo aggiramento di [F-044]) | dossier `generato_il` |
| 2026-08-27 10:13:59 | — | deploy | container ricreati → **log del 08-26 distrutti** | `docker inspect` |

**Cadenza.** 24 cicli, dal 14:07:00 al 19:52:00, delta costante 15 min, **nessun gap**. Nessun
`RestartCount` > 0 su alcun container.

## 4. Tabella news ingest

### 4a. Per fonte

| Fonte | fetched | duplicati scartati | no_ticker | stale (sentiment) | not_tradable (sentiment) | queued | **righe in `news_log`** | copertura temporale (fetch) |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `alpaca_benzinga` | 585 | **2.366** | 0 | 71 | 119 | 287 | **100** | 14:00:30 → 19:45:07 |
| `gdelt_gkg` | 1.775 | 3 | 1.758 | 1 | 0 | 14 | **14** | 14:30:38 → 19:45:04 |
| `reuters` | 12 | 0 | 3 | 0 | 0 | 12 | **0** | 08:37:34 (**fixture di test**) |
| **Totale reale** | **2.360** | **2.369** | **1.758** | **72** | **119** | **301** | **114** | 14:00 → 19:45 |

Contabilità: 4.321 righe in `news_queue_drops` per la giornata, tutte con `discarded_reason` e
`discard_stage` popolati. **Nessuna perdita silenziosa**: 585 − 2.366(dup, contatore additivo) …
→ 287 queued, di cui 190 scartati allo stadio `sentiment` (119 `not_tradable` + 71 `stale`) → 97
scorati, contro 100 righe `news_log` (differenza = articoli a cavallo del confine di giornata).

* `duplicates` (2.366) **supera** `fetched` (585) → **[F-007]**, il contatore è additivo
  cross-run e non è verificabile indipendentemente.
* `reuters` ha `fetched=12, queued=12` ma **zero righe** in `news_log`: è una fixture di test
  (`title='Federal Reserve holds rates steady'`, `url='https://reuters.com/article/foo'`) scritta
  alle 07:14:58, 08:15:59 e 08:37:34, **negli stessi tre run** che hanno inserito le righe
  `TEST_STOP_*` in `trades` → **[F-039]**/[F-028].
* Copertura: **nessun articolo raccolto prima delle 14:00:30 UTC**. L'ingest gira
  `minute="*/15", hour="14-21"`, quindi i 3 articoli pubblicati fra 12:31 e 13:30 UTC (pre-market
  e prima mezz'ora di sessione) sono entrati solo col fetch delle 14:00. `min(published_at)` =
  12:31:09.
* **Timestamp**: 0 righe con `published_at > fetched_at`, 0 con `published_at > now()`. Nessuna
  news dal futuro.
* **Latenza publish→fetch**: mediana **46,0 min**, media 49,5 min. Migliore della mediana storica
  ~1h50m di [F-019]: **non conto un'occorrenza di F-019 oggi**.
* **Deduplica**: 114 righe / **63 `content_hash` distinti** / 63 URL distinti → 0 duplicati di
  sindacazione per ticker, ma **51 righe di fan-out multi-ticker** (44,7%) → [F-012], occorrenza
  2026-08-26 già registrata da `ALPHA_MISS_REPORT_2026-08-26.md` §7.
* **Sanitizzazione**: presente e attiva (`sanitize_text` in `src/workers/sentiment.py`), nessun
  campo mancante nelle 114 righe (`discarded_reason` NULL su tutte, `extraction_method` popolato
  su tutte).

### 4b. Per ticker (top 15 di 51 con articoli; universo watchlist = 96)

| Ticker | righe | fonte | ISSUER_SPECIFIC | UNKNOWN | max score proprio | max score da fan-out |
|---|---:|---|---:|---:|---:|---:|
| NVDA | 15 | benzinga | — | — | +0,300 | — |
| GOOGL | 8 | benzinga | — | — | +0,017 | — |
| META | 6 | benzinga | — | — | +0,250 | — |
| MSFT | 4 | benzinga | — | — | — | — |
| XLV | 4 | benzinga | — | — | — | — |
| SPCX | 3 | benzinga | — | — | +0,561 | — |
| INTC | 3 | benzinga | — | — | +0,180 | — |
| LLY | 3 | benzinga | — | — | −0,546 | — |
| AMZN | 3 | benzinga | 0 | 3 | — | — |
| AAPL | 2 | benzinga | 0 | 2 | — | +0,006 |
| AMD | 2 | benzinga | 1 | 1 | +0,250 | — |
| MU | 2 | benzinga | — | — | +0,308 | — |
| MS | 2 | gdelt_gkg | — | — | +0,342 | — |
| AMAT | 1 | benzinga | 1 | 0 | +0,095 | — |
| HOOD | 2 | benzinga | 0 | 2 | — | +0,006 |

**Classificazione di rilevanza (dossier `copertura_articoli.totali.mapping_rilevanza`)**:
ISSUER_SPECIFIC 34, SECTOR_MACRO 0, FALSE_ENTITY_MATCH 0, IRRELEVANT_FANOUT 0,
**UNKNOWN 80**. Le 80 UNKNOWN sono **esattamente le 79 righe FinBERT + 1**: la classificazione di
rilevanza è un prodotto dei campi `llm_responses.directness`/`event_type`, che FinBERT non
produce (verificato: 79 segnali `finbert` → 0 righe con `directness`; 42+24+4 righe LLM → 100%
popolate). **L'outage non ha degradato solo il punteggio: ha spento anche il classificatore di
rilevanza.** Copertura effective-timely: **24/96 = 25,0%**.

### 4c. Notizie con maggiore impatto sul segnale

| Ora | Ticker | Titolo | Score | Effetto reale |
|---|---|---|---:|---|
| 14:03 | NVDA | "Goldman Sachs Executive Sounds The Alarm, Warns AI Could Cause 'Cognitive Atrophy' on Wall Street" | −0,0056 | **ha chiuso la posizione NVDA** (−$18,73) |
| 14:45 | META | "Here's How Much $1000 Invested In Meta Platforms 10 Years Ago Would Be Worth Today" | 0,0000 | **ha chiuso la posizione META** (+$61,68) |
| 14:31 | MU | "68% of AI Hyperscaler CapEx Could Go to Memory in 2027" | +0,3084 | sopra gate, bloccato da P0-05 |
| 17:15 | MS | (FinBERT, fonte gdelt) | +0,3421 | sopra gate, escluso da #108 |
| 19:30 | NVO | (FinBERT) | −0,5533 | segnale più forte del giorno, inutilizzabile (long-only) |
| 15:15 | HOOD | "SHIB Joins XRP, Bitcoin on Japan's First New Crypto Exchange in 4 Years" | +0,12 | nessun effetto; contenuto non riguarda HOOD |

**Confidenza dell'analisi ingest: Alta.** Ogni numero viene da `COUNT(*)` su tabelle persistite,
riconciliate fra `news_log`, `news_queue_drops` e `ingestion_stats_daily`.

## 5. Tabella performance modelli LLM

### 5a. Per modello

| Modello | richieste | successi | errori/timeout | refusal/invalid | `eligible=true` a DB | contributori reali | polarity media | conf. media | polarity min/max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `glm-5.2:cloud` | 35 | 35 | **0 registrati** | 0 | **7** | 21 (ensemble) + 2 (single) | +0,059 | 0,309 | −0,15 / +0,60 |
| `gpt-oss:20b-cloud` | 35 | 35 | **0 registrati** | 0 | **7** | 21 (ensemble) + 12 (single) | +0,035 | 0,414 | −0,35 / +0,50 |
| `finbert` (fallback) | 79 | 79 | 0 | 0 | n/a | 79 | — | — | −0,553 / +0,561 |

* **Latenza media: non misurabile.** Nessuna colonna di latenza in `llm_responses` e i log del
  giorno non esistono ([F-027]). Approssimazione dall'`ingested_to_scored` del dossier: ≈0 s
  (lo scoring è simultaneo all'ingest nel worker), quindi il dato non isola la chiamata al
  modello. **Dato mancante — vedi §12.**
* **Errori/timeout Ollama: 0 registrati e questo è il problema.** L'ensemble ha smesso di
  rispondere alle 15:31 e **non esiste una riga da nessuna parte** che registri il perché. Le
  35 righe per modello sono tutte successi; i 79 mancati tentativi non lasciano traccia.
* **`eligible` è sbagliato**: 7 righe `eligible=true` per modello contro **21 segnali ensemble**
  (= 42 risposte che hanno effettivamente contribuito). **28 contributori reali su 42 sono
  marcati `eligible=false`** → **[F-010]**.

### 5b. Composizione dei 114 segnali

| `model_id` | n | quota | `fallback_used` | `ensemble_std` medio |
|---|---:|---:|:---:|---:|
| `finbert` | **79** | **69,3%** | true | 0,000 |
| `ensemble:glm-5.2:cloud+gpt-oss:20b-cloud` | 21 | 18,4% | false | 0,056 (max 0,247) |
| `single:gpt-oss:20b-cloud` | 12 | 10,5% | true | 0,000 |
| `single:glm-5.2:cloud` | 2 | 1,8% | true | 0,000 |
| **Totale `fallback_used=true`** | **93** | **81,6%** | | |

### 5c. Per ora — il momento esatto dell'outage

| Ora UTC | segnali | ensemble | single-model | **FinBERT** |
|---|---:|---:|---:|---:|
| 14:00 | 23 | 15 | 8 | **0** |
| 15:00 | 18 | 6 | 6 | **6** |
| 16:00 | 15 | 0 | 0 | **15** |
| 17:00 | 10 | 0 | 0 | **10** |
| 18:00 | 25 | 0 | 0 | **25** |
| 19:00 | 23 | 0 | 0 | **23** |

### 5d. Confronto con la serie recente

| Giorno | segnali | `fallback_used` | quota | FinBERT puro |
|---|---:|---:|---:|---:|
| 2026-08-17 | 200 | 78 | 39,0% | — |
| 2026-08-19 | 170 | 47 | 27,6% | — |
| 2026-08-21 | 184 | 53 | 28,8% | — |
| 2026-08-24 | 124 | 43 | 34,7% | — |
| 2026-08-25 | 98 | 39 | 39,8% | **0** |
| **2026-08-26** | **114** | **93** | **81,6%** | **79** |

### 5e. Verifica funzionale della catena LLM

| Domanda | Risposta | Evidenza |
|---|---|---|
| L'output LLM è validato prima del signal store? | **Sì, parzialmente.** JSON strutturato + `fallback_used` + esclusione #108 dal ranking BUY. Ma **nessun controllo di plausibilità sul contenuto**: un listicle a informazione nulla passa come score 0,000 e viene usato per liquidare. | `execution_decisions` SELL META |
| L'ensemble gestisce la varianza alta? | **No come gate.** `ensemble_std` (max 0,247 oggi) è scritto ma non è mai una condizione d'ingresso → [F-037]. Nessuna occorrenza nuova contata: nessuna decisione della giornata è stata influenzata da varianza. | `sentiment_signals` |
| Le news duplicate pesano più volte? | **No per sindacazione** (0 duplicati per ticker, dedup su `content_hash`). **Sì per fan-out**: 51 righe extra da 63 articoli → un articolo produce fino a 3 segnali su ticker diversi. | dossier `copertura_articoli` |
| La stessa news può generare segnali multipli? | Sì, uno per ticker mappato. Ma S4 usa **solo il più recente per simbolo** → [F-023]. | — |
| La confidence bassa riduce il peso? | **Sì aritmeticamente** (`score = polarity × confidence`, verificato: META polarity 0 × conf 0,20 = 0,000; NVDA −0,0056 con conf 0,175). **No a valle**: una confidence di 0,175 e una di 0,90 attraversano lo stesso ramo `below_entry_gate`. | `sentiment_signals` 8960, 8975 |
| I modelli girano offline/background? | **Sì.** Coda Celery `inference` con `concurrency=1`; il ciclo di esecuzione legge da DB/Redis. Nessuna chiamata LLM nel percorso ordine. | `celery_app.py`, architettura |
| Rischio che un'allucinazione entri in decisione? | **Sì, dimostrato oggi in forma non-allucinatoria ma equivalente**: un modello ha correttamente valutato "nessuna informazione" (0,000) e quel giudizio è stato eseguito come "vendi". Il supervisore che dovrebbe filtrarlo non esiste su questo ramo. | §10 [DAY-003] |

## 6. Tabella segnali finali per ticker

**Segnali sopra il gate attivo (|score| ≥ 0,30; `feedback:entry_threshold:S4` = 0,30 verificato in Redis)**

| Ora | ID | Ticker | `model_id` | Score | Conf | fallback | Esito | Perché |
|---|---:|---|---|---:|---:|:---:|---|---|
| 14:31:12 | 8972 | **MU** | ensemble | **+0,3084** | 0,58 | **no** | `SKIP_PYRAMIDING` | a libro dal 2026-07-28, peso non allocato 2,0% |
| 14:31:32 | 8973 | NVDA | `single:gpt-oss` | +0,3000 | 0,60 | sì | ineleggibile | #108 single-model |
| 17:15:04 | 9016 | MS | `finbert` | +0,3421 | 0,52 | sì | `SKIP_FALLBACK` | #108 — **outage** |
| 17:30:06 | 9017 | NKE | `finbert` | −0,3025 | 0,46 | sì | nessuno | ribassista, long-only + outage |
| 19:15:06 | 9050 | SPCX | `finbert` | −0,3356 | 0,49 | sì | nessuno | ribassista + outage |
| 19:30:05 | 9056 | NVO | `finbert` | **−0,5533** | 0,67 | sì | `SKIP_FALLBACK` | ribassista, long-only + outage → [F-040] |
| 19:30:06 | 9057 | LLY | `finbert` | −0,5462 | 0,66 | sì | nessuno | ribassista + outage |
| 19:45:05 | 9060 | SPCX | `finbert` | **+0,5609** | 0,68 | sì | nessuno | 15 min dalla chiusura; **inversione di segno da −0,3356 in 30 min** |

> **Il fatto centrale della giornata in una riga: 8 segnali hanno superato il gate, 1 solo non era
> fallback, e quello è stato bloccato perché il titolo era già a libro. Zero ingressi erano
> possibili.**

**Segnali che hanno prodotto le due uscite (sotto gate, hanno agito)**

| Ora | ID | Ticker | Score | Conf | Articolo | Azione |
|---|---:|---|---:|---:|---|---|
| 14:03:46 | 8960 | NVDA | −0,0056 | 0,175 | "Goldman Sachs Executive Sounds The Alarm… 'Cognitive Atrophy'" | **SELL 14:22** |
| 14:45:12 | 8975 | META | 0,0000 | 0,20 | "Here's How Much $1000 Invested In Meta 10 Years Ago Would Be Worth Today" | **SELL 15:07** |

**Distribuzione complessiva.** 114 segnali su 51 simboli; `|score|` medio 0,0693; min −0,553,
max +0,561. 312 decisioni `SKIP_THRESHOLD` su 336 (92,9%), la moda dello score scartato è
**0,000** (87 righe).

**Disposizioni S4 registrate (`s4_intent_events`, 1.518 candidati osservati)**

| `reason_code` | n | `is_tradable` |
|---|---:|:---:|
| `SKIP_ENTRY_FRESHNESS` | 695 | f |
| `SKIP_ENTRY_GATE` | 312 | f |
| `SKIP_STALE` | 280 | f |
| `SKIP_FALLBACK` | 122 | f |
| **`SKIP_PYRAMIDING`** | **108** | **t** |
| `RANK_OUTSIDE_TOP_N` | 1 | f |

## 7. Tabella ordini generati / eseguiti

### 7a. Target del combiner vs ordini realmente inviati

| Ciclo | target emessi | inviati | bloccati |
|---|---:|---:|---:|
| 24 cicli (14:07 → 19:52) | **110** (108 BUY + 2 SELL) | **2** | **108** |

Target BUY per simbolo: CSCO 24, DELL 24, SOXX 24, LLY 17, MU 16, META 3, e **corrispondono
esattamente** alle 108 disposizioni `SKIP_PYRAMIDING` di `s4_intent_events` (CSCO 24, DELL 24,
SOXX 24, LLY 17, MU 16, META 3). Ma `portfolio_cycles.orders_count` = 110 e non distingue: →
**[F-014]**. In `execution_decisions` compaiono solo **4** righe `SKIP_PYRAMIDING` su 108 →
[F-031] (occorrenza 08-26 già registrata dall'alpha-miss).

### 7b. I due ordini eseguiti

| # | Decisione | Strategia | Ticker | Azione | Qtà | Prezzo atteso | Prezzo fill | Stato | Motore | Segnale causante | Risk check | P&L netto |
|---|---|---|---|---|---:|---:|---:|---|---|---|---|---:|
| 1 | 14:22:00.698 | **S4** (`stop_strategy=S4`) | NVDA | SELL (chiusura totale) | 8,945614364 | n/d (MARKET) | **210,69** | **filled** | Alpaca **paper** | 8960 (−0,0056) — **solo dal testo di `reason`, `signal_id` NULL** | gate d'uscita `below_entry_gate`; cap/HHI non applicabili a una chiusura | **−$18,73** |
| 2 | 15:07:00.642 | **S4** | META | SELL (chiusura totale) | 3,34095499 | n/d (MARKET) | **588,008774** | **filled** | Alpaca **paper** | 8975 (0,0000) — idem | idem | **+$61,68** |

* `order_id` distinti (`2fe5d96f-…`, `d1d09772-…`), presenti anche in `trades.exit_order_ids`.
  **Nessun ordine duplicato, nessun ordine nello stesso minuto, nessuna race.**
* **Paper/live**: paper confermato per via architetturale — `execution.engine=portfolio` con
  `ALPACA_PAPER_MODE` che governa `TradingClient(paper=…)`, e la decisione documentata in
  `config/trading.yaml:172-182` ("PAPER ONLY"). **Nota di onestà: non ho interrogato il broker in
  questa sessione, quindi la conferma è per configurazione e non per risposta dell'account.**
* Entrambi dentro RTH (14:22 e 15:07 UTC contro finestra 13:30–20:00). **Nessun ordine fuori
  orario.**
* **Rationale**: presente e leggibile in `reason`, con età e score del segnale.
* **Anomalia di tracciabilità**: `execution_decisions.signal_id` è NULL su **333/336** righe,
  incluse **entrambe** le SELL → **[F-011]**.

## 8. Tabella PnL / rendimento

### 8a. Realizzato del 2026-08-26

| Trade | Ticker | Sleeve | Apertura | Chiusura | Tenuta | Notional | Gross | Costo modellato | **Net** | Drift post-uscita |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|
| 829 | NVDA | S4 | 2026-08-25 19:07 | 2026-08-26 14:22 | 19,25 h | $1.903,10 | −$18,34 | $0,39 (1,81 bps) | **−$18,73** | −$9,21 |
| 831 | META | S4 | 2026-08-25 19:52 | 2026-08-26 15:07 | 19,25 h | $1.902,45 | +$62,07 | $0,39 (1,81 bps) | **+$61,68** | −$39,65 |
| | | | | | | | | | **+$42,95** | **−$48,87 evitati** |

* **PnL per ticker**: NVDA −$18,73; META +$61,68.
* **PnL per strategia**: **S4 +$42,95**; **S1 $0,00 realizzato** (nessuna chiusura); legacy $0,00.
* **Posizioni aperte prima del 2026-08-26**: entrambe le chiusure sono di posizioni aperte il
  2026-08-25 → **tutto il realizzato è overnight**, zero intraday.
* **Posizioni aperte il 2026-08-26**: **nessuna** (0 ingressi).
* **Slippage**: `trades.slippage_est` = 0,3886 e 0,3895 → **è una copia di `cost_usd`** (0,39 e
  0,39), non una misura di qualità d'esecuzione → **[F-015]**. La divergenza prezzo atteso/fill
  **non è misurata da nessuna parte** e non è ricostruibile senza i log ([F-027]).
* **Commissioni/costi**: $0,78 totali, modello `cost_model.yaml` a 1,81 bps per gamba (NVDA e META
  sono entrambi in un tier definito, quindi [F-034] non si applica a queste due righe).

### 8b. Non realizzato e riconciliazione

| Voce | Valore | Fonte |
|---|---:|---|
| NAV a fine giornata | **$110.073,75** | `risk_reports` 22:30:01 |
| Esposizione lorda | **29,34%** | idem |
| Herfindahl | 0,0250 | idem |
| Drawdown (curva equity reale, #107) | **1,24%** | idem |
| Posizioni aperte (`trades.exit_time IS NULL`) | **46** (34 S1, 2 S4, 10 senza sleeve) | `trades` |
| MTM del book aperto **con le quantità a DB** | +$21,66 | `ALPHA_MISS_REPORT_2026-08-26.md` §7 |
| MTM del book aperto **con le quantità reali al broker** | **−$33,51** | idem |
| Contributo delle quantità inesistenti (MRVL, NOK, WDC) | **−$55,17** | idem [F-048] |
| Riconciliazione: −33,51 + 38,87 (NVDA+META da close precedente al fill) | **+$5,36** | idem |
| Variazione equity Alpaca osservata | **+$5,28** (delta $0,08) | idem |

**Il MTM per sleeve non è calcolabile in modo affidabile** finché [F-048] è aperto: le quantità a
DB divergono da quelle al broker su 3 simboli, e su NOK di 74×. Non riporto una tabella MTM per
sleeve: sarebbe un numero sbagliato presentato come misura.

* **10 posizioni su 46 sono senza `stop_strategy`** → nessuna attribuzione di sleeve → [F-002]
  (occorrenza 08-26 già registrata dall'alpha-miss).
* `per_strategy_metrics` = `{}` → **nessun drawdown per sleeve è monitorato** (§10 [DAY-010]).

### 8c. Attribuzione decisionale (dossier `decision_quality.summary`)

| Voce | USD |
|---|---:|
| `passive_pnl_usd` (book fermo) | +6,85 |
| `selection_pnl_usd` (ingressi) | **0,00** (zero ingressi) |
| `exit_effect_usd` (le due uscite) | **+48,87** |
| `active_decision_pnl_usd` | **+48,87** |
| `actual_intraday_pnl_usd` | +55,72 |
| `market_beta_1_usd` | +65,53 |

**Nota di prudenza.** `passive_pnl_usd` è calcolato sulle quantità a DB, quindi eredita l'errore
di [F-048]: la voce "book fermo" contiene MTM fantasma. Solo `exit_effect_usd` (+48,87) è pulito,
perché deriva da due righe con quantità confermate dal fill.

## 9. Analisi correttezza buy/sell

| Controllo | Esito | Nota |
|---|---|---|
| BUY generati solo quando consentito | ✅ **corretto** | 108 target BUY, 108 bloccati da P0-05 su titoli già a libro. Nessun BUY inviato. |
| SELL/exit generati correttamente | ⚠️ **meccanicamente sì, decisionalmente no** | Il ramo `below_entry_gate` ha eseguito la propria regola alla lettera. La regola è quella sbagliata: chiude su score 0,000 (§10 [DAY-003]). |
| Stop-loss rispettati | ✅ **corretto per design** | `stop_loss: 0.0`, protettivo **disattivato per decisione documentata** del 2026-07-15 (`config/trading.yaml:172-182`). `stop_decisions` = 0 righe è quindi il comportamento atteso, non un guasto. `stop_shadow_log` = **1.111 righe** → la telemetria d'ombra gira. |
| Signal flip rispettato | ✅ | Nessun flip: 0 BUY, 2 SELL. |
| Max holding days rispettato | ✅ | Tenuta 19,25 h su entrambe, dentro qualunque orizzonte. |
| Rebalance band rispettata | ⚠️ **non verificabile oggi** | Nessun rebalance è stato inviato; i target si ripetono identici per 24 cicli (CSCO 17,22 → 17,13 azioni), quindi la banda non è stata messa alla prova. |
| Nessun ordine duplicato | ✅ | 2 `order_id` distinti, nessuna coppia nello stesso minuto. |
| Nessun ordine contrario ravvicinato | ⚠️ **uno, con rationale contraddittorio** | META: alle **14:07** il combiner emette un **target BUY** (peso 2,0%) su segnale +0,3855, bloccato da P0-05; alle **15:07** emette **SELL** (peso 0%) su segnale 0,000. Intento invertito sullo stesso simbolo **in 60 minuti**, con l'unica novità informativa un listicle a informazione nulla. |
| Roundtrip < 30 min (buy+sell stesso ciclo) | ✅ **nessuno** | 0 BUY inviati. |
| BUY ripetuto > 3× senza SELL (pyramiding) | ✅ **nessuno** | P0-05 ha bloccato 108/108. Il guard funziona. |
| SELL con sentiment positivo (bug A5) | ⚠️ **caso di confine** | Nessuna SELL con score > 0. META a **esattamente 0,000** e NVDA a −0,0056: non "positivo", ma **indistinguibile da assenza di segnale**. |
| Ordini su ticker non consentiti | ✅ | NVDA e META sono in watchlist. |
| Ordini fuori orario | ✅ | 14:22 e 15:07 UTC, dentro 13:30–20:00. |
| Trade su dati stale | ✅ **corretto** | `SKIP_STALE` su XOM (22,1h) + 505 righe `SIGNAL_STALE_SKIP` in `audit_log`. Le due uscite usano segnali di 0,3h e 0,4h. |
| Trade su output LLM non valido | ✅ **nessuno** | 0 refusal/invalid parse. |
| Trade con circuit breaker attivo | ⚠️ **sì, e senza effetto** | Il breaker di fallback è scattato alle 15:45:07. Non ha bloccato né ridimensionato nulla perché **`qc:sizing_multiplier` non ha consumatori**. Le due uscite precedono comunque lo scatto. |
| Trade con strategia disabilitata | ✅ | S1 e S4 attive in tutti i 24 cicli (`strategies_run = ["S1","S4"]`). |
| Paper/live coerente | ✅ **paper**, per configurazione | Vedi §7b: verificato per config, non per risposta broker. |
| Idempotenza su retry Celery | ✅ **nessuna violazione osservata** | 24 cicli, 24 slot, 0 doppioni. `ON CONFLICT (url,ticker) DO NOTHING` su `news_log`; `news_log_id` popolato su **114/114** segnali. |
| Riconciliazione ordini↔fill↔posizioni | ❌ **rotta** | `exit_order_ids` coerente per le 2 chiusure, ma il book aperto divergeva dal broker su 3 simboli ([F-048]) e 4 fill dentro RTH sono stati censurati come fuori sessione ([F-047]). |

## 10. Anomalie trovate

### [DAY-001] L'ensemble Ollama muore a metà sessione e il circuit breaker che dovrebbe segnalarlo è codice morto verificato — 4h14m di sessione senza valutazione LLM, senza un solo alert

* **Tipo**: Bug
* **Area**: LLM / Ops
* **Ledger**: **F-049 (nuovo)**
* **Evidenza**:
  * tabelle: `llm_responses`, `llm_budget`, `fallback_counters`, `sentiment_signals`; Redis
    `ensemble:divergence:log`, `qc:sizing_multiplier`, `fallback:alert_sent`; codice
    `src/store/redis_store.py:270-330`, `src/notifications/telegram.py:120-135`,
    `src/workers/sentiment.py:678-687`, `config/workers.yaml:42-45`
  * timestamp: ultima risposta **2026-08-26 15:31:00.458558+00**; primo FinBERT
    **15:45:06.324154+00**; scatto breaker **15:45:07.379684+00**; ultimo incremento
    **19:45:07.786854+00**
  * query/snippet:
    ```sql
    SELECT model_id, MAX(generated_at) FROM llm_responses
     WHERE generated_at >= '2026-08-26' AND generated_at < '2026-08-27' GROUP BY 1;
    -- glm-5.2:cloud     | 2026-08-26 15:31:00.458558+00
    -- gpt-oss:20b-cloud | 2026-08-26 15:31:00.458558+00

    SELECT * FROM fallback_counters;
    -- consecutive_fallback | 79 | last_increment 19:45:07.786 | reset_at 15:31:00.449

    SELECT date_trunc('hour',generated_at) h, COUNT(*), SUM((model_id='finbert')::int)
      FROM sentiment_signals WHERE generated_at::date='2026-08-26' GROUP BY 1 ORDER BY 1;
    -- 16:00 | 15 | 15   17:00 | 10 | 10   18:00 | 25 | 25   19:00 | 23 | 23
    ```
    ```
    $ docker exec alembic-redis-1 redis-cli LRANGE ensemble:divergence:log 0 0
    {"symbol":"SYSTEM","std":0.0,"scores":{"fallback_threshold_reached":3},
     "ts":"2026-08-26T15:45:07.379684+00:00","event_type":"fallback_circuit_breaker"}
    $ docker exec alembic-redis-1 redis-cli GET qc:sizing_multiplier   → 0.5
    $ docker exec alembic-redis-1 redis-cli GET fallback:alert_sent    → 1
    $ grep -rn "on_fallback_alert" src/ --include=*.py | grep -v test
    src/store/redis_store.py:61,67,74,322,324      # SOLO definizione e invocazione
    $ grep -rn "RedisStore(" src/ --include=*.py | grep -v "def "
    # 16 chiamanti, NESSUNO passa on_fallback_alert=
    $ grep -rn "send_fallback_alert" src/ --include=*.py | grep -v telegram.py
    # nessun risultato
    $ grep -rn "get_qc_sizing_multiplier" src/ --include=*.py | grep -v test
    src/store/redis_store.py:29,336                # SOLO docstring e definizione
    ```
* **Descrizione**: dopo le 15:31 i due modelli Ollama Cloud non hanno più risposto per il resto
  della sessione. **Non è esaurimento budget**: `llm_budget` del giorno segna $0,0377 spesi
  (contro ~$0,20 nelle sedute normali) e `budget_exhausted=false`. I 79 scoring successivi sono
  caduti tutti su FinBERT (81,6% di fallback sul giorno contro **0,0% il 2026-08-25** e 28–40% in
  media). Il circuit breaker si è armato al terzo fallback consecutivo, alle 15:45:07, e ha
  eseguito tre azioni **tutte inerti**: (a) ha scritto `qc:sizing_multiplier=0.5`, chiave che
  **nessun consumatore legge** — `get_qc_sizing_multiplier` ha come sole occorrenze la propria
  docstring e la propria definizione; (b) ha invocato `self._on_fallback_alert`, che è **sempre
  `None`** perché nessuno dei 16 chiamanti di `RedisStore(...)` passa quel kwarg, e
  `send_fallback_alert` non ha alcun chiamante fuori dal proprio modulo; (c) ha spinto **una** riga
  in una lista Redis con TTL 24h. Inoltre il trigger è `if new_value == self._max_fallbacks`
  (uguaglianza esatta con 3): se il contatore salta il valore 3 — riavvio del worker, OOM Redis
  che fa ritornare 0 da `increment_fallback_counter`, batch concorrente — non scatta mai più,
  perché a 79 la condizione è falsa. Il danno collaterale è più ampio del punteggio: FinBERT non
  produce `directness`/`event_type`, quindi le 79 righe finiscono `relevance=UNKNOWN`
  (80/114 = 70% del giorno) e **anche il classificatore di rilevanza si è spento**.
* **Impatto**: 4h14m su 6h30m di sessione (65%) senza valutazione d'ensemble. Nel pomeriggio
  **nessun ingresso era strutturalmente possibile**: ogni segnale era `fallback_used=true` e la
  regola #108 lo esclude dal ranking BUY. Sei degli otto segnali sopra gate della giornata
  provengono da questa finestra, incluso il più forte in assoluto (NVO −0,5533) e l'unico
  rialzista sopra gate del pomeriggio (MS +0,3421). Per il periodo di osservazione il costo vero
  è di misura: una seduta su 40 in cui la domanda "la news ha alpha?" **non è stata posta al
  sistema** per due terzi del tempo, senza che il ledger lo sapesse. E la finestra si chiude senza
  che nessun operatore sia stato avvisato.
* **Severità**: **Critical**
* **Confidenza**: **High** (timestamp da tre tabelle indipendenti + assenza di chiamanti provata
  per grep)
* **Azione consigliata**: ticket di correttezza (esente dal freeze — la carta di osservazione
  esenta i difetti che rendono sbagliata l'evidenza raccolta, e qui l'evidenza di un'intera
  seduta è compromessa senza segnale): (1) cablare `send_fallback_alert` a un chiamante reale,
  oppure sostituire la callback con una scrittura su `audit_log` che il forense può leggere anche
  dopo un redeploy; (2) cambiare `== self._max_fallbacks` in `>= self._max_fallbacks` con
  deduplica su `fallback:alert_sent`; (3) rendere osservabile il **motivo** del fallimento —
  persistere status/eccezione della chiamata Ollama in una tabella, non solo nei log volatili;
  (4) decidere se `qc:sizing_multiplier` va cablato o rimosso: oggi è una promessa non mantenuta
  in un percorso di rischio.
* **Test/monitor consigliato**: test che costruisca `RedisStore` come lo costruisce la produzione
  e verifichi che 3 fallback consecutivi producano un record osservabile e persistente; monitor
  giornaliero che allerti se `COUNT(*) FILTER (WHERE model_id LIKE 'ensemble:%')` scende sotto il
  50% dei segnali del giorno, o se `MAX(llm_responses.generated_at)` è più di 45 minuti prima
  della chiusura RTH.

### [DAY-002] La posizione NVDA è chiusa da un articolo su Goldman Sachs e l'AI, mentre il pezzo su NVDA pubblicato tre minuti prima diceva l'opposto

* **Tipo**: Bug
* **Area**: Signal / Orders
* **Ledger**: **F-008**, occorrenza 2026-08-26 (ottava)
* **Evidenza**:
  * tabelle: `sentiment_signals` 8954/8960/8967/8973, `news_log`, `execution_decisions`,
    `trades` 829
  * timestamp: 14:00:41 (+0,078) → 14:03:46 (−0,0056) → 14:16:12 (+0,22) → **SELL 14:22:00**
  * query/snippet:
    ```
    8954 14:00:41 NVDA ensemble  +0.0780 conf 0.40  "Nvidia Earnings Prediction Market Preview:
                                                     What Will Jensen Huang Say?"
                                                     ("Traders give Nvidia a 98% chance of beating earnings")
    8960 14:03:46 NVDA ensemble  -0.0056 conf 0.175 "Goldman Sachs Executive Sounds The Alarm,
                                                     Warns AI Could Cause 'Cognitive Atrophy' on Wall Street"
    8967 14:16:12 NVDA single    +0.2200 conf 0.55  "…Nvidia Wins No Matter Who Leads AI Race"  [ineleggibile]
    → reason: [below_entry_gate] ... generated 2026-08-26 14:03 UTC, score=-0.006 → position closed
    ```
* **Descrizione**: l'articolo che ha chiuso la posizione parla di un dirigente di Goldman Sachs che
  avverte del rischio di "atrofia cognitiva" da uso eccessivo dell'AI nella finanza. Non contiene
  informazione su NVDA: è un pezzo macro sul settore finanziario, mappato su NVDA dal fan-out. Tre
  minuti prima, l'articolo genuinamente specifico ("98% di probabilità di battere le stime") aveva
  prodotto **+0,078**. S4 usa solo il segnale più recente **eleggibile** per simbolo ([F-023]),
  quindi ha preso il macro invece dello specifico. Sei minuti dopo, un terzo pezzo su NVDA valeva
  **+0,22**, ma era `single:gpt-oss` e quindi ineleggibile ([F-010]).
* **Impatto**: una posizione da $1.903 di nozionale è stata liquidata su un articolo che non la
  riguarda. **Ex post l'uscita ha evitato $9,21 di ulteriore perdita** (drift post-uscita −$9,21
  nel dossier), quindi la giornata non registra un dollaro di danno — ma la regola che ha deciso è
  sbagliata e il segno del risultato è casuale.
* **Severità**: **High**
* **Confidenza**: **High**
* **Azione consigliata**: **nessuna taratura** (freeze). Ticket di correttezza sul fan-out:
  un articolo il cui soggetto non è il ticker non deve poter agire come contro-segnale su quel
  ticker. Il rail esiste già (`relevance` da `directness`), va cablato al ramo d'uscita —
  compatibilmente con QX-01 (misurare prima di applicare).
* **Test/monitor consigliato**: monitor che elenchi ogni giorno le uscite in cui il segnale
  causante ha `directness != 'direct'` o `relevance = 'UNKNOWN'`, con il P&L a fianco. Sarebbe la
  serie che serve a decidere se cablare il gate.

### [DAY-003] Un listicle "quanto valevano $1000 dieci anni fa" liquida una posizione: score 0,000 è trattato come contro-segnale perché fra gate d'ingresso e uscita non c'è banda

* **Tipo**: Bug
* **Area**: Signal / Orders
* **Ledger**: **F-013**, occorrenza 2026-08-26 (dodicesima)
* **Evidenza**:
  * tabelle: `sentiment_signals` 8975, `news_log`, `execution_decisions`, `trades` 831,
    `portfolio_cycles` 14:07 vs 15:07
  * timestamp: 14:07:04 target BUY META (+0,3855) bloccato → 14:45:12 segnale 0,000 →
    **SELL 15:07:00**
  * query/snippet:
    ```
    8975 14:45:12 META ensemble score 0.0000 conf 0.20 fallback=false
         title "Here's How Much $1000 Invested In Meta Platforms 10 Years Ago Would Be Worth Today"
         body  "Meta Platforms (NASDAQ:META) has outperformed the market over the past 10 years
                by 2.97% on an annualized basis…"
    reason: [below_entry_gate] S4 signal fell below the active feedback entry threshold
            (age=0.4h vs max_age=4h, generated 2026-08-26 14:45 UTC, score=+0.000):
            weight 0.0%, position closed.
    -- 60 minuti prima, stesso simbolo:
    14:07:04 META SKIP_PYRAMIDING  signal_score +0.3855  "peso non allocato 2.0%"
    ```
* **Descrizione**: l'articolo è un pezzo di riempimento sul rendimento decennale del titolo, senza
  alcuna notizia. L'ensemble lo ha valutato correttamente: polarity 0, confidence 0,20 → score
  **esattamente 0,000**. Il sistema non distingue "nessuna informazione" da "informazione
  negativa": la regola `below_entry_gate` chiude qualunque posizione il cui segnale più recente
  stia sotto **0,30**, e 0,000 ci sta sotto. Non esiste una banda morta fra la soglia che apre
  (0,30) e quella che chiude. Il risultato è un intento invertito sullo stesso simbolo in
  60 minuti: alle 14:07 il combiner voleva **comprare** META al 2% del NAV su un segnale +0,3855,
  alle 15:07 l'ha **venduta** su un non-articolo. La confidence 0,20 — cioè il modello che dice
  "non ne so nulla" — non attenua nulla a valle.
* **Impatto**: la posizione ha realizzato **+$61,68** e l'uscita ha evitato $39,65 di drift
  successivo: **ex post è stata la decisione migliore della giornata**. Ma è stata presa per il
  motivo sbagliato, e la stessa regola sullo stesso input avrebbe potuto tagliare un vincente.
  Fatto strutturale: le **due sole** decisioni della giornata sono entrambe di questo tipo.
* **Severità**: **High**
* **Confidenza**: **High**
* **Azione consigliata**: **nessuna taratura durante il freeze** — la banda è un parametro e la
  sua ampiezza va al 28/09. È però registrabile ora la distinzione **strutturale** fra "segnale
  assente/non informativo" (`|score|` sotto una soglia di informatività **con confidence bassa**)
  e "contro-segnale", perché è una questione di correttezza del modello di dominio, non di
  taratura. Da portare come decisione su #182/#338, non come patch.
* **Test/monitor consigliato**: monitor giornaliero delle uscite con `|signal_score| < 0.05` e
  `confidence < 0.30`, con P&L realizzato e drift post-uscita a fianco. Serve a quantificare
  quanto vale la banda prima di scegliere l'ampiezza.

### [DAY-004] 28 contributori reali dell'ensemble su 42 sono marcati `eligible=false`, e il ramo single-model scarta il segnale NVDA più informativo della finestra

* **Tipo**: Bug
* **Area**: LLM / Data
* **Ledger**: **F-010**, occorrenza 2026-08-26 (undicesima)
* **Evidenza**:
  * tabelle: `llm_responses`, `sentiment_signals`
  * timestamp: giornata intera; caso puntuale 14:16:12 (NVDA 8967)
  * query/snippet:
    ```sql
    SELECT model_id, COUNT(*), SUM(eligible::int) FROM llm_responses
     WHERE generated_at::date='2026-08-26' GROUP BY 1;
    -- glm-5.2:cloud     | 35 | 7
    -- gpt-oss:20b-cloud | 35 | 7
    SELECT model_id, COUNT(*) FROM sentiment_signals
     WHERE generated_at::date='2026-08-26' AND model_id LIKE 'ensemble%' GROUP BY 1;
    -- ensemble:glm-5.2:cloud+gpt-oss:20b-cloud | 21     → 42 risposte contributrici
    ```
* **Descrizione**: 21 segnali ensemble implicano 42 risposte che hanno effettivamente formato il
  punteggio, ma `eligible=true` compare su 14 righe totali (7+7). **28 contributori reali sono
  etichettati come non contributori**, quindi qualunque analisi LOO-ICIR o audit di attribuzione
  costruita su `eligible` misura un insieme diverso da quello che ha deciso. Sul lato decisionale:
  il segnale NVDA 8967 (+0,22, `single:gpt-oss`, 14:16) è stato scartato come fallback, e la
  posizione è stata chiusa 6 minuti dopo sul segnale precedente (−0,0056). *Onestà
  controfattuale: 0,22 è comunque sotto il gate 0,30, quindi `below_entry_gate` avrebbe chiuso
  anche con 8967 eleggibile — il difetto cambia il **motivo** registrato, non l'esito di questa
  uscita.*
* **Impatto**: la contabilità dei contributori è sbagliata di due terzi. Il ribilanciamento dei
  pesi d'ensemble (`ensemble:weights:current`) e ogni ricostruzione a posteriori di "chi ha deciso"
  poggiano su una colonna che, in questa giornata, sbaglia su 28 righe su 42.
* **Severità**: **Medium**
* **Confidenza**: **High**
* **Azione consigliata**: propagare il floor del retry (#90) fino alla scrittura di `eligible`,
  così che la colonna descriva i contributori reali. Difetto di correttezza dell'evidenza:
  esente dal freeze.
* **Test/monitor consigliato**: invariante di test — per ogni `signal_id` con
  `model_id LIKE 'ensemble:%'`, il numero di `llm_responses` con `eligible=true` deve uguagliare
  il numero di modelli nominati in `model_id`. Da eseguire come check notturno sul giorno appena
  chiuso.

### [DAY-005] Il ciclo portfolio parte alle 14:07 e la sessione apre alle 13:30: 37 minuti di sessione senza alcun ciclo, e 8 slot dopo la chiusura

* **Tipo**: Bug
* **Area**: Ops / Orders
* **Ledger**: **F-021**, occorrenza 2026-08-26 (dodicesima)
* **Evidenza**:
  * file: `src/workers/celery_app.py:210` →
    `crontab(minute="7,22,37,52", hour="14-21", day_of_week="1-5")`; idem righe 78, 151, 162, 184,
    228 per ingest e altri task
  * tabelle: `portfolio_cycles` (24 righe, 14:07:00.656 → 19:52:00.674); dossier
    `sessioni.regular.first_bar_at = 2026-08-26T13:30:00+00`
  * query/snippet:
    ```sql
    SELECT MIN(timestamp), MAX(timestamp), COUNT(*) FROM portfolio_cycles
     WHERE timestamp::date='2026-08-26';
    -- 14:07:00.656458+00 | 19:52:00.674211+00 | 24
    ```
* **Descrizione**: la finestra del beat è espressa a ora UTC fissa `14-21`, mentre in EDT la
  sessione regolare è 13:30–20:00 UTC. I primi **37 minuti** di ogni seduta non hanno né ciclo
  portfolio né ingest news; gli 8 slot fra 20:07 e 21:52 sono previsti a mercato chiuso (in
  `portfolio_cycles` non compaiono, coerentemente con un guard a valle, quindi lo spreco è di
  scheduling e non di ordini). Effetto misurabile oggi: nessun articolo pubblicato fra 12:31 e
  13:30 UTC è stato valutato prima delle 14:00:30.
* **Impatto**: il 9,5% di ogni sessione è fuori copertura, e sistematicamente la parte con la
  maggiore dispersione di prezzo. Non è quantificabile in dollari oggi (nessun segnale
  identificato in quella finestra), ma distorce ogni statistica per ora d'ingresso del dossier —
  `aggregati.per_ora_ingresso` non ha e non può avere una riga per l'ora 13.
* **Severità**: **Medium**
* **Confidenza**: **High**
* **Azione consigliata**: derivare la finestra dal calendario di mercato Alpaca invece che da
  un'ora UTC costante. È lo stesso vizio di [F-047] visto da un altro punto: entrambi trattano il
  calendario come se fosse UTC. Correttezza, non taratura.
* **Test/monitor consigliato**: test che, dato un giorno EDT e un giorno EST, verifichi che il
  primo slot pianificato non sia successivo all'apertura RTH; monitor che confronti
  `MIN(portfolio_cycles.timestamp)` con l'apertura RTH del calendario.

### [DAY-006] La suite di test ha scritto tre volte nel database di produzione, e le righe `trades` che ha creato sono state cancellate senza traccia

* **Tipo**: Bug
* **Area**: Data / Ops
* **Ledger**: **F-039**, occorrenza 2026-08-26 (terza). *Nota: la firma di [F-028] (righe
  `ingestion_stats_daily` con `source='reuters'`) è **lo stesso evento**, prodotta dai medesimi
  tre run; non la ri-appendo per non contare due volte la stessa occorrenza.*
* **Evidenza**:
  * tabelle: `audit_log` 14912-14923, `trades`, `ingestion_stats_daily`, `news_queue_drops`
  * timestamp: **07:13:54**, **08:14:55**, **08:36:30** (INSERT `trades`); **07:14:58**,
    **08:15:59**, **08:37:34** (drop `reuters` + `ingestion_stats_daily`)
  * query/snippet:
    ```sql
    SELECT action, table_name, COUNT(*) FROM audit_log
     WHERE created_at::date='2026-08-26' GROUP BY 1,2;
    -- SIGNAL_STALE_SKIP | sentiment_signals | 505
    -- INSERT            | trades            |  12      ← TEST_STOP_1/2/3/FIXED_AUD × 3 run
    SELECT id,symbol FROM trades WHERE symbol LIKE 'TEST%';   -- 0 righe
    SELECT MAX(id) FROM trades;                               -- 831  (832-846 consumati)
    SELECT dropped_at, title, url FROM news_queue_drops
     WHERE source='reuters' AND dropped_at::date='2026-08-26';
    -- 08:37:34 | Federal Reserve holds rates steady | https://reuters.com/article/foo
    -- 08:15:59 | (idem)                             | (idem)
    -- 07:14:58 | (idem)                             | (idem)
    SELECT day,source,fetched,queued,updated_at FROM ingestion_stats_daily
     WHERE day='2026-08-26' AND source='reuters';
    -- 2026-08-26 | reuters | 12 | 12 | 2026-08-26 08:37:34.524613+00
    ```
* **Descrizione**: tre esecuzioni della suite di test contro il database **di produzione**, tutte
  pre-market. Ogni run inserisce 4 righe `trades` con simboli `TEST_STOP_*` e nozionale $1.000,
  scrive una riga `ingestion_stats_daily` per una fonte (`reuters`) che nel 2026-08-26 non ha
  prodotto **nemmeno un articolo reale** (0 righe in `news_log`), e una riga `news_queue_drops`
  con la fixture `url='https://reuters.com/article/foo'`,
  `title='Federal Reserve holds rates steady'`. Le 12 righe `trades` sono poi **spariste**:
  `MAX(trades.id)=831` mentre gli id 832-846 sono stati consumati, e in `audit_log` esistono
  **gli INSERT ma nessun DELETE**. La correlazione temporale è stretta (07:13:54 ↔ 07:14:58;
  08:36:30 ↔ 08:37:34): un'unica suite, tre lanci.
* **Impatto**: la tabella più sensibile del sistema accetta scritture di test e cancellazioni non
  auditate. Oggi il danno diretto è nullo (le righe non hanno prodotto ordini e non sono più a
  DB), ma `ingestion_stats_daily` **contiene ancora oggi** una fonte fantasma per il 2026-08-26 e
  per il 2026-08-25, 08-22, 08-19, 08-15, 08-27: qualunque conteggio di copertura per fonte su
  quella tabella è contaminato. E un audit trail che registra l'inserimento ma non la
  cancellazione non è un audit trail.
* **Severità**: **High**
* **Confidenza**: **High**
* **Azione consigliata**: la suite deve puntare a un database dedicato — variabile d'ambiente di
  test obbligatoria, con fallimento esplicito se il DSN è quello di produzione. In parallelo,
  registrare i DELETE su `trades` in `audit_log`. Correttezza: finché la produzione accetta
  scritture di test, ogni conteggio del ledger è confutabile.
* **Test/monitor consigliato**: check notturno che allerti su qualunque riga con simbolo
  `LIKE 'TEST%'`, `url LIKE '%article/foo%'`, o su una `source` in `ingestion_stats_daily` che non
  abbia righe corrispondenti in `news_log` nello stesso giorno; conftest che rifiuti di partire se
  il DSN coincide con quello live.

### [DAY-007] `portfolio_cycles.orders_count` dice 110 ordini, ne sono stati inviati 2

* **Tipo**: Anomalia
* **Area**: Ops
* **Ledger**: **F-014**, occorrenza 2026-08-26 (quattordicesima)
* **Evidenza**:
  * tabelle: `portfolio_cycles`, `execution_decisions`, `s4_intent_events`, `trades`
  * timestamp: 24 cicli 14:07 → 19:52
  * query/snippet:
    ```sql
    SELECT SUM(orders_count) FROM portfolio_cycles WHERE timestamp::date='2026-08-26';  -- 110
    -- parsing di final_orders: 108 BUY + 2 SELL
    -- BUY per simbolo: CSCO 24, DELL 24, SOXX 24, LLY 17, MU 16, META 3, (NVDA/META SELL 2)
    SELECT symbol,COUNT(*) FROM s4_intent_events WHERE occurred_at::date='2026-08-26'
      AND event_type='disposition' AND reason_code='SKIP_PYRAMIDING' GROUP BY 1;
    -- CSCO 24, DELL 24, SOXX 24, LLY 17, MU 16, META 3      → 108, corrispondenza esatta
    SELECT COUNT(*) FROM trades WHERE entry_time::date='2026-08-26';                    -- 0
    ```
* **Descrizione**: `orders_count` conta i **target** del combiner, non le submission. I 108 BUY
  corrispondono uno a uno alle 108 disposizioni `SKIP_PYRAMIDING`: erano tutti su titoli già a
  libro e nessuno è mai stato inviato. In `execution_decisions` di quelle 108 ne compaiono **4**.
  Chi legge la telemetria del ciclo vede 110 ordini in una giornata da 2 ordini.
* **Impatto**: la metrica operativa più immediata ("quanti ordini oggi?") sbaglia di 55×. Non
  costa dollari; costa la capacità di accorgersi di una giornata a zero ingressi — che è
  esattamente la giornata di oggi.
* **Severità**: **Medium**
* **Confidenza**: **High**
* **Azione consigliata**: separare `targets_count` da `submitted_count` in `portfolio_cycles`, e
  persistere in `execution_decisions` **tutte** le disposizioni, non un campione. Il ledger
  `s4_intent_events` (108/108) mostra che il dato esiste già: va solo esposto dove viene letto.
* **Test/monitor consigliato**: invariante notturna
  `SUM(portfolio_cycles.submitted_count) == COUNT(*) FROM trades WHERE entry_time::date = d` +
  chiusure del giorno.

### [DAY-008] Quattro fill dentro la sessione regolare marcati `FILL_OUTSIDE_RTH`: il calendario Alpaca è letto come UTC

* **Tipo**: Bug
* **Area**: Data / Broker
* **Ledger**: **F-047**, occorrenza 2026-08-26 (seconda)
* **Evidenza**:
  * tabelle: `s4_lifecycle_events`, `s4_exit_policy_events`
  * timestamp: eventi osservati 14:12:00.022 (×3) e 15:12:00.516 (×1); fill censurati
    2026-08-25 **19:07:05** (NVDA, CSCO) e **19:52:04** (META)
  * query/snippet:
    ```sql
    SELECT event_type,status,reason_code,COUNT(*) FROM s4_lifecycle_events
     WHERE observed_at::date='2026-08-26' GROUP BY 1,2,3;
    -- ENTRY_RECONCILIATION | CENSORED | FILL_OUTSIDE_RTH | 4
    SELECT policy_id,event_type,status,reason_code,COUNT(*) FROM s4_exit_policy_events
     WHERE observed_at::date='2026-08-26' GROUP BY 1,2,3,4;
    -- P0 | P0_RUNTIME_REPLAY | CLOSED   | P0_TARGET_ZERO_BELOW_ENTRY_GATE | 4
    -- P0 | P0_OPEN_SNAPSHOT  | CENSORED | P0_ENTRY_NOT_RECONSTRUCTIBLE    | 2
    ```
* **Descrizione**: 19:07 e 19:52 UTC sono 15:07 e 15:52 ET, cioè **dentro** RTH (13:30–20:00 UTC).
  La censura conferma il meccanismo già documentato su F-047: `Calendar.open/close` di
  `alpaca-py` è naive in ora di New York, e `lifecycle.py::_utc()` fa
  `value.replace(tzinfo=timezone.utc)` senza convertire, spostando la finestra a 09:30–16:00 UTC.
  Due righe `P0_OPEN_SNAPSHOT / P0_ENTRY_NOT_RECONSTRUCTIBLE` sono la conseguenza a valle. **La
  correzione (`c9f77d2`, PR #373) è stata mergiata il 2026-08-27 alle 10:18 UTC, quindi la seduta
  del 2026-08-26 è interamente pre-fix** e questa occorrenza è la seconda e ultima attesa.
* **Impatto**: nessuna perdita. Azzera uno strumento di misura: la riconciliazione shadow #295 non
  produce osservazioni utilizzabili per il secondo giorno consecutivo, e l'orologio D+2 di #334
  non si arma.
* **Severità**: **Medium**
* **Confidenza**: **High**
* **Azione consigliata**: **nessuna** — già corretta in `c9f77d2`. Da verificare sulla seduta del
  2026-08-27: se `FILL_OUTSIDE_RTH` = 0 su fill pomeridiani, F-047 si chiude.
* **Test/monitor consigliato**: monitor che allerti su qualunque `FILL_OUTSIDE_RTH` il cui
  `filled_at` cada fra l'apertura e la chiusura RTH del calendario del giorno.

### [DAY-009] La catena segnale→decisione→trade non è ricostruibile per chiave: 333 righe su 336 hanno `signal_id` NULL, incluse entrambe le uscite

* **Tipo**: Bug
* **Area**: Data
* **Ledger**: **F-011**, occorrenza 2026-08-26 (quindicesima)
* **Evidenza**:
  * tabelle: `execution_decisions`
  * timestamp: giornata intera
  * query/snippet:
    ```sql
    SELECT decision, COUNT(*) tot, COUNT(signal_id) with_sig FROM execution_decisions
     WHERE tick_time::date='2026-08-26' GROUP BY 1;
    -- SKIP_THRESHOLD  | 312 | 0
    -- SKIP_FALLBACK   |  17 | 0
    -- SKIP_PYRAMIDING |   4 | 3
    -- SELL            |   2 | 0     ← le due sole operazioni della giornata
    -- SKIP_STALE      |   1 | 0
    ```
* **Descrizione**: `signal_id` è popolato su 3 righe su 336. Le due SELL che hanno mosso $3.805 di
  nozionale sono collegate al proprio segnale **solo dal testo libero** di `reason` ("generated
  2026-08-26 14:03 UTC, score=-0.006"). Ho ricostruito 8960 e 8975 leggendo quella stringa e
  cercando per `(symbol, generated_at)`: funziona, ma non è una chiave.
* **Impatto**: nessun costo diretto. Rende ogni ricostruzione forense dipendente dal parsing di
  testo libero, quindi fragile a qualunque cambio di formato del messaggio. In una giornata con 2
  operazioni è gestibile; su 40 sedute è il vincolo che limita l'automatizzabilità del ledger.
* **Severità**: **Medium**
* **Confidenza**: **High**
* **Azione consigliata**: popolare `signal_id` su tutti i rami che hanno un segnale in mano —
  `below_entry_gate` ce l'ha, dato che ne stampa timestamp e score nel `reason`. Correttezza
  dell'evidenza: esente dal freeze.
* **Test/monitor consigliato**: check notturno
  `SELECT COUNT(*) FROM execution_decisions WHERE signal_id IS NULL AND decision IN ('BUY','SELL') AND tick_time::date = d`,
  atteso 0.

### [DAY-010] Dopo la correzione del drawdown fittizio, nessun drawdown per sleeve è più monitorato: `per_strategy_metrics` è `{}` e `alerts` è vuoto

* **Tipo**: Rischio
* **Area**: Risk
* **Ledger**: **F-050 (nuovo)**
* **Evidenza**:
  * tabelle: `risk_reports`; codice `src/workers/risk_monitor_task.py:190-244`,
    `src/portfolio/risk_monitor.py:176-190`
  * timestamp: cambio di stato fra il report del **2026-08-24 22:30:01** e quello del
    **2026-08-25 22:30:01**
  * query/snippet:
    ```sql
    SELECT timestamp::date, alerts::text, per_strategy_metrics::text FROM risk_reports
     WHERE timestamp >= '2026-08-23' ORDER BY timestamp;
    -- 08-23 | [{"level":"ALERT","message":"Strategy portfolio drawdown 17.8% exceeds 10%",…}] | {"portfolio":{…}}
    -- 08-24 | [{"level":"ALERT","message":"Strategy portfolio drawdown 17.9% exceeds 10%",…}] | {"portfolio":{…}}
    -- 08-25 | []                                                                             | {}
    -- 08-26 | []                                                                             | {}
    ```
    ```python
    # src/workers/risk_monitor_task.py:236-238  (commit 8c61a44, fix #349)
    report = monitor.compute_report(
        strategy_returns={},      # ← nessuna serie per sleeve entra nel monitor
        current_weights={},
    ```
* **Descrizione**: `8c61a44` (fix #349) ha correttamente eliminato l'entry sintetica `portfolio`
  che generava ogni notte un ALERT di drawdown al 17,8% mentre il drawdown reale era 1,2%
  ([F-003], **risolto**). La correzione passa `strategy_returns={}`, quindi il ciclo che costruisce
  `per_strategy_metrics` non itera su nulla e `_check_alerts` riceve un dizionario vuoto.
  Risultato: da due sedute **nessuna metrica per sleeve viene calcolata e nessun alert per sleeve
  può scattare**. Il drawdown di libro (`combined_drawdown`, 1,24% oggi) resta corretto e ancorato
  alla curva equity reale; è la copertura **per S1 e per S4 separatamente** che è a zero. Il
  commento nel codice dichiara la scelta ("no synthetic per-strategy entry is registered"), quindi
  non è un incidente — è una lacuna assunta.
* **Impatto**: nessuna perdita oggi (drawdown di libro 1,24%, ampiamente sotto soglia). Ma S1 e S4
  hanno profili di rischio molto diversi (§8: S1 −$448,78 di realizzato all'ora 14 contro S4
  −$189,95, in `aggregati.per_ora_ingresso`), e nessun meccanismo si accorgerebbe se una delle due
  entrasse in drawdown profondo mentre l'altra la compensa. Su un libro paper è tollerabile; è la
  precondizione da chiudere prima del live.
* **Severità**: **Medium**
* **Confidenza**: **High**
* **Azione consigliata**: **non** ripristinare la vecchia serie (era sbagliata: `daily_return` di
  `portfolio_daily_state` è `SUM(net_pnl)/SUM(entry_notional)` sui soli trade chiusi, non un
  rendimento su NAV). Serve una curva equity **per sleeve** costruita come quella di libro (#107),
  e solo allora ricablare `strategy_returns`. Non è una taratura — è ricostruire una misura che
  oggi non esiste — ma **non passa il test di esenzione** della carta di osservazione: la sua
  assenza non rende sbagliata l'evidenza raccolta. Quindi: ticket aperto, **lavoro dopo il 28/09**.
* **Test/monitor consigliato**: nel frattempo, monitor giornaliero che calcoli il drawdown per
  sleeve fuori dal path di alert (read-only, sul modello di `stop_shadow_log`) e lo scriva nel
  dossier, così che la serie esista quando il gate verrà ricablato.

### [DAY-011] `duplicates` (2.366) supera `fetched` (585) nello stesso giorno per `alpaca_benzinga`

* **Tipo**: Anomalia
* **Area**: News / Data
* **Ledger**: **F-007**, occorrenza 2026-08-26 (tredicesima)
* **Evidenza**:
  * tabelle: `ingestion_stats_daily`, `news_queue_drops`
  * timestamp: `updated_at 2026-08-26 19:45:04.152415+00`
  * query/snippet:
    ```
    2026-08-26 | alpaca_benzinga | fetched 585 | queued 287 | duplicates 2366 | stale 71
    -- news_queue_drops conferma: alpaca_benzinga | duplicate_id | ingestion | 2366
    ```
* **Descrizione**: il contatore dei duplicati è **4 volte** il contatore dei fetch. Il valore è
  additivo cross-run (24 cicli di ingest rivedono la stessa finestra di articoli e ricontano gli
  scarti), mentre `fetched` sembra riferirsi a un insieme diverso. Le due colonne non sono
  confrontabili e nulla nello schema lo dichiara. La riga di `news_queue_drops` conferma il
  numero, quindi non è un errore di scrittura: è una semantica non documentata.
* **Impatto**: nessun costo. Qualunque "tasso di duplicazione" calcolato come
  `duplicates/fetched` dà 404% ed è privo di significato; il dato di copertura per fonte non è
  utilizzabile senza sapere quale dei due contatori è per-run e quale per-giorno.
* **Severità**: **Low**
* **Confidenza**: **High** (osservato; la semantica non è stata verificata nel codice di ingest in
  questa sessione — l'attribuzione "additivo cross-run" resta un'ipotesi coerente coi numeri)
* **Azione consigliata**: definire nello schema se ogni contatore è per-run o per-giorno e
  renderli omogenei. Documentazione + coerenza, non taratura.
* **Test/monitor consigliato**: invariante `duplicates <= fetched` sullo stesso `(day, source)`,
  oppure rinominare le colonne perché il confronto non venga tentato.

### [DAY-012] I log del 2026-08-26 non esistono più: la causa radice dell'outage LLM è definitivamente non diagnosticabile

* **Tipo**: Bug
* **Area**: Ops
* **Ledger**: **F-027**, occorrenza 2026-08-26 (dodicesima)
* **Evidenza**:
  * comandi:
    ```
    $ docker inspect -f '{{.State.StartedAt}}' alembic-worker-1
    2026-08-27T10:13:59.739117438Z          # RestartCount=0
    $ docker compose logs worker --no-color | grep -oE '\[2026-[0-9-]+ [0-9:]+' | head -1
    [2026-08-27 10:14:04
    $ docker compose logs worker-inference --no-color | grep -c "2026-08-26"
    0
    ```
  * timestamp: redeploy 2026-08-27 10:13:59 UTC (merge di `c9f77d2`, `c885643`, `2be7b32`)
* **Descrizione**: i container sono stati ricreati per il deploy del mattino e i log della seduta
  analizzata sono andati con loro. `RestartCount=0` su tutti e quattro, quindi **nessun riavvio
  durante il 2026-08-26** — l'unico dato sullo stato dei worker che sopravvive.
* **Impatto**: oggi non è generico. [DAY-001] è l'anomalia più grave della giornata e i contatori a
  DB permettono di **datarla al secondo** ma non di dire **perché**: nessuno status HTTP, nessuna
  eccezione, nessun timeout registrato. Il costo di F-027 si materializza esattamente quando
  serve.
* **Severità**: **Medium**
* **Confidenza**: **High**
* **Azione consigliata**: driver di logging persistente o export su volume prima del redeploy.
  Alternativa più economica e allineata a [DAY-001]: persistere gli eventi che contano
  (fallimento provider, scatto del breaker) in `audit_log`, che sopravvive.
* **Test/monitor consigliato**: hook di deploy che archivi `docker compose logs --since 48h` su
  disco prima di `up -d`.

## 11. False positive e aree risultate corrette

| Area | Verifica | Esito |
|---|---|---|
| **[F-003] drawdown fittizio `portfolio`** | `risk_reports` 08-25 e 08-26: `alerts=[]`, nessun "Strategy portfolio drawdown 17.9%" | ✅ **RISOLTO** da `8c61a44` (#349). L'ALERT notturno spurio è cessato. Residuo separato in [DAY-010]. **Nessuna occorrenza di F-003 contata oggi.** |
| **Stop-loss assenti** | `stop_decisions` = 0 righe (ultime: 2026-07-14) | ✅ **corretto per design**: `stop_loss: 0.0` per decisione documentata del 2026-07-15 (`config/trading.yaml:172-182`). Non è un guasto. `stop_shadow_log` = 1.111 righe: la telemetria d'ombra gira. |
| **Cadenza dei cicli** | 24 cicli, delta costante 15 min, 14:07 → 19:52 | ✅ nessun gap, nessun ciclo mancato, nessun doppione |
| **Contabilità dell'ingest** | 2.360 fetched → 4.321 drop tracciati con `discarded_reason` + `discard_stage` → 301 queued → 114 `news_log` | ✅ **nessun fallimento silenzioso**. Ogni scarto ha una causa persistita. |
| **Timestamp delle news** | 0 righe `published_at > fetched_at`; 0 `published_at > now()` | ✅ nessun dato dal futuro |
| **Deduplica per sindacazione** | 114 righe / 63 `content_hash` / 63 URL; `duplicati_syndication_per_ticker: 0` | ✅ la dedup su hash funziona |
| **`news_log_id` sui segnali** | 114/114 popolati | ✅ ogni segnale è riconducibile al proprio articolo |
| **Guard anti-pyramiding** | 108 target BUY su titoli già a libro, 108 bloccati | ✅ il guard ha fatto il suo lavoro senza falle |
| **[F-019] latenza di ingestione** | mediana publish→fetch **46,0 min** contro la mediana storica ~1h50m | ✅ **nessuna occorrenza oggi**. Migliore della serie. |
| **[F-037] varianza d'ensemble** | `ensemble_std` max 0,247, medio 0,056 | ✅ **nessuna occorrenza oggi**: nessuna decisione della giornata è stata influenzata da varianza alta. Il difetto resta aperto in astratto. |
| **[F-032] canonicalizzazione ticker** | nessun `BRKB`/simbolo fuori watchlist nelle 114 righe | ✅ nessuna occorrenza oggi |
| **Ordini fuori orario / duplicati / senza risk check** | 2 ordini, entrambi in RTH, `order_id` distinti, entrambi con `reason` esplicito | ✅ nessuna violazione |
| **Idempotenza Celery** | 24 slot / 24 cicli; `ON CONFLICT` su `news_log`; nessun trade doppio | ✅ nessuna violazione osservata |
| **[F-046] titolo non passato al modello** | I due articoli decisivi hanno titolo e corpo coerenti (nessun teaser) | ✅ nessuna occorrenza contata oggi (la persistenza dello score del 08-25 è già registrata dall'alpha-miss) |
| **Etichetta `exit_mechanism` (#184)** | Entrambe le SELL portano `below_entry_gate` con età e score nel `reason` | ✅ **etichette osservate**, non dedotte per orologio. Nessun conteggio di questo report è una stima. |

## 12. Dati mancanti o non accessibili

| Cosa manca | Perché | Query / azione che servirebbe |
|---|---|---|
| **Latenza per chiamata LLM** | nessuna colonna di latenza in `llm_responses`; log del giorno distrutti | `ALTER TABLE llm_responses ADD COLUMN latency_ms integer` + scrittura nel worker. Senza, §5a non può avere la colonna latenza. |
| **Causa dell'outage Ollama** | log distrutti ([F-027]); nessuna tabella registra i fallimenti di chiamata | tabella `llm_call_failures(ts, model_id, http_status, error, attempt)`. **Questo è il dato mancante più costoso della giornata.** |
| **Numero di tentativi falliti fra 15:31 e 19:45** | idem: 79 scoring caduti su FinBERT, 0 righe di tentativo | idem |
| **Slippage reale** | `trades.slippage_est` è una copia di `cost_usd` ([F-015]); prezzo atteso non persistito | persistere il mid/last NBBO al momento della submission e confrontarlo con `filled_avg_price` |
| **Riconciliazione broker↔DB in questa sessione** | non ho interrogato il broker (read-only stretto) | `GET /v2/positions` confrontato con `trades WHERE exit_time IS NULL`. **Eseguita lo stesso giorno** in `ALPHA_MISS_REPORT_2026-08-26.md` §7 → [F-048], 3 quantità divergenti. |
| **MTM per sleeve** | non calcolabile finché [F-048] è aperto (quantità a DB divergenti) | riscrittura delle uscite parziali su `trades`, poi MTM per `stop_strategy` |
| **Conferma paper via broker** | nessuna chiamata all'account | `GET /v2/account` → verifica del flag paper. Oggi confermato solo per configurazione. |
| **Drawdown per sleeve** | `per_strategy_metrics={}` ([DAY-010]) | curva equity per sleeve, sul modello di `_fetch_equity_curve` (#107) |
| **Dati REST** | token rifiutato ([F-041]) | header corretto o rigenerazione della chiave; nessun dato di questo report ne dipende |
| **Log frontend** | fuori perimetro; `alembic-frontend-1` up da 9 giorni, nessuna interazione utente sospetta rilevante alla giornata | — |

## 13. Raccomandazioni immediate

Ordinate per rapporto fra evidenza compromessa e costo. **Nessuna è una taratura**: il freeze
della carta di osservazione è rispettato in tutte.

1. **Rendere osservabile il fallimento dell'ensemble** ([DAY-001]). È l'unica raccomandazione
   veramente urgente. Tre interventi indipendenti e piccoli: cablare un chiamante a
   `send_fallback_alert`; cambiare `==` in `>=` sulla soglia del breaker; persistere i fallimenti
   di chiamata in una tabella invece che nei log volatili. Finché nessuno dei tre è fatto, ogni
   seduta può perdere due terzi della propria capacità di valutazione in silenzio, e il ledger
   dei 40 giorni conterrà giornate vuote indistinguibili da giornate senza segnali.
2. **Isolare la suite di test dal database di produzione** ([DAY-006]). Terza occorrenza. Costo:
   una variabile d'ambiente e un `conftest` che rifiuta di partire sul DSN live.
3. **Popolare `execution_decisions.signal_id` sui rami che hanno il segnale in mano**
   ([DAY-009]). `below_entry_gate` ne stampa già timestamp e score nel testo: è un campo da
   riempire, non un dato da ricostruire.
4. **Verificare sulla seduta del 2026-08-27 che `FILL_OUTSIDE_RTH` sia tornato a zero**
   ([DAY-008]). Se sì, F-047 si chiude e la riconciliazione shadow #295 comincia a produrre
   osservazioni utili.
5. **Derivare le finestre del beat dal calendario di mercato** ([DAY-005]). Stesso vizio di
   [DAY-008], stesso rimedio; recupera il 9,5% di ogni sessione.
6. **Separare `targets_count` da `submitted_count`** ([DAY-007]). Un giorno da 2 ordini che si
   presenta come 110 impedisce di accorgersi di una seduta a zero ingressi.

**Da NON fare adesso**: qualunque intervento sulla banda d'uscita, sul gate 0,30, sulla soglia di
informatività o sul cooldown. [DAY-002] e [DAY-003] sono difetti reali del modello di dominio, ma
la loro correzione è taratura e va al 28/09. Il lavoro ammesso oggi è **misurarli**, e i due
monitor proposti nelle rispettive schede servono esattamente a questo.

## 14. Test e monitor da aggiungere

| # | Tipo | Oggetto | Assertion / soglia |
|---|---|---|---|
| 1 | test unitario | circuit breaker di fallback | costruire `RedisStore` **come la produzione** e verificare che 3 fallback consecutivi producano un record persistente e osservabile; verificare che il trigger scatti anche se il contatore salta il valore 3 |
| 2 | monitor giornaliero | salute dell'ensemble | allerta se `quota(model_id LIKE 'ensemble:%') < 50%` dei segnali del giorno, **oppure** se `MAX(llm_responses.generated_at) < chiusura_RTH − 45 min` |
| 3 | test di invariante | `llm_responses.eligible` | per ogni `signal_id` con `model_id LIKE 'ensemble:%'`, `COUNT(eligible=true)` = numero di modelli nominati in `model_id` |
| 4 | `conftest` | isolamento della suite | fallire l'avvio se il DSN coincide con quello di produzione; allerta notturna su simboli `LIKE 'TEST%'` e su `source` presenti in `ingestion_stats_daily` ma assenti da `news_log` nello stesso giorno |
| 5 | test unitario | finestra del beat | dato un giorno EDT e un giorno EST, il primo slot pianificato non è successivo all'apertura RTH del calendario |
| 6 | monitor giornaliero | uscite a informazione nulla | elenco delle uscite con `|signal_score| < 0.05` **e** `confidence < 0.30`, con P&L realizzato e drift post-uscita. Serie per il 28/09. |
| 7 | monitor giornaliero | uscite da fan-out | elenco delle uscite il cui segnale causante ha `directness != 'direct'` o `relevance = 'UNKNOWN'`, con P&L. Serie per il 28/09. |
| 8 | check notturno | tracciabilità | `COUNT(*) FROM execution_decisions WHERE signal_id IS NULL AND decision IN ('BUY','SELL')` = 0 |
| 9 | check notturno | telemetria del ciclo | `SUM(submitted_count)` = ingressi + chiusure del giorno |
| 10 | monitor read-only | drawdown per sleeve | calcolo fuori dal path di alert, scritto nel dossier, in attesa del ricablaggio di `strategy_returns` |
| 11 | monitor | RTH del lifecycle | allerta su `FILL_OUTSIDE_RTH` con `filled_at` interno alla sessione del calendario |
| 12 | hook di deploy | ritenzione dei log | archiviare `docker compose logs --since 48h` su disco prima di `up -d` |

## 15. Ticket tecnici suggeriti

Solo correttezza, come impone la carta di osservazione. Per ciascuno indico se passa il test di
esenzione ("se non lo correggo, l'evidenza che raccolgo nelle prossime settimane è sbagliata?").

| # | Titolo | Area | Priorità | Esente dal freeze? |
|---|---|---|---|---|
| T-1 | L'outage dell'ensemble deve produrre un alert e una riga persistente: cablare `send_fallback_alert`, `>=` sulla soglia, tabella dei fallimenti di chiamata | LLM / Ops | **P0** | **Sì** — una seduta su 40 è stata svuotata in silenzio; senza, il ledger non distingue "nessun segnale" da "nessuna valutazione" |
| T-2 | La suite di test non deve poter scrivere nel DB di produzione; i DELETE su `trades` vanno auditati | Data / Ops | **P0** | **Sì** — righe di test dentro le tabelle da cui il ledger legge |
| T-3 | `execution_decisions.signal_id` popolato su tutti i rami che hanno il segnale in mano | Data | **P1** | **Sì** — la catena causale è oggi ricostruibile solo per parsing di testo libero |
| T-4 | `llm_responses.eligible` deve descrivere i contributori reali (propagare il floor del retry #90) | LLM | **P1** | **Sì** — 28 righe su 42 sbagliate oggi; il ribilanciamento dei pesi ne dipende |
| T-5 | Le finestre del beat derivano dal calendario di mercato, non da un'ora UTC fissa | Ops | **P1** | **Sì** — mancano sistematicamente i primi 37 minuti di ogni seduta osservata |
| T-6 | `portfolio_cycles`: separare `targets_count` da `submitted_count`; persistere tutte le disposizioni in `execution_decisions` | Ops | **P2** | Parzialmente — la telemetria non falsifica l'evidenza, ma nasconde le giornate a zero ingressi |
| T-7 | Semantica di `ingestion_stats_daily`: dichiarare per-run vs per-giorno e rendere i contatori omogenei | Data | **P2** | No — non falsifica l'evidenza, la rende solo illeggibile |
| T-8 | Curva equity per sleeve e ricablaggio di `strategy_returns` nel monitor di rischio | Risk | **P2 → dopo il 28/09** | **No** — l'assenza non rende sbagliata l'evidenza raccolta |
| T-9 | Persistere il prezzo atteso alla submission per misurare lo slippage reale ([F-015]) | Broker | **P2** | No — ma senza, la qualità d'esecuzione resta non misurata per tutta la finestra |
| T-10 | Ritenzione dei log dei container attraverso il redeploy | Ops | **P1** | **Sì di fatto** — oggi ha impedito la diagnosi dell'anomalia più grave della giornata |

**Fuori dal perimetro del freeze, da portare come decisione al 28/09**: la distinzione fra
"segnale assente" e "contro-segnale" nel ramo d'uscita ([DAY-002], [DAY-003]) — collegata a
#182/#338. I monitor 6 e 7 di §14 servono a costruire la serie che quella decisione richiederà.

## 16. Stato sistema

| Voce | Valore |
|---|---|
| **Ollama Cloud — stato** | **DOWN dalle 15:31:00 UTC alla fine della sessione** |
| **Ore di downtime nella sessione** | **4h14m** (15:31:00 → 19:45:07), cioè **65% della sessione RTH 13:30–20:00** |
| **Prova del downtime** | `MAX(llm_responses.generated_at)` = 15:31:00.458558 per **entrambi** i modelli; `llm_budget.updated_at` = 15:31:00.446940; `fallback_counters.reset_at` = 15:31:00.449297 con `last_increment_at` = 19:45:07.786854 e `counter_value` = **79** |
| **Causa del downtime** | **non determinabile** — log del 2026-08-26 distrutti dal redeploy ([F-027]); nessuna tabella registra i fallimenti di chiamata |
| **Esaurimento budget come causa** | **escluso**: $0,0377 spesi (contro ~$0,20 tipici), `budget_exhausted = false`, 19.551 token input / 2.378 output |
| **FinBERT fallback rate — segnali** | **93/114 = 81,6%** `fallback_used=true`; di cui **79/114 = 69,3% FinBERT puro** (contro **0,0%** il 2026-08-25) |
| **FinBERT fallback rate — decisioni** | 17 `SKIP_FALLBACK` su 336 decisioni (5,1%); ma **0 ordini d'ingresso** su 108 target, quindi il tasso sulle decisioni **eseguite** è 0/2 = 0% (le due uscite precedono l'outage) |
| **Modelli configurati** | Redis `config:sentiment_llm_models` = `glm52,gptoss` → `glm-5.2:cloud` + `gpt-oss:20b-cloud`. Coerente con CLAUDE.md. |
| **Gate d'ingresso S4 attivo** | Redis `feedback:entry_threshold:S4` = **0.30** (baseline, nessun ratchet in corso) |
| **Circuit breaker di fallback** | **scattato** 15:45:07.379684. Effetto reale: **nessuno** — `qc:sizing_multiplier=0.5` senza consumatori, callback Telegram `None`, 1 riga in una lista Redis con TTL 24h |
| **Stato residuo del breaker** | `fallback:consecutive:count` = **79**, TTL ~3h al momento dell'analisi (scadenza 2026-08-27 19:45); `qc:sizing_multiplier` = **0.5** ancora presente, inerte |
| **Alert Telegram consegnati** | **0** (nessun tentativo: la callback non è cablata) |
| **Worker restart events** | **0** — `RestartCount=0` su `worker`, `worker-inference`, `beat`, `api`. Nessun riavvio durante il 2026-08-26. |
| **Ricreazione dei container** | 2026-08-27 10:13:59 UTC (deploy di `c9f77d2`, `c885643`, `2be7b32`) — **dopo** la seduta analizzata |
| **Redis / Postgres** | up da 9 giorni, `healthy` |
| **Frontend** | up da 9 giorni; non rilevante alla giornata |
| **NAV / esposizione / drawdown** | $110.073,75 / 29,34% / 1,24% |
| **Posizioni aperte a fine giornata** | 46 (34 S1, 2 S4, 10 senza attribuzione di sleeve) |
| **Cicli portfolio** | 24/24, cadenza esatta, nessun gap |
| **Modalità** | **paper** (per configurazione; non verificato via broker in questa sessione) |
| **Freeze di osservazione** | **rispettato**: dossier `decision_quality.freeze` = `{mode: read_only_measurement, live_thresholds_weights_flags_cooldowns_changed: false, live_size_holding_exit_policy_changed: false}`. Questa sessione non ha modificato alcun file oltre il report e il ledger. |

---

*Report prodotto in sola lettura. Nessun ordine inviato, nessun worker avviato, nessuna pipeline
rieseguita, nessuna patch applicata.*
