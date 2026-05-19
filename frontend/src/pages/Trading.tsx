import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchPositions, fetchOrders } from '@/api/positions'

type Tab = 'positions' | 'orders'

export default function Trading() {
  const [tab, setTab] = useState<Tab>('positions')

  const { data: positions = [], isLoading: posLoading } = useQuery({
    queryKey: ['positions'],
    queryFn: fetchPositions,
    refetchInterval: 60000,
  })

  const { data: orders = [], isLoading: ordLoading } = useQuery({
    queryKey: ['orders'],
    queryFn: () => fetchOrders(100),
    refetchInterval: 60000,
  })

  const tabStyle = (t: Tab) => ({
    padding: '8px 20px',
    cursor: 'pointer',
    borderBottom: tab === t ? '2px solid var(--blue)' : '2px solid transparent',
    color: tab === t ? 'var(--blue)' : 'var(--text-muted)',
    fontWeight: tab === t ? 600 : 400,
    background: 'none',
    borderRadius: 0,
  })

  return (
    <div>
      <h2 style={{ margin: '0 0 20px', fontSize: 20, fontWeight: 700 }}>Trading</h2>

      <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', marginBottom: 20 }}>
        <button style={tabStyle('positions')} onClick={() => setTab('positions')}>Posizioni aperte ({positions.length})</button>
        <button style={tabStyle('orders')} onClick={() => setTab('orders')}>Storico ordini ({orders.length})</button>
      </div>

      {tab === 'positions' && (
        <div className="card" style={{ padding: 0 }}>
          {posLoading && <p style={{ padding: 16, color: 'var(--text-muted)' }}>Loading...</p>}
          <table>
            <thead>
              <tr><th>Ticker</th><th>Qty</th><th>Avg Price</th><th>Market Value</th><th>Unrealized P&L</th><th>P&L %</th></tr>
            </thead>
            <tbody>
              {positions.map((p) => (
                <tr key={p.symbol}>
                  <td><strong>{p.symbol}</strong></td>
                  <td>{p.qty}</td>
                  <td>${p.avg_entry_price.toFixed(2)}</td>
                  <td>${p.market_value.toFixed(2)}</td>
                  <td style={{ color: p.unrealized_pl >= 0 ? 'var(--green)' : 'var(--red)', fontWeight: 600 }}>
                    {p.unrealized_pl >= 0 ? '+' : ''}${p.unrealized_pl.toFixed(2)}
                  </td>
                  <td style={{ color: p.unrealized_plpc >= 0 ? 'var(--green)' : 'var(--red)' }}>
                    {(p.unrealized_plpc * 100).toFixed(2)}%
                  </td>
                </tr>
              ))}
              {positions.length === 0 && !posLoading && (
                <tr><td colSpan={6} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>No open positions</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'orders' && (
        <div className="card" style={{ padding: 0 }}>
          {ordLoading && <p style={{ padding: 16, color: 'var(--text-muted)' }}>Loading...</p>}
          <table>
            <thead>
              <tr><th>Ticker</th><th>Side</th><th>Qty</th><th>Fill Price</th><th>Status</th><th>Submitted</th></tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.id}>
                  <td><strong>{o.symbol}</strong></td>
                  <td>
                    <span className={`badge ${o.side === 'buy' ? 'badge-green' : 'badge-red'}`}>
                      {o.side.toUpperCase()}
                    </span>
                  </td>
                  <td>{o.qty}</td>
                  <td>{o.filled_avg_price ? `$${parseFloat(o.filled_avg_price).toFixed(2)}` : '—'}</td>
                  <td><span className="badge badge-grey">{o.status}</span></td>
                  <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                    {o.submitted_at ? new Date(o.submitted_at).toLocaleString() : '—'}
                  </td>
                </tr>
              ))}
              {orders.length === 0 && !ordLoading && (
                <tr><td colSpan={6} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>No orders</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
