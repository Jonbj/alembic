-- #328: preserve the issuer-relevance evidence already returned by each LLM.
-- Nullable is intentional: NULL means the model omitted the field, while explicit
-- schema defaults (for example directness='direct') remain observable as values.

ALTER TABLE llm_responses
    ADD COLUMN IF NOT EXISTS event_type TEXT,
    ADD COLUMN IF NOT EXISTS directness TEXT,
    ADD COLUMN IF NOT EXISTS materiality DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS novelty DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS risk_flags TEXT[],
    ADD COLUMN IF NOT EXISTS evidence_sentences TEXT[];
