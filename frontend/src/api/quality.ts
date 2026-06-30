import { apiFetch } from './client'

export interface PerModel {
  model_id: string
  n: number
  mean_polarity: number | null
  std_polarity: number | null
  mean_confidence: number | null
  near_zero_rate: number | null
  eligible_rate: number | null
}

export interface QualityMetrics {
  window_days: number
  per_model: PerModel[]
  signals: {
    n?: number
    mean_score?: number | null
    std_score?: number | null
    near_zero_rate?: number | null
    fallback_rate?: number | null
    mean_ensemble_std?: number | null
  }
  extraction: {
    n_labeled: number
    precision?: number | null
    recall?: number | null
    recall_in_watchlist?: number | null
    fp_per_article?: number | null
    macro_fp_per_article?: number | null
  }
}

export const fetchQualityMetrics = (days = 14) =>
  apiFetch<QualityMetrics>(`/api/quality/metrics?days=${days}`)
