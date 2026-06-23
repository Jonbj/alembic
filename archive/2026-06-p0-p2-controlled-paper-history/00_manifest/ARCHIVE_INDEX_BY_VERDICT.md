# Archive Index by Verdict — 2026-06 P0/P2 Controlled Paper History

**Created:** 2026-06-23  

---

## P0_ACCEPTED_WITH_RUNTIME_MONITORING

**Date:** 2026-06-18  
**Source:** `archive/.../03_acceptance_audits/P0_ACCEPTANCE_AUDIT_2026-06-18.md`  
**Prior forensic basis:** `archive/.../02_external_reviews/FORENSIC_DAILY_REPORT_2026-06-17.md`  
**Remediation plan executed:** `archive/.../04_remediation_plans/ALEMBIC_REMEDIATION_MASTER_PLAN_2026-06-18.md`  
**Status:** CLOSED — all P0 items resolved

Key P0 issues resolved:
- BUG-1: same-bar fill bias
- BUG-2: reconcile window (24h → 7d)
- BUG-3: missing execution path
- BUG-4: signal_score missing from fetch_decisions
- BUG-5: pyramiding guard (open_db_symbols pre-fetch)
- FinBERT singleton (reload latency 108–242s fixed)

---

## P1_ACCEPTED_WITH_RUNTIME_MONITORING

**Date:** 2026-06-19  
**First audit:** `archive/.../03_acceptance_audits/P1_ACCEPTANCE_AUDIT_2026-06-19.md` — gaps found  
**Re-audit:** `archive/.../03_acceptance_audits/P1_RE_ACCEPTANCE_AUDIT_2026-06-19.md` — ACCEPTED  
**Status:** CLOSED — all 13 P1 items accepted, test suite 2321 passed at time of audit

---

## P2_ACCEPTED_WITH_RUNTIME_MONITORING

**Date:** 2026-06-21  
**Source:** `docs/P2_ACCEPTANCE_AUDIT_2026-06-21.md` ← **stays live** (referenced by Day 1 PO sign-off)  
**Status:** `docs/P2_STATUS_2026-06-21.md` — current status document  
**Status:** CLOSED — verdict P2_ACCEPTED_WITH_RUNTIME_MONITORING  
Full suite: 2412 passed, 1 skipped (confirmed post BUG-2/4/5 fixes)

---

## FRONTEND_F0_SAFETY_HYGIENE_PASS

**Date:** 2026-06-21/22  
**Source reviews:** `archive/.../05_frontend_reviews/FRONTEND_IMPACT_AND_CUSTOMER_JOURNEY_REVIEW_2026-06-21.md`  
**Opus review:** `archive/.../05_frontend_reviews/OPUS_REVIEW_OF_GLM_FRONTEND_IMPACT_REVIEW_2026-06-21.md`  
**Evidence:** `artifacts/controlled_paper_preflight_20260622_231510/frontend_safety_hygiene_verification.txt`  
**Status:** CLOSED — F0-1 (ModeBadge), F0-2 (kill-switch OTP), F0-3 (RiskParamWarning), F0-4 (StrategyAuthStatus) all implemented  
**Tests:** 10/10 frontend safety hygiene tests PASS

---

## PREFLIGHT_PASS_WITH_WARNINGS_READY_FOR_PO_REVIEW

**Date:** 2026-06-22  
**Primary evidence:** `artifacts/controlled_paper_preflight_20260622_231510/`  
**Key file:** `artifacts/controlled_paper_preflight_20260622_231510/PO_SIGNOFF_PACKAGE.md`  
**Prior preflight (superseded):** `artifacts/controlled_paper_preflight_20260621_105030/`  
**Status:** PASS WITH WARNINGS — warnings accepted by PO  

Warnings at preflight:
- `stale_signals=true` (system idle overnight — pre-market, acceptable)
- `worker_beat_lag=true` (outside market hours)
- Kill-switch rehearsal: PASS (full activate/halt/OTP-reset cycle)

---

## POST_APPROVAL_DRYRUN_PASS_WITH_WARNINGS_READY_FOR_PO_REVIEW

**Date:** 2026-06-23 11:28 UTC  
**Evidence:** `artifacts/controlled_paper_post_approval_dryrun_20260623_112242/`  
**Key file:** `artifacts/controlled_paper_post_approval_dryrun_20260623_112242/PO_FINAL_SIGNOFF_PACKAGE.md`  
**Task ID:** `95a6bfbc-752c-4d80-a82f-c7889aa08d0d`  
**Result:** `{'skipped': True, 'reason': 'market_closed'}` — NOT `no_approved_strategies`  
**Status:** PASS — S1/S4 approval gate VERIFIED (cycle reached market_closed, not no_approved_strategies)

S1/S4 `approved=true` governance update committed before this dry-run.
S2 `approved=false` cleanup executed on Day 1 launch.

---

## CONTROLLED_PAPER_DAY1_READY_WAITING_FOR_MARKET_OPEN

**Date:** 2026-06-23 11:50 UTC  
**Evidence directory:** `artifacts/controlled_paper_day1_20260623_114625/`  
**PO sign-off:** `artifacts/controlled_paper_day1_20260623_114625/PO_FINAL_SIGNOFF_RECORDED.md`  
**Start report:** `artifacts/controlled_paper_day1_20260623_114625/CONTROLLED_PAPER_DAY1_START_REPORT.md`  
**EOD template:** `artifacts/controlled_paper_day1_20260623_114625/CONTROLLED_PAPER_DAY1_EOD_TEMPLATE.md`  
**Status:** DAY 1 IN PROGRESS — market open 13:30 UTC, first cycle 14:07 UTC

Scope: S1 (supervised_paper, 50%), S4 (paper, 10%)
Excluded: S2, S3, S7
Non-authorizations: live trading, strategy promotion, GLOBAL_LIVE_PROMOTION_ENABLED, P3/P4

**EOD verdict:** To be filled after market close (~20:00 UTC 2026-06-23).
