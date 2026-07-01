import { Link } from 'react-router-dom'

function path(pathname: string, params: Record<string, string | undefined>) {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value) qs.set(key, value)
  })
  const query = qs.toString()
  return query ? `${pathname}?${query}` : pathname
}

export function SignalTraceLinks({ symbol, compact = false }: { symbol: string; compact?: boolean }) {
  const ticker = symbol.trim().toUpperCase()
  if (!ticker) return null

  const linkStyle: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    minHeight: compact ? 22 : 28,
    padding: compact ? '2px 6px' : '4px 8px',
    borderRadius: 6,
    border: '1px solid var(--border)',
    color: 'var(--blue)',
    background: 'white',
    textDecoration: 'none',
    fontSize: compact ? 11 : 12,
    fontWeight: 700,
    whiteSpace: 'nowrap',
  }

  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
      <Link style={linkStyle} to={path('/news', { ticker })}>News</Link>
      <Link style={linkStyle} to={path('/signals', { symbol: ticker })}>Signal</Link>
      <Link style={linkStyle} to={path('/signals', { tab: 'decisions', symbol: ticker })}>Decision</Link>
      <Link style={linkStyle} to={path('/trading', { symbol: ticker })}>Orders</Link>
      {!compact && <Link style={linkStyle} to="/performance">Performance</Link>}
    </div>
  )
}
