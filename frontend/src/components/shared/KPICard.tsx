import { useState } from 'react'

export function KPICard({ label, value, sub, tooltip }: { label: string; value: string; sub?: string; tooltip?: string }) {
  const [show, setShow] = useState(false)
  return (
    <div className="card" style={{ flex: 1, minWidth: 160, position: 'relative' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <div style={{ color: 'var(--text-muted)', fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</div>
        {tooltip && (
          <span
            onMouseEnter={() => setShow(true)}
            onMouseLeave={() => setShow(false)}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 16,
              height: 16,
              borderRadius: '50%',
              background: 'var(--text-muted)',
              color: 'white',
              fontSize: 10,
              fontWeight: 700,
              cursor: 'help',
              flexShrink: 0,
              userSelect: 'none',
            }}
          >
            ?
          </span>
        )}
      </div>
      <div style={{ fontSize: 26, fontWeight: 700, margin: '6px 0 2px' }}>{value}</div>
      {sub && <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>{sub}</div>}
      {tooltip && show && (
        <div style={{
          position: 'absolute',
          bottom: '100%',
          left: '50%',
          transform: 'translateX(-50%)',
          background: '#1e293b',
          color: '#e2e8f0',
          border: '1px solid #334155',
          borderRadius: 6,
          padding: '8px 12px',
          fontSize: 12,
          lineHeight: 1.5,
          maxWidth: 260,
          zIndex: 100,
          boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
          whiteSpace: 'normal',
          marginBottom: 4,
        }}>
          {tooltip}
        </div>
      )}
    </div>
  )
}
