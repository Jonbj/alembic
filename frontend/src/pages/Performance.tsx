import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid,
  ResponsiveContainer,
} from 'recharts'
import { fetchPnL } from '@/api/performance'

const PERIODS = ['1M', '3M', '6M', '1Y'] as const
type Period = typeof PERIODS[number]

export default function Performance() {
  const [period, setPeriod] = useState<Period>('6M')

  const { data: pnl, isLoading } = useQuery({
    queryKey: ['pnl', period],
    queryFn: () => fetchPnL(period),
  })

  const daily = pnl?.daily ?? []
  const monthly = pnl?.monthly ?? []

  // Compute cumulative P&L from daily
  let cumPnL = 0
  const cumulativeData = daily.map((d) => {
    cumPnL += d.profit_loss ?? 0
    return { date: d.date, cumulative: parseFloat(cumPnL.toFixed(2)), equity: d.equity }
  })

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 20 }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>Performance</h2>
        <div style={{ display: 'flex', gap: 4 }}>
          {PERIODS.map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              style={{
                padding: '4px 10px',
                fontSize: 12,
                background: period === p ? 'var(--blue)' : 'transparent',
                color: period === p ? 'white' : 'var(--text-muted)',
                border: '1px solid var(--border)',
              }}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {isLoading && <p style={{ color: 'var(--text-muted)' }}>Loading...</p>}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 }}>
        <div className="card">
          <h3 style={{ margin: '0 0 16px', fontSize: 14, fontWeight: 600 }}>Cumulative P&L</h3>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={cumulativeData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="date" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `$${v}`} />
              <Tooltip formatter={(v) => [`$${Number(v).toFixed(2)}`, 'Cumulative P&L']} />
              <Line type="monotone" dataKey="cumulative" stroke="#3b82f6" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <h3 style={{ margin: '0 0 16px', fontSize: 14, fontWeight: 600 }}>Portfolio Equity</h3>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={cumulativeData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="date" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `$${(v/1000).toFixed(0)}k`} />
              <Tooltip formatter={(v) => [`$${Number(v).toFixed(2)}`, 'Equity']} />
              <Line type="monotone" dataKey="equity" stroke="#16a34a" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="card">
        <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>Monthly P&L Summary</h3>
        <table>
          <thead><tr><th>Month</th><th>P&L</th><th>Direction</th></tr></thead>
          <tbody>
            {monthly.map((m) => (
              <tr key={m.month}>
                <td>{m.month}</td>
                <td style={{ color: m.pnl >= 0 ? 'var(--green)' : 'var(--red)', fontWeight: 600 }}>
                  {m.pnl >= 0 ? '+' : ''}${m.pnl.toFixed(2)}
                </td>
                <td>
                  <span className={`badge ${m.pnl >= 0 ? 'badge-green' : 'badge-red'}`}>
                    {m.pnl >= 0 ? '▲ Gain' : '▼ Loss'}
                  </span>
                </td>
              </tr>
            ))}
            {monthly.length === 0 && !isLoading && (
              <tr><td colSpan={3} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>No data</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
