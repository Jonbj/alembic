# P1_ACCEPTANCE_AUDIT_2026-06-19

## 1. Executive Summary

This is an independent, read-only acceptance audit of the P1 remediation items from `docs/ALEMBIC_REMEDIATION_MASTER_PLAN_2026-06-18.md`. The audit verifies whether the implemented P1 work satisfies the Master Plan acceptance criteria and whether the system is ready to start P2.

Since the P0 audit was closed (`P0_ACCEPTED_WITH_RUNTIME_MONITORING`), a significant amount of follow-up work has been completed that also closes several P0 residual risks:

- **P0-04 residual (file-based SoT):** `strategy_lifecycle` DB table + registry DB mode override (`2cfe087`).
- **P0-05 residual (real-path stop-loss):** legacy `execution.py` now blocks BUY when price is unavailable, preventing unprotected market orders (`32bb83b`).
- **P0-11 residual (same-bar fill):** `BacktestOrchestrator` now fills at next-bar open by default, with a `fill_at_next_open` flag for backward compatibility (`219cd74`).

P1 items that have been implemented:

- **P1-01** Cost model realism: ADV fallback reduced to 500K shares, fixed-cost net-Sharpe (`bf66454`).
- **P1-03** Gate fixes: Gate 2 denominator corrected to all windows, Gate 4 silent clamp removed (`d5fc282`).
- **P1-05** Portfolio combiner: net-exposure cap (opt-in) + BUY/SELL conflict resolution (`0905bf3`, regression fix `6f202c3`).
- **P1-06** Cockpit + alerting: cockpit derives from registry SoT, worker-beat-lag and fallback-rate alerts (`7cef529`).
- **P1-09** S4 pipeline: signal freshness gate (4h TTL) + per-session idempotency (`5e57572`).

P1 items **not yet implemented** (and therefore blocking any `P1_ACCEPTED_*` verdict):

- **P1-02** Real historical stress test (2008/2020/2022).
- **P1-04** S4 gate script runnable + lifecycle report.
- **P1-07** S3 sizing point-in-time + survivorship-free.
- **P1-08** S1 survivorship-free universe (`active_at`).
- **P1-10** Promotion Readiness Gate logic (DB table exists, but no gate enforcement).
- **P1-11** CI expansion (mypy, pip-audit, secret scan, coverage).
- **P1-12** Paper/live divergence monitoring.
- **P1-13** Walk-forward with real IS/OOS fitting measurement.

**Test status:**

- Full suite: `2260 passed, 1 skipped, 44 warnings in 443.86s` (verified independently).
- P1 targeted tests: `79 passed, 1 warning in 1.51s`.

**Overall verdict: `P1_PARTIAL_DO_NOT_START_P2`.**

The implemented P1 work is directionally correct and test-covered, but the P1 set is incomplete. Critical validation/governance items (stress test, S4 gate, promotion gate, walk-forward, divergence monitoring) are missing. P2 must not start until the missing P1 items are closed or formally accepted as P2 scope with PO approval.

---

## 2. Overall Verdict

| Verdict | Meaning | Applicability |
|---------|---------|---------------|
| `P1_ACCEPTED_READY_FOR_P2` | All P1 closed, residual risk negligible, P2 may start | Not applicable |
| `P1_ACCEPTED_WITH_RUNTIME_MONITORING` | Core P1 closed, residual risks only observable in runtime | Not applicable |
| `P1_PARTIAL_DO_NOT_START_P2` | Some P1 incomplete or accepted with material residual risk | **Selected** |
| `P1_NOT_ACCEPTED` | P1s fundamentally failed | Not selected — implemented P1s pass tests |

**Rationale for `P1_PARTIAL_DO_NOT_START_P2`:**

1. **Missing P1 items are validation/governance blockers, not cosmetic.** P1-02 (real stress), P1-04 (S4 gate report), P1-07 (S3 PIT sizing), P1-08 (S1 survivorship-free), P1-10 (promotion gate), P1-12 (paper/live divergence), and P1-13 (walk-forward) are all required by the Master Plan before any strategy promotion or live reconsideration.
2. **Implemented P1s are partial relative to their own acceptance criteria.**
   - P1-03 fixes Gate 2 and Gate 4 but does not implement Gate 3 SPA / multiple-comparison correction.
   - P1-05 implements cap and conflict resolution but leaves the cap opt-in (`None` default) and does not prove vol-targeter is applied before constraints.
   - P1-06 implements cockpit SoT and two alerts but lacks readiness dashboard, paper/live divergence metric, cap-violation alerting, and stale-data flag.
   - P1-09 implements freshness and idempotency but lacks RAG/supervisor path and LOO ICIR verification.
   - P1-10 creates the DB table but does not implement the promotion gate logic.
3. **The full suite is green,** but the test suite does not yet cover the missing P1 acceptance criteria.
4. **P0 residual risks are now largely closed** by the follow-up commits, which improves the P0 verdict but does not change the P1 status.

---

## 3. P1 Acceptance Matrix

| P1 | Commit(s) | Acceptance Criteria (Master Plan) | Tests Added | Status | Residual Risk / Gap | Verdict |
|----|-----------|-------------------------------------|-------------|--------|---------------------|---------|
| P1-01 Cost model ADV reale + fixed cost + cost-aware sizing | `bf66454` | net-Sharpe include costi reali + fisso; sizing cost-aware | 8 (`test_p1_cost_model_realism.py`) | `ACCEPTED_WITH_MINOR_RESIDUAL_RISK` | Cost-aware sizing in live path not verified; live portfolio scheduler does not consult cost model for order sizing; fixed cost field exists but default is 0.0 | ACCEPTED_WITH_MINOR_RESIDUAL_RISK |
| P1-02 Stress test storico reale | — | 2008/2020/2022 o "non testabile" | 0 | `NOT_IMPLEMENTED` | No commit; no test; no stress module | NOT_IMPLEMENTED |
| P1-03 Gate fixes + SPA | `d5fc282` | Gate 2 denominator all windows; Gate 4 no silent clamp; SPA for Gate 3 | 11 (`test_p1_validation_gates_truth.py`) | `ACCEPTED_WITH_MINOR_RESIDUAL_RISK` | Gate 1 default `n_trials=1` remains, only documented as biased; Gate 3 SPA / multiple comparison not implemented | ACCEPTED_WITH_MINOR_RESIDUAL_RISK |
| P1-04 S4 gate script runnable + lifecycle | — | S4 gate report eseguibile e riproducibile | 0 | `NOT_IMPLEMENTED` | No runnable S4 gate report; promotion still blocked by registry validator, not by gate report | NOT_IMPLEMENTED |
| P1-05 Combiner net-cap + conflict + vol-targeter order | `0905bf3`, `6f202c3` | net-exposure ≤ cap sempre; conflitti BUY/SELL risolti; vol targeter pre-constraint | 6 (`test_p1_portfolio_combiner_risk.py`) | `ACCEPTED_WITH_MINOR_RESIDUAL_RISK` | Cap is opt-in (`None` default); no invariant enforcement in live path; vol-targeter is applied AFTER cap, so scaled orders can violate cap; no test for vol-targeter pre-constraint | ACCEPTED_WITH_MINOR_RESIDUAL_RISK |
| P1-06 Operator cockpit + readiness + alerting | `7cef529` | Cockpit veritiero + alert di safety attivi (fallback rate, worker lag, cap violation, divergence) | 12 (`test_p1_monitoring_heartbeat_cockpit.py`) | `ACCEPTED_WITH_MINOR_RESIDUAL_RISK` | Readiness dashboard, paper/live divergence metric, cap-violation alerting, stale-data flag, why-trade banner missing | ACCEPTED_WITH_MINOR_RESIDUAL_RISK |
| P1-07 S3 sizing PIT + survivorship-free | — | S3 volatilità causale (expanding/rolling window) | 0 | `NOT_IMPLEMENTED` | `src/strategies/s3/strategy.py:88` still flagged as full-sample lookahead; no PIT sizing test | NOT_IMPLEMENTED |
| P1-08 Survivorship-free universe S1 | — | Universo filtrato per `active_at` PIT | 0 | `NOT_IMPLEMENTED` | `active_at` field exists but unused; no PIT universe filter | NOT_IMPLEMENTED |
| P1-09 LLM/S4 pipeline (recency, RAG/supervisor, LOO ICIR, dedup) | `5e57572` | Pipeline S4 PIT, recency, RAG/supervisor presenti; LOO ICIR pulito | 15 (`test_p1_s4_freshness_idempotency.py`) | `ACCEPTED_WITH_MINOR_RESIDUAL_RISK` | RAG/supervisor not implemented; LOO ICIR not verified; idempotency is fail-open on Redis down | ACCEPTED_WITH_MINOR_RESIDUAL_RISK |
| P1-10 Promotion Readiness Gate + requalification | `2cfe087` | Gate non bypassabile; promozioni con evidenza | 10 (`test_p1_strategy_sot_db.py`) | `NEEDS_FOLLOWUP` | `strategy_lifecycle` table exists and registry loads mode from DB, but no promotion gate logic enforces `gate_report_id`, `approved`, `paper_days`, or blocks mode transitions | NEEDS_FOLLOWUP |
| P1-11 CI expansion | — | CI verde con mypy + pip-audit + secret scan + coverage | 0 | `NOT_IMPLEMENTED` | No CI expansion; no formal gate preventing regressions | NOT_IMPLEMENTED |
| P1-12 Paper/live divergence monitoring | — | Metrica divergenza attiva ≥ soglia | 0 | `NOT_IMPLEMENTED` | No divergence metric implemented | NOT_IMPLEMENTED |
| P1-13 Walk-forward con fitting reale su IS | — | Degrado OOS misurato | 0 | `NOT_IMPLEMENTED` | No walk-forward fitting measurement | NOT_IMPLEMENTED |

**P0 residual follow-up now closed (not P1, but improves P0 verdict):**

| P0 Follow-up | Commit | Closes | Tests | Status |
|--------------|--------|--------|-------|--------|
| P0-04 DB-backed strategy SoT | `2cfe087` | `strategy_lifecycle` table + `load_mode_from_db` | 10 (`test_p1_strategy_sot_db.py`) | ACCEPTED |
| P0-05 Real-path stop-loss guard | `32bb83b` | Block BUY when price unavailable in `execution.py` | 7 (`test_p1_execution_realpath_hardening.py`) | ACCEPTED |
| P0-11 T+1 fill | `219cd74` | `BacktestConfig.fill_at_next_open=True` default, next-bar-open fill | 11 (`test_p1_backtest_tplus1_fill.py`) | ACCEPTED |

---

## 4. Commit-by-Commit Review

### P1-01 — `bf66454` — Cost model realism

- **Files changed:** `src/backtest/costs/realistic.py`, `src/backtest/engine/data_replay.py`, `src/backtest/engine/orchestrator.py`, `tests/backtest/test_data_replay.py`, `tests/test_p1_cost_model_realism.py`
- **What it does:**
  - Reduces ADV fallback from 10M to 500K shares in `DataReplay` and `RealisticCostModel`.
  - Adds `BacktestConfig.annual_fixed_cost` and `BacktestResult.net_annualized_return()` / `net_sharpe()`.
- **Acceptance evidence:**
  - `src/backtest/costs/realistic.py` ADV fallback is 500K.
  - `src/backtest/engine/orchestrator.py:96` `annual_fixed_cost` field.
  - `src/backtest/engine/orchestrator.py:116-150` net return and net Sharpe methods.
  - 8 tests pass covering ADV fallback, impact increase, fixed-cost drag.
- **Gaps:**
  - The live portfolio scheduler does not use the cost model to size orders.
  - Fixed cost defaults to 0.0, so existing backtests still report gross Sharpe unless callers explicitly set it.
  - No test proves that the live path consults the cost model.
- **Verdict:** `ACCEPTED_WITH_MINOR_RESIDUAL_RISK`.

### P1-03 — `d5fc282` — Validation gate fixes

- **Files changed:** `src/backtest/gates/gate_2_walkforward.py`, `src/backtest/gates/gate_4_regime.py`, `tests/test_p1_validation_gates_truth.py`
- **What it does:**
  - Gate 2: denominator is now `len(wf_results)` (all windows, including no-trade).
  - Gate 4: removes silent clamp; returns failed when `min_passing_regimes` exceeds available regimes.
- **Acceptance evidence:**
  - `src/backtest/gates/gate_2_walkforward.py` denominator logic.
  - `src/backtest/gates/gate_4_regime.py` no clamp.
  - 11 tests pass.
- **Gaps:**
  - Gate 1 default `n_trials=1` is documented as inflated but not changed.
  - Gate 3 SPA / multiple comparison correction is not implemented.
  - No gate report lifecycle links gate results to `strategy_lifecycle`.
- **Verdict:** `ACCEPTED_WITH_MINOR_RESIDUAL_RISK`.

### P1-05 — `0905bf3` / `6f202c3` — Portfolio combiner risk

- **Files changed:** `src/portfolio/combiner.py`, `tests/test_p1_portfolio_combiner_risk.py`
- **What it does:**
  - `PortfolioCombiner.aggregate()` enforces `net_exposure_cap` when explicitly provided.
  - BUY/SELL conflicts on the same symbol are dropped.
  - Regression fix `6f202c3` changes default cap from `1.0` to `None` (opt-in) and removes duplicate `_compute_nav`.
- **Acceptance evidence:**
  - `src/portfolio/combiner.py:44-47` cap opt-in.
  - `src/portfolio/combiner.py:125-134` conflict resolution.
  - `src/portfolio/combiner.py:137-170` cap enforcement with `ConstraintViolation`.
  - 6 tests pass.
- **Gaps:**
  - Cap is opt-in. Live code may not pass `net_exposure_cap`, leaving the portfolio unprotected.
  - Vol-targeter is applied AFTER cap enforcement (`src/portfolio/combiner.py:104-108`). Scaled orders can re-violate the cap.
  - No test asserts vol-targeter order relative to constraints.
  - The live portfolio scheduler does not appear to instantiate `PortfolioCombiner` with a cap.
- **Verdict:** `ACCEPTED_WITH_MINOR_RESIDUAL_RISK`.

### P1-06 — `7cef529` — Cockpit + alerting

- **Files changed:** `src/monitoring/__init__.py`, `src/monitoring/alerts.py`, `src/monitoring/cockpit.py`, `tests/test_p1_monitoring_heartbeat_cockpit.py`
- **What it does:**
  - `get_cockpit_status()` derives strategy list from live `StrategyRegistry`.
  - Adds `check_worker_beat_lag()` and `check_fallback_rate()` alert primitives.
  - Schedule is derived from `StrategyEntry.schedule`.
- **Acceptance evidence:**
  - `src/monitoring/cockpit.py:13-39` derives status from registry.
  - `src/monitoring/alerts.py:11-36` alert functions.
  - 12 tests pass.
- **Gaps:**
  - No readiness dashboard (e.g. "S1 is not ready for promotion because gate X failed").
  - No paper/live divergence metric.
  - No cap-violation alerting integration.
  - No stale-data flag or "why-trade" explanation.
  - No banner distinguishing paper vs live mode in cockpit output.
  - Alert functions are primitives only; no scheduler or router wires them to Telegram/dashboard.
- **Verdict:** `ACCEPTED_WITH_MINOR_RESIDUAL_RISK`.

### P1-09 — `5e57572` — S4 freshness + idempotency

- **Files changed:** `migrations/024_p1_s4_freshness_audit_enum.sql`, `src/strategies/s4/config.py`, `src/workers/portfolio_scheduler.py`, `tests/test_p1_s4_freshness_idempotency.py`, `tests/workers/test_portfolio_scheduler.py`
- **What it does:**
  - `_filter_stale_signals()` drops signals older than `max_signal_age_hours` (default 4h).
  - `_get_fired_signal_ids()` / `_mark_signal_fired()` track fired S4 signals per session date in Redis.
  - Audit rows for `SIGNAL_STALE_SKIP` and `SIGNAL_DUPLICATE_SKIP`.
- **Acceptance evidence:**
  - `src/strategies/s4/config.py` `max_signal_age_hours` field.
  - `src/workers/portfolio_scheduler.py` freshness/idempotency helpers.
  - 15 tests pass.
- **Gaps:**
  - RAG/supervisor path is not implemented.
  - LOO ICIR verification is not implemented.
  - Redis unreachable for idempotency is fail-open (warning only), so duplicate signals can fire if Redis is down.
  - No test verifies the audit row is actually written by the scheduler.
- **Verdict:** `ACCEPTED_WITH_MINOR_RESIDUAL_RISK`.

### P1-10 — `2cfe087` — Strategy lifecycle SoT

- **Files changed:** `migrations/025_strategy_lifecycle.sql`, `src/strategies/registry.py`, `tests/test_p1_strategy_sot_db.py`
- **What it does:**
  - Creates `strategy_lifecycle` table with `strategy_id`, `mode`, `target_mode`, `gate_report_id`, `promoted_by`, `promoted_at`, `approved`.
  - `StrategyRegistry.load_mode_from_db()` overrides YAML mode from DB; fails open on DB error.
- **Acceptance evidence:**
  - `migrations/025_strategy_lifecycle.sql` schema.
  - `src/strategies/registry.py:115-154` DB loader.
  - 10 tests pass.
- **Gaps:**
  - The promotion gate logic is not implemented. There is no function that checks `gate_report_id`, `approved`, paper days, or other readiness criteria before allowing a mode transition.
  - `target_mode`, `promoted_at`, `approved` columns exist but are not used.
  - No API/UI endpoint for promotion requests or approval workflow.
- **Verdict:** `NEEDS_FOLLOWUP`.

### P0-04 follow-up — `2cfe087` — DB-backed strategy SoT

- Same commit as P1-10. This closes the P0-04 residual risk about file-based SoT.
- **Verdict:** `ACCEPTED`.

### P0-05 follow-up — `32bb83b` — Real-path stop-loss guard

- **Files changed:** `src/workers/execution.py`, `tests/test_p1_execution_realpath_hardening.py`, `tests/workers/test_execution_worker.py`
- **What it does:** blocks BUY in `run_execution_cycle` when EMA price is `None` or `data_client` is unavailable, preventing an unprotected market order.
- **Acceptance evidence:**
  - `tests/test_p1_execution_realpath_hardening.py` 7 tests pass.
- **Verdict:** `ACCEPTED`.

### P0-11 follow-up — `219cd74` — T+1 fill

- **Files changed:** `src/backtest/engine/data_replay.py`, `src/backtest/engine/orchestrator.py`, `src/backtest/costs/realistic.py`, `src/backtest/engine/order_simulation.py`, `tests/test_p1_backtest_tplus1_fill.py`
- **What it does:**
  - `DataReplay` accepts optional `opens` DataFrame and exposes `market_at_open()`.
  - `BacktestConfig.fill_at_next_open=True` by default.
  - Orders are buffered and filled at next bar's open; last-bar pending filled at last bar close.
- **Acceptance evidence:**
  - 11 tests pass.
- **Verdict:** `ACCEPTED`.

---

## 5. Test Coverage Review

| P1 | Test file | Count | Covers failure mode? | Missing coverage | Should be CI gate? |
|----|-----------|-------|----------------------|------------------|--------------------|
| P1-01 | `test_p1_cost_model_realism.py` | 8 | ADV fallback, fixed-cost drag | Live cost-aware sizing, default fixed cost > 0 | yes |
| P1-03 | `test_p1_validation_gates_truth.py` | 11 | Gate 2 denominator, Gate 4 clamp | Gate 3 SPA, Gate 1 default n_trials > 1 | yes |
| P1-05 | `test_p1_portfolio_combiner_risk.py` | 6 | Cap enforcement, conflict drop | Cap opt-in default, vol-targeter pre-constraint, live integration | yes |
| P1-06 | `test_p1_monitoring_heartbeat_cockpit.py` | 12 | Cockpit SoT, beat lag, fallback rate | Readiness, divergence, cap-violation, stale-data, banner | yes |
| P1-09 | `test_p1_s4_freshness_idempotency.py` | 15 | Freshness gate, idempotency | RAG/supervisor, LOO ICIR, Redis-down behavior | yes |
| P1-10 | `test_p1_strategy_sot_db.py` | 10 | Table schema, DB mode override | Promotion gate logic, approval workflow | yes |
| P0-04 follow-up | `test_p1_strategy_sot_db.py` | 10 | DB mode override, fallback | Concurrent promotion workflow | yes |
| P0-05 follow-up | `test_p1_execution_realpath_hardening.py` | 7 | No price → no BUY | Partial-fill/reject handling | yes |
| P0-11 follow-up | `test_p1_backtest_tplus1_fill.py` | 11 | T+1 fill, last-bar fill | Stochastic strategy determinism, cross-machine parity | yes |

**Total P1 + P0-follow-up targeted tests passing:** 79.

**Full suite:** 2260 passed, 1 skipped.

---

## 6. Residual Risks

1. **P1-02 missing:** no real historical stress test. S1/S4 could fail in 2008/2020/2022 and we would not know until live.
2. **P1-04 missing:** no runnable S4 gate report. S4 promotion remains blocked by registry hard-coding, not by a reproducible gate.
3. **P1-05 cap is opt-in.** If the live scheduler does not pass `net_exposure_cap`, the combiner provides no protection. Vol-targeter applied after the cap can re-violate it.
4. **P1-06 cockpit incomplete.** Operators still lack readiness, divergence, cap-violation, and stale-data visibility. Alert primitives are not wired to a router.
5. **P1-07 / P1-08 missing:** S3 lookahead and S1 survivorship bias remain unaddressed. Any backtest numbers for S1/S3 are still contaminated.
6. **P1-09 missing RAG/supervisor and LOO ICIR.** S4 signals may still contain noise or ensemble-weight contamination.
7. **P1-10 promotion gate not enforced.** The DB table exists but mode transitions are not validated against gate reports or paper days.
8. **P1-11 missing:** no CI expansion. Regressions in gates, cost model, or S4 pipeline could be missed.
9. **P1-12 missing:** paper/live divergence is not measured. We cannot validate that paper results predict live execution.
10. **P1-13 missing:** no walk-forward fitting measurement. IS/OOS degradation is unknown.
11. **P0-05 partial-fill/reject handling** is still not implemented, even though real-path stop-loss is now guarded.
12. **P1-09 idempotency fail-open on Redis down:** if Redis is unreachable, duplicate S4 signals can fire.

---

## 7. Runtime Validation Required

| Item | Runtime data needed | How to validate | Success criterion |
|------|---------------------|-----------------|-------------------|
| Full suite green (CI) | Clean CI environment | Run `pytest` in CI | 2260 passed, 1 skipped, deterministic re-run |
| P1-01 live cost-aware sizing | Live/paper order history | Verify scheduler uses cost model for sizing | Order notional inversely related to impact estimate |
| P1-05 cap invariant in live | Live portfolio state | Monitor `constraint_violations` + exposure | No exposure > cap when cap is set |
| P1-06 alert wiring | Worker heartbeats, fallback rate | Trigger stale beat / high fallback in dry-run | Telegram/dashboard alert fires |
| P1-09 S4 freshness in live | Signal timestamps, order logs | Run scheduler with 5h-old signal | Signal skipped, audit row written |
| P1-09 S4 idempotency in live | Redis, order logs | Run same signal twice in one session | Second run skipped |
| P1-10 promotion gate | DB + gate reports | Attempt promotion without approved gate report | Transition rejected |
| P1-12 paper/live divergence | ≥90 days paper + live fills | Compare fill price vs backtest fill, slippage | Divergence metric stable within declared tolerance |
| P1-02 real stress | Historical bear data | Run S1/S4 through 2008/2020/2022 | Strategy behavior documented or marked "non testabile" |

---

## 8. Follow-up Fixes Before P2

Before starting P2, the following P1 gaps must be closed or formally accepted by the Project Owner:

1. **P1-02 — Real historical stress test**
   - Implement stress periods (2008, 2020, 2022) or formally label strategies as "not stress-testable".
   - Add tests that fail if a strategy silently passes stress without real data.

2. **P1-04 — S4 gate report lifecycle**
   - Make the S4 gate script runnable and reproducible.
   - Link S4 gate results to `strategy_lifecycle.gate_report_id`.

3. **P1-05 — Make cap invariant + vol-targeter pre-constraint**
   - Default `net_exposure_cap` to a safe value (e.g. 1.0) or require the live scheduler to always pass it.
   - Apply vol-targeter before the cap, or re-validate cap after scaling.
   - Add a test that fails when scaled orders violate the cap.

4. **P1-06 — Complete cockpit + alert wiring**
   - Add readiness dashboard, paper/live divergence metric, cap-violation alerting, stale-data flag, why-trade explanation.
   - Wire alert primitives to Telegram/dashboard scheduler.

5. **P1-07 / P1-08 — S3 PIT sizing + S1 survivorship-free universe**
   - Fix S3 volatilità full-sample.
   - Filter S1 universe by `active_at` point-in-time.

6. **P1-09 — RAG/supervisor + LOO ICIR**
   - Add RAG/supervisor to the production sentiment path.
   - Verify LOO ICIR has no overlapping/future data.

7. **P1-10 — Promotion Readiness Gate logic**
   - Implement the gate that checks `gate_report_id`, `approved`, paper days, and safety criteria before any mode transition.
   - Add API/UI workflow for promotion request + approval.

8. **P1-11 — CI expansion**
   - Add mypy, pip-audit, secret scan, and coverage gates to CI.

9. **P1-12 — Paper/live divergence monitoring**
   - Implement the divergence metric and alerting.

10. **P1-13 — Walk-forward fitting measurement**
    - Add IS/OOS fitting measurement to walk-forward reports.

11. **P0-05 residual — Partial-fill / reject handling**
    - Define and test behavior when Alpaca returns a partial fill or order reject.

---

## 9. P2 Readiness Recommendation

**Do not start P2 until:**

1. P1-02, P1-04, P1-07, P1-08, P1-10, P1-11, P1-12, and P1-13 are closed or explicitly scoped out of P2 with PO approval.
2. P1-05 cap is enforced by default (not opt-in) and vol-targeter is pre-constraint.
3. P1-06 cockpit includes readiness and divergence metrics.
4. P1-09 includes RAG/supervisor and LOO ICIR verification.
5. Full CI expansion (P1-11) is active.

**If the above are closed, the verdict can be reconsidered as `P1_ACCEPTED_WITH_RUNTIME_MONITORING`** because:

- Core validation truth (t+1 fill, cost model, gate fixes, combiner cap, S4 freshness) is in place.
- Cockpit and audit chain provide observability.
- Remaining uncertainties (90-day paper divergence, real stress behavior, LOO ICIR in production) are runtime-observable.

**P2 should then be sequenced as:**
1. Docker/ops hardening + DR (WS-14).
2. Strategy requalification experiments on honest backtests (S1, S3, S4).
3. Controlled paper program (≥90 days) with divergence monitoring.
4. Live reconsideration only after paper evidence + closed P0/P1.

---

## 10. Stop Point

Non ho modificato file di codice, non ho scritto codice eseguibile, non ho creato patch, non ho eseguito commit, non ho avviato worker o pipeline, non ho inviato ordini. L'unico file creato è questo report di audit in `docs/P1_ACCEPTANCE_AUDIT_2026-06-19.md`.

**Raccomandazione:** il verdict è `P1_PARTIAL_DO_NOT_START_P2`. Non iniziare i P2 finché i gap di P1 non sono chiusi o formalmente accettati dal Project Owner. Nessuna strategia deve essere promossa e nessun ordine live deve essere autorizzato prima della chiusura dei P1 di validazione/governance.
