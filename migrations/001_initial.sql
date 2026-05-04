-- Migration 001: Initial schema for LLM Trading System
-- Created: 2026-05-03
--
-- FIX: Removed duplicate 'action' column definition in audit_log table.
-- Original bug had:
--   action VARCHAR(50),   -- first definition
--   ...
--   action audit_action_enum NOT NULL   -- second definition (duplicate!)
--
-- Fixed: Use single definition with proper enum type.

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enum types
CREATE TYPE audit_action_enum AS ENUM (
    'INSERT',
    'UPDATE',
    'DELETE',
    'SELECT',
    'KILLSWITCH_ACTIVATE',
    'KILLSWITCH_DEACTIVATE',
    'ENSEMBLE_DIVERGENCE',
    'FALLBACK_TRIGGERED',
    'BUDGET_EXHAUSTED',
    'DRIFT_DETECTED'
);

CREATE TYPE drift_level_enum AS ENUM (
    'STABLE',
    'YELLOW',
    'RED'
);

-- Sentiment signals table
-- Stores LLM ensemble and FinBERT fallback signals
CREATE TABLE IF NOT EXISTS sentiment_signals (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    score DOUBLE PRECISION NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    reasoning TEXT,
    model_id VARCHAR(50) NOT NULL,
    ensemble_std DOUBLE PRECISION DEFAULT 0.0,
    fallback_used BOOLEAN DEFAULT FALSE,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    forward_return DOUBLE PRECISION,  -- Added by migration 002, nullable here
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Unique constraint to prevent duplicate signals for same symbol/time
    CONSTRAINT unique_signal_per_symbol_time
        UNIQUE (symbol, generated_at)
);

-- Index for time-range queries (IC calculation, backtest)
-- Using BRIN for efficient range scans on large tables
-- Note: For tables < 100k rows, B-tree may be more efficient
CREATE INDEX IF NOT EXISTS idx_sentiment_time_brin
    ON sentiment_signals USING BRIN (generated_at);

-- Index for symbol + time lookups
CREATE INDEX IF NOT EXISTS idx_sentiment_symbol_time
    ON sentiment_signals (symbol, generated_at DESC);

-- Performance metrics table
-- Stores daily IC, ICIR, weights, and drift metrics
CREATE TABLE IF NOT EXISTS performance_metrics (
    id BIGSERIAL PRIMARY KEY,
    metric_date DATE NOT NULL UNIQUE,
    composite_ic DOUBLE PRECISION,
    icir DOUBLE PRECISION,
    model_weights JSONB NOT NULL DEFAULT '{}'::jsonb,
    psi_90d DOUBLE PRECISION,
    psi_12m DOUBLE PRECISION,
    drift_level drift_level_enum DEFAULT 'STABLE',
    consecutive_negative_ic_days INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Audit log table
-- FIX: Single 'action' column definition with enum type
-- ENHANCED: Added ip_address, request_id, table_name, record_id, old_value, new_value
-- for forensic-ready audit trail
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    action audit_action_enum NOT NULL,
    table_name VARCHAR(50),
    record_id BIGINT,
    old_value JSONB,
    new_value JSONB,
    details JSONB,
    user_id VARCHAR(50) NOT NULL DEFAULT 'system',
    ip_address INET,
    request_id UUID DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_action
    ON audit_log (action);

CREATE INDEX IF NOT EXISTS idx_audit_time
    ON audit_log (created_at DESC);

-- LLM budget tracking table
-- Tracks daily spending on LLM API calls
CREATE TABLE IF NOT EXISTS llm_budget (
    id BIGSERIAL PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    total_spent_usd DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    token_count_input INTEGER NOT NULL DEFAULT 0,
    token_count_output INTEGER NOT NULL DEFAULT 0,
    budget_exhausted BOOLEAN NOT NULL DEFAULT FALSE,
    exhausted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_budget_date
    ON llm_budget (date DESC);

-- Fallback counter table
-- Tracks consecutive ensemble fallbacks for circuit breaker
CREATE TABLE IF NOT EXISTS fallback_counters (
    id BIGSERIAL PRIMARY KEY,
    counter_name VARCHAR(50) NOT NULL UNIQUE,
    counter_value INTEGER NOT NULL DEFAULT 0,
    last_increment_at TIMESTAMPTZ,
    reset_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fallback_counter_name
    ON fallback_counters (counter_name);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for updated_at
CREATE TRIGGER update_performance_metrics_updated_at
    BEFORE UPDATE ON performance_metrics
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_llm_budget_updated_at
    BEFORE UPDATE ON llm_budget
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_fallback_counters_updated_at
    BEFORE UPDATE ON fallback_counters
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Initial budget row for today (will be upserted daily)
-- INSERT INTO llm_budget (date, total_spent_usd)
-- VALUES (CURRENT_DATE, 0.0)
-- ON CONFLICT (date) DO NOTHING;

COMMENT ON TABLE sentiment_signals IS 'Stores LLM ensemble and FinBERT fallback signals for all symbols';
COMMENT ON TABLE performance_metrics IS 'Daily aggregated performance metrics including IC, ICIR, and drift detection';
COMMENT ON TABLE audit_log IS 'Audit trail for all system actions and state changes';
COMMENT ON TABLE llm_budget IS 'Daily tracking of LLM API spending against budget';
COMMENT ON TABLE fallback_counters IS 'Counters for circuit breaker logic (consecutive fallbacks, etc.)';
