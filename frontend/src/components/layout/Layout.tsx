import { useEffect } from 'react'
import { Outlet } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Sidebar } from './Sidebar'
import { ReadinessBanner } from './ReadinessBanner'
import { useStore } from '@/store'
import { fetchReadiness } from '@/api/system'

function statusText(value: boolean | undefined, ok: string, bad: string): string {
  if (value == null) return '—'
  return value ? ok : bad
}

function ageText(minutes: number | null | undefined): string {
  if (minutes == null) return '—'
  if (minutes < 60) return `${Math.round(minutes)}m`
  return `${(minutes / 60).toFixed(1)}h`
}

function MobileStatus() {
  const { mode, killswitchActive, logout } = useStore()
  const { data: readiness, isError } = useQuery({
    queryKey: ['mobile-readiness'],
    queryFn: fetchReadiness,
    refetchInterval: 30000,
  })

  const blocked = killswitchActive || readiness?.killswitch_active || readiness?.db_healthy === false || readiness?.redis_healthy === false
  const degraded = !blocked && (readiness?.redis_writeable === false || readiness?.stale_signals || readiness?.worker_beat_lag || isError)
  const label = blocked ? 'Blocked' : degraded ? 'Degraded' : readiness ? 'Ready' : 'Loading'
  const tone = blocked ? 'bad' : degraded ? 'warn' : readiness ? 'good' : 'neutral'

  const handleLogout = () => {
    logout()
    window.location.href = '/login'
  }

  return (
    <section className="mobile-status-shell" aria-label="Mobile status">
      <div className="mobile-status-header">
        <div>
          <div className="mobile-brand">Alembic</div>
          <div className="mobile-subtitle">Status</div>
        </div>
        <span className={`mobile-status-pill mobile-status-${tone}`}>{label}</span>
      </div>

      <div className="mobile-status-grid">
        <div className="mobile-status-card">
          <span>Mode</span>
          <strong>{mode.replace('_', ' ')}</strong>
        </div>
        <div className="mobile-status-card">
          <span>Kill switch</span>
          <strong>{statusText(!(killswitchActive || readiness?.killswitch_active), 'Off', 'On')}</strong>
        </div>
        <div className="mobile-status-card">
          <span>Last signal</span>
          <strong>{ageText(readiness?.last_signal_age_minutes)}</strong>
        </div>
        <div className="mobile-status-card">
          <span>Last cycle</span>
          <strong>{ageText(readiness?.last_cycle_age_minutes)}</strong>
        </div>
        <div className="mobile-status-card">
          <span>Redis</span>
          <strong>{statusText(readiness?.redis_healthy && readiness?.redis_writeable, 'OK', 'Issue')}</strong>
        </div>
        <div className="mobile-status-card">
          <span>Database</span>
          <strong>{statusText(readiness?.db_healthy, 'OK', 'Issue')}</strong>
        </div>
      </div>

      <div className="mobile-status-note">
        Controls and detailed tables are available from a desktop viewport. Mobile is intentionally read-only for operational status.
      </div>

      <button className="mobile-logout" onClick={handleLogout}>Logout</button>
    </section>
  )
}

export function Layout() {
  const { setKillswitch, setMode, setLlmModels, setLlmModelRegistry } = useStore()

  useEffect(() => {
    const sync = async () => {
      try {
        const res = await fetch('/api/admin/status')
        if (!res.ok) return
        const data = await res.json()
        setKillswitch(data.killswitch)
        if (data.mode && data.mode !== 'unknown') setMode(data.mode)
        if (data.llm_models) setLlmModels(data.llm_models)
        if (data.llm_model_registry) setLlmModelRegistry(data.llm_model_registry)
      } catch { /* backend unreachable */ }
    }
    sync()
    const id = setInterval(sync, 15_000)
    return () => clearInterval(id)
  }, [setKillswitch, setLlmModelRegistry, setLlmModels, setMode])

  return (
    <>
      <Sidebar />
      <div className="app-main" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflowY: 'auto', maxWidth: '100%' }}>
        <ReadinessBanner />
        <main style={{ flex: 1, padding: '24px' }}>
          <Outlet />
        </main>
      </div>
      <MobileStatus />
    </>
  )
}
