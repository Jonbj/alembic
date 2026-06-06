import { apiFetch } from './client'

export interface DimensionRow {
  label: string
  trade_count: number
  win_rate: number
  avg_net_pnl: number
  total_net_pnl: number
}

export type AnalyticsDim = 'regime' | 'hour' | 'score' | 'holdtime'

export const fetchAnalyticsBySymbol = (days = 90) =>
  apiFetch<DimensionRow[]>(`/api/trades/analytics/by-symbol?days=${days}`)

export const fetchAnalyticsByDimension = (dim: AnalyticsDim, days = 90) =>
  apiFetch<DimensionRow[]>(`/api/trades/analytics/by-dimension?dim=${dim}&days=${days}`)
