-- Migration 021: portfolio_daily_state view for decay monitor (T-605 follow-up)
-- Aggregates daily net P&L from closed trades.
-- Used by decay_monitor_task to compute rolling Sharpe and max drawdown.

CREATE OR REPLACE VIEW portfolio_daily_state AS
SELECT
    exit_time::date                                          AS snapshot_date,
    SUM(net_pnl) / NULLIF(SUM(entry_notional), 0)           AS daily_return,
    SUM(net_pnl)                                             AS net_pnl,
    COUNT(*)                                                 AS n_trades
FROM trades
WHERE exit_time   IS NOT NULL
  AND net_pnl     IS NOT NULL
  AND entry_notional > 0
GROUP BY exit_time::date
ORDER BY exit_time::date;
