import { useQuery } from '@tanstack/react-query'
import { fetchReadiness, type Readiness } from '@/api/system'
import { isTradingWindow } from '@/utils/market'

type BannerState = 'ready' | 'degraded' | 'blocked' | 'closed'

const COLORS = {
  ready:    { bg: '#064e3b', border: '#059669', text: '#6ee7b7', label: 'READY' },
  degraded: { bg: '#78350f', border: '#d97706', text: '#fcd34d', label: 'DEGRADED' },
  blocked:  { bg: '#7f1d1d', border: '#dc2626', text: '#fca5a5', label: 'BLOCKED' },
  closed:   { bg: '#1e293b', border: '#475569', text: '#94a3b8', label: 'MARKET CLOSED' },
} as const

/**
 * Banner state, market-hours aware. HTTP 200 from the endpoint never implies healthy.
 *
 * - Infra failures (kill-switch / db / redis down, non-writable Redis/MISCONF) are
 *   alarming 24/7 → blocked/degraded regardless of session.
 * - Stale signals and beat lag only mean trouble DURING market hours; outside the
 *   session no signals/cycles are expected, so they are not flagged.
 */
function bannerState(r: Readiness, marketOpen: boolean): BannerState {
  if (r.killswitch_active || !r.db_healthy || !r.redis_healthy) return 'blocked'
  if (!r.redis_writeable) return 'degraded' // MISCONF — matters any time
  if (marketOpen) return r.stale_signals || r.worker_beat_lag ? 'degraded' : 'ready'
  return 'closed'
}

function flagChips(r: Readiness, marketOpen: boolean) {
  // [label, healthy, market-dependent]
  const flags: Array<[string, boolean, boolean]> = [
    ['redis', r.redis_healthy && r.redis_writeable, false],
    ['db', r.db_healthy, false],
    ['kill-switch off', !r.killswitch_active, false],
    ['signals fresh', !r.stale_signals, true],
    ['beat ok', !r.worker_beat_lag, true],
  ]
  return flags.map(([label, ok, marketDep]) => {
    const expected = marketDep && !marketOpen && !ok // down but expected (market closed)
    const good = ok || expected
    return (
      <span
        key={label}
        title={expected ? 'in pausa (mercato chiuso)' : ok ? 'ok' : 'unhealthy'}
        style={{
          fontSize: 10, padding: '1px 6px', borderRadius: 4,
          background: good ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.25)',
          color: good ? '#6ee7b7' : '#fca5a5',
          opacity: expected ? 0.6 : 1,
        }}
      >
        {expected ? '–' : ok ? '✓' : '✕'} {label}
      </span>
    )
  })
}

/**
 * Global readiness banner. State is derived from the flags (not the HTTP status) and
 * is market-hours aware so it does not cry DEGRADED all night/weekend when no signals
 * or cycles are expected to run.
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

  const marketOpen = isTradingWindow()
  const state = bannerState(data, marketOpen)
  const c = COLORS[state]
  return (
    <div style={{
      background: c.bg, borderBottom: `1px solid ${c.border}`, color: c.text,
      padding: '5px 16px', fontSize: 12, display: 'flex', alignItems: 'center',
      gap: 12, flexWrap: 'wrap',
    }}>
      <span style={{ fontWeight: 700, letterSpacing: '0.05em' }}>● {c.label}</span>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>{flagChips(data, marketOpen)}</div>
      {state === 'degraded' || state === 'blocked' ? (
        <span style={{ opacity: 0.85, fontStyle: 'italic' }}>
          HTTP 200 ≠ healthy — vedi flag. Runbook: docs/archive/2026-06-p2-milestone/CONTROLLED_PAPER_PREFLIGHT_RUNBOOK §7
        </span>
      ) : state === 'closed' ? (
        <span style={{ opacity: 0.7, fontStyle: 'italic' }}>
          Segnali e cicli in pausa fuori orario — riprendono all'apertura del mercato (≈14:00 UTC)
        </span>
      ) : null}
    </div>
  )
}
