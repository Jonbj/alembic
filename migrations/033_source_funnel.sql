-- S2-1 (FUNCTIONAL_REVIEW_2026-07-03 §9.1 #6, roadmap EN-05/EN-06):
-- per-source ingestion funnel + trace columns. Measurement only, never in hot path.

-- EN-06: one row per (day, source), counters incremented by each ingestion run.
CREATE TABLE IF NOT EXISTS ingestion_stats_daily (
    day                  DATE        NOT NULL,
    source               VARCHAR(50) NOT NULL,
    fetched              INTEGER     NOT NULL DEFAULT 0,
    queued               INTEGER     NOT NULL DEFAULT 0,
    duplicates           INTEGER     NOT NULL DEFAULT 0,
    discarded_no_ticker  INTEGER     NOT NULL DEFAULT 0,
    discarded_stale      INTEGER     NOT NULL DEFAULT 0,
    parse_fail           INTEGER     NOT NULL DEFAULT 0,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (day, source)
);

-- EN-05: trace columns on news_log.
-- raw_ingested_at = when the connector fetched the article (vs published_at = event time,
--   vs sentiment processing time) → real per-source latency becomes measurable.
-- content_hash    = normalised title+body hash (same function as the Redis dedup) → offline
--   cross-source duplicate analysis on persisted data.
-- discarded_reason = created HERE, populated by S2-2 (discard logging); NULL until then.
ALTER TABLE news_log ADD COLUMN IF NOT EXISTS raw_ingested_at  TIMESTAMPTZ;
ALTER TABLE news_log ADD COLUMN IF NOT EXISTS content_hash     VARCHAR(64);
ALTER TABLE news_log ADD COLUMN IF NOT EXISTS discarded_reason VARCHAR(30);

-- Group-by / join support for the per-source endpoint.
CREATE INDEX IF NOT EXISTS idx_news_log_source ON news_log (source);
CREATE INDEX IF NOT EXISTS idx_sentiment_signals_news_log_id ON sentiment_signals (news_log_id);
