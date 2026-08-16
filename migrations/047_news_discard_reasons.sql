-- 047_news_discard_reasons.sql
-- FIX-06 / #39: extend the #149 event ledger from stale-only queue drops to
-- every explicit ingestion/sentiment discard.  `news_log` remains the ledger
-- of processed (url, ticker) pairs: putting duplicate discard events there
-- would violate its uniqueness contract or corrupt source/P&L attribution.
SET lock_timeout = '2s';

ALTER TABLE news_queue_drops
    ADD COLUMN IF NOT EXISTS discarded_reason VARCHAR(30),
    ADD COLUMN IF NOT EXISTS discard_stage VARCHAR(20) NOT NULL DEFAULT 'sentiment',
    ADD COLUMN IF NOT EXISTS url TEXT,
    ADD COLUMN IF NOT EXISTS raw_ingested_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64);

-- Rows written by migration 044 predate the reason column and were all stale
-- drops from the sentiment queue by construction.
UPDATE news_queue_drops
SET discarded_reason = 'stale'
WHERE discarded_reason IS NULL;

ALTER TABLE news_queue_drops
    ALTER COLUMN discarded_reason SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_news_queue_drops_reason'
    ) THEN
        ALTER TABLE news_queue_drops
            ADD CONSTRAINT ck_news_queue_drops_reason CHECK (
                discarded_reason IN (
                    'no_ticker', 'stale', 'duplicate_id', 'duplicate_content',
                    'not_tradable', 'parse_fail', 'near_neutral'
                )
            );
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_news_queue_drops_stage'
    ) THEN
        ALTER TABLE news_queue_drops
            ADD CONSTRAINT ck_news_queue_drops_stage CHECK (
                discard_stage IN ('ingestion', 'sentiment')
            );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_news_queue_drops_reason
    ON news_queue_drops (discarded_reason, dropped_at DESC);

COMMENT ON TABLE news_queue_drops IS
    'News discard event ledger (name retained for compatibility with #149 reports).';
