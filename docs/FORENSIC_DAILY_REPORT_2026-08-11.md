# Forensic Daily Report — 2026-08-11

Settima seduta del periodo di osservazione (inizio 2026-08-03, scadenza attesa 2026-09-28).
Timezone operativo: **UTC** — verificato in `src/workers/celery_app.py` (tutte le `crontab` sono in
UTC) e nel database (`SHOW timezone` → `UTC`, tutte le colonne temporali sono
`timestamp with time zone`). Nessuna ambiguità di fuso.

Sessione di mercato 2026-08-11: **13:30–20:00 UTC** (EDT). Il report distingue pre-market
(< 13:30), sessione (13:30–20:00), post-market (> 20:00) e batch giornalieri.

Fonti usate: PostgreSQL `alembic-postgres-1` (sola lettura), Redis `alembic-redis-1` (sola
lettura), `docs/evidence/dossier/2026-08-11.json`, `docs/ALPHA_MISS_REPORT_2026-08-11.md`, codice
sorgente. **Non usati** i log dei container (cancellati dal redeploy, vedi [DAY-013]) e le API REST
locali (token JWT scaduto, vedi §12).

Questo report **non propone tarature**: siamo dentro il periodo di sola osservazione
(`docs/evidence/OBSERVATION_CHARTER.md`). I ticket suggeriti in §15 sono limitati a difetti di
**correttezza** — quelli che, se non corretti, rendono sbagliata l'evidenza raccolta nelle prossime
settimane.

Findings già coperti da un'occorrenza 2026-08-11 scritta dall'analisi alpha-miss e qui solo citati
(nessuna seconda occorrenza, per non contare due volte la giornata verso le soglie di ricorrenza):
**F-001, F-002, F-010, F-012, F-020, F-024, F-030, F-031, F-032**.

---

## 1. Executive summary

La pipeline ha girato end-to-end senza interruzioni: 162 notizie ingerite da 2 fonti, 162 segnali
scorati, 321 risposte LLM (nessun timeout, nessun fallback FinBERT, budget $0,19), 24 cicli di
portafoglio, 564 righe di decisione, 4 ordini inviati al broker (2 BUY, 2 SELL), tutti riempiti,
tutti dentro l'orario di sessione, tutti in **paper**. Posizioni DB e broker riconciliate: 48 = 48.
Realizzato del giorno **−14,29 $**, NAV di chiusura **110.299,09 $** (−46,42 $).

Il difetto centrale della giornata è nuovo e riguarda il percorso di **uscita**. Entrambe le SELL
(SONY, HOOD) sono state emesse su posizioni il cui segnale il meccanismo FIX-D aveva
**esplicitamente ri-ammesso** in quel ciclo — e il sistema stesso scrive nella motivazione che «il
meccanismo che ha azzerato il peso non è registrato». La causa è identificata:
`src/strategies/s4/strategy.py:167-169` **riapplica** la stessa finestra di 4h che FIX-D aveva
appena derogato, quindi la preservazione è annullata un livello più a valle. Due posizioni su tre
sono state chiuse da un filtro duplicato, senza contro-segnale.

Secondo difetto strutturale, mai registrato prima: `regime_mult` (0,70 oggi) scala il **notional**
dell'ordine ma non il target del combiner, e il guard anti-pyramiding blocca ogni rabbocco — quindi
ogni posizione S4 resta permanentemente al **70% del peso obiettivo** e ogni ciclo successivo
riemette un ordine che non potrà mai passare (73 ordini target contro 4 inviati).

Terzo: la varianza d'ensemble non è mai un gate d'ingresso, e il segnale con il massimo disaccordo
della giornata (HOOD, `ensemble_std` 0,283 su score 0,360) è diventato uno dei due soli BUY.

Il freeze del ratchet ha tenuto: alle 18:30 il loop di loss-feedback si è attivato su S4
(«3 consecutive losses») e la soglia è rimasta a 0,30.

## 2. Verdict finale

**OK con warning.**

Il processo ha funzionato end-to-end e nessun ordine è stato emesso in violazione di un vincolo di
sicurezza (orario, modalità, duplicazione, idempotenza, riconciliazione). Le anomalie trovate sono
**di meccanismo e di auditabilità**, non di sicurezza: due uscite su due sono state decise da un
filtro duplicato che il sistema non sa attribuire, il dimensionamento S4 è cronicamente al 70% del
target, e la catena segnale→decisione resta non verificabile perché ogni BUY ha `signal_id` NULL.
Nessun elemento suggerisce che il libro sia stato messo a rischio; molti elementi suggeriscono che
l'**evidenza** raccolta in questi giorni sia meno interpretabile di quanto sembri.

---

## 3. Timeline del 2026-08-11 (UTC)

| ora | componente | evento | esito | fonte |
|---|---|---|---|---|
| 10:52 | ingestion (?) | riga `ingestion_stats_daily` source=`reuters`, fetched 24 / queued 24 | **fantasma**: zero righe in `news_log` | [DAY-010] |
| 13:30:00 | monitor | primo snapshot broker: NAV 110.436,74, 48 posizioni, cash 77.268,54 | ok | `portfolio_monitor_snapshots` |
| 13:30:01 | alerting | incidente **CRITICAL** «Ciclo di portafoglio in ritardo» + WARNING «Segnali sentiment in ritardo» | auto-risolti 14:02 / 14:08 | [DAY-011] |
| 13:30:44 | regime detector | regime `sideways`, multiplier **0,70**, VIX 14,9, due LLM concordi | ok (F-017 non si manifesta) | `regime:current` |
| 14:01:06 | alerting | incidente CRITICAL «Dati broker non aggiornati» | risolto 14:02 | `mobile_events` |
| 14:01:23 | ingest | prima fetch news della giornata (alpaca_benzinga) | 31 min dopo l'apertura | `llm_budget.created_at` |
| 14:01–14:02 | sentiment | primi segnali: HOOD +0,360 (ensemble), AVGO +0,330 (single-model) | HOOD → BUY; AVGO → **nessuna riga** | [DAY-006] |
| 14:07 | ciclo 886 | 13 decisioni: **BUY HOOD** (12,92 az. @ 94,18), 4 SKIP_FALLBACK, 1 SKIP_STALE (QQQ 19,9h) | ordine `e400189c` riempito | `execution_decisions`, `trades` 699 |
| 14:22 | ciclo 887 | **SELL SONY** (50,28 az. @ 23,71), motivo `[unknown]` | trade 695 chiuso, net −5,47 | [DAY-001] |
| 14:30 | sentiment | AMD +0,396, SOXX +0,251 | AMD → SKIP_PYRAMIDING 14:37 | `sentiment_signals` |
| 14:37–18:07 | cicli 888-902 | 15 cicli, **zero ordini**; 13 SKIP_PYRAMIDING su NOK/CSCO/SHEL/AMD/XLE/HOOD/IBM | i target riemessi ogni ciclo non passano mai | [DAY-002], [DAY-007] |
| 15:44 | news | *«Why Is Nokia Stock Surging on Tuesday?»* → NOK ensemble **+0,725** (16:00) | SKIP_PYRAMIDING (posizione S1 dal 07-14) | F-031, F-030 |
| 16:21 / 16:45 | news | CSCO +0,482 / SHEL +0,450 | SKIP_PYRAMIDING | F-031 |
| 18:07 | ciclo 902 | HOOD esce dai target weights (età segnale 4,1h > 4h) — 1° ciclo di isteresi | nessun ordine | `exit_persistence_cycles: 2` |
| 18:22 | ciclo 903 | **SELL HOOD** (12,92 az. @ 93,69), motivo `[unknown]` | trade 699 chiuso, net −8,82 | [DAY-001] |
| 18:30 | loss-feedback | trigger S4 «3 consecutive losses» (evidenza trade 699) | soglia **0,30 → 0,30**: il freeze del ratchet ha tenuto | `feedback:state:S4` |
| 19:00:52 | sentiment | IBM ensemble **+0,323** (deal AI NVIDIA da $240M) | → BUY | `sentiment_signals` 7331 |
| 19:07 | ciclo 906 | **BUY IBM** (5,067 az. @ 238,01), score registrato 0,388 (= 0,323 × 1,2 velocity) | ordine `6491c199` riempito | `trades` 700 |
| 19:22 | ciclo 907 | IBM SKIP_PYRAMIDING, score registrato 0,323 (**stesso segnale, valore diverso**) | vedi §11 | `execution_decisions` 9363 |
| 19:46 | ingest | ultima fetch news della giornata | 14 min prima della chiusura | `ingestion_stats_daily` |
| 19:52 | ciclo 909 | ultimo ciclo della sessione | nessun ordine | `portfolio_cycles` 909 |
| 20:00 | monitor | ultimo snapshot: NAV 110.299,09, −46,42 sulla giornata, 48 posizioni | ok | `portfolio_monitor_snapshots` |
| 22:30 | risk report | ALERT «drawdown 14,8% eccede 10%», `daily_pnl` −653,76 | **incoerente** con la giornata | [DAY-008] |

Cicli di portafoglio: **24**, dalle 14:07 alle 19:52, cadenza esatta 15 minuti, nessun buco,
nessun ciclo doppio, nessun ciclo fuori sessione.

---

## 4. Tabella news ingest

### Per fonte (`ingestion_stats_daily`, giorno 2026-08-11)

| fonte | fetched | queued | duplicates | scartate no_ticker | stale | parse_fail | righe in `news_log` | url distinti |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| alpaca_benzinga | 681 | 292 | **2.628** | 0 | 0 | 0 | 74 | 38 |
| gdelt_gkg | 1.772 | 133 | 44 | 1.625 | 0 | 0 | 88 | 71 |
| reuters | 24 | 24 | 0 | 6 | 0 | 0 | **0** | 0 |
| **totale** | **2.477** | **449** | **2.672** | **1.631** | **0** | **0** | **162** | **109** |

`duplicates` (2.628) supera `fetched` (681) di 3,9× su alpaca_benzinga → [DAY-009].
La riga `reuters` non ha alcun corrispettivo in `news_log` (zero righe con `source='reuters'` in
tutta la storia del DB) → [DAY-010].

Copertura temporale: `published_at` da 12:49:35 a 18:12:12 (benzinga) e da 14:00 a 18:15 (gdelt).
`created_at` da 14:01:23 a 19:46:09. **Zero notizie con timestamp futuro**, zero con
`discarded_reason` valorizzato, zero `content_hash` NULL.

Buco temporale: nessuna riga fra le 00:00 e le 14:01 e nessuna dopo le 19:46 — è la finestra beat
`hour="14-21"` in UTC fisso, non un guasto ([DAY-011]).

Latenza di ingestione (`created_at − published_at`): mediana **31,0 min**, media 45,9, min 8,9, max
115,6. Contro una finestra di entry-freshness `MAX_NEWS_AGE_HOURS=2h` la mediana consuma il 26% —
**nettamente meglio** dei ~75 min del 08-10 e dell'1h50 che ha generato F-019. Oggi F-019 non si
manifesta.

`news_queue_drops`: **185** scarti in coda (131 benzinga, 54 gdelt), tutti con `age_hours` fra 2,0
e ~3,5 — cioè scarti per anzianità, coerenti con la policy. Nessun retry, nessun failure silenzioso
rilevabile in tabella.

### Per ticker (top 15 di 47 distinti)

| ticker | righe | url distinti | extraction_method |
|---|---:|---:|---|
| **GS** | 25 | 25 | `org_lookup` |
| **MS** | 23 | 23 | `org_lookup` |
| **DB** | 7 | 7 | `org_lookup` |
| META | 6 | 6 | `source_metadata` |
| SPCX | 6 | 6 | `source_metadata` |
| **BRKB** | 6 | 6 | `org_lookup` |
| AMD | 5 | 5 | misto |
| GOOGL | 5 | 5 | `source_metadata` |
| MU | 5 | 5 | misto |
| NVDA | 5 | 5 | `source_metadata` |
| NVO | 5 | 5 | misto |
| SHEL | 4 | 4 | `org_lookup` |
| TSLA | 4 | 4 | `source_metadata` |
| AMZN | 4 | 4 | `source_metadata` |
| TSM | 4 | 4 | `org_lookup` |

GS + MS + DB = **55 righe su 162 (34%)** e nessuna riguarda quelle tre banche: è F-020, in
peggioramento rispetto al 30,1% del 08-10 (occorrenza già registrata dall'alpha-miss).
`BRKB` è la forma non canonica di BRK.B: F-032, **ancora in produzione** dopo il deploy di #226 —
la canonicalizzazione a monte esiste, `sanitize_ticker` a valle la annulla (occorrenza già
registrata).

Copertura watchlist: 46 dei 96 simboli hanno almeno una riga; **50 simboli (52%) a zero** — dentro
la banda 40-55 delle sei sedute precedenti (F-001, occorrenza già registrata).

### Fan-out: una notizia, molti ticker

162 righe da **109 url distinti**. L'articolo più moltiplicato,
*«Nvidia masterstroke to turn itself into an asset class…»* (benzinga), genera **14 righe** e quindi
14 punteggi su 14 ticker diversi; *«S&P500 eyes record highs…»* ne genera 6; due altri 4 ciascuno.
Complessivamente 26 articoli su 109 (24%) producono 79 delle 162 righe scorate (48,8%) — F-012,
occorrenza già registrata. **Le notizie duplicate non pesano più volte sullo stesso ticker** (una
riga per coppia url×ticker), ma la stessa notizia genera segnali indipendenti su ticker diversi.

### Top news per impatto sul segnale

| ora segnale | ticker | notizia | score | esito |
|---|---|---|---:|---|
| 16:00 | NOK | *Why Is Nokia Stock Surging on Tuesday?* | **+0,725** | SKIP_PYRAMIDING (F-031) |
| 16:45 | CSCO | earnings/AI | **+0,482** | SKIP_PYRAMIDING |
| 17:02 | SHEL | energia | **+0,450** | SKIP_PYRAMIDING |
| 14:30 | AMD | semis | **+0,396** | SKIP_PYRAMIDING |
| 14:01 | HOOD | espansione prodotto crypto UK | **+0,360** | **BUY 14:07 → SELL 18:22** |
| 14:01 | AVGO | — | **+0,330** (single-model) | **nessuna riga** ([DAY-006]) |
| 19:00 | IBM | deal AI NVIDIA $240M | **+0,323** | **BUY 19:07** |
| 18:01 | XLE | energia | +0,307 | SKIP_PYRAMIDING |

---

## 5. Tabella performance modelli LLM

| modello | richieste | polarity media | confidence media | min/max polarity | polarity = 0 | `eligible` |
|---|---:|---:|---:|---:|---:|---:|
| `gpt-oss:20b-cloud` | 162 | +0,050 | 0,353 | −0,300 / +0,700 | 109 (67%) | 20 (12%) |
| `glm-5.2:cloud` | 159 | +0,063 | 0,226 | −0,350 / +0,800 | 95 (60%) | 20 (13%) |

**Errori, timeout, refusal: 0 osservabili.** `glm` ha 159 risposte contro 162 di `gpt-oss` — 3
richieste in meno, non distinguibili da errori senza i log (§12). Nessun output invalido è arrivato
in tabella. **Latenza non misurata: non esiste una colonna di durata** in `llm_responses` (§12).

Composizione dei 162 segnali:

| `model_id` del segnale | n | fallback | score medio | confidence media | `ensemble_std` medio |
|---|---:|---:|---:|---:|---:|
| `ensemble:glm-5.2:cloud+gpt-oss:20b-cloud` | 118 | 0 | +0,034 | 0,262 | 0,038 |
| `single:gpt-oss:20b-cloud` | 39 | 39 | +0,026 | 0,496 | 0,000 |
| `single:glm-5.2:cloud` | 5 | 5 | +0,084 | 0,620 | 0,000 |

**Fallback rate 27% (44/162)** — nessuno su FinBERT: il ramo FinBERT non è stato usato nemmeno una
volta oggi, Ollama Cloud ha risposto sempre. Costo LLM giornaliero $0,187, budget non esaurito.

Distribuzione dello score: 74 dei 118 ensemble hanno `ensemble_std` = 0,00 (accordo perfetto,
tipicamente entrambi a polarity 0); solo 8 superano 0,15.

Disaccordo massimo della giornata:

| ticker | score | std | glm (pol/conf) | gpt-oss (pol/conf) | esito |
|---|---:|---:|---|---|---|
| **HOOD** | +0,360 | **0,283** | +0,70 / 0,80 | +0,30 / 0,40 | **BUY** ([DAY-003]) |
| SOXX | +0,251 | 0,247 | +0,25 / 0,50 | +0,60 / 0,70 | SKIP_THRESHOLD |
| TSM | −0,006 | 0,212 | +0,10 / 0,30 | −0,20 / 0,30 | segno opposto fra modelli |
| GOOGL | +0,228 | 0,212 | +0,50 / 0,60 | +0,20 / 0,60 | SKIP_THRESHOLD |
| GS | +0,039 | 0,212 | 0,00 / 0,15 | +0,30 / 0,30 | SKIP_THRESHOLD |
| IBM | +0,323 | 0,177 | +0,35 / 0,75 | +0,60 / 0,70 | **BUY** |

### Verifica funzionale

| domanda | risposta | evidenza |
|---|---|---|
| L'output LLM è validato prima del signal store? | **Sì, parzialmente**: parsing JSON strutturato, `polarity ∈ [-1,1]`, `confidence ∈ [0,1]` (`src/models/signals.py`); nessun output malformato in tabella | schema + dati |
| L'ensemble gestisce la varianza alta? | **No, non nel percorso d'ingresso**: `ensemble_std` è calcolato e persistito ma è letto solo da `src/performance/postmortem.py` (soglia 0,30) *dopo* una perdita. Nessun gate. | [DAY-003] |
| Le news duplicate pesano più volte? | **No** sullo stesso ticker; **sì** attraverso ticker diversi (fan-out, F-012) | §4 |
| La stessa news può generare segnali multipli? | Sì, uno per ticker taggato — l'articolo NVDA ne ha generati 14 | §4 |
| La confidence bassa riduce il peso? | **Sì**: `score = polarity × confidence`, verificato riga per riga (es. AVGO 0,55 × 0,60 = 0,33) | `llm_responses` vs `sentiment_signals` |
| I modelli sono chiamati offline/background? | **Sì**: solo dal worker `inference`, mai dentro il ciclo di trading; il ciclo legge `sentiment_signals` da Postgres | `celery_app.py`, `portfolio_scheduler.py` |
| Rischio che un'allucinazione entri in decisione? | **Sì, presente**: nessun supervisor agent, nessun gate di varianza, nessuna verifica RAG delle affermazioni quantitative. L'unica difesa è il gate a 0,30 sullo score. | [DAY-003] |

`llm_responses.eligible` resta incoerente: **98 dei 118** segnali ensemble hanno **zero** risposte
eleggibili (eppure l'ensemble è stato calcolato), e **36 dei 39** segnali «single-model» hanno in
realtà **due** risposte in tabella — il secondo modello ha risposto ed è stato escluso dal floor di
confidence. Esempio verificato, AVGO segnale 7186: `glm` polarity 0,00 conf 0,20 (escluso),
`gpt-oss` polarity 0,55 conf 0,60 (usato), entrambi `eligible=false`. È F-010, occorrenza 08-11
già registrata.

---

## 6. Tabella segnali finali per ticker

162 segnali su 47 simboli. Sopra il gate attivo (`feedback:entry_threshold:S4` = **0,30**):

| ticker | max score | conf | modello | ora | decisione | perché |
|---|---:|---:|---|---|---|---|
| NOK | **+0,605** (0,725 alle 16:07) | 0,80 | ensemble | 16:00 | SKIP_PYRAMIDING ×3 | già a libro (S1) dal 07-14 |
| CSCO | **+0,482** | 0,75 | ensemble | 16:45 | SKIP_PYRAMIDING ×2 | già a libro dal 07-15 |
| SHEL | **+0,450** | 0,75 | ensemble | 17:02 | SKIP_PYRAMIDING ×2 | già a libro dal 07-14 |
| AMD | **+0,396** | 0,60 | ensemble | 14:30 | SKIP_PYRAMIDING | già a libro dal 07-14 |
| **HOOD** | **+0,360** | 0,60 | ensemble | 14:01 | **BUY** 14:07 | libero → entrato |
| AVGO | **+0,330** | 0,60 | single (fallback) | 14:01 | **nessuna riga** | [DAY-006] |
| **IBM** | **+0,323** | 0,725 | ensemble | 19:00 | **BUY** 19:07 | libero → entrato |
| XLE | **+0,307** | 0,625 | ensemble | 18:01 | SKIP_PYRAMIDING ×3 | già a libro (legacy) dal 07-10 |

Sotto il gate, i più vicini: MS +0,278 (24 SKIP_THRESHOLD — righe `org_lookup` estranee),
SOXX +0,251, GOOGL +0,228, AMD residuo +0,172, NVDA +0,112, AMZN +0,102.

Distribuzione decisioni (564 righe, 46 simboli):

| decisione | n | note |
|---|---:|---|
| SKIP_THRESHOLD | 540 | di cui **311 con score esattamente 0,000** |
| SKIP_PYRAMIDING | 13 | **novità positiva**: la traccia c'è (issue #231), prima era muta |
| SKIP_FALLBACK | 6 | IWM ×2, MRVL, RIO, WDC, DIS |
| **SELL** | 2 | SONY, HOOD — entrambe `exit_mechanism = unknown` |
| **BUY** | 2 | HOOD, IBM |
| SKIP_STALE | 1 | QQQ, segnale 19,9h |

`audit_log`: 282 `SIGNAL_STALE_SKIP`, **5 `SIGNAL_DUPLICATE_SKIP`** (la guardia di idempotenza
P1-S4 ha funzionato), 2 `INSERT`.

---

## 7. Tabella ordini generati / eseguiti

### Ordini effettivamente inviati al broker (4)

| ts decisione | strat. | ticker | azione | qty | prezzo atteso | prezzo fill | stato | broker | rationale | segnale | risk check | anomalie |
|---|---|---|---|---:|---:|---:|---|---|---|---|---|---|
| 14:07:00 | S4 | HOOD | BUY | 12,917 | ~94,18 | **94,18** | filled | Alpaca **paper** | sentiment +0,360 ensemble, peso 2,0% | id 7185 (ma `signal_id` NULL nella riga) | regime_mult 0,70, gate 0,30, EMA pass, no-pyramiding, min-notional | qty = 70% del target (18,442) → [DAY-002]; `signal_id` NULL → [DAY-005]; segnale a massimo disaccordo → [DAY-003] |
| 14:22:00 | S4 | SONY | SELL | 50,281 | ~23,71 | **23,71** | filled | Alpaca paper | `[unknown]` peso 0%, meccanismo non registrato | nessuno | isteresi uscita 2 cicli | chiusura senza contro-segnale → [DAY-001] |
| 18:22:00 | S4 | HOOD | SELL | 12,917 | ~93,69 | **93,69** | filled | Alpaca paper | `[unknown]` peso 0%, meccanismo non registrato | nessuno | isteresi uscita 2 cicli | idem → [DAY-001] |
| 19:07:00 | S4 | IBM | BUY | 5,067 | ~238,01 | **238,01** | filled | Alpaca paper | sentiment +0,388 ensemble (= 0,323 × 1,2 velocity), peso 2,0% | id 7331 (ma `signal_id` NULL) | regime_mult 0,70, gate 0,30, EMA pass, min-notional | qty = 70% del target (7,240) → [DAY-002]; entrata a 53 min dalla chiusura |

Nessun ordine respinto, nessun ordine cancellato, nessun fill parziale non riconciliato, nessuno
stop-loss scattato (protettivo disattivato per decisione operatore, `stop_loss: 0.0`).

### Ordini target generati e mai inviati

`portfolio_cycles` del giorno: **24 cicli, 73 ordini nei `final_orders`, 4 inviati**. Il divario non
è rumore: HOOD compare come BUY in 13 cicli consecutivi, NOK in 9, CSCO in 8, SHEL in 7, XLE in 6,
IBM in 3 — sempre lo stesso rabbocco riemesso e sempre bloccato ([DAY-002], [DAY-007]).

---

## 8. Tabella PnL / rendimento

### Realizzato (posizioni chiuse il 2026-08-11)

| trade | ticker | strat. | ingresso | uscita | qty | prezzo in | prezzo out | gross | costo stimato | **net** |
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|
| 695 | SONY | S4 | 08-10 16:07 | 08-11 14:22 | 50,281 | 23,77 | 23,71 | −3,02 | 2,45 | **−5,47** |
| 699 | HOOD | S4 | 08-11 14:07 | 08-11 18:22 | 12,917 | 94,18 | 93,69 | −6,33 | 2,49 | **−8,82** |
| | | | | | | | | | **totale** | **−14,29** |

**Tutto il realizzato del giorno è S4.** Nessun trade S1 chiuso.
PnL da posizioni aperte prima del 08-11: −5,47 (SONY). PnL da posizioni aperte il 08-11: −8,82
(HOOD). Posizione aperta e non chiusa: IBM (trade 700, 5,067 az. @ 238,01, MTM a fine giornata
**+2,08**).

### Non realizzato / libro

| voce | valore | fonte |
|---|---:|---|
| NAV apertura (previous close equity) | 110.345,51 | `portfolio_monitor_snapshots` |
| NAV chiusura 20:00 | **110.299,09** | idem |
| variazione NAV del giorno | **−46,42** | idem |
| unrealized_pnl a chiusura | +1.153,25 | idem |
| esposizione lorda | 29,96% (limite 50%) | idem |
| drawdown corrente | 0,29% (limite 5%) | idem |
| posizioni aperte | 48 (DB: 48 ✓) | `trades` / snapshot |
| MTM del libro aperto (dossier) | −19,46 | dossier §aggregati |

Ricomposizione: realizzato −14,29 + MTM libro −19,46 = **−33,75** contro una variazione NAV di
**−46,42**. Residuo **−12,67**, non spiegato. Le due serie usano fonti di prezzo diverse (marks del
broker alle 20:00 contro close Alpaca `adjustment=all` del dossier) e la differenza è dell'ordine di
grandezza atteso; **non la attribuisco** in assenza di uno storico di marks intraday per posizione.

### Costi e slippage

| ticker | `cost_bps` | `cost_usd` | `slippage_est` |
|---|---:|---:|---:|
| SONY | 20,244 | 2,454 | **2,454** |
| HOOD | 20,247 | 2,493 | **2,493** |
| IBM | 20,246 | 2,442 | **2,442** |

`slippage_est` è **identico** a `cost_usd` su tutti e tre: la qualità di esecuzione non è misurata,
è ricopiata dal modello di costo ([DAY-012]). Il `cost_bps` di 20,24 su tutti e tre conferma che i
tre simboli cadono nel tier di default del modello di costo (F-034, sollevato il 08-10). In paper
non ci sono commissioni reali: questi numeri sono stime, non addebiti.

### PnL per strategia

| strategia | realizzato | note |
|---|---:|---|
| S4 | **−14,29** | 2 chiusure |
| S1 | 0,00 | nessuna chiusura |
| legacy (senza `stop_strategy`) | 0,00 | nessuna chiusura; 11 delle 48 posizioni restano non attribuibili (F-002) |

---

## 9. Analisi correttezza buy/sell

| controllo | esito | evidenza |
|---|---|---|
| BUY generati solo quando consentito | **OK** | 2 BUY, entrambi su segnale ensemble sopra 0,30, EMA pass, simbolo in watchlist, nessuna posizione aperta, `regime_mult` applicato |
| SELL/exit generati correttamente | **NO** | entrambe le SELL sono su posizioni il cui segnale FIX-D aveva ri-ammesso, e il sistema dichiara di non sapere perché il peso sia andato a 0 → [DAY-001] |
| Stop-loss rispettati | **N/A** | stop protettivo disattivato per decisione operatore (`config/trading.yaml:182`); `stop_shadow_log` 1.150 righe, shadow attivo; `stop_decisions` fermo al 07-14 (ramo `vol_scaled`, non in uso) |
| Signal flip rispettato | **N/A** | nessun flip di segno sopra soglia oggi |
| Max holding days rispettato | **OK formalmente, dubbio sostanzialmente** | S4 dichiara `max_signal_age_hours: 4` in tempo di parete; HOOD chiusa a 4,25h, SONY a 22,25h (overnight) → F-024 |
| Banda di rebalance rispettata | **NO** | non esiste banda fra gate d'ingresso (0,30) e uscita (peso 0): F-013. Oggi non ha prodotto churn perché nessun simbolo è rientrato dopo l'uscita |
| Ordini duplicati | **nessuno** | 4 ordini, 4 `order_id` distinti, nessuna coppia nello stesso minuto |
| Ordini contrari ravvicinati | **nessuno < 30 min** | HOOD BUY 14:07 → SELL 18:22 = 4h15 |
| Ordini su ticker non consentiti | **nessuno** | tutti in watchlist |
| Ordini fuori orario | **nessuno** | 14:07–19:07, dentro 13:30–20:00 |
| Trade su dati stale | **nessun BUY** | 1 SKIP_STALE (QQQ 19,9h) e 282 `SIGNAL_STALE_SKIP` nell'audit log; le due SELL invece **nascono** dalla staleness |
| Trade su output LLM non valido | **nessuno** | nessun output malformato; i 44 fallback single-model sono esclusi dal ranking BUY (#108) |
| Trade con circuit breaker attivo | **N/A** | `system:mode = paper`, nessun halt operatore, drawdown 0,29% contro limite 5% |
| Trade su strategia disabilitata | **nessuno** | `strategies_run = ["S1","S4"]` in tutti e 24 i cicli |
| Coerenza paper/live | **OK** | `broker_environment = paper` in tutti gli 84 snapshot, `system:mode = paper`, `execution.engine = portfolio` (solo `portfolio-cycle` invia ordini) |
| Idempotenza su retry Celery | **OK** | 5 `SIGNAL_DUPLICATE_SKIP` nell'audit log; nessun ordine duplicato |
| Riconciliazione ordini↔fill↔posizioni | **OK** | 2 BUY = 2 righe `trades` con `entry_order_id`; 2 SELL = 2 righe con `exit_order_id` e `exit_order_ids` popolato; 48 posizioni DB = 48 broker |

**Nota obbligatoria su `exit_mechanism` (#184).** Le due righe di uscita del 2026-08-11 sono
**post-fix** e portano l'etichetta `unknown`, che è la risposta onesta prevista dal design
(`src/portfolio/exit_classification.py`): la disposizione osservata era `STALE_PRESERVED` e il
classificatore rifiuta di consultare l'orologio. **Nessun conteggio di questo report deduce
`exit_mechanism` dall'età del segnale**, e nessuna riga pre-fix è stata interpretata.

### Pattern operativi richiesti

| pattern | esito |
|---|---|
| Roundtrip < 30 min | **nessuno** |
| BUY ripetuto > 3× senza SELL (pyramiding) | **nessuno inviato**: 13 tentativi bloccati da P0-05, tutti tracciati |
| **SELL con sentiment positivo (bug A5)** | **2 su 2**: SONY (ultimo score citato +0,431) e HOOD (+0,360). Non è il bug A5 classico (nessun segnale negativo è stato letto come SELL): è la conseguenza di [DAY-001] |
| `fallback_used=True` su tutti i simboli | **no**: 27% (44/162); Ollama up tutto il giorno |
| NO-ORDER (decisione creata, ordine non generato) | **sì, 69 volte**: 73 ordini target contro 4 inviati → [DAY-007] |
| Score < 0,05 che generano ordini | **nessuno** |
| Ordini identici nello stesso minuto | **nessuno** |

---

## 10. Anomalie trovate

### [DAY-001] Le due uscite del giorno sono decise da un filtro di staleness duplicato che annulla FIX-D

* **Tipo:** Bug
* **Area:** Signal / Orders
* **Evidenza:**
  * file/log/tabella: `execution_decisions` id 8866 e 9260; `src/workers/portfolio_scheduler.py:714`
    (`_preserve_stale_signals_for_open_positions`); **`src/strategies/s4/strategy.py:167-169`**;
    `config/trading.yaml:160` (`exit_persistence_cycles: 2`)
  * timestamp: 2026-08-11 14:22:09 (SONY) e 18:22:10 (HOOD)
  * snippet/query:
    ```sql
    SELECT symbol, decision, exit_mechanism, reason FROM execution_decisions
     WHERE created_at::date='2026-08-11' AND decision='SELL';
    -- "[unknown] S4 signal was stale but FIX-D re-admitted it this cycle — open
    --  position, no counter-signal — and the weight is 0 anyway: the mechanism that
    --  zeroed it is not recorded, so this exit is NOT a signal expiry, see #184"
    ```
    ```python
    # src/strategies/s4/strategy.py:167-169
    max_age = getattr(self._config, "max_signal_age_hours", 0) or 0
    if max_age > 0:
        df = df[df["generated_at"] >= ts - timedelta(hours=max_age)]
    ```
* **Descrizione:** lo scheduler applica il filtro dei 4h, poi FIX-D **ri-ammette** esplicitamente i
  segnali stale dei simboli con posizione aperta e senza contro-segnale, e passa il DataFrame alla
  strategia. `NewsDrivenTactical._signals_as_of` **riapplica la stessa finestra di 4h** sullo stesso
  DataFrame, eliminando di nuovo proprio le righe che FIX-D aveva salvato. Il ticker sparisce dai
  `target_weights`, il peso va a 0, l'isteresi di uscita conferma su 2 cicli e la posizione viene
  chiusa. Le età combaciano al minuto: SONY 19,6h (fuori dal primo ciclo del giorno, SELL al
  secondo), HOOD 4,3h (fuori alle 18:07, SELL alle 18:22). Il commento nel codice dichiara che il
  filtro serve alla **parità backtest/live** (QS-07) — ma nel live la parità la rompe, perché il
  live ha una deroga (FIX-D) che il backtest non ha.
* **Impatto:** 2 posizioni su 3 chiuse senza contro-segnale, per solo scorrere del tempo, con la
  telemetria che dichiara di non conoscere il meccanismo. FIX-D — introdotto proprio per non
  liquidare posizioni sane — è inerte sul percorso che conta. Ogni evidenza su «quanto dura una
  posizione S4» e «perché S4 esce» raccolta in questa finestra misura questo difetto, non la
  strategia.
* **Severità:** High
* **Confidenza:** High (meccanismo dedotto dal codice e da timestamp che combaciano; non ho eseguito
  una riproduzione live, che avrebbe richiesto di far girare il ciclo)
* **Azione consigliata:** ticket di correttezza — la finestra di freschezza deve essere applicata
  **una sola volta**, e il livello strategia deve rispettare la ri-ammissione decisa a monte
  (es. marcando le righe preservate con un flag che `_signals_as_of` onora). Nessuna taratura:
  il valore 4h resta congelato.
* **Test/monitor consigliato:** test che, dato un DataFrame contenente un segnale di 5h su un
  simbolo con posizione aperta e nessun contro-segnale, `NewsDrivenTactical.generate_orders` **non**
  emetta una SELL; monitor giornaliero che allerti se `exit_mechanism='unknown'` supera il 50% delle
  uscite.
* **Ledger:** **F-035 (nuovo)**

---

### [DAY-002] `regime_mult` scala il notional ma non il target: le posizioni S4 restano al 70% del peso obiettivo, per sempre

* **Tipo:** Bug
* **Area:** Orders / Risk
* **Evidenza:**
  * file/log/tabella: `src/workers/portfolio_scheduler.py:3914`; `portfolio_cycles` 886-909;
    `trades` 699 e 700; `regime:current`
  * timestamp: 2026-08-11 14:07 (HOOD) e 19:07 (IBM)
  * snippet/query:
    ```python
    notional = round(price * order.quantity * regime_mult, 2)   # riga 3914, regime_mult = 0.70
    ```
    ```
    HOOD: combiner chiede 18,4418 az. → eseguite 12,9174 (rapporto 0,7004)
    IBM : combiner chiede  7,2399 az. → eseguite  5,0672 (rapporto 0,6999)
    ```
* **Descrizione:** il combiner calcola `delta = target_qty − current_qty` a peso pieno; l'esecutore
  moltiplica il notional per `regime_mult` (0,70 nel regime `sideways` di oggi). La posizione si
  ferma quindi al 70% del target. Al ciclo successivo il combiner ricalcola lo stesso delta
  residuo e riemette l'ordine — ma il guard anti-pyramiding P0-05 blocca **ogni** BUY su un simbolo
  con posizione aperta, quindi il rabbocco non passerà mai. Verificato sui dati: HOOD BUY 14:07 →
  SKIP_PYRAMIDING 15:37 «già a libro dal 2026-08-11»; IBM BUY 19:07 → SKIP_PYRAMIDING 19:22, stessa
  formula. Lo scaling del notional è voluto (P0-09); il difetto è l'**interazione**: nessuno dei due
  meccanismi sa dell'altro.
* **Impatto:** la sleeve S4 opera stabilmente a ~1,4% di NAV per slot invece del 2% dichiarato, in
  ogni regime diverso da 1,0 — e il backtest, che non ha né lo scaling né il guard, misura un
  oggetto diverso. Genera inoltre il grosso dei 69 ordini target mai inviati. Sui due ingressi di
  oggi: 520,03 $ non allocati su HOOD e 517,20 $ su IBM.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** ticket di correttezza — applicare `regime_mult` al **target** (o consentire
  al guard P0-05 di distinguere un rabbocco verso il target da un vero pyramiding). Il valore di
  `regime_mult` non va toccato.
* **Test/monitor consigliato:** test che con `regime_mult=0.7` e target 2% la posizione converga al
  2% e non al 1,4%; monitor sul rapporto `ordini inviati / ordini target` per ciclo.
* **Ledger:** **F-038 (nuovo)**

---

### [DAY-003] La varianza d'ensemble non è mai un gate: il segnale a massimo disaccordo del giorno è diventato uno dei due BUY

* **Tipo:** Rischio
* **Area:** LLM / Signal
* **Evidenza:**
  * file/log/tabella: `sentiment_signals` id 7185 + `llm_responses`; `src/performance/postmortem.py:80`;
    `CLAUDE.md` §Hallucination Mitigation
  * timestamp: 2026-08-11 14:01:29 (segnale) → 14:07 (BUY)
  * snippet/query:
    ```sql
    SELECT s.symbol, s.score, s.ensemble_std, r.model_id, r.polarity, r.confidence
      FROM sentiment_signals s JOIN llm_responses r ON r.signal_id=s.id WHERE s.id=7185;
    -- HOOD score 0.360  ensemble_std 0.283
    --   glm-5.2:cloud     polarity 0.70  confidence 0.80
    --   gpt-oss:20b-cloud polarity 0.30  confidence 0.40
    ```
* **Descrizione:** `ensemble_std` è calcolato e persistito ma nel percorso d'ingresso non è letto da
  nessuno (`grep` su `src/`: le uniche letture sono `postmortem.py`, che si attiva **dopo** una
  perdita, e la copia nel DataFrame). CLAUDE.md prescrive esplicitamente «Ensemble variance: query
  multiple models/seeds; flag high-variance outputs for human review or discard». Oggi il segnale
  con lo std più alto della giornata (0,283, i due modelli distanti 0,40 di polarity e 0,40 di
  confidence) è passato senza alcuna segnalazione ed è diventato uno dei due soli ordini d'acquisto.
* **Impatto:** l'unica difesa contro un'allucinazione di un singolo modello è il gate sullo score, e
  lo score medio nasconde il disaccordo (0,70×0,80 e 0,30×0,40 mediano a 0,36, sopra soglia). Non
  esiste supervisor agent né verifica RAG delle affermazioni quantitative: una notizia mal letta da
  un modello su due può diventare un ordine.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** **nessuna taratura durante il freeze** (scegliere una soglia di varianza è
  esattamente ciò che la carta congela). Registrare l'evidenza e portare la decisione al 28/09;
  nel frattempo, strumentazione: esporre `ensemble_std` nella motivazione della decisione, che oggi
  non lo cita.
* **Test/monitor consigliato:** monitor che registri, per ogni BUY, lo `ensemble_std` del segnale
  causante, così che al giorno 40 si possa misurare se i BUY ad alto disaccordo hanno IC peggiore.
* **Ledger:** **F-037 (nuovo)**

---

### [DAY-004] Il trigger di revisione documentato è scattato su WDC (−20,5%) e nessun alert lo ha segnalato

* **Tipo:** Anomalia
* **Area:** Risk / Ops
* **Evidenza:**
  * file/log/tabella: `stop_shadow_log`; `config/trading.yaml:180-182`; `mobile_events`
  * timestamp: 2026-08-11, 9 cicli su 24
  * snippet/query:
    ```sql
    SELECT symbol, count(*), min(observed_price/entry_price-1) FROM stop_shadow_log
     WHERE created_at::date='2026-08-11' AND observed_price <= entry_price*(1-d_hard)
     GROUP BY 1;   -- WDC | 9 | -0.2051   (d_hard = 0.20)
    SELECT title, severity FROM mobile_events WHERE occurred_at::date='2026-08-11';
    -- solo: ciclo in ritardo, segnali in ritardo, dati broker non aggiornati
    ```
* **Descrizione:** `config/trading.yaml:180-182` scrive testualmente: «Revisit: if any position
  rides past −15/20% (d_hard shadow), wire d_hard to a real broker order». Il 2026-08-11 WDC ha
  superato la soglia `d_hard` di 0,20 in 9 cicli su 24, con escursione peggiore −20,51%; NOK è a
  −19,84%, appena sotto. La condizione ricorre da settimane (NOK il 07-30, 07-31, 08-03, 08-07,
  08-10; WDC il 07-28, 08-07, 08-10) e **nessun alert l'ha mai sollevata**. Lo stesso rilievo era
  già stato formulato come raccomandazione T-03 nel report del 2026-07-29 e non è stato attuato.
* **Impatto:** la decisione di revisione scritta dall'operatore non gli arriverà mai: dipende dal
  fatto che qualcuno interroghi a mano una tabella di shadow. Non è una perdita — lo stop è
  disattivato per scelta esplicita — è la perdita del **punto di decisione**.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** strumentazione (non taratura, come per la deroga #161): un alert su
  `stop_shadow_log` quando `observed_price <= entry_price*(1-d_hard)`.
* **Test/monitor consigliato:** l'alert stesso, con soglia di ripetizione giornaliera per simbolo.
* **Ledger:** **F-036 (nuovo)**

---

### [DAY-005] Ogni BUY ha `signal_id` NULL: la causa è che il DataFrame dei segnali non trasporta la colonna

* **Tipo:** Bug
* **Area:** Signal / Data
* **Evidenza:**
  * file/log/tabella: **`src/workers/portfolio_scheduler.py:3651-3660`**;
    `src/strategies/s4/strategy.py:172-174`; `execution_decisions` id 8852 e 9336
  * timestamp: 2026-08-11 14:07:08 e 19:07:10
  * snippet/query:
    ```python
    # portfolio_scheduler.py:3651 — le chiavi del dict sono:
    # symbol, score, confidence, reasoning, model_id, ensemble_std, fallback_used, generated_at
    # signal_id NON c'è.
    # strategy.py:172:  raw_signal_id = row.get("signal_id") if "signal_id" in row.index else None
    ```
    ```sql
    SELECT decision, count(*) FILTER (WHERE signal_id IS NULL), count(*)
      FROM execution_decisions WHERE created_at::date='2026-08-11' GROUP BY 1;
    -- BUY: 2 su 2 NULL; SELL: 2 su 2 NULL; SKIP_PYRAMIDING: 0 su 13 (percorso diverso)
    ```
* **Descrizione:** F-011 registra da sette giorni che 505 righe su 508 hanno `signal_id` NULL, senza
  causa identificata. La causa è questa: il DataFrame costruito nel live non include `signal_id`,
  quindi `_signals_as_of` lo legge come `None`, la `provenance` del ranker lo propaga come `None` e
  la riga di decisione lo scrive NULL. Le uniche 3 righe con `signal_id` valorizzato provengono dal
  percorso `_pyramiding_blocked`, che usa una query separata (`fetch_latest_signal_ids`) — coerente
  con i 13 SKIP_PYRAMIDING di oggi, tutti con id.
* **Impatto:** la catena segnale→decisione→trade non è ricostruibile per nessun ordine reale. È il
  motivo per cui ogni report forense deve riagganciare i segnali per simbolo e ora invece che per
  chiave, e per cui il valore di conviction registrato nella riga (0,388 su IBM) non è verificabile
  contro la riga di segnale (0,323) senza un ragionamento indiretto. **Questo difetto rende
  l'evidenza raccolta non verificabile**, quindi rientra nell'esenzione della carta.
* **Severità:** High
* **Confidenza:** High
* **Azione consigliata:** ~~ticket di correttezza — aggiungere `signal_id` al dict di riga 3651~~.
  **Già corretto**: mentre questo report veniva scritto, il commit `f742343` («fix: conserva il
  `signal_id` nella pipeline S4 (#123)», PR #234, mergiata su `main` il 2026-08-12 alle 12:03 CEST)
  aggiunge esattamente `"signal_id": s.signal_id` al dict di riga 3657. La correzione **non era in
  produzione il 2026-08-11**: l'immagine in esecuzione quel giorno la precede, quindi tutte le
  righe della giornata restano NULL e l'evidenza raccolta fino a oggi non è verificabile a ritroso.
  Resta da **verificare il deploy** e da confermare sui dati del primo giorno utile.
* **Test/monitor consigliato:** test che una BUY S4 scriva `execution_decisions.signal_id` non NULL;
  monitor giornaliero sulla quota di righe BUY/SELL con `signal_id` NULL.
* **Ledger:** F-011 (nuova occorrenza)

---

### [DAY-006] AVGO: unico segnale fresco sopra il gate sparito senza lasciare una riga

* **Tipo:** Anomalia
* **Area:** Signal
* **Evidenza:**
  * file/log/tabella: `sentiment_signals` 7186; `execution_decisions`;
    `src/workers/portfolio_scheduler.py:3586` (`_record_fallback_drops(..., non_fallback_signals=signals)`)
  * timestamp: 2026-08-11 14:01:34
  * snippet/query:
    ```sql
    SELECT id,symbol,score,model_id,fallback_used FROM sentiment_signals WHERE id=7186;
    -- 7186 | AVGO | 0.33 | single:gpt-oss:20b-cloud | t
    SELECT count(*) FROM execution_decisions
     WHERE created_at::date='2026-08-11' AND symbol='AVGO';   -- 0
    ```
* **Descrizione:** AVGO è in watchlist, non ha posizione aperta, e il suo unico segnale della
  giornata (+0,330, sopra il gate 0,30) è un fallback single-model. Gli altri fallback della
  giornata hanno lasciato una riga `SKIP_FALLBACK`; AVGO no. La ragione è la clausola
  `non_fallback_signals=signals` nel logger: AVGO ha ancora in finestra (lookback 96h) due segnali
  ensemble del 08-10, quindi è considerato «valutato davvero» e non viene registrato — ma quei
  segnali del 08-10 sono poi scartati per anzianità e, essendo sotto 0,30, non producono neppure la
  riga di `_record_stale_drops`. Risultato: un simbolo con un segnale fresco sopra soglia risulta
  a valle indistinguibile da NO_NEWS, che è esattamente ciò che l'issue #151 voleva evitare.
* **Impatto:** l'analisi di alpha-miss classifica AVGO come «nessuna copertura» quando invece la
  copertura c'era ed è stata scartata. Contamina la causa di miss dominante, che è la metrica su
  cui la domanda di uscita n.1 verrà falsificata.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** ticket di correttezza sull'osservabilità — la clausola di dedup deve
  confrontarsi con i segnali **freschi**, non con l'intera finestra di 96h.
* **Test/monitor consigliato:** invariante giornaliera «ogni simbolo con un segnale del giorno
  |score| ≥ gate ha almeno una riga in `execution_decisions`».
* **Ledger:** F-006 (nuova occorrenza)

---

### [DAY-007] `portfolio_cycles`: 73 ordini target contro 4 inviati

* **Tipo:** Bug
* **Area:** Ops / Orders
* **Evidenza:**
  * file/log/tabella: `portfolio_cycles` 886-909
  * timestamp: 2026-08-11 14:07 → 19:52
  * snippet/query:
    ```sql
    SELECT sum(orders_count), sum(jsonb_array_length(final_orders)), count(*)
      FROM portfolio_cycles WHERE timestamp::date='2026-08-11';   -- 73 | 73 | 24
    ```
* **Descrizione:** `orders_count` e `final_orders` registrano gli ordini **proposti** dal combiner,
  non quelli inviati. Il rapporto oggi è 73:4. HOOD compare come BUY in 13 cicli consecutivi pur
  essendo stato comprato una sola volta. Chi legge la telemetria del ciclo non può distinguere una
  giornata operosa da una giornata in cui tutto è stato bloccato.
* **Impatto:** ogni serie storica costruita su `orders_count` (attività, turnover, intensità) è
  sovrastimata di un ordine di grandezza.
* **Severità:** Low
* **Confidenza:** High
* **Azione consigliata:** aggiungere un campo `orders_submitted` accanto a `orders_count`; non
  riscrivere lo storico.
* **Test/monitor consigliato:** invariante `orders_submitted ≤ orders_count` e allerta se il
  rapporto scende sotto il 10% per più giorni.
* **Ledger:** F-014 (nuova occorrenza)

---

### [DAY-008] `risk_reports` emette un ALERT «drawdown 14,8%» e un `daily_pnl` di −653,76 in una giornata chiusa a −46,42

* **Tipo:** Bug
* **Area:** Risk
* **Evidenza:**
  * file/log/tabella: `risk_reports` id 60; `portfolio_monitor_snapshots`
  * timestamp: 2026-08-11 22:30:00
  * snippet/query:
    ```sql
    SELECT combined_drawdown, per_strategy_metrics->'portfolio'->>'drawdown',
           per_strategy_metrics->'portfolio'->>'daily_pnl', alerts FROM risk_reports WHERE id=60;
    -- 0.012429 | 0.14765590197592068 | -653.7584274773443
    -- [{"level":"ALERT","message":"Strategy portfolio drawdown 14.8% exceeds 10%"}]
    ```
* **Descrizione:** nello stesso record convivono `combined_drawdown` = 1,24% e un
  `per_strategy_metrics.portfolio.drawdown` = 14,77%, ed è il secondo a far scattare l'ALERT. Il
  `daily_pnl` di −653,76 non corrisponde a nulla di osservabile: il realizzato è −14,29, la
  variazione NAV −46,42, lo snapshot broker delle 20:00 riporta `current_drawdown` 0,29%.
* **Impatto:** un ALERT che si ripete ogni sera e che nessuno può usare: chi lo legge non sa se il
  libro è a −0,3% o a −14,8%. È rumore che spegne l'attenzione sugli alert veri (vedi [DAY-004]).
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** ticket di correttezza sulla metrica; **nessuna modifica della soglia** del
  10% (sarebbe taratura).
* **Test/monitor consigliato:** test che, dato uno snapshot con drawdown broker noto,
  `per_strategy_metrics.portfolio.drawdown` lo riproduca entro tolleranza.
* **Ledger:** F-003 (nuova occorrenza)

---

### [DAY-009] `ingestion_stats_daily.duplicates` (2.628) supera `fetched` (681) di 3,9×

* **Tipo:** Anomalia
* **Area:** News / Data
* **Evidenza:**
  * file/log/tabella: `ingestion_stats_daily`, giorno 2026-08-11, source `alpaca_benzinga`
  * timestamp: aggiornamento 19:45:01
  * snippet/query:
    ```sql
    SELECT source, fetched, queued, duplicates FROM ingestion_stats_daily WHERE day='2026-08-11';
    -- alpaca_benzinga | 681 | 292 | 2628
    ```
* **Descrizione:** il contatore dei duplicati non può eccedere gli elementi recuperati se conta
  articoli; conta evidentemente coppie articolo×ticker o accumula fra passate senza reset.
  Ricorre dal 08-04.
* **Impatto:** l'efficienza dell'ingest non è misurabile; non si può distinguere «il provider
  ripete» da «il nostro dedup ricalcola».
* **Severità:** Low
* **Confidenza:** High
* **Azione consigliata:** definire l'unità di conteggio e documentarla nella colonna.
* **Test/monitor consigliato:** invariante `duplicates ≤ fetched` per fonte e giorno.
* **Ledger:** F-007 (nuova occorrenza)

---

### [DAY-010] Righe `reuters` fantasma nel database di produzione

* **Tipo:** Bug
* **Area:** Data / Ops
* **Evidenza:**
  * file/log/tabella: `ingestion_stats_daily`; `news_log`
  * timestamp: 2026-08-11 10:52:53 (pre-market, fuori da ogni finestra beat)
  * snippet/query:
    ```sql
    SELECT day,fetched,queued,updated_at FROM ingestion_stats_daily WHERE source='reuters'
     ORDER BY day DESC LIMIT 4;   -- 08-11: 24/24 @10:52 · 08-10: 12/12 @22:05 · 08-07: 16/16 @09:02
    SELECT count(*) FROM news_log WHERE source='reuters';   -- 0
    ```
* **Descrizione:** non esiste un connettore Reuters attivo e non è mai stata scritta una riga di
  `news_log` con quella fonte, in tutta la storia del DB. Le righe compaiono a orari sparsi
  (10:52, 22:05, 09:02, 23:32) tipici di esecuzioni di test. È la suite che scrive nel database di
  produzione.
* **Impatto:** le statistiche d'ingestione contengono una fonte inesistente; qualunque analisi
  «quante fonti abbiamo» è sbagliata. Peggio: se i test scrivono qui, possono scrivere altrove.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** ticket di correttezza — isolare il DSN dei test; ripulire lo storico è
  facoltativo e non urgente.
* **Test/monitor consigliato:** guard in `conftest` che rifiuti un DSN che punti al database di
  produzione.
* **Ledger:** F-028 (nuova occorrenza)

---

### [DAY-011] Finestre beat in ora UTC fissa: 37 minuti di sessione scoperti e un CRITICAL auto-risolto ogni mattina

* **Tipo:** Bug
* **Area:** Ops
* **Evidenza:**
  * file/log/tabella: `src/workers/celery_app.py:78,142,153,175,201`; `mobile_events`
  * timestamp: incidente aperto 13:30:01, risolto 14:08:00
  * snippet/query:
    ```python
    "schedule": crontab(minute="7,22,37,52", hour="14-21", day_of_week="1-5")   # portfolio cycle
    "schedule": crontab(minute="*/15",       hour="14-21", day_of_week="1-5")   # news ingest
    ```
* **Descrizione:** le finestre sono in UTC fisso e ignorano il DST. In EDT il mercato apre alle
  13:30 UTC ma il primo ciclo è alle 14:07 e la prima fetch news alle 14:01: **37 minuti di sessione
  scoperti ogni giorno**. Il monitor lo rileva come incidente CRITICAL «Ciclo di portafoglio in
  ritardo» alle 13:30:01, che si auto-risolve alle 14:08 — un falso allarme quotidiano
  strutturale. All'altro capo, i cicli programmati fino alle 21:52 cadono dopo la chiusura e non
  producono nulla.
* **Impatto:** l'apertura è la finestra a più alta dispersione e non è coperta; l'incidente
  ricorrente addestra a ignorare gli alert.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** ancorare le finestre al calendario di mercato (Alpaca `GetCalendarRequest`,
  già usato da `scripts/daily_alpha_miss_analysis.sh`). Correttezza, non taratura: la cadenza di 15
  minuti resta invariata.
* **Test/monitor consigliato:** test parametrico su una data EST e una EDT che verifichi che il
  primo ciclo cada entro 10 minuti dall'apertura.
* **Ledger:** F-021 (nuova occorrenza)

---

### [DAY-012] `trades.slippage_est` è una copia di `cost_usd` su tutti e tre i trade

* **Tipo:** Bug
* **Area:** PnL
* **Evidenza:**
  * file/log/tabella: `trades` 695, 699, 700
  * timestamp: 2026-08-11
  * snippet/query:
    ```sql
    SELECT symbol, cost_usd, slippage_est, cost_usd - slippage_est FROM trades
     WHERE entry_time::date='2026-08-11' OR exit_time::date='2026-08-11';
    -- SONY 2.4541886081577977 | 2.4541886081577977 | 0
    -- HOOD 2.4927320942900550 | 2.4927320942900550 | 0
    -- IBM  2.4417164480520968 | 2.4417164480520968 | 0
    ```
* **Descrizione:** lo slippage dovrebbe essere `prezzo di fill − prezzo di riferimento alla
  decisione`; è invece identico al costo modellato. La qualità di esecuzione non è misurata.
* **Impatto:** non si può distinguere un fill buono da uno cattivo, né misurare l'impatto
  dell'esecuzione a mercato sui rendimenti di S4.
* **Severità:** Low
* **Confidenza:** High
* **Azione consigliata:** persistere il prezzo di riferimento al momento della decisione e derivarne
  lo slippage; oppure azzerare la colonna e dichiararla non implementata.
* **Test/monitor consigliato:** test che, dato un fill a prezzo diverso dal riferimento, `slippage_est`
  differisca da `cost_usd`.
* **Ledger:** F-015 (nuova occorrenza)

---

### [DAY-013] I log dei container del giorno analizzato non esistono più

* **Tipo:** Bug
* **Area:** Ops
* **Evidenza:**
  * file/log/tabella: `docker inspect`, `docker compose logs`
  * timestamp: container ricreati 2026-08-12 10:13:04 UTC
  * snippet/query:
    ```
    docker compose logs worker --since 48h | head -2      → prima riga: 2026-08-12T10:13:12
    docker inspect -f '{{.Created}} {{.RestartCount}}' alembic-worker-1 → 2026-08-12T10:13:04  0
    ```
* **Descrizione:** worker, worker-inference, beat e api sono stati **ricreati** (non riavviati:
  `RestartCount=0`, `Created` = oggi) alle 10:13 UTC del 08-12. Tutti i log del 08-11 sono persi.
  È la quinta occorrenza del difetto.
* **Impatto:** l'analisi forense di oggi non ha potuto verificare: latenza LLM, eccezioni non
  propagate, messaggi «Signal velocity: N/M symbols adjusted», errori dei provider, retry. Tutte le
  affermazioni di questo report derivano dal DB e dal codice, mai dai log.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** driver di logging persistente (file o journald) con rotazione, oppure
  esportazione dei log a fine giornata prima di qualunque redeploy.
* **Test/monitor consigliato:** controllo, all'inizio del ciclo forense, che il più vecchio log
  disponibile preceda la data analizzata; in caso contrario dichiararlo (come qui).
* **Ledger:** F-027 (nuova occorrenza)

---

### [DAY-014] `llm_responses.eligible` continua a mislabellare i contributori reali

* **Tipo:** Bug
* **Area:** LLM
* **Evidenza:**
  * file/log/tabella: `llm_responses`, `sentiment_signals` del 2026-08-11
  * timestamp: giornata intera
  * snippet/query:
    ```sql
    -- 98 dei 118 segnali "ensemble" hanno ZERO risposte eleggibili
    -- 36 dei 39 segnali "single:gpt-oss" hanno DUE risposte in tabella
    -- 7 risposte eligible con confidence < 0.5 ; 3 risposte NON eligible con confidence >= 0.7
    ```
* **Descrizione:** ricorrenza identica al 08-10. Il flag non descrive chi ha contribuito
  all'aggregato. Conseguenza pratica: 44 segnali sono etichettati `fallback_used=true` e quindi
  esclusi dal ranking BUY (#108) anche quando entrambi i modelli hanno risposto.
* **Impatto:** il 27% dei segnali del giorno è fuori dal percorso d'ingresso per una ragione che il
  dato non documenta correttamente. AVGO (+0,330, sopra gate) è il caso di oggi.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** vedi F-010, già tracciato.
* **Test/monitor consigliato:** invariante «un segnale `ensemble:A+B` ha esattamente 2 risposte
  `eligible=true`».
* **Ledger:** F-010 — occorrenza 2026-08-11 **già scritta** dall'analisi alpha-miss (costo 6,70).
  Nessuna seconda occorrenza.

---

### [DAY-015] Entrambe le uscite del giorno sono su sentiment positivo

* **Tipo:** Anomalia
* **Area:** Orders
* **Evidenza:**
  * file/log/tabella: `execution_decisions` 8866, 9260; `sentiment_signals`
  * timestamp: 14:22:09 e 18:22:10
  * snippet/query: motivazioni che citano `score=+0.431` (SONY) e `score=+0.360` (HOOD)
* **Descrizione:** il pattern «SELL con sentiment positivo» (bug A5) si presenta oggi 2 volte su 2,
  ma **non** è il bug A5: nessun segnale negativo è stato letto come positivo. È la conseguenza
  diretta di [DAY-001] — il peso va a 0 per anzianità, non per inversione di segno.
* **Impatto:** chi monitora il pattern A5 sui dati aggregati vedrà un falso positivo al 100%.
* **Severità:** Low
* **Confidenza:** High
* **Azione consigliata:** nessuna azione autonoma; si risolve con [DAY-001].
* **Test/monitor consigliato:** nel monitor A5, escludere le uscite con `exit_mechanism` in
  (`expired`, `unknown`).
* **Ledger:** F-024 — occorrenza 2026-08-11 **già scritta** dall'analisi alpha-miss (costo 3,88).
  Nessuna seconda occorrenza.

---

## 11. False positive e aree risultate corrette

| verifica | esito |
|---|---|
| **IBM registra conviction 0,388 mentre il segnale in DB è 0,323** | **non è un'anomalia**: 0,32311599444153155 × 1,2 = 0,38773919332983786, il moltiplicatore viene da `_compute_signal_velocity` (boost `SIGNAL_VELOCITY_BOOST=0.20`, storia Redis `signal:IBM:history` = [0,323 / 0,000 / −0,010] → velocità 0,333 > soglia 0,30). Già chiarito nel report del 08-05. **Resta però** che due righe consecutive sullo stesso segnale (19:07 = 0,388, 19:22 = 0,323) registrano conviction diverse e nessuna delle due dichiara il moltiplicatore: la riga di decisione non è auto-esplicativa |
| Regime detection | **corretta**: `regime:current` scritto alle 13:30:44, regime `sideways`, due LLM concordi, `data_quality: complete`. F-017 non si manifesta oggi |
| Freeze del ratchet (#191) | **tenuto**: `feedback:state:S4` alle 18:30 registra trigger «3 consecutive losses» con `threshold_before 0.3 → threshold_after 0.3`. `config/trading.yaml:320 threshold_ratchet_enabled: false` è nell'immagine in esecuzione |
| Idempotenza | **corretta**: 5 `SIGNAL_DUPLICATE_SKIP` nell'audit log, nessun ordine duplicato, nessun `order_id` ripetuto |
| Riconciliazione posizioni | **corretta**: 48 trade aperti in DB, 48 posizioni negli 84 snapshot broker della giornata |
| Modalità paper/live | **corretta e inequivocabile**: `broker_environment='paper'` su tutti gli snapshot, `system:mode='paper'` |
| Tracciamento dei blocchi anti-pyramiding | **corretto da oggi**: le 13 righe `SKIP_PYRAMIDING` con score e peso non allocato sono la strumentazione di #231. Fino al 08-07 questi blocchi erano muti (F-031 nel titolo dice ancora «non lascia alcuna traccia»: quella metà non descrive più il presente) |
| Latenza di ingestione | **buona oggi**: mediana 31 min contro una finestra di 2h (26%). F-019 non si manifesta |
| Copertura FinBERT / Ollama | **Ollama up tutto il giorno**: 321 risposte, zero fallback FinBERT, budget $0,19 non esaurito |
| Notizie con timestamp futuro | **nessuna** |
| Sanitizzazione input | **attiva**: `sanitize_ticker` applicato a monte (è anzi la causa di F-032 su BRK.B) |
| Ordini fuori orario / su ticker non consentiti / duplicati | **nessuno** |
| `stop_decisions` vuota | **atteso**: il ramo `vol_scaled` non è in uso; il percorso attivo è `stop_shadow_log` (1.150 righe oggi) |
| `d_init_fixed = 0` in `stop_shadow_log` | **non è un bug**: riflette fedelmente `stop_loss: 0.0`. **Ma rende `would_breach_fixed` privo di significato** (308 «breach» = semplicemente «prezzo sotto l'ingresso»): il braccio di confronto fixed non è utilizzabile per la decisione PASS→`vol_scaled` |

---

## 12. Dati mancanti o non accessibili

| dato | stato | cosa servirebbe |
|---|---|---|
| Log dei container del 2026-08-11 | **persi** (redeploy 08-12 10:13) | driver di logging persistente — [DAY-013] |
| API REST locali (`/api/decisions`, `/trades`, `/signals`, `/positions`, `/orders`) | **inaccessibili**: `{"detail":"Invalid or expired JWT token"}` con il bearer fornito | rigenerare il token nel prompt del cron, oppure un token di servizio a lunga scadenza in sola lettura |
| Latenza per chiamata LLM | **non esiste**: nessuna colonna di durata in `llm_responses` | aggiungere `latency_ms` (strumentazione) |
| Timeout / refusal / errori LLM | **non persistiti**: solo le risposte riuscite arrivano in tabella | contatore per esito in `fallback_counters` o log strutturato |
| Ordini a libro presso il broker (stop/TP bracket) | **non verificati**: avrebbe richiesto una chiamata all'API Alpaca, esclusa dal mandato read-only | uno snapshot serale degli ordini aperti in tabella |
| Prezzo di riferimento alla decisione | **non persistito** → slippage non calcolabile — [DAY-012] | colonna `reference_price` su `trades` |
| Marks intraday per posizione | **non persistiti** → i −12,67 $ residui della riconciliazione NAV non sono attribuibili | snapshot per-posizione, non solo aggregato |
| Attribuzione di strategia su 11 delle 48 posizioni | **NULL** (`stop_strategy`), tutte entrate il 07-10 | F-002, già tracciato |

---

## 13. Raccomandazioni immediate

Tutte di **correttezza o strumentazione**; nessuna tocca soglie, pesi, flag di strategia o
cooldown, coerentemente con la carta di osservazione.

1. **Correggere [DAY-001]** (doppio filtro di staleness che annulla FIX-D). È il difetto che
   determina il comportamento d'uscita di S4 e quindi la risposta alla domanda di uscita n.1.
   Passa il test di esenzione: senza la correzione, i prossimi 30 giorni misurano il filtro, non la
   strategia.
2. ~~**Correggere [DAY-005]**~~ — **fatto in parallelo a questa analisi**: commit `f742343` / PR #234
   (issue #123) aggiunge `signal_id` al DataFrame. Resta da **verificare che sia deployato** e da
   confermare sui dati del primo giorno utile che `execution_decisions.signal_id` non sia più NULL
   sulle righe BUY/SELL.
3. **Correggere [DAY-002]** (`regime_mult` sul target o guard P0-05 consapevole del rabbocco).
   La sleeve S4 sta operando al 70% del peso che il backtest assume.
4. **Rendere persistenti i log dei container** prima del prossimo redeploy — [DAY-013].
5. **Rigenerare il token API** usato dal cron forense — §12.
6. **Alert su `stop_shadow_log` oltre `d_hard`** — [DAY-004]: il punto di decisione scritto
   dall'operatore in `trading.yaml` non gli sta arrivando.
7. **Isolare il DSN dei test dal DB di produzione** — [DAY-010].

Non raccomandato durante il freeze: introdurre un gate di varianza d'ensemble ([DAY-003]) o una
banda di isteresi fra ingresso e uscita (F-013). Sono tarature: vanno alla sintesi del 28/09.

---

## 14. Test o monitor da aggiungere

| # | test / monitor | copre |
|---|---|---|
| T-01 | Test: segnale di 5h su simbolo con posizione aperta e nessun contro-segnale → `generate_orders` non emette SELL | [DAY-001] |
| T-02 | Test: BUY S4 scrive `execution_decisions.signal_id` non NULL | [DAY-005] |
| T-03 | Test: con `regime_mult=0.7` e target 2%, la posizione converge al 2% | [DAY-002] |
| T-04 | Invariante giornaliera: ogni simbolo con segnale del giorno `|score| ≥ gate` ha ≥1 riga in `execution_decisions` | [DAY-006] |
| T-05 | Invariante: un segnale `ensemble:A+B` ha esattamente 2 risposte `eligible=true` | [DAY-014] |
| T-06 | Invariante: `ingestion_stats_daily.duplicates ≤ fetched` per fonte e giorno | [DAY-009] |
| T-07 | Monitor: alert quando `stop_shadow_log.observed_price ≤ entry_price*(1−d_hard)` | [DAY-004] |
| T-08 | Monitor: quota giornaliera di uscite con `exit_mechanism='unknown'`; allerta oltre il 50% | [DAY-001] |
| T-09 | Monitor: rapporto `ordini inviati / ordini target` per ciclo | [DAY-007] |
| T-10 | Test parametrico DST: il primo ciclo cade entro 10 minuti dall'apertura sia in EST sia in EDT | [DAY-011] |
| T-11 | Guard in `conftest`: rifiuto di un DSN che punti al database di produzione | [DAY-010] |
| T-12 | Telemetria: registrare `ensemble_std` e il moltiplicatore di velocity nella riga di decisione | [DAY-003], §11 |

---

## 15. Ticket tecnici suggeriti

| id | titolo | tipo | priorità | esente dal freeze? |
|---|---|---|---|---|
| TK-A | S4: la finestra di freschezza è applicata due volte e annulla FIX-D (`strategy.py:167-169`) | correttezza | **P0** | **sì** — senza, l'evidenza sulle uscite S4 è sbagliata |
| ~~TK-B~~ | ~~`signals_df` non trasporta `signal_id`~~ — **chiuso da PR #234 / commit `f742343` (issue #123) il 2026-08-12**; resta la verifica di deploy | correttezza | — | — |
| TK-C | `regime_mult` scala il notional ma non il target; P0-05 blocca il rabbocco | correttezza | P1 | sì — il live diverge dal backtest |
| TK-D | Log dei container non persistenti fra redeploy | ops | P1 | sì — strumentazione |
| TK-E | Alert su superamento `d_hard` in `stop_shadow_log` | ops | P1 | sì — strumentazione (cfr. deroga #161) |
| TK-F | `_record_fallback_drops`: la dedup usa la finestra 96h invece dei segnali freschi (AVGO muto) | correttezza | P2 | sì — contamina la causa di miss |
| TK-G | `risk_reports`: `combined_drawdown` e `per_strategy_metrics.portfolio.drawdown` divergono di 12 punti | correttezza | P2 | sì — l'ALERT non è interpretabile |
| TK-H | La suite di test scrive `ingestion_stats_daily` nel DB di produzione | correttezza | P2 | sì |
| TK-I | Finestre beat in UTC fisso: 37 minuti di sessione scoperti e CRITICAL quotidiano | correttezza | P2 | sì |
| TK-J | `trades.slippage_est` copia `cost_usd`: persistere il prezzo di riferimento | osservabilità | P3 | sì — strumentazione |
| TK-K | `portfolio_cycles`: distinguere `orders_count` da `orders_submitted` | osservabilità | P3 | sì |
| TK-L | Registrare `ensemble_std` e il moltiplicatore di velocity nella motivazione della decisione | osservabilità | P3 | sì |
| TK-M | Gate di varianza d'ensemble sull'ingresso | **taratura** | — | **no** — al 28/09 |
| TK-N | Banda di isteresi fra gate d'ingresso e uscita (F-013) | **taratura** | — | **no** — al 28/09 |

Nota: il fix `DAY → GTC` sulle gambe bracket (già emerso dall'audit Alpaca del 08-07, issue
#195-#198) resta pertinente: entrambi i BUY di oggi sono su simboli frazionabili e usano
`time_in_force="day"` (`portfolio_scheduler.py:3935`), quindi le gambe stop/TP scadono a fine
sessione. Non lo riapro come finding: è già tracciato.

---

## 16. Stato sistema

| voce | stato |
|---|---|
| **Ollama Cloud** | **up per l'intera giornata**. 321 risposte fra 14:01 e 19:46, zero errori osservabili, `gpt-oss:20b-cloud` 162 richieste e `glm-5.2:cloud` 159 (3 in meno, non distinguibili da errori senza i log). **Downtime: 0 ore osservate** |
| **Fallback FinBERT** | **0%** delle decisioni. Nessun segnale con `model_id` FinBERT oggi. Il «fallback» del 27% è il ramo *single-model* (un LLM su due sotto il floor di eleggibilità), non FinBERT |
| **Fallback single-model** | 44 segnali su 162 (**27%**), di cui 39 `gpt-oss` e 5 `glm`. 6 hanno prodotto una riga `SKIP_FALLBACK`; AVGO no ([DAY-006]) |
| **Worker restart** | **0 restart durante il 2026-08-11** (`RestartCount=0` su tutti). Ma i container sono stati **ricreati** il 2026-08-12 alle 10:13:04 UTC, cancellando i log della giornata analizzata ([DAY-013]) |
| **Celery beat** | attivo, 24 cicli su 24 alla cadenza prevista; nessun ciclo saltato, nessun doppione |
| **Budget LLM** | $0,187 spesi (95.571 token in, 11.452 out), `budget_exhausted = false` |
| **Redis** | operativo; `regime:current` aggiornato 13:30:44, `feedback:entry_threshold:S4 = 0.3` (TTL ~3,4 giorni), `ensemble:weights:current` = glm 0,601 / gpt-oss 0,399 |
| **Postgres** | operativo, uptime 4 giorni |
| **Broker** | Alpaca **paper**, 84 snapshot su 84 attesi (ogni 5 min, 13:30-20:00), nessuna degradazione registrata (`degradations = []`) |
| **Alert emessi** | 3 incidenti, tutti auto-risolti entro 38 minuti: ciclo in ritardo (CRITICAL), segnali in ritardo (WARNING), dati broker non aggiornati (CRITICAL). **Zero alert su WDC a −20,5%** ([DAY-004]) |
