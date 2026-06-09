import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchPositions, fetchOrders, type Position, type Order } from '@/api/positions'
import { fetchTrades, type Trade } from '@/api/trades'
import { HelpButton } from '@/components/shared/HelpButton'

type Tab = 'positions' | 'orders' | 'fills'

function fmt(v: number | null, prefix = '$') {
  if (v == null) return '—'
  return `${prefix}${v.toFixed(2)}`
}

function sideColor(side: string | null) {
  if (side === 'buy' || side === 'portfolio_buy') return '#22c55e'
  if (side === 'sell' || side === 'portfolio_sell') return '#f87171'
  return '#94a3b8'
}

function fillSide(exitReason: string | null) {
  if (exitReason === 'portfolio_buy') return 'BUY'
  if (exitReason === 'portfolio_sell') return 'SELL'
  return exitReason ?? '—'
}

export default function Trading() {
  const [tab, setTab] = useState<Tab>('positions')
  const [symbolFilter, setSymbolFilter] = useState('')

  const { data: positions = [], isLoading: posLoading } = useQuery({
    queryKey: ['positions'],
    queryFn: fetchPositions,
    refetchInterval: 60000,
  })

  const { data: orders = [], isLoading: ordLoading } = useQuery({
    queryKey: ['orders'],
    queryFn: () => fetchOrders(200),
    refetchInterval: 60000,
  })

  const { data: fills = [], isLoading: fillsLoading } = useQuery({
    queryKey: ['trades-fills'],
    queryFn: () => fetchTrades(undefined, 'all', 200),
    refetchInterval: 60000,
  })

  const filteredOrders = useMemo(() =>
    (orders as Order[]).filter(o => !symbolFilter || o.symbol.toLowerCase().includes(symbolFilter.toLowerCase()))
  , [orders, symbolFilter])

  const filteredFills = useMemo(() =>
    (fills as Trade[]).filter(t => !symbolFilter || t.symbol.toLowerCase().includes(symbolFilter.toLowerCase()))
  , [fills, symbolFilter])

  const filteredPositions = useMemo(() =>
    (positions as Position[]).filter(p => !symbolFilter || p.symbol.toLowerCase().includes(symbolFilter.toLowerCase()))
  , [positions, symbolFilter])

  const tabStyle = (t: Tab) => ({
    padding: '8px 20px',
    color: tab === t ? '#3b82f6' : '#94a3b8',
    fontWeight: tab === t ? 600 : 400,
    background: 'none',
    border: 'none',
    borderBottom: tab === t ? '2px solid #3b82f6' : '2px solid transparent',
    fontSize: 14,
    cursor: 'pointer',
  } as React.CSSProperties)

  return (
    <div style={{ position: 'relative' }}>
      <h2 style={{ margin: '0 0 20px', fontSize: 20, fontWeight: 700 }}>Trading</h2>
      <HelpButton title="Trading — Guida" sections={[
        {
          heading: 'Posizioni aperte',
          content: 'Posizioni correntemente attive su Alpaca. **Unrealized P&L** è il profitto/perdita non realizzato. Dati aggiornati ogni 60 secondi.',
        },
        {
          heading: 'Ordini (tutti)',
          content: 'Storico completo degli ordini: pending, filled, cancelled. Mostra lo stato di ogni ordine inviato dal portfolio scheduler.',
        },
        {
          heading: 'Fills (eseguiti)',
          content: 'Solo gli ordini **filled**: prezzo di esecuzione, quantità, controvalore. In modalità portfolio ogni fill corrisponde a un aggiustamento di posizione (BUY = apertura/incremento, SELL = riduzione/chiusura).',
        },
        {
          heading: 'Paper trading',
          content: 'Gli ordini sono simulati — nessun capitale reale è coinvolto. I fill avvengono all\'apertura del mercato USA (15:30 IT).',
        },
      ]} />

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
        <div style={{ display: 'flex', borderBottom: '1px solid #334155' }}>
          <button style={tabStyle('positions')} onClick={() => setTab('positions')}>
            Positions ({positions.length})
          </button>
          <button style={tabStyle('orders')} onClick={() => setTab('orders')}>
            Orders ({orders.length})
          </button>
          <button style={tabStyle('fills')} onClick={() => setTab('fills')}>
            Fills ({fills.length})
          </button>
        </div>
        <input
          value={symbolFilter}
          onChange={e => setSymbolFilter(e.target.value)}
          placeholder="Filter symbol…"
          style={{ padding: '5px 10px', borderRadius: 6, border: '1px solid #334155', background: '#0f172a', color: 'white', fontSize: 13, width: 130 }}
        />
      </div>

      {tab === 'positions' && (
        <div style={{ background: '#1e293b', borderRadius: 8, overflow: 'hidden' }}>
          {posLoading && <p style={{ padding: 16, color: '#94a3b8' }}>Loading...</p>}
          <div style={{ display: 'grid', gridTemplateColumns: '10% 8% 12% 12% 14% 14% 10%', padding: '8px 12px', background: '#0f172a', fontSize: 11, color: '#64748b', fontWeight: 600, textTransform: 'uppercase' }}>
            {['Ticker', 'Qty', 'Entry Price', 'Market Price', 'Market Value', 'Unrealized P&L', 'P&L %'].map(h => <span key={h}>{h}</span>)}
          </div>
          {filteredPositions.map((p) => (
            <div key={p.symbol} style={{ display: 'grid', gridTemplateColumns: '10% 8% 12% 12% 14% 14% 10%', padding: '8px 12px', fontSize: 13, borderTop: '1px solid #0f172a' }}>
              <span style={{ fontWeight: 600 }}>{p.symbol}</span>
              <span>{p.qty.toFixed(4)}</span>
              <span>${p.avg_entry_price.toFixed(2)}</span>
              <span>{p.current_price != null ? `$${parseFloat(String(p.current_price)).toFixed(2)}` : '—'}</span>
              <span>${p.market_value.toFixed(2)}</span>
              <span style={{ color: p.unrealized_pl >= 0 ? '#22c55e' : '#f87171', fontWeight: 600 }}>
                {p.unrealized_pl >= 0 ? '+' : ''}${p.unrealized_pl.toFixed(2)}
              </span>
              <span style={{ color: p.unrealized_plpc >= 0 ? '#22c55e' : '#f87171' }}>
                {(p.unrealized_plpc * 100).toFixed(2)}%
              </span>
            </div>
          ))}
          {filteredPositions.length === 0 && !posLoading && (
            <div style={{ padding: 20, color: '#64748b', textAlign: 'center' }}>No open positions</div>
          )}
        </div>
      )}

      {tab === 'orders' && (
        <div style={{ background: '#1e293b', borderRadius: 8, overflow: 'hidden' }}>
          {ordLoading && <p style={{ padding: 16, color: '#94a3b8' }}>Loading...</p>}
          <div style={{ display: 'grid', gridTemplateColumns: '10% 8% 10% 12% 12% auto', padding: '8px 12px', background: '#0f172a', fontSize: 11, color: '#64748b', fontWeight: 600, textTransform: 'uppercase' }}>
            {['Ticker', 'Side', 'Qty', 'Fill Price', 'Status', 'Submitted'].map(h => <span key={h}>{h}</span>)}
          </div>
          {filteredOrders.map((o) => (
            <div key={o.id} style={{ display: 'grid', gridTemplateColumns: '10% 8% 10% 12% 12% auto', padding: '8px 12px', fontSize: 13, borderTop: '1px solid #0f172a' }}>
              <span style={{ fontWeight: 600 }}>{o.symbol}</span>
              <span style={{ color: sideColor(o.side), fontWeight: 600 }}>{o.side ? o.side.toUpperCase() : '—'}</span>
              <span>{o.qty ?? '—'}</span>
              <span>{o.filled_avg_price ? `$${parseFloat(o.filled_avg_price).toFixed(2)}` : '—'}</span>
              <span style={{ color: o.status === 'filled' ? '#22c55e' : o.status === 'canceled' ? '#f87171' : '#94a3b8', fontSize: 12 }}>{o.status}</span>
              <span style={{ color: '#64748b', fontSize: 12 }}>
                {o.submitted_at ? new Date(o.submitted_at).toLocaleString('it-IT', { dateStyle: 'short', timeStyle: 'short' }) : '—'}
              </span>
            </div>
          ))}
          {filteredOrders.length === 0 && !ordLoading && (
            <div style={{ padding: 20, color: '#64748b', textAlign: 'center' }}>No orders</div>
          )}
        </div>
      )}

      {tab === 'fills' && (
        <div style={{ background: '#1e293b', borderRadius: 8, overflow: 'hidden' }}>
          {fillsLoading && <p style={{ padding: 16, color: '#94a3b8' }}>Loading...</p>}
          <div style={{ display: 'grid', gridTemplateColumns: '10% 8% 14% 12% 14% auto', padding: '8px 12px', background: '#0f172a', fontSize: 11, color: '#64748b', fontWeight: 600, textTransform: 'uppercase' }}>
            {['Ticker', 'Side', 'Fill Price', 'Qty', 'Notional', 'Filled At'].map(h => <span key={h}>{h}</span>)}
          </div>
          {filteredFills.map((t: Trade) => (
            <div key={t.id} style={{ display: 'grid', gridTemplateColumns: '10% 8% 14% 12% 14% auto', padding: '8px 12px', fontSize: 13, borderTop: '1px solid #0f172a' }}>
              <span style={{ fontWeight: 600 }}>{t.symbol}</span>
              <span style={{ color: sideColor(t.exit_reason), fontWeight: 600 }}>{fillSide(t.exit_reason)}</span>
              <span>{fmt(t.entry_price)}</span>
              <span>{t.qty != null ? t.qty.toFixed(4) : '—'}</span>
              <span>{fmt(t.entry_notional)}</span>
              <span style={{ color: '#64748b', fontSize: 12 }}>
                {new Date(t.entry_time).toLocaleString('it-IT', { dateStyle: 'short', timeStyle: 'short' })}
              </span>
            </div>
          ))}
          {filteredFills.length === 0 && !fillsLoading && (
            <div style={{ padding: 20, color: '#64748b', textAlign: 'center' }}>
              No fills yet — orders execute at market open (15:30 IT).
            </div>
          )}
        </div>
      )}
    </div>
  )
}
