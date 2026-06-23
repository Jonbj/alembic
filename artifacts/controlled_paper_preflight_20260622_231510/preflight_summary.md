# Controlled Paper Preflight Summary — 2026-06-22

**Verdict: PREFLIGHT_PASS_WITH_WARNINGS_READY_FOR_PO_REVIEW**

Executed: 2026-06-22T21:15–21:24 UTC  
Commit: 9e1039e (HEAD, main)  
Environment: Alpaca paper only

## Phase Results

| Phase | Result | Notes |
|-------|--------|-------|
| 1 Static Verification | ✅ PASS (with note) | Working tree has 19 modified files (F0-1/F0-3 + fixes) |
| 2 Environment Safety | ✅ PASS | Paper endpoint, PK key, mode=paper |
| 3 Readiness Before | ✅ PASS (with note) | worker_beat_lag=true (outside market hours — acceptable) |
| 4 Strategy Governance | ✅ PASS (with warnings) | S2 approved=true data inconsistency; S4 not in API |
| 5 Frontend Safety Hygiene | ✅ PASS | 10/10 tests, typecheck clean |
| 6 Evidence Directory | ✅ CREATED | 18 artifact files |
| 7 Pre-Run Snapshot | ✅ CAPTURED | baseline: 89 cycles, 356 decisions, 16 open trades |
| 8 Dry-Run Cycle | ⚠️ SKIPPED (safety gate) | approved=False → no_approved_strategies; correct behavior |
| 9 Decisions Verification | ✅ PASS | 30 decisions, all explained, no live refs |
| 10 Order Lifecycle | ✅ PASS (0 orders in preflight) | Historical cycles confirm order path works |
| 11 Kill-Switch Rehearsal | ✅ PASS | Full activate/halt/OTP-reset cycle |
| 12 Final Readiness | ✅ PASS | All blocking flags green |

## Critical Finding

**The `approved` gate is working correctly.** Both S1 and S4 have `approved=False` in `strategy_lifecycle`. The scheduler correctly skips all strategies, producing no portfolio_cycles row and no orders. This is the designed fail-closed behavior.

**PO action required:** `UPDATE strategy_lifecycle SET approved=true WHERE strategy_id IN ('S1','S4');`

## Warnings (not stop conditions)

1. **R-13 Pyramiding**: 16 open paper positions (multiple per symbol). Must be acknowledged.
2. **Working tree not clean**: F0-1/F0-3 safety hygiene uncommitted (all safety improvements).
3. **worker_beat_lag**: Outside market hours — expected and acceptable.
4. **S2 data inconsistency**: approved=true, mode=disabled. Low risk, recommend cleanup.
5. **S4 not in strategies API**: Present in lifecycle+YAML but not exposed in STRATEGIES dict.

## What Was NOT Done

- No live trading
- No strategy promotions
- No P3/P4 work
- No live credentials used
- No live orders placed
- No lifecycle state modified
- No safety gate bypassed
- Controlled paper NOT authorized (PO sign-off required)
