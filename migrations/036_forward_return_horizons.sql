-- 036_forward_return_horizons.sql
-- Multi-horizon forward returns for sentiment_signals (S4 measurement foundation).
-- forward_return stays the 1-day horizon (backward compatible); 3d/5d are new.
-- Horizons are TRADING days (T+3, T+5 vs T close), computed by
-- run_forward_return_worker.

ALTER TABLE sentiment_signals
    ADD COLUMN IF NOT EXISTS forward_return_3d DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS forward_return_5d DOUBLE PRECISION;

COMMENT ON COLUMN sentiment_signals.forward_return_3d IS
    'Close-to-close return T -> T+3 trading days (NULL until computable)';
COMMENT ON COLUMN sentiment_signals.forward_return_5d IS
    'Close-to-close return T -> T+5 trading days (NULL until computable)';
