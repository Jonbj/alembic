-- Migration 028: add signal_score column to execution_decisions
-- The existing 'score' column stores the portfolio allocation weight (e.g. 0.02 = 2%).
-- signal_score stores the actual LLM sentiment signal that drove the decision (e.g. +0.707).
-- Keeping both allows IC analysis: correlate signal_score with subsequent returns.
ALTER TABLE execution_decisions
    ADD COLUMN IF NOT EXISTS signal_score double precision;
