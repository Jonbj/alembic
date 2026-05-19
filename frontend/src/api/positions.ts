import { apiFetch } from './client'

export interface Position {
  symbol: string
  qty: string
  market_value: string
  unrealized_pl: string
  unrealized_plpc: string
  avg_entry_price: string
  current_price: string
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

export const fetchPositions = () => apiFetch<Position[]>('/api/positions')
export const fetchOrders = (limit = 100) => apiFetch<Order[]>(`/api/orders?limit=${limit}`)
