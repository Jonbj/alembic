import { apiFetch } from './client'

export interface StrategySummary {
  id: string
  name: string
  description: string
  status: 'validated' | 'testing' | 'building'
  n_assets: number
  oos_sharpe: number | null
  max_drawdown: number | null
  annual_return: number | null
}

export interface BacktestResult {
  strategy_id: string
  period: { start: string; end: string }
  metrics: {
    sharpe: number
    sortino: number
    calmar: number
    max_drawdown: number
    annual_return: number
    annual_vol: number
    win_rate: number
    skewness: number
    kurtosis: number
  }
  equity_curve: { date: string; cumulative_return: number; drawdown: number }[]
  per_asset: { ticker: string; weight: number; contribution: number; sharpe: number }[]
}

export interface GateResult {
  gate_id: string
  gate_name: string
  passed: boolean
  details: string
  metric_value: number | null
  threshold: number | null
}

export interface SensitivityResult {
  parameter: string
  values: number[]
  results: { value: number; sharpe: number; max_dd: number }[]
  // 2-D Sharpe grid (parameter === "sharpe_grid")
  lookback_long_values?: number[]
  vol_window_values?: number[]
  grid?: number[][]
}

export const strategiesApi = {
  list: () => apiFetch<StrategySummary[]>('/api/strategies'),
  detail: (id: string) => apiFetch<StrategySummary>(`/api/strategies/${id}`),
  backtest: (id: string) => apiFetch<BacktestResult>(`/api/strategies/${id}/backtest`),
  gates: (id: string) => apiFetch<GateResult[]>(`/api/strategies/${id}/gates`),
  sensitivity: (id: string) => apiFetch<SensitivityResult[]>(`/api/strategies/${id}/sensitivity`),
}
