import { useState } from 'react'
import { Link } from 'react-router-dom'

export interface SignalTraceAvailability {
  newsId?: number
  signalId?: number
  decisionId?: number
  orderId?: string
  decisionType?: string
  decisionReason?: string
  decisionSignalScore?: number
  signalCount?: number
  decisionCount?: number
  orderCount?: number
  /** Strategy that originated the traced order (e.g. "S1"). Non-news strategies
   *  legitimately have no news/signal steps — the drawer says so instead of
   *  showing a misleading "not traced". */
  originStrategy?: string
}

const ORIGIN_LABELS: Record<string, string> = {
  S1: 'S1 · momentum',
  S4: 'S4 · news sentiment',
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
  showDrawer = true,
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
  showDrawer?: boolean
  includeNews?: boolean
  includeSignal?: boolean
  includeDecision?: boolean
  includeOrders?: boolean
  includePerformance?: boolean
  availability?: SignalTraceAvailability
  emptyMessage?: string
}) {
  const [drawerOpen, setDrawerOpen] = useState(false)
  const ticker = symbol.trim().toUpperCase()
  if (!ticker) return null
  const hasAvailability = availability !== undefined
  const signalCount = availability?.signalCount ?? 0
  const decisionCount = availability?.decisionCount ?? 0
  const orderCount = availability?.orderCount ?? 0
  const links: { key: string; to: string; text: string; show: boolean; available: boolean; detail: string }[] = [
    {
      key: 'news',
      to: path('/news', { ticker }),
      text: 'News',
      show: includeNews,
      available: !hasAvailability || availability?.newsId !== undefined,
      detail: availability?.newsId ? `News #${availability.newsId}` : 'Ticker news feed',
    },
    {
      key: 'signal',
      to: path('/signals', {
        symbol: ticker,
        signal_id: availability?.signalId ? String(availability.signalId) : undefined,
        news_id: availability?.newsId ? String(availability.newsId) : undefined,
      }),
      text: label('Signal', availability?.signalCount, hasAvailability),
      show: includeSignal && (!hasAvailability || signalCount > 0),
      available: !hasAvailability || signalCount > 0,
      detail: availability?.signalId ? `Signal #${availability.signalId}` : `${signalCount} signal(s)`,
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
      available: !hasAvailability || decisionCount > 0,
      detail: availability?.decisionType
        ? `${availability.decisionType}${availability.decisionSignalScore !== undefined ? ` · score ${availability.decisionSignalScore.toFixed(3)}` : ''}${availability.decisionReason ? ` · ${availability.decisionReason}` : ''}`
        : availability?.decisionId ? `Decision #${availability.decisionId}` : `${decisionCount} decision(s)`,
    },
    {
      key: 'orders',
      to: path('/trading', { symbol: ticker, order_id: availability?.orderId }),
      text: label('Orders', availability?.orderCount, hasAvailability),
      show: includeOrders && (!hasAvailability || orderCount > 0),
      available: !hasAvailability || orderCount > 0,
      detail: availability?.orderId ? `Order ${availability.orderId}` : `${orderCount} order trace(s)`,
    },
    {
      key: 'performance',
      to: '/performance',
      text: 'Performance',
      show: includePerformance && !compact && (!hasAvailability || orderCount > 0),
      available: !hasAvailability || orderCount > 0,
      detail: 'Closed-trade P&L view',
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
  const drawerSteps = links.filter((link) => ['news', 'signal', 'decision', 'orders', 'performance'].includes(link.key))
  const canShowDrawer = showDrawer && visibleLinks.length > 0
  const drawerButtonStyle: React.CSSProperties = {
    ...linkStyle,
    color: 'var(--text)',
    background: '#f8fafc',
    cursor: 'pointer',
  }

  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
      {canShowDrawer && (
        <button type="button" style={drawerButtonStyle} onClick={() => setDrawerOpen(true)}>
          Trace
        </button>
      )}
      {visibleLinks.map(link => (
        <Link key={link.key} style={linkStyle} to={link.to}>{link.text}</Link>
      ))}
      {drawerOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={`Causal trace for ${ticker}`}
          onClick={() => setDrawerOpen(false)}
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 1000,
            background: 'rgba(15, 23, 42, 0.36)',
            display: 'flex',
            justifyContent: 'flex-end',
          }}
        >
          <aside
            onClick={(event) => event.stopPropagation()}
            style={{
              width: 'min(420px, 100vw)',
              height: '100%',
              background: 'white',
              borderLeft: '1px solid var(--border)',
              boxShadow: '-18px 0 40px rgba(15, 23, 42, 0.18)',
              padding: 20,
              overflowY: 'auto',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start', marginBottom: 18 }}>
              <div>
                <h3 style={{ margin: 0, fontSize: 18, fontWeight: 800 }}>Trace {ticker}</h3>
                <p style={{ margin: '4px 0 0', color: 'var(--text-muted)', fontSize: 12 }}>
                  News to signal to decision to order to P&L.
                </p>
              </div>
              <button
                type="button"
                className="btn-ghost"
                onClick={() => setDrawerOpen(false)}
                aria-label="Close trace"
                style={{ padding: '4px 8px', fontSize: 12 }}
              >
                Close
              </button>
            </div>

            <div style={{ display: 'grid', gap: 10 }}>
              {drawerSteps.map((step, index) => {
                const isVisible = step.available
                const title = step.key === 'orders' ? 'Orders' : step.text.replace(/\s\(\d+\)$/, '')
                // A non-news strategy (e.g. S1 momentum) has no news/signal by
                // design: show the origin instead of "not traced".
                const origin = availability?.originStrategy
                const showOrigin = !isVisible
                  && !!origin
                  && origin !== 'S4'
                  && (step.key === 'news' || step.key === 'signal')
                const originLabel = origin ? (ORIGIN_LABELS[origin] ?? `origin: ${origin}`) : ''
                return (
                  <div
                    key={step.key}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '28px 1fr',
                      gap: 10,
                      alignItems: 'start',
                    }}
                  >
                    <div style={{
                      width: 26,
                      height: 26,
                      borderRadius: 999,
                      display: 'grid',
                      placeItems: 'center',
                      fontSize: 12,
                      fontWeight: 800,
                      background: isVisible ? '#dbeafe' : '#f1f5f9',
                      color: isVisible ? '#1d4ed8' : 'var(--text-muted)',
                    }}>
                      {index + 1}
                    </div>
                    <div style={{
                      border: '1px solid var(--border)',
                      borderRadius: 8,
                      padding: '9px 10px',
                      background: isVisible ? 'white' : '#f8fafc',
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center' }}>
                        <strong style={{ fontSize: 13 }}>{title}</strong>
                        <span className={`badge ${isVisible ? 'badge-blue' : 'badge-grey'}`}>
                          {isVisible ? 'available' : showOrigin ? originLabel : 'not traced'}
                        </span>
                      </div>
                      <div style={{ marginTop: 4, color: 'var(--text-muted)', fontSize: 12, overflowWrap: 'anywhere' }}>
                        {isVisible
                          ? step.detail
                          : showOrigin
                            ? `Order originated from ${originLabel} (price-based strategy) — no news is expected for this order.`
                            : 'No linked downstream record for this item.'}
                      </div>
                      {isVisible && (
                        <Link
                          to={step.to}
                          onClick={() => setDrawerOpen(false)}
                          style={{
                            display: 'inline-flex',
                            marginTop: 8,
                            color: 'var(--blue)',
                            fontSize: 12,
                            fontWeight: 700,
                            textDecoration: 'none',
                          }}
                        >
                          Open {title}
                        </Link>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </aside>
        </div>
      )}
    </div>
  )
}
