import { apiFetch } from './client'

export interface LLMFeedback {
  id: number
  signal_id: number
  symbol: string
  model_id: string
  polarity: number
  confidence: number
  reasoning: string
  eligible: boolean
  generated_at: string
  fallback_used: boolean
  ensemble_std: number
}

export interface WeightsData {
  current: Record<string, number>
  suggested: Record<string, number> | null
  purified_icir: Record<string, number> | null
  freeze_reason: string | null
  note: string | null
}

export const fetchLLMFeedback = (params?: { limit?: number; ticker?: string; model_id?: string }) => {
  const q = new URLSearchParams()
  if (params?.limit) q.set('limit', String(params.limit))
  if (params?.ticker) q.set('ticker', params.ticker)
  if (params?.model_id) q.set('model_id', params.model_id)
  return apiFetch<LLMFeedback[]>(`/api/llm/feedback?${q}`)
}

export const fetchWeights = () => apiFetch<WeightsData>('/api/weights/current')

export const approveWeights = (note?: string) =>
  apiFetch('/api/weights/approve', { method: 'POST', body: JSON.stringify({ note }) })
