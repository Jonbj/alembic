-- Migration 002: Weight update audit trail for Fase 2 approval loop
-- Created: 2026-05-05

CREATE TABLE IF NOT EXISTS weight_update_log (
    id                SERIAL PRIMARY KEY,
    applied_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    source            VARCHAR(20) NOT NULL
                          CHECK (source IN ('suggestion', 'override', 'expired')),
    applied_weights   JSONB NOT NULL,
    suggested_weights JSONB,
    purified_icir     JSONB,
    freeze_reason     TEXT,
    note              TEXT,
    approved_by       TEXT  -- SHA-256[:8] of the API key, never raw
);

CREATE INDEX IF NOT EXISTS idx_weight_log_applied_at
    ON weight_update_log (applied_at DESC);
