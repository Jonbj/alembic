-- migrations/007_add_llm_responses.sql
-- Stores individual model outputs before ensemble aggregation.
-- Retention: rows older than RETENTION_DAYS deleted by run_retention_sweep().

CREATE TABLE IF NOT EXISTS llm_responses (
    id           BIGSERIAL PRIMARY KEY,
    signal_id    BIGINT REFERENCES sentiment_signals(id) ON DELETE CASCADE,
    model_id     VARCHAR(50) NOT NULL,
    polarity     DOUBLE PRECISION NOT NULL,
    confidence   DOUBLE PRECISION NOT NULL,
    reasoning    TEXT,
    eligible     BOOLEAN NOT NULL DEFAULT TRUE,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_llm_responses_signal
    ON llm_responses (signal_id);

CREATE INDEX IF NOT EXISTS idx_llm_responses_time_brin
    ON llm_responses USING BRIN (generated_at);

CREATE INDEX IF NOT EXISTS idx_llm_responses_model_time
    ON llm_responses (model_id, generated_at DESC);
