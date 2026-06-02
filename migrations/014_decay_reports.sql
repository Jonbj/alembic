-- Migration 014: Decay reports table (T-605)
-- Created: 2026-06-02

CREATE TABLE IF NOT EXISTS decay_reports (
    id              SERIAL PRIMARY KEY,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT now(),
    strategy_id    TEXT NOT NULL,
    metric          TEXT NOT NULL CHECK (metric IN ('ic', 'hit_rate', 'sharpe', 'max_drawdown')),
    baseline_value  DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    actual_value    DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    decay_score     DOUBLE PRECISION NOT NULL DEFAULT 0.0 CHECK (decay_score >= 0 AND decay_score <= 1),
    alert_level     TEXT NOT NULL CHECK (alert_level IN ('NORMAL', 'WARNING', 'CRITICAL')),
    notes           JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_decay_reports_strategy_timestamp
    ON decay_reports (strategy_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_decay_reports_alert_level
    ON decay_reports (alert_level) WHERE alert_level != 'NORMAL';