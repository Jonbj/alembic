import { ApiError, apiFetch } from './client'

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
  source?: string
  dropped_models?: string[]
  model_registry?: LLMModelsData
}

export interface LLMModelInfo {
  key: string
  model_id: string
  label: string
  active: boolean
  economy_default: boolean
}

export interface LLMModelsData {
  selection: string
  active_model_ids: string[]
  economy_model: string
  invalid: string[]
  models: LLMModelInfo[]
}

interface CurrentWeightsResponse {
  weights: Record<string, number>
  source: string
  dropped_models?: string[]
  model_registry?: LLMModelsData
}

interface WeightSuggestionResponse {
  current_weights?: Record<string, number>
  suggested_weights?: Record<string, number>
  purified_icir?: Record<string, number>
  freeze_reason?: string | null
  note?: string | null
}

export const fetchLLMFeedback = (params?: { limit?: number; ticker?: string; model_id?: string }) => {
  const q = new URLSearchParams()
  if (params?.limit) q.set('limit', String(params.limit))
  if (params?.ticker) q.set('ticker', params.ticker)
  if (params?.model_id) q.set('model_id', params.model_id)
  return apiFetch<LLMFeedback[]>(`/api/llm/feedback?${q}`)
}

export const fetchLLMModels = () => apiFetch<LLMModelsData>('/api/llm/models')

export const fetchWeights = async (): Promise<WeightsData> => {
  const current = await apiFetch<CurrentWeightsResponse>('/api/weights/current')
  let suggestion: WeightSuggestionResponse | null = null
  try {
    suggestion = await apiFetch<WeightSuggestionResponse>('/api/weights/suggestion')
  } catch (err) {
    if (!(err instanceof ApiError) || err.status !== 404) throw err
  }
  return {
    current: current.weights,
    suggested: suggestion?.suggested_weights ?? null,
    purified_icir: suggestion?.purified_icir ?? null,
    freeze_reason: suggestion?.freeze_reason ?? null,
    note: suggestion?.note ?? null,
    source: current.source,
    dropped_models: current.dropped_models ?? [],
    model_registry: current.model_registry,
  }
}

export const approveWeights = (note?: string) =>
  apiFetch('/api/weights/approve', { method: 'POST', body: JSON.stringify({ note }) })
