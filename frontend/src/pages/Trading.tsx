import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchPositions, fetchOrders, type Position, type Order } from '@/api/positions'
import { fetchTrades, type Trade } from '@/api/trades'
import { HelpButton } from '@/components/shared/HelpButton'
import { DataTable } from '@/components/shared/DataTable'

type Tab = 'positions' | 'orders' | 'fills'

function fmt(v: number | null, prefix = '$') {
  if (v == null) return '—'
  return `${prefix}${v.toFixed(2)}`
}

function sideSpan(side: string | null) {
  const isBuy = side === 'buy' || side === 'portfolio_buy'
  const label = side === 'portfolio_buy' ? 'BUY' : side === 'portfolio_sell' ? 'SELL' : (side ?? '—').toUpperCase()
  return <span className={`badge ${isBuy ? 'badge-green' : 'badge-red'}`}>{label}</span>
}

function statusSpan(status: string) {
  const cls = status === 'filled' ? 'badge-green' : status === 'canceled' ? 'badge-red' : 'badge-grey'
  return <span className={`badge ${cls}`}>{status}</span>
}

function pnlSpan(v: number) {
  const color = v >= 0 ? 'var(--green)' : 'var(--red)'
  return <span style={{ color, fontWeight: 600 }}>{v >= 0 ? '+' : ''}${v.toFixed(2)}</span>
}

function ts(iso: string | null) {
  if (!iso) return <span style={{ color: 'var(--text-muted)' }}>—</span>
  return <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>
    {new Date(iso).toLocaleString('it-IT', { dateStyle: 'short', timeStyle: 'short' })}
  </span>
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

  const filteredPositions = useMemo(() =>
    (positions as Position[]).filter(p => !symbolFilter || p.symbol.toLowerCase().includes(symbolFilter.toLowerCase()))
  , [positions, symbolFilter])

  const filteredOrders = useMemo(() =>
    (orders as Order[]).filter(o => !symbolFilter || o.symbol.toLowerCase().includes(symbolFilter.toLowerCase()))
  , [orders, symbolFilter])

  const filteredFills = useMemo(() =>
    (fills as Trade[]).filter(t => !symbolFilter || t.symbol.toLowerCase().includes(symbolFilter.toLowerCase()))
  , [fills, symbolFilter])

  const tabStyle = (t: Tab): React.CSSProperties => ({
    padding: '8px 20px',
    color: tab === t ? 'var(--blue)' : 'var(--text-muted)',
    fontWeight: tab === t ? 600 : 400,
    background: 'none',
    border: 'none',
    borderBottom: tab === t ? '2px solid var(--blue)' : '2px solid transparent',
    fontSize: 14,
    cursor: 'pointer',
  })

  const posRows = filteredPositions.map(p => ({
    cells: [
      <strong>{p.symbol}</strong>,
      p.qty.toFixed(4),
      `$${p.avg_entry_price.toFixed(2)}`,
      p.current_price != null ? `$${parseFloat(String(p.current_price)).toFixed(2)}` : '—',
      `$${p.market_value.toFixed(2)}`,
      pnlSpan(p.unrealized_pl),
      <span style={{ color: p.unrealized_plpc >= 0 ? 'var(--green)' : 'var(--red)' }}>
        {(p.unrealized_plpc * 100).toFixed(2)}%
      </span>,
    ],
  }))

  const ordRows = filteredOrders.map(o => ({
    cells: [
      <strong>{o.symbol}</strong>,
      sideSpan(o.side),
      o.qty ?? '—',
      o.filled_avg_price ? `$${parseFloat(o.filled_avg_price).toFixed(2)}` : '—',
      statusSpan(o.status),
      ts(o.submitted_at),
    ],
  }))

  const fillRows = filteredFills.map(t => ({
    cells: [
      <strong>{t.symbol}</strong>,
      sideSpan(t.exit_reason),
      fmt(t.entry_price),
      t.qty != null ? t.qty.toFixed(4) : '—',
      fmt(t.entry_notional),
      ts(t.entry_time),
    ],
    expanded: t.entry_order_id
      ? <span>order_id: {t.entry_order_id}</span>
      : undefined,
  }))

  return (
    <div style={{ position: 'relative' }}>
      <h2 style={{ margin: '0 0 20px', fontSize: 20, fontWeight: 700 }}>Trading</h2>
      <HelpButton title="Trading — Guida" sections={[
        {
          heading: 'Positions',
          content: 'Posizioni correntemente attive su Alpaca con unrealized P&L. Aggiornate ogni 60 secondi.',
        },
        {
          heading: 'Orders',
          content: 'Storico completo degli ordini: pending, filled, cancelled. Verde = filled, rosso = canceled, grigio = pending.',
        },
        {
          heading: 'Fills',
          content: 'Solo gli ordini filled: prezzo di esecuzione, quantità, notional. BUY = apertura/incremento posizione, SELL = riduzione/chiusura. Clicca una riga per vedere l\'order ID.',
        },
      ]} />

      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 20 }}>
        <div style={{ display: 'flex', borderBottom: '1px solid var(--border)' }}>
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
          style={{ width: 130 }}
        />
      </div>

      {tab === 'positions' && (
        <DataTable
          loading={posLoading}
          columns={[
            { label: 'Ticker',         width: '10%' },
            { label: 'Qty',            width: '10%' },
            { label: 'Entry Price',    width: '12%' },
            { label: 'Market Price',   width: '12%' },
            { label: 'Market Value',   width: '14%' },
            { label: 'Unrealized P&L', width: '14%' },
            { label: 'P&L %',          width: '10%' },
          ]}
          rows={posRows}
          emptyMessage="No open positions"
        />
      )}

      {tab === 'orders' && (
        <DataTable
          loading={ordLoading}
          columns={[
            { label: 'Ticker',     width: '10%' },
            { label: 'Side',       width: '10%' },
            { label: 'Qty',        width: '10%' },
            { label: 'Fill Price', width: '12%' },
            { label: 'Status',     width: '14%' },
            { label: 'Submitted',  width: 'auto' },
          ]}
          rows={ordRows}
          emptyMessage="No orders"
        />
      )}

      {tab === 'fills' && (
        <DataTable
          loading={fillsLoading}
          columns={[
            { label: 'Ticker',     width: '10%' },
            { label: 'Side',       width: '10%' },
            { label: 'Fill Price', width: '14%' },
            { label: 'Qty',        width: '12%' },
            { label: 'Notional',   width: '14%' },
            { label: 'Filled At',  width: 'auto' },
          ]}
          rows={fillRows}
          emptyMessage="No fills yet — orders execute at market open (15:30 IT)."
        />
      )}
    </div>
  )
}
