-- migrations/032_sentiment_signals_published_at.sql
-- FIX-03 (FUNCTIONAL_REVIEW_2026-07-03): event-time freshness.
-- published_at = when the news was published (NewsItem.timestamp), as opposed to
-- generated_at = when the LLM processed it. NULL for legacy rows and non-news signals.
ALTER TABLE sentiment_signals
    ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ;

COMMENT ON COLUMN sentiment_signals.published_at IS
    'News publication time (event-time). NULL = unknown/legacy. Used by fetch_signals_for_cycle freshness gate (FIX-03).';
