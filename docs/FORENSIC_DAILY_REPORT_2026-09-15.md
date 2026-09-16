# Forensic Daily Report — 2026-09-15 (martedì)

Analisi read-only della seduta operativa del 2026-09-15. Timezone: **UTC**
(`src/workers/celery_app.py:55-56` → `timezone="UTC"`, `enable_utc=True`).
RTH: 13:30–20:00 UTC (EDT). Modalità broker: **paper**
(`ALPACA_BASE_URL=https://paper-api.alpaca.markets`), motore
`execution.engine=portfolio` (`config/trading.yaml:142`).

Periodo di sola osservazione attivo (`docs/evidence/OBSERVATION_CHARTER.md`,
scadenza 2026-09-28): nessuna taratura proposta. I ticket suggeriti in §15 sono
solo difetti di correttezza dell'evidenza.

---

## 1. Executive summary

La catena end-to-end ha funzionato: 1.532 articoli Benzinga + 1.978 GDELT
fetchati, 804 accodati, 211 scorati, 24 cicli di portafoglio, 4 ordini inviati,
4 riempiti, 0 rifiutati, 0 posizioni non riconciliate sui simboli tradati.
L'ensemble Ollama è stato **up tutto il giorno** (6 timeout su ~420 chiamate,
2 in RTH) e **FinBERT non è mai stato usato**: 0 righe in
`finbert_fallback_events`, 0 segnali `model_id='finbert'`.
Il difetto più rilevante trovato oggi è che il worker **dichiara comunque 72
"finbert_fallbacks"**: il contatore conta anche le letture a modello singolo, e
chi legge l'esito del task conclude un outage FinBERT che non c'è stato
[DAY-002]. Tre altri difetti nuovi: le righe `SKIP_FALLBACK` non entrano
nell'indice del worker controfattuale, quindi il costo del filtro #108 non è
misurabile per costruzione [DAY-003]; la chiave di deduplica di
`SKIP_PYRAMIDING` non contiene il giorno, e MRK — bloccato in 17 cicli su 24 —
non lascia **nessuna riga** il 09-15 [DAY-004]; l'API solleva
`psycopg2.pool.PoolError: trying to put unkeyed connection` nel teardown della
dipendenza, dopo aver già risposto 200 [DAY-005].
Economicamente la seduta è piatta: NAV 109.245,01 → 109.258,00 (**+12,99 $**,
+0,012%) contro SPY −0,438%, con esposizione 28,5%. Realizzato netto −33,31 $
(NFLX −48,72, PLTR +15,41); il resto è mark-to-market.
Nessun ordine duplicato, nessun ordine fuori orario, nessun ordine senza
segnale, nessun BUY piramidale, idempotenza per `signal_id` verificata
(`SIGNAL_DUPLICATE_SKIP` × 20).

## 2. Verdict

**OK con warning.**

Il processo è funzionalmente corretto sul percorso del denaro: ogni ordine è
tracciabile a un segnale, i guard hanno fatto quello che dichiarano, la
riconciliazione ordine→fill→posizione chiude. I warning sono tutti su
**osservabilità e misura**: quattro difetti nuovi che corrompono l'evidenza
raccolta (non le decisioni prese), più 22 ricorrenze di difetti già a ledger.
Non è "processo non affidabile": è un processo che decide bene e si racconta
male.

---

## 3. Timeline del 2026-09-15 (UTC)

| ora | componente | evento | fonte |
|---|---|---|---|
| 00:00–13:29 | news-stream (WS) | ingest 24/7 in coda; profondità da 26 a **248** articoli alle 13:00 | `news_queue_census` |
| 00:15–12:15 | sentiment-shadow | 13 cicli shadow off-session (Opzione C), 1–5 articoli l'uno | `worker-inference-…log` |
| 03:00:01 | performance | `run_reconcile_positions`: "Reconciled 0 trade fill(s)" | worker log |
| 06:17:10 | ensemble | timeout Ollama 90s su `glm-5.2:cloud` (fuori RTH) | worker-inference log |
| 07:00:04 | regime | **ERROR** fetch macro FRED VIXCLS → HTTP 500 | worker-inference log |
| 10:17 / 10:24 | ensemble | 2 timeout Ollama su `gpt-oss:20b-cloud` (fuori RTH) | worker-inference log |
| **13:30:01** | beat/monitor | apertura RTH. `mobile_events` apre **CRITICAL "Ciclo di portafoglio in ritardo"** | `mobile_events` |
| 13:30:01 | beat/monitor | WARNING "Segnali sentiment in ritardo" (chiuso 13:34) | `mobile_events` |
| 13:33:03 | sentiment | primo ciclo di scoring: 3 processati (1 ensemble, 2 single-model) | `ensemble_cycle_health` id 412 |
| 13:33:20 | news_log | prima riga persistita del giorno (alpaca_benzinga) | `news_log` |
| 14:07:00 | portfolio | **primo ciclo di portafoglio**, 37 min dopo l'apertura. Persi i beat 13:37 e 13:52 | `portfolio_cycles` 1491 |
| 14:07:04 | S4 | guard P0-05 blocca BUY su LLY, MRK, NFLX | worker log |
| 14:07:04 | S4 | persistite 2 righe `SKIP_PYRAMIDING` (NFLX, LLY). **MRK: nessuna riga** | `execution_decisions` |
| 14:07:06 | alert | **2 alert Telegram #161 respinti 400 Bad Request** | worker log |
| 14:07:03 | S4 | 11 righe `SKIP_FALLBACK` (AMD, AVGO, BP, C, GOOGL, MS, QQQ, SOXX, TSM, XLE, XOM) | `execution_decisions` |
| 14:08:00 | monitor | l'incidente CRITICAL delle 13:30 si auto-risolve, senza consegna | `mobile_events` |
| 14:12:00 | reconcile | `run_reconcile_fills_intraday`: 19 lifecycle, 5 P0, 10 P1 | worker log |
| 14:14:51 | ingest | prima (e quasi unica) riga GDELT del giorno | `news_log` |
| 14:35:12 | ensemble | timeout Ollama `gpt-oss` (1° in RTH) | worker-inference log |
| 14:52:05 | alert | 3° alert Telegram respinto 400 | worker log |
| 15:54:56 | sentiment | **segnale BA +0,514** (ensemble, conf 0,775, std 0,141) — news ordine 150 jet Turkish Airlines | `sentiment_signals` 10993 |
| 15:55:30 | sentiment | segnale NFLX **−0,171** (ensemble, conf 0,60) | `sentiment_signals` 10994 |
| 16:01:07 | sentiment | **segnale PLTR +0,343** (ensemble, conf 0,70) — nota UBS "best AI enabler" | `sentiment_signals` 10998 |
| **16:07:00** | portfolio | ciclo 1499: velocity 7/34 aggiustati, gate scarta 30/34. **4 ordini** | `portfolio_cycles` 1499 |
| 16:07:05,7 | broker | **BUY BA** — fill 210,30, qty 6,9038, nozionale 1.451,87 | ordine `3f601848…` |
| 16:07:05,9 | broker | **BUY PLTR** — fill 172,87, qty 8,3986, nozionale 1.451,87 | ordine `88aa3968…` |
| 16:07:06,2 | broker | cancellato 1 stop protettivo NFLX prima della SELL | worker log |
| 16:07:06,3 | broker | **SELL NFLX** (chiusura totale) — fill 77,88, qty 17,9503 | ordine `f633bf5c…` |
| 16:07:06,7 | broker | stop protettivo BA creato per **4** azioni su 6,9038 | ordine `a2cd9d3a…` |
| 16:07:06,8 | risk | #161: 10/41 posizioni non proteggibili (qty<1); AMAT −29,7%, WDC −24,3% | worker log |
| 16:22:04 | S4 | `SIGNAL_DUPLICATE_SKIP` su BA e PLTR (idempotenza per signal_id) | worker log |
| 16:22:05 | broker | stop BA sostituito 4 → **6** azioni; creato stop PLTR **8** su 8,3986 | ordini `34164d04…`, `4d93de6f…` |
| 16:30:00 | feedback | ratchet S4 **congelato** (EWMA R −0,86, 4 perdite consecutive, P&L −240,57) → 4° alert Telegram respinto 400 | worker log |
| 16:42:24 | sentiment | NVDA **−0,490** (single-model): il più negativo del giorno, non tradabile (long-only) | `sentiment_signals` |
| 17:36:05 | sentiment | PLTR **0,000** (conf 0,20) — ensemble, entrambi i contributori sotto soglia | `sentiment_signals` 11044 |
| **17:52:00** | portfolio | ciclo 1506: **SELL PLTR** `below_entry_gate` (score +0,000, età 0,3h) | `execution_decisions` 26113 |
| 17:52:05 | broker | fill PLTR 174,80 → netto **+15,41 $**, 1h45 di holding | trade 1004 |
| 17:53:51 | sentiment | **AVGO +0,560** (single:gpt-oss, conf 0,80): il punteggio più alto della giornata | `sentiment_signals` |
| 19:37:03 | S4 | AVGO scartato `SKIP_FALLBACK` (#108). Nessun controfattuale calcolato | `execution_decisions` |
| 19:52:00 | portfolio | ultimo ciclo (24° su 26 attesi) | `portfolio_cycles` 1514 |
| 19:56:29 | sentiment | ultimo segnale del giorno | `sentiment_signals` |
| 20:00 | ingest | "Market closed — skipping Alpaca/GDELT ingestion" | worker log |
| **20:20:15** | ops | **restart del worker** (warm shutdown + ripartenza) — deploy della migrazione 076 | worker log |
| 21:00:00 | decay | **10 alert CRITICAL** (S1×3, S2×4, S4×3). Nessun canale | worker log |
| 22:00:00 | forward | forward-return worker: 1085 segnali, 1023 aggiornati, 0 errori | worker log |
| 22:30:01 | risk | risk report id 95: NAV 109.258,00, drawdown 1,24%, HHI 0,030, alerts 0 | `risk_reports` |
| 22:45:10 | counterfactual | 953 SKIP processati, 865 aggiornati, 0 errori | worker log |
| 22:50:00 | monitor | 4 incidenti mobile aperti e **risolti entro 1 secondo** | `mobile_events` |
| 22:55:00 | alert | alert stale-drop consegnato (**200 OK**): l'unico Telegram riuscito del giorno | worker log |

## 4. News ingest

### 4.1 Per fonte

| fonte | fetched | queued | duplicates | scartati no-ticker | scartati stale | parse fail | righe `news_log` | copertura oraria |
|---|---|---|---|---|---|---|---|---|
| alpaca_benzinga | 1.532 | 804 | **6.151** (4,0× fetched) | 0 | 407 | 0 | 202 | 13:33 → 19:56 |
| gdelt_gkg | 1.978 | 9 | 0 | **1.969** (99,5%) | 0 | 0 | 9 | 14:14 → 19:45 |

Fonte: `ingestion_stats_daily`, `news_log`. Una sola fonte news reale è attiva
(Benzinga via Alpaca); GDELT produce 9 righe su 1.978 articoli.

### 4.2 Qualità delle righe scorate (211)

| controllo | valore |
|---|---|
| ticker distinti | 65 su 96 di watchlist (**31 simboli a zero news**) |
| URL distinti | 107 → **fan-out**: 34 URL mappati su 2–8 ticker producono 107/211 righe (**50,7%**) |
| latenza published→fetched (Benzinga) | mediana **0,5 min**, media 14,7 min, max 1,9 h |
| timestamp futuri | 0 |
| campi mancanti (title/body/published_at/content_hash) | 0 |
| `transport` popolato | **0/211** — la migrazione 075 è stata applicata al live solo il 2026-09-16 10:20 |
| titoli con entità HTML non decodificate | **50/211 (23,7%)** |
| corpi con entità HTML non decodificate | **147/211 (69,7%)** |
| tag HTML residui nei corpi | 0 |
| `extraction_method` | `source_metadata` 202, `org_lookup` 9 |

### 4.3 Stale e buchi temporali

`stale_drop_metrics_daily` 2026-09-15 / alpaca_benzinga: **381 stale drop su 804
accodati = 47,4%**, contro `alert_threshold` 0,25 → `alert_required=true`.
Scomposizione: 244 già stale **al fetch**, 137 scaduti **fuori seduta**, 0 in
coda. L'alert è partito alle 22:55 e **è stato consegnato** (unico 200 OK del
giorno).

Buco temporale strutturale: la coda cresce da 26 (00:00) a **248** (13:00) e
viene drenata a 0 entro le 16:00. Il worker di streaming ingerisce 24/7 ma il
consumatore è schedulato `hour=14-21`.

### 4.4 Top news per impatto sul segnale

| simbolo | score | conf | std | modello | ora | esito |
|---|---|---|---|---|---|---|
| AVGO | **+0,560** | 0,80 | 0,000 | single:gpt-oss | 17:53 | `SKIP_FALLBACK`, nessun controfattuale |
| BA | +0,514 | 0,775 | 0,141 | ensemble | 15:54 | **BUY eseguito** (post-velocity 0,616) |
| NVDA | −0,490 | 0,70 | 0,000 | single:gpt-oss | 16:42 | non tradabile (long-only) |
| JPM | +0,447 | 0,790 | 0,035 | ensemble | 18:52 | sotto rank cutoff |
| PLTR | +0,420 | 0,70 | 0,000 | single:gpt-oss | 19:23 | `SKIP_FALLBACK` |
| NKE | −0,420 | 0,70 | 0,000 | ensemble | 17:22 | non tradabile; NKE ha chiuso −0,50% (segnale corretto) |
| XOM | +0,420 | 0,70 | 0,000 | ensemble | 18:07 | `SKIP_PYRAMIDING` |
| PLTR | +0,343 | 0,70 | 0,141 | ensemble | 16:01 | **BUY eseguito**, chiuso 1h45 dopo |

### 4.5 Problemi trovati — confidenza dell'analisi

Alta su volumi, fonti, latenza, fan-out ed entità HTML (misurati direttamente su
`news_log`/`ingestion_stats_daily`). Media su `duplicates` (il contatore è
additivo cross-run e non è verificabile indipendentemente, vedi [DAY-012]).
Nulla su `transport`: non misurato per costruzione il 09-15.

## 5. Performance modelli LLM

`llm_responses` per il 2026-09-15, 420 righe su 211 segnali.

| modello | richieste | risposte | timeout | refusal/invalid | `eligible=true` | polarity media | confidence media | materiality | novelty |
|---|---|---|---|---|---|---|---|---|---|
| `glm-5.2:cloud` | 213 | 210 | 3 (06:17, 16:43, 22:16) | 0 | 89 (42,4%) | +0,0568 | 0,3965 | 0,305 | 0,353 |
| `gpt-oss:20b-cloud` | 213 | 210 | 3 (10:17, 10:24, 14:35) | 0 | 89 (42,4%) | +0,0234 | **0,4860** | 0,363 | 0,458 |

Latenza: non strumentata per chiamata. Prossimazione dall'esito del task
(`run_sentiment_worker`): 6,5–107 s per ciclo, mediana ~11 s con 1 articolo,
~50–80 s con 6–8 articoli; nessun ciclo ha superato il timeout di 90 s per
modello se non nelle 6 occorrenze sopra.

### 5.1 Composizione dell'ensemble

| bucket | n | % | note |
|---|---|---|---|
| `ensemble:` (≥2 modelli) | 139 | 65,9% | di cui **50 con entrambi i contributori `eligible=false`** (retry #90 a floor 0) |
| `single:gpt-oss:20b-cloud` | 63 | 29,9% | un solo modello sopra `min_confidence` |
| `single:glm-5.2:cloud` | 9 | 4,3% | idem |
| `finbert` | **0** | 0% | **nessun fallback deterministico** |

`ensemble_cycle_health`: 106 cicli, 139 ensemble / 72 single / **0 finbert**,
aggregate 211. 29 cicli RTH su 103 sotto il 50% di ensemble pieno.

### 5.2 Disaccordo

| metrica | valore |
|---|---|
| segnali con polarity di **segno opposto** fra i due modelli | **16** |
| segnali con spread grezzo ≥ 0,50 | 6 |
| spread massimo | **0,65** (SPY: glm +0,15 vs gpt-oss −0,50) |
| segnali con `ensemble_std ≥ 0,40` (soglia del guard) | **0** |
| segnali con `ensemble_std = 0,000` **e** spread grezzo ≥ 0,30 | **13** |

### 5.3 Verifica funzionale

| domanda | risposta | evidenza |
|---|---|---|
| L'output LLM è validato prima del signal store? | **Parzialmente.** Schema Pydantic `LLMSentimentOutput` sì; nessuna validazione semantica (`risk_flags` registrati ma non gating, `ambiguous_entity` su 158 righe) | `src/llm/ensemble.py`, `llm_responses.risk_flags` |
| L'ensemble gestisce la varianza alta? | **No, non oggi.** La soglia 0,40 non è mai scattata; il filtro di eleggibilità gira **prima** del calcolo di divergenza e azzera `ensemble_std` proprio sui 13 casi di massimo disaccordo | `ensemble.py:292-301` |
| Le news duplicate pesano più volte? | **No** sul lato URL+ticker (`uq_news_log_url_ticker`), **sì** sul lato fan-out: lo stesso articolo genera fino a 8 righe scorate | `news_log` |
| La stessa news può generare segnali multipli? | Sì, uno per ticker. S4 ne consuma però uno solo per simbolo | §4.2 |
| La confidenza bassa riduce il peso? | Sì nel calcolo (`polarity × confidence`, peso `confidence × LOO-ICIR`), **no all'uscita**: un segnale a confidenza 0,20 ha liquidato PLTR | `sentiment.py`, [DAY-020] |
| I modelli sono chiamati offline? | **Sì.** Coda `inference`, concorrenza 1, worker dedicato; nessuna chiamata LLM nel ciclo di portafoglio | `celery_app.py`, worker log |
| Un'allucinazione LLM può entrare direttamente in decisione? | **Sì, per costruzione.** Non esiste supervisore né RAG di verifica: BA è stato comprato sul testo del modello. Il contrappeso è deterministico a valle (gate 0,30, guard, rank, cap), non a monte | `execution_decisions.reason` id 25387 |

## 6. Segnali finali per ticker

211 segnali, 65 simboli. Passaggio al gate (`feedback:entry_threshold:S4 = 0.30`,
congelato dalla carta):

| stadio | n | note |
|---|---|---|
| segnali generati | 211 | |
| `|score| ≥ 0,30` | 24 | 14 rialzisti, **10 ribassisti** |
| ribassisti sopra gate | 10 | **nessuno tradabile**: vincolo long-only |
| rialzisti sopra gate, **fallback** | 3 | scartati dal filtro #108 (AVGO, PLTR, …) |
| rialzisti sopra gate, ensemble | 11 | entrano nel ranking |
| bloccati da P0-05 (già a libro) | 8 distinti | NFLX, LLY, MRK, XLE×3, SPY, CVX, XOM, SHEL |
| **ordinati** | **2** | BA, PLTR |

Righe `execution_decisions` del giorno:

| decisione | n | simboli | con `signal_id` | con `order_id` |
|---|---|---|---|---|
| `OBSERVE_LATE_ENTRY` | 1.505 | 75 | 1.505 | 0 |
| `SKIP_THRESHOLD` | 704 | 54 | 704 | 0 |
| `SHADOW_LATE_ENTRY` | 234 | 28 | 234 | 0 |
| `SKIP_FALLBACK` | 30 | 23 | 30 | 0 |
| `SKIP_PYRAMIDING` | 9 | 7 | 9 | 0 |
| `BUY` | 2 | BA, PLTR | 2 | 2 |
| `SELL` | 2 | NFLX, PLTR | **0** | 2 |

## 7. Ordini generati ed eseguiti

| # | ts decisione | ts submit | ts fill | strategia | ticker | azione | qty | prezzo atteso | fill | stato | rationale | segnale | risk check |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 16:07:00,61 | 16:07:05,74 | 16:07:06,52 | S4 | BA | BUY | 6,903757 | ~210,4 | **210,30** | filled | sentiment +0,616 post-velocity (grezzo +0,514), peso 2,0% | 10993 | gate 0,30 ✓, P0-05 ✓, regime ×0,7 ✓, cap ✓ |
| 2 | 16:07:00,61 | 16:07:05,91 | 16:07:06,61 | S4 | PLTR | BUY | 8,398565 | ~173,4 | **172,87** | filled | sentiment +0,343, peso 2,0% | 10998 | idem |
| 3 | 16:07:00,61 | 16:07:06,30 | 16:07:06,74 | S4 | NFLX | SELL (close) | 17,950341 | ~77,9 | **77,88** | filled | `below_entry_gate`, score −0,171 | (10994, non linkato) | stop cancellato prima ✓ |
| 4 | 17:52:00,60 | 17:52:04,94 | 17:52:05,32 | S4 | PLTR | SELL (close) | 8,398565 | ~174,8 | **174,80** | filled | `below_entry_gate`, score +0,000 | (11044, non linkato) | — |
| S1 | 16:07:06,78 | 16:07:06,7 | — | protettivo | BA | SELL stop | **4** | — | — | **canceled** | stop su parte intera, posizione non ancora aggiornata | — | qty<posizione |
| S2 | 16:22:05,37 | 16:22:05,4 | — | protettivo | BA | SELL stop | **6** | — | — | **new** (ancora aperto) | sostituisce S1 | — | copre 6 su 6,9038 |
| S3 | 16:22:05,52 | 16:22:05,5 | — | protettivo | PLTR | SELL stop | **8** | — | — | canceled (chiusura 17:52) | — | — | copriva 8 su 8,3986 |

Slippage: `trades.slippage_est` è una copia esatta di `cost_usd` su entrambi i
trade chiusi (0,79645 e 0,79989) → la qualità di esecuzione **non è misurata**.
Slippage reale stimabile dai bar 15 min: BA fill 210,30 contro barra 16:00
210,71 (favorevole −19 bp), PLTR 172,87 contro 173,365 (favorevole −29 bp),
NFLX 77,88 contro 77,63 (favorevole +32 bp). Nessuna esecuzione anomala.

## 8. PnL / rendimento

### 8.1 Book

| voce | valore |
|---|---|
| NAV 2026-09-14 (EOD) | 109.245,01 $ |
| NAV 2026-09-15 (EOD) | **109.258,00 $** |
| variazione giorno | **+12,99 $ (+0,0119%)** |
| SPY 09-14 → 09-15 | 760,755 → 757,42 = **−0,438%** |
| esposizione media | 28,48% |
| drawdown combinato | 1,24% |
| HHI | 0,030 |

Con beta 1 e 28,5% di esposizione, il book avrebbe dovuto perdere ~−0,125%: ha
fatto +0,012%. Differenza ~+14 bp. Nota: l'attribuzione beta=1 è una
supposizione, non una misura — il fetch del benchmark SPY fallisce da giorni
([DAY-011]).

### 8.2 Realizzato (trade chiusi il 09-15)

| trade | simbolo | aperto | entry | uscita | exit | qty | lordo | costi | **netto** | causa uscita | strategia |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1002 | NFLX | 2026-09-14 19:07 | 80,55 | 2026-09-15 16:07 | 77,88 | 17,950341 | −47,93 | 0,796 | **−48,72** | `portfolio_sell` / `below_entry_gate` | S4 |
| 1004 | PLTR | 2026-09-15 16:07 | 172,87 | 2026-09-15 17:52 | 174,80 | 8,398565 | +16,21 | 0,800 | **+15,41** | `hold_minimum_expiry` / `below_entry_gate` | S4 |
| | | | | | | **totale** | **−31,72** | **1,60** | **−33,31** | | |

- PnL da posizioni aperte **prima** del 09-15: −48,72 $ (NFLX).
- PnL da posizioni aperte **il** 09-15: +15,41 $ realizzati (PLTR) + −4,73 $ non realizzati a fine seduta (BA: entry 210,30, chiusura 209,615 × 6,9038).
- PnL non realizzato totale (delta implicito): +12,99 − (−33,31) = **+46,30 $**.
- Per strategia: **100% S4** sul realizzato. S1 non ha ribilanciato (`rebalance gate closed` in tutti e 24 i cicli). S2 non ha mai tradato.
- Commissioni Alpaca paper: 0. Il campo `cost_usd` è il modello interno
  (`cost-model:ccbc49f72a08ec5e`), non un addebito reale.

### 8.3 Cosa manca

Il PnL **per strategia** oltre S4 non è calcolabile: nessun trade S1/S2 chiuso.
Il PnL **non realizzato per ticker al 09-15 EOD** non è ricostruibile dal DB —
`risk_reports` salva solo il NAV aggregato e `/api/positions` restituisce il
mark **corrente** (09-16), non quello del 09-15. Query che servirebbe:
`SELECT symbol, qty, close FROM <snapshot posizioni EOD>` — la tabella non
esiste. `portfolio_monitor_snapshots` non è popolata per il 09-15.

## 9. Correttezza buy/sell

| controllo | esito | evidenza |
|---|---|---|
| BUY solo quando consentito | ✅ | entrambi ≥ gate 0,30 post-velocity, ensemble non-fallback, ema_pass=true, regime ×0,7 |
| SELL/exit corretti | ✅ | entrambe `below_entry_gate` su segnale fresco (età 0,2h e 0,3h < max 4h) |
| Stop-loss rispettati | ⚠️ | nessuno scattato; **10/41 posizioni non proteggibili** (qty<1), stop BA copre 6 su 6,9038 |
| Signal flip rispettato | ✅ | NFLX +0,322 (09-14) → −0,171 (09-15) → chiusa |
| Max holding days | ❌ | CSCO 21,7 gg, XLE 15,7, BP/GOOGL/PFE 14,9 contro orizzonte di trial D+2 |
| Rebalance band | ✅ | S1 `rebalance gate closed` 24/24 cicli |
| Ordini duplicati | ✅ nessuno | `SIGNAL_DUPLICATE_SKIP` × 20 (BA 15, PLTR 5) |
| Ordini contrari ravvicinati | ⚠️ | PLTR BUY 16:07 → SELL 17:52 (1h45), rationale presente e coerente |
| Roundtrip < 30 min | ✅ nessuno | minimo 1h45 |
| Pyramiding (BUY×3 senza SELL) | ✅ nessuno | guard P0-05 sparato 57 volte |
| SELL con sentiment positivo (A5) | ✅ nessuno | NFLX −0,171, PLTR +0,000 |
| Ordini su ticker non consentiti | ✅ | BA e PLTR in watchlist; 12–8 skip `not_tradable` per ciclo |
| Ordini fuori orario | ✅ nessuno | tutti fra 16:07 e 17:52 UTC |
| Trade su dati stale | ✅ | 5/36 segnali scartati per età > 4h al ciclo 16:07 |
| Trade su output LLM non valido | ✅ | 0 parse fail |
| Circuit breaker | ✅ inattivo a ragione | `consecutive_fallback = 0`, reset alle 19:56; nessun fallback FinBERT |
| Strategia disabilitata | ✅ | `execution.engine=portfolio`, worker legacy inattivo in tutti i cicli |
| Paper/live coerente | ✅ | `paper-api.alpaca.markets` |
| Idempotenza retry Celery | ✅ | per `signal_id`, cross-ciclo via Redis |
| Riconciliazione ordini/fill/posizioni | ⚠️ | 40 trade aperti = 40 posizioni Alpaca; **1 disallineamento: UNH** |

Avvertenza `exit_mechanism` (#184): le due righe SELL del 09-15 portano
`exit_mechanism = 'below_entry_gate'`, che è un'etichetta **osservata**
(post-fix), non dedotta dall'età del segnale. Nessuna riga pre-fix è stata
conteggiata in questo report.

## 10. Anomalie trovate

### [DAY-001] [F-005] Quattro alert Telegram persi con 400 Bad Request; la causa è un `<` non escapato nel messaggio #161

* Tipo: Bug
* Area: Ops
* Evidenza:
  * file/log/tabella: `logs/containers/worker-2026-09-15.log`; `src/portfolio/unprotected_positions.py:137`; `src/notifications/telegram.py:79`
  * timestamp: 14:07:06,448 · 14:07:06,613 · 14:52:05,792 · 16:30:00,222 UTC
  * snippet: `TelegramNotifier: Failed to send alert: Client error '400 Bad Request'` — 4 su 5 invii del giorno. L'unico 200 OK è l'alert stale-drop delle 22:55. Il testo generato è `"sub-1-share position (qty < 1) — a broker stop is impossible here (#161)"` e il notifier invia con `parse_mode="HTML"` (default a `telegram.py:79`): la sequenza `< 1)` è interpretata come apertura di tag e Telegram rifiuta il messaggio.
* Descrizione: gli alert #161 su posizioni scoperte (AMAT −29,7%, WDC −24,3%, NOK −15,4%) e il ratchet loss-feedback S4 congelato non raggiungono nessun canale. Il quarto (16:30) usa sintassi Markdown (`*bold*`, `\_`) sotto `parse_mode="HTML"`: stessa famiglia di difetto, conferma media.
* Impatto: le allerte di rischio più importanti della giornata sono invisibili. Il canale mobile è l'altra metà del guasto: `monitor_devices = 0`, `mobile_notification_deliveries = 0`.
* Severità: High
* Confidenza: High (per i tre #161) / Medium (per il ratchet)
* Azione consigliata: escapare il testo secondo il `parse_mode` effettivo, o costruire i messaggi con un formatter che conosce il modo. Non è taratura.
* Test/monitor consigliato: test che invia ogni template di alert a un finto endpoint Telegram con validatore HTML; contatore `telegram_send_failures` con alert su ≥1.

### [DAY-002] [F-078] Il worker sentiment dichiara 72 "finbert_fallbacks" mentre FinBERT non è mai stato invocato

* Tipo: Bug
* Area: LLM
* Evidenza:
  * file/log/tabella: `src/workers/sentiment.py:1491` e `:1538-1546`; `finbert_fallback_events`; `ensemble_cycle_health`; `logs/containers/worker-inference-2026-09-15.log`
  * timestamp: tutta la seduta
  * snippet/query: `fallback_count = sum(1 for r in results if r.fallback_used)` → ritornato come `"finbert_fallbacks": fallback_count`. Ma `r.fallback_used` è `True` anche per le letture `single:<model>` (`_label_from_model_count`, `sentiment.py:346-356`). Verifica: `SELECT COUNT(*) FROM finbert_fallback_events WHERE created_at::date='2026-09-15'` → **0**; `SELECT COUNT(*) FROM sentiment_signals WHERE model_id='finbert' AND created_at::date='2026-09-15'` → **0**; `SELECT SUM(n_finbert), SUM(n_single) FROM ensemble_cycle_health WHERE cycle_started_at::date='2026-09-15'` → **0, 72**. Gli esiti dei task riportano `'finbert_fallbacks': 2/3/1/…` per 72 in totale.
* Descrizione: il contatore esposto nell'esito del task Celery mescola due eventi opposti — outage dell'ensemble (FinBERT) e degradazione a modello singolo — sotto il nome del primo. Il commento a `sentiment.py:1502-1506` descrive tre bucket disgiunti "che rispecchiano il dict di ritorno del worker", ma il dict di ritorno non ha un bucket single-model: `ensemble_success = len(results) − fallback_count` sottrae anche i single. La tabella `ensemble_cycle_health` (#427) è invece corretta.
* Impatto: chiunque legga i log dei task o la telemetria Celery per stimare il tasso di fallback FinBERT — incluso ogni report forense che non interroghi il DB — sbaglia di 72 su 72. La riga "FinBERT fallback rate" in §16 sarebbe stata 34,1% invece di 0%. È un difetto di **correttezza dell'evidenza**: passa il test di esenzione della carta.
* Severità: Medium
* Confidenza: High
* Azione consigliata: separare il dict di ritorno in `ensemble_success` / `single_model` / `finbert_fallbacks`, allineandolo ai tre bucket già calcolati venti righe più sopra per `record_ensemble_cycle_health`.
* Test/monitor consigliato: test che, con un ensemble in cui un modello sta sotto `min_confidence`, asserisce `finbert_fallbacks == 0` e `single_model == 1`; invariante `finbert_fallbacks == COUNT(finbert_fallback_events)` del giorno.

### [DAY-003] [F-079] `SKIP_FALLBACK` è escluso dall'indice del worker controfattuale: il costo del filtro #108 non è misurabile

* Tipo: Bug
* Area: Signal
* Evidenza:
  * file/log/tabella: `execution_decisions`; indice `idx_execution_decisions_counterfactual`
  * timestamp: 22:45:10 UTC (ciclo del worker controfattuale)
  * snippet/query: l'indice copre `decision IN ('SKIP_THRESHOLD','SKIP_EMA','SKIP_CAP','SKIP_PYRAMIDING','SHADOW_LATE_ENTRY')`. Risultato: `SELECT decision, COUNT(*), COUNT(counterfactual_return_1h) FROM execution_decisions WHERE tick_time::date='2026-09-15' GROUP BY 1` → `SKIP_THRESHOLD 704/648`, `SKIP_PYRAMIDING 9/9`, `SHADOW_LATE_ENTRY 234/208`, **`SKIP_FALLBACK 30/0`**.
* Descrizione: 30 segnali scartati perché a modello singolo (fra cui **AVGO +0,560, il punteggio più alto della giornata**, e PLTR +0,420) non ricevono mai un controfattuale. Il filtro #108 è una politica deliberata (post-SPCX), ma il suo costo non è stato misurato nemmeno una volta.
* Impatto: la domanda "quanto costa escludere i segnali a modello singolo?" non è rispondibile dal ledger. Con 72 letture single-model al giorno (34% del totale) è il ramo di scarto più grande dopo il gate di soglia.
* Severità: Medium
* Confidenza: High
* Azione consigliata: aggiungere `SKIP_FALLBACK` all'indice e alla query del worker controfattuale. Nessuna modifica al comportamento di trading.
* Test/monitor consigliato: asserzione che ogni `decision LIKE 'SKIP%'` con `signal_id` non nullo riceva un `counterfactual_computed_at` entro 24h, o una `counterfactual_skip_reason` esplicita.

### [DAY-004] [F-080] La chiave di deduplica di `SKIP_PYRAMIDING` non contiene il giorno: MRK bloccato 17 volte, zero righe

* Tipo: Bug
* Area: Signal
* Evidenza:
  * file/log/tabella: `src/workers/portfolio_scheduler.py:3904-3919` (`_pyramiding_block_key`) e `:4185-4187`; Redis `s4:logged_pyramiding_blocks`; `execution_decisions`
  * timestamp: 17 cicli fra 14:07 e 19:52 UTC
  * snippet/query: `if signal_id is not None: return f"{symbol}|{signal_id}"` — il parametro `giorno` è usato **solo** nel ramo senza `signal_id`. `redis-cli SISMEMBER s4:logged_pyramiding_blocks "MRK|10882"` → **1**, scritto il 2026-09-14 alle 19:52:30. Il segnale 10882 (MRK, +0,307, generato 2026-09-14 19:48) è stato tenuto vivo dal ramo FIX-D per tutta la seduta del 09-15. `SELECT decision, COUNT(*) FROM execution_decisions WHERE symbol='MRK' AND tick_time::date='2026-09-15' GROUP BY 1` → solo `OBSERVE_LATE_ENTRY 20` e `SHADOW_LATE_ENTRY 4`. Nel log: 17 righe `P0-05 pyramiding guard: skipping BUY for MRK`.
* Descrizione: la deduplica per segnale è deliberata (evitare 24 righe identiche al giorno), ma un segnale preservato da FIX-D sopravvive per **giorni**, e la riga viene scritta solo il primo. Il 09-15 il guard ha bloccato 8 simboli distinti e ne ha persistiti 7: MRK è invisibile. È esattamente la confusione "bloccato di proposito" vs "mai valutato" che il commento a `_record_pyramiding_blocks` dice di voler eliminare.
* Impatto: qualunque conteggio giornaliero dei blocchi P0-05 letto dal DB sottostima; la sottostima cresce proprio sui segnali più longevi, cioè quelli preservati per posizione aperta. Nel log il guard è sparato **57 volte** (MRK 17, XLE 10, XOM 7, NFLX 7, CVX 7, SHEL 6, SPY 2, LLY 1) contro 9 righe persistite.
* Severità: Medium
* Confidenza: High
* Azione consigliata: includere il giorno nella chiave anche quando `signal_id` esiste (`f"{symbol}|{signal_id}|{giorno}"`), oppure dare un TTL di 24h alla voce Redis. Una riga al giorno per segnale, non una sola per sempre.
* Test/monitor consigliato: test che, dato lo stesso `signal_id` bloccato in due giorni consecutivi, asserisce due righe `SKIP_PYRAMIDING`; riconciliazione giornaliera `COUNT(log "pyramiding guard") vs COUNT(SKIP_PYRAMIDING)` per simbolo.

### [DAY-005] [F-081] L'API solleva `PoolError: trying to put unkeyed connection` nel teardown, dopo aver già risposto 200

* Tipo: Bug
* Area: Ops
* Evidenza:
  * file/log/tabella: `logs/containers/api-2026-09-15.log` righe 4117-4191 e 4197-4271; `src/api/deps.py:50`; `src/store/pg_store.py:253`
  * timestamp: non databile (uvicorn non stampa timestamp); 2 occorrenze il 09-15, 2 il 09-14, **zero** dal 09-04 al 09-13
  * snippet: le richieste immediatamente precedenti sono `GET /api/trades/summary?days=30 → 200 OK` e `GET /api/performance/daily?from_date=2026-09-08&to_date=2026-09-14 → 200 OK`. Traccia: `deps.py:50 pg.close()` → `pg_store.py:264` → `pg_store.py:253 _get_pool().putconn(conn)` → `psycopg2/pool.py:103 raise PoolError("trying to put unkeyed connection")`.
* Descrizione: `psycopg2` solleva questo errore quando `putconn` riceve una connessione che il pool non ha più in `_rused` — cioè un doppio rilascio o una collisione di `id()`. Il pool è un globale creato una sola volta (`pg_store.py:105-118`, `minconn=2/maxconn=20`), mai resettato, quindi non è una ricreazione del pool. L'eccezione avviene **dopo** l'invio della risposta: il client vede 200, nessun alert scatta, il difetto vive solo nel log.
* Impatto: non ho potuto stabilire se la connessione resti fuori dal pool (perdita) o se sia già rientrata (solo rumore). Nel primo caso il pool si degrada fino al ramo di fallback `psycopg2.connect` diretto (`pg_store.py:220-226`), che apre connessioni non pooled. Al momento dell'analisi `pg_stat_activity` mostra 6 connessioni (1 active, 5 idle) — nessuna saturazione osservabile. Comparsa nuova: 4 occorrenze in 2 giorni dopo 10 giorni puliti.
* Severità: Medium
* Confidenza: Medium
* Azione consigliata: rendere `PostgreSQLStore.close()` idempotente e difendersi dal doppio rilascio (`putconn` in `try/except PoolError` con log esplicito del chiamante). Prima, però, individuare il secondo rilascio: la firma è comparsa fra il 09-13 e il 09-14.
* Test/monitor consigliato: test che chiama `close()` due volte su uno store pooled e asserisce nessuna eccezione; gauge sulla dimensione del pool e alert su `PoolError` nei log API.

### [DAY-006] [F-054] Tredici segnali con `ensemble_std` a 0,000 esatto mentre i due modelli distano fino a 0,65

* Tipo: Bug
* Area: LLM
* Evidenza:
  * file/log/tabella: `sentiment_signals` + `llm_responses`; `src/llm/ensemble.py:292-301`
  * timestamp: tutta la seduta
  * snippet/query: join su `signal_id` con `ensemble_std = 0` e spread grezzo ≥ 0,30 → 13 righe. Le peggiori: SPY (glm +0,15 vs gpt-oss −0,50, spread **0,65**), DIS (+0,30 vs −0,30, 0,60), INTC (+0,15 vs −0,40, 0,55), NVDA (−0,15 vs −0,70, 0,55), **AVGO (+0,20 vs +0,70, 0,50, score finale +0,560)**.
* Descrizione: lo Step 1 (filtro di eleggibilità su `min_confidence`) precede lo Step 3 (calcolo della divergenza), e lo Step 2 dichiara "se un solo modello è eleggibile, usalo (nessuna divergenza possibile)". Lo zero non significa "concordano": significa "non ho guardato".
* Impatto: il guard di divergenza (soglia 0,40) **non è mai scattato** in tutta la seduta — 0 segnali con `ensemble_std ≥ 0,40` — proprio perché i 13 casi di massimo disaccordo sono usciti dal calcolo. Nessuno dei 13 ha però generato un ordine: tutti `SKIP_FALLBACK` o sotto rank. Costo nullo oggi, difetto di registrazione.
* Severità: Medium
* Confidenza: High
* Azione consigliata: calcolare e persistere `ensemble_std` su **tutte** le polarity grezze, prima del filtro di eleggibilità, e tenere separato il valore usato dal guard.
* Test/monitor consigliato: invariante "se `llm_responses` ha ≥2 righe per un segnale, `ensemble_std` è la deviazione delle loro polarity".

### [DAY-007] [F-010] Cinquanta segnali etichettati `ensemble:` hanno entrambi i contributori marcati `eligible=false`; il modello col peso maggiore è anche il più escluso

* Tipo: Bug
* Area: LLM
* Evidenza:
  * file/log/tabella: `llm_responses`; `src/workers/sentiment.py:818-823`; `src/store/pg_store.py:2897`; Redis `ensemble:weights:current`
  * timestamp: tutta la seduta
  * snippet/query: per segnale, conteggio `eligible`: `fallback=f, ne=0, nt=2` → **50 righe**; `fallback=f, ne=2, nt=2` → 89. Quei 50 sono i segnali salvati dal retry #90 a floor 0 — hanno contribuito davvero ma risultano non eleggibili. Complessivamente 89/210 eleggibili per modello (42,4%).
  * Novità del giorno: `ensemble:weights:current` = `{glm-5.2: 0,70, gpt-oss: 0,30}` mentre delle 72 letture a modello singolo **63 sono `single:gpt-oss`** e solo 9 `single:glm-5.2`. Il modello che porta il 70% del peso LOO-ICIR è quello che cade sotto il floor di confidenza 7 volte su 8 (confidence media glm 0,3965 contro gpt-oss 0,4860).
* Descrizione: il flag `eligible` è calcolato sul floor di default e forzato a `false` sul fallback, quindi non descrive chi ha effettivamente contribuito. In più il ribilanciamento dei pesi e il filtro di eleggibilità non si parlano: il peso configurato e il peso effettivo divergono in modo sistematico.
* Impatto: ogni analisi LOO-ICIR o di attribuzione per modello che legga `eligible` lavora su un campione sbagliato, e con segno prevedibile — sottopesa proprio il modello a cui il ribilanciamento ha dato più peso.
* Severità: Medium
* Confidenza: High
* Azione consigliata: persistere il floor effettivamente applicato per segnale e marcare `eligible` rispetto a quello.
* Test/monitor consigliato: invariante "un segnale `ensemble:` con N contributori ha N righe `eligible=true`"; report settimanale peso configurato vs quota di contributi effettivi.

### [DAY-008] [F-062] Dieci alert CRITICAL del decay monitor senza alcun canale

* Tipo: Rischio
* Area: Ops
* Evidenza:
  * file/log/tabella: `logs/containers/worker-2026-09-15.log`; `mobile_notification_deliveries`; `monitor_devices`
  * timestamp: 21:00:00,023–037 UTC
  * snippet: `DECAY CRITICAL [S1]: IC dropped 280% from 0.035 to -0.063` … 10 righe, poi `Decay monitor complete: 3 strategies, 10 total alerts` e `Task … succeeded`.
* Descrizione: solo `log.critical`. `monitor_devices = 0`, `mobile_notification_deliveries = 0` dal 09-15 in poi, Telegram in errore 400 su 4 invii su 5.
* Impatto: il segnale più forte del sistema ("tutte e tre le strategie sono in decadimento critico") non raggiunge nessuno.
* Severità: High
* Confidenza: High
* Azione consigliata: instradare gli alert CRITICAL su un canale con conferma di consegna e fallimento rumoroso.
* Test/monitor consigliato: contatore "alert CRITICAL emessi" vs "alert consegnati" con allerta a divergenza > 0.

### [DAY-009] [F-004] Il decay monitor confronta metriche globali di pipeline contro tre baseline distinte, inclusa S2 mai tradata

* Tipo: Bug
* Area: PnL
* Evidenza:
  * file/log/tabella: `logs/containers/worker-2026-09-15.log`; `portfolio_cycles.strategies_run`
  * timestamp: 21:00:00 UTC
  * snippet: le tre strategie ricevono lo **stesso** IC (−0,063) e lo **stesso** hit rate (33,2%), confrontati con baseline 0,035 / 0,042 / 0,028 e 54,0% / 56,0% / 52,0%. Quattro dei 10 CRITICAL sono su **S2**, che non compare in `strategies_run` di nessuno dei 24 cicli (`["S1","S4"]` in tutti).
* Descrizione: la metrica misurata non è per strategia; la baseline sì. Il confronto è privo di significato.
* Impatto: 10 alert CRITICAL al giorno che non identificano alcuna strategia in particolare. Assuefazione garantita.
* Severità: Medium
* Confidenza: High
* Azione consigliata: calcolare IC/hit-rate/Sharpe per strategia dai trade attribuiti, o sospendere il confronto per le strategie senza trade.
* Test/monitor consigliato: asserzione che una strategia con zero trade nel periodo non produca alert di decay.

### [DAY-010] [F-021] Le finestre beat sono in ora UTC fissa: persi i primi 37 minuti di seduta, 24 cicli su 26

* Tipo: Bug
* Area: Ops
* Evidenza:
  * file/log/tabella: `portfolio_cycles`; `mobile_events`
  * timestamp: apertura RTH 13:30:00 UTC; primo ciclo **14:07:00,717**
  * snippet/query: `SELECT MIN(timestamp), COUNT(*) FROM portfolio_cycles WHERE timestamp::date='2026-09-15'` → `14:07:00.717300`, **24**. `mobile_events`: incidente **CRITICAL** `Ciclo di portafoglio in ritardo` aperto alle 13:30:01,016 e auto-risolto alle 14:08:00,991.
* Descrizione: il beat è schedulato `hour=14-21` in UTC fisso; in EDT l'apertura è alle 13:30 UTC. Persi i cicli delle 13:37 e 13:52.
* Impatto: 37 minuti di seduta senza valutazione, proprio la finestra di maggiore dispersione. Il sistema **rileva** il ritardo e lo chiude da solo, senza che nessuno venga avvisato (0 device, 0 consegne).
* Severità: Medium
* Confidenza: High
* Azione consigliata: derivare le finestre beat dal calendario Alpaca invece che da ore UTC fisse.
* Test/monitor consigliato: asserzione "il primo ciclo del giorno cade entro 10 minuti dall'apertura restituita da `GetCalendarRequest`".

### [DAY-011] [F-016] Il fetch del benchmark SPY fallisce 84 volte, a WARNING, senza alcun alert

* Tipo: Bug
* Area: Data
* Evidenza:
  * file/log/tabella: `logs/containers/worker-2026-09-15.log`
  * timestamp: 84 occorrenze nella seduta
  * snippet: `SPY benchmark fetch failed: {"message":"subscription does not permit querying recent SIP data"}`
* Descrizione: il piano dati Alpaca non include il SIP recente. Il fallimento è permanente e silenzioso (WARNING).
* Impatto: ogni attribuzione beta del dossier ricade su beta=1 per supposizione. Il confronto book-vs-benchmark di §8.1 è stato fatto in questo report **a mano** (feed IEX), non dal sistema.
* Severità: Medium
* Confidenza: High
* Azione consigliata: usare il feed IEX per il benchmark (funziona: l'ho verificato) o dichiarare l'indisponibilità come `NO_BENCHMARK` invece di degradare in silenzio.
* Test/monitor consigliato: alert se il benchmark manca per più di 1 seduta.

### [DAY-012] [F-007] `duplicates` (6.151) supera di 4 volte `fetched` (1.532) sullo stesso giorno per Benzinga

* Tipo: Anomalia
* Area: News
* Evidenza:
  * file/log/tabella: `ingestion_stats_daily`
  * timestamp: aggiornato 21:39:53 UTC
  * snippet/query: `2026-09-15 | alpaca_benzinga | fetched 1532 | queued 804 | duplicates 6151 | discarded_stale 407 | parse_fail 0`. GDELT nello stesso giorno è coerente (1.978 fetched / 0 duplicates).
* Descrizione: i log per singolo run mostrano `{'fetched': 50, 'tickers_found': 197, 'queued': 5, 'duplicates': 201}`, cioè i duplicati sono contati **per coppia (articolo, ticker)** mentre `fetched` conta gli articoli. Il contatore è additivo cross-run e le due unità non sono confrontabili.
* Impatto: il "tasso di duplicazione" non è calcolabile da questa tabella. Solo Benzinga esplode, perché solo Benzinga ha il fan-out multi-ticker.
* Severità: Low
* Confidenza: High
* Azione consigliata: documentare l'unità di ciascun contatore o normalizzarli tutti su (articolo, ticker).
* Test/monitor consigliato: invariante `duplicates ≤ fetched × max_ticker_per_articolo`.

### [DAY-013] [F-019] Il 47,4% delle news accodate viene scartato per staleness; il 64% era già stale al fetch

* Tipo: Bug
* Area: News
* Evidenza:
  * file/log/tabella: `stale_drop_metrics_daily`
  * timestamp: misurato 22:55:00 UTC
  * snippet/query: `queued 804 | stale_drops 381 (47,4%) | already_stale_at_fetch 244 | went_stale_off_session 137 | went_stale_in_queue 0 | avg_fetch_latency_hours 3,03 | avg_queue_wait_hours 1,93 | alert_threshold 0,25 | alert_required true`
* Descrizione: quasi metà di ciò che entra in coda scade prima di essere scorato, e due terzi di quelli erano già vecchi quando Alpaca li ha consegnati. Nota: la mediana della latenza **sulle righe effettivamente persistite** è ottima (0,5 min) — la coda lunga è tutta negli articoli che non arrivano mai a `news_log`.
* Impatto: la finestra di entry-freshness (2,0h) consuma il grosso del materiale. L'alert è partito ed è stato consegnato (22:55, 200 OK): il rilevamento funziona.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna in periodo di osservazione (è taratura). Continuare a registrare la serie.
* Test/monitor consigliato: già presente e funzionante.

### [DAY-014] [F-069] La coda news cresce a 248 articoli fuori seduta; 137 scadono prima che il consumatore riparta

* Tipo: Bug
* Area: News
* Evidenza:
  * file/log/tabella: `news_queue_census`; `stale_drop_metrics_daily.went_stale_off_session`
  * timestamp: profondità 26 (00:00) → 110 (09:00) → **248 (13:00)** → 82 (14:00) → 0 (16:00)
  * snippet/query: `SELECT date_trunc('hour',sampled_at), MAX(queue_depth) FROM news_queue_census WHERE sampled_at::date='2026-09-15' GROUP BY 1`
* Descrizione: il worker WS ingerisce 24/7, il worker di scoring è gated su `market_closed` (85 skip nel log di inference). Il risultato è un picco di coda all'apertura, drenato in ~2,5 ore, con 137 articoli scaduti nel frattempo.
* Impatto: le news notturne — comprese quelle sui gap di apertura — arrivano allo scoring già fuori finestra.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna in periodo di osservazione. Collegata a #607/#608.
* Test/monitor consigliato: allerta su `queue_depth` all'apertura sopra una soglia assoluta.

### [DAY-015] [F-012] Metà delle righe scorate nasce da articoli fan-out multi-ticker

* Tipo: Rischio
* Area: News
* Evidenza:
  * file/log/tabella: `news_log`
  * timestamp: tutta la seduta
  * snippet/query: 107 URL distinti → 211 righe. Distribuzione ticker per URL: 1→104, 2→18, 3→6, 4→5, 5→1, 6→2, **8→2**. Le righe da URL multi-ticker sono 107/211 = **50,7%**. `llm_responses.risk_flags`: `ambiguous_entity` **158**, `low_source_quality` 148, `already_priced_in` 117, `rumor` 14. `event_type='macro'` su 133 righe di 420, di cui 70 con `directness='macro'`.
* Descrizione: un pezzo macro taggato su 8 simboli produce 8 segnali indipendenti che il ranker tratta come evidenza separata.
* Impatto: nessun ordine del 09-15 è nato da una riga fan-out (BA e PLTR vengono da articoli issuer-specific), ma il pool da cui il ranker sceglie è per metà di questa qualità. `risk_flags` è registrato e **mai usato come gate** (QX-01).
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna in periodo di osservazione (l'enforcement dei `risk_flags` è gated sul golden set).
* Test/monitor consigliato: quota giornaliera di righe fan-out nel pool dei segnali sopra gate.

### [DAY-016] [F-076] `sanitize_text` non decodifica le entità HTML: 69,7% dei corpi e 23,7% dei titoli le contengono

* Tipo: Bug
* Area: News
* Evidenza:
  * file/log/tabella: `news_log`; `src/text/sanitizer.py`
  * timestamp: tutta la seduta
  * snippet/query: `SELECT COUNT(*) FILTER (WHERE title ~ '&[a-zA-Z]+;' OR title ~ '&#[0-9]+;'), COUNT(*) FILTER (WHERE body_full ~ …) FROM news_log WHERE fetched_at::date='2026-09-15'` → **50 titoli, 147 corpi** su 211. Tag HTML residui: 0.
* Descrizione: il sanitizer rimuove i tag ma non fa `html.unescape`. Il modello riceve `&amp;`, `&#39;`, `&rsquo;` nel testo. Peggiora rispetto alla misura precedente (61,6%).
* Impatto: rumore nel prompt e, per il ramo FinBERT, consumo del budget di 512 caratteri. Nessun effetto dimostrato sul segnale.
* Severità: Low
* Confidenza: High
* Azione consigliata: aggiungere `html.unescape` in `sanitize_text`. Passa il test di esenzione solo se si accetta che cambia l'input del modello — da registrare come discontinuità nella carta.
* Test/monitor consigliato: asserzione che l'output di `sanitize_text` non contenga entità HTML.

### [DAY-017] [F-022] Dieci posizioni su 41 sono non proteggibili; lo stop di BA copre 6 azioni su 6,9038

* Tipo: Rischio
* Area: Risk
* Evidenza:
  * file/log/tabella: `logs/containers/worker-2026-09-15.log`; `/api/orders`
  * timestamp: 24 cicli, da 14:07:06 a 19:52
  * snippet: `#161: 10/41 held positions are unprotectable (qty < 1): ['AMAT','AMD','ASML','CAT','DELL','LLY','NOK','SPY','UNH','WDC']`; `#161: AMAT unprotected at -29.7% (qty 0.8571)`; `#161: WDC unprotected at -24.3% (qty 0.3347)`. Per BA: stop da **4** azioni alle 16:07:06 (cancellato), sostituito da **6** alle 16:22:05 su una posizione di 6,903757.
* Descrizione: Alpaca rifiuta stop su quantità frazionarie, quindi la copertura è il pavimento intero. Sotto 1 azione non esiste alcuno stop. In più lo stop nasce con la quantità sbagliata (4) al ciclo di apertura e viene corretto solo al ciclo successivo: **15 minuti di copertura parziale al 58%**.
* Impatto: AMAT (−29,7%) e WDC (−24,3%) violano `d_hard` senza alcun ordine di protezione, in tutti e 24 i cicli. Su BA la finestra scoperta è breve ma sistematica a ogni nuovo ingresso.
* Severità: High
* Confidenza: High
* Azione consigliata: non è taratura ma cambio di comportamento — fuori dalla finestra di osservazione. Nel frattempo, alzare il livello dell'alert: oggi è un WARNING nei log e un Telegram respinto ([DAY-001]).
* Test/monitor consigliato: monitor "nozionale scoperto oltre `d_hard`" con consegna verificata.

### [DAY-018] [F-031] Il guard anti-pyramiding ha bloccato 57 ingressi; su 8 segnali distinti sopra gate

* Tipo: Osservazione
* Area: Signal
* Evidenza:
  * file/log/tabella: `logs/containers/worker-2026-09-15.log`; `execution_decisions`
  * timestamp: 14:07 → 18:37 UTC
  * snippet/query: firing per simbolo — MRK 17, XLE 10, XOM 7, NFLX 7, CVX 7, SHEL 6, SPY 2, LLY 1. Righe `SKIP_PYRAMIDING` persistite: 9 (vedi [DAY-004] per MRK).
* Descrizione: otto segnali sopra il gate d'ingresso non hanno potuto comprare perché il simbolo era già a libro da S1/legacy (LLY dal 2026-07-15, XOM dal 07-13, SPY dal 07-10, XLE dal 08-31).
* Impatto: controfattuale a chiusura di seduta, size 2% NAV (2.185 $) per segnale, entrata alla barra 15 min del blocco: NFLX +8,59, MRK +6,02, CVX +7,25, XOM +1,81, SHEL +0,44, SPY +0,01, XLE −6,45, LLY −12,20 → **+5,48 $ lordi complessivi**. Al netto di ~28 $ di costi di round-trip stimati (16 bp × 8 × 2.185), il guard ha fatto **risparmiare** ~22 $ alla seduta. Il difetto resta strutturale, non ha avuto un costo oggi.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna in periodo di osservazione. Continuare a registrare i controfattuali.
* Test/monitor consigliato: già coperto dal worker controfattuale (`SKIP_PYRAMIDING` 9/9 calcolati).

### [DAY-019] [F-013] PLTR comprato alle 16:07 e chiuso alle 17:52 su un segnale a punteggio 0,000

* Tipo: Bug
* Area: Orders
* Evidenza:
  * file/log/tabella: `execution_decisions` 25388 e 26113; `trades` 1004; `sentiment_signals` 10998 e 11044
  * timestamp: BUY 16:07:00,61 → SELL 17:52:00,60 UTC (1h45)
  * snippet: entrata su segnale 10998 (+0,343, conf 0,70, 16:01); uscita su segnale 11044 (**+0,000**, conf 0,20, 17:36) con reason `[below_entry_gate] … score=+0.000: weight 0.0%, position closed`. `trades.exit_reason = 'hold_minimum_expiry'`: la posizione è stata chiusa al **primo ciclo eleggibile** dopo lo scadere del hold minimum (6.300 s esatti).
* Descrizione: il gate d'ingresso è 0,30, il gate d'uscita è 0. Fra i due non c'è banda: qualunque segnale successivo che non ripeta ≥ 0,30 liquida. Il hold minimum ha soltanto ritardato la chiusura, non l'ha evitata.
* Impatto: la posizione ha reso **+15,41 $ netti**. Controfattuale "tenere fino a chiusura": uscita a 174,80 contro chiusura 172,605 → **l'uscita anticipata ha risparmiato 18,43 $** su 8,398565 azioni. Il difetto è strutturale; oggi ha giocato a favore.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna in periodo di osservazione (la banda è taratura).
* Test/monitor consigliato: già registrato dal ledger.

### [DAY-020] [F-059] Entrambe le liquidazioni sono state decise da segnali che non basterebbero ad aprire una posizione

* Tipo: Bug
* Area: Signal
* Evidenza:
  * file/log/tabella: `sentiment_signals` 10994 e 11044; `execution_decisions` 25389 e 26113
  * timestamp: 16:07 (NFLX) e 17:52 (PLTR) UTC
  * snippet: NFLX chiusa su segnale a **confidence 0,60** e score −0,171; PLTR chiusa su segnale a **confidence 0,20** e score +0,000. `min_confidence` richiesto per entrare: 0,30 (e il floor dell'aggregatore è 0,40).
* Descrizione: nessuna soglia di confidenza protegge l'uscita. Un segnale che il sistema considera troppo incerto per comprare è abbastanza certo per vendere.
* Impatto: sulla chiusura PLTR il costo è già attribuito a [DAY-019] (−18,43, cioè un risparmio). Su NFLX l'uscita a 77,88 contro chiusura 77,935 ha lasciato sul tavolo 0,99 $ — irrilevante.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna in periodo di osservazione (è simmetria di soglie, cioè taratura).
* Test/monitor consigliato: registrare la confidenza del segnale che decide ogni uscita, per costruire la serie.

### [DAY-021] [F-061] Il ledger append-only delle uscite S4 riemette due eventi già registrati

* Tipo: Bug
* Area: PnL
* Evidenza:
  * file/log/tabella: `s4_exit_policy_events`
  * timestamp: 09-15 14:12:05 e 14:27:05 (HOOD); 09-15 16:12:05 e 17:57:05 (PLTR)
  * snippet/query: `SELECT symbol, intent_id, trigger_at, COUNT(*) FROM s4_exit_policy_events WHERE created_at::date='2026-09-15' AND event_type='P0_RUNTIME_REPLAY' GROUP BY 1,2,3 HAVING COUNT(*)>1` → HOOD (trigger 2026-09-14 18:22:00) ×2, PLTR (trigger 2026-09-11 18:22:00) ×2. `event_id` diversi, stesso `intent_id`, stesso `fill_price`, stesso `net_pnl`.
  * Sul giorno: 32 righe totali (9 `P0_RUNTIME_REPLAY`, 12 `P1_HOLDING`, 7 `P1_TIME_DUE`, 4 `P0_OPEN_SNAPSHOT`), di cui 2 duplicate.
* Descrizione: il riconciliatore intraday ricalcola gli eventi derivati a ogni ciclo (`run_reconcile_fills_intraday` riporta 17-19 lifecycle e 4-5 P0 a ogni giro) e la deduplica non tiene su tutti i rami.
* Impatto: contare P&L o uscite dal trial ledger sovrastima. Sul 09-15 il doppio conteggio vale −3,90 $ (HOOD) e +0,69 $ (PLTR): irrilevante come importo, fatale come metodo, perché il trial S4 si decide su quel ledger.
* Severità: Medium
* Confidenza: High
* Azione consigliata: chiave naturale unica su `(intent_id, policy_id, event_type, trigger_at)` con `ON CONFLICT DO NOTHING`.
* Test/monitor consigliato: invariante di unicità sulla chiave naturale, verificata a fine giornata.

### [DAY-022] [F-025] Posizioni S4 aperte da 21,7 giorni contro un orizzonte di trial dichiarato a D+2

* Tipo: Bug
* Area: Orders
* Evidenza:
  * file/log/tabella: `trades`; `s4_exit_policy_events`
  * timestamp: fotografia a fine seduta
  * snippet/query: `SELECT symbol, entry_time FROM trades WHERE exit_time IS NULL` → CSCO 2026-08-25 (**21,7 gg**), XLE 08-31 (15,7), BP/GOOGL/PFE 09-01 (14,9), PANW 09-14 (1,8), BA 09-15 (0,9). Le altre 33 risalgono a luglio/agosto (S1).
* Descrizione: il ramo `preserve-stale` (FIX-D) mantiene indefinitamente le posizioni tiepidamente positive, mentre la scadenza a 4h chiude le altre. Non esiste orizzonte massimo.
* Impatto: il campione del trial S4 contiene posizioni a tre settimane accanto a posizioni a un'ora. Va segmentato, non mediato.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna in periodo di osservazione.
* Test/monitor consigliato: distribuzione dell'età delle posizioni S4 nel report giornaliero.

### [DAY-023] [F-014] `portfolio_cycles.orders_count` somma 81 contro 4 ordini realmente inviati

* Tipo: Bug
* Area: Ops
* Evidenza:
  * file/log/tabella: `portfolio_cycles`
  * timestamp: 24 cicli
  * snippet/query: `SELECT SUM(orders_count) FROM portfolio_cycles WHERE timestamp::date='2026-09-15'` → **81**. Ordini effettivamente sottomessi al broker: **4** (più 3 stop protettivi). Il valore per ciclo cresce monotonamente da 3 a 5 indipendentemente dalle submission.
* Descrizione: il campo conta gli ordini **target** del combiner, non le submission. Il log dice `orders_before=4 orders_after=4 constraints=0 final=4` anche quando 3 dei 4 vengono poi bloccati.
* Impatto: qualunque conteggio di attività letto da questa tabella è di un ordine di grandezza sbagliato.
* Severità: Low
* Confidenza: High
* Azione consigliata: rinominare il campo o aggiungere `orders_submitted`.
* Test/monitor consigliato: riconciliazione `SUM(orders_count)` vs `COUNT(execution_decisions WHERE order_id IS NOT NULL)`.

### [DAY-024] [F-015] `slippage_est` è una copia esatta di `cost_usd` su entrambi i trade chiusi

* Tipo: Bug
* Area: PnL
* Evidenza:
  * file/log/tabella: `trades`
  * timestamp: 16:07 e 17:52 UTC
  * snippet/query: NFLX `slippage_est = 0.7964487432408385`, `cost_usd = 0.7964487432408385`; PLTR `0.7998895735070681` e `0.7998895735070681`.
* Descrizione: il campo non misura lo scostamento fra prezzo atteso e prezzo di fill: riporta il costo modellato.
* Impatto: la qualità di esecuzione non è misurata. Ho dovuto calcolarla a mano dai bar 15 min (§7): tutti e tre i fill del giorno sono stati favorevoli (−19, −29, +32 bp), quindi nessun problema reale — ma il sistema non lo sa.
* Severità: Low
* Confidenza: High
* Azione consigliata: registrare il prezzo di riferimento al momento della decisione e calcolare `slippage = fill − riferimento`.
* Test/monitor consigliato: asserzione `slippage_est != cost_usd` su almeno una riga del giorno.

### [DAY-025] [F-048] UNH: il ledger dice 1,5926 azioni, il broker ne ha 0,5926

* Tipo: Bug
* Area: Broker
* Evidenza:
  * file/log/tabella: `trades` id 279; `/api/positions`
  * timestamp: la posizione è aperta dal 2026-07-10; il disallineamento **precede** il 09-15
  * snippet/query: `SELECT qty, quantity_remaining, exit_order_ids FROM trades WHERE id=279` → `1.592634163 | NULL | NULL`. Posizione Alpaca UNH: `qty = 0.592634163`. Differenza: **esattamente 1 azione**, cioè il pavimento intero dello stop protettivo.
* Descrizione: un fill di stop da 1 azione è avvenuto senza che `trades.qty` venisse decrementata né `exit_order_ids` popolata. È la classe di difetto già nota delle uscite parziali. Su 40 trade aperti questo è **l'unico** disallineamento: la riconciliazione degli altri 39 chiude al centesimo.
* Impatto: il book mark-to-market sovrastima UNH di 1 azione (~375 $). `run_reconcile_positions` è girato alle 03:00 ("Reconciled 0 trade fill(s)") senza rilevarlo: il job riconcilia i **fill**, non le **quantità**.
* Severità: Medium
* Confidenza: High
* Azione consigliata: aggiungere alla riconciliazione giornaliera un confronto `trades.quantity_remaining` vs quantità broker, con alert su divergenza.
* Test/monitor consigliato: invariante giornaliero "per ogni trade aperto, `COALESCE(quantity_remaining, qty) == qty_broker`".

### [DAY-026] [F-058] Quattro incidenti mobile aperti e risolti nello stesso secondo; zero device, zero consegne

* Tipo: Bug
* Area: Ops
* Evidenza:
  * file/log/tabella: `mobile_events`; `mobile_notification_deliveries`; `monitor_devices`
  * timestamp: aperti 22:50:00,4–0,7 — risolti 22:50:01,0 UTC
  * snippet/query: `Griglia portfolio-cycle fuori seduta` (warning), `Copertura news assente su PFE / SBUX / UNH` (warning) — tutti `status='recovered'` entro 1 secondo. `SELECT COUNT(*) FROM monitor_devices` → **0**; `mobile_notification_deliveries` dal 09-15 → **0**.
* Descrizione: il valutatore apre un incidente e lo chiude nello stesso ciclo perché la condizione non è più vera (fuori seduta, per costruzione). L'incidente CRITICAL delle 13:30 ([DAY-010]) ha avuto sorte analoga, chiuso da solo alle 14:08.
* Impatto: la coda incidenti è formalmente pulita e operativamente inerte: nessun canale, nessuna consegna, nessun destinatario registrato.
* Severità: Medium
* Confidenza: High
* Azione consigliata: non auto-risolvere un incidente mai notificato; registrare almeno un device o disattivare il ramo mobile dichiarandolo.
* Test/monitor consigliato: alert se `mobile_events` del giorno > 0 e `mobile_notification_deliveries` = 0.

### [DAY-027] [F-011] Le due righe SELL non hanno `signal_id`: la catena segnale→decisione→trade si spezza sul lato uscita

* Tipo: Bug
* Area: Signal
* Evidenza:
  * file/log/tabella: `execution_decisions` 25389 e 26113
  * timestamp: 16:07 e 17:52 UTC
  * snippet/query: `SELECT decision, COUNT(signal_id) FROM execution_decisions WHERE tick_time::date='2026-09-15' GROUP BY 1` → `BUY 2/2`, **`SELL 0/2`**. Tutte le 2.482 righe di SKIP/OBSERVE hanno invece `signal_id`.
* Descrizione: il segnale che ha causato l'uscita è citato nel testo di `reason` (`generated 2026-09-15 15:55 UTC, score=-0.171`) ma non è legato per chiave esterna. Ho dovuto risalire a 10994 e 11044 per timestamp.
* Impatto: ogni ricostruzione automatica "quale segnale ha chiuso questa posizione" richiede parsing di testo libero. Sul lato ingresso il link c'è; sul lato uscita no.
* Severità: Medium
* Confidenza: High
* Azione consigliata: popolare `signal_id` anche sulle righe SELL.
* Test/monitor consigliato: invariante "ogni riga BUY/SELL con `order_id` ha `signal_id` non nullo".

## 11. False positive e aree risultate corrette

* **F-073 non è osservabile oggi.** `execution_decisions.signal_score` porta il valore **post-velocity**, non quello grezzo: il rapporto `signal_score / sentiment_signals.score` vale 1,20 su 49 righe, 0,80 su 48, 1,00 su 467 (BA: 0,5136 × 1,20 = 0,6164, persistito 0,6164). La contraddizione del 09-08 non si riproduce. Non ho verificato se si tratti di una correzione o di un percorso diverso — chi riprende F-073 deve partire da qui.
* **`hold_minimum_expiry` non contraddice `below_entry_gate`.** Sono due campi diversi: `trades.exit_reason` porta il marker temporale (#430, primo ciclo dopo lo scadere del hold minimum, 6.300 s esatti), `execution_decisions.reason` porta la causa. Coerenti.
* **Ollama non è caduto.** 6 timeout in 24 ore su ~420 chiamate (2 in RTH), 0 fallback FinBERT, `consecutive_fallback = 0`. Il circuit breaker è rimasto inattivo a ragione.
* **Idempotenza verificata.** `SIGNAL_DUPLICATE_SKIP` ha impedito 20 ri-esecuzioni di BA e PLTR sugli stessi `signal_id` nei cicli successivi al 16:07.
* **Il guard di staleness funziona.** 5/36 segnali scartati per età > 4h al ciclo 16:07; 22-24 scartati per entry-freshness (2h) a ogni ciclo; FIX-D preserva solo i simboli a libro senza contro-segnale.
* **Nessun pattern operativo sospetto.** Zero roundtrip < 30 min, zero pyramiding, zero SELL su sentiment positivo, zero ordini nello stesso minuto sullo stesso simbolo, zero ordini fuori 13:30–20:00, zero decisioni BUY/SELL senza `order_id`.
* **Riconciliazione ordini/fill/posizioni.** 4 ordini inviati, 4 riempiti, 0 rifiutati; 40 trade aperti ↔ 40 posizioni Alpaca, 39 combaciano al centesimo (l'unica eccezione è UNH, [DAY-025], e precede il 09-15).
* **F-009 non ha costo misurabile oggi.** 102 segnali distinti scartati dal gate 0,30 con controfattuale calcolato: 46 avevano il segno corretto a +1h (45%). Limitando ai soli rialzisti (gli unici tradabili, long-only): 55 segnali, 29 in salita (52,7%), **+21,91 $ lordi** distribuiti su 55 posizioni ipotetiche al 2% NAV, cioè 0,40 $ ciascuna. Rumore.
* **F-040 confermata ma senza costo.** 10 segnali ribassisti sopra |0,30| (NVDA −0,490, NVO/NKE −0,420, QQQ −0,381, …), nessuno tradabile per vincolo long-only. NKE ha effettivamente chiuso a −0,50%: il segnale era corretto e inutilizzabile.
* **`portfolio_cycle_persist_failures` vuota** per il giorno: nessun ciclo perso in scrittura.
* **Il forward-return worker ha girato correttamente** (1.085 segnali, 1.023 aggiornati, 0 errori). I forward return del 09-15 sono NULL per costruzione: verranno calcolati al giro del 09-16.

## 12. Dati mancanti o non accessibili

| dato | perché manca | query/azione che servirebbe |
|---|---|---|
| `news_log.transport` per il 09-15 | migrazione 075 applicata al live il **2026-09-16 10:20**, dopo la seduta | nessuna: non misurato, non recuperabile |
| Latenza per chiamata LLM | non strumentata; solo la durata del task | istrumentare `run_ensemble_query` con un istogramma per modello |
| Slippage reale | `slippage_est` è `cost_usd` ([DAY-024]) | persistere il prezzo di riferimento alla decisione |
| PnL non realizzato per ticker al 09-15 EOD | `risk_reports` salva solo il NAV; `/api/positions` dà il mark corrente; `portfolio_monitor_snapshots` non popolata per il giorno | snapshot posizioni EOD, tabella da creare |
| Benchmark SPY interno | fetch SIP negato ([DAY-011]); ho usato il feed IEX a mano | passare il benchmark su IEX |
| Controfattuale di `SKIP_FALLBACK` | escluso dall'indice ([DAY-003]) | aggiungere la decisione all'indice e rieseguire il worker |
| Blocchi P0-05 su MRK | chiave di deduplica senza giorno ([DAY-004]) | ricostruibili solo dal log del worker, che non sopravvive al redeploy |
| Timestamp delle eccezioni API | uvicorn non li stampa nel log di accesso | abilitare il formato con timestamp |

## 13. Raccomandazioni immediate

1. **Correggere l'escape dei messaggi Telegram** ([DAY-001]). Le allerte di rischio sono l'unico canale vivo e ne perde 4 su 5. La causa è puntuale e nota: `qty < 1` sotto `parse_mode="HTML"`.
2. **Separare `finbert_fallbacks` da `single_model`** nell'esito del task sentiment ([DAY-002]). Finché resta così, ogni report che non interroghi il DB dichiara un outage FinBERT inesistente.
3. **Aggiungere `SKIP_FALLBACK` all'indice del controfattuale** ([DAY-003]). È il ramo di scarto più grande dopo il gate e non è mai stato misurato.
4. **Mettere il giorno nella chiave di deduplica di `SKIP_PYRAMIDING`** ([DAY-004]).
5. **Aggiungere il confronto quantità broker vs `trades`** alla riconciliazione giornaliera ([DAY-025]).
6. Nessuna raccomandazione di taratura: siamo dentro la finestra di sola osservazione fino al 2026-09-28.

## 14. Test / monitor da aggiungere

| # | test o monitor | copre |
|---|---|---|
| T1 | invio di ogni template di alert a un finto endpoint Telegram con validatore del `parse_mode` | [DAY-001] |
| T2 | con un modello sotto `min_confidence`: `finbert_fallbacks == 0` e `single_model == 1` | [DAY-002] |
| T3 | invariante `finbert_fallbacks del giorno == COUNT(finbert_fallback_events)` | [DAY-002] |
| T4 | ogni `SKIP%` con `signal_id` riceve un controfattuale o una `skip_reason` entro 24h | [DAY-003] |
| T5 | stesso `signal_id` bloccato in due giorni → due righe `SKIP_PYRAMIDING` | [DAY-004] |
| T6 | doppio `close()` su uno store pooled non solleva; alert su `PoolError` nei log API | [DAY-005] |
| T7 | invariante "≥2 righe `llm_responses` ⇒ `ensemble_std` = deviazione delle loro polarity" | [DAY-006] |
| T8 | invariante "segnale `ensemble:` con N contributori ⇒ N righe `eligible=true`" | [DAY-007] |
| T9 | contatore alert CRITICAL emessi vs consegnati, allerta su divergenza | [DAY-008], [DAY-026] |
| T10 | primo ciclo del giorno entro 10 min dall'apertura del calendario Alpaca | [DAY-010] |
| T11 | unicità su `(intent_id, policy_id, event_type, trigger_at)` in `s4_exit_policy_events` | [DAY-021] |
| T12 | invariante giornaliero `COALESCE(quantity_remaining, qty) == qty_broker` per ogni trade aperto | [DAY-025] |
| T13 | invariante "riga BUY/SELL con `order_id` ⇒ `signal_id` non nullo" | [DAY-027] |

## 15. Ticket tecnici suggeriti

Tutti di **correttezza**, esenti dal congelamento della carta (senza di essi
l'evidenza raccolta nelle prossime settimane è sbagliata).

| ticket | titolo | finding | priorità |
|---|---|---|---|
| A | `run_sentiment_worker`: separare `single_model` da `finbert_fallbacks` nel dict di ritorno | F-078 | alta |
| B | Aggiungere `SKIP_FALLBACK` all'indice e alla query del worker controfattuale | F-079 | alta |
| C | `_pyramiding_block_key`: includere il giorno anche con `signal_id` presente | F-080 | media |
| D | `TelegramNotifier`: escape del corpo secondo il `parse_mode` effettivo | F-005 | alta |
| E | `PostgreSQLStore.close()` idempotente + diagnosi del doppio rilascio | F-081 | media |
| F | Riconciliazione giornaliera quantità: `trades` vs posizioni broker | F-048 | media |
| G | Chiave naturale unica su `s4_exit_policy_events` | F-061 | alta (decide il trial S4) |
| H | Popolare `signal_id` sulle righe SELL di `execution_decisions` | F-011 | media |
| I | `ensemble_std` calcolato prima del filtro di eleggibilità | F-054 | media |
| J | Benchmark SPY su feed IEX, o `NO_BENCHMARK` esplicito | F-016 | media |

## 16. Stato sistema

| voce | valore |
|---|---|
| **Ollama** | **up**. 6 timeout da 90 s in 24h (06:17 glm, 10:17 gpt-oss, 10:24 gpt-oss, 14:35 gpt-oss, 16:43 glm, 22:16 glm), di cui **2 in RTH**. Nessun intervallo di indisponibilità: **0 ore di downtime**. 0 refusal, 0 parse fail. |
| **FinBERT fallback rate** | **0,0%** (0 su 211 segnali; 0 righe in `finbert_fallback_events`; 0 segnali `model_id='finbert'`). Il valore riportato dal worker (34,1%) è errato — vedi [DAY-002]. |
| **Degradazione a modello singolo** | 72/211 = **34,1%** (63 `gpt-oss`, 9 `glm-5.2`). 29 cicli RTH su 103 sotto il 50% di ensemble pieno. Nessun alert di degradazione sostenuta emesso. |
| **Circuit breaker fallback** | inattivo. `consecutive_fallback = 0`, ultimo reset 19:56:29. |
| **Worker restart** | **1**: warm shutdown e ripartenza del container `worker` alle **20:20:15 UTC** (deploy della migrazione 076, applicata alle 20:20:08). Fuori seduta, nessun ciclo perso. |
| **Cicli di portafoglio** | 24 su 26 attesi (persi 13:37 e 13:52, [DAY-010]). 0 fallimenti di persistenza. |
| **Cicli sentiment** | 106 con almeno un articolo, 3 a zero, 85 saltati per `market_closed`. |
| **Alert consegnati** | 1 su 5 (solo stale-drop 22:55). 10 CRITICAL decay senza canale. 0 device mobile, 0 consegne mobile. |
| **Errori applicativi** | worker: 0 ERROR, 10 CRITICAL (tutti decay). worker-inference: 5 ERROR (1 FRED 500, 4 rete Telegram). api: 2 eccezioni ASGI (`PoolError`). beat: 0. |
| **Modelli attivi** | `config:sentiment_llm_models = glm52,gptoss`; pesi `{glm-5.2: 0,70, gpt-oss: 0,30}` (auto_apply). |
| **Soglia S4** | `feedback:entry_threshold:S4 = 0.30` — invariata, ratchet congelato alle 16:30. |
