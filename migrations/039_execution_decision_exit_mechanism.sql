-- Migration 039: exit_mechanism column on execution_decisions (#60)
-- Structured tag for weight-0 S4 SELL exits so downstream measurement (#61
-- anti-whipsaw damping) doesn't need to parse the free-text 'reason' column
-- to tell apart "no_signal" / "expired" / "whipsaw" exits. NULL for all
-- other decision rows (BUY, non-zero SELL, stop_loss, sentiment_reversal) —
-- those already carry a clear, self-descriptive reason string.
ALTER TABLE execution_decisions
    ADD COLUMN IF NOT EXISTS exit_mechanism VARCHAR(32);
