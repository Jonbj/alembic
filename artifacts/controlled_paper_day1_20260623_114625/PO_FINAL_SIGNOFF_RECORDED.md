# ALEMBIC — PO FINAL SIGN-OFF RECORDED
# Controlled Paper Trading Day 1

**Document type:** PO Final Sign-Off (Recorded)
**Date/Time (UTC):** 2026-06-23 11:46 UTC
**Evidence directory:** `artifacts/controlled_paper_day1_20260623_114625/`
**Prior preflight:** `artifacts/controlled_paper_preflight_20260622_231510/`
**Prior post-approval dry-run:** `artifacts/controlled_paper_post_approval_dryrun_20260623_112242/`
**PO Name:** Jonbj (Stefano Delgobbo — stefano.delgobbo@gmail.com)
**PO Signature:** *(explicit operational instruction — task message 2026-06-23)*
**Date signed:** 2026-06-23 11:46 UTC

---

## Authorization Source

The PO (Jonbj / Stefano Delgobbo) has provided explicit operational authorization via the
Controlled Paper Day 1 Launch task message on 2026-06-23, which states:

> "Il PO approva il Controlled Paper Day 1 per:
>   Scope: S1 + S4 only.
>   Environment: Alpaca paper only.
>   Live trading: NO.
>   Strategy live promotion: NO.
>   GLOBAL_LIVE_PROMOTION_ENABLED must remain False.
>   P3/P4: NO.
>   S2/S3/S7: excluded."

---

## Evidence Chain

| Step | Date | Verdict | Evidence |
|------|------|---------|---------|
| P2 Acceptance Audit | 2026-06-21 | P2_ACCEPTED_WITH_RUNTIME_MONITORING | `docs/P2_ACCEPTANCE_AUDIT_2026-06-21.md` |
| Controlled Paper Preflight | 2026-06-22 | PREFLIGHT_PASS_WITH_WARNINGS_READY_FOR_PO_REVIEW | `artifacts/controlled_paper_preflight_20260622_231510/` |
| Post-Approval Dry-Run | 2026-06-23 11:28 UTC | POST_APPROVAL_DRYRUN_PASS_WITH_WARNINGS_READY_FOR_PO_REVIEW | `artifacts/controlled_paper_post_approval_dryrun_20260623_112242/` |
| S1/S4 Approval Gate | 2026-06-23 11:24 UTC | approved=true both | dry-run result: `market_closed` (not `no_approved_strategies`) |
| BUG-2/4/5 Fixes | 2026-06-23 | All 2412 tests pass | reconcile 7d, signal_score visible, pyramiding guard |
| Kill-Switch Rehearsal | 2026-06-22 | PASS | `killswitch_reset.json` |
| Frontend Safety Hygiene | 2026-06-22 | PASS 10/10 tests | `frontend_safety_hygiene_verification.txt` |

---

## Authorization Decisions (PO CONFIRMED)

**Controlled Paper Day 1 authorized:**
- [x] **YES**

**Scope:**
- [x] **S1** — supervised_paper
- [x] **S4** — paper
- [ ] S2 — excluded (disabled)
- [ ] S3 — excluded (not in lifecycle)
- [ ] S7 — excluded (R&D only)

**Live trading authorization:**
- [x] **NO** — live trading is NOT authorized

**Strategy live promotion authorization:**
- [x] **NO** — strategy live promotion is NOT authorized

**GLOBAL_LIVE_PROMOTION_ENABLED remains False:**
- [x] **YES** — hardcoded in `src/strategies/promotion.py`, not in .env

**PO accepts the following warnings:**
- [x] Prior dry-run skipped for `market_closed` (not `no_approved_strategies`) — correct behavior
- [x] `stale_signals=true` at sign-off time (pre-market, ~14h idle) — must clear before first paper cycle during market hours
- [x] `worker_beat_lag=true` at sign-off time (pre-market) — must clear during market hours
- [x] R-13: 16 existing open positions acknowledged — BUG-5 pyramiding guard deployed
- [x] S2 `approved=true` inconsistency — cleanup to be performed at Day 1 (approved=false, mode stays disabled)
- [x] S4 not in strategies API — non-blocking, tracked for future transparency improvement

---

## What This Authorization Does NOT Include

| Item | Status |
|------|--------|
| Live trading | ❌ NOT authorized |
| Strategy live promotion | ❌ NOT authorized |
| GLOBAL_LIVE_PROMOTION_ENABLED=True | ❌ NOT authorized |
| S2/S3/S7 paper or live | ❌ NOT authorized |
| P3/P4 | ❌ NOT started |
| mode change to live | ❌ NOT authorized |
| promotion_blocked removal | ❌ NOT authorized |
| live_authorized=true | ❌ NOT authorized |
| promotion_authorized=true | ❌ NOT authorized |
