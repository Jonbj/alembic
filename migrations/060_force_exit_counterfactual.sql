-- Migration 060: counterfactual coverage for force-exit SELL decisions (#450)
--
-- #450: execution_decisions rows with decision='SELL' and reason LIKE
-- 'sentiment_reversal%' are written by _sentiment_reversal_sells (portfolio_scheduler
-- L4742-4796) when the held position's sentiment score drops below
-- config.SENTIMENT_REVERSAL_EXIT_THRESHOLD. These decisions currently leave
-- counterfactual_return_1h/overnight as NULL because
-- fetch_skip_decisions_without_counterfactual() filters on decision IN
-- ('SKIP_THRESHOLD', 'SKIP_EMA', 'SKIP_CAP', 'SKIP_PYRAMIDING') only.
--
-- The 048 partial index also filters on decision IN (those four SKIP_* values),
-- so the planner cannot use it for the SELL branch. Without an index, the worker
-- would full-scan execution_decisions every night — acceptable while
-- sentiment_reversal SELLs are O(30) but bound to grow as the trading record
-- lengthens.
--
-- New partial index mirrors the SKIP_* one: same keyset order, same predicate
-- shape, narrower universe (one decision + one reason prefix). The LIKE on
-- reason is anchored to the prefix and the population is small, so the index
-- stays small and the planner can use it for fetch_force_exit_decisions_
-- without_counterfactual().
--
-- counterfactual_computed_at is NOT NULL after the worker processes a row, so
-- the partial predicate prunes the ever-growing processed set the same way
-- the SKIP_* index does.

CREATE INDEX IF NOT EXISTS idx_execution_decisions_force_exit_cf
    ON execution_decisions (tick_time DESC, id DESC)
    WHERE counterfactual_computed_at IS NULL
      AND decision = 'SELL'
      AND reason LIKE 'sentiment_reversal%';
