import { apiFetch } from './client'

export interface PnLData {
  daily: { date: string; equity: number; profit_loss: number }[]
  monthly: { month: string; pnl: number }[]
}

export interface WeeklyTradePnL {
  total_trades: number
  win_rate: number
  avg_net_pnl: number
  avg_gross_pnl: number
  avg_slippage_est: number
  total_net_pnl: number
  total_gross_pnl: number
  total_notional: number
  trades_per_week: number
  avg_hold_minutes: number
  slippage_pct_of_gross: number
  return_on_notional: number
  avg_cost_bps: number
  total_cost_usd: number
  avg_spread_cost_bps: number
  avg_impact_cost_bps: number
  cost_drag_pct: number
}

export interface WeeklyReport {
  computed_at: string
  weights: {
    current: Record<string, number>
    suggested: Record<string, number>
    purified_icir: Record<string, number>
    freeze_reason: string
  }
  trade_pnl: Partial<WeeklyTradePnL>
  capital_efficiency: {
    portfolio_value_usd: number
    deployed_notional: number
    n_open_positions: number
    deployment_pct: number
    cash_pct: number
    annual_cash_drag_pct: number
    efficiency_ratio: number
  }
  regime: {
    label: string
    multiplier: number
    confidence: number
    deployment_ceiling_pct: number
    regime_discount_pct: number
  }
  feedback: {
    threshold_baseline: number
    threshold_max: number
    current_threshold: number
    current_scale: number
    is_elevated: boolean
    consecutive_wins: number
    recovery_win_streak: number
    last_adjustment_ts: string
  }
  infrastructure: {
    monthly_fixed_usd: number
    monthly_llm_usd: number
    monthly_total_usd: number
    annual_total_usd: number
    breakevens: Record<string, number>
  }
}

export interface DailyTrade {
  symbol: string
  entry_time: string | null
  exit_time: string | null
  entry_price: number | null
  exit_price: number | null
  qty: number | null
  gross_pnl: number | null
  net_pnl: number
  exit_reason: string | null
}

export interface DailyPnLDay {
  date: string
  trades_closed: number
  total_gross_pnl: number
  total_costs: number
  total_net_pnl: number
  winners: number
  losers: number
  trades: DailyTrade[]
}

export interface DailyPnLReport {
  from_date: string
  to_date: string
  days: DailyPnLDay[]
  summary: {
    total_gross_pnl: number
    total_costs: number
    total_net_pnl: number
    total_trades: number
    winners: number
    losers: number
    win_rate: number
    positive_days: number
    negative_days: number
  }
}

export const fetchPnL = (period = '6M') =>
  apiFetch<PnLData>(`/api/performance/pnl?period=${period}`)

export const fetchWeeklyReport = () =>
  apiFetch<WeeklyReport>('/api/performance/weekly')

export const fetchDailyPnL = (fromDate: string, toDate: string) =>
  apiFetch<DailyPnLReport>(
    `/api/performance/daily?from_date=${fromDate}&to_date=${toDate}`
  )
