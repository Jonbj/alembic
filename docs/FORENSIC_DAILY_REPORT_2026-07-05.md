# Forensic Daily Report — 2026-07-05 (Alembic ATS)

**Analista**: Trading Systems Forensic Analyst + Senior Backend Engineer + Quant Operations Reviewer (sessione autonoma, read-only)
**Data generazione**: 2026-07-06, ~13:00 UTC
**Timezone operativo**: UTC, confermato in codice (`src/workers/celery_app.py:51`, `timezone="UTC"`) — nessuna ambiguità.
**Metodologia**: analisi diretta (SQL/API/log/codice) + 3 sub-agent paralleli in background su domini indipendenti (news/LLM, segnali→ordini, ops/incident forensics). Tutti i comandi eseguiti in modalità read-only; nessun ordine, nessun commit, nessun restart, nessuna pipeline rieseguita.

---

## 1. Executive Summary

Il 2026-07-05 è una **domenica**: `celery_app.py` gate esplicitamente `sentiment-worker`, `run-news-ingestion`, `run-alpaca-ingestion`, `run-execution`, `portfolio-cycle` a `day_of_week="1-5"`. Zero righe in `news_log`, `sentiment_signals`, `llm_responses`, `execution_decisions`, `trades` quel giorno è **comportamento corretto**, non un'anomalia. Gli unici eventi del 07-05 sono job di batch/monitoraggio (decay-monitor, risk-monitor, forward-return-worker) che girano 7/7.

La vera notizia della giornata è che quei job di monitoraggio hanno emesso **6 alert CRITICAL** (IC e Sharpe di S1/S2/S4 crollati) basati su dati che risalgono a **prima** del gap, perché la pipeline di trading si è fermata silenziosamente **giovedì 2026-07-02 19:52 UTC** — un giorno di mercato intero (venerdì 07-03) più il weekend senza una sola decisione o ordine, mentre generazione news/segnali è proseguita fino a venerdì 21:30. Root cause non dimostrabile con certezza: i log dei container della finestra critica sono stati distrutti da un redeploy legittimo (fix NAV) avvenuto sabato 07-04 09:55 UTC, ma un forte indizio circostanziale (NAV negativo/esposizione 100% auto-correttasi 1 minuto prima del redeploy) punta a un problema di lettura stato-account Alpaca.

Indipendentemente dal gap, l'analisi della finestra attiva (06-29→07-03) ha trovato **due bug critici distinti**: (1) una news GDELT vecchia di 14 giorni è stata scorata come fresca e ha generato un BUY live su MU senza alcun filtro di staleness attivo; (2) l'output raw dei modelli LLM viene scartato ogni volta che l'ensemble va in fallback, rendendo non verificabile la causa reale del **54-86%/giorno** di fallback FinBERT (il "fallback" è la maggioranza, non l'eccezione). Nessun ordine live, nessuna violazione paper/live, nessun kill-switch attivo, nessun pyramiding.

**In breve**: 2026-07-05 di per sé è "vuoto e corretto"; il sistema nel suo complesso ha un'interruzione operativa non allertata di ~2.5 giorni immediatamente a monte, ancora non riconciliata al momento di questa analisi (le prime esecuzioni schedulate successive al redeploy partono oggi 07-06 alle 14:00 UTC, dopo la chiusura di questo report).

---

## 2. Verdict Finale

# **ANOMALIE SIGNIFICATIVE**

(non "processo non affidabile": i controlli di sicurezza — paper mode, kill-switch, idempotenza lock, niente pyramiding, niente SELL con sentiment positivo — hanno tutti retto; ma un'interruzione multi-giorno della pipeline decisionale non allertata, un bug di staleness che ha prodotto un trade live, e una perdita di audit trail sui fallback LLM sono anomalie sostanziali che richiedono remediation prima della prossima fase.)

---

## 3. Timeline del 2026-07-05 (UTC)

| Ora | Componente | Evento | Stato | Fonte |
|---|---|---|---|---|
| 00:00–13:59 | tutti i worker pipeline | Nessuna esecuzione — gate `day_of_week="1-5"` (domenica) | Atteso | `celery_app.py:65-231` |
| 03:00 | `performance.run_daily_report` (gira 7/7) | Report giornaliero inviato via Telegram, "Overall IC: 0.2902, ICIR: 5.680", "Reconciled 0 trade fill(s)" | OK (dati stale, nessun nuovo fill da riconciliare) | log `worker-1`, 2026-07-05 03:00:00 |
| 03:30 | `retention.run_retention_sweep` (7/7) | 0 righe eliminate (news_log>180gg, llm_responses>365gg) | OK | log `worker-1`, 03:30:00 |
| 04:30 | `performance.run_drift_detection` (domenica 04:30) | "Drift alerts sent: 2" via Telegram | ⚠️ Warning (contenuto non recuperabile, solo Telegram) | log `worker-1`, 04:30:00 |
| 05:00 | `check_suggestion_expiry` (7/7) | No-op | OK | log `worker-1`, 05:00:00 |
| 06:00–20:59 | tutti i worker pipeline | Nessuna esecuzione (gate weekday) | Atteso | — |
| 21:00 | `decay_monitor_task.run_decay_check` (7/7) | **6 alert CRITICAL**: IC e Sharpe di S1/S2/S4 tutti in CRITICAL (vedi §9/§10) | 🔴 CRITICAL | `decay_reports` id 325-336; log `worker-1` 21:00:00 |
| 21:00–21:59 | — | Nessuna attività pipeline core | Atteso (weekend) | `news_log`/`sentiment_signals`/`execution_decisions`: 0 righe 07-05 |
| 22:00 | `performance.run_forward_return_worker` (7/7) | "479 signals to process", "updated=95 skipped=384 errors=0" — 33 warning "subscription does not permit querying recent SIP data" (Alpaca free-tier IEX vs SIP, noto) | OK (limite dati noto) | log `worker-1` 22:00:00-22:00:09 |
| 22:30 | `risk_monitor_task.compute_risk_report` (7/7) | `risk_reports` id=23: NAV=110,307.36, exposure=5.70%, HHI=1.0, drawdown=5.45%, 0 alert | OK — valori tornati normali (vedi §12 per il confronto con 07-02/07-03 anomali) | `risk_reports` id 23 |
| 22:45 | `performance.run_counterfactual_worker` (7/7) | "No SKIP decisions pending counterfactual" | OK (nessuna nuova decisione da valutare, coerente col gap) | log `worker-1` 22:45:00 |
| continuo | `telegram_poller.poll_telegram_updates` | Poll ogni 5s, ~36.458 invocazioni osservate dal 07-04 09:55 a oggi | OK | beat log |

**Nota sul gap a monte (contesto obbligatorio per interpretare la giornata)**: l'ultima riga in `portfolio_cycles`/`execution_decisions`/`trades` è **2026-07-02 19:52:00 UTC** (giovedì). `news_log`/`sentiment_signals` sono proseguiti fino a **2026-07-03 21:30 UTC** (venerdì, 147 segnali quel giorno). Il sabato 2026-07-04 09:55:00 UTC tutti e 5 i container applicativi (`worker`, `worker-inference`, `beat`, `api`, `frontend`) sono stati ricreati (deploy, non crash — vedi §8). Da allora fino all'orario di questa analisi (07-06 ~13:00 UTC) non si è ancora verificata la prima finestra schedulata utile (14:00-21:00 UTC, lun-ven) per verificare se la pipeline core è tornata operativa.

---

## 4. Tabella News Ingest (finestra attiva 2026-06-29 → 2026-07-03; 2026-07-05 = 0 righe, confermato)

### Per fonte/giorno (righe reali in `news_log`)

| day | alpaca_benzinga | gdelt_gkg | marketaux | cnbc/rss |
|---|---|---|---|---|
| 06-29 | 38 | 41 | 6 | – |
| 06-30 | 87 | 49 | 6 | – |
| 07-01 | 128 | 0 | – | – |
| 07-02 | 92 | 20 | 14 | 1 |
| 07-03 | 56 | 91 | – (disabilitato FIX-01) | – (disabilitato FIX-02) |

`marketaux` disabilitato il 07-03 (FIX-01, 17gg paper evidence: 0/20 winner, -$14.11/trade); RSS disabilitato il 07-03 (FIX-02, 0 righe in 17gg); `finnhub`/`sec_edgar` mai attivi in finestra (shelved/disabled prima). `ingestion_stats_daily` esiste solo dal 07-03 (migrazione 033 same-day, non un buco storico) e conta pull/dedup Redis pre-matching, non righe `news_log` — non confrontare direttamente le due tabelle.

### Per ticker (evidenza di problemi)

| Problema | Evidenza |
|---|---|
| News stale scorata come fresca | 5 item GDELT/MarketAux pubblicati 2026-06-15, fetchati 2026-06-29 (13-14gg di ritardo) — **1 ha generato un trade live** (vedi [DAY-001]) |
| Duplicato cross-source stesso ticker | news_log id 1708 (reflector.com) e 1842 (krmg.com), stesso `content_hash`, ticker MU, 6h58m di distanza — oltre la TTL dedup di 4h → doppio scoring (vedi [DAY-005]) |
| Timestamp futuri | Nessuno trovato (né `published_at`, né `fetched_at`, né `raw_ingested_at`) |
| Ticker NULL/vuoto | Nessuno trovato |
| `discarded_reason` | 100% NULL su tutte le 629 righe finestra — colonna esiste (migrazione 033) ma popolamento (S2-2) non ancora shippato |
| GDELT buco 07-01 | 0 righe quel giorno (alpaca_benzinga normale) — causa non investigata, bassa priorità |

### Ticker resolution (shadow mode, QX-01)

450 righe `news_resolved_entities`: 277 `NO_TRADE_LOW_RESOLUTION_CONFIDENCE`, 173 `NO_TRADE_NOT_TRADABLE`, **0 RESOLVED**. Confidenza mai oltre 0.60 (soglia 0.80): il chiamante (`sentiment.py:620-621`) non passa mai `alias_tickers`/`llm_proposed`, quindi `alias_match` e `llm_agreement` (40% del peso evidenza) non possono mai essere `True` — il gate QX-01 non è calibrabile allo stato attuale (vedi [DAY-004]). Questo è shadow-mode: **non ha bloccato nessun trade** in finestra.

**Confidenza analisi**: Alta per i conteggi/pattern sopra (verificati via SQL diretto); Bassa per la causa del buco GDELT 07-01 (non investigata).

---

## 5. Tabella Performance Modelli LLM (finestra 2026-06-29 → 2026-07-03)

| model_id | n risposte | conf&lt;0.4 (%) | polarity min/max/avg | confidence min/max/avg |
|---|---|---|---|---|
| kimi-k2.6:cloud | 154 | 29 (18.83%) | -0.85 / 0.85 / 0.021 | 0.10 / 1.00 / 0.515 |
| glm-5.2:cloud | 121 | 25 (20.66%) | -0.80 / 0.90 / 0.073 | 0.10 / 0.90 / 0.529 |
| qwen3.5:cloud | 19 | 0 (0%) | -0.70 / 0.85 / 0.129 | 0.35 / 0.95 / 0.721 |

Coppia attiva ruotata nella settimana: kimi+qwen3.5 (06-29) → kimi+glm-5.2 (06-30 in poi), coerente con LOO ICIR rebalancing di CLAUDE.md.

**Formula `score = polarity × confidence`**: verificata esatta su tutte le 658 righe `sentiment_signals` della finestra, 0 violazioni — implementata correttamente in `src/workers/sentiment.py:205,213,244`.

**`ensemble_std`**: min 0.0000, mediana 0.0000, avg 0.0111, max 0.2828 (mai sopra soglia 0.30 — per costruzione, chi diverge troppo diventa fallback e non ha `ensemble_std` salvato). Le 15 righe a std più alto (0.21-0.28) hanno |score| medio **più alto** (0.286) delle righe a basso std (0.093) — **la varianza alta NON viene scontata**: `agreement_weighting` è `False` di default in `src/llm/ensemble.py:191,217-220` (vedi [DAY-006]).

**Tasso di fallback per giorno** (headline finding — il fallback è la maggioranza, non l'eccezione):

| day | segnali totali | fallback | fallback % |
|---|---|---|---|
| 06-29 | 114 | 62 | 54.4% |
| 06-30 | 142 | 120 | 84.5% |
| 07-01 | 128 | 90 | 70.3% |
| 07-02 | 127 | 101 | 79.5% |
| 07-03 | 147 | 127 | 86.4% |

Trend 30gg (Agent C, dal report esistente): 20.3% (06-26) → 54.4% → 84.5% → 70.3% → 79.5% → **86.4%** (07-03) — peggioramento monotono, non un blip isolato. Rate complessivo 30gg: 741/1846 = **40.1%**.

Di 500 fallback in finestra, 493 (98.6%) motivati "FinBERT fallback (ensemble divergence)", solo 7 "Ollama timeout". Ma **`raw_outputs` viene scartato ogni volta che `aggregated is None`** (`sentiment.py:211`) — 0/493 hanno una riga `llm_responses` corrispondente. **Non è verificabile se questi 493 fallback siano vera divergenza di polarity, "entrambi i modelli sotto soglia 0.4 confidence", o vero timeout Ollama** — l'audit trail è distrutto strutturalmente (vedi [DAY-002]).

**Verifiche funzionali richieste**:
- Output validato prima del signal store? **Sì** — `response_schema=LLMSentimentOutput`, output malformati sollevano eccezione e vengono scartati prima dell'aggregazione (`src/llm/ensemble.py:348-362`).
- Ensemble gestisce varianza alta? **No** — vedi `ensemble_std` sopra, `agreement_weighting=False` di default.
- News duplicate pesano più volte? **Sì in un caso confermato** (MU, [DAY-005]); il constraint `unique_signal_per_symbol_time (symbol, generated_at)` non previene questo perché `generated_at` è un timestamp di processing a precisione microsecondo, non una business key.
- Stessa news → segnali multipli? Per lo stesso `news_log_id`: **no** (0 casi in finestra). Per la stessa storia sotto `news_log_id` diverso (fonti diverse): **sì**, vedi sopra.
- Confidence bassa riduce il peso? **Sì per lo score** (formula moltiplicativa verificata), **no per il position-sizing** — i fallback/segnali a bassa concordanza ricevono lo stesso slot di peso discreto (0.05/0.0333/0.025) dei segnali ensemble-concordi (vedi [DAY-009]).
- Modelli chiamati offline/background? **Sì, confermato** — `sentiment-worker` instradato su queue `inference` (`celery_app.py:68-72`), nessuna chiamata sync in `execution.py`/`portfolio_scheduler.py`.
- Rischio hallucination diretto in decisione trading? **Sì, concreto** — vedi [DAY-001] (news stale → trade live).

**Confidenza analisi**: Alta (dati DB + codice letti direttamente).

---

## 6. Tabella Segnali Finali per Ticker (finestra attiva)

Non esiste una tabella "segnale finale per ticker" distinta da `sentiment_signals`/`execution_decisions`; ricostruita da `execution_decisions` (06-29→07-03):

| decision | count | prima occorrenza | ultima occorrenza |
|---|---|---|---|
| BUY | 12 | 2026-06-29 16:22:00 | 2026-07-02 19:52:00 |
| SELL | 14 | 2026-06-29 14:22:00 | 2026-07-02 14:22:01 |
| SKIP_STALE | 413 | 2026-07-01 14:07:34 | 2026-07-02 19:52:06 |
| SKIP_THRESHOLD | 330 | 2026-07-02 14:07:07 | 2026-07-02 19:52:06 |

Nessuna riga `execution_decisions` per il 07-03 nonostante 147 nuovi segnali quel giorno — questo è il cuore del gap operativo (§8/§11). Simboli con posizione aperta al momento dell'analisi (entrate tutte 2026-07-02, mai chiuse per via del gap): **META** (signal_score 0.475), **NOW** (0.35375), **MU** (0.40375) — tutti regime_mult=0.7.

**Confidenza**: Alta.

---

## 7. Tabella Ordini Generati/Eseguiti (finestra attiva)

12 entry + 13 exit in finestra (di cui 4 exit relativi a entry pre-06-29); 3 posizioni **ancora aperte**.

| Verifica | Esito |
|---|---|
| BUY → `execution_decisions` match | 12/12 ✅ |
| SELL/exit → `execution_decisions` match | 12/13 — **1 eccezione**: trade id=222 (MU, exit 06-29 16:37:01, `exit_reason=sentiment_reversal`) ha un ordine reale filled ma **nessuna riga `execution_decisions`** (vedi [DAY-008]) |
| `order_id` → `/orders` API | Tutti risolvono a ordini reali `status=filled`. Nessun order_id fantasma. |
| Duplicati stesso minuto/simbolo/lato | 0 trovati |
| NO-ORDER (decisione BUY/SELL, order_id NULL) | 0 trovati |
| Roundtrip &lt;30min | **1 trovato**: SPCX SELL 07-01 17:52:00 → BUY 18:07:00 (15min) → SELL 18:22:00 (15min), **stesso signal_score riutilizzato in entrambe le direzioni** (vedi [DAY-007]) |
| Pyramiding (&gt;3 BUY consecutivi) | 0 trovati — max 2 BUY consecutivi per simbolo, sempre con SELL intermedio |
| SELL con sentiment positivo | 0 trovati |
| score&lt;0.05 con ordine generato | 12 righe ma tutte rebalance strutturali a target-weight 0% (chiusura posizione, non segnale debole tradato) — benigno |
| Broker vs ledger drift | **2 SELL** (LLY, XLF, batch 06-29 14:22) filled con `trade_id=None` in `/orders`, nonostante il ledger locale mostrasse quelle posizioni già chiuse 3gg prima — causa non accertata, flag per follow-up separato |

**Reconciliation ordini↔fill↔posizioni**: pulita salvo i due gap sopra (MU 06-29 audit trail; LLY/XLF broker drift).

**Confidenza**: Alta.

---

## 8. Tabella PnL/Rendimento

**Posizioni aperte al momento dell'analisi** (`/api/positions`, mark-to-market live, entrate 2026-07-02):

| Simbolo | Qty | Entry price | Prezzo corrente | Unrealized PnL | Unrealized % |
|---|---|---|---|---|---|
| META | 4.024970557 | 585.86764 | 591.85 | +24.08 | +1.02% |
| MU | 1.637415923 | 964.306 | 1007.438 | +70.63 | +4.47% |
| NOW | 22.096326836 | 106.719095 | 104.68 | -45.06 | -1.91% |
| **Totale** | | | | **+49.65** | |

**Realizzato in finestra (06-29→07-03)**: non ricalcolato in dettaglio da questo audit oltre ai 12 trade chiusi già riconciliati in §7 (`trades.net_pnl`/`gross_pnl` disponibili per query diretta, non estratti riga-per-riga qui — dato disponibile ma non aggregato in questa passata).

**PnL 2026-07-05 specifico**: **non esiste** — zero trade aperti/chiusi quel giorno (nessuna attività di mercato). Non confondere questo con il PnL non realizzato mostrato sopra, che riflette il prezzo di mercato **al momento dell'analisi (07-06)**, non una chiusura al 07-05.

**Slippage/costi**: colonne `slippage_est`, `cost_bps`, `cost_usd`, `spread_cost_bps`, `impact_cost_bps`, `regulatory_cost_usd` esistono in `trades` e sono popolate per i trade chiusi in finestra — non aggregate in questa passata (dato disponibile: `SELECT avg(cost_bps), avg(slippage_est) FROM trades WHERE exit_time BETWEEN '2026-06-29' AND '2026-07-03'`, query non eseguita da nessuno dei 3 sub-agent, raccomandata come follow-up).

**Cosa manca**: aggregazione PnL per strategia (S1 vs S4) — i trade non sono taggati per strategia in modo diretto nella tabella `trades` (serve join con `execution_decisions`/`portfolio_cycles.strategies_run`, non eseguito). Raccomandato come follow-up query.

**Confidenza**: Media (dati grezzi disponibili e verificati, aggregazioni per-strategia/slippage non calcolate in questa passata — dichiarato esplicitamente, non stimato).

---

## 9. Analisi Correttezza Buy/Sell

| Controllo (da SETTIMA FASE) | Esito |
|---|---|
| BUY solo quando consentito | ✅ Nessun BUY con score sotto soglia genuino (i 12 casi score&lt;0.05 sono rebalance strutturali, non trading signal) |
| SELL/exit corretti | ✅ salvo il gap di audit trail MU [DAY-008] (ordine reale, riga decisione mancante) |
| Stop-loss rispettato | Meccanismo esiste (`_stop_loss_breached_symbols()`, `portfolio_scheduler.py:536`) ma **gira dentro `run_portfolio_cycle()`**, la stessa funzione ferma dal 07-02 19:52 — non verificabile se avrebbe scattato durante il gap |
| Signal flip rispettato | ✅ nei casi osservati (nessuna riga con decisione contraria senza rationale) |
| Max holding days | **Non esiste un timer "max holding days" nel codice** (grep su `constraints.py`, strategie S1/S4: nessun risultato) — unico controllo temporale è la freschezza segnale S4 (age&gt;4h), anch'esso dentro `run_portfolio_cycle()` |
| Rebalance band rispettata | ✅ nei cicli osservati (constraints_fired sempre `[]` nella finestra pre-gap) |
| Niente ordini duplicati | ✅ verificato, 0 casi |
| Niente ordini contrari ravvicinati senza rationale | ⚠️ [DAY-007] — stesso signal_score riusato SELL→BUY→SELL in 30min su SPCX |
| Niente ordini su ticker non consentiti | ✅ nessuna evidenza contraria |
| Niente ordini fuori orario | ✅ tutti i trade in finestra 14:00-21:00 UTC, coerente col gate |
| Niente trade se dati stale | ❌ **VIOLATO** — [DAY-001], news 14gg stale ha generato un BUY live |
| Niente trade se LLM output non valido | ✅ (schema validation attiva, output malformati scartati prima dell'aggregazione) |
| Niente trade se circuit breaker attivo | ✅ `killswitch_active`/`system:halted_by_operator` entrambi nil in Redis ora; nessuna evidenza di trigger in finestra |
| Niente trade se strategia disabilitata | ✅ S2 (disabled) non ha generato trade; S1/S4 (approved) sì |
| Paper/live coerente | ✅ confermato — `strategy_lifecycle`: S1=supervised_paper, S4=paper, entrambi approved=true; `ALPACA_BASE_URL=https://paper-api.alpaca.markets`, chiave `PK`-prefix (paper) |
| Idempotenza su retry Celery | ✅ lock Redis con token UUID + Lua atomic-delete (`_CYCLE_LOCK_KEY`, B26-FIX) — design corretto, nessuna doppia esecuzione osservata |
| Reconciliation ordini/fill/posizioni | ✅ salvo i 2 gap già citati (§7) |

**Confidenza**: Alta salvo dove esplicitamente segnata Media/non verificabile.

---

## 10. Anomalie Trovate

### [DAY-001] News stale scorata come fresca ha generato un BUY live

* Tipo: Bug
* Area: News / Signal / Orders
* Evidenza:
  * file/log/tabella: `news_log` id 1228, `sentiment_signals`, `execution_decisions` id 404
  * timestamp: pubblicata 2026-06-15 18:15 UTC, fetchata e scorata 2026-06-29 16:19:06 UTC, BUY eseguito 2026-06-29 16:22:04 UTC (MU)
  * snippet: reason decisione = "sentiment +0.363 (ensemble:kimi-k2.6:cloud+qwen3.5:cloud)"; `discarded_stale` è hardcoded a 0 nel funnel counters (migrazione 033: "no separate discarded_stale counter yet — stays 0 until S2-2")
* Descrizione: una news GDELT/MarketAux vecchia di 14 giorni è stata trattata come notizia fresca (nessun filtro di staleness attivo prima dello scoring LLM), ed è entrata direttamente nella pipeline di decisione producendo un ordine BUY reale.
* Impatto: viola esplicitamente il requisito "niente trade se dati stale"; espone il sistema a segnali basati su eventi già prezzati dal mercato da settimane.
* Severità: Critical
* Confidenza: High
* Azione consigliata: implementare S2-2 (staleness filter pre-LLM, età massima configurabile per fonte, es. GDELT backfill vs realtime) prima di qualunque ulteriore fase live.
* Test/monitor consigliato: alert automatico se `fetched_at - published_at > N ore` per news che raggiungono l'ensemble; test di regressione che verifichi il rifiuto di news con gap età oltre soglia.

### [DAY-002] Audit trail dei fallback LLM distrutto strutturalmente

* Tipo: Bug
* Area: LLM
* Evidenza:
  * file/log/tabella: `src/workers/sentiment.py:180-211`, `llm_responses` (0 righe per 493/500 fallback della finestra)
  * timestamp: tutta la finestra 06-29→07-03
  * snippet: quando `aggregated is None` la funzione ritorna `SentimentResult(...), []` scartando i `raw_outputs` calcolati alla riga 180
* Descrizione: ogni volta che l'ensemble va in fallback (per timeout O per divergenza/bassa confidenza — le due cause non sono distinguibili), i valori polarity/confidence per-modello che hanno causato il fallback vengono buttati via prima di raggiungere `llm_responses`.
* Impatto: il 54-86%/giorno di fallback osservato non è diagnosticabile — non si può confermare né escludere un vero problema Ollama-side vs. semplice sotto-soglia di confidenza dei modelli.
* Severità: Critical
* Confidenza: High
* Azione consigliata: persistere sempre i `raw_outputs` in `llm_responses` (con un flag `used_in_aggregate=false` per i fallback), anche quando il risultato finale è FinBERT.
* Test/monitor consigliato: dashboard che distingua fallback-per-timeout vs fallback-per-confidenza vs fallback-per-divergenza; alert se il tasso di fallback supera una soglia (es. 50%/giorno) per 2 giorni consecutivi.

### [DAY-003] Interruzione silenziosa pipeline decisionale, 2026-07-02 19:52 → almeno 2026-07-06 14:00 (~2.5+ giorni di mercato)

* Tipo: Anomalia
* Area: Orders / Ops
* Evidenza:
  * file/log/tabella: `portfolio_cycles`, `execution_decisions`, `trades` — ultima riga 2026-07-02 19:52:00 UTC in tutte e tre
  * timestamp: gap da 2026-07-02 20:07 UTC (primo tick mancante) fino ad almeno 2026-07-06 13:00 UTC (ora analisi) — copre il resto di giovedì, tutto venerdì 07-03 (32 tick attesi), il weekend (correttamente non schedulato) e la mattina di lunedì 07-06 (non ancora nella finestra 14-21 UTC)
  * snippet: `sentiment_signals` per lo stesso periodo mostra 147 nuovi segnali il 07-03 (worker-inference, queue separata, ha continuato a funzionare)
* Descrizione: `run_portfolio_cycle()`/`run_execution_worker()` (queue `celery` default, container `worker`) hanno smesso di produrre qualunque riga in DB, mentre `sentiment-worker` (queue `inference`, container `worker-inference`) ha continuato regolarmente. La funzione persiste una riga in `portfolio_cycles` solo a fine ciclo completato (`portfolio_scheduler.py`, funzione di persistenza dopo tutta la logica) — un abort in un qualunque pre-flight check (clock Alpaca, account Alpaca, redis kill-switch, prezzo dati, registry strategie) non lascia traccia DB. Root cause non dimostrabile con i dati disponibili: i log container di quella finestra sono stati distrutti da una ricreazione completa dello stack (5 container) il 2026-07-04 09:55:00 UTC — confermato essere un **deploy legittimo** (commit `8784b2da` "fix(risk): real NAV + gross exposure from Alpaca in daily risk report" → build immagine 7s dopo → container up 43s dopo → commit doc "mark resolved" 36s dopo l'avvio), non un crash (RestartCount=0 su tutti). Indizio circostanziale forte ma non conclusivo: `risk_reports` mostra NAV=**-578.52** (valore impossibile) e exposure=100% con alert "exposure exceeds 50%" alle 2026-07-02 22:30 e 2026-07-03 22:30, poi tornato normale (NAV=110,307.36, exposure=5.7%) entro le 2026-07-04 09:54:29 — **un minuto prima** del deploy che ha corretto esattamente quel bug NAV/exposure. Questo suggerisce che una lettura malformata dello stato-account Alpaca possa aver interessato anche il pre-flight `trading_client.get_account()` di `portfolio_scheduler.py`, ma non è verificato: quel percorso di abort (`alpaca_unreachable`) *dovrebbe* mandare un alert Telegram CRITICAL — non recuperabile in questa analisi read-only (nessuna persistenza locale degli alert, solo Telegram).
* Impatto: ~2.5 giorni di mercato senza generazione decisioni/ordini, senza alcun alert DB-visibile che lo segnali chiaramente (dipende dal path di abort, alcuni sono silenziosi — vedi [DAY-010]); le 3 posizioni aperte (META/NOW/MU) sono rimaste esposte senza possibilità di stop-loss/rebalance/signal-flip per tutto il periodo.
* Severità: Critical
* Confidenza: Media (il fatto del gap è Alta confidenza; la causa radice è Media/ipotesi non confermata)
* Azione consigliata: (1) verificare manualmente lo storico Telegram del canale alert per il periodo 07-02 20:00 → 07-03 22:00 per capire quale messaggio di abort (se presente) fu inviato; (2) aggiungere logging esterno persistente (non solo container json-file) così una ricreazione container non distrugga le evidenze; (3) monitor attivo "zero righe portfolio_cycles per N tick attesi durante market hours" con alert indipendente dal path del ciclo stesso.
* Test/monitor consigliato: canary/heartbeat scritto in una tabella separata ad ogni tentativo di ciclo (anche gli abort), indipendente dalla riga `portfolio_cycles` finale; alert se il canary non avanza per &gt;30min durante market hours.

### [DAY-004] Resolver ticker in shadow mode strutturalmente incapace di raggiungere RESOLVED

* Tipo: Bug
* Area: Signal / Data
* Evidenza:
  * file/log/tabella: `src/workers/sentiment.py:620-621`, `src/connectors/ticker_resolver.py:26`, `news_resolved_entities` (450 righe, 0 RESOLVED)
  * timestamp: tutta la finestra osservata
  * snippet: `resolve_and_log_shadow(items_to_process, pg_store)` chiamato senza `alias_tickers` né `llm_proposed`
* Descrizione: `alias_match` (peso 0.25) e `llm_agreement` (peso 0.15) — 40% del peso evidenza del resolver — non possono mai essere `True` perché il chiamante non passa i dati necessari. Confidenza massima osservabile: 0.60, contro soglia 0.80.
* Impatto: il gate QX-01 (misurazione prima di enforcement, richiesto da CLAUDE.md) non può essere calibrato sul golden label set finché questo wiring non viene corretto — il lavoro di raccolta dati shadow in corso è in parte sprecato.
* Severità: High
* Confidenza: High
* Azione consigliata: wire `alias_tickers`/`llm_proposed` nella chiamata da `sentiment.py`, poi ri-raccogliere un periodo di shadow data pulito prima di procedere con QX-01.
* Test/monitor consigliato: test unitario che verifichi che almeno una parte dei casi in un batch sintetico raggiunga `alias_match=True`/`llm_agreement=True` quando i dati sono forniti correttamente.

### [DAY-005] Duplicato cross-source oltre la finestra di dedup (TTL 4h)

* Tipo: Bug
* Area: News
* Evidenza:
  * file/log/tabella: `news_log` id 1708 (reflector.com) e 1842 (krmg.com), `src/connectors/deduplicator.py:22,51,106-122`
  * timestamp: fetch 2026-07-03 14:17:48 e 21:15:55 (6h58m di distanza), ticker MU, stesso `content_hash`
  * snippet: `_DEDUP_TTL_SECONDS` = 4h (riga 22) ma il docstring della classe (riga 51) dichiara "2-hour" — commento disallineato dal codice
* Descrizione: due outlet hanno syndicato lo stesso wrap di mercato AP-style; la seconda copia è arrivata oltre la TTL Redis di dedup ed è stata scorata come evento indipendente, producendo due `sentiment_signals` per lo stesso evento sottostante sullo stesso simbolo.
* Impatto: basso in questo caso specifico (confidence quasi zero, score ~-0.0001), ma il meccanismo è reale e riproducibile — un evento a impatto reale duplicato oltre le 4h peserebbe due volte sul segnale aggregato per quel simbolo/giornata.
* Severità: Medium
* Confidenza: High
* Azione consigliata: allungare la TTL di dedup content-hash o passare a un dedup basato su similarity testuale con finestra più ampia (es. 24h) per notizie di mercato ricorrenti; correggere il docstring.
* Test/monitor consigliato: metrica giornaliera "% sentiment_signals con content_hash duplicato in finestra 24h" come proxy di double-counting residuo.

### [DAY-006] Segnali ad alta divergenza tra modelli non vengono scontati nel peso

* Tipo: Bug (gap rispetto a guardrail CLAUDE.md)
* Area: LLM
* Evidenza:
  * file/log/tabella: `src/llm/ensemble.py:191,217-220`; `sentiment_signals.ensemble_std`
  * timestamp: tutta la finestra
  * snippet: `agreement_weighting=False` di default; le 15 righe a `ensemble_std` più alto (0.21-0.28) hanno |score| medio 0.286 vs 0.093 del resto
* Descrizione: CLAUDE.md richiede "Ensemble variance: ... flag high-variance outputs for human review or discard", ma il meccanismo di sconto per disaccordo esiste nel codice ed è disattivato di default in attesa di validazione QX-01.
* Impatto: segnali dove i modelli sono in forte disaccordo pesano quanto (o più, empiricamente) segnali a basso disaccordo.
* Severità: Medium
* Confidenza: Medium
* Azione consigliata: valutare l'attivazione di `agreement_weighting` con soglia conservativa, oppure documentare esplicitamente che è gated su QX-01 e tracciare la decisione.
* Test/monitor consigliato: backtest A/B con `agreement_weighting` on/off su dati storici prima di abilitarlo in paper.

### [DAY-007] Roundtrip &lt;30min con riutilizzo dello stesso signal_score

* Tipo: Anomalia
* Area: Orders
* Evidenza:
  * file/log/tabella: `execution_decisions`/`trades`, simbolo SPCX
  * timestamp: SELL 2026-07-01 17:52:00.667 → BUY 18:07:00.627 (15.0 min) → SELL 18:22:00.638 (15.0 min)
  * snippet: entrambe le SELL con signal_score identico -0.5733276873322924, entrambe le BUY con +0.18 identico
* Descrizione: lo stesso segnale (stesso score, non un nuovo segnale fresco) è stato riutilizzato su due cicli consecutivi per generare direzioni opposte di trade nell'arco di 30 minuti.
* Impatto: possibile costo di transazione/slippage non necessario se il segnale sottostante non è realmente cambiato tra i due tick.
* Severità: Medium
* Confidenza: High
* Azione consigliata: verificare la logica di refresh/staleness del segnale usato da `run_portfolio_cycle` per SPCX in quello specifico intervallo — capire se un segnale "vecchio" di un ciclo è stato riletto per errore.
* Test/monitor consigliato: alert su roundtrip &lt;30min per lo stesso simbolo con score identico bit-per-bit tra le due decisioni.

### [DAY-008] Scrittura silenziosa fallita per una decisione di exit (sentiment reversal)

* Tipo: Bug
* Area: Orders
* Evidenza:
  * file/log/tabella: `src/workers/portfolio_scheduler.py:1596-1615`; trade id=222 (MU)
  * timestamp: exit 2026-06-29 16:37:01, `exit_reason=sentiment_reversal`
  * snippet: il blocco che scrive `write_execution_decision()` per le sentiment-reversal-sell forzate è in un try/except che logga solo un warning in caso di fallimento — l'ordine è già stato inviato al broker prima di questo blocco
* Descrizione: l'ordine SELL è reale e filled (confermato via `/orders`), ma non esiste alcuna riga `execution_decisions` corrispondente — la scrittura DB della decisione è fallita silenziosamente dopo che l'ordine era già uscito.
* Impatto: buco nell'audit trail per un ordine reale; il pattern gemello il giorno dopo (SPCX) è riuscito, quindi è un fallimento intermittente, non sistemico.
* Severità: Medium
* Confidenza: High
* Azione consigliata: loggare a livello ERROR (non warning) + alert quando la persistenza della decisione fallisce dopo un ordine già inviato; considerare un retry o una coda di riconciliazione per questi casi.
* Test/monitor consigliato: query periodica "trade con decision_id NULL o non risolvibile" come check di integrità referenziale.

### [DAY-009] Segnali fallback/bassa-concordanza non scontati nel position sizing

* Tipo: Anomalia
* Area: Signal / Risk
* Evidenza:
  * file/log/tabella: decisione GS BUY 06-29 16:22, reason "sentiment +0.428 (finbert), portfolio weight 3.3%" — stesso slot di peso di BUY ensemble-concordi nello stesso tick (MU, MS)
  * timestamp: 2026-06-29 16:22
  * snippet: colonna peso assume solo valori discreti {0.05, 0.0333, 0.025} indipendentemente dalla fonte (ensemble vs FinBERT fallback vs singolo modello)
* Descrizione: il position sizing usa slot equal-weight discreti che non distinguono un segnale FinBERT-fallback (o ensemble a singolo modello) da un segnale a doppio-modello concorde — la sola discriminazione di "qualità" del segnale è già incorporata nello `score` (polarity×confidence), non nel sizing.
* Impatto: dato che il 54-86%/giorno dei segnali sono fallback ([DAY-002]/tabella §5), gran parte del portafoglio è dimensionato con la stessa logica di segnali ensemble di alta qualità.
* Severità: Medium
* Confidenza: High
* Azione consigliata: valutare uno sconto esplicito di sizing per segnali `fallback_used=true` o a singolo modello, oltre allo sconto già presente nello score.
* Test/monitor consigliato: backtest comparativo con/senza sconto sizing per fallback.

### [DAY-010] Alert CRITICAL del decay monitor confondono metrica globale-portafoglio con "per strategia"

* Tipo: Ambiguità
* Area: Risk / PnL
* Evidenza:
  * file/log/tabella: `src/workers/decay_monitor_task.py:44-110` (commento esplicito riga 53: "Metrics are pipeline-global (no strategy_id column in the table)"); `decay_reports` id 325-336, 2026-07-05 21:00 UTC
  * timestamp: 2026-07-05 21:00:00
  * snippet: `actual_value` per "ic" (-0.004481854127574997), "sharpe" (-0.8952296748251855), "hit_rate" (0.4329073482428115) e "max_drawdown" (0.054493715596850414) sono **identici bit-per-bit** per S1, S2 **e S4** — solo il `baseline_value` differisce per strategia (hardcoded in `_BASELINES`)
* Descrizione: il decay monitor calcola IC/hit-rate da `sentiment_signals` e Sharpe/drawdown da `portfolio_daily_state` **senza filtro per strategia** (nessuna colonna `strategy_id` in quelle tabelle), poi confronta lo stesso valore aggregato-portafoglio contro la baseline hardcoded di ciascuna strategia. Il risultato: **S2, che è `disabled` e non ha generato un solo trade**, ha comunque ricevuto due alert CRITICAL ("IC dropped 111%", "Sharpe below 50% of baseline") identici a S1/S4.
* Impatto: gli alert Telegram CRITICAL inviati il 07-05 per S1/S2/S4 sono fuorvianti — non misurano il decadimento di ciascuna strategia individualmente, ma il decadimento del portafoglio complessivo etichettato tre volte. Un operatore che leggesse l'alert penserebbe (erroneamente) che tutte e tre le strategie stiano performando ugualmente male in modo indipendente.
* Severità: High
* Confidenza: High (verificato leggendo il codice sorgente e confrontando i valori DB)
* Azione consigliata: (a) sopprimere gli alert decay per strategie `disabled`/non-approved (S2); (b) implementare attribuzione IC/Sharpe realmente per-strategia (serve `strategy_id` propagato in `sentiment_signals`/`portfolio_daily_state`) prima di considerare affidabili questi alert.
* Test/monitor consigliato: test che verifichi `decay_reports.actual_value` differisca tra strategie quando i dati sottostanti differiscono; gate che escluda strategie non-approved dal decay check.

---

## 11. False Positive / Aree Risultate Corrette

* **Weekend gap (2026-07-04/07-05)**: NON è un'anomalia — comportamento corretto per design (`day_of_week="1-5"` in `celery_app.py`).
* **Kill-switch/circuit breaker**: verificato non attivo (`killswitch_active`, `system:halted_by_operator` entrambi nil in Redis); nessuna evidenza abbia mai interrotto il trading per questo motivo nella finestra.
* **Pyramiding**: verificato assente — max 2 BUY consecutivi per simbolo, sempre con SELL intermedio, coerente col design "position manager idempotente" di CLAUDE.md.
* **SELL con sentiment positivo (bug pattern A5)**: verificato assente, 0 casi.
* **Paper/live coerenza**: confermata paper su tutta la linea (config, DB, credenziali Alpaca `PK`-prefix).
* **Validazione schema output LLM**: confermata attiva, output malformati non raggiungono mai l'aggregazione.
* **Formula score = polarity × confidence**: verificata esatta su 658/658 righe, 0 violazioni.
* **Sync LLM calls nel path esecuzione**: verificato assente — rispetta il vincolo "mai nel loop di trading" di CLAUDE.md.
* **Idempotenza lock Celery**: design corretto (token UUID + Lua atomic delete), nessuna doppia esecuzione osservata.
* **Duplicati ordine stesso minuto**: verificato assente, 0 casi (nessuna race condition scheduler rilevata).
* **Restart container del 07-04**: inizialmente sospettato causa del gap; **escluso** come causa diretta (il gap inizia 1.5 giorni prima) e confermato essere un deploy legittimo tracciabile a un commit specifico, non un crash.

---

## 12. Dati Mancanti o Non Accessibili

| Dato | Perché manca | Query/azione che servirebbe |
|---|---|---|
| Log container per la finestra 2026-07-02 18:00 → 2026-07-04 00:00 (root cause esatta del gap) | Distrutti dalla ricreazione container del 07-04 09:55 (log driver `json-file` locale, nessuno shipping esterno) | Nessuna — dato perso in modo permanente. Raccomandato logging esterno persistente per il futuro. |
| Contenuto degli alert Telegram inviati (se presenti) nella finestra del gap | `_fire_alert`/`TelegramNotifier.send_alert` sono fire-and-forget, nessuna persistenza DB | Controllo manuale della cronologia chat del bot Telegram (`TELEGRAM_BOT_TOKEN`) da parte di chi ha accesso — fuori scope read-only di questa analisi |
| Vero tasso di output LLM invalido/malformato per modello | Le eccezioni vengono scartate prima di raggiungere `llm_responses` | Instrumentare `src/llm/ensemble.py` per loggare (non solo scartare) le eccezioni di parsing per modello |
| Causa reale del 54-86%/giorno di fallback (Ollama-down vs sotto-soglia-confidenza vs vera divergenza) | `raw_outputs` scartato su fallback ([DAY-002]) | Fix [DAY-002], poi ri-raccogliere |
| PnL aggregato per strategia (S1 vs S4) nella finestra | Non calcolato in questa passata (richiede join `trades`↔`execution_decisions`↔`portfolio_cycles.strategies_run`) | `SELECT ... FROM trades JOIN execution_decisions ...` — follow-up raccomandato |
| Slippage/costi aggregati nella finestra | Colonne popolate ma non aggregate in questa passata | `SELECT avg(cost_bps), avg(slippage_est) FROM trades WHERE exit_time BETWEEN ...` |
| Causa del buco GDELT (0 righe) il 2026-07-01 | Non investigato (bassa priorità assegnata) | Controllo log ingestion specifico per quel giorno, se recuperabile |
| .env history al momento del redeploy 07-04 | `.env` non è versionato in git | Nessuna — non recuperabile |

---

## 13. Raccomandazioni Immediate

1. **Verificare manualmente la cronologia Telegram** per il periodo 2026-07-02 20:00 → 2026-07-04 09:55 UTC — è l'unica fonte residua che potrebbe rivelare quale (se presente) alert di abort fu effettivamente inviato durante il gap [DAY-003].
2. **Attendere e verificare il primo ciclo utile di oggi (2026-07-06, 14:00 UTC)** per confermare se la pipeline core (`portfolio-cycle`, `run-execution`, `sentiment-worker`) è effettivamente tornata operativa dopo il redeploy — non ancora verificabile al momento di questo report.
3. **Non promuovere ulteriormente nessuna strategia** finché [DAY-001] (staleness filter) e [DAY-002] (audit trail fallback) non sono risolti — sono difetti che minano rispettivamente la sicurezza dei trade e l'auditabilità richiesta.
4. **Sospendere/correggere gli alert decay per S2** (disabled) finché [DAY-010] non è risolto, per evitare fatica da falso allarme sugli operatori.
5. **Implementare logging esterno persistente** (fuori dal ciclo di vita dei container) prima del prossimo deploy, per evitare un'altra perdita di evidenze forensi come quella di questo incidente.

---

## 14. Test o Monitor da Aggiungere

* Canary "portfolio-cycle heartbeat" scritto indipendentemente dal risultato del ciclo (anche sugli abort), con alert se assente per &gt;30min durante market hours [DAY-003].
* Alert su tasso di fallback LLM giornaliero &gt;50% per 2 giorni consecutivi [DAY-002].
* Filtro/alert di staleness pre-scoring per news con gap `fetched_at - published_at` oltre soglia configurabile per fonte [DAY-001].
* Test di integrità referenziale periodico "trade con decision_id non risolvibile" [DAY-008].
* Gate che escluda strategie `disabled`/non-approved dal decay monitor, o implementazione di vera attribuzione per-strategia [DAY-010].
* Metrica "% sentiment_signals con content_hash duplicato in finestra 24h" [DAY-005].
* Test unitario sul wiring `alias_tickers`/`llm_proposed` nel resolver shadow [DAY-004].

---

## 15. Ticket Tecnici Suggeriti

1. **[Critical]** Implementare filtro staleness news pre-LLM (S2-2, già previsto ma non shippato) — chiude [DAY-001].
2. **[Critical]** Persistere sempre `raw_outputs` in `llm_responses` anche sui fallback, con flag di provenienza — chiude [DAY-002].
3. **[Critical]** Logging esterno persistente per i container applicativi (indipendente dal ciclo di vita container) — mitiga la ripetizione di [DAY-003].
4. **[High]** Canary/heartbeat indipendente per `portfolio-cycle` con alert su assenza prolungata durante market hours — mitiga [DAY-003].
5. **[High]** Wire `alias_tickers`/`llm_proposed` nella chiamata shadow resolver — chiude [DAY-004].
6. **[High]** Attribuzione per-strategia reale nel decay monitor (o soppressione alert per strategie disabled) — chiude [DAY-010].
7. **[Medium]** Estendere/rivedere TTL dedup content-hash (attualmente 4h, docstring dice 2h) — chiude [DAY-005] e disallineamento doc/codice.
8. **[Medium]** Valutare abilitazione `agreement_weighting` nell'ensemble dopo backtest A/B — indirizza [DAY-006].
9. **[Medium]** Alzare a ERROR + alert la persistenza fallita di `write_execution_decision()` dopo ordine già inviato — chiude [DAY-008].
10. **[Medium]** Sconto esplicito di position-sizing per segnali fallback/singolo-modello — indirizza [DAY-009].
11. **[Low]** Investigare causa buco GDELT 07-01; correggere query aggregate PnL-per-strategia e slippage come follow-up analitico.

---

## 16. Stato Sistema

* **Ollama (ensemble cloud)**: stato post-restart **non verificabile** — la prima finestra schedulata utile (14:00-21:00 UTC odierno) non si era ancora verificata al momento di questa analisi (13:00 UTC circa). Pre-restart: trend di degrado chiaro e monotono nel tasso di fallback (20.3% → 86.4% in 6 giorni), culminato in una serie di 11 fallback consecutivi il 07-03 tra le 20:17 e le 21:30 UTC — ma la causa esatta (timeout reale vs sotto-soglia-confidenza) non è distinguibile dai dati disponibili ([DAY-002]).
* **FinBERT fallback rate**: **40.1%** sui 30 giorni precedenti (741/1846 segnali); **86.4%** nell'ultimo giorno attivo (07-03) — il fallback è la modalità dominante, non l'eccezione.
* **Worker restart/recreation events**: **1 evento** confermato — ricreazione completa dei 5 container applicativi il 2026-07-04 09:55:00 UTC, identificata come deploy legittimo (commit `8784b2da`, fix NAV/exposure) e non un crash (RestartCount=0 su tutti). Nessuna altra evidenza di restart nei 30 giorni precedenti (attività `sentiment_signals` continua e senza buchi dal 06-15 al 07-03).
* **Container non toccati dal restart**: `postgres` e `redis`, entrambi "up" ininterrottamente da 4 settimane — stato dati/coda sopravvissuto intatto al redeploy applicativo.

---

*Fine report. Nessuna modifica al codice, nessun commit, nessun ordine inviato, nessuna pipeline rieseguita durante questa analisi.*
