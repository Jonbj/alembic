import { Link } from 'react-router-dom'

export interface SignalTraceAvailability {
  newsId?: number
  signalId?: number
  decisionId?: number
  orderId?: string
  signalCount?: number
  decisionCount?: number
  orderCount?: number
}

function path(pathname: string, params: Record<string, string | undefined>) {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value) qs.set(key, value)
  })
  const query = qs.toString()
  return query ? `${pathname}?${query}` : pathname
}

function label(base: string, count: number | undefined, showCounts: boolean) {
  return showCounts && count !== undefined ? `${base} (${count})` : base
}

export function SignalTraceLinks({
  symbol,
  compact = false,
  includeNews = true,
  includeSignal = true,
  includeDecision = true,
  includeOrders = true,
  includePerformance = true,
  availability,
  emptyMessage,
}: {
  symbol: string
  compact?: boolean
  includeNews?: boolean
  includeSignal?: boolean
  includeDecision?: boolean
  includeOrders?: boolean
  includePerformance?: boolean
  availability?: SignalTraceAvailability
  emptyMessage?: string
}) {
  const ticker = symbol.trim().toUpperCase()
  if (!ticker) return null
  const hasAvailability = availability !== undefined
  const signalCount = availability?.signalCount ?? 0
  const decisionCount = availability?.decisionCount ?? 0
  const orderCount = availability?.orderCount ?? 0
  const links: { key: string; to: string; text: string; show: boolean }[] = [
    { key: 'news', to: path('/news', { ticker }), text: 'News', show: includeNews },
    {
      key: 'signal',
      to: path('/signals', {
        symbol: ticker,
        signal_id: availability?.signalId ? String(availability.signalId) : undefined,
        news_id: availability?.newsId ? String(availability.newsId) : undefined,
      }),
      text: label('Signal', availability?.signalCount, hasAvailability),
      show: includeSignal && (!hasAvailability || signalCount > 0),
    },
    {
      key: 'decision',
      to: path('/signals', {
        tab: 'decisions',
        symbol: ticker,
        decision_id: availability?.decisionId ? String(availability.decisionId) : undefined,
      }),
      text: label('Decision', availability?.decisionCount, hasAvailability),
      show: includeDecision && (!hasAvailability || decisionCount > 0),
    },
    {
      key: 'orders',
      to: path('/trading', { symbol: ticker, order_id: availability?.orderId }),
      text: label('Orders', availability?.orderCount, hasAvailability),
      show: includeOrders && (!hasAvailability || orderCount > 0),
    },
    {
      key: 'performance',
      to: '/performance',
      text: 'Performance',
      show: includePerformance && !compact && (!hasAvailability || orderCount > 0),
    },
  ]
  const visibleLinks = links.filter(link => link.show)
  if (visibleLinks.length === 0) {
    return emptyMessage ? (
      <span style={{ color: 'var(--text-muted)', fontSize: compact ? 11 : 12 }}>
        {emptyMessage}
      </span>
    ) : null
  }

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
      {visibleLinks.map(link => (
        <Link key={link.key} style={linkStyle} to={link.to}>{link.text}</Link>
      ))}
    </div>
  )
}
