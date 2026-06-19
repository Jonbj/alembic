-- migrations/027_news_log_published_at.sql
-- Split news_log.fetched_at into two distinct timestamps.
--
-- Before this migration:
--   fetched_at  = article publication date from source (GDELT DATE col, Alpaca published_at, etc.)
--   created_at  = DEFAULT now() — actual DB insertion time, never explicitly set by code
--
-- After this migration:
--   published_at = article publication date from source  (what fetched_at used to store)
--   fetched_at   = when our pipeline ingested the article (reset to created_at; DEFAULT now() for new rows)
--   created_at   = unchanged, kept for compatibility
--
-- Effect on monitoring queries that use WHERE fetched_at > NOW() - INTERVAL '24 hours':
--   they now correctly detect whether the ingest pipeline ran recently.

ALTER TABLE news_log ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ;

-- Backfill: preserve article publication dates before resetting fetched_at.
UPDATE news_log SET published_at = fetched_at WHERE published_at IS NULL;

-- Reset fetched_at to the actual DB insertion time for all existing rows.
UPDATE news_log SET fetched_at = created_at;

-- Index for article-date range queries (backtesting, content-age freshness checks).
CREATE INDEX IF NOT EXISTS idx_news_log_published_brin ON news_log USING BRIN (published_at);
