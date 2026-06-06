-- Phase C: Counterfactual / Opportunity Cost Analysis
-- Adds 1-hour forward return for SKIP_EMA and SKIP_CAP decisions.
-- Populated nightly by run_counterfactual_worker (22:45 UTC).
ALTER TABLE execution_decisions
    ADD COLUMN IF NOT EXISTS counterfactual_return_1h DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS counterfactual_computed_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_execution_decisions_counterfactual
    ON execution_decisions (tick_time DESC)
    WHERE counterfactual_computed_at IS NULL
      AND decision IN ('SKIP_EMA', 'SKIP_CAP');
