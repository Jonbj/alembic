# Preflight & Day 1 Evidence — Pointer

All preflight, post-approval, and Day 1 controlled paper evidence remains **in-place**
under `artifacts/` to preserve references from the PO Final Sign-Off documents.

## Evidence Directories (in-place)

| Directory | Verdict / Purpose |
|-----------|-------------------|
| `artifacts/controlled_paper_preflight_20260621_105030/` | First preflight run (superseded by 0622 run) |
| `artifacts/controlled_paper_preflight_20260622_231510/` | **Canonical preflight** — PREFLIGHT_PASS_WITH_WARNINGS_READY_FOR_PO_REVIEW |
| `artifacts/controlled_paper_post_approval_dryrun_20260623_112242/` | **Post-approval dry-run** — POST_APPROVAL_DRYRUN_PASS — S1/S4 approval gate VERIFIED |
| `artifacts/controlled_paper_day1_20260623_114625/` | **ACTIVE DAY 1 EVIDENCE** — do not move |

## Key Reference Chain

```
PO_FINAL_SIGNOFF_RECORDED.md
  → docs/P2_ACCEPTANCE_AUDIT_2026-06-21.md          (stays in docs/)
  → artifacts/controlled_paper_preflight_20260622_231510/
  → artifacts/controlled_paper_post_approval_dryrun_20260623_112242/
```

## Do Not Move

These directories are referenced by live PO sign-off documents. Moving them would
break the evidence chain for the Day 1 controlled paper audit trail.
