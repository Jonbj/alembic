# Forensic Daily Report — 2026-08-03 (lunedì)

**Analista:** sessione autonoma non-interattiva (Trading Systems Forensic Analyst / Senior Backend
Engineer / Quant Operations Reviewer).
**Modalità:** read-only. Nessuna modifica a codice, configurazione o stato del sistema. Nessun
ordine, nessuna chiamata broker in modalità trading, nessun worker avviato.

**Timezone operativo: UTC**, confermato nel codice — `src/workers/celery_app.py:51-52`
(`timezone="UTC"`, `enable_utc=True`). Tutti gli orari di questo documento sono UTC.
Market hours NYSE 13:30–20:00 UTC. **Nessuna ambiguità di timezone rilevata.**

**Modalità broker: PAPER**, verificata a runtime e non dedotta:
`ALPACA_BASE_URL=https://paper-api.alpaca.markets` nell'ambiente del container `worker`,
`config/trading.yaml → execution.engine: portfolio`, Redis `system:mode = paper`.
L'md5 di `/app/config/trading.yaml` nel container coincide con quello del repo
(`2b10d2915ee6f576293af480d4d7771e`): **nessun drift config baked/repo**.

**Primo giorno pieno del periodo di sola osservazione** (`docs/evidence/OBSERVATION_CHARTER.md`).
In coerenza con la carta questo documento **non propone tarature**. I ticket suggeriti in §15 sono
esclusivamente difetti di **correttezza/misura**, cioè quelli che, se non corretti, rendono
sbagliata l'evidenza raccolta nelle prossime settimane.

**Documento complementare:** `docs/ALPHA_MISS_REPORT_2026-08-03.md` copre l'attribuzione alpha
(mover catturati/mancati). Questo report copre la **correttezza funzionale della pipeline**. Dove
un numero è già stato calcolato lì (prezzi di chiusura, controfattuali per mover) lo cito invece di
ri-derivarlo.

---

## 1. Executive summary

La pipeline ha girato end-to-end senza interruzioni: 24 cicli portfolio a cadenza 15 min esatta
(14:07→19:52), 202 news scorate, 13 ordini inviati e riempiti, 0 reject, 0 restart di container.
Ollama è stato **up al 100%** (404/404 risposte dai due modelli, nessun timeout); FinBERT è
intervenuto **1 volta su 202** (0,5%). Il realizzato è **+$142,75** (tutto S4), equity di chiusura
**$109.704,03**.

I controlli di sicurezza hanno funzionato: guard anti-pyramiding, idempotenza per `signal_id`,
`hold_minimum_minutes=90`, isteresi d'uscita a 2 cicli, safety-net regime delle 13:30 dopo il
fallimento FRED delle 07:00. Nessun ordine fuori orario, nessun duplicato, nessun ordine senza
segnale, nessuna posizione non riconciliata.

Il problema del giorno **non è l'esecuzione ma la misura**. Quattro difetti strutturali corrompono
proprio l'evidenza che il periodo di osservazione deve raccogliere: (a) il retry a floor 0
introdotto con #90 non è stato propagato né alla persistenza né al ramo single-model, così il 74%
dei modelli che hanno realmente contribuito a un segnale risulta `eligible=False` e il
ribilanciamento LOO-ICIR che fissa i pesi live gira sul 17% dell'evidenza; (b) `signal_id` è NULL
su 505/508 decisioni, quindi la catena news→segnale→decisione→trade non è ricostruibile per FK;
(c) metà delle righe scorate viene da articoli fan-out taggati a società diverse dal soggetto —
tre dei sei BUY del giorno nascono da un singolo pezzo su CoreWeave; (d) `slippage_est` è una copia
di `cost_usd`, quindi la qualità di esecuzione non è misurata affatto.

---

## 2. Verdict finale

### OK CON WARNING — esecuzione corretta, misura compromessa

Motivazione, esplicita sulle due dimensioni:

- **Correttezza operativa (ordini, risk, esecuzione): OK.** Ogni ordine del 2026-08-03 è
  riconducibile a una decisione persistita, ha superato i guard previsti, è stato riempito e
  riconciliato. Non ho trovato un singolo ordine ingiustificato, duplicato, fuori orario o su
  ticker non consentito.
- **Affidabilità dell'evidenza raccolta: COMPROMESSA su quattro fronti.** I difetti [DAY-001],
  [DAY-002], [DAY-004] e [DAY-009] non hanno prodotto perdite il 2026-08-03, ma corrompono
  sistematicamente le serie (pesi ensemble, catena di provenienza, attribuzione news, qualità di
  esecuzione) su cui la sintesi del giorno 40 dovrà basarsi. Passano il test di esenzione della
  carta: *«se non lo correggo, l'evidenza che raccolgo nelle prossime settimane è sbagliata?»* →
  sì.

Il verdetto non è "anomalie significative" perché nessun difetto ha causato una perdita
misurabile: il costo attribuito totale della giornata è **$10,07** ([DAY-006], churn di rientro),
contro un realizzato di +$142,75.

---

## 3. Timeline del 2026-08-03 (UTC)

| Ora | Componente | Evento | Esito | Fonte |
|---|---|---|---|---|
| 07:00:00 | `regime.detect_regime` | Run primario pre-market | **FALLITO** — FRED HTTP 500 su `series_id=VIXCLS`; task riportato `succeeded ... : None`, `regime:current` non scritta | `docker logs worker-inference` |
| 07:04:24 | `ingestion` (reuters) | Ultimo aggiornamento `ingestion_stats_daily` per reuters: fetched=4, queued=4, discarded_no_ticker=1 | 0 righe in `news_log` | `ingestion_stats_daily` |
| 13:30:00 | `regime.detect_regime` | Safety-net P0-09 (30 min pre-open) | **OK** in 52 s — `sideways ×0.7`, `disagreement=False`, VIX 17,09 | log + Redis `regime:current` |
| 13:30 | NYSE | Apertura mercato | — | — |
| 14:00:00 | `sentiment-worker` | Primo run della sessione | OK in 0,8 s — coda vuota, 0 item | log worker-inference |
| 14:07:00 | `portfolio-cycle` #742 | Primo ciclo. `S4: dropped 32/32 stale signals (age > 4h)` — nessun segnale S4 fresco all'apertura (il worker sentiment non gira di notte) | 47 ordini target, **0 inviati**, constraints=0 | `portfolio_cycles` id 742 |
| 14:07:05 | `execution_decisions` | id 5682 `SKIP_STALE` su SHEL: `signal 67.9h old > max_age 4h (score -0.266)` | Corretto | `execution_decisions` |
| 14:15:07 | `sentiment-worker` | Prima news scorata del giorno (`news_log` 6085, NVDA) | Run 14:15 chiuso in 130 s | `news_log`, `sentiment_signals` |
| 14:15:07 | `alpaca_benzinga` | Prima riga ingest | — | `news_log` |
| 14:22:00 | `portfolio-cycle` #743 | **3 SELL inviate**: AMZN (`whipsaw`, score −0,150), MA (`no_signal`), MSFT (`whipsaw`, score +0,000) | 3 fill, chiudono trade 598/594/597 aperti il 07-31 | `execution_decisions` 5707-5709, `trades` |
| 15:00:16 | `gdelt_gkg` | Prima riga ingest GKG (45 min dopo Benzinga) | — | `news_log` |
| 15:30:34 | `sentiment` | **MSFT +0,710 conf 0,875** (glm +0,85/0,90, gpt +0,75/0,85) su «Microsoft Stock Jumps as Azure Tops $100 Billion» — segnale più forte della giornata | Nessun ordine: sovrascritto 58 s dopo | `sentiment_signals` 6124 |
| 15:31:32 | `sentiment` | MSFT −0,056 da «What Is Going on With **Oracle** Stock on Monday?» | Annulla il precedente ([DAY-005]) | `sentiment_signals` 6130 |
| 15:31:40 | `sentiment` | ORCL +0,515 conf 0,775, stesso articolo (ticker-specifico stavolta) | → BUY | `sentiment_signals` 6131 |
| 15:37:00 | `portfolio-cycle` #748 | **BUY ORCL** 9,065 az. @ 137,09, notional $1.242,78, weight 2,0% | Fill | dec. 5810, trade 640 |
| 16:01:20 | `sentiment` | ORCL −0,343 da «Amazon, Alphabet Lead 'AI Debt Tsunami'» (articolo macro taggato a 7 ticker) | Capovolgimento 0,858 pt in 30 min | `sentiment_signals` 6150 |
| 16:07:00 | `portfolio-cycle` #750 | **BUY ARM** (S1 momentum) 1,409 az. @ 237,124, weight 0,5% | Fill | dec. 5858, trade 641 |
| 16:31:02 | `sentiment` | AMZN +0,343 da «CoreWeave Stock Jumps…» | → BUY | `sentiment_signals` 6175 |
| 16:37:00 | `portfolio-cycle` #752 | **BUY AMZN** 4,362 az. @ 284,59 (ri-acquisto del titolo venduto alle 14:22) | Fill | dec. 5912, trade 642 |
| 16:45:11/21 | `sentiment` | MSFT +0,307 e NVDA +0,388 dallo **stesso** articolo CoreWeave | → 2 BUY | `sentiment_signals` 6176, 6178 |
| 16:52:00 | `portfolio-cycle` #753 | **BUY MSFT** 2,543 az. @ 488,50 + **BUY NVDA** 5,998 az. @ 207,13. Log: `Hold minimum (90 min): skipped 1 SELL order(s) for recently-bought: ['AMZN','ARM','ORCL']` | 2 fill | dec. 5938/5939, trade 643/644 |
| 17:22:00 | `portfolio-cycle` #755 | **SELL ORCL** @ 139,77 (`whipsaw`, 105 min dall'ingresso) | Realizzato +$23,61 su $43,15 disponibili | dec. 5997 |
| 18:22:00 | `portfolio-cycle` #759 | **SELL AMZN** @ 282,60 (`whipsaw`, score **+0,196** positivo) | Realizzato −$8,93 | dec. 6093 |
| 18:37:00 | `portfolio-cycle` #760 | **SELL MSFT** @ 490,05 (`whipsaw`, score **+0,013** positivo) | Realizzato +$3,70 | dec. 6110 |
| 19:07:00 | `portfolio-cycle` #762 | **SELL NVDA** @ 208,55 (`whipsaw`, score +0,000) | Realizzato +$8,29 | dec. 6139 |
| 19:15:41 | `sentiment` | META +0,356 conf 0,600 da «Meta Platforms Stock Is Gaining Monday» | → BUY | `sentiment_signals` 6269 |
| 19:22:00 | `portfolio-cycle` #764 | **BUY META** 2,066 az. @ 593,40, **38 min prima della chiusura**, sopra il close (590,24) | Fill, resta aperta | dec. 6156, trade 645 |
| 19:45:45 / 19:46:02 | `ingestion` | Ultime righe Benzinga / GKG | — | `news_log` |
| 19:52:00 | `portfolio-cycle` #765 | Ultimo ciclo della sessione | 49 ordini target, 0 inviati | `portfolio_cycles` 765 |
| 20:00 | NYSE | Chiusura | — | — |
| 21:00:00 | `decay_monitor_task` | 8 alert CRITICAL su S1/S2/S4 con **metriche identiche** (IC 0,004; Sharpe −6,98) | [DAY-008] | log worker |
| 22:30:01 | `risk_report` | id 52: NAV $109.722,24, exposure 29,84%, herfindahl 0,0227, `combined_drawdown` **0,0124** ma alert «drawdown 13,9% exceeds 10%» | [DAY-007] | `risk_reports` |

**Gap temporali:** nessuno nella cadenza dei cicli (24 cicli, esattamente 15 min di distanza,
14:07→19:52). Il primo ciclo è alle 14:07 e non alle 13:37 perché il beat è schedulato
`hour="14-21"` — **37 minuti di apertura non coperti, da design, non un guasto.**

---

## 4. Tabella news ingest

### 4.1 Per fonte

| Fonte | fetched | queued | duplicates | discarded_no_ticker | discarded_stale | parse_fail | righe in `news_log` | copertura oraria |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `alpaca_benzinga` | 707 | 370 | 2.998 | 0 | 0 | 0 | **91** | 14:15 → 19:45 |
| `gdelt_gkg` | 2.242 | 184 | 117 | 1.985 | 0 | 0 | **111** | 15:00 → 19:46 |
| `reuters` | 4 | 4 | 0 | 1 | 0 | 0 | **0** | run 07:04 |
| **Totale** | **2.953** | **558** | **3.115** | **1.986** | **0** | **0** | **202** | |

Osservazioni:

- **`duplicates` (2.998) supera `fetched` (707) di 4,2× per Benzinga** — stesso pattern del 07-31
  già registrato come **F-007** nel ledger (contatore UPSERT additivo cross-run,
  `src/store/pg_store.py:369`). Non ho potuto verificarlo indipendentemente per-ciclo. Le 202 righe
  finali di `news_log` restano verificate riga per riga.
- **GDELT scarta l'88,5% del fetched** per `discarded_no_ticker` (1.985/2.242) — atteso dato che
  GKG è un feed globale non finanziario, ma è un rapporto segnale/rumore da tenere sotto
  osservazione.
- **Reuters: 4 fetched, 4 queued, 0 righe in `news_log`.** Il task RSS risulta disabilitato dal
  2026-07-03 (`celery_app.py`, FIX-02) eppure `ingestion_stats_daily` ha una riga reuters con
  `updated_at` 07:04:24 del 2026-08-03. Non è un ordine sbagliato né una perdita, ma è un residuo
  che rende ambigua la lettura di quali fonti siano davvero attive → §12.
- **Nessuna news scartata come stale, nessun parse fail, nessun timestamp futuro** (0 righe con
  `published_at > created_at` su entrambe le fonti).
- **Nessuna news fuori orario di mercato**: `published_at` va da 13:04:31 a 18:02:31.

### 4.2 Latenza pubblicazione → scoring

| Fonte | lag medio | lag massimo |
|---|---:|---:|
| `alpaca_benzinga` | **80 min** | 121 min |
| `gdelt_gkg` | **74 min** | 107 min |

Un articolo pubblicato viene tradotto in segnale dopo **oltre un'ora in media**. Esempio concreto:
«What Is Going on With Oracle Stock on Monday?» pubblicato 14:37:33, scorato 15:31:40, ordine
15:37:00 — **60 minuti** fra pubblicazione ed esecuzione. Non è un difetto di correttezza (è
cadenza del beat + coda), ma è un dato che pesa sulla domanda di uscita 1 della carta e va
registrato.

### 4.3 Per ticker

202 righe, **130 URL distinti**, **56 ticker distinti** su una watchlist di 96.

| Ticker | righe | | Ticker | righe |
|---|---:|---|---|---:|
| MS | 28 | | INFY | 7 |
| GS | 13 | | LLY | 7 |
| MU | 12 | | SPCX | 6 |
| AMD | 11 | | NVDA | 5 |
| MSFT | 10 | | GOOGL | 5 |
| SHEL | 8 | | TSM | 4 |
| META | 7 | | DIS | 4 |
| AMZN | 7 | | AAPL | 4 |

**41/96 simboli (43%) senza alcuna riga in `news_log`** — occorrenza già registrata al ledger come
**F-001** dall'Alpha-Miss Report, non la duplico qui.

### 4.4 Fan-out multi-ticker (problema principale dell'ingest) — [DAY-004]

| n. ticker per articolo | n. articoli | righe generate |
|---:|---:|---:|
| 1 | 98 | 98 |
| 2 | 17 | 34 |
| 3 | 4 | 12 |
| 4 | 6 | 24 |
| 5 | 1 | 5 |
| 6 | 2 | 12 |
| 7 | 1 | 7 |
| 10 | 1 | 10 |

**104 righe su 202 (51%) provengono da 32 articoli taggati a 2+ ticker.** I peggiori:

| Titolo | Fonte | n. ticker | Ticker |
|---|---|---:|---|
| Yen Intervention And Falling Oil Help Stocks… | benzinga | **10** | AAPL,AMD,AMZN,AZN,GOOGL,META,MSFT,MU,NVDA,QQQ |
| Amazon, Alphabet Lead 'AI Debt Tsunami'… | benzinga | 7 | AMZN,GOOGL,META,MSFT,NVDA,ORCL,SPCX |
| Trump Warns Oil Executives… | benzinga | 6 | BP,CVX,QQQ,SHEL,SPY,XOM |
| CoreWeave Stock Jumps as AI Data-Center Demand… | benzinga | 5 | AAPL,AMZN,META,MSFT,NVDA |
| What Is Going on With **Oracle** Stock on Monday? | benzinga | 4 | AMZN,GOOGL,MSFT,ORCL |

`extraction_method`: 111 `org_lookup` (tutti GKG), 91 `source_metadata` (tutti Benzinga). Il
fan-out **non** è un errore del resolver: Benzinga fornisce i tag nel proprio metadata e il sistema
li accetta tutti come se l'articolo parlasse di ciascun ticker. Vedi §10 [DAY-004].

### 4.5 Sanitizzazione

`sanitize_text()` è invocata sia sul corpo live sia sul path shadow
(`src/workers/sentiment.py:583, 597`). Non ho trovato omissioni. **Nessuna evidenza di homoglyph o
di testo nascosto** nelle 202 righe ispezionate.

**Confidenza dell'analisi ingest: ALTA** per `news_log` (verificata riga per riga),
**MEDIA** per `ingestion_stats_daily` (contatori additivi non verificabili indipendentemente,
vedi F-007).

---

## 5. Tabella performance modelli LLM

### 5.1 Per modello

| Modello | richieste | risposte | timeout | refusal/invalid | polarity media | conf. media | σ polarity | min/max polarity | polarity = 0 |
|---|---:|---:|---:|---:|---:|---:|---:|---|---:|
| `glm-5.2:cloud` | 202 | **202** | **0** | **0** | +0,0475 | 0,2629 | 0,2136 | −0,60 / +0,85 | 90 (45%) |
| `gpt-oss:20b-cloud` | 202 | **202** | **0** | **0** | +0,0059 | 0,3873 | 0,2134 | −0,60 / +0,75 | 103 (51%) |
| `finbert` (fallback) | 1 | 1 | — | — | — | 0,208 | — | — | — |

**Latenza:** non misurata per singola chiamata (nessuna colonna in `llm_responses`, nessun log per
chiamata). Proxy disponibile: durata del task `run_sentiment_worker` — mediana **~113 s** per
batch, range 68–204 s. Vedi §12.

### 5.2 Composizione del segnale

| `model_id` del segnale | `fallback_used` | n. | score medio | conf. media | `ensemble_std` media |
|---|---|---:|---:|---:|---:|
| `ensemble:glm-5.2:cloud+gpt-oss:20b-cloud` | f | **129** | +0,0369 | 0,3012 | 0,0449 |
| `single:gpt-oss:20b-cloud` | t | **64** | −0,0325 | 0,4925 | 0,0000 |
| `single:glm-5.2:cloud` | t | **8** | +0,0519 | 0,5000 | 0,0000 |
| `finbert` | t | **1** | +0,0053 | 0,2083 | 0,0000 |

**`fallback_used=True` su 73/202 = 36,1%**, ma la lettura corretta è: **Ollama non è mai caduto**.
72 dei 73 "fallback" sono letture a modello singolo, non outage — entrambi i modelli avevano
risposto, ma uno solo aveva superato il floor 0,4. FinBERT vero è entrato **1 volta su 202 (0,5%)**.
Il contatore `consecutive_fallback` in `fallback_counters` è a **0** con `reset_at` 19:46:02: il
circuit breaker di sizing non è mai scattato, correttamente (`_is_full_fallback` distingue
single-model da outage pieno, #128/#111).

### 5.3 Accordo / disaccordo fra modelli

| Metrica | Valore |
|---|---:|
| Coppie con polarity di **segno opposto** | **8 / 202 (4,0%)** |
| Coppie con polarity **identica** | 84 / 202 (41,6%) — di cui **71 entrambe a 0,00** |
| \|Δpolarity\| medio sui segnali ensemble | 0,064 |
| \|Δpolarity\| medio sui segnali single-model | 0,147 (gpt) / 0,256 (glm) |
| \|Δpolarity\| massimo | 0,50 |

Il disaccordo è **basso**: la divergenza non è il collo di bottiglia della giornata. Il collo di
bottiglia è che **entrambi i modelli dicono "non so"**: 71 coppie su 202 hanno polarity 0,00 da
entrambi.

### 5.4 Distribuzione dello score finale

| Metrica | Valore |
|---|---:|
| Segnali totali | 202 |
| score esattamente 0,000 | **79 (39,1%)** |
| \|score\| < 0,05 | **118 (58,4%)** |
| score ≥ +0,30 (gate d'ingresso) | **9 (4,5%)** |
| score ≤ −0,30 | 4 (2,0%) |
| min / max | −0,360 / **+0,710** |

Solo **13 segnali su 202 (6,4%)** attraversano il gate ±0,30. Questo quantifica su base
distribuzionale la stessa affermazione di **F-009** già a ledger (*il collo di bottiglia è la
magnitudine, non il segno*); **non aggiungo una seconda occorrenza a F-009 per lo stesso giorno**,
lo cito come evidenza di supporto.

### 5.5 Ticker con score estremi

| Simbolo | score | conf. | fallback | ora | esito |
|---|---:|---:|---|---|---|
| **MSFT** | **+0,710** | 0,875 | f | 15:30:34 | **nessun ordine** — sovrascritto a 58 s ([DAY-005]) |
| CVX | +0,560 | 0,800 | f | 16:30:42 | nessun ordine — guard anti-pyramiding (già in book) |
| ORCL | +0,515 | 0,775 | f | 15:31:40 | **BUY 15:37** |
| LLY | +0,444 | 0,725 | f | 16:00:15 | nessun ordine — guard anti-pyramiding |
| NVDA | +0,388 | 0,675 | f | 16:45:21 | **BUY 16:52** |
| META | +0,356 | 0,600 | f | 19:15:41 | **BUY 19:22** |
| AMZN | +0,343 | 0,650 | f | 16:31:02 | **BUY 16:37** |
| MSFT | +0,307 | 0,550 | f | 16:45:11 | **BUY 16:52** |
| PLTR | +0,300 | 0,600 | **t** | 14:15:14 | nessun ordine — segnale fallback, escluso da S4 |
| MU | −0,300 | 0,600 | t | 15:00:24 | nessun ordine (long-only) |
| ORCL | −0,343 | 0,650 | f | 16:01:20 | **SELL 17:22** |
| NVDA | −0,350 | 0,700 | t | 16:01:02 | nessun ordine |
| SHEL | −0,360 | 0,600 | t | 16:45:40 | nessun ordine (long-only) |

### 5.6 Verifica funzionale della catena LLM

| Domanda | Risposta | Evidenza |
|---|---|---|
| L'output LLM è validato prima di entrare nello store? | **Sì** — schema Pydantic `LLMSentimentOutput` via function-calling; 0 parse fail su 404 risposte | `src/workers/sentiment.py:285` |
| L'ensemble gestisce la varianza alta? | **Sì** — `divergence_threshold` → FinBERT; scattato 1 volta | `src/llm/ensemble.py:291` |
| Le news duplicate pesano più volte? | **No per URL** (`uq_news_log_url_ticker`), **sì per ticker**: lo stesso URL genera una riga e un segnale per ogni ticker taggato → [DAY-004] | `news_log` schema |
| La stessa news può generare segnali multipli? | **Sì, per ticker diversi** — è esattamente il fan-out di §4.4 | §4.4 |
| Confidence bassa riduce davvero il peso? | **Sì** — `score = polarity × confidence` e peso ensemble = `confidence × weight_LOO`; verificato su tutti i 13 segnali estremi | `ensemble.py:299-302` |
| I modelli sono chiamati offline/background? | **Sì** — coda `inference`, worker dedicato concurrency=1, mai dentro il loop d'esecuzione | `celery_app.py` beat |
| Rischio che un'allucinazione entri in decisione? | **Mitigato ma non nullo**: doppio modello + floor di confidenza + gate 0,30. **Non c'è supervisor agent né verifica RAG delle affermazioni quantitative.** Il fan-out di §4.4 è il vettore realmente sfruttato oggi | §10 [DAY-004] |

---

## 6. Tabella segnali finali per ticker

Segnali che hanno prodotto un'azione o che erano candidati sopra gate. `SKIP_THRESHOLD` totali del
giorno: **494** su 24 cicli (~20,6/ciclo).

| Simbolo | segnali del giorno | miglior score | decisione | strategia | motivo del non-ordine |
|---|---:|---:|---|---|---|
| ORCL | 2 | +0,515 → −0,343 | BUY 15:37 + SELL 17:22 | S4 | — |
| MSFT | 9 | +0,710 (15:30) | SELL 14:22, BUY 16:52, SELL 18:37 | S4 | il +0,710 non è mai stato eseguito |
| AMZN | 7 | +0,343 | SELL 14:22, BUY 16:37, SELL 18:22 | S4 | — |
| NVDA | 5 | +0,388 | BUY 16:52 + SELL 19:07 | S4 | — |
| META | 7 | +0,356 | BUY 19:22 | S4 | — |
| ARM | 0 | — | BUY 16:07 | **S1** | segnale momentum, non news |
| MA | 0 | — | SELL 14:22 | S4 | `no_signal` — nessun segnale nella finestra |
| CVX | ≥1 | +0,560 | nessuna | S4 | guard anti-pyramiding (già in book) |
| LLY | ≥1 | +0,444 | nessuna | S4 | guard anti-pyramiding |
| PLTR | ≥1 | +0,300 | nessuna | S4 | `fallback_used=True` → escluso |
| XLK | — | +0,294 | SKIP_THRESHOLD ×18 | S4 | sotto gate |
| CAT | — | +0,264 | SKIP_THRESHOLD ×10 | S4 | sotto gate |
| BABA | — | +0,230 | SKIP_THRESHOLD ×5 | S4 | sotto gate (mover +4,13%) |
| SNOW | — | +0,156 | SKIP_THRESHOLD ×4 | S4 | sotto gate (mover +4,86%) |
| RDDT | — | +0,169 | SKIP_THRESHOLD ×4 | S4 | sotto gate (mover +9,98%) |
| SHEL | — | −0,266 (67,9h) | SKIP_STALE | S4 | segnale scaduto, correttamente scartato |

---

## 7. Tabella ordini generati / eseguiti

**13 ordini inviati, 13 riempiti, 0 rejected, 0 cancelled.** Broker: Alpaca **paper**.

| # | Decisione (UTC) | id dec. | Strat. | Simbolo | Azione | Qty | Prezzo fill | Notional | Stato | Segnale causante | Risk check applicati | Anomalie |
|---:|---|---:|---|---|---|---:|---:|---:|---|---|---|---|
| 1 | 14:22:00 | 5707 | S4 | AMZN | SELL (whipsaw) | 4,5308 | 283,3499 | $1.283,9 | filled | `signal_id` **NULL** (ricostruito: 6090, single-model −0,15) | isteresi 2 cicli; hold-min n/a | [DAY-003] |
| 2 | 14:22:00 | 5708 | S4 | MA | SELL (no_signal) | 2,1462 | 575,68 | $1.235,5 | filled | nessuno (per costruzione) | isteresi 2 cicli | — |
| 3 | 14:22:00 | 5709 | S4 | MSFT | SELL (whipsaw) | 2,6566 | 486,67 | $1.292,9 | filled | `signal_id` **NULL** (score +0,000) | isteresi 2 cicli | [DAY-003] |
| 4 | 15:37:00 | 5810 | S4 | ORCL | BUY | 9,0654 | 137,09 | $1.242,78 | filled | `signal_id` **NULL** (ricostruito: 6131, +0,515) | gate 0,30 ✓, weight cap 2% ✓, regime ×0,7 ✓, pyramiding ✓, idempotenza ✓ | [DAY-003] |
| 5 | 16:07:00 | 5858 | **S1** | ARM | BUY | 1,4089 | 237,124 | $334,09 | filled | n/a (momentum) | weight 0,5% ✓, pyramiding ✓ | — |
| 6 | 16:37:00 | 5912 | S4 | AMZN | BUY | 4,3618 | 284,5917 | $1.241,35 | filled | **6175** (+0,343, art. CoreWeave) | gate ✓, cap ✓, pyramiding ✓ | ri-acquisto dopo SELL 14:22 → [DAY-006]; [DAY-004] |
| 7 | 16:52:00 | 5939 | S4 | MSFT | BUY | 2,5434 | 488,50 | $1.242,46 | filled | **6176** (+0,307, art. CoreWeave) | gate ✓, cap ✓, pyramiding ✓ | ri-acquisto dopo SELL 14:22 → [DAY-006]; [DAY-004] |
| 8 | 16:52:00 | 5938 | S4 | NVDA | BUY | 5,9984 | 207,13 | $1.242,46 | filled | **6178** (+0,388, art. CoreWeave) | gate ✓, cap ✓, pyramiding ✓ | [DAY-004] |
| 9 | 17:22:00 | 5997 | S4 | ORCL | SELL (whipsaw) | 9,0654 | 139,77 | $1.267,1 | filled | `signal_id` NULL (6150, −0,343) | hold-min 90' ✓ (105'), isteresi ✓ | F-008 |
| 10 | 18:22:00 | 6093 | S4 | AMZN | SELL (whipsaw) | 4,3618 | 282,60 | $1.232,6 | filled | `signal_id` NULL (score **+0,196**) | hold-min ✓ (105'), isteresi ✓ | SELL su sentiment positivo → [DAY-006] |
| 11 | 18:37:00 | 6110 | S4 | MSFT | SELL (whipsaw) | 2,5434 | 490,05 | $1.246,4 | filled | `signal_id` NULL (score **+0,013**) | hold-min ✓ (105'), isteresi ✓ | SELL su sentiment positivo → [DAY-006] |
| 12 | 19:07:00 | 6139 | S4 | NVDA | SELL (whipsaw) | 5,9984 | 208,553 | $1.251,0 | filled | `signal_id` NULL (score +0,000) | hold-min ✓ (135'), isteresi ✓ | — |
| 13 | 19:22:00 | 6156 | S4 | META | BUY | 2,0663 | 593,40 | $1.226,13 | filled | `signal_id` **NULL** (6269, +0,356) | gate ✓, cap ✓, pyramiding ✓ | ingresso 38' dalla chiusura, **sopra il close** (590,24); [DAY-003] |

**`portfolio_cycles.orders_count` somma 1.169 per la giornata**: quel campo conta gli *ordini
target* del combiner (47–51 per ciclo, in larghissima parte no-op), non gli ordini inviati, che
sono 13. Vedi [DAY-009].

Guard che hanno bloccato ordini (correttamente):
- `P0-05 pyramiding guard` — 24 attivazioni per ciclo su ~40 simboli già in book.
- `P1-S4 SIGNAL_DUPLICATE_SKIP` — 8 attivazioni (NVDA ×5 su `signal_id=6178`, AMZN ×2 su 6175,
  MSFT ×1 su 6176): **l'idempotenza per `signal_id` ha impedito 8 BUY duplicati.**
- `Hold minimum (90 min)` — attivo su AMZN/ARM/ORCL alle 16:52.
- `S4: dropped N/M stale signals (age > 4h)` — su ogni ciclo, fino a 32/32 al primo.

---

## 8. Tabella PnL / rendimento

### 8.1 Realizzato del 2026-08-03

| Voce | Valore |
|---|---:|
| Trade chiusi | **7** (tutti S4) |
| Gross P&L | **+$145,34** |
| Costi (`cost_usd`) | −$2,59 |
| **Net P&L realizzato** | **+$142,75** |
| di cui S1 | **$0,00** (nessuna uscita S1 nella giornata) |

### 8.2 Per posizione

**Chiuse il 08-03, aperte prima:**

| Simbolo | Aperta | Entry | Exit | Qty | Net P&L |
|---|---|---:|---:|---:|---:|
| MSFT | 07-31 19:22 | 463,39 | 486,67 | 2,6566 | **+$61,60** |
| AMZN | 07-31 19:37 | 271,85 | 283,3499 | 4,5308 | **+$51,86** |
| MA | 07-31 17:22 | 574,14 | 575,68 | 2,1462 | **+$2,63** |
| | | | | **subtotale** | **+$116,09** |

**Aperte e chiuse il 08-03 (roundtrip intraday):**

| Simbolo | Entry | Exit | Durata | Qty | Net P&L |
|---|---:|---:|---|---:|---:|
| ORCL | 137,09 | 139,77 | 1h45 | 9,0654 | **+$23,61** |
| NVDA | 207,13 | 208,553 | 2h15 | 5,9984 | **+$8,29** |
| MSFT | 488,50 | 490,05 | 1h45 | 2,5434 | **+$3,70** |
| AMZN | 284,5917 | 282,60 | 1h45 | 4,3618 | **−$8,93** |
| | | | | **subtotale** | **+$26,67** |

**Aperte il 08-03 e ancora aperte:** ARM (S1, $334,09) e META (S4, $1.226,13).

### 8.3 Book e rendimento

| Voce | Valore | Fonte |
|---|---:|---|
| Equity chiusura 08-03 | **$109.704,03** | Alpaca (via `market_daily.jsonl`) |
| Equity chiusura 07-31 | $109.502,32 | idem |
| Δ giornata | **+$201,71 (+0,184%)** | calcolo |
| SPY del giorno | **+1,42%** | `market_daily.jsonl` |
| QQQ del giorno | +1,76% | idem |
| MTM del book aperto | **−$6,89** | `market_daily.jsonl` |
| Posizioni aperte a fine giornata | **49** ($34.645 di notional d'ingresso) | `trades WHERE exit_time IS NULL` |
| — di cui S1 | 35 ($23.669) | idem |
| — di cui S4 | 2 ($2.863) | idem |
| — di cui **`stop_strategy` NULL** | **12 ($8.112)** | **F-002**, già a ledger |
| NAV nel risk report 22:30 | $109.722,24 | `risk_reports` id 52 |
| Esposizione lorda | **29,84%** | idem |
| Herfindahl | 0,0227 | idem |

Il book ha reso +0,18% in una giornata a SPY +1,42%: con esposizione al 29,8% il beta atteso vale
~+0,42%, quindi c'è **underperformance anche corretta per esposizione**, coerente con la lettura
dell'Alpha-Miss Report (il book è dalla parte sbagliata della rotazione settoriale del giorno).

### 8.4 Costi e slippage

| Voce | Valore |
|---|---:|
| `cost_usd` totale sui 7 trade chiusi | $2,59 |
| `cost_usd` sui 2 trade ancora aperti | $0,39 |
| Costo medio per roundtrip | ~$0,37 |
| **Slippage misurato** | **NON DISPONIBILE** |

`trades.slippage_est` è **identico byte per byte a `cost_usd`** su tutte e 7 le righe chiuse
(es. trade 594: entrambi `0.6753113285185987`). Non è una misura di slippage: è il costo di
transazione modellato, ri-etichettato. Non esiste da nessuna parte un prezzo di riferimento al
momento della decisione contro cui misurare il fill. Vedi [DAY-010].

---

## 9. Analisi correttezza buy/sell

| Controllo | Esito | Evidenza |
|---|---|---|
| BUY generati solo quando consentito | **OK** | 6/6 BUY con `ema_pass=t`, `regime_mult=0.7`, weight ≤ 2%; i 5 S4 tutti con `signal_score ≥ 0.30` |
| SELL/exit generati correttamente | **OK con riserva** | 7/7 hanno `exit_mechanism` popolato (5 whipsaw, 1 no_signal, 1 portfolio_sell). Riserva: 2 SELL su sentiment **positivo** → [DAY-006] |
| Stop-loss rispettati | **N/A** | `stop_loss: 0.0` per decisione operativa del 2026-07-15; `stop_shadow_enabled: true`; 0 righe in `stop_decisions` il 08-03 |
| Signal flip rispettato | **OK** | ORCL +0,515→−0,343 ha prodotto l'uscita; il meccanismo funziona (la qualità dell'input è un altro problema, F-008) |
| Max holding days rispettato | **OK** | nessuna posizione ha superato il limite; le più vecchie (07-10) sono S1, che usa il rango momentum |
| Rebalance band rispettata | **OK** | 24 cicli, `constraints=0` in tutti; nessun ordine ha superato i cap |
| `hold_minimum_minutes: 90` | **OK** | tutte le uscite intraday a 105–135 min; guard registrato in log alle 16:52 |
| `exit_persistence_cycles: 2` (isteresi) | **OK, attivo** | tutte le uscite avvengono al 2° ciclo consecutivo di target=0, non al 1° |
| `s4_anti_whipsaw_confirm_cycles: 2` | **SHADOW, da design** | `would_suppress=True, streak=1/2` su **5/5** SELL whipsaw; documentato come measure-before-enforce in `trading.yaml:205-217` |
| Nessun ordine duplicato | **OK** | 13 `order_id` distinti; l'idempotenza per `signal_id` ha bloccato 8 tentativi ripetuti |
| Nessun ordine contrario ravvicinato senza rationale | **OK formalmente** | ogni SELL ha `reason` + `exit_mechanism`; ma AMZN e MSFT fanno SELL→BUY→SELL in una sessione → [DAY-006] |
| Nessun ordine su ticker non consentito | **OK** | 13/13 in `symbols.watchlist` |
| Nessun ordine fuori orario | **OK** | tutti fra 14:22 e 19:22, dentro 13:30–20:00 |
| Nessun trade su dati stale | **OK** | `SKIP_STALE` su SHEL (67,9h); `dropped N/M stale signals (age > 4h)` a ogni ciclo |
| Nessun trade su output LLM non valido | **OK** | 0 parse fail; PLTR +0,300 escluso perché `fallback_used=True` |
| Nessun trade con circuit breaker attivo | **OK** | `system:mode=paper`, nessuna chiave di halt, `consecutive_fallback=0` |
| Nessun trade da strategia disabilitata | **OK** | solo S1 e S4 in `strategies_run`; S2/S7 assenti |
| Coerenza paper/live | **OK** | paper verificato su 3 fonti indipendenti (env, yaml, Redis) |
| Idempotenza su retry Celery | **OK** | `P1-S4 SIGNAL_DUPLICATE_SKIP` per set Redis per-sessione, 8 attivazioni |
| Riconciliazione ordini↔fill↔posizioni | **OK** | `reconcile-fills-intraday` a :12/:27/:42/:57; tutti i trade chiusi hanno `exit_price` e `net_pnl`; 0 orfani |
| Roundtrip < 30 min | **NESSUNO** | minimo osservato 105 min |
| Pyramiding (>3 BUY senza SELL) | **NESSUNO** | guard P0-05 attivo su tutti i simboli in book |
| Ordini identici nello stesso minuto | **NESSUNO** | 14:22 → 3 SELL su simboli diversi; 16:52 → 2 BUY su simboli diversi |
| Score < 0,05 che generano ordini | **NESSUNO** | il minimo `signal_score` su un BUY è +0,307 |
| Decisione senza ordine (NO-ORDER) | **NESSUNO** | 13/13 BUY-SELL hanno `order_id` non vuoto |
| `fallback_used=True` su tutti i simboli | **NO** | 36% distribuito su tutta la giornata; Ollama sempre up |

---

## 10. Anomalie trovate

### [DAY-001] `llm_responses.eligible` marca come non-contributori i modelli che hanno formato il segnale (retry #90 non propagato) → **F-010**

* **Tipo:** Bug
* **Area:** LLM / Data
* **Evidenza:**
  * file/log/tabella: `src/llm/ensemble.py:283-284`, `src/workers/sentiment.py:297-307`,
    `src/store/pg_store.py:1755-1783`, tabelle `llm_responses` + `sentiment_signals`
  * timestamp: tutta la sessione 2026-08-03 14:15 → 19:46
  * query:
    ```sql
    SELECT s.fallback_used, r.model_id, r.eligible, count(*), round(avg(r.confidence)::numeric,3)
    FROM llm_responses r JOIN sentiment_signals s ON s.id = r.signal_id
    WHERE r.generated_at::date = '2026-08-03' GROUP BY 1,2,3;
    -- f | glm-5.2:cloud | f | 95 | 0.145      <-- hanno contribuito, marcati ineleggibili
    -- f | glm-5.2:cloud | t | 34 | 0.596
    ```
* **Descrizione:** con #90 `run_inference` ritenta `aggregate(..., min_confidence=0.0)` quando la
  chiamata a floor 0,4 restituisce `None`. Il retry riesce e i due modelli **entrano davvero nel
  segnale** (`fallback_used=False`, `model_id='ensemble:...'`). Ma `pg_store.log_llm_responses()`
  usa un `min_confidence: float = 0.4` hardcoded nella firma e scrive `eligible = confidence >=
  0.4`, senza sapere che il floor effettivo era 0. Risultato del 08-03: **95 dei 129 segnali
  ensemble (73,6%) hanno entrambi i modelli marcati `eligible=False` pur avendo prodotto lo score.**
* **Impatto:** `_FETCH_PER_MODEL_FOR_IC` (`pg_store.py:2185-2196` e `2240-2251`) filtra
  `s.fallback_used = FALSE AND r.eligible = TRUE`. Il ribilanciamento LOO-ICIR che scrive
  `ensemble:weights:current` (oggi `glm 0,6009 / gpt 0,3991`, `source: auto_apply`) gira quindi su
  **34 segnali su 202 (16,8%)**, e per costruzione solo sulla coda ad alta confidenza — un
  sottocampione **non casuale**. Quei pesi rientrano nel calcolo di ogni score successivo: il
  difetto è nel path live, non solo nel reporting. Espone anche `eligible_rate` della dashboard
  Quality (`quality_routes.py:63`), da cui deriva la lettura storica «ensemble affidabile solo
  17%», che è un artefatto di questo bug, non una misura.
* **Severità:** **High**
* **Confidenza:** **High** (codice letto, query eseguita, consumatori identificati)
* **Azione consigliata:** propagare a `log_llm_responses` il floor effettivamente usato
  dall'aggregatore (passare `min_confidence` dal chiamante, o `model_ids` di
  `AggregatedResult` come verità sui contributori). **Nessuna ritaratura**: è correttezza di misura,
  esente ai sensi della carta di osservazione.
* **Test/monitor consigliato:** test d'integrazione — due `ModelOutput` con confidence 0,2 e 0,3
  che innescano il retry #90 devono produrre due righe `eligible=TRUE`. Monitor giornaliero:
  `count(*) FILTER (WHERE fallback_used=false)` in `sentiment_signals` **deve** eguagliare
  `count(DISTINCT signal_id) FILTER (WHERE eligible)` in `llm_responses`.

### [DAY-002] Il floor di confidenza è asimmetrico: scarta un modello quando l'altro è sicuro, li usa entrambi quando nessuno lo è → **F-010**

* **Tipo:** Bug
* **Area:** LLM
* **Evidenza:**
  * file: `src/workers/sentiment.py:297-307`, `src/llm/ensemble.py:283-289`,
    `src/workers/sentiment.py:216-222`
  * timestamp: 72 segnali distribuiti su tutta la sessione
  * query: la stessa di [DAY-001]; incrocio con `sentiment_signals.model_id`
* **Descrizione:** tre regimi mutuamente incoerenti a parità di dati.
  **(a)** Entrambi i modelli ≥ 0,4 → ensemble a 2 modelli (34 casi).
  **(b)** Nessuno dei due ≥ 0,4 → il retry #90 abbassa il floor a 0 → ensemble a 2 modelli
  (95 casi).
  **(c)** Esattamente uno ≥ 0,4 → `aggregate()` restituisce un risultato a **1 solo modello**,
  taggato `single:<model>` con `fallback_used=True`, e **l'opinione dell'altro modello è
  buttata** (72 casi, 35,6% della giornata). Il retry non entra mai perché il risultato non è
  `None`. Il sistema è quindi *meno* inclusivo proprio quando ha un modello confidente.
  Caso concreto: segnale 6090 (AMZN, 14:15) → glm polarity 0,00 conf 0,10; gpt −0,30 conf 0,50 →
  score **−0,15** da gpt soltanto. Quel segnale ha guidato la SELL AMZN delle 14:22.
* **Impatto:** il 36% dei segnali del giorno è prodotto da metà dell'ensemble senza che sia mai
  stata presa una decisione esplicita in tal senso, ed è marcato `fallback_used=True`, il che lo
  **esclude sia dal path S4 sia dal calcolo LOO-ICIR**. La distinzione fra «single-model» e
  «fallback vero» esiste (`_is_full_fallback`, #128/#111) per il circuit breaker ma non per il
  consumo dei segnali. Questi 72 segnali entrano comunque nell'evidenza del periodo di
  osservazione come se fossero una categoria omogenea.
* **Severità:** **High**
* **Confidenza:** **High**
* **Azione consigliata:** ticket di correttezza per rendere il floor coerente fra i tre rami. La
  *scelta* del valore del floor è taratura e resta congelata; la coerenza fra i rami non lo è.
* **Test/monitor consigliato:** test parametrico sui tre regimi (0,2/0,3 · 0,5/0,6 · 0,2/0,5) che
  verifichi quanti `model_ids` finiscono in `AggregatedResult`. Monitor: rapporto
  `single:*` / totale segnali giornalieri.

### [DAY-003] `signal_id` NULL su 505/508 decisioni: la catena news→segnale→decisione→trade non è ricostruibile per chiave esterna → **F-011**

* **Tipo:** Bug
* **Area:** Signal / Orders / Data
* **Evidenza:**
  * tabella: `execution_decisions`, `trades`
  * timestamp: tutta la sessione
  * query:
    ```sql
    SELECT decision, count(*) tot, count(signal_id) with_sig
    FROM execution_decisions WHERE created_at::date='2026-08-03' GROUP BY 1;
    -- BUY            |   6 | 3
    -- SELL           |   7 | 0
    -- SKIP_THRESHOLD | 494 | 0
    -- SKIP_STALE     |   1 | 0
    ```
* **Descrizione:** solo **3 righe su 508** hanno la FK verso `sentiment_signals` popolata. Le
  decisioni 5810 (ORCL) e 6156 (META) citano nel testo di `reason` lo score esatto
  (`sentiment +0.515`, `+0.356`) e hanno `signal_score` valorizzato con il valore identico ai
  segnali 6131 e 6269 — il legame **esiste** ma è ricostruibile solo per matching numerico, non
  per FK. Idem su `trades`: i trade 640 (ORCL) e 645 (META) hanno `signal_id` NULL mentre 642/643/644
  ce l'hanno. Tutte e 7 le SELL hanno `signal_id` NULL pur avendo il punteggio nel testo.
  Da notare che `sentiment_signals.news_log_id` è invece popolato su **202/202** — l'anello
  news→segnale è integro; è l'anello segnale→decisione a rompersi.
* **Impatto:** il protocollo forense stesso prescrive analisi basate sul DB. Con questa FK vuota,
  ricostruire «quale notizia ha causato questo trade» richiede un join per testo e timestamp,
  cioè un'euristica. `portfolio_scheduler.py:1013-1029` documenta già che l'attribuzione di
  strategia usa la presenza di `signal_id` come euristica e che questa «silenziosamente etichetta
  un BUY S4 come S1 quando `signal_id` non è stato catturato». È la stessa radice.
  **Corrompe direttamente l'auditabilità dell'evidenza raccolta nelle prossime settimane.**
* **Severità:** **High**
* **Confidenza:** **High**
* **Azione consigliata:** ticket per popolare `execution_decisions.signal_id` su tutti i rami
  (BUY, SELL, SKIP_*) dallo stesso `_signal_ids` già risolto in
  `portfolio_scheduler.py:2308-2312`, e propagarlo a `trades`.
* **Test/monitor consigliato:** monitor giornaliero — `count(*) FILTER (WHERE signal_id IS NULL)`
  su `execution_decisions` con `signal_score IS NOT NULL` deve essere 0.

### [DAY-004] Metà delle righe scorate viene da articoli fan-out: 3 dei 6 BUY del giorno nascono da un unico pezzo su CoreWeave → **F-012**

* **Tipo:** Anomalia / Rischio
* **Area:** News / LLM / Signal
* **Evidenza:**
  * tabella: `news_log`, `sentiment_signals`, `execution_decisions`
  * timestamp: 15:29:30 (pubblicazione) → 16:37/16:52 (ordini)
  * query:
    ```sql
    SELECT n_tickers, count(*) FROM (
      SELECT url, count(DISTINCT ticker) n_tickers FROM news_log
      WHERE created_at::date='2026-08-03' GROUP BY url) x GROUP BY 1;
    -- 1→98, 2→17, 3→4, 4→6, 5→1, 6→2, 7→1, 10→1
    ```
* **Descrizione:** 32 articoli su 130 (25%) sono taggati a 2+ ticker e generano **104 delle 202
  righe scorate (51%)**. Ogni riga viene poi valutata come se l'articolo parlasse di quel ticker.
  Il caso più netto del giorno: **«CoreWeave Stock Jumps as AI Data-Center Demand Skyrockets Ahead
  of Q2 Earnings»** — un pezzo su CoreWeave, società **non in watchlist e non in book** — è taggato
  ad AAPL, AMZN, META, MSFT, NVDA e produce i segnali 6175 (AMZN +0,343), 6176 (MSFT +0,307),
  6178 (NVDA +0,388), cioè **3 dei 6 BUY della giornata**. Le `reason` persistite sono coerenti
  con il testo ma esplicitamente derivate («*Strong earnings from Amazon and its hyperscale peers…*»,
  «*…as highlighted in the article…*»). Un secondo caso: «Yen Intervention And Falling Oil Help
  Stocks…» taggato a **10 ticker** contemporaneamente. `extraction_method` è `source_metadata` su
  tutte le righe Benzinga: **il resolver deterministico non è coinvolto** — i tag arrivano dal
  provider e vengono accettati integralmente.
* **Impatto:** economicamente il 08-03 **non è costato**: i tre BUY da CoreWeave chiudono a
  +$3,06 netti aggregati (AMZN −8,93, MSFT +3,70, NVDA +8,29). Ma è un difetto di attribuzione
  che CLAUDE.md classifica come caso peggiore («un ticker sbagliato è l'errore peggiore»), e ha una
  conseguenza diretta sulla domanda di uscita 1 della carta: se metà dell'evidenza «news → segnale»
  è in realtà «articolo su un terzo → segnale», la risposta a *«esiste alpha nella news editoriale
  su questa watchlist?»* misura un'altra cosa.
* **Severità:** **High**
* **Confidenza:** **High**
* **Azione consigliata:** ticket di correttezza per registrare, per ogni riga di `news_log`, se il
  ticker è il **soggetto** dell'articolo o solo menzionato (il campo `extraction_method` esiste già,
  QT-03: serve un valore distinto per il fan-out), così che l'evidenza sia separabile a posteriori.
  Non propongo di filtrare — sarebbe taratura.
* **Test/monitor consigliato:** metrica giornaliera `fan_out_rate = (righe da URL multi-ticker) /
  righe totali` sulla dashboard Quality, e conteggio degli ordini la cui `reason` deriva da un
  articolo fan-out.

### [DAY-005] Un articolo su Oracle annulla in 58 secondi il segnale MSFT più forte della giornata (+0,710, conf 0,875) → **F-008**

* **Tipo:** Bug
* **Area:** News / Signal
* **Evidenza:**
  * tabella: `sentiment_signals` 6124 e 6130, `news_log` 6124 e 6130, `llm_responses`
  * timestamp: 15:30:34 → 15:31:32 (58 secondi)
  * snippet:
    ```
    6124 MSFT gdelt_gkg "Microsoft Stock Jumps as Azure Tops $100 Billion and Copilot
         Hits 30 Million Paid Seats"  -> score +0.710 conf 0.875
         (glm +0.85/0.90 eligible=t, gpt +0.75/0.85 eligible=t)
    6130 MSFT alpaca_benzinga "What Is Going on With ORACLE Stock on Monday?"
         -> score -0.056 conf 0.275   (glm -0.15/0.20, gpt -0.25/0.35)
    ```
* **Descrizione:** il ciclo portfolio legge **l'ultimo** segnale per simbolo. Alle 15:37 il segnale
  MSFT valido era il 6130 (−0,056), non il 6124 (+0,710). Il segnale più forte della giornata —
  ticker-specifico, entrambi i modelli d'accordo e confidenti (0,90 e 0,85) — è stato annullato 58
  secondi dopo da un articolo il cui titolo nomina **Oracle**, in cui MSFT compare solo per
  fan-out ([DAY-004]). Non esiste aggregazione fra segnali dello stesso simbolo nella stessa
  finestra: vince l'ultimo arrivato, indipendentemente da confidenza e specificità.
* **Impatto:** **nullo in dollari sul 08-03**, e l'ho verificato invece di assumerlo. MSFT chiude a
  487,65; il prezzo alle ~15:37 era ~487,25 (barra 15m 15:30, close 487,25). Un ingresso alle 15:37
  con lo stesso notional ($1.242) avrebbe reso 2,549 × (487,65 − 487,25) = **+$1,02** tenendo fino
  alla chiusura, contro i **+$3,70** effettivamente realizzati dall'ingresso più tardo delle 16:52.
  Il difetto, su questa occorrenza, **ha fatto guadagnare** $2,68. Resta un difetto: un trade può
  guadagnare denaro ed essere funzionalmente sbagliato.
* **Severità:** **Medium**
* **Confidenza:** **High**
* **Azione consigliata:** agganciato a **F-008** (stesso meccanismo già registrato sul lato uscita
  con ORCL). Solo evidenza, nessuna proposta di taratura.
* **Test/monitor consigliato:** log/metrica «segnale sovrascritto entro N minuti da uno di
  confidenza inferiore», con delta di score e delta di confidenza.

### [DAY-006] Churn intraday: AMZN e MSFT venduti, ricomprati e rivenduti nella stessa sessione; 2 SELL su sentiment positivo → **F-013**

* **Tipo:** Anomalia
* **Area:** Orders / Risk
* **Evidenza:**
  * tabella: `execution_decisions` 5707/5912/6093 (AMZN), 5709/5939/6110 (MSFT); `trades` 598/642, 597/644
  * timestamp: AMZN 14:22 SELL → 16:37 BUY → 18:22 SELL; MSFT 14:22 SELL → 16:52 BUY → 18:37 SELL
  * snippet:
    ```
    6093 AMZN SELL [whipsaw] ... (score=+0.196, age=1.1h)   <-- sentiment POSITIVO
    6110 MSFT SELL [whipsaw] ... (score=+0.013, age=0.6h)   <-- sentiment POSITIVO
    6139 NVDA SELL [whipsaw] ... (score=+0.000, age=0.4h)   <-- sentiment NULLO
    ```
* **Descrizione:** **4 dei 6 BUY del giorno sono stati chiusi lo stesso giorno.** Su AMZN e MSFT il
  ciclo completo è SELL → BUY → SELL in una sessione. Il meccanismo è che il peso target S4 è 2%
  sopra il gate 0,30 e **0% sotto**, senza banda intermedia: appena lo score scende sotto 0,30 la
  posizione viene azzerata, anche se lo score resta **positivo**. Da qui i 2 SELL su sentiment
  positivo (+0,196 e +0,013) e 1 su score esattamente nullo. I guard temporali hanno fatto il loro
  lavoro (`hold_minimum_minutes=90` rispettato su tutte, isteresi 2 cicli rispettata su tutte), ma
  agiscono sulla *tempistica*, non sulla soglia. Il gate addizionale
  `s4_anti_whipsaw_confirm_cycles: 2` avrebbe soppresso **5 SELL su 5**
  (`would_suppress=True, streak=1/2` su tutte) ma è in shadow per design.
* **Impatto:** **$10,07 di costo attribuito**, controfattuale corto (stesso giorno, stesso
  strumento, stessa sessione), calcolato sulla sola penalità di rientro:
  - AMZN: venduta a 283,3499 alle 14:22, ricomprata a 284,5917 alle 16:37 → +$1,2418/az. su
    4,3618 az. = **$5,42**
  - MSFT: venduta a 486,67 alle 14:22, ricomprata a 488,50 alle 16:52 → +$1,83/az. su 2,5434 az.
    = **$4,65**

  A questo si somma il costo d'uscita anticipata già calcolato altrove ($8,89 aggregato sui 4
  roundtrip, di cui $19,54 su ORCL già registrati come **F-008**): non lo riconteggio qui.
* **Severità:** **Medium**
* **Confidenza:** **High** (prezzi di fill reali dal DB, nessuna stima)
* **Azione consigliata:** **nessuna** durante l'osservazione — la banda d'uscita è taratura e la
  carta la congela. Questa registrazione serve esattamente ad alimentare il log del gate shadow con
  numeri in dollari.
* **Test/monitor consigliato:** metrica giornaliera `same_session_reentry_cost` = Σ (prezzo di
  ri-acquisto − prezzo di vendita) × qty per ogni coppia SELL→BUY sullo stesso simbolo nella stessa
  sessione.

### [DAY-007] `risk_reports.combined_drawdown` (1,24%) incoerente con il drawdown che genera l'ALERT (13,9%) → **F-003**

* **Tipo:** Bug
* **Area:** Risk / PnL
* **Evidenza:**
  * tabella: `risk_reports` id **52**
  * timestamp: 2026-08-03 22:30:01 UTC
  * snippet: `combined_drawdown = 0.012429` (1,24%) nella colonna dedicata, mentre
    `alerts = [{"level":"ALERT","message":"Strategy portfolio drawdown 13.9% exceeds 10%",
    "strategy_id":"portfolio"}]` — **11× di scarto nello stesso record**
* **Descrizione:** ricorrenza esatta del difetto registrato il 2026-07-31 (risk_report id 49, stessi
  valori). L'alert nasce da `per_strategy_metrics->portfolio->drawdown`, la colonna
  `combined_drawdown` è calcolata altrove. Nessuna delle due è dichiarata autorevole.
* **Impatto:** durante il periodo di osservazione il drawdown è una delle grandezze da leggere.
  Due valori a un ordine di grandezza di distanza nello stesso record rendono la lettura arbitraria.
  Nessuna perdita diretta.
* **Severità:** **Medium**
* **Confidenza:** **High**
* **Azione consigliata:** agganciato a **F-003** (2ª occorrenza).
* **Test/monitor consigliato:** assert in `risk_report`: |combined_drawdown −
  per_strategy_metrics.portfolio.drawdown| < 0,01, altrimenti WARNING esplicito.

### [DAY-008] `decay_monitor` produce metriche identiche per S1, S2 e S4, inclusa S2 che non ha mai tradato → **F-004**

* **Tipo:** Bug
* **Area:** Ops / Data
* **Evidenza:**
  * log: `docker compose logs worker`, 2026-08-03 21:00:00
  * snippet:
    ```
    DECAY CRITICAL [S1]: IC dropped 89% from 0.035 to 0.004
    DECAY CRITICAL [S2]: IC dropped 90% from 0.042 to 0.004
    DECAY CRITICAL [S4]: IC dropped 86% from 0.028 to 0.004
    DECAY CRITICAL [S1|S2|S4]: Sharpe below 50% of baseline: -6.98 vs {0.95|1.10|0.80}
    ```
* **Descrizione:** IC attuale **0,004 identico** per le tre strategie e Sharpe **−6,98 identico**:
  `_fetch_actual_metrics` (`src/workers/decay_monitor_task.py:52-66`) non filtra per `strategy_id`.
  IC/hit-rate vengono da `sentiment_signals` (dominio S4), Sharpe/drawdown da
  `portfolio_daily_state` (book intero), poi applicati a tre baseline diverse. **S2 è disabilitata**
  (0% di allocazione) e non ha mai una riga in `trades`, eppure genera 4 alert CRITICAL.
* **Impatto:** 8 alert CRITICAL al giorno, di cui almeno 4 su una strategia inesistente. Rumore che
  desensibilizza, e rischio diretto sulla domanda di uscita 2 della carta se qualcuno consultasse
  `decay_reports` credendo di leggere metriche S1-specifiche.
* **Severità:** **Medium**
* **Confidenza:** **High**
* **Azione consigliata:** agganciato a **F-004** (2ª occorrenza).
* **Test/monitor consigliato:** test che verifichi che due strategie con trade disgiunti producano
  metriche `actual` diverse.

### [DAY-009] Telemetria di ciclo fuorviante: `orders_count` = ordini target, non inviati; il log hold-minimum stampa i candidati invece degli scartati → **F-014**

* **Tipo:** Bug
* **Area:** Ops / Data
* **Evidenza:**
  * tabella/codice: `portfolio_cycles`, `src/workers/portfolio_scheduler.py:2163-2170`
  * timestamp: tutti i 24 cicli; il caso del log alle 16:52:05
  * snippet:
    ```sql
    SELECT sum(orders_count) FROM portfolio_cycles WHERE timestamp::date='2026-08-03';  -- 1169
    ```
    ```
    16:52:05 Hold minimum (90 min): skipped 1 SELL order(s) for recently-bought: ['AMZN','ARM','ORCL']
    ```
    ```python
    _skipped = _before_hold - len(result.final_orders)   # = 1
    log.info("... skipped %d SELL order(s) for recently-bought: %s", _hold_min, _skipped,
             sorted(_recently_bought))                    # stampa TUTTI i recently_bought
    ```
* **Descrizione:** due trappole distinte per chi legge a posteriori. **(a)** `portfolio_cycles.
  orders_count` somma **1.169** per la giornata, ma gli ordini realmente inviati sono **13**: il
  campo conta gli ordini *target* del combiner (47–51 per ciclo, quasi tutti no-op). Il conteggio
  reale (`submitted`) è solo nel risultato del task Celery, non persistito. **(b)** il log
  hold-minimum dichiara «skipped 1» e poi elenca 3 simboli: il numero è quello scartato, la lista è
  l'insieme dei candidati.
* **Impatto:** nessuna perdita. Ma un'analisi che leggesse `portfolio_cycles` come registro degli
  ordini sbaglierebbe di due ordini di grandezza, e il log hold-minimum attribuirebbe blocchi a
  simboli mai bloccati. Rientra pienamente nella categoria «l'evidenza raccolta è sbagliata».
* **Severità:** **Low**
* **Confidenza:** **High**
* **Azione consigliata:** persistere `submitted` in `portfolio_cycles` (o rinominare `orders_count`
  in `target_orders_count`) e stampare nel log l'intersezione effettiva.
* **Test/monitor consigliato:** assert `orders_count >= submitted` con entrambi i campi persistiti;
  riconciliazione giornaliera `sum(submitted)` vs `count(*)` in `execution_decisions` con
  `order_id` non vuoto.

### [DAY-010] `trades.slippage_est` è una copia di `cost_usd`: la qualità di esecuzione non è misurata → **F-015**

* **Tipo:** Bug
* **Area:** PnL / Data
* **Evidenza:**
  * tabella: `trades`, righe 594, 597, 598, 640, 642, 643, 644
  * timestamp: tutti gli exit del 2026-08-03
  * snippet: trade 594 → `slippage_est = 0.6753113285185987`,
    `cost_usd = 0.6753113285185987` (identici a 16 cifre); trade 641 (aperto) →
    `slippage_est = NULL`, `cost_usd = 0.171`
* **Descrizione:** le due colonne non sono indipendenti: `slippage_est` viene valorizzata all'exit
  con il costo di transazione modellato. Non esiste in `execution_decisions` un prezzo atteso o di
  arrivo al momento della decisione, quindi **non c'è alcun riferimento contro cui misurare lo
  scostamento del fill**. Il campo dichiara di misurare una cosa e ne contiene un'altra.
* **Impatto:** qualunque analisi di execution quality sul periodo di osservazione (slippage per
  size, per orario, per liquidità) è impossibile e, se condotta su questa colonna, restituirebbe il
  modello di costo invece della realtà. La distinzione conta perché tutti gli ingressi sono ordini
  **market** con notional ~$1.240 su titoli molto liquidi: lo slippage vero è probabilmente
  piccolo, ma questo è un'ipotesi, non una misura.
* **Severità:** **Medium**
* **Confidenza:** **High**
* **Azione consigliata:** ticket per catturare il prezzo di riferimento (last/mid) al momento della
  submission in `execution_decisions`, e calcolare `slippage_est` come `fill − reference`.
* **Test/monitor consigliato:** assert che `slippage_est <> cost_usd` su almeno una riga del
  campione giornaliero, altrimenti WARNING «slippage non misurato».

### [DAY-011] Il fetch del benchmark SPY fallisce sistematicamente (limite di sottoscrizione SIP), senza alcun alert → **F-016**

* **Tipo:** Rischio
* **Area:** Data / Ops
* **Evidenza:**
  * log: `docker compose logs worker`, ricorrente per tutto il 2026-08-03 (84 occorrenze rilevate
    nella finestra di retention), 6 tentativi consecutivi a ogni snapshot
  * codice: `src/portfolio/spy.py:102`, chiamato da `src/workers/mobile_monitor_task.py:51`
  * snippet: `SPY benchmark fetch failed: {"message":"subscription does not permit querying
    recent SIP data"}`
* **Descrizione:** il piano dati Alpaca non consente di leggere barre SIP recenti; la funzione
  cattura l'eccezione, logga WARNING e restituisce `None`. `mobile_monitoring/performance.py:214-224`
  gestisce il `None` azzerando `spy_return`, `benchmark_return` e `alpha` e registrando una
  degradazione — quindi **non c'è crash e non c'è dato inventato**, il che è corretto. Ma la
  condizione dura da tutto il giorno e non produce alert: è un guasto permanente mascherato da
  warning ripetuto.
* **Impatto:** il confronto con il benchmark è **assente dal read model mobile**. La domanda di
  uscita 2 della carta (*P&L economico di S1 confrontato con SPY*) usa una via diversa —
  `market_daily.jsonl` del 08-03 riporta correttamente `"spy": 0.0142` — quindi **la carta non è
  bloccata**. Resta che una delle due vie di lettura del benchmark è morta e nessuno viene avvisato.
* **Severità:** **Low**
* **Confidenza:** **High**
* **Azione consigliata:** far emergere la degradazione come alert una-tantum invece che come
  warning per-minuto, oppure allineare la richiesta al feed consentito dalla sottoscrizione.
* **Test/monitor consigliato:** alert se `portfolio_monitor_snapshots.degradations` contiene
  `benchmark` per più di N snapshot consecutivi.

### [DAY-012] La rilevazione di regime delle 07:00 fallisce ma il task viene registrato come `succeeded` → **F-017**

* **Tipo:** Rischio
* **Area:** Ops
* **Evidenza:**
  * log: `docker compose logs worker-inference`, 2026-08-03 07:00:04
  * snippet:
    ```
    07:00:04,179 ERROR  Failed to fetch macro data for regime detection:
                        Server error '500 Internal Server Error' ... series_id=VIXCLS
    07:00:04,608 INFO   Task ...regime.detect_regime[...] succeeded in 4.59s: None
    ```
* **Descrizione:** il run primario pre-market non ha scritto `regime:current`. Il task chiude come
  `succeeded` con risultato `None`: dal punto di vista di Celery e di qualunque monitor basato sullo
  stato dei task, **il fallimento è invisibile**. Il safety-net P0-09 delle 13:30 ha poi risolto
  correttamente (`sideways ×0.7` in 52 s) e tutti i 24 cicli hanno usato `regime_mult=0.7`.
* **Impatto:** **nullo il 08-03** grazie al safety-net, che ha funzionato esattamente come
  progettato. Il rischio è che se fallissero entrambi i run, i cicli userebbero il fallback
  `high_vol ×0.2` (incidente già osservato il 2026-06-23) senza che nessun segnale d'errore fosse
  mai emesso.
* **Severità:** **Low**
* **Confidenza:** **High**
* **Azione consigliata:** far fallire il task, o emettere un alert, quando `detect_regime` non
  riesce a scrivere `regime:current`.
* **Test/monitor consigliato:** alert se `regime:current` ha età > 24h all'apertura del mercato.

### [DAY-013] Il token del bot Telegram compare in chiaro nei log a livello INFO → **F-018**

* **Tipo:** Rischio
* **Area:** Ops
* **Evidenza:**
  * log: `docker compose logs worker-inference`, ogni 5 secondi per tutto il 2026-08-03
  * snippet (token redatto qui): `HTTP Request: GET
    https://api.telegram.org/bot<TOKEN>/getUpdates?offset=... "HTTP/1.1 200 OK"`
  * la stessa URL con token compare anche nel WARNING di consegna fallita (`sendMessage`)
* **Descrizione:** il logger HTTP di `httpx` stampa l'URL completo del poller Telegram, che
  contiene il bot token, **17.280 volte al giorno** (ogni 5 s). Chiunque abbia accesso ai log dei
  container ha il token del bot.
* **Impatto:** nessuno sul trading. È un'esposizione di credenziale nei log, che permetterebbe di
  inviare messaggi come il bot e — dato che il bot serve il flusso di approvazione con inline
  keyboard — di interagire con quel flusso.
* **Severità:** **Medium**
* **Confidenza:** **High**
* **Azione consigliata:** portare `httpx` a WARNING nella configurazione di logging, o redigere il
  segmento `/bot<token>/` nell'URL.
* **Test/monitor consigliato:** grep in CI sui log di esempio per il pattern `api.telegram.org/bot[0-9]`.

---

## 11. False positive e aree risultate corrette

Elenco di ciò che ho controllato e che **non** è un problema, per evitare che venga ri-segnalato:

1. **`portfolio_cycles.constraints_fired` vuoto in tutti i 765 cicli dal 2026-06-15.** Sembra un
   enforcer mai eseguito; non lo è. Il log conferma a ogni ciclo `Portfolio cycle complete: …
   constraints=0`, e `orchestrator.py:314-317` mostra che `_enforcer.enforce()` viene invocato
   ogni volta che ci sono ordini e NAV > 0. Con esposizione al 29,8% contro cap ben più larghi,
   **zero violazioni è il risultato corretto**, non un'omissione.
2. **`s4_anti_whipsaw_confirm_cycles: 2` in shadow.** Non è un flag dimenticato: `trading.yaml:205-217`
   lo documenta come gate measure-before-enforce, additivo rispetto a `exit_persistence_cycles`
   (che è invece **attivo** e ha effettivamente ritardato tutte le uscite al 2° ciclo). Le 5
   annotazioni `would_suppress=True` del giorno sono esattamente il dato che quel gate deve
   raccogliere.
3. **Fallimento FRED delle 07:00.** Coperto dal safety-net delle 13:30 (P0-09), che ha funzionato.
   L'unico residuo è la mancanza di segnalazione → [DAY-012].
4. **`fallback_used=True` sul 36% dei segnali.** Non è un'indisponibilità di Ollama: entrambi i
   modelli hanno risposto 202/202 volte, 0 timeout. Il FinBERT vero è entrato **1 volta**.
5. **Nessun ciclo prima delle 14:07 con mercato aperto dalle 13:30.** È il beat
   (`hour="14-21"`), non un guasto. Va conosciuto, non corretto.
6. **`S4: dropped 32/32 stale signals` al primo ciclo.** Corretto: il worker sentiment non gira di
   notte, quindi all'apertura tutti i segnali superstiti hanno > 4h. Il guard di freschezza
   funziona.
7. **`SKIP_STALE` su SHEL con segnale di 67,9h.** Comportamento corretto e ben documentato nella
   `reason`.
8. **Guard anti-pyramiding e idempotenza.** 24 attivazioni/ciclo del primo e 8 del secondo: hanno
   impedito ordini duplicati che, senza di essi, sarebbero stati inviati (NVDA sarebbe stato
   comprato 6 volte sullo stesso `signal_id`).
9. **Il campo `execution_decisions.score`.** Vale `0.02` su tutti i BUY S4: **non** è lo score del
   segnale (che sta in `signal_score`) ma il peso target di portafoglio. Il nome trae in inganno ma
   il dato è corretto e la colonna giusta esiste. Segnalato in §12 come trappola di lettura, non
   come bug.
10. **`sentiment_signals.news_log_id` popolato su 202/202.** L'anello news→segnale è integro; il
    problema di provenienza è a valle ([DAY-003]).
11. **Riconciliazione fill.** Tutti i 7 trade chiusi hanno `exit_price`, `net_pnl`, `cost_usd` e
    `exit_order_id`; nessun ordine orfano, nessuna posizione non riconciliata.

---

## 12. Dati mancanti o non accessibili

| Cosa | Stato | Query/azione che servirebbe |
|---|---|---|
| **API REST locale** | **NON ACCESSIBILE** — tutti gli endpoint (`/api/decisions`, `/trades`, `/signals`, `/positions`, `/orders`) rispondono **HTTP 403 `{"detail":"Invalid or expired JWT token"}`** con il bearer fornito nel prompt. L'intera analisi è stata condotta **direttamente su PostgreSQL, Redis e i log Docker**, che sono la fonte autorevole. | Rigenerare il token di servizio, oppure aggiornare il prompt del cron con un token valido |
| **Latenza per chiamata LLM** | Non registrata: `llm_responses` non ha colonne di timing. Disponibile solo la durata del task batch (mediana ~113 s) | Aggiungere `latency_ms` a `llm_responses` |
| **Slippage reale** | Non misurabile: nessun prezzo di riferimento alla submission → [DAY-010] | Aggiungere `reference_price` a `execution_decisions` |
| **Ordini inviati per ciclo** | Non persistiti: presenti solo nel risultato del task Celery → [DAY-009] | Aggiungere `submitted_count` a `portfolio_cycles` |
| **Conteggi grezzi per-ciclo dell'ingest** | Non ricostruibili: `ingestion_stats_daily` è un UPSERT additivo (F-007) | Log per-ciclo di fetched/queued/duplicates |
| **Riga `reuters` in `ingestion_stats_daily`** | Presente (fetched 4, queued 4, `updated_at` 07:04:24) benché il task RSS risulti disabilitato dal 2026-07-03. **Non ho identificato quale processo la scriva.** 0 righe in `news_log`, quindi nessun impatto sui segnali | `grep -rn "reuters" src/` e verifica dello scheduler host |
| **Prezzi intraday storici** | Disponibili (barre 15m da Alpaca, usate per il controfattuale MSFT di [DAY-005]) | — |
| **Trappole di lettura note** | `execution_decisions.score` = peso target, non score del segnale; `portfolio_cycles.orders_count` = ordini target; `trades.slippage_est` = costo modellato | Documentare nello schema |

---

## 13. Raccomandazioni immediate

Tutte di **sola correttezza/misura**. Nessuna proposta di taratura, in ottemperanza alla carta di
osservazione.

1. **Rigenerare il token dell'API** usato dal cron forense: oggi l'analisi ha retto solo perché il
   DB è accessibile. Se domani cambiasse anche quello, il report sarebbe "non verificabile".
2. **Correggere `llm_responses.eligible`** ([DAY-001]). È la raccomandazione con la priorità più
   alta: sta corrompendo i pesi ensemble **live** attraverso LOO-ICIR, cioè sta alterando gli score
   proprio mentre li stiamo osservando. Ogni giorno che passa aggiunge evidenza calcolata su un
   sottocampione distorto.
3. **Popolare `execution_decisions.signal_id`** su tutti i rami ([DAY-003]). Senza questo, il
   protocollo forense «solo DB» prescritto da questo stesso cron non è eseguibile.
4. **Marcare il fan-out multi-ticker** in `news_log.extraction_method` ([DAY-004]) — non filtrarlo,
   solo renderlo separabile a posteriori. Senza, la domanda di uscita 1 della carta risponde a una
   domanda diversa da quella posta.
5. **Non toccare** il gate 0,30, la banda d'uscita, `hold_minimum_minutes`, `exit_persistence_cycles`
   né `s4_anti_whipsaw_confirm_cycles`. Il churn di [DAY-006] è vistoso e costoso ma è taratura:
   va **misurato** per 40 giorni, non aggiustato.

---

## 14. Test o monitor da aggiungere

| # | Tipo | Descrizione | Copre |
|---|---|---|---|
| M-1 | Monitor giornaliero | `count(*) FILTER (WHERE fallback_used=false)` in `sentiment_signals` **=** `count(DISTINCT signal_id) FILTER (WHERE eligible)` in `llm_responses` | [DAY-001] |
| T-1 | Test integrazione | Due `ModelOutput` a confidence 0,2/0,3 → retry #90 → **due** righe `eligible=TRUE` | [DAY-001] |
| T-2 | Test parametrico | Tre regimi di confidenza (0,2/0,3 · 0,5/0,6 · **0,2/0,5**) → verificare `len(model_ids)` in `AggregatedResult` | [DAY-002] |
| M-2 | Monitor giornaliero | Righe in `execution_decisions` con `signal_score IS NOT NULL AND signal_id IS NULL` deve essere **0** | [DAY-003] |
| M-3 | Metrica Quality | `fan_out_rate` = righe da URL multi-ticker / righe totali; + n. ordini originati da articoli fan-out | [DAY-004] |
| M-4 | Log/metrica | «Segnale sovrascritto entro N min da uno di confidenza inferiore», con Δscore e Δconfidence | [DAY-005] |
| M-5 | Metrica giornaliera | `same_session_reentry_cost` = Σ (prezzo re-buy − prezzo sell) × qty sulle coppie SELL→BUY intra-sessione | [DAY-006] |
| A-1 | Assert | \|`combined_drawdown` − `per_strategy_metrics.portfolio.drawdown`\| < 0,01 | [DAY-007] |
| T-3 | Test | Due strategie con trade disgiunti devono produrre metriche `actual` **diverse** in `decay_monitor` | [DAY-008] |
| A-2 | Assert/riconciliazione | `sum(submitted)` dei cicli **=** `count(*)` in `execution_decisions` con `order_id` non vuoto | [DAY-009] |
| A-3 | Assert | `slippage_est <> cost_usd` su almeno una riga del campione giornaliero | [DAY-010] |
| A-4 | Alert | `degradations` contiene `benchmark` per > N snapshot consecutivi | [DAY-011] |
| A-5 | Alert | Età di `regime:current` > 24h all'apertura del mercato | [DAY-012] |
| C-1 | Check CI | grep sui log di esempio per `api.telegram.org/bot[0-9]` | [DAY-013] |

---

## 15. Ticket tecnici suggeriti

Solo difetti di **correttezza**, conformi all'esenzione della carta di osservazione (§«Cosa è
esente»). Per ciascuno ho applicato il test *«se non lo correggo, l'evidenza che raccolgo nelle
prossime settimane è sbagliata?»*.

| Ticket | Titolo | Priorità | Test di esenzione |
|---|---|---|---|
| **T-01** | Propagare il floor effettivo del retry #90 a `log_llm_responses`; `eligible` deve riflettere i contributori reali | **P0** | **Sì** — i pesi LOO-ICIR live girano oggi sul 17% dell'evidenza, su un sottocampione distorto |
| **T-02** | Rendere coerente il floor di confidenza fra i tre rami dell'aggregatore (il valore del floor resta congelato) | **P1** | **Sì** — il 36% dei segnali del giorno è prodotto da metà ensemble senza decisione esplicita |
| **T-03** | Popolare `execution_decisions.signal_id` e `trades.signal_id` su tutti i rami (BUY/SELL/SKIP) | **P0** | **Sì** — senza FK la catena di provenienza non è ricostruibile e l'attribuzione di strategia resta euristica |
| **T-04** | Distinguere in `news_log.extraction_method` il ticker-soggetto dal ticker-menzionato (fan-out) | **P1** | **Sì** — metà dell'evidenza «news→segnale» misura articoli su terzi |
| **T-05** | Persistere `submitted_count` in `portfolio_cycles`; correggere il log hold-minimum | **P2** | **Sì** — chi legge `orders_count` sbaglia di due ordini di grandezza |
| **T-06** | Catturare `reference_price` alla submission e calcolare uno slippage reale | **P2** | **Sì** — la execution quality del periodo non è misurabile |
| **T-07** | Allineare `combined_drawdown` al drawdown che genera l'alert (già noto, 2ª occorrenza) | **P2** | Sì — il drawdown è una grandezza da leggere durante l'osservazione |
| **T-08** | `decay_monitor`: filtrare le metriche `actual` per `strategy_id`; escludere le strategie disabilitate | **P2** | Sì — 8 alert CRITICAL/giorno, di cui 4 su una strategia inesistente |
| **T-09** | Alert (non warning ripetuto) su fallimento del regime detector e del benchmark SPY | **P3** | No — nessun impatto sull'evidenza; ticket di igiene operativa |
| **T-10** | Redigere il bot token Telegram dai log `httpx` | **P2** | No — sicurezza, non evidenza |

---

## 16. Stato sistema

| Componente | Stato 2026-08-03 |
|---|---|
| **Ollama (ollama.com)** | **UP — 0 ore di downtime.** 404 risposte su 404 richieste (202 per modello), **0 timeout**, 0 output invalidi |
| **Coppia di modelli attiva** | `glm52,gptoss` — Redis `config:sentiment_llm_models` corretta, **nessuna regressione a "all"** |
| **Pesi ensemble** | `glm-5.2:cloud 0,6009 / gpt-oss:20b-cloud 0,3991`, `source: auto_apply` — **calcolati su evidenza distorta**, vedi [DAY-001] |
| **FinBERT fallback (vero)** | **1 / 202 segnali = 0,5%**. Sulle 6 decisioni di BUY del giorno: **0%** |
| **"fallback_used" complessivo** | 73 / 202 = 36,1%, di cui 72 letture single-model (non outage) e 1 FinBERT |
| **Circuit breaker sizing** | Mai scattato. `fallback_counters.consecutive_fallback = 0`, `reset_at` 19:46:02 |
| **Regime** | `sideways ×0,7`. Run 07:00 **fallito** (FRED 500 su VIXCLS), safety-net 13:30 riuscito in 52 s |
| **Worker restart** | **0.** `alembic-worker-1`, `worker-inference-1`, `beat-1`, `api-1` up da 4 giorni; `postgres-1`, `redis-1` up da 13 giorni. Nessun `WorkerLostError` |
| **Cicli portfolio** | 24/24 completati, cadenza 15 min esatta 14:07→19:52, 0 eccezioni |
| **Errori applicativi** | 1 ERROR (FRED 500, 07:00). Nessun `Traceback` in giornata |
| **Warning ricorrenti** | `SPY benchmark fetch failed` (permanente, [DAY-011]); `S1: dropped 2 sparse/stale-tailed ticker(s) ['AZN','SPCX']` ×24; `P0-05 pyramiding guard` ×24 per ~40 simboli |
| **Alert consegnati** | 1 RISK ALERT (drawdown 13,9%) + 8 DECAY CRITICAL. **Nessun errore di consegna Telegram il 08-03** (il 400 Bad Request di F-005 è del 07-31; l'unico WARNING Telegram del 08-03 riguarda 2 `Connection reset by peer` sul poller, auto-recuperati) |
| **Modalità broker** | **PAPER**, verificata su 3 fonti indipendenti |
| **Halt / kill-switch** | Nessuna chiave di halt in Redis. `system:mode = paper`. Kill-switch non attivato |

---

## Appendice — Aggiornamenti al ledger delle evidenze

`docs/evidence/findings.json`, in sola aggiunta:

| Finding | Azione | Costo |
|---|---|---|
| **F-003** | +1 occorrenza (2ª) — [DAY-007] | `null` (difetto di misura) |
| **F-004** | +1 occorrenza (2ª) — [DAY-008] | `null` (difetto di misura) |
| **F-008** | +1 occorrenza (2ª, stesso giorno, evento distinto: MSFT) — [DAY-005] | **`0.0`** — controfattuale calcolato: +$1,02 contro +$3,70 realizzati, il difetto non ha fatto perdere denaro |
| **F-010** | **nuovo** — [DAY-001] + [DAY-002], stessa radice (retry #90 non propagato) | `null` |
| **F-011** | **nuovo** — [DAY-003] | `null` |
| **F-012** | **nuovo** — [DAY-004] | `null` (i 3 BUY da fan-out chiudono a +$3,06) |
| **F-013** | **nuovo** — [DAY-006] | **$10,07** attribuito |
| **F-014** | **nuovo** — [DAY-009] | `null` |
| **F-015** | **nuovo** — [DAY-010] | `null` |
| **F-016** | **nuovo** — [DAY-011] | `null` |
| **F-017** | **nuovo** — [DAY-012] | `null` |
| **F-018** | **nuovo** — [DAY-013] | `null` |

**Non ho aggiunto occorrenze** a F-001 (copertura news), F-002 (attribuzione strategia NULL), F-008
sul caso ORCL e F-009 (gate vs magnitudine): l'Alpha-Miss Report del 2026-08-03 le ha già
registrate per questa data e un secondo inserimento gonfierebbe i costi cumulati. Dove ho prodotto
evidenza di supporto (§5.4 per F-009, §4.1 per F-007, §8.3 per F-002) l'ho citata nel testo senza
toccare il ledger.
