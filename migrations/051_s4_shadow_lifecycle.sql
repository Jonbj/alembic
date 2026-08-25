-- #295: fill e sleeve virtuali del trial exit S4, solo shadow.
-- Gli eventi sono immutabili; event_id deterministico rende retry/restart idempotenti.

CREATE TABLE IF NOT EXISTS s4_lifecycle_events (
    event_id                       UUID PRIMARY KEY,
    intent_id                      UUID NOT NULL,
    event_type                     TEXT NOT NULL CHECK (
        event_type IN ('ENTRY_RECONCILIATION', 'VIRTUAL_S4_EXIT')
    ),
    observed_at                    TIMESTAMPTZ NOT NULL,
    symbol                         VARCHAR(20) NOT NULL,
    order_id                       TEXT,
    status                         TEXT NOT NULL,
    reason_code                    TEXT NOT NULL,
    fill_id                        UUID,
    filled_at                      TIMESTAMPTZ,
    filled_quantity                DOUBLE PRECISION NOT NULL DEFAULT 0,
    filled_notional                DOUBLE PRECISION NOT NULL DEFAULT 0,
    first_executable_price         DOUBLE PRECISION,
    first_executable_price_source  TEXT,
    d0                             DATE,
    due_session                    DATE,
    policy_version                 TEXT NOT NULL,
    s1_virtual_quantity            DOUBLE PRECISION NOT NULL DEFAULT 0,
    s4_virtual_quantity            DOUBLE PRECISION NOT NULL DEFAULT 0,
    broker_quantity                DOUBLE PRECISION,
    unattributed_quantity          DOUBLE PRECISION,
    virtual_exit_quantity          DOUBLE PRECISION,
    virtual_exit_price             DOUBLE PRECISION,
    reconstructible                BOOLEAN NOT NULL DEFAULT FALSE,
    details                        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at                     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_s4_lifecycle_intent
    ON s4_lifecycle_events (intent_id, observed_at DESC, event_id DESC);
CREATE INDEX IF NOT EXISTS idx_s4_lifecycle_validation_window
    ON s4_lifecycle_events (d0, reconstructible, reason_code)
    WHERE event_type = 'ENTRY_RECONCILIATION';

CREATE OR REPLACE FUNCTION prevent_s4_lifecycle_event_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 's4_lifecycle_events is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS s4_lifecycle_events_append_only ON s4_lifecycle_events;
CREATE TRIGGER s4_lifecycle_events_append_only
    BEFORE UPDATE OR DELETE ON s4_lifecycle_events
    FOR EACH ROW EXECUTE FUNCTION prevent_s4_lifecycle_event_mutation();

DROP VIEW IF EXISTS s4_lifecycle_residuals;
DROP VIEW IF EXISTS s4_lifecycle_validation;
DROP VIEW IF EXISTS s4_lifecycle_current;

CREATE VIEW s4_lifecycle_current AS
SELECT DISTINCT ON (intent_id) *
FROM s4_lifecycle_events
WHERE event_type = 'ENTRY_RECONCILIATION'
ORDER BY intent_id, observed_at DESC, event_id DESC;

CREATE VIEW s4_lifecycle_validation AS
SELECT
    COALESCE(d0, observed_at::date) AS lifecycle_date,
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE reconstructible) AS reconstructible,
    COUNT(*) FILTER (WHERE NOT reconstructible) AS residual,
    COUNT(*) FILTER (WHERE reconstructible)::DOUBLE PRECISION
        / NULLIF(COUNT(*), 0) AS coverage
FROM s4_lifecycle_current
GROUP BY COALESCE(d0, observed_at::date);

CREATE VIEW s4_lifecycle_residuals AS
SELECT
    COALESCE(d0, observed_at::date) AS lifecycle_date,
    reason_code,
    COUNT(*) AS lifecycle_count
FROM s4_lifecycle_current
WHERE NOT reconstructible
GROUP BY COALESCE(d0, observed_at::date), reason_code;
