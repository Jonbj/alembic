-- 044_news_queue_drops.sql
-- #149: record every queue item the sentiment worker discards as stale.
--
-- The worker skips stale items without an LLM call and deletes them from
-- news:processing at run end, leaving no trace anywhere. A day that loses 71% of
-- its queued items (2026-07-27: 579 queued, 165 reached news_log) is therefore
-- indistinguishable from a quiet day, and the two competing explanations —
-- "items arrived already older than the 2h gate" vs "items aged while waiting in
-- the queue" — cannot be told apart. They have opposite fixes, so the fix cannot
-- be chosen without this table.
--
-- age_hours is frozen at drop time rather than derived from dropped_at, which
-- would drift with run delays. article_id groups the fan-out copies of one
-- article (ingestion emits one entry per tagged ticker), making it possible to
-- see how much capacity a single macro article consumes.
SET lock_timeout = '2s';

CREATE TABLE IF NOT EXISTS news_queue_drops (
    id           BIGSERIAL PRIMARY KEY,
    dropped_at   TIMESTAMPTZ      NOT NULL DEFAULT now(),
    item_id      TEXT             NOT NULL,
    article_id   TEXT             NOT NULL,
    symbol       TEXT,
    source       TEXT,
    published_at TIMESTAMPTZ,
    age_hours    DOUBLE PRECISION,
    title        TEXT
);

-- Daily aggregation ("how much did we lose, by source, by age bucket").
CREATE INDEX IF NOT EXISTS idx_news_queue_drops_dropped_at
    ON news_queue_drops (dropped_at DESC);

-- Fan-out analysis ("which articles consume the queue").
CREATE INDEX IF NOT EXISTS idx_news_queue_drops_article
    ON news_queue_drops (article_id, dropped_at DESC);
