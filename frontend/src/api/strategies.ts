import { apiFetch } from './client'

/** Authorization state fields returned by the strategy API (F0-1). */
export interface StrategyAuthFields {
  /** Lifecycle mode: "supervised_paper" | "paper" | "research" | "disabled" | "live" */
  mode?: string
  /** True when promotion to a higher lifecycle mode is blocked by a gate or policy. */
  promotion_blocked?: boolean
  /** Explicit flag: false = not authorized for live trading. Fail-closed: absent = treat as false. */
  live_authorized?: boolean
  /** Explicit flag: false = not authorized for promotion. */
  promotion_authorized?: boolean
  /**
   * Non-empty string when backtest metrics are a stale historical snapshot
   * and must not be interpreted as authorization for paper, promotion, or live trading.
   */
  data_quality_warning?: string
  /** Describes the validation lifecycle state (e.g. "backtest_only"). */
  validation_status?: string
  /** ISO date of the most recent metric snapshot, if known. */
  metrics_as_of?: string
}

export interface Strategy extends StrategyAuthFields {
  id: string
  name: string
  description: string
  status: string
  n_assets: number
  oos_sharpe: number | null
  max_drawdown: number | null
  annual_return: number | null
  /** "LIVE" when the strategy has run in at least one portfolio cycle; "BACKTEST" otherwise. */
  data_source?: 'LIVE' | 'BACKTEST'
}

export interface StrategyDetail extends StrategyAuthFields {
  id: string
  name: string
  description: string
  status: string
  parameters: Record<string, unknown>
  universe: string[] | string
  n_assets: number
  oos_sharpe: number | null
  max_drawdown: number | null
  annual_return: number | null
  is_sharpe?: number | null
  calmar_ratio?: number | null
  sortino_ratio?: number | null
  win_rate?: number | null
  avg_holding_period?: string | null
  total_trades?: number | null
  /** "LIVE" when the strategy has run in at least one portfolio cycle; "BACKTEST" otherwise. */
  data_source?: 'LIVE' | 'BACKTEST'
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