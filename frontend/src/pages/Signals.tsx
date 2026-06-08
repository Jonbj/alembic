import { useState, useMemo, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useVirtualizer } from '@tanstack/react-virtual'
import { fetchSignals, type Signal } from '@/api/signals'
import { fetchDecisions, type Decision } from '@/api/trades'
import { DirectionBadge } from '@/components/shared/DirectionBadge'
import { HelpButton } from '@/components/shared/HelpButton'

const ROW_H = 40

const COLS = [
  { label: 'Ticker',     pct: 10 },
  { label: 'Direction',  pct: 12 },
  { label: 'Score',      pct: 11 },
  { label: 'Confidence', pct: 11 },
  { label: 'Model',      pct: 28 },
  { label: 'Fallback',   pct: 8 },
  { label: 'Time',       pct: 20 },
]

const GRID_TEMPLATE = COLS.map(c => `${c.pct}%`).join(' ')

export default function Signals() {
  const [ticker, setTicker] = useState('')
  const [direction, setDirection] = useState('')
  const [tab, setTab] = useState<'signals' | 'decisions'>('signals')

  const { data: signals = [], isLoading, error } = useQuery({
    queryKey: ['signals'],
    queryFn: () => fetchSignals(),
    refetchInterval: 60000,
  })

  const { data: decisions = [], isLoading: decisionsLoading } = useQuery({
    queryKey: ['decisions', ticker],
    queryFn: () => fetchDecisions(ticker || undefined, 100),
    enabled: tab === 'decisions',
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

  const DECISION_LABELS: Record<string, string> = {
    BUY: 'BUY',
    SKIP_EMA: 'Skip — below EMA',
    SKIP_CAP: 'Skip — cycle cap',
    SKIP_POSITION: 'Skip — position open',
  }

  return (
    <div style={{ position: 'relative' }}>
      <h2 style={{ margin: '0 0 20px', fontSize: 20, fontWeight: 700 }}>Signals</h2>

      <div style={{ display: 'flex', gap: 0, marginBottom: 20, borderBottom: '1px solid #334155' }}>
        {(['signals', 'decisions'] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              padding: '8px 20px', border: 'none', cursor: 'pointer',
              background: 'transparent',
              color: tab === t ? '#3b82f6' : '#64748b',
              borderBottom: tab === t ? '2px solid #3b82f6' : '2px solid transparent',
              fontWeight: tab === t ? 600 : 400, fontSize: 14,
              textTransform: 'capitalize',
            }}
          >{t === 'signals' ? 'Signals' : 'Decision Log'}</button>
        ))}
      </div>

      {tab === 'decisions' && (
        <div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <input
              value={ticker}
              onChange={e => setTicker(e.target.value)}
              placeholder="Filter symbol…"
              style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #334155', background: '#0f172a', color: 'white', fontSize: 13, width: 140 }}
            />
          </div>
          {decisionsLoading ? (
            <div style={{ color: '#64748b', padding: 20 }}>Loading…</div>
          ) : (
            <div style={{ background: '#1e293b', borderRadius: 8, overflow: 'hidden' }}>
              <div style={{
                display: 'grid', gridTemplateColumns: '14% 9% 8% 8% 12% auto',
                padding: '8px 12px', background: '#0f172a',
                fontSize: 11, color: '#64748b', fontWeight: 600, textTransform: 'uppercase',
              }}>
                {['Tick Time', 'Symbol', 'Weight', 'Decision', 'Order ID', 'Reason'].map(h => (
                  <span key={h}>{h}</span>
                ))}
              </div>
              {(decisions as Decision[]).map((d: Decision) => (
                <div key={d.id} style={{
                  display: 'grid', gridTemplateColumns: '14% 9% 8% 8% 12% auto',
                  padding: '8px 12px', fontSize: 13, borderTop: '1px solid #0f172a',
                  alignItems: 'start',
                }}>
                  <span style={{ color: '#94a3b8' }}>{d.tick_time.slice(0, 16).replace('T', ' ')}</span>
                  <span style={{ fontWeight: 600 }}>{d.symbol}</span>
                  <span>{(d.score * 100).toFixed(1)}%</span>
                  <span style={{
                    color: d.decision === 'BUY' ? '#22c55e' : d.decision === 'SELL' ? '#f87171' : '#94a3b8',
                    fontWeight: ['BUY', 'SELL'].includes(d.decision) ? 600 : 400,
                  }}>{DECISION_LABELS[d.decision] ?? d.decision}</span>
                  <span style={{ color: '#64748b', fontSize: 11 }}>{d.order_id ?? '—'}</span>
                  <span style={{ color: '#94a3b8', fontSize: 12, lineHeight: 1.4 }}>{d.reason ?? '—'}</span>
                </div>
              ))}
              {(decisions as Decision[]).length === 0 && (
                <div style={{ padding: 20, color: '#64748b', textAlign: 'center' }}>No decisions logged yet.</div>
              )}
            </div>
          )}
        </div>
      )}

      {tab === 'signals' && (
      <>
      <HelpButton title="Signals — Segnali" sections={[
        {
          heading: "Cosa sono i segnali",
          content: "I segnali sono l'output del modello LLM ensemble. Per ogni ticker nel watchlist, 4 modelli (kimi, qwen, deepseek, glm) generano un sentiment score da -1 (bearish forte) a +1 (bullish forte), con confidence 0-1. Il sistema aggrega i punteggi ponderati per produrre il segnale finale.",
        },
        {
          heading: "Come leggere i segnali",
          content: "**Ticker**: il simbolo azionario (es. SPY, QQQ).\n\n**Direction**: basata sullo score — BUY (score > 0.1), SELL (score < -0.1), HOLD (-0.1 ≤ score ≤ 0.1).\n\n**Score**: valore da -1 a +1. |score| > 0.3 è significativo, > 0.6 è forte.\n\n**Confidence**: da 0 a 1. Indica quanto concordano i modelli. Alta confidence = segnale affidabile.\n\n**Model**: quale modello LLM ha generato questo specifico segnale.\n\n**FB**: badge giallo = il modello fallback è stato usato (il modello primario ha fallito).",
        },
        {
          heading: "Filtri",
          content: "Usa il campo di testo per filtrare per ticker e il dropdown per direzione (BUY/SELL/HOLD). La lista è virtualizzata per gestire migliaia di segnali senza rallentare.",
        },
      ]} />

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

        {/* Single scroll container — header is sticky inside it */}
        <div
          ref={scrollRef}
          style={{ maxHeight: 520, overflowY: 'auto' }}
        >
          {/* Sticky header */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: GRID_TEMPLATE,
              padding: '0 12px',
              fontWeight: 600,
              fontSize: 11,
              textTransform: 'uppercase',
              letterSpacing: 0.5,
              color: 'var(--text-muted)',
              borderBottom: '1px solid var(--border)',
              position: 'sticky',
              top: 0,
              background: 'var(--bg-primary, #0f172a)',
              zIndex: 2,
            }}
          >
            {COLS.map(c => <div key={c.label}>{c.label}</div>)}
          </div>

          {/* Virtualized rows — width: 100% is CRITICAL for absolute-positioned grid children */}
          <div style={{ height: virtualizer.getTotalSize(), position: 'relative', width: '100%' }}>
            {virtualItems.map((vr) => {
              const s = filtered[vr.index]
              return (
                <div
                  key={vr.key}
                  data-index={vr.index}
                  ref={virtualizer.measureElement}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: GRID_TEMPLATE,
                    padding: '0 12px',
                    alignItems: 'center',
                    height: ROW_H,
                    borderBottom: '1px solid var(--border)',
                    position: 'absolute',
                    top: 0,
                    width: '100%',
                    transform: `translateY(${vr.start}px)`,
                  }}
                >
                  <div><strong>{s.symbol}</strong></div>
                  <div><DirectionBadge score={s.score} /></div>
                  <div style={{ fontVariantNumeric: 'tabular-nums' }}>{s.score.toFixed(4)}</div>
                  <div>{(s.confidence * 100).toFixed(1)}%</div>
                  <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>{s.model_id}</div>
                  <div>{s.fallback_used ? <span className="badge badge-yellow">FB</span> : '—'}</div>
                  <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>{new Date(s.generated_at).toLocaleString()}</div>
                </div>
              )
            })}
          </div>
          {filtered.length === 0 && !isLoading && (
            <div style={{ padding: '16px', textAlign: 'center', color: 'var(--text-muted)' }}>No signals</div>
          )}
        </div>
      </div>
      </>
      )}
    </div>
  )
}