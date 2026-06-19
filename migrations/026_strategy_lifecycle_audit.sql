-- Migration 026: strategy_lifecycle_audit — immutable audit trail for mode transitions.
--
-- Every call to request_promotion(), approve_promotion(), or demote_strategy()
-- inserts a row here. The table is append-only (no UPDATE/DELETE).
--
-- action values:
--   'requested'  — request_promotion() called; target_mode + gate_report_id set
--   'approved'   — approve_promotion() called; mode flipped to target_mode
--   'demoted'    — demote_strategy() called; mode decreased
--   'blocked'    — request_promotion() rejected (PromotionBlockedError raised)

CREATE TABLE IF NOT EXISTS strategy_lifecycle_audit (
    id              BIGSERIAL   NOT NULL PRIMARY KEY,
    strategy_id     TEXT        NOT NULL,
    from_mode       TEXT        NOT NULL,
    to_mode         TEXT        NOT NULL,
    action          TEXT        NOT NULL
                    CHECK (action IN ('requested', 'approved', 'demoted', 'blocked')),
    actor           TEXT        NOT NULL,
    reason          TEXT        NULL,
    gate_report_id  TEXT        NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_slaudit_strategy ON strategy_lifecycle_audit (strategy_id, created_at DESC);
