import { useState, useMemo, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useVirtualizer } from '@tanstack/react-virtual'
import { fetchSignals, type Signal } from '@/api/signals'
import { DirectionBadge } from '@/components/shared/DirectionBadge'

const ROW_H = 40   // px per row — used for virtualizer estimate and tbody height

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

  const scrollRef = useRef<HTMLDivElement>(null)
  const virtualizer = useVirtualizer({
    count: filtered.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_H,
    overscan: 8,
  })
  const virtualItems = virtualizer.getVirtualItems()

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

        {/* Fixed-layout table so column widths are stable with absolute-positioned rows */}
        <table style={{ tableLayout: 'fixed', width: '100%', borderCollapse: 'collapse' }}>
          <colgroup>
            <col style={{ width: '10%' }} />
            <col style={{ width: '12%' }} />
            <col style={{ width: '11%' }} />
            <col style={{ width: '11%' }} />
            <col style={{ width: '28%' }} />
            <col style={{ width: '8%' }} />
            <col style={{ width: '20%' }} />
          </colgroup>
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
        </table>

        {/* Scroll container — virtualizer attaches here */}
        <div
          ref={scrollRef}
          style={{ maxHeight: 520, overflowY: 'auto' }}
        >
          <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
            <table style={{ tableLayout: 'fixed', width: '100%', borderCollapse: 'collapse' }}>
              <colgroup>
                <col style={{ width: '10%' }} />
                <col style={{ width: '12%' }} />
                <col style={{ width: '11%' }} />
                <col style={{ width: '11%' }} />
                <col style={{ width: '28%' }} />
                <col style={{ width: '8%' }} />
                <col style={{ width: '20%' }} />
              </colgroup>
              <tbody style={{ display: 'block', position: 'relative', height: virtualizer.getTotalSize() }}>
                {virtualItems.map((vr) => {
                  const s = filtered[vr.index]
                  return (
                    <tr
                      key={vr.key}
                      data-index={vr.index}
                      ref={virtualizer.measureElement}
                      style={{
                        display: 'table',
                        tableLayout: 'fixed',
                        width: '100%',
                        position: 'absolute',
                        top: 0,
                        transform: `translateY(${vr.start}px)`,
                        height: ROW_H,
                      }}
                    >
                      <td style={{ width: '10%' }}><strong>{s.symbol}</strong></td>
                      <td style={{ width: '12%' }}><DirectionBadge score={s.score} /></td>
                      <td style={{ width: '11%', fontVariantNumeric: 'tabular-nums' }}>{s.score.toFixed(4)}</td>
                      <td style={{ width: '11%' }}>{(s.confidence * 100).toFixed(1)}%</td>
                      <td style={{ width: '28%', color: 'var(--text-muted)', fontSize: 12 }}>{s.model_id}</td>
                      <td style={{ width: '8%' }}>{s.fallback_used ? <span className="badge badge-yellow">FB</span> : '—'}</td>
                      <td style={{ width: '20%', color: 'var(--text-muted)', fontSize: 12 }}>{new Date(s.generated_at).toLocaleString()}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {filtered.length === 0 && !isLoading && (
            <div style={{ padding: '16px', textAlign: 'center', color: 'var(--text-muted)' }}>No signals</div>
          )}
        </div>
      </div>
    </div>
  )
}
