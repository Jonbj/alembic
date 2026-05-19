import { apiFetch } from './client'

export interface PnLData {
  daily: { date: string; equity: number; profit_loss: number }[]
  monthly: { month: string; pnl: number }[]
}

export const fetchPnL = (period = '6M') => apiFetch<PnLData>(`/api/performance/pnl?period=${period}`)
