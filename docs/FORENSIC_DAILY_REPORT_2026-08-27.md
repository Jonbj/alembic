# Forensic Daily Report — 2026-08-27

**Sessione:** giovedì 2026-08-27, RTH 13:30–20:00 UTC (EDT, UTC−4)
**Modalità:** read-only. Nessun ordine inviato, nessun worker avviato, nessuna pipeline rieseguita.
**Timezone:** `src/workers/celery_app.py:51-52` → `timezone="UTC"`, `enable_utc=True`. Tutti i timestamp di questo report sono UTC. **Non c'è ambiguità sul fuso del sistema**, ma c'è un difetto DST nelle finestre beat (vedi [DAY-007]).
**Ambiente broker:** `portfolio_monitor_snapshots.broker_environment = 'paper'`, `mode = 'paper'`, `source = 'alpaca_paper'` su tutte le 86 righe con provenienza. **Confermato paper, non live.**
**Motore di esecuzione:** `config/trading.yaml:142` → `engine: portfolio`. Tutti gli 8 ordini della giornata portano un `tick_time` allineato ai cicli `:07/:22/:37/:52` → emessi da `portfolio-cycle`, nessuno da `run-execution`.

---

## 1. Executive summary

La catena end-to-end ha funzionato: 2.616 item raccolti, 133 scorati, 501 decisioni di skip tracciate,
8 ordini (5 BUY, 3 SELL) tutti eseguiti e riconciliati, NAV 109.965,05 → 110.038,29 (+73,24 $, +0,067%)
contro SPY +0,66%. Nessun ordine duplicato, nessun ordine fuori orario, nessun ordine senza risk check,
nessun roundtrip sotto i 30 minuti, idempotenza attiva (1 `SIGNAL_DUPLICATE_SKIP`).
Ma la giornata è stata la più dispersa della finestra (σ 3,49%, 14 mover oltre il 3%) e il sistema ne ha
catturato +16 $ su una sleeve S4 da 75 k$. Il difetto dominante è di **selezione del segnale**: S4 tiene il
segnale più *recente*, non il più *forte*, e con articoli fan-out multi-ticker ogni 15 minuti il riferimento
di un titolo viene sovrascritto da un market-wrap a punteggio 0,000. Su CRM (+22,58%, miglior titolo della
watchlist) questo ha prodotto tre round trip e −12,27 $ realizzati+MTM su un controfattuale buy-and-hold di
+22,53 $. Tre difetti nuovi o non ancora registrati emergono da questa sessione: (a) il **guard di divergenza
d'ensemble è aggirabile** — `ensemble_std` è calcolato solo fra i modelli eleggibili, quindi vale 0,000 esatto
proprio quando i due modelli divergono di 0,60–0,85 (4 casi oggi, incluso PANW +0,6375, terzo punteggio del
giorno); (b) la **suite di test scrive nel DB di produzione** — 10 righe fixture in
`portfolio_monitor_snapshots` incluse le ultime della giornata, quindi un consumatore del "last snapshot"
legge un portafoglio inventato; (c) l'**output strutturato del modello non è validato** (un enum con uno
zero-width space dentro). Il trigger documentato di revisione a −15% ha fatto firing su 2 posizioni
(AMAT −19,4%, WDC −16,2%) e `mobile_events` è **vuota da sempre**: nessun alert è mai stato consegnato.

## 2. Verdict finale

**ANOMALIE SIGNIFICATIVE.**

Non "processo non affidabile": la catena money-path è coerente, riconciliata e conforme alle sue regole —
gli 8 ordini sono giustificati, tracciati, eseguiti al prezzo atteso e le posizioni quadrano. Non "OK con
warning": 21 anomalie di cui 3 nuove, con due difetti che rendono *sbagliata l'evidenza raccolta* e non solo
il P&L del giorno — il guard di divergenza aggirato ([DAY-004]) e le righe di test in produzione
([DAY-006]). Il canale di allerta è morto ([DAY-012]) e i log della seduta non esistono più ([DAY-010]),
quindi la ricostruzione di oggi è stata possibile solo grazie ai ledger append-only in Postgres.

---

## 3. Timeline del 2026-08-27 (UTC)

| ora | componente | evento | evidenza |
|---|---|---|---|
| — | **13:30 apertura RTH** | nessun ciclo, nessun ingest, nessuno scoring: le finestre beat partono da `hour=14` | `celery_app.py:78,151,162,210` |
| 07:00 | `regime-detector` | esito non ricostruibile (log perduti); `regime_mult` osservato in tutte le decisioni = **0,7** | `execution_decisions.regime_mult` |
| 07:38–23:04 | *test suite* | **10 righe fixture** scritte in `portfolio_monitor_snapshots` (NAV 110.307,36 costante, 1 posizione MSFT 12,3456 az.) | [DAY-006] |
| 13:30 | `regime-detector-premarket` | schedulato (`hour=13, minute=30`); esito non ricostruibile | `celery_app.py:143` |
| 13:30 | `mobile-monitor-snapshot` | prima riga con provenienza reale: NAV 109.905,32 | `portfolio_monitor_snapshots` |
| **14:00:16–14:00:37** | `run-alpaca-ingestion` + `run-news-ingestion` | **primo ingest della giornata**, 30 min dopo l'apertura. 39 item in coda dal 26/08 19:45 scartati `stale` (età 18,5 h) | `news_queue_drops` |
| 14:00:37 | `sentiment-worker` | primo scoring: 19 segnali nell'ora, 4 in fallback (21,1%) | `sentiment_signals` |
| 14:01:41 | LLM | NVDA id **9070** score +0,5543 (ensemble pieno) — articolo "What's Going On With Broadcom Stock Thursday?" (**fan-out**) | `sentiment_signals`, `news_log` |
| **14:07:00** | `portfolio-cycle` #1 | **BUY NVDA** 6,0985 az. @ 224,7706 = 1.370,77 $, rank 1, `decision_id` 15120, order `9c1c44e6…` | `trades` 892 |
| 14:15:13 | LLM | NVDA id 9073 score **−0,4050** (8 min dopo la BUY, segno opposto e sbagliato: NVDA ha chiuso +8,74%) | `sentiment_signals` |
| 14:15:30 | LLM | CRM id **9075 score +0,7200** conf 0,900 — articolo *issuer-specific* "These Analysts Boost Their Forecasts On Salesforce Following Strong Q2 Results" | `sentiment_signals` |
| 14:15:43 | LLM | CRM id **9076 score +0,3220** — articolo *fan-out* su NVDA. **13 secondi dopo, sovrascrive il +0,72** | [DAY-003] |
| **14:22:00** | `portfolio-cycle` #2 | **BUY CRM** 5,5240 az. @ 247,9665 usando il segnale **9076** (+0,322), non il 9075 (+0,720). Rank 4 | `trades` 893, `execution_decisions` 15134 |
| 14:22:05 | guard P0-05 | 3 SKIP_PYRAMIDING (CSCO, SOXX, DELL) | `execution_decisions` |
| 14:45:57 | LLM | CRM id **9085 score 0,0000** conf 0,200 — market-wrap generico "Stock Market Today: S&P 500, Nasdaq 100 Futures Gain… CRM, CRWD, HPQ in Focus" | [DAY-001] |
| 14:52–15:52 | `portfolio-cycle` | CRM sotto gate da 5 cicli; uscita bloccata da `hold_minimum_minutes: 90` | `config/trading.yaml:154` |
| 15:02:08 | LLM | NVDA id 9091 +0,6200 (ensemble pieno) → SKIP_PYRAMIDING, già a libro dalle 14:07 | `execution_decisions` |
| **16:07:00** | `portfolio-cycle` | **SELL CRM** @ 244,84 — `exit_reason=portfolio_sell`, `exit_mechanism=below_entry_gate`, motivo: «age=1,4h, score=+0,000». Tenuta **105 min**. Netto **−18,02 $** | `trades` 893 |
| 16:07:04 | ranking | SKIP_FALLBACK BAC (single-model −0,120) | `execution_decisions` 15245 |
| 16:31:39 | LLM | NVDA id 9119 **−0,1774** | `sentiment_signals` |
| 16:45:20 | LLM | PANW id **9124 score +0,6375** — single-model: gpt-oss +0,85/0,75, glm 0,00/0,10, **`ensemble_std` registrato 0,000** | [DAY-004] |
| 16:45:45 | LLM | PANW id 9125 +0,0210 — 25 s dopo, sovrascrive il +0,6375. PANW ha chiuso **+12,83%** | [DAY-003] |
| 16:47:09 | LLM | NVDA id **9129 score 0,0000** — "Musk, Altman, Huang All Set to Speak at US-Hosted G20 Tech Meeting" | [DAY-001] |
| **16:52:00** | `portfolio-cycle` | **SELL NVDA** @ 229,1267 — `below_entry_gate`, «age=0,1h, score=+0,000». Tenuta 165 min. Netto **+26,29 $** | `trades` 892 |
| 17:01:13 | LLM | CRM id 9135 +0,5072 — articolo "Figma Stock Rallies Thursday" (**fan-out**) | `sentiment_signals` |
| **17:07:00** | `portfolio-cycle` | **BUY CRM** 5,4807 az. @ 249,26 (4,42 $ **sopra** il prezzo di uscita di 45 min prima). Rank 2 | `trades` 894 |
| 17:30:11 | LLM | CRM id 9144 **+0,6904** conf 0,825 — "Salesforce Stock Rockets 20% on Anthropic Windfall, Guidance Raise" (il vero catalizzatore, *issuer-specific*) | `sentiment_signals` |
| 17:37:00 | ranking | slot 17:37: **tutti e 5 i top-N sono SKIP_PYRAMIDING**; NOW (+0,363, sopra gate, non detenuto) tagliato `RANK_OUTSIDE_TOP_N` | F-051 |
| 17:45:11 | LLM | CRM id **9150 score 0,0000** — "Nvidia's Unusual Move…; $40 Trillion US Debt Bomb Ticks" (macro generico) | [DAY-001] |
| 18:00–19:00 | `sentiment-worker` | **finestra degradata**: 14/20 righe in fallback (70,0%) | F-049 |
| 18:30:13 | LLM | XLF −0,4900 e XLE −0,2400 (single-model). Segno corretto, S4 long-only → nessun ordine | [DAY-020] |
| 18:46:38 | LLM | CRM id 9171 **fallback FinBERT** +0,4573 (unico FinBERT della giornata) su articolo Adobe | `sentiment_signals` |
| **18:52:00** | `portfolio-cycle` | **SELL CRM** @ 251,61 — `below_entry_gate`, «age=1,1h, score=+0,000». Tenuta **105 min**. Netto **+12,13 $** | `trades` 894 |
| 19:30:46 | LLM | CRM id 9185 +0,6363 — "Salesforce's Q2 Results Squash 'SaaSpocalypse' Fears" | `sentiment_signals` |
| **19:37:00** | `portfolio-cycle` | **BUY CRM** @ 253,23 (rank 3) + **BUY TSLA** @ 354,19 (rank 4), 23 min dalla chiusura. Rank 1/2/5 = SKIP_PYRAMIDING | `trades` 895/896 |
| 19:45:01 | ingest | ultimo aggiornamento `ingestion_stats_daily` per benzinga/gdelt | `ingestion_stats_daily` |
| 19:49:02 | `sentiment-worker` | ultimo scoring della giornata | `sentiment_signals` |
| 19:52:00 | `portfolio-cycle` #24 | ultimo ciclo. 2 SKIP_PYRAMIDING (CRM, DELL), 1 SKIP_FALLBACK (SNOW +0,1375; SNOW ha chiuso +4,36%) | `execution_decisions` |
| **20:00 chiusura** | monitor | NAV 110.038,29, prev close 109.965,05, Δ **+73,24 $**, unrealized +1.111,04, 48 posizioni, drawdown 0,5493% | `portfolio_monitor_snapshots` |
| 20:07–21:52 | `portfolio-cycle` | **8 slot schedulati dopo la chiusura** — nessuna riga prodotta (guard di mercato) | [DAY-007] |
| 22:30:01 | `risk-report` | **1 sola riga**: NAV 110.007,72, exposure 31,77%, herfindahl 0,0244, `combined_drawdown` **1,2429%**, `alerts []`, `per_strategy_metrics {}` | [DAY-013] |
| 23:04:15 | *test suite* | **ultima riga della giornata in `portfolio_monitor_snapshots` è una fixture** (NAV 110.307,36, 1 posizione MSFT) | [DAY-006] |
| **23:14:50** | deploy | **redeploy dei container**: i log della seduta cessano di esistere | [DAY-010] |
| 00:07–00:13 (+1) | `decay-monitor` | 84 `SPY benchmark fetch failed` (6 retry/min), nessun alert | [DAY-017] |

Cicli portfolio: **24**, dalle 14:07:00 alle 19:52:00, cadenza 15 min, zero buchi.

---

## 4. Tabella news ingest

### Per fonte

| fonte | fetched | queued | duplicates | no_ticker | stale | righe in `news_log` | url unici | ticker |
|---|---|---|---|---|---|---|---|---|
| `alpaca_benzinga` | 550 | 303 | **2.535** | 0 | 39 | 118 | 54 | 36 |
| `gdelt_gkg` | 2.010 | 15 | 4 | 1.991 | 0 | 15 | 15 | 9 |
| `reuters` | 56 | 56 | 0 | 14 | 0 | **0** | 0 | 0 |
| **totale** | **2.616** | **374** | **2.539** | **2.005** | **39** | **133** | **69** | **43** |

Fonte: `ingestion_stats_daily WHERE day='2026-08-27'`, `news_log`, `news_queue_drops`.

- `duplicates` 2.535 > `fetched` 550 per benzinga → [DAY-016].
- La riga `reuters` è **spuria**: `RSS_INGESTION_ENABLED=0` dal 2026-07-03 (`ingestion.py:937-938`), il task non è nel beat schedule, e `news_log` non ha **mai** contenuto una riga `reuters` (0 su tutta la storia). 248 item "fetched" su 16 giorni, `queued` sempre = `fetched`, `no_ticker` sempre = `fetched/4` → firma di fixture. Vedi [DAY-006].
- **Nessun ingest pre-market né post-market.** Prima riga 14:00:37, ultima 19:49:02. Copertura oraria uniforme (17–23 righe/ora), zero buchi fra 14:00 e 20:00.
- Scarti allo stadio `sentiment`: `not_tradable` **155** (51% dei queued benzinga, filtrati solo *dopo* ~45 min di coda), `stale` 39, `duplicate_content` 4.
- **Zero timestamp futuri** (`published_at > fetched_at`: 0 righe). **Zero `published_at` NULL.**
- Latenza `published_at → fetched_at`: media 61,3 min, mediana **60,4 min**.
- Scomposizione (mediane, 133 righe, dossier `timeline`): `published→first_seen` 12,6 min (esterno) · `first_seen→ingested` **46,1 min** (coda Redis interna, 76% del totale) · `ingested→scored` ≈ 0 (i due timestamp sono scritti nella stessa transazione, quindi la metrica è strutturalmente vuota).
- Sanitizzazione input: `sanitize_text` è applicata nei connettori (`rss.py:57-62`, homoglyph → skip). **Non ho trovato prova di violazioni in ingresso oggi.** Il difetto di sanitizzazione/validazione è sull'**output** del modello → [DAY-005b / DAY-019].

### Per ticker (top 12 per numero di righe scorate)

| ticker | righe | ret. giorno | max score | min score | ultimo score | fallback | articoli propri |
|---|---|---|---|---|---|---|---|
| NVDA | 26 | +8,74% | +0,6290 | −0,4050 | 0,0000 | 7 | pochi: la maggioranza sono articoli su Broadcom/Coherent/Arm/Synopsys/Supermicro/Marvell/AMD/Intel/Micron/IREN |
| CRM | 15 | **+22,58%** | **+0,7200** | −0,0600 | +0,4705 | 5 | 4 su 15 (Figma, ServiceNow, Adobe, Microsoft, Snowflake, opzioni IV sono fan-out) |
| PANW | 7 | +12,83% | +0,6375 | −0,0334 | +0,0233 | 2 | — |
| TSLA | 5 | +2,60% | +0,4200 | −0,1196 | −0,1196 | 2 | — |
| META | 5 | −0,87% | +0,2550 | −0,4977 | −0,3056 | 0 | — |
| MSFT | 5 | +1,75% | +0,1989 | 0,0000 | +0,1989 | 0 | — |
| GOOGL | 5 | −0,39% | +0,1765 | 0,0000 | +0,1200 | 1 | — |
| INTC | 4 | +4,36% | +0,2278 | 0,0000 | **0,0000** | 1 | 1 su 4 |
| AMZN | 4 | −1,54% | +0,1889 | 0,0000 | 0,0000 | 1 | 0 su 4 |
| MU | 4 | −0,32% | +0,1645 | −0,1800 | 0,0000 | 1 | — |
| NOW | 3 | **+10,04%** | +0,3633 | +0,0210 | +0,3633 | 0 | 2 su 3 |
| QQQ | 3 | +1,37% | +0,4705 | +0,1800 | +0,2013 | 1 | — |

43 ticker su 96 hanno ricevuto almeno un punteggio. **53 simboli della watchlist a zero righe.**
Copertura *effective-timely* (issuer-specific + pubblicato entro il close): **26/96 = 27,1%**.
Fan-out: 28 dei 69 articoli unici mappano su ≥2 ticker (uno su 12, uno su 8) → 64 mapping extra su 133 righe (48,1%). `mapping_rilevanza`: 92 UNKNOWN vs 41 ISSUER_SPECIFIC, **0** righe classificate SECTOR_MACRO / FALSE_ENTITY_MATCH / IRRELEVANT_FANOUT.

### Top news per impatto sul segnale

| ora | titolo | ticker | score | esito |
|---|---|---|---|---|
| 14:15:30 | These Analysts Boost Their Forecasts On Salesforce Following Strong Q2 Results | CRM | **+0,7200** | **scartato** (sovrascritto 13 s dopo) |
| 17:30:11 | Salesforce Stock Rockets 20% on Anthropic Windfall, Guidance Raise | CRM | +0,6904 | non usato (posizione già aperta) |
| 16:45:20 | (earnings beat PANW) | PANW | +0,6375 | **scartato** (sovrascritto 25 s dopo) |
| 15:47:13 | Why Is AMD Stock Trending Today? | NVDA | +0,6290 | SKIP_PYRAMIDING |
| 19:30:46 | Salesforce's Q2 Results Squash 'SaaSpocalypse' Fears | CRM | +0,6363 | **BUY 19:37** |
| 14:15:43 | Nvidia To Rally Around 146%? Here Are 10 Top Analyst Forecasts For Thursday | CRM | +0,3220 | **BUY 14:22** |
| 14:45:57 | Stock Market Today: … CRM, CRWD, HPQ in Focus | CRM | **0,0000** | **SELL 16:07 (−18,02 $)** |
| 16:47:09 | Musk, Altman, Huang All Set to Speak at US-Hosted G20 Tech Meeting | NVDA | **0,0000** | **SELL 16:52 (+26,29 $)** |

**Confidenza dell'analisi ingest: High** (tre tabelle indipendenti concordano: `ingestion_stats_daily`, `news_log`, `news_queue_drops`), con l'eccezione della riga `reuters` che è dimostrabilmente artefatta.

---

## 5. Tabella performance modelli LLM

| modello | richieste | `eligible=true` | polarity media | conf. media | σ polarity | min | max |
|---|---|---|---|---|---|---|---|
| `glm-5.2:cloud` | 133 | 45 (33,8%) | +0,1530 | 0,3402 | 0,3146 | −0,70 | +0,90 |
| `gpt-oss:20b-cloud` | 133 | 45 (33,8%) | +0,1400 | 0,4659 | 0,3334 | −0,70 | +1,00 |
| `finbert` (fallback) | 1 | n/a | +0,7658 (ricostruito) | 0,597 | — | — | — |

Coppia attiva confermata: Redis `config:sentiment_llm_models = "glm52,gptoss"`.

**Errori / timeout / refusal:** entrambi i modelli hanno prodotto **133 righe su 133** — zero risposte
mancanti, zero refusal, zero parse failure (`parse_fail = 0` su tutte le fonti). Nessun outage Ollama.

**Latenza per modello: NON MISURABILE.** `llm_responses` non ha una colonna di durata e i log della
sessione non esistono più ([DAY-010]). Query che servirebbe se la colonna esistesse:
`SELECT model_id, percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms) FROM llm_responses WHERE generated_at::date='2026-08-27' GROUP BY 1`.

### Composizione dei segnali prodotti

| `model_id` del segnale | n | quota |
|---|---|---|
| `ensemble:glm-5.2:cloud+gpt-oss:20b-cloud` | 94 | 70,7% |
| `single:gpt-oss:20b-cloud` | 36 | 27,1% |
| `single:glm-5.2:cloud` | 2 | 1,5% |
| `finbert` | 1 | 0,8% |

`fallback_used = true` su **39/133 = 29,3%**. Fallback *vero* (FinBERT, ensemble non calcolabile): **1**.
Gli altri 38 sono degradi a modello singolo. Per ora UTC: 14:00 21,1% · 15:00 31,8% · 16:00 26,1% ·
17:00 11,5% · **18:00 70,0%** · 19:00 21,7%.

### Distribuzione punteggi (`score = polarity × confidence`)

Media +0,1085 su 133 righe. Estremi: CRM +0,7200 / META −0,4977.
`ensemble_std`: 0,00 su **83** righe (di cui 39 per costruzione, essendo single-model), 0,04–0,28 su 47,
≥0,30 su **3**.

### Disaccordo forte fra modelli (spread di polarity ≥ 0,50)

| segnale | ticker | score finale | `ensemble_std` **registrato** | polarity gpt-oss | polarity glm | **spread reale** |
|---|---|---|---|---|---|---|
| 9124 | PANW | +0,6375 | **0,000** | +0,85 (conf 0,75) | 0,00 (conf 0,10) | **0,85** |
| 9166 | XLK | +0,4200 | **0,000** | +0,60 (conf 0,70) | −0,15 (conf 0,35) | **0,75** |
| 9161 | NVDA | +0,4500 | **0,000** | +0,75 (conf 0,60) | +0,10 (conf 0,20) | **0,65** |
| 9171 | CRM | +0,4573 (FinBERT) | **0,000** | −0,30 (conf 0,20) | +0,30 (conf 0,25) | **0,60** |
| 9140 | AMZN | +0,0720 | 0,354 | +0,30 | −0,20 | 0,50 |

Le prime 4 righe sono il difetto [DAY-004]: `src/llm/ensemble.py:293-300` filtra a `confidence ≥ 0.4`
*prima* di calcolare `std`, e `std = 0.0` quando resta un solo modello — quindi il controllo
`std >= divergence_threshold (0.40) → fallback FinBERT` non viene mai eseguito nei casi di massimo
disaccordo. Nel caso 9171 nessuno dei due era eleggibile → FinBERT (comportamento corretto).

### Verifica funzionale della catena LLM

| domanda | esito | evidenza |
|---|---|---|
| L'output LLM è validato prima di entrare nel signal store? | **Parzialmente NO** | polarity/confidence/materiality/novelty hanno bound Pydantic; `event_type` e `directness` sono `str` liberi senza enum → 6 valori fuori enum in agosto, incluso uno con zero-width space. [DAY-019] |
| L'ensemble gestisce la varianza alta? | **NO in modo affidabile** | il gate `std ≥ 0,40` esiste ma è aggirato dal filtro di eleggibilità: 4 casi oggi. [DAY-004] |
| E la varianza è un gate d'ingresso a valle? | **NO** | 3 segnali con `ensemble_std ≥ 0,30` sono passati senza alcun trattamento. [DAY-021] |
| Le news duplicate pesano più volte? | **NO** per URL identico (`uq_news_log_url_ticker`, dedup Redis 2.539 scarti). **SÌ per contenuto**: 0 `duplicates_syndication_per_ticker` ma 15 articoli su 2+ ticker. |
| La stessa news può generare segnali multipli? | **SÌ, per ticker diversi** (fan-out: 64 mapping extra). Per lo *stesso* ticker no. | `news_log` group by url |
| Confidence bassa riduce il peso? | **SÌ**, `score = polarity × confidence` è rispettato (verificato su 9124: 0,85 × 0,75 = 0,6375). |
| I modelli sono chiamati offline/background? | **SÌ** | `sentiment-worker` su queue `inference`, `crontab(*/15)`; nessuna chiamata LLM in `portfolio_scheduler`. Corretto. |
| Un'allucinazione LLM può entrare direttamente in decisione? | **SÌ, con un solo gate** | il gate è la soglia 0,30 su `polarity × confidence`. Non c'è supervisor agent, non c'è verifica RAG delle affermazioni quantitative, e il guard di varianza è aggirabile. Un singolo modello con `polarity 0,85 / conf 0,75` produce un segnale tradabile senza cross-check. |

---

## 6. Tabella segnali finali per ticker

Segnali che hanno raggiunto o superato il gate d'ingresso attivo (Redis `feedback:entry_threshold:S4 = 0.3`)
in almeno un momento della giornata:

| ticker | max score | ret. giorno | esito | motivo |
|---|---|---|---|---|
| CRM | +0,7200 | +22,58% | **3 BUY / 2 SELL** | tradato, ma con il segnale sbagliato ([DAY-003]) |
| PANW | +0,6375 | +12,83% | **nessun ordine** | il +0,6375 non entra mai nel ledger S4: sovrascritto dal +0,021 25 s dopo. Comunque già a libro da S1 dal 13/07 |
| NVDA | +0,6290 | +8,74% | **1 BUY / 1 SELL** | ok; i successivi 0,62/0,63 → SKIP_PYRAMIDING |
| AMAT | +0,5215 | +0,54% | SKIP_PYRAMIDING | rank 1 allo slot 19:37, già a libro da 07-14 (−19,4%) |
| QQQ | +0,4705 | +1,37% | SKIP_PYRAMIDING | a libro da 07-31 |
| ARM | +0,4320 | +1,65% | SKIP_PYRAMIDING | a libro da 08-03 |
| XLK | +0,4200 | +3,16% | nessun ordine | single-model con spread reale 0,75 ([DAY-004]) |
| TSLA | +0,4200 | +2,60% | **1 BUY** | ok |
| NOW | +0,3633 | **+10,04%** | nessun ordine | sopra gate, ensemble pieno, non detenuto: `RANK_OUTSIDE_TOP_N` per 6 cicli poi `SKIP_ENTRY_FRESHNESS` (F-051) |
| MRVL | +0,3578 | −1,49% | SKIP_PYRAMIDING | a libro da 07-14 |
| META | −0,4977 | −0,87% | nessun ordine | segno corretto, S4 long-only ([DAY-020]) |
| XLF | −0,4900 | −0,65% | nessun ordine | segno corretto, long-only |
| AMD | −0,3500 | −0,89% | nessun ordine | segno corretto, long-only |

Sotto gate ma su mover forti: ADBE +0,060 (+5,73%), AVGO +0,230 (+4,49%), INTC +0,228 (+4,36%),
SNOW +0,1375 (+4,36%, escluso da `SKIP_FALLBACK` perché single-model).

Dispositions del ledger `s4_intent_events` (1.700 candidati osservati, 1.700 disposition):
`SKIP_ENTRY_FRESHNESS` 750 · `SKIP_ENTRY_GATE` 487 · `SKIP_STALE` 236 · `SKIP_PYRAMIDING` 106 ·
`SKIP_FALLBACK` 98 · `RANK_OUTSIDE_TOP_N` 17 · **`SUBMITTED` 5** · `SKIP_IDEMPOTENCY` 1.

---

## 7. Tabella ordini generati/eseguiti

Tutti e 8 gli ordini sono **paper** (`alpaca_paper`), motore `portfolio`, market order, fill immediato
(`order_submitted_to_filled` mediana 0,0 min su 5 ingressi).

| # | ts decisione | strategia | ticker | azione | qty | prezzo fill | notional | stato | `decision_id` | segnale causante | risk check applicati | anomalia |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 14:07:00 | S4 | NVDA | BUY | 6,098483 | 224,7706 | 1.370,77 | filled | 15120 | **9070** (+0,5543) | gate 0,30 ✓ · freschezza 4h ✓ · anti-pyramiding ✓ · idempotenza ✓ · `regime_mult` 0,7 ✓ · rank 1/5 ✓ | `signal_score` loggato +0,6652 ≠ 0,5543 ([DAY-005]) |
| 2 | 14:22:00 | S4 | CRM | BUY | 5,523973 | 247,9665 | 1.369,77 | filled | 15134 | **9076** (+0,3220) | idem, rank 4/5 | usa il segnale fan-out invece del +0,7200 issuer-specific ([DAY-003]) |
| 3 | 16:07:00 | S4 | CRM | SELL (close) | 5,523973 | 244,84 | 1.352,50 | filled | 15262 | **NULL** — motivo cita il segnale delle 14:45 (score 0,000) | `hold_minimum_minutes` 90 ✓ (105 min) · `exit_persistence_cycles` 2 ✓ | `signal_id` NULL ([DAY-015]); trigger = market-wrap generico ([DAY-001]) |
| 4 | 16:52:00 | S4 | NVDA | SELL (close) | 6,098483 | 229,1267 | 1.397,34 | filled | 15318 | **NULL** — motivo cita il segnale delle 16:47 (score 0,000) | idem (165 min) | `signal_id` NULL; trigger = articolo G20 ([DAY-001]) |
| 5 | 17:07:00 | S4 | CRM | BUY | 5,480743 | 249,26 | 1.366,14 | filled | 15343 | **9135** (+0,5072) | rank 2/5 | rientro **4,42 $/az. sopra** l'uscita di 45 min prima; `signal_score` +0,6086 ≠ 0,5072 |
| 6 | 18:52:00 | S4 | CRM | SELL (close) | 5,480743 | 251,61 | 1.379,05 | filled | 15528 | **NULL** — segnale delle 17:45 (score 0,000) | idem (105 min) | `signal_id` NULL; trigger = macro generico |
| 7 | 19:37:00 | S4 | CRM | BUY | 5,406271 | 253,23 | 1.369,04 | filled | 15592 | **9185** (+0,6363) | rank 3/5 | 23 min dalla chiusura; `entry_percentile` 0,949 |
| 8 | 19:37:00 | S4 | TSLA | BUY | 3,865242 | 354,19 | 1.369,04 | filled | 15593 | **9186** (+0,4200) | rank 4/5 | `signal_score` +0,5040 ≠ 0,4200 |

**Zero ordini rejected, zero cancelled, zero partial fill non riconciliati.**
`portfolio_cycles.orders_count` somma **115** per la giornata contro **8** ordini realmente inviati → [DAY-023].

Guard che hanno bloccato ordini: `SKIP_THRESHOLD` 487 · `SKIP_PYRAMIDING` 14 (coppie simbolo-segnale
distinte; 106 osservazioni a livello di slot) · `SKIP_FALLBACK` 4 (BAC, WMT, TM, SNOW).

---

## 8. Tabella PnL / rendimento

### Realizzato (3 uscite, tutte S4)

| trade | ticker | entry | exit | qty | gross | costo | **netto** | tenuta |
|---|---|---|---|---|---|---|---|---|
| 893 | CRM | 247,9665 | 244,84 | 5,5240 | −17,27 | 0,7525 | **−18,02** | 105 min |
| 892 | NVDA | 224,7706 | 229,1267 | 6,0985 | +26,57 | 0,2744 | **+26,29** | 165 min |
| 894 | CRM | 249,26 | 251,61 | 5,4807 | +12,88 | 0,7511 | **+12,13** | 105 min |
| | | | | | **+22,18** | **1,778** | **+20,40** | |

### Non realizzato aperto il 2026-08-27 (mark al close)

| trade | ticker | entry | close | qty | MTM | nota |
|---|---|---|---|---|---|---|
| 895 | CRM | 253,23 | 252,05 | 5,4063 | **−6,38** | terzo lotto CRM |
| 896 | TSLA | 354,19 | 354,81 | 3,8652 | **+2,40** | |

`close` derivato: `entry_price + mtm_eod/qty` dal dossier (fonte prezzi Alpaca SIP, `adjustment=all`).

### Per ticker

| ticker | realizzato | MTM aperto oggi | **totale giorno** | ret. titolo | controfattuale buy-and-hold |
|---|---|---|---|---|---|
| CRM | −5,89 | −6,38 | **−12,27** | **+22,58%** | +22,53 (primo lotto tenuto al close) |
| NVDA | +26,29 | — | **+26,29** | +8,74% | +19,57 (uscire è stato migliore) |
| TSLA | — | +2,40 | **+2,40** | +2,60% | — |
| | **+20,40** | **−3,98** | **+16,42** | | |

### Per strategia

| sleeve | realizzato | note |
|---|---|---|
| **S4** | **+20,40** | tutte e 3 le uscite e tutti e 5 gli ingressi della giornata sono S4 |
| **S1** | 0,00 | nessun ordine; gate `rebalance_frequency: MONTHLY` chiuso (#185) |
| legacy / contaminazione | 0,00 | — |

### Posizioni aperte prima del 2026-08-27

46 posizioni nello snapshot d'apertura. Il dossier scompone il P&L intraday del book preesistente in
`passive_pnl +3,16` / `selection_pnl +53,44` / `exit_effect **−35,25**` → `active_decision_pnl +18,19`
contro `actual_intraday_pnl +21,35`. L'`exit_effect` di −35,25 $ è la misura indipendente dello stesso
fenomeno che ho stimato a 34,80 $ sul solo CRM: **la giornata ha perso denaro sulle uscite, non sugli
ingressi.**

### Book

| metrica | valore | fonte |
|---|---|---|
| NAV apertura (prev close) | 109.965,05 | `portfolio_monitor_snapshots` 20:00 |
| NAV chiusura | **110.038,29** | idem |
| Δ giorno | **+73,24 (+0,067%)** | idem |
| SPY | +0,655% | dossier `mercato/rendimenti/SPY` |
| `market_beta_1_usd` (attesa a beta 1) | +112,93 | dossier `decision_quality/summary` |
| Unrealized totale al close | +1.111,04 | snapshot |
| Gross exposure | 31,79% | snapshot |
| Posizioni aperte | 48 | snapshot |
| Drawdown (monitor 20:00) | **0,5493%** | `portfolio_monitor_snapshots` |
| Drawdown (`risk_reports` 22:30) | **1,2429%** | `risk_reports` → **incoerenza** [DAY-013] |

### Slippage e costi

| voce | valore |
|---|---|
| Costi totali (5 entry + 3 exit) | 4,52 $ |
| `slippage_est` | **identico a `cost_usd` su tutte e 3 le uscite** ([DAY-014]) |
| Slippage vero (fill vs quota pre-trade) | **NON CALCOLABILE**: le righe `trades` non conservano il prezzo di riferimento pre-invio. Query che servirebbe: confronto `trades.entry_price` con `nbbo.mid` dal blocco `event_market_context` del dossier, che oggi non è popolato per gli ingressi. |

---

## 9. Analisi correttezza buy/sell

| controllo | esito | evidenza |
|---|---|---|
| BUY generati solo quando consentito | **OK** | tutti e 5 con `score ≥ 0,30` (raw 0,42–0,6363), `ema_pass=true`, `regime_mult=0,7`, rank ≤ 5, dentro RTH, simbolo in watchlist |
| SELL/exit generati correttamente | **OK sul meccanismo, discutibile sull'innesco** | tutti e 3 `exit_reason=portfolio_sell` con `exit_mechanism=below_entry_gate` — target weight portato a 0 dal gate. Meccanicamente corretto; l'innesco è un market-wrap a 0,000 ([DAY-001]) |
| Stop-loss rispettati | **N/A per decisione esplicita** | `config/trading.yaml:182` `stop_loss: 0.0` (decisione 2026-07-15, documentata). `stop_decisions` vuota dal 2026-07-14; `stop_shadow_log` 1.131 righe di sola osservazione. **Conforme al design.** |
| Signal flip rispettato | **OK** | nessun BUY su segnale negativo, nessun SELL su segnale positivo. Il SELL con «score +0,000» non è un flip: è il gate, non un contro-segnale |
| Max holding days rispettato | **OK** | nessuna posizione S4 aperta oggi ha superato l'orizzonte; `max_signal_age` 4h applicato (750 `SKIP_ENTRY_FRESHNESS`) |
| Rebalance band rispettata | **OK** | `hold_minimum_minutes: 90` e `exit_persistence_cycles: 2` rispettati su tutte e 3 le uscite. **Nota:** entrambi i round trip CRM sono durati **esattamente 105 min** = primo ciclo dopo la scadenza dei 90 min. La decisione di uscita era già determinata alle 14:52; la banda non l'ha annullata, l'ha solo differita. La politica effettiva di S4 oggi è stata «compra, tieni 105 min, vendi» |
| Nessun ordine duplicato | **OK** | 0 coppie (minuto, simbolo, decisione) con count > 1 |
| Nessun ordine contrario nello stesso intervallo | **OK** | roundtrip minimo 105 min, ben oltre i 30 min di soglia. Ma 3 BUY su CRM in una seduta con 2 SELL intermedi ([DAY-002]) |
| Nessun ordine su ticker non consentito | **OK** | 3 simboli distinti, tutti in watchlist |
| Nessun ordine fuori orario | **OK** | tutti fra 14:07 e 19:37 UTC, dentro RTH 13:30–20:00 |
| Nessun trade su dati stale | **OK** | 236 `SKIP_STALE` + 750 `SKIP_ENTRY_FRESHNESS` fanno il loro lavoro |
| Nessun trade su output LLM non valido | **PARZIALE** | non esiste un gate di validità dell'output oltre polarity/confidence: vedi [DAY-004] e [DAY-019] |
| Nessun trade con circuit breaker attivo | **NON VERIFICABILE** | nessuna traccia di stato del breaker in DB e log della seduta perduti ([DAY-010]). F-049/F-050 documentano che il breaker è inerte |
| Nessun trade con strategia disabilitata | **OK** | `strategy_lifecycle` mostra S4 `paper` approved=false, S1 `supervised_paper` — coerente con l'esecuzione paper |
| Paper/live coerente | **OK** | `broker_environment='paper'` su tutte le 86 righe con provenienza |
| Idempotenza su retry Celery | **OK** | 1 `SIGNAL_DUPLICATE_SKIP` in `audit_log`, 1 `SKIP_IDEMPOTENCY` nel ledger, 453 `SIGNAL_STALE_SKIP`. Il fail-closed su Redis assente non è stato attivato |
| Riconciliazione ordini/fill/posizioni | **OK sul giorno, NOTA sul book** | tutti e 8 gli ordini hanno `entry_order_id`/`exit_order_id` e prezzo di fill. `order_lookup_error` = 0 su 138 righe di timeline. Divergenze DB↔broker sul book preesistente (NOK/WDC/MRVL) sono già registrate in F-048 |

### Pattern operativi specifici richiesti

| pattern | esito |
|---|---|
| Roundtrip < 30 min | **assente** (minimo 105 min) |
| BUY ripetuto > 3 volte senza SELL intermedio | **assente** (3 BUY CRM, ma con 2 SELL intercalati) |
| SELL con sentiment positivo (bug A5) | **assente** — tutte e 3 le SELL su `score 0,000` |
| `fallback_used=True` su tutti i simboli in un periodo | **parziale**: finestra 18:00–19:00 al 70,0% (14/20). Non un outage totale |
| NO-ORDER (decisione creata, ordine non generato) | **assente** — 8 decisioni BUY/SELL, 8 `order_id` popolati |
| Score < 0,05 che hanno generato ordini | **assente** (minimo raw 0,42) |
| Ordini identici nello stesso minuto | **assente** — le due BUY del 19:37 sono su simboli diversi (CRM, TSLA), stesso ciclo, comportamento atteso |

---

## 10. Anomalie trovate

### [DAY-001] (F-008) Le tre uscite della giornata sono innescate da articoli generici multi-ticker a punteggio 0,000

* Tipo: Bug
* Area: Signal / Orders
* Evidenza:
  * tabelle: `sentiment_signals`, `execution_decisions`, `trades`, `news_log`
  * timestamp: 2026-08-27 16:07:00, 16:52:00, 18:52:00 UTC
  * snippet:
    ```
    SELL CRM  16:07 → [below_entry_gate] «generated 14:45 UTC, score=+0.000»
       → signal 9085, conf 0,200, articolo "Stock Market Today: S&P 500, Nasdaq 100 Futures
         Gain Following NVDA Blockbuster Q2 Report— CRM, CRWD, HPQ in Focus (UPDATED)"
    SELL NVDA 16:52 → «generated 16:47 UTC, score=+0.000»
       → signal 9129, conf 0,250, "Musk, Altman, Huang All Set to Speak at US-Hosted G20 Tech Meeting"
    SELL CRM  18:52 → «generated 17:45 UTC, score=+0.000»
       → signal 9150, conf 0,200, "Nvidia's Unusual Move Answers AI Trade's Key Question;
         $40 Trillion US Debt Bomb Ticks; Key Fed Speech Awaited"
    ```
* Descrizione: tre articoli di rassegna di mercato, nessuno dei quali contiene informazione
  issuer-specific su CRM o NVDA, hanno prodotto punteggi 0,000 con confidence 0,20–0,25. Poiché S4 usa il
  segnale più recente come riferimento, quei 0,000 hanno azzerato il target weight e liquidato posizioni
  aperte su segnali +0,72 e +0,63. Il modello si è comportato correttamente (un market-wrap *non* è
  informazione su CRM); è la pipeline che tratta «nessuna informazione» come «informazione negativa».
* Impatto: sul CRM ha prodotto la sequenza di tre round trip; sull'NVDA ha chiuso in profitto per caso.
  In generale converte l'assenza di notizie in un ordine di vendita.
* Severità: **High**
* Confidenza: **High**
* Azione consigliata: ticket di correttezza — un punteggio 0,000 con confidence < 0,3 non è un
  contro-segnale e non deve azzerare il target di una posizione aperta (la stessa forma logica di FIX-D/#236,
  applicata al punteggio neutro invece che all'età). **Non è una taratura**: non sposta soglie, distingue
  «neutro» da «assente».
* Test/monitor consigliato: test che una posizione aperta su score ≥ gate non venga chiusa da un segnale
  successivo con `|score| < 0.05 AND confidence < 0.3`; monitor giornaliero sul numero di uscite il cui
  segnale-innesco ha `n_ticker_articolo > 3`.

### [DAY-002] (F-013) Tre round trip su CRM nella stessa seduta, su un titolo chiuso a +22,58%

* Tipo: Anomalia
* Area: Orders
* Evidenza:
  * tabella: `trades` id 893/894/895
  * timestamp: 14:22 → 16:07 → 17:07 → 18:52 → 19:37 UTC
  * snippet:
    ```
    BUY  14:22 @ 247,9665 → SELL 16:07 @ 244,84  → netto −18,02  (drift post-uscita +39,83)
    BUY  17:07 @ 249,26   → SELL 18:52 @ 251,61  → netto +12,13
    BUY  19:37 @ 253,23   → aperta, MTM EOD −6,38
    Netto giornata: −12,27 su un titolo a +22,58%
    ```
* Descrizione: non esiste banda fra il gate d'ingresso (0,30) e la condizione d'uscita (target 0). Ogni
  volta che il segnale più recente scende sotto gate la posizione viene chiusa, e ogni volta che risale la
  posizione viene riaperta — a prezzi crescenti (4,42 $/az. e 1,62 $/az. sopra le uscite rispettive).
* Impatto: **34,80 $** su un controfattuale corto (tenere il primo lotto valeva +22,53 $; il risultato è
  stato −12,27 $). Corroborato indipendentemente dal dossier: `exit_effect_usd = −35,25`.
* Severità: **High**
* Confidenza: **High**
* Azione consigliata: i dollari sono già registrati nel ledger su F-013 dalla sessione alpha-miss di
  questa data. Nessun nuovo ticket: la banda d'uscita è **taratura**, congelata fino al 28/09.
  Va invece corretto l'innesco ([DAY-001]), che non è taratura.
* Test/monitor consigliato: monitor «numero di round trip per simbolo per seduta > 1» con alert.

### [DAY-003] (F-023) S4 tiene il segnale più recente, non il più forte: due sovrascritture in 13 e 25 secondi

* Tipo: Bug
* Area: Signal
* Evidenza:
  * file: `src/strategies/s4/ranking.py:200-205` — `if prev is None or sig.generated_at > prev.generated_at: best[sig.symbol] = sig`
  * tabelle: `sentiment_signals`, `s4_intent_events`
  * snippet:
    ```
    CRM  14:15:30 id 9075 score +0,7200 conf 0,900  ISSUER_SPECIFIC ("Analysts Boost Forecasts On Salesforce")
    CRM  14:15:43 id 9076 score +0,3220 conf 0,700  FAN-OUT        ("Nvidia To Rally Around 146%?")
      → il BUY delle 14:22 usa 9076. Nel ledger #294 il candidate dello slot 14:22 è 9076, rank 4.
    PANW 16:45:20 id 9124 score +0,6375 conf 0,750  (terzo punteggio del giorno)
    PANW 16:45:45 id 9125 score +0,0210 conf 0,200  FAN-OUT
      → il ledger allo slot 16:52 registra 9125 e SKIP_ENTRY_GATE. Il +0,6375 non appare in nessuno
        dei 24 slot. PANW ha chiuso +12,83%.
    ```
* Descrizione: la deduplicazione per simbolo è per `generated_at DESC`, quindi con 15 articoli su CRM e 26
  su NVDA in una seduta la scelta del segnale di riferimento è governata dall'ordine di arrivo in coda, non
  dal contenuto. Un articolo fan-out arrivato 13 secondi dopo batte un articolo issuer-specific con
  confidence 0,90.
* Impatto: sul BUY di CRM l'effetto immediato sul P&L è nullo (stesso simbolo, stesso peso, stesso prezzo),
  ma il riferimento a bassa convinzione è quello che poi viene facilmente superato da un 0,000. Su PANW il
  segnale più forte della giornata non è mai entrato nel processo decisionale; il costo diretto è nullo
  perché il titolo era già a libro e il guard anti-pyramiding l'avrebbe bloccato comunque.
* Severità: **High**
* Confidenza: **High**
* Azione consigliata: ticket di correttezza — il criterio di deduplicazione deve incorporare convinzione e
  relevance, non solo la freschezza (per esempio: a parità di finestra di freschezza, tieni
  `max(|score| × confidence)`, con preferenza per `relevance = ISSUER_SPECIFIC`). Passa il test di esenzione:
  finché il riferimento è scelto per ordine d'arrivo, ogni giornata osservata misura la latenza della coda,
  non il segnale.
* Test/monitor consigliato: test che con due segnali dello stesso simbolo entro 60 s il ranker scelga quello
  a punteggio maggiore; metrica giornaliera «quota di simboli il cui `max_score_own` non è il segnale usato».

### [DAY-004] (**F-054, nuovo**) Il guard di divergenza d'ensemble è aggirato dal filtro di eleggibilità: `ensemble_std` vale 0,000 proprio quando il disaccordo è massimo

* Tipo: Bug
* Area: LLM
* Evidenza:
  * file: `src/llm/ensemble.py:293-300`
    ```python
    eligible = [o for o in outputs if o.confidence >= effective_min_confidence]   # 0.4
    if not eligible: return None
    std = float(np.std([o.polarity for o in eligible], ddof=1)) if len(eligible) > 1 else 0.0
    if len(eligible) > 1 and std >= self.divergence_threshold:   # 0.40 live
        return None   # → FinBERT
    ```
  * tabelle: `sentiment_signals`, `llm_responses`
  * timestamp: 16:45:20, 18:15:11, 18:30:13 UTC (e 18:46:38 come controesempio corretto)
  * snippet:
    ```
    sig 9124 PANW score +0,6375 ensemble_std 0,000 | gpt-oss +0,85 (0,75)  glm  0,00 (0,10) → spread 0,85
    sig 9166 XLK  score +0,4200 ensemble_std 0,000 | gpt-oss +0,60 (0,70)  glm −0,15 (0,35) → spread 0,75
    sig 9161 NVDA score +0,4500 ensemble_std 0,000 | gpt-oss +0,75 (0,60)  glm +0,10 (0,20) → spread 0,65
    ```
* Descrizione: la deviazione standard è calcolata **solo fra i modelli eleggibili**. Quando uno dei due ha
  confidence < 0,4 resta un solo modello, `std` è impostato a 0,0 per costruzione e il controllo
  `std ≥ 0,40 → fallback FinBERT` non viene mai eseguito. Ma «il secondo modello ha bassa confidence» è
  esattamente la forma tipica del disaccordo: glm su PANW ha scritto «the news item provides only a headline»
  con polarity 0,00, mentre gpt-oss ha scritto «bullish outlook after a strong earnings beat» con +0,85. Il
  sistema archivia quel disaccordo come **accordo perfetto** e produce un segnale tradabile da un solo
  modello, senza il cross-check che CLAUDE.md § *Hallucination Mitigation* prescrive.
* Impatto: il controllo di varianza dichiarato non protegge nei casi che dovrebbe coprire. 4 casi oggi su 133
  segnali (3,0%), fra cui il terzo punteggio più alto della giornata. Rende inoltre **inutilizzabile
  `ensemble_std` come evidenza retrospettiva**: 83 righe a 0,00 su 133 non significano consenso.
* Severità: **High**
* Confidenza: **High**
* Azione consigliata: ticket di correttezza. Calcolare e persistere `polarity_spread_all_models` su
  *tutti* i modelli che hanno risposto, indipendentemente dall'eleggibilità, e valutare la soglia di
  divergenza su quello. Passa il test di esenzione: finché `ensemble_std` è 0 nei casi di disaccordo massimo,
  ogni analisi futura sulla varianza d'ensemble raccolta in questa finestra è falsa.
* Test/monitor consigliato: test unitario — due output con polarity 0,85/0,00 e confidence 0,75/0,10 devono
  produrre uno spread registrato ≥ 0,40 (fallback o flag), non `std = 0,0`; monitor giornaliero sul numero di
  segnali con `ensemble_std = 0` ma spread reale dei `llm_responses` ≥ 0,40.

### [DAY-005] (F-052) `execution_decisions.signal_score` non coincide con lo score del segnale citato — causa individuata: il moltiplicatore di velocità

* Tipo: Bug
* Area: Signal / Data
* Evidenza:
  * file: `src/workers/portfolio_scheduler.py:4055-4090` (moltiplicatore applicato a `signals_df` **dopo**
    lo snapshot del ledger), `src/strategies/s4/intent_ledger.py:250`
  * tabelle: `execution_decisions`, `sentiment_signals`, `s4_intent_events`
  * snippet:
    ```
    signal 9070 NVDA : sentiment_signals 0,5543 | ledger snapshot 0,5543 | execution_decisions 0,6652 (×1,20)
    signal 9135 CRM  : 0,5072 | 0,5072 | 0,6086 (×1,20)
    signal 9186 TSLA : 0,4200 | 0,4200 | 0,5040 (×1,20)
    signal 9185 CRM  : 0,6363 | 0,6363 | 0,5090 (×0,80)
    signal 9076 CRM  : 0,3220 | 0,3220 | 0,3220 (×1,00)

    slot 19:37, rank per snapshot.score:  AMAT 0,5215→rank1  DELL 0,5812→rank2
                                          CRM  0,6363→rank3  TSLA 0,4200→rank4  ARM 0,4320→rank5
    ```
* Descrizione: il ranking S4 ordina per `effective_strength = score`, ma lo score su cui ordina è quello
  **moltiplicato per la velocità del segnale** (`SIGNAL_VELOCITY_BOOST`, valori osservati ×0,80/×1,00/×1,20),
  applicato a `signals_df` a valle. Il ledger #294 registra invece lo score **grezzo**. Risultato: il `rank`
  persistito non è una funzione monotona dello `score` persistito, e `execution_decisions.signal_score`
  porta un terzo valore ancora. Tre rappresentazioni dello stesso segnale nello stesso ciclo.
* Impatto: la selezione S4 non è ricostruibile dal ledger scritto per renderla ricostruibile. Nessun impatto
  diretto sul P&L; impatto pieno sull'auditabilità e su qualunque analisi di IC per rank.
* Severità: **High**
* Confidenza: **High**
* Azione consigliata: ticket di correttezza — persistere nello snapshot del ledger sia lo score grezzo sia
  quello effettivamente usato per l'ordinamento, con il moltiplicatore applicato. Passa il test di esenzione.
* Test/monitor consigliato: invariante — per ogni `decision_slot`, la sequenza dei `rank` deve essere
  monotona non crescente nello score usato per l'ordinamento; asserzione in CI.

### [DAY-006] (F-028) La suite di test scrive nel database di produzione: l'ultima riga di portafoglio della giornata è una fixture

* Tipo: Bug
* Area: Data / Ops
* Evidenza:
  * tabelle: `portfolio_monitor_snapshots`, `ingestion_stats_daily`
  * timestamp: 07:38:27, 07:41:12, 08:37:16, 08:41:12, 09:09:47, 10:41:09 … **23:04:15** UTC
  * snippet:
    ```
    SELECT source, COUNT(*), MIN(nav), MAX(nav) FROM portfolio_monitor_snapshots
     WHERE created_at::date='2026-08-27' GROUP BY 1;
      alpaca_paper | 86 | 109905.32 | 110067.35
      (NULL)       | 10 | 110307.36 | 110307.36     ← fixture

    payload fixture: nav 110307.36 (costante su 10 righe), cash 76998.12, open_positions 1,
      positions=[{symbol MSFT, qty 12.3456, avg_entry_price 511.22, unrealized_return -0.01234}],
      operational.market_phase = "open"  ← alle 07:38 UTC, mercato chiuso

    ingestion_stats_daily: reuters fetched=56 queued=56 no_ticker=14 updated_at 23:06:19
      ma RSS_INGESTION_ENABLED=0 dal 2026-07-03 e news_log non ha MAI una riga reuters (0 su tutta la storia)
    ```
* Descrizione: dieci righe scritte da test nella tabella di produzione che alimenta il read-model mobile,
  con valori di fixture riconoscibili (`qty 12.3456`, `unrealized_return -0.01234`). La riga con
  `as_of` massimo della giornata (23:04:15) **è una fixture**: qualunque consumatore che legga «lo snapshot
  più recente» vede NAV 110.307,36 e una sola posizione MSFT invece di 110.038,29 e 48 posizioni. Nella
  stessa giornata compare anche una riga `reuters` in `ingestion_stats_daily` per una fonte disabilitata da
  8 settimane, che fa apparire 56 item raccolti che non esistono.
* Impatto: (a) il read-model mobile può servire un portafoglio inventato; (b) `ingestion_stats_daily` — usata
  come tabella di riferimento per la copertura news, inclusa la tabella §4 di questo report — contiene righe
  che non corrispondono a nessuna ingestione. È un difetto di **integrità dell'evidenza**, non solo di igiene
  dei test.
* Severità: **High**
* Confidenza: **High**
* Azione consigliata: ticket di correttezza. La suite deve puntare a un database dedicato (variabile
  d'ambiente distinta o fixture con rollback obbligatorio); in subordine, un vincolo che impedisca
  `INSERT` senza `source` su `portfolio_monitor_snapshots`. Passa il test di esenzione: righe di test dentro
  la serie osservata rendono sbagliata l'evidenza.
* Test/monitor consigliato: query di sanità notturna — `COUNT(*) WHERE source IS NULL` su
  `portfolio_monitor_snapshots` e `WHERE source NOT IN (fonti abilitate)` su `ingestion_stats_daily`, deve
  essere 0; alert su violazione.

### [DAY-007] (F-021) Finestre beat in UTC fisso: i primi 37 minuti della seduta senza ingest, senza scoring e senza cicli

* Tipo: Bug
* Area: Ops
* Evidenza:
  * file: `src/workers/celery_app.py:78` (sentiment), `:151` (gdelt), `:162` (alpaca), `:210` (portfolio) —
    tutti `hour="14-21"`
  * timestamp: apertura RTH 13:30 UTC; prima riga `news_log` 14:00:37; primo ciclo 14:07:00
* Descrizione: le finestre sono espresse in ora UTC fissa. In EDT (dal secondo weekend di marzo al primo di
  novembre) la seduta apre alle 13:30 UTC, quindi la finestra 13:30–14:07 è cieca: nessuna news raccolta,
  nessun segnale prodotto, nessun ciclo di portafoglio. Simmetricamente, gli 8 slot 20:07–21:52 sono
  schedulati dopo la chiusura (oggi neutralizzati da un guard di mercato: nessuna riga in `portfolio_cycles`
  dopo 19:52).
* Impatto: l'apertura — la finestra a maggiore densità informativa della seduta — è strutturalmente
  inosservabile. La sessione alpha-miss di questa data ha già attribuito 134,05 $ a questa finestra morta
  sul solo NOW (apertura 130,48 → prezzo alla prima barra utile 138,26 → chiusura 138,43: **l'intero
  movimento intraday cade prima del primo ciclo**).
* Severità: **High**
* Confidenza: **High**
* Azione consigliata: ticket di correttezza — derivare le finestre dal calendario Alpaca
  (`GetCalendarRequest`, già usato da `scripts/daily_alpha_miss_analysis.sh`) invece di codificare le ore UTC.
  Non è taratura: non sposta soglie, allinea l'orologio a quello dichiarato.
* Test/monitor consigliato: test parametrico su una data EDT e una EST che verifichi che il primo slot cada
  entro 10 minuti dall'apertura; monitor «minuti fra open RTH e primo ciclo» con alert oltre 15.

### [DAY-008] (F-019) La coda interna è il collo di bottiglia, e si autoalimenta: 155 item non tradabili filtrati solo dopo 45 minuti, 39 item scartati stale dopo una notte in coda

* Tipo: Bug
* Area: News / Ops
* Evidenza:
  * tabelle: dossier `timeline` (133 righe), `news_queue_drops`
  * snippet:
    ```
    mediane: published→first_seen 12,6 min | first_seen→ingested 46,1 min | published→scored 60,4 min
    news_queue_drops stadio 'sentiment' del 2026-08-27:
      not_tradable  155 righe, attesa media in coda 45,3 min
      stale          39 righe, attesa media in coda 324,8 min, età media 6,59 h (max 18,50 h)
    le 39 stale sono state accodate il 2026-08-26 alle 19:45 e scartate il 2026-08-27 alle 14:00:25
    ```
* Descrizione: due meccanismi si compongono. (a) Il filtro `not_tradable` (fuori watchlist) gira allo stadio
  *sentiment*, non allo stadio *ingestion*: 155 dei 303 item accodati da benzinga (51%) occupano la coda e il
  budget d'inferenza per ~45 minuti prima di essere scartati come non tradabili. (b) La coda non viene
  drenata alla chiusura: gli item accodati alle 19:45 restano in Redis tutta la notte e vengono scartati come
  `stale` al primo giro del mattino dopo, età 18,5 h. Il ritardo interno di 46 minuti — 76% della latenza
  totale — è quindi in buona parte auto-inflitto.
* Impatto: metà della capacità di scoring è spesa su simboli che non possono generare un ordine, e il ritardo
  che ne deriva spinge gli articoli genuini verso il confine della finestra di freschezza. Non isolo un costo
  in dollari: i miss di oggi muoiono sulla magnitudine, non sulla freschezza.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: ticket — applicare il filtro watchlist allo stadio di ingestione (come già fa
  `gdelt_gkg`, che scarta 1.991 `no_ticker` prima della coda) e drenare/invalidare la coda alla chiusura
  della seduta.
* Test/monitor consigliato: test che un item fuori watchlist non venga mai accodato da
  `_process_alpaca_items`; monitor `first_seen_to_ingested` p50 con alert oltre 20 min.

### [DAY-009] (F-012) Il 48% delle righe scorate nasce da fan-out multi-ticker e il 69% non è classificato

* Tipo: Bug
* Area: News / Signal
* Evidenza:
  * dossier `copertura_articoli`, `news_log`
  * snippet:
    ```
    69 articoli unici → 133 righe: 64 mapping fan-out extra (48,1%)
    articoli per numero di ticker: 41×1, 15×2, 2×3, 9×4, 1×8, 1×12
    mapping_rilevanza: UNKNOWN 92 | ISSUER_SPECIFIC 41 | SECTOR_MACRO 0 | FALSE_ENTITY_MATCH 0 | IRRELEVANT_FANOUT 0
    esempio: "Marvell Technology Could Swing $20.8 Billion After Earnings" → AFRM, BURL, DLTR, GAP, IREN, MRVL, PURR
    ```
* Descrizione: quasi metà delle righe scorate attribuisce a un ticker un articolo il cui soggetto è un altro
  emittente. Le tre categorie che servirebbero a riconoscerlo (SECTOR_MACRO, FALSE_ENTITY_MATCH,
  IRRELEVANT_FANOUT) hanno **zero** righe per il quinto giorno consecutivo: il classificatore non classifica.
* Impatto: il BUY di CRM delle 14:22 nasce da un articolo su NVDA; l'unico segnale FinBERT della giornata
  attribuisce a CRM un articolo su Adobe. I dollari sono già registrati su F-013/F-008.
* Severità: **High**
* Confidenza: **High**
* Azione consigliata: ticket — popolare effettivamente `mapping_rilevanza` (oggi il 69% è UNKNOWN) come
  prerequisito di qualunque gating per relevance, che resta gated su QX-01.
* Test/monitor consigliato: monitor giornaliero sulla quota UNKNOWN, con soglia di allarme.

### [DAY-010] (F-027) I log dei container non sopravvivono al redeploy: della seduta analizzata non resta una riga

* Tipo: Anomalia
* Area: Ops
* Evidenza:
  * `docker compose logs worker --since 48h --timestamps | head -1` → `2026-08-27T23:14:50.360Z`
  * `docker ps` → `alembic-worker-1`, `alembic-worker-inference-1`, `alembic-api-1`, `alembic-beat-1`
    creati `2026-08-28 01:14:41 +0200` = **2026-08-27 23:14:41 UTC**
* Descrizione: il redeploy delle 23:14 UTC ha azzerato i log dei worker. La seduta 13:30–20:00 non è
  ispezionabile: nessun log dello scheduler, dello scoring, dell'ensemble, del ranking, dei retry Celery.
  Le fasi 2/4/5 di questo report sono state ricostruite **esclusivamente** dai ledger append-only in
  Postgres (`s4_intent_events`, `execution_decisions`, `llm_responses`, `stop_shadow_log`).
* Impatto: rende non verificabili tre controlli richiesti: esito del regime detector, stato del circuit
  breaker, retry/timeout Celery. Tredicesima occorrenza.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: ticket ops — driver di logging persistente (file su volume o collector esterno) con
  retention ≥ 7 giorni.
* Test/monitor consigliato: check di readiness post-deploy che verifichi la presenza di log del giorno
  precedente.

### [DAY-011] (F-041) Il bearer token del protocollo forense è rifiutato su tutti gli endpoint REST

* Tipo: Bug
* Area: Frontend / Ops
* Evidenza:
  ```
  GET /api/decisions?limit=5 → 403 {"detail":"Invalid or expired JWT token"}
  GET /api/trades?limit=5    → 403   idem
  GET /api/signals?limit=5   → 403   idem
  GET /api/positions         → 403   idem
  GET /api/orders?limit=5    → 403   idem
  ```
* Descrizione: il token statico fornito al protocollo forense viene validato come JWT e rifiutato. Quarta
  occorrenza consecutiva. La sessione ha ricostruito tutto via SQL diretto.
* Impatto: la via d'accesso prevista dal protocollo non funziona; ogni sessione forense deve reimplementare
  le query. Se un giorno il DB non fosse raggiungibile, la giornata sarebbe interamente non verificabile.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: ticket — o un token di servizio a lunga scadenza per il protocollo forense, o
  aggiornare il protocollo alla modalità di autenticazione reale.
* Test/monitor consigliato: smoke test in CI che colpisca i 5 endpoint con il token documentato.

### [DAY-012] (F-036) Il trigger di revisione a −15% ha fatto firing su due posizioni e `mobile_events` è vuota da sempre

* Tipo: Bug
* Area: Risk / Ops
* Evidenza:
  * config: `config/trading.yaml:201` → `unprotected_position_alert_pct: 0.15`; `:180-181` «Revisit: if any
    position rides past -15/20% (d_hard shadow), wire d_hard to a real broker order»
  * tabelle: `stop_shadow_log`, `mobile_events`
  * snippet:
    ```
    ultimo ciclo del 2026-08-27, escursione dall'entry:
      AMAT (S1) entry 593,798 → 478,495 = −19,42%   d_hard 0,20 breached in 10 dei 24 cicli
      WDC  (S4) entry 549,24  → 460,05  = −16,24%
      4 posizioni oltre −10%, 2 oltre −15%, su 49 monitorate
    SELECT COUNT(*) FROM mobile_events;                       → 0
    SELECT COUNT(*) FROM stop_decisions WHERE created_at::date='2026-08-27'; → 0
    risk_reports.alerts del 22:30                             → []
    ```
    e il task gira regolarmente: `run_mobile_alert_evaluation … succeeded … {'status': 'ok', 'processed': 1}`
* Descrizione: la condizione di revisione documentata — resa machine-readable con #161 proprio perché era
  già scattata quattro volte senza che nessuno la sorvegliasse — si è verificata oggi su due posizioni.
  `mobile_events` non contiene **nemmeno una riga in tutta la sua storia**, benché
  `mobile-alert-evaluation` giri ogni minuto e ritorni `status: ok`. Il canale di allerta è inerte, non
  silenziato: valuta e non scrive.
* Impatto: nessuna condizione di rischio raggiungerà mai un operatore per questa via. L'assenza di stop
  protettivi è una decisione documentata e legittima (`stop_loss: 0.0`, evidenza Kimi 2026-07-15), ma quella
  decisione era condizionata all'osservazione del d_hard — e l'osservazione non produce alcun segnale.
* Severità: **High**
* Confidenza: **High**
* Azione consigliata: ticket di correttezza — verificare perché `run_mobile_alert_evaluation` restituisce
  `processed: 1` senza scrivere alcun evento, e aggiungere un canale di fallback (log a livello WARNING +
  riga in `risk_reports.alerts`) per il trigger −15%.
* Test/monitor consigliato: test d'integrazione che, data una posizione a −16%, produca esattamente una riga
  `mobile_events`; monitor «giorni consecutivi con 0 alert» con soglia.

### [DAY-013] (F-003 + F-050) Due valori di drawdown per la stessa giornata, e nessun drawdown per sleeve

* Tipo: Bug
* Area: Risk
* Evidenza:
  ```
  portfolio_monitor_snapshots 2026-08-27 20:00:00 → current_drawdown 0,005493  (0,55%)
  risk_reports                2026-08-27 22:30:01 → combined_drawdown 0,012429 (1,24%)
  risk_reports.per_strategy_metrics → {}
  risk_reports.alerts               → []
  righe risk_reports per la giornata → 1
  ```
* Descrizione: le due sorgenti che dovrebbero misurare la stessa grandezza differiscono di un fattore 2,26.
  Inoltre, dopo la rimozione dell'entry sintetica `portfolio` dal path per-strategy (#349),
  `per_strategy_metrics` è un oggetto vuoto: nessuna sleeve ha un drawdown misurato, quindi nessun kill-switch
  per sleeve può scattare. Una sola riga per l'intera giornata (22:30) rende impossibile ricostruire
  l'andamento del drawdown intraday.
* Impatto: il valore usato dal kill-switch non è determinabile dai dati persistiti, e il freeze impone di non
  toccare le soglie — quindi la protezione è, di fatto, non verificabile.
* Severità: **High**
* Confidenza: **High**
* Azione consigliata: ticket di correttezza — una sola definizione di drawdown, con la sorgente dichiarata
  nella riga; ripopolare `per_strategy_metrics` con il drawdown per sleeve calcolato su NAV per sleeve e non
  su notional di trade chiusi.
* Test/monitor consigliato: invariante — `|risk_reports.combined_drawdown − monitor.current_drawdown| < 0,001`
  a parità di timestamp; asserzione notturna.

### [DAY-014] (F-015) `trades.slippage_est` è una copia esatta di `cost_usd` su tutte le uscite

* Tipo: Bug
* Area: PnL
* Evidenza:
  ```
  trade 893: cost_usd 0,7525052875133793  slippage_est 0,7525052875133793
  trade 892: cost_usd 0,2743850975984010  slippage_est 0,2743850975984010
  trade 894: cost_usd 0,7511489302863590  slippage_est 0,7511489302863590
  ```
* Descrizione: il campo che dovrebbe misurare la differenza fra prezzo atteso e prezzo di fill contiene il
  costo modellato. Le due grandezze sono concettualmente indipendenti.
* Impatto: la qualità d'esecuzione non è misurata su nessun trade. In paper con fill immediato l'impatto
  monetario è nullo, ma la serie raccolta in questa finestra non potrà rispondere alla domanda
  «quanto costa eseguire» al passaggio al live.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: ticket — persistere la quota NBBO al momento dell'invio e calcolare
  `slippage = fill − mid_pre_invio`, oppure azzerare il campo dichiarandolo non misurato (meglio null che un
  valore sbagliato).
* Test/monitor consigliato: asserzione in CI che `slippage_est != cost_usd` su almeno un trade sintetico.

### [DAY-015] (F-011) `signal_id` NULL su tutte e tre le SELL, che hanno prodotto tutto il realizzato della giornata

* Tipo: Bug
* Area: Signal / Orders
* Evidenza:
  ```
  execution_decisions 2026-08-27: 513 righe, signal_id popolato su 17
    SKIP_THRESHOLD 487|0   SKIP_PYRAMIDING 14|12   BUY 5|5   SKIP_FALLBACK 4|0   SELL 3|0
  ```
* Descrizione: il testo del motivo cita esplicitamente il segnale che ha causato l'uscita («generated
  2026-08-27 14:45 UTC, score=+0.000») ma la chiave estera non è popolata. La catena
  segnale → decisione → ordine è ricostruibile solo per parsing di stringhe.
* Impatto: le tre uscite che hanno prodotto +20,40 $ di realizzato non sono agganciabili al segnale che le ha
  causate. Sedicesima occorrenza.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: ticket — popolare `signal_id` sul path SELL (l'id è già in mano al chiamante, dato che
  ne stampa `generated_at` e `score`).
* Test/monitor consigliato: invariante — ogni riga BUY/SELL di `execution_decisions` ha `signal_id NOT NULL`.

### [DAY-016] (F-007) `duplicates` (2.535) supera `fetched` (550) per `alpaca_benzinga`

* Tipo: Anomalia
* Area: News / Data
* Evidenza: `ingestion_stats_daily WHERE day='2026-08-27' AND source='alpaca_benzinga'` →
  `fetched 550, queued 303, duplicates 2535, discarded_stale 39`
* Descrizione: il contatore dei duplicati è 4,6× il numero di item raccolti. La lettura più probabile è che
  `duplicates` conti i tentativi di deduplicazione a livello di coppia (articolo, ticker) attraverso più
  passate, mentre `fetched` conta articoli. Le due unità di misura non sono confrontabili ma sono presentate
  nella stessa riga.
* Impatto: la riga statistica non è interpretabile come tasso di duplicazione, e il tasso di duplicazione è
  una delle metriche di qualità dell'ingest. Tredicesima occorrenza.
* Severità: **Low**
* Confidenza: **High**
* Azione consigliata: ticket — dichiarare l'unità di misura di ogni contatore o normalizzarli tutti ad
  articolo.
* Test/monitor consigliato: invariante `duplicates ≤ fetched × max_ticker_per_articolo`.

### [DAY-017] (F-016) Il fetch del benchmark SPY fallisce in modo permanente, con 6 retry al minuto e nessun alert

* Tipo: Anomalia
* Area: Data / Ops
* Evidenza:
  ```
  84 occorrenze in ~14 minuti (00:07–00:13 UTC del 28/08, batch notturno):
  WARNING SPY benchmark fetch failed: {"message":"subscription does not permit querying recent SIP data"}
  È l'UNICO tipo di WARNING/ERROR presente nella finestra di log disponibile (84/84 righe).
  ```
* Descrizione: limite di sottoscrizione dati, quindi non correggibile in codice. Ma il chiamante ritenta 6
  volte al minuto per la durata del batch e degrada a WARNING senza mai emettere un alert né marcare la
  metrica come indisponibile. Il confronto S1-vs-SPY del ledger economico
  (`spy_benchmark_usd 343,82`) proviene da un'altra fonte e resta valido.
* Impatto: i log della giornata — quando esistono — sono saturati da un errore noto, che maschera errori
  nuovi. Nessun impatto sul money-path.
* Severità: **Low**
* Confidenza: **High**
* Azione consigliata: ticket — un solo tentativo con esito memoizzato per la giornata e la metrica marcata
  `UNAVAILABLE` invece di ritentata.
* Test/monitor consigliato: nessuno; il monitor utile è la soglia sul rapporto WARNING/riga di log.

### [DAY-018] (F-010) `llm_responses.eligible` contraddice l'eleggibilità realmente applicata

* Tipo: Bug
* Area: LLM / Data
* Evidenza:
  ```
  sig 9124 PANW, model_id del segnale = single:gpt-oss:20b-cloud, score +0,6375 = 0,85 × 0,75
    llm_responses: gpt-oss:20b-cloud polarity 0,85 confidence 0,75 eligible = FALSE
                   glm-5.2:cloud     polarity 0,00 confidence 0,10 eligible = FALSE
  → il segnale è stato prodotto da un modello che la tabella marca come non eleggibile.
  Aggregato: 88/133 righe per modello con eligible=false (66,2%).
  ```
* Descrizione: il flag persistito non è quello valutato al momento dell'aggregazione. Undicesima occorrenza,
  qui con una falsificazione diretta: un modello marcato non eleggibile ha prodotto un segnale tradabile.
* Impatto: qualunque analisi di eleggibilità sui dati di questa finestra è falsa; in particolare non si può
  ricostruire dai dati *perché* un segnale è finito in fallback.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: ticket — scrivere in `eligible` esattamente il predicato usato in
  `ensemble.py:293`, o rinominare il campo in ciò che effettivamente misura.
* Test/monitor consigliato: invariante — se `sentiment_signals.model_id LIKE 'single:%X'`, la riga
  `llm_responses` del modello X per quel segnale deve avere `eligible = true`.

### [DAY-019] (**F-055, nuovo**) L'output strutturato del modello è persistito senza validazione di enum: un valore contiene uno zero-width space

* Tipo: Bug
* Area: LLM / Data
* Evidenza:
  * file: `src/models/news.py:106-109` — `directness: str = Field(default="direct", description="direct|customer_supplier|…")`, nessun `Literal`, nessun validator
  * tabella: `llm_responses`
  * snippet:
    ```
    SELECT id, encode(convert_to(directness,'UTF8'),'hex') FROM llm_responses
     WHERE directness NOT IN ('direct','customer_supplier','competitor_readthrough','sector','macro','unclear');
      14392 | 756e636c e2808b 656172   ← "uncl" + U+200B ZERO WIDTH SPACE + "ear"
          - | competitor_readthrough|macro

    event_type fuori enum in agosto: 'sector' ×3, 'earnings|guidance' ×1
    Totale: 6 valori fuori enum su 6.057 righe (agosto).
    ```
* Descrizione: i campi `directness` e `event_type` sono stringhe libere. Il modello ha emesso
  `"uncl​ear"` — visivamente identico a `"unclear"` — e la riga è stata persistita. CLAUDE.md prescrive
  la normalizzazione degli homoglyph e la rimozione di testo nascosto **in ingresso**; il percorso in uscita
  non ha né sanitizzazione né validazione di enum, benché sia proprio quello che alimenta le decisioni.
* Impatto: **oggi latente**, non monetario. `directness` alimenta
  `ticker_resolver.directness_multiplier()` (che ritorna 0.0 per chiavi ignote) e la regola
  `directness == "unclear" → NO_TRADE_*`; un token corrotto **manca entrambi i rami**: non è riconosciuto
  come `unclear` (quindi non produce il NO_TRADE) e riceve moltiplicatore 0,0. Il resolver è oggi invocato
  solo da `resolver_shadow.py`, quindi l'effetto è confinato all'osservazione — ma l'enforcement del resolver
  è esattamente ciò che QX-01 sta preparando, e a quel punto il difetto diventa money-path.
* Severità: **Low** oggi, **High** all'attivazione dell'enforcement
* Confidenza: **High**
* Azione consigliata: ticket di correttezza a bassa priorità — tipizzare `directness`/`event_type` come
  `Literal[...]` con coercizione via NFKC + strip dei caratteri di controllo, e un ramo esplicito
  `INVALID_ENUM` invece del fallback silenzioso al default. Da chiudere **prima** di attivare l'enforcement
  del resolver.
* Test/monitor consigliato: test che `"uncl​ear"` venga normalizzato a `"unclear"` o rigettato
  esplicitamente; check notturno `COUNT(*) WHERE directness NOT IN (enum)` = 0.

### [DAY-020] (F-040) Cinque segnali ribassisti superano il gate col segno corretto e non producono nulla

* Tipo: Osservazione
* Area: Signal
* Evidenza:
  ```
  META 16:46 −0,4977 → titolo −0,87%   (segno corretto)
  XLF  18:30 −0,4900 → titolo −0,65%   (segno corretto)
  AMD  15:47 −0,3500 → titolo −0,89%   (segno corretto)
  META 19:45 −0,3056 → titolo −0,87%   (segno corretto)
  NVDA 14:15 −0,4050 → titolo +8,74%   (segno SBAGLIATO, 8 min dopo la BUY delle 14:07)
  ```
  Il filtro è `ranking.py:229-235` → `if strength <= 0: RANK_LONG_ONLY`.
* Descrizione: S4 è long-only per design, quindi i segnali ribassisti sono scartati anche quando superano il
  gate in modulo. Quattro su cinque avevano il segno corretto. Non è un difetto: è il perimetro dichiarato
  della strategia. Lo registro perché è l'unico modo di quantificare il costo del vincolo long-only nella
  finestra di osservazione.
* Impatto: non stimabile come costo — un ramo short non esiste e non è nel perimetro. Va registrato come
  informazione per la sintesi del 28/09.
* Severità: **Low**
* Confidenza: **High**
* Azione consigliata: nessuna azione, nessun ticket. Materiale per la sintesi.
* Test/monitor consigliato: metrica giornaliera «hit-rate dei segnali ribassisti sopra gate», da leggere alla
  sintesi.

### [DAY-021] (F-037) Tre segnali con `ensemble_std ≥ 0,30` passano senza alcun trattamento

* Tipo: Bug
* Area: LLM / Risk
* Evidenza: `SELECT COUNT(*) FROM sentiment_signals WHERE generated_at::date='2026-08-27' AND ensemble_std >= 0.3` → **3**
  (AMZN 0,354 · CRM 0,318 · CRM 0,283+). Nessun ramo del codice legge `ensemble_std` come gate d'ingresso a
  valle dell'aggregatore.
* Descrizione: la varianza d'ensemble è telemetria, non un controllo. Con [DAY-004] il quadro completo è: il
  controllo che esiste (dentro l'aggregatore) è aggirabile, e a valle non ce n'è nessuno.
* Impatto: nessuno oggi in dollari — i 3 segnali non hanno generato ordini. Rilevante come struttura.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: nessun ticket in finestra di osservazione (introdurre un gate è **taratura**). Va
  invece corretta la *misura* → [DAY-004].
* Test/monitor consigliato: già coperto dal monitor di [DAY-004].

---

## 11. False positive e aree risultate corrette

| area | verifica | esito |
|---|---|---|
| **Discrepanza `s4_intent_events` ↔ `execution_decisions`** | il ledger registra 106 `SKIP_PYRAMIDING` e 98 `SKIP_FALLBACK`; `execution_decisions` solo 14 e 4 | **FALSO POSITIVO.** Le due tabelle hanno grana diversa per design: il ledger scrive per (candidato, slot), `execution_decisions` una volta per (simbolo, segnale) dopo il ciclo (`portfolio_scheduler.py:2855-2857`). Sui gate confrontabili i conteggi coincidono esattamente: `SKIP_ENTRY_GATE` 487 = `SKIP_THRESHOLD` 487. **Non è F-006.** |
| **Assenza di stop-loss** | `stop_decisions` vuota dal 2026-07-14, 48 posizioni senza protezione | **CORRETTO E DOCUMENTATO.** `config/trading.yaml:172-183`: decisione 2026-07-15 con evidenza OOS (no_protective −56 $ vs fixed_2pct −419 $). `stop_shadow_enabled: true` produce 1.131 righe di osservazione. Il difetto non è lo stop assente, è che l'osservazione non genera alert → [DAY-012]. |
| **`hold_minimum_minutes` / `exit_persistence_cycles`** | entrambi i round trip CRM durati esattamente 105 min | **FUNZIONANTE.** FIX-B e l'isteresi hanno differito le uscite come previsto. Nota di lettura: hanno *differito*, non *evitato* — la tenuta mediana di 1,75 h nel dossier è il parametro, non il segnale. |
| **Ordini fuori orario** | 8 slot beat schedulati dopo la chiusura (20:07–21:52) | **NESSUN ORDINE.** Zero righe in `portfolio_cycles` dopo 19:52 — il guard di mercato ha funzionato. Il difetto DST è sul lato apertura, non chiusura. |
| **Idempotenza** | 1 `SIGNAL_DUPLICATE_SKIP`, 1 `SKIP_IDEMPOTENCY` | **FUNZIONANTE.** Il ramo fail-closed su Redis assente (P2-05-A) non è stato attivato. |
| **`score = polarity × confidence`** | verificato su 9124 (0,85 × 0,75 = 0,6375) e su tutti i single-model | **CORRETTO.** Nessun doppio conteggio della confidence nel ranker (`ranking.py:229-231`). |
| **LLM nel trading loop** | `grep` su `portfolio_scheduler.py` e `orchestrator.py` | **NESSUNA chiamata LLM sincrona.** Lo scoring gira su queue `inference` con `crontab(*/15)`; il ciclo legge da Postgres. Conforme al vincolo architetturale. |
| **Timestamp futuri** | `COUNT(*) WHERE published_at > fetched_at` | **0.** Nessun `published_at` NULL. |
| **Timezone di sistema** | `celery_app.py:51-52` | **UTC esplicito, nessuna ambiguità.** Il difetto è nelle *finestre*, non nel fuso. |
| **Riconciliazione fill** | 138 righe di timeline, `order_lookup_error` | **0 errori.** Tutti gli 8 ordini con order_id, prezzo di fill e timestamp. |
| **Ordini senza segnale (F-042)** | tutte e 5 le BUY | **NESSUNO.** `signal_id` popolato su tutte. Il difetto simmetrico è sulle SELL → [DAY-015]. |
| **F-043 (tutti i segnali sopra gate sono rialzisti)** | 5 segnali ribassisti sopra gate | **NON SI RIPETE oggi.** Vedi [DAY-020]. |

---

## 12. Dati mancanti o non accessibili

| dato | perché manca | query/azione che servirebbe |
|---|---|---|
| Latenza per modello LLM | `llm_responses` non ha colonna di durata; log della seduta perduti | aggiungere `latency_ms` a `llm_responses`; poi `percentile_cont(0.5) … GROUP BY model_id` |
| Slippage vero (fill vs quota) | `trades` non conserva il riferimento pre-invio; `slippage_est` è una copia di `cost_usd` | persistere `nbbo_mid_at_submit`; `SELECT entry_price - nbbo_mid_at_submit FROM trades` |
| Esito del regime detector 07:00/13:30 | log perduti; `regime:current` non ha storico in DB | `regime_mult = 0,7` osservato su tutte le decisioni è l'unica prova indiretta; persistere l'esito in `audit_log` |
| Stato del circuit breaker durante la seduta | nessuna tabella; log perduti | F-049/F-050 già documentano l'inerzia; servirebbe una riga per transizione di stato |
| Retry/timeout Celery | log perduti | driver di logging persistente ([DAY-010]) |
| Endpoint REST (`decisions/trades/signals/positions/orders`) | 403 su tutti e 5 ([DAY-011]) | token di servizio per il protocollo forense |
| Drawdown intraday | 1 sola riga `risk_reports` per la giornata (22:30) | schedulare `risk-report` con la cadenza dei cicli, o almeno open/close |
| `per_strategy_metrics` | `{}` ([DAY-013]) | ripopolare con NAV per sleeve |
| `guard_cost_usd` / `guard_avoided_loss_usd` del dossier | `None`: il notional inteso è null su tutti i guard tranne `SKIP_PYRAMIDING` post-2026-08-19 | `intended_notional_usd` va popolato sui rami `SKIP_THRESHOLD` |
| Ripartizione fill parziali | `exit_order_ids` non ispezionato in questa sessione; F-048 documenta divergenze DB↔broker sul book preesistente | riconciliazione per `exit_order_ids` unnest vs Alpaca `get_orders` |
| Log frontend | non ispezionati (container `alembic-frontend-1` su da 08-15, nessuna anomalia segnalata dal money-path) | `docker compose logs frontend` — non rilevante per questa giornata |

---

## 13. Raccomandazioni immediate

1. **Non correggere nulla che sia taratura.** Siamo al giorno 18 di 40 della finestra di osservazione
   (`docs/evidence/OBSERVATION_CHARTER.md`). Banda d'uscita, soglie, gate di varianza: tutto congelato al 28/09.
2. **Priorità 1 — [DAY-006] righe di test in produzione.** È l'unico difetto che contamina direttamente la
   serie che verrà letta alla sintesi. Le 10 righe fixture del 27/08 vanno segnalate come tali, non cancellate
   (append-only), e la suite va isolata.
3. **Priorità 2 — [DAY-004] guard di divergenza aggirato.** Non introdurre un gate nuovo (taratura): correggere
   la **misura**, persistendo lo spread reale su tutti i modelli che hanno risposto. Senza questo, i 40 giorni
   non conterranno alcun dato utilizzabile sulla varianza d'ensemble.
4. **Priorità 3 — [DAY-001] il punteggio neutro non è un contro-segnale.** È la stessa forma logica già
   accettata come deroga per #236: un'assenza di informazione non deve chiudere una posizione. Con tre uscite
   su tre innescate così e 34,80 $ misurati in una sola seduta, ogni giorno di attesa aggiunge rumore alla
   domanda d'uscita n.1.
5. **Priorità 4 — [DAY-012] canale di allerta inerte.** Due posizioni oltre il trigger documentato di revisione
   e zero eventi in tutta la storia della tabella. È strumentazione, non taratura: nessuna deroga necessaria.
6. **[DAY-007] finestre DST.** Allineare al calendario Alpaca. 37 minuti di apertura ciechi ogni giorno di
   EDT, e la finestra contiene sistematicamente i mover della giornata.
7. **Non toccare** `stop_loss: 0.0`, `hold_minimum_minutes`, `exit_persistence_cycles`, la soglia 0,30, il
   `SIGNAL_VELOCITY_BOOST`. Tutto taratura.

## 14. Test o monitor da aggiungere

| # | tipo | descrizione | anomalia coperta |
|---|---|---|---|
| 1 | test unitario | due output con polarity 0,85/0,00 e conf 0,75/0,10 → spread persistito ≥ 0,40, non `std=0,0` | [DAY-004] |
| 2 | invariante notturna | `portfolio_monitor_snapshots`: 0 righe con `source IS NULL`; `ingestion_stats_daily`: 0 righe con `source` non abilitata | [DAY-006] |
| 3 | invariante CI | per ogni `decision_slot`, `rank` monotono nello score usato per l'ordinamento | [DAY-005] |
| 4 | test unitario | due segnali dello stesso simbolo entro 60 s → il ranker sceglie quello a punteggio maggiore | [DAY-003] |
| 5 | test integrazione | posizione aperta su score ≥ gate non chiusa da un segnale con `\|score\| < 0,05 AND conf < 0,3` | [DAY-001] |
| 6 | test integrazione | posizione a −16% → esattamente una riga `mobile_events` | [DAY-012] |
| 7 | test parametrico | primo slot beat entro 10 min dall'apertura, su una data EDT e una EST | [DAY-007] |
| 8 | invariante | ogni riga BUY/SELL di `execution_decisions` ha `signal_id NOT NULL` | [DAY-015] |
| 9 | invariante | `\|risk_reports.combined_drawdown − monitor.current_drawdown\| < 0,001` a timestamp confrontabile | [DAY-013] |
| 10 | check notturno | `COUNT(*) FROM llm_responses WHERE directness NOT IN (enum)` = 0 | [DAY-019] |
| 11 | monitor | round trip per simbolo per seduta > 1 → alert | [DAY-002] |
| 12 | monitor | `first_seen_to_ingested` p50 > 20 min → alert; item fuori watchlist mai accodati | [DAY-008] |
| 13 | monitor | quota `mapping_rilevanza = UNKNOWN` sopra soglia → alert | [DAY-009] |
| 14 | readiness post-deploy | presenza di log del giorno precedente | [DAY-010] |
| 15 | smoke test CI | i 5 endpoint REST rispondono 200 col token documentato | [DAY-011] |
| 16 | monitor | giorni consecutivi con 0 righe in `mobile_events` → alert | [DAY-012] |

## 15. Ticket tecnici suggeriti

Solo difetti di **correttezza** (test della carta: «se non lo correggo, l'evidenza raccolta nelle prossime
settimane è sbagliata?»). Nessuna taratura.

| # | titolo | tier | motivazione dell'esenzione | anomalia |
|---|---|---|---|---|
| T-1 | **La suite di test non deve scrivere nel DB di produzione** — isolare `portfolio_monitor_snapshots` e `ingestion_stats_daily` | tier0 | Righe fixture dentro la serie osservata: l'evidenza del 28/09 conterrebbe dati inventati. Passa il test. | [DAY-006] |
| T-2 | **Persistere lo spread di polarity su tutti i modelli che hanno risposto**, non solo sugli eleggibili | tier1 | `ensemble_std = 0` nei casi di disaccordo massimo rende falsa ogni analisi di varianza sulla finestra. Passa il test. Correzione di misura, non di soglia. | [DAY-004], [DAY-021] |
| T-3 | **Un punteggio neutro a bassa confidence non azzera il target di una posizione aperta** | tier1 | Stessa forma logica della deroga #236 già concessa: distinguere «neutro» da «assente». Tre uscite su tre innescate così, 34,80 $ in una seduta. Passa il test. | [DAY-001] |
| T-4 | **La deduplicazione per simbolo del ranker deve incorporare convinzione e relevance, non solo la freschezza** | tier1 | Finché il riferimento è scelto per ordine d'arrivo in coda, i 40 giorni misurano la latenza della coda e non il segnale. Passa il test. | [DAY-003] |
| T-5 | **Le finestre beat vanno derivate dal calendario Alpaca, non da ore UTC fisse** | tier1 | 37 min di apertura ciechi ogni giorno EDT: allineamento all'orologio dichiarato, non nuova taratura. Passa il test. | [DAY-007] |
| T-6 | **Lo snapshot del ledger #294 deve persistere lo score usato per l'ordinamento** oltre a quello grezzo | tier1 | Il ledger scritto per rendere ricostruibile la selezione non la ricostruisce. Passa il test. | [DAY-005] |
| T-7 | **`run_mobile_alert_evaluation` ritorna `ok` senza scrivere eventi**: canale di allerta inerte + fallback su `risk_reports.alerts` | tier1 | Strumentazione: non cambia cosa compriamo né con che size. Due posizioni oltre il trigger documentato oggi. | [DAY-012] |
| T-8 | **Una sola definizione di drawdown** + ripopolare `per_strategy_metrics` | tier1 | Il valore usato dal kill-switch non è determinabile dai dati persistiti. Passa il test. | [DAY-013] |
| T-9 | **Popolare `signal_id` sulle decisioni SELL** | tier2 | L'id è già in mano al chiamante (ne stampa `generated_at` e `score`). Auditabilità della catena. | [DAY-015] |
| T-10 | **`llm_responses.eligible` deve riflettere il predicato applicato in `ensemble.py:293`** | tier2 | Un modello marcato non eleggibile ha prodotto un segnale tradabile: il campo mente. | [DAY-018] |
| T-11 | **Filtrare la watchlist allo stadio di ingestione** e drenare la coda alla chiusura | tier2 | Metà della capacità di scoring spesa su simboli non tradabili; 39 item scartati stale dopo una notte in coda. | [DAY-008] |
| T-12 | **Tipizzare `directness`/`event_type` come `Literal` con normalizzazione NFKC**, da chiudere prima dell'enforcement del resolver | tier2 | Latente oggi (resolver in shadow), money-path all'attivazione di QX-01. | [DAY-019] |
| T-13 | **Persistere la quota NBBO all'invio** e calcolare lo slippage vero (o azzerare il campo) | tier3 | La finestra non potrà rispondere a «quanto costa eseguire» al passaggio al live. | [DAY-014] |
| T-14 | **Driver di logging persistente** con retention ≥ 7 giorni | tier2 | Senza log, tre controlli obbligatori del protocollo forense sono non verificabili ogni giorno. | [DAY-010] |
| T-15 | **Token di servizio per il protocollo forense** sui 5 endpoint REST | tier3 | Quarta occorrenza; la via d'accesso prevista dal protocollo non funziona. | [DAY-011] |
| T-16 | **Dichiarare l'unità di misura dei contatori di `ingestion_stats_daily`** | tier4 | `duplicates` 4,6× `fetched`: la riga non è interpretabile. | [DAY-016] |
| T-17 | **Memoizzare l'esito del fetch SPY** e marcare la metrica `UNAVAILABLE` | tier4 | 84 WARNING identici saturano i log e mascherano errori nuovi. | [DAY-017] |

## 16. Stato sistema

| voce | valore |
|---|---|
| **Ollama up/down** | **UP tutta la seduta.** Entrambi i modelli hanno prodotto 133 risposte su 133; zero timeout, zero refusal, zero parse failure. **Ore di downtime: 0.** |
| **Degrado parziale** | finestra 18:00–19:00 UTC al 70,0% di single-model (14/20). Ensemble pieno per ora: 14:00 15/19 · 15:00 15/22 · 16:00 17/23 · 17:00 23/26 · **18:00 6/20** · 19:00 18/23 |
| **`fallback_used` rate** | **29,3% (39/133)** — contro l'81,6% del 2026-08-26 |
| **Fallback FinBERT vero** | **1 solo segnale** (id 9171, CRM, 18:46:38) = **0,8%**. Gli altri 38 sono degradi a modello singolo, non FinBERT |
| **Fallback rate sulle decisioni** | 4 `SKIP_FALLBACK` su 513 decisioni (0,8%). **Nessuno dei 5 BUY è nato da un segnale in fallback** |
| **Modelli attivi** | Redis `config:sentiment_llm_models = "glm52,gptoss"` — corretto, nessun reset a "all" |
| **Gate d'ingresso** | Redis `feedback:entry_threshold:S4 = 0.3` — al baseline, nessun ratchet in corso |
| **Worker restart** | **1 evento**: tutti i container applicativi (`worker`, `worker-inference`, `api`, `beat`) ricreati **2026-08-27 23:14:41 UTC**, dopo la chiusura. Nessun restart durante la seduta. `postgres`/`redis` up dal 2026-05-21, `frontend` dal 2026-08-15 |
| **Cicli portfolio** | 24/24 attesi fra 14:07 e 19:52. Zero salti, zero eccezioni registrate |
| **Circuit breaker** | **non verificabile** (nessuna traccia in DB, log della seduta perduti). F-049/F-050 documentano che è inerte |
| **Alert consegnati** | **0.** `mobile_events` vuota, `risk_reports.alerts = []`, e due posizioni oltre il trigger documentato di revisione |

---

*Report generato in modalità read-only. Nessun file di codice modificato, nessun ordine inviato, nessun*
*worker avviato. Ledger delle evidenze aggiornato in `docs/evidence/findings.json`.*
