-- migrations/006_add_news_log.sql
-- Stores each news article processed by SentimentWorker (title, url, source, ticker).
-- Retention: rows older than RETENTION_DAYS deleted by run_retention_sweep().

CREATE TABLE IF NOT EXISTS news_log (
    id          BIGSERIAL PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT '',
    url         TEXT NOT NULL DEFAULT '',
    source      VARCHAR(50) NOT NULL,
    ticker      VARCHAR(20) NOT NULL,
    body_snippet TEXT,
    raw_sentiment DOUBLE PRECISION,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_news_log_time_brin
    ON news_log USING BRIN (fetched_at);

CREATE INDEX IF NOT EXISTS idx_news_log_ticker_time
    ON news_log (ticker, fetched_at DESC);

CREATE INDEX IF NOT EXISTS idx_news_log_source_time
    ON news_log (source, fetched_at DESC);
