import { useState } from 'react'

const TABS = [
  { id: 'alembic-overview', label: 'Overview' },
  { id: 'alembic-risk',     label: 'Risk Monitor' },
] as const

type TabId = typeof TABS[number]['id']

export default function DashboardPage() {
  const [active, setActive] = useState<TabId>('alembic-overview')
  const hostname = window.location.hostname
  const grafanaBase = `http://${hostname}:3001`
  const src = `${grafanaBase}/d/${active}?kiosk=1&theme=dark&refresh=5m`

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', padding: '0 0 0 0' }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '12px 20px',
        borderBottom: '1px solid var(--border)',
        background: 'var(--surface)',
      }}>
        <span style={{ color: 'var(--text)', fontWeight: 600, fontSize: 15, marginRight: 8 }}>
          Monitoring
        </span>
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActive(tab.id)}
            style={{
              padding: '5px 14px',
              fontSize: 13,
              fontWeight: active === tab.id ? 600 : 400,
              color: active === tab.id ? 'white' : 'var(--text-muted)',
              background: active === tab.id ? 'var(--blue)' : 'transparent',
              border: `1px solid ${active === tab.id ? 'var(--blue)' : 'var(--border)'}`,
              borderRadius: 4,
              cursor: 'pointer',
            }}
          >
            {tab.label}
          </button>
        ))}
        <a
          href={`${grafanaBase}/d/${active}`}
          target="_blank"
          rel="noopener noreferrer"
          style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-muted)', textDecoration: 'none' }}
        >
          Open in Grafana ↗
        </a>
      </div>
      <iframe
        key={src}
        src={src}
        title={`Grafana ${active}`}
        sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
        style={{
          flex: 1,
          width: '100%',
          border: 'none',
          minHeight: 0,
        }}
      />
    </div>
  )
}
