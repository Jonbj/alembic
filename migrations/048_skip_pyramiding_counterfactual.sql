-- #337: renamed from 046_skip_pyramiding_counterfactual.sql — the 046 prefix
-- collided with 046_news_labels_2annotator.sql (that one is referenced by name
-- from tests/, so this file is the one that moved). Applicata a mano sul live il 2026-08-22, sotto il nome
-- precedente 046_skip_pyramiding_counterfactual.sql.
--
-- #315: SKIP_PYRAMIDING enters the counterfactual pipeline like the other skip
-- reasons. fetch_skip_decisions_without_counterfactual() now includes
-- 'SKIP_PYRAMIDING' in its IN (...) filter (it already covered SKIP_THRESHOLD,
-- which 018_counterfactual.sql's partial index never did either) — rebuild the
-- index so the planner can still use it for all four decision values.
DROP INDEX IF EXISTS idx_execution_decisions_counterfactual;

CREATE INDEX IF NOT EXISTS idx_execution_decisions_counterfactual
    ON execution_decisions (tick_time DESC)
    WHERE counterfactual_computed_at IS NULL
      AND decision IN ('SKIP_THRESHOLD', 'SKIP_EMA', 'SKIP_CAP', 'SKIP_PYRAMIDING');
