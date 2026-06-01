import { apiFetch } from './client'

export interface Strategy {
  id: string
  name: string
  description: string
  status: string
  n_assets: number
  oos_sharpe: number
  max_drawdown: number
  annual_return: number
}

export interface StrategyDetail {
  id: string
  name: string
  description: string
  status: string
  parameters: {
    lookback_long: number
    lookback_short: number
    vol_window: number
    vol_target: number
    max_leverage: number
  }
  universe: string[]
  n_assets: number
  oos_sharpe: number
  max_drawdown: number
  annual_return: number
  is_sharpe: number
  calmar_ratio: number
  sortino_ratio: number
  win_rate: number
  avg_holding_period: string
  total_trades: number
}

export interface EquityPoint {
  date: string
  cumulative_return: number
  drawdown: number
}

export interface GateResult {
  gate_id: string
  gate_name: string
  passed: boolean
  details: string
  metric_value: number
  threshold: number
}

export interface SensitivityPoint {
  lookback: number
  vol_window: number
  sharpe: number
  max_drawdown: number
}

export const strategiesApi = {
  list: () => apiFetch<Strategy[]>('/api/strategies'),
  detail: (id: string) => apiFetch<StrategyDetail>(`/api/strategies/${id}`),
  backtest: (id: string) => apiFetch<EquityPoint[]>(`/api/strategies/${id}/backtest`),
  gates: (id: string) => apiFetch<GateResult[]>(`/api/strategies/${id}/gates`),
  sensitivity: (id: string) => apiFetch<SensitivityPoint[]>(`/api/strategies/${id}/sensitivity`),
}