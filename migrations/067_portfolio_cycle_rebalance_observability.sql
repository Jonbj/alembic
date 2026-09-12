-- Migration 067: target transitions on portfolio cycles (#468).
--
-- The always-on exit hysteresis removes the first weight-zero SELL from the
-- final order list.  Persist the strategies that actually re-decided their
-- target and the symbols removed from each previous target before that filter,
-- so a monthly S1 rotation remains reconstructible without changing execution.

ALTER TABLE portfolio_cycles
    ADD COLUMN IF NOT EXISTS rebalanced_strategies JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS zero_weight_symbols JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN portfolio_cycles.rebalanced_strategies IS
    'Strategies that computed a new target in this cycle; observability only (#468).';

COMMENT ON COLUMN portfolio_cycles.zero_weight_symbols IS
    'Map strategy -> symbols whose prior positive target became zero in this cycle, or null when the prior target is unavailable; captured before exit hysteresis (#468).';
