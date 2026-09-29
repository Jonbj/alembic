# Forensic Daily Report — 2026-09-21

Sessione forense autonoma, sola lettura, eseguita il 2026-09-29 (a posteriori: il forense del 21/09 non
era mai stato scritto, vedi F-026 / DAY-028 del report 22/09). Fuso operativo **UTC**
(`src/workers/celery_app.py`, `timezone="UTC"`, `enable_utc=True`): tutti i timestamp sono UTC.
Seduta RTH 13:30–20:00 UTC (EDT). Conto **paper** verificato, non assunto:
`portfolio_monitor_snapshots.broker_environment='paper'`, `mode='paper'` su tutte le istantanee del giorno;
`execution.engine=portfolio` (log 14:00:00 «legacy execution worker inactive»).

Periodo di **sola osservazione** (`docs/evidence/OBSERVATION_CHARTER.md`, scadenza 2026-09-28): nessuna
taratura proposta. I ticket suggeriti riguardano solo difetti di correttezza/strumentazione.

Contesto di deploy: il riconciliatore ha ricostruito il backend due volte prima dell'apertura —
**08:20Z** `ed53c851 → 16c1ed95` (16 commit, contiene `edfd73e0`: fix F-076 entità HTML nel prompt e
F-054 divergenza d'ensemble) e **10:20Z** `16c1ed95 → 44451ca6` (7 commit). È quindi la **prima seduta**
con il fix F-076/F-054 live. Ensemble live: `glm-5.2:cloud` + `gpt-oss:20b-cloud` (lo swap a GLM-5.3 è del 22/09).

Fonte complementare già esistente per la stessa data: `docs/ALPHA_MISS_REPORT_2026-09-21.md` (dossier
`docs/evidence/dossier/2026-09-21.json`, schema 3.1). Dove un evento è già stato prezzato lì, l'occorrenza
forense nel ledger ha `costo_usd: null` per non contarlo due volte (stessa convenzione del 18/09).

---

## 1. Executive summary

La pipeline ha girato end-to-end: 189 righe scorate (177 Benzinga WS + 12 GDELT, 122 articoli distinti)
→ 189 segnali → 24 cicli portfolio → **5 BUY e 3 SELL S4**, tutti `filled` sul conto paper e riconciliati
col broker (resta lo scarto UNH di 1 azione, già noto). Nessun ordine fuori orario, duplicato, senza segnale
o su segnale stale; idempotenza dei retry verificata (21 `SKIP_IDEMPOTENCY`, 21 `SIGNAL_DUPLICATE_SKIP`).
Ollama è rimasto su tutta la seduta (21 timeout per-modello, 9 fallback FinBERT reali = 4,8% dei segnali,
nessuno ha generato un ordine). NAV 110.027,02 $ (+593,85 $, +0,54%) con SPY +1,55%. S4 realizzato +10,94 $.

Tre problemi di correttezza pesano sull'evidenza della seduta. (1) Entrambi i giri di `detect_regime`
falliscono (FRED timeout 07:00, 502 alle 13:30) e risultano `succeeded`; senza `regime:current` **tutti i
24 cicli** applicano il fallback ×0,20 «vix=absent» con VIX a 14,87: ogni ingresso S4 è a ~420 $ invece di
~1.540 $ (F-017, nessun alert). (2) **NVO comprata** alle 14:07 su un titolo senza corpo (+0,295, corpo =
un URL) 16 minuti dopo un −0,435 motivato dal crollo pre-market sui trial CagriSema, con il titolo già a
−7,4%: S4 legge solo l'ultimo segnale (F-023). (3) **Regressione di latenza 6×**: 61 s per articolo
(10 s il 18/09), pubblicazione→segnale mediana 10,4 min (0,7 il 18/09), primo giorno della serie (F-019).

## 2. Verdict

**OK con warning.**

Il percorso del denaro è corretto: ogni ordine ha segnale, gate, risk check (anti-pyramiding, idempotenza,
hold minimo, isteresi d'uscita) e fill riconciliato. I warning non bloccano ma rendono **parziale**
l'evidenza S4 del giorno: la size è fissata dalla disponibilità di FRED e non dal regime (F-017), e
l'ingresso NVO dimostra che un segnale forte di segno opposto viene ignorato se ne arriva uno più recente.
La regressione di latenza non ha ancora causa attribuibile (F-086: nessuna traccia di trasporto Ollama).

---

## 3. Timeline del 2026-09-21 (UTC)

| Ora | Componente | Evento | Esito | Fonte |
|---|---|---|---|---|
| 00:00–13:29 | `worker-news-stream` | WS Alpaca/Benzinga 24/7; 95 dispatch di `run_sentiment_worker` fuori seduta | tutti `market_closed`; 470 `duplicate_id` WS accodati off-session | log inference, `news_queue_drops` |
| 04:00:00 | Telegram | alert notturno | **400 Bad Request** | `worker-2026-09-21.log` |
| 07:00:15 | `detect_regime` | FRED «read operation timed out» | task `succeeded in 15.6s: None` | `worker-inference-2026-09-21.log` |
| 08:20:03–08:20:37 | deploy | `ed53c851 → 16c1ed95` (16 commit, fix F-076/F-054) | worker/inference ripartiti 08:20:18 | `logs/deploy_reconcile_2026-09-21.log` |
| 10:20:03–10:20:37 | deploy | `16c1ed95 → 44451ca6` (7 commit) | ripartiti 10:20:17 | idem |
| 13:30:01 | `mobile_alert_evaluation` | `pipeline:portfolio_cycle_late` **CRITICAL** + `pipeline:signal_stale` WARNING | recuperati 14:08:00 / 13:33:01 | `mobile_events` |
| 13:30:04 | `detect_regime` | FRED T10Y2Y **502** (URL con `api_key` in chiaro nel log) | `succeeded in 4.6s: None` → `regime:current` assente per tutta la seduta | log inference |
| 13:32:43 | `sentiment` | prima riga `news_log`/segnale | primo task: 7 processati, **295 `stale`** della coda notturna | `sentiment_signals`, log inference |
| 13:34:00 | `sentiment` | GM +0,420 («What To Watch Before Buying The Stock», recap di un PT UBS; glm `already_priced_in`) | sopra gate, poi bloccato da P0-05 | segnale 11807 |
| 13:46:40 | `sentiment` | **NVO −0,435** (ensemble; crollo pre-market sui trial CagriSema) | sotto gate short (long-only) | 11811 |
| 14:02:38 | `sentiment` | **NVO +0,295** su titolo del Capital Markets Day, corpo = URL | diventa l'ultimo segnale NVO | 11824 |
| 14:04:46 | `sentiment` | META +0,409 (Wells Fargo PT 640→796) | sopra gate | 11827 |
| **14:07:00** | `portfolio-cycle` 1586 | primo ciclo (37 min dopo l'apertura); `P0-09: regime:current absent — ×0.20` | BUY META, BUY NVO; GM SKIP_PYRAMIDING; 3 SKIP_STALE; 6 SKIP_FALLBACK | `execution_decisions`, log worker |
| 14:07:05–08 | broker | BUY META 0,5906 @712,616 · BUY NVO 10,5912 @39,7366 (nozionale 420,87 $ ciascuno) | `filled` | ordini `76881455`, `a9a52b29` |
| 14:07:06 | Telegram | alert #161 (AMAT −21%, WDC −19% senza stop) | **400 Bad Request** ×2 | log worker |
| 14:11:52 | FinBERT | fallback per divergenza (SPY) | polarity 0,02 | `finbert_fallback_events` 16 |
| 14:22:00 | S4 → broker | BUY HOOD 3,4023 @122,78 (segnale 11842 +0,399) | `filled` 14:22:07; stop NVO 10/10,59 sh | trade 1020 |
| 14:37:07 | stop sync | stop HOOD 3/3,40 sh | poi `canceled` alla SELL | ordine `f56f4b97` |
| 14:47 / 14:49 | `sentiment` | NVO −0,036 (ensemble) / NVO **−0,595** (single glm, `fallback_used`) | S4 usa il −0,036 (preferenza non-fallback, F-056) | 11864 / 11865 |
| 14:52:04 | S4 gate | NOK +0,333 → SKIP_PYRAMIDING (posizione S1 da **6,12 $**) | nessun ordine | decisione 35679 |
| 15:15:20 | `sentiment` | META +0,435 ISSUER_SPECIFIC | SKIP_PYRAMIDING 15:22 (META già S4) | 11884 / 35874 |
| 15:34:40 | `sentiment` | **AMD +0,710** («Hits Fresh Record High») | SKIP_PYRAMIDING 15:37 (S1 497,50 $) | 11896 / 35973 |
| 15:37:00 | S4 → broker | BUY ARM 1,3104 @315,584 (11898 +0,581 × 1,2) + stop 1 sh | `filled`; isteresi: NVO flag 1/2 | trade 1021 |
| 15:52:00 | S4 → broker | SELL NVO @39,85 `below_entry_gate` (−0,036) | net **+0,97 $** (`hold_minimum_expiry`) | trade 1019 |
| 15:52 | `sentiment` | META 11904 +0,027 FANOUT («$6.51 Diesel…»); isteresi HOOD+META | — | log worker |
| 16:07:00 | S4 → broker | SELL HOOD @124,12 (+0,183) · SELL META @722,284 (+0,027) | net **+4,33 $** / **+5,63 $** | trade 1020 / 1018 |
| 16:22:00 | S4 → broker | BUY NOW 2,9791 @137,54 (11920 +0,314 × 1,2, PT Cantor 141→174) | `filled`; stop 2 sh alle 16:37 | trade 1022 |
| 17:07 / 17:22 / 18:07 | S4 gate | SKIP_PYRAMIDING JPM +0,343 (S1), INTC +0,409 (S4), QQQ +0,399 (S4) | nessun ordine | `execution_decisions` |
| 18:34:12 | `sentiment` | INTC +0,640 single gpt-oss | già a libro S4 | 11972 |
| 19:37:01 | alert | `pipeline:signal_stale` WARNING | recuperato 19:46:01 | `mobile_events` |
| 19:49:40 | `sentiment` | ultimo segnale | — | `sentiment_signals` |
| 19:52:00 | `portfolio-cycle` 1609 | ultimo ciclo (24 totali) | ok | `portfolio_cycles` |
| 20:00:00 | snapshot | NAV 110.027,02 $, **+593,85 $**, 45 posizioni | — | `portfolio_monitor_snapshots` |
| 21:00 | `decay_monitor` | 7 righe **DECAY CRITICAL** (S1/S2/S4 stesso IC −0,044) | solo log | log worker |
| 21:35:02 | `reconcile-positions` | 44 `fully_held` + 1 `partially_wound_down_coheld` (UNH), anomalies 0 | — | log worker |
| 21:57:06 | `reconcile_fills_intraday` | 0 fill aggiornati; 20 eventi lifecycle S4 | ok | log worker |
| 22:13–22:49 | host | «Network is unreachable» sul poller Telegram (18 errori) | nessun job di trading coinvolto; shadow 22:20 ok (28 scorati) | log inference |
| 22:50:00–01 | alert | `portfolio_cycle_session_grid`, `held_no_news_loss` SBUX/VALE | **aperti e chiusi in 1 s** | `mobile_events` |
| 23:05:00 | Telegram | alert serale | **400 Bad Request** | log worker |

---

## 4. News ingest

### 4.1 Per fonte

| Fonte | Trasporto | Estrazione | Righe scorate | Articoli | Ticker | Prima–ultima riga | Lag pub→riga (mediana) | Fetched (stats) | Duplicati (stats) | Scarti |
|---|---|---|---|---|---|---|---|---|---|---|
| alpaca_benzinga | ws | source_metadata | 177 | 111 | 55 | 13:32:43–19:49:40 | 14,8 min | 1.514 | **6.753** | 547 stale (stats); drop: 295 stale off-session + 252 stale REST, 192 not_tradable |
| gdelt_gkg | — | org_lookup | 12 | 11 | 6 | 14:47:14–19:49:28 | 12,9 min | 1.896 | 4 | 1.881 no_ticker |

* Timestamp futuri (`published_at > created_at`): **0**. `discarded_reason` sulle righe scorate: 0. Corpi vuoti: 0
  (ma il corpo NVO 11824 è solo un URL, DAY-002).
* Fan-out: **31 articoli multi-ticker generano 98 righe su 189 (51,9%)**, massimo 11 righe (roundup «Nasdaq 100
  Rallies, Intel Soars 14%»).
* Duplicati: 7.300+ `duplicate_id` in `news_queue_drops` (REST 5.027, WS 1.635), 4 `duplicate_content`.
  Il contatore `duplicates` di `ingestion_stats_daily` supera `fetched` (DAY-022).
* Coda notturna: 295 articoli WS accodati off-session scartati `stale` nell'ora 13 (DAY-023).
* Copertura: 56/96 simboli di watchlist con almeno una riga, **40 a zero** (dossier `no_news_backstop`), 3 mover a zero news
  (RDDT, AMAT, BP).
* Entità HTML in `news_log.body_full`: 69/189 righe — il path Benzinga persiste il grezzo (atteso); nel testo che
  raggiunge FinBERT (`finbert_fallback_events.finbert_input`) **0/9** contengono entità: fix F-076 efficace sul primo giorno.

### 4.2 Per ticker (top 18 per righe)

| Ticker | Righe | Ensemble | Single/FinBERT | Max | Min | Ultimo |
|---|---|---|---|---|---|---|
| SPY | 27 | 16 | 11 | +0,165 | −0,250 | −0,020 |
| META | 11 | 8 | 3 | +0,435 | −0,050 | +0,240 |
| NVO | 10 | 5 | 5 | +0,295 | **−0,595** | 0,000 |
| NVDA | 9 | 5 | 4 | +0,243 | −0,171 | +0,028 |
| MSFT | 9 | 3 | 6 | +0,312 | +0,008 | +0,040 |
| AMZN | 8 | 3 | 5 | +0,060 | −0,040 | +0,040 |
| GOOGL | 7 | 4 | 3 | +0,128 | −0,080 | +0,040 |
| INTC | 7 | 4 | 3 | +0,640 | 0,000 | +0,640 |
| QQQ | 5 | 1 | 4 | +0,399 | +0,020 | +0,028 |
| AMD | 5 | 3 | 2 | **+0,710** | +0,020 | +0,164 |
| SPCX | 5 | 2 | 3 | +0,240 | +0,007 | +0,140 |
| LLY | 5 | 2 | 3 | +0,200 | −0,180 | 0,000 |
| TSLA | 5 | 4 | 1 | +0,142 | +0,040 | +0,040 |
| TSM | 4 | 2 | 2 | +0,589 (FinBERT) | 0,000 | 0,000 |
| MS | 4 | 3 | 1 | +0,040 | −0,159 | +0,040 |
| MU | 4 | 4 | 0 | +0,184 | −0,153 | +0,184 |
| SOXX | 3 | 2 | 1 | +0,135 | +0,040 | +0,040 |
| PANW | 3 | 2 | 1 | +0,210 | 0,000 | +0,210 |

### 4.3 Top news per impatto sul segnale

| Segnale | Ticker | Score | Titolo (abbrev.) | Esito |
|---|---|---|---|---|
| 11896 | AMD | +0,710 | «AMD Stock Hits Fresh Record High, Up 183% This Year» | bloccato P0-05 (S1 a libro) |
| 11972 | INTC | +0,640 (single) | «Intel Shares Rise Over 5% After Key Trading Signal» | già S4 |
| 11865 | NVO | −0,595 (single) | «Novo Nordisk Falls 7% as Post-Wegovy Growth Plan Fails…» | ignorato (fallback) |
| 11866 | TSM | +0,589 (FinBERT) | «AMD Rises 5% as Report Flags 10% Chip Price Increase…» | SKIP_FALLBACK |
| 11898 | ARM | +0,581 | «What Is Going On With Arm Holdings Stock on Monday?» | **BUY** 15:37 |
| 11811 | NVO | −0,435 | «Novo Nordisk, Telix … Moving Lower In Monday's Pre-Market» | superato da 11824 |
| 11884 | META | +0,435 | «Meta Stock Is Surging: What's Happening Today?» | SKIP_PYRAMIDING |
| 11807 | GM | +0,420 | «General Motors: What To Watch Before Buying The Stock» | SKIP_PYRAMIDING (recap retrospettivo) |
| 11827 | META | +0,409 | «Wells Fargo Maintains Overweight on Meta, Raises PT» | **BUY** 14:07 |
| 11842 | HOOD | +0,399 | «Robinhood Stock Jumps 5% as Bitcoin Rally and SEC Rule Change Align» | **BUY** 14:22 |
| 11920 | NOW | +0,314 | «This Analyst Raises Price Targets For Microsoft And This AI Infrastructure…» | **BUY** 16:22 (ticker verificato nel corpo: ServiceNow PT 141→174) |
| 11824 | NVO | +0,295 | «At Novo Nordisk Capital Markets Day, Co U.S. Head Says…» (corpo = URL) | **BUY** 14:07 (DAY-002) |

Confidenza dell'analisi ingest: **alta** per conteggi e timestamp (DB), media per la copertura (dossier).

---

## 5. Performance modelli LLM

| Modello | Risposte | `eligible` | Polarity media | Confidence media | Score medio (p×c) | Dev.std score | conf < 0,3 | Timeout (log) |
|---|---|---|---|---|---|---|---|---|
| glm-5.2:cloud | 180 | 68 | +0,128 | 0,386 | +0,064 | 0,162 | 62 | 9 |
| gpt-oss:20b-cloud | 178 | 68 | +0,084 | 0,446 | +0,052 | 0,161 | 24 | 12 |
| FinBERT (fallback) | 9 eventi | — | — | — | +0,080 | — | — | — |

| Tipo segnale | N | Score medio | |score| medio | ≥ 0,30 |
|---|---|---|---|---|
| ensemble glm-5.2+gpt-oss | 120 | +0,075 | 0,125 | 14 |
| single gpt-oss | 46 | +0,050 | 0,095 | 2 |
| single glm-5.2 | 14 | +0,042 | 0,186 | 2 |
| finbert | 9 | +0,080 | 0,081 | 1 |

* **Latenza**: 61 task di scoring in seduta, 11.582 s per 189 articoli = **61,3 s/articolo** (10,1 s il 18/09,
  15,3 il 17/09); massimo 589 s per un task. Pubblicazione→segnale in seduta: mediana **10,4 min**, p90 69 min
  (0,7 / 8,9 il 18/09). Le chiamate Ollama non sono loggate (F-086): la causa non è attribuibile (DAY-006).
* **Fallback FinBERT reali**: 9 (8 Ollama timeout, 1 divergenza) = 4,8% dei segnali; input con corpo presente
  in 9/9 (`body_chars` 26–428). Nessuno ha prodotto un ordine (TSM +0,589 e MCD esclusi da #108).
* `fallback_used=true`: **69/189 (36,5%)**, di cui 60 letture a modello singolo; la somma `finbert_fallbacks`
  negli esiti dei task è 69, contro 9 FinBERT reali (DAY-008).
* **Eleggibilità**: 52 dei 120 segnali d'ensemble non hanno alcuna risposta `eligible=true` (DAY-007).
* **Disaccordo**: `F-054 masked divergence` loggato 51 volte (nuovo log del fix: divergenza su tutte le risposte
  vs sui soli eleggibili). NVO 11929 single glm −0,413 con `ensemble_std` 0,530.
* **Validazione**: output strutturato JSON con `risk_flags`/`directness`; i `risk_flags` non sono un gate
  (by design, QX-01). GM 11807: glm segnala `already_priced_in` e dà comunque 0,6/0,7.
* Offline/background: sì. Nessuna chiamata LLM nel ciclo portfolio (i cicli leggono `sentiment_signals`).

---

## 6. Segnali finali per ticker (sopra gate 0,30 o decisivi)

| Ticker | Segnale | Score | ×vel. | Tipo | Decisione S4 | Motivo |
|---|---|---|---|---|---|---|
| META | 11827 | +0,409 | 1,2 → 0,491 | ensemble | **BUY** 14:07 | primo ciclo utile |
| NVO | 11824 | +0,295 | 1,2 → 0,354 | ensemble | **BUY** 14:07 | ultimo segnale; −0,435 delle 13:46 ignorato |
| GM | 11807 | +0,420 | 1,2 | ensemble | SKIP_PYRAMIDING ×24 | S1 a libro dal 07-15 (845 $) |
| HOOD | 11842 | +0,399 | 1,0 | ensemble | **BUY** 14:22 | |
| NOK | 11858 | +0,333 | 1,0 | ensemble | SKIP_PYRAMIDING ×5 | S1 a libro con **6,12 $** |
| META | 11884 | +0,435 | 1,2 | ensemble | SKIP_PYRAMIDING | META già S4 |
| AMD | 11896 | +0,710 | 1,2 | ensemble | SKIP_PYRAMIDING ×10 | S1 a libro (497,50 $) |
| ARM | 11898 | +0,581 | 1,2 → 0,698 | ensemble | **BUY** 15:37 | |
| NOW | 11920 | +0,314 | 1,2 → 0,377 | ensemble | **BUY** 16:22 | |
| MSFT | 11919 | +0,312 | — | ensemble | SKIP_THRESHOLD / rank | |
| JPM | 11927 | +0,343 | 1,2 | ensemble | SKIP_PYRAMIDING ×10 | S1 a libro |
| T | 11932 | +0,322 | — | ensemble | non eseguito (rank/threshold) | |
| INTC | 11934 | +0,409 | 1,2 | ensemble | SKIP_PYRAMIDING | già S4 |
| QQQ | 11958 | +0,399 | 1,2 | ensemble | SKIP_PYRAMIDING ×8 | già S4 |
| INTC | 11913 / 11972 | +0,360 / +0,640 | — | single | esclusi (#108) | |
| TSM | 11866 | +0,589 | — | FinBERT | escluso (#108) | |
| NVO | 11811 / 11865 / 11929 | −0,435 / −0,595 / −0,413 | — | ens/single | nessuno (long-only) | |

`execution_decisions` del giorno: 623 SKIP_THRESHOLD, 22 SKIP_FALLBACK, 7 SKIP_PYRAMIDING (contro 94 intenti
SKIP_PYRAMIDING nel ledger intent), 3 SKIP_STALE (PANW/XLE/XLK, segnali di 66–69 h del venerdì: corretto),
5 BUY, 3 SELL; più 1.715 righe d'osservazione `OBSERVE_/SHADOW_LATE_ENTRY` (#512, escluse). Portfolio combiner
applicato (S1+S4, S1 con gate di ribilanciamento chiuso su tutti i cicli), peso S4 2,0% per ingresso, poi
`regime_mult` 0,2 sul nozionale.

---

## 7. Ordini generati/eseguiti

| Decisione | Ora | Strategia | Ticker | Azione | Qty | Nozionale | Fill | Stato | Segnale | Risk check | Anomalie |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 35392 | 14:07:00 | S4 | META | BUY | 0,5906 | 420,87 | 712,616 | filled 14:07:05 | 11827 +0,409 | gate, P0-05, idempotenza, regime ×0,2 | nessuno stop (qty < 1) |
| 35393 | 14:07:00 | S4 | NVO | BUY | 10,5912 | 420,87 | 39,7366 | filled 14:07:08 | 11824 +0,295 | idem | DAY-002; stop 10 sh alle 14:22 |
| 35485 | 14:22:00 | S4 | HOOD | BUY | 3,4023 | 417,74 | 122,78 | filled 14:22:07 | 11842 +0,399 | idem | stop 3 sh alle 14:37 |
| 35972 | 15:37:00 | S4 | ARM | BUY | 1,3104 | 413,54 | 315,584 | filled 15:37:04 | 11898 +0,581 | idem | stop 1 sh immediato (76%) |
| 36071 | 15:52:00 | S4 | NVO | SELL | 10,5912 | — | 39,85 | filled 15:52:07 | (NULL) −0,036 14:47 | isteresi 2 cicli, hold min. | `signal_id` NULL |
| 36171 | 16:07:00 | S4 | HOOD | SELL | 3,4023 | — | 124,12 | filled 16:07:05 | (NULL) +0,183 15:07 | idem | SELL su score positivo |
| 36172 | 16:07:00 | S4 | META | SELL | 0,5906 | — | 722,284 | filled 16:07:04 | (NULL) +0,027 15:52 FANOUT | idem | DAY-003 |
| 36271 | 16:22:00 | S4 | NOW | BUY | 2,9791 | 409,76 | 137,54 | filled 16:22:05 | 11920 +0,314 | idem | stop 2 sh alle 16:37 (67%) |

Broker: Alpaca **paper**. Ordini a mercato; `decision_price` NULL su tutte le decisioni (DAY-010). Stop GTC
cancellati alla SELL successiva (ARM il 22/09 17:22, «Cancelled 1 protective stop(s) for ARM before SELL»).
Nessun ordine rigettato.

---

## 8. PnL / rendimento

| Voce | Valore | Fonte | Confidenza |
|---|---|---|---|
| NAV 20:00 | 110.027,02 $ | `portfolio_monitor_snapshots` | misurata |
| Variazione giornata (vs close venerdì) | **+593,85 $ (+0,54%)**; SPY +1,55% | idem | misurata |
| Intraday open→close posizioni già aperte (43) | **+221,73 $** (S1 35 pos. +38,32 · S4 8 pos. +183,41) | dossier `snapshot_apertura` | misurata |
| Gap venerdì-close → lunedì-open (residuo) | ≈ +351 $ (593,85 − 221,73 − 20,95) | derivato | attribuita |
| S4 realizzato (3 chiusure) | **+10,94 $** (NVO +0,97 · HOOD +4,33 · META +5,63) | `trades` 1019/1020/1018 | misurata |
| S4 aperti oggi, MtM al close | ARM +9,59 $ · NOW +0,42 $ | dossier `ingressi` | misurata |
| Costi | 0,079–0,228 $ per trade (modello); commissioni Alpaca 0 | `trades.cost_usd` | stimata |
| Slippage | **non misurabile**: `slippage_est` = `cost_usd`, `decision_price` NULL | `trades` | — |

Top/bottom intraday sulle posizioni aperte prima del 21/09: INTC (S4) +76,25 · MRVL (S4) +38,12 · PANW (S4)
+29,73 · CSCO (S4) +28,27 · QQQ (S4) +28,17 · AMD (S1) +25,74 ║ BP (S1) −29,40 · CVX (S1) −17,95 · XLE (S4)
−15,62 · XOM (S1) −14,63 · VALE (S1) −13,78 · SHEL (S1) −13,33. Tutte le 7 posizioni S4 più grandi (INTC,
MRVL, PANW, CSCO, QQQ, XLE, MU) stanno nel target S1 congelato (DAY-016): il loro +183 $ non è misura della
regola di S4. Unrealized broker al 20:00: +1.704,88 $. Nessun `exit_mechanism` interpretato in questo report
su righe pre-#184.

---

## 9. Correttezza buy/sell

| Controllo | Esito |
|---|---|
| BUY solo se consentito (gate 0,30 × velocity, ensemble, fresco ≤ 4 h, non a libro) | ✔ 5/5 |
| SELL/exit corretti | ✔ 3/3 `below_entry_gate` dopo isteresi 2 cicli e hold minimo 90′ (NVO/HOOD etichettate `hold_minimum_expiry` #430: prima uscita utile dopo l'hold) |
| Stop-loss | `risk.stop_loss: 0.0` (by design); stop protettivi parziali, META senza stop (DAY-013) |
| Signal flip | NVO: flip da −0,435 a +0,295 in 16 min → BUY (DAY-002) |
| Max holding / rebalance band S1 | S1 gate chiuso su 24/24 cicli ✔ |
| Ordini duplicati / stesso minuto | nessuno (META+NVO 14:07 su simboli diversi) ✔ |
| Roundtrip < 30 min | nessuno (minimo 1 h 45) ✔ |
| Pyramiding > 3 BUY | nessuno ✔ (P0-05 attivo) |
| SELL con sentiment positivo (A5) | HOOD +0,183, META +0,027 — by design `below_entry_gate`, costo META su DAY-003 |
| Score < 0,05 che generano ordini | solo uscite (+0,027, −0,036), nessun ingresso ✔ |
| Ticker non consentiti / fuori orario | nessuno ✔ |
| Trade su dati stale / LLM invalido | no: SKIP_STALE ×3, SKIP_FALLBACK ×22 ✔ |
| Circuit breaker / strategia disabilitata | nessun breaker scattato; S4 abilitata ✔ |
| Paper/live coerente | paper ✔ |
| Idempotenza retry | 21 SKIP_IDEMPOTENCY + 21 `SIGNAL_DUPLICATE_SKIP` (ARM ×17) ✔ |
| Reconciliation ordini/fill/posizioni | 5 BUY + 3 SELL = broker; UNH 1 azione di scarto con «anomalies: 0» (DAY-027) |
| NO-ORDER (decisione senza ordine) | nessuno ✔ |

---

## 10. Anomalie trovate

### [DAY-001] Regime assente tutta la seduta: `detect_regime` fallisce due volte, risulta `succeeded`, ogni ciclo a ×0,20

* Tipo: Bug · Area: Risk / Ops
* Evidenza:
  * file/log/tabella: `worker-inference-2026-09-21.log`; `worker-2026-09-21.log`; `trades.regime_mult`
  * timestamp: 07:00:15 (FRED timeout), 13:30:04 (T10Y2Y 502); 14:07:03–19:52:05
  * snippet: `Task src.workers.regime.detect_regime[...] succeeded in 4.5575930810009595s: None`; 62× `P0-09: regime:current absent — deterministic VIX fallback ×0.20 (vix=absent)`
* Descrizione: con input macro mancante il fallback applica il moltiplicatore più severo; VIX FRED della seduta 14,87
  (il 18/09 con VIX 14,81 il regime era SIDEWAYS 0,7). Nessun `mobile_events`.
* Impatto: 5 ingressi S4 a 409–421 $ (~19% di uno slot da 2.200 $). La serie S4 del giorno è ridotta 3,5× per un guasto di rete.
* Severità: High · Confidenza: High
* Azione consigliata: ticket correttezza — un fallimento di `detect_regime` deve fallire il task e aprire un alert; il fallback "absent" va dichiarato nell'artefatto come discontinuità.
* Test/monitor consigliato: test che `detect_regime` con FRED in errore non ritorni `succeeded`; monitor su righe `P0-09 … absent` > 0 in seduta.
* → ledger **F-017** (costo già prezzato in ALPHA_MISS 21/09: 52,35 $; qui `null`)

### [DAY-002] NVO comprata su un titolo senza corpo 16 minuti dopo un −0,435, con il titolo già a −7,4%

* Tipo: Anomalia · Area: Signal
* Evidenza:
  * tabella: `sentiment_signals` 11811 / 11824, `llm_responses`, `news_log`, `execution_decisions` 35393, `trades` 1019
  * timestamp: 13:46:40 (−0,435: glm −0,6/0,85, gpt −0,6/0,6), 14:02:38 (+0,295: glm 0,45/0,75, gpt 0,3/0,7), BUY 14:07:00
  * snippet: `news_log.body_full` di 11824 = `https://edge.media-server.com/mmc/p/xdjeyf7u/`
* Descrizione: S4 legge solo l'ultimo segnale per simbolo; un titolo del Capital Markets Day senza corpo sostituisce il
  segnale che descriveva il crollo sui trial CagriSema. Velocity 1,2 porta il gate a 0,354. La guardia ombra di
  contraddizione l'ha segnalato, solo in ombra.
* Impatto: trade chiuso a +0,97 $ (uscita 15:52 su −0,036). Esito positivo per caso: funzionalmente l'ingresso contraddice l'evidenza della stessa seduta.
* Severità: Medium · Confidenza: High
* Azione consigliata: nessuna taratura; misurare (read-only) quante BUY S4 hanno un segnale di segno opposto sopra gate nelle 2 h precedenti.
* Test/monitor consigliato: monitor «BUY con segnale opposto |s| ≥ 0,30 nelle 2 h precedenti».
* → ledger **F-023**, costo −0,97 $ (attribuita: senza il difetto nessun ingresso, P&L 0 invece di +0,97)

### [DAY-003] META venduta su un articolo sul gasolio fan-out (+0,027)

* Tipo: Anomalia · Area: Signal / Orders
* Evidenza: `execution_decisions` 36172 «generated 2026-09-21 15:52 UTC, score=+0.027»; segnale 11904 FANOUT «$6.51 Diesel Should Be Crushing the Economy»; `trades` 1018 net +5,63; close META 741,245.
* Descrizione: un articolo macro senza rapporto con Meta chiude una posizione aperta su +0,409 issuer-specifico; il +0,435 delle 15:15 era stato sostituito da segnali più deboli.
* Impatto: `drift_post_uscita` +11,20 $.
* Severità: Medium · Confidenza: High
* Azione consigliata / Test: vedi F-008 (classificare le SELL per `attribution` del segnale citato).
* → ledger **F-008** (costo già in ALPHA_MISS 21/09: 11,20 $; qui `null`)

### [DAY-004] HOOD venduta su un segnale positivo (+0,183) sotto il gate d'ingresso

* Tipo: Rischio · Area: Orders
* Evidenza: `execution_decisions` 36171 «score=+0.183, generated 15:07»; isteresi 15:52 `['HOOD','META']`; trade 1020 net +4,33; dossier `drift_post_uscita` −2,79 $.
* Descrizione: nessuna banda fra gate d'ingresso 0,30 e uscita; un +0,183 TAG_UNCONFIRMED (liquidazioni crypto) chiude la posizione.
* Impatto: oggi l'uscita ha evitato 2,79 $; il meccanismo resta indipendente dal segno.
* Severità: Low · Confidenza: High
* Azione consigliata: nessuna (taratura congelata); solo misura.
* Test/monitor: conteggio giornaliero SELL con score > 0.
* → ledger **F-013**, costo −2,79 $ (attribuita)

### [DAY-005] P0-05 blocca 94 intenti, fra cui AMD +0,710 e NOK +0,333 su una posizione S1 da 6,12 $

* Tipo: Anomalia · Area: Risk
* Evidenza: log worker (GM 24, PBR 24, AMD 10, JPM 10, QQQ 8, NOK 5, AMAT 4, MRK 3, LLY 2, META 2, INTC 2); `execution_decisions` 35679 «posizione $6.12»; 7 righe SKIP_PYRAMIDING su 94 intenti.
* Descrizione: il guard tratta come «a libro» anche un residuo S1 da 6 $ e blocca un ingresso S4 da 2.203 $ di target.
* Impatto: 3 mover colpiti (AMD, AMAT, INTC).
* Severità: Medium · Confidenza: High
* → ledger **F-031** (costo già in ALPHA_MISS 21/09: −1,65 $; qui `null`)

### [DAY-006] Latenza di scoring 6×: 61 s per articolo, pubblicazione→segnale mediana 10,4 min

* Tipo: Anomalia · Area: LLM / Ops
* Evidenza: esiti `run_sentiment_worker`: 11.582 s / 189 articoli (09-18: 2.456 s / 242 = 10,1 s; 09-17: 15,3 s); max 589 s; `sentiment_signals` pub→segnale mediana 10,4 min, p90 69,2 (09-18: 0,7 / 8,9). Timeout per modello 21 (09-18: 22).
* Descrizione: primo giorno della regressione osservata anche il 22/09 (DAY-013). Coincide con i rebuild delle 08:20Z/10:20Z, ma senza traccia di trasporto Ollama (F-086) non è attribuibile a provider, retry o codice.
* Impatto: consuma la finestra di freschezza; alle 14:07 la coda dell'apertura ha `raw_ingested_at`→segnale mediana 64 min.
* Severità: Medium · Confidenza: Medium
* Azione consigliata: bisezione read-only dei 23 commit deployati il 21/09 sul percorso di scoring.
* Test/monitor: metrica per-item del task in `ingestion_stats` o Postgres con alert > 30 s.
* → ledger **F-019**

### [DAY-007] 52 dei 120 segnali d'ensemble senza alcuna risposta `eligible`

* Tipo: Bug · Area: LLM · Evidenza: join `sentiment_signals`–`llm_responses` del giorno: 68 con 2 eleggibili, 52 con 0.
* Impatto: il ledger non dice quali risposte hanno formato lo score. Severità: Low · Confidenza: High
* → ledger **F-010**

### [DAY-008] 69 segnali `fallback_used` (36,5%), ma solo 9 FinBERT reali

* Tipo: Bug · Area: LLM / Ops · Evidenza: 46 single gpt-oss + 14 single glm + 9 FinBERT; esiti task `finbert_fallbacks` sommano 69; `finbert_fallback_events` 9 righe.
* Impatto: il tasso di fallback riportato è 7,7× quello reale. Severità: Low · Confidenza: High
* → ledger **F-078**

### [DAY-009] Le 3 SELL non portano `signal_id`

* Tipo: Bug · Area: Data · Evidenza: `execution_decisions` 36071/36171/36172 `signal_id` NULL; `decision_signal_id_coverage.regressions`=["SELL"].
* Severità: Low · Confidenza: High · → ledger **F-011**

### [DAY-010] Slippage non misurabile: `decision_price` NULL, `slippage_est` = `cost_usd`

* Tipo: Bug · Area: PnL · Evidenza: `trades` 1018–1022 `slippage_est` identico a `cost_usd`; `decision_price` NULL su 8/8 decisioni d'ordine.
* Severità: Low · Confidenza: High · → ledger **F-015**

### [DAY-011] `orders_count` = 5–7 su tutti i cicli contro 0–2 ordini inviati

* Tipo: Anomalia · Area: Ops · Evidenza: `portfolio_cycles` 1586–1609.
* Severità: Low · Confidenza: High · → ledger **F-014**

### [DAY-012] Primo ciclo alle 14:07, 37 minuti dopo l'apertura; alert CRITICAL `portfolio_cycle_late`

* Tipo: Anomalia · Area: Ops · Evidenza: `portfolio_cycles` 1586; `mobile_events` 13:30:01→14:08:00.
* Impatto: META (PT pubblicato 12:38) e NVO entrano solo al primo ciclo. Severità: Low · Confidenza: High · → ledger **F-021**

### [DAY-013] Stop protettivi parziali: META senza stop, NOW al 67%, ARM al 76%

* Tipo: Rischio · Area: Risk · Evidenza: ordini stop `913f5da1` ARM 1/1,3104, `48ea3d45` NOW 2/2,9791 (un ciclo dopo), `f56f4b97` HOOD 3/3,4023, `7d43a28d` NVO 10/10,5912; META 0,5906 nessuno; log «#161: AMAT unprotected at −21.4%, WDC −18.7%».
* Severità: Low · Confidenza: High · → ledger **F-022**

### [DAY-014] Fan-out: 31 articoli multi-ticker producono 98 righe su 189 (51,9%)

* Tipo: Anomalia · Area: News · Evidenza: `news_log` per `content_hash`, massimo 11 righe.
* Severità: Low · Confidenza: High · → ledger **F-012**

### [DAY-015] 40 simboli di watchlist su 96 senza alcuna riga `news_log`

* Tipo: Anomalia · Area: News · Evidenza: dossier `no_news_backstop.population` 40; mover a zero news RDDT, AMAT, BP.
* Severità: Low · Confidenza: High · → ledger **F-001**

### [DAY-016] 7 posizioni S4 nel target S1 congelato: il loro +183 $ intraday non misura S4

* Tipo: Rischio · Area: Risk / PnL · Evidenza: dossier `snapshot_apertura` S4: INTC +76,25, MRVL +38,12, PANW +29,73, CSCO +28,27, QQQ +28,17, XLE −15,62, MU −1,51; S1 «rebalance gate closed» 24/24 cicli; stessi simboli dei report 18/09 e 22/09.
* Severità: Medium · Confidenza: Medium (controfattuale di uscita non ricostruito) · → ledger **F-089**

### [DAY-017] Benchmark SPY: 84 fetch falliti per limite SIP, nessun alert

* Tipo: Anomalia · Area: Data · Evidenza: 84× `SPY benchmark fetch failed: subscription does not permit querying recent SIP data`.
* Severità: Low · Confidenza: High · → ledger **F-016**

### [DAY-018] Decay monitor: S1, S2 e S4 con lo stesso IC (−0,044), S1 e S2 con lo stesso drawdown (13,4%)

* Tipo: Bug · Area: Risk · Evidenza: 7 righe `DECAY CRITICAL` 21:00 («IC dropped … to -0.044» ×3, «Max drawdown … 13.4%» ×2).
* Severità: Low · Confidenza: High · → ledger **F-004**

### [DAY-019] I 7 DECAY CRITICAL restano nel log

* Tipo: Anomalia · Area: Ops · Evidenza: nessuna riga `mobile_events` corrispondente. Severità: Low · Confidenza: High · → ledger **F-062**

### [DAY-020] Telegram 400 Bad Request su 4 alert

* Tipo: Bug · Area: Ops · Evidenza: `TelegramNotifier: Failed to send alert` 04:00:00, 14:07:06 ×2, 23:05:00.
* Severità: Medium · Confidenza: High · → ledger **F-005**

### [DAY-021] Segreti in chiaro nei log: `api_key` FRED e bot token Telegram

* Tipo: Rischio · Area: Ops · Evidenza: ERROR 13:30:04 con `api_key=…` nell'URL FRED; token bot in 17.257 righe di `worker-inference` e 10 di `worker`.
* Severità: Medium · Confidenza: High · → ledger **F-018**

### [DAY-022] `ingestion_stats_daily`: 6.753 duplicati contro 1.514 fetched per alpaca_benzinga

* Tipo: Bug · Area: Data · Severità: Low · Confidenza: High · → ledger **F-007**

### [DAY-023] 295 articoli della coda notturna scartati stale all'apertura

* Tipo: Anomalia · Area: News · Evidenza: `news_queue_drops` ora 13, `transport=ws`, `enqueued_off_session=true`, `stale` 295; 95 dispatch `market_closed` nella notte.
* Severità: Low · Confidenza: High · → ledger **F-069**

### [DAY-024] Tre alert della sera aperti e chiusi nello stesso secondo

* Tipo: Bug · Area: Ops · Evidenza: `mobile_events` `portfolio_cycle_session_grid`, `held_no_news_loss:SBUX`, `:VALE` 22:50:00 → 22:50:01.
* Severità: Low · Confidenza: High · → ledger **F-058**

### [DAY-025] `signal_score` persistito grezzo (NVO 0,295) mentre il gate ha valutato 0,354

* Tipo: Bug · Area: Data · Evidenza: `execution_decisions` 35393 `signal_score` 0,295, `velocity_multiplier` 1,2, reason «gate 0.354».
* Severità: Low · Confidenza: High · → ledger **F-073**

### [DAY-026] Il ranking tiene segnali di giorni prima su simboli già a libro (AMAT 11781 del 18/09)

* Tipo: Anomalia · Area: Signal · Evidenza: dossier `intenti_ingresso_s4` (AMAT 11781: 4 SKIP_PYRAMIDING, 20 RANK_OUTSIDE_TOP_N); log «skipping BUY for AMAT» ×4.
* Severità: Low · Confidenza: Medium · → ledger **F-051**

### [DAY-027] UNH: 1 azione di scarto fra ledger e broker, riconciliatore «anomalies: 0»

* Tipo: Bug · Area: Broker · Evidenza: `trades` 279 qty 1,592634, `quantity_remaining` NULL; `/api/positions` UNH 0,592634; `reconcile-positions` 21:35 `partially_wound_down_coheld: 1`, `anomalies: 0`.
* Severità: Low · Confidenza: High · → ledger **F-048**

---

## 11. False positive / aree risultate corrette

* **Fix F-076 live**: 0/9 input FinBERT con entità HTML (prima seduta post-deploy).
* **Fix F-054 live**: 51 righe `F-054 masked divergence` rendono osservabile la divergenza nascosta dal filtro d'eleggibilità.
* SKIP_STALE PANW/XLE/XLK: segnali del venerdì a 66–69 h, correttamente scartati.
* `hold_minimum_expiry` su NVO/HOOD: etichetta diagnostica #430 (prima uscita utile dopo l'hold da 90′), non un nuovo percorso d'uscita.
* NOW: il ticker è corretto (corpo: «ServiceNow Inc (NYSE: NOW) – from $141 to $174»).
* Idempotenza: nessun doppio ordine nonostante 17 ri-valutazioni di ARM 11898.
* Nessun ordine fuori orario, su simbolo non consentito, su fallback, o durante un breaker.
* Rete host giù 22:13–22:49 (poller Telegram): nessun job di trading o di evidenza coinvolto; shadow 22:20 ok.
* Il divario NAV (+593,85) vs intraday (+242,68) è spiegato dal gap venerdì→lunedì, non è una incoerenza di PnL.

## 12. Dati mancanti o non accessibili

* Traccia di trasporto delle chiamate Ollama (latenza per modello, retry): non esiste (F-086) → latenza per modello non calcolabile.
* `economic_pnl.json` fermo al 17/09; `longitudinal_panels.json` assente.
* Prezzo di decisione (`decision_price`) assente: slippage non calcolabile.
* Controfattuale d'uscita delle posizioni S4 nel target S1 (DAY-016): non ricostruito in questa sessione.
* Query utile: `SELECT tick_time, symbol, weight FROM …` sui pesi target S4 per ciclo — i pesi per ciclo non sono persistiti in forma interrogabile oltre a `final_orders`.

## 13. Raccomandazioni immediate (solo correttezza)

1. `detect_regime`: fallire rumorosamente e allertare; dichiarare le sedute a fallback «absent» come discontinuità della serie S4 (DAY-001).
2. Bisezione read-only della regressione di latenza fra `ed53c851` e `44451ca6` (DAY-006).
3. Prima della sintesi del giorno 40: escludere o marcare il P&L delle posizioni S4 nel target S1 congelato (DAY-016).

## 14. Test o monitor da aggiungere

* Test: `detect_regime` con FRED in errore → task non `succeeded`, alert emesso.
* Monitor: righe `P0-09 … absent` in seduta > 0 → WARNING.
* Monitor: secondi per articolo del worker sentiment (soglia 30 s) persistiti in Postgres.
* Monitor: BUY S4 con segnale opposto |s| ≥ 0,30 sullo stesso simbolo nelle 2 h precedenti.
* Invariante: `fallback_used` ≡ FinBERT oppure campo distinto per «single-model».

## 15. Ticket tecnici suggeriti

* [correttezza] `detect_regime` registra `succeeded` su errore FRED e lascia il sizing S4 al fallback ×0,20 senza alert (F-017).
* [strumentazione] Persistenza latenza/esito per chiamata Ollama (F-086) — prerequisito per diagnosticare F-019.
* [correttezza misura] P&L S4 contaminato dalle posizioni nel target S1 congelato (F-089).

## 16. Stato sistema

* **Ollama**: up per tutta la seduta; nessun outage completo. 21 timeout per-modello (glm 9, gpt-oss 12), concentrati 14–15 UTC (14) e 18 UTC (5). Ore di downtime: **0**.
* **FinBERT fallback rate**: 9/189 segnali = **4,8%**; sulle decisioni d'ordine: **0/8** (0%); fra le 22 SKIP_FALLBACK 1 è FinBERT (MCD).
* **Worker restart**: 08:20:17–18 e 10:20:16–17 (rebuild del riconciliatore, pre-market); nessun restart in seduta; nessun SoftTimeLimit/SIGKILL.
* Redis: `fresh` e scrivibile su tutte le istantanee. Rete host: irraggiungibile 22:13–22:49 (fuori seduta, senza impatto).
