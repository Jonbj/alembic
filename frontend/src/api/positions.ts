import { apiFetch } from './client'

interface RawPosition {
  symbol: string
  qty: string
  market_value: string
  unrealized_pl: string
  unrealized_plpc: string
  avg_entry_price: string
  current_price: string
}

export interface Position {
  symbol: string
  qty: number
  market_value: number
  unrealized_pl: number
  unrealized_plpc: number
  avg_entry_price: number
  current_price: number
}

export interface Order {
  id: string
  symbol: string
  side: string
  qty: string
  filled_avg_price: string | null
  status: string
  filled_at: string | null
  submitted_at: string | null
}

export const fetchPositions = () =>
  apiFetch<RawPosition[]>('/api/positions').then((raw) =>
    raw.map((p): Position => ({
      symbol: p.symbol,
      qty: parseFloat(p.qty),
      market_value: parseFloat(p.market_value),
      unrealized_pl: parseFloat(p.unrealized_pl),
      unrealized_plpc: parseFloat(p.unrealized_plpc),
      avg_entry_price: parseFloat(p.avg_entry_price),
      current_price: parseFloat(p.current_price),
    }))
  )

export const fetchOrders = (limit = 100) => apiFetch<Order[]>(`/api/orders?limit=${limit}`)
