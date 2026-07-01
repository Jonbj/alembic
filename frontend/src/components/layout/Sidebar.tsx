import { NavLink } from 'react-router-dom'
import { ModeBadge } from './ModeBadge'
import { useStore } from '@/store'
import alembicLogo from '@/assets/alembic.png'

const NAV = [
  { to: '/',            label: 'Overview',    icon: '⊞' },
  { to: '/operations',  label: 'Operations',  icon: '⚙' },
  { to: '/news',        label: 'News',        icon: '📰' },
  { to: '/signals',     label: 'Signals',     icon: '⚡' },
  { to: '/quality',     label: 'Quality',     icon: '🔬' },
  { to: '/trading',     label: 'Trading',     icon: '📈' },
  { to: '/performance',   label: 'Performance',  icon: '📊' },
  { to: '/strategies',  label: 'Strategies',  icon: '🎯' },
  { to: '/auto-improve',  label: 'Auto-Improve', icon: '🔧' },
  { to: '/validation',  label: 'Validation',  icon: '🧪' },
  { to: '/labeling',    label: 'Labeling',    icon: '🏷️' },
  { to: '/llm',         label: 'LLM',         icon: '🤖' },
  { to: '/backtest',    label: 'Backtest',    icon: '🔬' },
  { to: '/dashboard',  label: 'Dashboard',   icon: '📡' },
  { to: '/docs',        label: 'Docs',        icon: '📖' },
]

export function Sidebar() {
  const { token, logout, llmModels, setLlmModels } = useStore()
  const isSavings = llmModels !== 'all'

  const toggleSavings = async () => {
    const next = isSavings ? 'all' : 'glm'
    try {
      const res = await fetch('/api/admin/llm-models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ models: next }),
      })
      if (res.ok) {
        setLlmModels(next)
      } else {
        console.warn(`LLM model toggle failed: ${res.status}`)
      }
    } catch { /* network error — no state change */ }
  }

  const handleLogout = () => {
    logout()
    window.location.href = '/login'
  }

  return (
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
        <img src={alembicLogo} alt="Alembic" style={{ width: 32, height: 32, borderRadius: 6, objectFit: 'cover' }} />
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
          onClick={toggleSavings}
          title={isSavings ? 'Economy mode (1 model) — click for full ensemble' : 'Full ensemble (4 models) — click for economy mode'}
          style={{
            marginTop: 8,
            width: '100%',
            background: isSavings ? '#92400e' : 'transparent',
            color: isSavings ? '#fcd34d' : '#94a3b8',
            border: `1px solid ${isSavings ? '#b45309' : '#334155'}`,
            fontSize: 11,
            padding: '5px 8px',
            display: 'flex',
            alignItems: 'center',
            gap: 5,
          }}
        >
          <span>{isSavings ? '🪙' : '⚡'}</span>
          <span>{isSavings ? 'Economy (GLM)' : 'Full ensemble'}</span>
        </button>
        <button
          onClick={handleLogout}
          style={{ marginTop: 6, width: '100%', background: 'transparent', color: '#94a3b8', border: '1px solid #334155', fontSize: 12 }}
        >
          ⏻ Logout
        </button>
      </div>
    </nav>
  )
}
