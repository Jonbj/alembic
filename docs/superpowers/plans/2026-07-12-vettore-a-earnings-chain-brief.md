# Vettore A — Earnings Event Chain: Handoff Brief (spec-level)

**Status:** requirements + assumptions locked; NO implementation plan yet — the first
task of the implementing agent is a bounded discovery on FMP, then writing the plan
with the superpowers:writing-plans skill. This is deliberately NOT a fake-precise TDD
plan: FMP response schemas must be probed before exact code can be honest.

**Why this vector:** measured 2026-07-12 — the current S4 (editorial-news sentiment,
large-cap) has IC ≈ 0.01, hit-rate 51.8%, negative avg forward return on tradeable
scores (≥0.30), and −$788 all-time over 237 trades. Latency is NOT the problem
(median 1.1h news→score): the *content* is already priced. The designed cure
(`docs/ROADMAP_DATA_ALPHA_2026-07-02.md` §4, Vettore A) is switching the input from
editorial news to the primary earnings event chain: calendar → deterministic surprise
→ transcript tone — data that is fresh, ticker-certain, and semi-structured (where an
LLM has a real comparative advantage). It also unlocks S7 PEAD ("S7 produce zero per
dati mancanti: consensus non wired").

## Assumptions adopted (revocable by the PO — flag if you disagree)

- **A1 — Provider: FMP one-stop** (roadmap open decision #2). Already used
  successfully for the ALPHA-A5 backtest (`reports/s7_backtest/ALPHA_A5_gate_report_2026-07-03_fmp.md`);
  `FMP_API_KEY` is already present in the container env.
- **A2 — Universe: unchanged large-cap watchlist for S4 enrichment** (open decision #1
  concerns S7's PEAD edge on small/mid — separate decision, NOT blocked by this work).
- **A3 — Gates: the pre-registered ALPHA-A3 transcript-tone gate applies** (see
  `1007b13` s7-poc: POC-2c tone IC analysis + pre-registered gate). No new alpha goes
  live un-gated; QX-01 discipline (CLAUDE.md) stays in force.

## What exists already (do NOT rebuild)

- `src/connectors/earnings_calendar.py` — `EarningsCalendarProvider` (Finnhub
  calendar) feeding the `earnings-pead` worker; **consensus is NOT wired** (the known
  gap that zeroes S7).
- `src/workers/earnings_pead_worker.py` + `pead_signals` table + S7 strategy code
  (shelved, `strategy_lifecycle.mode=research`).
- S7 POC transcript tooling: `scripts/score_s7_transcripts.py` (POC-2b, DK-CoT tone
  scoring, resumable) and the POC-2c IC analysis — reuse the prompt + caching pattern.
- Sentiment pipeline plumbing (sanitizer, budget tracker, Redis/PG stores, decision
  log) — the event chain rides the same offline-worker architecture (CLAUDE.md: no
  LLM in the hot path).

## Deliverables for the implementing agent

**Phase 0 — Discovery (bounded: ≤ half a day, read-only, no live changes):**
1. Probe FMP with the existing key (inside `alembic-worker-1`): earnings calendar,
   analyst estimates (consensus EPS), transcripts endpoints for 5 watchlist symbols.
   Record: exact endpoints, response schemas, rate limits, historical depth, cost tier.
2. Verify the consensus gap: where `earnings_pead_worker` expects consensus and what
   shape it needs.
3. Output: a short discovery report appended to this file (schemas + gaps + any
   assumption invalidated).

**Phase 1 — Deterministic surprise (no LLM):** FMP consensus wired into the earnings
worker → `surprise_pct = (actual − consensus)/|consensus|` computed deterministically
at event time; stored on `pead_signals`. Acceptance: for the last 4 earnings weeks of
the watchlist, ≥90% of events have consensus + actual + surprise populated within 1h
of the report.

**Phase 2 — Transcript tone as S4 input:** on earnings day, transcript (or press
release when transcript lags) scored with the POC-2b DK-CoT tone prompt by the live
ensemble pair, producing a NORMAL `sentiment_signals` row (source-tagged) — so it
flows through the existing gate/ranker/decision-log unchanged, and IC is measurable
with the multi-horizon forward returns from the measurement-foundation plan.
Acceptance: event-sourced signals distinguishable via `news_log.source`, IC
computable separately per source.

**Phase 3 — Gate evaluation:** after ≥4 weeks of event-sourced signals: IC(event
signals) vs IC(editorial signals) with the pre-registered thresholds. PASS → PO
decision on rebalancing S4's input mix / sleeve; FAIL → document and stop (no
tuning-until-it-passes).

## Hard constraints

- Ingestion offline → worker → PG/Redis → execution reads (CLAUDE.md non-negotiable).
- Every phase behind its own branch + review; nothing merges without the acceptance
  criteria met; no config/allocation changes anywhere in this work.
- Budget: transcript scoring only on event days (~5-15/day on the watchlist in
  earnings season) — estimate and report cost in Phase 0.

## Kickoff prompt (for a fresh agent — model: claude-sonnet-5 for Phases 1-2; use a
stronger model or ask for review if Phase 0 discovery contradicts this brief)

```
You are working in /home/stefano/Documents/Projects/Alembic (LLM trading system,
paper trading). Read CLAUDE.md, then
docs/superpowers/plans/2026-07-12-vettore-a-earnings-chain-brief.md (this file),
then docs/ROADMAP_DATA_ALPHA_2026-07-02.md §4 (Vettore A).

Execute Phase 0 (bounded discovery, read-only) exactly as described in the brief,
append the discovery report to the brief file, and STOP for review. Do not start
Phase 1 until the discovery report is approved. After approval, use the
superpowers:writing-plans skill to produce a full TDD plan for Phase 1 only, and
execute it with superpowers:subagent-driven-development on branch
vettore-a-phase1-<date>. Never touch main, config files, or the live DB.
```

---

## Phase 0 — Discovery Report (2026-08-18, issue #37)

**Metodo.** Sonda read-only degli endpoint FMP / Finnhub / Alpha Vantage con le chiavi
presenti nel container live (lette dall'`.env`, mai scritte nel repo). 5 simboli di
watchlist rappresentativi: AAPL, MSFT, NVDA, JPM, PFE. Riproducibile con
`scripts/probe_earnings_chain_phase0.py` (strumentazione read-only, nessun DB/worker,
nessuna taratura — compatibile col freeze #171). Nessuna modifica live eseguita.

**Risultato in sintesi.** Il brief (2026-07-12) è invecchiato su due punti che cambiano il
perimetro, non la direzione: (a) il codice S7/PEAD che il brief cita come esistente è
stato **rimosso** il 2026-07-15 (PR #56, ALPHA-A3 confutato a decision-grade); (b)
l'assunzione A1 «FMP one-stop» è **parzialmente invalidata**: la subscription FMP
Starter è stata cancellata (#23 chiuso) e i **transcript FMP richiedono il piano
Ultimate** (402). La buona notizia: **Finnhub copre gratis l'intera chain deterministica**
(calendar + consensus + actual + surprise precalcolato) ed è già integrato nello stack;
i **transcript restano raggiungibili via Alpha Vantage free tier**, come il POC S7 faceva
già. La Phase 1 (deterministic surprise) è quindi fattibile senza nuova chiave né
nuovo piano; la Phase 2 (transcript tone) passa per Alpha Vantage, non FMP.

### 0.1 Drift codice vs brief (assunzioni invalidate)

Il brief §"What exists already" cita tre artefatti come esistenti. Verifica sul codice
corrente (branch `agent/issue-37`, base `origin/main`):

| Artefatto citato dal brief | Stato reale |
|---|---|
| `src/connectors/earnings_calendar.py` (`EarningsCalendarProvider`) | **ASSENTE** — rimosso in `d1e6de6` (PR #56, 2026-07-15) |
| `src/workers/earnings_pead_worker.py` + tabella `pead_signals` + codice S7 | **ASSENTI** — rimossi nello stesso commit; S7 ritirato (POC-2 FAIL, n=73, IC +0.012) |
| `scripts/score_s7_transcripts.py` (POC-2b DK-CoT tone) + POC-2c IC | **PRESENTE** in `scripts/` (prompt DK-CoT e pattern di caching riutilizzabili) |
| `src/connectors/finnhub_news.py` | **PRESENTE** ma cabla solo `/company-news` (verificato): nessun endpoint earnings/estimate/surprise/consensus è acceso oggi |

**Conseguenza sul passo 2 del brief ("verify the consensus gap").** Il "consensus gap"
che azzerava S7 non è più codice vivo da verificare: il worker che lo esprimeva è stato
rimosso insieme alla strategia. Dal git history (`d1e6de6^:src/workers/earnings_pead_worker.py`)
il worker aspettava un `EarningsEvent` con `eps_actual`, `eps_estimate` e
`surprise_pct = (actual − estimate)/|estimate|`, e scriveva `pead_signals` con colonne
`eps_actual`/`eps_consensus`/`surprise_pct`. È lo **stesso shape** che `stable/earnings` e
`stock/earnings` restituiscono oggi (§§0.2–0.3): la forma del dato è confermata, l'unica
cosa sparita è il consumatore. Questo va detto all'operatore: la Phase 1 non "sblocca S7"
(S7 è deceduto per merito, non per fame di dati) — costruisce un **nuovo** vettore
event-driven come input S4 / alpha autonomo, coerente con la motivazione del commento
del 2026-07-24 su #37 (rotation day: 2/10 mover intercettati, gli altri senza nemmeno un
articolo — assenza di dati, non difetto di soglia).

### 0.2 FMP — matrice endpoint (piano = free/discounted, Starter cancellato)

`src/config.py:190-194` documenta: «FMP Starter cancelled 2026-07-15, #23; key retained
for opportunistic historical pulls». La chiave è valida ma su un piano dove:

| Endpoint | Codice | Stato | Note |
|---|---|---|---|
| `stable/earnings-calendar` (senza `from`/`to`) | 200 | **free** | finestra rotante ~3 mesi (77 record, date 2026-05-18→2026-08-18); record `{symbol,date,epsActual,epsEstimated,revenueActual,revenueEstimated,lastUpdated}` |
| `stable/earnings-calendar` (con `from`/`to`) | 402 | **premium** | il parametro range è a pagamento |
| `stable/earnings?symbol=X` | 200 | **free** | storia per-symbol **~40 anni** (AAPL: 165 record, 1985-09-30→2026-10-29), stesso shape del calendar |
| `stable/analyst-estimates?period=annual` | 200 | **free** | stime annuali revenue/ebitda/netIncome (low/high/avg) |
| `stable/analyst-estimates?period=quarter` | 402 | **premium** | il consensus trimestrale (quello che serve all'earnings chain) è a pagamento su FMP |
| `stable/earning-call-transcript?symbol=X` | 402 | **premium (Ultimate)** | transcript NON disponibili su FMP — confermato anche in `scripts/fetch_s7_transcripts.py:2-4` |
| `/api/v3/*`, `/api/v4/*` (tutti i legacy) | 403 | **legacy** | endpoint legacy chiusi il 2025-08-31, accessibili solo a sottoscrizioni precedenti |
| `stable/profile`, `stable/quote`, `stable/income-statement` | 200 | free | sanity del piano (la chiave è viva, il tier è free/discounted) |

**Schema record `stable/earnings` / `stable/earnings-calendar`** (è il dato della chain):
```json
{"symbol":"AAPL","date":"2026-10-29","epsActual":null,"epsEstimated":1.98,
 "revenueActual":null,"revenueEstimated":113340900000,"lastUpdated":"2026-08-18"}
```
Record futuri: `epsActual=null` (solo stima). Record passati con copertura analisti:
entrambi presenti → `surprise_pct = (epsActual − epsEstimated)/|epsEstimated|` calcolabile
deterministicamente. Record pre-2000: `epsEstimated=null` (niente consensus allora).

**Rate limit / cost tier.** Nessun header `X-RateLimit` restituito. Piano FMP attivo =
free/discounted (Starter cancellato). Limiti documentati FMP free ≈ 250 chiamate/giorno.
Per la chain live (pull per-symbol dei ~95 simboli watchlist su event day, non ogni giorno)
il bind è largo; lo span solo-storico si fa una volta (backfill).

### 0.3 Finnhub — copre gratis l'intera chain deterministica (e già integrato)

`FINNHUB_API_KEY` wired in `src/config.py:188`; connector `src/connectors/finnhub_news.py`
esiste ma usa solo `/company-news`. Gli endpoint earnings sono accendibili:

| Endpoint | Codice | Stato | Note |
|---|---|---|---|
| `calendar/earnings?from=&to=` | 200 | **free, range supportato** | `earningsCalendar[]` con `{symbol,date,hour,quarter,year,epsEstimate,epsActual,revenueEstimate,revenueActual}` — calendar + consensus + actual insieme |
| `stock/earnings?symbol=X` | 200 | **free** | `{symbol,estimate,actual,period,surprise,surprisePercent,year,quarter}` — **surprise già precalcolato da Finnhub**; storico recente (AAPL: ultimi 4 trimestri) |
| `stock/recommendation?symbol=X` | 200 | free | trend raccomandazione analisti (strongBuy/buy/hold/…) |
| `stock/earnings-estimate?symbol=X&freq=quarterly` | 302 | **endpoint rinominato/404** | non necessario: `stock/earnings` copre già estimate+actual+surprise |
| `company-news` | 200 | free (già wired) | sanity, 60 req/min |

**Conclusione FMP vs Finnhub per la Phase 1.** Finnhub `calendar/earnings` (con range, free)
+ `stock/earnings` (surprise precalcolato, free) coprono **tutta** la Phase 1
(deterministic surprise) senza nuova chiave né nuovo piano. FMP `stable/earnings`
(per-symbol, 40 anni di storia) è il complemento per il backtest storico profondo e il
cross-check del consensus — non il one-stop. L'assunzione A1 del brief va rivista: il
one-stop **non è FMP** (transcript a pagamento, consensus trimestrale a pagamento); il
one-stop deterministico è **Finnhub**, con FMP come sorgente storica di profondità.

### 0.4 Transcript (Phase 2) — Alpha Vantage, non FMP

`scripts/fetch_s7_transcripts.py` già documenta la rotta: «I transcript FMP richiedono il
piano Ultimate → si usa Alpha Vantage free tier». Verificato:
`EARNINGS_CALL_TRANSCRIPT?symbol=AAPL` → 200 ma `transcript: []` quando non si passa il
`quarter` (AV key i transcript per fiscal quarter, non per data — lo script S7 itera i
due trimestri candidati). `ALPHAVANTAGE_API_KEY` presente nell'`.env`.

**Costo Phase 2.** AV free = 25 chiamate/giorno (~5 req/min). Il brief stima ~5-15
event-day di earnings season sulla watchlist: entra nel budget ma **stretto**, e il POC S7
già impone un cost-cap pre-registrato (`_MAX_TRANSCRIPTS = 120`) + caching su disco +
resumabilità (processa finché la quota regge, poi si ferma pulito). La Phase 2 deve
preservare questo pattern di cost-cap + cache, non rifondarlo. Budget stimato: zero
dollari (tutti free tier), ~25 transcript/giorno in earnings season.

### 0.5 Bloccanti e perimetro freeze

- **#22 (PO-1 universo) APERTO**, ma il brief stesso (assunzione A2) dice che la decisione
  universo riguarda il PEAD edge small/mid di S7 (strategia deceduta) ed è **separata**,
  non blocca la Phase 0 discovery né la Phase 1 sulla watchlist large-cap attuale. La
  discovery proceeds sulla watchlist di `config/trading.yaml:7` (usata).
- **#23 (PO-2 FMP) CHIUSO** — l'adozione provvisoria di FMP è stata revocata di fatto
  (Starter cancellato). La discovery lo registra: FMP non è più il one-stop; la decisione
  PO da riaprire è «Finnhub come one-stop deterministico + FMP storico + AV transcript?».
  È una decisione PO (wayfinder:decision), **non** qualcosa che questa PR impone: la PR
  consegna solo l'evidenza, l'operatore decide.
- **Freeze #171.** Phase 0 è read-only: nessuna taratura, nessun flag/soglia toccato, nessun
  worker, nessun cambiamento live. Lo script di probe è strumentazione read-only. Nessuna
  deroga richiesta.

### 0.6 Assunzioni invalidate — checklist per l'operatore

| Assunzione brief | Verdetto discovery |
|---|---|
| A1 — FMP one-stop, chiave già nel container | **PARZIALMENTE INVALIDATA** — chiave presente ma Starter cancellato; transcript e consensus trimestrale a pagamento su FMP. One-stop deterministico = Finnhub. |
| «consensus wired via Finnhub (pre-empt parziale)» (corpo issue #37) | **INVALIDATA come codice vivo** — il pre-empt (commit `5b7991c`) è stato rimosso con S7 in `d1e6de6`; oggi Finnhub cabla solo company-news. Gli endpoint ci sono ma sono spenti. |
| §"What exists already": earnings_calendar.py / earnings_pead_worker / pead_signals | **INVALIDATA** — rimossi in PR #56. La Phase 1 costruisce ex novo, non "wira il consensus nel worker esistente". |
| A2 — universo large-cap invariato | **VALIDA** — non toccata; #22 non blocca. |
| A3 — gate pre-registrato ALPHA-A3 tone + QX-01 | **VALIDA** — nessun nuovo alpha va live un-gated; la discovery non tocca gate. |
| Budget transcript ~5-15/day, costo da stimare | **CONFERMATO** — zero dollari (free tier AV), 25/day hard cap, cost-cap pattern S7 da preservare. |

### 0.7 Raccomandazione (non vincolante — decisione operatore)

La discovery suggerisce di **riallineare il brief** prima della Phase 1: il one-stop
deterministico è Finnhub (`calendar/earnings` + `stock/earnings`), FMP resta per lo
storico profondo (`stable/earnings`, 40 anni), i transcript passano per Alpha Vantage. La
Phase 1 non sblocca S7 (deceduto per merito) ma crea un vettore event-driven ortogonale a
S1/S4, coerente con l'evidenza del 2026-07-24. **Tutto questo resta una decisione PO**:
questa PR consegna solo l'evidenza read-only, non cambia provider, non attiva endpoint,
non tocca tarature. L'approvazione del report (o la sua rettifica) sblocca la scrittura
del piano TDD della Phase 1, come da kickoff prompt.
