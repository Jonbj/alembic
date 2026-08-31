-- Migration 057: live open-quantity column for trades (#397).
--
-- trades.qty is overloaded: it holds the entry fill qty while a trade is open
-- and is overwritten with the exit fill qty once the trade closes
-- (reconcile_trade_fills). So it can never answer "how much is still held" for
-- a partially-wind-down open trade — partial exits and broker-side stop fills
-- were never written back, leaving DB qty 2.8x-74x the broker position (NOK/WDC/
-- MRVL, 2026-08 alpha-miss review [F-048]).
--
-- quantity_remaining is the live open position size, maintained by the
-- reconcile pass from authoritative broker SELL fills (see
-- PostgreSQLStore.reconcile_open_positions). NULL = not yet reconciled;
-- consumers fall back to qty (COALESCE(quantity_remaining, qty)) so the column
-- is additive and backfill is best-effort, never blocking.
--
-- No data backfill here: the three known rows are repaired by
-- scripts/repair_phantom_quantities_397.py (operator-run), and market_daily.jsonl
-- is left untouched (append-only ledger — contamination noted, not rewritten).

ALTER TABLE trades
    ADD COLUMN IF NOT EXISTS quantity_remaining DOUBLE PRECISION;