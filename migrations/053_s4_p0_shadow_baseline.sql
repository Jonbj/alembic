-- #296: baseline P0 del trial exit S4, esclusivamente shadow.
-- Nessuna colonna rappresenta un ordine shadow: runtime_order_id e' provenance
-- read-only dell'ordine E0 osservato.

CREATE TABLE IF NOT EXISTS s4_exit_policy_events (
    event_id                       UUID PRIMARY KEY,
    intent_id                      UUID NOT NULL,
    policy_id                      VARCHAR(8) NOT NULL,
    policy_version                 TEXT NOT NULL,
    event_type                     TEXT NOT NULL,
    observed_at                    TIMESTAMPTZ NOT NULL,
    d0                             DATE,
    symbol                         VARCHAR(20) NOT NULL,
    status                         TEXT NOT NULL,
    reason_code                    TEXT NOT NULL,
    trigger_at                     TIMESTAMPTZ NOT NULL,
    virtual_exit_quantity          DOUBLE PRECISION NOT NULL DEFAULT 0,
    runtime_quantity               DOUBLE PRECISION NOT NULL DEFAULT 0,
    first_executable_at            TIMESTAMPTZ,
    first_executable_price         DOUBLE PRECISION,
    first_executable_price_source  TEXT,
    filled_at                      TIMESTAMPTZ,
    fill_price                     DOUBLE PRECISION,
    initial_notional               DOUBLE PRECISION NOT NULL DEFAULT 0,
    gross_pnl                      DOUBLE PRECISION,
    entry_cost_usd                 DOUBLE PRECISION,
    exit_cost_usd                  DOUBLE PRECISION,
    net_pnl                        DOUBLE PRECISION,
    cost_model_version             TEXT NOT NULL,
    runtime_decision_id            BIGINT,
    runtime_order_id               TEXT,
    comparable                     BOOLEAN NOT NULL DEFAULT FALSE,
    divergence_reasons             TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    details                        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at                     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_s4_exit_policy_intent
    ON s4_exit_policy_events (intent_id, policy_id, observed_at DESC, event_id DESC);
CREATE INDEX IF NOT EXISTS idx_s4_p0_validation_window
    ON s4_exit_policy_events (d0, comparable, reason_code)
    WHERE policy_id = 'P0';

CREATE OR REPLACE FUNCTION prevent_s4_exit_policy_event_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 's4_exit_policy_events is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS s4_exit_policy_events_append_only ON s4_exit_policy_events;
CREATE TRIGGER s4_exit_policy_events_append_only
    BEFORE UPDATE OR DELETE ON s4_exit_policy_events
    FOR EACH ROW EXECUTE FUNCTION prevent_s4_exit_policy_event_mutation();

DROP VIEW IF EXISTS s4_p0_residuals;
DROP VIEW IF EXISTS s4_p0_validation;
DROP VIEW IF EXISTS s4_exit_policy_current;

CREATE VIEW s4_exit_policy_current AS
SELECT DISTINCT ON (intent_id, policy_id) *
FROM s4_exit_policy_events
ORDER BY intent_id, policy_id, observed_at DESC, event_id DESC;

CREATE VIEW s4_p0_validation AS
SELECT
    COALESCE(d0, observed_at::date) AS lifecycle_date,
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE comparable) AS comparable,
    COUNT(*) FILTER (WHERE NOT comparable) AS residual,
    COUNT(*) FILTER (WHERE comparable)::DOUBLE PRECISION
        / NULLIF(COUNT(*), 0) AS coverage
FROM s4_exit_policy_current
WHERE policy_id = 'P0'
GROUP BY COALESCE(d0, observed_at::date);

CREATE VIEW s4_p0_residuals AS
SELECT
    COALESCE(d0, observed_at::date) AS lifecycle_date,
    reason_code,
    unnest(divergence_reasons) AS divergence_reason,
    COUNT(*) AS lifecycle_count
FROM s4_exit_policy_current
WHERE policy_id = 'P0' AND NOT comparable
GROUP BY COALESCE(d0, observed_at::date), reason_code, divergence_reason;
