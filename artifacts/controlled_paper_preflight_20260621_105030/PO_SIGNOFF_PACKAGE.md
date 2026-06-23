# ALEMBIC — CONTROLLED PAPER PREFLIGHT PO SIGN-OFF PACKAGE

**Date / Time:** 2026-06-21T08:53–09:03 UTC  
**Preflight commit:** `9e1039e` (HEAD)  
**Config hash (trading.yaml):** `2759498a5a73012d3a305fe18cbb629e`  
**Config hash (strategies.yaml):** `11d7e81704bd3f805b0a562d98284ddf`  
**Operator:** Maintainer (automated preflight)  
**Environment:** Local Docker Compose — paper/sandbox only  

---

## Broker Endpoint Confirmation

| Item | Value | Status |
|------|-------|--------|
| `ALPACA_BASE_URL` | `https://paper-api.alpaca.markets` | ✅ PAPER |
| API key prefix | `PK` | ✅ PAPER |
| Live endpoint detected | NO | ✅ SAFE |
| Live credentials loaded | NO | ✅ SAFE |

**Operator statement:** No live credentials or live endpoint detected. No live orders were placed.

---

## Strategies

### In scope (enabled in config)

| Strategy | Mode | Allocation | approved in DB | promotion_blocked |
|----------|------|-----------|----------------|------------------|
| S1 | supervised_paper | 50% | FALSE | true |
| S4 | paper | 10% | FALSE | true |

### Excluded

| Strategy | Mode | Reason |
|----------|------|--------|
| S2 | disabled (DB) / research (config) | Options infra not implemented; all gates failed |
| S3 | research | Gate 3/5 failed; R&D only |
| S7 | research | PEAD R&D; not wired in orchestrator |

---

## Readiness

### Before dry-run

| Flag | Value | Status |
|------|-------|--------|
| redis_healthy | true | ✅ |
| redis_writeable | true | ✅ |
| db_healthy | true | ✅ |
| killswitch_active | false | ✅ |
| stale_signals | true | ⚠️ Acceptable (Sunday, outside market hours) |
| worker_beat_lag | true | ⚠️ Acceptable (Sunday, outside market hours) |

### Final (after kill-switch rehearsal)

| Flag | Value | Status |
|------|-------|--------|
| redis_healthy | true | ✅ |
| redis_writeable | true | ✅ |
| db_healthy | true | ✅ |
| killswitch_active | false | ⚠️ Cockpit gap — true state: HALTED |
| True admin KS state | true (halted) | ❌ Kill-switch not reset — see BLOCKERS |

---

## Dry-Run Cycle Result

- Task: `run_portfolio_cycle` (Celery, normal path, paper mode)
- Task ID: `af48e263-673d-41cb-9f42-ea55459bbab6`
- Result: `{'skipped': True, 'reason': 'no_approved_strategies'}`
- S1 excluded: `approved=False` in strategy_lifecycle (migration 025 seed)
- S4 excluded: `approved=False` in strategy_lifecycle (migration 025 seed)
- Orders placed: **0** (expected — no approved strategies)
- portfolio_cycles rows added: **0** (cycle skipped, no DB row)
- execution_decisions rows added: **0** (cycle skipped)

**Safety assessment:** This is the CORRECT behavior. The P2-02 promotion gate is working as designed.

---

## Decisions Summary

- Total historical decisions: 356
- New decisions from today's cycle: 0 (cycle skipped)
- Unexplained BUYs: 0
- Missing reasons: 0
- S2/S7 acting: 0
- "validated" language in decisions: 0

---

## Order Lifecycle Summary

- Historical paper orders (before preflight): 192 trades in `trades` table
- Orders from today's cycle: 0
- All historical orders: paper account only (`paper-api.alpaca.markets`)
- All orders: attributed to S4 news-driven strategy
- All orders: have `entry_order_id` (Alpaca paper UUIDs)

---

## Kill-Switch Rehearsal

| Step | Result |
|------|--------|
| Baseline: killswitch_active=false | ✅ |
| Activation via POST /api/admin/killswitch | ✅ |
| Confirmation via GET /api/admin/killswitch | ✅ (`active: true`) |
| Confirmation via GET /api/admin/status | ✅ (`killswitch: true`) |
| Cycle halt with KS active | ✅ "Portfolio cycle skipped — kill-switch active: manual operator halt via API" |
| Reset via DELETE /killswitch?confirm_token=... | ❌ **BUG** — bytes vs str comparison fails |

**Bug details:** In `src/api/routes/admin.py` line 192, `stored_token` (bytes from Redis) is compared with `confirm_token` (str from HTTP query param). In Python 3, `b"token" != "token"` is always True → token always rejected. Fix: `stored_token.decode() != confirm_token`.

**Current state:** Kill-switch ACTIVE (`system:halted_by_operator=1`, `system:mode=halted`). Cannot be reset via documented API without the code fix.

---

## Residual Risks (R-04 through R-12)

| ID | Risk | Operator Review |
|----|------|----------------|
| R-04 | CI soft gates | Accepted for paper phase |
| R-05 | LLM divergence alert | Accepted for paper phase |
| R-06 | S3 production readiness | S3 excluded — not applicable |
| R-07 | Controlled paper not started | This preflight is for authorization |
| R-08 | Live trading not authorized | Confirmed NOT authorized |
| R-09 | yfinance reliability | Accepted for paper phase |
| R-10 | Telegram token rotation | Accepted for paper phase |
| R-11 | Redis flush resets kill-switch | Accepted for paper phase (appendonly=yes recommended) |
| R-12 | S7 wiring risk | S7 excluded and not wired — accepted |

---

## Operational Notes

1. **Container rebuild required and executed:** Containers created 2026-06-19T23:38Z pre-dated both `55cbf56` (P2-05 safety fixes) and `9e1039e` (S1 status reconciliation). Rebuilt during preflight (operational deployment, not code change).

2. **Migrations 025/026 applied during preflight:** `strategy_lifecycle` and `strategy_lifecycle_audit` tables were absent. Applied during preflight. Both are idempotent (CREATE TABLE IF NOT EXISTS). Consequence: all strategies have `approved=FALSE` → promotion gate correctly blocks all execution.

3. **Cockpit readiness gap:** `/api/system/readiness` reads only `killswitch_active` Redis key, not `system:halted_by_operator`. Operator must cross-check with `GET /api/admin/status` to see true kill-switch state.

---

## BLOCKERS — Items preventing GO

### BLOCKER 1 — Kill-Switch Reset Bug
**File:** `src/api/routes/admin.py:192`  
**Bug:** `stored_token (bytes) != confirm_token (str)` always True → DELETE /killswitch always rejected  
**Fix:** `stored_token.decode() != confirm_token`  
**Impact:** Operator cannot reset the kill-switch via the documented API after operator-halt activation  
**Current state:** Kill-switch is ACTIVE (system halted) — cannot be reset until bug is fixed  

### BLOCKER 2 — Strategy Approval Gate
**Table:** `strategy_lifecycle`  
**State:** S1 `approved=FALSE`, S4 `approved=FALSE`  
**Impact:** With correct P2-02 code, NO portfolio cycle will place orders. Paper trading would produce only skipped cycles.  
**Action required:** PO must explicitly approve strategies via `approve_promotion()` or `UPDATE strategy_lifecycle SET approved=TRUE WHERE strategy_id IN ('S1','S4')` after verifying this is intentional  
**Note:** This is NOT a code bug — it's the promotion gate working correctly. The seed data reflects "not yet formally approved through gate process."  

### BLOCKER 3 — Cockpit Readiness Does Not Reflect Operator Halt
**File:** `src/monitoring/cockpit.py:94`  
**Gap:** Only reads `killswitch_active` Redis key, ignores `system:halted_by_operator`  
**Fix:** Add `or bool(redis_client.get("system:halted_by_operator"))` to the killswitch_active check  
**Impact:** Operator using `/api/system/readiness` may believe system is running when it is halted  

---

## Frontend / Operator Gaps (Non-Blocking)

- No cockpit UI for readiness flags (operator must use curl)
- No strategy lifecycle mode display in frontend
- S4 not displayed in `GET /api/strategies` list (by design)

---

## AUTHORIZATION DECISIONS

**The following must be completed by the PO before controlled paper trading:**

```
1. Fix kill-switch reset bug (admin.py:192)
2. Fix cockpit readiness gap (cockpit.py:94)  
3. Approve strategies via governance process (approved=TRUE for S1 and/or S4)
4. Re-run preflight dry-run cycle with approved strategies to generate order evidence
5. Complete this sign-off block
```

```
═══════════════════════════════════════════════════════════════
AUTHORIZATION DECISIONS (PO MUST COMPLETE ALL THREE)
───────────────────────────────────────────────────────────────
Controlled paper trading authorized?          [ ] YES   [ ] NO
Live trading authorized?                      [ ] NO    (must be NO)
Strategy promotions authorized?               [ ] NO    (must be NO)

PO Name:     ____________________________
PO Signature: ____________________________
Date signed: ____________________________
═══════════════════════════════════════════════════════════════
```

**Do not pre-check YES.**  
**Controlled paper trading is NOT authorized by this preflight.**  
**Two blockers (KS reset bug + strategy approval) must be resolved first.**
