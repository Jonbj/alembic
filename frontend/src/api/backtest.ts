import { apiFetch } from './client'

export interface BacktestRun {
  run_id: string
  total: number
  scored: number
  with_return: number
  started_at: string
  ended_at: string
  symbols: number
  models: number
}

export interface BacktestSummary {
  ic: number | null
  icir: number | null
  hit_rate: number | null
  avg_long_return: number | null
  avg_short_return: number | null
  n_scored: number
  n_weeks: number
}

export interface BucketRow {
  bucket: number
  avg_score: number
  avg_return: number
  n: number
}

export interface ModelIcRow {
  model_id: string
  n: number
  ic: number | null
  hit_rate: number | null
  avg_return: number | null
}

export interface SymbolIcRow {
  symbol: string
  n: number
  ic: number | null
  hit_rate: number | null
  avg_return: number | null
}

export interface PnlPoint {
  day: string
  long_return: number | null
  short_return: number | null
  signals: number
  cum_long: number
  cum_short: number
  cum_long_short: number
}

export interface BacktestSignal {
  id: number
  symbol: string
  score: number | null
  confidence: number | null
  model_id: string
  ensemble_std: number | null
  fallback_used: boolean
  forward_return_24h: number | null
  forward_return_4h: number | null
  forward_return_1h: number | null
  news_source: string | null
  generated_at: string
}

export const backtestApi = {
  runs: () => apiFetch<BacktestRun[]>('/api/backtest/runs'),
  summary: (runId: string) => apiFetch<BacktestSummary>(`/api/backtest/${runId}/summary`),
  bucketAnalysis: (runId: string, buckets = 10) =>
    apiFetch<BucketRow[]>(`/api/backtest/${runId}/bucket_analysis?buckets=${buckets}`),
  modelIc: (runId: string) => apiFetch<ModelIcRow[]>(`/api/backtest/${runId}/model_ic`),
  symbolIc: (runId: string) => apiFetch<SymbolIcRow[]>(`/api/backtest/${runId}/symbol_ic`),
  pnlCurve: (runId: string, threshold = 0.05) =>
    apiFetch<PnlPoint[]>(`/api/backtest/${runId}/pnl_curve?threshold=${threshold}`),
  signals: (runId: string, limit = 200, offset = 0, symbol?: string) => {
    const qs = new URLSearchParams({ limit: String(limit), offset: String(offset) })
    if (symbol) qs.set('symbol', symbol)
    return apiFetch<BacktestSignal[]>(`/api/backtest/${runId}/signals?${qs}`)
  },
}
