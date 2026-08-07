# Forensic Daily Report — 2026-07-14

Generato: sessione autonoma Claude, 2026-07-15. Modalità read-only (Postgres SELECT, `docker compose logs`, lettura codice/config). Nessun ordine inviato, nessun worker avviato, nessuna modifica al sistema.

## 1. Executive Summary

Il 14/07/2026 il sistema ha eseguito 24 cicli di portfolio (ogni 15 min, 14:00–21:52 UTC), generando 27 BUY e 19 SELL, tutti riconciliati 1:1 con `trades` (nessun ordine orfano, nessun NO-ORDER, nessuna duplicazione stesso-minuto). PnL realizzato netto: **-$161.05** su 19 trade chiusi (8 stop_loss legacy -$197.01, 7 portfolio_sell +$31.22, 4 sentiment_reversal +$4.73). Nessun breach di cap/exposure/circuit breaker.

Due problemi materiali: (1) per ~77 minuti (15:30–16:47 UTC) l'ensemble LLM ha girato con la coppia sbagliata (kimi+glm52 invece di glm52+gptoss, bug già noto e in fix), producendo 18 segnali degradati di cui **2 sono diventati trade reali** (NFLX, DIS). (2) Il fallback deterministico FinBERT è scattato sul **53.3%** dei segnali della giornata (146/274), distribuito su tutte le ore di mercato, non un singolo blackout — segnale di instabilità cronica dell'ensemble Ollama, non isolata. Inoltre AAPL ha subito 3 round-trip buy→sell in 90 minuti per conflitto non coordinato tra S1 momentum e il guardrail sentiment_reversal (esito economico neutro/positivo ma churn operativo inutile).

Log dei container worker/worker-inference/beat NON coprono il 14/07 (restart successivi al deploy delle 21:48 UTC dello stesso giorno + un restart odierno) — ricostruzione basata su tabelle Postgres, non su log applicativi. Il token Bearer fornito per le API REST è risultato un JWT non valido; tutti i dati sono stati ricostruiti via query dirette al DB.

## 2. Verdict

**OK con warning.**

Motivazione: nessun malfunzionamento ha causato ordini errati, violazioni di rischio o perdite anomale attribuibili a bug esecutivo. I due problemi materiali (contaminazione ensemble, fallback rate 53%) sono di **qualità del segnale**, non di integrità esecutiva — l'architettura di safety (fallback FinBERT, guardrail sentiment_reversal, riconciliazione ordini/trade, idempotenza) ha funzionato come da design. Il churn su AAPL è un difetto di coordinamento tra strategie da correggere ma a impatto economico trascurabile oggi.

## 3. Timeline 2026-07-14 (UTC)

Timezone: **UTC**, confermato in `src/workers/celery_app.py` (`timezone="UTC", enable_utc=True`). Market hours nominali (da CLAUDE.md/prompt): 13:30–20:00 UTC (EDT, luglio). **Ambiguità**: lo scheduler Celery gira sentiment-worker e GDELT ingestion 14:00–21:00 UTC — 30 min in ritardo all'apertura, 1h oltre la chiusura reale in EDT (vedi [DAY-006]).

| Ora UTC | Evento | Fonte |
|---|---|---|
| 14:00:27 | Reset giornaliero `llm_budget` (nuova riga date=2026-07-14) | `llm_budget` |
| 14:00–21:45 | Sentiment worker attivo, 15 min di cadenza, ingest GDELT+Benzinga in parallelo | `ingestion_stats_daily`, `sentiment_signals` |
| 14:07:01 | Ciclo portfolio #1: 43 ordini, strategie [S1,S4], 15 nuove entry S1 (AMAT, AMD, ARM, ASML, CAT, INTC, MRVL, MU, NOK, SHEL, SOXX, TSM, TXN, VALE, XLK); in parallelo 8 stop_loss su posizioni legacy 07-10 (ERIC, LLY) | `portfolio_cycles`, `trades` |
| 14:22:00 | Stop_loss/portfolio_sell batch: JNJ, MRK stop_loss; SPCX, CVX, BA, DIS portfolio_sell (DIS chiusa per **S4 signal expired**, age 16.9h > max_age 4h) | `execution_decisions` |
| 14:37–17:52 | Ulteriori stop_loss su posizioni legacy 07-10 (XLV, C, GM, CSCO) — nessun parametro vol-scaled (`stop_k`/`stop_floor`/`stop_cap` NULL, posizioni pre-migrazione) | `trades` |
| **15:18–15:20** | Redis `config:sentiment_llm_models` torna a `"all"` (toggle Sidebar, bug noto — vedi memoria progetto); reset manuale a `glm52,gptoss` alle 15:20 (**non risolutivo** — vedi 15:30 sotto) | audit/memoria + osservazione DB |
| **15:30:32–16:47:02** | **Finestra di contaminazione ensemble**: 18 `sentiment_signals` generati con modello `kimi-k2.6:cloud` (solo o in coppia con glm-5.2), NON la coppia live glm52+gptoss. Simboli coinvolti: IBM, CRM, INFY, ORCL, SAP, GS, GOOGL, NFLX, C, DIS, QQQ, AMD, SPY | `sentiment_signals` (vedi [DAY-001]) |
| 15:52:00 | Entry NFLX e NVDA (S4) — **NFLX driven da segnale contaminato** (id 3392, score 0.1875, model `ensemble:kimi-k2.6:cloud+glm-5.2:cloud`) | `trades`, `sentiment_signals` |
| 16:07:00 | Entry DIS (S4) — **driven da segnale contaminato** (id 3403, score 0.362, reason cita esplicitamente `ensemble:kimi-k2.6:cloud+glm-5.2:cloud`) | `execution_decisions.reason` |
| 16:07–16:22 | 2× `SIGNAL_DUPLICATE_SKIP` audit su NVDA (signal_id 3393) — idempotenza corretta, nessun doppio ordine | `audit_log` |
| 16:52:00 | SHEL chiusa: **S4 signal expired** (age 20.9h, score stale +0.045) — posizione era stata aperta da S1 alle 14:07, ma chiusa da logica di decadimento S4 (vedi [DAY-004], ambiguità di attribuzione) | `execution_decisions` |
| 17:07:00 | Entry MSFT (S4, signal_score 0.08) | `trades` |
| 18:00:24 | Segnale AAPL bearish -0.379 (conf. 0.725), coppia corretta `glm-5.2+gpt-oss` | `sentiment_signals` id 3485 |
| 18:07–19:52 | **Churn AAPL**: 4 BUY (S1 momentum) intervallati da 3 SELL (`sentiment_reversal: score -0.379 < threshold -0.35`), ciclo ~15-30 min ciascuno; ultima entry (19:52) resta aperta a fine giornata | `trades`, `execution_decisions` (vedi [DAY-002]) |
| 18:37:00 | Entry JPM, SHEL (S1, re-entry) | `trades` |
| 19:22:00 | Entry NVO (S4, signal_score 0.18); JPM chiusa portfolio_sell (+$12.41 net) | `trades` |
| 19:52:00 | Entry TM (S4, signal_score 0.154); ultima entry AAPL della giornata | `trades` |
| 21:45:00 | Ultimo aggiornamento `ingestion_stats_daily` per il giorno | `ingestion_stats_daily` |
| 21:46:09 | Reset contatore `consecutive_fallback` (fallback intermittente, non un blocco continuo) | `fallback_counters` |
| 22:30:01 | Snapshot giornaliero `risk_reports`: NAV $110,029.17, exposure 30.4%, drawdown combinato 6.96%, HHI=1.0 (**metrica non funzionante**, vedi [DAY-005]), 0 alert | `risk_reports` |
| — | **Nessun evento successivo alle 21:52 disponibile nei log container** per 07-14 (restart 21:48 UTC dello stesso giorno + restart odierno hanno azzerato la history log) | `docker compose logs` |

## 4. Tabella News Ingest

| Fonte | Fetched | Queued (→news_log) | Duplicati | Discarded (no ticker) | Parse fail | extraction_method |
|---|---|---|---|---|---|---|
| gdelt_gkg | 2866 | 332 (186 in finestra 00-24h `fetched_at`†) | 153 | 2513 | 0 | org_lookup (186) |
| alpaca_benzinga | 676 | 371 (87 in finestra 00-24h†) | 2939 | 0 | 0 | source_metadata (87) |

† Nota: `ingestion_stats_daily` conteggia per `day` (bucket giornaliero interno), mentre la query diretta su `news_log.fetched_at` nella finestra 2026-07-14T00:00–24:00Z UTC restituisce 186 (gdelt) + 87 (benzinga) = 273 righe — leggermente diverso dai contatori giornalieri aggregati per via di boundary/timezone del bucket `day`. Nessuna riga con `published_at` futuro o >48h stale nella finestra osservata (0/273).

**Duplicati content_hash cross-ticker**: 15 gruppi di articoli con lo stesso `content_hash` associato a ticker diversi (max 7 ticker per articolo, es. CRM/IBM/INFY/MSFT/NOW/ORCL/SAP su un unico pezzo enterprise-software). Verificato che l'analisi LLM è **genuinamente differenziata per ticker** (polarity IBM -0.7/-0.65 vs CRM -0.25/-0.25 sullo stesso articolo) — non è un bug di copia, ma comporta N chiamate LLM indipendenti per lo stesso evento (costo/latenza moltiplicati, non deduplicati a livello di "evento").

**Ticker resolution (shadow, QX-01 non enforced)**: `news_resolved_entities` per il giorno → 274 `NO_TRADE_LOW_RESOLUTION_CONFIDENCE` + 110 `NO_TRADE_NOT_TRADABLE`, **0 risoluzioni positive**. Confermato via grep che `ticker_resolver.py` è chiamato solo da `resolver_shadow.py` — nessun impatto sul flusso ordini reale odierno, ma dato rilevante per la decisione QX-01 (se il resolver fosse enforced oggi, bloccherebbe ~il 100% dei segnali news-driven).

Confidenza analisi: **Alta** (dati completi, nessun gap temporale rilevato nell'ingest).

## 5. Tabella Performance Modelli LLM

| Modello | Risposte (llm_responses) | Polarity media | Polarity min/max | Confidence media |
|---|---|---|---|---|
| glm-5.2:cloud | 274 | 0.079 | -0.850 / 0.900 | 0.301 |
| gpt-oss:20b-cloud | 207 | 0.059 | -0.700 / 0.800 | 0.402 |
| kimi-k2.6:cloud | 66 | 0.033 | -0.650 / 0.800 | 0.293 |

Nota: kimi-k2.6 presente **solo** nella finestra 15:30–16:47 UTC (contaminazione, vedi [DAY-001]) — non è nella coppia live configurata (`glm52,gptoss`, confermato in Redis `config:sentiment_llm_models` al momento dell'analisi).

**Distribuzione sentiment_signals.model_id (breakdown ensemble/fallback):**

| model_id | Count | fallback_used |
|---|---|---|
| finbert | 146 | true (146/146) |
| ensemble:glm-5.2:cloud+gpt-oss:20b-cloud (coppia corretta) | 43 | false |
| ensemble:gpt-oss:20b-cloud (solo, partner assente/timeout) | 52 | false |
| ensemble:glm-5.2:cloud (solo, partner assente/timeout) | 15 | false |
| ensemble:kimi-k2.6:cloud+glm-5.2:cloud (contaminato) | 13 | false |
| ensemble:kimi-k2.6:cloud (contaminato, solo) | 5 | false |
| **Totale** | **274** | **146 fallback (53.3%)** |

Budget: `llm_budget` 2026-07-14 = $0.1406 speso, 62685 token input / 9294 output, `budget_exhausted=false` — il fallback **non** è causato da esaurimento budget. Root cause plausibile (da codice `sentiment.py`): timeout Ollama sul singolo modello o divergenza ensemble oltre soglia; nessuna riga di log applicativo disponibile per confermare la causa esatta per-evento (vedi [DAY-007], gap osservabilità).

**Verifica funzionale:**
- Output LLM validato prima di entrare nel signal store? **Sì** — fallback FinBERT interviene su timeout/divergenza/budget, mai un output LLM grezzo non validato entra come segnale definitivo.
- Ensemble gestisce varianza alta? **Sì** — `ensemble_std` presente in schema; fallback scatta su divergenza (vedi codice `sentiment.py:231-232`).
- News duplicate pesano più volte? Solo nel senso del fan-out multi-ticker (stesso evento, N ticker, N chiamate genuinamente distinte) — non duplicazione dello stesso (news, ticker).
- Stessa news → segnali multipli? Sì, ma per-ticker differenziati (verificato, non bug).
- Confidence bassa riduce il peso? Il fallback FinBERT ha confidence molto basse (es. 0.07–0.4) e i punteggi risultanti sono coerentemente piccoli in valore assoluto — consistente con score = polarity × confidence.
- Modelli chiamati offline/background? **Sì**, Celery task `sentiment-worker`, mai in hot path.
- Rischio hallucination diretto in decisione? **Basso ma non nullo** — il caso NFLX/DIS del 15:30-16:47 mostra che un ensemble degradato (modello sbagliato, non hallucination in senso stretto) è comunque entrato in una decisione di trading reale senza ulteriore filtro di plausibilità cross-modello.

## 6. Tabella Segnali Finali per Ticker (che hanno generato un ordine)

| Ticker | Strategia | Signal score (LLM, se S4) | Score (peso, S1) | Esito |
|---|---|---|---|---|
| NFLX | S4 | 0.1875 (kimi+glm52, **contaminato**) | — | BUY 15:52, chiusa 18:52 portfolio_sell +$21.31 net |
| NVDA | S4 | 0.39 | — | BUY 15:52, chiusa 18:52 (stesso ciclo di NFLX) |
| DIS | S4 | 0.3625 (kimi+glm52, **contaminato**) | — | BUY 16:07, ancora aperta a fine giornata |
| MSFT | S4 | 0.08 | — | BUY 17:07, ancora aperta |
| NVO | S4 | 0.18 | — | BUY 19:22, ancora aperta |
| TM | S4 | 0.154 | — | BUY 19:52, ancora aperta |
| AAPL | S1 | — | 0.0135→0.0128 (4 entry) | 4 BUY/3 SELL sentiment_reversal, churn (vedi [DAY-002]) |
| SHEL | S1 | — | 0.0128, poi 0.0128 (re-entry) | BUY 14:07, chiusa 16:52 (S4 expiry, -$5.38), re-BUY 18:37 |
| 15 simboli S1 (AMAT, AMD, ARM, ASML, CAT, INTC, MRVL, MU, NOK, SOXX, TSM, TXN, VALE, XLK) | S1 | — | 0.0056–0.0128 | BUY 14:07, tutte ancora aperte a fine giornata |
| JPM | S1 | — | 0.0128 | BUY 18:37, chiusa 17:37 portfolio_sell +$12.41 (nota: chiusura precede in timestamp una entry precedente al 07-13, non la entry del 07-14) |

Nessun segnale con `signal_score < 0.05` ha generato un ordine S4 (minimo osservato: MSFT 0.08). I punteggi S1 (0.005–0.02) sono **pesi di portafoglio**, non punteggi di sentiment — non comparabili direttamente alla soglia 0.05 richiesta per i segnali S4/news-driven.

## 7. Tabella Ordini Generati/Eseguiti

Riconciliazione `execution_decisions` ↔ `trades` per il 14/07: **27 BUY → 27 trade aperti (1:1)**, **19 SELL → 19 trade chiusi (1:1)**. Zero decisioni BUY/SELL con `order_id` nullo (nessun pattern NO-ORDER). Zero decisioni duplicate stesso-simbolo-stesso-minuto (nessuna race condition scheduler). Motore: **Alpaca paper** (`ALPACA_BASE_URL=https://paper-api.alpaca.markets`, confermato — nessuna ambiguità paper/live). Engine attivo: `execution.engine=portfolio` (config `trading.yaml`, baked==repo, nessun drift) → solo `portfolio-cycle` invia ordini, coerente con quanto osservato (nessun ordine da `run-execution`/legacy_sentiment).

24 cicli portfolio nella giornata (14:07–19:52+, ogni 15 min), `constraints_fired: []` in **tutti** i cicli campionati e nella scansione full-day — nessun cap/exposure limit attivato il 14/07.

Vedi tabella §6 per dettaglio ordine/ticker/rationale. Nessun reject osservato (assenza di tabella "orders" separata: lo stato ordine è tracciato solo tramite presenza/assenza di riga `trades` con `entry_price` popolato — non c'è un log locale di reject Alpaca; per confermare reject espliciti servirebbe l'API Alpaca, non consultata per vincolo read-only/no-broker-call).

## 8. Tabella PnL/Rendimento

**PnL realizzato (19 trade chiusi il 14/07):**

| exit_reason | # trade | Somma net_pnl | Somma costi |
|---|---|---|---|
| stop_loss (posizioni legacy 07-10, no metadata vol-scaled) | 8 | **-$197.01** | — |
| portfolio_sell (rebalance/decadimento S4) | 7 | **+$31.22** | — |
| sentiment_reversal (churn AAPL) | 4 | **+$4.73** | — |
| **Totale** | **19** | **-$161.05** | **$13.59** |

**Per strategia (trade con `stop_strategy` valorizzato):**

| Strategia | # trade chiusi | net_pnl |
|---|---|---|
| (vuoto — legacy pre-migrazione) | 9 | -$193.79 |
| S4 | 5 | +$36.81 |
| S1 | 5 | -$4.07 |

**Non calcolabile in questa sessione**: PnL non realizzato sulle 42 posizioni aperte a fine giornata (richiede mark-to-market con prezzo corrente/close — non disponibile senza chiamata broker live, esclusa dal perimetro read-only). Per calcolarlo servirebbe: quotazione EOD 07-14 per ciascun simbolo aperto × qty, confrontata con `entry_price`. Non inventato.

## 9. Analisi Correttezza Buy/Sell

- **Buy generati solo se consentito**: sì, tutte le entry S1/S4 osservate hanno `execution_decisions.reason` coerente con la strategia attiva (S1 momentum o S4 news-driven), nessun ordine "orfano" senza segnale a monte.
- **Sell/exit corretti**: sì, tre meccanismi distinti osservati e tutti coerenti — `stop_loss` (posizioni legacy), `portfolio_sell` (rebalance/decadimento peso), `sentiment_reversal` (guardrail su sentiment corrente negativo per posizioni long).
- **Stop-loss rispettati**: sì per le 8 posizioni legacy (07-10), ma con parametri **non** vol-scaled (`stop_k`/`stop_floor`/`stop_cap` NULL — pre-migrazione schema). Nessuna entry **del 07-14 stesso** ha raggiunto uno stop_loss nella stessa giornata, quindi non è verificabile con i dati odierni se il nuovo meccanismo vol-scaled (introdotto con la migrazione 037, deployata 07-14 21:48 UTC — **dopo** la chiusura della finestra osservata) sia corretto in produzione.
- **Signal flip rispettato**: sì — vedi SELL con reason `sentiment_reversal` e soglia esplicita (-0.35).
- **Max holding / rebalance band**: il meccanismo "S4 signal expired (age > max_age 4h)" chiude correttamente posizioni la cui giustificazione informativa non è più fresca (DIS, SHEL).
- **Nessun ordine duplicato**: confermato (0 righe stesso simbolo/minuto/decisione).
- **Nessun ordine contrario ravvicinato senza rationale**: il caso AAPL (§[DAY-002]) ha rationale esplicito ad ogni step (score S1 vs soglia sentiment_reversal) — non è un bug di mancanza di rationale, ma di **coordinamento** tra due rationale legittimi che si contraddicono ciclo dopo ciclo.
- **Nessun trade su dati stale**: la logica di expiry (`max_age=4h` per S4) esiste e ha agito (DIS, SHEL) — ma si veda [DAY-001] per il caso in cui un segnale "fresco" ma generato da un ensemble contaminato è comunque entrato in decisione.
- **Nessun trade con LLM output non valido**: fallback FinBERT ha intercettato correttamente i casi di timeout/divergenza/budget.
- **Circuit breaker/kill-switch**: nessuna evidenza di attivazione il 14/07 (nessun log disponibile, nessuna riga `risk_reports.alerts` non vuota).
- **Paper/live coerente**: sì, confermato `ALPACA_BASE_URL=paper-api.alpaca.markets`.
- **Idempotenza retry Celery**: confermata via 4 righe `SIGNAL_DUPLICATE_SKIP` in `audit_log` (NFLX, NVDA×2, MSFT) — nessun doppio ordine risultante.
- **Reconciliation ordini/fill/posizioni**: 27 BUY = 27 trade aperti, 19 SELL = 19 trade chiusi, 1:1 esatto.

## 10. Anomalie Trovate

### [DAY-001] Finestra di contaminazione ensemble LLM (kimi+glm52 invece di glm52+gptoss) con impatto su 2 trade reali

* Tipo: Bug (root-cause già nota, non nuova — ma impatto operativo del 07-14 documentato qui per la prima volta)
* Area: LLM / Signal
* Evidenza:
  * file/log/tabella: `sentiment_signals` (model_id), `execution_decisions.reason`, `src/llm/model_registry.py:26-33` (in_all semantics), memoria progetto `project_pair_toggle_rootcause.md`
  * timestamp: 2026-07-14 15:30:32–16:47:02 UTC
  * snippet/query: `SELECT generated_at, model_id, symbol FROM sentiment_signals WHERE model_id LIKE '%kimi%' AND generated_at BETWEEN '2026-07-14 14:50' AND '2026-07-14 17:10'` → 18 righe; decisione DIS 16:07 cita testualmente "ensemble:kimi-k2.6:cloud+glm-5.2:cloud" nel `reason`.
* Descrizione: il toggle binario del Sidebar frontend (`all`/`glm52`) ha resettato `config:sentiment_llm_models` Redis a `"all"`, che si espande a `{kimi, glm52}` (non alla coppia live `glm52,gptoss`, perché `gptoss.in_all=False`). Il reset manuale registrato in memoria alle 15:20 UTC **non ha fermato** la contaminazione: segnali con kimi continuano fino alle 16:47, ~87 minuti dopo il fix dichiarato — la finestra reale è più lunga di quanto tracciato nella memoria di sessione precedente.
* Impatto: 18 segnali generati con ensemble errato; **2 sono diventati trade reali** — NFLX (signal_id 3392, score 0.1875) e DIS (signal_id 3403, score 0.362, esplicitamente citato nel rationale dell'ordine). Kimi è il modello a peggiore accuratezza secondo lo Stage-1 screening (memoria progetto).
* Severità: **High**
* Confidenza: **High** (dati diretti da tabella + rationale ordine che cita il modello contaminato esplicitamente)
* Azione consigliata: verificare se WS-1 (selettore coppia registry-aware) è stato effettivamente deployato dopo il 07-14; se non lo è, disabilitare temporaneamente il toggle Sidebar lato UI finché non è multi-select/registry-aware. Rivedere se il reset manuale Redis richiede anche un restart/flush di eventuali task già in coda con la vecchia selezione.
* Test/monitor consigliato: alert automatico se `sentiment_signals.model_id` contiene un modello non presente nella whitelist configurata (`config:sentiment_llm_models` corrente) — rileverebbe la contaminazione in tempo reale invece che in analisi forense post-hoc.

### [DAY-002] Churn AAPL: 4 BUY/3 SELL in ~90 minuti per conflitto S1 momentum vs guardrail sentiment_reversal

* Tipo: Bug
* Area: Signal / Orders
* Evidenza:
  * file/log/tabella: `trades`, `execution_decisions`, `src/workers/portfolio_scheduler.py:2852-2889` (`_sentiment_reversal_sells`)
  * timestamp: 2026-07-14 18:07:00–19:52:00 UTC
  * snippet/query: 4 righe `trades` symbol=AAPL entry_time 18:22/18:52/19:22/19:52, ciascuna (tranne l'ultima) chiusa entro 15 min con `exit_reason='sentiment_reversal'`, reason `"sentiment_reversal: score -0.379 < threshold -0.35"` ripetuto identico 4 volte (segnale sentiment AAPL fermo dalle 18:00:24, nessuna nuova notizia nel frattempo).
* Descrizione: S1 (momentum tecnico) genera una BUY su AAPL ad ogni ciclo in cui il momentum resta positivo, ignorando che il guardrail `_sentiment_reversal_sells` — che legge lo stesso segnale sentiment persistente e negativo (-0.379) — forzerà la vendita entro 15-30 minuti. Le due logiche non sono coordinate: S1 non consulta lo stato di sentiment reversal prima di aprire una nuova posizione sullo stesso simbolo appena chiuso per quel motivo.
* Impatto: 3 round-trip completi in 90 minuti, PnL netto complessivo leggermente positivo (+$1.52 sulle prime 3, quarta ancora aperta) ma costi di transazione pagati 4 volte inutilmente; pattern esplicitamente elencato come sospetto nel protocollo di audit ("Roundtrip < 30 min").
* Severità: **Medium** (impatto economico oggi trascurabile, ma il pattern è strutturale e potrebbe costare di più in altre condizioni di mercato/volatilità)
* Confidenza: **High**
* Azione consigliata: aggiungere un cooldown per S1 (es. non ri-comprare un simbolo entro N minuti da un'uscita `sentiment_reversal` sullo stesso simbolo) o far consultare a S1 lo stato sentiment corrente prima di aprire nuove posizioni.
* Test/monitor consigliato: alert su ≥2 round-trip buy/sell sullo stesso simbolo entro 2 ore; test di regressione che simuli momentum positivo persistente + sentiment negativo persistente e verifichi che il sistema non oscilli indefinitamente.

### [DAY-003] Fallback FinBERT al 53.3% dei segnali della giornata (146/274), distribuito su tutte le ore di mercato

* Tipo: Anomalia
* Area: LLM
* Evidenza:
  * file/log/tabella: `sentiment_signals` (model_id='finbert', fallback_used=true)
  * timestamp: continuo 14:00–21:45 UTC (4-35 fallback per ora, nessuna ora esente)
  * snippet/query: `SELECT count(*) FILTER (WHERE fallback_used), model_id FROM sentiment_signals WHERE generated_at::date='2026-07-14' GROUP BY model_id` → finbert 146/146 fallback_used=true su 274 totali.
* Descrizione: più della metà dei segnali del giorno non ha usato l'ensemble LLM ma il fallback deterministico. `llm_budget.budget_exhausted=false` esclude la causa "budget"; il codice (`sentiment.py`) attribuisce il fallback a timeout Ollama o divergenza ensemble oltre soglia, ma senza log applicativi per il 07-14 non è possibile determinare quale delle due cause domini.
* Impatto: metà dei segnali del giorno ha una qualità di sentiment ridotta (FinBERT locale, non l'ensemble DK-CoT); il contatore `consecutive_fallback` si resetta di frequente (non un singolo blackout lungo) — suggerisce instabilità intermittente cronica di Ollama Cloud piuttosto che un incidente isolato.
* Severità: **High**
* Confidenza: **Medium** (il tasso è misurato con certezza; la causa esatta timeout-vs-divergenza non è distinguibile senza log)
* Azione consigliata: aggiungere un contatore/dashboard giornaliero del fallback rate con soglia di allerta (es. >20%); loggare esplicitamente la causa specifica (timeout vs divergenza vs budget) per ogni fallback in modo persistente (oggi solo il risultato aggregato è in DB, non la causa per-evento).
* Test/monitor consigliato: alert Telegram/dashboard se fallback rate giornaliero > soglia; retention log worker-inference sufficiente a coprire almeno 48h per permettere diagnosi post-hoc.

### [DAY-004] Attribuzione ambigua exit cross-strategia (SHEL aperta da S1, chiusa da logica decadimento S4)

* Tipo: Ambiguità
* Area: Signal / Orders
* Evidenza:
  * file/log/tabella: `trades` (SHEL, stop_strategy='S1', entry 14:07:01), `execution_decisions` (SHEL SELL 16:52:00.603366, reason "S4 signal expired... generated 2026-07-13 20:00 UTC")
  * timestamp: 2026-07-14 14:07:01 (entry) → 16:52:00 (exit)
* Descrizione: la posizione SHEL è etichettata `stop_strategy='S1'` (aperta per momentum), ma la sua chiusura cita il decadimento di un segnale S4 generato il giorno prima e non collegato alla entry S1 di oggi. Compatibile con un combinatore di portafoglio che netta i pesi per simbolo cross-strategia (comportamento potenzialmente corretto), ma l'audit trail (`exit_reason`) attribuisce la causa a una strategia diversa da quella che ha aperto la posizione, rendendo l'attribuzione P&L per-strategia meno affidabile a colpo d'occhio.
* Impatto: rischio di misclassificazione nei report P&L per-strategia (SHEL -$5.38 è contato "S1" in `stop_strategy` ma la decisione di chiusura è di dominio S4).
* Severità: **Low**
* Confidenza: **Medium**
* Azione consigliata: chiarire/documentare (ADR) se il netting cross-strategia per-simbolo è intenzionale; se sì, aggiungere un campo che distingua "strategia che ha aperto" da "strategia che ha determinato la chiusura" nei report.
* Test/monitor consigliato: nessuno specifico oltre a un test di regressione sul combinatore multi-strategia già esistente, se presente.

### [DAY-005] `herfindahl_index` in `risk_reports` è una metrica stub non funzionante (sempre 1.0)

* Tipo: Bug
* Area: Risk
* Evidenza:
  * file/log/tabella: `src/workers/risk_monitor_task.py:85` — `current_weights = {"portfolio": 1.0} if strategy_returns else {}`
  * timestamp: riga `risk_reports` 2026-07-14 22:30:01, herfindahl_index=1.000000
* Descrizione: `_herfindahl()` (in `src/portfolio/risk_monitor.py:91-96`) è correttamente implementato per calcolare la concentrazione su un dizionario di pesi, ma il chiamante (`risk_monitor_task.py`) gli passa un placeholder hardcoded a chiave singola `{"portfolio": 1.0}} anziché i pesi reali per strategia/simbolo. Il risultato è matematicamente sempre 1.0 (concentrazione massima) indipendentemente dalla reale diversificazione del portafoglio (oggi: 42 posizioni aperte su 2 strategie attive). Verificato inoltre che `_check_alerts()` non legge mai `herfindahl_index` — la metrica è puramente decorativa oggi, non blocca né allerta nulla.
* Impatto: chiunque legga la dashboard/report di rischio vede un HHI=1.0 costante, potenzialmente interpretandolo come "portafoglio completamente concentrato" quando non lo è — rischio di conclusioni errate su concentration risk, sebbene non vi sia impatto operativo diretto (nessun alert dipende da questo campo oggi).
* Severità: **Medium**
* Confidenza: **High** (verificato leggendo il codice sorgente diretto)
* Azione consigliata: cablare `current_weights` con i pesi reali (per strategia o per simbolo, da definire) prima di considerare l'HHI affidabile; nel frattempo, non usare questo campo per decisioni.
* Test/monitor consigliato: test unitario che verifichi HHI < 1.0 per un portafoglio con ≥2 posizioni non nulle.

### [DAY-006] Disallineamento timezone/DST tra schedule Celery e reali orari NYSE (EDT)

* Tipo: Ambiguità
* Area: Ops / Data
* Evidenza:
  * file/log/tabella: `src/workers/celery_app.py:69` — commento "Sentiment Worker every 15 min during market hours (Mon-Fri 14:00-21:00 UTC = 9am-4pm ET)"
* Descrizione: NYSE apre 9:30-16:00 ET, che in EDT (vigente a luglio, come il 07-14) corrisponde a 13:30-20:00 UTC — coerente con quanto indicato nel prompt di questa sessione. Lo schedule codificato (14:00-21:00 UTC), applicato tutto l'anno senza aggiustamento DST, parte 30 minuti dopo l'apertura reale e continua per un'ora oltre la chiusura reale in EDT. Il commento nel codice stesso è impreciso su due fronti (ora di apertura "9am" invece di "9:30am", e l'equivalenza UTC/ET che vale solo in EST/inverno).
* Impatto: la prima mezz'ora di mercato (13:30-14:00 UTC) non genera segnali sentiment né ingest GDELT nella cadenza dedicata a market-hours; l'ultima ora (20:00-21:00 UTC) genera segnali "durante il mercato" quando il mercato è già chiuso in EDT.
* Severità: **Low**
* Confidenza: **High**
* Azione consigliata: valutare se rendere lo schedule DST-aware (es. calcolare l'offset EDT/EST dinamicamente) o quantomeno correggere UTC fissi a 13:30-20:00 per l'estate, accettando il disallineamento in inverno se già noto/voluto.
* Test/monitor consigliato: nessuno specifico; revisione manuale dello schedule a ogni cambio DST (marzo/novembre).

### [DAY-007] Log container worker/worker-inference/beat non disponibili per il 2026-07-14

* Tipo: Non verificabile (gap di dati)
* Area: Ops
* Evidenza:
  * `docker compose logs worker` → 67 righe totali, prima riga già post-restart odierno (log iniziano ~2026-07-15 11:05 UTC)
  * `docker compose ps` → worker "Up About an hour", worker-inference "Up 3 hours", beat "Up About an hour" (rispetto al momento dell'analisi)
* Descrizione: i container sono stati ricreati come parte del deploy 2026-07-14 21:48 UTC (merge ff3de56, migrazione 037 — da memoria progetto) e di nuovo in un restart successivo il 07-15. Nessuna delle due repliche precedenti ha lasciato log accessibili via `docker compose logs` per la finestra 07-14. Tutta la ricostruzione di questo report per errori/warning/timeout LLM si basa su tabelle Postgres (fallback_counters, sentiment_signals.fallback_used), non su messaggi di log applicativi con stack trace.
* Impatto: impossibile confermare la causa esatta (timeout vs divergenza) di ciascun evento di fallback FinBERT o determinare se ci sono stati errori silenziosi non riflessi in nessuna tabella.
* Severità: **Medium** (limita la profondità diagnostica, non indica di per sé un malfunzionamento)
* Confidenza: **High**
* Azione consigliata: configurare retention log persistente (driver `json-file` con `max-size`/`max-file` adeguati, o spedizione a un log aggregator) così che un restart/deploy non cancelli la storia operativa del giorno.
* Test/monitor consigliato: verificare periodicamente che i log coprano almeno le ultime 48h indipendentemente da restart/deploy.

### [DAY-008] Token Bearer API REST fornito non valido (JWT atteso, chiave statica ricevuta)

* Tipo: Non verificabile (gap di accesso)
* Area: Ops / Data
* Evidenza:
  * `curl -H "Authorization: Bearer eJvMeu..." $BASE/decisions` → `{"detail":"Invalid or expired JWT token"}` (stessa risposta su tutti e 5 gli endpoint richiesti)
  * `src/api/auth.py:36` — messaggio di errore esatto, conferma che l'endpoint richiede un JWT valido, non una chiave statica
* Descrizione: il token fornito nelle istruzioni del task non è un JWT valido (o è scaduto) per l'istanza API in esecuzione. Tutti i dati richiesti dalle 5 API sono stati comunque ricostruiti con successo via query dirette a Postgres (fonte più autoritativa comunque, essendo le API un layer sopra le stesse tabelle).
* Impatto: nessuno sui risultati di questo report (dati equivalenti recuperati via DB); impatto solo su eventuali automazioni future che dipendano dalle API REST con questo token.
* Severità: **Low**
* Confidenza: **High**
* Azione consigliata: emettere/rotare un token di servizio valido per sessioni forensi automatizzate, o documentare la procedura di login per ottenerne uno fresco ad ogni sessione.
* Test/monitor consigliato: includere un health-check del token all'inizio della routine cron giornaliera, con fallback esplicito su query DB dirette (come fatto qui) se il token è scaduto.

## 11. False Positive / Aree Corrette

* **Bug A5 (SELL con sentiment positivo)**: verificato assente. I casi con score positivo citati nel `reason` di una SELL (es. DIS "score=+0.060", SHEL "score=+0.045") sono decadimento per età del segnale (`S4 signal expired`), non un trigger di vendita basato sul valore del sentiment corrente — il valore citato è solo il punteggio storico del segnale scaduto, non la causa della vendita. Non è il pattern A5.
* **Riconciliazione ordini↔trade**: 27 BUY = 27 trade aperti, 19 SELL = 19 trade chiusi, esatto 1:1, nessun NO-ORDER, nessuna duplicazione stesso-minuto.
* **Idempotenza retry Celery**: 4 eventi `SIGNAL_DUPLICATE_SKIP` confermano il guardrail anti-doppio-ordine attivo e funzionante.
* **Paper/live**: nessuna ambiguità, `ALPACA_BASE_URL` punta a paper-api.
* **News duplicate fan-out multi-ticker**: verificato che la stessa notizia genera N segnali per N ticker, ma con analisi LLM genuinamente differenziata per azienda (non una copia).
* **Nessun future-dated/stale news**: 0/273 righe con `published_at` futuro o >48h stale.
* **Nessun cap/exposure/circuit breaker breach**: `constraints_fired: []` in tutti i 24 cicli, `risk_reports.alerts: []`.
* **Config baked vs repo `trading.yaml`**: nessun drift rilevato (`execution.engine=portfolio` identico in entrambi).

## 12. Dati Mancanti o Non Accessibili

* Log applicativi worker/worker-inference/beat per il 07-14 (container ricreati, history persa) — vedi [DAY-007].
* API REST (`/api/decisions`, `/trades`, `/signals`, `/positions`, `/orders`) — token JWT fornito non valido — vedi [DAY-008]. Dati equivalenti ottenuti via SQL diretto.
* PnL non realizzato sulle 42 posizioni aperte a fine giornata — richiederebbe prezzo di mercato corrente/EOD, non disponibile senza chiamata broker live (esclusa da questa sessione read-only).
* Causa esatta (timeout vs divergenza) di ciascun evento di fallback FinBERT — non loggata in modo persistente per-evento, solo aggregata.
* Stato reale del kill-switch/circuit breaker durante la giornata — nessun log disponibile per confermare se sia mai stato controllato/attivato oltre all'assenza di alert in `risk_reports`.
* Verifica diretta via Alpaca del prezzo di fill effettivo vs prezzo atteso (slippage) — disponibile solo come `slippage_est` calcolato internamente, non confrontato con un dato broker indipendente in questa sessione.

## 13. Raccomandazioni Immediate

1. Confermare se WS-1 (fix selettore ensemble registry-aware) è stato deployato dopo il 07-14; se no, disabilitare temporaneamente il toggle binario Sidebar per prevenire ulteriori contaminazioni ensemble ([DAY-001]).
2. Investigare la causa del fallback rate 53% con priorità Alta — se cronico, la qualità del segnale S4 è strutturalmente compromessa per metà delle valutazioni giornaliere ([DAY-003]).
3. Correggere `risk_monitor_task.py:85` per passare pesi reali a `_herfindahl()` invece del placeholder hardcoded, prima di usare l'HHI in qualunque decisione o dashboard ([DAY-005]).
4. Configurare retention log persistente per i worker Celery indipendente da restart/deploy ([DAY-007]).

## 14. Test o Monitor da Aggiungere

* Alert automatico su presenza di `model_id` non whitelisted in `sentiment_signals` rispetto a `config:sentiment_llm_models` corrente (rileva contaminazioni ensemble in tempo reale).
* Dashboard/alert su fallback rate giornaliero > soglia (es. 20%).
* Alert su ≥2 round-trip buy/sell sullo stesso simbolo entro 2 ore (rileva churn cross-strategia).
* Test unitario per `_herfindahl()` con dati reali multi-strategia/multi-simbolo (HHI atteso < 1.0 con ≥2 posizioni).
* Logging persistente della causa specifica per ogni evento di fallback FinBERT (timeout/divergenza/budget), non solo l'aggregato.
* Health-check del token API a inizio sessione forense automatizzata, con fallback esplicito a query DB dirette.

## 15. Ticket Tecnici Suggeriti (solo remediation, no patch qui)

* **TICKET-A**: "Ensemble selection: eliminare/disabilitare toggle Sidebar binario finché non è registry-aware multi-select" — Area LLM, priorità Alta, collegato a [DAY-001] e al workstream WS-1 già noto.
* **TICKET-B**: "Investigare e ridurre il fallback rate FinBERT (attualmente 53% su giornata campione)" — Area LLM, priorità Alta, collegato a [DAY-003].
* **TICKET-C**: "Coordinamento S1 momentum / guardrail sentiment_reversal per evitare churn ravvicinato" — Area Signal/Orders, priorità Media, collegato a [DAY-002].
* **TICKET-D**: "Fix herfindahl_index stub in risk_monitor_task.py (pesi reali invece di placeholder)" — Area Risk, priorità Media, collegato a [DAY-005].
* **TICKET-E**: "Retention log persistente worker/worker-inference/beat indipendente da restart" — Area Ops, priorità Media, collegato a [DAY-007].
* **TICKET-F**: "Chiarire/documentare (ADR) attribuzione exit cross-strategia nel combinatore di portafoglio" — Area Signal, priorità Bassa, collegato a [DAY-004].
* **TICKET-G**: "Rendere lo schedule Celery sentiment/GDELT DST-aware o correggere a 13:30-20:00 UTC" — Area Ops, priorità Bassa, collegato a [DAY-006].
* **TICKET-H**: "Provisioning token API di servizio valido per sessioni forensi automatizzate" — Area Ops, priorità Bassa, collegato a [DAY-008].

## 16. Stato Sistema

* **Ollama Cloud**: nessun downtime totale confermabile (il budget non è esaurito e ci sono comunque 128 segnali con ensemble LLM riuscito, 43 con la coppia corretta completa) — ma fallback rate 53.3% indica instabilità intermittente cronica, non un singolo blackout isolabile in una finestra precisa (il contatore `consecutive_fallback` si resetta ripetutamente durante il giorno).
* **FinBERT fallback rate**: **53.3%** delle decisioni sentiment del giorno (146/274).
* **Worker restart events**: worker, worker-inference e beat sono stati ricreati sia come parte del deploy 2026-07-14 21:48 UTC (merge ff3de56, migrazione 037 exit_order_ids — noto da memoria progetto) sia in un restart successivo osservato il 2026-07-15 (worker "up ~1h", worker-inference "up ~3h", beat "up ~1h" al momento dell'analisi). Nessun log storico disponibile per determinare se ci siano stati restart aggiuntivi/crash nel corso del 07-14 stesso.
