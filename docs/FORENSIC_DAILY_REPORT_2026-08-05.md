# Forensic Daily Report — 2026-08-05

**Giornata di borsa:** mercoledì 2026-08-05 (EDT, sessione 13:30–20:00 UTC)
**Report generato:** 2026-08-06
**Modalità:** read-only. Nessun ordine inviato, nessun worker avviato, nessuna patch applicata.
**Periodo di osservazione:** giorno 3 di 40 (`docs/evidence/OBSERVATION_CHARTER.md`, inizio 2026-08-03).
Nessuna proposta di taratura in questo report: solo difetti di correttezza e registrazione di evidenza.

---

## 1. Executive summary

La catena end-to-end ha funzionato: 194 articoli ingeriti da 2 fonti, 195 segnali scorati, 488
decisioni persistite, 19 ordini inviati, 19 riempiti, 0 rifiutati, riconciliazione ordini→fill→
posizioni completa. Il P&L realizzato è **+65,51 $** su 11 uscite, il MTM del libro **−197,12 $**,
l'equity chiude a **110.239,74 $** (−126,49 $ sul giorno); la ricomposizione lascia un residuo di
**5,12 $** (0,005 % del NAV), il migliore delle quattro giornate osservate finora.

Quattro anomalie nuove, tutte di correttezza e non di taratura. (a) La **suite di test scrive nel
database di produzione**: le righe `ingestion_stats_daily` con `source='reuters'` — 13 giornate dal
21/07, inclusa una del 2026-08-06 — sono artefatti di `tests/workers/test_rss_ingestion.py`, che
non mocka `PostgreSQLStore`. (b) Alle **19:30 un guasto DNS** è stato tradotto in «mercato chiuso»:
i due connettori di ingest e il sentiment worker hanno saltato un ciclo intero a mercato aperto,
riportando `succeeded`, senza alcun alert. (c) I segnali su Berkshire sono scritti come **`BRKB`**
mentre il simbolo tradabile è **`BRK.B`**: 81 righe storiche di `sentiment_signals` non possono
generare né chiudere alcuna posizione. (d) Alle 20:00 il loop di loss-feedback ha alzato la
**soglia d'ingresso S4 da 0,30 a 0,35** e scalato il sizing a 0,80 con TTL 3,4 giorni: il parametro
che la carta di osservazione considera congelato si muove da solo e nulla ne registra lo stato.

Confermata la **previsione falsificabile** registrata il 08-04 su F-024: le quattro posizioni S4
aperte dopo le 18:30 (PFE, MCD, NVO, PLTR) sono state chiuse `expired` al primo ciclo del giorno.
Oggi il meccanismo ha però fatto guadagnare 21,28 $ e ha inoltre liquidato una posizione **legacy
del 10/07 su BP** che nessuna strategia rivendica.

## 2. Verdict finale

> **OK CON WARNING — con una riserva sulla purezza dei dati.**

La catena decisionale è funzionalmente corretta: nessun ordine senza segnale, nessun segnale sotto
soglia che abbia generato un ordine, nessun ordine duplicato, nessun ordine fuori orario, hold
minimum e guard anti-pyramiding rispettati, idempotenza dimostrata (`SIGNAL_DUPLICATE_SKIP` su
PLTR, 4 volte). Il warning non è sul trading ma sull'**evidenza**: tre dei quattro difetti nuovi
(test che scrivono in produzione, ingest saltato e mascherato da «mercato chiuso», soglia S4 che
si muove da sola) rendono i dati raccolti in questa finestra meno affidabili di quanto sembrino,
ed è esattamente la classe di difetti che la carta di osservazione esenta dal congelamento.

---

## 3. Timeline del 2026-08-05

Tutti gli orari in **UTC**. Timezone confermato dal codice: `src/workers/celery_app.py` usa
`crontab(hour="14-21")` per l'intera pipeline e i timestamp Postgres sono `timestamptz` in UTC.
**Ambiguità nota e ricorrente:** gli USA sono in EDT, la sessione è 13:30–20:00 UTC, ma le finestre
beat sono cablate su 14:00–21:00 UTC (EST) — vedi [DAY-012].

| Ora UTC | Fase | Componente | Evento | Esito |
|---|---|---|---|---|
| 07:00:00 | pre-market | `regime.detect_regime` | rilevazione regime primaria | **OK** — `bull ×1.0`, disagreement=False, 40,6 s |
| 13:30:00 | pre-market | `regime.detect_regime` | safety-net P0-09 | **OK** — `bull ×1.0`, 56,8 s. `regime_mult=1.0` su tutte le 488 decisioni |
| 13:30 | apertura | NYSE | apertura di sessione | **nessun componente attivo** — primo ciclo alle 14:07 (37 min di scoperto, [DAY-012]) |
| 14:00:00 | ingest | `run_news_ingestion_worker` / `run_alpaca_ingestion_worker` | primo ciclo di ingest | OK |
| 14:00:00 | LLM | `run_sentiment_worker` | primo ciclo | `no_items_in_queue`, **134 item scartati per staleness** |
| 14:00:00 | coda | `news_queue_drops` | inizio scarti in coda | 264 scarti nella giornata, età media 11,43 h |
| 14:07:00 | portfolio | `run_portfolio_cycle` | ciclo 1/24 | 49 posizioni caricate, 0 ordini |
| 14:07:13 | risk | `fractional_stop_sync` | sync stop protettivi | created 0, replaced 1, noop 38, **skipped 13** ([DAY-014]) |
| 14:15:09 | LLM | sentiment | segnale **DIS +0,5722** conf 0,775 (ensemble) da *«Dow Jumps 500 Points; Disney Earnings Beat Views»* | il segnale più azionabile del giorno |
| 14:22:09 | decisione | portfolio cycle | **6 SELL + 2 BUY** | 4 SELL `expired` (MCD, NVO, PFE, PLTR), 1 `s1_weight_drop` (SBUX), 2 BUY (SNOW S1, **DIS S4** score 0,687) |
| 14:22:10-12 | esecuzione | Alpaca paper | 5 stop protettivi cancellati prima delle SELL, poi 2 nuovi creati | OK, sequenza corretta |
| 14:27:01 | riconciliazione | `reconcile_fills_intraday` | 7 fill aggiornati | OK |
| 14:30:37 | LLM | ensemble | **divergenza reale → FinBERT** su SPCX | 1 dei soli 2 fallback FinBERT veri della giornata |
| 14:52:07 | decisione | portfolio cycle | BUY SBUX (S1, peso 1,1 %) | riacquisto 30 min dopo la SELL delle 14:22 |
| 15:07/15:22/15:37 | guard | hold-minimum 90 min | 2, 2, 1 SELL bloccate | guard corretto; **log dichiara 2 ed elenca 3 simboli** ([DAY-010]) |
| 15:30:14 | LLM | sentiment | segnale **PLTR +0,7269** conf 0,875 (ensemble) | secondo score più alto del giorno |
| 15:37:07 | decisione | portfolio cycle | **BUY PLTR** (S4, peso 2,0 %) | trade 656, 10,369 az. a 159,87 |
| 15:52:07 | decisione | portfolio cycle | **SELL BP** `[expired]` — segnale S4 del 08-04 17:15, età 22,6 h | chiude il **trade 285, aperto il 10/07**, +48,19 $ ([DAY-005], [DAY-006]) |
| 15:52-16:37 | guard | `SIGNAL_DUPLICATE_SKIP` | segnale 6524 (PLTR) già usato — 4 skip consecutivi | **idempotenza corretta** |
| 16:07:11 | decisione | portfolio cycle | BUY BP (S1), **SELL DIS** `[whipsaw]`, SELL SNOW `[s1_weight_drop]` | DIS uscita a 99,79 dopo 1,75 h (già registrata su F-008 dal report alpha-miss) |
| 16:15:38 | LLM | sentiment | ciclo con `ensemble_success: 0`, 6 «finbert_fallbacks» | in realtà 6 `single:<model>`, **zero FinBERT** ([DAY-007]) |
| 17:26:05 | ops | telegram poller | `Connection reset by peer` | transitorio, nessun impatto |
| 17:45:31 | LLM | sentiment | segnale **LLY +0,747** conf 0,900 — **massimo della giornata** | LLY è il mover #1 (+4,86 %); già in book S1, BUY bloccata da P0-05 (F-023) |
| 17:52:10 | decisione | portfolio cycle | SELL BP `[s1_weight_drop]` a 41,63 | trade 657 chiuso, −5,00 $ |
| **17:56–18:01** | **ops** | **rete/Alpaca** | **risposte HTTP `<html>` + `Connection refused`** | Mobile snapshot ko ×4, order reconciliation ko, **riconciliazione dell'exit del trade 657 fallita** — recuperata alle 18:12 |
| 18:07:09 | decisione | portfolio cycle | BUY BP (S1) — **secondo riacquisto BP della giornata** | trade 658 |
| 18:15:36 | LLM | sentiment | segnale **BRKB +0,49** conf 0,700 | **mai entrato nel ranking S4**: il simbolo tradabile è `BRK.B` ([DAY-003]) |
| 18:52:08 | decisione | portfolio cycle | BUY **BRK.B** (S1, peso 1,2 %) | per S1, non per il segnale news |
| 19:07:10 | decisione | portfolio cycle | BUY SNOW (S1) — **secondo riacquisto SNOW** | trade 660 |
| **19:30:04** | **ingest+LLM** | **DNS** | **`NameResolutionError` su paper-api.alpaca.markets → fail-closed** | **ingest Alpaca, ingest GDELT e sentiment worker saltano il ciclo con `reason: market_closed` a mercato aperto; tutti e tre `succeeded`** ([DAY-002]) |
| 19:45:01 | ingest | recupero | Alpaca fetched 25 / dupl 150; GDELT fetched 74 / queued 7 | ciclo recuperato con 15 min di ritardo |
| 19:46:21 | LLM | sentiment | 12 processati, **29 scartati per staleness** | conseguenza del buco delle 19:30 |
| 19:52:08 | decisione | portfolio cycle | ciclo 24/24 — SELL BP `[s1_weight_drop]`, SELL PLTR `[expired]` (età 4,4 h) | ultimo ciclo utile |
| 20:00:00 | chiusura | NYSE | chiusura di sessione | — |
| **20:00:00** | **feedback** | `loss_feedback` | **trigger S4: EWMA R −0,05, 3 perdite di fila → soglia 0,30→0,35, regime scale 1,00→0,80** | **la soglia S4 non è più quella di ieri** ([DAY-004]) |
| 20:00–21:45 | beat | ingest/sentiment/portfolio | **8 cicli eseguiti a mercato chiuso e scartati dal guard** | nessun ordine; spreco strutturale ([DAY-012]) |
| 21:00:00 | monitor | `decay_monitor` | **7 alert DECAY CRITICAL** su S1/S2/S4 con metriche identiche | S2 disabilitata genera 3 dei 7 ([DAY-009]) |
| 22:00:00 | monitor | `forward_return_worker` | 1095 segnali, updated 976, skipped 119, errors 0 | OK |
| **22:06:30** | **contaminazione** | **suite di test** | **`ingestion_stats_daily` source=`reuters`: fetched 4, queued 4** | **scrittura di test nel DB di produzione** ([DAY-001]) |
| 22:30:01 | monitor | `risk_monitor` | ALERT «portfolio drawdown 13,9 % exceeds 10 %», ma `combined_drawdown=0,0124` nello stesso record | incoerenza ricorrente ([DAY-008]) |

Eventi assenti e verificati come tali: nessun restart di container (tutti e 7 su da 07-22/07-30,
`RestartCount=0`), nessun circuit breaker, nessun halt operatore, nessuno stop-loss scattato
(`stop_decisions` vuota), nessun ordine rifiutato o cancellato.

---

## 4. Tabella news ingest

### 4.1 Per fonte

| fonte | fetched | queued | duplicates | scartati no-ticker | righe in `news_log` | primo | ultimo | latenza mediana | latenza max |
|---|---:|---:|---:|---:|---:|---|---|---:|---:|
| `alpaca_benzinga` | 548 | 309 | 2 362 | 0 | **77** | 14:15:09 | 19:15:47 | 100,2 min | 120,1 min |
| `gdelt_gkg` | 1 848 | 175 | 83 | 1 661 | **117** | 15:15:09 | 19:46:21 | 90,8 min | 106,4 min |
| `reuters` | 4 | 4 | 0 | 1 | **0** | — | — | — | — |
| **totale reale** | **2 396** | **484** | **2 445** | **1 661** | **194** | 14:15:09 | 19:46:21 | — | — |

La riga `reuters` **non è un ingest**: l'RSS è disabilitato nel beat schedule dal 2026-07-03 e non
compare mai nei log dei container. È un artefatto della suite di test — vedi [DAY-001]. Va esclusa
da ogni conteggio.

`duplicates` (2 362) supera `fetched` (548) di 4,3× su Benzinga: ricorrenza di F-007, contatore
UPSERT additivo cross-run, non verificabile indipendentemente perché i duplicati non lasciano riga.

### 4.2 Qualità delle righe persistite

| controllo | esito |
|---|---|
| righe totali | 194 |
| URL distinti | 124 |
| `content_hash` distinti | 122 — 0 righe con hash nullo |
| timestamp futuri (`published_at > created_at`) | **0** |
| campi obbligatori vuoti (title/url) | **0** |
| righe con `discarded_reason` | 0 |
| `extraction_method` | `org_lookup` 117 (100 % GDELT), `source_metadata` 77 (100 % Benzinga) |
| articoli scartati in coda (`news_queue_drops`) | **264**, età media 11,43 h |
| news scartate per staleness dal sentiment worker | 134 (14:00) + 75 + 17 + 8 + 1 + **29** (19:46) |

Il rapporto 194 righe / 124 URL distinti misura il fan-out multi-ticker: **32 articoli su 124 (26 %)
sono taggati a 2+ ticker e generano 102 delle 194 righe (53 %)** — ricorrenza di F-012, già
registrata oggi dal report alpha-miss, non riconteggiata qui.

**Nessuna sanitizzazione anomala rilevata**: nessun homoglifo o carattere di controllo nei titoli
persistiti; i ticker sono ASCII-safe con l'unica eccezione strutturale di `BRKB` ([DAY-003]).

### 4.3 Per ticker (top 15 di 46 coperti su 96 in watchlist)

| ticker | articoli | segnali | score max | score min |
|---|---:|---:|---:|---:|
| MS | 33 | 33 | +0,150 | −0,118 |
| LLY | 17 | 18 | **+0,747** | −0,035 |
| DIS | 14 | 14 | **+0,572** | −0,120 |
| GS | 13 | 13 | +0,100 | −0,120 |
| AMD | 11 | 11 | +0,256 | −0,270 |
| MU | 10 | 10 | +0,343 | −0,012 |
| CAT | 7 | 7 | +0,280 | −0,113 |
| AAPL | 7 | 7 | +0,104 | −0,003 |
| NVDA | 6 | 6 | +0,154 | −0,160 |
| AMZN / DB / MSFT | 5 / 5 / 5 | idem | +0,040 / 0,000 / +0,080 | −0,120 / −0,180 / −0,100 |
| BRKB | 4 | 4 | **+0,490** | −0,150 |
| SPCX | 4 | 4 | +0,108 | −0,171 |

MS è **il ticker più coperto della giornata con 33 articoli, nessuno dei quali parla di Morgan
Stanley** (org_lookup sul boilerplate delle case di analisi): ricorrenza di F-020, già registrata
oggi dal report alpha-miss. Con GS e DB fanno 51 righe su 194 (26 %) di copertura fittizia: la
copertura reale della watchlist è **43/96 ticker, non 46**.

### 4.4 Top news per impatto sul segnale

| pubblicata | ora segnale | ticker | titolo | score | effetto |
|---|---|---|---|---:|---|
| ~15:45 | 17:45:31 | LLY | *Eli Lilly's Weight-Loss Empire Keeps Expanding As Mounjaro, Zepbound Generate Nearly $15 Billion* | **+0,747** | nessun ordine (P0-05: già in book S1) |
| ~13:45 | 15:30:14 | PLTR | (earnings, +93 % revenue growth) | **+0,727** | **BUY 15:37**, trade 656 |
| ~12:35 | 14:15:09 | DIS | *Dow Jumps 500 Points; Disney Earnings Beat Views* | **+0,572** (→ 0,687 dopo boost velocity ×1,2) | **BUY 14:22**, trade 654 |
| ~16:35 | 18:15:36 | BRKB | — | +0,490 | **nessun effetto possibile**: simbolo non tradabile ([DAY-003]) |
| ~14:20 | 16:01:13 | NVO | — | +0,488 | scartato da #108 (`single:gpt-oss`) |

### 4.5 Problemi trovati nell'ingest

1. Riga `reuters` fantasma da test in produzione — [DAY-001], **nuovo**.
2. Buco di un ciclo alle 19:30 mascherato da «mercato chiuso» — [DAY-002], **nuovo**.
3. Latenza mediana 90–100 min contro finestra di freschezza di 120 min — ricorrenza F-019, già
   registrata oggi dal report alpha-miss.
4. `duplicates` > `fetched` su Benzinga — ricorrenza F-007 (non ri-registrata: nessun elemento
   nuovo rispetto al 08-04).
5. 1 661 articoli GDELT scartati per assenza di ticker (90 % del fetched): tasso normale per GKG.

**Confidenza dell'analisi ingest: alta.** Tutte le grandezze vengono da `news_log` e
`ingestion_stats_daily` riga per riga, con l'eccezione dichiarata del contatore `duplicates`.

---

## 5. Tabella performance modelli LLM

Coppia attiva: `glm-5.2:cloud` + `gpt-oss:20b-cloud` (Ollama Cloud), come da registro.
**`llm_responses` non ha colonna di latenza**: la latenza per-modello non è misurabile, solo la
durata dei cicli.

| modello | richieste | successi | errori | timeout | refusal / output invalido | polarity media | polarity range | confidence media | `eligible=true` |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|
| `glm-5.2:cloud` | 195 | 195 | **0** | **0** | **0** | +0,052 | −0,60 … +0,85 | 0,251 | **28 / 195 (14,4 %)** |
| `gpt-oss:20b-cloud` | 195 | 195 | **0** | **0** | **0** | +0,043 | −0,60 … +0,80 | 0,383 | **28 / 195 (14,4 %)** |
| FinBERT (fallback) | 2 | 2 | 0 | 0 | 0 | — | — | 0,285 | n/d |

**Ollama up per l'intera sessione: 0 minuti di downtime, 0 errori, 0 timeout.**
Durata dei cicli sentiment: da 17,9 s (3 item) a 99,3 s (12 item), mediana ~66 s. Nessun ciclo ha
sfiorato il `task_soft_time_limit` di 780 s.

### 5.1 Concordanza fra modelli

| metrica | valore |
|---|---:|
| segnali con entrambi i modelli interrogati | 195 / 195 (100 %) |
| disaccordo di **segno** (polarity di segno opposto, entrambe non nulle) | **5 / 195 (2,6 %)** |
| scarto assoluto medio \|glm − gpt\| | **0,097** |
| scarti > 0,50 | 5 |
| divergenze che hanno realmente attivato FinBERT | **2** (SPCX 14:30:37, LLY 17:15:23) |

I due modelli sono **molto concordi**: il collo di bottiglia di S4 non è la varianza d'ensemble ma
la magnitudine (F-009) e la calibrazione della confidence.

### 5.2 Distribuzione dell'output di ensemble — e il difetto che la governa

| `model_id` scritto | n | quota | confidence media | score medio |
|---|---:|---:|---:|---:|
| `ensemble:glm-5.2:cloud+gpt-oss:20b-cloud` | 132 | 67,7 % | 0,286 | +0,046 |
| `single:gpt-oss:20b-cloud` (`fallback_used=true`) | 54 | 27,7 % | 0,529 | +0,026 |
| `single:glm-5.2:cloud` (`fallback_used=true`) | 7 | 3,6 % | 0,693 | +0,006 |
| `finbert` | **2** | **1,0 %** | 0,285 | +0,085 |

La decomposizione per regime di eleggibilità torna **esattamente**:

| regime (floor confidence 0,4) | conteggio | esito |
|---|---:|---|
| entrambi ≥ 0,4 | 30 | 28 ensemble + **2 FinBERT** (divergenza) |
| **nessuno** ≥ 0,4 | **104** | retry a floor 0 (#90) → **ensemble a 2 modelli** |
| **esattamente uno** ≥ 0,4 | **61** | **`single:<model>`, l'opinione dell'altro modello buttata** |

30 + 104 + 61 = 195 ✓; 28 + 104 = 132 ensemble ✓; 54 + 7 = 61 single ✓.
Questa è la prova aritmetica pulita di **F-010** — vedi [DAY-007].

### 5.3 Verifica funzionale della catena LLM

| domanda | risposta | evidenza |
|---|---|---|
| L'output LLM è validato prima di entrare nel signal store? | **Sì, parzialmente** — parsing JSON strutturato, clamp di polarity/confidence, floor di confidenza. Ma la validazione **non blocca** un output plausibile e sbagliato | 0 righe con polarity fuori [−1,+1] |
| L'ensemble gestisce la varianza alta? | **Sì** — divergenza → FinBERT, 2 casi su 195 | log `Ensemble diverged for …` |
| Le news duplicate pesano più volte? | **No sul duplicato esatto** (vincolo `uq_news_log_url_ticker` + content_hash). **Sì sul quasi-duplicato**: 124 URL → 194 righe per fan-out multi-ticker | §4.2 |
| La stessa news può generare segnali multipli? | **Sì, per ticker diversi**, per design. Sullo *stesso* ticker no | — |
| La confidence bassa riduce davvero il peso? | **Sì**: `score = polarity × confidence` verificato su tutte le 195 righe | `src/workers/sentiment.py` |
| I modelli sono chiamati offline/background? | **Sì** — `worker-inference`, coda `inference`, concurrency 1, mai nel loop di esecuzione | `celery_app.py:74-79` |
| Un'allucinazione LLM può entrare direttamente in una decisione di trading? | **Sì, in linea di principio.** Nessun supervisor cross-esamina il testo del `rationale` contro l'articolo sorgente. Il caso PLTR del 08-04 (rationale su Palantir da un articolo su Broadcom) resta il precedente | F-012 |

---

## 6. Tabella segnali finali per ticker

488 decisioni persistite: 467 `SKIP_THRESHOLD`, 11 SELL, 8 BUY, 2 `SKIP_STALE`.
Distribuzione degli score scartati dal gate:

| intervallo `signal_score` | righe `SKIP_THRESHOLD` |
|---|---:|
| −0,270 … −0,216 | 19 |
| −0,171 … −0,144 | 16 |
| −0,065 … −0,003 | 12 |
| **0,000 … +0,073** | **345 (74 %)** |
| +0,100 … +0,156 | 40 |
| +0,202 … +0,238 | 35 |

**Massimo assoluto scartato dal gate: +0,238 (QQQ).** Nessuna decisione scartata era ≥ 0,30:
il gate 0,300 ha agito esattamente come specificato.

Segnali che hanno superato il gate 0,300 (candidati reali della giornata):

| ora | ticker | score | conf | `ensemble_std` | model | esito |
|---|---|---:|---:|---:|---|---|
| 17:45:31 | LLY | **+0,747** | 0,900 | 0,035 | ensemble | **nessun ordine** — P0-05 no-pyramiding (già in book S1) |
| 15:30:14 | PLTR | **+0,727** | 0,875 | 0,035 | ensemble | **BUY 15:37** ✓ |
| 16:00:47 | LLY | +0,666 | 0,800 | 0,035 | ensemble | P0-05 |
| 18:15:21 | LLY | +0,631 | 0,850 | 0,071 | ensemble | P0-05 |
| 16:01:29 | LLY | +0,620 | 0,775 | 0,000 | ensemble | P0-05 |
| 16:30:46 | LLY | +0,618 | 0,775 | 0,106 | ensemble | P0-05 |
| 15:45:13 | LLY | +0,612 | 0,800 | 0,177 | ensemble | P0-05 |
| 14:15:09 | DIS | **+0,572** | 0,775 | 0,071 | ensemble | **BUY 14:22** ✓ (score usato 0,687 = ×1,2 velocity) |
| 18:15:36 | **BRKB** | **+0,490** | 0,700 | 0,000 | single:gpt | **mai valutato — simbolo orfano** ([DAY-003]) |
| 16:01:13 | NVO | +0,488 | 0,650 | 0,000 | single:gpt | scartato da #108 |
| 18:45:16 | LLY | +0,488 | 0,650 | 0,000 | single:gpt | scartato da #108 + P0-05 |
| 17:45:42 | LLY | +0,450 | 0,750 | 0,000 | ensemble | P0-05 |
| 14:30:21 | SPY | +0,420 | 0,700 | 0,000 | single:gpt | scartato da #108 |
| 16:30:30 | TSM | +0,360 | 0,600 | 0,000 | single:gpt | scartato da #108 |
| 15:45:36 | MU | +0,343 | 0,650 | 0,141 | ensemble | già in book |
| 16:01:11 | LLY | +0,315 | 0,700 | 0,000 | single:gpt | scartato da #108 + P0-05 |

**Solo 2 dei 16 segnali sopra soglia hanno prodotto un ordine.** Le cause: P0-05 no-pyramiding (9
casi), regola #108 sui `fallback_used` (5 casi, tutti falsi FinBERT — [DAY-007]), simbolo orfano
(1 caso — [DAY-003]).

Gate applicati per ciclo (log, tutti e 24 i cicli):
`entry-freshness` scarta 30–34 segnali · `#108 fallback` 6–8 · `stale > 4h` 12/30 ·
`feedback gate 0,300` 20/25 · `FIX-D` preserva 7 stale su posizioni aperte senza contro-segnale.

---

## 7. Tabella ordini generati / eseguiti

**Modalità: PAPER.** Verificata su tre livelli: `config/trading.yaml → execution.engine=portfolio`;
endpoint broker `paper-api.alpaca.markets` in tutti i log di rete; `run_execution_worker` risponde
`{'skipped': True, 'reason': 'engine=portfolio'}` a ogni ciclo (nessun doppio percorso ordini).

| # | ora dec. | strat | ticker | azione | qty | prezzo fill | stato | meccanismo d'uscita | rationale / segnale causante | risk check |
|---|---|---|---|---|---:|---:|---|---|---|---|
| 1 | 14:22:09 | S1 | SNOW | BUY | 1,7203 | 321,878 | **filled** | — | momentum, peso 0,7 % | P0-05, cap settore, vol target |
| 2 | 14:22:09 | **S4** | DIS | BUY | 16,5164 | 100,870 | **filled** | — | sent. **+0,687**, segnale 6491 (non linkato, F-011) | gate 0,300, freshness, cap 2 % |
| 3 | 14:22:09 | S4 | MCD | SELL | 4,3154 | 273,850 | **filled** | `expired` (19,9 h) | *no counter-signal found* | stop cancellato prima |
| 4 | 14:22:09 | S4 | NVO | SELL | 25,9518 | 45,470 | **filled** | `expired` (19,6 h) | idem, segnale 6461 | stop cancellato prima |
| 5 | 14:22:09 | S4 | PFE | SELL | 45,0083 | 25,470 | **filled** | `expired` (19,9 h) | idem | stop cancellato prima |
| 6 | 14:22:09 | S4 | PLTR | SELL | 6,9780 | 160,270 | **filled** | `expired` (18,9 h) | idem, segnale 6480 | stop cancellato prima |
| 7 | 14:22:09 | S1 | SBUX | SELL | 6,8264 | 105,500 | **filled** | `s1_weight_drop` | peso target → 0 % | stop cancellato prima |
| 8 | 14:52:07 | S1 | SBUX | BUY | 9,0192 | 105,410 | **filled** | — | momentum, peso 1,1 % | **riacquisto a 30 min** |
| 9 | 15:37:07 | **S4** | PLTR | BUY | 10,3691 | 159,870 | **filled** | — | sent. **+0,727**, segnale 6524 | gate 0,300, cap 2 % |
| 10 | 15:52:07 | *(nessuna)* | BP | SELL | 16,6695 | 41,640 | **filled** | `expired` (22,6 h) | chiude il **trade 285 del 10/07** | ([DAY-005]) |
| 11 | 16:07:11 | S1 | BP | BUY | 22,9940 | 41,7617 | **filled** | — | momentum, peso 1,2 % | **riacquisto a 15 min** |
| 12 | 16:07:11 | S4 | DIS | SELL | 16,5164 | 99,790 | **filled** | `whipsaw` | score +0,000, età 0,1 h | `anti_whipsaw_shadow: would_suppress=True` |
| 13 | 16:07:11 | S1 | SNOW | SELL | 1,7203 | 317,830 | **filled** | `s1_weight_drop` | peso target → 0 % | hold-minimum rispettato (1,75 h) |
| 14 | 17:52:10 | S1 | BP | SELL | 22,9940 | 41,630 | **filled** | `s1_weight_drop` | peso target → 0 % | **riconciliazione fallita 17:57, recuperata 18:12** |
| 15 | 18:07:09 | S1 | BP | BUY | 23,0609 | 41,740 | **filled** | — | momentum, peso 1,2 % | **secondo riacquisto BP, 15 min** |
| 16 | 18:52:08 | S1 | BRK.B | BUY | 1,8577 | 517,346 | **filled** | — | momentum, peso 1,2 % | — |
| 17 | 19:07:10 | S1 | SNOW | BUY | 1,7281 | 319,014 | **filled** | — | momentum, peso 0,7 % | **secondo riacquisto SNOW** |
| 18 | 19:52:08 | S1 | BP | SELL | 23,0609 | 41,240 | **filled** | `s1_weight_drop` | peso target → 0 % | — |
| 19 | 19:52:08 | S4 | PLTR | SELL | 10,3691 | 158,720 | **filled** | `expired` (4,4 h) | *no counter-signal found* | — |

**19 ordini generati, 19 inviati, 19 riempiti, 0 rifiutati, 0 cancellati, 0 parziali.**
Riconciliazione ordini → fill → posizioni: **completa**. Ogni `order_id` di decisione compare in
`trades.entry_order_id` o `trades.exit_order_ids`; 8 BUY ↔ 8 nuovi trade (653–660), 11 SELL ↔ 11
uscite. Nessun ordine orfano, nessun trade senza ordine.

Due decisioni `SKIP_STALE` (SHEL 14:07 età 19,4 h; SOXX 18:52 età 4,1 h) — comportamento corretto.

**`portfolio_cycles.orders_count` somma 1 174 su 24 cicli** contro 19 ordini reali: fattore 62×.
Ricorrenza di F-014 ([DAY-010]).

---

## 8. Tabella PnL / rendimento

### 8.1 Realizzato

| strategia (`trades.stop_strategy`) | trade chiusi | net P&L |
|---|---:|---:|
| S4 | 6 | **+23,80 $** |
| S1 | 4 | **−6,48 $** |
| **NULL (non attribuito)** | **1** | **+48,19 $** |
| **totale** | **11** | **+65,51 $** |

**Il 74 % del realizzato della giornata non è attribuibile ad alcuna strategia.** Il dossier
deterministico attribuisce quei 48,19 $ a S1 (`s1_realizzato: 41,71`), il DB dice NULL: **due
fonti in disaccordo sulla stessa grandezza** — [DAY-006].

### 8.2 Per ticker

| ticker | aperta il | chiusa il | qty | entry | exit | net P&L | strategia |
|---|---|---|---:|---:|---:|---:|---|
| BP (trade 285) | 07-10 | 08-05 15:52 | 16,6695 | 38,670 | 41,640 | **+48,19** | *(NULL)* |
| NVO | 08-04 18:52 | 08-05 14:22 | 25,9518 | 44,000 | 45,470 | **+37,52** | S4 |
| MCD | 08-04 18:37 | 08-05 14:22 | 4,3154 | 265,330 | 273,850 | **+36,14** | S4 |
| SBUX | 08-04 14:37 | 08-05 14:22 | 6,8264 | 102,620 | 105,500 | **+19,28** | S1 |
| PFE | 08-04 18:37 | 08-05 14:22 | 45,0083 | 25,440 | 25,470 | +0,72 | S4 |
| BP (657) | 08-05 16:07 | 08-05 17:52 | 22,9940 | 41,762 | 41,630 | −5,00 | S1 |
| SNOW (653) | 08-05 14:22 | 08-05 16:07 | 1,7203 | 321,878 | 317,830 | −7,26 | S1 |
| PLTR (656) | 08-05 15:37 | 08-05 19:52 | 10,3691 | 159,870 | 158,720 | −12,84 | S4 |
| BP (658) | 08-05 18:07 | 08-05 19:52 | 23,0609 | 41,740 | 41,240 | −13,50 | S1 |
| **DIS** | 08-05 14:22 | 08-05 16:07 | 16,5164 | 100,870 | 99,790 | **−18,76** | S4 |
| PLTR (652) | 08-04 19:37 | 08-05 14:22 | 6,9780 | 162,900 | 160,270 | **−18,97** | S4 |

**Fatto strutturale della giornata:** tutte e 5 le uscite in perdita sono trade **aperti e chiusi
lo stesso giorno**; le 4 migliori sono posizioni **portate overnight**. Osservazione, non causalità.

### 8.3 Origine del P&L

| voce | importo |
|---|---:|
| realizzato da posizioni aperte **prima** del 08-05 (5 trade) | **+141,85 $** |
| realizzato da posizioni aperte **il** 08-05 (6 trade) | **−76,34 $** |
| **realizzato totale** | **+65,51 $** |
| MTM del libro aperto (49 posizioni) | **−197,12 $** |
| **P&L economico del giorno** | **−131,61 $** |
| equity 08-04 → 08-05 | 110.366,23 → **110.239,74 $** = **−126,49 $** |
| **residuo di riconciliazione** | **+5,12 $ (0,005 % del NAV)** |

Il residuo è il migliore delle quattro giornate osservate (101,08 $ il 08-04). Resta imputabile
allo scarto fra chiusure IEX e marcature SIP: il feed SIP è indisponibile ([DAY-011]).

### 8.4 Costi e slippage

| voce | importo |
|---|---:|
| `cost_usd` sugli 11 trade chiusi (roundtrip) | **10,29 $** |
| `cost_usd` sui 3 ingressi ancora aperti | 1,28 $ |
| **costi modellati toccati nella giornata** | **≈ 11,57 $** |
| **slippage misurato** | **non disponibile** |

**`trades.slippage_est` è identico a `cost_usd` a 16 cifre decimali su tutte e 11 le righe chiuse.**
La qualità di esecuzione dei 19 ordini della giornata non è misurata da nessuna parte — ricorrenza
di F-015, [DAY-013].

Anomalia di costo notata: i due roundtrip BP (657, 658) pagano 1,967 e 1,971 $ su ~960 $ di
nozionale = **20,5 bps**, contro ~5,4 bps degli altri (SNOW 0,299 $ su 553 $). È il modello di
costo che penalizza il titolo a prezzo basso e alto lotto — non una misura di mercato.

### 8.5 P&L per strategia — avvertenza sulla carta

Il realizzato per strategia di oggi **non risponde alla domanda di uscita 2** della carta: è
distorto dalla regola d'uscita S1 (chiude solo chi ha perso rango) e ha il 74 % del volume in una
riga non attribuita. La grandezza corretta resta il P&L **economico**, che il dossier
deterministico calcola separatamente.

---

## 9. Analisi correttezza buy/sell

| controllo | esito | evidenza |
|---|---|---|
| BUY generati solo quando consentito | ✅ | 8/8 con score sopra soglia (S4) o rank momentum (S1); nessun BUY su ticker fuori watchlist |
| SELL / exit generati correttamente | ✅ | 11/11 con `exit_mechanism` esplicito: 6 `expired`, 4 `s1_weight_drop`, 1 `whipsaw` |
| Stop-loss rispettati | ✅ (nessuno scattato) | `stop_decisions` vuota; 5 stop cancellati correttamente **prima** delle SELL |
| Signal flip rispettato | ✅ | l'unica uscita da contro-segnale (DIS `whipsaw`) è tracciabile allo score sceso a 0,000 |
| Max holding days rispettato | ✅ / ⚠️ | il vincolo attivo è `max_signal_age=4h` **in tempo di parete**, non in giorni — vedi [DAY-005] |
| Rebalance band rispettata | ⚠️ | **nessuna banda fra gate d'ingresso 0,30 e uscita 0** su S4; S1 ricalcola il ranking ogni 15 min → 4 rientri same-day (F-013, già registrata oggi) |
| Ordini duplicati | ✅ nessuno | 19 `order_id` distinti; nessun ordine identico nello stesso minuto |
| Ordini contrari ravvicinati senza rationale | ⚠️ **4 casi, tutti con rationale** | BP SELL 15:52 → BUY 16:07 (15 min); BP SELL 17:52 → BUY 18:07 (15 min); SNOW SELL 16:07 → BUY 19:07; SBUX SELL 14:22 → BUY 14:52. Ogni gamba ha `exit_mechanism` e reason espliciti |
| Roundtrip < 30 min (buy+sell stesso ciclo) | ✅ **nessuno** | hold minimum 90 min applicato e verificato: 5 blocchi nella giornata |
| Pyramiding (>3 BUY di fila senza SELL) | ✅ nessuno | guard P0-05 ha bloccato **1 151 BUY** in 24 cicli |
| SELL con sentiment positivo (bug A5) | ✅ **nessuna** | tutte e 11 le SELL hanno score 0,000 o segnale scaduto; nessuna su score positivo |
| `fallback_used=True` su tutti i simboli (Ollama giù) | ✅ **no** | Ollama up tutta la sessione; 132/195 ensemble a due modelli |
| NO-ORDER (decisione creata, ordine assente) | ✅ **nessuno** | tutte e 19 le decisioni BUY/SELL hanno `order_id` valorizzato |
| Score < 0,05 che generano ordini | ✅ **nessuno** | i 6 BUY S1 hanno `score` di *peso di portafoglio* (0,0066–0,0116), non di sentiment: non è una violazione |
| Ordini identici nello stesso minuto (race scheduler) | ✅ nessuno | — |
| Ordini fuori orario | ✅ nessuno | tutti fra 14:22 e 19:52 UTC; 8 cicli post-chiusura scartati dal guard |
| Trade su dati stale | ✅ | 2 `SKIP_STALE` corretti; 12/30 segnali stale scartati per ciclo |
| Trade con output LLM non valido | ✅ | 0 output invalidi |
| Circuit breaker attivo | ✅ n/a | nessun halt, nessun kill-switch |
| Strategia disabilitata che tradа | ✅ | S2 non ha alcuna riga in `trades` (ma genera alert — [DAY-009]) |
| Paper/live coerente | ✅ | `engine=portfolio`, endpoint paper, `run-execution` inattivo a ogni ciclo |
| **Idempotenza su retry Celery** | ✅ **dimostrata** | `P1-S4: signal_id=6524 for PLTR already fired today — skipping (SIGNAL_DUPLICATE_SKIP)`, 4 volte fra 15:52 e 16:37 |
| Reconciliation ordini/fill/posizioni | ✅ **con un recupero** | 1 fallimento alle 17:57 (rete), recuperato alle 18:12 dal ciclo successivo |

---

## 10. Anomalie trovate

### [DAY-001] La suite di test scrive nel database di produzione

* **Tipo:** Bug
* **Area:** Data / Ops
* **Evidenza:**
  * tabella: `ingestion_stats_daily`, righe con `source='reuters'`
  * timestamp: `2026-08-05 22:06:30.333847+00` (e `2026-08-06 12:35:58+00`)
  * query / snippet:
    ```sql
    SELECT * FROM ingestion_stats_daily WHERE source='reuters' ORDER BY day DESC;
    -- 2026-08-06 | reuters | 4 | 4 | 0 | 1 | 0 | 0 | 2026-08-06 12:35:58
    -- 2026-08-05 | reuters | 4 | 4 | 0 | 1 | 0 | 0 | 2026-08-05 22:06:30
    -- 13 giornate, 2026-07-21 → 2026-08-06, 216 fetched / 216 queued totali
    SELECT count(*) FROM news_log WHERE source='reuters';  -- 0
    ```
    ```python
    # src/workers/ingestion.py:753-756 — dentro run_rss_ingestion_worker()
    from src.store.pg_store import PostgreSQLStore
    with PostgreSQLStore() as _pg:
        _pg.record_ingestion_stats(source_name, stats)
    ```
    ```python
    # tests/workers/test_rss_ingestion.py:94-110 — mocka RSSConnector, Deduplicator,
    # Redis e config, ma NON PostgreSQLStore
    with patch("src.workers.ingestion.RSSConnector") …, \
         patch("src.workers.ingestion.Redis") …, \
         patch.dict(os.environ, {"RSS_INGESTION_ENABLED": "1"}):
        result = run_rss_ingestion_worker()
    ```
* **Descrizione:** l'ingest RSS è disabilitato dal 2026-07-03 (non schedulato nel beat, gated da
  `RSS_INGESTION_ENABLED=0`) e la parola «reuters» non compare **mai** nei log dei container. Le
  righe esistono comunque. I due test `test_rss_worker_*` forzano `RSS_INGESTION_ENABLED=1` e
  chiamano `run_rss_ingestion_worker()` per davvero: `PostgreSQLStore()` non è mockato, quindi
  apre una connessione al `DATABASE_URL` dell'ambiente — che sulla macchina di sviluppo è il
  Postgres di produzione. I numeri combaciano esattamente: test 1 (3 item, 2 queued, 1 senza
  ticker) + test 2 (1 item, 2 queued) = `fetched=4, queued=4, discarded_no_ticker=1`, la riga
  scritta.
* **Impatto:** `ingestion_stats_daily` è una delle tabelle di audit di questo stesso protocollo
  forense, e contiene dati falsi indistinguibili da quelli veri. Più in generale: **una `pytest`
  eseguita nella directory del repo scrive nel DB live**. Oggi il danno è limitato a un contatore,
  ma nulla nel design impedisce che un test futuro tocchi `trades`, `execution_decisions` o
  `sentiment_signals`. È esattamente la classe di difetti che la carta di osservazione esenta dal
  congelamento: se non lo correggo, l'evidenza raccolta nelle prossime sette settimane è
  contaminata da scritture non di produzione.
* **Severità:** High
* **Confidenza:** High — i numeri della riga sono derivabili riga per riga dal codice dei due test.
* **Azione consigliata:** ticket di correttezza. (a) `conftest.py` che fallisce se `DATABASE_URL`
  punta al DB `trading` di produzione; (b) mockare `PostgreSQLStore` nei due test RSS; (c) ripulire
  le 13 righe `source='reuters'` con una migrazione tracciata (non con una DELETE manuale).
* **Test/monitor consigliato:** una fixture autouse che asserisce l'assenza di connessioni al DB
  live durante la suite; un check giornaliero che segnala righe in `ingestion_stats_daily` con
  `source` non presente nel beat schedule attivo.

---

### [DAY-002] Un guasto DNS viene tradotto in «mercato chiuso»: ingest e scoring saltano un ciclo a mercato aperto, e i task riportano successo

* **Tipo:** Bug
* **Area:** Ops / News / LLM
* **Evidenza:**
  * log: `docker compose logs worker` e `worker-inference`
  * timestamp: `2026-08-05 19:30:04` UTC (mercato aperto fino alle 20:00)
  * snippet:
    ```
    [19:30:04,027: ERROR/ForkPoolWorker-2] Could not fetch Alpaca market clock: … NameResolutionError
      ("Failed to resolve 'paper-api.alpaca.markets' ([Errno -5] No address associated with hostname)") — fail-closed
    [19:30:04,027: INFO/ForkPoolWorker-2] Market closed — skipping Alpaca ingestion
    [19:30:04,027: INFO] Task …run_alpaca_ingestion_worker… succeeded in 4.01s: {'skipped': True, 'reason': 'market_closed'}
    [19:30:04,247: INFO] Task …run_news_ingestion_worker…  succeeded in 4.01s: {'skipped': True, 'reason': 'market_closed'}
    [19:30:04,030: ERROR] (worker-inference) Could not fetch Alpaca market clock: … — fail-closed
    → run_sentiment_worker 19:30:04 succeeded in 4.05s: {'skipped': True, 'reason': 'market_closed'}
    ```
    Le uniche 18 righe «Market closed — skipping» della giornata sono quella delle 19:30 e le 16
    legittime fra 20:00 e 21:45.
* **Descrizione:** il `fail-closed` sul market clock è una scelta di sicurezza corretta — meglio
  non ingerire che ingerire a mercato chiuso. Il difetto è che l'esito viene **etichettato
  `market_closed`** invece di `clock_unavailable`, il task Celery viene registrato **`succeeded`**,
  e non viene emesso alcun alert. Il risultato: un buco di ingest e di scoring di un ciclo intero
  (19:30 → 19:45, gli ultimi 30 minuti di sessione) che in ogni tabella e in ogni dashboard è
  **indistinguibile da un mercato legittimamente chiuso**. Il ciclo di recupero delle 19:46 ha
  poi scartato 29 item per staleness. Lo stesso guasto di rete si era già manifestato in forma
  diversa fra 17:56 e 18:01 (risposte HTTP `<html>`, `Connection refused`), facendo fallire la
  riconciliazione dell'exit del trade 657 — recuperata alle 18:12.
* **Impatto:** sulla giornata, nullo sul P&L: nessun segnale sopra soglia era pendente e l'ultimo
  ciclo di portafoglio (19:52) ha letto i segnali recuperati. Sull'evidenza, rilevante: **la
  copertura news misurata da F-001 e la latenza misurata da F-019 non distinguono «non c'era
  notizia» da «non abbiamo guardato»**, e la domanda di uscita 1 della carta si regge su quella
  distinzione.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** ticket di correttezza. Separare `reason='clock_unavailable'` da
  `reason='market_closed'`; far fallire (o ritentare) il task nel primo caso invece di riportare
  successo; alert se il market clock è irraggiungibile durante la finestra 13:30–20:00.
* **Test/monitor consigliato:** test unitario che, con il clock che solleva, verifica che il task
  non ritorni `market_closed`; monitor che conta i cicli di ingest saltati dentro la finestra di
  sessione e allerta se > 0.

---

### [DAY-003] I segnali su Berkshire sono scritti come `BRKB` mentre il simbolo tradabile è `BRK.B`: 81 righe storiche non possono generare alcun ordine

* **Tipo:** Bug
* **Area:** Signal / Data
* **Evidenza:**
  * tabelle: `sentiment_signals`, `news_log`, `execution_decisions`, `trades`
  * timestamp: `2026-08-05 18:15:36` (segnale `BRKB +0,490`), `18:52:08` (BUY `BRK.B` da S1)
  * query:
    ```sql
    SELECT symbol, count(*) FROM sentiment_signals WHERE symbol LIKE 'BRK%';      -- BRKB  | 81
    SELECT symbol, count(*) FROM execution_decisions WHERE symbol LIKE 'BRK%';    -- BRK.B | 1
    SELECT symbol, count(*) FROM trades WHERE symbol LIKE 'BRK%';                 -- BRK.B | 1
    ```
    ```
    config/trading.yaml:46      - BRK.B          (watchlist)
    config/trading.yaml:127     financials: [… BRK.B …]
    src/workers/ingestion.py:46 "BRK.A": "BRK.B"   ← normalizza A→B, ma non BRKB→BRK.B
    log 18:15:57  symbols: ['AMD','LLY','MS','GS','MSFT','BRKB']
    log #108 drop: ['ASML','IWM','JPM','RIO','TXN','UBS','XOM']  ← BRKB non compare: non è nel ranking
    ```
* **Descrizione:** il ticker che arriva dai provider (e viene persistito in `news_log` e
  `sentiment_signals`) è `BRKB`, senza punto. Il simbolo di watchlist, di configurazione settoriale
  e di broker è `BRK.B`. `src/workers/ingestion.py:46` normalizza `BRK.A → BRK.B` ma non tocca la
  forma senza punto. Il risultato: **81 righe di `sentiment_signals` in tutta la storia della
  tabella, e 4 oggi, che non possono né aprire né chiudere una posizione**, perché il ranking S4
  e il percorso d'uscita per contro-segnale sono chiavati sul simbolo. Le decisioni e i trade su
  Berkshire usano solo `BRK.B` — 1 sola riga ciascuna, quella del BUY momentum S1 delle 18:52.
* **Impatto:** su Berkshire, S4 è **strutturalmente cieco in entrambe le direzioni**. Oggi c'era un
  segnale a **+0,490, sopra il gate 0,300**, che non è mai stato valutato. Il costo diretto è
  isolabile solo in parte: quel segnale era `single:gpt-oss` e sarebbe comunque caduto sulla regola
  #108, e BRK.B ha chiuso a +0,32 %. Ma il difetto è permanente e bidirezionale, e falsa la
  copertura news dichiarata: BRKB conta fra i ticker «coperti» pur essendo irraggiungibile.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** ticket di correttezza. Normalizzare il simbolo in ingestione con la
  stessa mappa già usata per `BRK.A` e verificare che l'intera watchlist sia chiusa rispetto alla
  normalizzazione (backfill delle 81 righe storiche separato e tracciato).
* **Test/monitor consigliato:** test che asserisce
  `set(sentiment_signals.symbol) ⊆ set(WATCHLIST_SYMBOLS)`; monitor giornaliero che segnala
  simboli presenti in `sentiment_signals` e assenti dalla watchlist.

---

### [DAY-004] La soglia d'ingresso S4 — congelata dalla carta di osservazione — viene mutata automaticamente dal loop di loss-feedback, e nessun registro ne traccia lo stato

* **Tipo:** Rischio (correttezza dell'evidenza)
* **Area:** Risk / Ops
* **Evidenza:**
  * log: `docker compose logs worker`
  * timestamp: `2026-08-05 20:00:00,035` UTC
  * snippet:
    ```
    [20:00:00,035: WARNING] Loss feedback triggered for S4: EWMA R -0.05, 3 consecutive losses,
      rolling P&L $269.49 — threshold 0.30→0.35, regime scale 1.00→0.80
    ```
    ```
    redis> GET feedback:entry_threshold:S4   → "0.35"     TTL 291112 s (3,4 giorni)
    redis> GET feedback:regime_scale:S4      → "0.8"      TTL 291111 s
    redis> GET feedback:entry_threshold:S1   → "0.0"
    ```
    ```
    src/workers/portfolio_scheduler.py:1293   raw = _r.get(f"feedback:entry_threshold:{strategy}")
    config/trading.yaml:343                   apply_regime_scale: false     ← il regime scale resta shadow
    log 08-05 (24/24 cicli):  "S4 feedback gate: dropped N/M signals below threshold 0.300"
    ```
* **Descrizione:** la carta di osservazione congela «soglie, pesi, flag, cooldown, parametri di
  strategia» dal 03/08 al 28/09. Il gate d'ingresso S4 non è però un parametro statico: è letto a
  ogni ciclo da `feedback:entry_threshold:S4`, che il loop di loss-feedback alza dopo N perdite
  consecutive e lascia decadere con TTL di 3,4 giorni. Il 08-05 tutti e 24 i cicli hanno usato
  0,300; alle 20:00, dopo la chiusura, il valore è passato a **0,35**. Dal 08-06 S4 misura un
  oggetto diverso. Il `regime_scale` a 0,80 resta invece shadow (`apply_regime_scale: false`) e
  non tocca il sizing. Nulla in `findings.json`, `market_daily.jsonl` o nei dossier registra il
  valore della soglia giorno per giorno.
* **Impatto:** i 40 giorni della finestra **non sono confrontabili fra loro** su S4, e non c'è modo
  di accorgersene dai dati raccolti. Tocca direttamente la domanda di uscita 1 della carta e
  l'interpretazione di F-009, che misura il costo del gate «0,30» assumendolo costante. È lo stesso
  profilo delle deroghe già registrate per #163 e #185: se non lo si rende osservabile, l'evidenza
  raccolta è sbagliata.
* **Severità:** High
* **Confidenza:** High
* **Azione consigliata:** **non toccare il meccanismo** (sarebbe taratura). Rendere osservabile lo
  stato: persistere il valore effettivo di `feedback:entry_threshold:<strategy>` e di
  `regime_scale` in `portfolio_cycles` o in una tabella dedicata a ogni ciclo, e aggiungere il
  campo alla riga giornaliera di `market_daily.jsonl`. Annotare la scoperta nella carta.
* **Test/monitor consigliato:** monitor che allerta a ogni transizione di
  `feedback:entry_threshold:*`; check di sintesi al giorno 40 che rifiuta di aggregare giorni con
  soglie diverse senza segmentarli.

---

### [DAY-005] Confermata la previsione su F-024: quattro posizioni S4 chiuse `expired` al primo ciclo del giorno, e il meccanismo liquida anche posizioni che S4 non ha mai aperto

* **Tipo:** Bug (ricorrenza di F-024, con severità nuova)
* **Area:** Orders
* **Evidenza:**
  * tabella: `execution_decisions` id 6600, 6601, 6602, 6603, 6722, 7069
  * timestamp: `2026-08-05 14:22:09` e `15:52:07` UTC
  * snippet:
    ```
    6600 14:22 MCD  SELL expired  [expired] S4 signal expired (age=19.9h > max_age=4h,
                                   generated 2026-08-04 18:30 UTC, score=+0.393) — no counter-signal found
    6601 14:22 NVO  SELL expired  (age=19.6h, generated 08-04 18:45, score=+0.656)
    6602 14:22 PFE  SELL expired  (age=19.9h, generated 08-04 18:30, score=+0.514)
    6603 14:22 PLTR SELL expired  (age=18.9h, generated 08-04 19:30, score=+0.383)
    6722 15:52 BP   SELL expired  (age=22.6h, generated 08-04 17:15, score=+0.646)  ← chiude trade 285, APERTO IL 10/07
    7069 19:52 PLTR SELL expired  (age=4.4h,  generated 08-05 15:30, score=+0.727)
    ```
* **Descrizione:** il report del 08-04 aveva registrato la previsione falsificabile «le 4 posizioni
  S4 aperte dopo le 18:30 del 08-04 (PFE, MCD, NVO, PLTR) devono essere chiuse con
  `exit_mechanism='expired'` al primo ciclo del giorno». **Verificata alla lettera**: tutte e
  quattro, alle 14:22:09, con età fra 18,9 e 19,9 ore quasi interamente notturne, e con il testo
  che dichiara esplicitamente *no counter-signal found*.
  Due elementi nuovi rispetto al 08-04. **Primo**: il meccanismo ha colpito il **trade 285 su BP,
  aperto il 10/07 e senza attribuzione di strategia** — un segnale S4 scaduto ha liquidato una
  posizione che S4 non ha mai aperto, e 15 minuti dopo S1 l'ha ricomprata (decisione 6746).
  **Secondo**: la chiusura di PLTR alle 19:52 mostra che la regola morde anche **dentro** la
  sessione (età 4,4 h su un ingresso delle 15:37), quindi non è solo un problema di orologio
  notturno ma un tetto di detenzione implicito di 4 ore.
* **Impatto:** **oggi il difetto ha fatto guadagnare denaro.** Sommando il `drift_post_uscita` del
  dossier deterministico sulle quattro uscite delle 14:22 (MCD +0,65, PLTR −12,84, PFE +15,30,
  NVO −24,39) il risultato è **−21,28 $**: tenere fino alla chiusura sarebbe costato 21,28 $ in
  più. Su BP il drift è −7,17 $, anch'esso favorevole. Il costo attribuito è quindi **0,00 $
  (calcolato, non stimato per difetto)**. Resta il difetto strutturale: le uscite non sono decise
  da un contro-segnale ma da un orologio, e l'attribuzione incrociata S4→posizione S1/legacy è una
  interferenza fra strategie.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** ticket di correttezza sull'**interferenza fra strategie**: un
  `exit_mechanism` S4 non deve poter chiudere una posizione la cui provenienza non è S4. La
  conversione di `max_signal_age` in tempo di mercato è invece **taratura** e resta congelata.
* **Test/monitor consigliato:** test che verifica che un'uscita `expired` di S4 agisca solo su
  trade con `stop_strategy='S4'`; monitor giornaliero che conta le uscite `expired` per
  provenienza della posizione.

---

### [DAY-006] Il 74 % del realizzato della giornata non è attribuibile ad alcuna strategia, e le due fonti di attribuzione si contraddicono

* **Tipo:** Bug (ricorrenza di F-002, prima occorrenza con importo misurato)
* **Area:** PnL / Data
* **Evidenza:**
  * tabelle: `trades`, `docs/evidence/dossier/2026-08-05.json`
  * timestamp: `2026-08-05 15:52:00` UTC
  * query:
    ```sql
    SELECT stop_strategy, count(*), round(sum(net_pnl)::numeric,2)
    FROM trades WHERE exit_time::date='2026-08-05' GROUP BY 1;
    --  S1  | 4 |  -6.48
    --  S4  | 6 | +23.80
    --      | 1 | +48.19      ← trade 285, BP, aperto il 07-10, stop_strategy NULL
    SELECT count(*) FILTER (WHERE stop_strategy IS NULL) FROM trades WHERE exit_time IS NULL;  -- 11 su 49
    ```
    Dossier deterministico dello stesso giorno: `"s1_realizzato": 41.71` = −6,48 + 48,19.
* **Descrizione:** ricorrenza del difetto già registrato il 07-31, 08-03 e 08-04, ma per la prima
  volta **con un importo reale a bilancio**: il trade 285 su BP si è chiuso oggi realizzando
  +48,19 $, cioè il **74 % del realizzato dell'intera giornata**, senza alcuna attribuzione di
  strategia in `trades.stop_strategy`. Restano 11 posizioni aperte su 49 nella stessa condizione
  (tutte aperte il 10/07). Elemento nuovo: **le due fonti divergono**. Il DB dice NULL; lo script
  del dossier attribuisce l'importo a S1 con un'euristica propria. Chi legge le due serie ottiene
  due risposte diverse alla stessa domanda, e nessuna delle due è dichiarata autorevole.
* **Impatto:** la domanda di uscita 2 della carta chiede lo split del P&L economico S1 contro SPY.
  Finché l'11/49 del libro e il 74 % del realizzato di una giornata restano fuori dallo split — o
  peggio, dentro per euristica in una fonte e fuori nell'altra — quello split non è calcolabile in
  modo riproducibile. Nessuna perdita diretta: costo non stimabile.
* **Severità:** High (per l'evidenza, non per il P&L)
* **Confidenza:** High
* **Azione consigliata:** ticket di correttezza. Backfill di `stop_strategy` sulle 11 posizioni
  legacy con la provenienza ricostruita dalle decisioni del 10/07; e allineare l'euristica del
  dossier alla colonna, o dichiarare esplicitamente quale delle due è la fonte autorevole.
* **Test/monitor consigliato:** check giornaliero che allerta se
  `sum(net_pnl WHERE stop_strategy IS NULL) / sum(net_pnl) > 10 %`; test di consistenza fra il
  totale per strategia del dossier e quello di `trades`.

---

### [DAY-007] Il retry a floor 0 non è propagato: 61 segnali su 195 (31 %) buttano l'opinione di un modello, e 63 sono contati come «FinBERT» quando FinBERT ne ha prodotti 2

* **Tipo:** Bug (ricorrenza di F-010, con decomposizione esatta)
* **Area:** LLM
* **Evidenza:**
  * tabelle: `llm_responses`, `sentiment_signals`; log `worker-inference`
  * timestamp: giornata intera, 24 cicli
  * query:
    ```sql
    -- regimi di eleggibilità (floor 0.4), per segnale
    both>=0.4: 30 | neither>=0.4: 104 | exactly one>=0.4: 61      (totale 195)
    -- esito scritto
    ensemble: 132 (= 28 + 104) | single:gpt-oss: 54 | single:glm: 7 | finbert: 2
    -- eligible=true: 28/195 per entrambi i modelli
    ```
    ```
    Divergenze reali → FinBERT nei log:  2   (SPCX 14:30:37, LLY 17:15:23)
    Somma di 'finbert_fallbacks' sui 24 cicli del worker: 63
    ```
* **Descrizione:** ricorrenza esatta di F-010 con l'aritmetica che chiude perfettamente.
  **(a) Floor asimmetrico:** quando *nessuno* dei due modelli supera 0,4 il retry #90 rientra e
  produce un ensemble a due modelli (104 casi); quando li supera *uno solo*, il retry non entra
  mai (il risultato non è `None`) e il sistema scrive `single:<model>` buttando l'opinione
  dell'altro — **61 casi, il 31 % della produzione**. Il sistema è meno inclusivo proprio quando
  ha un modello confidente. **(b) Etichettatura falsa:** quei 61 vengono marcati
  `fallback_used=true` e contati come «finbert_fallbacks» dal worker (63 con i 2 veri), mentre
  FinBERT ha prodotto **2 righe su 195 (1,0 %)**. La regola #108 esclude dal ranking BUY tutti i
  `fallback_used`, cioè **60 segnali di LLM cloud veri**. **(c) `eligible`:** 28 righe su 195 per
  modello sono marcate eleggibili mentre 132 segnali sono ensemble a due modelli — il
  ribilanciamento LOO-ICIR che scrive `ensemble:weights:current` gira su un sottocampione non
  casuale.
* **Impatto:** oggi 5 segnali sopra il gate 0,300 sono stati scartati da #108 come «FinBERT»
  (LLY ×2, NVO, SPY, TSM) e nessuno era FinBERT. Nessuno di essi ha un costo isolabile: LLY e TSM
  erano già in book (P0-05), NVO/SPY/TSM hanno chiuso in negativo o piatti rispetto al momento del
  segnale. Costo non stimabile su questa giornata; il difetto resta sul path live perché i pesi
  d'ensemble calcolati sul sottocampione rientrano in ogni score successivo.
* **Severità:** High
* **Confidenza:** High
* **Azione consigliata:** ticket di correttezza. Propagare il `min_confidence` effettivamente usato
  a `log_llm_responses` (oggi 0,4 hardcoded, `src/store/pg_store.py:1757,1781`); estendere il retry
  #90 al ramo single-model; distinguere `fallback_used` in `finbert_fallback` e
  `single_model_ensemble` così che #108 escluda solo il primo.
* **Test/monitor consigliato:** test che verifica `eligible` coerente con il floor realmente
  applicato; monitor che confronta il contatore `finbert_fallbacks` del worker con
  `count(model_id='finbert')` e allerta se divergono.

---

### [DAY-008] `combined_drawdown` incoerente con il drawdown che genera l'ALERT

* **Tipo:** Bug (ricorrenza di F-003)
* **Area:** Risk
* **Evidenza:**
  * tabella: `risk_reports` id **54**
  * timestamp: `2026-08-05 22:30:01.004479+00`
  * query:
    ```sql
    SELECT combined_drawdown, alerts FROM risk_reports WHERE id=54;
    -- combined_drawdown = 0.012429  (1,24 %)
    -- alerts = [{"level":"ALERT","message":"Strategy portfolio drawdown 13.9% exceeds 10%","strategy_id":"portfolio"}]
    ```
* **Descrizione:** ricorrenza identica al 07-31, 08-03 e 08-04. Nello stesso record convivono un
  `combined_drawdown` di 1,24 % nella colonna dedicata e un alert al 13,9 % generato da
  `per_strategy_metrics.portfolio.drawdown`; 11× di scarto, nessuna delle due grandezze dichiarata
  autorevole. Il valore 0,138668 è congelato da **sette giorni consecutivi** (30/07 → 05/08) mentre
  il NAV si muove: l'alert si ripete identico ogni sera senza portare informazione. La causa
  radice era stata isolata il 08-04: la vista `portfolio_daily_state` calcola `daily_return` sui
  **soli trade chiusi** nel giorno (oggi: +65,51 / 8.914,00 di nozionale d'ingresso), grandezza
  che non ha relazione con il rendimento del libro (−126,49 $).
* **Impatto:** nessuna perdita diretta. Il drawdown è una delle grandezze da leggere durante il
  periodo di osservazione ed è, oggi, illeggibile.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** ticket di correttezza già motivato il 08-04; nessuna azione nuova.
* **Test/monitor consigliato:** test di consistenza fra `combined_drawdown` e il drawdown usato
  per l'alert nello stesso record.

---

### [DAY-009] `decay_monitor` confronta metriche pipeline-globali contro tre baseline distinte, inclusa S2 mai tradata

* **Tipo:** Bug (ricorrenza di F-004)
* **Area:** Risk / Ops
* **Evidenza:**
  * log: `docker compose logs worker`
  * timestamp: `2026-08-05 21:00:00,441-451` UTC
  * snippet:
    ```
    DECAY CRITICAL [S1]: IC dropped 75% from 0.035 to 0.009    Sharpe below 50% of baseline: -7.00 vs 0.95
    DECAY CRITICAL [S2]: IC dropped 79% from 0.042 to 0.009    Hit rate dropped 15.7pp    Sharpe: -7.00 vs 1.10
    DECAY CRITICAL [S4]: IC dropped 69% from 0.028 to 0.009    Sharpe below 50% of baseline: -7.00 vs 0.80
    total_alerts: 7
    ```
* **Descrizione:** ricorrenza invariata. **IC attuale 0,009 identico** per S1, S2 e S4 e **Sharpe
  −7,00 identico** per le tre, confrontati contro tre baseline diverse (0,95 / 1,10 / 0,80). S2 è
  disabilitata, non ha mai una riga in `trades`, e genera **3 dei 7 alert**. Radice invariata:
  `src/workers/decay_monitor_task.py:52-66` non filtra per `strategy_id`; la serie Sharpe viene
  dalla stessa `portfolio_daily_state` difettosa di [DAY-008].
* **Impatto:** rischio diretto sulla domanda di uscita 2 della carta se qualcuno consulta
  `decay_reports` credendo di leggere metriche S1-specifiche. Nessuna perdita.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** ticket di correttezza già motivato; nessuna azione nuova.
* **Test/monitor consigliato:** test che verifica che due strategie con trade diversi producano
  metriche di decay diverse.

---

### [DAY-010] Telemetria del ciclo portfolio fuorviante: `orders_count` conta i target, il log hold-minimum elenca i candidati

* **Tipo:** Bug (ricorrenza di F-014)
* **Area:** Ops
* **Evidenza:**
  * tabella `portfolio_cycles`; log `worker`
  * timestamp: giornata intera; `2026-08-05 15:07:12,012`
  * query e snippet:
    ```sql
    SELECT sum(orders_count) FROM portfolio_cycles WHERE timestamp::date='2026-08-05';  -- 1174
    -- ordini realmente inviati: 19
    ```
    ```
    [15:07:12,012] Hold minimum (90 min): skipped 2 SELL order(s) for recently-bought: ['DIS','SBUX','SNOW']
    [19:22:09,292] Hold minimum (90 min): skipped 3 SELL order(s) for recently-bought: ['BP','BRK.B','SNOW']
    [19:37:08,906] Hold minimum (90 min): skipped 1 SELL order(s) for recently-bought: ['BRK.B','SNOW']
    ```
* **Descrizione:** ricorrenza esatta del 08-03 e 08-04, oggi con lo scarto peggiore mai misurato:
  1 174 contro 19 = **62×** (era 4-5× nelle due giornate precedenti, perché oggi ci sono stati meno
  ordini reali a parità di target). E il log hold-minimum continua a dichiarare il conteggio degli
  scartati mentre elenca l'insieme dei candidati recenti: alle 19:37 dichiara 1 e ne elenca 2.
* **Impatto:** un'analisi che leggesse `portfolio_cycles` come registro degli ordini sbaglierebbe
  di quasi due ordini di grandezza. Puro difetto di osservabilità.
* **Severità:** Low
* **Confidenza:** High
* **Azione consigliata:** ticket già motivato; nessuna azione nuova.
* **Test/monitor consigliato:** persistere `orders_submitted` accanto a `orders_count`.

---

### [DAY-011] Il fetch del benchmark SPY fallisce in modo permanente senza alcun alert

* **Tipo:** Osservazione (ricorrenza di F-016)
* **Area:** Data / Ops
* **Evidenza:**
  * log: `docker compose logs worker`
  * timestamp: 84 occorrenze nella giornata
  * snippet: `SPY benchmark fetch failed: {"message":"subscription does not permit querying recent SIP data"}`
* **Descrizione:** ricorrenza invariata rispetto al 08-03 e 08-04. **84 WARNING**, nessun alert,
  nessun degrado esplicito a IEX. `src/portfolio/spy.py:102` cattura, logga e torna `None`;
  `src/mobile_monitoring/performance.py:214-224` azzera `spy_return`, `benchmark_return` e `alpha`
  — corretto, non inventa dati. Ma la condizione dura tutto il giorno e nessuno viene avvisato.
* **Impatto:** oggi il residuo di riconciliazione P&L è sceso a **5,12 $** (contro 101,08 $ il
  08-04), quindi la conseguenza misurata il 08-04 non si ripete con la stessa ampiezza. La domanda
  di uscita 2 della carta usa una via diversa (`market_daily.jsonl` riporta correttamente
  `spy: -0.0020`), quindi non è bloccata. Resta che una delle due vie di lettura del benchmark è
  morta e nessuno viene avvisato.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** alert (non taratura) su fallimento persistente del benchmark; valutare il
  degrado esplicito a IEX.
* **Test/monitor consigliato:** monitor che allerta se il benchmark è `None` per > 3 cicli.

---

### [DAY-012] Le finestre beat sono in ora UTC fissa e ignorano il DST: 37 minuti di sessione scoperti, 8 cicli sprecati dopo la chiusura

* **Tipo:** Bug (ricorrenza di F-021)
* **Area:** Ops
* **Evidenza:**
  * `src/workers/celery_app.py:78` (ingest, `hour="14-21"`), `:201` (portfolio-cycle,
    `minute="7,22,37,52" hour="14-21"`)
  * timestamp: primo ciclo `14:07:00`, prima riga `news_log` `14:15:09`, ultimo ciclo utile `19:52`
  * snippet: 16 righe «Market closed — skipping» fra 20:00 e 21:45 (8 slot × 2 connettori), più i
    cicli portfolio e sentiment nella stessa finestra
* **Descrizione:** ricorrenza esatta del 08-04. Gli USA sono in EDT: la sessione va 13:30–20:00
  UTC, le finestre beat vanno 14:00–21:00 UTC (EST). Misurato oggi: **primo ciclo di portafoglio
  alle 14:07, cioè 37 minuti dopo l'apertura**; **8 slot fra 20:00 e 21:45 eseguiti e scartati** dal
  guard. Il guard funziona: nessun ordine è mai partito fuori orario.
* **Impatto:** nessun costo isolabile oggi (la prima notizia arriva alle 14:15). Il buco è però
  strutturale e quotidiano per ~8 mesi l'anno, e cade nella fase in cui i report alpha-miss
  misurano ripetutamente più della metà del movimento dei mover (gap di apertura). **Ogni giorno
  osservato esclude sistematicamente gli stessi 37 minuti di sessione.**
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** ticket di correttezza: agganciare le finestre beat al calendario Alpaca
  invece che a un'ora UTC fissa.
* **Test/monitor consigliato:** test che verifica che il primo ciclo di portafoglio cada entro N
  minuti dall'apertura effettiva restituita da `GetCalendarRequest`.

---

### [DAY-013] `trades.slippage_est` è una copia di `cost_usd`: la qualità di esecuzione non è misurata

* **Tipo:** Bug (ricorrenza di F-015)
* **Area:** PnL / Broker
* **Evidenza:**
  * tabella `trades`, tutte e 11 le righe chiuse il 2026-08-05
  * query:
    ```sql
    SELECT id, cost_usd, slippage_est FROM trades WHERE exit_time::date='2026-08-05';
    -- 653: 0.2989… = 0.2989…  |  654: 0.9212… = 0.9212…  |  657: 1.9669… = 1.9669…  (11/11 identici)
    ```
* **Descrizione:** ricorrenza invariata. `slippage_est` è valorizzato all'uscita con il costo di
  transazione modellato, non con lo scostamento del fill da un prezzo di riferimento — che non
  esiste, perché `execution_decisions` non registra alcun prezzo atteso o di arrivo al momento
  della decisione. Il campo dichiara di misurare una cosa e ne contiene un'altra.
* **Impatto:** qualsiasi analisi di execution quality sui 19 ordini della giornata è impossibile e,
  se condotta su questa colonna, restituirebbe il modello di costo invece della realtà. Tutti gli
  ingressi sono ordini market da 550–1 670 $ su titoli molto liquidi, quindi lo slippage vero è
  probabilmente piccolo — ma è un'ipotesi, non una misura. La query che servirebbe (confronto fra
  `filled_avg_price` e il mid del NBBO al `submitted_at`) è oggi impossibile perché richiede il
  feed SIP ([DAY-011]).
* **Severità:** Low
* **Confidenza:** High
* **Azione consigliata:** ticket già motivato; nessuna azione nuova.
* **Test/monitor consigliato:** —

---

### [DAY-014] Gli stop protettivi lasciano scoperte 13 posizioni a ogni ciclo di sync

* **Tipo:** Osservazione (ricorrenza di F-022)
* **Area:** Risk
* **Evidenza:**
  * log: `docker compose logs worker`
  * timestamp: 8 sync nella giornata
  * snippet:
    ```
    [14:07:13] Fractional protective stop sync: {'created':0,'replaced':1,'noop':38,'skipped':13,'cancelled_orphans':0,'errors':[]}
    [14:22:12] … {'created':2,'noop':34,'skipped':16, …}
    [19:07:10] … {'created':1,'noop':37,'skipped':13, …}
    ```
* **Descrizione:** ricorrenza del 08-04. Alpaca rifiuta gli stop su quantità frazionarie e
  `fractional_stop_orders.py:69` usa `math.floor(abs(position_qty))`: le posizioni sotto 1 azione
  non ottengono alcuno stop. **13 posizioni su 49 (27 %) restano senza protezione broker-side a
  ogni ciclo**, invariate per tutta la giornata. Confermato inoltre che lo stop viene creato al
  ciclo *successivo* all'ingresso (BRK.B comprato 18:52, sync stop 19:07): ~15 minuti di
  esposizione non protetta su ogni nuovo ingresso.
* **Impatto:** nessuno stop è scattato oggi, quindi nessun costo reale. La condizione di revisione
  scritta in `config/trading.yaml:180-182` è già oggetto della deroga #161 registrata nella carta.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** nessuna nuova — l'alert è già in corso (#161); la size minima ≥ 1 azione
  è taratura e resta al 28/09.
* **Test/monitor consigliato:** già coperto da #161.

---

### [DAY-015] Il bot token Telegram compare in chiaro negli URL loggati a livello INFO

* **Tipo:** Osservazione (ricorrenza di F-018)
* **Area:** Ops
* **Evidenza:** `docker compose logs worker-inference`, task `poll-telegram-updates`
  (`celery_app.py`, schedule 5.0 s) → ~17 280 richieste `GET api.telegram.org/bot<TOKEN>/getUpdates`
  loggate a livello INFO da `httpx` nelle 24 ore.
* **Descrizione:** ricorrenza invariata del 08-03 e 08-04. Chiunque abbia accesso ai log dei
  container ha il token del bot che serve il flusso di approvazione con inline keyboard. Le
  chiamate occupano inoltre l'unico ForkPoolWorker di un container a concurrency 1 dedicato
  all'isolamento dell'inferenza.
* **Impatto:** nessuno sul trading; esposizione di credenziale nei log. Costo non stimabile.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** abbassare a WARNING il logger `httpx` nel container di inferenza e
  redigere il token.
* **Test/monitor consigliato:** —

---

## 11. False positive e aree risultate corrette

| area | esito | evidenza |
|---|---|---|
| **Lo score 0,687 su DIS che il report alpha-miss non riusciva a spiegare** | **spiegato, non è un'anomalia** | `sentiment_signals` massimo per DIS = **+0,5722**; `execution_decisions.signal_score` = 0,6867 = **0,5722 × 1,2**. Il moltiplicatore viene da `_compute_signal_velocity` (`portfolio_scheduler.py:3229, 3767-3797`), e il log delle 14:22 registra «Signal velocity: 5/25 symbols adjusted». Il difetto sottostante (F-011, `signal_id` NULL che impedisce la verifica) **resta**, ma il valore è deterministico e corretto |
| **Rilevazione di regime** | **corretta oggi** | 07:00 e 13:30 entrambe riuscite, `bull ×1.0`, `disagreement=False`. Nessuna ricorrenza di F-017; `regime_mult=1.0` su tutte le 488 decisioni |
| **Alert Telegram** | **nessun fallimento oggi** | il trigger di loss-feedback S4 delle 20:00 non ha prodotto alcun `400 Bad Request`. Nessuna ricorrenza di F-005 |
| **Idempotenza su retry** | **dimostrata** | `SIGNAL_DUPLICATE_SKIP` su `signal_id=6524` (PLTR), 4 cicli consecutivi 15:52→16:37 |
| **Guard anti-pyramiding P0-05** | **corretto, 1 151 blocchi** | ha impedito ogni doppio ingresso, incluso su LLY (mover #1, 8 segnali sopra soglia) |
| **Hold minimum 90 min** | **corretto** | 5 blocchi; nessun roundtrip sotto 90 minuti in tutta la giornata |
| **Cancellazione stop prima delle SELL** | **corretta** | 5 stop cancellati prima delle rispettive SELL, sequenza sempre nell'ordine giusto |
| **Riconciliazione ordini→fill→posizioni** | **completa** | 19/19 `order_id` mappati; il fallimento delle 17:57 è stato recuperato dal ciclo delle 18:12 senza intervento |
| **Restart di container** | **zero** | tutti e 7 i container su da 07-22/07-30, `RestartCount=0` |
| **Nessun ordine fuori orario** | **verificato** | 8 cicli post-chiusura eseguiti e correttamente scartati dal guard |
| **Nessuna SELL su sentiment positivo** | **verificato** | tutte e 11 le SELL su score 0,000 o segnale scaduto |
| **Nessun ordine sotto il gate** | **verificato** | massimo `signal_score` fra i 467 `SKIP_THRESHOLD` = +0,238 |
| **Timestamp futuri / campi mancanti nelle news** | **zero** | 194/194 righe con `published_at ≤ created_at`, title e url non vuoti, `content_hash` sempre presente |

---

## 12. Dati mancanti o non accessibili

| risorsa | stato | impatto sull'analisi | cosa servirebbe |
|---|---|---|---|
| **API REST locale (`localhost:8001`)** | **non accessibile** — tutti e 5 gli endpoint rispondono `403 {"detail":"Invalid or expired JWT token"}` col bearer fornito | **nullo**: ogni grandezza è stata ricavata da Postgres, dai log dei container e dal dossier deterministico | rigenerare il token; l'endpoint risponde, è l'autenticazione a fallire. Seconda giornata consecutiva |
| **Latenza per-modello LLM** | **non misurabile** | la sezione 5 non riporta latenza per modello | `llm_responses` non ha colonna di latenza; servirebbe una migrazione |
| **Slippage reale** | **non misurabile** | sezione 8.4 incompleta | prezzo di arrivo in `execution_decisions` + feed SIP ([DAY-011], [DAY-013]) |
| **Contenuto dei 29 item scartati alle 19:46** | **perso** | non si può quantificare il costo di [DAY-002] | `news_queue_drops` registra il conteggio ma non il payload degli item scartati per staleness dal sentiment worker |
| **Log Docker oltre 48 h** | ritenzione limitata | nessuno per questa giornata | — |
| **Log frontend** | non esaminati | nessuno: nessuna interazione operatore nella giornata | — |
| **Verifica indipendente di `duplicates`** | **impossibile** | F-007 resta non verificabile | i duplicati non lasciano riga |

---

## 13. Raccomandazioni immediate

Tutte di **correttezza**, nessuna di taratura — coerentemente con il periodo di osservazione.

1. **Isolare la suite di test dal DB di produzione** ([DAY-001]). È la raccomandazione più urgente
   perché è l'unica che può, in linea di principio, corrompere tabelle del money path. Una
   `conftest.py` che rifiuta di partire se `DATABASE_URL` punta al database `trading` costa dieci
   righe.
2. **Distinguere `clock_unavailable` da `market_closed`** ([DAY-002]) e non riportare `succeeded`
   nel primo caso. Senza questo, ogni buco di rete durante la finestra si presenta nei dati come
   assenza di notizie, che è esattamente la grandezza su cui si decide la domanda di uscita 1.
3. **Normalizzare `BRKB → BRK.B` in ingestione** ([DAY-003]) e aggiungere l'asserzione che i
   simboli dei segnali siano un sottoinsieme della watchlist.
4. **Rendere osservabile la soglia d'ingresso effettiva** ([DAY-004]): persisterla a ogni ciclo e
   nella riga giornaliera di `market_daily.jsonl`, e annotare nella carta di osservazione che il
   parametro non è statico. **Non toccare il meccanismo.**
5. **Backfill di `stop_strategy` sulle 11 posizioni legacy del 10/07** ([DAY-006]) e allineamento
   fra l'attribuzione del dossier e quella del DB. Senza, lo split S1/SPY della domanda 2 non è
   riproducibile.
6. **Impedire che un `exit_mechanism` S4 chiuda posizioni non-S4** ([DAY-005]).

## 14. Test o monitor da aggiungere

| # | tipo | descrizione | copre |
|---|---|---|---|
| T1 | fixture pytest autouse | fallisce se `DATABASE_URL` risolve al DB di produzione | [DAY-001] |
| T2 | monitor giornaliero | segnala righe in `ingestion_stats_daily` con `source` non nel beat schedule attivo | [DAY-001] |
| T3 | test unitario | il market clock che solleva non deve produrre `reason='market_closed'` | [DAY-002] |
| T4 | monitor | conta i cicli di ingest/sentiment saltati **dentro** la finestra di sessione; allerta se > 0 | [DAY-002] |
| T5 | test di invariante | `set(sentiment_signals.symbol) ⊆ set(WATCHLIST_SYMBOLS)` | [DAY-003] |
| T6 | monitor | allerta a ogni transizione di `feedback:entry_threshold:*` e la registra nel ledger | [DAY-004] |
| T7 | test | un'uscita `expired` di S4 agisce solo su trade con `stop_strategy='S4'` | [DAY-005] |
| T8 | check giornaliero | allerta se `sum(net_pnl WHERE stop_strategy IS NULL) / sum(net_pnl) > 10 %` | [DAY-006] |
| T9 | monitor | confronta il contatore `finbert_fallbacks` del worker con `count(model_id='finbert')` | [DAY-007] |
| T10 | test di consistenza | `combined_drawdown` vs drawdown dell'alert nello stesso `risk_reports` | [DAY-008] |
| T11 | test | due strategie con trade diversi devono produrre metriche di decay diverse | [DAY-009] |
| T12 | colonna | `portfolio_cycles.orders_submitted` accanto a `orders_count` | [DAY-010] |
| T13 | monitor | benchmark `None` per > 3 cicli consecutivi → alert | [DAY-011] |
| T14 | test | il primo ciclo di portafoglio cade entro N minuti dall'apertura da `GetCalendarRequest` | [DAY-012] |

## 15. Ticket tecnici suggeriti

Tutti superano il test di esenzione della carta («se non lo correggo, l'evidenza che raccolgo nelle
prossime settimane è sbagliata?»). Nessuno tocca soglie, pesi o parametri di strategia.

| id | titolo | severità | finding |
|---|---|---|---|
| **TCK-A** | La suite di test scrive in `ingestion_stats_daily` del DB di produzione — isolare `DATABASE_URL` nei test e mockare `PostgreSQLStore` in `test_rss_ingestion.py` | **High** | F-025 |
| **TCK-B** | Distinguere `clock_unavailable` da `market_closed`: non riportare `succeeded` su fail-closed di rete e allertare | **Medium** | F-026 |
| **TCK-C** | Normalizzare `BRKB → BRK.B` in ingestione e asserire che i simboli dei segnali siano nella watchlist | **Medium** | F-027 |
| **TCK-D** | Persistere la soglia d'ingresso e il regime scale effettivi a ogni ciclo (osservabilità del loop di loss-feedback) | **High** | F-028 |
| **TCK-E** | Un `exit_mechanism` S4 non deve chiudere posizioni con `stop_strategy` diverso da S4 | **Medium** | F-024 |
| **TCK-F** | Backfill di `stop_strategy` sulle 11 posizioni legacy del 10/07 e allineamento dossier↔DB | **High** | F-002 |
| **TCK-G** | Propagare il `min_confidence` effettivo a `log_llm_responses`; estendere il retry #90 al ramo single-model; separare `finbert_fallback` da `single_model_ensemble` in #108 | **High** | F-010 |
| **TCK-H** | Agganciare le finestre beat al calendario Alpaca invece che a un'ora UTC fissa (DST) | **Medium** | F-021 |
| — | *(già aperti nelle giornate precedenti)* `combined_drawdown`, `decay_monitor` per-strategia, `orders_count`, benchmark SPY, `slippage_est`, token Telegram | — | F-003, F-004, F-014, F-016, F-015, F-018 |

## 16. Stato sistema

| grandezza | valore |
|---|---|
| **Ollama Cloud** | **UP per l'intera sessione. 0 minuti di downtime.** 195/195 richieste riuscite per entrambi i modelli, 0 errori, 0 timeout, 0 output invalidi |
| **Coppia attiva** | `glm-5.2:cloud` + `gpt-oss:20b-cloud` — corretta, corrispondente al registro |
| **FinBERT fallback rate (reale)** | **2 / 195 = 1,0 %** dei segnali · **0 / 19 = 0 %** degli ordini |
| **FinBERT fallback rate (come riportato dal worker)** | **63 / 195 = 32,3 %** — cifra falsa, vedi [DAY-007] |
| **Segnali `fallback_used=true` esclusi dal ranking BUY (#108)** | 61 (31,3 %), di cui **60 sono LLM cloud veri** |
| **Worker restart events** | **0.** `alembic-worker-1`, `worker-inference-1`, `api-1`, `beat-1` su dal 2026-07-30 13:49; `postgres-1`, `redis-1` dal 2026-07-22; `frontend-1` dal 2026-07-28. `RestartCount=0` su tutti e 7 |
| **Incidenti di rete** | **2** — 17:56–18:01 (risposte HTTP `<html>`, `Connection refused`; 1 riconciliazione fallita, recuperata alle 18:12) e 19:30 (DNS `NameResolutionError`; 3 task saltati, [DAY-002]) |
| **Cicli di portafoglio** | 24/24 eseguiti, 14:07 → 19:52 |
| **Cicli sentiment** | 23/24 eseguiti (1 saltato alle 19:30) + 8 correttamente saltati a mercato chiuso |
| **Errori nei log** | 4 `ERROR` in `worker` (2 DNS + 2 decay-monitor CRITICAL non sono errori di sistema), 2 in `worker-inference` (1 DNS, 1 telegram reset) |
| **Regime** | `bull ×1.0`, entrambe le rilevazioni riuscite; `regime_mult=1.0` su 488/488 decisioni |
| **Soglia S4 a fine giornata** | **0,35** (era 0,30 durante tutti i 24 cicli) — TTL 3,4 giorni, [DAY-004] |
| **Kill-switch / circuit breaker / halt operatore** | nessuno attivo |
| **NAV di chiusura** | 110.248,50 $ (`risk_reports` id 54) · esposizione totale 29,99 % · Herfindahl 0,0226 |

---

*Report prodotto in modalità read-only. Nessun file di codice o configurazione modificato, nessun
ordine inviato, nessun worker avviato. Ledger delle evidenze aggiornato in
`docs/evidence/findings.json`.*
