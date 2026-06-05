import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
  ResponsiveContainer,
} from 'recharts'
import { fetchPnL } from '@/api/performance'
import { fetchTradesSummary } from '@/api/trades'
import { HelpButton } from '@/components/shared/HelpButton'

const PERIODS = ['1M', '3M', '6M', '1Y'] as const
type Period = typeof PERIODS[number]

export default function Performance() {
  const [period, setPeriod] = useState<Period>('6M')

  const { data: pnl, isLoading } = useQuery({
    queryKey: ['pnl', period],
    queryFn: () => fetchPnL(period),
  })

  const { data: tradeSummary } = useQuery({
    queryKey: ['trades-summary-perf', 30],
    queryFn: () => fetchTradesSummary(30),
    refetchInterval: 300000,
  })

  const daily = pnl?.daily ?? []
  const monthly = pnl?.monthly ?? []

  const cumulativeData = useMemo(() => {
    let cumPnL = 0
    return daily.map((d) => {
      cumPnL += d.profit_loss ?? 0
      return { date: d.date, cumulative: parseFloat(cumPnL.toFixed(2)), equity: d.equity }
    })
  }, [daily])

  return (
    <div style={{ position: 'relative' }}>
      <HelpButton title="Performance — Rendimento" sections={[
        {
          heading: "Come leggere i grafici",
          content: "**Cumulative P&L**: il profitto/perdita cumulativo nel periodo selezionato. Linea blu che sale = profitto, che scende = perdita.\n\n**Portfolio Equity**: il valore totale del portafoglio nel tempo. Linea verde.",
        },
        {
          heading: "Periodi disponibili",
          content: "1M, 3M, 6M, 1Y. I dati vengono dal worker di performance che gira ogni giorno alle 22:00 UTC. Se non vedi dati, potrebbe non esserci ancora un ciclo completo.",
        },
        {
          heading: "Monthly P&L Summary",
          content: "La tabella in basso mostra P&L mensile aggregato. ▲ Gain = mese positivo, ▼ Loss = mese negativo. Utile per verificare la consistenza del rendimento.",
        },
      ]} />
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

      {tradeSummary && tradeSummary.total_trades > 0 && (
        <div style={{ marginTop: 32 }}>
          <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 600 }}>Trade Activity (last 30d)</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <div style={{ background: '#1e293b', borderRadius: 8, padding: 16 }}>
              <div style={{ fontSize: 13, color: '#94a3b8', marginBottom: 12 }}>Summary</div>
              {[
                ['Trades', String(tradeSummary.total_trades)],
                ['Trades/week', tradeSummary.trades_per_week.toFixed(1)],
                ['Win rate', `${(tradeSummary.win_rate * 100).toFixed(1)}%`],
                ['Avg net P&L', `$${tradeSummary.avg_net_pnl.toFixed(2)}`],
                ['Total net P&L', `$${tradeSummary.total_net_pnl.toFixed(2)}`],
                ['Avg hold', `${tradeSummary.avg_hold_minutes.toFixed(0)}min`],
                ['Slippage % gross', `${(tradeSummary.slippage_pct_of_gross * 100).toFixed(1)}%`],
              ].map(([label, value]) => (
                <div key={label} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #0f172a', fontSize: 13 }}>
                  <span style={{ color: '#64748b' }}>{label}</span>
                  <span style={{ fontWeight: 600 }}>{value}</span>
                </div>
              ))}
            </div>
            <div style={{ background: '#1e293b', borderRadius: 8, padding: 16 }}>
              <div style={{ fontSize: 13, color: '#94a3b8', marginBottom: 12 }}>Notional & P&L</div>
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={[
                  { label: 'Total Notional', value: tradeSummary.total_notional },
                  { label: 'Gross P&L', value: tradeSummary.total_gross_pnl },
                  { label: 'Net P&L', value: tradeSummary.total_net_pnl },
                ]}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="label" tick={{ fill: '#94a3b8', fontSize: 10 }} />
                  <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} tickFormatter={v => `$${v}`} />
                  <Tooltip formatter={(v) => [`$${Number(v).toFixed(2)}`]} />
                  <Bar dataKey="value" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
