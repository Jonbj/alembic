-- Migration 056: attribute the verified F-002 legacy cohort and prevent
-- future trades from losing their origin sleeve when stop freezing is absent.
--
-- The 11 symbols below were all S1 targets in the 2026-07-10 portfolio cycles;
-- S4 targeted only SPCX while this cohort was opened.  Keep the timestamp and
-- NULL predicates so reruns are idempotent and unrelated history is untouched.

UPDATE trades
SET stop_strategy = 'S1'
WHERE stop_strategy IS NULL
  AND entry_time >= TIMESTAMPTZ '2026-07-10 00:00:00+00'
  AND entry_time < TIMESTAMPTZ '2026-07-11 00:00:00+00'
  AND symbol IN (
      'BAC', 'GOOGL', 'GS', 'MS', 'PBR', 'RIO',
      'ROKU', 'SPY', 'UBS', 'UNH', 'XLE'
  );

-- NOT VALID deliberately preserves unrelated historical NULL rows while the
-- constraint is enforced for every new or subsequently updated trade row.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'trades_stop_strategy_required'
          AND conrelid = 'trades'::regclass
    ) THEN
        ALTER TABLE trades
            ADD CONSTRAINT trades_stop_strategy_required
            CHECK (stop_strategy IS NOT NULL) NOT VALID;
    END IF;
END
$$;
