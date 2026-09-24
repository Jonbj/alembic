# Forensic Daily Report — 2026-08-28 (venerdì)

Analisi read-only end-to-end della seduta del 2026-08-28.
Timezone operativo: **UTC** (`src/workers/celery_app.py`: `timezone="UTC"`, `enable_utc=True`).
Sessione RTH 2026-08-28: **13:30–20:00 UTC** (EDT). Modalità broker: **paper** (`portfolio_monitor_snapshots.broker_environment='paper'`, `strategy_lifecycle`: S4=paper, S1=supervised_paper, S2=disabled, S7=research).

Periodo di sola osservazione (`docs/evidence/OBSERVATION_CHARTER.md`, freeze fino al 2026-09-28):
in questo report **non** si propone alcuna taratura. I ticket suggeriti riguardano solo difetti di
correttezza che, se non corretti, rendono sbagliata l'evidenza raccolta.

---

## 1. Executive summary

La pipeline ha girato end-to-end senza eccezioni fatali: 81 articoli ingeriti e scorati, 81 segnali,
24 cicli portfolio, 5 ordini attribuiti (2 BUY + 3 SELL) tutti riempiti, 3 stop protettivi piazzati e
poi cancellati. Il P&L realizzato di giornata è **+20,08 $** (S4; S1 zero realizzato), il book ha
chiuso a **−239,77 $ (−0,218%)** contro SPY −0,227% e QQQ −0,649%: una giornata di beta, non di alfa.
Nessun alert è stato emesso in tutta la sessione (`mobile_events`=0, `risk_reports.alerts=[]`).

Il processo è funzionalmente coerente sui passaggi principali — dedup, gate d'ingresso, hold minimum,
anti-pyramiding e riconciliazione ordini/fill/trade hanno fatto quello che dicono di fare — ma la
giornata espone tre problemi di **correttezza dell'evidenza**, non di trading: (a) `/api/trades`
riporta per il 2026-08-28 un realizzato di **−55,03 $** contro i **+20,08 $** del ledger, cioè un
segno invertito; (b) `execution_decisions.signal_score` contiene per NVDA il punteggio grezzo e per
CRM quello moltiplicato ×1,2 dalla velocity, nello stesso giorno e nella stessa colonna; (c) su
2026-08-28 il prompt riceveva **solo il corpo dell'articolo** (teaser di ~145 caratteri, con entità
HTML non decodificate in 18 righe su 81) e mai il titolo.

Due casi meritano attenzione di merito. L'unico BUY in perdita (NVDA, −22,94 $) nasce dal segnale con
la **massima divergenza d'ensemble della giornata** (`ensemble_std`=0,318) e con flag `rumor` da
entrambi i modelli: la varianza non è un gate. E su CRM il fallback per divergenza ha prodotto un
verdetto FinBERT di **−0,578** mentre i due LLM sulla stessa frase davano +0,6 e 0,0 — un segno che
nessuno dei due modelli sostituiti aveva espresso.

## 2. Verdict finale

**OK con warning.**

Il flusso news → LLM → segnale → decisione → ordine → fill → posizione è ricostruibile riga per riga
e internamente consistente; nessun ordine è stato generato senza segnale, nessuno fuori orario,
nessun duplicato, nessun trade su ticker non consentito. I warning sono di due tipi: superfici di
lettura che riportano numeri sbagliati (API trades, `signal_score`, `ensemble_std`) e guard che
esistono ma non sono armati (varianza d'ensemble, `d_hard`). Il P&L di giornata non è compromesso;
l'evidenza costruita sopra queste colonne sì.

---

## 3. Timeline del 2026-08-28 (UTC)

| Ora UTC | Componente | Evento | Fonte |
|---|---|---|---|
| 13:30:00 | monitor | Apertura. NAV 110.027,99 (prev close 110.041,95), 48 posizioni, cash 75.062,59. Degradations: `signal stale` + `portfolio_cycle stale` | `portfolio_monitor_snapshots` |
| 13:30–14:00 | beat | **Nessun ingest, nessuno scoring, nessun ciclo portfolio.** Finestra beat `hour="14-21"` fissa UTC | `celery_app.py:83,274` |
| 14:00:35 | ingest+sentiment | Primo ciclo. 20 articoli (18 benzinga + 2 gdelt), pubblicati 12:50–14:00 | `news_log`, `llm_budget` |
| 14:00:41 | sentiment | Segnale 9201 NVDA **+0,3612** (ensemble glm+gptoss, conf 0,675, **std 0,318**, event `mna`, risk_flags `{rumor}` su entrambi i modelli) | `sentiment_signals`, `llm_responses` |
| 14:07:00 | portfolio cycle #1 | 5 ordini target. **BUY NVDA** 1.981,54 $ @224,72 (fill 14:07:07, qty 8,8178, rank 4, ranked score 0,4334 = 0,3612×1,2) | `portfolio_cycles`, `execution_decisions` 15642, `s4_intent_events` |
| 14:07:04 | S4 | SKIP_STALE IWM (19,9h) e TSLA (18,3h) | `execution_decisions` 15623/15624 |
| 14:07:05 | S4 | SKIP_PYRAMIDING DELL (a libro dal 2026-07-13) | `execution_decisions` 15643 |
| 14:07:07 | broker | Stop protettivo SELL **5** CRM (posizione 5,406 az. = 92,5% coperto) — poi cancellato | `/api/orders` f56c7997 |
| 14:22:00 | cycle #2 | **SELL TSLA** @352,3947, `exit_mechanism=expired` (segnale 18,6h, generato 08-27 19:46, score −0,120). Net **−7,21 $** | `execution_decisions` 15664, `trades` 896 |
| 14:22:06 | broker | Stop protettivo SELL **8** NVDA (posizione 8,818 az. = 90,7%) — poi cancellato | `/api/orders` de560129 |
| 14:45:20 | sentiment | Segnale 9216 NVDA **−0,1065** da "Nvidia Warns Of AI Power Bottleneck — And **Bloom Energy** Could Benefit" (articolo fan-out INTC/NVDA/ORCL; gptoss `directness=sector`, entrambi `already_priced_in`) | `sentiment_signals`, `llm_responses` |
| 14:46:14 | sentiment | Segnale 9219 CRM **−0,578** via **FinBERT (ensemble divergence)**: gptoss aveva dato +0,6/conf 0,7 e glm 0,0/conf 0,8 sulla stessa frase | `sentiment_signals`, `llm_responses` |
| 14:52:05 | S4 | SKIP_PYRAMIDING CSCO e CRM (sentiment −0,578 citato in `reason`) | `execution_decisions` 15708/15709 |
| 15:00:26 | sentiment | Segnale 9222 CRM **−0,0707** (ensemble, conf 0,275, std eleggibile 0,177) | `sentiment_signals` |
| 15:22:00 | cycle | **SELL CRM** @262,66, `exit_mechanism=below_entry_gate` (score −0,071 < gate 0,30). Net **+50,23 $** | `execution_decisions` 15756, `trades` 895 |
| 15:22:05 | S4 | SKIP_PYRAMIDING ARM | `execution_decisions` 15757 |
| 15:45:13 | sentiment | Segnale 9229 MRVL **+0,596** ("Marvell CEO Calls Google AI Revenue Opportunity a 'Monster Number'") — MRVL chiuderà **−10,28%** | `sentiment_signals`, `market_daily.jsonl` |
| 15:52:00 | cycle | **SELL NVDA** @222,1645, `exit_mechanism=below_entry_gate`; `trades.exit_reason=hold_minimum_expiry` (105 min = primo beat oltre il hold minimum di 90 min). Net **−22,94 $** | `execution_decisions` 15804, `trades` 902 |
| 15:52:03 | S4 | SKIP_FALLBACK NOK (single:gptoss +0,150) | `execution_decisions` 15781 |
| 15:52:04 | S4 | SKIP_PYRAMIDING MRVL (sentiment +0,596) | `execution_decisions` 15805 |
| 17:07:04 | S4 | SKIP_FALLBACK LLY (single:gptoss +0,120) | `execution_decisions` 15893 |
| 17:16–17:30 | monitor | Degradation `signal stale` (nessun segnale nello slot 17:15) | `portfolio_monitor_snapshots` |
| 17:46:21 | sentiment | Segnale 9260 MRVL **+0,583**; 17:52:04 SKIP_PYRAMIDING MRVL | `sentiment_signals`, `execution_decisions` 15986 |
| 18:52:03 | S4 | SKIP_FALLBACK UNH (finbert +0,008) | `execution_decisions` 16056 |
| 19:03–19:15 | monitor | Degradation `signal stale` | `portfolio_monitor_snapshots` |
| 19:15:07 | sentiment | Segnale 9279 CRM **+0,6166** (ensemble, conf 0,825, std 0,141, event `earnings`) da "Salesforce Stock Books Best Week Since August 2020" — **ultimo scoring della giornata** | `sentiment_signals` |
| 19:22:00 | cycle | **BUY CRM** 1.973,95 $ @259,73 (rank 1, ranked score **0,7399** = 0,6166×1,2 velocity). 38 min dalla chiusura | `execution_decisions` 16131, `trades` 903 |
| 19:31–19:55 | monitor | Degradation `signal stale` | `portfolio_monitor_snapshots` |
| 19:37:04 | broker | Stop protettivo SELL **7** CRM (posizione 7,600 az. = 92,1%) — poi cancellato | `/api/orders` 2de99ca1 |
| 19:45:01 | ingest | Ultimo aggiornamento `ingestion_stats_daily` (benzinga 676 fetched, gdelt 1908) | `ingestion_stats_daily` |
| 19:52:00 | cycle #24 | Ultimo ciclo (3 ordini target, 0 sottomessi). CRM osservato a 256,55 (−1,22% dall'ingresso di 30 min prima) | `portfolio_cycles`, `stop_shadow_log` |
| 20:00:00 | monitor | Chiusura. NAV 109.802,18 (**−239,77 $, −0,218%**), 47 posizioni, unrealized 852,66 | `portfolio_monitor_snapshots` |
| 20:07–21:52 | beat | 8 slot ciclo portfolio e ~12 slot sentiment schedulati a mercato chiuso: **nessuna riga, nessuna traccia dello skip** | assenza in `portfolio_cycles` |
| 22:30:01 | risk | Risk report: NAV 109.803,07, exposure 30,92%, HHI 0,0256, `combined_drawdown` 1,243%, `per_strategy_metrics` **{}**, `alerts` **[]** | `risk_reports` id 77 |

---

## 4. Tabella news ingest

### 4.1 Per fonte

| Fonte | fetched | queued | duplicates | disc. no_ticker | disc. stale | righe in `news_log` | hash unici | ticker | finestra pubblicazione | finestra ingest |
|---|---|---|---|---|---|---|---|---|---|---|
| alpaca_benzinga | 676 | 337 | **2813** | 0 | **168** | 69 | 37 | 34 | 12:50:50 → 18:54:15 | 14:00:41 → 19:15:13 |
| gdelt_gkg | 1908 | 12 | 3 | **1893 (99,2%)** | 0 | 12 | 12 | 10 | 14:00:00 → 18:15:00 | 14:00:35 → 18:47:39 |
| reuters | — | — | — | — | — | 0 | — | — | — | nessuna riga in `ingestion_stats_daily` |

Latenza pubblicazione → ingest: benzinga mediana **32,0 min**, media 37,0, max 85,9. gdelt mediana 16,1.
Nessun timestamp futuro (`published_at > created_at`: 0 righe). Nessun `discarded_reason` valorizzato.
Nessun `parse_fail`. Lo scoring è inline con l'ingest: `generated_at ≈ created_at`, quindi la latenza
pubblicazione → segnale è la stessa (mediana 29,8 min).

Buchi temporali: **13:30–14:00** (nessun fetch: la finestra beat parte alle 14:00 UTC) e **19:15–20:00**
(nessun articolo scorato nell'ultima ora di mercato). Copertura effettiva della seduta: 5h15m su 6h30m = **81%**.

### 4.2 Per ticker (righe `news_log`, 42 simboli su ~96 di watchlist)

| Ticker | righe | Ticker | righe | Ticker | righe |
|---|---|---|---|---|---|
| NVDA | 9 | MRVL, AAPL, GOOGL, HOOD | 3 | XLE, MCD, META, DELL, MS, CSCO, CAT, BRK.B, XLF, PANW, PLTR, QQQ, SHEL, BABA, SPCX, SPY, TM, XLV, AMZN, WDC, GS, INTC, IWM, JPM | 1 |
| CRM | 6 | TSM, AMAT, AMD, AVGO, DIS, LLY, ORCL, TSLA, XLK | 2 | | |
| MSFT, SOXX, MU | 4 | | | | |

**54 simboli di watchlist senza alcuna news in giornata** (`market_daily.jsonl`: `watchlist_zero_news`: 54).

### 4.3 Fan-out multi-ticker

16 hash distinti hanno generato **44 righe su 81 (54,3%)**. I peggiori:

| Titolo | ticker |
|---|---|
| Cathie Wood Trims AMD After a 120% Rally… | AMD, AVGO, MSFT, MU, ORCL, PLTR, SOXX, SPCX, TSM (**9**) |
| Leading And Lagging Sectors For August 28, 2026 | XLE, XLF, XLK, XLV |
| Nasdaq 100 Falls As Warsh Revives Rate Hike Bets | IWM, MRVL, QQQ, XLK |
| 10 Information Technology Stocks Whale Activity In Today's Session | AMAT, CRM, MU, NVDA |
| 10 Financials Stocks Whale Activity In Today's Session | GS, HOOD, JPM |
| Nvidia Warns Of AI Power Bottleneck — And Bloom Energy Could Benefit | INTC, NVDA, ORCL |

### 4.4 Top news per impatto sul segnale

| # | Ticker | Titolo | Score | Effetto |
|---|---|---|---|---|
| 9279 | CRM | Salesforce Stock Books Best Week Since August 2020 | +0,6166 | **BUY CRM** 1.973,95 $ alle 19:22 |
| 9229/9260 | MRVL | Marvell CEO Calls Google AI Revenue… / Google AI Chip Deal $120B | +0,596 / +0,583 | SKIP_PYRAMIDING ×2 (MRVL chiude −10,28%) |
| 9201 | NVDA | Inside NVIDIA's $13 Billion Hugging Face Bid | +0,3612 | **BUY NVDA** 1.981,54 $ alle 14:07 |
| 9216 | NVDA | Nvidia Warns Of AI Power Bottleneck — And Bloom Energy Could Benefit | −0,1065 | **SELL NVDA** alle 15:52 |
| 9219 | CRM | What's Going on With Salesforce Stock on Friday? | −0,578 (FinBERT) | SKIP_PYRAMIDING CRM |
| 9222 | CRM | Stock of the Day: Where is the Top for Salesforce? | −0,0707 | **SELL CRM** alle 15:22 |

### 4.5 Problemi trovati nell'ingest

* Sanitizzazione: **18 righe su 81 (22,2%)** arrivano al modello con entità HTML non decodificate
  (`&#39;`, `&amp;`) — incluso l'articolo che ha generato il BUY NVDA. Nessun tag HTML residuo.
* Il campo `body_full` è **NULL su tutte le 81 righe** (e su tutta la finestra 08-24 → 09-02): il
  modello vede solo `body_snippet`, media **145 caratteri**.
* `duplicates` (2813) supera `fetched` (676) per benzinga di un fattore 4,2.
* `discarded_stale` benzinga 168, contro 39 il 08-27 e 71 il 08-26 — il valore più alto della settimana.
* gdelt scarta il 99,2% del raccolto per assenza di ticker.
* Nessun campo `retry`/`attempt` persistito: eventuali ritentativi non sono osservabili.

Confidenza dell'analisi ingest: **alta** per ciò che è a DB (`news_log`, `ingestion_stats_daily`);
**nulla** per ciò che accade prima della persistenza (i log container del 2026-08-28 non esistono,
il più vecchio è `worker-2026-09-04.log`).

---

## 5. Tabella performance modelli LLM

### 5.1 Modelli di produzione (ensemble live)

| Modello | risposte | polarity media | sd polarity | confidence media | conf min/max | `eligible=true` | finestra |
|---|---|---|---|---|---|---|---|
| glm-5.2:cloud | 80 | +0,019 | 0,286 | 0,319 | 0,05 / 0,90 | 24 | 14:00:35 → 19:15:13 |
| gpt-oss:20b-cloud | 80 | +0,013 | 0,265 | 0,439 | 0,10 / 0,75 | 24 | 14:00:35 → 19:15:13 |

Nessun `polarity` NULL, nessun parse error persistito, budget **0,0907 $** su 46.473 token input /
5.757 output, `budget_exhausted=false`. Disponibilità trasporto: **80 item su 81 (98,8%)**; l'unico
item senza alcuna risposta è il segnale 9205 (AAPL), con `reasoning="FinBERT fallback (Ollama timeout)"`.
Non esiste misura di latenza per i modelli di produzione (`llm_responses` non ha colonna latenza).

### 5.2 Modelli shadow (non in decisione)

| Modello | richieste | fallimenti | tasso | latenza media | max |
|---|---|---|---|---|---|
| kimi-k2.6:cloud | 81 | 51 | **63,0%** | 83.090 ms | 95.031 ms |
| qwen3.5:cloud | 81 | 29 | **35,8%** | 71.115 ms | 95.031 ms |

Cause: `error:RuntimeError` e `timeout`. Distribuite su tutta la sessione, non concentrate: nessun
outage identificabile, piuttosto un budget di tempo insufficiente (max = 95 s su entrambi).

### 5.3 Composizione dei segnali

| Etichetta | n | % | score medio | conf media | `ensemble_std` medio |
|---|---|---|---|---|---|
| `ensemble:glm-5.2:cloud+gpt-oss:20b-cloud` | 55 | 67,9% | +0,027 | 0,375 | 0,069 |
| `single:gpt-oss:20b-cloud` | 22 | 27,2% | −0,025 | 0,505 | **0,000** |
| `finbert` | 3 | 3,7% | −0,059 | 0,460 | **0,000** |
| `single:glm-5.2:cloud` | 1 | 1,2% | +0,140 | 0,400 | **0,000** |

`fallback_used=true` su **26 righe (32,1%)**, ma **25 di esse hanno entrambe le risposte dei modelli a DB**:
il fallback non è un guasto di trasporto, è l'effetto del filtro `confidence >= 0.4` (`src/llm/ensemble.py:311`).
Il fallback FinBERT per timeout reale è **1 su 81 (1,2%)**.

Distribuzione score: min −0,578 (CRM finbert), max +0,617 (CRM ensemble). 143 valutazioni di
`SKIP_THRESHOLD` su score esattamente 0,000.

### 5.4 Metadati strutturati

`directness`: `unclear` 44, `sector` 34, `direct` 35, `competitor_readthrough` 19, `macro` 13,
`customer_supplier` 5. `risk_flags`: `ambiguous_entity` 82 (51% delle risposte), `low_source_quality` 51,
`already_priced_in` 45, `rumor` 13. **Nessuno di questi campi è un gate**: entrano nel signal store e
nel ranking senza filtro (per disegno, in attesa del golden set QX-01).

### 5.5 Verifica funzionale

| Domanda | Risposta | Evidenza |
|---|---|---|
| L'output LLM è validato prima del signal store? | **Parzialmente.** Lo schema JSON è forzato (Function Calling) e polarity/confidence sono clampate in [-1,1]; enum e range semantici non sono validati (F-055) | `src/llm/ensemble.py:330` |
| L'ensemble gestisce la varianza alta? | **Solo come interruttore binario.** `std ≥ 0,40` → FinBERT; sotto, la varianza non modula nulla | `ensemble.py:321` |
| Le news duplicate pesano più volte? | **No** in senso stretto (dedup per `content_hash`: 4 `SIGNAL_DUPLICATE_SKIP` in `audit_log`), **sì** per fan-out: 1 articolo → fino a 9 segnali su 9 ticker | §4.3 |
| La stessa news può generare segnali multipli? | **Sì, uno per ticker taggato** (per disegno) | §4.3 |
| Confidence bassa riduce il peso? | **Sì** (peso = confidence × peso LOO-ICIR), ma sotto 0,4 il modello viene **escluso**, non attenuato | `ensemble.py:311,327` |
| I modelli sono chiamati offline/background? | **Sì.** Worker Celery `inference`, mai dentro il ciclo portfolio; il ciclo legge `sentiment_signals` da Postgres | `celery_app.py`, `portfolio_scheduler.py` |
| Rischio che un'allucinazione entri in decisione? | **Sì, per costruzione.** Nessun supervisor agent, nessuna verifica RAG delle affermazioni quantitative, nessun gate su `risk_flags`. Il BUY NVDA di giornata è nato da un articolo `{rumor}` | §10 [DAY-006] |

---

## 6. Tabella segnali finali per ticker

Segnali generati il 2026-08-28: **81** su **42 simboli**. Sopra il gate d'ingresso S4 (0,30, in valore assoluto):

| Segnale | Ora | Ticker | Score | Conf | `ensemble_std` | Modello | Esito |
|---|---|---|---|---|---|---|---|
| 9201 | 14:00:41 | NVDA | **+0,3612** | 0,675 | **0,3182** | ensemble | → **BUY** 14:07 |
| 9229 | 15:45:13 | MRVL | **+0,5958** | 0,750 | 0,1768 | ensemble | → SKIP_PYRAMIDING |
| 9219 | 14:46:14 | CRM | **−0,5778** | 0,688 | 0,000 | finbert | → SKIP_PYRAMIDING (nessun BUY: segno negativo) |
| 9260 | 17:46:21 | MRVL | **+0,5833** | 0,750 | 0,0707 | ensemble | → SKIP_PYRAMIDING |
| 9279 | 19:15:07 | CRM | **+0,6166** | 0,825 | 0,1414 | ensemble | → **BUY** 19:22 |

Tutti gli altri 76 segnali sono sotto soglia. Funnel S4 del giorno (`s4_intent_events`, 24 slot decisionali):

| Stadio | n intent | % |
|---|---|---|
| `CANDIDATE_OBSERVED` | 1.711 | 100% |
| `SKIP_ENTRY_FRESHNESS` | 763 | 44,6% |
| `SKIP_ENTRY_GATE` | 532 | 31,1% |
| `SKIP_STALE` | 228 | 13,3% |
| `SKIP_FALLBACK` | 99 | 5,8% |
| `SKIP_PYRAMIDING` | 80 | 4,7% |
| `SKIP_IDEMPOTENCY` | 4 | 0,2% |
| `RANK_OUTSIDE_TOP_N` | 3 | 0,2% |
| **`SUBMITTED`** | **2** | **0,12%** |

La somma delle disposition eguaglia esattamente i candidati: il funnel è chiuso, nessun intent perso.

---

## 7. Tabella ordini generati / eseguiti

### 7.1 Ordini attribuiti (S4, paper)

| Ora decisione | Strat | Ticker | Azione | Qty | Notional | Prezzo atteso | Prezzo fill | Stato | Rationale | Segnale | Risk check |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 14:07:00 | S4 | NVDA | BUY | 8,8178 | 1.981,54 $ | 224,76 (`portfolio_market_snapshot.latest_price`) | **224,72** | filled 14:07:07 | sentiment +0,361, peso 2,0%, rank 4 | 9201 | gate 0,30 ✓, EMA ✓, regime_mult 1,0, anti-pyr ✓ |
| 14:22:00 | S4 | TSLA | SELL (close) | 3,8652 | — | — | **352,3947** | filled 14:22:08 | `expired`: segnale 18,6h > max_age 4h | (9186, 08-27) | — |
| 15:22:00 | S4 | CRM | SELL (close) | 5,4063 | — | — | **262,66** | filled 15:22:07 | `below_entry_gate`: score −0,071 | (9222) | — |
| 15:52:00 | S4 | NVDA | SELL (close) | 8,8178 | — | — | **222,1645** | filled 15:52:06 | `below_entry_gate`: score −0,106, età 1,1h | (9216) | hold minimum 90 min rispettato (105 min) |
| 19:22:00 | S4 | CRM | BUY | 7,6000 | 1.973,95 $ | 259,67 | **259,73** | filled 19:22:06 | sentiment +0,617 (ranked 0,740), peso 2,0%, rank 1 | 9279 | gate 0,30 ✓, EMA ✓, regime_mult 1,0 |

Nessun ordine rifiutato, nessun fill parziale, nessun ordine fuori 13:30–20:00 UTC, nessun ordine su
ticker fuori watchlist. Tutti i fill sono avvenuti entro 2,5 s dalla sottomissione.

### 7.2 Ordini di protezione (stop, non attribuiti a segnale/decisione/trade)

| Ora | Ticker | Qty ordine | Qty posizione | Copertura | Stato finale |
|---|---|---|---|---|---|
| 14:07:07 | CRM | 5 | 5,4063 | 92,5% | canceled (alla chiusura della posizione) |
| 14:22:06 | NVDA | 8 | 8,8178 | 90,7% | canceled |
| 19:37:04 | CRM | 7 | 7,5999 | 92,1% | canceled |

Gli stop sono emessi a quantità intera: la frazione resta scoperta. Sono piazzati **un ciclo dopo**
l'ingresso (NVDA: BUY 14:07 → stop 14:22; CRM: BUY 19:22 → stop 19:37), quindi 15 minuti di
posizione non protetta.

### 7.3 Telemetria dei cicli

`portfolio_cycles.orders_count` va da 2 a 6 per ciclo, per un totale di **88 "ordini"** su 24 cicli,
contro **5 ordini realmente sottomessi**: il campo conta i pesi target del combiner, non le
sottomissioni. Ogni ciclo ha `constraints_fired=[]` e `rebalanced_strategies=[]`; `strategies_run`
sempre `["S1","S4"]`.

---

## 8. Tabella PnL / rendimento

### 8.1 Realizzato (ledger `trades`, chiusure del 2026-08-28)

| Trade | Ticker | Strat | Ingresso | Uscita | Qty | Gross | Costi | **Net** | Apertura |
|---|---|---|---|---|---|---|---|---|---|
| 896 | TSLA | S4 | 08-27 19:37 @354,19 | 08-28 14:22 @352,3947 | 3,8652 | −6,94 | 0,273 | **−7,21 $** | pre-08-28 |
| 895 | CRM | S4 | 08-27 19:37 @253,23 | 08-28 15:22 @262,66 | 5,4063 | +50,98 | 0,754 | **+50,23 $** | pre-08-28 |
| 902 | NVDA | S4 | 08-28 14:07 @224,72 | 08-28 15:52 @222,1645 | 8,8178 | −22,53 | 0,406 | **−22,94 $** | **08-28** |
| | | | | | **Totale** | **+21,51** | **1,43** | **+20,08 $** | |

Trade 903 (CRM, aperto 08-28 19:22 @259,73) è rimasto aperto a fine giornata e si è chiuso il
2026-09-03 a 263,87 per +30,37 $ net: **non** è P&L del 2026-08-28.

Attribuzione: **S4 +20,08 $, S1 0,00 $** (`market_daily.jsonl`, `s1_realizzato`: 0).

### 8.2 Non realizzato e P&L totale

| Misura | Valore | Fonte |
|---|---|---|
| NAV apertura (prev close) | 110.041,95 $ | `portfolio_monitor_snapshots` |
| NAV chiusura 20:00 | 109.802,18 $ | idem |
| **Variazione NAV giornata** | **−239,77 $ (−0,218%)** | idem |
| Unrealized apertura → chiusura | 1.117,91 → 852,66 = **−265,25 $** | idem |
| Posizioni aperte | 48 → 47 | idem |
| P&L economico giornaliero S1 | **−237,88 $** | `economic_pnl.json` |
| P&L economico giornaliero S4 | **−49,54 $** | idem |
| P&L economico giornaliero BOOK | **−287,42 $** | idem |
| SPY / QQQ | −0,227% / −0,649% | `market_daily.jsonl` |

Il book (−0,218%) ha fatto **esattamente SPY** (−0,227%) in una giornata di rotazione fuori dai
semiconduttori (MRVL −10,28%, ARM −6,33%, NVDA −4,57%, AMAT −4,29%). Il P&L di S4 (−49,54 $) è
dominato dal mark-to-market delle 47 posizioni ereditate, non dai 3 trade chiusi.

Differenza fra NAV Alpaca (−239,77) e P&L economico BOOK (−287,42): **47,65 $**. Le due misure usano
timbri di prezzo diversi (snapshot 20:00 vs close ufficiale) e definizioni diverse (la definizione
economica marca dal close del primo giorno della finestra). La differenza è attesa, non è un difetto.

### 8.3 Slippage e costi

`trades.slippage_est` è **identico a `cost_usd`** su tutte e 4 le righe (0,273 / 0,754 / 0,406 / 1,096):
è la stima di costo del modello, non slippage misurato. Confronto prezzo atteso → fill dove disponibile:
NVDA 224,76 → 224,72 (**+1,8 bp favorevole**), CRM 259,67 → 259,73 (**−2,3 bp sfavorevole**). Costi
totali del giorno sulle chiusure: **1,43 $** su 4.744 $ di nozionale scambiato = 3,0 bp.

---

## 9. Analisi correttezza buy/sell

| Controllo | Esito | Evidenza |
|---|---|---|
| BUY solo quando consentito | **OK** | 2 BUY, entrambi con score sopra 0,30, EMA pass, anti-pyramiding verificato, rank dentro top-N |
| SELL/exit generati correttamente | **OK con riserva** | 3 SELL, tutte con motivo esplicito e tracciato. La riserva è l'asimmetria: si compra a 0,30 e si vende appena si scende sotto 0,30, senza banda |
| Stop-loss rispettati | **Non applicabile / guard non armato** | 0 righe in `stop_decisions`; gli stop broker non sono stati toccati. AMAT ha violato `d_hard` in tutti i 24 cicli in shadow senza conseguenze (§10 [DAY-007]) |
| Signal flip rispettato | **OK** | NVDA +0,361 → −0,106 → chiusura al primo beat eleggibile; CRM −0,071 → chiusura |
| Max holding days rispettato | **OK** | TSLA chiusa a 18,6h di età segnale (max_age 4h) |
| Hold minimum (90 min) rispettato | **OK** | NVDA: ingresso 14:07:00, uscita 15:52:00 = 105 min = primo multiplo di ciclo oltre i 90 min (`exit_classification.py:70`) |
| Rebalance band rispettata | **Nessuna banda esiste** | `constraints_fired=[]` su tutti e 24 i cicli; gate entrata 0,30 vs uscita 0 |
| Ordini duplicati | **Nessuno** | 5 ordini attribuiti, 5 id distinti, 5 decision id distinti |
| Ordini contrari ravvicinati | **Uno, con rationale** | CRM: SELL 15:22 → BUY 19:22 (4h00m). Entrambi motivati da segnali distinti (9222 −0,071; 9279 +0,617). Nessun roundtrip < 30 min |
| BUY ripetuti ≥3 senza SELL (pyramiding) | **Nessuno** | 2 BUY su 2 ticker diversi; 6 SKIP_PYRAMIDING hanno bloccato il rabbocco |
| SELL con sentiment positivo (bug A5) | **Nessuno** | TSLA −0,120, CRM −0,071, NVDA −0,106: tutte e 3 con segnale negativo |
| Ordini su ticker non consentiti | **Nessuno** | NVDA e CRM in watchlist |
| Ordini fuori orario | **Nessuno** | 14:07 → 19:37 UTC, tutti dentro 13:30–20:00 |
| Trade su dati stale | **Nessuno** | 2 SKIP_STALE + 228 intent `SKIP_STALE` hanno funzionato |
| Trade su output LLM non valido | **Non verificabile** | Nessuna validazione di enum/range è persistita; 0 parse error registrati |
| Trade con circuit breaker attivo | **Nessuno** | `fallback_counters.consecutive_fallback` non ha incrementi nella giornata |
| Trade su strategia disabilitata | **Nessuno** | S2 disabled, S7 research: 0 ordini. Solo S4 ha sottomesso |
| Coerenza paper/live | **OK, esplicita** | `broker_environment='paper'`, `mode='paper'`, `source='alpaca_paper'` su tutti i 92 snapshot; S4 `mode=paper`, `promotion_blocked=true` |
| Idempotenza retry Celery | **OK, osservata** | 4 `SKIP_IDEMPOTENCY` su NVDA e CRM: il ledger intent ha riconosciuto l'intento già sottomesso negli slot successivi e non ha riemesso l'ordine |
| Riconciliazione ordini/fill/posizioni | **OK** | 14 eventi `ENTRY_RECONCILIATION`/`FILLED`/`BROKER_FILLED` su CRM, NVDA, TSLA; posizioni 48 → 47 coerente con 2 chiusure nette + 1 apertura |
| Ordini identici nello stesso minuto | **Nessuno** | — |
| Score < 0,05 che generano ordini | **Nessuno** | score dei 2 BUY: 0,361 e 0,617 |
| Decisione creata senza ordine (NO-ORDER) | **Nessuno** fra BUY/SELL | Le 543 SKIP_* sono decisioni di non-ordine per disegno |
| `fallback_used=True` su tutti i simboli | **No** | 26/81 (32%), distribuito; Ollama su |

---

## 10. Anomalie trovate

### [DAY-001] `/api/trades` inverte il segno del realizzato di giornata (F-084)

* **Tipo:** Bug
* **Area:** PnL / Frontend
* **Evidenza:**
  * tabella/endpoint: `GET /api/trades?limit=200` vs tabella `trades`
  * timestamp: 2026-08-28 14:22 / 15:22 / 15:52
  * snippet: API TSLA `entry_price: 364.74, net_pnl: -47.7177` — DB `entry_price 354.19, net_pnl -7.2123`.
    API CRM `entry_price: 259.73, net_pnl: 15.8404` — DB `entry_price 253.23, net_pnl 50.2275`.
    API NVDA `net_pnl: -23.1507` — DB `-22.9392`.
* **Descrizione:** l'endpoint restituisce una riga per **ordine broker**, non per trade. I BUY escono
  con `exit_reason="portfolio_buy"` e `net_pnl: null`; i SELL escono con `entry_time`/`entry_order_id`
  nulli e un `entry_price` che non è quello d'ingresso — per CRM è il prezzo del BUY delle 19:22
  (259,73), cioè un ingresso **successivo** all'uscita che sta descrivendo.
* **Impatto:** sommando le righe API il 2026-08-28 risulta un realizzato di **−55,03 $**; il ledger
  dice **+20,08 $**. Segno invertito, scarto 75,11 $. Chiunque legga dal REST (UI, mobile, revisore
  umano, sessione forense che non apra Postgres) ricava una giornata perdente da una vincente.
* **Severità:** High
* **Confidenza:** High
* **Azione consigliata:** far leggere all'endpoint il ledger `trades` (un record per trade chiuso,
  `net_pnl` valorizzato) e spostare la vista per-ordine su `/api/orders`, che già esiste ed è corretta.
* **Test/monitor:** test di contratto che, per una data con chiusure note, verifichi
  `sum(api.net_pnl) == sum(trades.net_pnl)` sullo stesso giorno.

### [DAY-002] `execution_decisions.signal_score` contiene grezzo e moltiplicato nello stesso giorno (F-073)

* **Tipo:** Bug
* **Area:** Signal / Data
* **Evidenza:**
  * tabella: `execution_decisions` vs `s4_intent_events.snapshot`
  * timestamp: 2026-08-28 14:07:00 (NVDA) e 19:22:00 (CRM)
  * snippet: NVDA — `sentiment_signals.score=0.3611968`, `intent.snapshot.score=0.3611968`,
    `intent.disposition.ranked_signal.score=0.4334362` (= ×1,2), `execution_decisions.signal_score=0.3611968` (**grezzo**).
    CRM — `sentiment_signals.score=0.6165789`, `ranked_signal.score=0.7398947` (= ×1,2),
    `execution_decisions.signal_score=0.7398947` (**moltiplicato**).
* **Descrizione:** su entrambi gli ordini il moltiplicatore di signal-velocity valeva 1,2
  (`_compute_signal_velocity`, `SIGNAL_VELOCITY_BOOST`), ma la colonna `signal_score` ha registrato il
  grezzo per uno e il boostato per l'altro. La colonna `velocity_multiplier` è NULL su entrambe le
  righe (migrazione 077 non ancora applicata a quella data), quindi la provenienza non è ricostruibile
  dalla riga stessa.
* **Impatto:** ogni analisi che legga `signal_score` per ricostruire il gate d'ingresso (misure #169/#467,
  calibrazione, IC) confronta grandezze non omogenee. Con boost 1,2 un grezzo di 0,25 entra a 0,30:
  il gate osservato non è il gate applicato.
* **Severità:** High
* **Confidenza:** High
* **Azione consigliata:** persistere sempre il grezzo in `signal_score` e il moltiplicatore in
  `velocity_multiplier` (già previsto da #550 / PR #624), e annotare nel charter la discontinuità
  della serie per le date precedenti.
* **Test/monitor:** invariante a DB — per ogni riga BUY, `signal_score` deve coincidere con
  `sentiment_signals.score` del `signal_id`; ogni scostamento deve essere spiegato da `velocity_multiplier`.

### [DAY-003] `ensemble_std` = 0,000 esatto su 26 righe con entrambi i modelli a DB (F-054)

* **Tipo:** Bug
* **Area:** LLM
* **Evidenza:**
  * tabella: `sentiment_signals` + `llm_responses`
  * timestamp: tutta la sessione 2026-08-28
  * snippet: segnale 9236 (AMD) — `model_id='single:gpt-oss:20b-cloud'`, `ensemble_std=0.000`, ma
    `llm_responses` ha glm `polarity=0.0/conf=0.2` e gptoss `polarity=-0.4/conf=0.6`: la dispersione
    reale è 0,283. Stessa forma su 25 righe su 26 con `fallback_used=true`.
* **Descrizione:** fino al commit `edfd73e0` (2026-09-21, tre settimane **dopo** questa giornata)
  `ensemble_std` era calcolato sui soli contributori eleggibili. Con un solo eleggibile la statistica
  è 0 per costruzione, e il dissenso del modello filtrato sparisce.
* **Impatto:** il 32% dei segnali della giornata dichiara accordo perfetto dove c'era disaccordo. Qualunque
  guard, calibrazione o studio di IC che legga `ensemble_std` su date ≤ 2026-09-20 sta leggendo un
  campo che vale 0 proprio nei casi di disaccordo tipico. La serie ha una discontinuità al 2026-09-21.
* **Severità:** Medium
* **Confidenza:** High (difetto accertato per data del commit di correzione)
* **Azione consigliata:** nessuna correzione di codice (già fatta); annotare la discontinuità nel
  charter e nei preventivi che usano `ensemble_std` come regressore.
* **Test/monitor:** controllo giornaliero `count(*) FILTER (WHERE ensemble_std=0 AND n_responses>1)` — deve restare 0.

### [DAY-004] 18 righe su 81 arrivano al modello con entità HTML non decodificate (F-076)

* **Tipo:** Bug
* **Area:** News / LLM
* **Evidenza:**
  * tabella: `news_log`
  * timestamp: 2026-08-28 14:00:41 (news 9201) e altre 17
  * snippet: `body_snippet` di 9201 = `"Nvidia&#39;s reports a $13 billion bid for Hugging Face…"`;
    9279 = `"…the top S&amp;P 500 performer…"`. Query:
    `SELECT count(*) FROM news_log WHERE created_at::date='2026-08-28' AND (title ~ '&[a-zA-Z]+;|&#[0-9]+;' OR body_snippet ~ '&[a-zA-Z]+;|&#[0-9]+;')` → 18/81 (22,2%).
* **Descrizione:** `sanitize_text` non decodificava le entità HTML fino al commit `edfd73e0` (2026-09-21).
  Il modello riceve `&#39;` al posto dell'apostrofo e `&amp;` al posto di `&`, con grammatica corrotta
  (`"Nvidia's reports"`).
* **Impatto:** degrada il tokenizzatore e la NER proprio sui nomi di entità (`S&amp;P`). Colpisce
  l'articolo che ha generato l'unico BUY in perdita della giornata. Non quantificabile in dollari su
  una singola occorrenza.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** nessuna (corretto il 2026-09-21); annotare che i prompt delle sedute
  precedenti non sono confrontabili con i successivi.
* **Test/monitor:** già presente il conteggio in `docs/evidence`; aggiungere l'asserzione sul testo
  effettivamente inviato al modello, non solo su `news_log`.

### [DAY-005] Il prompt del 2026-08-28 conteneva solo il corpo, mai il titolo, su un teaser di ~145 caratteri (F-046)

* **Tipo:** Bug
* **Area:** LLM / News
* **Evidenza:**
  * file: `src/workers/sentiment.py` alla revisione in produzione quel giorno (`3a3425d7`, 2026-08-26)
  * snippet: `prompt = _DK_COT_PROMPT.format(text=clean_body[:_body_limit], symbol=clean_symbol)` —
    nessun parametro titolo. Il fix titolo è `bf5bef2e` (2026-09-01), quattro giorni dopo.
  * tabella: `news_log.body_full` NULL su 81/81; `avg(length(body_snippet))` = 145 caratteri.
* **Descrizione:** su questa seduta il modello (e FinBERT) hanno valutato un teaser di ~145 caratteri
  senza mai vedere l'headline. Esempio 9219: testo = *"Salesforce stock dipped on Friday due to
  profit-taking following a historic rally driven by Q2 earnings, raised guidance and Claudeforce."*,
  titolo mai passato.
* **Impatto:** l'informazione più densa dell'articolo (il titolo) è assente dall'input su tutta la
  finestra di osservazione precedente al 2026-09-01. Tutte le misure di qualità del segnale su quelle
  date descrivono un modello diverso da quello attuale.
* **Severità:** High (per l'evidenza; il codice è già corretto)
* **Confidenza:** High
* **Azione consigliata:** registrare 2026-09-01 come rottura della serie nel charter, accanto a
  2026-09-21 (F-054/F-076). Verificare perché `body_full` resta NULL: il limite `SENTIMENT_LLM_BODY_CHARS=600`
  non ha alcun effetto se il corpo disponibile è di 145 caratteri.
* **Test/monitor:** asserzione che il prompt effettivo contenga il titolo, e metrica giornaliera
  `avg(length(testo inviato al modello))`.

### [DAY-006] L'unico BUY in perdita nasce dal segnale con la massima divergenza d'ensemble e flag `rumor` (F-037)

* **Tipo:** Rischio
* **Area:** LLM / Orders
* **Evidenza:**
  * tabella: `llm_responses` signal_id 9201, `trades` id 902
  * timestamp: 2026-08-28 14:00:41 → 14:07:00 → 15:52:00
  * snippet: glm `polarity=0.65, confidence=0.75, risk_flags={rumor}`; gptoss `polarity=0.20,
    confidence=0.60, risk_flags={rumor}`. `ensemble_std=0.3182` — il massimo delle 55 righe ensemble
    della giornata (media 0,069). Ordine `92386920`, 1.981,54 $, chiuso a **−22,94 $**.
* **Descrizione:** la soglia di divergenza è 0,40; con due modelli scatta solo se |p1−p2| ≥ 0,566.
  Qui la differenza è 0,45: sotto soglia, ensemble formato, ordine emesso. `ensemble_std` non è letto
  in nessun punto del percorso d'ingresso, ed entrambi i modelli avevano etichettato la notizia come
  `rumor` (un'offerta da 13 miliardi per Hugging Face) senza che il flag pesi nulla.
* **Impatto:** 22,94 $ di perdita realizzata su un segnale che, per costruzione, il sistema non ha
  alcun modo di considerare meno affidabile della media. NVDA ha chiuso la giornata a −4,57%.
* **Severità:** Medium
* **Confidenza:** Medium (il controfattuale "nessuna entrata" è corto e verificabile; la soglia
  esatta di un eventuale gate non lo è)
* **Azione consigliata:** **nessuna taratura in questo periodo.** Registrare l'occorrenza e attendere
  il golden set QX-01 che deve decidere se `ensemble_std` e `risk_flags` meritano un gate.
* **Test/monitor:** monitor che pubblichi giornalmente il decile superiore di `ensemble_std` fra gli
  ordini eseguiti, per costruire la serie senza armare nulla.

### [DAY-007] AMAT viola `d_hard` in tutti i 24 cicli senza uscita né alert (F-036)

* **Tipo:** Rischio
* **Area:** Risk
* **Evidenza:**
  * tabella: `stop_shadow_log`
  * timestamp: 2026-08-28 14:07:05 → 19:52:10 (24 cicli su 24)
  * snippet: `symbol='AMAT', strategy='S1', entry_price=593.80, d_hard=0.2000, d_hard_trigger=475.04,
    observed 461.27–474.09 (media 466.09), d_hard_breached=true` su tutte le righe. `stop_decisions`
    per il 2026-08-28: **0 righe** (l'ultima popolazione di quella tabella è del 2026-07-14).
* **Descrizione:** il trigger di revisione documentato scatta e resta confinato nel log shadow. Nessuna
  `stop_decision`, nessun ordine, nessun `mobile_event`, nessun `alert` nel risk report delle 22:30.
* **Impatto:** AMAT era a −21,5% dall'ingresso quel giorno; alla data di questa analisi è ancora
  aperta a −22,87% (−116,39 $ non realizzati). Uscire al prezzo medio osservato del 2026-08-28
  (466,09) invece che al prezzo corrente (458,00) avrebbe evitato **6,93 $** su 0,857 azioni. La
  cifra è piccola perché AMAT si è mossa poco da allora: il problema è la ricorrenza, non l'importo.
* **Severità:** Medium
* **Confidenza:** High sul fatto, Medium sul costo
* **Azione consigliata:** nessuna modifica di soglia (freeze). Serve però che la violazione **lasci
  una traccia azionabile**: una riga in `stop_decisions` o un `mobile_event` di categoria `risk`,
  senza automatismo di uscita.
* **Test/monitor:** alert giornaliero "posizioni con `d_hard_breached` in ≥1 ciclo", con elenco e
  drawdown, consegnato allo stesso canale del risk report.

### [DAY-008] 37 minuti ciechi all'apertura e 2 ore di finestra sprecate dopo la chiusura (F-021)

* **Tipo:** Bug
* **Area:** Ops / Signal
* **Evidenza:**
  * file: `src/workers/celery_app.py:83,98,156,167,189,274` — `crontab(..., hour="14-21")`
  * timestamp: 2026-08-28 13:30:00 → 14:07:00
  * snippet: mercato aperto alle 13:30 UTC (EDT); primo articolo ingerito 14:00:35, primo ciclo
    portfolio 14:07:00. Gli snapshot 13:30→14:00 riportano `degradations: [{"component":"signal"},{"component":"portfolio_cycle"}]`.
    A fine giornata: ultimo ciclo 19:52, ma la finestra beat arriva fino alle 21:52 — 8 slot ciclo e
    ~12 slot sentiment a mercato chiuso.
* **Descrizione:** le finestre beat sono espresse in ora UTC fissa e ignorano il DST. In EDT si perdono
  i primi 30–37 minuti di seduta e si spendono due ore di schedulazione a mercato chiuso.
* **Impatto:** tutte le notizie pubblicate fra 12:50 e 14:00 (la fascia più densa, pre-apertura e
  apertura) arrivano in un unico blocco alle 14:00:35, con latenza fino a 85,9 minuti. Il 19% della
  seduta non è osservato. Il monitor stesso segnala la degradazione ma nessuno la raccoglie.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** derivare le finestre dal calendario Alpaca invece che da ore UTC fisse.
  È correttezza, non taratura: la finestra osservata deve coincidere con la seduta.
* **Test/monitor:** test che, dato un giorno EDT e un giorno EST, verifichi che il primo slot cada
  entro 5 minuti dall'apertura effettiva.

### [DAY-009] Il resolver deterministico produce 0 verdetti `RESOLVED` su 179 righe (F-057)

* **Tipo:** Bug
* **Area:** News / Data
* **Evidenza:**
  * tabella: `news_resolved_entities`
  * timestamp: 2026-08-28, intera giornata
  * snippet: `NO_TRADE_NOT_TRADABLE` 98, `NO_TRADE_LOW_RESOLUTION_CONFIDENCE` 81, `RESOLVED` **0**.
    `resolved_ticker` NULL su tutte le 179 righe. `directness='direct'` su 179/179.
    Confidenza media 0,427 e 0,528, contro soglia 0,80.
* **Descrizione:** il resolver non raggiunge mai la soglia perché `alias_match` e `llm_agreement` sono
  cablati a False: il massimo ottenibile è 0,60. Le 98 righe `NO_TRADE_NOT_TRADABLE` hanno comunque
  `tradable=false`, mentre le 81 `NO_TRADE_LOW_RESOLUTION_CONFIDENCE` hanno `tradable=true` — cioè il
  sistema sa che il simbolo è negoziabile ma non se lo conferma.
* **Impatto:** il percorso che dovrebbe portare `false_positive_ticker_rate → 0` non è mai attivo. La
  copertura per ora è garantita dal `source_metadata` di Benzinga (che tagga i ticker a monte), non dal
  resolver. Nessun costo in questa giornata: il ticker resolution non ha prodotto errori osservabili.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** correggere il calcolo del punteggio (F-057 è già aperto). Nessuna
  abilitazione dell'enforcement finché il golden set QX-01 non esiste.
* **Test/monitor:** asserzione che, dato un alias noto presente in `ticker_lookup`, `alias_match` sia True.

### [DAY-010] `signal_id` NULL su 546 decisioni su 548 (F-011)

* **Tipo:** Bug
* **Area:** Signal / Data
* **Evidenza:**
  * tabella: `execution_decisions`
  * timestamp: 2026-08-28, 24 cicli
  * snippet: `SKIP_THRESHOLD` 532 righe con `signal_id` NULL su 532; `SELL` 3 righe con `signal_id`
    NULL su 3; `SKIP_PYRAMIDING` 3 su 6 valorizzate; solo i 2 `BUY` hanno il `signal_id`.
    `s4_intent_id` NULL su **tutte** e 548 le righe.
* **Descrizione:** la catena segnale → decisione → trade si interrompe sulla quasi totalità delle
  decisioni. Le SELL, in particolare, citano il segnale nel testo libero di `reason` ma non lo
  collegano: per risalire al segnale 9222 che ha chiuso CRM bisogna leggere una stringa.
* **Impatto:** impossibile calcolare l'IC lato uscita, o misurare quale segnale abbia chiuso quale
  posizione, senza parsing di testo libero. Ogni analisi di attribuzione su queste righe è fragile.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** valorizzare `signal_id` e `s4_intent_id` anche sui percorsi di uscita e di
  skip. È correttezza dell'evidenza.
* **Test/monitor:** invariante `count(*) FILTER (WHERE decision IN ('BUY','SELL') AND signal_id IS NULL) = 0`.

### [DAY-011] Il 54% delle righe scorate nasce da articoli fan-out multi-ticker (F-012)

* **Tipo:** Rischio
* **Area:** News
* **Evidenza:**
  * tabella: `news_log`
  * timestamp: 2026-08-28
  * snippet: 16 `content_hash` distinti generano 44 righe su 81. L'articolo
    `a816cec1…` ("Cathie Wood Trims AMD After a 120% Rally") produce **9** righe (AMD, AVGO, MSFT, MU,
    ORCL, PLTR, SOXX, SPCX, TSM).
* **Descrizione:** un singolo articolo produce fino a 9 segnali indipendenti su 9 ticker, ognuno dei
  quali compete per uno slot nel ranking S4 come se fosse evidenza separata.
* **Impatto:** l'unità di osservazione non è l'evento ma la coppia (articolo, ticker). Il segnale
  9216 (NVDA, −0,1065) viene da un articolo il cui soggetto è **Bloom Energy**, e ha chiuso una
  posizione NVDA da 1.981 $. Su 51% delle risposte i modelli hanno alzato il flag `ambiguous_entity`.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** nessuna in questo periodo (è la materia del disegno "unità = evento" già in
  discussione). Registrare la proporzione giornaliera come serie.
* **Test/monitor:** metrica giornaliera "quota di righe scorate provenienti da hash con ≥3 ticker".

### [DAY-012] `duplicates` (2.813) supera `fetched` (676) di un fattore 4,2 (F-007)

* **Tipo:** Anomalia
* **Area:** News / Data
* **Evidenza:**
  * tabella: `ingestion_stats_daily`
  * timestamp: 2026-08-28 19:45:01
  * snippet: `alpaca_benzinga | fetched 676 | queued 337 | duplicates 2813 | discarded_stale 168`.
    Stesso pattern il 08-26 (585/2366) e il 08-27 (550/2535).
* **Descrizione:** il contatore dei duplicati non è commensurabile con quello dei fetch: conta
  probabilmente le consegne (REST + WebSocket) o i tentativi per ticker, non gli articoli.
* **Impatto:** il tasso di duplicazione non è calcolabile da questi campi, e con esso l'efficienza
  dell'ingest. `discarded_stale` a 168 (contro 39 e 71 nei due giorni precedenti) non è interpretabile
  senza sapere su quale denominatore insiste.
* **Severità:** Low
* **Confidenza:** High
* **Azione consigliata:** definire e documentare il denominatore di ciascun contatore.
* **Test/monitor:** asserzione `duplicates <= fetched` oppure rinomina del campo.

### [DAY-013] Gli stop protettivi coprono la sola parte intera e arrivano un ciclo dopo l'ingresso (F-022)

* **Tipo:** Rischio
* **Area:** Risk / Broker
* **Evidenza:**
  * endpoint: `GET /api/orders`
  * timestamp: 2026-08-28 14:07:07, 14:22:06, 19:37:04
  * snippet: `CRM sell qty "5"` su posizione 5,4063 (92,5%); `NVDA sell qty "8"` su 8,8178 (90,7%);
    `CRM sell qty "7"` su 7,5999 (92,1%). Tutti e tre `status: canceled`, `signal_id/decision_id/trade_id` null.
* **Descrizione:** le quantità frazionarie non sono coperte, e lo stop viene creato al ciclo successivo
  all'ingresso: NVDA è rimasta senza protezione dalle 14:07 alle 14:22 (15 minuti).
* **Impatto:** dal 7,5% al 9,3% del nozionale resta scoperto per tutta la vita della posizione; il
  100% lo è per 15 minuti dopo l'ingresso. Nessuna perdita materializzata in questa giornata.
* **Severità:** Low
* **Confidenza:** High
* **Azione consigliata:** nessuna in questo periodo. Registrare la copertura come serie.
* **Test/monitor:** metrica giornaliera `qty_stop / qty_posizione` per ogni posizione aperta.

### [DAY-014] Il risk report non ha metriche per sleeve e il drawdown non coincide con quello del monitor (F-003, F-050)

* **Tipo:** Bug
* **Area:** Risk
* **Evidenza:**
  * tabella: `risk_reports` id 77 vs `portfolio_monitor_snapshots`
  * timestamp: 2026-08-28 22:30:01 vs 20:00:00
  * snippet: risk report `combined_drawdown = 0.012429` (1,243%), `per_strategy_metrics = {}`,
    `alerts = []`. Snapshot di chiusura `current_drawdown = 0.007627` (0,763%), `drawdown_limit` valorizzato.
* **Descrizione:** due misure di drawdown differiscono di 0,48 punti percentuali sullo stesso giorno,
  e la struttura che dovrebbe contenerle per strategia è vuota.
* **Impatto:** nessun drawdown per sleeve è monitorato; l'unico numero pubblicato non è riconciliato
  con quello che il monitor usa per gli alert. Un eventuale superamento di limite per S4 o S1 non
  sarebbe rilevabile.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** popolare `per_strategy_metrics` e allineare la definizione di drawdown alle
  due superfici (o dichiarare esplicitamente che misurano cose diverse).
* **Test/monitor:** asserzione giornaliera sulla coerenza fra `risk_reports.combined_drawdown` e
  l'ultimo `portfolio_monitor_snapshots.current_drawdown` della seduta.

### [DAY-015] Il dossier deterministico del 2026-08-28 non è mai stato generato (F-044)

* **Tipo:** Anomalia
* **Area:** Ops
* **Evidenza:**
  * directory: `docs/evidence/dossier/`
  * timestamp: 2026-08-28
  * snippet: presenti `2026-08-27.json` e `2026-08-31.json`, assente `2026-08-28.json`. 32 file in
    totale; l'altro venerdì mancante è `2026-09-05`.
* **Descrizione:** il dossier giornaliero, che è la fonte del classificatore causale alpha-miss e
  dell'attribuzione beta, non esiste per questa seduta. `market_daily.jsonl` per il 08-28 c'è ed è
  completo, quindi il buco è specifico del generatore del dossier.
* **Impatto:** l'analisi causale delle 5 miss della giornata (`NO_NEWS` 3, `THIN_NEUTRAL` 2) è
  disponibile solo in forma aggregata; i 7 mover "catturati" non sono verificabili posizione per posizione.
* **Severità:** Low
* **Confidenza:** High
* **Azione consigliata:** il generatore deve fallire rumorosamente (già materia di F-044/F-510);
  rigenerare a posteriori il dossier del 08-28 e del 09-05 se i dati lo consentono.
* **Test/monitor:** controllo settimanale "un dossier per ogni seduta aperta del calendario Alpaca".

### [DAY-016] CRM venduta alle 15:22 e ricomprata alle 19:22 nella stessa seduta (F-013)

* **Tipo:** Anomalia
* **Area:** Orders
* **Evidenza:**
  * tabella: `execution_decisions` 15756 e 16131, `trades` 895 e 903
  * timestamp: 2026-08-28 15:22:00 → 19:22:00
  * snippet: SELL @262,66 su segnale 9222 (score **−0,071**, conf 0,275, `low_source_quality` +
    `ambiguous_entity`); BUY @259,73 su segnale 9279 (score **+0,617**, conf 0,825, event `earnings`).
* **Descrizione:** non esiste banda fra gate d'ingresso (0,30) e gate d'uscita (0): un segnale di
  −0,071 con confidenza 0,275 basta a liquidare una posizione da 1.420 $, e quattro ore dopo un
  segnale opposto la riapre più grande (1.974 $). Nessun vincolo di cooldown fra le due direzioni.
* **Impatto:** su questa occorrenza il churn è stato **favorevole**: riacquisto 2,93 $ più in basso su
  5,406 azioni = +15,84 $, meno ~1,30 $ di frizione aggiuntiva = **+14,54 $ di beneficio netto**. Il
  rischio resta strutturale: la stessa dinamica con il movimento invertito costa lo stesso importo di segno opposto.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** nessuna taratura. Registrare il churn come serie firmata (beneficio/perdita)
  in modo che il periodo di osservazione produca un segno, non un aneddoto.
* **Test/monitor:** metrica giornaliera "coppie SELL→BUY o BUY→SELL sullo stesso simbolo entro la
  seduta", con il delta prezzo associato.

### [DAY-017] CRM chiusa su un segnale con confidenza 0,275 mentre per comprarla ne servirebbe molta di più (F-059)

* **Tipo:** Rischio
* **Area:** Signal / Orders
* **Evidenza:**
  * tabella: `sentiment_signals` 9222, `execution_decisions` 15756
  * timestamp: 2026-08-28 15:00:26 → 15:22:00
  * snippet: segnale 9222 — `score=-0.0707, confidence=0.275`, contributi glm `-0.15/0.20` e gptoss
    `-0.40/0.35`, **entrambi sotto il floor di eleggibilità 0,40**, risk_flags `low_source_quality` e
    `ambiguous_entity`. Titolo: *"Stock of the Day: Where is the Top for Salesforce?"* (colonna d'opinione).
* **Descrizione:** l'ingresso richiede |score| ≥ 0,30; l'uscita scatta appena |score| scende sotto
  0,30, inclusi segnali che l'ensemble stesso ha giudicato non abbastanza confidenti per contribuire.
  Il rigore è asimmetrico.
* **Impatto:** una posizione da 1.420 $ è stata liquidata su un'opinione a bassa confidenza. In questa
  occorrenza l'uscita è stata redditizia (+50,23 $ realizzati), quindi nessun costo attribuibile.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** nessuna taratura (è esattamente una soglia congelata). Registrare
  l'occorrenza perché la decisione del 2026-09-28 abbia dati.
* **Test/monitor:** serie giornaliera "uscite decise da segnali con confidence < min_confidence".

### [DAY-018] Il fallback per divergenza emette un verdetto fuori dall'intervallo dei due modelli sostituiti

* **Tipo:** Bug
* **Area:** LLM
* **Evidenza:**
  * tabella: `sentiment_signals` 9219 e 9218, `llm_responses`
  * timestamp: 2026-08-28 14:46:14 e 14:00-ca.
  * snippet: **CRM 9219** — gptoss `polarity=+0.60, conf=0.70`; glm `polarity=0.00, conf=0.80`;
    std = 0,424 ≥ soglia 0,40 → `aggregate()` restituisce None →
    `reasoning="FinBERT fallback (ensemble divergence)"`, **score = −0,578, confidence 0,688**.
    **ORCL 9218** — gptoss `+0.55/0.60`, glm `−0.20/0.40` → FinBERT **+0,106**.
    Testo valutato (senza titolo, cfr. [DAY-005]): *"Salesforce stock dipped on Friday due to
    profit-taking following a historic rally driven by Q2 earnings, raised guidance and Claudeforce."*
* **Descrizione:** quando i due LLM divergono, il sistema non degrada verso un indicatore
  deterministico (medie mobili, RSI, come prescrive la guida architetturale) ma verso **un terzo
  modello di sentiment**, FinBERT, che legge la stessa frase con una lettura di superficie
  ("dipped", "profit-taking") e produce un verdetto di magnitudine 0,578 — più estremo di entrambi i
  modelli che sostituisce e di segno opposto a quello di gpt-oss. Su CRM il segno di FinBERT è
  risultato **sbagliato**: CRM ha chiuso la settimana a +24,31% ed è salita da 253,23 a 262,74
  durante la seduta.
* **Impatto:** il guardrail anti-allucinazione amplifica la varianza invece di ridurla. In questa
  giornata il −0,578 ha prodotto solo uno `SKIP_PYRAMIDING` (CRM era già a libro) e il ranker ha poi
  preferito il segnale ensemble più recente, quindi **nessun ordine è cambiato**. Con la stessa
  dinamica su un simbolo non detenuto, un −0,578 sarebbe passato il gate d'uscita e, con segno
  invertito, il gate d'ingresso.
* **Severità:** Medium
* **Confidenza:** High sul meccanismo, High sull'assenza di costo in questa occorrenza
* **Azione consigliata:** nessuna taratura della soglia. Ma il percorso di fallback va reso
  **conservativo per costruzione**: in caso di divergenza il risultato corretto è "nessun segnale",
  non "un segnale diverso". Ticket di correttezza: rendere il fallback per divergenza un `NO_SIGNAL`
  anziché una sostituzione di modello, oppure vincolare l'output FinBERT all'inviluppo dei modelli
  sostituiti. La scelta va pre-registrata prima di essere misurata.
* **Test/monitor:** metrica giornaliera "fallback per divergenza il cui segno non coincide con quello
  di nessun modello sostituito".

### [DAY-019] Il 32% dei segnali è etichettato fallback senza che nessun modello abbia fallito (F-078)

* **Tipo:** Bug
* **Area:** LLM / Ops
* **Evidenza:**
  * tabella: `sentiment_signals` + `llm_responses`
  * timestamp: 2026-08-28, intera giornata
  * snippet: 26 righe con `fallback_used=true`; **25 di esse hanno 2 risposte dei modelli a DB**.
    L'unica con 0 risposte è 9205 (AAPL, `"FinBERT fallback (Ollama timeout)"`). Esempio 9213 (MU):
    glm `conf=0.35`, gptoss `conf=0.40` → solo gptoss supera il floor 0,40 → `single:gpt-oss:20b-cloud`,
    `fallback_used=true`.
* **Descrizione:** `fallback_used` mescola tre situazioni distinte: guasto di trasporto (1 caso),
  divergenza d'ensemble (2 casi), e semplice filtro di confidenza (23 casi). `llm_responses.eligible`
  è inoltre forzato a False su tutte le risposte dei fallback (`force_ineligible=result.fallback_used`,
  `sentiment.py:871`), quindi risposte con confidenza 0,70 e 0,80 risultano "non eleggibili".
* **Impatto:** il "FinBERT fallback rate" della giornata è **3,7%** se si contano le etichette e
  **1,2%** se si contano i guasti reali; l'"Ollama down rate" è **0%**. Qualunque monitor costruito su
  `fallback_used` sovrastima di un fattore 26 l'indisponibilità dell'ensemble. Il campo `eligible` non
  è utilizzabile per ricostruire chi ha superato il floor.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** separare il motivo del fallback in un campo dedicato
  (`transport_failure` / `divergence` / `confidence_floor`) e smettere di forzare `eligible=False`.
  È correttezza: senza questa distinzione l'evidenza su disponibilità e qualità è indistinguibile.
* **Test/monitor:** serie giornaliera dei tre motivi separati.

### [DAY-020] 20 slot schedulati non lasciano alcuna traccia e l'assenza va dedotta (F-065)

* **Tipo:** Ambiguità
* **Area:** Ops
* **Evidenza:**
  * tabelle: `sentiment_signals`, `portfolio_cycles`
  * timestamp: 2026-08-28 17:15, 19:00, 19:30, 19:45 e 20:00→21:45 (sentiment); 20:07→21:52 (cicli)
  * snippet: 24 cicli portfolio persistiti su 32 slot schedulati (`hour="14-21"`, minuti 7/22/37/52);
    20 slot sentiment con righe su 32. `ensemble_cycle_health` è vuota per questa data (la tabella
    esiste solo dal 2026-09-02); `finbert_fallback_events` dal 2026-09-14.
* **Descrizione:** non è distinguibile il caso "il ciclo è partito e non aveva nulla da fare" dal caso
  "il ciclo non è partito". Per i cicli dopo le 20:00 la spiegazione plausibile è il guard di mercato
  chiuso, ma non esiste una riga che lo dica.
* **Impatto:** l'osservabilità della pipeline è per assenza. Un'interruzione reale del worker nello
  stesso intervallo produrrebbe esattamente la stessa evidenza — ed è successo, a giudicare dalle
  degradations `signal stale` di 17:16-17:30, 19:03-19:15 e 19:31-19:55, che nessuno ha raccolto.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** persistere un esito per ogni slot schedulato, anche vuoto ("nessun articolo
  nuovo", "mercato chiuso"). `ensemble_cycle_health` fa già questo dal 2026-09-02: estenderne la
  copertura ai cicli portfolio.
* **Test/monitor:** riconciliazione giornaliera "slot schedulati vs slot con esito persistito".

### [DAY-021] Nessun alert in tutta la seduta, a fronte di quattro condizioni che ne meritavano uno (F-062)

* **Tipo:** Rischio
* **Area:** Ops / Risk
* **Evidenza:**
  * tabelle: `mobile_events` (0 righe per il 2026-08-28), `risk_reports.alerts` (`[]`)
  * timestamp: 2026-08-28, intera giornata
  * snippet: nello stesso giorno — AMAT oltre `d_hard` in 24/24 cicli; resolver a 0 verdetti su 179;
    degradation `signal stale` in 4 finestre distinte; 37 minuti di seduta senza alcun ciclo.
* **Descrizione:** le condizioni sono state rilevate e persistite (shadow log, `news_resolved_entities`,
  `degradations`) ma nessuna ha un canale. Il risk report, l'unico artefatto che pubblica `alerts`,
  esce alle 22:30 con lista vuota.
* **Impatto:** un operatore che guardi solo i canali di allerta vede una giornata pulita. Le anomalie
  sono recuperabili solo da una sessione forense come questa, cioè a posteriori e a campione.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** collegare `degradations` del monitor e `d_hard_breached` dello shadow log a
  `mobile_events`, con severità informativa. Nessun automatismo di trading.
* **Test/monitor:** asserzione "ogni `degradation` di severità ≥ warning persistita per ≥3 snapshot
  consecutivi genera un `mobile_event`".

### [DAY-022] Due segnali fortemente rialzisti su MRVL nel giorno in cui MRVL perde il 10,28% (F-043)

* **Tipo:** Osservazione
* **Area:** LLM / Signal
* **Evidenza:**
  * tabella: `sentiment_signals` 9229 e 9260, `market_daily.jsonl`
  * timestamp: 2026-08-28 15:45:13 e 17:46:21
  * snippet: 9229 `+0.5958/conf 0.750` da *"Marvell CEO Calls Google AI Revenue Opportunity a 'Monster
    Number'"*; 9260 `+0.5833/conf 0.750` da *"Marvell's Google AI Chip Deal Could Drive $120 Billion in
    Long-Term Revenue"*. MRVL chiude a **−10,28%**, il peggior mover della watchlist.
* **Descrizione:** due headline promozionali sulla stessa notizia (l'accordo Google) hanno prodotto i
  due segnali più forti della giornata dopo CRM, in direzione opposta al movimento reale. Entrambi i
  segnali sono passati il gate d'ingresso 0,30.
* **Impatto:** **nessuno**, per un motivo accidentale: MRVL era già a libro dal 2026-07-14 e il guard
  anti-pyramiding P0-05 ha bloccato entrambi gli ingressi. Senza quel blocco S4 avrebbe comprato
  ~2.200 $ di MRVL a metà di una discesa del 10%. La perdita evitata sul residuo intraday
  (dall'ingresso 15:52 a 224,74 fino a 217,95 di fine giornata) sarebbe stata dell'ordine di **−66 $**.
* **Severità:** Low (per la giornata), High come segnale di qualità del segnale
* **Confidenza:** Medium (il controfattuale sulla size è plausibile ma non osservato)
* **Azione consigliata:** nessuna. Registrare l'occorrenza: è materiale per il golden set QX-01 e per
  la decisione di fine osservazione sul valore informativo delle headline analyst-driven.
* **Test/monitor:** serie "segnali sopra gate il cui segno è opposto al rendimento di seduta del simbolo".

### [DAY-023] Ingresso su CRM 38 minuti prima della chiusura, su un articolo che racconta un movimento già avvenuto (F-030)

* **Tipo:** Osservazione
* **Area:** Signal / Orders
* **Evidenza:**
  * tabella: `sentiment_signals` 9279, `trades` 903, `stop_shadow_log`
  * timestamp: pubblicazione 18:54:15 → scoring 19:15:07 → ordine 19:22:00 → chiusura 20:00
  * snippet: testo valutato = *"Salesforce closed up 24.31% for the week, its strongest run since
    August 2020 and the top S&amp;P 500 performer, after an 80% Q2 EPS beat and Anthropic AI deal."*
    Fill a 259,73; ultimo prezzo osservato dal sistema alle 19:52:10 = **256,55** (−1,22%).
* **Descrizione:** l'articolo è un riepilogo retrospettivo della settimana: l'informazione è, per
  costruzione, già nel prezzo. La latenza pubblicazione → ordine è di 28 minuti, ma la latenza
  evento → ordine è di giorni.
* **Impatto:** la posizione è nata immediatamente sotto il prezzo d'ingresso. Nessun costo attribuibile:
  il trade 903 si è chiuso il 2026-09-03 a 263,87 con **+30,37 $** netti. L'osservazione riguarda il
  timing, non l'esito.
* **Severità:** Low
* **Confidenza:** High
* **Azione consigliata:** nessuna. È esattamente il fenomeno che F-030 sta misurando.
* **Test/monitor:** già coperto dalla serie di latenza evento → punteggio.

### [DAY-024] I log applicativi del 2026-08-28 non esistono (F-027)

* **Tipo:** Non verificabile
* **Area:** Ops
* **Evidenza:**
  * directory: `logs/containers/`
  * timestamp: 2026-08-28
  * snippet: il file più vecchio è `worker-2026-09-04.log`; nessun `*-2026-08-28.log`.
* **Descrizione:** l'intera fase 2 del protocollo forense che dipende dai log (chiamate LLM per modello,
  timeout, retry, eccezioni silenziose, restart dei worker) non è eseguibile per questa data.
* **Impatto:** tutto ciò che questo report afferma proviene da Postgres, dall'API REST e dagli
  artefatti in `docs/evidence`. Restart dei worker, eccezioni non propagate e retry Celery sono
  **non verificabili** per il 2026-08-28.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** nessuna retroattiva. La persistenza è attiva dal 2026-09-04.
* **Test/monitor:** controllo settimanale che esista un file di log per ogni seduta della finestra di osservazione.

---

## 11. False positive e aree risultate corrette

| Area | Verifica | Esito |
|---|---|---|
| **Reuters "provider down"** | Righe `reuters` in `ingestion_stats_daily` il 08-26, 08-27 e 08-29 ma non il 08-28, e **zero righe in `news_log` in tutta la finestra** | **Falso allarme.** Non è un provider: sono le scritture della suite di test contro il DB di produzione (F-028). La loro assenza il 08-28 significa che i test non hanno girato, non che una fonte è caduta |
| **Ollama down** | 80 risposte su 81 item dai due modelli di produzione; budget 0,0907 $ speso, `budget_exhausted=false`; `fallback_counters.consecutive_fallback` senza incrementi | **Corretto.** Ollama Cloud **up** per l'intera sessione. 0 ore di downtime. I 63 fallimenti shadow riguardano kimi/qwen, fuori dal percorso decisionale |
| **SELL con sentiment positivo (bug A5)** | Le 3 SELL hanno segnali −0,120, −0,071, −0,106 | **Nessuna occorrenza** |
| **Roundtrip < 30 min** | Intervallo minimo BUY→SELL sullo stesso simbolo: NVDA 105 min | **Nessuna occorrenza** |
| **Ordini identici nello stesso minuto** | 5 ordini, 5 minuti distinti | **Nessuna occorrenza** |
| **Ordini senza segnale** | 5 su 5 attribuiti a una decisione e a un `signal_id` o a un `reason` esplicito; i 3 ordini non attribuiti sono stop protettivi | **Nessuna occorrenza** (diverso da F-042 del 2026-09-16) |
| **Score < 0,05 che generano ordini** | 0,361 e 0,617 | **Nessuna occorrenza** |
| **Hold minimum** | NVDA 105 min = primo beat oltre i 90 min configurati | **Corretto** |
| **Idempotenza** | 4 `SKIP_IDEMPOTENCY` hanno impedito la riemissione dell'ordine NVDA negli slot 14:22 e successivi | **Corretto e osservato** |
| **Dedup news** | 4 `SIGNAL_DUPLICATE_SKIP` e 420 `SIGNAL_STALE_SKIP` in `audit_log`; 81 righe scorate, nessuna coppia (hash, ticker) ripetuta | **Corretto** |
| **Funnel S4 chiuso** | 1.711 candidati = somma esatta delle 8 disposition | **Corretto** |
| **Riconciliazione** | 14 eventi `ENTRY_RECONCILIATION/FILLED/BROKER_FILLED`; posizioni 48 → 47 coerenti con 2 chiusure nette e 1 apertura; `portfolio_cycle_persist_failures` vuota | **Corretto** |
| **Paper/live** | `broker_environment='paper'` su 92/92 snapshot, S4 `mode=paper` e `promotion_blocked=true` | **Corretto e non ambiguo** |
| **Anti-pyramiding P0-05** | 6 blocchi, fra cui i due su MRVL nel giorno del −10,28% | **Corretto, e in questa giornata protettivo** |
| **`SKIP_FALLBACK`** | NOK +0,150, LLY +0,120, UNH +0,008: tutti sotto il gate 0,30 comunque | **Nessun alpha miss materiale** |
| **`exit_mechanism` post-#184** | Le 3 SELL hanno `reason` in forma `[meccanismo] descrizione` con età e score espliciti, cioè la forma post-correzione | **Etichette osservate, non dedotte per età.** Nessuna riserva #184 da applicare a questo report |

---

## 12. Dati mancanti o non accessibili

| Cosa manca | Perché | Query/risorsa che servirebbe |
|---|---|---|
| Log applicativi del 2026-08-28 | Persistenza su host attiva solo dal 2026-09-04 (F-027) | — irrecuperabile |
| Latenza per chiamata LLM di produzione | `llm_responses` non ha colonna latenza (solo `llm_shadow_responses` ce l'ha) | `ALTER TABLE llm_responses ADD COLUMN latency_ms integer` |
| Conteggi di retry/timeout per modello di produzione | Nessuna tabella di trasporto (F-086) | — |
| `ensemble_cycle_health` per il 2026-08-28 | Tabella popolata solo dal 2026-09-02 | non misurato ≠ nessun problema |
| `finbert_fallback_events` per il 2026-08-28 | Tabella popolata solo dal 2026-09-14 | l'evidenza runtime di quali componenti FinBERT abbia ricevuto **non esiste** per questa data |
| Prezzi di chiusura ufficiali per simbolo | `market_daily.jsonl` riporta solo SPY, QQQ e i mover in forma testuale | `GET /v2/stocks/bars` Alpaca con `timeframe=1Day, start=2026-08-28` — servirebbe per quantificare il controfattuale dell'uscita NVDA |
| Filtro per data su `/api/decisions` e `/api/signals` | Gli endpoint accettano solo `limit` e ignorano silenziosamente `date`, `start`, `end`: con `limit=200` si arriva al 2026-09-21, mai al 2026-08-28 | l'analisi è stata fatta su Postgres. Servirebbe `?from=&to=` sugli endpoint, altrimenti la superficie REST non è usabile per il forense |
| Dossier deterministico del 2026-08-28 | Mai generato (DAY-015) | `docs/evidence/dossier/2026-08-28.json` |
| `news_queue_drops`, `stale_drop_metrics_daily` | Tabelle introdotte dopo questa data | non misurato |
| Attribuzione dello slippage reale | `trades.slippage_est` è una copia di `cost_usd` (F-015) | confronto fill vs mid al momento della sottomissione |

---

## 13. Raccomandazioni immediate

Tutte di sola correttezza: nessuna tocca soglie, pesi o parametri di strategia (charter fino al 2026-09-28).

1. **Riparare `/api/trades`** (DAY-001). È la raccomandazione più urgente: è l'unica superficie che
   pubblica un numero di P&L col segno sbagliato.
2. **Rendere `signal_score` univoco** (DAY-002) e annotare nel charter che la serie precedente alla
   migrazione 077 mescola grezzo e moltiplicato.
3. **Registrare nel charter le tre rotture di serie già identificate**: 2026-09-01 (titolo nel prompt,
   F-046), 2026-09-21 (`ensemble_std` su tutte le risposte, F-054; entità HTML, F-076). Senza questa
   annotazione qualunque confronto pre/post è una discontinuità silenziosa.
4. **Separare i tre motivi di fallback** (DAY-019): senza questa distinzione il tasso di
   indisponibilità dell'ensemble è sovrastimato di un fattore 26 e non è misurabile.
5. **Far parlare `d_hard`** (DAY-007): una violazione in 24 cicli su 24 deve lasciare una riga
   azionabile, non solo uno shadow log.
6. **Derivare le finestre beat dal calendario Alpaca** (DAY-008): la finestra osservata deve coincidere
   con la seduta, altrimenti il 19% di ogni giornata EDT non è nel campione.
7. **Valorizzare `signal_id` e `s4_intent_id` sulle uscite** (DAY-010): senza, l'IC lato uscita non è calcolabile.

## 14. Test o monitor da aggiungere

| # | Monitor / test | Copre |
|---|---|---|
| 1 | Contratto `sum(/api/trades.net_pnl) == sum(trades.net_pnl)` per giorno | DAY-001 |
| 2 | Invariante: per ogni BUY, `signal_score` = `sentiment_signals.score` × `velocity_multiplier` | DAY-002 |
| 3 | `count(*) FILTER (WHERE ensemble_std = 0 AND n_responses > 1)` = 0 | DAY-003 |
| 4 | Asserzione sul prompt effettivo: contiene il titolo; metrica `avg(len(testo inviato))` | DAY-004, DAY-005 |
| 5 | Serie giornaliera del decile superiore di `ensemble_std` fra gli ordini eseguiti | DAY-006 |
| 6 | Alert giornaliero "posizioni con `d_hard_breached` in ≥1 ciclo" | DAY-007 |
| 7 | Test parametrico EDT/EST: primo slot beat entro 5 min dall'apertura effettiva | DAY-008 |
| 8 | `count(*) FILTER (WHERE decision IN ('BUY','SELL') AND signal_id IS NULL)` = 0 | DAY-010 |
| 9 | Quota giornaliera di righe scorate da hash con ≥3 ticker | DAY-011 |
| 10 | Rapporto `qty_stop / qty_posizione` per ogni posizione aperta | DAY-013 |
| 11 | Coerenza `risk_reports.combined_drawdown` ↔ ultimo `current_drawdown` di seduta | DAY-014 |
| 12 | Controllo settimanale "un dossier per ogni seduta aperta del calendario Alpaca" | DAY-015 |
| 13 | Metrica "coppie SELL→BUY sullo stesso simbolo entro la seduta", con delta prezzo firmato | DAY-016 |
| 14 | Serie "uscite decise da segnali con `confidence` < `min_confidence`" | DAY-017 |
| 15 | Metrica "fallback per divergenza con segno diverso da entrambi i modelli sostituiti" | DAY-018 |
| 16 | Serie separata dei tre motivi di fallback | DAY-019 |
| 17 | Riconciliazione "slot schedulati vs slot con esito persistito" | DAY-020 |
| 18 | Degradation persistente ≥3 snapshot → `mobile_event` | DAY-021 |
| 19 | Serie "segnali sopra gate con segno opposto al rendimento di seduta" | DAY-022 |
| 20 | Controllo settimanale "un file di log per ogni seduta della finestra" | DAY-024 |

## 15. Ticket tecnici suggeriti

Solo difetti di correttezza, come impone il charter. Nessuno propone una taratura.

| Ticket | Titolo | Priorità | Finding |
|---|---|---|---|
| T-1 | `/api/trades` deve servire il ledger `trades`, non gli ordini broker (il realizzato di giornata esce col segno invertito) | **P0** | F-084 / DAY-001 |
| T-2 | `execution_decisions.signal_score`: una sola provenienza, con `velocity_multiplier` accanto | **P0** | F-073 / DAY-002 |
| T-3 | Annotare nel charter le rotture di serie 2026-09-01 e 2026-09-21 e i campi coinvolti | **P0** | DAY-003, DAY-004, DAY-005 |
| T-4 | Separare `fallback_reason` in `transport_failure` / `divergence` / `confidence_floor`; smettere di forzare `eligible=False` | **P1** | F-078 / DAY-019 |
| T-5 | Il fallback per divergenza deve essere fail-closed (`NO_SIGNAL`), non una sostituzione di modello con verdetto fuori inviluppo | **P1** | DAY-018 (nuovo) |
| T-6 | `d_hard_breached` deve produrre una riga azionabile (`stop_decisions` o `mobile_event`), senza automatismi di uscita | **P1** | F-036 / DAY-007 |
| T-7 | Finestre beat derivate dal calendario Alpaca invece che da `hour="14-21"` fisso | **P1** | F-021 / DAY-008 |
| T-8 | `signal_id` e `s4_intent_id` valorizzati anche su uscite e skip | **P1** | F-011 / DAY-010 |
| T-9 | Persistere un esito per ogni slot schedulato, anche vuoto | **P2** | F-065 / DAY-020 |
| T-10 | `risk_reports.per_strategy_metrics` popolato; drawdown riconciliato col monitor | **P2** | F-003, F-050 / DAY-014 |
| T-11 | Filtri `from`/`to` su `/api/decisions`, `/api/signals`, `/api/trades` (oggi i parametri di data sono ignorati in silenzio) | **P2** | §12 |
| T-12 | Il generatore del dossier deve fallire rumorosamente; rigenerare 2026-08-28 e 2026-09-05 | **P2** | F-044 / DAY-015 |
| T-13 | Indagare perché `body_full` è NULL su tutte le righe: il modello vede 145 caratteri dove la configurazione ne prevede 600 | **P2** | DAY-005 |

## 16. Stato sistema

| Voce | Valore |
|---|---|
| **Ollama (produzione)** | **UP per l'intera sessione.** 80 risposte su 81 item per ciascuno dei due modelli (`glm-5.2:cloud`, `gpt-oss:20b-cloud`). Disponibilità **98,8%**. **0 ore di downtime.** Spesa 0,0907 $, 46.473 token input / 5.757 output, budget non esaurito |
| **Ollama (shadow)** | Degradato ma fuori dal percorso decisionale: `kimi-k2.6:cloud` 51/81 fallimenti (63,0%), `qwen3.5:cloud` 29/81 (35,8%), `error:RuntimeError` e `timeout` a 95 s |
| **FinBERT fallback rate** | **3,7%** dei segnali per etichetta (3/81) — di cui **1,2%** (1/81) per guasto reale di trasporto e 2,5% (2/81) per divergenza d'ensemble. Sulle **decisioni di ordine**: 0 su 5 ordini deriva da un segnale FinBERT. Sulle 26 righe `fallback_used=true` (32,1%), 25 hanno entrambe le risposte dei modelli a DB: sono filtro di confidenza, non fallback |
| **Circuit breaker** | Non scattato. `fallback_counters.consecutive_fallback` senza incrementi nella giornata |
| **Worker restart events** | **Non verificabili.** I log container del 2026-08-28 non esistono (F-027). Indizio indiretto: 4 finestre di `degradation: signal stale` (13:30-14:00, 17:16-17:30, 19:03-19:15, 19:31-19:55), compatibili sia con un riavvio sia con l'assenza di news nuove |
| **Persistenza cicli portfolio** | 24/24 cicli di mercato aperto persistiti, `portfolio_cycle_persist_failures` vuota |
| **Broker** | Alpaca **paper**, 92 snapshot regolari ogni 5 minuti da 13:30 a 20:00 senza buchi |
| **Database** | Nessun errore, nessun fallimento di persistenza. `audit_log`: 420 `SIGNAL_STALE_SKIP`, 4 `SIGNAL_DUPLICATE_SKIP`, 2 `INSERT trades` |
| **Alert emessi** | **0** (`mobile_events` vuota, `risk_reports.alerts = []`) |

---

*Report generato in sola lettura. Nessun file di codice modificato, nessun commit, nessun ordine
inviato, nessun worker avviato. Le anomalie sono state riportate anche in `docs/evidence/findings.json`.*
