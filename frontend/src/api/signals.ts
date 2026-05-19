import { apiFetch } from './client'

export interface Signal {
  symbol: string
  score: number
  confidence: number
  model_id: string
  fallback_used: boolean
  generated_at: string
}

export const fetchSignals = (symbol?: string) =>
  apiFetch<Signal[]>(`/api/signals${symbol ? `?symbol=${symbol}` : ''}`)
