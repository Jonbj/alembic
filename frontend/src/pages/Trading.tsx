import { useState, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { fmtDateTime } from '@/utils/format'
import { useQuery } from '@tanstack/react-query'
import { fetchPositions, fetchOrders, type Position, type Order } from '@/api/positions'
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
    {fmtDateTime(iso)}
  </span>
}

export default function Trading() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [tab, setTab] = useState<Tab>('positions')
  const [symbolFilter, setSymbolFilter] = useState(searchParams.get('symbol') ?? '')

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

  const filteredPositions = useMemo(() =>
    (positions as Position[]).filter(p => !symbolFilter || p.symbol.toLowerCase().includes(symbolFilter.toLowerCase()))
  , [positions, symbolFilter])

  const filteredOrders = useMemo(() =>
    (orders as Order[]).filter(o => !symbolFilter || o.symbol.toLowerCase().includes(symbolFilter.toLowerCase()))
  , [orders, symbolFilter])

  const filteredFills = useMemo(() =>
    (orders as Order[]).filter((o) =>
      o.status === 'filled' &&
      (!symbolFilter || o.symbol.toLowerCase().includes(symbolFilter.toLowerCase()))
    )
  , [orders, symbolFilter])

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

  const updateSymbolFilter = (value: string) => {
    setSymbolFilter(value)
    const next = new URLSearchParams(searchParams)
    if (value.trim()) next.set('symbol', value.trim().toUpperCase())
    else next.delete('symbol')
    setSearchParams(next, { replace: true })
  }

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

  const fillRows = filteredFills.map(o => {
    const qty = o.qty && o.qty !== 'None' ? parseFloat(o.qty) : null
    const price = o.filled_avg_price ? parseFloat(o.filled_avg_price) : null
    const notional = qty != null && price != null ? qty * price : null
    return {
    cells: [
      <strong>{o.symbol}</strong>,
      sideSpan(o.side),
      price != null ? fmt(price) : '—',
      qty != null ? qty.toFixed(4) : '—',
      fmt(notional),
      ts(o.filled_at),
    ],
    expanded: o.id
      ? <span>order_id: {o.id}</span>
      : undefined,
    }
  })

  return (
    <div style={{ position: 'relative' }}>
      <h2 style={{ margin: '0 0 20px', fontSize: 20, fontWeight: 700 }}>Trading</h2>
      <HelpButton title="Trading — Guida" sections={[
        {
          heading: 'Positions',
          content: 'Posizioni correntemente attive su Alpaca con unrealized P&L. Aggiornate ogni 60 secondi.',
        },
        {
          heading: 'Colonne — Positions',
          content: '**Ticker**: simbolo azionario.\n**Qty**: numero di azioni detenute.\n**Entry Price**: prezzo medio ponderato di ingresso (avg fill price di tutti gli ordini BUY sulla posizione).\n**Market Price**: prezzo corrente di mercato dell\'azione.\n**Market Value**: Qty × Market Price — valore attuale della posizione in USD.\n**Unrealized P&L**: guadagno/perdita non ancora realizzato = Market Value − (Entry Price × Qty). Verde se positivo, rosso se negativo.\n**P&L %**: rendimento percentuale sulla posizione = Unrealized P&L / (Entry Price × Qty) × 100.',
        },
        {
          heading: 'Orders',
          content: 'Storico completo degli ordini: pending, filled, cancelled. Verde = filled, rosso = canceled, grigio = pending.',
        },
        {
          heading: 'Colonne — Orders',
          content: '**Ticker**: simbolo azionario.\n**Side**: BUY (acquisto) o SELL (vendita).\n**Qty**: quantità ordinata (in azioni).\n**Fill Price**: prezzo medio di esecuzione dell\'ordine. "—" se l\'ordine non è ancora stato eseguito (es. pending o canceled).\n**Status**: stato dell\'ordine — filled (eseguito), partial_fill (parzialmente eseguito), canceled (annullato), pending_new (in attesa di conferma).\n**Submitted**: timestamp di quando l\'ordine è stato inviato ad Alpaca.',
        },
        {
          heading: 'Fills',
          content: 'Solo gli ordini filled: prezzo di esecuzione, quantità, notional. BUY = apertura/incremento posizione, SELL = riduzione/chiusura. Clicca una riga per vedere l\'order ID.',
        },
        {
          heading: 'Colonne — Fills',
          content: '**Ticker**: simbolo azionario.\n**Side**: BUY (apertura/incremento) o SELL (riduzione/chiusura di posizione).\n**Fill Price**: prezzo effettivo di esecuzione — può differire leggermente dal prezzo richiesto per ordini a mercato (slippage).\n**Qty**: numero di azioni effettivamente eseguite.\n**Notional**: controvalore totale dell\'ordine = Fill Price × Qty in USD — rappresenta il capitale impiegato.\n**Filled At**: data e ora di esecuzione dell\'ordine (fuso orario locale).',
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
            Fills ({filteredFills.length})
          </button>
        </div>
        <input
          value={symbolFilter}
          onChange={e => updateSymbolFilter(e.target.value)}
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
          loading={ordLoading}
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
