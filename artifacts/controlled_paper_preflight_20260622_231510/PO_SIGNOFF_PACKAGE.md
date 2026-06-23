# ALEMBIC — CONTROLLED PAPER TRADING PO SIGN-OFF PACKAGE

**Document type:** PO Sign-Off Package  
**Preflight date:** 2026-06-22  
**Preflight time (UTC):** 21:15 – 21:24  
**Evidence directory:** `artifacts/controlled_paper_preflight_20260622_231510/`  
**Operator:** Maintainer (Claude Code / Jonbj)  
**Commit at preflight start:** `9e1039e` (HEAD, branch: main)

---

## 1. Commit and Config Hashes

| Item | Value |
|------|-------|
| HEAD commit | `9e1039e20eb0183dcd19e320333a183c9ed3f180` |
| Commit message | `docs(pre-paper): reconcile stale doc/API surfaces per Kimi P2 Audit findings` |
| Branch | `main` |
| `config/trading.yaml` MD5 | `2759498a5a73012d3a305fe18cbb629e` |
| `config/strategies.yaml` MD5 | `11d7e81704bd3f805b0a562d98284ddf` |
| Working tree status | **19 modified / 8 untracked files** (F0-1/F0-3 safety hygiene + backend fixes — all safety improvements, none committed yet) |

---

## 2. Environment Confirmation

| Check | Value | Result |
|-------|-------|--------|
| `ALPACA_BASE_URL` | `https://paper-api.alpaca.markets` | ✅ PAPER |
| API key prefix | `PK` | ✅ PAPER KEY |
| Live endpoint in .env | 0 occurrences | ✅ NONE |
| `GLOBAL_LIVE_PROMOTION_ENABLED` | `False` | ✅ PASS |
| `system:mode` (Redis) | `paper` | ✅ PASS |
| `/api/admin/status` mode | `paper` | ✅ PASS |

**Operator statement:** No live credentials were loaded. No live orders were placed. All interactions were with `paper-api.alpaca.markets` paper account only.

---

## 3. Readiness — Before Dry-Run

| Flag | Value | Assessment |
|------|-------|------------|
| `redis_healthy` | `true` | ✅ PASS |
| `redis_writeable` | `true` | ✅ PASS |
| `db_healthy` | `true` | ✅ PASS |
| `killswitch_active` | `false` | ✅ PASS |
| `stale_signals` | `false` | ✅ PASS |
| `worker_beat_lag` | `true` | ⚠️ OUTSIDE MARKET HOURS (21:17 UTC Sunday — acceptable) |
| `last_signal_age_minutes` | `11.97` | ℹ️ Signals active |
| `last_cycle_age_minutes` | `5844` (~97h) | ℹ️ System idle since 2026-06-18 |

**Assessment:** All blocking flags green. `worker_beat_lag=true` is expected and documented-acceptable outside US market hours.

---

## 4. Strategy Governance

| Strategy | Mode (lifecycle DB) | Approved (DB) | Mode (YAML) | Enabled (YAML) | In Scope |
|----------|---------------------|---------------|-------------|----------------|---------|
| S1 | `supervised_paper` | `false` | `supervised_paper` | `true` | ✅ Observation only |
| S2 | `disabled` | `true` ⚠️ | `research` | `false` | ❌ Excluded (allocation=0%, disabled) |
| S4 | `paper` | `false` | `paper` | `true` | ✅ With gates (approved=false blocks) |
| S7 | not present | N/A | `research` | `false` | ❌ Excluded (R&D, allocation=0%) |

**S1 API truth (GET /api/strategies/s1):**
- `status: supervised_paper` ✅
- `promotion_blocked: true` ✅
- `live_authorized: false` ✅
- `data_quality_warning: present` ✅

**No live promotions pending:** `SELECT COUNT(*) FROM strategy_lifecycle WHERE mode='live' OR target_mode='live'` = **0** ✅

**S2 data inconsistency:** `approved=true` despite `mode=disabled`. This is a data artifact — S2 has no execution path (enabled=false, allocation_pct=0.00, mode=disabled in lifecycle). Risk: **LOW**. Recommend cleanup before PO sign-off.

---

## 5. Frontend Safety Hygiene

| Test | Result |
|------|--------|
| F0-1 vitest tests (5/5) | ✅ 5 PASSED |
| F0-3 vitest tests (5/5) | ✅ 5 PASSED |
| Total frontend tests | ✅ 10/10 PASSED |
| TypeScript compilation | ✅ PASS (exit 0) |
| `VALIDATA` in frontend/src | Only in test (negative assertion) ✅ |
| `validated` misleading use | None ✅ |
| `in esecuzione live` | Only in test (negative assertion) ✅ |
| `full_auto` badge color | `badge-red` ✅ |
| Kill-switch deactivation | OTP confirm dialog required ✅ |
| Risk slider warnings | `RiskParamWarning` + save confirm for >10% ✅ |
| Promote/approve/demote UI | None for strategy lifecycle ✅ |

**Note:** `LLM.tsx` has an `approveWeights` button — this approves **LLM ensemble weights** (a different concept from strategy lifecycle promotion). This is existing, documented operator functionality, not a strategy promotion control.

**Pre-existing ESLint issues** (not in F0-1/F0-3 scope): ApiKeyModal.tsx, Layout.tsx, News.tsx, Performance.tsx, Signals.tsx — unrelated to safety hygiene changes.

---

## 6. Dry-Run Cycle Result

**Task ID:** `abb2243f-f272-4fd7-91ef-2651fec4b776`  
**Triggered at:** 2026-06-22T21:18:12Z  
**Method:** Celery manual trigger (same safety-gated path as scheduler)

**Result:**
```
{'skipped': True, 'reason': 'no_approved_strategies'}
```

**Worker log:**
```
Strategy S1: approved=False in strategy_lifecycle — excluded from cycle.
Strategy S4: approved=False in strategy_lifecycle — excluded from cycle.
No operationally approved strategies — skipping portfolio cycle
```

**Analysis:**
The `_filter_approved_strategies()` gate is working correctly as designed (fail-closed). Neither S1 nor S4 have `approved=True` in `strategy_lifecycle`. No portfolio_cycles row was created. No orders were submitted.

This is the intended behavior — the `approved` flag is the final mechanical gate that requires explicit PO authorization. **To enable real paper cycles, the PO must set `approved=True` for at least one strategy.**

**Historical cycle evidence (pre-existing, from 2026-06-18):**
```
id=89, strategies_run=["S1","S4"], orders_count=5, constraints_fired=[]
id=88, strategies_run=["S1","S4"], orders_count=5, constraints_fired=[]
id=87, strategies_run=["S1","S4"], orders_count=6, constraints_fired=[]
```
Demonstrates that the full order path (S1+S4 running, orders placed, no constraint violations) was operational before the approved gate was added.

---

## 7. Decisions Summary

- **Total decisions from last 30:** 30 (all from cycles 87-89, 2026-06-18)
- **All from S4** (news-driven, LLM attribution)
- **Unexplained BUYs:** 0 ✅
- **Live mode references:** 0 ✅
- **"validated" language:** 0 ✅
- **Symbols:** AMAT, AZN, CRM, IWM, ORCL, QQQ, XLK (all from watchlist)

No new decisions were created by the preflight dry-run (cycle was skipped at approved gate).

---

## 8. Order Lifecycle Summary

**During preflight cycle:** 0 orders submitted (cycle skipped — approved gate)  
**Open trades from previous sessions:** 16 open positions

⚠️ **R-13 WARNING (pyramiding):** Trades show multiple open positions per symbol:
- ORCL: 4 positions (IDs 184, 185, 186, 187)
- IWM: 3 positions (IDs 188, 189, 191)
- AMAT: 2 positions (IDs 190, 192)

The `open_trade_symbols` pyramid guard must be verified as active when `approved=True`. Recommend resolving or acknowledging existing open positions before first authorized paper cycle.

---

## 9. Kill-Switch Rehearsal

| Step | Action | Result |
|------|--------|--------|
| Baseline | `killswitch_active=false` confirmed | ✅ |
| Activation | `POST /api/admin/killswitch` | `{"killswitch":"activated","mode":"halted"}` ✅ |
| Readiness confirm | `killswitch_active: true` | ✅ |
| Cycle halt | Worker: `Portfolio cycle skipped — kill-switch active` | ✅ |
| Emergency cancel | Worker: `EMERGENCY: cancelled all pending Alpaca orders` | ✅ |
| Cooldown enforced | 120s wait (policy enforced in backend) | ✅ |
| Recovery token | `POST /api/admin/killswitch/recovery-token` (5-min OTP) | ✅ |
| Deactivation | `DELETE /api/admin/killswitch?confirm_token=<OTP>` | `{"killswitch":"deactivated","mode":"paper"}` ✅ |
| Final readiness | `killswitch_active: false` | ✅ |

**Kill-switch rehearsal: PASS** — full activate/halt/reset cycle verified.

---

## 10. Final Readiness

```json
{
  "redis_healthy": true,
  "redis_writeable": true,
  "db_healthy": true,
  "killswitch_active": false,
  "stale_signals": false,
  "worker_beat_lag": true,
  "last_signal_age_minutes": 3.20,
  "last_cycle_age_minutes": 5851.98
}
```

All blocking flags: **GREEN** ✅  
`worker_beat_lag`: outside market hours — acceptable.

---

## 11. Residual Risks Reviewed (R-04 to R-15)

| Risk | Severity | Status | Accepted |
|------|----------|--------|---------|
| R-04 Soft CI gates (mypy/pip-audit/gitleaks) | MEDIUM | Open | Accept for paper |
| R-05 LLM divergence max_consecutive_fallbacks | MEDIUM | Open | Accept for paper |
| R-06 S3 not forensic-reviewed | MEDIUM | Open | Accept (S3 not in scope) |
| R-07 Controlled paper not yet started | HIGH | Pending PO sign-off | — |
| R-08 Live trading not authorized | CRITICAL | Not authorized | Not authorized |
| R-09 yfinance reliability | MEDIUM | Open | Accept for paper |
| R-10 Telegram bot token rotation | MEDIUM | Open | Accept for paper |
| R-11 Redis flush clears kill-switch | HIGH | Open | Accept for paper (monitor) |
| R-12 S7 wiring risk | MEDIUM | Mitigated | Accept |
| R-13 Pyramiding (16 open positions) | HIGH | Open — PREFLIGHT BLOCKER | ⚠️ Requires PO acknowledgment |
| R-14 entry_time NULL on closed trades | HIGH | Open | Accept for paper (blocks postmortem) |
| R-15 Postmortem pipeline never ran | MEDIUM | Open | Accept (blocked by R-14) |

**R-13 requires explicit PO acknowledgment** before authorizing the first paper cycle.

---

## 12. Remaining Gaps / Items for PO Decision

Before the PO signs and before controlled paper can begin:

1. **`approved=True` required**: PO must set `approved=True` for at least S1 and/or S4 in `strategy_lifecycle`:
   ```sql
   UPDATE strategy_lifecycle SET approved=true, updated_at=now() WHERE strategy_id IN ('S1','S4');
   ```
   Without this, no portfolio cycles will run.

2. **R-13 acknowledgment**: 16 open paper positions (multiple per symbol). Resolve or explicitly accept pyramid risk before first authorized cycle.

3. **Uncommitted changes**: 19 modified + 8 untracked files (F0-1/F0-3 frontend safety hygiene + backend fixes). Should be committed before or after PO sign-off.

4. **S2 `approved=true` cleanup** (minor): `approved=true` on disabled strategy is a data inconsistency. Recommend `UPDATE strategy_lifecycle SET approved=false WHERE strategy_id='S2';`

5. **S4 not in strategies API**: S4 is not in the `STRATEGIES` dict in `src/api/routes/strategies.py`. Informational gap — S4 is tracked in lifecycle table and YAML but not frontend-visible. Consider adding for transparency.

6. **Docker image rebuild recommended** after uncommitted changes are committed.

---

## 13. Evidence Artifacts

| Artifact | File | Status |
|----------|------|--------|
| Git state | `static_verification.txt` | ✅ Present |
| Environment safety | `environment_safety.txt` | ✅ Present |
| Frontend hygiene | `frontend_safety_hygiene_verification.txt` | ✅ Present |
| Readiness before | `readiness_before.json` | ✅ Present |
| Readiness after cycle | `readiness_after.json` | ✅ Present |
| Readiness after KS reset | `readiness_final.json` | ✅ Present |
| Strategy status | `strategy_status_before.json` | ✅ Present |
| Lifecycle table | `lifecycle_table.txt` | ✅ Present |
| Cycle logs | `cycle_output.log` | ✅ Present |
| Portfolio cycles DB | included in `orders_after.json` | ✅ Present |
| Decisions (before/after) | `decisions_before.json` / `decisions_after.json` | ✅ Present |
| Order lifecycle | `orders_after.json` | ✅ Present |
| Kill-switch rehearsal | `killswitch_before.json`, `killswitch_active.json`, `killswitch_cycle_output.log`, `killswitch_reset.json` | ✅ Present |
| Config hashes | `config_hashes.txt` | ✅ Present |

---

## 14. Authorization Block (PO MUST COMPLETE)

```
═══════════════════════════════════════════════════════════════════════════════
ALEMBIC — CONTROLLED PAPER TRADING AUTHORIZATION
═══════════════════════════════════════════════════════════════════════════════

Date / Time (UTC):          2026-06-22 21:24 UTC
Preflight commit:           9e1039e20eb0183dcd19e320333a183c9ed3f180
Config hash (trading.yaml): 2759498a5a73012d3a305fe18cbb629e
Config hash (strategies):   11d7e81704bd3f805b0a562d98284ddf
Operator:                   Maintainer / Jonbj
Environment:                Alpaca paper (paper-api.alpaca.markets)

Strategies in scope:
  S1 — supervised_paper   [ ] confirmed in lifecycle table
  S4 — paper              [ ] confirmed in lifecycle table
  S2 — disabled           [ ] confirmed NOT in scope
  S7 — research/contained [ ] confirmed NOT in orchestrator

Preflight results:
  Readiness (before):       redis_healthy=✅ redis_writeable=✅ db_healthy=✅
  Dry-run cycle:            [ ] SKIPPED (approved gate — correct fail-closed behavior)
                              Requires approved=True for S1/S4 to run real cycles
  Decisions reviewed:       [ ] All 30 historical decisions have non-empty reasons
  No live account touched:  [ ] Operator statement present in evidence
  Kill-switch rehearsal:    [ ] activated ✅ [ ] cycle halted ✅ [ ] reset via OTP ✅

Evidence package:           artifacts/controlled_paper_preflight_20260622_231510/

Residual risks R-04..R-15 reviewed by: ____________________________

Pre-authorization actions required:
  [ ] R-13 acknowledged (16 open positions, pyramid risk accepted)
  [ ] approved=True set for S1 and/or S4 in strategy_lifecycle
  [ ] Uncommitted F0-1/F0-3 changes committed

───────────────────────────────────────────────────────────────────────────────
AUTHORIZATION DECISIONS (PO MUST COMPLETE ALL THREE)
───────────────────────────────────────────────────────────────────────────────

Controlled paper trading authorized?          [ ] YES   [ ] NO
Live trading authorized?                      [ ] NO    (must be NO — do not check YES)
Strategy promotions authorized?               [ ] NO    (must be NO — do not check YES)

If YES for controlled paper: also run the strategy lifecycle approval command:
  docker exec alembic-postgres-1 psql -U trading -d trading -c \
    "UPDATE strategy_lifecycle SET approved=true, updated_at=now() WHERE strategy_id IN ('S1','S4');"

───────────────────────────────────────────────────────────────────────────────
PO Name:          ____________________________
PO Signature:     ____________________________
Date signed:      ____________________________
═══════════════════════════════════════════════════════════════════════════════
```
