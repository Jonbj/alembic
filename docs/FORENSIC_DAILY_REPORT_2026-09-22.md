# Forensic Daily Report — 2026-09-22

Sessione forense autonoma, sola lettura. Fuso operativo **UTC** (`src/workers/celery_app.py`,
`timezone="UTC"`, `enable_utc=True`): tutti i timestamp di questo report sono UTC. Sessione RTH
13:30–20:00 UTC (EDT). Conto **paper** verificato, non assunto: `ALPACA_BASE_URL=https://paper-api.alpaca.markets`
e `portfolio_monitor_snapshots.broker_environment='paper'` su tutte le istantanee della giornata.

Periodo di **sola osservazione** (`docs/evidence/OBSERVATION_CHARTER.md`, scadenza 2026-09-28):
nessuna taratura è proposta. I ticket suggeriti riguardano solo difetti di correttezza o di
strumentazione, cioè quelli che se non corretti rendono sbagliata l'evidenza delle settimane successive.

Contesto di deploy della giornata: alle **07:32 UTC** i worker sono stati ricreati con `main` che
contiene la PR #643 (swap GLM-5.2 → **GLM-5.3**, deroga registrata nel charter il 2026-09-22) e il
fix F-076/F-054 (`edfd73e0`, entità HTML nel prompt e `ensemble_std` su tutte le risposte). È la
**prima seduta** con GLM-5.3 nell'ensemble live.

---

## 1. Executive summary

La pipeline ha girato end-to-end: 232 righe scorate (221 Benzinga WS + 11 GDELT) → 232 segnali →
24 cicli portfolio → 3 BUY e 2 SELL S4, tutti `filled` sul conto paper, riconciliati col broker
tranne UNH (scarto di 1 azione già noto). Nessun ordine fuori orario, duplicato, senza segnale o su
dati stale. L'idempotenza dei retry regge (12 `SKIP_IDEMPOTENCY`). Ollama è stato su tutta la sessione:
27 timeout e 3 fallback FinBERT reali (1,3%). Equity +16,28 $ a 110.041 $ con SPY −0,02%. S4 fa circa
+65 $ di mark-to-close (realizzato +16,60 $: ARM +19,14, BABA −2,54).

Il risultato positivo di S4 **non viene dalle regole di S4**. Sette delle undici posizioni S4 aperte
(CSCO, XLE, PANW, MRVL, INTC, QQQ, MU) stanno nei **pesi target di S1 congelati al 2026-09-01**. Il
combiner le tiene quindi in vita anche quando S4 le porta a zero: la loro uscita S4 è di fatto disarmata.
Dal 20/08, sui simboli fuori dal target S1, S4 ha chiuso 63 trade. Su quelli dentro ne ha chiusi 2,
entrambi per `sentiment_reversal`. Oggi il disarmo ha **reso** +72,50 $ (tenute contro vendute alla
regola), ma non è la strategia che si sta misurando. Secondo difetto: lo swap GLM-5.3 ha **azzerato in
silenzio i pesi LOO-ICIR**. `glm-5.2` 0,7 / `gpt-oss` 0,3 diventano 0,5/0,5, cosa verificata su 49/49
segnali a due contributori. Il charter dice invece che i pesi restano «ereditati come stantii». Anche i
due BUY BABA nascono da articoli GDELT che hanno **solo il titolo**, il primo dei quali («Alibaba Jumps 4%») racconta
un rialzo già avvenuto.

## 2. Verdict

**Anomalie significative.**

Il percorso del denaro è corretto: ogni ordine ha segnale, gate, risk check e fill riconciliato. Due difetti però
rendono **non interpretabile** l'evidenza raccolta per il 28/09. (1) La P&L attribuita a S4 include
posizioni la cui uscita S4 non può scattare (F-089, nuovo). (2) Da oggi la serie degli score d'ensemble
viene da pesi diversi da quelli dichiarati, e la discontinuità registrata nel charter li descrive in modo
sbagliato (F-088, nuovo). Nessuno dei due richiede di fermare il sistema. Tutti e due vanno dichiarati
prima della sintesi del giorno 40.

---

## 3. Timeline del 2026-09-22 (UTC)

| Ora | Componente | Evento | Esito | Fonte |
|---|---|---|---|---|
| 00:00–13:29 | `worker-news-stream` | WS Alpaca/Benzinga 24/7; 104 dispatch di `run_sentiment_worker` fuori seduta | tutti `skipped: market_closed` | `worker-inference-2026-09-22.log` |
| 07:00:04 | `detect_regime` | FRED `VIXCLS` → **500** | task `succeeded … None` (F-017); URL con `api_key` in chiaro nel log | log inference |
| 07:28 / 07:32 | deploy | merge PR #643 (GLM-5.3) → **Warm shutdown** e ripartenza di `worker` e `worker-inference` | ripartiti 07:32:08 | log worker/inference |
| 10:28–10:29 | `sentiment_shadow` | SoftTimeLimit 780 s → TimeLimitExceeded(840) → **SIGKILL**, lotto di 12 item perso | turno prosegue | log inference |
| 13:30:01 | `mobile_alert_evaluation` | `pipeline:portfolio_cycle_late` **CRITICAL** + `pipeline:signal_stale` WARNING | aperti | `mobile_events` |
| 13:30:46 | `detect_regime` | secondo giro | ok, regime SIDEWAYS, `regime_mult` 0,7 | log, `trades.regime_mult` |
| 13:31:54 | `sentiment` | primo segnale (GOOGL +0,341, ensemble) | drena la coda notturna: **185** `stale` + 27 `not_tradable` nell'ora 13 | `news_queue_drops` |
| 13:32:01 | alert | `signal_stale` rientrato | ok | `mobile_events` |
| 13:35:23 | FinBERT | fallback #1 (SOXX, Ollama timeout; body_chars 471) | input senza entità HTML | `finbert_fallback_events` id 25 |
| 13:50:50 | `sentiment` | **META +0,318** (ensemble) sopra gate | mai valutato: sovrascritto alle 14:03 da META 0,000, prima del primo ciclo (DAY-007/008) | `sentiment_signals` 12008 |
| **14:07:00** | `portfolio-cycle` | **primo ciclo, 37 min dopo l'apertura** | `portfolio_cycle_late` rientra 14:08 | `portfolio_cycles` 1610 |
| 14:07:04 | S4 gate | SKIP_STALE ×3, SKIP_FALLBACK (INTC +0,640 del 21/09), SKIP_PYRAMIDING GOOGL +0,341 | nessun ordine | `execution_decisions` |
| 14:07:06 | Telegram | alert #161 (AMAT scoperta a −21,3%) | **400 Bad Request** | log worker |
| 14:15 (pub) | GDELT | «Alibaba Jumps 4% as Zhenwu V900 Chip…», corpo = titolo (91 char) | ingerito 14:57:33 | `news_log` 12065 |
| 14:57:33 | `sentiment` | **BABA +0,3825** (glm 0,7/0,75; gpt 0,4/0,6) | sopra gate | `sentiment_signals` 12064 |
| 15:07:00 | S4 → broker | **BUY BABA** 12,3054 @ 116,7025 (nozionale 1.436 $) | `filled` 15:07:07 | trade 1023, ordine `f98150a2` |
| 15:22:04 | stop sync | stop BABA qty 12 su 12,3054 (97,5%) | `new`, poi cancellato alla SELL | ordine `480db144` |
| 15:27:07 | `sentiment` | BABA +0,188 (articolo Benzinga sullo stesso evento) | diventa l'ultimo segnale BABA | 12090 |
| 16:37:04 | S4 gate | SKIP_PYRAMIDING SOXX +0,403 (S1 a libro dal 07-28) | nessun ordine | `execution_decisions` |
| 16:45:51 | `sentiment` | CSCO −0,420 (single gpt-oss) dopo −0,150 alle 16:11 | CSCO (S4) **non viene venduta** (DAY-001) | 12114/12127 |
| 16:52:00 | S4 → broker | **SELL BABA** (tutta), `below_entry_gate` su +0,188 | `filled` @ 116,56, net **−2,54 $**, tenuta 1h45 | trade 1023, ordine `8aacfe22` |
| 16:59:30 (pub) | Benzinga | Arora Report «Commodity ETF… Muse Ignites CPU Fever», macro a **14 ticker** | ARM −0,011 alle 17:05 | `news_log` 12138 |
| 17:22:00 | S4 → broker | **SELL ARM** (tutta), `below_entry_gate` su −0,011 | `filled` @ 330,36, net **+19,14 $** | trade 1021, ordine `6e7a3df0` |
| 17:30 (pub) | GDELT | «Alibaba unveils new AI chip and data center expansion plans», corpo = titolo (59 char) | glm: `already_priced_in`, `low_source_quality` | `news_log` 12152 |
| 17:37:00 | S4 → broker | **BUY BABA** 12,3415 @ 116,36 (segnale 12151 +0,3475), **45 min dopo la SELL** | `filled` 17:37:05 | trade 1024 |
| 17:52:04 | stop sync | stop BABA qty 12 su 12,3415 (97,2%) | `new` | ordine `92b18075` |
| 18:06:42 | `sentiment` | CSCO −0,294 (ensemble) | CSCO resta a libro | 12176 |
| 19:03:31 | `sentiment` | META +0,354 (Muse download) × velocità 1,2 = 0,424 | sopra gate | 12214 |
| 19:07:00 | S4 → broker | **BUY META** 1,9489 @ 738,95 | `filled` 19:07:06 | trade 1025 |
| 19:07:06 | stop sync | stop META **qty 1 su 1,9489 (51,3%)** | `new` | ordine `81142bf6` |
| 19:48:05 | `sentiment` | ultimo segnale della seduta | — | `sentiment_signals` |
| 19:52:00 | `portfolio-cycle` | ultimo ciclo (24 in tutto, tutti con `submitted` 0/1) | ok | `portfolio_cycles` 1633 |
| 20:00:00 | snapshot | NAV 110.041,29 $, variazione giornata **+16,28 $**, 46 posizioni | — | `portfolio_monitor_snapshots` |
| 21:00:00 | `decay_monitor` | 5 righe **DECAY CRITICAL** (S1/S2/S4 con lo stesso IC −0,043) | solo log | log worker |
| 21:35:02 | `reconcile-positions` | 45 `fully_held` + 1 `partially_wound_down_coheld` (UNH), **anomalies: 0** | — | log worker |
| 21:57:07 | `reconcile_fills_intraday` | 0 fill aggiornati; 21 eventi lifecycle S4 | ok | log worker |
| 22:50:00–01 | alert | `portfolio_cycle_session_grid` (open gap 37,0 min) + `held_no_news_loss` AMAT/SBUX | tutti **aperti e chiusi in 1 s** | `mobile_events` |
| 23:05:00 | Telegram | alert serale | **400 Bad Request** | log worker |

---

## 4. News ingest

### 4.1 Per fonte

| Fonte | Trasporto | Estrazione | Righe scorate | Ticker distinti | Prima–ultima riga | Lag mediano pub→riga | Fetched (stats) | Duplicati (stats) | Scartati |
|---|---|---|---|---|---|---|---|---|---|
| alpaca_benzinga | ws | source_metadata | 221 | 50 | 13:31:54–19:48:05 | 8,3 min | 1.549 | **6.296** | 427 stale, 170 not_tradable |
| gdelt_gkg | — | org_lookup | 11 | 8 | 14:57:33–18:02:22 | 5,0 min | 1.714 | 2 | 1.701 no_ticker |

* Nessun timestamp futuro (`published_at > created_at`: 0). Nessun `discarded_reason` sulle righe scorate.
* Tutti i corpi Benzinga sono presenti. **I corpi GDELT coincidono col titolo** (`body_full` = titolo, 59–91 caratteri).
* Fan-out: 146 articoli distinti (`content_hash`) producono 232 righe. **33 articoli multi-ticker ne generano 119 (51,3%)**,
  il peggiore 14 righe (Arora Report, DAY-005/006).
* Stale: 185 alle 13:xx (coda notturna WS, `enqueued_off_session`) e **242 durante la seduta, tutti `transport=rest`**,
  ingeriti in mediana 4,1 h dopo la pubblicazione (backfill REST di articoli già vecchi, non perdite di scoring).
* Entità HTML in `news_log`: 173/232 righe. **Non è il criterio di F-076**: il charter avverte che il path Benzinga
  persiste il grezzo. Il criterio (testo che raggiunge il modello) è verificato su `finbert_fallback_events` (§11).
* Copertura: 51 simboli con almeno un segnale. Proxy di copertura: ~45/96 simboli di watchlist senza segnali (DAY-029).

### 4.2 Per ticker (top 18 per righe)

| Ticker | Righe | Ensemble | Single/FinBERT | Max | Min | Ultimo |
|---|---|---|---|---|---|---|
| SPY | 39 | 20 | 19 | +0,180 | −0,180 | −0,110 |
| META | 25 | 18 | 7 | +0,420 | −0,018 | +0,008 |
| GOOGL | 11 | 6 | 5 | +0,341 | −0,186 | +0,008 |
| NVDA | 10 | 7 | 3 | +0,186 | −0,210 | −0,084 |
| AAPL | 10 | 7 | 3 | +0,123 | −0,015 | +0,123 |
| MU | 9 | 8 | 1 | +0,320 | 0,000 | 0,000 |
| AMZN | 9 | 6 | 3 | +0,156 | −0,180 | +0,040 |
| MSFT | 9 | 5 | 4 | +0,236 | −0,090 | 0,000 |
| TSLA | 6 | 3 | 3 | +0,080 | −0,165 | −0,165 |
| SPCX | 6 | 2 | 4 | +0,200 | −0,210 | −0,210 |
| LLY | 6 | 4 | 2 | +0,398 | −0,064 | −0,064 |
| BABA | 5 | 4 | 1 | +0,383 | −0,040 | +0,348 |
| AMD | 5 | 3 | 2 | +0,385 | −0,180 | −0,014 |
| JPM | 5 | 4 | 1 | +0,173 | −0,200 | +0,010 |
| MS | 5 | 1 | 4 | +0,223 | −0,180 | +0,120 |
| GS | 4 | 3 | 1 | +0,183 | +0,009 | +0,120 |
| PANW | 4 | 3 | 1 | +0,260 | 0,000 | +0,008 |
| ERIC | 3 | 3 | 0 | −0,373 | −0,450 | −0,373 |

### 4.3 Top news per impatto sul segnale

| Segnale | Ticker | Score | News | Esito |
|---|---|---|---|---|
| 12064 | BABA | +0,3825 | GDELT «Alibaba Jumps 4% as Zhenwu V900…» (solo titolo, pub. 14:15) | BUY 15:07 → SELL 16:52, −2,54 $ |
| 12151 | BABA | +0,3475 | GDELT «Alibaba unveils new AI chip…» (solo titolo, pub. 17:30) | BUY 17:37, aperta |
| 12214 | META | +0,354 (×1,2) | Benzinga «Meta's Muse Beat ChatGPT's Early Download Pace» | BUY 19:07, aperta |
| 12137 | ARM | −0,011 | Arora Report macro a 14 ticker | SELL ARM 17:22 |
| 12008 | META | +0,318 | — | mai valutato (sovrascritto) |
| 12001 | ERIC | −0,450 | — | RANK_LONG_ONLY |

**Confidenza dell'analisi ingest: alta** per volumi, fonti e fan-out (letture dirette dal DB). Media sulla copertura
di watchlist (proxy su segnali, non la metrica `no_news_backstop` del dossier, che per il 22/09 non esiste).

---

## 5. Performance modelli LLM

| Modello | Risposte | Eleggibili (flag) | Sotto floor 0,40 | Conf. mediana | Polarity media | Pos/Neg/Zero | Timeout (log) |
|---|---|---|---|---|---|---|---|
| glm-5.3:cloud | 220 | 49 | **167 (75,9%)** | 0,25 | +0,054 | 110/65/45 | 14 |
| gpt-oss:20b-cloud | 226 | 49 | 104 (46,0%) | 0,40 | +0,040 | 106/61/59 | 13 |

Confronto con i giorni precedenti (stesso campo): glm-5.2 era sotto floor nel 54–59% delle risposte (mediana 0,30)
dal 17 al 21/09. **Con GLM-5.3 la quota sale a 75,9% (mediana 0,25).** È un effetto della deroga di swap, da leggere
nella segmentazione before/after dichiarata nel charter. Non è una proposta di taratura.

| Tipo segnale | Righe | % | Score medio | Min | Max | Sopra gate |0,30| | `ensemble_std`=0 |
|---|---|---|---|---|---|---|---|
| ensemble glm-5.3+gpt-oss | 147 | 63,4% | +0,024 | −0,450 | +0,403 | 11 | 38 |
| single gpt-oss (fallback_used) | 76 | 32,8% | +0,018 | −0,420 | +0,420 | 5 | 14 |
| single glm-5.3 (fallback_used) | 6 | 2,6% | +0,052 | −0,138 | +0,200 | 0 | 3 |
| finbert (reale) | 3 | 1,3% | +0,023 | +0,011 | +0,048 | 0 | 3 |

* **Latenza**: nessuna telemetria per chiamata (F-086). Dal log dei task: 120 cicli sentiment in seduta,
  232 item, durata mediana del task 152,6 s, **per-item mediana 58,8 s** (09-17: 10,5 s; 09-18: 9,6 s; 09-21: 62,0 s),
  15 task oltre 300 s, massimo 689,9 s. Pubblicazione→segnale Benzinga: mediana 8,3 min, p90 93,4 min
  (09-15/16: 0,5 min). La regressione **precede** lo swap GLM (già presente il 21/09) → DAY-013.
* **Refusal/invalid output**: nessun parse-fail osservato. Timeout: 27 (orari 10–19).
* **Disaccordo**: su 217 segnali con due risposte, 17 hanno spread di polarity ≥ 0,30 e **14 segni opposti**. Esempio
  NFLX 12219: gpt-oss −0,6/0,6 contro glm +0,2/0,25. glm viene escluso dal floor e il segnale esce −0,36 su un
  articolo il cui titolo è rialzista (DAY-010).
* **Pesi effettivi**: 0,5/0,5 invece di 0,7/0,3 (DAY-002). Verificato riproducendo lo score su 49/49 segnali a due contributori.
* **Fallback FinBERT reali**: 3 (SOXX 13:35, SPY 15:02, LLY 17:48), tutti «Ollama timeout». `body_chars` 471/43/435 >
  0: FinBERT ha visto parte del corpo in tutti e tre. Nessuna entità HTML nell'input.
* **Offline/background**: confermato. I modelli girano solo in `worker-inference` (coda `inference`) e il ciclo
  portfolio legge `sentiment_signals` dal DB. Nessuna chiamata LLM nel percorso ordini.

---

## 6. Segnali finali per ticker (quelli che hanno toccato il gate o un ordine)

| Ticker | Segnale | Ora | Score | Tipo | Destino |
|---|---|---|---|---|---|
| GOOGL | 11992 | 13:31:54 | +0,341 | ensemble | SKIP_PYRAMIDING (S1 dal 09-01) |
| LLY | 11993 | 13:32:01 | +0,398 | ensemble | superato da segnali successivi, nessuna decisione |
| MU | 11997 | 13:36:34 | +0,320 | ensemble | già S4 a libro; sovrascritto 13:52 (+0,025) |
| META | 12008 | 13:50:50 | +0,318 | ensemble | **mai valutato** (sovrascritto 14:03, primo ciclo 14:07) |
| ERIC | 11999/12001/12042 | 13:41–14:35 | −0,385/−0,450/−0,373 | ensemble | RANK_LONG_ONLY |
| BABA | 12064 | 14:57:33 | +0,383 | ensemble | **BUY 15:07** |
| AMD | 12100 | 15:46:04 | +0,385 | single gpt-oss | SKIP_FALLBACK |
| SOXX | 12117 | 16:23:42 | +0,403 | ensemble | SKIP_PYRAMIDING (S1 dal 07-28) |
| CSCO | 12127 | 16:45:51 | −0,420 | single gpt-oss | long-only; posizione S4 **tenuta** |
| BABA | 12151 | 17:34:58 | +0,348 | ensemble | **BUY 17:37** |
| XLK | 12178 | 18:09:03 | +0,420 | single gpt-oss | SKIP_FALLBACK |
| META | 12201 | 18:40:28 | +0,420 | single gpt-oss | SKIP_FALLBACK |
| META | 12214 | 19:03:31 | +0,354 (gate 0,424) | ensemble | **BUY 19:07** |
| NFLX | 12219 | 19:29:07 | −0,360 | single gpt-oss | long-only |

Disposizioni S4 (`s4_intent_events`): 1.732 candidati, SKIP_ENTRY_GATE 704, SKIP_ENTRY_FRESHNESS 563,
SKIP_FALLBACK 199, SKIP_STALE 138, **SKIP_PYRAMIDING 102** (contro **4** righe in `execution_decisions`),
SKIP_IDEMPOTENCY 12, RANK_OUTSIDE_TOP_N 8 (MRK 11673 e AMAT 11781, segnali di giorni prima), RANK_LONG_ONLY 3,
SUBMITTED 3.

---

## 7. Ordini generati/eseguiti

| Decisione | Strategia | Ticker | Azione | Qty | Prezzo atteso | Fill | Stato | Broker | Rationale | Segnale | Risk check | Anomalie |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 15:07:00 (38167) | S4 | BABA | BUY | 12,3054 | n/d (`decision_price` NULL) | 116,7025 | filled 15:07:07 | Alpaca paper | +0,382, peso 2,0%, regime 0,7 | 12064 | gate 0,30, ranking top-N (rank 3), P0-05, idempotenza | news già prezzata (F-030), solo titolo |
| 15:22:04 | S4 stop | BABA | SELL stop | 12 | — | — | canceled 16:52 | Alpaca paper | stop protettivo | — | — | 97,5% copertura, un ciclo dopo l'ingresso (F-022) |
| 16:52:00 (38889) | S4 | BABA | SELL | 12,3054 | — | 116,56 | filled 16:52:05 | Alpaca paper | `below_entry_gate` (+0,188) dopo hold minimo 90 min | NULL | hysteresis; stop cancellato prima | SELL con sentiment positivo (F-013), `signal_id` NULL (F-011) |
| 17:22:00 (39098) | S4 | ARM | SELL | 1,3104 | — | 330,36 | filled 17:22:05 | Alpaca paper | `below_entry_gate` (−0,011) | NULL | — | uscita da articolo macro a 14 ticker (F-008) |
| 17:37:00 (39203) | S4 | BABA | BUY | 12,3415 | n/d | 116,36 | filled 17:37:05 | Alpaca paper | +0,348, peso 2,0% | 12151 | gate, rank 4, idempotenza | ri-ingresso 45 min dopo la SELL (F-013) |
| 17:52:04 | S4 stop | BABA | SELL stop | 12 | — | — | new | Alpaca paper | stop | — | — | 97,2% |
| 19:07:00 (39855) | S4 | META | BUY | 1,9489 | n/d | 738,95 | filled 19:07:06 | Alpaca paper | +0,354 × vel. 1,2 = 0,424 | 12214 | gate, rank 3 | — |
| 19:07:06 | S4 stop | META | SELL stop | 1 | — | — | new | Alpaca paper | stop | — | — | **51,3%** di copertura (F-022) |

Nessun ordine S1: gate di ribilanciamento chiuso (ultimo ribilanciamento 2026-09-01). Ogni ciclo dichiara 5 ordini
target (AMAT, GM, SOXX, NOW, BABA/…) bloccati da P0-05. `orders_count` 5 contro 0–1 inviati (F-014).

---

## 8. PnL / rendimento

Prezzi: barre giornaliere e al minuto Alpaca (market data, sola lettura). Chiusura 22/09 vs chiusura 21/09.

| Voce | Ticker | Qty | Da → A | $ | Tipo |
|---|---|---|---|---|---|
| Realizzato (aperta oggi) | BABA #1023 | 12,3054 | 116,7025 → 116,56 | **−2,54** net (gross −1,75, costi 0,79) | realizzato |
| Realizzato (aperta 21/09) | ARM #1021 | 1,3104 | 315,584 → 330,36 | **+19,14** net (di cui +9,78 maturati oggi da 322,90) | realizzato |
| Aperta oggi | BABA #1024 | 12,3415 | 116,36 → 116,31 | −0,62 gross | non realizzato |
| Aperta oggi | META #1025 | 1,9489 | 738,95 → 736,595 | −4,59 gross | non realizzato |
| Pre-esistente S4 | MU | 1,4634 | 1043,96 → 1096,16 | +76,39 | non realizzato |
| Pre-esistente S4 | MRVL | 6,3743 | 257,38 → 262,36 | +31,74 | non realizzato |
| Pre-esistente S4 | INTC | 14,5237 | 121,78 → 123,86 | +30,21 | non realizzato |
| Pre-esistente S4 | QQQ | 2,0745 | 741,47 → 747,46 | +12,43 | non realizzato |
| Pre-esistente S4 | PANW | 3,8762 | 371,76 → 374,57 | +10,89 | non realizzato |
| Pre-esistente S4 | WDC | 0,3347 | 448,17 → 464,60 | +5,50 | non realizzato |
| Pre-esistente S4 | NOW | 2,9791 | 137,68 → 137,00 | −2,03 | non realizzato |
| Pre-esistente S4 | XLE | 22,0056 | 62,46 → 61,78 | −14,96 | non realizzato |
| Pre-esistente S4 | CSCO | 17,1357 | 111,46 → 106,44 | **−86,02** | non realizzato |
| **S4 giornata** | | | | **≈ +65,2** (costi stimati di ingresso esclusi, ~1 $) | |
| **Book (broker)** | | | 110.025,01 → 110.041,29 | **+16,28** (snapshot 20:00) | equity |
| S1 (residuo) | | | | ≈ −49 (derivato: book − S4; include la deriva after-hours dello snapshot) | stima |

* Per strategia: S4 ≈ +65 $, S1 ≈ −49 $ (residuo, non misurato per ticker). Benchmark: SPY −0,02%, QQQ +0,81%.
* Il segno positivo di S4 dipende da MU/MRVL/INTC/QQQ/PANW. Sono proprio le posizioni che S4 **non può chiudere** (DAY-001).
* Slippage: non misurabile. `decision_price` è NULL su tutte le decisioni BUY/SELL e `slippage_est` copia il costo (F-015).
  Proxy segnale→fill: BABA 117,12 (14:57) → 116,70 fill (−0,36%), META 738,61 (19:07) → 738,95 (+0,05%).
* Commissioni: 0 (Alpaca). `cost_usd` modellato 0,79 + 0,22 + 0,76 + 0,25 = 2,02 $.
* `/api/trades` mostra la SELL BABA con `entry_price` 116,36 (quello del **secondo** BUY) e `gross_pnl` **+2,46**. Il ledger
  `trades` dice −1,75 (DAY-016).

---

## 9. Correttezza buy/sell

| Controllo | Esito | Nota |
|---|---|---|
| BUY solo quando consentito | ✅ | 3 BUY, tutti con segnale ensemble ≥ 0,30, rank ≤ top-N, P0-05 e idempotenza verificati |
| SELL/exit corretti | ⚠️ | BABA e ARM chiuse secondo la regola dichiarata. **7 posizioni S4 non possono uscire** (DAY-001) |
| Stop-loss | ⚠️ | nessuno scattato. Coperture 97,5/97,2/**51,3%**. AMAT −21%, WDC −17% senza stop (sub-one-share) |
| Signal flip | ⚠️ | CSCO −0,15/−0,42/−0,29 su posizione S4 senza uscita (DAY-001) |
| Max holding days | ❌ | CSCO 28 giorni, XLE 22, WDC 63 (DAY-001) |
| Rebalance band | ⚠️ | nessuna banda fra gate 0,30 e uscita: BABA SELL a +0,188 e ri-BUY 45 min dopo (DAY-004) |
| Ordini duplicati | ✅ | nessuno. 12 `SKIP_IDEMPOTENCY` / `SIGNAL_DUPLICATE_SKIP` |
| Ordini contrari ravvicinati senza rationale | ⚠️ | BABA SELL 16:52 → BUY 17:37: entrambi con rationale, ma è churn (DAY-004) |
| Ticker non consentiti | ✅ | tutti in watchlist |
| Fuori orario | ✅ | tutti fra 15:07 e 19:07 |
| Dati stale | ✅ | 3 SKIP_STALE, 563 SKIP_ENTRY_FRESHNESS |
| LLM output non valido | ✅ | nessun parse-fail. Single-model esclusi dal ranking BUY |
| Circuit breaker | ✅ | loss-feedback S4 `triggered: False` su tutti i controlli. Nessun breaker attivo |
| Strategia disabilitata | ✅ | S1+S4 attive, `execution.engine=portfolio` |
| Paper/live | ✅ | paper verificato (URL e snapshot) |
| Idempotenza retry Celery | ✅ | nessun doppio invio |
| Riconciliazione | ⚠️ | 45/46 al centesimo. UNH ledger 1,5926 vs broker 0,5926 e il riconciliatore dice «anomalies: 0» (DAY-015) |

Pattern specifici: roundtrip < 30 min **nessuno** (BABA 1h45). Pyramiding > 3 BUY **nessuno**. SELL con sentiment
positivo **sì** (BABA +0,188, DAY-004). `fallback_used=True` su tutti i simboli **no** (Ollama su tutta la sessione).
NO-ORDER (decisione senza ordine) **no** (3 BUY + 2 SELL, 5 ordini). Score < 0,05 che genera ordine: **SELL ARM su −0,011**
(uscita per regola, DAY-005). Ordini identici nello stesso minuto **no**.

`exit_mechanism`: le due righe del 22/09 (`below_entry_gate`) sono **post-#184**, cioè disposizioni osservate e non
stime per età. `trades.exit_reason` riporta invece `hold_minimum_expiry` (BABA) e `portfolio_sell` (ARM) per le
stesse uscite. Sono due vocabolari diversi, non una contraddizione di meccanismo.

---

## 10. Anomalie trovate

### [DAY-001] Le posizioni S4 dentro il target congelato di S1 non possono uscire: 7 su 11, la più vecchia da 28 giorni

* Tipo: Bug
* Area: Signal / Orders / Risk
* Evidenza:
  * file/log/tabella: Redis `strategy:rebalance_state:S1`; `trades`; `execution_decisions`; log worker; `src/workers/portfolio_scheduler.py` (`_persist_rebalance_state`)
  * timestamp: tutta la seduta; `last_rebalance` S1 = 2026-09-01T14:07:00Z
  * snippet/query:
    ```
    strategy:rebalance_state:S1 → 46 target_weights, fra cui
      CSCO 0,0236  XLE 0,0236  QQQ 0,0236  PANW 0,0211  INTC 0,0145  MRVL 0,0120  MU 0,0118  WDC 0,0116
    trades S4 entrati dal 2026-08-20, per appartenenza al target S1:
      fuori dal target: 63 chiusi, 3 aperti (BABA, META, NOW — tutti ≤ 1 giorno)
      dentro il target:  2 chiusi (QQQ 981, MU 989, entrambi sentiment_reversal), 7 aperti (CSCO, XLE, PANW, MRVL, INTC, QQQ, MU)
    log 18:07: "Strategy S1: rebalance gate closed — holding 43 position(s)"; "merged_weights=45 symbols"
    CSCO: segnali freschi −0,150 (16:11), −0,420 (16:45, single), −0,294 (18:06) → solo SKIP_THRESHOLD, nessuna SELL
    ```
* Descrizione: S1 non ribilancia dal 01/09 e a ogni ciclo ridichiara i suoi pesi target congelati. Quel dizionario
  contiene anche simboli che S4 ha comprato per conto suo, a date diverse (CSCO 08-25, XLE 08-31, PANW 09-14,
  MRVL/INTC/QQQ 09-16, MU 09-17). Quando S4 porta il proprio peso a zero (sotto gate, reversal, freschezza), il combiner
  somma comunque il peso S1 e la posizione resta. Per BABA e ARM, fuori dal target S1, la stessa regola ha venduto
  entro poche ore. CSCO ha ricevuto tre segnali negativi freschi e non è stata toccata. Le uniche due uscite S4 su
  simboli del target S1 negli ultimi 33 giorni sono passate per `sentiment_reversal`, cioè un percorso che ignora il combiner.
* Impatto: la P&L che il charter attribuisce a S4 include posizioni che S4 non gestisce più. Oggi il segno di S4
  (+65 $) dipende da MU/MRVL/INTC/QQQ/PANW. Controfattuale corto: vendendo alla regola S4 (secondo ciclo dopo il primo
  segnale fresco sotto gate) CSCO 16:37 @105,03, XLE 14:52 @62,36, PANW 14:52 @369,26, INTC 17:37 @121,74, QQQ 17:37
  @745,08, MU 14:22 @1081,27, MRVL 19:07 @264,59 (fallback_filtered), contro la chiusura, si ottiene **−72,50 $**.
  In altre parole, il disarmo ha *reso* 72,50 $ oggi. Resta però un'altra strategia da quella dichiarata. Si lega a F-025 (età) e F-031
  (lo stesso intreccio S1/S4 visto dal lato ingresso) ma ha una causa diversa: non il preserve-stale, il target S1 congelato.
* Severità: High
* Confidenza: High sul meccanismo (63 vs 2, pesi letti da Redis). Medium sul costo (isteresi approssimata a 2 cicli).
* Azione consigliata: ticket di correttezza. Il target congelato di S1 non deve contenere posizioni di proprietà S4,
  oppure l'uscita S4 deve ridurre la parte S4 della posizione indipendentemente dal peso S1. Prima del 28/09 va
  dichiarato nel charter che la P&L S4 delle 7 posizioni non è P&L della regola S4.
* Test/monitor consigliato: test del combiner con un simbolo presente nel target S1 held e portato a zero da S4 →
  deve produrre una SELL della quota S4. Monitor giornaliero «posizioni S4 nel target S1» con età.
* → ledger **F-089** (nuovo)

### [DAY-002] Lo swap GLM-5.3 ha azzerato in silenzio i pesi LOO-ICIR: l'ensemble è passato da 0,7/0,3 a 0,5/0,5

* Tipo: Bug
* Area: LLM / Signal
* Evidenza:
  * file/log/tabella: Redis `ensemble:weights:current`; `worker-inference-2026-09-22.log`; `sentiment_signals` × `llm_responses`; `src/llm/model_registry.py::normalize_weights_for_active_models`; `src/llm/ensemble.py::_w`
  * timestamp: dal deploy delle 07:32; 126 warning nella giornata
  * snippet/query:
    ```
    ensemble:weights:current = {"glm-5.2:cloud": 0.70, "gpt-oss:20b-cloud": 0.30, "source": "auto_apply"}
    WARNING Ignoring weights for inactive sentiment models: ['glm-5.2:cloud']   (×126)
    normalize → {"gpt-oss:20b-cloud": 1.0};  _w(o) = o.confidence * weights.get(o.model_id, 1.0)  → glm-5.3 = 1.0
    score riprodotto con pesi uguali: 49/49 segnali a due contributori (09-22); con 0,7/0,3: 1/49
    ```
* Descrizione: la PR #643 ha spostato la chiave `glm52` su `glm-5.3:cloud` ma i pesi in Redis sono indicizzati per
  `model_id`. Al caricamento il peso di `glm-5.2:cloud` viene scartato e quello di `gpt-oss` rinormalizzato a 1,0.
  `glm-5.3`, assente dal dizionario, prende il default 1,0. Il risultato è un ensemble a pesi **uguali**. La
  discontinuità registrata nel charter (riga «model_id … swap GLM-5.3», punto b) dice invece che i pesi pre-deploy
  restano «ereditati come stantii» fino al prossimo `run_weekly_weights`. È falso: non sono ereditati, sono scartati.
* Impatto: da oggi gli score d'ensemble cambiano per due ragioni sovrapposte, il modello (dichiarata) e i pesi (non
  dichiarata). Controfattuale corto con 0,7/0,3 sugli stessi output: due segnali cambiano lato gate (GOOGL 0,341→0,296,
  MU 0,320→0,294), entrambi senza conseguenze d'ordine (GOOGL bloccato da P0-05, MU già a libro). I tre BUY restano sopra
  gate (BABA 0,421/0,335, META 0,320×1,2). **Costo della giornata: 0,00 $.** La serie però è contaminata.
* Severità: Medium (High per l'interpretabilità del 28/09)
* Confidenza: High
* Azione consigliata: correggere l'annotazione del charter (è una correzione di strumento, non una taratura): «pesi
  effettivi 0,5/0,5 dal 2026-09-22 07:32 UTC». Ticket di correttezza: una rinomina di `model_id` dietro una chiave
  stabile deve migrare o invalidare esplicitamente i pesi, non cadere sul default con un WARNING.
* Test/monitor consigliato: test che, con pesi per un `model_id` non più attivo, il loader alzi un errore o logghi i
  pesi effettivi usati. Persistere i pesi effettivi per segnale.
* → ledger **F-088** (nuovo)

### [DAY-003] BABA comprata su un titolo GDELT che racconta un rialzo già avvenuto

* Tipo: Anomalia
* Area: News / Signal
* Evidenza:
  * file/log/tabella: `news_log` 12065; `sentiment_signals` 12064; `trades` 1023; barre Alpaca
  * timestamp: pub. 14:15, riga 14:57:33, BUY 15:07:00, SELL 16:52:00
  * snippet/query: `body_full` = «Alibaba Jumps 4% as Zhenwu V900 Chip Targets the Gap NVIDIA Left in China; Baidu Sits Tight» (91 char, identico al titolo). BABA apre 120,15 (+3,8% sulla chiusura 115,75), 14:15 118,03, fill 116,70.
* Descrizione: l'articolo GDELT porta solo il titolo, che descrive il gap d'apertura. Quando il segnale arriva il
  movimento si è già consumato e sta rientrando. glm-5.3 dà +0,7/0,75 su 91 caratteri e nessun `risk_flag`.
* Impatto: trade 1023 net **−2,54 $** (misurato). Il secondo ingresso (1024, altro titolo GDELT «Alibaba unveils new AI
  chip…», 59 char) ripete lo schema su notizia del mattino. Qui glm segnala `already_priced_in`, `low_source_quality` ma il
  flag non gate-a (QX-01, per disegno): mark −0,62 $.
* Severità: Medium · Confidenza: High
* Azione consigliata: nessuna taratura. Misurare nel golden set QX-01 la quota di segnali da fonti «solo titolo».
* Test/monitor consigliato: contatore giornaliero dei segnali sopra gate con `body_full = title`.
* → ledger **F-030**

### [DAY-004] BABA venduta a +0,188 e ricomprata 45 minuti dopo

* Tipo: Anomalia
* Area: Orders / Signal
* Evidenza:
  * file/log/tabella: `execution_decisions` 38889, 39203; `trades` 1023, 1024
  * timestamp: SELL 16:52:00 @116,56; BUY 17:37:00 @116,36
  * snippet/query: `[below_entry_gate] … generated 2026-09-22 15:27 UTC, score=+0.188: weight 0.0%, position closed.`
* Descrizione: nessuna banda fra gate d'ingresso (0,30) e uscita. Un secondo articolo positivo sullo stesso evento
  (+0,188) chiude la posizione aperta sul primo (+0,383) appena scade l'hold minimo. Un terzo la riapre.
* Impatto: controfattuale corto (tenere #1023 fino alla chiusura) −4,83 $ gross, −5,23 $ con costo di ingresso.
  Esito reale #1023 + #1024 fino alla chiusura: −3,54 $. Il churn ha **reso 1,69 $** (costo −1,69).
* Severità: Low · Confidenza: High
* Azione consigliata: nessuna (taratura congelata). Resta nel conteggio di ricorrenza.
* Test/monitor consigliato: contatore SELL→BUY stesso simbolo entro 60 min.
* → ledger **F-013**

### [DAY-005] ARM chiusa da un articolo macro a 14 ticker con score −0,011

* Tipo: Anomalia
* Area: News / Signal / Orders
* Evidenza:
  * file/log/tabella: `news_log` 12138 (`content_hash` 92f8a370…); `sentiment_signals` 12137; `execution_decisions` 39098; `trades` 1021
  * timestamp: pub. 16:59:30, segnale 17:05:48, SELL 17:22:00
  * snippet/query: stesso articolo → AAPL −0,004, AMD −0,008, AMZN −0,003, **ARM −0,011**, BABA 0,000, GOOGL −0,031, INTC +0,004, META −0,003, MSFT −0,018, NVDA −0,005, QCOM 0,000, QQQ −0,018, SPY −0,008, TSLA −0,004
* Descrizione: il segnale ARM +0,58 del 21/09 era tenuto in vita da FIX-D («nessun contro-segnale»). Un editoriale
  macro (Arora Report, «CPU Fever») cita ARM in una riga e produce un contro-segnale quasi nullo, che basta a chiudere.
* Impatto: realizzato +19,14 $. Tenendo fino alla chiusura (333,20) si sarebbero presi altri **3,72 $** (costo attribuito).
* Severità: Low · Confidenza: High
* Azione consigliata: nessuna taratura. Il caso resta nel conteggio di F-008.
* → ledger **F-008**

### [DAY-006] Fan-out: metà delle righe scorate viene da articoli multi-ticker

* Tipo: Rischio · Area: News
* Evidenza: `news_log`, `content_hash`: 146 articoli → 232 righe. 33 articoli multi-ticker → **119 righe (51,3%)**, massimo 14.
* Descrizione e impatto: stessa struttura di F-012. Oggi ha prodotto l'uscita ARM (DAY-005) e la maggior parte dei
  segnali «macro» su SPY/META/NVDA. Costo non stimato separatamente (quello ARM è in F-008).
* Severità: Medium · Confidenza: High
* → ledger **F-012**

### [DAY-007] Primo ciclo alle 14:07: META +0,318 delle 13:50 non ha mai visto un ciclo

* Tipo: Anomalia · Area: Ops / Orders
* Evidenza: `portfolio_cycles` 1610 (14:07:00); `mobile_events` `portfolio_cycle_session_grid` (open_gap 37,01 min); `sentiment_signals` 12008 (13:50:50, +0,318), 12017 (14:03:55, 0,000)
* Descrizione: le finestre beat in UTC fisso lasciano scoperti i primi 37 minuti in EDT. Un ciclo alle 13:52 avrebbe
  visto META +0,318 (fresco, ensemble, non a libro) e comprato.
* Impatto: congetturale, size tipica S4 2.200 $. Ingresso 13:52 ≈ 744,88–745,43, chiusura 736,68 → **−25,83 $**
  (il buco ha evitato una perdita).
* Severità: Medium · Confidenza: Medium
* → ledger **F-021**

### [DAY-008] META: segnale sopra gate sovrascritto 13 minuti dopo da uno nullo

* Tipo: Anomalia · Area: Signal
* Evidenza: `sentiment_signals` 12008 → 12017. S4 legge solo l'ultimo segnale per simbolo.
* Impatto: stesso episodio di DAY-007. Il costo è registrato lì (null qui per non contarlo due volte).
* Severità: Low · Confidenza: High
* → ledger **F-023**

### [DAY-009] P0-05 blocca GOOGL e SOXX sopra gate (a libro da S1), e traccia 4 blocchi su 102

* Tipo: Anomalia · Area: Orders / Data
* Evidenza: `execution_decisions` SKIP_PYRAMIDING 14:07 GOOGL 11992 (+0,341, «a libro dal 2026-09-01») e 16:37 SOXX 12117 (+0,403, «dal 2026-07-28»); `s4_intent_events` SKIP_PYRAMIDING **102** contro **4** righe decisione; log: NOW ×24, GM ×24, AMAT ×19, SOXX ×14, ARM ×12
* Impatto: congetturale 2.200 $. GOOGL 360,09 → 351,185 (−54,41 $ evitati), SOXX 566,74 → 572,75 (+23,33 $ mancati).
  Netto **−31,08 $**. Tracciabilità: 4% dei blocchi in `execution_decisions`.
* Severità: Medium · Confidenza: Medium
* → ledger **F-031**

### [DAY-010] NFLX: segni opposti fra i modelli, il dissenziente è sotto floor e il segnale esce −0,36 su un titolo rialzista

* Tipo: Anomalia · Area: LLM
* Evidenza: `llm_responses` su 12219: gpt-oss −0,6/0,6 («downgrade … likely to depress»), glm-5.3 +0,2/0,25 («mildly bullish contrarian»). Titolo «Netflix Stock 'High on the List' for Former Hedge Fund Manager». `ensemble_std` 0,566 (il fix F-054 misura bene), ma la guardia decide sugli eleggibili.
* Descrizione: nella giornata 14 segnali con segni opposti. Il floor 0,40 toglie il dissenziente e la divergenza non
  arriva mai alla guardia. Il fix F-054 ha reso visibile il fenomeno, la guardia resta per disegno sugli eleggibili.
* Impatto: nessun trade (long-only) → costo non stimato.
* Severità: Low · Confidenza: High
* → ledger **F-054**

### [DAY-011] 82 segnali su 232 (35,3%) sono letture a modello singolo marcate `fallback_used`, e glm-5.3 sta sotto floor nel 75,9% delle risposte

* Tipo: Anomalia · Area: LLM / Data
* Evidenza: `sentiment_signals.model_id` `single:*` = 82 (70 hanno due risposte a DB). Esito task: somma `finbert_fallbacks` = **85** contro **3** righe `finbert_fallback_events`. glm-5.3 sotto 0,40: 167/220 (glm-5.2 54–59% nei 4 giorni precedenti).
* Descrizione: la lettura a modello singolo viene esclusa dal ranking BUY come fallback (29 SKIP_FALLBACK, fra cui AMD +0,385,
  XLK +0,420, META +0,420) e il task la conta come fallback FinBERT. Con GLM-5.3 la quota di glm sotto floor sale di ~17 punti.
* Impatto: strutturale, costo non stimato. È la base del conteggio «FinBERT fallback rate» del §16.
* Severità: Medium · Confidenza: High
* → ledger **F-078**

### [DAY-012] 98 dei 147 segnali d'ensemble non hanno nessuna risposta marcata `eligible`

* Tipo: Anomalia · Area: Data / LLM
* Evidenza: join `sentiment_signals` (ensemble) × `llm_responses`: `eligible=true` su 0 risposte per 98 segnali. Il retry a floor 0 (#90) non si propaga al flag.
* Impatto: `llm_responses.eligible` non dice chi ha contribuito. Costo non stimato.
* Severità: Low · Confidenza: High
* → ledger **F-010**

### [DAY-013] Latenza di scoring ~6× dal 21/09: 59 s per articolo, pubblicazione→segnale p90 93 minuti

* Tipo: Anomalia · Area: LLM / Ops
* Evidenza: log task `run_sentiment_worker`: per-item mediana 10,5 s (09-17) · 9,6 (09-18) · **62,0 (09-21) · 58,8 (09-22)**. 15 task > 300 s, max 690 s. Pub→segnale Benzinga mediana 0,5 min (09-15/16) → 8,3 min, `raw_ingested_at`→riga mediana 27 s → 419 s. 27 timeout Ollama.
* Descrizione: la regressione precede lo swap GLM (è già presente il 21/09 con glm-5.2). Senza traccia di trasporto
  delle chiamate Ollama (F-086) non si capisce se sia il provider, i retry o la coda.
* Impatto: consuma la finestra di freschezza d'ingresso (2 h). Costo non stimato.
* Severità: Medium · Confidenza: Medium
* → ledger **F-019**

### [DAY-014] Stop META al 51,3% della posizione; AMAT (−21%) e WDC (−17%) senza stop

* Tipo: Rischio · Area: Risk / Broker
* Evidenza: ordine `81142bf6` qty 1 su 1,9489; log `#161: AMAT unprotected at -21.3% … sub_one_share` (×24), WDC −15,4→−17,9% (×23)
* Impatto: metà del nozionale META senza stop. Costo non stimato (nessuno stop scattato).
* Severità: Medium · Confidenza: High
* → ledger **F-022**

### [DAY-015] UNH: 1 azione di scarto fra ledger e broker, riconciliatore «anomalies: 0»

* Tipo: Bug · Area: PnL / Broker
* Evidenza: `trades` 279 qty 1,592634, `quantity_remaining` NULL; `/api/positions` UNH 0,592634; log 21:35 `partially_wound_down_coheld: 1, anomalies: 0`
* Impatto: scarto invariato dal 15/09. Costo non stimato.
* Severità: Medium · Confidenza: High
* → ledger **F-048**

### [DAY-016] `/api/trades` attribuisce alla SELL BABA il prezzo del BUY successivo: +2,46 $ invece di −1,75 $

* Tipo: Bug · Area: Frontend / PnL
* Evidenza: `/api/trades` riga `8aacfe22`: `entry_price` 116,36, `gross_pnl` 2,4611, `exit_reason` portfolio_sell. `trades` 1023: entry 116,7025, gross −1,75.
* Impatto: il P&L di un roundtrip esposto dall'API ha segno sbagliato quando lo stesso simbolo viene ricomprato. Costo non stimato.
* Severità: Medium · Confidenza: High
* → ledger **F-084**

### [DAY-017] Le due SELL non portano `signal_id`

* Tipo: Anomalia · Area: Data
* Evidenza: `execution_decisions` 38889, 39098: `signal_id` NULL. Il segnale causante è citato solo nel testo del `reason`.
* Severità: Low · Confidenza: High
* → ledger **F-011**

### [DAY-018] `decision_price` NULL su tutte le decisioni d'ordine: lo slippage non è misurabile

* Tipo: Anomalia · Area: PnL / Data
* Evidenza: `execution_decisions` 38167/38889/39098/39203/39855: `decision_price` NULL. `trades.slippage_est` NULL.
* Severità: Low · Confidenza: High
* → ledger **F-015**

### [DAY-019] `orders_count` = 5 su tutti i cicli contro 0–1 ordini inviati

* Tipo: Anomalia · Area: Ops
* Evidenza: `portfolio_cycles` 1610–1633. I 5 ordini target (AMAT, GM, SOXX, NOW, BABA…) vengono bloccati da P0-05 a ogni ciclo. `submitted` 0/1 nell'esito del task.
* Severità: Low · Confidenza: High
* → ledger **F-014**

### [DAY-020] Decay monitor: S1, S2 e S4 riportano lo stesso IC (−0,043), S1 e S2 lo stesso drawdown (13,4%)

* Tipo: Anomalia · Area: Risk
* Evidenza: log 21:00:00 `DECAY CRITICAL [S1] IC … 0.035 to -0.043`, `[S2] … 0.042 to -0.043`, `[S4] … 0.028 to -0.043`; drawdown 13,4% su S1 e S2.
* Descrizione: metriche globali confrontate con tre baseline, fra cui S2 che non è attiva.
* Severità: Medium · Confidenza: High
* → ledger **F-004**

### [DAY-021] I 5 DECAY CRITICAL restano nel log: nessun canale

* Tipo: Anomalia · Area: Ops
* Evidenza: nessuna riga `mobile_events` fra 21:00 e 21:05. Nessun invio Telegram associato.
* Severità: Medium · Confidenza: High
* → ledger **F-062**

### [DAY-022] Telegram 400 Bad Request su tre alert

* Tipo: Bug · Area: Ops
* Evidenza: log worker 14:07:06, 14:22:05 (alert #161 AMAT/WDC scoperte), 23:05:00
* Severità: Medium · Confidenza: High
* → ledger **F-005**

### [DAY-023] Segreti in chiaro nei log: bot token Telegram e `api_key` FRED

* Tipo: Rischio · Area: Ops
* Evidenza: `worker-2026-09-22.log`, `worker-inference-2026-09-22.log`: URL `https://api.telegram.org/bot<token>/…` (httpx INFO e WARNING di errore); `…/fred/series/observations?series_id=VIXCLS&api_key=…` nell'ERROR delle 07:00:04
* Severità: Medium · Confidenza: High
* → ledger **F-018**

### [DAY-024] Benchmark SPY: 84 fetch falliti per limite SIP, nessun alert

* Tipo: Anomalia · Area: Data
* Evidenza: `SPY benchmark fetch failed: {"message":"subscription does not permit querying recent SIP data"}` ×84
* Severità: Low · Confidenza: High
* → ledger **F-016**

### [DAY-025] Regime detection 07:00: FRED 500 e task «succeeded … None»

* Tipo: Anomalia · Area: Ops
* Evidenza: log inference 07:00:04 ERROR + 07:00:05 `succeeded in 5.1s: None`. Il giro delle 13:30 riesce.
* Severità: Low · Confidenza: High
* → ledger **F-017**

### [DAY-026] `ingestion_stats_daily`: 6.296 duplicati contro 1.549 fetched per alpaca_benzinga

* Tipo: Anomalia · Area: Data
* Evidenza: `ingestion_stats_daily` 2026-09-22; `news_queue_drops` `duplicate_id` 6.296
* Severità: Low · Confidenza: High
* → ledger **F-007**

### [DAY-027] Tre alert della sera aperti e chiusi nello stesso secondo

* Tipo: Bug · Area: Ops
* Evidenza: `mobile_events` `pipeline:portfolio_cycle_session_grid` (open gap 37 min), `coverage:held_no_news_loss:AMAT` (−20,4%), `…:SBUX` (−9,7%, 9 sedute senza news): `first_observed_at` 22:50:00, `resolved_at` 22:50:01
* Descrizione: il valutatore generico chiude incidenti che non possiede. L'alert giusto sul buco d'apertura (DAY-007) vive un secondo.
* Severità: Medium · Confidenza: High
* → ledger **F-058**

### [DAY-028] Evidenza persa: il ledger del 17/09 non è mai arrivato, nessun forense per il 18 e il 21, dossier fermi al 17/09

* Tipo: Anomalia · Area: Ops / Data
* Evidenza: `docs/FORENSIC_DAILY_REPORT_2026-09-17.md` non tracciato da git (scritto 2026-09-18 14:53). Cita due id nuovi
  «F-087» (Decision Log SELL META incoerente) e «F-088» (min_confidence spegne l'ensemble) che nel ledger **non esistono**:
  il F-087 del ledger è un altro finding (datato 08-28), `prossimo_id` era 88. `docs/evidence/dossier/` e
  `market_daily.jsonl` si fermano al 2026-09-17. Nessun forense per 2026-09-18 e 2026-09-21.
* Impatto: due giorni di evidenza assenti e uno spazio di id biforcato. Chi legge il report del 17/09 cercherà F-087/F-088 e
  troverà un altro difetto. Questo report assegna F-088 e F-089 a finding nuovi e diversi, e lo scrive qui.
* Severità: Medium · Confidenza: High
* → ledger **F-026**

### [DAY-029] ~45 simboli di watchlist su 96 senza segnali nella seduta

* Tipo: Anomalia · Area: News
* Evidenza: 51 simboli distinti in `sentiment_signals`. Alert `held_no_news_loss` su SBUX (9 sedute) e AMAT (2).
* Nota: proxy su segnali, non la metrica `no_news_backstop` del dossier (assente per il 22/09).
* Severità: Low · Confidenza: Medium
* → ledger **F-001**

### [DAY-030] Il ranking assegna slot a segnali di giorni prima su simboli già a libro

* Tipo: Anomalia · Area: Signal
* Evidenza: `s4_intent_events` RANK_OUTSIDE_TOP_N MRK 11673 (rank 6–7, 6 slot), AMAT 11781 (rank 6, 2 slot). Entrambi a libro, entrambi con P0-05.
* Severità: Low · Confidenza: High
* → ledger **F-051**

### [DAY-031] 185 articoli della coda notturna scartati stale all'apertura

* Tipo: Anomalia · Area: News
* Evidenza: `news_queue_drops` 13:xx `stale` 185, `enqueued_off_session` true; 104 dispatch `market_closed` nella notte
* Severità: Low · Confidenza: High
* → ledger **F-069**

---

## 11. False positive / aree risultate corrette

* **F-076 (entità HTML nel prompt)**: primo giorno di verifica dopo il deploy. 3/3 input FinBERT senza entità
  (`finbert_input ~ '&(amp|#\d+|[a-z]+);'` = false). Le 173 righe `news_log` con entità **non** sono un fallimento,
  come previsto dal charter.
* **F-054 (misura)**: `ensemble_std` ora > 0 su tutti i segnali con spread > 0 (0 casi `std=0` con spread > 0 su 147 ensemble).
* **Titolo nel prompt (F-046)**: `_build_sentiment_prompt` riceve `clean_title`, quindi il difetto «solo corpo» non è più presente nel codice live.
* Nessun ordine fuori orario, duplicato, senza segnale, su ticker fuori watchlist o con dati stale.
* Idempotenza: `SIGNAL_DUPLICATE_SKIP`/`SKIP_IDEMPOTENCY` su BABA (×10) e META (×2).
* Hold minimo 90 min rispettato (BABA venduta a 1h45).
* Stop cancellato prima della SELL BABA («Cancelled 1 protective stop(s) for BABA before SELL»).
* `exit_mechanism` del giorno osservato (post-#184), non stimato per età.
* Swap GLM-5.3: **registrato** come deroga nel charter prima del deploy (lo è la sostituzione del modello, non l'effetto sui pesi: DAY-002).
* Loss-feedback S4 valutato ogni 30 min, `triggered: False`.
* Riconciliazione 45/46 al centesimo.

## 12. Dati mancanti o non accessibili

* Latenza per chiamata LLM, esito HTTP per modello: non persistiti (F-086). Serve una tabella di trasporto.
* Dossier/`market_daily` del 22/09 non generati: copertura `no_news_backstop` e funnel_v2 non disponibili.
* P&L S1 per ticker: non ricostruito (derivato solo come residuo). Query: posizioni S1 × barre giornaliere 21→22/09.
* Pesi effettivi per segnale: non persistiti. Ricostruiti riproducendo la formula.
* `decision_price` NULL: slippage decisione→fill non misurabile.
* Stato Redis a fine 22/09: letto il 23/09, dopo un altro redeploy (10:08 UTC). I pesi e il target S1 hanno `last_rebalance`/`source` coerenti con il 22/09.

## 13. Raccomandazioni immediate (solo correttezza, nessuna taratura)

1. **Charter**: correggere il punto (b) della discontinuità GLM-5.3. I pesi effettivi sono 0,5/0,5 dalle 07:32 UTC del 22/09, non «stantii ereditati» (DAY-002).
2. **Charter**: dichiarare prima del 28/09 che le posizioni S4 dentro il target S1 congelato (7 oggi) non sono gestite dalla regola S4 e vanno escluse o segmentate nella P&L S4 (DAY-001).
3. Recuperare nel ledger i due finding del 17/09 mai registrati, con id nuovi e una nota di mappatura (DAY-028). Il merito è di chi governa il ledger.
4. Verificare la catena cron dei dossier (ferma al 17/09).

## 14. Test o monitor da aggiungere

* Combiner: simbolo nel target S1 held portato a zero da S4 → SELL della quota S4 (DAY-001).
* Monitor «posizioni S4 ∩ target S1 congelato» con età e P&L.
* Loader dei pesi: errore o log dei pesi effettivi quando un `model_id` pesato non è attivo. Persistenza dei pesi per segnale (DAY-002).
* Contatore segnali sopra gate da fonti con `body_full = title` (DAY-003).
* `/api/trades`: test di un roundtrip ripetuto sullo stesso simbolo (DAY-016).
* Latenza per-item del worker sentiment come metrica giornaliera, con allerta sopra 30 s (DAY-013).
* Riconciliatore: uno scarto di qty ≥ 1 azione deve contare come anomalia (DAY-015).

## 15. Ticket tecnici suggeriti

| Ticket | Tipo | Finding | Perché è correttezza |
|---|---|---|---|
| Uscita S4 disarmata dal target S1 congelato | bug | F-089 | la P&L S4 misura un'altra regola |
| Rinomina `model_id` azzera i pesi d'ensemble | bug | F-088 | serie score con pesi non dichiarati |
| `/api/trades` P&L con prezzo del BUY successivo | bug | F-084 | P&L esposto di segno sbagliato |
| Riconciliatore cieco su UNH | bug | F-048 | posizione a DB ≠ broker |
| Valutatore chiude incidenti non suoi | bug | F-058 | l'unico alert sul buco d'apertura vive 1 s |

## 16. Stato sistema

* **Ollama Cloud**: up tutta la sessione (0 ore di downtime). 27 timeout (glm-5.3 14, gpt-oss 13). Ensemble riuscito su 147/232 segnali (63,4%).
* **FinBERT fallback rate**: **3/232 segnali = 1,3%** reali (Ollama timeout). Sulle decisioni: 0 decisioni d'ordine basate su FinBERT.
  Le letture a modello singolo (82, 35,3%) **non** sono fallback FinBERT anche se il task le conta come tali (DAY-011).
* **Worker restart**: 1 evento programmato, 07:32 (deploy PR #643, Warm shutdown di `worker` e `worker-inference`).
  1 SIGKILL del pool `worker-inference` alle 10:29 (hard time limit del turno ombra off-session). Nessun restart in seduta.
* **Redis/Postgres**: up (container da 4 giorni). Nessun MISCONF.
* **Regime**: SIDEWAYS, `regime_mult` 0,7. FRED in errore alle 07:00, ok alle 13:30.
