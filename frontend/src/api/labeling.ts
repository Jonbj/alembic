import { apiFetch } from './client'

export interface LabelItem {
  done: boolean
  label_id?: number
  source?: string
  title?: string
  body_snippet?: string | null
  published_at?: string | null
  text_adequacy?: string | null
}

export interface LabelProgress {
  labeled: number
  pending: number
  total: number
}

export interface LabelSubmit {
  gt_tickers: string[]
  gt_relevance: string
  gt_sentiment_dir: string
  gt_sentiment_strength: number
  gt_rationale?: string
  annotator_id?: string
}

export const fetchNextLabel = () => apiFetch<LabelItem>('/api/labeling/next')
export const fetchLabelProgress = () => apiFetch<LabelProgress>('/api/labeling/progress')
export const submitLabel = (labelId: number, body: LabelSubmit) =>
  apiFetch<{ label_id: number; status: string }>(`/api/labeling/${labelId}`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
