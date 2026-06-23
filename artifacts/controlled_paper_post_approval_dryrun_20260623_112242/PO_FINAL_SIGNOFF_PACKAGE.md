# ALEMBIC — CONTROLLED PAPER TRADING PO FINAL SIGN-OFF PACKAGE

**Document type:** PO Final Sign-Off Package (Post-Approval Dry-Run)  
**Date/Time (UTC):** 2026-06-23 11:30 UTC  
**Evidence directory:** `artifacts/controlled_paper_post_approval_dryrun_20260623_112242/`  
**Prior preflight evidence:** `artifacts/controlled_paper_preflight_20260622_231510/`  
**Operator:** Maintainer (Claude Code / Jonbj)  
**Commit at approval:** (see git status — committed changes from 2026-06-23 session + BUG-2/4/5 fixes)

---

## 1. Prior Preflight Evidence Reference

| Item | Value |
|------|-------|
| Preflight date | 2026-06-22 21:15–21:24 UTC |
| Preflight evidence | `artifacts/controlled_paper_preflight_20260622_231510/` |
| Preflight verdict | `PREFLIGHT_PASS_WITH_WARNINGS_READY_FOR_PO_REVIEW` |
| Preflight commit | `9e1039e20eb0183dcd19e320333a183c9ed3f180` |
| Dry-run result | SKIPPED (no_approved_strategies) — correct fail-closed behavior |
| Kill-switch rehearsal | PASS (full activate/halt/OTP-reset cycle) |

---

## 2. PO Approval Governance Evidence

**Authorization type:** Explicit PO operational instruction, 2026-06-23  
**PO identity:** Jonbj / Stefano Delgobbo (stefano.delgobbo@gmail.com)  
**Scope authorized:** S1/S4 approved=true for controlled paper path only

**SQL executed:**
```sql
UPDATE strategy_lifecycle
SET approved = true, updated_at = CURRENT_TIMESTAMP
WHERE strategy_id IN ('S1', 'S4');
```

**Result:** `UPDATE 2` — confirmed only 2 rows updated.

---

## 3. Approval Governance Before / After

| strategy_id | mode | approved (before) | approved (after) | mode changed? |
|-------------|------|-------------------|-----------------|---------------|
| S1 | supervised_paper | **false** | **true** | NO |
| S2 | disabled | true (unchanged) | true (unchanged) | NO |
| S4 | paper | **false** | **true** | NO |

**Changes:** ONLY `approved` and `updated_at` modified for S1/S4.  
**target_mode, promoted_by, promoted_at, gate_report_id:** ALL NULL — unchanged.  
**GLOBAL_LIVE_PROMOTION_ENABLED:** False — unchanged.  
**promotion_blocked:** True for S1/S4 — unchanged (enforced in API layer).  
**live_authorized:** False for S1/S4 — unchanged.

---

## 4. Readiness Before Approval

```json
{"redis_healthy":true,"redis_writeable":true,"db_healthy":true,
 "killswitch_active":false,"stale_signals":true,"worker_beat_lag":true,
 "last_signal_age_minutes":814.16,"last_cycle_age_minutes":6690.89}
```

All blocking flags: **GREEN** ✅  
stale_signals=true: system idle ~13.5h (non-blocking — no new LLM signals ingested since last session)  
worker_beat_lag=true: outside US market hours (07:22 EDT) — expected, acceptable

---

## 5. Post-Approval Dry-Run Cycle Result

| Item | Value |
|------|-------|
| Task ID | `95a6bfbc-752c-4d80-a82f-c7889aa08d0d` |
| Triggered at | 2026-06-23T11:28:54Z |
| Method | `celery call` — same safety-gated path as scheduler |
| Result | `{'skipped': True, 'reason': 'market_closed', 'next_open': '2026-06-23 09:30:00-04:00'}` |
| Duration | 0.53s |

**Critical finding:** Reason is `market_closed` — NOT `no_approved_strategies`.

This confirms:
1. `_filter_approved_strategies()` gate ran at line 512 ✅
2. S1/S4 with `approved=true` were ADMITTED by the gate ✅
3. Cycle continued to market check at line 533 ✅
4. Correct skip: US market closed at 07:28 EDT ✅
5. No strategy lifecycle mutation during cycle ✅

**Code path executed:**
```
run_portfolio_cycle()
  → credentials check (PASS)
  → registry.get_active_strategies() (S1, S4)
  → _filter_approved_strategies() (PASS — both approved=true)
  → TradingClient.get_clock() → is_open=False
  → return {'skipped': True, 'reason': 'market_closed'}
```

---

## 6. Decisions Summary

- **Decisions before dry-run:** 356 (all from 2026-06-18 sessions)
- **Decisions after dry-run:** 356 (unchanged — market_closed returned before decision loop)
- **New decisions from this cycle:** 0 (expected — market was closed)
- **All historical decisions have reasons:** ✅ (verified in preflight)
- **No live references in decisions:** ✅
- **No unexplained orders:** ✅

---

## 7. Order Lifecycle

- **Orders during dry-run cycle:** 0 (correct — market closed, cycle returned early)
- **Open trades in DB:** 16 (unchanged from preflight baseline)
- **No new paper orders placed:** ✅
- **No live orders placed:** ✅

⚠️ **R-13 (Pyramiding — acknowledged):** 16 open paper positions remain from prior sessions.
The BUG-5 fix (pyramiding guard) is now deployed. New cycles will NOT open additional positions
for symbols already in open trades. Existing positions pre-date the fix.

---

## 8. Readiness After Dry-Run

```json
{"redis_healthy":true,"redis_writeable":true,"db_healthy":true,
 "killswitch_active":false,"stale_signals":true,"worker_beat_lag":true,
 "last_signal_age_minutes":821.97,"last_cycle_age_minutes":6698.70}
```

All blocking flags: **GREEN** ✅

---

## 9. No-Live Confirmation

| Check | Result |
|-------|--------|
| ALPACA_BASE_URL | `https://paper-api.alpaca.markets` ✅ |
| API key prefix | PK (paper) ✅ |
| GLOBAL_LIVE_PROMOTION_ENABLED | False (hardcoded) ✅ |
| system:mode | paper ✅ |
| mode changed to live | NO ✅ |
| target_mode = live | NO (null) ✅ |
| live orders placed | NO ✅ |
| live credentials used | NO ✅ |
| S1/S4 promotion_blocked | True (unchanged) ✅ |
| S1/S4 live_authorized | False (unchanged) ✅ |
| kill-switch | false (unchanged) ✅ |

**Operator statement:** No live trading was authorized, initiated, or executed. The approval governance update is a controlled-paper-only gate change. GLOBAL_LIVE_PROMOTION_ENABLED remains False. No strategy was promoted to live.

---

## 10. Residual Risks

| Risk | Severity | Status |
|------|----------|--------|
| R-04 Soft CI gates (mypy/pip-audit) | MEDIUM | Open — accept for paper |
| R-05 LLM divergence fallbacks | MEDIUM | Open — accept for paper |
| R-07 Controlled paper not yet started | HIGH | Pending THIS PO sign-off |
| R-08 Live trading not authorized | CRITICAL | Not authorized ✅ |
| R-09 yfinance reliability | MEDIUM | Open — accept for paper |
| R-10 Telegram token rotation | MEDIUM | Open — accept for paper |
| R-11 Redis flush / kill-switch | HIGH | Monitor — accept for paper |
| R-13 Pyramiding (16 open positions) | HIGH | BUG-5 fixed; existing positions acknowledged |
| R-14 entry_price NULL on closed trades | HIGH | BUG-2 fixed (reconcile 7-day window) |
| R-15 Postmortem pipeline | MEDIUM | Unblocked by BUG-2 fix |
| stale_signals=true | LOW | System idle — will self-resolve at next ingestion run |
| S2 approved=true inconsistency | LOW | Pre-existing data artifact; S2 has no execution path |

---

## 11. Frontend Gaps Remaining

- **S4 not in strategies API**: S4 present in lifecycle+YAML but not in `STRATEGIES` dict in `src/api/routes/strategies.py`. Operator cannot see S4 status from frontend. Low priority for paper start.
- **Pre-existing ESLint issues**: ApiKeyModal.tsx, Layout.tsx, News.tsx — not safety-relevant.

---

## 12. Evidence Package

| Artifact | File | Status |
|----------|------|--------|
| PO approval evidence | `po_approval_evidence.md` | ✅ |
| Pre-approval lifecycle | `pre_approval_strategy_lifecycle.json` + `pre_approval_lifecycle.txt` | ✅ |
| SQL governance script | `approval_update.sql` | ✅ |
| SQL execution output | `approval_sql_output.txt` | ✅ |
| Post-approval lifecycle | `post_approval_lifecycle.txt` | ✅ |
| Approval diff | `approval_diff.md` | ✅ |
| Readiness before | `readiness_before.json` | ✅ |
| Readiness after approval | `readiness_after_approval.json` | ✅ |
| Decisions before | `decisions_before.json` | ✅ |
| Strategy status before | `strategy_status_before.json` | ✅ |
| Portfolio status before | `portfolio_status_before.json` | ✅ |
| Cycle trigger | `cycle_trigger.txt` | ✅ |
| Cycle output log | `cycle_output.log` | ✅ |
| Decisions after | `decisions_after.json` | ✅ |
| Readiness after dry-run | `readiness_after.json` | ✅ |
| No-live confirmation | `no_live_confirmation.txt` | ✅ |

---

## 13. Recommendation

The post-approval dry-run demonstrates that:

1. **S1/S4 now pass the approval gate** — cycle reaches `market_closed` instead of `no_approved_strategies`
2. **All promotion gates remain intact** — `promotion_blocked=True`, `live_authorized=False`, `GLOBAL_LIVE_PROMOTION_ENABLED=False`
3. **All safety checks pass** — kill-switch false, paper endpoint, no live orders
4. **BUG-2/4/5 fixes deployed** — reconcile window, signal_score visibility, pyramiding guard

**The system is ready for PO to authorize controlled paper trading Day 1.**

When market opens (2026-06-23 09:30 EDT = 13:30 UTC), the scheduled cycle will execute normally with S1/S4 admitted. The first real paper cycles will occur then, subject to market conditions and signal freshness.

---

## 14. AUTHORIZATION BLOCK — PO MUST COMPLETE

```
═══════════════════════════════════════════════════════════════════════════════
ALEMBIC — CONTROLLED PAPER TRADING DAY 1 AUTHORIZATION
═══════════════════════════════════════════════════════════════════════════════

Post-Approval Dry-Run Date:      2026-06-23 11:28 UTC
Dry-Run Task ID:                 95a6bfbc-752c-4d80-a82f-c7889aa08d0d
Dry-Run Result:                  SKIPPED (market_closed) — approval gate PASSED ✅
Approval Commit:                 (current HEAD — BUG-2/4/5 fixes + governance update)

Prior Preflight (reference):
  Preflight commit:              9e1039e
  Preflight evidence:            artifacts/controlled_paper_preflight_20260622_231510/

Environment:                     Alpaca paper (paper-api.alpaca.markets)
GLOBAL_LIVE_PROMOTION_ENABLED:   False ✅
Kill-switch:                     false ✅
DB / Redis:                      healthy ✅

Strategies authorized for controlled paper:
  [ ] S1 — supervised_paper (promotion_blocked=true, live_authorized=false)
  [ ] S4 — paper            (promotion_blocked=true, live_authorized=false)

Excluded strategies confirmed:
  [ ] S2 — disabled (NOT in scope)
  [ ] S7 — research/R&D (NOT in scope)

Residual risks R-04..R-15 reviewed by: ____________________________

R-13 pyramiding (16 open positions):       [ ] Acknowledged — risk accepted for paper
stale_signals=true at dry-run time:        [ ] Acknowledged — system idle, will self-resolve
S2 approved=true data inconsistency:       [ ] Acknowledged — no execution path

───────────────────────────────────────────────────────────────────────────────
AUTHORIZATION DECISIONS (PO MUST COMPLETE ALL)
───────────────────────────────────────────────────────────────────────────────

Controlled paper trading authorized?       [ ] YES   [ ] NO

Live trading authorized?                   [ ] NO    (must be NO — do not check YES)
Strategy promotions authorized?            [ ] NO    (must be NO — do not check YES)
GLOBAL_LIVE_PROMOTION_ENABLED remains False?  [x] YES  (this is fixed in code)

───────────────────────────────────────────────────────────────────────────────
PO Name:          ____________________________
PO Signature:     ____________________________
Date signed:      ____________________________
Conditions/notes: ____________________________
═══════════════════════════════════════════════════════════════════════════════
```
