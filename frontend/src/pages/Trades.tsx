import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchTrades, type Trade, type TradeStatus } from '@/api/trades'
import { HelpButton } from '@/components/shared/HelpButton'
import { DataTable } from '@/components/shared/DataTable'

function fmt(v: number | null, prefix = '$') {
  if (v == null) return '—'
  return `${prefix}${v.toFixed(2)}`
}

function sideSpan(exitReason: string | null) {
  const isBuy = exitReason === 'portfolio_buy'
  const label = isBuy ? 'BUY' : exitReason === 'portfolio_sell' ? 'SELL' : exitReason ?? '—'
  return <span className={`badge ${isBuy ? 'badge-green' : 'badge-red'}`}>{label}</span>
}

export default function Trades() {
  const [statusFilter, setStatusFilter] = useState<TradeStatus>('all')
  const [symbolFilter, setSymbolFilter] = useState('')
  const { data: trades = [], isLoading } = useQuery({
    queryKey: ['trades', statusFilter],
    queryFn: () => fetchTrades(undefined, statusFilter, 200),
    refetchInterval: 60000,
  })

  const filtered = useMemo(() =>
    (trades as Trade[]).filter((t: Trade) =>
      !symbolFilter || t.symbol.toLowerCase().includes(symbolFilter.toLowerCase())
    ), [trades, symbolFilter])

  return (
    <div style={{ position: 'relative' }}>
      <h2 style={{ margin: '0 0 20px', fontSize: 20, fontWeight: 700 }}>Execution History</h2>
      <HelpButton title="Execution History — Guida" sections={[
        {
          heading: 'Cosa mostra questa pagina',
          content: 'Lista degli ordini **filled** (eseguiti) su Alpaca in modalità portfolio. Ogni riga corrisponde a un singolo ordine eseguito dal portfolio scheduler al ciclo di 15 minuti.\n\n**BUY**: apertura o incremento di posizione su un ticker.\n**SELL**: riduzione o chiusura di posizione su un ticker.',
        },
        {
          heading: 'Filtri',
          content: '**Symbol**: campo testo per filtrare per ticker (es. "AVGO" mostra solo ordini su AVGO).\n**all**: tutti gli ordini filled, BUY e SELL.\n**open**: solo BUY fills — corrisponde alle posizioni attualmente aperte.\n**closed**: solo SELL fills — posizioni ridotte o chiuse.',
        },
        {
          heading: 'Colonne',
          content: '**Symbol**: ticker azionario.\n**Side**: BUY (apertura/incremento posizione) o SELL (riduzione/chiusura). Colore verde per BUY, rosso per SELL.\n**Fill Price**: prezzo medio di esecuzione effettivo — può differire dal prezzo di mercato al momento dell\'ordine (slippage bid-ask).\n**Qty**: numero di azioni eseguite (fino a 4 decimali per azioni frazionarie).\n**Notional**: controvalore totale in USD = Fill Price × Qty. Rappresenta il capitale effettivamente impiegato nell\'operazione.\n**Filled At**: data e ora di esecuzione dell\'ordine in fuso orario locale (formato IT: GG/MM/AA HH:MM).',
        },
        {
          heading: 'Espansione riga — Order ID',
          content: 'Clicca su una riga per espanderla e vedere l\'ID dell\'ordine Alpaca (es. "a1b2c3d4-..."). Puoi usare questo ID per cercare l\'ordine direttamente nel pannello Alpaca Paper Trading per verificare l\'esecuzione o vedere i dettagli di fill multipli.',
        },
      ]} />

      <div style={{ display: 'flex', gap: 8, marginBottom: 16, alignItems: 'center' }}>
        <input value={symbolFilter} onChange={e => setSymbolFilter(e.target.value)} placeholder="Filter symbol…" style={{ width: 140 }} />
        {(['all', 'open', 'closed'] as TradeStatus[]).map(s => (
          <button key={s} onClick={() => setStatusFilter(s)}
            className={statusFilter === s ? 'btn-primary' : 'btn-ghost'}
            style={{ textTransform: 'capitalize' }}
          >{s}</button>
        ))}
        <span style={{ marginLeft: 'auto', color: 'var(--text-muted)', fontSize: 13 }}>{filtered.length} orders</span>
      </div>

      <DataTable
        loading={isLoading}
        columns={[
          { label: 'Symbol',    width: '10%' },
          { label: 'Side',      width: '10%' },
          { label: 'Fill Price', width: '14%' },
          { label: 'Qty',       width: '12%' },
          { label: 'Notional',  width: '14%' },
          { label: 'Filled At', width: 'auto' },
        ]}
        rows={filtered.map((t: Trade) => ({
          cells: [
            <strong>{t.symbol}</strong>,
            sideSpan(t.exit_reason),
            fmt(t.entry_price),
            t.qty != null ? t.qty.toFixed(4) : '—',
            fmt(t.entry_notional),
            <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>
              {new Date(t.entry_time).toLocaleString('it-IT', { dateStyle: 'short', timeStyle: 'short' })}
            </span>,
          ],
          expanded: t.entry_order_id ? <span>order_id: {t.entry_order_id}</span> : undefined,
        }))}
        emptyMessage="No filled orders yet — orders are filled at market open (15:30 IT)."
      />
    </div>
  )
}
