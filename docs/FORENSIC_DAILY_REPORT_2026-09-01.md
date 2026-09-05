# Forensic Daily Report — 2026-09-01

**Generato:** 2026-09-02 (sessione autonoma, sola lettura)
**Timezone operativo:** UTC, dichiarato in `src/workers/celery_app.py:52` (`timezone="UTC"`). Nessuna ambiguità: tutti i timestamp di questo report sono UTC.
**Sessione RTH:** 13:30–20:00 UTC (2026-09-01 è EDT, UTC−4).
**Modalità:** `paper` su tutte le 86 righe `portfolio_monitor_snapshots` della giornata (`broker_environment='paper'`, `mode='paper'`, `source='alpaca_paper'`). Nessun ordine live.
**Codice in produzione durante la sessione:** `446d77fb` (deployato 2026-09-01T12:20Z, prima dell'apertura). Nessun redeploy a mercato aperto: le riconciliazioni delle 14:20, 14:57, 16:20 e 18:20 sono state rimandate («Mercato aperto (o stato ignoto): rimando»), il batch successivo è andato alle 20:20Z, dopo la chiusura. Fonte: `logs/deploy_reconcile_2026-09-01.log`.
**Regime di scoring:** prima seduta con la **Variante A** del prompt sentiment (#399/#408, `bf5bef2e`, deployata 2026-09-01T10:33Z, deroga registrata nella carta di osservazione). Gli score di oggi non sono confrontabili con quelli di agosto senza segmentare.

---

## 1. Executive summary

La catena end-to-end ha funzionato: 2.466 articoli grezzi da 2 fonti → 106 righe `news_log` → 106 segnali → 441 decisioni su 48 cicli → 13 ordini, 13 fill, 0 reject, 0 duplicati, 0 ordini fuori orario, riconciliazione ordine↔fill↔posizione completa (coverage 3/3 = 100% nelle viste `s4_*_validation`).

Il NAV è passato da 109.830,84 $ a 109.705,65 $: **−125,19 $, −0,114%**, contro SPY **−0,69%** e QQQ **−1,27%**. Alembic ha battuto entrambi i benchmark. Il realizzato è −136,75 $ (5 uscite S1 per −113,70 $, 1 uscita S4 per −23,06 $); il MTM del libro aperto −51,10 $. La scomposizione del dossier attribuisce la perdita al **libro preesistente** (`passive_pnl_usd` −58,80 $) e assegna alle decisioni del giorno **+2,01 $** netti: le 47 posizioni aperte prima di oggi hanno perso 54,66 $, le 7 nuove hanno guadagnato.

Ollama **non è mai caduto**: entrambi i modelli hanno risposto su 98 news su 100 (198 risposte totali). Il 41,5% di `fallback_used=true` non è un guasto: 38 casi su 44 sono ensemble degradato a un solo modello perché *una* gamba stava sotto `min_confidence=0,40`. S4 li scarta tutti (`SKIP_FALLBACK`), fra cui i due segnali più forti sopra il gate della giornata (SPCX +0,72, AAPL +0,3375) — che però, misurati alla chiusura, avrebbero **perso** 20,72 $.

Il problema vero non è nel money-path, è nell'**osservabilità**: i log del 09-01 non esistono più (container ricreati il 09-02T10:20Z), il bearer del protocollo forense è rifiutato su tutti gli endpoint REST, `ensemble_cycle_health` e `performance_metrics` sono vuote, `per_strategy_metrics` è `{}`, e i **6 alert CRITICAL** emessi dal decay monitor alle 21:00 sono finiti solo su `log.critical` — cioè in un file cancellato 13 ore dopo. Nessun canale d'allerta ha funzionato: `mobile_events` ha zero righe da sempre e zero dispositivi registrati.

## 2. Verdict finale

> ### OK CON WARNING
>
> Il processo ha funzionato end-to-end e il money-path è corretto: nessun ordine spurio, nessun duplicato, nessun fill non riconciliato, paper/live coerente, idempotenza rispettata (1 `SKIP_IDEMPOTENCY` correttamente applicato su HOOD alle 19:52). I 25 finding di questo report sono **tutti** difetti di misurazione, attribuzione o osservabilità — non di esecuzione. Due sono nuovi e nessuno ha mosso denaro oggi.
>
> Il warning è specifico e non attenuabile: **la giornata non è auditabile in modo indipendente**. Log assenti, API REST inaccessibile, canale d'allerta inesistente. Questo report esiste solo perché il DB e il dossier deterministico sono sopravvissuti; il 41,5% di fallback, i 6 CRITICAL e i 1.082 candidati etichettati «non tradabili» sarebbero invisibili a chiunque non interrogasse Postgres a mano.

---

## 3. Timeline del 2026-09-01

Tutti gli orari UTC. «Fonte» indica la tabella/file da cui l'evento è ricostruito.

| Orario | Fase | Componente | Evento | Fonte |
|---|---|---|---|---|
| 10:33 | pre-market | deploy | `bf5bef2e` — Variante A del prompt sentiment in produzione | carta di osservazione |
| 12:20:03 | pre-market | deploy_reconcile | `bf5bef2e → 446d77fb` (2 commit, backend ricostruito) | `logs/deploy_reconcile_2026-09-01.log` |
| 13:30:00 | apertura | monitor | primo snapshot: NAV 109.744,74, 47 posizioni, `pipeline_health.signal = stale` (age 63.769 s) | `portfolio_monitor_snapshots` |
| **13:30–14:00** | **apertura** | **—** | **nessun ciclo di ingest né di portafoglio: 30–37 minuti di sessione scoperti (beat `hour="14-21"` in UTC fisso, DST-blind)** | `celery_app.py:79,219` |
| 14:00:44 | RTH | sentiment | primo ciclo di scoring: segnale 9383 (HD, −0,2458, ensemble) | `sentiment_signals` |
| 14:00:44 | RTH | ingest | prima riga `news_log` del giorno; `llm_budget` apre la giornata | `news_log`, `llm_budget` |
| 14:07:00 | RTH | portfolio-cycle | ciclo 1246, `strategies_run=["S1","S4"]`, `orders_count=45` (target, non inviati — F-014) | `portfolio_cycles` |
| 14:07:00 | RTH | S1 | **4 BUY**: BP, GOOGL, PFE, INTC (ribilanciamento mensile — 09-01 è il 1° del mese) | `execution_decisions` 16632-16635 |
| 14:07:10 | RTH | broker | 4 fill: BP 43,88 / GOOGL 336,07 / INTC 86,59 / PFE 28,69 | `trades` 923-926 |
| 14:07:06 | RTH | S4 | prime `SKIP_*`: 1 `SKIP_FALLBACK` (INTC), 1 `SKIP_STALE` (IWM, 18,9 h), 20+ `SKIP_THRESHOLD` | `execution_decisions` |
| 14:22:00 | RTH | S1 | **4 SELL** per `s1_weight_drop`: GE, MMM, TXN, ARM — peso target a 0% | `execution_decisions` 16690-16693 |
| 14:22:00 | RTH | broker | 4 fill: TXN 252,47 (−75,86), MMM 170,64 (−36,53), GE 333,58 (−19,14), ARM 231,67 (−7,86) | `trades` 423,671,404,641 |
| 14:47:17 | RTH | sentiment | segnale **9400 HOOD +0,4815** (ensemble, std 0,0354) — «Morgan Stanley Upgrades Target» | `sentiment_signals` |
| 14:52:00 | RTH | S4 | **BUY HOOD** rank 2 su 5 candidati, peso 2,0% | `execution_decisions` 16720 |
| 14:52:06 | RTH | broker | fill HOOD 106,39976 su prezzo eseguibile 106,27 → **+12,2 bps** di slippage | `s4_lifecycle_events` |
| 14:57:00 | RTH | S4 ledger | `ENTRY_RECONCILIATION` HOOD `BROKER_FILLED`; `P0_OPEN_SNAPSHOT` + `P1_HOLDING`, `due_session=2026-09-03` | `s4_lifecycle_events`, `s4_exit_policy_events` |
| 15:01:06 | RTH | sentiment | segnale **9404 HOOD +0,0228** (conf. 0,25) su un pezzo di colore («BONER Meme Coin») — sovrascrive 9400 per S4 | `sentiment_signals` |
| 15:30:54 | RTH | sentiment | segnale **9408 MSFT +0,4500** (ensemble, std 0,0000) | `sentiment_signals` |
| 15:37:00 | RTH | S4 | **BUY MSFT** rank 2, peso 2,0%; fill 500,91 (slippage 0,0 bps) | `execution_decisions` 16770, `trades` 929 |
| 15:37–15:52 | RTH | ? | **36 id di `trades` e 32 di `portfolio_cycles` consumati senza righe** (gap 928/930-961, 1253-1284) | sequenze Postgres |
| 16:00:16 | RTH | sentiment | segnale **9416 QQQ −0,4072** (ensemble, conf. 0,64) — «Global Bond Rout Sparks Tech Selloff» | `sentiment_signals` |
| 16:07:00 | RTH | S4 overlay | **SELL QQQ** `sentiment_reversal` (−0,407 < −0,35) su una posizione **S1** aperta il 07-31 | `execution_decisions` 16819 |
| 16:07:00 | RTH | broker | fill QQQ 711,03 → **+25,70 $** realizzati, accreditati a S1 | `trades` 593 |
| 16:37:00 | RTH | S4 | **SELL HOOD** `below_entry_gate` (score scaduto a +0,023, age 1,6 h) | `execution_decisions` 16854 |
| 16:37:05 | RTH | broker | fill HOOD 104,73 → **−23,06 $** realizzati; `P0_TARGET_ZERO_BELOW_ENTRY_GATE` | `trades` 927 |
| 18:52:50 | RTH | breaker | `fallback_counters.consecutive_fallback` ultimo incremento | `fallback_counters` |
| 19:34:11 | RTH | sentiment | segnale **9477 HOOD +0,5395** (ensemble, std 0,1061) — di nuovo l'upgrade MS | `sentiment_signals` |
| 19:37:00 | RTH | S4 | **BUY HOOD** rank 1 su 6; SOXX rank 6 (+0,3376, sopra gate) tagliato `RANK_OUTSIDE_TOP_N` | `execution_decisions` 17077, `s4_intent_events` |
| 19:37:05 | RTH | broker | fill HOOD 103,42 (slippage 0,0 bps) | `trades` 962 |
| 19:42:00 | RTH | S4 ledger | **terzo** `ENTRY_RECONCILIATION` sull'ordine HOOD già chiuso + **secondo** `P0_RUNTIME_REPLAY` identico | `s4_lifecycle_events` |
| 19:49:43 | RTH | sentiment | ultimo segnale del giorno (9488 AMZN −0,0056); `consecutive_fallback` azzerato | `sentiment_signals` |
| 19:52:00 | RTH | S4 | ultimo ciclo (1301): `SKIP_IDEMPOTENCY` su HOOD (già comprato 15 min prima) — **guardia corretta** | `s4_intent_events` |
| 20:00:00 | chiusura | monitor | NAV 109.705,65 (−125,19, −0,114%), 48 posizioni, unrealized +922,09 | `portfolio_monitor_snapshots` |
| 20:12:03 | post-market | P1 challenger | **CRM** e **NVDA** dichiarati `P1_TIME_DUE` (D+2 dal 08-28): CRM −17,98 $, NVDA −69,18 $ virtuali. Il runtime E0 **tiene CRM** e aveva già chiuso NVDA il 08-28 a −22,94 $ | `s4_exit_policy_events` |
| 20:20:03 | post-market | deploy_reconcile | `446d77fb → 75821127` (13 commit) — include #427 (`dc83d23`) e #460 | `logs/deploy_reconcile_2026-09-01.log` |
| 21:00:00 | post-market | decay monitor | **6 alert CRITICAL** (S1, S2, S4 × hit_rate + ic), tutti su valori identici. Solo `log.critical`, nessun canale | `decay_reports` |
| 22:30:01 | post-market | risk report | NAV 109.683,43, exposure 33,96%, HHI 0,0254, `combined_drawdown` 0,0124, `alerts=[]`, `per_strategy_metrics={}` | `risk_reports` 81 |
| 22:45:00 | post-market | counterfactual | 396/426 controfattuali 1h calcolati; 32 `MISSING_EXIT_BAR`, 3 `PENDING_OVERNIGHT` | `execution_decisions` |
| 2026-09-02 08:00:18 | +1g | dossier | dossier deterministico 2026-09-01 generato (Alpaca SIP, `adjustment=all`) | `docs/evidence/dossier/2026-09-01.json` |
| 2026-09-02 10:20:13 | +1g | deploy | container ricreati → **log del 09-01 distrutti** | `docker inspect` |

**Eventi mancanti dalla timeline** (nessuna riga in DB): `ensemble_cycle_health` (0 righe, codice non ancora deployato), `performance_metrics` (0 righe, tabella senza scrittori), `mobile_events` (0 righe da sempre), `stop_decisions` (0 righe — corretto: `stop_loss: 0.0`, solo shadow con 1.142 righe in `stop_shadow_log`).

---

## 4. Tabella news ingest

### 4.1 Per fonte

| Fonte | Fetched | Queued | Duplicates | Scartate no_ticker | Scartate stale | not_tradable | Parse fail | Righe `news_log` | Articoli unici | Effective-timely | Quota E-T |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `alpaca_benzinga` | 588 | 316 | **2.594** | 0 | 135 | 133 | 0 | 93 | 46 | 14 | 30,4% |
| `gdelt_gkg` | 1.878 | 16 | 1 | 1.861 | 0 | 0 | 0 | 13 | 13 | 11 | **84,6%** |
| **Totale** | **2.466** | **332** | **2.595** | **1.861** | **135** | **133** | **0** | **106** | **59** | **25** | 42,4% |

Fonti non attive per design: `reuters` (test), `marketaux`/`finnhub`/`sec_edgar`/`rss` (non schedulate o dietro flag). Nessun errore di fonte, nessun retry, nessun buco temporale nella finestra 14:00–19:49.

**Copertura temporale:** ingest continuo 14:00:44 → 19:49:43. Nulla dopo la chiusura: la guardia `is_market_open()` (`sentiment.py:1121`) ferma correttamente il worker, anche se il beat sarebbe schedulato fino alle 21:45.

### 4.2 Per ticker (48 ticker su 96 di watchlist)

| Ticker | Righe | URL unici | | Ticker | Righe | | Ticker | Righe |
|---|---:|---:|---|---|---:|---|---|---:|
| NVDA | 10 | 10 | | GS, MU, DB, SPCX, DELL, AAPL | 3 | | INFY, NOW, CVX, CRM, CMCSA, C, AMAT, XLF, SOXX, BAC, AXP, TM, AVGO, TSM, UBS, INTC, IWM, JPM, V, MRK, MS, WFC | 1 |
| AMZN, HOOD | 5 | 5 | | XOM, AMD, DIS, HD, META, MSFT, SHEL, SNOW, XLE, XLK, XLV | 2 | | | |
| GOOGL, TSLA, SPY, QQQ, PANW, ORCL | 4 | 4 | | | | | | |

**48/96 simboli (50,0%) a zero righe.** Copertura *effective-timely* (articolo rilevante + arrivato in tempo utile): **21/96 = 21,9%**.

### 4.3 Top news per impatto sul segnale

| Titolo | Ticker mappati | Segnale prodotto | Effetto |
|---|---:|---|---|
| «Morgan Stanley Upgrades HOOD, Cites Prediction Market Boom» | 2 (HOOD, MS) | HOOD **+0,5395** (max ensemble del giorno) | **BUY HOOD 19:37** |
| «Robinhood Stock Rises as Morgan Stanley Upgrades Target to $…» | 1 | HOOD **+0,4815** | **BUY HOOD 14:52** |
| «QUICK SPARK: Microsoft's AI Spending Pays Off With Azure Growth» | 2 (MSFT, NVDA) | MSFT **+0,4500** | **BUY MSFT 15:37** |
| «Global Bond Rout Sparks Tech Selloff: 5 Nasdaq Stocks Falling» | 4 | QQQ **−0,4072** | **SELL QQQ** (posizione S1) |
| «Oil Surges, Treasury Yields Climb a Fifth Day, Software Retreats» | **9** (DELL, IWM, NOW, ORCL, PANW, QQQ, XLE, XLK, XLV) | XLE +0,4264, QQQ −0,3034, NOW −0,2709, XLK −0,2421, PANW −0,2198, IWM −0,2196, ORCL −0,1800, DELL −0,1540, XLV −0,0800 | nessun ordine (tutti già detenuti o sotto gate) |
| «Long Bond Again Dips Into Danger Zone—Highest Yield in Japan» | **9** | AAPL −0,24, SPY −0,2038, QQQ −0,1924, GOOGL −0,18, AMZN −0,175, TSLA −0,1358, MSFT/META/NVDA +0,0012 (FinBERT, conf. 0,048) | nessun ordine |
| «SpaceX Stock Rockets 32% in August» | 2 (SPCX, GOOGL) | SPCX **+0,7200** (max assoluto del giorno) | **scartato** `SKIP_FALLBACK` |
| «How Did BONER Meme Coin Create One of Robinhood's Biggest…» | 1 | HOOD **+0,0228** | ha **sovrascritto** l'upgrade MS e liquidato HOOD alle 16:37 |

### 4.4 Problemi trovati nell'ingest

| Problema | Misura |
|---|---|
| Duplicati > fetched | 2.594 `duplicate_id` contro 588 `fetched` per `alpaca_benzinga` (4,4×) |
| Fan-out multi-ticker | 47 righe su 106 (44,3%) sono mapping extra; 2 articoli mappati su 9 ticker, 1 su 7, 4 su 4 |
| Tag non validati | `TAG_UNCONFIRMED` **76/106 (71,7%)**, `FALSE_ENTITY_MATCH` 2, `ISSUER_SPECIFIC` solo 28 |
| Latenza | published→scored p50 **69,3 min**, p90 107,1 min, max **119,0 min** (99,2% della finestra `MAX_NEWS_AGE_HOURS=2`) |
| Corpo troncato | `body_snippet` medio **151 caratteri**, massimo 219. Il modello legge un teaser |
| News stale | 135 scarti `stale` (5,5% del fetched) — coerente col p90 di latenza |
| Timestamp futuri | **0** |
| Campi mancanti | **0** (titolo, url, published_at, body tutti popolati su 106/106) |
| Sanitizzazione | presente: `extraction_method` popolato su 106/106 (93 `source_metadata`, 13 `org_lookup`); ma entità HTML non decodificate nei corpi (`Here&#39;s`) |
| Failure silenziosi / retry | nessuno rilevabile — ma i log non esistono più (vedi DAY-002), quindi **non verificabile** |

**Confidenza dell'analisi ingest:** Alta sui conteggi (`ingestion_stats_daily` + `news_queue_drops` + `news_log` concordano), Media sulla qualità del mapping (i tag provider non sono validati da nulla), Bassa sui retry/errori transitori (log distrutti).

---

## 5. Tabella performance modelli LLM

### 5.1 Richieste per modello (da `llm_responses`)

| Modello | Risposte | Eligible | Polarity media | Conf. media | Min pol. | Max pol. | Timeout/assenti |
|---|---:|---:|---:|---:|---:|---:|---:|
| `gpt-oss:20b-cloud` | 100 | 36 | +0,0220 | 0,4771 | −0,600 | +0,900 | 0 |
| `glm-5.2:cloud` | 98 | 36 | −0,0222 | 0,3747 | −0,650 | +0,750 | **2** (DIS, SPY) |

**Latenza media: NON MISURABILE.** Non esiste una colonna di latenza per chiamata e i log del 09-01 sono stati distrutti (DAY-002). Il solo proxy disponibile è `llm_budget`: 99.735 token input + 7.723 output, 0,1747 $ spesi, budget non esaurito.

**Refusal / output invalido: 0 parse failure**, ma 3 valori di `risk_flags` malformati persistiti senza validazione (`ambiguo_entity`, `ambiguou_entity`, `whether already_priced_in`). `directness` e `event_type` sono entrambi entro gli enum attesi oggi. Campi strutturati popolati su 198/198.

### 5.2 Composizione dell'ensemble (da `sentiment_signals`)

| `model_id` | Segnali | `fallback_used` | Score medio | Conf. media | `ensemble_std` media |
|---|---:|---:|---:|---:|---:|
| `ensemble:glm-5.2:cloud+gpt-oss:20b-cloud` | 62 | 0 | −0,0063 | 0,4329 | 0,0860 |
| `single:gpt-oss:20b-cloud` | 32 | 32 | +0,0310 | 0,5406 | 0,0000 |
| `single:glm-5.2:cloud` | 6 | 6 | −0,0525 | 0,5833 | 0,0000 |
| `finbert` | 6 | 6 | −0,0576 | 0,2589 | 0,0000 |

**Ricostruzione esatta delle 106 righe**: 36 ensemble con **entrambe** le gambe ≥ 0,40 → `eligible=true` (72 risposte); 26 ensemble prodotti dal retry `min_confidence=0.0` di #90 (nessuna gamba ≥ 0,40 → accordo, non divergenza); **38 single-model** (esattamente una gamba ≥ 0,40); 6 FinBERT (divergenza vera di polarità). 36+26+38+6 = 106. ✔

**Conseguenza operativa:** `fallback_used=true` su 44/106 (41,5%) **non indica un guasto di Ollama**. Ollama è stato su per l'intera sessione. 38 dei 44 sono ensemble degradato a un modello per la soglia di confidenza; solo 6 sono sostituzioni FinBERT.

### 5.3 Distribuzione degli score

| Fascia \|score\| | n | Quota |
|---|---:|---:|
| ≥ 0,40 (sopra gate con margine) | 6 | 5,7% |
| 0,30 – 0,40 (sopra gate) | 4 | 3,8% |
| 0,05 – 0,30 (sotto gate) | 55 | 51,9% |
| < 0,05 (near-neutral) | 41 | 38,7% |

**Ticker con score estremi:** SPCX **+0,7200** (single, scartato) · HOOD +0,5395 · HOOD +0,4815 · MSFT +0,4500 · XLE +0,4264 · QQQ **−0,4072** · CRM +0,3681 · GOOGL −0,3589 (FinBERT) · AMZN −0,3447 · AAPL +0,3375 (single, scartato).

**Disaccordo forte fra modelli** (`ensemble_std` alto a fronte di uno score che ha comunque superato o sfiorato il gate):

| Simbolo | Score | `ensemble_std` | std/\|score\| | Esito |
|---|---:|---:|---:|---|
| **CRM** | +0,3681 | **0,3889** | **1,06** | sopra gate, rank 3 alle 19:37, `SKIP_PYRAMIDING` |
| SHEL | +0,2944 | 0,3889 | 1,32 | sotto gate |
| MU | −0,3274 | 0,3182 | 0,97 | ribassista, long-only |
| QQQ | −0,1924 | 0,2828 | 1,47 | sotto gate |
| AMZN | −0,3447 | 0,2475 | 0,72 | ribassista, long-only |
| AMD | +0,2818 | 0,2475 | 0,88 | sotto gate |
| XLE | +0,4264 | 0,2121 | 0,50 | sopra gate, già detenuto |

**Casi in cui un singolo modello ha dominato l'ensemble:** 38 (i `single:`), di cui `gpt-oss` 32 e `glm-5.2` 6 — asimmetria 5:1 spiegata dalla confidenza media più bassa di glm-5.2 (0,3747 contro 0,4771), non da errori.

**Fallback deterministico FinBERT:** 6 casi (5,7% dei segnali, **5,7% delle decisioni** — nessuno ha generato un ordine). Tre di essi (META, MSFT, NVDA sullo stesso articolo macro) hanno confidenza **0,048** e score +0,0012.

### 5.4 Verifica funzionale della catena LLM

| Domanda | Risposta | Evidenza |
|---|---|---|
| L'output LLM è validato prima del signal store? | **Parzialmente.** Lo schema JSON è forzato (198/198 campi popolati, 0 parse fail) ma gli **array liberi non sono validati**: 3 `risk_flags` malformati persistiti | DAY-006 |
| L'ensemble gestisce la varianza alta? | **No come gate.** `ensemble_std` è calcolato e persistito ma non entra in nessuna decisione d'ingresso: CRM è passato a 0,368 con std 0,389 | DAY-007 |
| Le news duplicate pesano più volte? | **No.** `uq_news_log_url_ticker` + 2.595 scarti `duplicate_id`/`duplicate_content`; `duplicati_syndication_per_ticker = 0` nel dossier | corretto |
| La stessa news può generare segnali multipli? | **Sì, per ticker diverso**, ed è il design del fan-out: 47 righe extra su 106 (44,3%). Un articolo macro genera 9 segnali indipendenti | DAY-017 |
| Confidenza bassa riduce il peso? | **Sì**: `score = polarity × confidence` verificato su tutte le righe (es. 9451 MSFT: pol. 0,025 × conf. 0,048 = 0,0012) | corretto |
| I modelli sono chiamati offline/background? | **Sì.** Nessuna chiamata LLM nel ciclo di portafoglio: `portfolio-cycle` legge `sentiment_signals`; lo scoring gira su `worker-inference` (queue `inference`, concurrency 1) | corretto |
| Hallucination LLM può entrare in decisione? | **Sì, per costruzione, mitigata solo in parte.** RAG assente, supervisor assente, varianza non-gate. La mitigazione reale è la soglia 0,30 + il gate anti-fallback. Caso concreto oggi: il segnale HOOD +0,0228 nato da un pezzo su una meme-coin ha liquidato una posizione da 1.419 $ | DAY-007, DAY-024 |

---

## 6. Tabella segnali finali per ticker

Segnali ≥ \|0,20\| (i restanti 82 sono sotto gate e non hanno generato decisioni attive).

| Simbolo | Score | Conf. | `ensemble_std` | Modello | Fallback | Generato | Esito S4 | Rend. seduta |
|---|---:|---:|---:|---|:--:|---|---|---:|
| SPCX | **+0,7200** | 0,800 | 0,0000 | single gpt-oss | **sì** | 16:16 | `SKIP_FALLBACK` | −1,02% |
| HOOD | +0,5395 | 0,760 | 0,1061 | ensemble | no | 19:34 | **SUBMITTED** rank 1 | −1,24% |
| HOOD | +0,4815 | 0,700 | 0,0354 | ensemble | no | 14:47 | **SUBMITTED** rank 2 | −1,24% |
| MSFT | +0,4500 | 0,750 | 0,0000 | ensemble | no | 15:30 | **SUBMITTED** rank 2 | −1,24% |
| XLE | +0,4264 | 0,675 | 0,2121 | ensemble | no | 18:16 | `SKIP_PYRAMIDING` rank 4 | +1,27% |
| QQQ | **−0,4072** | 0,640 | 0,0354 | ensemble | no | 16:00 | `RANK_LONG_ONLY` → **SELL overlay** | −1,27% |
| CRM | +0,3681 | 0,725 | **0,3889** | ensemble | no | 16:30 | `SKIP_PYRAMIDING` rank 3 | +0,22% |
| GOOGL | −0,3589 | 0,508 | 0,0000 | **finbert** | sì | 18:51 | nessuna (long-only) | −1,28% |
| AMZN | −0,3447 | 0,675 | 0,2475 | ensemble | no | 19:46 | nessuna (long-only) | −0,80% |
| AAPL | **+0,3375** | 0,750 | 0,0000 | single gpt-oss | **sì** | 15:47 | `SKIP_FALLBACK` | +2,61% |
| SOXX | +0,3376 | 0,650 | 0,2121 | ensemble | no | **08-31** 14:03 | `RANK_OUTSIDE_TOP_N` rank 6 | −2,10% |
| MU | −0,3274 | 0,675 | 0,3182 | ensemble | no | 15:15 | nessuna (long-only) | −2,64% |
| QQQ | −0,3034 | 0,725 | 0,0707 | ensemble | no | 18:16 | `RANK_LONG_ONLY` | −1,27% |
| SHEL | +0,2944 | 0,650 | 0,3889 | ensemble | no | 19:46 | sotto gate | +2,25% |
| AMD | +0,2818 | 0,575 | 0,2475 | ensemble | no | 17:01 | sotto gate | −1,45% |
| NOW | −0,2709 | 0,660 | 0,1061 | ensemble | no | 18:00 | nessuna (long-only) | **−3,44%** |
| TSLA | +0,2682 | 0,625 | 0,1768 | ensemble | no | 19:47 | `RANK_OUTSIDE_TOP_N` rank 7 | **−3,22%** |
| HD | −0,2458 | 0,625 | 0,1414 | ensemble | no | 14:00 | nessuna (long-only) | −0,88% |
| XLK | −0,2421 | 0,610 | 0,0071 | ensemble | no | 18:17 | nessuna (long-only) | −1,53% |
| NVDA | −0,2400 | 0,600 | 0,0000 | single gpt-oss | sì | 16:30 | nessuna (long-only) | −1,26% |
| AAPL | −0,2400 | 0,600 | 0,0000 | single gpt-oss | sì | 18:30 | nessuna (long-only) | +2,61% |
| PANW | −0,2198 | 0,600 | 0,0707 | ensemble | no | 18:15 | nessuna (long-only) | **−5,24%** |
| IWM | −0,2196 | 0,575 | 0,0707 | ensemble | no | 18:00 | nessuna (long-only) | −1,10% |
| SPY | −0,2038 | 0,575 | 0,2121 | ensemble | no | 18:37 | nessuna (long-only) | −0,69% |
| NVDA | +0,2025 | 0,575 | 0,1061 | ensemble | no | 15:00 | sotto gate | −1,26% |

**Segnali sopra il gate 0,30 in valore assoluto: 10.** Rialzisti e azionabili: 5 (HOOD ×2, MSFT, XLE, CRM) più 2 scartati per fallback (SPCX, AAPL) e 1 fuori top-N (SOXX). Ribassisti col segno corretto: 4 (QQQ ×2, GOOGL, AMZN, MU) — nessuno produce un ingresso perché il libro è long-only; uno solo (QQQ) ha prodotto un'uscita.

**Dispositions S4 del giorno** (`s4_intent_events`, 1.189 candidati / 1.189 disposizioni):

| `reason_code` | n | Quota |
|---|---:|---:|
| `SKIP_ENTRY_GATE` | 387 | 32,5% |
| `SKIP_ENTRY_FRESHNESS` | 349 | 29,4% |
| `SKIP_STALE` | 213 | 17,9% |
| `SKIP_FALLBACK` | **122** | 10,3% |
| `SKIP_PYRAMIDING` | 103 | 8,7% |
| `RANK_LONG_ONLY` | 8 | 0,7% |
| `RANK_OUTSIDE_TOP_N` | 3 | 0,3% |
| **`SUBMITTED`** | **3** | **0,25%** |
| `SKIP_IDEMPOTENCY` | 1 | 0,08% |

---

## 7. Tabella ordini generati/eseguiti

13 decisioni attive, 13 ordini, 13 fill, **0 reject, 0 cancel, 0 duplicati**. Motore: `execution.engine = portfolio` — tutti gli ordini nascono dai tick a `:07/:22/:37/:52` (portfolio-cycle); i 24 tick a `:12/:27/:42/:57` (`run-execution`, legacy) hanno prodotto solo righe `SKIP_*`, **nessun ordine**, come da configurazione.

| # | Decisione | Strategia | Ticker | Azione | Qty | Prezzo atteso | Prezzo fill | Slippage | Stato | Motore | Segnale | Rationale | Risk check | Anomalie |
|---|---|---|---|---|---:|---:|---:|---:|---|---|---|---|---|---|
| 16632 | 14:07:00 | S1 | BP | BUY | 18,9697 | n.d. | 43,88 | n.m. | FILLED | Alpaca paper | — (momentum) | peso 1,2% | cap settore energy, exposure 33,9% | — |
| 16633 | 14:07:00 | S1 | GOOGL | BUY | 2,4768 | n.d. | 336,07 | n.m. | FILLED | Alpaca paper | — | peso 1,2% | idem | — |
| 16634 | 14:07:00 | S1 | INTC | BUY | 5,9196 | n.d. | 86,59 | n.m. | FILLED | Alpaca paper | — | peso 0,7% | idem | segnale sentiment INTC = −0,120 (contrario, `SKIP_FALLBACK` nello stesso ciclo) |
| 16635 | 14:07:00 | S1 | PFE | BUY | 29,0132 | n.d. | 28,69 | n.m. | FILLED | Alpaca paper | — | peso 1,2% | idem | — |
| 16690 | 14:22:00 | S1 | ARM | SELL | 1,4089 | n.d. | 231,67 | n.m. | FILLED | Alpaca paper | — | `s1_weight_drop` → 0% | — | — |
| 16691 | 14:22:00 | S1 | GE | SELL | 2,3050 | n.d. | 333,58 | n.m. | FILLED | Alpaca paper | — | `s1_weight_drop` | — | — |
| 16692 | 14:22:00 | S1 | MMM | SELL | 3,7981 | n.d. | 170,64 | n.m. | FILLED | Alpaca paper | — | `s1_weight_drop` | — | — |
| 16693 | 14:22:00 | S1 | TXN | SELL | 2,6908 | n.d. | 252,47 | n.m. | FILLED | Alpaca paper | — | `s1_weight_drop` | — | — |
| **16720** | 14:52:00 | **S4** | HOOD | BUY | 13,3398 | **106,27** | **106,39976** | **+12,2 bps** | FILLED | Alpaca paper | **9400** (+0,4815) | «Morgan Stanley…», peso 2,0%, rank 2/5 | gate 0,30 ✔, anti-pyramiding ✔, fixed-slot ✔ | rank 1 era CRM con segnale di **91 h** |
| **16770** | 15:37:00 | **S4** | MSFT | BUY | 2,8280 | 500,91 | 500,91 | 0,0 bps | FILLED | Alpaca paper | **9408** (+0,4500) | «Azure Growth», peso 2,0%, rank 2 | idem | — |
| **16819** | 16:07:00 | **S4 overlay** | QQQ | SELL | 1,0790 | n.d. | 711,03 | n.m. | FILLED | Alpaca paper | **9416** (−0,4072) | `sentiment_reversal: −0,407 < −0,35` | nessuna soglia di confidenza sull'uscita | **chiude una posizione S1** aperta il 07-31 |
| **16854** | 16:37:00 | **S4** | HOOD | SELL | 13,3398 | n.d. | 104,73 | n.m. | FILLED | Alpaca paper | — | `below_entry_gate` (score scaduto a +0,023, age 1,6 h) | — | round-trip a 105 min dall'ingresso |
| **17077** | 19:37:00 | **S4** | HOOD | BUY | 13,5265 | 103,42 | 103,42 | 0,0 bps | FILLED | Alpaca paper | **9477** (+0,5395) | «Morgan Stanley…», peso 2,0%, rank 1/6 | gate ✔, idempotenza ✔ (bloccata la ripetizione alle 19:52) | ri-ingresso sullo stesso simbolo, stessa seduta |

`n.m.` = non misurabile: il prezzo eseguibile di riferimento è persistito solo per gli ingressi S4 (`s4_lifecycle_events.first_executable_price`). Per S1 e per tutte le uscite non esiste (vedi DAY-026).

**Constraint e limiti applicati:** `constraints_fired = []` su tutti i 24 cicli — nessun cap di settore, esposizione o concentrazione ha morso. Exposure lorda 32,7%→33,97% contro un limite di 50%; HHI 0,0254; drawdown corrente 0,85%→0,84% contro un limite del 5%. Il portfolio combiner ha girato in tutti i 24 cicli (`strategies_run=["S1","S4"]`). Circuit breaker: **nessuna chiave in Redis** (vedi DAY-028); `fallback_counters.consecutive_fallback` ha oscillato e si è azzerato alle 19:49.

---

## 8. Tabella PnL / rendimento

### 8.1 Vista NAV (fonte: `portfolio_monitor_snapshots`, broker Alpaca paper)

| Voce | Valore |
|---|---:|
| Equity chiusura precedente | 109.830,84 $ |
| NAV 20:00:00 | 109.705,65 $ |
| **Variazione giornata** | **−125,19 $ (−0,114%)** |
| Cash 20:00 | 72.435,76 $ |
| Unrealized P&L 20:00 | +922,09 $ |
| Exposure lorda | 33,97% (limite 50%) |
| Posizioni aperte | 48 (47 all'apertura) |
| SPY | **−0,69%** |
| QQQ | **−1,27%** |
| Alfa vs SPY | **+0,57 pp** |

### 8.2 Realizzato per trade (fonte: `trades`)

| Trade | Simbolo | Sleeve | Ingresso | Prezzo ing. | Uscita | Prezzo usc. | Qty | Gross | Costo | **Net** | Motivo | Tenuta |
|---:|---|---|---|---:|---|---:|---:|---:|---:|---:|---|---:|
| 423 | TXN | S1 | 07-24 14:07 | 280,51 | 14:22 | 252,47 | 2,6908 | −75,45 | 0,41 | **−75,86** | `portfolio_sell` | 936,2 h |
| 671 | MMM | S1 | 08-06 18:52 | 180,16 | 14:22 | 170,64 | 3,7981 | −36,16 | 0,37 | **−36,53** | `portfolio_sell` | 619,5 h |
| 404 | GE | S1 | 07-22 19:37 | 341,70 | 14:22 | 333,58 | 2,3050 | −18,72 | 0,43 | **−19,14** | `portfolio_sell` | 978,7 h |
| 641 | ARM | S1 | 08-03 16:07 | 237,12 | 14:22 | 231,67 | 1,4089 | −7,68 | 0,18 | **−7,86** | `portfolio_sell` | 694,2 h |
| 593 | QQQ | S1 | 07-31 16:37 | 687,08 | 16:07 | 711,03 | 1,0790 | +25,84 | 0,14 | **+25,70** | `sentiment_reversal` | 767,5 h |
| 927 | HOOD | **S4** | **09-01** 14:52 | 106,40 | 16:37 | 104,73 | 13,3398 | −22,27 | 0,78 | **−23,06** | `portfolio_sell` (`below_entry_gate`) | **1,75 h** |
| | | | | | | | | **−134,44** | **2,31** | **−136,75** | | |

### 8.3 Realizzato per sleeve

| Sleeve | Trade chiusi | Gross | Costi | **Net realizzato** |
|---|---:|---:|---:|---:|
| S1 | 5 | −112,17 | 1,53 | **−113,70** |
| S4 | 1 | −22,27 | 0,78 | **−23,06** |
| **Totale** | **6** | **−134,44** | **2,31** | **−136,75** |

Attenzione: i +25,70 $ di QQQ sono contabilizzati a **S1** ma sono stati generati da un **segnale S4** (`sentiment_reversal`). Senza quella riga, S1 realizzato è −139,40 $ e la sleeve news ne ha prodotti +25,70. Vedi DAY-023.

### 8.4 Non realizzato — posizioni aperte prima del 2026-09-01

47 posizioni, nozionale d'apertura 34.392,63 $ (fonte: `decision_quality.opening_snapshot` del dossier, prezzi Alpaca SIP).

| Sleeve | Posizioni | `passive_pnl` | `actual_intraday_pnl` | Effetto uscite |
|---|---:|---:|---:|---:|
| S1 | 43 | −74,85 | **−70,71** | +4,14 |
| S4 | 4 | +16,05 | **+16,05** | 0,00 |
| **Totale** | **47** | **−58,80** | **−54,66** | **+4,14** |

Estremi: DELL −28,53 · PANW −28,50 · LLY −19,32 · SNOW −10,50 || PBR +25,94 · **CRM (S4) +23,56** · AAPL +20,03 · CVX +8,72.

### 8.5 Non realizzato — posizioni aperte il 2026-09-01

| Simbolo | Sleeve | Ora | Prezzo ingresso | MTM a chiusura | `entry_percentile` |
|---|---|---|---:|---:|---:|
| INTC | S1 | 14:07 | 86,59 | **+14,09** | 0,236 |
| BP | S1 | 14:07 | 43,88 | **+11,19** | 0,306 |
| HOOD (2°) | S4 | 19:37 | 103,42 | +1,22 | 0,215 |
| MSFT | S4 | 15:37 | 500,91 | +0,31 | 0,449 |
| GOOGL | S1 | 14:07 | 336,07 | −2,60 | 0,728 |
| PFE | S1 | 14:07 | 28,69 | −4,06 | 0,360 |
| | | | | **+20,15** | mediana 0,360 |

### 8.6 Scomposizione causale della giornata (dossier, `decision_quality.summary`)

| Asse | USD |
|---|---:|
| `passive_pnl_usd` (libro preesistente, nessuna decisione) | **−58,80** |
| `selection_pnl_usd` (quali titoli si tenevano) | −18,40 |
| `exit_effect_usd` (effetto delle uscite) | **+20,41** |
| **`active_decision_pnl_usd`** (somma delle decisioni di oggi) | **+2,01** |
| `actual_intraday_pnl_usd` (misurato) | −56,79 |
| `market_beta_1_usd` | −10,38 |

Gli assi non sono additivi (`counterfactual_axes_are_additive: false`): non sommarli.

### 8.7 Slippage e costi

| Voce | Valore |
|---|---:|
| Costi ingressi 09-01 (7 trade) | 3,04 $ |
| Costi uscite 09-01 (6 trade) | 2,31 $ |
| **Costi totali giornata** | **5,35 $** (4,3% della perdita di NAV) |
| Slippage misurato (soli ingressi S4) | HOOD#1 **+12,2 bps** · MSFT 0,0 · HOOD#2 0,0 |
| `trades.slippage_est` | popolato su **1 riga su 7**, e vale esattamente `cost_usd` (0,7814) |
| Cost model | `cost-model:ccbc49f72a08ec5e` |

### 8.8 Cosa manca per un P&L completo

| Dato mancante | Query/fix che servirebbe |
|---|---|
| Prezzo atteso alla decisione per S1 e per tutte le uscite | persistere `first_executable_price` anche fuori dal ledger S4, oppure `SELECT` sul quote snapshot al `tick_time` |
| Slippage reale per ordine | `trades.slippage_est = fill_price − decision_reference_price` invece della copia di `cost_usd` |
| MTM per sleeve nel DB | `per_strategy_metrics` di `risk_reports` è `{}`: il breakdown esiste solo nel dossier del giorno dopo |
| P&L attribuito al segnale che l'ha causato | `execution_decisions.signal_id` è NULL su 431/441 righe |

---

## 9. Analisi correttezza buy/sell

**Nota metodologica obbligatoria su `exit_mechanism`:** le righe del 09-01 portano `s1_weight_drop` e `below_entry_gate`, etichette che per `docs/exit_mechanism_labels.md` **esistono solo dopo il fix di #184**. La loro sola presenza data la riga: sono **etichette osservate**, non stime per età dell'ultimo segnale. Nessun conteggio di questo report si appoggia a righe pre-fix.

| Controllo | Esito | Evidenza |
|---|---|---|
| BUY generati solo quando consentito | ✅ | 7 BUY: 4 S1 su ribilanciamento mensile (09-01 = 1° del mese, `rebalance_frequency: MONTHLY` rispettata dopo #185), 3 S4 tutti con score ≥ +0,45 > gate 0,30 |
| SELL/exit generati correttamente | ⚠️ | 6 SELL tutti con motivo esplicito. Ma `sentiment_reversal` ha chiuso una posizione **S1** (QQQ), meccanismo già deciso da rimuovere con la deroga #182(a) e **non ancora deployato** |
| Stop-loss rispettati | ✅ n/a | `stop_loss: 0.0` per design (solo shadow). `stop_decisions` = 0 righe, `stop_shadow_log` = 1.142 righe. Coerente |
| Signal flip rispettato | ✅ | QQQ: da +0,012 all'ingresso a −0,407 → uscita. HOOD: da +0,4815 a +0,023 → uscita `below_entry_gate` |
| Max holding days rispettato | ❌ | S4 tiene **WDC da 42,1 giorni** e CSCO da 7,0 contro un orizzonte di trial D+2. Il challenger P1 ha dichiarato CRM `P1_TIME_DUE` alle 20:12 e il runtime la tiene ancora |
| Rebalance band rispettata | ✅ | `constraints_fired = []` su 24/24 cicli; nessun ribilanciamento intra-banda |
| Nessun ordine duplicato | ✅ | 0 coppie `(minuto, simbolo, azione)` ripetute; `SKIP_IDEMPOTENCY` ha bloccato la ripetizione HOOD alle 19:52 |
| Nessun ordine contrario ravvicinato senza rationale | ⚠️ | HOOD BUY 14:52 → SELL 16:37 → BUY 19:37. **Ogni gamba ha un rationale esplicito e verificabile**, ma non esiste banda fra gate d'ingresso (0,30) e soglia d'uscita (0) |
| Nessun ordine su ticker non consentito | ✅ | 13/13 in `symbols.watchlist` |
| Nessun ordine fuori orario | ✅ | 0 righe BUY/SELL fuori 13:30–20:00 |
| Nessun trade su dati stale | ✅ | 213 `SKIP_STALE` + 349 `SKIP_ENTRY_FRESHNESS` applicati; i 3 ingressi S4 hanno segnali di 5, 6 e 3 minuti |
| Nessun trade su output LLM invalido | ✅ | 0 parse failure; i 3 `risk_flags` malformati non hanno prodotto ordini |
| Nessun trade con circuit breaker attivo | ⚠️ **non verificabile** | non esiste alcuna chiave breaker in Redis: non si può dimostrare che fosse inattivo, solo che non era osservabile |
| Nessun trade su strategia disabilitata | ✅ | `strategy_lifecycle`: S1 `supervised_paper`, S4 `paper` (entrambe `approved=true`); S2 `disabled` e S7 `research` non hanno prodotto nulla |
| Paper/live coerente | ✅ | 86/86 snapshot `paper`; `engine: portfolio`; il ramo `legacy_sentiment` non ha inviato niente |
| Idempotenza su retry Celery | ✅ | 1 `SKIP_IDEMPOTENCY`; nessun trade duplicato per `entry_order_id` |
| Reconciliation ordini↔fill↔posizioni | ✅ | `s4_lifecycle_validation` e `s4_p0_validation`: coverage **1,000** (3/3) per il 09-01; `s4_lifecycle_residuals` e `s4_p0_residuals` **vuote**; 48 posizioni a DB = 48 al broker |
| Score < 0,05 che generano ordini | ✅ nessuno | i 4 BUY S1 hanno `trades.score` 0,007–0,012, ma quel campo per S1 è il **peso di portafoglio**, non uno score sentiment. Nessun ordine S4 sotto 0,45 |
| Pyramiding (>3 BUY senza SELL) | ✅ nessuno | max 2 BUY sullo stesso simbolo (HOOD), separati da un SELL |
| SELL con sentiment positivo (bug A5) | ✅ nessuno | HOOD venduta a score +0,023, tecnicamente positivo ma **sotto il gate**: è il meccanismo `below_entry_gate`, non un bug di segno |
| `fallback_used=True` su tutti i simboli (Ollama giù) | ✅ **no** | 41,5%, e nessuna finestra con 100%: la causa è la soglia di confidenza, non un outage |
| NO-ORDER (decisione senza ordine) | ✅ nessuno | 13 decisioni attive → 13 `order_id` popolati → 13 fill |
| Ordini identici nello stesso minuto | ✅ nessuno | — |

---

## 10. Anomalie trovate

> **Convenzione di costo adottata oggi.** Dove il controfattuale corto è misurabile e risulta **favorevole** (il difetto ha evitato una perdita), il costo è registrato **negativo**, non `null` e non `0.0`. Registrarlo `null` renderebbe il ledger un conteggio unilaterale dei soli esiti sfavorevoli. È la prima volta che il ledger contiene costi negativi: le note delle occorrenze lo dichiarano esplicitamente.
>
> **Sette finding già registrati oggi** da `ALPHA_MISS_REPORT_2026-09-01.md` (F-001, F-009, F-012, F-023, F-026, F-031, F-040) sono citati in questo report ma **non ri-appesi** al ledger, per non gonfiare il conteggio di ricorrenza dello stesso giorno. **Unica eccezione: F-013** (DAY-021), ri-appeso perché l'occorrenza dell'alpha-miss report ha `costo_usd: null` e io ho una misura (−16,71 $), e la regola solo-append non consente di arricchirla; la nota dell'occorrenza avvisa di non contare due volte la ricorrenza del 2026-09-01.

### [DAY-001] Il bearer del protocollo forense è rifiutato su tutti gli endpoint REST — F-041

* Tipo: Bug
* Area: Ops
* Evidenza:
  * file/log/tabella: API `http://localhost:8001/api/{decisions,trades,signals,positions,orders}`
  * timestamp: 2026-09-02, esecuzione di questa sessione
  * snippet: `curl -H "Authorization: Bearer eJvMeuHhJS27..." → {"detail":"Invalid or expired JWT token"}` su 5 endpoint su 5
* Descrizione: le cinque chiamate REST che il protocollo forense prescrive come fonte primaria restituiscono tutte 401. L'intera analisi è stata rifatta interrogando Postgres a mano.
* Impatto: il canale d'ispezione documentato è inutilizzabile. Un audit meno paziente concluderebbe «non verificabile» sull'intera giornata.
* Severità: Medium
* Confidenza: High
* Azione consigliata: correggere il protocollo (header/schema di auth) o emettere un token di servizio a sola lettura per il forense.
* Test/monitor consigliato: smoke test in CI che chiami i 5 endpoint con il token del protocollo e fallisca su 401.

### [DAY-002] Zero righe di log per il 2026-09-01: il deploy del giorno dopo ha distrutto le prove — F-027

* Tipo: Bug
* Area: Ops
* Evidenza:
  * file/log/tabella: `docker compose logs worker --since 72h`, `docker inspect`
  * timestamp: container ricreati 2026-09-02T10:20:13Z
  * snippet: `docker compose logs worker --since 72h | grep -c "2026-09-01"` → **0**; primo timestamp disponibile `[2026-09-02 10:20:22`
* Descrizione: la riconciliazione delle 10:20Z del 09-02 (`19f18270 → fc3eddd2`) ha ricreato worker, worker-inference, api e beat. Nessun log del giorno analizzato sopravvive.
* Impatto: latenza LLM per chiamata, eccezioni transitorie, retry Celery, warning di semaforo e i 6 `log.critical` del decay monitor sono **definitivamente perduti**. Le sezioni 5 (latenza) e diversi controlli della sezione 9 restano non verificabili per costruzione.
* Severità: High
* Confidenza: High
* Azione consigliata: driver di logging persistente o `docker compose logs > logs/containers_$(date).log.gz` come primo passo di `deploy_reconcile.sh`, prima del `up -d`.
* Test/monitor consigliato: il cron forense verifica di avere log del giorno target e fallisce non-zero se `grep -c` è 0.

### [DAY-003] `ensemble_cycle_health` vuota per il 09-01: la strumentazione #427 è arrivata dopo la chiusura — F-049

* Tipo: Non verificabile
* Area: LLM / Ops
* Evidenza:
  * file/log/tabella: `ensemble_cycle_health` (0 righe **da sempre**), `logs/deploy_reconcile_2026-09-01.log`
  * timestamp: `dc83d23` deployato 2026-09-01T20:20:03Z (dopo la chiusura)
  * snippet: `git merge-base --is-ancestor dc83d23 446d77fb` → **NO**; `SELECT COUNT(*) FROM ensemble_cycle_health` → 0
* Descrizione: il codice che scrive la salute per-ciclo dell'ensemble (`sentiment.py:1354`) non era nell'immagine in produzione durante la sessione del 09-01. Nella stessa area, **nessuna chiave di circuit breaker esiste in Redis** (`KEYS *breaker*` → vuoto): l'unico contatore vivo è `fallback_counters.consecutive_fallback`, azzerato alle 19:49:43.
* Impatto: la sola risposta possibile a «Ollama era su?» per il 09-01 è la ricostruzione manuale da `llm_responses` fatta in §5.2. La serie di salute dell'ensemble comincia dal 09-02 e ogni giornata precedente resta un buco.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna correzione di codice (già deployato). Registrare la **discontinuità** nella carta di osservazione: la serie `ensemble_cycle_health` esiste solo dal 2026-09-02.
* Test/monitor consigliato: allerta se `ensemble_cycle_health` non ha righe RTH in una seduta di borsa.

### [DAY-004] Il 41,5% di «fallback» non è un guasto: è la soglia di confidenza che dimezza l'ensemble, e S4 scarta il risultato — F-010

* Tipo: Bug
* Area: LLM / Signal
* Evidenza:
  * file/log/tabella: `sentiment_signals`, `llm_responses`, `src/workers/sentiment.py:427-464,766-770`, `src/config.py:256`
  * timestamp: 2026-09-01 14:00–19:49
  * snippet: 198 risposte / 100 news (98 news con **entrambi** i modelli); `eligible=true` solo 72 (min conf. 0,400, = `ENSEMBLE_MIN_CONFIDENCE`); 38 segnali `single:` con `fallback_used=true`; 122 dispositions `SKIP_FALLBACK`
* Descrizione: Ollama non è mai caduto. Su 106 segnali: 36 ensemble con entrambe le gambe ≥ 0,40, 26 ensemble dal retry a floor 0 di #90, **38 single-model** perché una sola gamba superava 0,40, 6 FinBERT per divergenza vera. Le 38 risposte che *hanno effettivamente prodotto lo score pubblicato* sono marcate `eligible=false` (forzatura a `sentiment.py:770`), quindi LOO-ICIR non le conta mai come contributori; e S4 le scarta in blocco con `SKIP_FALLBACK`, fra cui i due segnali sopra gate più forti della giornata: **SPCX +0,7200** (il massimo assoluto) e **AAPL +0,3375**.
* Impatto: due difetti sovrapposti. (1) L'etichetta `fallback_used` conflaziona «FinBERT ha sostituito l'ensemble» (6 casi) con «un modello era timido» (38 casi), e chiunque legga la metrica conclude che Ollama era giù. (2) Il 36% dei segnali della giornata è inaccessibile a S4 per un motivo che non è la qualità del segnale. Costo misurato sul controfattuale corto (score→chiusura, size tipica S4 2.200 $): SPCX **−13,37 $**, AAPL **−7,35 $** — cioè oggi lo scarto ha **evitato 20,72 $ di perdita**. Il difetto resta: la selezione non è governata dal merito del segnale.
* Severità: High
* Confidenza: High
* Azione consigliata: separare `fallback_used` in `degraded_reason ∈ {finbert_substitution, single_model_confidence, timeout}` e far decidere a S4 su quella, non sul booleano. Non toccare la soglia 0,40 (è taratura, congelata).
* Test/monitor consigliato: test che, dato un ensemble con una gamba a conf. 0,35 e l'altra a 0,60, asserisca `eligible=true` sulla gamba usata e un `degraded_reason` distinto da quello di FinBERT.

### [DAY-005] `risk_flags` accetta stringhe malformate: il modello scrive `ambiguo_entity` e il DB le persiste — F-055

* Tipo: Bug
* Area: LLM / Data
* Evidenza:
  * file/log/tabella: `llm_responses.risk_flags`
  * timestamp: 2026-09-01, finestra di scoring
  * snippet: `SELECT unnest(risk_flags), COUNT(*) ... GROUP BY 1` → `ambiguous_entity` 79, `low_source_quality` 64, `already_priced_in` 59, `rumor` 5, **`ambiguo_entity` 1, `ambiguou_entity` 1, `whether already_priced_in` 1**
* Descrizione: `risk_flags` è un `text[]` senza vincolo di enum né normalizzazione. Tre valori su 209 emissioni sono errori di battitura o frammenti di frase del modello, salvati come se fossero flag legittimi.
* Impatto: qualunque conteggio per flag è silenziosamente sbagliato. `ambiguous_entity` — il flag che il gating di `risk_flags` (QX-01) dovrà leggere — perde l'1,3% delle occorrenze in varianti ortografiche. Sono i tre casi visti oggi; il difetto è nel contratto, quindi non c'è limite superiore.
* Severità: Medium
* Confidenza: High
* Azione consigliata: `CHECK` su un enum chiuso (o normalizzazione + quarantena in un campo `risk_flags_raw`), prima di attivare qualunque gating su `risk_flags`.
* Test/monitor consigliato: test di persistenza che passi `["ambiguo_entity", "AMBIGUOUS_ENTITY", "ambiguous​entity"]` e verifichi normalizzazione o rifiuto.

### [DAY-006] La varianza d'ensemble non è mai un cancello: CRM passa il gate con un disaccordo più grande dello score — F-037

* Tipo: Rischio
* Area: LLM / Signal
* Evidenza:
  * file/log/tabella: `sentiment_signals`, `s4_intent_events`
  * timestamp: 2026-09-01 16:30:10 (segnale 9421)
  * snippet: CRM `score=+0,3681`, `ensemble_std=0,3889` → `std/|score| = 1,06`; rank **3** nello slot 19:37
* Descrizione: `ensemble_std` è calcolato, persistito e letto solo dal postmortem. Non entra in nessuna decisione d'ingresso. Oggi 7 segnali hanno `std/|score| ≥ 0,50`, e CRM ha superato il gate 0,30 con i due modelli che divergono di più di quanto lo score valga.
* Impatto: un segnale su cui i due modelli non sono d'accordo pesa esattamente come uno su cui concordano (MSFT, `std=0,0000`). CRM oggi non ha comprato solo perché era già a libro (`SKIP_PYRAMIDING`): la protezione è stata accidentale. Nessun costo attribuibile oggi.
* Severità: Medium
* Confidenza: High
* Azione consigliata: **non tarare** durante l'osservazione. Strumentare: registrare in `s4_intent_events.missingness` (o in un campo dedicato) quali candidati sarebbero stati scartati da un gate su `std`, in ombra, per avere il campione al 28/09.
* Test/monitor consigliato: contatore giornaliero dei segnali sopra gate con `std ≥ |score|`.

### [DAY-007] Gli slot top-N di S4 vanno a segnali vecchi di giorni su simboli già detenuti, e tagliano il candidato sopra gate — F-051

* Tipo: Bug
* Area: Signal
* Evidenza:
  * file/log/tabella: `s4_intent_events` (dispositions con `rank` non nullo)
  * timestamp: slot 2026-09-01 14:52 e 19:37
  * snippet:
    * slot **14:52** — rank 1 **CRM** segnale 9279 `model_generated_at=2026-08-28 19:15` (**91 h**), `SKIP_PYRAMIDING`; rank 2 HOOD (fresco, 5 min) `SUBMITTED`; rank 3 AMD (08-31), 4 XLF (08-31), 5 SOXX (08-31) — tutti `SKIP_PYRAMIDING`
    * slot **19:37** — rank 1 HOOD `SUBMITTED`; rank 2-5 MSFT/CRM/XLE/XLF tutti `SKIP_PYRAMIDING`; rank **6 SOXX** segnale 9285 (+0,3376, **sopra gate**, generato il 08-31 14:03) → **`RANK_OUTSIDE_TOP_N`**
* Descrizione: il ranker ordina insieme segnali freschi e segnali di giorni prima, e non esclude a monte i simboli che l'anti-pyramiding bloccherà comunque. Nello slot 19:37 cinque dei sei slot sono occupati da candidati che non possono comprare, e l'unico altro candidato sopra gate viene scartato per esaurimento posti.
* Impatto: la capacità d'ingresso di S4 è consumata da candidati inerti. Il residuo di SOXX dalle 19:37 alla chiusura non è misurabile dal dossier; SOXX ha chiuso la seduta a **−2,10%**, quindi l'esclusione è stata *plausibilmente favorevole* — non un costo.
* Severità: High
* Confidenza: High
* Azione consigliata: escludere i simboli `anti_pyramiding=true` **prima** del taglio top-N, e non solo dopo. È correttezza della selezione, non taratura: senza questa correzione ogni giornata osservata misura un ranker che spende slot su candidati che non possono agire.
* Test/monitor consigliato: test che, dati N+1 candidati sopra gate di cui N già detenuti, asserisca che l'unico non detenuto entri nel top-N.

### [DAY-008] `is_tradable` nel ledger degli intenti significa «selezionato dal ranker»: 1.082 candidati su 1.189 risultano «non tradabili» — F-045

* Tipo: Bug
* Area: Signal / Data
* Evidenza:
  * file/log/tabella: `src/strategies/s4/strategy.py:79`, `src/analysis/dossier/book.py:416-422`, `s4_intent_events`, dossier `aggregati.guardia_contraddizione`
  * timestamp: 2026-09-01, tutti i 24 cicli
  * snippet: `is_tradable=diagnostic.reason_code == "RANK_SELECTED"`; distribuzione del giorno `t`=107, `f`=**1.082**, `NULL`=1.189 (candidati). Dossier: `n_intenti_tradabili: 107`, `n_intenti_non_tradabili: 1082`, `n_valutabili: 107`
* Descrizione: il campo si chiama `is_tradable` ma è scritto come «il ranker mi ha selezionato». SOXX (ETF liquido, segnale sopra gate) e QQQ risultano `is_tradable=false`. Il modulo `counterfactual_runtime.py:179` lo sa e lo commenta esplicitamente («`is_tradable` è falsa soltanto perché lo slot non era ancora libero»); `book.py` non lo sa e usa il campo come partizione di tradabilità, scartando in `n_intenti_non_tradabili` tutto ciò che non è stato selezionato.
* Impatto: la popolazione valutabile della guardia ombra di contraddizione (#335) è **107 su 1.189 (9,0%)**, e per costruzione esclude esattamente i candidati che DAY-007 identifica come il problema. Sulla finestra d'osservazione: 403 valutabili su 7.138 intenti, `n_soppressi = 0`. Lo zero non è una misura, è l'assenza di popolazione.
* Severità: High
* Confidenza: High
* Azione consigliata: rinominare il campo in `rank_selected` e, se serve una vera tradabilità, scriverla separatamente. È correttezza dell'evidenza: la guardia ombra sta misurando 9% dell'universo credendo di misurarlo tutto.
* Test/monitor consigliato: test che asserisca `is_tradable=true` per un candidato con `RANK_OUTSIDE_TOP_N` su un simbolo effettivamente negoziabile.

### [DAY-009] `snapshot.ranking_score` assente su tutte le 2.378 righe del giorno: la selezione del 09-01 non è ricostruibile — F-052

* Tipo: Non verificabile
* Area: Signal / Data
* Evidenza:
  * file/log/tabella: `s4_intent_events.snapshot`, `logs/deploy_reconcile_2026-09-02.log`
  * timestamp: 2026-09-01, tutti gli slot
  * snippet: `SELECT COUNT(*), COUNT(snapshot->>'ranking_score') FROM s4_intent_events WHERE decision_slot::date='2026-09-01'` → **2378 | 0**. `fc3eddd` (PR #464, fix #401) deployato **2026-09-02T10:20:03Z**
* Descrizione: la correzione che rende il `rank` persistito una funzione dello score persistito nello stesso record è arrivata in produzione il giorno **dopo**. Sul 09-01 il ledger contiene il `rank` e uno `score` che il ranker non ha usato per ordinare (ordina sullo score post-velocity), quindi l'ordinamento non è verificabile dal record.
* Impatto: gli slot 14:52 e 19:37 documentati in DAY-007 sono ricostruiti dal `rank` dichiarato, non verificati contro un punteggio. La serie di intent auditabile inizia dal 2026-09-02.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna correzione (già deployata). Registrare la discontinuità: `snapshot.ranking_score` esiste solo dal 2026-09-02.
* Test/monitor consigliato: controllo giornaliero che `rank` sia una permutazione monotona di `snapshot.ranking_score` entro lo stesso `decision_slot`.

### [DAY-010] Il ledger delle uscite S4 riemette lo stesso evento derivato a ogni ciclo: una chiusura CRM = 7 righe identiche — F-061 (**NUOVO**)

* Tipo: Bug
* Area: Data / Ops
* Evidenza:
  * file/log/tabella: `s4_exit_policy_events`, `s4_lifecycle_events`
  * timestamp: HOOD il 2026-09-01 (2 copie); CRM 2026-08-27/28 (7 copie)
  * snippet:
    ```
    intent 683af6c2 CRM P0_RUNTIME_REPLAY: 7 event_id distinti,
      observed_at identico 2026-08-27 16:07:06.392851,
      net_pnl identico -18.7344, fill_price identico 244.840,
      created_at da 08-27 16:12 a 08-28 19:27,
      details.entry_lifecycle_event_id DIVERSO su ognuna
    ordine c14ed02d CRM ENTRY_RECONCILIATION: 8 righe; b7d149d1 NVDA: 7
    HOOD 09-01: 3 ENTRY_RECONCILIATION sull'ordine a89a3ddb (14:57, 16:42, 19:42)
      — la terza riconcilia l'ingresso di una posizione chiusa alle 16:37
    ```
* Descrizione: `ENTRY_RECONCILIATION` non è idempotente: ogni ciclo riemette la riconciliazione di un ordine già riconciliato, con un nuovo `event_id`. L'`event_id` del `P0_RUNTIME_REPLAY` è derivato da quello dell'evento di ingresso, quindi ogni riemissione a monte genera una nuova copia della chiusura a valle. Il fix di #374 (l'identità dell'evento derivato include quella dell'osservazione a monte) è la causa prossima di questa moltiplicazione.
* Impatto: **contenuto oggi**, non nullo. Le viste `s4_exit_policy_current` e `s4_lifecycle_current` usano `DISTINCT ON (intent_id, policy_id)` e il report del trial legge la vista, non la tabella: `s4_p0_validation` e `s4_lifecycle_validation` danno coverage 1,000 con 0 residui per il 09-01, e il monitor delle milestone ha letto correttamente 7 osservazioni / 2 cluster. Ma la tabella append-only è l'**artefatto di record** del contratto di trial, e chiunque la conti direttamente ottiene fino a 7× il P&L reale di una chiusura. Il rischio è di lettura, non di esecuzione.
* Severità: Medium
* Confidenza: High
* Azione consigliata: rendere `ENTRY_RECONCILIATION` idempotente sull'`order_id` (non riemettere se l'ordine è già riconciliato e non è cambiato nulla), oppure vincolare `UNIQUE (intent_id, policy_id, event_type, observed_at)` così che la duplicazione fallisca invece di accumularsi. Passa il test di esenzione della carta solo in senso debole (l'evidenza *pubblicata* è corretta), quindi resta un remediation ticket, non un intervento urgente.
* Test/monitor consigliato: invariante giornaliera `COUNT(*) = COUNT(DISTINCT (intent_id, policy_id, event_type))` su `s4_exit_policy_events` per `event_type='P0_RUNTIME_REPLAY'` e `status='CLOSED'`.

### [DAY-011] Il decay monitor confronta un unico numero globale con tre baseline diverse, e allerta su una strategia disabilitata — F-004

* Tipo: Bug
* Area: Risk / Ops
* Evidenza:
  * file/log/tabella: `decay_reports`, `strategy_lifecycle`, `performance_metrics`
  * timestamp: 2026-09-01 21:00:00.033065 (tutte le 12 righe con lo stesso timestamp)
  * snippet:
    ```
    strategy | metric        | baseline | actual  | level
    S1       | hit_rate      | 0.540    | 0.2762  | CRITICAL
    S2       | hit_rate      | 0.560    | 0.2762  | CRITICAL
    S4       | hit_rate      | 0.520    | 0.2762  | CRITICAL
    S1/S2/S4 | ic            | .035/.042/.028 | -0.0425 | CRITICAL ×3
    S1/S2/S4 | sharpe        | .95/1.10/.80   |  1.2491 | NORMAL ×3
    S1/S2/S4 | max_drawdown  | .08/.06/.10    |  0.0734 | NORMAL ×3
    ```
    `strategy_lifecycle`: **S2 = `disabled`, `approved=false`** — non ha girato (`strategies_run=["S1","S4"]` su 24/24 cicli)
* Descrizione: `_fetch_actual_metrics(strategy_id, pg)` restituisce lo stesso valore per tutti gli `strategy_id`: hit_rate 0,2762, ic −0,0425, sharpe 1,2491, drawdown 0,0734 identici sulle tre sleeve. Il monitor confronta un aggregato di pipeline con tre baseline per-strategia. Aggravante: due dei sei CRITICAL riguardano S2, che è disabilitata. In parallelo la tabella `performance_metrics`, progettata per il segnale di drift per-modello (`composite_ic`, `icir`, `psi_90d`, `psi_12m`, `drift_level`), ha **0 righe e zero riferimenti** in `src/` e `scripts/`: il solo monitor di decadimento vivo è quello rotto.
* Impatto: 6 CRITICAL al giorno privi di significato per-strategia. Un vero decadimento di S4 sarebbe indistinguibile dal rumore già presente.
* Severità: High
* Confidenza: High
* Azione consigliata: filtrare le strategie non `approved`/`disabled` e calcolare le metriche per sleeve (`trades.stop_strategy`) invece che sull'aggregato. Oppure, se le metriche per sleeve non sono ancora affidabili, emettere un solo report `pipeline` e smettere di fingere tre.
* Test/monitor consigliato: test che, dati due insiemi di trade disgiunti per sleeve, asserisca `actual_value` **diverso** per S1 e S4.

### [DAY-012] I 6 CRITICAL della giornata non hanno alcun canale: solo `log.critical`, in un file cancellato 13 ore dopo — F-062 (**NUOVO**)

* Tipo: Bug
* Area: Ops / Risk
* Evidenza:
  * file/log/tabella: `src/workers/decay_monitor_task.py:176-181`, `mobile_events`, `mobile_event_history`, `mobile_notification_deliveries`, `monitor_devices`
  * timestamp: 2026-09-01 21:00 (emissione), 2026-09-02 10:20 (distruzione del log)
  * snippet:
    ```python
    if report.overall_level == DecayLevel.CRITICAL:
        log.critical("DECAY CRITICAL [%s]: %s", strategy_id, alert)
    ```
    Nessun `AlertService`, `send_alert` o `notify` in tutto il file.
    `SELECT COUNT(*) FROM mobile_events`            → 0   (zero righe da sempre)
    `SELECT COUNT(*) FROM mobile_event_history`     → 0
    `SELECT COUNT(*) FROM mobile_notification_deliveries` → 0
    `SELECT COUNT(*) FROM monitor_devices`          → 0
    `risk_reports.alerts` del 09-01                 → `[]`
* Descrizione: il decay monitor scrive `decay_reports` e logga; non dispaccia. L'unico altro canale — lo stack mobile, i cui task `run_mobile_alert_evaluation` e `run_mobile_monitor_snapshot` girano **ogni minuto** — non ha mai scritto un incidente e non ha nessun dispositivo registrato a cui consegnarlo. Il report di rischio delle 22:30 chiude con `alerts=[]`.
* Impatto: la giornata ha prodotto 6 CRITICAL, 12 posizioni in perdita marcata, 7 ticker ciechi lato uscita per 3.457,98 $ di nozionale e 33 posizioni su 47 senza copertura news effettiva. **Zero notifiche.** Combinato con DAY-002, i CRITICAL non esistono più in nessuna forma leggibile fuori da `decay_reports`. È la categoria «log errori non propagati ad alert» nella sua forma completa.
* Severità: High
* Confidenza: High
* Azione consigliata: collegare il decay monitor a un canale durevole (riga `mobile_events` o `risk_reports.alerts`, non un log) e verificare che lo stack mobile abbia almeno un dispositivo, altrimenti disattivare i due task che girano a vuoto ogni minuto. È strumentazione, non taratura: non cambia cosa si compra.
* Test/monitor consigliato: test che, dato un report CRITICAL, asserisca l'esistenza di una riga durevole; e un canary giornaliero che fallisca se `monitor_devices` è vuota mentre i task di alert sono schedulati.

### [DAY-013] `per_strategy_metrics` è `{}`: nessun drawdown per sleeve è sorvegliato — F-050

* Tipo: Bug
* Area: Risk
* Evidenza:
  * file/log/tabella: `risk_reports` id 81
  * timestamp: 2026-09-01 22:30:01.090864
  * snippet: `jsonb_pretty(per_strategy_metrics)` → `{}`; `combined_drawdown = 0.012429`; `alerts = []`
* Descrizione: dopo la rimozione dell'entry sintetica `portfolio` (#349) il report di rischio pubblica solo un drawdown combinato e un oggetto per-strategia vuoto. Una sola riga per l'intera giornata.
* Impatto: né S1 né S4 hanno un drawdown sorvegliato; il kill-switch per sleeve non può scattare perché non ha input. Il breakdown esiste solo nel dossier del giorno dopo (§8.4), che non è un canale operativo.
* Severità: Medium
* Confidenza: High
* Azione consigliata: popolare `per_strategy_metrics` dai trade per `stop_strategy` (il dossier lo fa già: S1 −70,71, S4 +16,05) e riattivare la valutazione degli alert su quelle voci.
* Test/monitor consigliato: allerta se `per_strategy_metrics = '{}'` in un report di una seduta di borsa.

### [DAY-014] `portfolio_daily_state.daily_return` dà −2,90% contro un NAV a −0,114%: 25 volte tanto — F-003

* Tipo: Bug
* Area: PnL / Risk
* Evidenza:
  * file/log/tabella: vista `portfolio_daily_state`, `portfolio_monitor_snapshots`
  * timestamp: 2026-09-01
  * snippet:
    ```sql
    -- definizione della vista
    sum(net_pnl) / NULLIF(sum(entry_notional), 0) AS daily_return
    -- valore 09-01
    snapshot_date | daily_return          | net_pnl  | n_trades
    2026-09-01    | -0.02896347383467847  | -136.75  | 6
    -- NAV reale: 109830.84 -> 109705.65 = -0.114%
    ```
* Descrizione: il denominatore è il nozionale d'ingresso dei soli trade **chiusi** quel giorno (4.720 $), non il NAV (109.831 $). Il rendimento «giornaliero» è un rendimento sui trade chiusi.
* Impatto: fattore **25,4×** di sovrastima oggi. È la serie da cui si deriva il drawdown per sleeve: qualunque soglia calibrata su questi numeri scatta molto prima o molto dopo il previsto. Il valore è tanto più assurdo quanto meno si è tradato — un unico trade chiuso in perdita produrrebbe un «rendimento giornaliero» a due cifre.
* Severità: High
* Confidenza: High
* Azione consigliata: usare il NAV di `portfolio_monitor_snapshots` come denominatore, o rinominare la colonna in `closed_trade_return` e correggere i consumatori. È correttezza dell'evidenza: la serie di rendimento giornaliero raccolta durante l'osservazione non misura il portafoglio.
* Test/monitor consigliato: test che confronti `daily_return` con `(nav_close/nav_prev − 1)` e fallisca oltre una tolleranza ragionevole.

### [DAY-015] `execution_decisions.signal_id` è NULL su 431 righe su 441: la catena segnale→decisione→trade non è ricostruibile — F-011

* Tipo: Bug
* Area: Data
* Evidenza:
  * file/log/tabella: `execution_decisions`
  * timestamp: 2026-09-01, 48 tick
  * snippet:
    ```
    decision        |  n  | with_signal_id
    SKIP_THRESHOLD  | 387 |   0
    SKIP_PYRAMIDING |  44 |   6
    SKIP_FALLBACK   |  14 |   0
    BUY             |   7 |   3
    SELL            |   6 |   1
    SKIP_STALE      |   3 |   0
    ```
* Descrizione: la chiave esterna verso `sentiment_signals` esiste ma è popolata su 10 righe su 441 (2,3%). I 4 BUY S1 non hanno segnale sentiment per costruzione (è corretto), ma i 387 `SKIP_THRESHOLD` citano uno score nel testo del `reason` senza puntare al segnale che lo ha prodotto.
* Impatto: ogni analisi «quale notizia ha causato questa decisione» deve fare join per simbolo e finestra temporale, con ambiguità reale nei casi di segnali multipli per simbolo nello stesso ciclo (oggi: HOOD 5 segnali, NVDA 10 righe news). È lo stesso join che il dossier deve rifare ogni mattina.
* Severità: Medium
* Confidenza: High
* Azione consigliata: popolare `signal_id` su tutte le dispositions che hanno letto un segnale (il valore è già in mano al chiamante — `s4_intent_events` lo persiste correttamente).
* Test/monitor consigliato: invariante che ogni `execution_decisions` con `signal_score IS NOT NULL` abbia `signal_id IS NOT NULL`.

### [DAY-016] Il 71,7% delle righe scorate poggia su un tag provider che nessuno ha validato — F-057

* Tipo: Rischio
* Area: News / Data
* Evidenza:
  * file/log/tabella: dossier `copertura_articoli.totali.mapping_rilevanza`, `news_log.extraction_method`
  * timestamp: 2026-09-01
  * snippet:
    ```
    ISSUER_SPECIFIC:      28
    TAG_UNCONFIRMED:      76   <-- 71,7% di 106
    FALSE_ENTITY_MATCH:    2
    SECTOR_MACRO:          0
    IRRELEVANT_FANOUT:     0
    extraction_method: source_metadata 93, org_lookup 13
    ```
* Descrizione: il resolver deterministico non produce verdetti `RESOLVED` (alias_match e llm_agreement cablati a False, punteggio massimo 0,60 contro soglia 0,80), quindi ogni mappatura articolo→ticker resta `TAG_UNCONFIRMED` e viene comunque scorata. Due mappature sono classificate `FALSE_ENTITY_MATCH` dal dossier stesso.
* Impatto: `false_positive_ticker_rate → 0` è l'obiettivo di design del resolver, e oggi il 72% delle righe che alimentano il signal store non ha passato alcuna conferma. Nessun ordine del 09-01 è nato da una mappatura sospetta (i 3 ingressi S4 sono HOOD/MSFT su articoli `direct`), quindi il costo di oggi non è stimabile; il rischio è strutturale.
* Severità: Medium
* Confidenza: High
* Azione consigliata: la catena è già bloccata su golden set QX-01 (#30). Nessuna azione di codice: registrare la ricorrenza e la quota.
* Test/monitor consigliato: quota giornaliera `TAG_UNCONFIRMED` come metrica esplicita, con soglia di attenzione, invece di riderivarla dal dossier.

### [DAY-017] `duplicates` 2.594 contro `fetched` 588: il contatore di dedup non è verificabile — F-007

* Tipo: Ambiguità
* Area: News / Data
* Evidenza:
  * file/log/tabella: `ingestion_stats_daily`, `news_queue_drops`
  * timestamp: 2026-09-01, `updated_at` 19:45:01
  * snippet: `alpaca_benzinga: fetched=588, queued=316, duplicates=2594, discarded_stale=135`; `news_queue_drops`: `duplicate_id`/`ingestion`/`alpaca_benzinga` = 2.594
* Descrizione: gli scarti per duplicazione superano di 4,4× gli articoli recuperati nello stesso giorno. Le due tabelle concordano fra loro, quindi il 2.594 è reale — ma è additivo su re-fetch dello stesso batch, e `fetched` no. Le due colonne non sono confrontabili benché stiano affiancate nella stessa riga.
* Impatto: nessuna perdita. Ma la percentuale di duplicazione — la metrica che dovrebbe dire se vale la pena consumare il WebSocket Alpaca (#455) — non è calcolabile da questa riga.
* Severità: Low
* Confidenza: High
* Azione consigliata: separare `fetched_raw` (tutte le risposte provider) da `fetched_new`, o normalizzare i due contatori sullo stesso denominatore.
* Test/monitor consigliato: invariante `duplicates ≤ fetched_raw` sulla riga del giorno.

### [DAY-018] Il modello legge 151 caratteri di corpo: `include_content` di Alpaca resta non usato — F-046

* Tipo: Bug
* Area: News / LLM
* Evidenza:
  * file/log/tabella: `news_log.body_snippet`
  * timestamp: 2026-09-01
  * snippet: `AVG(LENGTH(body_snippet)) = 151`, `MAX = 219` su 106 righe; 0 righe con corpo vuoto
* Descrizione: `alpaca_benzinga` restituisce il `summary` (~160 caratteri) quando lo stesso endpoint, con le stesse chiavi, offre `content` da 3.930 a 15.757 caratteri (analisi #454). Il titolo ora entra nel prompt (#399, deployato 10:33Z), il corpo resta un teaser.
* Impatto: le tre righe FinBERT dell'articolo macro delle 18:30 escono con confidenza **0,048** — il classificatore non ha materiale su cui decidere. Non è stimabile un costo per il 09-01: nessun ordine è nato da un corpo troncato in modo dimostrabilmente fuorviante. La correzione è già una issue aperta (#454) e la deroga è registrata nella carta.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna in questa sessione — #454 è la sede. Registrare la misura del 09-01 come baseline pre-fix (151 caratteri medi) per poter dimostrare l'effetto del cambio.
* Test/monitor consigliato: metrica giornaliera `AVG(LENGTH(body_snippet))` per fonte, con allerta sotto 500 caratteri per `alpaca_benzinga` dopo il deploy di #454.

### [DAY-019] S4 non ha un orizzonte d'uscita: WDC è aperta da 42 giorni contro un trial a D+2 — F-025

* Tipo: Bug
* Area: Orders / Risk
* Evidenza:
  * file/log/tabella: `trades` (aperti, `stop_strategy='S4'`), `s4_exit_policy_events`
  * timestamp: fotografia alle 2026-09-01 20:00
  * snippet:
    ```
    symbol | entry_time          | giorni | qty     | quantity_remaining
    WDC    | 2026-07-21 16:37    |  42.1  | 2.9811  | 0.3347
    CSCO   | 2026-08-25 19:07    |   7.0  | 17.1357 | (null)
    CRM    | 2026-08-28 19:22    |   4.0  |  7.6000 | (null)
    XLE    | 2026-08-31 19:37    |   1.0  | 22.0056 | (null)
    ```
    Alle 20:12:03 il challenger P1 dichiara CRM `P1_TIME_DUE` (`due_session=2026-09-01`, net −17,98 $) e il runtime E0 la tiene.
* Descrizione: il ramo preserve-stale mantiene indefinitamente le posizioni con un segnale ancora sopra gate, mentre la scadenza a 4 h chiude le altre. WDC è aperta da sei settimane con un'uscita parziale (0,33 di 2,98 residue) e nessun meccanismo che la porti a termine.
* Impatto: le posizioni S4 «tiepide» accumulano esposizione fuori dall'orizzonte che il contratto di trial dichiara (D+2). La differenza P1−E0 su CRM oggi è **+17,98 $ a favore di E0** (P1 avrebbe chiuso in perdita, E0 tiene una posizione a +23,56 $ MTM): un'osservazione a favore del runtime, non contro. Il difetto è che l'orizzonte non esiste, non che tenere sia sempre sbagliato.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna taratura durante l'osservazione. Il trial S4 sull'uscita (#423) è esattamente lo strumento che deve rispondere; registrare che il campione contiene una posizione a 42 giorni, che va segmentata e non mediata.
* Test/monitor consigliato: allerta se una posizione S4 supera N× l'orizzonte dichiarato dalla `policy_version` attiva.

### [DAY-020] `sentiment_reversal` ha chiuso una posizione S1 e il P&L è finito nella sleeve sbagliata — F-033

* Tipo: Bug
* Area: Orders / PnL
* Evidenza:
  * file/log/tabella: `execution_decisions` 16819, `trades` 593
  * timestamp: 2026-09-01 16:07:00
  * snippet: `trade 593 | QQQ | stop_strategy=S1 | entry 2026-07-31 16:37 @687.08 | decision_id 5421 | exit 16:07 @711.03 | exit_reason=sentiment_reversal | net_pnl +25.70`; decisione: `sentiment_reversal: score -0.407 < threshold -0.35` su segnale 9416 (S4)
* Descrizione: l'overlay S4 ha liquidato una posizione che S4 non ha aperto — è precisamente il caso della deroga **#182(a)**, pre-registrata il 2026-08-25 e **non ancora deployata**. Il realizzato è accreditato a S1.
* Impatto: la serie realizzata di S1 del 09-01 (−113,70 $) contiene +25,70 $ generati da un segnale S4. Senza quella riga S1 è a −139,40 $ e S4 a −23,06+25,70 = **+2,64 $**. Il segno della sleeve news sulla giornata dipende da un'attribuzione sbagliata. Oggi l'esito è stato favorevole (uscita in guadagno), quindi non c'è un costo da registrare: c'è una **misattribuzione di +25,70 $**.
* Severità: High
* Confidenza: High
* Azione consigliata: nessuna azione nuova — #182(a) è già la sede e la deroga è concessa. Il report del 28/09 deve trattare questa data come pre-deploy e non sommare il realizzato S1/S4 attraverso il confine.
* Test/monitor consigliato: contatore giornaliero delle uscite `sentiment_reversal` su posizioni con `stop_strategy != 'S4'`, e allerta a > 0 dopo il deploy di #182(a).

### [DAY-021] Round-trip HOOD in 105 minuti: nessuna banda fra gate d'ingresso e soglia d'uscita — F-013

* Tipo: Bug
* Area: Orders
* Evidenza:
  * file/log/tabella: `execution_decisions` 16720/16854/17077, `trades` 927/962, `sentiment_signals` 9400/9404/9477
  * timestamp: 2026-09-01 14:52 → 16:37 → 19:37
  * snippet:
    ```
    14:47:17  segnale 9400  HOOD +0.4815  "Morgan Stanley Upgrades Target"
    14:52:00  BUY  106.39976  (1419.35 $, rank 2)
    15:01:06  segnale 9404  HOOD +0.0228 conf 0.25  "BONER Meme Coin"  <-- sovrascrive 9400
    16:37:00  SELL 104.73  [below_entry_gate] score=+0.023, age 1.6h  -> -23.06 $
    19:34:11  segnale 9477  HOOD +0.5395  di nuovo l'upgrade MS
    19:37:00  BUY  103.42  (1398.92 $, rank 1)
    19:52:00  SKIP_IDEMPOTENCY  <-- guardia corretta
    ```
* Descrizione: fra il gate d'ingresso 0,30 e la soglia d'uscita (peso target 0) non c'è banda morta. Un pezzo di colore con confidenza 0,25 ha sostituito l'upgrade Morgan Stanley come «ultimo segnale del simbolo» e ha portato il peso a zero. Tre ore dopo lo stesso upgrade è rientrato come nuovo articolo e la posizione è stata ricomprata.
* Impatto: **da precisare, contro la lettura intuitiva.** Il realizzato è −23,06 $, ma il dossier misura `mtm_eod` della prima posizione a **−38,55 $**: tenendola si sarebbe perso di più. Ricomprando a 103,42 la seconda gamba chiude a **+1,22 $**. Il conto della giornata su HOOD è −21,84 $ contro −38,55 $ di buy-and-hold: il churn ha **risparmiato 16,71 $**, al costo di 1,52 $ di commissioni aggiuntive. Il difetto (una posizione da 1.419 $ liquidata da una notizia su una meme-coin) resta reale; l'esito di oggi è stato fortunato.
* Severità: High
* Confidenza: High
* Azione consigliata: l'assenza di banda è taratura (congelata). Ciò che **non** è taratura è che S4 usi solo il segnale più recente per simbolo invece del più forte nella finestra (F-023, già registrata oggi dall'alpha-miss report): quella è la leva di correttezza.
* Test/monitor consigliato: contatore giornaliero dei round-trip intra-seduta con il delta P&L contro il buy-and-hold, così che il costo del churn sia misurato e non presunto.

### [DAY-022] `trades.slippage_est` è una copia di `cost_usd` e manca su 6 righe su 7 — F-015

* Tipo: Bug
* Area: PnL / Data
* Evidenza:
  * file/log/tabella: `trades`, `s4_lifecycle_events`
  * timestamp: 2026-09-01
  * snippet:
    ```
    id  | symbol | slippage_est | cost_usd
    923 | BP     | (null)       | 0.4332
    924 | GOOGL  | (null)       | 0.1418
    925 | INTC   | (null)       | 0.2645
    926 | PFE    | (null)       | 0.4332
    927 | HOOD   | 0.7814       | 0.7814   <-- identici
    929 | MSFT   | (null)       | 0.2502
    962 | HOOD   | (null)       | 0.7365
    ```
    Slippage vero, ricavabile solo dal ledger S4: HOOD#1 fill 106,39976 su eseguibile 106,27 = **+12,2 bps**; MSFT e HOOD#2 = 0,0 bps.
* Descrizione: la colonna che dovrebbe misurare la qualità d'esecuzione contiene, quando è popolata, il costo modellato. Il prezzo di riferimento alla decisione è persistito solo per gli ingressi S4 (`first_executable_price`), mai per S1 né per le uscite.
* Impatto: la qualità d'esecuzione è misurabile su 3 ordini su 13 (23%). I 12,2 bps di HOOD#1 sono l'unico slippage avverso osservato oggi (≈1,73 $ su 1.419 $) e sono visibili solo perché il ledger del trial S4 li registra per altri motivi.
* Severità: Medium
* Confidenza: High
* Azione consigliata: persistere un prezzo di riferimento alla decisione per ogni ordine e calcolare `slippage_est = (fill − riferimento) × qty`, oppure smettere di popolare la colonna con un valore che non è slippage.
* Test/monitor consigliato: test che asserisca `slippage_est != cost_usd` su un caso costruito con fill diverso dal riferimento.

### [DAY-023] 36 id di `trades` e 32 di `portfolio_cycles` consumati senza righe, in una finestra di 15 minuti — F-039

* Tipo: Anomalia
* Area: Data / Ops
* Evidenza:
  * file/log/tabella: sequenze `trades_id_seq`, `portfolio_cycles_id_seq`, tabelle `trades`, `portfolio_cycles`, `audit_log`
  * timestamp: fra 2026-09-01 15:37 e 15:52
  * snippet:
    ```
    trades:            ... 927, [928 assente], 929, [930..961 assenti], 962 ; last_value 965
    portfolio_cycles:  ... 1252 (15:37), [1253..1284 assenti], 1285 (15:52)
    audit_log:         ... 16921 (INSERT trades 929), [16922..16933 assenti], 16934 (15:52)
    ```
    Nessuna riga `DELETE` in `audit_log` per il 09-01 (solo `SIGNAL_STALE_SKIP` 393, `INSERT trades` 7, `SIGNAL_DUPLICATE_SKIP` 1).
* Descrizione: 32 id consumati **simultaneamente** su due sequenze diverse fra due cicli consecutivi. Il pattern (blocchi uguali su `trades` e `portfolio_cycles`) è quello di transazioni annullate: rollback consumano la sequenza. La causa più probabile è la suite di test contro il DB di produzione — lo stesso meccanismo già documentato con le righe `ingestion_stats_daily.source='reuters'` (presenti il 08-25, 08-27, 08-29 e **2026-09-02 10:10**, ma non il 09-01).
* Impatto: nessuna riga spuria è rimasta e nessun ordine è stato inviato. Ma se una di quelle transazioni fosse arrivata a un `commit`, avrebbe scritto trade fittizi nel libro durante la sessione. Il gemello su `ingestion_stats_daily` è già confermato.
* Severità: Medium
* Confidenza: Medium (il pattern è compatibile con rollback di test; senza log del 09-01 il colpevole non è identificabile)
* Azione consigliata: credenziali di sola lettura per la produzione e `DATABASE_URL` distinta per la suite; e un audit trail delle cancellazioni su `trades`.
* Test/monitor consigliato: controllo giornaliero che `trades_id_seq.last_value − MAX(trades.id)` sia 0, con allerta sui salti.

### [DAY-024] La finestra del beat è in UTC fisso e ignora il DST: si perdono i primi 30-37 minuti di ogni seduta EDT — F-021

* Tipo: Bug
* Area: Ops / Signal
* Evidenza:
  * file/log/tabella: `src/workers/celery_app.py:79,94,152,163,185,219,237`, `sentiment_signals`, `execution_decisions`
  * timestamp: 2026-09-01, apertura 13:30 UTC
  * snippet: `crontab(minute="7,22,37,52", hour="14-21", day_of_week="1-5")`; primo segnale del giorno **14:00:44**, primo tick di portafoglio **14:07:00**, apertura RTH **13:30:00**. Ultimo tick 19:52, ultimo segnale 19:49 — le finestre schedulate 20:00-21:52 sono vuote (correttamente fermate da `is_market_open()`, `sentiment.py:1121`).
* Descrizione: le finestre orarie sono scritte come ore UTC costanti, tarate su EST (UTC−5). In EDT (UTC−4) l'apertura è alle 13:30 UTC e la prima finestra utile alle 14:00: **30 minuti di scoring e 37 di ciclo di portafoglio scoperti**, ogni seduta, per tutta la parte estiva dell'anno. Simmetricamente due ore di finestra schedulata a mercato chiuso, salvate solo dalla guardia interna.
* Impatto: la mezz'ora d'apertura è la fascia a più alta dispersione. Oggi 106 news su 106 sono arrivate dopo le 14:00, quindi nessun segnale è stato perso in modo dimostrabile — ma la finestra di ingest apre 30 minuti dopo l'apertura per costruzione, e l'unico motivo per cui non si vede è che l'ingest non gira prima.
* Severità: Medium
* Confidenza: High
* Azione consigliata: derivare le finestre dal calendario Alpaca (già usato da `market_clock`) invece da ore UTC letterali. È correttezza: finché la finestra è sfalsata, l'evidenza raccolta esclude sistematicamente la prima mezz'ora di ogni seduta.
* Test/monitor consigliato: test con una data EDT e una EST che asserisca che il primo tick cada entro 5 minuti dall'apertura in entrambi i casi.

### [DAY-025] SPCX è nel gruppo settoriale degli indici larghi ma è un titolo singolo, e oggi era lo score più alto della giornata — F-034

* Tipo: Anomalia
* Area: Risk / Data
* Evidenza:
  * file/log/tabella: `config/trading.yaml:119,135`, `config/cost_model.yaml:44`, `news_log`, `sentiment_signals`
  * timestamp: 2026-09-01 16:16:34 (segnale 9420)
  * snippet:
    ```yaml
    etf_broad: [SPY, QQQ, IWM, SPCX]        # trading.yaml:135 — cap settoriale
    tier_c: [..., ROKU, RDDT, SPCX]         # cost_model.yaml:44 — "mid-cap, niche ETF, less liquid"
    ```
    Segnale 9420 SPCX **+0,7200** (conf. 0,800) su «SpaceX Stock Rockets 32% in August», `extraction_method=source_metadata`. Storico: 209 segnali, 8 BUY, 7 SELL — SPCX è negoziabile.
* Descrizione: lo stesso simbolo è classificato «indice largo» dalla mappa settoriale che alimenta `MAX_SECTOR_EXPOSURE` e «mid-cap poco liquido» dal cost model. Le due classificazioni sono incompatibili e le usano due vincoli diversi.
* Impatto: il cap settoriale mette in un unico paniere SPY, QQQ, IWM e un titolo idiosincratico a spread 10 bps. Oggi non ha morso (`constraints_fired = []` su 24/24 cicli) e il segnale è stato scartato per altro motivo, quindi nessun costo. Ma il giorno in cui SPCX passa il gate con un ensemble valido, il vincolo di concentrazione lo tratterà come diversificazione.
* Severità: Low
* Confidenza: High
* Azione consigliata: spostare SPCX in un gruppo settoriale coerente col suo cost tier. È classificazione, non taratura di soglie.
* Test/monitor consigliato: controllo di coerenza in CI fra `sectors` di `trading.yaml` e i tier di `cost_model.yaml` (nessun simbolo `tier_c`/`tier_d` in `etf_broad`).

### [DAY-026] I 14 `SKIP_FALLBACK` non ricevono mai un controfattuale: il costo dello scarto per fallback non è misurato — F-060

* Tipo: Bug
* Area: Signal / Ops
* Evidenza:
  * file/log/tabella: `execution_decisions`, indice `idx_execution_decisions_counterfactual`
  * timestamp: 2026-09-01 22:45:00 (batch controfattuale)
  * snippet:
    ```
    counterfactual_skip_reason | n   | computed
    (null)                     | 426 | 396
    MISSING_EXIT_BAR           |  32 |  32
    PENDING_OVERNIGHT          |   3 |   0
    ```
    Le 30 righe non calcolate sono esattamente BUY(7) + SELL(6) + `SKIP_FALLBACK`(14) + `SKIP_STALE`(3): l'indice parziale copre solo `SKIP_THRESHOLD`, `SKIP_EMA`, `SKIP_CAP`, `SKIP_PYRAMIDING`.
* Descrizione: il batch che calcola «cosa sarebbe successo se non avessimo scartato» ignora per costruzione la categoria `SKIP_FALLBACK` — cioè il 10,3% delle dispositions e proprio la popolazione che DAY-004 identifica come la più grossa esclusione non motivata dalla qualità del segnale.
* Impatto: il costo (o il beneficio) dello scarto per fallback non compare in nessuna serie automatica. I 20,72 $ di perdita evitata calcolati in DAY-004 esistono solo perché li ho ricavati a mano dal dossier: al 28/09 la domanda «quanto è costato il gate anti-fallback» non avrà una risposta strumentata.
* Severità: Medium
* Confidenza: High
* Azione consigliata: estendere l'indice parziale e il batch a `SKIP_FALLBACK` (e `SKIP_STALE`). È strumentazione pura, non tocca l'esecuzione, e senza di essa la finestra d'osservazione non può pesare il difetto più grande della giornata.
* Test/monitor consigliato: invariante che ogni `SKIP_*` con `signal_score IS NOT NULL` finisca con `counterfactual_computed_at` o un `counterfactual_skip_reason` esplicito.

---

## 11. False positive e aree risultate corrette

| Sospetto | Verdetto | Perché |
|---|---|---|
| «Ollama giù: 41,5% di fallback» | **FALSO** | 198 risposte su 100 news, entrambi i modelli su 98/100. Solo 2 assenze glm-5.2 (DIS, SPY) e 6 sostituzioni FinBERT per divergenza vera. Il 41,5% è la soglia `ENSEMBLE_MIN_CONFIDENCE=0,40`, non un outage |
| «Il whipsaw HOOD è costato soldi» | **FALSO nel segno** | −21,84 $ sulla giornata contro −38,55 $ di `mtm_eod` tenendo la prima posizione: il round-trip ha risparmiato 16,71 $, spendendo 1,52 $ di commissioni. Il difetto di meccanismo resta (DAY-021), l'esito no |
| «Lo scarto dei fallback ha bruciato l'alpha del giorno» | **FALSO oggi** | SPCX −13,37 $ e AAPL −7,35 $ al controfattuale corto: lo scarto ha evitato 20,72 $ di perdita |
| «Il taglio di SOXX dal top-N è costato» | **PROBABILMENTE FALSO** | SOXX chiude a −2,10%; il taglio è avvenuto alle 19:37, 23 minuti dalla chiusura, residuo non misurabile |
| «Latenza `ingested_to_scored` negativa su 106/106 righe» | **NON è un difetto** | `news_log.created_at` è scritto *al momento dello scoring*, non all'ingest (l'ingest vero è `raw_ingested_at`/`first_seen_at`, e `first_seen_to_ingested` misura correttamente 123–5.650 s). L'intervallo è ≈0 per costruzione, di −5 a −19 ms per ordine di INSERT. È una denominazione confusa nel dossier, non un errore di misura |
| «Ordini identici nello stesso minuto / race dello scheduler» | **NESSUNO** | 0 coppie `(minuto, simbolo, azione)` duplicate su 13 ordini |
| «Doppio invio su retry Celery» | **CORRETTO** | `SKIP_IDEMPOTENCY` su HOOD alle 19:52 ha bloccato il secondo invio dello stesso segnale 9477. La guardia funziona |
| «I cicli si fermano alle 19:52 mentre il beat va a 21:52» | **CORRETTO** | `is_market_open()` (`sentiment.py:1121`) ferma il worker alla chiusura. Comportamento voluto (il difetto è il lato *apertura*, DAY-024) |
| «Duplicati nel ledger S4 corrompono l'evidenza del trial» | **CONTENUTO** | `s4_exit_policy_current` e `s4_lifecycle_current` usano `DISTINCT ON (intent_id, policy_id)`; `s4_p0_validation` e `s4_lifecycle_validation` danno coverage 1,000 con 0 residui. Il report del trial legge la vista. Resta la trappola sulla tabella (DAY-010) |
| «`stop_decisions` vuota: gli stop non funzionano» | **CORRETTO** | `stop_loss: 0.0` per design (solo shadow); `stop_shadow_log` ha 1.142 righe nella sessione |
| «`ensemble_cycle_health` vuota: #427 non funziona» | **SPIEGATO** | `dc83d23` non è antenato di `446d77fb`, il commit live durante la sessione. Deployato alle 20:20Z, dopo la chiusura |
| «Il ribilanciamento S1 di 8 ordini è churn» | **CORRETTO** | 2026-09-01 è il 1° del mese: `rebalance_frequency: MONTHLY` rispettata (correzione #185 in produzione) |
| «`exit_mechanism` non è affidabile (#184)» | **NON SI APPLICA** | le etichette del 09-01 sono `s1_weight_drop` e `below_entry_gate`, che per `docs/exit_mechanism_labels.md` esistono **solo post-fix**. Sono osservate, non dedotte dall'orologio |
| «Nessun cap di rischio ha morso: i limiti sono spenti» | **CORRETTO** | exposure 33,97% su un limite del 50%, drawdown 0,84% su 5%, HHI 0,0254. I vincoli non hanno morso perché non c'era niente da mordere |
| «PBR e BP non erano coperti dalla pipeline» | **VERO ma corretto** | entrambi i mover rialzisti a 0 righe `news_log`, catturati da S1 momentum. Sistema long-only: 9 mover su 11 erano ribassisti e non detenuti, quindi inaccessibili per costruzione |

---

## 12. Dati mancanti o non accessibili

| Dato | Stato | Query/azione che servirebbe |
|---|---|---|
| Log worker/worker-inference/api/beat del 09-01 | **distrutti** (container ricreati 09-02T10:20Z) | irrecuperabile. Vedi DAY-002 |
| Latenza per chiamata LLM, timeout, retry, refusal | **non misurabile** | nessuna colonna di latenza in `llm_responses`; era solo nei log. Servirebbe `llm_responses.latency_ms` |
| Endpoint REST `decisions/trades/signals/positions/orders` | **401** su 5/5 | DAY-001 |
| Salute per-ciclo dell'ensemble | **0 righe** (codice post-chiusura) | `ensemble_cycle_health` inizia dal 09-02 |
| Drift per-modello (`composite_ic`, `icir`, `psi_90d/12m`, `drift_level`) | **tabella morta** | `performance_metrics`: 0 righe, 0 riferimenti in `src/` e `scripts/` |
| Drawdown e P&L per sleeve nel DB | **assenti** | `risk_reports.per_strategy_metrics = {}`; esistono solo nel dossier del giorno dopo |
| Prezzo di riferimento alla decisione per S1 e per le uscite | **assente** | `first_executable_price` esiste solo per gli ingressi S4 |
| `ranking_score` persistito negli intent del 09-01 | **assente** (fix deployato il 09-02) | DAY-009 |
| Controfattuale per `SKIP_FALLBACK` e `SKIP_STALE` | **mai calcolato** | DAY-026 |
| Confronto posizioni DB↔broker riga per riga | **non eseguito** | in questa sessione non ho chiamato Alpaca (vincolo read-only sul broker). Prossimità: `portfolio_monitor_snapshots.open_positions` = 48 = `COUNT(*) FROM trades WHERE exit_time IS NULL`, e `s4_*_validation` danno 0 residui |
| Identità di chi ha consumato 36 id di `trades` alle 15:37-15:52 | **non identificabile** | serviva il log del 09-01 (DAY-002) |
| Log frontend | **non rilevanti** | `alembic-frontend-1` non partecipa al money-path |

---

## 13. Raccomandazioni immediate

Tutte compatibili con la carta di osservazione: nessuna toccta soglie, pesi, flag o cooldown.

1. **Archiviare i log prima di ogni redeploy.** Una riga in `deploy_reconcile.sh` (`docker compose logs --no-color > logs/containers_$(date +%F_%H%M).log.gz`) prima di `up -d`. Senza questa, ogni forense futuro parte già cieco. → DAY-002
2. **Dare un canale ai CRITICAL.** Il decay monitor deve scrivere in un posto durevole. Sei allerte al giorno che finiscono in un file cancellato equivalgono a nessuna allerta. → DAY-012
3. **Correggere il denominatore di `portfolio_daily_state.daily_return`.** È la serie di rendimento giornaliero da cui si deriva il drawdown per sleeve, e oggi sbaglia di 25×. Difetto di correttezza dell'evidenza: passa il test di esenzione della carta. → DAY-014
4. **Escludere i simboli anti-pyramiding prima del taglio top-N.** Oggi cinque slot su sei sono stati spesi su candidati che non potevano comprare. Correttezza della selezione, non taratura. → DAY-007
5. **Rinominare `is_tradable` in `rank_selected`.** La guardia ombra di #335 crede di misurare 1.189 intenti e ne misura 107. Finché il nome mente, il suo `n_soppressi = 0` non è una misura. → DAY-008
6. **Estendere il batch controfattuale a `SKIP_FALLBACK`.** È la più grande esclusione della giornata (122 dispositions) e non ha alcuna misura automatica del suo costo. → DAY-026, DAY-004
7. **Riparare o togliere il bearer del protocollo forense.** Cinque endpoint su cinque a 401 rendono l'intero protocollo REST teatro. → DAY-001

## 14. Test o monitor da aggiungere

| # | Tipo | Cosa | Finding |
|---|---|---|---|
| 1 | monitor | il cron forense fallisce non-zero se `docker compose logs \| grep -c <data>` è 0 | DAY-002 |
| 2 | invariante | `trades_id_seq.last_value − MAX(trades.id) = 0`, allerta sui salti | DAY-023 |
| 3 | invariante | `COUNT(*) = COUNT(DISTINCT (intent_id, policy_id, event_type))` su `s4_exit_policy_events` CLOSED | DAY-010 |
| 4 | invariante | ogni `execution_decisions` con `signal_score IS NOT NULL` ha `signal_id IS NOT NULL` | DAY-015 |
| 5 | invariante | ogni `SKIP_*` con `signal_score` ha `counterfactual_computed_at` o uno skip reason esplicito | DAY-026 |
| 6 | invariante | `rank` è permutazione monotona di `snapshot.ranking_score` nello stesso `decision_slot` | DAY-009 |
| 7 | test | ensemble con gambe a conf. 0,35 e 0,60 → `eligible=true` sulla gamba usata, `degraded_reason` distinto da FinBERT | DAY-004 |
| 8 | test | `risk_flags` con typo/omoglifo/zero-width → normalizzato o rifiutato, mai persistito grezzo | DAY-005 |
| 9 | test | N+1 candidati sopra gate, N già detenuti → il non detenuto entra nel top-N | DAY-007 |
| 10 | test | candidato `RANK_OUTSIDE_TOP_N` su simbolo negoziabile → `is_tradable=true` | DAY-008 |
| 11 | test | due insiemi di trade disgiunti per sleeve → `decay_reports.actual_value` **diverso** fra S1 e S4 | DAY-011 |
| 12 | test | `daily_return` entro tolleranza di `(nav_close/nav_prev − 1)` | DAY-014 |
| 13 | test | una data EDT e una EST → primo tick entro 5 minuti dall'apertura in entrambi i casi | DAY-024 |
| 14 | test | fill diverso dal riferimento → `slippage_est != cost_usd` | DAY-022 |
| 15 | monitor | quota giornaliera `TAG_UNCONFIRMED` come metrica esplicita con soglia | DAY-016 |
| 16 | monitor | `AVG(LENGTH(body_snippet))` per fonte, allerta sotto 500 caratteri post-#454 | DAY-018 |
| 17 | monitor | uscite `sentiment_reversal` su posizioni `stop_strategy != 'S4'`, allerta > 0 post-#182(a) | DAY-020 |
| 18 | monitor | round-trip intra-seduta col delta P&L contro il buy-and-hold | DAY-021 |
| 19 | monitor | segnali sopra gate con `ensemble_std ≥ |score|` | DAY-006 |
| 20 | monitor | `per_strategy_metrics = '{}'` in una seduta di borsa → allerta | DAY-013 |
| 21 | monitor | `ensemble_cycle_health` senza righe RTH in una seduta → allerta | DAY-003 |
| 22 | monitor | `monitor_devices` vuota mentre i task di alert sono schedulati → canary | DAY-012 |
| 23 | CI | coerenza `sectors` (trading.yaml) ↔ tier (cost_model.yaml): nessun `tier_c`/`tier_d` in `etf_broad` | DAY-025 |
| 24 | CI | smoke test dei 5 endpoint REST col token del protocollo forense | DAY-001 |
| 25 | invariante | `ingestion_stats_daily.duplicates ≤ fetched_raw` | DAY-017 |

## 15. Ticket tecnici suggeriti

Solo difetti di **correttezza** — quelli che, non corretti, rendono sbagliata l'evidenza raccolta fino al 28/09. Nessuna taratura.

| Priorità | Titolo | Finding | Test di esenzione |
|---|---|---|---|
| **P1** | `portfolio_daily_state.daily_return`: usare il NAV come denominatore, non il nozionale dei trade chiusi | DAY-014 / F-003 | **Sì.** La serie di rendimento giornaliero della finestra d'osservazione non misura il portafoglio: sbaglia di 25× oggi |
| **P1** | S4 ranker: escludere i candidati `anti_pyramiding` prima del taglio top-N | DAY-007 / F-051 | **Sì.** Ogni giornata osservata misura un ranker che spreca 5 slot su 6 su candidati inerti |
| **P1** | `s4_intent_events.is_tradable` → `rank_selected`, e allineare `dossier/book.py` | DAY-008 / F-045 | **Sì.** La guardia ombra di #335 pubblica `n_soppressi=0` su una popolazione del 9% credendola totale |
| **P1** | Archiviare i log dei container prima di ogni redeploy | DAY-002 / F-027 | **Sì.** Senza log, tutta l'evidenza non-DB della finestra è irrecuperabile a posteriori |
| **P2** | Separare `fallback_used` in `degraded_reason`, e propagare `eligible` sui contributori reali | DAY-004 / F-010 | **Sì.** LOO-ICIR non conta 38 contributori su 106 e S4 scarta il 36% dei segnali per un booleano ambiguo |
| **P2** | Finestre del beat dal calendario Alpaca invece che da ore UTC letterali | DAY-024 / F-021 | **Sì.** La finestra d'osservazione esclude sistematicamente i primi 30 minuti di ogni seduta EDT |
| **P2** | Estendere il batch controfattuale a `SKIP_FALLBACK` e `SKIP_STALE` | DAY-026 / F-060 | **Sì.** Il difetto più grande della giornata non ha misura automatica del suo costo |
| **P2** | Canale durevole per i CRITICAL del decay monitor + canary su `monitor_devices` | DAY-012 / F-062 | Strumentazione (come #161/#324): non cambia cosa si compra |
| **P2** | Decay monitor: metriche per sleeve e filtro sulle strategie non approvate | DAY-011 / F-004 | **Sì.** 6 CRITICAL/giorno indistinguibili dal rumore, di cui 2 su una strategia disabilitata |
| **P3** | `ENTRY_RECONCILIATION` idempotente sull'`order_id` (o vincolo UNIQUE sul derivato) | DAY-010 / F-061 | No: le viste `_current` contengono il danno. Igiene del ledger |
| **P3** | Vincolo di enum + normalizzazione Unicode su `risk_flags` | DAY-005 / F-055 | Prerequisito del gating QX-01, non urgente prima del golden set |
| **P3** | Prezzo di riferimento alla decisione per ogni ordine; `slippage_est` vero | DAY-022 / F-015 | No: nessuna decisione dipende oggi dalla qualità d'esecuzione |
| **P3** | Popolare `execution_decisions.signal_id` su tutte le dispositions | DAY-015 / F-011 | No: il join per simbolo+finestra funziona, con ambiguità |
| **P3** | Credenziali di sola lettura in produzione + `DATABASE_URL` distinta per i test | DAY-023 / F-039 | No oggi (nessuna riga spuria committata), ma il rischio è sul money-path |
| **P4** | SPCX fuori da `etf_broad`, in un gruppo coerente col cost tier | DAY-025 / F-034 | No: il cap non ha morso |
| **P4** | `ingestion_stats_daily`: separare `fetched_raw` da `fetched_new` | DAY-017 / F-007 | No: solo leggibilità della metrica |

---

## 16. Stato sistema

### Ollama

**UP per l'intera sessione. Zero ore di downtime.**

| Misura | Valore |
|---|---:|
| News processate | 100 |
| Risposte LLM totali | 198 |
| News con **entrambi** i modelli | 98 / 100 (98,0%) |
| News con un solo modello | 2 (DIS 9425, SPY 9460 — `glm-5.2` assente) |
| News con zero modelli (timeout totale) | **0** |
| Tasso di indisponibilità `glm-5.2` | 2,0% |
| Tasso di indisponibilità `gpt-oss` | 0,0% |
| Costo API | 0,1747 $ (99.735 token in, 7.723 out), budget non esaurito |

La strumentazione dedicata (`ensemble_cycle_health`, #427) **non era in produzione**: `dc83d23` è arrivato alle 20:20Z. Questi numeri sono ricostruiti da `llm_responses` e `sentiment_signals`.

### FinBERT — tasso di fallback

| Definizione | Valore |
|---|---:|
| `fallback_used=true` sui segnali | 44 / 106 = **41,5%** |
| di cui **FinBERT vero** (sostituzione per divergenza) | **6 / 106 = 5,7%** |
| di cui ensemble degradato a un modello (soglia conf. 0,40) | 38 / 106 = 35,8% |
| Fallback sulle **decisioni** (`SKIP_FALLBACK` / dispositions) | 122 / 1.189 = **10,3%** |
| Fallback sugli **ordini eseguiti** | **0 / 13 = 0,0%** |

Nessun ordine della giornata è nato da un segnale di fallback: i 3 ingressi S4 e l'uscita QQQ vengono tutti da segnali ensemble a due modelli.

### Circuit breaker

| Misura | Valore |
|---|---|
| Chiavi Redis `*breaker*` | **nessuna** |
| `fallback_counters.consecutive_fallback` | valore 0, ultimo incremento 18:52:50, azzerato 19:49:43 |
| Notifica di degradazione sostenuta (#427, item 3) | codice non in produzione durante la sessione |

Il breaker non è dimostrabilmente inattivo: è **non osservabile**.

### Worker restart events

| Container | Avviato | Restart count | Log del 09-01 |
|---|---|---:|---|
| `alembic-worker-1` | 2026-09-02T10:20:13Z | 0 | **assenti** |
| `alembic-worker-inference-1` | 2026-09-02T10:20:13Z | 0 | **assenti** |
| `alembic-api-1` | 2026-09-02T10:20:13Z | 0 | assenti |
| `alembic-beat-1` | 2026-09-02T10:20:13Z | 0 | assenti |
| `alembic-postgres-1` | ~2026-09-01T15:30Z (up 21 h) | 0 | — |
| `alembic-redis-1` | ~2026-09-01T15:30Z (up 21 h) | 0 | — |

**Restart durante la sessione del 09-01: 0 dimostrabili.** I container sono stati *ricreati* (non riavviati) alle 12:20Z del 09-01, prima dell'apertura, e poi alle 20:20Z, dopo la chiusura — entrambi da `deploy_reconcile.sh`, che rimanda correttamente a mercato aperto. `restart_count = 0` su tutti e quattro i container attuali, ma è il conteggio dall'avvio del 09-02: **eventuali crash-restart del 09-01 non sono più osservabili** (DAY-002).

### Altro

| Componente | Stato |
|---|---|
| Modelli dell'ensemble | `config:sentiment_llm_models = glm52,gptoss` ✔ (coerente con il registry) |
| Pesi dell'ensemble | glm-5.2 **0,700** / gpt-oss **0,300** (`auto_apply` del 2026-08-31 04:00, `icir` 0,1053 / −0,0050, VIX 15,21) |
| Gate d'ingresso S4 | `feedback:entry_threshold:S4 = 0.3` — **baseline, non ratchettato** ✔ |
| `pipeline_health` (13:30) | redis fresh, broker fresh, database fresh, **signal stale** (63.769 s), **portfolio_cycle stale** (63.479 s) — normale all'apertura, entrambi rientrati dal primo ciclo |
| `degradations` | `[]` su 86/86 snapshot |
| Shadow LLM (Stage 2 model comparison) | 212 righe in `llm_shadow_responses` ✔ |
| Stop shadow | 1.142 righe in `stop_shadow_log`, 0 in `stop_decisions` ✔ (design) |
| Canale d'allerta | **inesistente**: `mobile_events` 0, `mobile_event_history` 0, `mobile_notification_deliveries` 0, `monitor_devices` 0, `risk_reports.alerts = []` |

---

*Report generato in sola lettura. Nessun file di codice modificato, nessun commit, nessun ordine inviato, nessun worker avviato. Le occorrenze corrispondenti sono state appese a `docs/evidence/findings.json`; il commit è a carico di `scripts/commit_evidence_ledger.sh`.*
