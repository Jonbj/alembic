import { apiFetch } from './client'

export interface Signal {
  symbol: string
  score: number
  confidence: number
  model_id: string
  fallback_used: boolean
  generated_at: string
  signal_id?: number | null
  used_in_decision?: boolean
  decision_at?: string | null
  decision_type?: string | null
}

export const fetchSignals = (filters?: { symbol?: string; newsId?: number }) => {
  const params = new URLSearchParams()
  if (filters?.symbol) params.set('symbol', filters.symbol)
  if (filters?.newsId) params.set('news_id', String(filters.newsId))
  const qs = params.toString()
  return apiFetch<Signal[]>(`/api/signals${qs ? `?${qs}` : ''}`)
}
