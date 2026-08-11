import { apiFetch } from './client'

export interface Trade {
  id: number | string
  symbol: string
  signal_id: number | null
  decision_id: number | null
  entry_order_id: string | null
  entry_price: number | null
  entry_time: string
  entry_notional: number | null
  score: number | null
  regime_mult: number | null
  exit_price: number | null
  exit_time: string | null
  exit_reason: string | null
  qty: number | null
  gross_pnl: number | null
  slippage_est: number | null
  net_pnl: number | null
  postmortem_diagnosis: string | null
  created_at?: string
  status?: string
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
  news_log_id?: number | null
  score: number
  regime_mult: number
  ema_pass: boolean
  decision: string
  order_id: string | null
  reason: string | null
  created_at: string
  signal_generated_at: string | null
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

export const fetchDecisions = (symbol?: string, limit = 20, decisionId?: number) => {
  const params = new URLSearchParams({ limit: String(limit) })
  if (symbol) params.set('symbol', symbol)
  if (decisionId) params.set('decision_id', String(decisionId))
  return apiFetch<Decision[]>(`/api/decisions?${params}`)
}

// Phase B: feedback loop status
// F8 regime_scale was retired 2026-08-10 (#134, lifecycle
// docs/F8_LIFECYCLE_HISTORY_2026-08-10.md); the entry threshold is now the only
// surviving ratchet lever.
export interface FeedbackStatus {
  entry_threshold: number
  entry_threshold_baseline: number
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

export interface CounterfactualRawSkipCount {
  decision: string
  total: number
  processed: number
  with_return: number
  pending: number
  included_in_phase_c: boolean
}

export interface CounterfactualWorkerState {
  last_run_at: string
  completed_at: string
  status: 'ok' | 'skipped' | 'error' | string
  reason: string | null
  updated: number
  skipped_no_data: number
  errors: number
  total_decisions: number
}

export interface CounterfactualStatus {
  days: number
  last_processed_at: string | null
  raw_skip_counts: CounterfactualRawSkipCount[]
  phase_c: {
    total_skips: number
    processed: number
    with_return: number
    pending: number
  }
  worker: CounterfactualWorkerState | null
  next_run_hint: string
}

export const fetchCounterfactualStatus = (days = 7) =>
  apiFetch<CounterfactualStatus>(`/api/trades/analytics/counterfactual/status?days=${days}`)
