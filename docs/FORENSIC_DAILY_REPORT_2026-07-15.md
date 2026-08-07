# Forensic Daily Report — 2026-07-15

Analista: sessione autonoma Claude (Forensic Analyst + Backend Engineer + Quant Ops Reviewer)
Modalità: read-only, nessuna scrittura su DB/broker, nessuna esecuzione di pipeline live.
Timezone operativo: **UTC** (confermato in `src/workers/celery_app.py:49` `timezone="UTC"`, `enable_utc=True`; DB Postgres `SHOW timezone` → `UTC`). Nessuna ambiguità di timezone trovata.
Market hours di riferimento: 13:30–20:00 UTC (9:30–16:00 ET). Ingest news e sentiment worker sono schedulati **14:00–21:00 UTC** (crontab `hour="14-21"`), non 13:30 — vedi [DAY-007].

Fonti usate: Postgres `alembic-postgres-1` (tabelle `news_log`, `ingestion_stats_daily`, `sentiment_signals`, `llm_responses`, `execution_decisions`, `trades`, `portfolio_cycles`, `risk_reports`, `strategy_lifecycle`, `fallback_counters`, `llm_budget`, `audit_log`), API REST locale (`/api/decisions`, `/api/trades`, `/api/signals`, `/api/positions`, `/api/orders`), codice sorgente (`src/workers/*.py`, `src/strategies/s4/*.py`, `src/portfolio/orchestrator.py`, `src/store/pg_store.py`).

**Log Docker NON disponibili per il 2026-07-15**: tutti i container (`worker`, `worker-inference`, `beat`, `api`) sono stati riavviati il 2026-07-16 12:21:38 UTC (verificato via `docker inspect --format '{{.State.StartedAt}}'`), quindi `docker compose logs --since 48h` copre solo dal 2026-07-16 11:43 in poi. La ricostruzione della giornata del 07-15 si basa **interamente su Postgres** (che conserva timestamp e dettaglio completi) — vedi [DAY-004].

---

## 1. Executive Summary

Il 2026-07-15 il sistema ha operato in **paper trading** (S1 `supervised_paper`, S4 `paper`, `execution.engine=portfolio`), con S1 momentum e S4 news-driven attivi, S2/S7 disabilitati. 202 news ingerite (92 Benzinga/Alpaca, 110 GDELT GKG, spike su MS/GS per stagione earnings bancari), 206 segnali di sentiment generati dall'ensemble glm-5.2+gpt-oss, 24 cicli di portfolio da 15 minuti, 23 decisioni di esecuzione (15 BUY, 8 SELL) tutte tracciate fino al fill (100% riconciliate ordine↔decisione↔trade). PnL realizzato dai trade chiusi il 07-15: **+$84.15 netto** (8 trade, 5 vincenti/3 perdenti, tutti S4). Nessun processo di broker/rischio ha bloccato la giornata (circuit breaker non attivato, 0 alert di rischio, drawdown combinato 6.96%).

Ho però trovato un **bug di correttezza critico e riproducibile**: un ordine BUY reale (MSFT, trade #347, $3,077.55, tuttora aperto) è stato generato dalla strategia S4 (long-only per design) attribuito a un segnale di sentiment **negativo** (-0.110, "Competitive AI growth likely erodes MSFT's relative position"). Il codice del ranker (`src/strategies/s4/ranking.py:155`) impone esplicitamente `if strength <= 0: continue` (long-only), quindi questo ordine non dovrebbe essere potuto esistere secondo la logica attuale — evidenza di una probabile race condition fra due segnali MSFT contraddittori generati a 34 secondi di distanza (+0.165 poi -0.110). È un caso isolato (nessun altro negli ultimi 7 giorni), ma è esattamente la classe di errore che il progetto considera worst-case (CLAUDE.md: "A wrong ticker/direction is the worst-case error").

Altri due difetti minori: l'endpoint `/api/orders` restituisce la stringa letterale `"None"` per il campo `qty` di tutti gli ordini BUY a notional (180/300 ordini campionati) per un bug di field-mapping (`o.qty` invece di `o.filled_qty`); e la metrica `herfindahl_index` in `risk_reports` è strutturalmente degenere (sempre vicina a 1.0) perché calcolata su pesi per-strategia con solo 2 strategie attive, non su pesi per-simbolo — probabilmente non fa quello che il nome suggerisce.

Un singolo blackout Ollama transitorio (12/12 chiamate in timeout nello stesso batch, 18:45:02–18:45:06 UTC) è stato assorbito correttamente dal fallback FinBERT senza impatto operativo. Il tasso di fallback complessivo resta alto (51.5%, 106/206 segnali), ma è un problema noto e già tracciato (non peggiorato rispetto alla scorsa settimana).

## 2. Verdict Finale

**OK con warning** — la pipeline end-to-end ha funzionato correttamente nella stragrande maggioranza dei casi (23/23 decisioni riconciliate, tutte le SELL per scadenza segnale corrette, nessuna pyramiding, nessun ordine duplicato, nessun trade su strategia disabilitata, sanitizzazione e resolver ticker regolarmente applicati). Il downgrade da "OK" a "OK con warning" è motivato dal bug **[DAY-001] Critical** (BUY con sentiment negativo) che viola l'invariante long-only documentato, e da due difetti minori di data-quality/osservabilità ([DAY-002], [DAY-003]).

---

## 3. Timeline del 2026-07-15 (UTC)

| Ora (UTC) | Componente | Evento | Fonte |
|---|---|---|---|
| 07:00 | `regime-detector` (beat) | Regime detection giornaliera pre-market | celery_app.py beat schedule |
| 13:11–13:24 | Ingest Benzinga | Prime news pubblicate (GS 13:11, MS 13:23, NVDA 13:14) — **pubblicate prima che l'ingest inizi a girare (14:00)** | `news_log.published_at` |
| 13:30 | `regime-detector-premarket` (beat) | Secondo run regime, 30 min prima apertura NYSE (safety net) | celery_app.py:117 |
| 13:30 | Market open (NYSE) | — | riferimento esterno |
| 14:00–14:01 | Ingest Benzinga + GDELT (primo ciclo) | Primo fetch della giornata; 202 news totali finiranno in `news_log` entro le 19:48 | `ingestion_stats_daily`, `news_log` |
| 14:01:22–19:48:01 | Sentiment worker (ogni 15 min, batch ~12 articoli) | 206 `sentiment_signals` generati (94 divergenza→FinBERT, 12 timeout→FinBERT, 100 ensemble) | `sentiment_signals` |
| 14:07:00 | Portfolio cycle #438 (S1+S4) | 44 ordini candidati → 7 nuove BUY S1 (XLV,C,CSCO,GM,JNJ,LLY,MRK, peso 1.3% cad.) | `portfolio_cycles`, `execution_decisions` |
| 14:22:00 | Portfolio cycle #439 | 5 SELL per scadenza segnale S4 >4h (TM,NVO,NFLX,MSFT-vecchia posizione,DIS) + 1 BUY S1 (CVX) | `execution_decisions` 2857–2863 |
| 14:37:00 | Portfolio cycle #440 | BUY S4 IBM (sentiment +0.165) | `execution_decisions` 2863 |
| 14:52:00 | Portfolio cycle #441 | BUY S4 NVDA (sentiment +0.170) | `execution_decisions` 2864 |
| 15:22:00 | Portfolio cycle #443 | BUY S4 BABA (sentiment +0.558) | `execution_decisions` 2865 |
| 16:37:00 | Portfolio cycle #448 | SELL NVDA — segnale decaduto a -0.020 (sotto soglia), correttamente chiuso | `execution_decisions` 2866 |
| 17:22:00 | Portfolio cycle #451 | SELL IBM (segnale a 0.000, decaduto) + BUY S4 INFY (fallback FinBERT, +0.429) | `execution_decisions` 2867–2868 |
| **18:30:16 / 18:30:50** | Sentiment worker | **Due segnali MSFT contraddittori a 34s di distanza**: id 3770 (+0.165, ensemble completo) poi id 3773 (-0.110, solo gpt-oss) | `sentiment_signals` 3770, 3773 |
| 18:37:00 | Portfolio cycle #456 | 47 ordini candidati → BUY S4 MMM (+0.352, corretto) **e BUY S4 MSFT (-0.110, [DAY-001])**, entrambi 5% peso | `portfolio_cycles.final_orders`, `execution_decisions` 2870–2871 |
| 18:45:02–18:45:06 | Sentiment worker (batch) | **12/12 chiamate Ollama in timeout** nello stesso batch → fallback FinBERT completo | `sentiment_signals` (reasoning="FinBERT fallback (Ollama timeout)") |
| 19:00:11 | Sentiment worker | Ripristino parziale (1 solo fallback per divergenza, non timeout) | `sentiment_signals` |
| 19:15:09 | Sentiment worker | Ripristino completo ensemble (glm+gpt-oss tornano a rispondere) | `sentiment_signals` |
| 19:37:00 | Portfolio cycle #460 | SELL BABA per scadenza segnale (4.3h > 4h max) | `execution_decisions` 2872 |
| 19:52:00 | Portfolio cycle #461 (ultimo della giornata) | 45 ordini candidati, nessuna nuova decisione | `portfolio_cycles` |
| 20:00 | Market close (NYSE) | — | riferimento esterno |
| 21:30 | `reconcile-fills-evening` (beat) | EOD reconcile pass | celery_app.py:85 |
| 22:00 | `forward-return-worker` (beat) | Calcolo forward return per IC/ICIR | celery_app.py:73 |
| 22:30:00 | Risk monitor | Unico `risk_reports` della giornata: NAV $110,028.94, exposure 36.49%, drawdown 6.96%, 0 alert | `risk_reports` id=33 |

Nessun evento registrato dopo le 19:52 fino al risk report delle 22:30 (finestra 14:00–21:00 UTC per ingest/sentiment/portfolio-cycle è per design, coerente con beat schedule).

---

## 4. Tabella News Ingest

### Per fonte (righe effettivamente in `news_log`, 2026-07-15 00:00–24:00 UTC)

| Fonte | Righe salvate | Range temporale (fetched_at) | Extraction method | Discarded (post-log) |
|---|---|---|---|---|
| alpaca_benzinga | 92 | 14:01:22 – 19:46:12 | source_metadata (92) | 0 |
| gdelt_gkg | 110 | 15:15:17 – 19:48:01 | org_lookup (110) | 0 |
| **Totale** | **202** | | | **0** |

### Funnel counters (`ingestion_stats_daily`, cumulativi su tutti i cicli del giorno — nota metodologica sotto)

| Fonte | fetched (item grezzi) | queued (per-ticker) | duplicates (per-ticker) | discarded_no_ticker |
|---|---|---|---|---|
| alpaca_benzinga | 478 | 326 | 2044 | 0 |
| gdelt_gkg | 2112 | 203 | 62 | 1882 |

**Nota metodologica importante**: `fetched` conta gli item grezzi (un articolo = 1), mentre `queued`/`duplicates` contano **dopo il fan-out per-ticker** (un articolo con 3 asset tag genera 3 candidati); per questo `duplicates` può superare `fetched` senza essere un'anomalia (`src/workers/ingestion.py:106-155`, confermato). Il rapporto `queued`(326)→righe salvate in `news_log`(92) per Benzinga si spiega con il vincolo `UNIQUE(url, ticker)`: molte espansioni per-ticker collassano sullo stesso `(url,ticker)` già visto in cicli precedenti dello stesso giorno.

Per GDELT, `discarded_no_ticker`=1882/2112 (89%) conferma che la fonte è strutturalmente rumorosa (bassissima resa ticker-match) — coerente con la storia nota del progetto (GDELT come fonte a basso yield).

### Per ticker (top 15, 2026-07-15)

| Ticker | # news | Note |
|---|---|---|
| MS | 50 | Morgan Stanley earnings day (Dow: "Morgan Stanley Profit Tops Views") |
| GS | 20 | Goldman Sachs earnings |
| MU | 12 | Micron |
| BRKB | 9 | Berkshire |
| NVDA | 8 | |
| ASML | 6 | Guidance bullish chip forecast |
| AAPL | 5 | |
| DB | 5 | Deutsche Bank |
| MSFT | 5 | Incluse le 2 news contraddittorie delle 18:30 (vedi [DAY-001]) |
| TSM, INTC, AMAT, JPM | 3–4 cad. | |

### Controlli specifici

| Check | Esito |
|---|---|
| Timestamp futuri (`published_at > fetched_at + 5min`) | **0 righe** — nessuna anomalia |
| Duplicati cross-provider (stesso `content_hash`, fonti diverse) | **0 righe** — nessun overlap Benzinga/GDELT rilevato quel giorno |
| Buchi temporali > 60 min tra news consecutive | **0** — copertura continua 14:01–19:48 |
| News fuori mercato (prima 13:30 / dopo 20:00) | 12 news pubblicate 13:11–13:29 (pre-market, normali, ingerite comunque appena il worker parte alle 14:00) |
| Campi mancanti (`ticker`, `source`) | Nessuno — vincoli NOT NULL rispettati |
| Sanitizzazione applicata prima del prompt LLM | Confermato in codice (`sanitize_text`/`sanitize_ticker`, `src/workers/sentiment.py:202-204`), non verificabile a runtime senza log (vedi [DAY-004]) |
| Ticker ambiguity / risoluzione bare-text ($cashtag) | 0 righe con `extraction_method` = bare-text/cashtag; solo `org_lookup`/`source_metadata` — nessun caso ambiguo quel giorno |

**Confidenza analisi news ingest: High** (dati completi in DB, controlli incrociati coerenti).

---

## 5. Tabella Performance Modelli LLM

Ensemble live confermato: **glm-5.2:cloud + gpt-oss:20b-cloud** (coerente con `config:sentiment_llm_models` noto da sessioni precedenti).

| Modello | Chiamate loggate (`llm_responses`) | Eligible (contribuiscono all'ensemble) | Non-eligible (chiamata fatta, esclusa da aggregazione) | Avg polarity | Avg confidence |
|---|---|---|---|---|---|
| glm-5.2:cloud | 194 | 48 (24.7%) | 146 | 0.082 | 0.311 |
| gpt-oss:20b-cloud | 194 | 90 (46.4%) | 104 | 0.070 | 0.396 |

### Composizione dei 206 `sentiment_signals` del giorno

| Esito | Count | % |
|---|---|---|
| Ensemble completo (entrambi i modelli concordi/eligible) | 38 | 18.4% |
| Solo glm-5.2 eligible | 10 | 4.9% |
| Solo gpt-oss eligible | 52 | 25.2% |
| **Fallback FinBERT — divergenza ensemble** | 94 | 45.6% |
| **Fallback FinBERT — timeout Ollama** | 12 | 5.8% |
| **Totale fallback FinBERT** | **106** | **51.5%** |

### Disaccordo estremo rilevato

Il caso più significativo del giorno: **MSFT**, due segnali generati a 34 secondi di distanza sulla stessa notizia/finestra:
- id 3770, 18:30:16 UTC: score **+0.165**, ensemble completo (glm+gpt-oss d'accordo)
- id 3773, 18:30:50 UTC: score **-0.110**, solo gpt-oss (glm-5.2 escluso/non eligible)

Questo caso alimenta direttamente [DAY-001].

### Verifiche funzionali richieste

| Domanda | Risposta |
|---|---|
| Output LLM validato prima di entrare nel signal store? | Sì — schema strutturato (`LLMSentimentOutput`, function calling), righe non valide non arrivano a `sentiment_signals` (solo a `llm_responses` se applicabile) |
| L'ensemble gestisce varianza alta? | Sì per design (fallback a FinBERT su divergenza) — ma il tasso di fallback resta alto (51.5%), vedi [DAY-006] |
| News duplicate pesano più volte? | No — dedup `(url,ticker)` a monte impedisce doppio conteggio della stessa notizia |
| Stessa news può generare segnali multipli? | Solo se menziona più ticker (fan-out per-ticker by design, 1 segnale per (news,ticker)) |
| Confidence bassa riduce il peso? | Sì — `score = polarity × confidence` (CLAUDE.md), verificato nei dati (es. MSFT -0.11 = polarity più alta × confidence 0.55) |
| Modelli chiamati offline/background, mai nel trading loop? | Confermato — `sentiment.py` gira nel worker Celery `inference` queue, il portfolio cycle legge solo da Postgres (`fetch_signals_for_cycle`), mai chiamate LLM sincrone nel ciclo di trading |
| Rischio hallucination diretta in decisione trading? | Mitigato da RAG-free ma strutturato DK-CoT + validazione JSON; nessun caso di reasoning palesemente incoerente col ticker trovato oggi |

**Confidenza analisi LLM: High** per i conteggi (dati DB completi), **Medium** per la causa esatta della divergenza (non abbiamo i prompt/raw text esatti per ogni singola divergenza).

---

## 6. Tabella Segnali Finali per Ticker (quelli che hanno guidato una decisione)

| Ticker | Score sentiment | Modello | Decisione | Peso | Note |
|---|---|---|---|---|---|
| IBM | +0.165 | ensemble:gpt-oss | BUY | 3.3% | poi SELL 17:22 (segnale decaduto a 0) |
| NVDA | +0.170 | ensemble:glm+gpt-oss | BUY | 2.0% | poi SELL 16:37 (segnale a -0.020) |
| BABA | +0.558 | ensemble:glm+gpt-oss | BUY | 2.0% | poi SELL 19:37 (scaduto 4.3h) |
| INFY | +0.429 | finbert (fallback divergenza) | BUY | 3.3% | ancora aperta |
| NVO | +0.210 | ensemble:gpt-oss | BUY | 3.3% | ancora aperta |
| MMM | +0.352 | ensemble:glm+gpt-oss | BUY | 5.0% | ancora aperta — **corretto**, contrasto diretto con MSFT sotto |
| **MSFT** | **-0.110** | ensemble:gpt-oss (solo) | **BUY** | **5.0%** | **[DAY-001] — long-only violato** |
| TM,NVO(vecchia),NFLX,MSFT(vecchia),DIS,BABA | (score 0, segnale scaduto >4h) | — | SELL | 0% | chiusura per staleness, corretto |

I 7 BUY S1 momentum (XLV, C, CSCO, GM, JNJ, LLY, MRK, CVX) non hanno un "segnale sentiment" — sono guidati da momentum di prezzo puro; il campo `score` in `trades`/`execution_decisions` per queste righe è il **peso di portafoglio** (1.2-1.3%), non uno score di sentiment (vedi nota metodologica in §9).

---

## 7. Tabella Ordini Generati/Eseguiti

24 cicli di portfolio hanno prodotto tra 44 e 50 ordini "candidati" (`portfolio_cycles.final_orders`) ciascuno (~1080 candidati totali), ma solo **23 sono diventati decisioni effettive** (`execution_decisions`) — il resto sono ricalcoli di ribilanciamento per ~40 posizioni S1 già aperte, scartati dalla regola **no-pyramiding** (`P0-05`, `src/workers/portfolio_scheduler.py:1934-1937`: una BUY su un simbolo già in posizione viene sempre saltata). Questo è un comportamento **per design**, non un'anomalia — ma va tenuto presente per non confondere "ordini generati dall'orchestrator" con "ordini realmente inviati" (vedi [DAY-008]).

Riconciliazione ordine↔decisione↔trade↔fill: **23/23 = 100%** (verificato incrociando `/api/orders` filtrato per `filled_at` 07-15 con `execution_decisions` e `trades`).

| # | Tick time (UTC) | Strategia | Ticker | Side | Peso/Notional | Prezzo fill | Stato | Rationale | Segnale causante | Anomalie |
|---|---|---|---|---|---|---|---|---|---|---|
| 1-7 | 14:07:00 | S1 | XLV,C,CSCO,GM,JNJ,LLY,MRK | BUY | 1.3% / $785.36 cad. | vari | filled | momentum | n/a (S1) | — |
| 8 | 14:22:00 | S4 | TM | SELL | 0% (chiusura) | — | filled | segnale scaduto 44.4h | id 07-13 | — |
| 9 | 14:22:00 | S4 | NVO | SELL | 0% | — | filled | segnale scaduto 41.6h | id 07-13 | — |
| 10 | 14:22:00 | S4 | NFLX | SELL | 0% | — | filled | segnale scaduto 22.6h | id 07-14 | — |
| 11 | 14:22:00 | S4 | MSFT (vecchia pos.) | SELL | 0% | — | filled | segnale scaduto 42.1h | id 07-13 | — |
| 12 | 14:22:00 | S4 | DIS | SELL | 0% | — | filled | segnale scaduto 22.3h | id 07-14 | — |
| 13 | 14:22:00 | S1 | CVX | BUY | 1.2% / $767.39 | — | filled | momentum | n/a | — |
| 14 | 14:37:00 | S4 | IBM | BUY | 3.3% / $2,053.44 | 215.90 | filled | sentiment +0.165 | 3621 | — |
| 15 | 14:52:00 | S4 | NVDA | BUY | 2.0% / $1,231.85 | 210.19 | filled | sentiment +0.170 | 3628 | — |
| 16 | 15:22:00 | S4 | BABA | BUY | 2.0% / $1,230.54 | 119.08 | filled | sentiment +0.558 | 3645 | — |
| 17 | 16:37:00 | S4 | NVDA | SELL | 0% | 206.31 | filled | segnale decaduto a -0.020 | — | corretto (signal flip) |
| 18 | 17:22:00 | S4 | IBM | SELL | 0% | 213.50 | filled | segnale decaduto a 0.000 | — | corretto (signal flip) |
| 19 | 17:22:00 | S4 | INFY | BUY | 3.3% / $2,042.55 | — | filled | sentiment +0.429 (fallback FinBERT) | — | — |
| 20 | 18:07:00 | S4 | NVO | BUY | 3.3% / $2,052.44 | — | filled | sentiment +0.210 | — | — |
| 21 | 18:37:00 | S4 | MMM | BUY | 5.0% / $3,077.55 | 159.80 | filled | sentiment +0.352 | 3769 | — |
| 22 | **18:37:00** | **S4** | **MSFT** | **BUY** | **5.0% / $3,077.55** | **396.90** | **filled** | **sentiment -0.110** | **3773** | **[DAY-001] CRITICAL** |
| 23 | 19:37:00 | S4 | BABA | SELL | 0% | 117.75 | filled | segnale scaduto 4.3h | — | corretto |

Broker/engine: **Alpaca paper trading** (`execution.engine=portfolio`, `TradingClient`/`MarketOrderRequest`, `alpaca-py`). Nessun ordine live rilevato — `strategy_lifecycle` conferma S1=`supervised_paper`, S4=`paper`.

---

## 8. Tabella PnL/Rendimento

### PnL realizzato — trade chiusi il 2026-07-15 (8 trade, tutti S4)

| Trade | Simbolo | Entry | Exit | Gross PnL | Costi | Net PnL | Note |
|---|---|---|---|---|---|---|---|
| 322 | NFLX | 07-14 15:52 | 07-15 14:22 | +$20.46 | $0.67 | **+$19.79** | scadenza segnale |
| 330 | NVO | 07-14 19:22 | 07-15 14:22 | +$81.38 | $1.72 | **+$79.66** | scadenza segnale — miglior trade del giorno |
| 323 | DIS | 07-14 16:07 | 07-15 14:22 | +$20.47 | $0.67 | **+$19.80** | scadenza segnale |
| 324 | MSFT (vecchia pos.) | 07-14 17:07 | 07-15 14:22 | +$30.12 | $0.24 | **+$29.88** | scadenza segnale — **non collegata** al trade #347 (nuova posizione, stesso simbolo) |
| 332 | TM | 07-14 19:52 | 07-15 14:22 | +$7.56 | $6.26 | **+$1.31** | costi molto alti relativi al gross (83% del gross eroso da costi) |
| 342 | NVDA | 07-15 14:52 | 07-15 16:37 | -$22.72 | $0.24 | **-$22.96** | signal flip rapido (1h45m) |
| 341 | IBM | 07-15 14:37 | 07-15 17:22 | -$22.83 | $4.22 | **-$27.05** | signal flip rapido (2h45m) |
| 343 | BABA | 07-15 15:22 | 07-15 19:37 | -$13.76 | $2.52 | **-$16.28** | scaduto (4h15m) |
| **Totale (8 trade)** | | | | **+$100.68** | **$16.53** | **+$84.15** | 5 vincenti (+$150.44) / 3 perdenti (-$66.29) |

Costo medio per trade: $2.07 (16.4% del gross PnL aggregato) — non trascurabile su posizioni di questa taglia ($700–3,000).

### PnL non realizzato — posizioni aperte il 2026-07-15, ancora aperte ora (query time 2026-07-16)

| Simbolo | Entry time (07-15) | Unrealized PnL (al momento della query, 07-16) |
|---|---|---|
| LLY | 14:07 | +$15.61 |
| MRK | 14:07 | +$11.24 |
| XLV | 14:07 | +$8.99 |
| C | 14:07 | +$8.17 |
| CVX | 14:22 | +$5.91 |
| GM | 14:07 | -$3.29 |
| JNJ | 14:07 | -$12.24 |
| CSCO | 14:07 | -$30.61 |
| INFY | 17:22 | +$9.20 |
| NVO | 18:07 | +$14.28 |
| MMM | 18:37 | +$13.48 |
| **MSFT ([DAY-001])** | 18:37 | **+$16.28** (attualmente in profitto nonostante il sentiment negativo alla decisione) |
| **Totale 12 posizioni ancora aperte** | | **+$57.01** |

**Attenzione — cosa NON è questo numero**: è il PnL non realizzato calcolato **ora** (2026-07-16, mattina), non il PnL di fine giornata del 07-15. Non ho uno snapshot di prezzo di chiusura del 07-15 in questa sessione (limite dichiarato, vedi §12), quindi **non posso calcolare un "rendimento del giorno 07-15" in senso stretto** per le posizioni ancora aperte — solo il PnL realizzato (+$84.15) è un numero robusto e attribuibile puramente al 07-15.

**Slippage stimato**: colonna `slippage_est` in `trades` è popolata e coincide numericamente con `cost_usd` per tutti gli 8 trade chiusi (stesso valore) — verificare se è un artefatto di calcolo (slippage stimato = costo totale?) o intenzionale; non ho approfondito la formula di costo in questa sessione.

**PnL per strategia**: 100% del PnL realizzato del 07-15 è S4 (i trade S1 aperti quel giorno non si sono ancora chiusi). Non posso attribuire un PnL "S1 del giorno" perché nessuna posizione S1 aperta il 07-15 è stata chiusa lo stesso giorno.

**Confidenza PnL: High** per il realizzato (numeri DB, cross-check con `/api/orders` fill price), **Medium-Low** per il non realizzato (dipende da prezzo corrente, non da un time-anchor 07-15).

---

## 9. Analisi Correttezza Buy/Sell

| Check | Esito | Evidenza |
|---|---|---|
| BUY generati solo se consentiti (no pyramiding) | **PASS** | `P0-05` verificato nel codice e nei dati: 0 BUY su simboli già in posizione aperta quel giorno |
| SELL/exit generati correttamente per scadenza segnale | **PASS** | 6/8 SELL con motivazione esplicita "signal expired (age > max_age)" o "not driving a position" |
| Stop-loss rispettati | **Non verificato in profondità** | nessun trade chiuso il 07-15 con `exit_reason` legato a stop-loss (`stop_decisions`/`stop_shadow_log` non consultate in questa sessione) |
| Signal flip rispettato | **PASS** | NVDA (17:22, score sceso a -0.020) e IBM (17:22, score sceso a 0.000) chiusi correttamente |
| Max holding / rebalance band | **PASS** (osservato) | nessuna posizione tenuta oltre max_signal_age_hours=4h per S4 senza chiusura o rinnovo segnale |
| Nessun ordine duplicato | **PASS** | 23 `execution_decisions` = 23 ordini Alpaca `filled` con timestamp 07-15 — corrispondenza 1:1 |
| Nessun ordine contrario ravvicinato senza rationale | **PASS con 1 eccezione qualitativa** | MSFT: SELL (14:22, chiusura vecchia posizione per staleness) seguito ~4h15m dopo da BUY (18:37, **nuova** posizione su rationale di sentiment negativo) — la SELL è motivata, la BUY successiva è il bug [DAY-001] |
| Nessun ordine su ticker non consentito | **PASS** | Tutti i simboli sono nel watchlist (`config.WATCHLIST_SYMBOLS`) |
| Nessun ordine fuori orario | **PASS** | Tutti i 23 ordini filled tra 14:07 e 19:37 UTC, dentro la finestra di scheduling |
| Nessun trade su dati stale | **PASS (con 1 violazione di segno, non di staleness)** | Il filtro freshness (max_signal_age_hours=4h) ha funzionato — il segnale MSFT usato (id 3773) aveva 7 minuti, non era stale; il problema è il **segno**, non l'età |
| Nessun trade con output LLM non valido | **PASS** | Tutti i signal_id referenziati esistono e hanno score/confidence numerici validi |
| Nessun trade con circuit breaker attivo | **PASS** | `risk_reports.alerts = []`, nessun breaker innescato |
| Nessun trade su strategia disabilitata | **PASS** | Solo S1 (`supervised_paper`, approved) e S4 (`paper`, approved) hanno operato; S2 (`disabled`) e S7 (`research`, not approved) non hanno generato nulla |
| Paper/live coerente | **PASS** | Tutto paper, nessuna ambiguità |
| Idempotenza su retry Celery | **PASS (verificato indirettamente)** | Meccanismo `SIGNAL_DUPLICATE_SKIP` attivo e loggato in `audit_log` più volte nel giorno (es. IBM signal 3621 skippato 3 volte in cicli successivi, BABA signal 3645 skippato 2 volte) — la protezione anti-doppio-fire ha funzionato |
| Reconciliation ordini↔fill↔posizioni | **PASS** | 100% (23/23) |

**Nota sulla colonna "score" — possibile fonte di falsi positivi da evitare**: `trades.score` / `execution_decisions.score` è il **peso di portafoglio** (es. 0.0128 = 1.28% NAV), NON lo score di sentiment (confermato in `src/store/pg_store.py:822-843`, docstring esplicita "Portfolio allocation weight"). Lo score di sentiment vero è in `signal_score`/`trades.signal_score`, popolato solo per trade S4. Controllare "score < 0.05 → anomalia" sulla colonna sbagliata avrebbe prodotto 8 falsi positivi (tutti i trade S1). Verificato con la colonna corretta: **nessun trade S4 con |signal_score| < 0.1** (soglia minima configurata in `S4Config.min_score`).

---

## 10. Anomalie Trovate

### [DAY-001] BUY generato su segnale di sentiment negativo (long-only violato)

- **Tipo**: Bug
- **Area**: Signal / Orders
- **Evidenza**:
  - file/log/tabella: `sentiment_signals` (id 3770, 3773), `execution_decisions` (id 2871), `trades` (id 347), `portfolio_cycles.final_orders` (cycle id 456), `src/strategies/s4/ranking.py:155`
  - timestamp: segnali 2026-07-15 18:30:16 e 18:30:50 UTC; decisione/fill 18:37:00–18:37:08 UTC
  - snippet/query:
    ```
    id=3770 MSFT +0.165 ensemble:glm-5.2:cloud+gpt-oss:20b-cloud generated_at=18:30:16
    id=3773 MSFT -0.110 ensemble:gpt-oss:20b-cloud (solo)         generated_at=18:30:50
    execution_decisions id=2871: decision=BUY, signal_score=-0.110, score(peso)=0.05,
      reason="S4 news-driven: sentiment -0.110 ... portfolio weight 5.0%."
    trades id=347: MSFT, entry_notional=3077.55, entry_price=396.9, tuttora aperta
    ranking.py:154-157: "strength = sig.score ... if strength <= 0: continue  # long-only: skip neutral or net-negative signals"
    ```
  - query SQL usate per riprodurre: vedi Appendice A in fondo al documento.
- **Descrizione**: Il ranker S4 (`CrossSectionalRanker._filter_and_deduplicate`) è esplicitamente long-only e scarta ogni segnale con score ≤ 0. La query che alimenta il ciclo di portfolio (`fetch_signals_for_cycle`, `DISTINCT ON (symbol) ... ORDER BY fallback_used ASC, generated_at DESC`) seleziona, per MSFT, l'ultimo segnale generato entro la finestra di freschezza — che in questo caso era quello negativo (id 3773, generato 34 secondi dopo il positivo id 3770). Secondo la logica del codice attuale, questo avrebbe dovuto escludere MSFT dai candidati del ciclo; invece `portfolio_cycles.final_orders` mostra una `CombinedOrder` MSFT BUY con `strategy_id='merged'` e peso 5% (identico al peso di MMM, l'altro simbolo selezionato quel ciclo, coerente con bucket 10%/2 simboli) — prova che il ranker **ha effettivamente incluso MSFT tra i selezionati**, non solo che il testo di motivazione ha citato il segnale sbagliato. Non sono riuscito a determinare con certezza (in modalità read-only, senza rieseguire la pipeline) il meccanismo esatto — l'ipotesi più probabile è una race condition innescata da due segnali quasi simultanei e di segno opposto sullo stesso simbolo entro la stessa finestra di fetch, ma serve una riproduzione controllata per confermare (vedi Azione consigliata).
- **Impatto**: Un ordine BUY reale da $3,077.55 è stato piazzato (ed eseguito, paper) in diretta contraddizione con il proprio segnale dichiarato. È esattamente la classe di errore che CLAUDE.md definisce worst-case per la ticker resolution ("a wrong ticker/direction is the worst-case error") — qui non è un ticker sbagliato ma una **direzione sbagliata rispetto al proprio segnale**, concettualmente equivalente in termini di rischio di fiducia nel sistema. Al momento della query (07-16) il trade è in profitto (+$16.28) per puro movimento di prezzo favorevole — **non è una giustificazione**: per la regola esplicita del task, un trade può guadagnare ed essere comunque funzionalmente sbagliato.
- **Severità**: **Critical**
- **Confidenza**: **High** sull'osservazione (dati DB inequivocabili, riproducibili con le query in Appendice A); **Medium** sulla causa radice esatta (race condition sospettata, non confermata da esecuzione controllata).
- **Azione consigliata**: Aprire un ticket per riprodurre in un test isolato: caricare l'esatto set di `sentiment_signals` di MSFT delle 18:30 del 07-15 (già persistito in DB) in `NewsDrivenTactical.compute_target_weights` e verificare passo-passo se il ranker lo esclude (come dovrebbe) o lo include (bug confermato). Se confermato, il fix è probabilmente nella query SQL `_FETCH_SIGNALS_FOR_CYCLE` o nella cache/istanza di `signals_df` usata dall'orchestrator per quel ciclo specifico. **Non ho applicato alcuna patch** (fuori scope di questa sessione read-only).
- **Test/monitor consigliato**: (1) un test di non-regressione che inietti due `SentimentResult` per lo stesso simbolo con segni opposti a pochi secondi di distanza e verifichi che il ranker selezioni coerentemente in base all'ultimo segnale E che quel segnale rispetti il filtro long-only; (2) un alert operativo real-time: "BUY generato con `signal_score < 0`" — query diretta (vedi Appendice A) eseguibile come check post-ciclo, zero falsi positivi attesi (il filtro long-only dovrebbe rendere questo insieme sempre vuoto).

### [DAY-002] `/api/orders` restituisce `qty:"None"` per tutti gli ordini BUY a notional

- **Tipo**: Bug
- **Area**: Data / Orders (API)
- **Evidenza**:
  - file/log/tabella: `src/api/routes/trading.py:76` (`"qty": str(o.qty)`)
  - timestamp: riscontrato su 180/300 ordini campionati da `/api/orders?limit=300` (tutti i BUY)
  - snippet: `{"id": "faef5749-...", "symbol": "MSFT", "side": "buy", "qty": "None", "filled_avg_price": "396.9", ...}`
- **Descrizione**: Gli ordini BUY di questo sistema sono piazzati a Alpaca per **notional** (importo in $), non per quantità di azioni. L'oggetto `Order` di Alpaca in questo caso ha `o.qty = None` e la quantità effettivamente eseguita è in `o.filled_qty`. Il codice legge `o.qty` invece di `o.filled_qty`, producendo la stringa letterale `"None"` invece del numero reale di azioni comprate.
- **Impatto**: Basso per il trading (la quantità reale è comunque presente e corretta in `trades.qty`), ma l'endpoint `/api/orders` — usato per audit/frontend — è inaffidabile per qualunque consumer che tenti di leggere `qty` su un ordine BUY (riceverebbe la stringa `"None"`, non `null`/`0`, il che può anche rompere silenziosamente un parser numerico lato frontend).
- **Severità**: Medium
- **Confidenza**: High
- **Azione consigliata**: In `get_orders()` (trading.py:76), usare `o.filled_qty if o.filled_qty is not None else o.qty` invece di `o.qty` da solo.
- **Test/monitor consigliato**: Test di contratto sull'endpoint `/api/orders` che verifichi che nessuna riga con `status="filled"` abbia `qty` non numerico.

### [DAY-003] `risk_reports.herfindahl_index` strutturalmente degenere

- **Tipo**: Rischio / Ambiguità
- **Area**: Risk / Frontend
- **Evidenza**:
  - file/log/tabella: `risk_reports` id=33 (2026-07-15 22:30 UTC), `src/portfolio/risk_monitor.py:91-95, 159`
  - snippet: `herfindahl_index = 1.000000`; `_herfindahl(current_weights)` dove `current_weights` sono **pesi per strategia** (S1/S4), non per simbolo
- **Descrizione**: L'HHI è calcolato su `current_weights: dict[str, float]` che a monte (linea 130 del chiamante) rappresenta allocazioni **per strategy_id**, non per posizione/simbolo. Con solo 2 strategie attive (S1, S4) e — verosimilmente — un forte sbilanciamento di peso verso una sola, l'indice tende a 1.0 (concentrazione massima) quasi sempre, indipendentemente da quanto è realmente diversificato il book (che in questa sessione ha 49 posizioni aperte). Il nome della metrica ("Herfindahl-Hirschman Index for concentration") suggerisce concentrazione di portafoglio per titolo, ma misura concentrazione fra 2 sleeve — probabile disallineamento fra intento e implementazione.
- **Impatto**: Nessun impatto sulle decisioni di trading (il valore non alimenta nessun gate/alert attivo — `alerts=[]`), ma rende la metrica nella UI/risk report **non informativa** per chi la legge aspettandosi "concentrazione per titolo".
- **Severità**: Low
- **Confidenza**: Medium (non ho verificato il valore esatto di `current_weights` passato quel giorno, solo la logica del codice e il risultato numerico coerente con l'ipotesi)
- **Azione consigliata**: Chiarire nel nome/doc della metrica cosa realmente misura, oppure aggiungere un secondo HHI per-simbolo se l'intento originale era quello.
- **Test/monitor consigliato**: Unit test su `_herfindahl` con un caso a 2 pesi sbilanciati per documentare il comportamento atteso.

### [DAY-004] Log Docker non disponibili per il giorno analizzato

- **Tipo**: Ambiguità / Rischio (operativo, non del giorno stesso)
- **Area**: Ops
- **Evidenza**: `docker inspect alembic-worker-1 --format '{{.State.StartedAt}}'` → `2026-07-16T12:21:38Z`; `docker compose logs worker-inference --since 48h` → prima riga utile è `2026-07-16 11:43:40`
- **Descrizione**: Tutti i container sono stati ricreati/riavviati il giorno successivo a quello analizzato (motivo probabile: deploy correlato al lavoro recente sul branch `disable-fill-divergence-alert-2026-07-15` o altre modifiche recenti). Questo azzera qualunque log applicativo (INFO/WARNING/ERROR di Celery/FastAPI) per il 2026-07-15. L'intera ricostruzione di questo report si basa su Postgres, che fortunatamente conserva timestamp e dettaglio sufficienti — ma alcune domande richieste dal task (es. "worker restart events" del giorno, latenza esatta delle chiamate Ollama, eventuali eccezioni silenziose non scritte su tabella) **non sono verificabili**.
- **Impatto**: Riduce la confidenza su tutto ciò che non è persistito esplicitamente in una tabella (in particolare: eccezioni gestite con solo `log.warning(...)` e nessuna riga DB, retry Celery non andati a buon fine, latenza per-chiamata Ollama).
- **Severità**: Medium (rischio di audit, non di trading)
- **Confidenza**: High
- **Azione consigliata**: Configurare log shipping persistente (es. verso file montato su volume, o verso un log aggregator) indipendente dal ciclo di vita dei container, così un riavvio non cancella la storia operativa.
- **Test/monitor consigliato**: Alert se un container di produzione ha uptime < 24h senza un deploy tracciato corrispondente.

### [DAY-005] Blackout Ollama transitorio (18:45:02–18:45:06 UTC) — assorbito correttamente

- **Tipo**: Corretto (comportamento di guardrail funzionante, non un'anomalia da correggere)
- **Area**: LLM / Ops
- **Evidenza**: `sentiment_signals` con `reasoning='FinBERT fallback (Ollama timeout)'`, 12 righe, tutte con `generated_at` fra 18:45:02.350633 e 18:45:06.687834 (stesso batch)
- **Descrizione**: Un intero batch di 12 articoli ha subito timeout Ollama simultaneo; il fallback deterministico FinBERT è scattato correttamente per tutti e 12 senza bloccare il ciclo successivo (alle 19:00 e 19:15 l'ensemble torna a rispondere normalmente). Nessun impatto su trading (i segnali fallback restano soggetti alle stesse soglie).
- **Impatto**: Nessuno — guardrail ha funzionato come da CLAUDE.md ("When LLM ensemble variance is high or timeout occurs, fall back to deterministic indicators... Never block order execution").
- **Severità**: Low (informativo)
- **Confidenza**: High
- **Azione consigliata**: Nessuna azione correttiva necessaria; monitorare se la frequenza di questi micro-blackout aumenta (vedi §16 per stima oraria).
- **Test/monitor consigliato**: Alert se `consecutive_fallback` (in `fallback_counters`) supera una soglia (es. 2 cicli consecutivi al 100% fallback) — la tabella esiste già e sembra popolata correttamente.

### [DAY-006] Tasso di fallback ensemble elevato (51.5%) — problema noto, non peggiorato

- **Tipo**: Rischio (pre-esistente)
- **Area**: LLM / Signal
- **Evidenza**: 106/206 segnali del 07-15 in fallback FinBERT (94 per divergenza, 12 per timeout)
- **Descrizione**: Il 45.6% dei segnali del giorno è finito in fallback per pura divergenza fra glm-5.2 e gpt-oss (non per errore tecnico). Questo è un problema già tracciato in sessioni precedenti (rebalance soglia 0.30→0.40 il 07-11 giudicato inefficace, fallback storicamente 70-86%). Il valore di oggi (51.5% complessivo) è **migliore** della baseline storica ma resta strutturalmente alto.
- **Impatto**: Ogni segnale in fallback usa FinBERT (confidence tipicamente più bassa, nessun ragionamento DK-CoT) invece dell'ensemble LLM — riduce la qualità/informativeness media del segnale, ma non introduce direttamente bug di correttezza (il flusso downstream tratta FinBERT come una fonte di score legittima con le sue soglie).
- **Severità**: Medium (non un'anomalia del 07-15 specificamente, ma degna di menzione per contestualizzare le metriche del giorno)
- **Confidenza**: High
- **Azione consigliata**: Nessuna nuova azione in questa sessione — problema già in carico al programma R&D del progetto (vedi memoria di progetto "Ensemble Divergence Order Drought").
- **Test/monitor consigliato**: Dashboard giornaliera del tasso di fallback per causale (divergenza vs timeout) — sembra già misurabile con la query usata in questo report.

### [DAY-007] Gap di copertura news/sentiment nei primi 30 minuti di mercato (13:30–14:00 UTC)

- **Tipo**: Ambiguità
- **Area**: News / Ops
- **Evidenza**: `celery_app.py:69` (`crontab(minute="*/15", hour="14-21", ...)`) per sentiment worker e ingest; market open reference 13:30 UTC
- **Descrizione**: L'ingest news e il sentiment worker sono schedulati per partire alle 14:00 UTC, 30 minuti dopo l'apertura di mercato (13:30 UTC). Le news pubblicate in quella finestra (12 osservate il 07-15, 13:11–13:29) vengono comunque ingerite al primo giro utile (14:00-14:01), quindi non sono perse — ma il segnale di sentiment su eventuali notizie "hot" dei primi 30 minuti arriva con ritardo strutturale.
- **Impatto**: Basso nella pratica osservata (nessuna notizia critica sembra essere stata persa quel giorno), ma è un gap di design esplicito, non documentato come tale nei commenti del codice (che parlano di "market hours 9am-4pm ET" senza notare lo scarto di 30 min rispetto all'apertura reale).
- **Severità**: Low
- **Confidenza**: High
- **Azione consigliata**: Decidere esplicitamente se anticipare l'ingest a 13:30 UTC o documentare il gap come accettato.
- **Test/monitor consigliato**: Nessuno specifico necessario oltre a tenere il commento del codice allineato al comportamento reale.

### [DAY-008] `portfolio_cycles.orders_count` non rappresenta ordini realmente inviati

- **Tipo**: Ambiguità
- **Area**: Orders / Frontend
- **Evidenza**: `portfolio_cycles` mostra 44-50 `orders_count`/cicli (~1080 nel giorno) vs 23 `execution_decisions` effettive
- **Descrizione**: Il campo `final_orders`/`orders_count` in `portfolio_cycles` rappresenta l'output grezzo del combinatore (post delta ≥2%, post enforcement rischio), **prima** del filtro no-pyramiding e idempotenza applicato in `portfolio_scheduler.py`. La stragrande maggioranza (~98%) di questi "ordini" sono ricalcoli di ribilanciamento per posizioni S1 già aperte che vengono scartati. Se qualcuno legge `orders_count` come "ordini piazzati quel ciclo" senza conoscere questo filtro a valle, sovrastima drasticamente l'attività di trading reale.
- **Impatto**: Rischio di misinterpretazione in dashboard/report che usano `orders_count` come proxy di attività.
- **Severità**: Low
- **Confidenza**: High
- **Azione consigliata**: Rinominare o documentare chiaramente `orders_count` come "candidati pre-filtro pyramiding", ed esporre separatamente il conteggio di `execution_decisions` reali per ciclo.
- **Test/monitor consigliato**: Nessuno specifico; nota di documentazione sufficiente.

---

## 11. False Positive / Aree Risultate Corrette

- **Score < 0.05 → falso allarme evitato**: i 7 trade S1 con `score`≈0.0128 NON sono violazioni di soglia sentiment — quella colonna è il peso di portafoglio per i trade S1, non uno score LLM (vedi §9). Nessun trade S4 ha violato la soglia minima reale (`min_score=0.1` su `signal_score`).
- **NVDA e IBM SELL "improvvisi"**: a un primo sguardo sembrano round-trip sospetti (BUY 14:52/14:37, SELL 16:37/17:22, cioè 1h45m/2h45m dopo), ma sono **corretti**: il segnale S4 è decaduto sotto soglia (NVDA: +0.17→-0.02; IBM: +0.165→0.000) entro la finestra di freschezza di 4h, e la strategia ha chiuso coerentemente per signal-flip. Comportamento by-design, non un bug.
- **MSFT vecchia posizione chiusa 14:22 + MSFT nuova posizione aperta 18:37**: non è un roundtrip anomalo sullo stesso trade — sono due posizioni distinte (trade #324 chiuso per staleness da un segnale del 07-13; trade #347 aperto da un segnale nuovo del 07-15). La SELL delle 14:22 è corretta; solo la BUY delle 18:37 è il problema ([DAY-001]).
- **Duplicati/anti-doppio-fire funzionante**: `audit_log` mostra `SIGNAL_DUPLICATE_SKIP` scattare correttamente più volte (IBM signal 3621 skippato 3 volte, BABA signal 3645 skippato 2 volte) — l'idempotenza Celery-safe funziona come da design.
- **Nessun duplicato cross-provider, nessun timestamp futuro, nessun buco di ingest** — tutti i controlli specifici della Fase 3 sono passati puliti.
- **Nessuna pyramiding**: 0 violazioni della regola "1 posizione per simbolo" osservate.
- **Paper/live**: nessuna ambiguità, tutto correttamente isolato in paper.

---

## 12. Dati Mancanti o Non Accessibili

| Dato mancante | Motivo | Query/azione che servirebbe |
|---|---|---|
| Log applicativi Celery/FastAPI del 07-15 | Container riavviati il 07-16 12:21 UTC | Log shipping persistente (vedi [DAY-004]) |
| Latenza per-chiamata Ollama (solo conteggi/esiti disponibili) | Non persistita in tabella, solo nei log assenti | Aggiungere colonna `latency_ms` a `llm_responses` |
| Prezzo di chiusura ufficiale del 07-15 per calcolare "rendimento del giorno" sulle posizioni ancora aperte | Solo prezzo live (07-16) disponibile via `/api/positions` | Query a un market-data snapshot storico (es. Alpaca historical bars EOD 07-15) |
| Dettaglio stop-loss (`stop_decisions`, `stop_shadow_log`) per il 07-15 | Non consultate in questa sessione per limiti di tempo | `SELECT * FROM stop_decisions WHERE ... 2026-07-15` |
| Formula esatta di `slippage_est`/`cost_usd` (risultano identici per tutti gli 8 trade chiusi) | Non approfondito il codice di costo in questa sessione | Leggere `src/costs/*.py` |
| Conferma se il bug [DAY-001] è una race condition o un altro meccanismo | Richiederebbe eseguire il ranker in isolamento con i dati storici — non permesso in modalità read-only | Test unitario dedicato (vedi azione consigliata [DAY-001]) |

---

## 13. Raccomandazioni Immediate

1. **Riprodurre e correggere [DAY-001]** con priorità alta: è una violazione diretta dell'invariante long-only, isolata ma potenzialmente ricorrente sotto condizioni simili (due segnali di segno opposto ravvicinati sullo stesso simbolo).
2. Fixare il bug `qty:"None"` in `/api/orders` ([DAY-002]) — patch a una riga, basso rischio.
3. Chiarire/rinominare `herfindahl_index` ([DAY-003]) o calcolarlo anche per-simbolo.
4. Impostare log persistence per i container di produzione, indipendente dai riavvii ([DAY-004]).

## 14. Test o Monitor da Aggiungere

1. Check post-ciclo: query automatica "esiste una `execution_decisions` con `decision='BUY'` e `signal_score < 0`?" → deve essere sempre 0 righe; se non lo è, alert immediato (query pronta in Appendice A).
2. Test di non-regressione sul ranker S4 con segnali contraddittori ravvicinati per lo stesso simbolo (vedi [DAY-001]).
3. Contract test su `/api/orders`: nessun campo numerico deve arrivare come stringa `"None"`.
4. Alert su `consecutive_fallback` (tabella già esistente, verificarne l'uso attivo).
5. Dashboard giornaliera fallback-rate per causale (divergenza vs timeout).

## 15. Ticket Tecnici Suggeriti (solo descrizione, nessuna patch applicata)

- **TICKET-A (Critical)**: Investigare e correggere la selezione segnale S4 quando esistono due `sentiment_signals` per lo stesso simbolo con segno opposto entro la stessa finestra di fetch di un ciclo di portfolio — riferimento incidente MSFT 2026-07-15 18:37 UTC, trade #347.
- **TICKET-B (Medium)**: Fix `qty:"None"` in `GET /api/orders` (`src/api/routes/trading.py:76`) — usare `filled_qty` con fallback a `qty`.
- **TICKET-C (Low)**: Chiarire semantica di `risk_reports.herfindahl_index` (per-strategia vs per-simbolo) e aggiornare naming/doc o aggiungere metrica per-simbolo.
- **TICKET-D (Medium, Ops)**: Log shipping persistente per i container Celery/FastAPI, indipendente dal ciclo di vita del container.
- **TICKET-E (Low)**: Rinominare/documentare `portfolio_cycles.orders_count`/`final_orders` come "candidati pre-filtro", non "ordini inviati".

---

## 16. Stato Sistema

| Metrica | Valore |
|---|---|
| Ollama up/down | 1 blackout transitorio, 18:45:02–18:45:06 UTC (12 chiamate consecutive in timeout nello stesso batch), auto-risolto entro il ciclo successivo (15 minuti dopo). Nessun altro downtime rilevabile dai dati disponibili. |
| Downtime stimato Ollama | ≤ 15 minuti (durata di un ciclo sentiment worker), su una finestra operativa di 7h (14:00-21:00 UTC) = **<4% della giornata operativa** |
| FinBERT fallback rate (% segnali) | **51.5%** (106/206) — 45.6% per divergenza ensemble, 5.8% per timeout |
| Worker restart events (07-15) | **Non verificabile** — nessun log disponibile per quel giorno (vedi [DAY-004]); i container attuali risultano avviati il 07-16 12:21 UTC, quindi qualunque restart del 07-15 non è più tracciabile via Docker |
| LLM spend del giorno | $0.093 (47,361 token input, 7,026 output) — ben sotto budget, `budget_exhausted=false` |
| Circuit breaker | Mai attivato (0 alert in `risk_reports`) |
| Strategie attive | S1 (`supervised_paper`, approved), S4 (`paper`, approved). S2 disabled, S7 research/not-approved — nessuna delle due ha operato |

---

## Appendice A — Query di riferimento per riprodurre [DAY-001]

```sql
-- Segnali MSFT contraddittori del 07-15 18:30
SELECT id, symbol, score, confidence, model_id, fallback_used, generated_at
FROM sentiment_signals WHERE symbol='MSFT'
  AND generated_at BETWEEN '2026-07-15 18:25:00+00' AND '2026-07-15 18:40:00+00';

-- Decisione BUY risultante con segno sbagliato
SELECT id, tick_time, symbol, signal_score, score, decision, order_id, reason
FROM execution_decisions
WHERE tick_time = '2026-07-15 18:37:00.588906+00' AND symbol='MSFT';

-- Check generale: qualunque BUY storico con signal_score negativo (dovrebbe essere sempre vuoto)
SELECT tick_time, symbol, signal_score, decision
FROM execution_decisions
WHERE decision='BUY' AND signal_score < 0
ORDER BY tick_time;

-- Ordine grezzo del combinatore per quel ciclo (conferma peso 5% = bucket S4 10%/2 simboli)
SELECT final_orders FROM portfolio_cycles WHERE id = 456;
```
