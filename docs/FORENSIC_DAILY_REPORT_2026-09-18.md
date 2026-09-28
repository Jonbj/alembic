# Forensic Daily Report — 2026-09-18

Sessione forense autonoma in sola lettura, eseguita il 2026-09-28. Il fuso operativo è **UTC**
(`src/workers/celery_app.py`: `timezone="UTC"`, `enable_utc=True`) e tutti i timestamp del report sono UTC. La seduta
regolare va dalle 13:30 alle 20:00 UTC (EDT). Il conto è **paper**, verificato: `portfolio_monitor_snapshots.broker_environment='paper'`
e `mode='paper'` su tutte le istantanee della giornata.

Il periodo è di **sola osservazione** (`docs/evidence/OBSERVATION_CHARTER.md`, scadenza 2026-09-28), quindi il report non propone
tarature. I ticket riguardano solo difetti di correttezza o di strumentazione.

Contesto della seduta:
* Ensemble **glm-5.2 + gpt-oss**, prima dello swap a GLM-5.3 del 22/09.
* Fix F-076/F-054 (`edfd73e0`) **non ancora deployati**.
* #182(a) (`SKIP_REVERSAL_OWNER`) già attivo.

Questo report integra `docs/ALPHA_MISS_REPORT_2026-09-18.md` senza duplicarlo. Quel report ha già registrato le occorrenze del
18/09 per F-023 (HOOD, 72,99 $), F-031 (AMAT, 37,89 $) e F-008 (AVGO, 5,94 $).

---

## 1. Executive summary

La pipeline ha girato end-to-end con un'interruzione:
* **Flusso**: 242 righe `news_log` (134 articoli: 200 Benzinga, 42 GDELT) → 243 segnali → **24/24 cicli portfolio** → 1 BUY
  (AVGO) e 3 SELL S4 (BA, NVO, AVGO). Tutti gli ordini sono `filled` sul conto paper.
* **Riavvio host**: verso le **17:29:45** l'host si è riavviato in modo non pulito, a seduta aperta. Il journal si
  interrompe senza sequenza di spegnimento; il nuovo boot è delle 17:30:32. Per circa 80 s tutto lo stack è rimasto giù,
  Postgres e Redis compresi. Il WebSocket news è rientrato solo alle 17:35, dopo 55 rifiuti «connection limit exceeded».
  Nessun ciclo perso e nessun ordine mancato, ma **nessun allarme**: l'incidente `system:market_clock` è stato aperto e
  chiuso in 0,4 s. Il riavvio ha anche prodotto un doppio scoring dello stesso articolo SPCX (F-072).
* **LLM**: Ollama è rimasto su per tutta la seduta, con un solo timeout (glm alle 16:28). I segnali a modello singolo sono
  75 su 243 (30,9%). I fallback FinBERT reali sono **0**, un dato misurato (`finbert_fallback_events`); il task ne dichiara 75.
* **NAV**: −31,45 $ (−0,03%) contro SPY +0,13% e QQQ +0,63%. Il realizzato S4 è −17,78 $ (BA −21,22, NVO +6,47, AVGO −3,03).
  Il mark open→close vale S4 ≈ −20,1 $ e S1 −23,07 $.

Il difetto principale è di nuovo **F-089**:
* Sette posizioni S4 nel target congelato di S1 hanno ricevuto segnali freschi sotto gate: PANW −0,198, QQQ −0,219, XLE,
  INTC, MU, MRVL, WDC. Il risultato è solo `SKIP_THRESHOLD`.
* Con la stessa regola, AVGO e NVO, che non stanno nel target S1, sono state vendute alle 19:37.
* Oggi il disarmo ha **reso** 114,99 $ contro la regola, quindi il costo attribuito è negativo. La P&L S4 resta però
  non interpretabile come «regola S4».

C'è poi una **liquidazione BA** su un segnale che non basterebbe per comprare: single gpt-oss +0,04 a confidenza 0,40
(F-059, 13,46 $ attribuiti). Il testo della decisione la chiama «FinBERT fallback» (F-078).

## 2. Verdict

**OK con warning.** Due anomalie pesano sull'evidenza: F-089 (uscita S4 disarmata) e il riavvio host in seduta senza
allarme (F-085).

Il percorso del denaro è corretto. Ogni ordine ha segnale, gate, ranking, P0-05, idempotenza, isteresi d'uscita, fill e
riconciliazione. #182 ha funzionato: GM −0,372, posizione S1, `SKIP_REVERSAL_OWNER`. Il riavvio non ha fatto perdere
cicli né ordini, ma è passato inosservato. La serie S4 del giorno va letta con la dichiarazione F-089 del charter.

---

## 3. Timeline del 2026-09-18 (UTC)

| Ora | Componente | Evento | Esito | Fonte |
|---|---|---|---|---|
| 00:00–13:30 | `worker-news-stream` | WS Benzinga 24/7; accodamento fuori seduta | 518 `duplicate_id`, 135 stale e 36 `not_tradable` scartati all'apertura | `news_queue_drops` (`enqueued_off_session=t`) |
| 01:13–01:14 | telegram poller | 10 read timeout | isolato | log inference |
| 06:17 / 07:17 / 10:18 | Ollama (shadow) | timeout glm / gpt-oss | fuori seduta | log inference |
| 07:00:03 | `detect_regime` | FRED **500** → «Failed to fetch macro data» | task **`succeeded: None`** (F-017) | log inference |
| 08:20 | deploy | Warm shutdown `worker`+`worker-inference`; `WorkerLostError` SIGTERM job 8673 | ripartiti 08:20:16 | log worker/inference |
| 13:30:00 | snapshot | NAV 109.480,57 (+22,07), 45 posizioni; `signal` stale | warning | `portfolio_monitor_snapshots` |
| 13:30:01 | alert | `pipeline:portfolio_cycle_late` **CRITICAL** fino alle 14:08; `signal_stale` fino alle 13:33 | recovered | `mobile_events` |
| 13:31:04 | `detect_regime` | sideways ×0,7 (VIX 14,81) | ok | log inference |
| 13:32:06 | `sentiment` | primo segnale; GOOGL +0,303 (13:32) e PBR +0,606 (13:33) | S1 a libro | `sentiment_signals` |
| 13:34–13:43 | `sentiment` | NFLX −0,536 / −0,519 (downgrade Wells Fargo) | long-only, non azionabile | 11546, 11552 |
| 13:51:13 | `sentiment` | **HOOD +0,338** ISSUER_SPECIFIC → 13:59 +0,073 (CFTC) | mai valutato (F-023, ALPHA_MISS) | 11568 → 11578 |
| **14:07:00** | `portfolio-cycle` | primo ciclo, 37 min dopo l'apertura (F-021); FIX-D preserva 10 stale; BA segnalata per l'uscita, trattenuta dall'isteresi di 2 cicli | nessun ordine | `portfolio_cycles` 1562, log |
| 14:22:00 | S4 → broker | **SELL BA** 7,1955 `fallback_filtered`: ultimo segnale single gpt-oss +0,04/conf 0,40 del 17/09 17:22 | `filled` @196,39, net **−21,22 $** | trade 1015, `464ebf0a` |
| 14:37:04 | Telegram | alert #161 AMAT −27,5% / WDC −21,0% | **400 Bad Request** ×2 | log worker |
| 15:41:58 | `sentiment` | AVGO +0,368 (ensemble, ISSUER_SPECIFIC) | — | 11644 |
| 15:52:00 | S4 → broker | **BUY AVGO** 4,066 @356,05 (ranking 0,442 = 0,368 × 1,2, rank 2; percentile 0,449; decisione @356,015) | `filled` 15:52:10 | trade 1017, `acc48042` |
| 16:07:05 | stop sync | stop AVGO qty 4 su 4,066 (98,4%), un ciclo dopo | canceled all'uscita | `52ed257b` |
| 16:18–16:22 | `sentiment` → S4 | GM −0,372 (S1) → `SKIP_REVERSAL_OWNER` (#182) | posizione S1 tenuta | ED 33628 |
| 16:28:33 | Ollama | glm timeout (90 s), **unico in seduta** → SPCX single gpt-oss **+0,600** | `SKIP_FALLBACK` 16:37 (SPCX −1,36% sul giorno) | 11668 |
| 17:06 | `sentiment` | QQQ −0,219 (ensemble) su posizione S4 | tenuta (F-089) | — |
| 17:29:43 | `sentiment` | SPCX 11698 (+0,240) su `news_log` 11699 | persistito | `sentiment_signals` |
| **~17:29:45–17:30:32** | **host** | **riavvio non pulito**: log container troncati alle 17:29:35–43, journal fermo, nuovo boot 17:30:32. Postgres in recovery (API «database system is starting up», primo avvio fallito) | stack giù ~80 s | `journalctl --list-boots`, log |
| 17:30:53 | stack | beat, `worker`, `worker-inference` «ready» (stessi container, modalità recovery) | — | log |
| 17:31:09 | `/v2/clock` | DNS non ancora pronto → «Market closed — skipping Alpaca/GDELT ingestion» | incidente `system:market_clock` CRITICAL **aperto e chiuso in 0,4 s** | log worker, `mobile_events` |
| 17:30–17:35 | WS news | **55 × «connection limit exceeded»** (la connessione dell'host morto contava ancora) | primo articolo WS dopo il riavvio: 17:35:14 | log news-stream, `news_log` |
| 17:37:00 | `portfolio-cycle` | ciclo regolare | nessun ciclo perso | `portfolio_cycles` 1576 |
| 17:52:52 | `sentiment` | **SPCX 11746 (+0,295) sullo stesso `news_log` 11699**: re-score dopo recovery | duplicato (F-072) | `sentiment_signals` |
| 19:16–19:17 | `sentiment` | AVGO +0,115 (ETF semis, 7 ticker, fan-out); NVO −0,210 (Ozempic generico, issuer-specifico) | — | 11783, 11788 |
| 19:22:04 | S4 | isteresi di uscita: AVGO e NVO segnalate | — | log |
| 19:37:00 | S4 → broker | **SELL AVGO** @355,50 (net −3,03) e **SELL NVO** @43,328 (net +6,47), `below_entry_gate` | `filled` | trade 1017/1016 |
| 19:54 | `sentiment` | PANW −0,198 su posizione S4 (−3,06% sul giorno) | tenuta (F-089) | — |
| 19:55:09 | `sentiment` | ultimo segnale della seduta | — | — |
| 20:00:00 | snapshot | NAV **109.427,05**, variazione **−31,45 $**, 43 posizioni, gross 0,326 | — | `portfolio_monitor_snapshots` |
| 20:20 | deploy | Warm shutdown; `WorkerLostError` SIGTERM job 2070 (inference) | fuori seduta | log |
| 21:00:00 | `decay_monitor` | **10 × DECAY CRITICAL**, stesso IC −0,047 su S1, S2 e S4 | solo log | log worker |
| 21:35:01 | `reconcile-positions` | 42 `fully_held` + 1 `partially_wound_down_coheld`, **anomalies 0** | — | log worker |
| 22:24–22:29 | shadow | 4 fallback FinBERT (timeout) → SoftTimeLimit 780 s → **SIGKILL** (TimeLimit 840 s) | turno prosegue | log inference |
| 22:50:00 | alert | `portfolio_cycle_session_grid` + `held_no_news_loss:SBUX` **aperti e chiusi in 1 s** | — | `mobile_events` |
| 23:05:00 | `duplicate_signals_alert` | 69 `news_log` duplicati, `alerted: 1`, ma Telegram **400** | allerta persa | log worker |

---

## 4. News ingest

### 4.1 Per fonte

| Fonte | Trasporto | Estrazione | Righe | Articoli | Ticker | Prima–ultima | Lag pub→riga mediano / p90 | Fetched (stats) | Duplicati (stats) | Scartati (drops) |
|---|---|---|---|---|---|---|---|---|---|---|
| alpaca_benzinga | ws | source_metadata | 197 | 94 | 59 | 13:32:06–19:55:09 | 0,8 / 54,2 min | 1.477 | **7.082** | `duplicate_id` 1.439 in seduta + 518 fuori seduta; stale 135 (fuori seduta, età mediana 3,6 h); `not_tradable` 171 |
| alpaca_benzinga | rest | source_metadata | 3 | 1 | 3 | 14:03–14:04 | 83,3 min | (incl.) | (incl.) | `duplicate_id` 5.125; stale 258 (età mediana 4,2 h); `not_tradable` 5 |
| gdelt_gkg | — | org_lookup | 42 | 39 | 9 | 14:02:48–19:54:05 | 2,5 / 10,8 min | 1.900 | 83 | `no_ticker` 1.775; `duplicate_content` 83 |

* Nessun timestamp futuro (`published_at > created_at`: 0), nessun `discarded_reason` sulle righe scorate e nessun corpo mancante.
* I **corpi GDELT coincidono col titolo** (42/42).
* **BRK.B riceve 22 segnali da GDELT** (20 `content_hash` distinti): sono copie sindacate della stessa notizia, «Warren
  Buffett steps down as Berkshire Hathaway chairman». La dedup per hash non le riconosce (DAY-031). Nessun ordine.
* Entità HTML (`&amp;`, `&#39;`…) nel corpo: **98/242 righe** (95 WS, 3 REST). Il fix non era deployato (DAY-015).
* Fan-out: 134 articoli producono 242 righe. **38 articoli multi-ticker ne generano 146 (60,3%)**, con un massimo di 18
  ticker (roundup «Bitcoin Tops $80,000, S&P 500 Slips…») (DAY-027).
* Copertura: 62 simboli di watchlist con almeno una riga e **34 a zero**, fra cui due mover (ARM +4,04%, TXN +3,29%) e DELL
  −3,46%, detenuta (DAY-023).
* **Buco di trasporto**: il WS è fermo dalle 17:29:36 alle 17:35:14 per il riavvio dell'host (DAY-004). Il REST non ha
  inserito righe nuove nella finestra 17:25–18:30; il run delle 17:31 è stato saltato per il DNS. Una perdita di articoli
  non è dimostrabile: Alpaca WS non ripete, ma i run REST successivi deduplicano tutto contro righe già presenti.
* Nessun altro buco: la distanza massima fra due segnali in seduta è 18,9 min.

### 4.2 Per ticker (top 16 per segnali)

| Ticker | Segnali | Ensemble | Max | Min | Ultimo |
|---|---|---|---|---|---|
| SPY | 26 | 12 | +0,085 | −0,230 | +0,020 |
| BRK.B | 22 | 19 | +0,013 | −0,298 | −0,116 |
| NVDA | 13 | 8 | +0,068 | −0,080 | +0,019 |
| GOOGL | 11 | 4 | +0,303 | −0,132 | +0,006 |
| MU | 8 | 6 | +0,230 | −0,133 | +0,230 |
| GS | 8 | 6 | +0,098 | 0,000 | +0,098 |
| AMZN | 8 | 5 | +0,051 | −0,237 | −0,014 |
| MS | 8 | 2 | +0,090 | −0,006 | +0,090 |
| AAPL | 7 | 6 | +0,225 | −0,165 | −0,165 |
| MSFT | 6 | 3 | +0,008 | −0,150 | −0,120 |
| HOOD | 6 | 6 | +0,338 | +0,006 | +0,021 |
| META | 6 | 4 | +0,031 | −0,150 | +0,031 |
| INTC | 5 | 3 | +0,240 | 0,000 | 0,000 |
| NFLX | 5 | 5 | +0,011 | −0,538 | −0,538 |
| SPCX | 5 | 3 | +0,600 | −0,240 | +0,044 |
| TSLA | 5 | 3 | +0,120 | −0,180 | −0,180 |

### 4.3 Top news per impatto sul segnale

| Segnale | Ticker | Score | Contenuto | Esito |
|---|---|---|---|---|
| 11644 | AVGO | +0,368 (×1,2 → 0,442) | «What Is Going on With Broadcom Stock on Friday?», outlook del CEO sulla domanda AI (glm: `already_priced_in`) | BUY 15:52 → SELL 19:37, −3,03 $ |
| 11783 | AVGO | +0,115 | «$3.2T Chip Boom: Which Semiconductor ETFs Get The Biggest Slice?» (fan-out, 7 ticker) | SELL AVGO (F-008) |
| 11788 | NVO | −0,210 | generico di Ozempic in Canada (issuer-specifico) | SELL NVO, +6,47 $, ha evitato −2,93 $ |
| 11478 (17/09) | BA | +0,04 single, conf 0,40 | lettura a modello singolo | SELL BA alle 14:22 (DAY-002) |
| 11568 | HOOD | +0,338 | SEC / tokenized stocks | mai valutato (F-023) |
| 11668 | SPCX | +0,600 single | Starlink | `SKIP_FALLBACK` (corretto a posteriori: SPCX −1,36%) |
| 11546/11552/11694 | NFLX | −0,54 | downgrade Wells Fargo | long-only, non azionabile |

**Confidenza dell'analisi ingest: alta.** Letture dirette da `news_log`, `news_queue_drops` e `ingestion_stats_daily`.

---

## 5. Performance modelli LLM

| Modello | Risposte | `eligible`=true | Sotto floor 0,40 | Conf. mediana | Polarity media | Pos/Neg/Zero | Score medio (p×c) | Errori di trasporto in seduta |
|---|---|---|---|---|---|---|---|---|
| glm-5.2:cloud | 242 | 89 | 141 (58,3%) | 0,30 | −0,001 | 104/96/42 | −0,002 | **1 timeout** (16:28) |
| gpt-oss:20b-cloud | 243 | 89 | 91 (37,4%) | 0,40 | 0,000 | 90/91/62 | +0,004 | 0 |

| Tipo segnale | Righe | % | Score medio | Min | Max | Sopra gate \|0,30\| | `ensemble_std`=0 |
|---|---|---|---|---|---|---|---|
| ensemble glm-5.2+gpt-oss | 168 | 69,1% | 0,000 | −0,538 | +0,606 | 13 | 38 (tutti a polarity identica) |
| single gpt-oss (`fallback_used`) | 63 | 25,9% | −0,009 | −0,240 | +0,600 | 1 (SPCX) | 63 |
| single glm-5.2 (`fallback_used`) | 12 | 4,9% | +0,021 | −0,083 | +0,120 | 0 | 12 |
| FinBERT (reale) | **0** | 0% | — | — | — | — | — |

* **Latenza**: nessuna telemetria per singola chiamata (F-086). Dai task risultano 76 cicli sentiment attivi in seduta e 242
  item. La durata mediana del task è 22,5 s, quella **per item 9,6 s**, il massimo 123,7 s; nessun task supera i 300 s.
  Il lag pub→riga WS ha mediana 0,8 min.
* **Errori**: in seduta 1 timeout glm (16:28:33). Fuori seduta, nello shadow: 5 timeout glm e 16 gpt-oss, più 4 fallback
  FinBERT dello shadow alle 22:24–22:27, che non scrive in `finbert_fallback_events` perché non è il percorso live.
  Nessun parse-fail.
* **Disaccordo**: su 242 segnali con due risposte, 23 hanno uno spread di polarity ≥ 0,30 e 19 hanno **segni opposti**.
  Di questi 19, **10 sono diventati segnali a modello singolo con `ensemble_std` = 0**: il dissenziente stava sotto il floor
  (DAY-017, F-054, pre-fix). Sui 38 ensemble con std 0 le polarity dei due modelli sono identiche, quindi F-054 non si
  presenta sugli ensemble.
* **Dominanza di un modello**: 75 segnali (30,9%) sono a modello singolo. Sono esclusi dal ranking BUY (20 righe
  `SKIP_FALLBACK`, 217 intenti) ma restano usabili come controsegnale d'uscita, ed è così che è uscita BA (DAY-002).
* **`eligible`**: 79 dei 168 segnali ensemble hanno **zero** risposte `eligible=true` (DAY-016, F-010).
* **Fallback FinBERT reali: 0.** È un dato misurato: `finbert_fallback_events` ha righe dal 14/09, ma nessuna il 18/09.
  L'esito del task dichiara invece `finbert_fallbacks: 75` (DAY-003).
* **Offline/background**: confermato. I modelli girano solo in `worker-inference` (coda `inference`) e il ciclo portfolio
  legge `sentiment_signals` dal DB. Non c'è nessuna chiamata LLM nel percorso ordini.
* **Validazione**: l'output passa dall'estrazione JSON, dal floor di confidenza e dal filtro single-model per il BUY. I
  `risk_flags` (`already_priced_in` su AVGO/HOOD/LLY/PBR/GM) **non fanno da gate**, per disegno (QX-01).
* **Duplicati e multi-segnale**: la stessa news può generare più segnali in due modi. Il primo è il fan-out, un articolo
  su più ticker. Il secondo è il re-score SPCX dopo il crash, due righe sullo stesso `news_log` (DAY-005). Per S4 non pesano
  più volte, perché il ranker legge un solo segnale per simbolo (F-023).

---

## 6. Segnali finali per ticker (quelli arrivati a gate, ranking o ordine)

| Ticker | Segnale | Ora | Score grezzo | Ranking | Tipo | Destino |
|---|---|---|---|---|---|---|
| GOOGL | 11531 | 13:32 | +0,303 | — | ensemble | mai valutato (sovrascritto prima del ciclo 14:07); detenuto da S1 |
| PBR | 11533/11541 | 13:32/13:33 | +0,452/+0,606 | — | ensemble | `SKIP_PYRAMIDING` ×24 (S1 a libro) |
| NFLX | 11546/11552/11694 | 13:34–17:14 | −0,54 | — | ensemble | `RANK_LONG_ONLY`, poi `SKIP_ENTRY_FRESHNESS` |
| HOOD | 11568 | 13:51 | +0,338 | — | ensemble | **mai valutato** (13:59 +0,073) — F-023 |
| AVGO | 11644 | 15:41 | +0,368 | **0,442** | ensemble | **BUY 15:52** (rank 2), poi `SKIP_IDEMPOTENCY` ×13 |
| F | 11663/11695 | 16:18/17:15 | −0,338/−0,420 | — | ensemble | `SKIP_ENTRY_GATE` (ranking) / `RANK_LONG_ONLY` |
| GM | 11664 | 16:18 | −0,372 | — | ensemble | posizione S1: **`SKIP_REVERSAL_OWNER`** (#182) |
| SPCX | 11668 | 16:28 | +0,600 | — | single gpt-oss | `SKIP_FALLBACK` ×4 |
| MRK | 11673 | 16:45 | +0,314 | — | ensemble | `SKIP_PYRAMIDING` ×8, `RANK_OUTSIDE_TOP_N` ×5 |
| LLY | 11751 | 17:58 | +0,362 | — | ensemble | `SKIP_PYRAMIDING` ×8 (S1 a libro) |
| AVGO | 11783 | 19:16 | +0,115 | — | ensemble (fan-out) | **SELL 19:37** |
| NVO | 11788 | 19:17 | −0,210 | — | ensemble | **SELL 19:37** |
| PANW / QQQ / XLE / INTC / MU / MRVL / WDC | vari | 13:32–19:54 | da −0,219 a +0,248 | — | ensemble | posizioni S4 **tenute**, solo `SKIP_THRESHOLD` (DAY-001) |

Disposizioni S4 (`s4_intent_events`):

| Disposizione | Intenti |
|---|---|
| candidati | 2.050 |
| SKIP_ENTRY_GATE | 885 |
| SKIP_ENTRY_FRESHNESS | 731 |
| SKIP_FALLBACK | 217 |
| **SKIP_PYRAMIDING** | **96** (contro **7** righe in `execution_decisions`) |
| SKIP_STALE | 84 |
| RANK_LONG_ONLY | 15 |
| SKIP_IDEMPOTENCY | 13 |
| RANK_OUTSIDE_TOP_N | 8 |
| SUBMITTED | 1 |

`execution_decisions` del giorno: OBSERVE_LATE_ENTRY 1.787, SKIP_THRESHOLD 885, SHADOW_LATE_ENTRY 263, SKIP_FALLBACK 20,
SKIP_PYRAMIDING 7, SELL 3, BUY 1, SKIP_REVERSAL_OWNER 1.

Target weights: S1 ha il gate di ribilanciamento chiuso («holding 43 position(s)», ultimo ribilanciamento il 2026-09-01).
S4 ha peso 2,0% per ingresso con regime ×0,7. Il combiner è attivo (`merged_weights=44`, `constraints=0` su tutti i cicli).

---

## 7. Ordini generati/eseguiti

| Decisione | Strategia | Ticker | Azione | Qty | Prezzo atteso | Fill | Stato | Broker | Rationale | Segnale | Risk check | Anomalie |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 14:22:00 (32563) | S4 | BA | SELL | 7,1955 | — | 196,39 | filled 14:22:06 | Alpaca paper | `fallback_filtered`: ensemble +0,359 del 17/09 invecchiato (22 h), ultimo segnale single gpt-oss +0,04/0,40 | NULL | isteresi 2 cicli; stop cancellato prima | uscita su segnale non ammesso al BUY (DAY-002); etichetta «FinBERT fallback» (DAY-003); `signal_id` NULL |
| 15:52:00 (33286) | S4 | AVGO | BUY | 4,066 | 356,015 (snapshot intento) | 356,05 | filled 15:52:10 | Alpaca paper | +0,368 × velocità 1,2 = 0,442, peso 2,0%, regime 0,7 | 11644 | gate, rank 2, P0-05, idempotenza | `signal_score` 0,442 persistito moltiplicato con `velocity_multiplier` NULL (DAY-008); `decision_price` NULL |
| 16:07:05 | S4 stop | AVGO | SELL stop | 4 | — | — | canceled | Alpaca paper | stop protettivo | — | — | 98,4%, un ciclo dopo (DAY-014) |
| 19:37:00 (35164) | S4 | AVGO | SELL | 4,066 | — | 355,50 | filled 19:37:05 | Alpaca paper | `below_entry_gate` +0,115 (fan-out), hold 3,75 h | NULL | isteresi 2 cicli | F-008 (ALPHA_MISS); `signal_id` NULL |
| 19:37:00 (35165) | S4 | NVO | SELL | 33,2014 | — | 43,328 | filled 19:37:08 | Alpaca paper | `below_entry_gate` −0,210 (issuer-specifico), hold 26,75 h | NULL | isteresi 2 cicli | `signal_id` NULL |

Nessun ordine S1, perché il gate di ribilanciamento è chiuso. `orders_count` vale 4–7 per ciclo contro 0–2 ordini inviati
(DAY-011). Stop BA cancellato alle 14:22:06 prima della SELL.

---

## 8. PnL / rendimento

Fonti:
* `trades` e ordini broker via `/api/orders`;
* `docs/evidence/dossier/2026-09-18.json` (`snapshot_apertura` open→close, `ingressi.mtm_eod`, `chiusure.drift_post_uscita`,
  prezzi Alpaca SIP);
* `portfolio_monitor_snapshots`;
* barre al minuto Alpaca SIP in sola lettura, per i controfattuali.

`economic_pnl.json` (close→close) è **as_of 2026-09-17** e non include questa seduta.

| Voce | Ticker | Qty | Da → A | $ | Tipo |
|---|---|---|---|---|---|
| Realizzato (aperta 17/09) | BA #1015 | 7,1955 | 199,23 → 196,39 | **−21,22** net (gross −20,44, costi 0,79) | realizzato |
| Realizzato (aperta 17/09) | NVO #1016 | 33,2014 | 43,109 → 43,328 | **+6,47** net (gross 7,26, costi 0,79) | realizzato |
| Realizzato (aperta oggi) | AVGO #1017 | 4,066 | 356,05 → 355,50 | **−3,03** net (gross −2,24, costi 0,80) | realizzato |
| **Realizzato S4** | | | | **−17,78** | |
| Preesistente S4 | MU #1014 | 1,4634 | 984,715 → 1.015,80 | +45,49 | non realizzato (open→close) |
| Preesistente S4 | MRVL #1005 | 6,3743 | 242,06 → 244,25 | +13,96 | idem |
| Preesistente S4 | QQQ #1011 | 2,0745 | 718,08 → 720,70 | +5,44 | idem |
| Preesistente S4 | XLE #922 | 22,0056 | 63,82 → 63,93 | +2,42 | idem |
| Preesistente S4 | CSCO #830 | ~17,1 | 110,35 → 109,51 | −14,39 | idem |
| Preesistente S4 | INTC #1007 | 14,5237 | 109,795 → 108,60 | −17,36 | idem |
| Preesistente S4 | PANW #1001 | 3,8762 | 375,075 → 363,58 | **−44,56** | idem |
| Preesistente S4 | WDC #373 | 0,3347 (broker) | 427,50 → 441,36 | ≈ +4,6 (il dossier mette nozionale d'apertura 0: DAY-013) | idem |
| Preesistente S4 (uscite oggi) | BA / NVO | | open → exit | −3,17 / −5,71 | quota intraday del realizzato |
| **S4 intraday** | | | | **≈ −20,1** (open→close delle 10 preesistenti −17,87, più AVGO −2,24 gross) | |
| S1 (35 posizioni) | | | open→close | **−23,07** (GM −40,12, DELL −23,32, GOOGL −19,23; AMAT +19,61, ASML +18,85) | non realizzato |
| **Book (broker)** | | | 109.458,50 → 109.427,05 | **−31,45 (−0,03%)** (snapshot 20:00); `market_daily` equity 109.433,17 | equity |

Note:
* Benchmark: SPY +0,13%, QQQ +0,63%, SOXX +2,69%. L'esposizione lorda del book è fra 0,326 e 0,353. Il −0,03% va letto
  come beta ridotto più selezione negativa su PANW/GM/DELL, **non** come rendimento della strategia.
* La P&L S4 dipende dalle 10 posizioni preesistenti, **7 delle quali non possono uscire per regola S4** (DAY-001).
* Slippage: `decision_price` è NULL in `execution_decisions` e presente solo nello snapshot dell'intento. Proxy
  decisione→fill del BUY AVGO: **+1,0 bp**. Le SELL non sono misurabili. Commissioni 0 (Alpaca). Il costo modellato è 2,38 $
  in `cost_usd`, e `slippage_est` ne è una copia (F-015).
* `/api/trades` riporta la SELL NVO a **+119,24 $** e la SELL BA a **−39,36 $**, perché usa l'entry di trade precedenti. Il
  ledger dice +7,26 / −20,44 gross. La SELL AVGO ha P&L nullo e il BUY AVGO risulta ancora `open` (DAY-012).

---

## 9. Correttezza buy/sell

| Controllo | Esito | Nota |
|---|---|---|
| BUY solo quando consentito | ✅ | 1 BUY AVGO: ensemble, ranking 0,442 ≥ 0,30, rank 2, P0-05, idempotenza |
| SELL/exit corretti | ⚠️ | AVGO e NVO chiuse secondo la regola dichiarata. BA chiusa su un single-model a 0,04 (DAY-002). **7 posizioni S4 nel target S1 non escono** (DAY-001) |
| Stop-loss | ⚠️ | nessuno scattato. Stop AVGO al 98,4% un ciclo dopo; AMAT (−26/−28%) e WDC (−20/−22%) senza stop (sub_one_share) |
| Signal flip | ⚠️ | PANW −0,198 e QQQ −0,219 su posizioni S4: nessuna uscita (DAY-001). GM −0,372 su posizione S1: `SKIP_REVERSAL_OWNER`, corretto per #182 |
| Max holding days | ⚠️ | CSCO dal 25/08 e XLE dal 31/08, tenute dal combiner (DAY-001) |
| Rebalance band | ✅/⚠️ | l'isteresi di uscita di 2 cicli è attiva (BA, AVGO, NVO); non c'è banda di score (F-013) |
| Ordini duplicati | ✅ | nessuno; 13 `SKIP_IDEMPOTENCY` su AVGO |
| Ordini contrari ravvicinati | ✅ | nessun ri-ingresso dopo le SELL |
| Ticker non consentiti | ✅ | tutti in watchlist |
| Fuori orario | ✅ | ordini fra 14:22 e 19:37 |
| Dati stale | ✅ | 84 intenti `SKIP_STALE`, 731 `SKIP_ENTRY_FRESHNESS`; FIX-D preserva 10 posizioni senza controsegnale |
| LLM output non valido | ✅ | nessun parse-fail; i single-model sono esclusi dal BUY |
| Circuit breaker | ✅ | loss-feedback S4 `triggered: False` (EWMA R −0,16), soglia 0,30 invariata |
| Strategia disabilitata | ✅ | S1+S4 attive, `execution.engine=portfolio` |
| Paper/live | ✅ | paper verificato (snapshot) |
| Idempotenza retry Celery | ⚠️ | nessun doppio ordine; il riavvio host ha però prodotto un **doppio segnale** SPCX (DAY-005) |
| Riconciliazione | ⚠️ | 42 `fully_held` + 1 `partially_wound_down_coheld` con «anomalies: 0»; `trades.qty` WDC 2,98 contro 0,3347 al broker (DAY-013) |

Pattern specifici:

* Roundtrip < 30 min: **nessuno** (AVGO 3,75 h).
* Pyramiding > 3 BUY: **nessuno**.
* SELL con sentiment positivo: **sì, 2**. AVGO a +0,115 (fan-out, F-008) e BA a +0,04 single (DAY-002).
* `fallback_used=True` su tutti i simboli: **no** (al massimo 30,9% dei segnali).
* NO-ORDER: **no** (4 decisioni d'ordine, 4 ordini).
* Score < 0,05 che genera ordine: **SELL BA su +0,04** (uscita, non ingresso).
* Ordini identici nello stesso minuto: **no**. AVGO e NVO sono entrambe alle 19:37, ma su simboli diversi.

`exit_mechanism`: le tre righe del 18/09 (`fallback_filtered`, `below_entry_gate` ×2) hanno il formato post-#184, con la
disposizione nel testo del motivo. Sono quindi **osservate, non stime per età**. `trades.exit_reason` riporta
`portfolio_sell`: è un vocabolario diverso, non un conflitto.

---

## 10. Anomalie trovate

### [DAY-001] Sette posizioni S4 nel target congelato di S1 non escono, mentre AVGO e NVO, fuori dal target, escono con la stessa regola

* Tipo: Bug
* Area: Signal / Orders / Risk
* Evidenza:
  * file/log/tabella: Redis `strategy:rebalance_state:S1` (`last_rebalance` 2026-09-01T14:07Z); `sentiment_signals`; `execution_decisions`; barre Alpaca al minuto
  * timestamp: tutta la seduta
  * snippet/query:
    ```
    target S1 congelato: INTC .0145 PANW .0211 XLE .0236 CSCO .0236 MRVL .0120 QQQ .0236 WDC .0116 MU .0118
    segnali ensemble freschi sotto gate: INTC +0,144 (13:32), PANW 0,000 (13:35) / -0,198 (19:54), XLE 0,000 (13:48),
      MU +0,150 (13:33), QQQ -0,219 (17:06), MRVL +0,011 (17:35), WDC +0,248 (15:21)
    execution_decisions: INTC/PANW/XLE/MU 24, MRVL 13, QQQ 12, WDC 19 righe SKIP_THRESHOLD; nessuna SELL
    stessa regola, fuori target S1: AVGO +0,115 e NVO -0,210 -> SELL below_entry_gate 19:37
    ```
* Descrizione: è il meccanismo di F-089. Il combiner somma il peso S1 congelato e la quota S4 azzerata non genera la SELL.
  CSCO, senza segnali, è esclusa dal conto perché FIX-D la terrebbe comunque.
* Impatto: controfattuale corto, stessa convenzione del 17/09 e del 22/09: vendita al secondo ciclo dopo il primo segnale
  fresco sotto gate, contro la chiusura.

  | Titolo | Vendita per regola | Tenere contro vendere |
  |---|---|---|
  | INTC | 14:22 @108,23 | +5,37 |
  | PANW | 14:22 @356,80 | +26,28 |
  | XLE | 14:22 @64,03 | −2,20 |
  | MU | 14:22 @992,455 | +34,16 |
  | QQQ | 17:22 @716,41 | +8,90 |
  | MRVL | 17:52 @237,77 | +41,29 |
  | WDC | 15:37 @437,84, qty broker 0,3347 | +1,18 |

  Tenere ha reso **+114,99 $** rispetto alla regola, quindi il costo attribuito è **−114,99 $**. Oggi il difetto ha
  giovato, ma la P&L S4 del giorno non misura la regola S4.
* Severità: High · Confidenza: High sul meccanismo, Medium sul costo (isteresi approssimata)
* Azione consigliata: il ticket F-089 è già aperto. La dichiarazione nel charter deve coprire anche il 18/09.
* Test/monitor consigliato: allerta giornaliera «posizione S4 con segnale fresco sotto gate e peso S1 congelato > 0».
* → ledger **F-089**

### [DAY-002] BA liquidata su una lettura single-model +0,04 a confidenza 0,40, che non basterebbe per comprare

* Tipo: Rischio · Area: Orders / Signal
* Evidenza: `execution_decisions` 32404 (14:07, SKIP_FALLBACK su 11478 single gpt-oss +0,040/conf 0,40) e 32563 (14:22,
  SELL `fallback_filtered`); log «Exit hysteresis (2 cycles): held 1 position(s) flagged for exit: ['BA']»; FIX-D ha
  preservato 10 stale ma non BA; `sentiment_signals` 11447 (17/09 16:22, ensemble +0,359) e 11753 (18/09 18:02, ensemble +0,075)
* Descrizione: l'ultimo ensemble su BA era +0,359, sopra gate, ma invecchiato (22 h). Una lettura a modello singolo
  esclusa dal BUY (#108) ha fatto da controsegnale: FIX-D non ha preservato la posizione e BA è stata chiusa.
* Impatto: controfattuale corto. Senza la lettura single, FIX-D teneva BA fino al primo ensemble fresco sotto gate (18:02
  +0,075), con vendita alle 18:22 @198,26 dopo 2 cicli di isteresi. Risultato: 7,1955 × (198,26 − 196,39) = **13,46 $**
  (attribuito). Al close il `drift_post_uscita` del dossier è 13,02 $.
* Severità: Medium · Confidenza: Medium
* Azione consigliata: nessuna taratura. Documentare nella sintesi di fine periodo che le uscite possono essere decise da
  letture non ammesse all'ingresso.
* → ledger **F-059**

### [DAY-003] 75 «finbert_fallbacks» dichiarati, 0 reali; l'uscita BA chiama «FinBERT fallback» un segnale ensemble

* Tipo: Bug (osservabilità) · Area: LLM / Data
* Evidenza: la somma degli esiti `run_sentiment_worker` in seduta dà `finbert_fallbacks: 75`; `finbert_fallback_events` del
  18/09 ha **0 righe**; `sentiment_signals` ha 63 single gpt-oss e 12 single glm. Il testo di ED 32563: «S4 signal excluded
  from the ranking as FinBERT fallback, #108 (… generated 2026-09-17 16:22 UTC, score=+0.359)», e 11447 è un **ensemble**.
* Impatto: il tasso di fallback letto dai log è 31% invece di 0%. Costo null.
* Severità: Low · Confidenza: High
* → ledger **F-078**

### [DAY-004] Riavvio non pulito dell'host in seduta (~17:29:45): stack giù ~80 s, WebSocket news giù 5,5 min, nessun allarme

* Tipo: Anomalia · Area: Ops
* Evidenza:
  * `journalctl --list-boots`: boot −2 termina senza sequenza di spegnimento (ultime righe: livepatch, sysstat); boot −1
    inizia il 2026-09-18 19:30:32 CEST = **17:30:32 UTC**
  * log container interrotti fra 17:29:01 (`worker`), 17:29:35 (beat) e 17:29:43 (ultima riga DB); «ready» alle
    17:30:53–55, stessi container in modalità recovery
  * API: primo avvio fallito con «asyncpg CannotConnectNowError: the database system is starting up»
  * 17:31:09 DNS non risolto: «Could not fetch Alpaca market clock … NameResolutionError» → «Market closed — skipping
    Alpaca/GDELT ingestion»
  * WS news: 55 × «connection limit exceeded», primo articolo WS alle 17:35:14
  * `mobile_events`: solo `system:market_clock` CRITICAL, aperto 17:31:10.427 e risolto 17:31:10.849
* Descrizione: la causa del riavvio non è ricostruibile dal journal, che si interrompe prima dei log dei container. Il
  sistema non ha nessun canale che segnali «stack giù» o «host riavviato»: l'unico incidente è stato chiuso in 0,4 s dal
  valutatore generico.
* Impatto: il ciclo delle 17:37 è regolare (24/24) e non manca nessun ordine. C'è un doppio scoring SPCX (DAY-005). La
  perdita di articoli WS nel buco di 5,5 min non è dimostrabile. **Costo 0,0 $** misurato sui cicli e sugli ordini.
* Severità: Medium · Confidenza: High sull'evento, Low sulla causa
* Azione consigliata: dead-man alert esterno allo stack (heartbeat beat/worker verso un canale indipendente) e allerta al
  boot dell'host in giorno di borsa.
* Test/monitor consigliato: confronto giornaliero fra `journalctl --list-boots` e il calendario di mercato; riavvio in
  seduta → allerta.
* → ledger **F-085**. È lo stesso difetto di monitoraggio: stack giù senza alert. La causa scatenante è diversa (riavvio
  host invece di Redis MISCONF), quindi si aggancia e non si apre un id nuovo.

### [DAY-005] SPCX scorato due volte sullo stesso articolo dopo il crash: `news_log` 11699 → segnali 11698 e 11746

* Tipo: Bug · Area: LLM / Data
* Evidenza: `sentiment_signals` 11698 (17:29:43, +0,240, std 0,071) e 11746 (17:52:52, +0,295, std 0,141), stesso
  `news_log_id` 11699 («Elon Musk Says Starlink Now Beats Cable on Reliability»). Il crash è arrivato subito dopo la
  persistenza, prima della rimozione da `news:processing`. Al 28/09 il gruppo è ancora a DB: il charter (deroga del 24/09)
  lo lascia perché la DELETE è bloccata dal trigger append-only `s4_intent_events`.
* Impatto: SPCX non era a libro e nessuno dei due segnali supera il gate. Costo null.
* Severità: Low · Confidenza: High
* → ledger **F-072**. Causa diversa dal SoftTimeLimit del 08/09, stesso meccanismo di recovery.

### [DAY-006] Incidenti aperti e chiusi in meno di un secondo: `system:market_clock` (17:31) e le allerte serali (22:50)

* Tipo: Bug · Area: Ops
* Evidenza: `mobile_events`:
  * `system:market_clock` CRITICAL, 17:31:10.427 → 17:31:10.849;
  * `pipeline:portfolio_cycle_session_grid` e `coverage:held_no_news_loss:SBUX`, 22:50:00 → 22:50:01.
* Costo null. Severità: Medium · Confidenza: High
* → ledger **F-058**

### [DAY-007] Alert Telegram rifiutati (400), compreso l'allarme duplicati che si dichiara «alerted: 1»

* Tipo: Anomalia · Area: Ops
* Evidenza: log worker:
  * 14:37:04 ×2 (#161 AMAT/WDC): «TelegramNotifier: Failed to send alert: Client error '400 Bad Request'»;
  * 23:05:00: `run_duplicate_signals_alert` → `{'duplicated_news_log': 69, 'alerted': 1}` con lo stesso 400.
* Costo null. Severità: Medium · Confidenza: High
* → ledger **F-005**

### [DAY-008] BUY AVGO con `signal_score` 0,442 persistito moltiplicato, `velocity_multiplier` NULL

* Tipo: Bug (osservabilità) · Area: Signal / Data
* Evidenza: `execution_decisions` 33286 e `trades` 1017: `signal_score` 0,442; segnale 11644 `score` 0,368; intento
  `snapshot.score` 0,3683 e `ranking_score` 0,442.
* Descrizione: la provenienza del punteggio persistito è mista fra una giornata e l'altra, senza marcatura. BA il 17/09
  aveva il grezzo 0,274, AVGO oggi il moltiplicato.
* Costo null. Severità: Low · Confidenza: High
* → ledger **F-073** (PR #624)

### [DAY-009] Le 3 SELL hanno `signal_id` NULL

* Tipo: Bug (osservabilità) · Area: Data
* Evidenza: `execution_decisions` 32563, 35164, 35165. `decision_signal_id_coverage` del dossier: SELL 0/3.
* Costo null. Severità: Low · Confidenza: High
* → ledger **F-011**

### [DAY-010] `decision_price` NULL su tutte e 4 le decisioni d'ordine

* Tipo: Bug (osservabilità) · Area: Data
* Evidenza: `execution_decisions` BUY/SELL con `decision_price` NULL (4/4). L'intento AVGO riporta `late_entry.decision_price`
  356,015. `trades.slippage_est` è uguale a `cost_usd` (0,79 / 0,79 / 0,80).
* Costo null. Severità: Low · Confidenza: High
* → ledger **F-015**

### [DAY-011] `orders_count` 4–7 per ciclo contro 0–2 ordini inviati

* Tipo: Bug (osservabilità) · Area: Ops
* Evidenza: `portfolio_cycles` 1562–1585; ciclo 1584 (19:37) `orders_count` 7, con 2 ordini inviati.
* Costo null. Severità: Low · Confidenza: High
* → ledger **F-014**

### [DAY-012] `/api/trades` mostra NVO a +119,24 $ e BA a −39,36 $ (ledger +7,26 / −20,44)

* Tipo: Bug · Area: Frontend / Data
* Evidenza: `GET /api/trades`:
  * `24673dd4` NVO: `entry_price` 39,7366, gross 119,2436;
  * `464ebf0a` BA: entry 201,86, gross −39,3594;
  * SELL AVGO `6f903e84` con P&L null e BUY AVGO `acc48042` ancora `open`;
  * `trades` 1016/1015 riportano entry 43,109 / 199,23.
* Costo null. Severità: Medium · Confidenza: High
* → ledger **F-084**

### [DAY-013] `trades.qty` di WDC vale 2,98 azioni contro 0,3347 al broker; il riconciliatore dichiara «anomalies: 0»

* Tipo: Bug · Area: Broker / Data
* Evidenza: `trades` 373 `qty` 2,9811; log #161 «WDC unprotected … (qty 0.3347, status sub_one_share)» ×24; il dossier dà a
  WDC nozionale d'apertura 0; `run_reconcile_positions` 21:35:01: 42 `fully_held` + 1 `partially_wound_down_coheld`,
  «anomalies: 0».
* Costo null. Severità: Low · Confidenza: High
* → ledger **F-048**

### [DAY-014] Stop AVGO creato un ciclo dopo e su 4 azioni su 4,066; AMAT e WDC senza stop

* Tipo: Rischio · Area: Risk
* Evidenza: il BUY delle 15:52:10 riceve lo stop solo alle 16:07:05 («created: 1»), ordine `52ed257b` qty 4 (98,4%). Log
  «#161: AMAT unprotected at −28,3%…−26,5%», «WDC … −21,7%…−20,1%» (48 righe).
* Costo null (nessuno stop scattato). Severità: Medium · Confidenza: High
* → ledger **F-022**

### [DAY-015] Entità HTML nel testo inviato ai modelli: 98/242 righe, fix non ancora deployato

* Tipo: Bug · Area: News / LLM
* Evidenza: `news_log.body_full ~ '&(amp|#39|quot|lt|gt);'`: 98/242 righe (95 WS, 3 REST). Log WS: «What&#39;s Going On With
  Stellantis…», «S&amp;P 500». Un titolo GDELT contiene `&#x2013;`.
* Descrizione: il 18/09 non ci sono righe `finbert_fallback_events` per verificare il testo effettivo inviato. L'occorrenza
  è quindi **attribuita al codice pre-fix** (`edfd73e0` deployato il 22/09).
* Costo null. Severità: Low · Confidenza: Medium
* → ledger **F-076**

### [DAY-016] 79 dei 168 segnali ensemble hanno zero risposte `eligible=true`

* Tipo: Bug (osservabilità) · Area: LLM / Data
* Evidenza: join `sentiment_signals` (ensemble) × `llm_responses`, `bool_or(eligible)=false` su 79 segnali.
* Costo null. Severità: Low · Confidenza: High
* → ledger **F-010**

### [DAY-017] 10 segnali single-model nascono da risposte di segno opposto e sono persistiti con `ensemble_std` = 0

* Tipo: Bug (strumento di misura) · Area: LLM
* Evidenza: 19 segnali con polarity di segno opposto fra glm e gpt-oss; 10 di questi sono `single:*` con `ensemble_std` = 0,000.
  Il dissenziente stava sotto il floor.
* Descrizione: è il difetto di misura corretto da `edfd73e0` (deroga F-054 del 21/09), non ancora in produzione.
* Costo null. Severità: Low · Confidenza: High
* → ledger **F-054**

### [DAY-018] DECAY CRITICAL con lo stesso IC −0,047 su S1, S2 e S4

* Tipo: Bug · Area: Risk / Ops
* Evidenza: log worker 21:00:00:
  * «[S1] IC dropped 235% from 0.035 to -0.047»;
  * «[S2] … 0.042 to -0.047»;
  * «[S4] … 0.028 to -0.047»;
  * drawdown 13,4% identico su S1 e S2 (S2 non attiva).
* Costo null. Severità: Medium · Confidenza: High
* → ledger **F-004**

### [DAY-019] I 10 DECAY CRITICAL restano solo nel log

* Tipo: Bug · Area: Ops
* Evidenza: `mobile_events` del 18/09 senza righe decay; nessun invio Telegram alle 21:00.
* Costo null. Severità: Medium · Confidenza: High
* → ledger **F-062**

### [DAY-020] Bot token Telegram e api_key FRED in chiaro nei log

* Tipo: Rischio · Area: Ops
* Evidenza:
  * 17.246 righe con `api.telegram.org/bot…` in `worker-inference-2026-09-18.log` e 7 in `worker-2026-09-18.log`;
  * URL FRED con `api_key=` ×4 (07:00 e 13:30).
* Costo null. Severità: Medium · Confidenza: High
* → ledger **F-018**

### [DAY-021] Fetch benchmark SPY fallito 84 volte senza alert

* Tipo: Anomalia · Area: Data
* Evidenza: log worker, «SPY benchmark fetch failed» ×84.
* Costo null. Severità: Low · Confidenza: High
* → ledger **F-016**

### [DAY-022] `duplicates` 7.082 contro `fetched` 1.477 per alpaca_benzinga

* Tipo: Anomalia · Area: Data
* Evidenza: `ingestion_stats_daily` 2026-09-18.
* Costo null. Severità: Low · Confidenza: High
* → ledger **F-007**

### [DAY-023] 34 simboli di watchlist a zero righe news, fra cui i mover ARM (+4,04%) e TXN (+3,29%)

* Tipo: Osservazione · Area: News
* Evidenza: dossier `no_news_backstop.population` (34 zero, 3 mover: ARM, TXN, DELL detenuta); `candidati_miss[ARM|TXN].opportunity_v2.net_opportunity_usd` 66,75 e 30,50.
* Impatto: congetturale, size 2.200 $: **97,25 $** non catturati (ARM 66,75 + TXN 30,50, dal dossier, ingresso al primo
  ciclo utile e uscita al close, al netto dei costi). ALPHA_MISS li classifica NO_NEWS senza registrarli nel ledger.
* Severità: Medium · Confidenza: Medium
* → ledger **F-001**

### [DAY-024] Coda notturna WS drenata all'apertura: 135 stale, 36 not_tradable, 518 duplicati fuori seduta

* Tipo: Anomalia · Area: News / Ops
* Evidenza: `news_queue_drops` con `enqueued_off_session=true`.
* Costo null. Severità: Low · Confidenza: High
* → ledger **F-069**

### [DAY-025] Primo ciclo alle 14:07: HOOD +0,338 delle 13:51 e GOOGL +0,303 delle 13:32 non vedono mai un ciclo

* Tipo: Anomalia · Area: Ops / Orders
* Evidenza:
  * `portfolio_cycles` 1562 (14:07:00);
  * `mobile_events` `portfolio_cycle_late` 13:30:01 → 14:08:00;
  * HOOD 11568 (13:51) → 11578 (13:59);
  * GOOGL 11531 (13:32), sovrascritto prima delle 14:07.
* Descrizione: le finestre beat in UTC fisso lasciano scoperti i primi 37 minuti in EDT. Un ciclo alle 13:52 avrebbe
  valutato HOOD prima della sovrascrittura. GOOGL era comunque detenuto da S1 (P0-05).
* Impatto: costo null qui. HOOD è già costato in F-023 da ALPHA_MISS (72,99 $).
* Severità: Medium · Confidenza: Medium
* → ledger **F-021**

### [DAY-026] Rilevazione di regime fallita alle 07:00 (FRED 500) e task registrato come `succeeded`

* Tipo: Bug · Area: Ops
* Evidenza: log inference 07:00:03 «Failed to fetch macro data for regime detection: Server error '500'» → 07:00:04
  «detect_regime succeeded in 4.26s: None». Il giro delle 13:30 riesce (sideways ×0,7).
* Costo null (nessun ciclo prima delle 13:30). Severità: Low · Confidenza: High
* → ledger **F-017**

### [DAY-027] Fan-out: 60,3% delle righe scorate viene da articoli multi-ticker, e l'uscita AVGO nasce da uno di questi

* Tipo: Rischio · Area: News
* Evidenza: `news_log.content_hash`: 134 articoli → 242 righe; 38 multi-ticker → 146 righe; massimo 18. AVGO 11783 (+0,115)
  viene da un pezzo sugli ETF semis a 7 ticker.
* Impatto: costo null qui. L'uscita AVGO è già registrata in F-008 da ALPHA_MISS (5,94 $).
* Severità: Medium · Confidenza: High
* → ledger **F-012**

### [DAY-028] Ingresso AVGO a movimento già consumato per l'83,5%

* Tipo: Anomalia · Area: Signal
* Evidenza: dossier `ingressi[AVGO]`: `quota_movimento_precedente_al_segnale` 0,835, `quota_nel_gap` 0,464, percentile 0,449.
* Impatto: realizzato −3,03 $. Costo null: l'uscita dipende da F-008 e il contributo dell'ingresso tardivo non è separabile.
* Severità: Low · Confidenza: High
* → ledger **F-030**

### [DAY-029] P0-05 sono 96 intenti ma 7 righe in `execution_decisions`

* Tipo: Anomalia · Area: Orders / Data
* Evidenza: `s4_intent_events` SKIP_PYRAMIDING 96 (SHEL 24, PBR 24, NVO 21, MS 8, MRK 8, LLY 8, AMAT 3) contro 7 righe
  `execution_decisions`, di cui 2 senza `signal_id`.
* Impatto: costo null qui. AMAT è già costata in F-031 da ALPHA_MISS (37,89 $).
* Severità: Medium · Confidenza: High
* → ledger **F-031**

### [DAY-030] HOOD +0,338 ISSUER_SPECIFIC sovrascritto dopo 8 minuti da +0,073

* Tipo: Anomalia · Area: Signal
* Evidenza: `sentiment_signals` 11568 → 11578; nessuno dei 24 intenti HOOD porta 11568.
* Impatto: costo null qui (72,99 $ già registrati da ALPHA_MISS).
* Severità: Medium · Confidenza: High
* → ledger **F-023**

### [DAY-031] Copie sindacate della stessa notizia GDELT scorate 22 volte sullo stesso ticker (BRK.B)

* Tipo: Osservazione · Area: News / Data
* Evidenza:
  ```sql
  SELECT n.source, n.extraction_method, count(*), count(DISTINCT n.content_hash)
  FROM sentiment_signals s JOIN news_log n ON n.id = s.news_log_id
  WHERE s.created_at::date = '2026-09-18' AND s.symbol = 'BRK.B' GROUP BY 1,2;
  -- gdelt_gkg | org_lookup | 22 | 20
  ```
  I titoli sono tutti varianti di «Warren Buffett steps down as Berkshire Hathaway chairman». Per GDELT il corpo coincide
  col titolo, quindi l'hash cambia a ogni riformulazione del titolo.
* Descrizione: la dedup `duplicate_content` (83 scarti) coglie solo le copie identiche. Un solo evento produce il 9,1% dei
  segnali della giornata, 22 osservazioni correlate su un ticker in cui il modello vede sempre la stessa informazione.
* Impatto: nessun ordine. L'IC S4 (`scripts/compute_s4_ic.py`) sceglie un segnale per simbolo con `scelta_produzione()`
  e non è gonfiato. Restano esposte le misure per riga: i forward return per segnale e i pesi LOO-ICIR per modello, che
  contano 22 osservazioni dove l'informazione è una. Costo null, confidenza congetturale sull'impatto.
* Severità: Low · Confidenza: High sul fatto, Low sull'impatto
* Azione consigliata: in sola misura, raggruppare le righe GDELT per (ticker, evento) prima di ogni statistica per riga.
  Nessun cambio all'ingest durante il freeze.
* → ledger **F-090 (nuovo)**. Nessun finding esistente copre «molte copie di un evento su un ticker»: F-012 è il caso
  opposto (un articolo su molti ticker), F-007 riguarda un contatore.

---

## 11. False positive o aree risultate corrette

* **Timezone**: UTC esplicito nel codice. Nessun problema di DST oltre a F-021.
* **Paper/live**: paper verificato, nessun ordine live.
* **Ollama**: su per tutta la seduta. Un solo timeout in seduta (glm 16:28), nessun fallback FinBERT reale, nessuna fase
  «tutti fallback».
* **#182 (`SKIP_REVERSAL_OWNER`)**: GM −0,372 su posizione S1, reversal saltato, come da regola decisa.
* **Isteresi di uscita a 2 cicli**: applicata a BA, AVGO e NVO, ogni volta con un ciclo di attesa.
* **SELL NVO**: uscita su notizia propria (−0,210, issuer-specifica), `drift_post_uscita` −2,93 $, quindi ha evitato una perdita.
* **`SKIP_FALLBACK` SPCX +0,600**: il filtro #108 ha evitato un ingresso su un titolo chiuso a −1,36%.
* **`ensemble_std`=0 sugli ensemble** (38): tutti a polarity identica. F-054 si presenta solo sui single (DAY-017).
* **Riavvio host**: nessun ciclo perso (24/24), nessun ordine duplicato o mancato, beat ripartito con i task dovuti.
* **Restart di deploy** delle 08:20 e delle 20:20: fuori seduta; i messaggi non confermati sono stati ripristinati.
* **Idempotenza ordini**: 13 `SKIP_IDEMPOTENCY` su AVGO, nessun doppio invio.
* **Nessun ordine senza segnale, fuori orario, duplicato o su ticker fuori watchlist.**
* **Loss-feedback S4**: non scattato, soglia 0,30 invariata.

## 12. Dati mancanti o non accessibili

* Latenza per chiamata LLM e uptime Ollama: non persistiti (F-086). Stimati dai log dei task.
* Testo effettivo ricevuto dai modelli: verificabile solo sui fallback FinBERT, che il 18/09 sono 0. DAY-015 resta
  attribuito al codice. I 4 fallback FinBERT dello shadow (22:24–22:27) non sono persistiti in `finbert_fallback_events`.
* Causa del riavvio dell'host: il journal si interrompe alle 17:22:49 UTC, 7 minuti prima dell'ultima riga dei container.
  Servirebbero `/var/log/kern.log`, eventuali pstore/IPMI o log del BIOS.
* Timestamp del log `worker-news-stream`: assenti (formato `logging` di default), quindi la durata dei 55 rifiuti WS è
  dedotta da `news_log`.
* `decision_price` delle SELL: assente (DAY-010), quindi lo slippage d'uscita non è misurabile.
* `economic_pnl.json` è as_of 2026-09-17: il P&L close→close del 18/09 non c'è.
* Simbolo della posizione `partially_wound_down_coheld`: non è nel log.
* Log API: senza timestamp per riga.
* Ledger: `findings.json` su main non passava `validate_findings`. F-086 aveva un'occorrenza del 2026-09-09 anteriore al
  suo `primo_avvistamento` 2026-09-16. Il campo è stato portato al 2026-09-09, unica modifica ammessa fuori dall'append,
  e il ledger ora valida.

## 13. Raccomandazioni immediate

1. **Charter (F-089)**: estendere la dichiarazione sulle posizioni S4 nel target S1 al 18/09. Oggi il disarmo ha giovato
   (+114,99 $), il che mostra che il segno del bias non è fisso. È una correzione di strumento, non una taratura.
2. **Registrare nel charter la rottura del 18/09 alle 17:29–17:35** (riavvio host, WS giù 5,5 min) come interruzione della
   serie osservata di ingest.
3. Nessuna taratura: gate, isteresi, stop e freschezza restano congelati fino al 28/09.

## 14. Test o monitor da aggiungere

* Dead-man alert esterno allo stack e allerta «riavvio host in giorno di borsa» (DAY-004).
* Timestamp nel log `worker-news-stream` (formatter) e contatore di rifiuti «connection limit exceeded» (DAY-004).
* Invariante: posizione S4 con segnale fresco sotto gate e peso S1 congelato > 0 → allerta (DAY-001).
* Contatore giornaliero `finbert_fallback_events` accanto a `finbert_fallbacks` del task, con allerta se divergono (DAY-003).
* `run_duplicate_signals_alert` deve riportare `alerted` solo a consegna avvenuta (DAY-007).
* Test di contratto `/api/trades`: una SELL eredita l'entry del proprio trade (DAY-012).

## 15. Ticket tecnici suggeriti (solo correttezza)

* **F-085**: dead-man/heartbeat esterno. Oggi un riavvio dell'intero host in seduta non produce alcun segnale all'operatore.
  È un difetto di correttezza per l'evidenza, perché le rotture della serie non vengono registrate se nessuno le vede.
* **F-089**: già tracciato. Aggiungere al ticket la riga del 18/09 con costo di segno opposto.
* **F-090**: nessun ticket di codice durante il freeze. Documentare nella metodologia che le statistiche per riga su GDELT
  vanno raggruppate per evento.

## 16. Stato sistema

| Voce | Valore |
|---|---|
| Ollama | **up** per tutta la seduta; 0 h di downtime; 1 timeout glm (16:28), 0 gpt-oss in seduta |
| Ollama fuori seduta | 5 timeout glm e 16 gpt-oss (shadow) |
| FinBERT fallback rate | **0%** dei segnali (0/243) e delle decisioni. `finbert_fallback_events`: 0 righe (misurato) |
| Single-model | 75/243 segnali (30,9%); 20 decisioni SKIP_FALLBACK |
| Worker restart | 2 ricreazioni di deploy fuori seduta (08:20, 20:20; 2 `WorkerLostError` SIGTERM). **1 riavvio non pulito dell'host in seduta (~17:29:45 → 17:30:53)**, con recovery di Postgres, Redis e worker. 1 SIGKILL shadow alle 22:29 (TimeLimit 840 s) |
| WebSocket news | giù 17:29:36 → 17:35:14 (55 × «connection limit exceeded») |
| Cicli portfolio | 24/24 (14:07–19:52); primo ciclo 37 min dopo l'apertura |
| Alert | `portfolio_cycle_late` CRITICAL 13:30–14:08; `system:market_clock` CRITICAL per 0,4 s; 3 invii Telegram falliti (400); DECAY CRITICAL solo nel log |
