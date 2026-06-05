import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer,
} from 'recharts'
import { fetchTrades, fetchTradesSummary, type Trade, type TradeStatus, type SummaryPeriod } from '@/api/trades'

const PERIODS: SummaryPeriod[] = [7, 30, 90]

function fmt(v: number | null, prefix = '$') {
  if (v == null) return '—'
  return `${prefix}${v.toFixed(2)}`
}

function fmtPct(v: number | null) {
  if (v == null) return '—'
  return `${(v * 100).toFixed(1)}%`
}

function holdLabel(mins: number | null) {
  if (mins == null) return '—'
  if (mins < 60) return `${Math.round(mins)}m`
  return `${(mins / 60).toFixed(1)}h`
}

export default function Trades() {
  const [period, setPeriod] = useState<SummaryPeriod>(7)
  const [statusFilter, setStatusFilter] = useState<TradeStatus>('all')
  const [symbolFilter, setSymbolFilter] = useState('')
  const [expandedId, setExpandedId] = useState<number | null>(null)

  const { data: summary } = useQuery({
    queryKey: ['trades-summary', period],
    queryFn: () => fetchTradesSummary(period),
    refetchInterval: 120000,
  })

  const { data: trades = [], isLoading } = useQuery({
    queryKey: ['trades', statusFilter, period],
    queryFn: () => fetchTrades(undefined, statusFilter, 200),
    refetchInterval: 120000,
  })

  const filtered = useMemo(() =>
    (trades as Trade[]).filter((t: Trade) =>
      !symbolFilter || t.symbol.toLowerCase().includes(symbolFilter.toLowerCase())
    ), [trades, symbolFilter])

  const cumulativeData = useMemo(() => {
    const closed = filtered
      .filter(t => t.exit_time && t.net_pnl != null)
      .sort((a, b) => (a.exit_time! > b.exit_time! ? 1 : -1))
    let cum = 0
    return closed.map(t => {
      cum += t.net_pnl!
      return { date: t.exit_time!.slice(0, 10), cumulative: parseFloat(cum.toFixed(2)) }
    })
  }, [filtered])

  const lineColor = (cumulativeData.at(-1)?.cumulative ?? 0) >= 0 ? '#22c55e' : '#ef4444'
  const totalNetPnl = summary?.total_net_pnl ?? 0

  return (
    <div style={{ position: 'relative' }}>
      <h2 style={{ margin: '0 0 20px', fontSize: 20, fontWeight: 700 }}>Trades</h2>

      <div style={{ display: 'flex', gap: 4, marginBottom: 20 }}>
        {PERIODS.map(p => (
          <button
            key={p}
            onClick={() => setPeriod(p)}
            style={{
              padding: '4px 12px', borderRadius: 6, border: 'none', cursor: 'pointer',
              background: period === p ? '#3b82f6' : '#334155',
              color: 'white', fontSize: 13,
            }}
          >{p}d</button>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24 }}>
        {[
          { label: 'Total Trades', value: String(summary?.total_trades ?? '—') },
          { label: 'Win Rate', value: fmtPct(summary?.win_rate ?? null) },
          { label: 'Avg Net P&L', value: fmt(summary?.avg_net_pnl ?? null) },
          { label: 'Total Net P&L', value: fmt(totalNetPnl), color: totalNetPnl >= 0 ? '#22c55e' : '#ef4444' },
        ].map(c => (
          <div key={c.label} style={{ background: '#1e293b', borderRadius: 8, padding: '14px 16px' }}>
            <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>{c.label}</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: (c as { color?: string }).color ?? 'white' }}>{c.value}</div>
          </div>
        ))}
      </div>

      {cumulativeData.length > 0 && (
        <div style={{ background: '#1e293b', borderRadius: 8, padding: 16, marginBottom: 24 }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>Cumulative Net P&L</div>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={cumulativeData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="date" tick={{ fill: '#94a3b8', fontSize: 11 }} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} tickFormatter={v => `$${v}`} />
              <Tooltip formatter={(v: number) => [`$${v.toFixed(2)}`, 'Cumulative']} />
              <Line type="monotone" dataKey="cumulative" stroke={lineColor} dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <input
          value={symbolFilter}
          onChange={e => setSymbolFilter(e.target.value)}
          placeholder="Filter symbol…"
          style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #334155', background: '#0f172a', color: 'white', fontSize: 13, width: 140 }}
        />
        {(['all', 'open', 'closed'] as TradeStatus[]).map(s => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            style={{
              padding: '4px 12px', borderRadius: 6, border: 'none', cursor: 'pointer',
              background: statusFilter === s ? '#3b82f6' : '#334155',
              color: 'white', fontSize: 13, textTransform: 'capitalize',
            }}
          >{s}</button>
        ))}
      </div>

      {isLoading ? (
        <div style={{ color: '#64748b', padding: 20 }}>Loading…</div>
      ) : (
        <div style={{ background: '#1e293b', borderRadius: 8, overflow: 'hidden' }}>
          <div style={{
            display: 'grid',
            gridTemplateColumns: '8% 10% 10% 7% 7% 9% 9% 7% 9% 12% 12%',
            padding: '8px 12px', background: '#0f172a',
            fontSize: 11, color: '#64748b', fontWeight: 600, textTransform: 'uppercase',
          }}>
            {['Symbol', 'Entry', 'Exit', 'Score', 'Regime', 'Entry $', 'Exit $', 'Hold', 'Net P&L', 'Exit Reason', 'Decision'].map(h => (
              <span key={h}>{h}</span>
            ))}
          </div>
          {filtered.map((t: Trade) => (
            <div key={t.id}>
              <div
                onClick={() => setExpandedId(expandedId === t.id ? null : t.id)}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '8% 10% 10% 7% 7% 9% 9% 7% 9% 12% 12%',
                  padding: '8px 12px', fontSize: 13, cursor: 'pointer',
                  borderTop: '1px solid #0f172a',
                  background: expandedId === t.id ? '#0f172a' : 'transparent',
                }}
              >
                <span style={{ fontWeight: 600 }}>{t.symbol}</span>
                <span style={{ color: '#94a3b8' }}>{t.entry_time.slice(0, 10)}</span>
                <span style={{ color: '#94a3b8' }}>{t.exit_time?.slice(0, 10) ?? '—'}</span>
                <span>{t.score.toFixed(2)}</span>
                <span>{t.regime_mult.toFixed(2)}×</span>
                <span>{fmt(t.entry_price)}</span>
                <span>{fmt(t.exit_price)}</span>
                <span>{holdLabel(t.exit_time ? ((new Date(t.exit_time).getTime() - new Date(t.entry_time).getTime()) / 60000) : null)}</span>
                <span style={{ color: (t.net_pnl ?? 0) >= 0 ? '#22c55e' : '#ef4444' }}>
                  {fmt(t.net_pnl)}
                </span>
                <span style={{ color: '#94a3b8', fontSize: 12 }}>{t.exit_reason ?? '—'}</span>
                <span style={{ color: '#94a3b8', fontSize: 12 }}>ID {t.decision_id ?? '—'}</span>
              </div>
              {expandedId === t.id && (
                <div style={{ padding: '8px 12px 12px', background: '#0f172a', fontSize: 12, color: '#94a3b8' }}>
                  <span>signal_id: {t.signal_id ?? '—'}</span>
                  {' | '}
                  <span>order: {t.entry_order_id}</span>
                  {' | '}
                  <span>notional: {fmt(t.entry_notional)}</span>
                  {' | '}
                  <span>slippage est: {fmt(t.slippage_est)}</span>
                  {' | '}
                  <span>gross P&L: {fmt(t.gross_pnl)}</span>
                </div>
              )}
            </div>
          ))}
          {filtered.length === 0 && (
            <div style={{ padding: 20, color: '#64748b', textAlign: 'center' }}>No trades found.</div>
          )}
        </div>
      )}
    </div>
  )
}
