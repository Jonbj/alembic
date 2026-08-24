-- #294: point-in-time S4 entry intents before rank/guards and final disposition.
-- Events are immutable; retries use deterministic UUIDs and ON CONFLICT DO NOTHING.

CREATE TABLE IF NOT EXISTS s4_intent_events (
    event_id               UUID PRIMARY KEY,
    intent_id              UUID NOT NULL,
    causal_event_id        TEXT NOT NULL,
    event_type             TEXT NOT NULL CHECK (event_type IN ('candidate', 'disposition')),
    occurred_at            TIMESTAMPTZ NOT NULL,
    decision_slot          TIMESTAMPTZ NOT NULL,
    symbol                 VARCHAR(20) NOT NULL,
    signal_id              BIGINT REFERENCES sentiment_signals(id) ON DELETE SET NULL,
    published_at           TIMESTAMPTZ,
    first_seen_at          TIMESTAMPTZ,
    model_generated_at     TIMESTAMPTZ NOT NULL,
    decision_at            TIMESTAMPTZ NOT NULL,
    rank                   INTEGER CHECK (rank IS NULL OR rank > 0),
    competing_candidates   JSONB NOT NULL DEFAULT '[]'::jsonb,
    s1_state               JSONB NOT NULL,
    anti_pyramiding        BOOLEAN,
    reason_code            TEXT NOT NULL,
    is_tradable            BOOLEAN,  -- passed entry gates + ranking; independent of execution
    versions               JSONB NOT NULL,
    snapshot               JSONB NOT NULL,
    missingness            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (intent_id, event_type)
);

CREATE INDEX IF NOT EXISTS idx_s4_intent_events_slot
    ON s4_intent_events (decision_slot DESC, event_type);
CREATE INDEX IF NOT EXISTS idx_s4_intent_events_signal
    ON s4_intent_events (signal_id, decision_slot DESC);
CREATE INDEX IF NOT EXISTS idx_news_resolved_entities_intent_lookup
    ON news_resolved_entities (news_log_id, candidate_ticker, created_at DESC, id DESC);

CREATE OR REPLACE FUNCTION prevent_s4_intent_event_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 's4_intent_events is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS s4_intent_events_append_only ON s4_intent_events;
CREATE TRIGGER s4_intent_events_append_only
    BEFORE UPDATE OR DELETE ON s4_intent_events
    FOR EACH ROW EXECUTE FUNCTION prevent_s4_intent_event_mutation();

DROP VIEW IF EXISTS s4_tradable_intent_population;
DROP VIEW IF EXISTS s4_candidate_population;

CREATE VIEW s4_candidate_population AS
SELECT *
FROM s4_intent_events
WHERE event_type = 'candidate';

CREATE VIEW s4_tradable_intent_population AS
SELECT
    candidate.*,
    disposition.event_id AS disposition_event_id,
    disposition.rank AS final_rank,
    disposition.reason_code AS final_reason_code,
    disposition.s1_state AS final_s1_state,
    disposition.anti_pyramiding AS final_anti_pyramiding
FROM s4_intent_events AS candidate
JOIN s4_intent_events AS disposition
  ON disposition.intent_id = candidate.intent_id
 AND disposition.event_type = 'disposition'
WHERE candidate.event_type = 'candidate'
  AND disposition.is_tradable IS TRUE;
