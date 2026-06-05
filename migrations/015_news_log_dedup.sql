-- migrations/015_news_log_dedup.sql
-- Adds UNIQUE(url, ticker) to news_log so ON CONFLICT DO NOTHING works.
--
-- Without this constraint the INSERT ... ON CONFLICT DO NOTHING in
-- pg_store._INSERT_NEWS_LOG was a no-op: the only possible conflict was on
-- the BIGSERIAL primary key, which auto-increments and never duplicates.
-- The Redis Deduplicator (2h TTL) was the only guard, so articles
-- re-appearing in the feed after 2h accumulated multiple copies.
--
-- Step 1: remove existing true duplicates, keeping the latest row.
DELETE FROM news_log
WHERE id NOT IN (
    SELECT DISTINCT ON (url, ticker) id
    FROM news_log
    ORDER BY url, ticker, created_at DESC
);

-- Step 2: add the unique constraint so future inserts are idempotent.
ALTER TABLE news_log
    ADD CONSTRAINT uq_news_log_url_ticker UNIQUE (url, ticker);
