-- 037_llm_shadow_responses.sql
-- Stage 2 shadow-mode model comparison (spec 2026-07-09). Shadow candidates score
-- live news items; forward returns join via news_log_id -> sentiment_signals.
SET lock_timeout = '2s';

CREATE TABLE IF NOT EXISTS llm_shadow_responses (
    id          BIGSERIAL PRIMARY KEY,
    news_log_id BIGINT REFERENCES news_log(id) ON DELETE SET NULL,
    symbol      VARCHAR(20) NOT NULL,
    model_id    TEXT NOT NULL,
    polarity    DOUBLE PRECISION,
    confidence  DOUBLE PRECISION,
    reasoning   TEXT,
    parse_error BOOLEAN NOT NULL DEFAULT FALSE,
    latency_ms  INTEGER,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_shadow_model_time
    ON llm_shadow_responses (model_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_shadow_news
    ON llm_shadow_responses (news_log_id);
