import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchSignals, type Signal } from '@/api/signals'
import { DirectionBadge } from '@/components/shared/DirectionBadge'

export default function Signals() {
  const [ticker, setTicker] = useState('')
  const [direction, setDirection] = useState('')

  const { data: signals = [], isLoading, error } = useQuery({
    queryKey: ['signals'],
    queryFn: () => fetchSignals(),
    refetchInterval: 60000,
  })

  const filtered = useMemo(() =>
    signals.filter((s: Signal) => {
      if (ticker && !s.symbol.toLowerCase().includes(ticker.toLowerCase())) return false
      if (direction === 'BUY' && s.score <= 0.1) return false
      if (direction === 'SELL' && s.score >= -0.1) return false
      if (direction === 'HOLD' && Math.abs(s.score) > 0.1) return false
      return true
    }),
    [signals, ticker, direction]
  )

  return (
    <div>
      <h2 style={{ margin: '0 0 20px', fontSize: 20, fontWeight: 700 }}>Signals</h2>

      <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        <input placeholder="Filter ticker..." value={ticker} onChange={(e) => setTicker(e.target.value)} style={{ width: 160 }} />
        <select value={direction} onChange={(e) => setDirection(e.target.value)}>
          <option value="">All directions</option>
          <option value="BUY">BUY</option>
          <option value="SELL">SELL</option>
          <option value="HOLD">HOLD</option>
        </select>
        <span style={{ color: 'var(--text-muted)', alignSelf: 'center', fontSize: 12 }}>{filtered.length} signals</span>
      </div>

      <div className="card" style={{ padding: 0 }}>
        {isLoading && <p style={{ padding: 16, color: 'var(--text-muted)' }}>Loading...</p>}
        {error && <p style={{ padding: 16, color: 'var(--red)' }}>Error loading signals</p>}
        <table>
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Direction</th>
              <th>Score</th>
              <th>Confidence</th>
              <th>Model</th>
              <th>Fallback</th>
              <th>Time</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((s, i) => (
              <tr key={i}>
                <td><strong>{s.symbol}</strong></td>
                <td><DirectionBadge score={s.score} /></td>
                <td style={{ fontVariantNumeric: 'tabular-nums' }}>{s.score.toFixed(4)}</td>
                <td>{(s.confidence * 100).toFixed(1)}%</td>
                <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>{s.model_id}</td>
                <td>{s.fallback_used ? <span className="badge badge-yellow">FB</span> : '—'}</td>
                <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>{new Date(s.generated_at).toLocaleString()}</td>
              </tr>
            ))}
            {filtered.length === 0 && !isLoading && (
              <tr><td colSpan={7} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>No signals</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
