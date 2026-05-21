import { useState } from 'react'
import React from 'react'
import { NavLink } from 'react-router-dom'
import { ApiKeyModal } from './ApiKeyModal'

function Logo() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="9.5" cy="15" r="5.2" />
      <path d="M7.5 10.3 L7.5 6 M11.5 10.3 L11.5 6" />
      <path d="M6.5 6 L12.5 6" />
      <path d="M13.7 11.8 Q19 11.8 19 7.2 L21 7.2" />
      <circle cx="21" cy="11.2" r="1.25" fill="currentColor" stroke="none" />
      <circle cx="9.5" cy="15" r="1.3" fill="currentColor" stroke="none" opacity="0.45" />
    </svg>
  )
}

const C = { width: 14, height: 14, viewBox: '0 0 16 16', fill: 'none', stroke: 'currentColor', strokeWidth: 1.5, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }

const ICONS: Record<string, React.ReactElement> = {
  overview:    <svg {...C}><rect x="2" y="2" width="5" height="5" rx="1"/><rect x="9" y="2" width="5" height="5" rx="1"/><rect x="2" y="9" width="5" height="5" rx="1"/><rect x="9" y="9" width="5" height="5" rx="1"/></svg>,
  signals:     <svg {...C}><path d="M2 12l3-5 3 3 4-7 2 4"/><path d="M2 14h12"/></svg>,
  trading:     <svg {...C}><path d="M3 12V6"/><path d="M8 12V3"/><path d="M13 12V8"/><path d="M2 14h12"/></svg>,
  performance: <svg {...C}><path d="M2 12l3-3 3 2 3-4 3 3"/><path d="M2 14h12"/></svg>,
  backtest:    <svg {...C}><circle cx="8" cy="8" r="6"/><path d="M8 4v4l3 2"/></svg>,
  news:        <svg {...C}><rect x="2" y="3" width="12" height="10" rx="1.2"/><path d="M4 6h6M4 8.5h6M4 11h4"/></svg>,
  llm:         <svg {...C}><path d="M3 5a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2H7l-3 2v-2H5a2 2 0 0 1-2-2z"/><circle cx="6.5" cy="7" r=".7" fill="currentColor"/><circle cx="9.5" cy="7" r=".7" fill="currentColor"/></svg>,
  config:      <svg {...C}><circle cx="8" cy="8" r="2"/><path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M3.4 12.6l1.4-1.4M11.2 4.8l1.4-1.4"/></svg>,
  admin:       <svg {...C}><path d="M8 1.5l5 2v4.2c0 3.2-2.1 5.7-5 6.8-2.9-1.1-5-3.6-5-6.8V3.5z"/></svg>,
  auto:        <svg {...C}><path d="M8 2v3"/><path d="M8 11v3"/><circle cx="8" cy="8" r="3"/><path d="M2 8h3M11 8h3"/></svg>,
  key:         <svg {...C}><circle cx="6" cy="10" r="3"/><path d="M9 7l5-5"/><path d="M14 2l-1 1M12 4l-1 1"/></svg>,
}

const NAV: { to: string; label: string; icon: string; group?: string }[] = [
  { to: '/',             label: 'Overview',     icon: 'overview',    group: 'TRADE' },
  { to: '/signals',      label: 'Signals',      icon: 'signals' },
  { to: '/trading',      label: 'Trading',      icon: 'trading' },
  { to: '/performance',  label: 'Performance',  icon: 'performance' },
  { to: '/backtest',     label: 'Backtest',     icon: 'backtest',   group: 'RESEARCH' },
  { to: '/news',         label: 'News',         icon: 'news' },
  { to: '/llm',          label: 'LLM',          icon: 'llm' },
  { to: '/config',       label: 'Config',       icon: 'config',     group: 'SYSTEM' },
  { to: '/admin',        label: 'Admin',        icon: 'admin' },
  { to: '/auto-improve', label: 'Auto-Improve', icon: 'auto' },
]

export function Sidebar({ apiOnline }: { apiOnline: boolean | null }) {
  const [apiKeyOpen, setApiKeyOpen] = useState(false)

  return (
    <>
      <aside className="sidebar">
        <div className="brand">
          <span className="glyph"><Logo /></span>
          <span className="name">Alembic</span>
        </div>

        <nav className="sidebar-nav">
          {NAV.map(({ to, label, icon, group }) => (
            <div key={to}>
              {group && <div className="nav-group">{group}</div>}
              <NavLink
                to={to}
                end={to === '/'}
                className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
              >
                <span className="nav-ico">{ICONS[icon]}</span>
                <span>{label}</span>
              </NavLink>
            </div>
          ))}
        </nav>

        <div className="sidebar-foot">
          <div className="foot-row">
            <span className={`dot ${apiOnline === null ? 'yel' : apiOnline ? 'green' : 'red'}`} />
            <span>{apiOnline === null ? 'connecting…' : apiOnline ? 'api online' : 'api offline'}</span>
          </div>
          <button
            onClick={() => setApiKeyOpen(true)}
            className="nav-link"
            style={{ fontSize: 11, color: 'var(--fg-3)' }}
          >
            <span className="nav-ico">{ICONS.key}</span>
            <span>API Key</span>
          </button>
        </div>
      </aside>

      <ApiKeyModal open={apiKeyOpen} onClose={() => setApiKeyOpen(false)} />
    </>
  )
}
