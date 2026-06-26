import { useQuery } from '@tanstack/react-query'
import { fetchReadiness, readinessState, type Readiness } from '@/api/system'

const COLORS = {
  ready:    { bg: '#064e3b', border: '#059669', text: '#6ee7b7', label: 'READY' },
  degraded: { bg: '#78350f', border: '#d97706', text: '#fcd34d', label: 'DEGRADED' },
  blocked:  { bg: '#7f1d1d', border: '#dc2626', text: '#fca5a5', label: 'BLOCKED' },
} as const

function flagChips(r: Readiness) {
  const flags: Array<[string, boolean]> = [
    ['redis', r.redis_healthy && r.redis_writeable],
    ['db', r.db_healthy],
    ['kill-switch off', !r.killswitch_active],
    ['signals fresh', !r.stale_signals],
    ['beat ok', !r.worker_beat_lag],
  ]
  return flags.map(([label, ok]) => (
    <span key={label} title={ok ? 'ok' : 'unhealthy'} style={{
      fontSize: 10, padding: '1px 6px', borderRadius: 4,
      background: ok ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.25)',
      color: ok ? '#6ee7b7' : '#fca5a5',
    }}>{ok ? '✓' : '✕'} {label}</span>
  ))
}

/**
 * Global readiness banner. HTTP 200 from the endpoint does NOT mean healthy —
 * the state is derived from the flags, so a writable-Redis failure or stale
 * signals renders DEGRADED, not green.
 */
export function ReadinessBanner() {
  const { data, isError } = useQuery({
    queryKey: ['readiness'],
    queryFn: fetchReadiness,
    refetchInterval: 30_000,
  })

  if (isError) {
    return (
      <div style={{ background: '#7f1d1d', borderBottom: '1px solid #dc2626', color: '#fca5a5',
        padding: '4px 16px', fontSize: 12, fontWeight: 600 }}>
        ● readiness endpoint unreachable — system state unknown
      </div>
    )
  }
  if (!data) return null

  const state = readinessState(data)
  const c = COLORS[state]
  return (
    <div style={{
      background: c.bg, borderBottom: `1px solid ${c.border}`, color: c.text,
      padding: '5px 16px', fontSize: 12, display: 'flex', alignItems: 'center',
      gap: 12, flexWrap: 'wrap',
    }}>
      <span style={{ fontWeight: 700, letterSpacing: '0.05em' }}>● {c.label}</span>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>{flagChips(data)}</div>
      {state !== 'ready' && (
        <span style={{ opacity: 0.85, fontStyle: 'italic' }}>
          HTTP 200 ≠ healthy — vedi flag. Runbook: docs/CONTROLLED_PAPER_PREFLIGHT_RUNBOOK §7
        </span>
      )}
    </div>
  )
}
