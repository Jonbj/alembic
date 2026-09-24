# Forensic Daily Report — 2026-08-21

Timezone operativo: **UTC** (`src/workers/celery_app.py:56`, `timezone="UTC"`). Market hours RTH
usati come riferimento: **13:30–20:00 UTC** (9:30–16:00 ET). Ambiente: **paper trading**, confermato
da `portfolio_monitor_snapshots` (`broker_environment='paper'`, `mode='paper'`,
`source='alpaca_paper'` su tutte le 82 righe del giorno). Motore di esecuzione:
`config/trading.yaml.execution.engine=portfolio` (versione del file attiva quel giorno, commit
`91afa8609` dell'11/08) → solo `portfolio-cycle` invia ordini.

> **Nota di processo**: `docs/evidence/findings.json` conteneva già, prima di questa sessione, 11
> finding con un'occorrenza datata 2026-08-21 che citano `FORENSIC_DAILY_REPORT_2026-08-21.md` come
> fonte — il file non esisteva mai su disco. Questo report lo ricostruisce: i fatti già registrati
> sono stati riverificati indipendentemente sul DB (le cifre coincidono in tutti i casi controllati)
> e non sono stati duplicati nel ledger; sono state aggiunte solo due occorrenze genuinamente nuove
> (F-021, F-030) trovate durante questa sessione. Nessun'altra modifica a `findings.json` oltre
> l'append di queste due occorrenze.

## 1. Executive summary

Giornata a basso traffico decisionale: 184 news ingerite (2 sole fonti attive), 368 chiamate LLM,
583 righe `execution_decisions`, ma solo **2 esiti non-skip**: 1 BUY (HOOD, S4, 17:07 UTC) e 1 SELL
da `sentiment_reversal` (INTC, S4, 16:37 UTC). Nessun'altra posizione aperta/chiusa. NAV
+$288.06 (+0.26%), drawdown corrente max 0.57%, gross exposure max 33.4% (limite 50%) — nessun
circuit breaker toccato. Paper trading confermato su tutte le 82 istantanee del monitor.

Il difetto più rilevante del giorno è strutturale e già noto (F-020, ricorrenza in peggioramento):
33% delle news `gdelt_gkg`/`org_lookup` (61/184) sono attribuite a MS/GS/DB per un boilerplate
"la banca X dice" senza che l'articolo le riguardi — **la correzione (#243, commit `b7102aad`) è
stata deployata il giorno DOPO**, il 2026-08-22. Nessun ordine è nato da queste righe (mai sopra
gate 0.30). Un secondo difetto (F-003, già noto) genera un ALERT CRITICAL-looking spurio a fine
giornata: "drawdown 17.8%" contro uno 0.46% reale, causato da un mismatch fra `combined_drawdown` e
`per_strategy_metrics.portfolio.drawdown` in `risk_reports`. L'unico BUY e l'unico SELL della
giornata sono entrambi funzionalmente corretti e ben motivati (DK-CoT coerente col prezzo). Due
gap strutturali nuovi sono stati misurati e agganciati a finding esistenti: 37-41 minuti di
pipeline "stale" all'apertura (F-021) e un ingresso HOOD che cattura solo lo 0.29% di un titolo
che ha fatto +13.7% perché il segnale arriva al 95.5% del movimento già avvenuto (F-030).

Dati non verificabili per questa data: log container (retention dal 2026-09-04, la giornata non è
più coperta), `performance_metrics` (tabella vuota da sempre), stato/uptime di Ollama (nessuna
telemetria diretta di trasporto — F-086), storico ordini Alpaca (fuori perimetro read-only di
questa sessione).

## 2. Verdict finale

**OK con warning.**

Nessuna anomalia ha prodotto un ordine sbagliato, un trade su ticker errato o una violazione di
risk limit. I due difetti di correttezza rilevati (F-020, F-003) sono entrambi già noti,
già in remediation (F-020 corretto il giorno dopo) o di sola osservabilità (F-003, alert spurio
senza conseguenze operative osservate). Il downgrade da "OK" a "OK con warning" è dovuto al volume
e alla persistenza di difetti di *osservabilità* (telemetria fuorviante F-014/F-015, gate
d'ingresso che erode segnali forti F-009, overwrite di segnali F-023, eligible-rate asimmetrico
F-010) che rendono più difficile fidarsi delle metriche aggregate derivate da questa giornata senza
le correzioni già proposte nei finding citati.

## 3. Timeline del 2026-08-21 (UTC)

| Ora | Componente | Evento |
|---|---|---|
| 13:30:00 | Portfolio monitor | Apertura RTH. `portfolio_monitor_snapshots`: nav=110.051,78; degradations=WARNING su `signal` e `portfolio_cycle` ("Expected activity is stale") — nessun ciclo/segnale ancora girato quel mattino. |
| 13:30–13:55 | Pipeline | Nessuna news, nessun ciclo. Il monitor continua a segnalare stale su entrambi i componenti (5 snapshot consecutivi). |
| 14:00:37 | Ingest | Primo articolo `alpaca_benzinga` (`news_log` min `created_at`). Degradation `signal` si libera alle 14:01. |
| 14:00:00–14:15:00 | Ingest `gdelt_gkg` | Primi articoli GDELT (published_at min 12:31 UTC, quindi l'articolo esisteva prima di essere ingerito — normale lag di fonte, non timestamp futuro). |
| 14:07:00.577 | Portfolio cycle #1078 | Primo ciclo `["S1","S4"]`, orders_count=5 (candidati, non invii — F-014), constraints_fired=[]. Degradation `portfolio_cycle` si libera. |
| 14:07:13.908 | Execution | IWM/QQQ SKIP_STALE (segnali di 19.4h/19.9h, età > max_age 4h) — decadimento normale di segnali overnight. |
| 14:16:24 → 14:16:26 | Signal (TSLA) | Segnale -0.360 (recall veicoli Cina) sovrascritto 2s dopo da +0.013 (fanout SpaceX/Nvidia, non su TSLA) — F-023, nessun impatto su ordine. |
| 14:37–19:37 | Portfolio cycle | 23 cicli aggiuntivi ogni 15 min, cadenza regolare, nessun buco. |
| 16:30:10 | Signal (INTC) | Score -0.419 (glm -0.7/gpt-oss -0.3, entrambi eligible) su "Intel $20B equity offering... AI chip competition pressure" — bear case coerente. |
| 16:37:00.595 | Execution/Trade | **SELL INTC** — `sentiment_reversal: score -0.419 < threshold -0.35`. Chiude trade id 702 (S4, aperto 08-12), qty 0.0349, net_pnl -$1.07. `open_positions` 49→48. |
| 17:00:25 | Signal (HOOD) | Score +0.372 ("Why Is Robinhood Stock Surging Friday?", articolo dedicato non-fanout). |
| 17:07:00.593 | Execution/Trade | **BUY HOOD** — score(peso)=2.0%, signal_score +0.447 (ensemble glm-5.2+gpt-oss, "White House crypto policy... direct positive for Robinhood"). entry $107.815, notional $1.869,37. `open_positions` 48→49. |
| 17:22–18:52 | Execution | 7 righe SKIP_PYRAMIDING (AVGO, AMD, NFLX, MU, XOM, HOOD ×1) — anti-pyramiding P0-05 corretto: blocca re-buy su posizioni già a libro. |
| 17:07:14.077 | Execution (TXN) | SKIP_FALLBACK: single-model (solo gpt-oss, score 0.000 conf 0.40) escluso dal ranking per #108 — comportamento corretto. |
| 19:52:15.940 | Execution | Ultima riga `execution_decisions` del giorno. |
| 19:52:00.555 | Portfolio cycle #1101 | Ultimo ciclo del giorno (24° dalle 14:07). Nessuna riga oltre le 19:52 — vedi F-021 sull'ambiguità di cosa succeda dopo. |
| 20:00:00 | Portfolio monitor | Chiusura RTH: nav 110.131,84 (+$288.06 vs prev close), open_positions 49, gross_exposure 33.4%, unrealized_pnl $1.309,41. |
| 22:30:01 | Risk report | Unica riga `risk_reports` del giorno: ALERT spurio "Strategy portfolio drawdown 17.8% exceeds 10%" — F-003, incoerente col monitor (0.46%). |

## 4. Tabella news ingest

| Fonte | Righe | extraction_method | Finestra oraria | Note |
|---|---|---|---|---|
| gdelt_gkg | 94 | org_lookup | 14:00–19:15 | 34 righe MS, 17 GS, 10 DB attribuite a terzi (F-020) |
| alpaca_benzinga | 90 | source_metadata | 14:00–19:45 | — |
| **Totale** | **184** | — | 14:00–19:45 | Nessun articolo prima delle 14:00 né dopo le 19:45 |

`ingestion_stats_daily`: gdelt_gkg fetched=1977, queued=127, duplicates=10, discarded_no_ticker=1852
(94% degli articoli GDELT grezzi non ha alcun match ticker — normale, molte notizie generiche);
alpaca_benzinga fetched=673, queued=375, duplicates=3356 (4.99× fetched — F-007, spiegato da
content_hash condivisi fra fino a 9 ticker sullo stesso articolo macro, non un contatore rotto).

Nessun timestamp futuro (`published_at` max 17:53:50, tutti ≤ `created_at`). Nessuna news fuori
mercato nel senso di post-20:00/pre-13:30 nel giorno stesso (fascia di ingest 14:00–19:45,
interamente dentro RTH). Copertura watchlist: 43/96 simboli (45%) a zero righe — F-001. Duplicati
inter-provider: nessun overlap diretto osservato fra gdelt_gkg e alpaca_benzinga sullo stesso
evento nel campione controllato.

**Tabella per ticker (top 10 per numero di righe)**

| Ticker | Righe | Note |
|---|---|---|
| MS | 34 | 34/34 non pertinenti (F-020) |
| GS | 17 | 17/17 non pertinenti (F-020) |
| DB | 10 | 10/10 non pertinenti (F-020) |
| MU | 7 | — |
| TSM | 5 | — |
| AMZN | 6 | — |
| GOOGL | 6 | — |
| MSFT | 6 | — |
| NVDA | 6 | — |
| QQQ / SPY | 5 / 5 | — |

**Top news per impatto sul segnale** (per |score| finale in `sentiment_signals`):

| Ticker | Score | Articolo | Esito |
|---|---|---|---|
| SPCX | +0.640 | (fallback FinBERT) | sotto gate 0.30? No — non tradabile (non in watchlist esecutiva effettiva quel giorno) |
| RIO | +0.560 | (fallback) | posizione legacy già detenuta |
| MU | +0.503 | dedicato | SKIP_PYRAMIDING (già a libro dal 07-28) |
| AMD | +0.433 | dedicato | SKIP_PYRAMIDING (già a libro dal 07-14) |
| **INTC** | **-0.419** | "$20B equity offering... AI chip pressure" | **SELL sentiment_reversal** |
| SPY | +0.381 | dedicato | non tradabile direttamente da S4 |
| **HOOD** | **+0.372 / +0.447** | "Why Is Robinhood Stock Surging" / crypto policy | **BUY** |

**Problemi trovati**: F-020 (ticker resolution errata, 33% delle righe gdelt), F-007 (contatore
duplicati apparentemente incoerente ma spiegato), F-001 (bassa copertura watchlist). **Confidenza
dell'analisi**: alta — tutte le cifre sono lette direttamente da `news_log`/`sentiment_signals`,
non stimate.

## 5. Tabella performance modelli LLM

| Modello | Risposte | Eligible | % eligible | Polarity media | Confidence media | Min/Max polarity |
|---|---|---|---|---|---|---|
| glm-5.2:cloud | 184 | 31 | 16.85% | +0.055 | 0.256 | -0.70 / +0.80 |
| gpt-oss:20b-cloud | 184 | 31 | 16.85% | +0.036 | 0.383 | -0.45 / +0.75 |

Entrambi i modelli sono chiamati su **tutte** le 184 news (nessun modello saltato per errore/timeout
osservabile nei dati persistiti — non ci sono righe mancanti rispetto a `news_log`). `fallback_used`
in `sentiment_signals`: 53/184 (28.8%), distribuito abbastanza uniformemente nell'arco della
giornata (7/37 alle 14h, 5/23 alle 15h, 13/37 alle 16h, 13/37 alle 17h, 7/30 alle 18h, 8/20 alle
19h) — **nessuna finestra concentrata** che suggerisca un'interruzione discreta di Ollama; è
compatibile con la normale soglia di eligibilità (confidence < 0.4) piuttosto che con un outage.
Non verificabile in modo diretto: `finbert_fallback_events` (tabella runtime, deploy 2026-09-10,
non esisteva ancora) e i log worker-inference (non retenuti).

`ensemble_std` medio 0.037, massimo 0.318 (SPY, MU, INTC, HOOD, AMAT fra i più alti) — coerente con
la formula post-eleggibilità nota per essere disallineata dal disaccordo reale (F-054, difetto
misurato ma con primo avvistamento 2026-08-27, quindi non ancora osservato/corretto a questa data
— non ripetuto come occorrenza qui perché fuori dal perimetro di questa giornata specifica; il dato
grezzo del 08-21 non è stato riverificato retroattivamente sotto quella lente).

**Disaccordo forte** (spread polarity ≥ 0.5, entrambi eligible): INTC (-0.7/-0.3, stesso segno,
score -0.419), nessun caso di segni opposti fra i top-|score| controllati manualmente oltre TSLA
(-0.36 vs quasi-zero, ma sovrascritto — F-023). **Dominanza single-model**: 53/184 righe (28.8%),
50 gpt-oss-only + 3 glm-only.

**Verifica funzionale**: output LLM validato prima del signal store — sì, schema strutturato
persistito coerentemente (nessun campo mancante osservato nel campione ispezionato). L'ensemble
gestisce varianza alta solo quando *entrambi* i modelli sono eligible (F-010, F-054 — limite noto,
non specifico di questa data). News duplicate non pesano più volte: `sentiment_signals` ha 184 righe
= 184 righe `news_log` distinte (1:1), nessun fan-out a livello di persistenza. La stessa news può
generare segnali su più ticker se l'articolo è multi-entità (fan-out legittimo, F-012, 55.6% della
giornata secondo `aggregati.cause_del_giorno` del dossier). Confidence bassa riduce il peso: sì, la
formula `score = polarity × confidence` è quella descritta in CLAUDE.md ed è quella osservata nei
dati (es. HOOD score 0.075 conf bassa → sotto gate, score 0.447 conf alta → sopra gate). Modelli
chiamati offline/background: confermato, nessuna chiamata LLM sincrona nel path di esecuzione
(`worker-inference`, coda `inference`, separata da `portfolio-cycle`). Rischio hallucination diretto
in decisione: mitigato dal gate 0.30 + DK-CoT reasoning testuale leggibile nella `reason` di ogni
decisione (entrambi i trade del giorno hanno rationale coerente col prezzo osservato).

## 6. Tabella segnali finali per ticker (estratto, segnali rilevanti)

| Ticker | Score finale | Confidence | Ensemble std | Fallback | Esito decisionale |
|---|---|---|---|---|---|
| HOOD | +0.447 (17:00) | 0.625 | 0.283 | No | BUY |
| INTC | -0.419 (16:30) | 0.75 | 0.283 | No | SELL (reversal) |
| SPCX | +0.640 | 0.80 | 0 | Sì | non tradato |
| RIO | +0.560 | 0.80 | 0 | Sì | già a libro |
| MU | +0.503 | 0.70 | 0.035 | No | SKIP_PYRAMIDING |
| AMD | +0.433 | 0.70 | 0.035 | No | SKIP_PYRAMIDING |
| BABA | -0.315 (17:15) | — | — | No | SKIP_THRESHOLD (decay sotto 0.30 al ciclo 17:22 — F-009) |
| TSLA | +0.013 (sovrascrive -0.360) | — | 0.127 | No | nessun ordine (F-023) |
| MS/GS/DB | ≤ 0.24 in valore assoluto | — | — | misto | SKIP_THRESHOLD (mai rilevante — F-020) |

Soglia attiva tutto il giorno: **0.300** (`feedback:entry_threshold:S4` — stopgap del 2026-08-07,
non il valore 0.45 del ratchet, confermato testualmente su tutte le 571 righe SKIP_THRESHOLD).

## 7. Tabella ordini generati/eseguiti

| Timestamp decisione | Strategia | Ticker | Azione | Qty | Prezzo entry/exit | Stato | Rationale | Segnale | Risk check |
|---|---|---|---|---|---|---|---|---|---|
| 17:07:00 | S4 | HOOD | BUY | 17.3385 | $107.815395 | filled | Crypto policy positiva per Robinhood | +0.447 | notional $1.869 ≥ $100 min; stop-risk sizing applicato (stop_strategy=S4, stop_mode=fixed, d_init 5.2%) |
| 16:37:00 | S4 | INTC | SELL (sentiment_reversal) | 0.0349 | $90.034 | filled | $20B equity offering, pressione competitiva AI | -0.419 < -0.35 | nessun risk check dedicato (i reversal bypassano il combiner ordinario — comportamento noto, non anomalo per design) |

Nessun altro ordine **inviato** quel giorno. `portfolio_cycles.final_orders` elenca ~5 "ordini"
candidati per ciclo (24 cicli × 5 ≈ 120 righe JSON) su AMAT/MRVL/UNH/AVGO/NFLX/AMD/HOOD, con
quantità pressoché costanti (es. AMAT 3.8396 alle 14:07 → 3.8368 alle 17:07) — **non sono ordini
inviati**: `open_positions` resta 49 (48 nella finestra 16:40–17:05, per l'uscita INTC) per tutto il
giorno tranne il ±1 spiegato da HOOD/INTC, e `gross_exposure` salta esattamente di +0.0170 (≈
$1.869, il notional HOOD) alle 17:10 e di nient'altro per tutto il resto della giornata — prova
quantitativa indipendente che i 5 "ordini" per ciclo non producono fill ripetuti. Questo è
esattamente il meccanismo già descritto da **F-014** (telemetria `orders_count`/`final_orders`
= candidati del target portfolio, non ordini inviati): confermato, non una nuova anomalia.

## 8. Tabella PnL/rendimento

| Metrica | Valore | Fonte |
|---|---|---|
| NAV apertura (13:30) | $110.051,78 | portfolio_monitor_snapshots |
| NAV chiusura (20:00) | $110.131,84 | portfolio_monitor_snapshots |
| NAV change today (close) | +$288,06 (+0,26%) | portfolio_monitor_snapshots |
| Previous close equity | $109.843,78 | portfolio_monitor_snapshots |
| Unrealized P&L (13:30 → 20:00) | $1.226,97 → $1.309,41 | portfolio_monitor_snapshots |
| Realized P&L del giorno | **-$1,07** (solo trade INTC, id 702) | trades |
| Gross exposure (min/max) | 31.64% / 33.41% (limite 50%) | portfolio_monitor_snapshots |
| Drawdown corrente (min/max) | 0.45% / 0.57% (limite 5%) | portfolio_monitor_snapshots |
| Cash | $75.202,76 → $73.336,54 (dopo BUY HOOD) | portfolio_monitor_snapshots |
| Open positions | 49 (48 tra 16:40–17:05) | portfolio_monitor_snapshots |

PnL per ticker: solo INTC ha un realizzato (-$1,07, posizione S4 aperta il 07-08 e tenuta 214h45m).
HOOD non ha PnL realizzato (posizione ancora aperta a fine giornata), mtm_eod +$5,45 (0,29% del
notional) nonostante il titolo abbia chiuso +13,70% — vedi F-030. PnL per strategia: non
separabile in modo affidabile per le 11 posizioni legacy senza `stop_strategy` popolato (F-002),
fra cui GS (+3,73%), MS (+3,25%) e RIO (+3,06%), tre mover del giorno il cui P&L non è attribuibile
a S1 né a S4 per costruzione — contributo stimato al NAV: +$92,49 aggregato sulle 11 posizioni
(32% della variazione NAV del giorno), ma **non scomponibile per singola strategia**. Slippage
stimato: `trades.slippage_est` è una copia bit-per-bit di `cost_usd` (INTC: 0,6461655744586391 =
0,6461655744586391) — **non è una misura indipendente di execution quality** (F-015). Commissioni:
non separate da `cost_usd`/`cost_bps` nel modello di costo aggregato disponibile.

**Dati mancanti per il PnL**: `performance_metrics` è vuota (0 righe in tutta la tabella, non solo
per questo giorno) — nessun composite_ic/ICIR/drift_level calcolato per nessuna data. Query che
servirebbe per popolarla: verificare se il job che scrive `performance_metrics` sia mai stato
schedulato (fuori perimetro di questa sessione read-only).

## 9. Analisi correttezza buy/sell

**BUY generati solo quando consentito**: sì. L'unico BUY (HOOD) ha score sopra gate (0.447 > 0.30),
ha passato `ema_pass=true`, non era già a libro alla generazione del segnale (i due tentativi
precedenti alle 15:52/16:07 erano sotto soglia), e il tentativo successivo (18:52, score 0.352) è
stato correttamente bloccato da anti-pyramiding P0-05.

**SELL/exit generati correttamente**: sì. L'unico SELL (INTC) è un `sentiment_reversal` con score
-0.419, sotto la soglia -0.35, motivato da una notizia specifica e coerente (diluizione azionaria +
pressione competitiva). La posizione chiusa era di proprietà **S4** (`trades.stop_strategy='S4'`):
**questo è rilevante perché #182(a) — la correzione che impedisce a `sentiment_reversal` di
liquidare posizioni non-S4 — non era ancora deployata il 08-21** (deroga registrata il 2026-08-25 in
`OBSERVATION_CHARTER.md`, deploy successivo). Il rischio strutturale era quindi presente tutto il
giorno, ma **non si è manifestato**: l'unico reversal della giornata ha chiuso una posizione propria
di S4, non una posizione S1/legacy. Nessun caso di "SELL con sentiment positivo" (bug A5): il segno
del segnale (-0.419) è coerente con un'azione SELL.

**Stop-loss**: nessuna riga con `exit_reason='stop_loss'` — atteso, `risk.stop_loss: 0.0` disattiva
il controllo dal 2026-07-14 (`docs/exit_mechanism_labels.md`); resta solo la telemetria shadow
(`stop_shadow_log`, 1174 righe quel giorno, coerente con ~49 posizioni × 24 cicli). **Signal flip**:
rispettato (nessun BUY→SELL immediato sullo stesso simbolo). **Max holding days / rebalance band**:
`rebalanced_strategies` è `[]` su tutte le 24 righe — nessun rebalance S1 innescato, coerente con la
cadenza MONTHLY dichiarata e con la correzione #185 (deployata 2026-08-06, quindi attiva). **Niente
ordini duplicati**: confermato dalla stabilità di `open_positions`/`gross_exposure` (§7). **Niente
ordini contrari ravvicinati sullo stesso simbolo**: HOOD ha solo BUY quel giorno, INTC solo SELL.
**Niente ordini su ticker non consentiti**: entrambi i ticker tradati sono in watchlist. **Niente
ordini fuori orario**: entrambi dentro 13:30–20:00 UTC (16:37 e 17:07). **Niente trade su dati
stale**: i segnali usati (INTC generato 16:30, usato 16:37; HOOD generato 17:00, usato 17:07) sono
entrambi freschi (<10 min). **Niente trade su LLM output non valido**: entrambi i segnali hanno
`eligible=true` su almeno un contributore con reasoning strutturato leggibile. **Circuit breaker**:
mai vicino ai limiti (gross 33.4%/50%, drawdown 0.57%/5%). **Paper/live coerente**: confermato paper
su tutte le 82 istantanee. **Idempotenza Celery**: non direttamente testabile (nessun retry
osservato nei dati persistiti quel giorno), ma la costanza di `open_positions` attraverso 24 cicli
di ricalcolo del target portfolio è evidenza indiretta che il layer di idempotenza/delta-vs-holdings
ha impedito invii ripetuti (F-014).

**Avvertenza `exit_mechanism` (#184)**: nessuna riga `execution_decisions` del 08-21 ha
`exit_mechanism` valorizzato con `portfolio_sell` (l'unica uscita è `sentiment_reversal`, che non
passa dal classificatore S4 per definizione — vedi `docs/exit_mechanism_labels.md`). Non ci sono
quindi righe da questa data la cui etichetta `expired`/`whipsaw` vada letta come stima per età
anziché come misura osservata: il tema #184 non si applica a questa giornata specifica.

## 10. Anomalie trovate

### [DAY-822] risk_reports: ALERT drawdown 17.8% spurio contro drawdown reale 0.46%

* Tipo: Bug (ricorrenza — F-003)
* Area: Risk
* Evidenza:
  * tabella: `risk_reports` id=70; `portfolio_monitor_snapshots` (ultimo snapshot 20:00)
  * timestamp: 2026-08-21 22:30:01 UTC
  * snippet: `combined_drawdown=0.012429` vs `per_strategy_metrics->portfolio->drawdown=0.1775475695171766`; `alerts=[{"level":"ALERT","message":"Strategy portfolio drawdown 17.8% exceeds 10%","strategy_id":"portfolio"}]`; confronto: `portfolio_monitor_snapshots` (20:00:00) `current_drawdown=0.004648`
* Descrizione: il campo usato per generare l'ALERT (`per_strategy_metrics.portfolio.drawdown`, 17.75%) diverge di un ordine di grandezza dal drawdown realmente osservato dal monitor operativo (0.46%) e dal campo "gemello" nello stesso record (`combined_drawdown`, 1.24%). L'alert è quindi un falso allarme CRITICAL-looking generato da un bug di calcolo, non da una condizione di rischio reale.
* Impatto: rischio di allarme ignorato per abitudine (alert fatigue) o, all'opposto, intervento operatore non necessario se qualcuno reagisse al testo dell'alert senza incrociarlo col monitor.
* Severità: Medium
* Confidenza: High
* Azione consigliata: ticket per audit del calcolo `per_strategy_metrics.portfolio.drawdown` in `risk_reports` — è un difetto di correttezza dello strumento di misura (rientra nel perimetro di esenzione dal freeze: se l'alert mente, ogni giorno osservato da qui al 28/09 produce un allarme non affidabile).
* Test/monitor consigliato: test di coerenza automatico `combined_drawdown ≈ per_strategy_metrics.portfolio.drawdown` (tolleranza dichiarata) prima di emettere un alert di livello ALERT.

### [DAY-001] org_lookup attribuisce a MS/GS/DB articoli su società estranee (33% delle news gdelt)

* Tipo: Bug (ricorrenza in peggioramento — F-020; **corretto il giorno dopo**)
* Area: News / Data
* Evidenza:
  * tabella: `news_log` (source='gdelt_gkg', extraction_method='org_lookup')
  * timestamp: tutto il 2026-08-21
  * snippet: MS 34 righe / GS 17 / DB 10 = 61/184 (33%); titoli campione: "TrinityBridge Ltd Takes Position in Honeywell Aerospace $HONA" → MS; "OVERSEA CHINESE BANKING Corp Ltd Takes... in ServiceNow" → MS; nessuno di questi articoli menziona Morgan Stanley/Goldman Sachs/Deutsche Bank
* Descrizione: `_org_names_supported_by_article` (il filtro che richiede evidenza testuale dell'org nel titolo/corpo prima di risolvere un ticker) è stato introdotto il 2026-08-22 (`git log -S`, commit `b7102aad`, "fix: richiedi evidenza testuale per org_lookup", issue #243). Il 08-21 questo filtro **non esisteva**: qualunque organizzazione elencata da GDELT nei metadati del documento sorgente (incluse menzioni secondarie come "la banca X dice") veniva risolta in un ticker, indipendentemente dal fatto che comparisse nel titolo/corpo effettivamente persistito.
* Impatto misurato: nessun ordine è nato da queste 61 righe (score massimo in valore assoluto 0.24, sotto gate 0.30). Impatto strutturale: 61 chiamate LLM sprecate su contenuto non pertinente al ticker dichiarato, rumore nella copertura apparente della watchlist (F-001), rischio strutturale di falso positivo (il "worst case error" secondo CLAUDE.md) rimasto aperto fino al deploy del giorno successivo.
* Severità: Medium (nessun impatto monetario misurato oggi; il meccanismo è esattamente quello che CLAUDE.md classifica come il peggiore possibile, e la correzione è arrivata solo 24h dopo la giornata qui analizzata)
* Confidenza: High
* Azione consigliata: nessuna — fix già deployato il 2026-08-22 (`b7102aad`, issue #243). Verificare che il deploy abbia effettivamente azzerato il fenomeno nelle giornate successive (fuori perimetro di questo report).
* Test/monitor consigliato: monitor di regressione su `news_log.extraction_method='org_lookup'` che segnali quando la quota di righe attribuite a un singolo ticker bancario supera una soglia storica.

### [DAY-002] Un articolo debole (score 0.075) precede di 55 minuti quello che sblocca il BUY: il gate erode segnali forti su mover (BABA)

* Tipo: Alpha miss (ricorrenza — F-009)
* Area: Signal
* Evidenza:
  * tabella: `execution_decisions` (symbol='BABA'), `sentiment_signals`
  * timestamp: segnale 17:15 (score -0.315), decisioni SKIP_THRESHOLD 17:22-17:52
  * snippet: "score 0.252... < feedback threshold 0.300" (decadimento fra generazione e primo ciclo utile)
* Descrizione: il segnale su BABA (-8.57% il mover più forte del giorno) nasce sopra soglia (-0.315) ma decade sotto (-0.252 in valore assoluto) prima del primo ciclo di controllo per effetto del decay/velocity applicato dal combiner.
* Impatto: nullo sul money path (book long-only, BABA non detenuto — un segnale short non sarebbe comunque stato eseguibile).
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna nuova — comportamento già registrato, la remediation (se ammessa) è taratura e resta congelata fino al 28/09 per `OBSERVATION_CHARTER.md`.
* Test/monitor consigliato: nessuno aggiuntivo oltre quanto già tracciato da F-009.

### [DAY-003] Eligible rate asimmetrico: solo 16.85% delle risposte LLM entra nel calcolo di disaccordo/pesi

* Tipo: Bug (ricorrenza — F-010)
* Area: LLM
* Evidenza:
  * tabella: `llm_responses`
  * timestamp: tutto il giorno
  * snippet: eligible=true su 31/184 per entrambi i modelli; 53/184 segnali `fallback_used=true`
* Descrizione: il floor asimmetrico di eleggibilità (confidence ≥ 0.4) esclude la maggioranza delle risposte dal calcolo di ensemble_std e dal ribilanciamento LOO-ICIR, che quindi gira su un sottocampione non casuale ad alta confidenza.
* Impatto: nessun trade specifico attribuibile oggi; distorce i pesi `ensemble:weights:current` nel tempo.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna nuova (già tracciata).
* Test/monitor consigliato: nessuno aggiuntivo.

### [DAY-004] Overwrite di segnale a 2 secondi su TSLA

* Tipo: Bug (ricorrenza, nuovo minimo di intervallo — F-023)
* Area: Signal
* Evidenza: `sentiment_signals` symbol='TSLA', 14:16:24 (-0.360) e 14:16:26 (+0.013)
* Descrizione: S4 tiene solo l'ultimo segnale per simbolo; un articolo dedicato viene sovrascritto 2 secondi dopo da un fanout non pertinente.
* Impatto: nullo (nessuno dei due segnali era comunque utilizzabile per un ordine quel giorno).
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna nuova.
* Test/monitor consigliato: nessuno aggiuntivo.

### [DAY-005] `orders_count`/`final_orders` in `portfolio_cycles` non rappresentano ordini inviati

* Tipo: Bug di osservabilità (ricorrenza — F-014; ambiguità iniziale di questa sessione risolta con evidenza quantitativa indipendente)
* Area: Orders / Ops
* Evidenza: `portfolio_cycles` (24 righe, orders_count=5 costante); `portfolio_monitor_snapshots` (open_positions, gross_exposure)
* Descrizione: ogni ciclo (24 nel giorno) elenca ~5 `CombinedOrder` su un piccolo insieme di simboli (AMAT/MRVL/UNH/AVGO/NFLX/AMD/HOOD) con quantità quasi costanti, ma `open_positions` e `gross_exposure` si muovono solo in corrispondenza dei 2 trade realmente eseguiti (INTC, HOOD). `final_orders` rappresenta quindi il portafoglio-bersaglio ricalcolato ogni ciclo (candidati), non gli ordini effettivamente inviati al broker.
* Impatto: rischio di lettura errata della telemetria (un operatore che leggesse `orders_count=5×24=120` penserebbe a un giorno molto attivo, quando gli ordini reali sono 2). Non ho trovato un ledger locale che distingua esplicitamente "candidato" da "inviato" da "filled" — la prova che nulla di anomalo sia accaduto è indiretta (via NAV/exposure/open_positions), non diretta.
* Severità: Medium
* Confidenza: High (evidenza quantitativa incrociata su 3 serie indipendenti)
* Azione consigliata: nessuna nuova (F-014 già la tracica); suggerire nel ticket di F-014 di esporre esplicitamente un contatore "orders_submitted" distinto da "orders_candidate".
* Test/monitor consigliato: nessuno aggiuntivo oltre quanto già proposto per F-014.

### [DAY-006] `trades.slippage_est` è una copia esatta di `cost_usd`

* Tipo: Bug (ricorrenza esatta — F-015)
* Area: PnL
* Evidenza: `trades` id=702 (INTC): `cost_usd=0.6461655744586391`, `slippage_est=0.6461655744586391` (identici bit per bit)
* Descrizione: nessuna misura indipendente della qualità di esecuzione — lo slippage stimato è semplicemente una copia del costo di trading modellato.
* Impatto: nessuna capacità di distinguere costo modellato da slippage reale sul book.
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna nuova.
* Test/monitor consigliato: nessuno aggiuntivo.

### [DAY-007] `ingestion_stats_daily.duplicates` supera `fetched` per alpaca_benzinga

* Tipo: Osservazione (ricorrenza, spiegata — F-007)
* Area: Data
* Evidenza: `ingestion_stats_daily` 2026-08-21 alpaca_benzinga: fetched=673, duplicates=3356 (4.99×)
* Descrizione: il contatore è additivo cross-run (non un conteggio giornaliero puro) ed è spiegato da content_hash condivisi su articoli macro multi-ticker (fino a 9 ticker sullo stesso hash) — la deduplicazione stessa funziona correttamente (184 righe reali in news_log).
* Impatto: nessuno sul money path; possibile fraintendimento se il contatore viene letto come tasso di duplicazione per-articolo.
* Severità: Low
* Confidenza: Medium (spiegazione plausibile e coerente coi dati, ma il meccanismo esatto del contatore non è stato letto nel codice in questa sessione)
* Azione consigliata: nessuna nuova.
* Test/monitor consigliato: nessuno aggiuntivo.

### [DAY-008] 11 posizioni legacy senza attribuzione di strategia, 3 sono mover del giorno

* Tipo: Osservazione (ricorrenza — F-002)
* Area: PnL / Data
* Evidenza: `trades`/book con `stop_strategy` vuoto su BAC, GOOGL, GS, MS, PBR, RIO, ROKU, SPY, UBS, UNH, XLE (tutte entrate 2026-07-10)
* Descrizione: GS (+3.73%), MS (+3.25%), RIO (+3.06%) sono mover del giorno ma il loro P&L non è attribuibile a S1 né a S4; contributo aggregato stimato +$92.49 al NAV (32% della variazione del giorno).
* Impatto: PnL per-strategia sottostimato/non ricostruibile per queste 11 posizioni.
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna nuova.
* Test/monitor consigliato: nessuno aggiuntivo.

### [DAY-009] Copertura news bassa sulla watchlist

* Tipo: Osservazione (ricorrenza — F-001)
* Area: News
* Evidenza: 43/96 simboli (45%) a zero righe in `news_log`; PLTR (+3.44%) e F (+3.00%) sono miss NO_NEWS puri
* Descrizione: coerente con la banda storica 38-57% osservata dal 07-31.
* Impatto: costo congetturale stimato $141.68 (size S4 tipica $2200 sul return pieno, dal dossier `opportunity_v2`).
* Severità: Low
* Confidenza: Medium (congetturale)
* Azione consigliata: nessuna nuova.
* Test/monitor consigliato: nessuno aggiuntivo.

### [DAY-011] Buco di pipeline a inizio seduta: 30-37 minuti senza segnali né cicli

* Tipo: Bug (ricorrenza — F-021, nuova occorrenza aggiunta al ledger in questa sessione)
* Area: Ops
* Evidenza:
  * tabella: `portfolio_monitor_snapshots.degradations`
  * timestamp: 13:30:00–14:05:00 UTC
  * snippet: `[{"reason":"Expected signal activity is stale","severity":"warning","component":"signal"},{"reason":"Expected portfolio_cycle activity is stale","severity":"warning","component":"portfolio_cycle"}]` presente su ogni snapshot dalle 13:30 alle 13:55; `portfolio_cycle` resta in warning fino alle 14:05
* Descrizione: il crontab (`celery_app.py`, commit attivo `a4cb0ec7`) usa ore UTC fisse (`hour="14-21"`) non consapevoli del DST: apertura RTH 13:30 UTC, primo `sentiment_worker` alle 14:00 (30 min dopo), primo `portfolio-cycle` alle 14:07 (37 min dopo). Il monitor di salute della pipeline se ne accorge da solo e lo marca WARNING, confermando indipendentemente il meccanismo già descritto da F-021 (non solo dedotto dal crontab).
* Impatto: nessun articolo risulta arrivato/perso in quella finestra (news_log non ha righe prima delle 14:00, `news_queue_drops` è vuota tutto il giorno — tabella probabilmente non ancora popolata a questa data), quindi non verificabile se qualcosa di scorabile sia stato perso. Lato coda: **non verificato per questa giornata specifica** se la griglia produca 8 cicli sprecati dopo la chiusura (come misurato in altre occorrenze di F-021) — `portfolio_cycles`/`execution_decisions` cessano entrambi alle 19:52, non proseguono visibilmente fino a 21:45/21:52.
* Severità: Low
* Confidenza: High (sul buco di apertura, misurato direttamente); Low (sulla coda dopo chiusura, non verificabile per mancanza di log)
* Azione consigliata: nessuna nuova oltre quella già proposta su F-021 (rendere il crontab consapevole del calendario di mercato/DST) — è taratura di scheduling, non necessariamente correttezza; valutazione all'operatore se rientra nell'esenzione del freeze.
* Test/monitor consigliato: alert automatico se `degradations` resta WARNING su `portfolio_cycle` oltre N minuti dall'apertura dichiarata dal calendario Alpaca.

### [DAY-012] Ingresso HOOD cattura lo 0.29% di un titolo che ha fatto +13.70%: il segnale arriva al 95.5% del movimento già avvenuto

* Tipo: Osservazione (ricorrenza — F-030, nuova occorrenza aggiunta al ledger in questa sessione)
* Area: Signal / Orders
* Evidenza:
  * tabella: `docs/evidence/dossier/2026-08-21.json` → `ingressi[0]`; `mercato.rendimenti.HOOD`
  * timestamp: BUY 17:07:00
  * snippet: `quota_movimento_precedente_al_segnale=0.9552`, `entry_percentile=0.827`, `mtm_eod=5.4548`, `mercato.rendimenti.HOOD=0.1370`
* Descrizione: il primo segnale utile su HOOD (0.447, alle 17:00) arriva quando il titolo è già all'82.7° percentile del proprio range di sessione — il 95.5% del movimento della giornata era già avvenuto. Il book cattura solo $5.45 di mark-to-market su un notional di $1.869 (0.29%), contro un titolo che ha chiuso +13.70%. Un segnale precedente e più debole (0.075, alle 15:52/16:07) era sotto gate.
* Impatto: opportunity cost non stimato in dollari con rigore (nessun controfattuale "entrata a inizio sessione" calcolato dalla dossier per i nomi effettivamente tradati, solo per i miss candidates) — vedi nota metodologica nel ledger.
* Severità: Low (osservazione strutturale, non un errore di esecuzione: il sistema ha comprato appena il segnale ha superato gate, per design)
* Confidenza: High sui numeri misurati (quota, percentile, mtm); Low sulla stima di costo (non calcolata)
* Azione consigliata: nessuna nuova oltre quella già tracciata da F-030 (accelerare lo scoring rispetto alla pubblicazione della notizia è taratura, congelata al 28/09).
* Test/monitor consigliato: nessuno aggiuntivo oltre quanto già proposto per F-030.

## 11. False positive o aree risultate corrette

* **`score=0.02` sulla riga BUY HOOD non è un punteggio di sentiment sotto soglia**: è il *peso di
  portafoglio* (2.0% NAV) post-normalizzazione, non lo score LLM (che è `signal_score=0.447`,
  correttamente sopra gate). Un controllo automatico ingenuo su "score < 0.05 ha generato ordini"
  avrebbe segnalato un falso allarme qui — verificato leggendo `execution_decisions.reason`
  ("portfolio weight 2.0%").
* **`portfolio_cycles.final_orders` con ~5 ordini per ciclo × 24 cicli non è pyramiding/duplicazione**:
  confermato con tre serie indipendenti (`open_positions`, `gross_exposure`, `cash`) che nessun
  fill ripetuto è avvenuto — vedi [DAY-005].
* **`sentiment_reversal` su INTC non ha violato il confine di sleeve (#182)**: nonostante la
  correzione #182(a) non fosse ancora deployata quel giorno, l'unico reversal della giornata ha
  chiuso una posizione effettivamente di proprietà S4 — nessuna liquidazione impropria di posizioni
  altrui si è manifestata.
* **Anti-pyramiding P0-05 funziona come da design**: 7 tentativi di re-buy su posizioni già a
  libro (AVGO, AMD, NFLX, MU, XOM, HOOD) sono stati tutti correttamente bloccati con motivazione
  esplicita in `execution_decisions.reason`.
* **Nessun ordine su dati stale, nessun ordine con LLM output non valido, nessun trade da circuit
  breaker attivo**: tutte le verifiche di §9 sono passate.
* **Paper trading confermato senza ambiguità**: `broker_environment`, `mode` e `source` di
  `portfolio_monitor_snapshots` sono coerenti su tutte le 82 istantanee del giorno.
* **Soglia d'ingresso S4 stabile a 0.300 per tutta la giornata**: nessuna evidenza del ratchet
  automatico che l'aveva portata a 0.45 in altre finestre (#191).

## 12. Dati mancanti o non accessibili

* **Log container** (`logs/containers/*-2026-08-21.log`): non presenti — la retention osservata
  parte dal 2026-09-04 (17 giorni). Impatto: impossibile verificare direttamente errori/eccezioni
  non propagate ad alert, timing esatto delle chiamate Ollama, restart dei worker.
* **`performance_metrics`**: tabella vuota (0 righe totali, non solo per questa data) — nessun
  composite_ic/ICIR/psi/drift_level disponibile per nessuna giornata.
* **`finbert_fallback_events`**: non esisteva ancora (deploy 2026-09-10) — non verificabile quali
  componenti (titolo/corpo) FinBERT abbia effettivamente ricevuto sui 53 fallback del giorno; solo
  il flag aggregato `fallback_used` è disponibile.
* **`s4_intent_events` / `s4_lifecycle_events` / `s4_exit_policy_events`**: 0 righe — instrumentazione
  deployata il 2026-08-25 (migrazioni 050/051), non ancora popolata il 08-21. Il lifecycle
  dettagliato fino al confine broker non è ricostruibile con questa granularità per questa data.
* **`news_queue_drops`**: 0 righe — la tabella sembra non ancora popolata a questa data (le deroghe
  collegate, #432/#511, sono datate settembre); impossibile quantificare scarti di coda per
  staleness nella finestra di apertura.
* **Storico ordini/posizioni Alpaca**: non consultato — fuori dalle risorse autorizzate per questa
  sessione read-only (API locale, log host, DB Postgres). La ricostruzione di posizioni/PnL si basa
  interamente su `trades` + `portfolio_monitor_snapshots`.
* **API REST locale**: non supporta filtro per data storica (`?date=` ignorato, ritorna sempre le
  righe più recenti per `id` decrescente) — usata solo per verificare lo schema di risposta, non
  come fonte per la ricostruzione del 08-21 (sostituita da query SQL dirette, più precise).
* **Uptime/downtime Ollama**: nessuna telemetria diretta di trasporto (F-086, difetto noto e non
  specifico di questa data) — inferito indirettamente dalla distribuzione uniforme di
  `fallback_used` nell'arco della giornata (nessuna finestra concentrata), ma questa è
  un'inferenza, non una misura.

## 13. Raccomandazioni immediate

Nessuna raccomandazione di taratura (fuori perimetro per `OBSERVATION_CHARTER.md` fino al
2026-09-28). Le uniche azioni compatibili con l'esenzione "difetti di correttezza" sono quelle già
proposte nei finding citati (F-003 sul calcolo del drawdown in `risk_reports`, già segnalato più
volte). Nessuna nuova azione immediata oltre a quanto già in coda nei ticket dei finding esistenti.

## 14. Test o monitor da aggiungere

* Test di coerenza `combined_drawdown` vs `per_strategy_metrics.portfolio.drawdown` prima di
  emettere un `ALERT` (F-003).
* Contatore esplicito "orders_submitted" distinto da "orders_candidate" in `portfolio_cycles`
  (F-014).
* Alert su `degradations` che resta WARNING oltre N minuti dall'apertura dichiarata dal calendario
  Alpaca (F-021).
* Monitor di regressione sulla quota di righe `org_lookup` attribuite a un singolo ticker bancario
  (verifica indiretta che il fix #243 tenga nelle giornate successive — fuori perimetro di questo
  report).

## 15. Ticket tecnici suggeriti

Nessun ticket nuovo. Tutti i difetti di correttezza rilevati sono già tracciati (F-003, F-020 già
corretto, F-014, F-021, F-030) o sono osservazioni/alpha-miss già note (F-001, F-002, F-007, F-009,
F-010, F-012, F-015, F-023) senza remediation ammissibile prima del 28/09.

## 16. Stato sistema

* **Ollama up/down**: non misurabile direttamente per questa data (nessun log, nessuna tabella di
  trasporto attiva). Proxy indiretto: `fallback_used` 28.8% (53/184), distribuito uniformemente
  nelle 6 ore di attività (7,5,13,13,7,8 per fascia oraria) — **nessuna finestra concentrata che
  suggerisca un outage discreto**, ma questa è un'inferenza qualitativa, non una misura di uptime.
* **FinBERT fallback rate**: 53/184 segnali (28.8%) hanno `fallback_used=true`; su 583 righe
  `execution_decisions` totali, solo 1 (`SKIP_FALLBACK`, TXN) è stata esplicitamente esclusa dal
  ranking per fallback single-model — le altre righe fallback che non hanno raggiunto gate non sono
  distinguibili nel conteggio aggregato delle decisioni.
* **Worker restart events**: non verificabile (nessun log retenuto per questa data, nessuna tabella
  di stato worker interrogata in questa sessione).
