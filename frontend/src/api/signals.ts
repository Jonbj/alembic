import { apiFetch } from './client'

export interface Signal {
  symbol: string
  score: number
  confidence: number
  model_id: string
  fallback_used: boolean
  generated_at: string
}

export const fetchSignals = (symbol?: string) => {
  const params = new URLSearchParams()
  if (symbol) params.set('symbol', symbol)
  const qs = params.toString()
  return apiFetch<Signal[]>(`/api/signals${qs ? `?${qs}` : ''}`)
}
