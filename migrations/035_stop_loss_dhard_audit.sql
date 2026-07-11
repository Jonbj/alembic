-- Migration 035: d_hard audit logging for fractionable positions
-- Adds broker disaster-stop columns to stop_shadow_log so fractionable positions
-- (which cannot carry Alpaca bracket stops) still leave a per-cycle audit trail.

ALTER TABLE stop_shadow_log
    ADD COLUMN IF NOT EXISTS d_hard          DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS d_hard_trigger  DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS d_hard_breached   BOOLEAN;
