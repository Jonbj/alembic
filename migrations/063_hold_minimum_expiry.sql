-- Migration 063: make the first portfolio cycle after the 90-minute hold
-- queryable in the trade ledger (#430). This is a diagnostic relabel only:
-- no order, threshold, flag, cooldown or strategy parameter changes.
--
-- Portfolio cycles are 15 minutes apart and the hold check includes the exact
-- 90-minute boundary, so the first eligible cycle is nominally 105 minutes.
-- One minute absorbs worker/fill timestamp jitter around that nominal beat.

UPDATE trades
SET exit_reason = 'hold_minimum_expiry'
WHERE exit_reason = 'portfolio_sell'
  AND entry_time >= TIMESTAMPTZ '2026-08-03 00:00:00+00'
  AND exit_time IS NOT NULL
  AND ABS(EXTRACT(EPOCH FROM (exit_time - entry_time)) - 6300) <= 60;
