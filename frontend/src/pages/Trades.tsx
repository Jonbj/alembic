import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchTrades, type Trade, type TradeStatus } from '@/api/trades'
import { HelpButton } from '@/components/shared/HelpButton'

function fmt(v: number | null, prefix = '$') {
  if (v == null) return '—'
  return `${prefix}${v.toFixed(2)}`
}

function sideLabel(exitReason: string | null): { label: string; color: string } {
  if (exitReason === 'portfolio_buy') return { label: 'BUY', color: '#22c55e' }
  if (exitReason === 'portfolio_sell') return { label: 'SELL', color: '#f87171' }
  return { label: exitReason ?? '—', color: '#94a3b8' }
}

export default function Trades() {
  const [statusFilter, setStatusFilter] = useState<TradeStatus>('all')
  const [symbolFilter, setSymbolFilter] = useState('')
  const [expandedId, setExpandedId] = useState<number | string | null>(null)

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
          content: 'Lista degli ordini **filled** (eseguiti) su Alpaca in modalità portfolio. Ogni riga corrisponde a un singolo ordine eseguito dal portfolio scheduler.\n\n**BUY**: apertura o incremento di posizione.\n**SELL**: riduzione o chiusura di posizione.',
        },
        {
          heading: 'Filtri',
          content: '**Symbol**: filtra per ticker.\n**all**: tutti gli ordini filled.\n**open**: solo BUY fills (posizioni aperte).\n**closed**: solo SELL fills (posizioni ridotte/chiuse).',
        },
        {
          heading: 'Colonne',
          content: '**Side**: BUY o SELL.\n**Fill Price**: prezzo medio di esecuzione.\n**Qty**: quantità eseguita.\n**Notional**: controvalore in dollari.\n**Filled At**: orario di esecuzione.',
        },
      ]} />

      <div style={{ display: 'flex', gap: 8, marginBottom: 16, alignItems: 'center' }}>
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
        <span style={{ marginLeft: 'auto', color: '#64748b', fontSize: 13 }}>
          {filtered.length} orders
        </span>
      </div>

      {isLoading ? (
        <div style={{ color: '#64748b', padding: 20 }}>Loading…</div>
      ) : (
        <div style={{ background: '#1e293b', borderRadius: 8, overflow: 'hidden' }}>
          <div style={{
            display: 'grid',
            gridTemplateColumns: '10% 10% 14% 12% 14% auto',
            padding: '8px 12px', background: '#0f172a',
            fontSize: 11, color: '#64748b', fontWeight: 600, textTransform: 'uppercase',
          }}>
            {['Symbol', 'Side', 'Fill Price', 'Qty', 'Notional', 'Filled At'].map(h => (
              <span key={h}>{h}</span>
            ))}
          </div>
          {filtered.map((t: Trade) => {
            const side = sideLabel(t.exit_reason)
            return (
              <div key={t.id}>
                <div
                  onClick={() => setExpandedId(expandedId === t.id ? null : t.id)}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '10% 10% 14% 12% 14% auto',
                    padding: '8px 12px', fontSize: 13, cursor: 'pointer',
                    borderTop: '1px solid #0f172a',
                    background: expandedId === t.id ? '#0f172a' : 'transparent',
                  }}
                >
                  <span style={{ fontWeight: 600 }}>{t.symbol}</span>
                  <span style={{ color: side.color, fontWeight: 600 }}>{side.label}</span>
                  <span>{fmt(t.entry_price)}</span>
                  <span>{t.qty != null ? t.qty.toFixed(4) : '—'}</span>
                  <span>{fmt(t.entry_notional)}</span>
                  <span style={{ color: '#94a3b8', fontSize: 12 }}>
                    {new Date(t.entry_time).toLocaleString('it-IT', { dateStyle: 'short', timeStyle: 'short' })}
                  </span>
                </div>
                {expandedId === t.id && (
                  <div style={{ padding: '8px 12px 12px', background: '#0f172a', fontSize: 12, color: '#94a3b8' }}>
                    <span>order_id: {t.entry_order_id ?? '—'}</span>
                  </div>
                )}
              </div>
            )
          })}
          {filtered.length === 0 && (
            <div style={{ padding: 20, color: '#64748b', textAlign: 'center' }}>
              No filled orders yet — orders are filled at market open (15:30 IT).
            </div>
          )}
        </div>
      )}
    </div>
  )
}
