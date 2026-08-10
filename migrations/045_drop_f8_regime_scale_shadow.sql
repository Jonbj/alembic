-- 045_drop_f8_regime_scale_shadow.sql
-- #134: F8 (feedback:regime_scale:S*) was retired 2026-08-10.
-- Lifecycle: docs/F8_LIFECYCLE_HISTORY_2026-08-10.md.
-- The migration DROPS the persisted-shadow table from migration 040 since the
-- writer (insert_f8_shadow) is gone and no new rows can be produced. Backups
-- of the rows written 2026-07-21 → 2026-08-07 already live in backups/ and
-- are intentionally NOT touched here — the 140 rows are the local evidence of
-- the trajectory F8 would have had, and they remain queryable from the
-- backup until the operator decides to delete them.
--
-- OPERATOR DECISION REQUIRED: this migration is shipped but NOT applied
-- automatically. The table is inert (no writers, no readers post-2026-08-10)
-- so leaving it in place is safe; drop it only after you have confirmed the
-- backup is safe and any downstream report/dashboard has been updated.
SET lock_timeout = '2s';

DROP TABLE IF EXISTS f8_regime_scale_shadow;
