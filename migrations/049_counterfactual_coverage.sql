-- #337: the counterfactual column feeding #230's verdict was censored in two
-- systematic (non-random) ways. This migration adds the columns needed to make
-- the censoring readable at query time, and reindexes for keyset pagination.
--
-- 1. Batch starvation: the worker took ORDER BY tick_time DESC LIMIT 500 once a
--    night. Above ~500 skips/day the oldest rows (first hour of the session,
--    where overnight news lands) never got computed and aged out of the 7-day
--    window. The worker now pages to exhaustion via a (tick_time, id) keyset,
--    so the index carries id as a second key.
--
-- 2. Tail of the session: rows after ~19:00 UTC have their +1h window past the
--    close. They used to get counterfactual_computed_at with a NULL return and
--    were never retried. They now carry an explicit reason and either an
--    overnight return (entry -> first bar of the next session) or a
--    PENDING_OVERNIGHT marker with an attempt counter, so a row is never a
--    silent NULL.
--
-- counterfactual_skip_reason values written by run_counterfactual_worker:
--   NULL                    counterfactual_return_1h is populated
--   HORIZON_AFTER_CLOSE     +1h fell past the close; counterfactual_return_overnight holds
--                           the entry -> next-session-open return instead
--   PENDING_OVERNIGHT       as above, but the next session had not happened yet at run
--                           time; computed_at stays NULL and the row is retried
--   MISSING_ENTRY_BAR       no 1-min bar at tick_time
--   MISSING_EXIT_BAR        intra-session bar gap at tick_time + 1h
--   ZERO_ENTRY_PRICE        entry bar close was 0
--   NO_BARS_AFTER_HORIZON   nothing past the +1h mark even after the retry budget ran
--                           out (the terminal form of PENDING_OVERNIGHT)
--   NO_BARS                 Alpaca returned no bars for the symbol, attempts exhausted
--   FETCH_ERROR             Alpaca call failed, attempts exhausted
--
-- Coverage is complete when, for a given day:
--   count(*) = count(counterfactual_computed_at)
--            + count(*) FILTER (WHERE counterfactual_skip_reason = 'PENDING_OVERNIGHT')
-- The PENDING_OVERNIGHT term drains on the following night's run.

ALTER TABLE execution_decisions
    ADD COLUMN IF NOT EXISTS counterfactual_skip_reason TEXT,
    ADD COLUMN IF NOT EXISTS counterfactual_return_overnight DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS counterfactual_attempts INTEGER NOT NULL DEFAULT 0;

-- Keyset pagination orders by (tick_time DESC, id DESC); carry id so the
-- partial index still serves the whole scan.
DROP INDEX IF EXISTS idx_execution_decisions_counterfactual;

CREATE INDEX IF NOT EXISTS idx_execution_decisions_counterfactual
    ON execution_decisions (tick_time DESC, id DESC)
    WHERE counterfactual_computed_at IS NULL
      AND decision IN ('SKIP_THRESHOLD', 'SKIP_EMA', 'SKIP_CAP', 'SKIP_PYRAMIDING');

-- Lets the coverage query above stay cheap without scanning the whole table.
CREATE INDEX IF NOT EXISTS idx_execution_decisions_cf_pending_overnight
    ON execution_decisions (tick_time DESC)
    WHERE counterfactual_skip_reason = 'PENDING_OVERNIGHT';
