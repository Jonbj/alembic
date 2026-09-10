-- #512: misura pre-trade, point-in-time, della rincorsa del movimento S4.
-- Una riga SHADOW/OBSERVE per intent; nessuna colonna viene letta dal money path.

ALTER TABLE execution_decisions
    ADD COLUMN IF NOT EXISTS s4_intent_id UUID,
    ADD COLUMN IF NOT EXISTS decision_price DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS decision_price_source TEXT,
    ADD COLUMN IF NOT EXISTS session_open DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS session_high_so_far DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS session_low_so_far DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS session_return_from_open DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS session_range_percentile DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS shadow_late_entry BOOLEAN,
    ADD COLUMN IF NOT EXISTS entry_context_missingness JSONB NOT NULL DEFAULT '{}'::jsonb;

-- Il ledger ritenta in modo idempotente lo stesso decision_slot. Senza questo
-- vincolo un crash-recovery moltiplicherebbe l'evidenza ombra.
CREATE UNIQUE INDEX IF NOT EXISTS idx_execution_decisions_s4_late_entry_intent
    ON execution_decisions (s4_intent_id)
    WHERE s4_intent_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_execution_decisions_s4_late_entry_shadow
    ON execution_decisions (tick_time DESC, shadow_late_entry)
    WHERE s4_intent_id IS NOT NULL;

-- Lo stesso worker notturno che prezza gli SKIP calcola il rendimento a +1h
-- delle sole osservazioni che avrebbero soppresso l'ingresso. Le righe CLEAR
-- non entrano nel controfattuale e non consumano chiamate Alpaca.
DROP INDEX IF EXISTS idx_execution_decisions_counterfactual;

CREATE INDEX idx_execution_decisions_counterfactual
    ON execution_decisions (tick_time DESC, id DESC)
    WHERE counterfactual_computed_at IS NULL
      AND decision IN ('SKIP_THRESHOLD', 'SKIP_EMA', 'SKIP_CAP', 'SKIP_PYRAMIDING',
                       'SHADOW_LATE_ENTRY');
