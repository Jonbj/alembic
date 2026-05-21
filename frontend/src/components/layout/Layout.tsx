import { useEffect, useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Topbar } from './Topbar'
import { useStore } from '@/store'

export function Layout() {
  const { killswitchActive, setKillswitch, setMode } = useStore()
  const [apiOnline, setApiOnline] = useState<boolean | null>(null)

  useEffect(() => {
    const sync = async () => {
      try {
        const res = await fetch('/api/admin/status')
        if (!res.ok) { setApiOnline(false); return }
        const data = await res.json()
        setApiOnline(true)
        setKillswitch(data.killswitch)
        if (data.mode && data.mode !== 'unknown') setMode(data.mode)
      } catch {
        setApiOnline(false)
      }
    }
    sync()
    const id = setInterval(sync, 15_000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="app-shell">
      <Sidebar apiOnline={apiOnline} />
      <Topbar />
      <main className="view">
        {killswitchActive && (
          <div className="ks-banner">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M8 2l6.5 11h-13z"/><path d="M8 6v3M8 11v.5"/>
            </svg>
            <strong>Kill switch active.</strong>
            <span style={{ color: 'var(--fg-1)' }}>All trading halted. Open positions held.</span>
          </div>
        )}
        <div className="view-inner">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
