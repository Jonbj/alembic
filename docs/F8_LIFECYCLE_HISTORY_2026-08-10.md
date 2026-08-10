# F8 (feedback:regime_scale) — Lifecycle History and Removal

> **Esito finale: F8 RITIRATA il 2026-08-10.** La premessa di dipendenza seriale
> che una regola di equity-curve de-risk richiede è falsificata sull'unità
> per-GIORNO (S1 +0.065, S4 +0.017 — nessuna dipendenza rilevabile) e il meccanismo
> stesso è indipendentemente rotto: un trigger azzera lo stesso `last_adjustment`
> che il ramo decay legge, quindi una sleeve che ri-triggera più spesso della
> finestra di decay può uscire solo con una serie di vittorie — che è esattamente
> ciò che una sleeve in perdita non ha. Decisione PO (2026-08-07, issue #134):
> **Ritirare F8, non ritararlo.** Modello di rimozione: S7 lifecycle
> (`docs/S7_LIFECYCLE_HISTORY_2026-07-15.md`).

Questo documento raccoglie la storia di F8 (design, implementazione, test,
misure, decisione PO) come record permanente post-rimozione. Il codice è
**recuperabile da git** (commit `9171099` per il wiring, `aef3828` per la
persistenza shadow) e la conoscenza è preservata in questo doc + i report
riferiti qui sotto.

---

## 1. Design rationale

F8 era una **regola di equity-curve trading**: scala la size di una sleeve in
base al **P&L della sleeve stessa**. In letteratura standard aggiunge valore
**solo se i rendimenti dei trade sono positivamente autocorrelati** — se le
perdite si raggruppano davvero. Su una serie indipendente è inseguimento di
rumore che paga solo il drag; su una serie mean-reverting è attivamente al
contrario (taglia la size proprio prima del rimbalzo).

Era la seconda leva del loss-feedback ratchet (la prima era l'innalzamento
dell'entry threshold `feedback:entry_threshold`, che resta ed è governata da
#191). Le due condividevano il nome del meccanismo ma sono leve indipendenti:

- **`entry_threshold`** — alza la soglia di ingresso dopo perdite S4. Agisce
  filtrando i segnali, non riducendo la size. *Viva, in produzione.*
- **`regime_scale`** (F8) — riduce la size della sleeve dopo le sue stesse
  perdite. Era cablata in `apply_feedback_scale` del path portfolio dietro
  flag `apply_regime_scale: false` (shadow-only). **Ritirata.**

### Cosa aveva di specifico

- ×0.80 per trigger (floored a 0.20).
- Per-strategy: la leva scala di S1 non tocca S4.
- Step-down con 3 vittorie consecutive (recovery) o 24h di quiete (decay).
- Applicazione gated da `apply_regime_scale` (bool o lista di strategy ids).

## 2. Implementazione (superficie codice)

| Componente | Path | Note |
|---|---|---|
| Orchestrator | `src/portfolio/orchestrator.py` | `_scale_gate`, `feedback_scales`/`apply_feedback_scale` params, `feedback_shadow` field su `CycleResult` |
| Performance worker | `src/workers/performance.py` | `_load_loss_feedback_config` (defaults `regime_scale_factor`, `regime_min_scale`, `apply_regime_scale`), `_step_threshold_down` (restituisce `(threshold, scale)`), `run_loss_feedback_check` (legge/scrive scale), `_format_feedback_stall_section` (riporta scale), weekly_structured |
| Portfolio scheduler | `src/workers/portfolio_scheduler.py` | `_read_feedback_regime_scales`, `_build_f8_shadow_rows`, wiring F8 in `run_portfolio_cycle` |
| Execution worker | `src/workers/execution.py` | `_load_feedback_regime_scale`, `regime_mult *= feedback_scale` in `run_execution_cycle` |
| Redis store | `src/store/redis_store.py` | `set_feedback_regime_scale`, `get_feedback_regime_scale`, ramo `feedback:regime_scale` in `refresh_feedback_ttl` |
| PG store | `src/store/pg_store.py` | `insert_f8_shadow` (writer della `f8_regime_scale_shadow`) |
| API | `src/api/routes/trading.py` | campo `regime_scale` in `/api/feedback/status` |
| Config | `config/trading.yaml` | `loss_feedback.{regime_scale_factor, regime_min_scale, apply_regime_scale}` |
| Migration | `migrations/040_f8_regime_scale_shadow.sql` | tabella `f8_regime_scale_shadow` (cycle_ts, strategy, scale, unscaled_weight, scaled_weight, applied) |
| Script osservativo | `scripts/ratchet_reachability.py`, `scripts/f8_regime_scale_shadow_evidence.py` | misure read-only, motivazione della decisione |
| Script operativo | `scripts/audit_deployment_decomposition.py` | riga "after F8" nel modello di decomposizione |

### Cosa è stato rimosso vs preservato (2026-08-10, scope = rimozione completa)

**Rimosso** (tutta la superficie runtime F8, eliminata dal repo):
- Tutti i rami F8 nel source (vedi tabella sopra).
- Tutti i test F8-specifici: `tests/test_f8_feedback_regime_scale.py`,
  `tests/test_f8_shadow_evidence.py`, `tests/test_ratchet_reachability.py`,
  `tests/test_serial_dependence.py`. Porzioni F8 rimosse da
  `tests/workers/test_loss_feedback.py`, `tests/portfolio/test_orchestrator_feedback_scale.py`,
  `tests/workers/test_portfolio_scheduler.py`, `tests/test_redis_store.py`,
  `tests/store/test_pg_store_stop_methods.py`, `tests/test_p1_execution_realpath_hardening.py`,
  `tests/workers/test_execution_worker.py`, `tests/workers/test_performance_hidden_costs.py`.
- Script F8: `scripts/ratchet_reachability.py`, `scripts/f8_regime_scale_shadow_evidence.py`.
  Porzioni F8 rimosse da `scripts/audit_deployment_decomposition.py`.

**Preservato** (evidenza + guard):
- Test guard anti re-introduzione: `tests/test_f8_regime_scale_removed.py`
  (modello: `tests/test_p0_13_strategy_containment.py::TestS7NotInOperationalRegistry`).
- Migration 040: la tabella `f8_regime_scale_shadow` resta in piedi (non droppata
  automaticamente) finché l'operatore non esegue la migration 045
  (`migrations/045_drop_f8_regime_scale_shadow.sql`). Le righe già scritte sono
  evidenza locale di cosa F8 avrebbe fatto se fosse stato live.
- `scripts/f8_regime_scale_shadow_evidence.py` — i report raw restano in
  `reports/f8_*` (gitignored, evidenza locale). Lo script stesso rimosso.

**Non preservato** (recuperabile da git): commit `9171099` (wiring), `aef3828`
(persistenza shadow), `77d2af9` (per-strategy gate). Questo doc è la conoscenza
consolidata.

## 3. Misure (la premessa è falsificata)

### 3.1 Reachability (2026-07-29 → 2026-08-05)

`scripts/ratchet_reachability.py` (22 test). Replica il ratchet reale alla
cadenza live (30 min, Mon-Fri 14:00-21:00 UTC) su tutto lo storico dei trade
e conta quale ramo di uscita scatta davvero.

```
                              S1        S4
ticks valutati               453       453
triggered=True             39.5%     32.0%
down-steps                    26        26
recovery (win streak)          0        15
decay (24h di quiete)          2         9
decay clock starved           21        17
episodi sotto 1.0              2         8
escape a 1.0                   1         8
```

Il ramo decay condivide l'orologio col trigger → una sleeve che ri-triggera
più spesso di 24h può uscire solo con una serie di vittorie. S1 ne produce
zero, S4 ne produce 15 (recovery completa). Differenza `win rate` 6.7% (S1)
vs 40.0% (S4): la soglia di 3 vittorie consecutive è fuori portata per S1 per
costruzione.

### 3.2 Confondente per-day (2026-07-30)

```
S1   per-trade ac=+0.3177  streaky        per-DAY ac=+0.0646   nessuna dipendenza
S4   per-trade ac=+0.4585  streaky        per-DAY ac=+0.0173   nessuna dipendenza
```

L'80-89% delle coppie consecutive di trade nello stesso orario di uscita
condivide il giorno di uscita — il contatore per-trade conta la stessa
giornata storta una volta per posizione aperta. Il confondente non è una
stima statistica: è un fatto strutturale di come la sleeve tiene le
posizioni.

### 3.3 Verdetto (2026-08-07)

La premessa di dipendenza seriale è falsificata sull'unità per-GIORNO
(S1 ac +0.065, S4 ac +0.017 — "no detectable dependence"). L'onestà
matematica richiede di segnalare che n=10 (S1) e n=26 (S4) sono
campioni piccoli e il "nessuna dipendenza" è sotto-potenziato; ma
l'**asimmetria** che decide: F8 costa manutenzione e complessità per una
premessa non supportata, e il beneficio atteso è al massimo un effetto
troppo piccolo per essere visto. Tenerlo "per sicurezza" significa
conservare codice inerte con una trappola dentro — lo stato assorbente.

## 4. Decisioni PO

- **2026-07-09** — `regime_scale_factor` 0.80; `apply_regime_scale: false` (shadow).
- **2026-07-21** (`#32`) — TTL 48h → 96h; persistenza in `f8_regime_scale_shadow`
  (migration 040) per dare al flip decision una traiettoria vera invece di un
  replay ricostruito. Per-strategy allowlist nel flag.
- **2026-07-27** (`#32`) — gate per-strategia, allowlist. S4 PASS, S1 FAIL sul
  contatore registrato. Programma: ship mechanism, leave flag off.
- **2026-07-30** (`#134`) — misura per-day rivela che il contatore ha un
  confondente cross-sezionale; la premessa crolla.
- **2026-08-03** (`#134`) — la decisione del titolo della issue ("ratchet mal
  tarato o decisione di allocazione?") ha una terza risposta: nessuna delle due.
  Consiglio PO: ritirare F8.
- **2026-08-07** — **PO DECISION: F8 RITIRATA.** Scadenza `F8|2026-08-08`
  risolta con un giorno di anticipo.
- **2026-08-10** — rimozione applicata + lifecycle history scritto.

## 5. Sintesi evidence

| Misura | Esito | n | Ragione |
|---|---|---|---|
| Reachability (07-29) | warning | 453/livello | trigger resetta decay clock → assorbente |
| Per-day ac (07-30) | FAIL premise | 10 S1 / 26 S4 | nessuna dipendenza seriale |
| Storico live (08-07) | FAIL premise | 58 S1 / 258 S4 | per-trade streaky, per-day ~0 |
| Verdetto finale | FAIL | — | doppio conteggio + recovery irraggiungibile + state assorbente |

## 6. Rimozione (2026-08-10) — scope: rimozione completa

**Rimosso (tutta la superficie runtime F8, eliminata dal repo):**
- `src/portfolio/orchestrator.py`: `_scale_gate`, `feedback_scales`/`apply_feedback_scale`
  come parametri di `run_cycle`, campo `feedback_shadow` su `CycleResult`, ramo
  di scaling nel merge weighted-sum.
- `src/workers/portfolio_scheduler.py`: `_read_feedback_regime_scales`,
  `_build_f8_shadow_rows`, pluming F8 in `run_portfolio_cycle`, log F8,
  persistenza `f8_regime_scale_shadow`.
- `src/workers/performance.py`: `regime_scale_factor`/`regime_min_scale`/`apply_regime_scale`
  come config defaults, ramo scale in `run_loss_feedback_check` (trigger,
  recovery, decay), ramo scale in `_step_threshold_down`, ramo scale in
  `_refresh_feedback_ttl`, riga `Regime scale:` in `_format_feedback_stall_section`,
  campo `current_scale` in `weekly_structured`.
- `src/workers/execution.py`: `_load_feedback_regime_scale`, riga
  `regime_mult *= feedback_scale` in `run_execution_cycle`.
- `src/store/redis_store.py`: `set_feedback_regime_scale`, `get_feedback_regime_scale`,
  ramo `feedback:regime_scale` in `refresh_feedback_ttl` (TTL refresh).
- `src/store/pg_store.py`: `insert_f8_shadow`.
- `src/api/routes/trading.py`: campo `regime_scale` in `GET /api/feedback/status`.
- `config/trading.yaml`: chiavi `loss_feedback.{regime_scale_factor, regime_min_scale, apply_regime_scale}`.
- Script F8: `scripts/ratchet_reachability.py`, `scripts/f8_regime_scale_shadow_evidence.py`.
- Test F8: `tests/test_f8_feedback_regime_scale.py`, `tests/test_f8_shadow_evidence.py`,
  `tests/test_ratchet_reachability.py`, `tests/test_serial_dependence.py`. Porzioni F8
  rimosse da `tests/workers/test_loss_feedback.py`, `tests/portfolio/test_orchestrator_feedback_scale.py`,
  `tests/workers/test_portfolio_scheduler.py`, `tests/test_redis_store.py`,
  `tests/store/test_pg_store_stop_methods.py`, `tests/test_p1_execution_realpath_hardening.py`,
  `tests/workers/test_execution_worker.py`, `tests/workers/test_performance_hidden_costs.py`.
- `scripts/audit_deployment_decomposition.py`: riga "after F8" nel modello di
  decomposizione.

**Preservato (evidenza + guard):**
- Migration 040 (tabella `f8_regime_scale_shadow`): resta in piedi. Migration 045
  (`migrations/045_drop_f8_regime_scale_shadow.sql`) preparata ma NON applicata —
  è l'operatore a decidere quando dropparla. Le righe scritte restano
  l'evidenza della traiettoria che F8 avrebbe avuto.
- Test guard anti re-introduzione: `tests/test_f8_regime_scale_removed.py`
  (modello: `tests/test_p0_13_strategy_containment.py::TestS7NotInOperationalRegistry`).
  Pattern: nessun metodo Redis, nessun metodo pg_store, nessun campo CycleResult,
  nessuna chiave config.

**Non preservato (recuperabile da git):**
- Il wiring del 07-23 (commit `9171099`): il gate per-strategia, il
  `_scale_gate`, il `feedback_shadow` field. Re-introduzione deve passare per
  un design + premise retest freschi, non per `git revert`.
- La persistenza shadow (commit `aef3828`): migration 040 + `insert_f8_shadow`.

**Costi consuntivi F8 (lifecycle):**
- 0$ vendor (nessuna API esterna).
- LLM: zero chiamate F8-specifiche (F8 era codice deterministico, non LLM).
- Storage: ~140 righe in `f8_regime_scale_shadow` (07-21 → 08-07) — gitignored.

## 7. References

- Issue tracker: #134 (parent), #32 (F8 evolution), #191 (sister lever).
- Misure: `scripts/ratchet_reachability.py`, `scripts/f8_regime_scale_shadow_evidence.py`
  (entrambi rimossi dal repo, recuperabili da git).
- Report: `docs/F8_REGIME_SCALE_SHADOW_EVIDENCE_2026-07-21.md`,
  `docs/FORENSIC_DAILY_REPORT_2026-08-05.md`, `docs/FORENSIC_DAILY_REPORT_2026-08-06.md`.
- Modello di rimozione: `docs/S7_LIFECYCLE_HISTORY_2026-07-15.md`.
- Carta di osservazione: `docs/evidence/OBSERVATION_CHARTER.md` (F8 ritiro è
  rimozione di codice inerte, non consuma deroga).
