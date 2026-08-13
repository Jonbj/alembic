# Forensic Daily Report — 2026-08-12

Analista: sessione autonoma (Trading Systems Forensic Analyst / Backend / Quant Ops).
Generato: 2026-08-13, in sola lettura.
Periodo di osservazione attivo (giorno 8 di 40, carta `docs/evidence/OBSERVATION_CHARTER.md`):
**nessuna taratura proposta**. I ticket suggeriti riguardano solo la correttezza dell'evidenza.

Rapporto complementare: `docs/ALPHA_MISS_REPORT_2026-08-12.md` (già scritto e già
riversato nel ledger). Questo report **non ri-conta** le occorrenze che quello ha
registrato per il 2026-08-12 (F-001, F-002, F-006, F-008, F-012, F-020, F-030, F-031,
F-035): le cita e basta.

---

## 1. Executive summary

Giornata operativa **funzionalmente pulita nel percorso ordini** e sporca nella
strumentazione. 24 cicli di portafoglio (14:07→19:52 UTC), 157 segnali su 46 simboli,
5 ordini realmente inviati al broker paper (3 BUY: NVDA, INTC, SPCX; 2 SELL: IBM, NVDA),
tutti tracciabili a un segnale ensemble a due modelli su articoli ticker-specifici.
Nessun ordine duplicato, nessun ordine fuori orario, nessun ordine senza segnale,
conteggio posizioni riconciliato ciclo per ciclo (48→47→48→49→50→49). Ollama up al 100%,
zero fallback FinBERT, `mode=paper` confermato in tutti gli 82 snapshot.
Il freeze del ratchet #191 è **verificato vivo**: il loss-feedback si è attivato alle
19:30 ("5 consecutive losses") e la soglia è rimasta a 0,300.

Il rosso è altrove. La **rilevazione di regime è morta in silenzio da due giorni**: la
chiave Redis porta `detected_at 2026-08-11T13:30:44` e ha TTL 72h, quindi non è mai
scaduta e il fallback deterministico su VIX non è mai entrato — l'intera giornata ha
girato con `regime_mult 0.70` derivato da macro del giorno prima. Un segnale SPCX sopra
il gate (+0,385 alle 16:01) è stato scartato come single-model e **non ha lasciato
nessuna riga nel Decision Log**; SPCX è poi entrata alle 18:52 quasi 5% più in alto.
70 ordini target contro 5 inviati. I log dei container del 12 agosto non esistono più.

P&L: NAV 110.298,73 → 110.461,10 (**+162,37**), ma la parte S4 della giornata vale
**−61,89** (−27,40 realizzati su IBM e NVDA, −34,49 di MTM aperto su INTC e SPCX).

## 2. Verdict finale

**OK con warning.**

Il percorso segnale→decisione→ordine→fill→posizione è corretto e riconciliato su tutti
e 5 gli ordini della giornata. I warning sono di **osservabilità e di freschezza degli
input**, non di esecuzione: regime stale da 24h non rilevato ([DAY-001]), un segnale
sopra gate scomparso dal Decision Log ([DAY-002]), telemetria di ciclo fuorviante
([DAY-005]), log distrutti ([DAY-012]). Nessuno di questi ha prodotto un ordine
sbagliato oggi; tre di essi **degradano l'evidenza** che il periodo di osservazione sta
raccogliendo, ed è per questo che sono segnalati.

---

## 3. Timeline del 2026-08-12 (tutti gli orari UTC)

Timezone: **non ambiguo**. `src/workers/celery_app.py:51` dichiara `timezone="UTC"` e
tutte le colonne DB sono `timestamptz`. Sessione NYSE 13:30–20:00 UTC (EDT).

| ora UTC | fase | componente | evento | esito |
|---|---|---|---|---|
| 07:00 | pre-market | `regime-detector` (queue inference) | rilevazione regime | **nessuna scrittura** su `regime:current` (vedi [DAY-001]) |
| 13:30 | apertura | `regime-detector-premarket` | seconda rilevazione (rete P0-09) | **nessuna scrittura** — resta il valore dell'11/08 |
| 13:30 | apertura | portfolio monitor | primo snapshot: NAV 110.511,19, 48 posizioni, `mode=paper` | ok |
| 13:30–14:07 | apertura | beat `hour="14-21"` | **nessun ciclo di portafoglio né di scoring**: 37 min di sessione scoperti | [DAY-011] |
| 14:01 | market | ingest `alpaca_benzinga` | prima riga in `news_log` (articolo pubblicato 12:55) | latenza ~66 min |
| 14:07 | market | portfolio-cycle #910 | S1+S4, 0 ordini finali; 2 righe `SKIP_STALE` (GM 18,4h, QQQ 20,1h) | ok |
| 14:15 | market | sentiment worker | NVDA +0,385 (single:glm-5.2, fallback) | scartato da #108, nessuna riga Decision Log |
| 14:22 | market | portfolio-cycle #911 | **SELL IBM** 5,067182 az. @233,2737 — `[unknown] FIX-D re-admitted … weight is 0 anyway` | net −26,47 · [DAY-004] |
| 14:45 | market | ingest `gdelt_gkg` | prima riga GKG (published 14:00) | latenza ~45 min |
| 15:52 | market | portfolio-cycle #917 | primi `SKIP_PYRAMIDING`: SPY (+0,427), TSM (+0,382) | guard P0-05, tracciato |
| 16:01 | market | sentiment worker | **SPCX +0,385** (single:gpt-oss, fallback) | scartato, **zero righe Decision Log** · [DAY-002] |
| 16:30 | market | sentiment worker | NOK +0,560 (ensemble) — punteggio più alto della giornata | NOK già a libro da S1 → `SKIP_PYRAMIDING` 16:37 |
| 17:15 | market | sentiment worker | NVDA +0,343 (ensemble, conf 0,650, std 0,141) da "What's Going On With Nvidia Stock on Wednesday?" | valido |
| 17:22 | market | portfolio-cycle #923 | **BUY NVDA** 5,500045 az. @223,9655 (target 7,857 → 70%) | fill ok · [DAY-006] |
| 17:45 | market | sentiment worker | INTC +0,419 (ensemble, conf 0,675, std 0,035) da "Intel's $20 Billion Capital Raise…" | valido |
| 17:52 | market | portfolio-cycle #925 | **BUY INTC** 12,034897 az. @102,2925 (target 17,193 → 70%) | fill ok |
| 18:30 | market | sentiment worker | NVDA +0,023 da rassegna macro multi-ticker | ultimo per simbolo → sotto gate |
| 18:45 | market | sentiment worker | SPCX +0,628 (ensemble, conf 0,825) da "SpaceX Stock Surges Past $135 IPO Price" | valido |
| 18:52 | market | portfolio-cycle #929 | **BUY SPCX** 8,294554 az. @148,36 (target 11,853 → 70%) | fill ok |
| 19:07 | market | portfolio-cycle #930 | **SELL NVDA** @223,84 — `[below_entry_gate] … score=+0,023` | net −0,93, roundtrip 1h45 · [DAY-003] |
| 19:07 | market | S4 filtro #108 | `SKIP_FALLBACK` IWM (unica riga di questo tipo del giorno) | perimetro ristretto |
| 19:15 | market | sentiment worker | TSM +0,450 e MS +0,420, entrambi single-model | scartati; entrambi già a libro |
| 19:30 | post | loss-feedback S4 | trigger "5 consecutive losses", `threshold_before 0.3 → threshold_after 0.3` | **freeze #191 tenuto** |
| 19:45 | market | ultimo segnale del giorno | INTC 0,000 (single:gpt-oss) | — |
| 19:52 | market | portfolio-cycle #933 | ultimo ciclo, 5 ordini target, 0 inviati | [DAY-005] |
| 20:00 | chiusura | portfolio monitor | NAV 110.461,10, `nav_change_today +162,37`, 49 posizioni | riconciliato |
| 21:00 | batch | decay monitor | 12 righe: `sharpe` CRITICAL su S1, S2 e S4 con **identico** `actual_value −6,571` | [DAY-008] |
| 22:30 | batch | risk report | `combined_drawdown 0,0124` + alert "drawdown 15,7% exceeds 10%" | [DAY-007] |

---

## 4. Tabella news ingest

### Per fonte (`ingestion_stats_daily` + `news_log`)

| fonte | fetched | queued | duplicates | scartati no-ticker | stale | parse fail | righe in `news_log` | copertura oraria |
|---|---|---|---|---|---|---|---|---|
| `alpaca_benzinga` | 729 | 383 | **3202** | 0 | 0 | 0 | 70 | published 12:55→17:46 |
| `gdelt_gkg` | 2033 | 125 | 33 | 1895 | 0 | 0 | 87 | published 14:00→18:00 |

`duplicates` (3202) è **4,4× i `fetched`** per Benzinga — contatore non fidato, quarto
giorno di fila (3122 il 10/08, 2628 l'11/08). Vedi [DAY-009].

### Qualità

| controllo | esito |
|---|---|
| righe totali `news_log` | 157 (111 URL distinti, 46 ticker) |
| `content_hash` valorizzato | 157/157 |
| hash distinti | 111 → 46 righe sono fan-out multi-ticker dello stesso articolo (F-012, già a ledger) |
| duplicati cross-provider (stesso titolo, fonti diverse) | 0 |
| timestamp futuri (`published_at > created_at`) | **0** |
| news scartate per età (`news_queue_drops`) | 161 Benzinga (età media 6,8h), 32 GKG (17,5h) |
| latenza mediana `created_at − published_at` | Benzinga **86,7 min** (30,1–119,4) · GKG **75,3 min** (45,4–105,8) |
| `signal_freshness_minutes` dichiarato | **30** in `config/trading.yaml:149` → la latenza è ~2,9× la finestra · [DAY-010] |
| metodo di estrazione | Benzinga 70/70 `source_metadata`; GKG 87/87 `org_lookup` |

### Ticker con più copertura

| ticker | righe news | segnali | max score | min score | fallback |
|---|---|---|---|---|---|
| MS | 18 | 18 | +0,420 | −0,220 | 8 |
| GS | 12 | 12 | +0,100 | −0,080 | 4 |
| NVDA | 11 | 11 | +0,385 | −0,027 | 6 |
| MU | 10 | 10 | +0,360 | −0,203 | 3 |
| INTC | 7 | 7 | +0,419 | −0,120 | 3 |

Il cluster MS/GS/DB (35 righe `org_lookup`) resta l'artefatto di ticker resolution già
registrato su F-020 dall'alpha-miss di oggi, con la novità NOK/Nokian Renkaat.

**Confidenza dell'analisi ingest: Alta** sulle righe persistite, **Bassa** sui contatori
aggregati (`duplicates` incoerente) e **nulla** sui retry/failure di rete, perché i log
del giorno non esistono più ([DAY-012]).

---

## 5. Tabella performance modelli LLM

Fonte: `llm_responses` (157 chiamate per modello) e `sentiment_signals` (157 segnali).
**La latenza per modello non è misurabile**: `llm_responses` non ha colonna di durata e
i log del giorno sono persi.

| modello | risposte | mancate | polarity media | conf. media | polarity min/max | righe `eligible=true` |
|---|---|---|---|---|---|---|
| `gpt-oss:20b-cloud` | 157 | 0 | +0,088 | 0,396 | −0,40 / +0,80 | 31 |
| `glm-5.2:cloud` | 155 | 2 | +0,093 | 0,272 | −0,50 / +0,80 | 31 |

| esito d'ensemble | segnali | quota | note |
|---|---|---|---|
| `ensemble:glm-5.2+gpt-oss` | 104 | 66,2% | di cui **31 con entrambi i modelli ≥ 0,40 di confidence**; i restanti **73 nascono dal retry a floor 0** (#90), cioè da due letture che i modelli stessi hanno marcato a bassa confidenza |
| `single:gpt-oss:20b-cloud` | 46 | 29,3% | `fallback_used=true` → esclusi dal ranking BUY (#108) |
| `single:glm-5.2:cloud` | 7 | 4,5% | idem |
| `finbert` | **0** | 0% | **nessun fallback deterministico: Ollama up al 100%** |

Distribuzione confidence per modello: `gpt-oss` 77 risposte ≥0,40 / 80 <0,40;
`glm-5.2` 38 ≥0,40 / **117 <0,40**. Il modello con peso maggiore in ensemble
(`glm-5.2`, 0,601) è quello che dichiara meno confidence.

**Disaccordo forte** (std di polarity al limite di `divergence_threshold` 0,30):
SPY 0,283 (score +0,356), TSM 0,283 (+0,319), SOXX 0,283 (+0,318) — tutti e tre
sopra il gate d'ingresso. Vedi [DAY-017].

**Score estremi del giorno**: SPCX +0,628, NOK +0,560, TSM +0,450, MS +0,420,
INTC +0,419; sul lato negativo MS −0,220, AMD −0,220, HD −0,204, MU −0,203.

### Verifica funzionale del percorso LLM

| domanda | risposta | evidenza |
|---|---|---|
| l'output LLM è validato prima del signal store? | **Sì, strutturalmente**: `LLMSentimentOutput` è uno schema Pydantic passato a `run_ensemble_query`; polarity e confidence sono clampate in `EnsembleAggregator.aggregate`. Nessuna verifica *semantica* (RAG/supervisor) | `src/llm/ensemble.py:284-325` |
| l'ensemble gestisce la varianza alta? | **La rileva ma non la usa come gate d'ingresso**: `std ≥ divergence_threshold` fa cadere in fallback, ma `ensemble_std` non è mai letto nel percorso BUY | [DAY-017] |
| le news duplicate pesano più volte? | Dedup per `content_hash` + `UNIQUE(url,ticker)`: 0 duplicati cross-provider oggi. Il fan-out multi-ticker (46 righe su 157) è per design, non duplicazione | §4 |
| la stessa news può generare segnali multipli? | Sì, uno per ticker; ma il guard `SIGNAL_DUPLICATE_SKIP` impedisce che lo **stesso** `signal_id` generi due ingressi nella stessa sessione (8 blocchi oggi: INTC ×4, SPCX ×4) | `audit_log` |
| confidence bassa riduce il peso? | Sì: `score = polarity × confidence` e il peso in aggregazione è `confidence × weight`. Verificato su NVDA 7433: 0,6×0,7 e 0,4×0,6 → +0,343 | `sentiment_signals` |
| i modelli sono chiamati offline? | **Sì.** Tutte le chiamate stanno nella queue `inference`; il ciclo di portafoglio legge solo da Postgres/Redis | `celery_app.py:93` |
| un'allucinazione può entrare in decisione? | **Sì, con un'unica difesa.** Non esiste supervisor agent né verifica RAG delle affermazioni quantitative: l'unico filtro è la soglia sullo score. Se entrambi i modelli sbagliano nella stessa direzione, il gate non se ne accorge | [DAY-017] |

---

## 6. Tabella segnali finali per ticker

46 simboli hanno prodotto almeno un segnale; 42 compaiono in `execution_decisions`.
Gate S4 attivo: `feedback:entry_threshold:S4 = 0,300`.

### Segnali sopra il gate (score assoluto ≥ 0,300)

| ticker | ora | score | conf | std | ensemble? | esito | motivo |
|---|---|---|---|---|---|---|---|
| SPCX | 18:45 | +0,628 | 0,825 | 0,071 | sì | **BUY 18:52** | — |
| NOK | 16:30 | +0,560 | 0,800 | 0,000 | sì | `SKIP_PYRAMIDING` 16:37 | già a libro da S1 dal 14/07 |
| TSM | 19:15 | +0,450 | 0,750 | — | **no (single)** | scartato #108 | già a libro da S1 |
| MS | 19:15 | +0,420 | 0,700 | — | **no (single)** | scartato #108 | già a libro (legacy 10/07) |
| INTC | 17:45 | +0,419 | 0,675 | 0,035 | sì | **BUY 17:52** | — |
| AMD | 17:00 | +0,396 | 0,600 | 0,071 | sì | `SKIP_PYRAMIDING` 17:07 | già a libro da S1 |
| RIO | 16:45 | +0,388 | 0,775 | 0,000 | sì | `SKIP_PYRAMIDING` 16:52 | già a libro (legacy) |
| **SPCX** | **16:01** | **+0,385** | 0,550 | — | **no (single)** | **scartato #108, nessuna riga** | **[DAY-002]** |
| NVDA | 14:15 | +0,385 | 0,700 | — | **no (single)** | scartato #108 | nessuna riga |
| MU | 19:45 | +0,360 | 0,575 | 0,106 | sì | `SKIP_PYRAMIDING` 19:52 | già a libro da S1 |
| SPY | 15:45 | +0,356 | 0,600 | **0,283** | sì | `SKIP_PYRAMIDING` 15:52 | già a libro (legacy) |
| NVDA | 17:15 | +0,343 | 0,650 | 0,141 | sì | **BUY 17:22** | — |
| MU | 16:30 | +0,330 | 0,600 | 0,177 | sì | `SKIP_PYRAMIDING` 16:37 | già a libro |
| TSM | 15:45 | +0,319 | 0,650 | **0,283** | sì | `SKIP_PYRAMIDING` 15:52 | già a libro |
| SOXX | 17:15 | +0,318 | 0,550 | **0,283** | sì | `SKIP_PYRAMIDING` 17:37 | già a libro |

Lettura: **15 segnali sopra il gate, 3 sono diventati ordini**. 8 fermati dal guard
anti-pyramiding P0-05 (F-031, già a ledger: il costo è verificato a 0 perché il grosso
del movimento era nel gap di apertura), 4 dal filtro fallback #108.

### Distribuzione delle decisioni

| decisione | righe | con `signal_id` |
|---|---|---|
| `SKIP_THRESHOLD` | 398 | 0 |
| `SKIP_PYRAMIDING` | 12 | 12 |
| `BUY` | 3 | 3 |
| `SKIP_STALE` | 2 | 0 |
| `SELL` | 2 | 0 |
| `SKIP_FALLBACK` | 1 | 0 |
| **totale** | **418** | **15 (3,6%)** |

Simboli con segnale ma senza alcuna riga di decisione: AAPL, AMAT, AXP, **BRKB**,
HOOD, META. BRKB è il caso di canonicalizzazione [DAY-018].

---

## 7. Tabella ordini generati / eseguiti

Motore: `execution.engine = portfolio` (`config/trading.yaml:142`) → solo
`portfolio-cycle` invia ordini. Ambiente: **paper**, confermato in 82/82 snapshot
(`broker_environment='paper'`, `mode='paper'`, `source='alpaca_paper'`).

| # | ora decisione | strategia | ticker | azione | qty target | qty eseguita | prezzo fill | stato | segnale | risk check | anomalia |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 14:22:00 | S4 | IBM | SELL (close) | tutta | 5,067182 | 233,2737 | filled | — (`signal_id` NULL) | hold_min ok (19,25h) | uscita per scadenza wall-clock, nessun contro-segnale · [DAY-004] |
| 2 | 17:22:00 | S4 | NVDA | BUY | 7,857491 | **5,500045** | 223,9655 | filled | 7433 (+0,343) | gate 0,30 ✓, freshness ✓, no-pyramiding ✓ | eseguita al 70% del target · [DAY-006] |
| 3 | 17:52:00 | S4 | INTC | BUY | 17,193208 | **12,034897** | 102,2925 | filled | 7450 (+0,419) | idem | idem |
| 4 | 18:52:00 | S4 | SPCX | BUY | 11,853492 | **8,294554** | 148,36 | filled | 7482 (+0,628) | idem | idem; entrata al 92° percentile del range del giorno (F-030) |
| 5 | 19:07:00 | S4 | NVDA | SELL (close) | tutta | 5,500045 | 223,84 | filled | — (`signal_id` NULL) | hold_min 105 min > 90 ✓, exit_persistence 3 cicli ✓ | roundtrip 1h45 · [DAY-003] |

**Ordini target mai inviati: 65.** Somma `portfolio_cycles.orders_count` = 70 sui 24
cicli, contro 5 ordini realmente sottomessi. Vedi [DAY-005].

Controlli negativi superati:
- nessun ordine con timestamp fuori 13:30–20:00 UTC;
- nessuna coppia di ordini identici nello stesso minuto;
- nessun BUY ripetuto ≥3 volte senza SELL intermedio;
- nessun ordine su ticker fuori watchlist;
- nessun ordine generato senza una riga `execution_decisions` corrispondente;
- `stop_decisions` vuota, **coerente col design**: `risk.stop_loss = 0.0`
  (`config/trading.yaml:182`, decisione paper del 15/07), quindi lo stop protettivo è
  disabilitato per scelta, non per guasto.

---

## 8. Tabella PnL / rendimento

Fonte prezzi: barre Alpaca SIP `adjustment="all"` e `portfolio_monitor_snapshots`.

### Libro complessivo

| voce | valore |
|---|---|
| NAV apertura (`previous_close_equity`) | 110.298,73 |
| NAV chiusura (20:00 UTC) | 110.461,10 |
| **variazione giornaliera** | **+162,37** |
| unrealized_pnl a chiusura | 1.341,68 |
| gross exposure | 31,23% |
| current_drawdown | 0,147% |
| posizioni aperte | 49 |

### PnL realizzato (2 chiusure, entrambe S4)

| trade | ticker | entrata | uscita | qty | gross | costo modellato | **net** | drift post-uscita |
|---|---|---|---|---|---|---|---|---|
| 700 | IBM | 11/08 19:07 @238,01 | 12/08 14:22 @233,2737 | 5,067182 | −24,00 | 2,4695 (20,25 bps) | **−26,47** | +13,71 (IBM risale a 235,98) |
| 701 | NVDA | 12/08 17:22 @223,9655 | 12/08 19:07 @223,84 | 5,500045 | −0,69 | 0,2443 (1,75 bps) | **−0,93** | +1,38 |
| | | | | | | | **−27,40** | |

### PnL non realizzato sulle posizioni aperte oggi

| trade | ticker | entrata | close 12/08 | qty | **MTM a fine giornata** |
|---|---|---|---|---|---|
| 702 | INTC | 17:52 @102,2925 | 100,9501 | 12,034897 | **−16,16** |
| 703 | SPCX | 18:52 @148,36 | 146,1500 | 8,294554 | **−18,33** |
| | | | | | **−34,49** |

### Sintesi per origine

| origine | PnL 12/08 |
|---|---|
| posizioni **aperte il 12/08** (NVDA chiusa, INTC, SPCX) | **−35,42** |
| posizioni aperte **prima** del 12/08 e chiuse oggi (IBM) | **−26,47** realizzati |
| **totale attribuibile a S4 sulla giornata** | **−61,89** |
| resto del libro (S1 + legacy, 46 posizioni, solo MTM) | **≈ +224,26** (differenza col NAV) |

Beffa strutturale della giornata: i tre titoli comprati hanno **tutti chiuso in verde**
(NVDA +3,03%, INTC +3,32%, SPCX +9,65%) e le tre posizioni sono **tutte in perdita**.
Il titolo è scelto bene, il momento no — misurato e già registrato su F-030 dall'alpha-miss.

### Costi e slippage

| ticker | `cost_bps` | `cost_usd` | `slippage_est` | tier applicato |
|---|---|---|---|---|
| IBM | 20,246 | 2,4695 | **2,4695** | default (`tier_d`, small-cap illiquid) |
| NVDA | 1,748 | 0,2443 | **0,2443** | `tier_a` |
| INTC | 5,248 | 0,6461 | — | `tier_b` |
| SPCX | 20,248 | 2,4917 | — | default (`tier_d`) |

`slippage_est` è **identico** a `cost_usd` su tutte le righe: lo slippage reale non è
misurato ([DAY-014]). IBM a 20,25 bps è il tier sbagliato per una mega-cap ([DAY-015]).

**Cosa manca per un PnL completo**: non esiste una tabella di posizioni riconciliata
lato broker (le posizioni vivono solo su Alpaca; il DB tiene `trades` aperti). Il PnL
per strategia sulle 11 posizioni legacy del 10/07 **non è attribuibile** perché
`stop_strategy` è NULL (F-002, già a ledger). Query che servirebbe:
`SELECT symbol, qty, avg_entry_price, unrealized_pl FROM <positions_snapshot>` — la
tabella non esiste; oggi si può solo ricostruire da `trades` + barre giornaliere.

---

## 9. Analisi correttezza buy/sell

| controllo | esito | evidenza |
|---|---|---|
| BUY solo quando consentito | **OK** | 3 BUY, tutti con score ensemble ≥ 0,343 > gate 0,300, tutti su simboli non a libro, tutti dentro `max_signal_age_hours=4` |
| SELL/exit corretti | **OK con riserva** | 2 SELL, entrambe con `weight → 0`. NVDA per caduta sotto il gate (corretto per design), IBM per scadenza wall-clock del segnale (design discutibile: [DAY-004]) |
| stop-loss rispettati | **N/A** | `stop_loss = 0.0` per decisione operativa; nessuno stop da rispettare. Nota: `alert:unprotected_position:WDC` è ancora acceso |
| signal flip rispettato | **OK** | nessun BUY su score negativo, nessuna SELL su score sopra gate salvo IBM (segnale stale +0,323 ri-ammesso e poi ri-eliminato — F-035) |
| max holding days | **Violato per omissione** | WDC (trade 373, S4) aperta dal 21/07: **22 giorni** contro `max_signal_age_hours = 4` ([DAY-016]) |
| rebalance band | **Assente per costruzione** | gate d'ingresso 0,300 e soglia d'uscita 0 coincidono: nessuna isteresi ([DAY-003]) |
| ordini duplicati | **Nessuno** | 5 ordini, 5 `order_id` distinti, nessuna coppia nello stesso minuto |
| ordini contrari ravvicinati | **1 caso, con rationale** | NVDA BUY 17:22 → SELL 19:07 (105 min). Rationale presente e leggibile; guard `hold_minimum_minutes=90` e `exit_persistence_cycles=2` entrambi rispettati |
| ticker non consentiti | **Nessuno** | tutti in watchlist |
| ordini fuori orario | **Nessuno** | 14:22–19:07 UTC |
| trade su dati stale | **1, per design** | la SELL IBM nasce da un segnale di 19,4h ri-ammesso da FIX-D |
| trade su output LLM non valido | **Nessuno** | i 3 BUY hanno tutti 2 risposte modello valide con confidence ≥0,60 |
| circuit breaker | **Non attivo** | `fallback_counters.consecutive_fallback = 0`, resettato alle 19:45; `system:halted_by_operator` assente |
| strategia disabilitata | **N/A** | S1 e S4 attive in tutti i 24 cicli |
| paper/live coerente | **OK** | `paper` in 82/82 snapshot |
| idempotenza retry Celery | **OK** | guard `SIGNAL_DUPLICATE_SKIP` (8 blocchi) impedisce che lo stesso `signal_id` generi due ingressi nella stessa sessione; i logger `SKIP_STALE`/`SKIP_FALLBACK` sono deduplicati via chiavi Redis |
| riconciliazione ordini↔fill↔posizioni | **OK** | conteggio posizioni negli snapshot: 48 → 47 (SELL IBM 14:22) → 48 (BUY NVDA 17:22) → 49 (BUY INTC 17:52) → 50 (BUY SPCX 18:52) → 49 (SELL NVDA 19:07). Ogni transizione cade nello snapshot immediatamente successivo all'ordine |

### Nota obbligatoria su `exit_mechanism` (#184)

Le due righe SELL del giorno portano `exit_mechanism` = `unknown` (IBM) e
`below_entry_gate` (NVDA). Sono **post-fix**: si riconoscono dal testo del motivo, che
in un caso dichiara esplicitamente *"the mechanism that zeroed it is not recorded, so
this exit is NOT a signal expiry, see #184"*. Nessuna riga di questo report conta o
interpreta etichette `expired`/`whipsaw` dedotte per età: sul 2026-08-12 non ce ne sono.

---

## 10. Anomalie trovate

### [DAY-001] La rilevazione di regime è morta in silenzio da due giorni e il TTL a 72h nasconde il guasto

* **Tipo:** Bug
* **Area:** Ops / Risk
* **Evidenza:**
  * chiave: `regime:current` (Redis), `macro:vix:latest`
  * timestamp: contenuto `"detected_at":"2026-08-11T13:30:44.850442Z"`; TTL residuo misurato il 13/08 alle ~12:36 UTC = **89.646 s**
  * snippet: `REGIME_REDIS_TTL_SECONDS = 259200` (72h, `src/config.py:352`). 2026-08-11 13:30:44 + 72h = 2026-08-14 13:30 → residuo atteso ~24h54m. **Coincide**: l'ultima scrittura è dell'11/08.
  * schedule: `regime-detector` alle 07:00 e `regime-detector-premarket` alle 13:30 (`celery_app.py:122,134`) — nessuna delle due ha scritto il 12/08 né il 13/08.
* **Descrizione:** `src/workers/regime.py` esce con `return` (non con eccezione) in **almeno 12 rami di fallimento** (fetch macro, validazione VIX, validazione yield curve, momentum, entrambi gli LLM giù, data quality parziale, label non valida). Celery registra il task come *succeeded*. Il commento in `celery_app.py:128` assume che al fallimento «`regime:current` resta assente» e che scatti il fallback deterministico VIX di `portfolio_scheduler.py:315` — ma il TTL è di 72h, quindi **la chiave non sparisce mai**: al posto del fallback si usa un regime vecchio. Il 12/08 l'intera giornata ha girato con `regime_mult = 0,70` e `vix = 14,9` datati 11/08 13:30.
* **Impatto:** il moltiplicatore di sizing che scala **ogni** ordine S4 (e con esso i −61,89 della giornata) deriva da macro di 24h prima. Con TTL 72h il sistema può operare fino a tre giorni su un regime obsoleto senza che nessun allarme scatti. Per il periodo di osservazione è peggio: le size registrate nella finestra non sono attribuibili al regime del giorno.
* **Severità:** High
* **Confidenza:** High
* **Azione consigliata:** far fallire il task (raise) invece di `return` silenzioso, e/o allineare il TTL alla cadenza (≤ 26h) così che l'assenza attivi davvero il fallback VIX previsto da P0-09. È correttezza, non taratura: senza, ogni giorno della finestra può essere sizato su un input scaduto.
* **Test/monitor consigliato:** monitor che confronti `now() − detected_at` con 26h e allerti; test di regressione che asserisca che un fallimento di `detect_regime` propaghi l'errore al risultato Celery.
* **Ledger:** F-017

### [DAY-002] Un segnale SPCX sopra il gate viene scartato come single-model e non lascia nessuna traccia nel Decision Log

* **Tipo:** Bug
* **Area:** LLM / Signal
* **Evidenza:**
  * tabella: `sentiment_signals` id **7393**, `2026-08-12 16:01:51`, symbol SPCX, score **+0,385**, confidence 0,550, `model_id='single:gpt-oss:20b-cloud'`, `fallback_used=true`, articolo *"Elon Musk Says AI Will Be SpaceX's Biggest Business by September"* (published 14:37)
  * tabella: `execution_decisions` — righe SPCX del giorno: 14:37, 14:52, 15:07 (`SKIP_THRESHOLD score 0.000`), poi **nulla fino al BUY delle 18:52**. Il segnale delle 16:01 non compare in nessuna forma.
  * codice: `portfolio_scheduler.py:3433-3437` — `_record_fallback_drops` logga `SKIP_FALLBACK` **solo** per i simboli il cui unico segnale del lotto è fallback. SPCX aveva anche il segnale 7354 (14:30, ensemble, score 0,000), quindi il perimetro lo esclude.
* **Descrizione:** il segnale è single-model perché `glm-5.2` è rimasto sotto `min_confidence 0,40`. Il retry a floor 0 introdotto con #90 sana esattamente questo caso nel ramo *ensemble* (73 segnali su 104 oggi nascono da lì), ma **non è propagato al ramo single-model**: lì il modello sotto soglia viene semplicemente buttato, il segnale è marcato `fallback_used` e il filtro #108 lo esclude dal ranking BUY. In più il perimetro di #151 fa sì che l'esclusione sia **invisibile**.
* **Impatto:** SPCX è entrata alle 18:52 a 148,36 invece che al ciclo delle 16:07 a ~141,73, cioè **il 4,7% più in alto**, ed è la posizione col MTM peggiore della giornata. Controfattuale corto, stesso strumento e stesso giorno, con il nozionale S4 realmente usato (1.230,59 $): 1.230,59 / 141,73 = 8,6828 azioni × (146,15 − 141,73) = **+38,38 $** invece dei −18,33 registrati. Registro **+38,38 su F-010** come alpha mancato; i −18,33 sono già su F-030 e non vanno contati due volte.
  Gli altri tre scarti #108 del giorno non costano: NVDA 14:15 (+0,385) avrebbe reso −0,17% da lì a fine giornata, TSM e MS delle 19:15 erano entrambi già a libro e P0-05 li avrebbe fermati comunque.
* **Severità:** High
* **Confidenza:** Medium (il controfattuale assume che il ciclo delle 16:07 avrebbe eseguito; tutti gli altri guard erano liberi)
* **Azione consigliata:** propagare il retry a floor 0 anche al ramo single-model, così che due letture concordi a bassa confidenza producano un ensemble anziché un fallback; e togliere il perimetro di `_record_fallback_drops` per i segnali **sopra il gate**, che vanno sempre tracciati. È correttezza: senza, l'alpha-miss classifica come «nessun segnale» giornate in cui il segnale c'era.
* **Test/monitor consigliato:** invariante «ogni segnale con `|score| ≥ entry_threshold` ha almeno una riga in `execution_decisions` entro il ciclo successivo»; conteggio giornaliero delle violazioni.
* **Ledger:** F-010

### [DAY-003] Roundtrip NVDA in 1h45: gate d'ingresso e soglia d'uscita coincidono, nessuna banda di isteresi

* **Tipo:** Bug
* **Area:** Signal / Orders
* **Evidenza:**
  * tabella: `trades` id 701 — BUY 17:22 @223,9655 su score +0,343, SELL 19:07 @223,84, net **−0,93**
  * tabella: `execution_decisions` id 9775, reason `[below_entry_gate] S4 signal fell below the active feedback entry threshold (age=0.6h vs max_age=4h, generated 2026-08-12 18:30 UTC, score=+0,023): weight 0.0%, position closed`
  * codice: `portfolio_scheduler.py:3715-3722` applica `signals_df[score.abs() < _fb_threshold]` all'**intero** dataframe, non ai soli candidati nuovi
* **Descrizione:** il simbolo esce dal dataframe non appena l'ultimo punteggio scende sotto 0,300, il peso target va a zero e nasce una SELL. Entrata e uscita condividono la stessa soglia. Oggi il segnale che ha spinto NVDA sotto il gate viene da un articolo su società terze (Lumentum / rassegna CPI) — meccanica già registrata su F-008.
* **Impatto:** roundtrip di 105 minuti su una posizione da 1.232 $, chiusa in perdita su un titolo che chiude +3,03%. I dollari (1,38 di drift post-uscita) sono già iscritti su F-008.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** **nessuna oggi** — introdurre una banda di isteresi è taratura, congelata fino al 28/09. Il finding vive per ricorrenza (sesta giornata).
* **Test/monitor consigliato:** contatore giornaliero dei roundtrip < 4h per strategia.
* **Ledger:** F-013

### [DAY-004] La posizione IBM è chiusa dal solo trascorrere del tempo di parete, senza contro-segnale

* **Tipo:** Bug
* **Area:** Orders / Signal
* **Evidenza:**
  * tabella: `execution_decisions` id 9418, 14:22 — `[unknown] S4 signal was stale but FIX-D re-admitted it this cycle — open position, no counter-signal — and the weight is 0 anyway … (age=19.4h vs max_age=4h, generated 2026-08-11 19:00 UTC, score=+0,323)`
  * tabella: `trades` id 700 — entrata 11/08 19:07 (53 min prima della chiusura), uscita 12/08 14:22, tenuta **19,25h**, net −26,47
* **Descrizione:** `max_signal_age_hours = 4` è misurato in tempo di parete. Una posizione aperta a fine sessione attraversa 17,5h di mercato chiuso e al primo ciclo del giorno dopo è già scaduta. Il segnale era **positivo e sopra il gate** (+0,323): l'uscita non ha alcun contenuto informativo.
* **Impatto:** IBM risale dopo l'uscita e chiude a 235,98, cioè +13,71 sulla stessa quantità. Quel costo è già iscritto su **F-035** (che copre il meccanismo di codice: FIX-D ri-ammette, `_signals_as_of` rielimina). Qui registro la ricorrenza del meccanismo *wall-clock* con costo `null` per non contare due volte la stessa giornata.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** misurare l'età in tempo di mercato invece che di parete. È al confine fra correttezza e taratura: la finestra dichiarata è 4h **di validità dell'informazione**, e contare le ore notturne misura un oggetto diverso da quello dichiarato. Da valutare come deroga, non da applicare unilateralmente.
* **Test/monitor consigliato:** test che una posizione aperta alle 19:07 non risulti scaduta all'apertura successiva.
* **Ledger:** F-024

### [DAY-005] 70 ordini target contro 5 inviati: `portfolio_cycles.orders_count` non misura l'attività di trading

* **Tipo:** Anomalia
* **Area:** Ops / Data
* **Evidenza:**
  * query: `SELECT sum(orders_count) FROM portfolio_cycles WHERE timestamp::date='2026-08-12'` → **70**
  * `trades` + `execution_decisions` del giorno → **5** ordini realmente sottomessi
  * ciclo 930 (19:07): `final_orders` elenca INTC, NOK, SOXX, SPCX (BUY) e NVDA (SELL); solo la SELL NVDA raggiunge il broker
* **Descrizione:** `orders_count` conta gli ordini **target** prodotti dal combiner, prima dei guard a valle (P0-05 anti-pyramiding, `SIGNAL_DUPLICATE_SKIP`, delta ≈ 0). Chi legge la telemetria vede un sistema che emette 70 ordini al giorno; ne emette 5.
* **Impatto:** nessun dollaro. Ma è la metrica che un operatore guarda per capire se il sistema sta lavorando, ed è sbagliata di un fattore 14. Nella finestra di osservazione questo falsa qualunque conteggio di attività.
* **Severità:** Low
* **Confidenza:** High
* **Azione consigliata:** aggiungere un campo distinto `orders_submitted` accanto a `orders_count`, senza toccare il secondo (serie storica).
* **Test/monitor consigliato:** asserzione che `orders_submitted ≤ orders_count` e alert quando il rapporto scende sotto 0,2 per più giorni.
* **Ledger:** F-014

### [DAY-006] `regime_mult` scala il nozionale ma non il target del combiner: tutti e tre gli ingressi eseguiti al 70%

* **Tipo:** Bug
* **Area:** Orders / Risk
* **Evidenza:**
  * `portfolio_cycles.final_orders` vs `trades.qty`: NVDA 7,857491 → 5,500045 (**0,6999**); INTC 17,193208 → 12,034897 (**0,6999**); SPCX 11,853492 → 8,294554 (**0,6997**)
  * codice: `portfolio_scheduler.py:3914` `notional = round(price * order.quantity * regime_mult, 2)` con `regime_mult = 0,70`
  * al ciclo successivo il combiner ricalcola il delta e riemette l'ordine: INTC 19:07 → `SKIP_PYRAMIDING`; SPCX 19:07/19:22/19:37/19:52 → `SIGNAL_DUPLICATE_SKIP` in `audit_log`, **nessuna riga** in `execution_decisions`
* **Descrizione:** ogni posizione S4 resta stabilmente al 70% del peso obiettivo in qualunque regime ≠ 1,0, e il rabbocco è strutturalmente impossibile perché i guard bloccano ogni BUY su simbolo già a libro. Il backtest, che non ha né lo scaling né i guard, misura un oggetto diverso.
* **Impatto:** **0,00 verificato, non stimato per difetto.** Il nozionale non allocato oggi ha *evitato* perdite: NVDA 2,357 az. non comprate × −0,125 = +0,30; INTC 5,158 × −1,342 = +6,92; SPCX 3,559 × −2,210 = +7,86. Netto **+15,08 a favore del difetto**. Il finding vive per il meccanismo (sotto-deployment cronico del 30% della sleeve S4 e divergenza live↔backtest), non per il costo di oggi.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** applicare `regime_mult` al **target** del combiner, non al nozionale dell'ordine, così che il delta successivo sia zero e non generi rabbocchi bloccati.
* **Test/monitor consigliato:** invariante `qty_eseguita / qty_target ∈ {0, 1}` a meno di frazioni di arrotondamento.
* **Ledger:** F-038

### [DAY-007] `risk_reports.combined_drawdown` dice 1,24%, l'alert nella stessa riga dice 15,7%

* **Tipo:** Bug
* **Area:** Risk
* **Evidenza:**
  * tabella: `risk_reports`, 2026-08-12 22:30:00 — `combined_drawdown = 0.012429`, `alerts = [{"level":"ALERT","message":"Strategy portfolio drawdown 15.7% exceeds 10%","strategy_id":"portfolio"}]`
  * confronto: `portfolio_monitor_snapshots.current_drawdown` a chiusura = 0,001468 (0,15%)
* **Descrizione:** tre grandezze diverse chiamate «drawdown» nella stessa riga, con due ordini di grandezza di distanza. Nessuna coincide con quella usata dal kill-switch.
* **Impatto:** non stimabile in dollari — nessun ordine ne dipende. Ma è il numero che decide se un allarme di rischio è credibile, e chi lo legge non sa quale dei tre guardare.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** riconciliare le tre definizioni o rinominarle esplicitamente.
* **Test/monitor consigliato:** test che asserisca che il valore citato nel messaggio d'alert sia lo stesso della colonna.
* **Ledger:** F-003

### [DAY-008] Il decay monitor confronta metriche globali di pipeline contro tre baseline diverse

* **Tipo:** Bug
* **Area:** Ops
* **Evidenza:**
  * tabella: `decay_reports`, 2026-08-12 21:00 — 12 righe. `ic` = 0,018986 **identico** per S1, S2 e S4; `hit_rate` = 0,346698 identico; `sharpe` = −6,571142 identico. Solo le baseline differiscono (S1 0,035/0,54/0,95; S2 0,042/0,56/1,10; S4 0,028/0,52/0,80).
  * conseguenza: `sharpe` risulta CRITICAL per tutte e tre.
  * **S2 è morta** (audit strategie 2026-08-04) e viene ancora monitorata.
* **Descrizione:** l'`actual_value` non è per-strategia: è una metrica unica di pipeline confrontata contro tre soglie diverse. Il verdetto per strategia è quindi privo di contenuto.
* **Impatto:** non stimabile in dollari. È il meccanismo di sorveglianza del decadimento, cioè esattamente ciò su cui il periodo di osservazione dovrebbe poggiare.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** calcolare IC / hit-rate / Sharpe sui trade della singola strategia; rimuovere S2 dal monitor.
* **Test/monitor consigliato:** test che, dati due set di trade disgiunti per S1 e S4, produca due `actual_value` diversi.
* **Ledger:** F-004

### [DAY-009] `ingestion_stats_daily.duplicates` supera i `fetched` di 4,4× per Benzinga

* **Tipo:** Anomalia
* **Area:** News / Data
* **Evidenza:**
  * tabella: `ingestion_stats_daily`, 2026-08-12, `alpaca_benzinga`: fetched **729**, queued 383, duplicates **3202**
  * `gdelt_gkg` nello stesso giorno è coerente: fetched 2033, duplicates 33, discarded_no_ticker 1895
  * serie: 3122/844 (10/08), 2628/681 (11/08), 3202/729 (12/08)
* **Descrizione:** il contatore evidentemente non conta articoli ma coppie articolo × ticker, oppure accumula fra passate senza reset. Le righe realmente persistite (70) e gli hash distinti (111 su 157) non lo confermano in nessuna lettura.
* **Impatto:** non stimabile — telemetria. Ma rende impossibile rispondere a «quanta news stiamo scartando», domanda diretta per la prima domanda di uscita della carta.
* **Severità:** Low
* **Confidenza:** High
* **Azione consigliata:** documentare l'unità di misura del contatore o correggerla.
* **Test/monitor consigliato:** invariante `duplicates ≤ fetched` per fonte e per giorno.
* **Ledger:** F-007

### [DAY-010] La latenza d'ingestione è 2,9× la finestra di freshness dichiarata

* **Tipo:** Rischio
* **Area:** News
* **Evidenza:**
  * `news_log` del 12/08: mediana `created_at − published_at` = **86,7 min** su Benzinga (70 righe, 30,1–119,4) e **75,3 min** su GKG (87 righe, 45,4–105,8)
  * `config/trading.yaml:149` `signal_freshness_minutes: 30`
  * a valle si sommano il ciclo di scoring (minuti 12,27,42,57) e quello di portafoglio (7,22,37,52)
  * `news_queue_drops`: 161 articoli Benzinga scartati a un'età media di 6,8h, 32 GKG a 17,5h
* **Descrizione:** la notizia arriva già quasi scaduta rispetto alla finestra che il sistema si è dato. Peggiorato rispetto alla misura del 10/08 (75,2 / 75,5 min).
* **Impatto:** la conseguenza (il movimento è già avvenuto quando il segnale nasce) è misurata e già iscritta a **F-030** per il 12/08 con 41,31 $. Qui costo `null` per non contarla due volte.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** nessuna oggi — cambiare la finestra è taratura. Il finding vive per ricorrenza.
* **Test/monitor consigliato:** metrica giornaliera della mediana di latenza per fonte, con soglia d'allarme a 2× `signal_freshness_minutes`.
* **Ledger:** F-019

### [DAY-011] Le finestre beat sono in ora UTC fissa e perdono i primi 37 minuti di sessione

* **Tipo:** Bug
* **Area:** Ops
* **Evidenza:**
  * `celery_app.py:78,93,142,153,175,201` — tutte le finestre operative sono `hour="14-21"`
  * apertura NYSE il 12/08 (EDT): **13:30 UTC**
  * primo `portfolio_cycles` del giorno: **14:07:00**; primo segnale: 14:01
  * il commento a `celery_app.py:134` scrive esso stesso «*This run fires just before portfolio cycles begin (first cycle at 14:07)*», cioè il disallineamento è noto e cristallizzato
* **Descrizione:** in ora legale la sessione apre alle 13:30 UTC ma nessun ciclo gira prima delle 14:07. In ora solare (novembre→marzo) la finestra 14-21 invece taglia l'ultima ora di sessione. Il DST non è mai considerato.
* **Impatto:** non stimabile per il 12/08 — nessun segnale utile è nato prima delle 14:01. Ma l'apertura è la finestra in cui si concentra il movimento (misurato oggi: il gap d'apertura contiene il 99% mediano del movimento dei mover, F-030), quindi la scopertura cade esattamente sul momento peggiore.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** ancorare le finestre al calendario Alpaca (`GetCalendarRequest`) invece che a ore UTC fisse.
* **Test/monitor consigliato:** test che, dato un giorno EST e uno EDT, la prima esecuzione cada entro 10 minuti dall'apertura.
* **Ledger:** F-021

### [DAY-012] I log dei container del 12 agosto non esistono più

* **Tipo:** Bug
* **Area:** Ops
* **Evidenza:**
  * `docker compose ps`: worker, worker-inference, api, beat tutti `Up 4 hours` (riavvio ~2026-08-13 08:20 UTC)
  * `docker compose logs worker --timestamps | head` → prima riga `2026-08-13T08:20:16`
  * `docker compose logs worker | grep -c "2026-08-12"` → **0**
* **Descrizione:** il redeploy di stamattina ha azzerato i log. La giornata che questo report analizza non ha **nessuna** riga di log disponibile.
* **Impatto:** misurata sull'osservabilità, non in dollari. Le domande che solo i log possono chiudere restano aperte: quante chiamate Ollama sono andate in timeout e sono state ritentate, perché `detect_regime` ha fallito ([DAY-001]), quanti retry di ingest ci sono stati, se qualche alert Telegram è stato rifiutato. Cinque giorni consecutivi con lo stesso buco.
* **Severità:** High
* **Confidenza:** High
* **Azione consigliata:** driver di logging persistente (file o journald) o spedizione a un sink esterno. È correttezza: senza, il forense di domani non potrà mai verificare la giornata di oggi.
* **Test/monitor consigliato:** controllo giornaliero che i log coprano almeno le 24h precedenti.
* **Ledger:** F-027

### [DAY-013] Il fix di `signal_id` (#123) è in produzione ma copre solo il ramo BUY

* **Tipo:** Bug
* **Area:** Data
* **Evidenza:**
  * `execution_decisions` del 12/08: `BUY` **3/3 con `signal_id`** (7433, 7450, 7482), `SKIP_PYRAMIDING` 12/12, ma `SELL` **0/2**, `SKIP_THRESHOLD` **0/398**, `SKIP_STALE` 0/2, `SKIP_FALLBACK` 0/1
  * totale: **15 righe su 418 (3,6%)** hanno la chiave esterna
  * `trades`: id 701/702/703 (aperti oggi) hanno `signal_id`; id 700 (IBM, aperto l'11/08) no
  * commit `f742343` "fix: conserva il signal_id nella pipeline S4 (#123)", PR #234, mergiato il 12/08 alle 12:03 CEST — **deploy confermato dai dati**
* **Descrizione:** la correzione aggiunge `signal_id` al DataFrame dei segnali, quindi il ramo che produce un BUY lo propaga. I rami di uscita (`SELL`) e i logger di scarto (`_record_gate_drops`, `_record_stale_drops`, `_record_fallback_drops`) scrivono ancora `signal_id=None` esplicitamente.
* **Impatto:** **0,00 verificato.** Nessun ordine sbagliato ne deriva. Il danno è sull'auditabilità: la catena segnale→uscita non è ricostruibile per chiave esterna, ed è proprio la catena che serve per attribuire un'uscita al segnale che l'ha causata.
* **Severità:** Low (era Medium: il ramo d'ingresso, il più importante, è risolto)
* **Confidenza:** High
* **Azione consigliata:** estendere la propagazione ai rami SELL e ai tre logger di scarto.
* **Test/monitor consigliato:** metrica giornaliera `count(signal_id)/count(*)` su `execution_decisions`, per decisione.
* **Ledger:** F-011

### [DAY-014] `slippage_est` è una copia letterale di `cost_usd`

* **Tipo:** Bug
* **Area:** PnL
* **Evidenza:**
  * `trades` id 700: `slippage_est = 2.469519910243238`, `cost_usd = 2.469519910243238`
  * `trades` id 701: `slippage_est = 0.24433599049578708`, `cost_usd = 0.24433599049578708`
* **Descrizione:** il campo destinato a misurare la qualità di esecuzione contiene il costo modellato, non la differenza fra prezzo atteso e prezzo di fill.
* **Impatto:** non stimabile in dollari. La qualità di esecuzione non è misurata affatto, quindi non sapremo mai se il market order in ambiente paper sta nascondendo slippage che il live pagherebbe.
* **Severità:** Low
* **Confidenza:** High
* **Azione consigliata:** calcolare `slippage_est = (fill_price − reference_price) × qty` con il prezzo di riferimento al momento della decisione.
* **Test/monitor consigliato:** test che, dato un fill diverso dal riferimento, `slippage_est ≠ cost_usd`.
* **Ledger:** F-015

### [DAY-015] IBM paga 20,25 bps di costo modellato perché non ha un tier nel cost model

* **Tipo:** Bug
* **Area:** PnL
* **Evidenza:**
  * `trades` id 700, IBM: `cost_bps = 20.246`, `cost_usd = 2.4695` su 1.206,05 $ di nozionale
  * confronto stesso giorno: NVDA `cost_bps = 1.748` (tier_a), INTC `5.248` (tier_b)
  * `config/cost_model.yaml`: `tier_d` ha `default: true`, `spread_bps: 20.0`, descrizione «Default: small-cap, illiquid»; IBM non è mappata
  * verifica che il costo entra nel P&L: NVDA gross −0,69 → net −0,93, differenza 0,2443 = `cost_usd`
* **Descrizione:** 25 simboli di watchlist su 96 non hanno tier e cadono nel default small-cap. IBM è una mega-cap. SPCX, l'altra riga a 20,25 bps di oggi, è una quotazione recente e il tier illiquido è probabilmente corretto per lei.
* **Impatto:** **1,84 $ misurati** sul trade 700. Con il tier di INTC (5,248 bps) IBM avrebbe pagato ~0,633 $ invece di 2,4695 $. Non è cash — il paper Alpaca ha `commission_per_share = 0` — ma `cost_usd` è sottratto a `net_pnl`, quindi è perdita iscritta a libro e distorce ogni statistica di redditività della finestra di osservazione.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** completare la mappatura dei 25 simboli scoperti in `config/cost_model.yaml`. È correttezza contabile, non taratura di strategia: non tocca cosa compriamo né con che size (nessun gate pre-trade legge il cost model).
* **Test/monitor consigliato:** test che ogni simbolo di watchlist abbia un tier esplicito.
* **Ledger:** F-034

### [DAY-016] WDC è aperta da 22 giorni sotto una strategia con orizzonte di 4 ore

* **Tipo:** Bug
* **Area:** Orders
* **Evidenza:**
  * `trades` id 373: symbol WDC, `stop_strategy = 'S4'`, `entry_time = 2026-07-21 16:37`, nozionale 1.637,33, `exit_time` NULL al 12/08
  * `s4_config.max_signal_age_hours = 4`
  * `alert:unprotected_position:WDC` acceso in Redis
* **Descrizione:** preserve-stale (FIX-D) ri-ammette a ogni ciclo il segnale vecchio perché la posizione è aperta e non c'è contro-segnale. Simmetricamente, IBM è stata chiusa per scadenza dopo 19h ([DAY-004]): le due regole si contraddicono e l'esito dipende da quale ramo tocca la posizione.
* **Impatto:** non stimabile — il controfattuale sarebbe lungo 22 giorni. L'effetto vero è di misura: qualunque statistica di holding period di S4 calcolata sul libro attuale non descrive S4.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** definire un orizzonte d'uscita esplicito per S4 (taratura, quindi post-28/09) **oppure** riconciliare i due rami perché non si contraddicano (correttezza).
* **Test/monitor consigliato:** alert quando una posizione S4 supera N× `max_signal_age_hours`.
* **Ledger:** F-025

### [DAY-017] La varianza d'ensemble non è mai un gate: tre segnali al limite di divergenza sono passati

* **Tipo:** Rischio
* **Area:** LLM
* **Evidenza:**
  * `sentiment_signals` del 12/08 con `ensemble_std = 0.283` contro `divergence_threshold = 0.30`: SPY id 7381 (+0,356), TSM id 7387 (+0,319), SOXX id 7431 (+0,318) — **tutti e tre sopra il gate d'ingresso 0,300**
  * tutti e tre hanno generato ordini target ed erano a un `SKIP_PYRAMIDING` di distanza dall'esecuzione
  * `ensemble_std` è letto **solo** da `src/performance/postmortem.py` (soglia 0,30), che si attiva dopo una perdita ≥ 2%
  * CLAUDE.md prescrive «*Ensemble variance: flag high-variance outputs for human review or discard*»
* **Descrizione:** la varianza è calcolata, persistita, e poi consultata solo *dopo* la perdita. Nel percorso d'ingresso non esiste alcuna lettura. Non esiste supervisor agent né verifica RAG. Se entrambi i modelli allucinano nella stessa direzione, l'unica difesa è la soglia sullo score.
* **Impatto:** non stimabile. Qualunque soglia di varianza proponessi sarebbe taratura, congelata: il controfattuale non è costruibile senza violare la carta.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** nessuna oggi. Strumentazione ammessa: registrare in `execution_decisions` la `ensemble_std` del segnale che ha generato l'ordine, così che al 28/09 la decisione sia informata.
* **Test/monitor consigliato:** distribuzione giornaliera di `ensemble_std` sui soli segnali sopra il gate.
* **Ledger:** F-037

### [DAY-018] BRKB produce segnali che non raggiungono mai il percorso decisionale

* **Tipo:** Bug
* **Area:** Data / Signal
* **Evidenza:**
  * `sentiment_signals` id 7408 (16:30, +0,240, fallback) e 7461 (18:01, +0,013, ensemble), symbol **`BRKB`**
  * `news_log`: entrambi via `org_lookup` da GDELT, articoli su Berkshire
  * `execution_decisions` per `symbol LIKE 'BRK%'` il 12/08: **0 righe**
  * la watchlist usa `BRK.B` (compare nel dossier deterministico con return −1,24%)
* **Descrizione:** i provider scrivono `BRKB`, la watchlist dice `BRK.B`, e non esiste canonicalizzazione fra i due. Il segnale nasce, viene persistito, e muore prima del ciclo di portafoglio.
* **Impatto:** **0,00 verificato, non stimato per difetto.** Entrambi i punteggi erano sotto il gate 0,300 e BRK.B ha chiuso a −1,24%: un BUY avrebbe perso denaro. Il finding vive per il meccanismo, non per il costo di oggi.
* **Severità:** Low
* **Confidenza:** High
* **Azione consigliata:** già tracciato come issue **#226**.
* **Test/monitor consigliato:** invariante «ogni `sentiment_signals.symbol` appartiene alla watchlist canonica».
* **Ledger:** F-032

---

## 11. False positive e aree risultate corrette

| area | verifica | esito |
|---|---|---|
| **Freeze del ratchet (#191)** | `feedback:state:S4` = `{"last_adjustment_ts":"2026-08-12T19:30:00", "reason":"5 consecutive losses", "threshold_before":0.3, "threshold_after":0.3}` | **Corretto, e verificato sotto stress.** Il trigger si è attivato davvero e la soglia **non** è salita. La deroga del 07/08 è chiusa: `threshold_ratchet_enabled: false` è in `config/trading.yaml:320` e in `performance.py:1735`, commit `543c3b3`, PR #220 mergiata |
| **Fetch benchmark SPY (F-016)** | 6 chiavi `benchmark:spy_closes:*` presenti in Redis con dati fino al 13/08 | **Risolto.** Il fallimento permanente per limite di sottoscrizione non si ripresenta. Nessuna occorrenza aggiunta |
| **Inquinamento del DB dai test (F-028)** | `ingestion_stats_daily` ha righe `reuters` (fetched=queued, 12/12 e 24/24) il 10/08 e l'11/08, **nessuna il 12/08** | **Pulito sul giorno target.** Nessuna occorrenza aggiunta |
| **Ollama** | 157 risposte da `gpt-oss:20b-cloud` e 155 da `glm-5.2:cloud` su 157 segnali; zero righe `model_id='finbert'` | **Up al 100%.** Le 2 risposte mancanti di glm non hanno prodotto fallback FinBERT |
| **Kill-switch / halt operatore** | `system:halted_by_operator` assente, `system:mode='paper'`, `fallback_counters.consecutive_fallback = 0` | Nessun blocco attivo |
| **Idempotenza** | 8 righe `SIGNAL_DUPLICATE_SKIP` in `audit_log` (INTC ×4, SPCX ×4) impediscono il doppio ingresso sullo stesso `signal_id` | Funziona |
| **Riconciliazione posizioni** | 48→47→48→49→50→49 negli snapshot, ogni transizione allineata all'ordine corrispondente | Nessuna divergenza |
| **Timezone** | `celery_app.py:51` `timezone="UTC"`; tutte le colonne sono `timestamptz` | **Nessuna ambiguità** — solo il problema DST delle finestre ([DAY-011]) |
| **Timestamp futuri** | 0 righe con `published_at > created_at` | Pulito |
| **Duplicati cross-provider** | 0 titoli condivisi fra Benzinga e GDELT | Dedup funziona |
| **Guard anti-pyramiding** | 12 righe `SKIP_PYRAMIDING` con peso non allocato e data d'ingresso | **Non più silenzioso.** Su NOK e MU (mover del giorno) il guard ha *risparmiato*: le gambe intraday erano −0,72% e −0,18% |
| **`stop_decisions` vuota** | `risk.stop_loss = 0.0` per decisione paper del 15/07 | Non è un guasto |
| **Ordini fuori orario / duplicati** | 5 ordini, tutti 14:22–19:07 UTC, `order_id` distinti | Pulito |

---

## 12. Dati mancanti o non accessibili

| dato | perché manca | cosa servirebbe |
|---|---|---|
| **Log applicativi del 12/08** | container riavviati il 13/08 alle 08:20 UTC | driver di logging persistente ([DAY-012]) |
| **Latenza per chiamata LLM** | `llm_responses` non ha colonna di durata e i log sono persi | colonna `latency_ms` in `llm_responses` |
| **Timeout / refusal / output invalidi per modello** | contati solo indirettamente (2 risposte glm mancanti su 157); il resto vive nei log | contatori persistiti per esito di chiamata |
| **API REST locale** | `Authorization: Bearer …` restituisce **403 `{"detail":"Invalid or expired JWT token"}`** su `/api/positions`, `/api/decisions`, ecc. (`/health` risponde 200) | token rigenerato. L'intera analisi è stata fatta su Postgres + Redis, che sono le fonti primarie: nessuna conclusione dipende dall'API |
| **Posizioni lato broker** | non esiste tabella di snapshot posizioni; solo il conteggio in `portfolio_monitor_snapshots` | tabella `positions_snapshot` con `symbol, qty, avg_entry_price, unrealized_pl` per fare riconciliazione riga per riga anziché per conteggio |
| **PnL per strategia sulle 11 posizioni legacy del 10/07** | `stop_strategy` NULL (F-002) | backfill di attribuzione |
| **`performance_metrics`** | la tabella è **completamente vuota** (0 righe in assoluto): composite IC, ICIR, PSI e drift non sono mai stati scritti | verificare se il task esiste ed è schedulato; non incluso fra le anomalie del giorno perché non è un evento del 12/08 ma uno stato permanente da indagare a parte |
| **Motivo del fallimento di `detect_regime`** | i 12 rami di `return` silenzioso non lasciano traccia in DB e i log sono persi | vedi [DAY-001] |

---

## 13. Raccomandazioni immediate

Tutte dentro l'esenzione della carta («se non lo correggo, l'evidenza che raccolgo nelle
prossime settimane è sbagliata?»). **Nessuna taratura.**

1. **[DAY-001] Regime.** È la più urgente: il moltiplicatore che scala ogni ordine S4
   gira su dati di ieri e nessuno se n'è accorto per due giorni. Far propagare
   l'errore Celery e/o abbassare il TTL sotto la cadenza del task.
2. **[DAY-012] Log persistenti.** Cinque giorni di fila senza log della giornata
   analizzata. Ogni domanda di causa radice resterà senza risposta finché non si
   risolve.
3. **[DAY-002] Tracciare gli scarti sopra il gate.** Un segnale sopra soglia che sparisce
   dal Decision Log rende falsa la classificazione delle cause di miss, che è il dato
   su cui poggia la prima domanda di uscita della carta.
4. **[DAY-015] Completare `cost_model.yaml`.** 25 simboli su 96 pagano 4× il dovuto e
   il costo è sottratto a `net_pnl`: le soglie della carta sono in dollari.
5. **[DAY-013] Estendere `signal_id` ai rami SELL.** Fix da poche righe; senza, le
   uscite non sono attribuibili al segnale che le ha causate.

Fuori esenzione, da tenere per il 28/09: banda di isteresi ([DAY-003]), tempo di mercato
per `max_signal_age` ([DAY-004]), orizzonte d'uscita S4 ([DAY-016]), gate di varianza
d'ensemble ([DAY-017]).

## 14. Test / monitor da aggiungere

| # | monitor | soglia d'allarme |
|---|---|---|
| M-1 | età di `regime:current` (`now() − detected_at`) | > 26h |
| M-2 | copertura dei log dei container | < 24h |
| M-3 | segnali con `|score| ≥ entry_threshold` senza riga in `execution_decisions` | ≥ 1 al giorno |
| M-4 | `count(signal_id)/count(*)` su `execution_decisions`, per tipo di decisione | < 100% su BUY/SELL |
| M-5 | rapporto ordini inviati / ordini target | < 0,2 per 3 giorni |
| M-6 | invariante `duplicates ≤ fetched` in `ingestion_stats_daily` | violato |
| M-7 | mediana di latenza d'ingestione per fonte | > 2× `signal_freshness_minutes` |
| M-8 | roundtrip < 4h per strategia | ≥ 2 al giorno |
| M-9 | posizioni S4 aperte da più di N× `max_signal_age_hours` | ≥ 1 |
| M-10 | simboli di watchlist senza tier in `cost_model.yaml` | ≥ 1 |
| M-11 | simboli in `sentiment_signals` fuori dalla watchlist canonica | ≥ 1 |
| M-12 | distribuzione di `ensemble_std` sui segnali sopra il gate | quota ≥ 0,25 in crescita |
| M-13 | `decay_reports`: `actual_value` identico fra strategie diverse | violato |
| M-14 | primo ciclo di portafoglio vs apertura da calendario Alpaca | scarto > 10 min |

## 15. Ticket tecnici suggeriti

| id | titolo | area | tipo | priorità | finding |
|---|---|---|---|---|---|
| TK-R1 | `detect_regime` fallisce in silenzio: propagare l'errore e allineare il TTL alla cadenza | Ops/Risk | correttezza (esente dal freeze) | **P0** | F-017 |
| TK-R2 | Logging persistente dei container: i log non sopravvivono al redeploy | Ops | correttezza (esente) | **P0** | F-027 |
| TK-R3 | Propagare il retry a floor 0 al ramo single-model e tracciare sempre gli scarti #108 sopra il gate | LLM/Signal | correttezza (esente) | **P1** | F-010 |
| TK-R4 | Completare `cost_model.yaml`: 25 simboli di watchlist cadono nel tier default a 20 bps | PnL | correttezza contabile (esente) | **P1** | F-034 |
| TK-R5 | Estendere la propagazione di `signal_id` (#123) ai rami SELL e ai logger di scarto | Data | correttezza (esente) | **P1** | F-011 |
| TK-R6 | `regime_mult` va applicato al target del combiner, non al nozionale dell'ordine | Orders | correttezza (esente) | **P2** | F-038 |
| TK-R7 | Riconciliare le tre definizioni di drawdown in `risk_reports` | Risk | correttezza (esente) | **P2** | F-003 |
| TK-R8 | `decay_reports`: metriche per-strategia, e rimuovere S2 dal monitor | Ops | correttezza (esente) | **P2** | F-004 |
| TK-R9 | `slippage_est` deve misurare lo slippage, non copiare `cost_usd` | PnL | correttezza (esente) | **P2** | F-015 |
| TK-R10 | Ancorare le finestre beat al calendario Alpaca invece che a ore UTC fisse | Ops | correttezza (esente) | **P2** | F-021 |
| TK-R11 | `orders_submitted` distinto da `orders_count` in `portfolio_cycles` | Ops | strumentazione | P3 | F-014 |
| TK-R12 | Documentare o correggere l'unità di `ingestion_stats_daily.duplicates` | Data | strumentazione | P3 | F-007 |
| TK-R13 | Indagare perché `performance_metrics` è vuota da sempre | Ops | correttezza | P3 | — |
| TK-R14 | Persistere `ensemble_std` nella riga di decisione (solo strumentazione) | LLM | strumentazione | P3 | F-037 |
| — | Canonicalizzazione BRKB / BRK.B | Data | correttezza | — | **già aperto: #226** |

**Congelati fino al 2026-09-28** (taratura, non ticket): banda di isteresi ingresso/uscita
(F-013), tempo di mercato per `max_signal_age` (F-024), orizzonte d'uscita S4 (F-025),
gate sulla varianza d'ensemble (F-037), size minima ≥ 1 azione (F-022).

## 16. Stato sistema

| voce | valore |
|---|---|
| **Ollama** | **UP, 0h di downtime.** 157/157 risposte da `gpt-oss:20b-cloud`, 155/157 da `glm-5.2:cloud` (2 mancate, 1,3%) |
| **Fallback FinBERT** | **0,0%** — zero righe `model_id='finbert'` in `sentiment_signals`. `fallback_counters.consecutive_fallback = 0`, resettato l'ultima volta alle 19:45:40 |
| **Fallback single-model** | 53/157 segnali (33,8%): 46 `single:gpt-oss`, 7 `single:glm-5.2`. **Non è un'indisponibilità**: in 51 casi su 53 entrambi i modelli avevano risposto, e uno è stato scartato dal floor di confidence 0,40 |
| **Consenso a due modelli sopra il floor** | 31/157 (19,7%). Altri 73 ensemble (46,5%) nascono dal retry a floor 0, cioè da due letture che i modelli stessi dichiarano a bassa confidenza |
| **Decisioni influenzate dal fallback** | 1 riga `SKIP_FALLBACK` (IWM). Altri 3 segnali sopra il gate scartati **senza** riga: SPCX 16:01, NVDA 14:15, e TSM/MS delle 19:15 |
| **Riavvii worker** | **1 evento**, il 2026-08-13 alle ~08:20 UTC (redeploy): api, beat, worker, worker-inference tutti `Up 4 hours`. Postgres e Redis `Up 5 days`, frontend `Up 2 days`. **Nessun riavvio durante la sessione del 12/08** (i 24 cicli sono contigui, ogni 15 minuti senza buchi) |
| **Peso ensemble attivo** | `glm-5.2:cloud` 0,6009 / `gpt-oss:20b-cloud` 0,3991, congelati dal 10/08 (`freeze_reason: IC variance = 0.188 >= 0.15`) |
| **Coppia modelli** | `config:sentiment_llm_models = "glm52,gptoss"` — corretta, nessun reset a "all" |
| **Gate d'ingresso S4** | 0,300 per tutta la giornata; trigger di loss-feedback alle 19:30 **non** ha alzato la soglia (freeze #191 attivo) |
| **Regime** | `sideways`, `multiplier 0,70`, VIX 14,9 — **stale, `detected_at 2026-08-11T13:30:44`** ([DAY-001]) |
| **Modalità** | `paper` in 82/82 snapshot; `execution.engine = portfolio` |
| **Alert attivi** | `alert:unprotected_position:WDC` (acceso); 1 alert in `risk_reports` («drawdown 15,7% exceeds 10%», numero incoerente — [DAY-007]) |

---

*Report generato in sola lettura. Nessun file di codice modificato, nessun ordine inviato,
nessuna pipeline rieseguita.*
