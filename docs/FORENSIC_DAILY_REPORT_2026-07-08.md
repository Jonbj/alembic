# Forensic Daily Report — 2026-07-08

Analista: Trading Systems Forensic Analyst + Senior Backend Engineer + Quant Operations Reviewer (sessione autonoma, read-only)
Generato: 2026-07-09
Timezone operativo: **UTC** (esplicito in `src/workers/celery_app.py`, Celery `beat_schedule` interamente in crontab UTC; nessuna ambiguità di codice).
Market hours di riferimento: 13:30–20:00 UTC. Finestra operativa scheduler (sentiment/GDELT/Benzinga/portfolio-cycle): **14:00–21:00 UTC, Lun–Ven** (crontab `hour="14-21"`).

---

## 1. Executive Summary

Il 8 luglio 2026 la pipeline ha operato in **modalità paper** (S1 `supervised_paper`, S4 `paper`, entrambe `approved=true`). S4 ha generato **4 BUY** (AVGO, AZN alle 15:37 UTC; CVX, XOM alle 18:22 UTC) e **2 SELL di rebalance** (AVGO 17:22, AZN 18:52), tutte con fill confermato lato Alpaca paper. CVX e XOM restano posizioni aperte a fine giornata. PnL realizzato netto: **+30,38 USD** (AVGO +42,09, AZN -11,71). NAV 110.088,68 → 110.122,03 USD (+33,35, coerente col realizzato + piccolo MTM sulle posizioni aperte). Nessun ordine duplicato, nessun roundtrip <30min, nessuna pyramiding, nessun "SELL con sentiment positivo" spurio (i 2 SELL sono rebalance-to-zero per score decaduto, non inversione di segno — verificato). Il meccanismo di loss-feedback ha alzato correttamente `entry_threshold` da 0,45 a 0,50 alle 18:30 UTC per `rolling_net_pnl=-195,09`.

News ingest: 227 righe in `news_log` (gdelt_gkg 143, alpaca_benzinga 84); nessun timestamp futuro, nessun campo mancante. Fallback FinBERT al 71,8% (163/227), in linea col trend cronico 70–86%.

**Due scoperte rilevanti.** (1) Il blackout di `audit_log`/log container già segnalato nel report del 07-07 **prosegue**: l'azione `SIGNAL_STALE_SKIP` (la più frequente, centinaia/giorno fino al 06-07) è rimasta a **zero righe** per l'intero 07-08, e in generale `audit_log` ha scritto solo **6 righe sparse** contro le ~300/giorno normali. In più, i container `worker`/`worker-inference`/`api`/`beat` sono stati **ricreati il 07-09 alle 12:07 UTC** (il giorno dopo il target, poco prima di questa sessione), il che ha **azzerato fisicamente** ogni log Docker per il 07-08 — i comandi `docker compose logs --since 48h` richiesti dalla procedura non restituiscono nulla per la giornata target. (2) Un **bug di ticker-attribution** sistemico: **47/227 (20,7%) delle news del giorno** sono etichettate col ticker `MS` (Morgan Stanley) da GDELT (`extraction_method=org_lookup`), ma **45 su 47 titoli non riguardano Morgan Stanley** (Ovintiv, SpaceX, Alibaba, Eli Lilly, Baidu, ecc.) — pattern simile su `GS` (Goldman Sachs). Il meccanismo non ha prodotto ordini spuri oggi (MS/GS sempre SKIP_THRESHOLD), ma inquina ~1 news su 5 del giorno e rappresenta esattamente il rischio "false_positive_ticker_rate" che CLAUDE.md indica come prioritario.

## 2. Verdict Finale

**OK con warning.**

La logica funzionale osservabile via DB/API (segnali → decisioni → ordini → fill → posizioni → loss-feedback) è internamente coerente e corretta in tutti i controlli eseguibili: nessun ordine spurio, soglie rispettate, idempotenza verificata attivamente (un tentativo di doppio BUY alle 15:52 è stato correttamente bloccato da `SIGNAL_DUPLICATE_SKIP`), paper/live coerente, PnL riconciliato. Il warning deriva da due fattori: (a) l'osservabilità di log/audit resta compromessa (continuazione del blackout già rilevato il 07-07, ora aggravato dalla perdita fisica dei log container), per cui latenza LLM, retry, ed eccezioni Celery **non sono verificabili**; (b) un bug di qualità dati concreto e ben evidenziato (ticker mis-attribution su MS/GS) che non ha causato danno operativo oggi ma è un rischio strutturale non banale.

---

## 3. Timeline del 2026-07-08 (UTC)

| Ora UTC | Componente | Evento | Fonte |
|---|---|---|---|
| ~13:30:44 | Regime detector (pre-market) | Regime `sideways`, multiplier 0,7 (VIX 15,57, yield curve 0,36, SPY mom 20d +1,41) | Redis `regime:current` |
| 14:00–14:15 | Scheduler | Apertura finestra operativa; **primo item accettato in `news_log` solo alle 14:15:32** (vs 14:01–14:03 negli altri giorni recenti) — ritardo ~12-14 min, causa non verificabile (log mancanti) | `news_log` min(fetched_at); vedi [DAY-005] |
| 14:07:01 | Portfolio cycle | Primo ciclo del giorno, 0 ordini | `portfolio_cycles` id 296 (min id del giorno) |
| 15:37:00.610 | S4 combiner | **BUY AVGO** (score sentiment 0,6625, ensemble kimi-k2.6+glm-5.2, peso 5%) e **BUY AZN** (score 0,48, ensemble glm-5.2, peso 5%) | `execution_decisions` id 1743,1744; `portfolio_cycles` id 324 |
| 15:37:06–08 | Alpaca (paper) | Ordini submitted→filled: AVGO ~1,8s, AZN ~1,8s | `/api/orders` |
| 15:37:06.8 | Audit | Prime 2 righe `audit_log` del giorno (`INSERT` su `trades`) — riprese dopo 46,5h di silenzio dal 07-06 17:07 | `audit_log` |
| 15:52:00.696 | S4 combiner | Ricalcolo genera **di nuovo** BUY AVGO+AZN (stesso segnale ancora "fresco") — **bloccato da idempotenza** prima della submission | `portfolio_cycles` id 325 (`final_orders` con 2 CombinedOrder); `audit_log` `SIGNAL_DUPLICATE_SKIP` ×2 alle 15:52:06 |
| 16:17–17:22 | S4 | Score AVGO decade da 0,662 a 0,190 (sotto soglia mantenimento 0,45) in ~5 cicli SKIP_THRESHOLD progressivi | `execution_decisions` id 1778,1796,1814,1833,1852 |
| 17:22:00.660 | S4 combiner | **SELL AVGO** (rebalance→0%, score residuo ancora +0,190, non inversione di segno) | `execution_decisions` id 1868; fill 17:22:08.17, holding 1h45m |
| 18:22:01.404 | S4 combiner | **BUY CVX** (score 0,455, ensemble) e **BUY XOM** (score 0,4375, ensemble) — news "Ceasefire Cracks, Oil Bounces" | `execution_decisions` id 1938,1939; fill 18:22:08–09 |
| 18:22:07.94 | Audit | 2 righe `audit_log` (`INSERT` trades CVX/XOM) | `audit_log` |
| 18:30:00.104 | Loss-feedback | **Trigger**: `rolling_net_pnl=-195,09` (nessuna sequenza di perdite consecutive, `consecutive_losses=0`) → `entry_threshold` 0,45→0,50, `regime_scale` 0,512→0,4096 | Redis `feedback:state` |
| 18:37→19:37 | S4 | Score CVX decade 0,455→0,444→0,275, sempre sotto la nuova soglia 0,50; nessuna nuova entry | `execution_decisions` id 1956,1964,1974,1984 |
| 18:52:00.667 | S4 combiner | **SELL AZN** (rebalance→0%, score residuo +0,480, non inversione di segno) | `execution_decisions` id 1962; fill 18:52:06.37, holding 3h15m |
| 21:47:46.7 | News/Sentiment | Ultimo item `news_log` e ultimo incremento `fallback_counters` (`consecutive_fallback=2`) del giorno | `news_log`, `fallback_counters` |
| 21:45:00–01 | Ingestion stats | Scrittura `ingestion_stats_daily` per gdelt_gkg/alpaca_benzinga | `ingestion_stats_daily.updated_at` |
| 22:00 | Forward-return worker | Schedulato (non verificabile l'esito, log assenti) | `celery_app.py` beat schedule |
| 22:30:00.626 | Risk monitor | Snapshot EOD: NAV 110.122,03 USD, exposure 4,39%, drawdown combinato 5,45%, `alerts=[]` | `risk_reports` id=26 (unica riga del giorno — **normale**, il job gira 1×/giorno alle 22:30, non un gap) |

**Nota su osservabilità**: la timeline sopra è ricostruita **esclusivamente da tabelle operative del DB** (`execution_decisions`, `trades`, `portfolio_cycles`, `sentiment_signals`, `llm_responses`/`llm_budget`, `risk_reports`, Redis `feedback:state`/`regime:current`) e dall'endpoint `/api/orders`. **Non da log applicativi**: `docker compose logs {worker,worker-inference,api,beat} --since 48h` non contiene alcuna riga del 07-08 perché questi 4 container sono stati ricreati il 07-09 12:07:38 UTC (vedi [DAY-002]), e `audit_log` per il 07-08 conta solo 6 righe totali (vedi [DAY-001]).

---

## 4. Tabella News Ingest

### Per fonte (day = 2026-07-08, da `ingestion_stats_daily`)

| Fonte | Fetched | Queued (→Redis) | Duplicates¹ | Discarded no-ticker | In `news_log` (finale) |
|---|---|---|---|---|---|
| alpaca_benzinga | 692 | 442 | 3.746 | 0 | 84 |
| gdelt_gkg | 2.889 | 180 | 32 | 2.717 (94%) | 143 |

¹ Stesso fenomeno documentato nel report 07-07 [DAY-008]: il contatore è per coppia `(url, ticker)` post fan-out multi-ticker, non per articolo grezzo. Non è un'anomalia, ma la metrica resta fuorviante per nome.

Gap tra "queued" (622 totali) e righe finali in `news_log` (227): attribuibile ai filtri `SentimentWorker` (`skipped_stale`/`skipped_neutral`/`skipped_not_tradable`) — conteggi per-run **non verificabili** (log mancanti, vedi §12).

### Per ticker (top 16, da `sentiment_signals`)

| Ticker | N. segnali | Score medio | Score min/max | Fallback FinBERT | Decisione più comune |
|---|---|---|---|---|---|
| **MS** | **47** | +0,019 | -0,24 / **+0,49** | 46/47 (98%) | SKIP_THRESHOLD — **vedi [DAY-003], 45/47 news non pertinenti** |
| MU | 20 | +0,009 | -0,37 / +0,41 | 14/20 | SKIP_THRESHOLD |
| GS | 16 | +0,013 | -0,22 / +0,36 | 14/16 | SKIP_THRESHOLD — stesso pattern di [DAY-003] |
| DIS | 9 | -0,066 | -0,21 / +0,05 | 4/9 | SKIP_THRESHOLD |
| SHEL | 9 | -0,013 | -0,21 / +0,15 | 8/9 | SKIP_THRESHOLD |
| NVDA | 7 | +0,053 | -0,19 / +0,30 | 3/7 | SKIP_THRESHOLD |
| BABA | 7 | +0,069 | 0,00 / +0,41 | 7/7 | SKIP_THRESHOLD |
| AAPL | 7 | +0,112 | -0,40 / +0,67 | 4/7 | SKIP_THRESHOLD |
| MSFT | 6 | +0,095 | 0,00 / +0,27 | 3/6 | SKIP_THRESHOLD |
| DB | 6 | -0,115 | -0,35 / +0,02 | 5/6 | SKIP_THRESHOLD |
| **AVGO** | — | +0,662 (news trigger) | — | 0/1 (ensemble) | **BUY → SELL (rebalance)** |
| **AZN** | — | +0,480 (news trigger) | — | 0/1 (ensemble) | **BUY → SELL (rebalance)** |
| **CVX** | — | +0,455 (news trigger) | — | 0/1 (ensemble) | **BUY (aperto)** |
| **XOM** | — | +0,438 (news trigger) | — | 0/1 (ensemble) | **BUY (aperto)** |

**227 segnali totali (`sentiment_signals`), 316 decisioni valutate (`execution_decisions`), di cui 310 SKIP_THRESHOLD (98,1%), 4 BUY, 2 SELL.**

### Top news per impatto sul segnale (|score| più alto, 07-08)

| Ticker | Score | Modello | Titolo | Fonte |
|---|---|---|---|---|
| AAPL | +0,666 | finbert (fallback) | "Samsung Now Makes More Money Than Nvidia..." | alpaca_benzinga |
| AVGO | +0,663 | ensemble kimi-k2.6+glm-5.2 | "Apple Unveils $30 Billion Broadcom Deal" | alpaca_benzinga → **BUY** |
| **MS** | **+0,498** | finbert (fallback) | **"Ovintiv (NYSE:OVV) Stock Price Expected to Rise..."** — nessuna relazione con Morgan Stanley | gdelt_gkg → vedi [DAY-003] |
| META | +0,498 | finbert (fallback) | "Qualcomm's Edge AI Push Could Fuel..." | alpaca_benzinga |
| AZN | +0,480 | ensemble glm-5.2 | "Sino Biopharma Accelerates Global Growth With GSK, AstraZeneca Partnerships" | alpaca_benzinga → **BUY** |
| CVX | +0,455 | ensemble | "Ceasefire Cracks, Oil Bounces: Why Exxon, Chevron Stocks Are Hot Again" | alpaca_benzinga → **BUY** |
| XOM | +0,438 | ensemble | (stesso articolo CVX) | alpaca_benzinga → **BUY** |

### Qualità/problemi rilevati

- **Timestamp futuri**: nessuno (`published_at > fetched_at` → 0 righe).
- **`published_at` mancante**: 0 righe.
- **Duplicati cross-provider stesso giorno** (stesso `content_hash` tra fonti diverse): nessuno.
- **`discarded_reason`**: sempre vuoto nei 227 record — coerente con lo scarto pre-insert (stesso comportamento osservato il 07-07).
- **Contenuto GDELT**: **143/143 (100%)** delle righe `gdelt_gkg` hanno `body_snippet` identico al titolo (nessun body reale disponibile) — il modello LLM/FinBERT ragiona quindi solo sull'headline per queste news, non su un articolo completo. Contribuisce al rischio di attribuzione errata (vedi [DAY-003]) e limita la profondità del DK-CoT reasoning richiesto da CLAUDE.md per queste fonti.
- **Ticker mis-attribution sistemica MS/GS**: vedi [DAY-003] — finding principale della giornata.
- **Ingest ritardato**: primo `news_log` accettato alle 14:15:32 invece dei consueti 14:01–14:03 — vedi [DAY-005].

**Confidenza analisi ingest: Alta** per volumi/duplicati/timestamp (dati DB completi); **Media** per il gap queued→news_log (log per-run mancanti).

---

## 5. Tabella Performance Modelli LLM

| Modello | Risposte totali | Eligible (conf≥0.4) | Non-eligible | Polarity media (eligible) | Confidence media (eligible) | Range polarity |
|---|---|---|---|---|---|---|
| glm-5.2:cloud | 64 | 58 | 6 | +0,203 | 0,576 | -0,70 / +0,85 |
| kimi-k2.6:cloud | 64 | 38 | 26 | +0,068 | 0,591 | -0,70 / +0,70 |

- **Chiamate totali ensemble**: 128 (64 signal-attempt × 2 modelli).
- **Esito aggregazione**: 64/227 segnali (28,2%) hanno usato l'ensemble con successo; **163/227 (71,8%)** in fallback FinBERT.
- **Trend fallback ultimi 6 giorni operativi**: 70,3% (07-01) → 79,5% (07-02) → 86,4% (07-03) → 76,1% (07-06) → 78,9% (07-07) → **71,8% (07-08)**. Migliore giorno della settimana, ma resta dentro la banda cronica 70–86% — non un'anomalia specifica del 07-08 (continuazione di [DAY-002] del report 07-07).
- **Budget LLM**: 0,1107 USD spesi, `budget_exhausted=false` — nessun segnale perso per esaurimento budget.
- **Nessun timeout puro rilevato**: motivo di fallback sempre "ensemble divergence" nei campioni ispezionati (coerente col 07-07); non verificabile in modo esaustivo senza log per-chiamata.
- **Nessuna finestra prolungata di fallback=100%** (Ollama-down pattern): aggregando per ciclo scheduler da 15 min, ogni finestra ha almeno 1 risposta ensemble riuscita tranne poche eccezioni isolate (es. 17:00–17:15 con 2/2 non-fallback, 18:00–18:15 con 2/2 non-fallback) — il servizio ha risposto con continuità per tutto il giorno.
- **Latenza media per chiamata**: **non verificabile** (log worker-inference assenti, vedi [DAY-002]).
- **Validazione output prima dell'ingresso nel signal store**: sì — `eligible=false` filtra 34/128 risposte (min_confidence 0.4); JSON schema strutturato via function calling.
- **Gestione varianza alta**: sì, per design (soglia divergenza declassa a FinBERT).
- **News duplicate pesano più volte?**: per design sì (fan-out multi-ticker su articoli diversi), ma **il vero problema del giorno è a monte**: un articolo su Ovintiv non ha nulla a che fare con MS eppure genera un segnale MS (vedi [DAY-003]) — non è duplicazione, è mis-attribuzione.
- **Confidence bassa riduce il peso?**: sì — formula `score = polarity × confidence` verificata a campione (es. MS: polarity presumibile ~0,59 × confidence ~0,84 ≈ 0,498 osservato, consistente).
- **Chiamate offline/background, mai nel trading loop?**: confermato — stessa architettura Celery `inference` queue verificata nel report 07-07, nessuna modifica rilevata.
- **Rischio hallucination diretto in decisione**: **presente ma indiretto** — non è il modello che "inventa" fatti (il FinBERT sul testo "Ovintiv... Stock Price Expected to Rise" produce una classificazione di sentiment ragionevole *per quel testo*), il problema è che quel testo è stato associato al ticker sbagliato **prima** di arrivare all'LLM. Lo score non ha mai superato la soglia di ingresso su MS/GS oggi, quindi nessun ordine ne è derivato, ma il rischio strutturale resta (vedi [DAY-003]).

**Confidenza analisi LLM: Media** — distribuzioni statistiche solide (dati DB), latenza/retry non verificabili.

---

## 6. Tabella Segnali Finali per Ticker

Vedi §4 (tabella "Per ticker") per il dettaglio completo dei 14 ticker principali. Riepilogo decisioni per i 4 ticker con attività di trading:

| Ticker | Score trigger | Decisione | Holding | Esito fine giornata |
|---|---|---|---|---|
| AVGO | +0,6625 | BUY→SELL (rebalance) | 1h45m | Chiuso, +42,09 USD |
| AZN | +0,480 | BUY→SELL (rebalance) | 3h15m | Chiuso, -11,71 USD |
| CVX | +0,455 | BUY | — | Aperto (unrealized -9,56 USD al momento dell'analisi) |
| XOM | +0,4375 | BUY | — | Aperto (unrealized -19,52 USD al momento dell'analisi) |

---

## 7. Tabella Ordini Generati/Eseguiti

| # | Timestamp decisione | Strategia | Ticker | Azione | Qty | Prezzo fill | Stato | Broker | Rationale | Risk check |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 15:37:00.610 | S4 combiner | AVGO | BUY | 8,84705 | 386,35646 | filled (submit 15:37:06.58, fill 15:37:08.37, ~1,8s) | Alpaca paper | Sentiment +0,662, $30B accordo Apple-Broadcom | Sì — id 1743 |
| 2 | 15:37:00.610 | S4 combiner | AZN | BUY | 17,95044 | 190,38 | filled (submit 15:37:06.78, fill 15:37:08.59, ~1,8s) | Alpaca paper | Sentiment +0,480, licenza Sino Biopharma $2,1B | Sì — id 1744 |
| — | 15:52:00.696 | S4 combiner | AVGO+AZN | **BUY (bloccato)** | — | — | **mai inviato** | — | Stesso segnale ancora fresco, ricalcolo duplicato | **SIGNAL_DUPLICATE_SKIP** — idempotenza funzionante |
| 3 | 17:22:00.660 | S4 combiner (rebalance) | AVGO | SELL | 6,19195 | 393,37 | filled (submit 17:22:05.98, fill 17:22:08.17, ~2,2s) | Alpaca paper | Score decaduto a +0,190 (< soglia mantenimento 0,45) | Sì — id 1868 |
| 4 | 18:22:01.404 | S4 combiner | CVX | BUY | 13,73363 | 176,07 | filled (submit 18:22:07.75, fill 18:22:08.20, ~0,4s) | Alpaca paper | Sentiment +0,455, rally petrolio (Hormuz) | Sì — id 1938 |
| 5 | 18:22:01.404 | S4 combiner | XOM | BUY | 17,12036 | 141,24 | filled (submit 18:22:07.87, fill 18:22:09.57, ~1,7s) | Alpaca paper | Sentiment +0,4375, rally petrolio | Sì — id 1939 |
| 6 | 18:52:00.667 | S4 combiner (rebalance) | AZN | SELL | 12,56592 | 189,84 | filled (submit 18:52:05.91, fill 18:52:06.37, ~0,5s) | Alpaca paper | Score decaduto ma ancora +0,480 (< soglia 0,50 post-adjustment) | Sì — id 1962 |

**S1 non ha generato alcuna decisione BUY/SELL** (0/316, tutte le decisioni non-skip attribuite a S4 — stesso pattern osservato il 07-07; possibile indicatore di under-utilizzo cronico di S1, non un bug del giorno).

Nessun reject, nessun cancel, nessun ordine parziale. Tutti gli ordini `status=filled` sia in `trades` sia in `/api/orders`. Reconciliation ordini↔fill↔posizioni: **OK** — `entry_order_id`/`exit_order_id` in `trades` coincidono con `order_id` in `execution_decisions` e con `id` in `/api/orders`; `/api/positions` mostra CVX/XOM coerenti con le 2 entry rimaste aperte.

**Nota**: `portfolio_cycles.orders_count` conta gli ordini **pianificati dal combiner** (`final_orders`), non quelli effettivamente sottomessi — il ciclo 325 (15:52) mostra `orders_count=2` ma **zero** ordini reali raggiungono il broker, perché l'idempotency filter li scarta prima della submission. Chi legge solo `orders_count` per un conteggio di audit rischia di sovrastimare l'attività reale (stessa categoria di ambiguità di data-model del [DAY-004]/[DAY-008] del report 07-07).

---

## 8. Tabella PnL/Rendimento

| Trade | Ticker | Entry | Exit | Qty | Gross PnL | Cost (bps) | Cost (USD) | Net PnL | Motivo uscita |
|---|---|---|---|---|---|---|---|---|---|
| 240 | AVGO | 386,356 | 393,37 | 6,19195 | 43,43 | 5,35 | 1,336 | **+42,09** | portfolio_sell (rebalance) |
| 241 | AZN | 190,38 | 189,84 | 12,56592 | -6,79 | 20,35 | 4,924 | **-11,71** | portfolio_sell (rebalance) |
| 242 | CVX | 176,07 | — (aperto) | 13,73363 | — | 5,35 | 1,293 | — (unrealized -9,56 al momento dell'analisi) | — |
| 243 | XOM | 141,24 | — (aperto) | 17,12036 | — | 5,35 | 1,293 | — (unrealized -19,52 al momento dell'analisi) | — |
| **Totale realizzato 07-08** | | | | | **36,64** | | **6,26** | **+30,38** | |

- **PnL realizzato 07-08**: +30,38 USD (2 chiusure, 1 vincente/1 perdente).
- **PnL non realizzato al 07-08 EOD**: non disponibile a granularità EOD esatta — il valore -9,56/-19,52 riportato sopra è preso da `/api/positions` **al momento dell'analisi (07-09)**, non uno snapshot marcato al prezzo di chiusura del 07-08; da non confondere con MTM di fine giornata target.
- **PnL per strategia**: tutti i 4 trade sono S4 (news-driven tactical); nessuna attività S1/S2 il giorno.
- **NAV bridge**: 110.088,68 (07-07 22:30) → 110.122,03 (07-08 22:30) = **+33,35 USD**, coerente con il realizzato (+30,38) più un piccolo MTM positivo sulle posizioni CVX/XOM aperte nel pomeriggio. **Confidenza Alta** su questa bridge (differenza rispetto al realizzato piccola e spiegabile, a differenza del 07-07 dove il gap era ampio e non riconciliato).
- **Costi/commissioni**: `cost_usd` totale 6,26 USD sui 4 trade; AZN mostra `spread_cost_bps=20,0` (stesso pattern del 07-07 — ADR europeo, liquidità inferiore).
- **Slippage**: colonna `slippage_est` sempre uguale a `cost_usd` per le righe compilate (240,241) — stesso aliasing/ridondanza già notato nel report 07-07, non bloccante.

**Confidenza PnL: Alta** per i realizzati; **Media** per l'unrealized (dipende da timing della query, non da uno snapshot EOD dedicato).

---

## 9. Analisi Correttezza Buy/Sell

| Check | Esito | Note |
|---|---|---|
| BUY generati solo se consentiti | ✅ OK | 4 BUY, tutti con score sentiment sopra soglia al momento della decisione, `ema_pass=true` |
| SELL/exit generati correttamente | ✅ OK | 2 rebalance-sell, rationale tracciato in `execution_decisions.reason` |
| Stop-loss rispettati | ✅ N/A | Nessun trigger stop-loss il 07-08 (`exit_reason` sempre `portfolio_sell`) |
| Signal flip rispettato | ✅ OK | Nessun flip: entrambi i SELL avvengono con score **ancora positivo** (decadimento sotto soglia mantenimento, non inversione — verificato "bug A5" non presente) |
| Max holding days | ✅ N/A | Tutti i trade <1 giorno |
| Rebalance band rispettata | ✅ OK | AVGO (score 0,662→0,190) e AZN (0,480 stabile ma sotto la nuova soglia 0,50) chiusi coerentemente con FIX-F |
| Ordini duplicati | ✅ **Bloccati correttamente** | Tentativo di doppio BUY AVGO/AZN alle 15:52 intercettato da `SIGNAL_DUPLICATE_SKIP` **prima** della submission — idempotenza verificata attivamente in produzione, non solo in codice |
| Ordini contrari ravvicinati stesso ticker | ✅ Nessuno | Nessun roundtrip <30 min |
| Ordini su ticker non consentiti | ✅ OK | AVGO/AZN/CVX/XOM tutti nel watchlist |
| Ordini fuori orario | ✅ OK | Tutti tra 15:37–18:52 UTC, dentro la finestra di mercato |
| Trade su dati stale | ⚠️ Non verificabile | Il path di filtro stale esiste nel codice (`_filter_stale_signals`) ma il suo audit trail (`SIGNAL_STALE_SKIP`) è a zero righe per il 07-08 — vedi [DAY-001]; comportamento funzionale presumibilmente intatto (l'audit write fallisce in un blocco try/except separato che non altera la logica di filtro), ma non confermabile |
| Trade con LLM output non valido | ✅ OK | `eligible=false` correttamente escluso |
| Circuit breaker attivo | ✅ OK, non attivato | `constraints_fired=[]` su tutti i cicli del giorno |
| Strategia disabilitata | ✅ OK | Solo S1/S4 attive (`approved=true`); S2 `disabled`, S7 `research` |
| Paper/live coerente | ✅ OK | Tutti gli ordini via Alpaca **paper** |
| Idempotenza retry Celery | ✅ **Verificata in azione** | Vedi sopra — non solo presente nel codice ma osservata funzionare sul giorno target |
| Loss-feedback / risk throttling | ✅ OK, attivato correttamente | `entry_threshold` 0,45→0,50 alle 18:30 per rolling PnL negativo; CVX successivamente correttamente bloccato (score 0,444<0,50) coerente con la nuova soglia |
| Reconciliation ordini/fill/posizioni | ✅ OK | Vedi §7 |

---

## 10. Anomalie Trovate

### [DAY-001] Blackout `audit_log` prosegue dal 07-06/07-07, ora isolato all'azione `SIGNAL_STALE_SKIP`

* Tipo: Anomalia
* Area: Ops / Data
* Evidenza:
  * file/log/tabella: `audit_log`; `src/workers/portfolio_scheduler.py:1940` (`write_audit_log(action="SIGNAL_STALE_SKIP", ...)`)
  * timestamp: ultima riga `SIGNAL_STALE_SKIP` = 2026-07-06 17:07:04.577756 UTC; **zero righe di questo tipo** fino ad almeno il momento dell'analisi (2026-07-09)
  * snippet/query: `SELECT created_at::date, action::text, count(*) FROM audit_log WHERE created_at>='2026-06-29' GROUP BY 1,2` → `SIGNAL_STALE_SKIP` presente ogni giorno 06-29→07-06 (284–1118 righe/giorno), **assente** 07-07 e 07-08; totale `audit_log` per il 07-08 = **6 righe** (4 `INSERT` su `trades`, 2 `SIGNAL_DUPLICATE_SKIP`) contro le ~300+/giorno della norma
* Descrizione: la scrittura di audit per i segnali scartati per staleness (il path di gran lunga più frequente, dato che gira su ogni ciclo da 15 min per ogni segnale valutato) è rimasta silenziosamente rotta per il secondo giorno consecutivo. Le altre azioni di audit (`INSERT` su trade aperti/chiusi, `SIGNAL_DUPLICATE_SKIP`) **funzionano** — quindi non è un blackout totale del meccanismo di audit, ma una rottura isolata sul path più chiamato. Il codice (righe 1936–1951) avvolge la write in un try/except con solo `log.warning` — un fallimento qui non altera la logica di business (il filtro stale continua a funzionare), ma azzera l'audit trail corrispondente.
* Impatto: impossibile verificare quanti segnali siano stati scartati per staleness il 07-08, né la loro distribuzione oraria — una parte della Fase 7 ("niente trade se dati stale") resta non verificabile. Il problema persiste da >60 ore al momento dell'analisi.
* Severità: **High** (non Critical come nel report 07-07, perché qui è isolato a un solo tipo di evento e non copre l'intero audit trail; ma la persistenza per 3 giorni consecutivi senza remediation è aggravante)
* Confidenza: **High**
* Azione consigliata: instrumentare `write_audit_log` con un contatore di successi/fallimenti esposto (es. Prometheus counter o riga in una tabella di health) invece di un semplice `log.warning` che — come dimostrato — può restare invisibile per giorni se i log container stessi non sono accessibili (vedi [DAY-002]).
* Test/monitor consigliato: alert su "conteggio giornaliero `SIGNAL_STALE_SKIP` = 0 durante un giorno di mercato attivo" (il pattern storico mostra sempre centinaia di righe/giorno, quindi uno zero è un segnale affidabile di rottura).

### [DAY-002] Perdita fisica dei log Docker per il 07-08 (container recreate il 07-09 12:07 UTC)

* Tipo: Anomalia / Ambiguità
* Area: Ops
* Evidenza:
  * file/log/tabella: `docker inspect alembic-{worker,worker-inference,api,beat}-1`
  * timestamp: `StartedAt=2026-07-09T12:07:38–39Z`, `RestartCount=0` per tutti e 4; `alembic-postgres-1`/`alembic-redis-1`/`alembic-frontend-1` mostrano invece `StartedAt=2026-07-07T14:38:53Z` (restart già noto dal report 07-07, non toccato di nuovo)
  * snippet/query: `docker compose logs worker --since 48h 2>&1 | grep -c "2026-07-08"` → **0**; prima riga di log disponibile per ciascuno dei 4 container è il banner di avvio Celery del 07-09
* Descrizione: 4 dei 7 container (worker, worker-inference, api, beat — esattamente quelli con la logica applicativa rilevante per questa analisi) sono stati ricreati circa 22 minuti prima dell'inizio di questa sessione, il giorno **dopo** quello target. Il log driver Docker (`json-file`) è legato all'istanza del container, quindi la ricreazione ha cancellato ogni riga di log per il 07-08 in modo irreversibile da questa sessione. Non è determinabile se si sia trattato di un deploy pianificato, un riavvio manuale in preparazione di questa analisi, o altro (nessun accesso a log esterni o host).
* Impatto: i comandi `docker compose logs ... --since 48h` richiesti esplicitamente dalla procedura di analisi **non producono alcun dato utile per il giorno target**. Combinato con [DAY-001], la Fase 4 (latenza LLM, timeout/retry granulari) e parte della Fase 7 restano strutturalmente non verificabili con gli strumenti disponibili in sessione.
* Severità: **Medium** (impatto sull'auditabilità, non sulla correttezza operativa osservata — le tabelle DB restano coerenti e complete)
* Confidenza: **High** sull'evento, **Low** sulla causa
* Azione consigliata: introdurre log shipping esterno persistente (es. Loki/CloudWatch/file su volume non legato al ciclo di vita del container) così che un restart/recreate non cancelli la storia; se il restart del 07-09 è stato un'azione manuale legata a questa sessione, documentarlo esplicitamente per non confonderlo con un incidente.
* Test/monitor consigliato: alert su "container critico ricreato" che verifichi automaticamente se log storici sono stati esportati prima della ricreazione.

### [DAY-003] Bug di ticker-attribution sistemico: MS/GS ricevono sentiment da news non pertinenti

* Tipo: Bug
* Area: News / Signal
* Evidenza:
  * file/log/tabella: `news_log` (ticker='MS', 47 righe), `src/connectors/ticker_extractor.py` (match `lower(company_name) = ANY(...)` su `ticker_lookup`), `ticker_lookup` id=38 (`company_name='Morgan Stanley'`, `ticker='MS'`, `aliases={}`)
  * timestamp: intera giornata 07-08 (14:15–21:47 UTC)
  * snippet/query: `SELECT id,title FROM news_log WHERE fetched_at::date='2026-07-08' AND ticker='MS'` → 47 righe; ispezione manuale: **45/47 titoli non riguardano Morgan Stanley** come soggetto primario (es. "Ovintiv (NYSE:OVV) Stock Price Expected to Rise...", "SpaceX hovers at IPO opening price...", "Alibaba Group (NYSE:BABA) Shares Gap Up...", "Eli Lilly Shares Dip Slightly...", "Baidu (NASDAQ:BIDU) Shares Gap Up..."); stesso pattern su `GS` (16 righe, es. "The 5 Types of RWAs Being Tokenized Fastest", "$14,000 dog grooming bills...", "Giga Metals Appoints Steven Latimer to Board")
* Descrizione: il worker di ingest GDELT (`extraction_method=org_lookup`) tagga un articolo con ticker `MS`/`GS` ogni volta che "Morgan Stanley"/"Goldman Sachs" compare **in qualsiasi punto** dei metadati GKG dell'articolo (verosimilmente come banca citata — "analyst at Morgan Stanley", "Goldman Sachs vs Interactive Brokers" — non come soggetto principale), senza alcun filtro di prominenza/rilevanza. Il 100% delle righe `gdelt_gkg` ha `body_snippet` identico al titolo (nessun testo completo persistito), quindi non è verificabile se la menzione sia legittima nel corpo integrale, ma la sproporzione tra titoli e ticker assegnato (45/47 casi palesemente scollegati) rende il pattern quasi certo. Il risultato: **47/227 (20,7%) delle news dell'intera giornata** sono etichettate con un ticker probabilmente errato, generando segnali di sentiment per un'azienda che l'articolo non tratta.
* Impatto: oggi nessun ordine spurio (MS/GS sempre sotto soglia), ma il rischio è concreto — lo score massimo osservato su MS oggi (+0,498) è già vicino alle soglie di ingresso (0,45–0,50) osservate nella giornata; in un giorno con meno concorrenza di segnali legittimi, un cluster di articoli "rumore" con sentiment concorde potrebbe generare un ordine su un ticker completamente scollegato dalla notizia reale — esattamente il "false positive ticker" che CLAUDE.md identifica come "worst-case error". Inquina inoltre le metriche di qualità/IC per MS e GS (media storica vicina a zero, ~+0,02, coerente con rumore).
* Severità: **High**
* Confidenza: **High** (pattern quantificato su 47+16 titoli ispezionati manualmente, root cause coerente col codice del resolver — match esatto senza filtro di prominenza)
* Azione consigliata: nel path `org_lookup`, richiedere che il nome azienda compaia nel **titolo** (o in una posizione ad alta prominenza nei metadati GKG, es. V2ORGANIZATIONS con score/count sopra soglia) prima di assegnare il ticker; oppure limitare `org_lookup` per i "grandi nomi" frequentemente citati come fonte (banche d'investimento, rating agency) a un set con soglia di confidenza più alta, simile al design già esistente per i cashtag ambigui (CLAUDE.md: "Il bare-text path only matches ambiguous tickers ... via an explicit `$cashtag`").
* Test/monitor consigliato: metrica giornaliera "% news per ticker con nome azienda NON presente nel titolo" con soglia di allerta; backtest mirato su MS/GS per quantificare l'impatto storico su IC/ICIR di questi due ticker rispetto al resto del watchlist.

### [DAY-004] Ambiguità semantica del campo `score` in `execution_decisions`/`trades`

* Tipo: Ambiguità
* Area: Data
* Evidenza:
  * file/log/tabella: `execution_decisions` id 1743 (`score=0.05`, `signal_score=0.6625`), `trades` id 240 (`score=0.05`)
* Descrizione: per le decisioni `BUY`, la colonna `score` rappresenta il **peso di allocazione target** (0,05 = 5% del portafoglio), non lo score di sentiment — quello vero è in `signal_score`. Per le decisioni `SKIP_THRESHOLD`, `score` è invece sempre `0` e il valore reale confrontato con la soglia è ancora in `signal_score`. Lo stesso nome di colonna ha quindi due semantiche diverse a seconda del tipo di decisione, ed è **letteralmente zero** informativo per le decisioni di skip.
* Impatto: chi esegue query di anomaly-detection ingenue tipo "score < 0.05 che hanno generato ordini" (come richiesto testualmente nella checklist di Fase 8 di questa stessa procedura) trova un falso positivo su ogni singolo BUY del giorno (tutti mostrano `score=0.05`), quando il vero score di sentiment che ha determinato l'ingresso era 0,44–0,66, ben sopra soglia. Verificato esplicitamente in questa sessione — nessun trade è realmente entrato con score <0,05.
* Severità: **Low**
* Confidenza: **High**
* Azione consigliata: rinominare `execution_decisions.score` in qualcosa come `target_weight` (semantica BUY) e chiarire nello schema/commento che per le decisioni non-BUY il campo è sempre 0 e va ignorato; usare sempre `signal_score` per confronti di soglia/anomaly-detection.
* Test/monitor consigliato: nessuno specifico — chiarezza documentale/schema.

### [DAY-005] Primo ingest del giorno ritardato rispetto al pattern consueto

* Tipo: Ambiguità
* Area: News / Ops
* Evidenza:
  * file/log/tabella: `news_log` min(fetched_at) per giorno: 07-01 14:01:46, 07-02 14:02:21, 07-03 14:02:30, 07-06 14:02:43, **07-08 14:15:32**
* Descrizione: negli altri 4 giorni recenti con pattern normale, la prima news accettata arriva 1-3 minuti dopo l'apertura della finestra scheduler (14:00 UTC, primo ciclo `*/15`). Il 07-08 il primo item accettato arriva 12-14 minuti dopo, coincidendo con il **secondo** ciclo schedulato (14:15) invece del primo (14:00).
* Impatto: basso — non risulta in perdita di ordini o segnali mancanti nel resto della giornata, ma rappresenta ~15 minuti di finestra di mercato senza ingest attivo all'apertura.
* Severità: **Low**
* Confidenza: **Low** (potrebbe essere semplice variazione naturale nel volume di news qualificate al primo ciclo, non un fallimento — non verificabile senza i log del ciclo 14:00, assenti per [DAY-002])
* Azione consigliata: nessuna azione urgente; monitorare se il pattern si ripete nei prossimi giorni.
* Test/monitor consigliato: alert su "nessuna riga `news_log` entro N minuti dall'apertura scheduler" con N calibrato sui giorni normali (es. 5 min).

---

## 11. False Positive o Aree Risultate Corrette

- **"Score < 0,05 che hanno generato ordini"** (checklist esplicita di Fase 8) — **falso positivo**, spiegato in [DAY-004]: il campo `score` per i BUY è il peso di allocazione (5%), non il sentiment; lo score reale (`signal_score`) era 0,44–0,66 su tutti i 4 BUY, sempre sopra soglia.
- **"SELL con sentiment positivo" (bug A5)** — AVGO (score residuo +0,190) e AZN (+0,480) sono stati venduti nonostante score positivo. **Verificato come corretto**: rebalance-to-zero per decadimento sotto la soglia di mantenimento (0,45→0,50 dopo l'adjustment di loss-feedback), non un'inversione di segno. Stesso pattern già validato nel report 07-07 (FIX-F). **Nessun bug.**
- **Ordini duplicati stesso ciclo/minuto** — i tentativi di doppio BUY AVGO/AZN alle 15:52 sono stati **effettivamente bloccati** dal filtro di idempotenza (`SIGNAL_DUPLICATE_SKIP`) prima di raggiungere il broker: comportamento verificato in produzione sul giorno target, non solo presunto dal codice.
- **`portfolio_cycles.orders_count=2` al ciclo 15:52 senza ordini reali sottomessi** — non è una race condition né un bug: il campo conta gli ordini pianificati dal combiner (`final_orders`), il filtro di idempotenza agisce successivamente. Nessuna discrepanza nei dati broker.
- **Unica riga `risk_reports` per il giorno (22:30 UTC)** — verificato nel beat schedule (`risk-monitor` gira 1×/giorno alle 22:30 UTC): comportamento atteso, non un gap di monitoraggio.
- **Loss-feedback threshold escalation (18:30 UTC)** — meccanismo di sicurezza funzionante correttamente: alza la soglia di ingresso in risposta a PnL rolling negativo, verificato applicato in modo prospettico e coerente sui cicli successivi (CVX bloccato a score 0,444<0,50).
- **Roundtrip <30 min, pyramiding, ordini fuori orario, mismatch paper/live** — tutti verificati assenti.
- **Regime detector pre-market** — popolato correttamente (`regime:current` fresco alle 13:30:44 UTC, `multiplier=0,7`), coerente con il fix di capital-deployment applicato in precedenza (nessun fallback ×0,2 osservato).

---

## 12. Dati Mancanti o Non Accessibili

| Dato richiesto | Stato | Query/fonte che servirebbe |
|---|---|---|
| Log applicativi Celery/worker per il 07-08 (latenza LLM, errori, retry, timeout Ollama) | **Non disponibile** — log container fisicamente persi per recreate del 07-09 12:07 (vedi [DAY-002]) | Log shipping esterno persistente, se esiste |
| Conteggio esatto segnali scartati per staleness (`SIGNAL_STALE_SKIP`) del 07-08 | **Non disponibile** (audit path rotto, vedi [DAY-001]) | Fix del path di audit + backfill non possibile retroattivamente |
| Root cause del ritardo di ~15 min nel primo ingest ([DAY-005]) | **Non determinabile** | Log del ciclo 14:00 UTC, assenti |
| Root cause della ricreazione dei 4 container il 07-09 12:07 UTC | **Non determinabile in questa sessione** | Log/storico infra host, accesso non disponibile |
| MTM esatto delle posizioni CVX/XOM al 07-08 22:30 UTC (EOD) | **Non disponibile** — solo prezzo corrente al momento dell'analisi (07-09) | Snapshot di prezzo Alpaca storico marcato a 22:00/22:30 UTC del 07-08 |
| Contenuto completo (non solo titolo) degli articoli GDELT GKG, necessario per confermare/escludere la root cause di [DAY-003] con certezza assoluta | **Non disponibile** — `body_snippet` = titolo per il 100% delle righe gdelt_gkg | Payload GKG grezzo (V2ORGANIZATIONS/V2PERSONS) se persistito altrove, o richiesta diretta all'endpoint GDELT per l'articolo originale |
| `performance_metrics` (composite_ic, icir, drift_level) per 07-08 | Non controllato in questa sessione (fuori scope diretto, coerente con nota "vuoto" già presente nel report 07-07) | `SELECT * FROM performance_metrics WHERE date='2026-07-08'` |

---

## 13. Raccomandazioni Immediate

1. **[DAY-003] è la priorità operativa**: il bug di ticker-attribution MS/GS è concreto, quantificato, e coerente col rischio "worst-case error" che CLAUDE.md pone come massima priorità di design. Non ha causato danno oggi solo per coincidenza (nessun cluster di score sopra soglia), non per garanzia strutturale.
2. Il blackout parziale di `audit_log` ([DAY-001]) è ora al terzo giorno consecutivo (07-06→07-08) senza remediation: va investigato a livello di codice (non solo infra), dato che altre azioni di audit (`INSERT`, `SIGNAL_DUPLICATE_SKIP`) continuano a funzionare — la rottura è isolata al path `SIGNAL_STALE_SKIP`, il che restringe molto lo spazio di ricerca rispetto all'ipotesi "blackout totale" del report 07-07.
3. Introdurre log shipping esterno **prima** che accada un altro recreate dei container ([DAY-002]) — la finestra di osservabilità del sistema è oggi fragile rispetto a un evento operativo banale (redeploy).
4. Non usare `execution_decisions.score`/`trades.score` per query di anomaly-detection: usare sempre `signal_score` ([DAY-004]).

## 14. Test o Monitor da Aggiungere

- Alert su "0 righe `SIGNAL_STALE_SKIP` in `audit_log` durante un giorno di mercato attivo" (pattern storico affidabile: sempre centinaia/giorno quando il path funziona).
- Alert su "container critico ricreato" con verifica automatica di export log pre-ricreazione.
- Metrica giornaliera "% news per ticker con nome azienda non presente nel titolo" (proxy per [DAY-003]), con soglia di allerta su MS/GS/altri "grandi nomi" frequentemente citati come fonte.
- Alert su "nessuna riga `news_log` entro 5 minuti dall'apertura scheduler (14:00 UTC)".
- SLO esplicito su FinBERT fallback rate (soglia consigliata: alert se >85% su media mobile — già raccomandato nel report 07-07, non ancora implementato risulta dal trend osservato).
- Test di regressione sul resolver `org_lookup` con un dataset di articoli "banca citata come fonte, non come soggetto" per prevenire regressioni su [DAY-003].

## 15. Ticket Tecnici Suggeriti

1. **[High]** Root-cause e fix del bug di ticker-attribution MS/GS in `org_lookup` ([DAY-003]) — richiede filtro di prominenza/posizione sul match GDELT GKG.
2. **[High]** Root-cause del path `SIGNAL_STALE_SKIP` rotto in `write_audit_log`, attivo da 3 giorni consecutivi ([DAY-001]) — isolare la causa specifica (diversa da un blackout generico, dato che altri path di audit funzionano).
3. **[Medium]** Log shipping esterno persistente per i container `worker`/`worker-inference`/`api`/`beat`, indipendente dal ciclo di vita del container ([DAY-002]).
4. **[Low]** Rinominare/documentare `execution_decisions.score` vs `signal_score` per evitare falsi positivi nelle query di audit ([DAY-004]).
5. **[Low]** Investigare il ritardo di ~15 min nel primo ingest del 07-08 se il pattern si ripete ([DAY-005]).
6. **[Low, riportato dal 07-07, ancora aperto]** `/api/health.mode` hardcoded — non ri-verificato in questa sessione ma nessuna evidenza di fix nel diff del codice ispezionato.

## 16. Stato Sistema

- **Ollama up/down**: **up per l'intera giornata** — 64/227 segnali (28,2%) hanno completato l'ensemble con successo, distribuiti su tutte le fasce orarie senza finestre prolungate di fallback=100%; nessuna evidenza di timeout puro nei campioni ispezionati.
- **FinBERT fallback rate**: **71,8%** (163/227) — il valore più basso della settimana osservata (range 70,3–86,4%), ma resta dentro la banda cronica già segnalata come rischio strategico (non operativo) nel report 07-07.
- **Worker restart events**: **1 evento rilevante ma fuori target-day** — i container `worker`/`worker-inference`/`api`/`beat` risultano ricreati il **2026-07-09 12:07:38 UTC** (giorno successivo al target, poco prima di questa sessione), causa non determinabile; nessun restart rilevato **durante** il 07-08 stesso (i timestamp `StartedAt` precedenti, 2026-07-07 14:38:53, coprono l'intero giorno target senza interruzioni intermedie per questi 4 container). `postgres`/`redis`/`frontend` non toccati dal 07-07 in poi.
