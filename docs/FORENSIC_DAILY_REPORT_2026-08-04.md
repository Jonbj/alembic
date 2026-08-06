# Forensic Daily Report — 2026-08-04

Analista: sessione autonoma (Trading Systems Forensic Analyst / Senior Backend Engineer / Quant
Operations Reviewer). Modalità **read-only**: nessuna patch, nessun ordine, nessun worker avviato.

Perimetro temporale: 2026-08-04, **timezone UTC** (`src/workers/celery_app.py` →
`timezone="UTC", enable_utc=True`; nessuna ambiguità). Sessione di mercato EDT: 13:30–20:00 UTC.

Fonti: `alembic-postgres-1` (SELECT), `docker compose logs worker|worker-inference|beat`,
Alpaca **read-only** (`get_account`, `get_orders`, `StockBarsRequest`, feed **IEX** — SIP non in
sottoscrizione, cfr. F-016), codice sorgente del repo.

Periodo di sola osservazione (carta del 2026-08-01, **giorno 2 di 40**): nessuna proposta di
taratura. I ticket suggeriti in §15 sono esclusivamente difetti di **correttezza/misura**, cioè
quelli che, se non corretti, rendono sbagliata l'evidenza raccolta nelle prossime settimane.

---

## 1. Executive summary

Giornata **funzionalmente sana sulla catena di esecuzione e strutturalmente rumorosa a monte**.
La pipeline ha girato end-to-end senza errori: 24 cicli ingest, 24 cicli sentiment, 24 cicli
portfolio, 0 ERROR nel worker, nessun restart di container. Riconciliazione ordini→fill→trade
**perfetta**: 11 ordini market decisi = 11 inviati = 11 filled = 11 righe in `trades`, più 7 stop
GTC protettivi. Realizzato del giorno **−57,98 $** su 4 uscite; MTM del book portato dal 08-03
**+790,43 $** (S1 +692,83, S4 +57,36, legacy senza strategia +40,24); equity di chiusura
**110.366,23 $**. Nessun ordine fuori orario, nessun ordine duplicato, nessun pyramiding (il guard
ha bloccato 47 BUY su simboli già aperti), paper mode confermato (`ALPACA_PAPER_MODE=True`).
I difetti stanno tutti **prima** della decisione. Il più grave è nuovo e sistematico: l'estrazione
ticker `org_lookup` su GDELT attribuisce a **MS** (20 righe su 20) e **GS** (8 su 8) articoli su
società terze — Energizer, Sysco, AON, Apollo — perché la banca compare come analista nel
boilerplate; MS ha ricevuto un sentiment **−0,325** da una trimestrale di Energizer. Secondo
difetto nuovo: S4 tiene **solo il segnale più recente per simbolo**, quindi un segnale forte viene
sovrascritto da uno debole generato pochi secondi dopo (CAT +0,648 → +0,013 in 10 secondi, 15 casi
nella giornata). Terzo: il churn intraday è tornato su tre simboli (SBUX venduto e ricomprato dopo
**15 minuti**), costo attribuito 8,12 $. Le metriche di rischio restano non affidabili: il
`daily_pnl` del risk report dice **−1.645,86 $** in una giornata da **+662 $**.

## 2. Verdict finale

> **OK CON WARNING.**

Motivazione: la catena decisione→ordine→fill→posizione è **verificata corretta e riconciliata al
100%** su tutti gli 11 ordini della giornata, e nessun controllo di sicurezza è risultato aggirato.
Il verdetto non sale a "OK" perché (a) due difetti nuovi di **qualità dell'input** (misattribuzione
ticker `org_lookup`, sovrascrittura del segnale forte) possono produrre ordini sul titolo sbagliato
o impedire ordini sul titolo giusto, e (b) l'apparato di **misura** (risk report, decay monitor,
telemetria di ciclo) continua a produrre numeri che contraddicono i dati sottostanti — il che,
durante un periodo di osservazione la cui uscita è decisa da soglie in dollari, è il rischio
principale. Non scende a "anomalie significative" perché nessuno dei difetti ha prodotto, il
2026-08-04, una perdita reale sopra i 10 $ né un ordine non autorizzato.

---

## 3. Timeline del 2026-08-04 (tutti gli orari UTC)

| Ora UTC | Componente | Evento | Esito | Fonte |
|---|---|---|---|---|
| 03:00 | `performance-daily` | batch giornaliero | ok | beat |
| 07:00:12 | `regime.detect_regime` | `ERROR: SPY momentum out of reasonable range: nan%` → **task marcato `succeeded`** | fallimento silenzioso | `worker-inference` log |
| 07:00 → tutto il giorno | regime | `regime_mult = 0.70` costante su tutti i 24 cicli | invariato | `execution_decisions.regime_mult` |
| 13:30 | mercato | **apertura** | — | Alpaca calendar |
| 13:30–14:00 | ingest / cicli | **nessun ingest e nessun ciclo portfolio** (beat `hour="14-21"`) | buco strutturale 30–37 min | `celery_app.py:78,201` |
| 14:00:15 | ingest | prima riga in `news_log` (alpaca_benzinga) | ok | `news_log` |
| 14:00:15–19:46 | sentiment worker | 24 cicli, 204 articoli scorati, 143 ensemble, 61 single-model | ok | `worker-inference` |
| 14:07:00 | portfolio-cycle #766 | **primo ciclo**, 37 min dopo l'apertura | BUY PFE (S4, +0,443) | `portfolio_cycles`, `execution_decisions` 6195 |
| 14:07:11 | broker | PFE buy 48,266 @ 25,11 — **filled** | ok | Alpaca `b2c6ff70` |
| 14:22:00 | portfolio-cycle #767 | SELL META `[expired]` (segnale +0,356 di 19,1h) + SELL SBUX `[s1_weight_drop]` | 2 uscite in perdita | `execution_decisions` 6205/6206 |
| 14:22:10–11 | broker | META sell @ 582,05 (−23,69 $) · SBUX sell @ 102,21 (−25,14 $) · stop PFE creato (qty 48) | filled / filled / new | Alpaca |
| 14:30:01 | `loss_feedback` | trigger S1 (EWMA R −0,88, 2 perdite di fila) → alert Telegram **400 Bad Request** | alert non consegnato | worker log |
| 14:37:00 | portfolio-cycle #768 | **BUY SBUX (S1)** — 15 minuti dopo averlo venduto | churn | `execution_decisions` 6222 |
| 14:37:09 | hold-minimum | `skipped 1 SELL order(s) for recently-bought: ['PFE']` | S4 voleva già uscire da PFE 30 min dopo l'ingresso | worker log |
| 14:52 / 15:07 / 15:22 | hold-minimum | stessa SELL PFE bloccata altre 3 volte | — | worker log |
| 15:52:00 | portfolio-cycle #773 | SELL PFE `[whipsaw]` (score sceso a +0,018, età 1,4h) — 105 min di holding | +16,22 $ realizzati | `execution_decisions` 6306 |
| 17:52:00 | portfolio-cycle #781 | SELL ABBV `[s1_weight_drop]` | −25,37 $ | `execution_decisions` 6450 |
| 18:37:00 | portfolio-cycle #784 | BUY PFE (S4, +0,514) + BUY MCD (S4, +0,471) | 2 ingressi | 6502 / 6503 |
| 18:52:00 | portfolio-cycle #785 | **BUY ABBV (S1)** — 60 min dopo averlo venduto — + BUY NVO (S4, +0,656) | churn + ingresso | 6518 / 6519 |
| 19:00:00 | `loss_feedback` | secondo trigger S1 (3 perdite di fila) → Telegram **400 Bad Request** | alert non consegnato | worker log |
| 19:37:00 | portfolio-cycle #788 | BUY PLTR (S4, +0,383) — segnale generato da un articolo **su Broadcom** | ingresso | 6565 / signal 6480 |
| 19:45:37 → 19:45:47 | sentiment | CAT +0,648 sovrascritto da CAT +0,013 in **10 secondi** | segnale forte perso | `sentiment_signals` 6486/6488 |
| 19:52:00 | portfolio-cycle #789 | ultimo ciclo; `Hold minimum: skipped 1 SELL order(s) for recently-bought: ['ABBV','MCD','NVO','PFE','PLTR']` | telemetria incoerente | worker log |
| 20:00:00 | mercato | **chiusura**; ingest passa a `Market closed — skipping` | ok | worker log |
| 20:07–21:52 | portfolio-cycle | **8 cicli schedulati e scartati** (`Market closed, next open 2026-08-05 09:30-04:00`) | no-op, safe | worker log |
| 21:00:00 | `decay-monitor` | **8 alert DECAY CRITICAL**, IC 0,012 e Sharpe −7,58 identici per S1/S2/S4 | metriche non per-strategia | worker log |
| 22:30:01 | `risk-monitor` | risk_report id=53: NAV 110.314,09, `combined_drawdown` 1,24% vs ALERT "drawdown 13,9%" | incoerenza | `risk_reports` |

Distinzione di fase: **pre-market** (nessuna attività di trading, solo `regime-detector` 07:00),
**market hours** 13:30–20:00 (tutta l'attività, ma effettiva solo 14:00–19:52), **post-market**
(8 cicli no-op), **batch giornalieri** 21:00 decay / 22:30 risk / 22:45 retention.

---

## 4. Tabella news ingest

### 4.1 Per fonte

| Fonte | fetched | queued | duplicates | scartati no_ticker | stale | parse_fail | righe in `news_log` | primo ingest | ultimo ingest |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| alpaca_benzinga | 710 | 363 | **3.398** | 0 | 0 | 0 | 126 | 14:00:15 | 19:46:08 |
| gdelt_gkg | 1.964 | 232 | 49 | 1.745 | 0 | 0 | 78 | 14:45:56 | 19:45:47 |
| **totale** | **2.674** | **595** | **3.447** | **1.745** | 0 | 0 | **204** | | |

Fonte: `ingestion_stats_daily` (day = 2026-08-04) e `news_log`.

### 4.2 Copertura temporale e freschezza

| Metrica | Valore |
|---|---|
| `published_at` più vecchio / più recente | 12:49:38 / 18:09:32 |
| Righe con `published_at` NULL | 0 |
| Righe con `published_at > created_at` (timestamp futuri) | **0** |
| Righe con `content_hash` NULL | 0 |
| Latenza di ingestione (mediana) | **105,8 min** (1h 46m) |
| Latenza di ingestione (max) | 121,4 min (2h 01m) |
| Finestra di entry-freshness (`MAX_NEWS_AGE_HOURS`) | 120 min |
| Quota della finestra consumata dalla mediana | **88 %** |
| Articoli scartati per età prima dello scoring (`news_queue_drops`) | 273 (età media 8,7 h) |
| Buchi temporali nell'ingest | nessuno: ingest ogni 15 min da 14:00 a 19:45, 24 cicli attesi = 24 eseguiti |

### 4.3 Fan-out multi-ticker

| Ticker per URL | # URL | # righe generate |
|---:|---:|---:|
| 1 | 70 | 70 |
| 2 | 17 | 34 |
| 3 | 10 | 30 |
| 4–9 | 7 | 44 |
| 13 | 2 | 26 |
| **totale** | **106** | **204** |

**134 righe su 204 (66 %)** nascono da articoli multi-ticker. Il 08-03 era il 50 %.

### 4.4 Per ticker (top 12) e metodo di estrazione

| Ticker | righe | `source_metadata` | `org_lookup` | Nota |
|---|---:|---:|---:|---|
| CAT | 27 | 6 | 21 | genuine (trimestrale Caterpillar) |
| **MS** | 20 | 0 | **20** | **20 su 20 su società terze — vedi [DAY-001]** |
| MU | 11 | 4 | 7 | genuine |
| AMD | 9 | 6 | 3 | ok |
| **GS** | 8 | 0 | **8** | **8 su 8 su società terze — vedi [DAY-001]** |
| NVDA | 8 | 8 | 0 | fan-out |
| MSFT | 7 | 7 | 0 | fan-out |
| GOOGL | 7 | 7 | 0 | fan-out |
| SPCX | 7 | 7 | 0 | ok |
| META / INTC / PLTR | 6 | 6 | 0 | fan-out |

Totale per metodo: `source_metadata` 126 (Benzinga), `org_lookup` 78 (GDELT).
Di questi 78, **~32 (41 %)** sono attribuiti a ticker bancari su articoli di altre società.

### 4.5 Top news per impatto sul segnale

| Titolo | Ticker | Score | Ha prodotto ordine? |
|---|---|---:|---|
| Caterpillar Cashes In On AI Buildout, Raises 2026 Sales Outlook | CAT | +0,747 | no (posizione già aperta, pyramiding guard) |
| Novo Nordisk raises adjusted sales and operating profit outlook | NVO | +0,656 | **sì — BUY 18:52** |
| BP's Q2 Profit Doubles Amid Middle East Conflict | BP | +0,646 | no (già aperta) |
| Arm Jumps More Than 11%: Data Center Royalty Growth | ARM | +0,626 | no (già aperta) |
| Pfizer's Diversified Drug Portfolio Fuels Growth | PFE | +0,514 | **sì — BUY 18:37** |
| McDonald's Earnings Top Views | MCD | +0,471 | **sì — BUY 18:37** |
| Nike's 'Win Now' Plan May Be a Long Game, JPMorgan Warns | NKE | −0,568 | no (S4 è long-only) |
| **What Is Going on With Broadcom Stock on Tuesday?** | **PLTR** | +0,383 | **sì — BUY 19:37** ⚠ |
| **Energizer (NYSE:ENR) Releases Earnings Results, Misses Expectations** | **MS** | **−0,325** | no ⚠ |

### 4.6 Problemi trovati sull'ingest

1. `duplicates` (3.398) supera di **4,8×** `fetched` (710) per alpaca_benzinga — F-007.
2. GDELT scarta 1.745 articoli su 1.964 per assenza di ticker (89 %): il rapporto segnale/rumore
   della fonte è basso ma la selezione funziona.
3. 273 articoli entrano in coda e vengono scartati per età (media 8,7 h) prima dello scoring.
4. Riconciliazione di coda imperfetta: `queued` 595, ma 204 scorati + 273 stale + 84
   `skipped_not_tradable` = 561 → **34 articoli non tracciati**. Non blocca nulla ma la coda non
   quadra da nessuna parte.
5. **Zero timestamp futuri, zero campi mancanti, zero parse failure, zero retry**: la sanificazione
   e il parsing hanno funzionato.

**Confidenza dell'analisi ingest: Alta** (tutte le grandezze derivano da righe di DB e dai
contatori dello stesso worker che le ha prodotte; l'unico punto debole è il contatore `duplicates`,
non verificabile in modo indipendente — F-007).

---

## 5. Tabella performance modelli LLM

### 5.1 Per modello (`llm_responses`, 2026-08-04)

| Modello | Richieste | Errori/timeout | `eligible=true` | polarity media | conf. media | polarity min/max |
|---|---:|---:|---:|---:|---:|---|
| `gpt-oss:20b-cloud` | 204 | 0 | 48 | +0,115 | 0,418 | −0,70 / +0,83 |
| `glm-5.2:cloud` | 202 | **2** (Ollama timeout) | 48 | +0,137 | 0,322 | −0,75 / +0,90 |
| `finbert` (locale) | 1 | 0 | n/a | — | — | — |

### 5.2 Esito dell'ensemble (`sentiment_signals` + contatori del worker)

| Grandezza | Valore | % |
|---|---:|---:|
| Articoli processati | 204 | 100 % |
| Ensemble a 2 modelli riuscito | 143 | 70,1 % |
| Ricadute a modello singolo (`fallback_used=true`) | **61** | **29,9 %** |
| — di cui `single:gpt-oss:20b-cloud` | 53 | 26,0 % |
| — di cui `single:glm-5.2:cloud` | 7 | 3,4 % |
| — di cui **realmente FinBERT** | **1** | **0,5 %** |
| Segnali con 2 risposte LLM in `llm_responses` | 202 | 99,0 % |
| Cicli sentiment eseguiti | 24 | — |
| Durata mediana / massima di un ciclo | 56,7 s / 154,0 s | — |
| Tempo totale di inferenza | 1.759 s (29 min su 6h) | — |

**Il contatore del worker chiama "finbert_fallbacks" 61 casi di cui solo 1 è FinBERT.** I 61 sono
esclusi dal ranking BUY di S4 dalla regola #108 ("niente BUY su fallback FinBERT"), che quindi
scarta 60 letture prodotte da un vero LLM cloud.

### 5.3 Disaccordo fra modelli

| Metrica | Valore |
|---|---:|
| Coppie confrontabili | 202 |
| Gap medio \|polarity_glm − polarity_gptoss\| | 0,095 |
| Casi con gap > 0,40 | 3 (1,5 %) |
| Casi con **segno opposto** | 6 (3,0 %) |
| `ensemble_std` medio sui segnali | 0,038 |
| `ensemble_std` massimo | 0,283 (NVDA, AMD) |

Il disaccordo è **basso** ed è il valore più sano della giornata: la "divergence drought" che aveva
prodotto il 70-86 % di fallback dopo lo swap GLM-5.2 non si è ripresentata (29,9 % oggi).

### 5.4 Score estremi

Positivi: CAT +0,747 · NVO +0,706 · CAT +0,718/+0,720/+0,693 · BP +0,646 · ARM +0,626.
Negativi: NKE −0,568 · **MS −0,325** (da un articolo su Energizer) · SPCX −0,300 · MCD −0,319.
Distribuzione confidence: modale in 0,2–0,3 (183 risposte su 405), coda alta 0,8–1,0 (43).

### 5.5 Verifiche funzionali richieste

| Domanda | Risposta | Evidenza |
|---|---|---|
| L'output LLM è validato prima di entrare nel signal store? | **Sì, parzialmente.** Schema JSON forzato, polarity ∈ [−1,1], confidence ∈ [0,1]: 0 violazioni su 405 risposte. **Non c'è però validazione di pertinenza**: nessun controllo che il testo parli davvero del ticker. | [DAY-001], [DAY-006] |
| L'ensemble gestisce la varianza alta? | Sì: `ensemble_std` persistito, ricaduta a modello singolo su timeout. Ma la ricaduta **non distingue** timeout da disaccordo, e marca tutto come "fallback FinBERT". | [DAY-005] |
| Le news duplicate pesano più volte? | **In parte sì.** CAT ha ricevuto 27 segnali distinti da 27 righe `news_log` che descrivono in gran parte lo stesso evento (rialzo guidance 2026). Il vincolo `uq_news_log_url_ticker` dedup per URL, non per contenuto. | §4.1, §4.4 |
| La stessa news può generare segnali multipli? | **Sì**, uno per ticker: 134 righe su 204 da articoli multi-ticker. | [DAY-006] |
| Confidence bassa riduce davvero il peso? | **Sì.** `score = polarity × confidence` verificato su tutte le righe. Es. CAT id 6289: polarity ~0, conf 0,2 → score 0. | `sentiment_signals` |
| I modelli sono chiamati offline/background? | **Sì.** Tutte le chiamate LLM avvengono in `worker-inference` (coda `inference`, concurrency 1) su beat ogni 15 min. Il `portfolio-cycle` legge solo da Postgres: 0 chiamate LLM nel loop di trading. | `celery_app.py`, log |
| Rischio che un'allucinazione entri in decisione? | **Sì, dimostrato.** Il BUY PLTR delle 19:37 ha come rationale "Palantir's strong earnings boosted confidence" ma il segnale nasce dall'articolo *"What Is Going on With Broadcom Stock on Tuesday?"*. Nessun supervisore incrocia rationale e fonte. | [DAY-006] |

---

## 6. Tabella segnali finali per ticker

204 segnali su **54 simboli distinti** (dei 96 in watchlist → **42 simboli senza alcuna copertura**).

### 6.1 Segnali che hanno superato il gate 0,30 (i soli candidati a un ordine)

| Ticker | Miglior score | Modello | Ha generato un ordine? | Perché no |
|---|---:|---|---|---|
| CAT | +0,747 | ensemble | no | pyramiding guard (posizione S1 aperta) |
| NVO | +0,706 | ensemble | **sì** (BUY 18:52) | — |
| BP | +0,646 | ensemble | no | posizione già aperta |
| ARM | +0,626 | ensemble | no | posizione già aperta |
| MRVL | +0,593 | ensemble | no | posizione già aperta |
| NKE | −0,568 | ensemble | no | S4 long-only |
| ORCL | +0,565 | ensemble | no | superato dalla soglia al ciclo successivo |
| INTC | +0,550 | ensemble | no | posizione già aperta |
| MU | +0,543 | ensemble | no | posizione già aperta |
| PFE | +0,514 | ensemble | **sì** (BUY 18:37) | — |
| MCD | +0,471 | ensemble | **sì** (BUY 18:37) | — |
| SPCX | +0,450 | **single** | **no** | escluso dal ranking BUY dalla regola #108 |
| NVDA | +0,397 | ensemble | **no** | **sovrascritto da +0,070 15 min dopo** — [DAY-016] |
| PLTR | +0,383 | ensemble | **sì** (BUY 19:37) | — |
| AMD | +0,361 | ensemble | no | posizione già aperta |
| GOOGL | +0,333 | ensemble | no | posizione già aperta |
| SOXX | +0,327 | ensemble | no | posizione già aperta |
| **MS** | **−0,325** | single | no | S4 long-only — **ma il segnale è falso**, [DAY-001] |

### 6.2 Imbuto dei segnali, per ciclo (mediane su 24 cicli)

| Stadio | Valore mediano per ciclo |
|---|---:|
| Segnali nella finestra di lookback | ~50 |
| Scartati da **entry-freshness** (news > 2h) | **29** (range 26–32) |
| Scartati da **staleness** (segnale > 4h) | 17–25 |
| Scartati perché **fallback** (#108) | inclusi sopra |
| Sopravvissuti = "fresh signals" caricati | 22 (range 9–26) |
| Scartati dal **gate 0,30** | 16 (range 5–21) — **~75 %** |
| Arrivati al ranking S4 | **4–6** |
| Ordini generati | 0–2 |

**381 righe `SKIP_THRESHOLD`** scritte nel Decision Log, contro 11 righe BUY/SELL.

---

## 7. Tabella ordini generati / eseguiti

### 7.1 Ordini market (decisione → broker → fill → trade)

Riconciliazione: **11 decisioni = 11 ordini inviati = 11 filled = 11 righe `trades`. Zero reject,
zero cancellazioni, zero ordini orfani, zero duplicati.**

| # | Decisione (UTC) | Strat. | Ticker | Azione | Qty | Prezzo fill | Stato | `decision_id` | `signal_id` | Rationale / meccanismo | Risk check |
|---:|---|---|---|---|---:|---:|---|---:|---|---|---|
| 1 | 14:07:00 | S4 | PFE | BUY | 48,2656 | 25,11 | filled | 6195 | **6288** | sentiment +0,443, peso 2,0 % | gate 0,30 ✓, pyramiding ✓, cap 2 % ✓ |
| 2 | 14:22:00 | S4 | META | SELL | 2,0663 | 582,05 | filled | 6205 | NULL | `[expired]` segnale +0,356 di 19,1h > 4h | hold-min ✓ (19h) |
| 3 | 14:22:00 | S1 | SBUX | SELL | 6,8421 | 102,21 | filled | 6206 | NULL | `[s1_weight_drop]` peso → 0 % | hold-min ✓ |
| 4 | 14:37:00 | S1 | SBUX | **BUY** | 6,8264 | 102,62 | filled | 6222 | NULL | momentum, peso 1,2 % | pyramiding ✓ (posizione chiusa 15 min prima) |
| 5 | 15:52:00 | S4 | PFE | SELL | 48,2656 | 25,46 | filled | 6306 | NULL | `[whipsaw]` score → +0,018 | hold-min ✓ (105 min > 90) |
| 6 | 17:52:00 | S1 | ABBV | SELL | 2,8806 | 242,64 | filled | 6450 | NULL | `[s1_weight_drop]` | hold-min ✓ |
| 7 | 18:37:00 | S4 | PFE | BUY | 45,0083 | 25,44 | filled | 6502 | NULL | sentiment +0,514 | gate ✓, cap ✓ |
| 8 | 18:37:00 | S4 | MCD | BUY | 4,3154 | 265,33 | filled | 6503 | NULL | sentiment +0,471 | gate ✓, cap ✓ |
| 9 | 18:52:00 | S1 | ABBV | **BUY** | 2,7192 | 243,91 | filled | 6518 | NULL | momentum, peso 1,2 % | pyramiding ✓ (chiusa 60 min prima) |
| 10 | 18:52:00 | S4 | NVO | BUY | 25,9518 | 44,00 | filled | 6519 | **6461** | sentiment +0,656 | gate ✓, cap ✓ |
| 11 | 19:37:00 | S4 | PLTR | BUY | 6,9780 | 162,90 | filled | 6565 | **6480** | sentiment +0,383 (**articolo su Broadcom**) | gate ✓, cap ✓ |

Broker: **Alpaca paper** (`ALPACA_PAPER_MODE=True`, account `869964ae-…`, status ACTIVE).
Tutti gli ordini sono `market` / `time_in_force=day`, inviati fra 1,0 e 1,3 s dopo la decisione.

### 7.2 Stop protettivi GTC

| Ora | Ticker | Qty stop | Qty posizione | **Copertura** | Stato |
|---|---|---:|---:|---:|---|
| 14:22:11 | PFE | 48 | 48,2656 | 99,4 % | canceled (posizione chiusa 15:52) |
| 14:52:09 | SBUX | 6 | 6,8264 | **87,9 %** | new |
| 18:52:11 | MCD | 4 | 4,3154 | **92,7 %** | new |
| 18:52:11 | PFE | 45 | 45,0083 | 100,0 % | new |
| 19:07:12 | ABBV | 2 | 2,7192 | **73,6 %** | new |
| 19:07:13 | NVO | 25 | 25,9518 | 96,3 % | new |
| 19:52:10 | PLTR | 6 | 6,9780 | **86,0 %** | new |

Lo stop è sempre creato **un ciclo dopo** l'ingresso: 15 minuti di esposizione senza protezione
broker-side per ogni nuova posizione. Vedi [DAY-015].

### 7.3 Telemetria dei cicli

24 cicli, `orders_count` fra 47 e 52 — ma sono i **pesi target**, non gli ordini inviati (11).
`constraints_fired = []` su tutti i 24 cicli: nessun cap di settore, esposizione o concentrazione è
scattato. Esposizione lorda di fine giornata 33,2 %, Herfindahl 0,0215 (52 posizioni ben
diversificate). Nessun circuit breaker attivo; `system:halted_by_operator` non impostato.

---

## 8. Tabella PnL / rendimento

### 8.1 Realizzato (4 uscite)

| Trade | Ticker | Strat. | Ingresso | Uscita | Qty | gross_pnl | costi | **net_pnl** | Motivo |
|---:|---|---|---|---|---:|---:|---:|---:|---|
| 645 | META | S4 | 08-03 19:22 @ 593,40 | 08-04 14:22 @ 582,05 | 2,0663 | −23,45 | 0,242 | **−23,69** | `[expired]` |
| 595 | SBUX | S1 | 07-31 17:52 @ 105,827 | 08-04 14:22 @ 102,21 | 6,8421 | −24,75 | 0,393 | **−25,14** | `[s1_weight_drop]` |
| 646 | PFE | S4 | 08-04 14:07 @ 25,11 | 08-04 15:52 @ 25,46 | 48,2656 | +16,89 | 0,671 | **+16,22** | `[whipsaw]` |
| 596 | ABBV | S1 | 07-31 18:07 @ 251,31 | 08-04 17:52 @ 242,64 | 2,8806 | −24,98 | 0,392 | **−25,37** | `[s1_weight_drop]` |
| | | | | | | | | **−57,98** | |

Per strategia: **S1 −50,51 $**, **S4 −7,47 $**. Nessuna delle 4 uscite è legacy senza attribuzione.

### 8.2 Non realizzato — posizioni portate dal 08-03 (MTM sul giorno)

| Attribuzione | Posizioni | MTM 08-04 |
|---|---:|---:|
| S1 | 35 | **+692,83 $** |
| S4 | 2 | +57,36 $ |
| **NULL (legacy 07-10)** | **12** | **+40,24 $** |
| **totale** | **49** | **+790,43 $** |

Migliori: WDC +62,16 (S4) · ARM +58,68 · PANW +42,96 · CAT +42,22 · CSCO +39,99 · SOXX +39,49.
Peggiori: **BP −29,51 (NULL)** · PBR −14,06 (NULL) · UNH −12,18 (NULL) · CVX −11,70 · SHEL −11,68.

### 8.3 Non realizzato — posizioni aperte il 08-04 (ingresso → close)

| Ticker | Strat. | Ingresso | Close | Qty | MTM |
|---|---|---:|---:|---:|---:|
| SBUX | S1 | 102,62 | 104,94 | 6,826 | +15,84 |
| MCD | S4 | 265,33 | 268,34 | 4,315 | +12,99 |
| NVO | S4 | 44,00 | 44,24 | 25,952 | +6,23 |
| ABBV | S1 | 243,91 | 243,70 | 2,719 | −0,57 |
| PFE | S4 | 25,44 | 25,40 | 45,008 | −1,80 |
| PLTR | S4 | 162,90 | 162,61 | 6,978 | −2,02 |
| | | | | | **+30,66** |

### 8.4 Ricomposizione e residuo

| Voce | Importo |
|---|---:|
| Realizzato | −57,98 $ |
| MTM posizioni portate | +790,43 $ |
| MTM nuove posizioni | +30,66 $ |
| **Somma calcolata** | **+763,11 $** |
| **Variazione equity broker (109.704,20 → 110.366,23)** | **+662,03 $** |
| **Residuo non spiegato** | **−101,08 $ (−0,09 % del NAV)** |

Il residuo **non è un difetto contabile dimostrato**: il MTM è calcolato su chiusure del feed
**IEX**, mentre il broker marca sul consolidato SIP, non accessibile in sottoscrizione (F-016).
Su 49 posizioni, ~2 $ di scarto medio per posizione spiegano interamente il residuo. È però la
misura di quanto la mancanza del SIP costa in **auditabilità**: la riconciliazione P&L di questo
sistema non può oggi scendere sotto i ~100 $ di errore.

### 8.5 Costi ed esecuzione

| Metrica | Valore |
|---|---:|
| Costi totali (`cost_usd`) sugli 11 ordini | 5,08 $ |
| Costo medio per ordine | 0,46 $ |
| **Slippage misurato** | **non disponibile** |

`trades.slippage_est` è **identico byte per byte a `cost_usd`** su tutte le 11 righe della
giornata: non è una misura di slippage, è una copia del costo modellato. La qualità di esecuzione
del 2026-08-04 **non è misurata**. Query che servirebbe (oggi impossibile senza SIP): confronto
fra `filled_avg_price` e il mid del NBBO al momento del `submitted_at`.

### 8.6 Rendimento della strategia — avvertenza

Il P&L realizzato di S1 (−50,51 $) **non misura** l'edge di S1: la regola d'uscita chiude solo le
posizioni che hanno perso rango momentum, cioè quelle scese (#134). Nella stessa giornata il MTM
di S1 è **+692,83 $**. Coerentemente con la carta di osservazione §"P&L economico", la serie
realizzata di S1 va **esplicitamente ignorata** in favore del P&L economico.

---

## 9. Analisi correttezza buy/sell

| Controllo | Esito | Evidenza |
|---|---|---|
| BUY generati solo quando consentito | ✅ | 7 BUY, tutti con gate 0,30 superato (S4) o peso target > 0 (S1) |
| SELL/exit generati correttamente | ✅ | 4 SELL, ognuna con `exit_mechanism` esplicito (`expired`, `s1_weight_drop` ×2, `whipsaw`) |
| Stop-loss rispettati | ⚠️ | Nessuno stop è scattato. 7 stop GTC creati, ma coprono solo la parte intera: 73,6–100 % del nozionale — [DAY-015] |
| Signal flip rispettato | ✅ | PFE uscita a score +0,018 (sotto soglia), META a segnale scaduto: nessuna uscita contraddittoria |
| Max holding days rispettato | ✅ | posizione più vecchia 07-10, entro i limiti S1 |
| Rebalance band rispettata | ⚠️ | Il deadband esiste sul peso ma **non c'è banda fra gate d'ingresso (0,30) e uscita (0)** — [DAY-002] |
| Niente ordini duplicati | ✅ | 11 ordini, 11 `client_order_id` distinti; `SIGNAL_DUPLICATE_SKIP` ha bloccato 6 ri-invii (NVO ×4, PFE, PLTR) |
| Niente ordini contrari nello stesso intervallo senza rationale | ❌ | SBUX SELL 14:22 → BUY 14:37 (**15 min**, stessa strategia S1). Rationale presente ma incoerente — [DAY-002] |
| Niente ordini su ticker non consentiti | ✅ | tutti gli 11 simboli in `symbols.watchlist` |
| Niente ordini fuori orario | ✅ | primo 14:07, ultimo 19:37, sessione 13:30–20:00. Gli 8 cicli post-chiusura sono stati scartati dal guard `Market closed` |
| Niente trade se dati stale | ✅ | 273 articoli e 17–25 segnali/ciclo scartati per età; `SKIP_STALE` idempotente |
| Niente trade se output LLM non valido | ✅ | 0 risposte fuori schema su 405 |
| Niente trade se circuit breaker attivo | ✅ | nessun breaker attivo; `constraints_fired=[]` su 24 cicli |
| Niente trade se strategia disabilitata | ✅ | solo S1 e S4 hanno girato; S2/S3 zero ordini |
| Paper/live mode coerente | ✅ | `ALPACA_PAPER_MODE=True`, endpoint paper, `execution.engine=portfolio` (solo `portfolio-cycle` invia ordini) |
| Idempotenza su retry Celery | ✅ | 24 task `run_portfolio_cycle` con 24 task-id distinti, 0 retry; `SIGNAL_DUPLICATE_SKIP` protegge il doppio invio |
| Reconciliation ordini ↔ fill ↔ posizioni | ✅ | 11 = 11 = 11; 52 posizioni aperte a fine giornata = 49 portate − 4 chiuse + 7 aperte |
| Pyramiding | ✅ | 47 BUY bloccati dal guard "open trade exists in DB" su ogni ciclo |
| Attribuzione di strategia | ❌ | 12 posizioni su 52 con `stop_strategy` NULL — F-002 |

---

## 10. Anomalie trovate

### [DAY-001] `org_lookup` attribuisce a MS e GS articoli su società completamente estranee

* **Tipo:** Bug
* **Area:** News / Data
* **Evidenza:**
  * tabella: `news_log` (`extraction_method='org_lookup'`, `source='gdelt_gkg'`), `sentiment_signals` id 6440
  * timestamp: 18:15:48 UTC (riga 6440), l'intera giornata per le altre 27
  * query:
    ```sql
    SELECT ticker, left(title,85) FROM news_log
    WHERE created_at >= '2026-08-04' AND created_at < '2026-08-05'
      AND extraction_method = 'org_lookup' AND ticker IN ('MS','GS','DB','AXP');
    ```
* **Descrizione:** tutte e **20** le righe attribuite a **MS** (Morgan Stanley) e tutte e **8**
  quelle attribuite a **GS** (Goldman Sachs) il 2026-08-04 provengono da articoli su società
  terze: *"Energizer (NYSE:ENR) Releases Earnings Results, Misses Expectations By $0.08 EPS"*,
  *"Sysco (NYSE:SYY) Releases Q1 2027 Earnings Guidance"*, *"AON (NYSE:AON) Stock Price Expected
  to Rise, Keefe Bruyette & Woods Analyst Says"*, *"Apollo Global Management Issues Earnings
  Results"*, *"Jeff Bezos Filed To Sell Billions Worth Of Amazon Stock"*. Il meccanismo è
  trasparente: gli aggregatori tipo tickerreport/marketbeat citano la banca come *casa di analisi*
  nel boilerplate, `org_lookup` intercetta l'organizzazione e la risolve nel ticker della banca
  stessa. L'articolo su Energizer ha prodotto per **MS** un sentiment **−0,325**, cioè sopra il
  gate 0,30 in valore assoluto. Su ~78 righe `org_lookup` della giornata, **~32 (41 %)** sono
  attribuzioni false di questo tipo. È esattamente l'errore che `CLAUDE.md` §"Ticker Resolution"
  definisce il peggiore possibile ("un ordine su un titolo non correlato").
* **Impatto:** il 2026-08-04 nessun ordine è nato da queste righe — S4 è long-only e il segnale MS
  era negativo. Ma **MS è una posizione aperta del book** (legacy 07-10), e il percorso di uscita
  per contro-segnale consuma segnali negativi: un −0,325 fabbricato da una trimestrale di
  Energizer è sufficiente, per costruzione, a motivare la chiusura di una posizione reale su
  Morgan Stanley. Nella stessa giornata MS ha chiuso **+2,75 %**.
* **Severità:** High
* **Confidenza:** High (28 righe su 28 verificate una per una)
* **Azione consigliata:** rendere `org_lookup` non-idoneo per le organizzazioni che compaiono in
  ruolo di intermediario/analista, oppure richiedere che l'organizzazione risolta compaia nel
  titolo e non solo nel corpo. Ticket di correttezza: senza questo, ogni giorno di osservazione
  raccoglie ~30 segnali falsi su ticker bancari.
* **Test/monitor consigliato:** test di regressione con i 28 titoli reali del 2026-08-04 come
  fixture, asserendo `NO_TRADE_AMBIGUOUS`; monitor giornaliero sul rapporto
  `righe org_lookup su ticker finanziari / righe org_lookup totali` con alert sopra il 20 %.

### [DAY-002] Churn intraday: SBUX venduto e ricomprato dopo 15 minuti, ABBV dopo 60, PFE comprato-venduto-ricomprato

* **Tipo:** Bug
* **Area:** Orders
* **Evidenza:**
  * tabella: `execution_decisions` id 6206/6222 (SBUX), 6450/6518 (ABBV), 6195/6306/6502 (PFE); `trades` 595/647, 596/650, 646/648
  * timestamp: 14:22:00 → 14:37:00 (SBUX); 17:52:00 → 18:52:00 (ABBV); 14:07 → 15:52 → 18:37 (PFE)
  * snippet: `[s1_weight_drop] S1 target weight dropped to 0% — position closed` alle 14:22, poi
    `S1 momentum: time-series momentum signal, portfolio weight 1.2%` alle 14:37, **stesso simbolo,
    stessa strategia, ciclo successivo**.
* **Descrizione:** S1 ricalcola il ranking momentum a ogni ciclo di 15 minuti e non conserva
  `_last_rebalance` (scelta deliberata, commento in `portfolio_scheduler.py:3268`). Un simbolo che
  oscilla intorno al taglio del ranking viene venduto e ricomprato nel ciclo successivo. Su S4 la
  stessa dinamica passa dal gate: PFE è stato comprato alle 14:07 a score +0,443, e già alle 14:37
  il sistema voleva venderlo (bloccato 4 volte dall'hold-minimum di 90 min), venduto alle 15:52 a
  score +0,018, ricomprato alle 18:37 a score +0,514. Non esiste **nessuna banda** fra la soglia
  d'ingresso (0,30) e quella d'uscita (0).
* **Impatto:** costo diretto misurabile sui tre roundtrip:
  * SBUX: venduto 6,842 sh @102,21, ricomprato 6,826 sh @102,62 → 6,826 × 0,41 = **−2,80 $** di
    prezzo avverso + 0,756 $ di costi = **−3,56 $**
  * ABBV: venduto 2,881 sh @242,64, ricomprato 2,719 sh @243,91 → 2,719 × 1,27 = **−3,45 $** +
    0,736 $ di costi = **−4,19 $**
  * PFE: venduto @25,46, ricomprato @25,44 → +0,90 $ di prezzo favorevole − 1,27 $ di costi = **−0,37 $**
  * **Totale 8,12 $** su una giornata con 11 ordini: il 25 % dei costi di transazione della
    giornata serve a rientrare in posizioni appena chiuse.
* **Severità:** Medium
* **Confidenza:** High (prezzi di fill del broker)
* **Azione consigliata:** **nessuna in questo periodo** — è una taratura (banda di isteresi),
  congelata dalla carta. Registrare la ricorrenza e il costo.
* **Test/monitor consigliato:** monitor giornaliero "roundtrip < 90 min sullo stesso simbolo" con
  il costo in dollari, alimentato direttamente dal ledger.

### [DAY-003] Il risk report dichiara −1.645,86 $ in una giornata da +662 $, e due drawdown che differiscono di 11×

* **Tipo:** Bug
* **Area:** PnL / Risk
* **Evidenza:**
  * tabella: `risk_reports` id=53, 22:30:01 UTC; vista `portfolio_daily_state`; `src/portfolio/risk_monitor.py:174`
  * snippet:
    ```
    combined_drawdown        = 0.012429   (1,24 %)
    per_strategy_metrics.portfolio.drawdown = 0.13867 (13,87 %)
    alerts = ["Strategy portfolio drawdown 13.9% exceeds 10%"]
    per_strategy_metrics.portfolio.daily_pnl = -1645.8627
    ```
* **Descrizione:** ricorrenza esatta dell'incoerenza già registrata il 07-31 e il 08-03, **con la
  causa ora isolata**. La vista `portfolio_daily_state` definisce
  `daily_return = sum(net_pnl) / sum(entry_notional)` **sui soli trade chiusi quel giorno**: il
  2026-08-04 vale −0,014920, cioè il rendimento dei 4 trade usciti, non del portafoglio. Quella
  serie alimenta Sharpe e drawdown del risk report, e
  `daily_pnl = rets[-1] × nav × weight = −0,014920 × 110.314,09 × 1,0 = −1.645,86 $`. La giornata
  reale ha fatto **+662 $** di equity: lo scarto è di **28×** in valore e di **segno opposto**.
  `combined_drawdown` (1,24 %) è invece calcolato sulla curva NAV vera e misura tutt'altra cosa;
  nessuna delle due grandezze è dichiarata autorevole. Il drawdown che genera l'ALERT è congelato a
  0,138668 da **sei giorni consecutivi** (07-30 → 08-04) mentre il NAV si muove: l'alert
  "13,9 % exceeds 10 %" si ripete identico ogni sera e non porta informazione.
* **Impatto:** nessuna perdita diretta. Ma la carta di osservazione decide con soglie in dollari e
  con il P&L economico: avere il metro ufficiale del rischio che sbaglia di 28× e di segno rende
  inservibile ogni lettura di drawdown e Sharpe raccolta nelle prossime settimane, e l'alert
  quotidiano identico ha già consumato la sua credibilità.
* **Severità:** High
* **Confidenza:** High (formula verificata a mano contro le righe della vista)
* **Azione consigliata:** ticket di correttezza. Il rendimento giornaliero di portafoglio deve
  venire dalla curva equity (realizzato + MTM), non dai soli trade chiusi. Passa il test di
  esenzione della carta: se non lo correggo, le metriche di rischio delle prossime 38 giornate sono
  sbagliate.
* **Test/monitor consigliato:** test che asserisce
  `|risk_report.daily_pnl − (equity_t − equity_{t-1})| < 5 % del NAV`; alert se `combined_drawdown`
  e `per_strategy_metrics.portfolio.drawdown` divergono di più di 2×.

### [DAY-004] `decay_monitor`: IC e Sharpe identici per S1, S2 e S4, con S2 disabilitata che genera 4 alert CRITICAL

* **Tipo:** Bug
* **Area:** Ops / Risk
* **Evidenza:**
  * log: `worker`, 2026-08-04 21:00:00,446–457 UTC
  * snippet:
    ```
    DECAY CRITICAL [S1]: IC dropped 67% from 0.035 to 0.012
    DECAY CRITICAL [S2]: IC dropped 72% from 0.042 to 0.012
    DECAY CRITICAL [S4]: IC dropped 59% from 0.028 to 0.012
    DECAY CRITICAL [S1|S2|S4]: Sharpe below 50% of baseline: -7.58 vs 0.95|1.10|0.80
    DECAY CRITICAL [S2]: Max drawdown exceeds baseline by 6.7pp: 12.7% vs 6.0%
    ```
  * codice: `src/workers/decay_monitor_task.py:52-66` (nessun filtro `strategy_id`)
* **Descrizione:** ricorrenza invariata del 07-31 e del 08-03. IC attuale **0,012 identico** e
  Sharpe **−7,58 identico** per tre strategie, confrontati contro tre baseline diverse: le
  grandezze "attuali" sono globali di pipeline (IC da `sentiment_signals`, dominio S4; Sharpe da
  `portfolio_daily_state`, intero book — la stessa serie difettosa di [DAY-003]). **S2 è
  disabilitata, non ha mai una riga in `trades`, e produce 4 degli 8 alert.**
* **Impatto:** 8 alert CRITICAL al giorno privi di contenuto informativo per strategia. Rischio
  diretto sulla domanda di uscita 2 della carta ("S1 ha un edge?") se qualcuno legge `decay_reports`
  credendo che siano metriche S1-specifiche.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** ticket di correttezza (filtro `strategy_id`, esclusione delle strategie
  disabilitate). Stessa motivazione di [DAY-003].
* **Test/monitor consigliato:** test che asserisce che due strategie con trade diversi non possono
  produrre lo stesso Sharpe; assert che una strategia con 0 trade non generi alert.

### [DAY-005] 61 letture etichettate "finbert_fallbacks" di cui 1 sola è FinBERT — e tutte e 61 sono escluse dai BUY

* **Tipo:** Bug
* **Area:** LLM
* **Evidenza:**
  * tabella: `sentiment_signals` (`model_id`, `fallback_used`), `llm_responses` (`eligible`)
  * log: `worker-inference`, contatori dei 24 task `run_sentiment_worker`
  * query:
    ```sql
    SELECT model_id, count(*) FROM sentiment_signals
    WHERE generated_at >= '2026-08-04' AND generated_at < '2026-08-05' GROUP BY 1;
    -- ensemble 143 | single:gpt-oss 53 | single:glm-5.2 7 | finbert 1
    SELECT model_id, count(*) FILTER (WHERE eligible) FROM llm_responses
    WHERE generated_at >= '2026-08-04' AND generated_at < '2026-08-05' GROUP BY 1;
    -- gpt-oss 48/204 | glm-5.2 48/202
    ```
* **Descrizione:** ricorrenza del difetto registrato il 08-03. Tre incoerenze nello stesso punto:
  (a) i contatori del worker sommano `finbert_fallbacks: 61` mentre **una sola** riga ha
  `model_id='finbert'`; le altre 60 sono letture single-model di un LLM cloud vero;
  (b) `llm_responses.eligible` è `true` su 48 righe per modello mentre 143 segnali sono ensemble a
  due modelli — il flag non identifica i contributori reali;
  (c) la regola #108 esclude dal ranking BUY di S4 **tutti** i segnali con `fallback_used=true`,
  cioè il 29,9 % della produzione della giornata, sul presupposto (falso in 60 casi su 61) che si
  tratti del modello locale debole.
* **Impatto:** il caso concreto del 2026-08-04 è **SPCX**: segnale +0,450 alle 19:16 da
  `single:gpt-oss:20b-cloud`, sopra il gate, escluso dal ranking. SPCX ha chiuso a **+10,06 %** ed
  è uno dei 9 mover mancati del giorno. Ingresso ipotetico al ciclo 19:22 (124,30 $) contro
  chiusura 125,95 $ = +1,33 % su una size S4 tipica di 2.200 $ = **+29,23 $** non catturati.
* **Severità:** Medium
* **Confidenza:** Medium (il costo è congetturale: nessun trade è avvenuto)
* **Azione consigliata:** ticket di correttezza — separare `fallback_used` (FinBERT) da
  `single_model` (un LLM ha risposto, l'altro no) e applicare #108 solo al primo. Senza questa
  distinzione, un terzo dei segnali osservati nelle prossime settimane è classificato male.
* **Test/monitor consigliato:** assert che `count(model_id='finbert') == finbert_fallbacks` nei
  contatori del worker; metrica giornaliera separata per `single_model_rate` e `finbert_rate`.

### [DAY-006] Due terzi dei segnali nascono da articoli multi-ticker, e il BUY su PLTR è motivato da un pezzo su Broadcom

* **Tipo:** Rischio
* **Area:** News / LLM
* **Evidenza:**
  * tabella: `news_log` id 6480 (PLTR), 6474/6475/6476 (GOOGL/MSFT/SPCX); `execution_decisions` 6565
  * timestamp: 19:30:21 (segnale 6480), 19:37:00 (BUY PLTR)
  * snippet: titolo `What Is Going on With Broadcom Stock on Tuesday?` →
    ticker `PLTR`, `extraction_method='source_metadata'`, score **+0,383** →
    rationale dell'ordine: *"Palantir's strong earnings boosted confidence, likely improving its
    revenue outlook and positively influencing its share price."*
* **Descrizione:** ricorrenza del 08-03, con quota in crescita: **134 righe scorate su 204 (66 %,
  contro il 50 % del 08-03)** provengono da 36 articoli multi-ticker. Un solo pezzo,
  *"How Anthropic and SpaceX Are Quietly Boosting Big Tech Profits"*, ha generato tre segnali
  distinti (SPCX +0,450, MSFT +0,387, GOOGL +0,333); *"Big Tech's $1.2 Trillion Hyperscaler AI
  Bet"* ne ha generati quattro (NVDA, AMD, SOXX, AMAT). Nel caso PLTR il rationale persistito
  descrive fatti su Palantir che il titolo dell'articolo non contiene: non è verificabile se il
  corpo li menzioni, e **nessun componente incrocia rationale e fonte**.
* **Impatto:** l'unico ordine della giornata sul mover più forte (PLTR, +29,17 %) è stato deciso
  su un articolo intitolato a un'altra società. Ha funzionato, ma per ragioni non ricostruibili:
  è un trade che ha guadagnato denaro pur non essendo funzionalmente giustificato. Costo non
  stimabile.
* **Severità:** Medium
* **Confidenza:** High (attribuzione verificata riga per riga)
* **Azione consigliata:** nessuna azione di taratura in questo periodo. Registrare la ricorrenza; è
  candidato naturale al supervisore anti-allucinazione previsto da `CLAUDE.md`.
* **Test/monitor consigliato:** metrica giornaliera `share_of_scored_rows_from_multiticker`;
  controllo che il ticker compaia nel titolo o nelle prime N parole del corpo.

### [DAY-007] La latenza di ingestione consuma l'88 % della finestra di freschezza: 29 segnali per ciclo nascono già scaduti

* **Tipo:** Bug
* **Area:** News / Data
* **Evidenza:**
  * tabella: `news_log` (`created_at − published_at`), `news_queue_drops`
  * log: `worker`, `S4: dropped N signal(s) below entry-freshness (news_age_hours=2.0)`
  * query:
    ```sql
    SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (created_at-published_at))/60),
           max(EXTRACT(EPOCH FROM (created_at-published_at))/60)
    FROM news_log WHERE created_at >= '2026-08-04' AND created_at < '2026-08-05';
    -- 105.81 min | 121.37 min
    ```
* **Descrizione:** ricorrenza del difetto isolato lo stesso giorno dall'analisi alpha-miss.
  Mediana di ingestione **105,8 minuti** contro una finestra `MAX_NEWS_AGE_HOURS = 2,0 h` (120 min):
  la notizia mediana arriva con l'88 % del suo tempo utile già consumato, e la massima (121,4 min)
  arriva **oltre** la scadenza. Effetto misurato: il gate di entry-freshness scarta **26–32 segnali
  per ciclo** su tutti e 24 i cicli. Inoltre 273 articoli sono scartati in coda con età media 8,7 h.
* **Impatto:** riduce drasticamente la finestra di reazione di S4. Il costo economico della
  giornata è già stato stimato in **2,37 $** nell'analisi alpha-miss del 2026-08-04: qui non lo
  ri-conteggio per non gonfiare la serie.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** nessuna in questo periodo (la finestra di 2h è una taratura). Registrare.
* **Test/monitor consigliato:** monitor sulla mediana giornaliera della latenza di ingestione con
  alert oltre il 75 % della finestra di freschezza.

### [DAY-008] Il fetch del benchmark SPY fallisce 84 volte senza alcun alert, e limita la riconciliabilità del P&L a ±100 $

* **Tipo:** Bug
* **Area:** Data / Ops
* **Evidenza:**
  * log: `worker`, 84 occorrenze il 2026-08-04
  * snippet: `SPY benchmark fetch failed: {"message":"subscription does not permit querying recent SIP data"}`
* **Descrizione:** ricorrenza del 08-03. Il fallimento è **permanente e strutturale** (limite di
  sottoscrizione), si ripete 84 volte in una giornata, ed è loggato a livello WARNING senza mai
  produrre un alert né degradare esplicitamente a IEX.
* **Impatto:** oltre al benchmark mancante, il 2026-08-04 fornisce la **prima misura del costo di
  auditabilità**: la ricomposizione del P&L giornaliero (§8.4) chiude a +763,11 $ contro i
  +662,03 $ della curva equity del broker, con un residuo di **101,08 $** interamente compatibile
  con lo scarto fra chiusure IEX e marcature SIP. Finché il SIP manca, **nessuna riconciliazione
  P&L di questo sistema può scendere sotto ~100 $ di errore** — che è la stessa scala della soglia
  "misurata" della carta (100 $).
* **Severità:** Medium
* **Confidenza:** Medium (il nesso residuo↔feed è argomentato, non dimostrato: dimostrarlo
  richiederebbe proprio i dati SIP mancanti)
* **Azione consigliata:** rendere esplicito e allertato il degrado a IEX. Decidere se la
  sottoscrizione SIP vale il suo costo è una decisione da portare fuori dal periodo di osservazione.
* **Test/monitor consigliato:** alert quando un fetch benchmark fallisce per N cicli consecutivi;
  metrica giornaliera del residuo di riconciliazione P&L.

### [DAY-009] La rilevazione di regime fallisce (`nan%`) ma il task Celery risulta `succeeded`

* **Tipo:** Bug
* **Area:** Ops / Risk
* **Evidenza:**
  * log: `worker-inference`, 2026-08-04 07:00:12,297 UTC
  * snippet:
    ```
    ERROR/ForkPoolWorker-1] SPY momentum out of reasonable range: nan%
    INFO/ForkPoolWorker-1] Task src.workers.regime.detect_regime[...] succeeded in 12.27s: None
    ```
* **Descrizione:** ricorrenza del 08-03. L'unico ERROR della giornata su entrambi i worker, ed è
  seguito immediatamente da `succeeded`. Il `regime_mult` è rimasto a **0,70 su tutti e 24 i cicli**:
  non è possibile distinguere "0,70 è il regime rilevato" da "0,70 è il valore residuo dell'ultimo
  calcolo riuscito".
* **Impatto:** il `regime_mult` moltiplica tutto il sizing. Un fallimento silenzioso su questa
  grandezza rende non interpretabile la size di ogni posizione aperta nel periodo di osservazione.
  Costo non stimabile.
* **Severità:** High (per l'osservabilità; nessun danno diretto misurato)
* **Confidenza:** High
* **Azione consigliata:** ticket di correttezza — il task deve fallire, non riportare `succeeded`,
  e il `regime_mult` deve portare un timestamp di ultimo calcolo riuscito. Passa il test di
  esenzione: senza questo non si sa se il sizing osservato riflette il regime o un valore stantio.
* **Test/monitor consigliato:** assert che `detect_regime` sollevi su `nan`; alert se
  `regime:current` non è aggiornato da > 24 h.

### [DAY-010] Gli alert di loss-feedback non vengono consegnati (Telegram 400 Bad Request)

* **Tipo:** Bug
* **Area:** Ops
* **Evidenza:**
  * log: `worker`, 14:30:01,329 e 19:00:00,232 UTC
  * snippet:
    ```
    Loss feedback triggered for S1: EWMA R -0.88, 2 consecutive losses, rolling P&L $-146.47 — threshold 0.30→0.00
    TelegramNotifier: Failed to send alert: Client error '400 Bad Request' for url 'https://api.telegram.org/bot.../sendMessage'
    ```
* **Descrizione:** ricorrenza del 07-31. Entrambi i trigger di loss-feedback su S1 della giornata
  hanno tentato di notificare l'operatore e hanno fallito con 400. Il fallimento è degradato a
  WARNING e la logica prosegue. Nota di lettura: il testo `threshold 0.30→0.00` è **cosmeticamente
  fuorviante** — `performance.py:1978` forza `new_threshold = 0.0` per S1 con il commento "S1 has no
  discrete entry-threshold gate; persist state only", quindi non si tratta di un allentamento della
  soglia dopo le perdite. Il messaggio però lo suggerisce.
* **Impatto:** due eventi di feedback su perdite consecutive di S1 non sono arrivati all'operatore.
  Nessuna perdita diretta; costo non stimabile.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** correggere il 400 (probabile escaping MarkdownV2 nel messaggio: contiene
  `EWMA R`, `$-146.47`, `→`). Correggere anche il testo del log.
* **Test/monitor consigliato:** test di serializzazione del messaggio con caratteri speciali;
  contatore `telegram_delivery_failures` con alert oltre 0 al giorno.

### [DAY-011] Telemetria del ciclo fuorviante: `orders_count` conta i pesi target e il log hold-minimum elenca i candidati invece degli scartati

* **Tipo:** Bug
* **Area:** Ops
* **Evidenza:**
  * tabella: `portfolio_cycles` (`orders_count` 47–52 su tutti i 24 cicli)
  * log: `worker`, 19:52:10,034 UTC
  * snippet: `Hold minimum (90 min): skipped 1 SELL order(s) for recently-bought: ['ABBV', 'MCD', 'NVO', 'PFE', 'PLTR']`
* **Descrizione:** ricorrenza esatta del 08-03. `orders_count` registra 47–52 su ogni ciclo mentre
  gli ordini realmente inviati nella giornata sono **11**: il campo conta i pesi target del
  portafoglio combinato, non gli ordini. Il log dell'hold-minimum dichiara `skipped 1` e poi elenca
  **5** simboli, che sono i candidati recenti, non gli scartati.
* **Impatto:** chi legge `portfolio_cycles` per ricostruire l'attività della giornata sbaglia di
  un fattore 4-5. Costo non stimabile.
* **Severità:** Low
* **Confidenza:** High
* **Azione consigliata:** ticket di correttezza — separare `target_weights_count` da
  `orders_submitted`; far corrispondere numero e lista nel log.
* **Test/monitor consigliato:** assert `portfolio_cycles.orders_count == len(final_orders)`.

### [DAY-012] `duplicates` supera `fetched` di 4,8× nello stesso giorno per alpaca_benzinga

* **Tipo:** Osservazione
* **Area:** News / Data
* **Evidenza:**
  * tabella: `ingestion_stats_daily`, day = 2026-08-04
  * snippet: `alpaca_benzinga: fetched 710, queued 363, duplicates 3398` · `gdelt_gkg: fetched 1964, queued 232, duplicates 49`
* **Descrizione:** ricorrenza del 07-31. Il contatore dei duplicati vale **4,8 volte** gli articoli
  scaricati nello stesso giorno. La spiegazione più probabile resta additiva cross-run (ogni
  finestra di 15 minuti ri-scarica gli stessi articoli e li riconta), ma non è verificabile in modo
  indipendente perché i duplicati non lasciano riga.
* **Impatto:** nessuno operativo. Rende non interpretabile la metrica di efficienza dell'ingest.
  Costo non stimabile.
* **Severità:** Low
* **Confidenza:** Medium
* **Azione consigliata:** nessuna urgente. Documentare la semantica del contatore.
* **Test/monitor consigliato:** assert `duplicates <= fetched` per finestra, oppure rinominare il
  campo in `duplicate_hits_cumulative`.

### [DAY-013] `execution_decisions.signal_id` NULL su 389 righe su 392

* **Tipo:** Bug
* **Area:** Data
* **Evidenza:**
  * tabella: `execution_decisions`
  * query:
    ```sql
    SELECT count(*) FROM execution_decisions
    WHERE tick_time >= '2026-08-04' AND tick_time < '2026-08-05' AND signal_id IS NULL;  -- 389 / 392
    ```
* **Descrizione:** ricorrenza del 08-03. Solo **3** righe della giornata portano il `signal_id`
  (PFE→6288, NVO→6461, PLTR→6480). Le 381 `SKIP_THRESHOLD` lo hanno NULL per costruzione
  (`_record_gate_drops` passa `signal_id=None`), ma anche 8 delle 11 decisioni BUY/SELL reali lo
  hanno NULL — incluse le due BUY S4 delle 18:37 su PFE e MCD, che un segnale ce l'hanno eccome.
* **Impatto:** la catena segnale → decisione → trade non è ricostruibile per chiave esterna;
  l'attribuzione va fatta a mano incrociando timestamp e testo del `reason`, che è esattamente il
  lavoro che questo report ha dovuto fare. Costo non stimabile, ma pesa su ogni ricostruzione
  futura del periodo di osservazione.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** ticket di correttezza. La provenienza è già pinnata in
  `RankingResult.provenance` (`ranking.py:49-66`): va solo propagata alla scrittura della decisione.
* **Test/monitor consigliato:** assert che ogni decisione BUY di S4 abbia `signal_id` non NULL.

### [DAY-014] La finestra beat è UTC fissa e ignora il DST: 37 minuti persi all'apertura, 8 cicli sprecati dopo la chiusura

* **Tipo:** Bug
* **Area:** Ops
* **Evidenza:**
  * codice: `src/workers/celery_app.py:78` (ingest `hour="14-21"`), `:201` (`portfolio-cycle`
    `minute="7,22,37,52", hour="14-21"`)
  * tabella: `portfolio_cycles` — primo ciclo **14:07:00**, ultimo **19:52:00**
  * log: `worker`, 20:07/20:22/…/21:52 → `Market closed (next open: 2026-08-05 09:30:00-04:00) — skipping portfolio cycle`
* **Descrizione:** le finestre beat sono espresse in UTC fisso `hour="14-21"`, che corrisponde
  alla sessione americana in **EST** (14:30–21:00 UTC). Il 2026-08-04 gli Stati Uniti sono in
  **EDT** e la sessione va da 13:30 a 20:00 UTC. Conseguenze misurate: (a) nessun ciclo portfolio
  e nessun ingest fra l'apertura (13:30) e le 14:00/14:07 — **i primi 37 minuti della sessione non
  esistono per il sistema**; (b) **8 cicli** schedulati fra 20:07 e 21:52 vengono eseguiti e
  scartati dal guard `Market closed`. Il guard funziona: nessun ordine è mai partito fuori orario.
* **Impatto:** il 2026-08-04 la perdita è nulla in pratica — la prima riga di `news_log` è delle
  14:00:15, quindi non c'era nulla da tradare nella finestra scoperta. Ma il buco è **strutturale e
  quotidiano per ~8 mesi l'anno**, e cade proprio nella fase della sessione in cui l'analisi
  alpha-miss dello stesso giorno misura la maggior parte del movimento (55 % in media nel gap di
  apertura). Costo non stimabile su questa giornata.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** ticket di correttezza — ancorare il beat al calendario Alpaca o a
  `America/New_York` invece che a un'ora UTC fissa. Passa il test di esenzione: finché la finestra
  è sfasata, ogni giorno osservato esclude sistematicamente la stessa porzione di sessione, il che
  distorce l'evidenza raccolta e non è una taratura.
* **Test/monitor consigliato:** test che confronta la finestra beat con
  `GetCalendarRequest` per una data in EDT e una in EST; alert se il primo ciclo del giorno parte
  più di 10 minuti dopo l'apertura.

### [DAY-015] Gli stop protettivi coprono dal 74 % al 100 % della posizione, e arrivano 15 minuti dopo l'ingresso

* **Tipo:** Rischio
* **Area:** Risk / Broker
* **Evidenza:**
  * Alpaca `get_orders` 2026-08-04 (7 ordini `stop` / `gtc`); `trades.qty`
  * codice: `src/portfolio/fractional_stop_orders.py:69` → `whole_qty = math.floor(abs(position_qty))`
  * snippet:
    ```
    ABBV  stop qty 2   posizione 2.719199704   →  73,6 % coperto
    PLTR  stop qty 6   posizione 6.977961939   →  86,0 % coperto
    SBUX  stop qty 6   posizione 6.826447086   →  87,9 % coperto
    MCD   stop qty 4   posizione 4.315418535   →  92,7 % coperto
    ```
* **Descrizione:** Alpaca rifiuta gli ordini stop su quantità frazionarie, quindi il modulo protegge
  solo la parte intera. Il docstring dichiara che *"the residual is typically a small % of
  notional"*: il 2026-08-04 il residuo scoperto vale **26,4 % su ABBV**, 14,0 % su PLTR, 12,1 % su
  SBUX. L'assunzione documentata non regge sulle posizioni con poche azioni, cioè proprio quelle sui
  titoli a prezzo alto. In più lo stop viene creato al **ciclo successivo** all'ingresso: PFE
  comprato 14:07 / stop 14:22, MCD 18:37 / 18:52, PLTR 19:37 / 19:52 — 15 minuti di esposizione
  senza protezione broker-side su ogni nuovo ingresso.
* **Impatto:** nessuno stop è scattato il 2026-08-04, quindi nessun costo reale. In un gap avverso
  la perdita eccederebbe il livello di stop per la quota scoperta. Costo non stimabile su questa
  giornata.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** nessuna azione di taratura. Aggiornare il docstring con i numeri reali e
  valutare (fuori dal periodo) un sizing che produca quantità intere sui titoli a prezzo alto.
* **Test/monitor consigliato:** metrica giornaliera `min(stop_coverage)` sul book con alert sotto
  l'80 %; monitor del ritardo fra fill d'ingresso e creazione dello stop.

### [DAY-016] S4 usa solo il segnale più recente per simbolo: un +0,648 viene sovrascritto da un +0,013 dieci secondi dopo

* **Tipo:** Bug
* **Area:** Signal
* **Evidenza:**
  * codice: `src/store/pg_store.py:2305` (`fetch_signals_for_cycle` — "Fetch **one** signal per
    symbol… the most recent ensemble signal is preferred… among same-status signals the most recent
    wins") e `src/strategies/s4/ranking.py:171-174` (`_filter_and_deduplicate`: `if prev is None or
    sig.generated_at > prev.generated_at`)
  * tabella: `sentiment_signals` id 6486/6488; `execution_decisions` 19:52:09
  * snippet:
    ```
    6486  2026-08-04 19:45:37  CAT  +0.6484  ensemble   "Caterpillar raises 2026 sales growth forecast amid AI buildout demand"
    6488  2026-08-04 19:45:47  CAT  +0.0125  ensemble   (articolo generico)
    → execution_decisions 19:52:09  CAT  signal_score 0.012522  "score 0.013 < feedback threshold 0.300"
    ```
* **Descrizione:** la selezione del segnale per S4 è "l'ultimo per simbolo", non il massimo né una
  media pesata. Poiché lo stesso evento genera più articoli e il worker li scora in sequenza a pochi
  secondi di distanza, **un articolo generico che arriva dopo cancella la lettura forte**. Casi
  della giornata (segnale ≥ 0,30 seguito da uno < 0,30 prima del ciclo successivo): **15**, di cui
  quattro con distanza inferiore a 30 secondi — ARM +0,626 → +0,008 in 16 s, CAT +0,648 → +0,013 in
  10 s, GOOGL +0,333 → +0,009 in 21 s. Su CAT il fenomeno si ripete **sei volte** nella stessa
  giornata: il titolo ha chiuso a **+5,54 %** e non ha mai raggiunto il ranking S4.
* **Impatto:** il 2026-08-04 la maggior parte dei simboli colpiti (CAT, ARM, INTC, GOOGL, MU, MRVL,
  AMD) era già in portafoglio e il pyramiding guard avrebbe comunque bloccato l'ordine, quindi il
  costo reale è basso. L'unico simbolo **non detenuto** colpito è **NVDA**: +0,397 alle 16:45:44,
  sovrascritto da +0,070 alle 17:00:46, quindi mai valutato al ciclo 17:07. NVDA da 211,3 $ (17:07)
  a 211,96 $ di chiusura = +0,31 % su size S4 tipica 2.200 $ = **+6,86 $** non catturati.
  Il prezzo della giornata è modesto; il meccanismo no.
* **Severità:** High (il difetto è strutturale: scarta sistematicamente il segnale migliore)
* **Confidenza:** High per il meccanismo (codice + 15 casi verificati), Low per il costo
  (congetturale, un solo simbolo non detenuto colpito in un giorno)
* **Azione consigliata:** ticket di correttezza. La scelta "ultimo vince" non è una soglia da
  tarare, è una regola di selezione che scarta informazione: con essa attiva, l'evidenza su
  "S4 reagisce alle notizie forti?" raccolta nelle prossime 38 giornate misura in realtà "S4 reagisce
  all'ultima notizia arrivata". Passa il test di esenzione della carta.
* **Test/monitor consigliato:** test che, dati due segnali sullo stesso simbolo a 10 s di distanza
  con score 0,65 e 0,01, verifica quale arriva al ranking; monitor giornaliero
  `n_strong_signals_superseded` (oggi: 15).

### [DAY-017] Le posizioni S4 aperte nelle ultime ore di sessione sono condannate all'uscita al mattino: META chiusa per scadenza del segnale, −11,94 $ rispetto al mantenimento

* **Tipo:** Bug
* **Area:** Signal / Orders
* **Evidenza:**
  * tabella: `execution_decisions` id 6205; `trades` id 645
  * timestamp: ingresso 2026-08-03 19:22:00, uscita 2026-08-04 14:22:00
  * snippet:
    ```
    [expired] S4 signal expired (age=19.1h > max_age=4h, generated 2026-08-03 19:15 UTC,
    score=+0.356): weight 0.0% — no counter-signal found, position closed.
    ```
* **Descrizione:** `max_signal_age_hours = 4` è misurato in **tempo di parete**, non in tempo di
  mercato. Un segnale generato alle 19:15 di una sessione ha 45 minuti di vita utile prima della
  chiusura, e al primo ciclo del giorno dopo ha 19,1 ore: la posizione viene chiusa senza che sia
  arrivata alcuna notizia contraria — il testo lo dice esplicitamente, *"no counter-signal found"*.
  Il 2026-08-04 questo ha chiuso META alle 14:22. Lo stesso destino attende, per costruzione, le
  **4 posizioni S4 aperte dopo le 18:30 del 2026-08-04** (PFE, MCD, NVO, PLTR), che al primo ciclo
  del 2026-08-05 avranno tutte segnali di età > 15 ore.
* **Impatto:** META venduta a 582,05, chiusura di giornata 587,83. Controfattuale corto — mantenere
  fino alla chiusura invece di uscire al primo ciclo: 2,0663 × (587,83 − 582,05) = **+11,94 $**, cioè
  la perdita realizzata sarebbe stata −11,75 $ invece di −23,69 $. Costo attribuito della regola sul
  singolo caso: **11,94 $**.
* **Severità:** Medium
* **Confidenza:** Medium (il controfattuale "tenere fino alla chiusura" è corto ma arbitrario nella
  scelta dell'orizzonte)
* **Azione consigliata:** **nessuna azione in questo periodo se si legge `max_signal_age` come
  taratura** — ed è la lettura corretta del valore 4. Ma la scelta di contare le ore notturne è una
  questione di *misura del tempo*, non di soglia: va registrata come tale e riesaminata alla
  scadenza. Registrare la ricorrenza; il pattern si ripeterà il 2026-08-05 su quattro posizioni,
  il che rende la previsione falsificabile.
* **Test/monitor consigliato:** monitor `exit_mechanism='expired'` con la quota di posizioni chiuse
  al primo ciclo del giorno; confronto sistematico fra prezzo di uscita e chiusura di giornata.

---

## 11. False positive e aree risultate corrette

Verifiche eseguite che **non** hanno prodotto anomalie — vale la pena registrarle perché sono i
pattern che il prompt chiedeva esplicitamente di cercare:

| Pattern cercato | Esito | Evidenza |
|---|---|---|
| **Roundtrip < 30 min nello stesso ciclo** | Nessuno *nello stesso ciclo*. SBUX è a 15 min ma su due cicli distinti — riportato in [DAY-002] | `trades` |
| **Pyramiding (BUY > 3 volte senza SELL)** | **Zero.** Il guard ha bloccato 47 BUY per ciclo su simboli con posizione aperta, 24 cicli su 24 | log `P1-1 pyramiding guard` |
| **SELL con sentiment positivo (bug A5)** | **Nessun caso spurio.** META è uscita con score +0,356 ma per *scadenza* del segnale, con motivo esplicito e `exit_mechanism='expired'` — è la regola, non un'inversione di segno | `execution_decisions` 6205 |
| **`fallback_used=True` su tutti i simboli (Ollama giù)** | **No.** Ollama è rimasto disponibile tutto il giorno: 2 soli timeout su 406 chiamate (0,5 %), fallback al 29,9 % per disaccordo/parsing, non per indisponibilità | `llm_responses`, log |
| **NO-ORDER: decisione creata ma ordine non generato** | **Zero.** Tutte e 11 le decisioni BUY/SELL hanno un `order_id` valorizzato e un ordine broker corrispondente | riconciliazione §7.1 |
| **Score < 0,05 che hanno generato ordini** | **Zero.** Gli score S4 dei 5 BUY sono +0,443, +0,514, +0,471, +0,656, +0,383. I due BUY S1 non usano sentiment | `execution_decisions` |
| **Ordini identici nello stesso minuto (race scheduler)** | **Zero.** Le tre coppie nello stesso minuto (18:37 PFE+MCD, 18:52 ABBV+NVO) sono simboli diversi dello stesso ciclo, non duplicati | Alpaca `get_orders` |
| **Ordini fuori orario** | **Zero.** Guard `Market closed` ha scartato 8 cicli post-chiusura | log |
| **Ordini senza risk check** | **Zero.** Tutti passano gate/pyramiding/hold-minimum/cap | §7.1 |
| **Posizioni non riconciliate** | **Zero.** 49 portate − 4 chiuse + 7 aperte = 52 aperte, coerente con `trades` | `trades` |
| **Timestamp futuri nei dati** | **Zero** su 204 righe `news_log` | §4.2 |
| **Ambiguità di timezone** | **Nessuna.** Celery `timezone="UTC"`, tutte le colonne `timestamptz`, tutti i log in UTC | `celery_app.py` |
| **Restart di worker** | **Zero.** `alembic-worker-1`, `worker-inference-1`, `beat-1` up da 5 giorni | `docker ps` |
| **Eccezioni silenziose** | Una sola, [DAY-009]. Nessun `except: pass` ha inghiottito errori nella catena ordini |
| **Output LLM fuori schema** | **Zero** su 405 risposte |

Nota su un'osservazione dell'analisi alpha-miss dello stesso giorno: **NVO comprato alle 18:52 con
sentiment +0,656 mentre il titolo chiudeva a −6,05 %** non è un difetto della catena. Il crollo era
avvenuto nel gap di apertura; dall'ingresso (44,00) alla chiusura (44,24) la posizione ha guadagnato
+6,23 $. Il segnale era corretto rispetto al momento in cui è stato agito.

---

## 12. Dati mancanti o non accessibili

| Dato | Stato | Impatto sull'analisi | Come si otterrebbe |
|---|---|---|---|
| **API REST locale (`localhost:8001`)** | **Non accessibile** — tutti e 5 gli endpoint rispondono `{"detail":"Invalid or expired JWT token"}` col bearer fornito | Nullo: ogni grandezza è stata ricavata da Postgres, dai log e da Alpaca read-only | rigenerare il token; l'endpoint risponde, è l'autenticazione a fallire |
| **Feed SIP** | Non in sottoscrizione (F-016) | Residuo di riconciliazione P&L di **101 $** non eliminabile (§8.4); slippage reale non calcolabile | upgrade della sottoscrizione Alpaca |
| **Slippage di esecuzione** | `trades.slippage_est` è una copia di `cost_usd` | La qualità di esecuzione degli 11 ordini **non è misurata** | confronto `filled_avg_price` vs mid NBBO al `submitted_at` — richiede SIP |
| **Corpo degli articoli** | `body_snippet` troncato | Non ho potuto verificare se l'articolo su Broadcom menzioni davvero Palantir ([DAY-006]) | conservare il corpo completo o l'hash del testo passato al prompt |
| **Attribuzione S1/S4 su 12 posizioni** | `stop_strategy` NULL (F-002) | Il MTM di +40,24 $ di quelle 12 posizioni resta fuori dallo split richiesto dalla domanda di uscita 2 della carta | backfill dell'attribuzione sui trade aperti il 07-10 |
| **Log frontend** | Non esaminati | Nullo: nessuna decisione di trading passa dal frontend | `docker compose logs frontend` |
| **Riconciliazione della coda news** | 34 articoli su 595 `queued` non tracciati in nessun contatore | Basso | strumentare l'uscita della coda con un motivo per ogni elemento |
| **Connettori MCP** | 5 server (AWS Marketplace, Gmail, Google Calendar, Google Drive, WordPress) richiedono OAuth, non autorizzabile in sessione non interattiva | Nullo per questa analisi | autorizzazione dalle impostazioni connettori claude.ai |

---

## 13. Raccomandazioni immediate

Vincolo della carta: siamo al giorno 2 di 40 di sola osservazione, e **ogni taratura è congelata**.
Quello che segue è filtrato con il test di esenzione — *se non lo correggo, l'evidenza che raccolgo
nelle prossime settimane è sbagliata?*

**Passano il test (correttezza/misura, da fare subito):**

1. **[DAY-003]** Il rendimento giornaliero di portafoglio deve venire dalla curva equity, non dai
   soli trade chiusi. Oggi il risk report dice −1.646 $ in una giornata da +662 $. Senza questo, i
   drawdown e gli Sharpe delle prossime 38 giornate non sono leggibili.
2. **[DAY-016]** La selezione "ultimo segnale vince" scarta il segnale migliore. Senza questo, la
   domanda di uscita 1 della carta ("esiste alpha nella news editoriale?") viene risposta misurando
   la reattività all'*ultima* notizia, non alla notizia forte.
3. **[DAY-009]** Il fallimento della rilevazione di regime deve fallire il task. Il `regime_mult`
   moltiplica tutto il sizing: se non si sa quando è stantio, non si sa cosa significano le size
   osservate.
4. **[DAY-001]** `org_lookup` deve smettere di attribuire alle banche gli articoli in cui compaiono
   come casa di analisi. Sono ~30 segnali falsi al giorno su ticker che il book detiene davvero.
5. **[DAY-014]** Ancorare la finestra beat al calendario di mercato invece che a un'ora UTC fissa.
   Ogni giorno osservato esclude sistematicamente gli stessi 37 minuti di sessione.
6. **[DAY-013]** Propagare `signal_id` alle decisioni: la provenienza è già pinnata in
   `RankingResult.provenance`, va solo scritta.

**Non passano il test (registrare, non agire):**
[DAY-002] churn (banda di isteresi = taratura), [DAY-007] latenza vs finestra 2h (soglia),
[DAY-015] copertura degli stop (limite del broker), [DAY-017] `max_signal_age` (soglia — ma la
scelta di contare le ore notturne va riesaminata alla scadenza), [DAY-006] fan-out (richiede un
supervisore, cioè lavoro di design).

**Verifica falsificabile da fare domani (2026-08-05):** le 4 posizioni S4 aperte dopo le 18:30 del
08-04 (PFE, MCD, NVO, PLTR) devono essere chiuse con `exit_mechanism='expired'` al primo ciclo del
giorno. Se non accade, [DAY-017] va rivisto.

---

## 14. Test o monitor da aggiungere

| # | Tipo | Descrizione | Copre |
|---|---|---|---|
| T-1 | test | Due segnali sullo stesso simbolo a 10 s di distanza (0,65 e 0,01): asserire quale arriva al ranking | [DAY-016] |
| T-2 | test | Fixture con i 28 titoli `org_lookup` reali del 08-04 → asserire `NO_TRADE_AMBIGUOUS` su MS/GS | [DAY-001] |
| T-3 | test | `\|risk_report.daily_pnl − (equity_t − equity_{t−1})\| < 5 % NAV` | [DAY-003] |
| T-4 | test | Due strategie con trade diversi non possono avere lo stesso Sharpe; una strategia con 0 trade non genera alert | [DAY-004] |
| T-5 | test | `detect_regime` solleva su `nan` invece di ritornare | [DAY-009] |
| T-6 | test | Serializzazione del messaggio Telegram con `→`, `$-146.47`, `_` | [DAY-010] |
| T-7 | test | `portfolio_cycles.orders_count == len(final_orders)` | [DAY-011] |
| T-8 | test | Finestra beat confrontata con `GetCalendarRequest` su una data EDT e una EST | [DAY-014] |
| T-9 | test | Ogni decisione BUY di S4 ha `signal_id` non NULL | [DAY-013] |
| T-10 | test | `finbert_fallbacks` nei contatori == `count(model_id='finbert')` | [DAY-005] |
| M-1 | monitor | `n_strong_signals_superseded` giornaliero (oggi 15) | [DAY-016] |
| M-2 | monitor | Roundtrip < 90 min sullo stesso simbolo, con costo in $ (oggi 3 / 8,12 $) | [DAY-002] |
| M-3 | monitor | Quota `org_lookup` su ticker finanziari (oggi 41 %), alert > 20 % | [DAY-001] |
| M-4 | monitor | Mediana giornaliera della latenza di ingestione vs finestra di freschezza (oggi 88 %) | [DAY-007] |
| M-5 | monitor | `min(stop_coverage)` sul book (oggi 73,6 %), alert < 80 % | [DAY-015] |
| M-6 | monitor | Residuo di riconciliazione P&L giornaliero (oggi −101 $) | [DAY-008] |
| M-7 | monitor | `telegram_delivery_failures` (oggi 2), alert > 0 | [DAY-010] |
| M-8 | monitor | Quota di righe scorate da articoli multi-ticker (oggi 66 %) | [DAY-006] |
| M-9 | monitor | Ritardo fra fill d'ingresso e creazione dello stop (oggi 15 min su 6 posizioni) | [DAY-015] |
| M-10 | monitor | Quota di posizioni S4 chiuse con `exit_mechanism='expired'` al primo ciclo del giorno | [DAY-017] |

---

## 15. Ticket tecnici suggeriti

Solo difetti di correttezza, come impone la carta. Nessuna patch è stata applicata.

| ID | Titolo | Area | Priorità | Finding |
|---|---|---|---|---|
| T-A | Il rendimento giornaliero di portafoglio deve derivare dalla curva equity, non dai soli trade chiusi (`portfolio_daily_state`) | Risk | **P0** | [DAY-003] |
| T-B | S4: sostituire la selezione "ultimo segnale per simbolo" con una regola che non scarti il segnale più forte della finestra | Signal | **P0** | [DAY-016] |
| T-C | `detect_regime` deve fallire il task Celery quando il momentum è `nan`; `regime:current` deve portare l'istante dell'ultimo calcolo riuscito | Ops | **P0** | [DAY-009] |
| T-D | `org_lookup`: escludere le organizzazioni in ruolo di analista/intermediario dalla risoluzione ticker | News | **P1** | [DAY-001] |
| T-E | Ancorare le finestre beat (`ingest`, `portfolio-cycle`) al calendario di mercato invece che a `hour="14-21"` UTC | Ops | **P1** | [DAY-014] |
| T-F | Propagare `RankingResult.provenance.signal_id` a `execution_decisions` | Data | **P1** | [DAY-013] |
| T-G | Separare `fallback_used` (FinBERT) da `single_model`; applicare la regola #108 solo al primo | LLM | **P1** | [DAY-005] |
| T-H | `decay_monitor`: filtrare per `strategy_id` ed escludere le strategie disabilitate | Ops | **P2** | [DAY-004] |
| T-I | `trades.slippage_est` deve misurare lo slippage o essere rimosso | PnL | **P2** | §8.5, F-015 |
| T-J | Telegram: correggere il 400 sugli alert di loss-feedback; correggere il testo `threshold 0.30→0.00` per S1 | Ops | **P2** | [DAY-010] |
| T-K | `portfolio_cycles`: separare `target_weights_count` da `orders_submitted`; allineare numero e lista nel log hold-minimum | Ops | **P3** | [DAY-011] |
| T-L | Il degrado del benchmark SPY a IEX deve essere esplicito e allertato, non 84 WARNING al giorno | Data | **P3** | [DAY-008] |

---

## 16. Stato sistema

| Componente | Stato 2026-08-04 |
|---|---|
| **Ollama Cloud** | **UP tutto il giorno.** 2 timeout su `glm-5.2:cloud` su 406 chiamate (0,5 %). **Downtime: 0 ore.** |
| **Coppia di modelli attiva** | `glm-5.2:cloud` + `gpt-oss:20b-cloud` (coerente con la coppia live attesa) |
| **Ensemble a 2 modelli** | 143 / 204 = **70,1 %** |
| **Ricadute a modello singolo** | 61 / 204 = **29,9 %** |
| **FinBERT fallback reale** | **1 / 204 = 0,5 %** (il contatore del worker ne dichiara 61 — [DAY-005]) |
| **Fallback rate sulle decisioni** | **0 / 11 = 0 %** — nessuno degli 11 ordini nasce da un segnale fallback (la regola #108 li esclude) |
| **Latenza inferenza** | ciclo mediano 56,7 s, massimo 154,0 s, totale 29 min su 6 h di sessione |
| **Worker restart events** | **0.** `alembic-worker-1`, `alembic-worker-inference-1`, `alembic-beat-1`, `alembic-api-1` up da 5 giorni; `postgres` e `redis` da 2 settimane |
| **ERROR nei log** | **1** in totale (worker-inference, [DAY-009]); **0** nel worker |
| **Cicli portfolio** | 24 / 24 eseguiti, 0 falliti, durata 8,7–40,1 s |
| **Cicli ingest** | 24 / 24; cicli post-chiusura correttamente scartati |
| **Cicli sentiment** | 24 / 24 |
| **Broker** | Alpaca **paper**, account `869964ae-13de-41ce-8f8e-a28d000f45e0`, status ACTIVE, equity di chiusura **110.366,23 $**, cash 73.661,18 $ |
| **Circuit breaker / halt operatore** | non attivi |
| **Rumore nei log** | **17.279** richieste `getUpdates` a Telegram in `worker-inference` (uno ogni ~5 s), ciascuna con il **bot token in chiaro** nell'URL. Occupano l'unico ForkPoolWorker di un container a concurrency 1 dedicato all'inferenza. Ricorrenza di F-018. |

---

*Report generato in modalità read-only. Nessun file modificato oltre a questo e a
`docs/evidence/findings.json`. Nessuna patch applicata, nessun ordine inviato, nessun worker
avviato.*
