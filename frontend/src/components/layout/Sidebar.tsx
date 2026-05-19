import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { ModeBadge } from './ModeBadge'
import { ApiKeyModal } from './ApiKeyModal'

const NAV = [
  { to: '/',            label: 'Overview',    icon: '⊞' },
  { to: '/signals',     label: 'Signals',     icon: '⚡' },
  { to: '/trading',     label: 'Trading',     icon: '📈' },
  { to: '/performance', label: 'Performance', icon: '📊' },
  { to: '/news',        label: 'News',        icon: '📰' },
  { to: '/llm',         label: 'LLM',         icon: '🤖' },
  { to: '/config',      label: 'Config',      icon: '⚙' },
  { to: '/admin',       label: 'Admin',       icon: '🔒' },
]

export function Sidebar() {
  const [apiKeyOpen, setApiKeyOpen] = useState(false)

  return (
    <>
      <nav style={{
        width: 'var(--sidebar-w)',
        minWidth: 'var(--sidebar-w)',
        background: '#1e293b',
        display: 'flex',
        flexDirection: 'column',
        minHeight: '100vh',
        position: 'sticky',
        top: 0,
      }}>
        <div style={{ padding: '16px 12px 12px', display: 'flex', alignItems: 'center', gap: 8, borderBottom: '1px solid #334155', marginBottom: 4 }}>
          <img src="/alembic.png" alt="Alembic" style={{ width: 32, height: 32, borderRadius: 6, objectFit: 'cover' }} />
          <div>
            <div style={{ color: 'white', fontWeight: 700, fontSize: 14, letterSpacing: '-0.3px', lineHeight: 1.1 }}>Alembic</div>
            <div style={{ color: '#64748b', fontSize: 10, fontWeight: 500, letterSpacing: '0.05em', textTransform: 'uppercase' }}>Open Source Finance</div>
          </div>
        </div>

        <div style={{ flex: 1, padding: '4px 0' }}>
          {NAV.map(({ to, label, icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              style={({ isActive }) => ({
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '9px 14px',
                color: isActive ? 'white' : '#94a3b8',
                background: isActive ? 'var(--blue)' : 'transparent',
                borderRadius: 6,
                margin: '1px 6px',
                textDecoration: 'none',
                fontSize: 13,
                fontWeight: isActive ? 600 : 400,
                transition: 'background 0.15s',
              })}
            >
              <span>{icon}</span>
              <span>{label}</span>
            </NavLink>
          ))}
        </div>

        <div style={{ padding: '12px 14px', borderTop: '1px solid #334155' }}>
          <ModeBadge />
          <button
            onClick={() => setApiKeyOpen(true)}
            style={{ marginTop: 10, width: '100%', background: 'transparent', color: '#94a3b8', border: '1px solid #334155', fontSize: 12 }}
          >
            ⚙ API Key
          </button>
        </div>
      </nav>

      <ApiKeyModal open={apiKeyOpen} onClose={() => setApiKeyOpen(false)} />
    </>
  )
}
