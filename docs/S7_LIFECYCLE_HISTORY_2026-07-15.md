# S7 (PEAD) — Lifecycle History and Removal

> **Esito finale: S7 RITIRATA il 2026-07-15.** Tre valutazioni distinte su dati reali
> (ALPHA-A5 large-cap FAIL, POC-1 small/mid INCONCLUSIVE, POC-2 transcript-tone FAIL
> decision-grade) + una superseded (Finnhub, 0 eventi). L'edge dichiarato di S7
> (transcript tone → alpha, ALPHA-A3) è confutato跨-modello; il base PEAD su large-cap è
> beta, non alpha; l'universo small/mid non è raggiungibile con copertura dati sufficiente.
> Decisione PO (PO-5, pre-registrata su #26): *"Se POC-2 FAIL → REMOVE."* POC-2 FAILed →
> REMOVE applicato. Issue #38 chiusa.

Questo documento raccoglie tutta la storia di S7 (design, implementazione, test,
valutazioni, POC, decisioni PO) come record permanente post-rimozione. I report raw
per-evento restano in `reports/s7_poc/` e `reports/s7_backtest/` (gitignored, evidenza
locale). Piano di revival: `docs/superpowers/plans/2026-07-04-s7-revival-resume.md`.

---

## 1. Design rationale

S7 = **PEAD (Post-Earnings Announcement Drift)**, strategia event-driven. Tesi: dopo una
sorpresa positiva negli earnings, il prezzo non incorpora subito tutta l'informazione →
drift positivo misurabile nei giorni successivi (Ball & Brown 1968, Foster et al. 1984).
S7 cattura l'effetto classificando gli 8-K filing SEC via LLM (Ollama, DK-CoT).

**Edge dichiarati (ROADMAP_DATA_ALPHA_2026-07-02, Vettore A — catena earnings):**
- **ALPHA-A2** — consensus EPS/revenue esterno → surprise calcolata da consensus reale,
  non estratto dall'LLM dal testo del 8-K (dove non c'è). *Stato: mai wired (consensus
  rotto/assente → surprise_pct null → soglia 0.05 mai superata).*
- **ALPHA-A3** — transcript tone (alpha qualitativo): tone del transcript earnings →
  signal. *L'edge specifico di S7, dove l'LLM brilla vs fattori numerici competuti.*
- **ALPHA-A5** — POC backtest go/no-go (drift netto ≥1.5% a 20d, hit-rate >55%, test
  esplicito large vs small cap).
- **Vettore D** (ALPHA-D1) — analyst revisions/rating come alimentatore del drift.

**Stato operativo (pre-rimozione):** S7 introdotta 2026-06-07, mai wired nel
`PortfolioOrchestrator` (P0-13, commit `6d86d3f`), `enabled=false`, allocation 0%.
Produce **zero ordini** da mesi (carburante zero: consensus assente + bug EDGAR ticker).
S7 SHELVED 2026-07-03 dopo ALPHA-A5 FAIL; revival POCautorizzato dal PO 2026-07-15 (PO-5).

## 2. Implementazione (superficie codice)

| Componente | Path | Note |
|---|---|---|
| Strategy | `src/strategies/s7/` | `signal.py`, `compute_target_weights()` |
| Worker | `src/workers/pead_worker.py` | classificazione 8-K via Ollama |
| API routes | `src/api/routes/pead_routes.py` | |
| Beat task | `pead-ingestion` in `src/workers/celery_app.py` | ogni 30 min, 14:05–21:35 UTC, queue `inference` |
| Ingestion | `run_sec_edgar_ingestion_worker`, `run_pead_ingestion_worker` | EDGAR → +5min → Ollama |
| Persistenza | `pead_signals` table (PostgreSQL) | DDL solo doc (ARCHITECTURE.md); nessuna migration la crea nel DB live — tabella mai materializzata |
| Config | `config/strategies.yaml` (S7: enabled=false, allocation_pct=0.15) | |
| Lifecycle | `strategy_lifecycle` / `strategy_lifecycle_audit` | S7 = research/SHELVED (nessuna row seedata — migration 025 inserisce solo S1/S2/S4) |
| Doc | `docs/strategies/s7-pead.md`, `docs/strategies.md` §S7 | |

**Script di valutazione/POC:** `scripts/backtest_s7_pead.py` (ALPHA-A5 large-cap),
`scripts/backtest_s7_smallmid.py` (POC-1), `scripts/analyze_s7_events.py` (distribuzione),
`scripts/fetch_s7_transcripts.py` (POC-2 fetch, Alpha Vantage free tier),
`scripts/score_s7_transcripts.py` (tone scoring Ollama),
`scripts/analyze_s7_tone.py` (gate ALPHA-A3), `scripts/s7_poc_helpers.py`.

> **Nota su cosa è stato rimosso vs preservato (2026-07-15, scope = rimozione
> completa):** tutta la superficie runtime S7 è stata **eliminata** — strategy dir,
> entrambi i pead worker, `earnings_calendar.py` (nessun altro consumer), `pead.py`
> models, `pead_routes.py`, beat task, config, API/display entries, redis pead methods,
> test S7-specifici. Una nota di design (`docs/strategies.md`) indicava il worker come
> "mattone di S9/Vettore B", ma S9/Vettore B non esistono, l'8-K path era già
> disabilitato (commit 171437e), e `earnings_calendar.py` non aveva consumer esterni →
> mantenerlo avrebbe lasciato codice orfano. Il codice è **recuperabile da git** se una
> futura strategia event-driven vorrà riutilizzarlo; la conoscenza è preservata in
> questo documento + `reports/s7_*`. Dettagli §6.

## 3. Cronologia valutazioni (4 run, 1 superseded)

### 3.1 Run Finnhub (early 2026-07-03) — INCONCLUSIVE, superseded
`reports/s7_backtest/ALPHA_A5_gate_report_2026-07-03.md`. Il piano Finnhub copre
`calendar/earnings` solo ~30 giorni indietro → **0 eventi**. Superseded dal run FMP (3.2).

### 3.2 ALPHA-A5 large-cap (2026-07-03, FMP) — FAIL
`reports/s7_backtest/ALPHA_A5_gate_report_2026-07-03_fmp.md` · harness
`scripts/backtest_s7_pead.py` @ 04a9a28. Finestra 2026-01-01/05-15, 96 eventi (76 BEAT,
20 MISS) con |surprise|≥5%.

| Criterio | Soglia | Valore | Esito |
|---|---|---|---|
| BEAT drift 20d | ≥+1.5% | +1.96% | ✅ soglia |
| Hit-rate | >55% | 51% | ❌ FAIL |
| n BEAT | ≥30 | 76 | ✅ |
| Small/mid-cap | test large-vs-small | n=0 | ❌ non testato |

**Addendum distribuzione (BEAT long, n=76):** excess vs SPY media **+0.05%**, mediana
**−1.07%** → il drift raw è **beta, non alpha**. Media raw senza i top-5 winner = −0.23%
(5 outlier reggono tutto). Nessuna dose-response (surprise 5-15% → excess −0.30%; 15-50%
→ −1.97%). Tutti i 76 eventi large-cap (≥$10B), bucket small/mid a n=0. Lato MISS (n=20):
excess +0.16%, niente.

**Verdetto:** PEAD su large-cap USA da raw surprise è indistinguibile da zero — coerente
con la letteratura (fattore competuto via). S7 **SHELVED** in `strategy_lifecycle`.

### 3.3 POC-1 small/mid PEAD (2026-07-04) — INCONCLUSIVE_DATA
`reports/s7_poc/POC1_smallmid_report_2026-07-04.md` · `scripts/backtest_s7_smallmid.py`.
Tesi: l'edge PEAD accademico vive su small/mid-cap, non large. Soglia |surprise|≥5%,
bucket $300M–$10B, ADV20g≥$5M, benchmark IWM, 30bps, hold 20 sedute.

**Funnel:** 8.440 eventi → 6.177 simboli → 600 campionati (alfabetico, budget Starter) →
442 eventi small/mid common-equity → **15 sopravvissuti** a barre IEX + liquidità.

| Direzione | n | mean netto | hit netto | Verdetto |
|---|---|---|---|---|
| BEAT (long) | 7 | −0.56% | 57% | FAIL (n<30) |
| MISS (short) | 8 | −2.18%* | 50% | FAIL (n<30) |

**Verdetto gate POC-1: `INCONCLUSIVE_DATA`** (n=15 < min 30). Due bug di codice trovati e
corretti in esecuzione (meccanici, non toccano le soglie pre-reg): (1) mismatch unità
market-cap (USD grezzi vs milioni → bucket small/mid sempre vuoto senza fix), (2) crash
batch Alpaca su ticker preferred (`ABR-PD`) che azzerava ~100 simboli buoni per batch.

**Onestà limiti:** i 15 sopravvissuti sono $3.78B–$9.9B (upper-mid, nessuna vera
small-cap <$2B passa i filtri barre+liquidità); campionamento alfabetico bias non
misurato; n=7/8 → segni non sono evidenza contro l'ipotesi, solo rumore.

### 3.4 POC-2 transcript tone ALPHA-A3 (2026-07-15) — FAIL (decision-grade)
`reports/s7_poc/S7_REVIVAL_DECISION_REPORT_2026-07-15.md`. Pipeline: fetch transcript
(Alpha Vantage `EARNINGS_CALL_TRANSCRIPT` free tier, 25 req/day, $0 vendor) → tone scoring
DK-CoT via Ollama (`kimi-k2.6:cloud` + GLM agreement `glm-5.2:cloud`) → join tone↔excess_20d
(forward return dai CSV POC-1/A5) → `scripts/analyze_s7_tone.py`.

**Copertura:** 73 transcript (coverage 60.8% > soglia 50%). Gate pre-reg: n≥30, Spearman
IC(tone,excess_20d)≥+0.10, tercile spread top−bottom≥+1.5%, IC>0 in entrambe le metà
(split per data).

| Metrica | Valore | Soglia | Esito |
|---|---|---|---|
| n | 73 | ≥30 | ✅ |
| Coverage | 60.8% | ≥50% | ✅ |
| Spearman IC(tone, excess_20d) | **+0.012** | ≥+0.10 | ❌ ~0 |
| Tercile spread top−bottom | **−0.93%** (top +1.19%, bottom +2.12%) | ≥+1.5% | ❌ invertito |
| Split-half IC (1a/2a metà) | **−0.230 / +0.244** | >0 entrambe | ❌ opposti |
| IC dentro BEAT (n=58) | **−0.016** | — | ❌ nessun tone additivo |
| Concordanza guidance/surprise | 69% | — | descrittivo |
| **Agreement kimi↔glm (n=20)** | **Spearman +0.858** | — | robusto跨-modello |

**Verdetto gate ALPHA-A3: `FAIL`.** Il tone score del transcript non predice l'excess
return 20d. I due modelli convergono sui tone score (ρ=+0.858) → il FAIL **non è artefatto
kimi**: il tone non porta alpha, robustamente. Nessun debole segnale da rifinire: IC≈0,
spread invertito, split-half opposto, nessun tone additivo oltre la surprise.

## 4. Decisioni PO

- **2026-07-03:** S7 SHELVED dopo ALPHA-A5 FAIL (large-cap = beta). Riapertura solo via
  decisione PO (universo small/mid o POC transcript-tone).
- **2026-07-15 (PO-5, issue #26):** S7 = **KEEP** — finire POC-2 a decision-grade entro
  2026-08-01. **Override** della raccomandazione REMOVE (per inseguire transcript-tone
  prima di rimuovere). Condizionale pre-registrata: **"Se POC-2 FAIL → REMOVE."**
- **2026-07-15 (post-POC-2):** POC-2 FAIL a decision-grade → condizionale **attivata** →
  **REMOVE applicato**. #38 relabel `ready-for-human` → PO ha confermato rimozione +
  documentazione + commit/deploy/rebuild.

## 5. Sintesi evidence

| Valutazione | Esito | n | Ragione |
|---|---|---|---|
| ALPHA-A5 large-cap (07-03) | FAIL | 76 | drift = beta SPY, hit 51%, no dose-response |
| POC-1 small/mid (07-04) | INCONCLUSIVE | 15 | n<30, copertura IEX/liquidità insufficiente |
| POC-2 transcript tone (07-15) | FAIL | 73 | IC≈0, spread invertito, split-half opposto, cross-model |

L'edge numerico (raw surprise PEAD) è competuto su large-cap; l'edge qualitativo
dichiarato (transcript tone) è confutato跨-modello a sample decision-grade; l'universo
small/mid (dove l'edge accademico vive) non è raggiungibile con copertura dati
sufficiente nei POC eseguiti. S7 non ha prodotto ordini in tutto il suo lifecycle.

## 6. Rimozione (2026-07-15) — scope: rimozione completa

**Rimosso (tutta la superficie runtime S7, eliminata dal repo):**
- Strategy dir `src/strategies/s7/` (`__init__.py`, `strategy.py`, `signal.py`).
- `src/models/pead.py` (SurpriseSignal, EarningsLLMOutput).
- `src/workers/pead_worker.py` (classificazione 8-K via Ollama) +
  `src/workers/earnings_pead_worker.py` (Finnhub earnings → surprise).
- `src/connectors/earnings_calendar.py` (EarningsCalendarProvider — nessun consumer
  esterno oltre il worker S7; eliminato con esso).
- `src/api/routes/pead_routes.py` + import/include in `src/api/main.py`.
- Beat task `pead-ingestion` + `earnings-pead` (e relativi import) in
  `src/workers/celery_app.py` → ferma l'inference idle Ollama su 8-K.
- Config: entry S7 in `config/strategies.yaml`; S7 stop sizing in
  `config/trading.yaml`; `PEAD_*` settings in `src/config.py` (§275-296).
- API/display: `S7_STRATEGY`/`S7_DETAIL`/`GATES_S7`/`SENSITIVITY_S7` + key `"s7"` in
  `src/api/routes/strategies.py`; righe `pead-ingestion`/`earnings-pead` in
  `system_routes.py`.
- `src/store/redis_store.py`: metodi `write/read_pead_signal`,
  `is/mark_pead_processed` (le chiavi Redis `signal:*:pead_event` /
  `pead:processed:*` non sono più scritte; TTL 30d le esaurisce).
- Cross-ref commenti: `stop_policy.py` (FrozenStop.strategy type hint),
  `portfolio_scheduler.py` (S7 sizing map), `loss_feedback.py`, `ingestion.py`,
  `celery_app.py` (commenti beat/EDGAR).
- Test S7-specifici: `tests/strategies/test_s7_pead.py`,
  `tests/workers/test_pead_worker.py`, `tests/workers/test_earnings_pead_worker.py`,
  `tests/connectors/test_earnings_calendar.py`. Aggiornati:
  `tests/test_p0_13_strategy_containment.py` (guard anti re-introduzione),
  `tests/test_p1_promotion_gate_logic.py` (rimosso test S7 promotion),
  `tests/portfolio/test_stop_policy.py` (rimosso S7 dal fixture). Suite: 2796 pass/0 fail.

**Preservato (evidenza + guard):**
- Script POC: `scripts/{backtest_s7_pead,backtest_s7_smallmid,analyze_s7_events,
  fetch_s7_transcripts,score_s7_transcripts,analyze_s7_tone,s7_poc_helpers}.py`.
- `tests/analysis/test_s7_poc_helpers.py` (testa `scripts/s7_poc_helpers.py`).
- Report/CSV di valutazione in `reports/s7_*` (gitignored, evidenza locale).
- DB audit history: `strategy_lifecycle_audit` (immutable — nessuna row S7 era
  seedata in `strategy_lifecycle`; lo storico SHELVED/FAIL resta in audit).
- `pead_signals` table: mai materializzata (DDL solo doc, nessuna migration) →
  nessuna migration di drop necessaria.
- `tests/test_p0_13_strategy_containment.py::TestS7NotInOperationalRegistry` =
  guard che S7 non ricompaia nel `StrategyRegistry` operativo.

**Non preservato (recuperabile da git):** il worker PEAD / pipeline EDGAR /
classificazione 8-K, che una nota di design indicava come "mattone di S9/Vettore B".
S9/Vettore B non esistono; l'8-K path era già disabilitato (commit `171437e`); il
connector earnings non aveva consumer esterni → mantenerlo avrebbe lasciato codice
orfano. Se una futura strategia event-driven vorrà riutilizzare la superficie PEAD,
il codice è recuperabile da git (commit pre-rimozione) e la conoscenza è in questo doc.

**Costi consuntivi S7 (lifecycle):** FMP Starter $29 (mese 07, disdetto 07-15 #23);
ALPHA-A5/POC-1 $0 vendor aggiuntivo (FMP Starter); POC-2 $0 (Alpha Vantage free tier);
LLM Ollama: chiamate 8-K classification (idle, periodo SHELVED) + 73 kimi + 20 GLM POC-2.

## 7. References

- Decision report POC-2: `reports/s7_poc/S7_REVIVAL_DECISION_REPORT_2026-07-15.md`
- POC-1 report: `reports/s7_poc/POC1_smallmid_report_2026-07-04.md` · decision
  `reports/s7_poc/S7_REVIVAL_DECISION_REPORT_2026-07-04.md`
- ALPHA-A5 report: `reports/s7_backtest/ALPHA_A5_gate_report_2026-07-03_fmp.md`
- Plans: `docs/superpowers/plans/2026-07-04-s7-revival-resume.md`,
  `docs/superpowers/plans/2026-07-04-s7-revival-pocs.md`
- Roadmap: `docs/ROADMAP_DATA_ALPHA_2026-07-02.md` §Vettore A (ALPHA-A2/A3/A5)
- Strategy doc: `docs/strategies/s7-pead.md`, `docs/strategies.md` §S7
- Issues: #38 (S7 revival, closes con la PR di rimozione), #26 (PO-5 decision)