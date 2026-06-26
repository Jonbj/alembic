/**
 * True during Alembic's portfolio-cycle window: Mon–Fri 14:00–21:00 UTC.
 *
 * This is the window in which the beat scheduler runs portfolio cycles and signals
 * are produced (config: beat crontab hour=14-21, fixed UTC — does not shift with DST).
 * It is intentionally the *cycle* window, not the raw US session (13:30–20:00 UTC in
 * summer): the readiness banner cares about when the SYSTEM is expected to be active,
 * so that stale-signal / beat-lag flags only read as "degraded" while cycles should be
 * running. Outside this window those flags are expected and suppressed.
 *
 * Market holidays are not modeled (a holiday reads as "open" — a rare, harmless
 * false positive).
 */
export function isTradingWindow(now: Date = new Date()): boolean {
  const day = now.getUTCDay() // 0=Sun … 6=Sat
  const isWeekday = day >= 1 && day <= 5
  const hour = now.getUTCHours()
  return isWeekday && hour >= 14 && hour < 21
}
