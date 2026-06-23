# Restore Notes — Archive 2026-06 P0/P2

**Purpose:** How to find, use, and restore historical documents from this archive.

---

## Finding a Historical Report

All files in this archive are readable in-place via git. Navigate by category:

```
archive/2026-06-p0-p2-controlled-paper-history/
├── 00_manifest/          # This index + restore notes
├── 01_initial_specs/     # Design specs, alembic_v2 docs, superpowers specs
├── 02_external_reviews/  # Code reviews, forensic reports, LLM audits
├── 03_acceptance_audits/ # P0 and P1 acceptance audits
├── 04_remediation_plans/ # Remediation plans and memos
├── 05_frontend_reviews/  # Frontend safety reviews (F0 closed)
├── 06_preflight_and_day1_history/  # Pointer to artifacts (in-place)
├── 07_pasted_raw_inputs/ # Raw prompt templates
├── 08_superseded_docs/   # Analysis and evaluation docs, stale references
└── 09_legacy_reports/    # Old plans, stale claude-memory
```

To find a file: use `git log --diff-filter=R --find-renames -- <old-path>` to trace
where any file was moved.

---

## Restoring a File

All files were moved with `git mv`, so they appear as renames in git history.
To restore a file to its original location:

```bash
# Find where it was moved from (example):
git log --diff-filter=R --name-status -- docs/P0_ACCEPTANCE_AUDIT_2026-06-18.md

# Restore to original location with git mv:
git mv archive/2026-06-p0-p2-controlled-paper-history/03_acceptance_audits/P0_ACCEPTANCE_AUDIT_2026-06-18.md \
       docs/P0_ACCEPTANCE_AUDIT_2026-06-18.md
git commit -m "restore: P0_ACCEPTANCE_AUDIT to docs/"
```

Alternatively, just read the file from its archive path — it is fully readable there.

---

## Files That Must NOT Be Used as Current Truth

| File | Reason |
|------|--------|
| `03_acceptance_audits/P1_ACCEPTANCE_AUDIT_2026-06-19.md` | First P1 pass — gaps existed; use RE_ACCEPTANCE |
| `04_remediation_plans/ALEMBIC_REMEDIATION_MASTER_PLAN_2026-06-18.md` | Historical plan — all items executed |
| `08_superseded_docs/paper_trading_log.md` | Old 90-day clock from 2026-06-05 — superseded by Day 1 2026-06-23 |
| `09_legacy_reports/MEMORY.md` | Stale local memory snapshot — see `~/.claude/projects/` for active memory |
| Any file under `01_initial_specs/alembic_v2/` | v2 design, allocations differ from current config |

---

## Files Superseded by Current Docs

| Archived | Current Canonical |
|----------|------------------|
| `01_initial_specs/01_strategy_design.md` | `config/strategies.yaml` + `docs/strategies.md` |
| `01_initial_specs/05_validation_and_gates.md` | `docs/P2_ACCEPTANCE_AUDIT_2026-06-21.md` |
| `09_legacy_reports/2026-06-15-alpaca-feature-roadmap.md` | `docs/superpowers/plans/2026-06-16-master-roadmap.md` |
| `09_legacy_reports/2026-06-16-signal-improvements.md` | `docs/superpowers/plans/2026-06-16-master-roadmap.md` |
| `08_superseded_docs/models.md` | `docs/llm-config.md` |

---

## Source of Truth for Day 1 / Day 2

| Need | File |
|------|------|
| Current system status | `docs/P2_STATUS_2026-06-21.md` |
| Current risk register | `docs/RESIDUAL_RISK_REGISTER.md` |
| Day 1 active evidence | `artifacts/controlled_paper_day1_20260623_114625/` |
| Day 1 PO sign-off | `artifacts/controlled_paper_day1_20260623_114625/PO_FINAL_SIGNOFF_RECORDED.md` |
| Day 1 start report | `artifacts/controlled_paper_day1_20260623_114625/CONTROLLED_PAPER_DAY1_START_REPORT.md` |
| Day 1 EOD template | `artifacts/controlled_paper_day1_20260623_114625/CONTROLLED_PAPER_DAY1_EOD_TEMPLATE.md` |
| Preflight evidence | `artifacts/controlled_paper_preflight_20260622_231510/` |
| Post-approval dry-run | `artifacts/controlled_paper_post_approval_dryrun_20260623_112242/` |
| P2 acceptance audit | `docs/P2_ACCEPTANCE_AUDIT_2026-06-21.md` |
| Preflight runbook | `docs/CONTROLLED_PAPER_PREFLIGHT_RUNBOOK_2026-06-21.md` |
| Master roadmap | `docs/superpowers/plans/2026-06-16-master-roadmap.md` |
| API reference | `docs/API.md` |
| Operations guide | `docs/operations.md` |
| Deployment guide | `docs/deployment.md` |

---

## What Was Not Archived

- All source code (`src/`, `tests/`, `frontend/`)
- All config files (`config/`)
- All migrations (`migrations/`)
- All active evidence (`artifacts/`)
- All live documentation (`docs/API.md`, `docs/ARCHITECTURE.md`, etc.)
- `docs/P2_ACCEPTANCE_AUDIT_2026-06-21.md` (referenced by Day 1 PO sign-off)
- `docs/superpowers/plans/2026-06-16-master-roadmap.md` (SOURCE OF TRUTH per CLAUDE.md)

---

## Authorization Status at Archive Date

- Live trading: **NOT authorized**
- Strategy live promotion: **NOT authorized**
- `GLOBAL_LIVE_PROMOTION_ENABLED`: **False** (hardcoded)
- S1/S4: paper only, `promotion_blocked=true`, `live_authorized=false`
- S2/S3/S7: excluded from controlled paper
- P3/P4: **NOT started**
