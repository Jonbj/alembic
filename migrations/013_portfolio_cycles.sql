-- Migration 013: Portfolio cycles table (T-604)
-- Created: 2026-06-02

CREATE TABLE IF NOT EXISTS portfolio_cycles (
    id                  SERIAL PRIMARY KEY,
    timestamp           TIMESTAMPTZ NOT NULL DEFAULT now(),
    strategies_run      JSONB NOT NULL DEFAULT '[]',
    orders_count        INTEGER NOT NULL DEFAULT 0,
    constraints_fired   JSONB NOT NULL DEFAULT '[]',
    final_orders        JSONB NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_portfolio_cycles_timestamp
    ON portfolio_cycles (timestamp DESC);
