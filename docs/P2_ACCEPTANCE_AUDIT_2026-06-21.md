# Alembic P2 Acceptance Audit — 2026-06-21

**Auditor:** Kimi (independent technical acceptance auditor)  
**Mode:** Read-only audit. No code changes, no patch writes, no worker/pipeline starts, no broker/API live calls, no orders placed, no live trading authorization, no strategy promotions, no P3/P4 work initiated.  
**Scope:** P2 remediation stream (P2-01 through P2-05) as defined in `docs/ALEMBIC_REMEDIATION_MASTER_PLAN_2026-06-18.md`.  
**Baseline commit audited:** `55cbf56` (HEAD at audit date).  
**Report date:** 2026-06-21  
**Verdict:** **P2_ACCEPTED_WITH_RUNTIME_MONITORING**

---

## 1. Executive Summary

The P2 engineering blockers have been implemented and are covered by passing tests:

- **P2-01 CI Hardening** — blocking `ruff`/`pytest`/`coverage` gates are wired; soft security gates (`mypy`, `pip-audit`, `gitleaks`) run but do not block merges.
- **P2-02 Promotion Gate Wiring** — state machine `research → paper → supervised_paper → live` is enforced in code and DB; `GLOBAL_LIVE_PROMOTION_ENABLED=False` makes live promotion fail-closed.
- **P2-03 Validation Truth Wiring** — point-in-time sizing, walk-forward gates, and historical stress period extraction are wired into S1/S3/S4 backtest runners.
- **P2-04 Monitoring / Operator Cockpit** — an 8-key health dict is exposed via `/api/system/readiness`, `/api/system/decisions`, `/api/system/scheduler`, and `/api/system/activity`.
- **P2-05 Execution Edge Cases** — the three P2-05 blockers (Redis idempotency fail-open, un-wired net exposure cap, vol-targeter re-violating cap) plus a broker-reject callback are implemented in `src/workers/portfolio_scheduler.py` and `src/portfolio/orchestrator.py`.

The full test suite matches the claimed baseline (**2386 passed, 1 skipped, 0 failures**). The 18 dedicated P2-05 execution-edge-case tests and the 48 dedicated P2-01..P2-04 tests all pass.

However, **documentation/operator-surface drift** prevents a clean `P2_ACCEPTED_READY_FOR_CONTROLLED_PAPER` verdict:

1. `README.md` line 27 and `docs/ARCHITECTURE.md` section 8.2 still list P2-05 as **Pending / NOT_IMPLEMENTED**, contradicting `docs/P2_STATUS_2026-06-21.md`.
2. `src/api/routes/strategies.py` hardcodes S1 as `status: "validated"` with stale backtest metrics (OOS Sharpe 0.5128, annual return 7%, max drawdown 15%) that do not match either the current `config/strategies.yaml` (`mode: supervised_paper`, `promotion_blocked: true`) or the operator cockpit truth source.
3. `docs/P2_STATUS_2026-06-21.md` lists S2 as `paper`, while `config/strategies.yaml` and the lifecycle migration seed S2 as `disabled`/`research` with 0% allocation.

These are not code safety defects, but they are **operational-readiness defects**: an operator reading the README or the strategy API could misread authorization state and performance expectations. For that reason the conservative verdict is **P2_ACCEPTED_WITH_RUNTIME_MONITORING**, with explicit controlled-paper pre-conditions listed in Section 14.

---

## 2. Audit Scope & Constraints

- Audited only P2-01 through P2-05 closure claims.
- Did **not** re-audit P0/P1 fixes in depth; only regression-tested via the full suite and spot checks.
- Did **not** run live brokers, workers, pipelines, or place orders.
- Did **not** evaluate P3/P4 scope, new alpha ideas, or live promotion readiness beyond the P2 gates.
- Verdict options used: `P2_ACCEPTED_READY_FOR_CONTROLLED_PAPER`, `P2_ACCEPTED_WITH_RUNTIME_MONITORING`, `P2_PARTIAL_DO_NOT_START_CONTROLLED_PAPER`, `P2_NOT_ACCEPTED`.

---

## 3. Inputs Reviewed

| Document / File | Purpose |
|-----------------|---------|
| `archive/…/04_remediation_plans/ALEMBIC_REMEDIATION_MASTER_PLAN_2026-06-18.md` | P2 scope, taxonomy, acceptance criteria (archived 2026-06-23) |
| `archive/…/03_acceptance_audits/P0_ACCEPTANCE_AUDIT_2026-06-18.md` | Prior P0 baseline (archived 2026-06-23) |
| `archive/…/03_acceptance_audits/P1_RE_ACCEPTANCE_AUDIT_2026-06-19.md` | Prior P1 baseline (archived 2026-06-23) |
| `docs/P2_STATUS_2026-06-21.md` | P2 self-declaration of completion |
| `docs/RESIDUAL_RISK_REGISTER.md` | Open/closed residual risks |
| `docs/ARCHITECTURE.md` | Architecture docs; checked for stale P2-05 status |
| `README.md` | Project status table; checked for stale P2-05 status |
| `docs/strategies.md`, `docs/strategies/s7-pead.md`, `docs/FRONTEND_OPERATOR_GUIDE.md` | Strategy/operator surfaces sanity |
| `src/workers/portfolio_scheduler.py` | P2-05-A/B/D implementation |
| `src/portfolio/orchestrator.py` | P2-05-C vol-targeter/enforcer ordering |
| `src/portfolio/constraints.py` | `ConstraintEnforcer` cap wiring |
| `src/portfolio/vol_targeting.py` | Vol-targeter scaling logic |
| `src/strategies/promotion.py` | P2-02 promotion state machine & global kill-switch |
| `src/monitoring/cockpit.py`, `src/api/routes/system_routes.py` | P2-04 operator cockpit |
| `src/strategies/s1/backtest.py`, `src/strategies/s3/backtest.py`, `src/strategies/s4/backtest.py` | P2-03 validation truth wiring |
| `src/api/routes/strategies.py` | Public strategy status/metrics API |
| `config/trading.yaml`, `config/strategies.yaml` | Risk limits and strategy authorization config |
| `.github/workflows/ci.yml` | P2-01 CI gate wiring |
| `tests/workers/test_p2_05_execution_edge_cases.py` | P2-05 dedicated test evidence |
| `tests/workers/test_p2_cockpit.py`, `tests/workers/test_p2_promotion.py`, `tests/workers/test_p2_validation_truth.py`, `tests/workers/test_p2_ci.py` | P2-01..P2-04 test evidence |

---

## 4. P0 / P1 Baseline

Per the prior audit reports (not re-audited in depth):

- **P0:** Accepted with runtime monitoring. Critical execution defects closed; residual risks tracked in `docs/RESIDUAL_RISK_REGISTER.md`.
- **P1:** Accepted with runtime monitoring. All 13 P1 items had building blocks implemented and tested; full suite 2321 passed, 1 skipped.

No P0/P1 regressions were introduced by the P2 commit (verified by full suite passing at 2386 tests).

---

## 5. Pre-Audit Baseline

- `docs/P2_STATUS_2026-06-21.md` declared P2-01/02/03/04/05 **Complete / ACCEPTED**.
- Controlled paper trading, live trading, and strategy promotions remained **Not authorized** pending this audit.
- Claimed test count: **2386 passed, 1 skipped, 0 failures** (+33 vs pre-P2-05 baseline of 2353).

---

## 6. P2 Commit Review

Audited commit: `55cbf56` (HEAD, clean working tree at audit time).

Key code-path changes supporting the P2 completion claim:

| P2 Item | File / Lines | Evidence |
|---------|--------------|----------|
| P2-05-A Redis fail-closed | `src/workers/portfolio_scheduler.py:302-322` | `_get_fired_signal_ids()` returns `None` on any Redis exception; log line explicitly states "all S4 BUY signals will be skipped (fail-closed)". |
| P2-05-A idempotency filter | `src/workers/portfolio_scheduler.py:325-335` | `_apply_idempotency_filter()` drops S4 BUY orders for symbols in the skip set; SELLs are preserved. |
| P2-05-A caller wiring | `src/workers/portfolio_scheduler.py:794, 934` | Caller checks for `None` and populates `_idempotency_skip` with all S4 symbols, then filters final orders. |
| P2-05-B risk config loading | `src/workers/portfolio_scheduler.py:338-352` | `_load_risk_config()` reads `config/trading.yaml` with safe defaults (`max_portfolio_exposure=0.50`, `max_single_asset_pct=0.10`) and falls back to defaults on any error. |
| P2-05-B cap wiring | `src/workers/portfolio_scheduler.py:704, 710-711` and `src/portfolio/constraints.py:60-69` | `ConstraintEnforcer` instantiated with `max_portfolio_exposure` and `max_single_asset_pct` from config. |
| P2-05-C vol before enforcer | `src/portfolio/orchestrator.py:221-229` | `PortfolioVolTargeter.scale_orders()` runs **before** `ConstraintEnforcer.enforce()`, with an explicit code comment explaining the fix. |
| P2-05-D broker reject callback | `src/workers/portfolio_scheduler.py:1232-1357` | `_submit_portfolio_orders()` accepts `_on_broker_reject`; exceptions are logged and callback is invoked without silently dropping rejections. |
| P2-02 global live kill-switch | `src/strategies/promotion.py:27` | `GLOBAL_LIVE_PROMOTION_ENABLED: bool = False` module-level constant. |
| P2-02 state machine | `src/strategies/promotion.py:43-87` | `request_promotion()` enforces sequential transitions and raises `PromotionBlockedError` for any live promotion while the flag is `False`. |
| P2-02 DB approval fail-closed | `src/workers/portfolio_scheduler.py:78-138` | `_filter_approved_strategies()` excludes strategies on `approved=False` or DB error; only missing rows are admitted (legacy fail-open, documented). |
| P2-04 cockpit | `src/monitoring/cockpit.py:43-128` | `get_cockpit_alerts()` returns the 8-key health dict (`redis_healthy`, `redis_writeable`, `db_healthy`, `killswitch_active`, `stale_signals`, `worker_beat_lag`, `last_signal_age_minutes`, `last_cycle_age_minutes`). |
| P2-04 endpoints | `src/api/routes/system_routes.py:80-248` | Exposes `/api/system/readiness`, `/api/system/decisions`, `/api/system/scheduler`, `/api/system/activity`. |
| P2-03 stress periods | `src/strategies/s1/backtest.py:18, 85, 101`, `src/strategies/s3/backtest.py:14, 82, 99`, `src/strategies/s4/backtest.py:15, 94, 113` | All three runners import `extract_historical_stress_periods()` and surface `is_oos_degradation_ratio`. |
| P2-01 CI gates | `.github/workflows/ci.yml` | `ruff`, `pytest`, and `coverage (fail_under=60)` are blocking; `mypy`, `pip-audit`, `gitleaks` are soft (`continue-on-error: true`). |

---

## 7. P2 Acceptance Matrix

| Ticket | Requirement | Evidence | Verdict | Notes |
|--------|-------------|----------|---------|-------|
| P2-01 | CI blocking gates: ruff, pytest, coverage ≥60% | `.github/workflows/ci.yml`; full suite passes; `fail_under=60` in coverage step | **ACCEPTED** | Soft gates (mypy, pip-audit, gitleaks) are documented and expected to become blocking in P3. |
| P2-02 | Promotion state machine wired; live promotion fail-closed | `src/strategies/promotion.py`; DB migrations 024/025; `GLOBAL_LIVE_PROMOTION_ENABLED=False` | **ACCEPTED** | S1 correctly demoted to `supervised_paper`; S4 `paper`/`promotion_blocked=true`; S7 contained in R&D. |
| P2-03 | Validation truth wiring: PIT sizing, walk-forward, stress periods, LOO ICIR fix | `src/strategies/s1/s3/s4/backtest.py`; S3 backtest uses PIT universe | **ACCEPTED** | IC T0 contamination remains a documented methodological risk (out of P2 scope). |
| P2-04 | Operator cockpit with 8-key health dict and endpoints | `src/monitoring/cockpit.py`; `src/api/routes/system_routes.py`; `docs/FRONTEND_OPERATOR_GUIDE.md` | **ACCEPTED** | No frontend UI for readiness/lifecycle — operator uses curl; documented gap. |
| P2-05 | Execution edge cases closed (idempotency, exposure cap, vol-cap ordering, broker reject) | `src/workers/portfolio_scheduler.py`; `src/portfolio/orchestrator.py`; 18 dedicated tests | **ACCEPTED** | See detailed matrix in Section 8. |

---

## 8. P2-05 Execution Edge Case Matrix

| Sub-item | Required Behavior | Implementation | Tests | Status |
|----------|---------------------|----------------|-------|--------|
| **P2-05-A** | Redis unavailable must fail-closed (no duplicate BUYs) | `_get_fired_signal_ids()` returns `None` on any exception; caller translates `None` into a skip-all-S4-BUYs set via `_apply_idempotency_filter()` (`src/workers/portfolio_scheduler.py:302-335, 794, 934`) | `test_returns_none_on_redis_connection_error`, `test_returns_none_on_redis_timeout`, `test_removes_buy_for_skipped_symbol`, `test_keeps_sell_for_skipped_symbol` | **CLOSED** |
| **P2-05-B** | Net exposure cap must be wired to config | `_load_risk_config()` reads `risk.max_portfolio_exposure` and `risk.max_position_pct` from `config/trading.yaml` with safe defaults; `ConstraintEnforcer.__init__` accepts both caps (`src/workers/portfolio_scheduler.py:338-352, 704, 710-711`; `src/portfolio/constraints.py:60-69`) | `test_reads_max_portfolio_exposure_from_yaml`, `test_reads_max_single_asset_pct_from_yaml`, `test_returns_safe_defaults_when_file_missing`, `test_custom_values_override_defaults` | **CLOSED** |
| **P2-05-C** | Vol-targeter must not re-violate cap | `PortfolioVolTargeter.scale_orders()` runs **before** `ConstraintEnforcer.enforce()` in `PortfolioOrchestrator._combine_orders()`; enforcer is the final constraint pass (`src/portfolio/orchestrator.py:218-229`) | Covered by orchestrator constraint tests and P2-05 suite | **CLOSED** |
| **P2-05-D** (additional) | Broker rejections must not be silently dropped | `_submit_portfolio_orders()` accepts `_on_broker_reject` callback and invokes it on any submission exception (`src/workers/portfolio_scheduler.py:1232-1357`) | `test_on_broker_reject_called_when_submit_raises`, `test_rejected_order_not_in_submitted_list`, `test_reject_on_first_does_not_stop_second`, `test_buy_blocked_when_price_missing`, `test_sell_proceeds_without_price`, `test_bracket_failure_leaves_no_submitted_entry` | **CLOSED** |

All 18 dedicated P2-05 tests pass.

---

## 9. Documentation / Frontend Sanity Check

| Surface | Expected State | Actual State | Finding |
|---------|----------------|--------------|---------|
| `docs/P2_STATUS_2026-06-21.md` | P2-05 Complete / ACCEPTED | Matches | None |
| `README.md` lines 17-31 | P2-05 Complete | Line 27 still says **P2-05 Execution Edge Cases — Pending**; line 28 says Kimi audit **Not yet authorized** | **MEDIUM**: contradicts P2_STATUS. Must be reconciled before controlled paper. |
| `docs/ARCHITECTURE.md` section 8.2 | P2-05 implemented | Line 618 still says **P2-05 Pending Safety Items (NOT_IMPLEMENTED — blocks Kimi P2 Acceptance Audit)** | **MEDIUM**: same doc drift as README. |
| `src/api/routes/strategies.py` | Reflects current strategy status & backtest truth | Hardcodes S1 as `status: "validated"`, OOS Sharpe 0.5128, annual return 7%, max drawdown 15%. `config/strategies.yaml` says S1 `mode: supervised_paper`, `promotion_blocked: true`. `reports/s1_backtest/summary.json` still contains the same 0.5128/5.42% values (report dated 2026-05-30 per `config/s1_strategy.yaml`). | **MEDIUM**: public API misrepresents authorization status and uses stale performance snapshot. Not a code execution risk, but an operator-misunderstanding risk. |
| `docs/P2_STATUS_2026-06-21.md` | Strategy authorization table matches config | Lists S2 as `paper` while `config/strategies.yaml` and migration 025 seed S2 as `disabled`/`research` with 0% allocation | **LOW**: doc error; S2 cannot trade because it is disabled in registry. |
| `docs/FRONTEND_OPERATOR_GUIDE.md` | Cockpit endpoints documented | Complete and accurate; notes live trading NOT authorized | None |

**Documentation verdict:** P2 implementation is closed in code, but the project status table, architecture doc, and strategy API have not been fully reconciled. These are **blockers for a READY-FOR-PAPER verdict** but not for P2 engineering acceptance.

---

## 10. P0 / P1 Regression Watchlist

Spotted during the audit; no regressions observed, but these items should remain on the controlled-paper watchlist:

- **S1 backtest report stale:** `reports/s1_backtest/summary.json` is from the 2026-05-30 config snapshot. P2-03 wired truth sources but did not regenerate the S1 report. Before any capital increase or promotion discussion, regenerate the report with the current PIT pipeline and realistic costs.
- **Gate thresholds remain very conservative:** S1 passes all gates with `min_sharpe=0.0`, `min_oos_sharpe=0.0`, `min_regime_sharpe=0.0`, `max_drawdown_allowed=-0.3`, `min_cumulative_return=-0.1`. Passing is therefore almost tautological. This is a known methodological residual risk, not a P2 code defect.
- **S2 status confusion:** P2_STATUS says `paper`; config/registry says disabled. Ensure the lifecycle table and config are reconciled before anyone attempts to enable S2.
- **Pyramiding guard:** `open_trade_symbols` is passed to `_submit_portfolio_orders()` (P0-05), but the idempotency skip set only covers S4. S1/S4 duplicate-signal logic is separate and was not re-audited in depth.

---

## 11. Tests Run

| Test Command | Result |
|--------------|--------|
| `pytest -q` | **2386 passed, 1 skipped, 42 warnings** — matches P2_STATUS claim |
| `pytest tests/workers/test_p2_05_execution_edge_cases.py -v` | **18 passed** |
| `pytest tests/workers/test_p2_cockpit.py tests/workers/test_p2_promotion.py tests/workers/test_p2_validation_truth.py tests/workers/test_p2_ci.py -v` | **48 passed** (P2-01..P2-04 dedicated tests) |

No test failures, no unexpected skips beyond the single known skipped test.

---

## 12. Residual Risks

Per `docs/RESIDUAL_RISK_REGISTER.md`:

- R-01 through R-03 are closed by P2-05.
- **R-04 through R-12 remain open** and must be watched during controlled paper:
  - IC T0 contamination / lookahead in S3 backtest (methodological).
  - S1 same-bar fill, zero-cost, survivorship bias, circular stress/regime assumptions in historical report.
  - S4/S7 news-driven alpha lacking confirmed IC > placebo and dedicated gate reports.
  - Operator cockpit has no frontend UI; reliance on curl/manual inspection.
  - Soft CI security gates (mypy/pip-audit/gitleaks) not yet blocking.
  - Documentation drift noted in Section 9.

These residual risks are consistent with the `P2_ACCEPTED_WITH_RUNTIME_MONITORING` verdict.

---

## 13. Overall Verdict

**P2_ACCEPTED_WITH_RUNTIME_MONITORING**

Reasoning:

- All five P2 engineering items are implemented and test-covered.
- P2-05, the former release blocker, is verifiably closed in code.
- No P0/P1 regressions.
- Documentation and public API surfaces still contain stale / contradictory statements that could mislead an operator about P2 closure, strategy status, and backtest performance. These must be cleaned up before controlled paper starts.
- A dry-run of a controlled-paper cycle should be executed and signed off before real paper capital is exposed.

The verdict is **not** `P2_ACCEPTED_READY_FOR_CONTROLLED_PAPER` and **not** `P2_PARTIAL_DO_NOT_START_CONTROLLED_PAPER`. The code is ready enough to begin the *pre-flight* steps for controlled paper, but paper trading itself should not start until the pre-conditions in Section 14 are satisfied.

---

## 14. Recommendation for Controlled Paper

**Do not start controlled paper trading until all of the following are complete and signed off by the Product Owner:**

1. **Documentation reconciliation:**
   - Update `README.md` line 27 to **P2-05 Execution Edge Cases — Complete** and line 28 to **Kimi P2 Acceptance Audit — COMPLETE (with runtime monitoring)**.
   - Update `docs/ARCHITECTURE.md` section 8.2 to reflect P2-05 implementation and remove the "blocks Kimi P2 Acceptance Audit" language.
   - Correct `docs/P2_STATUS_2026-06-21.md` S2 status to match `config/strategies.yaml` (`disabled`/`research`).

2. **Strategy API / status truth:**
   - Either regenerate `reports/s1_backtest/summary.json` with the current PIT pipeline and update `src/api/routes/strategies.py` to read from it dynamically, **or** change the API to report `mode: supervised_paper`, `promotion_blocked: true`, and add a `data_quality_warning` field explaining that the displayed metrics are a stale snapshot. The API must not describe S1 as `validated` while the config says it is demoted and promotion-blocked.

3. **End-to-end paper dry-run:**
   - Start the stack in paper mode (Alpaca paper credentials, `GLOBAL_LIVE_PROMOTION_ENABLED=False`).
   - Trigger one portfolio cycle manually via the Celery beat / scheduler path.
   - Verify `/api/system/readiness` returns all-green (`redis_healthy=true`, `redis_writeable=true`, `db_healthy=true`, `killswitch_active=false`, `stale_signals=false`, `worker_beat_lag=false`).
   - Verify `/api/system/decisions` records only expected paper decisions.
   - Confirm no orders were sent to a live account.

4. **Kill-switch rehearsal:**
   - POST `/api/admin/killswitch` with `{"active": true}` and confirm the next portfolio cycle halts.
   - Reset to `false` before resuming.

5. **PO sign-off:**
   - PO must explicitly authorize controlled paper trading after reviewing this audit report and the reconciliation PR.

Once the above are satisfied, controlled paper trading may begin under the following **runtime monitoring conditions**:

- Daily review of `/api/system/readiness` and `/api/system/decisions`.
- Weekly review of the residual risk register.
- A 30-day checkpoint gate before any discussion of `supervised_paper → live` promotion.
- `GLOBAL_LIVE_PROMOTION_ENABLED` must remain `False` until a separate live-readiness audit is completed.

---

## 15. Stop Point

This audit was performed in read-only mode. The auditor did **not**:

- modify any repository files except this audit report;
- write code patches or migrations;
- start workers, pipelines, or the trading stack;
- call live brokers or external trading APIs;
- place, cancel, or modify orders;
- authorize live trading, controlled paper trading, or strategy promotions;
- initiate P3 or P4 work.

The next authorized action is for the project team to address the documentation/API reconciliation items in Section 14 and seek PO sign-off before starting controlled paper trading.
