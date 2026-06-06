import { apiFetch } from './client'

export interface Trade {
  id: number
  symbol: string
  signal_id: number | null
  decision_id: number | null
  entry_order_id: string
  entry_price: number | null
  entry_time: string
  entry_notional: number
  score: number
  regime_mult: number
  exit_price: number | null
  exit_time: string | null
  exit_reason: string | null
  qty: number | null
  gross_pnl: number | null
  slippage_est: number | null
  net_pnl: number | null
  postmortem_diagnosis: string | null
  created_at: string
}

export interface TradesSummary {
  total_trades: number
  win_rate: number
  avg_gross_pnl: number
  avg_slippage_est: number
  avg_net_pnl: number
  total_gross_pnl: number
  total_net_pnl: number
  total_notional: number
  avg_hold_minutes: number
  trades_per_week: number
  return_on_notional: number
  slippage_pct_of_gross: number
}

export interface Decision {
  id: number
  tick_time: string
  symbol: string
  signal_id: number | null
  score: number
  regime_mult: number
  ema_pass: boolean
  decision: string
  order_id: string | null
  created_at: string
}

export type TradeStatus = 'open' | 'closed' | 'all'
export type SummaryPeriod = 7 | 30 | 90

export const fetchTrades = (symbol?: string, status: TradeStatus = 'all', limit = 50) => {
  const params = new URLSearchParams({ status, limit: String(limit) })
  if (symbol) params.set('symbol', symbol)
  return apiFetch<Trade[]>(`/api/trades?${params}`)
}

export const fetchTradesSummary = (days: SummaryPeriod = 7) =>
  apiFetch<TradesSummary>(`/api/trades/summary?days=${days}`)

export const fetchDecisions = (symbol?: string, limit = 20) => {
  const params = new URLSearchParams({ limit: String(limit) })
  if (symbol) params.set('symbol', symbol)
  return apiFetch<Decision[]>(`/api/decisions?${params}`)
}

// Phase B: feedback loop status
export interface FeedbackStatus {
  entry_threshold: number
  entry_threshold_baseline: number
  regime_scale: number
  adjustment_active: boolean
  last_adjustment_ts: string | null
  last_reason: string | null
  consecutive_losses: number | null
  rolling_net_pnl: number | null
}

export const fetchFeedbackStatus = () =>
  apiFetch<FeedbackStatus>('/api/feedback/status')

// Phase C: counterfactual opportunity cost
export interface CounterfactualRow {
  decision: string
  total_skips: number
  computed: number
  avg_return: number
  pct_profitable: number
  sum_positive_returns: number
}

export const fetchCounterfactualSummary = (days = 7) =>
  apiFetch<CounterfactualRow[]>(`/api/trades/analytics/counterfactual?days=${days}`)
