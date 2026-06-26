/**
 * True during the US equity regular session (Mon–Fri 09:30–16:00 ET), DST-correct
 * via the IANA timezone (America/New_York). Holidays and half-days are not modeled
 * (a market holiday will read as "open" — a rare, harmless false positive).
 *
 * Used by the readiness banner to suppress stale-signal / beat-lag "degraded" noise
 * outside market hours, when no signals or cycles are expected to run.
 */
export function isUsMarketHours(now: Date = new Date()): boolean {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).formatToParts(now)
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? ''
  const weekday = get('weekday')
  let hour = parseInt(get('hour'), 10)
  if (hour === 24) hour = 0 // some runtimes render midnight as "24"
  const minute = parseInt(get('minute'), 10)
  const isWeekday = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'].includes(weekday)
  const mins = hour * 60 + minute
  return isWeekday && mins >= 9 * 60 + 30 && mins < 16 * 60
}
