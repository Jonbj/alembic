# P0_ACCEPTANCE_AUDIT_2026-06-18

## 1. Executive Summary

This is an independent, read-only acceptance audit of the thirteen P0 remediation items declared closed in `docs/ALEMBIC_REMEDIATION_MASTER_PLAN_2026-06-18.md`.

The P0 commits implement meaningful safety and governance improvements: S1 is demoted from live, paper/live mode is explicit, strategy allocations are hard-enforced, stop-loss is on by default, duplicate BUY is guarded, the kill-switch is re-checked before submission, market-clock failures abort the cycle, risk config bounds are server-side, the regime multiplier is no longer hardcoded, reproducibility and anti-lookahead tests exist, the test suite baseline is green for the P0 tests, and S4/S7 are contained.

However, several declared P0s are only **partially closed** when measured against their full Master Plan acceptance criteria:

- **P0-02** still leaves the daily-analysis cron running with `--dangerously-skip-permissions`, i.e. the LLM agent retains destructive capability.
- **P0-06** fixes the pre-submission re-check but does **not** implement human-gated recovery, 2FA/cooldown, or kill-switch audit.
- **P0-08** implements server-side bounds but does **not** audit config changes or require elevated approval for weakening risk controls.
- **P0-10** captures `run_id`, `data_hash` and `seed`, but **not model version/code version**, and the orchestrator does not consume the manifest for deterministic execution.
- **P0-12** targeted tests pass, but the **full suite could not be completed** in this environment (hung around 70 %), and the audit-log write is outside the trade transaction and lacks a `record_id` link.

Targeted P0 tests (80 tests) **all pass** in the local `.venv`. This is necessary but not sufficient for acceptance: some acceptance criteria are behavioral/governance items that tests do not yet cover.

**Overall verdict: P0_PARTIAL_DO_NOT_START_P1.**

---

## 2. Overall Verdict

| Verdict | Meaning | Applicability |
|---------|---------|---------------|
| `P0_ACCEPTED_READY_FOR_P1` | All P0 closed, residual risk negligible, P1 may start | **Not applicable** |
| `P0_ACCEPTED_WITH_RUNTIME_MONITORING` | Core P0 closed, residual risks only observable in runtime | **Not applicable** |
| `P0_PARTIAL_DO_NOT_START_P1` | Some P0 incomplete or accepted with material residual risk | **Selected** |
| `P0_NOT_ACCEPTED` | P0s fundamentally failed | Not selected — the work is real and directionally correct |

**Rationale for P0_PARTIAL_DO_NOT_START_P1:**

1. **Governance gaps remain in P0 items.** A P0 that claims "cron cannot perform destructive actions" but still invokes `claude --dangerously-skip-permissions` is not closed. A P0 that claims "human-gated recovery + 2FA + audit" but only implements a Redis re-check is not closed. A P0 that claims "audit of every config change" but only implements server-side bounds is not closed.
2. **The full test suite has not been demonstrated green end-to-end** in a clean environment. Targeted tests pass, but the Master Plan acceptance for P0-12 is the whole suite.
3. **The reproducibility manifest is incomplete** (missing model/code version) and is a prerequisite for trusting any later gate report.
4. **Regime multiplier is read but not yet consumed in sizing**, so the live de-risking effect is unproven.
5. **None of the above are runtime-only uncertainties**; they are missing implementation. They should be closed before P1 work begins.

---

## 3. P0 Acceptance Matrix

| P0 | Commit | Acceptance Criteria | Tests Added | Status | Residual Risk | Verdict |
|----|--------|---------------------|-------------|--------|---------------|---------|
| P0-01 Operational freeze + demote S1 | `cb1d43a` | S1 not live 50%; engine live off; promotions blocked; freeze documented | None (policy/config) | `ACCEPTED_WITH_MINOR_RESIDUAL_RISK` | Engine "live off" relies on P0-03 default paper; no automated test asserts no live path; SoT still file-based | ACCEPTED_WITH_MINOR_RESIDUAL_RISK |
| P0-02 Secret rotation + cron sandbox + JWT fail-fast | `e2dad8f` | No secret in repo; JWT fail-fast; cron cannot perform destructive actions | 3 (`test_p0_02_jwt_and_scan.py`) | `NEEDS_FOLLOWUP` | Cron still uses `--dangerously-skip-permissions`; actual key rotation is a PO action; no test for destructive capability | NEEDS_FOLLOWUP |
| P0-03 Paper/live explicit single source | `6796c55` | Explicit single-source mode with audit; no URL-substring inference | 7 (`test_paper_live_mode.py`) | `ACCEPTED_WITH_MINOR_RESIDUAL_RISK` | Mode changes are not audited; no elevated approval before switching to live | ACCEPTED_WITH_MINOR_RESIDUAL_RISK |
| P0-04 Strategy Status SoT + alloc enforcement | `7e7f0f9` | SoT unique; over-allocation raises; mode respected | 11 (`test_p0_04_alloc_enforcement.py`) | `ACCEPTED_WITH_MINOR_RESIDUAL_RISK` | SoT is file-based YAML, not DB; `promotion_blocked` not enforced at promotion time | ACCEPTED_WITH_MINOR_RESIDUAL_RISK |
| P0-05 Execution Safety Contract | `24b45f0` | Stop-loss/bracket active on every new BUY; pending-order anti duplicate-BUY; market calendar fail-closed | 7 (`test_p0_05_execution_safety.py`) | `ACCEPTED_WITH_MINOR_RESIDUAL_RISK` | No e2e test asserts stop-loss leg on real order; partial-fill/reject handling unchanged; DB-down disables guard; duplicate within same batch not deduped | ACCEPTED_WITH_MINOR_RESIDUAL_RISK |
| P0-06 Kill-switch fail-closed + re-check + human recovery | `5f2d58e` | Re-check before every submit; human-gated recovery; 2FA/cooldown; audit | 6 (`test_p0_06_killswitch.py`) | `NEEDS_FOLLOWUP` | Pre-submission re-check done; recovery is API-key-only, no 2FA/cooldown/human gate, no audit; legacy auto-recovery still present | NEEDS_FOLLOWUP |
| P0-07 Market calendar fail-closed | `3bd7e44` | Clock fetch failure aborts cycle | 2 (`test_p0_07_market_calendar.py`) | `ACCEPTED` | No audit row on abort; Telegram-only alert | ACCEPTED |
| P0-08 Config validation + audit | `d7a6c3f` | Server-side bounds; audit of every config change | 15 (`test_p0_08_config_validation.py`) | `NEEDS_FOLLOWUP` | Bounds implemented and tested; no audit of config changes; no elevated approval for weakening controls; other safety sections not validated | NEEDS_FOLLOWUP |
| P0-09 Regime multiplier applied | `52556d1` | Regime multiplier read from detector or explicitly declared off; not hardcoded 1.0 | 6 (`test_p0_09_regime_multiplier.py`) | `ACCEPTED_WITH_MINOR_RESIDUAL_RISK` | Multiplier is written to analytics but not consumed in position sizing; no explicit "regime off" UI path | ACCEPTED_WITH_MINOR_RESIDUAL_RISK |
| P0-10 Reproducibility manifest + deterministic re-run | `bc84a13` | Re-run identical across machines; manifest captures run_id, data_hash, model version, seed | 5 (`test_p0_10_reproducibility.py`) | `ACCEPTED_WITH_MINOR_RESIDUAL_RISK` | Model version / code version / config hash not captured; orchestrator does not consume the manifest; no cross-machine validation | ACCEPTED_WITH_MINOR_RESIDUAL_RISK |
| P0-11 No-lookahead / t+1 decision | `b12c54d` | DataReplay anti-lookahead locked in tests; no-lookahead test green | 4 (`test_p0_11_no_lookahead.py`) | `ACCEPTED_WITH_MINOR_RESIDUAL_RISK` | Same-bar fill (t+0) in orchestrator not fixed; only `prices_until` is locked | ACCEPTED_WITH_MINOR_RESIDUAL_RISK |
| P0-12 Test suite baseline green + audit_log | `bc84a13`, `c272d0c` | Suite green and deterministic; audit_log written | 8 (`test_suite_baseline.py`, `test_audit_log_writer.py`) | `ACCEPTED_WITH_MINOR_RESIDUAL_RISK` | Full suite hung at ~70 % in this environment; audit write is after trade commit and lacks `record_id`; allocation/mode changes not audited | ACCEPTED_WITH_MINOR_RESIDUAL_RISK |
| P0-13 S4 promotion block + S7 R&D containment | `6d86d3f` | S4 promotion blocked; S7 not in operational registry/UI; no live order from S7 | 6 (`test_p0_13_strategy_containment.py`) | `ACCEPTED` | Enforcement only via `_validate_allocations`; no operational-readiness predicate in `register()` or execution engine | ACCEPTED |

**Test execution summary:**

```
pytest tests/test_p0_02_jwt_and_scan.py tests/test_paper_live_mode.py
     tests/test_p0_04_alloc_enforcement.py tests/test_p0_05_execution_safety.py
     tests/test_p0_06_killswitch.py tests/test_p0_07_market_calendar.py
     tests/test_p0_08_config_validation.py tests/test_p0_09_regime_multiplier.py
     tests/test_p0_10_reproducibility.py tests/test_p0_11_no_lookahead.py
     tests/test_p0_13_strategy_containment.py tests/test_suite_baseline.py
     tests/test_audit_log_writer.py --tb=short -q

80 passed, 1 warning in 1.22s
```

The targeted P0 tests pass. This does **not** prove the full suite is green or that all acceptance criteria are satisfied.

---

## 4. Commit-by-Commit Review

### P0-01 — `cb1d43a` — policy freeze + S1 demotion

- **Files changed:** `config/strategies.yaml`
- **What it does:** changes S1 `mode` from `live` to `supervised_paper`, adds `promotion_blocked: true`, and adds a note explaining the demotion and re-promotion conditions.
- **Acceptance evidence:**
  - `config/strategies.yaml:17-18` S1 is `mode: supervised_paper`, `promotion_blocked: true`.
  - No strategy in `config/strategies.yaml` has `mode: live`.
- **Gaps:** no automated test; actual order-submission safety depends on P0-03 (`ALPACA_PAPER_MODE` default `true`) and execution-engine checks. The freeze is a policy statement in a YAML file, not an enforced runtime gate.
- **Verdict:** `ACCEPTED_WITH_MINOR_RESIDUAL_RISK`.

### P0-02 — `e2dad8f` — JWT fail-fast + strip hardcoded API key

- **Files changed:** `src/api/main.py`, `scripts/daily_analysis.sh`, `tests/conftest.py`, `tests/test_p0_02_jwt_and_scan.py`
- **What it does:**
  - `src/api/main.py:16-22` refuses to start if `JWT_SECRET_KEY` is empty.
  - `scripts/daily_analysis.sh` no longer embeds a literal API key; it reads from `ALEMBIC_API_KEY` env or `ADMIN_API_KEY` in `.env` and substitutes a placeholder.
- **Acceptance evidence:**
  - Static scan of `scripts/` finds no API-key literals.
  - `tests/test_p0_02_jwt_and_scan.py` covers JWT fail-fast and secret scan.
- **Gaps:**
  - `scripts/daily_analysis.sh:109` still invokes `claude --dangerously-skip-permissions`, giving the LLM agent full permissions. This directly contradicts the acceptance criterion "cron cannot perform destructive actions".
  - Actual revocation of the previously exposed key requires Project Owner action.
  - No CI check bans full-permission flags in cron scripts.
- **Verdict:** `NEEDS_FOLLOWUP`.

### P0-03 — `6796c55` — paper/live explicit single source

- **Files changed:** `src/config.py`, `src/workers/execution.py`, `src/workers/performance.py`, `src/workers/portfolio_scheduler.py`, `tests/test_paper_live_mode.py`
- **What it does:** adds `ALPACA_PAPER_MODE: bool` defaulting to `true` and replaces all URL-substring checks with direct reads of this field.
- **Acceptance evidence:**
  - `src/workers/execution.py:840`, `src/workers/portfolio_scheduler.py:273,295,636`, `src/workers/performance.py:726` all use `config.ALPACA_PAPER_MODE`.
  - `rg '"paper-api" in' src/` returns no matches.
  - `tests/test_paper_live_mode.py` has 7 tests covering default, env override, and independence from URL.
- **Gaps:** no audit of mode changes; no elevated approval before switching to live.
- **Verdict:** `ACCEPTED_WITH_MINOR_RESIDUAL_RISK`.

### P0-04 — `7e7f0f9` — Strategy Status SoT + allocation enforcement

- **Files changed:** `src/strategies/registry.py`, `tests/test_p0_04_alloc_enforcement.py`
- **What it does:** `StrategyEntry` gains `mode` and `promotion_blocked`; `_validate_allocations` now raises `ValueError` on total allocation >1.0, S4 >10 %, S2 enabled, or S4 mode `live`.
- **Acceptance evidence:**
  - `src/strategies/registry.py:54` `promotion_blocked: bool = False`.
  - `src/strategies/registry.py:175-201` `_validate_allocations` raises on violations.
  - `config/strategies.yaml` S4 `promotion_blocked: true`; S7 `enabled: false`, `mode: research`.
  - 11 tests cover over-allocation, S4 cap, S2 enabled, S4 live, and mode fields.
- **Gaps:** SoT is still file-based YAML, not the DB-backed `strategy_lifecycle` table described in WS-02. `promotion_blocked` is enforced only by the validator, not by `register()` or the execution engine.
- **Verdict:** `ACCEPTED_WITH_MINOR_RESIDUAL_RISK`.

### P0-05 — `24b45f0` — Execution Safety Contract

- **Files changed:** `src/config.py`, `src/workers/portfolio_scheduler.py`, `tests/test_p0_05_execution_safety.py`
- **What it does:**
  - `ALPACA_BRACKET_ENABLED` defaults to `true` (`src/config.py:125-127`).
  - `_submit_portfolio_orders` receives `open_trade_symbols` and skips BUY for symbols already open in the DB (`src/workers/portfolio_scheduler.py:940-947`).
  - Bracket order with `StopLossRequest` attached when price known (`src/workers/portfolio_scheduler.py:988-994`).
  - DB-unreachable graceful degradation logs a warning and disables the guard for the cycle.
- **Acceptance evidence:**
  - 7 tests cover duplicate-BUY guard and bracket default.
- **Gaps:**
  - No e2e test asserts that an actual `MarketOrderRequest` carries a `StopLossRequest` leg.
  - Partial-fill / Alpaca-order-reject handling is unchanged.
  - The guard only filters against prior DB state, not pending Alpaca orders or duplicate symbols within the same `final_orders` batch.
  - Market-calendar fail-closed is implemented by P0-07, not this commit, but required by the P0-05 inventory.
- **Verdict:** `ACCEPTED_WITH_MINOR_RESIDUAL_RISK`.

### P0-06 — `5f2d58e` — Kill-switch fail-closed + re-check

- **Files changed:** `src/workers/portfolio_scheduler.py`, `tests/test_p0_06_killswitch.py`
- **What it does:**
  - Adds `_is_ks_active_failclosed()` which returns `True` when `killswitch_active` or `system:halted_by_operator` is set, and also when Redis is unreachable.
  - Re-checks the kill-switch immediately before order submission and calls `_emergency_cancel_all` if active.
- **Acceptance evidence:**
  - `src/workers/portfolio_scheduler.py:98-113` fail-closed helper.
  - `src/workers/portfolio_scheduler.py:629-633` pre-submission re-check.
  - 6 tests cover active keys, Redis-down fail-closed, and prevention of submission.
- **Gaps:**
  - `src/api/routes/admin.py:131-140` `DELETE /api/admin/killswitch` requires only an API key and clears halts immediately. No 2FA, no cooldown, no human-gated workflow, no audit row.
  - No audit logging for kill-switch activation, deactivation, or abort.
  - Legacy `execution.py` still contains `_try_killswitch_recovery` auto-recovery logic for drawdown halts.
- **Verdict:** `NEEDS_FOLLOWUP`.

### P0-07 — `3bd7e44` — Market calendar fail-closed

- **Files changed:** `src/workers/portfolio_scheduler.py`, `tests/test_p0_07_market_calendar.py`
- **What it does:** replaces the previous `get_clock()` exception handler that logged "proceeding anyway" with an abort path that returns `{"error": "clock_unavailable"}` and sends a Telegram warning.
- **Acceptance evidence:**
  - `src/workers/portfolio_scheduler.py:298-313` returns error on exception and does not fall through to submission.
  - 2 tests assert abort on clock failure and on market closed.
- **Gaps:** no audit row on abort; Telegram-only alert.
- **Verdict:** `ACCEPTED`.

### P0-08 — `d7a6c3f` — Config validation + audit

- **Files changed:** `src/api/routes/config_routes.py`, `tests/test_p0_08_config_validation.py`
- **What it does:** adds `_RISK_BOUNDS` and `_validate_risk_params()`; rejects out-of-bound risk values with HTTP 422 before any merge/write.
- **Acceptance evidence:**
  - `src/api/routes/config_routes.py:16-43` bounds and validator.
  - `src/api/routes/config_routes.py:71` validator called before `_deep_merge`.
  - 15 tests cover rejection and acceptance of boundary values.
- **Gaps:**
  - No audit logging of config changes.
  - No elevated approval for weakening risk controls within bounds.
  - Other safety-relevant sections (`killswitch_recovery`, `loss_feedback`, `schedule`) are not validated.
  - File is overwritten directly, so concurrent edits can race.
- **Verdict:** `NEEDS_FOLLOWUP`.

### P0-09 — `52556d1` — Regime multiplier applied

- **Files changed:** `src/workers/portfolio_scheduler.py`, `tests/test_p0_09_regime_multiplier.py`
- **What it does:** adds `_get_regime_multiplier_from_redis()` which reads `regime:current` from Redis; falls back to `0.2` (high-vol / conservative) if missing, corrupt, or unreachable; writes the multiplier into `execution_decisions` and `trades`.
- **Acceptance evidence:**
  - `src/workers/portfolio_scheduler.py:116-139` Redis reader with conservative fallback.
  - `src/workers/portfolio_scheduler.py:598,710` regime_mult written to decisions/trades.
  - `rg 'regime_mult=1\.0'` returns no matches.
  - 6 tests cover Redis reads and fallback behavior.
- **Gaps:**
  - The multiplier is **not consumed in position sizing** (acknowledged in commit message).
  - No explicit "regime off" configuration path.
- **Verdict:** `ACCEPTED_WITH_MINOR_RESIDUAL_RISK`.

### P0-10 — `bc84a13` — Reproducibility manifest + deterministic re-run

- **Files changed:** `src/backtest/engine/orchestrator.py`, `tests/test_p0_10_reproducibility.py`, plus P0-12 test fixes
- **What it does:** adds `BacktestManifest` dataclass with `run_id`, `data_hash`, `seed`, `created_at`; locks in deterministic re-run via tests.
- **Acceptance evidence:**
  - `src/backtest/engine/orchestrator.py:25-42` manifest definition.
  - `tests/test_p0_10_reproducibility.py` 5 tests pass: identical re-runs, data-hash stability, field presence.
- **Gaps:**
  - **Model version / code version / config hash are not captured**, though the acceptance criteria explicitly list "model version".
  - `BacktestOrchestrator.run()` does not accept a seed or consume the manifest.
  - No cross-machine / CI validation of determinism.
- **Verdict:** `ACCEPTED_WITH_MINOR_RESIDUAL_RISK`.

### P0-11 — `b12c54d` — No-lookahead / t+1 decision

- **Files changed:** `tests/test_p0_11_no_lookahead.py`
- **What it does:** no source-code behavioral change; locks in the existing `DataReplay.prices_until(as_of)` anti-lookahead behavior with 4 new tests, including `test_injected_future_signal_fails`.
- **Acceptance evidence:**
  - `src/backtest/engine/data_replay.py:88-90` `prices_until` filters `index <= as_of`.
  - `tests/test_p0_11_no_lookahead.py` 4 tests pass.
- **Gaps:**
  - The orchestrator still fills orders at the same bar (`market_at(ts)`), i.e. same-bar fill (t+0) is not fixed. The commit message explicitly scopes this out as P1 work.
- **Verdict:** `ACCEPTED_WITH_MINOR_RESIDUAL_RISK`.

### P0-12 — `bc84a13` / `c272d0c` — Test suite baseline green + audit_log

- **Files changed:**
  - `c272d0c`: `pyproject.toml`, `src/brokers/ibkr_adapter.py`, `src/store/pg_store.py`, tests.
  - `bc84a13`: additional stale-mock fixes in `tests/store/test_pg_news_llm.py`, `tests/test_pg_store.py`, `tests/workers/test_performance_worker.py`.
- **What it does:**
  - Makes `ib_insync` optional.
  - Adds `pytest-asyncio` to dev dependencies.
  - Adds `PostgreSQLStore.write_audit_log()` and calls it from `open_trade()`.
  - Fixes stale mocks so targeted tests pass.
- **Acceptance evidence:**
  - `src/store/pg_store.py:1645-1682` audit-log writer.
  - `src/store/pg_store.py:480-489` `open_trade()` calls `write_audit_log()`.
  - `tests/test_suite_baseline.py` 3 tests pass.
  - `tests/test_audit_log_writer.py` 5 tests pass.
- **Gaps:**
  - `open_trade()` commits the trade **before** writing the audit row; if audit fails, the trade exists unaudited.
  - `open_trade()` does not pass `record_id` to `write_audit_log()`, so the audit row cannot be joined back to the trade.
  - The **full suite could not be completed** in this environment (agent run hung at ~70 %). Targeted tests pass, but the Master Plan acceptance criterion is the full suite.
  - Allocation changes and strategy mode changes are not audited.
- **Verdict:** `ACCEPTED_WITH_MINOR_RESIDUAL_RISK`.

### P0-13 — `6d86d3f` — S4 promotion block + S7 R&D containment

- **Files changed:** `config/strategies.yaml`, `src/strategies/registry.py`, `tests/test_p0_13_strategy_containment.py`
- **What it does:** adds `promotion_blocked` to `StrategyEntry`, sets S4 `promotion_blocked: true`, adds S7 as `enabled: false`, `mode: research`, `promotion_blocked: true`, and raises if S4 mode is `live`.
- **Acceptance evidence:**
  - `config/strategies.yaml:42` S4 `promotion_blocked: true`, `mode: paper`.
  - `config/strategies.yaml:51-52` S7 `enabled: false`, `mode: research`, `promotion_blocked: true`.
  - `src/strategies/registry.py:197-201` raises on S4 `mode == "live"`.
  - `src/strategies/registry.py:90-92` `get_active_strategies()` filters by `enabled`.
  - 6 tests cover S4 block and S7 containment.
- **Gaps:** enforcement is via `_validate_allocations`; direct registration or `load_defaults=False` could bypass it; there is no explicit operational-readiness predicate.
- **Verdict:** `ACCEPTED`.

---

## 5. Test Coverage Review

| P0 | Test file | Count | Covers failure mode? | Missing coverage | Type | Should be CI gate? |
|----|-----------|-------|------------------------|------------------|------|--------------------|
| P0-02 | `test_p0_02_jwt_and_scan.py` | 3 | Secret scan + JWT fail-fast | Cron destructive capability, actual key rotation | unit + static scan | yes |
| P0-03 | `test_paper_live_mode.py` | 7 | Default paper, env override, URL independence | Mode-change audit, elevated live approval | unit | yes |
| P0-04 | `test_p0_04_alloc_enforcement.py` | 11 | Over-alloc, S4 cap, S2 enabled, S4 live | DB-backed SoT, promotion-block enforcement | unit | yes |
| P0-05 | `test_p0_05_execution_safety.py` | 7 | Duplicate BUY, bracket default | Stop-loss leg on real order, partial fill, reject, Alpaca pending | unit + integration | yes |
| P0-06 | `test_p0_06_killswitch.py` | 6 | Active key, Redis-down, pre-submission abort | Human recovery, 2FA, cooldown, audit, legacy auto-recovery | unit | yes |
| P0-07 | `test_p0_07_market_calendar.py` | 2 | Clock failure, market closed | Audit row, multi-channel alert | unit | yes |
| P0-08 | `test_p0_08_config_validation.py` | 15 | Out-of-bound risk values | Audit, elevated approval, other sections | unit | yes |
| P0-09 | `test_p0_09_regime_multiplier.py` | 6 | Redis read, fallback | Multiplier consumed in sizing, explicit off path | unit | yes |
| P0-10 | `test_p0_10_reproducibility.py` | 5 | Determinism, manifest fields | Model/code/config version, cross-machine | unit | yes |
| P0-11 | `test_p0_11_no_lookahead.py` | 4 | Future prices excluded | Same-bar fill, `market_at` future | unit | yes |
| P0-12 | `test_suite_baseline.py`, `test_audit_log_writer.py` | 8 | Import/collection, audit writer | Full suite green, transactional audit, allocation/mode audit | unit | yes |
| P0-13 | `test_p0_13_strategy_containment.py` | 6 | S4 live raise, S7 not active | Direct-registration bypass, operational-readiness predicate | unit | yes |

**Total targeted P0 tests passing:** 80.

**Tests that should become regression gates in CI:**
- `test_p0_02_jwt_and_scan.py::test_no_hardcoded_api_key_in_scripts`
- `test_paper_live_mode.py::test_paper_mode_defaults_to_true`
- `test_p0_04_alloc_enforcement.py::test_over_allocation_raises`
- `test_p0_05_execution_safety.py::test_duplicate_buy_skipped_when_already_open`
- `test_p0_06_killswitch.py::test_kill_switch_prevents_submission_when_active_presubmit`
- `test_p0_07_market_calendar.py::test_clock_failure_aborts_cycle`
- `test_p0_08_config_validation.py::test_config_rejects_out_of_bound_stop_loss`
- `test_p0_09_regime_multiplier.py::test_regime_multiplier_fallback_when_key_missing`
- `test_p0_10_reproducibility.py::test_backtest_rerun_deterministic`
- `test_p0_11_no_lookahead.py::test_injected_future_signal_fails`
- `test_suite_baseline.py::test_pytest_asyncio_installed`
- `test_p0_13_strategy_containment.py::test_s4_live_mode_raises`

---

## 6. Residual Risks

1. **Destructive cron capability (P0-02).** The daily-analysis script still launches Claude with `--dangerously-skip-permissions`. A compromised `.env` or injected prompt could cause repository/data/broker changes.
2. **Kill-switch recovery weakness (P0-06).** A single API key can resume trading after a halt. No 2FA, cooldown, human approval, or audit.
3. **Config audit absence (P0-08).** Every risk-control change is server-bounded but not logged. An operator can move stop-loss from 2 % to 10 % within bounds without trace.
4. **Reproducibility manifest incomplete (P0-10).** Model/code/config versions are not pinned. Gate reports produced now cannot be defensibly reproduced.
5. **Audit-log transactionality (P0-12).** Audit row is written after the trade commit and without `record_id`; a failing audit insert leaves an unaudited trade.
6. **Regime multiplier not consumed (P0-09).** The multiplier is recorded but does not reduce position size; high-vol regime de-risking is not yet effective.
7. **Same-bar fill remains (P0-11).** The orchestrator still fills at `close[t]`. Backtest numbers remain optimistic until t+1 fill is implemented.
8. **File-based strategy SoT (P0-04).** All enforcement depends on `config/strategies.yaml` and `_validate_allocations`. A manual edit can change status unless branch protection enforces PR + review.
9. **Legacy execution path (P0-05/P0-06).** `src/workers/execution.py` is still present with different safety semantics and auto-recovery logic. If ever re-activated, it could bypass P0-05/P0-06 protections.
10. **Full suite not demonstrated green.** Targeted P0 tests pass, but the full suite could not be completed in a clean environment.

---

## 7. Runtime Validation Required

The following cannot be fully validated by static code review or targeted unit tests alone:

| Item | Runtime data needed | Dry-run / paper-run | Logs/metrics to check | Minimum observation | Success criterion |
|------|---------------------|---------------------|-----------------------|---------------------|-----------------|
| Full test suite green | Clean CI environment with Postgres/Redis/network mocks | N/A | CI logs | 1 clean run | 100 % pass rate (or declared skips) with deterministic re-run |
| Kill-switch drill mid-cycle | Redis key `killswitch_active` set during a cycle | Dry-run with broker mock | Worker logs, Telegram, audit_log | 1 drill | No order submitted after key set; `emergency_cancel_all` invoked; audit row written |
| Kill-switch recovery workflow | API key + recovery mechanism | Dry-run | audit_log, Telegram/TOTP | 1 drill | Recovery requires 2FA/cooldown/human confirm and writes audit row |
| Paper/live divergence | ≥90 days paper trading | Paper | fill-price vs backtest fill, slippage, cost diff | 90 calendar days | Divergence metric stable within declared tolerance |
| Regime multiplier effect on sizing | Redis `regime:current` with multiplier <1.0 | Paper or dry-run | execution_decisions/trades `regime_mult`, order notional vs baseline | 1 cycle | Order notional scaled by multiplier in high-vol regime |
| Config change audit | N/A | N/A | `audit_log` table after POST /api/config | 1 change | Row with user/key hash, timestamp, old/new values |
| Market-clock fail-closed | Simulated `get_clock()` exception | Dry-run | Worker returns `clock_unavailable`, no orders, Telegram warning | 1 drill | Cycle aborts without orders |
| LOO ICIR contamination | S4 ensemble weight history + forward returns | Backtest | `src/performance/ic.py` output | Analysis | No overlapping/future data in ICIR calculation |

---

## 8. Follow-up Fixes Before P1

Before starting any P1 work, the following P0 gaps must be closed:

1. **P0-02 — Remove or sandbox destructive cron capability**
   - Eliminate `--dangerously-skip-permissions` from `scripts/daily_analysis.sh` or run the cron under a read-only/sandboxed Claude profile.
   - Add a CI check that fails if any script invokes Claude with full-permission flags.
   - Complete actual secret rotation for the previously exposed key.

2. **P0-06 — Human-gated kill-switch recovery + audit**
   - Replace API-key-only `DELETE /api/admin/killswitch` with Telegram confirm, TOTP, or admin-UI 2FA plus a configurable cooldown.
   - Add `write_audit_log()` calls for kill-switch activation, deactivation, and every pre-submission abort.
   - Remove or disable the legacy auto-recovery path in `src/workers/execution.py`.

3. **P0-08 — Config change audit + elevated approval**
   - Add an audit row on every `POST /api/config` capturing actor, timestamp, old value, new value.
   - Require elevated approval for changes that weaken risk controls (e.g. stop-loss widening, drawdown cap increase).
   - Validate additional safety-relevant sections (`killswitch_recovery`, `loss_feedback`, etc.).

4. **P0-10 — Complete the reproducibility manifest**
   - Add `model_version`, `code_version` (git commit hash), and `config_hash` to `BacktestManifest`.
   - Wire `seed` into `BacktestOrchestrator.run()` and pass the manifest object so the engine is deterministic under stochastic strategies.
   - Add a CI job that re-runs a reference backtest and compares metrics within declared tolerance.

5. **P0-12 — Transactional audit + full suite green**
   - Move `write_audit_log()` inside the same transaction as `open_trade()` and pass the returned `record_id`.
   - Add audit-log writers for allocation changes and strategy mode changes.
   - Demonstrate a full green suite run in CI with all services available or mocked.

6. **P0-09 — Consume regime multiplier in sizing**
   - Apply the regime multiplier to target notional / order quantity in the portfolio orchestrator.
   - Add an explicit "regime off" configuration path and surface it in the UI.

7. **P0-05 — Harden execution safety**
   - Add a real-path test that asserts every `MarketOrderRequest` has a `StopLossRequest` leg.
   - Implement and test partial-fill / reject handling before the next cycle.
   - Add a redundant Alpaca `get_orders(status=OPEN)` pending-order check.

8. **P0-04 / P0-13 — Operational-readiness predicate**
   - Enforce `promotion_blocked` and `mode=research` inside `StrategyRegistry.register()`.
   - Add an `is_operational()` predicate used by the execution engine and UI to prevent R&D strategies from producing orders.

9. **P0-11 — t+1 fill queue**
   - Implement t+1 / next-open fill in `BacktestOrchestrator` and add a test that fails on same-bar fill.

---

## 9. P1 Readiness Recommendation

**Do not start P1 until:**

1. P0-02, P0-06, and P0-08 are moved from `NEEDS_FOLLOWUP` to `ACCEPTED`.
2. P0-10 captures model/code/config version.
3. P0-12 demonstrates a full green suite run in CI.
4. P0-09 consumes the regime multiplier in sizing.
5. P0-05 has a real-path stop-loss-leg test and partial-fill handling.

**After the above, the verdict can be reconsidered as `P0_ACCEPTED_WITH_RUNTIME_MONITORING`** because:

- Core execution safety (stop-loss, duplicate BUY, kill-switch re-check, calendar fail-closed, paper/live mode) is in place.
- Strategy containment and allocation enforcement are active.
- The remaining uncertainties (paper-live divergence, 90-day paper behavior, FinBERT fallback rate, LOO ICIR) are runtime-observable and belong in P1/P2 monitoring.

**P1 should then be sequenced as:**
1. Validation truth (t+1 fill, cost model, gate fixes, reproducibility parity).
2. Governance/cockpit layer (operator cockpit, monitoring/alerting, promotion gate).
3. Strategy requalification experiments on honest backtests.

---

## 10. Stop Point

Non ho modificato file di codice, non ho scritto codice eseguibile, non ho creato patch, non ho eseguito commit, non ho avviato worker o pipeline, non ho inviato ordini. L'unico file creato è questo report di audit in `docs/P0_ACCEPTANCE_AUDIT_2026-06-18.md`.

**Raccomandazione:** procedere ai P1 solo se il verdict diventa `P0_ACCEPTED_READY_FOR_P1` o `P0_ACCEPTED_WITH_RUNTIME_MONITORING`. Allo stato attuale il verdict è `P0_PARTIAL_DO_NOT_START_P1`.
