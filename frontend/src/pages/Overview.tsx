import { useQuery } from '@tanstack/react-query'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { fetchSignals } from '@/api/signals'
import { fetchPositions } from '@/api/positions'
import { fetchPnL } from '@/api/performance'

function KPICard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="card" style={{ flex: 1, minWidth: 160 }}>
      <div style={{ color: 'var(--text-muted)', fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 700, margin: '6px 0 2px' }}>{value}</div>
      {sub && <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>{sub}</div>}
    </div>
  )
}

function directionBadge(score: number) {
  if (score > 0.1) return <span className="badge badge-green">BUY ▲</span>
  if (score < -0.1) return <span className="badge badge-red">SELL ▼</span>
  return <span className="badge badge-grey">HOLD —</span>
}

export default function Overview() {
  const { data: signals = [] } = useQuery({ queryKey: ['signals'], queryFn: () => fetchSignals(), refetchInterval: 60000 })
  const { data: positions = [] } = useQuery({ queryKey: ['positions'], queryFn: fetchPositions, refetchInterval: 60000 })
  const { data: pnl } = useQuery({ queryKey: ['pnl'], queryFn: () => fetchPnL('6M'), refetchInterval: 300000 })

  const buys = signals.filter((s) => s.score > 0.1).length
  const sells = signals.filter((s) => s.score < -0.1).length
  const holds = signals.length - buys - sells

  const totalUnrealized = positions.reduce((acc, p) => acc + parseFloat(p.unrealized_pl || '0'), 0)
  const monthlyPnL = pnl?.monthly ?? []
  const currentMonthPnL = monthlyPnL[monthlyPnL.length - 1]?.pnl ?? 0

  return (
    <div>
      <h2 style={{ margin: '0 0 20px', fontSize: 20, fontWeight: 700 }}>Overview</h2>

      <div style={{ display: 'flex', gap: 16, marginBottom: 24, flexWrap: 'wrap' }}>
        <KPICard label="Net P&L (month)" value={`$${currentMonthPnL.toFixed(2)}`} sub="current month" />
        <KPICard label="Open positions" value={String(positions.length)} sub={positions.map((p) => p.symbol).join(', ') || '—'} />
        <KPICard label="Unrealized P&L" value={`$${totalUnrealized.toFixed(2)}`} />
        <KPICard label="Signals today" value={`${buys}B / ${sells}S / ${holds}H`} sub={`${signals.length} total`} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 24 }}>
        <div className="card">
          <h3 style={{ margin: '0 0 16px', fontSize: 14, fontWeight: 600 }}>Monthly P&L</h3>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={monthlyPnL}>
              <XAxis dataKey="month" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v) => [`$${Number(v).toFixed(2)}`, 'P&L']} />
              <Bar dataKey="pnl" radius={[3, 3, 0, 0]}>
                {monthlyPnL.map((entry, i) => (
                  <Cell key={i} fill={entry.pnl >= 0 ? '#16a34a' : '#dc2626'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>Open Positions</h3>
          {positions.length === 0 ? (
            <p style={{ color: 'var(--text-muted)' }}>No open positions</p>
          ) : (
            <table>
              <thead><tr><th>Ticker</th><th>Qty</th><th>P&L</th><th>P&L%</th></tr></thead>
              <tbody>
                {positions.map((p) => (
                  <tr key={p.symbol}>
                    <td><strong>{p.symbol}</strong></td>
                    <td>{p.qty}</td>
                    <td style={{ color: parseFloat(p.unrealized_pl) >= 0 ? 'var(--green)' : 'var(--red)' }}>
                      ${parseFloat(p.unrealized_pl).toFixed(2)}
                    </td>
                    <td>{(parseFloat(p.unrealized_plpc) * 100).toFixed(2)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="card">
        <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>Latest Signals</h3>
        <table>
          <thead><tr><th>Ticker</th><th>Direction</th><th>Score</th><th>Confidence</th><th>Model</th><th>Time</th></tr></thead>
          <tbody>
            {signals.slice(0, 10).map((s, i) => (
              <tr key={i}>
                <td><strong>{s.symbol}</strong></td>
                <td>{directionBadge(s.score)}</td>
                <td>{s.score.toFixed(3)}</td>
                <td>{(s.confidence * 100).toFixed(0)}%</td>
                <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>{s.model_id}</td>
                <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>{new Date(s.generated_at).toLocaleTimeString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
