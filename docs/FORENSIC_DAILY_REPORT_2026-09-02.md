# Forensic Daily Report — 2026-09-02

**Sessione:** analisi forense autonoma end-to-end del processo Alembic per la seduta del 2026-09-02.
**Modalità:** sola lettura. Nessun file di codice modificato, nessun ordine, nessun worker avviato, nessun commit. Unici file scritti: questo report e `docs/evidence/findings.json`.
**Timezone:** **UTC, verificato nel codice** — `src/workers/celery_app.py:52-53` (`timezone="UTC"`, `enable_utc=True`). Tutti i timestamp di questo report sono UTC. Il 2026-09-02 gli USA sono in EDT (UTC−4): RTH = **13:30–20:00 UTC**. Nessuna ambiguità di timezone: è invece un **difetto misurato** che le finestre `crontab` siano scritte in ora UTC fissa (§10, DAY-003).
**Codice in esecuzione durante la seduta:** commit `2b6513ad`. Il riconciliatore ha correttamente rinviato il rebuild a mercato aperto (`logs/deploy_reconcile_cron.log`, riga `2026-09-02T18:20:03Z Mercato aperto ... rimando`) e ha ridispiegato a `7c1fc823` alle **20:20:04 UTC**, dopo la chiusura. Il comportamento osservato è quindi attribuibile a un solo commit, senza discontinuità intra-seduta.
**Perimetro rispetto al report alpha:** `docs/ALPHA_MISS_REPORT_2026-09-02.md` (già scritto, con 13 occorrenze già registrate a ledger) copre **mercato, miss, copertura e qualità del segnale**. Questo report copre il **processo**: ingest, valutazione LLM, catena decisione→ordine→fill, riconciliazione, telemetria, allarmi e osservabilità. Dove i due si toccano lo dichiaro e **non riaddebito lo stesso dollaro** (§10, note di non-duplicazione).
**Regime di osservazione:** `docs/evidence/OBSERVATION_CHARTER.md`, taratura congelata fino al 2026-09-28. Nessuna soglia proposta. I ticket suggeriti in §15 sono solo di **correttezza/osservabilità**.

---

## 1. Executive summary

Il processo ha funzionato end-to-end e la catena ordine→fill→posizione **riconcilia esattamente** col broker: 7 ordini sul broker (6 filled + 1 stop protettivo cancellato), 6 righe corrispondenti a DB, 44 posizioni DB contro 44 posizioni broker con **quantità identiche** leggendo `quantity_remaining` (il campo introdotto da #397). Nessun ordine duplicato, nessun ordine fuori orario, nessun ordine senza risk check, nessun trade su ticker non consentito, paper mode verificato (`ALPACA_BASE_URL=https://paper-api.alpaca.markets`, chiave `PK…`). L'idempotenza ha funzionato ed è osservabile: 2 righe `SKIP_IDEMPOTENCY` nel ledger S4, client_order_id deterministici (`ambc-sell-HOOD-20260902T1507`). Nessun LLM è stato chiamato nel loop di trading (`portfolio_scheduler` legge solo DB/Redis) e la sanitizzazione del testo è applicata a corpo, titolo e ticker prima del prompt.

Ollama **non è mai caduto**: 23 cicli sentiment su 24 hanno prodotto ensemble, fallback totale 38/128 righe (29,7%), di cui **una sola** FinBERT (0,8%). Realizzato di giornata **−9,59 $** (S1 −29,38 $, S4 +19,79 $), 2,10 $ di costi, equity di chiusura 109.856,09 $.

I difetti trovati sono di **osservabilità e di attribuzione**, non di esecuzione. Tre pesano più degli altri. (a) Un ciclo sentiment su 24 (**17:30 UTC**) non è partito, il monitor l'ha visto, e **la causa non è più ricostruibile** perché il riconciliatore ha ridispiegato alle 20:20 distruggendo i log della seduta (17ª occorrenza di F-027, la prima in cui blocca una diagnosi concreta). (b) La catena segnale→decisione è rotta per chiave esterna su **686 righe su 696** (98,6%): tre delle cinque uscite della giornata citano il segnale causante solo nel testo del `reason`. (c) `ensemble_std` è persistito a **0,000 esatto** su 3 segnali in cui i due modelli distavano 0,50–0,60 di polarity, due dei quali sopra la magnitudine del gate.

## 2. Verdict finale

**OK con warning.**

L'esecuzione è corretta e riconciliata; nessuna delle anomalie ha prodotto un ordine sbagliato. Il warning è sull'**auditabilità**: la giornata è ricostruibile solo perché il dossier deterministico e i ledger S4 hanno retto — i log dei container sono spariti 20 minuti dopo la chiusura, il token REST del protocollo forense è rifiutato su tutti e 5 gli endpoint, e la chiave esterna che collega segnale e decisione è nulla nel 98,6% dei casi. Se domani un ordine fosse sbagliato, con questi tre difetti insieme non sarebbe diagnosticabile.

---

## 3. Timeline del 2026-09-02 (UTC)

| Ora | Componente | Evento | Esito | Fonte |
|---|---|---|---|---|
| 13:30:01 | mobile-monitor | `alert_incident` CRITICAL «Ciclo di portafoglio in ritardo» + WARNING «Segnali sentiment in ritardo» | aperti; recovered 14:08 / 14:01 | `mobile_events` |
| 13:30 | — | **apertura RTH. Nessun ciclo Alembic è schedulato prima delle 14:00** (`crontab hour="14-21"`) | 30-37 min di sessione scoperti | `celery_app.py:79,93,160` |
| 14:00:18→14:01:54 | sentiment (ciclo 1/24) | 9 articoli scorati, 9 ensemble, 0 single, 0 finbert | OK (95,8 s) | `ensemble_cycle_health` id 1 |
| 14:00 | ingestion | **57 articoli scartati `stale`** in un colpo solo, età 2,17h–18,73h; fra questi 4 pre-market su DELL | scarto strutturale | `news_queue_drops` |
| 14:07:00 | portfolio-cycle 1/24 | S1+S4; 5 ordini target, 0 inviati; 4 `SKIP_STALE`, 1 `SKIP_PYRAMIDING` (HOOD) | OK | `portfolio_cycles` 1302 |
| 14:12:00 | s4-lifecycle | `ENTRY_RECONCILIATION` HOOD+MSFT; ledger uscite P0/P1 popolato | OK | `s4_lifecycle_events`, `s4_exit_policy_events` |
| 14:45:23 | sentiment | segnale **9508 HOOD score 0,000 conf 0,15** da «This OGE Energy Analyst Turns Bullish…» (articolo che non nomina Robinhood) | ensemble, non-fallback | `sentiment_signals` |
| 15:00:22 | sentiment | segnale **9512 PANW +0,670 conf 0,80** (titolo earnings) su un titolo che chiude −9,28% | ensemble | `sentiment_signals` |
| 15:07:00→15:07:10 | portfolio-cycle | **SELL HOOD** 13,5265 @ 106,5652 — `below_entry_gate` sul segnale 9508 | filled; realizzato **+41,77 $** | decision 17223, order `5dda…a81d` |
| 15:16 / 15:45 / 16:15 | sentiment | DELL +0,3033 / +0,3033 / **+0,6363**: sopra gate | 3× `SKIP_PYRAMIDING` | `s4_intent_events` |
| 15:30:00 | sentiment (ciclo 7/24) | ciclo eseguito, **0 articoli** (5,8 s) | OK, nessun input | `ensemble_cycle_health` id 7 |
| 15:40:00 | mobile-monitor | WARNING «Segnali sentiment in ritardo» | recovered 15:46 | `mobile_events` |
| 15:45:21 | sentiment | **9529 MS +0,3575** da singolo modello (glm 0,00@0,15 ineleggibile, gpt-oss 0,55@0,65) — `ensemble_std` scritto **0,000** | escluso dal ranking (`SKIP_FALLBACK`) | `llm_responses` |
| 16:00:54 | sentiment | **9535 NVDA**: glm +0,700, gpt-oss −0,450, spread 1,15 → **FinBERT fallback** (unica riga FinBERT del giorno) | guardia di divergenza funzionante | `llm_responses` |
| 16:22:00→16:22:06 | portfolio-cycle | **SELL MSFT** 2,8280 @ 494,25 — `below_entry_gate` su 9545 (+0,231) | filled; realizzato **−19,12 $** | decision 17368 |
| **17:30:00** | sentiment (ciclo mancante) | **nessuna riga `ensemble_cycle_health`, nessuna riga `news_log`, nessun segnale** | **ciclo non eseguito** | assenza in 3 tabelle |
| 17:39:00 | mobile-monitor | WARNING «Segnali sentiment in ritardo», `age_seconds: 1419` | recovered 17:46 | `mobile_events` |
| 18:00:21 | sentiment | **9571 NVDA +0,4786 conf 0,68, ensemble_std 0,283** (glm +0,80@0,80, gpt-oss +0,40@0,55) | sopra gate | `sentiment_signals` |
| 18:00:32 | sentiment | **9572 PANW −0,4950 conf 0,83** | sopra soglia reversal | `sentiment_signals` |
| 18:07:00→18:07:07 | portfolio-cycle | **BUY NVDA** notional 1418,11 → 6,3086 @ 224,79 (unico ingresso del giorno) **+** **SELL PANW** 2,2748 @ 323,95 (`sentiment_reversal`, posizione **S1** aperta il 2026-07-13) | entrambi filled | decisions 17573/17574 |
| 18:12:00 | s4-exit-trial | `P0_OPEN_SNAPSHOT` + `P1_TIME_ONLY_DECISION` su NVDA (P1 due 2026-09-04) | OK | `s4_exit_policy_events` |
| 18:22:04 | portfolio-cycle | stop protettivo NVDA `sell stop qty 6` (su 6,3086) — **15 minuti dopo l'ingresso, solo parte intera** | accepted | order `40e8…4480` |
| 18:30:21 | sentiment | glm-5.2 **non risponde** (1 di 2 mancate risposte del giorno) → `single:gpt-oss` | fallback | `llm_responses` |
| 19:01:03 | sentiment | **9593 GS −0,4971 conf 0,73** da «Goldman Sachs warns investors to expect lower returns…» | sopra soglia reversal | `sentiment_signals` |
| 19:07:00→19:07:06 | portfolio-cycle | **SELL GS** 0,6452 @ 1002,15 (`sentiment_reversal`, posizione **S1** aperta il 2026-07-10) | filled; realizzato **−34,92 $** | decision 17695 |
| 19:45:19 | sentiment | **9614 NVDA +0,028 conf 0,20** da «Next Phase Of AI–Elon Musk's 1 Billion Robots» — **entrambi i modelli sotto il floor 0,30**, aggregato via retry a floor 0 | non-fallback per etichetta | `llm_responses` |
| 19:52:00→19:52:06 | portfolio-cycle 24/24 | **SELL NVDA** 6,3086 @ 224,38 — `below_entry_gate`; stop protettivo cancellato | filled; realizzato **−2,87 $** | decision 17800 |
| 20:00 | — | chiusura RTH. Ultimi cicli beat schedulati fino alle 21:52 (8 cicli sprecati) | — | `celery_app.py` |
| 20:12:03 | s4-exit-trial | `P1_TIME_DUE` su AVGO (−6,82 $) e XLE (+24,66 $) — uscite **virtuali**, nessun ordine | OK | `s4_exit_policy_events` |
| **20:20:04** | deploy_reconcile | **redeploy `2b6513ad → 7c1fc823`**, 4 container ricreati | **log della seduta distrutti** | `logs/deploy_reconcile_cron.log` |
| 21:00:00 | decay-monitor | **6 alert CRITICAL** (S1, S2, S4) con `actual_value` identico su tutte e tre le sleeve; S2 non è mai stata tradata | solo `log.critical`, nessun canale | log worker |
| 22:30:01 | risk-monitor | NAV 109.850,57; exposure 30,2%; HHI 0,0276; drawdown 1,24%; **`per_strategy_metrics = {}`**, `alerts = []` | 1 sola riga/giorno (by design) | `risk_reports` |
| 22:45:00 | counterfactual | 604/673 `SKIP_THRESHOLD` con controfattuale 1h; 69 skipped; overnight 0/696 | parziale | `execution_decisions` |
| 22:50:00 | held-news-loss-alert (#324) | apre WARNING «Copertura news assente su ASML» e «…su WDC» | **entrambi chiusi 0,35 s dopo** dal valutatore generico | `mobile_events` |

**Gap di cadenza:** i 24 cicli di portafoglio (14:07→19:52) sono regolari, zero gap oltre 16 minuti. I cicli sentiment sono 23 su 24 attesi: manca il **17:30**.

---

## 4. Tabella news ingest

### 4.1 Per fonte

| Fonte | `fetched` | `queued` | righe in `news_log` | ticker | `duplicates` | `no_ticker` | `stale` | `parse_fail` | Copertura temporale (fetch) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| alpaca_benzinga | 546 | 280 | **106** | 44 | 2135 | 0 | 54 | 0 | 14:00:41 → 19:46:10 |
| gdelt_gkg | 2134 | 22 | **22** | 12 | 3 | 2109 | 3 | 0 | 14:45:13 → 19:31:08 |
| **reuters** | 12 | 12 | **0** | 0 | 0 | 3 | 0 | 0 | riga scritta alle **15:07:07**, nessun articolo (§10 DAY-019) |
| **Totale reale** | — | — | **128** | **51** | — | — | — | — | 6 ore, zero gap orari |

Scarti registrati in `news_queue_drops` (che è la fonte fine, non i contatori aggregati): `duplicate_id` 2135 (150 simboli), `no_ticker` 2112, `not_tradable` 120 (99 simboli), `stale` 57 (42 simboli), `duplicate_content` 3.

**Copertura temporale e buchi.** Righe distribuite su tutte e 6 le ore 14–19 (23/20/32/6/20/27). Il buco non è orario ma **strutturale**: nessuna riga prima delle 14:00:41 — l'ingest non è schedulato prima delle 14:00 UTC. Tutti e **57 gli scarti `stale` cadono nell'ora 14:00**, con età da 2,17h a 18,73h: è l'intero arretrato notturno e pre-market buttato in un colpo solo al primo ciclo del giorno.

**Timestamp.** Zero righe con `published_at > fetched_at`, zero timestamp futuri. Latenza `published→fetched`: mediana **50,04 min**, massimo **113,00 min** contro un cap `MAX_NEWS_AGE_HOURS=2` (120 min): la coda arriva a 6 minuti dalla scadenza.

**Duplicati fra provider:** zero. Nessun `content_hash` compare su più di una fonte.

### 4.2 Per ticker (top 15 per righe)

| Ticker | Righe | Articoli unici | `max abs(score)` | Return seduta | Nota |
|---|---:|---:|---:|---:|---|
| NVDA | 9 | 9 | 0.4786 | +3,21% | 9 mappature su 9 `TAG_UNCONFIRMED`; comprato e venduto oggi |
| PANW | 8 | 8 | 0.6700 | −9,28% | score **positivo** 0,670 alle 15:00, negativo −0,495 alle 18:00 |
| DELL | 8 | 8 | 0.6363 | **+15,81%** | 3× `SKIP_PYRAMIDING`; 4 articoli pre-market scartati `stale` |
| GOOGL | 8 | 8 | 0.2100 | +0,63% | — |
| MU | 5 | 5 | 0.2100 | +2,43% | — |
| MSFT | 4 | 4 | 0.2307 | −0,84% | uscita 16:22 |
| SPCX | 4 | 4 | 0.1957 | −1,07% | contiene la riga con `risk_flag` malformato |
| SPY | 4 | 4 | 0.2299 | +0,44% | — |
| AVGO | 4 | 4 | 0.0960 | −0,66% | 1 mancata risposta glm |
| TSLA | 4 | 4 | 0.1200 | +0,26% | — |
| PLTR | 3 | 3 | 0.4200 | −5,81% | segno corretto sopra magnitudine gate, tutti `single:` → `SKIP_FALLBACK` |
| DB | 3 | 3 | 0.0200 | +2,32% | articoli su terzi, DB come casa d'analisi |
| DIS | 3 | 3 | 0.2100 | +1,66% | — |
| QQQ | 3 | 3 | 0.1346 | +0,23% | — |
| AAPL | 3 | 3 | 0.2600 | −0,05% | — |

**Fan-out.** 12 articoli mappati su più ticker; i tre maggiori: «Nvidia Jumps On AI Bid, Software Stocks Dip» su **12** ticker, «Top 12 Most-Searched Tickers» su **10**, «Next Phase Of AI–Elon Musk's 1 Billion Robots» su **9**. Due dei tre ordini di uscita della giornata derivano da uno di questi tre articoli.

**Estrazione ticker.** `source_metadata` 106 righe (alpaca_benzinga, tag del provider, **non validati**), `org_lookup` 22 righe (gdelt). Nessun'altra via. Il rilevatore `FALSE_ENTITY_MATCH` del dossier segnala 2 righe, entrambe `org_lookup`, **zero** su `source_metadata` (dettaglio già a ledger su F-057 dal report alpha).

**Sanitizzazione: presente e applicata.** `src/workers/sentiment.py:403-409` chiama `sanitize_text` su corpo e titolo e `sanitize_ticker` sul simbolo prima della costruzione del prompt; `src/llm/finbert.py:128` fa lo stesso sul ramo di fallback. Non è un'area di rischio oggi.

**Retry / failure silenziosi.** `parse_fail = 0` su entrambe le fonti reali. Nessun errore di fonte dati registrato.

---

## 5. Tabella performance modelli LLM

Ensemble attivo: `glm-5.2:cloud` + `gpt-oss:20b-cloud` (Ollama Cloud), `finbert` come fallback locale.

| Modello | Richieste | Risposte | Mancate | Polarity media | Polarity σ | Confidence media | min / max polarity | Latenza |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| gpt-oss:20b-cloud | 128 | 128 | **0** | +0,0509 | 0,2672 | 0,4221 | −0,700 / +0,800 | **non misurabile** |
| glm-5.2:cloud | 128 | 126 | **2** (18:30 GS, 19:00 AVGO) | +0,0521 | 0,2713 | **0,3401** | −0,700 / +0,850 | **non misurabile** |
| finbert (fallback) | 1 | 1 | 0 | — | — | 0,242 | — | — |

**Latenza: dato mancante.** `llm_responses` non ha colonna di latenza e i log del worker della seduta sono stati distrutti (§10 DAY-001). L'unica latenza misurabile è quella di stadio del dossier: `ingested→scored` ≈ 0 s (lo scoring avviene dentro il ciclo di ingest), `scored→ciclo eleggibile` mediana 6,48 min, `ordine→fill` mediana **0,6 s**.

**Composizione dei 128 segnali:**

| Percorso | n | % | Score medio | Confidence media | `ensemble_std` medio |
|---|---:|---:|---:|---:|---:|
| `ensemble:glm-5.2+gpt-oss` | 90 | 70,3% | +0,0418 | 0,3757 | 0,0607 |
| `single:gpt-oss:20b-cloud` | 30 | 23,4% | +0,0266 | 0,4787 | 0,000 |
| `single:glm-5.2:cloud` | 7 | 5,5% | −0,0068 | 0,7214 | 0,000 |
| `finbert` | 1 | 0,8% | +0,0174 | 0,242 | 0,000 |
| **fallback totale** | **38** | **29,7%** | | | |

**Distribuzione degli score.** 79/128 (61,7%) nel secchio [0,000; +0,193]; solo **5 segnali** con `|score| ≥ 0,40`; 12 segnali con `|score| ≥ 0,30` (il gate). Distribuzione della confidence fortemente bimodale: **41/128 (32%) a confidence ≤ 0,20**, cioè sotto il floor `min_confidence = 0,30` richiesto per un ingresso.

**Ticker con score estremi:** PANW +0,6700 (15:00) e −0,4950 (18:00) nella stessa seduta; DELL +0,6363; GS −0,4971; NVDA +0,4786; CRM +0,4950; PLTR −0,4200; XLE +0,4370.

**Disaccordo fra modelli.** 16 segnali con spread di polarity ≥ 0,30. Il caso estremo è **NVDA 9535** (glm +0,700 conf 0,80 contro gpt-oss −0,450 conf 0,70, spread **1,15**): la guardia di divergenza è scattata correttamente e il segnale è caduto su FinBERT. È l'unica riga FinBERT della giornata e **il meccanismo ha funzionato**.

**Casi in cui un solo modello ha dominato l'ensemble.** 3 segnali (PANW 9537, MS 9529, PLTR 9564) sono prodotti da un solo modello perché l'altro è caduto sotto il floor di confidence — e su tutti e tre `ensemble_std` è persistito a **0,000 esatto** mentre le due polarity distavano 0,60 / 0,55 / 0,50 (§10 DAY-006).

### 5.1 Verifica funzionale del ramo LLM

| Domanda | Risposta | Evidenza |
|---|---|---|
| L'output LLM è validato prima di entrare nel signal store? | **Parzialmente.** Polarity/confidence sono numerici e vincolati; `directness`, `event_type` e `risk_flags` sono **stringhe libere**: oggi compare il token malformato `amplechance_already_priced_in` (§10 DAY-009) | `llm_responses` id 15248 |
| L'ensemble gestisce la varianza alta? | **Sì sul ramo a due modelli** (NVDA 9535, spread 1,15 → FinBERT). **No quando un modello è ineleggibile**: il ramo single-model salta il calcolo e scrive `std = 0` | `src/llm/ensemble.py:246-256` |
| Le news duplicate pesano più volte? | **No fra provider** (zero `content_hash` condivisi) e la dedup per id ha scartato 2135 righe. **Sì per fan-out**: un articolo su 12 ticker genera fino a 12 righe scorate | `news_log`, `news_queue_drops` |
| La stessa news può generare segnali multipli? | **Sì, uno per ticker mappato.** «Nvidia Jumps On AI Bid…» ha generato i segnali NVDA +0,4786 e PANW −0,4950, che nello stesso ciclo delle 18:07 hanno prodotto **un BUY e una SELL** | decisions 17573/17574 |
| Confidence bassa riduce davvero il peso? | **Sì nell'aggregazione** (media pesata sulla confidence) e sì come filtro d'ingresso (`min_confidence = 0,30`). **No sul lato uscita**: HOOD chiusa su conf 0,15, NVDA su conf 0,20 (già a ledger su F-059 dal report alpha) | `sentiment_signals` |
| I modelli sono chiamati offline/background? | **Sì.** `portfolio_scheduler.py` non contiene alcuna chiamata a Ollama/FinBERT: legge `sentiment_signals` e Redis. Coda `inference` separata, concorrenza 1 | grep su `src/workers/portfolio_scheduler.py` |
| Un'allucinazione LLM può entrare direttamente in decisione? | **Sì, per il lato uscita.** La catena testo→score→`below_entry_gate`→SELL non ha alcun filtro di rilevanza né soglia di confidence; due delle cinque uscite di oggi ne sono un esempio (già a ledger su F-020/F-008) | §9 |

---

## 6. Tabella segnali finali per ticker (|score| ≥ 0,30)

| Ora | Ticker | Signal id | Score | Conf | `ensemble_std` | Percorso | Return seduta | Esito |
|---|---|---:|---:|---:|---:|---|---:|---|
| 15:00:22 | PANW | 9512 | **+0,6700** | 0,80 | 0,035 | ensemble | −9,28% | 4 intenti soppressi dalla **guardia ombra** #335 (segno contraddetto dal prezzo); nessun ordine |
| 15:16:00 | DELL | 9527 | +0,3033 | 0,65 | 0,071 | ensemble | +15,81% | `SKIP_PYRAMIDING` |
| 15:45:20 | DELL | 9528 | +0,3033 | 0,65 | 0,141 | ensemble | +15,81% | `SKIP_PYRAMIDING` |
| 15:45:21 | MS | 9529 | +0,3575 | 0,65 | **0,000** | single (gpt-oss) | +0,37% | `SKIP_FALLBACK` — escluso dal ranking |
| 15:45:40 | CRM | 9531 | +0,4950 | 0,83 | 0,000 | ensemble | −0,46% | `SKIP_PYRAMIDING` (già detenuto) |
| 16:01:21 | PANW | 9537 | −0,3000 | 0,50 | **0,000** | single (glm) | −9,28% | `RANK_LONG_ONLY` |
| 16:15:14 | DELL | 9543 | **+0,6363** | 0,83 | 0,071 | ensemble | +15,81% | `SKIP_PYRAMIDING` |
| 17:00:30 | PLTR | 9564 | −0,4200 | 0,60 | **0,000** | single (gpt-oss) | −5,81% | `SKIP_FALLBACK` |
| 18:00:21 | NVDA | 9571 | +0,4786 | 0,68 | **0,283** | ensemble | +3,21% | **BUY 18:07** |
| 18:00:32 | PANW | 9572 | −0,4950 | 0,83 | 0,000 | ensemble | −9,28% | **SELL 18:07** (`sentiment_reversal`) |
| 19:01:03 | GS | 9593 | −0,4971 | 0,73 | 0,035 | ensemble | +0,19% | **SELL 19:07** (`sentiment_reversal`) |
| 19:15:09 | XLE | 9595 | +0,4370 | 0,68 | 0,106 | ensemble | +0,51% | `SKIP_PYRAMIDING` (già detenuto) |

**Esiti sul lato ingresso (ledger `s4_intent_events`, 1438 intenti, 64 simboli):**

| Reason code | n | Nota |
|---|---:|---|
| `SKIP_ENTRY_GATE` | 673 | corrisponde 1:1 alle 673 `SKIP_THRESHOLD` in `execution_decisions` |
| `SKIP_ENTRY_FRESHNESS` | 472 | `signal_freshness_minutes = 30` |
| `SKIP_STALE` | 129 | `max_signal_age` |
| `SKIP_FALLBACK` | 85 | segnali single/FinBERT esclusi dal ranking BUY (#108) |
| `SKIP_PYRAMIDING` | 68 | |
| `RANK_LONG_ONLY` | 8 | PANW 5, GS 3 |
| `SKIP_IDEMPOTENCY` | **2** | **la guardia di idempotenza ha lavorato ed è osservabile** |
| `SUBMITTED` | **1** | NVDA |

**Guardia ombra di contraddizione (#335, read-only):** 25 intenti su 1438 in firing, 4 dei quali tradabili, **tutti PANW**. Nessuno eseguito, nessun costo. Il campo `giorno_di_earnings` vale `None` su 1438/1438 (calendario indisponibile: già a ledger su F-063 dal report alpha).

---

## 7. Tabella ordini generati / eseguiti

Riconciliazione broker↔DB su tutti e 7 gli ordini del giorno (Alpaca Trading API, lettura sola).

| # | Decisione (UTC) | Strategia | Ticker | Azione | Qty / Notional | Prezzo atteso | Prezzo fill | Stato | Motore | Segnale causante | Rationale | Risk check applicato | Anomalie |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 15:07:00 | S4 | HOOD | SELL (close) | 13,526494 | — | **106,5652** (15:07:10) | filled | paper Alpaca | 9508 (**non linkato**, solo nel testo) | `below_entry_gate`, score +0,000 age 0,4h | gate d'uscita + `exit_persistence_cycles=2` (14:52, 15:07) ✔ | segnale a conf 0,15 da articolo che non nomina il titolo (F-020, già a ledger) |
| 2 | 16:22:00 | S4 | MSFT | SELL (close) | 2,827953 | — | **494,25** (16:22:06) | filled | paper Alpaca | 9545 (**non linkato**) | `below_entry_gate`, score +0,231 | 2 cicli consecutivi sotto gate (16:07, 16:22) ✔ | — |
| 3 | 18:07:00 | S4 | NVDA | **BUY** | notional 1418,11 → 6,308555 | — | **224,79** (18:07:07) | filled | paper Alpaca | **9571** (linkato) | «S4 news-driven: sentiment +0,479… portfolio weight 2,0%» | gate 0,30 ✔, `regime_mult` 0,70 ✔, EMA ✔, no-pyramiding ✔, cap settore ✔ | `ensemble_std` 0,283 = 59% dello score, non è un gate (DAY-026) |
| 4 | 18:07:00 | **S1** | PANW | SELL (close) | 2,274756 | — | **323,95** (18:07:06) | filled | paper Alpaca | **9572** (linkato) | `sentiment_reversal: −0,495 < −0,35` | soglia reversal ✔ | overlay S4 chiude posizione **S1** aperta il 13/07 (DAY-010) |
| 5 | 18:22:04 | S4 | NVDA | SELL STOP protettivo | **qty 6** (su 6,3086) | trigger 187,95 | — | **canceled** 19:52 | paper Alpaca | — | stop GTC post-ingresso | — | creato **15 min dopo** l'ingresso; copre il **95,1%** della posizione (DAY-011) |
| 6 | 19:07:00 | **S1** | GS | SELL (close) | 0,645154 | — | **1002,15** (19:07:06) | filled | paper Alpaca | **9593** (linkato) | `sentiment_reversal: −0,497 < −0,35` | soglia reversal ✔ | overlay S4 chiude posizione **S1** aperta il 10/07 (DAY-010) |
| 7 | 19:52:00 | S4 | NVDA | SELL (close) | 6,308555 | — | **224,38** (19:52:06) | filled | paper Alpaca | 9614 (**non linkato**) | `below_entry_gate`, score +0,028 age 0,1h | `hold_minimum_minutes=90` ✔ (105 min), 2 cicli ✔ | segnale prodotto dal retry a floor 0 con **entrambi** i modelli sotto il floor (DAY-007) |

**Riconciliazione.** 7 ordini broker ↔ 7 eventi DB, quantità e prezzi identici al centesimo. `filled_qty = qty` su tutti e 6 gli ordini eseguiti, nessun fill parziale, nessun reject, nessuna cancellazione non voluta (l'unica cancellazione è lo stop protettivo, corretta perché la posizione era chiusa). Latenza `submitted→filled` mediana **0,6 s** (max 2,7 s).

**Telemetria del ciclo:** `sum(orders_count) = 74` su 24 cicli, contro **6 ordini realmente inviati** (§10 DAY-012).

---

## 8. Tabella PnL / rendimento

### 8.1 Realizzato (chiusure della seduta)

| Trade | Ticker | Sleeve | Ingresso | Uscita | Qty | Prezzo in | Prezzo out | Gross | Costi | **Net** | Motivo |
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|
| 962 | HOOD | S4 | 2026-09-01 | 15:07 | 13,5265 | 103,42 | 106,5652 | +42,54 | 0,77 | **+41,77** | `portfolio_sell` |
| 929 | MSFT | S4 | 2026-09-01 | 16:22 | 2,8280 | 500,91 | 494,25 | −18,83 | 0,28 | **−19,12** | `portfolio_sell` |
| 294 | PANW | S1 | 2026-07-13 | 18:07 | 2,2748 | 321,34 | 323,95 | +5,94 | 0,40 | **+5,54** | `sentiment_reversal` |
| 259 | GS | S1 | 2026-07-10 | 19:07 | 0,6452 | 1055,702 | 1002,15 | −34,55 | 0,37 | **−34,92** | `sentiment_reversal` |
| 966 | NVDA | S4 | **2026-09-02 18:07** | 19:52 | 6,3086 | 224,79 | 224,38 | −2,59 | 0,28 | **−2,87** | `portfolio_sell` |
| | **Totale** | | | | | | | **−7,49** | **2,10** | **−9,59** | |

Per sleeve: **S1 −29,38 $** (2 uscite, entrambe decise da un segnale S4), **S4 +19,79 $** (3 uscite).
Per origine: posizioni aperte **prima** del 2026-09-02 → −6,73 $ realizzati; posizione aperta **il** 2026-09-02 (NVDA) → −2,87 $ realizzati.

### 8.2 Non realizzato / MTM (48 posizioni vive all'open RTH, dossier `decision_quality.opening_snapshot`)

| Sleeve | Posizioni | Nozionale all'open | P&L passivo (close−open) | P&L effettivo | Effetto delle uscite |
|---|---:|---:|---:|---:|---:|
| S1 | 42 | 28.954,15 $ | +111,14 $ | +99,37 $ | −11,77 $ |
| S4 | 6 | 8.092,43 $ | +20,57 $ | +7,56 $ | −13,01 $ |
| **Totale** | **48** | **37.046,57 $** | **+131,71 $** | **+106,93 $** | **−24,78 $** |

**Attribuzione beta=1:** mercato (SPY) **+131,68 $**, settore incrementale +56,98 $, residuo −56,95 $. Il P&L passivo della giornata è **interamente beta di mercato**: 131,68 su 131,71. L'attribuzione settoriale però manca su 9 posizioni su 48 (§10 DAY-023).

**Book:** equity di chiusura **109.856,09 $** (`last_equity` broker), NAV nel risk report delle 22:30 **109.850,57 $**, esposizione 30,2%, HHI 0,0276, drawdown combinato 1,24%. Benchmark: SPY +0,44% sulla seduta.

**Slippage.** **Non misurato.** `trades.slippage_est` è identico a `cost_usd` su tutte e 6 le righe della giornata (0,77 / 0,28 / 0,40 / 0,37 / 0,28): è la stima di costo del modello, non una misura di qualità d'esecuzione (§10 DAY-013). La misura vera richiederebbe il mid NBBO al momento della submission confrontato col `filled_avg_price`; il dossier registra l'NBBO solo per il contesto di evento, non per gli ordini.

### 8.3 Dati non ricalcolabili qui

Il P&L economico della finestra di osservazione (`docs/evidence/economic_pnl.json`, rigenerato il 2026-09-03) dà, al 2026-09-02: **S1 +666,15 $** cumulati (contro un SPY-equivalente di +419,22 $ sullo stesso capitale, delta +246,93 $) e **S4 −400,77 $** cumulati, fuori dalla banda ±200 $ della carta. Giorno 23 su 40. Non ricalcolo questi numeri: li cito dalla loro fonte deterministica.

---

## 9. Analisi correttezza buy/sell

**Avvertenza obbligatoria su `exit_mechanism` (#184).** Questo report **non conta né interpreta** `exit_mechanism` su righe pre-fix. Le 3 righe della giornata con `exit_mechanism` popolato (`below_entry_gate` su HOOD, MSFT e NVDA) sono **post-fix** e riportano il motivo osservato, non una deduzione per età: il testo del `reason` contiene il timestamp e lo score del segnale letto al momento della decisione (`generated 2026-09-02 14:45 UTC, score=+0.000`), che è la firma delle righe post-#184 documentata in `docs/exit_mechanism_labels.md`. Le due `sentiment_reversal` hanno `exit_mechanism` NULL e sono classificate dal loro `reason` esplicito.

| Controllo | Esito | Evidenza |
|---|---|---|
| BUY generati solo quando consentito | ✔ | 1 solo BUY, score 0,4786 > gate 0,30, non-fallback, EMA pass, `regime_mult` 0,70, simbolo in watchlist, nessuna posizione S4 preesistente |
| SELL / exit generati correttamente | ✔ meccanicamente, ⚠ nel merito | tutte e 5 le uscite rispettano la regola scritta; due liquidano posizioni in rialzo su segnali a confidence 0,15 e 0,20 (già a ledger, F-020/F-008/F-059) |
| Stop-loss rispettati | ✔ con riserva | nessuno stop è scattato; **11 posizioni su 44 non hanno alcuno stop** (§10 DAY-011) |
| Signal flip rispettato | ✔ | PANW e GS chiusi su reversal −0,495 e −0,497 contro soglia −0,35 |
| Max holding days rispettato | ✔ | il trial P1 ha emesso `P1_TIME_DUE` su AVGO e XLE (D+2 scaduto) come uscite **virtuali**; nessun ordine reale, coerente col disegno del trial |
| Rebalance band rispettata | ✔ | zero `constraints_fired` su 24 cicli |
| Nessun ordine duplicato | ✔ | 7 client_order_id distinti e deterministici; 2 `SKIP_IDEMPOTENCY` provano che la guardia ha lavorato |
| Nessun ordine contrario ravvicinato senza rationale | ✔ | NVDA BUY 18:07 → SELL 19:52 = **105 min**, sopra `hold_minimum_minutes = 90`; il rationale è esplicito su entrambi i lati. Nessun roundtrip < 30 min |
| Nessun ordine su ticker non consentito | ✔ | 120 righe `not_tradable` scartate a monte (XLC, SIRI, SNDK, CVS, FTNT, BRK, BRK/A…) |
| Nessun ordine fuori orario | ✔ | tutti fra 15:07 e 19:52 UTC, dentro RTH 13:30–20:00 |
| Nessun trade su dati stale | ✔ | 129 `SKIP_STALE` + 472 `SKIP_ENTRY_FRESHNESS` nel ledger; 4 `SKIP_STALE` in `execution_decisions` |
| Nessun trade su output LLM non valido | ⚠ | nessun output *non parsabile* è entrato; ma `risk_flags`/`directness`/`event_type` non sono validati contro enum (DAY-009) |
| Nessun trade con circuit breaker attivo | ✔ | `fallback_counters.consecutive_fallback = 0`, resettato alle 19:46; il breaker non è mai scattato |
| Nessun trade con strategia disabilitata | ✔ | `strategies_run = ["S1","S4"]` su tutti e 24 i cicli |
| Paper/live coerente | ✔ | `ALPACA_BASE_URL=https://paper-api.alpaca.markets`, chiave `PK…`, `execution.engine = portfolio` |
| Idempotenza su retry Celery | ✔ | client_order_id deterministici + 2 `SKIP_IDEMPOTENCY` |
| Riconciliazione ordini↔fill↔posizioni | ✔ | 44 simboli DB = 44 simboli broker, quantità identiche su `quantity_remaining`; 1 sola posizione (NOK) con anomalia di attribuzione dei fill nel dossier (DAY-024) |

### Pattern operativi richiesti esplicitamente

| Pattern | Esito |
|---|---|
| Roundtrip < 30 min (buy+sell stesso simbolo stesso ciclo) | **Nessuno.** Il più corto è NVDA a 105 min |
| BUY ripetuto > 3 volte senza SELL (pyramiding) | **Nessuno.** 1 solo BUY nella giornata; 68 tentativi bloccati dal guard anti-pyramiding |
| SELL con sentiment positivo (bug A5) | **3 casi**: HOOD (score +0,000), MSFT (+0,231), NVDA (+0,028). **Non è il bug A5**: è il ramo `below_entry_gate`, che per costruzione chiude quando lo score scende sotto il gate d'ingresso, con `reason` esplicito. Il difetto reale è l'assenza di banda fra gate d'ingresso e soglia d'uscita (già a ledger su F-013 dal report alpha) |
| `fallback_used=True` su tutti i simboli in un periodo (Ollama giù) | **Nessuno.** Il fallback massimo orario è 50% (ore 16 e 17); ensemble presente in 21 cicli su 23 |
| NO-ORDER: decisione creata ma ordine non generato | **Nessuno.** Tutte e 6 le decisioni non-SKIP hanno `order_id` popolato e un ordine broker corrispondente |
| Score < 0,05 che hanno generato ordini | **2 casi, sul lato uscita**: HOOD su +0,000 e NVDA su +0,028. Sul lato ingresso, zero |
| Ordini identici nello stesso minuto (race scheduler) | **Nessuno.** Il ciclo 18:07 ha prodotto due ordini nello stesso secondo ma su simboli e lati diversi (BUY NVDA, SELL PANW), entrambi derivati dallo **stesso articolo** — comportamento coerente, non una race |

---

## 10. Anomalie trovate

Nessuna anomalia qui riportata propone una taratura: il periodo di sola osservazione è attivo. Le occorrenze già registrate dal report alpha della stessa giornata (F-001, F-008, F-009, F-012, F-013, F-020, F-030, F-031, F-040, F-057, F-059, F-060, F-063) **non sono ripetute** in questa sezione.

### [DAY-001] [F-027] I log della seduta analizzata sono stati distrutti 20 minuti dopo la chiusura, e questa volta bloccano una diagnosi

* Tipo: Bug
* Area: Ops
* Evidenza:
  * file/log/tabella: `logs/deploy_reconcile_cron.log`; `docker compose logs {worker,worker-inference,beat,api}`; `docker inspect`
  * timestamp: 2026-09-02T20:20:04Z
  * snippet/query: `2026-09-02T20:20:01Z Lock acquisito — avvio riconciliazione.` / `=== Riconciliazione 2b6513ad → 7c1fc823 (2 commit, da ricostruire: backend) ===`. `docker inspect` dà `StartedAt = 2026-09-02T20:20:14Z` su tutti e 4 i container; la prima riga di log disponibile è `beat-1 | [2026-09-02 20:20:22,776: INFO/MainProcess] beat: Starting...`
* Descrizione: il riconciliatore di deploy (cron `20 */2 * * *`) ha ridispiegato 20 minuti dopo la chiusura, ricreando i container e azzerandone i log. **Nota a favore del meccanismo:** la riconciliazione ha correttamente *rinviato* il rebuild alle 18:20 con la motivazione «Mercato aperto (o stato ignoto): rimando» — la disciplina di deploy funziona, è la ritenzione dei log che non esiste.
* Impatto: 17ª occorrenza, ma **la prima in cui costa una diagnosi concreta**. Il ciclo sentiment mancante delle 17:30 (DAY-002) non è più investigabile: non esiste alcuna traccia di eccezione, timeout o revoca del task.
* Severità: High
* Confidenza: High
* Azione consigliata: driver di logging persistente (`json-file` con rotazione su volume, o `journald`) sui 4 servizi, in modo che il redeploy non sia una cancellazione. È osservabilità pura: non tocca né soglie né comportamento.
* Test/monitor consigliato: assert nel forense giornaliero — `docker compose logs <svc> --since 24h | grep -c "<data analizzata>"` deve essere > 0, altrimenti il report dichiara "log non disponibili" in testa invece che a metà.

### [DAY-002] [F-065] Un ciclo sentiment su 24 non è partito e non ha lasciato traccia

* Tipo: Anomalia
* Area: LLM / Ops
* Evidenza:
  * file/log/tabella: `ensemble_cycle_health`, `news_log`, `sentiment_signals`, `mobile_events`
  * timestamp: 2026-09-02 17:30:00Z (atteso), allarme alle 17:39:00.972471Z
  * snippet/query: `SELECT cycle_started_at FROM ensemble_cycle_health WHERE cycle_started_at::date='2026-09-02'` → 23 righe, gli slot presenti sono 14:00…17:15 e 17:45…19:45, **manca il 17:30**. `SELECT fetched_at FROM news_log WHERE fetched_at BETWEEN '2026-09-02 17:15' AND '2026-09-02 17:45'` → 0 righe. `mobile_events`: WARNING «Segnali sentiment in ritardo», `details = {"age_seconds": 1419}`
* Descrizione: il beat schedula `sentiment-worker` e `run-alpaca-ingestion` ogni 15 minuti nelle ore 14–21. Lo slot delle 17:30 non ha prodotto **né** una riga di salute **né** un articolo **né** un segnale. Che l'assenza della riga di salute significhi "task non eseguito" e non "task eseguito a vuoto" è dimostrato dal ciclo delle 15:30, che ha girato senza articoli da scorare e ha comunque scritto la sua riga (`aggregate = 0`, durata 5,8 s). Il monitor ha rilevato il ritardo dopo 23,6 minuti; la causa resta ignota per DAY-001.
* Impatto: 30 minuti consecutivi senza scoring in piena sessione (17:15→17:45). Nessun ordine risulta perso in quella finestra, ma il buco è invisibile a posteriori se non incrociando tre tabelle: nessun contatore di cicli attesi contro cicli eseguiti esiste.
* Severità: Medium
* Confidenza: High
* Azione consigliata: ticket di correttezza per un contatore di copertura dei cicli (attesi vs eseguiti per giorno di borsa) alimentato da `ensemble_cycle_health`, così che un ciclo mancante sia un fatto misurato e non un'assenza da dedurre.
* Test/monitor consigliato: query giornaliera di copertura sui cicli attesi dal `crontab` contro le righe di `ensemble_cycle_health`; soglia di allarme sul conteggio, non sulla latenza.

### [DAY-003] [F-021] Le finestre beat in ora UTC fissa lasciano scoperti i primi 37 minuti di sessione e mandano al macero l'intero arretrato notturno

* Tipo: Bug
* Area: Data / Ops
* Evidenza:
  * file/log/tabella: `src/workers/celery_app.py:79,93,104,160`; `news_queue_drops`; `src/config.py:316`
  * timestamp: 2026-09-02 13:30:00Z (apertura) → 14:00:41Z (prima riga `news_log`); scarti alle 14:00
  * snippet/query: `crontab(minute="*/15", hour="14-21", day_of_week="1-5")`. `SELECT date_trunc('hour',dropped_at), count(*), min(age_hours), max(age_hours) FROM news_queue_drops WHERE dropped_at::date='2026-09-02' AND discarded_reason='stale' GROUP BY 1` → **una sola riga**: `14:00 | 57 | 2.17 | 18.73`
* Descrizione: in EDT l'apertura è alle 13:30 UTC ma nessun worker è schedulato prima delle 14:00, e il primo ciclo di portafoglio è alle 14:07. Combinato con `MAX_NEWS_AGE_HOURS = 2`, questo significa che ogni articolo pubblicato fra la chiusura precedente e circa le 12:00 UTC è **irrecuperabile per costruzione**: alle 14:00 ha già più di 2 ore. Oggi ne sono caduti 57, fra cui **4 articoli pre-market su DELL**, il primo mover dell'universo (+15,81%), incluso «12 Information Technology Stocks Moving In Wednesday's Pre-Market Session» a 2,17 ore d'età.
* Impatto: il sistema non può reagire a nessuna notizia pubblicata fuori dalla finestra 14–21 UTC, cioè a nessuna trimestrale rilasciata a mercati chiusi — che è quando le trimestrali vengono rilasciate. Oggi le tre punte dell'universo (DELL, PANW, SNOW) erano tutte reazioni a earnings.
* Severità: High
* Confidenza: High
* Azione consigliata: derivare le finestre beat dal calendario Alpaca invece che da ore UTC costanti (già `GetCalendarRequest` è usata altrove nel repo). È correttezza, non taratura: la finestra dichiarata è "la sessione", non "le ore 14–21".
* Test/monitor consigliato: test che, dato un calendario EST e uno EDT, la prima esecuzione schedulata cada ≤ apertura RTH; monitor giornaliero sul conteggio di `stale` concentrati nel primo ciclo.
* Nota di non-duplicazione: il controfattuale su DELL **non** è addebitato qui. Il report alpha ha già addebitato 54,52 $ a F-031 per l'anti-pyramiding, e un ingresso alle 14:07 (open 462,05) sarebbe stato **peggiore** di quello delle 15:22 (445,70) usato in quel calcolo: il costo incrementale dello scarto `stale` su DELL è nullo o negativo. Costo `null`.

### [DAY-004] [F-019] Metà della finestra di freschezza è consumata prima che il segnale esista, e due terzi del ritardo sono interni

* Tipo: Bug
* Area: News / Data
* Evidenza:
  * file/log/tabella: `docs/evidence/dossier/2026-09-02.json` → `timeline[].latenze_secondi` (131 righe)
  * timestamp: intera seduta
  * snippet/query: mediane su 128 righe — `published_to_first_seen` **8,68 min**, `first_seen_to_ingested` **31,14 min**, `ingested_to_scored` ≈ 0, `published_to_scored` **50,04 min** (max **113,00 min**), `scored_to_eligible_cycle` 6,48 min
* Descrizione: dei 50 minuti mediani che separano la pubblicazione dallo score, solo 8,7 sono esterni (ritardo del provider); **31,1 minuti sono coda interna** fra il primo avvistamento e l'ingestione, cioè circa due cicli da 15 minuti. Il cap di staleness è 120 minuti e l'articolo più lento della giornata è arrivato a 113: a 7 minuti dall'esclusione automatica.
* Impatto: il 42% della finestra di validità è già speso quando il segnale nasce, e la quota interna è la maggiore. Rispetto alla mediana storica di ~1h50m registrata su questo finding è un netto miglioramento, ma la composizione mostra che il collo è interno e non del provider.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna taratura. La misura per stadio è già disponibile nel dossier: va solo pubblicata come serie, per poter valutare l'effetto del consumo WebSocket (#455) quando sarà dispiegato.
* Test/monitor consigliato: serie giornaliera delle 4 mediane di stadio in `market_daily.jsonl`, con allarme quando `first_seen_to_ingested` supera due cicli di beat.

### [DAY-005] [F-011] La catena segnale→decisione è rotta per chiave esterna su 686 righe su 696, comprese 3 delle 5 uscite

* Tipo: Bug
* Area: Signal / Orders
* Evidenza:
  * file/log/tabella: `execution_decisions`
  * timestamp: 2026-09-02 14:07:03 → 19:52:04
  * snippet/query: `SELECT decision, count(*), sum((signal_id IS NULL)::int) FROM execution_decisions WHERE tick_time::date='2026-09-02' GROUP BY 1` → `SKIP_THRESHOLD 673/673`, `SKIP_FALLBACK 5/5`, `SKIP_STALE 4/4`, `SKIP_PYRAMIDING 8/1`, `SELL 5/3`, `BUY 1/0`
* Descrizione: 686 righe su 696 (**98,6%**) hanno `signal_id` NULL. Tre delle cinque SELL della giornata (HOOD, MSFT, NVDA — le tre `below_entry_gate`) citano il segnale causante **solo nel testo** del campo `reason` («generated 2026-09-02 19:45 UTC, score=+0.028»): per risalire al segnale bisogna fare parsing di una stringa in italiano/inglese, non un join.
* Impatto: qualunque analisi di attribuzione fatta per chiave esterna sottostima di due ordini di grandezza. Oggi il ledger `s4_intent_events` salva l'analisi (ha `signal_id` su tutti i 1438 intenti), ma è un secondo percorso, non lo stesso: se i due divergessero non ci sarebbe modo di accorgersene.
* Severità: High
* Confidenza: High
* Azione consigliata: popolare `execution_decisions.signal_id` sul ramo d'uscita, dove il segnale è già in mano al chiamante (lo scrive nel `reason`). È correttezza dell'evidenza: senza, la serie di 40 giorni non è ricostruibile per join.
* Test/monitor consigliato: invariante giornaliera — ogni riga `execution_decisions` con `decision IN ('BUY','SELL')` deve avere `signal_id NOT NULL` oppure una motivazione strutturale esplicita.

### [DAY-006] [F-054] `ensemble_std` è persistito a 0,000 esatto su tre segnali in cui i due modelli distavano 0,50–0,60 di polarity

* Tipo: Bug
* Area: LLM
* Evidenza:
  * file/log/tabella: `sentiment_signals` × `llm_responses`; `src/llm/ensemble.py:246-256`
  * timestamp: 15:45:21 (MS), 16:01:21 (PANW), 17:00:30 (PLTR)
  * snippet/query:
    * MS 9529 — `score +0,3575`, `ensemble_std 0,000`; risposte: `glm-5.2:cloud 0,00@0,15` e `gpt-oss:20b-cloud 0,55@0,65` — spread **0,55**
    * PANW 9537 — `score −0,3000`, `ensemble_std 0,000`; `glm −0,60@0,50`, `gpt-oss 0,00@0,20` — spread **0,60**
    * PLTR 9564 — `score −0,4200`, `ensemble_std 0,000`; `glm −0,20@0,30`, `gpt-oss −0,70@0,60` — spread **0,50**
* Descrizione: il filtro di eleggibilità gira **prima** del calcolo della divergenza (`Step 1: Eligibility Filtering` … `Step 2: If only one model is eligible: use it (no divergence possible)`), quindi quando un modello cade sotto `min_confidence` il ramo single-model salta lo Step 3 e scrive `std = 0`. Lo zero non significa "i modelli concordano": significa "non ho guardato". Due dei tre segnali superano la magnitudine del gate 0,30.
* Impatto: il campo che documenta l'accordo dell'ensemble afferma il contrario del vero proprio nei casi meno affidabili. **Onestà sulla portata**: la soglia della guardia è `std ≥ 0,40` e la σ di popolazione delle tre coppie vale 0,300 / 0,275 / 0,250 — quindi anche se la guardia fosse girata **non sarebbe scattata** su nessuno dei tre. Oggi il difetto è di registrazione, non di gate mancato: nessun ordine è stato prodotto (tutti e tre finiti in `SKIP_FALLBACK` o `RANK_LONG_ONLY`).
* Severità: Medium
* Confidenza: High
* Azione consigliata: calcolare e persistere la σ su **tutte** le risposte ricevute, indipendentemente dall'eleggibilità, in un campo distinto da quello usato per il gate. Non cambia alcuna soglia.
* Test/monitor consigliato: invariante — `ensemble_std = 0` è ammesso solo se le polarity grezze sono effettivamente identiche; altrimenti la riga è un errore di registrazione.

### [DAY-007] [F-010] Il segnale che ha liquidato NVDA è stato aggregato col retry a floor 0, con entrambi i modelli sotto la soglia di confidence

* Tipo: Bug
* Area: LLM / Orders
* Evidenza:
  * file/log/tabella: `sentiment_signals` 9614; `llm_responses`
  * timestamp: 2026-09-02 19:45:19Z (segnale) → 19:52:00Z (SELL)
  * snippet/query: segnale 9614 NVDA `score +0,0280`, `confidence 0,20`, `model_id = ensemble:glm-5.2:cloud+gpt-oss:20b-cloud`, `fallback_used = false`, `ensemble_std 0,141`; le due righe `llm_responses` collegate sono `glm 0,20@0,20 eligible=false` e `gpt-oss 0,00@0,20 eligible=false`. 12 segnali della giornata hanno la stessa firma (tutte le risposte `eligible=false` ma `fallback_used=false`)
* Descrizione: quando nessun modello raggiunge `min_confidence = 0,30`, il retry introdotto con #90 riaggrega con floor 0 e produce un risultato etichettato **ensemble non-fallback**, mentre ogni riga contribuente resta marcata `eligible=false`. La colonna `eligible` non registra quindi l'eleggibilità reale: i contributori veri di 12 segnali risultano non contributori. Il segnale 9614 è uno di questi ed è quello che, sette minuti dopo, ha chiuso la posizione NVDA.
* Impatto: due effetti distinti. (a) Audit: `llm_responses.eligible` non è utilizzabile per attribuire un segnale ai modelli che l'hanno prodotto. (b) Semantico: un segnale su cui **entrambi** i modelli dichiarano confidence 0,20 entra nel percorso d'uscita con la stessa dignità di uno a confidence 0,80, perché il lato uscita non applica alcun floor.
* Severità: Medium
* Confidenza: High
* Azione consigliata: distinguere nel dato persistito il ramo "floor 0" da quello ordinario (un `aggregation_mode` esplicito), invece di riusare `eligible` per due significati.
* Test/monitor consigliato: invariante — un segnale con `fallback_used=false` deve avere almeno una `llm_responses.eligible = true`, oppure un `aggregation_mode` che lo giustifichi.
* Nota di non-duplicazione: i 0,19 $ di `drift_post_uscita` di questa liquidazione sono già addebitati a F-008 dal report alpha. Qui il costo è `null`.

### [DAY-008] [F-023] Il segnale più forte della giornata su NVDA è stato sovrascritto da quattro segnali più deboli, e a decidere l'uscita è stato l'ultimo

* Tipo: Bug
* Area: Signal
* Evidenza:
  * file/log/tabella: `sentiment_signals` (9 righe NVDA), `execution_decisions` 17573 e 17800, `trades` 966
  * timestamp: 18:00:21 → 19:45:19
  * snippet/query: NVDA nella seduta — 9520 (15:15, +0,000), 9535 (16:00, +0,017 FinBERT), 9551 (16:16, +0,225), 9555 (16:30, +0,238), **9571 (18:00, +0,4786)**, 9589 (18:45, +0,000), 9591 (19:00, −0,034), 9605 (19:30, −0,050), **9614 (19:45, +0,028)**. BUY sul 9571, SELL sul 9614
* Descrizione: la selezione S4 tiene per ogni simbolo **solo il segnale più recente**, non il più forte né una loro composizione. Il segnale che ha motivato l'acquisto (+0,4786, confidence 0,68, articolo che parla esplicitamente del rialzo di NVDA) è stato sostituito 45 minuti dopo da un +0,000 su un pezzo di whale-alert, poi da due negativi deboli, infine da un +0,028 su un articolo il cui corpo dichiara di non parlare di singoli titoli. Nessuno dei quattro contraddice il primo: sono semplicemente più recenti.
* Impatto: la posizione è stata chiusa a 105 minuti dall'apertura per esaurimento della freschezza del segnale, non per un contro-segnale. Il meccanismo è lo stesso osservato su HOOD il 2026-09-01 e di nuovo su HOOD oggi.
* Severità: High
* Confidenza: High
* Azione consigliata: nessuna taratura ora. Ai fini dell'evidenza serve però che il dossier registri, per ogni uscita `below_entry_gate`, **quale sarebbe stato il massimo score nella finestra**: senza quel numero il costo di questo difetto non è stimabile in nessuna giornata.
* Test/monitor consigliato: campo derivato `max_score_in_window` accanto a `signal_score` sulle decisioni d'uscita.
* Nota di non-duplicazione: i −2,87 $ realizzati sono già addebitati a F-030 e i 0,19 $ di drift a F-008. Costo `null` qui.

### [DAY-009] [F-055] Un token malformato è entrato nel campo `risk_flags` senza che nulla lo rifiutasse

* Tipo: Bug
* Area: LLM / Data
* Evidenza:
  * file/log/tabella: `llm_responses` id 15248
  * timestamp: 2026-09-02, segnale 9523 (SPCX)
  * snippet/query: `SELECT unnest(risk_flags), count(*) FROM llm_responses WHERE generated_at::date='2026-09-02' GROUP BY 1` → `ambiguous_entity 114`, `low_source_quality 106`, `already_priced_in 56`, `rumor 7`, **`amplechance_already_priced_in 1`**
* Descrizione: il valore `amplechance_already_priced_in` non appartiene a nessun enum: è prosa del modello fusa con un flag valido, persistita senza validazione. `directness` e `event_type` sono soggetti allo stesso trattamento (`event_type` ha 10 valori distinti oggi, tutti plausibili, ma nulla lo garantisce).
* Impatto: qualunque conteggio o filtro su `risk_flags` è silenziosamente incompleto — un flag `already_priced_in` è sfuggito al conteggio perché scritto attaccato ad altro testo. Oggi nessuna decisione legge `risk_flags` (l'enforcement è gated su QX-01), quindi l'impatto è solo sulla misura; diventerebbe un impatto operativo il giorno in cui il gating si accende.
* Severità: Medium
* Confidenza: High
* Azione consigliata: validare gli enum in ingresso al persistore, scartando i token non riconosciuti in un campo `risk_flags_raw` invece di ammetterli nell'array tipizzato. È il prerequisito del gating `risk_flags` previsto da QX-01.
* Test/monitor consigliato: invariante giornaliera — zero valori di `risk_flags`, `directness`, `event_type` fuori dagli enum dichiarati.

### [DAY-010] [F-033] `sentiment_reversal` ha liquidato due posizioni S1 detenute da luglio, con la deroga #182(a) concessa ma non dispiegata

* Tipo: Bug
* Area: Orders / Risk
* Evidenza:
  * file/log/tabella: `execution_decisions` 17574 e 17695; `trades` 294 e 259; `docs/evidence/OBSERVATION_CHARTER.md` (riga di deroga 2026-08-25)
  * timestamp: 18:07:00Z (PANW), 19:07:00Z (GS)
  * snippet/query: `SELECT id,symbol,stop_strategy,entry_time,exit_time,exit_reason,net_pnl FROM trades WHERE exit_time::date='2026-09-02' AND exit_reason='sentiment_reversal'` → `294 | PANW | S1 | 2026-07-13 | +5,54` e `259 | GS | S1 | 2026-07-10 | −34,92`
* Descrizione: la deroga #182(a) del 2026-08-25 stabilisce che `sentiment_reversal` non chiuda più posizioni che S4 non ha aperto, e la riga di registro dice esplicitamente «deploy non ancora avvenuto — hash da inserire al merge». A otto giorni di distanza il meccanismo è ancora attivo: oggi ha chiuso **due posizioni S1** e **zero posizioni S4**, coerente con la misura che aveva motivato la deroga (22 uscite su 22 su titoli altrui).
* Impatto: la serie realizzata di S1 continua a essere prodotta in parte da decisioni S4. Il P&L S1 di oggi (−29,38 $) è **interamente** composto da queste due uscite; senza di esse S1 non avrebbe realizzato nulla. Per la domanda d'uscita del 28/09 su S1 questo è un contaminante diretto.
* Severità: High
* Confidenza: High
* Azione consigliata: nessuna nuova decisione — la decisione esiste dal 2026-08-25. Serve il **deploy** di #182(a), o in alternativa l'annotazione esplicita in `OBSERVATION_CHARTER.md` della data effettiva a partire dalla quale la serie sarà pulita.
* Test/monitor consigliato: invariante — una decisione `sentiment_reversal` che risolve a un `trades.stop_strategy` diverso da `S4` deve essere contata e pubblicata giornalmente.
* Costo: **misurata**, ma con una qualificazione stretta. Sul trade 259 (GS) il realizzato è −34,92 $; il report alpha ha già attribuito a F-020 solo il drift (**1,46 $**) come costo *della decisione*, perché la perdita era preesistente all'ingresso del 10/07. Il costo attribuibile a **questo** finding è la parte che non sarebbe stata realizzata affatto se il meccanismo fosse stato dispiegato: le due posizioni sarebbero rimaste aperte, quindi il realizzato di S1 sarebbe stato 0 $ e le posizioni avrebbero chiuso a MTM. PANW: uscita 323,95 contro close 328,48 → **−10,30 $** rispetto al tenere; GS: uscita 1002,15 contro close 1004,42 → **−1,46 $**. Costo dell'occorrenza = **11,76 $**.

### [DAY-011] [F-022] Undici posizioni su quarantaquattro non hanno alcuno stop protettivo, e quello creato oggi copre solo la parte intera

* Tipo: Anomalia
* Area: Risk
* Evidenza:
  * file/log/tabella: Alpaca Trading API (ordini aperti), `trades` (posizioni vive)
  * timestamp: stop NVDA creato 18:22:04Z, ingresso 18:07:07Z
  * snippet/query: 33 ordini `sell stop` aperti contro 44 posizioni. Senza stop: **AMAT, AMD, ASML, CAT, DELL, LLY, MRVL, MU, NOK, SPY, WDC** — tutte con quantità < 1 azione. Nozionale scoperto (market value broker): 372,83 + 370,19 + 623,54 + 730,04 + 453,10 + 807,01 + 112,87 + 379,46 + 5,48 + 693,81 + 149,00 = **4.697,33 $**. Lo stop NVDA di oggi: `sell stop qty 6` su una posizione di 6,308555 (copertura 95,1%)
* Descrizione: due facce dello stesso vincolo — Alpaca non accetta stop su quantità frazionarie. Le posizioni sotto 1 azione restano interamente scoperte; quelle sopra 1 azione sono coperte solo per la parte intera. In più lo stop arriva **un ciclo dopo** l'ingresso: la posizione NVDA è rimasta 15 minuti senza protezione.
* Impatto: 12,7% del nozionale di libro (4.697 $ su 37.047 $ all'open) è privo di stop, e sono in gran parte le posizioni più vecchie e più in perdita (ASML −4,89% dall'ingresso, WDC −18,27%). La condizione di revisione documentata in `config/trading.yaml:180-182` è la stessa già registrata su #161.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna (la size minima ≥ 1 azione è taratura, congelata al 28/09). Serve però che il numero sia **pubblicato ogni giorno** invece di essere riscoperto: `scripts/check_unprotected_positions.py` esiste già e non è in crontab.
* Test/monitor consigliato: riga giornaliera in `market_daily.jsonl` con conteggio e nozionale delle posizioni senza stop.

### [DAY-012] [F-014] La telemetria del ciclo dichiara 74 ordini contro i 6 realmente inviati

* Tipo: Bug
* Area: Ops
* Evidenza:
  * file/log/tabella: `portfolio_cycles`
  * timestamp: 24 cicli, 14:07 → 19:52
  * snippet/query: `SELECT sum(orders_count), sum(jsonb_array_length(final_orders)), count(*) FROM portfolio_cycles WHERE timestamp::date='2026-09-02'` → `74 | 74 | 24`. Ordini realmente inviati al broker nella stessa finestra: **6**
* Descrizione: `orders_count` è esattamente `jsonb_array_length(final_orders)`, cioè conta gli ordini **target** del combiner, non quelli sottomessi. Il rapporto è 12:1.
* Impatto: chiunque legga `portfolio_cycles` per stimare l'attività di trading sbaglia di un ordine di grandezza. Il campo ha un nome che promette una cosa e ne misura un'altra.
* Severità: Low
* Confidenza: High
* Azione consigliata: rinominare in `target_orders_count` e affiancare `submitted_orders_count`. Puramente nominale, nessun comportamento cambia.
* Test/monitor consigliato: invariante — `submitted_orders_count` deve pareggiare il conteggio delle `execution_decisions` con `order_id NOT NULL` nello stesso tick.

### [DAY-013] [F-015] `slippage_est` è una copia di `cost_usd` su tutte e sei le righe della giornata

* Tipo: Bug
* Area: PnL
* Evidenza:
  * file/log/tabella: `trades`
  * timestamp: 2026-09-02
  * snippet/query: trade 966 (NVDA) → `cost_usd = 0,28`, `slippage_est = 0,28`. Idem sulle altre quattro chiusure (0,77 / 0,28 / 0,40 / 0,37)
* Descrizione: il campo destinato a misurare la qualità d'esecuzione riporta la stima di costo del modello. Non esiste alcun confronto fra prezzo atteso e prezzo di fill.
* Impatto: la qualità d'esecuzione non è misurata da nessuna parte. Oggi non è un problema economico (fill in 0,6 s mediani su titoli molto liquidi), ma è un buco strutturale nella §6 del protocollo forense: alla domanda "quanto è costato lo slippage" la risposta corretta è "non lo sappiamo".
* Severità: Low
* Confidenza: High
* Azione consigliata: registrare il mid NBBO al momento della submission (l'infrastruttura c'è già: il dossier lo cattura per il contesto d'evento) e calcolare lo slippage come differenza col `filled_avg_price`.
* Test/monitor consigliato: invariante — `slippage_est` deve essere NULL finché non è misurato davvero, invece di duplicare `cost_usd`.

### [DAY-014] [F-050] Nessun drawdown per sleeve è monitorato: `per_strategy_metrics` è vuoto e `alerts` non può scattare

* Tipo: Anomalia
* Area: Risk
* Evidenza:
  * file/log/tabella: `risk_reports`
  * timestamp: 2026-09-02 22:30:01.139124Z
  * snippet/query: `per_strategy_metrics = {}`, `alerts = []`, `combined_drawdown = 0.012429`, `nav = 109850.57`
* Descrizione: 5ª occorrenza consecutiva. Dopo la rimozione dell'entrata sintetica `portfolio` (#349) il report di rischio calcola solo l'aggregato: né S1 né S4 hanno un drawdown proprio, quindi nessun kill-switch per-sleeve può essere valutato.
* Impatto: il rischio è sorvegliato solo a livello di libro. Una sleeve può andare in drawdown profondo mentre l'altra la compensa, senza che nulla lo segnali.
* Severità: Medium
* Confidenza: High
* Azione consigliata: ricostruire `per_strategy_metrics` da `trades.stop_strategy` (che oggi è popolato su 100% delle posizioni dello snapshot, vedi §11), senza reintrodurre l'entrata sintetica rimossa.
* Test/monitor consigliato: invariante — `per_strategy_metrics` deve avere una chiave per ogni sleeve presente in `strategies_run`.

### [DAY-015] [F-004] Il decay monitor confronta la stessa metrica globale contro tre baseline, inclusa una strategia mai tradata

* Tipo: Bug
* Area: Ops
* Evidenza:
  * file/log/tabella: log worker (unico frammento sopravvissuto al redeploy)
  * timestamp: 2026-09-02 21:00:00,032–060Z
  * snippet/query:
    ```
    DECAY CRITICAL [S1]: IC dropped 187% from 0.035 to -0.031
    DECAY CRITICAL [S2]: IC dropped 173% from 0.042 to -0.031
    DECAY CRITICAL [S4]: IC dropped 209% from 0.028 to -0.031
    DECAY CRITICAL [S1]: Hit rate dropped 27.1pp from 54.0% to 26.9%
    DECAY CRITICAL [S2]: Hit rate dropped 29.1pp from 56.0% to 26.9%
    DECAY CRITICAL [S4]: Hit rate dropped 25.1pp from 52.0% to 26.9%
    ```
* Descrizione: il valore *attuale* è identico sulle tre sleeve (**−0,031** di IC, **26,9%** di hit rate); a variare è solo la baseline. È una sola metrica di pipeline confrontata con tre riferimenti diversi, e uno dei tre è **S2, che non è nemmeno fra le `strategies_run`** della giornata.
* Impatto: sei alert CRITICAL che non distinguono le sleeve. Con S1 e S4 che oggi hanno realizzato segno opposto (−29,38 $ contro +19,79 $), un decay identico su entrambe non può essere informativo.
* Severità: Medium
* Confidenza: High
* Azione consigliata: calcolare l'IC e l'hit rate **per sleeve** dalle rispettive righe di `trades`, e rimuovere S2 dall'elenco finché non esiste.
* Test/monitor consigliato: invariante — due sleeve non possono avere lo stesso `actual_value` a meno che le loro popolazioni di trade non coincidano.

### [DAY-016] [F-062] Sei alert CRITICAL sono stati emessi su un canale che nessuno legge

* Tipo: Bug
* Area: Ops
* Evidenza:
  * file/log/tabella: log worker 2026-09-02 21:00; `mobile_events`
  * timestamp: 2026-09-02 21:00:00Z
  * snippet/query: i 6 `log.critical` del decay monitor non hanno alcuna riga corrispondente in `mobile_events` (che nella giornata contiene solo 7 eventi, nessuno di categoria decay) né alcun invio Telegram
* Descrizione: 2ª occorrenza. `decay_monitor_task` dispaccia i CRITICAL con `log.critical(...)` e nient'altro; non esiste `AlertService`, né riga mobile, né notifica. E poiché i log non sopravvivono al redeploy (DAY-001), l'alert ha una vita utile di poche ore.
* Impatto: la severità più alta del sistema è l'unica priva di canale. Oggi i sei alert sono sopravvissuti solo perché sono stati emessi **dopo** il redeploy delle 20:20: se il redeploy fosse avvenuto alle 21:20 anziché alle 20:20 non ne resterebbe traccia.
* Severità: High
* Confidenza: High
* Azione consigliata: instradare i CRITICAL del decay monitor sullo stesso canale `mobile_events` già usato dagli altri job. È osservabilità pura.
* Test/monitor consigliato: invariante — ogni `log.critical` emesso da un task schedulato deve avere una riga `mobile_events` corrispondente.

### [DAY-017] [F-058] I due alert di copertura aperti dal job #324 sono stati chiusi 0,35 secondi dopo dal valutatore generico

* Tipo: Bug
* Area: Ops
* Evidenza:
  * file/log/tabella: `mobile_events`
  * timestamp: aperti 2026-09-02 22:50:00.707247Z e 22:50:00.716237Z, risolti 22:50:01.060889Z e 22:50:01.046311Z
  * snippet/query: «Copertura news assente su ASML» e «Copertura news assente su WDC», `status = recovered`, `clear_observation_count = 1`, durata **0,354 s** e **0,330 s**
* Descrizione: 2ª occorrenza, sullo stesso job e con lo stesso meccanismo del primo avvistamento (2026-08-31). Il job `held-news-loss-alert` (cron 22:50) apre correttamente i due incidenti; il valutatore mobile generico, che gira ogni minuto, non riconosce quei fingerprint come propri, non trova la condizione nel suo insieme di regole e li dichiara rientrati.
* Impatto: la deroga registrata il 2026-08-31 per l'alert #324 è di fatto inefficace: gli incidenti che apre non arrivano mai a un operatore. E il caso è proprio quello che la deroga voleva coprire — **ASML è alla nona seduta consecutiva senza una riga di news** mentre è a −4,89% dall'ingresso.
* Severità: High
* Confidenza: High
* Azione consigliata: il valutatore generico deve chiudere solo i fingerprint di cui è proprietario (namespace per job emittente); dato incompleto → nessuna azione, non chiusura.
* Test/monitor consigliato: test — un incidente aperto da un job specializzato non deve cambiare stato al primo giro del valutatore generico.

### [DAY-018] [F-061] Il ledger append-only riemette lo stesso evento derivato a ogni ciclo

* Tipo: Bug
* Area: Data
* Evidenza:
  * file/log/tabella: `s4_exit_policy_events`, `s4_lifecycle_events`
  * timestamp: 14:12:03.704781Z e 15:12:04.090056Z
  * snippet/query: due righe `P0_RUNTIME_REPLAY` per lo **stesso** `intent_id = bed2e4d0-2b81-58fc-9c33-ebc9daeb616f` (HOOD), stesso `observed_at`, stesso `fill_price` 104,73, stesso `net_pnl` −23,791116468878734, ma `event_id` diversi (`1de58677…` e `f214304a…`) perché differisce l'`entry_lifecycle_event_id` a monte. In parallelo `ENTRY_RECONCILIATION` su HOOD è riemessa alle 14:12 e alle 15:12 con payload identico (`requested_notional 1419.36`), e su NVDA alle 18:12 e 19:57
* Descrizione: l'identità dell'evento derivato include quella dell'osservazione a monte, che a sua volta non è idempotente: ogni ciclo riconcilia da capo e produce un nuovo `entry_lifecycle_event_id`, che genera un nuovo `event_id` per lo stesso fatto.
* Impatto: qualunque conteggio sul ledger delle uscite S4 sovrastima. Oggi 9 righe `ENTRY_RECONCILIATION` per 4 eventi di ingresso distinti. È il ledger su cui poggia il trial S4, quindi è un difetto sull'evidenza, non sul denaro.
* Severità: Medium
* Confidenza: High
* Azione consigliata: rendere idempotente `ENTRY_RECONCILIATION` (chiave naturale su `intent_id` + `broker_order_id`), così che l'identità a valle smetta di biforcarsi.
* Test/monitor consigliato: invariante — `count(DISTINCT event_id) = count(DISTINCT (intent_id, policy_id, event_type, observed_at))`.

### [DAY-019] [F-028] La suite di test ha scritto di nuovo nel database di produzione durante la seduta

* Tipo: Bug
* Area: Data
* Evidenza:
  * file/log/tabella: `ingestion_stats_daily`, `news_log`
  * timestamp: riga scritta 2026-09-02 15:07:07.060929Z (**a mercato aperto**)
  * snippet/query: `SELECT * FROM ingestion_stats_daily WHERE day='2026-09-02' AND source='reuters'` → `fetched 12, queued 12, duplicates 0, discarded_no_ticker 3, parse_fail 0`. `SELECT count(*) FROM news_log WHERE source='reuters'` → **0, da sempre**. La serie storica di queste righe è una firma di fixture: valori sempre multipli di 4 con rapporto fisso 4:1 fra `fetched` e `discarded_no_ticker` (4/1, 8/2, 12/3, 20/5, 24/6, 36/9, 48/12, 56/14), su 20 giorni distinti a ore arbitrarie (06:08, 08:37, 23:06)
* Descrizione: 9ª occorrenza. Un connettore `reuters` che non esiste in produzione scrive statistiche di ingestione nel DB live. Oggi la riga è stata scritta **alle 15:07 UTC, cioè in piena sessione**, non a mercato chiuso.
* Impatto: contamina la tabella delle statistiche di ingestione, che è una delle fonti dei conteggi di copertura. Il rischio non è teorico: la stessa configurazione che permette a un test di scrivere `ingestion_stats_daily` gli permetterebbe di scrivere altre tabelle.
* Severità: High
* Confidenza: High
* Azione consigliata: isolare la suite dal DSN di produzione (fixture con database dedicato, o guardia che rifiuti la connessione quando il nome del DB è quello live). È correttezza dell'evidenza.
* Test/monitor consigliato: invariante giornaliera — nessuna riga in `ingestion_stats_daily` con `source` non presente nell'elenco dei connettori configurati.

### [DAY-020] [F-007] Il contatore dei duplicati vale quasi quattro volte il fetched dello stesso giorno

* Tipo: Anomalia
* Area: Data
* Evidenza:
  * file/log/tabella: `ingestion_stats_daily`, `news_queue_drops`
  * timestamp: aggiornata 2026-09-02 19:45:01.089138Z
  * snippet/query: `alpaca_benzinga` → `fetched 546`, `queued 280`, `duplicates 2135` (**3,9×** il fetched), `discarded_stale 54`. Il conteggio fine in `news_queue_drops` concorda esattamente (2135 righe `duplicate_id`), quindi non è un errore di contatore: è il `fetched` a non contare le stesse cose
* Descrizione: 19ª occorrenza. `fetched` misura una cosa (articoli restituiti dall'endpoint in un ciclo) e `duplicates` un'altra (mappature ticker-articolo già viste, sommate su tutti i cicli): i due non sono commensurabili e la tabella li presenta come se lo fossero.
* Impatto: qualunque rapporto di efficienza dell'ingest calcolato da questa tabella è privo di significato. La misura vera esiste in `news_queue_drops` ed è più severa: 2135 righe riscaricate e ributtate ogni giorno.
* Severità: Low
* Confidenza: High
* Azione consigliata: documentare la semantica dei due contatori nello schema o normalizzarli sulla stessa unità. Nessun comportamento cambia.
* Test/monitor consigliato: assert che `duplicates ≤ fetched × n_cicli`, altrimenti la semantica è cambiata senza che nessuno l'abbia dichiarato.

### [DAY-021] [F-041] Il token del protocollo forense è rifiutato su tutti e cinque gli endpoint REST

* Tipo: Bug
* Area: Ops
* Evidenza:
  * file/log/tabella: API locale `http://localhost:8001/api`
  * timestamp: 2026-09-03, durante questa analisi
  * snippet/query: `curl -s -H "Authorization: Bearer eJvMeuHhJS27FPugKIu4qKGgV7roIdLfcv7h20MwuQg" "$BASE/orders?limit=200"` → `{"detail":"Invalid or expired JWT token"}`. Identico su `/decisions`, `/trades`, `/signals`, `/positions`
* Descrizione: 9ª occorrenza. I cinque endpoint prescritti dal protocollo forense sono inutilizzabili. L'analisi ha dovuto passare interamente per query SQL dirette e per l'SDK Alpaca.
* Impatto: il protocollo forense prescrive una via d'accesso che non funziona da nove sedute. Chi lo eseguisse alla lettera, senza fallback SQL, produrrebbe un report vuoto e lo dichiarerebbe "non verificabile".
* Severità: Medium
* Confidenza: High
* Azione consigliata: allineare il protocollo alla realtà — o correggere l'header/token, o sostituire le cinque righe `curl` del prompt con le query SQL equivalenti, che funzionano.
* Test/monitor consigliato: smoke test giornaliero sui cinque endpoint con il token del protocollo.

### [DAY-022] [F-016] Il fetch del benchmark SPY fallisce in ciclo stretto, senza alcun allarme

* Tipo: Anomalia
* Area: Data
* Evidenza:
  * file/log/tabella: log worker
  * timestamp: continuo; frammento osservabile 2026-09-03 00:00:01 → 00:13:03
  * snippet/query: `docker compose logs worker | grep -c "SPY benchmark fetch failed"` → **84 righe in 14 minuti distinti**, cioè 6 tentativi al minuto, ogni minuto. Messaggio: `{"message":"subscription does not permit querying recent SIP data"}`
* Descrizione: 5ª occorrenza. Il fallimento è permanente (limite di sottoscrizione SIP, non transitorio) ma la logica riprova sei volte al minuto indefinitamente, a livello WARNING, senza mai emettere un allarme né disattivarsi.
* Impatto: due effetti. Il confronto col benchmark non è disponibile nel percorso live (lo scoreboard economico lo calcola per altra via, con dati daily). E le 84 righe/quarto d'ora sono rumore che rende i log — già di vita breve per DAY-001 — meno leggibili.
* Severità: Low
* Confidenza: High
* Azione consigliata: circuito aperto sul fallimento permanente (riconoscere il messaggio di sottoscrizione come non ritentabile) e un solo evento riassuntivo al giorno.
* Test/monitor consigliato: allarme sul rapporto fra righe WARNING ripetute e righe totali di log per servizio.

### [DAY-023] [F-064] L'attribuzione beta=1 lascia nove posizioni su quarantotto senza benchmark settoriale, e non lo dichiara in `missingness`

* Tipo: Bug
* Area: PnL / Data
* Evidenza:
  * file/log/tabella: `docs/evidence/dossier/2026-09-02.json` → `decision_quality.opening_snapshot[].beta_1_attribution`
  * timestamp: dossier generato 2026-09-03T08:00:21Z
  * snippet/query: `sector_incremental_usd` e `residual_usd` sono `null` su **RIO, ROKU, SPY, NOK, VALE, GM, IWM, CAT, SBUX** — i settori `materials`, `media`, `etf_broad`, `telecom`, `consumer`, `industrials` non hanno un ETF in `SECTOR_ETF_BY_SECTOR`. Su 8 di queste 9 posizioni il campo `missingness` è **`[]`**, cioè dichiara che non manca nulla
* Descrizione: il contratto del dossier è esplicito («Dato incompleto → UNKNOWN», «`None` quando barra, prezzo d'ingresso o calendario mancano») e la mappa settore→ETF è dichiarata «benchmark-only». Ma quando la mappa non copre il settore, la scomposizione non viene prodotta e l'assenza non viene annotata: un consumatore che legge `missingness == []` conclude che l'attribuzione è completa.
* Impatto: l'attribuzione settoriale copre 39 posizioni su 48 e il totale settoriale pubblicato (+56,98 $) è calcolato su un sottoinsieme non dichiarato. Contano fra le escluse VALE (+4,03% oggi) e CAT (+1,68%). È un difetto dello **strumento di misura** con cui al 28/09 si risponderà alla domanda su dove nasce il rendimento delle sleeve.
* Severità: Medium
* Confidenza: High
* Azione consigliata: aggiungere `sector_benchmark_unavailable` a `missingness` quando la mappa non copre il settore, e pubblicare accanto al totale settoriale la quota di nozionale su cui è calcolato.
* Test/monitor consigliato: invariante sul dossier — ogni campo `null` in `beta_1_attribution` deve avere una voce corrispondente in `missingness`.
* Nota sull'id nuovo: nessuno dei 63 finding esistenti riguarda il contratto di `missingness` del dossier. F-063 descrive un campo `None` **correttamente** dichiarato (calendario earnings); F-045 era un confronto `is_tradable` che non poteva mai essere vero; F-034 riguarda i tier di costo mancanti in `cost_model.yaml`, non l'attribuzione. Il meccanismo qui è opposto a quello di F-063: un `null` **non** dichiarato.

### [DAY-024] [F-048] I fill d'uscita di un trade chiuso a luglio sono attribuiti al trade aperto sullo stesso simbolo

* Tipo: Bug
* Area: PnL / Data
* Evidenza:
  * file/log/tabella: `docs/evidence/dossier/2026-09-02.json` → `copertura_uscita`/`opening_snapshot` per NOK; `src/analysis/dossier/decision_quality.py:152-154`; Alpaca order history
  * timestamp: dossier 2026-09-03T08:00:21Z
  * snippet/query: NOK è l'unica delle 48 posizioni con `missingness: ["exit_fill_qty_exceeds_trade_qty"]`. Storico broker NOK: BUY 34,510008 (07-10) → SELL 34,510008 (07-13, trade **268**) → BUY 41,563993 (07-14, trade **314**) → SELL STOP 41 (07-16). Il guard scatta perché la somma dei fill attribuiti a 314 (75,51) eccede la sua `qty_initial` (41,56)
* Descrizione: la camminata sui fill d'uscita raccoglie, per un trade aperto, anche i fill di vendita di trade precedenti chiusi sullo stesso simbolo. Il guard `exit_fill_qty_exceeds_trade_qty` lo rileva ma il dossier prosegue lo stesso, con `qty_open` clampata a 0.
* Impatto: oggi trascurabile — NOK vale 5,48 $ di market value e il P&L passivo attribuito è ~0. Ma il meccanismo è generale: qualsiasi simbolo con più trade sequenziali può avere `qty_open`, `passive_pnl_usd` ed `exit_active_effect_usd` sbagliati nel dossier. **Il DB live è corretto**: `trades.quantity_remaining` di NOK vale 0,563993, identico al broker.
* Severità: Medium
* Confidenza: High
* Azione consigliata: filtrare i fill per `filled_at ≥ entry_time` del trade, oltre che per `order_id`.
* Test/monitor consigliato: il guard esiste già — va promosso da annotazione a fallimento del blocco, così che il dossier non pubblichi un `passive_pnl_usd` calcolato su una quantità che sa essere sbagliata.

### [DAY-025] [F-037] L'unico acquisto della giornata poggia su un segnale la cui deviazione d'ensemble vale il 59% dello score, e nulla lo guarda

* Tipo: Rischio
* Area: LLM / Orders
* Evidenza:
  * file/log/tabella: `sentiment_signals` 9571; `llm_responses`; `trades` 966
  * timestamp: 2026-09-02 18:00:21Z (segnale) → 18:07:07Z (fill)
  * snippet/query: segnale 9571 NVDA `score +0,4786`, `ensemble_std **0,283**` → `std/|score| = 0,59`; risposte `glm-5.2 +0,80@0,80` e `gpt-oss +0,40@0,55` (spread 0,40, esattamente la soglia della guardia, che scatta su `≥` sul **σ**, non sullo spread, quindi non è scattata)
* Descrizione: 7ª occorrenza. `ensemble_std` non è mai letto come gate d'ingresso: è consultato solo dal postmortem. Il ranking S4 ha selezionato il segnale sulla sola magnitudine.
* Impatto: il trade è stato chiuso in perdita 105 minuti dopo. La perdita non è imputabile alla varianza (i due modelli concordavano sul **segno**, e il titolo ha chiuso +3,21%), quindi non registro un costo qui: registro che la varianza non è entrata nella decisione neanche in questo caso, che è il più alto della giornata.
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna (introdurre `ensemble_std` come gate è taratura, congelata). Ai fini dell'osservazione, pubblicare la serie di `std/|score|` sui soli segnali che generano ordini.
* Test/monitor consigliato: colonna `std_over_score` nel dossier per ogni intento `SUBMITTED`.
* Nota di non-duplicazione: i −2,87 $ sono già addebitati a F-030. Costo `null`.

---

## 11. False positive e aree risultate corrette

Cose che sembravano difetti e non lo sono, o che sono migliorate rispetto alla serie:

1. **Riconciliazione posizioni: apparentemente rotta, in realtà corretta.** Una lettura ingenua di `trades.qty` dà tre divergenze contro il broker (NOK +41,000, WDC +2,646, MRVL +1,000). Sono le stesse tre posizioni riparate da #397 il 2026-09-01. Leggendo `quantity_remaining` — che è il campo introdotto proprio per questo — le quantità coincidono **al nono decimale** su tutte e 44 le posizioni. Il dossier legge correttamente `COALESCE(quantity_remaining, qty)` (`scripts/alpha_miner_dossier.py:416`). Il fix regge.
2. **La guardia di divergenza d'ensemble ha funzionato.** NVDA 9535: glm +0,700 contro gpt-oss −0,450, spread 1,15 → aggregazione rifiutata, fallback su FinBERT. È l'unica riga FinBERT della giornata ed è esattamente il caso per cui esiste.
3. **La guardia di idempotenza è viva e osservabile.** 2 righe `SKIP_IDEMPOTENCY` nel ledger S4 più client_order_id deterministici (`ambc-sell-HOOD-20260902T1507`, `ambc-buy-NVDA-9571`). Un retry Celery non avrebbe potuto duplicare un ordine.
4. **F-002 non ricorre.** Lo `opening_snapshot` del 2026-09-02 attribuisce **48 posizioni su 48** (42 S1, 6 S4), zero `CONTAMINAZIONE`, contro le 10 non attribuite del 2026-08-26. Resta una singola riga contaminata nello scoreboard economico (−34,84 $, congelata), che è un trade chiuso, non una posizione viva.
5. **La disciplina di deploy funziona.** Il riconciliatore ha rinviato il rebuild alle 18:20 con la motivazione «Mercato aperto (o stato ignoto): rimando» e ha agito solo alle 20:20. Il codice in esecuzione durante la seduta è un solo commit (`2b6513ad`), senza discontinuità intra-seduta. Il problema è la ritenzione dei log, non il momento del deploy.
6. **Nessun outage Ollama, e il tasso di fallback è il migliore della serie recente.** 29,7% contro le bande 70-86% di luglio; ensemble presente in 21 cicli su 23; `consecutive_fallback = 0`.
7. **Il ledger delle uscite S4 (trial P0/P1) lavora e discrimina.** Su NVDA D0=2026-09-02, P0 chiude a −3,12 $ netti mentre P1 tiene fino al 2026-09-04; su AVGO e XLE P1 ha emesso `P1_TIME_DUE` virtuali (−6,82 $ e +24,66 $). Il criterio 3 del contratto continua a essere osservabile sul live.
8. **`BRK` / `BRK.B` / `BRK/A`: non è F-032 oggi.** Le tre varianti compaiono in `news_queue_drops`, ma `BRK` e `BRK/A` sono correttamente scartate come `not_tradable` e `BRK.B` come `duplicate_id`. Nessuna mappatura sbagliata è arrivata allo scoring.
9. **`exit_persistence_cycles` e `hold_minimum_minutes` rispettati alla lettera.** HOOD: segnale 14:45 → cicli 14:52 e 15:07 → SELL al secondo. MSFT: 16:00 e 16:15 sotto gate → SELL alle 16:22. NVDA: acquisto 18:07, primo ciclo eleggibile 19:37 (90 min), SELL al secondo ciclo successivo, 19:52 = **105 minuti**.
10. **Zero timestamp futuri, zero `published_at > fetched_at`, zero `parse_fail`, zero duplicati cross-provider, zero `constraints_fired`.**
11. **Sanitizzazione e disciplina asincrona rispettate.** `sanitize_text`/`sanitize_ticker` applicati a corpo, titolo e simbolo prima del prompt; nessuna chiamata LLM dentro `portfolio_scheduler`; coda `inference` separata a concorrenza 1.

---

## 12. Dati mancanti o non accessibili

| Dato | Perché manca | Query/strumento che servirebbe |
|---|---|---|
| **Latenza per chiamata LLM** | `llm_responses` non ha colonna di latenza; i log della seduta sono stati distrutti alle 20:20 (DAY-001) | colonna `latency_ms` su `llm_responses`, popolata dal client Ollama |
| **Causa del ciclo sentiment mancante delle 17:30** | log distrutti (DAY-001); Celery non persiste i fallimenti di task | ritenzione log + `result_backend` con `task_track_started` |
| **Slippage reale** | `slippage_est` duplica `cost_usd` (DAY-013) | mid NBBO alla submission confrontato col `filled_avg_price` |
| **Controfattuale overnight** | 0 righe su 696 hanno `counterfactual_return_overnight`; il worker delle 22:45 lo lascia a `PENDING_OVERNIGHT` | rilettura il giorno successivo (esiste già l'indice dedicato) |
| **Errori/timeout LLM disaggregati** | si deducono solo per assenza (2 risposte glm mancanti su 128) | tabella o contatore di esito per chiamata, oggi assente |
| **Attribuzione settoriale su 9 posizioni** | mappa `SECTOR_ETF_BY_SECTOR` incompleta e assenza non dichiarata (DAY-023) | ETF per `materials`, `media`, `telecom`, `consumer`, `industrials`, `etf_broad` |
| **Drawdown per sleeve** | `per_strategy_metrics = {}` (DAY-014) | ricostruzione da `trades.stop_strategy` |
| **Endpoint REST** | token rifiutato su tutti e 5 (DAY-021) | correzione dell'header o sostituzione con SQL nel protocollo |
| **Calendario earnings** | `giorno_di_earnings = None` su 1438/1438 intenti (già a ledger, F-063) | fonte calendario alternativa o chiave FMP |
| **Log frontend** | non ispezionati: il container frontend è attivo da 28 ore, ma nessuna evidenza della giornata dipende dal frontend | — |

---

## 13. Raccomandazioni immediate

Tutte di correttezza o osservabilità; nessuna tocca soglie, pesi o parametri di strategia (freeze rispettato).

1. **Ritenzione dei log dei container** (DAY-001). Precede tutto il resto: senza, ogni forense futura ha un buco e il DAY-002 di domani sarà di nuovo non diagnosticabile.
2. **Deploy di #182(a)** (DAY-010), già deciso e derogato il 2026-08-25 e ancora non in produzione. Ogni seduta che passa aggiunge uscite S4 al P&L realizzato di S1, e mancano 18 giorni di borsa alla lettura del 28/09.
3. **Popolare `execution_decisions.signal_id` sul ramo d'uscita** (DAY-005). Il segnale è già in mano al chiamante: lo scrive nel testo del `reason`.
4. **Canale per i CRITICAL del decay monitor** (DAY-016) e **namespace di proprietà per il valutatore mobile** (DAY-017). Sono i due difetti che rendono muti gli allarmi già esistenti.
5. **Isolare la suite di test dal DB di produzione** (DAY-019). Oggi ha scritto a mercato aperto.
6. **Contatore di copertura dei cicli** (DAY-002): cicli attesi contro cicli eseguiti, per giorno di borsa.

## 14. Test o monitor da aggiungere

| # | Monitor / test | Difende da |
|---|---|---|
| M1 | Copertura cicli: `ensemble_cycle_health` contro gli slot attesi dal `crontab`, per giorno di borsa | DAY-002 |
| M2 | Presenza dei log della giornata analizzata (`grep -c` sulla data) come precondizione del forense | DAY-001 |
| M3 | Invariante: `execution_decisions.decision IN ('BUY','SELL')` ⇒ `signal_id NOT NULL` | DAY-005 |
| M4 | Invariante: `ensemble_std = 0` solo se le polarity grezze sono identiche | DAY-006 |
| M5 | Invariante: `fallback_used=false` ⇒ almeno una `llm_responses.eligible = true` | DAY-007 |
| M6 | Invariante enum su `risk_flags`, `directness`, `event_type` | DAY-009 |
| M7 | Conteggio giornaliero delle `sentiment_reversal` che risolvono a `stop_strategy ≠ S4` | DAY-010 |
| M8 | Riga giornaliera in `market_daily.jsonl`: posizioni senza stop e nozionale scoperto | DAY-011 |
| M9 | Invariante: `per_strategy_metrics` ha una chiave per ogni sleeve in `strategies_run` | DAY-014 |
| M10 | Invariante: due sleeve non possono avere lo stesso `actual_value` di decay | DAY-015 |
| M11 | Invariante: ogni `log.critical` di un task schedulato ha una riga `mobile_events` | DAY-016 |
| M12 | Test: un incidente aperto da un job specializzato non cambia stato al primo giro del valutatore generico | DAY-017 |
| M13 | Invariante: `count(DISTINCT event_id) = count(DISTINCT (intent_id, policy_id, event_type, observed_at))` | DAY-018 |
| M14 | Invariante: nessuna `source` in `ingestion_stats_daily` fuori dai connettori configurati | DAY-019 |
| M15 | Invariante dossier: ogni `null` in `beta_1_attribution` ha una voce in `missingness` | DAY-023 |
| M16 | `exit_fill_qty_exceeds_trade_qty` promosso da annotazione a fallimento del blocco | DAY-024 |
| M17 | Smoke test giornaliero sui 5 endpoint REST col token del protocollo | DAY-021 |
| M18 | Serie giornaliera delle 4 mediane di latenza di stadio in `market_daily.jsonl` | DAY-004 |

## 15. Ticket tecnici suggeriti

Solo difetti di correttezza o di osservabilità dell'evidenza, come ammesso da `OBSERVATION_CHARTER.md`. La decisione se aprirli è dell'operatore.

| # | Titolo | Difetto | Priorità | Passa il test di esenzione? |
|---|---|---|---|---|
| T1 | Ritenzione persistente dei log dei container attraverso il redeploy | DAY-001 | P0 | Sì — senza, le anomalie operative delle prossime 18 sedute non sono diagnosticabili |
| T2 | Deploy di #182(a): `sentiment_reversal` non chiude posizioni non-S4 | DAY-010 | P0 | Sì — deroga già concessa il 2026-08-25, la serie realizzata di S1 continua a essere contaminata |
| T3 | `execution_decisions.signal_id` popolato sul ramo d'uscita | DAY-005 | P1 | Sì — la catena causale della serie non è ricostruibile per join |
| T4 | Finestre beat derivate dal calendario Alpaca invece che da ore UTC fisse | DAY-003 | P1 | Sì — l'arretrato notturno è escluso per costruzione, incluse tutte le trimestrali |
| T5 | Isolamento della suite di test dal database di produzione | DAY-019 | P1 | Sì — scritture di test in tabelle di evidenza |
| T6 | Canale di allarme per i CRITICAL del decay monitor | DAY-016 | P1 | Osservabilità |
| T7 | Namespace di proprietà nel valutatore mobile generico | DAY-017 | P1 | Osservabilità — rende inefficace la deroga #324 del 2026-08-31 |
| T8 | `ensemble_std` calcolato su tutte le risposte ricevute + `aggregation_mode` esplicito | DAY-006, DAY-007 | P2 | Osservabilità |
| T9 | Validazione enum su `risk_flags`/`directness`/`event_type` | DAY-009 | P2 | Sì — prerequisito del gating `risk_flags` previsto da QX-01 |
| T10 | Idempotenza di `ENTRY_RECONCILIATION` nel ledger S4 | DAY-018 | P2 | Sì — il ledger è la fonte del trial S4 |
| T11 | `missingness` completo nell'attribuzione beta=1 del dossier + ETF per i settori scoperti | DAY-023 | P2 | Sì — strumento con cui si risponderà alla domanda d'uscita sulle sleeve |
| T12 | Fill d'uscita filtrati per `filled_at ≥ entry_time` nel dossier | DAY-024 | P2 | Sì — `passive_pnl_usd` sbagliato su simboli con trade sequenziali |
| T13 | `per_strategy_metrics` ricostruito da `trades.stop_strategy` | DAY-014 | P2 | Osservabilità |
| T14 | Contatore di copertura dei cicli attesi vs eseguiti | DAY-002 | P2 | Osservabilità |
| T15 | Slippage misurato contro il mid NBBO alla submission | DAY-013 | P3 | Osservabilità |
| T16 | Circuito aperto sul fetch SPY permanentemente fallito | DAY-022 | P3 | Igiene dei log |
| T17 | `orders_count` → `target_orders_count` + `submitted_orders_count` | DAY-012 | P3 | Nominale |
| T18 | Protocollo forense allineato: token REST corretto o query SQL al suo posto | DAY-021 | P3 | Osservabilità |

## 16. Stato sistema

**Ollama.** **Up per l'intera seduta. Zero ore di downtime.** 23 cicli sentiment su 24 attesi hanno prodotto risposte; 21 dei 23 hanno prodotto almeno un aggregato ensemble a due modelli. I due cicli senza ensemble (17:00 e 18:30) hanno comunque prodotto una risposta single-model, quindi il servizio rispondeva. `fallback_counters.consecutive_fallback = 0`, ultimo incremento 16:00:54, reset 19:46:10: il circuit breaker non è mai scattato. Mancate risposte: **2 su 254** (0,8%), entrambe di `glm-5.2:cloud` (18:30 GS, 19:00 AVGO).

**FinBERT fallback rate.**
* Righe scorate con `fallback_used = true`: **38 su 128 = 29,7%**.
* Di queste, **FinBERT vero e proprio: 1 su 128 = 0,8%** (NVDA 9535, per divergenza d'ensemble 1,15 — la guardia che ha funzionato). Le altre 37 sono `single:` model, non FinBERT.
* Fallback per ora: 14h 17,4% · 15h 15,0% · 16h **50,0%** · 17h **50,0%** · 18h 20,0% · 19h 29,6%. I due picchi cadono su ore a basso volume (32 e 6 righe) e non coincidono con nessuna decisione.
* **Sulle decisioni:** l'unico BUY della giornata è su segnale non-fallback (come impone #108). Delle 5 SELL, tutte e 5 poggiano su segnali non-fallback per etichetta — con la qualificazione di DAY-007: il segnale che ha chiuso NVDA è etichettato non-fallback ma è stato aggregato col retry a floor 0, con entrambi i modelli a confidence 0,20. **Percentuale di decisioni su FinBERT: 0%.**

**Worker restart events.** `RestartCount = 0` su tutti e 7 i container: nessun crash, nessun riavvio automatico. C'è stato **un solo evento di ricreazione**, volontario: il redeploy del riconciliatore alle **2026-09-02T20:20:14Z** (`2b6513ad → 7c1fc823`), che ha ricreato `api`, `worker`, `worker-inference` e `beat`, dopo la chiusura del mercato e correttamente rinviato dal ciclo delle 18:20 mentre il mercato era aperto. `postgres` e `redis` sono in piedi da 45 ore, `frontend` da 28.

**Salute dei cicli.**

| Componente | Attesi | Eseguiti | Note |
|---|---:|---:|---|
| portfolio-cycle (`:07/:22/:37/:52`, 14–19) | 24 | **24** | zero gap oltre 16 min |
| sentiment-worker (`*/15`, 14:00–19:45) | 24 | **23** | manca il **17:30** (DAY-002) |
| ingestion (`*/15`, 14:00–19:45) | 24 | 23 | stesso slot mancante |
| reconcile-fills-intraday (`:12/:27/:42/:57`) | 24 | ≥9 osservati via `s4_lifecycle_events` | nessuna divergenza rilevata |
| decay-monitor (21:00) | 1 | 1 | 6 CRITICAL senza canale |
| risk-monitor (22:30) | 1 | 1 | `per_strategy_metrics` vuoto |
| counterfactual (22:45) | 1 | 1 | 604/673 calcolati, overnight 0 |
| held-news-loss-alert (22:50) | 1 | 1 | 2 incidenti aperti e chiusi in 0,35 s |

---

*Report forense generato in sessione autonoma di analisi giornaliera. Modalità sola lettura: nessuna modifica a codice o configurazione, nessun ordine, nessuna chiamata broker in modalità trading, nessun worker avviato, nessun commit. I soli file scritti sono questo report e `docs/evidence/findings.json`.*
