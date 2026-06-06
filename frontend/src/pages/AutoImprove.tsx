import { useQuery } from '@tanstack/react-query'
import { fetchFeedbackStatus, fetchCounterfactualSummary } from '@/api/trades'

const fmt = (v: number | null | undefined, digits = 2) =>
  v == null ? '—' : v.toFixed(digits)

const fmtPct = (v: number | null | undefined) =>
  v == null ? '—' : `${(v * 100).toFixed(1)}%`

const fmtSign = (v: number | null | undefined) => {
  if (v == null) return '—'
  const s = v >= 0 ? '+' : ''
  return `${s}${(v * 100).toFixed(2)}%`
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <h3 style={{ margin: '0 0 16px', fontSize: 15, fontWeight: 600, color: 'var(--text-muted)' }}>
        {title}
      </h3>
      {children}
    </div>
  )
}

function StatusDot({ active }: { active: boolean }) {
  return (
    <span style={{
      display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
      background: active ? '#f59e0b' : '#22c55e',
      marginRight: 6,
    }} />
  )
}

function Stat({
  label, value, sub, highlight = false,
}: {
  label: string
  value: React.ReactNode
  sub?: string
  highlight?: boolean
}) {
  return (
    <div>
      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color: highlight ? '#f59e0b' : 'inherit' }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{sub}</div>}
    </div>
  )
}

const th: React.CSSProperties = { padding: '4px 12px 8px 0', fontWeight: 500 }
const td: React.CSSProperties = { padding: '8px 12px 8px 0' }

export default function AutoImprove() {
  const { data: feedback, isLoading: fbLoading } = useQuery({
    queryKey: ['feedback-status'],
    queryFn: fetchFeedbackStatus,
    refetchInterval: 60_000,
  })

  const { data: counterfactual, isLoading: cfLoading } = useQuery({
    queryKey: ['counterfactual-7d'],
    queryFn: () => fetchCounterfactualSummary(7),
    refetchInterval: 300_000,
  })

  return (
    <div>
      <h2 style={{ margin: '0 0 4px', fontSize: 20, fontWeight: 700 }}>Auto-Improve</h2>
      <p style={{ margin: '0 0 24px', color: 'var(--text-muted)', fontSize: 14 }}>
        Automatic strategy adjustments triggered by live performance.
      </p>

      {/* Phase B: Loss Feedback */}
      <Card title="Phase B — Loss Feedback Loop">
        {fbLoading ? (
          <p style={{ color: 'var(--text-muted)' }}>Loading…</p>
        ) : !feedback ? (
          <p style={{ color: 'var(--text-muted)' }}>Unavailable</p>
        ) : (
          <>
            <div style={{ display: 'flex', gap: 32, flexWrap: 'wrap', marginBottom: 16 }}>
              <Stat
                label="Entry Threshold"
                value={fmt(feedback.entry_threshold, 2)}
                sub={`baseline ${fmt(feedback.entry_threshold_baseline, 2)}`}
                highlight={feedback.adjustment_active && feedback.entry_threshold > feedback.entry_threshold_baseline}
              />
              <Stat
                label="Regime Scale"
                value={`${fmt(feedback.regime_scale, 2)}×`}
                sub={feedback.regime_scale < 1 ? 'reduced by feedback' : 'normal'}
                highlight={feedback.regime_scale < 1}
              />
              <Stat
                label="Status"
                value={
                  <span style={{ fontSize: 16 }}>
                    <StatusDot active={feedback.adjustment_active} />
                    {feedback.adjustment_active ? 'Adjustment active' : 'At baseline'}
                  </span>
                }
                sub={feedback.last_reason ?? ''}
              />
            </div>

            {feedback.adjustment_active && (
              <div style={{
                background: 'rgba(245,158,11,0.10)',
                border: '1px solid rgba(245,158,11,0.3)',
                borderRadius: 8, padding: '10px 14px', fontSize: 13,
              }}>
                <strong>Last trigger:</strong>{' '}
                {feedback.consecutive_losses != null && `${feedback.consecutive_losses} consecutive losses`}
                {feedback.rolling_net_pnl != null && ` · rolling P&L $${feedback.rolling_net_pnl.toFixed(2)}`}
                {feedback.last_adjustment_ts && (
                  <span style={{ color: 'var(--text-muted)', marginLeft: 8 }}>
                    ({new Date(feedback.last_adjustment_ts).toLocaleString()})
                  </span>
                )}
              </div>
            )}

            <p style={{ margin: '12px 0 0', fontSize: 12, color: 'var(--text-muted)' }}>
              Checked every 30 min during market hours. Raises threshold after 3 consecutive losses
              or negative rolling P&L (last 10 trades). Recovers after 5 consecutive wins.
              Adjustments expire after 48 h.
            </p>
          </>
        )}
      </Card>

      {/* Phase C: Counterfactual / Opportunity Cost */}
      <Card title="Phase C — Opportunity Cost (last 7 days)">
        {cfLoading ? (
          <p style={{ color: 'var(--text-muted)' }}>Loading…</p>
        ) : !counterfactual || counterfactual.length === 0 ? (
          <p style={{ color: 'var(--text-muted)' }}>
            No data yet — counterfactual returns are computed nightly at 22:45 UTC.
            Data will appear after the first day of paper trading.
          </p>
        ) : (
          <>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ color: 'var(--text-muted)', textAlign: 'left' }}>
                  <th style={th}>Decision</th>
                  <th style={th}>Skips</th>
                  <th style={th}>Computed</th>
                  <th style={th}>Avg 1h return</th>
                  <th style={th}>% Profitable</th>
                  <th style={th}>Upside missed</th>
                </tr>
              </thead>
              <tbody>
                {counterfactual.map(row => (
                  <tr key={row.decision} style={{ borderTop: '1px solid var(--border)' }}>
                    <td style={td}>
                      <span style={{
                        background: row.decision === 'SKIP_EMA'
                          ? 'rgba(99,102,241,0.15)' : 'rgba(249,115,22,0.15)',
                        color: row.decision === 'SKIP_EMA' ? '#818cf8' : '#fb923c',
                        borderRadius: 4, padding: '2px 6px', fontSize: 11, fontWeight: 600,
                      }}>
                        {row.decision}
                      </span>
                    </td>
                    <td style={td}>{row.total_skips}</td>
                    <td style={td}>{row.computed}</td>
                    <td style={{ ...td, color: row.avg_return >= 0 ? '#4ade80' : '#f87171' }}>
                      {fmtSign(row.avg_return)}
                    </td>
                    <td style={td}>{fmtPct(row.pct_profitable)}</td>
                    <td style={{ ...td, color: row.sum_positive_returns > 0 ? '#f59e0b' : 'inherit' }}>
                      {fmtSign(row.sum_positive_returns)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            <p style={{ margin: '12px 0 0', fontSize: 12, color: 'var(--text-muted)' }}>
              <strong>SKIP_EMA</strong>: price was below EMA20 — would the trade have been profitable
              anyway? <strong>SKIP_CAP</strong>: cycle allocation cap was hit — what did we leave on
              the table? <em>Upside missed</em> = sum of positive 1-hour returns across all skipped
              signals. SKIP_POSITION (already open) is excluded.
            </p>
          </>
        )}
      </Card>
    </div>
  )
}
