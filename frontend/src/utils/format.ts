const IT = 'it-IT'
const DATE_TIME_OPTS: Intl.DateTimeFormatOptions = {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
}

/** Format any ISO/Date value as  15/06/2026, 23:47:29 */
export function fmtDateTime(value: string | number | Date | null | undefined): string {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString(IT, DATE_TIME_OPTS)
  } catch {
    return String(value)
  }
}

/** Format any ISO/Date value as  15/06/2026 */
export function fmtDate(value: string | number | Date | null | undefined): string {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString(IT, {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    })
  } catch {
    return String(value)
  }
}
