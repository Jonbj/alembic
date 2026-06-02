-- Migration 012: Multi-strategy risk reports table (T-602)
-- Created: 2026-06-02

CREATE TABLE IF NOT EXISTS risk_reports (
    id                      SERIAL PRIMARY KEY,
    timestamp               TIMESTAMPTZ NOT NULL DEFAULT now(),
    nav                     NUMERIC(18, 4),
    total_exposure          NUMERIC(8, 6),
    herfindahl_index        NUMERIC(8, 6),
    combined_drawdown       NUMERIC(8, 6),
    per_strategy_metrics    JSONB NOT NULL DEFAULT '{}',
    alerts                  JSONB NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_risk_reports_timestamp
    ON risk_reports (timestamp DESC);
