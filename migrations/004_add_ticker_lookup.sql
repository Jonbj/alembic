-- migrations/004_add_ticker_lookup.sql
-- Lookup table mapping GDELT organisation names to ticker symbols.
-- Used by TickerExtractor for news-driven ticker discovery.

CREATE TABLE IF NOT EXISTS ticker_lookup (
    id           SERIAL PRIMARY KEY,
    company_name TEXT NOT NULL,
    aliases      TEXT[] NOT NULL DEFAULT '{}',
    ticker       TEXT NOT NULL,
    source       TEXT NOT NULL  -- 'sp500', 'etf', 'manual'
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ticker_lookup_name_ticker
    ON ticker_lookup (lower(company_name), ticker);
CREATE INDEX IF NOT EXISTS idx_ticker_lookup_name
    ON ticker_lookup (lower(company_name));
CREATE INDEX IF NOT EXISTS idx_ticker_lookup_aliases
    ON ticker_lookup USING GIN (aliases);
