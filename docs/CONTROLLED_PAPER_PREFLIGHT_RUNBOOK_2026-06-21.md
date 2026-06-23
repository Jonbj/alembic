# CONTROLLED PAPER PREFLIGHT RUNBOOK — 2026-06-21

**Document type:** Operational runbook  
**Version:** 1.0  
**Date:** 2026-06-21  
**Status:** PENDING — dry-run not yet executed, PO sign-off not yet obtained  
**Baseline commit:** `9e1039e` (pre-paper reconciliation complete)  
**Author:** Maintainer team

---

## 1. Purpose

This runbook defines the exact sequence of steps required to prepare Alembic for
controlled paper trading. It exists to ensure that:

- every safety gate is verified before any automated order is placed against a
  paper brokerage account;
- the evidence required for PO sign-off is captured in a reproducible way;
- no operator mistake can confuse paper mode with live mode or skip a safety check.

**This runbook does NOT authorize controlled paper trading.**  
**This runbook does NOT authorize live trading.**  
**This runbook does NOT authorize strategy promotions.**  
**This runbook exists solely to generate the evidence package required for PO sign-off.**

PO sign-off (Section 15) is the only act that authorizes controlled paper trading.
Until that explicit sign-off is received, the system must not submit orders to any
brokerage account, paper or live.

---

## 2. Preconditions

All items below must be confirmed TRUE before beginning any preflight step.
Record the result of each check in the evidence package (Section 13).

```
[ ] P0_ACCEPTED_WITH_RUNTIME_MONITORING
      docs/P0_ACCEPTANCE_AUDIT_2026-06-19.md exists and shows this verdict.

[ ] P1_ACCEPTED_WITH_RUNTIME_MONITORING
      docs/P1_RE_ACCEPTANCE_AUDIT_2026-06-19.md exists and shows this verdict.

[ ] P2_ACCEPTED_WITH_RUNTIME_MONITORING
      docs/P2_ACCEPTANCE_AUDIT_2026-06-21.md exists and shows this verdict.

[ ] Pre-paper reconciliation commit present
      git log --oneline | grep 9e1039e   # must appear
      Commit message: "docs(pre-paper): reconcile stale doc/API surfaces per Kimi P2 Audit findings"

[ ] Full suite green: 2393 passed, 1 skipped, 0 failures
      .venv/bin/python -m pytest -q 2>&1 | tail -3

[ ] GLOBAL_LIVE_PROMOTION_ENABLED is False
      grep GLOBAL_LIVE_PROMOTION_ENABLED src/strategies/promotion.py
      # Must print: GLOBAL_LIVE_PROMOTION_ENABLED: bool = False

[ ] Live credentials NOT loaded
      Verify .env does NOT contain live Alpaca credentials
      (check ALPACA_BASE_URL — must NOT be https://api.alpaca.markets)

[ ] Alpaca paper credentials only
      ALPACA_BASE_URL=https://paper-api.alpaca.markets   (in .env)

[ ] Kill-switch currently false
      Step B confirms: killswitch_active=false via /api/system/readiness

[ ] No strategy promotions pending
      No row in strategy_lifecycle with target_mode='live' or mode='live'

[ ] No P3/P4 work in progress
      git status -- clean or only known changes; no P3/P4 branch active

[ ] Residual risk register reviewed
      docs/RESIDUAL_RISK_REGISTER.md — R-04 through R-12 reviewed;
      risks accepted by operator before proceeding.

[ ] Strategy authorization states understood (see Section 5)

[ ] Operator holds ADMIN_API_KEY for /api/system/* endpoints
```

---

## 3. Explicit Non-Authorizations

The following actions are **explicitly NOT authorized** by this runbook:

| Action | Status |
|--------|--------|
| Live trading (any form) | NOT authorized |
| Controlled paper trading start | NOT authorized until Section 15 PO sign-off |
| Strategy promotion (any strategy to any mode) | NOT authorized |
| Setting `GLOBAL_LIVE_PROMOTION_ENABLED=True` | NOT authorized |
| P3 or P4 work | NOT authorized |
| Changing strategy lifecycle state in DB or config | NOT authorized |
| Placing orders on a live brokerage account | NOT authorized |
| Bypassing any scheduler safety gate | NOT authorized |
| Running automated cycles continuously without dry-run evidence | NOT authorized |

Any action from the list above discovered during preflight execution constitutes a
**stop condition** (Section 17). Stop, investigate, and escalate to the PO before continuing.

---

## 4. Environment Safety Checklist

Execute every check in this section before Step A. Record pass/fail.

### 4.1 — Broker Environment

```bash
# Confirm Alpaca base URL is paper endpoint (not live)
grep ALPACA_BASE_URL .env
# Expected: ALPACA_BASE_URL=https://paper-api.alpaca.markets
# FAIL if: https://api.alpaca.markets (live endpoint)

# Confirm API key prefix (Alpaca paper keys start with PK, live with AK)
grep ALPACA_API_KEY .env | cut -d= -f2 | cut -c1-2
# Expected: PK  (paper key prefix)
# FAIL if: AK (live key prefix)
```

### 4.2 — Promotion Kill-Switch

```bash
grep GLOBAL_LIVE_PROMOTION_ENABLED src/strategies/promotion.py
# Expected: GLOBAL_LIVE_PROMOTION_ENABLED: bool = False
# FAIL if True or if line is missing
```

### 4.3 — Strategy Lifecycle States

```bash
# Query the strategy_lifecycle table directly
docker compose exec postgres psql -U trading -d trading \
  -c "SELECT strategy_id, mode, promotion_blocked, approved, updated_at
      FROM strategy_lifecycle
      ORDER BY strategy_id;"
```

Expected states (source of truth: `config/strategies.yaml` + migration 025):

| strategy_id | mode | promotion_blocked | approved |
|-------------|------|-------------------|----------|
| S1 | supervised_paper | true | false (not approved for promotion) |
| S2 | disabled | — | — (must not appear active) |
| S4 | paper | true | false |
| S7 | not present or research | — | — (contained, not in orchestrator) |

**FAIL** if any strategy shows `mode='live'` or `target_mode='live'`.

### 4.4 — Infrastructure Health

```bash
# Redis reachable
docker compose exec redis redis-cli ping
# Expected: PONG

# PostgreSQL reachable
docker compose exec postgres pg_isready -U trading
# Expected: /var/run/postgresql:5432 - accepting connections

# API reachable
curl -s http://localhost:8001/api/health
# Expected: {"status":"healthy","redis":"connected","postgres":"connected"}
```

### 4.5 — Kill-Switch State

```bash
docker compose exec redis redis-cli GET killswitch_active
# Expected: (nil) or "0" — must NOT be "1"
```

### 4.6 — Migrations Applied

```bash
docker compose exec postgres psql -U trading -d trading \
  -c "\dt" | grep -E "strategy_lifecycle|portfolio_cycles|execution_decisions"
# Expected: all three tables present
# (confirms migrations 013/024/025 applied)
```

### 4.7 — Config File Loaded

```bash
# Confirm trading.yaml is present and readable
cat config/trading.yaml | grep "max_portfolio_exposure"
# Expected: max_portfolio_exposure: 0.50

# Confirm strategies.yaml is present
cat config/strategies.yaml | grep "S1" | head -3
# Expected: S1: block with mode: supervised_paper
```

### 4.8 — No Open Live Orders

```bash
# Check Alpaca paper account for any unexpected open orders
# (This must be done via Alpaca paper dashboard or SDK — NOT the live endpoint)
# Confirm ALPACA_BASE_URL=https://paper-api.alpaca.markets before running.
# Expected: no unexpected open orders from previous sessions.
```

### 4.9 — System Mode

```bash
docker compose exec redis redis-cli GET system:mode
# Expected: "paper" or nil (not "live" or "full_auto" with live credentials)

# Set paper mode explicitly if not already set:
curl -X POST http://localhost:8001/api/admin/mode \
  -H "X-API-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"mode": "paper"}'
```

---

## 5. Strategy Scope for Preflight

The following table defines which strategies are in scope for the dry-run cycle:

| Strategy | Mode | Included in dry-run | Reason |
|----------|------|---------------------|--------|
| **S1** | `supervised_paper` | ✅ Yes — as observation target only | Backtest candidate; paper observation; 50% allocation; promotion_blocked=true |
| **S4** | `paper` | ✅ Yes — with idempotency and freshness gates active | News overlay; 10% allocation; promotion_blocked=true; IC>placebo not confirmed |
| **S2** | `disabled` | ❌ No | Options infra not implemented; all gates failed; 0% allocation |
| **S3** | `research` | ❌ No | Not production-ready; diagnostic use only if explicitly approved by PO |
| **S7** | `research` | ❌ No | R&D only; NOT wired in orchestrator; PEAD alpha not evaluated |

**Constraints enforced during preflight:**
- `promotion_blocked=true` for all S1 and S4 — no promotion possible
- `ConstraintEnforcer` reads `max_portfolio_exposure=0.50` and `max_position_pct=0.10` from `config/trading.yaml`
- `PortfolioVolTargeter` runs before `ConstraintEnforcer` (P2-05-C — cannot re-violate cap)
- S4 idempotency: `_get_fired_signal_ids()` fail-closed (returns `None` on Redis error → skip all S4 BUYs)

If `config/strategies.yaml` shows any deviation from the above (e.g., S2 enabled, S7 allocation > 0),
this is a **BLOCKER** — stop and raise to PO before continuing.

---

## 6. Preflight Step A — Static Verification

Record all results. No service must be started for this step.

```bash
# A1 — Git state
git status
# Expected: clean working tree (or only known untracked docs)

git log --oneline -1
# Expected: 9e1039e docs(pre-paper): reconcile stale doc/API surfaces...
# Record: COMMIT_HASH=$(git rev-parse HEAD)

# A2 — Test suite result (run if not already green in this session)
.venv/bin/python -m pytest -q 2>&1 | tail -5
# Expected: 2393 passed, 1 skipped, 0 failures
# Record result verbatim.

# A3 — Audit documents present
ls -la docs/P2_ACCEPTANCE_AUDIT_2026-06-21.md \
        docs/P2_STATUS_2026-06-21.md \
        docs/RESIDUAL_RISK_REGISTER.md
# Expected: all three files exist

# A4 — Strategy API does not report S1 as validated
curl -s -H "X-API-Key: $ADMIN_API_KEY" http://localhost:8001/api/strategies/s1 \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('status:', d.get('status')); print('promotion_blocked:', d.get('promotion_blocked')); print('live_authorized:', d.get('live_authorized'))"
# Expected:
#   status: supervised_paper
#   promotion_blocked: True
#   live_authorized: False
# FAIL if status == "validated" or live_authorized == True

# A5 — README does not claim paper/live authorized
grep -n "authorized" README.md | grep -v "NOT authorized\|not authorized"
# Expected: zero output (only NOT authorized references)
```

**Pass criteria for Step A:** all 5 sub-checks produce expected output.
Record pass/fail for each. Do not proceed to Step B if any fail.

---

## 7. Preflight Step B — Readiness Endpoint Check

```bash
# B1 — Call readiness endpoint
curl -s -H "X-API-Key: $ADMIN_API_KEY" http://localhost:8001/api/system/readiness | python3 -m json.tool
```

**Expected response:**
```json
{
  "redis_healthy": true,
  "redis_writeable": true,
  "db_healthy": true,
  "killswitch_active": false,
  "stale_signals": false,
  "worker_beat_lag": false,
  "last_signal_age_minutes": <any positive number>,
  "last_cycle_age_minutes": <any positive number or null if no cycle yet>
}
```

> **Important:** HTTP 200 does NOT mean all-healthy. Always inspect the body flags.
> The endpoint always returns 200 regardless of health state.

**Flag-by-flag interpretation:**

| Flag | Expected | If not expected |
|------|----------|-----------------|
| `redis_healthy` | `true` | STOP — Redis unreachable; no signals can flow |
| `redis_writeable` | `true` | STOP — MISCONF or disk full; signals cannot be written |
| `db_healthy` | `true` | STOP — PostgreSQL unreachable; no audit trail |
| `killswitch_active` | `false` | STOP — system is halted; investigate before proceeding |
| `stale_signals` | `false` outside market hours: ACCEPTABLE | During market hours: investigate |
| `worker_beat_lag` | `false` | During market hours: STOP; outside: note but may proceed |
| `last_signal_age_minutes` | Any value (may be high outside market hours) | Document value |
| `last_cycle_age_minutes` | Any value or null | Document value; null is acceptable before first cycle |

**Action if any STOP flag is set:** consult the operator runbooks in `docs/operations.md`
(Section "Operator Cockpit Runbooks") for the specific flag. Do not proceed to Step C
until all STOP conditions are resolved.

Record the full JSON response in the evidence package.

---

## 8. Preflight Step C — Strategy Governance Check

```bash
# C1 — Strategy API: list
curl -s -H "X-API-Key: $ADMIN_API_KEY" http://localhost:8001/api/strategies | python3 -m json.tool

# C2 — S1 detail (must show supervised_paper, promotion_blocked=true)
curl -s -H "X-API-Key: $ADMIN_API_KEY" http://localhost:8001/api/strategies/s1 | python3 -m json.tool

# C3 — Lifecycle table (direct DB query)
docker compose exec postgres psql -U trading -d trading \
  -c "SELECT strategy_id, mode, target_mode, promotion_blocked, approved, updated_at
      FROM strategy_lifecycle
      ORDER BY strategy_id;"

# C4 — No live promotions pending
docker compose exec postgres psql -U trading -d trading \
  -c "SELECT COUNT(*) FROM strategy_lifecycle WHERE mode='live' OR target_mode='live';"
# Expected: 0
```

**Pass criteria:**
- `GET /api/strategies/s1` returns `status: "supervised_paper"`, `promotion_blocked: true`, `live_authorized: false`
- No strategy shows `mode='live'` in `strategy_lifecycle`
- S2 is `disabled` (not `paper`, not `live`)
- S7 does not appear in the orchestrator active list (check `GET /api/strategies/s4` for S7 — it should not be there)

Record the full lifecycle table output in the evidence package.

---

## 9. Preflight Step D — Controlled Dry-Run Portfolio Cycle

> **Pre-requisite:** Steps A, B, C must all have passed. Environment safety checklist (Section 4)
> must be complete. Record the start timestamp.

This step runs ONE portfolio cycle through the normal scheduler path using the Celery task queue.
It does NOT bypass any safety gate, does NOT call order functions directly, and submits to the
Alpaca **paper** account only.

### 9.1 — Pre-Run State Capture

```bash
# Record config hash for evidence
md5sum config/trading.yaml config/strategies.yaml

# Record current Redis state
docker compose exec redis redis-cli MGET system:mode killswitch_active regime_multiplier

# Record current portfolio cycle count (baseline)
docker compose exec postgres psql -U trading -d trading \
  -c "SELECT COUNT(*) AS total_cycles FROM portfolio_cycles;"

# Record current execution decisions count (baseline)
docker compose exec postgres psql -U trading -d trading \
  -c "SELECT COUNT(*) AS total_decisions FROM execution_decisions;"
```

### 9.2 — Trigger One Portfolio Cycle

```bash
# Method A — Wait for the next scheduled beat tick (preferred: no manual intervention)
# The beat fires portfolio-cycle at xx:07/22/37/52 during 14:00–21:00 UTC Mon–Fri.
# Monitor logs during the next scheduled window:
docker compose logs -f worker 2>&1 | grep -E "portfolio|PortfolioOrchestra|cycle|order|submit"

# Method B — Trigger manually (only outside market hours or when beat is not running)
# Use only if Method A is not feasible for the dry-run window.
docker compose exec worker celery -A src.workers.celery_app call \
  src.workers.portfolio_scheduler.run_portfolio_cycle
```

> **Do not** call `_submit_portfolio_orders` or any order function directly.  
> **Do not** pass `--bypass` or `--skip-safety` flags — no such flags exist; any manual
> override that bypasses safety gates constitutes a stop condition.

### 9.3 — Evidence to Capture During Cycle

While the cycle runs, capture:

```bash
# Worker logs (capture to file)
docker compose logs worker 2>&1 | tail -200 > /tmp/preflight_cycle_logs_$(date +%Y%m%d_%H%M%S).txt

# After cycle completes — new portfolio_cycles row
docker compose exec postgres psql -U trading -d trading \
  -c "SELECT id, timestamp, strategies_run, orders_count, constraints_fired, nav
      FROM portfolio_cycles
      ORDER BY timestamp DESC LIMIT 3;"

# New execution_decisions rows
docker compose exec postgres psql -U trading -d trading \
  -c "SELECT tick_time, symbol, decision, reason
      FROM execution_decisions
      ORDER BY tick_time DESC LIMIT 20;"
```

Record:
- Cycle ID (from `portfolio_cycles.id`)
- Strategies run (should be S1, S4 — not S2, S3, S7)
- Order count (submitted + skipped)
- Constraints fired (list from `constraints_fired` column)
- NAV reported
- Any S4 idempotency skips (look for `SIGNAL_DUPLICATE_SKIP` in logs)
- Any cap enforcement (look for `ConstraintViolation` in logs)
- Readiness state after cycle

### 9.4 — Verify No Live Orders

```bash
# Confirm the cycle touched only the paper account
grep -i "paper-api.alpaca.markets\|paper_api\|PAPER" /tmp/preflight_cycle_logs_*.txt | head -10
grep -i "api.alpaca.markets" /tmp/preflight_cycle_logs_*.txt | grep -v "paper" | head -10
# Expected: no live endpoint references
```

---

## 10. Preflight Step E — `/api/system/decisions` Verification

```bash
# E1 — Fetch decisions from this cycle
curl -s -H "X-API-Key: $ADMIN_API_KEY" \
  "http://localhost:8001/api/system/decisions?limit=30" | python3 -m json.tool \
  > /tmp/preflight_decisions_$(date +%Y%m%d_%H%M%S).json

cat /tmp/preflight_decisions_*.json
```

**For each decision, verify:**

| Field | Expected |
|-------|----------|
| `tick_time` | Timestamp within last few minutes |
| `symbol` | From `config/trading.yaml` watchlist |
| `decision` | One of: `BUY`, `SELL`, `SKIP_*`, `SKIP_STALE`, `SIGNAL_DUPLICATE_SKIP`, `SKIP_CAP`, `SKIP_SAFETY` |
| `reason` | Non-empty string explaining the decision |
| Unexplained `BUY` | FAIL — every BUY must have a reason and a strategy attribution |
| Order without strategy | FAIL — all orders must trace to S1 or S4 |
| `mode: live` mention | FAIL — must be paper mode |
| `S1 validated` language | FAIL — stale metrics must not appear in decision records |

**Acceptable `SKIP_*` reasons:** stale signal, idempotency duplicate, cap limit, regime block,
no signal, promotion_blocked. All are safety behaviors, not failures.

Record the decisions JSON in the evidence package.

---

## 11. Preflight Step F — Order Lifecycle Evidence

If the dry-run cycle generated paper orders:

```bash
# Query recent trades (if written)
docker compose exec postgres psql -U trading -d trading \
  -c "SELECT symbol, side, quantity, entry_price, opened_at, strategy_source
      FROM trades
      ORDER BY opened_at DESC LIMIT 10;"

# Check paper account for placed orders (via Alpaca paper API)
# Use the SDK or dashboard at https://app.alpaca.markets (paper login)
# Record: order ID, symbol, side, qty, status (accepted/filled/rejected)
```

**For each paper order:**
- Signal ID (from audit logs or `execution_decisions.reason`)
- Strategy (S1 or S4)
- Symbol
- Decision reason
- Submitted / accepted / rejected by broker
- Fill status (filled / partial / open)
- Stop-loss bracket order present (for BUY — required if S4 bracket orders enabled)
- Audit row in `execution_decisions`
- Paper broker order ID
- Confirmation this is a paper account order (from Alpaca paper dashboard)

**If NO orders are generated:**
This is acceptable if:
- All signals are stale (outside market hours)
- All S4 signals are idempotency-skipped (already fired today)
- NAV is zero or positions already fully allocated
- Cap enforcement blocked all BUYs

Capture the skip reasons from `execution_decisions` and/or worker logs. Document why no orders
were generated and confirm this is expected given the current market/signal state.

---

## 12. Preflight Step G — Kill-Switch Rehearsal

> **Important:** This step confirms the emergency halt works. No orders will be placed while the
> kill-switch is active. Complete Step D first.

### 12.1 — Record Baseline

```bash
# Confirm kill-switch is currently inactive
curl -s -H "X-API-Key: $ADMIN_API_KEY" http://localhost:8001/api/system/readiness \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('killswitch_active:', d['killswitch_active'])"
# Expected: killswitch_active: False
```

### 12.2 — Activate Kill-Switch

```bash
# Activate via documented API endpoint
curl -X POST http://localhost:8001/api/admin/killswitch \
  -H "X-API-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"active": true}'

# Verify activation
curl -s -H "X-API-Key: $ADMIN_API_KEY" http://localhost:8001/api/system/readiness \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('killswitch_active:', d['killswitch_active'])"
# Expected: killswitch_active: True
```

### 12.3 — Verify Cycle Halts

```bash
# Check Redis directly
docker compose exec redis redis-cli GET killswitch_active
# Expected: "1"

# Trigger or wait for next portfolio cycle (if within market hours)
# Worker log should contain: "kill.switch" or "killswitch" with "active" and "halt"
docker compose logs worker 2>&1 | grep -i "kill.switch\|killswitch" | tail -10
# Expected: log line showing cycle aborted before order submission
```

### 12.4 — Reset Kill-Switch (OTP Flow)

```bash
# Use the OTP recovery endpoint (NOT redis-cli SET killswitch_active 0)
# The OTP flow enforces cooldown and writes an audit row.
curl -X POST http://localhost:8001/api/admin/killswitch/recover \
  -H "X-API-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"otp": "<OTP from Telegram recovery flow>"}'

# If OTP not yet available, check Telegram for recovery prompt
# OR wait for the 2-minute cooldown to expire and retry

# Verify reset
curl -s -H "X-API-Key: $ADMIN_API_KEY" http://localhost:8001/api/system/readiness \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('killswitch_active:', d['killswitch_active'])"
# Expected: killswitch_active: False
```

> **If the kill-switch cannot be reset** via the OTP recovery endpoint, **stop and escalate** to the
> PO. Do NOT use `redis-cli SET killswitch_active 0` as a bypass — it circumvents the audit trail
> and cooldown protection (see `docs/operations.md` → Runbook: Kill-Switch Active).

### 12.5 — Evidence Capture

Record:
- Timestamp of activation
- Timestamp of confirmation (readiness shows `killswitch_active: true`)
- Worker log line showing cycle halt
- Timestamp of reset
- Readiness after reset (`killswitch_active: false`)
- Any OTP/recovery audit row in `strategy_lifecycle_audit` or worker logs

---

## 13. Preflight Step H — Evidence Package

Collect the following artifacts before submitting the PO sign-off package:

```
evidence/preflight-YYYY-MM-DD/
├── 01_git_state.txt              # git log --oneline -5 output
├── 02_suite_result.txt           # pytest -q tail output (2393 passed...)
├── 03_readiness_before.json      # GET /api/system/readiness BEFORE dry-run
├── 04_readiness_after.json       # GET /api/system/readiness AFTER dry-run
├── 05_readiness_after_ks.json    # GET /api/system/readiness AFTER kill-switch reset
├── 06_strategy_status.json       # GET /api/strategies/s1 full response
├── 07_lifecycle_table.txt        # SELECT * FROM strategy_lifecycle output
├── 08_cycle_logs.txt             # Worker logs during dry-run cycle
├── 09_portfolio_cycles.txt       # SELECT from portfolio_cycles (last 3 rows)
├── 10_decisions.json             # GET /api/system/decisions output
├── 11_order_lifecycle.txt        # trades + paper broker order IDs
├── 12_killswitch_rehearsal.txt   # Kill-switch activate/verify/reset log
├── 13_config_hashes.txt          # md5sum trading.yaml strategies.yaml
├── 14_env_safety_checks.txt      # Section 4 results
└── 15_operator_notes.txt         # Any deviations, explanations, open items
```

Use this command to create the directory and start capturing:

```bash
mkdir -p evidence/preflight-$(date +%Y-%m-%d)
# Then save each artifact to its respective file as you complete each step.
```

**Mandatory items — evidence package is incomplete without all of these:**
- ✅ Commit hash recorded
- ✅ Config hashes recorded
- ✅ Full suite result (pass count + skipped count)
- ✅ Readiness before and after cycle (body JSON)
- ✅ Strategy status snapshot (S1 `supervised_paper`, S4 `paper`, S2 `disabled`)
- ✅ Decisions export (all decisions from dry-run cycle)
- ✅ Order lifecycle (paper orders or documented reason for no orders)
- ✅ Kill-switch rehearsal evidence (activate → halt → reset)
- ✅ Residual risk register snapshot (confirm R-04 through R-12 reviewed)
- ✅ Operator statement: "No live credentials were loaded; no live orders were placed"

---

## 14. Go / No-Go Criteria for PO Sign-Off

### GO — all of the following must be true

```
[ ] readiness all-green: redis_healthy=true, redis_writeable=true, db_healthy=true,
      killswitch_active=false, no unexplained stale/lag flags
[ ] dry-run cycle completed: at least one portfolio_cycles row created
[ ] decisions explain all cycle actions: every BUY/SELL/SKIP has a non-empty reason
[ ] no live account touched: paper endpoint confirmed in all order logs
[ ] kill-switch rehearsal passed: activated, cycle halted, reset successful via OTP flow
[ ] no safety red flags in logs: no ConstraintViolation bypass, no promotion_blocked bypass
[ ] residual risks accepted: operator reviewed R-04..R-12 and countersigned in evidence
[ ] S1 API does not report validated/live-ready: confirmed in Step A4
[ ] S2 not active: disabled in lifecycle table and not in cycle strategies_run
[ ] S7 not in orchestrator: not listed in strategies_run in portfolio_cycles
[ ] evidence package complete: all 15 artifacts present
[ ] PO has reviewed evidence package
[ ] PO explicitly signs (Section 15)
```

### NO-GO — any of the following blocks PO sign-off

```
[ ] readiness shows redis_healthy=false, redis_writeable=false, or db_healthy=false
[ ] killswitch_active=true and cannot be reset
[ ] any live credential detected in .env or logs
[ ] any live API endpoint called (api.alpaca.markets without "paper")
[ ] kill-switch cannot activate or reset successfully
[ ] strategy API still reports S1 status="validated"
[ ] S2 appears in strategies_run (should be disabled)
[ ] S7 appears in strategies_run (should be R&D/contained)
[ ] any strategy shows mode='live' in strategy_lifecycle
[ ] BUY order without reason in execution_decisions
[ ] broker reject silently ignored (no audit row, no _on_broker_reject callback evidence)
[ ] cap violation not enforced (ConstraintEnforcer output missing from logs)
[ ] idempotency skip not working (same S4 signal fires twice in decisions)
[ ] paper order missing stop-loss bracket (for S4 BUYs when bracket mode enabled)
[ ] missing audit evidence (portfolio_cycles row not created)
[ ] GLOBAL_LIVE_PROMOTION_ENABLED found True
[ ] any evidence artifact missing from Section 13
```

If any NO-GO condition is found, stop, document the finding, resolve it, and restart the
affected preflight steps. Do not present incomplete evidence to the PO.

---

## 15. PO Sign-Off Template

Complete this block after all preflight steps have passed and the evidence package is assembled.
The PO must review the evidence package before signing.

```
═══════════════════════════════════════════════════════════════════════════════
ALEMBIC — CONTROLLED PAPER TRADING AUTHORIZATION
═══════════════════════════════════════════════════════════════════════════════

Date / Time (UTC):        ____________________________
Preflight commit:         ____________________________
Config hash (trading):    ____________________________
Config hash (strategies): ____________________________
Operator:                 ____________________________
Environment:              Alpaca paper (paper-api.alpaca.markets)

Strategies in scope:
  S1 — supervised_paper   [ ] confirmed in lifecycle table
  S4 — paper              [ ] confirmed in lifecycle table
  S2 — disabled           [ ] confirmed NOT in scope
  S7 — research/contained [ ] confirmed NOT in orchestrator

Preflight results:
  Readiness (before dry-run):  redis_healthy=[ ] redis_writeable=[ ] db_healthy=[ ]
  Dry-run cycle completed:     [ ] portfolio_cycles row ID: ______
  Decisions reviewed:          [ ] all have non-empty reason
  No live account touched:     [ ] operator statement present in evidence
  Kill-switch rehearsal:       [ ] activated [ ] cycle halted [ ] reset via OTP

Evidence package location:    evidence/preflight-____-____-____/
Evidence artifacts complete:  [ ] all 15 artifacts present (see Section 13)

Residual risks R-04..R-12 reviewed and accepted by: ____________________________

───────────────────────────────────────────────────────────────────────────────
AUTHORIZATION DECISIONS (PO MUST COMPLETE ALL THREE)
───────────────────────────────────────────────────────────────────────────────

Controlled paper trading authorized?          [ ] YES   [ ] NO
Live trading authorized?                      [ ] NO    (must be NO — do not check YES)
Strategy promotions authorized?               [ ] NO    (must be NO — do not check YES)

If YES for controlled paper: operator may start scheduled paper trading sessions.
                             Monitor daily per Section 16. Stop on any Section 17 condition.

───────────────────────────────────────────────────────────────────────────────
PO Name:          ____________________________
PO Signature:     ____________________________
Date signed:      ____________________________
═══════════════════════════════════════════════════════════════════════════════
```

Scan and include the signed template in the evidence package as artifact `16_po_signoff.pdf`.

---

## 16. First Controlled Paper Day Checklist

*This section is a FUTURE reference only. It does not authorize paper trading — that requires
the signed PO template from Section 15.*

### Pre-market (before 14:00 UTC Mon–Fri)

```
[ ] GET /api/system/readiness — all 6 flags green
[ ] Strategy lifecycle table confirmed: S1=supervised_paper, S4=paper, S2=disabled
[ ] GLOBAL_LIVE_PROMOTION_ENABLED=False confirmed
[ ] Regime multiplier loaded: docker compose exec redis redis-cli GET regime_multiplier
[ ] Telegram bot responding (send /ping or similar test message)
[ ] Kill-switch accessible (test POST, then immediately reset)
[ ] AUTO_APPLY_ENABLED=false for first week (manual weight approval)
[ ] Daily loss limit confirmed in trading.yaml: portfolio_drawdown: 0.05 (5%)
[ ] Operator online and monitoring during 14:00–21:00 UTC session
```

### During session

```
[ ] Poll GET /api/system/readiness every 30 min (or set cron alert)
[ ] Monitor GET /api/system/decisions after each portfolio cycle
[ ] Monitor Telegram for CRITICAL alerts (drawdown cap, IC below threshold, drift)
[ ] Grafana: watch "Signal score distribution", "IC rolling 30d", "Kill-switch events"
[ ] If any NO-GO condition in Section 17 fires: activate kill-switch, stop, escalate
```

### End of day

```
[ ] GET /api/system/decisions?limit=50 — export and review
[ ] Check paper account P&L (Alpaca paper dashboard)
[ ] Run forward-return worker: docker compose exec worker celery ... call run_forward_return_worker
[ ] Check portfolio_cycles for today's runs
[ ] Document any anomalies in daily notes
[ ] Save evidence: readiness snapshot, decisions export, P&L summary
```

**Kill criteria (activate kill-switch immediately):**
- Portfolio daily loss ≥ 5% (auto-activates; also manual if auto fails)
- Any signal pointing to live account
- Any strategy showing mode='live' in lifecycle
- Redis not writable during market hours
- Unexplained order not matching any signal

**Monitoring cadence:**
- Pre-market: 1 full readiness check
- During market hours: every 30 min (readiness + decisions)
- Post-market: daily evidence pack + Telegram digest review

---

## 17. Stop Conditions During Paper

Activate the kill-switch and escalate to PO if any of the following occur:

| Condition | Action |
|-----------|--------|
| `killswitch_active=true` not resetting | Investigate before any cycle |
| `redis_writeable=false` during market hours | Stop all cycles; see operations.md |
| `db_healthy=false` | Stop; audit trail unavailable |
| `stale_signals=true` during market hours for >15 min | Investigate ingestion pipeline |
| Divergence threshold breached: Jaccard < 0.8 (signal vs orders) | Review decisions |
| Broker reject spike (>30% of submitted orders rejected in one cycle) | Stop; investigate |
| Partial fill unresolved for >24h | Investigate reconcile-fills-evening task |
| Cap violation not enforced (BUY quantity exceeds `max_portfolio_exposure × NAV`) | CRITICAL: stop |
| Order submitted without matching `execution_decisions` audit row | CRITICAL: stop |
| `strategy_lifecycle` shows any strategy with `mode='live'` | CRITICAL: stop immediately |
| `GLOBAL_LIVE_PROMOTION_ENABLED` found True | CRITICAL: set back to False; restart services; notify PO |
| Any order confirmed against live Alpaca account (not paper) | CRITICAL: stop; notify PO |
| PO revokes authorization | Stop all cycles; do not resume without new sign-off |

**Emergency halt command:**
```bash
curl -X POST http://localhost:8001/api/admin/killswitch \
  -H "X-API-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"active": true}'
```

---

## 18. Relationship to Frontend / Operator Surface

The Alembic frontend (React dashboard, port 3000) currently does NOT provide a dedicated
operator cockpit UI for:
- Live readiness status (`/api/system/readiness` flags)
- Strategy lifecycle mode display
- Promotion-blocked state per strategy

**For all preflight and paper-monitoring tasks, operators must use the API endpoints directly
(documented in this runbook and in `docs/FRONTEND_OPERATOR_GUIDE.md`).**

A cockpit UI is on the backlog (P3 scope). Its absence is acceptable for the dry-run and
initial paper trading phase provided:
- The operator has direct API access and the `ADMIN_API_KEY`
- Readiness and decisions are polled manually per the cadence in Section 16
- Evidence is captured as API JSON responses

**Recommended operator setup (no UI required):**
```bash
# Alias for quick readiness check
alias readiness='curl -s -H "X-API-Key: $ADMIN_API_KEY" http://localhost:8001/api/system/readiness | python3 -m json.tool'

# Alias for recent decisions
alias decisions='curl -s -H "X-API-Key: $ADMIN_API_KEY" "http://localhost:8001/api/system/decisions?limit=20" | python3 -m json.tool'
```

---

## 19. Appendices

### 19.1 — Endpoint Reference

| Endpoint | Auth | Purpose | Section |
|----------|------|---------|---------|
| `GET /api/health` | No | Basic stack health | 4.4 |
| `GET /api/system/readiness` | Yes | 8-flag health dict | 7 |
| `GET /api/system/decisions?limit=N` | Yes | Recent execution decisions | 10 |
| `GET /api/system/scheduler` | Yes | Beat schedule + last run times | — |
| `GET /api/system/activity` | Yes | Unified activity log | — |
| `GET /api/strategies/s1` | Yes | S1 status + authorization fields | 8 |
| `GET /api/strategies` | Yes | All strategies list | 8 |
| `GET /api/admin/status` | Yes | Kill-switch state + mode | 12 |
| `POST /api/admin/killswitch` | Yes | Activate/deactivate kill-switch | 12 |
| `POST /api/admin/killswitch/recover` | Yes | OTP recovery after drawdown halt | 12 |
| `POST /api/admin/mode` | Yes | Set operating mode (paper/halted/…) | 4.9 |

Auth: `X-API-Key: $ADMIN_API_KEY` header required for all authenticated endpoints.
Base URL: `http://localhost:8001` (local) or `http://<HOST>:8001` (remote).

### 19.2 — Expected `/api/system/readiness` JSON Shape

```json
{
  "redis_healthy": true,
  "redis_writeable": true,
  "db_healthy": true,
  "killswitch_active": false,
  "stale_signals": false,
  "worker_beat_lag": false,
  "last_signal_age_minutes": 12.4,
  "last_cycle_age_minutes": 45.2
}
```

### 19.3 — Redis Keys Used During Preflight

| Key | Purpose | Expected value |
|-----|---------|----------------|
| `killswitch_active` | Kill-switch state | `0` or nil (not `1`) |
| `system:mode` | Operating mode | `"paper"` |
| `regime_multiplier` | Regime scale | `"1.0"` (bull), `"0.7"` (sideways), etc. |
| `ensemble:weights:current` | LLM ensemble weights | JSON with model weights |
| `s4:fired_signals:<YYYY-MM-DD>` | S4 idempotency tracking | Set of signal IDs fired today |
| `readiness:ping` | MISCONF write test | Set by readiness check, TTL 30s |

### 19.4 — Docker Compose Manual Cycle Trigger

```bash
# Manual portfolio cycle trigger (use only when beat is not running or for dry-run)
docker compose exec worker celery -A src.workers.celery_app call \
  src.workers.portfolio_scheduler.run_portfolio_cycle

# Check if beat is running
docker compose ps beat

# Check active Celery tasks
docker compose exec worker celery -A src.workers.celery_app inspect active
```

### 19.5 — Evidence Checklist (quick reference)

```
[ ] 01_git_state.txt
[ ] 02_suite_result.txt
[ ] 03_readiness_before.json
[ ] 04_readiness_after.json
[ ] 05_readiness_after_ks.json
[ ] 06_strategy_status.json
[ ] 07_lifecycle_table.txt
[ ] 08_cycle_logs.txt
[ ] 09_portfolio_cycles.txt
[ ] 10_decisions.json
[ ] 11_order_lifecycle.txt
[ ] 12_killswitch_rehearsal.txt
[ ] 13_config_hashes.txt
[ ] 14_env_safety_checks.txt
[ ] 15_operator_notes.txt
[ ] 16_po_signoff.pdf   (after PO signs)
```

### 19.6 — Glossary

| Term | Definition |
|------|-----------|
| **paper trading** | Trading against a simulated paper account (Alpaca paper); no real money |
| **controlled paper** | Supervised paper trading with daily evidence collection and monitoring; authorized only by PO sign-off |
| **supervised_paper** | Strategy lifecycle mode meaning the strategy is under manual human observation in paper mode; not promotable to live without gate re-run |
| **promotion_blocked** | Flag in `strategy_lifecycle` and `config/strategies.yaml` that prevents any promotion request from completing; requires explicit human removal |
| **live** | Strategy mode where real capital is deployed on a live brokerage account; requires 90-day paper period + OOS Sharpe + `GLOBAL_LIVE_PROMOTION_ENABLED=True` + PO sign-off |
| **readiness** | The 8-flag health dict returned by `/api/system/readiness`; HTTP 200 does not imply all-healthy |
| **decision** | A row in `execution_decisions` recording what the execution engine decided per tick per symbol |
| **dry-run** | A single portfolio cycle executed in paper mode to generate evidence; does not authorize ongoing paper trading |
| **kill-switch** | Redis flag `killswitch_active`; when `1`, all order submission is halted; reset only via OTP recovery flow |
| **evidence package** | The set of 15+ artifacts in `evidence/preflight-YYYY-MM-DD/` that the PO reviews before sign-off |
| **P2_ACCEPTED_WITH_RUNTIME_MONITORING** | The Kimi audit verdict: P2 engineering complete; monitoring watchlist (R-04..R-12) must be reviewed during paper |

---

## Document History

| Version | Date | Author | Change |
|---------|------|--------|--------|
| 1.0 | 2026-06-21 | Maintainer | Initial runbook — dry-run and PO sign-off pending |
