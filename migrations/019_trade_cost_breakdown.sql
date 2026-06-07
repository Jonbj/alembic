-- 019_trade_cost_breakdown.sql
-- Add real cost breakdown columns to trades table.
-- Replaces the flat slippage_est = entry_notional * 0.0005 with tier-based actuals.
-- All columns NULLABLE: existing closed trades retain slippage_est, new trades get full breakdown.

ALTER TABLE trades
    ADD COLUMN IF NOT EXISTS cost_bps             NUMERIC,
    ADD COLUMN IF NOT EXISTS cost_usd             NUMERIC,
    ADD COLUMN IF NOT EXISTS spread_cost_bps      NUMERIC,
    ADD COLUMN IF NOT EXISTS impact_cost_bps      NUMERIC,
    ADD COLUMN IF NOT EXISTS regulatory_cost_usd  NUMERIC;

COMMENT ON COLUMN trades.cost_bps            IS 'Total roundtrip cost in bps (spread + impact). NULL for pre-019 trades.';
COMMENT ON COLUMN trades.cost_usd            IS 'Total cost in USD (bps-based + regulatory fees). NULL for pre-019 trades.';
COMMENT ON COLUMN trades.spread_cost_bps     IS 'Tier-based bid-ask spread cost in bps. NULL for pre-019 trades.';
COMMENT ON COLUMN trades.impact_cost_bps     IS 'Almgren-Chriss market impact in bps. NULL for pre-019 trades.';
COMMENT ON COLUMN trades.regulatory_cost_usd IS 'SEC Section 31 + FINRA TAF fees (sells only). NULL for pre-019 trades.';
