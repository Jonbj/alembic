-- WS-5 (2026-07-14): support multi-tranche exits.
-- A single trade row can be closed through several Alpaca sell orders (e.g.
-- SHEL 2026-07-13: three partial trims). Storing all exit order IDs lets
-- reconcile_trade_fills compute a quantity-weighted average exit price instead
-- of reading only the first tranche.
ALTER TABLE trades
    ADD COLUMN IF NOT EXISTS exit_order_ids TEXT[] DEFAULT NULL;
