-- Migration 023: add signal_score column to trades table
--
-- trades.score currently stores allocation_weight (e.g. 0.02 = 2% portfolio weight),
-- which makes IC, Sharpe and score-bucket analytics meaningless (constant input).
-- signal_score stores the actual LLM sentiment score that motivated the trade.

ALTER TABLE trades
    ADD COLUMN IF NOT EXISTS signal_score DOUBLE PRECISION;
