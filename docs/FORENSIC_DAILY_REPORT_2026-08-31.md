# Forensic Daily Report — 2026-08-31

> Analisi read-only della seduta di **lunedì 2026-08-31**. Fuso operativo **UTC**
> (`src/workers/celery_app.py:52-53`: `timezone="UTC"`, `enable_utc=True`) — nessuna
> ambiguità di timezone nel codice. L'ambiguità è nelle **finestre beat fisse**
> (`hour="14-21"`), che ignorano il DST: vedi [DAY-009].
> Sessione RTH: **13:30–20:00 UTC** (EDT, DST attivo). Modalità broker: **paper**
> (`portfolio_monitor_snapshots.broker_environment = paper`, `source = alpaca_paper`,
> 94 righe su 94).
>
> **Nota sul regime di scoring:** il fix del prompt sentiment Variante A (#399/#408,
> `bf5bef2e`) è stato deployato il **2026-09-01T10:33Z**, cioè *dopo* la seduta qui
> analizzata. Tutti i punteggi del 2026-08-31 provengono dal prompt **pre-fix**
> (nessun titolo nel prompt, read-through sotto-scorato). Non confrontare questa
> giornata con quelle da settembre in poi senza segmentare.

---

## 1. Executive summary

La pipeline ha girato **senza guasti infrastrutturali**: 24 cicli di portafoglio, 102
news scorate, 196 chiamate LLM tutte persistite, nessun timeout d'ensemble esteso,
nessun riavvio worker in seduta, riconciliazione DB↔broker perfetta (47 trade aperti =
47 posizioni broker), zero ordini duplicati, zero ordini fuori orario, esposizione
32,2% contro un tetto del 50% e drawdown 0,81% contro un limite del 5%.

Il difetto della giornata è **a monte, nella qualità del segnale, e ha un costo
misurato**. Fra le 18:01 e le 18:31 UTC tre listicle Benzinga della stessa famiglia
(*"N <settore> Stocks Whale Activity In Today's Session"*) hanno prodotto **13 segnali
a punteggio 0,000** su 13 ticker. Entrambi i modelli li avevano marcati
`ambiguous_entity` / `low_source_quality`, `materiality=0`, `novelty=0`, confidenza
0,15–0,20 — eppure sono stati persistiti come `ensemble:…` con `fallback_used=false`,
e quindi come "segnale più recente non-fallback" hanno **azzerato lo stato S4 di tutti
e 13 i ticker** per il resto della seduta. Due conseguenze documentate: **AVGO**,
comprata alle 17:22 su una nota JPMorgan issuer-specific (+0,653, conf 0,785), è stata
**liquidata alle 19:07** perché il suo punteggio era diventato 0,000 (−1,27 $ realizzati
contro +3,15 $ di MTM a fine seduta: **−4,42 $**); **TSLA**, che alle 18:07 mostrava
0,281 — il massimo issuer-specific della giornata, a 0,019 dal gate — è tornata a 0,000
alle 18:22 e ha chiuso **+5,51%**.

Seconda anomalia con costo: la `sentiment_reversal` di S4 ha chiuso alle 19:37 una
posizione **S1** su GOOGL aperta il 2026-07-10 (−30,21 $ realizzati, iscritti a S1;
−1,31 $ rispetto al mantenimento a fine seduta). È il caso già pre-registrato dalla
deroga #182(a) del 2026-08-25, **non ancora deployata**.

Terza, nuova: l'alert EOD sulle posizioni scoperte lato uscita (#324) ha girato per la
**prima volta** alle 22:50 aprendo 5 incidenti — e tutti e 5 sono stati **richiusi
0,4 secondi dopo** dal valutatore mobile generico, che recupera indiscriminatamente
ogni fingerprint attivo non suo. Il canale che la deroga aveva appena costruito ha
vita utile inferiore al secondo.

Quarta, emersa in **ri-verifica il 2026-09-01 alle 17:0xZ**: un giro della suite di test
lanciato sulla macchina alle ~16:57Z ha risolto `DATABASE_URL` sul database di
**produzione** ed eseguito le `TRUNCATE ... CASCADE` delle proprie fixture. La storia
degli incidenti mobile — l'evidenza primaria delle sezioni 3 e [DAY-004] — **non esiste
più**, insieme a utenti, device e sessioni del monitor ([DAY-017]). Tutte le altre
tabelle citate in questo report sono state ri-verificate integre.

## 2. Verdict finale

**ANOMALIE SIGNIFICATIVE.**

L'infrastruttura è sana e il money path è auditabile end-to-end sui due ordini
d'ingresso. Ma la giornata contiene **tre difetti di correttezza con effetto sul
comportamento osservato**, non solo sull'osservabilità:

1. un articolo che entrambi i modelli hanno dichiarato non informativo ha comandato
   una liquidazione (AVGO) e ha cancellato il miglior segnale della seduta (TSLA);
2. l'overlay d'uscita di S4 ha liquidato una posizione S1 (GOOGL), meccanismo già
   deciso da rimuovere ma ancora vivo;
3. l'unico canale d'allerta nuovo della settimana si auto-annulla;
4. e — fuori seduta, ma dentro la catena di custodia dell'evidenza — un giro di test ha
   **cancellato** la storia degli incidenti mobile dal database di produzione
   ([DAY-017]).

Nessuno dei quattro è di taratura: sono difetti che, se non corretti, rendono
**sbagliata l'evidenza** raccolta da qui al 28/09 — il quarto la cancella
retroattivamente. Il resto è ricorrenza nota e già a ledger.

---

## 3. Timeline del 2026-08-31 (tutti gli orari UTC)

| Ora | Componente | Evento | Esito | Fonte |
|---|---|---|---|---|
| 13:30:00 | mobile monitor | Primo snapshot: NAV 109.832,71 · prev close 109.802,54 · cash 75.848,10 · esposizione 30,94% · 47 posizioni | OK | `portfolio_monitor_snapshots` |
| 13:30:01 | mobile alert | Aperti 2 incidenti: *"Ciclo di portafoglio in ritardo"* (critical) e *"Segnali sentiment in ritardo"* (warning) | aperti | `mobile_events` |
| 13:30–14:00 | **tutta la pipeline** | **Nessun ingest, nessuno score, nessun ciclo, nessuna decisione** (0 righe in tutte e 4 le tabelle) | finestra cieca | [DAY-009] |
| 14:01:03 | ingestion | Prima riga `news_log` della seduta (alpaca_benzinga) | OK | `news_log` |
| 14:02:01 | mobile alert | Incidente "Segnali sentiment in ritardo" → recovered | OK | `mobile_events` |
| 14:03 / 14:06 | sentiment | SOXX +0,3376 · MU +0,3391 (entrambi sopra gate) | OK | `sentiment_signals` |
| 14:07:00 | portfolio-cycle | **Primo ciclo della giornata** (37 min dopo l'apertura). 5 CombinedOrder in `final_orders` | OK | `portfolio_cycles` |
| 14:07:04 | execution | 3 × SKIP_STALE (IWM −0,316 / QQQ −0,130 / DELL −0,169, segnali di **68,6–69,3 h**, da venerdì 28) | scartati | `execution_decisions` |
| 14:07:04 | execution | 3 × SKIP_PYRAMIDING: AMD +0,504 · **CRM +0,740** (massimo della giornata) · MU +0,407 | bloccati | [DAY-011] |
| 14:08:01 | mobile alert | Incidente "Ciclo di portafoglio in ritardo" → recovered | OK | `mobile_events` |
| 14:45:11 | ingestion | Prima riga gdelt_gkg (5 in tutta la giornata) | OK | `news_log` |
| 14:37 / 16:07 / 16:22 | execution | SKIP_PYRAMIDING su SOXX +0,405 · CVX +0,544 · DELL +0,504 | bloccati | [DAY-011] |
| 15:11→15:17 · 16:39→16:46 · 17:44→17:46 | mobile alert | Altri 3 incidenti "Segnali sentiment in ritardo", aperti e recuperati (buchi di arrivo news di 25–30 min) | OK | `mobile_events` |
| 17:02:56 | sentiment | **FinBERT fallback #1** — NVDA, score +0,0063 | fallback | `sentiment_signals` id 9330 |
| 17:18:14 | sentiment | **AVGO +0,6526** conf 0,785, ensemble pieno (glm 0,85/0,85 · oss 0,78/0,72, entrambi `eligible=true`) — *"JPMorgan Says Broadcom's Google Concerns Are Overstated Ahead of Earnings"* | OK | id 9339 |
| 17:22:00 | portfolio-cycle | **BUY AVGO** — score con boost velocity 0,7831, peso target 2,0%, ordine `14247e85` per 3,796 sh | inviato | `execution_decisions` |
| 17:22:04 | broker | Fill AVGO @ 369,51 — nozionale 1.402,66 $ | FILLED | `trades` id 921 |
| 17:27:00 | S4 lifecycle | `ENTRY_RECONCILIATION` AVGO — `BROKER_FILLED`, `unattributed_quantity = 0` | OK | `s4_lifecycle_events` |
| 17:52:03 | execution | SKIP_FALLBACK ORCL (single-model +0,100) | bloccato | #108 |
| **18:01–18:31** | **sentiment** | **3 listicle *"Whale Activity"* → 13 segnali a 0,000** su BAC, GS, HOOD, MS, BABA, AMZN, NKE, TSLA, **AVGO**, DELL, MRVL, MU, NVDA | **[DAY-001]** | id 9348–9360 |
| 18:07:03 | execution | **TSLA 0,281** < gate 0,300 (scarto 0,019) — miglior punteggio issuer-specific della giornata | SKIP_THRESHOLD | [DAY-002] |
| 18:16:38 | sentiment | AVGO **0,000** (id 9356) sostituisce il +0,6526 delle 17:18 | — | [DAY-001] |
| 18:22:03 | execution | Da qui in poi TSLA e AVGO valgono 0,000 in ogni ciclo | — | `execution_decisions` |
| 18:48:43 | sentiment | **FinBERT fallback #2** — GOOGL −0,2396 | fallback | id 9367 |
| 18:52:03 | execution | SKIP_FALLBACK CAT (single-model −0,215) | bloccato | #108 |
| **19:07:00** | portfolio-cycle | **SELL AVGO** — `[below_entry_gate]` «segnale generato 18:16, score +0,000» | inviato | [DAY-001] |
| 19:07 | broker | Fill @ 369,379463 — tenuta **1 h 45 min**, netto **−1,27 $** | FILLED | `trades` id 921 |
| 19:30:21 | sentiment | XLE **+0,4208** conf 0,675 — *"Oil Jumps Near \$90 On Iran Risk"* (`directness = sector`) | OK | id 9373 |
| 19:31:02 | sentiment | GOOGL **−0,3551** conf 0,65 — *"ChatGPT Ads Surge…"* (`directness = competitor_readthrough`) | OK | id 9375 |
| **19:37:00** | portfolio-cycle | **BUY XLE** (22,0056 sh @ 63,86 = 1.405,28 $) **+ SELL GOOGL** `sentiment_reversal` (−0,355 < −0,35) | inviati | [DAY-003] |
| 19:37:04 | broker | Fill GOOGL @ 338,67 — posizione **S1** aperta il 2026-07-10, netto **−30,21 $** | FILLED | `trades` id 258 |
| 19:42:00 | S4 lifecycle | `ENTRY_RECONCILIATION` XLE — `BROKER_FILLED`, `unattributed_quantity = 0` | OK | `s4_lifecycle_events` |
| 19:47:10 | ingestion | Ultima riga `news_log` | OK | `news_log` |
| 19:52:00 | portfolio-cycle | **24° e ultimo ciclo**. Da 20:07 il guard `get_clock()` salta correttamente i cicli a mercato chiuso | OK | `portfolio_scheduler.py:2237` |
| 20:00:00 | mobile monitor | NAV 109.833,17 (**+30,63 $, +0,028%**), esposizione 31,63%, 47 posizioni | OK | `portfolio_monitor_snapshots` |
| 22:30:01 | risk-monitor | NAV 109.832,25 · esposizione 31,63% · HHI 0,0258 · drawdown 1,24% · `per_strategy_metrics = {}` · `alerts = []` | [DAY-013] | `risk_reports` id 80 |
| 22:50:00 | held-news-loss (#324) | **Primo giro assoluto**: 5 incidenti aperti (ASML, MMM, NOK, TXN, UNH) | aperti | `mobile_events` |
| 22:50:01 | mobile alert | **Tutti e 5 richiusi 0,4 s dopo** dal valutatore generico | **[DAY-004]** | `mobile_events` |

Ultimo evento della giornata: nessuna consegna push emessa (`mobile_notification_deliveries`
vuota per la data) — nessun device registrato.

---

## 4. Tabella news ingest

### 4.1 Per fonte

| Fonte | `fetched` | `queued` | `duplicates` | `no_ticker` | `stale` | `parse_fail` | Righe in `news_log` | Ticker distinti | Prima / ultima |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `alpaca_benzinga` | 700 | 353 | **2.773** | 0 | 97 | 0 | 97 | 34 | 14:01:03 → 19:47:10 |
| `gdelt_gkg` | 1.627 | 5 | 2 | 1.620 | 0 | 0 | 5 | 4 | 14:45:11 → 19:46:00 |
| **Totale** | **2.327** | **358** | **2.775** | **1.620** | **97** | **0** | **102** | **36** | |

Scarti registrati in `news_queue_drops` (4.606 righe): `duplicate_id` 2.773 (ingestion),
`no_ticker` 1.620 (ingestion), `not_tradable` 114 (sentiment), `stale` 97 (sentiment),
`duplicate_content` 2 (ingestion).

Osservazioni:

* `duplicates` (2.773) è **3,96× i `fetched`** (700) sulla stessa riga — ricorrenza nota
  (denominatori diversi: `duplicates` accumula su tutte le finestre di poll
  sovrapposte). Vedi [DAY-012].
* GDELT: 1.620 su 1.627 scartati per `no_ticker` (99,6%). Resa netta **5 righe**.
* **Nessun timestamp futuro** (`published_at > fetched_at`: 0 righe).
* Nessun campo mancante: 0 righe senza titolo, 0 senza corpo, 0 senza `content_hash`.
* Corpo medio **157 caratteri** — è il `summary` Benzinga, non il `content`
  (oggetto di #454, fuori dal perimetro di correttezza).
* Latenza `published_at → fetched_at`: p50 **36,0 min**, p90 75,9 min, max 94,3 min.
  Scomposizione dal dossier: `published→first_seen` 10,6 min (esterno),
  `first_seen→ingested` 18,7 min (interno), `ingested→scored` ≈ 0.
  **In netto miglioramento** rispetto alla mediana storica di ~1h50m di F-019: consuma
  il 30% della finestra `MAX_NEWS_AGE_HOURS=2`, non il 92%.
* **Nessun buco temporale anomalo**: i tre intervalli senza segnali (14:47→15:16,
  16:15→16:45, 17:20→17:45, 25–30 min) coincidono con assenza di news, non con guasti.

### 4.2 Per ticker (top 20, tutte le righe `alpaca_benzinga` salvo dove indicato)

| Ticker | Righe | Articoli unici | Max \|score\| | Rendimento seduta |
|---|---:|---:|---:|---:|
| NVDA | 12 | 12 | 0,3551 | +1,48% |
| SPY | 9 | 9 | 0,2400 | — |
| TSLA | 5 | 5 | 0,2813 | **+5,51%** |
| AAPL | 5 | 5 | 0,0600 | −0,89% |
| GOOGL | 5 | 5 | 0,3551 | −2,09% |
| META | 4 | 4 | 0,2072 | −0,98% |
| MU | 4 | 4 | 0,3391 | +2,77% |
| XLE | 3 | 3 | **0,4208** | +2,04% |
| AVGO | 3 | 3 | **0,6526** | +0,42% |
| CVX | 3 | 3 | 0,4533 | +2,12% |
| SPCX | 3 | 3 | 0,2862 | — |
| QQQ / MRVL / ORCL / AMZN | 3 ciascuno | 3 | ≤ 0,134 | — |
| AMD | 2 (+1 gdelt) | 3 | 0,4924 | +1,10% |
| DELL | 2 | 2 | 0,4204 | −0,05% |
| NKE | 2 | 2 | **−0,4050** | −1,35% |
| XLF | 2 | 2 | 0,3465 | −0,67% |
| BAC | 2 | 2 | 0,2901 | −0,61% |
| BRK.B | 2 (gdelt) | 2 | 0,1350 | −0,19% |
| SOXX | 1 | 1 | 0,3376 | +0,48% |
| QCOM | 1 | 1 | 0,1800 | **+3,83%** |

**Copertura**: 60 dei 96 simboli di watchlist (62,5%) **senza una sola riga** di news —
massimo della serie osservata. Copertura *effective timely* (articolo issuer-specific
pubblicato entro il close): **15 ticker su 96 = 15,6%**; 20 articoli su 50 unici.
Ripartizione rilevanza: `ISSUER_SPECIFIC` 20, `UNKNOWN` 82, tutte le altre 0.

### 4.3 Top news per impatto sul segnale

| Ora | Ticker | Score | Conf | Titolo | Effetto |
|---|---|---:|---:|---|---|
| 17:18 | AVGO | **+0,6526** | 0,785 | *JPMorgan Says Broadcom's Google Concerns Are Overstated Ahead of Earnings* | **BUY 17:22** |
| 19:32 | AMD | +0,4924 | 0,775 | *Cisco and AMD Team With HUMAIN On Saudi AI Infrastructure* | SKIP_PYRAMIDING |
| 16:00 | CVX | +0,4533 | 0,675 | *What's Going On With Chevron Shares On Monday?* | SKIP_PYRAMIDING |
| 19:30 | XLE | **+0,4208** | 0,675 | *Oil Jumps Near \$90 On Iran Risk, California Utilities Crater* | **BUY 19:37** |
| 16:15 | DELL | +0,4204 | 0,675 | *Dell Q2 Preview: Record Revenue, Strong AI Backlog* | SKIP_PYRAMIDING |
| 17:17 | NKE | **−0,4050** | 0,675 | *JPMorgan Cuts Nike 2027 Earnings Outlook* | RANK_LONG_ONLY (nessun ordine) |
| 19:31 | GOOGL | **−0,3551** | 0,650 | *ChatGPT Ads Surge: How OpenAI's Rapid Expansion Imperils Google and Meta* | **SELL 19:37** |
| 18:00 | TSLA | +0,2813 | — | *Tesla Stock Surges Ahead of Cybercab Event* | SKIP_THRESHOLD (−0,019 dal gate) |
| 18:01–18:31 | 13 ticker | **0,0000** | 0,15–0,20 | *"N <settore> Stocks Whale Activity In Today's Session"* × 3 | **azzeramento stato S4** |

---

## 5. Tabella performance modelli LLM

| Modello | Richieste | Persistite | Errori/timeout | `eligible=true` | `eligible=false` | Polarity media | Conf media | Min/Max polarity |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `glm-5.2:cloud` | 98 | 98 | 0 | 31 (31,6%) | 67 | +0,0964 | 0,3311 | −0,60 / +0,85 |
| `gpt-oss:20b-cloud` | 98 | 98 | 0 | 31 (31,6%) | 67 | +0,0944 | 0,4439 | −0,60 / +0,78 |
| `finbert` (fallback) | 2 | 2 | 0 | n/a | n/a | — | 0,40–0,51 | −0,24 / +0,01 |

*Latenza per modello: **non misurabile** — `llm_responses` non ha una colonna di durata
e i log del worker della giornata non esistono più ([DAY-010]).*

**Composizione dei 102 segnali persistiti**

| Etichetta `model_id` | N | Risposte associate | Di cui `eligible` | \|score\| medio |
|---|---:|---:|---:|---:|
| `ensemble:glm-5.2+gpt-oss` | 31 | 2 | **2** | 0,2726 |
| `ensemble:glm-5.2+gpt-oss` | **32** | 2 | **0** | **0,0070** |
| `single:…` | 33 | 2 | 0 | 0,0763 |
| `single:…` | 4 | 1 | 0 | 0,0513 |
| `finbert` | 2 | 0 | — | 0,1229 |

Solo **31 segnali su 102 (30,4%)** poggiano su una coppia di risposte che superano il
predicato di eleggibilità come persistito. Gli altri 32 etichettati `ensemble` (e
`fallback_used=false`) sono il prodotto del retry a floor 0 di #90, la cui decisione
non viene ri-scritta su `llm_responses.eligible` — vedi [DAY-005].

**Tasso di fallback** (`fallback_used=true`): **39/102 = 38,2%**. Per ora:

| Ora UTC | Segnali | Ensemble | Single | FinBERT | % fallback |
|---|---:|---:|---:|---:|---:|
| 14 | 24 | 15 | 9 | 0 | 37,5% |
| 15 | 5 | 2 | 3 | 0 | 60,0% |
| 16 | 17 | 8 | 9 | 0 | 52,9% |
| 17 | 19 | 11 | 7 | 1 | 42,1% |
| 18 | 22 | 17 | 4 | 1 | 22,7% |
| 19 | 15 | 10 | 5 | 0 | 33,3% |

**Disaccordo fra modelli** (96 coppie complete):

* disaccordo di **segno**: 4 coppie;
* gap di polarity > 0,30: 10 coppie; gap medio 0,1177; **gap massimo 0,55** (TSLA:
  glm −0,20 vs oss +0,35).
* Su **7 delle 11 coppie più divergenti** `ensemble_std` è persistito a **0,000 esatto**
  — vedi [DAY-006].

**Metadati strutturati prodotti** (196 risposte):

* `event_type`: macro 77 · other 62 · product 21 · analyst_rating 10 · mna 7 ·
  regulatory 6 · management 4 · earnings 4 · lawsuit 3 · guidance 1 · sector 1.
* `directness`: macro 50 · **unclear 44** · direct 42 · sector 36 ·
  competitor_readthrough 15 · customer_supplier 8 · supplier_readthrough 1.
* `risk_flags`: **`ambiguous_entity` 101 (51,5% delle risposte)** · `low_source_quality`
  67 · `already_priced_in` 51 · `rumor` 9.

**Verifica funzionale**

| Domanda | Risposta | Evidenza |
|---|---|---|
| L'output LLM è validato prima di entrare nel signal store? | **No** — enum non tipizzati, nessuna normalizzazione | F-055 (già a ledger) |
| L'ensemble gestisce la varianza alta? | **No come gate**: `ensemble_std` non è mai una condizione d'ingresso, ed è 0,000 proprio sulle coppie divergenti | [DAY-006], F-037 |
| Le news duplicate pesano più volte? | No: dedup per `content_hash` e `duplicate_id` a monte (0 duplicati di sindacazione per ticker nel dossier) | `copertura_articoli` |
| La stessa news può generare segnali multipli? | **Sì, uno per ticker** (fan-out): 52 mapping fan-out extra su 50 articoli unici → 102 righe | F-012 |
| La confidenza bassa riduce il peso? | **Solo in ingresso.** `score = polarity × confidence` e il ranker richiede `confidence ≥ 0,30`; **il ramo d'uscita non applica alcun minimo di confidenza** | **[DAY-007]** |
| I modelli sono chiamati offline / fuori dal trading loop? | **Sì.** Coda `inference` dedicata, `sentiment-worker` disaccoppiato dal `portfolio-cycle`; il ciclo legge solo da Postgres | `celery_app.py`, `pg_store.fetch_signals_for_cycle` |
| Un'allucinazione può entrare direttamente in decisione? | **Sì, di fatto.** Il resolver deterministico ha emesso `NO_TRADE_*` su **216 righe su 216** e il verdetto non è vincolante | [DAY-014] |

---

## 6. Tabella segnali finali per ticker

36 simboli scorati, 102 segnali. Ordinati per massimo \|score\|.

| Ticker | N | Max score | Min score | Conf media | `ensemble_std` medio | Fallback | Esito nel ciclo | Rend. seduta |
|---|---:|---:|---:|---:|---:|:---:|---|---:|
| AVGO | 3 | **+0,6526** | 0,0000 | 0,512 | 0,0165 | sì | **BUY 17:22 → SELL 19:07** | +0,42% |
| AMD | 3 | +0,4924 | +0,0400 | 0,625 | 0,1296 | sì | SKIP_PYRAMIDING ×3 | +1,10% |
| CVX | 3 | +0,4533 | +0,0769 | 0,600 | 0,0825 | no | SKIP_PYRAMIDING | +2,12% |
| XLE | 3 | **+0,4208** | +0,0113 | 0,358 | 0,1179 | no | **BUY 19:37** | +2,04% |
| DELL | 2 | +0,4204 | 0,0000 | 0,413 | 0,0283 | no | SKIP_PYRAMIDING + SKIP_STALE | −0,05% |
| NKE | 2 | −0,4050 | −0,4050 | 0,413 | 0,0000 | no | **RANK_LONG_ONLY ×4** | −1,35% |
| GOOGL | 5 | **−0,3551** | −0,3551 | 0,450 | 0,0566 | sì | **SELL 19:37** (`sentiment_reversal`) | −2,09% |
| NVDA | 12 | +0,3551 | −0,0050 | 0,390 | 0,0412 | sì | RANK_OUTSIDE_TOP_N ×6 | +1,48% |
| XLF | 2 | +0,3465 | 0,0000 | 0,450 | 0,1237 | no | SKIP_PYRAMIDING | −0,67% |
| MU | 4 | +0,3391 | 0,0000 | 0,506 | 0,0530 | sì | SKIP_PYRAMIDING + RANK_OUTSIDE_TOP_N | +2,77% |
| SOXX | 1 | +0,3376 | +0,3376 | 0,650 | 0,2121 | no | SKIP_PYRAMIDING + RANK_OUTSIDE_TOP_N ×11 | +0,48% |
| BAC | 2 | +0,2901 | 0,0000 | 0,400 | 0,0707 | no | SKIP_THRESHOLD | −0,61% |
| SPCX | 3 | +0,2862 | 0,0000 | 0,433 | 0,0354 | sì | SKIP_THRESHOLD | — |
| **TSLA** | **5** | **+0,2813** | 0,0000 | 0,428 | 0,0354 | sì | **SKIP_THRESHOLD (−0,019 dal gate)** | **+5,51%** |
| LLY | 1 | +0,2739 | +0,2739 | 0,625 | 0,1768 | no | SKIP_THRESHOLD | — |
| SPY | 9 | +0,2000 | −0,2400 | 0,417 | 0,0196 | sì | fuori watchlist tradabile | — |
| META | 4 | 0,0000 | −0,2072 | 0,488 | 0,1114 | no | SKIP_THRESHOLD | −0,98% |
| CSCO | 2 | +0,2040 | +0,0400 | 0,500 | 0,0707 | sì | SKIP_THRESHOLD | +0,51% |
| **QCOM** | 1 | +0,1800 | +0,1800 | 0,600 | 0,0000 | no | SKIP_THRESHOLD | **+3,83%** |
| altri 17 | 33 | ≤ 0,166 | ≥ −0,115 | — | — | misto | SKIP_THRESHOLD | — |

**Distribuzione dei 423 SKIP_THRESHOLD** (gate attivo `feedback:entry_threshold:S4 = 0,30`,
letto direttamente da Redis):

| Banda \|score\| | Decisioni |
|---|---:|
| 0,000–0,021 | 195 |
| 0,036–0,058 | 81 |
| 0,062–0,072 | 27 |
| 0,115–0,147 | 26 |
| 0,166–0,207 | 29 |
| 0,216–0,240 | 12 |
| **0,274–0,290** | **53** |

53 decisioni si sono fermate nell'ultimo 9% sotto il gate.

**Nota sul moltiplicatore di velocity.** `execution_decisions.signal_score` è
`sentiment_signals.score × 1,20` per i segnali ensemble sul ramo d'ingresso
(`SIGNAL_VELOCITY_BOOST`, `portfolio_scheduler.py:4095`), e **× 1,00** sul ramo
d'uscita e per i single-model. Verificato su 13 coppie decisione↔segnale: rapporto
1,200000 esatto in 8 casi, 1,000000 negli altri. Il gate effettivo d'ingresso è quindi
0,25 per un simbolo in accelerazione e 0,375 per uno in decelerazione. **Non è un
difetto** — è la leva documentata — ma va tenuto presente leggendo i «0,019 dal gate»
di TSLA: alle 18:07 TSLA non ha ricevuto il boost.

---

## 7. Tabella ordini generati / eseguiti

**Ordini realmente inviati al broker: 4** (2 BUY + 2 SELL). Tutti **paper**
(`alpaca_paper`), tutti dentro la sessione RTH.

| Ora decisione | Strat. | Ticker | Azione | Qty | Prezzo atteso | Prezzo fill | Nozionale | Stato | Ordine | Segnale causante | Risk check | Anomalia |
|---|---|---|---|---:|---:|---:|---:|---|---|---|---|---|
| 17:22:00 | S4 | AVGO | BUY | 3,796000108 | mkt | **369,51** | 1.402,66 $ | FILLED 17:22:04 | `14247e85…` | id **9339** (+0,6526 → 0,7831 con boost) | gate 0,30 ✓ · anti-pyramiding ✓ · esposizione 31% < 50% ✓ | **sizing 70% del target combiner** ([DAY-008]) |
| 19:07:00 | S4 | AVGO | SELL (chiusura) | 3,796000108 | mkt | **369,379463** | 1.402,17 $ | FILLED | `ab3d0de2…` | id **9356** (0,000, conf 0,15) | `below_entry_gate` | **[DAY-001] [DAY-007]** |
| 19:37:00 | S4 | XLE | BUY | 22,005637331 | mkt | **63,86** | 1.405,28 $ | FILLED 19:37:04 | `14fd5207…` | id **9373** (+0,4208 → 0,5050) | gate ✓ · anti-pyramiding ✓ | sizing 70% ([DAY-008]) |
| 19:37:00 | **S1** | GOOGL | SELL (chiusura) | 1,922245427 | mkt | **338,67** | 651,00 $ | FILLED 19:37:04 | `2df01405…` | id **9375** (−0,3551) | `sentiment_reversal` soglia −0,35 | **[DAY-003]** — overlay S4 su posizione S1 |

**Ordini generati ma non inviati.** Ogni ciclo ha prodotto **5 `CombinedOrder`** in
`final_orders` (24 cicli → 120 target, 4 ordini reali). Esempio del ciclo 17:22:
AMD (peso 2,347%), CVX (2,794%), DELL (2,393%), **AVGO (2,000%)**, CRM (2,000%) — solo
AVGO è arrivata al broker, le altre quattro fermate da `SKIP_PYRAMIDING`. Vedi
[DAY-013b].

**Dispositions complete del ledger intent S4** (1.237 candidati osservati):

| Reason code | N |
|---|---:|
| `SKIP_ENTRY_GATE` | 423 |
| `SKIP_ENTRY_FRESHNESS` | 399 |
| `SKIP_STALE` | 205 |
| `SKIP_PYRAMIDING` | 112 |
| `SKIP_FALLBACK` | 55 |
| `RANK_OUTSIDE_TOP_N` | 33 |
| `SKIP_IDEMPOTENCY` | 4 |
| `RANK_LONG_ONLY` | 4 |
| **`SUBMITTED`** | **2** |

`RANK_OUTSIDE_TOP_N` per simbolo: SOXX 11, MU 7, NVDA 6, XLF 5, MRVL 4. **Quattro
su cinque (SOXX, MU, XLF, MRVL) sono già a libro con `stop_strategy = S1`** e hanno
comunque consumato slot del top-5 — vedi [DAY-015].

**Decision log** (`execution_decisions`, 443 righe): SKIP_THRESHOLD 423 ·
SKIP_PYRAMIDING 11 · SKIP_STALE 3 · BUY 2 · SELL 2 · SKIP_FALLBACK 2.
`signal_id` popolato su **13 righe su 443 (2,9%)** — [DAY-013a].

---

## 8. Tabella PnL / rendimento

### 8.1 Realizzato del giorno (`trades` con `exit_time` in data)

| Trade | Ticker | Sleeve | Ingresso | Uscita | Motivo | Qty | Lordo | Costi | **Netto** |
|---|---|---|---|---|---|---:|---:|---:|---:|
| 921 | AVGO | S4 | 2026-08-31 17:22 @ 369,51 | 2026-08-31 19:07 @ 369,379463 | `portfolio_sell` / `below_entry_gate` | 3,796 | −0,50 $ | 0,77 $ | **−1,27 $** |
| 258 | GOOGL | **S1** | 2026-07-10 14:07 @ 354,32 | 2026-08-31 19:37 @ 338,67 | `sentiment_reversal` | 1,922 | −30,08 $ | 0,13 $ | **−30,21 $** |
| | | | | | | | **−30,58 $** | **0,90 $** | **−31,48 $** |

Per sleeve: **S1 −30,21 $** · **S4 −1,27 $**. Nessun altro trade chiuso.

### 8.2 Non realizzato / NAV

| Grandezza | Apertura (13:30) | Chiusura (20:00) | Δ |
|---|---:|---:|---:|
| NAV | 109.832,71 $ | 109.833,17 $ | **+0,46 $** |
| vs previous close (109.802,54) | +30,17 $ | **+30,63 $ (+0,028%)** | |
| Unrealized P&L | +883,70 $ | +914,44 $ | +30,74 $ |
| Cash | 75.848,10 $ | 75.093,33 $ | −754,77 $ |
| Esposizione lorda | 30,94% | 31,63% (max 32,24%) | tetto 50% ✓ |
| Drawdown corrente | 0,735% | 0,735% (max 0,814%) | limite 5% ✓ |
| Posizioni aperte | 47 | 47 | = |

### 8.3 Scomposizione decisionale (dossier `decision_quality.summary`)

| Voce | USD | Confidenza |
|---|---:|---|
| P&L passivo delle 47 posizioni all'apertura | **−21,16** | misurata |
| Effetto *selection* (i 2 ingressi S4, MTM a fine seduta) | **+5,35** | misurata (provvisoria) |
| Effetto *exit* (le 2 uscite, contro il mantenimento a fine seduta) | **−4,95** | attribuita |
| P&L delle decisioni attive | **+0,40** | — |
| P&L intraday effettivo | **−20,76** | misurata |
| Componente mercato (β=1 su SPY) | −12,80 | attribuita |

Dettaglio delle due uscite (baseline: stessa qty tenuta fino al close):

* **AVGO** — `drift_post_exit = +3,65 $` → effetto uscita **−3,65 $**.
  Ricostruzione alternativa: MTM a fine seduta se mantenuta **+3,15 $** contro
  **−1,27 $** realizzati = **−4,42 $**.
* **GOOGL** — `drift_post_exit = +1,31 $` → effetto uscita **−1,31 $**.

Effetto *sizing* rispetto allo slot S4 di riferimento (2.200 $): AVGO **−1,79 $**,
XLE **−1,24 $**.

### 8.4 P&L economico cumulato dall'inizio della finestra di osservazione (2026-08-03)

| Sleeve | 2026-08-28 | **2026-08-31** | Δ giorno |
|---|---:|---:|---:|
| S1 | +655,37 $ | **+655,92 $** | +0,55 $ |
| S4 | −393,88 $ | **−397,41 $** | −3,53 $ |
| CONTAMINAZIONE | — | ≈ −34,84 $ | — |

Fonte: `docs/evidence/economic_pnl.json` (generato 2026-09-01T10:07). **S4 resta fuori
dalla banda ±200 $** della domanda di uscita n. 1.

### 8.5 Slippage e costi

Non misurabili: `trades.slippage_est` è **una copia esatta** di `cost_usd` su entrambe
le righe chiuse (0,7711415178408538 e 0,12992079991190342). Ricorrenza nota (F-015).
Costo modellato del giorno: 0,90 $ su 2.807,94 $ di nozionale movimentato (3,2 bps).

### 8.6 Contro-fattuali S4 registrati (`s4_exit_policy_events`)

| Politica | Ticker | D0 | Esito | Netto |
|---|---|---|---|---:|
| P0 runtime replay | AVGO | 2026-08-31 | `P0_TARGET_ZERO_BELOW_ENTRY_GATE` | −2,00 $ |
| P0 runtime replay | NVDA | 2026-08-28 | `P0_TARGET_ZERO_BELOW_ENTRY_GATE` | −23,29 $ |
| P1 time-only | CRM ×3 | 2026-08-27 | `P1_TIME_DUE` | **+52,29 / +30,11 / +59,86 $** |
| P1 time-only | TSLA | 2026-08-27 | `P1_TIME_DUE` | **+55,08 $** |
| P1 time-only | NVDA | 2026-08-27 | `P1_TIME_DUE` | −27,16 $ |
| P1 time-only | AVGO ×2, XLE, NVDA | — | `P1_HOLDING` | aperte |

Le due chiusure `P0_TARGET_ZERO_BELOW_ENTRY_GATE` di questa settimana sono entrambe
negative; le quattro chiusure P1 (tenuta a orizzonte fisso) sommano **+170,18 $**.
Osservazione, non taratura.

---

## 9. Analisi correttezza buy/sell

> **Avvertenza obbligatoria su `exit_mechanism` (#184).** Nessuna riga di questa seduta
> è pre-fix: le due uscite portano `exit_mechanism = below_entry_gate` (osservato dalla
> disposition del ciclo) e `NULL` (ramo `sentiment_reversal`, che non passa dal
> classificatore). Nessun conteggio di questo report deduce il meccanismo dall'età
> dell'ultimo segnale.

| Controllo | Esito | Evidenza |
|---|---|---|
| BUY generati solo quando consentito | ✅ | Entrambi sopra gate 0,30, `ema_pass=t`, anti-pyramiding verificato, ranking top-5 |
| SELL/exit generati correttamente | ⚠️ | Meccanicamente corretti; **due su due sono peggiorativi** rispetto al mantenimento ([DAY-001], [DAY-003]) |
| Stop-loss rispettati | ⚠️ **non verificabile** | `stop_decisions` **vuota dal 2026-07-14**; `stop_shadow_log` viva fino a 19:52 (solo ombra). Nessuno stop protettivo attivo osservabile |
| Signal flip rispettato | ✅ | GOOGL −0,3551 < −0,35 → `sentiment_reversal`; nessun flip ignorato |
| Max holding days rispettato | ✅ | Nessuna uscita per età nella seduta |
| Rebalance band rispettata | ✅ | `constraints_fired = []` su tutti e 24 i cicli; deadband 2% non violata |
| Ordini duplicati | ✅ nessuno | 0 gruppi (symbol, minuto) con conteggio > 1; 4 `SKIP_IDEMPOTENCY` hanno correttamente bloccato i ri-tentativi su AVGO (×3) e XLE (×1) |
| Ordini contrari ravvicinati | ⚠️ | AVGO BUY 17:22 → SELL 19:07 = **1 h 45 min**, con rationale registrato ma **basato su un articolo non informativo** ([DAY-001]). Sopra i 30 min, quindi non è un roundtrip di ciclo |
| BUY ripetuti > 3 senza SELL (pyramiding) | ✅ nessuno | Guard P0-05 attivo, 11 blocchi |
| Ordini su ticker non consentiti | ✅ nessuno | AVGO, XLE, GOOGL tutti in watchlist |
| Ordini fuori orario | ✅ nessuno | 17:22 / 19:07 / 19:37 — tutti dentro 13:30–20:00 UTC |
| Trade con dati stale | ✅ nessuno | 3 SKIP_STALE hanno bloccato segnali di 68–69 h |
| Trade con output LLM non valido | ⚠️ | **Sì sul ramo d'uscita**: AVGO chiusa su un segnale a confidenza 0,15, sotto il `min_confidence = 0,30` che il ranker impone all'ingresso ([DAY-007]) |
| Circuit breaker attivo | ✅ n/a | Esposizione max 32,24% (tetto 50%), drawdown max 0,814% (limite 5%). Nessun breaker scattato |
| Strategia disabilitata | ✅ | `strategies_run = ["S1","S4"]` su tutti e 24 i cicli, coerente con `config/trading.yaml` |
| Paper/live coerente | ✅ | `broker_environment = paper` e `mode = paper` su 94 snapshot su 94 |
| Idempotenza retry Celery | ✅ | 4 `SKIP_IDEMPOTENCY` nel ledger intent; nessun ordine duplicato a valle |
| Riconciliazione ordini↔fill↔posizioni | ✅ | 4 `ENTRY_RECONCILIATION` tutte `BROKER_FILLED` con `unattributed_quantity = 0` e `reconstructible = true`; **47 trade aperti a DB = 47 posizioni broker** |
| Segnali ribassisti azionabili | ❌ | NKE −0,405 (segno corretto, titolo −1,35%) fermato da `RANK_LONG_ONLY` in 4 cicli ([DAY-016]) |

---

## 10. Anomalie trovate

### [DAY-001] Tre listicle *"Whale Activity"* azzerano lo stato S4 di 13 ticker e forzano la liquidazione di AVGO

* **Tipo:** Bug
* **Area:** LLM / Signal / Orders
* **Evidenza:**
  * tabella: `news_log` id 9348–9360 · `sentiment_signals` id 9348–9360 ·
    `llm_responses` (signal_id 9355, 9356) · `execution_decisions` · `trades` id 921
  * timestamp: 18:01:00 → 18:31:00 UTC (ingest/score); SELL AVGO 19:07:00 UTC
  * query:
    ```sql
    SELECT n.id, left(n.title,40), n.ticker, s.score, s.confidence, s.model_id
    FROM news_log n JOIN sentiment_signals s ON s.news_log_id = n.id
    WHERE n.created_at::date = '2026-08-31' AND n.title ILIKE '%Whale Activity%';
    -- 13 righe, score = 0.0000 su tutte, model_id = 'ensemble:...', fallback_used = false
    SELECT signal_id, model_id, polarity, confidence, eligible, materiality, novelty, risk_flags
    FROM llm_responses WHERE signal_id IN (9355, 9356);
    -- glm: 0 / 0.10 / false / 0 / 0 / {ambiguous_entity, low_source_quality}
    -- oss: 0 / 0.20 / false / 0 / 0 / {ambiguous_entity}
    ```
* **Descrizione:** tre articoli della stessa famiglia sindacata Benzinga
  (*"8 Financials…"*, *"9 Consumer Discretionary…"*, *"10 Information Technology Stocks
  Whale Activity In Today's Session"*) sono stati mappati in fan-out su 13 ticker:
  BAC, GS, HOOD, MS, BABA, AMZN, NKE, TSLA, **AVGO**, DELL, MRVL, MU, NVDA.
  Entrambi i modelli li hanno correttamente giudicati non informativi
  (`polarity = 0`, `confidence` 0,10–0,20, `directness = unclear`,
  `event_type = other`, `materiality = 0`, `novelty = 0`,
  `risk_flags = {ambiguous_entity, low_source_quality}`, `eligible = false` su
  entrambi). Nonostante ciò il segnale è stato **persistito con `model_id =
  'ensemble:…'` e `fallback_used = false`**, e per `fetch_signals_for_cycle`
  (`ORDER BY symbol, fallback_used ASC, generated_at DESC`) è diventato *il* segnale
  di riferimento per S4 su tutti e 13 i simboli fino a fine seduta.
  Conseguenze osservate: **AVGO**, aperta alle 17:22 su un segnale +0,6526
  (conf 0,785, ensemble pieno, entrambi `eligible`) tratto da una nota JPMorgan
  issuer-specific, è passata a 0,000 alle 18:16 e **chiusa alle 19:07** con reason
  `[below_entry_gate] … generated 2026-08-31 18:16 UTC, score=+0.000`;
  **TSLA**, che alle 18:07 valeva 0,281 (miglior punteggio issuer-specific del giorno,
  dall'articolo *"Tesla Stock Surges Ahead of Cybercab Event"* delle 18:00), è tornata a
  0,000 alle 18:22 e ha chiuso **+5,51%**; **DELL** ha perso il suo +0,4204 delle 16:15;
  **NKE** il suo −0,4050 delle 17:17.
* **Impatto:** un articolo che entrambi i modelli hanno dichiarato privo di contenuto
  informativo ha comandato una decisione di liquidazione su denaro reale (paper) e ha
  cancellato il miglior segnale della seduta su un mover da +5,5%. Costo diretto
  misurabile sul solo caso AVGO: **4,42 $** (−1,27 $ realizzati contro +3,15 $ di MTM
  a fine seduta); il dossier misura lo stesso effetto come `drift_post_exit = 3,65 $`.
* **Severità:** High
* **Confidenza:** High
* **Azione consigliata:** *remediation ticket*, non patch. Un segnale i cui contributori
  hanno tutti `materiality = 0` **e** `novelty = 0` **e** `risk_flags ⊇
  {ambiguous_entity}` non deve poter sostituire un segnale precedente più forte sullo
  stesso simbolo. Due opzioni indipendenti dalla taratura: (a) non persistere affatto un
  segnale i cui contributori sono tutti `eligible = false` con materialità nulla,
  marcandolo `fallback_used = true` così che il filtro #108 lo escluda già oggi;
  (b) sostituire il "last wins" di `fetch_signals_for_cycle` con un aggregato che
  preferisce la magnitudine entro la finestra di freschezza. **Non toccare la soglia
  0,30** (congelata).
* **Test/monitor consigliato:** test di regressione con due segnali sullo stesso
  simbolo — uno issuer-specific forte, uno fan-out neutro e più recente — che asserisce
  che il ciclo *non* chiuda la posizione. Monitor giornaliero: conteggio di simboli il
  cui `score` passa da `> gate` a `0,000` per effetto di un articolo con
  `directness = unclear`.

### [DAY-002] TSLA fermata a 0,019 dal gate sul mover più forte della seduta

* **Tipo:** Anomalia (alpha miss)
* **Area:** Signal
* **Evidenza:**
  * tabella: `execution_decisions` (tick 18:07:03) · `sentiment_signals` id 9347 ·
    `docs/evidence/dossier/2026-08-31.json` → `candidati_miss[0]`
  * timestamp: segnale 18:00 UTC, decisione 18:07:03 UTC
  * snippet: `score 0.281 < feedback threshold 0.300` · `causa: BELOW_GATE` ·
    `accessible_opportunity_usd: 34.00`
* **Descrizione:** TSLA ha chiuso **+5,51%**. L'articolo issuer-specific
  *"Tesla Stock Surges Ahead of Cybercab Event"* (18:00, `subject_ticker = TSLA`,
  `relevance = ISSUER_SPECIFIC`, 1 solo ticker) ha prodotto +0,2813 — lo scarto più
  piccolo dal gate osservato nella serie (0,019). Gli altri 4 segnali TSLA del giorno
  sono tutti fan-out (`quota_righe_fanout = 0,80`).
* **Impatto:** il collo di bottiglia è la **magnitudine**, non il segno.
  `accessible_opportunity_usd = 34,00 $` su slot da 2.200 $ (entry 362,35 alle 14:52,
  exit 367,95 al close); `gross_opportunity_usd = 121,12 $`.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** **nessuna** in questa finestra — la soglia 0,30 è taratura
  congelata dalla Carta di osservazione. Registrare e basta: l'evidenza serve alla
  sintesi del 28/09. *(Già iscritta al ledger dal report alpha-miss dello stesso giorno,
  costo 205,40 $ insieme a QCOM: qui non si duplica.)*
* **Test/monitor consigliato:** serie giornaliera dello scarto minimo dal gate sui mover
  ≥ 3%, già prodotta dal dossier.

### [DAY-003] `sentiment_reversal` di S4 liquida una posizione S1 tenuta 52 giorni

* **Tipo:** Bug
* **Area:** Orders / PnL
* **Evidenza:**
  * tabella: `trades` id **258** · `execution_decisions` (tick 19:37:00, `signal_id` 9375)
  * timestamp: 2026-08-31 19:37:00 UTC (ingresso 2026-07-10 14:07)
  * snippet: `sentiment_reversal: score -0.355 < threshold -0.35` ·
    `stop_strategy = 'S1'` · `net_pnl = -30.21306173246186`
* **Descrizione:** l'overlay d'uscita di S4 ha chiuso GOOGL, posizione **S1** aperta il
  2026-07-10 (1.253,5 ore di tenuta), sul segnale −0,3551 delle 19:31 tratto da
  *"ChatGPT Ads Surge: How OpenAI's Rapid Expansion Imperils Google and Meta"*
  (`directness = competitor_readthrough` su entrambi i modelli). È esattamente il
  meccanismo che la **deroga #182(a)**, pre-registrata il 2026-08-25, dichiara di
  voler rimuovere: `sentiment_reversal` non deve chiudere posizioni che S4 non ha
  aperto. Al 2026-08-31 la deroga risulta **non ancora deployata**.
* **Impatto:** −30,21 $ realizzati **iscritti alla sleeve S1** ma generati da un
  segnale S4 — la serie realizzata di S1 continua a essere contaminata. Costo
  attribuito sul contro-fattuale corto (stessa qty tenuta fino al close):
  `exit_active_effect_usd = −1,31 $`.
* **Severità:** High
* **Confidenza:** High
* **Azione consigliata:** completare il deploy di #182(a). Fino ad allora **ogni giorno
  di finestra produce P&L S4 mescolato a P&L S1**, e la domanda di uscita n. 1 non è
  rispondibile sui dati raccolti.
* **Test/monitor consigliato:** asserzione che nessuna riga `execution_decisions` con
  `reason LIKE 'sentiment_reversal%'` chiuda un trade con `stop_strategy <> 'S4'`;
  alert immediato se accade.

### [DAY-004] L'alert EOD #324 si auto-annulla 0,4 secondi dopo l'apertura, al primo giro assoluto

* **Tipo:** Bug
* **Area:** Ops
* **Evidenza:**
  * file: `src/workers/mobile_alert_task.py:269-285` · `src/workers/held_news_loss_alert.py:186-201`
  * tabella: `mobile_events` (5 righe `kind = 'position'`)
  * timestamp: apertura 22:50:00.633–22:50:00.650 UTC, `resolved_at` 22:50:01.047–22:50:01.068 UTC
  * query:
    ```sql
    SELECT fingerprint, occurred_at, resolved_at, status, clear_observation_count
    FROM mobile_events WHERE fingerprint LIKE 'coverage:held_no_news_loss%';
    -- 5 righe, tutte status='recovered', delta occurred→resolved ≈ 0,42 s, clear_observation_count = 1
    ```
* **Descrizione:** il job `held-news-loss-alert` (#324, cron 22:50 UTC feriale) ha
  girato **per la prima volta in assoluto** questa sera e ha correttamente aperto 5
  incidenti WARNING (ASML 7 sedute senza news, MMM 9, NOK 2, TXN 2, UNH 3, tutte in
  perdita marcata). Il valutatore generico `mobile-alert-evaluation`, schedulato
  **ogni minuto**, chiude in `_evaluate` *ogni* fingerprint attivo non presente nel
  proprio `expected`:
  ```python
  # src/workers/mobile_alert_task.py:269
  for fp in active - expected:
      ...
      await self.store.record_observation(fingerprint=fp, ..., expected=False,
                                          recovery_observations_required=confirmations)
  ```
  Il set `expected` di quel valutatore contiene solo le condizioni che *lui* calcola
  (pipeline, esposizione, drawdown, DB/Redis); i fingerprint `coverage:held_no_news_loss:*`
  non ci sono mai, e `confirmations = 1` per essi. Risultato: incidente aperto e
  richiuso entro il tick successivo.
* **Impatto:** il canale che la deroga del 2026-08-31 ha appena costruito — e il cui
  scopo dichiarato è *«preservare l'incidente attivo invece di dichiarare una falsa
  rientranza»* — ha **vita utile inferiore al secondo**. Nessuna consegna è stata
  emessa (`mobile_notification_deliveries` vuota per la data). L'operatore non riceve
  nulla e la serie di incidenti su cui si dovrebbe misurare la cecità lato uscita
  nasce già chiusa: **l'evidenza raccolta da qui al 28/09 su questo canale sarebbe
  sbagliata**. Difetto strutturale, costo diretto non stimabile.
* **Severità:** High
* **Confidenza:** High
* **Azione consigliata:** *remediation ticket*. Il valutatore generico deve limitare la
  sweep di recovery ai fingerprint di cui è **proprietario** (per prefisso o per
  `kind`), invece di trattare `active - expected` come "tutto ciò che non vedo è
  rientrato". È un difetto di correttezza dell'osservabilità e passa il test di
  esenzione della Carta.
* **Test/monitor consigliato:** test d'integrazione che apre un incidente con un
  fingerprint estraneo, esegue un ciclo del valutatore generico e asserisce che
  l'incidente resti `open`. Monitor: allarme su qualunque incidente con
  `resolved_at - occurred_at < 60 s`.

### [DAY-005] 32 segnali `ensemble` su 63 non hanno un solo contributore `eligible`

* **Tipo:** Bug
* **Area:** LLM
* **Evidenza:**
  * tabella: `sentiment_signals` ⋈ `llm_responses`
  * timestamp: tutta la seduta
  * query:
    ```sql
    WITH s AS (SELECT ss.id, ss.model_id, count(*) FILTER (WHERE r.eligible) n_elig, count(r.*) n_resp
               FROM sentiment_signals ss LEFT JOIN llm_responses r ON r.signal_id = ss.id
               WHERE ss.created_at::date = '2026-08-31' GROUP BY 1,2)
    SELECT model_id LIKE 'ensemble%' AS ens, n_resp, n_elig, count(*) FROM s GROUP BY 1,2,3;
    -- ensemble/2/2 → 31 · ensemble/2/0 → 32 · single/2/0 → 33 · single/1/0 → 4 · finbert → 2
    ```
* **Descrizione:** su 102 segnali della seduta, solo **31 (30,4%)** poggiano su due
  risposte con `eligible = true`. Altri **32** sono etichettati `ensemble:…` con
  `fallback_used = false` pur avendo **zero** contributori eleggibili; 33 sono
  etichettati `single:…` pur avendo **due** risposte. È la mancata propagazione del
  retry a floor 0 introdotto con #90 (`sentiment.py:438`,
  `aggregator.aggregate(raw_outputs, weights=weights, min_confidence=0.0)`), il cui
  esito non viene riscritto su `llm_responses.eligible`.
* **Impatto:** oltre a rendere non auditabile chi ha davvero contribuito, l'etichetta
  `ensemble` + `fallback_used = false` è **ciò che permette a questi segnali di
  superare il filtro #108 e di vincere il tie-break di `fetch_signals_for_cycle`** —
  cioè è il meccanismo abilitante di [DAY-001]. Il loro \|score\| medio è 0,0070.
* **Severità:** High
* **Confidenza:** High
* **Azione consigliata:** *remediation ticket*: `eligible` deve riflettere il predicato
  effettivamente applicato al momento dell'aggregazione (incluso il retry a floor 0), e
  l'etichetta `single:`/`ensemble:` deve derivare dallo stesso insieme di contributori.
* **Test/monitor consigliato:** invariante di scrittura —
  `count(eligible) = numero di model_ids nel model_id del segnale` — verificata in
  test unitario sul percorso di persistenza e come check giornaliero sul DB.

### [DAY-006] `ensemble_std = 0,000` esatto proprio sulle coppie che divergono di più

* **Tipo:** Bug
* **Area:** LLM
* **Evidenza:**
  * tabella: `sentiment_signals.ensemble_std` ⋈ `llm_responses`
  * timestamp: tutta la seduta
  * snippet (11 coppie con gap ≥ 0,30):
    | Ticker | glm pol/conf | oss pol/conf | score finale | `ensemble_std` |
    |---|---|---|---:|---:|
    | TSLA | −0,20 / 0,30 | +0,35 / 0,65 | +0,2275 | **0,0000** |
    | ORCL | −0,25 / 0,30 | +0,20 / 0,50 | +0,1000 | **0,0000** |
    | SPY | −0,40 / 0,60 | 0,00 / 0,30 | −0,2400 | **0,0000** |
    | SPCX | +0,40 / 0,50 | 0,00 / 0,20 | +0,2000 | **0,0000** |
    | NVDA | −0,10 / 0,25 | +0,20 / 0,55 | +0,1100 | **0,0000** |
    | META | −0,15 / 0,60 | −0,60 / 0,75 | −0,2072 | 0,3182 |
    | AMD | +0,75 / 0,80 | +0,35 / 0,75 | +0,4924 | 0,2828 |
* **Descrizione:** quando uno dei due modelli è escluso dal filtro di eleggibilità, la
  deviazione standard è calcolata su **un solo contributore** e vale 0 per costruzione.
  Il risultato è che la metrica di divergenza è nulla esattamente nei casi di massimo
  disaccordo — TSLA con segni opposti e gap 0,55 risulta "accordo perfetto".
* **Impatto:** la varianza d'ensemble è inutilizzabile sia come diagnostica sia come
  futuro gate; ogni analisi che la usi per stimare l'affidabilità del segnale è
  invertita nei casi peggiori. Nessun costo diretto (non è oggi un gate d'ingresso).
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** *remediation ticket*: calcolare `ensemble_std` sull'insieme
  delle risposte ricevute, non su quelle sopravvissute al filtro; oppure persistere
  `NULL` quando i contributori sono meno di due, così che "0,000" non significhi due
  cose opposte.
* **Test/monitor consigliato:** test unitario con due polarità di segno opposto che
  asserisce `ensemble_std > 0`.

### [DAY-007] Asimmetria di confidenza fra ingresso e uscita: si compra a conf ≥ 0,30, si vende a conf 0,15

* **Tipo:** Bug
* **Area:** Signal / Orders
* **Evidenza:**
  * file: `src/strategies/s4/config.py:18` (`min_confidence: float = 0.3`) ·
    `src/strategies/s4/ranking.py:217` (`if sig.confidence < cfg.min_confidence: continue`) ·
    `src/workers/portfolio_scheduler.py:4107-4127` (gate applicato a `signals_df`
    **prima** che il ranker veda i segnali)
  * tabella: `sentiment_signals` id 9356 (`confidence = 0.15`) · `trades` id 921
  * timestamp: 2026-08-31 19:07:00 UTC
* **Descrizione:** per **aprire** una posizione S4 un segnale deve superare tre
  condizioni: \|score\| ≥ `feedback:entry_threshold` (0,30), `score` ≥ `min_score`
  (0,10) e **`confidence` ≥ `min_confidence` (0,30)**. Per **chiudere** una posizione
  non ne serve nessuna: il gate elimina il simbolo da `signals_df`, il simbolo non
  compare più in `target_weights`, e `NewsDrivenTactical` chiude qualunque simbolo
  assente. Il segnale che ha chiuso AVGO aveva `confidence = 0.15`, cioè **la metà del
  minimo che il ranker richiede per comprare sullo stesso ticker**.
* **Impatto:** un segnale troppo incerto per essere azionabile in acquisto è pienamente
  azionabile in vendita. È una asimmetria di rigore fra le due direzioni sullo stesso
  strumento e su denaro (paper) reale.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** *remediation ticket* — applicare `min_confidence` anche al
  ramo che azzera il peso, oppure trattare un segnale sotto `min_confidence` come
  "nessuna osservazione" (che preserva la posizione) invece che come "osservazione a
  zero" (che la chiude). **Distinto da F-013 e F-023**: quelli chiedono rispettivamente
  una banda d'isteresi sullo *score* e un'aggregazione al posto del *last-wins*;
  nessuna delle due correzioni impedirebbe un'uscita comandata da un segnale a
  confidenza 0,15 con score, poniamo, −0,40.
* **Test/monitor consigliato:** test che apre una posizione e le sottopone un segnale
  con `confidence < min_confidence`, asserendo che la posizione **non** venga chiusa.

### [DAY-008] `regime_mult` scala l'ordine inviato ma non il target del combiner: entrambi gli ingressi al 70% del peso

* **Tipo:** Bug
* **Area:** Orders / Risk
* **Evidenza:**
  * tabella: `portfolio_cycles.final_orders` (ciclo 17:22:00) vs `trades` id 921
  * timestamp: 2026-08-31 17:22:00 UTC
  * snippet:
    ```
    CombinedOrder(symbol='AVGO', side=BUY, quantity=5.42371023846147,
                  allocation_weight=0.020000000000000004)
    -- trades.qty effettiva: 3.796000108  →  5.42371023846147 × 0.70 = 3.79659717
    -- execution_decisions.regime_mult = 0.7 su tutte le 443 righe
    ```
* **Descrizione:** il combiner produce un target del 2,0% del NAV (5,4237 azioni AVGO
  su NAV ≈ 109,9 k$); l'ordine effettivamente inviato è esattamente `target × 0,70`,
  cioè il `regime_mult` corrente. Il target del combiner **non** viene riscritto, quindi
  al ciclo successivo il portafoglio risulta permanentemente sotto-peso rispetto
  all'obiettivo che il combiner crede di aver raggiunto, e il rabbocco non parte.
  Stesso comportamento su XLE (22,0056 sh contro un target di ~31,4).
* **Impatto:** entrambe le posizioni S4 aperte oggi valgono ~1.403 $ contro uno slot di
  riferimento di 2.200 $. Il dossier misura l'effetto *sizing* contro lo slot pieno in
  −1,79 $ (AVGO) e −1,24 $ (XLE). Ricalcolando invece contro il **target del combiner**
  (il difetto vero e proprio), il 30% non schierato avrebbe prodotto −0,54 $ su AVGO e
  +0,94 $ su XLE: **effetto netto +0,40 $ a favore oggi**. Il segno cambia ogni giorno;
  il difetto è che il portafoglio non è mai al peso che dichiara.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** *remediation ticket*: applicare `regime_mult` **a monte**, nel
  target del combiner, così che il peso obiettivo e il peso effettivo coincidano.
  Non è taratura — non cambia il valore di `regime_mult`, solo dove viene applicato.
* **Test/monitor consigliato:** invariante `submitted_notional / NAV ≈ allocation_weight`
  entro la deadband, verificata a ogni ciclo.

### [DAY-009] La finestra beat ignora il DST: i primi 37 minuti di sessione sono ciechi, ogni giorno

* **Tipo:** Bug
* **Area:** Ops / Data
* **Evidenza:**
  * file: `src/workers/celery_app.py` — `crontab(minute="*/15", hour="14-21", day_of_week="1-5")`
    su `sentiment-worker`, `run-news-ingestion`, `run-alpaca-ingestion`, `run-execution`;
    `crontab(minute="7,22,37,52", hour="14-21", …)` su `portfolio-cycle`
  * timestamp: 13:30:00 → 14:07:00 UTC
  * query:
    ```sql
    SELECT count(*) FROM news_log            WHERE created_at >= '2026-08-31 13:30' AND created_at < '2026-08-31 14:00'; -- 0
    SELECT count(*) FROM sentiment_signals   WHERE created_at >= '2026-08-31 13:30' AND created_at < '2026-08-31 14:00'; -- 0
    SELECT count(*) FROM execution_decisions WHERE tick_time  >= '2026-08-31 13:30' AND tick_time  < '2026-08-31 14:00'; -- 0
    SELECT count(*) FROM portfolio_cycles    WHERE timestamp  >= '2026-08-31 13:30' AND timestamp  < '2026-08-31 14:00'; -- 0
    ```
* **Descrizione:** in EDT il mercato apre alle 13:30 UTC, ma la prima finestra beat è
  alle 14:00 e il primo ciclo di portafoglio alle 14:07. **Zero** attività nei primi
  37 minuti — la fascia a più alto volume e dispersione della giornata. Simmetricamente,
  8 cicli fra 20:07 e 21:52 sono schedulati a mercato chiuso; qui sono stati
  correttamente saltati dal guard `get_clock()` (`portfolio_scheduler.py:2237`), quindi
  lo spreco è solo di scheduling.
* **Impatto:** il sistema stesso se ne accorge e lo segnala ogni mattina: alle 13:30:01
  apre due incidenti (*"Ciclo di portafoglio in ritardo"* critical, *"Segnali sentiment
  in ritardo"* warning) che si auto-recuperano alle 14:02 e 14:08. La degradazione è
  scritta anche in `portfolio_monitor_snapshots.degradations` su tutti gli snapshot
  13:30–14:00. Costo non stimabile per la singola giornata; il valore è nella ricorrenza.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** *remediation ticket*: esprimere le finestre in
  `America/New_York` (Celery lo supporta via `timezone` per-schedule) oppure allargare
  a `hour="13-20"` con guard di calendario già presente. È correttezza, non taratura.
* **Test/monitor consigliato:** test che, dato un calendario Alpaca, asserisca che
  esista almeno un ciclo entro 10 minuti dall'apertura per ogni seduta.

### [DAY-010] I log dei container della seduta analizzata non esistono più

* **Tipo:** Bug
* **Area:** Ops
* **Evidenza:**
  * comando: `docker ps --format '{{.Names}} {{.CreatedAt}}'` →
    `alembic-worker-1`, `alembic-worker-inference-1`, `alembic-beat-1`, `alembic-api-1`
    tutti **creati 2026-09-01 14:20:07 +0200**
  * `docker compose logs worker --since 60h | wc -l` → **115 righe**, la più vecchia
    del 2026-09-01 ~12:32 UTC
  * timestamp: redeploy del 2026-09-01 (fix prompt Variante A `bf5bef2e`)
* **Descrizione:** il forense del 2026-08-31 gira il 2026-09-01, dopo un redeploy che
  ha ricreato tutti i container applicativi. Nessuna riga di log della seduta analizzata
  è recuperabile: errori HTTP verso Ollama, timeout, retry, latenze per chiamata,
  eccezioni non propagate — tutto perduto.
* **Impatto:** l'intera FASE 4 (latenza media per modello, timeout, refusal) è
  ricostruibile **solo** da ciò che è finito a database. Le colonne mancano
  (`llm_responses` non ha durata), quindi la metrica non esiste. Non stimabile in
  dollari; il costo è la non-verificabilità.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** *remediation ticket*: driver di logging persistente
  (file/journald con rotazione) o spedizione dei log fuori dal container.
* **Test/monitor consigliato:** check giornaliero che l'orario della riga di log più
  vecchia disponibile preceda l'apertura della seduta da analizzare.

### [DAY-011] L'anti-pyramiding ha bloccato i segnali più forti della giornata, incluso il massimo assoluto

* **Tipo:** Anomalia
* **Area:** Signal / Risk
* **Evidenza:**
  * tabella: `execution_decisions` (11 righe `SKIP_PYRAMIDING`) ·
    `docs/evidence/dossier/2026-08-31.json` → `decision_quality.guards`
  * timestamp: 14:07:04 → 19:52:03 UTC
  * snippet: `P0-05 anti-pyramiding: gia' a libro dal 2026-08-28, sentiment +0.740, peso non allocato 2.0%` (CRM)
* **Descrizione:** 11 blocchi su 7 simboli. **CRM +0,740** — il punteggio più alto
  dell'intera seduta — bloccato perché già a libro dal 28/08. Poi AMD +0,591 e +0,504,
  CVX +0,544, DELL +0,504, SOXX +0,405, MU +0,407, XLF +0,346, MRVL 0,000.
* **Impatto:** il dossier calcola il costo del guard su orizzonte 1h e nozionale
  inteso per i 6 casi stimabili: **19,88 $ complessivi**, di cui DELL 9,79 $
  (nozionale inteso 2.003,23 $) e CRM 1,32 $. Rendimenti di seduta dei bloccati:
  CVX +2,12%, MU +2,77%, AMD +1,10%, SOXX +0,48%, CRM +0,60%, XLF −0,67%, MRVL −2,29%.
* **Severità:** Medium
* **Confidenza:** Medium
* **Azione consigliata:** **nessuna** in questa finestra — la politica di
  pyramiding è oggetto delle issue #182/#338 e ricade nella taratura congelata.
  Registrare la ricorrenza.
* **Test/monitor consigliato:** già coperto dal `guard_counterfactual` del dossier.

### [DAY-012] `ingestion_stats_daily.duplicates` (2.773) è 3,96× i `fetched` (700) sulla stessa riga

* **Tipo:** Anomalia (osservabilità)
* **Area:** Data
* **Evidenza:**
  * tabella: `ingestion_stats_daily`, riga `2026-08-31 / alpaca_benzinga`
  * timestamp: `updated_at = 2026-08-31 19:45:03`
  * snippet: `fetched=700, queued=353, duplicates=2773, discarded_stale=97`
* **Descrizione:** ricorrenza nota. I due contatori hanno denominatori diversi:
  `duplicates` accumula gli scarti su tutte le finestre di poll sovrapposte, `fetched`
  conta solo gli item nuovi dell'ultima. La riga letta da sola è ingannevole.
  Corroborato da `news_queue_drops`: 2.773 righe `duplicate_id` in stage `ingestion`.
* **Impatto:** nessun effetto sul money path; rende però illeggibile la resa reale del
  connettore (700 fetched → 353 queued → 97 righe persistite = **13,9%**).
* **Severità:** Low
* **Confidenza:** High
* **Azione consigliata:** *remediation ticket* di sola osservabilità — separare
  `duplicates_in_window` da `duplicates_cumulative`.
* **Test/monitor consigliato:** invariante `duplicates ≤ fetched` per finestra di poll.

### [DAY-013a] `execution_decisions.signal_id` è NULL su 430 righe su 443 (97,1%)

* **Tipo:** Bug
* **Area:** Data
* **Evidenza:**
  * query: `SELECT count(*), count(signal_id) FROM execution_decisions WHERE created_at::date='2026-08-31';` → **443 / 13**
  * ripartizione: SKIP_THRESHOLD 423 → 0 popolati · SKIP_PYRAMIDING 11 → 10 ·
    BUY 2 → 2 · SELL 2 → 1 · SKIP_STALE 3 → 0 · SKIP_FALLBACK 2 → 0
* **Descrizione:** la catena segnale → decisione → trade non è ricostruibile per chiave
  esterna. La SELL AVGO delle 19:07 — la decisione più costosa della giornata — ha
  `signal_id = NULL`: l'id 9356 è ricostruibile **solo** parsando il testo di `reason`
  (`generated 2026-08-31 18:16 UTC`).
* **Impatto:** ogni analisi causale di questo report ha dovuto ricongiungere per
  timestamp e testo. Non stimabile in dollari; è costo di audit.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** *remediation ticket*: popolare `signal_id` su tutti i rami,
  incluso quello d'uscita.
* **Test/monitor consigliato:** invariante — nessuna riga `BUY`/`SELL` con
  `signal_id IS NULL`.

### [DAY-013b] `portfolio_cycles.orders_count` somma 119 contro 4 ordini realmente inviati

* **Tipo:** Bug
* **Area:** Ops
* **Evidenza:**
  * tabella: `portfolio_cycles` (24 righe), `orders_count = 5` su 23 cicli e 4 su uno;
    `jsonb_array_length(final_orders) = orders_count` su ogni riga
  * `constraints_fired = []` su tutti e 24 i cicli
* **Descrizione:** `orders_count` conta i `CombinedOrder` *target*, non gli ordini
  inviati. Nella giornata: 119 target contro 4 ordini reali (2 BUY dai target, 2 SELL
  che nei target non compaiono affatto). `constraints_fired` vuoto anche nei 11 cicli
  in cui l'anti-pyramiding ha effettivamente bloccato ordini.
* **Impatto:** la telemetria del ciclo è inutilizzabile per capire cosa il sistema ha
  fatto. Nessun costo diretto.
* **Severità:** Low
* **Confidenza:** High
* **Azione consigliata:** *remediation ticket*: separare `targets_count` da
  `orders_submitted_count`, e popolare `constraints_fired`.
* **Test/monitor consigliato:** confronto giornaliero `SUM(orders_count)` vs ordini
  broker della seduta.

### [DAY-013c] `risk_reports.per_strategy_metrics` è vuoto: nessun drawdown per sleeve è sorvegliato

* **Tipo:** Bug
* **Area:** Risk
* **Evidenza:**
  * tabella: `risk_reports` id 80, `timestamp = 2026-08-31 22:30:01`
  * snippet: `per_strategy_metrics = {}` · `alerts = []` · `combined_drawdown = 0.012429`
* **Descrizione:** dopo la rimozione dell'entry sintetica `'portfolio'` dal path del
  drawdown per-strategia (#349), nessun drawdown per sleeve viene più calcolato.
  L'unico numero prodotto è quello aggregato di libro.
* **Impatto:** un drawdown concentrato su S4 (che nella finestra di osservazione è a
  −397 $) non può far scattare nessun alert. Nessun costo oggi.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** *remediation ticket*: ricostruire le metriche per sleeve dalla
  serie NAV attribuita, non da `portfolio_daily_state.daily_return`.
* **Test/monitor consigliato:** check giornaliero che `per_strategy_metrics` contenga
  una voce per ogni strategia in `strategies_run`.

### [DAY-013d] Il token bearer del protocollo forense è rifiutato su tutti gli endpoint REST

* **Tipo:** Bug
* **Area:** Ops
* **Evidenza:**
  * comando: `curl -H "Authorization: Bearer <token>" http://localhost:8001/api/positions`
  * risposta: `HTTP 403 {"detail":"Invalid or expired JWT token"}` — identica su
    `/positions`, `/orders`, `/decisions`, `/trades`, `/signals`
  * timestamp: 2026-09-01, durante la stesura di questo report
* **Descrizione:** ricorrenza nota — l'header corretto è `X-API-Key`, non
  `Authorization: Bearer`. Il prompt del cron forense specifica quello sbagliato.
* **Impatto:** tutta l'analisi è stata condotta su Postgres e sul dossier. Nessuna
  perdita di sostanza in questo caso (il DB è la sorgente autorevole), ma il protocollo
  dichiara una risorsa che non funziona.
* **Severità:** Low
* **Confidenza:** High
* **Azione consigliata:** correggere l'header nel prompt del cron.
* **Test/monitor consigliato:** smoke test degli endpoint elencati nel prompt.

### [DAY-014] Il resolver deterministico non ha prodotto un solo verdetto `RESOLVED` su 216 righe

* **Tipo:** Rischio
* **Area:** News / Data
* **Evidenza:**
  * query:
    ```sql
    SELECT decision, count(*), count(*) FILTER (WHERE tradable)
    FROM news_resolved_entities WHERE created_at::date = '2026-08-31' GROUP BY 1;
    -- NO_TRADE_NOT_TRADABLE               114 |   0
    -- NO_TRADE_LOW_RESOLUTION_CONFIDENCE  102 | 102
    ```
* **Descrizione:** tutte e 102 le righe che *hanno* prodotto un segnale portano il
  verdetto `NO_TRADE_LOW_RESOLUTION_CONFIDENCE` pur essendo `tradable = true`. Zero
  `RESOLVED`. È coerente con quanto già accertato sull'intera storia della tabella:
  `alias_match` e `llm_agreement` sono cablati a `false`, quindi il punteggio massimo
  raggiungibile (0,60) resta sotto la soglia 0,80.
* **Impatto:** il resolver oggi è **puramente consultivo** — CLAUDE.md lo dichiara
  (enforcement gated su golden set QX-01) — ma la conseguenza pratica è che, il giorno
  in cui l'enforcement venisse acceso, **bloccherebbe il 100% del flusso**. Nel
  frattempo l'unica barriera contro un ticker sbagliato è il fan-out del provider.
  Corollario di oggi: `risk_flags = ambiguous_entity` su **101 risposte su 196 (51,5%)**
  e nessun gate lo legge.
* **Severità:** High
* **Confidenza:** High
* **Azione consigliata:** *remediation ticket*: rendere raggiungibile un `RESOLVED`
  (cablare `alias_match` sugli alias interni già esistenti) **prima** che l'enforcement
  diventi decidibile. Non è taratura: senza questo, la domanda "il resolver funziona?"
  non è rispondibile al 28/09.
* **Test/monitor consigliato:** metrica giornaliera `quota_RESOLVED`; allarme se resta
  a 0 per più di N sedute.

### [DAY-015] Quattro dei cinque simboli che hanno consumato slot del top-5 erano già a libro con S1

* **Tipo:** Anomalia
* **Area:** Signal
* **Evidenza:**
  * tabella: `s4_intent_events` (33 righe `RANK_OUTSIDE_TOP_N`) ⋈ `trades`
  * snippet: SOXX 11 cicli, MU 7, NVDA 6, XLF 5, MRVL 4; SOXX/MU/XLF/MRVL tutti con
    `stop_strategy = 'S1'` e ingresso fra il 2026-07-14 e il 2026-07-30
* **Descrizione:** il ranking assegna gli slot top-N anche a simboli già detenuti da
  un'altra sleeve, che finiranno comunque bloccati dall'anti-pyramiding a valle.
* **Impatto:** oggi **nessun costo dimostrabile**: l'unico candidato fresco escluso
  (TSLA) era comunque sotto gate, quindi non è stato spiazzato da nessuno. Il difetto
  è latente.
* **Severità:** Low
* **Confidenza:** Medium
* **Azione consigliata:** *remediation ticket*: applicare il filtro anti-pyramiding
  **prima** del ranking, non dopo.
* **Test/monitor consigliato:** conteggio giornaliero di slot top-N occupati da simboli
  che saranno poi respinti da un guard.

### [DAY-016] Un segnale ribassista sopra gate, col segno corretto, non produce nulla

* **Tipo:** Anomalia
* **Area:** Signal
* **Evidenza:**
  * tabella: `s4_intent_events` (4 righe `RANK_LONG_ONLY`, simbolo NKE, 17:22→18:07) ·
    `sentiment_signals` (NKE −0,4050, conf 0,675, ensemble)
  * rendimento seduta NKE: **−1,35%**
* **Descrizione:** NKE ha prodotto il secondo punteggio assoluto più forte della giornata
  (−0,405, dall'articolo *"JPMorgan Cuts Nike 2027 Earnings Outlook, Flags China,
  Rising Competition"*), con il segno **corretto**. Il vincolo long-only lo rende non
  azionabile: 4 cicli, zero ordini. NKE non era a libro, quindi non c'era nemmeno una
  posizione da proteggere. Il segnale è poi stato azzerato alle 18:15 dal listicle di
  [DAY-001].
* **Impatto:** congetturale — su uno slot S4 tipico (2.200 $) il movimento non catturato
  vale **29,70 $**.
* **Severità:** Low
* **Confidenza:** Medium
* **Azione consigliata:** **nessuna** in questa finestra: il vincolo long-only è scelta
  di design, non difetto. Registrare la ricorrenza per la sintesi del 28/09.
* **Test/monitor consigliato:** serie giornaliera di segnali sopra gate col segno
  corretto e non azionabili per long-only.

### [DAY-017] Un giro di test contro il DB di produzione ha TRUNCATO la storia degli incidenti mobile del 2026-08-31

* **Tipo:** Bug
* **Area:** Ops / Data
* **Evidenza:**
  * file: `tests/conftest.py:10` — `os.environ.setdefault("DATABASE_URL", "postgresql://trading:trading@localhost:5432/trading")`,
    cioè **lo stesso DSN di `.env`** usato dallo stack vivo (esiste un database
    `test_db` sullo stesso server, e le fixture non lo usano);
    `tests/mobile_monitoring/test_incidents.py:47-59` e `tests/api/test_mobile_read.py:69-77`
    ```python
    await conn.execute("TRUNCATE TABLE mobile_notification_deliveries CASCADE")
    await conn.execute("TRUNCATE TABLE mobile_event_history CASCADE")
    await conn.execute("TRUNCATE TABLE mobile_events CASCADE")
    await conn.execute("TRUNCATE TABLE monitor_sessions CASCADE")
    await conn.execute("TRUNCATE TABLE monitor_devices CASCADE")
    await conn.execute("TRUNCATE TABLE monitor_users CASCADE")
    ```
  * timestamp: report scritto 2026-09-01T12:51Z con `mobile_events` popolata;
    `.pytest_cache/v/cache/lastfailed` modificata **2026-09-01T16:57:13Z**;
    ri-verifica alle 17:0xZ → tabelle vuote
  * query di verifica (eseguita in questa sessione):
    ```sql
    SELECT count(*) FROM mobile_events;                  -- 0
    SELECT count(*) FROM mobile_event_history;           -- 0
    SELECT count(*) FROM mobile_notification_deliveries; -- 0
    SELECT count(*) FROM monitor_users;                  -- 0
    SELECT count(*) FROM monitor_devices;                -- 0
    SELECT count(*) FROM monitor_sessions;               -- 0
    ```
* **Descrizione:** le sezioni 3 e [DAY-004] di questo report sono state costruite su
  `mobile_events` mentre la tabella era ancora popolata (timeline 13:30:01 → 22:50:01,
  con i timestamp al millisecondo dei 5 incidenti `coverage:held_no_news_loss:*`).
  Poche ore dopo, un giro della suite di test lanciato sulla macchina ha risolto
  `DATABASE_URL` sul database **di produzione** e ha eseguito le `TRUNCATE ... CASCADE`
  delle proprie fixture. La storia degli incidenti mobile — non solo del 2026-08-31, ma
  **dell'intera vita del sistema** — non esiste più, insieme a utenti, device e sessioni
  del monitor. Nessun'altra tabella risulta toccata: `news_log`, `sentiment_signals`,
  `llm_responses`, `trades`, `execution_decisions`, `portfolio_cycles`, `risk_reports`,
  `ingestion_stats_daily` sono integre e coincidono byte-per-byte con i numeri citati
  in questo report (ri-verificate in questa sessione).
* **Impatto:** è la ricorrenza nota F-028 («la suite di test scrive nel database di
  produzione») ma con un **raggio d'azione qualitativamente diverso**: non righe
  spurie inserite, bensì **cancellazione irreversibile di evidenza già raccolta**.
  Tre conseguenze concrete: (1) [DAY-004] non è più ri-verificabile da nessuno se non
  attraverso questo report; (2) la serie di incidenti su cui il canale #324 dovrebbe
  essere misurato da qui al 28/09 riparte da zero, e ogni conteggio di ricorrenza su
  quel canale è azzerato; (3) qualunque device mobile registrato dovrà ri-autenticarsi.
  Costo diretto in dollari non stimabile — il costo è la distruzione della prova.
* **Severità:** High
* **Confidenza:** High
* **Azione consigliata:** *remediation ticket*. Due misure indipendenti e nessuna delle
  due è taratura: (a) `tests/conftest.py` deve puntare per default a `test_db` (già
  esistente sullo stesso server) e **rifiutarsi di girare** se il DSN risolto coincide
  con `config.DATABASE_URL` di produzione — fail-closed, non `setdefault`;
  (b) revocare al ruolo usato dai test il privilegio `TRUNCATE` sulle tabelle vive.
  Supera il test di esenzione della Carta: senza la correzione, ogni giro di test può
  cancellare l'evidenza delle settimane precedenti, e l'osservazione al 28/09 sarebbe
  costruita su una serie con buchi non dichiarati.
* **Test/monitor consigliato:** guardia in `conftest.py` che asserisca
  `urlparse(dsn).path != urlparse(config.DATABASE_URL).path` e aborti la sessione
  altrimenti; check giornaliero sul conteggio monotòno non decrescente delle tabelle
  append-only (`mobile_events`, `news_log`, `trades`, `execution_decisions`).

---

## 11. False positive e aree risultate corrette

Verificate esplicitamente e **risultate corrette**:

1. **Nessun ordine fuori orario.** I 4 ordini stanno fra 17:22 e 19:37 UTC, dentro
   13:30–20:00. I cicli 20:07–21:52 schedulati dal beat sono stati saltati dal guard
   `get_clock()` come da design (`portfolio_scheduler.py:2237-2240`).
2. **Nessun ordine duplicato, nessuna race condition.** Zero gruppi
   `(symbol, minuto)` con più di un ingresso; i 4 `SKIP_IDEMPOTENCY` del ledger intent
   (AVGO ×3, XLE ×1) mostrano il guard che lavora correttamente sui cicli successivi
   all'ingresso.
3. **Nessun roundtrip sotto i 30 minuti.** Il più corto è AVGO a 1 h 45 min.
4. **Nessuna SELL su sentiment positivo (bug A5).** Le due SELL sono su score 0,000
   (`below_entry_gate`) e −0,3551 (`sentiment_reversal`).
5. **Nessun ordine generato senza segnale.** Entrambi i BUY hanno `signal_id` popolato
   e verificabile (9339, 9373). Nessun ordine broker orfano.
6. **Nessun segnale generato senza news.** Tutti i 102 segnali hanno `news_log_id`
   popolato e la riga corrispondente esiste.
7. **Nessun timestamp futuro.** `published_at > fetched_at` su 0 righe.
8. **Riconciliazione perfetta.** 47 trade aperti a DB = 47 posizioni broker;
   `unattributed_quantity = 0` su tutte e 4 le riconciliazioni lifecycle;
   `reconstructible = true` su tutte.
9. **Nessun circuit breaker violato.** Esposizione 30,9%→32,2% contro tetto 50%;
   drawdown 0,73%→0,81% contro limite 5%; `alerts = []` nel risk report.
10. **Paper/live coerente.** 94 snapshot su 94 con `broker_environment = paper` e
    `mode = paper`.
11. **Nessuna eccezione silenziosa nella generazione del dossier.** Il dossier 2026-08-31
    si è generato completo (schema 2.6, 2,03 MB, `missingness = []`,
    `simboli_senza_dati = []`) — le regressioni F-044/F-045 non si sono ripresentate.
12. **`fallback_used` non è un falso positivo di FinBERT.** Solo 2 segnali su 102
    provengono davvero da FinBERT; gli altri 37 sono degradazioni a modello singolo,
    correttamente etichettate `single:…`.
13. **La latenza d'ingestione è migliorata in modo netto.** p50 `published→scored`
    **36,0 min** contro la mediana storica di ~1h50m registrata su F-019: consuma il 30%
    della finestra di freschezza, non il 92%. **Non riportata come anomalia oggi.**
14. **Il moltiplicatore di velocity (×1,20 / ×0,80) non è un bug.** Verificato che il
    fattore 1,200000 esatto sulle decisioni d'ingresso corrisponde a
    `SIGNAL_VELOCITY_BOOST = 0.20` (`config.py:309`), applicato in
    `portfolio_scheduler.py:4095` **prima** del gate. Leva documentata, non anomalia —
    ma va tenuta presente leggendo gli scarti dal gate.
15. **Ollama non è mai caduto.** 196 risposte su 196 persistite, nessuna finestra
    d'ensemble vuota; i 3 buchi di scoring (25–30 min) coincidono con assenza di news,
    non con guasti. F-049 **non ricorre oggi**.
16. **L'anti-pyramiding e i guard hanno lasciato traccia.** A differenza di F-031
    storico, tutti gli 11 blocchi hanno una riga `execution_decisions` con causa
    esplicita e nozionale non allocato.

---

## 12. Dati mancanti o non accessibili

| Dato | Stato | Query/risorsa che servirebbe |
|---|---|---|
| Log applicativi del 2026-08-31 | **Perduti** (redeploy 2026-09-01 14:20 CEST) | Driver di logging persistente — [DAY-010] |
| Latenza per chiamata LLM | **Non esiste** | Colonna `duration_ms` su `llm_responses` |
| Timeout / refusal / output invalidi per modello | **Non distinguibili** | Le risposte non persistite non lasciano traccia; solo `fallback_used` a valle |
| Endpoint REST `/api/*` | **403** su tutti | Usare `X-API-Key` invece di `Authorization: Bearer` — [DAY-013d] |
| Slippage reale | **Non misurato** | `trades.slippage_est` è copia di `cost_usd`; servirebbe il mid NBBO al submit |
| Stop protettivi | **Nessuna riga dal 2026-07-14** | `stop_decisions` vuota; solo `stop_shadow_log` (38.430 righe, viva fino a 19:52) |
| Drawdown per sleeve | **Vuoto** | `risk_reports.per_strategy_metrics = {}` — [DAY-013c] |
| Costo del guard `SKIP_THRESHOLD` in USD | **Non calcolato** | Il dossier calcola `guard_cost_usd` solo per `SKIP_PYRAMIDING` post-2026-08-19 (nozionale inteso noto); per `SKIP_THRESHOLD` resta `null` su 33 righe su 33 |
| `net_opportunity_usd` dei candidati miss | **`null`** su TSLA e QCOM | `TradeCostCalculator` non produce il costo di roundtrip per quei tier |
| Consegne push degli alert | **Nessuna** | `mobile_notification_deliveries` vuota — nessun device registrato |
| Storia incidenti mobile (`mobile_events`, `mobile_event_history`) | **Distrutta** il 2026-09-01 ~16:57Z, dopo la stesura di questo report | Nessuna: il dato non è recuperabile. Le righe citate in §3 e [DAY-004] sopravvivono **solo** in questo report — [DAY-017] |
| Utenti / device / sessioni del monitor | **Azzerati** dalla stessa `TRUNCATE` | Ri-registrazione manuale — [DAY-017] |

---

## 13. Raccomandazioni immediate

> Vincolo della Carta di osservazione: **nessuna taratura**. Tutto ciò che segue è
> correttezza — supera il test *«se non lo correggo, l'evidenza che raccolgo nelle
> prossime settimane è sbagliata?»*.

1. **Completare il deploy di #182(a)** ([DAY-003]). Finché `sentiment_reversal` chiude
   posizioni non-S4, il P&L di S4 e quello di S1 restano mescolati e la domanda di
   uscita n. 1 non è rispondibile. La deroga è già concessa: manca solo il deploy.
2. **Impedire che un segnale a materialità e novità nulle sostituisca un segnale forte**
   ([DAY-001] + [DAY-005]). La correzione minima e non tarante: marcare
   `fallback_used = true` un segnale i cui contributori sono **tutti** `eligible = false`,
   così che il filtro #108 — che già esiste — lo escluda dal ranking e dal tie-break di
   `fetch_signals_for_cycle`. Nessuna soglia toccata.
3. **Limitare la sweep di recovery del valutatore mobile ai propri fingerprint**
   ([DAY-004]). Un incidente che vive 0,4 secondi non è un'osservazione: è rumore che
   cancella l'evidenza di #324 mentre viene prodotta.
4. **Applicare `min_confidence` anche al ramo d'uscita** ([DAY-007]). Non è una nuova
   soglia: è la stessa già configurata per l'ingresso, applicata simmetricamente.
5. **Popolare `execution_decisions.signal_id` su tutti i rami** ([DAY-013a]). Senza,
   ogni analisi causale futura ricomincerà da parsing di stringhe.
6. **Rendere persistenti i log dei container** ([DAY-010]). Ogni redeploy cancella la
   giornata che il forense deve analizzare: è la quattordicesima occorrenza.

Da **non** fare in questa finestra: toccare il gate 0,30, il vincolo long-only, la
politica di pyramiding, `regime_mult`, `SIGNAL_VELOCITY_BOOST` o la soglia
`sentiment_reversal`. Tutto congelato al 2026-09-28.

---

## 14. Test e monitor da aggiungere

| # | Tipo | Descrizione | Copre |
|---|---|---|---|
| T1 | Test regressione | Due segnali sullo stesso simbolo: issuer-specific forte, poi fan-out neutro più recente. Asserisce che la posizione **non** venga chiusa | [DAY-001] |
| T2 | Invariante DB | `count(llm_responses WHERE eligible) = numero di model_id nell'etichetta del segnale`, per ogni segnale | [DAY-005] |
| T3 | Test unitario | Due polarità di segno opposto → `ensemble_std > 0` (mai 0,000 esatto) | [DAY-006] |
| T4 | Test regressione | Posizione aperta + segnale con `confidence < min_confidence` → posizione **preservata** | [DAY-007] |
| T5 | Invariante ciclo | `submitted_notional / NAV ≈ allocation_weight` entro deadband | [DAY-008] |
| T6 | Test calendario | Per ogni seduta del calendario Alpaca esiste un ciclo entro 10 min dall'apertura | [DAY-009] |
| T7 | Test integrazione | Incidente con fingerprint estraneo + un ciclo del valutatore generico → resta `open` | [DAY-004] |
| T8 | Monitor giornaliero | Allarme su qualunque `mobile_events` con `resolved_at − occurred_at < 60 s` | [DAY-004] |
| T9 | Invariante DB | Nessuna riga `execution_decisions` con `decision IN ('BUY','SELL')` e `signal_id IS NULL` | [DAY-013a] |
| T10 | Asserzione cross-sleeve | Nessuna decisione `sentiment_reversal` chiude un trade con `stop_strategy <> 'S4'` | [DAY-003] |
| T11 | Metrica giornaliera | `quota_RESOLVED` del resolver; allarme se 0 per N sedute consecutive | [DAY-014] |
| T12 | Check log | L'orario della riga di log più vecchia precede l'apertura della seduta da analizzare | [DAY-010] |
| T13 | Metrica giornaliera | Numero di simboli il cui score passa da `> gate` a `0,000` per un articolo con `directness = unclear` | [DAY-001] |
| T14 | Check risk report | `per_strategy_metrics` contiene una voce per ogni strategia in `strategies_run` | [DAY-013c] |

---

## 15. Ticket tecnici suggeriti

| Priorità | Titolo | Difetto | Perché passa il test di esenzione |
|---|---|---|---|
| **P0** | *`tests/conftest.py` fail-closed sul DSN di produzione + revoca `TRUNCATE` al ruolo dei test* | [DAY-017] | Un giro di test può cancellare l'evidenza già raccolta: l'osservazione al 28/09 avrebbe buchi non dichiarati |
| **P0** | *Deploy di #182(a): `sentiment_reversal` non chiude posizioni non-S4* | [DAY-003] | Ogni seduta ulteriore mescola P&L S1 e S4: la domanda 1 diventa non rispondibile |
| **P0** | *Un segnale con tutti i contributori `eligible=false` deve essere marcato `fallback_used=true`* | [DAY-001], [DAY-005] | Oggi comanda liquidazioni e cancella i segnali migliori: il comportamento osservato non è quello di design |
| **P1** | *`mobile_alert_task` deve recuperare solo i fingerprint di cui è proprietario* | [DAY-004] | Il canale #324 nasce chiuso: l'evidenza sulla cecità lato uscita non si accumula |
| **P1** | *`min_confidence` applicato simmetricamente a ingresso e uscita* | [DAY-007] | Le uscite sono decise da segnali che il sistema stesso giudica inaffidabili |
| **P1** | *`eligible` e l'etichetta `single:`/`ensemble:` derivati dallo stesso insieme di contributori* | [DAY-005] | Il 69% dei segnali è etichettato in modo non verificabile |
| **P1** | *Finestre beat in `America/New_York` invece di UTC fissa* | [DAY-009] | 37 minuti di sessione ciechi ogni giorno, sistematicamente |
| **P2** | *`regime_mult` applicato al target del combiner, non all'ordine* | [DAY-008] | Il portafoglio non è mai al peso che dichiara |
| **P2** | *`signal_id` popolato su tutti i rami di `execution_decisions`* | [DAY-013a] | La catena causale non è ricostruibile per chiave |
| **P2** | *`ensemble_std` calcolato sull'insieme ricevuto, o `NULL` sotto due contributori* | [DAY-006] | La metrica di divergenza è invertita nei casi peggiori |
| **P2** | *Resolver: rendere raggiungibile un verdetto `RESOLVED`* | [DAY-014] | Senza, l'enforcement non sarà mai accendibile e la domanda resta aperta |
| **P2** | *Log dei container persistenti al redeploy* | [DAY-010] | Il forense analizza giornate di cui non esiste più telemetria |
| **P3** | *`per_strategy_metrics` ricostruito dalla serie NAV attribuita* | [DAY-013c] | Nessun drawdown per sleeve sorvegliato |
| **P3** | *Anti-pyramiding applicato prima del ranking top-N* | [DAY-015] | Slot consumati da candidati che saranno respinti a valle |
| **P3** | *`targets_count` separato da `orders_submitted_count`; `constraints_fired` popolato* | [DAY-013b] | Telemetria del ciclo non interpretabile |
| **P3** | *`duplicates_in_window` separato da `duplicates_cumulative`* | [DAY-012] | Resa reale del connettore illeggibile |
| **P3** | *Correggere l'header di autenticazione nel prompt del cron forense* | [DAY-013d] | Il protocollo dichiara una risorsa non funzionante |

---

## 16. Stato sistema

### Ollama

**UP per l'intera sessione.** Nessuna finestra di indisponibilità: **0 ore di
downtime**.

* 196 risposte persistite su 196 attese (98 per modello, `glm-5.2:cloud` e
  `gpt-oss:20b-cloud`), nessun buco d'ensemble.
* I 3 intervalli senza segnali (14:47→15:16 · 16:15→16:45 · 17:20→17:45, 25–30 min)
  coincidono con assenza di news in arrivo, non con guasti: in ognuno di essi il
  monitor mobile ha aperto e recuperato un warning *"Segnali sentiment in ritardo"*
  entro 2–7 minuti.
* Coppia attiva confermata via Redis: `config:sentiment_llm_models = glm52,gptoss`;
  pesi LOO-ICIR `{glm-5.2:cloud: 0.70, gpt-oss:20b-cloud: 0.30}` (`source: auto_apply`).
* Gate d'ingresso letto da Redis: `feedback:entry_threshold:S4 = 0.3` (baseline, nessun
  ratchet attivo).

### FinBERT / fallback

| Metrica | Valore |
|---|---|
| Segnali con `fallback_used = true` | **39 / 102 = 38,2%** |
| Di cui **FinBERT vero** (`model_id = 'finbert'`) | **2 / 102 = 2,0%** (NVDA 17:02, GOOGL 18:48) |
| Di cui degradazione a **modello singolo** | 37 / 102 = 36,3% |
| Decisioni `SKIP_FALLBACK` | 2 / 443 = **0,45%** (ORCL 17:52, CAT 18:52) |
| Dispositions `SKIP_FALLBACK` nel ledger intent | 55 / 1.237 = 4,4% |
| Ordini generati da un fallback | **0** — il filtro #108 li esclude dal ranking BUY |

### Worker restart

* **Nessun riavvio durante la seduta**: le 24 esecuzioni di `portfolio-cycle`
  (14:07→19:52, cadenza :07/:22/:37/:52 senza salti) e i 94 snapshot mobile
  (13:30→20:00 continui) non presentano interruzioni.
* **Redeploy successivo**: tutti i container applicativi (`api`, `worker`,
  `worker-inference`, `beat`) ricreati il **2026-09-01 14:20:07 +0200**, per il deploy
  del prompt Variante A. Ha cancellato i log della seduta analizzata — [DAY-010].
* `alembic-postgres-1` e `alembic-redis-1` up da 25 ore, `alembic-frontend-1` da 25 ore
  (immagine del 2026-08-15).

### Riepilogo salute

| Indicatore | Valore | Limite | Esito |
|---|---:|---:|:---:|
| Esposizione lorda (max) | 32,24% | 50% | ✅ |
| Drawdown corrente (max) | 0,814% | 5% | ✅ |
| Herfindahl | 0,0258 | — | ✅ |
| Posizioni DB vs broker | 47 = 47 | — | ✅ |
| Quantità non attribuite | 0 | 0 | ✅ |
| Cicli eseguiti | 24 / 24 attesi in RTH | — | ✅ |
| Alert emessi | 5 warning EOD | — | ⚠️ auto-annullati ([DAY-004]) |

---

*Report generato in sola lettura il 2026-09-01. Nessuna modifica al codice, nessun
ordine inviato, nessun worker avviato. Fonti primarie: PostgreSQL `alembic-postgres-1`,
`docs/evidence/dossier/2026-08-31.json` (schema 2.6), `docs/evidence/economic_pnl.json`,
Redis `alembic-redis-1`, sorgenti in `src/`.*

*Ri-verifica indipendente eseguita il **2026-09-01T17:00–17:15Z** in una seconda sessione
read-only: ri-eseguite contro `alembic-postgres-1` le query portanti di §4 (righe
`ingestion_stats_daily` 700/353/2.773/97 e 1.627/5/2/1.620 — identiche), §5 (98+98
risposte, 31+31 `eligible`), §6 (63 ensemble + 32 + 5 single + 2 FinBERT), §7
(443 decisioni: 423/11/3/2/2/2; 430 `signal_id` NULL), §8 (trade 921, 258, 922),
[DAY-001] (13 segnali id 9348–9360, tutti i contributori `eligible=false`),
[DAY-005] (ensemble 2/0 → 32, ensemble 2/2 → 31, single 2/0 → 33),
[DAY-006] (11 coppie con gap ≥ 0,30, di cui 6 con `ensemble_std = 0,0000`, tutte
etichettate `single:`), [DAY-009] (`crontab(hour="14-21")`, `timezone="UTC"`),
[DAY-011] (`guard_cost_usd` `SKIP_PYRAMIDING` = 19,88 $ su 6 casi stimabili, 1 `null`),
[DAY-013a/b/c/d] (443/13 · 119 vs 4 · `per_strategy_metrics = {}` · `Bearer` → 403 e
`X-API-Key` → 200), [DAY-014] (102 `NO_TRADE_LOW_RESOLUTION_CONFIDENCE`, 114
`NO_TRADE_NOT_TRADABLE`, zero `RESOLVED`). **Tutte confermate senza scostamenti.**
L'unica evidenza non più ri-verificabile è quella su `mobile_events` — vedi [DAY-017].*
