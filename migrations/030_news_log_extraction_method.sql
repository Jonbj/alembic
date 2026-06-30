-- migrations/030_news_log_extraction_method.sql
-- QT-03: record how each ticker was derived, to measure extraction precision per
-- method and confirm QT-01 eliminated the watchlist fallback. Additive + nullable
-- (existing rows/writes unaffected).
--   source_metadata — ticker from the source's entity/symbol metadata (MarketAux/Alpaca)
--   cashtag         — extracted from a $cashtag in the text (QT-01 fallback)
--   org_lookup      — GDELT org name resolved via ticker_lookup
--   regex           — bare-word watchlist match in RSS text

ALTER TABLE news_log ADD COLUMN IF NOT EXISTS extraction_method TEXT;
