# Archive Manifest — 2026-06 P0/P2 Controlled Paper History

**Created:** 2026-06-23  
**Commit at archiving:** 99c14a7 (+ this cleanup commit)  
**Archived by:** Repository maintainer (documentation cleanup)

---

## Purpose

These files are maintained for audit, historical reference, and traceability.
They are **not** current operational documents.

All P0/P1/P2 phases are complete. The system is in **Controlled Paper Day 1** state.
Live trading is NOT authorized. Strategy promotions are NOT authorized.
`GLOBAL_LIVE_PROMOTION_ENABLED` remains `False`.

---

## Current Live Documents (NOT archived)

| File | Purpose |
|------|---------|
| `README.md` | Project overview |
| `CLAUDE.md` | Agent operating guide |
| `AGENT.md` | API agent briefing |
| `CONTRIBUTING.md` | Developer guide |
| `DECISIONS.md` | Operational decisions log |
| `docs/API.md` | API reference |
| `docs/ARCHITECTURE.md` | System architecture |
| `docs/operations.md` | Operations guide |
| `docs/deployment.md` | Deployment guide |
| `docs/FRONTEND_OPERATOR_GUIDE.md` | Frontend operator reference |
| `docs/RESIDUAL_RISK_REGISTER.md` | Active risk register |
| `docs/P2_STATUS_2026-06-21.md` | Current P2 status |
| `docs/P2_ACCEPTANCE_AUDIT_2026-06-21.md` | **Referenced by Day 1 PO sign-off — must stay** |
| `docs/CONTROLLED_PAPER_PREFLIGHT_RUNBOOK_2026-06-21.md` | Active runbook |
| `docs/strategies.md` | Strategy reference |
| `docs/user_guide.md` | User guide |
| `docs/llm-config.md` | LLM ensemble config |
| `docs/CHANGELOG.md` | Ongoing change log |
| `docs/strategies/s7-pead.md` | S7 strategy spec (R&D) |
| `docs/superpowers/plans/2026-06-16-master-roadmap.md` | SOURCE OF TRUTH roadmap |
| `artifacts/controlled_paper_day1_20260623_114625/` | **ACTIVE Day 1 evidence** |
| `artifacts/controlled_paper_preflight_20260622_231510/` | Active evidence (referenced by PO sign-off) |
| `artifacts/controlled_paper_post_approval_dryrun_20260623_112242/` | Active evidence (referenced by PO sign-off) |
| `artifacts/controlled_paper_preflight_20260621_105030/` | First preflight (kept in place) |

---

## Archived Files

### 01_initial_specs — Initial Design Specifications

| Original Path | Category | Date | Notes |
|--------------|----------|------|-------|
| `docs/alembic_v2/00_README.md` | Initial spec | 2026-05-22 | v2 system design — superseded by current implementation |
| `docs/alembic_v2/01_strategy_design.md` | Initial spec | 2026-05-22 | Strategy design doc v2 — allocations differ from current config |
| `docs/alembic_v2/05_validation_and_gates.md` | Initial spec | 2026-05-22 | Gates doc v2 — superseded by P0/P1/P2 audits |
| `docs/alembic_v2/files_prodotto.zip` | Initial spec bundle | 2026-05-22 | Original v2 spec bundle |
| `docs/superpowers/specs/2026-05-03-trading-system-design.md` | Design spec | 2026-05-03 | Original trading system design |
| `docs/superpowers/specs/2026-05-04-gdelt-ab-test-design.md` | Design spec | 2026-05-04 | GDELT A/B test |
| `docs/superpowers/specs/2026-05-05-auto-apply-weights-design.md` | Design spec | 2026-05-05 | Auto-apply weights |
| `docs/superpowers/specs/2026-05-05-regime-detector-design.md` | Design spec | 2026-05-05 | Regime detector |
| `docs/superpowers/specs/2026-05-05-telegram-approval-flow-design.md` | Design spec | 2026-05-05 | Telegram flow |
| `docs/superpowers/specs/2026-05-05-weight-approval-loop-design.md` | Design spec | 2026-05-05 | Weight approval |
| `docs/superpowers/specs/2026-05-13-gkg-backtest-design.md` | Design spec | 2026-05-13 | GKG backtest |
| `docs/superpowers/specs/2026-05-13-multi-asset-news-driven-design.md` | Design spec | 2026-05-13 | Multi-asset |
| `docs/superpowers/specs/2026-05-18-frontend-design.md` | Design spec | 2026-05-18 | Frontend design |
| `docs/superpowers/specs/2026-05-26-backtest-inference-optimization-design.md` | Design spec | 2026-05-26 | Backtest opt |
| `docs/superpowers/specs/2026-06-04-smallmid-watchlist-design.md` | Design spec | 2026-06-04 | Small/mid cap |
| `docs/superpowers/specs/2026-06-05-trade-observability-design.md` | Design spec | 2026-06-05 | Observability |
| `docs/superpowers/specs/2026-06-06-trade-analytics-engine-design.md` | Design spec | 2026-06-06 | Analytics engine |
| `docs/superpowers/specs/2026-06-07-trade-cost-realism-design.md` | Design spec | 2026-06-07 | Cost realism |

### 02_external_reviews — External / LLM Reviews

| Original Path | Category | Date | Verdict / Status |
|--------------|----------|------|-----------------|
| `docs/CODE_REVIEW_FULL_2026-06-15.md` | Code review | 2026-06-15 | Full code review pre-P0 |
| `docs/FORENSIC_DAILY_REPORT_2026-06-17.md` | Forensic report | 2026-06-17 | P0 forensic — basis for remediation plan |
| `docs/FUNCTIONAL_QUANT_PRODUCT_REVIEW_2026-06-17.md` | Functional review | 2026-06-17 | P0 era review |
| `docs/KIMI_TECHNICAL_VERIFICATION_MATRIX_2026-06-18.md` | External verification | 2026-06-18 | Kimi K2 verification matrix |
| `docs/OPUS_REVIEW_OF_KIMI_TECHNICAL_VERIFICATION_2026-06-18.md` | External review | 2026-06-18 | Opus review of Kimi matrix |
| `docs/TECHNICAL_CODE_REVIEW_2026-06-18.md` | Technical review | 2026-06-18 | Technical code review |

### 03_acceptance_audits — P0/P1 Acceptance Audits

| Original Path | Category | Date | Verdict |
|--------------|----------|------|---------|
| `docs/P0_ACCEPTANCE_AUDIT_2026-06-18.md` | P0 audit | 2026-06-18 | P0_ACCEPTED_WITH_RUNTIME_MONITORING |
| `docs/P1_ACCEPTANCE_AUDIT_2026-06-19.md` | P1 audit | 2026-06-19 | P1 first pass (gaps identified) |
| `docs/P1_RE_ACCEPTANCE_AUDIT_2026-06-19.md` | P1 re-audit | 2026-06-19 | P1_ACCEPTED_WITH_RUNTIME_MONITORING |

**Note:** `docs/P2_ACCEPTANCE_AUDIT_2026-06-21.md` is **NOT** archived — it is referenced directly by the Day 1 PO Final Sign-Off package and must remain at its original path.

### 04_remediation_plans — Remediation Plans & Memos

| Original Path | Category | Date | Status |
|--------------|----------|------|--------|
| `docs/ALEMBIC_REMEDIATION_MASTER_PLAN_2026-06-18.md` | Master plan | 2026-06-18 | EXECUTED — all P0/P1/P2 items closed |
| `docs/OPUS_FUNCTIONAL_REMEDIATION_BLUEPRINT_2026-06-18.md` | Blueprint | 2026-06-18 | Executed / superseded by master plan |
| `docs/OPUS_QUANT_TRADING_VALIDITY_MEMO_2026-06-18.md` | Validity memo | 2026-06-18 | Basis for P0 scope; executed |

### 05_frontend_reviews — Frontend Safety Reviews (F0 closed)

| Original Path | Category | Date | Verdict |
|--------------|----------|------|---------|
| `docs/FRONTEND_IMPACT_AND_CUSTOMER_JOURNEY_REVIEW_2026-06-21.md` | Frontend review | 2026-06-21 | F0-1/F0-3 PASS (implemented) |
| `docs/OPUS_REVIEW_OF_GLM_FRONTEND_IMPACT_REVIEW_2026-06-21.md` | Review of review | 2026-06-21 | F0 closed — F0-1/F0-3 safety hygiene complete |
| `docs/frontend-review-plan.md` | Review plan | pre-2026-06-21 | Superseded — review executed |

### 07_pasted_raw_inputs — Prompt Templates & Raw Inputs

| Original Path | Category | Notes |
|--------------|----------|-------|
| `docs/REVIEW-PROMPT.md` | Prompt template | LLM review prompt, 2026-05-04 — historical |

### 08_superseded_docs — Superseded Analysis Docs

| Original Path | Category | Date | Why Superseded |
|--------------|----------|------|---------------|
| `docs/entry_threshold_analysis.md` | Analysis | 2026-06-04 | Threshold analysis pre-P0 — superseded by current trading config |
| `docs/news-api-evaluation-2026.md` | Evaluation | 2026-05-16 | News API eval — decision made, not action item |
| `docs/paper_trading_log.md` | Log | 2026-06-05 | 90-day clock from 2026-06-05 superseded — Day 1 is now 2026-06-23 |
| `docs/model-tournament-workflow.md` | Workflow | pre-2026-06 | Tool workflow doc — not current operational process |
| `models.md` (root) | Reference | 2026-05-06 | Stale model list — see docs/llm-config.md for current models |

### 09_legacy_reports — Legacy Plans & Stale Memory

| Original Path | Category | Date | Notes |
|--------------|----------|------|-------|
| `docs/superpowers/plans/2026-06-15-alpaca-feature-roadmap.md` | Plan | 2026-06-15 | Incorporated into master roadmap |
| `docs/superpowers/plans/2026-06-16-signal-improvements.md` | Plan | 2026-06-16 | Incorporated into master roadmap |
| `docs/claude-memory/MEMORY.md` | Stale memory | pre-2026-06-17 | Stale local memory snapshot — active memory is in ~/.claude/projects/ |
| `docs/claude-memory/project_trading_system.md` | Stale memory | pre-2026-06-17 | Stale |
| `docs/claude-memory/project_pending_reviews.md` | Stale memory | pre-2026-06-17 | Stale |
| `docs/claude-memory/project_multiasset_brainstorm.md` | Stale memory | pre-2026-06-17 | Stale |
| `docs/claude-memory/README.md` | Memory readme | pre-2026-06-17 | Stale |

---

## Important Verdict Timeline

| Date | Verdict | Evidence |
|------|---------|---------|
| 2026-06-18 | P0_ACCEPTED_WITH_RUNTIME_MONITORING | `03_acceptance_audits/P0_ACCEPTANCE_AUDIT_2026-06-18.md` |
| 2026-06-19 | P1_ACCEPTED_WITH_RUNTIME_MONITORING | `03_acceptance_audits/P1_RE_ACCEPTANCE_AUDIT_2026-06-19.md` |
| 2026-06-21 | P2_ACCEPTED_WITH_RUNTIME_MONITORING | `docs/P2_ACCEPTANCE_AUDIT_2026-06-21.md` (live) |
| 2026-06-21 | F0-1/F0-3 frontend safety hygiene PASS | `05_frontend_reviews/FRONTEND_IMPACT_AND_CUSTOMER_JOURNEY_REVIEW_2026-06-21.md` |
| 2026-06-22 | PREFLIGHT_PASS_WITH_WARNINGS_READY_FOR_PO_REVIEW | `artifacts/controlled_paper_preflight_20260622_231510/` |
| 2026-06-23 | POST_APPROVAL_DRYRUN_PASS_WITH_WARNINGS | `artifacts/controlled_paper_post_approval_dryrun_20260623_112242/` |
| 2026-06-23 | PO Final Sign-Off recorded | `artifacts/controlled_paper_day1_20260623_114625/PO_FINAL_SIGNOFF_RECORDED.md` |
| 2026-06-23 | CONTROLLED_PAPER_DAY1_READY_WAITING_FOR_MARKET_OPEN | `artifacts/controlled_paper_day1_20260623_114625/CONTROLLED_PAPER_DAY1_START_REPORT.md` |

---

## Non-Authorizations (valid as of archive date)

- **Live trading**: NOT authorized
- **Strategy live promotion**: NOT authorized
- **GLOBAL_LIVE_PROMOTION_ENABLED**: remains `False` (hardcoded in `src/strategies/promotion.py`)
- **promotion_blocked**: True for S1/S4
- **live_authorized**: False for S1/S4
- **P3/P4**: NOT started
- **S2/S3/S7**: NOT in controlled paper scope
