-- ═══════════════════════════════════════════════════════════════════════════
-- ALEMBIC — Controlled Paper Approval Governance SQL
-- ═══════════════════════════════════════════════════════════════════════════
--
-- Purpose:    Set approved=true for S1/S4 to allow controlled paper cycles.
-- Scope:      Controlled paper path ONLY. NOT a live promotion.
-- Authority:  Explicit PO operational instruction — 2026-06-23 (Jonbj / Stefano Delgobbo)
-- Reference:  artifacts/controlled_paper_preflight_20260622_231510/PO_SIGNOFF_PACKAGE.md
--             (PO unblocked this step via operational context instruction)
--
-- ── WHAT THIS DOES ───────────────────────────────────────────────────────
--   Sets approved=true for S1 and S4 only.
--   Does NOT change mode, target_mode, promoted_by, promoted_at, or gate_report_id.
--   Does NOT affect S2, S3, S7.
--   Does NOT enable GLOBAL_LIVE_PROMOTION_ENABLED.
--   Does NOT constitute a live promotion.
--   promotion_blocked=true remains enforced in the application layer.
--
-- ── WHAT THIS DOES NOT DO ────────────────────────────────────────────────
--   NOT live promotion
--   NOT live trading authorization
--   NOT P3/P4
--   NOT GLOBAL_LIVE_PROMOTION_ENABLED=True
-- ═══════════════════════════════════════════════════════════════════════════

BEGIN;

UPDATE strategy_lifecycle
SET    approved   = true,
       updated_at = CURRENT_TIMESTAMP
WHERE  strategy_id IN ('S1', 'S4');

-- Verify: only approved column and updated_at changed; mode/target_mode/live flags unchanged
SELECT strategy_id, mode, target_mode, approved, updated_at
FROM   strategy_lifecycle
ORDER  BY strategy_id;

COMMIT;
