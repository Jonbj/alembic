import { apiFetch } from './client'

export interface ValidationMetrics {
  window_days: number | null
  nav: number | null
  regime_mult: number | null
  deployment_pct: number | null
  turnover: { traded_notional: number; turnover_ratio: number | null }
  churn: {
    total_opens: number
    distinct_symbols: number
    roundtrip_symbols: Record<string, number>
    roundtrip_count: number
    avg_hold_minutes: number | null
  }
  pnl: {
    closed_trades: number
    open_trades: number
    realized_net_pnl: number
    realized_gross_pnl: number
    cost_drag: number
    win_rate: number | null
    open_notional: number
  }
  exits: Record<string, number>
  generated_at: string
}

export const fetchValidationMetrics = (days = 7) =>
  apiFetch<ValidationMetrics>(`/api/validation/metrics?days=${days}`)
